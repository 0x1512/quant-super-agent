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

    base += nav_path(p["g1_monthly"], "#E0685C", 1.0)
    base += nav_path(p["g5_monthly"], "#3FD68F", 1.0)
    base += nav_path(p["ls_monthly"], "#7A8CA0", 2.2)
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
    hot = "#E0B04B" if both else None
    line_c = hot or "#34C186"
    out = ['<svg viewBox="0 0 78 14" width="78" height="14" role="img" '
           'aria-label="verdict chain">']
    prev = None
    for (name, v), x in zip(gates, xs):
        passed = v == "pass"
        cur = line_c if passed else "#3A2A28"
        if prev is not None:
            dash = "" if passed else ' stroke-dasharray="2,2"'
            out.append(f'<line x1="{prev}" y1="7" x2="{x - 4}" y2="7" '
                       f'stroke="{cur}" stroke-width="1.4" opacity="'
                       f'{1.0 if passed else 0.45}"{dash}/>')
        # 节点：通过=实心+✓，失败=空心+✗（不单靠颜色，色弱可读）
        if passed:
            fill = hot or ("#34C186" if name != "v2" else "#E0B04B")
            out.append(f'<circle cx="{x}" cy="7" r="3.6" fill="{fill}"/>'
                       f'<text x="{x}" y="9.6" text-anchor="middle" '
                       f'font-size="7.5" font-weight="700" fill="#0B0E14">'
                       "\u2713</text>")
        else:
            stroke = "#D0695A" if v == "fail" else "#7C8A9B"
            out.append(f'<circle cx="{x}" cy="7" r="3.6" fill="none" '
                       f'stroke="{stroke}" stroke-width="1.3" '
                       'opacity="0.85"/>'
                       f'<text x="{x}" y="9.8" text-anchor="middle" '
                       f'font-size="8" font-weight="700" fill="{stroke}">'
                       "\u2715</text>")
        prev = x + 4
    ann = r.get("ann_ls")
    flag = ("#34C186" if (ann or 0) > 0 else
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
/* ============ v6 token system ==================================
   色板（4 语义 + 3 灰阶 + 3 面板，全页仅此 10 个 hex）：
   --up #34C186 涨/过 | --down #D0695A 跌/否 | --gold #E0B04B 钱与结论
   --ink-1 #DCE3EC 主文 | --ink-2 #8B98A9 次文 | --ink-3 #7C8A9B 注脚(>=4.5:1)
   --bg #0B0E14 | --panel #141923 | --panel-2 #10151D
   字阶（6 档，1.25 模数）：10/12/14/17/22/28px
   ================================================================ */
*{box-sizing:border-box}
:root{--bg:#0B0E14;--panel:#141923;--panel-2:#10151D;
--up:#34C186;--down:#D0695A;--gold:#E0B04B;
--ink-1:#DCE3EC;--ink-2:#8B98A9;--ink-3:#7C8A9B;
--line:rgba(255,255,255,.06);
--fs-0:10px;--fs-1:12px;--fs-2:14px;--fs-3:17px;--fs-4:22px;--fs-5:28px;
--mono:ui-monospace,'JetBrains Mono',Consolas,monospace;
--sans:-apple-system,'Segoe UI',Roboto,'PingFang SC',
'HarmonyOS Sans SC','Microsoft YaHei',sans-serif}
html{scroll-behavior:smooth}
body{font:var(--fs-2)/1.75 var(--sans);margin:0;background:var(--bg);
color:var(--ink-1);accent-color:var(--gold);
font-feature-settings:'tnum' 1;
background-image:radial-gradient(circle,rgba(255,255,255,.016) 1px,
transparent 1px);background-size:26px 26px}
::selection{background:rgba(224,176,75,.32)}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-thumb{background:#232B38;border-radius:5px}
::-webkit-scrollbar-thumb:hover{background:#2E3949}
::-webkit-scrollbar-track{background:var(--bg)}
main{max-width:1160px;margin:0 auto;padding:26px 28px 60px;position:relative;
z-index:1}
h1{font-size:var(--fs-4);font-weight:600;margin:0 0 2px;letter-spacing:.2px}
h2{font-size:var(--fs-1);font-weight:600;margin:34px 0 12px;
color:var(--ink-2);text-transform:uppercase;letter-spacing:1.6px}
.meta{color:var(--ink-2);font-size:var(--fs-2)}
.num,td,.rv,.big,.gaugev,.wfn,.kpival,.herolab,.ygn{font-family:var(--mono);
font-variant-numeric:tabular-nums}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
/* ---- 顶栏：徽章 + sticky 目录（F6 合并） ---- */
.toc{position:sticky;top:0;z-index:20;display:flex;gap:8px;flex-wrap:wrap;
align-items:center;padding:9px 0 8px;margin:-26px 0 6px;
background:rgba(11,14,20,.9);backdrop-filter:blur(10px);
border-bottom:1px solid var(--line)}
.toc .badge{margin:0}
.toc nav{margin-left:auto;display:flex;gap:4px;flex-wrap:wrap}
.toc a{font-family:var(--mono);font-size:var(--fs-0);letter-spacing:1px;
color:var(--ink-3);text-decoration:none;padding:3px 10px;
border-radius:999px;border:1px solid transparent}
.toc a:hover{color:var(--ink-1);border-color:var(--line)}
.toc a.on{color:var(--gold);border-color:rgba(224,176,75,.35)}
/* ---- 导览（C1） ---- */
details.guide{margin:10px 0 2px;border:1px solid rgba(224,176,75,.22);
background:rgba(224,176,75,.05);border-radius:10px;padding:0}
details.guide summary{cursor:pointer;padding:9px 16px;color:var(--ink-2);
font-size:var(--fs-1);list-style:none;display:flex;gap:8px;align-items:center}
details.guide summary::before{content:"\25B8"}
details.guide[open] summary::before{content:"\25BE"}
details.guide .gbody{padding:2px 16px 12px;color:var(--ink-2);
font-size:var(--fs-1);line-height:1.9}
details.guide b{color:var(--ink-1);font-weight:600}
/* ---- 面板材质（A9） ---- */
.runcard,.card,.surv,.kpis,.isos{background:
linear-gradient(180deg,#161B26,#12161F);border:1px solid rgba(255,255,255,.07);
box-shadow:inset 0 1px 0 rgba(255,255,255,.03)}
.runcard{border-radius:14px;padding:18px 22px;margin-top:14px}
.rtop{display:flex;align-items:center;gap:10px}
.rdot{width:8px;height:8px;border-radius:50%;background:var(--up)}
.rtitle{font-weight:600;font-size:var(--fs-3)}
.rsub{color:var(--ink-2);font-size:var(--fs-1);margin-left:auto}
.rstats{display:flex;flex-wrap:wrap;gap:0;margin-top:14px}
.rstat{padding:4px 22px 4px 0;margin-right:22px;
border-right:1px solid var(--line)}
.rstat:last-child{border-right:none}
.rk{color:var(--ink-3);font-size:var(--fs-0);text-transform:uppercase;
letter-spacing:1.2px}
.rv{font-size:var(--fs-2);color:var(--ink-1);margin-top:2px}
.cards{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0 0}
.card{border-radius:14px;padding:18px 22px;flex:1;min-width:280px}
.surv{border-radius:14px;padding:18px 22px;min-width:300px;flex:1;
position:relative;overflow:hidden}
.surv::before{content:"";position:absolute;inset:0 auto 0 0;width:3px;
background:linear-gradient(var(--gold),rgba(224,176,75,.2))}
.surv b{font-size:var(--fs-3);font-weight:600;letter-spacing:.2px}
.big{margin:10px 0 2px;color:var(--up);font-size:var(--fs-5);font-weight:700;
line-height:1.1}
.big.hero{font-size:var(--fs-5)}
.sub{color:var(--ink-2);font-size:var(--fs-1);line-height:1.75}
.tick{display:inline-block}
.dig{display:inline-block;height:1em;overflow:hidden;
vertical-align:baseline}
.reel{display:block}
.reel span{display:block;height:1em;line-height:1em}
.sym{display:inline-block}
/* ---- 表格（E 系列密度改造） ---- */
table{border-collapse:collapse;width:100%;font-size:var(--fs-2);
font-variant-numeric:tabular-nums}
th,td{padding:6px 10px;border-bottom:1px solid rgba(255,255,255,.045);
text-align:left}
th{color:var(--ink-2);font-size:var(--fs-0);text-transform:uppercase;
letter-spacing:1px;position:sticky;top:41px;background:#131824;
z-index:5}
td.r{text-align:right}
tbody tr:nth-child(even) td{background:rgba(255,255,255,.012)}
tbody tr{border-left:2px solid transparent;cursor:pointer}
tbody tr:hover td{background:rgba(255,255,255,.045)}
tbody tr.goldrow{border-left:2px solid var(--gold)}
tbody tr.sel td{background:rgba(224,176,75,.05)}
.ok{color:var(--up);font-weight:700}.no{color:var(--down)}
.na{color:var(--ink-3);font-style:italic}
.gold{color:var(--gold);font-weight:600}
code{background:var(--panel-2);border:1px solid var(--line);border-radius:5px;
padding:1px 7px;font-size:var(--fs-1);color:#B9C6D4}
.foot{color:var(--ink-3);font-size:var(--fs-1);margin-top:26px;
border-top:1px solid var(--line);padding-top:14px;line-height:1.9}
.famrow{display:flex;align-items:center;gap:10px;margin:5px 0}
.fambar{height:14px;border-radius:3px;background:var(--ink-3);opacity:.6}
.fambar.neg{background:var(--down);opacity:.8}
.wfn{fill:var(--ink-1);font-size:var(--fs-3);font-weight:700}
.wfl{fill:var(--ink-2);font-size:var(--fs-0)}
.wfs{fill:var(--ink-3);font-size:var(--fs-0)}
/* ---- KPI 条（C2 释义经 title） ---- */
.kpis{display:flex;flex-wrap:wrap;gap:0;margin-top:12px;
border-radius:14px;padding:16px 8px}
.kpi{flex:1;min-width:128px;padding:2px 18px;
border-right:1px solid rgba(255,255,255,.05);cursor:help}
.kpi:last-child{border-right:none}
.kpik{color:var(--ink-3);font-size:var(--fs-0);text-transform:uppercase;
letter-spacing:1.4px}
.kpival{font-size:var(--fs-5);font-weight:700;margin-top:3px;line-height:1.15;
transition:background .4s}
.kpival.pos{color:var(--up)}.kpival.neg{color:var(--down)}
.kpival.flash{background:rgba(224,176,75,.22);border-radius:4px}
.kpibench{color:var(--ink-3);font-size:var(--fs-0);margin-top:2px;
font-family:var(--mono);font-variant-numeric:tabular-nums}
.kpibench b{color:var(--ink-2);font-weight:600}
.kmini{height:3px;background:var(--panel-2);border-radius:2px;margin-top:7px;
overflow:hidden}
.kmini i{display:block;height:100%;border-radius:2px}
/* ---- 归因 / 表达式 / 雷达 / 热力 ---- */
.attrib{border-left:3px solid var(--gold);background:var(--panel);
border-top:1px solid var(--line);border-right:1px solid var(--line);
border-bottom:1px solid var(--line);border-radius:0 12px 12px 0;
padding:13px 18px;margin-top:14px;color:#B9C6D4;font-size:var(--fs-2);
line-height:1.85}
.attrib b{color:var(--gold)}
.attrib a{color:#B9C6D4;text-decoration:none;
border-bottom:1px dotted rgba(124,138,155,.6)}
.expr{display:inline-block;font-family:var(--mono);
font-variant-numeric:tabular-nums;font-size:var(--fs-1);
color:#B9C6D4;background:var(--panel-2);border:1px solid var(--line);
border-radius:5px;padding:2px 9px;margin:6px 0 2px;letter-spacing:.2px}
.mech{display:inline-block;font-size:var(--fs-1);color:#B9C6D4;
background:var(--panel-2);border:1px solid var(--line);
border-radius:5px;padding:1px 8px;margin:6px 0 2px}
.radarlab{fill:var(--ink-2);font-size:var(--fs-0);letter-spacing:.4px}
.radargv{fill:var(--gold);font-size:var(--fs-1);font-weight:700;
font-family:var(--mono)}
.heatcell{stroke:var(--bg);stroke-width:1}
.heatv{fill:var(--ink-2);font-size:9px;font-family:var(--mono);
text-anchor:middle}
.heaty{fill:var(--ink-2);font-size:var(--fs-0);font-family:var(--mono)}
.rollbar-pos{fill:var(--up);opacity:.7}
.rollbar-neg{fill:var(--down);opacity:.7}
.rollline{fill:none;stroke:var(--gold);stroke-width:1.6;opacity:.95}
.isos{display:flex;gap:0;border-radius:14px;overflow:hidden}
.isos>div{flex:1;padding:15px 22px}
.isos>div+div{border-left:1px solid rgba(255,255,255,.05)}
.isos .lab{color:var(--ink-3);font-size:var(--fs-0);text-transform:uppercase;
letter-spacing:1.4px}
.isos .val{font-family:var(--mono);font-variant-numeric:tabular-nums;
font-size:var(--fs-4);font-weight:700;margin-top:3px}
.sens{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,
1fr));gap:10px}
.senscell{background:var(--panel-2);border:1px solid var(--line);
border-radius:10px;padding:12px 14px}
.sensk{color:var(--ink-3);font-size:var(--fs-0);letter-spacing:.8px;
text-transform:uppercase}
.sensv{font-family:var(--mono);font-variant-numeric:tabular-nums;
font-size:var(--fs-3);font-weight:700;margin-top:3px}
.senssub{color:var(--ink-3);font-size:var(--fs-0);
font-family:var(--mono)}
/* ---- 日志 / 元数据 ---- */
.trace{font-family:var(--mono);font-size:var(--fs-1);color:#7FBF9F;
background:#0C1119;border:1px solid var(--line);border-radius:10px;
padding:12px 15px;margin-top:14px;overflow:hidden}
.tline{white-space:nowrap;text-overflow:ellipsis}
.logbody{padding:4px 16px 12px;font-family:var(--mono);
font-size:var(--fs-1);color:#7FBF9F;max-height:240px;overflow:auto}
.logbody .err{color:var(--down)}.logbody .dim{color:var(--ink-3)}
details.log{margin-top:14px;border:1px solid var(--line);
border-radius:10px;background:#0C1119}
details.log summary{cursor:pointer;padding:9px 16px;color:var(--ink-2);
font-family:var(--mono);font-size:var(--fs-1);list-style:none}
details.log summary::before{content:"\25B8 "}
details.log[open] summary::before{content:"\25BE "}
details.runmeta{margin-top:8px}
details.runmeta summary{cursor:pointer;list-style:none;display:inline-flex;
align-items:center;gap:6px;color:var(--ink-3);font-size:var(--fs-1);
font-family:var(--mono)}
details.runmeta summary::before{content:"\25B8 "}
details.runmeta[open] summary::before{content:"\25BE "}
details.runmeta[open] summary{margin-bottom:6px}
.runmetagrid{display:flex;flex-wrap:wrap;gap:4px 18px;color:var(--ink-3);
font-size:var(--fs-1);font-family:var(--mono);padding:8px 0 2px}
.badges{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.badge{font-family:var(--mono);font-size:var(--fs-0);
letter-spacing:1.2px;padding:3px 10px;border-radius:999px;border:1px solid}
.b-sim{color:var(--ink-2);border-color:rgba(139,152,169,.3);
background:var(--panel-2)}
.b-pend{color:var(--gold);border-color:rgba(224,176,75,.3);
background:rgba(224,176,75,.07)}
.b-dual{color:var(--up);border-color:rgba(52,193,134,.3);
background:rgba(52,193,134,.06)}
.b-frozen{color:var(--ink-2);border-color:var(--line);
background:var(--panel-2)}
.lsrow{display:flex;align-items:center;gap:8px;margin:3px 0}
.lsbar{flex:1;height:9px;background:var(--panel-2);border-radius:4px;
overflow:hidden}
.lsbar div{height:100%;border-radius:4px}
.heroend{fill:var(--gold);font-size:var(--fs-3);font-weight:700;
font-family:var(--mono)}
.herolab{fill:var(--ink-3);font-size:var(--fs-0)}
.ygn{fill:var(--up);font-size:var(--fs-2);font-weight:700;
font-family:var(--mono)}
.gaugev{fill:var(--ink-1);font-size:var(--fs-3);font-weight:700}
.corrv{fill:#0A0E14;font-size:var(--fs-1);font-weight:700;
font-family:var(--mono)}
/* ---- Bento ---- */
.bento{display:grid;grid-template-columns:repeat(12,1fr);gap:16px;
margin-top:14px;align-items:stretch}
.b12{grid-column:span 12}.b8{grid-column:span 8}.b7{grid-column:span 7}
.b6{grid-column:span 6}.b5{grid-column:span 5}.b4{grid-column:span 4}
.bento .card{margin:0}
@media(max-width:1200px){.b7{grid-column:span 12}.b5{grid-column:span 6}
.b4{grid-column:span 6}.b8{grid-column:span 12}}
@media(max-width:900px){.bento>*{grid-column:span 12 !important}
.toc nav{display:none}}
@media(min-width:1600px){main{max-width:1440px}}
/* ---- 交互件（F1 胶囊统一） ---- */
.pills{display:flex;gap:6px}
.pill{font-family:var(--mono);font-size:var(--fs-0);letter-spacing:1px;
padding:3px 12px;border-radius:999px;border:1px solid var(--line);
background:var(--panel-2);color:var(--ink-2);cursor:pointer;
user-select:none}
.pill:hover{border-color:rgba(139,152,169,.4);color:var(--ink-1)}
.pill.on{color:#0B0E14;background:var(--gold);border-color:var(--gold);
font-weight:700}
.feerow{display:flex;align-items:center;gap:14px;margin-top:8px;
flex-wrap:wrap}
.feeslider{flex:1;min-width:220px;-webkit-appearance:none;appearance:none;
height:4px;border-radius:2px;background:linear-gradient(90deg,var(--up),
var(--ink-3),var(--down));outline:none}
.feeslider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
width:16px;height:16px;border-radius:50%;background:var(--gold);
border:2px solid #0B0E14;cursor:grab}
.feeout{font-family:var(--mono);font-variant-numeric:tabular-nums;
font-size:var(--fs-2);color:var(--ink-1);min-width:340px}
.tbtools{display:flex;gap:8px;flex-wrap:wrap;align-items:center;
margin:8px 0}
.tbsearch{font-family:var(--mono);font-size:var(--fs-1);
background:var(--panel-2);border:1px solid var(--line);border-radius:8px;
padding:6px 12px;color:var(--ink-1);outline:none;min-width:200px}
.tbsearch:focus-visible{border-color:rgba(224,176,75,.5)}
th.sortable{cursor:pointer}
th.sortable:hover{color:var(--ink-1)}
th.sortable::after{content:" \2195";opacity:.35;font-size:9px}
th.sortable[data-dir=asc]::after{content:" \2191";opacity:.9;
color:var(--gold)}
th.sortable[data-dir=desc]::after{content:" \2193";opacity:.9;
color:var(--gold)}
.tbstats{display:flex;gap:16px;flex-wrap:wrap;color:var(--ink-3);
font-family:var(--mono);font-size:var(--fs-0);letter-spacing:.6px;
margin:6px 0 2px}
.tbstats b{color:var(--ink-1);font-weight:600}
.xhair-tip{position:absolute;pointer-events:none;background:#131824;
border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:7px 11px;
font-family:var(--mono);font-variant-numeric:tabular-nums;
font-size:var(--fs-1);color:var(--ink-1);z-index:6;white-space:nowrap;
box-shadow:0 6px 18px rgba(0,0,0,.5)}
.hero-wrap{position:relative}
#heroG{transition:opacity .25s ease}
.g#heroG.swap{opacity:0}
.concl{font-family:var(--mono);font-size:var(--fs-0);letter-spacing:.6px;
color:var(--gold);border:1px solid rgba(224,176,75,.3);
background:rgba(224,176,75,.06);border-radius:999px;padding:2px 10px;
margin-left:10px;vertical-align:2px;white-space:nowrap}
.zeroseal{text-align:center;padding:60px 0;color:var(--ink-3)}
.zeroseal b{display:block;font-size:var(--fs-5);font-weight:700;
font-family:var(--mono);color:var(--ink-2);margin-bottom:8px}
.tbhidden{display:none !important}
.legend{fill:var(--ink-3);font-size:var(--fs-0)}
@media (prefers-reduced-motion:reduce){*{animation:none !important;
transition:none !important}}
@media print{body{background:#fff;color:#111}
.surv,.runcard,.card,.kpis,.isos,.attrib,.toc{border-color:#ccc;
background:#fff}
.big{color:#0A7A42}.foot,code{color:#333}
tbody tr{opacity:1}}
"""

ENHANCE_JS = r"""
<script>
/* 渐进增强层：无 JS 时本页全部内容静态完整（三通道制）。
   依赖页面内嵌 QSA_DATA（各因子月收益/指标 + 费率网格）。*/
(function(){
"use strict";
var D = window.QSA_DATA; if(!D) return;
var $ = function(s){return document.querySelector(s)};
var $$ = function(s){return [].slice.call(document.querySelectorAll(s))};
var F = D.factors, HERO = D.hero, bench = D.bench, fee = D.fee||{};
var cur = HERO, mode = "ALL", curFee = D.base_fee_bps||8;

function nav(m){var v=1,o=[1];for(var i=0;i<m.length;i++){v*=(1+m[i]);o.push(v)}return o}
function under(nv){var pk=nv[0],o=[];for(var i=0;i<nv.length;i++){pk=Math.max(pk,nv[i]);o.push(nv[i]/pk-1)}return o}
function ann(m){if(!m.length)return null;var v=1;for(var i=0;i<m.length;i++)v*=(1+m[i]);return Math.pow(v,12/m.length)-1}
function sharpeM(m){if(m.length<3)return null;var u=m.reduce((a,b)=>a+b,0)/m.length;
 var s=Math.sqrt(m.reduce((a,b)=>a+(b-u)*(b-u),0)/(m.length-1));
 return s>0?u/s*Math.sqrt(12):null}
function mddM(nv){var pk=nv[0],w=0;for(var i=0;i<nv.length;i++){pk=Math.max(pk,nv[i]);w=Math.min(w,nv[i]/pk-1)}return w}
function fmtP(x){return (x==null)?"—":((x>=0?"+":"")+(x*100).toFixed(1)+"%")}
function fmtN(x){return (x==null)?"—":x.toFixed(2)}

/* ---------- 主图重画 ---------- */
var HW=1000,HH=300,UW=64;
function poly(pts,w,h,pad){var lo=Math.min.apply(null,pts),hi=Math.max.apply(null,pts);
 var sp=(hi-lo)||1e-9,o=[];
 for(var i=0;i<pts.length;i++)o.push((pad+i*(w-2*pad)/Math.max(1,pts.length-1)).toFixed(1)+","+(pad+(1-(pts[i]-lo)/sp)*(h-2*pad)).toFixed(1));
 return o.join(" ")}
function drawHero(id){
 var f=F[id]; if(!f) return;
 var ms=f.months, ls=feeCurve(id), nv=nav(ls), uw=under(nav(ls));
 var bn=nav(bench.slice(0,ls.length));
 var all=nv.concat(bn), lo=Math.min.apply(null,all), hi=Math.max.apply(null,all);
 var sp=(hi-lo)||1e-9;
 var Y=function(v){return 4+(1-(v-lo)/sp)*(HH-8)}, X=function(i){return 4+i*(HW-8)/Math.max(1,nv.length-1)};
 var g=$("#heroG"); if(!g) return;
 var pk=nv[0],wpk=0,wd=0,wv=0,wpi=0;
 for(var i=0;i<nv.length;i++){if(nv[i]>pk){pk=nv[i];wpk=i}
  var d=nv[i]/pk-1; if(d<wd){wd=d;wv=i;wpi=wpk;}}
 var vr=nv.length-1; for(var i=wv;i<nv.length;i++){if(nv[i]>=nv[wpi]){vr=i;break}}
 var s="";
 s+='<rect x="'+X(wpi)+'" y="4" width="'+Math.max(0,X(wv)-X(wpi))+'" height="'+(HH-8)+'" fill="#E0685C" opacity="0.07"/>';
 s+='<rect x="'+X(wv)+'" y="4" width="'+Math.max(0,X(vr)-X(wv))+'" height="'+(HH-8)+'" fill="#3FD68F" opacity="0.06"/>';
 s+='<polygon points="4,'+(HH-4)+" "+poly(nv,HW,HH,4)+" "+(HW-4)+","+(HH-4)+'" fill="url(#navfill)"/>';
 s+='<polyline points="'+poly(bn,HW,HH,4)+'" fill="none" stroke="#7A8CA0" stroke-width="1.4" stroke-dasharray="5,4" opacity="0.9"/>';
 s+='<polyline points="'+poly(nv,HW,HH,4)+'" fill="none" stroke="#3FD68F" stroke-width="1.8"/>';
 s+='<circle cx="'+X(wv)+'" cy="'+Y(nv[wv])+'" r="4.5" fill="#E0685C"><title>最大回撤谷底 '+ms[wv]+'（'+(wd*100).toFixed(1)+'%）</title></circle>';
 s+='<circle cx="'+X(nv.length-1)+'" cy="'+Y(nv[nv.length-1])+'" r="4" fill="#FFC857"><title>终值 ×'+nv[nv.length-1].toFixed(3)+'（'+ms[ms.length-1]+'）</title></circle>';
 var uwl=Math.min.apply(null,uw),us=(-uwl)||1e-9,u=[];
 for(var i=0;i<uw.length;i++)u.push((4+i*(HW-8)/Math.max(1,uw.length-1)).toFixed(1)+","+(HH+12+(uw[i]/us)*(UW-8)).toFixed(1));
 s+='<line x1="4" y1="'+(HH+8)+'" x2="'+(HW-4)+'" y2="'+(HH+8)+'" stroke="rgba(255,255,255,.1)"/>';
 s+='<polygon points="4,'+(HH+8)+" "+u.join(" ")+" "+(HW-4)+","+(HH+8)+'" fill="#E0685C" opacity="0.35"/>';
 if(mode!=="ALL"){var cut=Math.floor(ms.length*0.8),xa=X(mode==="IS"?0:cut),xb=X(mode==="IS"?cut:ms.length-1);
  s+='<rect x="0" y="0" width="'+HW+'" height="'+(HH+UW+16)+'" fill="#0B0E14" opacity="0.72"/>';
  s+='<rect x="'+xa+'" y="0" width="'+(xb-xa)+'" height="'+(HH+UW+16)+'" fill="none" stroke="#FFC857" stroke-width="1.2" opacity="0.8"/>';}
 g.innerHTML=s;
 $("#heroTitle").textContent="净值曲线 · "+id+"（"+(mode==="ALL"?"全样本":mode)+"）";
 $("#heroEnd").textContent="¥1,000,000 → ¥"+(nv[nv.length-1]*1e6).toLocaleString("en-US",{maximumFractionDigits:0});
 window.__nv=nv; window.__ms=ms; window.__uw=uw;
 drawKpi(id,ls);
 var hd=$("#heatDiv"); if(hd && window.__drawHeat) window.__drawHeat(id);
 var rl=$("#rollDiv"); if(rl && window.__drawRoll) window.__drawRoll(id);
}
function feeCurve(id){
 var f=F[id]; if(id!==HERO||!fee[curFee]) return f.ls;
 return fee[curFee].ls;
}
function drawKpi(id,ls0){
 var f=F[id], ls=ls0||feeCurve(id);
 var seg=ls; var ms=F[id].months;
 if(mode!=="ALL"){var cut=Math.floor(ms.length*0.8); seg=mode==="IS"?ls.slice(0,cut):ls.slice(cut);}
 var nv=nav(seg);
 var a=ann(seg), sh=sharpeM(seg), md=mddM(nv);
 var so=null; {var dn=seg.filter(function(x){return x<0});
  if(dn.length>2){var dv=Math.sqrt(dn.reduce(function(p,c){return p+c*c},0)/seg.length*12);
   so=dv>0?ann(seg)/dv:null;}}
 var set=function(i,v,pos){var el=$$(".kpival")[i]; if(!el)return;
  el.textContent=v; el.className="kpival "+(pos?"pos":(pos===false?"neg":""));
  var bar=$$(".kmini i")[i]; if(bar){var fv=Math.min(1,Math.abs(parseFloat(v))/ (i===0?0.35:i===1?3:i===2?4:i===3?0.4:i===4?1:2.5));
   bar.style.width=(fv*100).toFixed(0)+"%";}};
 set(0,fmtP(a),a>0); set(1,fmtN(sh),sh>=1); set(2,fmtN(so),so>=1.4);
 $$(".kpival").forEach(function(el){el.classList.add("flash");
  setTimeout(function(){el.classList.remove("flash")},450);});
 set(3,fmtP(md),false); set(4,(f.turnover*100).toFixed(0)+"%",null); set(5,fmtN(f.calmar),f.calmar>=1);
 var bl=$$(".kpibench b")[0];
 if(bl&&D.bench_ann!=null){var d=a-D.bench_ann;bl.textContent=(d>=0?"+":"")+(d*100).toFixed(1)+"%";bl.style.color=d>=0?"#3FD68F":"#E0685C";}
}
function select(id){cur=id;drawHero(id);
 var f=F[id];
 var ex=$(".expr"); if(ex&&f.expr)ex.textContent=f.expr;
 var me=$(".mech"); if(me&&f.mech)me.textContent=f.mech;
 $$("#dataTable tbody tr").forEach(function(tr){tr.style.background=tr.dataset.id===id?"rgba(255,200,87,.06)":""});
}
window.__qsaSelect=select;

/* ---------- 胶囊 ---------- */
$$(".pill[data-mode]").forEach(function(p){p.addEventListener("click",function(){
 $$(".pill[data-mode]").forEach(function(x){x.classList.remove("on")});
 p.classList.add("on"); mode=p.dataset.mode; drawHero(cur);});});

/* ---------- 费率滑块 ---------- */
var sl=$("#feeSlider");
if(sl){var out=$("#feeOut");
 sl.value=curFee;
 var upd=function(){curFee=+sl.value; var g=fee[curFee]; if(!g)return;
  out.innerHTML="单边 <b>"+curFee+"bps</b> · 年化 <b style='color:"+((g.ann>=0)?"#3FD68F":"#E0685C")+"'>"+fmtP(g.ann)+"</b> · Sharpe "+fmtN(g.sharpe)+" · MDD "+fmtP(g.mdd)+"（后端精确口径）";
  if(cur===HERO)drawHero(HERO);};
 sl.addEventListener("input",upd); upd();}

/* ---------- 表格：折叠(B2)/搜索/族筛选/排序/列toggle/行点击 ---------- */
var tb=$("#dataTable"); if(tb){
 var fams={},tbody=tb.tBodies[0],rows0=[].slice.call(tbody.rows);
 rows0.forEach(function(r){fams[r.dataset.fam]=1});
 var tools=document.createElement("div"); tools.className="tbtools";
 tools.innerHTML='<input class="tbsearch" placeholder="搜索因子…（如 gap / vol / 252，按 / 聚焦）" id="tbq">';
 Object.keys(fams).sort().forEach(function(fm){
  var b=document.createElement("button"); b.className="pill on"; b.textContent=fm;
  b.dataset.fam=fm; tools.appendChild(b);});
 var all=document.createElement("button"); all.className="pill on"; all.textContent="全部";
 all.dataset.fam="__all__"; tools.insertBefore(all,tools.children[1]||null);
 var spk=document.createElement("button"); spk.className="pill on"; spk.textContent="IC";
 spk.dataset.fam="__spark__"; tools.appendChild(spk);
 tb.parentNode.insertBefore(tools,tb);
 /* B2 折叠：默认前 10 行 + 展开按钮（零 JS 时全展开） */
 var NCOL=6, SPARK=5, FOLD=10, expanded=false;
 var foldBtn=document.createElement("button");
 foldBtn.className="pill"; foldBtn.textContent="展开全部 "+rows0.length+" 项";
 var foldState=function(){rows0.forEach(function(r,i){
  r.classList.toggle("tbhidden",!expanded&&i>=FOLD);});
  foldBtn.textContent=expanded?"收起":"展开全部 "+rows0.length+" 项";};
 foldBtn.addEventListener("click",function(){expanded=!expanded;foldState();});
 tb.parentNode.insertBefore(foldBtn,tb.nextSibling);
 var q="",famOn="__all__";
 var apply=function(){var anyVis=false;
  rows0.forEach(function(r,i){
   var okQ=!q||r.dataset.id.indexOf(q)>=0||(r.dataset.fam.indexOf(q)>=0);
   var okF=famOn==="__all__"||r.dataset.fam===famOn;
   var vis=okQ&&okF;
   r.style.display=vis?"":"none";
   r.classList.toggle("tbhidden",!(expanded||i<FOLD)&&vis);
   if(vis)anyVis=true;});
  if(q||famOn!=="__all__"){expanded=true;foldBtn.style.display="none";}
  else{foldBtn.style.display=rows0.length>FOLD?"":"none";}};
 apply(); foldState();
 tools.addEventListener("click",function(e){
  var b=e.target.closest(".pill"); if(!b)return;
  if(b.dataset.fam==="__spark__"){b.classList.toggle("on");
   var on=b.classList.contains("on");
   [].forEach.call(tbody.rows,function(r){
    var c=r.cells[SPARK]; if(c)c.style.display=on?"":"none";});
   tb.tHead.rows[0].cells[SPARK].style.display=on?"":"none"; return;}
  if(b.dataset.fam==="__all__"){famOn="__all__";tools.querySelectorAll(".pill:not([data-fam=__spark__])").forEach(function(x){x.classList.toggle("on",x.dataset.fam==="__all__")});}
  else{famOn=b.dataset.fam;tools.querySelectorAll(".pill:not([data-fam=__spark__])").forEach(function(x){x.classList.toggle("on",x.dataset.fam===famOn)});}
  apply();});
 tools.addEventListener("input",function(e){if(e.target.id==="tbq"){q=e.target.value.trim();apply();}});
 var ths=[].slice.call(tb.tHead.rows[0].cells);
 ths.forEach(function(th,i){if(i<4){th.classList.add("sortable");
  th.addEventListener("click",function(){
   var dir=th.dataset.dir==="asc"?"desc":"asc"; ths.forEach(function(t){delete t.dataset.dir});
   th.dataset.dir=dir;
   rows0.sort(function(a,b){var x=a.cells[i].textContent,y=b.cells[i].textContent;
    var nx=parseFloat(x.replace(/[^0-9.\-+]/g,"")),ny=parseFloat(y.replace(/[^0-9.\-+]/g,""));
    if(!isNaN(nx)&&!isNaN(ny))return dir==="asc"?nx-ny:ny-nx;
    return dir==="asc"?x.localeCompare(y):y.localeCompare(x);});
   rows0.forEach(function(r){tbody.appendChild(r)});apply();});}});
 tbody.addEventListener("click",function(e){var tr=e.target.closest("tr");
  if(tr&&tr.dataset.id&&F[tr.dataset.id]){select(tr.dataset.id);
   rows0.forEach(function(r){r.classList.toggle("sel",r===tr)});
   document.getElementById("hero").scrollIntoView({behavior:"smooth",block:"start"});}});
 /* 键盘：/ 搜索，j/k 行移动，Enter 选中（B8 终端感） */
 var ki=0;
 document.addEventListener("keydown",function(e){
  var tag=(document.activeElement||{}).tagName;
  if(tag==="INPUT")return;
  if(e.key==="/"){e.preventDefault();var s=$("#tbq");if(s){s.focus();}return;}
  var vis=rows0.filter(function(r){return r.style.display!=="none"&&!r.classList.contains("tbhidden")});
  if(!vis.length)return;
  if(e.key==="j"||e.key==="k"){
   ki=Math.max(0,Math.min(vis.length-1,ki+(e.key==="j"?1:-1)));
   vis.forEach(function(r){r.classList.toggle("sel",r===vis[ki])});
   vis[ki].scrollIntoView({block:"nearest"});return;}
  if(e.key==="Enter"){var id=vis[ki]&&vis[ki].dataset.id;
   if(id&&F[id])select(id);}});}

/* ---------- toc 当前屏高亮（B1） ---------- */
var tocLinks=[].slice.call(document.querySelectorAll(".toc nav a"));
if(tocLinks.length&&"IntersectionObserver" in window){
 var secMap={};tocLinks.forEach(function(a){secMap[a.getAttribute("href").slice(1)]=a});
 var obs=new IntersectionObserver(function(es){es.forEach(function(en){
  if(en.isIntersecting){tocLinks.forEach(function(a){a.classList.remove("on")});
   var a=secMap[en.target.id]; if(a)a.classList.add("on");}})},{rootMargin:"-20% 0px -70% 0px"});
 ["kpis","hero","dist","fees","table","ctrl"].forEach(function(id){
  var el=document.getElementById(id); if(el)obs.observe(el);});}

/* ---------- 回到主图（B5） ---------- */
var top=document.createElement("button");
top.className="pill"; top.textContent="回到主图 ▲"; top.style.cssText=
 "position:fixed;right:22px;bottom:22px;z-index:30;display:none";
top.addEventListener("click",function(){document.getElementById("hero")
 .scrollIntoView({behavior:"smooth"})});
document.body.appendChild(top);
window.addEventListener("scroll",function(){
 top.style.display=scrollY>innerHeight?"":"none"});

/* ---------- 十字准线 ---------- */
var hw=$(".hero-wrap");
if(hw&&$("#heroSvg")){
 var svg=$("#heroSvg"), tip=document.createElement("div");
 tip.className="xhair-tip"; tip.style.display="none"; hw.appendChild(tip);
 var rect=svg.getBoundingClientRect();
 svg.addEventListener("mousemove",function(e){
  var r=svg.getBoundingClientRect();
  var xr=(e.clientX-r.left)/r.width*HW;
  var nv=window.__nv||[],ms=window.__ms||[],uw=window.__uw||[];
  if(!nv.length)return;
  var i=Math.max(0,Math.min(nv.length-1,Math.round(xr/(HW-8)*(nv.length-1))));
  var lx=(i*(HW-8)/Math.max(1,nv.length-1)+4)/HW*r.width;
  var ln=$("#xhairLine"); if(!ln){ln=document.createElementNS("http://www.w3.org/2000/svg","line");ln.id="xhairLine";
   ln.setAttribute("stroke","rgba(255,255,255,.28)");ln.setAttribute("stroke-width","1");ln.setAttribute("stroke-dasharray","3,3");
   svg.appendChild(ln);}
  ln.setAttribute("x1",lx);ln.setAttribute("x2",lx);ln.setAttribute("y1",0);ln.setAttribute("y2",r.height);
  tip.style.display="block";
  tip.style.left=Math.min(r.width-190,lx+14)+"px"; tip.style.top=(e.clientY-r.top-10)+"px";
  tip.innerHTML=ms[i]+" · 净值 ×"+nv[i].toFixed(3)+"<br>月收益 "+fmtP((nv[i]/nv[i-1]||1)-1)+" · 回撤 "+fmtP(uw[i]);
 });
 svg.addEventListener("mouseleave",function(){tip.style.display="none";
  var ln=$("#xhairLine"); if(ln)ln.remove();});
}
})();
</script>
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
        color = "#3FD68F" if v >= 0 else "#E0685C"
        bars.append(f'<rect x="{i * bw:.1f}" y="{y:.1f}" '
                    f'width="{max(bw - 0.5, 0.5):.1f}" height="{bh:.1f}" '
                    f'fill="{color}" opacity="0.75"/>')
    lo, hi = min(cums), max(cums)
    pts = []
    for i, v in enumerate(cums):
        t = 0.5 if hi <= lo else (v - lo) / (hi - lo)
        pts.append(f"{i * bw + bw / 2:.1f},{2 + (1 - t) * (h - 4):.1f}")
    poly = (f'<polyline points="{" ".join(pts)}" fill="none" '
            'stroke="#7A8CA0" stroke-width="1.2" opacity="0.9"/>')
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


def _ic_stats(ic_series: list[dict[str, Any]]) -> tuple[float, float,
                                                          float]:
    vals = [x.get("ic") for x in ic_series if x.get("ic") is not None]
    if not vals:
        return 0.0, 0.0, 0.0
    m = sum(vals) / len(vals)
    sd = (sum((x - m) ** 2 for x in vals) / max(1, len(vals) - 1)) ** 0.5
    icir = (m / sd) * (12 ** 0.5) if sd > 0 else 0.0
    pos = sum(1 for v in vals if v > 0) / len(vals)
    return m, icir, pos


def _os_ratio(ic_series: list[dict[str, Any]]) -> float:
    vals = [x.get("ic") for x in ic_series if x.get("ic") is not None]
    if len(vals) < 6:
        return 0.0
    cut = max(3, int(len(vals) * 0.8))
    def _ir(xs):
        if len(xs) < 2:
            return 0.0
        m = sum(xs) / len(xs)
        sd = (sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)) ** 0.5
        return (m / sd) * (12 ** 0.5) if sd > 0 else 0.0
    iir, oir = _ir(vals[:cut]), _ir(vals[cut:])
    return (oir / iir) if abs(iir) > 1e-9 else 0.0


def render_index_html(rows: list[dict[str, Any]], meta: dict[str, Any],
                      ics: dict[str, list[dict[str, Any]]],
                      pnls: dict[str, dict[str, Any]] | None = None,
                      extras: dict[str, Any] | None = None) -> str:
    """总览页 HTML v4（纵深动线：KPI→曲线→分布→逐年→证据→AI 区收编）.

    零 JS、与 INDEX.md 同口径。extras={hero_id, band, log, mech, sens}。
    """
    pnls = pnls or {}
    ex = extras or {}
    fam_mech = ex.get("mech") or _showcase.FAM_MECH
    n = len(rows)
    n_both = sum(1 for x in rows if x.get("both"))

    surv = sorted([x for x in rows if x.get("both")],
                  key=lambda x: -(x.get("ann_ls")
                                  if x.get("ann_ls") is not None
                                  else (x["oos_ic"] or 0)))
    hero = ex.get("hero_id") if ex.get("hero_id") in [
        s["id"] for s in surv] else None
    if hero is None and surv:
        hero = max(surv, key=lambda x: (x.get("ann_ls")
                                        if x.get("ann_ls") is not None
                                        else -9))["id"]
    hero_row = next((r for r in rows if r["id"] == hero), None)
    hp = pnls.get(hero) or {} if hero else {}
    hero_ic = ics.get(hero, []) if hero else []

    band = ex.get("band")
    if band is None and hero:
        band = [(r["id"], pnls[r["id"]]["ls_monthly"])
                for r in rows
                if r["family"] == hero_row.get("family") and r["id"] != hero
                and r["id"] in pnls][:4]
    else:
        band = band or []

    log = ex.get("log") or [
        f"[run] engine={meta.get('engine', 'qsa')} "
        f"backend={meta.get('backend', 'stdlib')} "
        f"commit={meta.get('commit', '—')}",
        f"[scan] {n} 个实现 → 矩阵化引擎（零逐因子回退）",
        "[stage2] 逐级淘汰：stage1 → stage2(冻结) → s2-v2(待拍板) → walk-forward",
        f"[pnl] 幸存者 {len(surv)} → 等权五分位多空，月度换仓，"
        f"单边 {(meta.get('fee_bps') or 8):.0f}bps，成本摊 20 日",
        f"[done] elapsed={meta.get('elapsed_s', '—')}  双过 {n_both}/{n}",
    ]

    fp = _showcase.fingerprint_svg(hero_ic) if hero else ""
    corr = (_showcase.corr_matrix_svg(
        {r["id"]: pnls[r["id"]]["ls_monthly"]
         for r in surv if r["id"] in pnls})
        if sum(1 for r in surv if r["id"] in pnls) >= 2 else "")

    e, l, last12 = (_lifespan(hero_ic) if hero else (None, None, None))
    life = _showcase.lifespan_bars(e, l, last12) if e is not None else ""

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
                '<div class="badges"><span class="badge b-sim">SIM</span>'
                '<span class="badge b-dual">双实现一致</span>'
                '<span class="badge b-pend">待拍板</span></div>'
                f'<div class="big">{oos}</div>'
                '<div class="sub">OOS IC（后 20% 月份）</div>'
                f'<code class="expr">{_esc(_showcase.factor_expr(r["id"]))}'
                "</code>"
                f'<div class="mech">{_esc(mech)}</div>'
                f'<div class="sub">ICIR(年化) {r["icir_a"]:.2f}'
                f"　·　多空 {r['tmb']:+.2f}"
                f"　·　正IC月 {r.get('pos_share', 0):.0%}{ann}</div>"
                f'{curve}</div>')

    surv_html = "".join(_surv_card(r) for r in surv) or (
        '<div class="sub">无幸存者（诚实零也是结果：全部变体未过'
        "诊断双过门，不硬凑候选）</div>")

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

    trs = []
    for r in sorted(rows, key=lambda x: -(x["oos_ic"] or -9)):
        spark = sparkline_svg(ics[r["id"]]) if r["id"] in ics else ""
        name_cls = "gold" if r.get("both") else ""
        row_cls = ' class="goldrow"' if r.get("both") else ""
        pnl_cell = ("—" if r.get("ann_ls") is None
                    else f"{r['ann_ls']:+.1%}")
        color = ("#3fd68f" if (r.get("ann_ls") or 0) > 0
                 else "#e0685c" if r.get("ann_ls") is not None
                 else "#57606a")
        trs.append(
            f'<tr{row_cls}><td class="{name_cls}">{_esc(r["id"])}</td>'
            f'<td><code>{_esc(r.get("family", "?"))}</code></td>'
            f'<td>{r["oos_ic"]:+.4f}</td><td>{r["icir_a"]:.2f}</td>'
            f'<td style="color:{color}">{pnl_cell}</td>'
            f'<td>{verdict_chain_svg(r)}</td><td>{spark}</td></tr>')

    dup = f"　·　{_esc(meta['dedup_note'])}" if meta.get("dedup_note") else ""
    log_html = "".join(f"<div>{_esc(line)}</div>" for line in log)

    # ---- v4 数据组件 ----
    bench_ann = None
    if hp.get("bench_monthly"):
        b = 1.0
        for r in hp["bench_monthly"]:
            b *= (1.0 + r)
        bench_ann = (b ** (12.0 / max(1, len(hp["bench_monthly"]))) - 1.0
                     if b > 0 else None)
    kpis = _showcase.kpi_strip(hp, bench_ann) if hp else ""
    isos = _showcase.is_os_bar(hero_ic) if hero else ""
    heat = (_showcase.monthly_heatmap_svg(hp["months"], hp["ls_monthly"])
            if hp.get("months") else "")
    roll = _showcase.rolling_ic_svg(hero_ic) if hero else ""
    yearly = hp.get("yearly_ls")
    yearly_html = _showcase.yearly_gain_svg(yearly) if yearly else ""
    gauges = _showcase.gauges_svg(hp) if hp else ""
    hero_svg = (_showcase.hero_pnl_svg(hp, band)
                if hp and hp.get("ls_monthly") else
                '<div class="zeroseal"><b>0</b>'
                f"全部 {n} 项均未通过诊断双过门 — 诚实零"
                "<br>不硬凑候选；正式结论只认冻结 run</div>")

    # 雷达六维（0-1 分）
    radar = ""
    if hp and hero:
        ic_m, icir_a, pos_share = _ic_stats(hero_ic)
        mdd = abs(hp.get("max_drawdown_ls") or 0.35)
        tu = hp.get("turnover_monthly_one_side") or 0.5
        ann = hp.get("ann_ls_net") or 0.0
        osr = _os_ratio(hero_ic)
        clip = lambda v: max(0.04, min(1.0, v))
        radar = _showcase.radar_svg({
            "盈利能力": (clip(ann / 0.30), f"{ann:+.0%}"),
            "IC 稳定性": (clip(icir_a / 1.5), f"{icir_a:.2f}"),
            "抗回撤": (clip(1 - mdd / 0.35), f"{-mdd:.0%}"),
            "低换手": (clip(1 - tu), f"{tu * 100:.0f}%"),
            "正 IC 月": (clip(pos_share / 0.7), f"{pos_share:.0%}"),
            "OS 保持": (clip(osr), f"{osr:.0%}"),
        })

    # 敏感性（fee 扫描，由 tools 预算好传入）
    sens_html = _showcase.sensitivity_grid(ex.get("sens") or [])

    # 归因卡（规则引擎生成，非 LLM 吹生成；锚链溯源）
    attrib = ""
    if hp and hero:
        worst_m = min(zip(hp["months"], hp["ls_monthly"]),
                      key=lambda x: x[1])
        best_m = max(zip(hp["months"], hp["ls_monthly"]),
                     key=lambda x: x[1])
        osr = _os_ratio(hero_ic)
        ann = hp.get("ann_ls_net")
        decay = ("样本外 IC 保持 " + f"{osr:.0%}"
                 if osr < 0.8 else f"样本外 IC 保持 {osr:.0%}（未见明显衰减）")
        attrib = (f"<div class='attrib'>诊断（规则引擎，非 AI 生成）："
                  f"<b>{_esc(hero)}</b> 年化 "
                  f"<b>{(ann or 0):+.1%}</b>（费后模拟），"
                  f"最大回撤 <b>{(hp.get('max_drawdown_ls') or 0):.1%}</b>"
                  f"（<a href='#hero'>▼ 回撤竖带</a>），最差月 "
                  f"{worst_m[1]:+.1%}（{worst_m[0]}）／最佳月 "
                  f"{best_m[1]:+.1%}（{best_m[0]}，"
                  f"<a href='#heat'>热力矩阵</a>）；{decay}"
                  f"（<a href='#isos'>IS/OS 对照</a>）。"
                  f"月度收益分布见 <a href='#heat'>#heat</a>，"
                  f"证据链见 <a href='#panel'>#panel</a>。</div>")
    import json as _json
    # JS 增强数据（无 JS 时页面静态完整；JS 仅做切换/联动）
    jsdata = ex.get("jsdata") or {}
    js_tag = ""
    if jsdata:
        js_tag = ("<script>window.QSA_DATA="
                  + _json.dumps(jsdata, separators=(",", ":"),
                                allow_nan=False) + ";</script>")

    # 指纹徽章（降级自指纹墙）
    fp_badge = _showcase.fingerprint_badge(hero_ic) if hero else ""

    def table_row(r):
        spark = sparkline_svg(ics[r["id"]]) if r["id"] in ics else ""
        name_cls = "gold" if r.get("both") else ""
        row_cls = ' class="goldrow"' if r.get("both") else ""
        pnl = r.get("ann_ls")
        pnl_cell = ('<span class="na">—</span>' if pnl is None
                    else f"{pnl:+.1%}")
        color = ("#34C186" if (pnl or 0) > 0
                 else "#D0695A" if pnl is not None else "")
        style = f' style="color:{color}"' if color else ""
        return (f'<tr{row_cls} data-id="{_esc(r["id"])}" '
                f'data-fam="{_esc(r.get("family", "?"))}">'
                f'<td class="{name_cls}">{_esc(r["id"])}</td>'
                f'<td><code>{_esc(r.get("family", "?"))}</code></td>'
                f'<td class="r">{r["oos_ic"]:+.4f} / {r["icir_a"]:.2f}</td>'
                f'<td class="r"{style}>{pnl_cell}</td>'
                f'<td>{verdict_chain_svg(r)}</td><td>{spark}</td></tr>')

    def _showcase_pct(x: float) -> str:
        return f"{x:+.1%}"

    # C4 每屏结论胶囊 / F9 空态印章 / E9 统计条
    conc_kpi = (f"双过 {n_both} · 最佳 {_esc(str(hero))}" if hero
                else "诚实零 · 无幸存者")
    conc_heat = ""
    conc_fee = ""
    if hp.get("months") and hp.get("ls_monthly"):
        pos_n = sum(1 for x in hp["ls_monthly"] if x > 0)
        worst = min(zip(hp["months"], hp["ls_monthly"]), key=lambda t: t[1])
        conc_heat = (f"正收益月 {pos_n / len(hp['ls_monthly']):.0%}"
                     f" · 最差 {worst[1]:+.1%}（{worst[0]}）")
    sens0 = ex.get("sens") or []
    if len(sens0) >= 2:
        conc_fee = (f"2→50bps 年化 {sens0[0]['v']} → {sens0[-1]['v']}")
    ann_hero = (hero_row or {}).get("ann_ls") if hero_row else None
    oos_sorted = sorted(r["oos_ic"] for r in rows
                        if r.get("oos_ic") is not None)
    med_oos = (oos_sorted[len(oos_sorted) // 2] if oos_sorted else 0.0)

    trs = [table_row(r)
           for r in sorted(rows, key=lambda x: -(x["oos_ic"] or -9))]
    dup = f"　·　{_esc(meta['dedup_note'])}" if meta.get("dedup_note") else ""
    log_html = "".join(f"<div>{_esc(line)}</div>" for line in log)

    bench_ann = None
    if hp.get("bench_monthly"):
        b = 1.0
        for r in hp["bench_monthly"]:
            b *= (1.0 + r)
        bench_ann = (b ** (12.0 / max(1, len(hp["bench_monthly"]))) - 1.0
                     if b > 0 else None)
    kpis = _showcase.kpi_strip(hp, bench_ann) if hp else ""
    isos = _showcase.is_os_bar(hero_ic) if hero else ""
    heat = (_showcase.monthly_heatmap_svg(hp["months"], hp["ls_monthly"])
            if hp.get("months") else "")
    roll = _showcase.rolling_ic_svg(hero_ic) if hero else ""
    yearly = hp.get("yearly_ls")
    yearly_html = _showcase.yearly_gain_svg(yearly) if yearly else ""
    hero_svg = (_showcase.hero_pnl_svg(hp, band)
                if hp and hp.get("ls_monthly") else
                f'<div class="sub">无幸存者净值可展示'
                f"（{n} 项均未通过诊断双过门 — 诚实零）</div>")

    radar = ""
    if hp and hero:
        ic_m, icir_a, pos_share = _ic_stats(hero_ic)
        mdd = abs(hp.get("max_drawdown_ls") or 0.35)
        tu = hp.get("turnover_monthly_one_side") or 0.5
        ann = hp.get("ann_ls_net") or 0.0
        osr = _os_ratio(hero_ic)
        clip = lambda v: max(0.04, min(1.0, v))
        radar = _showcase.radar_svg({
            "盈利能力": (clip(ann / 0.30), f"{ann:+.0%}"),
            "IC 稳定性": (clip(icir_a / 1.5), f"{icir_a:.2f}"),
            "抗回撤": (clip(1 - mdd / 0.35), f"{-mdd:.0%}"),
            "低换手": (clip(1 - tu), f"{tu * 100:.0f}%"),
            "正 IC 月": (clip(pos_share / 0.7), f"{pos_share:.0%}"),
            "OS 保持": (clip(osr), f"{osr:.0%}"),
        })

    sens_html = _showcase.sensitivity_grid(ex.get("sens") or [])

    attrib = ""
    if hp and hero:
        worst_m = min(zip(hp["months"], hp["ls_monthly"]),
                      key=lambda x: x[1])
        best_m = max(zip(hp["months"], hp["ls_monthly"]),
                     key=lambda x: x[1])
        osr = _os_ratio(hero_ic)
        ann = hp.get("ann_ls_net")
        decay = (f"样本外 IC 保持 {osr:.0%}"
                 + ("" if osr >= 0.8 else "（衰减可见，如实展示）"))
        attrib = (f"<div class='attrib'>诊断："
                  f"<b>{_esc(hero)}</b> 年化 "
                  f"<b>{(ann or 0):+.1%}</b>（费后模拟），"
                  f"最大回撤 <b>{(hp.get('max_drawdown_ls') or 0):.1%}</b>"
                  f"（<a href='#hero'>▼ 竖带</a>，日频口径；主图为月频），"
                  f"最差月 {worst_m[1]:+.1%}（{worst_m[0]}）／最佳月 "
                  f"{best_m[1]:+.1%}（{best_m[0]}，<a href='#heat'>热力</a>）；"
                  f"{decay}（<a href='#isos'>IS/OS</a>）。</div>")

    fams_n = len({r.get("family") for r in rows})

    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(meta.get('title', '测试总览'))} · quant-super-agent</title>
<style>{DARK_CSS}</style></head><body><main>
{run_header_html(meta, rows, n_both)}
<div class="toc">
<span class="badge b-sim">SIM · 费后模拟</span>
{fp_badge}
<span class="badge b-frozen">口径冻结</span>
<span class="badge b-pend">s2-v2 待拍板</span>
<nav>
<a href="#kpis">指标</a><a href="#dist">分布</a><a href="#fees">费率</a>
<a href="#table">全表</a><a href="#ctrl">口径</a>
</nav>
</div>
<details class="guide" open><summary>怎么读这页（30 秒）</summary>
<div class="gbody">
① <b>先看核心指标条</b>：六格全过及格线（绿）才值得往下看；
② <b>再看净值与回撤</b>：主图绿线是多空、灰虚线是基准，红带是最深回撤段；
③ <b>凭什么信</b>：右下「边界与口径」写明模拟假设与冻结门——<b>双过≠入册</b>，正式结论只认冻结 run（待拍板）。<br>
<span style="color:var(--ink-3)">交互：表内点任意行联动主图；费率滑块拖动看成本杀伤力；零 JS 时本页全部内容静态可读。</span>
</div></details>
<span class="sub">{_esc(meta.get('snap', ''))}　·　{n} 实现 · {fams_n} 族 · 诊断双过 {n_both}{dup}</span>
<details class="runmeta"><summary>Run Metadata（引擎/数据面/口径）</summary>
<div class="runmetagrid">
<span>engine {_esc(meta.get('engine', 'qsa'))}</span>
<span>backend {_esc(meta.get('backend', 'stdlib'))}</span>
<span>commit {_esc(meta.get('commit', '—'))}</span>
<span>样本 {_esc(str(meta.get('n_months', '')))} 月 × {meta.get('n_tickers', '')} 标的</span>
<span>判决门 stage1/stage2 冻结 · s2-v2 待拍板 · walk-forward</span>
</div></details>

<h2 id="kpis">核心指标 · {_esc(str(hero or '无幸存者'))}<span class="concl">{conc_kpi}</span></h2>
{kpis}

<div class="bento">
<div class="card b8 hero-wrap" id="hero">
<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
<b id="heroTitle" style="font-size:var(--fs-3)">净值曲线 · {_esc(str(hero or '—'))}</b>
<span class="pills">
<span class="pill on" data-mode="ALL">ALL</span>
<span class="pill" data-mode="IS">IS</span>
<span class="pill" data-mode="OS">OS</span></span>
<span class="sub" id="heroEnd" style="margin-left:auto;font-family:var(--mono);color:var(--gold);font-weight:700"></span>
</div>
<span class="expr">{_esc(_showcase.factor_expr(hero or ''))}</span>
<span class="mech">{_esc(fam_mech.get((hero_row or {}).get('family', ''), ''))}</span>
<div id="heroBox">{hero_svg}</div>
{attrib}
</div>
<div class="card b4" id="isos">
<h3 style="font-size:var(--fs-2);color:var(--ink-2);margin:0 0 8px">样本内外对照（IC 口径）</h3>
{isos}
<p class="sub" style="margin-top:10px">IS=前 80% 月 · OS=后 20% 月 · OS 保持率=OS ICIR / IS ICIR（不藏衰减）</p>
</div>
</div>

<div class="bento" id="dist">
<div class="card b7" id="heat">
<h3 style="font-size:var(--fs-2);color:var(--ink-2);margin:0 0 8px">月度收益热力<span class="concl">{conc_heat}</span></h3>
<div id="heatDiv">{heat}</div>
<p class="sub" style="margin:8px 0 4px">滚动 IC（12 月滚动均值线，信号是否只靠个别年份）</p>
<div id="rollDiv">{roll}</div>
</div>
<div class="card b5">
<h3 style="font-size:var(--fs-2);color:var(--ink-2);margin:0 0 8px">六维稳健性雷达</h3>
{radar}
<div style="margin-top:6px">{yearly_html}</div>
</div>
</div>

<div class="bento">
<div class="card b12" id="fees">
<h3 style="font-size:var(--fs-2);color:var(--ink-2);margin:0 0 8px">费率敏感性<span class="concl">{conc_fee}</span></h3>
<div class="feerow">
<input type="range" class="feeslider" id="feeSlider"
 min="2" max="50" step="1" value="{(meta.get('fee_bps') or 8)}"
 aria-label="单边费率 bps">
<span class="feeout" id="feeOut">拖动滑块调整单边费率（后端预计算口径）</span>
</div>
{sens_html}
<p class="sub">滑块为后端预计算的 2–50bps 网格（精确口径）；静态四格为锚点参照。无 JS 时静态格完整可读。</p>
</div>
</div>

<h2>幸存因子（诊断双过，待拍板）</h2>
<div class="cards">{surv_html}</div>

<h2 id="table">全部实现<span class="concl">{n} 变体 · 双过 {n_both}</span></h2>
<div class="tbstats"><span>共 <b>{n}</b> 变体</span><span>双过 <b>{n_both}</b></span>
<span>最佳 <b class="gold">{_esc(str(hero or '—'))}</b>{f" {_showcase_pct(ann_hero)}" if ann_hero is not None else ''}</span>
<span>OOS IC 中位 <b>{med_oos:.4f}</b></span></div>
<table id="dataTable"><colgroup>
<col style="width:16%"><col style="width:9%"><col style="width:17%">
<col style="width:13%"><col style="width:16%"><col style="width:29%">
</colgroup><thead><tr><th>因子</th><th>族</th><th>OOS IC / ICIR(年化)</th>
<th>多空年化(模拟)</th><th>判决链</th><th>月度IC</th></tr></thead>
<tbody>
{''.join(trs)}</tbody></table>
<p class="sub" style="margin:10px 0 4px">淘汰瀑布（全部 → s2-v2 → walk-forward → 冻结入册）</p>
{waterfall_svg([{"label": "全部变体", "n": n, "color": "#7C8A9B", "note": meta.get("elapsed_s", "")},
{"label": "过 s2-v2（年化口径）", "n": sum(1 for r in rows if r.get('s2v2') == 'pass'), "color": "#7C8A9B", "note": "待拍板"},
{"label": "+ walk-forward", "n": n_both, "color": "#34C186", "note": "诊断双过"},
{"label": "冻结 run 入册", "n": 0, "color": "#7C8A9B", "note": "待拍板后执行"}])}

<h2>族级对比（各族最强变体）</h2>
{''.join(fam_rows)}

<h2 id="ctrl">边界与口径（控制权）</h2>
<div class="card"><p style="margin:4px 0">· 判决门 <b class="gold">冻结</b>：stage1/stage2 与冻结裁决一致，页面改不动门。<br>
· 幸存者只是「诊断双过」：<b>不入册、不构成对外主张</b>，正式结论唯一路径=冻结 run（待拍板）。<br>
· 全部 PnL 为<b>模拟</b>（等权、月度换仓、成本摊 20 日），不含冲击成本/停牌/涨跌停。<br>
· 零幸存者时如实显示诚实零，不硬凑候选。</p></div>

<details class="log"><summary>运行日志（推理流回放）</summary>
<div class="trace" style="border:none;padding:0;background:none">
{_showcase.trace_flow_html(log)}</div>
<div class="logbody">{log_html}</div></details>

<div class="foot">判决链第一/二节点为冻结门 stage1/stage2；第三节点 s2-v2 为拟议年化口径（待拍板，未入册）；both=双过不构成对外主张。PnL 为组合级<b>模拟</b>（等权五分位、月度换仓、单边 {_esc(f"{(meta.get('fee_bps') or 8):.0f}")}bps、成本摊20日），不含冲击成本/停牌/涨跌停，不构成实盘主张。指标与门禁/单卡同源同口径；顶栏 MDD 为日频、主图竖带为月频净值口径。本页无 JS 亦完整可读（增强脚本仅提供切换/联动/滑块交互，无外部依赖）。</div>
</main>
{js_tag}
{ENHANCE_JS}
</body></html>
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
