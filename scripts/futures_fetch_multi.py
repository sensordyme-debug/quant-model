#!/usr/bin/env python3
"""OWNER-3 step 1: widen the futures store past the single ES OHLCV series.

    python scripts/futures_fetch_multi.py --plan
    python scripts/futures_fetch_multi.py --fetch  --symbols MES NQ MNQ
    python scripts/futures_fetch_multi.py --quotes --symbols ES MES NQ MNQ
    python scripts/futures_fetch_multi.py --report

WHY THIS EXISTS
---------------
`BLOCKERS.md` OWNER-3 says the futures branch is bound by data, and names two free steps
before any purchase is considered. This is step 1. `scripts/futures_data.py` built exactly
one store - `data/futures/ES.parquet`, 447,600 one-minute TRADES bars over 1.25 years - and
two things are missing from it that cost nothing to add:

  * ONE INSTRUMENT.  ES is a $50-a-point contract. A $1M paper account trades MES (1/10th),
    and nothing at all is known about the Nasdaq leg (NQ / MNQ). A cross-sectional or
    hedged idea cannot even be *stated* against a store with one column of prices, and a
    result found on ES alone has no out-of-instrument check available to it.
  * NO QUOTES.  The store is OHLCV, so `execution_sim` charges a spread it has never seen -
    `dataquality._check_quotes` prints "the spread is ASSUMED by the cost model, not
    measured" on every validation run of the ES store. An assumed cost is the cheapest way
    to manufacture an edge: assume a tick, be wrong by a tick on a 30-trade-a-day sleeve,
    and the entire result is the assumption. IBKR serves `BID_ASK` at one-minute resolution
    for these contracts, so the assumption is replaceable with a measurement for free.

WHY THIS IS A SECOND SCRIPT AND NOT AN EDIT TO `futures_data.py`
----------------------------------------------------------------
`futures_data.py` is the F-2 *probe*: its docstring pre-registers a verdict about whether
the account is permissioned at all, and its `--fetch` path is the one that produced the
deployed ES store. Rewriting it would edit the record of a pre-registered experiment and
put the one store the futures research already depends on at risk of a re-write. The chain
convention, the roll rule and the write-time refusal are therefore COPIED here deliberately
rather than imported, and `test_futures_fetch_multi.py` pins them against the originals so
the copy cannot drift silently.

WHAT IBKR ACTUALLY SERVES (measured 2026-09-13, paper account DUT091359, server 178)
------------------------------------------------------------------------------------
  * `BID_ASK` 1-minute bars come back for every contract that resolves - same bar count as
    `TRADES`, same timestamps. It is roughly 3x slower per page (222s vs 79s for a
    30,120-bar month), which is why the quote pass is a separate flag.
  * The **September-2025 micro expiries are gone**: `MESU5` and `MNQU5` return error 200
    (no security definition) by localSymbol *and* by contract month. IBKR retains roughly
    four expired quarters and the micros have already aged out of the fifth. So the MES and
    MNQ chains start one quarter later than ES and NQ, and their stores are ~3 months
    shorter. That is a fact about IBKR's retention, not a choice - see `CHAINS` below.

HOW A `BID_ASK` BAR IS SHAPED (this trips people up)
-----------------------------------------------------
IBKR does not return a bid bar and an ask bar. It returns ONE bar whose OHLC fields carry
four different quantities:

    open  = time-average BID over the minute      -> stored as `bid`
    close = time-average ASK over the minute      -> stored as `ask`
    low   = minimum BID over the minute           -> stored as `bid_low`
    high  = maximum ASK over the minute           -> stored as `ask_high`

`volume`, `average` and `barCount` are all -1 on a quote bar: there is no trade count in a
quote series, so the quote store deliberately carries no `v` column rather than a fake one.
`c` is written as the mid of `bid` and `ask` - not because a mid is interesting, but because
`check_futures_frame` reads `c` for its jump, roll and stale checks and a store that dodges
validation by omitting the column it validates on is the exact failure OWNER-3's third
resolved item was about.

clientId 77 keeps this clear of every other connection on this box: the paper runner (17),
the minute backfill (31), the F-2 probe (41), the intraday parquet store (61) and the LIVE
intraday trader (71). This script issues historical-data requests only and places no orders.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STORE = REPO / "data" / "futures"

# `python scripts/futures_fetch_multi.py` puts `scripts/` on sys.path - NOT the repo root,
# and not the working directory either. So `import quant_brain` fails, and because the
# validator is imported lazily inside `validate_and_write` it fails at the END of a fetch
# rather than the start. That cost a 27-minute MES pass on the first run of this script: all
# fifteen pages came back, then the write step raised ModuleNotFoundError and the process
# died with nothing on disk. Two fixes, both here: put the repo root on the path, and
# `preflight()` below imports the validator BEFORE the first request goes out.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: Raw pages land here before stitching. A full run is hours long (52 TRADES pages at ~79s
#: plus 72 quote pages at ~222s), and a gateway restart or a pacing violation part-way
#: through should cost the pages not yet fetched, not the ones already paid for.
CACHE = STORE / ".raw"

#: Roll this many days before last trade date. 8 is `futures_data.ROLL_DAYS`, kept identical
#: so the new stores line up bar-for-bar with the deployed ES store at every roll; a store
#: that rolled on a different day could not be used alongside it in the same backtest.
ROLL_DAYS = 8

#: How far back the FIRST contract of a chain reaches before its own roll. 95 days is
#: `futures_data`'s figure and reproduces ES.parquet's first bar exactly (2025-06-08).
LEAD_DAYS = 95

#: The front-quarter chains. ES and NQ are the same five expiries `futures_data.ES_CHAIN`
#: uses. MES and MNQ start at Z5 because IBKR no longer has a security definition for the
#: U5 micros (error 200, verified both by localSymbol and by contract month on 2026-09-13),
#: so their stores begin at 2025-09-07 rather than 2025-06-08. Listing that as a shorter
#: chain rather than as a skipped element matters: `_windows` gives the first contract of a
#: chain a 95-day lead-in, so this recovers a quarter of MES history that a "skip the dead
#: contract" implementation would silently drop.
CHAINS: dict[str, list[tuple[str, str]]] = {
    "ES": [("ESU5", "20250919"), ("ESZ5", "20251219"), ("ESH6", "20260320"),
           ("ESM6", "20260618"), ("ESU6", "20260918")],
    "NQ": [("NQU5", "20250919"), ("NQZ5", "20251219"), ("NQH6", "20260320"),
           ("NQM6", "20260618"), ("NQU6", "20260918")],
    "MES": [("MESZ5", "20251219"), ("MESH6", "20260320"),
            ("MESM6", "20260618"), ("MESU6", "20260918")],
    "MNQ": [("MNQZ5", "20251219"), ("MNQH6", "20260320"),
            ("MNQM6", "20260618"), ("MNQU6", "20260918")],
}

#: IBKR's own limit is 60 historical requests in any rolling ten minutes; exceeding it earns
#: error 162 and a silent hole in the store. Nothing here comes close (a page takes 79-222s,
#: so the natural rate is ~4 per ten minutes) but the throttle is cheap and a future caller
#: who fetches a cached-heavy run could hit it.
MAX_REQUESTS = 55
WINDOW_SECONDS = 600

#: IBKR housekeeping messages, not failures. Same list `futures_data.probe` filters on, plus
#: 2100/2119/2150 which the gateway emits on connect and on farm re-connection.
BENIGN = frozenset({2104, 2106, 2107, 2158, 2100, 2119, 2150})


# ------------------------------------------------------------------------------- windows

def windows(chain: list[tuple[str, str]]) -> list[tuple[str, dt.date, dt.date]]:
    """(localSymbol, window_start, window_end) for each contract's own front quarter.

    Identical arithmetic to `futures_data._windows`, reproduced rather than imported for the
    reason in the module docstring. Each contract owns the period from the previous
    contract's roll to its own; the first owns a `LEAD_DAYS` run-up because there is no
    previous roll to hand off from.
    """
    out, prev_roll = [], None
    for ls, exp in chain:
        roll = dt.datetime.strptime(exp, "%Y%m%d").date() - dt.timedelta(days=ROLL_DAYS)
        start = prev_roll if prev_roll else roll - dt.timedelta(days=LEAD_DAYS)
        out.append((ls, start, roll))
        prev_roll = roll
    return out


def plan(symbols: list[str], quotes: bool) -> list[str]:
    """What a run would request, without connecting. Printed by `--plan`.

    Worth having because the cost of this job is measured in hours: a caller should be able
    to see the page count and the expiries before committing to it.
    """
    lines = []
    total = 0
    for sym in symbols:
        for ls, start, end in windows(CHAINS[sym]):
            pages = _pages(start, end)
            total += len(pages)
            lines.append(f"  {sym:4s} {ls:6s} {start} .. {end}  {len(pages)} page(s)")
    per = 222 if quotes else 79
    lines.append(f"  {total} page(s) total, ~{total * per / 60:.0f} min at "
                 f"~{per}s/page ({'BID_ASK' if quotes else 'TRADES'})")
    return lines


def _pages(start: dt.date, end: dt.date) -> list[str]:
    """The `endDateTime` stamps that cover [start, end] walking back a month at a time.

    One month is IBKR's per-request cap at one-minute resolution, so a quarter is four
    requests. 21:00 is chosen (as in `futures_data`) because it sits after the CME close and
    before the next session opens, so a page boundary never lands mid-session.
    """
    out, cur = [], end
    while cur > start:
        out.append(cur.strftime("%Y%m%d") + "-21:00:00")
        cur = cur - dt.timedelta(days=30)
    return out


# -------------------------------------------------------------------------------- fetch

class Pacer:
    """Rolling-window request throttle. Sleeps rather than letting IBKR refuse."""

    def __init__(self, limit: int = MAX_REQUESTS, window: float = WINDOW_SECONDS):
        self.limit, self.window, self.stamps = limit, window, []

    def wait(self) -> None:
        now = time.time()
        self.stamps = [s for s in self.stamps if now - s < self.window]
        if len(self.stamps) >= self.limit:
            nap = self.window - (now - self.stamps[0]) + 1.0
            print(f"[fm] pacing: sleeping {nap:.0f}s to stay under "
                  f"{self.limit} requests / {self.window / 60:.0f} min", flush=True)
            time.sleep(nap)
            now = time.time()
            self.stamps = [s for s in self.stamps if now - s < self.window]
        self.stamps.append(time.time())


def _qualify(ib, sym: str, ls: str):
    """Resolve one dated contract, or None.

    `ib_async.qualifyContracts` returns a non-empty list even when the request failed - the
    unresolved entry comes back with `conId == 0`, and 2.1.0 will then raise deep inside
    `reqHistoricalData` with an unrelated AttributeError. `futures_data`'s `if not q:` guard
    predates that behaviour. Checking `conId` is what actually distinguishes "IBKR has
    dropped this expiry" from "IBKR served it", which is the MES/MNQ U5 case.
    """
    from ib_async import Future

    try:
        got = ib.qualifyContracts(
            Future(symbol=sym, exchange="CME", localSymbol=ls, includeExpired=True))
    except Exception as exc:  # noqa: BLE001 - a dropped expiry is a finding, not a crash
        print(f"[fm] {ls}: qualify raised {str(exc)[:90]}")
        return None
    live = [c for c in got if c is not None and getattr(c, "conId", 0)]
    if not live:
        print(f"[fm] {ls}: no security definition - IBKR has dropped this expiry")
        return None
    return live[0]


def _rows(bars, what: str, ls: str) -> list[dict]:
    """One IBKR bar list -> store rows. The only place the BID_ASK field mapping lives."""
    if what == "TRADES":
        return [{"t": b.date, "o": b.open, "h": b.high, "l": b.low, "c": b.close,
                 "v": float(b.volume), "contract": ls} for b in bars]
    # See the module docstring: open/close are the time-average bid/ask, low/high the
    # min bid / max ask. Nothing else in this repository should have to know that.
    return [{"t": b.date, "bid": b.open, "ask": b.close,
             "bid_low": b.low, "ask_high": b.high,
             "spread": b.close - b.open, "c": (b.open + b.close) / 2.0,
             "contract": ls} for b in bars]


def _page(ib, con, ls: str, sym: str, stamp: str, what: str, pacer, use_cache: bool):
    """Fetch (or re-read) one month of one contract at one bar size."""
    import pandas as pd

    key = CACHE / f"{sym}_{ls}_{what}_{stamp[:8]}.parquet"
    if use_cache and key.exists():
        df = pd.read_parquet(key)
        print(f"[fm] {ls} {what} {stamp[:8]}: {len(df):6d} bars (cached)", flush=True)
        return df
    pacer.wait()
    t0 = time.time()
    try:
        bars = ib.reqHistoricalData(
            con, endDateTime=stamp, durationStr="1 M", barSizeSetting="1 min",
            whatToShow=what, useRTH=False, formatDate=1, timeout=600)
    except Exception as exc:  # noqa: BLE001 - report the refusal, keep the pages we have
        print(f"[fm] {ls} {what} {stamp}: {str(exc)[:90]}", flush=True)
        return None
    if not bars:
        print(f"[fm] {ls} {what} {stamp}: empty", flush=True)
        return None
    df = pd.DataFrame(_rows(bars, what, ls))
    if use_cache:
        CACHE.mkdir(parents=True, exist_ok=True)
        df.to_parquet(key, index=False)
    print(f"[fm] {ls} {what} {stamp[:8]}: {len(df):6d} bars in {time.time() - t0:5.0f}s",
          flush=True)
    return df


def stitch(sym: str, frames: list, what: str):
    """Concatenate the pages and keep each timestamp once, from its own front-quarter.

    Same rule as `futures_data.fetch`: a bar counts only while its contract is the front
    month, and where two contracts both quote a timestamp the earlier one in chain order
    wins. `drop_duplicates(keep="first")` does that because `keep` is built in chain order.
    """
    import pandas as pd

    allbars = pd.concat(frames, ignore_index=True)
    allbars["t"] = pd.to_datetime(allbars["t"], utc=True)
    keep = []
    for ls, start, end in windows(CHAINS[sym]):
        s = pd.Timestamp(start, tz="UTC")
        e = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
        keep.append(allbars[(allbars["contract"] == ls) & (allbars["t"] >= s)
                            & (allbars["t"] < e)])
    return (pd.concat(keep, ignore_index=True)
              .drop_duplicates(subset=["t"], keep="first")
              .sort_values("t")
              .reset_index(drop=True))


def validate_and_write(name: str, df, path: Path, *, dry_run: bool = False) -> bool:
    """Validate at the boundary where data enters, and REFUSE to write a failing store.

    Copied intent from `futures_data.fetch`: a store that is written first and checked later
    has already been researched on by the time anyone reads the report. The roll and quote
    hazards this looks for survive an RTH filter and then become P&L. Returns True only if
    the store is on disk (or would be, under `--dry-run`).
    """
    from quant_brain.markets.futures_cme.dataquality import check_futures_frame

    report = check_futures_frame(name, df, time_col="t")
    for finding in report.findings:
        print(finding.line())
    print(f"  {report.summary()}")
    if report.failed:
        print(f"REFUSED to write {path}: the fetched series is not usable")
        return False
    if dry_run:
        print(f"[fm] dry-run: would write {len(df):,} rows -> {path}")
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return True


def preflight() -> None:
    """Import everything the WRITE path needs before the first request goes out.

    A fetch is measured in hours and a validator import is measured in milliseconds, so
    doing them in that order is free. Doing them in the other order is what turned a
    one-character path bug into a 27-minute pass that ended with nothing on disk: the
    validator is imported lazily inside `validate_and_write`, so `ModuleNotFoundError`
    surfaced only once all fifteen MES pages had already been paid for.

    Anything that can make the write fail belongs in here, not at the end.
    """
    from quant_brain.markets.futures_cme.dataquality import check_futures_frame  # noqa: F401


def fetch(args, what: str) -> int:
    """Fetch one bar type for every requested symbol, writing each store as it completes.

    Per-symbol writes are deliberate: the whole job is hours long, and a symbol finished is
    a symbol that survives a disconnection three hours later.
    """
    from ib_async import IB

    preflight()
    suffix = "" if what == "TRADES" else "_quotes"
    ib = IB()
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=30)
    except Exception as exc:  # noqa: BLE001 - unreachable gateway is reported, never faked
        print(f"[fm] cannot connect to IB Gateway at {args.host}:{args.port}: {exc}")
        print("[fm] no store written. This script does not synthesise futures data.")
        return 2
    print(f"[fm] connected {list(ib.managedAccounts())} clientId={args.client_id} "
          f"what={what}", flush=True)

    errors: list[tuple[int, str]] = []
    ib.errorEvent += lambda reqId, code, msg, c=None: (
        errors.append((code, msg)) if code not in BENIGN else None)

    pacer = Pacer()
    rc = 0
    for sym in args.symbols:
        frames, missing = [], []
        for ls, start, end in windows(CHAINS[sym]):
            con = _qualify(ib, sym, ls)
            if con is None:
                missing.append(ls)
                continue
            got = 0
            for stamp in _pages(start, end):
                df = _page(ib, con, ls, sym, stamp, what, pacer, not args.no_cache)
                if df is None:
                    continue
                frames.append(df)
                got += len(df)
            print(f"[fm] {ls}: {got:7d} bars over {start}..{end}", flush=True)

        path = STORE / f"{sym}{suffix}.parquet"
        if not frames:
            print(f"[fm] {sym}{suffix}: nothing fetched; no store written")
            rc = 2
            continue
        out = stitch(sym, frames, what)
        if missing:
            print(f"[fm] {sym}: {len(missing)} expiry/expiries unavailable: "
                  f"{', '.join(missing)}")
        if not validate_and_write(f"{sym}{suffix}", out, path, dry_run=args.dry_run):
            rc = 2
            continue
        days = out["t"].dt.tz_convert("America/New_York").dt.date.nunique()
        print(f"[fm] {sym}{suffix}: {len(out):,} bars / {days} days "
              f"({out['t'].min()} .. {out['t'].max()}) -> {path}", flush=True)
        if what == "BID_ASK":
            print("  " + spread_summary(out).replace("\n", "\n  "), flush=True)

    for code, msg in errors[:10]:
        print(f"[fm] ! IBKR {code}: {msg[:110]}")
    ib.disconnect()
    return rc


def spread_summary(df) -> str:
    """The number OWNER-3 step 1 exists to produce: what the spread ACTUALLY is.

    Reported three ways because three different consumers need three different units:

      TICKS       what `execution_sim` charges, and what a trader thinks in.
      POINTS      the raw quote, so the tick conversion can be checked by hand.
      BASIS POINTS the only unit that can be compared across instruments and across time.
                  A tick is a FIXED 0.25 points, so its cost in bps falls as the index
                  rises - one ES tick was 0.57 bps at 4,400 and is 0.33 bps at 7,600.  An
                  "assumed one tick" cost model is therefore not a constant assumption at
                  all: it silently gets cheaper every year the market goes up, which is the
                  direction that flatters a backtest.  Quoting bps is what makes that
                  visible.

    Computed per row against that row's own mid rather than against one representative
    price level, so the bps figures carry the drift in the index over the sample instead of
    pinning it to whatever level someone picked.

    Split RTH / overnight because a sleeve that only trades the cash session must not be
    costed at an average dragged up by 3am, and the 0.5%-of-notional tail overnight is
    exactly where an unsplit mean comes from.
    """
    import pandas as pd

    tick = 0.25  # ES, MES, NQ and MNQ all tick in quarter-points
    # The mask is built on the full frame and then subset by the SAME boolean the spread was
    # subset by. Dropping NaNs first and indexing with a full-length mask afterwards is a
    # silent length mismatch the moment one quote fails to parse, and it would mis-attribute
    # every minute after the first bad one to the wrong session.
    spread = pd.Series(pd.to_numeric(df["spread"], errors="coerce"))
    mid = pd.Series(pd.to_numeric(df["c"], errors="coerce"))
    et = pd.DatetimeIndex(pd.to_datetime(df["t"], utc=True)).tz_convert("America/New_York")
    minutes = pd.Series((et.hour * 60 + et.minute).to_numpy(), index=spread.index)
    ok = spread.notna() & mid.notna() & (mid > 0)
    s, in_rth = spread[ok], ((minutes >= 570) & (minutes < 960))[ok]
    bps = (s / mid[ok]) * 10_000.0
    if not len(s):
        return "spread: no parsable quotes"

    def _row(label, sub, sub_bps):
        return (f"  {label:11s} n={len(sub):7,d}  median {sub.median() / tick:5.2f} ticks "
                f"({sub.median():.4f} pts, {sub_bps.median():.3f} bps)  "
                f"mean {sub.mean() / tick:5.2f} ticks ({sub.mean():.4f} pts, "
                f"{sub_bps.mean():.3f} bps)")

    lines = ["spread (quoted, one side to the other):", _row("all hours", s, bps)]
    for label, mask in (("RTH", in_rth), ("overnight", ~in_rth)):
        if mask.any():
            lines.append(_row(label, s[mask], bps[mask]))
    lines.append(f"  p95 {s.quantile(0.95) / tick:.2f} ticks "
                 f"({bps.quantile(0.95):.3f} bps), max {s.max() / tick:.2f} ticks")

    # What a strategy actually pays. Crossing the spread costs half of it per side at the
    # mid, so a round trip costs one full quoted spread - which is the figure F-2a's
    # measured round-trip cost has to be compared against, not the half.
    rt = bps[in_rth] if in_rth.any() else bps
    lines.append(f"  round trip at the RTH median quote: {s[in_rth].median() / tick:.2f} "
                 f"ticks = {rt.median():.3f} bps  (half-spread per side "
                 f"{rt.median() / 2:.3f} bps)")
    at_one = float((s <= tick).mean())
    lines.append(f"  {at_one:.1%} of minutes quote one tick or tighter; the cost model's "
                 f"ASSUMED one tick is {'SUPPORTED' if at_one >= 0.5 else 'NOT supported'} "
                 f"as the typical quote")
    return "\n".join(lines)


# ------------------------------------------------------------------------------- report

def report() -> int:
    """Re-validate every store on disk. No connection, no fetch - just the current truth."""
    import pandas as pd

    from quant_brain.markets.futures_cme.dataquality import check_futures_frame

    paths = sorted(STORE.glob("*.parquet"))
    if not paths:
        print(f"[fm] no stores under {STORE}")
        return 1
    worst = 0
    for p in paths:
        df = pd.read_parquet(p)
        ts = pd.to_datetime(df["t"], utc=True)
        days = ts.dt.tz_convert("America/New_York").dt.date.nunique()
        print(f"\n{p.name}: {len(df):,} rows / {days} days "
              f"({ts.min()} .. {ts.max()})  cols={list(df.columns)}")
        rep = check_futures_frame(p.stem, df, time_col="t")
        for f in rep.findings:
            print(f.line())
        print(f"  {rep.summary()}")
        if "spread" in df.columns:
            print("  " + spread_summary(df).replace("\n", "\n  "))
        worst = max(worst, 2 if rep.failed else 0)
    return worst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="fetch TRADES stores")
    ap.add_argument("--quotes", action="store_true", help="fetch BID_ASK quote stores")
    ap.add_argument("--plan", action="store_true", help="print the request plan, no connect")
    ap.add_argument("--report", action="store_true", help="re-validate the stores on disk")
    ap.add_argument("--symbols", nargs="+", default=["MES", "NQ", "MNQ"],
                    choices=sorted(CHAINS))
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and validate but do not write the parquet")
    ap.add_argument("--no-cache", action="store_true", help="ignore and skip the raw page cache")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002, help="4002 IB Gateway, 7497 TWS")
    ap.add_argument("--client-id", type=int, default=77,
                    help="77 by default: distinct from the live sleeve's 71 and the "
                         "F-2 probe's 41, so this never displaces a trading connection")
    args = ap.parse_args()

    if args.plan:
        for line in plan(args.symbols, args.quotes):
            print(line)
        return 0
    if args.report:
        return report()
    if not (args.fetch or args.quotes):
        ap.error("nothing to do: pass --fetch, --quotes, --plan or --report")

    rc = 0
    if args.fetch:
        rc = max(rc, fetch(args, "TRADES"))
    if args.quotes:
        rc = max(rc, fetch(args, "BID_ASK"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
