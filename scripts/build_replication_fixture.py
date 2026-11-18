#!/usr/bin/env python3
"""Build the v1.0-A replication fixtures from the raw tushare cache.

Turns scripts/fetch_ashare_raw.py's cache (full-market daily bars,
2021-01..2026-10, unadjusted, with preclose) into the repo's deterministic
fixtures:

* ``examples/data/ashare_top300_main.csv`` — date,ticker,close,open,volume,
  hfq-normalized, 2021-07-01..2026-06-30 (the replication sample);
* ``examples/data/ashare_top300_tail.csv``  — the same columns for
  2026-07-01..2026-09-30 (the real-data settlement horizon, A9);
* ``examples/data/replication_meta/monthly_caps.csv`` — month,ticker,
  cap_proxy for the neutralization variants (A6), where cap_proxy is the
  mean daily amount (turnover, in thousand CNY) of that ticker in that
  month, computed from the cached raw bars — no network call.

Design choices, all recorded because they ARE the conventions (A4):
* universe: top-300 by mean daily amount over 2021-H1, needing >= 100 bars
  in that window — chosen from the data itself so anyone can rebuild the
  identical set; ST stocks effectively never reach this turnover tier
  (and the residual risk is declared, not hidden);
* adjustment: preclose-chained hfq. F_t = F_{t-1} * preclose_t/close_{t-1};
  open/close are multiplied by F. Then ln(open_t/preclose_t) is the exact
  adjusted overnight return and daily returns match tushare's pct_chg —
  no separate adjustment-factor interface (rate-limited on our token);
* everything is sorted and formatted with fixed precision so the CSVs are
  byte-stable for identical upstream data.

The size factor for neutralization uses mean daily amount as a market-cap
proxy: the tushare ``daily_basic`` interface (total_mv) is rate-limited to
~1 call/hour on this project's token, so 63 month-end cross-sections are
not fetchable in any reasonable time. The proxy is computed offline from
the cached raw bars (amount is already in every daily row) and the
substitution is declared in the H card's convention table (A4). Industries
come from a single ``stock_basic`` call, cached in
/tmp/ashare_meta_cache.pkl.
"""
import csv
import json
import os
import pickle
import time
import urllib.error
import urllib.request
from pathlib import Path

TOKEN = os.environ.get("TUSHARE_TOKEN", "")
if not TOKEN:
    raise SystemExit("set TUSHARE_TOKEN in the environment "
                     "(tokens never live in the repo)")
RAW = Path("/tmp/ashare_raw_cache2.pkl")
META = Path("/tmp/ashare_meta_cache.pkl")
OUT = Path(__file__).resolve().parents[1] / "examples" / "data"

SELECT_START, SELECT_END = "20210104", "20210630"   # universe window
MAIN_START, MAIN_END = "20210701", "20260630"       # replication sample
TAIL_START, TAIL_END = "20260701", "20260930"       # settlement horizon
TOP_N = 300
MIN_BARS = 100


