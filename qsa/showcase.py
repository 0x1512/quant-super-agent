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
C_GOLD = "#ffc857"      # 幸存者（金）
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
    out = [f'<svg viewBox="0 0 {w} {h + uw_h + 26}" width="100%" '
           'role="img" aria-label="long-short NAV hero">']
    # 网格
    for gy in range(1, 4):
        y = pad_y = 4 + gy * (h - 8) / 4
        out.append(f'<line x1="4" y1="{y:.0f}" x2="{w - 4}" y2="{y:.0f}" '
                   'stroke="#1a2230" stroke-width="1"/>')
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
    # L-S 主线（发光：三层描边）
    pts = _poly(main_nav, w, lo, hi, h)
    for sw, op in ((7, 0.12), (3.5, 0.3), (2.2, 1.0)):
        out.append(f'<polyline points="{pts}" fill="none" stroke="{C_LS}" '
                   f'stroke-width="{sw}" opacity="{op}"/>')
    out.append(f'<circle cx="{w - 4:.0f}" cy="{4 + (1 - (main_nav[-1] - lo) / ((hi - lo) or 1)) * (h - 8):.1f}" '
               f'r="4" fill="{C_GOLD}"/>')
    # 终值徽章（B10）
    final = main_nav[-1]
    out.append(f'<text x="{w - 10}" y="20" text-anchor="end" '
               f'class="heroend">¥1,000,000 → ¥{final * 1e6:,.0f}'
               '</text>')
    out.append(f'<text x="8" y="{h - 8:.0f}" class="herolab">'
               f'{months[0]} — {months[-1]} · 费后模拟 · 灰虚线=等权基准'
               f' · 青光=多空 L-S · 浅青带=邻域 {len(band)} 窗口</text>')
    # 回撤水下（B3）
    uw = _underwater(main_nav)
    base = h + 8
    uw_pts = _poly(uw, w, min(uw), 0.0, uw_h, 4)
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
    return "".join(out) + "</svg>"


# ---------------------------------------------------------------- B4 年度增强
def yearly_gain_svg(yearly: list[tuple[str, float]],
                    w: int = 640, h: int = 120) -> str:
    hi = max(abs(r) for _, r in yearly) or 1e-9
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
           'aria-label="yearly gain">']
    bw = (w - 8) / max(1, len(yearly)) * 0.52
    gap = (w - 8) / max(1, len(yearly))
    for i, (y, r) in enumerate(yearly):
        x = 4 + i * gap
        bh = abs(r) / hi * (h / 2 - 22)
        color = C_G5 if r >= 0 else C_G1
        y0 = h / 2 - bh if r >= 0 else h / 2
        hot = ' filter="url(#glow)"' if r == max(x[1] for x in yearly) else ""
        out.append(f'<rect x="{x:.0f}" y="{y0:.0f}" width="{bw:.0f}" '
                   f'height="{max(bh, 2):.0f}" rx="3" fill="{color}" '
                   f'class="wfbar" style="animation-delay:{i * 100}ms"{hot}/>')
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
    cell = 44
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
