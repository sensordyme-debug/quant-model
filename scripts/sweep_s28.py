#!/usr/bin/env python
"""S-28: should the champion's risk model be measured on the leg it is paid in?

    python scripts/sweep_s28.py                 # every stage
    python scripts/sweep_s28.py --stage a       # identity + the forecast diagnostic
    python scripts/sweep_s28.py --stage bc      # the books + the post-hoc matched-risk column
    python scripts/sweep_s28.py --no-record     # do not append to the ledger

S-25 measured that **94% of this book's return and all of its measurable alpha is earned
overnight** (+8.103 bps/day at t +6.80 against +0.738 intraday at t +0.47), and that the two
legs carry 0.115 and 0.151 of annualized volatility against the book's 0.188 - so the leg that
pays carries the *smaller* share of the risk. S-26 asked what the book should HOLD given that
split (a futures overlay; refused on drawdown) and S-27 asked what it should RANK on (an
overnight momentum blend; refused - the whole trend forecasts the overnight leg better than its
own history does). Neither asked the third question, which is the one the sizing machinery
actually poses:

    the book is sized by `target_vol / sigma`, and `sigma` is a CLOSE-TO-CLOSE estimate of a
    quantity 61% of whose variance comes from the session leg the book is not paid for.

A risk model is a forecast of the risk you are about to take. If the overnight and intraday
legs have different volatility dynamics, then an estimate that pools them is the wrong
forecast for a book whose P&L is an overnight object, and the sizing that follows from it
de-risks at the wrong times. This iteration replaces the estimator - and only the estimator -
and prices the difference on the harness that reproduces the deployed book to the digit.

Where the change bites is not a mystery and is stated in advance, because it decides how the
result must be read. With `margin_budget = 0.75` flat, the shipped book is pinned at ~1.50x
gross by the margin budget whenever the vol target asks for more than the budget can fund
(S-8's "the vol target is inert upwards"), so `sigma` only moves the book when it is LARGE -
i.e. in a volatility crisis. **This is therefore a study about how the book de-risks in a
crisis, not about its average exposure.**

The mechanism is a new, default-inert hook in the shipped `signals.py` (`S1_VOL_RETURNS` /
`set_vol_returns`, F-3's `S1_ML_SCORES` pattern) that supplies the return window the vol
target is measured on. Nothing else in the file changes, the environment is unset in every
deployed path, and the I-1 gate (`scripts/compare_orders.py`) was re-run after the edit.

PRE-REGISTERED before the first number, six clauses
---------------------------------------------------
(1) IDENTITY. Installing the close-to-close frame through the hook must reproduce the
    deployed cell BIT FOR BIT - CAR 22.192150%, 5,052 orders - because that frame is by
    construction what `_size` already computes. If it does not, the hook is changing
    something other than the estimator and nothing below may be read. The three leg frames
    must also satisfy `(1+on)(1+id) = (1+cc)` to 1e-12.

(2) DIAGNOSTIC BEFORE BOOK, which is S-27's rule. The claim only makes sense if a trailing
    overnight-leg vol forecasts the NEXT overnight-leg vol better than the pooled
    close-to-close vol does. The table is pooled over the nine sleeve names: trailing 60
    sessions of each estimator against the realized vol of each leg over the next 21. If the
    close-to-close estimator forecasts the overnight leg at least as well, the primary is
    expected to fail and the reason will already be on the page.

(3) PRIMARY, the level-matched overnight estimator (`on_k`). Raw overnight vol is ~0.6x
    close-to-close vol, so handing it to `target_vol / sigma` unchanged is a LEVERAGE change,
    and S-16/O-1b already priced leverage on this book. The primary therefore rescales the
    overnight leg by a CAUSAL expanding-window constant so the estimator has the same average
    level as the shipped one and only its TIMING differs. Promotable only on `evaluate.py`'s
    criteria transplanted here: beat the deployed book on CAR, Sharpe no more than 0.03 below,
    drawdown no more than 1.0 point worse and never above 35% absolute - in the full period
    and in BOTH halves, at the same cost model (2 bp of spread + IBKR Pro financing).

(4) LEVEL COLUMN. The raw `on` estimator is reported beside it, so the level effect and the
    timing effect are separated rather than summed. It is judged on the same criteria and is
    expected to buy return with drawdown, because it removes crisis de-risking.

(5) PLACEBO. The same construction on the INTRADAY leg (`id_k`) - the leg the book is not
    paid in. If `on_k` passes and `id_k` passes equally, the result is about the estimator
    being different rather than about the leg that pays, and the primary is withdrawn.

(6) EXPECTATION, written down first so the run can be wrong rather than merely reported.
    Overnight and intraday volatility are driven by a common regime, so the two estimators
    are expected to be highly correlated in level (> 0.85) and the level-matched book is
    expected to be NEARLY THE DEPLOYED BOOK, differing only across crisis episodes. The
    honest outcome is most likely "no material difference", which is itself a finding: the
    risk model does not need the leg split even though the P&L does.

Nothing here changes a default. `champion.json`, `live/*` and the scheduled tasks are
untouched; every row this script writes is DIAGNOSTIC.
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

import signals as sig                                         # noqa: E402
import rates                                                  # noqa: E402
from lean_prices import load_ohlcv                            # noqa: E402
from sweep_s19 import START_EQUITY, paired, summarize          # noqa: E402
from sweep_s25 import legs_simulate, identity_check            # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
START = "2012-01-03"
END = "2026-09-04"
HALVES = [("IS 2012-2019", START, "2019-12-31"), ("OOS 2020-2026", "2020-01-02", END)]

S25_DEPLOYED_CAR = 22.192150170492255     # clause 1: S-25/S-26/S-27's own printed figure
S25_DEPLOYED_ORDERS = 5052
K_MIN_PERIODS = 252                       # burn-in for the causal level match
FWD = 21                                  # sessions of forward realized vol in the diagnostic
TRAIL = 60                                # the shipped `vol_est_window`

#: evaluate.py's criteria, transplanted to this harness (champion.json "criteria").
SHARPE_TOL = 0.03
DD_TOL = 1.0
DD_LIMIT = 35.0


# ------------------------------------------------------------------- clause 1: the frames

def leg_frames(frames: dict, tickers: list) -> dict[str, pd.DataFrame]:
    """The three per-session return definitions, on the same adjusted store.

    `cc` is what `_size` computes today. `on` is the close-to-open leg and `id` the
    open-to-close leg, the same split S-25 attributed the book's P&L with. Every leg carries
    the store's dividend adjustment, so the ex-date credit sits in `on` exactly as it does in
    the attribution - immaterial for a second moment, and stated rather than assumed.
    """
    closes, opens = frames["close"][tickers], frames["open"][tickers]
    cc = closes.pct_change()
    on = opens / closes.shift(1) - 1.0
    idr = closes / opens - 1.0
    return {"cc": cc, "on": on, "id": idr}


def leg_identity(legs: dict) -> float:
    """max |(1+on)(1+id) - (1+cc)| over the whole store."""
    resid = (1 + legs["on"]) * (1 + legs["id"]) - (1 + legs["cc"])
    return float(np.nanmax(np.abs(resid.to_numpy())))


def level_factor(legs: dict, leg: str) -> pd.Series:
    """Causal expanding-window factor that puts `leg`'s vol on the close-to-close scale.

    Pooled across the sleeve (mean squared return per session, then an expanding mean), and
    shifted one session, so the factor on day D uses only returns through D-1. The store
    starts in 1998 and the book starts in 2012, so the factor is burned in long before the
    first funded session and no cell in this script ever runs on the fallback of 1.0.
    """
    m_cc = (legs["cc"] ** 2).mean(axis=1)
    m_leg = (legs[leg] ** 2).mean(axis=1)
    num = m_cc.expanding(min_periods=K_MIN_PERIODS).mean().shift(1)
    den = m_leg.expanding(min_periods=K_MIN_PERIODS).mean().shift(1)
    k = np.sqrt(num / den)
    return k.replace([np.inf, -np.inf], np.nan).fillna(1.0)


def estimator_frames(legs: dict) -> dict[str, pd.DataFrame | None]:
    """The five estimators this study prices. `None` is the shipped path, untouched."""
    k_on, k_id = level_factor(legs, "on"), level_factor(legs, "id")
    return {"shipped (cc, no hook)": None,
            "cc through the hook": legs["cc"],
            "on (raw)": legs["on"],
            "on_k (level-matched)": legs["on"].mul(k_on, axis=0),
            "id (raw)": legs["id"],
            "id_k (level-matched)": legs["id"].mul(k_id, axis=0)}


# --------------------------------------------------------------- clause 2: the diagnostic

def forecast_table(legs: dict, tickers: list) -> pd.DataFrame:
    """Does a trailing estimator forecast the next 21 sessions' realized vol of each leg?

    Pooled over the nine names in log vol (vol is lognormal-ish and the correlation of levels
    is dominated by a handful of crisis observations otherwise). Rows are the estimator the
    book could be sized on, columns the leg whose future risk is being forecast.
    """
    rows = []
    for est in ("cc", "on", "id"):
        trail = legs[est].rolling(TRAIL).std(ddof=1) * np.sqrt(252)
        row = {"estimator": est}
        for tgt in ("cc", "on", "id"):
            fwd = (legs[tgt].rolling(FWD).std(ddof=1) * np.sqrt(252)).shift(-FWD)
            x, y = [], []
            for t in tickers:
                m = pd.concat([trail[t], fwd[t]], axis=1).dropna()
                m = m[(m > 0).all(axis=1)]
                x.append(np.log(m.iloc[:, 0].to_numpy()))
                y.append(np.log(m.iloc[:, 1].to_numpy()))
            x, y = np.concatenate(x), np.concatenate(y)
            row[f"-> {tgt}"] = float(np.corrcoef(x, y)[0, 1])
            row["n"] = len(x)
        rows.append(row)
    return pd.DataFrame(rows).set_index("estimator")


def estimator_agreement(legs: dict, tickers: list) -> dict:
    """Clause 6's number: how alike are the two trailing estimators, in level and in change?"""
    a = (legs["cc"].rolling(TRAIL).std(ddof=1))[tickers]
    b = (legs["on"].rolling(TRAIL).std(ddof=1))[tickers]
    c = (legs["id"].rolling(TRAIL).std(ddof=1))[tickers]
    out = {}
    for name, other in (("on", b), ("id", c)):
        m = pd.concat([a.stack(), other.stack()], axis=1).dropna()
        m = m[(m > 0).all(axis=1)]
        lv = np.log(m.to_numpy())
        out[f"corr(log sigma_cc, log sigma_{name})"] = float(np.corrcoef(lv[:, 0], lv[:, 1])[0, 1])
        d = np.diff(lv, axis=0)
        out[f"corr(d log sigma_cc, d log sigma_{name})"] = float(np.corrcoef(d[:, 0], d[:, 1])[0, 1])
        out[f"mean sigma_{name} / sigma_cc"] = float((m.iloc[:, 1] / m.iloc[:, 0]).mean())
    return out


