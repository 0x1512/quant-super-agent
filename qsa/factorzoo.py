"""Factor zoo — the fast lane of candidate production (v1.1).

v1.0 proved one factor can be reproduced honestly, one at a time, by hand.
That throughput cannot find strategies. This module turns the pinned
snapshot into a factor *factory*:

* a library of operator kernels (rolling mean/std/rank/corr with
  incremental updates — O(N) per ticker, so the whole zoo runs in seconds
  without any third-party dependency);
* a catalog of template factors, every one traceable to public literature
  (Jegadeesh-Titman momentum, Lehmann reversal, Amihud illiquidity,
  Bali lottery-MAX, George-Hwang 52-week-high, the overnight-gap family
  from the replicated report's public summary, and WorldQuant Alpha#101
  — the published 2015 paper, nothing proprietary);
* a batch fast-lane evaluator: monthly rank-IC, ICIR, quintile spreads,
  and train/val/oos IC gates per factor, producing a leaderboard.

Fast lane vs heavy gate — deliberate, declared tiering: the zoo RANKS
candidates on shared data; it does not certify them. Nothing here touches
the registry, the pre-registered thresholds, or the verify gate. A
candidate that survives the zoo still graduates through the full v1.0
path (pre-registration -> engine -> independent recomputation -> verdict)
before any claim is published. Speed comes from not lying faster; it
comes from not wasting the expensive honesty machinery on factors that
die in the first screen.

All factors are oriented "higher = better" (negative-direction families
are sign-flipped in the catalog), so downstream sorting never special-
cases. Values are computed strictly from data up to and including each
date (rolling windows end at t, used at t's month-end — the same
no-lookahead convention as the replication plane).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

from .backtest import month_key, month_end_indices
from .replication import (group_monthly_returns, ic_summary,
                          monthly_ic_series)


# ---------------------------------------------------------------------------
# incremental rolling kernels — O(N) per series
# ---------------------------------------------------------------------------

def _cumulative(xs: list[float]) -> list[float]:
    out = [0.0]
    for x in xs:
        out.append(out[-1] + x)
    return out


def rolling_mean(xs: list[float | None], win: int) -> list[float | None]:
    """Welford-free simple rolling mean over the last ``win`` present
    values; None until the window fills."""
    out: list[float | None] = [None] * len(xs)
    buf: list[float] = []
    for i, x in enumerate(xs):
        if x is None:
            out[i] = None if len(buf) < win else out[i - 1]
            continue
        buf.append(x)
        if len(buf) > win:
            buf.pop(0)
        if len(buf) == win:
            out[i] = sum(buf) / win
    return out


def rolling_std(xs: list[float | None], win: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    buf: list[float] = []
    for i, x in enumerate(xs):
        if x is None:
            continue
        buf.append(x)
        if len(buf) > win:
            buf.pop(0)
        if len(buf) == win:
            m = sum(buf) / win
            out[i] = math.sqrt(sum((b - m) ** 2 for b in buf) / (win - 1))
    return out


def rolling_sum(xs: list[float | None], win: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    acc = 0.0
    buf: list[float] = []
    for i, x in enumerate(xs):
        if x is None:
            continue
        buf.append(x)
        acc += x
        if len(buf) > win:
            acc -= buf.pop(0)
        if len(buf) == win:
            out[i] = acc
    return out


def rolling_max(xs: list[float | None], win: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    buf: list[float] = []
    for i, x in enumerate(xs):
        if x is None:
            continue
        buf.append(x)
        if len(buf) > win:
            buf.pop(0)
        if len(buf) == win:
            out[i] = max(buf)
    return out


def rolling_corr(xs: list[float | None], ys: list[float | None],
                 win: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    bx: list[float] = []
    by: list[float] = []
    for i in range(len(xs)):
        x, y = xs[i], ys[i]
        if x is None or y is None:
            continue
        bx.append(x)
        by.append(y)
        if len(bx) > win:
            bx.pop(0)
            by.pop(0)
        if len(bx) == win:
            mx, my = sum(bx) / win, sum(by) / win
            cov = sum((a - mx) * (b - my) for a, b in zip(bx, by))
            vx = sum((a - mx) ** 2 for a in bx)
            vy = sum((b - my) ** 2 for b in by)
            if vx > 0 and vy > 0:
                out[i] = cov / math.sqrt(vx * vy)
    return out


# ---------------------------------------------------------------------------
# per-ticker primitive series builders (from snapshot dicts)
# ---------------------------------------------------------------------------

def series_of(panel: dict[str, dict[str, float]],
              dates: list[str]) -> dict[str, list[float | None]]:
    """{ticker: [value or None per date in dates]} — aligned, gap-aware."""
    out: dict[str, list[float | None]] = {}
    for tk, row in panel.items():
        out[tk] = [row.get(d) for d in dates]
    return out


def returns_of(close_rows: dict[str, list[float | None]],
               ) -> dict[str, list[float | None]]:
    out: dict[str, list[float | None]] = {}
    for tk, xs in close_rows.items():
        seq: list[float | None] = [None] * len(xs)
        prev: float | None = None
        for i, x in enumerate(xs):
            if x is None:
                prev = None
                continue
            if prev is not None and prev > 0:
                seq[i] = x / prev - 1.0
            prev = x
        out[tk] = seq
    return out


def overnight_of(open_rows, close_rows) -> dict[str, list[float | None]]:
    """ln(open_t / close_{t-1}) — the replicated report's daily gap."""
    out = {}
    for tk in close_rows:
        co, cc = open_rows.get(tk, []), close_rows[tk]
        seq: list[float | None] = [None] * len(cc)
        prev: float | None = None
        for i in range(len(cc)):
            o, c = (co[i] if i < len(co) else None), cc[i]
            if prev is not None and o and o > 0 and prev > 0:
                seq[i] = math.log(o / prev)
            prev = c if c is not None else None
        out[tk] = seq
    return out


