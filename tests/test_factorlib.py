"""Tests for the factor library (v1.3).

Correctness pins:
* every catalog entry builds on synthetic panels (all fields) without
  exception, non-empty, finite values
* needs-filtering: close-only inputs build only close-needing factors
* cross-sectional rank is an exact percentile rank
* parkinson variance on constant H/L is zero; garman_klass <= parkinson
  on the synthetic construction is not asserted (no such law) — but the
  RS estimator is non-negative by construction on real-ish panels
* window_variants produce the parameterized ids
* determinism: two builds of the same spec are identical
"""
import math
import random
import unittest

from qsa import factorlib as fl


def synth(seed: int = 7, n_tk: int = 40, n_dates: int = 400):
    rng = random.Random(seed)
    dates = [f"2024{1 + i // 28:02d}{1 + i % 28:02d}" for i in range(n_dates)]
    tks = [f"T{i:03d}" for i in range(n_tk)]

    def mk(fn):
        return {tk: {d: fn() for d in dates} for tk in tks}

    inputs = {
        "closes": mk(lambda: rng.random() * 10 + 5),
        "opens": mk(lambda: rng.random() * 10 + 5),
        "volumes": mk(lambda: rng.random() * 1e6 + 1e4),
        "amounts": mk(lambda: rng.random() * 1e8 + 1e6),
        "vwaps": mk(lambda: rng.random() * 10 + 5),
    }
    inputs["highs"] = {
        tk: {d: max(inputs["closes"][tk][d], inputs["opens"][tk][d])
             + rng.random() for d in dates} for tk in tks}
    inputs["lows"] = {
        tk: {d: min(inputs["closes"][tk][d], inputs["opens"][tk][d])
             - rng.random() for d in dates} for tk in tks}
    inputs["dates"] = dates
    return inputs


