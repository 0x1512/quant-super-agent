"""Tests for the crew plane (SUPERAGENT_PLAN #5).

The session card is a STRICT SUPERSET of the numeric rows: the rows
survive verbatim (nothing dropped), and the card adds role, job keys
and checkpoint accounting. Acceptance is mechanical:

* card["rows"] == the stream's return value, row for row;
* one job key per job — equal to the manifest's jobs_by_kind count;
* reconcile() finds zero discrepancies on a real run's artifacts.
"""
import random
import tempfile
import unittest
from pathlib import Path

from qsa import checkpoint, crew, dispatch


def panels(seed: int = 11, n_tk: int = 12, n_dates: int = 160):
    rng = random.Random(seed)
    dates = [f"2024{1 + i // 28:02d}{1 + i % 28:02d}" for i in range(n_dates)]
    tks = [f"T{i:03d}" for i in range(n_tk)]
    closes = {tk: {d: rng.random() * 10 + 5 for d in dates} for tk in tks}
    opens = {tk: {d: v - rng.random() * 0.1 for d, v in
                  closes[tk].items()} for tk in tks}
    volumes = {tk: {d: rng.random() * 1e6 for d in dates} for tk in tks}
    return closes, opens, volumes, dates


class TestRecordAndReconcile(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-crew-"))
        self.addCleanup(self._rm)

    def _rm(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_card_is_superset_of_rows(self):
        jobs = [("zoo", 0), ("zoo", 1), ("zoo", 2)]
        rows = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        card = crew.record(self.tmp / "crew", "zoo", jobs, rows,
                           {"checkpoint_hits": 0})
        self.assertEqual(card["rows"], rows)          # rows verbatim
        self.assertEqual(card["role"], "GateKeeper")  # attribution added
        self.assertEqual(card["n_jobs"], card["n_rows"], 3)
        self.assertEqual(len(set(card["job_keys"])), 3)
        # persisted and readable
        again = crew.sessions(self.tmp / "crew")
        self.assertEqual(again["zoo"]["rows"], rows)

    def test_reconcile_detects_every_discrepancy(self):
        crew.record(self.tmp / "crew", "zoo", [("zoo", i) for i in range(4)],
                    [{"i": i} for i in range(4)])
        # manifest agrees -> clean
        self.assertEqual(crew.reconcile(
            self.tmp / "crew", {"jobs_by_kind": {"zoo": 4, "forge": 2}}),
            [])
        # manifest disagrees -> flagged
        bad = crew.reconcile(self.tmp / "crew",
                             {"jobs_by_kind": {"zoo": 5}})
        self.assertEqual(len(bad), 1)
        self.assertIn("zoo", bad[0])
        # card without a manifest entry -> flagged
        crew.record(self.tmp / "crew", "lib", [("lib", 0)], [{"i": 0}])
        bad = crew.reconcile(self.tmp / "crew",
                             {"jobs_by_kind": {"zoo": 4}})
        self.assertEqual(len(bad), 1)
        self.assertIn("lib", bad[0])

    def test_torn_card_is_skipped_not_fatal(self):
        d = self.tmp / "crew"
        d.mkdir(parents=True)
        (d / "zoo.json").write_text('{"kind": "zo', encoding="utf-8")
        self.assertEqual(crew.sessions(d), {})
        self.assertEqual(crew.reconcile(d, {"jobs_by_kind": {}}), [])


class TestStreamIntegration(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-crew2-"))
        self.addCleanup(self._rm)
        self.closes, self.opens, self.volumes, self.dates = panels()

    def _rm(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_zoo_leaves_a_matching_session_card(self):
        ref = dispatch.zoo(self.closes, self.opens, self.volumes,
                           self.dates, workers=2)
        crew_dir = self.tmp / "crew"
        ck = checkpoint.Checkpoint(self.tmp / "ck", "fp")
        got = dispatch.zoo(self.closes, self.opens, self.volumes,
                           self.dates, workers=2, ckpt=ck, crew_dir=crew_dir)
        self.assertEqual(got, ref)
        card = crew.sessions(crew_dir)["zoo"]
        self.assertEqual(card["rows"], ref)            # rows verbatim
        self.assertEqual(card["role"], "GateKeeper")
        self.assertEqual(card["n_jobs"], len(ref))
        self.assertEqual(card["meta"]["checkpoint_misses"], len(ref))
        # warm second pass: same card content, all hits this time
        dispatch.zoo(self.closes, self.opens, self.volumes,
                     self.dates, workers=2, ckpt=ck, crew_dir=crew_dir)
        card2 = crew.sessions(crew_dir)["zoo"]
        self.assertEqual(card2["rows"], ref)
        self.assertEqual(card2["meta"]["checkpoint_hits"], len(ref))
        self.assertEqual(card2["meta"]["checkpoint_misses"], 0)
        # and it reconciles against a manifest built from the same counts
        self.assertEqual(crew.reconcile(
            crew_dir, {"jobs_by_kind": {"zoo": len(ref)}}), [])


if __name__ == "__main__":
    unittest.main()
