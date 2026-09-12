#!/usr/bin/env python
"""F-4: the afternoon reversal, measured where the sample can actually resolve it.

    python scripts/sweep_f4.py --stage events   --workers 6                 # stage 1, event study
    python scripts/sweep_f4.py --stage events   --from-csv                  # re-aggregate, no bars
    python scripts/sweep_f4.py --stage backtest --workers 3 --record        # stage 2, full harness

WHY THIS EXISTS
---------------
Two independent samples now point the same way and in both cases the number was filed as a
by-product rather than tested as a mechanism:

  * X-1 (2026-09-10), 2,684 sessions of megacap equities: the cross-sectional momentum edge
    is +0.63 bps entering at 10:30 and **-0.69 bps at t = -2.80** entering at 14:30.
  * F-2a (2026-09-11), 313 sessions of front-month ES: day-momentum into the last 30 minutes
    is **-2.415 bps at t = -2.56**, the only significant statistic in that table, with the
    sign reversed from the premise that was pre-registered for it.

F-4 asks the question directly, on the store with the power: `data/minute_alpaca`, the
56 names of the intraday sleeve's tradable universe (the 50 megacaps plus PLTR/MSTR/COIN/
SMCI/SOXL/SOXS, all disjoint from the daily champion's book), 2016-01-04..2026-09-09.

THE RULE, PRE-REGISTERED BEFORE THE FIRST NUMBER IS COMPUTED
------------------------------------------------------------
(1) **The mechanism.** The signal is the SIGN of the session's return from the open to minute
    T. The trade is entered at the open of bar T+1 (the harness's fill convention) and held to
    the framework's flatten at 15:38 ET. `direction = -1` (reversal) fades that sign;
    `direction = +1` (momentum) is the same experiment with the opposite sign and is reported
    from the same gross column rather than run twice.
(2) **The decision statistic.** Legs inside one session overlap in time and share the market
    factor, so each session is collapsed to ONE number, and that number is the SUM of the legs
    (a book puts the same notional on each), exactly as L-1 and X-1 established. The t is over
    sessions. The reported bps is the accumulated session sum divided by the number of legs,
    i.e. the edge per dollar deployed.
(3) **The pass mark, identical to every A-track and X-track candidate.** The cell must be
    positive NET of the real cost model at **t > 2 in at least two of the three regimes**
    (2016-2019, 2020-2023, 2024-2026). Nothing else is a pass, and nothing is deployed on a
    pooled number alone.
(4) **Two books, and only the first is the pre-registered one.** `raw` is the directional book
    the backlog specifies: each name's own sign, each name's own return. `neutral` is the
    dollar-neutral version (signal and return both demeaned against the equal-weight basket),
    carried as a LABELLED DIAGNOSTIC so that a surviving raw edge can be split into "the market
    reverses in the afternoon" and "the names that ran revert against their peers". A pass on
    `neutral` alone is not a pass on F-4.
(5) **The expected outcome is written down first: failure on COST, not on sign.** X-1's own
    +0.36 bps of afternoon reversal against a 4.70 bps round trip predicts it. If that is what
    happens, F-4 is not a strategy - it is the **third** measurement of an effect whose only
    viable instrument is the one F-2a priced at a **0.488 bps round trip**, and it is an
    argument for buying CME history rather than for a twelfth equity lever.
(6) **The prior that must not be hidden.** A-10 already killed the deployed form of this trade:
    `late_momo` with `direction=-1` at 15:00, on the 16-name sleeve with a 60 bps magnitude
    filter and six names, lost **-$468/day at t = -7.38** over 2,686 of these same sessions and
    was set to alloc 0.0. F-4 differs in breadth (56 names, no magnitude filter) and in that it
    grids the entry time rather than assuming 15:00. If F-4 also fails, that is a confirmation
    and the entry says so; it is not a new refusal.
(7) **Nothing here is promotable without stage 2.** A stage 1 survivor earns a run through the
    shipped framework (`intraday_backtest`, the deployed risk limits, the real per-share
    commission and the sell-side regulatory fees) and must clear (3) again there.

Cost model is `sweep_x1._cost_bps`: two slippage charges, two per-share commissions on the REAL
(split-unadjusted) share count, and the sell-side SEC/TAF fees exactly once - a round trip has
exactly one sale whichever way the leg points.
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
from intraday_common import (DAILY_SLEEVE_UNIVERSE, DATA_DIR, REPO,  # noqa: E402
                             UNIVERSE, parquet_path, share_scale)
# The event-study primitives are X-1's and are reused unchanged so the two studies stay
# comparable leg for leg: the same (day, minute) panel loader, the same cost formula, the same
# session-clustered t. _panel_job's module constants (LAST_DAY 2026-09-09, 390 bars) are the
# ones X-1 ran on and are what the worker processes re-import.
from sweep_x1 import _cluster_t, _cost_bps, _panel_job  # noqa: E402

EQUITY = 1_000_000.0
OUT = REPO / "results" / "f4"
YEARS = list(range(2016, 2027))
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]

#: Alpaca spells Berkshire's B share with a dot; fetch_data keeps the Yahoo spelling.
_CANDIDATES = [s.replace("-", ".") for s in MEGACAPS] + list(UNIVERSE)
#: The sleeve's tradable breadth: everything the store holds that the daily champion does not
#: trade (AGENTS.md disjointness rule), de-duplicated and ordered.
UNIVERSE_F4 = sorted({s for s in _CANDIDATES
                      if s not in DAILY_SLEEVE_UNIVERSE and parquet_path(s).exists()})

BARS_PER_SESSION = 390
FLATTEN_MINUTE = 368             # framework constant: the sleeve is flat from 15:38
#: entry minutes, 10:00 .. 15:30 every half hour. 30 is X-1's first entry and 360 is the last
#: point that still leaves a tradable hold before the flatten.
ENTRIES = list(range(30, 361, 30))
#: exit conventions. `flatten` is what this sleeve can actually do; `close` is F-2a's convention
#: (the last bar's close) and is carried as a labelled diagnostic only - the sleeve cannot hold
#: past 15:38 without colliding with the daily rebalance at 15:45.
EXITS = ["flatten", "close"]
BOOKS = ["raw", "neutral"]
MIN_NAMES = 20                   # refuse to score a session thinner than this

#: stage 2 runs the mechanism through the SHIPPED `late_momo` module, which already implements
#: exactly this trade (`direction=-1` fades the day's move into the flatten). Nothing in
#: algorithms/ or scripts/intraday_*.py is modified, so AGENTS.md rule (a) owes no replay.
#: `min_move` 0 and a wide `max_names` are what turn A-10's six-name filtered version into
#: F-4's breadth version; `weight` is set so 56 names sit at the framework's gross cap.
STAGE2_BASE = {"direction": -1, "min_move": 0.0, "max_names": len(UNIVERSE_F4)}


# --------------------------------------------------------------------------------- stage 1
def _events_year(year: int, symbols: list[str], workers: int) -> pd.DataFrame:
    """All (day, entry, exit, book) event aggregates for one calendar year."""
    panels = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for sym, days, o, c in ex.map(_panel_job, [(year, s) for s in symbols]):
            if days is not None:
                panels[sym] = (days, o, c)
    if len(panels) < MIN_NAMES:
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

    rows = []
    for m in ENTRIES:
        sig = C[:, m, :] / O[:, 0, :] - 1.0          # session return, open -> minute m
        px_in = O[:, m + 1, :]
        for exit_name in EXITS:
            px_out = O[:, FLATTEN_MINUTE, :] if exit_name == "flatten" else C[:, -1, :]
            fwd = px_out / px_in - 1.0
            ok = np.isfinite(sig) & np.isfinite(fwd) & (px_in > 0) & (sig != 0.0)
            nvalid = ok.sum(axis=1)
            enough = nvalid >= MIN_NAMES
            if not enough.any():
                continue
            basket_sig = np.nanmean(np.where(ok, sig, np.nan), axis=1, keepdims=True)
            basket_fwd = np.nanmean(np.where(ok, fwd, np.nan), axis=1, keepdims=True)
            for book in BOOKS:
                s_use = sig if book == "raw" else sig - basket_sig
                f_use = fwd if book == "raw" else fwd - basket_fwd
                take = ok & enough[:, None] & (s_use != 0.0)
                if not take.any():
                    continue
                # direction = +1 (momentum) is stored; the reversal is its negation, and both
                # are charged the same cost, so only one column is ever computed.
                side = np.sign(np.where(take, s_use, 0.0))
                r = np.where(take, side * f_use * 1e4, 0.0)
                drift = np.where(take, f_use * 1e4, 0.0)
                cost = np.where(take, _cost_bps(px_in * scale), 0.0)
                n = take.sum(axis=1)
                rows.append(pd.DataFrame({
                    "day": all_days, "entry": m, "exit": exit_name, "book": book,
                    "n": n, "gross_sum": np.nansum(r, axis=1),
                    "cost_sum": np.nansum(cost, axis=1),
                    "drift_sum": np.nansum(drift, axis=1),
                    "side_sum": side.sum(axis=1),
                    "hit": ((r > 0) & take).sum(axis=1)})[n > 0])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


#: F-2a's measured ES round trip, in basis points of notional (half-tick book, $2.05 a side on
#: $347,117 of contract notional). `--cost-bps` substitutes it for the equity cost column so the
#: SAME legs can be re-scored on the cheap instrument. This is a counterfactual on the cost only:
#: it assumes the index future carries the same cross-sectional signal, which it does not, so it
#: is an UPPER bound on what the mechanism could be worth there and is labelled as one.
FUTURES_ROUND_TRIP_BPS = 0.488


def _cell(tot: pd.DataFrame) -> dict:
    """One row of the grid from a per-session aggregate frame."""
    legs = float(tot["n"].sum())
    _, g_t, n_days = _cluster_t(tot["gross"])
    _, m_t, _ = _cluster_t(tot["gross"] - tot["cost"])           # momentum, net
    _, r_t, _ = _cluster_t(-tot["gross"] - tot["cost"])          # reversal, net
    _, d_t, _ = _cluster_t(tot["drift"])
    return {"sessions": n_days, "legs": int(legs), "legs/day": round(legs / max(1, n_days), 1),
            "gross bps": round(tot["gross"].sum() / legs, 2), "t gross": round(g_t, 2),
            "cost bps": round(tot["cost"].sum() / legs, 2),
            "momo net bps": round((tot["gross"].sum() - tot["cost"].sum()) / legs, 2),
            "t momo": round(m_t, 2),
            "rev net bps": round((-tot["gross"].sum() - tot["cost"].sum()) / legs, 2),
            "t rev": round(r_t, 2),
            "hit %": round(100.0 * tot["hit"].sum() / legs, 1),
            "[diag] drift bps": round(tot["drift"].sum() / legs, 2), "[diag] t drift": round(d_t, 2),
            "[diag] breadth": round(float(tot["side"].sum() / legs), 3)}


def _agg(cell: pd.DataFrame) -> pd.DataFrame:
    return cell.groupby("day").agg(gross=("gross_sum", "sum"), cost=("cost_sum", "sum"),
                                   drift=("drift_sum", "sum"), side=("side_sum", "sum"),
                                   n=("n", "sum"), hit=("hit", "sum"))


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
    print(f"  {len(ev):,} (day, cell) rows, {int(ev['n'].sum()):,} legs, {ev['day'].nunique():,} sessions")

    grid = []
    for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
        sub = ev[(ev["day"] >= dt.date(y0, 1, 1)) & (ev["day"] <= dt.date(y1, 12, 31))]
        for book in BOOKS:
            for exit_name in EXITS:
                for m in ENTRIES:
                    cell = sub[(sub["book"] == book) & (sub["exit"] == exit_name) & (sub["entry"] == m)]
                    if cell.empty:
                        continue
                    grid.append({"regime": name, "book": book, "exit": exit_name, "entry": m,
                                 "clock": f"{9 + (30 + m) // 60}:{(30 + m) % 60:02d}", **_cell(_agg(cell))})
    gdf = pd.DataFrame(grid)
    gdf.to_csv(OUT / "events_grid.csv", index=False)

    for book in BOOKS:
        label = ("PRE-REGISTERED directional book" if book == "raw"
                 else "[DIAGNOSTIC] dollar-neutral book (signal and return demeaned)")
        for exit_name in EXITS:
            ex_label = ("exit 15:38 flatten, what the sleeve can trade" if exit_name == "flatten"
                        else "[DIAGNOSTIC] exit at the closing bar, F-2a's convention")
            t = gdf[(gdf["book"] == book) & (gdf["exit"] == exit_name) & (gdf["regime"] == "ALL")]
            if t.empty:
                continue
            print(f"\n=== stage 1 ALL 2016-2026: {label}; {ex_label} ===")
            print("  gross > 0 = the day's move extends; 'rev net' is the fade sign net of the same cost")
            with pd.option_context("display.width", 260):
                print(t.drop(columns=["regime", "book", "exit"]).to_string(index=False))

    # the pre-registered cell, regime by regime
    for book in BOOKS:
        t = gdf[(gdf["book"] == book) & (gdf["exit"] == "flatten") & (gdf["regime"] != "ALL")]
        if t.empty:
            continue
        print(f"\n=== stage 1 by regime: {book} book, exit at the flatten ===")
        with pd.option_context("display.width", 260):
            print(t[["regime", "entry", "clock", "sessions", "legs", "gross bps", "t gross",
                     "cost bps", "rev net bps", "t rev", "momo net bps", "t momo"]].to_string(index=False))

    # -------------------------------------------------- verdict, rule (3) above
    per_regime = gdf[gdf["regime"] != "ALL"]
    winners, gross_only = {}, {}
    for (book, exit_name, m), cell in per_regime.groupby(["book", "exit", "entry"]):
        for sign, col, tcol in (("momentum", "momo net bps", "t momo"), ("reversal", "rev net bps", "t rev")):
            if int(((cell[col] > 0) & (cell[tcol] > 2.0)).sum()) >= 2:
                winners[(book, exit_name, m, sign)] = int(((cell[col] > 0) & (cell[tcol] > 2.0)).sum())
        # the gross column, to separate "no effect" from "an effect smaller than its cost"
        g = cell["gross bps"] * (-1.0)
        if int(((g > 0) & (cell["t gross"] < -2.0)).sum()) >= 2:
            gross_only[(book, exit_name, m)] = int(((g > 0) & (cell["t gross"] < -2.0)).sum())

    ncells = len(BOOKS) * len(EXITS) * len(ENTRIES)
    print("\n=== F-4 stage 1 verdict (rule pre-registered in the docstring, before the runs) ===")
    print(f"  NET edge at t > 2 in >= 2 of 3 regimes: {len(winners)} of {2 * ncells} "
          f"({ncells} cells x 2 signs)")
    for (b, e, m, sign), v in sorted(winners.items()):
        print(f"    {b:<7} exit {e:<7} entry {m:>3} ({sign}): {v}/3 regimes")
    print(f"  GROSS reversal at t < -2 in >= 2 of 3 regimes (effect present but maybe unaffordable): "
          f"{len(gross_only)} of {ncells}")
    for (b, e, m), v in sorted(gross_only.items()):
        print(f"    {b:<7} exit {e:<7} entry {m:>3}: {v}/3 regimes")
    if not winners:
        print("  -> no cell clears cost; clause (5) applies and stage 2 would only be fitting a losing book")
    cheap = _cost_floor_counterfactual(ev)
    json.dump({"net_winners": [{"book": a, "exit": b, "entry": c, "sign": d, "regimes": v}
                               for (a, b, c, d), v in winners.items()],
               "gross_reversal": [{"book": a, "exit": b, "entry": c, "regimes": v}
                                  for (a, b, c), v in gross_only.items()],
               "at_futures_cost": cheap},
              (OUT / "verdict_events.json").open("w", encoding="utf-8"), indent=2)
    return 0


def _cost_floor_counterfactual(ev: pd.DataFrame) -> dict:
    """Re-score the SAME legs at F-2a's 0.488 bps round trip instead of the equity cost model.

    F-2a closed with the claim that an effect refused on cost in equities is an argument for
    buying CME history, because the instrument is 10x-17x cheaper. That claim is testable here
    without any new data: hold the measured gross column fixed, swap the cost column, and ask
    whether the pre-registered pass mark is reached. It is an UPPER bound - the future carries
    one price, not 56, so it cannot express the cross-sectional book at all and can only express
    the raw one at the market's own (much smaller) dispersion.
    """
    rows = []
    for book in BOOKS:
        for m in ENTRIES:
            cell_all = ev[(ev["book"] == book) & (ev["exit"] == "flatten") & (ev["entry"] == m)]
            if cell_all.empty:
                continue
            passing = 0
            for name, y0, y1 in REGIMES:
                sub = cell_all[(cell_all["day"] >= dt.date(y0, 1, 1)) & (cell_all["day"] <= dt.date(y1, 12, 31))]
                if sub.empty:
                    continue
                tot = _agg(sub)
                net = -tot["gross"] - tot["n"] * FUTURES_ROUND_TRIP_BPS
                mean, t, _ = _cluster_t(net)
                passing += (mean > 0) and (t > 2.0)
            tot = _agg(cell_all)
            legs = float(tot["n"].sum())
            net = -tot["gross"] - tot["n"] * FUTURES_ROUND_TRIP_BPS
            _, t_all, _ = _cluster_t(net)
            rows.append({"book": book, "entry": m, "clock": f"{9 + (30 + m) // 60}:{(30 + m) % 60:02d}",
                         "rev net bps @0.488": round(float(net.sum()) / legs, 2),
                         "t rev": round(t_all, 2), "regimes passing": int(passing)})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "events_futures_cost.csv", index=False)
    print(f"\n=== F-4 counterfactual: the SAME legs charged F-2a's ES round trip "
          f"({FUTURES_ROUND_TRIP_BPS} bps) instead of {ev['cost_sum'].sum() / ev['n'].sum():.2f} ===")
    print("  UPPER BOUND ONLY: one future cannot carry a 56-name cross-section. Reversal sign, exit at the flatten.")
    with pd.option_context("display.width", 200):
        print(df.to_string(index=False))
    n_pass = int((df["regimes passing"] >= 2).sum())
    print(f"  cells reaching the pre-registered mark on the cheap instrument: {n_pass} of {len(df)}")
    return {"n_pass": n_pass, "n_cells": len(df),
            "best": df.sort_values("t rev", ascending=False).head(1).to_dict("records")}


# --------------------------------------------------------------------------------- stage 2
def _bt_job(spec):
    """One (year, entry minute): the SHIPPED late_momo module through the shipped framework."""
    year, entry, weight, overrides = spec
    lo, hi = dt.date(year, 1, 1), min(dt.date(year, 12, 31), dt.date(2026, 9, 9))
    from intraday_common import load_universe
    bars = load_universe(UNIVERSE_F4, lo, hi)
    if not bars:
        return year, entry, None
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("late_momo")
    params = {**strat.PARAMS, **STAGE2_BASE, "entry_minute": entry, "weight": weight,
              **(overrides or {})}
    s = ib.run(strat, bars, EQUITY, params, lo, hi, False, feats_all=feats)
    d = s.pop("daily")
    return year, entry, {"daily": d, "trades_per_day": s["trades_per_day"],
                         "costs_per_day": s["costs_per_day"],
                         "turnover_per_day_x": s["turnover_per_day_x"],
                         "stopped_days": s["stopped_days"]}


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


def stage_backtest(workers: int, entries: list[int], weight: float, overrides: dict | None,
                   record: bool, tag: str) -> int:
    jobs = [(y, m, weight, overrides) for y in YEARS for m in entries]
    print(f"stage 2 (shipped harness, late_momo direction=-1): {len(entries)} entry minutes x "
          f"{len(YEARS)} years, {workers} workers; each year is a fresh ${EQUITY:,.0f} book")
    print(f"  params: {STAGE2_BASE} weight={weight} ({len(UNIVERSE_F4)} names)")
    per_entry: dict = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for year, entry, out in ex.map(_bt_job, jobs):
            if out is None:
                continue
            per_entry.setdefault(entry, {})[year] = out
            print(f"  {year} entry {entry:>3}  {len(out['daily'])} sessions  $/day "
                  f"{out['daily']['pnl'].mean():>9,.0f}  tr/day {out['trades_per_day']:5.1f}", flush=True)
    if not per_entry:
        sys.exit("no results")
    OUT.mkdir(parents=True, exist_ok=True)
    verdict = {}
    for m in entries:
        if m not in per_entry:
            continue
        d = pd.concat([per_entry[m][y]["daily"] for y in sorted(per_entry[m])],
                      ignore_index=True).sort_values("day").reset_index(drop=True)
        d.to_csv(OUT / f"daily_entry{m}.csv", index=False)
        rows, passing = [], 0
        for name, y0, y1 in REGIMES:
            sub = d[(d["day"] >= dt.date(y0, 1, 1)) & (d["day"] <= dt.date(y1, 12, 31))]
            s = stats(sub)
            if not s:
                continue
            passing += s["t"] > 2.0
            rows.append({"regime": name, **{k: round(v, 2) for k, v in s.items()}})
            if record:
                yrs = [y for y in range(y0, y1 + 1) if y in per_entry[m]]
                fake = {"sessions": s["sessions"], "net_profit_pct": s["net_pct"], "cagr_pct": s["car_pct"],
                        "sharpe": s["sharpe"], "max_drawdown_pct": s["max_dd_pct"],
                        "avg_daily_pnl": s["$/day"], "worst_day": s["worst_day"],
                        "trades": int(round(np.mean([per_entry[m][y]["trades_per_day"] for y in yrs]) * s["sessions"])),
                        "trades_per_day": float(np.mean([per_entry[m][y]["trades_per_day"] for y in yrs])),
                        "costs_per_day": float(np.mean([per_entry[m][y]["costs_per_day"] for y in yrs])),
                        "stopped_days": sum(per_entry[m][y]["stopped_days"] for y in yrs)}
                ib.record("late_momo", f"F-4 reversal entry {m} [{name}] {tag}".strip(), fake,
                          {**STAGE2_BASE, "entry_minute": m, "weight": weight,
                           "symbols": len(UNIVERSE_F4)}, dt.date(y0, 1, 1), dt.date(y1, 12, 31))
        rows.append({"regime": "ALL", **{k: round(v, 2) for k, v in stats(d).items()}})
        print(f"\n=== stage 2: reversal, entry {m} ({len(UNIVERSE_F4)} names) {overrides or ''} ===")
        with pd.option_context("display.width", 260):
            print(pd.DataFrame(rows).to_string(index=False))
        tpd = np.mean([per_entry[m][y]["trades_per_day"] for y in per_entry[m]])
        cpd = np.mean([per_entry[m][y]["costs_per_day"] for y in per_entry[m]])
        tov = np.mean([per_entry[m][y]["turnover_per_day_x"] for y in per_entry[m]])
        print(f"  trades/day {tpd:.1f}   costs/day ${cpd:,.0f}   turnover/day {tov:.2f}x equity")
        verdict[m] = {"passing": int(passing), "t": [r.get("t") for r in rows[:-1]]}
    print("\n=== F-4 stage 2 verdict (positive at t > 2 in >= 2 of 3 regimes) ===")
    for m, r in verdict.items():
        print(f"  entry {m:>3}  {r['passing']}/3 regimes   t = {r['t']}   {'PASS' if r['passing'] >= 2 else 'fail'}")
    json.dump(verdict, (OUT / "verdict_backtest.json").open("w", encoding="utf-8"), indent=2, default=str)
    return 0


def main() -> int:
    global YEARS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="events", choices=["events", "backtest"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--symbols", nargs="*", default=UNIVERSE_F4)
    ap.add_argument("--years", nargs="*", type=int, default=YEARS)
    ap.add_argument("--entries", nargs="*", type=int, default=[300, 330],
                    help="stage 2 entry minutes (default 14:30 and 15:00, X-1's and A-10's)")
    ap.add_argument("--weight", type=float, default=round(1.5 / max(1, len(UNIVERSE_F4)), 4),
                    help="per-name weight; default puts the full universe at the sleeve's gross cap")
    ap.add_argument("--params", help="JSON overrides for the late_momo PARAMS (stage 2)")
    ap.add_argument("--tag", default="")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--from-csv", action="store_true",
                    help="re-aggregate results/f4/events.csv instead of re-reading eleven years of bars")
    args = ap.parse_args()
    print(f"store: {DATA_DIR}")
    print(f"universe: {len(UNIVERSE_F4)} names, disjoint from the daily sleeve")
    YEARS = list(args.years)
    if args.stage == "events":
        return stage_events(args.workers, args.symbols, args.from_csv)
    return stage_backtest(args.workers, args.entries, args.weight,
                          json.loads(args.params) if args.params else None, args.record, args.tag)


if __name__ == "__main__":
    sys.exit(main())
