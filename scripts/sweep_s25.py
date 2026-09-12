#!/usr/bin/env python
"""S-25: which half of the day does the deployed daily champion actually get paid in?

    python scripts/sweep_s25.py                    # decomposition + controls + screen
    python scripts/sweep_s25.py --cross            # re-run the split on the official crosses
    python scripts/sweep_s25.py --no-record        # do not append to the ledger

Every figure in this repository about the daily sleeve is a close-to-close number. The book
holds nine ETFs around the clock, so each session it is paid twice: once while the market is
shut (the previous close into the open) and once while it is open (the open into the close).
Nothing here has ever separated them, and the published equity-premium literature says the
two legs are not the same object - the overnight leg is where the index premium is usually
found. This iteration measures the split on the deployed book, tests the two conditional
books it implies, and prices the one number that decides them.

The book is S-19's share-level pandas harness, which runs the *shared* `signals.py` and was
validated at corr 0.99650 against the champion's own LEAN equity curve. This script adds
per-session leg attribution to it and two flat-in-one-leg variants.

PRE-REGISTERED before the first number, five clauses
----------------------------------------------------
(1) IDENTITY. The two legs plus the day's fees, slippage and interest must reproduce the
    deployed book's own return session by session (checked to 1e-6 of equity), and the
    `both` mode must reproduce `sweep_s19.simulate(..., fill="close")` to the digit. If it
    does not, the attribution is measuring something other than the deployed book and
    nothing below it may be read.

(2) CONTROL, which F-5 made compulsory on the intraday side and S-15/S-20 on this one. A
    long book collects whatever the overnight leg pays whether or not its ranking has any
    content, so the leg is quoted against an ALWAYS-INVESTED control over the identical
    sessions - the equal-weight nine-name sleeve and SPY alone - scaled each day to the
    book's own gross exposure. The forecast is the DIFFERENCE, paired by session, and only
    the difference may be called selection.

(3) STRATEGY SCREEN. `overnight` (hold the book from the close to the next open, flat all
    session) and `intraday` (flat overnight, hold from the open to the close) are promotable
    only if they beat the deployed book on CAR, with drawdown no more than 1.0 point worse,
    in BOTH halves, at the same cost model - `evaluate.py`'s criteria transplanted to the
    harness that can express them. The expectation is written down first, so the result can
    be wrong rather than merely reported: BOTH ARE EXPECTED TO FAIL ON COST BY A FACTOR, not
    a margin. Each turns the whole book over twice a day; at 1.5x gross and 2 bp a side that
    is ~6 bps/day of spread alone against a total book return of ~9 bps/day, and no leg
    difference measured anywhere is that large. The deliverable in that case is the
    BREAKEVEN one-way cost, which is a durable property of the split.

(4) BENCHMARK DEFECT. The whole split hinges on one price, and S-24 established what that
    price is: the daily store's close IS the official closing cross to the cent, but its
    open is the first consolidated print, not the opening auction, and it wobbles 0.6-1.5
    bps a day for six of the nine names. So the decomposition is re-run on the official
    opening crosses (`data/auctions`, 2016-2026, S-24's `cross_frames`), and the two must
    agree in SIGN and to within 1.0 bps/day on the overnight leg, or what is being measured
    is Yahoo's print convention rather than the market's overnight session.

(5) DIVIDENDS. The store is back-adjusted, so a dividend is credited inside the overnight
    leg on the ex-date, which is exactly where a holder receives it. That is a feature of
    the measurement and not a defect, but it means the overnight leg carries the sleeve's
    entire yield and the intraday leg carries none of it.

Nothing here changes a default. The deployed strategy, its config and its schedule are
untouched; `both` is the deployed book, and the two variants exist to be priced.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                                       # noqa: E402
import rates                                                # noqa: E402
from lean_prices import load_ohlcv                          # noqa: E402
from sweep_s19 import (MIN_ORDER_VALUE, START_EQUITY, commission, paired,  # noqa: E402
                       simulate, summarize, tstat)

LEDGER = REPO / "research" / "experiments.jsonl"
START = "2012-01-03"
END = "2026-09-04"
CROSS_START = "2016-01-04"
HALVES = [("IS 2012-2019", START, "2019-12-31"), ("OOS 2020-2026", "2020-01-02", END)]
MODES = ["both", "overnight", "intraday"]


# ------------------------------------------------------------------- the attributing book

def _ols_beta(y: list[float], x: list[float]) -> float:
    """Slope of `y` on `x`, both equity-normalized leg returns. S-26's hedge sizer."""
    ya, xa = np.asarray(y, dtype=float), np.asarray(x, dtype=float)
    ok = np.isfinite(ya) & np.isfinite(xa)
    ya, xa = ya[ok], xa[ok]
    if len(ya) < 2 or xa.var(ddof=1) == 0:
        return float("nan")
    return float(np.cov(ya, xa, ddof=1)[0, 1] / xa.var(ddof=1))


