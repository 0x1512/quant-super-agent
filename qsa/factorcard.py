"""Factor test card — 系统性测类表现展示（v1.5 展示层）.

对齐业界范式并按本仓纪律改造：

* WorldQuant BRAIN 的 alpha 摘要页（IS stats + submission verdict）
  → 判决链条 + 主指标表；
* alphalens tearsheet（IC 时序、分位收益）→ 月度 IC 图 + 五分位
  多空（G1/G5 年化与 TMB）；
* 聚宽/米筐回测报告（净值、回撤、年度表）→ walk-forward 块均值
  表（因子语境的"回撤"= 时间局部死亡检测）；
* PandaAI（问一句、看一图）→ 四行卡骨架保留，卡片自足可读。

纪律改造：展示预测力指标与门禁判决，不展示组合收益回测——
引擎不持有仓位假设，任何收益数字必须出自冻结 run。纯函数、
byte-stable、零依赖（stdlib only）。
"""
from __future__ import annotations

from typing import Any

BLOCK_CHARS = "▁▂▃▄▅▆▇█"          # 8 档高度（月度/累计 IC 共用）
POS_CHAR, NEG_CHAR = "+", "-"
BAR_CHAR = "#"


# -- 图形基元 ---------------------------------------------------------------

def _scale(v: float, lo: float, hi: float) -> str:
    """Map v in [lo, hi] onto the 8-step block alphabet (clamped)."""
    if hi <= lo:
        return BLOCK_CHARS[3]
    t = (v - lo) / (hi - lo)
    return BLOCK_CHARS[max(0, min(7, int(t * 8)))]


def ic_chart(ic_series: list[dict[str, Any]], width: int = 60) -> str:
    """月度 IC 双行图：上行每档月度 IC，下行累计 IC。

    每月一字符；series 长于 width 时按等距抽样（不缩不隐），
    短于 width 时原样输出。行尾无空格，byte-stable。
    """
    ics = [x["ic"] for x in ic_series]
    if not ics:
        return "（无 IC 样本）"
    if len(ics) > width:
        idx = [round(i * (len(ics) - 1) / (width - 1)) for i in range(width)]
        ics = [ics[i] for i in idx]
    m = max(abs(v) for v in ics) or 1e-9
    row_ic = "".join(BLOCK_CHARS[max(0, min(7, int((v / m + 1) * 4)))]
                     if v else POS_CHAR for v in ics)
    cum, cums = 0.0, []
    for v in ics:
        cum += v
        cums.append(cum)
    clo, chi = min(cums), max(cums)
    row_cum = "".join(_scale(v, clo, chi) for v in cums)
    first = ic_series[0]["date"][:6]
    last = ic_series[-1]["date"][:6]
    pad = max(0, len(ics) - 6)
    return "\n".join([
        "```",
        f"月度IC   {row_ic}",
        f"累计IC   {row_cum}",
        f"         {first}{' ' * pad}{last}  （高度∝|IC|，8档）",
        "```",
    ])


def block_table(wf_detail: dict[str, Any], series: list[dict[str, Any]],
                block_months: int = 6) -> str:
    """Walk-forward 块均值条形表：每半年一块，正块 # 上、负块 # 下.

    detail 由 walkforward_verdict 产出（block_means 已含）；series
    用于取每块的日期区间。负值行前缀 `-`，与判决理由同读。
    """
    means = wf_detail.get("block_means") or []
    if not means:
        return "（块数不足以判读 walk-forward）"
    scale = max(abs(b) for b in means) or 1e-9
    lines = ["| 块 | 区间 | 块均IC | 图 |", "|---|---|---|---|"]
    for i, b in enumerate(means):
        chunk = series[i * block_months:(i + 1) * block_months]
        rng = (f"{chunk[0]['date'][:6]}..{chunk[-1]['date'][:6]}"
               if chunk else "?")
        n = max(1, round(abs(b) / scale * 18))
        bar = (BAR_CHAR * n) if b >= 0 else ("-" * n)
        lines.append(f"| {i + 1} | {rng} | {b:+.4f} | `{bar}` |")
    return "\n".join(lines)


# -- 卡片段落 ---------------------------------------------------------------

