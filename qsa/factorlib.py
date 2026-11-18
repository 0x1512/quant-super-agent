"""Factor library — the accumulated open-source catalog (v1.3 offense).

Three families, every entry carrying its citation and its exact recipe
in ``desc`` (the desc IS the spec: what it says is what the build does):

* **wq_a*** — WorldQuant "101 Formulaic Alphas" (Kakushadze 2015,
  arXiv:1601.00991). Only formulas transcribed with confidence are
  included; the remainder of the paper's list is pending verification
  and deliberately absent — a mis-cited formula is a fabricated factor.
* **range / volatility** — textbook estimators unlocked by the high/low
  panel: Parkinson (1980), Garman-Klass (1980), Rogers-Satchell (1991),
  stochastic %K (Lane), candle anatomy.
* **liquidity / flow** — Amihud (2002) per-dollar illiquidity on the raw
  amount panel, vwap pressure, abnormal-turnover spikes.

``needs`` declares each factor's required input panels;
``build_catalog(available)`` filters, so the same library degrades
gracefully on close-only snapshots. ``FAMILIES`` exposes the window-
parameterized cores of the main families so the mutation search
(qsa/offense.py) sweeps them without duplicating math.
"""
from __future__ import annotations

import math
from typing import Any, Callable

from .factorzoo import (FactorBuild, _finalize, rolling_corr, rolling_max,
                        rolling_mean, rolling_std, rolling_sum, returns_of,
                        series_of)

Rows = dict[str, list[float | None]]
EPS = 1e-12


# Rows-level wrappers around factorzoo's per-ticker list operators
# (factorzoo's rolling_* take one ticker's list; these take the whole
# panel and stay None-propagating).


def rmean(xs: Rows, win: int) -> Rows:
    return {tk: rolling_mean(seq, win) for tk, seq in xs.items()}


def rstd(xs: Rows, win: int) -> Rows:
    return {tk: rolling_std(seq, win) for tk, seq in xs.items()}


def rsum(xs: Rows, win: int) -> Rows:
    return {tk: rolling_sum(seq, win) for tk, seq in xs.items()}


def rmax(xs: Rows, win: int) -> Rows:
    return {tk: rolling_max(seq, win) for tk, seq in xs.items()}


def rcorr(x: Rows, y: Rows, win: int) -> Rows:
    return {tk: rolling_corr(x[tk], y[tk], win) for tk in x}


def _rc(xs: list[float | None], ys: list[float | None],
        win: int) -> list[float | None]:
    return rolling_corr(xs, ys, win)

# ------------------------------------------------------------ series helpers


def log_of(xs: Rows) -> Rows:
    return {tk: [None if x is None or x <= 0 else math.log(x) for x in seq]
            for tk, seq in xs.items()}


def abs_of(xs: Rows) -> Rows:
    return {tk: [None if x is None else abs(x) for x in seq]
            for tk, seq in xs.items()}


def sign_of(xs: Rows) -> Rows:
    return {tk: [None if x is None else
                 (1.0 if x > 0 else -1.0 if x < 0 else 0.0) for x in seq]
            for tk, seq in xs.items()}


def delta(xs: Rows, n: int) -> Rows:
    out: Rows = {}
    for tk, seq in xs.items():
        res: list[float | None] = [None] * len(seq)
        for i in range(len(seq)):
            if i >= n and seq[i] is not None and seq[i - n] is not None:
                res[i] = seq[i] - seq[i - n]
        out[tk] = res
    return out


def shift(xs: Rows, n: int) -> Rows:
    out: Rows = {}
    for tk, seq in xs.items():
        res: list[float | None] = [None] * len(seq)
        for i in range(n, len(seq)):
            res[i] = seq[i - n]
        out[tk] = res
    return out


def rolling_min(xs: Rows, win: int) -> Rows:
    out: Rows = {}
    for tk, seq in xs.items():
        res: list[float | None] = [None] * len(seq)
        window: list[float] = []
        for i, x in enumerate(seq):
            if x is None:
                window = []
                continue
            window.append(x)
            if len(window) > win:
                window.pop(0)
            if len(window) == win:
                res[i] = min(window)
        out[tk] = res
    return out


