"""Showcase components — AI 科技感 + 策略价值感的叙事组件库（v3）.

全部纯函数、零 JS（CSS animation / SVG，reduced-motion 由页面级
兜底统一降级）。分两组：

AI 过程可见（A 组）：trace 推理流 / ECG 心电 / 粒子数据流 /
指纹墙 / 并行赛道 —— "看见 agent 在工作"。
策略价值叙事（B 组）：hero 净值（基准+邻域带+终值）/ 回撤水下 /
年度增强条 / 三针仪表 / IC 寿命条 / 相关矩阵 —— "看见钱与风险"。
"""
from __future__ import annotations

import math
from typing import Any

# 色板（与页面 DARK_CSS 一致）
C_LS = "#4cc2ff"        # 多空主线（青）
C_G5 = "#3fd68f"        # 多头（绿）
C_G1 = "#ff6b6b"        # 空头（红）
C_BENCH = "#8b98a9"     # 基准（灰）
C_GOLD = "#E0B04B"      # 幸存者（金）
C_DIM = "#57606a"


def _navs(monthly: list[float]) -> list[float]:
    nav, out = 1.0, []
    for r in monthly:
        nav *= (1.0 + r)
        out.append(nav)
    return out


def _underwater(navs: list[float]) -> list[float]:
    peak, out = -1e18, []
    for v in navs:
        peak = max(peak, v)
        out.append(v / peak - 1.0 if peak > 0 else 0.0)
    return out


def _poly(xs: list[float], w: float, lo: float, hi: float,
          h: float, pad: float = 4) -> str:
    span = (hi - lo) or 1e-9
    return " ".join(
        f"{pad + i * (w - 2 * pad) / max(1, len(xs) - 1):.1f},"
        f"{pad + (1 - (v - lo) / span) * (h - 2 * pad):.1f}"
        for i, v in enumerate(xs))


# ---------------------------------------------------------------- B1+B2+B3+B9+B10
# 族机制标签（B5，一句话人话）
FAM_MECH = {
    "overnight": "隔夜缺口动量：过去 N 日「收盘-当日最高」缺口的累积（负缺口=被砸出空间）",
    "near-high": "近高动量：收盘距 N 日高点的距离（贴近高点=强势）",
    "momentum": "窗口动量：过去 N 日累计收益（跳过 s 日避免短期反转污染）",
    "volatility": "波动率：过去 N 日收益标准差（低波=质量代理）",
    "reversal": "短期反转：过去 N 日累计收益取反（跌多了反弹）",
    "skew": "偏度/极端收益：收益分布形状特征",
    "volume": "量能特征：成交量相关形态",
    "friction": "交易摩擦：零收益/停牌结构",
    "misc": "其他形态（未归类）",
}


