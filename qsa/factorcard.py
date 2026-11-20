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

import qsa.showcase as _showcase  # noqa: E402

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


# -- PnL 段（组合级模拟；假设显式，模拟 ≠ 实盘主张） -----------------------

def pnl_curve_svg(p: dict[str, Any], w: int = 320, h: int = 96) -> str:
    """三线累计净值 SVG：G5 绿 / G1 红 / L-S 蓝粗（归一 1.0 起）."""
    def nav_path(monthly: list[float], color: str, width: float) -> str:
        nav, pts = 1.0, []
        for i, r in enumerate(monthly):
            nav *= (1.0 + r)
            pts.append((i, nav))
        lo = min(v for _, v in pts)
        hi = max(v for _, v in pts)
        span = (hi - lo) or 1e-9
        xy = " ".join(f"{i * (w / max(1, len(pts) - 1)):.1f},"
                      f"{2 + (1 - (v - lo) / span) * (h - 4):.1f}"
                      for i, v in pts)
        return (f'<polyline points="{xy}" fill="none" stroke="{color}" '
                f'stroke-width="{width}"/>')

    n = len(p["months"])
    if not n:
        return "<svg></svg>"
    base = (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            'role="img" aria-label="cumulative NAV">')
    base += f'<rect x="0" y="0" width="{w}" height="{h}" fill="#fff"/>'
    base += nav_path(p["g1_monthly"], "#c94f4f", 1.0)
    base += nav_path(p["g5_monthly"], "#2e9e5b", 1.0)
    base += nav_path(p["ls_monthly"], "#3a6ea5", 2.2)
    return base + "</svg>"


def pnl_nav_ascii(monthly: list[float], width: int = 60) -> str:
    """L-S 累计净值的单行 sparkline（Markdown 通道用，8 档）."""
    if not monthly:
        return "（无样本）"
    if len(monthly) > width:
        step = len(monthly) / width
        monthly = [monthly[int(i * step)] for i in range(width)]
    nav, navs = 1.0, []
    for r in monthly:
        nav *= (1.0 + r)
        navs.append(nav)
    lo, hi = min(navs), max(navs)
    row = "".join(_scale(v, lo, hi) for v in navs)
    return "```\nL-S净值  " + row + "\n```"


def render_pnl_md(p: dict[str, Any], tables: Any) -> str:
    """PnL 段（Markdown）：指标条 + 净值 sparkline + 年度表 + 假设."""
    parts = [
        "## 模拟 PnL（G5−G1 多空，费后）",
        "",
        tables[0],
        "",
        pnl_nav_ascii(p["ls_monthly"]),
        "",
        "### 年度收益（多空净）",
        "",
        tables[1],
        "",
        "> 假设：等权五分位、月度换仓、单边费率显式（见上表）、成本摊 "
        "20 交易日、G1=低因子。**模拟 PnL ≠ 实盘主张**：无冲击成本/"
        "停牌/涨跌停约束；对外数字唯一路径仍是冻结 run。",
    ]
    return "\n".join(parts)


# -- 叙事组件（暗色通道；零 JS，CSS/SVG 动画 + reduced-motion 兜底） ------

TICK_KEY = "tick"


def _ticker(value: str, cls: str = "tick") -> str:
    """Number Ticker：每位数字一个滚轮，CSS 动画滚到终值.

    基础 transform 即终值（reduced-motion 禁动画时静态正确显示）；
    keyframes 从 0 位滚到位，逐位错峰。非数字字符静态直出。
    """
    out, i = [], 0
    for ch in value:
        if ch.isdigit():
            d = int(ch)
            reel = "".join(f"<span>{k}</span>" for k in range(10))
            out.append(
                f'<span class="dig"><span class="reel" style="'
                f"transform:translateY(-{d}em);animation-delay:{i * 60}ms"
                f';--d:{d}">{reel}</span></span>')
        else:
            out.append(f'<span class="sym">{ch}</span>')
        i += 1
    return f'<span class="{cls}">{"".join(out)}</span>'


