"""Tests for the router + board (SUPERAGENT_PLAN #6).

Router: multiple orders run CONCURRENTLY, each in its own work dir;
because every run is a pure function of (goal, data), concurrent
output is byte-identical to a sequential run — asserted here with real
runs, not argued.

Board: one screen reconciled from every ledger; the numbers on it are
recomputed from disk in the same test.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from qsa import board as B
from qsa import crew, router, tasks as T
from qsa.orders import OrderBook

ROOT = Path(__file__).resolve().parents[1]


class TestBoard(unittest.TestCase):
    """Board numbers == ledger queries (the board is a read, not a
    second source of truth)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-board-"))
        self.addCleanup(self._rm)
        self._old_root = os.environ.get("QSA_TASKS_ROOT")
        os.environ["QSA_TASKS_ROOT"] = str(self.tmp / "reg")
        self.root = self.tmp / "work"
        self.root.mkdir()

    def _rm(self):
        if self._old_root is None:
            os.environ.pop("QSA_TASKS_ROOT", None)
        else:
            os.environ["QSA_TASKS_ROOT"] = self._old_root
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _known_state(self):
        from qsa import blackboard as bb
        book = OrderBook(self.root / "orders.jsonl")
        a = book.create("goal A", {"x": 1})
        b = book.create("goal B", {"x": 2})
        book.admit(b, {"x": 2})
        book.start(b, {"x": 2})
        book.settle(b, {"n": 3})
        blk = bb.bootstrapped(self.root / "blackboard.jsonl")
        blk.post("order_note", f"事件触发订单草案 {a}", "x",
                 status="blocker", tags=["watch", "needs-decision"])
        inc = self.root / "watchdog" / "incidents.jsonl"
        inc.parent.mkdir(parents=True, exist_ok=True)
        rows = [json.dumps({"task": task, "attribution": attr,
                            "detail": "d", "ts": "t"})
                for task, attr in (("T-1", "infra_died"),
                                   ("T-2", "no_progress"))]
        inc.write_text("\n".join(rows) + "\n", encoding="utf-8")
        crew.record(self.root / "crew", "zoo", [("zoo", 0)], [{"id": "z"}])
        return a, b

    def test_render_reconciles_every_ledger(self):
        a, b = self._known_state()
        text = B.render(self.root)
        self.assertIn("drafted=1", text)                 # order A
        self.assertIn("settled=1", text)                 # order B
        self.assertIn(a, text)
        self.assertIn("2 incidents", text)
        self.assertIn("no_progress", text)
        self.assertIn("1 unresolved blockers", text)     # patrol-style post
        self.assertIn("zoo", text) and self.assertIn("GateKeeper", text)

    def test_empty_root_renders(self):
        text = B.render(self.root)
        self.assertIn("(none)", text)
        self.assertIn("0 incidents", text)


class TestRouterConcurrency(unittest.TestCase):
    """Concurrent runs == sequential runs, byte for byte (real runs)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="qsa-router-"))
        cls.reg = cls.tmp / "reg"
        cls.goal_a = None       # default goal (module reads its own default)
        cls.goal_b = ("top300 残差因子进攻：引用因子库+交互+窗口变异，"
                      "门槛 0.04")
        # concurrent: two orders, two work dirs, at the same time
        cards = router.route(
            [{"goal": cls.goal_a, "work": str(cls.tmp / "conc-a")},
             {"goal": cls.goal_b, "work": str(cls.tmp / "conc-b")}],
            root=str(cls.reg))
        cls.cards = cards
        # sequential reference for goal A
        r = subprocess.run(
            [sys.executable, str(ROOT / "examples" / "run_offense.py"),
             "--work", str(cls.tmp / "seq-a")],
            capture_output=True, text=True, timeout=600, cwd=str(ROOT))
        assert r.returncode == 0, r.stderr[-2000:]

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_all_tasks_settled(self):
        for c in self.cards:
            self.assertEqual(c["state"], "settled", c)
            self.assertEqual(c.get("exit_code"), 0)

    def test_concurrent_equals_sequential(self):
        conc = json.loads((self.tmp / "conc-a" / "leaderboard.json")
                          .read_text("utf-8"))
        seq = json.loads((self.tmp / "seq-a" / "leaderboard.json")
                         .read_text("utf-8"))
        self.assertEqual(conc, seq)

    def test_isolated_work_dirs(self):
        for d in ("conc-a", "conc-b"):
            self.assertTrue((self.tmp / d / "run_config.json").exists())
        # different goals produced different fingerprints
        ca = json.loads((self.tmp / "conc-a" / "run_config.json")
                        .read_text("utf-8"))
        cb = json.loads((self.tmp / "conc-b" / "run_config.json")
                        .read_text("utf-8"))
        self.assertNotEqual(ca["fingerprint"], cb["fingerprint"])

    def test_crew_reconciles_on_real_runs(self):
        for d in ("conc-a", "conc-b"):
            man = json.loads((self.tmp / d / "manifest.json")
                             .read_text("utf-8"))
            self.assertEqual(crew.reconcile(self.tmp / d / "crew", man), [])

    def test_no_wait_returns_immediately(self):
        t0 = time.time()
        cards = router.route(
            [{"goal": self.goal_a, "work": str(self.tmp / "nowait")}],
            root=str(self.reg), wait=False)
        dt = time.time() - t0
        self.assertLess(dt, 5.0)                    # Started, not blocking
        self.assertIn(cards[0]["state"], ("starting", "running"))
        T.wait(cards[0]["id"], timeout=600, root=str(self.reg))


if __name__ == "__main__":
    unittest.main()
