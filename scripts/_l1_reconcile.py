#!/usr/bin/env python
"""L-1 reconciliation: why does the event study say +13 bps and the harness say -13?

Stage 1 of scripts/sweep_l1.py measures the fade as an event: enter at the open of the bar after
the stretch is seen, unwind `h` bars later at that bar's open. Stage 2 runs the same rule as a
strategy through the shipped framework and loses in every regime - and so does the inverted
control, which is the signature of a mechanics difference rather than a signal one.

This script runs both on ONE window, pairs the harness's own trade log into round trips, and
prints the realized gross basis points side by side with the event study's, so the gap is
attributed rather than argued about.

    python scripts/_l1_reconcile.py --start 2023-01-01 --end 2023-03-31
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
os.environ.setdefault("INTRADAY_DATA_DIR", str(REPO_DIR / "data" / "minute_alpaca"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import intraday_backtest as ib  # noqa: E402
from intraday_common import LEVERAGED_UNIVERSE, REPO, load_universe  # noqa: E402

sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
from base import features  # noqa: E402


def round_trips(trades: list[dict]) -> pd.DataFrame:
    """Pair the harness's fills per symbol into round trips (this strategy holds one side at a time)."""
    out = []
    open_pos: dict[str, dict] = {}
    for tr in trades:
        s, q, px = tr["sym"], tr["qty"], tr["px"]
        cur = open_pos.get(s)
        if cur is None:
            open_pos[s] = {"qty": q, "px": px, "t": tr["t"], "cost": tr["cost"]}
            continue
        if np.sign(q) == np.sign(cur["qty"]):      # adding to the position: volume-weight the entry
            tot = cur["qty"] + q
            cur["px"] = (cur["px"] * cur["qty"] + px * q) / tot
            cur["qty"] = tot
            cur["cost"] += tr["cost"]
            continue
        closed = min(abs(q), abs(cur["qty"]))
        side = np.sign(cur["qty"])
        out.append({"sym": s, "in": cur["t"], "out": tr["t"], "side": side,
                    "bars": int((tr["t"] - cur["t"]).total_seconds() // 60),
                    "gross_bps": side * (px / cur["px"] - 1.0) * 1e4,
                    "notional": closed * cur["px"],
                    "cost": cur["cost"] * closed / abs(cur["qty"]) + tr["cost"] * closed / abs(q)})
        rem = cur["qty"] + q
        open_pos[s] = {"qty": rem, "px": px, "t": tr["t"], "cost": 0.0} if rem else None
        if not rem:
            open_pos.pop(s)
    return pd.DataFrame(out)


def events(bars, zt: float, h: int, m_from=20, m_to=340, flatten=368) -> pd.DataFrame:
    rows = []
    for sym, df in bars.items():
        f = features(df)
        for day, g in f.groupby("day", sort=True):
            c, o = g["c"].to_numpy(float), g["o"].to_numpy(float)
            vwap, atr = g["vwap"].to_numpy(float), g["atr14"].to_numpy(float)
            minute = g["minute"].to_numpy(int)
            n = len(c)
            with np.errstate(invalid="ignore", divide="ignore"):
                z = (c / vwap - 1.0) / (atr / c)
            fire = np.isfinite(z) & (np.abs(z) >= zt) & (minute >= m_from) & (minute <= m_to)
            last = -1
            for i in np.flatnonzero(fire):
                if i <= last or i + 1 + h >= n or minute[i + 1 + h] >= flatten:
                    continue
                rows.append({"sym": sym, "day": day, "minute": minute[i], "z": z[i],
                             "gross_bps": -np.sign(z[i]) * (o[i + 1 + h] / o[i + 1] - 1.0) * 1e4})
                last = i + h
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2023-03-31")
    ap.add_argument("--z", type=float, default=12.0)
    ap.add_argument("--hold", type=int, default=30)
    ap.add_argument("--symbols", nargs="*", default=LEVERAGED_UNIVERSE)
    args = ap.parse_args()
    lo, hi = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    bars = load_universe(args.symbols, lo, hi)
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("lev_revert")
    p = {**strat.PARAMS, "entry_z": args.z, "max_hold": args.hold, "exit_z": -1e6, "stop_atr": 1e6}
    s = ib.run(strat, bars, 1_000_000.0, p, lo, hi, False, feats_all=feats, collect_trades=True)
    rt = round_trips(s["trades_log"])
    ev = events(bars, args.z, args.hold)

    print(f"\nwindow {lo} .. {hi}, {len(bars)} symbols, z >= {args.z}, hold {args.hold}")
    print(f"  harness   : {s['sessions']} sessions, $/day {s['avg_daily_pnl']:,.0f}, "
          f"costs/day {s['costs_per_day']:,.0f}, trades {s['trades']}, stopped days {s['stopped_days']}")
    print(f"  round trips: {len(rt)}  mean gross {rt['gross_bps'].mean():+.2f} bps  "
          f"median hold {rt['bars'].median():.0f} bars  mean notional ${rt['notional'].mean():,.0f}")
    print(f"  event study: {len(ev)} events  mean gross {ev['gross_bps'].mean():+.2f} bps")
    print(f"  gross $/day from round trips: "
          f"{(rt['gross_bps'] / 1e4 * rt['notional']).sum() / s['sessions']:,.0f}")

    print("\nby hold length (harness round trips):")
    rt["bucket"] = pd.cut(rt["bars"], [0, 5, 15, 29, 31, 60, 1000])
    print(rt.groupby("bucket", observed=True).agg(n=("gross_bps", "size"),
                                                  gross_bps=("gross_bps", "mean"),
                                                  notional=("notional", "mean")).to_string())
    print("\nby symbol:")
    j = rt.groupby("sym").agg(n=("gross_bps", "size"), harness_bps=("gross_bps", "mean")).join(
        ev.groupby("sym").agg(ev_n=("gross_bps", "size"), event_bps=("gross_bps", "mean")))
    print(j.to_string())

    # do the entries even line up? match on (symbol, session, entry minute-1 = decision bar)
    rt["day"] = [t.date() for t in rt["in"]]
    rt["dec_minute"] = [int((t.hour - 9) * 60 + t.minute - 30) - 1 for t in rt["in"]]
    m = ev.merge(rt, left_on=["sym", "day", "minute"], right_on=["sym", "day", "dec_minute"],
                 how="outer", indicator=True, suffixes=("_ev", "_rt"))
    print("\nentry alignment (event decision bar vs harness fill bar - 1):")
    print(m["_merge"].value_counts().to_string())
    both = m[m["_merge"] == "both"]
    if len(both):
        print(f"  matched {len(both)}: event {both['gross_bps_ev'].mean():+.2f} bps vs "
              f"harness {both['gross_bps_rt'].mean():+.2f} bps, "
              f"corr {both['gross_bps_ev'].corr(both['gross_bps_rt']):.3f}")
        bad = both[(both["gross_bps_ev"] - both["gross_bps_rt"]).abs() > 1.0]
        print(f"  disagreeing by > 1 bp: {len(bad)}")
        if len(bad):
            print(bad[["sym", "day", "minute", "bars", "gross_bps_ev", "gross_bps_rt"]].head(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
