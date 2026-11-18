"""Tests for the offense module (v1.3).

The residual objective is the load-bearing wall — these tests pin it to
manual OLS, orthogonality, and degradation behavior:
* _solve: known 2x2, singular -> None
* residualize matches a hand-computed two-variable OLS to 1e-9
* residuals are orthogonal to the basis columns (X'r = 0 per date)
* small-name dates are dropped instead of regressed
* empty basis is a passthrough
* interactions: exactly C(k,2)*3 candidates, rank-blended signals are
  scale-free (multiplying a basis signal by 1000 changes nothing after
  cs_rank)
* the planted-foresight signal scores IC ~ +1 through the whole fast
  lane (end-to-end correctness of eval_signal)
"""
import math
import random
import unittest

from qsa import offense as off
from qsa.backtest import month_key


def panels(seed: int = 11, n_tk: int = 30, n_dates: int = 300):
    rng = random.Random(seed)
    dates = [f"2024{1 + i // 28:02d}{1 + i % 28:02d}" for i in range(n_dates)]
    tks = [f"T{i:03d}" for i in range(n_tk)]
    closes = {tk: {d: rng.random() * 10 + 5 for d in dates} for tk in tks}
    return dates, tks, closes


def sig_of(fn, tks, dates):
    return {tk: {d: fn(tk, d) for d in dates} for tk in tks}


class TestSolve(unittest.TestCase):
    def test_known_2x2(self):
        beta = off._solve([[2.0, 1.0], [1.0, 3.0]], [3.0, 5.0])
        self.assertAlmostEqual(beta[0], 0.8, places=9)
        self.assertAlmostEqual(beta[1], 1.4, places=9)

    def test_singular_returns_none(self):
        self.assertIsNone(off._solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0]))


class TestResidualize(unittest.TestCase):
    def setUp(self):
        rng = random.Random(3)
        self.tks = [f"T{i}" for i in range(20)]
        self.dates = ["20240101", "20240102"]
        mk = lambda: {tk: {d: rng.gauss(0, 1) for d in self.dates}
                      for tk in self.tks}
        self.cand, self.b1, self.b2 = mk(), mk(), mk()

    def test_matches_manual_ols(self):
        res = off.residualize(self.cand, [self.b1, self.b2])
        for d in self.dates:
            ys = [self.cand[tk][d] for tk in self.tks]
            x1 = [self.b1[tk][d] for tk in self.tks]
            x2 = [self.b2[tk][d] for tk in self.tks]
            n = len(ys)
            mx1, mx2, my = sum(x1) / n, sum(x2) / n, sum(ys) / n
            s11 = sum((a - mx1) ** 2 for a in x1)
            s22 = sum((b - mx2) ** 2 for b in x2)
            s12 = sum((a - mx1) * (b - mx2) for a, b in zip(x1, x2))
            s1y = sum((a - mx1) * (y - my) for a, y in zip(x1, ys))
            s2y = sum((b - mx2) * (y - my) for b, y in zip(x2, ys))
            det = s11 * s22 - s12 * s12
            b1 = (s22 * s1y - s12 * s2y) / det
            b2 = (s11 * s2y - s12 * s1y) / det
            r0 = ys[0] - (my + b1 * (x1[0] - mx1) + b2 * (x2[0] - mx2))
            self.assertAlmostEqual(res["T0"][d], r0, places=9)

    def test_residuals_orthogonal_to_basis(self):
        res = off.residualize(self.cand, [self.b1, self.b2])
        for d in self.dates:
            names = sorted(set(res) & set(self.b1) & set(self.b2))
            r = [res[tk][d] for tk in names]
            for b in (self.b1, self.b2):
                col = [b[tk][d] for tk in names]
                ip = sum(a * c for a, c in zip(r, col))
                self.assertAlmostEqual(ip, 0.0, places=8)
            self.assertAlmostEqual(sum(r), 0.0, places=8)  # intercept

    def test_passthrough_empty_basis(self):
        self.assertEqual(off.residualize(self.cand, []), self.cand)

    def test_thin_dates_dropped(self):
        # a date present on only 5 names must vanish, not be regressed;
        # basis needs the date too or nothing can ever be kept
        rng = random.Random(31)
        thin_c = {tk: {"20240103": rng.gauss(0, 1)} for tk in self.tks[:5]}
        thin_b1 = {tk: {"20240103": rng.gauss(0, 1)} for tk in self.tks[:5]}
        thin_b2 = {tk: {"20240103": rng.gauss(0, 1)} for tk in self.tks[:5]}
        cand = {tk: dict(self.cand[tk]) for tk in self.tks}
        b1 = {tk: dict(self.b1[tk]) for tk in self.tks}
        b2 = {tk: dict(self.b2[tk]) for tk in self.tks}
        for tk in self.tks[:5]:
            cand[tk]["20240103"] = thin_c[tk]["20240103"]
            b1[tk]["20240103"] = thin_b1[tk]["20240103"]
            b2[tk]["20240103"] = thin_b2[tk]["20240103"]
        res = off.residualize(cand, [b1, b2])
        self.assertFalse(any("20240103" in row for row in res.values()))
        res2 = off.residualize(cand, [b1, b2], min_names=5)
        self.assertTrue(any("20240103" in row for row in res2.values()))


