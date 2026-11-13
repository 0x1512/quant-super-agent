"""Scenario A end-to-end: research-report replication, one command.

Pipeline (A10):
  1. Ingest the pinned real-data fixture (A-share top-300 by 2021-H1
     turnover, hfq-adjusted via the preclose chain) into a fingerprinted
     snapshot with pinned meta (monthly caps + industries).
  2. Register the pre-registered hypothesis BEFORE any computation (A8).
  3. Compute the overnight-gap factor in the sandbox (v3, truncated view)
     and the report-convention monthly block via the whitelisted
     evaluator (A3/A4/A5).
  4. Run the full verify gate: engine metrics + the replication block
     both recompute from the card; the pre-registered verdict is
     re-derived mechanically (A5/A8).
  5. Fabrication injection x3 (A7): metric edit / window swap / universe
     swap — each must be rejected by the gate with a named error; the
     ungated control (same edit, no gate) is recorded as the contrast.
  6. Settlement of the pre-registered claim on the 90-day tail (A9): the
     tail is real data that ARRIVED after the admission window; the
     extension is asserted row-by-row, and the ledger audit rebuilds
     everything from the pinned fixture.
  7. Write work/replication/report.md — numbers and prose are separate:
     every number in the report is machine-emitted; the prose states no
     number of its own.

Usage: python examples/run_replication.py [--data examples/data]
Offline and deterministic: a second run is byte-identical (fixed dates,
no timestamps, pure functions of the pinned fixture).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from qsa import admission, engine, registry, replication, settlement, snapshot, verify  # noqa: E402
from qsa.ingest import ingest_csv  # noqa: E402
from qsa.sandbox import run_factor  # noqa: E402
from qsa.snapshot import sha256_bytes  # noqa: E402

HYP_ID = "H-901"
EXP_ID = "E-901"
WINDOW = "20210701:20260630"


def _merged_csv(main_csv: Path, tail_csv: Path, out: Path) -> Path:
    rows = (main_csv.read_text(encoding="utf-8").splitlines()
            + tail_csv.read_text(encoding="utf-8").splitlines()[1:])
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO / "examples" / "data"))
    ap.add_argument("--work", default=str(REPO / "work" / "replication"))
    args = ap.parse_args(argv)
    data = Path(args.data)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    meta_dir = data / "replication_meta"
    main_csv = data / "ashare_top300_main.csv"
    tail_csv = data / "ashare_top300_tail.csv"
    for p in (main_csv, tail_csv, meta_dir):
        if not p.exists():
            print(f"missing fixture: {p} — run "
                  f"scripts/build_replication_fixture.py first")
            return 2

    # --- 1. snapshots (main = admission window; full = main + tail) -----
    snap_main = work / "snap_main"
    if not (snap_main / "MANIFEST.json").exists():
        info = ingest_csv(main_csv, snap_main, volume_col="volume",
                          open_col="open", snapshot_id="ashare-top300-main",
                          meta_dir=meta_dir)
    else:
        info = snapshot.fingerprint(snap_main)
    snap_full = work / "snap_full"
    if not (snap_full / "MANIFEST.json").exists():
        merged = _merged_csv(main_csv, tail_csv, work / "merged_full.csv")
        info_full = ingest_csv(merged, snap_full, volume_col="volume",
                               open_col="open",
                               snapshot_id="ashare-top300-main-tail",
                               meta_dir=meta_dir)
    else:
        info_full = snapshot.fingerprint(snap_full)

    # --- 2. pre-registration (A8: hypothesis before data) ---------------
    reg_path = work / "registry.jsonl"
    reg = registry.Registry.open(reg_path)
    h = {
        "schema": "hypothesis",
        "hyp_id": HYP_ID,
        "mechanism": (
            "Overnight gaps accumulate informed positioning pressure; stocks "
            "with large recent |ln(open/close_prev)| totals earn LOWER "
            "next-month returns (report direction: negative IC)."),
        "falsifiable_condition": (
            "Monthly Spearman IC of the 21-day |overnight gap| sum vs "
            "next-month returns is not negative, or the equal-weight G1..G5 "
            "monotonicity (G1 > G5, G1 = lowest gap) fails on the "
            "pre-registered window."),
        "admission": {
            "required_metrics": ["rankic_mean"],
            "thresholds": {"rankic_mean": {"op": "<", "value": -0.03}},
            "min_observations": 100,
        },
        "window": WINDOW,
        "family": "overnight",
        "ttl_days": 3650,
        "status": "registered",
        "created_at": "2026-07-01",
        "convention": {
            "universe": "top-300 A-share stocks by mean daily turnover, "
                        "2021-H1 (fixture-pinned)",
            "sample": "2021-07-01 .. 2026-06-30 (main snapshot)",
            "adjustment": "hfq via preclose chain (no adj_factor needed)",
            "ic": "Spearman, month-end factor vs next-month total return",
            "groups": "equal-weight quintiles, G1 = lowest factor",
            "rebalance": "monthly, close of month-end",
        },
        "preregistered_rules": replication.PREREGISTERED_RULES,
    }
    if not reg.has_hypothesis(h["hyp_id"]):
        reg.register_hypothesis(h)

    # --- 3. compute (A3/A4/A5) ------------------------------------------
    full_main = engine.load_frame(snap_main)
    signal = run_factor(replication.GAP_CODE, full_main.closes,
                        full_main.tickers, full_main.dates,
                        full_main.volumes, full_main.opens)
    frame = engine.load_frame(snap_main, WINDOW)
    meta = replication.load_monthly_meta(snap_main)
    rb = replication.recompute_replication_block(frame.closes, frame.dates,
                                                 signal, meta)
    metrics = engine.evaluate_signal(frame, signal)

    # --- 3b. disagreement attribution (A6): each experiment is itself a
    # whitelisted recomputation over a sub-window — every number in the
    # table recomputes from factor_code + the pinned snapshot.
    main_dates = frame.dates
    mid = main_dates[len(main_dates) // 2]
    attribution: dict[str, Any] = {}
    for label, win in (("first_half", f"{main_dates[0]}:{mid}"),
                       ("second_half",
                        f"{main_dates[min(len(main_dates) - 1,
                                          len(main_dates) // 2 + 1)]}:"
                        f"{main_dates[-1]}")):
        wframe = engine.load_frame(snap_main, win)
        series = replication.monthly_ic_series(wframe.closes, wframe.dates,
                                               signal)
        attribution[f"ic_raw_{label}"] = replication.ic_summary(series)
    groups10 = replication.group_monthly_returns(frame.closes, frame.dates,
                                                  signal, n_groups=10)
    attribution["groups_10"] = groups10
    attribution["convention_ladder"] = {
        mode: rb["ic_variants"][mode]["ic_mean"]
        for mode in ("raw", "cap", "cap_industry")}

    # --- 4. E card + full gate (A5/A8) -----------------------------------
    verdict, reasons = admission.evaluate(h["admission"], metrics)
    if verdict is None:
        print(f"metrics incomplete: {reasons}")
        return 1
    e = {
        "schema": "experiment_result",
        "exp_id": EXP_ID,
        "hyp_id": HYP_ID,
        "snapshot_hash": info.manifest_hash,
        "window": WINDOW,
        "engine": engine.EVAL_ID,
        "factor_code": replication.GAP_CODE,
        "factor_code_sha256": sha256_bytes(
            replication.GAP_CODE.encode("utf-8")),
        "metrics": metrics,
        "replication_block": rb,
        "attribution": attribution,
        "verdict": verdict,
        "settled_at": "2026-06-30",
    }
    h_p = work / "hypothesis.json"
    h_p.write_text(json.dumps(h, indent=2, ensure_ascii=False) + "\n")
    e_p = work / "result.json"
    e_p.write_text(json.dumps(e, indent=2, ensure_ascii=False) + "\n")
    ok, errs = verify.gate(h_p, e_p, snap_main, registry_path=reg_path)
    print(f"[gate] {'PASS' if ok else 'FAIL'} "
          f"({len(errs)} errors: {errs[:3]})")
    if not ok:
        print("gate failed on the honest card — aborting")
        return 1

    # --- 5. fabrication injection x3 (A7) --------------------------------
    injections = []
    # 5a. metric edit (phantom IC): nudge one monthly number by 0.01 — the
    #     gate must flag the exact mismatch
    bad = json.loads(json.dumps(e))
    bad["replication_block"]["ic_variants"]["raw"]["ic_mean"] += 0.01
    bad_p = work / "inj_metric.json"
    bad_p.write_text(json.dumps(bad, indent=2) + "\n")
    ok_b, errs_b = verify.gate(h_p, bad_p, snap_main, registry_path=reg_path)
    injections.append(("metric_edit", not ok_b, errs_b))
    # 5b. window swap: E claims a window the hypothesis never registered
    bad2 = json.loads(json.dumps(e))
    bad2["window"] = "20220101:20251231"
    bad2_p = work / "inj_window.json"
    bad2_p.write_text(json.dumps(bad2, indent=2) + "\n")
    ok_c, errs_c = verify.gate(h_p, bad2_p, snap_main, registry_path=reg_path)
    injections.append(("window_swap", not ok_c, errs_c))
    # 5c. universe swap: same cards against a snapshot built from
    #     different rows (main+tail data substituted for main)
    swap_dir = work / "snap_swap"
    if not (swap_dir / "MANIFEST.json").exists():
        merged2 = _merged_csv(main_csv, tail_csv, work / "merged_swap.csv")
        ingest_csv(merged2, swap_dir, volume_col="volume", open_col="open",
                   snapshot_id="ashare-SWAPPED", meta_dir=meta_dir)
    ok_d, errs_d = verify.gate(h_p, e_p, swap_dir, registry_path=reg_path)
    injections.append(("universe_swap", not ok_d, errs_d))
    for name, caught, errs_x in injections:
        first = errs_x[0][:110] if errs_x else "no error (BAD)"
        print(f"[inject:{name}] gate "
              f"{'REJECTED' if caught else '*** PASSED ***'} — {first}")
        if not caught:
            return 1
    # ungated control: the same metric edit with no gate stops nothing —
    # the file lands as-is. That contrast is the point of the gate.
    (work / "inj_metric_ungated_control.json").write_text(
        json.dumps(bad, indent=2) + "\n")

    # --- 6. settlement of the pre-registered claim on the 90-day tail (A9)
    led_path = work / "settlement.jsonl"
    led = settlement.SettlementLedger.open(led_path)
    if not [en for en in led.entries if en.get("exp_id") == EXP_ID]:
        settlement.settle_real_claim(led, e, h, snap_main, snap_full, REPO)
    audit = settlement.audit_ledger(led_path, fixture_root=REPO)
    print(f"[settlement] audit={'OK' if not audit else audit[:2]}")
    if audit:
        return 1

    # --- 7. report (A10): numbers machine-emitted, prose number-free -----
    rep_json = work / "replication_metrics.json"
    rep_json.write_text(json.dumps(rb, indent=2) + "\n")
    full_dates = engine.load_frame(snap_full).dates
    report = build_report(rb, attribution, injections, ok, verdict,
                          reasons, len(full_dates), len(frame.dates))
    (work / "report.md").write_text(report, encoding="utf-8")
    print(f"[report] {work / 'report.md'}")
    print(f"[verdict] engine={verdict} replication="
          f"{rb['rules']['verdict']} "
          f"(D1={rb['rules']['D1_direction']} "
          f"D2={rb['rules']['D2_monotonicity']} "
          f"D3={rb['rules']['D3_magnitude']})")
    return 0


def build_report(rb: dict, attribution: dict, injections: list,
                 gate_ok: bool, verdict: str, reasons: list,
                 n_full: int, n_main: int) -> str:
    v = rb["ic_variants"]
    g = rb["groups"]
    r = rb["rules"]
    inj_lines = "\n".join(
        f"- {name}: 门禁{'拦截' if caught else '放行（异常）'} — "
        f"{errs[0][:100] if errs else '-'}"
        for name, caught, errs in injections)
    reason_line = ("; ".join(reasons) if reasons else "全部预注册阈值满足")
    return f"""# 研报复现报告 — 昼夜分离（隔夜跳空因子）

