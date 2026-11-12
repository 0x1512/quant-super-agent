#!/usr/bin/env python3
"""v0.4 acceptance demo — the ablation table, produced mechanically.

Planted worlds carry a real but modest 1-day reversal (strength 0.15 → the
policy's reversal factor sits around rank IC ≈ 0.13); noise worlds carry
nothing. The persona policy is IDENTICAL in every configuration, so any
difference between rows is the gating machinery — risk veto, bull/bear
debate — not a smarter script. Deterministic, offline, ~1-2 minutes.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa.ablation import run_ablation  # noqa: E402

root = Path(__file__).resolve().parents[1] / "work" / "ablation"
if root.exists():
    shutil.rmtree(root)

result = run_ablation(root, verbose=True)

print("\n" + result["table"])
print(f"\ntable written to {result['out_dir'] / 'table.md'}")
print("\nReading the table: the policy never changes — only the machinery "
      "does.\nDiscovery on planted worlds shows what a layer costs; false "
      "positives on\nnoise worlds show what it buys.")
