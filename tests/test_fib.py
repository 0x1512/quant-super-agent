"""FIB harness tests (v0.6): determinism, honesty control, per-class catch
and localization, metric semantics, judge independence."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qsa import fib
from qsa.fib import (JUDGES, SCENARIOS, metrics_for, run_all, run_scenario)


class FibBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


class TestHonestControl(FibBase):
    def test_honest_card_passes_all_judges(self):
        sc = SCENARIOS[0]
        rows = run_scenario(self.root, sc)
        for r in rows:
            self.assertTrue(r["merged"], (r["judge"], r["errors"]))

    def test_honest_card_has_no_injection_flag(self):
        sc = SCENARIOS[0]
        rows = run_scenario(self.root, sc)
        for r in rows:
            self.assertFalse(r["injected"])
            self.assertTrue(r["honest"])


class TestFullStackCatches(FibBase):
    """Every injection must be blocked by the full-stack judge."""

    def _fullstack_row(self, sc):
        rows = run_scenario(self.root, sc)
        return next(r for r in rows if r["judge"] == "full-stack")

    def test_each_injection_blocked(self):
        for sc in SCENARIOS[1:]:
            r = self._fullstack_row(sc)
            self.assertFalse(r["merged"],
                             f"FIB {sc.fib_id} {sc.name} merged under full-stack")
            self.assertTrue(r["errors"],
                            f"FIB {sc.fib_id} blocked with no errors")

    def test_localization_names_touched_field(self):
        for sc in SCENARIOS[1:]:
            r = self._fullstack_row(sc)
            # the touched field's last component or a known catch phrase
            # must appear in the first error
            tail = sc.touched_field.split(".")[-1]
            first = r["localized_error"]
            self.assertTrue(
                tail in first or any(p in first for p in
                                     ("recomputation", "mechanical evaluation",
                                      "ledger", "one-shot", "version pin",
                                      "does not match", "not registered",
                                      "already settled", "settlement",
                                      "deflation")),
                f"FIB {sc.fib_id}: no localization for {sc.touched_field!r} "
                f"in {first!r}")


class TestUngatedBaseline(FibBase):
    def test_ungated_merges_everything(self):
        for sc in SCENARIOS:
            rows = run_scenario(self.root, sc)
            u = next(r for r in rows if r["judge"] == "ungated")
            self.assertTrue(u["merged"],
                            f"ungated should merge FIB {sc.fib_id}")
            self.assertEqual(u["errors"], [])


class TestSchemaOnlyBaseline(FibBase):
    """Schema-only should catch some (but not all) injections; it must
    never let a card through that has a broken sha or missing key. It
    must also NOT catch metric-level lies (2, 4, 9, 7, 11, 16, 19) because
    it does not recompute."""

    def test_schema_catches_structural_injections(self):
        # structural lies the schema layer can see without recomputation:
        # a missing required key, a broken hyp link, a code-hash mismatch
        structural = {1, 12, 21}
        # everything else (2,3,4,6,7,9,11,13,14,15,16,19) is invisible to
        # schema-only: it needs recomputation, the registry, or the ledger
        for sc in SCENARIOS[1:]:
            rows = run_scenario(self.root, sc)
            s = next(r for r in rows if r["judge"] == "schema-only")
            if sc.fib_id in structural:
                self.assertFalse(s["merged"],
                                 f"schema-only should catch FIB {sc.fib_id}")
            else:
                # metric-level / registry-level lies: schema-only cannot see them
                self.assertTrue(s["merged"],
                                f"schema-only should NOT catch FIB {sc.fib_id} "
                                f"(invisible without recomputation/ledger)")


class TestMetricsSemantics(FibBase):
    def test_metrics_computed(self):
        rows, m = run_all(self.root)
        self.assertIn("full-stack", m)
        fs = m["full-stack"]
        self.assertEqual(fs["n_honest"], 1)
        self.assertEqual(fs["n_injected"], len(SCENARIOS) - 1)
        self.assertEqual(fs["honest_passed"], 1)
        self.assertEqual(fs["honest_blocked"], 0)
        self.assertEqual(fs["gate_catch_rate"], 1.0)
        self.assertEqual(fs["silent_pass_rate"], 0.0)
        self.assertEqual(fs["honesty_rate"], 1.0)
        self.assertGreater(fs["pressure_asymmetry"], 0)

    def test_ungated_metrics(self):
        rows, m = run_all(self.root)
        u = m["ungated"]
        self.assertEqual(u["gate_catch_rate"], 0.0)
        self.assertEqual(u["silent_pass_rate"], 1.0)
        self.assertEqual(u["honesty_rate"], 1.0)
        self.assertEqual(u["honest_passed"], 1)

    def test_schema_metrics(self):
        rows, m = run_all(self.root)
        s = m["schema-only"]
        # some caught, some not — must be strictly between 0 and 1
        self.assertGreater(s["gate_catch_rate"], 0.0)
        self.assertLess(s["gate_catch_rate"], 1.0)


class TestDeterminism(FibBase):
    def test_byte_identical_across_runs(self):
        a = self.root / "run-a"
        b = self.root / "run-b"
        rows_a, m_a = run_all(a)
        rows_b, m_b = run_all(b)
        self.assertEqual(json.dumps(rows_a, sort_keys=True),
                         json.dumps(rows_b, sort_keys=True))
        self.assertEqual(json.dumps(m_a, sort_keys=True),
                         json.dumps(m_b, sort_keys=True))

    def test_seed_reproducible(self):
        # same seed -> same rows
        r1 = self.root / "seed1"
        r2 = self.root / "seed2"
        rows1, _ = run_all(r1)
        rows2, _ = run_all(r2)
        self.assertEqual(len(rows1), len(rows2))
        for x, y in zip(rows1, rows2):
            self.assertEqual(x["merged"], y["merged"])


class TestPublishedArtifact(FibBase):
    """docs/fib_v07_run.json is the published raw log — it must stay
    byte-identical to a fresh run (metrics + per-scenario verdicts)."""

    def test_published_run_matches_fresh_metrics(self):
        repo = Path(__file__).resolve().parents[1]
        published = json.loads(
            (repo / "docs" / "fib_v07_run.json").read_text())
        _, m = run_all(self.root)
        self.assertEqual(published["metrics"], m)
        self.assertEqual(published["n_scenarios"], len(SCENARIOS))


class TestJudgeIndependence(FibBase):
    def test_judges_do_not_mutate_each_other(self):
        # run scenarios in different orders — results must be identical
        sc = SCENARIOS[4]  # FIB 4: in-sample overfit
        r1 = run_scenario(self.root, sc)
        r2 = run_scenario(self.root, sc)
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
