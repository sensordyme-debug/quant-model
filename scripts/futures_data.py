#!/usr/bin/env python3
"""F-2a: find out whether this IBKR paper account can serve CME index-futures history,
and if it can, write that history to a local store the way `alpaca_data.py` does.

    python scripts/futures_data.py --probe
    python scripts/futures_data.py --fetch --symbols MES --months 6
    python scripts/futures_data.py --report

WHY THIS EXISTS, AND WHAT IS PRE-REGISTERED
-------------------------------------------
`research/backlog.md` has carried F-2 (the index-futures track) as "needs owner: IBKR
futures permission + CME data, or a Databento key" since 2026-09-10.  Nobody has ever
tested that claim, and it is the last open item in the backlog with a stated mechanism;
everything else is either refused, standing, or an owner decision.  A blocker that has
never been probed is an assumption, and this repository's rule since S-24 is that an
assumption gets measured or it gets a sign.

Pre-registered before the first request, so the answer cannot be moved afterwards:

  (1) UNBLOCKED if IB Gateway returns at least one full session of 1-minute TRADES bars
      for the front-month contract of at least one of ES / MES / NQ / MNQ.  Then F-2 is
      the loop's work and no purchase is needed.
  (2) BLOCKED if every request is refused.  Then the deliverable is not "needs data" but
      the exact product name and error code, written to research/BLOCKERS.md, so the
      owner can buy the right thing once instead of guessing.
  (3) A contract definition that resolves is NOT evidence of (1).  IBKR returns security
      definitions for instruments it will not price - `reqContractDetails` succeeding
      only proves the symbol exists.  The test is bars, and the number of them.

Read the distinction the probe reports:

  * `secdef`      - the contract exists and IBKR described it (permission-free).
  * `head`        - `reqHeadTimeStamp` answered, i.e. the data farm admits to holding a
                    history for it.  Still not a grant: it is refused per-request.
  * `bars`        - actual OHLCV rows.  This is the only line that decides (1) vs (2).

Error codes worth naming in the report rather than swallowing: 200 (no security
definition), 162 (historical data service error - IBKR's catch-all, which is what a
missing CME subscription usually looks like), 354 (not subscribed), 10197 (no market
data during competing live session), 321 (server validation).

clientId 41 keeps this clear of the paper runner (17), the minute backfill (31), the
intraday parquet store (61) and the live intraday trader (71).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STORE = REPO / "data" / "futures"
REPORT = REPO / "research" / "futures_probe.json"

# The four contracts that matter for F-2, cheapest-to-trade first.  The micros (MES/MNQ)
# are what a $1M paper account would actually trade - one MES is ~1/10th of one ES - and
# they carry the same underlying index, so a refusal on the minis is not a refusal on the
# track if the micros answer.
CONTRACTS = [
    ("MES", "CME", "Micro E-mini S&P 500"),
    ("ES", "CME", "E-mini S&P 500"),
    ("MNQ", "CME", "Micro E-mini Nasdaq-100"),
    ("NQ", "CME", "E-mini Nasdaq-100"),
]

# What each contract is worth, so a later harness prices a tick rather than a percent.
# Source: CME contract specifications.  Kept here because the probe is the first thing
# in this repository to know a futures multiplier and the next script should not re-guess.
SPECS = {
    "MES": {"multiplier": 5.0, "tick": 0.25, "tick_value": 1.25},
    "ES": {"multiplier": 50.0, "tick": 0.25, "tick_value": 12.50},
    "MNQ": {"multiplier": 2.0, "tick": 0.25, "tick_value": 0.50},
    "NQ": {"multiplier": 20.0, "tick": 0.25, "tick_value": 5.00},
}


def _front_month(details: list) -> list:
    """Sort resolved contract months ascending and drop anything already expired."""
    today = dt.date.today().strftime("%Y%m%d")
    months = sorted(
        {d.contract.lastTradeDateOrContractMonth for d in details if d.contract.lastTradeDateOrContractMonth},
    )
    return [m for m in months if m >= today]


def probe(args) -> dict:
    from ib_async import IB, Future

    ib = IB()
    out = {
        "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "host": args.host,
        "port": args.port,
        "connected": False,
        "accounts": [],
        "results": {},
        "errors": [],
    }

    # Collect IBKR's own error stream - the reason a request failed is the deliverable
    # here, not a nuisance, so it is captured rather than printed and lost.
    seen: list[dict] = []
    ib.errorEvent += lambda reqId, code, msg, c=None: seen.append(
        {"reqId": reqId, "code": code, "msg": msg}
    )

    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=25)
    except Exception as exc:  # noqa: BLE001 - the message is the finding
        out["errors"].append(f"connect: {exc}")
        print(f"[f2] cannot connect to IB Gateway at {args.host}:{args.port}: {exc}")
        return out

    out["connected"] = True
    out["accounts"] = list(ib.managedAccounts())
    print(f"[f2] connected {out['accounts']}  server {ib.client.serverVersion()}")

    for sym, exch, label in CONTRACTS:
        res = {"label": label, "secdef": 0, "months": [], "head": None,
               "bars_1m": 0, "bars_1d": 0, "sample": None, "errors": []}
        mark = len(seen)

        try:
            details = ib.reqContractDetails(Future(symbol=sym, exchange=exch))
        except Exception as exc:  # noqa: BLE001
            details = []
            res["errors"].append(f"secdef: {exc}")
        res["secdef"] = len(details)
        res["months"] = _front_month(details)[:4]
        print(f"[f2] {sym:4s} secdef={res['secdef']:3d}  front={res['months'][:2]}")

        if res["months"]:
            con = Future(symbol=sym, exchange=exch,
                         lastTradeDateOrContractMonth=res["months"][0])
            qual = ib.qualifyContracts(con)
            if qual:
                con = qual[0]

                # (a) does the farm admit to a history at all?
                try:
                    res["head"] = str(ib.reqHeadTimeStamp(con, whatToShow="TRADES", useRTH=False))
                except Exception as exc:  # noqa: BLE001
                    res["errors"].append(f"head: {exc}")

                # (b) daily bars - the cheapest possible request
                try:
                    d = ib.reqHistoricalData(
                        con, endDateTime="", durationStr="10 D", barSizeSetting="1 day",
                        whatToShow="TRADES", useRTH=False, formatDate=1, timeout=45)
                    res["bars_1d"] = len(d)
                except Exception as exc:  # noqa: BLE001
                    res["errors"].append(f"daily: {exc}")

                # (c) the one that decides: a session of 1-minute TRADES bars
                try:
                    m = ib.reqHistoricalData(
                        con, endDateTime="", durationStr="2 D", barSizeSetting="1 min",
                        whatToShow="TRADES", useRTH=False, formatDate=1, timeout=90)
                    res["bars_1m"] = len(m)
                    if m:
                        b = m[-1]
                        res["sample"] = {"t": str(b.date), "o": b.open, "h": b.high,
                                         "l": b.low, "c": b.close, "v": float(b.volume)}
                except Exception as exc:  # noqa: BLE001
                    res["errors"].append(f"minute: {exc}")

        res["ib_errors"] = [e for e in seen[mark:] if e["code"] not in (2104, 2106, 2107, 2158)]
        for e in res["ib_errors"]:
            res["errors"].append(f"{e['code']}: {e['msg'][:120]}")
        print(f"[f2] {sym:4s} head={res['head']}  daily={res['bars_1d']}  "
              f"minute={res['bars_1m']}  errors={len(res['ib_errors'])}")
        for e in res["ib_errors"][:3]:
            print(f"      ! {e['code']} {e['msg'][:110]}")
        out["results"][sym] = res

    ib.disconnect()
    return out


def depth(args) -> dict:
    """Stage 2. `--probe` proves the account is permissioned; it does not prove there is
    enough history to research on.

    A quarterly contract lists years before it expires but is only liquid in its own front
    quarter, so the 2,760 bars stage 1 returned are two sessions of ONE contract.  A usable
    F-2 sample is either (a) IBKR's own back-adjusted CONTFUT series, or (b) a stitch of
    expired quarterlies, which only works if IBKR still retains them.  A-4 put the power
    requirement on this repository's intraday work at ~2,000 sessions, so the number this
    stage reports - years of 1-minute history - is what decides whether F-2 is a research
    track or a second purchase request.
    """
    from ib_async import IB, ContFuture, Future

    ib = IB()
    out = {
        "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "contfut": {},
        "expired": {},
        "errors": [],
    }
    seen: list[dict] = []
    ib.errorEvent += lambda reqId, code, msg, c=None: seen.append(
        {"reqId": reqId, "code": code, "msg": msg})

    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=25)
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"connect: {exc}")
        print(f"[f2] cannot connect: {exc}")
        return out
    print(f"[f2] connected {list(ib.managedAccounts())}")

    for sym, exch, _label in CONTRACTS:
        r = {"head": None, "bars_1m": 0, "first": None, "last": None, "errors": []}
        mark = len(seen)
        try:
            qual = ib.qualifyContracts(ContFuture(symbol=sym, exchange=exch))
            con = qual[0] if qual else None
        except Exception as exc:  # noqa: BLE001
            con = None
            r["errors"].append(f"qualify: {exc}")
        if con is not None:
            try:
                r["head"] = str(ib.reqHeadTimeStamp(con, whatToShow="TRADES", useRTH=False))
            except Exception as exc:  # noqa: BLE001
                r["errors"].append(f"head: {exc}")
            try:
                m = ib.reqHistoricalData(
                    con, endDateTime="", durationStr="2 D", barSizeSetting="1 min",
                    whatToShow="TRADES", useRTH=False, formatDate=1, timeout=90)
                r["bars_1m"] = len(m)
                if m:
                    r["first"], r["last"] = str(m[0].date), str(m[-1].date)
            except Exception as exc:  # noqa: BLE001
                r["errors"].append(f"minute: {exc}")
        r["ib_errors"] = [e for e in seen[mark:] if e["code"] not in (2104, 2106, 2107, 2158)]
        for e in r["ib_errors"]:
            r["errors"].append(f"{e['code']}: {e['msg'][:120]}")
        out["contfut"][sym] = r
        print(f"[f2] CONTFUT {sym:4s} head={str(r['head'])[:19]:19s} 1m={r['bars_1m']:5d} "
              f"err={len(r['ib_errors'])}")

    # Can an already-expired quarterly still be fetched?  If yes, a stitched series can be
    # built as far back as IBKR retains; if no, CONTFUT is the only route.
    for sym, exch, month in [("ES", "CME", "20260619"), ("ES", "CME", "20250620"),
                             ("MES", "CME", "20250620")]:
        key = f"{sym}{month}"
        r = {"bars_1m": 0, "errors": []}
        mark = len(seen)
        try:
            c = Future(symbol=sym, exchange=exch, lastTradeDateOrContractMonth=month,
                       includeExpired=True)
            qual = ib.qualifyContracts(c)
            con = qual[0] if qual else None
            if con is not None:
                m = ib.reqHistoricalData(
                    con, endDateTime=month + " 12:00:00 US/Eastern", durationStr="1 D",
                    barSizeSetting="1 min", whatToShow="TRADES", useRTH=False,
                    formatDate=1, timeout=90)
                r["bars_1m"] = len(m)
        except Exception as exc:  # noqa: BLE001
            r["errors"].append(str(exc))
        r["ib_errors"] = [e for e in seen[mark:] if e["code"] not in (2104, 2106, 2107, 2158)]
        for e in r["ib_errors"]:
            r["errors"].append(f"{e['code']}: {e['msg'][:120]}")
        out["expired"][key] = r
        print(f"[f2] EXPIRED {key:12s} 1m={r['bars_1m']:5d} err={len(r['ib_errors'])}")
        for e in r["ib_errors"][:2]:
            print(f"      ! {e['code']} {e['msg'][:110]}")

    # Stage 3. `reqHeadTimeStamp` is IBKR's claim, not its behaviour, and the two differ
    # often enough that the claim is not worth trusting: ask for more than it offers and
    # see what comes back.  Daily first (cheap), then minute at the bar size F-2 needs.
    out["extent"] = {}
    for sym, exch, _l in CONTRACTS:
        e = {"daily_bars": 0, "daily_first": None, "minute_bars": 0, "minute_first": None,
             "errors": []}
        mark = len(seen)
        try:
            qual = ib.qualifyContracts(ContFuture(symbol=sym, exchange=exch))
            con = qual[0] if qual else None
            if con is not None:
                d = ib.reqHistoricalData(
                    con, endDateTime="", durationStr="15 Y", barSizeSetting="1 day",
                    whatToShow="TRADES", useRTH=False, formatDate=1, timeout=120)
                e["daily_bars"] = len(d)
                if d:
                    e["daily_first"], e["daily_last"] = str(d[0].date), str(d[-1].date)
                m = ib.reqHistoricalData(
                    con, endDateTime="", durationStr="1 M", barSizeSetting="1 min",
                    whatToShow="TRADES", useRTH=False, formatDate=1, timeout=180)
                e["minute_bars"] = len(m)
                if m:
                    e["minute_first"], e["minute_last"] = str(m[0].date), str(m[-1].date)
        except Exception as exc:  # noqa: BLE001
            e["errors"].append(str(exc))
        e["ib_errors"] = [x for x in seen[mark:] if x["code"] not in (2104, 2106, 2107, 2158)]
        out["extent"][sym] = e
        print(f"[f2] EXTENT  {sym:4s} daily {e['daily_bars']:5d} from {str(e['daily_first'])[:10]:10s}"
              f"  minute {e['minute_bars']:7d} from {str(e['minute_first'])[:10]}")

    ib.disconnect()
    return out


# The front-quarter stitch. IBKR refuses an endDateTime on a CONTFUT (error 10339) and
# caps a 1-minute continuous request at one month, so the continuous series cannot be
# paged and is useless for research; dated quarterlies CAN be paged, and IBKR still
# carries roughly four expired quarters.  Each contract is used only during the quarter
# in which it is the front month, rolling 8 calendar days before its own expiry, which is
# the convention CME's own volume shift follows.
ES_CHAIN = [
    ("ESU5", "20250919"), ("ESZ5", "20251219"), ("ESH6", "20260320"),
    ("ESM6", "20260618"), ("ESU6", "20260918"),
]
MES_CHAIN = [
    ("MESU5", "20250919"), ("MESZ5", "20251219"), ("MESH6", "20260320"),
    ("MESM6", "20260618"), ("MESU6", "20260918"),
]
CHAINS = {"ES": ES_CHAIN, "MES": MES_CHAIN}
ROLL_DAYS = 8


def _windows(chain):
    """(localSymbol, window_start, window_end) for each contract's own front quarter."""
    out, prev_roll = [], None
    for ls, exp in chain:
        roll = dt.datetime.strptime(exp, "%Y%m%d").date() - dt.timedelta(days=ROLL_DAYS)
        start = prev_roll if prev_roll else roll - dt.timedelta(days=95)
        out.append((ls, start, roll))
        prev_roll = roll
    return out