class TestFactorlib(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = synth()
        cls.full = {'closes', 'opens', 'volumes', 'highs', 'lows',
                    'amounts', 'vwaps'}
        cls.catalog = fl.build_catalog(cls.full)
        cls.signals = {sp["id"]: sp["build"](cls.inputs)
                       for sp in cls.catalog}

    def test_catalog_size_and_families(self):
        ids = {sp["id"] for sp in self.catalog}
        self.assertGreaterEqual(len(ids), 28)
        for expect in ("wq_a2", "wq_a6", "wq_a12", "wq_a23",
                       "parkinson_vol_20d", "garman_klass_20d",
                       "rogers_satchell_20d", "stoch_k_14d",
                       "amihud_dollar_21d", "vwap_premium_5d",
                       "mom_gap_12m", "dist_high_252d", "sharpe_21d",
                       "intraday_21d", "vol_of_vol_20d", "mom_12m"):
            self.assertIn(expect, ids)

    def test_every_build_runs_nonempty_finite(self):
        for sp in self.catalog:
            sig = self.signals[sp["id"]]
            n = sum(len(v) for v in sig.values())
            self.assertGreater(n, 0, sp["id"])
            for row in sig.values():
                for v in row.values():
                    self.assertTrue(math.isfinite(v), (sp["id"], v))

    def test_wq_a24_branch_matches_paper(self):
        # paper: cond = delta(sma(close,100),100)/delay(close,100)
        # cond <= 0.05 -> -(close - ts_min(close,100))   [branch 1]
        # cond >  0.05 -> -delta(close,3)                [branch 2]
        dates = [f"2024{1 + i // 28:02d}{1 + i % 28:02d}"
                 for i in range(220)]
        spec = {sp["id"]: sp for sp in self.catalog}["wq_a24"]

        def run(closes):
            inputs = {"closes": {"X": dict(zip(dates, closes))},
                      "dates": dates}
            return spec["build"](inputs)["X"]

        # W1: flat world, one -2% pop on the last day -> cond ~ 0 <= 0.05
        # branch1 = -(close - min100) = -(9.8 - 9.8) = 0.0
        flat = [10.0] * 219 + [9.8]
        v = run(flat)[dates[-1]]
        self.assertAlmostEqual(v, 0.0, places=9,
                               msg="cond<=0.05 must pick branch 1")

        # W2: 1%/day ramp -> cond = 0.874 > 0.05, last day dips hard:
        # must equal branch2 = -delta(close,3) exactly, and differ from
        # branch1 = -(close - ts_min(close,100))
        ramp = [10.0] * 100 + [10.0 * 1.01 ** (i - 99)
                               for i in range(100, 219)] + [21.0]
        v2 = run(ramp)[dates[-1]]
        branch2 = -(ramp[-1] - ramp[-4])
        branch1 = -(ramp[-1] - min(ramp[-100:]))
        self.assertAlmostEqual(v2, branch2, places=9,
                               msg="cond>0.05 must pick branch 2")
        self.assertNotAlmostEqual(v2, branch1, places=6)

    def test_needs_filtering(self):
        only_close = fl.build_catalog({"closes"})
        for sp in only_close:
            self.assertIn("closes", sp["needs"])
            self.assertNotIn("highs", sp["needs"])
        ids = {sp["id"] for sp in only_close}
        self.assertIn("mom_12m", ids)        # needs closes only
        self.assertNotIn("parkinson_vol_20d", ids)
        self.assertNotIn("wq_a6", ids)
        cv = fl.build_catalog({"closes", "opens", "volumes"})
        self.assertGreater(len(cv), len(only_close))

    def test_determinism(self):
        again = {sp["id"]: sp["build"](self.inputs) for sp in self.catalog}
        self.assertEqual(again, self.signals)

    def test_cs_rank_exact_percentile(self):
        rows = {"a": [1.0, None], "b": [2.0, 5.0], "c": [3.0, 7.0],
                "d": [10.0, 9.0]}
        out = fl.cs_rank(rows)
        self.assertAlmostEqual(out["a"][0], 0.125)
        self.assertAlmostEqual(out["b"][0], 0.375)
        self.assertAlmostEqual(out["c"][0], 0.625)
        self.assertAlmostEqual(out["d"][0], 0.875)
        self.assertIsNone(out["a"][1])

    def test_rolling_min_and_helpers(self):
        xs = {"a": [3.0, 1.0, 2.0, 5.0, None, 4.0]}
        self.assertEqual(fl.rolling_min(xs, 2)["a"],
                         [None, 1.0, 1.0, 2.0, None, None])
        # delta/shift None propagation
        self.assertEqual(fl.delta(xs, 1)["a"][1], -2.0)
        self.assertIsNone(fl.delta(xs, 1)["a"][5])
        self.assertEqual(fl.shift(xs, 2)["a"][2], 3.0)

    def test_parkinson_zero_on_flat_range(self):
        p = fl.build_catalog({"closes", "opens", "highs", "lows"})
        inputs = dict(self.inputs)
        inputs["highs"] = {tk: {d: 10.0 for d in inputs["dates"]}
                           for tk in inputs["closes"]}
        inputs["lows"] = {tk: {d: 10.0 for d in inputs["dates"]}
                          for tk in inputs["closes"]}
        spec = next(s for s in p if s["id"] == "parkinson_vol_20d")
        sig = spec["build"](inputs)
        vals = [v for row in sig.values() for v in row.values()]
        self.assertTrue(all(abs(v) < 1e-12 for v in vals))

    def test_high_low_respected_by_stoch(self):
        sig = self.signals["stoch_k_14d"]
        n_bad = 0
        for tk, row in sig.items():
            for d, v in row.items():
                # flip=True negates %K, so the signal lives in [-1-eps, eps]
                if not (-1.0 - 1e-9 <= v <= 0.0 + 1e-9):
                    n_bad += 1
        self.assertEqual(n_bad, 0)

    def test_window_variants(self):
        vs = fl.window_variants(["mom_gap", "sharpe"], [3, 6])
        ids = [s["id"] for s in vs]
        self.assertEqual(ids, ["mom_gap_3m", "mom_gap_6m",
                               "sharpe_3d", "sharpe_6d"])
        built = [s["build"](self.inputs) for s in vs]
        self.assertTrue(all(sum(len(r) for r in b.values()) > 0
                            for b in built))

    def test_catalog_summary_rows(self):
        rows = fl.catalog_summary()
        self.assertEqual(len(rows), len(self.catalog))
        self.assertTrue(all(r["needs"] for r in rows))
        fams = {r["family"] for r in rows}
        self.assertIn("WorldQuant 101", fams)
        self.assertIn("range/vol", fams)
        self.assertIn("liquidity", fams)


if __name__ == "__main__":
    unittest.main()
