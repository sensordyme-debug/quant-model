#!/usr/bin/env python
"""S-36 / AUD-25: the six signal-module loose ends, priced one at a time.

    py -3.11 scripts/sweep_s36.py --stage a   # clauses 1-2: identity, the ML rank double gate
    py -3.11 scripts/sweep_s36.py --stage b   # clauses 3-4: the window guard, the ib clock
    py -3.11 scripts/sweep_s36.py --stage c   # clauses 5-7: inert setting, dead code, S-3 gap
    py -3.11 scripts/sweep_s36.py             # all three

THE FINDING (audit item AUD-25, `research/audit_2026-09-12.md:235`). It is the last
`daily`-owned audit item and it is six separate claims filed as one bullet, which is why no
earlier iteration took it: there is no single number that decides it. So this one prices each
claim on its own threshold and then ships only what earns it. Quoted verbatim:

  (a) `ML_MODE="rank"` gates on the forecast's sign contrary to its docstring (S-27's ranked
      books were gated on two signs).
  (b) `Params.__post_init__` guards only the momentum window: a long `trend_window` returns
      "insufficient history" forever and reads as 0% CAR.
  (c) `--history ib` reads the in-progress daily bar (a third clock convention).
  (d) `minimum_order_margin_portfolio_percentage` is inert for `market_order`.
  (e) `blended_momentum` is dead code.
  (f) The S-3 harness credits the overnight gap that LEAN's next-open fill cannot capture.

Three of the six are claims about the DEPLOYED book's shipped code (`signals.py`, `main.py`,
`paper_trade.py`) and three are claims about RESEARCH machinery. That split decides the gate
each one has to pass, not how interesting it is, and it is the reason the clauses below are
ordered by blast radius rather than by the audit's lettering.

CLAUSES, PRE-REGISTERED BEFORE THE FIRST NUMBER (run 2026-09-12):

  (1) IDENTITY, AND WHETHER THE DEPLOYED BOOK CAN REACH ANY OF THE SIX. The offline book must
      reproduce the cell seven previous iterations agree on: 22.192150170492255% CAR and 5,052
      orders at zero cost. Then, separately, the shipped defaults must be shown to stand
      OUTSIDE every defect: `S1_ML_SCORES` unset (a), `trend_window == 0` (b), the paper task's
      own clock (c). A defect the deployed book cannot reach is preventive and is fixed at
      hygiene priority; one it can reach is urgent. This clause decides which report this is.

  (2) THE ML RANK DOUBLE GATE, ON THE REAL FORECAST FILE. `momentum_scores` in `ML_MODE="rank"`
      sets `eligible &= (score > p.min_momentum)` on the MOMENTUM score - the documented
      behaviour - and then overwrites `score` with the forecast. Downstream, `leaders()` and
      `target_weights` both apply `scores[t] > floor` to whatever `score` now holds, i.e. to
      the FORECAST, against the same `min_momentum`. So a name needs two positive numbers where
      the docstring promises one. Priced on `data/f3/ml_scores.csv`, the export S-27 actually
      ran: the count of name-days the second gate removes, the sessions on which the funded set
      differs, and the two books end to end.
      MATERIAL if the second gate removes any funded name on more than 1% of sessions, OR if
      the two books' CAR differs by more than 0.5 points - the same 0.5 S-33 pre-registered
      for "cosmetic" on this sleeve. Cosmetic otherwise, and then the fix is the DOCSTRING,
      not the code: a gate that has been measured and works is not changed to match prose.

  (3) THE WINDOW GUARD SURFACE, DERIVED FROM THE SOURCE NOT FROM MEMORY. `__post_init__`
      widens `history_bars` for `mom_lookbacks + mom_skip + rank_persist` and nothing else.
      Enumerate EVERY integer window field on `Params`, and for each one determine by running
      it which of three things a value above `history_bars` does:
        SILENT-ZERO      - the signal returns {} forever and the sweep prints a tidy 0% CAR
                           (the S-9 failure the docstring says it exists to prevent),
        SILENT-TRUNCATE  - `.iloc[-N:]` quietly yields fewer than N bars, so two different
                           values of the parameter are the SAME CELL and a grid over it
                           reports a flat shelf that is an artefact,
        SAFE             - the parameter is bounded by something else, or fails loudly.
      MATERIAL if the surface contains more than one field, because then the guard's own
      docstring ("widen the window instead, so the horizon is what is being tested") is a
      promise the code keeps for exactly one parameter out of N. The SILENT-TRUNCATE class is
      the one the audit did not name and is the reason this clause enumerates rather than
      checks: a zero CAR is visible in any table, two identical cells are not.

  (4) THE `--history ib` CLOCK, AND WHETHER THE TASK CAN REACH IT. `fetch_history_yf` drops
      today's unfinished session explicitly; `fetch_history_ib` passes `endDateTime=""` and
      does not. Establish by reading the shipped scheduled-task command line what `--history`
      the deployed runner uses, then price the defect on the only unit that matters: if the
      in-progress bar is read, the signal ranks on a partial day. MATERIAL if the deployed
      task can reach the path. If it cannot, the fix is still cheap but it is an `eng` edit to
      a live runner, and this clause has to say so rather than make it.

  (5) THE INERT SETTING. `main.py:191` sets `minimum_order_margin_portfolio_percentage = 0.002`
      and `submit_targets` sends `market_order` with an explicit share count. Prove from the
      LEAN source in `../Lean` which call sites read the setting and that none is on the
      `market_order` path, and prove the band that IS enforced is the repository's own
      `min_order_value`. MATERIAL only in the AUD-12 sense - dead code that reads as a control -
      which is a comment-or-delete decision, never a number.

  (6) THE DEAD FUNCTION. `blended_momentum` - AST over every `.py` in the repository, not a
      grep, so that a name used only inside a string or a comment is not counted as a call.

  (7) THE S-3 HARNESS GAP. `sweep_s3.simulate` earns `prices[i+1]/prices[i] - 1`, a
      close-to-close step, on weights decided at close[i]. LEAN fills that decision at the
      NEXT OPEN, so the segment close[i] -> open[i+1] is credited to a position that did not
      exist. Priced by re-running the same harness on an open-to-open step - which is what a
      next-open fill actually earns - and reading the difference. MATERIAL if the gap is more
      than 20% of the harness's reported CAR, because S-3's whole published case is a
      comparison of numbers from this harness.

THE FIX AND ITS WITHDRAWAL CONDITION. Anything shipped into `signals.py` must leave the
deployed book bit-identical: clause 1's identity re-run after the patch, plus
`scripts/compare_orders.py` still agreeing on every date. A single changed order WITHDRAWS the
patch. `algorithms/s1_momo/signals.py` is loaded by the paper runner, so that gate is not
optional here as it was in S-32..S-35.

SCOPE. `algorithms/s1_momo/signals.py`, `algorithms/s1_momo/main.py` (comment only),
`scripts/sweep_s3.py`, `tests/test_signals_windows.py`, this file. NO LEAN run and NO ledger
row: nothing here is a strategy result. `research/champion.json` is not touched.
"""
from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                                          # noqa: E402
from lean_prices import load_ohlcv                             # noqa: E402
from sweep_s25 import legs_simulate                            # noqa: E402
from sweep_s31 import describe                                 # noqa: E402

