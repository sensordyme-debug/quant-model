#!/usr/bin/env python
"""S-37 / AUD-13: the paper runner has no data-completeness gate, priced per failure mode.

    py -3.11 scripts/sweep_s37.py --stage a    # clauses 1-2: identity+reach, the SPY-missing flatten
    py -3.11 scripts/sweep_s37.py --stage b1   # clause 3: the all-NaN column, name by name
    py -3.11 scripts/sweep_s37.py --stage b2   # clause 4: the stale price, in both places
    py -3.11 scripts/sweep_s37.py --stage b3   # clause 5: hold vs flatten, mean and tail
    py -3.11 scripts/sweep_s37.py --stage c    # clauses 6-7: false positives, the fix post-patch
    py -3.11 scripts/sweep_s37.py              # all of them

THE FINDING (audit item AUD-13, `research/audit_2026-09-12.md:136`), quoted verbatim:

  `paper_trade.py:502-505`, `signals.py:884,976`. A missing SPY column yields `regime_reason
  "SPY missing"` and flattens everything; an all-NaN column silently rotates XLK to QQQ; a
  last-row NaN is forward-filled and sized on a stale price. A yfinance outage at 15:45 is a
  full round trip at real spread. Fix: exit 3 and notify if any universe column is missing,
  the last row has NaN, or `as_of` is older than the previous session; never flatten on a
  reason that names a missing ticker.

It is the last `daily`-owned audit item that needs no trading day. S-36 said the track had
none left; that was wrong about this one - AUD-13 is filed `[daily+eng]`, its two named files
are the daily signal module and the daily runner, and nothing in it requires the account to
trade. What it DOES require is the deploy gate, because `paper_trade.py` is the live runner.

Three defects are filed as one bullet and they are not the same kind of thing. Two are
*silent* - the book trades a different portfolio and nothing in the log says so - and one is
*loud and wrong*: it flattens the whole account and writes a reason that reads like a risk
decision. This sweep prices each on its own pre-registered threshold and then ships one gate.

The mechanism is simulated rather than assumed. Every clause below corrupts the DECISION FRAME
the way an outage corrupts it (`prices.drop(columns=["SPY"])`, a column set to NaN, a missing
last row) and runs the deployed book through `sweep_s25.legs_simulate` unchanged, so the number
is what the shipped signal + the shipped rebalance + the shipped costs actually do with bad
data. No shared research code is modified: `legs_simulate` calls `sig.target_weights` by module
attribute, so a wrapper installed on that attribute reaches the real decision site.

CLAUSES, PRE-REGISTERED BEFORE THE FIRST NUMBER (run 2026-09-12):

  (1) IDENTITY, AND WHETHER THE DEPLOYED TASK CAN REACH THE DEFECT. The offline book must
      reproduce the cell eight previous iterations agree on: 22.192150170492255% CAR and 5,052
      orders at zero cost. Then, separately: read the shipped scheduled-task command line and
      establish which history source the account actually uses, and prove by walking the code
      path that a frame missing a universe column reaches `plan_orders` without any exit. A
      defect the deployed task cannot reach is preventive; one it can reach is urgent.

  (2) THE SPY-MISSING FLATTEN, PRICED END TO END AT AN OUTAGE RATE. Drop `REGIME_TICKER` from
      the decision frame on a random p of sessions, fixed seeds, and read the deployed book's
      CAR against the control. Report the cost per event in basis points of equity and, the
      number the owner can act on, HOW MANY OUTAGES PER YEAR it takes to cost 0.5 CAR points -
      S-33's pre-registered "cosmetic" bar on this sleeve.
      MATERIAL if that break-even is 12 outages/year or fewer, i.e. if one bad print a month
      is enough to spend the entire selection premium S-33 measured. Priced at 0 bp AND at the
      champion's 2 bp column, because the audit's own claim ("a full round trip at real
      spread") is a claim about the cost model and must be read in the column that has one.

  (3) THE ALL-NaN COLUMN, ON EVERY NAME IN THE UNIVERSE NOT JUST XLK. `target_weights` runs
      `dropna(axis=1, how="all")` before anything else, so an all-NaN column is not an error,
      it is a smaller universe. Corrupt each traded name in turn on a random p of sessions and
      read (a) the sessions on which the funded set differs from the control, (b) the CAR.
      MATERIAL if any single name moves CAR by more than 0.5 points at the tested rate, or if
      the funded set differs on more than 1% of the corrupted sessions - the two thresholds
      S-36 used for the same class of question. The audit names XLK->QQQ; this clause exists
      to find whether XLK is the worst case or an example, because the fix is the same either
      way and the REPORT is not.

  (4) THE STALE PRICE, IN BOTH PLACES IT LANDS. A last-row NaN is forward-filled by
      `target_weights` (the signal ranks on a stale close) and `paper_trade.py:555` then sizes
      shares at `closes[s].dropna().iloc[-1]`, which is the same stale close. The second is
      arithmetic and can be priced exactly: the realized weight error of a name whose price
      moved r over the missed session is r/(1+r), and the deployed no-trade band is 1% of
      equity. Measure the one-session move distribution over the real store for the traded
      universe and report the share of name-days whose sizing error exceeds the band, plus the
      book-level CAR cost of ranking on a stale close.
      MATERIAL if the p95 one-session move exceeds the band, because then the stale path
      routinely mis-sizes by more than the amount the runner refuses to trade for.

  (5) THE ASYMMETRY THAT DECIDES THE FIX'S DESIGN: IS REFUSING SAFER THAN FLATTENING? The
      audit prescribes "exit 3", i.e. hold yesterday's book for a session. That is not free:
      if the true signal wanted to be flat, holding is risk the book did not choose. Price
      both responses against the control on the SAME corrupted sessions - flatten-for-a-day
      versus hold-for-a-day - in the mean AND in the worst session, because C-2's standing
      rule on this repository is that a harness or a remedy can be conservative in the mean
      column and reckless in the tail column at the same time.
      The fix takes the audit's prescription only if holding wins on BOTH. If it wins on the
      mean and loses in the tail, this clause says so and the gate still refuses - but the
      report has to carry the number, not the prescription.

  (6) THE GATE'S FALSE POSITIVES, MEASURED BEFORE IT IS WRITTEN. A completeness gate that
      fires on a legitimate condition is worse than the defect: it stops the account trading
      and it will be switched off. Over the real daily store, count the sessions on which the
      shipped universe legitimately has a missing or NaN close - a name before its own
      inception, a holiday row, a store hole - and derive from that count the exact predicate
      the gate may use. WITHDRAWAL CONDITION: if the predicate the audit prescribes ("any
      universe column missing") fires on more than 0 sessions of the shipped store, the gate
      is narrowed to names with established history and the narrowing is reported.

  (7) THE FIX, AND WHAT IS DELIBERATELY NOT FIXED. One function in `paper_trade.py` returning
      the list of faults, exit 3 + `notify()` on any of them, called BEFORE the signal is
      called so a fault can never become an order. `signals.py` is examined and left alone
      unless clause 1 shows the runner gate cannot cover it: an edit to a live-loaded file
      that buys nothing measurable is refused on S-35's precedent.
      BACKWARD COMPATIBILITY IS THE WITHDRAWAL CONDITION. The patch must leave the deployed
      book bit-identical - clause 1's identity re-run after the patch, `scripts/compare_orders.py`
      still agreeing on every date, and a dry run of the runner on healthy data producing the
      same plan - and the full unit suite green. A single changed order withdraws it.

SCOPE. `scripts/paper_trade.py`, `tests/test_paper_dataquality.py`, this file. NO LEAN run and
NO ledger row: nothing here is a strategy result. `research/champion.json` is not touched, and
neither is `algorithms/s1_momo/signals.py` unless clause 7 earns it.
"""
from __future__ import annotations

