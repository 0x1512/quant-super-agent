"""v0.3 gate extensions: registry disciplines (pre-registration, unique IDs,
OOS one-shot, deflation) and factor_code recomputation (FIB 2 phantom-metric,
FIB 9 unit-mismatch)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qsa import engine
from qsa.registry import Registry
from qsa.sandbox import run_factor
from qsa.snapshot import sha256_bytes
from qsa.verify import gate
from tests.test_gate import GateBase  # reuse the honest-pair fixture

GOOD_CODE = '''def factor(closes, tickers, dates, i):
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

REQUIRED = ["rankic_mean", "rankic_tstat", "quintile_spread",
            "monotonicity_proxy", "n_dates"]


class GateV03Base(GateBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reg_path = cls.root / "registry.jsonl"
        cls.h0 = {
            "schema": "hypothesis", "hyp_id": "H-0001",
            "mechanism": "m", "falsifiable_condition": "f",
            "admission": {"required_metrics": REQUIRED,
                          "thresholds": {"rankic_mean": {"op": ">=", "value": 0.02},
                                         "quintile_spread": {"op": ">=", "value": 0.0}},
                          "min_observations": 30},
            "window": cls.window, "family": "gatev03", "ttl_days": 90,
            "status": "registered", "created_at": cls.as_of_iso,
        }
        Registry.open(cls.reg_path).register_hypothesis(cls.h0)
        cls.cards_dir = cls.root / "cards-v03"
        cls.cards_dir.mkdir(exist_ok=True)
        (cls.cards_dir / "H.json").write_text(json.dumps(cls.h0))


class TestRegistryDisciplines(GateV03Base):
    def card_with_code(self, metrics_override=None, **overrides):
        frame = engine.load_frame(self.root / "snapshot", self.window)
        matrix = run_factor(GOOD_CODE, frame.closes, frame.tickers,
                            frame.dates)
        metrics = metrics_override if metrics_override is not None \
            else engine.evaluate_signal(frame, matrix)
        e = {
            "schema": "experiment_result", "exp_id": "E-0001",
            "hyp_id": "H-0001", "window": self.window,
            "snapshot_hash": self.snap.manifest_hash,
            "engine": engine.EVAL_ID, "metrics": metrics,
            "factor_code": GOOD_CODE,
            "factor_code_sha256": sha256_bytes(GOOD_CODE.encode()),
            "verdict": "fail", "settled_at": self.as_of_iso,
        }
        e.update(overrides)
        return e

    def write(self, e, name: str | None = None):
        digest = abs(hash(json.dumps(e, sort_keys=True))) % 9973
        p = self.cards_dir / f"{name or 'E'}-{digest}.json"
        p.write_text(json.dumps(e))
        return self.cards_dir / "H.json", p

    def test_honest_card_with_code_passes_ledger_gate(self):
        e = self.card_with_code()
        h, p = self.write(e)
        ok, errs = gate(h, p, self.root / "snapshot", self.reg_path)
        self.assertTrue(ok, errs)

    def test_unregistered_hypothesis_blocked(self):
        e = self.card_with_code()
        e["hyp_id"] = "H-9999"
        h, p = self.write(e)
        ok, errs = gate(h, p, self.root / "snapshot",
                        self.root / "registry-empty.jsonl")
        self.assertFalse(ok)
        self.assertTrue(any("not registered" in x for x in errs), errs)

    def test_duplicate_exp_id_blocked(self):
        reg = Registry.open(self.root / "registry-dup.jsonl")
        reg.register_hypothesis(self.h0)
        e0 = self.card_with_code()
        reg.settle_experiment(e0, self.h0)
        h, p = self.write(self.card_with_code())
        ok, errs = gate(h, p, self.root / "snapshot",
                        self.root / "registry-dup.jsonl")
        self.assertFalse(ok)
        self.assertTrue(any("already settled" in x for x in errs), errs)

    def test_deflation_flips_verdict_expectation(self):
        # a family mined 9 times before: tstat must clear the N=10 floor
        reg = Registry.open(self.root / "registry-defl.jsonl")
        reg.register_hypothesis(self.h0)
        for n in range(9):
            filler = self.card_with_code()
            filler["exp_id"] = f"E-9{n}00"
            reg.settle_experiment(filler, self.h0)
        frame = engine.load_frame(self.root / "snapshot", self.window)
        matrix = run_factor(GOOD_CODE, frame.closes, frame.tickers,
                            frame.dates)
        metrics = dict(engine.evaluate_signal(frame, matrix))
        # claim: same metrics but with a big tstat-shaped lie removed —
        # verdict must still be 'fail' mechanically; give card verdict=fail
        e = self.card_with_code(metrics_override=metrics)
        h, p = self.write(e)
        ok, errs = gate(h, p, self.root / "snapshot",
                        self.root / "registry-defl.jsonl")
        self.assertTrue(ok, errs)  # honest fail card passes the gate
        # now the same card claiming pass:
        e2 = self.card_with_code(metrics_override=metrics)
        e2["verdict"] = "pass"
        h2, p2 = self.write(e2)
        ok2, errs2 = gate(h2, p2, self.root / "snapshot",
                          self.root / "registry-defl.jsonl")
        self.assertFalse(ok2)
        self.assertTrue(any("mechanical evaluation" in x for x in errs2), errs2)

    def test_phantom_metric_blocked_by_recomputation(self):
        e = self.card_with_code()
        e["metrics"]["rankic_mean"] = 0.42  # the number nobody computed
        e["verdict"] = "fail"  # even an honest-looking verdict can't save it
        h, p = self.write(e)
        ok, errs = gate(h, p, self.root / "snapshot", self.reg_path)
        self.assertFalse(ok)
        self.assertTrue(any("recomputation from factor_code says" in x
                            for x in errs), errs)

    def test_rescaled_metric_blocked(self):
        e = self.card_with_code()
        e["metrics"]["rankic_mean"] = e["metrics"]["rankic_mean"] * 100
        h, p = self.write(e)
        ok, errs = gate(h, p, self.root / "snapshot", self.reg_path)
        self.assertFalse(ok)
        self.assertTrue(any("recomputation" in x for x in errs), errs)

    def test_code_sha_mismatch_blocked(self):
        e = self.card_with_code()
        e["factor_code_sha256"] = "0" * 64
        h, p = self.write(e)
        ok, errs = gate(h, p, self.root / "snapshot", self.reg_path)
        self.assertFalse(ok)
        self.assertTrue(any("factor_code_sha256" in x for x in errs), errs)

    def test_engine_version_pin(self):
        e = self.card_with_code()
        e["engine"] = "mystery-engine-9.9"
        h, p = self.write(e)
        ok, errs = gate(h, p, self.root / "snapshot", self.reg_path)
        self.assertFalse(ok)
        self.assertTrue(any("version pin" in x for x in errs), errs)

    def test_oos_consumption_blocked_at_gate(self):
        reg = Registry.open(self.root / "registry-oos.jsonl")
        h_oos = dict(self.h0)
        h_oos["oos_window"] = self.window
        reg.register_hypothesis(h_oos)
        e0 = self.card_with_code()
        e0["oos"] = {"window": self.window, "verdict": "fail"}
        reg.settle_experiment(e0, h_oos)  # burns the window
        e = self.card_with_code()
        e["oos"] = {"window": self.window, "verdict": "fail"}
        h, p = self.write(e)
        ok, errs = gate(h, p, self.root / "snapshot",
                        self.root / "registry-oos.jsonl")
        self.assertFalse(ok)
        self.assertTrue(any("one-shot" in x for x in errs), errs)


if __name__ == "__main__":
    unittest.main()
