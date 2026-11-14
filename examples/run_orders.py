#!/usr/bin/env python3
"""v1.2 — the zoo becomes an order book: every hypothesis has a lifecycle.

What this adds over run_factory.py (which is a batch script):

  1. infra gate first — orders are only created after the data plane
     checks pass and the blackboard is clear of blockers;
  2. admit freezes parameters — each factor's evaluation window,
     universe, and thresholds are hashed at admission; running with
     anything else is a hard error (pre-registration for all 24, not
     just the flagship);
  3. settle vs refuse is mechanical — oos IC above the pre-declared
     threshold settles with results attached; below it the order is
     REFUSED and the blackboard gets a decay_event with the numbers.
     No re-running until it passes: the state machine forbids it;
  4. one deliberate drift demo — a final order is admitted with one
     universe and started with another; the machine's refusal is the
     point, printed for the record.

Usage:
    python examples/run_orders.py [--work DIR] [--full]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qsa import factorzoo, snapshot  # noqa: E402
from qsa.blackboard import Blackboard, bootstrapped  # noqa: E402
from qsa.infragate import (bootstrap_forks, infra_gate,  # noqa: E402
                           render_gate)
from qsa.ingest import ingest_csv  # noqa: E402
from qsa.orders import OrderBook, OrderError  # noqa: E402

FIXTURE = ROOT / "examples" / "data"
OOS_FLOOR = 0.03  # pre-declared settle/refuse threshold, frozen at admit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work/orders")
    ap.add_argument("--full", action="store_true",
                    help="full sample instead of first 300 dates")
    args = ap.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ---- 1. infra gate: no orders before the data plane is sound -------
    board = bootstrapped(work / "blackboard.jsonl")
    forks = bootstrap_forks(work / "forks.jsonl")
    report = infra_gate(FIXTURE, board)
    (work / "gate.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(render_gate(report), flush=True)
    if not report["ok"]:
        print("\n[refuse] infra gate SHUT — no orders admitted.")
        return 1

    # ---- 2. data (same pinned fixture as the zoo) -----------------------
    snap_dir = work / "snap"
    if not (snap_dir / "MANIFEST.json").exists():
        ingest_csv(FIXTURE / "ashare_top300_main.csv", snap_dir,
                   volume_col="volume", open_col="open",
                   snapshot_id="ashare-top300-main-orders",
                   meta_dir=FIXTURE / "replication_meta")
    closes = snapshot.load_closes(snap_dir)
    opens = snapshot.load_opens(snap_dir)
    volumes = snapshot.load_volumes(snap_dir)
    dates = sorted({d for row in closes.values() for d in row})
    if not args.full:
        keep = set(dates[:300])
        dates = dates[:300]
        closes = {tk: {d: v for d, v in row.items() if d in keep}
                  for tk, row in closes.items()}
        opens = {tk: {d: v for d, v in row.items() if d in keep}
                 for tk, row in opens.items()}
        volumes = {tk: {d: v for d, v in row.items() if d in keep}
                   for tk, row in volumes.items()}
    print(f"[load] {len(closes)} tickers x {len(dates)} dates "
          f"(blackboard: {len(board)} entries, forks: "
          f"{len(forks.cards)}, {time.time()-t0:.1f}s)", flush=True)

    book = OrderBook(work / "orders.jsonl")
    universe_digest = forks.digest("BB-FORK-02")

    def prior_terminal(hypothesis: str, params: dict) -> dict | None:
        """A terminal order for the same hypothesis AND identical frozen
        params is a remembered verdict — recall it instead of re-running.
        (This is the cross-session payoff: the book does the memoization.)"""
        for o in book.orders.values():
            if (o["hypothesis"] == hypothesis
                    and o.get("params_hash") == book.param_hash(params)
                    and o["state"] in ("settled", "refused")):
                return o
        return None

    # ---- 3. every catalog factor walks the machine ----------------------
    settled, refused, recalled = [], [], []
    for spec in factorzoo.build_catalog():
        params = {
            "factor": spec["id"],
            "hypothesis": f"{spec['id']} carries OOS rank signal on "
                          f"top-300 (source: {spec['source']})",
            "universe": "top300",
            "universe_fork": f"BB-FORK-02@{universe_digest}",
            "cost_fork": "BB-FORK-03@8bps",
            "dates": [dates[0], dates[-1], len(dates)],
            "metric": "monthly rank-IC, triple-gate partitions 60/20/20",
            "settle_if": f"oos_ic > {OOS_FLOOR} (pre-declared)",
        }
        prior = prior_terminal(params["hypothesis"], params)
        if prior is not None:
            why = (prior["results"]["oos_ic"] if prior["results"]
                   else prior["refusal"])
            print(f"[recall] {spec['id']:22s} {prior['state']} "
                  f"(book remembers: {why})", flush=True)
            recalled.append(prior)
            continue
        oid = book.create(params["hypothesis"], params,
                          priority=5, note=spec["desc"])
        book.admit(oid, params)              # freeze
        book.start(oid, params)              # same params or hard error
        row = factorzoo.evaluate_factor(
            spec, {"closes": closes, "opens": opens, "volumes": volumes,
                   "dates": dates})
        oos = row["oos_ic"]
        if oos is not None and oos > OOS_FLOOR:
            book.settle(oid, {
                "ic_mean": row["ic_mean"], "icir": row["icir"],
                "oos_ic": oos, "train_ic": row["train_ic"],
                "n_months": row["n_months"],
                "verdict": "survivor (fast lane; gauntlet still required)",
            })
            settled.append(row)
            tag = "settle"
        else:
            reason = (f"oos IC {oos if oos is not None else 'n/a'} <= "
                      f"{OOS_FLOOR} — signal dead out-of-sample")
            book.refuse(oid, reason)
            board.post("decay_event",
                       f"{spec['id']} refused: OOS-dead on top-300",
                       f"train IC {row['train_ic']} -> oos IC "
                       f"{row['oos_ic']}; order refused, re-entry only "
                       f"via a NEW order with a changed hypothesis.",
                       tags=["decay", "orders", spec["id"]])
            refused.append(row)
            tag = "REFUSE"
        print(f"[{tag:6s}] {spec['id']:22s} oos_ic="
              f"{row['oos_ic'] if row['oos_ic'] is not None else 'n/a'}",
              flush=True)

    # ---- 4. the drift demo: pre-registration has teeth -------------------
    drift_params = {"factor": "drift_demo", "universe": "top300",
                    "metric": "demonstration only"}
    drift_hyp = "drift demo: admitted top300, started csi500"
    if prior_terminal(drift_hyp, drift_params) is None:
        did = book.create(drift_hyp, drift_params, priority=9,
                          note="discipline demo")
        book.admit(did, drift_params)
        tampered = dict(drift_params)
        tampered["universe"] = "csi500"
        try:
            book.start(did, tampered)
            raise AssertionError("unreachable: start must refuse drift")
        except OrderError as e:
            book.refuse(did, f"param drift caught at start: {e}")
            print(f"[drift ] {did}: refused as designed — params differ "
                  f"from admission", flush=True)
    else:
        print("[drift ] skipped (already in the book)", flush=True)

    # ---- 5. summary ------------------------------------------------------
    s = book.summary()
    lines = [
        "# v1.2 订单簿报告（状态机层）",
        "",
        f"- infra gate: {'OPEN' if report['ok'] else 'SHUT'} "
        f"（5 项检查见 gate.json）",
        f"- 黑板: {len(board)} 条（bootstrapped {8} 条真实踩坑史 + "
        f"{len(refused)} 条新衰减事件）",
        f"- fork 卡: {len(forks.cards)} 张，全部已拍板"
        f"（append-only，重复拍板被拒）",
        f"- 订单: settled {s['settled']} / refused {s['refused']} / "
        f"admitted {s['admitted']}（漂移演示）；本次运行 recall "
        f"{len(recalled)} 条（书有记忆，重跑不重算）",
        "",
        "## 幸存者（快车道；对外主张仍需 v1.0 全程）",
        "",
        "| factor | IC均值 | ICIR | oos IC |",
        "|--------|--------|------|--------|",
    ]
    for r in sorted(settled, key=lambda x: -(x["oos_ic"] or 0)):
        lines.append(f"| {r['id']} | {r['ic_mean']:.4f} | "
                     f"{r['icir']:.3f} | {r['oos_ic']:.4f} |")
    lines += [
        "",
        "## 状态机纪律（本次运行实际触发）",
        "",
        "- admit 冻结参数哈希；start 参数不一致 → 硬错（漂移演示已触发）",
        "- refused 订单不可重启（终态）；重进只能开新单、新假设",
        "- 订单日志 hash 链验证于每次加载（orders.jsonl）",
        "",
        f"耗时 {time.time()-t0:.1f}s。",
    ]
    (work / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[done] settled={s['settled']} refused={s['refused']} -> "
          f"{work/'report.md'} ({time.time()-t0:.1f}s total)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