# -------------------------------------------------------------------------- clause 3-5

def run(frames: dict, params, estimator, *, spread: float, fin: dict | None,
        start: str = START, end: str = END, diag_out: list | None = None,
        scale: float = 1.0) -> pd.DataFrame:
    sig.set_vol_returns(estimator)
    try:
        return legs_simulate(frames, params, "both", start, end, spread, fin,
                             diag_out=diag_out, scale=scale)
    finally:
        sig.set_vol_returns(None)


def describe(book: pd.DataFrame, label: str) -> dict:
    s = summarize(book, label)
    s["gross_x"] = float(book["gross_x"].mean())
    s["gross_max"] = float(book["gross_x"].max())
    s["turnover_x"] = float(book["turnover"].sum() / START_EQUITY / (len(book) / 252))
    return s


def table(rows: list[dict]) -> None:
    hdr = (f"{'cell':<24}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
           f"{'gross':>7}{'maxgr':>7}{'orders':>8}{'turn x/yr':>11}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['cell']:<24}{r['sessions']:>6}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}"
              f"{r['MaxDD']:>8.3f}{r['std']:>7.3f}{r['gross_x']:>7.2f}{r['gross_max']:>7.2f}"
              f"{r['orders']:>8,}{r['turnover_x']:>11.1f}")


