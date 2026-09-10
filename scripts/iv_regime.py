#!/usr/bin/env python
"""O-1: build the SPY options-implied regime store from Theta Data.

    python scripts/iv_regime.py --start 2015-10-01 --end 2026-09-09 --workers 8
    python scripts/iv_regime.py --rebuild          # re-aggregate from the raw cache only

Why this exists
---------------
A-10 measured the one mechanism this sleeve has that survives 2,686 sessions: daily P&L
correlates +0.202 with the universe's mean daily range at t = +10.70, positive in all three
regimes, while the *level* is negative everywhere. So the open question is not "how big" but
"when" - is there a causal, known-before-the-open regime signal that separates the range days the
book earns on from the ones it pays on? A-9 refused the opening range (ORB's stop is the range
midpoint, so width scales win and loss together). Options-implied volatility is the untried
candidate and, unlike anything the bars carry, it is a *forecast* rather than a realization.

What it writes
--------------
`data/options/iv_regime.parquet`, one row per trading day, every field an **end-of-day** value:

    day            trading day the row was observed on (EOD, so a session's gate uses day-1)
    u_price        SPY underlying price on the EOD stamp
    dte_front      calendar days from `day` to the front expiration (the "1w" bucket)
    iv_atm_1w      ATM implied vol of the front weekly, calls and puts averaged, strike-interpolated
    iv_call25_1w   front-weekly call IV interpolated at delta +0.25
    iv_put25_1w    front-weekly put IV interpolated at delta -0.25
    skew25_1w      iv_put25_1w - iv_call25_1w (positive = puts bid, the usual sign)
    dte_back       calendar days to the back expiration (the "1m" bucket, dte closest to 30)
    iv_atm_1m      ATM implied vol of the back expiration
    term_ratio     iv_atm_1w / iv_atm_1m (> 1 = inverted / stressed term structure)

Method and cost
---------------
Theta's EOD greeks endpoint is per-expiration and serves a date range, so the cheap loop is over
expirations, not days: for every Friday expiration in the window one request covers
[E - 45d, E - 2d], which is every day on which that expiration is either the front weekly or the
~1-month back. Each request is ~25s and ~4-9k rows, so the full 2015-2026 build is ~570 requests;
raw responses are cached per expiration under `data/options/raw/` (only the columns used), which
makes the build resumable and `--rebuild` free.

Causality: every field is stamped at the close of `day`, so a strategy trading session `d` may
only read the row for the last trading day **strictly before** `d`. `load_gate()` enforces that by
shifting, and returns the feature together with its own trailing median.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import theta_data as theta  # noqa: E402

OUT_DIR = REPO / "data" / "options"
RAW_DIR = OUT_DIR / "raw"
STORE = OUT_DIR / "iv_regime.parquet"

KEEP = ["strike", "right", "timestamp", "bid", "ask", "delta", "implied_vol", "underlying_price"]
#: an expiration is fetched over [E - BACK_DAYS, E - MIN_DTE]; that covers its life as the front
#: weekly (dte 2..10) and as the ~1-month back (dte 20..45)
BACK_DAYS, MIN_DTE = 46, 2
FRONT_DTE = (2, 10)
BACK_DTE = (20, 45)


# --------------------------------------------------------------------------------- fetch
def fridays(start: dt.date, end: dt.date, all_exps: list[str]) -> list[str]:
    """Every listed Friday expiration whose fetch window overlaps [start, end].

    Fridays only: they are the one cadence listed continuously since 2012 (SPY added Mon/Wed
    weeklies in 2016-2022 and dailies later), and the monthly third Friday is inside the set, so
    the back bucket is always available even in the years when weeklies were listed only ~6 weeks
    out.
    """
    out = []
    for e in all_exps:
        d = dt.date.fromisoformat(e)
        if d.weekday() != 4:
            continue
        if d - dt.timedelta(days=BACK_DAYS) > end or d < start:
            continue
        out.append(e)
    return out


def is_monthly(e: dt.date) -> bool:
    """Third Friday of the month - the one expiration listed months ahead in every year."""
    return e.weekday() == 4 and 15 <= e.day <= 21


def fetch_one(exp: str, force: bool = False) -> Path | None:
    """Cache the EOD greek rows of one expiration over the window it is actually used in.

    Cost control: a plain weekly is only ever the *front* bucket, so it is fetched over
    [E - 11d, E - 2d]; only the monthly third Friday is also the ~1-month back bucket and needs
    [E - 46d, E - 2d]. That is ~3x fewer rows than fetching every Friday over the full window,
    which matters because the response is ~1s per trading day of chain.

    Theta answers 403 for dates that need a PROFESSIONAL subscription (before 2016 on this
    account) and 472 for expirations it holds no greeks for (2016 on this account); both are
    skipped rather than raised, so a window that straddles the horizon still builds.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    e = dt.date.fromisoformat(exp)
    full = RAW_DIR / f"SPY_{exp}.parquet"
    wide = is_monthly(e)
    path = full if wide else RAW_DIR / f"SPY_{exp}_front.parquet"
    if (path.exists() or full.exists()) and not force:
        return path if path.exists() else full
    lo = e - dt.timedelta(days=BACK_DAYS if wide else FRONT_DTE[1] + 1)
    # An expiration that has not happened yet is still useful as the back bucket, but Theta
    # answers 400 for a window ending in the future, so the end is clamped to yesterday.
    hi = min(e - dt.timedelta(days=MIN_DTE), dt.date.today() - dt.timedelta(days=1))
    if hi < lo:
        return None
    for attempt in range(3):
        try:
            df = theta.eod_greeks("SPY", exp, "*", "both", start_date=str(lo), end_date=str(hi))
            break
        except urllib.error.HTTPError as ex:  # 403 out of plan, 472 no data
            print(f"  {exp}: HTTP {ex.code}", flush=True)
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as ex:  # terminal is queueing
            if attempt == 2:
                print(f"  {exp}: {type(ex).__name__}, giving up", flush=True)
                return None
            time.sleep(5 * (attempt + 1))
    if df.empty:
        return None
    df = df[[c for c in KEEP if c in df.columns]].copy()
    df["day"] = pd.to_datetime(df["timestamp"]).dt.date
    df.drop(columns=["timestamp"]).to_parquet(path, index=False)
    return path


