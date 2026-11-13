"""Scenario A — research-report replication (v1.0).

The mechanical core of the replication demo: the published report is
transcribed into a machine-readable reference card (every number with its
provenance), the report's factor is sandboxed v3 code, and the replication
verdict is pre-registered before any data is touched.

This module owns:
* ``REPORT`` — the report card: bibliographic facts + the published numbers
  we attempt to reproduce, each with a source pointer (A1);
* ``GAP_CODE`` — the overnight-gap factor as sandbox contract v3 code,
  exactly as the report defines it (A3);
* ``REVERSAL_CODE`` — the classic 20-day reversal the report benchmarks
  against;
* monthly-plane evaluators (monthly rank-IC series, quintile monthly
  returns) with a two-implementation cross-check on every IC (A5's
  "computed and independently recomputed" applied to the monthly plane);
* the pre-registered decision rules (A8) — pure functions, evaluated only
  after the hypothesis is registered.

Nothing here talks to the network or to the data source: it consumes a
fingerprinted snapshot + a meta CSV (monthly market caps / industries),
both materialized by the fixture builder.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import StatisticsError, correlation, fmean, pstdev
from typing import Any

# ---------------------------------------------------------------------------
# A1 — the report card. Every published number carries where it came from.
# ---------------------------------------------------------------------------

REPORT: dict[str, Any] = {
    "target": "overnight-gap factor (absRet_night)",
    "report": {
        "title": "市场微观结构剖析之九——昼夜分离：隔夜跳空与日内反转选股因子",
        "series": "Market microstructure anatomy IX — day/night separation",
        "broker": "华安证券 (Huaan Securities), financial engineering",
        "lead_author": "朱定豪 (Zhu Dinghao)",
        "published": "2020-09-03",
        "source_urls": [
            "https://stock.finance.sina.com.cn/stock/go.php/vReport_Show/"
            "kind/lastnum/rptid/652449716605/index.phtml",
            "https://zhuanlan.zhihu.com/p/700546862",
        ],
    },
    "factor_definition": {
        "formula": "absRet_night = abs(ln(Open_t / Close_{t-1}))",
        "aggregation": "21-trade-day rolling sum",
        "direction": "negative (large cumulative overnight gaps -> lower "
                     "forward returns)",
        "rebalance": "monthly (last trade day cross-section)",
        "provenance": "Zhihu factor-notes post quoting the report's formula "
                      "(p/700546862); report abstract on Sina",
    },
    # Published numbers, two reference systems, each with its provenance.
    "references": {
        "R1_report_abstract": {
            "what": "the report's *composite* day/night factor, "
                    "cap- and industry-neutralized (NOT the standalone gap "
                    "factor — kept for context)",
            "ic_mean": -0.0810,
            "icir_annualized": -4.04,
            "ls_annualized": 0.3692,
            "win_rate": 0.896,
            "max_drawdown": 0.0758,
            "provenance": "report abstract (Sina detail page, 2020-09-03)",
        },
        "R2_independent_retest": {
            "what": "standalone overnight-gap factor, built exactly per the "
                    "report's formula by an independent author (Zhihu "
                    "factor-notes series #11) — the nearest comparable to "
                    "what we recompute",
            "ic_mean": {"raw": -0.094, "cap_neutral": -0.091,
                        "cap_industry_neutral": -0.082},
            "icir": {"raw": -0.680, "cap_neutral": -0.713,
                     "cap_industry_neutral": -0.909},
            "p_ic_positive": {"raw": 0.2493, "cap_neutral": 0.2418,
                              "cap_industry_neutral": 0.1865},
            "group5_annualized_equal_weight": {"G1": 0.0253, "G5": -0.1442},
            "provenance": "https://zhuanlan.zhihu.com/p/700546862 (2024-05-29)",
        },
    },
    # A4 — conventions that differ between the report and our replication;
    # every entry is *displayed*, never silently absorbed.
    "convention_alignment": [
        ("golden-ratio intraday reversal (10:00 cut)",
         "report: yes (needs minute bars)", "ours: NOT reproducible on a "
         "daily-OHLCV plane — declared out of scope"),
        ("day/night composite weights",
         "report: published only in the paywalled body", "ours: out of scope "
         "(abstract gives the composite's results, not its weights)"),
        ("sample window",
         "report/retest: pre-2021 histories", "ours: 2021-07..2026-06 — the "
         "regime differs and the gap is attributed, not excused"),
        ("universe",
         "report: CSI300/500/1000 & whole-A; retest: unspecified (likely "
         "whole-A)", "ours: top-300 by H1-2021 turnover, listed >= 60 days, "
         "non-ST — fixed before the sample and rebuildable by anyone"),
        ("groups", "retest: 5", "ours: 5 (matching), 10 reported as "
         "attribution variant"),
        ("neutralization", "retest: raw / cap / cap+industry",
         "ours: same three variants, OLS on ln(size) with industry "
         "dummies, where size = mean daily amount of the month (cap "
         "proxy: tushare daily_basic total_mv is rate-limited to ~1 call/"
         "hour on this project's token, so month-end caps are not "
         "fetchable — the substitution is declared here, not hidden)"),
    ],
}

# ---------------------------------------------------------------------------
# A3 — the factors, as sandbox code. The code IS the documentation.
# ---------------------------------------------------------------------------

GAP_CODE = '''\
def factor(closes, opens, volumes, tickers, dates, i):
    """Overnight-gap factor (report's absRet_night), v3 contract.

    21-trade-day rolling sum of |ln(open_t / close_{t-1})|. The sandbox
    truncates every panel at date i, so 'the previous close' is always a
    past close. log() is approximated by its second-order expansion so the
    code stays inside the sandbox's arithmetic whitelist.
    """
    out = {}
    hist = dates[max(0, i - 21):i + 1]
    for tk in tickers:
        s = 0.0
        for j in range(1, len(hist)):
            c_prev = closes.get(tk, {}).get(hist[j - 1])
            o = opens.get(tk, {}).get(hist[j])
            if c_prev and o and c_prev > 0 and o > 0:
                r = o / c_prev - 1
                s += abs(r - r * r / 2)
        out[tk] = s
    return out
'''

REVERSAL_CODE = '''\
def factor(closes, tickers, dates, i):
    """Classic 20-day reversal: negative past-20d log-return (v1 contract).
    The report benchmarks its factors against this one; we recompute it so
    the comparison is on our own data plane."""
    out = {}
    hist = dates[max(0, i - 20):i + 1]
    for tk in tickers:
        c0 = closes.get(tk, {}).get(hist[0])
        c1 = closes.get(tk, {}).get(hist[-1])
        if c0 and c1 and c0 > 0:
            r = c1 / c0 - 1
            out[tk] = -(r - r * r / 2)
    return out
'''


# ---------------------------------------------------------------------------
# Monthly plane (the report's conventions), with a two-implementation IC.
# ---------------------------------------------------------------------------

def month_key(date_yyyymmdd: str) -> str:
    return date_yyyymmdd[:6]


def month_end_indices(dates: list[str]) -> list[int]:
    """Indices of each month's last trade date in ``dates`` (sorted)."""
    ends: list[int] = []
    for i, d in enumerate(dates):
        if i + 1 == len(dates) or month_key(dates[i + 1]) != month_key(d):
            ends.append(i)
    return ends


def _ranks(xs: list[float]) -> list[float]:
    """Average ranks (ties share the mean rank)."""
    order = sorted(range(len(xs)), key=lambda k: xs[k])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_impl_a(x: list[float], y: list[float]) -> float:
    """Implementation A: average-rank Pearson, hand-rolled (mirrors the
    engine's daily-plane rank IC so both planes share one convention)."""
    rx, ry = _ranks(x), _ranks(y)
    mx, my = fmean(rx), fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx)
                    * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def spearman_impl_b(x: list[float], y: list[float]) -> float:
    """Implementation B: the stdlib's correlation on the same average ranks.

    A5's double-compute discipline on the monthly plane: every reported IC
    must agree between A and B to 1e-12, else the run refuses to continue.
    A constant cross-section (degenerate after neutralization) has no rank
    information: both implementations define IC = 0.0 there, symmetrically."""
    rx, ry = _ranks(x), _ranks(y)
    try:
        return correlation(rx, ry)
    except StatisticsError:
        return 0.0


