#!/usr/bin/env python
"""L-1: does an intraday VWAP stretch on a 3x leveraged ETF revert enough to pay for itself?

    python scripts/sweep_l1.py --stage events   --workers 6            # stage 1, cost-free
    python scripts/sweep_l1.py --stage backtest --workers 6 --record   # stage 2, full harness

Why two stages
--------------
Every A-track false positive came from fitting a strategy on one window and reading its P&L. So
the mechanism is measured first, with no strategy and no parameters to fit: an **event study** on
the raw bars. For every bar where the deviation from session VWAP exceeds `z` of the name's own
14-bar ATR, buy the cheap side at the NEXT bar's open (the harness's own fill convention) and
unwind `h` bars later at that bar's open. The average of those returns, in basis points, is the
gross edge; the modelled round-trip cost is charged per event from the real (split-unadjusted)
share price, so "reverts" and "pays" are separated. Only if some cell clears cost does stage 2
run the actual strategy through `scripts/intraday_backtest.py`'s framework.

Statistics. Events overlap in time and the universe is three *inverse pairs* - TQQQ above VWAP and
SQQQ below VWAP are the same bet - so a naive t on ~1e6 events is meaningless. Events are drawn
non-overlapping per (symbol, session) and aggregated per session, which clusters both the
within-day overlap and the cross-symbol duplication into one number per day.

**How the session is aggregated decides the sign, so it is the whole methodology.** A book puts the
same notional on every event, so its daily P&L is the *sum* of that session's event returns, not
their average: the decision statistic here is therefore the per-session SUM (`bps.events`), and the
edge per dollar risked is that sum divided by the event count over the whole sample. The other
reading - average the events within a session, then average the sessions - gives every session one
vote no matter how much capital it employed, and on this universe it inverts the verdict
(+13.32 bps against -1.68 at z >= 12, hold 30) because the fade earns on quiet sessions with two
signals and loses on violent sessions with twenty-five. It is printed as a diagnostic, labelled,
next to the correlation that explains it, and it decides nothing.

Regimes are A-10's, chosen a priori: 2016-2019, 2020-2023, 2024-2026. Decision rule, fixed before
the runs (backlog L-1, owner instruction 2026-09-10): a cell is only interesting if the NET edge is
positive at t > 2 in at least two of the three regimes; nothing is deployed otherwise.
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
from intraday_common import (COMMISSION_PER_SHARE, DATA_DIR, LEVERAGED_DEPLOYABLE,  # noqa: E402
                             LEVERAGED_UNIVERSE, REPO, SEC_FEE_RATE, SLIPPAGE_BPS, TAF_PER_SHARE,
                             load_universe, share_scale)

EQUITY = 1_000_000.0
OUT = REPO / "results" / "l1"
YEARS = list(range(2016, 2027))
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]
#: the store is refreshed intraday, so the current session is partial and never enters a study
LAST_DAY = dt.date(2026, 9, 9)

#: event-study grid: stretch thresholds in ATR units and holding horizons in minutes
ZS = [3.0, 5.0, 8.0, 12.0]
HORIZONS = [5, 15, 30, 60]
ENTRY_FROM, ENTRY_TO = 20, 340       # same entry window as the strategy module
FLATTEN_MINUTE = 368

#: stage 2 variants: the strategy on the 6-name universe and on the 3 deployable names, plus the
#: continuation control (direction +1) that says whether any P&L is reversion or just trend.
VARIANTS = {
    "fade6": {"symbols": LEVERAGED_UNIVERSE, "params": {}},
    "fade3": {"symbols": LEVERAGED_DEPLOYABLE, "params": {}},
    "cont6": {"symbols": LEVERAGED_UNIVERSE, "params": {"direction": 1}},
}


# --------------------------------------------------------------------------------- stage 1
def _cost_bps(real_px: float) -> float:
    """Modelled round-trip cost of one event, in basis points of notional.

    Two slippage charges, two per-share commissions, and the sell-side regulatory fees exactly
    once (a round trip has one sale whichever way round it is). `real_px` is the unadjusted share
    price, because IBKR charges per share at the price that was really quoted.
    """
    comm = COMMISSION_PER_SHARE / real_px * 1e4
    sell = SEC_FEE_RATE * 1e4 + TAF_PER_SHARE / real_px * 1e4
    return 2 * SLIPPAGE_BPS + 2 * comm + sell


def _events_job(spec):
    """One (year, symbol): non-overlapping fade events per (z, horizon), aggregated per session."""
    year, sym = spec
    lo = dt.date(year, 1, 1)
    hi = min(dt.date(year, 12, 31), LAST_DAY)
    bars = load_universe([sym], lo, hi)
    if not bars:
        return []
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    f = features(bars[sym])
    rows = []
    for day, g in f.groupby("day", sort=True):
        c = g["c"].to_numpy(float)
        o = g["o"].to_numpy(float)
        vwap = g["vwap"].to_numpy(float)
        atr = g["atr14"].to_numpy(float)
        minute = g["minute"].to_numpy(int)
        n = len(c)
        if n < 60:
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            scale = atr / c
            z = (c / vwap - 1.0) / scale
        f_split = share_scale(sym, day)
        ok = np.isfinite(z) & (minute >= ENTRY_FROM) & (minute <= ENTRY_TO)
        for zt in ZS:
            fire = ok & (np.abs(z) >= zt)
            if not fire.any():
                continue
            for h in HORIZONS:
                last = -1
                gross, cost, hits, notion = [], [], 0, []
                for i in np.flatnonzero(fire):
                    if i <= last or i + 1 + h >= n:
                        continue
                    if minute[i + 1 + h] >= FLATTEN_MINUTE:
                        continue
                    px_in, px_out = o[i + 1], o[i + 1 + h]
                    if not (px_in > 0 and px_out > 0):
                        continue
                    r = -np.sign(z[i]) * (px_out / px_in - 1.0) * 1e4
                    gross.append(r)
                    cost.append(_cost_bps(px_in * f_split))
                    hits += r > 0
                    notion.append(px_in * f_split)
                    last = i + h            # non-overlapping
                if gross:
                    rows.append({"day": day, "sym": sym, "z": zt, "h": h, "n": len(gross),
                                 "gross_bps": float(np.mean(gross)), "cost_bps": float(np.mean(cost)),
                                 "hit_pct": 100.0 * hits / len(gross),
                                 "real_px": float(np.mean(notion))})
    return rows


def _cluster_t(per_session: pd.Series) -> tuple[float, float, int]:
    """mean, t and N over session-level averages (the clustering unit)."""
    x = per_session.dropna().to_numpy(float)
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
        jobs = [(y, s) for y in YEARS for s in symbols]
        print(f"stage 1 (event study): {len(symbols)} symbols x {len(YEARS)} years, {workers} workers")
        rows = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for out in ex.map(_events_job, jobs):
                rows += out
        if not rows:
            sys.exit("no events")
        ev = pd.DataFrame(rows)
        ev.to_csv(OUT / "events.csv", index=False)
    ev["net_bps"] = ev["gross_bps"] - ev["cost_bps"]
    print(f"  {len(ev):,} (day, symbol, z, horizon) cells, {ev['n'].sum():,} events, "
          f"{ev['day'].nunique():,} sessions")

    # -------------------------------------------------- grid: regime x z x horizon
    grid = []
    for name, y0, y1 in REGIMES + [("ALL", 2016, 2026)]:
        sub = ev[(ev["day"] >= dt.date(y0, 1, 1)) & (ev["day"] <= dt.date(y1, 12, 31))]
        for zt in ZS:
            for h in HORIZONS:
                cell = sub[(sub["z"] == zt) & (sub["h"] == h)]
                if cell.empty:
                    continue
                # DECISION statistic: a fixed notional per event, so the session earns the SUM
                tot = cell.groupby("day").apply(
                    lambda d: pd.Series({"gross": float((d["n"] * d["gross_bps"]).sum()),
                                         "net": float((d["n"] * d["net_bps"]).sum()),
                                         "n": float(d["n"].sum())}), include_groups=False)
                _, g_t, n_days = _cluster_t(tot["gross"])
                _, n_t, _ = _cluster_t(tot["net"])
                events = float(cell["n"].sum())
                # DIAGNOSTIC only: one vote per session regardless of capital employed
                w = cell.groupby("day").apply(
                    lambda d: pd.Series({"gross": np.average(d["gross_bps"], weights=d["n"]),
                                         "hit": np.average(d["hit_pct"], weights=d["n"])}),
                    include_groups=False)
                grid.append({"regime": name, "z": zt, "hold": h, "events": int(events),
                             "sessions": n_days, "ev/day": round(events / max(1, n_days), 1),
                             "gross bps": round(tot["gross"].sum() / events, 2), "t gross": round(g_t, 2),
                             "cost bps": round(float(np.average(cell["cost_bps"], weights=cell["n"])), 2),
                             "net bps": round(tot["net"].sum() / events, 2), "t net": round(n_t, 2),
                             "hit %": round(float(w["hit"].mean()), 1),
                             "[diag] session-equal gross bps": round(float(w["gross"].mean()), 2)})
    gdf = pd.DataFrame(grid)
    gdf.to_csv(OUT / "events_grid.csv", index=False)
    for name, _, _ in REGIMES + [("ALL", 0, 0)]:
        t = gdf[gdf["regime"] == name]
        if t.empty:
            continue
        print(f"\n=== stage 1: fade a VWAP stretch, {name} ===")
        with pd.option_context("display.width", 220):
            print(t.drop(columns=["regime"]).to_string(index=False))

    # -------------------------------------------------- per symbol, at the ALL level
    per_sym = []
    for sym, cell_all in ev.groupby("sym"):
        for zt in [ZS[1], ZS[2]]:
            for h in [HORIZONS[1], HORIZONS[2]]:
                cell = cell_all[(cell_all["z"] == zt) & (cell_all["h"] == h)]
                if cell.empty:
                    continue
                tot = cell.groupby("day").apply(lambda d: float((d["n"] * d["net_bps"]).sum()),
                                                include_groups=False)
                _, t, n = _cluster_t(tot)
                per_sym.append({"sym": sym, "z": zt, "hold": h, "events": int(cell["n"].sum()),
                                "sessions": n, "net bps": round(tot.sum() / cell["n"].sum(), 2),
                                "t": round(t, 2),
                                "mean real px": round(float(cell["real_px"].mean()), 2),
                                "cost bps": round(float(cell["cost_bps"].mean()), 2)})
    psdf = pd.DataFrame(per_sym).sort_values(["z", "hold", "sym"])
    psdf.to_csv(OUT / "events_per_symbol.csv", index=False)
    print("\n=== stage 1: per symbol (2016-2026, net of modelled cost) ===")
    with pd.option_context("display.width", 220):
        print(psdf.to_string(index=False))

    # -------------------------------------------------- why the two weightings disagree
    busy = []
    for zt, h in [(8.0, 30), (12.0, 30), (12.0, 60)]:
        cell = ev[(ev["z"] == zt) & (ev["h"] == h)]
        if cell.empty:
            continue
        g = cell.groupby("day").apply(
            lambda d: pd.Series({"m": np.average(d["gross_bps"], weights=d["n"]), "n": d["n"].sum()}),
            include_groups=False)
        r = float(np.corrcoef(g["n"], g["m"])[0, 1])
        n = len(g)
        q = g.assign(q=pd.qcut(g["n"], 4, labels=["Q1 fewest", "Q2", "Q3", "Q4 most"])).groupby(
            "q", observed=True).agg(sessions=("m", "size"), ev_per_session=("n", "mean"),
                                    gross_bps=("m", "mean"))
        print(f"\n=== how busy the session was vs what the fade earned, z >= {zt}, hold {h} ===")
        print(f"  corr(events/session, session mean gross bps) = {r:+.3f} "
              f"at t = {r * np.sqrt((n - 2) / max(1e-9, 1 - r * r)):+.2f} over {n} sessions")
        print(q.round(2).to_string())
        busy.append({"z": zt, "hold": h, "corr": round(r, 3), "sessions": n})
    pd.DataFrame(busy).to_csv(OUT / "events_busy.csv", index=False)

    # -------------------------------------------------- verdict
    best = gdf[gdf["regime"] != "ALL"]
    winners = {}
    for (zt, h), cell in best.groupby(["z", "hold"]):
        passing = int((cell["t net"] > 2.0).sum())
        if passing >= 2:
            winners[(zt, h)] = passing
    print("\n=== L-1 stage 1 verdict (rule fixed before the runs) ===")
    print(f"  cells with NET edge at t > 2 in >= 2 of 3 regimes: {len(winners)} of {len(ZS) * len(HORIZONS)}")
    for (zt, h), k in sorted(winners.items()):
        print(f"    z >= {zt}, hold {h} bars: {k}/3 regimes")
    if not winners:
        print("  -> no cell survives cost; stage 2 would only be fitting a losing mechanism")
    json.dump({"winners": [{"z": k[0], "hold": k[1], "regimes": v} for k, v in winners.items()]},
              (OUT / "verdict_events.json").open("w", encoding="utf-8"), indent=2)
    return 0


# --------------------------------------------------------------------------------- stage 2
def _bt_job(spec):
    """One (year, variant): the lev_revert module through the shipped framework."""
    year, variant, overrides = spec
    lo, hi = dt.date(year, 1, 1), min(dt.date(year, 12, 31), LAST_DAY)
    v = VARIANTS[variant]
    bars = load_universe(v["symbols"], lo, hi)
    if not bars:
        return year, variant, None
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("lev_revert")
    params = {**strat.PARAMS, **v["params"], **(overrides or {})}
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
            print(f"  {year} {variant:<6} {len(out['daily'])} sessions  $/day "
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
                ib.record("lev_revert", f"L-1 {v} [{name}] {tag}".strip(), fake,
                          {**VARIANTS[v]["params"], **(overrides or {}), "symbols": VARIANTS[v]["symbols"]},
                          dt.date(y0, 1, 1), dt.date(y1, 12, 31))
        s_all = stats(d)
        rows.append({"regime": "ALL", **{k: round(val, 2) for k, val in s_all.items()}})
        print(f"\n=== stage 2: lev_revert {v} ({', '.join(VARIANTS[v]['symbols'])}) "
              f"{overrides or ''} ===")
        with pd.option_context("display.width", 220):
            print(pd.DataFrame(rows).to_string(index=False))
        tpd = np.mean([per_year[v][y]["trades_per_day"] for y in per_year[v]])
        cpd = np.mean([per_year[v][y]["costs_per_day"] for y in per_year[v]])
        tov = np.mean([per_year[v][y]["turnover_per_day_x"] for y in per_year[v]])
        print(f"  trades/day {tpd:.1f}   costs/day ${cpd:,.0f}   turnover/day {tov:.2f}x equity")
        verdict[v] = {"passing": int(passing), "t": [r.get("t") for r in rows[:-1]]}
    print("\n=== L-1 stage 2 verdict (positive at t > 2 in >= 2 of 3 regimes) ===")
    for v, r in verdict.items():
        print(f"  {v:<6} {r['passing']}/3 regimes   t = {r['t']}   {'PASS' if r['passing'] >= 2 else 'fail'}")
    json.dump(verdict, (OUT / "verdict_backtest.json").open("w", encoding="utf-8"), indent=2, default=str)
    return 0


def main() -> int:
    global YEARS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="events", choices=["events", "backtest"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--symbols", nargs="*", default=LEVERAGED_UNIVERSE)
    ap.add_argument("--years", nargs="*", type=int, default=YEARS)
    ap.add_argument("--variants", nargs="*", default=list(VARIANTS))
    ap.add_argument("--params", help="JSON overrides for the lev_revert PARAMS (stage 2)")
    ap.add_argument("--tag", default="")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--from-csv", action="store_true",
                    help="re-aggregate results/l1/events.csv instead of re-reading ten years of bars")
    args = ap.parse_args()
    print(f"store: {DATA_DIR}")
    YEARS = list(args.years)
    if args.stage == "events":
        return stage_events(args.workers, args.symbols, args.from_csv)
    return stage_backtest(args.workers, args.variants,
                          json.loads(args.params) if args.params else None, args.record, args.tag)


if __name__ == "__main__":
    sys.exit(main())
