"""Tests for qsa.researchreport (v1.4 ⑨): layered report.

Layering contract: archive strip first (one line of facts), then at
most three four-line cards (是什么/多强/凭什么信/下一步), then the
board, then appendices. Rendering is pure — byte-identical across
calls (golden-testable).
"""
import unittest

from qsa.researchreport import archive_strip, four_line_card, render_layered

META = {
    "run": "offense-full", "dates": ["20210104", "20261106", 1210],
    "universe": "top300", "n_tickers": 300,
    "basis_n": 7, "basis_digest": "56cd62385a",
    "n_candidates": 78, "n_winners": 14,
    "workers": 13, "elapsed_s": "50.7",
}
WINNER = {"id": "wq_a19", "desc": "WQ alpha#19 clone",
          "source": "WorldQuant 101", "oos_ic": 0.073,
          "ic_mean": 0.09, "icir": 1.8, "n_months": 15}
FORGE_WINNER = {**WINNER, "id": "forge_turnover_shock_21",
                "source": "sandbox-forge", "code_fp": "abcd1234"}


class TestStrip(unittest.TestCase):
    def test_strip_is_one_line_of_facts(self):
        s = archive_strip(META)
        self.assertEqual(s.count("\n"), 0)
        for frag in ("run offense-full", "20210104..20261106 ×1210日",
                     "300 只", "残差基 7 因子 @56cd62385a", "候选 78",
                     "过线 14", "13 workers", "50.7s"):
            self.assertIn(frag, s)


class TestFourLineCard(unittest.TestCase):
    def test_exactly_four_content_lines_plus_header(self):
        card = four_line_card(WINNER, 1, 0.03, 12)
        lines = card.splitlines()
        self.assertEqual(len(lines), 5)
        self.assertTrue(lines[0].startswith("### 1."))
        for kw in ("是什么", "多强", "凭什么信", "下一步"):
            self.assertTrue(any(kw in ln for ln in lines), kw)
        self.assertNotIn("沙盒生成", card)

    def test_sandbox_source_is_labelled(self):
        card = four_line_card(FORGE_WINNER, 2, 0.03, 12)
        self.assertIn("沙盒生成", card)
        self.assertIn("abcd1234", card)


class TestLayered(unittest.TestCase):
    def test_layer_order_and_appendices(self):
        md = render_layered(META, [WINNER], "| board |", 0.03, 12,
                            library_md="| lib |",
                            forge_md="闭环", tree_md="树")
        self.assertLess(md.index("档案条"), md.index("前 3 名四行卡"))
        self.assertLess(md.index("前 3 名四行卡"), md.index("board"))
        self.assertLess(md.index("board"), md.index("附录 A"))
        self.assertLess(md.index("附录 A"), md.index("附录 B"))
        self.assertIn("诚实声明", md)

    def test_honest_zero_when_no_winners(self):
        md = render_layered({**META, "n_winners": 0}, [], "| board |",
                            0.03, 12)
        self.assertIn("诚实零", md)

    def test_at_most_three_cards(self):
        winners = [{**WINNER, "id": f"w{i}"} for i in range(5)]
        md = render_layered(META, winners, "", 0.03, 12)
        self.assertIn("### 3. w2", md)
        self.assertNotIn("### 4. w3", md)

    def test_golden_byte_identical(self):
        a = render_layered(META, [WINNER], "b", 0.03, 12)
        b = render_layered(META, [WINNER], "b", 0.03, 12)
        self.assertEqual(a, b)
        self.assertTrue(a.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
