#!/usr/bin/env python
"""F-6: does the OVERNIGHT GAP reverse during the session, on the names this sleeve may trade?

    python scripts/sweep_f6.py --stage events --workers 6      # stage 1, event study
    python scripts/sweep_f6.py --stage events --from-csv       # re-aggregate, no bars read

WHY THIS EXISTS
---------------
S-27 (2026-09-12) closed the daily sleeve's leg question and left exactly one number behind,
labelled post hoc and not pursued: on the daily champion's nine ETFs, a momentum score built
from **overnight** returns forecasts the next session's **intraday** leg NEGATIVELY - top-3
minus equal-weight **-2.230 bps/day at t -3.30**, sign-stable in both halves (IS -2.182,
OOS -2.290). It was not pursued there for three stated reasons: the nine names are the daily
champion's, so AGENTS.md's disjointness rule bars the intraday sleeve from them; the object is a
daily round trip whose gross sits under any realistic cost on that book; and a tradable version
needs its own pre-registration and an instrument.

F-6 supplies all three. The mechanism is the same shape at its shortest, cleanest horizon - the
**single overnight gap**, `open[d] / close[d-1] - 1`, fading during session `d` - and it is put
to the **56 names the intraday sleeve is allowed to trade** (50 megacaps + PLTR/MSTR/COIN/SMCI/
SOXL/SOXS, disjoint from the daily champion's book) on `data/minute_alpaca`, 2016-2026. That is
an instrument the sleeve already owns, a universe the disjointness rule permits, and a published
effect (the overnight/intraday tug of war) that this repository has never measured.

It is also a genuinely different object from everything already refused on this store:
  * F-4 fades the session's return **to date** into the flatten - refused, 0 of 96, on SIGN.
  * F-5 does the same on the three index ETFs - refused, 0 of 144, by the always-long control.
  * X-1 ranks on a 15/30/60-minute **intraday** lookback at a 30-60 minute horizon.
None of the three uses information from before the opening bell, which is where the entire
measurable alpha of the daily sleeve turned out to live (S-25: +8.103 bps/day overnight at
t +6.80 against +0.738 intraday at t +0.47).

THE RULE, PRE-REGISTERED BEFORE THE FIRST NUMBER IS COMPUTED
------------------------------------------------------------
(1) **The mechanism.** The signal is the overnight gap `open[d] / close[d-1] - 1`, where
    `close[d-1]` is the last finite minute close of the previous stored session and the two
    sessions are at most 5 calendar days apart (so a data hole is never scored as a gap). The
    trade is entered at the open of bar `m+1` (the harness's fill convention, so the 09:30 open
    that defines the signal is observed before anything is bought) and held to the framework's
    flatten at 15:38 ET. `reversal` fades the gap's sign; `momentum` is the same gross column
    negated and is reported from it rather than run twice, charged the same cost.
(2) **The decision statistic**, unchanged from L-1 / X-1 / F-4: legs inside one session overlap
    in time and share the market factor, so each session collapses to ONE number and that number
    is the SUM of its legs (a book puts the same notional on each). The t is clustered over
    sessions. The reported bps is the accumulated session sum divided by the leg count, i.e. the
    edge per dollar deployed.
(3) **The pass mark**, identical to every A-track, X-track and F-track candidate: the cell must
    be positive NET of the real cost model at **t > 2 in at least two of the three regimes**
    (2016-2019, 2020-2023, 2024-2026). Nothing else is a pass and nothing is deployed on a
    pooled number.
(4) **The primary book is `neutral`, and that is a change from F-4 made on F-5's evidence.**
    A gap book is a cross-sectional object, so the pre-registered book demeans BOTH the signal
    and the forward return against the equal-weight basket over the identical window; it is
    therefore immune to the drift that F-5 proved was a third of F-4's gross. The `raw`
    directional book is carried as a LABELLED DIAGNOSTIC and, per F-5's rule, its gross column
    may not be called a forecast until it beats the **always-long control over the identical
    windows** - which is reported beside it as `excess` with its own clustered t. A pass on
    `raw` alone is not a pass on F-6.
(5) **Two selections, both pre-registered.** `all` takes every valid name; `q20` takes only the
    extreme quintile of the demeaned gap on each side. If this is a gap effect rather than a
    drift, `q20` is where it lives, and it is also the column least contaminated by (7).
(6) **The expected outcome is written down first: the gross reversal sign is expected to be
    PRESENT and the cell is expected to be REFUSED ON COST.** The effect is published and S-27
    measured its daily-horizon cousin at t -3.30, so a zero gross column would be the surprise.
    But F-4 measured the pooled round trip on exactly these names at **4.59 bps** (4.90 in
    2016-2019 falling to 4.26 by 2024-2026), and L-1 (6.40-8.20), X-1 (4.70) and F-1 (0.892 of
    commission alone) were every one of them refused there. So the number this script exists to
    produce is the **breakeven round trip**: the cost at which the best surviving gross cell goes
    to zero, which is the only figure that transfers to a cheaper instrument. If the gross sign
    comes out POSITIVE (the gap extends), clause (6) is refuted and that is the finding, exactly
    as F-4's clause (5) was refuted by its own table.
(7) **Two contaminants, stated rather than assumed away.** The store is **split-adjusted but
    dividend-raw** (`scripts/alpaca_data.py`, `adjustment="split"`), so an ex-date prints a
    spurious downward gap of 20-50 bps on roughly 1% of name-days, which biases the reversal book
    toward a spurious long. And **earnings gaps cannot be excluded historically** - AGENTS.md
    records that the FMP basic plan serves only a narrow window around today - so the largest
    gaps in `q20` are disproportionately earnings reactions. Both contaminants push the same way
    and both are concentrated in the tails, which is why `all` and `q20` are reported side by
    side: a reversal that exists only in `q20` is as likely to be an ex-date artifact as an edge.
(8) **Nothing is promotable from this script.** F-6 is a stage-1 event study on bars; it writes
    **no ledger rows** (F-4's and F-5's precedent - `record` is reached only from a stage 2), and
    a survivor earns a stage-2 run through the shipped `intraday_backtest` framework at the
    deployed risk limits before anything is said about deployment. No file either runner loads is
    modified, so AGENTS.md rule (a) owes no replay.

(9) **ADDED AFTER THE `lookback=1` TABLE WAS READ, AND LABELLED AS SUCH.** The first run refused
    the single gap on all 112 tests and, more importantly, refuted clause (6): the gross fade is
    not there at all (best pooled cell -0.32 bps at t -0.43; **0 of 56** cells reach t < -2 in
    two of three regimes). That closes the single-gap object but it does **not** close the
    question F-6 was opened to answer, because S-27's by-product is not a single gap - it is a
    **20/60/120/252-day momentum blend of overnight returns**, i.e. a multi-session accumulation.
    So the same grid is re-run with the signal generalized to the **compounded overnight return
    over the last L sessions**, `L in {1, 5, 20}`, with `L=1` the original column that reproduces
    the first table bit-for-bit and is the identity check on this change. Everything else is
    unchanged: same universe, same entries, same exits, same two books, same two selections, same
    cost model, and **the same pass mark from clause (3)**. This is a post-hoc extension of the
    search and it is counted as one: the grid goes from 56 cells to **168** (336 tests with both
    signs), so at t > 2 roughly **15 cells would be expected to pass by chance alone** if every
    test were independent, and a single surviving cell is therefore not a finding. `L=20` loses
    the first 20 sessions of each calendar year to the rolling window (~8% of the sample), which
    is stated rather than repaired because the alternative is stitching panels across years for a
    column that is a robustness check, not the primary.

Cost model is `sweep_x1._cost_bps` unchanged - two slippage charges, two per-share commissions on
the REAL (split-unadjusted) share count, and the sell-side SEC/TAF fees exactly once, because a
round trip has exactly one sale whichever way the leg points.
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

from fetch_data import MEGACAPS  # noqa: E402
from intraday_common import (DAILY_SLEEVE_UNIVERSE, DATA_DIR, REPO,  # noqa: E402
                             UNIVERSE, parquet_path, share_scale)
# X-1's event-study primitives, reused unchanged so F-6 stays comparable leg for leg with X-1 and
# F-4: the same (day, minute) panel loader, the same cost formula, the same session-clustered t.
# _panel_job's LAST_DAY is 2026-09-09, two sessions short of the store's end - that is X-1's
# window and it is kept rather than widened, so the three studies span identical calendars.
from sweep_x1 import _cluster_t, _cost_bps, _panel_job  # noqa: E402

OUT = REPO / "results" / "f6"
YEARS = list(range(2016, 2027))
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]

#: Alpaca spells Berkshire's B share with a dot; fetch_data keeps the Yahoo spelling.
_CANDIDATES = [s.replace("-", ".") for s in MEGACAPS] + list(UNIVERSE)
#: The sleeve's tradable breadth: everything the store holds that the daily champion does not
#: trade (AGENTS.md disjointness rule), de-duplicated and ordered. Identical to F-4's.
UNIVERSE_F6 = sorted({s for s in _CANDIDATES
                      if s not in DAILY_SLEEVE_UNIVERSE and parquet_path(s).exists()})

BARS_PER_SESSION = 390
FLATTEN_MINUTE = 368             # framework constant: the sleeve is flat from 15:38
#: entry minutes measured from the 09:30 bar. 0 is the earliest causal entry (signal at the 09:30
#: open, fill at the 09:31 open); the rest walk the fade out to early afternoon, which is where
#: the published effect is usually reported to have decayed.
ENTRIES = [0, 5, 15, 30, 60, 120, 240]
#: exit conventions. `flatten` is what this sleeve can actually do; `close` is the last bar and is
#: a labelled diagnostic only - the sleeve cannot hold past 15:38 without colliding with the
#: daily rebalance at 15:45.
EXITS = ["flatten", "close"]
BOOKS = ["neutral", "raw"]       # neutral is the PRE-REGISTERED primary (clause 4)
SELECTIONS = ["all", "q20"]
#: clause (9): the signal is the compounded overnight return over the last L sessions. L=1 is the
#: original single-gap column and is the identity check on the generalization.
LOOKBACKS = [1, 5, 20]
MIN_NAMES = 20                   # refuse to score a session thinner than this
MAX_GAP_DAYS = 5                 # a hole longer than this is not an overnight gap
QUINTILE = 0.20


def _last_close(C: np.ndarray) -> np.ndarray:
    """(n_days, n_syms) last finite minute close of each session.

    The final bar is occasionally missing for a thin name, so the last five minutes are walked
    backwards rather than indexing -1 blindly; a session with nothing in its last five minutes
    is left NaN and drops out of the next day's gap.
    """
    out = np.full(C.shape[::2], np.nan, dtype=np.float64)
    for b in range(BARS_PER_SESSION - 5, BARS_PER_SESSION):
        v = C[:, b, :]
        out = np.where(np.isfinite(v), v, out)
    return out


def _ranks(x: np.ndarray) -> np.ndarray:
    """Ascending rank per row with NaN sorted last (so NaN ranks land beyond the valid count)."""
    filled = np.where(np.isfinite(x), x, np.inf)
    return np.argsort(np.argsort(filled, axis=1, kind="stable"), axis=1, kind="stable")


def _events_year(year: int, symbols: list[str], workers: int) -> pd.DataFrame:
    """All (day, entry, exit, book, selection) event aggregates for one calendar year."""
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

    # ---- the signal: the overnight gap, clause (1)
    prev_c = np.full((nd, ns), np.nan)
    prev_c[1:] = _last_close(C)[:-1]
    spacing = np.full(nd, 99)
    spacing[1:] = [(all_days[i] - all_days[i - 1]).days for i in range(1, nd)]
    prev_c[spacing > MAX_GAP_DAYS, :] = np.nan
    gap = O[:, 0, :] / prev_c - 1.0
    # clause (9): the L-session compounded overnight return. L=1 is `gap` itself.
    log_gap = pd.DataFrame(np.log1p(gap))
    signals = {L: (gap if L == 1
                   else np.expm1(log_gap.rolling(L, min_periods=L).sum().to_numpy()))
               for L in LOOKBACKS}

    # real (unadjusted) price per (day, symbol), for the per-share commission
    scale = np.array([[share_scale(s, d) for s in syms] for d in all_days], dtype=np.float64)

    rows = []
    for m in ENTRIES:
        px_in = O[:, m + 1, :]
        for exit_name in EXITS:
            px_out = O[:, FLATTEN_MINUTE, :] if exit_name == "flatten" else C[:, -1, :]
            fwd = px_out / px_in - 1.0
            for L, sig in signals.items():
                ok = np.isfinite(sig) & np.isfinite(fwd) & (px_in > 0) & (sig != 0.0)
                nvalid = ok.sum(axis=1)
                enough = nvalid >= MIN_NAMES
                if not enough.any():
                    continue
                basket_sig = np.nanmean(np.where(ok, sig, np.nan), axis=1, keepdims=True)
                basket_fwd = np.nanmean(np.where(ok, fwd, np.nan), axis=1, keepdims=True)
                # the quintile mask is always taken on the DEMEANED signal, so the same names are
                # selected whichever book scores them (clause 5)
                gd = np.where(ok, sig - basket_sig, np.nan)
                rank = _ranks(gd)
                k = np.maximum(1, np.round(QUINTILE * nvalid).astype(int))[:, None]
                extreme = (rank < k) | (rank >= (nvalid[:, None] - k))
                for book in BOOKS:
                    s_use = sig - basket_sig if book == "neutral" else sig
                    f_use = fwd - basket_fwd if book == "neutral" else fwd
                    for sel in SELECTIONS:
                        take = ok & enough[:, None] & (s_use != 0.0)
                        if sel == "q20":
                            take = take & extreme
                        if not take.any():
                            continue
                        # momentum is stored; the reversal is its negation, same cost either way
                        side = np.sign(np.where(take, s_use, 0.0))
                        r = np.where(take, side * f_use * 1e4, 0.0)
                        drift = np.where(take, f_use * 1e4, 0.0)   # always-long, same windows
                        cost = np.where(take, _cost_bps(px_in * scale), 0.0)
                        n = take.sum(axis=1)
                        rows.append(pd.DataFrame({
                            "day": all_days, "entry": m, "exit": exit_name, "book": book,
                            "sel": sel, "lb": L, "n": n, "gross_sum": np.nansum(r, axis=1),
                            "cost_sum": np.nansum(cost, axis=1),
                            "drift_sum": np.nansum(drift, axis=1),
                            "side_sum": side.sum(axis=1),
                            "hit": ((r > 0) & take).sum(axis=1)})[n > 0])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _agg(cell: pd.DataFrame) -> pd.DataFrame:
    return cell.groupby("day").agg(gross=("gross_sum", "sum"), cost=("cost_sum", "sum"),
                                   drift=("drift_sum", "sum"), side=("side_sum", "sum"),
                                   n=("n", "sum"), hit=("hit", "sum"))


def _cell(tot: pd.DataFrame) -> dict:
    """One row of the grid from a per-session aggregate frame."""
    legs = float(tot["n"].sum())
    _, g_t, n_days = _cluster_t(tot["gross"])
    _, m_t, _ = _cluster_t(tot["gross"] - tot["cost"])           # momentum, net
    _, r_t, _ = _cluster_t(-tot["gross"] - tot["cost"])          # reversal, net
    _, d_t, _ = _cluster_t(tot["drift"])
    # clause (4): the always-long control on the identical windows. For the reversal sign the
    # book is short the gap, so the control is subtracted from the reversal's own gross.
    _, e_t, _ = _cluster_t(-tot["gross"] - tot["drift"])
    return {"sessions": n_days, "legs": int(legs), "legs/day": round(legs / max(1, n_days), 1),
            "gross bps": round(tot["gross"].sum() / legs, 2), "t gross": round(g_t, 2),
            "cost bps": round(tot["cost"].sum() / legs, 2),
            "rev net bps": round((-tot["gross"].sum() - tot["cost"].sum()) / legs, 2),
            "t rev": round(r_t, 2),
            "momo net bps": round((tot["gross"].sum() - tot["cost"].sum()) / legs, 2),
            "t momo": round(m_t, 2),
            "rev breakeven": round(-tot["gross"].sum() / legs, 2),
            "hit %": round(100.0 * tot["hit"].sum() / legs, 1),
            "[ctrl] rev-long bps": round((-tot["gross"].sum() - tot["drift"].sum()) / legs, 2),
            "[ctrl] t": round(e_t, 2),
            "[diag] drift bps": round(tot["drift"].sum() / legs, 2), "[diag] t drift": round(d_t, 2),
            "[diag] breadth": round(float(tot["side"].sum() / legs), 3)}


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
        for (book, sel, exit_name, m, L), cell in sub.groupby(["book", "sel", "exit", "entry", "lb"]):
            if cell.empty:
                continue
            grid.append({"regime": name, "book": book, "sel": sel, "exit": exit_name,
                         "entry": m, "lb": int(L),
                         "clock": f"{9 + (31 + m) // 60}:{(31 + m) % 60:02d}",
                         **_cell(_agg(cell))})
    gdf = pd.DataFrame(grid)
    gdf.to_csv(OUT / "events_grid.csv", index=False)

    for L in LOOKBACKS:
        for book in BOOKS:
            label = ("PRE-REGISTERED primary: dollar-neutral book (signal and forward return demeaned)"
                     if book == "neutral" else
                     "[DIAGNOSTIC] raw directional book - read the [ctrl] columns, not the gross (F-5)")
            for sel in SELECTIONS:
                sel_label = ("every valid name" if sel == "all"
                             else "extreme quintile of the demeaned signal, both sides")
                t = gdf[(gdf["book"] == book) & (gdf["sel"] == sel) & (gdf["lb"] == L)
                        & (gdf["exit"] == "flatten") & (gdf["regime"] == "ALL")]
                if t.empty:
                    continue
                sig_label = ("the single overnight gap" if L == 1
                             else f"the compounded overnight return of the last {L} sessions [clause 9]")
                print(f"\n=== stage 1 ALL 2016-2026: signal = {sig_label}")
                print(f"    {label}; {sel_label}; exit 15:38 flatten ===")
                print("  gross < 0 = the signal FADES; 'rev' is the fade sign, 'rev breakeven' is "
                      "the round-trip cost at which it goes to zero")
                with pd.option_context("display.width", 280):
                    print(t.drop(columns=["regime", "book", "sel", "exit", "lb"]).to_string(index=False))

    for L in LOOKBACKS:
        for sel in SELECTIONS:
            t = gdf[(gdf["book"] == "neutral") & (gdf["sel"] == sel) & (gdf["lb"] == L)
                    & (gdf["exit"] == "flatten") & (gdf["regime"] != "ALL")]
            if t.empty:
                continue
            print(f"\n=== stage 1 by regime: PRIMARY neutral book, lookback {L}, {sel}, exit at the flatten ===")
            with pd.option_context("display.width", 280):
                print(t[["regime", "entry", "clock", "sessions", "legs", "gross bps", "t gross",
                         "cost bps", "rev net bps", "t rev", "rev breakeven"]].to_string(index=False))

    # -------------------------------------------------- verdict, clauses (3), (4), (6), (9)
    per_regime = gdf[gdf["regime"] != "ALL"]
    winners, gross_only = {}, {}
    for key, cell in per_regime.groupby(["book", "sel", "exit", "entry", "lb"]):
        for sign, col, tcol in (("momentum", "momo net bps", "t momo"),
                                ("reversal", "rev net bps", "t rev")):
            if int(((cell[col] > 0) & (cell[tcol] > 2.0)).sum()) >= 2:
                winners[(*key, sign)] = int(((cell[col] > 0) & (cell[tcol] > 2.0)).sum())
        # the gross reversal column, to separate "no effect" from "an effect smaller than its cost"
        if int(((cell["gross bps"] < 0) & (cell["t gross"] < -2.0)).sum()) >= 2:
            gross_only[key] = int(((cell["gross bps"] < 0) & (cell["t gross"] < -2.0)).sum())

    ncells = len(BOOKS) * len(SELECTIONS) * len(EXITS) * len(ENTRIES) * len(LOOKBACKS)
    print("\n=== F-6 stage 1 verdict (clause 3, unchanged by the clause 9 extension) ===")
    print(f"  NET edge at t > 2 in >= 2 of 3 regimes: {len(winners)} of {2 * ncells} "
          f"({ncells} cells x 2 signs)")
    for (b, s, e, m, L, sign), v in sorted(winners.items()):
        print(f"    lb {L:>2} {b:<7} {s:<4} exit {e:<7} entry {m:>3} ({sign}): {v}/3 regimes")
    print(f"  GROSS fade at t < -2 in >= 2 of 3 regimes (clause 6: effect present but unaffordable?): "
          f"{len(gross_only)} of {ncells}")
    for (b, s, e, m, L), v in sorted(gross_only.items()):
        print(f"    lb {L:>2} {b:<7} {s:<4} exit {e:<7} entry {m:>3}: {v}/3 regimes")
    if not winners:
        print("  -> no cell clears cost; clause (8) applies and stage 2 would only be fitting a losing book")

    # clause (6): the breakeven, on the strongest pooled gross fade anywhere in the grid
    prim = gdf[(gdf["regime"] == "ALL") & (gdf["exit"] == "flatten")].copy()
    best = prim.sort_values("t gross").head(1).to_dict("records")
    strongest = prim.reindex(prim["t gross"].abs().sort_values(ascending=False).index).head(3)
    if best:
        b = best[0]
        print("\n=== F-6 clause (6): the breakeven, the durable number ===")
        print(f"  strongest pooled FADE: lb {b['lb']} {b['book']}/{b['sel']} entry {b['entry']} "
              f"({b['clock']}) gross {b['gross bps']} bps at t {b['t gross']}")
        print(f"  breakeven round trip {b['rev breakeven']} bps against this store's measured "
              f"{b['cost bps']} bps (F-2a's ES contract is 0.488, but one future cannot carry a "
              f"{len(UNIVERSE_F6)}-name cross-section)")
        print("  the three largest |t gross| anywhere in the grid, whatever their sign:")
        with pd.option_context("display.width", 280):
            print(strongest[["lb", "book", "sel", "entry", "clock", "legs", "gross bps",
                             "t gross", "cost bps", "rev breakeven"]].to_string(index=False))

    json.dump({"net_winners": [{"book": a, "sel": s, "exit": e, "entry": c, "lb": L, "sign": d,
                                "regimes": v} for (a, s, e, c, L, d), v in winners.items()],
               "gross_fade": [{"book": a, "sel": s, "exit": e, "entry": c, "lb": L, "regimes": v}
                              for (a, s, e, c, L), v in gross_only.items()],
               "best_pooled_fade": best,
               "largest_abs_t": strongest.to_dict("records")},
              (OUT / "verdict_events.json").open("w", encoding="utf-8"), indent=2, default=str)
    return 0


def main() -> int:
    global YEARS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="events", choices=["events"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--symbols", nargs="*", default=UNIVERSE_F6)
    ap.add_argument("--years", nargs="*", type=int, default=YEARS)
    ap.add_argument("--from-csv", action="store_true",
                    help="re-aggregate results/f6/events.csv instead of re-reading eleven years of bars")
    args = ap.parse_args()
    print(f"store: {DATA_DIR}")
    print(f"universe: {len(UNIVERSE_F6)} names, disjoint from the daily sleeve")
    YEARS = list(args.years)
    return stage_events(args.workers, args.symbols, args.from_csv)


if __name__ == "__main__":
    sys.exit(main())
