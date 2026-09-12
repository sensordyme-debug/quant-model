#!/usr/bin/env python
"""S-26: can the champion's alpha-free intraday leg be hedged away cheaply enough to pay?

    python scripts/sweep_s26.py                  # the whole thing (~15 min, 20+ full books)
    python scripts/sweep_s26.py --quick          # identity + proxy + grid only
    python scripts/sweep_s26.py --no-record      # do not append to the ledger

S-25 measured the one split nobody had separated: the deployed daily book earns **+8.103
bps/day overnight (t +6.80, 94% of its return)** against **+0.738 intraday (t +0.47)**, and
against an always-invested control at the book's own gross the *selection* difference is
**+3.087 bps/day at t +4.20 overnight** and **-0.314 at t -0.37 intraday**. Fourteen years
find no intraday content in this ranking. The intraday leg nevertheless carries the larger
share of the risk - annualized 0.151 against the overnight leg's 0.115.

S-25 also closed the obvious way to act on that: a book that liquidates at the open and
re-establishes at the close turns over 1,248x its equity a year and loses *before a cent of
cost is charged*. So the leg cannot be isolated by trading the equity book. It can only be
isolated by **overlaying a short of the index over one leg**, and that is only worth asking
because F-2a measured the instrument: an ES round trip costs **0.488 bps of notional**
(MES 0.744) against the 4.70-8.20 bps every intraday refusal in this repository was written
on. This iteration puts the two results together and prices the overlay.

The mechanism, stated plainly: short `h * beta * equity` of the index from the open to the
close, where beta is the trailing OLS slope of the book's own intraday leg on the index's.
That removes most of the intraday variance, gives up whatever the index's own intraday leg
drifts, and pays one futures round trip a session. If the risk it removes is worth more than
the drift it sells, the freed budget can be levered back, and the comparison is the
vol-matched one S-15/S-20 made compulsory on this sleeve.

PRE-REGISTERED before the first number, seven clauses
----------------------------------------------------
(1) IDENTITY. With `hedge=None, scale=1.0` the harness must reproduce S-25's deployed cell
    to the digit (CAR 22.192150%, 5,052 orders) and the leg+cost residual must stay at
    ~1e-16 of equity with the hedge columns carried. If it does not, the two new arguments
    changed the book rather than overlaying on it and nothing below may be read.

(2) THE PROXY IS VALIDATED, NOT ASSUMED. The overlay is priced on the *index ETF's* own
    open-to-close return from the daily store, because no long ES history exists (F-2a:
    IBKR retains ~4 expired quarters, CONTFUT cannot be paged). That substitution is only
    admissible if ES's cash session actually tracks it, so it is checked on F-2a's 313-session
    store: **correlation >= 0.95 and a regression slope within 0.05 of 1.0**, or the overlay
    is reported as unresolvable on the data this repository holds.

(3) SAY WHAT THE HEDGE SELLS, BEFORE PRICING WHAT IT BUYS. The intraday leg has no *alpha*;
    it does not follow that it has no *return*. The index's own intraday leg over this window
    is reported first with its t-statistic, because the whole trade is an exchange of one
    drift for a reduction in variance and the honest framing is which of the two is better
    measured.

(4) THE GRID, unhedged and h = 0.25 / 0.50 / 0.75 / 1.00, all charged what they do: 2 bp of
    one-way equity spread, IBKR Pro financing on the settled balance (S-21's hook) and the
    futures round trip on the hedge notional every session.

(5) PRIMARY SCREEN, on the vol-matched column. The hedged book is scaled - on the real
    machinery, so gross, commission and the financed debit all follow - until its realized
    annualized volatility matches the deployed book's. It is promotable only if it beats the
    deployed book's CAR with drawdown no more than 1.0 point worse (`evaluate.py`'s criteria,
    transplanted to the harness that can express this book) **in the full period and in both
    halves**, and only if the scaled gross stays inside Reg-T's 2.0x.
    THE EXPECTATION, WRITTEN DOWN FIRST SO THE RESULT CAN BE WRONG RATHER THAN MERELY
    REPORTED: refused, and narrowly. The index's intraday leg drifted up over 2012-2026, so
    at beta ~1 and 1.25x gross the hedge sells roughly 1.5-2.0 bps/day and pays another
    0.6 bps of round trip against a book earning 8.66 bps/day; the vol it removes buys back
    perhaps a third more size. Those are the same order of magnitude, which is why it is
    worth measuring rather than reasoning about, and which is why the deliverable if it fails
    is the BREAKEVEN rather than the refusal.

(6) PLACEBO, which is the clause that decides what a pass would even mean. Run the identical
    overlay on the OVERNIGHT leg. If hedging the leg that carries all of the alpha helps too,
    then nothing here is about the split - the overlay is just a volatility reduction that
    the vol-matching then undoes, and the result is about leverage rather than about legs.
    The overnight overlay must be materially WORSE than the intraday one.
    (One known bias, stated rather than corrected: the store is back-adjusted, so its
    overnight leg carries the ex-date credit that a short future does not pay. That biases
    the overnight placebo against the hedge by about the sleeve's yield, ~0.5 bps/day, which
    is immaterial against the size of the effect being looked for.)

(7) NOTHING HERE IS SHIPPABLE BY THE LOOP EVEN IF IT PASSES. The overlay needs a futures
    position, which is the owner decision in `BLOCKERS.md` (F-2a: the account already has the
    data permission; what is missing is history, and what a live overlay needs is the owner's
    consent to hold futures at all). So a pass is evidence for that decision, not a
    deployment, and every row is tagged DIAGNOSTIC. Granularity is reported for the same
    reason: one ES contract is ~$347k of notional and one MES ~$35k, so a small book cannot
    hold the hedge continuously and the integer rounding is part of the honest price.
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

import signals as sig                                        # noqa: E402
import rates                                                 # noqa: E402
from lean_prices import load_ohlcv                           # noqa: E402
from sweep_s19 import START_EQUITY, paired, summarize, tstat  # noqa: E402
from sweep_s25 import legs_simulate, identity_check           # noqa: E402
from sweep_f2 import cost_table                              # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
FUTURES = REPO / "data" / "futures" / "ES.parquet"
START = "2012-01-03"
END = "2026-09-04"
HALVES = [("IS 2012-2019", START, "2019-12-31"), ("OOS 2020-2026", "2020-01-02", END)]
ET = "America/New_York"
REG_T = 2.0
S25_DEPLOYED_CAR = 22.192150170492255        # clause 1: S-25's own printed figure


# ------------------------------------------------------------------ clause 2: the proxy

def es_cash_sessions() -> pd.DataFrame:
    """ES front-quarter open-to-close return over the 09:30-16:00 ET cash session."""
    if not FUTURES.exists():
        return pd.DataFrame(columns=["date", "es_ret"])
    df = pd.read_parquet(FUTURES)
    t = df["t"].dt.tz_convert(ET)
    m = ((t.dt.hour * 60 + t.dt.minute) >= 9 * 60 + 30) & \
        ((t.dt.hour * 60 + t.dt.minute) < 16 * 60)
    df = df.loc[m].assign(date=t[m].dt.normalize().dt.tz_localize(None))
    g = df.groupby("date")
    first_open = g["o"].first()
    last_close = g["c"].last()
    bars = g.size()
    out = pd.DataFrame({"date": first_open.index, "es_ret": (last_close / first_open - 1).to_numpy(),
                        "bars": bars.to_numpy()})
    return out[out["bars"] > 200].reset_index(drop=True)        # full sessions only


def proxy_check(frames: dict, bench: str) -> dict:
    """Clause 2: does ES's cash session track the benchmark ETF's open-to-close return?"""
    es = es_cash_sessions()
    if es.empty:
        return {"ok": False, "n": 0, "why": "no ES store"}
    c, o = frames["close"][bench], frames["open"][bench]
    etf = pd.DataFrame({"date": c.index, "etf_ret": (c / o - 1.0).to_numpy()})
    m = es.merge(etf, on="date").dropna()
    x, y = m["etf_ret"].to_numpy(), m["es_ret"].to_numpy()
    corr = float(np.corrcoef(x, y)[0, 1])
    slope = float(np.cov(y, x, ddof=1)[0, 1] / x.var(ddof=1))
    resid = y - slope * x
    return {"ok": corr >= 0.95 and abs(slope - 1.0) <= 0.05, "n": len(m), "corr": corr,
            "slope": slope, "basis_sd_bps": float(1e4 * resid.std(ddof=1)),
            "mean_es_bps": float(1e4 * y.mean()), "mean_etf_bps": float(1e4 * x.mean()),
            "first": str(m["date"].iloc[0].date()), "last": str(m["date"].iloc[-1].date())}


# ---------------------------------------------------------------------------- the books

def run(frames: dict, params, *, ratio: float, scale: float = 1.0, spread: float = 2.0,
        cost_bps: float = 0.0, leg: str = "intraday", window: int = 60,
        bench: str = "SPY", fin: dict | None = None,
        start: str = START, end: str = END) -> pd.DataFrame:
    hedge = None if ratio == 0.0 else {"ratio": ratio, "leg": leg, "cost_bps": cost_bps,
                                       "window": window, "bench": bench}
    return legs_simulate(frames, params, "both", start, end, spread, fin,
                         hedge=hedge, scale=scale)


def describe(book: pd.DataFrame, label: str) -> dict:
    s = summarize(book, label)
    s["gross_x"] = float(book["gross_x"].mean())
    s["gross_max"] = float(book["gross_x"].max())
    s["hedge_x"] = float(book["hedge_x"].abs().mean())
    s["hedge_fee"] = float(book["hedge_fee"].sum())
    s["beta"] = float(book["hedge_beta"].mean(skipna=True))
    s["turnover_x"] = float(book["turnover"].sum() / START_EQUITY / (len(book) / 252))
    return s


def table(rows: list[dict]) -> None:
    hdr = (f"{'cell':<26}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
           f"{'gross':>7}{'hedge':>7}{'beta':>6}{'fut fee':>10}{'turn x/yr':>11}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['cell']:<26}{r['sessions']:>6}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}"
              f"{r['MaxDD']:>8.3f}{r['std']:>7.3f}{r['gross_x']:>7.2f}{r['hedge_x']:>7.2f}"
              f"{r['beta']:>6.2f}{r['hedge_fee']:>10,.0f}{r['turnover_x']:>11.1f}")


def vol_match(frames: dict, params, target_std: float, *, tol: float = 0.002,
              max_iter: int = 4, **kw) -> tuple[pd.DataFrame, float, list[str]]:
    """Scale the book on the real machinery until its realized vol matches `target_std`."""
    trace = []
    bk = run(frames, params, scale=1.0, **kw)
    s0 = summarize(bk, "x")["std"]
    trace.append(f"scale 1.000 -> std {s0:.4f}")
    k = target_std / s0
    for _ in range(max_iter):
        bk = run(frames, params, scale=k, **kw)
        s = summarize(bk, "x")["std"]
        trace.append(f"scale {k:.3f} -> std {s:.4f}")
        if abs(s - target_std) <= tol * target_std:
            break
        k *= target_std / s
    return bk, k, trace


# ------------------------------------------------------------------------------- ledger

def record(rows: list[dict], note: str, no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s26_hedge", "class": "book",
                "tag": f"S-26 {r['cell'].strip()} ({note})", "commit": "", "run_dir": "",
                "track": "S-26", "start": r.get("start", START), "end": r.get("end", END),
                "stats": {"Sessions": str(r["sessions"]),
                          "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.3f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees'] + r['hedge_fee']:.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--bench", default="SPY")
    ap.add_argument("--window", type=int, default=60, help="trailing sessions for the beta")
    ap.add_argument("--hedge-cost-bps", type=float, default=None,
                    help="futures round trip; default = F-2a's ES half-tick figure")
    ap.add_argument("--quick", action="store_true", help="skip clauses 5 to 7")
    ap.add_argument("--stage", default="all", choices=["all", "a", "b", "c"],
                    help="a = clauses 1-4, b = clause 5, c = clauses 6-7. Each stage is a "
                         "self-contained run of about five minutes, which is how it fits "
                         "inside a foreground call; 'all' is the same thing end to end.")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    ct = cost_table()
    es_rt = float(ct[(ct.sym == "ES") & (ct.spread == "half tick")]["total_bps"].iloc[0])
    es_full = float(ct[(ct.sym == "ES") & (ct.spread == "full tick")]["total_bps"].iloc[0])
    mes_rt = float(ct[(ct.sym == "MES") & (ct.spread == "half tick")]["total_bps"].iloc[0])
    cost = es_rt if args.hedge_cost_bps is None else args.hedge_cost_bps

    params = sig.Params()
    tickers = sig.traded_universe(params)
    frames = load_ohlcv(tickers)
    fin = {"rates": rates.load(), "spread": 0.0}
    kw = dict(spread=args.spread_bps, leg="intraday", window=args.window,
              bench=args.bench, fin=fin, start=args.start, end=args.end)
    print(f"store: {len(tickers)} tickers, {frames['close'].index[0].date()} .. "
          f"{frames['close'].index[-1].date()}")
    print(f"window {args.start} .. {args.end}   hedge benchmark {args.bench}   "
          f"beta window {args.window} sessions")
    print(f"futures round trip charged: {cost:.3f} bps of hedge notional per session "
          f"(F-2a: ES half tick {es_rt:.3f}, MES {mes_rt:.3f})\n")

    stage = args.stage
    # -------------------------------------------------------------- clause 1: identity
    if stage in ("all", "a"):
        print("=== clause 1: do the two new arguments leave the deployed book alone? ===")
        dep0 = run(frames, params, ratio=0.0, spread=0.0, fin=None,
                   start=args.start, end=args.end)
        d0 = describe(dep0, "deployed @ 0bp, no fin")
        idc = identity_check(dep0, 0.0)
        same = abs(d0["CAR"] - S25_DEPLOYED_CAR) < 1e-9
        print(f"  legs_simulate(hedge=None, scale=1.0)   CAR {d0['CAR']:.6f}%  "
              f"orders {d0['orders']:,}")
        print(f"  S-25's own printed cell                CAR {S25_DEPLOYED_CAR:.6f}%  "
              f"orders 5,052")
        print(f"  leg+cost identity  max |residual| "
              f"{idc['max_resid_frac_of_equity']:.2e} of equity")
        if (args.start, args.end) != (START, END):
            print("  (window moved from S-25's, so only the residual is a check here)\n")
        else:
            print(f"  VERDICT: {'PASS' if same else 'FAIL'}"
                  f"{'' if same else ' - READ NOTHING BELOW'}\n")
            if not same:
                return 1

        # ------------------------------------------------------------- clause 2: proxy
        print("=== clause 2: is the index ETF an admissible stand-in for the future? ===")
        pc = proxy_check(frames, args.bench)
        if not pc["n"]:
            print("  no ES store - clause 2 cannot be evaluated, the overlay is "
                  "unresolvable\n")
        else:
            print(f"  {pc['n']} overlapping cash sessions, {pc['first']} .. {pc['last']} "
                  f"(F-2a's front-quarter stitch)")
            print(f"  corr(ES cash session, {args.bench} open->close) = {pc['corr']:.4f}   "
                  f"slope {pc['slope']:.4f}   basis sd {pc['basis_sd_bps']:.1f} bps/session")
            print(f"  means: ES {pc['mean_es_bps']:+.2f} bps/day, {args.bench} "
                  f"{pc['mean_etf_bps']:+.2f} bps/day")
            print(f"  VERDICT: {'PASS' if pc['ok'] else 'FAIL'} - the overlay may be priced "
                  f"on the ETF leg with a {pc['basis_sd_bps']:.1f} bps basis noise\n")

    # the unhedged book every stage is quoted against, and the vol-matching target
    base = run(frames, params, ratio=0.0, cost_bps=cost, **kw)
    tgt_std = summarize(base, "b")["std"]

    # ------------------------------------------------- clause 3: what the hedge sells
    print("=== clause 3: the drift the hedge gives up, before anything it buys ===")
    c, o = frames["close"][args.bench], frames["open"][args.bench]
    idx = base["date"]
    b_id = 1e4 * (c / o - 1.0).reindex(idx).to_numpy()
    b_on = 1e4 * (o / c.shift(1) - 1.0).reindex(idx).to_numpy()
    print(f"  {args.bench} intraday leg (open->close)  {np.nanmean(b_id):+7.3f} bps/day  "
          f"t {tstat(b_id):+5.2f}")
    print(f"  {args.bench} overnight leg (close->open) {np.nanmean(b_on):+7.3f} bps/day  "
          f"t {tstat(b_on):+5.2f}")
    for name, lo, hi in HALVES:
        m = (idx >= pd.Timestamp(lo)) & (idx <= pd.Timestamp(hi))
        print(f"    {name:<16} intraday {np.nanmean(b_id[m.to_numpy()]):+7.3f} "
              f"(t {tstat(b_id[m.to_numpy()]):+5.2f})   overnight "
              f"{np.nanmean(b_on[m.to_numpy()]):+7.3f} (t {tstat(b_on[m.to_numpy()]):+5.2f})")
    print("  The intraday leg has no ALPHA (S-25: -0.314 bps/day at t -0.37 against the")
    print("  same-gross control). Whether it has a RETURN is the line above, and the overlay")
    print("  sells it at beta times the book's gross.\n")

    # -------------------------------------------------------------- clause 4: the grid
    rows, books = [], {"unhedged": base}
    if stage in ("all", "a"):
        print("=== clause 4: the grid, everything charged for what it does ===")
        rows.append(describe(base, "unhedged"))
        for ratio in (0.25, 0.50, 0.75, 1.00):
            key = f"h={ratio:.2f}"
            books[key] = run(frames, params, ratio=ratio, cost_bps=cost, **kw)
            rows.append(describe(books[key], key))
        table(rows)
        print(f"\n  ({args.spread_bps:g} bp one-way equity spread + IBKR Pro financing + "
              f"{cost:.3f} bps of futures round trip)")
        print("  paired daily difference against the unhedged book (bps/day):")
        for key, bk in books.items():
            if key == "unhedged":
                continue
            p = paired(bk, base, key, "unhedged")
            print(f"    {p['pair']:<28}{p['bps_per_day']:>+8.3f}  t {p['t']:>+6.2f}")
        print(f"\n  the vol-matching target is the unhedged book's own realized std "
              f"{tgt_std:.4f}")
        if args.quick or stage == "a":
            record(rows, f"pandas book, {args.start}..{args.end}, IBKR Pro financing, "
                         f"{args.spread_bps:g} bp spread, {cost:.3f} bps futures round trip "
                         f"- DIAGNOSTIC, not promotable", args.no_record)
            return 0

    # -------------------------------------------------- clause 5: the primary screen
    vm_rows, vm_books = [], {}
    if stage in ("all", "b"):
        print("\n=== clause 5: the primary screen, on the vol-matched column ===")
        for ratio in (0.50, 1.00):
            bk, k, trace = vol_match(frames, params, tgt_std, ratio=ratio,
                                     cost_bps=cost, **kw)
            key = f"h={ratio:.2f} vol-matched"
            vm_books[key] = (bk, k)
            vm_rows.append(describe(bk, key))
            print(f"  {key}: " + "; ".join(trace))
        table([describe(base, "unhedged (the bar)")] + vm_rows)
        print("\n  paired daily difference against the unhedged book (bps/day):")
        for key, (bk, k) in vm_books.items():
            p = paired(bk, base, key, "unhedged")
            print(f"    {p['pair']:<40}{p['bps_per_day']:>+8.3f}  t {p['t']:>+6.2f}")
        print("\n  halves - clause 5 needs BOTH (CAR%, drawdown in brackets):")
        half_rows = []
        for name, lo, hi in HALVES:
            line = f"    {name:<16}"
            hb = run(frames, params, ratio=0.0, cost_bps=cost,
                     **{**kw, "start": lo, "end": hi})
            hs = describe(hb, f"unhedged {name}")
            half_rows.append(hs)
            line += f"unhedged {hs['CAR']:>7.3f} (DD {hs['MaxDD']:>5.1f})   "
            for key, (bk, k) in vm_books.items():
                hb2 = run(frames, params, ratio=float(key.split("=")[1].split()[0]), scale=k,
                          cost_bps=cost, **{**kw, "start": lo, "end": hi})
                hs2 = describe(hb2, f"{key} {name}")
                half_rows.append(hs2)
                line += f"{key.split()[0]} {hs2['CAR']:>7.3f} (DD {hs2['MaxDD']:>5.1f})   "
            print(line)
        print("\n  Reg-T: the scaled book's mean/max gross exposure, which must stay under "
              f"{REG_T:.1f}x")
        for r in vm_rows:
            ok = r["gross_max"] <= REG_T
            print(f"    {r['cell']:<26} mean {r['gross_x']:.2f}x  max {r['gross_max']:.2f}x  "
                  f"-> {'inside' if ok else 'OUTSIDE REG-T'}")

        # the screen itself, on evaluate.py's criteria transplanted to this harness
        bar = describe(base, "bar")
        print("\n  VERDICT on clause 5's criteria (CAR up, drawdown no more than 1.0 point "
              "worse, in\n  the full period and in both halves, inside Reg-T):")
        for r in vm_rows:
            hs = [h for h in half_rows if h["cell"].startswith(r["cell"])]
            hb = {h["cell"].split()[-2] + " " + h["cell"].split()[-1]: h
                  for h in half_rows if h["cell"].startswith("unhedged ")}
            fails = []
            if r["CAR"] <= bar["CAR"]:
                fails.append(f"CAR {r['CAR']:.3f} <= {bar['CAR']:.3f}")
            if r["MaxDD"] > bar["MaxDD"] + 1.0:
                fails.append(f"drawdown {r['MaxDD']:.3f} > {bar['MaxDD']:.3f} + 1.0")
            for h in hs:
                key = " ".join(h["cell"].split()[-2:])
                ref = hb.get(key)
                if ref and h["CAR"] <= ref["CAR"]:
                    fails.append(f"{key} CAR {h['CAR']:.3f} <= {ref['CAR']:.3f}")
            if r["gross_max"] > REG_T:
                fails.append(f"gross {r['gross_max']:.2f}x > {REG_T:.1f}x")
            print(f"    {r['cell']:<26} {'PASS' if not fails else 'REFUSED: ' + '; '.join(fails)}")
        for r in vm_rows + half_rows:
            r["start"], r["end"] = args.start, args.end
        if stage == "b":
            record(vm_rows, f"pandas book, {args.start}..{args.end}, IBKR Pro financing, "
                            f"{args.spread_bps:g} bp spread, {cost:.3f} bps futures round "
                            f"trip, VOL-MATCHED - DIAGNOSTIC, not promotable", args.no_record)
            return 0

    # ------------------------------------------------------------- clause 6: placebo
    print("\n=== clause 6: the placebo - the same overlay on the leg that has the alpha ===")
    pl_rows = []
    for leg in ("intraday", "overnight"):
        bk = run(frames, params, ratio=1.00, cost_bps=cost, **{**kw, "leg": leg})
        r = describe(bk, f"h=1.00 {leg} hedge")
        pl_rows.append(r)
        r["_paired"] = paired(bk, base, r["cell"], "unhedged")
        if leg == "intraday":
            books["h=1.00"] = bk
    table(pl_rows)
    for r in pl_rows:
        print(f"    {r['_paired']['pair']:<44}{r['_paired']['bps_per_day']:>+8.3f}  "
              f"t {r['_paired']['t']:>+6.2f}")

    # ------------------------------------------------- clause 7: breakeven + granularity
    print("\n=== clause 7: the breakeven, which is the durable number if the screen refuses ===")
    print("The hedge notional is quoted against each session's OWN equity, never against the")
    print("$100k it started with: the edge is a bps-of-equity-per-day number, so the turnover")
    print("it is divided by has to be on the same basis or the breakeven is wrong by the")
    print("factor the book compounded (S-25's own turnover column is on the start-equity")
    print("basis, which is fine as a ledger statistic and is not what this division needs).\n")
    for ratio in (0.50, 1.00):
        free, k, _ = vol_match(frames, params, tgt_std, ratio=ratio, cost_bps=0.0, **kw)
        d = paired(free, base, f"h={ratio:.2f} free", "unhedged")
        s = describe(free, f"h={ratio:.2f} vol-matched, hedge free")
        hedge_x = s["hedge_x"]                      # mean notional per unit of live equity
        room = d["bps_per_day"] / hedge_x if hedge_x else float("nan")
        print(f"  h={ratio:.2f}  at ZERO hedge cost: CAR {s['CAR']:.3f}% vs the unhedged "
              f"{summarize(base, 'b')['CAR']:.3f}%, edge {d['bps_per_day']:+.3f} bps/day "
              f"(t {d['t']:+.2f})")
        print(f"         hedge notional {hedge_x:.2f}x live equity a session "
              f"({hedge_x * 252:.0f}x/yr)  ->  BREAKEVEN {room:+.3f} bps round trip"
              f"   (ES half tick {es_rt:.3f}, full tick {es_full:.3f}, MES {mes_rt:.3f})")
        vm_rows.append(s)
    hx = books["h=1.00"]["hedge_notional"].abs()
    eq = books["h=1.00"]["prev"]
    one_es, one_mes = 347_117.0, 34_712.0
    print(f"\n  granularity, because a contract is not divisible: the h=1.00 hedge needs a "
          f"median ${hx.median():,.0f} of notional")
    print(f"    below one ES contract (${one_es:,.0f}) on "
          f"{100 * (hx < one_es).mean():.1f}% of sessions, below one MES "
          f"(${one_mes:,.0f}) on {100 * (hx < one_mes).mean():.1f}%")
    print(f"    mean integer rounding error in MES units: "
          f"{100 * (hx / one_mes % 1.0).mean() / (hx / one_mes).mean():.1f}% of the hedge, "
          f"and the book's equity runs ${eq.iloc[0]:,.0f} -> ${eq.iloc[-1]:,.0f}")

    for r in rows + vm_rows + pl_rows:
        r["start"], r["end"] = args.start, args.end
        r.pop("_paired", None)
    record(rows + vm_rows + pl_rows,
           f"pandas book, {args.start}..{args.end}, IBKR Pro financing, "
           f"{args.spread_bps:g} bp spread, {cost:.3f} bps futures round trip "
           f"- DIAGNOSTIC, not promotable", args.no_record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
