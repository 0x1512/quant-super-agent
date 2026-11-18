#!/usr/bin/env python3
"""Throughput benchmark + floor gate (constitution priority #2: 高产能).

"产能指标（候选/分钟）可量化、进 CI" — this makes it mechanical:

    python tools/throughput_bench.py [--work work/throughput/run] \
        [--floor 20] [--full] [--reuse DIR]

Runs the offense workload (smoke window by default — the same one CI
uses), reads the run's own run_config.json (elapsed_s, workers) and
leaderboard.json (candidate rows), computes candidates/minute, writes
work/throughput/bench.json, and FAILS below the floor. Wall-clock is
inherently machine-dependent, so the floor is a coarse regression gate
(it catches an order-of-magnitude slowdown, not a 5% one); the pinned
reference number for marketing copy stays docs/TOUR_NUMBERS.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def count_candidates(leaderboard: dict) -> int:
    return sum(len(leaderboard.get(k) or []) for k in
               ("library", "interactions", "mutations", "forge"))


def measure(work: Path) -> dict:
    rc = json.loads((work / "run_config.json").read_text("utf-8"))
    lb = json.loads((work / "leaderboard.json").read_text("utf-8"))
    n = count_candidates(lb)
    elapsed = float(rc["elapsed_s"])
    per_min = n / (elapsed / 60.0)
    return {"mode": "full" if rc.get("full") else "smoke",
            "workers": rc.get("workers"), "candidates": n,
            "elapsed_s": elapsed, "per_min": round(per_min, 1),
            "fingerprint": rc.get("fingerprint"),
            "goal": rc.get("goal")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work/throughput/run")
    ap.add_argument("--floor", type=float, default=20.0,
                    help="candidates/min floor (coarse regression gate)")
    ap.add_argument("--full", action="store_true",
                    help="run the pinned full panel instead of smoke")
    ap.add_argument("--reuse", metavar="DIR",
                    help="measure an existing run dir instead of running")
    args = ap.parse_args()

    if args.reuse:
        work = Path(args.reuse)
    else:
        work = ROOT / args.work
        cmd = [sys.executable, "examples/run_offense.py",
               "--work", str(work)]
        if args.full:
            cmd.append("--full")
        t0 = time.time()
        subprocess.run(cmd, cwd=ROOT, check=True,
                       stdout=subprocess.DEVNULL)
        print(f"[bench] workload finished in {time.time()-t0:.1f}s wall")

    m = measure(work)
    m["floor"] = args.floor
    m["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out = ROOT / "work" / "throughput" / "bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"[bench] {m['mode']} mode: {m['candidates']} candidates "
          f"in {m['elapsed_s']}s @workers={m['workers']} "
          f"-> {m['per_min']}/min (floor {args.floor})")
    print(f"[bench] artifact: {out.relative_to(ROOT)}")
    if m["per_min"] < args.floor:
        print(f"[bench] FAIL: {m['per_min']}/min < floor {args.floor}/min")
        return 1
    print("[bench] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
