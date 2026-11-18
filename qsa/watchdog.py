"""Watchdog — SUPERAGENT_PLAN #7 (dsh's Watchdog Session, rules-first).

An external control loop, deliberately NOT part of the agent: it
watches running tasks from the task registry and mechanically
downgrades trouble, with an attribution. No model judgement — rules
only (model judgement is a later, risk-gated upgrade).

Rules (each writes an incident card, append-only):

* infra_died      — pid gone, no terminal field on disk
* budget_exhausted— runtime exceeded --max-runtime
* no_progress     — the task's footprint (log size + artifact count)
                    unchanged for --no-progress-ticks consecutive ticks

Downgrade = SIGTERM the whole process group + mark the task. The
watchdog never restarts anything and never edits results — recovery is
a human/order-book decision, not a silent retry.

    python -m qsa.watchdog --once [--max-runtime 3600] [--no-progress-ticks 3]
    python -m qsa.watchdog --ticks 5 --interval 30
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import tasks as T


def _footprint(root: Path, card: dict) -> tuple[int, int]:
    """Cheap progress signature: log bytes + files under the task dir."""
    tdir = root / "tasks" / card["id"]
    log = tdir / "child.log"
    n_files = sum(1 for _ in tdir.rglob("*") if _.is_file())
    return (log.stat().st_size if log.exists() else 0, n_files)


def _incident(root: Path, card: dict, attribution: str, detail: str) -> None:
    inc = root / "watchdog" / "incidents.jsonl"
    inc.parent.mkdir(parents=True, exist_ok=True)
    row = {"task": card["id"], "attribution": attribution,
           "detail": detail, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with inc.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[watchdog] {card['id']}: {attribution} — {detail}")


def tick(root: Path, state: dict, max_runtime: float,
         no_progress_ticks: int) -> dict:
    """One pass over running tasks. ``state`` maps task id -> footprint
    history; it is returned for the caller to persist."""
    for card in T.list_cards(root):
        was_running = card.get("state") == "running"
        alive = T._alive(card.get("pid", -1))
        # refresh may self-heal a dead-pid card to 'interrupted' — capture
        # the transition so it is ATTRIBUTED, not silently reclassified
        card = T.refresh({**card, "_root": str(root)}, root)
        if was_running and not alive and card.get("state") == "interrupted":
            _incident(root, card, "infra_died",
                      f"pid {card.get('pid', -1)} gone without a terminal "
                      f"state")
        if card.get("state") != "running":
            state.pop(card["id"], None)
            continue
        runtime = time.time() - card.get("started_at", time.time())
        if max_runtime and runtime > max_runtime:
            T.cancel(card["id"], root=str(root))
            _incident(root, card, "budget_exhausted",
                      f"runtime {runtime:.0f}s > {max_runtime}s")
            state.pop(card["id"], None)
            continue
        fp = _footprint(root, card)
        hist = state.setdefault(card["id"], {"fp": fp, "stalls": 0,
                                             "since": time.time()})
        if fp == hist["fp"]:
            hist["stalls"] += 1
        else:
            hist["fp"], hist["stalls"] = fp, 0
        if no_progress_ticks and hist["stalls"] >= no_progress_ticks:
            T.cancel(card["id"], root=str(root))
            _incident(root, card, "no_progress",
                      f"footprint unchanged for {hist['stalls']} ticks")
            state.pop(card["id"], None)
    return state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="work")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--ticks", type=int, default=0)
    ap.add_argument("--interval", type=float, default=30.0)
    ap.add_argument("--max-runtime", type=float, default=0.0)
    ap.add_argument("--no-progress-ticks", type=int, default=0)
    a = ap.parse_args(argv)

    root = Path(a.root)
    (root / "tasks").mkdir(parents=True, exist_ok=True)
    state_path = root / "watchdog" / "state.json"
    state = {}
    if state_path.exists():
        state = json.loads(state_path.read_text("utf-8"))

    n = 1 if a.once else max(a.ticks, 1)
    for i in range(n):
        state = tick(root, state, a.max_runtime, a.no_progress_ticks)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        if i < n - 1:
            time.sleep(a.interval)
    print("[watchdog] tick done" if a.once or a.ticks <= 1
          else f"[watchdog] {a.ticks} ticks done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
