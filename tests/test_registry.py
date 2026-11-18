"""Registry + deflation tests: pre-registration order, unique IDs, family
trial counts, one-shot OOS windows, Bonferroni floors."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa.deflation import bonferroni_tstat_floor, deflated_evaluate
from qsa.registry import Registry, RegistryError

ADM = {"required_metrics": ["rankic_mean", "rankic_tstat"],
       "thresholds": {"rankic_mean": {"op": ">=", "value": 0.02}},
       "min_observations": 30}


def _h(num, **extra):
    h = {"schema": "hypothesis", "hyp_id": f"H-{num:04d}",
         "mechanism": "m", "falsifiable_condition": "f", "admission": ADM,
         "window": "20240101:20240401", "family": "test", "ttl_days": 90,
         "status": "registered", "created_at": "2024-04-01"}
    h.update(extra)
    return h


def _e(num, hyp="H-0001", verdict="fail"):
    return {"schema": "experiment_result", "exp_id": f"E-{num:04d}",
            "hyp_id": hyp, "window": "20240101:20240401",
            "snapshot_hash": "0" * 64, "engine": "x", "metrics": {},
            "verdict": verdict, "settled_at": "2024-04-01"}


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = Registry.open(Path(self.tmp.name) / "registry.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_hypothesis_before_experiment(self):
        with self.assertRaisesRegex(RegistryError, "not registered"):
            self.reg.settle_experiment(_e(1), _h(1))

    def test_unique_ids(self):
        self.reg.register_hypothesis(_h(1))
        self.reg.settle_experiment(_e(1), _h(1))
        with self.assertRaisesRegex(RegistryError, "already registered"):
            self.reg.register_hypothesis(_h(1))
        with self.assertRaisesRegex(RegistryError, "already settled"):
            self.reg.settle_experiment(_e(1), _h(1))

    def test_family_trial_counting(self):
        self.reg.register_hypothesis(_h(1))
        self.assertEqual(self.reg.settle_experiment(_e(1), _h(1)), 1)
        self.reg.register_hypothesis(_h(2))
        self.assertEqual(self.reg.settle_experiment(_e(2), _h(2)), 2)
        self.assertEqual(self.reg.n_trials("test"), 2)
        self.assertEqual(self.reg.n_trials("other"), 0)

    def test_oos_one_shot(self):
        self.reg.register_hypothesis(_h(1, oos_window="20240501:20240531"))
        e = _e(1)
        e["oos"] = {"window": "20240501:20240531", "verdict": "fail"}
        self.reg.settle_experiment(e, _h(1))
        # same window again, even for a new hypothesis:
        with self.assertRaisesRegex(RegistryError, "one-shot"):
            self.reg.register_hypothesis(_h(2, oos_window="20240510:20240610"))
        # disjoint window is fine
        self.reg.register_hypothesis(_h(3, oos_window="20240601:20240630"))

    def test_reload_is_deterministic(self):
        self.reg.register_hypothesis(_h(1))
        self.reg.settle_experiment(_e(1), _h(1))
        path = Path(self.tmp.name) / "registry.jsonl"
        again = Registry(path)
        self.assertEqual(again.n_trials("test"), 1)
        self.assertTrue(again.has_hypothesis("H-0001"))


class TestDeflation(unittest.TestCase):
    def test_floor_rises_with_trials(self):
        self.assertEqual(bonferroni_tstat_floor(1), 0.0)
        self.assertGreater(bonferroni_tstat_floor(2),
                           bonferroni_tstat_floor(1))
        self.assertGreater(bonferroni_tstat_floor(20),
                           bonferroni_tstat_floor(2))

    def _metrics(self, mean=0.03, tstat=1.0, n=79):
        return {"rankic_mean": mean, "rankic_tstat": tstat, "n_dates": n}

    def test_single_trial_untouched(self):
        verdict, reasons = deflated_evaluate(ADM, self._metrics(), 1)
        self.assertEqual(verdict, "pass")
        self.assertFalse(any("deflation" in r for r in reasons))

    def test_mining_history_raises_the_bar(self):
        # same numbers that passed at N=1 fail at N=10 (t=1.0 < floor≈3.3)
        verdict, reasons = deflated_evaluate(ADM, self._metrics(), 10)
        self.assertEqual(verdict, "fail")
        self.assertTrue(any("deflation" in r for r in reasons))

    def test_strong_signal_survives_deflation(self):
        verdict, reasons = deflated_evaluate(ADM, self._metrics(tstat=5.0), 10)
        self.assertEqual(verdict, "pass")

    def test_direction_aware(self):
        adm_neg = {"required_metrics": ["rankic_mean", "rankic_tstat"],
                   "thresholds": {"rankic_mean": {"op": "<=", "value": -0.02}},
                   "min_observations": 30}
        m = {"rankic_mean": -0.03, "rankic_tstat": -5.0, "n_dates": 79}
        verdict, _ = deflated_evaluate(adm_neg, m, 10)
        self.assertEqual(verdict, "pass")


if __name__ == "__main__":
    unittest.main()
