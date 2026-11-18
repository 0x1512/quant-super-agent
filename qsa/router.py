"""Router — SUPERAGENT_PLAN #6 (multiple orders, concurrently).

Each order gets its own work directory and its own detached task (the
#1 async task model); the router spawns them all and waits. Because
every run is a pure function of (goal, data) — the dispatcher's
determinism contract — CONCURRENT runs are byte-identical to sequential
ones, and that is asserted in tests, not hoped for.

    specs = [{"goal": "...", "work": "work/o1"},
             {"goal": "...", "work": "work/o2"}]
    router.route(specs)          # parallel, one task card per spec
"""
from __future__ import annotations

import json
from pathlib import Path

from . import tasks as T

ROOT = Path(__file__).resolve().parents[1]


def _argv_for(spec: dict) -> list[str]:
    import sys
    argv = [sys.executable, str(ROOT / "examples" / "run_offense.py"),
            "--work", str(spec["work"])]
    if spec.get("full"):
        argv.append("--full")
    if spec.get("resume"):
        argv.append("--resume")
    if spec.get("goal"):
        argv += ["--goal", spec["goal"]]
    argv += spec.get("extra_args", [])
    return argv


def route(specs: list[dict], root: str | None = None,
          wait: bool = True) -> list[dict]:
    """Spawn one task per spec (each in its own work dir); optionally
    wait for all to reach a terminal state. Returns the task cards."""
    if not specs:
        return []
    cards = [T.start(_argv_for(s), root=root) for s in specs]
    if not wait:
        return cards
    out = []
    for c in cards:
        card, _ = T.wait(c["id"], timeout=0, root=root)
        out.append(card)
    return out


def main(argv: list[str] | None = None) -> int:            # pragma: no cover
    import sys
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2 or args[0] != "--specs":
        print('usage: python -m qsa.router --specs specs.json '
              '[--root work]')
        return 2
    specs = json.loads(Path(args[1]).read_text("utf-8"))
    root = None
    if "--root" in args:
        root = args[args.index("--root") + 1]
    cards = route(specs, root=root)
    for c in cards:
        print(f"{c['id']}  {c['state']:<10} exit={c.get('exit_code')}")
    return 0 if all(c.get("state") == "settled" for c in cards) else 1


if __name__ == "__main__":
    raise SystemExit(main())
