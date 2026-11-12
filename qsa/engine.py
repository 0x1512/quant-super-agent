"""Signal evaluation harness (lookahead-free) + the toy momentum factor.

The evaluation core is factor-agnostic: any function mapping the snapshot's
close panel to a signal matrix `{ticker: {date: value}}` can be evaluated
over a declared window. The toy momentum factor is one such function (it
keeps the v0.2 behaviour and numbers bit-identical). The mining loop (v0.3)
evaluates LLM-written factors through the exact same path — and so does the
verify gate when it recomputes a card's metrics from its `factor_code`.

Lookahead discipline is enforced before any computation: the window must sit
inside the snapshot bounds; a signal value at date *t* is only ever compared
against the *t -> t+1* forward return. All floats are rounded so results are
byte-stable across platforms.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Any, Callable

from .snapshot import SnapshotInfo, fingerprint, load_closes

EVAL_ID = "qsa-eval-0.4.0"
ENGINE_ID = "qsa-toy-momentum-0.2.0"  # kept: the toy factor's historical id

SignalMatrix = dict[str, dict[str, float]]
SignalFn = Callable[[dict[str, dict[str, float]], list[str], list[str]], SignalMatrix]


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


@dataclass(frozen=True)
class Frame:
    """A validated evaluation frame: closes + window-bounded calendar."""

    closes: dict[str, dict[str, float]]
    tickers: list[str]
    dates: list[str]
    snapshot: SnapshotInfo


def load_frame(snapshot_dir: str | Any, window: str | None = None) -> Frame:
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
    if len(dates) < 3:
        raise ValueError(f"window has {len(dates)} dates; need >= 3")
    return Frame(closes, tickers, dates, info)


def evaluate_signal(frame: Frame, signal: SignalMatrix) -> dict[str, float]:
    """Evaluate a signal matrix over the frame: daily cross-sectional Spearman
    rank IC against next-day forward returns, plus quintile diagnostics."""
    closes, tickers, dates = frame.closes, frame.tickers, frame.dates
    ics: list[float] = []
    quintile_spreads: list[float] = []
    quintile_means: list[list[float]] = []
    for i in range(len(dates) - 1):
        t, t_next = dates[i], dates[i + 1]
        sig, fwd = [], []
        for tk in tickers:
            row = signal.get(tk)
            v = row.get(t) if row else None
            c_now, c_fwd = closes[tk].get(t), closes[tk].get(t_next)
            if v is None or c_now is None or c_fwd is None:
                continue
            sig.append(float(v))
            fwd.append(c_fwd / c_now - 1.0)
        if len(sig) < 5:
            continue
        ic = spearman(sig, fwd)
        if ic is None:
            continue
        ics.append(ic)
        ranked = sorted(range(len(sig)), key=lambda i2: sig[i2])
        q = len(ranked) // 5
        if q == 0:
            continue
        buckets = [fmean([fwd[i2] for i2 in ranked[j * q:(j + 1) * q]])
                   for j in range(5)]
        quintile_means.append(buckets)
        quintile_spreads.append(buckets[4] - buckets[0])
    if not ics:
        raise ValueError("no evaluation dates produced an IC (signal too sparse)")
    mean_ic = fmean(ics)
    sd = pstdev(ics) if len(ics) > 1 else 0.0
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


def momentum_matrix(closes: dict[str, dict[str, float]], tickers: list[str],
                    dates: list[str], k: int = 10) -> SignalMatrix:
    """Toy factor: trailing-k-day return. Signal at *t* uses closes up to and
    including *t* only (lookahead-free by construction)."""
    out: SignalMatrix = {tk: {} for tk in tickers}
    for i in range(k, len(dates)):
        t, lag = dates[i], dates[i - k]
        for tk in tickers:
            c = closes[tk]
            a, b = c.get(t), c.get(lag)
            if a is None or b is None or b == 0:
                continue
            out[tk][t] = a / b - 1.0
    return out


def run(snapshot_dir: str, *, k: int = 10, window: str | None = None,
        lag_probe: int = 2) -> dict[str, Any]:
    """Momentum rank-IC over *window* (defaults to the full snapshot window).
    Returns {"metrics": {...}, "attribution": {...}}. Numbers are identical
    to the v0.2 implementation (the refactor is purely structural)."""
    frame = load_frame(snapshot_dir, window)
    if len(frame.dates) < k + 2:
        raise ValueError(f"window has {len(frame.dates)} dates; need >= k+2 = {k + 2}")

    def metrics_for_lag(lag: int) -> dict[str, float]:
        return evaluate_signal(frame, momentum_matrix(frame.closes, frame.tickers,
                                                      frame.dates, lag))

    base = metrics_for_lag(k)
    neighborhood: dict[str, float] = {}
    for lag in range(k - lag_probe, k + lag_probe + 1):
        if lag < 1 or lag == k:
            continue
        neighborhood[f"lag_{lag}"] = metrics_for_lag(lag)["rankic_mean"]
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
