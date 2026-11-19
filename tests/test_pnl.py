"""Long-short PnL layer tests — numbers checkable by hand.

The PnL display is the most quotable part of a card; its math must be
the least negotiable. Hand-computable worlds only (same style as
test_backtest): a monotone world where L-S sign is known by
construction, and unit tests for the monthly/yearly compounding
helpers.
"""
from __future__ import annotations

import unittest

from qsa.factorcard import (pnl_curve_svg, pnl_nav_ascii,
                            render_pnl_md)
from qsa.pnl import (_monthly, _yearly, longshort_pnl,
                     pnl_metrics_table, pnl_year_table)

P = {"months": ["202301", "202302"], "ls_monthly": [0.05, -0.02],
     "g5_monthly": [0.06, 0.01], "g1_monthly": [0.01, 0.03],
     "ls_nav": [1.05, 1.029], "ann_ls_net": 0.15, "ann_g5_net": 0.2,
     "nw_sharpe_ls": 1.2, "max_drawdown_ls": -0.1, "calmar_ls": 1.5,
     "turnover_monthly_one_side": 0.3, "fee_one_side": 0.0008,
     "n_months": 2, "yearly_ls": [("2023", 0.029)]}


class TestCompounding(unittest.TestCase):
    def test_monthly_compounds_within_month(self):
        # 2 days in Jan (+1%, +1%): (1.01*1.01)-1 = 0.0201
        m, r = _monthly([0.01, 0.01, 0.02], ["20230101", "20230102",
                                             "20230201"])
        self.assertEqual(m, ["202301", "202302"])
        self.assertAlmostEqual(r[0], 0.0201)
        self.assertAlmostEqual(r[1], 0.02)

    def test_yearly_compounds_months(self):
        y = _yearly(["202301", "202312"], [0.1, 0.1])
        self.assertEqual(len(y), 1)
        self.assertEqual(y[0][0], "2023")
        self.assertAlmostEqual(y[0][1], 0.21)
        self.assertEqual(_yearly([], []), [])


class TestMonotoneWorld(unittest.TestCase):
    """4 names x 5 months; signal ranks names by their future drift.

    High-signal names rise (A: +1%/day), low-signal names fall (D:
    −1%/day) -> G5 (high factor) outperforms G1 -> L-S must be
    positive at zero fee, and fees only shrink it.
    """

    def _world(self):
        dates = []
        for m in range(1, 6):
            for day in range(1, 22):
                dates.append(f"2023{m:02d}{day:02d}")
        drifts = {"A": 1.01, "B": 1.003, "C": 0.999, "D": 0.99}
        closes = {tk: {d: 100.0 * (dr ** i) for i, d in enumerate(dates)}
                  for tk, dr in drifts.items()}
        # signal: A highest ... D lowest, constant all sample
        signal = {tk: {d: float(4 - i) for d in dates}
                  for i, tk in enumerate(["A", "B", "C", "D"])}
        return closes, dates, signal

    def test_ls_sign_known_by_construction(self):
        closes, dates, signal = self._world()
        p = longshort_pnl(closes, dates, signal, n_groups=2,
                          fee_one_side=0.0)
        self.assertIsNotNone(p)
        self.assertGreater(p["ann_ls_net"], 0.0)     # high factor rises
        self.assertGreater(p["ann_g5_net"], 0.0)
        self.assertGreater(p["ls_nav"][-1], 1.0)

    def test_fee_makes_ls_worse_or_equal(self):
        closes, dates, signal = self._world()
        gross = longshort_pnl(closes, dates, signal, n_groups=2,
                              fee_one_side=0.0)
        fee = longshort_pnl(closes, dates, signal, n_groups=2,
                            fee_one_side=0.01)
        self.assertLessEqual(fee["ann_ls_net"], gross["ann_ls_net"])


class TestRender(unittest.TestCase):
    def test_svg_has_three_lines(self):
        svg = pnl_curve_svg(P)
        self.assertEqual(svg.count("<polyline"), 3)
        self.assertEqual(pnl_curve_svg({"months": []}), "<svg></svg>")

    def test_ascii_nav(self):
        out = pnl_nav_ascii(P["ls_monthly"])
        self.assertIn("L-S净值", out)
        self.assertEqual(pnl_nav_ascii([]), "（无样本）")

    def test_md_sections(self):
        md = render_pnl_md(P, (pnl_metrics_table(P), pnl_year_table(P)))
        for sec in ("模拟 PnL", "多空年化", "年度收益", "≠ 实盘主张"):
            self.assertIn(sec, md)
        self.assertIn("| 2023 | +2.90% |", md)


if __name__ == "__main__":
    unittest.main()
