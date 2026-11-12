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
