"""Dispatcher — v1.3.1: one orchestrator, N FactorMiner workers.

The orchestrator splits the candidate space into lightweight JOB
DESCRIPTORS and routes them to a pool of worker processes; each worker
rebuilds the deterministic catalogs locally, scores its jobs through the
exact same functions the sequential path uses, and the dispatcher merges
rows in job order. Spec dicts carry closures (``build`` functions nested
inside catalog builders), which cannot cross a process boundary — so jobs
are ``(kind, …)`` tuples and the workers reconstruct specs from the same
module-level builders. That is also what keeps the two paths identical by
construction.

Determinism contract (load-bearing, tested):

* every job is a pure function of ``(descriptor, inputs, basis)`` — no
  cross-candidate state, no RNG, no wall-clock in the scoring path;
* ``Pool.map`` preserves job order, so each stream returns the same list
  the sequential loop produced, and downstream sorts (stable) see the
  same input — leaderboards and order books stay BYTE-IDENTICAL for any
  ``workers`` value;
* ``workers=1`` is the original in-process loop (it even routes through
  the same ``_run`` executor, just without a pool), so the default path
  never drifts from the parallel one.

On Linux (fork) the shared context is inherited copy-on-write — zero
pickling of the panels; elsewhere the pool initializer pickles it once
per worker, which costs seconds but changes nothing about results.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
from itertools import combinations
from typing import Any

from . import factorlib, factorzoo, offense

Signal = dict[str, dict[str, float]]

_CTX: dict[str, Any] = {}


def default_workers(requested: int | None = None) -> int:
    """Sane default: don't grab all cores uninvited; 4 was the measured
    sweet spot for a 78-candidate space (spawn cost vs balance)."""
    if requested is not None and requested >= 1:
        return requested
    return max(1, min(4, os.cpu_count() or 1))


# v1.4 — job-kind -> crew role (the showcase's 编制名, now in the logs)
ROLE_NAMES: dict[str, str] = {
    "zoo": "GateKeeper",      # baseline: the known-law yardstick
    "lib": "RepoSmith",       # cited factor library
    "ix": "FlowMapper",       # interaction/combination design
    "mut": "SmokeRunner",     # window-variant trial runs
    "gate": "EnvSmith",       # environment & data checks
    "verify": "SmokeProbe",   # self-checks
    "forge": "EnvSmith",      # sandbox gap-filling (v1.4 ⑥)
}


def auto_workers(n_jobs: int, cpu: int | None = None) -> int:
    """v1.4 auto-扩编: pick N from the work at hand, not a fixed guess.

    Policy (pre-registered): N = clamp(ceil(jobs/8), 1, cpu, 16) —
    enough shards per worker to amortize spawn, never more workers than
    cores, capped at 16. Byte-identical for any N (the v1.3.1 contract),
    so this choice cannot move a single number; it only moves the clock.
    """
    cpu = cpu or os.cpu_count() or 1
    if n_jobs <= 0:
        return 1
    return max(1, min((n_jobs + 7) // 8, cpu, 16))


def manifest(run: str, workers: int, jobs_by_kind: dict[str, int],
             elapsed_s: float, out_path: "os.PathLike[str]" | None = None
             ) -> dict[str, Any]:
    """v1.4 run manifest: which role took how many jobs, at what N."""
    m = {"run": run, "workers": workers,
         "jobs_by_kind": dict(jobs_by_kind),
         "jobs_by_role": {ROLE_NAMES.get(k, k): v
                          for k, v in jobs_by_kind.items()},
         "elapsed_s": round(elapsed_s, 1)}
    if out_path is not None:
        from pathlib import Path
        Path(out_path).write_text(
            json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return m


def _init_worker(inputs: dict[str, Any], basis: list[Signal] | None,
                 ranks: list[Signal] | None, names: list[str] | None,
                 available: set[str] | None) -> None:
    _CTX.update(inputs=inputs, basis=basis, ranks=ranks, names=names,
                available=available, zoo_specs=None, lib_specs=None)


def _run(job: tuple) -> dict[str, Any]:
    kind = job[0]
    if kind == "zoo":
        if _CTX["zoo_specs"] is None:
            _CTX["zoo_specs"] = factorzoo.build_catalog()
        return factorzoo.evaluate_factor(_CTX["zoo_specs"][job[1]],
                                         _CTX["inputs"])
    if kind == "lib":
        if _CTX["lib_specs"] is None:
            _CTX["lib_specs"] = factorlib.build_catalog(_CTX["available"])
        return offense.evaluate(_CTX["lib_specs"][job[1]], _CTX["inputs"],
                                _CTX["basis"])
    if kind == "ix":
        _, i, j, op = job
        return offense.score_interaction(_CTX["ranks"], i, j, op,
                                         _CTX["names"], _CTX["inputs"],
                                         _CTX["basis"])
    if kind == "mut":
        _, family, win = job
        return offense.evaluate(factorlib.FAMILIES[family](win),
                                _CTX["inputs"], _CTX["basis"])
    raise ValueError(f"dispatch: unknown job kind {kind!r}")


def _map(jobs: list[tuple], ctx_args: tuple, workers: int) -> list:
    if workers <= 1 or len(jobs) <= 1:
        _init_worker(*ctx_args)
        return [_run(j) for j in jobs]
    if "fork" in mp.get_all_start_methods():
        _init_worker(*ctx_args)          # children inherit via fork COW
        pool_ctx = mp.get_context("fork")
        with pool_ctx.Pool(workers) as pool:
            return pool.map(_run, jobs, chunksize=1)
    pool_ctx = mp.get_context()          # spawn: pickle ctx once/worker
    with pool_ctx.Pool(workers, initializer=_init_worker,
                       initargs=ctx_args) as pool:
        return pool.map(_run, jobs, chunksize=1)


def _stitch(jobs: list[tuple], run_fn, kind: str, ckpt) -> list:
    """SUPERAGENT_PLAN #2: run only the jobs the checkpoint is missing,
    then stitch cached + fresh rows back in job order.

    ``run_fn(todo)`` must return rows aligned with ``todo``. The stitch
    preserves the exact job order ``_map`` would have produced, so a
    resumed run is byte-identical to an uninterrupted one by
    construction (each job is a pure function of descriptor+inputs).

    """
    if ckpt is None:
        out = run_fn(jobs)
    else:
        cached = {j: ckpt.get(kind, j) for j in jobs}
        todo = [j for j in jobs if cached[j] is None]
        fresh = run_fn(todo) if todo else []
        it = iter(fresh)
        out = []
        for j in jobs:
            row = cached[j] if cached[j] is not None else next(it)
            if cached[j] is None:
                ckpt.put(kind, j, row)
            out.append(row)
    return out


def _crew_record(crew_dir, kind, jobs, rows, ckpt, ck0) -> None:
    """SUPERAGENT_PLAN #5: leave a session card — role + job keys +
    rows + checkpoint accounting; a strict superset of the rows."""
    if crew_dir is None:
        return
    from . import crew
    meta = {"checkpoint_hits": (ckpt.hits - ck0[0]) if ckpt else 0,
            "checkpoint_misses": (ckpt.misses - ck0[1]) if ckpt else 0}
    crew.record(crew_dir, kind, jobs, rows, meta)


# ------------------------------------------------------------- the streams


def zoo(closes: dict[str, dict[str, float]],
        opens: dict[str, dict[str, float]],
        volumes: dict[str, dict[str, float]], dates: list[str],
        workers: int = 1, ckpt=None, crew_dir=None) -> list[dict[str, Any]]:
    """factorzoo.run_zoo with a worker pool: same rows, same sort."""
    inputs = {"closes": closes, "opens": opens, "volumes": volumes,
              "dates": dates}
    jobs = [("zoo", i) for i in range(len(factorzoo.build_catalog()))]
    ctx = (inputs, None, None, None, None)
    ck0 = (ckpt.hits, ckpt.misses) if ckpt is not None else None
    out = _stitch(jobs, lambda todo: _map(todo, ctx, workers), "zoo", ckpt)
    out.sort(key=factorzoo.zoo_sort_key, reverse=True)
    # the card records the SORTED rows — exactly what the stream returns
    _crew_record(crew_dir, "zoo", jobs, out, ckpt, ck0)
    return out


def library(inputs: dict[str, Any], basis: list[Signal],
            workers: int = 1, ckpt=None,
            crew_dir=None) -> list[dict[str, Any]]:
    """Library scan under the residual objective, parallel; returns rows
    in catalog order (the caller sorts, as before)."""
    available = {k for k in inputs if k != "dates"}
    jobs = [("lib", i)
            for i in range(len(factorlib.build_catalog(available)))]
    ctx = (inputs, basis, None, None, available)
    ck0 = (ckpt.hits, ckpt.misses) if ckpt is not None else None
    out = _stitch(jobs, lambda todo: _map(todo, ctx, workers), "lib",
                  ckpt)
    _crew_record(crew_dir, "lib", jobs, out, ckpt, ck0)
    return out


def interactions(basis_specs: list[dict[str, Any]],
                 inputs: dict[str, Any], basis: list[Signal],
                 top_k: int = 4, workers: int = 1,
                 ckpt=None, crew_dir=None) -> list[dict[str, Any]]:
    """offense.interactions with a worker pool; same rows, same order."""
    dates = inputs["dates"]
    ranks = [offense.cs_rank_signal(s, dates) for s in basis]
    names = [sp["id"] for sp in basis_specs[:top_k]]
    jobs = [("ix", i, j, op)
            for i, j in combinations(range(min(top_k, len(ranks))), 2)
            for op in ("product", "ratio", "spread")]
    ctx = (inputs, basis, ranks, names, None)
    ck0 = (ckpt.hits, ckpt.misses) if ckpt is not None else None
    out = _stitch(jobs, lambda todo: _map(todo, ctx, workers), "ix",
                  ckpt)
    _crew_record(crew_dir, "ix", jobs, out, ckpt, ck0)
    return out


def mutations(month_families: list[str], day_families: list[str],
              month_wins: list[int], day_wins: list[int],
              inputs: dict[str, Any], basis: list[Signal],
              workers: int = 1, ckpt=None,
              crew_dir=None) -> list[dict[str, Any]]:
    """offense.mutations with a worker pool; same rows, same order."""
    jobs = [("mut", nm, w) for nm in month_families
            if nm in factorlib.FAMILIES for w in month_wins]
    jobs += [("mut", nm, w) for nm in day_families
             if nm in factorlib.FAMILIES for w in day_wins]
    ctx = (inputs, basis, None, None, None)
    ck0 = (ckpt.hits, ckpt.misses) if ckpt is not None else None
    out = _stitch(jobs, lambda todo: _map(todo, ctx, workers), "mut",
                  ckpt)
    _crew_record(crew_dir, "mut", jobs, out, ckpt, ck0)
    return out