def monthly_ic_series(closes: dict[str, dict[str, float]],
                      dates: list[str],
                      signal: dict[str, dict[str, float]],
                      min_names: int = 10) -> list[dict[str, Any]]:
    """Monthly rank-IC series in the report's convention.

    At each month-end trade date d: factor value at d vs the next-month
    return ln(close(d_next) / close(d)), cross-sectionally, Spearman.
    Returns [{date, ic_a, ic_b, n}] — the two implementations must agree.
    """
    ends = month_end_indices(dates)
    out: list[dict[str, Any]] = []
    for i in ends:
        d = dates[i]
        nxt = None
        for j in range(i + 1, len(dates)):
            if month_key(dates[j]) != month_key(d):
                nxt = j
                break
        if nxt is None:  # last month in sample — no next month to score
            continue
        # forward window: from d to the last trade day of the next month
        end_j = nxt
        while end_j + 1 < len(dates) and month_key(dates[end_j + 1]) == month_key(dates[nxt]):
            end_j += 1
        d_end = dates[end_j]
        xs: list[float] = []
        ys: list[float] = []
        for tk, sig_row in signal.items():
            f = sig_row.get(d)
            c0 = closes.get(tk, {}).get(d)
            c1 = closes.get(tk, {}).get(d_end)
            if f is None or not c0 or not c1 or c0 <= 0:
                continue
            fwd = c1 / c0 - 1
            xs.append(f)
            ys.append(fwd - fwd * fwd / 2)
        if len(xs) < min_names:
            continue
        ic_a = spearman_impl_a(xs, ys)
        ic_b = spearman_impl_b(xs, ys)
        if abs(ic_a - ic_b) > 1e-12:
            raise AssertionError(
                f"monthly IC double-compute mismatch at {d}: "
                f"{ic_a!r} vs {ic_b!r} — refusing to report")
        out.append({"date": d, "ic": round(ic_a, 6), "n": len(xs)})
    return out