START = "2012-01-03"
END = "2026-09-04"

#: clause 1 - the cell seven previous iterations agree on (S-25, S-26, S-28, S-30..S-35)
S25_DEPLOYED_CAR = 22.192150170492255
S25_DEPLOYED_ORDERS = 5052

#: clause 2 - the forecast export S-27 ran, written by `scripts/sweep_f3.py --export`
ML_EXPORT = REPO / "data" / "f3" / "ml_scores.csv"

#: clause 2 - pre-registered materiality
ML_SESSION_THRESHOLD = 1.0          # % of sessions on which a funded name is removed
ML_CAR_THRESHOLD = 0.5              # CAR points, S-33's "cosmetic" bar on this sleeve

#: clause 7 - pre-registered materiality, as a share of the harness's reported CAR
S3_GAP_THRESHOLD = 20.0

OUT = REPO / "results"


def banner(text: str) -> None:
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}")


# ------------------------------------------------------------------ clause 1: identity

def clause1(frames: dict) -> dict:
    banner("CLAUSE 1  identity, and whether the deployed book can reach any of the six")
    book = legs_simulate(frames, sig.Params(), "both", START, END, 0.0, None)
    s = describe(book, "deployed")
    car = 100.0 * s["CAR"] if s["CAR"] < 1.0 else s["CAR"]
    orders = int(s.get("orders", s.get("Total Orders", 0)))
    print(f"  CAR      {car:.12f}%   expected {S25_DEPLOYED_CAR:.12f}%   "
          f"delta {abs(car - S25_DEPLOYED_CAR):.2e}")
    print(f"  orders   {orders:,}          expected {S25_DEPLOYED_ORDERS:,}")
    ok = abs(car - S25_DEPLOYED_CAR) < 1e-9 and orders == S25_DEPLOYED_ORDERS
    print(f"  IDENTITY {'EXACT' if ok else 'FAILED'}")

    print("\n  can the deployed book reach each defect?")
    p = sig.Params()
    reach = {
        "(a) ML rank gate": (bool(os.environ.get("S1_ML_SCORES", "")) or bool(sig.ML_SCORES_PATH),
                             f"S1_ML_SCORES={sig.ML_SCORES_PATH!r}"),
        "(b) trend window": (p.trend_window > 0, f"trend_window={p.trend_window}"),
        "(d) inert setting": (True, "main.py:191 is executed on every LEAN run"),
        "(e) dead function": (False, "not called from any deployed path"),
    }
    for name, (hit, why) in reach.items():
        print(f"    {name:<20} {'REACHABLE' if hit else 'unreachable':<12} {why}")
    return {"identity_ok": ok, "car": car, "orders": orders}


