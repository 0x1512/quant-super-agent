"""FamilyTree — ALPHA_PLAN S3: budgeted family-tree generation (Loop 1).

Loop 0's honest zero (0/24 public-literature factors survive stage-2
on the full sample) proved the transplant line is exhausted. Loop 1
turns to structured generation over the ONE family that ever showed
life — momentum — as a pre-registered grid:

    momentum × window {12, 18, 24, 36 months} × domain {top300,
    smallcap} × variant {plain, gap_gate, vol_adj}

24 cells, each cell ONE generated hypothesis. Everything the loop
spends and learns is sealed in numbers (ALPHA_PLAN loop metrics):

* ``tested``             — cells generated + evaluated (budget spent)
* ``survived_stage2``    — cells passing the frozen composite gate
* ``gauntlet_passed``    — honestly 0 while S9/S10 are unwired; the
                           survivors wait in the gauntlet queue
* ``graveyard_savings``  — cells NOT re-generated because a previous
                           loop's graveyard banned them (S2 seed)
* ``cost_per_survivor``  — spent / max(survived, 1); with zero
                           survivors the plan's fallback kicks in:
                           cost per excluded family

Discipline: only a FAIL (metrics present, thresholds missed) is
graveyard-able — a cell is banned when it was proven dead, never
when the data was too thin to judge (inconclusive stays re-testable
with better data; banning it would be silent cherry-picking).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .admission import STAGE2_ADMISSION, stage2_verdict
from .factorzoo import (FactorBuild, _cumulative, evaluate_factor,
                        overnight_of, returns_of, rolling_std,
                        rolling_sum, series_of)
from .funnel import GAUNTLET_CHECKS
from .graveyard import (REVISE_QUOTA, load as load_graveyard,
                        pending_proposals, record_verdict,
                        revive_on_data, save as save_graveyard,
                        summary as graveyard_summary)
from .orders import OrderBook

WINDOWS = [12, 18, 24, 36]                  # months
DOMAINS = ["top300", "smallcap"]
VARIANTS = ["plain", "gap_gate", "vol_adj"]

GENERATION_COST = 1                          # budget units per cell
GRAVEYARD_VERSION = 1


def cell_key(window: int, domain: str, variant: str) -> str:
    return f"mom{window}/{domain}/{variant}"


# -- the grid ---------------------------------------------------------------

def _smallcap_set(closes: dict[str, dict[str, float]],
                  volumes: dict[str, dict[str, float]]) -> set[str]:
    """Bottom half by average dollar volume over the first 60 common
    dates — an HONEST proxy for market cap (the fixture carries no
    cap field); stated in every cell's desc."""
    tickers = sorted(set(closes) & set(volumes))
    d0 = sorted({d for row in closes.values() for d in row})[:60]
    adv: dict[str, float] = {}
    for tk in tickers:
        vals = [closes[tk][d] * volumes[tk].get(d, 0)
                for d in d0 if closes[tk].get(d) is not None]
        if vals:
            adv[tk] = sum(vals) / len(vals)
    ranked = sorted(adv, key=lambda t: adv[t])
    return set(ranked[: len(ranked) // 2])


def make_cell(window: int, domain: str, variant: str) -> dict[str, Any]:
    """One grid cell as a factorzoo-compatible spec with provenance."""
    days = window * 21
    fid = f"ftl1_mom{window}_{domain}_{variant}"
    desc = (f"S3 family-tree cell: momentum {window}m (skip last month) "
            f"on {domain}"
            + (" (bottom-half avg dollar volume, 60d — proxy for cap)"
               if domain == "smallcap" else "")
            + ({"plain": "",
                "gap_gate": ", gated on positive 252d overnight gap",
                "vol_adj": ", divided by 20d return vol"}[variant]))
    build: FactorBuild = _make_build(days, domain, variant)
    return {"id": fid, "source": "ALPHA_PLAN S3 loop-1 grid",
            "desc": desc, "build": build, "flip": False,
            "provenance": {"program": "S3", "loop": 1,
                           "window": window, "domain": domain,
                           "variant": variant,
                           "parent": "momentum family "
                                     "(v1.4 smallcap momentum)"}}


def _make_build(days: int, domain: str,
                variant: str) -> FactorBuild:
    def build(inp: dict[str, Any]) -> dict[str, dict[str, float]]:
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        rows: dict[str, list[float | None]] = {}
        gaps = overnight_of(series_of(inp["opens"], inp["dates"]), cs) \
            if variant == "gap_gate" else None
        gap = ({tk: rolling_sum(g, 252) for tk, g in gaps.items()}
               if gaps is not None else None)
        vol = {tk: rolling_std(r, 20) for tk, r in rs.items()} \
            if variant == "vol_adj" else None
        small = (_smallcap_set(inp["closes"], inp["volumes"])
                 if domain == "smallcap" else None)
        for tk, r in rs.items():
            cum = _cumulative([0.0 if x is None else x for x in r])
            out: list[float | None] = []
            for i in range(len(r)):
                v = None
                if i >= days and i - 21 >= 0 and cum[i - days] is not None:
                    lo, hi = cum[i - days], cum[i - 21]
                    if lo is not None and hi is not None:
                        v = hi - lo
                if (v is not None and small is not None
                        and tk not in small):
                    v = None                              # domain gate
                if v is not None and gap is not None:
                    g = gap[tk][i] if tk in gap else None
                    v = v if (g is not None and g > 0) else None
                if v is not None and vol is not None:
                    s = vol[tk][i] if tk in vol else None
                    v = v / s if (s is not None and s > 1e-12) else None
                out.append(v)
            rows[tk] = out
        return rows
    return build


def family_grid() -> list[dict[str, Any]]:
    """The full pre-registered grid: 4 windows x 2 domains x 3
    variants = 24 cells, deterministic order (window, domain,
    variant) so loops are comparable."""
    return [make_cell(w, d, v)
            for w in WINDOWS for d in DOMAINS for v in VARIANTS]


def _rolling_sum(xs, win):                    # local alias, keeps import
    from .factorzoo import rolling_sum        # list short in the header
    return rolling_sum(xs, win)


# -- the graveyard: v2 ledger (qsa/graveyard.py) ------------------------------

GRAVEYARD_VERSION = 2                         # re-exported for docs
GATE_VERSION = "stage2-v1"


def run_family_tree(book: OrderBook, inputs: dict[str, Any],
                    budget: int, graveyard_path: Path,
                    queue_priority: int = 7,
                    implementation: str = "v1-volproxy",
                    loop: int = 1,
                    data_plane: dict[str, Any] | None = None,
                    ) -> dict[str, Any]:
    """Run one family-tree loop under graveyard v2.

    Phase order matters: (0) a grown data plane files revival
    proposals for thin cells; (1) pending revisit proposals spend
    their quota of the budget FIRST (the 拍板 20% — looking back is
    budgeted work, not a favour); (2) the fresh sweep skips banned
    cells for free and does NOT auto-retest parked/thin cells (they
    come back through the queue, with a reason).

    Returns the SEALED loop metrics (ALPHA_PLAN); survivors enter
    the gauntlet queue, verdicts land in the tiered graveyard."""
    yard = load_graveyard(graveyard_path)
    if data_plane:
        revive_on_data(yard, data_plane)
    grid_by_key = {cell_key(s["provenance"]["window"],
                            s["provenance"]["domain"],
                            s["provenance"]["variant"]): s
                   for s in family_grid()}
    survivors: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    thin_new: list[str] = []
    skipped_banned = 0
    skipped_parked = 0
    spent = 0

    # -- phase 1: revisits (quota first, reasons on file) ----------------
    revisit_budget = round(budget * REVISE_QUOTA)
    revisits_done: list[dict[str, Any]] = []
    for prop in pending_proposals(yard)[:revisit_budget]:
        spec = grid_by_key.get(prop["cell"])
        if spec is None:                       # cell left the grid
            prop["status"] = "closed"
            prop["outcome"] = "off-grid"
            continue
        if spent + GENERATION_COST > budget:
            break
        spent += GENERATION_COST
        row = evaluate_factor(spec, inputs)
        verdict, reasons = stage2_verdict(row)
        record_verdict(yard, prop["cell"], implementation, verdict,
                       reasons, row, GATE_VERSION, loop)
        prop["status"] = "run"
        prop["outcome"] = verdict
        prop["run_loop"] = loop
        revisits_done.append({"id": prop["id"], "cell": prop["cell"],
                              "by": prop["by"], "outcome": verdict})
        if verdict == "pass":
            survivors.append({"key": prop["cell"], "id": spec["id"],
                              "oos_ic": row["oos_ic"],
                              "icir": row["icir"], "via": "revisit"})

    # -- phase 2: fresh sweep --------------------------------------------
    fresh_tested = 0
    for spec in family_grid():
        p = spec["provenance"]
        key = cell_key(p["window"], p["domain"], p["variant"])
        tier = yard["cells"].get(key, {}).get("tier")
        if tier == "banned":
            skipped_banned += 1                # learning, not silence
            continue
        if tier is not None:                   # parked/thin/revived
            skipped_parked += 1                # queue is the way back
            continue
        if spent + GENERATION_COST > budget:
            continue                           # not generated this loop
        spent += GENERATION_COST
        fresh_tested += 1
        row = evaluate_factor(spec, inputs)
        verdict, reasons = stage2_verdict(row)
        tier_now = record_verdict(yard, key, implementation, verdict,
                                  reasons, row, GATE_VERSION, loop)
        if verdict == "pass":
            survivors.append({"key": key, "id": spec["id"],
                              "oos_ic": row["oos_ic"],
                              "icir": row["icir"], "via": "fresh"})
        elif verdict == "fail":
            failed.append({"key": key, "reasons": reasons,
                           "tier": tier_now})
        else:
            thin_new.append(key)

    # not_generated: grid cells the loop never touched this round
    not_generated = (len(grid_by_key) - skipped_banned - skipped_parked
                     - fresh_tested)
    # survivors -> gauntlet orders (S1's contract, fresh hypothesis)
    gauntlet_orders: list[str] = []
    for s in survivors:
        params: dict[str, Any] = {
            "stage": 2, "admission": STAGE2_ADMISSION,
            "gauntlet_checks": GAUNTLET_CHECKS,
            "origin_program": "S3", "loop": loop, "cell": s["key"],
            "via": s["via"],
            "unwired": ["walk_forward_oos", "fib_budget_accounting",
                        "portfolio_increment"]}
        gid = book.create(
            f"S3 loop-{loop} family-tree survivor: {s['key']} "
            f"(momentum grid cell, stage-2 pass on full sample)",
            params, priority=queue_priority,
            note=f"family-tree: cell {s['key']} survived stage-2 "
                 f"via {s['via']} (oos_ic={s['oos_ic']:.3f}, "
                 f"icir={s['icir']:.1f}); gauntlet checks pending "
                 f"S9/S10 wiring",
            origin="machine")
        book.admit(gid, params)
        book.enqueue(gid)
        gauntlet_orders.append(gid)
    save_graveyard(graveyard_path, yard)
    tiers = graveyard_summary(yard)
    new_bans = sum(1 for f in failed if f["tier"] == "banned")
    survived = len(survivors)
    excluded = len(failed)
    seal: dict[str, Any] = {
        "loop": loop, "program": "S3",
        "closed_at": time.time(),
        "implementation": implementation,
        "gate_version": GATE_VERSION,
        "tested": spent,
        "budget": budget,
        "survived_stage2": survived,
        "survivors_via_revisit": sum(
            1 for s in survivors if s["via"] == "revisit"),
        "revisits": revisits_done,
        "revisit_attempted": len(revisits_done),
        "revisit_passed": sum(1 for r in revisits_done
                              if r["outcome"] == "pass"),
        "gauntlet_passed": 0,               # honest: S9/S10 unwired
        "gauntlet_passed_note": "survivors queued; walk-forward and "
                                "portfolio-increment checks pending "
                                "S9/S10 wiring — not claimed as passed",
        "gauntlet_order_ids": gauntlet_orders,
        "graveyard_savings": skipped_banned,
        "skipped_parked_or_thin": skipped_parked,
        "graveyard_new_fails": excluded,
        "graveyard_new_bans": new_bans,
        "thin_new": thin_new,
        "graveyard_tiers": tiers,
        "cost_per_survivor": (round(spent / survived, 2)
                              if survived else None),
        "cost_per_excluded_family": (round(spent / excluded, 2)
                                     if excluded else
                                     (None if spent else 0.0)),
        "budget_unspent": max(0, budget - spent),
        "grid_not_generated": not_generated,
    }
    return seal


def seal_to_disk(path: Path, seal: dict[str, Any]) -> Path:
    """The loop's SSOT: sealed metrics land as JSON, docs quote it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seal, ensure_ascii=False, indent=1,
                               sort_keys=True), encoding="utf-8")
    return path
