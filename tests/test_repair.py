"""Tests for qsa.repair (v1.4 ⑤): the self-repair ladder.

Policy (pre-registered): missing_tail is repaired by truncating to the
common calendar (floor 60 dates); everything else — duplicate pairs,
unparseable numbers — is REFUSED, loudly, because no whitelisted policy
exists. The ladder must be able to refuse, and a repair that would
shrink the panel below the floor refuses too.
"""
import unittest

from qsa import repair


def panel_rows(n_dates: int = 70, n_tk: int = 3,
               short_from: int | None = None) -> list[dict]:
    dates = [f"202301{i:02d}" if i < 32 else f"202302{i - 31:02d}"
             for i in range(1, n_dates + 1)]
    rows = []
    for tk in range(n_tk):
        upto = len(dates)
        if short_from is not None and tk == n_tk - 1:
            upto = short_from          # last ticker stops early
        for d in dates[:upto]:
            rows.append({"date": d, "ticker": f"T{tk}",
                         "close": "10.0", "open": "9.5", "volume": "100"})
    return rows


class TestClassify(unittest.TestCase):
    def test_clean_panel_no_violations(self):
        self.assertEqual(repair.classify(panel_rows()), [])

    def test_missing_tail_detected(self):
        v = repair.classify(panel_rows(short_from=65))
        self.assertEqual([x.kind for x in v], ["missing_tail"])
        self.assertEqual(v[0].affected, ["T2"])

    def test_bad_number_detected(self):
        rows = panel_rows()
        rows[3]["close"] = "not-a-number"
        kinds = [x.kind for x in repair.classify(rows)]
        self.assertIn("bad_number", kinds)

    def test_duplicate_pair_detected(self):
        rows = panel_rows() + [panel_rows()[0]]
        kinds = [x.kind for x in repair.classify(rows)]
        self.assertIn("duplicate_pair", kinds)


class TestLadder(unittest.TestCase):
    def test_missing_tail_repaired_to_common_calendar(self):
        rows, log = repair.apply_ladder(panel_rows(short_from=65))
        kept_dates = {r["date"] for r in rows}
        self.assertEqual(len(kept_dates), 65)
        self.assertEqual(len(log.applied), 1)
        self.assertEqual(log.applied[0]["kind"], "missing_tail")
        self.assertIn("common calendar", log.applied[0]["detail"])
        # idempotent: the repaired panel classifies clean
        self.assertEqual(repair.classify(rows), [])

    def test_floor_refusal(self):
        rows = panel_rows(n_dates=70, short_from=50)
        with self.assertRaises(repair.IngestViolation) as cm:
            repair.apply_ladder(rows)
        self.assertIn("60", str(cm.exception))   # names the floor

    def test_duplicate_refused_no_policy(self):
        rows = panel_rows() + [panel_rows()[0]]
        with self.assertRaises(repair.IngestViolation):
            repair.apply_ladder(rows)

    def test_bad_number_refused(self):
        rows = panel_rows()
        rows[3]["close"] = ""
        with self.assertRaises(repair.IngestViolation):
            repair.apply_ladder(rows)

    def test_render_names_the_ladder_and_refusals(self):
        _, log = repair.apply_ladder(panel_rows(short_from=65))
        md = log.render()
        self.assertIn("数据修复梯", md)
        self.assertIn("✅", md)
        log2 = repair.RepairLog(
            refused=[{"kind": "duplicate_pair", "detail": "d",
                      "affected": []}])
        self.assertIn("⛔", log2.render())
        self.assertEqual(repair.RepairLog().render(), "")


if __name__ == "__main__":
    unittest.main()
