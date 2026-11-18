"""Board — SUPERAGENT_PLAN #6 (one screen, the whole workshop).

`qsa board` reconciles every ledger into one view: tasks (the #1
registry), orders (the hash-chained book, by state), watchdog
incidents (#7), unresolved blackboard blockers and crew sessions
(#5). The board is a READ over the ledgers — every number on it is
recomputable from disk, and the tests assert exactly that.

    python -m qsa.board --root work
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import blackboard as bb
from . import tasks as T


def _tasks_lines(root: Path) -> list[str]:
    cards = T.list_cards(root)
    if not cards:
        return ["tasks    (none)"]
    out = []
    for c in cards:
        out.append(f"tasks    {c['id']}  {c['state']:<12} "
                   f"exit={c.get('exit_code', '-')}")
    return out


def _orders_lines(root: Path) -> list[str]:
    from .orders import OrderBook
    p = root / "orders.jsonl"
    if not p.exists():
        return ["orders   (none)"]
    book = OrderBook(p)
    s = book.summary()
    parts = [f"{k}={v}" for k, v in sorted(s.items()) if v]
    out = ["orders   " + (" ".join(parts) if parts else "empty")]
    for oid in book.by_state("drafted")[:5]:
        o = book.orders[oid]
        out.append(f"orders   {oid}  drafted  ← {o['hypothesis'][:60]}")
    return out


def _watchdog_lines(root: Path) -> list[str]:
    p = root / "watchdog" / "incidents.jsonl"
    if not p.exists():
        return ["watchdog 0 incidents"]
    rows = [json.loads(x) for x in p.read_text("utf-8").splitlines()
            if x.strip()]
    out = [f"watchdog {len(rows)} incidents"]
    for r in rows[-3:]:
        out.append(f"watchdog   {r['task']}  {r['attribution']}")
    return out


def _board_lines(root: Path) -> list[str]:
    p = root / "blackboard.jsonl"
    if not p.exists():
        return ["board    (no blackboard)"]
    board = bb.bootstrapped(p)
    blockers = board.blockers()
    out = [f"board    {len(board)} entries, "
           f"{len(blockers)} unresolved blockers"]
    for i, e in enumerate(board.entries()):
        if e in blockers:
            out.append(f"board     #{i} {e['title']}")
    return out


def _crew_lines(root: Path) -> list[str]:
    from . import crew
    cards = crew.sessions(root / "crew")
    if not cards:
        return ["crew     (no sessions)"]
    out = []
    for kind, c in sorted(cards.items()):
        out.append(f"crew     {kind:<13} {c['role']:<12} "
                   f"{c['n_jobs']} jobs -> {c['n_rows']} rows")
    return out


def render(root: Path) -> str:
    root = Path(root)
    lines = [f"== quant-super-agent board  ({root}) =="]
    lines += _tasks_lines(root)
    lines += _orders_lines(root)
    lines += _watchdog_lines(root)
    lines += _board_lines(root)
    lines += _crew_lines(root)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="work")
    a = ap.parse_args(argv)
    print(render(Path(a.root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
