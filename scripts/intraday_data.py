#!/usr/bin/env python
"""Fetch 1-minute TRADES bars from IBKR into data/minute/<SYM>.parquet for the intraday sleeve.

    python scripts/intraday_data.py                    # UNIVERSE, last 3 months
    python scripts/intraday_data.py --months 6
    python scripts/intraday_data.py --symbols NVDA TSLA --months 1
    python scripts/intraday_data.py --status           # what is on disk

One request per symbol-month (IBKR serves "1 M" of 1-min bars in one call, ~8k bars),
paced under IBKR's 60-requests-per-10-minutes rule and resumable: months already on disk
are skipped. Uses clientId 61 so it never collides with the paper runner (17), the LEAN
minute fetcher (31) or the live intraday trader (71).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from collections import deque

import pandas as pd

from intraday_common import DATA_DIR, ET, UNIVERSE, load_bars, save_bars

MAX_REQ_PER_10MIN = 45


class Pacer:
    def __init__(self, limit=MAX_REQ_PER_10MIN, window=600):
        self.limit, self.window, self.stamps = limit, window, deque()

    def wait(self):
        now = time.time()
        while self.stamps and now - self.stamps[0] > self.window:
            self.stamps.popleft()
        if len(self.stamps) >= self.limit:
            sleep_for = self.window - (now - self.stamps[0]) + 1
            print(f"  pacing: sleeping {sleep_for:.0f}s", flush=True)
            time.sleep(sleep_for)
        self.stamps.append(time.time())


def month_ends(months: int) -> list[dt.datetime]:
    """End timestamps (ET) for each 1-month request, newest first."""
    now = dt.datetime.now(ET)
    ends = []
    for i in range(months):
        ends.append(now - dt.timedelta(days=30 * i))
    return ends


def fetch_symbol(ib, symbol: str, months: int, pacer: Pacer, force: bool) -> int:
    from ib_async import Stock, util
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    have = load_bars(symbol, rth_only=False)
    have_days = set(have.index.date) if not have.empty else set()
    total = 0
    for end in month_ends(months):
        window_start = (end - dt.timedelta(days=30)).date()
        # skip a month whose sessions are already on disk (at least 15 sessions present)
        if not force and sum(1 for d in have_days if window_start <= d <= end.date()) >= 15:
            continue
        pacer.wait()
        end_str = end.astimezone(dt.timezone.utc).strftime("%Y%m%d-%H:%M:%S")
        for attempt in range(3):
            try:
                bars = ib.reqHistoricalData(contract, endDateTime=end_str, durationStr="1 M",
                                            barSizeSetting="1 min", whatToShow="TRADES", useRTH=True,
                                            formatDate=2, timeout=120)
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  {symbol} {end.date()}: attempt {attempt + 1} failed: {exc}", flush=True)
                time.sleep(30 * (attempt + 1))
                bars = []
        if not bars:
            print(f"  {symbol} month ending {end.date()}: no bars", flush=True)
            continue
        df = util.df(bars)[["date", "open", "high", "low", "close", "volume"]]
        df = df.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"})
        df["date"] = pd.to_datetime(df["date"], utc=True)
        df = df.set_index("date")
        n = save_bars(symbol, df)
        total += len(df)
        print(f"  {symbol} month ending {end.date()}: {len(df)} bars (store now {n})", flush=True)
    return total


def status():
    print(f"store: {DATA_DIR}")
    for s in UNIVERSE:
        df = load_bars(s)
        if df.empty:
            print(f"  {s:<6} (none)")
        else:
            days = sorted(set(df.index.date))
            print(f"  {s:<6} {len(df):>7} bars  {len(days):>4} sessions  {days[0]} .. {days[-1]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--force", action="store_true", help="re-fetch months already on disk")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=61)
    args = ap.parse_args()
    if args.status:
        status()
        return 0
    from ib_async import IB
    ib = IB()
    ib.connect("127.0.0.1", args.port, clientId=args.client_id, timeout=30)
    ib.reqMarketDataType(3)
    pacer = Pacer()
    symbols = args.symbols or UNIVERSE
    t0 = time.time()
    for s in symbols:
        print(f"{s}:", flush=True)
        try:
            fetch_symbol(ib, s, args.months, pacer, args.force)
        except Exception as exc:  # noqa: BLE001
            print(f"  {s} FAILED: {exc}", flush=True)
    ib.disconnect()
    print(f"done in {(time.time() - t0) / 60:.1f} min")
    status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
