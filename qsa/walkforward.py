"""Walk-forward gauntlet — ALPHA_PLAN S9: decay detection as a
rolling trigger, wired into the gauntlet chain.

Stage-2 (S6) is a STATIC split: one train/val/oos cut of the
monthly-IC series. It cannot see TIME-LOCAL death — a factor that
works for three years and dies for two passes or fails as a whole,
depending on where the cut lands. The walk-forward check is the
rolling complement, pre-registered here:

* the monthly-IC series is cut into **half-year blocks** (~9 blocks
  on the 58-month sample; min 6 to judge at all);
* **decay trigger (the rolling trigger)**: any rolling 12-month IC
  mean < 0 fires — the factor is locally dead somewhere in the
  sample, and a locally-dead factor is not a portfolio candidate;
* **half-life test**: the mean IC of the LATER half of blocks must
  be >= 50% of the earlier half's (same spirit as stage-2's
  ic_decay_ratio, but measured on blocks, i.e. time-ordered);
* **consistency**: >= 2/3 of blocks with IC > 0.

PASS = no trigger AND half-life AND consistency. Thin data (< 6
blocks) is INCONCLUSIVE — never a judgement call, same discipline
as stage-2.

``run_gauntlet()`` executes the wired checks of a gauntlet order
(stage-2 re-check under the FROZEN admission params, then this
walk-forward check) and settles the order. The two unwired checks
(fib budget accounting, portfolio increment — S10) are stated ON
the settle results as unwired: a pass here means "survived the
wired chain", never "full chain passed".
"""
from __future__ import annotations

from typing import Any

from .admission import STAGE2_ADMISSION, stage2_verdict
from .factorzoo import _finalize, evaluate_factor, monthly_ic_series
from .orders import OrderBook, OrderError

BLOCK_MONTHS = 6                  # half-year blocks
MIN_BLOCKS = 6                    # fewer = unjudgeable
ROLLING_DECAY_WINDOW = 12         # months; mean < 0 fires the trigger
HALF_LIFE_RATIO = 0.5             # later-half mean >= 50% of earlier
CONSISTENCY_SHARE = 2 / 3         # blocks with IC > 0

WALKFORWARD_ADMISSION: dict[str, Any] = {
    "block_months": BLOCK_MONTHS,
    "min_blocks": MIN_BLOCKS,
    "rolling_decay_window": ROLLING_DECAY_WINDOW,
    "rolling_decay_rule": "rolling 12m IC mean < 0 -> locally dead",
    "half_life_ratio": HALF_LIFE_RATIO,
    "consistency_share": CONSISTENCY_SHARE,
}


# -- block statistics -------------------------------------------------------

def block_means(ic_series: list[dict[str, Any]],
                block_months: int = BLOCK_MONTHS) -> list[float]:
    """Mean IC per consecutive block of `block_months` entries."""
    out: list[float] = []
    for i in range(0, len(ic_series), block_months):
        chunk = ic_series[i:i + block_months]
        out.append(sum(x["ic"] for x in chunk) / len(chunk))
    return out


def rolling_decay(ic_series: list[dict[str, Any]],
                  window: int = ROLLING_DECAY_WINDOW,
                  ) -> list[dict[str, Any]]:
    """Every rolling `window`-month stretch whose mean IC < 0 —
    the trigger log (empty = never locally dead)."""
    fired: list[dict[str, Any]] = []
    ics = [x["ic"] for x in ic_series]
    for i in range(len(ics) - window + 1):
        m = sum(ics[i:i + window]) / window
        if m < 0:
            fired.append({"start_index": i,
                          "start_date": ic_series[i]["date"],
                          "end_date": ic_series[i + window - 1]["date"],
                          "mean_ic": round(m, 6)})
    return fired