def legs_simulate(frames: dict, params, mode: str, start: str, end: str,
                  slippage_bps: float = 0.0, financing: dict | None = None,
                  lag: int = 0, divs: pd.DataFrame | None = None,
                  hedge: dict | None = None, scale: float = 1.0,
                  diag_out: list | None = None, flat_frac: float = 0.0,
                  band: float | None = None, skip: dict | None = None) -> pd.DataFrame:
    """S-19's deployed book with the day's P&L split into its two legs.

    `mode="both"` is the deployed convention exactly: decide on the closes through i-1, fill
    at the close of i, carry the position through the next overnight and the next session.
    Positions carried into session i were therefore established at close[i-1], so the day's
    mark-to-market splits cleanly at open[i] with no assumption at all.

    `mode="overnight"` liquidates the whole book at open[i] and re-establishes the day's
    targets at close[i]; `mode="intraday"` establishes them at open[i] and liquidates at
    close[i]. Both decide on exactly the same information as the deployed book - the closes
    through i-1 - so the only thing that moves between the three is which leg is held.

    S-26 adds two optional arguments and changes nothing when they are absent (S-22's
    precedent on `sweep_s19.simulate`, so every S-25 row stays bit-identical).

    `scale` multiplies the shipped target weights, which is how a risk-matched column is
    priced on the real machinery: gross, commission and the financed debit all follow.

    `hedge` is `{"ratio": h, "leg": "intraday"|"overnight", "cost_bps": c, "window": n}` and
    shorts `h * beta * equity` of the index over that leg, where `beta` is the OLS slope of
    the book's own *unhedged* leg return on the index's, over the trailing `window` sessions
    - so it is causal (history through i-1 only) and it is in the right units by
    construction. `cost_bps` is charged on the hedge notional once per session, i.e. one
    round trip. The hedge P&L and its cost are booked to cash, never to `pnl_on`/`pnl_id`,
    so the leg columns stay a measurement of the equity book and the regression that sizes
    the next hedge is not fed its own output.

    S-30 adds one more default-inert argument, same precedent. `flat_frac` (only read when
    `mode="both"`, ignored at 0.0) sells that fraction of every position at the open and
    leaves the close-side rebalance to buy it back, so the day's target is re-established in
    ONE trade rather than in a liquidation followed by a reload. Intermediate values are the
    equity-book analogue of S-26's futures overlay: the book holds `1 - flat_frac` of its
    targets through the session and all of them overnight.

    `flat_frac=1.0` is an overnight-only book reached through the deployed rebalance, and
    S-30 measured that it is BIT-IDENTICAL to `mode="overnight"` - once nothing is held
    through the session the reload IS the rebalance, so there is no netting to save. That is
    a result, not a defect: see the `delta_note` in `research/champion.json`.

    S-32 adds two more default-inert arguments, same precedent, for the execution no-trade
    band the owner has had open since 2026-09-09. `band` replaces `MIN_ORDER_VALUE` in the
    rebalance plan - the fraction of equity below which a rebalancing delta is skipped - and
    `None` leaves the shipped 0.01 and every earlier row bit-identical. `skip` is
    `{"p": float, "seed": int}` and drops each candidate order at random with probability
    `p`; it is S-32's placebo, which holds the NUMBER of skipped orders fixed and changes
    only WHICH ones, so "the band buys something" can be separated from "the book trades
    less". Both act on the rebalance plan only, never on a liquidation leg.
    """
    closes, opens = frames["close"], frames["open"]
    tickers = [t for t in sig.traded_universe(params) if t in closes.columns]
    index = closes.index
    i0 = max(index.searchsorted(pd.Timestamp(start)) + 1, lag + params.history_bars)
    i1 = min(index.searchsorted(pd.Timestamp(end), side="right"), len(index))

    equity = cash = START_EQUITY
    positions: dict[str, int] = {}
    equity_curve = [START_EQUITY]
    state: dict = {}
    rows = []
    missing_open = 0

    fin_rates = (financing or {}).get("rates") or {}
    fin_shift = float((financing or {}).get("spread", 0.0))
    fin_first, fin_final = (min(fin_rates), max(fin_rates)) if fin_rates else ("", "")

    # --- S-26's hedge: the index legs it trades against, and the causal beta history
    hg_leg = (hedge or {}).get("leg", "intraday")
    hg_ratio = float((hedge or {}).get("ratio", 0.0))
    hg_cost = float((hedge or {}).get("cost_bps", 0.0))
    hg_window = int((hedge or {}).get("window", 60))
    hg_bench = (hedge or {}).get("bench", "SPY")
    if hedge is not None:
        bc, bo = closes[hg_bench], opens[hg_bench]
        bench_on = (bo / bc.shift(1) - 1.0).to_numpy()
        bench_id = (bc / bo - 1.0).to_numpy()
    hist_book: list[float] = []
    hist_bench: list[float] = []

    # --- S-32: the no-trade band and its placebo. Both inert at their defaults.
    band_x = MIN_ORDER_VALUE if band is None else float(band)
    skip_p = float((skip or {}).get("p", 0.0))
    rng = np.random.default_rng(int((skip or {}).get("seed", 0)))

    for i in range(i0, i1):
        interest, prev_mark = 0.0, equity
        if fin_rates and i > i0:
            days = (index[i].date() - index[i - 1].date()).days
            stamp = min(max(index[i].date().isoformat(), fin_first), fin_final)
            interest = rates.accrual(cash, fin_rates[stamp], days, fin_shift)
            cash += interest
            equity += interest
            equity_curve[-1] += interest

        prev_close_row, open_row, close_row = closes.iloc[i - 1], opens.iloc[i], closes.iloc[i]

        # --- the overnight leg on the position carried in, before anything trades today
        pnl_on = 0.0
        pnl_div = 0.0
        gross_in = 0.0
        div_row = divs.iloc[i] if divs is not None else None
        for t, n in positions.items():
            if not n:
                continue
            c0 = float(prev_close_row.get(t, np.nan))
            o1 = float(open_row.get(t, np.nan))
            if not np.isfinite(c0):
                continue
            gross_in += abs(n) * c0
            if not np.isfinite(o1):
                missing_open += 1
                o1 = c0                       # the whole move is then booked intraday
            pnl_on += n * (o1 - c0)
            if div_row is not None and t in div_row.index and np.isfinite(div_row[t]):
                # clause 5: in a back-adjusted store the ex-date credit lands inside the
                # overnight leg, which is where a holder receives it. Carried separately so
                # the leg can also be read price-only.
                pnl_div += n * c0 * float(div_row[t])

        # --- decide, on exactly the information the deployed runner has
        lo = max(0, i - lag - params.history_bars)
        targets, diag = sig.target_weights(closes.iloc[lo:i - lag], equity_curve, params, state)
        state = diag.get("state", {})
        if diag_out is not None:
            # S-28: the sizing diagnostics of the day, for a study about the vol target.
            # Read-only and default-inert, so every S-25/S-26 row stays bit-identical.
            diag_out.append({"date": index[i],
                             "portfolio_vol": diag.get("portfolio_vol"),
                             "vol_scale": diag.get("vol_scale"),
                             "gross_weight": diag.get("gross_weight"),
                             "margin_used": diag.get("margin_used"),
                             "winners": list(diag.get("winners") or []),
                             "reason": diag.get("reason")})
        ref = {t: float(prev_close_row[t]) for t in tickers if pd.notna(prev_close_row[t])}

        fees = turnover = 0.0
        orders = 0

        def trade(deltas: dict, px_row) -> None:
            nonlocal cash, fees, turnover, orders
            for t, d in sorted(deltas.items(), key=lambda kv: kv[1]):     # sells before buys
                p = float(px_row.get(t, np.nan))
                if not np.isfinite(p) or p <= 0 or d == 0:
                    continue
                p_eff = p * (1 + np.sign(d) * slippage_bps / 1e4)
                fee = commission(d, p_eff)
                cash -= d * p_eff + fee
                positions[t] = positions.get(t, 0) + d
                fees += fee
                turnover += abs(d) * p_eff
                orders += 1

        def plan() -> dict:
            out = {}
            for t in tickers:
                p = ref.get(t, 0.0)
                held = int(positions.get(t, 0))
                target = 0 if p <= 0 else int(targets.get(t, 0.0) * scale * equity / p)
                if abs(target - held) * max(p, 0.01) >= band_x * equity:
                    if skip_p > 0.0 and rng.random() < skip_p:
                        continue                      # S-32's placebo, drawn per candidate
                    out[t] = target - held
            return out

        # --- what trades at the open, if anything
        if mode == "overnight":
            trade({t: -n for t, n in positions.items() if n}, open_row)   # flat for the day
        elif mode == "both" and flat_frac > 0.0:
            # S-30: shed `flat_frac` of the carried book for the session only. No no-trade
            # band: this is a risk action on an existing position, not a rebalance, and at
            # the book's concentration every leg clears the 0.01x band by an order of
            # magnitude anyway.
            trade({t: -int(round(flat_frac * n)) for t, n in positions.items()
                   if n and int(round(flat_frac * n))}, open_row)
        elif mode in ("intraday", "preopen"):
            trade(plan(), open_row)                    # on for the session / the pre-open MOO
        elif mode != "both":
            raise ValueError(mode)

        # --- the intraday leg, on exactly what is held DURING the session
        pnl_id = 0.0
        for t, n in positions.items():
            if not n:
                continue
            o1 = float(open_row.get(t, np.nan))
            c1 = float(close_row.get(t, np.nan))
            if np.isfinite(o1) and np.isfinite(c1):
                pnl_id += n * (c1 - o1)

        # --- S-26's index hedge over one leg, sized on the trailing causal beta
        pnl_hg = hg_fee = hg_notional = 0.0
        hg_beta = float("nan")
        if hedge is not None:
            hg_beta = (_ols_beta(hist_book[-hg_window:], hist_bench[-hg_window:])
                       if len(hist_book) >= hg_window else float("nan"))
            leg_ret = bench_id[i] if hg_leg == "intraday" else bench_on[i]
            if np.isfinite(hg_beta) and np.isfinite(leg_ret):
                hg_notional = hg_ratio * hg_beta * prev_mark
                pnl_hg = -hg_notional * leg_ret
                hg_fee = abs(hg_notional) * hg_cost / 1e4
                cash += pnl_hg - hg_fee
            hist_book.append((pnl_on if hg_leg == "overnight" else pnl_id) / prev_mark)
            hist_bench.append(leg_ret)

        # --- and what trades at the close
        if mode in ("both", "overnight"):
            trade(plan(), close_row)          # the deployed rebalance / back on for the night
        elif mode == "intraday":
            trade({t: -n for t, n in positions.items() if n}, close_row)  # flat overnight

        value = cash + sum(n * float(close_row[t]) for t, n in positions.items()
                           if t in close_row.index and pd.notna(close_row[t]) and n)
        rows.append({"date": index[i], "equity": value, "prev": prev_mark,
                     "orders": orders, "fees": fees, "turnover": turnover,
                     "interest": interest, "cash": cash, "gross_in": gross_in,
                     "pnl_on": pnl_on, "pnl_id": pnl_id, "pnl_div": pnl_div,
                     "pnl_hedge": pnl_hg, "hedge_fee": hg_fee,
                     "hedge_notional": hg_notional, "hedge_beta": hg_beta})
        equity = value
        equity_curve.append(value)

    out = pd.DataFrame(rows)
    out["ret"] = out["equity"] / out["prev"] - 1.0
    out["ret_on"] = out["pnl_on"] / out["prev"]
    out["ret_div"] = out["pnl_div"] / out["prev"]
    out["ret_id"] = out["pnl_id"] / out["prev"]
    out["ret_hedge"] = out["pnl_hedge"] / out["prev"]
    out["gross_x"] = out["gross_in"] / out["prev"]
    out["hedge_x"] = out["hedge_notional"] / out["prev"]
    out.attrs["missing_open"] = missing_open
    return out