def _binop(a: Rows, b: Rows, fn: Callable[[float, float], float]) -> Rows:
    out: Rows = {}
    for tk in a:
        bs = b.get(tk, [])
        res: list[float | None] = []
        for i, x in enumerate(a[tk]):
            y = bs[i] if i < len(bs) else None
            res.append(None if (x is None or y is None) else fn(x, y))
        out[tk] = res
    return out


def divide(a: Rows, b: Rows) -> Rows:
    return _binop(a, b, lambda x, y: None if abs(y) < EPS else x / y)


def multiply(a: Rows, b: Rows) -> Rows:
    return _binop(a, b, lambda x, y: x * y)


def add(a: Rows, b: Rows) -> Rows:
    return _binop(a, b, lambda x, y: x + y)


def subtract(a: Rows, b: Rows) -> Rows:
    return _binop(a, b, lambda x, y: x - y)


def scale(xs: Rows, k: float) -> Rows:
    return {tk: [None if x is None else x * k for x in seq]
            for tk, seq in xs.items()}


def where(cond: Rows, a: Rows, b: Rows) -> Rows:
    """Per-element select: cond>0 -> a else b (cond None -> None)."""
    out: Rows = {}
    for tk in cond:
        as_, bs = a.get(tk, []), b.get(tk, [])
        res: list[float | None] = []
        for i, c in enumerate(cond[tk]):
            x = as_[i] if i < len(as_) else None
            y = bs[i] if i < len(bs) else None
            if c is None or x is None or y is None:
                res.append(None)
            else:
                res.append(x if c > 0 else y)
        out[tk] = res
    return out


def cov(xs: Rows, ys: Rows, win: int) -> Rows:
    """Rolling covariance implemented as corr*std_x*std_y (documented;
    mathematically identical to the direct definition)."""
    out: Rows = {}
    for tk in xs:
        corr = _rc(xs[tk], ys[tk], win)
        sx = rolling_std(xs[tk], win)
        sy = rolling_std(ys[tk], win)
        out[tk] = [None if (c is None or a is None or b is None) else c * a * b
                   for c, a, b in zip(corr, sx, sy)]
    return out


# ------------------------------------------------- cross-sectional operations


def cs_rank(xs: Rows) -> Rows:
    """Per-date cross-sectional percentile rank in (0,1]."""
    tickers = sorted(xs)
    out: Rows = {tk: [None] * len(xs[tk]) for tk in xs}
    if not tickers:
        return out
    for i in range(len(xs[tickers[0]])):
        vals = sorted((xs[tk][i], k) for k, tk in enumerate(tickers)
                      if xs[tk][i] is not None)
        m = len(vals)
        for j, (v, k) in enumerate(vals):
            out[tickers[k]][i] = (j + 0.5) / m
    return out


def cs_zscore(xs: Rows) -> Rows:
    tickers = sorted(xs)
    out: Rows = {tk: [None] * len(xs[tk]) for tk in xs}
    if not tickers:
        return out
    for i in range(len(xs[tickers[0]])):
        vals = [xs[tk][i] for tk in tickers if xs[tk][i] is not None]
        if len(vals) < 2:
            continue
        mu = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals))
        if sd < EPS:
            continue
        for tk in tickers:
            v = xs[tk][i]
            if v is not None:
                out[tk][i] = (v - mu) / sd
    return out


# ------------------------------------------------------------- input helpers


def _panels(inputs: dict[str, Any]) -> dict[str, Rows]:
    return {k: series_of(inputs[k], inputs["dates"]) for k in inputs
            if k != "dates"}


def _ret(inputs: dict[str, Any]) -> Rows:
    return returns_of(series_of(inputs["closes"], inputs["dates"]))


def _spec(fid: str, source: str, desc: str, needs: list[str],
          build: FactorBuild, flip: bool = False, win: int | None = None
          ) -> dict[str, Any]:
    sp = {"id": fid, "source": source, "desc": desc, "flip": flip,
          "needs": needs, "build": build}
    if win is not None:
        sp["win"] = win
    return sp


# ------------------------------------------------- window-parameterized cores
# Each family doubles as a library entry at its default window and as a
# mutation-search target (offense.window_variants sweeps other windows).

