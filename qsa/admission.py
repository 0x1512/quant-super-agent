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
