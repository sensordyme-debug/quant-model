#!/usr/bin/env python
"""What can THIS IBKR account actually serve for futures? Measured, not assumed.

    python scripts/futures_capability_audit.py            # the full matrix
    python scripts/futures_capability_audit.py --symbols ES NQ
    python scripts/futures_capability_audit.py --report   # re-read the last run

WHY A SECOND PROBE ALONGSIDE futures_data.py
---------------------------------------------
`futures_data.py --probe` answered one pre-registered question in September - can this
account serve ANY index-futures bars at all - and it answered it for four contracts
(ES/MES/NQ/MNQ). This asks a wider one before any money is spent on a data vendor: for eight
contracts across four exchanges, which RESOLUTIONS and which BAR TYPES does the account
actually return, and how far back?

Kept separate rather than folded into `futures_data.py` because that file's docstring
pre-registers a decision rule and its `CONTRACTS` list is part of that record. Widening it
after the fact would edit the evidence.

WHAT IT DOES NOT DO
-------------------
No orders, no subscriptions, no writes to any store. Read-only history requests on
clientId 42, which is clear of the paper runner (17), minute backfill (31), futures probe
(41), intraday store (61), live trader (71), dashboard (81) and the reconciler (18).

Error codes worth naming rather than swallowing, from IBKR's own list:
  200   no security definition          354   not subscribed to market data
  162   historical data service error - the catch-all a missing CME subscription wears
  10197 no market data during a competing live session
  321   server validation
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

REPORT = REPO / "research" / "futures_capability.json"
CLIENT_ID = 42

#: Eight contracts across four exchanges. The exchange matters: a wrong one returns error
#: 200 and looks identical to "not entitled", which is exactly the confusion this probe is
#: meant to remove.
CONTRACTS = [
    ("ES",  "CME",   "E-mini S&P 500"),
    ("MES", "CME",   "Micro E-mini S&P 500"),
    ("NQ",  "CME",   "E-mini Nasdaq-100"),
    ("MNQ", "CME",   "Micro E-mini Nasdaq-100"),
    ("RTY", "CME",   "E-mini Russell 2000"),
    ("M2K", "CME",   "Micro E-mini Russell 2000"),
    ("CL",  "NYMEX", "Crude Oil"),
    ("GC",  "COMEX", "Gold"),
]

#: (label, barSize, duration). IBKR caps duration per bar size; these are the largest the
#: API accepts for each, so a failure is entitlement rather than a malformed request.
RESOLUTIONS = [
    ("daily",  "1 day",   "1 Y"),
    ("hour",   "1 hour",  "1 M"),
    ("minute", "1 min",   "2 D"),
    ("second", "30 secs", "1 D"),
]

#: whatToShow values. TRADES is the bar the harness prices; the others decide whether this
#: account can ever build a spread-aware or open-interest-aware feature.
BAR_TYPES = ["TRADES", "MIDPOINT", "BID_ASK", "OPTION_IMPLIED_VOLATILITY"]


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:160]


def probe(symbols: list[str], host: str, port: int, client_id: int) -> dict:
    from ib_async import IB, ContFuture, Future

    ib = IB()
    out: dict = {"ts": dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ"),
                 "host": host, "port": port, "results": {}}
    try:
        ib.connect(host, port, clientId=client_id, timeout=30, readonly=True)
    except Exception as exc:
        out["connected"] = False
        out["error"] = _err(exc)
        return out
    out["connected"] = True
    try:
        out["accounts"] = list(ib.managedAccounts())
    except Exception:
        out["accounts"] = []

    wanted = [c for c in CONTRACTS if c[0] in symbols] if symbols else CONTRACTS
    for sym, exch, label in wanted:
        r: dict = {"label": label, "exchange": exch, "errors": []}
        print(f"\n=== {sym} ({exch}) {label} ===", flush=True)

        # ---- 1. does the contract even resolve? -------------------------------------
        front = None
        try:
            details = ib.reqContractDetails(Future(sym, exchange=exch))
            r["secdef"] = len(details)
            months = sorted({d.contract.lastTradeDateOrContractMonth for d in details})
            r["months"] = months[:6]
            if details:
                live = [d for d in details
                        if d.contract.lastTradeDateOrContractMonth >= dt.date.today().strftime("%Y%m%d")]
                front = (sorted(live, key=lambda d: d.contract.lastTradeDateOrContractMonth)[0].contract
                         if live else details[0].contract)
            print(f"  secdef {len(details)} contract(s); front {getattr(front,'lastTradeDateOrContractMonth','-')}")
        except Exception as exc:
            r["secdef"] = 0
            r["errors"].append(f"secdef: {_err(exc)}")
            print(f"  secdef FAILED: {_err(exc)}")

        # ---- 2. how far back does the data farm admit to holding? --------------------
        if front is not None:
            for what in ("TRADES", "BID_ASK"):
                try:
                    head = ib.reqHeadTimeStamp(front, whatToShow=what, useRTH=False)
                    r[f"head_{what.lower()}"] = str(head) if head else None
                    print(f"  head {what:<8}: {head}")
                except Exception as exc:
                    r[f"head_{what.lower()}"] = None
                    r["errors"].append(f"head {what}: {_err(exc)}")
                ib.sleep(0.3)

        # ---- 3. resolutions x bar types: the actual matrix ---------------------------
        grid: dict = {}
        if front is not None:
            for rlabel, bar, dur in RESOLUTIONS:
                grid[rlabel] = {}
                for what in BAR_TYPES:
                    # OPTION_IMPLIED_VOLATILITY is meaningless below daily; skip rather
                    # than record a misleading failure.
                    if what == "OPTION_IMPLIED_VOLATILITY" and rlabel != "daily":
                        grid[rlabel][what] = "skipped"
                        continue
                    try:
                        bars = ib.reqHistoricalData(
                            front, endDateTime="", durationStr=dur, barSizeSetting=bar,
                            whatToShow=what, useRTH=False, formatDate=1, timeout=30)
                        grid[rlabel][what] = len(bars)
                        if bars and what == "TRADES" and rlabel == "minute":
                            r["sample_minute"] = {"t": str(bars[-1].date), "o": bars[-1].open,
                                                  "c": bars[-1].close, "v": float(bars[-1].volume)}
                    except Exception as exc:
                        grid[rlabel][what] = 0
                        r["errors"].append(f"{rlabel}/{what}: {_err(exc)}")
                    ib.sleep(0.4)
                got = {k: v for k, v in grid[rlabel].items() if isinstance(v, int) and v}
                print(f"  {rlabel:<7}: " + (", ".join(f"{k}={v}" for k, v in got.items()) or "nothing"))
        r["grid"] = grid

        # ---- 4. open interest, and the continuous contract ---------------------------
        if front is not None:
            try:
                oi = ib.reqHistoricalData(front, endDateTime="", durationStr="1 M",
                                          barSizeSetting="1 day", whatToShow="OPTION_VOLUME",
                                          useRTH=False, formatDate=1, timeout=30)
                r["open_interest_bars"] = len(oi)
            except Exception as exc:
                r["open_interest_bars"] = 0
                r["errors"].append(f"open_interest: {_err(exc)}")
            ib.sleep(0.3)
        try:
            cf = ib.qualifyContracts(ContFuture(sym, exchange=exch))
            if cf:
                cb = ib.reqHistoricalData(cf[0], endDateTime="", durationStr="5 D",
                                          barSizeSetting="1 min", whatToShow="TRADES",
                                          useRTH=False, formatDate=1, timeout=30)
                r["contfut_bars"] = len(cb)
                r["contfut_first"] = str(cb[0].date) if cb else None
                r["contfut_last"] = str(cb[-1].date) if cb else None
                print(f"  ContFuture: {len(cb)} 1-min bars")
            else:
                r["contfut_bars"] = 0
                r["errors"].append("contfut: did not qualify")
        except Exception as exc:
            r["contfut_bars"] = 0
            r["errors"].append(f"contfut: {_err(exc)}")

        r["ib_errors"] = sorted({str(getattr(e, "errorCode", "")) for e in []})
        out["results"][sym] = r
        ib.sleep(0.5)

    ib.disconnect()
    return out


def render(out: dict) -> None:
    res = out.get("results", {})
    if not res:
        print("no results")
        return
    print("\n" + "=" * 92)
    print("FUTURES CAPABILITY MATRIX - measured on this account")
    print("=" * 92)
    hdr = f"{'sym':<5} {'exch':<6} {'secdef':>6} {'daily':>6} {'hour':>6} {'min':>6} {'30s':>6} {'quotes':>7} {'cont':>6}  earliest (TRADES)"
    print(hdr)
    print("-" * 92)
    for sym, r in res.items():
        g = r.get("grid", {})
        def cell(res_name, what="TRADES"):
            v = g.get(res_name, {}).get(what)
            return v if isinstance(v, int) else 0
        print(f"{sym:<5} {r.get('exchange',''):<6} {r.get('secdef',0):>6} "
              f"{cell('daily'):>6} {cell('hour'):>6} {cell('minute'):>6} {cell('second'):>6} "
              f"{cell('minute','BID_ASK'):>7} {r.get('contfut_bars',0):>6}  "
              f"{r.get('head_trades') or '-'}")
    print("-" * 92)
    print("counts are BARS RETURNED for the probe's duration; 0 means refused or empty")
    errs = {s: r["errors"] for s, r in res.items() if r.get("errors")}
    if errs:
        print("\nrefusals, verbatim:")
        for s, e in errs.items():
            for line in e[:4]:
                print(f"  {s:<5} {line}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=CLIENT_ID)
    ap.add_argument("--report", action="store_true", help="re-read the last run, no IB")
    args = ap.parse_args(argv)

    if args.report:
        if not REPORT.exists():
            print(f"{REPORT} does not exist; run without --report first")
            return 1
        render(json.loads(REPORT.read_text(encoding="utf-8")))
        return 0

    t0 = time.time()
    out = probe(args.symbols or [c[0] for c in CONTRACTS], args.host, args.port, args.client_id)
    out["elapsed_s"] = round(time.time() - t0, 1)
    if not out.get("connected"):
        print(f"could not connect to IB Gateway at {args.host}:{args.port}: {out.get('error')}")
        return 2
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    render(out)
    print(f"\nwritten to {REPORT.relative_to(REPO)}  ({out['elapsed_s']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
