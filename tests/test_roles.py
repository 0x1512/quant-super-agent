"""Role-layer tests: ablatable roles with mechanical duties (v0.4)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa import engine
from qsa.roles import ROLES, check_roles, data_check, risk_check
from qsa.sandbox import run_factor
from qsa.snapshot import build_snapshot

F_REV = '''def factor(closes, tickers, dates, i):
    if i < 1:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 1]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = -(a / b - 1.0)
    return out
'''


def _h(window: str, min_obs: int = 30) -> dict:
    return {"hyp_id": "H-0001", "mechanism": "reversal",
            "falsifiable_condition": "ic <= 0", "window": window,
            "admission": {"required_metrics": ["rankic_mean"],
                          "thresholds": {"rankic_mean": {"op": ">=", "value": 0.02}},
                          "min_observations": min_obs}}


class TestRoles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snap = self.root / "snap"
        build_snapshot(self.snap, seed=42, tickers=12, days=90)
        self.dates = engine.load_frame(self.snap).dates

    def tearDown(self):
        self.tmp.cleanup()

    def test_role_registry_is_complete(self):
        self.assertEqual(sorted(ROLES), ["data", "factor", "manager", "risk"])
        for spec in ROLES.values():
            self.assertTrue(spec.system.strip() and spec.duty.strip())

    def test_check_roles_rejects_unknown_and_factorless(self):
        with self.assertRaises(ValueError):
            check_roles(("data", "wizard"))
        with self.assertRaises(ValueError):
            check_roles(("data", "risk"))  # no factor role
        self.assertEqual(check_roles(["factor", "factor", "risk"]),
                         ("factor", "risk"))

    def test_data_check_accepts_sound_design(self):
        self.assertEqual(data_check(_h(f"{self.dates[0]}:{self.dates[-1]}"),
                                    self.snap), [])

    def test_data_check_blocks_window_outside_snapshot(self):
        errs = data_check(_h("19990104:19990131"), self.snap)
        self.assertTrue(errs and "not inside snapshot" in errs[0])

    def test_data_check_blocks_underpowered_design(self):
        errs = data_check(_h(f"{self.dates[0]}:{self.dates[9]}", min_obs=30),
                          self.snap)
        self.assertTrue(errs and "underpowered" in errs[-1])

    def test_data_check_blocks_empty_mechanism(self):
        h = _h(f"{self.dates[0]}:{self.dates[-1]}")
        h["mechanism"] = "  "
        errs = data_check(h, self.snap)
        self.assertIn("mechanism is empty", errs)

    def test_risk_check_stable_on_planted_signal(self):
        planted = self.root / "planted"
        build_snapshot(planted, seed=11, tickers=12, days=90,
                       plant={"effect": "reversal", "strength": 0.15})
        frame = engine.load_frame(planted)
        matrix = run_factor(F_REV, frame.closes, frame.tickers, frame.dates)
        metrics = engine.evaluate_signal(frame, matrix)
        h = _h(f"{self.dates[0]}:{self.dates[-1]}", min_obs=10)
        result = risk_check(F_REV, planted, h, metrics)
        self.assertTrue(result["neighborhood_stable"])
        self.assertIn("first_half", result["neighborhood_rankic"])

    def test_risk_check_unstable_on_noise_seed_8(self):
        noise = self.root / "noise8"
        build_snapshot(noise, seed=8, tickers=12, days=90)
        frame = engine.load_frame(noise)
        matrix = run_factor(F_REV, frame.closes, frame.tickers, frame.dates)
        metrics = engine.evaluate_signal(frame, matrix)
        h = _h(f"{self.dates[0]}:{self.dates[-1]}", min_obs=10)
        result = risk_check(F_REV, noise, h, metrics)
        # seed 8: full-sample IC positive, halves disagree (pinned by scan)
        self.assertFalse(result["neighborhood_stable"])
        self.assertIn("instability", result["reason"])

    def test_risk_check_survives_factor_that_cannot_rerun(self):
        bad = "def factor(closes, tickers, dates, i):\n    return {t: 1/0 for t in tickers}\n"
        h = _h(f"{self.dates[0]}:{self.dates[-1]}")
        result = risk_check(bad, self.snap, h,
                            {"rankic_mean": 0.1})
        self.assertFalse(result["neighborhood_stable"])
        self.assertTrue(result["reason"])


if __name__ == "__main__":
    unittest.main()
