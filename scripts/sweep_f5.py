#!/usr/bin/env python
"""F-5: market intraday momentum on the index, priced at the futures cost floor.

    python scripts/sweep_f5.py --report                 # the whole study
    python scripts/sweep_f5.py --report --book          # + the session book for any survivor

WHY THIS EXISTS
---------------
F-4 (2026-09-11) refused the afternoon reversal on 6,654,000 legs over 2,664 sessions, and the
refusal was on SIGN rather than on cost: over that sample the day's move EXTENDS. Its gross
column is positive at 12 of 12 entry minutes in the directional book, and every gross statistic
in the whole grid past |t| = 2 is momentum - raw 11:30 **+2.24 bps at t +2.61**, raw 15:00
**+0.89 at t +2.48**, neutral 11:30 **+1.78 at t +3.54**, and the largest single-regime cell in
the file is raw 2020-2023 at 15:00, **+2.18 at t +3.38**.

F-4 then wrote down a reusable rule - *"a cost refusal is an argument for a cheaper instrument
only when the gross column has the right sign at |t| > 2; when the sign is wrong the cheap
instrument buys a smaller loss, not an edge"* - and applied it only to the **reversal** sign,
where by its own table the sign is wrong. **It never applied that rule to the sign its own table
says is right.** Charged F-2a's 0.488 bps ES round trip instead of the equity sleeve's 4.59, the
raw 11:30 momentum cell reads +2.24 - 0.49 = +1.75 bps rather than -2.35. That arithmetic is the
whole reason F-5 exists, and it is arithmetic rather than a result: it is one number from a
56-name equal-weighted basket, and a basket is not what a future carries.

So F-5 tests the object the cheap instrument can actually hold: **the index itself**. Store is
`data/minute_alpaca` (SPY, QQQ, IWM, 1-minute SIP bars, 2016-01-04..2026-09-10), which this
repository has never run an event study on - X-1, L-1, A-10, F-1 and F-4 all excluded the three
index ETFs under the AGENTS.md disjointness rule.

WHAT THIS IS NOT, STATED BEFORE THE FIRST NUMBER
------------------------------------------------
SPY/QQQ/IWM are in `DAILY_SLEEVE_UNIVERSE`. **Nothing measured here may ever be deployed on the
intraday equity sleeve**, whatever it says, because that would collide with the daily champion's
own book. The only instrument this mechanism could be traded on is the index future, whose
history this repository does not own past 313 sessions (F-2a, and the purchase request in
BLOCKERS.md). The ETF cost column below therefore exists as a *reference scale*, not as a path
to deployment, and a survivor here is evidence for the CME purchase, not a strategy.

THE RULE, PRE-REGISTERED BEFORE THE FIRST NUMBER IS COMPUTED
------------------------------------------------------------
(1) **The mechanism and the fill convention.** The signal is the SIGN of a session return
    measured with bars that have already closed; the trade is entered at the OPEN of the next
    bar and held to a stated exit. Two signal definitions, both pre-registered:
      * `todate`  - the return from the session open to the close of minute T. This is F-4's
                    own definition and the one whose sign F-4 measured.
      * `first30` - the return of the first 30 minutes only (09:30 -> 10:00), held fixed as T
                    moves. This is the published market-intraday-momentum predictor
                    (Gao/Han/Li/Zhou), and it is a DIFFERENT object from `todate`: it cannot
                    drift with the position, so it is the cleaner test of "an early move
                    predicts a late one".
    Two exits: `flatten` (the close of bar 368, 15:38 ET, the sleeve's framework constant) and
    `h30` (the close of bar T+30). Twelve entry minutes, 10:00..15:30 every half hour.
(2) **The decision statistic.** One leg per session per cell, so there is no overlap to cluster:
    the statistic is the leg return in basis points and the t is over sessions.
(3) **The pass mark, identical to every A-track, X-track and F-track candidate.** Net of the
    decision cost column, positive at **t > 2 in at least two of the three regimes**
    (2016-2019, 2020-2023, 2024-2026). Nothing else is a pass.
(4) **The decision cost column is the futures one, 0.488 bps a round trip** (F-2a, measured on
    the contract: $347,117 of notional, $2.05 a side all-in, one tick wide). `gross` (0.0) and
    `etf` (the real per-share model on the ETF share price) are reported beside it. NQ is not
    separately priced - F-2a measured ES at 0.488 and MES at 0.744 - so the same 0.488 is used
    for QQQ as the ES-class floor and is labelled as an assumption, not a measurement.
(5) **THE CONTROL THAT DECIDES WHETHER THIS IS A MECHANISM AT ALL, and F-4 did not run it.**
    A book that is long whenever the market is up so far is long more often than not, because
    the index drifts up. It would therefore show a positive gross column with no forecasting
    content whatsoever. So the primary cell must ALSO beat an **always-long control** over the
    identical entry and exit windows, paired session by session, at **t > 2 pooled**. Both
    conditions are required; a pass on (3) alone is a measurement of the equity risk premium.
    A **random-sign placebo** (a fixed seed, independent of the session) is reported as the
    third row of the same table so the reader can see what zero looks like.
(6) **The expectation is written down first.** F-4's raw book is 56 single names equal-weighted,
    which is dominated by the market factor, so the index should carry a similar-signed but
    noisier version of the same number - and the published effect is a SHORT horizon one (the
    first half hour predicting the LAST half hour), not a hold-to-the-flatten one. The cell most
    likely to survive is therefore `first30` into a late `h30`, and the cell F-4's arithmetic
    points at (`todate`, 11:30, `flatten`) is the one most likely to be drift. If clause (5)
    kills the `todate` family and spares nothing, the honest reading is that F-4's momentum
    column was the equity risk premium seen through a directional book, which would also
    explain why it is positive at 12 of 12 entry minutes - a mechanism is rarely that tidy.
(7) **The prior that must not be hidden.** F-4's gross momentum column IS the discovery sample
    for this hypothesis and it covers the same calendar window on a correlated object, so the
    pooled number here is NOT an out-of-sample confirmation of F-4. What is close to independent
    is the split across three indices with different constituents (SPY, QQQ, IWM) and the
    regime split, which is why clause (3) is enforced per index and per regime rather than
    pooled. Nothing is promotable from this script: F-5 is a stage-1 event study, it writes no
    ledger rows, and a survivor earns a stage-2 run on the instrument it would actually trade.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

from intraday_common import (COMMISSION_PER_SHARE, SEC_FEE_RATE,  # noqa: E402
                             SLIPPAGE_BPS, TAF_PER_SHARE)

DATA = REPO / "data" / "minute_alpaca"
OUT = REPO / "results" / "f5"

INDICES = ["SPY", "QQQ", "IWM"]
BARS_PER_SESSION = 390
FLATTEN_MINUTE = 368                      # 15:38 ET, the sleeve's framework constant
ENTRIES = list(range(30, 361, 30))        # 10:00 .. 15:30
SIGNALS = ["todate", "first30"]
EXITS = ["flatten", "h30"]
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]
LAST_DAY = dt.date(2026, 9, 10)

#: F-2a, measured on the contract. Used for every index as the ES-class floor (clause 4).
FUT_RT_BPS = 0.488
PLACEBO_SEED = 20260911


def _cost_etf_bps(px: np.ndarray) -> np.ndarray:
    """Round-trip cost of one ETF leg in bps of notional: two slippages, two per-share
    commissions, and the sell-side regulatory fees exactly once (one sale per round trip)."""
    comm = COMMISSION_PER_SHARE / px * 1e4
    sell = SEC_FEE_RATE * 1e4 + TAF_PER_SHARE / px * 1e4
    return 2 * SLIPPAGE_BPS + 2 * comm + sell


def _grid(sym: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(days, open matrix, close matrix) on a (session, minute-of-day) grid.

    The parquet index is UTC; the store holds regular-session bars only, so the minute of day is
    recovered from the Eastern wall clock. Missing minutes stay NaN and drop out per event.
    """
    df = pd.read_parquet(DATA / f"{sym}.parquet")
    idx = df.index.tz_convert("America/New_York")
    minute = (idx.hour - 9) * 60 + idx.minute - 30
    day = np.array([d.date() for d in idx])
    ok = (minute >= 0) & (minute < BARS_PER_SESSION) & (day <= LAST_DAY)
    df, minute, day = df[ok], np.asarray(minute)[ok], day[ok]
    days = np.array(sorted(set(day)))
    row = pd.Index(days).get_indexer(day)
    o = np.full((len(days), BARS_PER_SESSION), np.nan, dtype=np.float64)
    c = np.full((len(days), BARS_PER_SESSION), np.nan, dtype=np.float64)
    o[row, minute] = df["o"].to_numpy(np.float64)
    c[row, minute] = df["c"].to_numpy(np.float64)
    return days, o, c


