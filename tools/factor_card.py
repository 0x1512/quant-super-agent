#!/usr/bin/env python3
"""factor_card — 生成因子测试表现卡（docs/cards/<id>.md）.

用法：
    python tools/factor_card.py --ids gap_sum_252,gap_sum_378,mom_504_63
    python tools/factor_card.py --ids all24            # 库内 24 因子全卡

id 解析：库内 id 走 factorzoo.build_catalog()；邻域扫描变体
（gap_sum_N / dist_high_N / mom_F_S / vol_N / rev_N）由内置工厂
重建，与 docs/loops/scan_momentum.json 同参。

判决链双口径：stage2 显示**冻结门**（icir>1.0 月度）判决；
拟议 stage2-v2（年化 1.0 = 月度 0.2887）单独一行，标注"待
拍板"，永不冒充已入册。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qsa import __version__ as QSA_VERSION  # noqa: E402

from qsa import factorzoo                      # noqa: E402
from qsa.admission import STAGE2_ADMISSION, evaluate as adm_eval  # noqa: E402
import qsa.showcase as _showcase
from qsa.factorcard import (render_card, render_index,
                            render_index_html)  # noqa: E402
from qsa.ingest import ingest_csv              # noqa: E402
from qsa.matrix import evaluate_factor_fast    # noqa: E402
from qsa.matrix import HAVE_NUMPY               # noqa: E402
from qsa.pnl import longshort_pnl               # noqa: E402
from qsa.snapshot import load_closes, load_opens, load_volumes  # noqa: E402
from qsa.walkforward import walkforward_verdict  # noqa: E402

# 拟议 stage2-v2：年化 ICIR 1.0（= 月度 0.2887）；唯一改动点
STAGE2_V2 = {**STAGE2_ADMISSION,
             "thresholds": {**STAGE2_ADMISSION["thresholds"],
                            "icir": {"op": ">", "value": 0.2887}}}

SCAN_N = None      # 从 scan_momentum.json 读族计数（多重检验脚注）


# -- 邻域变体工厂（与 docs/loops/scan_momentum.json 同参） ------------------

def _series(inp, key):
    return factorzoo.series_of(inp[key], inp["dates"])


def spec_gap(win):
    def build(inp):
        cs, os_ = _series(inp, "closes"), _series(inp, "opens")
        gaps = factorzoo.overnight_of(os_, cs)
        return {tk: factorzoo.rolling_sum(g, win) for tk, g in gaps.items()}
    return {"id": f"gap_sum_{win}", "source": "neighborhood-scan",
            "desc": f"{win} 日累计隔夜缺口（overnight momentum）",
            "build": build, "flip": False}


def spec_dist(win):
    def build(inp):
        cs = _series(inp, "closes")
        out = {}
        for tk, xs in cs.items():
            mx = factorzoo.rolling_max(xs, win)
            out[tk] = [None if (m is None or not c) else c / m - 1.0
                       for c, m in zip(xs, mx)]
        return out
    return {"id": f"dist_high_{win}", "source": "neighborhood-scan",
            "desc": f"{win} 日距最高价（near-high = 高分）",
            "build": build, "flip": False}


def spec_mom(form, skip):
    def build(inp):
        rs = factorzoo.returns_of(_series(inp, "closes"))
        rows = {}
        for tk, r in rs.items():
            cum = factorzoo._cumulative([0.0 if x is None else x for x in r])
            out = []
            for i in range(len(r)):
                v = None
                if i >= form and i - skip >= 0:
                    lo, hi = cum[i - form], cum[i - skip]
                    if lo is not None and hi is not None:
                        v = hi - lo
                out.append(v)
            rows[tk] = out
        return rows
    return {"id": f"mom_{form}_{skip}", "source": "neighborhood-scan",
            "desc": f"{form} 日形成 / skip {skip} 日动量",
            "build": build, "flip": False}


def spec_vol(win):
    def build(inp):
        rs = factorzoo.returns_of(_series(inp, "closes"))
        return {tk: factorzoo.rolling_std(r, win) for tk, r in rs.items()}
    return {"id": f"vol_{win}", "source": "neighborhood-scan",
            "desc": f"{win} 日波动率（低波 = 高分）",
            "build": build, "flip": True}


def spec_rev(win):
    def build(inp):
        rs = factorzoo.returns_of(_series(inp, "closes"))
        return {tk: factorzoo.rolling_sum(r, win) for tk, r in rs.items()}
    return {"id": f"rev_{win}", "source": "neighborhood-scan",
            "desc": f"{win} 日反转（低收益 = 高分）",
            "build": build, "flip": True}


def resolve_spec(fid: str, catalog: dict) -> dict | None:
    """库内 id → catalog；邻域变体 id → 工厂重建."""
    if fid in catalog:
        return catalog[fid]
    m = re.fullmatch(r"gap_sum_(\d+)", fid)
    if m:
        return spec_gap(int(m.group(1)))
    m = re.fullmatch(r"dist_high_(\d+)", fid)
    if m:
        return spec_dist(int(m.group(1)))
    m = re.fullmatch(r"mom_(\d+)_(\d+)", fid)
    if m:
        return spec_mom(int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r"vol_(\d+)", fid)
    if m:
        return spec_vol(int(m.group(1)))
    m = re.fullmatch(r"rev_(\d+)", fid)
    if m:
        return spec_rev(int(m.group(1)))
    return None


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, timeout=5
        ).stdout.strip() or "—"
    except Exception:
        return "—"


def family_of(fid: str) -> str:
    """族归类（展示用；前缀匹配，未命中归 misc）."""
    if "gap" in fid or "overnight" in fid or "intraday" in fid:
        return "overnight"
    if "dist" in fid or "chan" in fid:
        return "near-high"
    if fid.startswith("mom_"):
        return "momentum"
    if "rev" in fid or "run_length" in fid or "ret_vol" in fid:
        return "reversal"
    if "skew" in fid or "max_ret" in fid:
        return "skew"
    if "amihud" in fid or "pv_corr" in fid or "volume" in fid \
            or "vol_ratio" in fid or "signed_vol" in fid:
        return "volume"
    if "vol" in fid or "hl_range" in fid or "sharpe" in fid:
        return "volatility"
    if "zero_ret" in fid:
        return "friction"
    return "misc"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids",
                    help="逗号分隔 id；all24 = 库内全因子")
    ap.add_argument("--index", action="store_true",
                    help="生成总览页 INDEX.md（库内24 + 扫描变体全集合）")
    ap.add_argument("--out", default="docs/cards")
    args = ap.parse_args()
    if not args.ids and not args.index:
        ap.error("need --ids or --index")

    fixture = ROOT / "examples/data"
    with tempfile.TemporaryDirectory() as td:
        snap = Path(td) / "snap"
        ingest_csv(fixture / "ashare_top300_main.csv", snap,
                   volume_col="volume", open_col="open",
                   snapshot_id="cards", meta_dir=fixture / "replication_meta")
        closes = load_closes(snap)
        inputs = {"closes": closes, "opens": load_opens(snap),
                  "volumes": load_volumes(snap),
                  "dates": sorted({d for r in closes.values() for d in r})}

        catalog_list = factorzoo.build_catalog()
        catalog = {s["id"]: s for s in catalog_list}
        if args.ids == "all24":
            ids = sorted(catalog)
        elif args.ids:
            ids = [x.strip() for x in args.ids.split(",") if x.strip()]
        else:
            ids = []

        scan_fp = ROOT / "docs/loops/scan_momentum.json"
        scan_n = None
        if scan_fp.exists():
            try:
                scan_n = json.loads(scan_fp.read_text()).get("n_variants")
            except (ValueError, OSError):
                scan_n = None

        out_dir = ROOT / args.out
        out_dir.mkdir(parents=True, exist_ok=True)

        if args.index:
            scan_ids = ([f"gap_sum_{w}" for w in (63, 126, 189, 252, 378, 504)]
                        + [f"dist_high_{w}" for w in (63, 126, 189, 252, 378, 504)]
                        + [f"mom_{f}_{s}" for f in (126, 189, 252, 378, 504)
                           for s in (0, 21, 63)]
                        + [f"vol_{w}" for w in (10, 20, 60, 120)]
                        + [f"rev_{w}" for w in (5, 10, 21, 63)])
            ids = sorted(catalog) + scan_ids
            rows, ics, pnls = [], {}, {}
            t_start = time.perf_counter()
            for fid in ids:
                spec = resolve_spec(fid, catalog)
                row = evaluate_factor_fast(spec, inputs)
                sig = factorzoo._finalize(spec["build"](inputs),
                                          inputs["dates"],
                                          spec.get("flip", False))
                ic = factorzoo.monthly_ic_series(closes, inputs["dates"], sig)
                ics[fid] = ic
                wf, _ = walkforward_verdict(ic)
                derived = dict(row)
                derived["n_dates"] = row.get("n_months")
                tr, oo = row.get("train_ic"), row.get("oos_ic")
                if (isinstance(tr, (int, float)) and tr > 0
                        and isinstance(oo, (int, float))):
                    derived["ic_decay_ratio"] = oo / tr
                s2, _ = adm_eval(STAGE2_ADMISSION, derived)
                s2v2, _ = adm_eval(STAGE2_V2, derived)
                pnl = longshort_pnl(closes, inputs["dates"], sig)
                if pnl is not None:
                    pnls[fid] = pnl
                s1 = ("pass" if (row.get("oos_ic") or 0) > 0.03
                      else "fail")
                rows.append({
                    "id": fid, "family": family_of(fid),
                    "oos_ic": row.get("oos_ic"),
                    "icir_a": (row["icir"] * (12 ** 0.5)
                               if row.get("icir") is not None else 0.0),
                    "tmb": row.get("top_minus_bottom") or 0.0,
                    "pos_share": row.get("ic_positive_share") or 0.0,
                    "s1": s1, "s2": s2, "s2v2": s2v2, "wf": wf,
                    "both": s2v2 == "pass" and wf == "pass",
                    "ann_ls": (pnl or {}).get("ann_ls_net"),
                    "sharpe_ls": (pnl or {}).get("nw_sharpe_ls"),
                })
            meta = {"title": "现有全部因子效果",
                    "snap": "fixture A股Top300主表",
                    "n_months": "41–58", "n_tickers": 300,
                    "engine": f"qsa v{QSA_VERSION}",
                    "backend": ("numpy" if HAVE_NUMPY
                                else "stdlib"),
                    "elapsed_s": f"{time.perf_counter() - t_start:.1f}s",
                    "commit": _git_sha()}
            libs = [r for r in rows if r["id"] in catalog]
            scans = [r for r in rows if r["id"] not in catalog]
            dup = sum(1 for s in scans
                      if any(abs((s["oos_ic"] or 0) - (l["oos_ic"] or 0)) < 1e-9
                             and abs(s["icir_a"] - l["icir_a"]) < 1e-9
                             for l in libs))
            if dup:
                meta["dedup_note"] = (f"库内名与扫描名同参重合 {dup} 对"
                                      "（双实现数字一致，交叉验证）")
            # v4 敏感性 + v5 JS 网格：主幸存者（与 render 同选法）费率扫描
            surv_rows = [r for r in rows if r.get("both")]
            hero_row = (max(surv_rows, key=lambda x: x.get("ann_ls")
                            if x.get("ann_ls") is not None else -9)
                        if surv_rows else None)
            sens = []
            fee_grid: dict[str, dict] = {}
            fee_curve_cache: dict[int, dict] = {}
            if hero_row:
                hspec = resolve_spec(hero_row["id"], catalog)
                hsig = factorzoo._finalize(hspec["build"](inputs),
                                           inputs["dates"],
                                           hspec.get("flip", False))
                for bps in (2, 8, 20, 50):
                    sp = fee_curve_cache.get(bps)
                    if sp is None:
                        sp = longshort_pnl(closes, inputs["dates"], hsig,
                                           fee_one_side=bps / 10000.0)
                        fee_curve_cache[bps] = sp
                    if sp is None:
                        continue
                    sens.append({
                        "k": {2: "费率 万0.2（2bps）",
                              8: "费率 万0.8（8bps，基准）",
                              20: "费率 万2（20bps）",
                              50: "费率 万5（50bps，压力）"}[bps],
                        "v": f"{sp['ann_ls_net']:+.1%}",
                        "sub": (f"Sharpe {sp['nw_sharpe_ls']:.2f}"
                                f" · MDD {sp['max_drawdown_ls']:.0%}"),
                        "pos": (sp["ann_ls_net"] or 0) > 0})
                # JS 滑块网格：2–50bps 步进 2（后端精确口径）
                for bps in range(2, 51, 2):
                    sp = fee_curve_cache.get(bps)
                    if sp is None:
                        sp = longshort_pnl(closes, inputs["dates"], hsig,
                                           fee_one_side=bps / 10000.0)
                        fee_curve_cache[bps] = sp
                    if sp is None:
                        continue
                    ls = [round(x, 6) for x in sp["ls_monthly"]
                          if x is not None]
                    if len(ls) != len(sp["ls_monthly"]):
                        continue
                    fee_grid[str(bps)] = {
                        "ls": ls,
                        "ann": round(sp["ann_ls_net"] or 0.0, 5),
                        "sharpe": round(sp["nw_sharpe_ls"] or 0.0, 4),
                        "mdd": round(sp["max_drawdown_ls"] or 0.0, 5)}
            # v5 JS 增强数据：幸存者月序列 + 基准 + 费率网格
            jsdata = {}
            if hero_row:
                fams_mech = {f: m for f, m in
                             ((fam, _showcase.FAM_MECH.get(fam, ""))
                              for fam in {r.get("family")
                                          for r in rows})}
                fjs = {}
                for r in surv_rows:
                    p = pnls.get(r["id"])
                    if not p or not p.get("ls_monthly"):
                        continue
                    ls = [round(x, 6) for x in p["ls_monthly"]
                          if x is not None]
                    if len(ls) != len(p["ls_monthly"]):
                        continue
                    sp0 = fee_curve_cache.get(8) if r is hero_row else None
                    fjs[r["id"]] = {
                        "months": p["months"],
                        "ls": ls,
                        "turnover": round(
                            p.get("turnover_monthly_one_side") or 0.0, 4),
                        "calmar": round(sp0["calmar_ls"]
                                        if sp0 and r is hero_row and
                                        sp0.get("calmar_ls") is not None
                                        else (p.get("calmar_ls") or 0.0), 3),
                        "expr": _showcase.factor_expr(r["id"]),
                        "mech": fams_mech.get(r.get("family"), "")}
                if fjs:
                    bm = pnls.get(hero_row["id"], {}).get("bench_monthly")
                    bench_ann = None
                    if bm:
                        v = 1.0
                        for x in bm:
                            v *= (1.0 + x)
                        bench_ann = (round(v ** (12.0 / len(bm)) - 1.0, 5)
                                     if v > 0 else None)
                    jsdata = {
                        "factors": fjs,
                        "hero": hero_row["id"],
                        "bench": [round(x, 6) for x in (bm or [])
                                  if x is not None],
                        "bench_ann": bench_ann,
                        "base_fee_bps": 8,
                        "fee": fee_grid}
            page = render_index(rows, meta)
            fp = out_dir / "INDEX.md"
            fp.write_text(page, encoding="utf-8")
            html = render_index_html(rows, meta, ics, pnls,
                                     extras={"sens": sens, "jsdata": jsdata})
            fh = out_dir / "overview.html"
            fh.write_text(html, encoding="utf-8")
            n_both = sum(1 for r in rows if r["both"])
            print(f"index -> {fp.relative_to(ROOT)}  "
                  f"({len(rows)} items, {n_both} both)")
            print(f"html   -> {fh.relative_to(ROOT)}  "
                  f"({fh.stat().st_size} bytes, no-JS static)")
            print(f"done: index 1/1")
            return 0

        made = []
        for fid in ids:
            spec = resolve_spec(fid, catalog)
            if spec is None:
                print(f"!! unknown id {fid} — skipped", file=sys.stderr)
                continue
            row = evaluate_factor_fast(spec, inputs)
            sig = factorzoo._finalize(spec["build"](inputs), inputs["dates"],
                                      spec.get("flip", False))
            ic = factorzoo.monthly_ic_series(closes, inputs["dates"], sig)
            wf, wf_detail = walkforward_verdict(ic)
            pnl = longshort_pnl(closes, inputs["dates"], sig)

            derived = dict(row)
            derived["n_dates"] = row.get("n_months")
            tr, oo = row.get("train_ic"), row.get("oos_ic")
            if (isinstance(tr, (int, float)) and tr > 0
                    and isinstance(oo, (int, float))):
                derived["ic_decay_ratio"] = oo / tr
            s2, reasons = adm_eval(STAGE2_ADMISSION, derived)
            s2v2, _ = adm_eval(STAGE2_V2, derived)

            meta = {"id": fid, "desc": spec["desc"], "source": spec["source"],
                    "scan_n": scan_n,
                    "verdicts": {
                        "stage1": ("pass" if (oo or 0) > 0.03 else "fail"),
                        "stage2": s2, "walk_forward": wf,
                        "status": "探索层（未冻结，不入册）",
                        "note": (f"stage2-v2（年化1.0口径）待拍板 → {s2v2}；"
                                 f"首个不满足：{reasons[-1][:72]}"
                                 if reasons else
                                 f"stage2-v2（年化1.0口径）待拍板 → {s2v2}")}}
            card = render_card(meta, row, wf_detail, ic, pnl=pnl)
            fp = out_dir / f"{fid}.md"
            fp.write_text(card, encoding="utf-8")
            made.append(str(fp.relative_to(ROOT)))
        for p in made:
            print(f"card -> {p}  ({Path(p).stat().st_size} bytes)")
        print(f"done: {len(made)}/{len(ids)}")
        return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
