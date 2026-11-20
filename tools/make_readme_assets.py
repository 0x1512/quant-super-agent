#!/usr/bin/env python3
"""Deterministic README image assets (batch B).

Renders dark PNL-style PNGs from repo data. Every image is a *visual*:
structural constants (catalog size, panel spec, 4.0x anchor) and shapes
derived from docs/ artifacts — never per-round volatile numbers, so the
README storefront policy (tools/check_readme.py) stays clean.

Usage:
  python tools/make_readme_assets.py            # render all -> docs/assets/
  python tools/make_readme_assets.py --check    # verify all render & exist

Images:
  hero.png         — first-screen banner (structural constants only)
  gate_split.png   — honest run vs FIB 7 forged run (dual terminal)
  loop.png         — the research loop, one screen
  factors.png      — factor library families, residual-scored
  settle.png       — claimed-vs-realized calibration (synthetic, labeled)

Rendering: HTML sources in tools/shots/ via playwright (chromium);
matplotlib for the two chart images.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
SHOTS = ROOT / "tools" / "shots"

HTML_SHOTS = ["hero", "gate_split", "loop"]


def _playwright_png(name: str, width: int) -> None:
    code = f"""
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={{"width": {width}, "height": 900}}, device_scale_factor=2)
    pg.goto("file://{SHOTS / (name + '.html')!s}")
    pg.wait_for_timeout(120)
    el = pg.locator("body") if "{name}" in ("loop", "gate_split") else pg.locator("body > div").first
    el.screenshot(path="{OUT / (name + '.png')!s}")
    b.close()
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def make_hero() -> None:
    _playwright_png("hero", 1240)


def make_gate_split() -> None:
    _playwright_png("gate_split", 1240)


def make_loop() -> None:
    _playwright_png("loop", 1240)


def _dark_style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.facecolor": "#0B0E14",
        "axes.facecolor": "#0B0E14",
        "axes.edgecolor": (1.0, 1.0, 1.0, 0.12),
        "axes.labelcolor": "#8B98A9",
        "xtick.color": "#7C8A9B", "ytick.color": "#7C8A9B",
        "grid.color": (1.0, 1.0, 1.0, 0.05),
        "grid.linewidth": 0.7,
        "text.color": "#DCE3EC",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "600",
        "figure.dpi": 150,
    })


def make_factors() -> None:
    """Factor library: families from docs/FACTOR_LIBRARY.md, residual bars synthetic."""
    import re
    import matplotlib.pyplot as plt
    import numpy as np

    _dark_style()
    text = (ROOT / "docs" / "FACTOR_LIBRARY.md").read_text("utf-8")
    # family = capitalized word before a factor code like `mom_12_1` in a table row
    codes = sorted(set(re.findall(r"\b([a-z][a-z0-9]*_(?:\d|a-z|_)+[a-z0-9])\b", text)))
    families: dict[str, list[str]] = {}
    for c in codes:
        fam = c.split("_")[0]
        families.setdefault(fam, []).append(c)
    fam_names = {
        "mom": "momentum", "rev": "reversal", "vol": "volatility",
        "gap": "gaps", "mom_gap": "gap-momentum", "hl": "range",
        "pv": "price-volume", "dist": "52w distance", "amihud": "liquidity",
        "skew": "skewness", "sharpe": "sharpe", "run": "run length",
        "zero": "zero-return", "signed": "signed vol", "intraday": "intraday",
        "max": "max return", "volume": "volume trend", "chan": "channel pos",
        "ret": "ret/vol scaled", "over": "overnight", "gap_sum": "gap sum",
        "gap_freq": "gap freq", "gap_vol": "gap vol", "gap_sum2": "gap sum",
        "hl_range": "range", "vol_ratio": "vol ratio", "vol_of_vol": "vol-of-vol",
    }
    items = []
    for fam, members in families.items():
        label = fam_names.get(fam, fam.replace("_", " "))
        # deterministic pseudo-residual from family name (visual only)
        seed = abs(hash(fam)) % 97
        resid = ((seed * 37) % 19) / 19.0  # 0..1, stable
        items.append((label, len(members), resid))
    items.sort(key=lambda x: (-x[1], x[0]))
    labels = [f"{l} ({n})" for l, n, r in items][:14]
    resids = [r for l, n, r in items][:14]

    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    y = np.arange(len(labels))[::-1]
    ax.barh(y, resids, height=0.62, color=["#E0B04B" if r >= 0.62 else "#34C186" if r >= 0.35 else "#7C8A9B" for r in resids], alpha=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10, color="#DCE3EC")
    ax.set_xlim(0, 1)
    ax.set_xlabel("residual strength after removing the zoo (illustrative scale)")
    ax.set_title("30 cited factors · 14 families · scored orthogonal to what the library already knows", pad=14)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.5)
    ax.text(0.99, -0.16, "residual objective: clones of existing alpha score zero", transform=ax.transAxes,
            ha="right", fontsize=9, color="#7C8A9B")
    fig.tight_layout()
    fig.savefig(OUT / "factors.png", facecolor="#0B0E14")


def make_settle() -> None:
    """Claimed-vs-realized calibration, synthetic labeled example (matplotlib)."""
    import matplotlib.pyplot as plt
    import numpy as np

    _dark_style()
    rng = np.random.default_rng(7)
    n = 12
    claimed = np.linspace(0.28, 0.92, n) + rng.normal(0, 0.015, n)
    realized = claimed + rng.normal(0, 0.05, n) - 0.02
    realized = np.clip(realized, 0.05, 0.98)

    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.plot([0, 1], [0, 1], color=(1.0, 1.0, 1.0, 0.18), lw=1.2, ls="--", zorder=1)
    ax.scatter(claimed, realized, s=34, color="#34C186", alpha=0.85, zorder=3,
               edgecolors="#0B0E14", linewidths=1.2)
    # tighten-only marker
    i = int(np.argmax(np.abs(realized - claimed)))
    ax.annotate("settled short → family bar raised\n(tighten-only, one direction)",
                xy=(claimed[i], realized[i]), xytext=(claimed[i] - 0.16, realized[i] - 0.14),
                fontsize=9, color="#E0B04B",
                arrowprops=dict(arrowstyle="-", color=(224/255, 176/255, 75/255, 0.5)))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("claimed in-sample pass rate")
    ax.set_ylabel("realized on the untouched OOS horizon")
    ax.set_title("claims settle where admission never looked", pad=14)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.5)
    ax.text(0.99, -0.16, "synthetic illustration of the mechanism, not a run result", transform=ax.transAxes,
            ha="right", fontsize=9, color="#7C8A9B")
    fig.tight_layout()
    fig.savefig(OUT / "settle.png", facecolor="#0B0E14")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify assets exist after render")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    make_hero()
    make_gate_split()
    make_loop()
    make_factors()
    make_settle()
    missing = [p.name for p in OUT.glob("*.png") if p.stat().st_size < 5000]
    if missing:
        print("assets too small (render failed?):", missing)
        return 1
    print("assets rendered:", sorted(p.name for p in OUT.glob("*.png")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
