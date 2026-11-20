"""Long-short PnL layer — 组合级模拟（v1.5 展示层）.

对齐业界展示要素（WorldQuant BRAIN 的 alpha PnL、alphalens 的
分位组合、聚宽/米筐的回测报告），复用 backtest.py 的月度再平衡
与成本模型，叠加多空组合：

* G5（高因子组）做多 − G1（低因子组）做空，各自等权、月度换仓；
* 日级净收益 → 月度复利 → 累计净值曲线（G5/G1/L-S 三线）；
* 费后年化、NW Sharpe、最大回撤、Calmar、月均单边换手、费率
  拖累；年度收益表；
* 假设全显式（等权 / 月度再平衡 / 单边费率 / 成本摊 20 交易日 /
  G1=低因子）——这是**模拟 PnL**，不是实盘主张；对外数字唯一
  路径仍是冻结 run。

纯函数、零依赖（同 backtest 的 stdlib 纪律）。
"""
from __future__ import annotations

from typing import Any

from .backtest import (_annualize, max_drawdown, month_key,
                       month_end_indices, nw_sharpe, portfolio_path,
                       DEFAULT_FEE_ONE_SIDE)


def _monthly(net: list[float], dates: list[str]) -> tuple[list[str],
                                                           list[float]]:
    """日净收益 → 月度复利收益（∏(1+r)−1），按月聚齐."""
    out_m, out_r = [], []
    cur_key, acc = None, 1.0
    for r, d in zip(net, dates):
        k = month_key(d)
        if cur_key is None:
            cur_key = k
        if k != cur_key:
            out_m.append(cur_key)
            out_r.append(acc - 1.0)
            cur_key, acc = k, 1.0
        acc *= (1.0 + r)
    if cur_key is not None:
        out_m.append(cur_key)
        out_r.append(acc - 1.0)
    return out_m, out_r


def _yearly(months: list[str], rets: list[float]) -> list[tuple[str, float]]:
    by: dict[str, float] = {}
    for m, r in zip(months, rets):
        by[m[:4]] = by.get(m[:4], 1.0) * (1.0 + r)
    return sorted((y, v - 1.0) for y, v in by.items())


_BENCH_CACHE: dict[Any, Any] = {"key": None, "daily": None}


def _bench_monthly(closes: dict[str, dict[str, float]],
                   dates: list[str],
                   out_dates: list[str]) -> list[float]:
    """等权全市场基准的月度复利（与 L-S 同月对齐）.

    基准只依赖 closes/dates（与信号无关），同一数据面下按
    (id, 边界) 缓存日度等权收益，避免 59 因子重复重算。
    """
    from .backtest import daily_returns
    key = (id(closes), id(dates), dates[0] if dates else "",
           dates[-1] if dates else "", len(dates))
    daily = _BENCH_CACHE["daily"]
    if daily is None or _BENCH_CACHE["key"] != key:
        rets = daily_returns(closes, dates)
        by_date: dict[str, float] = {}
        cnt: dict[str, int] = {}
        for row in rets.values():
            for d, r in row.items():
                by_date[d] = by_date.get(d, 0.0) + r
                cnt[d] = cnt.get(d, 0) + 1
        daily = {d: by_date[d] / cnt[d] for d in by_date if cnt.get(d)}
        _BENCH_CACHE["key"] = key
        _BENCH_CACHE["daily"] = daily
    months, mr = _monthly([daily.get(d, 0.0) for d in out_dates],
                          out_dates)
    return mr


def _sortino(daily: list[float]) -> float | None:
    """年化收益 / 下行偏差（Sortino，MAR=0）."""
    if not daily:
        return None
    downside = [r for r in daily if r < 0]
    if len(downside) < 2:
        return None
    dd = (sum(r * r for r in downside) / len(daily)) ** 0.5 * (252 ** 0.5)
    if dd <= 0:
        return None
    return _annualize(daily) / dd


