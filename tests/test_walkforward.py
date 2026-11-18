"""S9 walk-forward gauntlet: rolling decay trigger, block half-life,
consistency — and the gauntlet executor settling real orders."""
import random
import tempfile
import unittest
from pathlib import Path

from qsa.admission import STAGE2_ADMISSION
from qsa.funnel import promote
from qsa.orders import OrderBook
from qsa.walkforward import (MIN_BLOCKS, WALKFORWARD_ADMISSION,
                             block_means, rolling_decay,
                             run_gauntlet, walkforward_verdict)


def _series(ics, year0=2020):
    out = []
    y, m = year0, 1
    for v in ics:
        out.append({"date": f"{y}-{m:02d}-01", "ic": v})
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _stable(n=48, mu=0.06, sd=0.04, seed=7):
    rng = random.Random(seed)
    return _series([rng.gauss(mu, sd) for _ in range(n)])


class TestBlocksAndTrigger(unittest.TestCase):

    def test_block_means_cut_half_years(self):
        s = _series([0.1] * 6 + [0.3] * 6 + [-0.1] * 6)
        means = block_means(s)
        self.assertEqual(len(means), 3)
        for got, want in zip(means, (0.1, 0.3, -0.1)):
            self.assertAlmostEqual(got, want, places=9)

    def test_rolling_decay_finds_negative_windows_only(self):
        s = _series([0.05] * 12 + [-0.2] * 14 + [0.05] * 12)
        fired = rolling_decay(s)
        self.assertTrue(fired)
        for f in fired:
            self.assertLess(f["mean_ic"], 0)
        # a clean series fires nothing
        self.assertEqual(rolling_decay(_stable()), [])


class TestVerdicts(unittest.TestCase):

    def test_stable_positive_series_passes(self):
        v, d = walkforward_verdict(_stable())
        self.assertEqual(v, "pass")
        self.assertEqual(d["n_decay_triggers"], 0)
        self.assertGreaterEqual(d["half_life_ratio"], 0.5)

    def test_locally_dead_series_fails_with_trigger_log(self):
        s = _stable()
        for i in range(18, 32):
            s[i]["ic"] = -0.08
        v, d = walkforward_verdict(s)
        self.assertEqual(v, "fail")
        self.assertGreater(d["n_decay_triggers"], 0)
        self.assertIn("locally dead", d["reason"])

    def test_front_loaded_decay_fails_half_life(self):
        # strong first half, weak-but-positive second half (no trigger)
        s = _series([0.20] * 24 + [0.01] * 24)
        v, d = walkforward_verdict(s)
        self.assertEqual(v, "fail")
        self.assertIn("half-life", d["reason"])

    def test_inconsistent_blocks_fail_consistency(self):
        # mild negative blocks, strong close: the 12m rolling trigger
        # never fires and half-life holds, but 2 of 6 blocks are
        # negative — a consistency fail, not a decay or half-life one
        # 42 months, 7 blocks, 3 negative (never adjacent: no 12m
        # trigger) and a strong tail (half-life holds) — the verdict
        # must come from consistency, nowhere else
        blocks = ([-0.01] * 6, [0.3] * 6, [-0.01] * 6, [0.3] * 6,
                  [-0.01] * 6, [0.3] * 6, [0.3] * 6)
        s = _series([v for b in blocks for v in b])
        v, d = walkforward_verdict(s)
        self.assertEqual(v, "fail")
        self.assertIn("consistency", d["reason"])
        self.assertEqual(d["n_decay_triggers"], 0)
        self.assertEqual(d["positive_blocks"], "4/7")
        self.assertGreaterEqual(d["half_life_ratio"], 0.5)

    def test_thin_sample_is_inconclusive(self):
        v, d = walkforward_verdict(_stable(n=30))
        self.assertEqual(v, "inconclusive")
        self.assertIn(f"< {MIN_BLOCKS}", d["reason"])

    def test_admission_is_pre_registered_constant(self):
        self.assertEqual(WALKFORWARD_ADMISSION["min_blocks"], MIN_BLOCKS)
        self.assertEqual(WALKFORWARD_ADMISSION["rolling_decay_rule"],
                         "rolling 12m IC mean < 0 -> locally dead")


def _inputs():
    from qsa import snapshot
    from qsa.ingest import ingest_csv
    root = Path(__file__).resolve().parents[1]
    fixture = root / "examples" / "data"
    td = Path(tempfile.mkdtemp(prefix="wf-snap-"))
    snap = td / "snap"
    ingest_csv(fixture / "ashare_top300_main.csv", snap,
               volume_col="volume", open_col="open",
               snapshot_id="wf-test",
               meta_dir=fixture / "replication_meta")
    closes = snapshot.load_closes(snap)
    return {"closes": closes,
            "opens": snapshot.load_opens(snap),
            "volumes": snapshot.load_volumes(snap),
            "dates": sorted({d for row in closes.values()
                             for d in row})}


