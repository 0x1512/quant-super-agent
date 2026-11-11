"""Toy research engine: cross-sectional momentum rank IC.

Deliberately simple so the evidence plane — not the factor — is the product.
The engine is lookahead-free by construction: the signal at date *t* uses
closes up to and including *t* only; the label is the *t -> t+1* forward
return (that is the quantity being evaluated, not an input). Window bounds
are enforced against the snapshot manifest before any computation runs.

All floats are rounded so results are byte-stable across platforms.
"""
from __future__ import annotations

from statistics import fmean, pstdev
from typing import Any

from .snapshot import fingerprint, load_closes

ENGINE_ID = "qsa-toy-momentum-0.2.0"


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float | None:
    ma, mb = fmean(a), fmean(b)
    da, db = [x - ma for x in a], [y - mb for y in b]
    num = sum(x * y for x, y in zip(da, db))
    den = (sum(x * x for x in da) ** 0.5) * (sum(y * y for y in db) ** 0.5)
    return None if den == 0 else num / den


def spearman(a: list[float], b: list[float]) -> float | None:
    return _pearson(_ranks(a), _ranks(b))


def _parse_window(window: str) -> tuple[str, str]:
    start, _, end = window.partition(":")
    if not start or not end:
        raise ValueError(f"window must be 'YYYYMMDD:YYYYMMDD', got {window!r}")
    return start, end


def run(snapshot_dir: str, *, k: int = 10, window: str | None = None,
        lag_probe: int = 2) -> dict[str, Any]:
    """Compute momentum rank-IC metrics over *window* (defaults to the full
    snapshot window). Returns {"metrics": {...}, "attribution": {...}}."""
    info = fingerprint(snapshot_dir)
    closes = load_closes(snapshot_dir)
    dates = sorted({d for series in closes.values() for d in series})
    tickers = sorted(closes)

    w_start, w_end = _parse_window(window) if window else (info.manifest["start"],
                                                           info.manifest["as_of"])
    if not (info.manifest["start"] <= w_start and w_end <= info.manifest["as_of"]):
        raise ValueError(
            f"window {w_start}:{w_end} extends beyond snapshot "
            f"{info.manifest['start']}:{info.manifest['as_of']} (lookahead refused)")
    dates = [d for d in dates if w_start <= d <= w_end]
    if len(dates) < k + 2:
        raise ValueError(f"window has {len(dates)} dates; need >= k+2 = {k + 2}")

    def evaluate_lag(lag: int) -> dict[str, float]:
        ics: list[float] = []
        quintile_spreads: list[float] = []
        quintile_means: list[list[float]] = []  # per date: [q1..q5] mean fwd return
        for i in range(lag, len(dates) - 1):
            t, t_next = dates[i], dates[i + 1]
            sig, fwd = [], []
            for tk in tickers:
                c_now, c_lag = closes[tk].get(t), closes[tk].get(dates[i - lag])
                c_fwd = closes[tk].get(t_next)
                if c_now is None or c_lag is None or c_fwd is None or c_lag == 0:
                    continue
                sig.append(c_now / c_lag - 1.0)
                fwd.append(c_fwd / c_now - 1.0)
            if len(sig) < 5:
                continue
            ic = spearman(sig, fwd)
            if ic is None:
                continue
            ics.append(ic)
            # quintile buckets by signal rank: q1 = cheapest momentum, q5 = richest
            ranked = sorted(range(len(sig)), key=lambda i2: sig[i2])
            q = len(ranked) // 5
            if q == 0:
                continue
            buckets = [fmean([fwd[i2] for i2 in ranked[j * q:(j + 1) * q]])
                       for j in range(5)]
            quintile_means.append(buckets)
            quintile_spreads.append(buckets[4] - buckets[0])
        if not ics:
            raise ValueError(f"no evaluation dates produced an IC (lag={lag})")
        mean_ic = fmean(ics)
        sd = pstdev(ics) if len(ics) > 1 else 0.0
        # monotonicity proxy: rank correlation of quintile index vs mean fwd return
        if quintile_means:
            avg = [fmean(col) for col in zip(*quintile_means)]
            mono = spearman([1.0, 2.0, 3.0, 4.0, 5.0], avg)
        else:
            mono = None
        return {
            "rankic_mean": round(mean_ic, 6),
            "rankic_tstat": round(mean_ic / (sd / len(ics) ** 0.5), 6) if sd > 0 else 0.0,
            "quintile_spread": round(fmean(quintile_spreads), 6) if quintile_spreads else 0.0,
            "monotonicity_proxy": round(mono, 6) if mono is not None else 0.0,
            "n_dates": len(ics),
        }

    base = evaluate_lag(k)
    neighborhood: dict[str, float] = {}
    for lag in range(k - lag_probe, k + lag_probe + 1):
        if lag < 1 or lag == k:
            continue
        neighborhood[f"lag_{lag}"] = evaluate_lag(lag)["rankic_mean"]
    base_sign = 1 if base["rankic_mean"] > 0 else (-1 if base["rankic_mean"] < 0 else 0)
    stable = all((1 if v > 0 else (-1 if v < 0 else 0)) == base_sign
                 for v in neighborhood.values()) if neighborhood else False

    return {
        "metrics": base,
        "attribution": {
            "neighborhood_stable": stable,
            "neighborhood_rankic": neighborhood,
        },
    }