def hero_pnl_svg(main: dict[str, Any],
                 band: list[tuple[str, list[float]]],
                 w: int = 1000, h: int = 300, uw_h: int = 64
                 ) -> str:
    """主视觉净值：邻域带 + G5/G1/基准 + L-S 发光主线 + 回撤水下.

    main: longshort_pnl 结果（含 months/g5/g1/ls/bench_monthly）。
    band: [(id, ls_monthly)] 邻域窗口线（半透明扇形带）。
    """
    months = main["months"]
    n = len(months)
    if not n:
        return "<svg></svg>"
    main_nav = _navs(main["ls_monthly"])
    bench_nav = _navs(main["bench_monthly"])
    g5 = _navs(main.get("g5_monthly") or [])
    g1 = _navs(main.get("g1_monthly") or [])
    series = ([_navs(m) for _, m in band if m]
              + [s for s in (main_nav, bench_nav, g5, g1) if s])
    lo = min(min(s) for s in series)
    hi = max(max(s) for s in series)
    out = [f'<svg id="heroSvg" viewBox="0 0 {w} {h + uw_h + 26}" '
           'width="100%" '
           'role="img" aria-label="long-short NAV hero">',
           '<defs><linearGradient id="navfill" x1="0" y1="0" x2="0"'
           ' y2="1"><stop offset="0" stop-color="#34C186" '
           'stop-opacity="0.16"/><stop offset="1" stop-color="#34C186" '
           'stop-opacity="0"/></linearGradient></defs>', '<g id="heroG">']
    # 网格
    for gy in range(1, 4):
        y = pad_y = 4 + gy * (h - 8) / 4
        out.append(f'<line x1="4" y1="{y:.0f}" x2="{w - 4}" y2="{y:.0f}" '
                   'stroke="rgba(255,255,255,.05)" stroke-width="1"/>')
    # 邻域带（半透明）
    for bid, m in band:
        nv = _navs(m)
        blo = min(min(_navs(x)) for x in [m]) if m else lo
        out.append(f'<polyline points="{_poly(nv, w, lo, hi, h)}" '
                   f'fill="none" stroke="{C_LS}" stroke-width="1" '
                   'opacity="0.16"/>')
    # 基准（灰虚线）
    out.append(f'<polyline points="{_poly(bench_nav, w, lo, hi, h)}" '
               f'fill="none" stroke="{C_BENCH}" stroke-width="1.4" '
               'stroke-dasharray="5,4" opacity="0.9"/>')
    # G5/G1
    if g5:
        out.append(f'<polyline points="{_poly(g5, w, lo, hi, h)}" '
                   f'fill="none" stroke="{C_G5}" stroke-width="1.2" '
                   f'opacity="0.75"/>')
    if g1:
        out.append(f'<polyline points="{_poly(g1, w, lo, hi, h)}" '
                   f'fill="none" stroke="{C_G1}" stroke-width="1.2" '
                   'opacity="0.75"/>')
    # MaxDD 竖带：peak→valley（淡红）、valley→recovery（淡绿）
    def _x_at(i: int) -> float:
        return 4 + i * (w - 8) / max(1, n - 1)

    peak_i = 0
    worst = (0, 0, 0.0)  # (peak, valley, depth)
    run_peak, run_peak_i = main_nav[0], 0
    for i, v in enumerate(main_nav):
        if v > run_peak:
            run_peak, run_peak_i = v, i
        dd = (v / run_peak - 1.0) if run_peak else 0.0
        if dd < worst[2]:
            worst = (run_peak_i, i, dd)
    vp, vv, vd = worst
    vr = next((i for i in range(vv, n)
               if main_nav[i] >= main_nav[vp]), n - 1)
    x_p, x_v, x_r = _x_at(vp), _x_at(vv), _x_at(vr)
    out.append(f'<rect x="{x_p:.1f}" y="4" width="{x_v - x_p:.1f}" '
               f'height="{h - 8:.1f}" fill="#D0695A" opacity="0.07"/>'
               f'<rect x="{x_v:.1f}" y="4" width="{x_r - x_v:.1f}" '
               f'height="{h - 8:.1f}" fill="#34C186" opacity="0.06"/>')
    out.append(f'<text x="{(x_p + x_v) / 2:.0f}" y="34" '
               f'text-anchor="middle" class="herolab">▼ {vd:.1%}</text>')
    # 面积渐变（v4 #11）
    area_pts = _poly(main_nav, w, lo, hi, h)
    out.append(f'<polygon points="4,{h - 4} {area_pts} {w - 4},{h - 4}" '
               'fill="url(#navfill)"/>')
    # L-S 主线（发光：三层描边）
    pts = _poly(main_nav, w, lo, hi, h)
    for sw, op in ((7, 0.12), (3.5, 0.3), (1.8, 1.0)):
        out.append(f'<polyline points="{pts}" fill="none" stroke="{C_LS}" '
                   f'stroke-width="{sw}" opacity="{op}"/>')
    # 发光锚点（SVG 原生 <title> 悬停，零 JS）：MaxDD 谷底 / 最佳月 / 终值
    def _y_at(i: int) -> float:
        return 4 + (1 - (main_nav[i] - lo) / ((hi - lo) or 1)) * (h - 8)

    best_i = max(range(n), key=lambda i: main_nav[i])
    y_v = _y_at(vv)
    out.append(f'<circle cx="{x_v:.1f}" cy="{y_v:.1f}" r="4.5" '
               f'fill="#D0695A" stroke="#0B0E14" stroke-width="1.5">'
               f"<title>最大回撤谷底 {months[vv]}（{vd:.1%}，"
               f"{months[vp]}→{months[vv]} 跌 / {months[vr]} 修复）</title>"
               "</circle>")
    out.append(f'<circle cx="{_x_at(best_i):.1f}" cy="{_y_at(best_i):.1f}" '
               'r="3.5" fill="#34C186" stroke="#0B0E14" stroke-width="1.5">'
               f"<title>净值峰值 {months[best_i]}（×"
               f"{main_nav[best_i]:.2f}）</title></circle>")
    out.append(f'<circle cx="{w - 4:.0f}" cy="{_y_at(n - 1):.1f}" '
               f'r="4" fill="{C_GOLD}">'
               f"<title>终值 ×{main_nav[-1]:.3f}（{months[-1]}）</title>"
               "</circle>")
    # 终值徽章（B10）
    final = main_nav[-1]
    out.append(f'<text x="{w - 10}" y="20" text-anchor="end" '
               f'class="heroend">¥1,000,000 → ¥{final * 1e6:,.0f}'
               '</text>')
    # 图内左上图例（C3：常显、色块样例、不依赖读者扫到图底）
    out.append('<g id="heroLegend">')
    lg = [("多空 L-S", "#34C186", ""), ("等权基准", "#7C8A9B", "5,4"),
          ("回撤段", "#D0695A", "")]
    lx = 12
    for lab, col, dash in lg:
        out.append(f'<line x1="{lx}" y1="14" x2="{lx + 18}" y2="14" '
                   f'stroke="{col}" stroke-width="2.4"'
                   + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")
        out.append(f'<text x="{lx + 23}" y="17.5" class="legend">{lab}</text>')
        lx += 23 + len(lab) * 11 + 26
    out.append("</g>")
    out.append(f'<text x="8" y="{h - 8:.0f}" class="herolab">'
               f"{months[0]} — {months[-1]} · 费后模拟（SIM）</text>")
    # 回撤水下（B3）：基线在主图下方 base=h+8，映射到 [base+4, base+uw_h-4]
    uw = _underwater(main_nav)
    base = h + 8
    uw_lo = min(uw)
    uw_span = (-uw_lo) or 1e-9
    n_uw = len(uw)
    uw_pts = " ".join(
        f"{4 + i * (w - 8) / max(1, n_uw - 1):.1f},"
        f"{base + 4 + (uw[i] / uw_span) * (uw_h - 8):.1f}"
        for i in range(n_uw))
    out.append(f'<line x1="4" y1="{base}" x2="{w - 4}" y2="{base}" '
               'stroke="#263140" stroke-width="1"/>')
    out.append(f'<polygon points="4,{base} {uw_pts} {w - 4},{base}" '
               f'fill="{C_G1}" opacity="0.35"/>')
    worst_i = min(range(len(uw)), key=lambda i: uw[i])
    # 最长水下期
    peak_i, span_best, cur = 0, (0, 0), 0
    for i, v in enumerate(uw):
        if v >= -1e-12:
            if i - cur > span_best[1] - span_best[0]:
                span_best = (cur, i)
            cur = i
    if len(uw) - cur > span_best[1] - span_best[0]:
        span_best = (cur, len(uw))
    out.append(f'<text x="8" y="{base + uw_h}" class="herolab">回撤水下'
               f' · 最大 {uw[worst_i] * 100:.1f}% @ {months[worst_i]}'
               f' · 最长水下 {span_best[1] - span_best[0]} 个月</text>')
    return "".join(out) + "</g></svg>"


# ---------------------------------------------------------------- B4 年度增强
def yearly_gain_svg(yearly: list[tuple[str, float]],
                    w: int = 640, h: int = 150) -> str:
    hi = max(abs(r) for _, r in yearly) or 1e-9
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
           'aria-label="yearly gain">']
    bw = (w - 40) / max(1, len(yearly)) * 0.42
    gap = (w - 40) / max(1, len(yearly))
    for i, (y, r) in enumerate(yearly):
        x = 20 + i * gap
        bh = abs(r) / hi * (h / 2 - 30)
        color = C_G5 if r >= 0 else C_G1
        y0 = h / 2 - bh if r >= 0 else h / 2
        out.append(f'<rect x="{x:.0f}" y="{y0:.0f}" width="{bw:.0f}" '
                   f'height="{max(bh, 2):.0f}" rx="3" fill="{color}" '
                   f'class="wfbar" style="animation-delay:{i * 100}ms"/>')
        out.append(f'<text x="{x + bw / 2:.0f}" y="{y0 - 6:.0f}" '
                   f'text-anchor="middle" class="ygn">{r * 100:+.1f}%</text>')
        out.append(f'<text x="{x + bw / 2:.0f}" y="{h - 6:.0f}" '
                   f'text-anchor="middle" class="wfl">{y}</text>')
    out.append(f'<line x1="4" y1="{h / 2}" x2="{w - 4}" y2="{h / 2}" '
               'stroke="#263140"/>')
    return "".join(out) + "</svg>"