# ------------------------------------------------- clause 2: the ML rank double gate

def _install_ml(table: "pd.DataFrame | None", mode: str = "rank") -> None:
    """Point the shipped `S1_ML_SCORES` hook at an in-memory table (S-27's helper)."""
    sig._ML_TABLE = table
    sig._ML_LOADED = True
    sig.ML_MODE = mode


def _funded(prices: pd.DataFrame, p, second_gate: bool) -> tuple[list, list]:
    """(names funded, names the second gate removed) for one decision window."""
    scores, eligible = sig.momentum_scores(prices, p)
    if scores.empty:
        return [], []
    scores = scores.sort_values(ascending=False)
    floor = sig.entry_floor(scores, p)
    top = [t for t in scores.index[:p.top_n] if eligible.get(t, True)]
    kept = [t for t in top if (scores[t] > floor if second_gate else True)]
    return kept, [t for t in top if t not in kept]


def clause2(frames: dict) -> dict:
    banner("CLAUSE 2  the ML rank double gate, on the real F-3 export")
    if not ML_EXPORT.exists():
        print(f"  SKIPPED: {ML_EXPORT} not present")
        return {"skipped": True}

    table = pd.read_csv(ML_EXPORT, index_col=0)
    table.index = pd.to_datetime(table.index).normalize()
    table = table.sort_index()
    print(f"  forecast file {ML_EXPORT.relative_to(REPO)}  "
          f"{len(table):,} rows  {table.index[0].date()}..{table.index[-1].date()}  "
          f"{len(table.columns)} columns")

    p = sig.Params()
    closes = frames["close"]
    tickers = [t for t in sig.traded_universe(p) if t in closes.columns]
    lo = closes.index.searchsorted(table.index[0])
    hi = closes.index.searchsorted(table.index[-1], side="right")

    _install_ml(table, "rank")
    sessions = removed_sessions = removed_namedays = funded_namedays = 0
    neg_forecast_days = 0
    try:
        for i in range(max(lo, p.history_bars), hi):
            window = closes.iloc[max(0, i - p.history_bars + 1):i + 1]
            window = window[[t for t in tickers if t in window.columns]].ffill()
            if pd.Timestamp(window.index[-1]).normalize() not in table.index:
                continue
            kept, dropped = _funded(window, p, second_gate=True)
            sessions += 1
            funded_namedays += len(kept)
            removed_namedays += len(dropped)
            if dropped:
                removed_sessions += 1
            row = table.loc[pd.Timestamp(window.index[-1]).normalize()]
            neg_forecast_days += int((row.reindex(tickers).astype(float) <= 0).sum())
    finally:
        _install_ml(None, "rank")

    share = 100.0 * removed_sessions / max(1, sessions)
    print(f"\n  sessions scored with a forecast          {sessions:,}")
    print(f"  funded name-days                         {funded_namedays:,}")
    print(f"  name-days removed by the SECOND gate     {removed_namedays:,}")
    print(f"  sessions where it removed a funded name  {removed_sessions:,}  ({share:.2f}%)")
    print(f"  name-days with a non-positive forecast   {neg_forecast_days:,}")

    # The second half of the pre-registered threshold: the two books end to end. The
    # docstring's book is "the survivors of the MOMENTUM floor, reordered by the forecast",
    # and `eligible` already carries exactly that floor - so dropping the second gate is
    # `entry_floor -> -inf` while the forecast is installed, and nothing else.
    print("\n  the two books, deployed convention, zero cost:")
    books = {}
    real_floor = sig.entry_floor
    for label, single in (("shipped (two gates)", False), ("as documented (one gate)", True)):
        _install_ml(table, "rank")
        if single:
            sig.entry_floor = lambda scores, p: -np.inf
        try:
            book = legs_simulate(frames, p, "both", str(table.index[0].date()),
                                 str(min(table.index[-1], closes.index[-1]).date()), 0.0, None)
        finally:
            sig.entry_floor = real_floor
            _install_ml(None, "rank")
        s = describe(book, label)
        books[label] = s
        print(f"    {label:<26} CAR {100 * s['CAR'] if s['CAR'] < 1 else s['CAR']:>8.3f}%  "
              f"Sharpe {s['Sharpe']:>6.3f}  MaxDD {100 * s['MaxDD'] if s['MaxDD'] < 1 else s['MaxDD']:>6.2f}%  "
              f"orders {int(s['orders']):>6,}")
    a, b = books["shipped (two gates)"], books["as documented (one gate)"]
    ca = 100 * a["CAR"] if a["CAR"] < 1 else a["CAR"]
    cb = 100 * b["CAR"] if b["CAR"] < 1 else b["CAR"]
    print(f"    {'difference (doc - shipped)':<26} {cb - ca:>+9.3f} CAR points")

    material = share > ML_SESSION_THRESHOLD or abs(cb - ca) > ML_CAR_THRESHOLD
    print(f"\n  thresholds {ML_SESSION_THRESHOLD:.1f}% of sessions OR "
          f"{ML_CAR_THRESHOLD:.1f} CAR points -> "
          f"{'MATERIAL' if material else 'COSMETIC'}")
    return {"sessions": sessions, "removed_sessions": removed_sessions,
            "removed_namedays": removed_namedays, "share": share,
            "car_shipped": ca, "car_documented": cb, "material": material}


