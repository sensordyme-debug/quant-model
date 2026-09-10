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


#: A full regular session is 390 one-minute bars; NYSE half days are 210.
FULL_SESSION_BARS = 390
HALF_SESSION_BARS = 210


def snap_after_close(when: dt.datetime) -> dt.datetime:
    """Move a request's end timestamp to 20:00 ET on its own day, never into the future.

    IBKR truncates the session that `endDateTime` lands in, so a window ending at the wall
    clock time of the run (e.g. 11:48) silently stored a 139-bar day and every strategy
    then computed a session P&L on two hours of tape. Snapping every end past the close
    means a window boundary can only ever land between sessions (found 2026-09-09, A-4)."""
    snapped = when.astimezone(ET).replace(hour=20, minute=0, second=0, microsecond=0)
    now = dt.datetime.now(ET)
    return min(snapped, now)


def month_ends(months: int) -> list[dt.datetime]:
    """End timestamps (ET) for each 1-month request, newest first. Windows step 25 days but
    each request covers a month, so consecutive windows overlap by ~5 days: IBKR can drop the
    first session of a window whose start falls after that session's close (found by
    scripts/fetch_minute.py on 2026-09-09), and the overlap plus de-duplication in save_bars
    recovers it. Every end is snapped past the close so no window truncates a session."""
    now = dt.datetime.now(ET)
    return [snap_after_close(now - dt.timedelta(days=25 * i)) for i in range(months)]


def truncated_sessions(symbol: str) -> list[dt.date]:
    """Sessions on disk that hold fewer bars than a full or half session.

    A half day (210 bars) is legitimate; anything else short is a window-boundary
    truncation. Today's session is excluded only while it is *still trading* - before
    2026-09-10 it was excluded unconditionally, which hid the one truncation that matters
    most: `scripts/intraday_launch.py` preflights by replaying the **last stored session**,
    so a short final day is exactly what the check is there to catch. On 2026-09-10 the
    post-close refresh left META at 115 bars and SMCI at 119; `--repair` reported "no
    truncated sessions" and the replay of that day carried an SMCI position past the flatten
    and marked the sleeve at -66,559 instead of -7,713."""
    df = load_bars(symbol)
    if df.empty:
        return []
    counts = df.groupby(df.index.date).size()
    now = dt.datetime.now(ET)
    # 16:00 ET plus a margin for IBKR to publish the closing minute
    still_trading = now.date() if now.time() < dt.time(16, 15) else None
    return [d for d, n in counts.items()
            if d != still_trading and n < FULL_SESSION_BARS and n != HALF_SESSION_BARS]


def repair_symbol(ib, symbol: str, pacer: Pacer) -> int:
    """Re-request the months covering any truncated session, ending after the close."""
    bad = truncated_sessions(symbol)
    if not bad:
        print(f"  {symbol}: no truncated sessions", flush=True)
        return 0
    # one request per distinct month-window covering the bad days, ending 3 days after
    ends, fixed = [], 0
    for d in bad:
        end = snap_after_close(dt.datetime.combine(d + dt.timedelta(days=3), dt.time(20), tzinfo=ET))
        if not any(abs((end - e).days) < 20 for e in ends):
            ends.append(end)
    print(f"  {symbol}: {len(bad)} truncated {bad} -> {len(ends)} requests", flush=True)
    for end in ends:
        fixed += fetch_window(ib, symbol, end, pacer)
    still = truncated_sessions(symbol)
    print(f"  {symbol}: truncated after repair: {still}", flush=True)
    return fixed


def qualify(ib, symbol: str):
    from ib_async import Stock
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    return contract


def fetch_window(ib, symbol: str, end: dt.datetime, pacer: Pacer, contract=None) -> int:
    """One "1 M" request of 1-minute TRADES bars ending at `end`, merged into the store."""
    from ib_async import util
    contract = contract or qualify(ib, symbol)
    pacer.wait()
    end_str = end.astimezone(dt.timezone.utc).strftime("%Y%m%d-%H:%M:%S")
    bars = []
    for attempt in range(3):
        try:
            bars = ib.reqHistoricalData(contract, endDateTime=end_str, durationStr="1 M",
                                        barSizeSetting="1 min", whatToShow="TRADES", useRTH=True,
                                        formatDate=2, timeout=120)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  {symbol} {end.date()}: attempt {attempt + 1} failed: {exc}", flush=True)
            time.sleep(30 * (attempt + 1))
    if not bars:
        print(f"  {symbol} month ending {end.date()}: no bars", flush=True)
        return 0
    df = util.df(bars)[["date", "open", "high", "low", "close", "volume"]]
    df = df.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"})
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date")
    n = save_bars(symbol, df)
    print(f"  {symbol} month ending {end.date()}: {len(df)} bars (store now {n})", flush=True)
    return len(df)


def fetch_symbol(ib, symbol: str, months: int, pacer: Pacer, force: bool) -> int:
    contract = qualify(ib, symbol)
    have = load_bars(symbol, rth_only=False)
    have_days = set(have.index.date) if not have.empty else set()
    total = 0
    for end in month_ends(months):
        window_start = (end - dt.timedelta(days=30)).date()
        # skip a month whose sessions are already on disk (at least 15 sessions present)
        if not force and sum(1 for d in have_days if window_start <= d <= end.date()) >= 15:
            continue
        total += fetch_window(ib, symbol, end, pacer, contract)
    return total


def status():
    print(f"store: {DATA_DIR}")
    for s in UNIVERSE:
        df = load_bars(s)
        if df.empty:
            print(f"  {s:<6} (none)")
        else:
            days = sorted(set(df.index.date))
            bad = truncated_sessions(s)
            flag = f"  TRUNCATED {len(bad)}" if bad else ""
            print(f"  {s:<6} {len(df):>7} bars  {len(days):>4} sessions  {days[0]} .. {days[-1]}{flag}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--force", action="store_true", help="re-fetch months already on disk")
    ap.add_argument("--repair", action="store_true",
                    help="re-fetch only the months holding a truncated session")
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
            if args.repair:
                repair_symbol(ib, s, pacer)
            else:
                fetch_symbol(ib, s, args.months, pacer, args.force)
        except Exception as exc:  # noqa: BLE001
            print(f"  {s} FAILED: {exc}", flush=True)
    ib.disconnect()
    print(f"done in {(time.time() - t0) / 60:.1f} min")
    status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
