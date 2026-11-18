"""Tests for the event trigger bus (SUPERAGENT_PLAN #3).

Acceptance: an injected event MUST raise an order draft (hash-chained,
on the blackboard); the same event never fires twice; and nothing —
nothing at all — executes until a human admits (不拍板零执行).
"""
import json
import os
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from qsa import blackboard as bb
from qsa import watch
from qsa.orders import OrderBook


class WatchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-watch-"))
        self.addCleanup(self._rm)
        self.panels = self.tmp / "panels"
        self.panels.mkdir()
        (self.panels / "px.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        self.root = self.tmp / "work"
        self.root.mkdir()

    def _rm(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _rules(self, rules: list[dict]) -> Path:
        p = self.tmp / "rules.json"
        p.write_text(json.dumps(rules, ensure_ascii=False),
                     encoding="utf-8")
        return p

    def _orders(self) -> OrderBook:
        return OrderBook(self.root / "orders.jsonl")


class TestFileRules(WatchCase):

    def test_event_raises_draft_and_blocks(self):
        rules = [{"id": "panel", "kind": "file",
                  "pattern": str(self.panels / "*.csv"),
                  "goal": "面板更新后重扫残差"}]
        drafts = watch.scan(rules, self.root)
        self.assertEqual(len(drafts), 1)
        book = self._orders()
        oid = drafts[0]["order_id"]
        self.assertEqual(book.orders[oid]["state"], "drafted")
        self.assertEqual(book.orders[oid]["history"][0]["params"]["source"],
                         "watch")
        # the human sees it as an unresolved blocker on the blackboard
        board = bb.bootstrapped(self.root / "blackboard.jsonl")
        hits = [e for e in board.entries(kind="order_note")
                if "watch" in e.get("tags", []) and oid in e["title"]]
        self.assertEqual(len(hits), 1)
        self.assertIn(hits[0], board.blockers())

    def test_same_mtime_never_fires_twice(self):
        rules = [{"id": "panel", "kind": "file",
                  "pattern": str(self.panels / "*.csv"), "goal": "g"}]
        self.assertEqual(len(watch.scan(rules, self.root)), 1)
        self.assertEqual(len(watch.scan(rules, self.root)), 0)
        self.assertEqual(len(watch.scan(rules, self.root)), 0)
        self.assertEqual(self._orders().summary()["drafted"], 1)

    def test_new_mtime_fires_again(self):
        rules = [{"id": "panel", "kind": "file",
                  "pattern": str(self.panels / "*.csv"), "goal": "g"}]
        watch.scan(rules, self.root)
        os.utime(self.panels / "px.csv",
                 (time.time() + 5, time.time() + 5))
        self.assertEqual(len(watch.scan(rules, self.root)), 1)
        self.assertEqual(self._orders().summary()["drafted"], 2)

    def test_no_match_no_draft(self):
        rules = [{"id": "panel", "kind": "file",
                  "pattern": str(self.tmp / "nothing" / "*.csv"),
                  "goal": "g"}]
        self.assertEqual(watch.scan(rules, self.root), [])
        self.assertFalse((self.root / "orders.jsonl").exists())


class TestTimerRules(WatchCase):

    def test_one_fire_per_bucket(self):
        rules = [{"id": "weekly", "kind": "timer", "every_s": 3600,
                  "goal": "周度刷新"}]
        self.assertEqual(len(watch.scan(rules, self.root, now=1000.0)), 1)
        self.assertEqual(len(watch.scan(rules, self.root, now=1500.0)), 0)
        self.assertEqual(len(watch.scan(rules, self.root, now=4000.0)), 1)
        self.assertEqual(self._orders().summary()["drafted"], 2)


class TestGateDiscipline(WatchCase):
    """不拍板零执行 — drafts never advance on their own."""

    def test_drafts_never_execute(self):
        rules = [{"id": "panel", "kind": "file",
                  "pattern": str(self.panels / "*.csv"), "goal": "g"},
                 {"id": "weekly", "kind": "timer", "every_s": 60,
                  "goal": "g2"}]
        for _ in range(3):
            watch.scan(rules, self.root)
        s = self._orders().summary()
        executed = sum(v for k, v in s.items()
                       if k in ("admitted", "running", "settled"))
        self.assertEqual(executed, 0)
        self.assertGreater(s.get("drafted", 0), 0)


class TestCLI(WatchCase):

    def test_once(self):
        p = self._rules([{"id": "panel", "kind": "file",
                          "pattern": str(self.panels / "*.csv"),
                          "goal": "g"}])
        rc = watch.main(["--rules", str(p), "--root", str(self.root),
                         "--once"])
        self.assertEqual(rc, 0)
        self.assertEqual(self._orders().summary()["drafted"], 1)

    def test_bad_rule_file_is_refused(self):
        p = self._rules([{"id": "x", "kind": "carrier-pigeon",
                          "goal": "g"}])
        with self.assertRaises(SystemExit):
            watch._load_rules(p)


class TestProviderPlane(WatchCase):
    """Gateway-mode event filtering: dismissals are processed + recorded;
    fallback and offline behave identically (every event drafts)."""

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

    def _rule(self) -> list[dict]:
        return [{"id": "panel", "kind": "file",
                 "pattern": str(self.panels / "*.csv"), "goal": "重扫"}]

    def _dismissed(self) -> list[dict]:
        p = self.root / "watch" / "dismissed.jsonl"
        if not p.exists():
            return []
        return [json.loads(x) for x in
                p.read_text("utf-8").splitlines() if x.strip()]

    def test_model_dismissal_drafts_nothing_but_is_recorded(self):
        env = self._gateway_env(
            '{"answer": "no", "reason": "该文件是临时产物，不值得开单"}')
        with unittest.mock.patch.dict(os.environ, env):
            self.assertEqual(watch.scan(self._rule(), self.root), [])
        self.assertFalse((self.root / "orders.jsonl").exists())
        d = self._dismissed()
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["rule"], "panel")
        self.assertIn("不值得", d[0]["reason"])
        # the event counts as processed: no re-ask on the next scan
        with unittest.mock.patch.dict(os.environ, env):
            self.assertEqual(watch.scan(self._rule(), self.root), [])
        self.assertEqual(len(self._dismissed()), 1)

    def test_model_confirmation_drafts_as_usual(self):
        env = self._gateway_env(
            '{"answer": "yes", "reason": "新数据到了，值得重扫"}')
        with unittest.mock.patch.dict(os.environ, env):
            drafts = watch.scan(self._rule(), self.root)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(self._dismissed(), [])

    def test_dead_gateway_changes_nothing(self):
        env = {"QSA_PROVIDER": "gateway",
               "QSA_GATEWAY_URL": "http://127.0.0.1:9/v1"}
        with unittest.mock.patch.dict(os.environ, env):
            self.assertEqual(len(watch.scan(self._rule(), self.root)), 1)
        self.assertEqual(self._dismissed(), [])


if __name__ == "__main__":
    unittest.main()
