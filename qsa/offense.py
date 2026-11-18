"""Offense — candidate production with a residual objective (v1.3).

The v1.1 zoo ranked candidates by raw IC; on a sample where 24 public
factors share two or three latent axes, that mostly re-discovers clones.
This module changes WHAT we optimize, then adds two throughput engines:

* **residual objective** — orthogonalize every candidate against the
  surviving factors (per-date cross-sectional OLS with intercept) and
  rank by the residual signal's IC. A new candidate earns its place by
  explaining return variance the survivors do not, which is the only
  thing a portfolio actually gains from it.
* **interaction mining** — pairwise products/ratios/spreads of the
  survivors' rank signals (scale-free), each residualized and evaluated:
  conditional structures (``a works when b is low``) without writing
  them by hand.
* **mutation search** — window sweeps over the parameterized families
  in qsa/factorlib.FAMILIES; every mutant is residualized too.

Everything still flows through the same fast lane (monthly rank-IC,
triple-gate partitions) — throughput changes the candidates, never the
scoring, and the registry/deflation discipline still counts every look.
"""
from __future__ import annotations

import math
from itertools import combinations
from typing import Any

from .factorlib import window_variants
from .factorzoo import series_of
from .replication import ic_summary, monthly_ic_series

Signal = dict[str, dict[str, float]]


# ------------------------------------------------------------------ residual