FAMILIES: dict[str, Callable[[int], dict[str, Any]]] = {}


def _mom_gap(win_months: int) -> dict[str, Any]:
    n = win_months * 21

    def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        cl, op = p["closes"], p["opens"]
        mom = subtract(cl, shift(cl, n))
        gap: Rows = {}
        for tk in cl:
            seq: list[float | None] = [None] * len(cl[tk])
            for i in range(21, len(cl[tk])):
                o = op[tk][i] if tk in op and i < len(op[tk]) else None
                c = cl[tk][i - 21]
                if o is not None and c is not None and o > 0 and c > 0:
                    seq[i] = math.log(o / c)
            gap[tk] = rsum({tk: seq}, 21)[tk]
        return _finalize(subtract(mom, gap), inputs["dates"], False)
    return _spec(f"mom_gap_{win_months}m",
                 "replicated-report family (parameterized)",
                 f"close - shift(close,{n}) minus trailing-21d sum of "
                 "ln(open_t/close_{t-21}); higher=better",
                 ["closes", "opens"], build, win=n)


def _mom(win_months: int) -> dict[str, Any]:
    n = win_months * 21

    def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        cl = p["closes"]
        mom = subtract(divide(cl, shift(cl, n)), {tk: [1.0] * len(cl[tk])
                                                  for tk in cl})
        # skip the most recent month (12-1 construction)
        return _finalize(shift(mom, 21), inputs["dates"], False)
    return _spec(f"mom_{win_months}m", "Jegadeesh-Titman 12-1 "
                 "(parameterized)",
                 f"shift(close,{n})/close - 1, lagged 21d; higher=better",
                 ["closes"], build, win=n)


def _dist_high(win: int) -> dict[str, Any]:
    def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        cl = _panels(inputs)["closes"]
        return _finalize(divide(cl, rmax(cl, win)),
                         inputs["dates"], False)
    return _spec(f"dist_high_{win}d", "George-Hwang (1999) proximity to "
                 "rolling high (parameterized)",
                 f"close/rmax(close,{win}); higher=better",
                 ["closes"], build, win=win)


def _sharpe(win: int) -> dict[str, Any]:
    def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        r = _ret(inputs)
        return _finalize(divide(rmean(r, win), rstd(r, win)),
                         inputs["dates"], False)
    return _spec(f"sharpe_{win}d", "rolling Sharpe (parameterized)",
                 f"mean(ret,{win})/std(ret,{win}); higher=better",
                 ["closes"], build, win=win)


def _intraday(win: int) -> dict[str, Any]:
    def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        co, cl = p["opens"], p["closes"]
        out: Rows = {}
        for tk in cl:
            seq: list[float | None] = []
            for i in range(len(cl[tk])):
                o = co[tk][i] if tk in co and i < len(co[tk]) else None
                c = cl[tk][i]
                seq.append(math.log(c / o)
                           if (o is not None and c is not None
                               and o > 0 and c > 0) else None)
            out[tk] = rmean({tk: seq}, win)[tk]
        return _finalize(out, inputs["dates"], False)
    return _spec(f"intraday_{win}d", "mean intraday log return "
                 "(parameterized)",
                 f"mean(ln(close/open),{win}); higher=better",
                 ["closes", "opens"], build, win=win)


def _vol_of_vol(win: int) -> dict[str, Any]:
    def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        r = _ret(inputs)
        v = rstd(r, win)
        vv = rstd({tk: [None if x is None else x * x for x in v[tk]]
                          for tk in v}, win)
        return _finalize(divide(vv, v), inputs["dates"], False)
    return _spec(f"vol_of_vol_{win}d", "vol-of-vol ratio (parameterized)",
                 f"std(ret^2,{win})/std(ret,{win}); higher=better",
                 ["closes"], build, win=win)


FAMILIES.update({"mom_gap": _mom_gap, "mom": _mom, "dist_high": _dist_high,
                 "sharpe": _sharpe, "intraday": _intraday,
                 "vol_of_vol": _vol_of_vol})


def window_variants(names: list[str], wins: list[int]) -> list[dict[str, Any]]:
    """Mutation-search input: cross every named family with every window."""
    return [FAMILIES[nm](w) for nm in names if nm in FAMILIES for w in wins]


