#!/usr/bin/env python3
"""Fetch raw A-share daily bars + adj factors from tushare into a local cache.

Local data-acquisition tool for the v1.0-A replication fixture. Pulls, per
trade date, the full-market `daily` and `adj_factor` rows and appends them to
a pickle cache with a resume marker, so the (rate-limited, ~10 min) fetch can
be interrupted and continued. Deterministic given the same upstream data; the
fixture builder (build_replication_fixture.py) turns this cache into the
fingerprinted CSVs that live in the repo.
"""
import json
import os
import pickle
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

TOKEN = os.environ.get("TUSHARE_TOKEN", "")
if not TOKEN:
    raise SystemExit("set TUSHARE_TOKEN in the environment "
                     "(tokens never live in the repo)")
CACHE = Path("/tmp/ashare_raw_cache2.pkl")  # v2: v1 silently lacked pre_close (wrong field name)
START, END = "20210101", "20261031"
BATCHES = ["daily"]  # adj_factor is 1/hour on this token; preclose (in daily)
#                    already carries the corporate-action info: the fixture
#                    builder chains preclose/close into hfq prices, so no
#                    separate adjustment-factor interface is needed.
FIELDS = {
    "daily": "ts_code,trade_date,open,high,low,close,pre_close,vol,amount",
}
RATE_SLEEP = 1.3  # daily-by-date is capped at 50/min on this token; stay under


def call(api, params, fields=""):
    req = urllib.request.Request(
        "http://api.tushare.pro",
        data=json.dumps({"api_name": api, "token": TOKEN, "params": params, "fields": fields}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=30))


def robust_call(api, params, fields=""):
    for attempt in range(6):
        try:
            r = call(api, params, fields)
            if r["code"] == 0:
                return r["data"]["items"]
            if "频率超限" in str(r.get("msg", "")) or "-4020" in str(r.get("msg", "")):
                time.sleep(20)
                continue
            raise RuntimeError(f"{api}: {r.get('msg')}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{api}: exhausted retries for {params}")


def trade_dates():
    """trade_cal is rate-limited (1/hour) on this token — derive the calendar
    from one stock's full daily series instead (single call, same answer)."""
    rows = robust_call("daily", {"ts_code": "600519.SH",
                                 "start_date": START, "end_date": END},
                       "trade_date")
    return [r[0] for r in rows]


def main():
    dates = trade_dates()
    print(f"trade dates {dates[0]}..{dates[-1]}: {len(dates)}", flush=True)
    if CACHE.exists():
        state = pickle.load(CACHE.open("rb"))
    else:
        state = {"daily": {}}
    done = set(state["daily"])
    todo = [d for d in dates if d not in done]
    print(f"already cached: {len(done)}; to fetch: {len(todo)}", flush=True)
    t0 = time.time()
    for n, d in enumerate(todo, 1):
        for api in BATCHES:
            rows = robust_call(api, {"trade_date": d}, FIELDS[api])
            state[api][d] = rows
        if n % 5 == 0 or n == len(todo):
            tmp = CACHE.with_suffix(".tmp")
            with tmp.open("wb") as fh:
                pickle.dump(state, fh)
            os.replace(tmp, CACHE)  # atomic: a killed run never truncates the cache
            rate = n / (time.time() - t0)
            eta = (len(todo) - n) / max(rate, 1e-9) / 60
            print(f"{n}/{len(todo)} {d} rows={len(state['daily'][d])} "
                  f"{rate:.1f}/s eta={eta:.1f}min", flush=True)
        time.sleep(RATE_SLEEP)
    tmp = CACHE.with_suffix(".tmp")
    with tmp.open("wb") as fh:
        pickle.dump(state, fh)
    os.replace(tmp, CACHE)
    print("DONE", flush=True)


if __name__ == "__main__":
    sys.exit(main())
