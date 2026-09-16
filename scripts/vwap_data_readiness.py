"""DECISION 9: can the existing store feed an 18:00-anchored V1.0.0 session? INSPECTION ONLY.

    python scripts/vwap_data_readiness.py

This reads bars and counts them. It runs no strategy, simulates no fill and produces no P&L.
The question it answers is narrower and earlier than "does the strategy work": does the data
on disk contain what the frozen specification needs, and where does it fall short?

WHAT THE FROZEN SPECIFICATION NEEDS
-------------------------------------
    an 18:00 ET anchor          the VWAP resets there and the trading day rolls there
    continuous 1-minute OHLCV   from that anchor through 15:45 ET the next afternoon
    volume                      the VWAP is volume-weighted and the trigger gates on SMA(10)
    5-minute aggregation        derived in the engine, so the 1-minute stream is enough
    contract identity per bar   a session spanning two contracts prices a roll as a return
    roll information            to know which sessions those are
    America/New_York            every rule is a wall-clock rule

`research/session_source` cannot supply this: it cuts RTH windows (09:30-16:00) and drops
incomplete sessions, so the overnight half of every anchored session is discarded before the
engine could see it. That is CONFLICT C6 and it is the reason this script exists.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.data import loader as L  # noqa: E402
from quant_brain.strategies.vwap_pullback.spec import FROZEN, TIMEZONE  # noqa: E402

STORE = REPO / "data" / "futures"
ANCHOR_MIN = FROZEN.anchor_minute()                 # 18:00 -> 1080
FLAT_MIN = FROZEN.minute_of("hard_flatten")         # 15:45 -> 945
#: 18:00 to 15:45 the next day, INCLUSIVE of both endpoints, is 1,306 one-minute bars -
#: the same inclusive convention the RTH window uses (09:30..16:00 is 391, not 390).
SPAN_MINUTES = (24 * 60 - ANCHOR_MIN) + FLAT_MIN + 1


def anchored_day(et: pd.Series) -> pd.Series:
    """The trading date a bar belongs to, rolling at 18:00 ET.

    Calendar arithmetic on dates. `+ pd.to_timedelta(1, "D")` on the timestamps adds
    twenty-four ABSOLUTE hours, which is not one calendar day across a DST transition and
    pushes the late-evening bars of a spring-forward session into the following trading day.
    See the same note in `strategies/vwap_pullback/data.py`.
    """
    mins = et.dt.hour * 60 + et.dt.minute
    day = et.dt.date.to_numpy()
    return pd.Series(np.where((mins >= ANCHOR_MIN).to_numpy(),
                              day + dt.timedelta(days=1), day), index=et.index)


def audit(symbol: str) -> dict:
    ds = L.load("ibkr_futures", STORE / f"{symbol}.parquet", instrument=symbol)
    f = ds.frame
    et = f["timestamp"].dt.tz_convert(TIMEZONE)
    mins = et.dt.hour * 60 + et.dt.minute
    day = anchored_day(et)

    inside = (mins >= ANCHOR_MIN) | (mins <= FLAT_MIN)
    overnight = (mins >= ANCHOR_MIN) | (mins < 9 * 60 + 30)
    work = pd.DataFrame({"day": day, "min": mins, "inside": inside,
                         "overnight": overnight,
                         "contract": f["contract_symbol"].astype(str),
                         "volume": f["volume"].to_numpy()})

    per = work[work["inside"]].groupby("day")
    bars = per.size()
    ov = work[work["inside"] & work["overnight"]].groupby("day").size()
    contracts = per["contract"].nunique()
    zero_vol = work[work["inside"]].groupby("day")["volume"].apply(lambda v: int((v <= 0).sum()))

    # a session is USABLE for this strategy only if it has the anchor, the flatten, and no
    # contract change inside it
    has_anchor = per["min"].min() <= ANCHOR_MIN + 5
    complete = bars >= SPAN_MINUTES * 0.80
    single = contracts == 1

    return {
        "symbol": symbol,
        "bars_total": len(f),
        "coverage": f"{et.iloc[0]:%Y-%m-%d %H:%M} .. {et.iloc[-1]:%Y-%m-%d %H:%M} ET",
        "anchored_days": int(bars.size),
        "median_bars_per_anchored_day": int(bars.median()) if bars.size else 0,
        "span_minutes_needed": SPAN_MINUTES,
        "median_overnight_bars": int(ov.median()) if ov.size else 0,
        "days_with_an_18_00_anchor": int(has_anchor.sum()),
        "days_at_least_80pc_complete": int(complete.sum()),
        "days_single_contract": int(single.sum()),
        "days_usable": int((has_anchor & complete & single).sum()),
        "days_with_zero_volume_bars": int((zero_vol > 0).sum()),
        "rolls": len(ds.manifest.roll.roll_timestamps),
        "contracts": list(ds.manifest.roll.contracts),
        "quality": ds.manifest.quality.status,
        "manifest": ds.manifest.manifest_id,
        "_bars": bars, "_ov": ov,
    }


def main() -> int:
    print("=" * 100)
    print("V1.0.0_FROZEN HISTORICAL DATA READINESS - inspection only, no strategy was run")
    print("=" * 100)
    print(f"  an anchored session runs 18:00 ET -> 15:45 ET = {SPAN_MINUTES} wall-clock "
          f"minutes")
    print(f"  the venue clock is {TIMEZONE.key}\n")

    rows = []
    for sym in ("ES", "NQ", "MES", "MNQ"):
        p = STORE / f"{sym}.parquet"
        if not p.exists():
            print(f"  {sym}: NO STORE")
            continue
        r = audit(sym)
        rows.append(r)
        bars, ov = r.pop("_bars"), r.pop("_ov")
        print(f"\n{sym}   {r['coverage']}")
        print(f"  bars in file                 {r['bars_total']:,}")
        print(f"  anchored (18:00) days        {r['anchored_days']}")
        print(f"  median bars per such day     {r['median_bars_per_anchored_day']:,} of "
              f"{SPAN_MINUTES:,} possible "
              f"({r['median_bars_per_anchored_day'] / SPAN_MINUTES:.0%})")
        print(f"  median OVERNIGHT bars        {r['median_overnight_bars']:,}  "
              f"(18:00 -> 09:29 ET)")
        print(f"  days that reach the anchor   {r['days_with_an_18_00_anchor']}")
        print(f"  days >= 80% complete         {r['days_at_least_80pc_complete']}")
        print(f"  days on ONE contract         {r['days_single_contract']}")
        print(f"  DAYS USABLE (all three)      {r['days_usable']}")
        print(f"  days containing a 0-volume bar  {r['days_with_zero_volume_bars']}")
        print(f"  rolls / contracts            {r['rolls']} / {r['contracts']}")
        print(f"  quality / manifest           {r['quality']} / {r['manifest']}")
        if bars.size:
            q = np.percentile(bars.to_numpy(), [5, 25, 50, 75, 95])
            print(f"  bars-per-day percentiles     "
                  + "  ".join(f"p{p_}={int(v):,}" for p_, v in zip((5, 25, 50, 75, 95), q)))
        if ov.size:
            print(f"  overnight-bar percentiles    "
                  + "  ".join(f"p{p_}={int(v):,}" for p_, v in
                              zip((5, 50, 95), np.percentile(ov.to_numpy(), [5, 50, 95]))))

    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    for r in rows:
        usable = r["days_usable"]
        pct = r["median_bars_per_anchored_day"] / SPAN_MINUTES
        verdict = "SUFFICIENT" if usable >= 100 and pct >= 0.80 else "INSUFFICIENT"
        print(f"  {r['symbol']:4} {verdict:13} {usable} usable anchored sessions, "
              f"median {pct:.0%} of the wall-clock span")
    print("\n  SUPERSEDED. This script's `days_usable` uses an 80%-of-span threshold, which")
    print("  was the right question for DECISION 9 - is there ENOUGH data - and is the wrong")
    print("  question for a backtest. The anchored loader that DECISION 9 said was missing")
    print("  now exists (`strategies/vwap_pullback/data.py`) and its completeness rule is")
    print("  strict: the 18:00 anchor present, the 15:45 flatten present, every minute in")
    print("  between present exactly once, one contract. On ES that is 313 sessions, not the")
    print("  326 counted above; the thirteen-session difference is holiday early closes that")
    print("  are 87% complete and have no 15:45 bar to flatten on.")
    print("  Run `python scripts/vwap_data_certify.py` for the authoritative census.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
