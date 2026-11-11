"""End-to-end demo tests: honest lifecycle merges; FIB injections get blocked
by the gate inside the forge; the whole run is byte-deterministic."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa.demo import run_lifecycle


class TestDemo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_honest_lifecycle_merges(self):
        summary = run_lifecycle(self.root / "honest", verbose=False)
        self.assertTrue(summary["merged"])
        self.assertEqual(summary["check"]["conclusion"], "success")
        self.assertIn(summary["verdict"], ("pass", "fail"))

    def test_fib7_silent_pass_blocked_end_to_end(self):
        summary = run_lifecycle(self.root / "fib7", fib="7", verbose=False)
        self.assertFalse(summary["merged"])
        self.assertEqual(summary["check"]["conclusion"], "failure")
        self.assertTrue(any("verdict" in ln for ln in summary["check"]["output_tail"]))

    def test_fib4_snapshot_mismatch_blocked_end_to_end(self):
        summary = run_lifecycle(self.root / "fib4", fib="4", verbose=False)
        self.assertFalse(summary["merged"])

    def test_fib15_window_shrink_blocked_end_to_end(self):
        summary = run_lifecycle(self.root / "fib15", fib="15", verbose=False)
        self.assertFalse(summary["merged"])

    def test_lifecycle_is_deterministic(self):
        run_lifecycle(self.root / "det-a", verbose=False)
        run_lifecycle(self.root / "det-b", verbose=False)
        for rel in ("state.json", "events.jsonl"):
            inner = Path("forge") / rel
            self.assertEqual((self.root / "det-a" / inner).read_bytes(),
                             (self.root / "det-b" / inner).read_bytes(),
                             f"{rel} differs across identical lifecycles")


if __name__ == "__main__":
    unittest.main()
