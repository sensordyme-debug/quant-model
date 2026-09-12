#!/usr/bin/env python
"""S-27: the champion ranks on close-to-close returns but is only paid overnight.

    python scripts/sweep_s27.py --stage a      # the signal diagnostic (ICs and spreads)
    python scripts/sweep_s27.py --stage b      # the books, through the deployed harness
    python scripts/sweep_s27.py --stage b --no-record

S-25 measured where this sleeve's money is made: **+8.103 bps/day overnight (t +6.80) against
+0.738 intraday (t +0.47)**, and against an always-invested control at the book's own gross the
*selection* difference is **+3.087 bps/day at t +4.20 overnight and -0.314 at t -0.37 intraday**.
Fourteen years find no intraday content in this ranking at all. S-26 then priced the only route
that isolates the leg by trading - a futures overlay - and refused it on drawdown.

Both of those asked what to HOLD. Neither asked what to RANK ON. The shipped signal is a blend of
20/60/120/252-day **close-to-close** returns, i.e. it scores names on a quantity that is 94%
composed of a leg the book is not paid for plus 6% of the leg it is. If the overnight leg is a
distinct object rather than an accounting slice, a momentum blend built from **overnight returns
only** should rank better in the leg that pays - and it costs nothing to find out: same nine
names, same top-3, same vol target, same regime gate, same rebalance, same turnover, same
instruments. This is the one direction S-25 left open that does not need a new instrument, a new
cost model or the owner's consent.

The mechanism it would be evidence for is the published close-to-open literature: overnight
returns are where the equity premium concentrates, and a name's overnight behaviour is persistent
in a way its intraday behaviour is not. The mechanism it would refuse is that the leg split is an
accounting fact about when a long book is marked, with no cross-sectional content.

HOW IT IS BUILT, and why nothing in the strategy is edited
----------------------------------------------------------
Three synthetic price indices per ticker, all from the same adjusted store:
    cc[d] = cc[d-1] * close[d]/close[d-1]        (the actual close series, up to a constant)
    on[d] = on[d-1] * open[d]/close[d-1]         (compounded OVERNIGHT returns only)
    id[d] = id[d-1] * close[d]/open[d]           (compounded INTRADAY returns only)
and by construction `on[d]/on[d-1] * id[d]/id[d-1] == cc[d]/cc[d-1]` on every session.
The champion's blend is then computed on each index and handed to the shipped algorithm through
**F-3's `S1_ML_SCORES` hook in `ML_MODE="rank"`**, which replaces the ranking ORDER and keeps the
champion's absolute momentum floor as the entry gate. No file the runner loads is modified, and
the score for decision date D uses only bars through D's close (the overnight leg of D is
close[D-1] -> open[D], which is public by D's close), so it is causal.

PRE-REGISTERED before the first number, six clauses
--------------------------------------------------
(1) IDENTITY. The `cc` index pushed through the hook must reproduce the deployed book to the
    digit (CAR 22.192150%, 5,052 orders at 0 bp; 19.640% costed - S-19/S-22/S-25/S-26's cell).
    A momentum blend is scale-free, so a cumulative-return reconstruction of the close series
    must rank identically. If it does not, the export is measuring something other than the
    shipped signal and NOTHING BELOW MAY BE READ.

(2) THE SIGNAL DIAGNOSTIC comes first and is reported whatever the books do. Cross-sectional
    rank IC of each of the three scores against each of the three forward legs of session D+1,
    pooled over 2012-2026 and by half, plus the top-3-minus-equal-weight spread in bps/day,
    which is the quantity the book actually collects. The champion's own cell (cc score ->
    forward overnight leg) is the number every other cell is read against.

(3) THE PRIMARY SCREEN, one cell: `on` scores, `ML_MODE="rank"`, deployed convention, charged
    2 bp of spread and IBKR Pro financing. It is promotable only if it beats the deployed
    19.640% on CAR with drawdown no more than 1.0 point worse (champion.json's own tolerance),
    in the FULL PERIOD and in BOTH halves, at the same cost model. A survivor then has to be
    re-run in LEAN through `scripts/backtest.py` + `scripts/evaluate.py` before anything is
    promoted; this harness may refuse a candidate but it may not promote one.

(4) THE PLACEBO, and it is a real falsification rather than decoration: the SAME construction on
    the `id` index. If the intraday-ranked book also beats the deployed one, then what is being
    measured is not the overnight leg - it is that ANY reconstruction of the momentum blend from
    a noisier price path perturbs the ranking favourably, i.e. luck in the selection of nine
    names over one sample. Clause 3 is then withdrawn even if it passed.

(5) THE EXPECTATION, written down first so the result can be wrong rather than merely reported.
    I expect the primary screen to FAIL, for a reason S-25 already contains: the overnight leg
    carries 94% of the return but the *selection* difference is +3.087 bps/day against a total
    book return of +8.662, so most of the overnight leg is beta the control collects too, and a
    ranking is only as good as its signal-to-noise. An overnight-only index compounds ~35% of
    the close-to-close variance into a 252-day window, so its momentum is a noisier estimate of
    the same trend, and noisier estimates rank worse. What would make me wrong is the overnight
    leg being a separate *persistent* characteristic, which is exactly what clause 2 measures.

(6) NO PROMOTION FROM HERE, NOTHING SHIPPED. `S1_ML_SCORES` stays unset in every deployed path,
    `live/*` and the scheduled tasks are untouched, and every ledger row this script writes is
    tagged DIAGNOSTIC. If clause 3 passes, the deliverable is a LEAN run set for the next
    iteration, not a champion.
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

import signals as sig                                            # noqa: E402
import rates                                                     # noqa: E402
from lean_prices import load_ohlcv                               # noqa: E402
from sweep_s19 import START_EQUITY, paired, summarize, tstat     # noqa: E402
from sweep_s25 import control_legs, identity_check, leg_table, legs_simulate, print_legs  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
EXPORT = REPO / "results" / "s27_scores"
START = "2012-01-03"
END = "2026-09-04"
HALVES = [("IS 2012-2019", START, "2019-12-31"), ("OOS 2020-2026", "2020-01-02", END)]
VARIANTS = ["cc", "on", "id"]
LEGNAME = {"on": "overnight", "id": "intraday", "cc": "close-to-close"}


# ------------------------------------------------------------------ the three price indices

def leg_returns(frames: dict, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Per-session leg returns: `on` = close[d-1]->open[d], `id` = open[d]->close[d]."""
    closes, opens = frames["close"][tickers], frames["open"][tickers]
    on = opens / closes.shift(1) - 1.0
    idy = closes / opens - 1.0
    cc = closes / closes.shift(1) - 1.0
    # the identity that makes the decomposition exact, checked rather than asserted
    resid = ((1 + on) * (1 + idy) - (1 + cc)).abs().max().max()
    return {"on": on, "id": idy, "cc": cc, "resid": resid}


