"""Factor card tests — byte-stability and shape of the showcase layer.

The card is the public face of a test result: it must render the same
bytes for the same numbers (golden-testable) and never invent a verdict
it was not given.
"""
import unittest

from qsa.factorcard import (_scale, block_table, ic_chart, metric_table,
                            render_card, render_index, render_index_html,
                            sparkline_svg, verdict_strip)

IC = [{"date": f"2023{i:02d}28", "ic": 0.01 * (i % 7 - 3)} for i in range(1, 13)]


class TestPrimitives(unittest.TestCase):
    def test_scale_clamps_and_degenerate(self):
        self.assertEqual(_scale(0, 0, 1), "▁")
        self.assertEqual(_scale(1, 0, 1), "█")
        self.assertEqual(_scale(0.5, 0.5, 0.5), BLOCK := "▄")  # degenerate
        self.assertEqual(_scale(-9, 0, 1), "▁")  # clamp low
        self.assertEqual(_scale(9, 0, 1), "█")   # clamp high

    def test_ic_chart_byte_stable(self):
        a, b = ic_chart(IC), ic_chart(IC)
        self.assertEqual(a, b)
        self.assertIn("月度IC", a)
        self.assertIn("累计IC", a)
        self.assertIn("202301", a)

    def test_ic_chart_empty(self):
        self.assertEqual(ic_chart([]), "（无 IC 样本）")

    def test_ic_chart_width_downsample(self):
        long = IC * 6  # 72 > width 60
        out = ic_chart(long, width=60)
        rows = [r for r in out.splitlines() if r.startswith("月度IC")]
        self.assertEqual(len(rows[0]) - len("月度IC   "), 60)

    def test_block_table_shape(self):
        detail = {"block_means": [0.05, -0.02, 0.03, 0.0, 0.06, 0.04, 0.01],
                  "reason": "ok"}
        out = block_table(detail, IC * 4)
        self.assertEqual(out.count("\n"), 8)      # header + 7 blocks
        self.assertIn("`-", out)                  # negative block renders dashes

    def test_block_table_empty(self):
        self.assertIn("不足以", block_table({}, IC))


class TestCardSections(unittest.TestCase):
    ROW = {"oos_ic": 0.06, "ic_mean": 0.04, "icir": 0.38,
           "g1_ann": -0.11, "g5_ann": 0.09, "top_minus_bottom": 0.2,
           "ic_positive_share": 0.61, "n_months": 41}

    def test_verdict_strip_marks(self):
        v = verdict_strip({"stage1": "pass", "stage2": "fail",
                           "walk_forward": "pass"})
        self.assertIn("stage1 ✓", v)
        self.assertIn("stage2 ✗", v)

    def test_metric_table_none_safe(self):
        out = metric_table({"oos_ic": None, "icir": None, "n_months": 3})
        self.assertIn("| OOS IC | — |", out)
        self.assertIn("| ICIR（年化） | — |", out)

    def test_render_card_contains_sections(self):
        wf = {"block_means": [0.05, 0.03, 0.06, 0.04, 0.02, 0.05, 0.06],
              "reason": "no decay trigger", "n_decay_triggers": 0,
              "half_life_ratio": 0.59, "positive_blocks": "7/7"}
        meta = {"id": "t", "desc": "d", "source": "s", "scan_n": 35,
                "verdicts": {"stage1": "pass", "stage2": "fail",
                             "walk_forward": "pass"}}
        card = render_card(meta, self.ROW, wf, IC)
        for sec in ("测试卡 · t", "判决链", "主指标", "月度 IC",
                    "Walk-forward", "诚实脚注"):
            self.assertIn(sec, card)
        self.assertEqual(render_card(meta, self.ROW, wf, IC), card)  # stable

    def test_render_index_sections(self):
        rows = [
            {"id": "a", "family": "f1", "oos_ic": 0.1, "icir_a": 1.2,
             "tmb": 0.2, "pos_share": 0.6, "s2": "fail", "s2v2": "pass",
             "wf": "pass", "both": True},
            {"id": "b", "family": "f2", "oos_ic": -0.01, "icir_a": 0.5,
             "tmb": 0.0, "pos_share": 0.5, "s2": "fail", "s2v2": "fail",
             "wf": "fail", "both": False},
        ]
        meta = {"title": "t", "snap": "s", "n_months": "12", "n_tickers": 3,
                "dedup_note": "重合 1 对"}
        out = render_index(rows, meta)
        for sec in ("幸存者", "族级对比", "全部测试项", "重合 1 对", "[卡](a.md)"):
            self.assertIn(sec, out)
        self.assertEqual(render_index(rows, meta), out)

    def test_render_index_no_survivors(self):
        rows = [{"id": "b", "family": "f", "oos_ic": 0.0, "icir_a": 0.0,
                 "tmb": 0.0, "pos_share": 0.5, "s2": "fail", "s2v2": "fail",
                 "wf": "fail", "both": False}]
        out = render_index(rows, {"title": "t", "snap": "s",
                                  "n_months": "1", "n_tickers": 1})
        self.assertIn("无（诚实零也是结果）", out)


class TestHtmlChannel(unittest.TestCase):
    ROWS = [
        {"id": "a", "family": "f1", "oos_ic": 0.1, "icir_a": 1.2,
         "tmb": 0.2, "pos_share": 0.6, "s2": "fail", "s2v2": "pass",
         "wf": "pass", "both": True},
        {"id": "b", "family": "f2", "oos_ic": -0.05, "icir_a": 0.5,
         "tmb": 0.0, "pos_share": 0.5, "s2": "fail", "s2v2": "fail",
         "wf": "fail", "both": False},
    ]
    META = {"title": "t<snap>", "snap": "s", "n_months": "12",
            "n_tickers": 3}

    def test_sparkline_svg_shape(self):
        svg = sparkline_svg(IC)
        self.assertTrue(svg.startswith("<svg "))
        self.assertIn("<rect", svg)
        self.assertIn("<polyline", svg)
        self.assertEqual(sparkline_svg([]), "<svg></svg>")

    def test_render_index_html_no_js_and_escaped(self):
        out = render_index_html(self.ROWS, self.META, {"a": IC, "b": IC})
        self.assertNotIn("<script", out)
        self.assertIn("t&lt;snap&gt;", out)          # escaped
        self.assertIn("class=\"surv\"", out)
        self.assertEqual(render_index_html(self.ROWS, self.META,
                                           {"a": IC, "b": IC}), out)

    def test_render_index_html_zero_survivors(self):
        rows = [dict(self.ROWS[1])]
        out = render_index_html(rows, self.META, {"b": IC})
        self.assertIn("诚实零", out)
        self.assertNotIn("class=\"surv\"", out)


if __name__ == "__main__":
    unittest.main()
