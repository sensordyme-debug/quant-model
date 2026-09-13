#!/usr/bin/env python
"""A-8: the ORB entry window and the time stop - the last untried lever on the deployed sleeve.

    python scripts/sweep_a8.py --attribute --workers 11       # stage 1: event study
    python scripts/sweep_a8.py --workers 11 --cells after30 after45 after60   # stage 2, one batch
    python scripts/sweep_a8.py --combine --record             # every batch on disk -> one verdict
    python scripts/sweep_a8.py --leveraged --workers 11       # the SOXL/SOXS check the item asks for

A cell costs ~4 minutes of wall clock per calendar year and the store is eleven years, so the
full grid does not fit in one command under the 40-minute ceiling the parallel-tracks rules set.
`--cells` runs a batch and persists it (`results/a8/daily_<cell>.csv` + `meta_<cell>.json`);
`--combine` reads every batch back and produces the single paired table and verdict. A cell is
deterministic given (store, years, universe), so the split changes no number - the control is
re-run in each batch and overwritten with an identical series, which is the check that it does not.

Why this exists
---------------
`entry_after` / `entry_before` / `time_stop` have sat at **15 / 150 / 240** through every A-track
iteration (A-1..A-12). A-2 swept the stop, A-9 the range width, A-12 the re-entry lockout; nothing
has ever asked *when* a breakout is allowed to be taken or how long it is allowed to run. The
backlog parked A-8 for one reason and it was a power reason: on the IBKR store's 260 sessions at
the sleeve's Sharpe 0.62, ~2,600 sessions are needed to resolve the sleeve against zero, so a
window sweep "would again produce a table of statistically identical cells".

**That objection has expired.** `data/minute_alpaca` holds 2,686 sessions of consolidated SIP
bars on the same 16 names back to 2016 - the sample A-4 asked for - and A-10/A-11/A-12 have
already run this exact harness over it. A-8 is therefore the last ORB lever with a stated premise
and a permitted instrument, and it is the last thing standing between the loop and the Current
objective's instruction to *say the sleeve cannot be validated* rather than find another lever.
Either the window moves the deployed book at the power that now exists, or the A-track is closed.

Method
------
Identical to `sweep_a10.py` / `sweep_a12.py` so the numbers are comparable row for row: one
backtest per (cell, calendar year) from a fresh $1,000,000 book, daily P&L concatenated into the
same three a-priori regimes (2016-2019 / 2020-2023 / 2024-2026). The control is the **deployed**
config exactly as `live/intraday_config.json` carries it (ORB alone, `disaster_atr` 4.0,
`per_symbol` 0.15, `gross` 1.5). Every cell is that control plus one moved minute constant, so
the framework, the caps, the loss limit and the 15:38 flatten are byte-identical between cells and
only the window moves. Because every cell sees the same sessions the test is **paired**: the
statistic that decides is the daily difference `cell - control`, which removes the sleeve's own
(negative) level and the regime's volatility from the comparison.

Stage 1 (`--attribute`) is the event study, and unlike A-12's it is not a kill gate - A-8 has
never been run at all, so the grid runs either way. It reconstructs every round trip of the
control (`sweep_a12.round_trips`, unchanged) and attributes realized P&L by **entry-minute
bucket** and by **whether the trip was closed by the 240-minute time stop or exited on its own
terms**. Those are exactly the two quantities the grid moves, measured where there is nothing to
fit: ~44,000 trips instead of the 2,686 daily numbers a grid cell is judged on.

Decision rule, fixed before the runs
------------------------------------
1. **Identity.** The control must reproduce A-12's control on the overlap year (same $/day, same
   trades/day) - otherwise the framework has drifted and nothing here is comparable.
2. **Mechanism.** Paired daily difference (cell - control) positive at t > 2 in at least two of
   the three regimes.
3. **Trade-reduction falsification** (narrowing cells only: `entry_after` up, `entry_before` down,
   `time_stop` down). This sleeve loses ~$289/day and loses money per trip, so *any* filter looks
   like an improvement on the level. A narrowing cell must beat its own trade-reduction line:
   paired improvement minus `(trips/day removed) x (control $/trip)` still positive at t > 2 in at
   least two regimes. A cell that merely lies on that line is refused as "trade less", not as a
   window effect. Cells that ADD exposure (`time_stop` up) are exempt - they cannot win by
   trading less - and are held to clauses 2 and 4 alone.
4. **Deployability** (AGENTS.md rule c): the resulting book positive at t > 2 in at least two of
   the three regimes. The sleeve is at -$289/day today, so a cell that only makes the loss smaller
   is a finding, not a deploy, and `live/intraday_config.json` does not move.
5. **Leveraged subset.** `--leveraged` reruns the grid on SOXL/SOXS alone (the item asks for the
   wide-range names separately, and `LEVERAGED_DEPLOYABLE` is where the ATR backstop binds most).
   It is reported, never used to select a cell for the full sleeve: 2 of 16 names cannot carry it.
6. **No post-hoc cells.** `GRID` below is fixed before any run. A cell added after seeing stage 1
   is printed with a `post hoc` label and cannot satisfy clause 2.
7. **Nothing ships from this script.** It writes `results/a8/` and (with `--record`) DIAGNOSTIC
   ledger rows. No shipped, runner-loaded or scheduled-task file is touched, so no replay is owed
   (AGENTS.md rule a); a config move would be a separate, journalled decision (rule c).

Costs are the shipped ones (1.5 bps slippage plus IBKR commission), which A-5 part 2 currently
measures at +2.22 bps against that 1.50 assumption - i.e. every cell here is priced optimistically
by ~0.7 bps, in the control's favour as much as any cell's, and the paired difference is the
statistic precisely because the level is not trustworthy.
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
from intraday_common import (DATA_DIR, LEVERAGED_DEPLOYABLE, REPO,  # noqa: E402
                             UNIVERSE, load_universe)
from sweep_a10 import EQUITY, REGIMES, SEEN_FROM, YEARS, stats, table  # noqa: E402
from sweep_a12 import DEPLOYED, round_trips  # noqa: E402

OUT = REPO / "results" / "a8"

#: The shipped constants this item moves, for the record and for the table headers.
SHIPPED = {"entry_after": 15, "entry_before": 150, "time_stop": 240}
#: 09:30 + 368 = 15:38 ET, the framework's own flatten; a time stop at or past it is inert.
FLATTEN_MINUTE = 368


def _cell(**orb) -> dict:
    sub = {**DEPLOYED["sub_params"], "orb": {**DEPLOYED["sub_params"]["orb"], **orb}}
    return {**DEPLOYED, "sub_params": sub}


#: Pre-registered grid (clause 6). Three levers, each swept alone so the attribution is clean.
#: `entry_after` up and `entry_before` down NARROW the window (clause 3 applies); `time_stop` up
#: ADDS exposure and is exempt from it. 368 = hold to the framework flatten, the maximum possible.
GRID: dict[str, dict] = {"control": DEPLOYED}
for _v in (30, 45, 60):
    GRID[f"after{_v}"] = _cell(entry_after=_v)
for _v in (120, 90, 60):
    GRID[f"before{_v}"] = _cell(entry_before=_v)
for _v in (120, 180, 300, FLATTEN_MINUTE):
    GRID[f"stop{_v}"] = _cell(time_stop=_v)

#: POST HOC (clause 6), added after stage 1a and labelled as such: the single 30-minute bucket
#: stage 1a found positive (90-119, +$43.2/trip at t +2.27, z +3.31 against the pooled -$20.1)
#: isolated as its own window. It cannot satisfy clause 2 and exists so that the STRONGEST form of
#: the hypothesis is priced rather than left as an anecdote - every contiguous window the
#: pre-registered cells can build has to swallow a negative bucket beside it.
GRID["win90_119"] = _cell(entry_after=90, entry_before=119)
POST_HOC = {"win90_119"}

#: cells that can win by trading less, and are therefore held to clause 3
NARROWING = {n for n in GRID if n.startswith(("after", "before", "win"))
             or n in ("stop120", "stop180")}

#: entry-minute buckets for stage 1. The shipped window is [15, 150]; the last bucket is what
#: `entry_before` would remove first and the first is what `entry_after` would remove first.
BUCKETS = [(15, 29), (30, 44), (45, 59), (60, 89), (90, 119), (120, 150)]


# --------------------------------------------------------------------------------- workers
def _job(spec):
    """One calendar year: load once, run every cell on the same bars and features."""
    year, cells, symbols = spec
    lo, hi = dt.date(year, 1, 1), dt.date(year, 12, 31)
    bars = load_universe(symbols or UNIVERSE, lo, hi)
    if not bars:
        return year, {}
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    from base import features
    feats = {s: features(df) for s, df in bars.items()}
    strat = ib.load_strategy("active")
    out = {}
    for name in cells:
        params = {**strat.PARAMS, **GRID[name]}
        s = ib.run(strat, bars, EQUITY, params, lo, hi, False, feats_all=feats)
        d = s.pop("daily")
        out[name] = {"daily": d, "trades_per_day": s["trades_per_day"],
                     "costs_per_day": s["costs_per_day"],
                     "turnover_per_day_x": s["turnover_per_day_x"],
                     "stopped_days": s["stopped_days"], "trades": s["trades"]}
    return year, out


def _attribute_job(spec):
    """One calendar year of the control with every fill kept, reduced to labelled round trips."""
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


# --------------------------------------------------------------------------------- statistics
def _trip_stats(d: pd.DataFrame) -> dict:
    n = len(d)
    if not n:
        return {}
    se = d["pnl"].std(ddof=1) / np.sqrt(n) if n > 1 else float("nan")
    return {"trips": n, "$/trip": round(float(d["pnl"].mean()), 1),
            "se": round(float(se), 1) if se == se else float("nan"),
            "t": round(float(d["pnl"].mean() / se), 2) if se else float("nan"),
            "bps/trip": round(float(d["bps"].mean()), 2),
            "win %": round(float((d["pnl"] > 0).mean() * 100), 1),
            "total $": round(float(d["pnl"].sum()))}


def _paired(cell: pd.DataFrame, ctrl: pd.DataFrame) -> dict:
    """Paired daily difference cell - control over the sessions both traded."""
    m = ctrl[["day", "pnl"]].merge(cell[["day", "pnl"]], on="day", suffixes=("_c", "_x"))
    diff = (m["pnl_x"] - m["pnl_c"]).values
    n = len(diff)
    if n < 2:
        return {}
    se = diff.std(ddof=1) / np.sqrt(n)
    return {"n": n, "d$/day": float(diff.mean()), "d_se": float(se),
            "d_t": float(diff.mean() / se) if se else float("nan")}


def _regime_slice(d: pd.DataFrame, y0: int, y1: int) -> pd.DataFrame:
    return d[(d["day"] >= dt.date(y0, 1, 1)) & (d["day"] <= dt.date(y1, 12, 31))]


# --------------------------------------------------------------------- stage 1: event study
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
    pooled = _trip_stats(d)

    # ---- entry-minute buckets: what `entry_after` / `entry_before` would actually remove
    rows = []
    for lo, hi in BUCKETS:
        sub = d[(d["entry_min"] >= lo) & (d["entry_min"] <= hi)]
        s = _trip_stats(sub)
        if not s:
            continue
        # distance from the pooled mean in units of this bucket's own standard error (clause 2's
        # premise check: a window lever needs at least one bucket that is not the average trip)
        z = ((s["$/trip"] - pooled["$/trip"]) / s["se"]) if s.get("se") else float("nan")
        rows.append({"entry minute": f"{lo}-{hi}", **s, "z vs pooled": round(z, 2)})
    table(rows + [{"entry minute": "ALL [15-150]", **pooled, "z vs pooled": 0.0}],
          f"stage 1a: control round trips by ENTRY MINUTE, {len(d):,} trips over "
          f"{d['day'].nunique():,} sessions",
          "  z is (bucket $/trip - pooled $/trip) / bucket se. If no bucket reaches |z| = 2 the\n"
          "  entry window has nothing to move and any grid win is a turnover artifact."
          ).to_csv(OUT / "attr_entry.csv", index=False)

    # by regime, to see whether any bucket effect is one epoch
    rows = []
    for name, _y0, _y1 in REGIMES:
        sub = d[d["regime"] == name]
        row = {"regime": name}
        for lo, hi in BUCKETS:
            s = _trip_stats(sub[(sub["entry_min"] >= lo) & (sub["entry_min"] <= hi)])
            row |= {f"{lo}-{hi} $": s.get("$/trip"), f"{lo}-{hi} t": s.get("t")}
        rows.append(row)
    table(rows, "stage 1b: entry-minute buckets by regime - stable, or one epoch?"
          ).to_csv(OUT / "attr_entry_regime.csv", index=False)

    # ---- the time stop: trips it closed vs trips that exited on their own terms
    ts = int(SHIPPED["time_stop"])
    # a stop placed at minute `ts` is decided on the bar at `ts` and fills at `ts + 1`
    at_stop = d["exit_min"] >= ts
    rows = [{"exit": f"time stop ({ts}+)", **_trip_stats(d[at_stop])},
            {"exit": f"own terms (<{ts})", **_trip_stats(d[~at_stop])},
            {"exit": "ALL", **pooled}]
    table(rows, "stage 1c: what the 240-minute time stop closes",
          "  DESCRIPTIVE ONLY, and for the same reason as 1d: a trip that reaches the time stop\n"
          "  is by construction a trip the midpoint stop did NOT hit, so the split is the stop's\n"
          "  own definition (a stop-out is a loss; a survivor is usually a winner) and carries no\n"
          "  information about where the time stop should sit. Only stop120..stop368 price that.")
    pd.DataFrame(rows).to_csv(OUT / "attr_timestop.csv", index=False)

    # ---- holding-period response, the other half of the time-stop question
    rows = []
    for lo, hi in [(0, 14), (15, 29), (30, 59), (60, 119), (120, 199), (200, 10_000)]:
        s = _trip_stats(d[(d["hold"] >= lo) & (d["hold"] <= hi)])
        if s:
            rows.append({"hold (min)": f"{lo}-{hi if hi < 10_000 else '+'}", **s})
    table(rows, "stage 1d: realized P&L by holding period (descriptive: the hold is an OUTCOME, "
                "not a choice)",
          "  Selection runs the wrong way here - a trip that survives is one the stop did not\n"
          "  hit - so this row cannot justify a cell. It is printed to size the grid's range."
          ).to_csv(OUT / "attr_hold.csv", index=False)
    return 0


# ------------------------------------------------------------------------ stage 2: the grid
def _persist(cell: str, sfx: str, d: pd.DataFrame, meta: dict) -> None:
    """One cell's daily series and per-year bookkeeping, so batches can be combined later.

    A cell is deterministic given (store, years, universe), so a cell run in batch A and the
    same cell run in batch B are the same numbers; splitting the grid across commands is only a
    scheduling decision and changes no result. The control is re-run in every batch and its
    persisted series is overwritten with an identical one, which is also the cheapest possible
    check that the batches agree.
    """
    d.to_csv(OUT / f"daily{sfx}_{cell}.csv", index=False)
    (OUT / f"meta{sfx}_{cell}.json").write_text(json.dumps(meta, indent=1, default=str))


def _restore(cells: list[str], sfx: str) -> tuple[dict, dict]:
    """Read back what `_persist` wrote for `cells`; returns (daily, per_year)."""
    daily, per_year = {}, {}
    for c in cells:
        f, m = OUT / f"daily{sfx}_{c}.csv", OUT / f"meta{sfx}_{c}.json"
        if not f.exists() or not m.exists():
            sys.exit(f"missing results for cell {c}: run the batch that contains it first")
        d = pd.read_csv(f)
        d["day"] = pd.to_datetime(d["day"]).dt.date
        daily[c] = d
        for year, rec in json.loads(m.read_text()).items():
            per_year.setdefault(int(year), {})[c] = rec
    return daily, per_year


def grid(args) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    symbols = args.symbols or (LEVERAGED_DEPLOYABLE[:2] if args.leveraged else None)
    tag_sfx = " [SOXL/SOXS]" if args.leveraged else ""
    sfx = "_lev" if args.leveraged else ""
    if args.combine:
        daily, per_year = _restore(args.cells, sfx)
        return analyse(args, daily, per_year, sfx, tag_sfx)
    # `--reuse-control` reads the control back from disk instead of re-running it, so that several
    # batches can run CONCURRENTLY without three processes writing `daily_control.csv` at once.
    # It is read here, before any worker starts, so it can never race a later batch's write. The
    # batch-agreement check the re-run provides is not lost, only moved: the batch that does NOT
    # pass this flag re-runs the control and overwrites the series every other batch read.
    reuse_daily, reuse_year = {}, {}
    if args.reuse_control:
        run_cells = [c for c in args.cells if c != "control"]
        if not run_cells:
            sys.exit("--reuse-control leaves nothing to run")
        reuse_daily, reuse_year = _restore(["control"], sfx)
        args.cells = ["control"] + run_cells
    else:
        run_cells = list(args.cells)
    print(f"store: {DATA_DIR}")
    print(f"universe: {symbols or f'{len(UNIVERSE)} deployed names'}")
    print(f"shipped constants: {SHIPPED}")
    print(f"{len(args.years)} yearly jobs x {len(run_cells)} cells, {args.workers} workers; "
          f"each year is a fresh ${EQUITY:,.0f} book"
          + (f" (control reused from {OUT / f'daily{sfx}_control.csv'})"
             if args.reuse_control else ""))

    per_year = {}
    jobs = [(y, run_cells, symbols) for y in args.years]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for year, out in ex.map(_job, jobs):
            if not out:
                print(f"  {year}: no bars", flush=True)
                continue
            per_year[year] = out
            c = out.get(run_cells[0])
            print(f"  {year}: {len(c['daily'])} sessions  {run_cells[0]} $/day "
                  f"{c['daily']['pnl'].mean():>8,.0f}  tr/day {c['trades_per_day']:5.1f}",
                  flush=True)
    if not per_year:
        sys.exit("no results")

    daily = {c: pd.concat([per_year[y][c]["daily"] for y in sorted(per_year) if c in per_year[y]],
                          ignore_index=True).sort_values("day").reset_index(drop=True)
             for c in run_cells}
    for c, d in daily.items():
        _persist(c, sfx, d, {y: {k: v for k, v in per_year[y][c].items() if k != "daily"}
                             for y in sorted(per_year) if c in per_year[y]})
    if args.reuse_control:
        daily["control"] = reuse_daily["control"]
        for year, rec in reuse_year.items():
            per_year.setdefault(year, {})["control"] = rec["control"]
    return analyse(args, daily, per_year, sfx, tag_sfx)


def analyse(args, daily: dict, per_year: dict, sfx: str, tag_sfx: str) -> int:
    def tpd(cell, y0, y1):
        vals = [per_year[y][cell]["trades_per_day"] for y in range(y0, y1 + 1)
                if y in per_year and cell in per_year[y]]
        return float(np.mean(vals)) if vals else float("nan")

    # ---------------------------------------------------------------- books, cell by cell
    book_rows = []
    for c in args.cells:
        d = daily[c]
        row = {"cell": c}
        for name, y0, y1 in REGIMES:
            s = stats(_regime_slice(d, y0, y1))
            if s:
                row |= {f"{name} $": round(s["$/day"]), f"{name} t": round(s["t"], 2)}
        s_all = stats(d)
        row |= {"ALL $": round(s_all["$/day"]), "ALL t": round(s_all["t"], 2),
                "sharpe": round(s_all["sharpe"], 2), "DD %": round(s_all["max_dd_pct"], 1),
                "tr/day": round(tpd(c, 2016, 2026), 1),
                "costs/day": round(np.mean([per_year[y][c]["costs_per_day"] for y in per_year
                                            if c in per_year[y]]))}
        book_rows.append(row)
    table(book_rows, f"stage 2a: the BOOK each cell produces{tag_sfx}, "
                     f"{int(stats(daily[args.cells[0]])['sessions'])} sessions",
          "  clause 4 (deployability): $ > 0 at t > 2 in >= 2 of the three regimes."
          ).to_csv(OUT / f"books{sfx}.csv", index=False)

    # ---------------------------------------------------------------- paired differences
    ctrl = daily["control"]
    ctrl_trips = None
    trips_csv = OUT / "trips.csv"
    if trips_csv.exists() and not args.leveraged:
        t = pd.read_csv(trips_csv)
        ctrl_trips = float(t["pnl"].mean())          # control $/trip, for clause 3

    pair_rows, verdicts = [], {}
    for c in args.cells:
        if c == "control":
            continue
        row = {"cell": c + (" (post hoc)" if c in POST_HOC else ""), "narrowing": c in NARROWING}
        passes, passes_fals = 0, 0
        for name, y0, y1 in REGIMES:
            p = _paired(_regime_slice(daily[c], y0, y1), _regime_slice(ctrl, y0, y1))
            if not p:
                continue
            row |= {f"{name} d$": round(p["d$/day"], 1), f"{name} t": round(p["d_t"], 2)}
            if p["d$/day"] > 0 and p["d_t"] > 2:
                passes += 1
            # clause 3: subtract the trade-reduction line
            if c in NARROWING and ctrl_trips is not None:
                removed = tpd("control", y0, y1) - tpd(c, y0, y1)
                line = removed * ctrl_trips           # $ the control loses on the trips removed
                excess = p["d$/day"] + line           # ctrl_trips is negative -> line is negative
                row |= {f"{name} xs": round(excess, 1),
                        f"{name} xt": round(excess / p["d_se"], 2) if p["d_se"] else float("nan")}
                if excess > 0 and p["d_se"] and excess / p["d_se"] > 2:
                    passes_fals += 1
        row |= {"regimes t>2": passes}
        if c in NARROWING and ctrl_trips is not None:
            row |= {"xs regimes t>2": passes_fals}
        verdicts[c] = (passes, passes_fals)
        pair_rows.append(row)
    note = ("  clause 2 (mechanism): d$ > 0 at t > 2 in >= 2 regimes.\n"
            "  clause 3 (falsification, narrowing cells only): 'xs' is the paired improvement\n"
            f"  net of the trade-reduction line (control $/trip = "
            f"{ctrl_trips:.1f} x trips/day removed);\n"
            "  it must clear zero at t > 2 in >= 2 regimes or the cell is just trading less."
            ) if ctrl_trips is not None else (
            "  clause 2 (mechanism): d$ > 0 at t > 2 in >= 2 regimes.\n"
            "  clause 3 not evaluated: run --attribute first to get the control's $/trip.")
    table(pair_rows, f"stage 2b: PAIRED difference cell - control{tag_sfx}", note
          ).to_csv(OUT / f"paired{sfx}.csv", index=False)

    # ---------------------------------------------------------------- verdict
    print(f"\n=== verdict{tag_sfx} ===")
    winners = []
    for c, (passes, passes_fals) in verdicts.items():
        d = daily[c]
        deploy = sum(1 for name, y0, y1 in REGIMES
                     for s in [stats(_regime_slice(d, y0, y1))]
                     if s and s["$/day"] > 0 and s["t"] > 2)
        ok2 = passes >= 2
        ok3 = (c not in NARROWING) or ctrl_trips is None or passes_fals >= 2
        ok4 = deploy >= 2
        if ok2 and ok3 and ok4 and c not in POST_HOC:
            winners.append(c)
        print(f"  {c + ('*' if c in POST_HOC else ''):<12} "
              f"clause2 mechanism {'PASS' if ok2 else 'fail'} ({passes}/3)   "
              f"clause3 falsification {'PASS' if ok3 else 'fail'}   "
              f"clause4 deployable {'PASS' if ok4 else 'fail'} ({deploy}/3)")
    if POST_HOC & set(verdicts):
        print("  * post hoc (clause 6): selected after stage 1a, so it cannot satisfy clause 2 "
              "and is never a winner.")
    if args.leveraged:
        print("  clause 5: this is the SOXL/SOXS check. It is reported, never used to select a "
              "cell for the full sleeve.")
    elif winners:
        print(f"  {len(winners)} cell(s) pass every clause: {winners}. A config move is a separate "
              "journalled decision (AGENTS.md rule c) and needs a replay (rule a).")
    else:
        print("  REFUSED: no cell passes all of clauses 2-4. The entry window and the time stop "
              "are not levers on this sleeve,\n  which closes the last A-track item with a stated "
              "premise and a permitted instrument.")

    if args.record:
        for c in args.cells:
            for name, y0, y1 in REGIMES:
                s = stats(_regime_slice(daily[c], y0, y1))
                if not s:
                    continue
                cpd = np.mean([per_year[y][c]["costs_per_day"] for y in range(y0, y1 + 1)
                               if y in per_year and c in per_year[y]])
                stopped = sum(per_year[y][c]["stopped_days"] for y in range(y0, y1 + 1)
                              if y in per_year and c in per_year[y])
                t_pd = tpd(c, y0, y1)
                fake = {"sessions": s["sessions"], "net_profit_pct": s["net_pct"],
                        "cagr_pct": s["car_pct"], "sharpe": s["sharpe"],
                        "max_drawdown_pct": s["max_dd_pct"], "avg_daily_pnl": s["$/day"],
                        "worst_day": s["worst_day"], "trades": int(round(t_pd * s["sessions"])),
                        "trades_per_day": t_pd, "costs_per_day": cpd, "stopped_days": stopped}
                ib.record("active", f"A-8 window {c} [{name}]{tag_sfx} (yearly-reset $1M book, "
                                    f"DIAGNOSTIC)", fake, GRID[c],
                          dt.date(y0, 1, 1), dt.date(y1, 12, 31))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--attribute", action="store_true", help="stage 1: the event study")
    ap.add_argument("--leveraged", action="store_true",
                    help="clause 5: rerun the grid on SOXL/SOXS alone")
    ap.add_argument("--combine", action="store_true",
                    help="skip the runs; analyse the cells already on disk (batches -> one table)")
    ap.add_argument("--reuse-control", action="store_true",
                    help="read the control back from disk instead of re-running it, so that "
                         "several batches can run concurrently without racing on its files")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--years", nargs="*", type=int, default=YEARS)
    ap.add_argument("--cells", nargs="*", default=list(GRID))
    ap.add_argument("--symbols", nargs="*", help="subset of the universe (smoke tests only)")
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC rows to the ledger")
    args = ap.parse_args()
    if "control" not in args.cells:
        args.cells = ["control"] + list(args.cells)
    if args.attribute:
        return attribute(args)
    return grid(args)


if __name__ == "__main__":
    raise SystemExit(main())
