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

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("INTRADAY_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data" / "minute_alpaca"))
from intraday_common import (DATA_DIR, ET, SPLITS_FILE, UNIVERSE, calendar_trim,  # noqa: E402
                             load_bars, save_bars)
from apikeys import require  # noqa: E402

BASE = "https://data.alpaca.markets/v2/stocks/bars"


def fetch_symbol(symbol: str, start: dt.date, end: dt.date, headers: dict, feed: str = "sip",
                 adjustment: str = "split") -> int:
    """Fill whatever part of [start, end] the store lacks: the head (before the first stored
    day), the tail (after the last stored day), or everything. Interior gaps are not detected."""
    have = load_bars(symbol, rth_only=False)
    if not have.empty:
        first, last = have.index.min().date(), have.index.max().date()
        total = 0
        if start < first:
            total += _fetch_range(symbol, start, first, headers, feed, adjustment)
        if last < end:
            total += _fetch_range(symbol, last, end, headers, feed, adjustment)
        if total == 0:
            print(f"  {symbol}: up to date ({first} .. {last})", flush=True)
        return total
    return _fetch_range(symbol, start, end, headers, feed, adjustment)


def _fetch_range(symbol: str, start: dt.date, end: dt.date, headers: dict, feed: str, adjustment: str) -> int:
    # The free plan refuses SIP requests that touch the most recent 15 minutes, so the window
    # end is clamped to 16 minutes before now (UTC).
    end_ts = min(dt.datetime.combine(end, dt.time(20, 0), tzinfo=dt.timezone.utc),
                 dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16))
    # adjustment="split" keeps intraday features continuous across split days (NVDA 2024,
    # AMZN/GOOGL 2022, AVGO 2024, SMCI 2024, SOXL/SOXS reverse splits); dividends are left raw.
    params = {"symbols": symbol, "timeframe": "1Min", "start": f"{start}T13:30:00Z",
              "end": end_ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "feed": feed, "limit": 10000, "adjustment": adjustment}
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
        # AUD-07: the 09:30-16:00 literal above is the regular session, so on a 13:00 early close
        # it kept 13:00-15:59 POST-MARKET prints and stored them as RTH. `calendar_trim` cuts each
        # session at its own calendar close; it is a pure subset, so a store fetched before this
        # existed is repaired by any re-fetch that overlaps the day.
        if len(df):
            trimmed = calendar_trim(df.set_index(et[(t >= dt.time(9, 30)) & (t < dt.time(16, 0))]))
            trimmed.index = trimmed.index.tz_convert("UTC")
            trimmed.index.name = df.index.name
            df = trimmed
        n = save_bars(symbol, df)
        print(f"  {symbol}: +{len(df)} RTH bars from {start} (store now {n})", flush=True)
    else:
        print(f"  {symbol}: no bars returned", flush=True)
    return total


def _daily_closes(symbol: str, start: dt.date, headers: dict, feed: str, adjustment: str) -> pd.Series:
    """Daily closes for one symbol, one page-loop, used only to derive split factors."""
    params = {"symbols": symbol, "timeframe": "1Day", "start": f"{start}T00:00:00Z",
              "end": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "feed": feed, "limit": 10000, "adjustment": adjustment}
    rows, token = [], None
    while True:
        q = dict(params)
        if token:
            q["page_token"] = token
        req = urllib.request.Request(BASE + "?" + urllib.parse.urlencode(q), headers=headers)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows += data.get("bars", {}).get(symbol, [])
        token = data.get("next_page_token")
        if not token:
            break
        time.sleep(0.35)
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    df["t"] = pd.to_datetime(df["t"], utc=True).dt.tz_convert(ET).dt.date
    return df.set_index("t")["c"].astype(float)


def _sig(x: float, digits: int = 6) -> float:
    """Round to significant digits, not decimals: SOXS's cumulative factor in 2016 is ~4e-7 and
    rounding that to 6 decimals would store a zero."""
    if not x or not np.isfinite(x):
        return float(x)
    return float(round(x, digits - 1 - int(np.floor(np.log10(abs(x))))))


