#!/usr/bin/env python3
"""Engine throughput benchmark — legacy vs matrix vs matrix+parallel.

Reproduce with ``python tools/bench_engine.py``. Numbers are sealed to
``docs/loops/bench_engine.json`` for the evidence trail (storefront
policy: measurements never go in the README, they live in the loops).

With numpy absent the matrix paths degrade to the stdlib engine and
the benchmark reports the fallback (exit 0) — the CI matrix stays
dependency-free on purpose.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qsa import factorzoo, snapshot                     # noqa: E402
from qsa.halving import successive_halving              # noqa: E402
from qsa.ingest import ingest_csv                       # noqa: E402
from qsa.matrix import HAVE_NUMPY, evaluate_factor_fast  # noqa: E402
from qsa.parallel import evaluate_specs_parallel        # noqa: E402

FIXTURE = ROOT / "examples" / "data"
OUT = ROOT / "docs" / "loops" / "bench_engine.json"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="bench-") as td:
        snap = Path(td) / "snap"
        ingest_csv(FIXTURE / "ashare_top300_main.csv", snap,
                   volume_col="volume", open_col="open",
                   snapshot_id="bench", meta_dir=FIXTURE / "replication_meta")
        closes = snapshot.load_closes(snap)
        opens = snapshot.load_opens(snap)
        volumes = snapshot.load_volumes(snap)
        inputs = {"closes": closes, "opens": opens, "volumes": volumes,
                  "dates": sorted({d for r in closes.values() for d in r})}
        catalog = factorzoo.build_catalog()
        n_dates, n_tickers = len(inputs["dates"]), len(closes)

        # -- legacy stdlib engine ------------------------------------------
        t0 = time.perf_counter()
        rows_legacy = [factorzoo.evaluate_factor(s, inputs) for s in catalog]
        t_legacy = time.perf_counter() - t0

        # -- matrix engine (serial) ----------------------------------------
        t0 = time.perf_counter()
        rows_fast = [evaluate_factor_fast(s, inputs) for s in catalog]
        t_fast = time.perf_counter() - t0

        # -- matrix engine (process pool) ----------------------------------
        t0 = time.perf_counter()
        by_id = evaluate_specs_parallel(catalog, inputs)
        t_par = time.perf_counter() - t0

        # -- halving triage over the same pool ------------------------------
        t0 = time.perf_counter()
        survivors, halving_log = successive_halving(catalog, inputs,
                                                    fractions=(0.25, 0.5),
                                                    keep=0.5, floor=0.0)
        t_halving = time.perf_counter() - t0

        identical = all(a == b for a, b in zip(rows_legacy, rows_fast))
        identical_par = all(by_id[r["id"]] == r for r in rows_legacy)
        workers = max(1, t_fast and round(t_fast / t_par) if t_par else 1)

        print(f"[bench] backend={'numpy' if HAVE_NUMPY else 'stdlib-fallback'}"
              f" panel={n_dates}d x {n_tickers} names x {len(catalog)} factors")
        print(f"[bench] legacy stdlib : {t_legacy:7.2f}s")
        print(f"[bench] matrix serial : {t_fast:7.2f}s"
              f"  ({t_legacy / t_fast:6.1f}x)  identical={identical}")
        print(f"[bench] matrix pool   : {t_par:7.2f}s"
              f"  ({t_legacy / t_par:6.1f}x)  identical={identical_par}")
        print(f"[bench] halving triage: {t_halving:7.2f}s ->"
              f" {len(survivors)}/{len(catalog)} survivors"
              f" (levels: {[e['kept'] for e in halving_log]})")
        if not identical or not identical_par:
            print("[bench] FATAL: results diverge — refusing to seal")
            return 1
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "ran_at": time.time(), "backend": "numpy" if HAVE_NUMPY else
            "stdlib-fallback",
            "panel": {"n_dates": n_dates, "n_tickers": n_tickers,
                      "n_factors": len(catalog)},
            "seconds": {"legacy_serial": round(t_legacy, 3),
                        "matrix_serial": round(t_fast, 3),
                        "matrix_pool": round(t_par, 3),
                        "halving_triage": round(t_halving, 3)},
            "speedup": {"matrix_serial": round(t_legacy / t_fast, 2),
                        "matrix_pool": round(t_legacy / t_par, 2)},
            "results_identical": True,
            "halving": halving_log,
        }, indent=1, sort_keys=True), encoding="utf-8")
        print(f"[bench] sealed -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