def fetch(args) -> int:
    import pandas as pd
    from ib_async import IB, Future

    ib = IB()
    ib.connect(args.host, args.port, clientId=args.client_id, timeout=25)
    print(f"[f2] connected {list(ib.managedAccounts())}")
    STORE.mkdir(parents=True, exist_ok=True)

    for sym in args.symbols:
        frames = []
        for ls, start, end in _windows(CHAINS[sym]):
            q = ib.qualifyContracts(Future(symbol=sym, exchange="CME", localSymbol=ls,
                                           includeExpired=True))
            if not q:
                print(f"[f2] {ls}: no security definition - IBKR has dropped this expiry")
                continue
            con = q[0]
            # One month is IBKR's per-request cap at this bar size, so walk the window
            # forward a month at a time and let the de-duplication below sort out overlap.
            cur = end
            got = 0
            while cur > start:
                stamp = cur.strftime("%Y%m%d") + "-21:00:00"
                try:
                    bars = ib.reqHistoricalData(
                        con, endDateTime=stamp, durationStr="1 M", barSizeSetting="1 min",
                        whatToShow="TRADES", useRTH=False, formatDate=1, timeout=240)
                except Exception as exc:  # noqa: BLE001
                    print(f"[f2] {ls} {stamp}: {str(exc)[:90]}")
                    bars = []
                if not bars:
                    break
                df = pd.DataFrame(
                    [{"t": b.date, "o": b.open, "h": b.high, "l": b.low, "c": b.close,
                      "v": float(b.volume), "contract": ls} for b in bars])
                frames.append(df)
                got += len(df)
                cur = cur - dt.timedelta(days=30)
            print(f"[f2] {ls}: {got:7d} bars over {start}..{end}")

        if not frames:
            print(f"[f2] {sym}: nothing fetched")
            continue
        allbars = pd.concat(frames, ignore_index=True)
        allbars["t"] = pd.to_datetime(allbars["t"], utc=True)
        # Keep each timestamp once, from the contract whose front quarter covers it.
        keep = []
        for ls, start, end in _windows(CHAINS[sym]):
            s = pd.Timestamp(start, tz="UTC")
            e = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
            keep.append(allbars[(allbars["contract"] == ls) & (allbars["t"] >= s)
                                & (allbars["t"] < e)])
        out = (pd.concat(keep, ignore_index=True)
                 .drop_duplicates(subset=["t"], keep="first")
                 .sort_values("t")
                 .reset_index(drop=True))
        path = STORE / f"{sym}.parquet"
        out.to_parquet(path, index=False)
        days = out["t"].dt.tz_convert("America/New_York").dt.date.nunique()
        print(f"[f2] {sym}: wrote {len(out):,} bars / {days} days "
              f"({out['t'].min()} .. {out['t'].max()}) -> {path}")
    ib.disconnect()
    return 0