def price_index(legs: dict[str, pd.DataFrame], which: str) -> pd.DataFrame:
    """Cumulative product of one leg's returns, normalized to 1.0 at the first bar."""
    r = legs[which].fillna(0.0)
    return (1.0 + r).cumprod()


def score_frame(index: pd.DataFrame, p) -> pd.DataFrame:
    """The champion's blend, vectorized: mean over lookbacks of the trailing total return.

    Reproduces `signals.blend(signals.horizon_returns(window, ...))` for the shipped
    parameters - `mom_score="blend"`, equal horizon weights, and S-10's **skip of 5 sessions
    applied to horizons of 120 or more** (`mom_skip=5`, `mom_skip_min_lookback=120`), which
    a naive `pct_change` silently omits. Clause 1 verifies the whole chain end to end rather
    than by inspection, and it is what caught the omission.
    """
    total = None
    for lb in p.mom_lookbacks:
        lb = int(lb)
        col = index.pct_change(lb)
        if p.mom_skip and lb >= p.mom_skip_min_lookback:
            col = col.shift(p.mom_skip)
        total = col if total is None else total + col
    return total / float(len(p.mom_lookbacks))


def install_scores(table: pd.DataFrame | None) -> None:
    """Point the shipped `S1_ML_SCORES` hook at an in-memory table (or turn it off)."""
    sig._ML_TABLE = table
    sig._ML_LOADED = True
    sig.ML_MODE = "rank"