# ---------------------------------------------------------------- B6 三针仪表
def _gauge(cx: float, cy: float, r: float, frac: float, color: str,
           label: str, value: str) -> str:
    a0, a1 = math.pi, 2 * math.pi
    a = a0 + (a1 - a0) * max(0.0, min(1.0, frac))
    x0, y0 = cx - r, cy
    x1, y1 = cx + r * math.cos(a), cy + r * math.sin(a)
    large = 1 if (a - a0) > math.pi else 0
    nx, ny = cx + (r - 9) * math.cos(a), cy + (r - 9) * math.sin(a)
    return (f'<path d="M {cx - r:.0f} {cy} A {r} {r} 0 1 1 {cx + r:.0f} '
            f'{cy}" fill="none" stroke="#1f2733" stroke-width="6" '
            'stroke-linecap="round"/>'
            f'<path d="M {x0:.0f} {y0:.0f} A {r} {r} 0 {large} 1 '
            f'{x1:.0f} {y1:.0f}" fill="none" stroke="{color}" '
            'stroke-width="6" stroke-linecap="round" opacity="0.95"/>'
            f'<line x1="{cx:.0f}" y1="{cy:.0f}" x2="{nx:.0f}" y2="{ny:.0f}" '
            f'stroke="{color}" stroke-width="2"/>'
            f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="2.5" fill="{color}"/>'
            f'<text x="{cx:.0f}" y="{cy + r / 2 + 14:.0f}" '
            f'text-anchor="middle" class="gaugev">{value}</text>'
            f'<text x="{cx:.0f}" y="{cy + r / 2 + 28:.0f}" '
            f'text-anchor="middle" class="wfl">{label}</text>')