def verdict(out: dict) -> tuple[bool, str]:
    """Apply the pre-registered rule. Bars decide; nothing else does."""
    best = max((r.get("bars_1m", 0) for r in out.get("results", {}).values()), default=0)
    if best >= 300:  # a full RTH session is 390 bars; 300 is a session with gaps
        return True, f"UNBLOCKED: {best} one-minute bars returned"
    if best > 0:
        return False, f"PARTIAL: only {best} one-minute bars returned"
    return False, "BLOCKED: no historical bars for any of ES/MES/NQ/MNQ"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true", help="test what the account can serve")
    ap.add_argument("--depth", action="store_true", help="how far back the history goes")
    ap.add_argument("--fetch", action="store_true", help="stitch the front-quarter store")
    ap.add_argument("--symbols", nargs="+", default=["ES"], choices=sorted(CHAINS))
    ap.add_argument("--report", action="store_true", help="re-read the last probe")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002, help="4002 IB Gateway, 7497 TWS")
    ap.add_argument("--client-id", type=int, default=41)
    args = ap.parse_args()

    if args.fetch:
        return fetch(args)

    if args.depth:
        d = depth(args)
        (REPORT.parent / "futures_depth.json").write_text(json.dumps(d, indent=2))
        best = max((r["bars_1m"] for r in d["contfut"].values()), default=0)
        heads = {s: r["head"] for s, r in d["contfut"].items()}
        print()
        print("=" * 70)
        print(f"  CONTFUT bars {best}, heads {heads}")
        print(f"  expired quarterlies: "
              f"{ {k: v['bars_1m'] for k, v in d['expired'].items()} }")
        print("=" * 70)
        return 0 if best else 2

    if args.report and not args.probe:
        if not REPORT.exists():
            print("no probe on disk; run --probe")
            return 1
        out = json.loads(REPORT.read_text())
    else:
        out = probe(args)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(out, indent=2))

    ok, msg = verdict(out)
    print()
    print("=" * 70)
    print(f"  F-2 data verdict: {msg}")
    print("=" * 70)
    for sym, r in out.get("results", {}).items():
        print(f"  {sym:4s} secdef {r['secdef']:3d}  head {str(r['head'])[:19]:19s}  "
              f"1d {r['bars_1d']:3d}  1m {r['bars_1m']:5d}")
        for e in r.get("errors", [])[:2]:
            print(f"        {e[:110]}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
