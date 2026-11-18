"""Funnel + stage-2 tests — ALPHA_PLAN S1/S6 acceptance, pinned.

S6: the composite gate refuses decayed/thin/short rows mechanically,
each failure named; a strong row passes with the criteria echoed.
S1: promotion is exactly-once, criteria frozen at admission, gauntlet
work queued LOW, and nothing but fast-lane survivors promotes.
Plus the integration truth: the REAL catalog rows from the fast lane
split under stage-2 (some pass, some fail) — the funnel is what makes
"15 settled" an honest funnel input instead of a vanity number.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa.admission import STAGE2_ADMISSION, stage2_verdict  # noqa: E402
from qsa.funnel import promote, promoted_from               # noqa: E402
from qsa.orders import OrderBook, OrderError                # noqa: E402

STRONG = {"oos_ic": 0.073, "icir": 1.9, "n_months": 30,
          "top_minus_bottom": 0.06, "train_ic": 0.10}


class TestStage2(unittest.TestCase):
    def test_strong_row_passes_with_criteria_echoed(self):
        v, reasons = stage2_verdict(STRONG)
        self.assertEqual(v, "pass")
        self.assertIn("pre-registered thresholds satisfied", reasons[0])

    def test_decayed_row_fails_with_both_reasons_named(self):
        v, reasons = stage2_verdict(dict(STRONG, oos_ic=0.01))
        self.assertEqual(v, "fail")
        self.assertTrue(any(r.startswith("oos_ic=") for r in reasons))
        self.assertTrue(any(r.startswith("ic_decay_ratio=") for r in reasons))

    def test_thin_and_negative_spread_fail(self):
        self.assertEqual(stage2_verdict(dict(STRONG, icir=0.8))[0], "fail")
        self.assertEqual(
            stage2_verdict(dict(STRONG, top_minus_bottom=-0.02))[0], "fail")

    def test_short_sample_is_inconclusive_never_a_call(self):
        v, _ = stage2_verdict(dict(STRONG, n_months=12))
        self.assertEqual(v, "inconclusive")

    def test_missing_metric_is_none_not_a_guess(self):
        row = dict(STRONG)
        del row["icir"]
        self.assertIsNone(stage2_verdict(row)[0])


class TestPromote(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-funnel-"))
        self.book = OrderBook(self.tmp / "orders.jsonl")

    def _fastlane(self, verdict="survivor (fast lane; "
                  "gauntlet still required)") -> str:
        oid = self.book.create("mom gap beats random",
                               {"factor": "mom_gap_12m", "thresh": 0.03})
        self.book.admit(oid, {"factor": "mom_gap_12m", "thresh": 0.03})
        self.book.start(oid)
        self.book.settle(oid, {**STRONG, "verdict": verdict})
        return oid

    def test_promotion_freezes_criteria_and_queues_low(self):
        oid = self._fastlane()
        gid = promote(self.book, oid, priority=7)
        g = self.book.orders[gid]
        self.assertEqual(g["state"], "queued")
        self.assertEqual(g["history"][0]["params"]["promoted_from"], oid)
        # the stage-2 criteria were frozen AT promotion (pre-registration
        # with teeth: running with different criteria is detectable)
        frozen = g["history"][0]["params"]["admission"]
        self.assertEqual(frozen["thresholds"],
                         STAGE2_ADMISSION["thresholds"])
        self.assertIn("portfolio_increment",
                      g["history"][0]["params"]["gauntlet_checks"])
        # honest wiring status is ON the order, not in a README
        self.assertIn("walk_forward_oos",
                      g["history"][0]["params"]["unwired"])
        self.assertEqual(g["history"][0]["priority"], 7)
        # the original stays settled and untouched
        self.assertEqual(self.book.orders[oid]["state"], "settled")
        # replay sees the whole funnel hop
        book2 = OrderBook(self.tmp / "orders.jsonl")
        self.assertEqual(promoted_from(book2, oid), gid)

    def test_double_promotion_is_refused(self):
        oid = self._fastlane()
        promote(self.book, oid)
        with self.assertRaises(OrderError) as cm:
            promote(self.book, oid)
        self.assertIn("exactly once", str(cm.exception))
        self.assertEqual(len(self.book.by_state("queued")), 1)

    def test_only_fast_lane_survivors_promote(self):
        refused = self.book.create("dead idea", {"x": 1})
        self.book.admit(refused, {"x": 1})
        self.book.refuse(refused, "oos dead")
        with self.assertRaises(OrderError):
            promote(self.book, refused)
        full = self.book.create("already gauged", {"x": 2})
        self.book.admit(full, {"x": 2})
        self.book.start(full)
        self.book.settle(full, {"verdict": "gauntlet passed",
                                **STRONG})
        with self.assertRaises(OrderError):
            promote(self.book, full)
        live = self.book.create("still running", {"x": 3})
        self.book.admit(live, {"x": 3})
        self.book.start(live)
        with self.assertRaises(OrderError):
            promote(self.book, live)


class TestRealCatalogIntegration(unittest.TestCase):
    """Real fast-lane rows through stage-2 — the funnel's input truth."""

    def test_first_three_factors_judged_on_real_fixture(self):
        from qsa import factorzoo, snapshot
        from qsa.ingest import ingest_csv
        root = Path(__file__).resolve().parents[1]
        fixture = root / "examples" / "data"
        with tempfile.TemporaryDirectory(prefix="funnel-snap-") as td:
            snap = Path(td) / "snap"
            ingest_csv(fixture / "ashare_top300_main.csv", snap,
                       volume_col="volume", open_col="open",
                       snapshot_id="funnel-test",
                       meta_dir=fixture / "replication_meta")
            closes = snapshot.load_closes(snap)
            opens = snapshot.load_opens(snap)
            volumes = snapshot.load_volumes(snap)
            dates = sorted({d for row in closes.values() for d in row})
            keep = set(dates[:300])
            inputs = {"closes": {tk: {d: v for d, v in row.items()
                                      if d in keep}
                                 for tk, row in closes.items()},
                      "opens": {tk: {d: v for d, v in row.items()
                                    if d in keep}
                                for tk, row in opens.items()},
                      "volumes": {tk: {d: v for d, v in row.items()
                                      if d in keep}
                                  for tk, row in volumes.items()},
                      "dates": dates[:300]}
            verdicts = {}
            for spec in factorzoo.build_catalog()[:3]:
                row = factorzoo.evaluate_factor(spec, inputs)
                v, reasons = stage2_verdict(row)
                assert v in ("pass", "fail", "inconclusive"), reasons
                verdicts[spec["id"]] = v
            # the mechanical claim pinned: every row gets a REAL stage-2
            # verdict from real numbers (0 passers would be legal too —
            # ALPHA_PLAN decision 1; what is illegal is no verdict)
            self.assertEqual(len(verdicts), 3)


if __name__ == "__main__":
    unittest.main()
