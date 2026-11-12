#!/usr/bin/env python3
"""v0.5 acceptance — the settlement ledger and the calibration curve.

Sweeps worlds (planted reversals of varying strength + pure noise), runs the
production stack (data+factor+risk roles, 1 debate round) on each, settles
every admitted claim on a 90-day horizon the admission never touched, and
emits the claimed-vs-realized calibration curve.

Honest expectations, stated before the run:
- planted-world admissions should mostly *hold* (the effect is real and the
  generator continues it — weaker plants settle noisier);
- the horizon is 90 days, as long as the claim's own window: measured, a
  pure-noise world centers on realized ~0 there (per-claim verdicts stay
  noisy — the aggregate curve is the instrument);
- >= 50 settled claims is the acceptance bar (exit 1 otherwise).

Deterministic end to end: same seeds, same bytes, ~20 s, fully offline.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa.settlement import (MIN_SETTLED, admission_multiplier,
                            run_calibration_sweep)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    out = root / "work" / "calibration"
    if out.exists():
        print(f"{out} already exists — remove it for a fresh deterministic run")
        return 1

    t0 = time.time()
    result = run_calibration_sweep(out, verbose=True)
    ledger, report = result["ledger"], result["report"]
    print(f"audit: {len(ledger.entries)} entries, chain + realized metrics "
          f"recompute clean")
    print(result["markdown"])

    # the reflection rule the ledger would demand of follow-up orders
    mult, basis = admission_multiplier(ledger, "abl-cal")
    print(f"reflection rule for family 'abl-cal' follow-ups: x{mult} — "
          f"{basis}")

    if report["n_settled"] < MIN_SETTLED:
        print(f"ACCEPTANCE FAILED: {report['n_settled']} settled claims "
              f"< {MIN_SETTLED}")
        return 1
    print(f"acceptance met: {report['n_settled']} settled claims "
          f"(>= {MIN_SETTLED}) in {time.time() - t0:.1f}s")
    print(f"artifacts: {out / 'settlement.jsonl'}, {out / 'calibration.md'}, "
          f"{out / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
