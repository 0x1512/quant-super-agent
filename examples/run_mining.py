#!/usr/bin/env python3
"""Offline mining-loop demo — an LLM proposes hypotheses and factor code; the
ledger disciplines them. Deterministic (ScriptedLLM), no network, no keys.

The scripted "LLM" behaves like a real one under pressure: iteration 3
quietly lowers the admission bar to rescue the rejected momentum direction.
Watch the ledger's Bonferroni floor catch it anyway — that is the demo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa.llm import ScriptedLLM  # noqa: E402
from qsa.mining import run_order  # noqa: E402
from qsa.snapshot import build_snapshot  # noqa: E402

ORDER = ("Mine one cross-sectional factor on this snapshot: propose a "
         "hypothesis with a pre-registered admission bar (mean daily rank "
         "IC >= 0.02), implement it, and report the mechanical verdict. "
         "Do not lower the bar, do not trim windows.")

H1 = '{"mechanism": "10-day momentum continuation: trailing winners outperform next session", "falsifiable_condition": "mean rank IC <= 0", "admission": {"required_metrics": ["rankic_mean", "rankic_tstat", "quintile_spread", "monotonicity_proxy", "n_dates"], "thresholds": {"rankic_mean": {"op": ">=", "value": 0.02}}, "min_observations": 30}}'

F1 = '''def factor(closes, tickers, dates, i):
    if i < 10:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 10]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = a / b - 1.0
    return out'''

H2 = '{"mechanism": "3-day short-term reversal: recent losers bounce next session", "falsifiable_condition": "mean rank IC >= 0", "admission": {"required_metrics": ["rankic_mean", "rankic_tstat", "quintile_spread", "monotonicity_proxy", "n_dates"], "thresholds": {"rankic_mean": {"op": "<=", "value": -0.02}}, "min_observations": 30}}'

F2 = '''def factor(closes, tickers, dates, i):
    if i < 3:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 3]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = -(a / b - 1.0)
    return out'''

H3 = ('{"mechanism": "20-day momentum: slower lookback captures the trend the 10-day version missed", '
      '"falsifiable_condition": "mean rank IC <= 0", '
      '"admission": {"required_metrics": ["rankic_mean", "rankic_tstat", "quintile_spread", "monotonicity_proxy", "n_dates"], '
      '"thresholds": {"rankic_mean": {"op": ">=", "value": 0.003}}, "min_observations": 30}}')

F3 = '''def factor(closes, tickers, dates, i):
    if i < 20:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 20]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = a / b - 1.0
    return out'''


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "work"
    work = root / "mining"
    snapshot_dir = root / "mining-snapshot"
    import shutil
    for d in (work, snapshot_dir):
        if d.exists():
            shutil.rmtree(d)
    build_snapshot(snapshot_dir, seed=42, tickers=12, days=90)

    llm = ScriptedLLM([H1, F1, H2, F2, H3, F3], run_log=work / "runs.jsonl")
    summary = run_order(work, snapshot_dir, ORDER, llm, budget=3,
                        family="demo-mining")

    print("\niteration ledger:")
    for r in summary["iterations"]:
        if r.get("blocked"):
            print(f"  it{r['iteration']}: BLOCKED at {r['stage']}: "
                  f"{str(r['blocked'])[:100]}")
        else:
            print(f"  it{r['iteration']}: {r.get('exp_id')} verdict="
                  f"{r.get('verdict')} N={r.get('n_trials')} "
                  f"attribution={r.get('attribution', {}).get('class')}")
    print(f"\nfinal_verdict: {summary['final_verdict']} — an honest negative "
          f"chain under budget, every card gate-checked and settled.")
    # regression contract: it1 misses the pre-registered bar, it2/it3 are the
    # bar-lowering retries the deflation floor rejects; nothing merges.
    expected = ["threshold_miss", "deflation", "deflation"]
    got = [r.get("attribution", {}).get("class") for r in summary["iterations"]
           if not r.get("blocked")]
    if summary["final_verdict"] != "fail" or got != expected:
        print(f"REGRESSION: expected {expected} -> fail, got {got} -> "
              f"{summary['final_verdict']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