def ic_summary(series: list[dict[str, Any]]) -> dict[str, float]:
    """Mean IC, ICIR, and P(IC<0) in the retest's reporting convention."""
    ics = [s["ic"] for s in series]
    if not ics:
        return {"ic_mean": 0.0, "icir": 0.0, "p_ic_negative": 0.0, "n": 0}
    m = fmean(ics)
    sd = pstdev(ics) if len(ics) > 1 else 0.0
    return {
        "ic_mean": round(m, 6),
        "icir": round(m / sd, 6) if sd > 0 else 0.0,
        "p_ic_negative": round(sum(1 for v in ics if v < 0) / len(ics), 6),
        "n": len(ics),
    }


def group_monthly_returns(closes: dict[str, dict[str, float]],
                          dates: list[str],
                          signal: dict[str, dict[str, float]],
                          n_groups: int = 5
                          ) -> dict[str, float]:
    """Equal-weight quintile (n-group) monthly annualized returns.

    Report convention: at each month-end, names are sorted by *ascending*
    factor value — G1 is always the LOWEST-factor group. For a negative-IC
    factor (like the overnight gap), the report's "G1 2.53% vs G5 -14.42%"
    shape means low-gap stocks out-earn high-gap stocks. Annualization
    compounds the monthly group means geometrically."""
    ends = month_end_indices(dates)
    group_monthly: list[list[float]] = []
    for i in ends:
        d = dates[i]
        nxt = None
        for j in range(i + 1, len(dates)):
            if month_key(dates[j]) != month_key(d):
                nxt = j
                break
        if nxt is None:
            continue
        end_j = nxt
        while end_j + 1 < len(dates) and month_key(dates[end_j + 1]) == month_key(dates[nxt]):
            end_j += 1
        d_end = dates[end_j]
        names: list[tuple[float, str]] = []
        for tk, sig_row in signal.items():
            f = sig_row.get(d)
            if f is None:
                continue
            names.append((f, tk))
        if len(names) < n_groups:
            continue
        names.sort(key=lambda t: t[0])  # ascending: G1 = lowest factor
        size = len(names) / n_groups
        rets: list[float] = []
        for g in range(n_groups):
            lo = int(round(g * size))
            hi = int(round((g + 1) * size))
            vals = []
            for _, tk in names[lo:hi]:
                c0 = closes.get(tk, {}).get(d)
                c1 = closes.get(tk, {}).get(d_end)
                if c0 and c1 and c0 > 0:
                    vals.append(c1 / c0 - 1)
            rets.append(fmean(vals) if vals else 0.0)
        group_monthly.append(rets)
    out: dict[str, float] = {}
    for g in range(n_groups):
        rets = [m[g] for m in group_monthly]
        geo = 1.0
        for r in rets:
            geo *= (1.0 + r)
        if rets and geo > 0:
            ann = geo ** (12.0 / len(rets)) - 1.0
        else:
            ann = 0.0
        out[f"G{g + 1}"] = round(ann, 6)
    return out


# ---------------------------------------------------------------------------
# Neutralization variants (the retest's three conventions).
# ---------------------------------------------------------------------------