import argparse
import ast
import copy
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

#: clause 1 - the cell eight previous iterations agree on (S-25..S-36)
S25_DEPLOYED_CAR = 22.192150170492255
S25_DEPLOYED_ORDERS = 5052

#: clause 2/3 - pre-registered materiality, S-33's "cosmetic" bar on this sleeve
CAR_THRESHOLD = 0.5
#: clause 2 - outages per year at which the break-even makes the defect material
BREAKEVEN_THRESHOLD = 12.0
#: clause 3 - % of corrupted sessions on which the funded set may differ
SET_THRESHOLD = 1.0
#: clause 4 - the deployed no-trade band, as a fraction of equity (paper_trade.MIN_ORDER_VALUE)
BAND = 0.01

#: the outage rates clause 2/3/5 price. 1/252 is one bad print a year, 1/21 one a month.
RATES = (1.0 / 252.0, 1.0 / 21.0)
SEEDS = (11, 23, 37, 51, 77)

OUT = REPO / "results"


def banner(text: str) -> None:
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}")


# ---------------------------------------------------------------- the defect injector

class Defect:
    """Install a corruption on `sig.target_weights`' input frame for a chosen set of dates.

    `legs_simulate` calls `sig.target_weights(closes.iloc[lo:i - lag], ...)` by module
    attribute, so replacing that attribute reaches the real decision site with the real
    frame. The corruption is applied to the frame, never to the answer, so the shipped
    signal decides what a missing column MEANS - which is the whole point: the audit's
    claim is about `risk_on`'s behaviour, not about an assumed flatten.

    Modes:
      drop      - the column is absent (yfinance returned no series for that symbol)
      nan_col   - the column exists and is entirely NaN (the symbol downloaded empty)
      nan_last  - only the last row is NaN (the 15:45 print did not arrive)
      stale     - the whole frame is one session short (`as_of` older than it should be)
      hold      - clause 5's "refuse and hold" arm: the previous session's targets are
                  repeated AND the previous state is returned unadvanced, because a runner
                  that exits 3 never reaches `call_signal` and therefore never writes state.
                  Its counterpart, the "flatten" arm, is not a mode at all - it is `drop` on
                  REGIME_TICKER, i.e. the defect itself.
    """

    def __init__(self, mode: str, dates: set, ticker: str | None = None):
        self.mode, self.dates, self.ticker = mode, dates, ticker
        self.real = sig.target_weights
        self.hits = 0
        self.last: tuple | None = None
        self.decisions: dict = {}

    def __enter__(self):
        sig.target_weights = self._call
        return self

    def __exit__(self, *exc):
        sig.target_weights = self.real
        return False

    def _call(self, prices, equity_curve=(), params=None, state=None, **kw):
        day = prices.index[-1]
        hit = day in self.dates
        if hit:
            self.hits += 1
            if self.mode == "hold":
                held = dict(self.last[0]) if self.last else {}
                diag = copy.deepcopy(self.last[1]) if self.last else {"state": dict(state or {})}
                self.decisions[day] = held
                return held, diag
            prices = self._corrupt(prices)
        out, diag = self.real(prices, equity_curve, params, state, **kw)
        if hit:
            self.decisions[day] = dict(out)
        self.last = (dict(out), diag)
        return out, diag

    def _corrupt(self, prices: pd.DataFrame) -> pd.DataFrame:
        t = self.ticker
        if self.mode == "drop":
            return prices.drop(columns=[t]) if t in prices.columns else prices
        if self.mode == "nan_col":
            out = prices.copy()
            if t in out.columns:
                out[t] = np.nan
            return out
        if self.mode == "nan_last":
            out = prices.copy()
            if t in out.columns:
                out.iloc[-1, out.columns.get_loc(t)] = np.nan
            return out
        if self.mode == "stale":
            return prices.iloc[:-1]
        raise ValueError(self.mode)


