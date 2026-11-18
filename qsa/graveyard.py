"""Graveyard v2 — ALPHA_PLAN S2: a ledger of doubt, not a wall.

The v1 flaw (user correction, 2026-11-18): one fail banned a cell
forever, but a fail can mean "the hypothesis is dead" OR "the
IMPLEMENTATION detail was wrong" (a volume proxy standing in for
market cap, a window-boundary bug, a skip-month semantics slip).
Banning on a single implementation kills ideas that were never
properly researched. v2 fixes the blast radius:

* **tiers** — ``thin`` (unjudgeable on this data plane; revives
  automatically when the data plane grows), ``parked`` (ONE
  implementation failed: suspended, retestable, not banned),
  ``banned`` (>= INDEPENDENT_FAILS_TO_BAN *distinct
  implementations* failed — user-拍板 threshold 2). A replay of the
  same implementation never advances the count (no ban-farming).
* **autopsy** — every fail stores per-criterion margins + the full
  metric snapshot, so a "close-call death" (margin within 20% of
  the line) is visibly different from a deep death, and any later
  gate re-version can replay the verdict for free.
* **hypothesis/implementation separation** — records live per
  (cell, implementation); a new implementation of the same
  hypothesis starts clean and is what can promote a cell to
  banned — or revive it.
* **revive_on_data** — when the data plane grows >= 20%, thin and
  data-sensitive cells automatically get revisit proposals; nobody
  has to remember them.
* **revisit queue** — any source (human, LLM line, data trigger)
  files ``RV-xxx`` proposals that MUST carry a reason and a change;
  the loop spends a fixed quota of its budget on them (user-拍板
  20%). Revisit pass-rate is sealed per loop: never succeeding says
  the gate is hard; often succeeding says the graveyard was
  over-killing. Both are signal.

User 拍板 on record (2026-11-18): revisit quota 20%; hypothesis-
level ban requires 2 independent implementation fails.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .admission import STAGE2_ADMISSION

VERSION = 2
INDEPENDENT_FAILS_TO_BAN = 2     # user 拍板 2026-11-18
CLOSE_CALL_MARGIN = -0.20        # within 20% of the line = close call
DATA_GROWTH_REVIVAL = 0.20       # +20% sample -> auto revisit proposals
REVISE_QUOTA = 0.20              # user 拍板 2026-11-18

TIERS = ("thin", "parked", "banned", "revived")


def new_graveyard(data_plane: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"version": VERSION,
            "data_plane": data_plane or {},
            "cells": {},
            "revisit_queue": [],
            "log": []}


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return new_graveyard()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") == VERSION:
        return data
    if data.get("version") == 1:
        return migrate_v1(data)
    raise ValueError(f"graveyard {path}: unknown version "
                     f"{data.get('version')!r}")


def save(path: Path, yard: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(yard, ensure_ascii=False, indent=1,
                               sort_keys=True), encoding="utf-8")


# -- v1 -> v2: the honest re-sentencing -------------------------------

def migrate_v1(data: dict[str, Any]) -> dict[str, Any]:
    """v1's permanent bans become v2 parked (suspended) cells: one
    implementation ('v1-volproxy') failed once. The re-sentencing is
    itself recorded in the log — history is amended in the open."""
    yard = new_graveyard({"snapshot_id": "loop1-full", "n_dates": 1210,
                          "note": "migrated from v1; n_dates as of "
                                  "loop 1"})
    for key, rec in data.get("banned", {}).items():
        impl = {"implementation": "v1-volproxy",
                "verdict": "fail",
                "reasons": rec.get("reasons", []),
                "gate_version": "stage2-v1",
                "loop": rec.get("loop"),
                "ts": rec.get("banned_at"),
                "metrics": {"oos_ic": rec.get("oos_ic"),
                            "icir": rec.get("icir")},
                "margins": "not recorded at v1"}
        yard["cells"][key] = {"tier": "parked",
                              "fail_implementations": ["v1-volproxy"],
                              "implementations": {"v1-volproxy": impl},
                              "history": ["v1: banned -> v2: parked "
                                          "(single-implementation "
                                          "fail re-sentenced)"]}
    yard["log"].append({"ts": time.time(),
                        "event": "migrate_v1",
                        "banned_recounted": len(data.get("banned", {})),
                        "note": "v1 death sentences re-sentenced to "
                                "parked under the 2-implementation "
                                "rule (user 拍板 2026-11-18)"})
    return yard


# -- autopsy: margins per criterion -----------------------------------

def margins(row: dict[str, Any]) -> dict[str, float]:
    """Relative distance to each pre-registered threshold,
    (value - line) / |line|; positive = cleared. Missing metrics
    are skipped (the gate already refuses to guess)."""
    out: dict[str, float] = {}
    for name, rule in STAGE2_ADMISSION["thresholds"].items():
        v = row.get(name)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        line = rule["value"]
        if rule["op"] == ">":
            out[name] = (v - line) / abs(line or 1e-9)
        elif rule["op"] == ">=":
            out[name] = (v - line) / abs(line or 1e-9)
    return out


def autopsy(row: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    m = margins(row)
    failed: dict[str, float] = {}
    for name, v in m.items():
        rule = STAGE2_ADMISSION["thresholds"][name]
        # margin 0: ">= x" CLEARS at exactly the line, "> x" does not
        if v < 0 or (v == 0 and rule["op"] == ">"):
            failed[name] = v
    closest = max(failed.values()) if failed else None
    return {"margins": m,
            "failed_criteria": sorted(failed),
            "closest_margin": closest,
            "close_call": bool(failed) and closest is not None
                          and closest >= CLOSE_CALL_MARGIN,
            "n_months": row.get("n_months"),
            "reasons": reasons}


def is_close_call(row: dict[str, Any], reasons: list[str]) -> bool:
    return autopsy(row, reasons)["close_call"]


# -- verdict recording --------------------------------------------------

def record_verdict(yard: dict[str, Any], cell: str,
                   implementation: str, verdict: str | None,
                   reasons: list[str], row: dict[str, Any],
                   gate_version: str, loop: int) -> str:
    """Record one implementation's verdict; returns the cell tier.
    pass -> revived (kept, with history); fail -> implementation
    counted, tier may promote to banned at the 拍板 threshold;
    inconclusive/thin -> tier thin (data-plane bound)."""
    rec = yard["cells"].setdefault(
        cell, {"tier": "thin", "fail_implementations": [],
               "implementations": {}, "history": []})
    entry = {"implementation": implementation, "verdict": verdict,
             "reasons": reasons, "gate_version": gate_version,
             "loop": loop, "ts": time.time(),
             "metrics": {k: row.get(k) for k in
                         ("oos_ic", "icir", "n_months",
                          "top_minus_bottom", "train_ic",
                          "ic_decay_ratio")}}
    if verdict in ("fail", None, "inconclusive"):
        entry["autopsy"] = (autopsy(row, reasons)
                            if verdict == "fail" else None)
    rec["implementations"][f"{implementation}@{loop}"] = entry
    if verdict == "pass":
        if rec["tier"] != "revived":
            rec["history"].append(
                f"loop {loop}: {implementation} passed — revived")
        rec["tier"] = "revived"
    elif verdict == "fail":
        if implementation not in rec["fail_implementations"]:
            rec["fail_implementations"].append(implementation)
            rec["history"].append(
                f"loop {loop}: {implementation} failed "
                f"({'close call' if entry['autopsy']['close_call'] else 'deep'})")
        n = len(rec["fail_implementations"])
        rec["tier"] = ("banned" if n >= INDEPENDENT_FAILS_TO_BAN
                       else "parked")
    else:                                     # thin / inconclusive
        rec["tier"] = "thin"
    return rec["tier"]


def is_banned(yard: dict[str, Any], cell: str) -> bool:
    return yard["cells"].get(cell, {}).get("tier") == "banned"


def summary(yard: dict[str, Any]) -> dict[str, int]:
    out = {"thin": 0, "parked": 0, "banned": 0, "revived": 0}
    for c in yard["cells"].values():
        out[c["tier"]] = out.get(c["tier"], 0) + 1
    out["revisit_pending"] = sum(
        1 for p in yard["revisit_queue"]
        if p["status"] == "pending")
    return out


# -- the revisit queue ---------------------------------------------------

def propose_revisit(yard: dict[str, Any], cell: str, reason: str,
                    change: str, by: str = "human") -> str:
    """File a revisit proposal. MUST carry a reason (why the death
    may be an implementation artefact) and a change (what would be
    different); both land in the ledger."""
    if cell not in yard["cells"]:
        raise ValueError(f"unknown cell {cell!r} — proposals revisit "
                         "recorded cells, not fresh ones")
    if not reason.strip() or not change.strip():
        raise ValueError("a revisit proposal without a reason AND a "
                         "change is vibes, not research")
    rv = f"RV-{len(yard['revisit_queue']) + 1:03d}"
    yard["revisit_queue"].append(
        {"id": rv, "cell": cell, "reason": reason, "change": change,
         "by": by, "status": "pending", "ts": time.time()})
    return rv


def pending_proposals(yard: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in yard["revisit_queue"]
            if p["status"] == "pending"]


def revive_on_data(yard: dict[str, Any], new_data_plane: dict[str, Any],
                   growth: float = DATA_GROWTH_REVIVAL) -> list[str]:
    """Data plane grew >= `growth`: thin cells (and thin HISTORY)
    automatically get revisit proposals — nobody has to remember
    them. Cells that failed WITH a judgeable sample do not: their
    deaths are about the criteria, not the sample length."""
    old_n = yard.get("data_plane", {}).get("n_dates") or 0
    new_n = new_data_plane.get("n_dates") or 0
    if old_n <= 0 or new_n < old_n * (1 + growth):
        return []
    made: list[str] = []
    for cell, rec in yard["cells"].items():
        if rec["tier"] != "thin":
            continue
        if any(p["cell"] == cell and p["status"] == "pending"
               for p in yard["revisit_queue"]):
            continue
        made.append(propose_revisit(
            yard, cell,
            reason=f"data plane grew {old_n} -> {new_n} dates "
                   f"(>= {int(growth * 100)}%); cell was unjudgeable "
                   f"before",
            change="re-run the same cell on the longer sample",
            by="data_plane_growth"))
    yard["data_plane"] = new_data_plane
    yard["log"].append({"ts": time.time(), "event": "revive_on_data",
                        "old_n_dates": old_n, "new_n_dates": new_n,
                        "proposals": made})
    return made
