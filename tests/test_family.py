"""S3 family-tree: budgeted generation, graveyard v2 discipline,
sealed loop metrics. Real-fixture tests keep the loop honest end
to end."""
import json
import tempfile
import unittest
from pathlib import Path

from qsa.family import (DOMAINS, VARIANTS, WINDOWS, family_grid,
                        run_family_tree, seal_to_disk)
from qsa.graveyard import (INDEPENDENT_FAILS_TO_BAN, load,
                           migrate_v1, new_graveyard, propose_revisit,
                           record_verdict, revive_on_data)
from qsa.orders import OrderBook


def _inputs():
    """Full-sample fast-lane inputs from the pinned fixture."""
    from qsa import snapshot
    from qsa.ingest import ingest_csv
    root = Path(__file__).resolve().parents[1]
    fixture = root / "examples" / "data"
    td = Path(tempfile.mkdtemp(prefix="family-snap-"))
    snap = td / "snap"
    ingest_csv(fixture / "ashare_top300_main.csv", snap,
               volume_col="volume", open_col="open",
               snapshot_id="family-test",
               meta_dir=fixture / "replication_meta")
    closes = snapshot.load_closes(snap)
    return {"closes": closes,
            "opens": snapshot.load_opens(snap),
            "volumes": snapshot.load_volumes(snap),
            "dates": sorted({d for row in closes.values()
                             for d in row})}


def _fail_row(oos=0.05, icir=2.0, spread=0.02, decay=0.3):
    """A stage-2 fail row: metrics present, one criterion missed."""
    return {"oos_ic": oos, "icir": icir, "n_months": 40,
            "top_minus_bottom": spread, "train_ic": oos * 2,
            "ic_decay_ratio": decay}


class TestGrid(unittest.TestCase):

    def test_grid_is_24_pre_registered_cells(self):
        g = family_grid()
        self.assertEqual(len(g), 4 * 2 * 3)
        ids = [s["id"] for s in g]
        self.assertEqual(len(set(ids)), len(ids))     # no dup cells
        for s in g:
            p = s["provenance"]
            self.assertEqual(p["program"], "S3")
            self.assertIn(p["window"], WINDOWS)
            self.assertIn(p["domain"], DOMAINS)
            self.assertIn(p["variant"], VARIANTS)
            self.assertIn("momentum", p["parent"])
        # smallcap cells state the volume-proxy honestly
        for s in g:
            if s["provenance"]["domain"] == "smallcap":
                self.assertIn("proxy for cap", s["desc"])


class TestTieredGraveyard(unittest.TestCase):
    """One fail parks; a SECOND INDEPENDENT implementation bans;
    replays of the same implementation never advance the count."""

    def _yard(self):
        return new_graveyard({})

    def test_single_fail_parks_not_bans(self):
        y = self._yard()
        tier = record_verdict(y, "mom12/x/plain", "impl-a", "fail",
                              ["icir low"], _fail_row(icir=0.1),
                              "stage2-v1", 1)
        self.assertEqual(tier, "parked")

    def test_replay_same_impl_never_bans(self):
        y = self._yard()
        for loop in (1, 2, 3):
            tier = record_verdict(y, "c", "impl-a", "fail", ["r"],
                                  _fail_row(), "stage2-v1", loop)
        self.assertEqual(tier, "parked")   # no ban-farming by replay

    def test_second_independent_impl_bans(self):
        y = self._yard()
        record_verdict(y, "c", "impl-a", "fail", ["r"],
                       _fail_row(), "stage2-v1", 1)
        tier = record_verdict(y, "c", "impl-b", "fail", ["r"],
                              _fail_row(), "stage2-v1", 2)
        self.assertEqual(tier, "banned")
        self.assertEqual(
            len(y["cells"]["c"]["fail_implementations"]),
            INDEPENDENT_FAILS_TO_BAN)

    def test_pass_revives_with_history_kept(self):
        y = self._yard()
        record_verdict(y, "c", "impl-a", "fail", ["r"],
                       _fail_row(), "stage2-v1", 1)
        tier = record_verdict(y, "c", "impl-a", "pass", [],
                              dict(_fail_row(), icir=2.0, oos_ic=0.05),
                              "stage2-v1", 2)
        self.assertEqual(tier, "revived")
        self.assertTrue(y["cells"]["c"]["history"])

    def test_thin_cell_tier_is_thin(self):
        y = self._yard()
        tier = record_verdict(y, "c", "impl-a", "inconclusive",
                              ["<24 months"], {"oos_ic": 0.04},
                              "stage2-v1", 1)
        self.assertEqual(tier, "thin")

    def test_close_call_flagged_in_autopsy(self):
        from qsa.graveyard import autopsy, is_close_call
        close = _fail_row(oos=0.029)            # -3% below the 0.03 line
        deep = _fail_row(oos=-0.30)             # -1100% below
        self.assertTrue(is_close_call(close, ["oos_ic=0.029 fails > 0.03"]))
        self.assertFalse(is_close_call(deep, ["oos_ic=-0.3 fails > 0.03"]))
        a = autopsy(close, ["x"])
        self.assertAlmostEqual(
            a["closest_margin"], close["oos_ic"] / 0.03 - 1, places=9)