def gauges_svg(p: dict[str, Any]) -> str:
    """三针仪表：NW Sharpe / 月换手 / Calmar."""
    sh = p.get("nw_sharpe_ls")
    tu = p.get("turnover_monthly_one_side")
    ca = p.get("calmar_ls")
    cells = [
        (160, 62, 44, min((sh or 0) / 3.0, 1.0), C_LS, "NW SHARPE",
         f"{sh:.2f}" if sh is not None else "—"),
        (460, 62, 44, min((tu or 0) / 1.0, 1.0), C_GOLD, "月换手(单边)",
         f"{(tu or 0) * 100:.0f}%"),
        (760, 62, 44, min((ca or 0) / 3.0, 1.0), C_G5, "CALMAR",
         f"{ca:.2f}" if ca is not None else "—"),
    ]
    out = ['<svg viewBox="0 0 920 118" width="100%" role="img" '
           'aria-label="tradability gauges">']
    out += [_gauge(*c) for c in cells]
    return "".join(out) + "</svg>"


# ---------------------------------------------------------------- B7 IC 寿命
def lifespan_bars(early: float | None, late: float | None,
                  last12: float | None, w: int = 360) -> str:
    """IC 寿命条：前半 vs 后半 + 最近 12 月."""
    hi = max(abs(x) for x in (early, late, last12) if x is not None) or 1e-9

    def bar(label, v, color):
        pct = int(abs(v or 0) / hi * 100)
        return (f'<div class="lsrow"><span class="wfl">{label}</span>'
                f'<div class="lsbar"><div style="width:{max(pct, 2)}%;'
                f'background:{color}"></div></div>'
                f'<span class="rv">{v:+.4f}</span></div>')

    return (bar("前半样本均值 IC", early, C_DIM)
            + bar("后半样本均值 IC", late, C_LS)
            + bar("最近 12 月 IC", last12, C_GOLD))


