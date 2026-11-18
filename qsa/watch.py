"""Watch — SUPERAGENT_PLAN #3 (dsh's event-driven triggers, gated).

The research agent must not need a human to press go: file and timer
events flow in, rules filter them, and each match raises an ORDER
DRAFT. The gate is non-negotiable — a draft is never executed. Nothing
runs until a human admits it (``不拍板零执行``), so the bus can only
PROPOSE work, never silently start it.

Rules (JSON list, one file):

    [{"id": "panel-drop", "kind": "file",
      "pattern": "data/panels/*.csv", "goal": "…research intent…"},
     {"id": "weekly-refresh", "kind": "timer", "every_s": 604800,
      "goal": "…"}]

Dedup is mechanical: a file event fires once per (path, mtime); a
timer fires once per bucket ``int(now / every_s)``. Every draft is a
real OrderBook entry (hash-chained) plus a blackboard blocker, so the
human sees it on the board and admits or refuses it there.

Provider plane: with ``QSA_PROVIDER=gateway`` a user-supplied model
filters each new event before a draft is raised (offline, the default,
every matching event drafts). A dismissal marks the event processed
and lands in ``watch/dismissed.jsonl`` with the model's reason —
auditable, never silent, and 不拍板零执行 either way.

    python -m qsa.watch --rules watch_rules.json --root work --once
    python -m qsa.watch --rules watch_rules.json --root work --daemon
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import time
from pathlib import Path

from . import blackboard as bb
from . import provider
from .orders import OrderBook


def _dismissed_path(root: Path) -> Path:
    return root / "watch" / "dismissed.jsonl"


def _record_dismissal(root: Path, rule_id: str, key: str, desc: str,
                      verdict: dict) -> None:
    """A model-filtered event is still an auditable fact, not a void."""
    p = _dismissed_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"rule": rule_id, "event": key, "desc": desc,
                             "by": verdict["by"], "reason": verdict["reason"],
                             "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                            ensure_ascii=False) + "\n")


def _load_rules(path: Path) -> list[dict]:
    rules = json.loads(Path(path).read_text("utf-8"))
    for r in rules:
        if r.get("kind") not in ("file", "timer"):
            raise SystemExit(f"watch: unknown rule kind {r.get('kind')!r}")
        if not r.get("id") or not r.get("goal"):
            raise SystemExit("watch: every rule needs id and goal")
    return rules


def _state_path(root: Path) -> Path:
    return root / "watch" / "state.json"


def _load_state(root: Path) -> dict:
    p = _state_path(root)
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return {"fired": {}}


def _save_state(root: Path, state: dict) -> None:
    p = _state_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, p)


def _file_events(rule: dict, now: float) -> list[tuple[str, str]]:
    """(dedup key, human description) for each matching path."""
    pattern = rule["pattern"]
    # static directory prefix (no glob chars) keeps the walk bounded
    parts = Path(pattern).parts
    prefix: list[str] = []
    for part in parts:
        if any(ch in part for ch in "*?["):
            break
        prefix.append(part)
    base = Path(*prefix) if prefix else Path(".")
    if not base.exists():
        return []
    out = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or not fnmatch.fnmatch(str(p), pattern):
            continue
        mtime = p.stat().st_mtime
        key = f"{p}|{int(mtime)}"
        when = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(mtime))
        out.append((key, f"file {p} (mtime {when})"))
    return out


def _timer_key(rule: dict, now: float) -> str:
    return f"bucket-{int(now // rule['every_s'])}"


def fire(rule: dict, key: str, desc: str, root: Path) -> dict | None:
    """Raise one order draft for a fired event; None if already fired.

    Provider plane: with ``QSA_PROVIDER=gateway`` a user-supplied model
    filters the event before a draft is raised; offline (default) every
    matching event drafts. A dismissal marks the event processed AND
    lands in ``watch/dismissed.jsonl`` with the model's reason — the
    bus stays auditable either way, and 不拍板零执行 is unchanged.
    """
    state = _load_state(root)
    fired = state["fired"].setdefault(rule["id"], [])
    if key in fired:
        return None
    q = (f"事件 {desc} 触发规则 {rule['id']}，研究目标是「{rule['goal']}」。"
         f"值得为此起草一张研究订单（等待人拍板）吗？")
    if rule.get("note"):
        q += f"规则说明：{rule['note']}。"
    v = provider.judge(q)
    if v["answer"] == "no":
        fired.append(key)                  # processed: never re-asked
        state["fired"][rule["id"]] = fired[-1000:]
        _save_state(root, state)
        _record_dismissal(root, rule["id"], key, desc, v)
        return None
    book = OrderBook(root / "orders.jsonl")
    params = {"source": "watch", "rule": rule["id"], "event": key}
    oid = book.create(rule["goal"], params, priority=7,
                      note=f"watch trigger: {desc}")
    board = bb.bootstrapped(root / "blackboard.jsonl")
    board.post("order_note",
               f"事件触发订单草案 {oid}",
               f"规则 {rule['id']}（{desc}）按目标「{rule['goal']}」起草了"
               f"一张订单，等待拍板 admit 后才会执行。",
               status="blocker", tags=["watch", "needs-decision"])
    fired.append(key)
    state["fired"][rule["id"]] = fired[-1000:]      # bounded memory
    _save_state(root, state)
    return {"order_id": oid, "rule": rule["id"], "event": key}


def scan(rules: list[dict], root: Path, now: float | None = None) \
        -> list[dict]:
    """One pass over all rules; returns the drafts raised this pass."""
    now = time.time() if now is None else now
    drafts: list[dict] = []
    for rule in rules:
        if rule["kind"] == "file":
            for key, desc in _file_events(rule, now):
                d = fire(rule, key, desc, root)
                if d:
                    drafts.append(d)
        else:                                   # timer
            key = _timer_key(rule, now)
            d = fire(rule, key, f"timer bucket {key}", root)
            if d:
                drafts.append(d)
    return drafts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", required=True)
    ap.add_argument("--root", default="work")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--interval", type=float, default=30.0)
    a = ap.parse_args(argv)
    root = Path(a.root)
    rules = _load_rules(Path(a.rules))
    if a.once or not a.daemon:
        drafts = scan(rules, root)
        print(f"[watch] pass done — {len(drafts)} 个新草案"
              + ("" if drafts else "（无事件）"))
        for d in drafts:
            print(f"[watch] draft {d['order_id']} <- {d['rule']}"
                  f" ({d['event']})")
        return 0
    print(f"[watch] daemon: {len(rules)} rules, interval {a.interval}s")
    while True:
        for d in scan(rules, root):
            print(f"[watch] draft {d['order_id']} <- {d['rule']}"
                  f" ({d['event']})", flush=True)
        time.sleep(a.interval)


if __name__ == "__main__":
    raise SystemExit(main())
