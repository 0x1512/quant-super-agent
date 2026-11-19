"""Successive halving — a compute-scheduling policy, never a gate.

Searching a large candidate pool spends most of its wall clock on
factors that will die anyway. Successive halving (the Hyperband
family) evaluates candidates on growing prefixes of the sample and
only promotes a fraction at each level; survivors reach the full
sample.

SEMANTIC DISCIPLINE: halving allocates compute, it does not judge.
No verdict, admission, or graveyard sentence may cite a halving
level — every research verdict still comes from the full-sample
pipeline with the frozen gates. A candidate killed at a prefix level
is "not worth the compute this round", never "refused": the audit
log keeps it eligible for a later full run.
"""
from __future__ import annotations

from typing import Any, Callable

from .matrix import evaluate_factor_fast

DEFAULT_FRACTIONS = (0.25, 0.5, 1.0)
DEFAULT_KEEP = 0.5


def _prefix_inputs(inputs: dict[str, Any], fraction: float
                   ) -> dict[str, Any] | None:
    """The first `fraction` of trade dates (panels cut to the prefix)."""
    dates = inputs["dates"]
    k = int(len(dates) * fraction)
    if k < 20:                          # too thin to triage anything
        return None
    keep = set(dates[:k])

    def cut(panel):
        return {tk: {d: v for d, v in row.items() if d in keep}
                for tk, row in panel.items()}

    return {**inputs, "closes": cut(inputs["closes"]),
            "opens": cut(inputs.get("opens", {})),
            "volumes": cut(inputs.get("volumes", {})),
            "dates": dates[:k]}


def successive_halving(specs: list[dict[str, Any]],
                       inputs: dict[str, Any],
                       fractions: tuple[float, ...] = DEFAULT_FRACTIONS,
                       keep: float = DEFAULT_KEEP,
                       floor: float = 0.0,
                       evaluator: Callable = evaluate_factor_fast
                       ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Triage `specs` through growing sample prefixes.

    At each level (except the last, which is the caller's full-sample
    stage): evaluate the pool on the prefix, drop candidates whose
    prefix ``oos_ic`` is below `floor`, then keep only the top `keep`
    fraction by prefix ``oos_ic``. Returns (survivors, audit_log);
    the log records every level's counts and the cut line, so a
    human can always ask "who was dropped where, at what number".
    """
    pool = list(specs)
    log: list[dict[str, Any]] = []
    for level, fraction in enumerate(fractions):
        if len(pool) <= 1 or fraction >= 1.0:
            break
        prefix = _prefix_inputs(inputs, fraction)
        if prefix is None:
            continue
        rows = [(spec, evaluator(spec, prefix)) for spec in pool]
        scored = [(spec, row.get("oos_ic"))
                  for spec, row in rows if row.get("oos_ic") is not None]
        scored.sort(key=lambda t: (t[1] is None, t[1] if t[1] is not None else 0.0),
                    reverse=True)
        above = [(s, v) for s, v in scored if v is not None and v >= floor]
        n_keep = max(1, int(len(above) * keep))
        kept = above[:n_keep]
        pool = [s for s, _ in kept]
        cut_line = kept[-1][1] if kept else None
        log.append({
            "level": level, "fraction": fraction,
            "n_dates": len(prefix["dates"]),
            "evaluated": len(rows), "above_floor": len(above),
            "kept": len(pool), "cut_oos_ic": cut_line,
            "dropped": sorted(s["id"] for s, v in scored
                              if s["id"] not in {x["id"] for x in pool}),
        })
    return pool, log
