"""O-2 confirmation: does the one positive cell survive the assumption it rests on?

The `--grid` verdict is negative and the `--stress` verdict flips only when the position is
allowed to *expire* instead of being bought back. That single modelling choice is worth more
than every parameter in the study, so this script attacks it four ways before the journal
believes it:

  1. entry-time shelf   - is 14:00 a shelf or a spike?
  2. pin risk           - the expire branch assumes a close that is OTM at the last quote is a
                          free expiry. SPY settles on the official 16:00 print and is
                          exercisable against until 17:30 ET, so require a buffer and see what
                          survives.
  3. year by year       - is the pooled t carried by one year?
  4. the mandate        - what does a book actually earn, and what does it lose on its worst day?

    python scripts/_o2_confirm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import odte_data  # noqa: E402
import sweep_o2 as o2  # noqa: E402

BEST = dict(structure="put", target=0.25, width_pct=0.015, exit="15:55", fee=0.75, expire_otm=True)


def stat(df: pd.DataFrame, col: str = "ror") -> tuple[float, float]:
    r = df[col].to_numpy()
    if len(r) < 2 or r.std(ddof=1) == 0:
        return float(100 * r.mean()), float("nan")
    return float(100 * r.mean()), float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r))))


def regime_row(df: pd.DataFrame) -> dict:
    rec = {}
    for nm, s, e in o2.REGIMES:
        sub = df[(df.date >= s) & (df.date <= e)]
        if sub.empty:
            continue
        m, t = stat(sub)
        rec[nm], rec[f"t {nm}"] = m, t
    m, t = stat(df)
    rec["all%"], rec["t all"] = m, t
    rec["pass"] = sum(1 for nm, *_ in o2.REGIMES
                      if rec.get(nm, -1) > 0 and rec.get(f"t {nm}", 0) > 2)
    return rec


def main() -> int:
    print("=" * 104)
    print("1 - ENTRY TIME. The cell was found at 14:00. A real effect is a shelf, not a spike.")
    times = ["09:35", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
             "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"]
    cfgs = [o2.Cfg(**BEST, entry=t) for t in times]
    frames = o2.run_cells(cfgs, "SPY", progress=900)
    rows = []
    for t, df in zip(times, frames):
        if df.empty:
            continue
        rows.append(dict(entry=t, n=len(df), **regime_row(df),
                         win=100 * (df.ror > 0).mean(), expired=100 * df.expired.mean(),
                         worst=100 * df.ror.min(), cr_w=(df.credit / df.width).mean()))
    print(o2.fmt(pd.DataFrame(rows)))

    print()
    print("=" * 104)
    print("2 - PIN RISK. 'expire OTM' books a zero exit whenever the last quote is past the short")
    print("strike. Require the close to clear the strike by a buffer, and pay the quoted spread")
    print("otherwise. The buffer is a fraction of spot; SPY's 0DTE short strike sits ~0.5% away.")
    bufs = [0.0, 0.0005, 0.001, 0.002, 0.003, 0.005]
    cfgs = [o2.Cfg(**BEST, entry="14:00", pin_buffer=b) for b in bufs]
    frames = o2.run_cells(cfgs, "SPY", progress=900)
    rows = []
    for b, df in zip(bufs, frames):
        if df.empty:
            continue
        rows.append(dict(buffer=f"{b:.2%}", n=len(df), **regime_row(df),
                         expired=100 * df.expired.mean()))
    print(o2.fmt(pd.DataFrame(rows)))
    base = frames[0]
    near = base[base.pin < 0.002]
    print(f"\nsessions closing within 0.2% of the short strike: {len(near)} of {len(base)} "
          f"({100 * len(near) / len(base):.1f}%); of those, {int(near.expired.sum())} are booked "
          f"as a free expiry.")
    print(f"pin distance percentiles (fraction of spot): "
          + ", ".join(f"p{p}={np.nanpercentile(base.pin, p):.4f}" for p in (1, 5, 10, 25, 50)))

    print()
    print("=" * 104)
    print("3 - YEAR BY YEAR, and the same cell with the exit it was refused on.")
    for label, cfg in (("expire OTM", o2.Cfg(**BEST, entry="14:00")),
                       ("close at quote", o2.Cfg(**{**BEST, "expire_otm": False}, entry="14:00"))):
        df = o2.run_study(cfg, "SPY")
        df["year"] = df.date.str[:4]
        yr = df.groupby("year").apply(
            lambda s: pd.Series({"n": len(s), "net%": 100 * s.ror.mean(),
                                 "t": stat(s)[1], "win%": 100 * (s.ror > 0).mean(),
                                 "worst%": 100 * s.ror.min()}), include_groups=False)
        print(f"\n{label}:")
        print(o2.fmt(yr.reset_index()))
        m, t = stat(df)
        print(f"  pooled {m:+.3f}% of risk/session, t = {t:+.2f}, "
              f"positive years {int((yr['net%'] > 0).sum())}/{len(yr)}")

    print()
    print("=" * 104)
    print("4 - THE MANDATE. What a book earns, and what its worst session costs, at a fixed")
    print("fraction of equity at risk per session. Defined risk caps that fraction at 1.0.")
    df = o2.run_study(o2.Cfg(**BEST, entry="14:00"), "SPY")
    m, t = stat(df)
    rows = []
    for rf in (0.10, 0.25, 0.50, 1.00):
        r = df.ror.to_numpy() * rf
        rows.append({"risk_frac": rf, "mean %/day": 100 * r.mean(),
                     "sd %/day": 100 * r.std(ddof=1), "worst day %": 100 * r.min(),
                     "p1 day %": 100 * np.percentile(r, 1),
                     "simple %/yr (252d)": 100 * r.mean() * 252,
                     "sessions/yr": len(df) / 10.7})
    print(o2.fmt(pd.DataFrame(rows)))
    print(f"\nsessions needed for 3%/day at risk_frac 1.0: the cell earns {m:.3f}% of risk, so a")
    print(f"3%/day book needs {3.0 / m:.1f}x equity at risk every session - which a defined-risk")
    print("position cannot do, because its risk is posted in full as margin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