def _solve(A: list[list[float]], b: list[float]) -> list[float] | None:
    """Small dense Gaussian elimination with partial pivoting."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for r in range(n):
            if r == col:
                continue
            f = M[r][col] / pv
            if f:
                for c in range(col, n + 1):
                    M[r][c] -= f * M[col][c]
    return [M[i][n] / M[i][i] for i in range(n)]


def residualize(candidate: Signal, basis: list[Signal],
                min_names: int = 12) -> Signal:
    """Per-date cross-sectional OLS of the candidate on the basis
    signals (with intercept); returns the residual signal. Dates with
    fewer than ``min_names`` common names are dropped — regression on
    3 stocks is noise dressed as math."""
    if not basis:
        return candidate
    out: Signal = {}
    dates = sorted({d for row in candidate.values() for d in row})
    for d in dates:
        keep: list[str] = []
        ys: list[float] = []
        rows: list[list[float]] = []
        for tk, row in candidate.items():
            y = row.get(d)
            if y is None:
                continue
            xs = [sig.get(tk, {}).get(d) for sig in basis]
            if any(x is None for x in xs):
                continue
            keep.append(tk)
            ys.append(y)
            rows.append([1.0] + xs)
        if len(keep) < max(min_names, len(basis) + 2):
            continue
        k = len(rows[0])
        A = [[sum(r[a] * r[b] for r in rows) for b in range(k)]
             for a in range(k)]
        bb = [sum(r[a] * y for r, y in zip(rows, ys)) for a in range(k)]
        beta = _solve(A, bb)
        if beta is None:
            continue
        for tk, r, y in zip(keep, rows, ys):
            pred = sum(w * x for w, x in zip(beta, r))
            out.setdefault(tk, {})[d] = y - pred
    return out


# --------------------------------------------------------- fast-lane scoring


def eval_signal(sig: Signal, closes: dict[str, dict[str, float]],
                dates: list[str], fid: str, source: str, desc: str
                ) -> dict[str, Any]:
    """Same fast lane as the zoo (monthly rank-IC, triple-gate) on an
    arbitrary precomputed signal — residual or otherwise."""
    ic = monthly_ic_series(closes, dates, sig)
    summ = ic_summary(ic) if ic else {"ic_mean": None, "icir": None}
    n = len(ic)

    def mean_ic(seq):
        return (sum(x["ic"] for x in seq) / len(seq)) if seq else None

    k1, k2 = max(1, int(n * 0.6)), max(1, int(n * 0.8))
    return {"id": fid, "source": source, "desc": desc, "n_months": n,
            "ic_mean": summ.get("ic_mean"), "icir": summ.get("icir"),
            "train_ic": mean_ic(ic[:k1]), "val_ic": mean_ic(ic[k1:k2]),
            "oos_ic": mean_ic(ic[k2:]),
            "ic_positive_share": (sum(1 for x in ic if x["ic"] > 0) / n)
            if n else None}


# --------------------------------------------------------- ranking helpers


def cs_rank_signal(sig: Signal, dates: list[str]) -> Signal:
    """Cross-sectional percentile rank per date (scale-free blend base)."""
    rows = series_of(sig, dates)
    ranked: dict[str, list[float | None]] = {tk: [None] * len(dates)
                                             for tk in rows}
    tickers = sorted(rows)
    for i in range(len(dates)):
        vals = sorted((rows[tk][i], k) for k, tk in enumerate(tickers)
                      if rows[tk][i] is not None)
        m = len(vals)
        for j, (v, k) in enumerate(vals):
            ranked[tickers[k]][i] = (j + 0.5) / m
    return {tk: {dates[i]: x for i, x in enumerate(seq) if x is not None}
            for tk, seq in ranked.items()}


def _sparse_from_rows(rows: dict[str, list[float | None]],
                      dates: list[str]) -> Signal:
    return {tk: {dates[i]: x for i, x in enumerate(seq) if x is not None}
            for tk, seq in rows.items()}


def evaluate(spec: dict[str, Any], inputs: dict[str, Any],
             basis: list[Signal] | None = None) -> dict[str, Any]:
    """Build a spec, optionally residualize, fast-lane score."""
    sig = spec["build"](inputs)
    if basis:
        sig = residualize(sig, basis)
        tag = " (residual)"
    else:
        tag = ""
    return eval_signal(sig, inputs["closes"], inputs["dates"],
                       spec["id"], spec["source"],
                       spec["desc"] + tag)


# ------------------------------------------------------------- interactions


def interaction_signal(a: Signal, b: Signal, op: str) -> Signal:
    """Blend two rank signals: product / ratio / spread (scale-free)."""
    sig: Signal = {}
    for tk in a:
        for d, x in a[tk].items():
            y = b.get(tk, {}).get(d)
            if y is None:
                continue
            if op == "product":
                v = x * y
            elif op == "ratio":
                v = x / y if y > 1e-9 else None
            else:
                v = x - y
            if v is not None:
                sig.setdefault(tk, {})[d] = v
    return sig


def score_interaction(ranks: list[Signal], i: int, j: int, op: str,
                      names: list[str], inputs: dict[str, Any],
                      basis: list[Signal]) -> dict[str, Any]:
    """Score one (rank_i, rank_j, op) blend — the unit of work the v1.3.1
    dispatcher ships to a worker process."""
    sig = interaction_signal(ranks[i], ranks[j], op)
    res = residualize(sig, basis)
    return eval_signal(res, inputs["closes"], inputs["dates"],
                       f"ix:{names[i]}×{names[j]}:{op}",
                       "interaction of survivors",
                       f"rank({names[i]}) {op} rank({names[j]}), "
                       "residualized")


def interactions(basis_specs: list[dict[str, Any]],
                 inputs: dict[str, Any], basis: list[Signal],
                 top_k: int = 4) -> list[dict[str, Any]]:
    """Pairwise products / ratios / spreads of the top-k survivors'
    rank signals, each residualized against the full survivor basis and
    fast-lane scored."""
    dates = inputs["dates"]
    ranks = [cs_rank_signal(s, dates) for s in basis]
    names = [sp["id"] for sp in basis_specs[:top_k]]
    return [score_interaction(ranks, i, j, op, names, inputs, basis)
            for (i, _a), (j, _b) in combinations(enumerate(ranks[:top_k]),
                                                 2)
            for op in ("product", "ratio", "spread")]


# ---------------------------------------------------------------- mutations


def mutations(month_families: list[str], day_families: list[str],
              month_wins: list[int], day_wins: list[int],
              inputs: dict[str, Any], basis: list[Signal]
              ) -> list[dict[str, Any]]:
    """Window sweeps over factorlib's parameterized families, each
    mutant residualized against the survivor basis."""
    specs = []
    specs += window_variants(month_families, month_wins)
    specs += window_variants(day_families, day_wins)
    return [evaluate(sp, inputs, basis) for sp in specs]


def render_board(rows: list[dict[str, Any]], top: int = 15,
                 title: str = "offense leaderboard") -> str:
    lines = [f"# {title}", "",
             "排序键 = 残差 oos IC（对幸存者正交化后的快车道判定）", "",
             "| # | candidate | IC均值 | ICIR | train/oos IC | n月 |",
             "|---|-----------|--------|------|--------------|-----|"]

    def f(x, nd=4):
        return "n/a" if x is None else f"{x:.{nd}f}"

    for k, r in enumerate(rows[:top], 1):
        lines.append(f"| {k} | {r['id']} | {f(r['ic_mean'])} | "
                     f"{f(r['icir'], 3)} | {f(r['train_ic'])} / "
                     f"{f(r['oos_ic'])} | {r['n_months']} |")
    return "\n".join(lines)