def walkforward_verdict(
        ic_series: list[dict[str, Any]]) -> tuple[str | None,
                                                  dict[str, Any]]:
    """Pre-registered walk-forward judgement on a monthly-IC series.
    Returns (verdict, detail); verdict in {pass, fail, inconclusive,
    None} with the same no-guessing discipline as stage-2."""
    blocks = block_means(ic_series)
    detail: dict[str, Any] = {
        "n_months": len(ic_series), "n_blocks": len(blocks),
        "block_means": [round(b, 6) for b in blocks],
    }
    if len(blocks) < MIN_BLOCKS:
        detail["reason"] = (f"{len(blocks)} blocks < {MIN_BLOCKS} — "
                            "sample cannot support a walk-forward call")
        return "inconclusive", detail
    trig = rolling_decay(ic_series)
    detail["decay_triggers"] = trig[:8]         # first few, for the card
    detail["n_decay_triggers"] = len(trig)
    if trig:
        detail["reason"] = (
            f"rolling {ROLLING_DECAY_WINDOW}m mean IC < 0 at "
            f"{trig[0]['start_date']}..{trig[0]['end_date']} — "
            "locally dead somewhere in-sample")
        return "fail", detail
    half = len(blocks) // 2
    early = sum(blocks[:half]) / half
    late = sum(blocks[half:]) / (len(blocks) - half)
    detail["early_mean"] = round(early, 6)
    detail["late_mean"] = round(late, 6)
    detail["half_life_ratio"] = (round(late / early, 6)
                                 if early != 0 else None)
    if detail["half_life_ratio"] is None:
        detail["reason"] = "early-block mean IC is 0 — cannot derive ratio"
        return None, detail
    if late < HALF_LIFE_RATIO * early:
        detail["reason"] = (
            f"half-life: late {late:.4f} < {HALF_LIFE_RATIO} * early "
            f"{early:.4f} — decayed across blocks")
        return "fail", detail
    pos = sum(1 for b in blocks if b > 0)
    detail["positive_blocks"] = f"{pos}/{len(blocks)}"
    if pos < CONSISTENCY_SHARE * len(blocks):
        detail["reason"] = (
            f"consistency: only {pos}/{len(blocks)} blocks positive "
            f"(< {CONSISTENCY_SHARE:.0%})")
        return "fail", detail
    detail["reason"] = "no decay trigger; half-life and consistency hold"
    return "pass", detail


# -- the gauntlet executor ----------------------------------------------------

WIRED_CHECKS = ["stage2_composite", "walk_forward_oos"]
UNWIRED_CHECKS = ["fib_budget_accounting", "portfolio_increment"]


def run_gauntlet(book: OrderBook, order_id: str, spec: dict[str, Any],
                 inputs: dict[str, Any]) -> dict[str, Any]:
    """Execute the WIRED gauntlet checks for a queued gauntlet order
    and settle it. The settle verdict is precise about what passed:
    'wired chain' only — the unwired checks stay named in results."""
    o = book.orders.get(order_id)
    if o is None:
        raise OrderError(f"unknown order {order_id}")
    if o["state"] != "queued":
        raise OrderError(
            f"{order_id}: state={o['state']} — the gauntlet runs "
            "queued orders only")
    params = o["history"][0].get("params") or {}
    if params.get("admission") != STAGE2_ADMISSION:
        raise OrderError(
            f"{order_id}: admission params are not the frozen "
            "stage-2 admission — refusing to judge under anything "
            "else")

    row = evaluate_factor(spec, inputs)
    signal = _finalize(spec["build"](inputs), inputs["dates"],
                       spec.get("flip", False))
    ic = monthly_ic_series(inputs["closes"], inputs["dates"], signal)
    v2, reasons2 = stage2_verdict(row)
    results: dict[str, Any] = {
        "stage2_recheck": {"verdict": v2, "reasons": reasons2},
        "row": {k: row.get(k) for k in ("oos_ic", "icir", "n_months",
                                        "top_minus_bottom", "train_ic")}}
    if v2 != "pass":
        # diagnostic only — the verdict stands on stage-2; the
        # walk-forward view is attached so every settled order
        # carries the full picture (what WOULD the rolling gate say)
        signal = _finalize(spec["build"](inputs), inputs["dates"],
                           spec.get("flip", False))
        vw_d, detail_d = walkforward_verdict(
            monthly_ic_series(inputs["closes"], inputs["dates"],
                              signal))
        results["walkforward"] = {"verdict": vw_d, "detail": detail_d,
                                  "diagnostic_only": True}
        results["verdict"] = (
            f"gauntlet FAIL at stage-2 recheck: {'; '.join(reasons2)}")
        results["gauntlet_passed"] = False
        book.start(order_id)
        book.settle(order_id, results)
        return results
    vw, detail = walkforward_verdict(ic)
    results["walkforward"] = {"verdict": vw, "detail": detail}
    if vw == "pass":
        results["gauntlet_passed"] = True
        results["verdict"] = (
            "gauntlet: WIRED chain passed (stage-2 recheck + "
            "walk-forward, no decay trigger); unwired: "
            + ", ".join(UNWIRED_CHECKS))
    else:
        results["gauntlet_passed"] = False
        results["verdict"] = (
            f"gauntlet FAIL at walk-forward: {detail.get('reason')}")
    book.start(order_id)
    book.settle(order_id, results)
    return results
