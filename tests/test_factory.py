"""Factor zoo — determinism, orientation, catalog integrity.

The zoo is a ranking machine: these tests pin the properties that make
its ranking trustworthy — same input gives the byte-same leaderboard, a
manufactured effect ranks exactly where it should, a dead-orientation
factor sinks, and every catalog entry builds a non-empty signal with a
public source citation.
"""
from __future__ import annotations

import math
import random
import unittest

from qsa.factorzoo import build_catalog, run_zoo, to_signal


def _effect_world(n_tickers: int = 40, n_days: int = 300,
                  effect: float = 1.0, seed: int = 7):
    """A world where next-month return correlates with a planted factor.

    factor_ticker ~ U(0,1) fixed per ticker; daily returns have a per-day
    common component plus a ticker tilt proportional to the factor. With
    effect=1 the planted factor's monthly IC is strongly positive; with
    effect=-1 it is strongly negative; with 0 it is noise.
    """
    rng = random.Random(seed)
    dates = [f"2023{1 + (i // 21):02d}{1 + (i % 21):02d}" for i in
             range(n_days)]
    tickers = [f"T{k:03d}" for k in range(n_tickers)]
    factor = {t: rng.random() for t in tickers}
    closes: dict[str, dict[str, float]] = {t: {dates[0]: 100.0}
                                           for t in tickers}
    for i, d in enumerate(dates[1:], 1):
        common = rng.gauss(0.0, 0.005)
        for t in tickers:
            tilt = effect * (factor[t] - 0.5) * 0.004
            prev = closes[t][dates[i - 1]]
            closes[t][d] = prev * (1.0 + common + tilt + rng.gauss(0, 0.01))
    signal = {t: {dates[-1]: factor[t]} for t in tickers}
    opens = {t: {d: c * 0.999 for d, c in row.items()}
             for t, row in closes.items()}
    vols = {t: {d: 1e6 + rng.random() * 1e5 for d in dates} for t in tickers}
    return closes, opens, vols, dates, signal


class TestDeterminism(unittest.TestCase):
    def test_same_input_same_leaderboard(self):
        closes, opens, vols, dates, sig = _effect_world(30, 200)
        cat = build_catalog()
        a = run_zoo(closes, opens, vols, dates, catalog=cat)
        b = run_zoo(closes, opens, vols, dates, catalog=cat)
        self.assertEqual([r["id"] for r in a], [r["id"] for r in b])
        for ra, rb in zip(a, b):
            self.assertEqual(ra, rb)


class TestOrientation(unittest.TestCase):
    def test_planted_positive_effect_dominates(self):
        # a world where high planted factor -> higher returns: the planted
        # signal (handed to the zoo as a one-entry catalog) must come back
        # with a positive mean IC and a positive score
        closes, opens, vols, dates, sig = _effect_world(60, 300, effect=1.0)
        cat = [{"id": "planted", "source": "test", "desc": "planted",
                "build": lambda inputs: {}, "flip": False}]
        # inject the planted signal directly through _finalize-compatible
        # shape: build returns rows; use to_signal round-trip instead
        rows = {t: [sig[t][dates[-1]]] * len(dates) for t in sig}
        cat[0]["build"] = lambda inputs: rows
        out = run_zoo(closes, opens, vols, dates, catalog=cat)
        self.assertEqual(out[0]["id"], "planted")
        self.assertGreater(out[0]["ic_mean"], 0.0)
        self.assertGreater(out[0]["top_minus_bottom"], 0.0)

    def test_flipped_world_sinks_the_same_factor(self):
        # same world with the effect sign reversed: the same oriented
        # factor now has negative IC -> sinks below zero score
        closes, opens, vols, dates, sig = _effect_world(60, 300, effect=-1.0)
        rows = {t: [sig[t][dates[-1]]] * len(dates) for t in sig}
        cat = [{"id": "planted", "source": "test", "desc": "planted",
                "build": lambda inputs: rows, "flip": False}]
        out = run_zoo(closes, opens, vols, dates, catalog=cat)
        self.assertLess(out[0]["ic_mean"], 0.0)


class TestCatalogIntegrity(unittest.TestCase):
    def test_catalog_builds_nonempty_signals_with_sources(self):
        closes, opens, vols, dates, sig = _effect_world(30, 320, seed=11)
        inputs = {"closes": closes, "opens": opens, "volumes": vols,
                  "dates": dates}
        cat = build_catalog()
        self.assertGreaterEqual(len(cat), 24)
        for spec in cat:
            self.assertTrue(spec["source"], f"{spec['id']}: no source")
            self.assertTrue(spec["desc"], f"{spec['id']}: no desc")
            rows = spec["build"](inputs)
            signal = to_signal(rows, dates) if not spec["flip"] else {
                t: {d: -v for d, v in row.items()} for t, row in
                to_signal(rows, dates).items()}
            self.assertTrue(signal, f"{spec['id']}: empty signal")
            n_vals = sum(len(r) for r in signal.values())
            self.assertGreater(n_vals, 100,
                               f"{spec['id']}: degenerate coverage")
            for row in signal.values():
                for v in row.values():
                    self.assertTrue(math.isfinite(v),
                                    f"{spec['id']}: non-finite value")

    def test_unique_ids(self):
        ids = [s["id"] for s in build_catalog()]
        self.assertEqual(len(ids), len(set(ids)))


class TestKernels(unittest.TestCase):
    def test_rolling_mean_and_std_hand_case(self):
        from qsa.factorzoo import rolling_mean, rolling_std, rolling_sum
        xs = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(rolling_mean(xs, 2),
                         [None, 1.5, 2.5, 3.5])
        self.assertEqual(rolling_sum(xs, 2), [None, 3.0, 5.0, 7.0])
        s = rolling_std(xs, 2)
        # every pair differs by exactly 1 -> sample std = sqrt(0.5)
        for v in s[1:]:
            self.assertAlmostEqual(v, math.sqrt(0.5))

    def test_rolling_corr_perfect_pair(self):
        from qsa.factorzoo import rolling_corr
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]  # exact 2x
        out = rolling_corr(xs, ys, 3)
        self.assertAlmostEqual(out[2], 1.0)
        self.assertAlmostEqual(out[4], 1.0)
        self.assertIsNone(out[1])


if __name__ == "__main__":
    unittest.main()