# --------------------------------------------- clause 3: the window guard surface

#: Every integer window on `Params`, with the companion switch (if any) that has to be ON
#: for the window to be read at all. Probing a field whose feature is off would classify the
#: feature's default rather than the field, which is how `iv_scale_window` first read as
#: SILENT-TRUNCATE here when it is in fact bounded by a different store.
WINDOW_FIELDS = {
    "alloc_vol_window": {"weight_mode": "invvol"},
    "trend_window": {},
    "regime_vol_window": {},
    "regime_median_window": {},
    "vol_est_window": {},
    "mom_vol_window": {"mom_score": "riskadj"},
    "trail_window": {"trail_stop": 0.10},
    "iv_scale_window": {"iv_scale_power": 1.0},
    "mom_skip": {},
    "rank_persist": {},
    "mom_lookbacks": {},
}


def _speaks(p, closes: pd.DataFrame, tickers: list[str]) -> tuple[bool, dict]:
    """Does the signal produce weights on the last window of history it is given?"""
    window = closes.iloc[-p.history_bars:][[t for t in tickers if t in closes.columns]].ffill()
    weights, diag = sig.target_weights(window, [100_000.0], p, {})
    return bool(weights), diag


def clause3(frames: dict) -> dict:
    banner("CLAUSE 3  the __post_init__ window guard surface")
    closes = frames["close"]
    base = sig.Params()
    tickers = [t for t in sig.traded_universe(base) if t in closes.columns]
    base_bars = base.history_bars
    print(f"  default history_bars {base_bars} "
          f"(widened from the 300 field default by mom_lookbacks {base.mom_lookbacks} "
          f"+ mom_skip {base.mom_skip} + 50)\n")

    hdr = f"  {'field':<24}{'default':>10}{'probe':>8}{'widens?':>9}{'speaks?':>9}  class"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    rows = []
    for name, switches in WINDOW_FIELDS.items():
        default = getattr(base, name)
        probe_val = (20, 60, 120, 400) if name == "mom_lookbacks" else base_bars + 100
        probe_show = "400" if name == "mom_lookbacks" else str(base_bars + 100)
        # The field's own feature has to be ON, or the probe classifies the feature's
        # default instead of the window.
        live = sig.replace(base, **switches) if switches else base
        try:
            p = sig.replace(live, **{name: probe_val})
        except Exception as exc:                                  # loud failure = SAFE
            rows.append((name, str(default), probe_show, "-", "-", f"RAISES {type(exc).__name__}"))
            continue
        widens = p.history_bars > live.history_bars
        speaks, diag = _speaks(p, closes, tickers)
        reason = diag.get("reason") or diag.get("regime_reason") or diag.get("iv_scale_reason")
        if widens:
            klass = "SAFE (guard widens)"
        elif not speaks:
            klass = f"SILENT-ZERO ({reason or 'no weights'})"
        else:
            # The definition of the truncation defect is that two DIFFERENT values of the
            # parameter are the SAME CELL. Classify on that test, not on a reason string:
            # a window read off a store other than `prices` is not bounded by
            # `history_bars` at all and must not be counted against this guard.
            b = sig.replace(live, **{name: base_bars + 500})
            wa, _ = sig.target_weights(
                closes.iloc[-p.history_bars:][tickers].ffill(), [100_000.0], p, {})
            wb, _ = sig.target_weights(
                closes.iloc[-b.history_bars:][tickers].ffill(), [100_000.0], b, {})
            klass = ("SILENT-TRUNCATE" if wa == wb
                     else "SAFE (not bounded by history_bars)")
        rows.append((name, str(default), probe_show, "yes" if widens else "no",
                     "yes" if speaks else "no", klass))
        print(f"  {name:<24}{str(default):>10}{probe_show:>8}"
              f"{'yes' if widens else 'no':>9}{'yes' if speaks else 'no':>9}  {klass}")

    zero = [r for r in rows if r[5].startswith("SILENT-ZERO")]
    trunc = [r for r in rows if r[5] == "SILENT-TRUNCATE"]
    safe = [r for r in rows if r[5].startswith("SAFE") or r[5].startswith("RAISES")]
    print(f"\n  SILENT-ZERO     {len(zero):>2}  {', '.join(r[0] for r in zero) or '-'}")
    print(f"  SILENT-TRUNCATE {len(trunc):>2}  {', '.join(r[0] for r in trunc) or '-'}")
    print(f"  SAFE            {len(safe):>2}  {', '.join(r[0] for r in safe) or '-'}")

    # The truncation is only a defect if two different values are the SAME CELL. Prove it.
    print("\n  proving SILENT-TRUNCATE is two cells collapsing into one:")
    collapsed = []
    for name, *_ in trunc:
        live = sig.replace(base, **WINDOW_FIELDS[name]) if WINDOW_FIELDS[name] else base
        a = sig.replace(live, **{name: base_bars + 100})
        b = sig.replace(live, **{name: base_bars + 500})
        wa, _ = sig.target_weights(
            closes.iloc[-a.history_bars:][tickers].ffill(), [100_000.0], a, {})
        wb, _ = sig.target_weights(
            closes.iloc[-b.history_bars:][tickers].ffill(), [100_000.0], b, {})
        same = wa == wb
        collapsed.append((name, same))
        print(f"    {name:<24} {base_bars + 100} vs {base_bars + 500}: "
              f"{'IDENTICAL weights' if same else 'differ'}")

    material = len(zero) + len(trunc) > 1
    print(f"\n  threshold: more than one field on the surface -> "
          f"{'MATERIAL' if material else 'COSMETIC'}")
    return {"zero": [r[0] for r in zero], "trunc": [r[0] for r in trunc],
            "safe": [r[0] for r in safe], "collapsed": collapsed, "material": material}


