"""Tests for qsa.followup (v1.4 ②): conversational incremental research.

The load-bearing promise: a bar-only follow-up NEVER rescores — the
cached rows are reused verbatim and only the verdict walk is redone;
anything that can move a score is honestly labelled recompute; anything
unparseable is refused rather than guessed.
"""
import json
import tempfile
import unittest
from pathlib import Path

from qsa import followup


def prev_fixture():
    rows = [
        {"id": "A", "oos_ic": 0.06, "n_months": 14, "ic_mean": 0.1,
         "icir": 1.0},
        {"id": "B", "oos_ic": 0.04, "n_months": 14, "ic_mean": 0.1,
         "icir": 1.0},
        {"id": "C", "oos_ic": 0.02, "n_months": 14, "ic_mean": 0.1,
         "icir": 1.0},
        {"id": "D", "oos_ic": 0.09, "n_months": 3, "ic_mean": 0.1,
         "icir": 1.0},
    ]
    return {"config": {"thresh": 0.03, "min_months": 12}, "rows": rows}


class TestParse(unittest.TestCase):
    def test_bar_only_is_rejudge(self):
        ins = followup.parse_instruction("门槛提到 0.05")
        self.assertEqual(ins["mode"], "rejudge")
        self.assertEqual(ins["thresh"], 0.05)

    def test_bar_word(self):
        self.assertEqual(followup.parse_instruction("严格一点")["thresh"],
                         0.05)

    def test_min_months_only_is_rejudge(self):
        ins = followup.parse_instruction("至少 18 个月才算")
        self.assertEqual(ins["mode"], "rejudge")
        self.assertEqual(ins["min_months"], 18)

    def test_universe_is_recompute(self):
        ins = followup.parse_instruction("只要小盘")
        self.assertEqual(ins["mode"], "recompute")
        self.assertEqual(ins["universe"], {"name": "smallcap"})

    def test_bar_plus_universe_is_recompute(self):
        ins = followup.parse_instruction("门槛 0.05，并剔除小盘")
        self.assertEqual(ins["mode"], "recompute")
        self.assertEqual(ins["thresh"], 0.05)
        self.assertEqual(ins["universe"]["exclude"], "smallcap")

    def test_unknown_refuses(self):
        ins = followup.parse_instruction("换一批数据源吧")
        self.assertEqual(ins["mode"], "refuse")
        self.assertIn("reason", ins)


class TestRejudge(unittest.TestCase):
    def test_pure_reverdict_zero_rescore(self):
        res = followup.rejudge(prev_fixture(),
                               {"mode": "rejudge", "thresh": 0.05,
                                "min_months": 12, "raw": "门槛提到 0.05"})
        # old winners at 0.03: A, B (D fails min_months)
        # new winners at 0.05: A
        self.assertEqual(res["kept"], ["A"])
        self.assertEqual(res["dropped"], ["B"])
        self.assertEqual(res["added"], [])
        self.assertEqual(res["n_winners"], 1)
        self.assertEqual(res["rows_reused"], 4)
        self.assertEqual(res["rows_rescored"], 0)

    def test_tighter_months_moves_the_bar_not_scores(self):
        res = followup.rejudge(prev_fixture(),
                               {"mode": "rejudge", "thresh": 0.03,
                                "min_months": 14, "raw": "至少 14 个月"})
        self.assertEqual(sorted(res["kept"]), ["A", "B"])
        self.assertEqual(res["dropped"], [])

    def test_deterministic_bytes(self):
        ins = {"mode": "rejudge", "thresh": 0.05, "raw": "门槛提到 0.05"}
        a = {k: v for k, v in followup.rejudge(prev_fixture(), ins).items()
             if k != "elapsed_s"}
        b = {k: v for k, v in followup.rejudge(prev_fixture(), ins).items()
             if k != "elapsed_s"}
        self.assertEqual(a, b)


class TestLoadPrev(unittest.TestCase):
    def test_loads_all_streams_including_forge(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "leaderboard.json").write_text(json.dumps({
                "library": [{"id": "L", "oos_ic": 0.05, "n_months": 14}],
                "interactions": [{"id": "I", "oos_ic": 0.04, "n_months": 14}],
                "mutations": [{"id": "M", "oos_ic": 0.02, "n_months": 14}],
                "forge": [{"id": "F", "oos_ic": 0.06, "n_months": 14}],
            }), encoding="utf-8")
            (d / "run_config.json").write_text(json.dumps(
                {"thresh": 0.03, "min_months": 12, "goal": "g",
                 "fingerprint": "fp"}), encoding="utf-8")
            prev = followup.load_prev(d)
            self.assertEqual([r["id"] for r in prev["rows"]],
                             ["L", "I", "M", "F"])
            self.assertEqual(prev["config"]["fingerprint"], "fp")

    def test_v13_run_falls_back_to_contract_config(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "leaderboard.json").write_text(json.dumps({
                "library": [{"id": "L", "oos_ic": 0.05, "n_months": 14}],
                "interactions": [], "mutations": []}), encoding="utf-8")
            prev = followup.load_prev(d)
            self.assertEqual(prev["config"]["thresh"], 0.03)


class TestRender(unittest.TestCase):
    def test_render_declares_mode_and_counts(self):
        res = followup.rejudge(prev_fixture(),
                               {"mode": "rejudge", "thresh": 0.05,
                                "min_months": 12, "raw": "门槛提到 0.05"})
        md = followup.render(res)
        self.assertIn("门槛提到 0.05", md)
        self.assertIn("复用", md)
        self.assertIn("重算 0", md)


if __name__ == "__main__":
    unittest.main()
