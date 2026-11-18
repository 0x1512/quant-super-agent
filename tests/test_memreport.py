"""Tests for qsa.memreport (v1.4 ⑧) + the `standard` board kind.

只紧不松 is a falsifiable claim: the ratchet check must PASS on a
monotone tightening history and FAIL on any loosening — wrong
direction, a min-bar sinking, or a max-bar rising. The ledger renders
real board entries grouped by kind plus the manifests of past runs.
"""
import json
import tempfile
import unittest
from pathlib import Path

from qsa.blackboard import Blackboard
from qsa.memreport import ledger, ratchet_check


def board_with_standards(*entries) -> Blackboard:
    """entries: tuples (standard, value, sense, direction)."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "bb.jsonl"
    bb = Blackboard(path)
    for st, val, sense, direction in entries:
        bb.post("standard", f"{st} -> {val}", f"ratchet test {st}",
                fields={"standard": st, "value": val, "sense": sense,
                        "direction": direction})
    return bb


class TestRatchet(unittest.TestCase):
    def test_empty_board_passes(self):
        with tempfile.TemporaryDirectory() as td:
            r = ratchet_check(Blackboard(Path(td) / "bb.jsonl"))
        self.assertTrue(r["ok"])
        self.assertEqual(r["n_standards"], 0)

    def test_monotone_tightening_passes(self):
        bb = board_with_standards(("oos_ic_bar", 0.03, "min", "tighten"),
                                  ("oos_ic_bar", 0.05, "min", "tighten"),
                                  ("max_cands", 200, "max", "tighten"),
                                  ("max_cands", 150, "max", "tighten"))
        r = ratchet_check(bb)
        self.assertTrue(r["ok"])
        self.assertEqual(r["history"]["oos_ic_bar"], [0.03, 0.05])
        self.assertEqual(r["history"]["max_cands"], [200, 150])

    def test_loosen_direction_fails(self):
        bb = board_with_standards(("oos_ic_bar", 0.05, "min", "loosen"))
        r = ratchet_check(bb)
        self.assertFalse(r["ok"])
        self.assertIn("direction=loosen", r["violations"][0])

    def test_min_bar_sinking_fails(self):
        bb = board_with_standards(("oos_ic_bar", 0.05, "min", "tighten"),
                                  ("oos_ic_bar", 0.02, "min", "tighten"))
        r = ratchet_check(bb)
        self.assertFalse(r["ok"])
        self.assertIn("变松", r["violations"][0])

    def test_max_bar_rising_fails(self):
        bb = board_with_standards(("max_cands", 100, "max", "tighten"),
                                  ("max_cands", 300, "max", "tighten"))
        r = ratchet_check(bb)
        self.assertFalse(r["ok"])

    def test_equal_value_is_not_loosening(self):
        bb = board_with_standards(("oos_ic_bar", 0.05, "min", "tighten"),
                                  ("oos_ic_bar", 0.05, "min", "tighten"))
        self.assertTrue(ratchet_check(bb)["ok"])

    def test_missing_standard_name_fails_legibly(self):
        with tempfile.TemporaryDirectory() as td:
            bb = Blackboard(Path(td) / "bb.jsonl")
            bb.post("standard", "anonymous tightening", "no name",
                    fields={"value": 0.1, "sense": "min",
                            "direction": "tighten"})
            r = ratchet_check(bb)
        self.assertFalse(r["ok"])
        self.assertIn("缺 standard 名", r["violations"][0])

    def test_chain_covers_structured_fields(self):
        bb = board_with_standards(("oos_ic_bar", 0.03, "min", "tighten"))
        raw = json.loads(bb.path.read_text("utf-8").splitlines()[0])
        self.assertIn("standard", raw)
        with self.assertRaises(ValueError):     # tampering breaks chain
            tampered = raw.copy()
            tampered["value"] = 0.99
            bb.path.write_text(json.dumps(tampered) + "\n",
                               encoding="utf-8")
            Blackboard(bb.path)


class TestLedger(unittest.TestCase):
    def test_renders_sections_verdict_and_manifests(self):
        bb = board_with_standards(("oos_ic_bar", 0.03, "min", "tighten"))
        bb.post("data_pitfall", "preclose 字段名坑",
                "Requesting 'preclose' is silently dropped.")
        bb.post("decay_event", "overnight_gap_21d decays",
                "front -0.056 / back -0.040")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "run-a").mkdir()
            (root / "run-a" / "manifest.json").write_text(json.dumps({
                "run": "run-a", "workers": 13, "elapsed_s": 50.7,
                "jobs_by_role": {"GateKeeper": 24, "RepoSmith": 30}}),
                encoding="utf-8")
            md = ledger(bb, root)
        self.assertIn("记忆黑板台账", md)
        self.assertIn("数据坑", md)
        self.assertIn("衰减与死亡判定", md)
        self.assertIn("✅ 通过", md)
        self.assertIn("run-a", md)
        self.assertIn("GateKeeper×24", md)

    def test_failed_ratchet_shows_in_ledger(self):
        bb = board_with_standards(("oos_ic_bar", 0.05, "min", "tighten"),
                                  ("oos_ic_bar", 0.02, "min", "tighten"))
        self.assertIn("⛔ 失败", ledger(bb))

    def test_empty_board_renders_honestly(self):
        with tempfile.TemporaryDirectory() as td:
            md = ledger(Blackboard(Path(td) / "bb.jsonl"))
        self.assertIn("还没有教训", md)


if __name__ == "__main__":
    unittest.main()