def identity_check(book: pd.DataFrame, slippage_bps: float) -> dict:
    """Clause 1: legs + costs must equal the day's P&L to the cent."""
    pnl = book["equity"] - book["prev"]
    resid = pnl - (book["pnl_on"] + book["pnl_id"] + book["interest"] - book["fees"]
                   + book.get("pnl_hedge", 0.0) - book.get("hedge_fee", 0.0))
    # `resid` is exactly the slippage paid, which is not separately booked above.
    rel = (resid.abs() / book["prev"]).max()
    return {"max_abs_resid_$": float(resid.abs().max()),
            "max_resid_frac_of_equity": float(rel),
            "mean_resid_bps": float(1e4 * (resid / book["prev"]).mean()),
            "slippage_bps": slippage_bps}


# ---------------------------------------------------------------------------- the controls

def control_legs(frames: dict, tickers: list[str], dates: pd.Index) -> pd.DataFrame:
    """Always-invested, unlevered leg returns: equal-weight sleeve and SPY alone."""
    closes, opens = frames["close"], frames["open"]
    ew_on, ew_id, spy_on, spy_id = [], [], [], []
    for d in dates:
        i = closes.index.get_loc(d)
        c0, o1, c1 = closes.iloc[i - 1], opens.iloc[i], closes.iloc[i]
        on, idy = [], []
        for t in tickers:
            a, b, c = float(c0.get(t, np.nan)), float(o1.get(t, np.nan)), float(c1.get(t, np.nan))
            if np.isfinite(a) and np.isfinite(b) and np.isfinite(c) and a > 0 and b > 0:
                on.append(b / a - 1.0)
                idy.append(c / b - 1.0)
        ew_on.append(np.mean(on) if on else np.nan)
        ew_id.append(np.mean(idy) if idy else np.nan)
        a, b, c = float(c0["SPY"]), float(o1["SPY"]), float(c1["SPY"])
        spy_on.append(b / a - 1.0)
        spy_id.append(c / b - 1.0)
    return pd.DataFrame({"date": dates, "ew_on": ew_on, "ew_id": ew_id,
                         "spy_on": spy_on, "spy_id": spy_id})