def event_dates(index: pd.DatetimeIndex, rate: float, seed: int) -> set:
    """A Bernoulli outage schedule over the decision dates, deterministic in `seed`."""
    rng = np.random.default_rng(seed)
    lo = index.searchsorted(pd.Timestamp(START))
    live = index[lo:]
    return set(live[rng.random(len(live)) < rate])


def run(frames: dict, cost_bps: float, defect: Defect | None = None) -> pd.DataFrame:
    if defect is None:
        return legs_simulate(frames, sig.Params(), "both", START, END, cost_bps, None)
    with defect:
        return legs_simulate(frames, sig.Params(), "both", START, END, cost_bps, None)


def car_of(book: pd.DataFrame) -> float:
    s = describe(book, "x")
    return 100.0 * s["CAR"] if s["CAR"] < 1.0 else s["CAR"]


# ------------------------------------------------------------------ clause 1: identity

def clause1(frames: dict) -> dict:
    banner("CLAUSE 1  identity, and whether the deployed task can reach the defect")
    book = run(frames, 0.0)
    s = describe(book, "deployed")
    car = 100.0 * s["CAR"] if s["CAR"] < 1.0 else s["CAR"]
    orders = int(s["orders"])
    print(f"  CAR      {car:.12f}%   expected {S25_DEPLOYED_CAR:.12f}%   "
          f"delta {abs(car - S25_DEPLOYED_CAR):.2e}")
    print(f"  orders   {orders:,}          expected {S25_DEPLOYED_ORDERS:,}")
    ok = abs(car - S25_DEPLOYED_CAR) < 1e-9 and orders == S25_DEPLOYED_ORDERS
    print(f"  IDENTITY {'EXACT' if ok else 'FAILED'}")

    # --- the deployed history source, read off the runner rather than remembered
    src = Path(REPO / "scripts" / "paper_trade.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    default = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument"
                and node.args and getattr(node.args[0], "value", "") == "--history"):
            for kw in node.keywords:
                if kw.arg == "default":
                    default = kw.value.value
    print(f"\n  runner --history default              {default!r}")
    print("  scheduled task 'Quant Paper Rebalance' passes NO arguments, so the account runs "
          f"--history {default}")

    # --- walk the path a corrupt frame takes through the runner, from the source
    print("\n  what the runner does with a frame missing a universe column:")
    body = src[src.index("missing = [s for s in universe"):src.index("plan = plan_orders")]
    for line in body.strip().splitlines():
        print(f"    | {line.strip()}")
    exits = [ln for ln in body.splitlines() if "return 3" in ln or "sys.exit" in ln]
    print(f"    -> exits on the way to plan_orders: {len(exits)}  "
          f"{'REACHABLE' if not exits else 'gated'}")

    # --- and what the signal decides when SPY is the missing one
    closes = frames["close"]
    probe = closes.iloc[-sig.Params().history_bars - 10:]
    w_ok, d_ok = sig.target_weights(probe, [1e6] * 5, sig.Params(), {})
    w_bad, d_bad = sig.target_weights(probe.drop(columns=[sig.REGIME_TICKER]),
                                      [1e6] * 5, sig.Params(), {})
    print(f"\n  signal with {sig.REGIME_TICKER} present  -> {len(w_ok)} names, "
          f"reason {d_ok.get('regime_reason')!r}")
    print(f"  signal with {sig.REGIME_TICKER} dropped  -> {len(w_bad)} names, "
          f"reason {d_bad.get('regime_reason')!r}")
    return {"identity_ok": ok, "car": car, "orders": orders, "history_default": default,
            "control": book}


