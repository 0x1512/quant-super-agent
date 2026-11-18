"""Mechanical admission evaluation — the single source of verdict truth.

The verdict of an experiment card is never an opinion: it is the mechanical
evaluation of the hypothesis card's pre-registered thresholds against the
computed metrics. Both the engine (when writing the card) and the verify gate
(when checking it) call :func:`evaluate`, so a "pass" that the numbers do not
support cannot survive the gate (FIB class 7), and neither can a gratuitous
"fail" on passing numbers.
"""
from __future__ import annotations

import operator
from typing import Any

OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
}


def parse_thresholds(admission: dict[str, Any]) -> list[tuple[str, str, float]]:
    """Return [(metric, op, value), ...]; raise ValueError with the offender named."""
    thresholds = admission.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("admission.thresholds: must be an object of {metric: {op, value}}")
    parsed: list[tuple[str, str, float]] = []
    for metric, rule in thresholds.items():
        if not isinstance(rule, dict) or "op" not in rule or "value" not in rule:
            raise ValueError(f"thresholds.{metric}: must be an object with 'op' and 'value'")
        op = rule["op"]
        if op not in OPS:
            raise ValueError(f"thresholds.{metric}: unknown op {op!r} "
                             f"(expected one of {sorted(OPS)})")
        value = rule["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"thresholds.{metric}.value: must be a number, got {value!r}")
        parsed.append((metric, op, float(value)))
    return parsed


def evaluate(admission: dict[str, Any], metrics: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Evaluate pre-registered admission criteria against computed metrics.

    Returns (verdict, reasons). verdict is None when the metrics are
    incomplete — the gate treats that as a hard failure (FIB class 14), never
    as a judgement call.
    """
    reasons: list[str] = []
    required = admission.get("required_metrics", [])
    for m in required:
        if m not in metrics:
            reasons.append(f"missing required metric '{m}'")
    if reasons:
        return None, reasons

    min_obs = admission.get("min_observations")
    if min_obs is not None:
        n = metrics.get("n_dates")
        if not isinstance(n, (int, float)) or n < min_obs:
            return "inconclusive", [
                f"n_dates={n} < min_observations={min_obs} (verdict: inconclusive)"]

    verdict = "pass"
    for metric, op, value in parse_thresholds(admission):
        actual = metrics.get(metric)
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            return None, [f"threshold metric '{metric}' present but not numeric "
                          f"(got {actual!r})"]
        if not OPS[op](actual, value):
            verdict = "fail"
            reasons.append(f"{metric}={actual} fails pre-registered {op} {value}")
    if verdict == "pass" and not reasons:
        reasons = [f"all pre-registered thresholds satisfied over "
                   f"n_dates={metrics.get('n_dates')}"]
    return verdict, reasons


# ----------------------------------------------------------------- stage-2
# ALPHA_PLAN S6 (2026-11-17): the composite survival gate. Stage-1
# (oos_ic > 0.03, the fast lane) is cheap triage — a stage-1 pass
# means nothing by itself. Stage-2 is what a factor must clear before
# the funnel promotes it toward the gauntlet, and the criteria are
# PRE-REGISTERED here (frozen into the promoted order's params by
# qsa/funnel.py — running a promotion with different criteria than
# admitted is a hard error, same teeth as every other gate).
#
# v1 honesty note: top_minus_bottom > 0 is the monotonicity PROXY
# (top-minus-bottom spread in the factor's own direction); full
# 5-quantile monotonicity and rolling last-12-month survival are
# gauntlet-stage checks (ALPHA_PLAN S9/S10 wiring, not yet wired).

STAGE2_ADMISSION: dict[str, Any] = {
    "required_metrics": ["oos_ic", "icir", "n_months",
                         "top_minus_bottom", "train_ic",
                         "ic_decay_ratio"],
    "min_observations": 24,          # months, carried as n_dates
    "thresholds": {
        "oos_ic": {"op": ">", "value": 0.03},
        "icir": {"op": ">", "value": 1.0},
        "top_minus_bottom": {"op": ">", "value": 0.0},
        "train_ic": {"op": ">", "value": 0.0},
        "ic_decay_ratio": {"op": ">=", "value": 0.5},
    },
}


def stage2_verdict(row: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Evaluate a fast-lane evaluation row against STAGE2.

    The only derived metric is ``ic_decay_ratio = oos_ic / train_ic``
    (both same-sign positive by the train_ic gate); a non-positive
    train_ic refuses to derive a ratio and the gate calls it
    inconclusive — never a judgement call.
    """
    derived = dict(row)
    derived["n_dates"] = row.get("n_months")
    train = row.get("train_ic")
    oos = row.get("oos_ic")
    if (isinstance(train, (int, float)) and not isinstance(train, bool)
            and train > 0
            and isinstance(oos, (int, float)) and not isinstance(oos, bool)):
        derived["ic_decay_ratio"] = oos / train
    return evaluate(STAGE2_ADMISSION, derived)