def _t(x) -> tuple[float, float, int]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return float("nan"), float("nan"), n
    se = x.std(ddof=1) / np.sqrt(n)
    return float(x.mean()), float(x.mean() / se) if se else float("nan"), n


def legs(sym: str) -> pd.DataFrame:
    """Every (session, signal, entry, exit) leg for one index, gross and net of both cost
    columns, together with the always-long and placebo controls on the identical windows."""
    days, O, C = _grid(sym)
    rng = np.random.default_rng(PLACEBO_SEED)
    placebo = rng.choice([-1.0, 1.0], size=len(days))
    open_px = O[:, 0]
    rows = []
    for entry in ENTRIES:
        # the signal uses bars that have CLOSED; the fill is the next bar's open.
        sig_px = {"todate": C[:, entry - 1], "first30": C[:, 29]}
        entry_px = O[:, entry]
        for exit_name in EXITS:
            exit_idx = FLATTEN_MINUTE if exit_name == "flatten" else entry + 30
            if exit_idx <= entry or exit_idx >= BARS_PER_SESSION:
                continue
            exit_px = C[:, exit_idx]
            fwd = (exit_px / entry_px - 1.0) * 1e4          # bps, the always-long leg
            etf = _cost_etf_bps(entry_px)
            for signal in SIGNALS:
                s = np.sign(sig_px[signal] / open_px - 1.0)
                g = s * fwd
                ok = np.isfinite(g) & np.isfinite(fwd) & (s != 0)
                rows.append(pd.DataFrame({
                    "day": days[ok], "sym": sym, "signal": signal,
                    "entry": entry, "exit": exit_name,
                    "gross": g[ok], "fut": g[ok] - FUT_RT_BPS, "etf": g[ok] - etf[ok],
                    "long_only": fwd[ok], "placebo": (placebo * fwd)[ok],
                    "sig": s[ok],
                }))
    out = pd.concat(rows, ignore_index=True)
    out["year"] = pd.to_datetime(out["day"]).dt.year
    return out