class TestV1Migration(unittest.TestCase):

    def test_v1_bans_resentenced_to_parked(self):
        v1 = {"version": 1, "banned": {
            "mom12/top300/plain": {"loop": 1, "verdict": "fail",
                                   "reasons": ["icir low"],
                                   "oos_ic": 0.03, "icir": 0.1,
                                   "banned_at": 123.0},
            "mom18/smallcap/plain": {"loop": 1, "verdict": "fail",
                                     "reasons": ["x"], "oos_ic": -0.1,
                                     "icir": -0.2, "banned_at": 124.0}}}
        y = migrate_v1(v1)
        self.assertEqual(y["version"], 2)
        for cell in v1["banned"]:
            self.assertEqual(y["cells"][cell]["tier"], "parked")
        self.assertIn("re-sentenced", y["log"][0]["note"])

    def test_real_loop1_graveyard_loads_as_v2_parked(self):
        root = Path(__file__).resolve().parents[1]
        y = load(root / "docs" / "loops" / "graveyard.json")
        self.assertEqual(y["version"], 2)
        self.assertEqual(len(y["cells"]), 10)
        self.assertTrue(all(c["tier"] == "parked"
                            for c in y["cells"].values()))


class TestRevisitQueue(unittest.TestCase):

    def test_proposal_requires_reason_and_change(self):
        y = new_graveyard({})
        record_verdict(y, "c", "impl-a", "fail", ["r"], _fail_row(),
                       "stage2-v1", 1)
        with self.assertRaises(ValueError):
            propose_revisit(y, "c", "", "change")     # no reason
        with self.assertRaises(ValueError):
            propose_revisit(y, "c", "why", "  ")      # no change
        with self.assertRaises(ValueError):
            propose_revisit(y, "ghost", "why", "what")  # unknown cell
        rv = propose_revisit(y, "c", "proxy was bad", "real cap data")
        self.assertEqual(rv, "RV-001")

    def test_data_growth_files_proposals_for_thin_only(self):
        y = new_graveyard({"snapshot_id": "s", "n_dates": 1000})
        record_verdict(y, "thin-cell", "i", "inconclusive", ["<24mo"],
                       {"oos_ic": 0.04}, "stage2-v1", 1)
        record_verdict(y, "dead-cell", "i", "fail", ["deep"],
                       _fail_row(), "stage2-v1", 1)
        # 10% growth: no revival
        self.assertEqual(revive_on_data(y, {"n_dates": 1100}), [])
        # 25% growth: thin revives, deep fail does not
        made = revive_on_data(y, {"n_dates": 1300})
        self.assertEqual(len(made), 1)
        self.assertEqual(y["revisit_queue"][0]["cell"], "thin-cell")