# --------------------------------------------------------------------------------- aggregate
def _interp(x: np.ndarray, y: np.ndarray, at: float) -> float:
    """Linear interpolation of y(x) at `at`, on x sorted ascending, NaN outside the range."""
    if len(x) < 2 or at < x[0] or at > x[-1]:
        return float("nan")
    return float(np.interp(at, x, y))


def _slice_features(g: pd.DataFrame) -> dict:
    """ATM and 25-delta implied vols for one (day, expiration) chain slice."""
    g = g[(g["implied_vol"] > 0.01) & (g["implied_vol"] < 3.0) & (g["bid"] > 0)]
    if g.empty:
        return {}
    u = float(g["underlying_price"].iloc[0])
    if not np.isfinite(u) or u <= 0:
        return {}
    out = {"u_price": u}
    atm = []
    for right, tag, target in (("CALL", "call25", 0.25), ("PUT", "put25", -0.25)):
        s = g[g["right"] == right].sort_values("strike")
        if len(s) < 2:
            continue
        # ATM: IV interpolated across strike at the underlying price
        v = _interp(s["strike"].values, s["implied_vol"].values, u)
        if np.isfinite(v):
            atm.append(v)
        # 25-delta: IV interpolated across delta. Deltas are monotone in strike, so sort by delta.
        d = s.dropna(subset=["delta"]).sort_values("delta")
        d = d[(d["delta"].abs() > 0.01) & (d["delta"].abs() < 0.99)]
        if len(d) >= 2:
            iv = _interp(d["delta"].values, d["implied_vol"].values, target)
            if np.isfinite(iv):
                out[f"iv_{tag}"] = iv
    if atm:
        out["iv_atm"] = float(np.mean(atm))
    return out