# ---------------------------------------------------------------- B8 相关矩阵
def corr_matrix_svg(navs: dict[str, list[float]]) -> str:
    """幸存者净值月收益相关矩阵（诚实展示同族高相关）."""

    def pearson(a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n < 3:
            return float("nan")
        ma, mb = sum(a[:n]) / n, sum(b[:n]) / n
        cov = sum((x - ma) * (y - mb) for x, y in zip(a[:n], b[:n]))
        va = math.sqrt(sum((x - ma) ** 2 for x in a[:n]))
        vb = math.sqrt(sum((y - mb) ** 2 for y in b[:n]))
        return cov / (va * vb) if va and vb else float("nan")

    ids = list(navs)
    n = len(ids)
    if not n:
        return ""
    cell = 62
    w = n * cell + 150
    out = [f'<svg viewBox="0 0 {w} {n * cell + 8}" width="{w}" '
           'role="img" aria-label="correlation matrix">']
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            r = pearson(navs[a], navs[b])
            t = max(0.0, min(1.0, (r + 1) / 2))
            color = C_GOLD if r > 0.7 else (C_LS if r > 0.3 else C_DIM)
            x, y = 120 + j * cell, i * cell + 4
            out.append(f'<rect x="{x}" y="{y}" width="{cell - 4}" '
                       f'height="{cell - 4}" rx="5" fill="{color}" '
                       f'opacity="{0.25 + 0.6 * t}"/>')
            out.append(f'<text x="{x + (cell - 4) / 2}" '
                       f'y="{y + (cell - 4) / 2 + 4}" text-anchor="middle" '
                       f'class="corrv">{r:.2f}</text>')
        out.append(f'<text x="112" y="{i * cell + 4 + 26}" '
                   f'text-anchor="end" class="wfl">{a}</text>')
    for j, b in enumerate(ids):
        out.append(f'<text x="{120 + j * cell + 20}" y="{n * cell + 8}" '
                   f'text-anchor="middle" class="wfl">{b}</text>')
    return "".join(out) + "</svg>"


# ---------------------------------------------------------------- A1 推理流
def trace_flow_html(lines: list[str], by_char: bool = False) -> str:
    """推理流：默认每行一条逐行浮现；by_char=True 时逐字符（短场景）."""
    import html as _h
    out = ['<div class="trace">']
    delay = 0
    for line in lines:
        if by_char:
            spans = []
            for ch in line:
                spans.append(f'<span style="animation-delay:'
                             f'{delay}ms">{_h.escape(ch)}</span>')
                delay += 14
            out.append('<div class="tline">' + "".join(spans) + "</div>")
        else:
            out.append(f'<div class="tline"><span '
                       f'style="animation-delay:{delay}ms">'
                       f'{_h.escape(line)}</span></div>')
            delay += 90
    out.append('<div class="tline"><span style="animation-delay:'
               f'{delay + 120}ms">▊</span></div>')
    return "".join(out) + "</div>"


def ecg_svg(w: int = 120, h: int = 28) -> str:
    beat = "0,14 10,14 14,6 18,22 22,2 26,20 30,14 44,14 52,10 58,14"
    pts = []
    for rep in range(6):
        base = rep * (w // 5)
        pts += [(base + int(x) * (w // 5) // 62, y) for x, y in
                ((int(a), int(b)) for a, b in (p.split(",") for p in beat.split()))]
    poly = " ".join(f"{min(x, w - 2)},{y}" for x, y in pts)
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<polyline points="{poly}" fill="none" stroke="{C_G5}" '
            'stroke-width="1.5" class="ecgline"/>'
            f'<circle r="2.5" fill="{C_G5}" class="ecgdot">'
            f'<animateMotion dur="3.2s" repeatCount="indefinite" '
            f'path="M{poly.replace(chr(44), chr(32))}"/></circle></svg>')


# ---------------------------------------------------------------- A3 粒子流
def dataflow_svg(w: int = 1000, h: int = 56, n_bars: int = 90,
                 seed: int = 7) -> str:
    """底部数据流：行情粒子流向中央引擎，输出端金色粒子."""
    import random
    rnd = random.Random(seed)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" '
           'class="dataflow" aria-hidden="true">']
    grp = []
    for i in range(n_bars):
        x = i * w / n_bars
        bh = 4 + rnd.random() * (h * 0.7)
        grp.append(f'<rect x="{x:.0f}" y="{h - bh:.0f}" width="2.5" '
                   f'height="{bh:.0f}" rx="1" fill="{C_LS}" '
                   f'opacity="{0.25 + rnd.random() * 0.5:.2f}"/>')
    # 两份实现无缝循环
    out.append('<g class="dflow">')
    out.append("".join(grp))
    out.append(f'<g transform="translate({w},0)">{"".join(grp)}</g>')
    out.append("</g>")
    # 中央引擎徽标 + 输出金粒子
    cx = w / 2
    out.append(f'<rect x="{cx - 26:.0f}" y="{h / 2 - 13:.0f}" width="52" '
               f'height="26" rx="6" fill="#111722" stroke="{C_GOLD}" '
               f'stroke-width="1.4"/>')
    out.append(f'<text x="{cx:.0f}" y="{h / 2 + 4:.0f}" text-anchor="middle" '
               f'class="wfl" fill="{C_GOLD}">ENGINE</text>')
    for k, dx in enumerate((-10, 0, 10)):
        out.append(f'<circle cx="{cx + 40 + dx * 4:.0f}" '
                   f'cy="{h / 2 + (k - 1) * 7:.0f}" r="2.6" fill="{C_GOLD}">'
                   f'<animate attributeName="opacity" values="0.2;1;0.2" '
                   f'dur="{1.6 + k * 0.4:.1f}s" repeatCount="indefinite"/></circle>')
    return "".join(out) + "</svg>"


# ---------------------------------------------------------------- A5 指纹墙
def fingerprint_badge(ic_series: list[dict[str, Any]]) -> str:
    """双实现一致性徽章（悬浮 title 给逐月明细摘要）."""
    pairs = [(m.get("ic_a"), m.get("ic_b")) for m in ic_series]
    same = sum(1 for a, b in pairs
               if a is not None and b is not None and abs(a - b) < 1e-12)
    n = len(pairs)
    if not n:
        return ""
    ok = same == n
    return (f'<span class="badge {"b-dual" if ok else "b-pend"}" '
            f'title="双实现逐月逐位一致 {same}/{n}（A/B 两套实现'
            f'独立计算 IC，逐月完全一致）">Dual-Impl Verified '
            f"({same}/{n})</span>")


def fingerprint_svg(ic_series: list[dict[str, Any]],
                    w: int = 640, h: int = 46) -> str:
    """双实现指纹墙：每月两枚点（A/B 实现），全绿=逐月一致."""
    n = len(ic_series)
    if not n:
        return ""
    cw = w / n
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
           'aria-label="dual-implementation fingerprint">']
    for i, m in enumerate(ic_series):
        same = True
        if "ic_a" in m and "ic_b" in m and m["ic_a"] is not None \
                and m["ic_b"] is not None:
            same = abs(m["ic_a"] - m["ic_b"]) < 1e-12
        color = C_G5 if same else C_G1
        x = i * cw
        out.append(f'<rect x="{x:.1f}" y="6" width="{max(cw - 1, 1):.1f}" '
                   f'height="14" rx="1.5" fill="{color}" opacity="0.8"/>')
        out.append(f'<rect x="{x:.1f}" y="25" width="{max(cw - 1, 1):.1f}" '
                   f'height="14" rx="1.5" fill="{color}" opacity="0.45"/>')
    return "".join(out) + "</svg>"


# ---------------------------------------------------------------- A7 并行赛道
def race_svg(w: int = 640, h: int = 120, lanes: int = 4,
             speedup: str = "18.1×") -> str:
    """并行赛道：worker 方块错峰冲线."""
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
           'aria-label="parallel race">']
    for i in range(lanes):
        y = 14 + i * (h - 20) / lanes
        out.append(f'<line x1="8" y1="{y:.0f}" x2="{w - 60}" y2="{y:.0f}" '
                   'stroke="#1f2733" stroke-width="1.4" '
                   'stroke-dasharray="3,5"/>')
        out.append(f'<text x="{w - 54}" y="{y + 4:.0f}" class="wfl">'
                   f'w{i + 1}</text>')
        delay = i * 240
        out.append(f'<rect x="10" y="{y - 6:.0f}" width="26" height="12" '
                   f'rx="3" fill="{C_LS}" class="racer" '
                   f'style="animation-delay:{delay}ms"/>')
    out.append(f'<text x="{w - 10}" y="14" text-anchor="end" '
               f'class="ygn">{speedup}</text>')
    return "".join(out) + "</svg>"


