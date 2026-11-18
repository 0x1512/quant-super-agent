#!/usr/bin/env python3
"""discovery@B — the breadth/verification tradeoff, measured (v0.7).

One family, one shared experiment ledger: planted and noise worlds arrive in
a fixed interleaved sequence and every world spends trials from the same
budget. As cumulative trials B grow, the Bonferroni deflation floor rises and
the per-trial discovery rate on planted worlds decays — the diminishing
returns of more mining, read straight off pipeline state rather than asserted.

Each world runs the full mining loop (roles data+factor+risk, one debate
round) under the same scripted persona policy, so the only thing that changes
between rows is B. The floor column is the ledger's own deflation floor at
the trial count the world faced.

Deterministic: same inputs -> byte-identical outputs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa.deflation import bonferroni_tstat_floor  # noqa: E402
from qsa.engine import load_frame  # noqa: E402
from qsa.llm import ScriptedLLM  # noqa: E402
from qsa.mining import run_order  # noqa: E402
from qsa.snapshot import build_snapshot  # noqa: E402

PLANT_STRENGTH = 0.10  # chosen so planted t-stats straddle the deflation
# floors the sequence generates (z(2)=2.24 .. z(24)=~3.1): discovery decays
# visibly within the sweep instead of staying pinned at 0 or 1
PLANTED_SEEDS = (11, 22, 33, 55, 66, 77, 88, 99)
NOISE_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
FAMILY = "disc"

ORDER = ("Mine one cross-sectional factor. Pre-register an admission bar of "
         "rankic_mean >= 0.02. Do not lower the bar.")

ROLES = ("data", "factor", "risk")


def hypothesis() -> str:
    # like qsa.ablation.hypothesis but WITHOUT a one-shot OOS window: the
    # shared ledger spans many worlds whose windows would otherwise collide
    # with the OOS-uniqueness discipline (this is a sweep, not a claim)
    return json.dumps({
        "mechanism": "1-day cross-sectional short-term reversal: yesterday's "
                     "losers outperform today",
        "falsifiable_condition": "mean rank IC <= 0",
        "admission": {
            "required_metrics": ["rankic_mean", "rankic_tstat",
                                 "quintile_spread", "monotonicity_proxy",
                                 "n_dates", "coverage"],
            "thresholds": {"rankic_mean": {"op": ">=", "value": 0.02},
                           "coverage": {"op": ">=", "value": 0.8}},
            "min_observations": 10}})


def policy_queue(rounds: int, budget: int = 3) -> list[str]:
    from qsa.ablation import BEAR, BULL, F_REV
    iteration = [hypothesis(), F_REV]
    if rounds:
        iteration += [BULL, BEAR] * rounds
    return iteration * budget


def main() -> int:
    out_dir = Path(__file__).resolve().parents[1] / "work" / "discovery"
    out_dir.mkdir(parents=True, exist_ok=True)
    worlds_dir = out_dir / "worlds"
    worlds_dir.mkdir(exist_ok=True)
    reg_path = out_dir / "registry.jsonl"

    # fixed interleaved sequence: planted, noise, planted, noise, ...
    seq = []
    for i in range(max(len(PLANTED_SEEDS), len(NOISE_SEEDS))):
        if i < len(PLANTED_SEEDS):
            seq.append(("planted", PLANTED_SEEDS[i]))
        if i < len(NOISE_SEEDS):
            seq.append(("noise", NOISE_SEEDS[i]))

    rows = []
    p_admit = p_seen = n_admit = n_seen = 0
    for k, (kind, seed) in enumerate(seq, 1):
        d = worlds_dir / f"{kind}-{seed}"
        if not d.exists():
            build_snapshot(d, seed=seed, tickers=12, days=90,
                           plant=({"effect": "reversal",
                                   "strength": PLANT_STRENGTH}
                                  if kind == "planted" else None))
        frame = load_frame(d)
        work = out_dir / "runs" / f"{k:02d}-{kind}-{seed}"
        llm = ScriptedLLM(policy_queue(1),
                          run_log=out_dir / f"run-{k:02d}.jsonl")
        summary = run_order(work, d, ORDER, llm, budget=3, family=FAMILY,
                            roles=ROLES, debate_rounds=1, verbose=False,
                            registry_path=reg_path)
        from qsa.registry import Registry
        b = Registry(reg_path).n_trials(FAMILY)
        admitted = bool(summary["admitted"])
        if kind == "planted":
            p_seen += 1
            p_admit += int(admitted)
        else:
            n_seen += 1
            n_admit += int(admitted)
        rows.append({
            "k": k, "kind": kind, "seed": seed, "B": b,
            "floor": round(bonferroni_tstat_floor(b), 4),
            "admitted": admitted,
            "discovery_rate": round(p_admit / p_seen, 6) if p_seen else 0.0,
            "false_positive_rate": (round(n_admit / n_seen, 6)
                                    if n_seen else 0.0),
        })
        print(f"  [{k:02d}] {kind:7s} seed={seed:<3d} B={b:<3d} "
              f"floor={rows[-1]['floor']:.3f} admitted={admitted} "
              f"discovery@B={rows[-1]['discovery_rate']:.3f} "
              f"fp@B={rows[-1]['false_positive_rate']:.3f}")

    lines = [
        "| k | world | seed | B (family trials) | deflation floor | admitted "
        "| discovery@B | FP@B |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['k']} | {r['kind']} | {r['seed']} | {r['B']} | "
                     f"{r['floor']:.4f} | {r['admitted']} | "
                     f"{r['discovery_rate']:.3f} | "
                     f"{r['false_positive_rate']:.3f} |")
    table = "\n".join(lines)
    (out_dir / "discovery.md").write_text(table + "\n", encoding="utf-8")
    (out_dir / "rows.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    final = rows[-1]
    print(f"\ndiscovery@B: {final['discovery_rate']:.3f} on planted "
          f"({p_admit}/{p_seen}), FP {final['false_positive_rate']:.3f} on "
          f"noise ({n_admit}/{n_seen}) at B={final['B']}")
    print(f"[+] wrote {out_dir / 'discovery.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
