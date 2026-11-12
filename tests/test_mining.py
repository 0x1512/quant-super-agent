"""Mining-loop tests: end-to-end discipline, blocked attempts, determinism,
attribution taxonomy."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qsa import attribution
from qsa.llm import ScriptedLLM
from qsa.mining import run_order
from qsa.snapshot import build_snapshot

H_PASS_MOST = ('{"mechanism": "m: almost anything counts", '
               '"falsifiable_condition": "f", '
               '"admission": {"required_metrics": ["rankic_mean", "rankic_tstat", '
               '"quintile_spread", "monotonicity_proxy", "n_dates"], '
               '"thresholds": {"rankic_mean": {"op": ">=", "value": -1.0}}, '
               '"min_observations": 30}}')

H_OOS = ('{"mechanism": "m: with a burned OOS window", '
         '"falsifiable_condition": "f", '
         '"oos_window": "OOSPLACEHOLDER", '
         '"admission": {"required_metrics": ["rankic_mean", "rankic_tstat", '
         '"quintile_spread", "monotonicity_proxy", "n_dates"], '
         '"thresholds": {"rankic_mean": {"op": ">=", "value": -1.0}}, '
         '"min_observations": 5}}')

F_MOM10 = '''def factor(closes, tickers, dates, i):
    if i < 10:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 10]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = a / b - 1.0
    return out'''

F_CHEAT_IMPORT = ("import os\n"
                  "def factor(closes, tickers, dates, i):\n"
                  "    return {}\n")

ORDER = "Mine one cross-sectional factor. Admission bar: rankic_mean >= 0.02."


class TestMining(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snap_dir = self.root / "snapshot"
        build_snapshot(self.snap_dir, seed=42, tickers=12, days=90)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, work: Path, responses, **kw):
        llm = ScriptedLLM(responses, run_log=work.parent / f"{work.name}-runs.jsonl")
        # v0.3 semantics unless a test opts into roles/debate explicitly: the
        # pre-review path (data+factor only, no debate) is what these assert.
        kw.setdefault("roles", ("data", "factor"))
        kw.setdefault("debate_rounds", 0)
        return run_order(work, self.snap_dir, ORDER, llm,
                         family="test", verbose=False, **kw)

    def test_honest_negative_chain_settles(self):
        summary = self._run(self.root / "w1",
                            [H_PASS_MOST, F_MOM10, H_PASS_MOST, F_MOM10])
        # the lax bar passes on iteration 1 and the loop stops there —
        # a pass under budget is a success, not a reason to keep mining
        self.assertEqual(len(summary["iterations"]), 1)
        r = summary["iterations"][0]
        self.assertTrue(r["merged"])
        self.assertEqual(r["verdict"], "pass")
        self.assertEqual(summary["final_verdict"], "pass")

    def test_sandbox_cheat_recorded_not_settled(self):
        summary = self._run(self.root / "w2",
                            [H_PASS_MOST, F_CHEAT_IMPORT, H_PASS_MOST, F_MOM10])
        blocked = [r for r in summary["iterations"] if r.get("blocked")]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["stage"], "factor_sandbox")
        self.assertIn("imports", str(blocked[0]["blocked"]))
        # iteration 2 still settles — one blocked attempt doesn't burn the order
        self.assertTrue(summary["iterations"][1]["merged"])

    def test_budget_is_respected(self):
        summary = self._run(self.root / "w3",
                            [H_PASS_MOST, F_CHEAT_IMPORT] * 3, budget=3)
        self.assertEqual(len(summary["iterations"]), 3)
        self.assertTrue(all(r.get("blocked") for r in summary["iterations"]))
        self.assertIsNone(summary["final_verdict"])

    def test_full_run_is_deterministic(self):
        def run_into(name):
            work = self.root / name
            self._run(work, [H_PASS_MOST, F_MOM10, H_PASS_MOST, F_MOM10])
            return {rel: (work / "forge" / rel).read_bytes()
                    for rel in ("state.json", "events.jsonl")} | \
                   {"registry": (work / "registry.jsonl").read_bytes(),
                    "runs": (self.root / f"{name}-runs.jsonl").read_bytes()}
        a = run_into("det-a")
        b = run_into("det-b")
        for key in a:
            self.assertEqual(a[key], b[key], f"{key} diverged across runs")

    def test_oos_window_burned_after_pass(self):
        # derive a real OOS window from the snapshot
        dates = sorted({ln.split(",")[0] for ln in
                        (self.snap_dir / "daily" / "prices.csv")
                        .read_text().splitlines()[1:]})
        oos = f"{dates[-10]}:{dates[-1]}"
        h_oos = H_OOS.replace("OOSPLACEHOLDER", oos)
        shared_ledger = self.root / "shared-registry.jsonl"
        summary = self._run(self.root / "w4", [h_oos, F_MOM10],
                            registry_path=shared_ledger)
        self.assertEqual(summary["final_verdict"], "pass")
        e = json.loads((self.root / "w4" / "cards" / "E-0001.json").read_text())
        self.assertIn("oos", e)
        # the window is burned in the shared ledger: a second order reusing it
        # is refused at hypothesis registration
        summary2 = self._run(self.root / "w5", [h_oos, F_MOM10],
                             registry_path=shared_ledger)
        blocked = [r for r in summary2["iterations"] if r.get("blocked")]
        self.assertTrue(blocked)
        self.assertEqual(blocked[0]["stage"], "hypothesis_registry")
        self.assertIn("one-shot", str(blocked[0]["blocked"]))
        self.assertTrue(all(r.get("blocked") for r in summary2["iterations"]))


class TestAttribution(unittest.TestCase):
    def _e(self, **kw):
        e = {"metrics": {"rankic_mean": 0.01, "n_dates": 79},
             "attribution": {}, "oos": None}
        e.update(kw)
        return e

    H = {"admission": {"min_observations": 30}}

    def test_insufficient_observations(self):
        a = attribution.classify(self._e(metrics={"rankic_mean": 0.01,
                                                  "n_dates": 5}), self.H)
        self.assertEqual(a["class"], "insufficient_observations")

    def test_deflation(self):
        a = attribution.classify(self._e(), self.H,
                                 reasons=["deflation: |t| < floor"])
        self.assertEqual(a["class"], "deflation")

    def test_instability(self):
        a = attribution.classify(
            self._e(attribution={"neighborhood_stable": False,
                                 "neighborhood_rankic": {"lag_9": -0.01}}),
            self.H, reasons=["rankic_mean=0.01 fails pre-registered >= 0.02"])
        self.assertEqual(a["class"], "instability")

    def test_threshold_miss(self):
        a = attribution.classify(self._e(), self.H,
                                 reasons=["rankic_mean=0.01 fails >= 0.02"])
        self.assertEqual(a["class"], "threshold_miss")

    def test_oos_miss(self):
        a = attribution.classify(
            self._e(oos={"verdict": "fail", "window": "x:y"}), self.H,
            reasons=["all good in-sample"])
        self.assertEqual(a["class"], "oos_miss")

    def test_prompt_is_explicit_about_no_bar_lowering(self):
        prompt = attribution.next_hypothesis_prompt("order", {"hyp_id": "H-0001"},
                                                    {"class": "threshold_miss"})
        self.assertIn("do not lower thresholds", prompt)
        self.assertIn("H-0001", prompt)


if __name__ == "__main__":
    unittest.main()


class TestV04Layers(unittest.TestCase):
    """Roles + adversarial review wired into the loop (default configs)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snap = self.root / "snap"
        build_snapshot(self.snap, seed=42, tickers=12, days=90)
        self.dates = engine_dates(self.snap)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, work, responses, snap=None, **kw):
        llm = ScriptedLLM(responses, run_log=work.parent / f"{work.name}-runs.jsonl")
        return run_order(work, snap or self.snap, ORDER, llm,
                         family="v04", verbose=False, **kw)

    def test_risk_veto_records_instability(self):
        # lax bar passes in-sample; default roles include risk -> the halves
        # disagree (seed 42 momentum) -> honest fail with class instability
        summary = self._run(self.root / "w1",
                            [H_PASS_MOST, F_MOM10, H_PASS_MOST, F_MOM10])
        r = summary["iterations"][0]
        self.assertEqual(r["verdict"], "fail")
        self.assertEqual(r["attribution"]["class"], "instability")
        card = json.loads((self.root / "w1" / "cards" / "E-0001.json").read_text())
        self.assertFalse(card["attribution"]["neighborhood_stable"])
        self.assertIn("first_half", card["attribution"]["neighborhood_rankic"])

    def test_review_admits_a_stable_passing_candidate(self):
        planted = self.root / "planted"
        build_snapshot(planted, seed=11, tickers=12, days=90,
                       plant={"effect": "reversal", "strength": 0.15})
        ds = engine_dates(planted)
        h = json.dumps({
            "mechanism": "1-day reversal: losers bounce",
            "falsifiable_condition": "mean rank IC <= 0",
            "oos_window": f"{ds[-15]}:{ds[-1]}",
            "admission": {"required_metrics": ["rankic_mean", "rankic_tstat",
                                               "quintile_spread",
                                               "monotonicity_proxy", "n_dates"],
                          "thresholds": {"rankic_mean": {"op": ">=",
                                                         "value": 0.02}},
                          "min_observations": 10}})
        bull = json.dumps({"side": "bull", "claims": [
            {"kind": "mechanism", "statement": "documented reversal",
             "checkable": False}]})
        bear = json.dumps({"side": "bear", "claims": [
            {"kind": "robustness", "statement": "halves disagree",
             "checkable": True, "check": "halves_stability"}]})
        summary = self._run(self.root / "w2", [h, F_REV_1D, bull, bear],
                            snap=planted, debate_rounds=1)
        self.assertEqual(summary["final_verdict"], "pass")
        card = json.loads((self.root / "w2" / "cards" / "E-0001.json").read_text())
        self.assertTrue(card["review"]["admitted"])
        self.assertEqual(len(card["review"]["review_ids"]), 2)
        # R cards exist on disk and in the ledger
        self.assertTrue((self.root / "w2" / "cards" / "R-0001.json").exists())
        ledger = [json.loads(l) for l in
                  (self.root / "w2" / "registry.jsonl").read_text().splitlines()]
        self.assertEqual(sum(1 for x in ledger if x.get("type") == "review"), 2)

    def test_review_vetoes_the_unstable_noise_passer(self):
        noise = self.root / "noise8"
        build_snapshot(noise, seed=8, tickers=12, days=90)
        ds = engine_dates(noise)
        h = json.dumps({
            "mechanism": "1-day reversal: losers bounce",
            "falsifiable_condition": "mean rank IC <= 0",
            "oos_window": f"{ds[-15]}:{ds[-1]}",
            "admission": {"required_metrics": ["rankic_mean", "rankic_tstat",
                                               "quintile_spread",
                                               "monotonicity_proxy", "n_dates"],
                          "thresholds": {"rankic_mean": {"op": ">=",
                                                         "value": 0.02}},
                          "min_observations": 10}})
        bull = json.dumps({"side": "bull", "claims": [
            {"kind": "mechanism", "statement": "documented reversal",
             "checkable": False}]})
        bear = json.dumps({"side": "bear", "claims": [
            {"kind": "robustness", "statement": "halves disagree",
             "checkable": True, "check": "halves_stability"}]})
        # no risk role: only the debate (bear claim verified by the gate's own
        # mechanics) can catch seed 8's unstable but IS+OOS-passing noise
        summary = self._run(self.root / "w3", [h, F_REV_1D, bull, bear],
                            snap=noise, roles=("data", "factor"),
                            debate_rounds=1)
        self.assertEqual(summary["final_verdict"], "fail")
        card = json.loads((self.root / "w3" / "cards" / "E-0001.json").read_text())
        self.assertFalse(card["review"]["admitted"])
        self.assertEqual(card["review"]["upheld_objections"][0]["check"],
                         "halves_stability")
        r = summary["iterations"][0]
        self.assertEqual(r["attribution"]["class"], "review_veto")


def engine_dates(snap_dir):
    from qsa import engine
    return engine.load_frame(snap_dir).dates


F_REV_1D = '''def factor(closes, tickers, dates, i):
    if i < 1:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 1]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = -(a / b - 1.0)
    return out
'''
