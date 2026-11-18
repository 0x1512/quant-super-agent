"""Tests for the checkpoint plane (SUPERAGENT_PLAN #2).

The load-bearing claim: a run interrupted mid-stream and resumed via
``--resume`` produces the SAME rows as an uninterrupted run, in the same
order, and never re-runs a job whose result is already on disk. These
tests pin it four ways:

* store — put/get roundtrip, persistence across instances, fingerprint
  guard (a different plan's cache is never reused), torn-write (crash
  mid-put) treated as a miss, hit/miss accounting exact;
* stitch — resume-after-partial-interruption equals the uninterrupted
  reference, with a mixed hit/miss workload, at the _stitch level;
* stream — dispatch.zoo with a checkpoint equals the no-checkpoint
  reference row for row (determinism contract extends to the resume
  path);
* end-to-end — run_offense.py --resume after deleting half the
  checkpoint files rewrites a byte-identical leaderboard.json and only
  actually runs the missing jobs.
"""
import json
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from qsa import checkpoint, dispatch

ROOT = Path(__file__).resolve().parents[1]


class TestCheckpointStore(unittest.TestCase):
    """The on-disk store: roundtrip, persistence, guards, accounting."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-ckpt-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_roundtrip_and_persistence(self):
        c1 = checkpoint.Checkpoint(self.tmp / "ck", "fp-aaa")
        job = ("zoo", "mom", 5)
        row = {"id": "mom_5", "oos_ic": 0.051}
        self.assertIsNone(c1.get("zoo", job))      # cold: miss
        c1.put("zoo", job, row)
        self.assertEqual(c1.get("zoo", job), row)  # warm: hit
        self.assertEqual((c1.hits, c1.misses), (1, 1))
        # a NEW instance over the same dir (fresh process) still hits
        c2 = checkpoint.Checkpoint(self.tmp / "ck", "fp-aaa")
        self.assertEqual(c2.get("zoo", job), row)
        self.assertEqual((c2.hits, c2.misses), (1, 0))

    def test_fingerprint_guard(self):
        c = checkpoint.Checkpoint(self.tmp / "ck", "fp-aaa")
        job = ("zoo", "mom", 5)
        c.put("zoo", job, {"id": "mom_5"})
        # a different plan fingerprint must NOT reuse the cached row
        other = checkpoint.Checkpoint(self.tmp / "ck", "fp-bbb")
        self.assertIsNone(other.get("zoo", job))
        self.assertEqual((other.hits, other.misses), (0, 1))

    def test_torn_write_is_a_miss(self):
        c = checkpoint.Checkpoint(self.tmp / "ck", "fp-aaa")
        job = ("zoo", "mom", 5)
        p = c._path("zoo", job)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"key": "zoo/mom/5", "fingerprint": "fp-aa',  # torn
                     encoding="utf-8")
        self.assertIsNone(c.get("zoo", job))
        self.assertEqual((c.hits, c.misses), (0, 1))

    def test_kinds_are_namespaced(self):
        c = checkpoint.Checkpoint(self.tmp / "ck", "fp-aaa")
        c.put("zoo", ("j",), {"v": 1})
        c.put("library", ("j",), {"v": 2})
        self.assertEqual(c.get("zoo", ("j",))["v"], 1)
        self.assertEqual(c.get("library", ("j",))["v"], 2)

    def test_key_is_stable_and_does_not_collide(self):
        a = checkpoint.Checkpoint(self.tmp / "a", "fp")
        b = checkpoint.Checkpoint(self.tmp / "b", "fp")
        jobs = [("zoo", f, w) for f in ("mom", "vol", "rev")
                for w in (3, 5, 10, 20)]
        paths = set()
        for j in jobs:
            a.put("zoo", j, {"job": list(j)})
            paths.add(str(a._path("zoo", j)))
        self.assertEqual(len(paths), len(jobs))    # no collisions
        # path derives only from the job -> stable across dirs/plans
        for j in jobs:
            self.assertEqual(a._path("zoo", j).name, b._path("zoo", j).name)
            self.assertEqual(a._path("zoo", j).parent.name, "zoo")

    def test_stats(self):
        c = checkpoint.Checkpoint(self.tmp / "ck", "fp-x")
        c.get("zoo", ("j1",))
        c.put("zoo", ("j1",), {})
        c.get("zoo", ("j1",))
        self.assertEqual(c.stats(), {"hits": 1, "misses": 1,
                                     "fingerprint": "fp-x"})


class TestStitchResume(unittest.TestCase):
    """_stitch: interrupted + resumed == uninterrupted, job for job."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-stitch-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        rng = random.Random(42)
        self.jobs = [("calc", i, rng.random()) for i in range(40)]
        # run_fn is a pure function of the job — the dispatcher contract
        self.calls = []

        def run_fn(todo):
            self.calls.append(list(todo))
            return [{"i": j[1], "r": round(j[1] * 1.5 + j[2], 6)}
                    for j in todo]

        self.run_fn = run_fn

    def test_resume_equals_uninterrupted(self):
        reference = dispatch._stitch(self.jobs, self.run_fn, "calc", None)
        # "interruption": only the first 17 jobs ever completed
        ck = checkpoint.Checkpoint(self.tmp / "ck", "fp")
        partial = dispatch._stitch(self.jobs[:17], self.run_fn, "calc", ck)
        self.assertEqual(partial, reference[:17])
        # "resume": full job list against the same checkpoint
        resumed = dispatch._stitch(self.jobs, self.run_fn, "calc", ck)
        self.assertEqual(resumed, reference)       # identical rows+order
        # call log: full ref, then the partial 17, then only the gap 17..
        self.assertEqual(self.calls, [self.jobs, self.jobs[:17],
                                      self.jobs[17:]])
        # accounting: 17 cached hits, 23 fresh misses on the resume pass
        self.assertEqual((ck.hits, ck.misses), (17, 40))

    def test_all_cached_runs_nothing(self):
        ck = checkpoint.Checkpoint(self.tmp / "ck", "fp")
        dispatch._stitch(self.jobs, self.run_fn, "calc", ck)
        self.assertEqual(len(self.calls), 1)
        again = dispatch._stitch(self.jobs, self.run_fn, "calc", ck)
        self.assertEqual(len(self.calls), 1)       # zero re-runs
        self.assertEqual(again, dispatch._stitch(self.jobs, self.run_fn,
                                                 "calc", None))
        # accounting: 40 misses (cold pass) + 40 hits (warm pass)
        self.assertEqual((ck.hits, ck.misses), (40, 40))

    def test_torn_cache_files_are_rerun(self):
        ck = checkpoint.Checkpoint(self.tmp / "ck", "fp")
        dispatch._stitch(self.jobs, self.run_fn, "calc", ck)
        # simulate a crash mid-put: corrupt three cache files
        files = sorted((self.tmp / "ck" / "calc").glob("*.json"))
        for p in files[:3]:
            p.write_text('{"fingerprint": "fp", "row": {', encoding="utf-8")
        resumed = dispatch._stitch(self.jobs, self.run_fn, "calc", ck)
        self.assertEqual(resumed, dispatch._stitch(self.jobs, self.run_fn,
                                                 "calc", None))
        self.assertEqual(ck.misses, 43)            # 40 + 3 torn


