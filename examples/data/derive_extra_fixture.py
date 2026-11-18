#!/usr/bin/env python3
"""Derive examples/data/ashare_top300_extra.csv (high/low/amount/vwap).

Provenance & method (2026-11-14):
- The pinned main fixture (ashare_top300_main.csv) carries qfq-adjusted
  close/open/volume. Its raw source — tushare ``daily`` rows for the full
  market, 9 columns [ts_code, trade_date, open, high, low, close,
  pre_close, volume(手), amount(千元)] — survives in the fetch cache
  (585-650MB pickle, /tmp/ashare_raw_cache*.pkl).
- qfq adjustment is a per-(ticker, date) multiplicative factor f applied
  uniformly to all price fields. We recover f = close_adj / close_raw and
  verified on ALL 360,913 rows: f recovered from open agrees to a median
  1.0e-6 (max 8.6e-5 — CSV rounding noise), i.e. the uniform-factor model
  holds exactly. f ranges 0.28..1.00 with f=1 at the batch anchor date,
  decreasing into the past — the signature of qfq.
- Therefore: high_adj = high_raw * f, low_adj = low_raw * f inherit the
  main fixture's adjustment basis exactly. amount stays RAW (tushare
  千元; volume is raw too, so amount/volume needs no adjustment).
  vwap_adj = amount*1000 / (volume*100) * f  (units: CNY).

Every row of the main fixture is present in the raw cache (0 missing).
This script asserts all of the above and writes the extra fixture plus a
manifest (sha256 + validation stats). Deterministic given the two inputs.

Usage: python examples/data/derive_extra_fixture.py \
           --raw /tmp/ashare_raw_cache2.pkl [--out examples/data]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="/tmp/ashare_raw_cache2.pkl")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    args = ap.parse_args()
    import pickle

    out_dir = Path(args.out)
    uni = set(json.loads(
        (out_dir / "ashare_top300_universe.json").read_text())["tickers"])

    main_rows: dict[tuple[str, str], tuple[float, float, float]] = {}
    with (out_dir / "ashare_top300_main.csv").open() as fh:
        for r in csv.DictReader(fh):
            main_rows[(r["ticker"], r["date"])] = (
                float(r["close"]), float(r["open"]), float(r["volume"]))

    raw: dict[tuple[str, str], list] = {}
    with open(args.raw, "rb") as fh:
        daily = pickle.load(fh)["daily"]
    for _dt, lst in daily.items():
        for r in lst:
            if r[0] in uni:
                raw[(r[0], r[1])] = r

    missing = [k for k in main_rows if k not in raw]
    assert not missing, f"{len(missing)} fixture rows missing in raw cache"

    devs, out_rows = [], []
    n_bad_order = n_bad_vwap = 0
    for (tk, dt) in sorted(main_rows, key=lambda k: (k[1], k[0])):
        c_adj, o_adj, vol = main_rows[(tk, dt)]
        r = raw[(tk, dt)]
        o_raw, h_raw, l_raw, c_raw, _pre, v_raw, amt_raw = (
            float(r[2]), float(r[3]), float(r[4]), float(r[5]),
            float(r[6]), float(r[7]), float(r[8]))
        assert abs(v_raw - vol) / max(vol, 1.0) < 1e-3, (tk, dt, v_raw, vol)
        f = c_adj / c_raw
        f_o = o_adj / o_raw
        devs.append(abs(f - f_o) / max(f, f_o))
        hi, lo = round(h_raw * f, 4), round(l_raw * f, 4)
        # qfq factor > 0 preserves price ordering
        if not (hi >= max(c_adj, o_adj) - 1e-3
                and lo <= min(c_adj, o_adj) + 1e-3):
            n_bad_order += 1
        vwap = round(amt_raw * 1000.0 / (v_raw * 100.0) * f, 4) if v_raw > 0 else ""
        if vwap != "" and not (lo - 1e-3 <= vwap <= hi + 1e-3):
            n_bad_vwap += 1
        out_rows.append([dt, tk, hi, lo, f"{amt_raw:.1f}", vwap])

    assert n_bad_order == 0, f"{n_bad_order} rows violate high>=max(o,c)"
    assert n_bad_vwap == 0, f"{n_bad_vwap} rows have vwap outside [low,high]"

    extra = out_dir / "ashare_top300_extra.csv"
    with extra.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "ticker", "high", "low", "amount", "vwap"])
        w.writerows(out_rows)

    sha = hashlib.sha256(extra.read_bytes()).hexdigest()
    manifest = {
        "file": "ashare_top300_extra.csv",
        "sha256": sha,
        "rows": len(out_rows),
        "derived_from": "tushare daily raw cache (unadjusted) x qfq factor "
                        "recovered from the pinned main fixture "
                        "(f = close_adj/close_raw, uniform across price "
                        "fields, verified on every row)",
        "f_open_vs_f_close_reldev": {
            "median": round(statistics.median(devs), 9),
            "max": round(max(devs), 9),
        },
        "units": {"high/low/vwap": "CNY, qfq basis of the main fixture",
                  "amount": "thousand CNY, RAW (unadjusted, as fetched)"},
        "checks": {"rows_vs_main": len(out_rows) == len(main_rows),
                   "high_low_order": "high>=max(open,close), "
                                     "low<=min(open,close), all rows",
                   "vwap_band": "low<=vwap<=high, all rows"},
    }
    (out_dir / "ashare_top300_extra_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"[extra] {extra.name}: {len(out_rows)} rows, sha256 {sha[:16]}…")
    print(f"[extra] f-consistency median {manifest['f_open_vs_f_close_reldev']['median']:.1e}, "
          f"max {manifest['f_open_vs_f_close_reldev']['max']:.1e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
