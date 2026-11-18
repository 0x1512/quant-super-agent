"""Panel tests — SUPERAGENT_PLAN2 #7 acceptance, mechanically pinned.

From the plan:
* a fully healthy workshop has an EMPTY first screen — health takes
  no space, the panorama folds into <details> at the tail;
* one blocker + one fork card injected: the first screen carries
  exactly those two, each with its ledger reference;
* zero JavaScript: `grep -c "<script"` over the page is 0 (三通道制);
* every number on the page is re-derived from the ledgers in the test.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa import blackboard as bb                      # noqa: E402
from qsa.infragate import ForkCards                   # noqa: E402
from qsa.panel import collect, render_html            # noqa: E402
from qsa.queue import Queue                           # noqa: E402


class PanelCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-panel-"))
        self.root = self.tmp / "work"
        self.root.mkdir()

    def page(self) -> str:
        return render_html(self.root)


class TestHealthy(PanelCase):
    def test_first_screen_empty_and_panorama_folded(self):
        page = self.page()
        # healthy takes no space: no cards, no section headers
        self.assertNotIn('class="card"', page)
        self.assertNotIn("<h2>", page)
        # the empty state is the ONLY first-screen content
        self.assertIn("没有在等你的事", page)
        # the panorama exists but folded, after the empty state
        self.assertIn("<details>", page)
        self.assertIn("车间全景", page)
        self.assertLess(page.index("没有在等你的事"),
                        page.index("<details>"))

    def test_zero_javascript(self):
        for _ in range(2):
            page = self.page()
        self.assertEqual(page.count("<script"), 0)
        self.assertEqual(page.count("onload"), 0)


class TestWaiting(PanelCase):
    def test_blocker_and_fork_are_the_whole_first_screen(self):
        fc = ForkCards(self.root / "forks.jsonl")
        fc.raise_fork("BB-FORK-99",
                      "neutralization universe for the next run?",
                      [{"label": "top-300", "desc": "current default"},
                       {"label": "full-market", "desc": "slower, wider"}],
                      recommended="top-300", default="top-300")
        board = bb.Blackboard(self.root / "blackboard.jsonl")
        board.post("order_note", "snapshot stale > 30d",
                   "rebuild before admitting new orders",
                   status="blocker")
        page = self.page()
        # exactly two cards, nothing else on the first screen
        self.assertEqual(page.count('class="card"'), 2)
        self.assertIn("拍板待选", page)
        self.assertIn("未解 blocker", page)
        # each card carries its ledger reference
        self.assertIn("forks.jsonl", page)
        self.assertIn("BB-FORK-99", page)
        self.assertIn("FORK BB-FORK-99 选 N", page)   # how to decide
        # the blocker cites its ledger index (the board is fresh, so
        # the blocker is entry 0) and its chain hash — checkable on disk
        self.assertIn(f"blackboard.jsonl #{len(board.entries()) - 1}",
                      page)
        self.assertIn(board.entries()[-1]["chain"][:10], page)

    def test_numbers_reconcile_with_ledgers(self):
        fc = ForkCards(self.root / "forks.jsonl")
        for i in range(3):
            fc.raise_fork(f"F-{i}", f"q{i}", [{"label": "a"}, {"label": "b"}],
                          recommended="a", default="a")
        board = bb.Blackboard(self.root / "blackboard.jsonl")
        for i in range(2):
            board.post("order_note", f"b{i}", "x", status="blocker")
        page = self.page()
        w = collect(self.root)
        self.assertEqual(len(w["forks"]), 3)      # re-derived from ledger
        self.assertEqual(len(w["blockers"]), 2)
        # the badges on the page agree with the recount
        self.assertIn(f'<span class="badge fork">{len(w["forks"])}</span>',
                      page)
        self.assertIn(
            f'<span class="badge blocker">{len(w["blockers"])}</span>', page)

    def test_resolved_blocker_leaves_the_first_screen(self):
        board = bb.Blackboard(self.root / "blackboard.jsonl")
        board.post("order_note", "temp blocker", "x", status="blocker")
        self.assertEqual(self.page().count('class="card"'), 1)
        board.resolve(0)
        self.assertEqual(self.page().count('class="card"'), 0)
        self.assertIn("没有在等你的事", self.page())


class TestOverflow(PanelCase):
    def test_backpressure_receipt_gets_its_own_section(self):
        q = Queue(self.root, slots=1, max_queue=0)
        self.assertIsNone(q.submit("goal overflowed", {"tag": "z"}))
        page = self.page()
        self.assertIn("队列满溢", page)
        self.assertIn("goal overflowed", page)
        # and it does NOT masquerade as a plain blocker section
        self.assertNotIn("未解 blocker", page)

    def test_overflow_count_matches_receipts_on_disk(self):
        q = Queue(self.root, slots=1, max_queue=0)
        for i in range(2):
            q.submit(f"goal {i}", {})
        n_receipts = len([e for e in
                          bb.Blackboard(self.root / "blackboard.jsonl")
                          .entries()
                          if e.get("status") == "blocker"
                          and "queue" in (e.get("tags") or [])])
        page = self.page()
        self.assertEqual(n_receipts, 2)
        self.assertIn(f'<span class="badge overflow">{n_receipts}</span>',
                      page)


class TestCli(PanelCase):
    def test_out_flag_writes_the_file(self):
        import subprocess
        out = self.tmp / "panel.html"
        r = subprocess.run(
            [sys.executable, "-m", "qsa.panel", "--root", str(self.root),
             "--out", str(out)],
            capture_output=True, text=True, cwd=Path(__file__).parents[1])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("zero JS", r.stdout)
        page = out.read_text("utf-8")
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertEqual(page.count("<script"), 0)


if __name__ == "__main__":
    unittest.main()