def _settled_fast_lane_book(inputs):
    """A book with one settled fast-lane survivor (real fixture,
    300-day window) ready to promote — the S9 demo's own front half."""
    from qsa import factorzoo
    book = OrderBook(Path(tempfile.mkdtemp()) / "orders.jsonl")
    dates = inputs["dates"][:300]
    keep = set(dates)

    def cut(panel):
        return {tk: {d: v for d, v in row.items() if d in keep}
                for tk, row in panel.items()}
    fast = {"closes": cut(inputs["closes"]),
            "opens": cut(inputs["opens"]),
            "volumes": cut(inputs["volumes"]), "dates": dates}
    spec = factorzoo.build_catalog()[0]        # mom_12_1
    row = factorzoo.evaluate_factor(spec, fast)
    oid = book.create("mom_12_1 carries OOS rank signal on top-300",
                      {"factor": "mom_12_1", "thresh": 0.03,
                       "universe": "top300"}, origin="machine")
    params = {"factor": "mom_12_1", "thresh": 0.03,
              "universe": "top300"}
    book.admit(oid, params)
    book.enqueue(oid)
    book.start(oid)
    if (row.get("oos_ic") or -1) > 0.03:
        book.settle(oid, {k: row.get(k) for k in
                          ("ic_mean", "icir", "oos_ic", "train_ic",
                           "n_months")}
                    | {"verdict": "survivor (fast lane)"})
        return book, oid, spec
    book.refuse(oid, "oos IC below floor in test window")
    return book, None, spec


class TestGauntletExecutor(unittest.TestCase):

    def test_gauntlet_settles_with_precise_verdict_real_fixture(self):
        inputs = _inputs()
        book, oid, spec = _settled_fast_lane_book(inputs)
        if oid is None:                        # window cut missed
            self.skipTest("no fast-lane survivor in first-300d cut")
        gid = promote(book, oid)
        res = run_gauntlet(book, gid, spec, inputs)
        self.assertEqual(book.orders[gid]["state"], "settled")
        self.assertIn(res["verdict"][:8], ("gauntlet",))
        # whatever the verdict, it names its stage precisely
        self.assertTrue(
            res["verdict"].startswith(
                ("gauntlet FAIL at stage-2 recheck",
                 "gauntlet FAIL at walk-forward",
                 "gauntlet: WIRED chain passed")),
            res["verdict"])

    def test_refuses_non_queued_and_unfrozen_orders(self):
        inputs = _inputs()
        book, oid, spec = _settled_fast_lane_book(inputs)
        if oid is None:
            self.skipTest("no fast-lane survivor in first-300d cut")
        gid = promote(book, oid)
        book.start(gid)                        # now running, not queued
        with self.assertRaises(Exception):
            run_gauntlet(book, gid, spec, inputs)
        # unfrozen admission is refused
        book2 = OrderBook(Path(tempfile.mkdtemp()) / "o2.jsonl")
        bad = book2.create("h", {"admission": {"tampered": True}},
                           origin="machine")
        book2.admit(bad, {"admission": {"tampered": True}})
        book2.enqueue(bad)
        with self.assertRaises(Exception):
            run_gauntlet(book2, bad, spec, inputs)

    def test_cheating_oracle_passes_wired_chain(self):
        """A look-ahead oracle factor must pass everything wired —
        the gauntlet is a filter, not a mind-reader; FIB-class
        injections are a separate program (S5/FIB), honestly."""
        inputs = _inputs()
        horizon = 21

        def oracle(inp):
            ds = inp["dates"]
            rows = {}
            for tk, crow in inp["closes"].items():
                out = []
                for i, d in enumerate(ds):
                    j = min(i + horizon, len(ds) - 1)
                    c0, c1 = crow.get(d), crow.get(ds[j])
                    if c0 and c1 and i + horizon < len(ds):
                        out.append(c1 / c0 - 1)
                    else:
                        out.append(None)
                rows[tk] = out
            return rows
        spec = {"id": "test_oracle", "source": "test",
                "desc": "look-ahead oracle (test only)",
                "build": oracle, "flip": False}
        book = OrderBook(Path(tempfile.mkdtemp()) / "o3.jsonl")
        gid = book.create("oracle", {"stage": 2,
                                     "admission": STAGE2_ADMISSION},
                          origin="machine")
        book.admit(gid, {"stage": 2, "admission": STAGE2_ADMISSION})
        book.enqueue(gid)
        res = run_gauntlet(book, gid, spec, inputs)
        self.assertEqual(book.orders[gid]["state"], "settled")
        self.assertEqual(res["stage2_recheck"]["verdict"], "pass")
        self.assertEqual(res["walkforward"]["verdict"], "pass")
        self.assertTrue(res["gauntlet_passed"])
        self.assertIn("unwired", res["verdict"])


if __name__ == "__main__":
    unittest.main()