# --------------------------------------------------------------- stage A: the signal itself

def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return float("nan")
    ra = pd.Series(a[ok]).rank().to_numpy()
    rb = pd.Series(b[ok]).rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def stage_a(scores: dict[str, pd.DataFrame], legs: dict[str, pd.DataFrame],
            tickers: list[str], start: str, end: str, top_n: int) -> list[dict]:
    """Clause 2: rank IC and the top-n-minus-equal-weight spread, score by forward leg."""
    idx = scores["cc"].index
    lo = idx.searchsorted(pd.Timestamp(start))
    hi = idx.searchsorted(pd.Timestamp(end), side="right")
    rows = []
    for sv in VARIANTS:
        S = scores[sv][tickers].to_numpy()
        for fv in VARIANTS:
            F = legs[fv][tickers].to_numpy()
            ics, spreads, ews = [], [], []
            for i in range(lo, hi - 1):
                s, f = S[i], F[i + 1]                      # decide on D, collect on D+1
                if not np.isfinite(s).any() or not np.isfinite(f).all():
                    continue
                ics.append(spearman(s, f))
                order = np.argsort(-np.where(np.isfinite(s), s, -np.inf))[:top_n]
                spreads.append(1e4 * (f[order].mean() - f.mean()))
                ews.append(1e4 * f.mean())
            ics = np.asarray(ics, dtype=float)
            sp = np.asarray(spreads, dtype=float)
            rows.append({"score": sv, "fwd": fv, "days": len(sp),
                         "IC": np.nanmean(ics), "IC_t": tstat(ics[np.isfinite(ics)]),
                         "spread_bps": sp.mean(), "spread_t": tstat(sp),
                         "ew_bps": float(np.mean(ews))})
    return rows


def print_stage_a(rows: list[dict], label: str) -> None:
    hdr = (f"{'score':<8}{'forward leg':<16}{'days':>6}{'rank IC':>10}{'t':>7}"
           f"{'top3-EW bps':>13}{'t':>7}{'EW bps':>9}")
    print(f"\n--- {label} ---")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{LEGNAME[r['score']][:7]:<8}{LEGNAME[r['fwd']]:<16}{r['days']:>6}"
              f"{r['IC']:>+10.4f}{r['IC_t']:>+7.2f}{r['spread_bps']:>+13.3f}"
              f"{r['spread_t']:>+7.2f}{r['ew_bps']:>+9.3f}")


# ----------------------------------------------------------------------- stage B: the books

def run_book(frames, params, tables, variant, start, end, spread, fin):
    install_scores(tables[variant])
    try:
        return legs_simulate(frames, params, "both", start, end, spread, fin)
    finally:
        install_scores(None)


