"""Patrol — SUPERAGENT_PLAN #4 (dsh's resident worker, silent).

A resident loop that keeps the workshop healthy WITHOUT making noise:
healthy targets produce ZERO output; a CONFIRMED problem with a known
simple fix produces exactly ONE repair-order draft (deduped); problems
without a known fix are logged to an incident file and left to a human
— the patrol never invents capabilities and never executes anything
(admit is still a human decision).

Provider plane: with ``QSA_PROVIDER=gateway`` a user-supplied model
gets to confirm each problem before it becomes an incident or a
draft; offline (default) the rule verdict stands. A model dismissal
is RECORDED (``model-dismissed`` incident line carrying the model's
reason and the original rule verdict) — never silent.

Targets (JSON list, one file):

    [{"id": "panel-a", "check": "file_fresh", "path": "data/a.csv",
      "max_age_s": 3600, "repair_goal": "re-ingest panel a"},
     {"id": "orders", "check": "orderbook", "path": "work/orders.jsonl"},
     {"id": "board", "check": "blockers", "max": 4},
     {"id": "ckpt", "check": "no_tmp", "path": "work/checkpoint",
      "repair_goal": "clear checkpoint tmp files"}]

    python -m qsa.patrol --targets patrol_targets.json --root work
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from . import blackboard as bb
from . import provider
from .orders import OrderBook


# ------------------------------------------------------------- the checks

def check_file_fresh(t: dict, root: Path) -> tuple[bool, str, bool]:
    """(ok, detail, fixable) — fixable == a repair_goal was declared."""
    p = Path(t["path"])
    if not p.exists():
        return False, f"missing: {p}", bool(t.get("repair_goal"))
    age = time.time() - p.stat().st_mtime
    if age > t.get("max_age_s", 3600):
        return (False, f"stale: {p} age {age:.0f}s > "
                       f"{t.get('max_age_s', 3600)}s",
                bool(t.get("repair_goal")))
    return True, f"fresh ({age:.0f}s)", False


def check_orderbook(t: dict, root: Path) -> tuple[bool, str, bool]:
    p = root / "orders.jsonl" if "path" not in t else Path(t["path"])
    if not p.exists():
        return True, "no order book yet", False
    try:
        OrderBook(p)
        return True, "chain intact", False
    except Exception as exc:                     # noqa: BLE001
        # a broken chain is never auto-fixed: it is the audit trail
        return False, f"order log chain broken: {exc}", False


def check_blockers(t: dict, root: Path) -> tuple[bool, str, bool]:
    p = root / "blackboard.jsonl" if "path" not in t else Path(t["path"])
    if not p.exists():
        return True, "no blackboard yet", False
    board = bb.bootstrapped(p)
    n = len(board.blockers())
    if n > t.get("max", 4):
        # unresolved blockers need a HUMAN decision, not a patrol fix
        return False, f"{n} unresolved blockers > {t.get('max', 4)}", False
    return True, f"{n} blockers", False


def check_no_tmp(t: dict, root: Path) -> tuple[bool, str, bool]:
    p = Path(t["path"]) if "path" in t else root / "checkpoint"
    if not p.exists():
        return True, "no dir", False
    tmps = sorted(p.rglob("*.tmp"))
    if tmps:
        return (False, f"{len(tmps)} torn tmp files"
                       f" (e.g. {tmps[0].name})", bool(t.get("repair_goal")))
    return True, "clean", False


CHECKS = {"file_fresh": check_file_fresh, "orderbook": check_orderbook,
          "blockers": check_blockers, "no_tmp": check_no_tmp}


# ------------------------------------------------------------ the patrol

def _state_path(root: Path) -> Path:
    return root / "patrol" / "state.json"


def _already_drafted(root: Path, target_id: str) -> bool:
    p = _state_path(root)
    if not p.exists():
        return False
    return target_id in json.loads(p.read_text("utf-8")).get("drafted", {})


def _already_dismissed(root: Path, target_id: str, detail: str) -> bool:
    """Identical model dismissal already on record (dedup across passes)."""
    p = root / "patrol" / "incidents.jsonl"
    if not p.exists():
        return False
    for ln in p.read_text("utf-8").splitlines():
        if ln and target_id in ln and detail in ln \
                and "model-dismissed" in ln:
            return True
    return False


def _mark_drafted(root: Path, target_id: str, order_id: str) -> None:
    p = _state_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(p.read_text("utf-8")) if p.exists() else {"drafted": {}}
    state["drafted"][target_id] = {"order_id": order_id,
                                   "ts": time.strftime(
                                       "%Y-%m-%dT%H:%M:%S")}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, p)


def _incident(root: Path, target_id: str, detail: str) -> None:
    p = root / "patrol" / "incidents.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"target": target_id, "detail": detail,
                             "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                            ensure_ascii=False) + "\n")


def patrol(targets: list[dict], root: Path) -> list[dict]:
    """One pass. Returns the repair drafts raised (usually empty).

    Silence discipline: healthy targets touch nothing and say nothing.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    drafts: list[dict] = []
    for t in targets:
        fn = CHECKS.get(t.get("check"))
        if fn is None:
            _incident(root, t.get("id", "?"),
                      f"unknown check {t.get('check')!r}")
            continue
        ok, detail, fixable = fn(t, root)
        if ok:
            continue
        # provider plane: offline defers to the rule verdict (yes);
        # a user-supplied gateway may dismiss it — every dismissal is
        # recorded next to the rule verdict, never silent
        q = (f"巡检目标 {t['id']}（check={t.get('check')}）报告问题："
             f"{detail}。这值得起草修复单或记为事故吗？")
        if t.get("note"):
            q += f"目标说明：{t['note']}。"
        v = provider.judge(q)
        if v["answer"] == "no":
            if not _already_dismissed(root, t["id"], detail):
                _incident(root, t["id"],
                          f"model-dismissed ({v['by']}): {v['reason']} "
                          f"|| rule verdict was: {detail}")
            continue
        if not fixable:
            _incident(root, t["id"], detail)
            continue
        if _already_drafted(root, t["id"]):
            continue                    # one repair order per problem, once
        book = OrderBook(root / "orders.jsonl")
        oid = book.create(t.get("repair_goal", f"repair {t['id']}"),
                          {"source": "patrol", "target": t["id"],
                           "problem": detail}, priority=8,
                          note=f"patrol: {detail}")
        board = bb.bootstrapped(root / "blackboard.jsonl")
        board.post("order_note",
                   f"巡检修复单 {oid}",
                   f"目标 {t['id']} 确认问题：{detail}。已起草修复订单，"
                   f"等待拍板 admit 后执行。",
                   status="blocker", tags=["patrol", "needs-decision"])
        _mark_drafted(root, t["id"], oid)
        drafts.append({"order_id": oid, "target": t["id"]})
    return drafts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--root", default="work")
    a = ap.parse_args(argv)
    targets = json.loads(Path(a.targets).read_text("utf-8"))
    drafts = patrol(targets, Path(a.root))
    for d in drafts:
        print(f"[patrol] repair draft {d['order_id']} <- {d['target']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