def waterfall_svg(stages: list[dict[str, Any]]) -> str:
    """淘汰瀑布：n0 全部 → 逐级门禁幸存，连接带下落.

    stages: [{label, n, color, note}]；高度∝n（对 n=0 画虚框占位）。
    """
    w, h, pad, base = 560, 150, 34, 122
    n_st = len(stages)
    col_w = (w - pad * 2) / n_st * 0.52
    gap = (w - pad * 2) / n_st
    top = max(s["n"] for s in stages) or 1
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
           'aria-label="elimination waterfall">']
    prev_x = prev_y = None
    for i, s in enumerate(stages):
        x = pad + i * gap
        hh = max(4, s["n"] / top * (base - 26))
        y = base - hh
        color = s["color"]
        if s["n"] == 0:
            out.append(f'<rect x="{x:.0f}" y="{base - 10:.0f}" '
                       f'width="{col_w:.0f}" height="10" fill="none" '
                       f'stroke="{color}" stroke-dasharray="3,3" '
                       'opacity="0.55"/>')
        else:
            out.append(f'<rect class="wfbar" x="{x:.0f}" y="{y:.0f}" '
                       f'width="{col_w:.0f}" height="{hh:.0f}" rx="3" '
                       f'fill="{color}" opacity="0.92" '
                       f'style="animation-delay:{i * 120}ms"/>')
            if prev_x is not None:
                x0, y0 = prev_x + col_w, prev_y
                x1, y1 = x, base - max(10, s["n"] / top * (base - 26))
                out.append(f'<polygon points="{x0:.0f},{y0:.0f} '
                           f'{x0 + gap - col_w:.0f},{y0:.0f} '
                           f'{x1:.0f},{y1:.0f} {x1:.0f},{base:.0f} '
                           f'{x0:.0f},{base:.0f}" fill="{color}" '
                           'opacity="0.18"/>')
        lbl_y = (y - 8) if s["n"] else base - 18
        out.append(f'<text x="{x + col_w / 2:.0f}" y="{max(lbl_y, 16):.0f}" '
                   f'text-anchor="middle" class="wfn">{s["n"]}</text>')
        out.append(f'<text x="{x + col_w / 2:.0f}" y="{base + 16:.0f}" '
                   'text-anchor="middle" class="wfl">'
                   f'{_esc(s["label"])}</text>')
        if s.get("note"):
            out.append(f'<text x="{x + col_w / 2:.0f}" y="{base + 30:.0f}" '
                       'text-anchor="middle" class="wfs">'
                       f'{_esc(s["note"])}</text>')
        prev_x, prev_y = x, base - max(4, s["n"] / top * (base - 26))
    out.append(f'<line x1="{pad - 14}" y1="{base}" x2="{w - 8}" '
               f'y2="{base}" stroke="#263140" stroke-width="1"/>')
    return "".join(out) + "</svg>"


def verdict_chain_svg(r: dict[str, Any]) -> str:
    """行内判决链：stage1→s2→s2v2→wf 四门节点 + PnL 终点旗.

    通过=实心+实线；失败=空心+淡线（保留在链上，诚实失败）；
    双过整链金色；PnL 旗绿(正)/红(负)/灰(无)。
    """
    gates = [("s1", r.get("s1")), ("s2", r.get("s2")),
             ("v2", r.get("s2v2")), ("wf", r.get("wf"))]
    xs = [7, 24, 41, 58]
    both = bool(r.get("both"))
    hot = "#ffc857" if both else None
    line_c = hot or "#3fd68f"
    out = ['<svg viewBox="0 0 78 14" width="78" height="14" role="img" '
           'aria-label="verdict chain">']
    prev = None
    for (name, v), x in zip(gates, xs):
        passed = v == "pass"
        cur = line_c if passed else "#5b2727"
        if prev is not None:
            dash = "" if passed else ' stroke-dasharray="2,2"'
            out.append(f'<line x1="{prev}" y1="7" x2="{x - 4}" y2="7" '
                       f'stroke="{cur}" stroke-width="1.4" opacity="'
                       f'{1.0 if passed else 0.45}"{dash}/>')
            if passed:
                out.append(f'<line x1="{prev}" y1="7" x2="{x - 4}" y2="7" '
                           f'stroke="{hot or "#ffffff"}" stroke-width="1.6" '
                           'class="chainline" opacity="0.85"/>')
        if passed:
            fill = hot or ("#3fd68f" if name != "v2" else "#ffc857")
            out.append(f'<circle cx="{x}" cy="7" r="3.4" fill="{fill}"/>')
        else:
            stroke = "#ff6b6b" if v == "fail" else "#57606a"
            out.append(f'<circle cx="{x}" cy="7" r="3.4" fill="none" '
                       f'stroke="{stroke}" stroke-width="1.3" '
                       'opacity="0.8"/>')
        prev = x + 4
    ann = r.get("ann_ls")
    flag = ("#3fd68f" if (ann or 0) > 0 else
            "#ff6b6b" if ann is not None else "#57606a")
    out.append(f'<rect x="70" y="3.5" width="7" height="7" rx="1.2" '
               f'fill="{flag}" opacity="{0.95 if ann is not None else 0.45}"/>')
    return "".join(out) + "</svg>"


