"""Tradeable-metrics backtest layer — math must be checkable by hand.

Every test here pins a number you can verify on paper: NW Sharpe on a
manufactured autocorrelated series, drawdown on a tiny equity path, fee
arithmetic on a two-name two-month world, capacity under a stated
participation cap. If the layer ever rounds, smooths, or silently
renormalizes differently, these fail.
"""
from __future__ import annotations

import math
import unittest

from qsa.backtest import (capacity, evaluate, max_drawdown, nw_sharpe,
                          portfolio_path)


class TestNWSharpe(unittest.TestCase):
    def test_constant_positive_series(self):
        # every day +0.1%: zero variance -> omega=0 -> None (honest)
        self.assertIsNone(nw_sharpe([0.001] * 100))

    def test_iid_series_nw_close_to_naive(self):
        # deterministic LCG noise with drift: genuinely near-zero lag
        # autocovariances, so the NW adjustment must be small
        state = 12345
        rets = []
        for i in range(400):
            state = (1103515245 * state + 12345) % (2 ** 31)
            u = state / 2 ** 31  # U(0,1)
            rets.append(0.0005 + (u - 0.5) * 0.02)
        m = sum(rets) / len(rets)
        naive = m / math.sqrt(
            sum((r - m) ** 2 for r in rets) / (len(rets) - 1)) * 242 ** 0.5
        nw = nw_sharpe(rets)
        self.assertIsNotNone(nw)
        self.assertAlmostEqual(nw, naive, delta=abs(naive) * 0.30)

    def test_strong_negative_autocorr_is_padded_not_exploding(self):
        # alternating +/-: Bartlett omega^2 would go near zero without
        # the PSD floor; the padded estimate must stay within sane range
        rets = [0.002 if i % 2 == 0 else -0.0019 for i in range(300)]
        nw = nw_sharpe(rets)
        self.assertIsNotNone(nw)
        self.assertLess(abs(nw), 500)

    def test_short_series_returns_none(self):
        self.assertIsNone(nw_sharpe([0.01] * 10))


class TestDrawdown(unittest.TestCase):
    def test_hand_computed_path(self):
        # +10%, -50%: equity 1.1 -> 0.55; dd = 0.55/1.1 - 1 = -0.5
        self.assertAlmostEqual(max_drawdown([0.10, -0.5]), -0.5)
        # monotone up: no drawdown
        self.assertAlmostEqual(max_drawdown([0.1, 0.1, 0.1]), 0.0)
        # recover then crash harder: 1.21 -> 1.331 -> 0.6655
        # dd = 0.6655/1.331 - 1 = -0.5
        self.assertAlmostEqual(max_drawdown([0.1, 0.1, -0.5]), -0.5)

    def test_constant(self):
        self.assertAlmostEqual(max_drawdown([0.0] * 50), 0.0)


def _world():
    """2 tickers, 4 months x ~21 days, deterministic prices.

    A: up 1%/day every day (close_i = 100 * 1.01^i)
    B: flat 100 forever
    Signal: B scores higher than A from month 2 on.
    """
    dates = []
    for y, m in [("2023", 1), ("2023", 2), ("2023", 3), ("2023", 4),
                 ("2023", 5)]:
        for day in range(1, 22):
            dates.append(f"{y}{m:02d}{day:02d}")
    # trading dates must be sorted & unique
    assert dates == sorted(dates)
    closes = {"A": {}, "B": {}}
    for i, d in enumerate(dates):
        closes["A"][d] = 100.0 * (1.01 ** i)
        closes["B"][d] = 100.0
    signal = {
        "A": {d: 0.0 for d in dates},
        "B": {d: 1.0 for d in dates},
    }
    return closes, dates, signal


class TestPortfolioPath(unittest.TestCase):
    def test_two_name_world_gross_and_fees(self):
        closes, dates, signal = _world()
        port = portfolio_path(closes, dates, signal, n_groups=2, group=2,
                              fee_one_side=0.0)
        # group 2 = highest factor = {B} (flat): every held day gross = 0
        for g in port["gross"]:
            self.assertAlmostEqual(g, 0.0)
        self.assertTrue(port["net"])
        # zero fee -> net == gross
        self.assertEqual(port["net"], port["gross"])
        # one rebalance cost = 1.0 turnover (0->1 on B), annual turnover
        # = sum(turnovers) * 12 / n_months; first month buys (turn=1),
        # later months hold the same name (turn=0)
        self.assertAlmostEqual(sum(port["turnovers"]), 1.0)
        # with a fee, net must be <= gross day-by-day
        port_fee = portfolio_path(closes, dates, signal, n_groups=2,
                                  group=2, fee_one_side=0.001)
        self.assertTrue(all(n <= g + 1e-12 for n, g in
                            zip(port_fee["net"], port_fee["gross"])))

    def test_group_one_is_lowest_factor(self):
        closes, dates, signal = _world()
        port = portfolio_path(closes, dates, signal, n_groups=2, group=1,
                              fee_one_side=0.0)
        # group 1 = {A} (up 1%/day): gross must be ~0.01 every held day
        for g in port["gross"]:
            self.assertAlmostEqual(g, 0.01, delta=1e-9)


class TestCapacity(unittest.TestCase):
    def test_participation_cap_math(self):
        port = {"holdings": {"20230101": ["A", "B"]}}
        # equal weight 0.5 each; ADV A=1000, B=4000 (thousand CNY)
        caps = {"202301": {"A": 1000.0, "B": 4000.0}}
        # C = min(0.1*1000/0.5, 0.1*4000/0.5) = min(200, 800) = 200
        self.assertAlmostEqual(
            capacity(port, [], caps, participation=0.1), 200.0)

    def test_no_meta_gives_none(self):
        port = {"holdings": {"20230101": ["A"]}}
        self.assertIsNone(capacity(port, [], {}, 0.1))


class TestEvaluate(unittest.TestCase):
    def test_full_dict_shape_and_partitions_echo(self):
        closes, dates, signal = _world()
        m = evaluate(closes, dates, signal, cap_proxy=None, n_groups=2,
                     group=1, partitions=("20230321", "20240421",
                                          "20230521"))
        for key in ("ann_return_net", "nw_sharpe_net", "max_drawdown",
                    "turnover_monthly_one_side", "turnover_annual_one_side",
                    "fee_one_side", "participation_cap",
                    "capacity_thousand_cny", "triple_gate", "partitions"):
            self.assertIn(key, m)
        # partitions echoed back exactly (no silent re-splitting)
        self.assertEqual(m["partitions"],
                         ["20230321", "20240421", "20230521"])
        self.assertEqual(m["fee_one_side"], 0.0008)
        self.assertIsNone(m["capacity_thousand_cny"])  # no meta -> None

    def test_group_one_beats_group_two_here(self):
        # A rises 1%/day, B is flat; signal says B high. So holding the
        # LOW factor group (A) must out-earn the high group (B).
        closes, dates, signal = _world()
        m_low = evaluate(closes, dates, signal, n_groups=2, group=1)
        m_high = evaluate(closes, dates, signal, n_groups=2, group=2)
        self.assertGreater(m_low["ann_return_net"], m_high["ann_return_net"])


if __name__ == "__main__":
    unittest.main()
