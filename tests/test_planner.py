"""Tests for qsa.planner (v1.4 ①/③): intent -> Plan -> fingerprint -> tree.

The planner is the front door of the product: one sentence in, a
fingerprinted plan out. These tests pin:

* defaults match the runner contract exactly (a silent default drift
  would re-run a different study than the one shown in the showcase);
* every non-default value is traceable to a phrase in the goal (notes);
* the fingerprint is deterministic and sensitive (any parameter change
  moves it);
* the research tree has one node per stage incl. forge, and renders.
"""
import unittest

from qsa.planner import (Plan, fingerprint, intent_to_plan, render_tree,
                         streams_for, tree, windows_for)


class TestDefaults(unittest.TestCase):
    def test_default_plan_matches_runner_contract(self):
        p = Plan(goal="x")
        self.assertEqual(p.month_families, ["mom", "mom_gap"])
        self.assertEqual(p.day_families,
                         ["dist_high", "sharpe", "intraday", "vol_of_vol"])
        self.assertEqual(p.month_wins, [3, 6, 9, 18, 24])
        self.assertEqual(p.day_wins, [10, 42, 63, 126, 252])
        self.assertEqual(p.thresh, 0.03)
        self.assertEqual(p.min_months, 12)
        self.assertEqual(p.top_k, 4)
        self.assertEqual(p.streams, {"zoo": True, "library": True,
                                     "interactions": True, "mutations": True,
                                     "forge": False})

    def test_windows_and_streams_accessors(self):
        p = Plan(goal="x")
        mf, df, mw, dw = windows_for(p)
        self.assertEqual((mf, df, mw, dw),
                         (p.month_families, p.day_families,
                          p.month_wins, p.day_wins))
        self.assertEqual(streams_for(p), p.streams)


class TestIntent(unittest.TestCase):
    def test_bar_words_and_explicit_bar(self):
        self.assertEqual(intent_to_plan("严格一点").thresh, 0.05)
        self.assertEqual(intent_to_plan("门槛 0.05 再看").thresh, 0.05)
        # the verbose form a human actually writes must parse too
        self.assertEqual(
            intent_to_plan("残差进攻，门槛 residual oos IC > 0.04").thresh,
            0.04)
        self.assertTrue(any("0.05" in n for n in
                            intent_to_plan("门槛 0.05").notes))

    def test_min_months_phrase_is_not_a_window(self):
        p = intent_to_plan("门槛 0.05，样本至少 17 个月")
        self.assertEqual(p.min_months, 17)
        self.assertNotIn(17, p.month_wins)      # must NOT become a sweep

    def test_window_merge(self):
        p = intent_to_plan("看 30 日和 6 个月的窗口")
        self.assertIn(30, p.day_wins)
        self.assertIn(6, p.month_wins)

    def test_universe_hints(self):
        self.assertEqual(intent_to_plan("只看小盘").universe["name"],
                         "smallcap")
        p = intent_to_plan("剔除小盘再来一遍")
        self.assertEqual(p.universe, {"name": "top300",
                                      "exclude": "smallcap"})

    def test_focus_disables_unmentioned_streams(self):
        p = intent_to_plan("只跑交互，别的不要")
        self.assertTrue(p.streams["interactions"])
        self.assertFalse(p.streams["library"])
        self.assertFalse(p.streams["mutations"])
        self.assertTrue(p.streams["zoo"])       # basis is never optional

    def test_forge_hint(self):
        p = intent_to_plan("引用因子库+交互+窗口变异+沙盒生成")
        self.assertTrue(p.streams["forge"])
        self.assertTrue(p.streams["library"])   # mentioned -> stays on

    def test_every_nondefault_has_a_note(self):
        p = intent_to_plan("严格，剔除小盘，只跑窗口变异，60 日")
        self.assertTrue(len(p.notes) >= 3)


class TestFingerprint(unittest.TestCase):
    def test_deterministic_and_sensitive(self):
        a = intent_to_plan("门槛 0.05 只跑窗口变异")
        b = intent_to_plan("门槛 0.05 只跑窗口变异")
        self.assertEqual(fingerprint(a), fingerprint(b))
        self.assertEqual(len(fingerprint(a)), 16)
        c = intent_to_plan("门槛 0.06 只跑窗口变异")
        self.assertNotEqual(fingerprint(a), fingerprint(c))
        self.assertNotEqual(fingerprint(a), fingerprint(Plan(goal="y")))

    def test_dict_and_plan_agree(self):
        p = intent_to_plan("只看小盘")
        self.assertEqual(fingerprint(p), fingerprint(p.to_dict()))


class TestTree(unittest.TestCase):
    def test_skeleton_and_render(self):
        t = tree("goal text", "abcd1234")
        ids = [n["id"] for n in t["nodes"]]
        self.assertEqual(ids, ["gate", "snapshot", "basis", "library",
                               "interactions", "mutations", "forge",
                               "orders"])
        md = render_tree(t)
        self.assertIn("abcd1234", md)
        self.assertIn("goal text", md)
        t["nodes"][0]["status"] = "done"
        t["nodes"][0]["note"] = "5 项核对通过"
        self.assertIn("✓", render_tree(t))
        self.assertIn("EnvSmith", md)            # roles are named


if __name__ == "__main__":
    unittest.main()
