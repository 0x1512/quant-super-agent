"""Ablation harness — role subsets × debate rounds vs discovery and FP rates.

v0.4's acceptance experiment. The harness is deliberately mechanical about
honesty:

* the **policy is identical in every configuration** — the same scripted
  persona responses (same hypothesis, same factor code, same bull/bear
  arguments). Whatever differs between rows can therefore only come from the
  gating machinery being switched on or off, never from a smarter or dumber
  script;
* **discovery** is measured on snapshots with a *planted* 1-day reversal
  (strength below "obvious", above "invisible"): admitted = the loop settled
  a pass through every active layer;
* **false positives** are measured on pure-noise snapshots: an admitted
  factor there is, by construction, a hallucinated edge;
* every run is a fresh order with a fresh ledger; the whole table is
  byte-reproducible (`tests/test_ablation.py` pins it).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import engine
from .llm import ScriptedLLM
from .mining import run_order
from .snapshot import build_snapshot

PLANT_STRENGTH = 0.15

ORDER = ("Mine one cross-sectional factor. Pre-register an admission bar of "
         "rankic_mean >= 0.02 and a 15-day one-shot OOS window. Do not lower "
         "the bar.")

CONFIGS: tuple[dict[str, Any], ...] = (
    {"label": "factor-only/0", "roles": ("data", "factor"), "rounds": 0},
    {"label": "factor+risk/0", "roles": ("data", "factor", "risk"), "rounds": 0},
    {"label": "factor-only/1", "roles": ("data", "factor"), "rounds": 1},
    {"label": "factor+risk/1", "roles": ("data", "factor", "risk"), "rounds": 1},
    {"label": "factor+risk/2", "roles": ("data", "factor", "risk"), "rounds": 2},
)

F_REV = '''def factor(closes, tickers, dates, i):
    if i < 1:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 1]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = -(a / b - 1.0)
    return out
'''

BULL = json.dumps({"side": "bull", "claims": [
    {"kind": "mechanism",
     "statement": "short-term reversal is a documented cross-sectional effect "
                  "and the candidate clears its pre-registered bar",
     "checkable": False, "check": None},
    {"kind": "robustness",
     "statement": "the signal keeps its sign across sub-windows",
     "checkable": True, "check": "halves_stability"}]})

BEAR = json.dumps({"side": "bear", "claims": [
    {"kind": "robustness",
     "statement": "the signal is unstable across sub-windows — a lucky full "
                  "sample over two disagreeing halves",
     "checkable": True, "check": "halves_stability"},
    {"kind": "statistical",
     "statement": "one more mining trial in a family that has seen many",
     "checkable": False, "check": None}]})


def hypothesis(oos_window: str) -> str:
    return json.dumps({
        "mechanism": "1-day cross-sectional short-term reversal: yesterday's "
                     "losers outperform today",
        "falsifiable_condition": "mean rank IC <= 0",
        "oos_window": oos_window,
        "admission": {
            "required_metrics": ["rankic_mean", "rankic_tstat",
                                 "quintile_spread", "monotonicity_proxy",
                                 "n_dates"],
            "thresholds": {"rankic_mean": {"op": ">=", "value": 0.02}},
            "min_observations": 10}})


def policy_queue(oos_window: str, rounds: int, budget: int = 3) -> list[str]:
    """One scripted persona policy, identical across all configurations."""
    iteration = [hypothesis(oos_window), F_REV]
    if rounds:
        iteration += [BULL, BEAR] * rounds
    return iteration * budget


def run_one(work: Path, snapshot_dir: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    frame = engine.load_frame(snapshot_dir)
    ds = frame.dates
    oos = f"{ds[-15]}:{ds[-1]}"
    llm = ScriptedLLM(policy_queue(oos, cfg["rounds"]),
                      run_log=work.parent / f"{work.name}-runs.jsonl")
    family = re.sub(r"[^a-z0-9_-]", "-", f"abl-{cfg['label']}")
    return run_order(work, snapshot_dir, ORDER, llm, budget=3,
                     family=family, roles=cfg["roles"],
                     debate_rounds=cfg["rounds"], verbose=False)


def run_ablation(out_dir: Path, *,
                 configs: tuple[dict[str, Any], ...] = CONFIGS,
                 planted_seeds: tuple[int, ...] = (11, 22, 33),
                 noise_seeds: tuple[int, ...] = tuple(range(1, 9)),
                 verbose: bool = False) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenarios: list[dict[str, Any]] = []
    for seed in planted_seeds:
        d = out_dir / f"planted-{seed}"
        if not d.exists():
            build_snapshot(d, seed=seed, tickers=12, days=90,
                           plant={"effect": "reversal",
                                  "strength": PLANT_STRENGTH})
        scenarios.append({"kind": "planted", "seed": seed, "dir": d,
                          "metric": "discovery"})
    for seed in noise_seeds:
        d = out_dir / f"noise-{seed}"
        if not d.exists():
            build_snapshot(d, seed=seed, tickers=12, days=90)
        scenarios.append({"kind": "noise", "seed": seed, "dir": d,
                          "metric": "false_positive"})

    log = print if verbose else (lambda *a, **k: None)
    rows: list[dict[str, Any]] = []
    for cfg in configs:
        row: dict[str, Any] = {"config": cfg["label"], "roles": list(cfg["roles"]),
                               "rounds": cfg["rounds"],
                               "discovery": [0, 0], "false_positive": [0, 0],
                               "trials": {"planted": [], "noise": []},
                               "blocked": {}}
        for sc in scenarios:
            work = out_dir / "runs" / f"{cfg['label'].replace('/', '-')}-{sc['kind']}-{sc['seed']}"
            if work.exists():
                raise ValueError(f"{work} already exists — ablation needs a "
                                 f"fresh tree (determinism)")
            summary = run_one(work, sc["dir"], cfg)
            admitted = bool(summary["admitted"])
            row[sc["metric"]][0] += int(admitted)
            row[sc["metric"]][1] += 1
            row["trials"][sc["kind"]].append(len(summary["iterations"]))
            for r in summary["iterations"]:
                if r.get("blocked"):
                    stage = r.get("stage", "?")
                    row["blocked"][stage] = row["blocked"].get(stage, 0) + 1
            log(f"  {cfg['label']:16s} {sc['kind']:7s} seed={sc['seed']:<3d} "
                f"admitted={admitted} trials={len(summary['iterations'])}")
        rows.append(row)

    def _rate(c: list[int]) -> str:
        return f"{c[0]}/{c[1]}"

    def _mean(xs: list[int]) -> str:
        return f"{sum(xs) / len(xs):.2f}" if xs else "-"

    lines = [
        "| config | roles | debate rounds | discovery (planted) | "
        "false positives (noise) | mean trials planted | mean trials noise |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['config']} | {'+'.join(r['roles'])} | {r['rounds']} | "
            f"{_rate(r['discovery'])} | {_rate(r['false_positive'])} | "
            f"{_mean(r['trials']['planted'])} | {_mean(r['trials']['noise'])} |")
    table = "\n".join(lines)
    (out_dir / "table.md").write_text(table + "\n", encoding="utf-8")
    return {"rows": rows, "table": table, "out_dir": out_dir}
