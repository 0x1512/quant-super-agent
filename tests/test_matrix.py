"""Matrix fast plane, halving and parallel tests.

The equivalence classes run only when numpy is importable (the CI
matrix is deliberately dependency-free and exercises the stdlib
fallback instead); the semantics classes run everywhere.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa import factorzoo
from qsa.matrix import HAVE_NUMPY, MonthPlane, evaluate_factor_fast
from qsa.halving import successive_halving
from qsa.parallel import evaluate_specs_parallel
from qsa.replication import (group_monthly_returns, monthly_ic_series,
                             _ranks)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "data"


def _fixture_inputs():
    import sys
    sys.path.insert(0, str(ROOT))
    from qsa import snapshot
    from qsa.ingest import ingest_csv
    tmp = tempfile.TemporaryDirectory()
    snap = Path(tmp.name) / "snap"
    ingest_csv(FIXTURE / "ashare_top300_main.csv", snap, volume_col="volume",
               open_col="open", snapshot_id="matrix-test",
               meta_dir=FIXTURE / "replication_meta")
    closes = snapshot.load_closes(snap)
    opens = snapshot.load_opens(snap)
    volumes = snapshot.load_volumes(snap)
    inputs = {"closes": closes, "opens": opens, "volumes": volumes,
              "dates": sorted({d for r in closes.values() for d in r})}
    return tmp, inputs


def _synthetic_inputs(months: int = 8, tickers: int = 24):
    """A deterministic toy panel: momentum-ish signal + noise closes."""
    dates = []
    y, m = 2021, 1
    for _ in range(months * 4):
        mm = f"{m:02d}"
        dates.append(f"{y}{mm}28")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    closes: dict[str, dict[str, float]] = {}
    signal: dict[str, dict[str, float]] = {}
    for j in range(tickers):
        tk = f"T{j:02d}"
        c, row_c, row_s = 100.0 + j, {}, {}
        for i, d in enumerate(dates):
            drift = 1.0 + (0.002 if j >= tickers // 2 else -0.001)
            c *= drift * (1.0 + ((i * 7 + j * 13) % 5 - 2) * 0.001)
            row_c[d] = round(c, 6)
            row_s[d] = float(j)
        closes[tk] = row_c
        signal[tk] = row_s
    return {"closes": closes, "opens": closes, "volumes": closes,
            "dates": dates}, signal


class TestSpearmanSemantics(unittest.TestCase):
    def test_rank_tie_averaging_matches_stdlib(self):
        import numpy as np
        from qsa.matrix import _avg_ranks
        for xs in ([3.0, 1.0, 2.0], [1.0, 1.0, 2.0, 2.0, 5.0],
                   [0.5, 0.5, 0.5], [7.0], [-1.0, 0.0, 1.0, 1.0]):
            got = _avg_ranks(np.array(xs))
            self.assertEqual([float(v) for v in got], _ranks(xs), xs)

    def test_constant_cross_section_is_zero(self):
        import numpy as np
        from qsa.matrix import _spearman_ab
        x = np.array([1.0, 1.0, 1.0, 1.0])
        y = np.array([0.1, 0.2, 0.3, 0.4])
        self.assertEqual(_spearman_ab(x, y), 0.0)

    def test_ab_mismatch_refuses(self):
        import numpy as np
        from qsa import matrix
        x = np.array([1.0, 2.0, 3.0, 4.0])
        y = np.array([4.0, 3.0, 2.0, 1.0])
        real = matrix._pearson_z
        matrix._pearson_z = lambda dx, dy, sxx, syy: real(dx, dy, sxx, syy) + 1e-9
        try:
            with self.assertRaises(AssertionError):
                matrix._spearman_ab(x, y)
        finally:
            matrix._pearson_z = real


class TestPlaneOnSynthetic(unittest.TestCase):
    def setUp(self):
        if not HAVE_NUMPY:
            self.skipTest("numpy backend not installed")
        self.inputs, self.signal = _synthetic_inputs()

    def test_plane_matches_stdlib_monthly_plane(self):
        ic_old = monthly_ic_series(self.inputs["closes"],
                                   self.inputs["dates"], self.signal)
        g_old = group_monthly_returns(self.inputs["closes"],
                                      self.inputs["dates"], self.signal)
        plane = MonthPlane.build(self.inputs["closes"],
                                 self.inputs["dates"], self.signal)
        self.assertEqual(plane.ic_series(), ic_old)
        self.assertEqual(plane.group_annualized(5), g_old)

    def test_min_names_drops_thin_months(self):
        thin = {"closes": self.inputs["closes"], "dates": self.inputs["dates"],
                "opens": {}, "volumes": {}}
        sig = {tk: row for tk, row in list(self.signal.items())[:5]}
        plane = MonthPlane.build(thin["closes"], thin["dates"], sig,
                                 min_names=10)
        self.assertEqual(plane.ic_series(), [])   # 5 names < 10 everywhere


@unittest.skipUnless(HAVE_NUMPY, "numpy backend not installed")
class TestFixtureEquivalence(unittest.TestCase):
    """The 24-factor real-data equivalence: matrix == stdlib everywhere."""

    @classmethod
    def setUpClass(cls):
        cls._tmp, cls.inputs = _fixture_inputs()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_all_catalog_factors_field_identical(self):
        for spec in factorzoo.build_catalog():
            row_old = factorzoo.evaluate_factor(spec, self.inputs)
            row_new = evaluate_factor_fast(spec, self.inputs)
            self.assertEqual(row_old, row_new, spec["id"])


class TestRollingFastPath(unittest.TestCase):
    """numpy fast path vs stdlib kernels: exact on integers, 1e-9 on floats."""

    KERNELS = ("rolling_mean", "rolling_std", "rolling_sum", "rolling_max")

    def _stdlib(self, name, *args):
        from qsa import factorzoo
        saved = factorzoo._HAVE_NP
        factorzoo._HAVE_NP = False
        try:
            return getattr(factorzoo, name)(*args)
        finally:
            factorzoo._HAVE_NP = saved

    def _both(self, name, xs, win, ys=None):
        from qsa import factorzoo
        call = getattr(factorzoo, name)
        fast = call(xs, win) if ys is None else call(xs, ys, win)
        slow = (self._stdlib(name, xs, win) if ys is None
                else self._stdlib(name, xs, ys, win))
        return fast, slow

    def test_integer_inputs_are_exact(self):
        xs = [1, 0, 0, 2, 1, 1, 1, 0, 3, 3, 3, 2, None, 1, 0, None, 2, 2, 1, 1]
        for name in self.KERNELS:
            for win in (2, 3, 5):    # stdlib rolling_std requires win >= 2
                fast, slow = self._both(name, xs, win)
                self.assertEqual(fast, slow, (name, win))

    def test_float_inputs_agree_to_1e_9(self):
        import math as _m
        xs = [round(_m.sin(i) * 3 + 2, 6) for i in range(24)]
        xs[7] = None
        xs[15] = None
        for name in self.KERNELS:
            for win in (2, 5, 8):
                fast, slow = self._both(name, xs, win)
                for a, b in zip(fast, slow):
                    if a is None or b is None:
                        self.assertIs(a, b, (name, win))
                    else:
                        self.assertLess(abs(a - b), 1e-9, (name, win))

    def test_constant_window_std_is_zero(self):
        xs = [2.0] * 12
        fast, slow = self._both("rolling_std", xs, 4)
        self.assertEqual(fast, slow)
        self.assertEqual(fast[-1], 0.0)

    def test_mean_carries_over_gaps(self):
        xs = [1.0, 2.0, None, 4.0, None, None, 7.0, 8.0]
        fast, slow = self._both("rolling_mean", xs, 2)
        self.assertEqual(fast, slow)
        self.assertIsNotNone(fast[5])      # carried, not None

    def test_corr_alignment(self):
        xs = [1.0, 2.0, 3.0, None, 5.0, 6.0, 7.0, 8.0]
        ys = [2.0, 4.0, 6.0, 8.0, None, 12.0, 14.0, 16.0]
        fast, slow = self._both("rolling_corr", xs, 3, ys=ys)
        self.assertEqual(len(fast), len(slow))
        for a, b in zip(fast, slow):
            if a is None or b is None:
                self.assertIs(a, b)
            else:
                self.assertLess(abs(a - b), 1e-9)

    def test_short_input_degrades(self):
        for name in self.KERNELS:
            fast, slow = self._both(name, [1.0, None], 5)
            self.assertEqual(fast, slow)
            self.assertEqual(fast, [None, None])


class TestHalving(unittest.TestCase):
    def setUp(self):
        if not HAVE_NUMPY:
            self.skipTest("numpy backend not installed")
        self.inputs, _ = _synthetic_inputs(months=12)
        short_window = {"rev_1w", "rev_1m", "vol_20d", "max_ret_20d",
                        "hl_range_20d", "run_length", "volume_trend",
                        "vol_ratio_5_20"}
        self.catalog = [dict(s) for s in factorzoo.build_catalog()
                        if s["id"] in short_window]

    def test_survivors_reproduce_full_sample_rows(self):
        pool, log = successive_halving(self.catalog, self.inputs,
                                       fractions=(0.5, 0.75), keep=0.5,
                                       floor=-1.0)
        self.assertTrue(pool)
        for spec in pool:  # determinism: halving never changes evaluation
            self.assertEqual(evaluate_factor_fast(spec, self.inputs),
                             factorzoo.evaluate_factor(spec, self.inputs))

    def test_floor_and_audit_log(self):
        pool, log = successive_halving(self.catalog, self.inputs,
                                       fractions=(0.5,), keep=0.5,
                                       floor=0.03)
        self.assertEqual(len(log), 1)
        entry = log[0]
        for key in ("level", "fraction", "n_dates", "evaluated",
                    "above_floor", "kept", "cut_oos_ic", "dropped"):
            self.assertIn(key, entry)
        self.assertLessEqual(entry["kept"], entry["evaluated"])

    def test_single_candidate_short_circuits(self):
        pool, log = successive_halving(self.catalog[:1], self.inputs,
                                       fractions=(0.5,))
        self.assertEqual(len(pool), 1)
        self.assertEqual(log, [])

    def test_thin_prefix_is_skipped(self):
        pool, log = successive_halving(self.catalog,
                                       self.inputs, fractions=(0.01,))
        self.assertEqual(len(pool), len(self.catalog))
        self.assertEqual(log, [])


class TestParallel(unittest.TestCase):
    def setUp(self):
        if not HAVE_NUMPY:
            self.skipTest("numpy backend not installed")
        import platform
        if platform.system() != "Linux":
            self.skipTest("fork start method unavailable")
        self.inputs, _ = _synthetic_inputs(months=9)
        self.catalog = [dict(s) for s in factorzoo.build_catalog()[:6]]

    def test_pool_matches_serial(self):
        got = evaluate_specs_parallel(self.catalog, self.inputs, workers=2)
        for spec in self.catalog:
            want = evaluate_factor_fast(spec, self.inputs)
            self.assertEqual(got[spec["id"]], want, spec["id"])

    def test_workers_one_is_serial(self):
        got = evaluate_specs_parallel(self.catalog, self.inputs, workers=1)
        self.assertEqual(len(got), len(self.catalog))


class TestFallbackPath(unittest.TestCase):
    """Without numpy the fast path must BE the stdlib path."""

    def test_disabled_numpy_falls_back(self):
        from qsa import matrix
        inputs, _ = _synthetic_inputs(months=6)
        spec = factorzoo.build_catalog()[0]
        saved = matrix.HAVE_NUMPY
        matrix.HAVE_NUMPY = False
        try:
            row = evaluate_factor_fast(spec, inputs)
        finally:
            matrix.HAVE_NUMPY = saved
        self.assertEqual(row, factorzoo.evaluate_factor(spec, inputs))


if __name__ == "__main__":
    unittest.main()
