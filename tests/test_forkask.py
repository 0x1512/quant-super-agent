"""Tests for qsa.forkask (v1.4 ⑦): the fork card as a real question.

Contract: a decided fork is reused, never re-asked; an open fork asks a
human with numbered options; invalid input re-prompts; EOF/empty falls
to the declared default and says so; the ledger stays append-only (a
second decide on the same fork is refused by ForkCards itself).
"""
import io
import json
import tempfile
import unittest
from pathlib import Path

from qsa.forkask import ask
from qsa.infragate import ForkCards


OPTS = [{"label": "小cap", "desc": "剔除大盘"},
        {"label": "全市场", "desc": "不剔"}]
KW = {"question": "要不要剔除小盘？", "options": OPTS,
      "recommended": "小cap", "default": "全市场"}


class ForkCase(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.path = Path(self.td.name) / "forks.jsonl"
        self.cards = ForkCards(self.path)

    def tearDown(self):
        self.td.cleanup()

    def events(self):
        return [json.loads(x) for x in
                self.path.read_text("utf-8").splitlines() if x.strip()]

    def test_ask_records_choice_by_human(self):
        r = ask(self.cards, "u-cut", stdin=io.StringIO("1\n"),
                stdout=io.StringIO(), **KW)
        self.assertEqual(r["choice"], "小cap")
        self.assertFalse(r["reused"])
        self.assertFalse(r["applied_default"])
        evs = self.events()
        self.assertEqual([e["type"] for e in evs], ["fork", "decision"])
        self.assertEqual(evs[1]["by"], "human")

    def test_second_ask_reuses_without_new_events(self):
        ask(self.cards, "u-cut", stdin=io.StringIO("1\n"),
            stdout=io.StringIO(), **KW)
        out = io.StringIO()
        r = ask(self.cards, "u-cut", stdin=io.StringIO("9\n"),
                stdout=out, **KW)          # would-be-invalid never read
        self.assertTrue(r["reused"])
        self.assertEqual(r["choice"], "小cap")
        self.assertIn("沿用", out.getvalue())
        self.assertEqual(len(self.events()), 2)   # append-only: no new ev

    def test_invalid_then_valid_choice(self):
        out = io.StringIO()
        r = ask(self.cards, "u-cut", stdin=io.StringIO("banana\n2\n"),
                stdout=out, **KW)
        self.assertEqual(r["choice"], "全市场")
        self.assertIn("无效选择", out.getvalue())

    def test_eof_falls_to_default_loudly(self):
        out = io.StringIO()
        r = ask(self.cards, "u-cut", stdin=io.StringIO(""), stdout=out,
                **KW)
        self.assertEqual(r["choice"], "全市场")
        self.assertTrue(r["applied_default"])
        self.assertEqual(
            self.events()[1]["by"], "default-policy")
        self.assertIn("（默认）", out.getvalue())

    def test_label_text_choice_accepted(self):
        r = ask(self.cards, "u-cut", stdin=io.StringIO("全市场\n"),
                stdout=io.StringIO(), **KW)
        self.assertEqual(r["choice"], "全市场")

    def test_ledger_refuses_double_decide(self):
        ask(self.cards, "u-cut", stdin=io.StringIO("1\n"),
            stdout=io.StringIO(), **KW)
        with self.assertRaises(ValueError):
            self.cards.decide("u-cut", "全市场", by="human",
                              rationale="again")


if __name__ == "__main__":
    unittest.main()