def intraday_of(open_rows, close_rows) -> dict[str, list[float | None]]:
    out = {}
    for tk in close_rows:
        co, cc = open_rows.get(tk, []), close_rows[tk]
        seq: list[float | None] = [None] * len(cc)
        for i in range(len(cc)):
            o, c = (co[i] if i < len(co) else None), cc[i]
            if o and o > 0 and c and c > 0:
                seq[i] = math.log(c / o)
        out[tk] = seq
    return out


def to_signal(rows: dict[str, list[float | None]],
              dates: list[str]) -> dict[str, dict[str, float]]:
    """Back to the sparse {ticker: {date: value}} the plane speaks."""
    sig: dict[str, dict[str, float]] = {}
    for tk, xs in rows.items():
        d: dict[str, float] = {}
        for i, x in enumerate(xs):
            if x is not None and math.isfinite(x):
                d[dates[i]] = x
        if d:
            sig[tk] = d
    return sig


# ---------------------------------------------------------------------------
# the catalog — public-literature templates, oriented higher=better
# ---------------------------------------------------------------------------

FactorBuild = Callable[[dict[str, Any]], dict[str, dict[str, float]]]


def _finalize(rows, dates, flip: bool):
    if flip:
        rows = {tk: [None if x is None else -x for x in xs]
                for tk, xs in rows.items()}
    return to_signal(rows, dates)


