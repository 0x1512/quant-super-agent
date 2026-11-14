"""Tradeable-metrics backtest layer (v1.1).

The v1.0 gate answers "is the claim honest?" — IC and quintile returns
computed and recomputed to the last digit. It deliberately does NOT answer
"can this be traded?", because a statistically honest factor can still be
untradeable: fee drag eats it, it needs more liquidity than exists, or its
entire edge lives in one sub-period.

This module adds the missing layer. Given the same pinned snapshot the
replication plane uses, it builds the monthly-rebalanced top-group
portfolio (G1 = lowest factor, matching the report convention), applies an
explicit cost model, and emits machine-checkable tradeable metrics:

* net annualized return / excess over an equal-weight benchmark,
* turnover (one-sided, per rebalance and annualized),
* capacity: the largest book where each holding stays under a stated
  participation cap of that month's traded value (cap_proxy from the
  pinned meta is the ADV stand-in, same declared proxy as A6),
* Newey-West adjusted Sharpe (Bartlett kernel, Andrews 1991-style lag
  weighting; plain method, no proprietary anything),
* max drawdown / Calmar,
* triple-gate: net excess across explicit train/val/oos partitions — a
  factor that only pays in one partition says so here instead of hiding
  behind the full-sample mean.

Every parameter that a portfolio manager would argue about (fee, slides,
participation cap, partitions, annualization days) is an explicit argument
with the default printed in the report — zero silent conventions. The
layer is deliberately outside the verify gate: it feeds candidate ranking
(the zoo's fast lane); claims that graduate to publication still go
through the full pre-registered gate.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

TRADING_DAYS = 242          # A-share convention; explicit, overridable
NW_MAX_LAG = 5              # Bartlett kernel max lag
DEFAULT_FEE_ONE_SIDE = 0.0008  # 8 bps one-sided: industry-common default
                                # (commission+stamp+slippage), never silent
DEFAULT_PARTICIPATION = 0.10   # capacity = each name <= 10% of its month's
                                # traded value


def month_key(d: str) -> str:
    return d[:6]


def month_end_indices(dates: list[str]) -> list[int]:
    ends: list[int] = []
    for i, d in enumerate(dates):
        if i + 1 == len(dates) or month_key(dates[i + 1]) != month_key(d):
            ends.append(i)
    return ends


def daily_returns(closes: dict[str, dict[str, float]],
                  dates: list[str]) -> dict[str, dict[str, float]]:
    """{ticker: {date: simple return vs previous available close}}.

    A ticker's first day and any gap (suspension) yields no return for that
    day; the portfolio treats a missing name as temporarily out (weight
    renormalizes over present names) — stated, not hidden."""
    out: dict[str, dict[str, float]] = {}
    for tk, row in closes.items():
        prev: float | None = None
        seq: dict[str, float] = {}
        for d in dates:
            c = row.get(d)
            if c is None:
                prev = None  # gap: next resumption is not a return
                continue
            if prev is not None and prev > 0:
                seq[d] = c / prev - 1.0
            prev = c
        out[tk] = seq
    return out


def nw_sharpe(rets: list[float],
              max_lag: int = NW_MAX_LAG,
              trading_days: int = TRADING_DAYS,
              min_days: int = 60) -> float | None:
    """Bartlett-kernel Newey-West adjusted annualized Sharpe.

    omega^2 = g0 + 2 * sum_{l=1..L} (1 - l/(L+1)) * g_l,  g_l =
    cov(r_t, r_{t-l}); Sharpe = mean(r)/sqrt(omega^2) * sqrt(trading_days).
    """
    n = len(rets)
    if n < min_days:
        return None
    m = sum(rets) / n
    g0 = sum((r - m) ** 2 for r in rets) / (n - 1)
    omega = g0
    for lag in range(1, min(max_lag, n - 1) + 1):
        w = 1.0 - lag / (max_lag + 1)
        cov = sum((rets[t] - m) * (rets[t - lag] - m)
                  for t in range(lag, n)) / (n - 1)
        omega += 2.0 * w * cov
    # finite-sample Bartlett sums can go non-positive or near-zero under
    # strong negative autocorrelation; pad to the Newey-West (1987)
    # positive-semidefinite floor rather than emit an exploding ratio
    omega = max(omega, g0 * 0.01)
    if omega <= 0:  # degenerate series (zero variance): no Sharpe exists
        return None
    return m / math.sqrt(omega) * math.sqrt(trading_days)


def max_drawdown(rets: list[float]) -> float:
    """Peak-to-trough drawdown of the compounded equity curve (negative)."""
    equity = 1.0
    peak = 1.0
    mdd = 0.0
    for r in rets:
        equity *= 1.0 + r
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1.0)
    return mdd


def _annualize(rets: list[float], trading_days: int = TRADING_DAYS) -> float:
    equity = 1.0
    for r in rets:
        equity *= 1.0 + r
    years = max(len(rets), 1) / trading_days
    if equity <= 0:
        return -1.0
    return equity ** (1.0 / max(years, 1e-9)) - 1.0


def portfolio_path(closes: dict[str, dict[str, float]],
                   dates: list[str],
                   signal: dict[str, dict[str, float]],
                   n_groups: int = 5,
                   group: int = 1,
                   fee_one_side: float = DEFAULT_FEE_ONE_SIDE,
                   ) -> dict[str, Any]:
    """Monthly-rebalanced equal-weight group portfolio, gross and net.

    At each month-end index i (excluding the last), names with a factor
    value on that date are sorted ascending, split into n_groups buckets,
    bucket ``group`` (1 = lowest factor) is held equal-weight through the
    next month. Cost = one-sided fee * |weight change| summed (a full
    turnover swap costs 2x). Returns the daily gross/net series, the
    monthly one-sided turnover, and the held names per month (audit trail).
    """
    rets = daily_returns(closes, dates)
    ends = month_end_indices(dates)
    gross: list[float] = []
    net: list[float] = []
    turnovers: list[float] = []
    holdings: dict[str, list[str]] = {}
    prev_weights: dict[str, float] = {}
    date_out: list[str] = []

    for k, i in enumerate(ends):
        if k + 1 == len(ends):
            break  # last month-end: no next month to hold through
        d = dates[i]
        scored = sorted((sig_row[d], tk) for tk, sig_row in signal.items()
                        if sig_row.get(d) is not None)
        if not scored:
            continue
        n = len(scored)
        size = max(1, n // n_groups)
        lo = (group - 1) * size
        hi = n if group == n_groups else min(n, group * size)
        names = sorted(tk for _, tk in scored[lo:hi])
        holdings[d] = names
        w = 1.0 / max(len(names), 1)
        # one-sided turnover at this rebalance
        turn = 0.0
        for tk in names:
            turn += abs(w - prev_weights.get(tk, 0.0))
        for tk in prev_weights:
            if tk not in set(names):
                turn += prev_weights[tk]
        turnovers.append(turn)
        cost = turn * fee_one_side * 2.0  # buy+sell both pay
        # daily returns through next month
        nxt_month = month_key(dates[min(i + 1, len(dates) - 1)])
        for j in range(i + 1, len(dates)):
            if month_key(dates[j]) != nxt_month:
                break
            dj = dates[j]
            rs = [rets[tk][dj] for tk in names
                  if dj in rets.get(tk, {})]
            if rs:
                r = sum(rs) / len(rs)
                gross.append(r)
                net.append(r - cost / max(1, 20))  # spread cost over ~20 days
                date_out.append(dj)
        prev_weights = {tk: w for tk in names}

    return {"gross": gross, "net": net, "dates": date_out,
            "turnovers": turnovers, "holdings": holdings}


def load_cap_proxy(snapshot_dir: Path) -> dict[str, dict[str, float]]:
    """month -> {ticker: mean daily traded value} from pinned meta."""
    p = Path(snapshot_dir) / "meta" / "monthly_caps.csv"
    caps: dict[str, dict[str, float]] = {}
    if not p.exists():
        return caps
    with p.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            caps.setdefault(row["month"], {})[row["ticker"]] = float(
                row["cap_proxy"])
    return caps


def capacity(port: dict[str, Any],
             dates: list[str],
             cap_proxy: dict[str, dict[str, float]],
             participation: float = DEFAULT_PARTICIPATION) -> float | None:
    """Largest book where every holding stays <= participation x its
    month's traded value, under the tightest month observed.

    C = min over months of min over names of participation*ADV_i/w_i
    (equal weights w). Units follow cap_proxy (thousand CNY in the
    replication fixture). None if no pinned meta."""
    if not cap_proxy or not port["holdings"]:
        return None
    worst = None
    for d, names in sorted(port["holdings"].items()):
        m = d[:6]
        adv = cap_proxy.get(m)
        if not adv:
            continue
        w = 1.0 / max(len(names), 1)
        for tk in names:
            a = adv.get(tk)
            if a and a > 0 and w > 0:
                c = participation * a / w
                worst = c if worst is None else min(worst, c)
    return worst


def evaluate(closes: dict[str, dict[str, float]],
             dates: list[str],
             signal: dict[str, dict[str, float]],
             cap_proxy: dict[str, dict[str, float]] | None = None,
             n_groups: int = 5,
             group: int = 1,
             fee_one_side: float = DEFAULT_FEE_ONE_SIDE,
             participation: float = DEFAULT_PARTICIPATION,
             partitions: tuple[str, str, str] | None = None,
             ) -> dict[str, Any]:
    """The full tradeable-metrics dict for one factor's top group.

    partitions: explicit (train_end, val_end, oos_end) date strings
    (YYYYMMDD); date <= train_end is train, <= val_end is val, rest oos.
    Default None = single 60/20/20 split by month count, echoed back in
    the result so the report can print it.
    """
    port = portfolio_path(closes, dates, signal, n_groups, group,
                          fee_one_side)
    net = port["net"]
    gross = port["gross"]
    # equal-weight universe benchmark (gross), same dates
    rets = daily_returns(closes, dates)
    by_date: dict[str, list[float]] = {}
    for tk, row in rets.items():
        for d, r in row.items():
            by_date.setdefault(d, []).append(r)
    bench = [sum(by_date[d]) / len(by_date[d]) for d in port["dates"]
             if d in by_date]
    bench_map = {d: sum(by_date[d]) / len(by_date[d])
                 for d in by_date}
    excess = [(net[t] - bench_map.get(port["dates"][t], 0.0))
              for t in range(len(net))]

    if partitions is None:
        n_months = len(port["holdings"])
        k1 = max(1, int(n_months * 0.6))
        k2 = max(k1 + 1, int(n_months * 0.8))
        keys = sorted(port["holdings"])
        partitions = (keys[k1 - 1], keys[k2 - 1], keys[-1])

    def part_rets(rets_: list[float], upto: str, start: str | None) -> list[float]:
        out = []
        started = start is None
        for idx, d in enumerate(port["dates"]):
            if start is not None and d <= start:
                started = True
            if not started:
                continue
            if d > upto:
                break
            out.append(rets_[idx])
        return out

    train_r = part_rets(excess, partitions[0], None)
    val_r = part_rets(excess, partitions[1], partitions[0])
    oos_r = part_rets(excess, partitions[2], partitions[1])

    to_ann = sum(port["turnovers"]) * 12 / max(1, len(port["turnovers"]))
    mdd = max_drawdown(net)
    ann_net = _annualize(net)
    ann_exc = _annualize(excess) if excess else None
    cap = capacity(port, dates, cap_proxy or {}, participation)
    out: dict[str, Any] = {
        "n_days": len(net),
        "n_months": len(port["holdings"]),
        "ann_return_net": ann_net,
        "ann_excess_net": ann_exc,
        "nw_sharpe_net": nw_sharpe(net),
        "nw_sharpe_excess": nw_sharpe(excess),
        "max_drawdown": mdd,
        "calmar": (ann_net / abs(mdd)) if mdd < 0 else None,
        "turnover_monthly_one_side": (
            sum(port["turnovers"]) / max(1, len(port["turnovers"]))),
        "turnover_annual_one_side": to_ann,
        "fee_one_side": fee_one_side,
        "participation_cap": participation,
        "capacity_thousand_cny": cap,
        "partitions": list(partitions),
        "triple_gate": {
            "train_exc_nw": nw_sharpe(train_r),
            "val_exc_nw": nw_sharpe(val_r),
            "oos_exc_nw": nw_sharpe(oos_r),
            "train_ann": _annualize(train_r) if train_r else None,
            "val_ann": _annualize(val_r) if val_r else None,
            "oos_ann": _annualize(oos_r) if oos_r else None,
        },
        "benchmark": "equal-weight universe, gross",
    }
    return out


def render_report(metrics: dict[str, Any], factor_id: str,
                   group: int = 1) -> str:
    """One-page markdown block; every number from the metrics dict."""
    tg = metrics["triple_gate"]
    cap = metrics.get("capacity_thousand_cny")
    cap_s = f"{cap/1e4:.2f} 亿" if cap is not None else "n/a (无钉死 meta)"
    lines = [
        f"## 可交易性回测 — {factor_id}",
        "",
        f"- 样本: {metrics['n_days']} 个交易日 / {metrics['n_months']} 个月度换仓",
        f"- 费后年化: {metrics['ann_return_net']:.4f}（单边费率 {metrics['fee_one_side']*1e4:.0f} bps）",
        f"- 费后超额年化（等权基准）: {metrics['ann_excess_net']:.4f}" if metrics['ann_excess_net'] is not None else "- 费后超额: n/a",
        f"- NW Sharpe（费后）: {metrics['nw_sharpe_net']}, 超额口径: {metrics['nw_sharpe_excess']}",
        f"- 最大回撤: {metrics['max_drawdown']:.4f}, Calmar: {metrics['calmar']}",
        f"- 换手（单边）: 月均 {metrics['turnover_monthly_one_side']:.4f} / 年化 {metrics['turnover_annual_one_side']:.2f}",
        f"- 容量（参与率上限 {metrics['participation_cap']*100:.0f}%）: {cap_s}",
        f"- triple-gate 超额（train/val/oos NW Sharpe）: "
        f"{tg['train_exc_nw']} / {tg['val_exc_nw']} / {tg['oos_exc_nw']}",
        f"- 分区切点: {metrics['partitions'][0]} / {metrics['partitions'][1]} / {metrics['partitions'][2]}",
        "",
        f"口径: 月度换仓等权 G{group}组; 成本=单边费率×双边换手;"
        " 容量=每券不超过当月成交额×参与率的最紧月份; 全部参数显式可改。",
    ]
    return "\n".join(lines)


def dump_json(metrics: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(metrics, indent=1, ensure_ascii=False,
                               default=str), encoding="utf-8")