def longshort_pnl(closes: dict[str, dict[str, float]],
                  dates: list[str],
                  signal: dict[str, dict[str, float]],
                  n_groups: int = 5,
                  fee_one_side: float = DEFAULT_FEE_ONE_SIDE,
                  ) -> dict[str, Any] | None:
    """G5−G1 多空组合的月度净值与指标（费后）.

    返回 None 当样本不足以分组（同 no-guessing 纪律）。
    L-S 日收益 = G5 净 − G1 净（两边各担自身成本与摊销）。
    """
    g5 = portfolio_path(closes, dates, signal, n_groups, n_groups,
                        fee_one_side)
    g1 = portfolio_path(closes, dates, signal, n_groups, 1, fee_one_side)
    n = min(len(g5["net"]), len(g1["net"]))
    if n < 20 or not g5["dates"][:n] == g1["dates"][:n]:
        return None
    ls_daily = [g5["net"][i] - g1["net"][i] for i in range(n)]
    ls_dates = g5["dates"][:n]
    months, ls_m = _monthly(ls_daily, ls_dates)
    _, g5_m = _monthly(g5["net"][:n], ls_dates)
    _, g1_m = _monthly(g1["net"][:n], ls_dates)

    nav_ls, nav = 1.0, []
    for r in ls_m:
        nav_ls *= (1.0 + r)
        nav.append(nav_ls)
    mdd_ls = max_drawdown(ls_daily)
    turn5 = sum(g5["turnovers"]) / max(1, len(g5["turnovers"]))
    turn1 = sum(g1["turnovers"]) / max(1, len(g1["turnovers"]))
    return {
        "months": months,
        "ls_monthly": ls_m,
        "g5_monthly": g5_m,
        "g1_monthly": g1_m,
        "bench_monthly": _bench_monthly(closes, dates, ls_dates),
        "ls_nav": nav,
        "ann_ls_net": _annualize(ls_daily),
        "ann_g5_net": _annualize(g5["net"][:n]),
        "nw_sharpe_ls": nw_sharpe(ls_daily),
        "sortino_ls": _sortino(ls_daily),
        "max_drawdown_ls": mdd_ls,
        "calmar_ls": (_annualize(ls_daily) / abs(mdd_ls)
                      if mdd_ls < 0 else None),
        "turnover_monthly_one_side": (turn5 + turn1) / 2,
        "fee_one_side": fee_one_side,
        "n_months": len(months),
        "yearly_ls": _yearly(months, ls_m),
    }


def pnl_metrics_table(p: dict[str, Any]) -> str:
    """指标条（Markdown 表；对齐聚宽回测报告的头部密度）."""
    def pct(v: Any) -> str:
        return "—" if v is None else f"{v * 100:+.2f}%"

    rows = [
        ("多空年化（费后）", pct(p["ann_ls_net"]),
         "G5−G1 对冲，两边各担成本"),
        ("G5 多头年化（费后）", pct(p["ann_g5_net"]), "高因子组等权"),
        ("NW Sharpe（多空）", f"{p['nw_sharpe_ls']:.2f}",
         "Newey-West 修正，日频年化"),
        ("最大回撤（多空）", pct(p["max_drawdown_ls"]), "日级净值口径"),
        ("Calmar", ("—" if p["calmar_ls"] is None
                    else f"{p['calmar_ls']:.2f}"), "年化 / |MDD|"),
        ("月均换手（单边）", f"{p['turnover_monthly_one_side'] * 100:.0f}%",
         "G5、G1 平均"),
        ("费率假设", f"{p['fee_one_side'] * 1e4:.0f} bps 单边",
         "成本摊 20 交易日；敏感性另跑"),
        ("样本", f"{p['n_months']} 月", "月度换仓"),
    ]
    lines = ["| 指标 | 值 | 口径 |", "|---|---|---|"]
    lines += [f"| {k} | {v} | {c} |" for k, v, c in rows]
    return "\n".join(lines)


def pnl_year_table(p: dict[str, Any]) -> str:
    """年度收益表（聚简式：年 | 多空净收益）."""
    if not p["yearly_ls"]:
        return "（无年度样本）"
    lines = ["| 年 | L-S 净收益 |", "|---|---|"]
    lines += [f"| {y} | {r * 100:+.2f}% |" for y, r in p["yearly_ls"]]
    return "\n".join(lines)