def verdict_strip(verdicts: dict[str, Any]) -> str:
    """判决链条：stage1 / stage2 / walk-forward / 状态与计数脚注."""
    mark = {"pass": "✓", "fail": "✗", "inconclusive": "?",
            None: "—"}
    parts = []
    for name in ("stage1", "stage2", "walk_forward"):
        v = verdicts.get(name)
        parts.append(f"{name} {mark.get(v, '?')}")
    status = verdicts.get("status", "探索层（未冻结，不入册）")
    line = " → ".join(parts)
    extra = verdicts.get("note", "")
    out = f"**判决链**：{line}　|　状态：{status}"
    if extra:
        out += f"　|　{extra}"
    return out


def metric_table(row: dict[str, Any]) -> str:
    """主指标表（对齐 BRAIN IS Summary 的信息密度，一行一口径）."""
    def f(v: Any, nd: int = 4) -> str:
        return "—" if v is None else f"{v:+.{nd}f}"

    icir_a = (row.get("icir") * (12 ** 0.5)
              if row.get("icir") is not None else None)
    g1, g5 = row.get("g1_ann"), row.get("g5_ann")
    rows = [
        ("OOS IC", f(row.get("oos_ic")),
         "后 20% 月份的月度 rank-IC 均值（预注册分割）"),
        ("IC 均值（全程）", f(row.get("ic_mean")),
         "全样本月度 rank-IC；A/B 双实现逐月一致（1e-12）"),
        ("ICIR（年化）", f(icir_a, 2),
         "月度 ICIR × √12；>1 视为强（诊断口径 0.29 月度）"),
        ("多空 G5−G1（年化）", f((g5 - g1) if g1 is not None and g5 is not None else None, 2),
         "五分位组合 G5 减 G1 的年化差（分层单调性代理）"),
        ("G1 / G5（年化）", f"{f(g1, 2)} / {f(g5, 2)}",
         "五分位两端各自年化（读单调方向）"),
        ("正 IC 月占比", f"{row.get('ic_positive_share', 0):.0%}"
         if row.get("ic_positive_share") is not None else "—",
         "IC > 0 的月份份额（时间一致性第一层）"),
        ("样本", f"{row.get('n_months', '—')} 月",
         "月度面板（fixture 快照，A 股 Top300 主表）"),
    ]
    lines = ["| 指标 | 值 | 口径 |", "|---|---|---|"]
    lines += [f"| {k} | {v} | {c} |" for k, v, c in rows]
    return "\n".join(lines)


