#!/usr/bin/env python
"""A-11: are the sleeve's fills possible, and what is left when the impossible ones are removed?

    python scripts/sweep_a11.py --workers 11 --record

Why this exists
---------------
A-5 measured, over the deployed mix's 12,743 fills on the 260-session IBKR store, that the order is
**median 1.03%, p90 5.55%, p99 26.1% and at worst 199%** of the volume of the minute it fills in,
and that the tail is concentrated in SMCI / SOXS / COIN / MSTR, which carry 30% of traded notional.
A fill of a fifth of a minute's volume at that minute's open with zero price impact is not a fill,
and 199% is not a trade at all - so an unknown part of the sleeve's gross P&L is booked at prices
that never existed. That is a **cost-model defect, not a lever**: the question this script answers
is not "does a cap earn more" but "what does the sleeve earn when the impossible fills are gone".

Method
------
Two measurements, on the Alpaca SIP store (2,686 sessions, 2016-2026) rather than A-5's 260-session
IBKR window, because that window is what produced every A-track false positive.

1. **The diagnostic.** Re-run A-5's participation census on ten years and the whole universe, using
   the *actual* volume of the minute each fill happens in. Reported notional-weighted, per symbol,
   and per regime, so the defect is sized on the sample the verdict is drawn from.
2. **The cap.** `RISK["part_cap"]` (0 = off, the shipped behaviour) clips every order to a share of
   the **trailing median** volume of the minute it will fill in - `intraday_common.volume_limits()`,
   20 prior sessions, strictly before the session, so the cap is knowable at decision time. Cells
   0.10 / 0.05 / 0.02 against the uncapped control, one backtest per (cell, calendar year) from a
   fresh $1M book, pooled into A-10's three a-priori regimes.

Because the strategy re-decides every minute, a clipped order is *worked* over the following bars
rather than dropped; the end-of-day flatten is clipped too (22 bars exist between 15:38 and the
close), and whatever the cap still leaves open is dumped into the closing bar and counted, because
that residual is the one fill of the session that genuinely cannot be worked.

Decision rule, fixed before the runs
------------------------------------
A-10 measured this sleeve at -$697/day, t = -3.01, and ORB alone (which is what the deployed
allocation now is) at -$289/day, t = -1.17. **A cap can only make a losing book smaller**, so
nothing here can promote the sleeve and `live/intraday_config.json` is not touched by this script.
The outcomes that matter are: (a) if the capped book's $/day is materially *better* than uncapped,
the shipped numbers were being dragged down by impossible fills and the cap belongs in the shared
sizing code; (b) if it is materially *worse*, the sleeve's historical gross was inflated by fills
that cannot happen and every A-track number is optimistic by that amount; (c) if the difference is
inside one standard error, the defect is real but immaterial at this book size and the honest
record is that it was measured.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
# Must be set before intraday_common is imported (it reads the env var at import time) and it is
# inherited by the spawned workers, so every process in this sweep reads the same store.
os.environ.setdefault("INTRADAY_DATA_DIR", str(REPO_DIR / "data" / "minute_alpaca"))

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import intraday_backtest as ib  # noqa: E402
from intraday_common import DATA_DIR, REPO, UNIVERSE, load_universe  # noqa: E402

EQUITY = 1_000_000.0
OUT = REPO / "results" / "a11"

#: live/intraday_config.json as deployed after A-10 (late_momo dropped, so the mix IS orb alone).
DEPLOYED = {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 0.0},
            "per_symbol": 0.15, "gross": 1.5,
            "sub_params": {"late_momo": {"direction": -1}, "orb": {"disaster_atr": 4.0}}}

#: cap as a fraction of the trailing median volume of the fill minute; 0.0 is the shipped no-cap.
CELLS = [0.0, 0.10, 0.05, 0.02]
YEARS = list(range(2016, 2027))
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]
SEEN_FROM = dt.date(2025, 8, 26)


def cell_name(c: float) -> str:
    return "off" if not c else f"{c:g}"


# --------------------------------------------------------------------------------- worker
def _job(spec):
    """One calendar year: load once, run every cap cell on the same bars and features."""
    year, cells, symbols = spec
    lo, hi = dt.date(year, 1, 1), dt.date(year, 12, 31)
    bars = load_universe(symbols or UNIVERSE, lo, hi)
    if not bars:
        return year, {}, pd.DataFrame()
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("active")
    params = {**strat.PARAMS, **DEPLOYED}

    # actual volume of every minute, for the diagnostic denominator (NOT the trailing median: the
    # census asks what really traded in the minute the backtester assumed it filled in).
    vol = {}
    for s, df in bars.items():
        vol[s] = df["v"].groupby([df.index.date,
                                  (df.index.hour - 9) * 60 + df.index.minute - 30]).sum()

    out, census = {}, pd.DataFrame()
    for c in cells:
        ib.RISK["part_cap"] = float(c)
        s = ib.run(strat, bars, EQUITY, params, lo, hi, False, feats_all=feats,
                   collect_trades=(c == 0.0))
        d = s.pop("daily")
        rec = {"daily": d, "trades_per_day": s["trades_per_day"], "costs_per_day": s["costs_per_day"],
               "turnover_per_day_x": s["turnover_per_day_x"], "stopped_days": s["stopped_days"],
               "trades": s["trades"]}
        for k in ("clipped_orders", "clipped_notional_refused", "forced_eod_orders", "forced_eod_notional"):
            if k in s:
                rec[k] = s[k]
        out[cell_name(c)] = rec
        if c == 0.0:
            rows = []
            for tr in s.get("trades_log", []):
                t, sym = tr["t"], tr["sym"]
                v = vol[sym].get((t.date(), (t.hour - 9) * 60 + t.minute - 30), np.nan)
                if v and v == v:
                    rows.append((sym, t.date(), abs(tr["qty"]) / v, abs(tr["qty"]) * tr["px"]))
            census = pd.DataFrame(rows, columns=["sym", "day", "part", "notional"])
    ib.RISK["part_cap"] = 0.0
    return year, out, census


# --------------------------------------------------------------------------------- statistics
def stats(d: pd.DataFrame) -> dict:
    n = len(d)
    if n < 2:
        return {}
    pnl, ret = d["pnl"].values, d["ret"].values
    se = pnl.std(ddof=1) / np.sqrt(n)
    growth = float(np.prod(1.0 + ret))
    eq = EQUITY * np.cumprod(1.0 + ret)
    peak = np.maximum.accumulate(np.concatenate([[EQUITY], eq]))
    return {"sessions": n, "$/day": pnl.mean(), "se": se, "t": pnl.mean() / se if se else float("nan"),
            "sharpe": ret.mean() / ret.std(ddof=1) * np.sqrt(252) if ret.std(ddof=1) else float("nan"),
            "net_pct": (growth - 1.0) * 100, "car_pct": ((growth ** (252 / n)) - 1.0) * 100,
            "max_dd_pct": -float((np.concatenate([[EQUITY], eq]) / peak - 1.0).min()) * 100,
            "worst_day": pnl.min(), "win_days_pct": (pnl > 0).mean() * 100}


def paired(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """Paired difference (cell - control) on the sessions both ran, the honest comparison here."""
    m = a.set_index("day")["pnl"].reindex(b["day"].values).values - b.set_index("day")["pnl"].values
    m = m[~np.isnan(m)]
    if len(m) < 2:
        return {}
    se = m.std(ddof=1) / np.sqrt(len(m))
    return {"d$/day": m.mean(), "d_se": se, "d_t": m.mean() / se if se else float("nan")}


def table(rows: list[dict], title: str, note: str = "") -> pd.DataFrame:
    t = pd.DataFrame(rows)
    print(f"\n=== {title} ===")
    with pd.option_context("display.width", 220):
        print(t.to_string(index=False))
    if note:
        print(note)
    return t


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--years", nargs="*", type=int, default=YEARS)
    ap.add_argument("--cells", nargs="*", type=float, default=CELLS)
    ap.add_argument("--symbols", nargs="*", help="subset of the universe (smoke tests only)")
    ap.add_argument("--record", action="store_true", help="append the regime runs to the ledger")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cells = [c for c in args.cells]
    if 0.0 not in cells:
        cells = [0.0] + cells
    names = [cell_name(c) for c in cells]
    print(f"store: {DATA_DIR}")
    print(f"{len(args.years)} yearly jobs x {len(cells)} cells {names}, {args.workers} workers; "
          f"each year is a fresh ${EQUITY:,.0f} book of the DEPLOYED allocation (orb alone)")

    per_year, census = {}, []
    jobs = [(y, cells, args.symbols) for y in args.years]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for year, out, cen in ex.map(_job, jobs):
            if not out:
                print(f"  {year}: no bars", flush=True)
                continue
            per_year[year] = out
            if not cen.empty:
                census.append(cen)
            o = out["off"]
            print(f"  {year}: {len(o['daily'])} sessions  off $/day {o['daily']['pnl'].mean():>8,.0f}  "
                  f"tr/day {o['trades_per_day']:5.1f}", flush=True)
    if not per_year:
        sys.exit("no results")

    # ------------------------------------------------------------------ 1. the diagnostic
    if census:
        cen = pd.concat(census, ignore_index=True)
        cen.to_csv(OUT / "census.csv", index=False)
        w = cen["notional"] / cen["notional"].sum()
        order = np.argsort(cen["part"].values)
        cw = np.cumsum(w.values[order])
        wq = lambda q: float(cen["part"].values[order][np.searchsorted(cw, q)])  # noqa: E731
        print(f"\n=== A-11 diagnostic: {len(cen):,} fills, {cen['sym'].nunique()} names, "
              f"{cen['day'].nunique():,} sessions ===")
        print(f"  order as a share of its fill minute's volume, NOTIONAL-WEIGHTED:")
        for q in (0.5, 0.75, 0.9, 0.99):
            print(f"    p{int(q*100):<3} {wq(q)*100:7.2f}%")
        print(f"    max   {cen['part'].max()*100:7.2f}%")
        print(f"  share of traded notional filled at > 5% of the minute:  "
              f"{w[cen['part'] > 0.05].sum()*100:5.1f}%")
        print(f"  share of traded notional filled at > 20% of the minute: "
              f"{w[cen['part'] > 0.20].sum()*100:5.1f}%")
        rows = []
        for sym, g in cen.groupby("sym"):
            rows.append({"sym": sym, "fills": len(g), "notional %": round(g["notional"].sum() / cen["notional"].sum() * 100, 1),
                         "median %": round(g["part"].median() * 100, 2), "p90 %": round(g["part"].quantile(0.9) * 100, 2),
                         "p99 %": round(g["part"].quantile(0.99) * 100, 2), "max %": round(g["part"].max() * 100, 1)})
        table(sorted(rows, key=lambda r: -r["p90 %"]), "participation by symbol (2016-2026)",
              "  A-5 on the 260-session IBKR store: median 1.03, p90 5.55, p99 26.1, max 199.").to_csv(
            OUT / "by_symbol.csv", index=False)

    # ------------------------------------------------------------------ 2. the cap
    daily = {n: pd.concat([per_year[y][n]["daily"] for y in sorted(per_year) if n in per_year[y]],
                          ignore_index=True).sort_values("day").reset_index(drop=True)
             for n in names}
    for n, d in daily.items():
        d.to_csv(OUT / f"daily_{n}.csv", index=False)

    ctrl = daily["off"]
    for scope, lo, hi in REGIMES + [("ALL", 2016, 2026)]:
        rows = []
        for n in names:
            d = daily[n]
            sub = d[(d["day"] >= dt.date(lo, 1, 1)) & (d["day"] <= dt.date(hi, 12, 31))]
            csub = ctrl[(ctrl["day"] >= dt.date(lo, 1, 1)) & (ctrl["day"] <= dt.date(hi, 12, 31))]
            s = stats(sub)
            if not s:
                continue
            p = paired(sub, csub) if n != "off" else {}
            rows.append({"cap": n, "sessions": s["sessions"], "$/day": round(s["$/day"]),
                         "t": round(s["t"], 2), "sharpe": round(s["sharpe"], 2),
                         "car %": round(s["car_pct"], 1), "maxDD %": round(s["max_dd_pct"], 1),
                         "worst day": round(s["worst_day"]),
                         "tr/day": round(np.mean([per_year[y][n]["trades_per_day"] for y in per_year
                                                  if lo <= y <= hi and n in per_year[y]]), 1),
                         "vs off $/day": round(p["d$/day"]) if p else "",
                         "vs off t": round(p["d_t"], 2) if p else ""})
        table(rows, f"participation cap, {scope}").to_csv(OUT / f"cells_{scope}.csv", index=False)

    # what the cap refused, and what it could not work off before the close
    rows = []
    for n in names:
        if n == "off":
            continue
        tot = lambda k: sum(per_year[y][n].get(k, 0) for y in per_year if n in per_year[y])  # noqa: E731
        nd = len(daily[n])
        rows.append({"cap": n, "clipped orders": tot("clipped_orders"),
                     "notional refused $/day": round(tot("clipped_notional_refused") / nd),
                     "forced closing-bar fills": tot("forced_eod_orders"),
                     "forced closing-bar $/day": round(tot("forced_eod_notional") / nd)})
    if rows:
        table(rows, "what the cap did",
              "  'forced closing-bar' is size the cap could not work off between 15:38 and the close;\n"
              "  it is dumped into the last bar, which is the one fill of the session that is not workable.").to_csv(
            OUT / "cap_action.csv", index=False)

    # the fitted window, for reference
    rows = []
    for n in names:
        s = stats(daily[n][daily[n]["day"] >= SEEN_FROM])
        if s:
            rows.append({"cap": n, "sessions": s["sessions"], "$/day": round(s["$/day"]),
                         "t": round(s["t"], 2), "sharpe": round(s["sharpe"], 2)})
    table(rows, f"the window every A-track parameter was fitted on (>= {SEEN_FROM})")

    if args.record:
        for n in names:
            for scope, lo, hi in REGIMES:
                d = daily[n]
                sub = d[(d["day"] >= dt.date(lo, 1, 1)) & (d["day"] <= dt.date(hi, 12, 31))]
                s = stats(sub)
                if not s:
                    continue
                yrs = [y for y in per_year if lo <= y <= hi and n in per_year[y]]
                tpd = float(np.mean([per_year[y][n]["trades_per_day"] for y in yrs]))
                cpd = float(np.mean([per_year[y][n]["costs_per_day"] for y in yrs]))
                fake = {"sessions": s["sessions"], "net_profit_pct": s["net_pct"], "cagr_pct": s["car_pct"],
                        "sharpe": s["sharpe"], "max_drawdown_pct": s["max_dd_pct"], "avg_daily_pnl": s["$/day"],
                        "worst_day": s["worst_day"], "trades": int(round(tpd * s["sessions"])),
                        "trades_per_day": tpd, "costs_per_day": cpd,
                        "stopped_days": sum(per_year[y][n]["stopped_days"] for y in yrs)}
                ib.RISK["part_cap"] = 0.0 if n == "off" else float(n)
                ib.record("active", f"A-11 alpaca part_cap={n} [{scope}] (yearly-reset $1M book)",
                          fake, DEPLOYED, dt.date(lo, 1, 1), dt.date(hi, 12, 31))
        ib.RISK["part_cap"] = 0.0

    json.dump({"cells": names, "years": sorted(per_year)},
              (OUT / "run.json").open("w", encoding="utf-8"), indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