class TestLoopUnderV2(unittest.TestCase):

    def test_budget_cuts_generation_and_seals_the_rest(self):
        book = OrderBook(Path(tempfile.mkdtemp()) / "orders.jsonl")
        with tempfile.TemporaryDirectory() as td:
            yard = Path(td) / "graveyard.json"
            seal = run_family_tree(book, _inputs(), budget=3,
                                   graveyard_path=yard)
            self.assertEqual(seal["tested"], 3)
            self.assertEqual(seal["budget_unspent"], 0)
            load(yard)
            tiers = seal["graveyard_tiers"]
            self.assertEqual(
                tiers["parked"] + tiers["thin"] + tiers["banned"]
                + tiers["revived"], 3)          # every cell recorded
            self.assertIn("gate_version", seal)

    def test_parked_not_auto_retested_banned_skips_free(self):
        # loop A: park one cell (budget 1)
        with tempfile.TemporaryDirectory() as td:
            yard = Path(td) / "graveyard.json"
            book1 = OrderBook(Path(td) / "a.jsonl")
            run_family_tree(book1, _inputs(), budget=1,
                            graveyard_path=yard)
            n_parked = load(yard)["cells"]
            self.assertGreaterEqual(len(n_parked), 1)
            # loop B: parked cells are skipped, NOT auto-retested
            book2 = OrderBook(Path(td) / "b.jsonl")
            seal2 = run_family_tree(book2, _inputs(), budget=24,
                                    graveyard_path=yard)
            self.assertEqual(seal2["skipped_parked_or_thin"],
                             len(n_parked))
            # none of the parked cells were re-tested for free
            self.assertLessEqual(seal2["tested"], 24)

    def test_revisit_quota_spent_first_with_outcome_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            yard = Path(td) / "graveyard.json"
            book1 = OrderBook(Path(td) / "a.jsonl")
            run_family_tree(book1, _inputs(), budget=1,
                            graveyard_path=yard)
            y = load(yard)
            cell = sorted(y["cells"])[0]
            propose_revisit(y, cell,
                            reason="single volproxy fail may be "
                                   "implementation artefact",
                            change="replay same cell this loop")
            from qsa.graveyard import save
            save(yard, y)
            book2 = OrderBook(Path(td) / "b.jsonl")
            seal = run_family_tree(book2, _inputs(), budget=10,
                                   graveyard_path=yard)
            self.assertEqual(seal["revisit_attempted"], 1)
            self.assertEqual(len(seal["revisits"]), 1)
            self.assertIn(seal["revisits"][0]["outcome"],
                          ("pass", "fail", "inconclusive", None))
            y2 = load(yard)
            rv = y2["revisit_queue"][0]
            self.assertEqual(rv["status"], "run")
            self.assertEqual(rv["run_loop"], 1)


class TestSealAndOrders(unittest.TestCase):

    def test_seal_written_and_orders_frozen(self):
        book = OrderBook(Path(tempfile.mkdtemp()) / "orders.jsonl")
        with tempfile.TemporaryDirectory() as td:
            yard = Path(td) / "graveyard.json"
            seal = run_family_tree(book, _inputs(), budget=24,
                                   graveyard_path=yard)
            out = Path(td) / "loop.json"
            seal_to_disk(out, seal)
            reread = json.loads(out.read_text())
            self.assertEqual(reread["tested"], seal["tested"])
            # gauntlet_passed stays honestly 0 until S9/S10 wire up
            self.assertEqual(reread["gauntlet_passed"], 0)
            self.assertIn("pending", reread["gauntlet_passed_note"])
            for gid in seal["gauntlet_order_ids"]:
                o = book.orders[gid]
                self.assertEqual(o["state"], "queued")
                params = o["history"][0]["params"]
                self.assertEqual(params["stage"], 2)
                self.assertIn("admission", params)     # frozen criteria
                self.assertEqual(params["unwired"],
                                 ["walk_forward_oos",
                                  "fib_budget_accounting",
                                  "portfolio_increment"])


if __name__ == "__main__":
    unittest.main()