def neutralize(values: dict[str, float],
               caps: dict[str, float] | None,
               industries: dict[str, str] | None,
               mode: str) -> dict[str, float]:
    """Cross-sectionally neutralize a monthly factor snapshot.

    mode: 'raw' (unchanged) | 'cap' (OLS on ln cap, residual) |
    'cap_industry' (OLS on ln cap + industry dummies, residual).
    Names missing cap/industry data fall back to 'raw' handling: they are
    dropped from the regression but keep a residual of 0.0 so the universe
    is stable across variants (a silent universe change would be exactly
    the FIB-10 lie this demo is about)."""
    if mode == "raw":
        return dict(values)
    names = sorted(k for k in values
                   if caps and k in caps and caps[k] > 0)
    if not names:
        return {k: 0.0 for k in values}
    y = [values[n] for n in names]
    cols: list[list[float]] = [[1.0] * len(names),
                               [math.log(caps[n]) for n in names]]
    if mode == "cap_industry" and industries:
        seen: list[str] = []
        for n in names:
            ind = industries.get(n, "?")
            if ind not in seen:
                seen.append(ind)
        for ind in seen[1:]:  # first industry is the intercept's baseline
            cols.append([1.0 if industries.get(n, "?") == ind else 0.0
                         for n in names])
    # OLS via normal equations with Gaussian elimination (stdlib only)
    k = len(cols)
    ata = [[sum(cols[a][r] * cols[b][r] for r in range(len(names)))
            for b in range(k)] for a in range(k)]
    aty = [sum(cols[a][r] * y[r] for r in range(len(names))) for a in range(k)]
    beta = _solve(ata, aty)
    out = dict.fromkeys(values, 0.0)
    for r, n in enumerate(names):
        fit = sum(beta[a] * cols[a][r] for a in range(k))
        out[n] = y[r] - fit
    return out


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            continue
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        for r in range(n):
            if r != col and m[r][col] != 0:
                f = m[r][col] / pv
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0
            for i in range(n)]


# ---------------------------------------------------------------------------
# A8 — the pre-registered decision rules. Pure functions; frozen text.
# ---------------------------------------------------------------------------

PREREGISTERED_RULES: dict[str, Any] = {
    "registered_before_data": True,
    "D1_direction": {
        "rule": "at least 2 of the 3 neutralization variants have "
                "ic_mean < 0 with |ic_mean| >= 0.03, and the raw variant's "
                "P(IC<0) >= 0.60",
        "pass_if": "direction_replicated = True",
    },
    "D2_monotonicity": {
        "rule": "raw equal-weight 5-group annualized: G1 > G5 "
                "(the retest's G1 2.53% vs G5 -14.42% shape, direction only)",
        "pass_if": "G1_annualized > G5_annualized",
    },
    "D3_magnitude": {
        "rule": "|ic_mean_raw - (-0.094)| <= 0.05 -> 'magnitude consistent'; "
                "otherwise 'magnitude gap' (attributed, not failed — the "
                "sample and universe differ by construction)",
        "pass_if": "verdict reported either way; never edited post hoc",
    },
    "overall": "D1 AND D2 must both pass for verdict=replicated; "
               "any failure is reported as an honest negative",
}


def apply_preregistered_rules(summary: dict[str, Any],
                              groups_raw: dict[str, float]) -> dict[str, Any]:
    """Evaluate the frozen rules against computed summaries."""
    variants = summary["variants"]
    d1_hits = sum(1 for v in variants.values()
                  if v["ic_mean"] < 0 and abs(v["ic_mean"]) >= 0.03)
    raw = variants["raw"]
    d1 = d1_hits >= 2 and raw["p_ic_negative"] >= 0.60
    d2 = groups_raw.get("G1", 0.0) > groups_raw.get("G5", 0.0)
    gap = abs(raw["ic_mean"] - (-0.094))
    return {
        "D1_direction": bool(d1),
        "D2_monotonicity": bool(d2),
        "D3_magnitude": "consistent" if gap <= 0.05 else "gap",
        "ic_gap_vs_retest": round(gap, 6),
        "verdict": "replicated" if (d1 and d2) else "not_replicated",
    }


# ---------------------------------------------------------------------------
# Meta loading + neutralized monthly IC + the whitelisted evaluators the
# verify gate recomputes from (v1.0 Scenario A5).
# ---------------------------------------------------------------------------

