"""Offline lifecycle demo: order -> hypothesis -> experiment -> gate -> PR.

Runs the whole evidence lifecycle against the deterministic forge in a
scratch directory, in seconds, with zero network:

1. build a synthetic snapshot (seeded; byte-identical on rerun)
2. open the research order as a forge issue
3. register the hypothesis card (pre-registered admission criteria)
4. run the toy momentum engine on the snapshot
5. write the experiment card with the *mechanically evaluated* verdict —
   honest by construction, and the toy data is momentum-hostile, so the
   demo's honest outcome is usually ``fail``
6. commit cards to a branch, push (the post-receive hook runs the verify
   gate as CI), open a PR, report back on the order issue
7. merge — allowed only if the gate is green (branch protection)

With ``--fib CLASS`` the demo injects a fabrication of that FIB class into
the E card before committing, and the gate must block the merge. Exit code 0
means the lifecycle behaved correctly (including "gate blocked the fake").
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import admission, engine, snapshot
from .forge import Forge
from .snapshot import canonical_json

ROOT = Path(__file__).resolve().parents[1]
FIB_CLASSES = ["1", "4", "7", "14", "15"]

ORDER_BODY = """Research order: momentum rank-IC pilot.

Evaluate 10-day cross-sectional momentum (rank IC of trailing return vs
next-day forward return) over the full snapshot window. Register the
hypothesis before computing. Report the mechanically evaluated verdict,
whatever it is. Do not tune, retry, or trim the window."""

HYPOTHESIS = {
    "schema": "hypothesis",
    "hyp_id": "H-0001",
    "mechanism": "Trailing 10-day winners outperform losers cross-sectionally "
                 "over the next session (underreaction continuation).",
    "falsifiable_condition": "Mean daily Spearman rank IC between the "
                              "trailing-10d return signal and next-day forward "
                              "return is <= 0 over the window.",
    "admission": {
        "required_metrics": ["rankic_mean", "rankic_tstat", "quintile_spread",
                             "monotonicity_proxy", "n_dates"],
        "thresholds": {
            "rankic_mean": {"op": ">=", "value": 0.02},
            "quintile_spread": {"op": ">=", "value": 0.0},
        },
        "min_observations": 30,
    },
    "window": None,  # filled from the snapshot
    "ttl_days": 90,
    "status": "registered",
    "created_at": None,  # snapshot as_of (deterministic: no wall clock)
}


def _fmt_metric_line(metrics: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(metrics.items()))


def _apply_fib(e_card: dict[str, Any], fib: str, dates: list[str]) -> str:
    """Mutate the E card per FIB class; returns a human label."""
    if fib == "1":       # missing-field
        del e_card["verdict"]
        return "FIB 1 missing-field: E card drops 'verdict'"
    if fib == "4":       # snapshot-mismatch
        e_card["snapshot_hash"] = "0" * 64
        return "FIB 4 snapshot-mismatch: card cites a nonexistent snapshot sha"
    if fib == "7":       # silent-pass
        e_card["verdict"] = "pass"
        return "FIB 7 silent-pass: failing metrics marked verdict=pass"
    if fib == "14":      # partial-metrics
        e_card["metrics"].pop("quintile_spread")
        return "FIB 14 partial-metrics: unfavourable metric omitted"
    if fib == "15":      # window-shrink
        mid = dates[len(dates) // 2]
        start, _, _ = e_card["window"].partition(":")
        e_card["window"] = f"{start}:{mid}"
        return "FIB 15 window-shrink: evaluation window trimmed to the friendly stretch"
    raise ValueError(f"unknown FIB class {fib!r}")


def run_lifecycle(work: Path, fib: str | None = None,
                  verbose: bool = True) -> dict[str, Any]:
    work = Path(work)
    if work.exists():
        raise ValueError(f"workdir {work} already exists; remove it first "
                         f"(determinism requires a fresh start)")
    log = print if verbose else (lambda *a, **k: None)

    # 1) snapshot
    info = snapshot.build_snapshot(work / "snapshot", seed=42, tickers=12, days=90)
    window = f"{info.manifest['start']}:{info.manifest['as_of']}"
    as_of_iso = f"{info.manifest['as_of'][:4]}-{info.manifest['as_of'][4:6]}-{info.manifest['as_of'][6:]}"
    log(f"[1] snapshot   toy synthetic, {info.manifest['rows']} rows, "
        f"window {window}, sha {info.manifest_hash[:12]}…")

    # 2) order as issue
    forge = Forge.init(work / "forge")
    order = forge.create_issue("Order: momentum rank-IC pilot", ORDER_BODY)
    log(f"[2] order      issue #{order}")

    # 3) hypothesis card (pre-registered)
    h = dict(HYPOTHESIS)
    h["window"] = window
    h["created_at"] = as_of_iso
    cards = work / "cards"
    cards.mkdir(parents=True)
    (cards / "H-0001.json").write_bytes(canonical_json(h) + b"\n")
    log(f"[3] hypothesis H-0001 registered (admission pre-committed)")

    # 4) experiment
    result = engine.run(str(work / "snapshot"), k=10, window=window)
    verdict, reasons = admission.evaluate(h["admission"], result["metrics"])

    e = {
        "schema": "experiment_result",
        "exp_id": "E-0001",
        "hyp_id": "H-0001",
        "window": window,
        "snapshot_hash": info.manifest_hash,
        "engine": engine.ENGINE_ID,
        "metrics": result["metrics"],
        "attribution": result["attribution"],
        "verdict": verdict,
        "settled_at": as_of_iso,
    }
    injected = None
    if fib:
        dates = sorted({ln.split(",")[0] for ln in
                        (work / "snapshot" / "daily" / "prices.csv")
                        .read_text().splitlines()[1:]})
        injected = _apply_fib(e, fib, dates)
        log(f"[4] INJECTION {injected}")

    (cards / "E-0001.json").write_bytes(canonical_json(e) + b"\n")
    log(f"[5] experiment E-0001  {_fmt_metric_line(e['metrics'])}")
    log(f"    honest verdict = {verdict} ({'; '.join(reasons)})")

    # 6) commit -> push (CI = verify gate) -> PR -> report -> merge
    branch = "research/H-0001"
    sha = forge.commit(branch, "cards: H-0001 + E-0001", {
        "cards/H-0001.json": (cards / "H-0001.json").read_text("utf-8"),
        "cards/E-0001.json": (cards / "E-0001.json").read_text("utf-8"),
    })
    ci_cmd = [sys.executable, "-m", "qsa.verify",
              "--hypothesis", str(cards / "H-0001.json"),
              "--result", str(cards / "E-0001.json"),
              "--snapshot", str(work / "snapshot")]
    check = forge.push(branch, ci_cmd, cwd=ROOT)
    log(f"[6] push       {branch[:20]}… sha {sha[:10]} -> CI '{check['name']}' "
        f"= {check['conclusion']}")

    pr = forge.create_pr(f"H-0001: momentum rank-IC pilot "
                         f"({'FIB ' + fib + ' injected' if fib else 'honest run'})",
                         head=branch)
    forge.add_comment(order, (
        f"E-0001 settled. verdict={e.get('verdict')}. "
        f"CI verify: {check['conclusion']}."
        + (f" Injected: {injected}" if injected else "")))
    merged = forge.merge_pr(pr)
    log(f"[7] merge      {'MERGED' if merged else 'BLOCKED by branch protection'}")

    return {"merged": merged, "check": check, "verdict": e.get("verdict"),
            "snapshot_hash": info.manifest_hash, "pr": pr}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", default=str(ROOT / "work"),
                        help="scratch workdir (default: ./work; must not exist)")
    parser.add_argument("--fib", choices=FIB_CLASSES, default=None,
                        help="inject a fabrication of this FIB class and "
                             "require the gate to block it")
    args = parser.parse_args(argv)

    summary = run_lifecycle(Path(args.work), fib=args.fib)

    if args.fib:
        ok = (not summary["merged"]) and summary["check"]["conclusion"] == "failure"
        print(f"\nFIB {args.fib} outcome: "
              f"{'GATE CAUGHT IT (merge blocked)' if ok else '!!! GATE FAILED TO BLOCK'}")
        return 0 if ok else 1
    print(f"\nlifecycle complete: merged={summary['merged']}, "
          f"verdict={summary['verdict']}, ci={summary['check']['conclusion']}")
    return 0 if summary["merged"] else 1


if __name__ == "__main__":
    sys.exit(main())