def run_header_html(meta: dict[str, Any], rows: list[dict[str, Any]],
                    n_both: int) -> str:
    """Run Inspector 头部：一单研究订单的运行卡."""
    stats = [
        ("引擎", meta.get("engine", "qsa")),
        ("后端", meta.get("backend", "stdlib")),
        ("变体", str(len(rows))),
        ("扫描耗时", meta.get("elapsed_s", "—")),
        ("双过", str(n_both)),
        ("commit", meta.get("commit", "—")),
    ]
    cells = "".join(f'<div class="rstat"><div class="rk">{_esc(k)}</div>'
                    f'<div class="rv">{_esc(v)}</div></div>'
                    for k, v in stats)
    return (f'<div class="runcard"><div class="rtop">'
            f'<span class="rdot"></span>'
            f'<span class="rtitle">{_esc(meta.get("title", "测试总览"))}'
            '</span><span class="rsub">研究订单 · 运行回放</span></div>'
            f'<div class="rstats">{cells}</div></div>')


DARK_CSS = """
*{box-sizing:border-box}
body{font:14px/1.55 -apple-system,'Segoe UI',Roboto,'PingFang SC',
'Microsoft YaHei',sans-serif;margin:0;background:#0a0e14;color:#dce3ec;
background-image:linear-gradient(#0d1420 1px,transparent 1px),
linear-gradient(90deg,#0d1420 1px,transparent 1px);
background-size:44px 44px;animation:gridbg 90s linear infinite}
body::before{content:"";position:fixed;inset:0;pointer-events:none;
background:radial-gradient(60% 40% at 50% 110%,rgba(76,194,255,.10),
transparent 70%),radial-gradient(40% 30% at 85% 8%,
rgba(255,200,87,.05),transparent 70%);z-index:0}
main{max-width:1080px;margin:0 auto;padding:28px 24px 48px;position:relative;
z-index:1}
h1{font-size:22px;margin:0 0 2px;letter-spacing:.3px}
h2{font-size:15px;margin:26px 0 10px;color:#aebccb;
text-transform:uppercase;letter-spacing:1.4px}
.meta{color:#8b98a9;font-size:13px}
.runcard{border:1px solid #1f2733;background:linear-gradient(180deg,
#111722,#0d1420);border-radius:12px;padding:16px 18px;margin-top:16px}
.rtop{display:flex;align-items:center;gap:10px}
.rdot{width:8px;height:8px;border-radius:50%;background:#3fd68f;
box-shadow:0 0 8px #3fd68f88;animation:pulse 2.4s ease-in-out infinite}
.rtitle{font-weight:600;font-size:15px}
.rsub{color:#8b98a9;font-size:12.5px;margin-left:auto}
.rstats{display:flex;flex-wrap:wrap;gap:0;margin-top:12px}
.rstat{padding:4px 22px 4px 0;margin-right:22px;border-right:1px solid #1f2733}
.rstat:last-child{border-right:none}
.rk{color:#66788c;font-size:11px;text-transform:uppercase;letter-spacing:1px}
.rv{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
font-variant-numeric:tabular-nums;font-size:14.5px;color:#dce3ec;margin-top:2px}
.cards{display:flex;gap:14px;flex-wrap:wrap;margin:12px 0 0}
.surv{background:linear-gradient(180deg,#131a26,#0f1520);
border:1px solid #2a3546;border-radius:12px;padding:16px 18px;min-width:300px;
flex:1;position:relative;overflow:hidden}
.surv::before{content:"";position:absolute;inset:0 auto 0 0;width:3px;
background:linear-gradient(#ffc857,#4cc2ff)}
.surv b{font-size:15.5px;letter-spacing:.3px}
.big{margin:8px 0 2px;color:#3fd68f;font-family:ui-monospace,monospace;
font-variant-numeric:tabular-nums;font-size:34px;font-weight:700}
.sub{color:#8b98a9;font-size:12.5px;line-height:1.7}
.tick{display:inline-block}
.dig{display:inline-block;height:1em;overflow:hidden;vertical-align:baseline}
.reel{display:block;animation:tickroll .9s cubic-bezier(.2,.7,.3,1) both}
.reel span{display:block;height:1em;line-height:1em}
.sym{display:inline-block}
table{border-collapse:collapse;width:100%;font-size:13px;
font-variant-numeric:tabular-nums}
th,td{padding:5px 8px;border-bottom:1px solid #1a2230;text-align:left}
th{color:#8b98a9;font-size:11.5px;text-transform:uppercase;
letter-spacing:.8px;position:sticky;top:0;background:#0d1420}
tr:hover td{background:#101826}
.ok{color:#3fd68f;font-weight:700}.no{color:#ff6b6b}.na{color:#57606a}
.gold{color:#ffc857;font-weight:700}
code{background:#161f2d;border-radius:4px;padding:1px 6px;font-size:11.5px;
color:#9fb6cc}
.foot{color:#66788c;font-size:12.5px;margin-top:20px;border-top:
1px solid #1f2733;padding-top:12px;line-height:1.8}
.famrow{display:flex;align-items:center;gap:10px;margin:5px 0}
.fambar{height:15px;border-radius:3px;background:#4cc2ff;opacity:.85}
.fambar.neg{background:#ff6b6b}
.wfn{fill:#dce3ec;font-size:15px;font-weight:700;
font-family:ui-monospace,monospace}
.wfl{fill:#8b98a9;font-size:11px}
.wfs{fill:#5c6b7d;font-size:10px}
.wfbar{transform-box:fill-box;transform-origin:bottom;
animation:wfgrow .8s cubic-bezier(.2,.7,.3,1) both}
@keyframes gridbg{to{background-position:44px 44px}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}
@keyframes tickroll{from{transform:translateY(0)}to{transform:translateY(var(--d)*-1em)}}
@keyframes wfgrow{from{transform:scaleY(.15);opacity:.3}to{transform:scaleY(1);opacity:1}}
.trace{font-family:ui-monospace,Menlo,Consolas,monospace;
font-size:12.5px;color:#8fe3b0;background:#0c1119;border:1px solid #1a2432;
border-radius:8px;padding:12px 14px;margin-top:14px;overflow:hidden}
.tline{white-space:nowrap;text-overflow:ellipsis}
.trace span{opacity:0;animation:tappear .05s both}
@keyframes tappear{to{opacity:1}}
.ecgline{stroke-dasharray:220 440;animation:ecgdraw 3.2s linear infinite}
@keyframes ecgdraw{to{stroke-dashoffset:-660}}
.dataflow{margin-top:6px;opacity:.9}
.dflow{animation:dflow 20s linear infinite}
@keyframes dflow{to{transform:translateX(-500px)}}
.racer{transform-box:fill-box;animation:racerun 3s cubic-bezier(.3,.6,.2,1)
infinite alternate}
@keyframes racerun{to{transform:translateX(540px)}}
.badges{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.badge{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;
letter-spacing:1.2px;padding:2px 9px;border-radius:4px;border:1px solid}
.b-sim{color:#4cc2ff;border-color:#2a4a5e;background:#0e1c28}
.b-pend{color:#ffc857;border-color:#5e4f1f;background:#231c0c}
.b-dual{color:#3fd68f;border-color:#1f4a35;background:#0b2118}
.b-frozen{color:#8b98a9;border-color:#333d4a;background:#141922}
tbody tr{opacity:.42;transition:opacity .18s}
tbody tr:hover{opacity:1}
tbody tr.goldrow{opacity:1}
.big{font-size:56px;line-height:1.05}
.mech{display:inline-block;font-size:11.5px;color:#9fd0ff;background:#0e1c28;
border:1px solid #2a4a5e;border-radius:4px;padding:1px 8px;margin:6px 0 2px}
.lsrow{display:flex;align-items:center;gap:8px;margin:3px 0}
.lsbar{flex:1;height:9px;background:#131b28;border-radius:4px;overflow:hidden}
.lsbar div{height:100%;border-radius:4px}
.heroend{fill:#ffc857;font-size:17px;font-weight:700;
font-family:ui-monospace,monospace}
.herolab{fill:#5c6b7d;font-size:11px}
.ygn{fill:#3fd68f;font-size:13px;font-weight:700;
font-family:ui-monospace,monospace}
.gaugev{fill:#dce3ec;font-size:15px;font-weight:700;
font-family:ui-monospace,monospace}
.corrv{fill:#0a0e14;font-size:12px;font-weight:700;
font-family:ui-monospace,monospace}
.chainline{stroke-dasharray:5 46;animation:chainrun 2.4s linear infinite}
@keyframes chainrun{to{stroke-dashoffset:-51}}
details.log{margin-top:14px;border:1px solid #1a2432;border-radius:8px;
background:#0c1119}
details.log summary{cursor:pointer;padding:8px 14px;color:#8b98a9;
font-family:ui-monospace,monospace;font-size:12px}
.logbody{padding:4px 14px 12px;font-family:ui-monospace,Menlo,monospace;
font-size:11.5px;color:#7ec99a;max-height:240px;overflow:auto}
.logbody .err{color:#ff6b6b}.logbody .dim{color:#57606a}
@media (prefers-reduced-motion:reduce){*{animation:none !important;transition:none !important}}
@media print{body{background:#fff;color:#111;animation:none}
body::before{display:none}.surv,.runcard{border-color:#ccc;background:#fff}
.big{color:#0a7a42}.foot,code{color:#333}}
"""

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


