"""Forge tests: determinism, CI recording, branch-protection merge blocking."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from qsa.forge import Forge

OK_CI = [sys.executable, "-c", "print('gate green')"]
FAIL_CI = [sys.executable, "-c", "import sys; print('gate red'); sys.exit(1)"]


def scenario(root: Path, ci: list[str]) -> tuple[Forge, bool]:
    forge = Forge.init(root)
    issue = forge.create_issue("order", "do the research")
    sha = forge.commit("research/H-0001", "cards", {"cards/E.json": "{}"})
    check = forge.push("research/H-0001", ci)
    pr = forge.create_pr("evidence", head="research/H-0001")
    forge.add_comment(issue, f"CI: {check['conclusion']}")
    merged = forge.merge_pr(pr)
    return forge, merged


class TestForge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_state_is_byte_deterministic(self):
        f1, _ = scenario(self.root / "a", OK_CI)
        f2, _ = scenario(self.root / "b", OK_CI)
        self.assertEqual((self.root / "a" / "state.json").read_bytes(),
                         (self.root / "b" / "state.json").read_bytes())
        self.assertEqual((self.root / "a" / "events.jsonl").read_bytes(),
                         (self.root / "b" / "events.jsonl").read_bytes())

    def test_green_ci_merges(self):
        _, merged = scenario(self.root / "green", OK_CI)
        self.assertTrue(merged)

    def test_red_ci_blocks_merge(self):
        forge, merged = scenario(self.root / "red", FAIL_CI)
        self.assertFalse(merged)
        events = (self.root / "red" / "events.jsonl").read_text()
        self.assertIn("merge_blocked", events)
        self.assertIn("gate red", events)  # failure reason carried in the event

    def test_merge_without_ci_blocked(self):
        forge = Forge.init(self.root / "noci")
        forge.commit("research/H-0002", "cards", {"x": "1"})
        pr = forge.create_pr("evidence", head="research/H-0002")
        self.assertFalse(forge.merge_pr(pr))
        self.assertIn("merge_blocked",
                      (self.root / "noci" / "events.jsonl").read_text())

    def test_check_run_output_recorded(self):
        forge = Forge.init(self.root / "out")
        forge.commit("b", "m", {"x": "1"})
        run = forge.push("b", FAIL_CI)
        self.assertEqual(run["conclusion"], "failure")
        self.assertTrue(any("gate red" in ln for ln in run["output_tail"]))


if __name__ == "__main__":
    unittest.main()