def record(rows: list[dict], note: str, no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s27_rank", "class": "book",
                "tag": f"S-27 {r['cell'].strip()} ({note})", "commit": "", "run_dir": "",
                "track": "S-27", "start": r.get("start", START), "end": r.get("end", END),
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
    ap.add_argument("--stage", choices=["a", "b", "ab"], default="ab")
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--export", action="store_true",
                    help="write the three score tables to results/s27_scores/ for LEAN")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    params = sig.Params()
    tickers = sig.traded_universe(params)
    ranked = [t for t in params.rank_universe]
    frames = load_ohlcv(tickers)
    fin = {"rates": rates.load(), "spread": 0.0}
    print(f"store: {len(tickers)} tickers, {frames['close'].index[0].date()} .. "
          f"{frames['close'].index[-1].date()}   rank universe {len(ranked)}: "
          f"{' '.join(ranked)}")
    print(f"window {args.start} .. {args.end}   lookbacks {params.mom_lookbacks}   "
          f"skip {params.mom_skip} on >= {params.mom_skip_min_lookback}   "
          f"top_n {params.top_n}\n")

    legs = leg_returns(frames, ranked)
    print(f"leg decomposition residual (1+on)(1+id)-(1+cc): {legs['resid']:.2e}  "
          f"-> the two legs are exact")

    indices = {v: price_index(legs, v) for v in VARIANTS}
    scores = {v: score_frame(indices[v], params) for v in VARIANTS}
    tables = {}
    for v in VARIANTS:
        t = scores[v].copy()
        t.index = pd.to_datetime(t.index).normalize()
        t = t.loc[t.notna().all(axis=1)]          # drop the leading warm-up block only
        tables[v] = t
        if args.export:
            EXPORT.mkdir(parents=True, exist_ok=True)
            t.to_csv(EXPORT / f"s27_{v}.csv")
    print(f"score tables: {len(tables['cc'])} rows, "
          f"{tables['cc'].index[0].date()} .. {tables['cc'].index[-1].date()}"
          + (f"   exported to {EXPORT}" if args.export else ""))

    # ------------------------------------------------------------------ clause 1: identity
    print("\n=== clause 1: does the exported close-to-close score reproduce the champion? ===")
    dep = legs_simulate(frames, params, "both", args.start, args.end, 0.0, None)
    hook = run_book(frames, params, tables, "cc", args.start, args.end, 0.0, None)
    a, b = summarize(hook, "cc through the hook"), summarize(dep, "deployed book")
    print(f"  hook (cc scores)   CAR {a['CAR']:.6f}%  Sharpe {a['Sharpe']:.6f}  "
          f"orders {a['orders']:,}  end ${a['end_equity']:,.2f}")
    print(f"  deployed book      CAR {b['CAR']:.6f}%  Sharpe {b['Sharpe']:.6f}  "
          f"orders {b['orders']:,}  end ${b['end_equity']:,.2f}")
    same = abs(a["CAR"] - b["CAR"]) < 1e-9 and a["orders"] == b["orders"]
    print(f"  VERDICT: {'PASS' if same else 'FAIL'} - the hook reproduces the shipped ranking"
          f"{'' if same else '  (READ NOTHING BELOW)'}")
    if not same:
        d = paired(hook, dep, "hook", "deployed")
        print(f"  paired difference {d['bps_per_day']:+.4f} bps/day (t {d['t']:+.2f})")
        return 1

    # ------------------------------------------------------------------ stage A: the signal
    if args.stage in ("a", "ab"):
        print("\n=== clause 2: what each score forecasts, cross-sectionally ===")
        print("Decide on D's score, collect D+1's leg. 'top3-EW' is the champion's own\n"
              "selection size against the equal-weight nine-name control - the quantity the\n"
              "book collects, in bps/day, before any cost or leverage.")
        print_stage_a(stage_a(scores, legs, ranked, args.start, args.end, params.top_n),
                      f"full period {args.start} .. {args.end}")
        for name, lo, hi in HALVES:
            print_stage_a(stage_a(scores, legs, ranked, lo, hi, params.top_n), name)

    # ------------------------------------------------------------------- stage B: the books
    if args.stage in ("b", "ab"):
        print("\n=== clauses 3 and 4: the books, on the deployed convention ===")
        screen, books = [], {}
        for spread in (0.0, args.spread_bps):
            for v in VARIANTS:
                key = f"{v} @ {spread:g}bp"
                bk = run_book(frames, params, tables, v, args.start, args.end, spread,
                              fin if spread else None)
                books[key] = bk
                s = summarize(bk, key)
                s["turnover_x"] = float(bk["turnover"].sum() / START_EQUITY / (len(bk) / 252))
                screen.append(s)
        hdr = (f"{'cell':<16}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
               f"{'orders':>8}{'fees':>10}{'turn x/yr':>11}")
        print(hdr)
        print("-" * len(hdr))
        for s in screen:
            print(f"{s['cell']:<16}{s['sessions']:>6}{s['CAR']:>9.3f}{s['Sharpe']:>8.3f}"
                  f"{s['MaxDD']:>8.3f}{s['std']:>7.3f}{s['orders']:>8,}{s['fees']:>10,.0f}"
                  f"{s['turnover_x']:>11.1f}")
        print("\n  (the costed rows carry 2 bp of spread and IBKR Pro financing; the 0 bp rows\n"
              "   carry neither, so the 'cc @ 0bp' row is the champion's own 22.192150%)")

        base = f"cc @ {args.spread_bps:g}bp"
        print(f"\npaired daily difference against '{base}' (bps/day):")
        for v in VARIANTS[1:]:
            p = paired(books[f"{v} @ {args.spread_bps:g}bp"], books[base],
                       f"{v} @ {args.spread_bps:g}bp", base)
            print(f"  {p['pair']:<36}{p['bps_per_day']:>+8.3f}  t {p['t']:>+6.2f}  "
                  f"({p['days']} days)")

        print("\nhalves at the costed spread - clause 3 needs BOTH:")
        halves: dict[str, list[dict]] = {v: [] for v in VARIANTS}
        for name, lo, hi in HALVES:
            line = f"  {name:<16}"
            for v in VARIANTS:
                bk = run_book(frames, params, tables, v, lo, hi, args.spread_bps, fin)
                s = summarize(bk, f"{v} {name}")
                s["start"], s["end"] = lo, hi
                screen.append(s)
                halves[v].append(s)
                line += f"{v:>6} {s['CAR']:>7.3f} (DD {s['MaxDD']:>5.1f})"
            print(line)

        # --- where the change lands: the leg attribution of each ranked book
        print("\nleg attribution of each ranking, against the same-gross always-invested control:")
        ctrl = control_legs(frames, [t for t in tickers if t in frames["close"].columns],
                            books["cc @ 0bp"]["date"])
        rows = []
        for v in VARIANTS:
            rows += [dict(r, window=f"{LEGNAME[v][:9]} rank")
                     for r in leg_table(books[f"{v} @ 0bp"], ctrl, v)
                     if r["control"] == "EW sleeve"]
        print_legs(rows)

        # --- the verdict, against the pre-registered marks
        dep_car = summarize(books[base], "d")["CAR"]
        dep_dd = summarize(books[base], "d")["MaxDD"]
        print(f"\n=== verdict against the pre-registered marks (deployed {dep_car:.3f}% / "
              f"DD {dep_dd:.3f}) ===")
        for v in VARIANTS[1:]:
            s = summarize(books[f"{v} @ {args.spread_bps:g}bp"], v)
            full_ok = s["CAR"] > dep_car and s["MaxDD"] <= dep_dd + 1.0
            half_ok = all(h["CAR"] > d["CAR"]
                          for h, d in zip(halves[v], halves["cc"]))
            tag = "PASS" if (full_ok and half_ok) else "REFUSED"
            role = "PRIMARY" if v == "on" else "PLACEBO"
            print(f"  {role} {LEGNAME[v]:<15} CAR {s['CAR']:>7.3f} DD {s['MaxDD']:>6.3f}  "
                  f"full {'ok' if full_ok else 'no':<3} halves {'ok' if half_ok else 'no':<3}"
                  f"  -> {tag}")

        for s in screen:
            s.setdefault("start", args.start)
            s.setdefault("end", args.end)
        record(screen, f"pandas book, {args.start}..{args.end}, IBKR Pro financing, "
                       f"{args.spread_bps:g} bp screen - DIAGNOSTIC, not promotable",
               args.no_record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
