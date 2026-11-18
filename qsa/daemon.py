"""Daemon — SUPERAGENT_PLAN2 #1 (one supervisor, the whole workshop).

SUPERAGENT_PLAN #1/#3/#4/#7 gave the workshop resident loops (tasks,
watch, patrol, watchdog) — but each was a process you started by hand,
and nothing restarted the ones that died. dsh-superagent runs as one
resident supervisor; this is ours, in this repo's register:
declarative config, mechanical ledgers, no invention.

What the daemon does (and refuses to do):

* **START GATE** — before any child spawns, the ledgers are verified:
  the order book's hash chain must recompute (``OrderBook()`` raises
  on a broken chain) and the watch/patrol state files must parse. A
  broken ledger REFUSES startup with the named reason — a supervisor
  that starts on top of a corrupted ledger is a multiplier, not a
  guard.
* **CHILD MANAGEMENT** — two service kinds: ``resident`` (a loop such
  as ``qsa watch --daemon``: spawned once, restarted with backoff when
  it dies) and ``every_s`` (one-shot commands such as a patrol pass or
  a watchdog tick, re-invoked on their interval). Every exit and every
  restart lands in ``daemon/incidents.jsonl`` with the exit code —
  auditable, never silent. A service that exits more than
  ``max_restarts`` times inside ``window_s`` is DEGRADED: it stops
  being restarted and the incident says so. A flapping service
  restarted forever would burn the workshop's attention, not save it.
* **CRASH DISCIPLINE** — running child pids are recorded atomically in
  ``daemon/state.json``. If the daemon is SIGKILLed, its children (in
  their own sessions) survive; on the next startup the daemon REAPS
  exactly the stale pids it can identify as its own (the child
  environment carries ``QSA_DAEMON_CHILD=1``), before spawning
  anything — a restart can never double-run a service. Event
  no-replay/no-loss is NOT the daemon's trick: the watch/patrol state
  files are keyed and written atomically (tmp + os.replace) by their
  own modules; the daemon only READS them, and restarts the loops that
  own them.
* **HEARTBEAT** — ``daemon/heartbeat.json`` (ts + per-service pid,
  restarts, degraded) is rewritten every tick; a stale heartbeat is
  how the board (and later the panel) shows "workshop down".

不拍板零执行 unchanged: the daemon supervises processes; it never
admits an order, never settles, never touches a fork decision.

    python -m qsa.daemon --root work                # default services
    python -m qsa.daemon --root work --config d.json
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .orders import OrderBook, OrderError

CHILD_ENV_KEY = "QSA_DAEMON_CHILD"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _is_our_child(pid: int) -> bool:
    """The pid is one of ours: /proc/<pid>/environ carries the marker.

    Linux-only by design (CI + workstations are Linux); on systems
    without /proc we err on NOT killing, and say so in the incident.
    """
    env = Path(f"/proc/{pid}/environ")
    try:
        return CHILD_ENV_KEY.encode() in env.read_bytes()
    except OSError:
        return False


class Daemon:
    """The supervisor. One instance, one root, one config."""

    def __init__(self, root: Path, config: dict, tick_s: float = 1.0):
        self.root = Path(root)
        self.dir = self.root / "daemon"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "logs").mkdir(parents=True, exist_ok=True)
        self.services: dict[str, dict] = {
            s["name"]: s for s in config.get("services", [])}
        self.tick_s = tick_s
        self.procs: dict[str, subprocess.Popen] = {}
        self.restarts: dict[str, list[float]] = {n: [] for n in self.services}
        self.degraded: set[str] = set()
        self.last_spawn: dict[str, float] = {}
        self.next_allowed: dict[str, float] = {}
        self.spawns: dict[str, int] = {n: 0 for n in self.services}
        self._stop = False

    # ----------------------------------------------------------- ledgers
    def _incident(self, kind: str, service: str, detail: str) -> None:
        p = self.dir / "incidents.jsonl"
        line = json.dumps({"ts": time.time(), "kind": kind,
                           "service": service, "detail": detail},
                          ensure_ascii=False)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _write_atomic(self, path: Path, obj: dict) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, path)

    def start_gate(self) -> list[str]:
        """Verify the ledgers this workshop stands on. [] = pass."""
        problems: list[str] = []
        book = self.root / "orders.jsonl"
        if book.exists():
            try:
                OrderBook(book)
            except OrderError as exc:
                problems.append(f"orders ledger refuses to rechain: {exc}")
            except Exception as exc:                    # noqa: BLE001
                problems.append(f"orders ledger unreadable: {exc}")
        for name, rel in (("watch", "watch/state.json"),
                          ("patrol", "patrol/state.json")):
            p = self.root / rel
            if not p.exists():
                continue
            try:
                json.loads(p.read_text("utf-8"))
            except Exception as exc:                    # noqa: BLE001
                problems.append(f"{name} state unreadable: {exc}")
        return problems

    def _reap_stale(self) -> int:
        """Kill children left by a SIGKILLed previous daemon. Returns n."""
        p = self.dir / "state.json"
        if not p.exists():
            return 0
        try:
            stale = json.loads(p.read_text("utf-8")).get("pids", {})
        except Exception:                               # noqa: BLE001
            stale = {}
        n = 0
        for name, pid in stale.items():
            if not isinstance(pid, int) or not _alive(pid):
                continue
            if not _is_our_child(pid):
                self._incident("reap-skip", str(name),
                               f"pid {pid} alive but not marked ours "
                               f"(no /proc environ match); not killed")
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                for _ in range(20):
                    if not _alive(pid):
                        break
                    time.sleep(0.1)
                if _alive(pid):
                    os.kill(pid, signal.SIGKILL)
                n += 1
                self._incident("reaped", str(name),
                               f"stale pid {pid} from a previous run")
            except ProcessLookupError:
                pass
        self._write_atomic(p, {"pids": {}})
        return n

    # ----------------------------------------------------------- children
    def _spawn(self, name: str) -> None:
        s = self.services[name]
        log = (self.dir / "logs" / f"{name}.log").open("ab")
        env = dict(os.environ)
        env[CHILD_ENV_KEY] = "1"
        env["QSA_SERVICE"] = name
        # children run with cwd=<root>, so make the qsa package
        # importable no matter where the workshop root lives
        pkg_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = (pkg_root + os.pathsep
                             + env.get("PYTHONPATH", "")).rstrip(os.pathsep)
        try:
            self.procs[name] = subprocess.Popen(
                s["argv"], stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, env=env, start_new_session=True,
                cwd=str(self.root))
        finally:
            log.close()            # the child holds its own dup
        self.spawns[name] += 1
        self.last_spawn[name] = time.time()

    def _stop_child(self, name: str, proc: subprocess.Popen,
                    grace: float = 5.0) -> None:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        self._incident("stopped", name, "shutdown: child terminated")

    # ----------------------------------------------------------- the loop
    def _bookkeep_exit(self, name: str, rc: int) -> None:
        self.restarts[name].append(time.time())
        self._incident("exit", name, f"exit code {rc}")
        backoff = float(self.services[name].get("backoff_s", 1.0))
        self.next_allowed[name] = time.time() + backoff

    def _degrade_if_flapping(self, name: str, now: float) -> bool:
        s = self.services[name]
        window = float(s.get("window_s", 300))
        max_r = int(s.get("max_restarts_per_window", 5))
        recent = [t for t in self.restarts[name] if now - t <= window]
        if len(recent) >= max_r and name not in self.degraded:
            self.degraded.add(name)
            self._incident("degraded", name,
                           f"{len(recent)} exits within {window:g}s "
                           f"(max {max_r}); no more restarts")
        return name in self.degraded

    def run(self, max_ticks: int | None = None) -> dict:
        self._reap_stale()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: setattr(self, "_stop", True))
        ticks = 0
        while not self._stop and (max_ticks is None or ticks < max_ticks):
            now = time.time()
            for name, s in self.services.items():
                proc = self.procs.get(name)
                if proc is not None and proc.poll() is not None:
                    self._bookkeep_exit(name, proc.returncode)
                    del self.procs[name]
                if name in self.procs or name in self.degraded:
                    continue
                mode = s.get("mode", "resident")
                if mode == "resident":
                    if now >= self.next_allowed.get(name, 0):
                        if not self._degrade_if_flapping(name, now):
                            self._spawn(name)
                else:                                   # every_s
                    due = self.last_spawn.get(name, 0) + float(s["every_s"])
                    if now >= due:
                        if not self._degrade_if_flapping(name, now):
                            self._spawn(name)
            self._write_state()
            ticks += 1
            if self._stop or (max_ticks is not None and ticks >= max_ticks):
                break
            time.sleep(self.tick_s)
        self.shutdown()
        return {n: {"spawns": self.spawns[n],
                    "exits": len(self.restarts[n]),
                    "degraded": n in self.degraded}
                for n in self.services}

    def _write_state(self) -> None:
        self._write_atomic(self.dir / "state.json",
                           {"pids": {n: p.pid for n, p in self.procs.items()}})
        self._write_atomic(self.dir / "heartbeat.json", {
            "ts": time.time(),
            "services": {n: {"pid": p.pid if (p := self.procs.get(n)) else None,
                             "spawns": self.spawns[n],
                             "degraded": n in self.degraded}
                         for n in self.services}})

    def shutdown(self) -> None:
        for name, proc in list(self.procs.items()):
            self._stop_child(name, proc)
            del self.procs[name]
        self._write_atomic(self.dir / "state.json", {"pids": {}})
        self._incident("shutdown", "-", "daemon stopped; no children left")


def _default_config(root: Path) -> dict:
    """Standard workshop: watch resident, patrol + watchdog periodic."""
    py = sys.executable
    services = []
    rules = root / "watch" / "rules.json"
    if rules.exists():
        services.append({
            "name": "watch", "mode": "resident",
            "argv": [py, "-m", "qsa.watch", "--daemon", "--rules",
                     str(rules), "--root", str(root), "--interval", "30"],
            "backoff_s": 5, "max_restarts_per_window": 5, "window_s": 300})
    targets = root / "patrol" / "targets.json"
    if targets.exists():
        services.append({
            "name": "patrol", "mode": "every_s", "every_s": 60,
            "argv": [py, "-m", "qsa.patrol", "--targets", str(targets),
                     "--root", str(root)]})
    services.append({
        "name": "watchdog", "mode": "every_s", "every_s": 60,
        "argv": [py, "-m", "qsa.watchdog", "--once", "--root", str(root)]})
    return {"services": services}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="work")
    ap.add_argument("--config", default=None,
                    help="JSON {services:[{name,mode,argv,...}]}; "
                         "default = the standard workshop")
    ap.add_argument("--tick-s", type=float, default=1.0)
    ap.add_argument("--max-ticks", type=int, default=0,
                    help="0 = run until SIGTERM (tests use a bound)")
    a = ap.parse_args(argv)
    root = Path(a.root)
    config = (json.loads(Path(a.config).read_text("utf-8"))
              if a.config else _default_config(root))
    d = Daemon(root, config, tick_s=a.tick_s)
    problems = d.start_gate()
    if problems:
        for p in problems:
            print(f"[daemon] refusing to start: {p}", file=sys.stderr)
        return 2
    print(f"[daemon] supervising {len(d.services)} services: "
          + ", ".join(d.services))
    summary = d.run(max_ticks=a.max_ticks or None)
    for name, s in summary.items():
        print(f"[daemon] {name}: {s['spawns']} spawns, {s['exits']} exits"
              + (", DEGRADED" if s["degraded"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
