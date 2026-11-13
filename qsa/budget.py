"""Budget estimators — every term of the budget equation, read off pipeline
state (v0.7).

The thesis budget equation is

    E[IR] ≈ ĪC · sqrt(B_eff) · P̂ · TC · e^{(λℓ − δ)·t}

and the v0.7 discipline is that *no term of it is asserted*: each one has a
readable estimator over artifacts the pipeline already produces — the
experiment registry (B, the trial count), the settlement ledger (ĪC, TC, the
decay slope standing in for λℓ−δ), and the planted/noise world pair (P̂ via
the α-frontier, because the true share of real effects is unobservable in
production and can only be anchored in worlds where the truth is planted).

What each estimator is, mechanically:

* **B** — ``registry`` trial count across families. The ledger's deflation
  already consumes it; here it is simply read out.
* **ĪC (ic_hat)** — mean realized rank IC over *held* settled claims: the
  information coefficient the pipeline actually delivered after admission,
  not the one it claimed.
* **TC** — the calibration report's cost block: gross vs net spread at the
  world's per-side cost model, on settled horizons.
* **λℓ−δ (decay_slope)** — OLS slope of realized on claimed across claimed
  bins. Slope 1 = claims neither decay nor compound; slope < 1 = leakage
  faster than compounding (the exponent is negative for this pipeline).
* **P̂ (frontier)** — measured on planted/noise world pairs at a grid of
  admission bars: power (planted admitted share) vs false-positive rate
  (noise admitted share). P̂ = power / (power + fpr) at 50/50 prevalence —
  an anchor, not a production observable; the honest statement of that
  limitation is the sensitivity grid itself.

``envelope`` turns the frontier into the breadth/verification tradeoff: at
deflation floor z(N), per-trial discovery falls while sqrt(N) breadth grows;
``discovery(N) · P̂(N) · sqrt(N)`` is the envelope (breadth net of
verification) whose peak is the operating point.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .deflation import bonferroni_tstat_floor
from .settlement import SettlementLedger, calibration_report


def read_budget(ledger_path: Path,
                registry: Any = None) -> dict[str, Any]:
    """Read the budget equation's terms off a settlement ledger (and,
    optionally, the experiment registry for the trial count B)."""
    ledger = (ledger_path if isinstance(ledger_path, SettlementLedger)
              else SettlementLedger(Path(ledger_path)))
    report = calibration_report(ledger)

    settled = [en for en in ledger.entries
               if en.get("outcome") in ("held", "fell_short")]
    held = [en for en in settled if en["outcome"] == "held"]

    ic_hat = None
    if held:
        ics = [float(en["realized"]["rankic_mean"]) for en in held]
        ic_hat = round(sum(ics) / len(ics), 6)

    # B: every trial the ledger knows about — settled claims plus attempts
    # that never became claims (unverifiable). The registry, when given,
    # knows the attempts the ledger never saw; prefer it.
    b_trials = None
    if registry is not None:
        try:
            families = {en.get("family") for en in registry.entries
                        if en.get("family")}
            b_trials = sum(registry.n_trials(f) for f in families
                           if f is not None)
        except (AttributeError, TypeError):
            b_trials = None
    if b_trials is None:
        b_trials = len(ledger.entries)

    p_hat = None
    by_truth = report.get("by_truth") or {}
    n_planted = (by_truth.get("planted") or {}).get("n", 0)
    n_noise = (by_truth.get("noise") or {}).get("n", 0)
    if n_planted + n_noise:
        p_hat = round(n_planted / (n_planted + n_noise), 6)

    return {
        "B": b_trials,
        "n_settled": report["n_settled"],
        "held": report["held"],
        "fell_short": report["fell_short"],
        "ic_hat": ic_hat,
        "p_hat_planted_anchor": p_hat,
        "decay_slope": report.get("decay_slope"),
        "horizon_days": report.get("horizon_days"),
        "tc": report.get("tc"),
    }


def frontier(tstats_planted: list[float], tstats_noise: list[float],
             floors: list[float]) -> list[dict[str, Any]]:
    """The α-frontier: at each admission floor z, power and false-positive
    rate measured on the planted/noise world pair (truth known by
    construction), and P̂ = power / (power + fpr) at 50/50 prevalence."""
    rows: list[dict[str, Any]] = []
    for z in floors:
        power = (sum(1 for t in tstats_planted if t >= z)
                 / len(tstats_planted)) if tstats_planted else 0.0
        fpr = (sum(1 for t in tstats_noise if t >= z)
               / len(tstats_noise)) if tstats_noise else 0.0
        denom = power + fpr
        p_hat = (power / denom) if denom else 1.0
        rows.append({"floor": round(z, 4), "power": round(power, 6),
                     "fpr": round(fpr, 6), "p_hat": round(p_hat, 6)})
    return rows


def envelope(tstats_planted: list[float], tstats_noise: list[float],
             ns: range | list[int]) -> list[dict[str, Any]]:
    """The breadth/verification envelope: at N cumulative trials the
    Bonferroni floor z(N) suppresses marginal discoveries while sqrt(N)
    breadth grows. The envelope value is discovery(N) · P̂(N) · sqrt(N) —
    breadth counted net of verification: an un-deflated pipeline has
    breadth but no credibility, and the P̂ factor prices exactly that.
    The value peaks somewhere; that peak is the operating point the budget
    equation predicts. Deterministic."""
    rows: list[dict[str, Any]] = []
    for n in ns:
        if n < 1:
            continue
        z = bonferroni_tstat_floor(int(n))
        power = (sum(1 for t in tstats_planted if t >= z)
                 / len(tstats_planted)) if tstats_planted else 0.0
        fpr = (sum(1 for t in tstats_noise if t >= z)
               / len(tstats_noise)) if tstats_noise else 0.0
        denom = power + fpr
        p_hat = (power / denom) if denom else 1.0
        rows.append({"N": int(n), "floor": round(z, 4),
                     "discovery": round(power, 6), "fpr": round(fpr, 6),
                     "p_hat": round(p_hat, 6),
                     "envelope": round(power * p_hat * (n ** 0.5), 6)})
    return rows
