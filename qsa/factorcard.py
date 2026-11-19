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


# -- SVG 原语（HTML 通道；零 JS，文件本体自足） ----------------------------

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def sparkline_svg(ic_series: list[dict[str, Any]], w: int = 150,
                  h: int = 26) -> str:
    """月度 IC 柱 + 累计折线的内嵌 sparkline（无 JS）."""
    ics = [x["ic"] for x in ic_series]
    if not ics:
        return "<svg></svg>"
    n = len(ics)
    bw = w / n
    m = max(abs(v) for v in ics) or 1e-9
    half = h / 2 - 2
    bars = []
    cum, cums, points = 0.0, [], []
    for i, v in enumerate(ics):
        cum += v
        cums.append(cum)
        bh = abs(v) / m * half
        y = (h / 2 - bh) if v >= 0 else h / 2
        color = "#2e9e5b" if v >= 0 else "#c94f4f"
        bars.append(f'<rect x="{i * bw:.1f}" y="{y:.1f}" '
                    f'width="{max(bw - 0.5, 0.5):.1f}" height="{bh:.1f}" '
                    f'fill="{color}" opacity="0.75"/>')
    lo, hi = min(cums), max(cums)
    pts = []
    for i, v in enumerate(cums):
        t = 0.5 if hi <= lo else (v - lo) / (hi - lo)
        pts.append(f"{i * bw + bw / 2:.1f},{2 + (1 - t) * (h - 4):.1f}")
    poly = (f'<polyline points="{" ".join(pts)}" fill="none" '
            'stroke="#3a6ea5" stroke-width="1.2" opacity="0.9"/>')
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="monthly IC">{"".join(bars)}{poly}'
            '<line x1="0" y1="' + str(h / 2) + f'" x2="{w}" y2="{h / 2}" '
            'stroke="#999" stroke-width="0.5" stroke-dasharray="2,2"/></svg>')