# ================================================================ v4 组件
def factor_expr(fid: str) -> str:
    """因子的等宽伪表达式标签（与 build 实现一一对应，rank=五分位隐式排序）."""
    import re as _re
    m = _re.fullmatch(r"gap_sum_(\d+)", fid)
    if m:
        w = m.group(1)
        return f"rank(ts_sum(ln(open/close[-1]), {w}))"
    m = _re.fullmatch(r"dist_high_(\d+)", fid)
    if m:
        return f"rank(close/ts_max(close,{m.group(1)}) - 1)"
    m = _re.fullmatch(r"mom_(\d+)_(\d+)", fid)
    if m:
        return f"rank(cum_ret(t-{m.group(2)}) - cum_ret(t-{m.group(1)}))"
    m = _re.fullmatch(r"vol_(\d+)", fid)
    if m:
        return f"rank(-ts_std(ret,{m.group(1)}))"
    m = _re.fullmatch(r"rev_(\d+)", fid)
    if m:
        return f"rank(-ts_sum(ret,{m.group(1)}))"
    return f"rank({fid})"


def kpi_strip(p: dict[str, Any], bench_ann: float | None = None) -> str:
    """一票否决级 6 硬指标条 + vs 基准差值微标（v4 #6/#8）."""
    def cell(k: str, v: str, pos: bool | None, bench: str = "",
             frac: float = 0.0, tip: str = "") -> str:
        cls = "pos" if pos else "neg" if pos is False else ""
        f = max(0.0, min(1.0, frac))
        tipattr = f' title="{tip}"' if tip else ""
        return (f'<div class="kpi"{tipattr}><div class="kpik">{k}</div>'
                f'<div class="kpival {cls}">{v}</div>'
                f'<div class="kmini"><i style="width:{f * 100:.0f}%;'
                f'background:{("#34C186" if pos else "#D0695A" if pos is False else "#7C8A9B")}"></i></div>'
                f'<div class="kpibench">{bench}</div></div>')

    ann = p.get("ann_ls_net")
    sh = p.get("nw_sharpe_ls")
    so = p.get("sortino_ls")
    mdd = p.get("max_drawdown_ls")
    tu = p.get("turnover_monthly_one_side")
    ca = p.get("calmar_ls")
    bench_line = ""
    if ann is not None and bench_ann is not None:
        d = ann - bench_ann
        c = "#34C186" if d >= 0 else "#D0695A"
        bench_line = (f'<b style="color:{c}">{d:+.1%}</b> vs 等权基准'
                      f"（{bench_ann:+.1%}）")
    cells = [
        cell("年化(费后)", f"{ann:+.1%}" if ann is not None else "—",
             (ann or 0) > 0, bench_line, frac=abs(ann or 0) / 0.35,
             tip="组合级模拟年化（等权五分位多空·月频·费后）。判据：>0 且经 2-50bps 费率扫描仍为正。"),
        cell("NW Sharpe", f"{sh:.2f}" if sh is not None else "—",
             (sh or 0) >= 1.0, "及格线 1.0", frac=(sh or 0) / 3.0,
             tip="Newey-West 修正的月收益 Sharpe（滞后 3）。判据：≥1 稳，≥1.5 强。"),
        cell("Sortino", f"{so:.2f}" if so is not None else "—",
             (so or 0) >= 1.4, "下行偏差口径", frac=(so or 0) / 4.0,
             tip="年化收益 / 下行偏差（只罚亏损月）。判据：≥1.4，比 Sharpe 更贴近回撤体感。"),
        cell("Max Drawdown", f"{mdd:.1%}" if mdd is not None else "—",
             False, "日频口径 · 主图为月频", frac=abs(mdd or 0) / 0.40,
             tip="净值峰谷最大回撤（日频）。红=风险提示，不随好坏变色。判据：<35% 可展示。"),
        cell("月换手(单边)", f"{tu * 100:.0f}%" if tu is not None else "—",
             None, "成本摊 20 日", frac=(tu or 0),
             tip="单边月换手率。越高对费率越敏感——配合下方费率滑块看。"),
        cell("Calmar", f"{ca:.2f}" if ca is not None else "—",
             (ca or 0) >= 1.0, "年化/|MDD|", frac=(ca or 0) / 2.5,
             tip="年化收益 / |最大回撤|。判据：≥1 表示每承受 1 单位回撤换 1 单位以上收益。"),
    ]
    return '<div class="kpis">' + "".join(cells) + "</div>"


