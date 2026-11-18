"""Tests for the resident patrol (SUPERAGENT_PLAN #4).

The silence discipline, pinned three ways:

* healthy targets -> ZERO output: no orders, no incidents, no noise;
* a confirmed problem with a known simple fix -> exactly ONE repair
  draft, deduped across passes;
* a problem WITHOUT a known fix -> an incident line, never an order
  (the patrol does not invent capabilities or execute anything).
"""
import json
import os
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from qsa import patrol
from qsa.orders import OrderBook


class PatrolCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-patrol-"))
        self.addCleanup(self._rm)
        self.root = self.tmp / "work"
        self.root.mkdir()

    def _rm(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _orders(self) -> OrderBook:
        return OrderBook(self.root / "orders.jsonl")

    def _incidents(self) -> list[dict]:
        p = self.root / "patrol" / "incidents.jsonl"
        if not p.exists():
            return []
        return [json.loads(x) for x in
                p.read_text("utf-8").splitlines() if x.strip()]


class TestSilence(PatrolCase):

    def test_healthy_run_is_silent(self):
        f = self.tmp / "panel.csv"
        f.write_text("a\n1\n", encoding="utf-8")       # fresh by mtime
        targets = [{"id": "panel", "check": "file_fresh",
                    "path": str(f), "max_age_s": 3600}]
        self.assertEqual(patrol.patrol(targets, self.root), [])
        # ZERO output: no order book, no incident file was even created
        self.assertFalse((self.root / "orders.jsonl").exists())
        self.assertEqual(self._incidents(), [])

    def test_missing_file_without_fix_goal_is_incident_only(self):
        targets = [{"id": "panel", "check": "file_fresh",
                    "path": str(self.tmp / "gone.csv"),
                    "max_age_s": 60}]
        self.assertEqual(patrol.patrol(targets, self.root), [])
        self.assertEqual(len(self._incidents()), 1)
        self.assertIn("missing", self._incidents()[0]["detail"])
        self.assertFalse((self.root / "orders.jsonl").exists())


class TestRepairDrafts(PatrolCase):

    def test_stale_panel_drafts_one_repair_order(self):
        f = self.tmp / "panel.csv"
        f.write_text("a\n1\n", encoding="utf-8")
        old = time.time() - 7200
        os.utime(f, (old, old))
        targets = [{"id": "panel", "check": "file_fresh",
                    "path": str(f), "max_age_s": 3600,
                    "repair_goal": "re-ingest the stale panel"}]
        drafts = patrol.patrol(targets, self.root)
        self.assertEqual(len(drafts), 1)
        book = self._orders()
        oid = drafts[0]["order_id"]
        self.assertEqual(book.orders[oid]["state"], "drafted")
        self.assertEqual(book.orders[oid]["history"][0]["params"]["source"],
                         "patrol")
        # dedup: the second pass drafts NOTHING further
        self.assertEqual(patrol.patrol(targets, self.root), [])
        self.assertEqual(self._orders().summary()["drafted"], 1)
        # and the draft never executes on its own
        self.assertIsNone(book.orders[oid]["results"])

    def test_torn_checkpoint_tmp_drafts_cleanup(self):
        ck = self.root / "checkpoint" / "zoo"
        ck.mkdir(parents=True)
        (ck / "abc.tmp").write_text("torn", encoding="utf-8")
        targets = [{"id": "ckpt", "check": "no_tmp",
                    "path": str(self.root / "checkpoint"),
                    "repair_goal": "clear torn tmp files"}]
        self.assertEqual(len(patrol.patrol(targets, self.root)), 1)
        self.assertEqual(patrol.patrol(targets, self.root), [])


class TestLedgerChecks(PatrolCase):

    def test_broken_order_chain_is_incident_not_order(self):
        p = self.root / "orders.jsonl"
        book = OrderBook(p)
        book.create("h", {})
        lines = p.read_text("utf-8").splitlines()
        # tamper with the chain field of the create event
        ev = json.loads(lines[0])
        ev["chain"] = "0" * 64
        lines[0] = json.dumps(ev)
        p.write_text("\n".join(lines), encoding="utf-8")
        targets = [{"id": "orders", "check": "orderbook"}]
        self.assertEqual(patrol.patrol(targets, self.root), [])
        self.assertEqual(len(self._incidents()), 1)
        self.assertIn("broken", self._incidents()[0]["detail"])

    def test_intact_chain_is_quiet(self):
        book = OrderBook(self.root / "orders.jsonl")
        book.create("h", {})
        targets = [{"id": "orders", "check": "orderbook"}]
        self.assertEqual(patrol.patrol(targets, self.root), [])
        self.assertEqual(self._incidents(), [])

    def test_blockers_over_limit_incident_only(self):
        from qsa import blackboard as bb
        board = bb.bootstrapped(self.root / "blackboard.jsonl")
        for i in range(6):
            board.post("order_note", f"blocker {i}", "x",
                       status="blocker", tags=["needs-decision"])
        targets = [{"id": "board", "check": "blockers", "max": 4}]
        self.assertEqual(patrol.patrol(targets, self.root), [])
        self.assertEqual(len(self._incidents()), 1)


class TestCLI(PatrolCase):

    def test_main(self):
        f = self.tmp / "panel.csv"
        f.write_text("a\n1\n", encoding="utf-8")
        old = time.time() - 7200
        os.utime(f, (old, old))
        tp = self.tmp / "targets.json"
        tp.write_text(json.dumps(
            [{"id": "panel", "check": "file_fresh", "path": str(f),
              "max_age_s": 3600, "repair_goal": "re-ingest"}]),
            encoding="utf-8")
        rc = patrol.main(["--targets", str(tp), "--root", str(self.root)])
        self.assertEqual(rc, 0)
        self.assertEqual(self._orders().summary()["drafted"], 1)


class TestProviderPlane(PatrolCase):
    """Gateway-mode confirmation: dismissals are recorded, never silent;
    a dead endpoint changes nothing."""

    def _gateway_env(self, content: str) -> dict:
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                self.rfile.read(n)
                body = json.dumps({
                    "choices": [{"message": {"content": content}}],
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return {"QSA_PROVIDER": "gateway",
                "QSA_GATEWAY_URL":
                    f"http://127.0.0.1:{srv.server_address[1]}/v1"}

    def _stale_target(self) -> tuple:
        f = self.tmp / "panel.csv"
        f.write_text("a\n1\n", encoding="utf-8")
        old = time.time() - 7200
        os.utime(f, (old, old))
        return [{"id": "panel", "check": "file_fresh", "path": str(f),
                 "max_age_s": 3600, "repair_goal": "re-ingest"}], f

    def test_model_dismissal_blocks_the_draft_and_is_recorded(self):
        targets, _ = self._stale_target()
        env = self._gateway_env(
            '{"answer": "no", "reason": "盘后数据盘中不更新属正常"}')
        with unittest.mock.patch.dict(os.environ, env):
            self.assertEqual(patrol.patrol(targets, self.root), [])
        # no order was drafted...
        self.assertFalse((self.root / "orders.jsonl").exists())
        # ...but the dismissal AND the rule verdict are on record
        inc = self._incidents()
        self.assertEqual(len(inc), 1)
        self.assertIn("model-dismissed", inc[0]["detail"])
        self.assertIn("盘后", inc[0]["detail"])
        self.assertIn("stale", inc[0]["detail"])
        # dedup: a second pass with the same verdict adds no noise
        with unittest.mock.patch.dict(os.environ, env):
            patrol.patrol(targets, self.root)
        self.assertEqual(len(self._incidents()), 1)

    def test_model_confirmation_still_drafts(self):
        targets, _ = self._stale_target()
        env = self._gateway_env(
            '{"answer": "yes", "reason": "盘中数据确实该更新"}')
        with unittest.mock.patch.dict(os.environ, env):
            drafts = patrol.patrol(targets, self.root)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(self._orders().summary()["drafted"], 1)
        self.assertEqual(self._incidents(), [])

    def test_dead_gateway_changes_nothing(self):
        targets, _ = self._stale_target()
        env = {"QSA_PROVIDER": "gateway",
               "QSA_GATEWAY_URL": "http://127.0.0.1:9/v1"}
        with unittest.mock.patch.dict(os.environ, env):
            drafts = patrol.patrol(targets, self.root)
        # fallback -> the rule verdict stands -> same as offline
        self.assertEqual(len(drafts), 1)
        self.assertEqual(self._orders().summary()["drafted"], 1)


if __name__ == "__main__":
    unittest.main()