def build_catalog() -> list[dict[str, Any]]:
    """24 template factors; source = public citation, desc = the recipe."""
    C: list[dict[str, Any]] = []

    def add(fid, source, desc, fn, flip=False):
        C.append({"id": fid, "source": source, "desc": desc,
                  "build": fn, "flip": flip})

    def make(fn):
        return fn

    def mom_12_1(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        rows = {}
        for tk, r in rs.items():
            cum = _cumulative([0.0 if x is None else x for x in r])
            out = []
            for i in range(len(r)):
                v = None
                if i >= 252 and cum[i - 21] is not None:
                    lo, hi = cum[i - 252], cum[i - 21]
                    if lo is not None and hi is not None:
                        v = hi - lo
                out.append(v)
            rows[tk] = out
        return rows

    add("mom_12_1", "Jegadeesh & Titman (1993)",
        "12-month momentum skipping the last month (log cumsum), "
        "higher=better", make(mom_12_1))

    def rev_1m(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        return {tk: rolling_sum(r, 21) for tk, r in rs.items()}

    add("rev_1m", "Jegadeesh (1990)",
        "1-month reversal: negative 21-day cumulative return", 
        make(rev_1m), flip=True)

    def rev_1w(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        return {tk: rolling_sum(r, 5) for tk, r in rs.items()}

    add("rev_1w", "Lehmann (1990)",
        "1-week reversal: negative 5-day cumulative return",
        make(rev_1w), flip=True)

    def vol_20d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        return {tk: rolling_std(r, 20) for tk, r in rs.items()}

    add("vol_20d", "Ang et al. (2006) low-vol anomaly",
        "20-day return std, NEGATIVE direction (low vol = high score)",
        make(vol_20d), flip=True)

    def amihud_21d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        vs = series_of(inp["volumes"], inp["dates"])
        ill = {}
        for tk in cs:
            seq: list[float | None] = [None] * len(inp["dates"])
            for i, r in enumerate(rs[tk]):
                v = vs[tk][i]
                if r is not None and v and v > 0:
                    seq[i] = abs(r) / (v * 1e3)  # |ret| per unit traded value
            ill[tk] = rolling_mean(seq, 21)
        return ill

    add("amihud_21d", "Amihud (2002)",
        "21-day mean |return|/traded value (illiquidity), higher=more illiq",
        make(amihud_21d))

    def pv_corr_20d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        vs = series_of(inp["volumes"], inp["dates"])
        out = {}
        for tk in cs:
            out[tk] = rolling_corr(
                [None if c is None else math.log(c) for c in cs[tk]],
                [None if v is None else math.log(v + 1.0) for v in vs[tk]],
                20)
        return out

    add("pv_corr_20d", "WorldQuant Alpha#101 (Kakushadze 2015, public)",
        "20-day corr of log close vs log volume, NEGATIVE direction",
        make(pv_corr_20d), flip=True)

    def overnight_gap_21d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        os_ = series_of(inp["opens"], inp["dates"])
        gaps = overnight_of(os_, cs)
        abs_g = {tk: [None if g is None else abs(g) for g in gs]
                 for tk, gs in gaps.items()}
        return {tk: rolling_mean(a, 21) for tk, a in abs_g.items()}

    add("overnight_gap_21d",
        "HuaAn report 2020-09-03 public summary (the Scenario-A factor)",
        "21-day mean |ln(open/prev close)|, NEGATIVE direction",
        make(overnight_gap_21d), flip=True)

    def intraday_21d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        os_ = series_of(inp["opens"], inp["dates"])
        intr = intraday_of(os_, cs)
        return {tk: rolling_mean(v, 21) for tk, v in intr.items()}

    add("intraday_21d",
        "same report's day/night split (public summary)",
        "21-day mean intraday ln(close/open)",
        make(intraday_21d))

    def gap_vol_21d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        os_ = series_of(inp["opens"], inp["dates"])
        gaps = overnight_of(os_, cs)
        return {tk: rolling_std([None if g is None else g for g in gs], 21)
                for tk, gs in gaps.items()}

    add("gap_vol_21d", "overnight-gap family (public summary)",
        "21-day std of the overnight gap, NEGATIVE direction",
        make(gap_vol_21d), flip=True)

    def dist_52w_high(inp):
        cs = series_of(inp["closes"], inp["dates"])
        out = {}
        for tk, xs in cs.items():
            mx = rolling_max(xs, 252)
            out[tk] = [None if (m is None or not c) else c / m - 1.0
                       for c, m in zip(xs, mx)]
        return out

    add("dist_52w_high", "George & Hwang (2004)",
        "distance to the 52-week high (negative = near high = high score)",
        make(dist_52w_high))

    def chan_pos_20d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        out = {}
        for tk, xs in cs.items():
            mx = rolling_max(xs, 20)
            seq: list[float | None] = [None] * len(xs)
            for i, c in enumerate(xs):
                m = mx[i]
                if m is not None and c:
                    seq[i] = c / m  # 1.0 = at channel top
            out[tk] = seq
        return out

    add("chan_pos_20d", "channel position (Donchian family)",
        "close / 20-day max (position in the price channel)",
        make(chan_pos_20d))

    def vol_ratio_5_20(inp):
        vs = series_of(inp["volumes"], inp["dates"])
        out = {}
        for tk, v in vs.items():
            m5 = rolling_mean(v, 5)
            m20 = rolling_mean(v, 20)
            out[tk] = [None if (a is None or b is None or b <= 0) else a / b
                       for a, b in zip(m5, m20)]
        return out

    add("vol_ratio_5_20", "volume-ratio family (public technical lore)",
        "5-day mean volume / 20-day mean volume, NEGATIVE direction "
        "(volume spike = fade)",
        make(vol_ratio_5_20), flip=True)

    def skew_20d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        out = {}
        for tk, r in rs.items():
            buf: list[float] = []
            seq: list[float | None] = [None] * len(r)
            for i, x in enumerate(r):
                if x is None:
                    continue
                buf.append(x)
                if len(buf) > 20:
                    buf.pop(0)
                if len(buf) == 20:
                    m = sum(buf) / 20
                    s2 = sum((b - m) ** 2 for b in buf) / 19
                    if s2 > 0:
                        s = math.sqrt(s2)
                        seq[i] = sum(((b - m) / s) ** 3 for b in buf) / 20
            out[tk] = seq
        return out

    add("skew_20d", "Harvey & Siddique (2000)",
        "20-day return skewness, NEGATIVE direction",
        make(skew_20d), flip=True)

    def max_ret_20d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        return {tk: rolling_max(r, 20) for tk, r in rs.items()}

    add("max_ret_20d", "Bali, Cakici & Whitelaw (2011) lottery MAX",
        "max daily return in 20 days, NEGATIVE direction",
        make(max_ret_20d), flip=True)

    def zero_ret_freq_21d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        out = {}
        for tk, r in rs.items():
            zero = [None if x is None else (1.0 if abs(x) < 1e-9 else 0.0)
                    for x in r]
            out[tk] = rolling_mean(zero, 21)
        return out

    add("zero_ret_freq_21d", "Lesmond et al. (1999) zero-return measure",
        "fraction of zero-return days in 21 (transaction-cost proxy)",
        make(zero_ret_freq_21d))

    def vol_of_vol(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        out = {}
        for tk, r in rs.items():
            s20 = rolling_std(r, 20)
            buf: list[float] = []
            seq: list[float | None] = [None] * len(r)
            for i, x in enumerate(s20):
                if x is None:
                    continue
                buf.append(x)
                if len(buf) > 20:
                    buf.pop(0)
                if len(buf) == 20:
                    m = sum(buf) / 20
                    seq[i] = math.sqrt(
                        sum((b - m) ** 2 for b in buf) / 19)
            out[tk] = seq
        return out

    add("vol_of_vol", "vol-of-vol family (public literature)",
        "20-day std of the 20-day rolling std, NEGATIVE direction",
        make(vol_of_vol), flip=True)

    def run_length(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        out = {}
        for tk, r in rs.items():
            seq: list[float | None] = [None] * len(r)
            run = 0
            for i, x in enumerate(r):
                if x is None:
                    run = 0
                    continue
                if x > 0:
                    run = run + 1 if run > 0 else 1
                elif x < 0:
                    run = run - 1 if run < 0 else -1
                seq[i] = float(run)
            out[tk] = seq
        return out

    add("run_length", "streak/reversal family (public technical lore)",
        "sign run length of consecutive returns, NEGATIVE direction "
        "(long up-streak = fade)",
        make(run_length), flip=True)

    def volume_trend(inp):
        vs = series_of(inp["volumes"], inp["dates"])
        out = {}
        for tk, v in vs.items():
            m20 = rolling_mean(v, 20)
            m60 = rolling_mean(v, 60)
            out[tk] = [None if (a is None or b is None or b <= 0) else a / b
                       for a, b in zip(m20, m60)]
        return out

    add("volume_trend", "volume-trend family (public technical lore)",
        "20d/60d mean-volume ratio, NEGATIVE direction",
        make(volume_trend), flip=True)

    def hl_range_20d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        os_ = series_of(inp["opens"], inp["dates"])
        out = {}
        for tk in cs:
            seq: list[float | None] = []
            for i in range(len(cs[tk])):
                o, c = (os_[tk][i] if tk in os_ and i < len(os_[tk]) else None), cs[tk][i]
                if o and o > 0 and c and c > 0:
                    seq.append(abs(math.log(c / o)))
                else:
                    seq.append(None)
            out[tk] = rolling_mean(seq, 20)
        return out

    add("hl_range_20d", "Parkinson (1980) range volatility",
        "20-day mean |intraday log range|, NEGATIVE direction",
        make(hl_range_20d), flip=True)

    def sharpe_20d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        m = {tk: rolling_mean(r, 20) for tk, r in rs.items()}
        s = {tk: rolling_std(r, 20) for tk, r in rs.items()}
        return {tk: [None if (a is None or b is None or b <= 0) else a / b
                     for a, b in zip(m[tk], s[tk])] for tk in rs}

    add("sharpe_20d", "rolling Sharpe family (public portfolio lore)",
        "20-day mean/std of daily returns",
        make(sharpe_20d))

    def gap_freq_21d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        os_ = series_of(inp["opens"], inp["dates"])
        gaps = overnight_of(os_, cs)
        out = {}
        for tk, gs in gaps.items():
            big = [None if g is None else (1.0 if abs(g) > 0.01 else 0.0)
                   for g in gs]
            out[tk] = rolling_mean(big, 21)
        return out

    add("gap_freq_21d", "overnight-gap family (public summary)",
        "fraction of |gap|>1% days in 21, NEGATIVE direction",
        make(gap_freq_21d), flip=True)

    def ret_vol_scaled_21d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        rs = returns_of(cs)
        m = {tk: rolling_mean(r, 21) for tk, r in rs.items()}
        s = {tk: rolling_std(r, 21) for tk, r in rs.items()}
        return {tk: [None if (a is None or b is None or b <= 0) else a / b
                     for a, b in zip(m[tk], s[tk])] for tk in rs}

    add("ret_vol_scaled_21d", "risk-adjusted reversal (public lore)",
        "21-day mean return / 21-day std, NEGATIVE direction (reversal)",
        make(ret_vol_scaled_21d), flip=True)

    def signed_vol_20d(inp):
        cs = series_of(inp["closes"], inp["dates"])
        vs = series_of(inp["volumes"], inp["dates"])
        rs = returns_of(cs)
        out = {}
        for tk in cs:
            seq: list[float | None] = [None] * len(inp["dates"])
            for i, r in enumerate(rs[tk]):
                v = vs[tk][i]
                if r is not None and v and v > 0:
                    seq[i] = math.copysign(math.log(v + 1.0), r)
            out[tk] = rolling_mean(seq, 20)
        return out

    add("signed_vol_20d", "signed-volume family (public microstructure)",
        "20-day mean of sign(return)*log(volume)",
        make(signed_vol_20d))

    def mom_gap_12m(inp):
        cs = series_of(inp["closes"], inp["dates"])
        os_ = series_of(inp["opens"], inp["dates"])
        gaps = overnight_of(os_, cs)
        gm = {tk: rolling_sum(g, 252) for tk, g in gaps.items()}
        return gm

    add("mom_gap_12m", "overnight-gap family (public summary)",
        "252-day cumulative overnight gap (overnight momentum)",
        make(mom_gap_12m))

    return C


# ---------------------------------------------------------------------------
# fast-lane evaluation
# ---------------------------------------------------------------------------

def evaluate_factor(spec: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    rows = spec["build"](inputs)
    signal = _finalize(rows, inputs["dates"], spec["flip"])
    dates = inputs["dates"]
    closes = inputs["closes"]
    ic = monthly_ic_series(closes, dates, signal)
    summ = ic_summary(ic)
    groups = group_monthly_returns(closes, dates, signal, n_groups=5)
    g1, g5 = groups.get("G1"), groups.get("G5")
    # catalog is oriented higher=better, so the headline spread is the
    # top-minus-bottom (G5 - G1) in the factor's own direction
    spread = (g5 - g1) if (g1 is not None and g5 is not None) else None
    # triple-gate on the monthly IC series (rank-IC sign consistency)
    n = len(ic)
    k1, k2 = max(1, int(n * 0.6)), max(1, int(n * 0.8))
    def mean_ic(seq):
        return (sum(x["ic"] for x in seq) / len(seq)) if seq else None
    train_ic = mean_ic(ic[:k1])
    val_ic = mean_ic(ic[k1:k2])
    oos_ic = mean_ic(ic[k2:])
    pos_share = (sum(1 for x in ic if x["ic"] > 0) / n) if n else None
    return {
        "id": spec["id"], "source": spec["source"], "desc": spec["desc"],
        "flip": spec["flip"],
        "n_months": n,
        "ic_mean": summ.get("ic_mean"),
        "icir": summ.get("icir"),
        "g1_ann": g1, "g5_ann": g5, "top_minus_bottom": spread,
        "train_ic": train_ic, "val_ic": val_ic, "oos_ic": oos_ic,
        "ic_positive_share": pos_share,
    }


def run_zoo(closes: dict[str, dict[str, float]],
            opens: dict[str, dict[str, float]],
            volumes: dict[str, dict[str, float]],
            dates: list[str],
            catalog: list[dict[str, Any]] | None = None,
            ) -> list[dict[str, Any]]:
    """Build every factor once, evaluate on the fast lane, return the
    leaderboard sorted by |IC mean| * sign-consistency (a t-stat-ish
    score: effect size times sqrt of consistent months)."""
    inputs = {"closes": closes, "opens": opens, "volumes": volumes,
              "dates": dates}
    cat = catalog if catalog is not None else build_catalog()
    out = [evaluate_factor(spec, inputs) for spec in cat]
    def score(r):
        # signed: a directionally-dead factor sinks even if |IC| is large;
        # the zoo orients every factor higher=better, so IC<0 means the
        # orientation (and the literature) failed on this sample
        icm = r["ic_mean"]
        if icm is None or r["n_months"] == 0:
            return 0.0
        return icm * math.sqrt(r["n_months"])
    out.sort(key=score, reverse=True)
    return out


def render_leaderboard(rows: list[dict[str, Any]], top: int = 10) -> str:
    lines = [
        "# 因子工厂 leaderboard（快验证层，非认证）",
        "",
        "排序键 = IC均值 × √月数（带符号：定向失败者沉底）；此层只做候选排序，",
        "任何主张仍需走 v1.0 预注册-引擎-门禁全程。top-bottom = G5(最高因子) - G1。",
        "",
        "| # | factor | IC均值 | ICIR | top-bottom年化 | n月 | train/val/oos IC | 出处 |",
        "|---|--------|--------|------|----------------|-----|------------------|------|",
    ]
    for k, r in enumerate(rows[:top], 1):
        def f(x, nd=4):
            return "n/a" if x is None else f"{x:.{nd}f}"
        lines.append(
            f"| {k} | {r['id']} | {f(r['ic_mean'])} | {f(r['icir'])} | "
            f"{f(r['top_minus_bottom'])} | {r['n_months']} | "
            f"{f(r['train_ic'])} / "
            f"{f(r['val_ic'])} / {f(r['oos_ic'])} | {r['source']} |")
    return "\n".join(lines)


def dump_leaderboard(rows: list[dict[str, Any]], path: Path) -> None:
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False,
                               default=str), encoding="utf-8")
