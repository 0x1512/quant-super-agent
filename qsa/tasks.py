"""Async task model — SUPERAGENT_PLAN #1 (dsh's async ReAct, local edition).

`qsa run --bg` semantics: a long research run must never hold the
human hostage. ``start`` spawns the workload detached in its own
process group and returns a task id immediately (the Started state);
status/wait/cancel operate on the task card; every transition lands on
disk so a killed process leaves an auditable state, never a mystery.

States (a subset of the order state machine; refused stays to orders):

    running -> settled | failed | cancelled | interrupted

* settled/failed are written by the child wrapper (exit code recorded)
* cancelled is written by ``cancel`` (SIGTERM to the whole group)
* interrupted is derived: pid gone without a terminal field — the
  watchdog marks it, and ``status`` self-heals it lazily too.

Registry layout (atomic writes, crash-safe to read):

    <root>/tasks/T-<id>/task.json    the card (rewritten atomically)
    <root>/tasks/T-<id>/child.log    combined child stdout/stderr

CLI:

    python -m qsa.tasks start -- python examples/run_offense.py --work work/off1
    python -m qsa.tasks status [T-id]
    python -m qsa.tasks wait T-id [--timeout 600]
    python -m qsa.tasks cancel T-id
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

TERMINAL = {"settled", "failed", "cancelled", "interrupted"}


def _root(root: str | None = None) -> Path:
    r = Path(root) if root else Path(os.environ.get("QSA_TASKS_ROOT",
                                                    "work"))
    (r / "tasks").mkdir(parents=True, exist_ok=True)
    return r


def _new_id() -> str:
    return f"T-{time.strftime('%H%M%S')}-{random.randrange(0x10000):04x}"


def _card_path(root: Path, tid: str) -> Path:
    return root / "tasks" / tid / "task.json"


def _write_card(root: Path, card: dict) -> None:
    p = _card_path(root, card["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(card, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, p)


def read_card(root: Path, tid: str) -> dict | None:
    p = _card_path(root, tid)
    if not p.exists():
        return None
    return json.loads(p.read_text("utf-8"))


def list_cards(root: Path) -> list[dict]:
    d = root / "tasks"
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("T-*/task.json")):
        try:
            out.append(json.loads(p.read_text("utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    # a detached child that exited but was not yet reaped lingers as a
    # zombie: kill(pid, 0) still succeeds, but it is NOT alive
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            fields = fh.read().rsplit(b")", 1)[-1].split()
        return bool(fields) and fields[0] != b"Z"
    except OSError:
        return True                 # no /proc: fall back to kill(0)


def refresh(card: dict, root: Path) -> dict:
    """Lazy self-heal: a running card whose pid is gone and stays gone
    for one full second without a terminal field is 'interrupted'."""
    if card.get("state") == "running" and not _alive(card.get("pid", -1)):
        time.sleep(0.05)
        if not _alive(card.get("pid", -1)) and not _terminal_written(card):
            card["state"] = "interrupted"
            card["ended_at"] = time.time()
            _write_card(root, card)
    return card


def _terminal_written(card: dict) -> bool:
    # child writes the terminal field via _child; re-read from disk so
    # a just-finished task is not misclassified
    fresh = read_card(Path(card["_root"]), card["id"]) if "_root" in card \
        else None
    return bool(fresh and fresh.get("state") in TERMINAL)


def start(argv: list[str], root: str | None = None,
          log_name: str = "child.log") -> dict:
    if not argv:
        raise SystemExit("tasks: start needs a command after --")
    r = _root(root)
    tid = _new_id()
    tdir = r / "tasks" / tid
    tdir.mkdir(parents=True, exist_ok=True)
    # phase 1: the card exists BEFORE the child can read it, so the
    # child never writes a terminal state we would then overwrite
    card = {"id": tid, "argv": argv, "started_at": time.time(),
            "state": "starting"}
    _write_card(r, card)
    log = open(tdir / log_name, "wb")
    child_argv = [sys.executable, "-m", "qsa.tasks", "_child", tid,
                  "--root", str(r), "--"] + argv
    proc = subprocess.Popen(child_argv, stdout=log, stderr=log,
                            stdin=subprocess.DEVNULL,
                            start_new_session=True, cwd=os.getcwd())
    log.close()                     # the child holds its own fd now
    fresh = read_card(r, tid) or card
    if fresh.get("state") not in TERMINAL:
        # phase 2: stamp the pid; the child waits for it before running
        # the payload, so its terminal write always lands AFTER this one
        fresh["pid"] = proc.pid
        fresh["state"] = "running"
        _write_card(r, fresh)
    return fresh


def _child(tid: str, argv: list[str], root: str | None = None) -> int:
    """Runs inside the detached group: execute the payload, then write
    the terminal state — the card is the contract, not the exit code."""
    root = _root(root)
    card = read_card(root, tid) or {"id": tid}
    # wait for the parent's phase-2 stamp (pid) so our terminal write
    # can never be overwritten by the running card (max 10s, then the
    # parent is presumed dead and we proceed anyway)
    deadline = time.time() + 10
    while "pid" not in card and time.time() < deadline:
        time.sleep(0.02)
        card = read_card(root, tid) or card
    t0 = time.time()
    code = subprocess.run(argv).returncode
    card = read_card(root, tid) or card   # keep every parent field
    card["state"] = "settled" if code == 0 else "failed"
    card["exit_code"] = code
    card["elapsed_s"] = round(time.time() - t0, 2)
    card["ended_at"] = time.time()
    _write_card(root, card)
    return 0  # the wrapper itself always succeeds; payload code is in the card


def cancel(tid: str, root: str | None = None) -> dict:
    r = _root(root)
    card = read_card(r, tid)
    if card is None:
        raise SystemExit(f"tasks: no such task {tid}")
    if card.get("state") in TERMINAL:
        return card
    pid = card.get("pid", -1)
    if pid > 0:
        try:
            os.killpg(os.getpgid(pid), 15)
        except (ProcessLookupError, PermissionError, OSError, ValueError):
            pass
    card["state"] = "cancelled"
    card["ended_at"] = time.time()
    _write_card(r, card)
    return card


def wait(tid: str, timeout: float = 0.0,
         root: str | None = None) -> tuple[dict, bool]:
    """Poll until terminal; returns (card, timed_out).

    Self-heals: a running card whose pid is gone (and stays gone) is
    marked interrupted and returned — wait never loops forever on a
    process that died without writing its terminal state.
    """
    r = _root(root)
    deadline = time.time() + timeout if timeout > 0 else None
    while True:
        card = read_card(r, tid)
        if card is None:
            raise SystemExit(f"tasks: no such task {tid}")
        if card.get("state") in TERMINAL:
            return card, False
        if "pid" in card and not _alive(card["pid"]):
            time.sleep(0.1)
            card = read_card(r, tid) or card
            if card.get("state") in TERMINAL:
                return card, False
            if "pid" in card and not _alive(card["pid"]):
                healed = refresh({**card, "_root": str(r)}, r)
                return healed, False
        if deadline is not None and time.time() > deadline:
            return refresh({**card, "_root": str(r)}, r), True
        time.sleep(0.1)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 2
    cmd, rest = args[0], args[1:]
    if cmd == "start":
        if "--" in rest:
            rest = rest[rest.index("--") + 1:]
        card = start(rest)
        print(f"[tasks] started {card['id']} (pid {card['pid']}) — "
              f"Started; state on disk")
        print(card["id"])
        return 0
    if cmd == "_child":
        tid = rest[0] if rest else ""
        root = None
        if "--root" in rest:
            root = rest[rest.index("--root") + 1]
        payload = (rest[rest.index("--") + 1:] if "--" in rest
                   else rest[1:])
        return _child(tid, payload, root=root)
    if cmd == "status":
        r = _root()
        cards = [refresh({**c, "_root": str(r)}, r)
                 for c in list_cards(r)]
        if rest:
            cards = [c for c in cards if c["id"] == rest[0]]
        if not cards:
            print("[tasks] no tasks")
            return 1
        for c in cards:
            el = c.get("elapsed_s")
            el_s = f"{el}s" if el is not None else \
                f"{time.time()-c['started_at']:.0f}s+"
            print(f"{c['id']}  {c['state']:<12} {el_s:>8}  "
                  f"{' '.join(c['argv'][:3])}")
        return 0
    if cmd == "wait":
        tid = rest[0]
        to = 0.0
        if "--timeout" in rest:
            to = float(rest[rest.index("--timeout") + 1])
        card, timed_out = wait(tid, to)
        print(json.dumps({k: v for k, v in card.items()}, ensure_ascii=False))
        if timed_out:
            print(f"[tasks] wait: timeout after {to}s (still running)")
            return 124
        return int(card.get("exit_code", 0) or 0)
    if cmd == "cancel":
        card = cancel(rest[0])
        print(f"[tasks] {card['id']} -> {card['state']}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
