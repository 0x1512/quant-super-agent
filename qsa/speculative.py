"""Speculative — SUPERAGENT_PLAN #9 (execute during the human's pause).

Between an order draft and the human's admit there is dead time. The
speculative plane uses it: preflight runs the SAME pipeline (same
goal, same fingerprint) into the target work dir with ``--resume``,
so every per-job result lands in the checkpoint. If the human admits
the order, delivery re-stitches from the checkpoint and finishes in
seconds; if they refuse, nothing was settled and the waste is
RECORDED, not hidden (waste rate goes to EVIDENCE).

Discipline: preflight computes but never DELIVERS — no admit, no
settle, no board post. The order stays drafted until a human decides.

    card = speculative.preflight(goal, work)      # bg task, returns now
    speculative.deliver(goal, work, order_id, book)   # after admit
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import tasks as T

ROOT = Path(__file__).resolve().parents[1]


def _stats_path(work: Path) -> Path:
    return work / "speculative" / "stats.json"


def _load_stats(work: Path) -> dict:
    p = _stats_path(work)
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return {"preflights": 0, "delivered": 0, "wasted": 0,
            "preflight_s": 0.0, "deliver_s": 0.0}


def _save_stats(work: Path, s: dict) -> None:
    p = _stats_path(work)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, p)


def _argv(goal: str | None, work: Path) -> list[str]:
    import sys
    argv = [sys.executable, str(ROOT / "examples" / "run_offense.py"),
            "--work", str(work), "--resume"]
    if goal:
        argv += ["--goal", goal]
    return argv


def preflight(goal: str, work: Path, root: str | None = None) -> dict:
    """Start the speculative run (async task card, returns at once)."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    card = T.start(_argv(goal, work), root=root)
    s = _load_stats(work)
    s["preflights"] += 1
    _save_stats(work, s)
    return card


def deliver(goal: str, work: Path, order_id: str, book,
            root: str | None = None) -> dict:
    """Admit-time delivery.

    If the preflight finished, its artifacts are already on disk and
    fingerprint-bound to this goal: verify and DELIVER them (sub-second
    — that is the whole point of speculating during the human's pause).
    If the preflight is missing or stale, fall back to a checkpoint-warm
    re-run. Either way the order settles only NOW, under the human's
    admit — preflight computed, but never delivered.
    """
    import subprocess

    from . import planner
    work = Path(work)
    t0 = time.time()
    # let a preflight finish rather than fight it for the same files
    reg = T._root(root)
    for c in T.list_cards(reg):
        if c.get("state") == "running" and c["argv"] == _argv(goal, work):
            T.wait(c["id"], timeout=0, root=str(reg))
    fp = planner.fingerprint(planner.intent_to_plan(goal))
    cfg_path = work / "run_config.json"
    board_path = work / "leaderboard.json"
    have = (cfg_path.exists() and board_path.exists())
    if have:
        cfg = json.loads(cfg_path.read_text("utf-8"))
        have = cfg.get("fingerprint") == fp
    if not have:
        # fallback: no (or stale) preflight — run the pipeline warm
        r = subprocess.run(_argv(goal, work), cwd=str(ROOT),
                           capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            book.refuse(order_id, f"delivery failed: {r.stderr[-400:]}")
            raise RuntimeError(f"deliver failed: {r.stderr[-800:]}")
        cfg = json.loads(cfg_path.read_text("utf-8"))
    elapsed = time.time() - t0
    board = json.loads(board_path.read_text("utf-8"))
    n_rows = sum(len(board.get(k, [])) for k in
                 ("library", "interactions", "mutations", "forge"))
    # the human has admitted; walk the state machine honestly
    params = {"goal": goal, "fingerprint": fp}
    state = book.orders[order_id]["state"]
    if state == "drafted":
        book.admit(order_id, params)
        state = "admitted"
    if state == "admitted":
        book.start(order_id, params)
    book.settle(order_id, {"elapsed_s": round(elapsed, 2),
                           "leaderboard": str(board_path),
                           "n_candidates": n_rows,
                           "n_winners": cfg.get("n_winners", 0),
                           "fingerprint": fp,
                           "speculative": have})
    s = _load_stats(work)
    s["delivered"] += 1
    s["deliver_s"] = round(s.get("deliver_s", 0) + elapsed, 2)
    _save_stats(work, s)
    return {"elapsed_s": round(elapsed, 2), "order_id": order_id,
            "leaderboard": str(board_path), "speculative": have}


def mark_wasted(work: Path) -> dict:
    """The human refused: preflight work was wasted — record it."""
    s = _load_stats(work)
    s["wasted"] += 1
    _save_stats(work, s)
    return s


def stats(work: Path) -> dict:
    return _load_stats(Path(work))
