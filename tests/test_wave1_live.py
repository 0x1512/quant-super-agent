"""Wave1-live show as a regression asset — the demo must never rot.

The show (examples/run_wave1_live.py) asserts its own beats; this test
runs the whole thing against a fresh work dir and additionally checks
the sealed LIVE_NUMBERS.json. If any Wave-1 promise breaks later, the
DEMO crashes here before the marketing page can lie.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestWave1Live(unittest.TestCase):
    def test_ten_goals_all_pass_and_numbers_seal(self):
        with tempfile.TemporaryDirectory(prefix="wave1-live-") as td:
            work = Path(td) / "show"
            r = subprocess.run(
                [sys.executable, str(ROOT / "examples" / "run_wave1_live.py"),
                 "--work", str(work)],
                capture_output=True, text=True, timeout=300, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)
            self.assertIn("10/10 goals PASS", r.stdout)
            n = json.loads((work / "LIVE_NUMBERS.json").read_text("utf-8"))
            # the promises the marketing page may quote — pinned
            self.assertEqual(n["commands"], 3)
            self.assertEqual(n["panel_scripts"], 0)
            self.assertEqual(n["rows_rescored"], 0)
            self.assertEqual(n["dropped"], 0)
            self.assertEqual(n["re_asked"], 0)
            self.assertEqual(n["n_orders"], 24)
            self.assertEqual(n["settled"] + n["refused"], n["n_orders"])
            self.assertLess(n["revive_s"], 1.0)
            self.assertGreater(n["per_factor_speedup_x"], 10)
            self.assertGreaterEqual(n["restarts"], 1)   # survived kill -9
            self.assertGreaterEqual(n["numbers"], 3)    # package verified
            self.assertLess(n["total_show_s"], 120.0)

    def test_show_is_reproducible_in_shape(self):
        # a second run on a second dir agrees on every behavior number
        nums = []
        for i in range(2):
            with tempfile.TemporaryDirectory(prefix="wave1-rep-") as td:
                work = Path(td) / "show"
                r = subprocess.run(
                    [sys.executable,
                     str(ROOT / "examples" / "run_wave1_live.py"),
                     "--work", str(work)],
                    capture_output=True, text=True, timeout=300, cwd=ROOT)
                self.assertEqual(r.returncode, 0, r.stderr[-500:])
                n = json.loads(
                    (work / "LIVE_NUMBERS.json").read_text("utf-8"))
                nums.append({k: v for k, v in n.items()
                             if not k.endswith("_s")
                             and k not in ("work_root", "speedup_x",
                                           "per_factor_speedup_x",
                                           "package_bytes")})
        self.assertEqual(nums[0], nums[1])


if __name__ == "__main__":
    unittest.main()