def vol_match(frames: dict, params, estimator, target_std: float, *, tol: float = 0.002,
              max_iter: int = 4, **kw) -> tuple[pd.DataFrame, float, list[str]]:
    """Scale the book on the real machinery until its realized vol matches `target_std`.

    S-26's helper, re-pointed at the estimator argument. `scale` multiplies the shipped
    targets, so gross, commission and the financed debit all follow - a relever priced on the
    same book rather than a return series multiplied after the fact.
    """
    trace = []
    bk = run(frames, params, estimator, scale=1.0, **kw)
    s0 = summarize(bk, "x")["std"]
    trace.append(f"scale 1.000 -> std {s0:.4f}")
    k = target_std / s0
    for _ in range(max_iter):
        bk = run(frames, params, estimator, scale=k, **kw)
        s = summarize(bk, "x")["std"]
        trace.append(f"scale {k:.3f} -> std {s:.4f}")
        if abs(s - target_std) <= tol * target_std:
            break
        k *= target_std / s
    return bk, k, trace


def drawdowns(book: pd.DataFrame, n: int = 3) -> list[dict]:
    """The `n` deepest peak-to-trough episodes, so a drawdown column can be read as events."""
    ret = book["ret"].to_numpy()
    dates = pd.to_datetime(book["date"]).to_numpy()
    curve = np.cumprod(1 + ret)
    peak = np.maximum.accumulate(curve)
    dd = 1 - curve / peak
    out, used = [], np.zeros(len(dd), dtype=bool)
    for _ in range(n):
        masked = np.where(used, -1.0, dd)
        i = int(masked.argmax())
        if masked[i] <= 0:
            break
        j = int(np.argmax(curve[:i + 1] == peak[i]))
        k = i
        while k + 1 < len(curve) and curve[k + 1] < peak[i]:
            k += 1
        used[j:k + 1] = True
        out.append({"depth": 100 * float(dd[i]),
                    "peak": str(pd.Timestamp(dates[j]).date()),
                    "trough": str(pd.Timestamp(dates[i]).date()),
                    "recovered": str(pd.Timestamp(dates[k]).date())})
    return out


