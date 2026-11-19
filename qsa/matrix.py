"""Matrix fast plane — an OPTIONAL numpy backend for the monthly plane.

The project runs stdlib-only (CI installs nothing). When numpy is
importable, this module evaluates factors on a [month-end x ticker]
matrix instead of per-month Python loops:

* the IC cross-sections use integer-count average ranks
  (``#strictly-less + (#tied + 1) / 2``), algebraically identical to
  replication._ranks;
* the A/B two-implementation IC discipline is preserved (hand formula
  vs z-scored dot product, must agree to 1e-12 or the run refuses);
* every public function is bit-for-bit equivalent to its replication/
  factorzoo twin at the module boundary (values are rounded the same
  way) — tests/test_matrix.py enforces this on the real fixture for
  all 24 catalog factors. The gate semantics never change: same
  numbers, faster wall clock.

``evaluate_factor_fast`` falls back to the stdlib implementation when
numpy is missing, so callers need no feature detection.
"""
from __future__ import annotations

import math
from typing import Any

from . import factorzoo
from .replication import (ic_summary, month_end_indices, month_key)

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:  # pragma: no cover - exercised implicitly on CI
    np = None
    HAVE_NUMPY = False

MIN_NAMES = 10

# -- cross-factor close-matrix cache (the panel is constant while the
#    catalog evaluates; rebuilding it per factor cost ~2s over 24 factors).
#    The key is (id(closes), id(dates)) BUT the cache also holds strong
#    references to both objects: while they live their ids cannot be
#    reused, and once replaced the stale entry drops with its refs.
_C_KEY: tuple[int, int] | None = None
_C_VAL: tuple[dict[str, int], "np.ndarray"] | None = None
_C_SRC: tuple[dict, list] | None = None       # keeps the keyed objects alive


def _close_matrix(closes: dict[str, dict[str, float]],
                  dates: list[str]):
    """[T x n_closes] close matrix + {ticker: column}, cached per panel."""
    global _C_KEY, _C_VAL, _C_SRC
    key = (id(closes), id(dates))
    if _C_KEY == key and _C_VAL is not None:
        return _C_VAL
    d_idx = {d: i for i, d in enumerate(dates)}
    tickers = list(closes.keys())
    cmap = {tk: j for j, tk in enumerate(tickers)}
    C = np.full((len(dates), len(tickers)), np.nan)
    for j, tk in enumerate(tickers):
        for d, v in closes[tk].items():
            k = d_idx.get(d)
            if k is not None and v is not None:
                C[k, j] = v
    _C_KEY, _C_VAL, _C_SRC = key, (cmap, C), (closes, dates)
    return cmap, C


# ---------------------------------------------------------------------------
# vectorized average ranks + two-implementation spearman (per month row)
# ---------------------------------------------------------------------------

def _avg_ranks(x: "np.ndarray") -> "np.ndarray":
    """Average ranks with ties sharing the mean rank — the counting form.

    rank[j] = #{k: x[k] < x[j]} + (#{k: x[k] == x[j]} + 1) / 2, which is
    exactly replication._ranks' ``(i + j) / 2 + 1`` over each tie run,
    computed exactly in integer/float arithmetic (no sort order needed).
    """
    lt = (x[None, :] < x[:, None]).sum(axis=1)
    eq = (x[None, :] == x[:, None]).sum(axis=1)
    return lt + (eq + 1) / 2.0


def _spearman_ab(x: "np.ndarray", y: "np.ndarray") -> float:
    """Spearman via two independent vector implementations (A5 discipline)."""
    rx, ry = _avg_ranks(x), _avg_ranks(y)
    mx, my = rx.mean(), ry.mean()
    dx, dy = rx - mx, ry - my
    sxx = float((dx * dx).sum())
    syy = float((dy * dy).sum())
    if sxx == 0.0 or syy == 0.0:
        return 0.0                      # constant cross-section: no rank info
    # impl A — the hand formula (mirrors replication.spearman_impl_a)
    a = float((dx * dy).sum() / math.sqrt(sxx * syy))
    # impl B — z-scored dot product (mirrors statistics.correlation on ranks)
    b = _pearson_z(dx, dy, sxx, syy)
    if abs(a - b) > 1e-12:
        raise AssertionError(
            f"matrix IC double-compute mismatch: {a!r} vs {b!r} — refusing")
    return a


def _pearson_z(dx: "np.ndarray", dy: "np.ndarray",
               sxx: float, syy: float) -> float:
    """Implementation B as an injectable unit: z-scored dot product."""
    return float(((dx / math.sqrt(sxx)) * (dy / math.sqrt(syy))).sum())


# ---------------------------------------------------------------------------
# the month-end plane
# ---------------------------------------------------------------------------

