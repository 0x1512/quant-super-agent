"""Recompute — the honest half of followups (v1.4).

When a follow-up can change SCORES (universe swap, window change), the
affected streams are re-run through the same dispatcher the full run
uses, on the same fingerprinted snapshot — filtered per the instruction.
Nothing is extrapolated: rows that were not recomputed are labelled
reused, rows that were are labelled recomputed, and the diff report says
which is which. A follow-up that silently mixed stale and fresh scores
would be the incremental lie; this module exists so that never happens.

Universe policies (pre-registered, no discretion):

* ``exclude=smallcap`` — drop the bottom quartile of tickers by mean
  daily amount (成交额), the same "小盘" cut the fork card BB-FORK-02
  reasons about;
* ``name=smallcap`` — keep only that bottom quartile.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from . import dispatch, factorlib, factorzoo

Signal = dict[str, dict[str, float]]


def _mean_amounts(amounts: dict[str, dict[str, float]]) -> dict[str, float]:
    return {tk: (sum(row.values()) / len(row) if row else 0.0)
            for tk, row in amounts.items()}


def filter_universe(inputs: dict[str, Any],
                    universe: dict[str, Any]) -> dict[str, Any]:
    """Return a NEW inputs dict restricted to the policy's tickers."""
    tickers = set(inputs["closes"])
    if universe.get("exclude") == "smallcap" or universe.get("name") == "smallcap":
        means = _mean_amounts(inputs["amounts"])
        ranked = sorted(tickers, key=lambda tk: -means.get(tk, 0.0))
        cut = max(1, len(ranked) // 4)
        small = set(ranked[len(ranked) - cut:])
        keep = (tickers - small) if universe.get("exclude") == "smallcap" \
            else small
    else:
        keep = tickers
    out = {k: {tk: row for tk, row in panel.items() if tk in keep}
           for k, panel in inputs.items() if k != "dates"}
    out["dates"] = inputs["dates"]
    return out


def load_inputs(prev_dir: Path, full: bool = True) -> dict[str, Any]:
    from . import snapshot
    snap = prev_dir / "snap"
    inputs = {
        "closes": snapshot.load_closes(snap),
        "opens": snapshot.load_opens(snap),
        "volumes": snapshot.load_volumes(snap),
        "highs": snapshot.load_highs(snap),
        "lows": snapshot.load_lows(snap),
        "amounts": snapshot.load_amounts(snap),
        "vwaps": snapshot.load_vwaps(snap),
    }
    dates = sorted({d for row in inputs["closes"].values() for d in row})
    if not full:
        keep = set(dates[:300])
        dates = dates[:300]
        inputs = {k: {tk: {d: v for d, v in row.items() if d in keep}
                      for tk, row in panel.items()}
                  for k, panel in inputs.items()}
    inputs["dates"] = dates
    return inputs


def run(prev: dict[str, Any], ins: dict[str, Any]) -> dict[str, Any]:
    prev_dir: Path = prev["work_dir"]
    t0 = time.perf_counter()
    cfg = prev["config"]
    inputs = filter_universe(load_inputs(prev_dir), ins["universe"])
    n_tk, n_d = len(inputs["closes"]), len(inputs["dates"])
    workers = dispatch.auto_workers(_estimate_jobs(inputs))

    # basis rebuilt from the SAME zoo catalog on the filtered universe
    zoo_rows = dispatch.zoo(inputs["closes"], inputs["opens"],
                            inputs["volumes"], inputs["dates"],
                            workers=workers)
    surv = [r for r in zoo_rows if r["oos_ic"] is not None
            and r["oos_ic"] > 0.03]
    surv.sort(key=lambda r: -r["oos_ic"])
    basis_specs = [next(s for s in factorzoo.build_catalog()
                        if s["id"] == r["id"]) for r in surv]
    basis = [factorzoo._finalize(s["build"](inputs), inputs["dates"],
                                 s["flip"]) for s in basis_specs]

    rows: list[dict[str, Any]] = []
    streams_rerun = ["zoo(basis)"]
    if cfg.get("streams", {}).get("library", True):
        rows += dispatch.library(inputs, basis, workers=workers)
        streams_rerun.append("library")
    if cfg.get("streams", {}).get("interactions", True):
        rows += dispatch.interactions(basis_specs, inputs, basis,
                                      top_k=cfg.get("top_k", 4),
                                      workers=workers)
        streams_rerun.append("interactions")
    if cfg.get("streams", {}).get("mutations", True):
        mf, df, mw, dw = cfg.get("month_families"), cfg.get("day_families"), \
            cfg.get("month_wins"), cfg.get("day_wins")
        rows += dispatch.mutations(mf, df, mw, dw, inputs, basis,
                                   workers=workers)
        streams_rerun.append("mutations")

    thresh = ins.get("thresh", cfg["thresh"])
    min_months = ins.get("min_months", cfg["min_months"])
    from .followup import _winners_from
    new = _winners_from(rows, thresh, min_months)
    old_ids = {r["id"] for r in _winners_from(
        prev["rows"], cfg["thresh"], cfg["min_months"])}
    new_ids = {r["id"] for r in new}
    basis_digest = hashlib.sha256(
        json.dumps([r["id"] for r in surv]).encode()).hexdigest()[:10]
    return {
        "mode": "recompute", "instruction": ins["raw"],
        "universe": ins["universe"],
        "universe_tickers": n_tk, "n_dates": n_d,
        "basis_digest": basis_digest,
        "streams_rerun": streams_rerun,
        "n_candidates": len(rows), "n_winners": len(new),
        "kept": sorted(new_ids & old_ids), "added": sorted(new_ids - old_ids),
        "dropped": sorted(old_ids - new_ids),
        "rows_reused": 0, "rows_rescored": len(rows),
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "winners": [r["id"] for r in new],
    }


def _estimate_jobs(inputs: dict[str, Any]) -> int:
    available = {k for k in inputs if k != "dates"}
    n = len(factorzoo.build_catalog()) + len(factorlib.build_catalog(available))
    n += 3 * 4 * 3          # interactions upper bound (top_k=4)
    n += 2 * 5 + 4 * 5      # mutations
    return n