def verdict(cand: dict, base: dict) -> tuple[bool, str]:
    """champion.json's criteria, full period only; the caller adds the halves."""
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


# ------------------------------------------------------------------------------- ledger

def record(rows: list[dict], note: str, no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s28_volest", "class": "book",
                "tag": f"S-28 {r['cell'].strip()} ({note})", "commit": "", "run_dir": "",
                "track": "S-28", "start": r.get("start", START), "end": r.get("end", END),
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
                    help="a = identity + diagnostic, b = the books, c = the post-hoc "
                         "matched-risk column")
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    params = sig.Params()
    tickers = sig.traded_universe(params)
    frames = load_ohlcv(tickers)
    legs = leg_frames(frames, tickers)
    ests = estimator_frames(legs)
    fin = {"rates": rates.load(), "spread": 0.0}

    print(f"store: {len(tickers)} tickers, {frames['close'].index[0].date()} .. "
          f"{frames['close'].index[-1].date()}   window {args.start} .. {args.end}")
    print(f"sleeve: {', '.join(tickers)}\n")

    # ---------------------------------------------------------------- stage a
    if "a" in args.stage:
        print("=" * 96)
        print("CLAUSE 1  identity")
        print("=" * 96)
        resid = leg_identity(legs)
        print(f"  leg identity  max |(1+on)(1+id) - (1+cc)|   {resid:.3e}"
              f"   {'PASS' if resid < 1e-12 else 'FAIL'}")

        base0 = run(frames, params, None, spread=0.0, fin=None,
                    start=args.start, end=args.end)
        hook0 = run(frames, params, ests["cc through the hook"], spread=0.0, fin=None,
                    start=args.start, end=args.end)
        b, h = describe(base0, "shipped"), describe(hook0, "cc hook")
        ok = (abs(b["CAR"] - S25_DEPLOYED_CAR) < 1e-9 and b["orders"] == S25_DEPLOYED_ORDERS
              and abs(h["CAR"] - b["CAR"]) < 1e-9 and h["orders"] == b["orders"])
        print(f"  shipped path              CAR {b['CAR']:.6f}%  orders {b['orders']:,}  "
              f"end ${b['end_equity']:,.2f}")
        print(f"  cc through the hook       CAR {h['CAR']:.6f}%  orders {h['orders']:,}  "
              f"end ${h['end_equity']:,.2f}")
        print(f"  S-25's printed figure     CAR {S25_DEPLOYED_CAR:.6f}%  orders "
              f"{S25_DEPLOYED_ORDERS:,}")
        print(f"  -> {'PASS' if ok else 'FAIL'}: the hook is the estimator and nothing else")
        if not ok:
            print("\n  clause 1 failed; stopping rather than reading a book that is not the "
                  "deployed one.")
            return 1

        print("\n" + "=" * 96)
        print("CLAUSE 2  does the leg forecast its own future risk better than the pooled "
              "estimate does?")
        print("=" * 96)
        ft = forecast_table(legs, tickers)
        print(f"  pooled over {len(tickers)} names, trailing {TRAIL} sessions against the next "
              f"{FWD}, correlation of log vols\n")
        print(f"  {'trailing':<12}{'-> cc':>10}{'-> on':>10}{'-> id':>10}{'obs':>10}")
        print("  " + "-" * 52)
        for est, row in ft.iterrows():
            print(f"  {est:<12}{row['-> cc']:>10.4f}{row['-> on']:>10.4f}"
                  f"{row['-> id']:>10.4f}{int(row['n']):>10,}")
        best_on = ft["-> on"].idxmax()
        print(f"\n  best forecast of the leg the book is PAID in: '{best_on}' "
              f"({ft.loc[best_on, '-> on']:.4f}); the shipped estimator scores "
              f"{ft.loc['cc', '-> on']:.4f}")

        print("\n  clause 6, how alike the estimators are:")
        for k, v in estimator_agreement(legs, tickers).items():
            print(f"    {k:<40}{v:>8.4f}")

    # ---------------------------------------------------------------- stage b
    if "b" in args.stage:
        print("\n" + "=" * 96)
        print(f"CLAUSE 3-5  the books, {args.spread_bps:g} bp one-way spread + IBKR Pro financing")
        print("=" * 96)
        cells = ["shipped (cc, no hook)", "on (raw)", "on_k (level-matched)",
                 "id (raw)", "id_k (level-matched)"]
        books, rows, diags = {}, [], {}
        for cell in cells:
            dg: list = []
            bk = run(frames, params, ests[cell], spread=args.spread_bps, fin=fin,
                     start=args.start, end=args.end, diag_out=dg)
            books[cell] = bk
            diags[cell] = pd.DataFrame(dg)
            r = describe(bk, cell)
            r["start"], r["end"] = args.start, args.end
            rows.append(r)
        table(rows)
        by = {r["cell"]: r for r in rows}
        base = by["shipped (cc, no hook)"]

        print("\n  where the estimator actually bites (the vol target against the margin "
              "budget):")
        print(f"    {'cell':<24}{'mean scale':>12}{'at cap':>9}{'scale<0.857':>13}"
              f"{'mean sigma':>12}")
        for cell in cells:
            d = diags[cell].dropna(subset=["vol_scale"])
            sc = d["vol_scale"].astype(float)
            print(f"    {cell:<24}{sc.mean():>12.3f}{(sc >= 1.999).mean():>9.1%}"
                  f"{(sc < 0.857).mean():>13.1%}"
                  f"{pd.to_numeric(d['portfolio_vol'], errors='coerce').mean():>12.4f}")
        print("    (a scale below 0.857 is the only region where the vol target, not the "
              "0.75 margin budget, sets the book's size)")

        print("\n  paired daily difference against the shipped book (bps/day):")
        for cell in cells[1:]:
            p = paired(books[cell], books["shipped (cc, no hook)"], cell, "shipped")
            print(f"    {p['pair']:<52}{p['bps_per_day']:>+8.3f}  t {p['t']:>+6.2f}  "
                  f"({p['days']} days)")

        print("\n  halves (CAR%, drawdown in brackets) - clause 3 needs BOTH:")
        half_rows = []
        for name, lo, hi in HALVES:
            line = f"    {name:<16}"
            for cell in cells:
                bk = run(frames, params, ests[cell], spread=args.spread_bps, fin=fin,
                         start=lo, end=hi)
                r = describe(bk, cell)
                r["cell"] = f"{cell} {name}"
                r["start"], r["end"] = lo, hi
                half_rows.append(r)
                line += f"{r['CAR']:>9.3f} [{r['MaxDD']:>5.2f}]"
            print(line)
        print(f"    {'':<16}" + "".join(f"{c[:14]:>16}" for c in cells))

        print("\n  verdict (champion.json criteria, transplanted; full period and both "
              "halves):")
        for cell in cells[1:]:
            ok_full, why = verdict(by[cell], base)
            halves_ok = []
            for name, _lo, _hi in HALVES:
                c = next(r for r in half_rows if r["cell"] == f"{cell} {name}")
                b = next(r for r in half_rows if r["cell"] ==
                         f"shipped (cc, no hook) {name}")
                halves_ok.append(verdict(c, b)[0])
            tag = "PROMOTABLE" if (ok_full and all(halves_ok)) else "REFUSED"
            print(f"    {cell:<24}{tag:<12}full: {why}")
            print(f"    {'':<24}{'':<12}halves: "
                  + ", ".join(f"{n}={'pass' if o else 'fail'}"
                              for (n, _l, _h), o in zip(HALVES, halves_ok)))

        # ------------------------------------------------------------ stage c, POST HOC
        # Labelled post hoc because it is not one of the six clauses: the primary is refused
        # on CAR while carrying LESS risk, so the only fair reading is at matched risk. It is
        # reported, not promoted, and S-26's rule applies in reverse - a de-relevered book
        # owes its own drawdown column, so a re-relevered one does too.
        extra_rows = []
        if "c" in args.stage:
            print("\n" + "=" * 96)
            print("POST HOC  the primary carries less risk than the book it is judged "
                  "against - price it at matched risk")
            print("=" * 96)
            print("  deepest drawdown episodes:")
            for cell in ("shipped (cc, no hook)", "on_k (level-matched)"):
                print(f"    {cell}")
                for e in drawdowns(books[cell]):
                    print(f"      {e['depth']:>6.2f}%   {e['peak']} -> {e['trough']} "
                          f"-> {e['recovered']}")
            tgt = base["std"]
            bk, k, trace = vol_match(frames, params, ests["on_k (level-matched)"], tgt,
                                     spread=args.spread_bps, fin=fin,
                                     start=args.start, end=args.end)
            r = describe(bk, "on_k vol-matched")
            r["start"], r["end"] = args.start, args.end
            extra_rows.append(r)
            print(f"\n  vol match to the shipped book's {tgt:.4f}: "
                  + " | ".join(trace) + f"   (scale {k:.3f})")
            table([base, r])
            ok, why = verdict(r, base)
            p = paired(bk, books["shipped (cc, no hook)"], "on_k vol-matched", "shipped")
            print(f"    paired {p['bps_per_day']:>+7.3f} bps/day  t {p['t']:>+6.2f}")
            print(f"    full period: {'passes' if ok else 'REFUSED'} - {why}")
            for name, lo, hi in HALVES:
                hb, hk, _ = vol_match(frames, params, ests["on_k (level-matched)"],
                                      next(x for x in half_rows
                                           if x["cell"] == f"shipped (cc, no hook) {name}")["std"],
                                      spread=args.spread_bps, fin=fin, start=lo, end=hi)
                hr = describe(hb, f"on_k vol-matched {name}")
                hr["cell"] = f"on_k vol-matched {name}"
                hr["start"], hr["end"] = lo, hi
                extra_rows.append(hr)
                hbase = next(x for x in half_rows
                             if x["cell"] == f"shipped (cc, no hook) {name}")
                hok, hwhy = verdict(hr, hbase)
                print(f"    {name:<16}CAR {hr['CAR']:>7.3f} [{hr['MaxDD']:>5.2f}] against "
                      f"{hbase['CAR']:>7.3f} [{hbase['MaxDD']:>5.2f}]  scale {hk:.3f}  "
                      f"{'passes' if hok else 'REFUSED'} - {hwhy}")

        record(rows + half_rows + extra_rows,
               f"pandas book, {args.start}..{args.end}, IBKR Pro financing, "
               f"{args.spread_bps:g} bp screen - DIAGNOSTIC, not promotable", args.no_record)
        if not args.no_record:
            print(f"\n  {len(rows) + len(half_rows) + len(extra_rows)} rows appended to "
                  f"{LEDGER.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