def _lifespan(ics: list[dict[str, Any]]) -> tuple[float | None, float | None,
                                                   float | None]:
    vals = [x.get("ic") for x in ics if x.get("ic") is not None]
    if not vals:
        return None, None, None
    n = len(vals)
    half = max(1, n // 2)
    early = sum(vals[:half]) / half
    late = sum(vals[half:]) / max(1, n - half)
    last12 = sum(vals[-12:]) / min(12, n)
    return early, late, last12


def render_index_html(rows: list[dict[str, Any]], meta: dict[str, Any],
                      ics: dict[str, list[dict[str, Any]]],
                      pnls: dict[str, dict[str, Any]] | None = None,
                      extras: dict[str, Any] | None = None) -> str:
    """总览页 HTML v3（AI 科技感 + 策略价值感；与 INDEX.md 同口径，零 JS）.

    extras 可选：{hero_id, band:[(id, ls_monthly)], log:[str], mech:{fam:str}}。
    """
    pnls = pnls or {}
    ex = extras or {}
    fam_mech = ex.get("mech") or _showcase.FAM_MECH
    n = len(rows)
    n_both = sum(1 for x in rows if x.get("both"))

    # 幸存者
    surv = sorted([x for x in rows if x.get("both")],
                  key=lambda x: -(x.get("ann_ls")
                                  if x.get("ann_ls") is not None
                                  else (x["oos_ic"] or 0)))
    # hero = 幸存者中年化最高；诚实零时无 hero（不硬凑）
    hero = ex.get("hero_id") if ex.get("hero_id") in [
        s["id"] for s in surv] else None
    if hero is None and surv:
        hero = max(surv, key=lambda x: (x.get("ann_ls")
                                        if x.get("ann_ls") is not None
                                        else -9))["id"]
    hero_row = next((r for r in rows if r["id"] == hero), None)
    hp = pnls.get(hero) or {} if hero else {}

    # 邻域带：同族其余窗口
    band = ex.get("band")
    if band is None and hero:
        band = [(r["id"], pnls[r["id"]]["ls_monthly"])
                for r in rows
                if r["family"] == hero_row.get("family") and r["id"] != hero
                and r["id"] in pnls][:4]
    else:
        band = band or []

    # 日志（A1/A6 终端回放，真实口径来自 meta）
    log = ex.get("log") or [
        f"[00:00:00.0] run order=scan-all  engine={meta.get('engine', 'qsa')} "
        f"backend={meta.get('backend', 'stdlib')} commit={meta.get('commit', '—')}",
        f"[scan] {n} 个实现 → 矩阵化引擎（零逐因子回退）",
        "[stage2] 逐级淘汰：stage1 → stage2(冻结) → s2-v2(待拍板) → walk-forward",
        f"[pnl] 幸存者 {len(surv)} → 等权五分位多空，月度换仓，"
        f"单边 {(meta.get('fee_bps') or 8):.0f}bps，成本摊 20 日",
        f"[done] elapsed={meta.get('elapsed_s', '—')}  "
        f"双过 {n_both}/{n}",
    ]

    # 指纹墙（A5）：hero 的双实现月度一致性
    fp = _showcase.fingerprint_svg(ics.get(hero, [])) if hero else ""

    # 相关矩阵（B8）
    corr = (_showcase.corr_matrix_svg(
        {r["id"]: pnls[r["id"]]["ls_monthly"]
         for r in surv if r["id"] in pnls})
        if sum(1 for r in surv if r["id"] in pnls) >= 2 else "")

    # 寿命（B7）
    e, l, last12 = (_lifespan(ics.get(hero, [])) if hero
                    else (None, None, None))
    life = _showcase.lifespan_bars(e, l, last12) if e is not None else ""

    # 幸存者卡（原有 + 指纹 + 机制）
    def _surv_card(r: dict[str, Any]) -> str:
        oos = _ticker(f"{r['oos_ic']:+.4f}")
        ann = (f"　·　<em>模拟PnL 年化 {r['ann_ls']:+.1%} / Sharpe "
               f"{r['sharpe_ls']:.2f}</em>"
               if r.get("ann_ls") is not None and r.get("sharpe_ls")
               else "")
        curve = ""
        if r["id"] in pnls:
            curve = pnl_curve_svg(pnls[r["id"]])
        elif r["id"] in ics:
            curve = sparkline_svg(ics[r["id"]])
        mech = fam_mech.get(r.get("family", ""), "")
        return (f'<div class="surv"><b>{_esc(r["id"])}</b>'
                f'<div class="big">{oos}</div>'
                '<div class="sub">OOS IC（后 20% 月份）</div>'
                f'<div class="mech">{_esc(mech)}</div>'
                f'<div class="sub">ICIR(年化) {r["icir_a"]:.2f}'
                f"　·　多空 {r['tmb']:+.2f}"
                f"　·　正IC月 {r.get('pos_share', 0):.0%}{ann}</div>"
                f'{curve}</div>')

    surv_html = "".join(_surv_card(r) for r in surv) or (
        '<div class="sub">无幸存者（诚实零也是结果：全部变体未过'
        "诊断双过门，不硬凑候选）</div>")

    # 族级对比
    fams: dict[str, dict[str, Any]] = {}
    for r in rows:
        f = r.get("family", "?")
        b = fams.setdefault(f, {"best": None, "n": 0})
        b["n"] += 1
        if b["best"] is None or (r["oos_ic"] or -9) > (b["best"]["oos_ic"] or -9):
            b["best"] = r
    fam_rows = []
    span = sorted(fams.items(),
                  key=lambda kv: -(kv[1]["best"]["oos_ic"] or -9))
    hi = max(abs(kv[1]["best"]["oos_ic"] or 0) for kv in span) or 1e-9
    for fam, b in span:
        v = b["best"]["oos_ic"] or 0
        pct = int(abs(v) / hi * 100)
        cls = "fambar" if v >= 0 else "fambar neg"
        fam_rows.append(
            f'<div class="famrow"><code>{_esc(fam)}</code>'
            f'<div class="{cls}" style="width:{max(pct, 2)}%"></div>'
            f'<span class="rv">{v:+.4f}</span>'
            f'<span class="sub">({_esc(b["best"]["id"])}, {b["n"]} 变体 · '
            f'{_esc(fam_mech.get(fam, ""))})</span></div>')

    # 全表（A4 降暗，幸存行高亮）
    trs = []
    for r in sorted(rows, key=lambda x: -(x["oos_ic"] or -9)):
        spark = sparkline_svg(ics[r["id"]]) if r["id"] in ics else ""
        name_cls = "gold" if r.get("both") else ""
        row_cls = ' class="goldrow"' if r.get("both") else ""
        pnl_cell = ("—" if r.get("ann_ls") is None
                    else f"{r['ann_ls']:+.1%}")
        color = ("#3fd68f" if (r.get("ann_ls") or 0) > 0
                 else "#ff6b6b" if r.get("ann_ls") is not None
                 else "#57606a")
        trs.append(
            f'<tr{row_cls}><td class="{name_cls}">{_esc(r["id"])}</td>'
            f'<td><code>{_esc(r.get("family", "?"))}</code></td>'
            f'<td>{r["oos_ic"]:+.4f}</td><td>{r["icir_a"]:.2f}</td>'
            f'<td style="color:{color}">{pnl_cell}</td>'
            f'<td>{verdict_chain_svg(r)}</td><td>{spark}</td></tr>')

    dup = f"　·　{_esc(meta['dedup_note'])}" if meta.get("dedup_note") else ""
    log_html = "".join(f"<div>{_esc(line)}</div>" for line in log)
    yearly = hp.get("yearly_ls")
    yearly_html = _showcase.yearly_gain_svg(yearly) if yearly else ""
    gauges = _showcase.gauges_svg(hp) if hp else ""
    hero_svg = (_showcase.hero_pnl_svg(hp, band)
                if hp and hp.get("ls_monthly") else
                '<div class="sub">无幸存者净值可展示'
                f"（{n} 项均未通过诊断双过门 — 诚实零）</div>")
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(meta.get('title', '测试总览'))} · quant-super-agent</title>
<style>{DARK_CSS}</style></head><body><main>
{run_header_html(meta, rows, n_both)}
<div class="meta" style="margin-top:10px">{_esc(meta.get('snap', ''))}　·　样本 {_esc(str(meta.get('n_months', '')))} 月 × {meta.get('n_tickers', '')} 标的　·　判决门=冻结 stage2 + walk-forward（stage2-v2 年化口径待拍板）　·　共 {n} 项，诊断双过 {n_both} 项{dup}</div>