def leg_table(book: pd.DataFrame, ctrl: pd.DataFrame, label: str) -> list[dict]:
    """Clause 2: the book's legs, the gross-scaled control's, and the difference."""
    m = book.merge(ctrl, on="date")
    g = m["gross_x"].to_numpy()
    out = []
    for leg, bcol in [("overnight", "ret_on"), ("intraday", "ret_id")]:
        b = 1e4 * m[bcol].to_numpy()
        for cname, ccol in [("EW sleeve", "ew_"), ("SPY", "spy_")]:
            c = 1e4 * m[ccol + ("on" if leg == "overnight" else "id")].to_numpy() * g
            d = b - c
            out.append({"window": label, "leg": leg, "control": cname, "days": len(b),
                        "book_bps": b.mean(), "book_t": tstat(b),
                        "ctrl_bps": np.nanmean(c), "diff_bps": np.nanmean(d),
                        "diff_t": tstat(d), "gross_x": g.mean()})
    return out


def print_legs(rows: list[dict]) -> None:
    hdr = (f"{'window':<16}{'leg':<11}{'control':<11}{'days':>6}{'book bps':>10}{'t':>7}"
           f"{'ctrl bps':>10}{'diff bps':>10}{'t':>7}{'gross':>7}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['window']:<16}{r['leg']:<11}{r['control']:<11}{r['days']:>6}"
              f"{r['book_bps']:>+10.3f}{r['book_t']:>+7.2f}{r['ctrl_bps']:>+10.3f}"
              f"{r['diff_bps']:>+10.3f}{r['diff_t']:>+7.2f}{r['gross_x']:>7.2f}")


