#!/usr/bin/env python
"""Fetch consolidated (SIP) 1-minute bars from Alpaca into data/minute_alpaca/<SYM>.parquet.

    python scripts/alpaca_data.py --start 2024-01-01                      # UNIVERSE
    python scripts/alpaca_data.py --symbols SPY QQQ --start 2016-01-01
    python scripts/alpaca_data.py --status

Alpaca's free plan serves full SIP history (all exchanges, back to 2016) for any US symbol,
with only the most recent 15 minutes withheld, at up to 200 requests/minute and 10,000 bars
per page. That makes it the breadth-and-depth research store; the IBKR store stays the
execution-matched one. Bars are regular-hours only and stamped at bar start (ET).
Run research on it with INTRADAY_DATA_DIR=data/minute_alpaca.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("INTRADAY_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data" / "minute_alpaca"))
from intraday_common import DATA_DIR, ET, UNIVERSE, load_bars, save_bars  # noqa: E402
from apikeys import require  # noqa: E402

BASE = "https://data.alpaca.markets/v2/stocks/bars"


def fetch_symbol(symbol: str, start: dt.date, end: dt.date, headers: dict, feed: str = "sip") -> int:
    have = load_bars(symbol, rth_only=False)
    if not have.empty:
        last = have.index.max().date()
        if last >= end:
            print(f"  {symbol}: up to date ({last})", flush=True)
            return 0
        if last > start:
            start = last                       # resume from the last stored day (inclusive; dedup on save)
    params = {"symbols": symbol, "timeframe": "1Min", "start": f"{start}T13:30:00Z", "end": f"{end}T20:00:00Z",
              "feed": feed, "limit": 10000, "adjustment": "raw"}
    total, token = 0, None
    frames = []
    while True:
        q = dict(params)
        if token:
            q["page_token"] = token
        req = urllib.request.Request(BASE + "?" + urllib.parse.urlencode(q), headers=headers)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(15)
                    continue
                print(f"  {symbol}: HTTP {e.code} {e.read()[:120]!r}", flush=True)
                return total
            except Exception as exc:  # noqa: BLE001
                print(f"  {symbol}: {exc}; retry", flush=True)
                time.sleep(5)
        else:
            return total
        rows = data.get("bars", {}).get(symbol, [])
        if rows:
            df = pd.DataFrame(rows)[["t", "o", "h", "l", "c", "v"]]
            df["t"] = pd.to_datetime(df["t"], utc=True)
            df = df.set_index("t")
            df.index.name = "date"
            frames.append(df)
            total += len(df)
        token = data.get("next_page_token")
        if not token:
            break
        time.sleep(0.35)                        # ~170 requests/min, under the 200/min cap
    if frames:
        df = pd.concat(frames)
        et = df.index.tz_convert(ET)
        t = et.time
        df = df[(t >= dt.time(9, 30)) & (t < dt.time(16, 0))]
        n = save_bars(symbol, df)
        print(f"  {symbol}: +{len(df)} RTH bars from {start} (store now {n})", flush=True)
    else:
        print(f"  {symbol}: no bars returned", flush=True)
    return total


def status(symbols):
    print(f"store: {DATA_DIR}")
    for s in symbols:
        df = load_bars(s)
        if df.empty:
            print(f"  {s:<6} (none)")
        else:
            days = sorted(set(df.index.date))
            print(f"  {s:<6} {len(df):>8} bars  {len(days):>5} sessions  {days[0]} .. {days[-1]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default=str(dt.date.today()))
    ap.add_argument("--feed", default="sip", choices=["sip", "iex"])
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    symbols = args.symbols or UNIVERSE
    if args.status:
        status(symbols)
        return 0
    k = require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    headers = {"APCA-API-KEY-ID": k["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": k["ALPACA_SECRET_KEY"]}
    start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    t0 = time.time()
    for s in symbols:
        try:
            fetch_symbol(s, start, end, headers, args.feed)
        except Exception as exc:  # noqa: BLE001
            print(f"  {s} FAILED: {exc}", flush=True)
    print(f"done in {(time.time() - t0) / 60:.1f} min")
    status(symbols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
