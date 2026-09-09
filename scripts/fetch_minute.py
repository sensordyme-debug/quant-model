#!/usr/bin/env python3
"""D-2: pull 1-minute TRADES bars from IBKR and write them in LEAN's minute format.

Yahoo caps 1-minute history at ~30 days, which is useless for backtesting, so the
intraday sleeve (S-2) gets its data from the same IB Gateway the paper runner uses.

    py -3.11 scripts/fetch_minute.py --start 2020-01-01
    py -3.11 scripts/fetch_minute.py --symbols SPY --start 2026-01-01 --dry-run
    py -3.11 scripts/fetch_minute.py --validate-only

Output is one zip per symbol per session:

    equity/usa/minute/<sym>/<yyyyMMdd>_trade.zip
      -> <yyyyMMdd>_<sym>_minute_trade.csv
         rows: <ms since midnight ET>,<o>,<h>,<l>,<c>,<v>   prices x 10000

Prices are raw (split-adjusted, dividends carried by the factor files D-1 already
wrote), matching how LEAN reads equity data at every resolution.

Three things this script takes seriously:

  * **Pacing.** IBKR allows 60 historical requests per rolling 10 minutes and will
    silently stall a connection that ignores that. A sliding-window pacer enforces it,
    so a long backfill runs unattended without being throttled or disconnected.
  * **Resumability.** Work is chunked by calendar month and a month whose sessions are
    already on disk is skipped, so an interrupted backfill is restarted by re-running
    the same command. `clientId` 31 keeps it clear of the paper runner's 17.
  * **Cross-resolution agreement.** The minute bars come from IBKR, the daily bars from
    Yahoo (D-1). If they disagree, an intraday strategy validated here would not match
    a daily one, so every session's minute close is checked against the daily close and
    the worst disagreement is reported and stored in the manifest.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEAN_ROOT = Path(__import__("os").environ.get("LEAN_ROOT", REPO.parent / "Lean"))
DATA_DIR = Path(__import__("os").environ.get("LEAN_DATA", LEAN_ROOT / "Data"))
USA = DATA_DIR / "equity" / "usa"
MINUTE = USA / "minute"
MANIFEST = REPO / "research" / "minute_manifest.json"

SCALE = 10000
RTH_OPEN_MS = 9 * 3600_000 + 30 * 60_000      # 09:30 ET
RTH_CLOSE_MS = 16 * 3600_000                  # 16:00 ET

# The intraday sleeve S-2 names these first: two index proxies, a small-cap proxy and
# the levered pair that supplies the volatility the mandate asks for.
DEFAULT_SYMBOLS = ["SPY", "QQQ", "IWM", "TQQQ", "SQQQ"]

# IBKR routing hint; SMART alone is ambiguous for a few of these.
PRIMARY = {"SPY": "ARCA", "IWM": "ARCA", "QQQ": "NASDAQ", "TQQQ": "NASDAQ", "SQQQ": "NASDAQ"}

# IBKR: 60 historical-data requests per rolling 10 minutes.
PACE_LIMIT = 55
PACE_WINDOW = 600.0


class Pacer:
    """Sliding-window request limiter; also honours the 2s same-contract rule."""

    def __init__(self, limit: int = PACE_LIMIT, window: float = PACE_WINDOW):
        self.limit, self.window, self.stamps = limit, window, []
        self.last_by_key: dict[str, float] = {}

    def wait(self, key: str = "") -> float:
        now = time.time()
        self.stamps = [t for t in self.stamps if now - t < self.window]
        delay = 0.0
        if len(self.stamps) >= self.limit:
            delay = self.window - (now - self.stamps[0]) + 0.5
        same = self.last_by_key.get(key)
        if same is not None:
            delay = max(delay, 2.1 - (now - same))
        if delay > 0:
            time.sleep(delay)
        stamp = time.time()
        self.stamps.append(stamp)
        self.last_by_key[key] = stamp
        return max(delay, 0.0)


def daily_sessions(lean_sym: str) -> dict[str, float]:
    """Trading calendar and closing prices from the D-1 daily file: {yyyymmdd: close}."""
    path = USA / "daily" / f"{lean_sym}.zip"
    if not path.exists():
        return {}
    out = {}
    with zipfile.ZipFile(path) as z:
        for row in z.read(z.namelist()[0]).decode().strip().splitlines():
            parts = row.split(",")
            out[parts[0].split()[0]] = int(parts[4]) / SCALE
    return out


def months(start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    """Inclusive first/last calendar day of each month touching [start, end]."""
    out, cursor = [], dt.date(start.year, start.month, 1)
    while cursor <= end:
        nxt = dt.date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        out.append((max(cursor, start), min(nxt - dt.timedelta(days=1), end)))
        cursor = nxt
    return out


def zip_path(lean_sym: str, day: str) -> Path:
    return MINUTE / lean_sym / f"{day}_trade.zip"


def minute_csv(bars) -> tuple[str, int, float]:
    """Render one session's bars as LEAN minute rows.

    Returns the csv, the number of bars whose high/low did not bracket open/close
    (widened rather than dropped, as in fetch_data.py), and the last close.
    """
    lines, clamped, last_close = [], 0, 0.0
    for bar in bars:
        stamp = bar.date
        ms = stamp.hour * 3600_000 + stamp.minute * 60_000 + stamp.second * 1000
        o, h, l, c = (int(round(float(v) * SCALE)) for v in (bar.open, bar.high, bar.low, bar.close))
        hi, lo = max(o, h, l, c), min(o, h, l, c)
        if (hi, lo) != (h, l):
            clamped += 1
            h, l = hi, lo
        lines.append(f"{ms},{o},{h},{l},{c},{int(bar.volume) if bar.volume > 0 else 0}")
        last_close = float(bar.close)
    return "\n".join(lines) + "\n", clamped, last_close


def write_session(lean_sym: str, day: str, bars) -> tuple[int, int, float]:
    csv, clamped, last_close = minute_csv(bars)
    path = zip_path(lean_sym, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{day}_{lean_sym}_minute_trade.csv", csv)
    return len(bars), clamped, last_close


def validate_session(lean_sym: str, day: str) -> tuple[str | None, int, float]:
    """Re-read a written session and check LEAN's structural invariants.

    Returns (problem or None, bar count, last close).
    """
    path = zip_path(lean_sym, day)
    if not path.exists():
        return "missing", 0, 0.0
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        want = f"{day}_{lean_sym}_minute_trade.csv"
        if names != [want]:
            return f"zip entry is {names}, expected ['{want}']", 0, 0.0
        rows = z.read(names[0]).decode().strip().splitlines()
    if not rows:
        return "empty session", 0, 0.0
    stamps, last_close = [], 0.0
    for row in rows:
        parts = row.split(",")
        if len(parts) != 6:
            return f"malformed row: {row}", len(rows), 0.0
        ms, o, h, l, c, v = (int(x) for x in parts)
        if not (l <= o <= h and l <= c <= h and l > 0):
            return f"inconsistent OHLC at {ms}: {o},{h},{l},{c}", len(rows), 0.0
        if v < 0:
            return f"negative volume at {ms}", len(rows), 0.0
        # useRTH=True, so anything outside the regular session means the request leaked
        # extended hours and would give an intraday strategy bars it cannot trade on.
        if not (RTH_OPEN_MS <= ms < RTH_CLOSE_MS):
            return f"bar at {ms} ms is outside regular trading hours", len(rows), 0.0
        stamps.append(ms)
        last_close = c / SCALE
    if stamps != sorted(stamps) or len(set(stamps)) != len(stamps):
        return "timestamps are not strictly increasing", len(rows), last_close
    return None, len(rows), last_close


def sessions_on_disk(lean_sym: str) -> set[str]:
    folder = MINUTE / lean_sym
    if not folder.exists():
        return set()
    return {p.name.split("_")[0] for p in folder.glob("*_trade.zip")}


def fetch_month(ib, contract, last_day: dt.date, pacer: Pacer, retries: int = 2):
    """One request of 1-minute TRADES bars covering the month ending on `last_day`.

    The duration is 5 weeks, not "1 M", deliberately. IBKR measures a duration back
    from `endDateTime`, so "1 M" ending 23:59 on the last day of the month starts at
    23:59 on the *first* day of the month - after that session's close - and silently
    drops it. That is one lost session per month, ~5% of the sample, invisible in the
    bar count. 35 days covers the longest month with four days of slack; the caller
    filters the overlap back to the chunk, so a session is still written exactly once.
    """
    end = dt.datetime.combine(last_day, dt.time(23, 59, 0))
    for attempt in range(retries + 1):
        waited = pacer.wait(contract.symbol)
        try:
            bars = ib.reqHistoricalData(
                contract, endDateTime=end, durationStr="5 W", barSizeSetting="1 min",
                whatToShow="TRADES", useRTH=True, formatDate=1, timeout=180)
            return list(bars or []), waited, None
        except Exception as exc:  # pacing violations and no-data errors both land here
            if attempt == retries:
                return [], waited, str(exc)
            time.sleep(10.0 * (attempt + 1))
    return [], 0.0, "unreachable"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", help="comma-separated tickers; default SPY,QQQ,IWM,TQQQ,SQQQ")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None, help="inclusive; defaults to yesterday, so the "
                                                "in-progress session is never written")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=31,
                    help="kept clear of paper_trade.py's 17")
    ap.add_argument("--refetch", action="store_true",
                    help="re-request months whose sessions are already on disk")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    ap.add_argument("--validate-only", action="store_true",
                    help="no connection; re-check and report what is already on disk")
    args = ap.parse_args()

    if not USA.exists():
        sys.exit(f"LEAN equity data folder not found: {USA}")

    symbols = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
               if args.symbols else list(DEFAULT_SYMBOLS))
    start = dt.date.fromisoformat(args.start)
    end = (dt.date.fromisoformat(args.end) if args.end
           else dt.date.today() - dt.timedelta(days=1))

    calendars = {s: daily_sessions(s.lower()) for s in symbols}
    for sym, cal in calendars.items():
        if not cal:
            print(f"[minute] WARNING no daily file for {sym.lower()}; "
                  f"cannot check the calendar or cross-check closes")

    report: dict[str, dict] = {}

    if args.validate_only:
        for sym in symbols:
            report[sym.lower()] = summarize(sym.lower(), calendars[sym], start, end)
        return finish(report, args, start, end, connected=False)

    from ib_async import IB, Stock
    ib = IB()
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=25)
    except Exception as exc:
        print(f"[minute] cannot connect to IB Gateway at {args.host}:{args.port}: {exc}")
        return 2
    print(f"[minute] connected {ib.managedAccounts()}  {len(symbols)} symbols  "
          f"{start} .. {end}  target {MINUTE}", flush=True)

    errors: list[str] = []
    pacer = Pacer()
    t_start = time.time()
    try:
        for sym in symbols:
            lean_sym = sym.lower()
            contract = Stock(sym, "SMART", "USD", primaryExchange=PRIMARY.get(sym, ""))
            ib.qualifyContracts(contract)
            have = sessions_on_disk(lean_sym)
            cal = calendars[sym]
            written = clamped_total = 0
            for first_day, last_day in months(start, end):
                expected = {d for d in cal if first_day.strftime("%Y%m%d") <= d
                            <= last_day.strftime("%Y%m%d")} if cal else set()
                if not args.refetch and expected and expected <= have:
                    continue
                bars, waited, err = fetch_month(ib, contract, last_day, pacer)
                if err:
                    errors.append(f"{sym} {first_day:%Y-%m}: {err}")
                    print(f"  {sym:<5} {first_day:%Y-%m}  REQUEST FAILED: {err}", flush=True)
                    continue
                by_day: dict[str, list] = {}
                for bar in bars:
                    day = bar.date.strftime("%Y%m%d")
                    # A "1 M" request reaches back past the chunk; only keep this chunk's
                    # sessions so a day is written exactly once, by one request.
                    if first_day.strftime("%Y%m%d") <= day <= last_day.strftime("%Y%m%d"):
                        by_day.setdefault(day, []).append(bar)
                if args.dry_run:
                    print(f"  {sym:<5} {first_day:%Y-%m}  {len(bars):>5} bars  "
                          f"{len(by_day)} sessions in range (dry run)", flush=True)
                    continue
                for day, day_bars in sorted(by_day.items()):
                    n, clamped, _ = write_session(lean_sym, day, day_bars)
                    written += n
                    clamped_total += clamped
                    have.add(day)
                print(f"  {sym:<5} {first_day:%Y-%m}  {len(by_day):>2} sessions  "
                      f"{sum(len(b) for b in by_day.values()):>5} bars"
                      f"{f'  paced {waited:.0f}s' if waited > 1 else ''}", flush=True)
            if not args.dry_run:
                info = summarize(lean_sym, cal, start, end)
                info["clamped_bars"] = clamped_total
                report[lean_sym] = info
                print(f"[minute] {sym}: {info['sessions']} sessions, {info['bars']} bars, "
                      f"{info['first'] or '-'} .. {info['last'] or '-'}, "
                      f"missing {len(info['missing_sessions'])}, "
                      f"close-vs-daily max dev {info['close_dev']:.5f}", flush=True)
    finally:
        ib.disconnect()

    print(f"[minute] elapsed {(time.time() - t_start) / 60:.1f} min", flush=True)
    for err in errors:
        print(f"[minute] REQUEST ERROR {err}")
    if args.dry_run:
        return 0
    return finish(report, args, start, end, connected=True, errors=errors)


def summarize(lean_sym: str, cal: dict[str, float], start: dt.date, end: dt.date) -> dict:
    """Validate every session on disk in range and cross-check closes against daily."""
    lo, hi = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    days = sorted(d for d in sessions_on_disk(lean_sym) if lo <= d <= hi)
    problems, bars, close_dev, worst_day = [], 0, 0.0, ""
    short_sessions = []
    for day in days:
        problem, n, last_close = validate_session(lean_sym, day)
        if problem:
            problems.append(f"{day}: {problem}")
            continue
        bars += n
        # A regular session is 390 minutes; half days are ~210. Anything under 100 bars
        # is a truncated request, not a holiday, and would look like a real session.
        if n < 100:
            short_sessions.append(f"{day}({n})")
        ref = cal.get(day)
        if ref and last_close:
            dev = abs(last_close / ref - 1.0)
            if dev > close_dev:
                close_dev, worst_day = dev, day
    expected = sorted(d for d in cal if lo <= d <= hi) if cal else []
    missing = [d for d in expected if d not in set(days)]
    return {
        "sessions": len(days), "bars": bars,
        "first": days[0] if days else None, "last": days[-1] if days else None,
        "expected_sessions": len(expected), "missing_sessions": missing,
        "short_sessions": short_sessions,
        "close_dev": round(close_dev, 6), "close_dev_day": worst_day,
        "problems": problems,
    }


def finish(report: dict, args, start: dt.date, end: dt.date, connected: bool,
           errors: list[str] | None = None) -> int:
    failed = False
    for sym, info in sorted(report.items()):
        if info["problems"]:
            failed = True
            for p in info["problems"][:5]:
                print(f"[minute] VALIDATION FAILED {sym} {p}")
            if len(info["problems"]) > 5:
                print(f"[minute] ... and {len(info['problems']) - 5} more for {sym}")
        if info["close_dev"] > 0.01:
            print(f"[minute] {sym}: minute close disagrees with the daily close by "
                  f"{info['close_dev']:.4f} on {info['close_dev_day']}  <-- CHECK")
        if info["short_sessions"]:
            print(f"[minute] {sym}: {len(info['short_sessions'])} truncated sessions: "
                  f"{', '.join(info['short_sessions'][:8])}")
    MANIFEST.write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "IBKR reqHistoricalData 1 min TRADES useRTH=True (raw prices; "
                  "dividends carried by the D-1 factor files)",
        "start": start.isoformat(), "end": end.isoformat(),
        "connected": connected,
        "request_errors": errors or [],
        "data": report,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"[minute] manifest -> {MANIFEST.relative_to(REPO)}")
    total_bars = sum(i["bars"] for i in report.values())
    total_missing = sum(len(i["missing_sessions"]) for i in report.values())
    print(f"[minute] {len(report)} symbols, {total_bars} bars, "
          f"{total_missing} sessions missing, {'FAILED' if failed else 'validation OK'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