def aggregate(days_lo: dt.date, days_hi: dt.date) -> pd.DataFrame:
    """Turn the raw per-expiration cache into one row per trading day."""
    rows = []
    for path in sorted(RAW_DIR.glob("SPY_*.parquet")):
        exp = dt.date.fromisoformat(path.stem.split("_")[1])
        if (RAW_DIR / f"SPY_{exp}.parquet").exists() and path.name.endswith("_front.parquet"):
            continue  # the full window supersedes a narrow one for the same expiration
        df = pd.read_parquet(path)
        if df.empty:
            continue
        for day, g in df.groupby("day"):
            if not (days_lo <= day <= days_hi):
                continue
            dte = (exp - day).days
            if not (FRONT_DTE[0] <= dte <= BACK_DTE[1]):
                continue
            f = _slice_features(g)
            if "iv_atm" not in f:
                continue
            rows.append({"day": day, "exp": exp, "dte": dte, **f})
    if not rows:
        return pd.DataFrame()
    chain = pd.DataFrame(rows)

    out = []
    for day, g in chain.groupby("day"):
        front = g[(g["dte"] >= FRONT_DTE[0]) & (g["dte"] <= FRONT_DTE[1])].nsmallest(1, "dte")
        back = g[(g["dte"] >= BACK_DTE[0]) & (g["dte"] <= BACK_DTE[1])].copy()
        if front.empty:
            continue
        f = front.iloc[0]
        row = {"day": day, "u_price": f["u_price"], "dte_front": int(f["dte"]),
               "iv_atm_1w": f["iv_atm"], "iv_call25_1w": f.get("iv_call25", np.nan),
               "iv_put25_1w": f.get("iv_put25", np.nan)}
        row["skew25_1w"] = row["iv_put25_1w"] - row["iv_call25_1w"]
        if not back.empty:
            b = back.iloc[(back["dte"] - 30).abs().argsort().iloc[0]]
            row.update({"dte_back": int(b["dte"]), "iv_atm_1m": b["iv_atm"],
                        "term_ratio": f["iv_atm"] / b["iv_atm"] if b["iv_atm"] else np.nan})
        else:
            row.update({"dte_back": np.nan, "iv_atm_1m": np.nan, "term_ratio": np.nan})
        out.append(row)
    return pd.DataFrame(out).sort_values("day").reset_index(drop=True)


# --------------------------------------------------------------------------------- consumer API
def load_gate(feature: str = "iv_atm_1w", lookback: int = 60) -> pd.DataFrame:
    """The store shifted one trading day, with its own trailing median. Strictly causal.

    Returns a frame indexed by the trading day the feature may be *used* on, with columns
    `value` (the previous trading day's EOD reading) and `median` (the trailing `lookback`-day
    median of readings up to and including that same close, so the threshold is causal too).
    """
    df = pd.read_parquet(STORE).sort_values("day").reset_index(drop=True)
    v = df[feature].astype(float)
    med = v.rolling(lookback, min_periods=max(20, lookback // 3)).median()
    out = pd.DataFrame({"day": df["day"], "value": v.values, "median": med.values})
    # shift by one row: the row observed at the close of day i is usable on day i+1
    out["day"] = out["day"].shift(-1)
    return out.dropna(subset=["day"]).set_index("day")


# --------------------------------------------------------------------------------- cli
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2015-10-01")
    ap.add_argument("--end", default=str(dt.date.today()))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rebuild", action="store_true", help="aggregate the raw cache, fetch nothing")
    ap.add_argument("--force", action="store_true", help="refetch expirations already cached")
    args = ap.parse_args()
    lo, hi = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.rebuild:
        if not theta.alive() and not theta.start_terminal():
            sys.exit("Theta Terminal is not running and did not come up")
        exps = fridays(lo, hi, theta.expirations("SPY"))
        todo = [e for e in exps if args.force or not
                ((RAW_DIR / f"SPY_{e}.parquet").exists() or (RAW_DIR / f"SPY_{e}_front.parquet").exists())]
        print(f"{len(exps)} Friday expirations in window, {len(todo)} to fetch, {args.workers} workers")
        done = 0
        with ThreadPoolExecutor(args.workers) as ex:
            for _ in ex.map(lambda e: fetch_one(e, args.force), todo):
                done += 1
                if done % 20 == 0:
                    print(f"  {done}/{len(todo)}", flush=True)

    df = aggregate(lo, hi)
    if df.empty:
        sys.exit("no rows aggregated")
    df.to_parquet(STORE, index=False)
    print(f"\nwrote {STORE}  {len(df)} days  {df['day'].min()}..{df['day'].max()}")
    with pd.option_context("display.width", 200):
        print(df.describe().T[["count", "mean", "std", "min", "50%", "max"]].round(4).to_string())
        print(df.tail(3).to_string(index=False))
    gaps = df["day"].diff().dt.days if np.issubdtype(df["day"].dtype, np.datetime64) else None
    if gaps is not None:
        print(f"largest gap between rows: {int(gaps.max())} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