# ------------------------------------------------------------------------------- reporting

def record(rows: list[dict], note: str, no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s25_legs", "class": "book",
                "tag": f"S-25 {r['cell'].strip()} ({note})", "commit": "", "run_dir": "",
                "track": "S-25", "start": r.get("start", START), "end": r.get("end", END),
                "stats": {"Sessions": str(r["sessions"]),
                          "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.3f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees']:.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--spread-bps", type=float, default=2.0,
                    help="one-way spread charged in the costed screen (clause 3)")
    ap.add_argument("--dividends", action="store_true",
                    help="clause 5: split the overnight leg into price and ex-date credit")
    ap.add_argument("--preopen", action="store_true",
                    help="post hoc: split the pre-open MOO move (BLOCKERS.md) by leg")
    ap.add_argument("--cross", action="store_true",
                    help="clause 4: re-run the split on the official opening crosses")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    params = sig.Params()
    tickers = sig.traded_universe(params)
    frames = load_ohlcv(tickers)
    fin = {"rates": rates.load(), "spread": 0.0}
    print(f"store: {len(tickers)} tickers, {frames['close'].index[0].date()} .. "
          f"{frames['close'].index[-1].date()}")
    print(f"window {args.start} .. {args.end}   band {MIN_ORDER_VALUE:g} x equity\n")

    # ------------------------------------------------------------------ clause 1: identity
    print("=== clause 1: does the attribution reproduce the deployed book? ===")
    dep = legs_simulate(frames, params, "both", args.start, args.end, 0.0, None)
    ref = simulate(frames, params, 0, "close", args.start, args.end, 0.0, None)
    a, b = summarize(dep, "legs both"), summarize(ref, "sweep_s19 deployed")
    print(f"  legs book        CAR {a['CAR']:.6f}%  Sharpe {a['Sharpe']:.6f}  "
          f"orders {a['orders']:,}  end ${a['end_equity']:,.2f}")
    print(f"  sweep_s19 book   CAR {b['CAR']:.6f}%  Sharpe {b['Sharpe']:.6f}  "
          f"orders {b['orders']:,}  end ${b['end_equity']:,.2f}")
    idc = identity_check(dep, 0.0)
    print(f"  leg identity     max |residual| ${idc['max_abs_resid_$']:.6f}  "
          f"({idc['max_resid_frac_of_equity']:.2e} of equity)  "
          f"sessions with no open {dep.attrs['missing_open']}")
    same = abs(a["CAR"] - b["CAR"]) < 1e-9 and a["orders"] == b["orders"]
    print(f"  VERDICT: {'PASS' if same else 'FAIL'} - the attributed book is the deployed book"
          f"{'' if same else ' (READ NOTHING BELOW)'}\n")

    # ------------------------------------------------------------------ clause 2: the split
    ctrl = control_legs(frames, [t for t in tickers if t in frames["close"].columns], dep["date"])
    print("=== clause 2: the split, against an always-invested control at the book's gross ===")
    print("book bps = the deployed book's own return in that leg; ctrl = the same-gross\n"
          "always-invested control; diff = what the ranking adds. Paired by session.\n")
    rows = leg_table(dep, ctrl, "full 2012-2026")
    for name, lo, hi in HALVES:
        sub = dep[(dep["date"] >= pd.Timestamp(lo)) & (dep["date"] <= pd.Timestamp(hi))]
        rows += leg_table(sub, ctrl, name)
    print_legs(rows)
    tot = 1e4 * dep["ret"].mean()
    on, idy = 1e4 * dep["ret_on"].mean(), 1e4 * dep["ret_id"].mean()
    print(f"\n  the book earns {tot:+.3f} bps/day in total: {on:+.3f} overnight "
          f"({100 * on / tot:.0f}%) and {idy:+.3f} intraday ({100 * idy / tot:.0f}%), "
          f"before the day's costs.")
    print(f"  leg volatility (annualized): overnight {dep['ret_on'].std(ddof=1) * np.sqrt(252):.3f}"
          f"  intraday {dep['ret_id'].std(ddof=1) * np.sqrt(252):.3f}"
          f"  total {dep['ret'].std(ddof=1) * np.sqrt(252):.3f}"
          f"  corr {dep['ret_on'].corr(dep['ret_id']):+.3f}")

    # ------------------------------------------------------------------ clause 3: the screen
    print(f"\n=== clause 3: the two conditional books, charged for what they do ===")
    screen, books = [], {}
    for spread in (0.0, args.spread_bps):
        for mode in MODES:
            key = f"{mode} @ {spread:g}bp"
            bk = legs_simulate(frames, params, mode, args.start, args.end, spread, fin)
            books[key] = bk
            s = summarize(bk, key)
            s["turnover_x"] = float(bk["turnover"].sum() / START_EQUITY / (len(bk) / 252))
            screen.append(s)
    hdr = (f"{'cell':<22}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
           f"{'orders':>8}{'fees':>10}{'turn x/yr':>11}")
    print(hdr)
    print("-" * len(hdr))
    for s in screen:
        print(f"{s['cell']:<22}{s['sessions']:>6}{s['CAR']:>9.3f}{s['Sharpe']:>8.3f}"
              f"{s['MaxDD']:>8.3f}{s['std']:>7.3f}{s['orders']:>8,}{s['fees']:>10,.0f}"
              f"{s['turnover_x']:>11.1f}")
    print("\n  (all six rows carry IBKR Pro financing on the settled balance, S-21's hook)")

    base = f"both @ {args.spread_bps:g}bp"
    print(f"\npaired daily difference against '{base}' (bps/day):")
    for mode in MODES[1:]:
        key = f"{mode} @ {args.spread_bps:g}bp"
        p = paired(books[key], books[base], key, base)
        print(f"  {p['pair']:<44}{p['bps_per_day']:>+8.3f}  t {p['t']:>+6.2f}  ({p['days']} days)")

    print("\nhalves (CAR%, at the costed spread) - clause 3 needs BOTH:")
    half_rows = []
    for name, lo, hi in HALVES:
        line = f"  {name:<16}"
        for mode in MODES:
            bk = legs_simulate(frames, params, mode, lo, hi, args.spread_bps, fin)
            s = summarize(bk, f"{mode} {name}")
            half_rows.append(s)
            line += f"{mode[:9]:>10} {s['CAR']:>7.3f} (DD {s['MaxDD']:>5.1f})"
        print(line)

    # the breakeven: what one-way cost would make each variant match the deployed book?
    print("\nbreakeven one-way cost (the durable number if the screen refuses):")
    dep0 = books["both @ 0bp"]
    for mode in MODES[1:]:
        v0 = books[f"{mode} @ 0bp"]
        gap_car = summarize(dep0, "d")["CAR"] - summarize(v0, "v")["CAR"]
        extra_turn = (v0["turnover"].sum() - dep0["turnover"].sum()) / START_EQUITY
        d = paired(v0, dep0, mode, "both")
        # bps of one-way cost the variant can pay, given it pays it on `extra_turn` more
        # notional per unit of equity, before it falls behind the deployed book at 0 bp.
        years = len(v0) / 252.0
        edge_per_year = d["bps_per_day"] * 252 / 1e4
        room = edge_per_year * years / extra_turn * 1e4 if extra_turn else float("nan")
        print(f"  {mode:<10} gross edge over deployed {d['bps_per_day']:+7.3f} bps/day "
              f"(t {d['t']:+5.2f}), extra turnover {extra_turn / years:6.1f}x equity/yr "
              f"-> breakeven {room:+8.3f} bps one-way   [CAR gap at 0 bp {-gap_car:+.3f}]")

    # ------------------------------------------------------------------ clause 5: dividends
    if args.dividends:
        from lean_prices import _price_factors                          # noqa: PLC0415
        print("\n=== clause 5: how much of the overnight leg is the ex-date credit? ===")
        idx = frames["close"].index
        divs = pd.DataFrame({t: _price_factors(t, idx).pct_change().fillna(0.0)
                             for t in tickers}, index=idx)
        yields = 1e4 * divs.mean() * 252
        print("  annualized yield carried in the store's adjustment, bps/yr:")
        print("   " + "  ".join(f"{t} {yields[t]:6.0f}" for t in tickers))
        dep_d = legs_simulate(frames, params, "both", args.start, args.end, 0.0, None,
                              divs=divs)
        m = dep_d.merge(ctrl, on="date")
        g = m["gross_x"].to_numpy()
        ew_div = 1e4 * divs.reindex(m["date"])[tickers].mean(axis=1).to_numpy() * g
        b_on = 1e4 * m["ret_on"].to_numpy()
        b_div = 1e4 * m["ret_div"].to_numpy()
        c_on = 1e4 * m["ew_on"].to_numpy() * g
        d_all, d_px = b_on - c_on, (b_on - b_div) - (c_on - ew_div)
        print(f"\n  book overnight {b_on.mean():+.3f} bps/day, of which the ex-date credit is "
              f"{b_div.mean():+.3f}; the same-gross EW control {c_on.mean():+.3f}, of which "
              f"{ew_div.mean():+.3f}.")
        print(f"  selection difference   with dividends {d_all.mean():+.3f} bps/day "
              f"(t {tstat(d_all):+.2f})   price-only {d_px.mean():+.3f} (t {tstat(d_px):+.2f})")
        print("  A ranking that tilts toward high-yield names books more of its total return\n"
              "  in the overnight leg for no economic reason, so the price-only column is the\n"
              "  one that says whether the overnight excess is an overnight EFFECT.")

    # ------------------------------------- post hoc: which leg pays for the pre-open move?
    if args.preopen:
        print("\n=== POST HOC (labelled as such): the pre-open MOO move, split by leg ===")
        print("Not a new claim and not pre-registered above: BLOCKERS.md already recommends this\n"
              "move on S-23's +1.85 and S-24's +1.98 CAR points. What the split adds is the\n"
              "MECHANISM - if the alpha is overnight, the move must be buying one extra overnight\n"
              "of the FRESH ranking, and the intraday leg should be flat between the two.\n")
        pre = legs_simulate(frames, params, "preopen", args.start, args.end, 0.0, None)
        chk = simulate(frames, params, 0, "open", args.start, args.end, 0.0, None)
        sp, sc = summarize(pre, "preopen"), summarize(chk, "s19 backtest")
        print(f"  identity: legs book CAR {sp['CAR']:.6f}%  vs sweep_s19 fill=open "
              f"{sc['CAR']:.6f}%  -> {'PASS' if abs(sp['CAR'] - sc['CAR']) < 1e-9 else 'FAIL'}")
        m = pre[["date", "ret_on", "ret_id", "ret"]].merge(
            dep[["date", "ret_on", "ret_id", "ret"]], on="date", suffixes=("_pre", "_dep"))
        for leg in ("ret_on", "ret_id", "ret"):
            d = 1e4 * (m[f"{leg}_pre"] - m[f"{leg}_dep"]).to_numpy()
            name = {"ret_on": "overnight leg", "ret_id": "intraday leg",
                    "ret": "the whole day"}[leg]
            print(f"  {name:<16} pre-open {1e4 * m[f'{leg}_pre'].mean():+7.3f}   deployed "
                  f"{1e4 * m[f'{leg}_dep'].mean():+7.3f}   difference {d.mean():+7.3f} bps/day "
                  f"at t {tstat(d):+5.2f}")

        # The other route BLOCKERS.md lists, which needs the real-time data subscription:
        # decide on the close of D and fill at that same close. It is an UPPER BOUND by
        # construction (no runner can act on a price at the instant it prints), and it is
        # the only convention of the three whose freshness lands in the overnight leg.
        fresh = legs_simulate(frames, params, "both", args.start, args.end, 0.0, None, lag=-1)
        sf = summarize(fresh, "fresh close")
        print(f"\n  the third convention, an upper bound: decide on close[D], fill at close[D]"
              f"\n  (needs the real-time data subscription in BLOCKERS.md; no runner can act on"
              f"\n  a price at the instant it prints, so read it as a ceiling, not a plan)")
        print(f"  CAR {sf['CAR']:.3f}%  Sharpe {sf['Sharpe']:.3f}  DD {sf['MaxDD']:.3f}%  "
              f"against deployed {summarize(dep, 'd')['CAR']:.3f}% and pre-open {sp['CAR']:.3f}%")
        mf = fresh[["date", "ret_on", "ret_id", "ret"]].merge(
            dep[["date", "ret_on", "ret_id", "ret"]], on="date", suffixes=("_f", "_dep"))
        for leg in ("ret_on", "ret_id", "ret"):
            d = 1e4 * (mf[f"{leg}_f"] - mf[f"{leg}_dep"]).to_numpy()
            name = {"ret_on": "overnight leg", "ret_id": "intraday leg",
                    "ret": "the whole day"}[leg]
            print(f"  {name:<16} fresh-close {1e4 * mf[f'{leg}_f'].mean():+7.3f}   deployed "
                  f"{1e4 * mf[f'{leg}_dep'].mean():+7.3f}   difference {d.mean():+7.3f} bps/day "
                  f"at t {tstat(d):+5.2f}")

    # ------------------------------------------------------------------- clause 4: the cross
    if args.cross:
        from sweep_s24 import SLEEVE, cross_frames, load_auctions      # noqa: PLC0415
        print("\n=== clause 4: the same split on the OFFICIAL opening crosses (S-24) ===")
        auctions = load_auctions(SLEEVE)
        xframes, bias = cross_frames(frames, auctions)
        w = bias["sessions"]
        print(f"  {len(auctions)} names, sleeve-weighted store-open bias "
              f"{float((bias['mean_bps'] * w).sum() / w.sum()):+.3f} bps\n")
        xrows = []
        for label, fr in [("store open", frames), ("official cross", xframes)]:
            bk = legs_simulate(fr, params, "both", CROSS_START, args.end, 0.0, None)
            c = control_legs(fr, [t for t in tickers if t in fr["close"].columns], bk["date"])
            xrows += [dict(r, window=f"{label} 2016-26") for r in leg_table(bk, c, label)]
        print_legs(xrows)
        so = [r for r in xrows if r["window"].startswith("store") and r["leg"] == "overnight"][0]
        xo = [r for r in xrows if r["window"].startswith("official") and r["leg"] == "overnight"][0]
        agree = (np.sign(so["book_bps"]) == np.sign(xo["book_bps"])
                 and abs(so["book_bps"] - xo["book_bps"]) <= 1.0)
        print(f"\n  overnight leg: store {so['book_bps']:+.3f} vs cross {xo['book_bps']:+.3f} "
              f"bps/day -> clause 4 {'PASS' if agree else 'FAIL'}")

    for s in screen:
        s["start"], s["end"] = args.start, args.end
    record(screen, f"pandas book, {args.start}..{args.end}, IBKR Pro financing, "
                   f"{args.spread_bps:g} bp screen - DIAGNOSTIC, not promotable",
           args.no_record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
