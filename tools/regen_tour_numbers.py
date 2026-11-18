#!/usr/bin/env python3
"""Tour-number regeneration & drift alarm (v1.4 ⑩ 演示自证).

Every number the demos quote must be REGENERABLE from the artifacts of
a real run — and must ALARM when the product drifts from the demo.

    python tools/regen_tour_numbers.py --work work/offense-full --write
    python tools/regen_tour_numbers.py --work work/offense-full   # check

Exit codes: 0 = numbers match (elapsed within slack), 1 = DRIFT, 2 =
missing artifacts. Exact fields (counts, ids) must match byte-for-byte;
``elapsed_s`` is timing noise, checked against a 1.6x slack and only
warned. The committed baseline lives at docs/TOUR_NUMBERS.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "TOUR_NUMBERS.json"
EXACT = ("run", "n_candidates", "n_winners", "n_streams", "workers",
         "basis_n", "n_dates", "fingerprint", "top3_ids")
SLACK = ("elapsed_s",)


def collect(work: Path) -> dict:
    need = ["manifest.json", "leaderboard.json", "run_config.json",
            "research_tree.json"]
    missing = [n for n in need if not (work / n).exists()]
    if missing:
        print("[tour] missing artifacts: " + ", ".join(missing))
        raise SystemExit(2)
    man = json.loads((work / "manifest.json").read_text("utf-8"))
    lb = json.loads((work / "leaderboard.json").read_text("utf-8"))
    cfg = json.loads((work / "run_config.json").read_text("utf-8"))
    raw = (lb.get("library", []) + lb.get("interactions", [])
           + lb.get("mutations", []) + lb.get("forge", []))
    # dedupe by id, first occurrence wins — the runner settles once per
    # candidate across streams (ledger integrity), the tour must match;
    # n_candidates keeps the manifest's convention (counted per stream)
    seen: set[str] = set()
    rows = []
    for r in raw:
        if r["id"] not in seen:
            seen.add(r["id"])
            rows.append(r)
    winners = sorted((r for r in rows
                      if r.get("oos_ic") is not None
                      and r["oos_ic"] > cfg["thresh"]
                      and (r.get("n_months") or 0) >= cfg["min_months"]),
                     key=lambda r: -r["oos_ic"])
    top3 = [r["id"] for r in sorted(
        (r for r in rows if r.get("oos_ic") is not None),
        key=lambda r: -r["oos_ic"])[:3]]
    return {
        "run": man["run"], "workers": man["workers"],
        "elapsed_s": man["elapsed_s"],
        "n_candidates": len(raw), "n_winners": len(winners),
        "n_streams": sum(1 for k in ("library", "interactions",
                                     "mutations", "forge") if lb.get(k)),
        "basis_n": len(lb.get("basis", [])),
        "fingerprint": cfg["fingerprint"],
        "n_dates": cfg.get("n_dates"),
        "top3_ids": top3,
        "throughput_per_min": round(len(rows) / (man["elapsed_s"] / 60), 1),
    }


def check(got: dict, base: dict) -> int:
    drift = 0
    for k in EXACT:
        if got.get(k) != base.get(k):
            print(f"[DRIFT] {k}: demo={base.get(k)!r} run={got.get(k)!r}")
            drift += 1
    for k in SLACK:
        b, g = base.get(k), got.get(k)
        if isinstance(b, (int, float)) and isinstance(g, (int, float)) \
                and g > b * 1.6:
            print(f"[WARN] {k}: demo={b} run={g} (>1.6x — 演示口径变慢)")
    return drift


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work/offense-full")
    ap.add_argument("--write", action="store_true",
                    help="rewrite the committed baseline from this run")
    args = ap.parse_args()
    got = collect(Path(args.work))
    print(json.dumps(got, ensure_ascii=False, indent=1))
    if args.write:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(got, ensure_ascii=False, indent=1)
                            + "\n", encoding="utf-8")
        print(f"[tour] baseline written -> {BASELINE}")
        return 0
    if not BASELINE.exists():
        print("[tour] no committed baseline — run with --write first")
        return 2
    base = json.loads(BASELINE.read_text("utf-8"))
    drift = check(got, base)
    if drift:
        print(f"[tour] ⛔ DRIFT: {drift} 个演示数字对不上——更新演示或回滚改动")
        return 1
    print("[tour] ✅ 演示数字与真实运行一致（counts/ids 全对，"
          "耗时在容差内）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
