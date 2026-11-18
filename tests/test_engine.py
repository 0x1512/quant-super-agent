"""Engine tests: determinism, lookahead refusal, window bounds."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa import engine, snapshot


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.snap = snapshot.build_snapshot(Path(cls.tmp.name) / "snapshot",
                                           seed=42, tickers=12, days=90)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_deterministic_metrics(self):
        a = engine.run(str(self.snap.dir), k=10)
        b = engine.run(str(self.snap.dir), k=10)
        self.assertEqual(a["metrics"], b["metrics"])
        self.assertEqual(a["attribution"], b["attribution"])

    def test_metric_shape(self):
        m = engine.run(str(self.snap.dir), k=10)["metrics"]
        for key in ("rankic_mean", "rankic_tstat", "quintile_spread",
                    "monotonicity_proxy", "n_dates"):
            self.assertIn(key, m)
        self.assertIsInstance(m["n_dates"], int)
        self.assertGreater(m["n_dates"], 30)

    def test_window_beyond_snapshot_refused(self):
        as_of = self.snap.manifest["as_of"]
        beyond = str(int(as_of) + 1)
        window = f"{self.snap.manifest['start']}:{beyond}"
        with self.assertRaisesRegex(ValueError, "lookahead refused"):
            engine.run(str(self.snap.dir), k=10, window=window)

    def test_window_too_short_refused(self):
        start = self.snap.manifest["start"]
        with self.assertRaisesRegex(ValueError, "dates"):
            engine.run(str(self.snap.dir), k=10, window=f"{start}:{start}")

    def test_neighborhood_attribution_present(self):
        attr = engine.run(str(self.snap.dir), k=10)["attribution"]
        self.assertIn("neighborhood_stable", attr)
        self.assertIn("neighborhood_rankic", attr)
        self.assertEqual(len(attr["neighborhood_rankic"]), 4)  # k±1, k±2


class TestBudgetMetrics(unittest.TestCase):
    """v0.7: coverage / turnover / cost / net / capacity readouts."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.snap = snapshot.build_snapshot(cls.root / "snapshot",
                                           seed=42, tickers=12, days=90)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_new_metrics_present_and_deterministic(self):
        a = engine.run(str(self.snap.dir), k=10)["metrics"]
        b = engine.run(str(self.snap.dir), k=10)["metrics"]
        self.assertEqual(a, b)
        for key in ("coverage", "turnover", "cost_bps_used",
                    "net_quintile_spread", "volume_dollar_median"):
            self.assertIn(key, a)
        self.assertEqual(a["coverage"], 1.0)  # momentum scores everyone
        self.assertGreaterEqual(a["turnover"], 0.0)
        self.assertLessEqual(a["turnover"], 2.0)
        self.assertGreater(a["volume_dollar_median"], 0.0)

    def test_net_is_gross_minus_cost_drag(self):
        m = engine.run(str(self.snap.dir), k=10)["metrics"]
        drag = 2.0 * m["turnover"] * m["cost_bps_used"] / 1e4
        # components are rounded to 6dp in the metric dict; the identity
        # holds to that precision, not bit-exactly
        self.assertAlmostEqual(
            m["net_quintile_spread"], m["quintile_spread"] - drag,
            delta=2e-6)
        self.assertLess(m["net_quintile_spread"], m["quintile_spread"])

    def test_manifest_cost_model_pinned_and_honored(self):
        pricey = snapshot.build_snapshot(
            self.root / "pricey", seed=42, tickers=12, days=90,
            costs={"per_side_bps": 25.0})
        self.assertEqual(pricey.manifest["costs"], {"per_side_bps": 25.0})
        m = engine.run(str(pricey.dir), k=10)["metrics"]
        self.assertEqual(m["cost_bps_used"], 25.0)
        base = engine.run(str(self.snap.dir), k=10)["metrics"]
        self.assertEqual(m["quintile_spread"], base["quintile_spread"])
        self.assertEqual(m["turnover"], base["turnover"])  # costs don't
        # change the signal, only the net readout
        self.assertLess(m["net_quintile_spread"], base["net_quintile_spread"])
        # default worlds stay byte-frozen: no costs block, default 10 bps
        self.assertNotIn("costs", self.snap.manifest)
        self.assertEqual(base["cost_bps_used"], 10.0)

    def test_negative_cost_model_refused(self):
        with self.assertRaises(ValueError):
            snapshot.build_snapshot(self.root / "neg", seed=1, tickers=5,
                                    days=30, costs={"per_side_bps": -1.0})

    def test_partial_coverage_measured(self):
        # a signal for only 5 of 12 tickers: coverage ~0.4167, not 1.0 —
        # the cherry-universe readout (signal must vary across tickers and
        # days, else rank IC is undefined and evaluation refuses)
        frame = engine.load_frame(self.snap.dir)
        five = frame.tickers[:5]
        sig = {tk: {d: float((five.index(tk) + di) % 5 + 1)
                    for di, d in enumerate(frame.dates)}
               for tk in five}
        m = engine.evaluate_signal(frame, sig)
        self.assertAlmostEqual(m["coverage"], 5 / 12, places=6)


if __name__ == "__main__":
    unittest.main()
