"""Budget-estimator tests (v0.7): read_budget over a synthetic ledger,
frontier semantics, envelope determinism and floor monotonicity."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa.budget import envelope, frontier, read_budget
from qsa.deflation import bonferroni_tstat_floor
from qsa.settlement import SettlementLedger


def _entry(i: int, claim: float, real: float, outcome: str, plant: bool,
           turnover: float = 0.5, gross: float = 0.001, net: float = 0.0):
    return {
        "schema": "settlement", "settle_id": f"S-{i:04d}",
        "exp_id": f"E-{i:04d}", "family": "f", "iteration": 1,
        "world": {"kind": "synthetic", "extension_days": 90,
                  "plant": ({"effect": "reversal", "strength": 0.15}
                            if plant else None)},
        "claimed": {"value": claim, "metric": "rankic_mean"},
        "realized": {"rankic_mean": real, "turnover": turnover,
                     "quintile_spread": gross, "net_quintile_spread": net},
        "outcome": outcome, "base_snapshot_hash": f"{i:064x}",
    }


class TestReadBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        led = SettlementLedger.open(self.root / "l.jsonl")
        rows = [
            _entry(1, 0.10, 0.09, "held", True, net=0.0005),
            _entry(2, 0.08, 0.02, "held", True, net=0.0003),
            _entry(3, 0.09, 0.01, "fell_short", False, net=-0.0002),
            _entry(4, 0.11, 0.10, "held", True, net=0.0006),
        ]
        for r in rows:
            led.record(r)
        self.led_path = self.root / "l.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_terms_read_off_ledger(self):
        t = read_budget(self.led_path)
        self.assertEqual(t["B"], 4)
        self.assertEqual(t["n_settled"], 4)
        self.assertEqual(t["held"], 3)
        # ĪC = mean realized rank IC over held claims
        self.assertAlmostEqual(t["ic_hat"], (0.09 + 0.02 + 0.10) / 3)
        # P̂ anchor = planted share of settled claims
        self.assertAlmostEqual(t["p_hat_planted_anchor"], 0.75)
        self.assertEqual(t["horizon_days"], 90)
        self.assertIsInstance(t["decay_slope"], float)
        tc = t["tc"]
        self.assertEqual(tc["n"], 4)
        self.assertAlmostEqual(tc["mean_turnover"], 0.5)
        self.assertAlmostEqual(tc["mean_net_spread"], 0.0003)

    def test_deterministic(self):
        self.assertEqual(read_budget(self.led_path), read_budget(self.led_path))


class TestFrontier(unittest.TestCase):
    def test_power_falls_and_phat_rises_with_floor(self):
        planted = [3.0, 2.5, 2.0, 1.5]
        noise = [1.0, 0.5, 0.2, -0.3]
        rows = frontier(planted, noise, [0.0, 1.0, 2.0, 3.0])
        self.assertEqual(rows[0]["power"], 1.0)
        self.assertEqual(rows[-1]["power"], 0.25)
        for a, b in zip(rows, rows[1:]):
            self.assertLessEqual(b["power"], a["power"])
            self.assertGreaterEqual(b["p_hat"], a["p_hat"])
        for r in rows:
            self.assertTrue(0.0 <= r["p_hat"] <= 1.0)


class TestEnvelope(unittest.TestCase):
    def test_floor_monotone_and_rows_deterministic(self):
        planted = [4.0, 3.0, 2.2]
        noise = [1.0, -0.5]
        ns = [1, 2, 4, 8, 16, 32]
        a = envelope(planted, noise, ns)
        b = envelope(planted, noise, ns)
        self.assertEqual(a, b)
        floors = [r["floor"] for r in a]
        self.assertEqual(floors, sorted(floors))
        self.assertEqual(floors[0], 0.0)  # N=1: no deflation
        for r, n in zip(a, ns):
            self.assertEqual(r["N"], n)
            # breadth net of verification never exceeds raw breadth (up to
            # the 6dp rounding of the row fields)
            self.assertLessEqual(r["envelope"],
                                 r["discovery"] * n ** 0.5 + 2e-6)

    def test_bonferroni_floor_matches_deflation(self):
        self.assertEqual(bonferroni_tstat_floor(1), 0.0)
        self.assertGreater(bonferroni_tstat_floor(10),
                           bonferroni_tstat_floor(2))


if __name__ == "__main__":
    unittest.main()