class TestFastLane(unittest.TestCase):
    def test_planted_foresight_scores_one(self):
        # replicate monthly_ic_series' convention exactly: signal at a
        # month-end d = the target it will be scored against, i.e. the
        # convexity-adjusted return to the LAST trade day of next month
        dates, tks, closes = panels()

        def next_month_end(i):
            nxt = next((j for j in range(i + 1, len(dates))
                        if month_key(dates[j]) != month_key(dates[i])), None)
            if nxt is None:
                return None
            end = nxt
            while (end + 1 < len(dates)
                   and month_key(dates[end + 1]) == month_key(dates[nxt])):
                end += 1
            return dates[end]

        sig: dict[str, dict[str, float]] = {tk: {} for tk in tks}
        for i in range(len(dates)):
            d, d_end = dates[i], next_month_end(i)
            if d_end is None:
                continue
            # d is a month-end iff the NEXT trade date opens a new month
            if month_key(dates[i + 1]) == month_key(d):
                continue
            for tk in tks:
                c0, c1 = closes[tk][d], closes[tk][d_end]
                fwd = c1 / c0 - 1
                sig[tk][d] = fwd - fwd * fwd / 2
        row = off.eval_signal(sig, closes, dates, "foresight",
                              "test", "planted next-month return")
        self.assertGreater(row["ic_mean"], 0.95, row)
        self.assertEqual(row["id"], "foresight")

    def test_random_signal_is_not_foresight(self):
        dates, tks, closes = panels(seed=5)
        rng = random.Random(9)
        sig = {tk: {d: rng.gauss(0, 1) for d in dates} for tk in tks}
        row = off.eval_signal(sig, closes, dates, "noise", "test", "rng")
        self.assertLess(abs(row["ic_mean"] or 0), 0.3)


class TestInteractions(unittest.TestCase):
    def _basis(self, dates, tks, scale=1.0):
        rng = random.Random(scale)
        return {tk: {d: rng.gauss(0, 1) * scale for d in dates}
                for tk in tks}

    def test_count_and_ids(self):
        dates, tks, closes = panels(seed=2)
        basis = [self._basis(dates, tks, s) for s in (1.0, 2.0, 3.0)]
        specs = [{"id": f"s{i}", "source": "t", "desc": "d", "flip": False}
                 for i in range(3)]
        rows = off.interactions(specs, {"closes": closes, "dates": dates},
                                basis, top_k=3)
        self.assertEqual(len(rows), 9)  # C(3,2)=3 pairs x 3 ops
        ids = {r["id"] for r in rows}
        self.assertIn("ix:s0×s1:product", ids)
        self.assertIn("ix:s0×s2:spread", ids)

    def test_rank_signal_scale_free(self):
        dates, tks, _ = panels(seed=4)
        rng = random.Random(1)
        base = {tk: {d: rng.gauss(0, 1) for d in dates} for tk in tks}
        scaled = {tk: {d: 1000.0 * v for d, v in row.items()}
                  for tk, row in base.items()}
        self.assertEqual(off.cs_rank_signal(base, dates),
                         off.cs_rank_signal(scaled, dates))

    def test_mutations_rows(self):
        dates, tks, closes = panels()
        inputs = {"closes": closes, "opens": closes, "volumes": closes,
                  "dates": dates}
        rows = off.mutations(["mom"], ["sharpe"], [3], [10], inputs, [])
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["id"] for r in rows}, {"mom_3m", "sharpe_10d"})


if __name__ == "__main__":
    unittest.main()