def load_monthly_meta(snapshot_dir: Path) -> dict[str, Any]:
    """Read <snapshot>/meta/monthly_caps.csv and industries.csv.

    monthly_caps.csv: header month,ticker,cap_proxy (month = YYYYMM;
    cap_proxy = mean daily amount in thousand CNY, the declared market-cap
    stand-in — see the H card's convention table)
    industries.csv:  header ticker,industry
    Both files are manifest-pinned (ingest copies and hashes them), so the
    replication gate can recompute neutralized metrics from exactly the
    meta the card's snapshot was built with."""
    snap = Path(snapshot_dir)
    caps: dict[str, dict[str, float]] = {}
    caps_p = snap / "meta" / "monthly_caps.csv"
    if caps_p.exists():
        with caps_p.open(encoding="utf-8", newline="") as fh:
            for n, row in enumerate(csv.DictReader(fh), start=2):
                m = (row.get("month") or "").strip()
                tk = (row.get("ticker") or "").strip()
                try:
                    mv = float(row.get("cap_proxy") or "")
                except ValueError:
                    raise ValueError(f"monthly_caps.csv row {n}: bad cap_proxy"
                                     ) from None
                if not m or not tk:
                    raise ValueError(f"monthly_caps.csv row {n}: missing "
                                     "month/ticker")
                caps.setdefault(m, {})[tk] = mv
    industries: dict[str, str] = {}
    ind_p = snap / "meta" / "industries.csv"
    if ind_p.exists():
        with ind_p.open(encoding="utf-8", newline="") as fh:
            for n, row in enumerate(csv.DictReader(fh), start=2):
                tk = (row.get("ticker") or "").strip()
                ind = (row.get("industry") or "").strip()
                if not tk or not ind:
                    raise ValueError(f"industries.csv row {n}: missing "
                                     "ticker/industry")
                industries[tk] = ind
    return {"caps": caps, "industries": industries,
            "has_industries": bool(industries)}


def monthly_ic_neutralized(closes: dict[str, dict[str, float]],
                           dates: list[str],
                           signal: dict[str, dict[str, float]],
                           meta: dict[str, Any],
                           mode: str,
                           min_names: int = 10) -> list[dict[str, Any]]:
    """Monthly rank-IC after cross-sectional neutralization (mode).

    Same month-end convention as monthly_ic_series; the factor cross-section
    at each month-end is first neutralized against that month's ln cap (and
    industry dummies for mode='cap_industry') from the pinned meta, then
    Spearman-ranked against next-month returns."""
    if mode == "raw":
        return monthly_ic_series(closes, dates, signal, min_names)
    caps_by_month = meta.get("caps") or {}
    industries = meta.get("industries") or {}
    ends = month_end_indices(dates)
    out: list[dict[str, Any]] = []
    for i in ends:
        d = dates[i]
        ym = d[:6]
        nxt = None
        for j in range(i + 1, len(dates)):
            if month_key(dates[j]) != month_key(d):
                nxt = j
                break
        if nxt is None:
            continue
        end_j = nxt
        while end_j + 1 < len(dates) and month_key(dates[end_j + 1]) == month_key(dates[nxt]):
            end_j += 1
        d_end = dates[end_j]
        raw_vals: dict[str, float] = {}
        fwd: dict[str, float] = {}
        for tk, sig_row in signal.items():
            f = sig_row.get(d)
            c0 = closes.get(tk, {}).get(d)
            c1 = closes.get(tk, {}).get(d_end)
            if f is None or not c0 or not c1 or c0 <= 0:
                continue
            raw_vals[tk] = f
            fwd[tk] = c1 / c0 - 1
        month_caps = caps_by_month.get(ym) or {}
        vals = neutralize(raw_vals, month_caps, industries, mode)
        xs = [vals[tk] for tk in sorted(vals)]
        ys = [fwd[tk] - fwd[tk] * fwd[tk] / 2 for tk in sorted(vals)]
        if len(xs) < min_names:
            continue
        ic_a = spearman_impl_a(xs, ys)
        ic_b = spearman_impl_b(xs, ys)
        if abs(ic_a - ic_b) > 1e-12:
            raise AssertionError(f"neutralized IC double-compute mismatch "
                                 f"at {d} ({mode}): {ic_a!r} vs {ic_b!r}")
        out.append({"date": d, "ic": round(ic_a, 6), "n": len(xs)})
    return out


def recompute_replication_block(closes: dict[str, dict[str, float]],
                                dates: list[str],
                                signal: dict[str, dict[str, float]],
                                meta: dict[str, Any]) -> dict[str, Any]:
    """The single whitelisted evaluator for E.replication_block.

    Produces every number the replication card reports in the report's own
    monthly convention — the three neutralization variants' IC summaries,
    the equal-weight quintile annualized returns, and the mechanically
    re-derived pre-registered verdict. verify.gate calls this and demands
    exact equality with the card's replication_block."""
    variants: dict[str, dict[str, float]] = {}
    for mode in ("raw", "cap", "cap_industry"):
        variants[mode] = ic_summary(monthly_ic_neutralized(
            closes, dates, signal, meta, mode))
    groups = group_monthly_returns(closes, dates, signal)
    rules = apply_preregistered_rules({"variants": variants}, groups)
    return {"ic_variants": variants, "groups": groups, "rules": rules}
