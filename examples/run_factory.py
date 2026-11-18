#!/usr/bin/env python3
"""v1.1 Scenario D — the factor factory, one command.

Fast lane (seconds): the pinned replication fixture -> 24 public-literature
template factors -> monthly rank-IC / ICIR / quintile spread / train-val-oos
IC per factor -> leaderboard.

Deep dive (top-3 by the leaderboard score): full tradeable-metrics
backtest on the same pinned data — net-of-fee return, Newey-West Sharpe,
turnover, capacity under a participation cap, drawdown/Calmar, and the
triple-gate partitions.

Tiering is the point: this demo RANKS candidates cheaply and honestly
(declared, reproducible numbers on pinned data); it certifies nothing.
Any candidate promoted to a claim still runs the v1.0 Scenario-A gauntlet
(pre-registration -> sandbox engine -> independent gate recomputation ->
verdict). Speed gained by skipping the honesty machinery would be a lie
factory; speed gained by not spending it on dead candidates is the point.

Usage:
    python examples/run_factory.py [--work DIR] [--top N] [--full]
      --full   run the zoo on the full fixture instead of the cached
               first 300 trade dates (fast smoke default)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qsa import backtest, factorzoo, snapshot  # noqa: E402
from qsa.ingest import ingest_csv  # noqa: E402
from qsa.replication import load_monthly_meta  # noqa: E402

FIXTURE = ROOT / "examples" / "data"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work/factory")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    snap_dir = work / "snap"
    if not (snap_dir / "MANIFEST.json").exists():
        ingest_csv(FIXTURE / "ashare_top300_main.csv", snap_dir,
                   volume_col="volume", open_col="open",
                   snapshot_id="ashare-top300-main",
                   meta_dir=FIXTURE / "replication_meta")
    closes = snapshot.load_closes(snap_dir)
    opens = snapshot.load_opens(snap_dir)
    volumes = snapshot.load_volumes(snap_dir)
    dates = sorted({d for row in closes.values() for d in row})
    meta = load_monthly_meta(snap_dir)
    if not args.full:
        # smoke mode: first 300 trade dates — the zoo itself is the demo;
        # CI runs this; --full exercises the whole 5-year sample
        dates = dates[:300]
        closes = {tk: {d: v for d, v in row.items() if d in set(dates)}
                  for tk, row in closes.items()}
        opens = {tk: {d: v for d, v in row.items() if d in set(dates)}
                 for tk, row in opens.items()}
        volumes = {tk: {d: v for d, v in row.items() if d in set(dates)}
                   for tk, row in volumes.items()}
    print(f"[load] {len(closes)} tickers x {len(dates)} dates "
          f"({time.time()-t0:.1f}s)", flush=True)

    t1 = time.time()
    board = factorzoo.run_zoo(closes, opens, volumes, dates)
    factorzoo.dump_leaderboard(board, work / "leaderboard.json")
    (work / "leaderboard.md").write_text(
        factorzoo.render_leaderboard(board, top=len(board)),
        encoding="utf-8")
    print(f"[zoo] {len(board)} factors evaluated ({time.time()-t1:.1f}s)",
          flush=True)

    cap_proxy = meta.get("caps", {})
    report = [
        "# v1.1 因子工厂报告（快验证层）",
        "",
        f"- 数据: 钉死 fixture（{len(closes)} 票 × {len(dates)} 交易日），"
        f"快照指纹见 {snap_dir.name}/MANIFEST.json",
        f"- 因子: {len(board)} 个公开文献模板（因子库见 qsa/factorzoo.py）",
        f"- 排序键: IC均值 × √月数（带符号，定向失败沉底）",
        "",
        factorzoo.render_leaderboard(board, top=10),
        "",
    ]

    for r in board[: args.top]:
        t2 = time.time()
        spec = next(s for s in factorzoo.build_catalog()
                    if s["id"] == r["id"])
        inputs = {"closes": closes, "opens": opens, "volumes": volumes,
                  "dates": dates}
        signal = factorzoo._finalize(spec["build"](inputs), dates,
                                     spec["flip"])
        # hold the TOP group (G5): the catalog is oriented higher=better,
        # so the tradable leg is the highest-factor quintile, not G1
        metrics = backtest.evaluate(closes, dates, signal,
                                    cap_proxy=cap_proxy, group=5)
        backtest.dump_json(metrics, work / f"backtest_{r['id']}.json")
        report.append(backtest.render_report(metrics, r["id"], group=5))
        report.append("")
        print(f"[backtest] {r['id']}: net {metrics['ann_return_net']:.4f}, "
              f"NW {metrics['nw_sharpe_net']}, "
              f"capacity {metrics['capacity_thousand_cny']} "
              f"({time.time()-t2:.1f}s)", flush=True)

    report.append(
        "## 分级声明\n\n"
        "- 本层为快验证：共享钉死数据上的可复算排序，不写 registry、不设阈值主张。\n"
        "- 任何要对外主张的因子必须走 v1.0 全程（预注册 H 卡 → 沙盒引擎 → "
        "门禁独立复算 → 预注册判定），见 examples/run_replication.py。\n"
        "- 成本/容量参数为显式行业常识默认（单边 8bps、参与率 10%），全部可改可审计。\n")
    (work / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"[done] {work/'report.md'} ({time.time()-t0:.1f}s total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
