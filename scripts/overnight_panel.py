"""One row per trade date: what the overnight session knew, and what the RTH session did.

WHY A PANEL AND NOT A BACKTEST
------------------------------
The question is whether information generated overnight predicts the regular session. That is
a question about a joint distribution, and the honest unit of observation is **one trade
date**. Not one bar. A study that samples every minute of the RTH session and calls the
overnight return a feature has one real observation dressed up as 390.

That distinction decides what can be concluded. There are at most 326 clean trade dates in
this store, so the smallest correlation separable from zero at the conventional bar is
1.96/sqrt(326) = **0.109**. Anything below that is not a finding here however small its
p-value looks, and any p-value computed on a per-minute panel is wrong by roughly the square
root of the bars per session.

THE SESSION BOUNDARIES, AND WHY THESE ONES
-------------------------------------------
CME equity-index futures run 18:00 ET to 17:00 ET the next day, with a one-hour halt. The
repository's Topstep rulebook gives a mandatory flat at 15:10 CT, which is **16:10 ET**, and
a session close at 16:00 CT = 17:00 ET.

So the tradable window for a Combine is 09:30 to 16:10 ET, and this module uses 09:30-16:00
to leave ten minutes of margin. That is deliberately wider than the 09:30-15:45 the previous
research used: measured on this store, the 15:45 fifteen-minute bucket alone carries 10.58%
of regular-session volume, the largest of the day, and the old window discarded 13.9% of RTH
volume along with the settlement flows the intraday-momentum literature is actually about.

"Overnight" is everything from the 18:00 ET open to 09:29 ET, on the CME trade date. A trade
date is assigned by shifting the clock forward six hours, so 18:00 ET Sunday belongs to
Monday, which is the exchange's own convention.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
No strategy, no signal, no position. Every column is either a fact about the overnight session
or a fact about the RTH session, and nothing joins them. The joining is the analysis, and it
belongs somewhere a reader can see the multiplicity.

Every overnight column is computable strictly before 09:30 ET. Every RTH column is strictly
after. There is no column that spans the boundary, so a leak would have to be a coding error
rather than a design choice, and `test_overnight_panel.py` checks for exactly that.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]

#: ET wall-clock boundaries. Strings compare correctly in HH:MM.
OVERNIGHT_OPEN = "18:00"
RTH_OPEN = "09:30"
RTH_LAST = "16:00"          # ten minutes inside the 16:10 ET Topstep flatten
FLATTEN_ET = "16:10"

#: A trade date is the ET clock shifted forward six hours, so the 18:00 ET open starts the
#: next date. This is the exchange convention and it is what makes "overnight" contiguous.
TRADE_DATE_SHIFT_HOURS = 6


def load_full_session(symbol: str) -> pd.DataFrame:
    """Every bar we hold, with a trade date, and only dates carrying ONE contract.

    Dropping mixed-contract dates rather than stitching is the conservative choice: a roll
    inside a trade date puts a price gap in the middle of an overnight return, and no amount
    of adjustment makes that observation trustworthy.
    """
    df = pd.read_parquet(REPO / "data" / "futures" / f"{symbol}.parquet")
    t = pd.to_datetime(df["t"], utc=True).dt.tz_convert("America/New_York")
    df = df.assign(et=t, hm=t.dt.strftime("%H:%M"),
                   tdate=(t + pd.Timedelta(hours=TRADE_DATE_SHIFT_HOURS)).dt.date)
    n_contracts = df.groupby("tdate")["contract"].nunique()
    clean = n_contracts[n_contracts == 1].index
    return df[df["tdate"].isin(clean)].sort_values("et").reset_index(drop=True)


def _seg(g: pd.DataFrame, lo: str, hi: str) -> pd.DataFrame:
    return g[(g["hm"] >= lo) & (g["hm"] < hi)]


def _overnight(g: pd.DataFrame) -> pd.DataFrame:
    """18:00 ET through 09:29 ET, which wraps midnight."""
    return g[(g["hm"] >= OVERNIGHT_OPEN) | (g["hm"] < RTH_OPEN)]


def _ret_pct(c: np.ndarray) -> float:
    return float((c[-1] / c[0] - 1.0) * 100.0) if len(c) > 1 and c[0] > 0 else np.nan


def _realised_vol_pct(c: np.ndarray, bars_per_year: float) -> float:
    if len(c) < 3:
        return np.nan
    r = np.diff(np.log(c))
    return float(np.sqrt((r ** 2).sum() * bars_per_year / len(r)) * 100.0)


def build(symbol: str) -> pd.DataFrame:
    """The panel. One row per trade date."""
    df = load_full_session(symbol)
    rows = []
    for tdate, g in df.groupby("tdate", sort=True):
        on = _overnight(g)
        rth = g[(g["hm"] >= RTH_OPEN) & (g["hm"] <= RTH_LAST)]
        if len(on) < 200 or len(rth) < 300:
            continue                                  # a truncated date is not a session
        oc = on["c"].to_numpy(dtype=float)
        oh, ol = on["h"].to_numpy(dtype=float), on["l"].to_numpy(dtype=float)
        rc = rth["c"].to_numpy(dtype=float)
        rhm = rth["hm"].to_numpy()

        on_hi, on_lo = float(oh.max()), float(ol.min())
        on_range = on_hi - on_lo
        prev_close = float(oc[0])                     # the 18:00 ET print, our reference
        rth_open = float(rc[0])

        r = {
            "tdate": tdate, "symbol": symbol,
            # ---- overnight facts, all knowable before 09:30 -----------------------------
            "on_bars": len(on),
            "on_ret_pct": _ret_pct(oc),
            "on_ret_pts": float(oc[-1] - oc[0]),
            "on_range_pts": on_range,
            "on_range_pct": on_range / prev_close * 100.0 if prev_close else np.nan,
            "on_high": on_hi, "on_low": on_lo,
            "on_vol_pct": _realised_vol_pct(oc, 252 * 1380),
            "on_volume": float(on["v"].sum()),
            # where the overnight session closed inside its own range: 1 = at the high
            "on_close_loc": ((float(oc[-1]) - on_lo) / on_range) if on_range > 0 else np.nan,
            # how much of the total path ended up as net move: 1 = a clean one-way trend
            "on_persistence": (abs(float(oc[-1] - oc[0])) / float(np.abs(np.diff(oc)).sum())
                               if len(oc) > 1 and np.abs(np.diff(oc)).sum() > 0 else np.nan),
            "on_max_excursion_pts": float(max(on_hi - oc[0], oc[0] - on_lo)),
            # ---- the boundary ------------------------------------------------------------
            "gap_pts": rth_open - float(oc[-1]),
            "gap_pct": (rth_open / float(oc[-1]) - 1.0) * 100.0 if oc[-1] else np.nan,
            "rth_open": rth_open,
            # ---- RTH outcomes, all strictly after 09:30 ----------------------------------
            "rth_bars": len(rth),
            "rth_ret_pct": _ret_pct(rc),
            "rth_ret_pts": float(rc[-1] - rc[0]),
            "rth_range_pts": float(rth["h"].max() - rth["l"].min()),
            "rth_vol_pct": _realised_vol_pct(rc, 252 * 390),
            "rth_volume": float(rth["v"].sum()),
            "rth_high": float(rth["h"].max()), "rth_low": float(rth["l"].min()),
        }
        # forward returns from the RTH open, in points
        for mins, name in ((5, "r5"), (15, "r15"), (30, "r30"), (60, "r60")):
            r[f"{name}_pts"] = float(rc[mins] - rc[0]) if len(rc) > mins else np.nan
        # named intraday blocks
        for lo, hi, name in (("10:00", "12:00", "mid"), ("12:00", "15:10", "aft"),
                             ("15:10", "16:00", "close")):
            seg = _seg(rth, lo, hi)
            sc = seg["c"].to_numpy(dtype=float)
            r[f"{name}_pts"] = float(sc[-1] - sc[0]) if len(sc) > 1 else np.nan
        # did RTH break the overnight extremes, and when
        broke_hi = np.argmax(rth["h"].to_numpy(dtype=float) > on_hi) \
            if (rth["h"].to_numpy(dtype=float) > on_hi).any() else -1
        broke_lo = np.argmax(rth["l"].to_numpy(dtype=float) < on_lo) \
            if (rth["l"].to_numpy(dtype=float) < on_lo).any() else -1
        r["broke_on_high_bar"] = int(broke_hi)
        r["broke_on_low_bar"] = int(broke_lo)
        r["opened_inside_on_range"] = bool(on_lo <= rth_open <= on_hi)
        r["first_hm"] = str(rhm[0]); r["last_hm"] = str(rhm[-1])
        rows.append(r)
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["ES", "NQ", "MES", "MNQ"])
    ap.add_argument("--out", type=Path,
                    default=REPO / "research" / "overnight_panel.parquet")
    args = ap.parse_args()
    frames = []
    for s in args.symbols:
        p = build(s)
        print(f"{s}: {len(p)} clean trade dates  "
              f"{p['tdate'].min()} .. {p['tdate'].max()}")
        frames.append(p)
    panel = pd.concat(frames, ignore_index=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(args.out, index=False)
    print(f"\n{len(panel)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