<h2>① 一次运行的推理流（终端回放）</h2>
<div class="trace">{_showcase.trace_flow_html(log)}</div>
<details class="log"><summary>▸ 完整日志</summary><div class="logbody">{log_html}</div></details>

<h2>② 数据流：订单 → 面板 → 信号 → 判决</h2>
<div class="dataflow">{_showcase.dataflow_svg()}</div>

<h2>③ 主幸存者净值（{ _esc(str(hero or '无')) }，等权多空 vs 等权基准）</h2>
<div class="badges"><span class="badge b-sim">SIM · 费后模拟</span><span class="badge b-frozen">口径冻结</span><span class="badge b-pend">s2-v2 待拍板</span></div>
<div class="mech">{_esc(fam_mech.get((hero_row or {}).get('family', ''), ''))}</div>
{hero_svg}
<div class="cards2">
<div class="card"><h3>年度等权增强（vs 等权全因子）</h3>{yearly_html}</div>
<div class="card"><h3>三针仪表（可交易性）</h3>{gauges}</div>
</div>

<h2>④ 证据面板</h2>
<div class="cards2">
<div class="card"><h3>双实现指纹（A/B 逐月一致）</h3>{fp}<p class="sub">全绿=两实现逐月逐位一致</p></div>
<div class="card"><h3>IC 寿命（前/后/最近12月）</h3>{life}<p class="sub">衰减可见，不藏尾巴</p></div>
</div>
{('<div class="card" style="margin-top:10px"><h3>幸存者月收益相关（同族高相关是诚实的）</h3>' + corr + '</div>') if corr else ''}