class TestStreamResume(unittest.TestCase):
    """dispatch.zoo through a checkpoint equals the plain reference."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-stream-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        rng = random.Random(11)
        n_dates, n_tk = 160, 12
        self.dates = [f"2024{1+i//28:02d}{1+i%28:02d}" for i in range(n_dates)]
        tks = [f"T{i:03d}" for i in range(n_tk)]
        self.closes = {tk: {d: rng.random() * 10 + 5 for d in self.dates}
                       for tk in tks}
        self.opens = {tk: {d: v - rng.random() * 0.1 for d, v in
                       self.closes[tk].items()} for tk in tks}
        self.volumes = {tk: {d: rng.random() * 1e6 for d in self.dates}
                        for tk in tks}

    def test_zoo_resume_equals_reference(self):
        ref = dispatch.zoo(self.closes, self.opens, self.volumes,
                           self.dates, workers=2)
        ck = checkpoint.Checkpoint(self.tmp / "ck", "fp")
        # interruption: the first run populated the checkpoint, then the
        # process died before writing any artifacts
        dispatch.zoo(self.closes, self.opens, self.volumes,
                     self.dates, workers=2, ckpt=ck)
        # crash: half the on-disk job results are lost
        files = sorted((self.tmp / "ck" / "zoo").glob("*.json"))
        self.assertGreater(len(files), 4)
        for p in files[: len(files) // 2]:
            p.unlink()
        # resume: full stream through the surviving checkpoint
        got = dispatch.zoo(self.closes, self.opens, self.volumes,
                           self.dates, workers=2, ckpt=ck)
        self.assertEqual(got, ref)
        self.assertGreater(ck.misses, 0)
        self.assertGreater(ck.hits, 0)


class TestEndToEndResume(unittest.TestCase):
    """run_offense.py --resume rewrites a byte-identical leaderboard.

    Smoke-scale end-to-end: run once to populate the checkpoint, delete
    half the cached job files (simulating a crash mid-run), re-run with
    --resume in the same work dir, and require leaderboard.json to be
    byte-identical to the first (uninterrupted) write.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-e2e-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.work = self.tmp / "offense"

    def _run(self, *extra):
        r = subprocess.run(
            [sys.executable, str(ROOT / "examples" / "run_offense.py"),
             "--work", str(self.work), *extra],
            capture_output=True, text=True, timeout=600, cwd=str(ROOT))
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        return r.stdout

    def test_resume_after_half_checkpoint_lost(self):
        self._run("--resume")
        board = json.loads((self.work / "leaderboard.json")
                           .read_text("utf-8"))
        # crash: lose half the on-disk job results
        ck_files = sorted((self.work / "checkpoint")
                          .rglob("*.json"))
        self.assertGreater(len(ck_files), 10)
        for p in ck_files[: len(ck_files) // 2]:
            p.unlink()
        second = self._run("--resume")
        self.assertIn("[resume] checkpoint", second)
        # only the missing jobs actually ran
        self.assertRegex(second, r"\[resume\] checkpoint 复用 \d+ 个作业结果，"
                                  r"实跑 [1-9]\d* 个")
        # byte-identical leaderboard (rows are the product, not the log)
        again = json.loads((self.work / "leaderboard.json")
                           .read_text("utf-8"))
        self.assertEqual(again, board)


if __name__ == "__main__":
    unittest.main()