# ---------------------------------------------------------------- the catalog


def _catalog_fixed() -> list[dict[str, Any]]:
    WQ = "Kakushadze, 101 Formulaic Alphas (2015), arXiv:1601.00991"
    cat: list[dict[str, Any]] = []

    def wq(fid: str, formula: str, needs: list[str],
           build: FactorBuild) -> None:
        cat.append(_spec(fid, WQ, formula, needs, build))

    def a2(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        x = cs_rank(delta(log_of(p["volumes"]), 2))
        y = cs_rank(divide(subtract(p["closes"], p["opens"]), p["opens"]))
        out = {tk: [None if c is None else -c
                    for c in _rc(x[tk], y[tk], 6)] for tk in x}
        return _finalize(out, inputs["dates"], False)

    wq("wq_a2", "Alpha#2: -1*corr(rank(delta(ln(volume),2)), "
        "rank((close-open)/open), 6)", ["closes", "opens", "volumes"], a2)

    def a3(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        x, y = cs_rank(p["opens"]), cs_rank(p["volumes"])
        out = {tk: [None if c is None else -c
                    for c in _rc(x[tk], y[tk], 10)] for tk in x}
        return _finalize(out, inputs["dates"], False)

    wq("wq_a3", "Alpha#3: -1*corr(rank(open), rank(volume), 10)",
        ["opens", "volumes"], a3)

    def a6(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        out = {tk: [None if c is None else -c
                    for c in _rc(p["opens"][tk], p["volumes"][tk], 10)]
               for tk in p["opens"]}
        return _finalize(out, inputs["dates"], False)

    wq("wq_a6", "Alpha#6: -1*corr(open, volume, 10)",
        ["opens", "volumes"], a6)

    def a8(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        r = _ret(inputs)
        s = multiply(rsum(p["opens"], 5), rsum(r, 5))
        return _finalize(scale(cs_rank(subtract(s, shift(s, 10))), -1),
                         inputs["dates"], False)

    wq("wq_a8", "Alpha#8: -1*rank(sum(open,5)*sum(ret,5) - "
        "delay(sum(open,5)*sum(ret,5),10))", ["closes", "opens"], a8)

    def a12(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        return _finalize(multiply(sign_of(delta(p["volumes"], 1)),
                                  scale(delta(p["closes"], 1), -1)),
                         inputs["dates"], False)

    wq("wq_a12", "Alpha#12: sign(delta(volume,1)) * (-1*delta(close,1))",
        ["closes", "volumes"], a12)

    def a13(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        c = cov(cs_rank(p["closes"]), cs_rank(p["volumes"]), 5)
        return _finalize(scale(cs_rank(c), -1), inputs["dates"], False)

    wq("wq_a13", "Alpha#13: -1*rank(cov(rank(close), rank(volume),5)); "
        "cov = corr*std*std", ["closes", "volumes"], a13)

    def a14(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        r = _ret(inputs)
        left = scale(cs_rank(delta(r, 3)), -1)
        corr = {tk: _rc(p["opens"][tk], p["volumes"][tk], 10)
                for tk in p["opens"]}
        return _finalize(multiply(left, corr), inputs["dates"], False)

    wq("wq_a14", "Alpha#14: -rank(delta(ret,3)) * corr(open,volume,10)",
        ["closes", "opens", "volumes"], a14)

    def a15(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        hi, vol = cs_rank(p["highs"]), cs_rank(p["volumes"])
        corr = {tk: _rc(hi[tk], vol[tk], 3) for tk in p["highs"]}
        ranked = cs_rank(corr)
        summed = {tk: rsum({tk: seq}, 3)[tk]
                  for tk, seq in ranked.items()}
        return _finalize(scale(summed, -1), inputs["dates"], False)

    wq("wq_a15", "Alpha#15: -1*sum(rank(corr(rank(high),rank(volume),3)),3)",
        ["highs", "volumes"], a15)

    def a16(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        c = cov(cs_rank(p["highs"]), cs_rank(p["volumes"]), 5)
        return _finalize(scale(cs_rank(c), -1), inputs["dates"], False)

    wq("wq_a16", "Alpha#16: -1*rank(cov(rank(high),rank(volume),5)); "
        "cov = corr*std*std", ["highs", "volumes"], a16)

    def a19(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        r = _ret(inputs)
        cl = p["closes"]
        inner = add(subtract(cl, shift(cl, 7)), delta(cl, 7))
        base = scale(sign_of(inner), -1)
        tail = add(cs_rank(add(rsum(r, 250), {tk: [1.0] * len(cl[tk])
                                                        for tk in cl})),
                   {tk: [1.0] * len(cl[tk]) for tk in cl})
        return _finalize(multiply(base, tail), inputs["dates"], False)

    wq("wq_a19", "Alpha#19: -sign((close-delay(close,7))+delta(close,7)) * "
        "(1+rank(1+sum(ret,250)))", ["closes"], a19)

    def a23(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        hi = p["highs"]
        avg20 = rmean(hi, 20)
        cond = subtract(hi, avg20)  # >0 iff high > mean(high,20)
        body = scale(delta(hi, 2), -1)
        zero = {tk: [0.0] * len(hi[tk]) for tk in hi}
        return _finalize(where(cond, body, zero), inputs["dates"], False)

    wq("wq_a23", "Alpha#23: (sum(high,20)/20 < high) ? -delta(high,2) : 0",
        ["highs"], a23)

    def a24(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        p = _panels(inputs)
        cl = p["closes"]
        sma100 = rmean(cl, 100)
        # paper: (delta(sma(close,100),100) / delay(close,100)) <= 0.05
        # (the paper writes `< 0.05 || == 0.05`, i.e. <=; the EPS makes
        # the equality branch reachable in floating point)
        cond = divide(delta(sma100, 100), shift(cl, 100))
        branch1 = scale(subtract(cl, rolling_min(cl, 100)), -1)
        branch2 = scale(delta(cl, 3), -1)
        pick = subtract({tk: [0.05 + 1e-12] * len(cl[tk]) for tk in cl},
                        cond)
        return _finalize(where(pick, branch1, branch2),
                         inputs["dates"], False)

    wq("wq_a24", "Alpha#24: (delta(sma(close,100),100)/delay(close,100) "
        "<= 0.05) ? -(close-ts_min(close,100)) : -delta(close,3)",
        ["closes"], a24)

    # ---------------- range / volatility (textbook, need highs+lows) -----
    def parkinson(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            hl = {tk: [None if (h is None or l is None or h <= 0 or l <= 0)
                       else math.log(h / l) ** 2
                       for h, l in zip(p["highs"][tk], p["lows"][tk])]
                  for tk in p["highs"]}
            out = rmean(hl, win)
            return _finalize(out, inputs["dates"], True)
        return build

    cat.append(_spec("parkinson_vol_20d", "Parkinson (1980), J. Business",
                     "mean(ln(H/L)^2,20)/(4*ln2); flip: low-vol anomaly",
                     ["highs", "lows"], parkinson(20), flip=True))

    def gk(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            h, l = p["highs"], p["lows"]
            o, c = p["opens"], p["closes"]
            half = {tk: [0.5 * math.log(hh / ll) ** 2
                         if (hh and ll and hh > 0 and ll > 0) else None
                         for hh, ll in zip(h[tk], l[tk])] for tk in h}
            co = {tk: [math.log(cc / oo) ** 2
                       if (oo and cc and oo > 0 and cc > 0) else None
                       for oo, cc in zip(o.get(tk, []), c[tk])] for tk in c}
            a = rmean(half, win)
            b = rmean(co, win)
            out = subtract(a, scale(b, 2 * math.log(2) - 1))
            return _finalize(out, inputs["dates"], True)
        return build

    cat.append(_spec("garman_klass_20d", "Garman & Klass (1980), J. Business",
                     "0.5*mean(ln(H/L)^2,20) - (2ln2-1)*mean(ln(C/O)^2,20);"
                     " flip: low-vol anomaly",
                     ["closes", "opens", "highs", "lows"], gk(20), flip=True))

    def rs(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            h, l, o, c = p["highs"], p["lows"], p["opens"], p["closes"]
            out: Rows = {}
            for tk in h:
                seq: list[float | None] = []
                for i in range(len(h[tk])):
                    hh, ll = h[tk][i], l[tk][i]
                    oo = o[tk][i] if tk in o and i < len(o[tk]) else None
                    cc = c[tk][i]
                    if None in (hh, ll, oo, cc) or min(hh, ll, oo, cc) <= 0:
                        seq.append(None)
                        continue
                    seq.append(math.log(hh / cc) * math.log(hh / oo)
                               + math.log(ll / cc) * math.log(ll / oo))
                out[tk] = rmean({tk: seq}, win)[tk]
            return _finalize(out, inputs["dates"], True)
        return build

    cat.append(_spec("rogers_satchell_20d", "Rogers & Satchell (1991), "
                     "Ann. Appl. Prob.",
                     "mean(ln(H/C)ln(H/O)+ln(L/C)ln(L/O),20); flip: "
                     "low-vol anomaly", ["closes", "opens", "highs", "lows"],
                     rs(20), flip=True))

    def range_ratio(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            hl = {tk: [None if (h is None or l is None or h <= 0 or l <= 0)
                       else math.log(h / l) ** 2
                       for h, l in zip(p["highs"][tk], p["lows"][tk])]
                  for tk in p["highs"]}
            pk = rmean(hl, win)
            r = _ret(inputs)
            cc = rstd(r, win)
            out = divide(pk, multiply(cc, cc))
            return _finalize(out, inputs["dates"], False)
        return build

    cat.append(_spec("range_ratio_20d", "range-vs-close variance ratio "
                     "(spirit of Alizadeh, Brandt & Diebold 2002)",
                     "parkinson_20d / std(ret,20)^2 — relative range "
                     "activity", ["closes", "highs", "lows"],
                     range_ratio(20)))

    def stoch_k(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            cl = p["closes"]
            hh = rmax(p["highs"], win)
            ll = rolling_min(p["lows"], win)
            out = divide(subtract(cl, ll), subtract(hh, ll))
            return _finalize(out, inputs["dates"], True)
        return build

    cat.append(_spec("stoch_k_14d", "Lane stochastic %K (classic TA)",
                     "(C-min(L,14))/(max(H,14)-min(L,14)); flip: "
                     "overbought reversal", ["closes", "highs", "lows"],
                     stoch_k(14), flip=True))

    def shadow_upper(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            h, l, o, c = p["highs"], p["lows"], p["opens"], p["closes"]
            out: Rows = {}
            for tk in h:
                seq: list[float | None] = []
                for i in range(len(h[tk])):
                    hh, ll = h[tk][i], l[tk][i]
                    oo = o[tk][i] if tk in o and i < len(o[tk]) else None
                    cc = c[tk][i]
                    rng = (hh - ll) if None not in (hh, ll) else None
                    if rng is None or rng <= 0 or oo is None or cc is None:
                        seq.append(None)
                        continue
                    body_hi = oo if oo >= cc else cc
                    seq.append((hh - body_hi) / rng)
                out[tk] = rmean({tk: seq}, win)[tk]
            return _finalize(out, inputs["dates"], True)
        return build

    cat.append(_spec("shadow_upper_20d", "candle anatomy (classic TA)",
                     "mean((H-max(O,C))/(H-L),20); flip: selling pressure "
                     "at the top", ["closes", "opens", "highs", "lows"],
                     shadow_upper(20), flip=True))

    def body_eff(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            o, c = p["opens"], p["closes"]
            co: Rows = {}
            for tk in c:
                seq = [math.log(cc / oo) if (oo and cc and oo > 0 and cc > 0)
                       else None
                       for oo, cc in zip(o.get(tk, []), c[tk])]
                co[tk] = seq
            return _finalize(divide(rmean(co, win),
                                    rmean(abs_of(co), win)),
                             inputs["dates"], False)
        return build

    cat.append(_spec("body_eff_20d", "candle anatomy (classic TA)",
                     "mean(ln(C/O),20)/mean(|ln(C/O)|,20) — directional "
                     "body efficiency", ["closes", "opens"], body_eff(20)))

    # ---------------- liquidity / flow (need amounts and/or vwap) --------
    def amihud(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            r = _ret(inputs)
            ill = divide(abs_of(r), p["amounts"])
            return _finalize(rmean(ill, win), inputs["dates"], True)
        return build

    cat.append(_spec("amihud_dollar_21d", "Amihud (2002), J. Fin. Markets",
                     "mean(|ret|/amount,21); flip: illiquidity premium",
                     ["closes", "amounts"], amihud(21), flip=True))

    def vwap_premium(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            prem = divide(subtract(p["closes"], p["vwaps"]), p["vwaps"])
            return _finalize(rmean(prem, win), inputs["dates"], False)
        return build

    cat.append(_spec("vwap_premium_5d", "vwap pressure (standard micro-"
                     "structure folklore)", "mean((close-vwap)/vwap,5)",
                     ["closes", "vwaps"], vwap_premium(5)))

    def vwap_vol_corr(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            x = cs_rank(divide(p["closes"], p["vwaps"]))
            y = cs_rank(p["volumes"])
            out = {tk: [None if c is None else -c
                        for c in _rc(x[tk], y[tk], win)]
                   for tk in x}
            return _finalize(out, inputs["dates"], False)
        return build

    cat.append(_spec("vwap_vol_corr_10", "price-volume divergence "
                     "(WorldQuant 101 spirit)",
                     "-corr(rank(close/vwap),rank(volume),10)",
                     ["closes", "volumes", "vwaps"], vwap_vol_corr(10)))

    def amount_spike(short: int, long: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            base = rmean(p["amounts"], long)
            ratio = divide(p["amounts"], base)
            return _finalize(rmean(ratio, short), inputs["dates"],
                             True)
        return build

    cat.append(_spec("amount_spike_5_60", "abnormal turnover (classic TA)",
                     "mean(amount/mean(amount,60),5); flip: spike reversal",
                     ["amounts"], amount_spike(5, 60), flip=True))

    def size_proxy(win: int) -> FactorBuild:
        def build(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
            p = _panels(inputs)
            lg = rmean(log_of(p["amounts"]), win)
            return _finalize(cs_zscore(lg), inputs["dates"], True)
        return build

    cat.append(_spec("ln_amount_z_20d", "size proxy (classic)",
                     "-zscore(mean(ln(amount),20)); flip: small-liquidity "
                     "premium", ["amounts"], size_proxy(20), flip=True))

    return cat


_FIXED_CACHE: list[dict[str, Any]] | None = None


def _fixed() -> list[dict[str, Any]]:
    global _FIXED_CACHE
    if _FIXED_CACHE is None:
        _FIXED_CACHE = _catalog_fixed()
    return _FIXED_CACHE


DEFAULTS = {"mom_gap": 12, "mom": 12, "dist_high": 252, "sharpe": 21,
            "intraday": 21, "vol_of_vol": 20}


def build_catalog(available: set[str] | None = None
                  ) -> list[dict[str, Any]]:
    """The whole library, filtered to the panels ``available`` (keys of
    the inputs dict, e.g. {'closes','opens','volumes','dates'}). Specs
    whose needs are not met are simply absent — no silent degradation."""
    avail = set(available) if available is not None else None
    out: list[dict[str, Any]] = []
    for sp in _fixed() + [FAMILIES[k](w)
                          for k, w in DEFAULTS.items()]:
        if avail is None or set(sp["needs"]) <= avail:
            out.append(sp)
    return out


def catalog_summary() -> list[dict[str, str]]:
    """Human-facing inventory: id, family, needs — for docs and the demo."""
    fam = {"wq_a": "WorldQuant 101", "parkinson": "range/vol",
           "garman": "range/vol", "rogers": "range/vol",
           "range_ratio": "range/vol", "stoch": "range/vol",
           "shadow": "range/vol", "body_eff": "range/vol",
           "amihud": "liquidity", "vwap": "liquidity", "amount": "liquidity",
           "ln_amount": "liquidity"}
    rows = []
    for sp in build_catalog():
        prefix = sp["id"].split("_")[0]
        family = "parameterized" if "win" in sp else fam.get(
            prefix, next((v for k, v in fam.items()
                          if sp["id"].startswith(k)), "other"))
        rows.append({"id": sp["id"], "family": family,
                     "needs": ",".join(sp["needs"]), "source": sp["source"]})
    return rows