# --------------------------------------------------- clause 2: the SPY-missing flatten

def clause2(frames: dict, control: dict) -> dict:
    banner("CLAUSE 2  the SPY-missing flatten, priced end to end at an outage rate")
    index = frames["close"].index
    rows = []
    for cost in (0.0, 2.0):
        base = control[cost] if cost in control else run(frames, cost)
        control[cost] = base
        base_car = car_of(base)
        print(f"\n  cost {cost:.1f} bp   control CAR {base_car:.3f}%")
        for rate in RATES:
            cars, events = [], []
            for seed in SEEDS:
                dates = event_dates(index, rate, seed)
                d = Defect("drop", dates, sig.REGIME_TICKER)
                book = run(frames, cost, d)
                cars.append(car_of(book))
                events.append(d.hits)
            mean_car = float(np.mean(cars))
            n = float(np.mean(events))
            per_year = n / (len(base) / 252.0)
            drop = base_car - mean_car
            per_event = drop / per_year if per_year else float("nan")
            breakeven = CAR_THRESHOLD / per_event if per_event > 0 else float("inf")
            rows.append({"cost": cost, "rate": rate, "events": n, "per_year": per_year,
                         "car": mean_car, "drop": drop, "per_event": per_event,
                         "breakeven": breakeven, "sd": float(np.std(cars, ddof=1))})
            print(f"    1 in {1/rate:5.0f}  events {n:6.1f} ({per_year:5.2f}/yr)  "
                  f"CAR {mean_car:7.3f}%  cost {drop:+7.3f} pts  "
                  f"{per_event:+7.4f} pts/outage  breakeven {breakeven:7.1f} outages/yr  "
                  f"(sd over {len(SEEDS)} seeds {np.std(cars, ddof=1):.3f})")
    best = min(r["breakeven"] for r in rows)
    print(f"\n  tightest break-even {best:.1f} outages/yr vs threshold {BREAKEVEN_THRESHOLD:.0f}")
    print(f"  CLAUSE 2 {'MATERIAL' if best <= BREAKEVEN_THRESHOLD else 'cosmetic'}")
    return {"rows": rows, "breakeven": best,
            "material": best <= BREAKEVEN_THRESHOLD}


