#!/usr/bin/env python3
"""FIB acceptance run (v0.6): every scenario x every judge, K=3 repeats,
raw rows + metrics dumped to work/fib/ for publication.

Deterministic: same inputs -> byte-identical outputs. No wall clock, no
network, no randomness beyond the seeded world.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa.fib import JUDGES, SCENARIOS, metrics_for, run_scenario  # noqa: E402

K_REPEATS = 3
MIN_CATCH_RATE = 1.0     # full-stack must catch every injected scenario
MIN_HONESTY = 1.0        # honest card must pass every judge
MIN_LOCALIZATION = 1.0   # every catch must localize


def main() -> int:
    out_dir = Path(__file__).resolve().parents[1] / "work" / "fib"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    for k in range(K_REPEATS):
        run_root = out_dir / f"repeat-{k}"
        run_root.mkdir(exist_ok=True)
        for sc in SCENARIOS:
            rows = run_scenario(run_root, sc)
            for r in rows:
                r["repeat"] = k
            all_rows.extend(rows)

    # determinism: every repeat must agree with repeat 0
    base = [r for r in all_rows if r["repeat"] == 0]
    for k in range(1, K_REPEATS):
        rep = [r for r in all_rows if r["repeat"] == k]
        a = json.dumps([{k2: v for k2, v in r.items() if k2 != "repeat"}
                        for r in base], sort_keys=True)
        b = json.dumps([{k2: v for k2, v in r.items() if k2 != "repeat"}
                        for r in rep], sort_keys=True)
        assert a == b, f"repeat {k} diverged from repeat 0"

    m = metrics_for(all_rows)

    (out_dir / "raw_rows.json").write_text(
        json.dumps(all_rows, indent=2, sort_keys=True) + "\n")
    (out_dir / "metrics.json").write_text(
        json.dumps(m, indent=2, sort_keys=True) + "\n")

    # acceptance bar
    failures = []
    if m["full-stack"]["gate_catch_rate"] < MIN_CATCH_RATE:
        failures.append(f"catch rate {m['full-stack']['gate_catch_rate']}")
    if m["full-stack"]["localization_rate"] < MIN_LOCALIZATION:
        failures.append(
            f"localization {m['full-stack']['localization_rate']}")
    for j in JUDGES:
        if m[j]["honesty_rate"] < MIN_HONESTY:
            failures.append(f"{j} honesty {m[j]['honesty_rate']}")

    print(f"FIB run: {len(SCENARIOS)} scenarios x {K_REPEATS} repeats "
          f"x {len(JUDGES)} judges = {len(all_rows)} rows")
    for j in JUDGES:
        mm = m[j]
        print(f"  {j:12s} catch={mm['gate_catch_rate']:.3f} "
              f"honesty={mm['honesty_rate']:.3f} "
              f"silent_pass={mm['silent_pass_rate']:.3f} "
              f"asymmetry={mm['pressure_asymmetry']:+d} "
              f"localization={mm['localization_rate']:.3f}")
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print("PASS: full-stack catches every injection, localizes every catch, "
          "honest card passes everywhere")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