def render_index_html(rows: list[dict[str, Any]], meta: dict[str, Any],
                      ics: dict[str, list[dict[str, Any]]]) -> str:
    """总览页 HTML（与 INDEX.md 同数据同口径；无 JS、内嵌 SVG）."""
    n, n_both = len(rows), sum(1 for r in rows if r.get("both"))
    fams: dict[str, dict[str, Any]] = {}
    for r in rows:
        f = r.get("family", "?")
        b = fams.setdefault(f, {"best": None, "n": 0})
        b["n"] += 1
        if b["best"] is None or (r["oos_ic"] or -9) > (b["best"]["oos_ic"] or -9):
            b["best"] = r
    css = ("body{font:14px/1.5 -apple-system,'Segoe UI',Roboto,"
           "'PingFang SC','Microsoft YaHei',sans-serif;margin:0;"
           "background:#f7f8fa;color:#24292f}"
           "main{max-width:1060px;margin:0 auto;padding:24px}"
           "h1{font-size:22px;margin:0 0 4px}.meta{color:#57606a;font-size:13px}"
           ".cards{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0}"
           ".surv{background:#fff;border:1px solid #d8dee4;border-radius:10px;"
           "padding:14px 18px;min-width:280px;flex:1}"
           ".surv b{font-size:17px}.big{font-size:30px;font-weight:700;"
           "color:#1a7f37;margin:6px 0 2px}"
           ".sub{color:#57606a;font-size:12.5px}"
           "table{border-collapse:collapse;width:100%;background:#fff;"
           "font-size:13px}th,td{padding:5px 9px;border-bottom:1px solid #eaeef2;"
           "text-align:left}th{background:#f0f2f5;position:sticky;top:0}"
           ".ok{color:#1a7f37;font-weight:700}.no{color:#cf222e}"
           ".na{color:#8c959f}code{background:#eff1f3;border-radius:4px;"
           "padding:1px 5px;font-size:12px}"
           ".foot{color:#57606a;font-size:12.5px;margin-top:18px;"
           "border-top:1px solid #d8dee4;padding-top:10px}"
           ".famrow{display:flex;align-items:center;gap:8px;margin:4px 0}"
           ".fambar{height:14px;border-radius:3px;background:#2e9e5b}"
           ".fambar.neg{background:#c94f4f}")
    surv = "".join(
        f'<div class="surv"><b>{_esc(r["id"])}</b>'
        f'<div class="big">{r["oos_ic"]:+.4f}</div>'
        f'<div class="sub">OOS IC　·　ICIR(年化) {r["icir_a"]:.2f}　·　'
        f'多空 {r["tmb"]:+.2f}　·　正IC月 {r.get("pos_share", 0):.0%}</div>'
        + (sparkline_svg(ics[r["id"]])
           if r["id"] in ics else "")
        + '</div>'
        for r in sorted([x for x in rows if x.get("both")],
                        key=lambda x: -(x["oos_ic"] or 0)))
    if not surv:
        surv = '<div class="sub">无（诚实零也是结果）</div>'
    fam_rows = []
    span = sorted(fams.items(), key=lambda kv: -(kv[1]["best"]["oos_ic"] or -9))
    hi = max(abs(kv[1]["best"]["oos_ic"] or 0) for kv in span) or 1e-9
    for fam, b in span:
        v = b["best"]["oos_ic"] or 0
        pct = int(abs(v) / hi * 100)
        cls = "fambar" if v >= 0 else "fambar neg"
        fam_rows.append(
            f'<div class="famrow"><code>{_esc(fam)}</code>'
            f'<div class="{cls}" style="width:{max(pct, 2)}%"></div>'
            f'<span>{v:+.4f}</span>'
            f'<span class="sub">({b["best"]["id"]}, {b["n"]} 变体)</span></div>')
    mark = {"pass": '<span class="ok">✓</span>',
            "fail": '<span class="no">✗</span>',
            "inconclusive": '<span class="na">?</span>',
            None: '<span class="na">—</span>'}
    trs = []
    for r in sorted(rows, key=lambda x: -(x["oos_ic"] or -9)):
        spark = sparkline_svg(ics[r["id"]]) if r["id"] in ics else ""
        bold = " font-weight:700" if r.get("both") else ""
        trs.append(
            f'<tr><td style="color:#24292f{bold}">{_esc(r["id"])}</td>'
            f'<td><code>{_esc(r.get("family", "?"))}</code></td>'
            f'<td>{r["oos_ic"]:+.4f}</td><td>{r["icir_a"]:.2f}</td>'
            f'<td>{mark.get(r.get("s2"))}</td><td>{mark.get(r.get("s2v2"))}</td>'
            f'<td>{mark.get(r.get("wf"))}</td><td>{spark}</td></tr>')
    dup = f"　·　{_esc(meta['dedup_note'])}" if meta.get("dedup_note") else ""
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(meta.get('title', '测试总览'))} · quant-super-agent</title>
<style>{css}</style></head><body><main>
<h1>{_esc(meta.get('title', '测试总览'))}</h1>
<div class="meta">{_esc(meta.get('snap', ''))}　·　样本 {_esc(str(meta.get('n_months', '')))} 月 × {meta.get('n_tickers', '')} 标的　·　判决门=冻结 stage2 + walk-forward（stage2-v2 年化口径待拍板）　·　共 {n} 项，诊断双过 {n_both} 项{dup}</div>
<h2 style="font-size:16px;margin-top:22px">幸存者（诊断双过，待拍板）</h2>
<div class="cards">{surv}</div>
<h2 style="font-size:16px;margin-top:22px">族级对比（各族最强变体，按 OOS IC）</h2>
{''.join(fam_rows)}
<h2 style="font-size:16px;margin-top:22px">全部测试项</h2>
<table><tr><th>因子</th><th>族</th><th>OOS IC</th><th>ICIR(年化)</th>
<th>stage2</th><th>s2-v2</th><th>walk-fwd</th><th>月度IC（柱=月度，线=累计）</th></tr>
{''.join(trs)}</table>
<div class="foot">stage2 列为冻结门（月度 icir&gt;1.0）判决；s2-v2 列为拟议年化口径（待拍板，未入册）；both=✓✓ 不构成对外主张，正式结论唯一路径是冻结 run。指标与门禁/单卡同源同口径。本页零 JS、纯静态（SVG 内嵌），文件本体自足。</div>
</main></body></html>
"""


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