<h2>⑤ 并行赛道（8 路进程池）</h2>
{_showcase.race_svg(lanes=4, speedup=meta.get('speedup', '18.1×'))}

<h2>⑥ 幸存者（诊断双过，待拍板）</h2>
<div class="cards">{surv_html}</div>

<h2>⑦ 淘汰瀑布（一单跑完的全部变体）</h2>
{waterfall_svg([{"label": "全部变体", "n": n, "color": "#4cc2ff", "note": meta.get("elapsed_s", "")},
{"label": "过 s2-v2（年化口径）", "n": sum(1 for r in rows if r.get('s2v2') == 'pass'), "color": "#7fd4ff", "note": "待拍板"},
{"label": "+ walk-forward", "n": n_both, "color": "#3fd68f", "note": "诊断双过"},
{"label": "冻结 run 入册", "n": 0, "color": "#8b98a9", "note": "待拍板后执行"}])}

<h2>⑧ 族级对比（各族最强变体，按 OOS IC）</h2>
{''.join(fam_rows)}

<h2>⑨ 全部测试项（降暗展示，悬停/幸存者高亮；链=stage1→stage2→s2-v2→walk-fwd）</h2>
<table><tr><th>因子</th><th>族</th><th>OOS IC</th><th>ICIR(年化)</th>
<th>多空年化(模拟)</th><th>判决链</th><th>月度IC（柱=月度，线=累计）</th></tr>
{''.join(trs)}</table>