# ------------------------------------------------------- clause 3: the all-NaN column

def clause3(frames: dict, control: dict) -> dict:
    banner("CLAUSE 3  the all-NaN column, on every traded name not just XLK")
    index = frames["close"].index
    if 0.0 not in control:                     # a DataFrame has no truth value; ask the key
        control[0.0] = run(frames, 0.0)
    base = control[0.0]
    base_car = car_of(base)
    rate, seed = 1.0 / 21.0, SEEDS[0]
    dates = event_dates(index, rate, seed)
    # Control funded sets on exactly these dates. The recorder names a ticker that is not in
    # the frame, so `_corrupt` is a no-op and the run is the control with a tap on it - the
    # funded sets are therefore comparable date-for-date rather than nearly so.
    rec = Defect("nan_col", dates, "__none__")
    run(frames, 0.0, rec)
    ref = rec.decisions

    print(f"  {len(dates)} corrupted sessions, 1 in {1/rate:.0f}, seed {seed}, "
          f"control CAR {base_car:.3f}%")
    hdr = f"    {'name':<8}{'CAR%':>9}{'delta':>9}{'sets differ':>13}{'%':>7}"
    print(hdr)
    print("    " + "-" * (len(hdr) - 4))
    rows = []
    for t in sig.traded_universe(sig.Params()):
        if t not in frames["close"].columns:
            continue
        d = Defect("nan_col", dates, t)
        book = run(frames, 0.0, d)
        car = car_of(book)
        diff = sum(1 for k, v in d.decisions.items()
                   if set(v) != set(ref.get(k, {})))
        pct = 100.0 * diff / max(1, len(d.decisions))
        rows.append({"ticker": t, "car": car, "delta": car - base_car,
                     "diff": diff, "pct": pct})
        print(f"    {t:<8}{car:>9.3f}{car - base_car:>+9.3f}{diff:>9} /{len(d.decisions):<4}{pct:>6.1f}%")
    worst = max(rows, key=lambda r: abs(r["delta"]))
    most = max(rows, key=lambda r: r["pct"])
    material = abs(worst["delta"]) > CAR_THRESHOLD or most["pct"] > SET_THRESHOLD
    print(f"\n  worst CAR move  {worst['ticker']} {worst['delta']:+.3f} pts "
          f"(threshold {CAR_THRESHOLD})")
    print(f"  most set churn  {most['ticker']} {most['pct']:.1f}% "
          f"(threshold {SET_THRESHOLD}%)")
    print(f"  CLAUSE 3 {'MATERIAL' if material else 'cosmetic'}")
    return {"rows": rows, "worst": worst, "most": most, "material": material}


