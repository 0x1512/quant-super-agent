"""Tests for the speculative plane (SUPERAGENT_PLAN #9).

Execute during the human's pause:

* preflight is async (a task card, Started at once);
* if the human admits, delivery hands over the precomputed,
  fingerprint-bound artifacts in well under 10% of a single run;
* if the human refuses, nothing was ever settled and the WASTE is
  recorded (it goes to EVIDENCE, not under the rug);
* a missing/stale preflight falls back to a checkpoint-warm re-run and
  still settles honestly.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from qsa import speculative
from qsa.orders import OrderBook

ROOT = Path(__file__).resolve().parents[1]
# examples/run_offense.DEFAULT_GOAL, spelled out so preflight/deliver
# compile the same plan fingerprint as a plain cold run
GOAL = ("top300 残差因子进攻：引用因子库+交互+窗口变异，"
        "门槛 residual oos IC > 0.03")


class SpeculativeE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="qsa-spec-"))
        cls.reg = str(cls.tmp / "reg")
        os.environ["QSA_TASKS_ROOT"] = cls.reg
        # the honest yardstick: ONE cold run, timed
        cls.t_cold = _timed_run(cls.tmp / "cold")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("QSA_TASKS_ROOT", None)
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self._book_path = self.tmp / "orders.jsonl"
        self.book = OrderBook(self._book_path)

    def test_preflight_deliver_refuse_cycle(self):
        # 1. draft + preflight during the human's pause
        work = self.tmp / "w1"
        oid = self.book.create("spec order", {"goal": "default"})
        card = speculative.preflight(GOAL, work, root=self.reg)
        self.assertIn(card["state"], ("starting", "running"))  # async
        # the human's pause outlasts the preflight: it has finished by
        # the time the admit arrives
        from qsa import tasks as T
        done, _ = T.wait(card["id"], timeout=600, root=self.reg)
        self.assertEqual(done["state"], "settled")
        # 2. the human admits -> sub-10% delivery
        res = speculative.deliver(GOAL, work, oid, self.book,
                                  root=self.reg)
        self.assertTrue(res["speculative"])
        self.assertLess(res["elapsed_s"], 0.1 * self.t_cold)
        order = self.book.orders[oid]
        self.assertEqual(order["state"], "settled")
        self.assertEqual(order["results"]["speculative"], True)
        self.assertTrue(Path(order["results"]["leaderboard"]).exists())
        # the delivered board is the same run a cold execution gives
        cold = json.loads((self.tmp / "cold" / "leaderboard.json")
                          .read_text("utf-8"))
        got = json.loads((work / "leaderboard.json").read_text("utf-8"))
        self.assertEqual(got, cold)
        # stats: one preflight, one delivery, zero waste
        s = speculative.stats(work)
        self.assertEqual((s["preflights"], s["delivered"], s["wasted"]),
                         (1, 1, 0))

    def test_refusal_records_waste(self):
        work = self.tmp / "w2"
        oid = self.book.create("spec order 2", {"goal": "default"})
        speculative.preflight(GOAL, work, root=self.reg)
        # the human refuses instead: order refused, waste recorded
        self.book.refuse(oid, "not this cycle")
        s = speculative.mark_wasted(work)
        self.assertEqual(s["wasted"], 1)
        self.assertEqual(s["delivered"], 0)
        self.assertEqual(self.book.orders[oid]["state"], "refused")

    def test_missing_preflight_falls_back_to_warm_run(self):
        work = self.tmp / "w3"          # no preflight ever ran here
        oid = self.book.create("spec order 3", {"goal": "default"})
        res = speculative.deliver(GOAL, work, oid, self.book,
                                  root=self.reg)
        self.assertFalse(res["speculative"])   # honest: it computed now
        self.assertEqual(self.book.orders[oid]["state"], "settled")
        cold = json.loads((self.tmp / "cold" / "leaderboard.json")
                          .read_text("utf-8"))
        got = json.loads((work / "leaderboard.json").read_text("utf-8"))
        self.assertEqual(got, cold)

    def test_stale_fingerprint_is_not_delivered(self):
        work = self.tmp / "w1"          # artifacts for the default goal
        oid = self.book.create("other goal", {"goal": "other"})
        other = ("top300 残差因子进攻：引用因子库+交互+窗口变异，"
                 "门槛 0.09")
        res = speculative.deliver(other, work, oid, self.book,
                                  root=self.reg)
        # a different goal cannot reuse the artifacts: it recomputed
        self.assertFalse(res["speculative"])
        self.assertEqual(self.book.orders[oid]["state"], "settled")
        cfg = json.loads((work / "run_config.json").read_text("utf-8"))
        self.assertEqual(cfg["thresh"], 0.09)


def _timed_run(work: Path) -> float:
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "run_offense.py"),
         "--work", str(work)],
        capture_output=True, text=True, timeout=600, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-2000:]
    return time.time() - t0


if __name__ == "__main__":
    unittest.main()