def is_os_bar(ic_series: list[dict[str, Any]]) -> str:
    """IS(前 80%) vs OS(后 20%) 全局对照条（WorldQuant BRAIN 式，静态版）."""
    vals = [x.get("ic") for x in ic_series if x.get("ic") is not None]
    if len(vals) < 6:
        return ""
    n = len(vals)
    cut = max(3, int(n * 0.8))
    isv, osv = vals[:cut], vals[cut:]

    def stats(xs):
        m = sum(xs) / len(xs)
        sd = (sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)) ** 0.5
        icir = (m / sd) * (12 ** 0.5) if sd > 0 else 0.0
        return m, icir

    im, iir = stats(isv)
    om, oir = stats(osv)
    hold = oir / iir if abs(iir) > 1e-9 else 0.0
    return (f'<div class="isos"><div>'
            f'<div class="lab">IS 样本内（前 {cut} 月）</div>'
            f'<div class="val">{im:+.4f} <span style="font-size:13px;'
            f'color:#8B98A9">IC</span></div>'
            f'<div class="val" style="color:#4CC2FF">{iir:+.2f} '
            f'<span style="font-size:13px;color:#8B98A9">ICIR(年化)</span>'
            f"</div></div><div>"
            f'<div class="lab">OS 样本外（后 {n - cut} 月）</div>'
            f'<div class="val" style="color:#34C186">{om:+.4f} '
            f'<span style="font-size:13px;color:#8B98A9">IC</span></div>'
            f'<div class="val" style="color:#34C186">{oir:+.2f} '
            f'<span style="font-size:13px;color:#8B98A9">ICIR(年化)'
            f"</span></div></div>"
            f'<div><div class="lab">OS 保持率</div>'
            f'<div class="val" style="color:#E0B04B">{hold:.0%}</div>'
            f'<div class="sub" style="font-size:11.5px;color:#5C6B7D">'
            f"OS ICIR / IS ICIR（不藏衰减）</div></div></div>")


def radar_svg(scores: dict[str, tuple[float, str]], w: int = 340,
              h: int = 262) -> str:
    """六维风控雷达（半透明多边形），scores={维度: (0-1分, 显示值)}."""
    keys = list(scores)
    if len(keys) < 3:
        return ""
    cx, cy, r = w / 2, h / 2 + 6, min(w, h) / 2 - 34
    import math as _m
    n = len(keys)
    ang = lambda i: -_m.pi / 2 + i * 2 * _m.pi / n

    def pt(i, frac):
        a = ang(i)
        return cx + r * frac * _m.cos(a), cy + r * frac * _m.sin(a)

    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
           'aria-label="risk radar">']
    for ring in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{pt(i, ring)[0]:.0f},{pt(i, ring)[1]:.0f}"
                       for i in range(n))
        out.append(f'<polygon points="{pts}" fill="none" '
                   'stroke="rgba(255,255,255,.07)" stroke-width="1"/>')
    for i in range(n):
        x, y = pt(i, 1.0)
        out.append(f'<line x1="{cx:.0f}" y1="{cy:.0f}" x2="{x:.0f}" '
                   f'y2="{y:.0f}" stroke="rgba(255,255,255,.07)"/>')
        lx, ly = pt(i, 1.22)
        anchor = "middle"
        if lx > cx + 8:
            anchor = "start"
        elif lx < cx - 8:
            anchor = "end"
        out.append(f'<text x="{lx:.0f}" y="{ly:.0f}" '
                   f'text-anchor="{anchor}" class="radarlab">'
                   f"{keys[i]}</text>")
        vx, vy = pt(i, 1.22)
        out.append(f'<text x="{vx:.0f}" y="{vy + 11:.0f}" '
                   f'text-anchor="{anchor}" class="radargv">'
                   f'{scores[keys[i]][1]}</text>')
    poly = " ".join(f"{pt(i, max(0.04, min(1.0, scores[k][0])))[0]:.1f},"
                    f"{pt(i, max(0.04, min(1.0, scores[k][0])))[1]:.1f}"
                    for i, k in enumerate(keys))
    out.append(f'<polygon points="{poly}" fill="rgba(63,214,143,.16)" '
               'stroke="#34C186" stroke-width="1.8"/>')
    for i, k in enumerate(keys):
        x, y = pt(i, max(0.04, min(1.0, scores[k][0])))
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="2.6" '
                   'fill="#34C186"/>')
    return "".join(out) + "</svg>"