def call(api, params, fields=""):
    backoff = 65  # daily_basic is 1/min on this token; other APIs rarely need it
    for attempt in range(15):
        try:
            req = urllib.request.Request(
                "http://api.tushare.pro",
                data=json.dumps({"api_name": api, "token": TOKEN,
                                 "params": params, "fields": fields}).encode(),
                headers={"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            if r["code"] == 0:
                return r["data"]["items"]
            msg = str(r.get("msg", ""))
            if "频率超限" in msg or "超频" in msg or "每小时" in msg or "每分钟" in msg:
                time.sleep(backoff)
                backoff = min(backoff * 2, 600)
                continue
            raise RuntimeError(f"{api}: {msg}")
        except (urllib.error.URLError, TimeoutError):
            time.sleep(backoff)
            backoff = min(backoff * 2, 600)
    raise RuntimeError(f"{api}: exhausted retries {params}")


def load_raw():
    state = pickle.load(RAW.open("rb"))
    by_date = state["daily"]  # {yyyymmdd: [[ts_code, date, open, high, low, close, preclose, vol, amount], ...]}
    return by_date


def series_of(by_date, ts_codes=None):
    """{ticker: [(date, open, close, preclose, vol, amount)]} sorted by date."""
    out: dict[str, list] = {}
    for d in sorted(by_date):
        for row in by_date[d]:
            tk, _, o, _h, _l, c, pc, v, amt = row
            if ts_codes is not None and tk not in ts_codes:
                continue
            out.setdefault(tk, []).append((d, o, c, pc, v, amt))
    return out


def hfq(rows):
    """preclose-chained hfq rows -> [(date, hfq_open, hfq_close, vol)]."""
    out = []
    f = 1.0
    prev_close = None
    for d, o, c, pc, v, _amt in rows:
        if prev_close and prev_close > 0 and pc and pc > 0:
            f *= pc / prev_close
        out.append((d, o * f if o else 0.0, c * f if c else 0.0, v or 0))
        prev_close = c
    return out


def main():
    by_date = load_raw()
    all_series = series_of(by_date)
    print(f"raw tickers: {len(all_series)}")

    # universe: mean amount over the selection window
    scores = []
    for tk, rows in all_series.items():
        w = [r for r in rows if SELECT_START <= r[0] <= SELECT_END]
        if len(w) >= MIN_BARS:
            scores.append((sum(r[5] for r in w) / len(w), tk))
    scores.sort(reverse=True)
    universe = sorted(tk for _, tk in scores[:TOP_N])
    print(f"universe: {len(universe)} tickers (top by 2021H1 mean amount)")

    sel = series_of(by_date, set(universe))
    main_rows, tail_rows = [], []
    for tk in universe:
        for d, o, c, v in hfq(sel[tk]):
            if o <= 0 or c <= 0:
                continue
            if MAIN_START <= d <= MAIN_END:
                main_rows.append((d, tk, f"{c:.4f}", f"{o:.4f}", str(int(v))))
            elif TAIL_START <= d <= TAIL_END:
                tail_rows.append((d, tk, f"{c:.4f}", f"{o:.4f}", str(int(v))))
    main_rows.sort(key=lambda r: (r[0], r[1]))
    tail_rows.sort(key=lambda r: (r[0], r[1]))
    print(f"main rows: {len(main_rows)}, tail rows: {len(tail_rows)}")

    OUT.mkdir(parents=True, exist_ok=True)
    header = ["date", "ticker", "close", "open", "volume"]
    for name, rows in (("ashare_top300_main.csv", main_rows),
                       ("ashare_top300_tail.csv", tail_rows)):
        p = OUT / name
        with p.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(header)
            w.writerows(rows)
        print(f"wrote {p} ({p.stat().st_size/1e6:.1f} MB)")

    # ---- meta: cap_proxy = mean daily amount (offline, from raw cache);
    # industry from the cached single stock_basic call ----
    state = pickle.load(META.open("rb")) if META.exists() else {}
    months = sorted({r[0][:6] for r in main_rows} | {r[0][:6] for r in tail_rows})
    uni = set(universe)
    # (month, ticker) -> [sum(amount), n_days] over the *unadjusted* raw rows
    amt_acc: dict[tuple[str, str], list[float]] = {}
    for tk in universe:
        for d, _o, _c, _pc, _v, amt in sel[tk]:
            m = d[:6]
            if m in set(months):
                acc = amt_acc.setdefault((m, tk), [0.0, 0])
                acc[0] += amt or 0.0
                acc[1] += 1
    if "industry" not in state:
        if os.environ.get("QSA_FETCH_INDUSTRY"):
            rows = call("stock_basic", {"exchange": "", "list_status": "L"},
                        "ts_code,industry")
            state["industry"] = {r[0]: r[1] for r in rows}
            pickle.dump(state, META.open("wb"))
        else:
            state["industry"] = {}
            print("NOTE: no cached industries and QSA_FETCH_INDUSTRY unset — "
                  "industries.csv will be omitted (cap+industry variant "
                  "degrades to cap; declared, not hidden)", flush=True)

    # meta lands in examples/data/replication_meta/ as the two CSVs the
    # loader expects (qsa.replication.load_monthly_meta); ingest copies
    # them into the snapshot and pins them by sha256
    meta_dir = OUT / "replication_meta"
    meta_dir.mkdir(exist_ok=True)
    with (meta_dir / "monthly_caps.csv").open("w", encoding="utf-8",
                                              newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["month", "ticker", "cap_proxy"])
        for m in months:
            for tk in sorted(uni):
                acc = amt_acc.get((m, tk))
                if acc and acc[1]:
                    w.writerow([m, tk, f"{acc[0] / acc[1]:.2f}"])
    if state.get("industry"):
        with (meta_dir / "industries.csv").open("w", encoding="utf-8",
                                                newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["ticker", "industry"])
            for tk in sorted(uni):
                w.writerow([tk, state["industry"].get(tk, "?")])
        print("meta written (replication_meta/monthly_caps.csv + industries.csv)")
    else:
        print("meta written (replication_meta/monthly_caps.csv only; "
              "industries unavailable — see NOTE above)")

    (OUT / "ashare_top300_universe.json").write_text(
        json.dumps({"rule": f"top {TOP_N} by mean daily amount "
                       f"{SELECT_START}..{SELECT_END}, >= {MIN_BARS} bars",
                    "tickers": universe}, indent=1), encoding="utf-8")
    print("universe json written")


if __name__ == "__main__":
    main()
