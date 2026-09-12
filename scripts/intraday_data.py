#!/usr/bin/env python
"""Fetch 1-minute TRADES bars from IBKR into data/minute/<SYM>.parquet for the intraday sleeve.

    python scripts/intraday_data.py                    # UNIVERSE, last 3 months
    python scripts/intraday_data.py --months 6
    python scripts/intraday_data.py --symbols NVDA TSLA --months 1
    python scripts/intraday_data.py --status           # what is on disk

One request per symbol-month (IBKR serves "1 M" of 1-min bars in one call, ~8k bars),
paced under IBKR's 60-requests-per-10-minutes rule and resumable: a window is skipped only
when the calendar's sessions inside it are all on disk and complete. Uses clientId 61 so it
never collides with the paper runner (17), the LEAN minute fetcher (31) or the live intraday
trader (71).

AUD-16 / D-4 (2026-09-12): this module could neither extend the store nor stay out of the
session it ran in, and the two defects hid each other.

  * `snap_after_close` returned `min(20:00, now)`, so a run during regular hours ended its
    request at the wall clock - which is the exact truncation the function exists to prevent,
    because IBKR truncates the session `endDateTime` lands in. All 16 symbols held a 173-bar
    2026-09-11 written at 12:35 ET. `scripts/intraday_launch.py` preflights by replaying the
    LAST STORED SESSION, so this defect points straight at the live gate.
  * `fetch_symbol` skipped any window holding 15 or more sessions on disk. A count cannot tell
    a complete month from one missing its last five days, and with 263 sessions stored every
    `--months N` window cleared 15, so the whole run was a no-op and `--months` did nothing.

Both are now decided by the same question - which CALENDAR sessions in this window is the store
missing or holding truncated - and truncation is classified by `store_health.session_shapes`
(E-6's head/tail rule) rather than re-drawn here from a bar count.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from collections import deque
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import store_health as sh  # noqa: E402

from intraday_common import DATA_DIR, ET, UNIVERSE, load_bars, parquet_path, save_bars  # noqa: E402
from quant_brain.markets.equity_us import CALENDAR  # noqa: E402

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


#: Minutes after the session close before the tape is treated as settled. The margin is added
#: to the CALENDAR's close, not to a hard-coded 16:00, so it is 16:15 on a regular day and 13:15
#: on an early close - AUD-07's rule applied to the fetcher.
SETTLE_MINUTES = 15


def last_safe_end(now: dt.datetime | None = None) -> dt.datetime:
    """The most recent instant a request may end on without truncating a session.

    IBKR truncates the session `endDateTime` lands in. Once today's close plus the settle
    margin has passed, "now" is outside every session and is therefore safe; before it, the
    only safe boundary is the previous day's 20:00, which sits between two sessions by
    construction. On a day the market never opened there is nothing to truncate.
    """
    now = now or dt.datetime.now(ET)
    try:
        sess = CALENDAR.session(now.date())
    except Exception:  # noqa: BLE001 - past the calendar's verified range; stay conservative
        sess = object()
    if sess is None:
        return now
    prior = (now - dt.timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    close_t = getattr(sess, "close_t", None)
    if close_t is None:
        return prior
    settled = (dt.datetime.combine(now.date(), close_t, tzinfo=ET)
               + dt.timedelta(minutes=SETTLE_MINUTES))
    return now if now >= settled else prior


def last_closed_session(now: dt.datetime | None = None) -> dt.date:
    """The newest trading day whose session has finished - the store's true end condition."""
    d = last_safe_end(now).date()
    for _ in range(10):
        if CALENDAR.is_trading_day(d):
            return d
        d -= dt.timedelta(days=1)
    return d


def snap_after_close(when: dt.datetime, *, now: dt.datetime | None = None,
                     legacy: bool = False) -> dt.datetime:
    """Move a request's end timestamp to 20:00 ET on its own day, never inside a session.

    IBKR truncates the session that `endDateTime` lands in, so a window ending at the wall
    clock time of the run (e.g. 11:48) silently stored a 139-bar day and every strategy
    then computed a session P&L on two hours of tape. Snapping every end past the close
    means a window boundary can only ever land between sessions (found 2026-09-09, A-4).

    AUD-16: the clamp used to be `min(snapped, now)`, which re-introduced the very bug the
    snap removes - during regular hours `now` IS inside the session. It is now clamped to
    `last_safe_end`, so a midday run steps back to the previous 20:00 and simply does not
    fetch today rather than fetching a third of it. `legacy=True` reproduces the old
    behaviour for the D-4 comparison and for nothing else.
    """
    snapped = when.astimezone(ET).replace(hour=20, minute=0, second=0, microsecond=0)
    now = now or dt.datetime.now(ET)
    return min(snapped, now if legacy else last_safe_end(now))


def month_ends(months: int, *, now: dt.datetime | None = None,
               legacy: bool = False) -> list[dt.datetime]:
    """End timestamps (ET) for each 1-month request, newest first. Windows step 25 days but
    each request covers a month, so consecutive windows overlap by ~5 days: IBKR can drop the
    first session of a window whose start falls after that session's close (found by
    scripts/fetch_minute.py on 2026-09-09), and the overlap plus de-duplication in save_bars
    recovers it. Every end is snapped past the close so no window truncates a session."""
    now = now or dt.datetime.now(ET)
    return [snap_after_close(now - dt.timedelta(days=25 * i), now=now, legacy=legacy)
            for i in range(months)]


def store_shapes(symbol: str) -> dict[dt.date, sh.SessionShape]:
    """Every stored session of `symbol` scored against the calendar, keyed by day.

    E-6's `session_shapes` is imported rather than re-implemented: a bar count cannot tell a
    thin name that skipped nine minutes from a fetch that died at lunch, and this module used
    to try (`n < 390 and n != 210`), which called every sparse session truncated and passed a
    390-minute day stored with exactly 210 bars."""
    p = parquet_path(symbol)
    if not p.exists():
        return {}
    return {s.day: s for s in sh.session_shapes(sh.rth_index(p), CALENDAR)}