def monthly_heatmap_svg(months: list[str], rets: list[float],
                        w: int = 680) -> str:
    """月度收益热力矩阵（年 × 12 月，珊瑚→灰→翡翠）."""
    if not months:
        return ""
    years = sorted({m[:4] for m in months})
    grid: dict[tuple[str, int], float] = {}
    for m, r in zip(months, rets):
        grid[(m[:4], int(m[5:7]))] = r
    hi = max(abs(r) for r in rets) or 1e-9
    cw, chh, x0, y0 = 46, 22, 44, 6
    h = y0 + len(years) * chh + 18

    def cellcolor(r: float) -> str:
        t = r / hi
        if t >= 0.55:
            return "heatmax"
        if t > 0.12:
            return "heathi"
        if t > -0.12:
            return "heatmid"
        if t > -0.55:
            return "heatlo"
        return "heatmax" if False else "heatlo2"

    w += 74  # 年度合计列
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
           'aria-label="monthly heatmap">']
    out.append(f'<defs><linearGradient id="neggrad">'
               '<stop offset="0" stop-color="#D0695A" stop-opacity=".55"/>'
               '<stop offset="1" stop-color="#8A3A32" stop-opacity=".9"/>'
               "</linearGradient></defs>")
    for mi in range(13):
        x = x0 + mi * cw
        lab = "合计" if mi == 12 else f"{mi + 1}月"
        out.append(f'<text x="{x + cw / 2:.0f}" y="{y0 + 10}" '
                   f'text-anchor="middle" class="heaty">{lab}</text>')
    for yi, y in enumerate(years):
        yy = y0 + 14 + yi * chh
        out.append(f'<text x="{x0 - 6}" y="{yy + 14}" '
                   f'text-anchor="end" class="heaty">{y}</text>')
        tot = 1.0
        n_m = 0
        for mi in range(12):
            r = grid.get((y, mi + 1))
            x = x0 + mi * cw
            if r is None:
                out.append(f'<rect x="{x}" y="{yy}" width="{cw - 2}" '
                           f'height="{chh - 2}" rx="3" fill="#151A22" '
                           f'fill-opacity="0.5" class="heatcell"/>')
                continue
            tot *= (1.0 + r)
            n_m += 1
            t = r / hi
            if t >= 0:
                op = 0.15 + 0.75 * min(1.0, t / 0.6)
                fill = f'fill="#34C186" fill-opacity="{op:.2f}"'
            else:
                op = 0.15 + 0.75 * min(1.0, -t / 0.6)
                fill = f'fill="#D0695A" fill-opacity="{op:.2f}"'
            out.append(f'<rect x="{x}" y="{yy}" width="{cw - 2}" '
                       f'height="{chh - 2}" rx="3" {fill} class="heatcell">'
                       f"<title>{y}-{mi + 1:02d} {r * 100:+.1f}%</title>"
                       "</rect>")
            out.append(f'<text x="{x + (cw - 2) / 2:.0f}" '
                       f'y="{yy + (chh - 2) / 2 + 3:.0f}" class="heatv">'
                       f"{r * 100:+.1f}</text>")
        if n_m:
            yr = tot - 1.0
            x = x0 + 12 * cw
            c = "#34C186" if yr >= 0 else "#D0695A"
            out.append(f'<rect x="{x}" y="{yy}" width="{cw - 2}" '
                       f'height="{chh - 2}" rx="3" fill="{c}" '
                       f'fill-opacity="0.22" class="heatcell">'
                       f"<title>{y} 年度合计 {yr * 100:+.1f}%（{n_m} 月复合）"
                       "</title></rect>")
            out.append(f'<text x="{x + (cw - 2) / 2:.0f}" '
                       f'y="{yy + (chh - 2) / 2 + 3:.0f}" class="heatv" '
                       f'style="fill:{c}">{yr * 100:+.1f}</text>')
    return "".join(out) + "</svg>"


def rolling_ic_svg(ic_series: list[dict[str, Any]], win: int = 12,
                   w: int = 680, h: int = 150) -> str:
    """月 IC 柱（正绿负珊瑚）+ 12 月滚动均值线 + 零轴（v4 #15）."""
    vals = [x.get("ic") for x in ic_series if x.get("ic") is not None]
    if len(vals) < 4:
        return ""
    n = len(vals)
    m = max(abs(v) for v in vals) or 1e-9
    roll_max = max(abs(sum(vals[i - win:i]) / win)
                   for i in range(win, n + 1))
    m = max(m, roll_max * 1.15)
    half = (h - 26) / 2
    mid = 13 + half
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
           'aria-label="rolling IC">']
    bw = (w - 8) / n * 0.62
    step = (w - 8) / n
    for i, v in enumerate(vals):
        bh = abs(v) / m * half
        y = mid - bh if v >= 0 else mid
        cls = "rollbar-pos" if v >= 0 else "rollbar-neg"
        out.append(f'<rect x="{4 + i * step:.1f}" y="{y:.1f}" '
                   f'width="{bw:.1f}" height="{bh:.1f}" rx="1" '
                   f'class="{cls}"/>')
    line_pts = []
    for i in range(win - 1, n):
        seg = vals[max(0, i - win + 1):i + 1]
        mv = sum(seg) / len(seg)
        x = 4 + i * step + bw / 2
        line_pts.append(f"{x:.1f},{mid - mv / m * half:.1f}")
    out.append(f'<polyline points="{" ".join(line_pts)}" class="rollline"/>'
               f'<line x1="4" y1="{mid}" x2="{w - 4}" y2="{mid}" '
               'stroke="rgba(255,255,255,.22)" stroke-width="1"/>'
               f'<text x="6" y="10" class="wfl">月 IC 柱 · 金线={win} 月滚动均值 · 零轴=白线'
               f"</text>")
    return "".join(out) + "</svg>"


def sensitivity_grid(rows: list[dict[str, Any]]) -> str:
    """参数敏感性网格（费率×口径），rows=[{k, v, sub, pos}]（v4 #20 静态版）."""
    cells = []
    for r in rows:
        c = "#34C186" if r.get("pos", True) else "#D0695A"
        cells.append(f'<div class="senscell"><div class="sensk">'
                     f'{r["k"]}</div><div class="sensv" '
                     f'style="color:{c}">{r["v"]}</div>'
                     f'<div class="senssub">{r.get("sub", "")}</div></div>')
    return '<div class="sens">' + "".join(cells) + "</div>"
