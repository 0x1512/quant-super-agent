"""Gate tests — the v0.2 acceptance surface.

Every FIB class that v0.2 claims to catch (1, 4, 7, 14, 15; plus 3 and the
reverse verdict lie) is injected into an otherwise honest card pair and must
be blocked by ``qsa.verify.gate`` with a localized error. The honest pair —
which on this toy data usually carries verdict=fail — must PASS: honesty is
the product, negative results are first-class.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qsa import admission, engine, snapshot
from qsa.verify import gate

REQUIRED = ["rankic_mean", "rankic_tstat", "quintile_spread",
            "monotonicity_proxy", "n_dates"]
THRESHOLDS = {
    "rankic_mean": {"op": ">=", "value": 0.02},
    "quintile_spread": {"op": ">=", "value": 0.0},
}


class GateBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.snap = snapshot.build_snapshot(cls.root / "snapshot",
                                           seed=42, tickers=12, days=90)
        cls.window = f"{cls.snap.manifest['start']}:{cls.snap.manifest['as_of']}"
        as_of = cls.snap.manifest["as_of"]
        cls.as_of_iso = f"{as_of[:4]}-{as_of[4:6]}-{as_of[6:]}"
        result = engine.run(str(cls.root / "snapshot"), k=10)
        cls.metrics = result["metrics"]
        cls.attribution = result["attribution"]
        cls.verdict, _ = admission.evaluate(
            {"required_metrics": REQUIRED, "thresholds": THRESHOLDS,
             "min_observations": 30}, cls.metrics)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def write_pair(self, root: Path, e_mutate=None, h_mutate=None):
        """Write an honest H/E pair (optionally mutated); returns their paths."""
        h = {
            "schema": "hypothesis", "hyp_id": "H-0001",
            "mechanism": "momentum continuation", "falsifiable_condition": "IC <= 0",
            "admission": {"required_metrics": REQUIRED, "thresholds": THRESHOLDS,
                          "min_observations": 30},
            "window": self.window, "ttl_days": 90, "status": "registered",
            "created_at": self.as_of_iso,
        }
        e = {
            "schema": "experiment_result", "exp_id": "E-0001", "hyp_id": "H-0001",
            "window": self.window, "snapshot_hash": self.snap.manifest_hash,
            "engine": engine.ENGINE_ID, "metrics": dict(self.metrics),
            "attribution": self.attribution, "verdict": self.verdict,
            "settled_at": self.as_of_iso,
        }
        if h_mutate:
            h_mutate(h)
        if e_mutate:
            e_mutate(e)
        (root / "H.json").write_text(json.dumps(h))
        (root / "E.json").write_text(json.dumps(e))
        return root / "H.json", root / "E.json"

    def case_dir(self, name: str) -> Path:
        d = self.root / "cases" / name
        d.mkdir(parents=True, exist_ok=True)
        return d


class TestHonestPair(GateBase):
    def test_honest_card_passes_gate(self):
        h, e = self.write_pair(self.case_dir("honest"))
        ok, errs = gate(h, e, self.root / "snapshot")
        self.assertTrue(ok, f"honest pair must pass; errors: {errs}")

    def test_verdict_is_mechanical(self):
        self.assertIn(self.verdict, ("pass", "fail"))
        expected, _ = admission.evaluate(
            {"required_metrics": REQUIRED, "thresholds": THRESHOLDS,
             "min_observations": 30}, self.metrics)
        self.assertEqual(self.verdict, expected)


class TestFibInjections(GateBase):
    """v0.2 acceptance: FIB classes 1, 4, 7, 14, 15 all gate-caught."""

    def assert_blocked(self, name: str, e_mutate=None, h_mutate=None,
                       substring: str = ""):
        h, e = self.write_pair(self.case_dir(name), e_mutate, h_mutate)
        ok, errs = gate(h, e, self.root / "snapshot")
        self.assertFalse(ok, f"FIB {name} must be blocked")
        self.assertTrue(any(substring in x for x in errs),
                        f"expected {substring!r} in errors: {errs}")
        return errs

    def test_fib1_missing_field(self):
        self.assert_blocked("fib1", e_mutate=lambda e: e.pop("verdict"),
                            substring="missing required field 'verdict'")

    def test_fib3_lookahead_window(self):
        beyond = str(int(self.snap.manifest["as_of"]) + 1)
        h, e = self.write_pair(self.case_dir("fib3"))
        # keep H.window == E.window so ONLY the as_of check fires
        for p in (h, e):
            doc = json.loads(p.read_text())
            doc["window"] = f"{self.snap.manifest['start']}:{beyond}"
            p.write_text(json.dumps(doc))
        ok, errs = gate(h, e, self.root / "snapshot")
        self.assertFalse(ok)
        self.assertTrue(any("after snapshot as_of" in x for x in errs), errs)

    def test_fib4_snapshot_mismatch(self):
        self.assert_blocked("fib4",
                            e_mutate=lambda e: e.update(snapshot_hash="0" * 64),
                            substring="cites a snapshot that was not used")

    def test_fib7_silent_pass(self):
        # force a card whose metrics genuinely fail a threshold
        def mutate(e):
            e["metrics"]["rankic_mean"] = -0.05
            e["verdict"] = "pass"
        errs = self.assert_blocked("fib7", e_mutate=mutate,
                                   substring="inconsistent with the pre-registered")
        self.assertTrue(any("mechanical evaluation" in x for x in errs), errs)

    def test_fib7_reverse_lie_fail_on_passing_numbers(self):
        def mutate(e):
            e["metrics"]["rankic_mean"] = 0.5   # clears >= 0.02 easily
            e["metrics"]["quintile_spread"] = 0.1
            e["verdict"] = "fail"
        self.assert_blocked("fib7r", e_mutate=mutate,
                            substring="inconsistent with the pre-registered")

    def test_fib14_partial_metrics(self):
        self.assert_blocked("fib14",
                            e_mutate=lambda e: e["metrics"].pop("quintile_spread"),
                            substring="missing required metric 'quintile_spread'")

    def test_fib15_window_shrink(self):
        start = self.snap.manifest["start"]
        as_of = self.snap.manifest["as_of"]
        mid = str(int(start) + (int(as_of) - int(start)) // 2)
        self.assert_blocked("fib15",
                            e_mutate=lambda e: e.update(window=f"{start}:{mid}"),
                            substring="pre-registered window")

    def test_tampered_snapshot_blocked(self):
        d = self.root / "snap-tampered"
        snapshot.build_snapshot(d, seed=42, tickers=12, days=90)
        h, e = self.write_pair(self.case_dir("tamper"))
        # point the card at the tampered snapshot
        tampered = fingerprint_tampered(d)
        e_doc = json.loads(e.read_text())
        e_doc["snapshot_hash"] = tampered
        e.write_text(json.dumps(e_doc))
        ok, errs = gate(h, e, d)
        self.assertFalse(ok)
        self.assertTrue(any("tampered" in x for x in errs), errs)


def fingerprint_tampered(d: Path) -> str:
    """Break the data file, return the (now stale) manifest hash."""
    from qsa.snapshot import canonical_json, sha256_bytes
    manifest = json.loads((d / "MANIFEST.json").read_text())
    manifest_hash = sha256_bytes(canonical_json(manifest))
    csv = d / "daily" / "prices.csv"
    csv.write_text(csv.read_text().replace("100.0", "777.7", 1))
    return manifest_hash


class TestSchemaRouting(GateBase):
    def test_unregistered_schema_type_fails(self):
        d = self.case_dir("unregistered")
        (d / "X.json").write_text(json.dumps({"schema": "vibes", "data": "🤞"}))
        from qsa.validate import validate_card
        errs = validate_card(json.loads((d / "X.json").read_text()), "X.json")
        self.assertTrue(any("not registered" in x for x in errs), errs)

    def test_schema_only_cli_mode(self):
        from qsa.verify import main
        h, e = self.write_pair(self.case_dir("cli"))
        self.assertEqual(main(["verify.py", str(h)]), 0)
        bad = self.case_dir("cli") / "bad.json"
        bad.write_text(json.dumps({"schema": "experiment_result"}))
        self.assertEqual(main(["verify.py", str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