def render_index(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    """测试总览页（per-factor 卡之上的组合视图）.

    三区：幸存者（诊断双过）→ 族级对比条形 → 全表。rows 需含
    id / family / oos_ic / icir_a / tmb / s2 / s2v2 / wf / both。
    排序与格式固定，byte-stable。
    """
    n = len(rows)
    n_both = sum(1 for r in rows if r.get("both"))
    fams: dict[str, dict[str, Any]] = {}
    for r in rows:
        f = r.get("family", "?")
        b = fams.setdefault(f, {"best": None, "n": 0})
        b["n"] += 1
        if b["best"] is None or (r["oos_ic"] or -9) > (b["best"]["oos_ic"] or -9):
            b["best"] = r

    parts = [
        f"# 测试总览 · {meta.get('title', '现有全部因子效果')}",
        "",
        f"> 快照 {meta.get('snap')}　·　样本 {meta.get('n_months')} 月 × "
        f"{meta.get('n_tickers')} 标的　·　判决门=冻结 stage2 + "
        "walk-forward（stage2-v2 年化口径待拍板）"
        f"　·　共 {n} 项，诊断双过 {n_both} 项"
        + (f"　·　{meta['dedup_note']}" if meta.get("dedup_note") else ""),
        "",
    ]
    # -- 幸存者区
    parts += ["## 幸存者（stage2-v2 诊断 + walk-forward 双过，待拍板）", ""]
    both = [r for r in rows if r.get("both")]
    if both:
        parts.append("| 因子 | OOS IC | ICIR(年化) | 多空G5−G1 | 正IC月 | 卡 |")
        parts.append("|---|---|---|---|---|---|")
        for r in sorted(both, key=lambda x: -(x["oos_ic"] or 0)):
            parts.append(
                f"| **{r['id']}** | {r['oos_ic']:+.4f} | {r['icir_a']:.2f} "
                f"| {r['tmb']:+.2f} | {r.get('pos_share', 0):.0%} "
                f"| [卡]({r['id']}.md) |")
    else:
        parts.append("- 无（诚实零也是结果）")
    parts.append("")
    # -- 族级对比
    parts += ["## 族级对比（各族最强变体，按 OOS IC）", "", "```"]
    order = sorted(fams.items(),
                   key=lambda kv: -(kv[1]["best"]["oos_ic"] or -9))
    lo = min((kv[1]["best"]["oos_ic"] or 0) for kv in order) or -1e-9
    hi = max((kv[1]["best"]["oos_ic"] or 0) for kv in order) or 1e-9
    for fam, b in order:
        v = b["best"]["oos_ic"] or 0
        bar = _scale(v, lo, hi) * 2 if v >= 0 else "▁" * 2
        parts.append(f"{fam:12} {bar}  {v:+.4f}  ({b['best']['id']}, "
                     f"{b['n']} 变体)")
    parts += ["```", ""]
    # -- 全表
    parts += ["## 全部测试项", "",
              "| 因子 | 族 | OOS IC | ICIR(年化) | stage2 | s2-v2 | walk-fwd |",
              "|---|---|---|---|---|---|---|"]
    mark = {"pass": "✓", "fail": "✗", "inconclusive": "?", None: "—"}
    for r in sorted(rows, key=lambda x: -(x["oos_ic"] or -9)):
        parts.append(
            f"| {r['id']} | {r.get('family', '?')} | "
            f"{r['oos_ic']:+.4f} | {r['icir_a']:.2f} "
            f"| {mark.get(r.get('s2'), '—')} | {mark.get(r.get('s2v2'), '—')} "
            f"| {mark.get(r.get('wf'), '—')} |")
    parts += [
        "",
        "---",
        "诚实脚注：stage2 列为冻结门（月度 icir>1.0）判决；s2-v2 列为"
        "拟议年化口径（待拍板，未入册）；both=✓✓ 不构成对外主张，正式"
        "结论唯一路径是冻结 run。指标与单卡/门禁同源同口径"
        "（evaluate_factor_fast + walkforward_verdict）。",
    ]
    return "\n".join(parts) + "\n"


def render_card(meta: dict[str, Any], row: dict[str, Any],
                wf_detail: dict[str, Any],
                ic_series: list[dict[str, Any]]) -> str:
    """整卡渲染：档案条 → 判决链 → 主指标 → IC 图 → 块表 → 脚注."""
    parts = [
        f"# 测试卡 · {meta['id']}",
        "",
        f"> {meta.get('desc', '')}　·　来源：{meta.get('source', '?')}"
        + (f"　·　扫描族 {meta['scan_n']} 试（多重检验计数见脚注）"
           if meta.get("scan_n") else ""),
        "",
        verdict_strip(meta.get("verdicts", {})),
        "",
        "## 主指标",
        "",
        metric_table(row),
        "",
        "## 月度 IC（时序）",
        "",
        ic_chart(ic_series),
        "",
        "## Walk-forward 块（时间局部死亡检测）",
        "",
        block_table(wf_detail, ic_series),
        "",
        f"- 判读：{wf_detail.get('reason', '—')}",
        f"- 衰减触发：{wf_detail.get('n_decay_triggers', '—')} 次"
        "（滚动 12 月均 IC < 0）"
        f"；半衰比 {wf_detail.get('half_life_ratio', '—')}"
        f"；正块 {wf_detail.get('positive_blocks', '—')}",
        "",
        "---",
        "诚实脚注：本卡为**探索层**证据（若状态非冻结）；门禁参数"
        "预注册、未因结果调整；扫描挑选计入 deflation 计数，正式"
        "主张唯一路径仍是冻结 run。不展示组合收益回测——引擎不"
        "持有仓位假设，任何收益数字必须出自冻结 run。",
    ]
    return "\n".join(parts) + "\n"
