"""Tests for the blackboard (v1.2).

Covers the integrity contract, not just the happy path:
* append + reload: chain survives a new process (new instance re-verifies)
* tamper detection: any rewritten entry breaks the chain
* blocker discipline: require_clear raises; resolve clears it
* kind whitelist: unknown kinds are refused
* bootstrapped(): idempotent, non-empty, real lessons present
"""
import json
import tempfile
import unittest
from pathlib import Path

from qsa.blackboard import Blackboard, KINDS, bootstrapped


class TestBlackboard(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "bb" / "blackboard.jsonl"

    def tearDown(self):
        self.dir.cleanup()

    def test_append_and_reload(self):
        bb = Blackboard(self.path)
        bb.post("data_pitfall", "trap A", "body A")
        bb.post("order_note", "note B", "body B", status="info",
                 tags=["t"])
        # new instance must re-verify the chain and see both entries
        bb2 = Blackboard(self.path)
        self.assertEqual(len(bb2), 2)
        self.assertEqual(bb2.entries(kind="data_pitfall")[0]["title"],
                         "trap A")
        self.assertEqual(bb2.entries()[1]["tags"], ["t"])

    def test_tamper_detected(self):
        bb = Blackboard(self.path)
        bb.post("data_pitfall", "real", "body")
        bb.post("data_pitfall", "real", "body")
        # rewrite the first entry's body silently
        lines = self.path.read_text(encoding="utf-8").splitlines()
        ev = json.loads(lines[0])
        ev["body"] = "doctored"
        lines[0] = json.dumps(ev, ensure_ascii=False)
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            Blackboard(self.path)
        self.assertIn("tampered", str(ctx.exception))

    def test_deleted_entry_detected(self):
        bb = Blackboard(self.path)
        for i in range(3):
            bb.post("order_note", f"n{i}", "b")
        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.path.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            Blackboard(self.path)

    def test_blocker_discipline(self):
        bb = Blackboard(self.path)
        bb.require_clear()  # empty board is clear
        bb.post("data_pitfall", "disk full", "cache dir exhausted",
                 status="blocker")
        with self.assertRaises(RuntimeError) as ctx:
            bb.require_clear()
        self.assertIn("disk full", str(ctx.exception))
        # resolve appends, never rewrites
        idx = len(bb) - 1
        bb.resolve(idx)
        bb.require_clear()  # resolved blocker no longer blocks
        self.assertEqual(bb.entries(kind="order_note")[0]["title"],
                         "RESOLVED: disk full")
        # resolving a non-blocker is refused (entry 1 is the note)
        with self.assertRaises(ValueError):
            bb.resolve(1)

    def test_unknown_kind_refused(self):
        bb = Blackboard(self.path)
        with self.assertRaises(ValueError):
            bb.post("vibes", "x", "y")
        self.assertEqual(len(bb), 0)
        for k in KINDS:
            bb.post(k, "t", "b")
        self.assertEqual(len(bb), 4)

    def test_search_case_insensitive(self):
        bb = Blackboard(self.path)
        bb.post("data_pitfall", "Pre-close trap", "lowercase body here")
        self.assertEqual(len(bb.search("PRE-CLOSE")), 1)
        self.assertEqual(len(bb.search("lowercase")), 1)
        self.assertEqual(len(bb.search("nope")), 0)

    def test_bootstrapped_idempotent_and_real(self):
        bb = bootstrapped(self.path)
        n1 = len(bb)
        self.assertGreaterEqual(n1, 8)
        # a second bootstrap must not re-seed
        bb2 = bootstrapped(self.path)
        self.assertEqual(len(bb2), n1)
        kinds = {e["kind"] for e in bb2.entries()}
        self.assertIn("data_pitfall", kinds)
        self.assertIn("convention_decision", kinds)
        self.assertIn("decay_event", kinds)
        # the paid-for lessons are actually there
        self.assertTrue(bb2.search("pre_close"))
        self.assertTrue(bb2.search("cap_proxy"))
        self.assertTrue(bb2.search("overnight_gap_21d"))


if __name__ == "__main__":
    unittest.main()
