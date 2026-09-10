#!/usr/bin/env python
"""A-10: statistical power. Judge the deployed intraday mix on the Alpaca SIP store.

    python scripts/sweep_a10.py --workers 11 --record

Why this exists
---------------
A-4 measured the sleeve on the IBKR store's 260 sessions and got Sharpe 0.69 at t = +0.61, then
did the power calculation: `(2/0.69)**2` years = ~2,120 sessions are needed to reject zero at two
sigma. `scripts/alpaca_data.py` now holds consolidated 1-minute bars for the same 16 names back to
2016 - **2,686 sessions**, i.e. the first sample this sleeve has ever had that is capable of
answering the question at all. A-5 sharpened the question: on the 77 sessions no A-track parameter
ever saw, gross P&L *before any slippage* is -$11/day, so what is being tested here is whether the
mix has a gross edge anywhere outside its own tuning window.

Method
------
One backtest per (strategy, calendar year), each starting from a fresh $1,000,000 book. The yearly
reset is deliberate: it makes a dollar of P&L in 2016 comparable with a dollar in 2026, which is
what a t-statistic on daily P&L needs, and it stops eleven years of compounding from letting the
last two years own the whole sample. Daily returns are then concatenated per regime, so Sharpe and
CAR are computed on the pooled series exactly as `intraday_backtest.summarize` would.

Three regimes, chosen a priori as market epochs rather than fitted: **2016-2019** (the low-vol
bull), **2020-2023** (COVID, the 2021 melt-up and the 2022 bear) and **2024-2026** (the current
one, which contains every session any A-track parameter has ever seen). Three strategies: the
deployed mix, and the same framework with each sub-strategy alone, so the isolation is done inside
the shipped per-symbol and gross caps rather than against a different sizing rule.

Decision rule, fixed before the runs (backlog A-10): the mix must be positive at t > 2 in at least
two of the three regimes. If it is not, `gross` in `live/intraday_config.json` is cut from 1.5 to
0.75 - the owner asked for volatility, not for noise dressed as edge. The script prints the verdict
and writes nothing; the config edit is a journalled decision (AGENTS.md rule c).

Costs are the shipped ones (1.5 bps slippage plus IBKR commission). The Alpaca store is
split-adjusted, so a fill price is the adjusted price and the notional per share differs from the
IBKR store on names that split (NVDA 2024, AMZN/GOOGL 2022); the sleeve sizes in weights, not
shares, so the book is unaffected.
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
OUT = REPO / "results" / "a10"

#: live/intraday_config.json as of A-2. The control for everything here.
DEPLOYED = {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 1.0},
            "per_symbol": 0.15, "gross": 1.5,
            "sub_params": {"late_momo": {"direction": -1}, "orb": {"disaster_atr": 4.0}}}

#: Each variant is the deployed framework with a different allocation, so the per-symbol and gross
#: caps, the loss limit and the flatten are identical and only the signal mix changes.
VARIANTS = {
    "mix": DEPLOYED,
    "orb": {**DEPLOYED, "alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 0.0}},
    "fade": {**DEPLOYED, "alloc": {"orb": 0.0, "vwap_trend": 0.0, "late_momo": 1.0}},
}

YEARS = list(range(2016, 2027))
#: a-priori market epochs, not fitted boundaries
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]
#: A-track parameters have only ever seen sessions from here on (the IBKR store starts 2025-08-26)
SEEN_FROM = dt.date(2025, 8, 26)


# --------------------------------------------------------------------------------- worker
def _job(spec):
    """One calendar year: load once, run every variant on the same bars and features."""
    year, variants, symbols = spec
    lo, hi = dt.date(year, 1, 1), dt.date(year, 12, 31)
    bars = load_universe(symbols or UNIVERSE, lo, hi)
    if not bars:
        return year, {}, pd.DataFrame()
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("active")

    # universe mean daily range (high-low over close), the A-4 long-volatility regressor
    rng = []
    for s, df in bars.items():
        g = df.groupby(df.index.date)
        rng.append(((g["h"].max() - g["l"].min()) / g["c"].last()).rename(s))
    ranges = pd.concat(rng, axis=1).mean(axis=1).rename("range")

    out = {}
    for name in variants:
        params = {**strat.PARAMS, **VARIANTS[name]}
        s = ib.run(strat, bars, EQUITY, params, lo, hi, False, feats_all=feats)
        d = s.pop("daily")
        out[name] = {"daily": d, "trades_per_day": s["trades_per_day"],
                     "costs_per_day": s["costs_per_day"], "turnover_per_day_x": s["turnover_per_day_x"],
                     "stopped_days": s["stopped_days"]}
    return year, out, ranges


# --------------------------------------------------------------------------------- statistics
def stats(d: pd.DataFrame) -> dict:
    """Pooled statistics on a concatenated daily frame (each year started from a fresh book)."""
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


def table(rows: list[dict], title: str, note: str = "") -> pd.DataFrame:
    t = pd.DataFrame(rows)
    print(f"\n=== {title} ===")
    with pd.option_context("display.width", 200):
        print(t.to_string(index=False))
    if note:
        print(note)
    return t


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--years", nargs="*", type=int, default=YEARS)
    ap.add_argument("--variants", nargs="*", default=list(VARIANTS))
    ap.add_argument("--symbols", nargs="*", help="subset of the universe (smoke tests only)")
    ap.add_argument("--record", action="store_true", help="append the regime runs to the ledger")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"store: {DATA_DIR}")
    print(f"{len(args.years)} yearly jobs x {len(args.variants)} variants, {args.workers} workers; "
          f"each year is a fresh ${EQUITY:,.0f} book")

    per_year, ranges = {}, []
    jobs = [(y, args.variants, args.symbols) for y in args.years]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for year, out, rng in ex.map(_job, jobs):
            if not out:
                print(f"  {year}: no bars", flush=True)
                continue
            per_year[year] = out
            ranges.append(rng)
            m = out.get(args.variants[0])
            print(f"  {year}: {len(m['daily'])} sessions  {args.variants[0]} $/day "
                  f"{m['daily']['pnl'].mean():>8,.0f}  tr/day {m['trades_per_day']:5.1f}", flush=True)

    if not per_year:
        sys.exit("no results")
    ranges = pd.concat(ranges).sort_index()

    # ------------------------------------------------------------------ per-variant, per-regime
    daily = {v: pd.concat([per_year[y][v]["daily"] for y in sorted(per_year) if v in per_year[y]],
                          ignore_index=True).sort_values("day").reset_index(drop=True)
             for v in args.variants}
    for v, d in daily.items():
        d.to_csv(OUT / f"daily_{v}.csv", index=False)

    verdict_rows = []
    for v in args.variants:
        d = daily[v]
        rows = []
        for name, y0, y1 in REGIMES:
            sub = d[(d["day"] >= dt.date(y0, 1, 1)) & (d["day"] <= dt.date(y1, 12, 31))]
            s = stats(sub)
            if not s:
                continue
            rows.append({"regime": name, **{k: round(val, 2) for k, val in s.items()}})
            if v == "mix":
                verdict_rows.append({"regime": name, "t": s["t"], "$/day": s["$/day"]})
        s_all = stats(d)
        rows.append({"regime": "ALL", **{k: round(val, 2) for k, val in s_all.items()}})
        # the window every A-track parameter was fitted on, for reference
        seen = stats(d[d["day"] >= SEEN_FROM])
        if seen:
            rows.append({"regime": f"(seen >= {SEEN_FROM})", **{k: round(val, 2) for k, val in seen.items()}})
        table(rows, f"{v}: deployed framework, Alpaca SIP store, {int(s_all['sessions'])} sessions").to_csv(
            OUT / f"regimes_{v}.csv", index=False)
        if args.record:
            for name, y0, y1 in REGIMES:
                sub = d[(d["day"] >= dt.date(y0, 1, 1)) & (d["day"] <= dt.date(y1, 12, 31))]
                s = stats(sub)
                if not s:
                    continue
                tpd = np.mean([per_year[y][v]["trades_per_day"] for y in range(y0, y1 + 1)
                               if y in per_year and v in per_year[y]])
                cpd = np.mean([per_year[y][v]["costs_per_day"] for y in range(y0, y1 + 1)
                               if y in per_year and v in per_year[y]])
                stopped = sum(per_year[y][v]["stopped_days"] for y in range(y0, y1 + 1)
                              if y in per_year and v in per_year[y])
                fake = {"sessions": s["sessions"], "net_profit_pct": s["net_pct"], "cagr_pct": s["car_pct"],
                        "sharpe": s["sharpe"], "max_drawdown_pct": s["max_dd_pct"], "avg_daily_pnl": s["$/day"],
                        "worst_day": s["worst_day"], "trades": int(round(tpd * s["sessions"])),
                        "trades_per_day": tpd, "costs_per_day": cpd, "stopped_days": stopped}
                ib.record("active", f"A-10 alpaca {v} [{name}] (yearly-reset $1M book)", fake,
                          VARIANTS[v], dt.date(y0, 1, 1), dt.date(y1, 12, 31))

    # ------------------------------------------------------------------ year by year, mix
    if "mix" in daily:
        rows = []
        for y in sorted(per_year):
            d = daily["mix"]
            sub = d[(d["day"] >= dt.date(y, 1, 1)) & (d["day"] <= dt.date(y, 12, 31))]
            s = stats(sub)
            if s:
                rows.append({"year": y, "sessions": s["sessions"], "$/day": round(s["$/day"]),
                             "t": round(s["t"], 2), "sharpe": round(s["sharpe"], 2),
                             "car %": round(s["car_pct"], 1), "worst day": round(s["worst_day"]),
                             "tr/day": round(per_year[y]["mix"]["trades_per_day"], 1),
                             "costs/day": round(per_year[y]["mix"]["costs_per_day"])})
        table(rows, "mix, year by year",
              "  A-track parameters were fitted on 2025-08-26.. only; every earlier year is unseen.").to_csv(
            OUT / "years_mix.csv", index=False)

    # ------------------------------------------------------------------ A-4's long-volatility claim
    if "mix" in daily:
        rows = []
        for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
            d = daily["mix"]
            sub = d[(d["day"] >= dt.date(y0, 1, 1)) & (d["day"] <= dt.date(y1, 12, 31))].set_index("day")
            r = ranges.reindex(sub.index)
            ok = r.notna() & sub["pnl"].notna()
            if ok.sum() < 30:
                continue
            c = float(np.corrcoef(sub["pnl"][ok], r[ok])[0, 1])
            n = int(ok.sum())
            rows.append({"regime": name, "sessions": n, "corr(P&L, range)": round(c, 3),
                         "t": round(c * np.sqrt((n - 2) / max(1e-9, 1 - c * c)), 2),
                         "mean range %": round(float(r[ok].mean()) * 100, 2)})
        table(rows, "A-4's long-volatility claim, re-tested out of its own sample",
              "  A-4 measured corr +0.538 (t = +10.25) on the 260-session IBKR store.").to_csv(
            OUT / "range_corr.csv", index=False)

    # ------------------------------------------------------------------ verdict
    print("\n=== A-10 verdict (rule fixed before the runs) ===")
    passing = [r for r in verdict_rows if r["t"] > 2.0]
    for r in verdict_rows:
        print(f"  {r['regime']:<12} $/day {r['$/day']:>8,.0f}   t {r['t']:+6.2f}   "
              f"{'PASS' if r['t'] > 2.0 else 'fail'}")
    print(f"  {len(passing)}/{len(verdict_rows)} regimes positive at t > 2")
    if len(passing) >= 2:
        print("  -> the mix keeps gross 1.5 in live/intraday_config.json")
    else:
        print("  -> RULE FIRES: cut gross 1.5 -> 0.75 in live/intraday_config.json and journal it")
    json.dump({"regimes": verdict_rows, "passing": len(passing)},
              (OUT / "verdict.json").open("w", encoding="utf-8"), indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