def _regime(y: int) -> str:
    for name, lo, hi in REGIMES:
        if lo <= y <= hi:
            return name
    return "?"


def report(book: bool) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ev = pd.concat([legs(s) for s in INDICES], ignore_index=True)
    ev["regime"] = ev["year"].map(_regime)
    ev.to_csv(OUT / "legs.csv", index=False)

    print("F-5  market intraday momentum on the index, priced at the futures cost floor")
    print(f"store data/minute_alpaca  indices {'/'.join(INDICES)}  "
          f"{ev['day'].min()}..{ev['day'].max()}  {ev['day'].nunique()} sessions  "
          f"{len(ev):,} legs")
    print(f"decision cost column = 'fut' at {FUT_RT_BPS} bps round trip (F-2a, measured on ES; "
          f"assumed for NQ/RTY)\n")

    # ---------------------------------------------------------------- clause 3, the pass mark
    print("=== (1) THE PRE-REGISTERED PASS MARK: net of 0.488 bps, t > 2 in 2 of 3 regimes ===")
    print("      primary family = signal 'todate', exit 'flatten' (clause 6 names 'first30'/'h30'")
    print("      as the more likely survivor; both are pre-registered, neither is post hoc)\n")
    passes = []
    hdr = (f"{'sym':5s} {'signal':8s} {'exit':8s} {'entry':>5s} {'N':>5s} "
           f"{'gross':>7s} {'t':>6s} {'net_fut':>8s} {'t':>6s} {'net_etf':>8s} "
           f"{'2of3':>5s} {'long%':>6s}")
    for signal in SIGNALS:
        for exit_name in EXITS:
            print(f"--- signal={signal}  exit={exit_name} ---")
            print(hdr)
            for sym in INDICES:
                for entry in ENTRIES:
                    d = ev[(ev["sym"] == sym) & (ev["signal"] == signal)
                           & (ev["exit"] == exit_name) & (ev["entry"] == entry)]
                    if d.empty:
                        continue
                    gm, gt, n = _t(d["gross"])
                    fm, ft, _ = _t(d["fut"])
                    em, _, _ = _t(d["etf"])
                    hits = sum(1 for r, _, _ in REGIMES
                               if (lambda v: v[1] > 2 if np.isfinite(v[1]) else False)(
                                   _t(d[d["regime"] == r]["fut"])))
                    ok = hits >= 2
                    if ok:
                        passes.append((sym, signal, exit_name, entry, fm, ft, hits))
                    print(f"{sym:5s} {signal:8s} {exit_name:8s} {entry:5d} {n:5d} "
                          f"{gm:7.2f} {gt:6.2f} {fm:8.2f} {ft:6.2f} {em:8.2f} "
                          f"{hits:5d} {100*(d['sig'] > 0).mean():6.1f}"
                          + ("   <== PASSES" if ok else ""))
            print()
    print(f"VERDICT on clause (3): {len(passes)} of "
          f"{len(INDICES)*len(SIGNALS)*len(EXITS)*len(ENTRIES)} cells reach t > 2 net in two "
          f"of three regimes.\n")

    # ------------------------------------------- clause 5, the control that decides everything
    print("=== (2) CLAUSE (5): IS IT A FORECAST, OR IS IT THE DRIFT? ===")
    print("    momentum minus always-long, paired by session, GROSS (cost is identical on both")
    print("    books so it cancels). If this is not positive at t > 2 the signal adds nothing")
    print("    to being long, and the 'edge' above is the equity risk premium.\n")
    print(f"{'sym':5s} {'signal':8s} {'exit':8s} {'entry':>5s} {'mom':>7s} {'long':>7s} "
          f"{'plcb':>7s} {'mom-long':>9s} {'t':>6s} {'mom-plcb':>9s} {'t':>6s}")
    ctrl = []
    for signal in SIGNALS:
        for exit_name in EXITS:
            for sym in INDICES:
                for entry in ENTRIES:
                    d = ev[(ev["sym"] == sym) & (ev["signal"] == signal)
                           & (ev["exit"] == exit_name) & (ev["entry"] == entry)]
                    if d.empty:
                        continue
                    dm, dt_, _ = _t(d["gross"] - d["long_only"])
                    pm, pt, _ = _t(d["gross"] - d["placebo"])
                    ctrl.append(dict(sym=sym, signal=signal, exit=exit_name, entry=entry,
                                     diff=dm, t=dt_, dplacebo=pm, tplacebo=pt))
                    print(f"{sym:5s} {signal:8s} {exit_name:8s} {entry:5d} "
                          f"{d['gross'].mean():7.2f} {d['long_only'].mean():7.2f} "
                          f"{d['placebo'].mean():7.2f} {dm:9.2f} {dt_:6.2f} {pm:9.2f} {pt:6.2f}")
            print()
    cdf = pd.DataFrame(ctrl)
    cdf.to_csv(OUT / "controls.csv", index=False)
    beats = cdf[(cdf["diff"] > 0) & (cdf["t"] > 2)]
    print(f"VERDICT on clause (5): {len(beats)} of {len(cdf)} cells beat the always-long control "
          f"at t > 2.")
    print(f"                       best cell: "
          f"{cdf.loc[cdf['t'].idxmax()].to_dict() if len(cdf) else 'n/a'}\n")

    # ------------------------------------------------------------------------ regime detail
    print("=== (3) THE REGIME TABLE FOR THE TWO FAMILIES CLAUSE (6) NAMES ===")
    for signal, exit_name, label in [("todate", "flatten", "F-4's arithmetic"),
                                     ("first30", "h30", "the published effect")]:
        print(f"--- {signal} / {exit_name}   ({label}) ---")
        print(f"{'sym':5s} {'entry':>5s} " + " ".join(f"{r:>16s}" for r, _, _ in REGIMES)
              + f" {'pooled net':>16s}")
        for sym in INDICES:
            for entry in ENTRIES:
                d = ev[(ev["sym"] == sym) & (ev["signal"] == signal)
                       & (ev["exit"] == exit_name) & (ev["entry"] == entry)]
                if d.empty:
                    continue
                cells = []
                for r, _, _ in REGIMES:
                    m, t, n = _t(d[d["regime"] == r]["fut"])
                    cells.append(f"{m:8.2f} t{t:6.2f}")
                m, t, _ = _t(d["fut"])
                print(f"{sym:5s} {entry:5d} " + " ".join(cells) + f" {m:8.2f} t{t:6.2f}")
        print()

    if book:
        print("=== (4) THE SESSION BOOK, for the best cell of each family ===")
        for signal, exit_name in [("todate", "flatten"), ("first30", "h30")]:
            sub = ev[(ev["signal"] == signal) & (ev["exit"] == exit_name)]
            best, bt = None, -np.inf
            for sym in INDICES:
                for entry in ENTRIES:
                    d = sub[(sub["sym"] == sym) & (sub["entry"] == entry)]
                    if d.empty:
                        continue
                    _, t, _ = _t(d["fut"])
                    if np.isfinite(t) and t > bt:
                        best, bt = (sym, entry), t
            if best is None:
                continue
            sym, entry = best
            d = sub[(sub["sym"] == sym) & (sub["entry"] == entry)].sort_values("day")
            r = d["fut"].to_numpy() / 1e4
            eq = np.cumprod(1 + r)
            yrs = (pd.to_datetime(d["day"].iloc[-1]) - pd.to_datetime(d["day"].iloc[0])).days / 365.25
            car = eq[-1] ** (1 / yrs) - 1 if yrs > 0 else float("nan")
            dd = float((1 - eq / np.maximum.accumulate(eq)).max())
            shp = r.mean() / r.std(ddof=1) * np.sqrt(252) if r.std(ddof=1) else float("nan")
            print(f"  {signal}/{exit_name}  best t: {sym} entry {entry}  "
                  f"N {len(d)}  1x notional, net of {FUT_RT_BPS} bps:")
            print(f"    CAR {100*car:6.2f}%   Sharpe {shp:5.2f}   maxDD {100*dd:5.1f}%   "
                  f"win {100*(d['fut'] > 0).mean():4.1f}%   worst {d['fut'].min():7.1f} bps")
        print()

    summary = dict(sessions=int(ev["day"].nunique()), legs=int(len(ev)),
                   passes=len(passes), control_beats=int(len(beats)),
                   cells=int(len(cdf)))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"wrote {OUT/'legs.csv'}, {OUT/'controls.csv'}, {OUT/'summary.json'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--book", action="store_true")
    a = ap.parse_args()
    if not a.report:
        ap.print_help()
        return 2
    return report(a.book)


if __name__ == "__main__":
    raise SystemExit(main())
