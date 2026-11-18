#!/usr/bin/env python3
"""v1.4 offense — one command: plan tree + auto crew + layered report.

    python examples/run_offense.py [--work work/offense] [--full]
                                    [--workers N|auto] [--goal "..."]

Out of the box, this runs the whole offensive pipeline on the pinned
fixture:

  0. infra gate + blackboard (same discipline as the order runner)
  1. merge main + extra fixtures (high/low/amount/vwap unlocked) into a
     fingerprinted snapshot
  2. zoo re-run -> the surviving factors become the RESIDUAL BASIS
  3. factor library scan (30 open-source factors: WorldQuant 101 subset,
     Parkinson/GK/RS range estimators, Amihud/flow family), each scored
     by residual IC against that basis — clones earn nothing
  4. interaction mining: pairwise product/ratio/spread of the top
     survivors' rank signals, residualized
  5. mutation search: window sweeps over the parameterized families,
     residualized
  5b. sandbox forge loop (v1.4): machine-detected gaps (missing panels,
     promised-but-empty streams) trigger deterministic template codegen
     -> AST-whitelisted sandbox -> same residual yardstick; every row is
     tagged source=sandbox-forge + code fingerprint
  6. every candidate above the pre-declared residual-oos threshold walks
     the ORDER STATE MACHINE (admit freezes params; settle/refuse is
     mechanical); the report lists what earned a fast-lane ticket

v1.4 orchestration, visible in artifacts:

  * PLAN TREE — the goal compiles to a fingerprinted Plan
    (qsa.planner); the run materializes it as research_tree.json with
    per-node status/notes/timing, updated as each stage lands, and the
    report leads with its rendering.
  * AUTO CREW — --workers auto (the default) sizes N from the job count
    (clamp(ceil(jobs/8), 1, cpus, 16)); every run drops manifest.json
    with the role-by-job split (GateKeeper/RepoSmith/FlowMapper/
    SmokeRunner names). Byte-identical for any N.
  * LAYERED REPORT — archive strip -> top-3 four-line cards ->
    leaderboard -> appendices (library manifest, sandbox-forge log,
    honesty). report.md is now qsa.researchreport output.

Stages 2-5 run through the v1.3.1 DISPATCHER: jobs are pure,
Pool.map preserves order, output is byte-identical to the sequential
path for any N.

Honesty tier: this is the fast lane. Nothing here certifies a claim;
winners still owe the v1.0 gauntlet. Numbers are machine-emitted.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qsa import (checkpoint, crew, dispatch, factorforge,  # noqa: E402
                 factorlib, factorzoo, offense, planner, recompute,
                 researchreport, snapshot)
from qsa.blackboard import bootstrapped  # noqa: E402
from qsa.infragate import bootstrap_forks, infra_gate, render_gate  # noqa: E402
from qsa.ingest import ingest_csv  # noqa: E402
from qsa.orders import OrderBook, OrderError  # noqa: E402

FIXTURE = ROOT / "examples" / "data"
THRESH = 0.03          # pre-declared: residual oos IC to earn an order
MIN_MONTHS = 12        # and at least this many scored months
DEFAULT_GOAL = ("top300 残差因子进攻：引用因子库+交互+窗口变异，"
                "门槛 residual oos IC > 0.03")


def merge_csvs(main: Path, extra: Path, out: Path) -> int:
    extra_map: dict[tuple[str, str], dict[str, str]] = {}
    with extra.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            extra_map[(r["ticker"], r["date"])] = r
    n = 0
    with main.open(encoding="utf-8") as fh, out.open("w", newline="",
                                                     encoding="utf-8") as wh:
        reader, writer = csv.DictReader(fh), csv.writer(wh)
        writer.writerow(["date", "ticker", "close", "open", "volume",
                         "high", "low", "amount", "vwap"])
        for r in reader:
            e = extra_map.get((r["ticker"], r["date"]))
            if e is None:
                raise ValueError(f"extra fixture missing {r['ticker']} "
                                 f"{r['date']} — fixtures out of sync")
            writer.writerow([r["date"], r["ticker"], r["close"], r["open"],
                             r["volume"], e["high"], e["low"], e["amount"],
                             e["vwap"]])
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work/offense")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--workers", default="auto",
                    help="FactorMiner worker processes: N, or 'auto' "
                         "(default; sized from the job count, "
                         "byte-identical output either way)")
    ap.add_argument("--goal", default=DEFAULT_GOAL,
                    help="research intent — compiled to a fingerprinted "
                         "Plan (qsa.planner)")
    ap.add_argument("--resume", action="store_true",
                    help="SUPERAGENT_PLAN #2: reuse per-job results from "
                         "<work>/checkpoint/ (same plan fingerprint) and "
                         "run only the missing jobs; output is "
                         "byte-identical to an uninterrupted run")
    args = ap.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ---- v1.4: plan tree (materialized, updated per stage) ---------------
    plan = planner.intent_to_plan(args.goal)
    fp = planner.fingerprint(plan)
    ckpt = checkpoint.Checkpoint(work / "checkpoint", fp) if args.resume \
        else None
    thresh, min_months = plan.thresh, plan.min_months
    tree = planner.tree(args.goal, fp)
    plan_path = work / "research_tree.json"

    def tick(nid: str, status: str, note: str) -> None:
        n = next(x for x in tree["nodes"] if x["id"] == nid)
        n["status"], n["note"] = status, note
        plan_path.write_text(json.dumps(tree, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    print(f"[plan] 指纹 {fp} · 目标「{args.goal}」", flush=True)
    for note in plan.notes:
        print(f"[plan]   {note}", flush=True)

    # ---- 0. gate + memory ------------------------------------------------
    board = bootstrapped(work / "blackboard.jsonl")
    forks = bootstrap_forks(work / "forks.jsonl")
    report = infra_gate(FIXTURE, board)
    print(render_gate(report), flush=True)
    if not report["ok"]:
        tick("gate", "skipped", "infra gate SHUT — 拒绝开工")
        print("\n[refuse] infra gate SHUT — no offense today.")
        return 1
    tick("gate", "done", f"{len(report['checks'])} 项核对通过")

    # ---- 1. merged snapshot with the full panel set ----------------------
    merged = work / "merged.csv"
    if not merged.exists():
        n = merge_csvs(FIXTURE / "ashare_top300_main.csv",
                       FIXTURE / "ashare_top300_extra.csv", merged)
        print(f"[merge] {n} rows: close/open/volume + high/low/amount/vwap",
              flush=True)
    snap_dir = work / "snap"
    if not (snap_dir / "MANIFEST.json").exists():
        ingest_csv(merged, snap_dir, volume_col="volume", open_col="open",
                   high_col="high", low_col="low", amount_col="amount",
                   vwap_col="vwap", snapshot_id="ashare-top300-full-panels",
                   meta_dir=FIXTURE / "replication_meta")
    inputs = {
        "closes": snapshot.load_closes(snap_dir),
        "opens": snapshot.load_opens(snap_dir),
        "volumes": snapshot.load_volumes(snap_dir),
        "highs": snapshot.load_highs(snap_dir),
        "lows": snapshot.load_lows(snap_dir),
        "amounts": snapshot.load_amounts(snap_dir),
        "vwaps": snapshot.load_vwaps(snap_dir),
    }
    dates = sorted({d for row in inputs["closes"].values() for d in row})
    if not args.full:
        keep = set(dates[:300])
        dates = dates[:300]
        inputs = {k: {tk: {d: v for d, v in row.items() if d in keep}
                      for tk, row in panel.items()}
                  for k, panel in inputs.items()}
    inputs["dates"] = dates
    # ---- v1.4: honor the intent's universe (smallcap / exclude-smallcap)
    if plan.universe.get("name") != "top300" or plan.universe.get("exclude"):
        inputs = recompute.filter_universe(inputs, plan.universe)
        print(f"[universe] 意图指定 {plan.universe} -> "
              f"{len(inputs['closes'])} tickers（按成交额下四分位切）",
              flush=True)
    tick("snapshot", "done",
         f"{len(inputs['closes'])} 票 × {len(dates)} 日，"
         f"{len(inputs) - 1} 面板"
         + (f"，范围 {plan.universe['name']}" if plan.universe.get("name")
            != "top300" or plan.universe.get("exclude") else ""))
    print(f"[load] {len(inputs['closes'])} tickers x {len(dates)} dates, "
          f"panels: {', '.join(sorted(k for k in inputs if k != 'dates'))}",
          flush=True)

    # ---- v1.4: auto crew sizing ------------------------------------------
    available = {k for k in inputs if k != "dates"}
    month_fams, day_fams, month_wins, day_wins = planner.windows_for(plan)
    streams = planner.streams_for(plan)
    n_zoo = len(factorzoo.build_catalog())
    n_lib = len(factorlib.build_catalog(available)) if streams["library"] \
        else 0
    n_ix = (min(args.top_k, 8) * (min(args.top_k, 8) - 1) // 2 * 3) \
        if streams["interactions"] else 0
    n_mut = (len(month_fams) * len(month_wins) + len(day_fams) * len(day_wins)) \
        if streams["mutations"] else 0
    n_jobs = n_zoo + n_lib + n_ix + n_mut
    workers = (dispatch.auto_workers(n_jobs) if args.workers == "auto"
               else dispatch.default_workers(int(args.workers)))
    print(f"[dispatch] auto-扩编: {n_jobs} jobs -> {workers} FactorMiner "
          f"worker{'s' if workers > 1 else ''} "
          f"(clamp(ceil(jobs/8),1,cpus,16); byte-identical to sequential)",
          flush=True)

    # ---- 2. zoo survivors = residual basis --------------------------------
    t1 = time.time()
    zoo = dispatch.zoo(inputs["closes"], inputs["opens"],
                       inputs["volumes"], dates, workers=workers,
                       ckpt=ckpt, crew_dir=work / "crew")
    surv = [r for r in zoo if r["oos_ic"] is not None
            and r["oos_ic"] > 0.03]
    surv.sort(key=lambda r: -r["oos_ic"])
    basis_specs = [next(s for s in factorzoo.build_catalog()
                        if s["id"] == r["id"]) for r in surv]
    # zoo builds return raw rows; finalize to sparse signals (factorlib
    # builds do this internally — conventions documented in offense.py)
    basis = [factorzoo._finalize(s["build"](inputs), dates, s["flip"])
             for s in basis_specs]
    basis_digest = hashlib.sha256(
        json.dumps([r["id"] for r in surv]).encode()).hexdigest()[:10]
    tick("basis", "done",
         f"{len(surv)} 幸存者 @{basis_digest}（{time.time()-t1:.1f}s）")
    print(f"[basis] {len(surv)} zoo survivors "
          f"({', '.join(r['id'] for r in surv[:5])}…) "
          f"@{basis_digest} ({time.time()-t1:.1f}s)", flush=True)

    # ---- 3. library scan under the residual objective ---------------------
    t2 = time.time()
    if streams["library"]:
        lib_rows = dispatch.library(inputs, basis, workers=workers,
                                    ckpt=ckpt, crew_dir=work / "crew")
        lib_rows.sort(key=lambda r: -(r["oos_ic"] or -9))
        tick("library", "done",
             f"{len(lib_rows)} 引用因子同尺评分（{time.time()-t2:.1f}s）")
        print(f"[library] {len(lib_rows)} factors scored by residual IC "
              f"({time.time()-t2:.1f}s)", flush=True)
    else:
        lib_rows = []
        tick("library", "skipped", "计划未要求（intent 未提及）")

    # ---- 4. interactions ---------------------------------------------------
    t3 = time.time()
    if streams["interactions"] and basis:
        ix_rows = dispatch.interactions(basis_specs, inputs, basis,
                                        top_k=args.top_k, workers=workers,
                                        ckpt=ckpt, crew_dir=work / "crew")
        ix_rows.sort(key=lambda r: -(r["oos_ic"] or -9))
        tick("interactions", "done",
             f"{len(ix_rows)} 组合候选（{time.time()-t3:.1f}s）")
        print(f"[interactions] {len(ix_rows)} pairs x ops "
              f"({time.time()-t3:.1f}s)", flush=True)
    elif not streams["interactions"]:
        ix_rows = []
        tick("interactions", "skipped", "计划未要求（intent 未提及）")
    else:
        ix_rows = []
        tick("interactions", "skipped", "残差基为空——无基线幸存者可组合")

    # ---- 5. mutations -------------------------------------------------------
    t4 = time.time()
    if streams["mutations"]:
        mut_rows = dispatch.mutations(
            month_fams, day_fams, month_wins, day_wins, inputs, basis,
            workers=workers, ckpt=ckpt, crew_dir=work / "crew")
        mut_rows.sort(key=lambda r: -(r["oos_ic"] or -9))
        tick("mutations", "done",
             f"{len(mut_rows)} 窗口变体（{time.time()-t4:.1f}s）")
        print(f"[mutations] {len(mut_rows)} window variants "
              f"({time.time()-t4:.1f}s)", flush=True)
    else:
        mut_rows = []
        tick("mutations", "skipped", "计划未要求（intent 未提及）")

    if ckpt is not None:
        print(f"[resume] checkpoint 复用 {ckpt.hits} 个作业结果，"
              f"实跑 {ckpt.misses} 个（指纹 {ckpt.fp}）", flush=True)

    # ---- 5b. sandbox forge loop (v1.4) --------------------------------------
    full_needs: set[str] = set()
    for spec in factorlib.build_catalog(None):
        full_needs.update(spec.get("needs", ()))
    t5 = time.time()
    forge_rows, gaps = factorforge.fill_gaps(
        inputs, streams,
        {"library": lib_rows, "interactions": ix_rows,
         "mutations": mut_rows},
        basis, catalog_needs=full_needs, force=streams.get("forge", False))
    if forge_rows:
        n_ok = sum(1 for r in forge_rows if r.get("ok"))
        n_ref = len(forge_rows) - n_ok
        print(f"[forge] {len(gaps)} 缺口 -> {len(forge_rows)} 沙盒候选 "
              f"({n_ok} 评估, {n_ref} 拒绝) "
              f"({time.time()-t5:.1f}s)", flush=True)
    else:
        print("[forge] 无缺口，未触发生成", flush=True)
    if forge_rows:
        tick("forge", "done",
             f"{len(gaps)} 缺口，{len(forge_rows)} 沙盒候选"
             f"（{time.time()-t5:.1f}s）")
    else:
        tick("forge", "skipped", "无缺口，未触发生成")

    # ---- 6. orders for what earned a fast-lane ticket ----------------------
    universe_desc = plan.universe.get("name", "top300") + (
        "-ex-smallcap" if plan.universe.get("exclude") else "")
    book = OrderBook(work / "orders.jsonl")
    universe_digest = forks.digest("BB-FORK-02")
    # dedupe across streams: same candidate id from library and mutation
    # pools must settle once, not twice (ledger integrity)
    winners: list[dict] = []
    seen: set[str] = set()
    for r in lib_rows + ix_rows + mut_rows + forge_rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        if r["oos_ic"] is not None and r["oos_ic"] > thresh \
                and (r["n_months"] or 0) >= min_months:
            winners.append(r)
    for r in winners:
        params = {
            "factor": r["id"],
            "hypothesis": f"{r['id']} carries OOS rank signal on top-300 "
                          f"RESIDUAL to the {len(surv)} zoo survivors",
            "universe": universe_desc, "universe_fork":
                f"BB-FORK-02@{universe_digest}",
            "objective": f"residual-vs-basis@{basis_digest}",
            "dates": [dates[0], dates[-1], len(dates)],
            "metric": "monthly rank-IC on residualized signal, "
                      "triple-gate 60/20/20",
            "settle_if": f"residual oos IC > {thresh} and n_months >= "
                         f"{min_months} (pre-declared in the plan)",
            "recipe": r["desc"],
        }
        oid = book.create(params["hypothesis"], params, priority=4,
                          note="v1.4 offense candidate"
                          + (" (sandbox-forge)" if r.get("source")
                             == "sandbox-forge" else ""))
        book.admit(oid, params)
        book.start(oid, params)
        book.settle(oid, {"residual_oos_ic": r["oos_ic"],
                          "ic_mean": r["ic_mean"], "icir": r["icir"],
                          "n_months": r["n_months"],
                          "verdict": "fast-lane survivor (gauntlet still "
                                     "required)"})
        print(f"[settle] {r['id']:34s} residual oos IC "
              f"{r['oos_ic']:+.4f}", flush=True)
    if not winners:
        print("[orders] no candidate cleared the pre-declared bar — an "
              "honest zero is a valid result", flush=True)
    tick("orders", "done", f"{len(winners)} 张订单 settle")
    board.post("order_note", f"offense run: {len(winners)} fast-lane "
                f"winners of {len(lib_rows)+len(ix_rows)+len(mut_rows)}"
                f"+{len(forge_rows)} candidates", f"basis={basis_digest}, "
                f"window {dates[0]}..{dates[-1]}, threshold residual oos IC "
                f"> {thresh}; winners owe the v1.0 gauntlet.",
                tags=["offense"])

    # ---- 7. artifacts: manifest, run config, layered report ----------------
    elapsed = time.time() - t0
    jobs_by_kind = {"zoo": n_zoo, "lib": n_lib, "ix": n_ix, "mut": n_mut,
                    "forge": len(forge_rows)}
    dispatch.manifest(work.name, workers, jobs_by_kind,
                      elapsed, out_path=work / "manifest.json")
    # SUPERAGENT_PLAN #5: session cards must reconcile with the manifest
    bad = crew.reconcile(work / "crew", {"jobs_by_kind": jobs_by_kind})
    if bad:
        print(f"[crew] 会话卡对账不一致：{bad}", flush=True)
    (work / "run_config.json").write_text(
        json.dumps({"goal": args.goal, "fingerprint": fp,
                    "thresh": thresh, "min_months": min_months,
                    "workers": workers, "top_k": args.top_k,
                    "full": args.full, "streams": streams,
                    "month_families": month_fams,
                    "day_families": day_fams,
                    "month_wins": month_wins, "day_wins": day_wins,
                    "n_dates": len(dates),
                    "elapsed_s": round(elapsed, 1),
                    "n_winners": len(winners)},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    all_rows = sorted(lib_rows + ix_rows + mut_rows + forge_rows,
                      key=lambda r: -(r["oos_ic"] or -9))
    meta = {
        "run": work.name, "dates": [dates[0], dates[-1], len(dates)],
        "universe": universe_desc, "n_tickers": len(inputs["closes"]),
        "basis_n": len(surv), "basis_digest": basis_digest,
        "n_candidates": len(all_rows), "n_winners": len(winners),
        "workers": workers, "elapsed_s": f"{elapsed:.1f}",
    }
    library_md = "\n".join(
        ["| id | family | needs | source |",
         "|----|--------|-------|--------|"]
        + [f"| {r['id']} | {r['family']} | {r['needs']} | {r['source']} |"
           for r in factorlib.catalog_summary()])
    report_md = researchreport.render_layered(
        meta, winners,
        offense.render_board(all_rows, top=20,
                             title="进攻 leaderboard（残差目标）"),
        thresh, min_months,
        library_md=library_md,
        forge_md=factorforge.render_forge_log(forge_rows, gaps),
        tree_md=planner.render_tree(tree))
    (work / "report.md").write_text(report_md, encoding="utf-8")
    (work / "leaderboard.json").write_text(
        json.dumps({"plan": {"goal": args.goal, "fingerprint": fp},
                    "basis": [r["id"] for r in surv],
                    "basis_digest": basis_digest,
                    "library": lib_rows, "interactions": ix_rows,
                    "mutations": mut_rows, "forge": forge_rows},
                   ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"\n[done] winners={len(winners)} -> {work/'report.md'} "
          f"({elapsed:.1f}s total, plan {fp}, {workers} workers)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
