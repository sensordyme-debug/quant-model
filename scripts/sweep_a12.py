#!/usr/bin/env python
"""A-12: the ORB whipsaw lockout. Does blocking a reversal after a stop-out pay for itself?

    python scripts/sweep_a12.py --workers 11 --record

Why this exists
---------------
The 2026-09-10 paper session lost **-6,779 on the intraday sleeve and -5,191 of it (77%) came
from a single pattern**: short SOXL/SOXS at 09:52 ET, stopped out into a rally at 10:25, long the
same pair at 10:36, out into the fade at 12:35. Two ORB entries on opposite sides of one reversal.
The shipped module permits this by construction - `max_entries` is counted *per side*, so being
stopped out of a short never consumes any of the long budget - and nothing in A-1..A-11 ever
tested it.

Two stages
----------
**Stage 1, `--attribute`, is an event study and it runs first.** One control run per year with
`collect_trades`, every fill reconstructed into round trips per (symbol, session), and each round
trip labelled by what preceded it in that symbol that day: the session's first entry, a `flip`
re-entry (opposite side to the trip that just closed - the 2026-09-10 pattern) or a `same` re-entry
(continuation). If flip re-entries are not materially worse per trip than the first entry, the
premise is dead and no grid is worth an hour of compute. This is the L-1 discipline: measure the
mechanism where there is nothing to fit before pricing a parameter.

**Stage 2, the default, is the paired grid.** Identical to `sweep_a10.py`: one backtest per
(variant, calendar year) from a fresh $1,000,000
book on the Alpaca SIP store, daily P&L concatenated into the same three a-priori regimes
(2016-2019 / 2020-2023 / 2024-2026). The control is the **deployed** config exactly as
`live/intraday_config.json` carries it after A-10 (ORB alone, `disaster_atr` 4.0, per_symbol 0.15,
gross 1.5) - not A-10's `mix`, because the late-day fade is allocated 0 today.

Every variant is the control plus one `(reentry_block, reentry_mode)` cell on the ORB module, so
the framework, the caps, the loss limit and the flatten are byte-identical between the cells and
only the entry filter moves. Because every cell runs over the same sessions, the test is
**paired**: the statistic that decides is the daily difference `cell - control`, which removes the
sleeve's own (negative) level and the regime's volatility from the comparison.

The falsification control is the point of `reentry_mode="same"`. A lockout of any kind removes
trades, and this sleeve loses money per trade, so *any* filter looks like an improvement on the
level. `same` blocks only the continuation re-entry - the one the whipsaw story says is harmless -
at a similar cost in turnover. If `same` improves as much as `flip`, the effect is "trade less",
not "avoid whipsaws", and the mechanism is refused.

Decision rule, fixed before the runs
------------------------------------
1. **Mechanism**: paired daily difference (cell - control) positive at t > 2 in at least two of
   the three regimes, *and* materially larger than the matching `same` cell.
2. **Deployability** (AGENTS.md rule c): the resulting book positive at t > 2 in at least two of
   the three regimes. The sleeve is at -$289/day today, so a filter that only makes the loss
   smaller is a finding, not a deploy.
Only if both hold does `live/intraday_config.json` move, and then only after a replay (rule a).
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
import sys  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import intraday_backtest as ib  # noqa: E402
from intraday_common import DATA_DIR, REPO, UNIVERSE, load_universe  # noqa: E402
from sweep_a10 import EQUITY, REGIMES, SEEN_FROM, YEARS, stats, table  # noqa: E402

OUT = REPO / "results" / "a12"

#: live/intraday_config.json["params"] as of A-10. The control for everything here.
DEPLOYED = {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 0.0},
            "per_symbol": 0.15, "gross": 1.5,
            "sub_params": {"orb": {"disaster_atr": 4.0}}}


def _cell(block: int, mode: str) -> dict:
    orb = {**DEPLOYED["sub_params"]["orb"], "reentry_block": block, "reentry_mode": mode}
    return {**DEPLOYED, "sub_params": {**DEPLOYED["sub_params"], "orb": orb}}


#: The grid stage 1 selected. The original pre-registered blocks were 30/60/120/999 minutes; the
#: event study (`--attribute`, 44,219 round trips) found the entire effect inside the first fifteen
#: minutes after an exit and nothing at any longer gap in either direction, so 15 is added and the
#: dead lengths are dropped rather than burned as compute. 60 is kept because it is the
#: pre-registered cell and the "inside an hour" reading of the 2026-09-10 session.
#: The decision rule below is unchanged by this - it was fixed before either stage ran.
VARIANTS = {"control": DEPLOYED}
for _m in ("flip", "any", "same"):
    VARIANTS[f"{_m}15"] = _cell(15, _m)
for _m in ("flip", "same"):
    VARIANTS[f"{_m}60"] = _cell(60, _m)


# --------------------------------------------------------------------------------- worker
def _job(spec):
    """One calendar year: load once, run every variant on the same bars and features."""
    year, variants, symbols = spec
    lo, hi = dt.date(year, 1, 1), dt.date(year, 12, 31)
    bars = load_universe(symbols or UNIVERSE, lo, hi)
    if not bars:
        return year, {}
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("active")
    out = {}
    for name in variants:
        params = {**strat.PARAMS, **VARIANTS[name]}
        s = ib.run(strat, bars, EQUITY, params, lo, hi, False, feats_all=feats)
        d = s.pop("daily")
        out[name] = {"daily": d, "trades_per_day": s["trades_per_day"],
                     "costs_per_day": s["costs_per_day"], "turnover_per_day_x": s["turnover_per_day_x"],
                     "stopped_days": s["stopped_days"]}
    return year, out


# ------------------------------------------------------------------ stage 1: the event study
def _attribute_job(spec):
    """One calendar year of the control, with every fill kept, reduced to labelled round trips."""
    year, symbols = spec
    lo, hi = dt.date(year, 1, 1), dt.date(year, 12, 31)
    bars = load_universe(symbols or UNIVERSE, lo, hi)
    if not bars:
        return year, []
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("active")
    params = {**strat.PARAMS, **DEPLOYED}
    s = ib.run(strat, bars, EQUITY, params, lo, hi, False, feats_all=feats, collect_trades=True)
    return year, round_trips(s["trades_log"])


def round_trips(trades: list[dict]) -> list[dict]:
    """Walk the fill log into round trips: position 0 -> open -> back to 0, per symbol and session.

    Realized P&L of a trip is exactly the book's own cash change over its fills, `-sum(qty*px) -
    sum(cost)`, because the position is flat at both ends - so the attribution is in the same
    dollars the daily series is, costs included, with nothing re-priced.

    Scale-outs are partial exits inside a trip and need no special case. `max_entries` is counted
    per side by the shipped module, which is precisely why a stop-out can be followed by a trip on
    the other side in the same minute-budget.
    """
    by_key: dict = {}
    for tr in trades:
        if tr.get("why") == "eod":
            pass                                    # a forced flatten still closes its trip
        by_key.setdefault((tr["sym"], tr["t"].date()), []).append(tr)
    out = []
    for (sym, day), fills in by_key.items():
        fills.sort(key=lambda f: f["t"])
        pos, trip = 0.0, []
        prev_side, prev_exit_min = 0, None
        k = 0
        for f in fills:
            if not trip:
                entry_min = int((f["t"].hour - 9) * 60 + f["t"].minute - 30)
                side = 1 if f["qty"] > 0 else -1
            trip.append(f)
            pos += f["qty"]
            if abs(pos) < 1e-9 * max(1.0, abs(f["qty"])):
                exit_min = int((f["t"].hour - 9) * 60 + f["t"].minute - 30)
                pnl = -sum(x["qty"] * x["px"] for x in trip) - sum(x["cost"] for x in trip)
                notional = abs(trip[0]["qty"]) * trip[0]["px"]
                kind = "first" if k == 0 else ("flip" if side != prev_side else "same")
                out.append({"sym": sym, "day": day, "k": k, "kind": kind, "side": side,
                            "entry_min": entry_min, "exit_min": exit_min,
                            "hold": exit_min - entry_min,
                            "gap": None if prev_exit_min is None else entry_min - prev_exit_min,
                            "pnl": pnl, "notional": notional,
                            "bps": 1e4 * pnl / notional if notional else float("nan")})
                prev_side, prev_exit_min = side, exit_min
                k += 1
                pos, trip = 0.0, []
        if trip:                                    # never closed (should not happen: EOD flatten)
            continue
    return out


def _trip_stats(d: pd.DataFrame) -> dict:
    n = len(d)
    if not n:
        return {}
    se = d["pnl"].std(ddof=1) / np.sqrt(n) if n > 1 else float("nan")
    return {"trips": n, "$/trip": round(float(d["pnl"].mean())),
            "t": round(float(d["pnl"].mean() / se), 2) if se else float("nan"),
            "bps/trip": round(float(d["bps"].mean()), 2),
            "win %": round(float((d["pnl"] > 0).mean() * 100), 1),
            "total $": round(float(d["pnl"].sum()))}


def attribute(args) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"store: {DATA_DIR}")
    print(f"stage 1 (event study): {len(args.years)} control years, {args.workers} workers")
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for year, trips in ex.map(_attribute_job, [(y, args.symbols) for y in args.years]):
            print(f"  {year}: {len(trips)} round trips", flush=True)
            rows.extend(trips)
    if not rows:
        sys.exit("no trips")
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "trips.csv", index=False)

    def regime_of(day):
        for name, y0, y1 in REGIMES:
            if y0 <= day.year <= y1:
                return name
        return "?"

    d["regime"] = d["day"].map(regime_of)
    table([{"kind": k, **_trip_stats(d[d["kind"] == k])} for k in ("first", "flip", "same")]
          + [{"kind": "ALL", **_trip_stats(d)}],
          f"stage 1: every round trip of the deployed control, {len(d):,} trips over "
          f"{d['day'].nunique():,} sessions",
          "  'flip' is the 2026-09-10 pattern: a re-entry on the opposite side to the trip that "
          "just closed.\n  If it is not materially worse than 'first', A-12 has no mechanism."
          ).to_csv(OUT / "attr_kind.csv", index=False)

    rows = []
    for name, _y0, _y1 in REGIMES:
        sub = d[d["regime"] == name]
        row = {"regime": name}
        for k in ("first", "flip", "same"):
            s = _trip_stats(sub[sub["kind"] == k])
            row |= {f"{k} n": s.get("trips"), f"{k} $": s.get("$/trip"), f"{k} t": s.get("t")}
        rows.append(row)
    table(rows, "stage 1 by regime: is the flip penalty stable, or one epoch?",
          "  a mechanism must be visible in more than the window the parameters were fitted on."
          ).to_csv(OUT / "attr_regime.csv", index=False)

    rows = []
    for lo, hi in ((0, 15), (15, 30), (30, 60), (60, 120), (120, 10_000)):
        sub = d[(d["kind"] == "flip") & (d["gap"] >= lo) & (d["gap"] < hi)]
        same = d[(d["kind"] == "same") & (d["gap"] >= lo) & (d["gap"] < hi)]
        rows.append({"gap (min)": f"{lo}-{hi if hi < 10_000 else ''}",
                     "flip n": len(sub), "flip $/trip": _trip_stats(sub).get("$/trip"),
                     "flip t": _trip_stats(sub).get("t"),
                     "same n": len(same), "same $/trip": _trip_stats(same).get("$/trip"),
                     "same t": _trip_stats(same).get("t")})
    table(rows, "stage 1: how long does the penalty last? (this is what `reentry_block` buys)",
          "  the block length worth testing in stage 2 is the largest gap that still shows one."
          ).to_csv(OUT / "attr_gap.csv", index=False)
    print(f"\nwrote {OUT}")
    return 0


def paired(cell: pd.DataFrame, ctrl: pd.DataFrame) -> dict:
    """Paired t-test on the daily P&L difference over the sessions both runs share."""
    a = cell.set_index("day")["pnl"]
    b = ctrl.set_index("day")["pnl"]
    d = (a - b).dropna()
    n = len(d)
    if n < 2:
        return {}
    se = d.std(ddof=1) / np.sqrt(n)
    return {"n": n, "d$/day": float(d.mean()), "t": float(d.mean() / se) if se else float("nan"),
            "win %": float((d > 0).mean() * 100)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--years", nargs="*", type=int, default=YEARS)
    ap.add_argument("--variants", nargs="*", default=list(VARIANTS))
    ap.add_argument("--symbols", nargs="*", help="subset of the universe (smoke tests only)")
    ap.add_argument("--record", action="store_true", help="append the regime runs to the ledger")
    ap.add_argument("--attribute", action="store_true",
                    help="stage 1 only: label the control's own round trips, fit nothing")
    args = ap.parse_args()
    if args.attribute:
        return attribute(args)
    if "control" not in args.variants:
        args.variants = ["control", *args.variants]
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"store: {DATA_DIR}")
    print(f"{len(args.years)} yearly jobs x {len(args.variants)} variants, {args.workers} workers; "
          f"each year is a fresh ${EQUITY:,.0f} book")

    per_year = {}
    jobs = [(y, args.variants, args.symbols) for y in args.years]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for year, out in ex.map(_job, jobs):
            if not out:
                print(f"  {year}: no bars", flush=True)
                continue
            per_year[year] = out
            c = out["control"]
            print(f"  {year}: {len(c['daily'])} sessions  control $/day {c['daily']['pnl'].mean():>8,.0f}  "
                  f"tr/day {c['trades_per_day']:5.1f}", flush=True)
    if not per_year:
        sys.exit("no results")

    daily = {v: pd.concat([per_year[y][v]["daily"] for y in sorted(per_year) if v in per_year[y]],
                          ignore_index=True).sort_values("day").reset_index(drop=True)
             for v in args.variants}
    for v, d in daily.items():
        d.to_csv(OUT / f"daily_{v}.csv", index=False)
    ctrl = daily["control"]

    def tpd(v):
        return float(np.mean([per_year[y][v]["trades_per_day"] for y in sorted(per_year)]))

    # ------------------------------------------------------------------ level, per variant
    rows = []
    for v in args.variants:
        d = daily[v]
        row = {"variant": v, "tr/day": round(tpd(v), 1)}
        for name, y0, y1 in REGIMES:
            s = stats(d[(d["day"] >= dt.date(y0, 1, 1)) & (d["day"] <= dt.date(y1, 12, 31))])
            row[f"{name} $/day"] = round(s["$/day"]) if s else None
            row[f"{name} t"] = round(s["t"], 2) if s else None
        s_all = stats(d)
        row |= {"ALL $/day": round(s_all["$/day"]), "ALL t": round(s_all["t"], 2),
                "sharpe": round(s_all["sharpe"], 2), "maxDD %": round(s_all["max_dd_pct"], 1),
                "worst day": round(s_all["worst_day"])}
        rows.append(row)
    table(rows, f"level: deployed ORB framework, Alpaca SIP store, {len(ctrl)} sessions",
          "  gate 2 (deployability): ALL/regime t > 2 in at least two of three regimes.").to_csv(
        OUT / "level.csv", index=False)

    # ------------------------------------------------------------------ paired vs the control
    rows = []
    for v in args.variants:
        if v == "control":
            continue
        d = daily[v]
        row = {"variant": v, "dtr/day": round(tpd(v) - tpd("control"), 1)}
        regimes_pass = 0
        for name, y0, y1 in REGIMES:
            lo, hi = dt.date(y0, 1, 1), dt.date(y1, 12, 31)
            pr = paired(d[(d["day"] >= lo) & (d["day"] <= hi)], ctrl[(ctrl["day"] >= lo) & (ctrl["day"] <= hi)])
            row[f"{name} d$"] = round(pr["d$/day"]) if pr else None
            row[f"{name} t"] = round(pr["t"], 2) if pr else None
            if pr and pr["t"] > 2:
                regimes_pass += 1
        pa = paired(d, ctrl)
        row |= {"ALL d$/day": round(pa["d$/day"]), "ALL t": round(pa["t"], 2),
                "days better %": round(pa["win %"], 1), "regimes t>2": regimes_pass}
        rows.append(row)
    table(rows, "paired difference vs the deployed control (same sessions, same bars)",
          "  gate 1 (mechanism): d$ > 0 at t > 2 in at least two of three regimes, and the "
          "'flip' cell must beat its 'same' twin.").to_csv(OUT / "paired.csv", index=False)

    # ------------------------------------------------------------------ mechanism vs turnover
    rows = []
    for b in sorted({int(v[4:]) for v in args.variants if v.startswith("flip")}):
        row = {"block (min)": b}
        for mode in ("flip", "any", "same"):
            v = f"{mode}{b}"
            if v not in daily:
                continue
            pa = paired(daily[v], ctrl)
            row[f"{mode} d$/day"] = round(pa["d$/day"])
            row[f"{mode} t"] = round(pa["t"], 2)
            row[f"{mode} dtr/day"] = round(tpd(v) - tpd("control"), 1)
        rows.append(row)
    if rows:
        table(rows, "mechanism or turnover? flip vs same at equal block length",
              "  'same' blocks the continuation re-entry, which the whipsaw story says is harmless.\n"
              "  If 'same' pays as much as 'flip' per trade removed, the effect is trading less.").to_csv(
            OUT / "mechanism.csv", index=False)

    # ------------------------------------------------------------------ the fitted window
    rows = []
    for v in args.variants:
        s = stats(daily[v][daily[v]["day"] >= SEEN_FROM])
        if s:
            rows.append({"variant": v, "sessions": s["sessions"], "$/day": round(s["$/day"]),
                         "t": round(s["t"], 2), "sharpe": round(s["sharpe"], 2)})
    table(rows, f"for reference only: the {len(daily['control'][daily['control']['day'] >= SEEN_FROM])} "
                f"sessions any A-track parameter has seen (>= {SEEN_FROM})",
          "  every A-track false positive was born here; it decides nothing.")

    if args.record:
        for v in args.variants:
            d = daily[v]
            for name, y0, y1 in REGIMES:
                sub = d[(d["day"] >= dt.date(y0, 1, 1)) & (d["day"] <= dt.date(y1, 12, 31))]
                s = stats(sub)
                if not s:
                    continue
                yrs = [y for y in range(y0, y1 + 1) if y in per_year]
                fake = {"sessions": s["sessions"], "net_profit_pct": s["net_pct"], "cagr_pct": s["car_pct"],
                        "sharpe": s["sharpe"], "max_drawdown_pct": s["max_dd_pct"], "avg_daily_pnl": s["$/day"],
                        "worst_day": s["worst_day"],
                        "trades": int(round(np.mean([per_year[y][v]["trades_per_day"] for y in yrs]) * s["sessions"])),
                        "trades_per_day": float(np.mean([per_year[y][v]["trades_per_day"] for y in yrs])),
                        "costs_per_day": float(np.mean([per_year[y][v]["costs_per_day"] for y in yrs])),
                        "stopped_days": sum(per_year[y][v]["stopped_days"] for y in yrs)}
                ib.record("active", f"A-12 reentry lockout {v} [{name}] (yearly-reset $1M book)",
                          fake, VARIANTS[v], dt.date(y0, 1, 1), dt.date(y1, 12, 31))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
