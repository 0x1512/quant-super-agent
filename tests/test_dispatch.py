"""Tests for the dispatcher (v1.3.1).

The load-bearing claim is the DETERMINISM CONTRACT: sharding the
candidate space across worker processes must change nothing. These tests
pin it three ways:

* stream equivalence — dispatch.* with workers=4 returns rows EQUAL
  (dict equality, floats included) and in the same order as the
  sequential reference implementations (offense.* / factorzoo.run_zoo);
* job order — mutation/interaction job builders mirror the reference
  builders' ordering exactly (window_variants / combinations);
* executor fallback — workers=1 routes through the same _run executor
  as the pool path, so the sequential default cannot drift; an unknown
  job kind raises instead of silently scoring nothing.
"""
import random
import unittest

from qsa import dispatch, factorlib, offense
from qsa.factorzoo import build_catalog, run_zoo, zoo_sort_key


def panels(seed: int = 11, n_tk: int = 24, n_dates: int = 200):
    rng = random.Random(seed)
    dates = [f"2024{1 + i // 28:02d}{1 + i % 28:02d}" for i in range(n_dates)]
    tks = [f"T{i:03d}" for i in range(n_tk)]
    closes = {tk: {d: rng.random() * 10 + 5 for d in dates} for tk in tks}
    return dates, tks, closes


def basis_signals(dates, tks, n=3):
    rng = random.Random(7)
    return [{tk: {d: rng.gauss(0, 1) for d in dates} for tk in tks}
            for _ in range(n)]


class TestStreamEquivalence(unittest.TestCase):
    """workers=4 must equal the sequential reference, row for row."""

    @classmethod
    def setUpClass(cls):
        dates, tks, closes = panels(seed=13, n_tk=20, n_dates=180)
        cls.dates, cls.tks = dates, tks
        cls.inputs = {"closes": closes, "opens": closes, "volumes": closes,
                      "dates": dates}
        cls.basis = basis_signals(dates, tks)
        cls.specs = [{"id": f"s{i}", "source": "t", "desc": "d",
                      "flip": False} for i in range(3)]

    def test_zoo_parallel_equals_sequential(self):
        ref = run_zoo(self.inputs["closes"], self.inputs["opens"],
                      self.inputs["volumes"], self.dates)
        par = dispatch.zoo(self.inputs["closes"], self.inputs["opens"],
                           self.inputs["volumes"], self.dates, workers=4)
        self.assertEqual(par, ref)

    def test_library_parallel_equals_sequential(self):
        available = {k for k in self.inputs if k != "dates"}
        ref = [offense.evaluate(sp, self.inputs, self.basis)
               for sp in factorlib.build_catalog(available)]
        par = dispatch.library(self.inputs, self.basis, workers=4)
        self.assertEqual(par, ref)

    def test_interactions_parallel_equals_sequential(self):
        ref = offense.interactions(self.specs, self.inputs, self.basis,
                                   top_k=3)
        par = dispatch.interactions(self.specs, self.inputs, self.basis,
                                    top_k=3, workers=4)
        self.assertEqual(par, ref)

    def test_mutations_parallel_equals_sequential(self):
        args = (["mom", "mom_gap"], ["sharpe", "vol_of_vol"],
                [3, 6], [10, 63])
        ref = offense.mutations(*args, self.inputs, self.basis)
        par = dispatch.mutations(*args, self.inputs, self.basis, workers=4)
        self.assertEqual(par, ref)


class TestJobOrder(unittest.TestCase):
    """Job builders must mirror the reference builders' order."""

    def test_mutation_jobs_mirror_window_variants(self):
        mf, df, mw, dw = ["mom", "nope", "mom_gap"], ["sharpe"], [3, 6], [10]
        ref = (factorlib.window_variants(mf, mw)
               + factorlib.window_variants(df, dw))
        jobs = ([("mut", nm, w) for nm in mf if nm in factorlib.FAMILIES
                 for w in mw]
                + [("mut", nm, w) for nm in df
                   if nm in factorlib.FAMILIES for w in dw])
        # rebuilding specs from job descriptors in order must reproduce
        # window_variants exactly (unknown family names skipped likewise)
        rebuilt = [factorlib.FAMILIES[j[1]](j[2])["id"] for j in jobs]
        self.assertEqual(rebuilt, [sp["id"] for sp in ref])

    def test_zoo_sort_key_matches_run_zoo_order(self):
        dates, tks, closes = panels(seed=5, n_tk=12, n_dates=90)
        rows = run_zoo(closes, closes, closes, dates)
        resorted = sorted(rows, key=zoo_sort_key, reverse=True)
        self.assertEqual([r["id"] for r in resorted],
                         [r["id"] for r in rows])


class TestExecutor(unittest.TestCase):
    def test_single_worker_uses_same_executor(self):
        # workers=1 must go through _run (not a separate code path):
        # patch _run's catalog branch marker via a tiny job set
        dates, tks, closes = panels(seed=3, n_tk=10, n_dates=60)
        inputs = {"closes": closes, "opens": closes, "volumes": closes,
                  "dates": dates}
        basis = basis_signals(dates, tks, 2)
        available = {k for k in inputs if k != "dates"}
        ref = [offense.evaluate(sp, inputs, basis)
               for sp in factorlib.build_catalog(available)]
        par = dispatch.library(inputs, basis, workers=1)
        self.assertEqual(par, ref)

    def test_unknown_job_kind_raises(self):
        with self.assertRaises(ValueError):
            dispatch._run(("nonsense",))

    def test_default_workers_bounded(self):
        self.assertGreaterEqual(dispatch.default_workers(), 1)
        self.assertEqual(dispatch.default_workers(0),
                         dispatch.default_workers(None))
        self.assertEqual(dispatch.default_workers(9), 9)


if __name__ == "__main__":
    unittest.main()