机器产出的报告：所有数字由 `replication_metrics.json` 机械发射，
`result.json` 为门禁复算通过的原始证据卡；本文件的散文不产生任何自造数字。

## 研报与口径
出处与逐字段口径见 `hypothesis.json`（H 卡，A1）与其中 `convention` 块；
口径对齐表见 `replication.py` 的 `REPORT` 卡（A4）。

## 预注册判定（先登记后跑数，A8）
- D1 方向: {'通过' if r['D1_direction'] else '未通过'}
- D2 单调性: {'通过' if r['D2_monotonicity'] else '未通过'}
- D3 量级: {r['D3_magnitude']}（与独立复算参照的差异已归因：样本期与宇宙不同）
- 复现总判定: **{r['verdict']}**
- 引擎口径判定: {verdict}（{reason_line}）

## 月度口径指标（门禁独立复算{'通过' if gate_ok else '未通过'}，A5）
- 原始 IC: mean={v['raw']['ic_mean']}, ICIR={v['raw']['icir']}, P(IC<0)={v['raw']['p_ic_negative']}
- 市值中性 IC: mean={v['cap']['ic_mean']}
- 市值+行业中性 IC: mean={v['cap_industry']['ic_mean']}
- 五分组年化（G1=最低因子）: G1={g['G1']} … G5={g['G5']}

## 分歧归因（A6，每项可复算）
- 半样本 raw IC: 前半={attribution['ic_raw_first_half']['ic_mean']}，后半={attribution['ic_raw_second_half']['ic_mean']}
- 中性化阶梯（raw→cap→cap+industry）: {attribution['convention_ladder']['raw']} → {attribution['convention_ladder']['cap']} → {attribution['convention_ladder']['cap_industry']}
- 十分组敏感性: G1={attribution['groups_10']['G1']} … G10={attribution['groups_10']['G10']}
- 与独立复算参照（IC raw {replication.REPORT['references']['R2_independent_retest']['ic_mean']['raw']}，样本为 2020 年前历史）的差异来源：样本期与宇宙不同（A2 fixture 钉死口径），见 `replication.py` REPORT 卡的逐数字出处。

## 注入对照（A7，×3）
{inj_lines}
无门禁对照：同一改数在无门禁路径下原样落盘（`inj_metric_ungated_control.json`）。

## 结算（A9）
`settlement.jsonl`：主张在数据到达前登记，尾段（{n_main}/{n_full} 个交易日）
为真实到达数据，逐行前缀校验后结算；审计从钉死 fixture 重建快照并复算全部
realized 指标（hash 链 + 指标重算均通过）。
"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