# ----------------------------------------------------------- clause 4: the stale price

def clause4(frames: dict, control: dict) -> dict:
    banner("CLAUSE 4  the stale price, in both places it lands")
    closes = frames["close"]
    tickers = [t for t in sig.traded_universe(sig.Params()) if t in closes.columns]
    lo = closes.index.searchsorted(pd.Timestamp(START))
    r = closes[tickers].pct_change().iloc[lo:]
    flat = r.to_numpy().ravel()
    flat = flat[np.isfinite(flat)]
    err = np.abs(flat / (1.0 + flat))          # realized weight error at a stale price
    q = np.percentile(err, [50, 75, 90, 95, 99])
    print(f"  one-session |move| over {len(flat):,} name-days, {len(tickers)} names")
    print(f"    median {100*q[0]:6.3f}%   p75 {100*q[1]:6.3f}%   p90 {100*q[2]:6.3f}%   "
          f"p95 {100*q[3]:6.3f}%   p99 {100*q[4]:6.3f}%")
    over = 100.0 * float((err > BAND).mean())
    print(f"    sizing error above the {100*BAND:.0f}% no-trade band: {over:.2f}% of name-days")
    p95_material = q[3] > BAND
    print(f"    p95 {100*q[3]:.3f}% vs band {100*BAND:.0f}%  -> "
          f"{'MATERIAL' if p95_material else 'below the band'}")

    # --- and the book-level cost of RANKING on a stale close
    index = closes.index
    if 0.0 not in control:                     # a DataFrame has no truth value; ask the key
        control[0.0] = run(frames, 0.0)
    base = control[0.0]
    base_car = car_of(base)
    print(f"\n  ranking on a stale close (control CAR {base_car:.3f}%)")
    rows = []
    for mode, label in (("nan_last", f"{sig.REGIME_TICKER} last row NaN"),
                        ("stale", "whole frame one session short")):
        for rate in RATES:
            cars = []
            for seed in SEEDS[:3]:
                dates = event_dates(index, rate, seed)
                d = Defect(mode, dates, sig.REGIME_TICKER)
                cars.append(car_of(run(frames, 0.0, d)))
            mean_car = float(np.mean(cars))
            rows.append({"mode": mode, "rate": rate, "car": mean_car,
                         "delta": mean_car - base_car})
            print(f"    {label:<34} 1 in {1/rate:5.0f}  CAR {mean_car:7.3f}%  "
                  f"{mean_car - base_car:+7.3f} pts")
    material = p95_material or any(abs(x["delta"]) > CAR_THRESHOLD for x in rows)
    print(f"  CLAUSE 4 {'MATERIAL' if material else 'cosmetic'}")
    return {"quantiles": q.tolist(), "over_band": over, "rows": rows, "material": material}


# --------------------------------------------- clause 5: is refusing safer than flattening?

