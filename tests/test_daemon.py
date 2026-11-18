"""Daemon tests — SUPERAGENT_PLAN2 #1 acceptance, mechanically pinned.

The acceptance table from the plan:
* broken ledger refuses startup WITH the named reason;
* a dead resident service is restarted and every exit/restart is an
  incident line;
* periodic services run on their interval;
* a flapping service is DEGRADED (no infinite restart loop);
* children orphaned by a SIGKILLed daemon are reaped before new ones
  spawn — a restart never double-runs a service;
* events are not replayed or lost across a daemon kill/restart (the
  watch state keys, not the daemon, own that — we pin the combination).
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa import daemon as dm                       # noqa: E402
from qsa.orders import OrderBook                   # noqa: E402


def _touch_service(path: Path) -> dict:
    """A service that touches <path> then exits 3 (always dies)."""
    return {"name": "toucher", "mode": "resident",
            "argv": [sys.executable, "-c",
                     "import sys, pathlib; "
                     "pathlib.Path(sys.argv[1]).touch(); sys.exit(3)",
                     str(path)],
            "backoff_s": 0.05, "max_restarts_per_window": 5,
            "window_s": 300}


class DaemonCase(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-daemon-"))
        self.root = self.tmp / "work"
        self.root.mkdir()

    def _incidents(self) -> list[dict]:
        p = self.root / "daemon" / "incidents.jsonl"
        if not p.exists():
            return []
        return [json.loads(x) for x in
                p.read_text("utf-8").splitlines() if x.strip()]


class TestStartGate(DaemonCase):
    def test_clean_ledgers_pass(self):
        d = dm.Daemon(self.root, {"services": []})
        self.assertEqual(d.start_gate(), [])

    def test_broken_order_chain_refuses_startup_with_reason(self):
        book = OrderBook(self.root / "orders.jsonl")
        book.create("h", {})
        p = self.root / "orders.jsonl"
        ev = [json.loads(x) for x in p.read_text().splitlines()]
        ev[0]["hypothesis"] = "tampered"            # break the chain
        p.write_text("\n".join(json.dumps(e, ensure_ascii=False)
                               for e in ev) + "\n")
        d = dm.Daemon(self.root, {"services": []})
        problems = d.start_gate()
        self.assertEqual(len(problems), 1)
        self.assertIn("refuses to rechain", problems[0])

    def test_unparseable_watch_state_refuses_startup(self):
        w = self.root / "watch"
        w.mkdir()
        (w / "state.json").write_text("{not json", encoding="utf-8")
        d = dm.Daemon(self.root, {"services": []})
        problems = d.start_gate()
        self.assertTrue(any("watch state unreadable" in x
                            for x in problems))

    def test_main_returns_2_on_broken_ledger(self):
        w = self.root / "watch"
        w.mkdir()
        (w / "state.json").write_text("{not json", encoding="utf-8")
        rc = dm.main(["--root", str(self.root), "--max-ticks", "1"])
        self.assertEqual(rc, 2)


class TestChildren(DaemonCase):
    def test_resident_service_restarts_and_records_incidents(self):
        f = self.tmp / "touches"
        cfg = {"services": [_touch_service(f)]}
        d = dm.Daemon(self.root, cfg, tick_s=0.05)
        d.run(max_ticks=30)
        self.assertGreaterEqual(d.spawns["toucher"], 2)
        exits = [i for i in self._incidents() if i["kind"] == "exit"]
        self.assertTrue(all("exit code 3" in e["detail"] for e in exits))
        self.assertGreaterEqual(len(exits), 1)
        # heartbeat was maintained and children are gone after shutdown
        hb = json.loads((self.root / "daemon" / "heartbeat.json")
                        .read_text())
        self.assertIn("toucher", hb["services"])
        self.assertEqual(json.loads((self.root / "daemon" / "state.json")
                                    .read_text())["pids"], {})

    def test_periodic_service_runs_on_its_interval(self):
        f = self.tmp / "ticks"
        cfg = {"services": [{"name": "ticker", "mode": "every_s",
                             "every_s": 0.3,
                             "argv": [sys.executable, "-c",
                                      "import sys, pathlib; "
                                      "pathlib.Path(sys.argv[1]).touch()",
                                      str(f)]}]}
        d = dm.Daemon(self.root, cfg, tick_s=0.05)
        d.run(max_ticks=int(0.3 * 4 / 0.05))
        self.assertGreaterEqual(d.spawns["ticker"], 3)

    def test_flapping_service_degrades_no_infinite_restart(self):
        f = self.tmp / "flap"
        svc = _touch_service(f)
        svc.update({"backoff_s": 0.01, "max_restarts_per_window": 2,
                    "window_s": 300})
        d = dm.Daemon(self.root, {"services": [svc]}, tick_s=0.02)
        d.run(max_ticks=80)
        self.assertIn("toucher", d.degraded)
        self.assertEqual(d.spawns["toucher"], 2)     # initial + 1 restart
        self.assertTrue(any(i["kind"] == "degraded"
                            for i in self._incidents()))


class TestCrashDiscipline(DaemonCase):
    def test_orphaned_children_are_reaped_before_respawn(self):
        # a leftover child from a "SIGKILLed daemon": our marker env
        sleeper = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            env={**os.environ, dm.CHILD_ENV_KEY: "1", "QSA_SERVICE": "x"})
        state = self.root / "daemon" / "state.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"pids": {"x": sleeper.pid}}),
                         encoding="utf-8")
        f = self.tmp / "after"
        cfg = {"services": [_touch_service(f)]}
        d = dm.Daemon(self.root, cfg, tick_s=0.05)
        self.assertEqual(d._reap_stale(), 1)
        time.sleep(0.2)
        self.assertNotEqual(sleeper.poll(), None)   # it is dead
        self.assertTrue(any(i["kind"] == "reaped"
                            for i in self._incidents()))

    def test_kill9_then_restart_never_replays_or_doubles(self):
        """End-to-end: real watch under the daemon; daemon SIGKILLed;
        restart reaps the orphan, respawns, and the one event that
        already fired drafts exactly one order — no replay, no loss."""
        root = self.root
        wdir = root / "watch"
        wdir.mkdir()
        rules = wdir / "rules.json"
        rules.write_text(json.dumps([
            {"id": "px", "kind": "file",
             "pattern": str(self.tmp / "panels" / "*.csv"),
             "goal": "新数据到达重扫"}]), encoding="utf-8")
        (self.tmp / "panels").mkdir()
        cfg_path = self.tmp / "daemon.json"
        cfg_path.write_text(json.dumps({"services": [{
            "name": "watch", "mode": "resident",
            "argv": [sys.executable, "-m", "qsa.watch", "--daemon",
                     "--rules", str(rules), "--root", str(root),
                     "--interval", "0.5"],
            "backoff_s": 0.2}]}), encoding="utf-8")

        def start_daemon(extra=()):
            return subprocess.Popen(
                [sys.executable, "-m", "qsa.daemon", "--root", str(root),
                 "--config", str(cfg_path), "--tick-s", "0.1", *extra])

        d1 = start_daemon()
        try:
            (self.tmp / "panels" / "px.csv").write_text("t,px\n1,2\n")
            orders = root / "orders.jsonl"
            for _ in range(150):                     # up to 15 s
                if orders.exists():
                    lines = [json.loads(x) for x in
                             orders.read_text().splitlines()
                             if x.strip()]
                    if any(e.get("type") == "create" for e in lines):
                        break
                time.sleep(0.1)
            else:
                self.fail("watch under the daemon never drafted")
            first = json.loads(
                orders.read_text().splitlines()[0])
            orphan = json.loads((root / "daemon" / "state.json")
                                .read_text())["pids"]["watch"]
        finally:
            d1.send_signal(signal.SIGKILL)
            d1.wait()
        # the daemon is dead; the watch child may still be alive

        d2 = start_daemon(("--max-ticks", "6"))
        try:
            for _ in range(100):                     # up to 10 s
                if d2.poll() is not None:
                    break
                time.sleep(0.1)
        finally:
            if d2.poll() is None:
                d2.terminate()
                d2.wait()
        # the orphan was reaped (whatever its state at kill time)
        self.assertFalse(dm._alive(orphan) and dm._is_our_child(orphan))
        # the event is neither replayed nor lost: exactly one create
        lines = [json.loads(x) for x in
                 (root / "orders.jsonl").read_text().splitlines()
                 if x.strip()]
        creates = [e for e in lines if e.get("type") == "create"]
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0]["order_id"], first["order_id"])
        # and the second daemon's own child was shut down with it
        self.assertEqual(json.loads((root / "daemon" / "state.json")
                                    .read_text())["pids"], {})

    def test_graceful_shutdown_records_and_leaves_no_children(self):
        cfg = {"services": [
            {"name": "sleeper", "mode": "resident",
             "argv": [sys.executable, "-c",
                      "import time; time.sleep(60)"]}]}
        d = dm.Daemon(self.root, cfg, tick_s=0.05)
        d.run(max_ticks=2)
        self.assertEqual(d.procs, {})
        kinds = [i["kind"] for i in self._incidents()]
        self.assertIn("stopped", kinds)
        self.assertIn("shutdown", kinds)


if __name__ == "__main__":
    unittest.main()
