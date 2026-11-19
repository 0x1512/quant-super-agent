"""Parallel catalog evaluation — process-pool sharding by factor.

The catalog's build functions are closures inside ``build_catalog()``
(not picklable), and the inputs panels are large dicts (expensive to
pickle per task). Both problems disappear with the fork start method:
workers inherit the parent's memory, so the pool initializer stashes
the inputs once and workers rebuild their own catalog by spec id.

On platforms without fork (or with ``workers=1``) the helper degrades
to the serial fast path — callers get the same answers everywhere,
only the wall clock changes. Determinism is untouched: each factor is
evaluated independently, so sharding cannot reorder any computation
inside a factor.
"""
from __future__ import annotations

import os
from typing import Any

from .matrix import evaluate_factor_fast

_WORKER_INPUTS: dict[str, Any] | None = None
_WORKER_SPECS: dict[str, dict[str, Any]] | None = None


def _init_worker(inputs: dict[str, Any]) -> None:
    global _WORKER_INPUTS, _WORKER_SPECS
    from . import factorzoo
    _WORKER_INPUTS = inputs
    _WORKER_SPECS = {s["id"]: s for s in factorzoo.build_catalog()}


def _eval_by_id(spec_id: str) -> dict[str, Any]:
    spec = _WORKER_SPECS[spec_id]                    # type: ignore[index]
    return evaluate_factor_fast(spec, _WORKER_INPUTS)  # type: ignore[arg-type]


def _default_workers(n_tasks: int) -> int:
    env = os.environ.get("QSA_WORKERS")
    if env and env.isdigit() and int(env) > 0:
        return min(int(env), n_tasks)
    try:
        import multiprocessing as mp
        return max(1, min(mp.cpu_count() - 1, n_tasks))
    except Exception:                                # pragma: no cover
        return 1


def evaluate_specs_parallel(specs: list[dict[str, Any]],
                            inputs: dict[str, Any],
                            workers: int | None = None
                            ) -> dict[str, dict[str, Any]]:
    """Evaluate many catalog factors in parallel; returns {spec_id: row}.

    Identical results to running evaluate_factor_fast serially (the
    tests assert this on the fixture). Falls back to serial when
    fork is unavailable or the pool is not worth the spawn cost.
    """
    if not specs:
        return {}
    n_workers = workers or _default_workers(len(specs))
    use_pool = n_workers > 1 and len(specs) > 1
    if use_pool:
        try:
            import multiprocessing as mp
            ctx = mp.get_context("fork")            # POSIX only, by design
            with ctx.Pool(n_workers, initializer=_init_worker,
                          initargs=(inputs,)) as pool:
                rows = pool.map(_eval_by_id, [s["id"] for s in specs],
                                chunksize=1)
            return {r["id"]: r for r in rows}
        except (ValueError, ImportError, OSError):
            pass                                     # no fork here — fall back
    return {spec["id"]: evaluate_factor_fast(spec, inputs)
            for spec in specs}