def clause5(frames: dict, control: dict) -> dict:
    banner("CLAUSE 5  the asymmetry that decides the fix: hold vs flatten, mean AND tail")
    index = frames["close"].index
    if 0.0 not in control:                     # a DataFrame has no truth value; ask the key
        control[0.0] = run(frames, 0.0)
    base = control[0.0]
    base_car = car_of(base)
    rate = 1.0 / 21.0
    out = {}
    hdr = (f"    {'arm':<10}{'CAR%':>9}{'delta':>9}{'Sharpe':>8}{'MaxDD%':>9}"
           f"{'worst day%':>12}{'orders':>9}")
    print(f"  1 in {1/rate:.0f} sessions, {len(SEEDS)} seeds, control CAR {base_car:.3f}%, "
          f"worst control day {100*base['ret'].min():.3f}%")
    print(hdr)
    print("    " + "-" * (len(hdr) - 4))
    # The flatten arm is the DEFECT itself (`drop` on REGIME_TICKER), not a blanked answer, so
    # both arms are what the deployed code would really do on the same corrupted sessions.
    arms = {"flatten": ("drop", sig.REGIME_TICKER), "hold": ("hold", None)}
    for arm, (mode, ticker) in arms.items():
        cars, sharpes, dds, worsts, orders = [], [], [], [], []
        for seed in SEEDS:
            dates = event_dates(index, rate, seed)
            d = Defect(mode, dates, ticker)
            book = run(frames, 0.0, d)
            s = describe(book, arm)
            cars.append(100.0 * s["CAR"] if s["CAR"] < 1.0 else s["CAR"])
            sharpes.append(s["Sharpe"])
            dds.append(s["MaxDD"])
            worsts.append(100.0 * float(book["ret"].min()))
            orders.append(int(s["orders"]))
        out[arm] = {"car": float(np.mean(cars)), "sharpe": float(np.mean(sharpes)),
                    "dd": float(np.mean(dds)), "worst": float(np.mean(worsts)),
                    "worst_max": float(np.min(worsts)), "orders": float(np.mean(orders))}
        print(f"    {arm:<10}{out[arm]['car']:>9.3f}{out[arm]['car'] - base_car:>+9.3f}"
              f"{out[arm]['sharpe']:>8.3f}{out[arm]['dd']:>9.3f}"
              f"{out[arm]['worst']:>12.3f}{out[arm]['orders']:>9,.0f}")
    mean_wins = out["hold"]["car"] > out["flatten"]["car"]
    tail_wins = (out["hold"]["dd"] <= out["flatten"]["dd"]
                 and out["hold"]["worst"] >= out["flatten"]["worst"])
    print(f"\n  hold beats flatten in the mean (CAR):  {mean_wins}")
    print(f"  hold beats flatten in the tail (MaxDD and worst day): {tail_wins}")
    print(f"  CLAUSE 5 -> the audit's 'exit 3' is "
          f"{'TAKEN on both columns' if mean_wins and tail_wins else 'taken with the tail stated'}")
    return {**out, "mean_wins": mean_wins, "tail_wins": tail_wins, "base_car": base_car}


# -------------------------------------------- clause 6: the gate's false positives

def clause6(frames: dict) -> dict:
    banner("CLAUSE 6  the gate's false positives, measured before the gate is written")
    closes = frames["close"]
    tickers = [t for t in sig.traded_universe(sig.Params()) if t in closes.columns]
    lo = closes.index.searchsorted(pd.Timestamp(START))
    window = closes[tickers].iloc[lo:]
    naive = window.isna().any(axis=1)
    print(f"  sessions {len(window):,} from {window.index[0].date()} to {window.index[-1].date()}")
    print(f"  the audit's predicate ('any universe column has a NaN close') fires on "
          f"{int(naive.sum()):,} sessions ({100*naive.mean():.2f}%)")
    per = window.isna().sum()
    for t in sorted(per[per > 0].index, key=lambda x: -per[x]):
        first = window[t].first_valid_index()
        print(f"    {t:<8}{int(per[t]):>6} NaN closes   first real close "
              f"{first.date() if first is not None else 'never'}")
    # the narrowed predicate: only names that have already printed a close
    started = window.notna().cummax()
    narrowed = (window.isna() & started).any(axis=1)
    print(f"\n  narrowed predicate ('a name that HAS a history is missing its close') fires on "
          f"{int(narrowed.sum()):,} sessions ({100*narrowed.mean():.2f}%)")
    if int(narrowed.sum()):
        for d in window.index[narrowed][:10]:
            bad = [t for t in tickers if pd.isna(window.at[d, t]) and started.at[d, t]]
            print(f"    {d.date()}  {bad}")
    ok = int(naive.sum()) == 0
    print(f"\n  WITHDRAWAL CONDITION: the audit's predicate fires on "
          f"{int(naive.sum())} sessions -> "
          f"{'take it as filed' if ok else 'NARROW the gate to names with established history'}")
    return {"naive": int(naive.sum()), "narrowed": int(narrowed.sum()),
            "sessions": len(window), "take_as_filed": ok}


