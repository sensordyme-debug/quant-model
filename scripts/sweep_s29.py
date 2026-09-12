#!/usr/bin/env python
"""S-29: should the champion's crisis switch read the market's volatility forecast instead of its own?

    python scripts/sweep_s29.py                 # every stage
    python scripts/sweep_s29.py --stage a       # identity + the forecast diagnostic
    python scripts/sweep_s29.py --stage b       # the books
    python scripts/sweep_s29.py --stage c       # the threshold shelf + the second implied series
    python scripts/sweep_s29.py --no-record     # do not append to the ledger

Volatility enters this book in exactly two places. S-28 priced the first - the vol target,
`target_vol / sigma`, which decides SIZE and which S-28 measured binds on only 2.8% of
sessions because the flat margin budget pins the book at ~1.50x gross the rest of the time.
The second is `risk_on`, the crisis switch, which decides DIRECTION: when SPY's trailing
20-session realized volatility exceeds 1.5x its own one-year median the book holds nothing
at all, and it has been off on 590 of 3,690 sessions (16.0%) since S-1.

    A realized estimate is a backward-looking measurement of a forward-looking quantity,
    and there is a market that quotes the forward-looking one directly.

That is the whole hypothesis. The switch is asking "is a crisis happening?" using twenty
sessions that have already happened; VIX is the price of finding out what the next thirty
days will do, and it is the one input this repository has never tried that is NEW INFORMATION
rather than a new rule on the same bars (the owner-side note of 2026-09-11). S-25 sharpens
the motivation: 94% of this book's return and all of its measurable alpha is earned
overnight, in the leg that carries gap risk, which is precisely the risk an option prices.

The mechanism is a new, default-inert hook in the shipped `signals.py`
(`S1_REGIME_SERIES` / `set_regime_series`, F-3's `S1_ML_SCORES` and S-28's `S1_VOL_RETURNS`
pattern) that supplies the LEVEL the switch compares to its own trailing median, and nothing
else. The gate is scale-free - `level >= threshold * median(level)` - so a VIX quoted in
percentage points and a realized vol quoted as a fraction produce the same arithmetic and no
constant is re-tuned. The environment variable is unset in every deployed path and the I-1
gate (`scripts/compare_orders.py`) was re-run after the edit.

PRE-REGISTERED before the first number, six clauses
---------------------------------------------------
(1) IDENTITY. Installing the SHIPPED realized level through the hook must reproduce the
    deployed cell BIT FOR BIT - CAR 22.192150%, 5,052 orders - because that series is by
    construction what `risk_on` already computes. A second identity is required and is what
    makes the off-rates below readable: an independently computed gate series (rolling
    median of the level, same threshold) must reproduce the book's own risk-off days
    exactly. If either fails, the hook is changing something other than the switch's input
    and nothing below may be read.

(2) DIAGNOSTIC BEFORE BOOK, which is S-27's rule and which S-28 obeyed. The claim only makes
    sense if the implied level forecasts SPY's NEXT 21 sessions of realized volatility better
    than the trailing 20-session realized estimate does. If it does not, the premise is empty
    and the primary is expected to fail with the reason already on the page. Reported beside
    it: how often each gate is off, how often they disagree, and what the deployed book
    earned on each gate's off days - because a switch is only worth its input if the days it
    removes are days worth removing.

(3) PRIMARY. The VIX-driven gate at the SHIPPED threshold (1.5x its own trailing 252-session
    median), everything else untouched, judged on `evaluate.py`'s criteria transplanted here:
    beat the deployed book on CAR, Sharpe no more than 0.03 below, drawdown no more than 1.0
    point worse and never above 35% absolute - in the full period AND in BOTH halves, at the
    same cost model (2 bp of one-way spread + IBKR Pro financing on the deployed convention).

(4) SHELF, NOT SPIKE. A threshold grid for both inputs. The primary is promotable only if its
    two grid neighbours also beat the deployed book on CAR. A win at exactly one threshold is
    a fitted constant and is refused.

(5) PLACEBO. The identical gate driven by a VIX series made STALE by 5 sessions. If the stale
    gate does as well as the live one, what is being measured is the LEVEL of volatility and
    not the market's forecast of it, and the primary is withdrawn. Robustness beside it: SPY's
    own 1-month ATM implied volatility from the Theta store (2017-2026, O-1's `iv_regime`),
    an independent instrument on a shorter window, which must agree in sign.

(6) EXPECTATION, written down first so this run can be wrong rather than merely reported.
    VIX is smoother and more persistent than 20-session realized vol and it carries a
    variance risk premium, so at the same multiple of its own median it is expected to fire
    LESS often. S-20 measured that the off-state is cash and that a defensive holding does not
    help, so fewer off days is a straight increase in exposure: THE MOST LIKELY OUTCOME IS
    MORE RETURN AND MORE DRAWDOWN, refused on the drawdown tolerance - a leverage change
    dressed as a forecast, which is exactly the trap S-28's raw legs fell into. The column
    that separates timing from exposure is therefore pre-registered rather than reached for
    afterwards: a threshold calibrated ON THE IN-SAMPLE HALF ONLY so the VIX gate is off on
    the same fraction of sessions as the shipped gate, then applied unchanged to the full
    period and to the out-of-sample half. Only that column can be read as a statement about
    WHEN to step aside.

Nothing here changes a default. `champion.json`, `live/*` and the scheduled tasks are
untouched; every row this script writes is DIAGNOSTIC.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                                          # noqa: E402
import rates                                                   # noqa: E402
import regime_data                                             # noqa: E402
from lean_prices import load_ohlcv                             # noqa: E402
from sweep_s19 import START_EQUITY, paired, summarize          # noqa: E402
from sweep_s25 import legs_simulate                            # noqa: E402
from sweep_s28 import drawdowns                                # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
START = "2012-01-03"
END = "2026-09-04"
HALVES = [("IS 2012-2019", START, "2019-12-31"), ("OOS 2020-2026", "2020-01-02", END)]

S25_DEPLOYED_CAR = 22.192150170492255      # clause 1: S-25/S-26/S-27/S-28's own printed figure
S25_DEPLOYED_ORDERS = 5052

#: evaluate.py's criteria, transplanted to this harness (champion.json "criteria").
SHARPE_TOL = 0.03
DD_TOL = 1.0
DD_LIMIT = 35.0

FWD = 21                                   # sessions of forward realized vol in the diagnostic
SHELF = (1.25, 1.40, 1.50, 1.60, 1.75, 2.00)
STALE = 5                                  # clause 5's staleness, in sessions

#: The second implied series starts 2017-01-03 and the gate needs 252 sessions of it before
#: it can speak, so its own window starts a year later. Stated here rather than discovered.
IV_START = "2018-01-16"


# ------------------------------------------------------------------ the levels themselves

def shipped_level(frames: dict, p: sig.Params) -> pd.Series:
    """Exactly what `risk_on` computes today, over the whole store.

    `regime_level` builds this inside each 307-bar decision window; a rolling estimate of
    width 20 is identical on the last 252 points of that window and on the full series, which
    is why installing this through the hook is expected to be bit-identical.
    """
    spy = frames["close"][sig.REGIME_TICKER]
    return spy.pct_change().rolling(p.regime_vol_window).std(ddof=1) * np.sqrt(sig.TRADING_DAYS)


def levels(frames: dict, p: sig.Params) -> dict[str, pd.Series | None]:
    """Every crisis-switch input this study prices. `None` is the shipped path, untouched."""
    idx = frames["close"].index
    vix = regime_data.load(regime_data.VIX_CSV).reindex(idx).ffill().dropna()
    out = {
        "shipped (no hook)": None,
        "realized through the hook": shipped_level(frames, p),
        "vix": vix,
        f"vix stale {STALE}d": vix.shift(STALE).dropna(),
    }
    if regime_data.SPY_IV_CSV.exists():
        out["spy atm iv 1m"] = regime_data.load(regime_data.SPY_IV_CSV).reindex(idx).ffill().dropna()
    return out


def gate_series(level: pd.Series, threshold: float, median_window: int) -> pd.Series:
    """Boolean risk-ON per date, computed outside the book. Clause 1's second identity.

    Identical arithmetic to `risk_on`: the level against `threshold` times the median of the
    trailing `median_window` observations of the same level, the last of which is the date
    itself. A date with fewer than `median_window` observations behind it is NaN, which is the
    book's "insufficient vol history" branch.
    """
    med = level.rolling(median_window).median()
    on = level < threshold * med
    return on.where(med.notna() & level.notna())


def off_rate(level: pd.Series, p: sig.Params, start: str, end: str,
             index: pd.DatetimeIndex) -> tuple[float, pd.Series]:
    """Share of decision dates the gate is OFF, and the gate itself, over a window.

    The gate is evaluated on the DECISION date, which is the session before the fill, exactly
    as the book reads it - so the series is shifted onto the fill dates before it is counted.
    """
    on = gate_series(level, p.regime_threshold, p.regime_median_window).reindex(index)
    fill_on = on.shift(1)                       # decided on d-1, in force on d
    w = fill_on.loc[(fill_on.index >= pd.Timestamp(start)) & (fill_on.index <= pd.Timestamp(end))]
    w = w.dropna()
    return (float((~w.astype(bool)).mean()) if len(w) else float("nan")), fill_on


# --------------------------------------------------------------- clause 2: the diagnostic

def forecast_table(frames: dict, lv: dict, p: sig.Params, start: str, end: str) -> pd.DataFrame:
    """Does each level forecast SPY's next 21 sessions of realized volatility?

    Correlation of logs (vol is lognormal-ish and a correlation of levels is otherwise decided
    by a handful of crisis observations), on the sessions every level is available for, so the
    rows are comparable to each other rather than each to its own longest sample.
    """
    spy = frames["close"][sig.REGIME_TICKER]
    fwd = (spy.pct_change().rolling(FWD).std(ddof=1) * np.sqrt(sig.TRADING_DAYS)).shift(-FWD)
    rows = []
    for name, level in lv.items():
        if level is None:
            continue
        m = pd.DataFrame({"x": level.reindex(fwd.index), "y": fwd}).dropna()
        m = m[(m.index >= pd.Timestamp(start)) & (m.index <= pd.Timestamp(end))]
        m = m[(m > 0).all(axis=1)]
        if len(m) < 100:
            continue
        x, y = np.log(m["x"].to_numpy()), np.log(m["y"].to_numpy())
        rows.append({"level": name, "corr(log, log fwd 21d realized)": float(np.corrcoef(x, y)[0, 1]),
                     "obs": len(m), "first": str(m.index[0].date()), "last": str(m.index[-1].date())})
    return pd.DataFrame(rows).set_index("level")


# --------------------------------------------------------------------- clause 3-6: books

def run(frames: dict, params: sig.Params, level: pd.Series | None, *, spread: float,
        fin: dict | None, start: str = START, end: str = END,
        threshold: float | None = None, diag_out: list | None = None) -> pd.DataFrame:
    p = params if threshold is None else replace(params, regime_threshold=threshold)
    sig.set_regime_series(level)
    try:
        return legs_simulate(frames, p, "both", start, end, spread, fin, diag_out=diag_out)
    finally:
        sig.set_regime_series(None)


def describe(book: pd.DataFrame, label: str) -> dict:
    s = summarize(book, label)
    s["gross_x"] = float(book["gross_x"].mean())
    s["turnover_x"] = float(book["turnover"].sum() / START_EQUITY / (len(book) / 252))
    return s


def table(rows: list[dict]) -> None:
    hdr = (f"{'cell':<28}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
           f"{'gross':>7}{'off%':>7}{'orders':>8}{'turn x/yr':>11}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        off = r.get("off_pct")
        off_s = f"{off:>7.1f}" if off is not None and np.isfinite(off) else f"{'-':>7}"
        print(f"{r['cell']:<28}{r['sessions']:>6}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}"
              f"{r['MaxDD']:>8.3f}{r['std']:>7.3f}{r['gross_x']:>7.2f}{off_s}"
              f"{r['orders']:>8,}{r['turnover_x']:>11.1f}")


def verdict(cand: dict, base: dict) -> tuple[bool, str]:
    """champion.json's criteria on one window; the caller adds the halves."""
    why = []
    if cand["CAR"] <= base["CAR"]:
        why.append(f"CAR {cand['CAR']:.3f} <= {base['CAR']:.3f}")
    if cand["Sharpe"] < base["Sharpe"] - SHARPE_TOL:
        why.append(f"Sharpe {cand['Sharpe']:.3f} < {base['Sharpe'] - SHARPE_TOL:.3f}")
    if cand["MaxDD"] > base["MaxDD"] + DD_TOL:
        why.append(f"DD {cand['MaxDD']:.3f} > {base['MaxDD'] + DD_TOL:.3f}")
    if cand["MaxDD"] > DD_LIMIT:
        why.append(f"DD {cand['MaxDD']:.3f} past the {DD_LIMIT:g}% absolute limit")
    return (not why), "; ".join(why) if why else "passes every criterion"


