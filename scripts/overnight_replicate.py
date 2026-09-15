"""Section 1 and 2: does the overnight/RTH split survive an independent look, and is it alpha?

TWO CLAIMS ARE BEING CHECKED, AND THEY ARE NOT THE SAME CLAIM
--------------------------------------------------------------
The earlier report on this repository said two things. First, that essentially all of the
return in the futures store accrued overnight. Second, that the regular session drifted
NEGATIVE on all four instruments. The second is the one that would matter, because a
reliably negative RTH drift is a tradable short and a reliably flat one is not.

Both were measured on a 09:30-15:45 window. Topstep's mandatory flat is 15:10 CT = 16:10 ET,
so 15:45-16:00 was eligible trading time that the measurement threw away - and it is the
heaviest quarter-hour of the session. This module remeasures on the full eligible window and
then tries to break the result with data the original never touched.

THE INDEPENDENT SAMPLE
----------------------
SPY and QQQ minute bars, 2016-2026, 2,687 trade dates from a different vendor (Alpaca), a
different venue (NYSE Arca / Nasdaq), and a different instrument class (ETF, not futures).
These are RTH-only bars, which sounds like a limitation and is not: the overnight return IS
the close-to-open gap, so an RTH-only store measures the overnight session exactly, and it
does so over 8.6x more history than the futures store holds.

If the overnight/RTH asymmetry is real it must appear here too. If it appears only in 312
days of 2025-2026 futures data, it was a fact about 2025-2026.

BETA OR ALPHA
-------------
Overnight drift is one of the most heavily documented anomalies in equities (Cliff, Cooper &
Gulen; Lou, Polk & Skouras). Documented does not mean tradable, and for this project it does
not even mean interesting, because the null it has to beat is not zero - it is **buy and
hold**. A strategy that is long overnight and flat by day earns a large share of the index's
total return while taking on the index's risk. That is beta with a schedule, not alpha.

So the test applied here is a ratio, not a t-statistic: does holding only the overnight
session produce a better return PER UNIT OF RISK than holding the whole day? If it does not,
there is nothing here that a long ES position does not already give you for free.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
ANN = 252


def _stats(r: np.ndarray, label: str = "") -> dict:
    """Per-session returns in percent -> the summary that decides things."""
    r = r[~np.isnan(r)]
    n = len(r)
    mu, sd = float(np.mean(r)), float(np.std(r, ddof=1))
    t = mu / (sd / np.sqrt(n)) if sd > 0 else np.nan
    return {"leg": label, "n": n, "mean_pct": mu, "sd_pct": sd, "t": t,
            "total_pct": float(np.sum(r)), "hit": float(np.mean(r > 0)),
            "sharpe_ann": (mu / sd * np.sqrt(ANN)) if sd > 0 else np.nan}


def etf_panel(sym: str) -> pd.DataFrame:
    """Close-to-open and open-to-close, per trade date, 2016-2026."""
    d = pd.read_parquet(REPO / "data" / "minute_alpaca" / f"{sym}.parquet")
    t = d.index
    if getattr(t, "tz", None) is None:
        t = t.tz_localize("UTC")
    t = t.tz_convert("America/New_York")
    d = d.assign(_d=t.date).sort_index()
    day = d.groupby("_d").agg(open=("o", "first"), close=("c", "last"),
                              high=("h", "max"), low=("l", "min"),
                              vol=("v", "sum"), bars=("c", "size"))
    day = day[day["bars"] >= 380]                # drop half days and truncated sessions
    prev = day["close"].shift(1)
    out = pd.DataFrame({
        "tdate": day.index,
        "symbol": sym,
        "on_ret_pct": (day["open"] / prev - 1.0) * 100.0,     # close -> open, the overnight
        "rth_ret_pct": (day["close"] / day["open"] - 1.0) * 100.0,
        "day_ret_pct": (day["close"] / prev - 1.0) * 100.0,   # close -> close, buy and hold
    }).dropna().reset_index(drop=True)
    # A close-to-open jump beyond 10% is a split or a bad print, not an overnight session.
    return out[out["on_ret_pct"].abs() < 10.0].reset_index(drop=True)


def main() -> int:
    from overnight_panel import load_full_session

    fut = pd.read_parquet(REPO / "research" / "overnight_panel.parquet")

    print("=" * 88)
    print("1. THE FUTURES STORE, REMEASURED ON THE FULL ELIGIBLE WINDOW (09:30-16:00 ET)")
    print("=" * 88)
    print(f"{'sym':5} {'leg':14} {'n':>5} {'mean%':>9} {'sd%':>7} {'t':>7} "
          f"{'total%':>9} {'hit':>6} {'Sharpe':>7}")
    for sym, g in fut.groupby("symbol"):
        for col, leg in (("on_ret_pct", "overnight"), ("gap_pct", "gap"),
                         ("rth_ret_pct", "RTH 0930-1600")):
            s = _stats(g[col].to_numpy(), leg)
            print(f"{sym:5} {s['leg']:14} {s['n']:5d} {s['mean_pct']:9.4f} {s['sd_pct']:7.3f} "
                  f"{s['t']:7.2f} {s['total_pct']:9.2f} {s['hit']:6.3f} {s['sharpe_ann']:7.2f}")
        print()

    print("=" * 88)
    print("2. THE OLD 09:30-15:45 WINDOW, FOR COMPARISON  (was RTH really negative?)")
    print("=" * 88)
    print(f"{'sym':5} {'window':16} {'n':>5} {'mean%':>9} {'t':>7} {'total%':>9}")
    for sym in ["ES", "NQ", "MES", "MNQ"]:
        df = load_full_session(sym)
        for last, name in (("15:45", "09:30-15:45"), ("16:00", "09:30-16:00")):
            rets = []
            for _, g in df.groupby("tdate"):
                r = g[(g["hm"] >= "09:30") & (g["hm"] <= last)]["c"].to_numpy(dtype=float)
                if len(r) >= 300:
                    rets.append((r[-1] / r[0] - 1.0) * 100.0)
            s = _stats(np.array(rets), name)
            print(f"{sym:5} {name:16} {s['n']:5d} {s['mean_pct']:9.4f} {s['t']:7.2f} "
                  f"{s['total_pct']:9.2f}")
        print()

    print("=" * 88)
    print("3. INDEPENDENT REPLICATION: SPY AND QQQ, 2016-2026, DIFFERENT VENDOR AND VENUE")
    print("=" * 88)
    etfs = pd.concat([etf_panel("SPY"), etf_panel("QQQ")], ignore_index=True)
    etfs.to_parquet(REPO / "research" / "etf_overnight_panel.parquet", index=False)
    print(f"{'sym':5} {'leg':14} {'n':>5} {'mean%':>9} {'sd%':>7} {'t':>7} "
          f"{'total%':>9} {'hit':>6} {'Sharpe':>7}")
    for sym, g in etfs.groupby("symbol"):
        print(f"      span {g.tdate.min()} .. {g.tdate.max()}")
        for col, leg in (("on_ret_pct", "overnight"), ("rth_ret_pct", "RTH"),
                         ("day_ret_pct", "buy and hold")):
            s = _stats(g[col].to_numpy(), leg)
            print(f"{sym:5} {s['leg']:14} {s['n']:5d} {s['mean_pct']:9.4f} {s['sd_pct']:7.3f} "
                  f"{s['t']:7.2f} {s['total_pct']:9.2f} {s['hit']:6.3f} {s['sharpe_ann']:7.2f}")
        print()

    print("=" * 88)
    print("4. BETA OR ALPHA: overnight-only against the buy-and-hold null")
    print("=" * 88)
    print("The question is not whether overnight beats zero. It is whether being long only")
    print("overnight beats being long all the time, per unit of risk.\n")
    print(f"{'sym':5} {'share of B&H':>13} {'Sharpe ON':>10} {'Sharpe B&H':>11} "
          f"{'ratio':>7} {'corr(ON,B&H)':>13}")
    for sym, g in etfs.groupby("symbol"):
        on, bh = g["on_ret_pct"].to_numpy(), g["day_ret_pct"].to_numpy()
        so, sb = _stats(on), _stats(bh)
        share = so["total_pct"] / sb["total_pct"] if sb["total_pct"] else np.nan
        print(f"{sym:5} {share:12.1%} {so['sharpe_ann']:10.2f} {sb['sharpe_ann']:11.2f} "
              f"{so['sharpe_ann'] / sb['sharpe_ann']:7.2f} {np.corrcoef(on, bh)[0, 1]:13.3f}")
    for sym, g in fut.groupby("symbol"):
        on = g["on_ret_pct"].to_numpy()
        bh = (g["on_ret_pct"] + g["gap_pct"] + g["rth_ret_pct"]).to_numpy()
        so, sb = _stats(on), _stats(bh)
        share = so["total_pct"] / sb["total_pct"] if sb["total_pct"] else np.nan
        print(f"{sym:5} {share:12.1%} {so['sharpe_ann']:10.2f} {sb['sharpe_ann']:11.2f} "
              f"{so['sharpe_ann'] / sb['sharpe_ann']:7.2f} {np.corrcoef(on, bh)[0, 1]:13.3f}")

    print("\n" + "=" * 88)
    print("5. IS THE OVERNIGHT DRIFT STABLE, OR A FACT ABOUT ONE PERIOD?")
    print("=" * 88)
    print(f"{'sym':5} {'year':6} {'n':>5} {'ON mean%':>10} {'ON t':>7} {'RTH mean%':>10} "
          f"{'RTH t':>7}")
    for sym, g in etfs.groupby("symbol"):
        g = g.assign(yr=pd.to_datetime(g["tdate"]).dt.year)
        for yr, gy in g.groupby("yr"):
            a = _stats(gy["on_ret_pct"].to_numpy())
            b = _stats(gy["rth_ret_pct"].to_numpy())
            print(f"{sym:5} {yr:6d} {a['n']:5d} {a['mean_pct']:10.4f} {a['t']:7.2f} "
                  f"{b['mean_pct']:10.4f} {b['t']:7.2f}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