# ------------------------------------------------------- clause 7: the fix, post-patch

def clause7(frames: dict, control: dict) -> dict:
    banner("CLAUSE 7  the fix: identity after the patch, and what is NOT fixed")
    book = run(frames, 0.0)
    s = describe(book, "control")
    car = car_of(book)
    orders = int(s["orders"])
    ok = abs(car - S25_DEPLOYED_CAR) < 1e-9 and orders == S25_DEPLOYED_ORDERS
    print(f"  post-patch CAR {car:.12f}%  orders {orders:,}  "
          f"delta {abs(car - S25_DEPLOYED_CAR):.2e}  {'EXACT' if ok else 'WITHDRAW THE PATCH'}")
    # clause 5's table has no control row - it prices two corrupted arms against each other -
    # so the reference the tail comparison needs is printed here, from the same book.
    print(f"  control reference for clause 5: Sharpe {s['Sharpe']:.3f}  MaxDD {s['MaxDD']:.3f}%  "
          f"worst day {100*float(book['ret'].min()):.3f}%  orders {orders:,}")

    import importlib
    import paper_trade as pt
    importlib.reload(pt)
    has = hasattr(pt, "data_faults")
    print(f"  paper_trade.data_faults present: {has}")
    if has:
        idx = pd.bdate_range("2026-08-03", periods=40)
        good = pd.DataFrame({t: np.linspace(100, 110, 40) for t in ("SPY", "QQQ", "XLK")},
                            index=idx)
        cases = {
            "healthy": good,
            "column missing": good.drop(columns=["SPY"]),
            "column all NaN": good.assign(XLK=np.nan),
            "last row NaN": good.assign(QQQ=list(good["QQQ"][:-1]) + [np.nan]),
        }
        for label, frame in cases.items():
            faults = pt.data_faults(frame, ["SPY", "QQQ", "XLK"], frame.index[-1],
                                    prev_session=idx[-2])
            print(f"    {label:<18} -> {faults or 'clean'}")
        stale = pt.data_faults(good.iloc[:-1], ["SPY", "QQQ", "XLK"], idx[-2],
                               prev_session=idx[-1])
        print(f"    {'as_of stale':<18} -> {stale or 'clean'}")
    return {"identity_ok": ok, "car": car, "orders": orders, "has_gate": has}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # Each stage is kept well inside AGENTS.md's 40-minute cap on a single command: one
    # `legs_simulate` pass over the 3,689-session sample is ~57 s, stage a is 22 of them,
    # b1 is 10, b2 is 22 and c is 1.
    ap.add_argument("--stage", choices=["a", "b1", "b2", "b3", "b", "c", "all"], default="all")
    args = ap.parse_args()

    # Loaded exactly as S-25..S-36 load it: the shipped traded universe and the FULL history,
    # so the warm-up before START is present and clause 1's identity is comparable with theirs.
    tickers = sig.traded_universe(sig.Params())
    frames = load_ohlcv(tickers)
    control: dict = {}

    if args.stage in ("a", "all"):
        c1 = clause1(frames)
        control[0.0] = c1["control"]
        clause2(frames, control)
    if args.stage in ("b1", "b", "all"):
        clause3(frames, control)
    if args.stage in ("b2", "b", "all"):
        clause4(frames, control)
    if args.stage in ("b3", "b", "all"):
        clause5(frames, control)
    if args.stage in ("c", "all"):
        clause6(frames)
        clause7(frames, control)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