# ------------------------------------------------------ clause 4: the --history ib clock

def clause4() -> dict:
    banner("CLAUSE 4  the --history ib clock, and whether the deployed task can reach it")
    src = (REPO / "scripts" / "paper_trade.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "fetch_history_yf":
            yf_drops = "today" in ast.unparse(node)
        if isinstance(node, ast.FunctionDef) and node.name == "fetch_history_ib":
            ib_src = ast.unparse(node)
    ib_drops = "today" in ib_src
    print(f"  fetch_history_yf drops the unfinished session: {yf_drops}")
    print(f"  fetch_history_ib drops the unfinished session: {ib_drops}")
    endless = "endDateTime=''" in ib_src or 'endDateTime=""' in ib_src
    print("  fetch_history_ib endDateTime: " + ('"" (now)' if endless else "pinned"))

    installer = REPO / "scripts" / "install_paper_task.ps1"
    deployed_flag, task_time = "(installer not found)", "(unknown)"
    if installer.exists():
        text = installer.read_text(encoding="utf-8")
        deployed_flag = "--history ib" if "--history ib" in text else "yfinance (the default)"
        for line in text.splitlines():
            if "-At " in line or "StartBoundary" in line:
                task_time = line.strip()[:90]
                break
    print(f"\n  the shipped scheduled task uses: {deployed_flag}")
    print(f"  task schedule line: {task_time}")
    material = deployed_flag.startswith("--history ib")
    print(f"\n  threshold: the deployed task can reach the path -> "
          f"{'MATERIAL' if material else 'PREVENTIVE'}")
    return {"yf_drops": yf_drops, "ib_drops": ib_drops,
            "deployed_flag": deployed_flag, "material": material}


# ----------------------------------------------- clause 5: the inert LEAN setting

LEAN = REPO.parent / "Lean"


def clause5() -> dict:
    banner("CLAUSE 5  minimum_order_margin_portfolio_percentage on the market_order path")
    if not LEAN.exists():
        print(f"  SKIPPED: {LEAN} not present")
        return {"skipped": True}
    hits = subprocess.run(
        ["git", "grep", "-n", "MinimumOrderMarginPortfolioPercentage", "--",
         "Common/", "Algorithm/"],
        cwd=LEAN, capture_output=True, text=True).stdout.splitlines()
    consumers = [h for h in hits
                 if "AlgorithmSettings.cs" not in h and "IAlgorithmSettings.cs" not in h
                 and "Parameters.cs" not in h and "Messages." not in h]
    print(f"  call sites in the LEAN engine that READ the setting ({len(consumers)}):")
    for h in consumers:
        print(f"    {h.split(':')[0]}:{h.split(':')[1]}")
    on_market_order = [h for h in consumers if "QCAlgorithm.Trading" in h]
    print(f"\n  of those, on the MarketOrder path: {len(on_market_order)}")

    main_src = (REPO / "algorithms" / "s1_momo" / "main.py").read_text(encoding="utf-8")
    sets_it = "minimum_order_margin_portfolio_percentage" in main_src
    uses_target = "set_holdings(" in main_src or "PortfolioTarget" in main_src.replace(
        "`set_holdings(PortfolioTarget(...))`", "")
    sends_market = "self.market_order(" in main_src
    band = "self.min_order_value" in main_src
    print(f"  main.py sets the setting                : {sets_it}")
    print(f"  main.py sends set_holdings/PortfolioTarget: {uses_target}")
    print(f"  main.py sends market_order(symbol, qty)  : {sends_market}")
    print(f"  main.py enforces its own min_order_value : {band}")
    inert = sets_it and sends_market and not on_market_order
    print(f"\n  VERDICT: the setting is {'INERT (dead code that reads as a control)' if inert else 'live'}")
    return {"consumers": len(consumers), "on_market_order": len(on_market_order),
            "inert": inert}


# --------------------------------------------------- clause 6: the dead function

def clause6() -> dict:
    banner("CLAUSE 6  blended_momentum: called from anywhere?")
    calls = []
    for path in sorted(REPO.rglob("*.py")):
        if "__pycache__" in path.parts or ".git" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = (fn.attr if isinstance(fn, ast.Attribute)
                        else fn.id if isinstance(fn, ast.Name) else None)
                if name == "blended_momentum":
                    calls.append(f"{path.relative_to(REPO)}:{node.lineno}")
            if isinstance(node, ast.Name) and node.id == "blended_momentum" \
                    and isinstance(node.ctx, ast.Load):
                calls.append(f"{path.relative_to(REPO)}:{node.lineno} (reference)")
    files = sorted(REPO.rglob("*.py"))
    print(f"  scanned {len([f for f in files if '__pycache__' not in f.parts])} python files")
    print(f"  AST call sites / load references: {len(calls)}")
    for c in calls:
        print(f"    {c}")
    print(f"\n  VERDICT: {'DEAD' if not calls else 'live'}")
    return {"calls": calls, "dead": not calls}


# ------------------------------------------------------- clause 7: the S-3 harness gap

def clause7() -> dict:
    banner("CLAUSE 7  the S-3 harness credits the overnight gap")
    s3 = REPO / "algorithms" / "s3_reversal"
    if not s3.exists():
        print(f"  SKIPPED: {s3} not present")
        return {"skipped": True}
    # `sweep_s3` does `import signals as sig` after putting `algorithms/s3_reversal` on the
    # path, but this process already holds s1_momo's `signals`. Swap it out for the import
    # and put it back, so the harness under test is the shipped one and nothing else moves.
    import importlib
    saved = sys.modules.pop("signals", None)
    sys.path.insert(0, str(s3))
    try:
        sweep_s3 = importlib.import_module("sweep_s3")
        s3sig = sweep_s3.sig
    finally:
        sys.path.remove(str(s3))
        if saved is not None:
            sys.modules["signals"] = saved

    src = (REPO / "scripts" / "sweep_s3.py").read_text(encoding="utf-8")
    step_line = [l.strip() for l in src.splitlines() if "prices.iloc[i + 1] / prices.iloc[i]" in l]
    print(f"  sweep_s3.simulate earns (c2c): {step_line[0] if step_line else '(not found)'}")
    print("  weights are decided on the close of bar i; LEAN fills them at the OPEN of i+1,")
    print("  so the segment close[i] -> open[i+1] is credited to a position that did not exist.\n")

    # `sweep_s3.main`'s own ticker list and warm-up start, verbatim, so the control below
    # is the harness as it is published rather than a near neighbour of it.
    p = s3sig.DEFAULTS
    tickers = sorted(set(s3sig.traded_universe(p)) | set(s3sig.s1.TRADED_UNIVERSE)
                     | set(s3sig.POOLS["etf"]))
    frames = load_ohlcv(tickers)
    closes, opens, volumes = frames["close"], frames["open"], frames["volume"]
    common = closes.index.intersection(opens.index)
    closes, opens, volumes = closes.loc[common], opens.loc[common], volumes.loc[common]

    # The gap itself, measured directly on the traded universe: how much of a
    # close-to-close step is the overnight segment.
    c2c = closes.pct_change()
    gap = opens / closes.shift(1) - 1.0
    o2o = opens.pct_change()
    print(f"  universe {len(tickers)} names, {len(common):,} sessions "
          f"{common[0].date()}..{common[-1].date()}")
    print(f"  mean |close-to-close| step   {100 * c2c.abs().mean().mean():.3f}%")
    print(f"  mean |overnight gap|         {100 * gap.abs().mean().mean():.3f}%")
    print(f"  gap as a share of the step   "
          f"{100 * gap.abs().mean().mean() / c2c.abs().mean().mean():.1f}%")

    # The number that decides the clause: the harness's own edge, re-earned open to open.
    # Zero cost on BOTH sides, so the only thing moving across the two rows is the step.
    curve_c2c, _ = sweep_s3.simulate(closes, volumes, p, start=START, end=END, cost_bps=0.0)
    m_c2c = sweep_s3.metrics(curve_c2c)

    # Same decisions, same costs, but the step is the one a next-open fill earns. This goes
    # through the SHIPPED `step_mode="o2o"` argument S-36 added, so the clause tests the
    # patch rather than a private re-implementation of it.
    curve_o2o, _ = sweep_s3.simulate(closes, volumes, p, start=START, end=END, cost_bps=0.0,
                                     opens=opens, step_mode="o2o")
    m_o2o = sweep_s3.metrics(curve_o2o)

    # And at the harness's own charge, because a convention error that only shows at zero
    # cost does not revive a book that this repository refused on cost.
    charged = {}
    for label, mode in (("close-to-close", "c2c"), ("open-to-open", "o2o")):
        curve, _ = sweep_s3.simulate(closes, volumes, p, start=START, end=END,
                                     cost_bps=sweep_s3.COST_BPS, opens=opens,
                                     step_mode=mode)
        charged[label] = sweep_s3.metrics(curve)

    car_c2c, car_o2o = 100 * m_c2c["CAR"], 100 * m_o2o["CAR"]
    gap_points = car_c2c - car_o2o
    share = 100.0 * gap_points / abs(car_c2c) if car_c2c else float("nan")
    print(f"\n  {'convention':<28}{'CAR%':>10}{'Sharpe':>9}{'MaxDD%':>9}")
    print(f"  {'-' * 54}")
    print(f"  {'close-to-close (shipped)':<28}{car_c2c:>10.3f}{m_c2c['Sharpe']:>9.3f}"
          f"{100 * m_c2c['MaxDD']:>9.3f}")
    print(f"  {'open-to-open (LEAN fill)':<28}{car_o2o:>10.3f}{m_o2o['Sharpe']:>9.3f}"
          f"{100 * m_o2o['MaxDD']:>9.3f}")
    print(f"  {'gap credited':<28}{gap_points:>10.3f}  ({share:.1f}% of the reported CAR)")
    print(f"\n  at the harness's own {sweep_s3.COST_BPS:.0f} bps per unit of turnover:")
    for label, m in charged.items():
        print(f"  {label:<28}{100 * m['CAR']:>10.3f}{m['Sharpe']:>9.3f}"
              f"{100 * m['MaxDD']:>9.3f}")
    material = abs(share) > S3_GAP_THRESHOLD
    print(f"\n  threshold {S3_GAP_THRESHOLD:.0f}% of the reported CAR -> "
          f"{'MATERIAL' if material else 'COSMETIC'}")
    return {"car_c2c": car_c2c, "car_o2o": car_o2o, "gap_points": gap_points,
            "share": share, "material": material}


def _simulate_o2o(mod, closes, opens, volumes, params, start, end, cost_bps=0.0):
    """`sweep_s3.simulate`'s loop with the one line the clause is about replaced.

    Decisions are identical - same window of closes, same signal, same state - and only the
    step the book earns changes: open[i+1] -> open[i+2] rather than close[i] -> close[i+1].
    """
    index = closes.index
    i0 = index.searchsorted(pd.Timestamp(start))
    i1 = min(index.searchsorted(pd.Timestamp(end)), len(index) - 2)
    equity, dates = [100_000.0], []
    state, prev = {}, {}
    for i in range(i0, i1):
        lo = max(0, i - params.history_bars + 1)
        window = closes.iloc[lo:i + 1]
        vol_window = None if volumes is None else volumes.iloc[lo:i + 1]
        weights, diag = mod.sig.target_weights(window, equity, params, state,
                                               volumes=vol_window)
        state = diag.get("state", {})
        step = opens.iloc[i + 2] / opens.iloc[i + 1] - 1.0
        gain = sum(w * step[t] for t, w in weights.items()
                   if t in step.index and np.isfinite(step[t]))
        turnover = sum(abs(weights.get(t, 0.0) - prev.get(t, 0.0))
                       for t in set(weights) | set(prev))
        equity.append(equity[-1] * (1.0 + gain) - equity[-1] * turnover * cost_bps / 1e4)
        dates.append(index[i + 1])
        prev = weights
    return pd.Series(equity[1:], index=dates)


# ------------------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["a", "b", "c", "all"], default="all")
    args = ap.parse_args()

    frames = None
    if args.stage in ("a", "b", "all"):
        # Loaded exactly as S-25..S-35 load it: the shipped traded universe and the FULL
        # history, so the 300-bar warm-up before START is present and clause 1's identity
        # is comparable with theirs rather than nearly so.
        tickers = sig.traded_universe(sig.Params())
        frames = load_ohlcv(tickers)

    if args.stage in ("a", "all"):
        clause1(frames)
        clause2(frames)
    if args.stage in ("b", "all"):
        clause3(frames)
        clause4()
    if args.stage in ("c", "all"):
        clause5()
        clause6()
        clause7()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
