#!/usr/bin/env python
"""S-39 / C-5c: price the frame the paper runner's data gate used to admit.

THE DEFECT, restated from the code rather than from the finding. `scripts/paper_trade.py`
chooses its history on one line of `main()`:

    closes = fetch_history_yf(...) if (args.history == "yfinance" or ib is None) else fetch_history_ib(ib, ...)

and the two sources had opposite conventions. `fetch_history_yf` dropped today's unfinished
bar (`closes.index < today`); `fetch_history_ib` applied no date filter at all, so
`reqHistoricalData(endDateTime="")` at the deployed 15:45 ET task time returned a bar for the
session IN PROGRESS. That row became `as_of`, the signal ranked on it, `plan_orders` sized
shares at it - and `data_faults` passed it, because its staleness clause tested `day < prev`
only. S-37 left that side out deliberately ("a different defect", belonging to the source)
and then did not fix the source, so the hole was held shut by nothing but the deployed task
passing no arguments. Both ends are closed in the same commit as this script.

WHAT THIS SCRIPT IS FOR. Closing the hole is not in question. What is in question is what
kind of hole it was, and the answer is not obvious: a 15:45 print of session D is FRESHER
information than the close of D-1, so the frame the gate admitted may well have made the
book MORE money, which would make this a latent unauthorized CLOCK CHANGE (BLOCKERS.md's
pre-open question, acquired by accident) rather than a latent data corruption. Those two
readings call for the same fix and completely different journal entries, and the loop does
not get to guess which.

THE MEASUREMENT. Both books fill at the same real 15:45 print of session i, so they are
paired to the instant and differ in ONE thing - whether the signal saw today's partial bar:

    cell        signal window ends          sizes shares at     fills at
    ----        ------------------          ---------------     --------
    deployed    close[i-1]                  close[i-1]          px[i, 15:45]
    partial     px[i, 15:44]  (the hole)    px[i, 15:44]        px[i, 15:45]
    bound       close[i]      (impossible)  close[i]            px[i, 15:45]

`bound` is not a candidate and could never be run: it lets the signal read a price 15 minutes
after it decides. It is carried because it is the cell S-19 actually measured (its "backtest
convention" fills at close[i]) and it brackets `partial` from above, so if `partial` lands
between `deployed` and `bound` the intraday price series is behaving.

PRICES. The decision price is the close of the 15:44 ET bar and the fill is the close of the
15:45 ET bar - a minute apart, so nothing reads a price it could not have had. Both come from
the Alpaca SIP minute store and are carried onto the daily store's adjusted scale as a
WITHIN-DAY RATIO, px_adj[i] = close_adj[i] * (px_raw[i] / close_raw[i]), which cancels every
difference between a split-adjusted minute store and a split-and-dividend-adjusted daily one
(S-24's implied-factor construction). The minute store starts 2016, so every cell below is
2016-2026 and the identity that ties it to the rest of the sleeve is run on 2012-2026.

CLAUSES, pre-registered before the first simulation:

  1. IDENTITY. With the fill forced back to close[i] and no partial bar, this file reproduces
     the cell nine previous iterations agree on: 22.192150170492255% / 5,052 orders,
     2012-2026 at zero cost. If it does not, nothing below is read.
  2. THE PRICE STORE. Coverage of the 15:44/15:45 pair over the nine names, and how far the
     15:44 print sits from that session's close - the quantity the whole question is about.
  3. THE THREE CELLS, 2016-2026, at 0 bp and at 2 bp + IBKR Pro financing, with the paired
     daily difference and its t-stat, plus both halves.
  4. ORDER-LEVEL DIVERGENCE. The fraction of sessions on which the two books send a different
     order list at all: a clock change that never changes a decision is not a clock change.
  5. VERDICT. `partial` beating `deployed` at |t| >= 2 reads as an unauthorized clock change
     and goes to BLOCKERS.md beside the pre-open move; anything less reads as what the gate
     always called it. Either way the gate is symmetric and `fetch_history_ib` filters.

    python scripts/sweep_s39.py                  # all clauses
    python scripts/sweep_s39.py --stage a        # identity + price store only

Nothing here is promotable, no shipped parameter is touched, and `champion.json` is not read
for anything but the universe. Requires an interpreter with pyarrow (py -3.14 on this box).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                       # noqa: E402
import rates                                # noqa: E402
from lean_prices import load_ohlcv          # noqa: E402
from sweep_s19 import commission, tstat, START_EQUITY, MIN_ORDER_VALUE  # noqa: E402

S19_CAR = 22.192150170492255
S19_ORDERS = 5_052
FULL_START, FULL_END = "2012-01-03", "2026-09-04"
MIN_START = "2016-01-05"                    # the Alpaca store's first full session
MINUTE_DIR = REPO / "data" / "minute_alpaca"
DECIDE_ET, FILL_ET = "15:44", "15:45"


# ------------------------------------------------------------------ clause 2: the price store
def intraday_ratios(tickers) -> pd.DataFrame:
    """{date -> {ticker -> (decide/close, fill/close)}} as two frames of within-day ratios.

    Read off the minute store in ET. The ratio is taken against the LAST regular-hours bar of
    the same session, so it is invariant to whatever adjustment either store carries, and the
    two prices are one minute apart in the same direction the runner experiences them.
    """
    dec, fil = {}, {}
    for t in tickers:
        p = MINUTE_DIR / f"{t}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        et = idx.tz_convert("America/New_York")
        day = pd.Index(et.date)
        hhmm = pd.Index([f"{h:02d}:{m:02d}" for h, m in zip(et.hour, et.minute)])
        c = df["c"].to_numpy()
        frame = pd.DataFrame({"day": day, "hhmm": hhmm, "c": c})
        # the session's own last RTH print, and the two prints the runner would have had
        last = frame.groupby("day")["c"].last()
        d = frame[frame["hhmm"] <= DECIDE_ET].groupby("day")["c"].last()
        f = frame[frame["hhmm"] <= FILL_ET].groupby("day")["c"].last()
        dec[t] = (d / last).dropna()
        fil[t] = (f / last).dropna()
    D = pd.DataFrame(dec)
    F = pd.DataFrame(fil)
    D.index = pd.to_datetime(D.index)
    F.index = pd.to_datetime(F.index)
    return D.sort_index(), F.sort_index()


# ------------------------------------------------------------------------ clauses 1, 3, 4
def simulate(frames, params, mode, start, end, dec_ratio=None, fill_ratio=None,
             slippage_bps=0.0, financing=None, trace=None) -> pd.DataFrame:
    """`sweep_s19.simulate` with the decision row and the fill price under explicit control.

    `mode` is one of the three rows in the docstring table. `dec_ratio`/`fill_ratio` are the
    within-day ratio frames from `intraday_ratios`; passing neither forces the fill back to
    close[i], which is the identity cell. Everything else - sizing rule, band, commission,
    sell-before-buy ordering, financing accrual - is `sweep_s19.simulate` verbatim, because
    the point of this file is that ONE input moves.
    """
    closes, opens = frames["close"], frames["open"]
    tickers = [t for t in sig.traded_universe(params) if t in closes.columns]
    index = closes.index
    i0 = max(index.searchsorted(pd.Timestamp(start)) + 1, params.history_bars)
    i1 = min(index.searchsorted(pd.Timestamp(end), side="right"), len(index))

    equity = cash = START_EQUITY
    positions: dict[str, int] = {}
    equity_curve = [START_EQUITY]
    state: dict = {}
    rows = []

    fin_rates = (financing or {}).get("rates") or {}
    fin_shift = float((financing or {}).get("spread", 0.0))
    fin_first, fin_final = (min(fin_rates), max(fin_rates)) if fin_rates else ("", "")

    for i in range(i0, i1):
        interest, prev_mark = 0.0, equity
        if fin_rates and i > i0:
            days = (index[i].date() - index[i - 1].date()).days
            stamp = min(max(index[i].date().isoformat(), fin_first), fin_final)
            interest = rates.accrual(cash, fin_rates[stamp], days, fin_shift)
            cash += interest
            equity += interest
            equity_curve[-1] += interest

        # --- the frame the runner holds at 15:45, and the prices it sizes from
        lo = max(0, i - params.history_bars)
        if mode == "deployed":
            window = closes.iloc[lo:i]
            ref_row = closes.iloc[i - 1]
        else:
            window = closes.iloc[lo + 1:i].copy()
            if mode == "bound":                       # close[i]: impossible, carried as a bound
                partial = closes.iloc[i]
            else:                                     # px[i, 15:44]: the frame the hole admitted
                r = dec_ratio.reindex([index[i]]).iloc[0] if dec_ratio is not None else None
                partial = closes.iloc[i] * r.reindex(closes.columns)
                if partial.reindex(tickers).isna().any():
                    partial = closes.iloc[i - 1]      # no minute bar: the runner's own last row
            window = pd.concat([window, partial.to_frame().T.set_index(pd.Index([index[i]]))])
            ref_row = partial

        targets, diag = sig.target_weights(window, equity_curve, params, state)
        state = diag.get("state", {})
        ref = {t: float(ref_row[t]) for t in tickers if pd.notna(ref_row.get(t, np.nan))}

        # --- the fill: the real 15:45 print, or close[i] when no minute store is supplied
        if fill_ratio is not None:
            fr = fill_ratio.reindex([index[i]]).iloc[0].reindex(closes.columns)
            px_fill_row = closes.iloc[i] * fr
            px_fill_row = px_fill_row.fillna(closes.iloc[i])
        else:
            px_fill_row = closes.iloc[i]

        deltas = {}
        for t in tickers:
            p = ref.get(t, 0.0)
            held = int(positions.get(t, 0))
            target = 0 if p <= 0 else int(targets.get(t, 0.0) * equity / p)
            if abs(target - held) * max(p, 0.01) >= MIN_ORDER_VALUE * equity:
                deltas[t] = target - held
        if trace is not None:
            trace[index[i]] = {t: int(d) for t, d in deltas.items()}

        fees = turnover = 0.0
        for t, d in sorted(deltas.items(), key=lambda kv: kv[1]):
            p = float(px_fill_row.get(t, np.nan))
            if not np.isfinite(p) or p <= 0:
                continue
            p_eff = p * (1 + np.sign(d) * slippage_bps / 1e4)
            fee = commission(d, p_eff)
            cash -= d * p_eff + fee
            positions[t] = positions.get(t, 0) + d
            fees += fee
            turnover += abs(d) * p_eff

        mark = closes.iloc[i]
        value = cash + sum(n * float(mark[t]) for t, n in positions.items()
                           if t in mark.index and pd.notna(mark[t]))
        rows.append({"date": index[i], "equity": value, "prev": prev_mark,
                     "orders": len(deltas), "fees": fees, "turnover": turnover})
        equity = value
        equity_curve.append(value)

    out = pd.DataFrame(rows).set_index("date")
    out["ret"] = out["equity"] / out["prev"] - 1.0
    return out


def summarize(book: pd.DataFrame) -> dict:
    n = len(book)
    years = n / 252.0
    car = (book["equity"].iloc[-1] / START_EQUITY) ** (1 / years) - 1.0
    vol = book["ret"].std() * np.sqrt(252)
    peak = book["equity"].cummax()
    return {"car": car * 100, "sharpe": (book["ret"].mean() * 252) / vol if vol else 0.0,
            "dd": float((1 - book["equity"] / peak).max() * 100), "vol": float(vol),
            "orders": int(book["orders"].sum()), "days": n}


def row(label, s):
    print(f"  {label:<34} {s['car']:8.3f}%  {s['sharpe']:6.3f}  {s['dd']:7.3f}%  "
          f"{s['orders']:>7,}  {s['days']:>5}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["a", "all"], default="all")
    args = ap.parse_args()

    params = sig.Params()
    frames = load_ohlcv(sig.traded_universe(params))
    tickers = [t for t in sig.traded_universe(params) if t in frames["close"].columns]

    # ------------------------------------------------------------------- CLAUSE 1  identity
    print("=" * 78)
    print("CLAUSE 1  identity against the cell nine iterations agree on")
    print("=" * 78)
    ident = simulate(frames, params, "deployed", FULL_START, FULL_END)
    s = summarize(ident)
    ok = abs(s["car"] - S19_CAR) < 1e-9 and s["orders"] == S19_ORDERS
    print(f"  CAR      {s['car']:.12f}%   expected {S19_CAR:.12f}%   "
          f"delta {abs(s['car'] - S19_CAR):.2e}")
    print(f"  orders   {s['orders']:,}            expected {S19_ORDERS:,}")
    print(f"  IDENTITY {'EXACT' if ok else 'FAILED'}")
    if not ok:
        print("  refusing to read anything below a broken identity")
        return 1

    # -------------------------------------------------------------- CLAUSE 2  the price store
    print("\n" + "=" * 78)
    print(f"CLAUSE 2  the {DECIDE_ET}/{FILL_ET} ET price store, as within-day ratios")
    print("=" * 78)
    D, F = intraday_ratios(tickers)
    have = [t for t in tickers if t in D.columns]
    print(f"  names with minute bars   {len(have)} of {len(tickers)}   {have}")
    idx = frames["close"].index
    win = idx[(idx >= pd.Timestamp(MIN_START)) & (idx <= pd.Timestamp(FULL_END))]
    cov = D.reindex(win)[have].notna().all(axis=1)
    print(f"  sessions {win[0].date()}..{win[-1].date()}   {len(win):,}   "
          f"all nine priced on {int(cov.sum()):,} ({cov.mean() * 100:.1f}%)")
    gap = (D.reindex(win)[have] - 1.0) * 1e4
    print(f"\n  how far the {DECIDE_ET} print sits from the same session's close, bps:")
    print(f"  {'name':<6} {'mean':>8} {'sd':>8} {'|p95|':>8}")
    for t in have:
        g = gap[t].dropna()
        print(f"  {t:<6} {g.mean():8.2f} {g.std():8.2f} {g.abs().quantile(0.95):8.2f}")
    slip = ((F.reindex(win)[have] / D.reindex(win)[have] - 1.0) * 1e4).stack().dropna()
    print(f"\n  {DECIDE_ET} -> {FILL_ET} drift (decide to fill): mean {slip.mean():+.3f} bps, "
          f"sd {slip.std():.3f}")

    # --- two controls, so the store is shown to inject a price and nothing else
    fin0 = {"rates": rates.load(), "spread": 0.0}
    print(f"\n  control (i): the FILL alone, same read (close[i-1]), 2 bp + financing")
    for lbl, fr in ((f"fill at close[i] (S-19's stand-in)", None),
                    (f"fill at the real {FILL_ET} print   ", F)):
        s = summarize(simulate(frames, params, "deployed", MIN_START, FULL_END, dec_ratio=D,
                               fill_ratio=fr, slippage_bps=2.0, financing=fin0))
        print(f"    {lbl}  CAR {s['car']:7.3f}%  Sharpe {s['sharpe']:6.3f}  "
              f"maxDD {s['dd']:6.2f}%  orders {s['orders']:,}")
    print("\n  control (ii): `partial` fed a flat ratio must BE `bound` - if the two differ,")
    print("                the ratio store is doing something besides carrying a price")
    flat = pd.DataFrame(1.0, index=D.index, columns=D.columns)
    a = simulate(frames, params, "partial", MIN_START, FULL_END, dec_ratio=flat, fill_ratio=F)
    b = simulate(frames, params, "bound", MIN_START, FULL_END, dec_ratio=D, fill_ratio=F)
    print(f"    max |equity difference|   {(a['equity'] - b['equity']).abs().max():.3e}")
    if args.stage == "a":
        return 0

    # --------------------------------------------------------------- CLAUSES 3 & 4  the cells
    fin = {"rates": rates.load(), "spread": 0.0}
    traces: dict[str, dict] = {}
    books: dict[tuple, pd.DataFrame] = {}
    for cost, cfg in (("0 bp", dict(slippage_bps=0.0, financing=None)),
                      ("2 bp + fin", dict(slippage_bps=2.0, financing=fin))):
        for mode in ("deployed", "partial", "bound"):
            tr = {} if cost == "0 bp" else None
            books[(cost, mode)] = simulate(frames, params, mode, MIN_START, FULL_END,
                                           dec_ratio=D, fill_ratio=F, trace=tr, **cfg)
            if tr is not None:
                traces[mode] = tr

    print("\n" + "=" * 78)
    print(f"CLAUSE 3  the three cells, {MIN_START}..{FULL_END}, filled at the real "
          f"{FILL_ET} print")
    print("=" * 78)
    for cost in ("0 bp", "2 bp + fin"):
        print(f"\n  {cost}")
        print(f"  {'cell':<34} {'CAR':>8}  {'Sharpe':>6}  {'maxDD':>7}  {'orders':>7}  "
              f"{'days':>5}")
        for mode in ("deployed", "partial", "bound"):
            row(mode, summarize(books[(cost, mode)]))
        base = books[(cost, "deployed")]["ret"]
        for mode in ("partial", "bound"):
            d = (books[(cost, mode)]["ret"] - base).dropna() * 1e4
            print(f"    paired {mode:<10} vs deployed  {d.mean():+7.3f} bps/day   "
                  f"t {tstat(d):+6.2f}")

    print("\n  halves, fully charged (2 bp + IBKR Pro financing)")
    for lo, hi, name in (("2016-01-05", "2019-12-31", "2016-2019"),
                         ("2020-01-01", "2026-09-04", "2020-2026")):
        print(f"    {name}")
        for mode in ("deployed", "partial", "bound"):
            b = books[("2 bp + fin", mode)]
            seg = b[(b.index >= lo) & (b.index <= hi)]
            sub = seg.copy()
            sub["prev"] = sub["equity"].shift(1).fillna(sub["prev"].iloc[0])
            s = summarize(sub)
            print(f"      {mode:<12} CAR {s['car']:7.3f}%  Sharpe {s['sharpe']:6.3f}  "
                  f"maxDD {s['dd']:6.2f}%")

    print("\n" + "=" * 78)
    print("CLAUSE 4  does the partial bar change the ORDER LIST, or only the price?")
    print("=" * 78)
    dep, par = traces["deployed"], traces["partial"]
    days = sorted(set(dep) & set(par))
    diff = [d for d in days if dep[d] != par[d]]
    names_dep = sum(len(dep[d]) for d in days)
    names_par = sum(len(par[d]) for d in days)
    same_set = [d for d in days if set(dep[d]) == set(par[d])]
    print(f"  sessions compared                     {len(days):,}")
    print(f"  order lists that differ at all        {len(diff):,} ({len(diff)/len(days)*100:.1f}%)")
    print(f"  same NAMES, different share counts    {len([d for d in diff if d in same_set]):,}")
    print(f"  different NAMES traded                {len(diff) - len([d for d in diff if d in same_set]):,}")
    print(f"  total orders  deployed {names_dep:,}   partial {names_par:,}")

    # ------------------------------------------------------------------------ CLAUSE 5 verdict
    d = (books[("2 bp + fin", "partial")]["ret"]
         - books[("2 bp + fin", "deployed")]["ret"]).dropna() * 1e4
    t = tstat(d)
    print("\n" + "=" * 78)
    print("CLAUSE 5  verdict on the pre-registered rule")
    print("=" * 78)
    print(f"  partial - deployed, fully charged: {d.mean():+.3f} bps/day at t {t:+.2f}")
    if abs(t) >= 2.0 and d.mean() > 0:
        print("  -> UNAUTHORIZED CLOCK CHANGE: the hole was worth money. File in BLOCKERS.md")
        print("     beside the pre-open move; the gate still closes, because acquiring a")
        print("     convention by accident is not the same as choosing one.")
    elif abs(t) >= 2.0:
        print("  -> the hole was a COST. The gate closes and there is nothing to file.")
    else:
        print("  -> NOT RESOLVED at |t| >= 2: the partial bar is not measurably better or")
        print("     worse than the close it replaced. The gate closes on the argument it")
        print("     always had - an untested convention the runner must not acquire by")
        print("     accident - and no owner-facing option is created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