def write_splits(symbols, start: dt.date, headers: dict, feed: str) -> dict:
    """Write DATA_DIR/_splits.json: the cumulative split factor raw_close/adjusted_close per date.

    The store holds split-ADJUSTED bars, which is right for features and wrong for a per-share
    commission: a 2016 NVDA share is priced at ~1/40th of what it traded at, so a dollar position
    buys ~40x the shares that were really bought. Asking Alpaca for the same daily bars twice -
    once raw, once split-adjusted - gives that factor exactly, with no split table to maintain.
    Dividends are left raw in both series, so the ratio is pure split.
    """
    # Merge, never replace. This file is the cost model's split table for the WHOLE store, but
    # `symbols` defaults to the 16-name UNIVERSE and `--start` to 2024-01-01, so a bare
    # `--splits` used to silently rewrite a 60-symbol table as 16 symbols measured over two
    # years - every dropped name then costs at scale 1.0 and a per-share commission reads up to
    # 40x wrong with nothing to show for it. Only the symbols actually re-derived here move.
    p = DATA_DIR / SPLITS_FILE
    try:
        out = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:  # noqa: BLE001 - a corrupt table must not be silently half-kept
        out = {}
    kept = len(out)
    for s in symbols:
        raw = _daily_closes(s, start, headers, feed, "raw")
        adj = _daily_closes(s, start, headers, feed, "split")
        common = raw.index.intersection(adj.index)
        if len(common) < 100:
            print(f"  {s}: too few daily bars ({len(common)}) to derive splits; assuming 1.0", flush=True)
            continue
        ratio = (raw.reindex(common) / adj.reindex(common)).sort_index()
        # Both closes are rounded to the cent, so the ratio wobbles by a few parts in 1e5 every
        # day. Only a split moves it by percent, so runs are cut at a 1% relative break and each
        # run is represented by its median - that turns 2,700 noisy points into one segment per
        # split event.
        segs, run = [], []
        for d, f in ratio.items():
            if not (f > 0):
                continue
            if run and abs(f / float(np.median([x[1] for x in run])) - 1.0) > 0.01:
                segs.append([str(run[0][0]), _sig(float(np.median([x[1] for x in run])))])
                run = []
            run.append((d, f))
        if run:
            segs.append([str(run[0][0]), _sig(float(np.median([x[1] for x in run])))])
        out[s] = segs
        changes = [f"{d}:{f:g}" for d, f in segs[1:]]
        print(f"  {s:<6} factor {segs[0][1]:g} at {segs[0][0]} -> {segs[-1][1]:g} today; "
              f"{len(segs) - 1} split(s){': ' + ', '.join(changes) if changes else ''}", flush=True)
    p.write_text(json.dumps(dict(sorted(out.items())), indent=1), encoding="utf-8")
    print(f"wrote {p} ({len(out)} symbols; {kept} were already there, "
          f"{len(symbols)} re-derived from {start})")
    return out


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
    ap.add_argument("--adjustment", default="split", choices=["split", "raw", "all"])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--splits", action="store_true",
                    help="derive and write _splits.json (needed before costing an adjusted store)")
    args = ap.parse_args()
    symbols = args.symbols or UNIVERSE
    if args.status:
        status(symbols)
        return 0
    k = require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    headers = {"APCA-API-KEY-ID": k["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": k["ALPACA_SECRET_KEY"]}
    start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    if args.splits:
        write_splits(symbols, start, headers, args.feed)
        return 0
    t0 = time.time()
    for s in symbols:
        try:
            fetch_symbol(s, start, end, headers, args.feed, args.adjustment)
        except Exception as exc:  # noqa: BLE001
            print(f"  {s} FAILED: {exc}", flush=True)
    print(f"done in {(time.time() - t0) / 60:.1f} min")
    status(symbols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
