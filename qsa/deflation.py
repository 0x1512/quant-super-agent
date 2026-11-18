"""Multiple-testing deflation — the ledger's credibility dividend.

An agent that mines factors at machine speed also *tests* factors at machine
speed: with N independent looks at the data, the bar for "this is not noise"
must rise. The registry knows N exactly (it counted every settled experiment
in the family), so admission can be deflated mechanically instead of by
trust: over and above the hypothesis's own thresholds, a passing verdict
additionally requires the t-statistic to clear the Bonferroni z-floor for N
trials at family-wise alpha 0.05.

No opinions, no per-run tuning — the same N always produces the same floor.
"""
from __future__ import annotations

from statistics import NormalDist
from typing import Any

from .admission import evaluate, parse_thresholds

ALPHA = 0.05


def bonferroni_tstat_floor(n_trials: int, alpha: float = ALPHA) -> float:
    """Two-sided Bonferroni z-threshold for *n_trials* looks."""
    if n_trials <= 1:
        return 0.0
    p = alpha / (2 * n_trials)
    if p >= 0.5:
        return 0.0
    return NormalDist().inv_cdf(1 - p)


def _direction(admission: dict[str, Any]) -> str:
    """Which sign of IC does this hypothesis hope for? 'pos' / 'neg' / 'any'."""
    want_pos = want_neg = False
    for metric, op, _value in parse_thresholds(admission):
        if metric != "rankic_mean":
            continue
        if op in (">=", ">"):
            want_pos = True
        if op in ("<=", "<"):
            want_neg = True
    if want_pos and not want_neg:
        return "pos"
    if want_neg and not want_pos:
        return "neg"
    return "any"


def deflated_evaluate(admission: dict[str, Any], metrics: dict[str, Any],
                      n_trials: int) -> tuple[str | None, list[str]]:
    """:func:`qsa.admission.evaluate`, plus the Bonferroni floor at N trials.

    With a single trial this is exactly the plain evaluation; deflation only
    bites when the ledger says the family has been mined before.
    """
    verdict, reasons = evaluate(admission, metrics)
    if verdict is None:
        return None, reasons
    if n_trials >= 2:
        t = metrics.get("rankic_tstat")
        if isinstance(t, bool) or not isinstance(t, (int, float)):
            return None, ["deflation requires 'rankic_tstat' in metrics "
                          "once a family has multiple trials"]
        floor = bonferroni_tstat_floor(n_trials)
        direction = _direction(admission)
        needed = t >= floor if direction == "pos" else (
            t <= -floor if direction == "neg" else abs(t) >= floor)
        if not needed:
            verdict = "fail"
            sign = {"pos": f"rankic_tstat={t} < floor",
                    "neg": f"rankic_tstat={t} > -floor",
                    "any": f"|rankic_tstat|={t} < floor"}[direction]
            reasons = list(reasons) + [
                f"deflation: {sign} {round(floor, 4)} (Bonferroni at N={n_trials}, "
                f"family-wise alpha={ALPHA}) — earlier trials in this family "
                f"raise the bar"]
    return verdict, reasons