def matched_threshold(level: pd.Series, base_level: pd.Series, p: sig.Params,
                      index: pd.DatetimeIndex, start: str, end: str) -> tuple[float, float, float]:
    """Clause 6: the threshold that equalizes off-rates ON THE GIVEN WINDOW ONLY.

    Solved on the in-sample half and then applied unchanged, so the out-of-sample column is
    causal. Bisection on a monotone quantity (a higher threshold can only fire less often).
    """
    target, _ = off_rate(base_level, p, start, end, index)
    lo, hi = 0.80, 6.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        r, _ = off_rate(level, replace(p, regime_threshold=mid), start, end, index)
        if not np.isfinite(r):
            break
        if r > target:                        # fires too often -> raise the bar
            lo = mid
        else:
            hi = mid
    thr = 0.5 * (lo + hi)
    got, _ = off_rate(level, replace(p, regime_threshold=thr), start, end, index)
    return thr, target, got


# ------------------------------------------------------------------------------- ledger

def record(rows: list[dict], note: str, no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s29_regime", "class": "book",
                "tag": f"S-29 {r['cell'].strip()} ({note})", "commit": "", "run_dir": "",
                "track": "S-29", "start": r.get("start", START), "end": r.get("end", END),
                "stats": {"Sessions": str(r["sessions"]),
                          "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.3f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees']:.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")


# ---------------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="abc",
                    help="a = identity + diagnostic, b = the books, c = the shelf and the "
                         "second implied series")
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    params = sig.Params()
    tickers = sig.traded_universe(params)
    frames = load_ohlcv(tickers)
    index = frames["close"].index
    lv = levels(frames, params)
    fin = {"rates": rates.load(), "spread": 0.0}
    note = f"pandas book, {args.start}..{args.end}, IBKR Pro financing, "\
           f"{args.spread_bps:g} bp screen - DIAGNOSTIC, not promotable"
    ledger_rows: list[dict] = []

    print(f"store: {len(tickers)} tickers, {index[0].date()} .. {index[-1].date()}   "
          f"window {args.start} .. {args.end}")
    print(f"sleeve: {', '.join(tickers)}")
    print(f"levels: {', '.join(k for k in lv if lv[k] is not None)}\n")

    # ---------------------------------------------------------------- stage a
    if "a" in args.stage:
        print("=" * 100)
        print("CLAUSE 1  identity")
        print("=" * 100)
        base0 = run(frames, params, None, spread=0.0, fin=None, start=args.start, end=args.end)
        dg: list = []
        hook0 = run(frames, params, lv["realized through the hook"], spread=0.0, fin=None,
                    start=args.start, end=args.end, diag_out=dg)
        b, h = describe(base0, "shipped"), describe(hook0, "hook")
        ok = (abs(b["CAR"] - S25_DEPLOYED_CAR) < 1e-9 and b["orders"] == S25_DEPLOYED_ORDERS
              and abs(h["CAR"] - b["CAR"]) < 1e-9 and h["orders"] == b["orders"])
        print(f"  shipped path                CAR {b['CAR']:.6f}%  orders {b['orders']:,}  "
              f"end ${b['end_equity']:,.2f}")
        print(f"  realized through the hook   CAR {h['CAR']:.6f}%  orders {h['orders']:,}  "
              f"end ${h['end_equity']:,.2f}")
        print(f"  S-25's printed figure       CAR {S25_DEPLOYED_CAR:.6f}%  orders "
              f"{S25_DEPLOYED_ORDERS:,}")
        print(f"  -> {'PASS' if ok else 'FAIL'}: the hook is the switch's input and nothing else")

        # second identity: the standalone gate must reproduce the book's own risk-off days
        diag = pd.DataFrame(dg).set_index("date")
        book_off = (diag["reason"] == "risk-off")
        _, fill_on = off_rate(lv["realized through the hook"], params, args.start, args.end, index)
        mine = (~fill_on.reindex(diag.index).astype("boolean")).astype(bool)
        agree = int((book_off == mine).sum())
        ok2 = agree == len(diag)
        print(f"  standalone gate vs the book's own risk-off days   {agree:,}/{len(diag):,}  "
              f"{'PASS' if ok2 else 'FAIL'}")
        if not (ok and ok2):
            print("\n  clause 1 failed; stopping rather than reading a book that is not the "
                  "deployed one.")
            return 1

        print("\n" + "=" * 100)
        print(f"CLAUSE 2  does the level forecast the NEXT {FWD} sessions of realized "
              f"volatility?")
        print("=" * 100)
        ft = forecast_table(frames, lv, params, args.start, args.end)
        print(f"  {'level':<28}{'corr':>9}{'obs':>9}   window")
        print("  " + "-" * 64)
        for name, row in ft.iterrows():
            print(f"  {name:<28}{row['corr(log, log fwd 21d realized)']:>9.4f}"
                  f"{int(row['obs']):>9,}   {row['first']} .. {row['last']}")

        print("\n  the two gates, at the shipped threshold "
              f"{params.regime_threshold:g}x their own {params.regime_median_window}-session median:")
        gates = {}
        for name in ("realized through the hook", "vix", f"vix stale {STALE}d", "spy atm iv 1m"):
            if name not in lv:
                continue
            r, on = off_rate(lv[name], params, args.start, args.end, index)
            gates[name] = on
            print(f"    {name:<28}off on {100 * r:>5.1f}% of sessions")

        # The decisive column, and it must be measured on a book that is NEVER gated - asking
        # what the deployed book earned on its own risk-off days is circular, because it is
        # flat on exactly those days by construction. `threshold=99` is a multiple no series
        # in this file reaches, so the gate runs and never fires.
        ungated = run(frames, params, None, spread=0.0, fin=None, start=args.start,
                      end=args.end, threshold=99.0)
        ung = ungated.set_index("date")["ret"]
        a = gates["realized through the hook"].reindex(ung.index)
        v = gates["vix"].reindex(ung.index)
        r_off, v_off = ~a.fillna(True).astype(bool), ~v.fillna(True).astype(bool)
        print(f"\n    agreement on {len(ung):,} sessions: both off {int((r_off & v_off).sum()):,}"
              f"   realized only {int((r_off & ~v_off).sum()):,}   vix only "
              f"{int((~r_off & v_off).sum()):,}   disagree "
              f"{int((r_off ^ v_off).sum()):,} "
              f"({100 * float((r_off ^ v_off).mean()):.1f}%)")

        def leg(mask, label):
            x = ung[mask]
            if len(x) == 0:
                return
            t = float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if x.std(ddof=1) else float("nan")
            print(f"    {label:<34}{1e4 * x.mean():>+9.2f} bps   t {t:>+6.2f}   "
                  f"{len(x):>5,} sessions")

        print("\n  what an UNGATED version of this book earns on the sessions each gate "
              "removes (bps/day, 0 bp, no financing):")
        leg(pd.Series(True, index=ung.index), "every session")
        for name, on in gates.items():
            leg(~on.reindex(ung.index).fillna(True).astype(bool), f"{name} off")
        print("  and on the sessions the two gates DISAGREE about:")
        leg(r_off & ~v_off, "realized off, vix on")
        leg(~r_off & v_off, "vix off, realized on")
        leg(r_off & v_off, "both off")

    # ---------------------------------------------------------------- stage b
    if "b" in args.stage:
        print("\n" + "=" * 100)
        print(f"CLAUSE 3 / 5 / 6  the books, {args.spread_bps:g} bp one-way spread + "
              f"IBKR Pro financing")
        print("=" * 100)

        thr_m, target_off, got_off = matched_threshold(
            lv["vix"], lv["realized through the hook"], params, index, START, HALVES[0][2])
        print(f"  clause 6 match, solved on {HALVES[0][0]} only: threshold {thr_m:.4f} puts the "
              f"vix gate off on {100 * got_off:.1f}% of that half against the shipped "
              f"{100 * target_off:.1f}%\n")

        cells = [("shipped (no hook)", lv["shipped (no hook)"], None),
                 ("vix @1.50 (primary)", lv["vix"], None),
                 (f"vix stale {STALE}d (placebo)", lv[f"vix stale {STALE}d"], None),
                 (f"vix @{thr_m:.2f} (off-matched)", lv["vix"], thr_m),
                 # Reference, not a candidate: what the switch is worth at all on THIS book.
                 # S-15 (b) priced it at 22.383% / DD 31.4 on the retired 3x champion at zero
                 # spread; the current book has never been asked. 99 is a multiple no series
                 # in this file reaches, so the gate runs and never fires.
                 ("no gate at all (reference)", None, 99.0)]

        books, rows = {}, []
        for cell, level, thr in cells:
            bk = run(frames, params, level, spread=args.spread_bps, fin=fin,
                     start=args.start, end=args.end, threshold=thr)
            books[cell] = bk
            r = describe(bk, cell)
            p_eff = params if thr is None else replace(params, regime_threshold=thr)
            src = lv["realized through the hook"] if level is None else level
            r["off_pct"] = 100 * off_rate(src, p_eff, args.start, args.end, index)[0]
            r["start"], r["end"] = args.start, args.end
            rows.append(r)
        table(rows)
        ledger_rows += rows

        base = rows[0]
        print(f"\n  paired daily return difference against '{base['cell']}' (bps/day):")
        for cell, _l, _t in cells[1:]:
            pr = paired(books[cell], books[base["cell"]], cell, base["cell"])
            print(f"    {cell:<30}{pr['bps_per_day']:>+9.3f}  t {pr['t']:>+6.2f}  "
                  f"({pr['days']:,} days)")

        print("\n  the halves:")
        half_rows = {}
        for label, s, e in HALVES:
            hr = []
            for cell, level, thr in cells:
                bk = run(frames, params, level, spread=args.spread_bps, fin=fin,
                         start=s, end=e, threshold=thr)
                r = describe(bk, f"{cell} | {label}")
                p_eff = params if thr is None else replace(params, regime_threshold=thr)
                src = lv["realized through the hook"] if level is None else level
                r["off_pct"] = 100 * off_rate(src, p_eff, s, e, index)[0]
                r["start"], r["end"] = s, e
                hr.append(r)
            half_rows[label] = hr
            print(f"\n  {label}")
            table(hr)
            ledger_rows += hr

        print("\n  verdicts (champion.json criteria, full period and both halves):")
        for i, (cell, _l, _t) in enumerate(cells[1:], start=1):
            ok_full, why_full = verdict(rows[i], rows[0])
            parts = [f"full {'PASS' if ok_full else 'FAIL'} ({why_full})"]
            for label, _s, _e in HALVES:
                hr = half_rows[label]
                ok_h, why_h = verdict(hr[i], hr[0])
                parts.append(f"{label} {'PASS' if ok_h else 'FAIL'} ({why_h})")
            print(f"    {cell}")
            for part in parts:
                print(f"      {part}")

        print("\n  the three deepest drawdowns of each book (full period):")
        for cell, _l, _t in cells:
            eps = drawdowns(books[cell], 3)
            txt = "   ".join(f"{e['depth']:.1f}% {e['peak']}->{e['trough']}" for e in eps)
            print(f"    {cell:<30}{txt}")

    # ---------------------------------------------------------------- stage c
    if "c" in args.stage:
        print("\n" + "=" * 100)
        print("CLAUSE 4  the threshold shelf - a win at exactly one threshold is a fitted "
              "constant")
        print("=" * 100)
        rows = []
        for name in ("realized through the hook", "vix"):
            for thr in SHELF:
                bk = run(frames, params, lv[name], spread=args.spread_bps, fin=fin,
                         start=args.start, end=args.end, threshold=thr)
                r = describe(bk, f"{name.split()[0]} @{thr:.2f}")
                r["off_pct"] = 100 * off_rate(
                    lv[name], replace(params, regime_threshold=thr), args.start, args.end, index)[0]
                r["start"], r["end"] = args.start, args.end
                rows.append(r)
        table(rows)
        ledger_rows += rows

        if "spy atm iv 1m" in lv:
            print("\n" + "=" * 100)
            print("CLAUSE 5b  the second implied series, on its own shorter window "
                  f"({IV_START} .. {args.end})")
            print("=" * 100)
            rows = []
            for cell, level in (("shipped (no hook)", None),
                                ("vix @1.50", lv["vix"]),
                                ("spy atm iv @1.50", lv["spy atm iv 1m"])):
                bk = run(frames, params, level, spread=args.spread_bps, fin=fin,
                         start=IV_START, end=args.end)
                r = describe(bk, cell)
                src = lv["realized through the hook"] if level is None else level
                r["off_pct"] = 100 * off_rate(src, params, IV_START, args.end, index)[0]
                r["start"], r["end"] = IV_START, args.end
                rows.append(r)
            table(rows)
            ledger_rows += rows

    record(ledger_rows, note, args.no_record)
    if ledger_rows and not args.no_record:
        print(f"\nrecorded {len(ledger_rows)} DIAGNOSTIC rows under daily/s29_regime")
    return 0


if __name__ == "__main__":
    sys.exit(main())
