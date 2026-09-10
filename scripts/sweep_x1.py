#!/usr/bin/env python
"""X-1: is there a cross-sectional intraday momentum edge across the 50 US megacaps?

    python scripts/sweep_x1.py --stage events   --workers 6            # stage 1, cost-free
    python scripts/sweep_x1.py --stage backtest --workers 3 --record   # stage 2, full harness

Hypothesis (backlog X-1). Breadth is where a robust intraday edge is more likely than in a
16-name book: rank the megacaps every `rebalance` minutes by their intraday return *relative to
the basket*, hold the top decile long and the bottom decile short, and flat by 15:38. The book is
dollar-neutral by construction, so what is measured is the cross-sectional spread, not the market.

Method, the same two stages L-1 established
-------------------------------------------
Stage 1 measures the mechanism with nothing to fit: an **event study** on the raw bars. At each
rebalance minute the cross-section is demeaned, the top and bottom `k` names are taken, each leg is
entered at the NEXT bar's open (the harness's fill convention) and unwound `h` bars later at that
bar's open. A leg's return is scored **relative to the equal-weight basket over the same window**,
because that is what a dollar-neutral book actually earns. Cost is charged per leg round trip from
the real (split-unadjusted) share price. Only a cell that clears cost earns a stage 2 run.

Statistics. Legs inside one session overlap in time and share the market factor, so each session is
collapsed to ONE number. **The decision statistic is the per-session SUM** of the legs' returns: a
book puts the same notional on every leg, so the session earns the sum, not the average. The
session-equal average is printed as a labelled diagnostic only - on L-1 the two disagreed in sign
and the session-equal one was wrong, because the count of signals is itself correlated with what a
signal is worth. The reported "bps" is the session sum accumulated over the sample divided by the
number of legs, i.e. the edge per dollar deployed, and the t is over sessions.

The momentum sign and the reversal sign are the same experiment: reversal is the negative of the
gross column, so it is reported explicitly rather than run twice, and both are charged the same
cost - a cell is only interesting if ONE of the two signs is positive net of cost.

Regimes are A-10's, chosen a priori: 2016-2019, 2020-2023, 2024-2026. Decision rule fixed before
the runs (backlog X-1, owner instruction 2026-09-10): the NET edge must be positive at t > 2 in at
least two of the three regimes; nothing is deployed otherwise.
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
from fetch_data import MEGACAPS  # noqa: E402
from intraday_common import (COMMISSION_PER_SHARE, DATA_DIR, REPO, SEC_FEE_RATE,  # noqa: E402
                             SLIPPAGE_BPS, TAF_PER_SHARE, load_bars, share_scale)

EQUITY = 1_000_000.0
OUT = REPO / "results" / "x1"
YEARS = list(range(2016, 2027))
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]
#: the store is refreshed intraday, so the current session is partial and never enters a study
LAST_DAY = dt.date(2026, 9, 9)

#: Alpaca spells Berkshire's B share with a dot; fetch_data keeps the Yahoo spelling.
UNIVERSE_X1 = [s.replace("-", ".") for s in MEGACAPS]

#: event-study grid
LOOKBACKS = [15, 30, 60, 0]          # minutes of intraday return used to rank; 0 = since the open
HORIZONS = [30, 60]                  # bars held
DECILES = [5, 10]                    # names per side
MIN_NAMES = 20                       # refuse to rank a cross-section thinner than this
REBALANCE = 30                       # a decision every 30 minutes
FIRST_MINUTE, LAST_ENTRY = 30, 330   # 10:00 .. 15:00
FLATTEN_MINUTE = 368                 # framework constant: flat by 15:38
BARS_PER_SESSION = 390

#: stage 2 variants, filled from the stage 1 grid at run time
VARIANTS = {
    "momo": {"params": {"direction": 1}},
    "rev": {"params": {"direction": -1}},
}


# --------------------------------------------------------------------------------- stage 1
def _cost_bps(real_px):
    """Modelled round-trip cost of one leg, in basis points of its notional (array or scalar).

    Two slippage charges, two per-share commissions, and the sell-side regulatory fees exactly
    once - a round trip has exactly one sale whether the leg is long or short. `real_px` is the
    unadjusted share price, because IBKR charges per share at the price that was really quoted.
    """
    comm = COMMISSION_PER_SHARE / real_px * 1e4
    sell = SEC_FEE_RATE * 1e4 + TAF_PER_SHARE / real_px * 1e4
    return 2 * SLIPPAGE_BPS + 2 * comm + sell


def _panel_job(spec):
    """One (year, symbol) -> (symbol, days, open matrix, close matrix), each (n_days, 390).

    The event study only needs prices on a (session, minute-of-day) grid, so each symbol-year is
    reduced to two small float arrays here and the cross-section is assembled in the parent. Missing
    minutes stay NaN and are dropped per event, which is how a halted or late-listed name behaves.
    """
    year, sym = spec
    lo, hi = dt.date(year, 1, 1), min(dt.date(year, 12, 31), LAST_DAY)
    df = load_bars(sym, lo, hi)
    if df.empty:
        return sym, None, None, None
    minute = (df.index.hour - 9) * 60 + df.index.minute - 30
    day = pd.Index(df.index.date)
    ok = (minute >= 0) & (minute < BARS_PER_SESSION)
    df, minute, day = df[ok], minute[ok], day[ok]
    days = np.array(sorted(set(day)))
    row = pd.Index(days).get_indexer(day)
    o = np.full((len(days), BARS_PER_SESSION), np.nan, dtype=np.float32)
    c = np.full((len(days), BARS_PER_SESSION), np.nan, dtype=np.float32)
    o[row, minute] = df["o"].to_numpy(np.float32)
    c[row, minute] = df["c"].to_numpy(np.float32)
    return sym, days, o, c


def _events_year(year: int, symbols: list[str], workers: int) -> pd.DataFrame:
    """All (day, lookback, horizon, k) event aggregates for one calendar year."""
    panels = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for sym, days, o, c in ex.map(_panel_job, [(year, s) for s in symbols]):
            if days is not None:
                panels[sym] = (days, o, c)
    if len(panels) < 10:
        return pd.DataFrame()
    all_days = np.array(sorted(set().union(*[set(d) for d, _, _ in panels.values()])))
    syms = sorted(panels)
    nd, ns = len(all_days), len(syms)
    O = np.full((nd, BARS_PER_SESSION, ns), np.nan, dtype=np.float32)
    C = np.full((nd, BARS_PER_SESSION, ns), np.nan, dtype=np.float32)
    for j, s in enumerate(syms):
        days, o, c = panels[s]
        idx = pd.Index(all_days).get_indexer(days)
        O[idx, :, j] = o
        C[idx, :, j] = c
    del panels
    # real (unadjusted) price per (day, symbol), for the per-share commission
    scale = np.array([[share_scale(s, d) for s in syms] for d in all_days], dtype=np.float64)

    entries = list(range(FIRST_MINUTE, LAST_ENTRY + 1, REBALANCE))
    rows = []
    for lb in LOOKBACKS:
        for m in entries:
            if lb and m - lb < 0:          # a negative index would wrap into the previous close
                continue
            past = C[:, m - lb, :] if lb else O[:, 0, :]
            sig = C[:, m, :] / past - 1.0                     # intraday return over the lookback
            sig = sig - np.nanmean(sig, axis=1, keepdims=True)  # vs the equal-weight basket
            px_in = O[:, m + 1, :]
            for h in HORIZONS:
                if m + 1 + h >= FLATTEN_MINUTE:
                    continue
                px_out = O[:, m + 1 + h, :]
                fwd = px_out / px_in - 1.0
                fwd = fwd - np.nanmean(fwd, axis=1, keepdims=True)   # dollar-neutral book
                valid = np.isfinite(sig) & np.isfinite(fwd) & (px_in > 0)
                order = np.where(valid, sig, np.nan)
                # rank within each session, NaNs last
                rank = np.argsort(np.argsort(np.where(np.isnan(order), np.inf, order), axis=1), axis=1)
                nvalid = valid.sum(axis=1, keepdims=True)
                for k in DECILES:
                    long = valid & (rank >= nvalid - k)
                    short = valid & (rank < k)
                    enough = (nvalid.ravel() >= max(MIN_NAMES, 3 * k))
                    side = np.where(long, 1.0, 0.0) + np.where(short, -1.0, 0.0)
                    take = (side != 0) & enough[:, None]
                    if not take.any():
                        continue
                    r = np.where(take, side * fwd * 1e4, 0.0)
                    cost = np.where(take, _cost_bps(px_in * scale), 0.0)
                    n = take.sum(axis=1)
                    with np.errstate(invalid="ignore"):
                        rows.append(pd.DataFrame({
                            "day": all_days, "lb": lb, "h": h, "k": k, "minute": m,
                            "n": n, "gross_sum": np.nansum(r, axis=1),
                            "cost_sum": np.nansum(cost, axis=1),
                            "hit": np.nansum((r > 0) & take, axis=1),
                            "px": np.nansum(np.where(take, px_in * scale, 0.0), axis=1)})[n > 0])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _cluster_t(per_session) -> tuple[float, float, int]:
    """mean, t and N over session-level numbers (the clustering unit)."""
    x = np.asarray(per_session, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return float("nan"), float("nan"), n
    se = x.std(ddof=1) / np.sqrt(n)
    return float(x.mean()), float(x.mean() / se) if se else float("nan"), n


def stage_events(workers: int, symbols: list[str], from_csv: bool = False) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if from_csv:
        ev = pd.read_csv(OUT / "events.csv")
        ev["day"] = pd.to_datetime(ev["day"]).dt.date
        print(f"re-aggregating {OUT / 'events.csv'} (no bars read)")
    else:
        print(f"stage 1 (event study): {len(symbols)} symbols x {len(YEARS)} years, {workers} workers")
        parts = []
        for y in YEARS:
            df = _events_year(y, symbols, workers)
            if not df.empty:
                parts.append(df)
                print(f"  {y}: {df['day'].nunique():,} sessions, {int(df['n'].sum()):,} legs", flush=True)
        if not parts:
            sys.exit("no events")
        ev = pd.concat(parts, ignore_index=True)
        ev.to_csv(OUT / "events.csv", index=False)
    ev["net_sum"] = ev["gross_sum"] - ev["cost_sum"]
    print(f"  {len(ev):,} (day, cell, minute) rows, {int(ev['n'].sum()):,} legs, "
          f"{ev['day'].nunique():,} sessions")

    # -------------------------------------------------- grid: regime x lookback x horizon x k
    grid = []
    for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
        sub = ev[(ev["day"] >= dt.date(y0, 1, 1)) & (ev["day"] <= dt.date(y1, 12, 31))]
        for lb in LOOKBACKS:
            for h in HORIZONS:
                for k in DECILES:
                    cell = sub[(sub["lb"] == lb) & (sub["h"] == h) & (sub["k"] == k)]
                    if cell.empty:
                        continue
                    # DECISION statistic: one fixed notional per leg, so a session earns the SUM
                    tot = cell.groupby("day").agg(gross=("gross_sum", "sum"), cost=("cost_sum", "sum"),
                                                  net=("net_sum", "sum"), n=("n", "sum"), hit=("hit", "sum"))
                    _, g_t, n_days = _cluster_t(tot["gross"])
                    _, n_t, _ = _cluster_t(tot["net"])
                    _, r_t, _ = _cluster_t(-tot["gross"] - tot["cost"])   # the reversal sign
                    legs = float(tot["n"].sum())
                    # DIAGNOSTIC only: one vote per session regardless of capital employed
                    sess_equal = cell.groupby("day").apply(
                        lambda d: float(d["gross_sum"].sum() / d["n"].sum()), include_groups=False)
                    grid.append({"regime": name, "lb": lb, "hold": h, "k": k, "legs": int(legs),
                                 "sessions": n_days, "legs/day": round(legs / max(1, n_days), 1),
                                 "gross bps": round(tot["gross"].sum() / legs, 2), "t gross": round(g_t, 2),
                                 "cost bps": round(tot["cost"].sum() / legs, 2),
                                 "net bps": round(tot["net"].sum() / legs, 2), "t net": round(n_t, 2),
                                 "rev net bps": round((-tot["gross"].sum() - tot["cost"].sum()) / legs, 2),
                                 "t rev": round(r_t, 2),
                                 "hit %": round(100.0 * tot["hit"].sum() / legs, 1),
                                 "[diag] session-equal gross bps": round(float(sess_equal.mean()), 2)})
    gdf = pd.DataFrame(grid)
    gdf.to_csv(OUT / "events_grid.csv", index=False)
    for name, _, _ in REGIMES + [("ALL", 0, 0)]:
        t = gdf[gdf["regime"] == name]
        if t.empty:
            continue
        print(f"\n=== stage 1: cross-sectional momentum, {name} "
              f"(gross > 0 = winners keep winning; 'rev net' is the fade sign, net of the same cost) ===")
        with pd.option_context("display.width", 240):
            print(t.drop(columns=["regime"]).to_string(index=False))

    # -------------------------------------------------- time of day, at the ALL level
    tod = []
    for (lb, h, k, m), cell in ev.groupby(["lb", "h", "k", "minute"]):
        if (lb, h, k) != (LOOKBACKS[1], HORIZONS[0], DECILES[0]):
            continue
        tot = cell.groupby("day").agg(gross=("gross_sum", "sum"), net=("net_sum", "sum"), n=("n", "sum"))
        _, g_t, n_days = _cluster_t(tot["gross"])
        legs = float(tot["n"].sum())
        tod.append({"entry minute": m, "clock": f"{9 + (30 + m) // 60}:{(30 + m) % 60:02d}",
                    "legs": int(legs), "gross bps": round(tot["gross"].sum() / legs, 2),
                    "t gross": round(g_t, 2), "net bps": round(tot["net"].sum() / legs, 2)})
    if tod:
        print(f"\n=== stage 1: by entry time (lookback {LOOKBACKS[1]}, hold {HORIZONS[0]}, k={DECILES[0]}) ===")
        print(pd.DataFrame(tod).to_string(index=False))
        pd.DataFrame(tod).to_csv(OUT / "events_time_of_day.csv", index=False)

    # -------------------------------------------------- L-1's lesson, checked on this universe
    busy = []
    for lb, h, k in [(LOOKBACKS[1], HORIZONS[0], DECILES[0]), (LOOKBACKS[-1], HORIZONS[-1], DECILES[-1])]:
        cell = ev[(ev["lb"] == lb) & (ev["h"] == h) & (ev["k"] == k)]
        if cell.empty:
            continue
        g = cell.groupby("day").apply(
            lambda d: pd.Series({"m": float((d["gross_sum"]).sum() / d["n"].sum()), "n": float(d["n"].sum())}),
            include_groups=False)
        r = float(np.corrcoef(g["n"], g["m"])[0, 1])
        n = len(g)
        print(f"\n=== L-1 check: does the number of legs predict what a leg earns? "
              f"(lookback {lb}, hold {h}, k={k}) ===")
        print(f"  corr(legs/session, session mean gross bps) = {r:+.3f} "
              f"at t = {r * np.sqrt((n - 2) / max(1e-9, 1 - r * r)):+.2f} over {n} sessions")
        busy.append({"lb": lb, "hold": h, "k": k, "corr": round(r, 3), "sessions": n})
    if busy:
        pd.DataFrame(busy).to_csv(OUT / "events_busy.csv", index=False)

    # -------------------------------------------------- verdict
    best = gdf[gdf["regime"] != "ALL"]
    winners = {}
    for (lb, h, k), cell in best.groupby(["lb", "hold", "k"]):
        for sign, col, tcol in (("momentum", "net bps", "t net"), ("reversal", "rev net bps", "t rev")):
            passing = int(((cell[col] > 0) & (cell[tcol] > 2.0)).sum())
            if passing >= 2:
                winners[(lb, h, k, sign)] = passing
    print("\n=== X-1 stage 1 verdict (rule fixed before the runs) ===")
    ncells = len(LOOKBACKS) * len(HORIZONS) * len(DECILES)
    print(f"  cells with a NET edge at t > 2 in >= 2 of 3 regimes: {len(winners)} of {2 * ncells} "
          f"({ncells} parameter cells x 2 signs)")
    for (lb, h, k, sign), v in sorted(winners.items()):
        print(f"    lookback {lb}, hold {h}, k={k}, {sign}: {v}/3 regimes")
    if not winners:
        print("  -> no cell survives cost; stage 2 would only be fitting a losing mechanism")
    json.dump({"winners": [{"lb": a, "hold": b, "k": c, "sign": d, "regimes": v}
                           for (a, b, c, d), v in winners.items()]},
              (OUT / "verdict_events.json").open("w", encoding="utf-8"), indent=2)
    return 0


# --------------------------------------------------------------------------------- stage 2
def _bt_job(spec):
    """One (year, variant): the xsect module through the shipped framework."""
    year, variant, overrides = spec
    lo, hi = dt.date(year, 1, 1), min(dt.date(year, 12, 31), LAST_DAY)
    from intraday_common import load_universe
    bars = load_universe(UNIVERSE_X1, lo, hi)
    if not bars:
        return year, variant, None
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("xsect")
    params = {**strat.PARAMS, **VARIANTS[variant]["params"], **(overrides or {})}
    s = ib.run(strat, bars, EQUITY, params, lo, hi, False, feats_all=feats)
    d = s.pop("daily")
    return year, variant, {"daily": d, "trades_per_day": s["trades_per_day"], "costs_per_day": s["costs_per_day"],
                           "turnover_per_day_x": s["turnover_per_day_x"], "stopped_days": s["stopped_days"]}


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


def stage_backtest(workers: int, variants: list[str], overrides: dict | None, record: bool, tag: str) -> int:
    jobs = [(y, v, overrides) for y in YEARS for v in variants]
    print(f"stage 2 (harness): {len(variants)} variants x {len(YEARS)} years, {workers} workers; "
          f"each year is a fresh ${EQUITY:,.0f} book")
    per_year: dict = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for year, variant, out in ex.map(_bt_job, jobs):
            if out is None:
                continue
            per_year.setdefault(variant, {})[year] = out
            print(f"  {year} {variant:<5} {len(out['daily'])} sessions  $/day "
                  f"{out['daily']['pnl'].mean():>9,.0f}  tr/day {out['trades_per_day']:5.1f}", flush=True)
    if not per_year:
        sys.exit("no results")
    OUT.mkdir(parents=True, exist_ok=True)
    verdict = {}
    for v in variants:
        if v not in per_year:
            continue
        d = pd.concat([per_year[v][y]["daily"] for y in sorted(per_year[v])],
                      ignore_index=True).sort_values("day").reset_index(drop=True)
        d.to_csv(OUT / f"daily_{v}.csv", index=False)
        rows, passing = [], 0
        for name, y0, y1 in REGIMES:
            sub = d[(d["day"] >= dt.date(y0, 1, 1)) & (d["day"] <= dt.date(y1, 12, 31))]
            s = stats(sub)
            if not s:
                continue
            passing += s["t"] > 2.0
            rows.append({"regime": name, **{k: round(val, 2) for k, val in s.items()}})
            if record:
                yrs = [y for y in range(y0, y1 + 1) if y in per_year[v]]
                fake = {"sessions": s["sessions"], "net_profit_pct": s["net_pct"], "cagr_pct": s["car_pct"],
                        "sharpe": s["sharpe"], "max_drawdown_pct": s["max_dd_pct"], "avg_daily_pnl": s["$/day"],
                        "worst_day": s["worst_day"],
                        "trades": int(round(np.mean([per_year[v][y]["trades_per_day"] for y in yrs]) * s["sessions"])),
                        "trades_per_day": float(np.mean([per_year[v][y]["trades_per_day"] for y in yrs])),
                        "costs_per_day": float(np.mean([per_year[v][y]["costs_per_day"] for y in yrs])),
                        "stopped_days": sum(per_year[v][y]["stopped_days"] for y in yrs)}
                ib.record("xsect", f"X-1 {v} [{name}] {tag}".strip(), fake,
                          {**VARIANTS[v]["params"], **(overrides or {}), "symbols": len(UNIVERSE_X1)},
                          dt.date(y0, 1, 1), dt.date(y1, 12, 31))
        s_all = stats(d)
        rows.append({"regime": "ALL", **{k: round(val, 2) for k, val in s_all.items()}})
        print(f"\n=== stage 2: xsect {v} ({len(UNIVERSE_X1)} megacaps) {overrides or ''} ===")
        with pd.option_context("display.width", 240):
            print(pd.DataFrame(rows).to_string(index=False))
        tpd = np.mean([per_year[v][y]["trades_per_day"] for y in per_year[v]])
        cpd = np.mean([per_year[v][y]["costs_per_day"] for y in per_year[v]])
        tov = np.mean([per_year[v][y]["turnover_per_day_x"] for y in per_year[v]])
        print(f"  trades/day {tpd:.1f}   costs/day ${cpd:,.0f}   turnover/day {tov:.2f}x equity")
        verdict[v] = {"passing": int(passing), "t": [r.get("t") for r in rows[:-1]]}
    print("\n=== X-1 stage 2 verdict (positive at t > 2 in >= 2 of 3 regimes) ===")
    for v, r in verdict.items():
        print(f"  {v:<5} {r['passing']}/3 regimes   t = {r['t']}   {'PASS' if r['passing'] >= 2 else 'fail'}")
    json.dump(verdict, (OUT / "verdict_backtest.json").open("w", encoding="utf-8"), indent=2, default=str)
    return 0


def main() -> int:
    global YEARS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="events", choices=["events", "backtest"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--symbols", nargs="*", default=UNIVERSE_X1)
    ap.add_argument("--years", nargs="*", type=int, default=YEARS)
    ap.add_argument("--variants", nargs="*", default=list(VARIANTS))
    ap.add_argument("--params", help="JSON overrides for the xsect PARAMS (stage 2)")
    ap.add_argument("--tag", default="")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--from-csv", action="store_true",
                    help="re-aggregate results/x1/events.csv instead of re-reading ten years of bars")
    args = ap.parse_args()
    print(f"store: {DATA_DIR}")
    YEARS = list(args.years)
    if args.stage == "events":
        return stage_events(args.workers, args.symbols, args.from_csv)
    return stage_backtest(args.workers, args.variants,
                          json.loads(args.params) if args.params else None, args.record, args.tag)


if __name__ == "__main__":
    sys.exit(main())