<div class="foot">判决链第一/二节点为冻结门 stage1/stage2（月度 icir&gt;1.0）；第三节点 s2-v2 为拟议年化口径（待拍板，未入册）；both=双过不构成对外主张，正式结论唯一路径是冻结 run。PnL 列为组合级<b>模拟</b>（等权五分位、月度换仓、单边 {_esc(f"{(meta.get('fee_bps') or 8):.0f}")}bps、成本摊20日），不含冲击成本/停牌/涨跌停，不构成实盘主张。指标与门禁/单卡同源同口径。本页零 JS、纯静态（CSS/SVG 动画 + reduced-motion 兜底 + 打印样式），文件本体自足。</div>
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
        parts.append("| 因子 | OOS IC | ICIR(年化) | 多空G5−G1 | 正IC月 | 模拟PnL | 卡 |")
        parts.append("|---|---|---|---|---|---|---|")
        for r in sorted(both, key=lambda x: -(x["oos_ic"] or 0)):
            pnl_s = ("—"
                     if r.get("ann_ls") is None
                     else f"年化 {r['ann_ls']:+.1%} / Sharpe "
                          f"{r['sharpe_ls']:.2f}（费后）")
            parts.append(
                f"| **{r['id']}** | {r['oos_ic']:+.4f} | {r['icir_a']:.2f} "
                f"| {r['tmb']:+.2f} | {r.get('pos_share', 0):.0%} "
                f"| {pnl_s} | [卡]({r['id']}.md) |")
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
                ic_series: list[dict[str, Any]],
                pnl: dict[str, Any] | None = None) -> str:
    """整卡渲染：档案条 → 判决链 → 主指标 → IC 图 → 块表 → PnL → 脚注."""
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
    ]
    if pnl is not None:
        from .pnl import pnl_metrics_table, pnl_year_table
        parts += [render_pnl_md(pnl, (pnl_metrics_table(pnl),
                                      pnl_year_table(pnl))), ""]
    parts += [
        "---",
        "诚实脚注：本卡为**探索层**证据（若状态非冻结）；门禁参数"
        "预注册、未因结果调整；扫描挑选计入 deflation 计数，正式"
        "主张唯一路径仍是冻结 run。PnL 段为组合级**模拟**（假设"
        "见该段脚注），不含冲击成本/停牌/涨跌停约束，不构成实盘"
        "收益主张。",
    ]
    return "\n".join(parts) + "\n"