def sessions_needed(symbol: str, start: dt.date, end: dt.date, *,
                    shapes: dict | None = None, now: dt.datetime | None = None) -> list[dt.date]:
    """Calendar sessions in [start, end] the store does not hold complete.

    Two populations, one rule: a session the calendar has and the store does not is MISSING
    (the case `--repair` could never see, because it iterated the days on disk), and a session
    the store has whose head or tail is absent is TRUNCATED. Sessions that have not closed yet
    are never counted - an incomplete live session is not a defect."""
    shapes = store_shapes(symbol) if shapes is None else shapes
    end = min(end, last_closed_session(now))
    if start > end:
        return []
    return [d for d in CALENDAR.trading_days(start, end)
            if d not in shapes or shapes[d].truncated]


def incomplete_sessions(symbol: str, *, now: dt.datetime | None = None) -> list[dt.date]:
    """`sessions_needed` over the whole stored span: what `--repair` has to fix."""
    shapes = store_shapes(symbol)
    if not shapes:
        return []
    return sessions_needed(symbol, min(shapes), last_closed_session(now), shapes=shapes, now=now)


def repair_symbol(ib, symbol: str, pacer: Pacer) -> int:
    """Re-request the months covering any missing or truncated session, ending after the close.

    `scripts/intraday_launch.py` preflights by replaying the LAST STORED SESSION, so a short
    final day is exactly what this is here to catch. On 2026-09-10 the post-close refresh left
    META at 115 bars and SMCI at 119; the bar-count check reported "no truncated sessions" and
    the replay of that day carried an SMCI position past the flatten and marked the sleeve at
    -66,559 instead of -7,713."""
    bad = incomplete_sessions(symbol)
    if not bad:
        print(f"  {symbol}: no missing or truncated sessions", flush=True)
        return 0
    # one request per distinct month-window covering the bad days, ending 3 days after
    ends, fixed = [], 0
    for d in bad:
        end = snap_after_close(dt.datetime.combine(d + dt.timedelta(days=3), dt.time(20), tzinfo=ET))
        if not any(abs((end - e).days) < 20 for e in ends):
            ends.append(end)
    print(f"  {symbol}: {len(bad)} incomplete {bad[:8]}{' ...' if len(bad) > 8 else ''} "
          f"-> {len(ends)} requests", flush=True)
    for end in ends:
        fixed += fetch_window(ib, symbol, end, pacer)
    still = incomplete_sessions(symbol)
    print(f"  {symbol}: incomplete after repair: {still}", flush=True)
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


def fetch_symbol(ib, symbol: str, months: int, pacer: Pacer, force: bool,
                 *, legacy_skip: bool = False) -> int:
    """Request every month window that is not already complete on disk.

    AUD-16: the skip used to be "15 or more sessions of this window are on disk", which is a
    count and therefore blind to which sessions those are. A store holding 263 sessions
    cleared it in every window, so the fetcher had no way to advance past its own last day and
    `--months N` was a no-op for every N. The skip is now the question that was actually being
    asked: is any calendar session in this window missing or truncated?"""
    contract = qualify(ib, symbol)
    shapes = store_shapes(symbol)
    total = 0
    for end in month_ends(months):
        window_start = (end - dt.timedelta(days=30)).date()
        if not force:
            if legacy_skip:
                if sum(1 for d in shapes if window_start <= d <= end.date()) >= 15:
                    continue
            else:
                need = sessions_needed(symbol, window_start, end.date(), shapes=shapes)
                if not need:
                    continue
                print(f"  {symbol} {window_start}..{end.date()}: {len(need)} session(s) "
                      f"missing or truncated ({need[0]} .. {need[-1]})", flush=True)
        total += fetch_window(ib, symbol, end, pacer, contract)
        shapes = store_shapes(symbol)   # later windows must see what this one just merged
    return total


def status():
    print(f"store: {DATA_DIR}")
    for s in UNIVERSE:
        df = load_bars(s)
        if df.empty:
            print(f"  {s:<6} (none)")
        else:
            days = sorted(set(df.index.date))
            bad = incomplete_sessions(s)
            flag = f"  INCOMPLETE {len(bad)} (last {bad[-1]})" if bad else ""
            print(f"  {s:<6} {len(df):>7} bars  {len(days):>4} sessions  {days[0]} .. {days[-1]}{flag}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--force", action="store_true", help="re-fetch months already on disk")
    ap.add_argument("--repair", action="store_true",
                    help="re-fetch the months holding a missing or truncated session, over the "
                         "WHOLE stored span rather than the last --months")
    ap.add_argument("--legacy-skip", action="store_true",
                    help="AUD-16 comparison only: restore the pre-2026-09-12 count-based skip")
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
                fetch_symbol(ib, s, args.months, pacer, args.force,
                             legacy_skip=args.legacy_skip)
                # the default run IS a repair for the window it covers (AUD-16); anything left
                # incomplete is older than --months and needs --repair, so say so rather than
                # leave it to `status`.
                left = [d for d in incomplete_sessions(s)
                        if d < (dt.datetime.now(ET) - dt.timedelta(days=25 * args.months)).date()]
                if left:
                    print(f"  {s}: {len(left)} incomplete session(s) older than --months "
                          f"{args.months} (oldest {left[0]}, newest {left[-1]}); run --repair",
                          flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  {s} FAILED: {exc}", flush=True)
    ib.disconnect()
    print(f"done in {(time.time() - t0) / 60:.1f} min")
    status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