class MonthPlane:
    """Precomputed [month-end x ticker] matrices for one factor signal.

    Rows are the month-end trade dates that have a following month
    (exactly replication.monthly_ic_series' convention); columns keep
    the signal dict's iteration order so stable sorts tie-break the
    same way as the stdlib implementation.
    """

    __slots__ = ("dates_m", "n", "F", "R", "f_ok", "min_names")

    def __init__(self, dates_m, F, R, f_ok, min_names):
        self.dates_m = dates_m          # list[str], the month-end dates
        self.n = F.shape[1]             # tickers (column count)
        self.F = F                      # factor values (NaN = missing)
        self.R = R                      # next-month simple returns (NaN = missing)
        self.f_ok = f_ok                # bool matrix: factor value present
        self.min_names = min_names

    @classmethod
    def build(cls, closes: dict[str, dict[str, float]],
              dates: list[str], signal: dict[str, dict[str, float]],
              min_names: int = MIN_NAMES) -> "MonthPlane | None":
        """Assemble the plane; None when no month-end has a forward month."""
        pairs: list[tuple[int, int]] = []
        ends = month_end_indices(dates)
        for i in ends:
            nxt = None
            for j in range(i + 1, len(dates)):
                if month_key(dates[j]) != month_key(dates[i]):
                    nxt = j
                    break
            if nxt is None:
                continue
            end_j = nxt
            while (end_j + 1 < len(dates)
                   and month_key(dates[end_j + 1]) == month_key(dates[nxt])):
                end_j += 1
            pairs.append((i, end_j))
        if not pairs:
            return None
        tickers = list(signal.keys())
        if not tickers:
            return None
        M = len(pairs)
        cmap, C = _close_matrix(closes, dates)
        col_of = np.array([cmap.get(tk, -1) for tk in tickers], dtype=int)
        gather = np.where(col_of >= 0, col_of, 0)   # placeholder for missing
        have = col_of >= 0
        i_rows = np.array([i for i, _ in pairs])
        e_rows = np.array([e for _, e in pairs])
        F = np.full((M, len(tickers)), np.nan)
        for j, tk in enumerate(tickers):
            row = signal.get(tk, {})
            for m, (i, _) in enumerate(pairs):
                v = row.get(dates[i])
                if v is not None:
                    F[m, j] = v
        c0 = C[i_rows][:, gather]
        c1 = C[e_rows][:, gather]
        c0[:, ~have] = np.nan                      # names absent from closes
        c1[:, ~have] = np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            R = np.where((c0 > 0) & np.isfinite(c0) & np.isfinite(c1) & (c1 != 0),
                         c1 / c0 - 1.0, np.nan)
        f_ok = np.isfinite(F)
        dates_m = [dates[i] for i, _ in pairs]
        return cls(dates_m, F, R, f_ok, min_names)

    # -- IC series (identical output to replication.monthly_ic_series) ------

    def ic_series(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in range(len(self.dates_m)):
            col = np.isfinite(self.R[m]) & self.f_ok[m]
            n = int(col.sum())
            if n < self.min_names:
                continue
            fwd = self.R[m][col]
            y = fwd - fwd * fwd / 2.0
            ic = _spearman_ab(self.F[m][col], y)
            out.append({"date": self.dates_m[m], "ic": round(ic, 6), "n": n})
        return out

    # -- quintile annualized returns (identical to replication) -------------

    def group_annualized(self, n_groups: int = 5) -> dict[str, float]:
        monthly: list[list[float]] = []
        for m in range(len(self.dates_m)):
            ok = self.f_ok[m]                  # grouping mask: factor present
            n = int(ok.sum())
            if n < n_groups:
                continue
            idx = np.where(ok)[0]
            order = np.argsort(self.F[m][idx], kind="stable")
            r_sorted = self.R[m][idx[order]]   # NaN returns drop out below
            size = n / n_groups
            rets: list[float] = []
            for g in range(n_groups):
                lo = int(round(g * size))
                hi = int(round((g + 1) * size))
                v = r_sorted[lo:hi]
                v = v[np.isfinite(v)]
                rets.append(float(v.mean()) if v.size else 0.0)
            monthly.append(rets)
        out: dict[str, float] = {}
        for g in range(n_groups):
            rs = [m[g] for m in monthly]
            geo = 1.0
            for r in rs:
                geo *= (1.0 + r)
            ann = geo ** (12.0 / len(rs)) - 1.0 if rs and geo > 0 else 0.0
            out[f"G{g + 1}"] = round(ann, 6)
        return out


# ---------------------------------------------------------------------------
# the fast evaluate_factor (drop-in equivalent of factorzoo.evaluate_factor)
# ---------------------------------------------------------------------------

def evaluate_factor_fast(spec: dict[str, Any],
                         inputs: dict[str, Any]) -> dict[str, Any]:
    """evaluate_factor on the matrix backend; stdlib fallback without numpy.

    Output keys and values match factorzoo.evaluate_factor exactly (the
    test suite asserts field-by-field equality on the real fixture).
    """
    rows = spec["build"](inputs)
    signal = factorzoo._finalize(rows, inputs["dates"], spec.get("flip", False))
    if HAVE_NUMPY:
        plane = MonthPlane.build(inputs["closes"], inputs["dates"], signal)
        ic = plane.ic_series() if plane is not None else []
        groups = plane.group_annualized(5) if plane is not None else {}
    else:  # pragma: no cover - the no-numpy path IS factorzoo's
        from .replication import group_monthly_returns, monthly_ic_series
        ic = monthly_ic_series(inputs["closes"], inputs["dates"], signal)
        groups = group_monthly_returns(inputs["closes"], inputs["dates"],
                                       signal)
    summ = ic_summary(ic)
    n = len(ic)
    k1, k2 = max(1, int(n * 0.6)), max(1, int(n * 0.8))

    def mean_ic(seq):
        return (sum(x["ic"] for x in seq) / len(seq)) if seq else None

    g1, g5 = groups.get("G1"), groups.get("G5")
    spread = (g5 - g1) if (g1 is not None and g5 is not None) else None
    return {
        "id": spec["id"], "source": spec["source"], "desc": spec["desc"],
        "flip": spec.get("flip", False),
        "n_months": n,
        "ic_mean": summ.get("ic_mean"),
        "icir": summ.get("icir"),
        "g1_ann": g1, "g5_ann": g5, "top_minus_bottom": spread,
        "train_ic": mean_ic(ic[:k1]),
        "val_ic": mean_ic(ic[k1:k2]),
        "oos_ic": mean_ic(ic[k2:]),
        "ic_positive_share": (sum(1 for x in ic if x["ic"] > 0) / n)
                             if n else None,
    }
