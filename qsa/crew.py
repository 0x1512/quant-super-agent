"""Crew — SUPERAGENT_PLAN #5 (dsh's worker sessions, as evidence).

Every dispatched stream runs under a ROLE (the 编制名 from
``dispatch.ROLE_NAMES``). The crew plane makes that real: each stream
leaves a SESSION CARD on disk — the rows it produced (the numeric
product) plus the role, the job keys, the checkpoint accounting and
timing. The card is a STRICT SUPERSET of the numeric rows: nothing is
dropped, attribution is added.

Acceptance (mechanical, in tests):

* card["rows"] equals the stream's return value, row for row;
* card["job_keys"] has one entry per job (== manifest jobs_by_kind);
* ``reconcile`` cross-checks every card against the run manifest.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .dispatch import ROLE_NAMES


def record(crew_dir: Path, kind: str, jobs: list[tuple], rows: list,
           meta: dict | None = None) -> dict:
    """Write one session card: <crew_dir>/<kind>.json (atomic)."""
    crew_dir = Path(crew_dir)
    crew_dir.mkdir(parents=True, exist_ok=True)
    card: dict[str, Any] = {
        "kind": kind,
        "role": ROLE_NAMES.get(kind, kind),
        "n_jobs": len(jobs),
        "job_keys": [json.dumps(j, ensure_ascii=False, default=str)
                     for j in jobs],
        "n_rows": len(rows),
        "rows": rows,
        "meta": meta or {},
    }
    p = crew_dir / f"{kind}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return card


def sessions(crew_dir: Path) -> dict[str, dict]:
    """All session cards keyed by stream kind."""
    crew_dir = Path(crew_dir)
    out: dict[str, dict] = {}
    if not crew_dir.exists():
        return out
    for p in sorted(crew_dir.glob("*.json")):
        try:
            out[p.stem] = json.loads(p.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def reconcile(crew_dir: Path, manifest: dict) -> list[str]:
    """Every card must cover exactly the manifest's job count for its
    stream; returns a list of discrepancies (empty == reconciled)."""
    problems: list[str] = []
    cards = sessions(crew_dir)
    jobs_by_kind = manifest.get("jobs_by_kind", {})
    for kind, n in jobs_by_kind.items():
        if n == 0 or kind == "forge":
            continue        # forge is not a job-sharded crew stream
        card = cards.get(kind)
        if card is None:
            problems.append(f"{kind}: no session card "
                            f"(manifest says {n} jobs)")
            continue
        if card["n_jobs"] != n or card["n_rows"] != n:
            problems.append(f"{kind}: card {card['n_jobs']} jobs / "
                            f"{card['n_rows']} rows != manifest {n}")
        if len(set(card["job_keys"])) != card["n_jobs"]:
            problems.append(f"{kind}: duplicate job keys in card")
    for kind in cards:
        if kind not in jobs_by_kind:
            problems.append(f"{kind}: card without a manifest entry")
    return problems
