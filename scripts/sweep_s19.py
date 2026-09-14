#!/usr/bin/env python
"""S-19: price the deployed daily runner's clock EXACTLY, instead of bounding it.

The defect is S-17's and it is not in dispute: `scripts/paper_trade.py` runs at 15:45 ET
on day D, calls `yf.download(period="2y")`, whose last *complete* daily bar at that moment
is D-1's close, and then sends market orders that fill at the close of D. The LEAN
backtest decides on the close of D and fills at the open of D+1. Written as one index, with
`i` the session the orders actually fill in:

    convention   last close the signal reads   fills at      elapsed signal -> fill
    ----------   ---------------------------   --------      ----------------------
    backtest     close[i-1]                    open[i]       one overnight gap
    deployed     close[i-1]                    close[i]      one overnight gap + a session
    lag1         close[i-2]                    open[i]       two overnight gaps + a session

So the backtest and the deployed runner **decide identically** - same signal, same bars,
same order list on the first day - and differ in one thing only: where the order fills.
`S1_SIGNAL_LAG=1`, which is all LEAN can express on daily bars (a bar for D arrives stamped
D 16:00, so nothing submitted then can fill at D's close), is the third row: one whole
overnight gap staler than the live path, which is why S-17 called it an upper bound and not
a measurement.

This script measures the first two rows against each other by running the *shared*
`algorithms/s1_momo/signals.py` through a share-level book that fills wherever it is told.
That makes the comparison paired by construction: the two books see the same targets from
the same history and differ only in the price paid, so the difference is the clock and
nothing else.

The third row is carried too, because it is the cell LEAN can run: if this book reproduces
LEAN's control and LEAN's `S1_SIGNAL_LAG=1` at both ends, the number in the middle - the
one nothing else can produce - is believable.

    python scripts/sweep_s19.py                 # the four conventions, full period + halves
    python scripts/sweep_s19.py --lean          # also print the LEAN rows from the ledger
    python scripts/sweep_s19.py --no-record     # do not append to the ledger

Nothing here is a candidate for promotion: every row is the *same strategy* executed at a
different moment, so the winner is already known (the earliest fill) and the question is
only what the difference is worth. The answer belongs in BLOCKERS.md, where the owner is
being asked to move a scheduled task.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quant_brain.core.validation import LeakageError

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                       # noqa: E402
import rates                                # noqa: E402  (S-22: optional financing hook)
from lean_prices import load_ohlcv          # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"

START = "2012-01-03"
END = "2026-09-04"
MIN_ORDER_VALUE = 0.01                      # main.py's shipped band
START_EQUITY = 100_000.0

#: LEAN's `InteractiveBrokersFeeModel` for US equities, as the champion's own runs charge
#: it: a per-share rate with a per-order minimum and a cap at a fraction of trade value.
#: Calibrated rather than assumed - `--lean` prints the control's total fees beside this
#: book's, and the two have to agree before any row below is read.
#:
#: S-44 took the constants off the engine's source rather than off the calibration:
#: `InteractiveBrokersFeeModel.cs:150` is `feePerShare: 0.005m, minimumFee: 1,
#: maximumFeeRate: 0.005m`, so the cap rate was **0.01 here and 0.005 there**.
FEE_PER_SHARE = 0.005
FEE_MIN = 1.00
FEE_MAX_FRAC = 0.005


def commission(shares: float, price: float) -> float:
    """LEAN's US-equity IB fee, transcribed from `InteractiveBrokersFeeModel.cs:161-172`.

    Two things about the shape, and S-44 got the second one only by transcribing instead of
    patching the constant. The minimum and the cap are an `if`/**`else if`**, not a clamp:
    an order whose per-share fee is under $1 pays $1 even when that exceeds 0.5% of its
    value, and the engine never lets the cap pull a fee below the floor. `commission_legacy`
    below is the `min(max(...))` form this file used before S-44, kept callable so any row
    written under it can be reproduced; the two agree except where the fill price is under
    $1.00 or the order is worth under $200, and the champion's book reaches neither.
    """
    q = abs(float(shares))
    value = q * abs(float(price))
    fee = FEE_PER_SHARE * q
    if fee < FEE_MIN:
        fee = FEE_MIN
    elif fee > FEE_MAX_FRAC * value:
        fee = FEE_MAX_FRAC * value
    return abs(fee)


def commission_legacy(shares: float, price: float) -> float:
    """The pre-S-44 form: a clamp, and a 1% cap where the engine caps at 0.5%.

    Verbatim, so that every `daily/*` ledger row written before 2026-09-13 stays
    reproducible. S-44 clause 4 shows it is bit-identical to `commission` on every S-19
    convention, so nothing already recorded on the champion's universe moves.
    """
    value = abs(shares) * price
    return min(max(FEE_MIN, FEE_PER_SHARE * abs(shares)), 0.01 * value)


def tstat(x) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 2 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


# ------------------------------------------------------------------------------- the book

def simulate(frames: dict, params, lag: int, fill: str, start: str, end: str,
             slippage_bps: float = 0.0, financing: dict | None = None,
             unsizable: list | None = None) -> pd.DataFrame:
    """Walk the shipped signal day by day and execute it at `fill` on the fill session.

    `lag` is the number of *extra* sessions of staleness beyond the backtest's own: 0 is
    "the signal reads through the previous close", which is what both the champion and the
    deployed runner do. `fill` is "open" or "close" of the session the orders land in.

    Sizing always uses close[i-1] - the price both implementations actually hold at the
    moment they decide (LEAN's `securities[symbol].price` at the rebalance bar, and the
    runner's `prices` dict built from the last complete yfinance close). Holding that fixed
    is what makes the two conventions produce the same order list from the same state, so
    the only thing that moves between them is the fill.

    S-22 adds one optional argument and changes nothing when it is absent. `financing` is
    `{"rates": {"YYYY-MM-DD": pct}, "spread": pp}` and, when given, accrues interest on the
    settled cash balance at the top of every session for the *calendar* days since the last
    one, exactly as `main.py:accrue_financing` does in LEAN - charged before the day's
    sizing, so it compounds against the book rather than being reported beside it. Default
    `None` leaves the S-19 rows bit-identical.

    D-10 adds a second optional argument of the same shape and with the same promise. When
    `unsizable` is a list, every ranked name this book could not express as a whole-share
    position is appended to it (`sig.unsizable_targets`, plus the session date). It is an
    out-parameter and nothing else: the planning loop below is untouched, so the returned
    book is bit-identical whether it is passed or not.
    """
    # A NEGATIVE lag is a decision window that reaches PAST the fill, and nothing here used
    # to stop one. The only place `lag` is bounded is the `i0` line below, and a negative
    # value makes that bound SMALLER rather than illegal - it loosens the very check that
    # looks like it is guarding. Measured with lag=-2: CAR 1,369%, Sharpe 15.4, MaxDD 1.8%,
    # against the deployed 18.7% / 1.04 / 11.1%. That is not a parameter choice, it is a
    # different universe, and it was reachable by typing a minus sign.
    if lag < 0:
        raise LeakageError(
            f"simulate(lag={lag}): a negative lag is a look-ahead. `lag` counts sessions of "
            f"EXTRA staleness beyond the backtest's own one-session delay, so the smallest "
            f"legal value is 0 - the convention the champion and the deployed runner both "
            f"use. A negative lag lets the decision read prices that have not printed at the "
            f"moment of the fill."
        )
    closes = frames["close"]
    opens = frames["open"]
    tickers = [t for t in sig.traded_universe(params) if t in closes.columns]
    index = closes.index
    i0 = max(index.searchsorted(pd.Timestamp(start)) + 1, lag + params.history_bars)
    i1 = min(index.searchsorted(pd.Timestamp(end), side="right"), len(index))

    equity = START_EQUITY
    cash = START_EQUITY
    positions: dict[str, int] = {}
    equity_curve = [START_EQUITY]
    state: dict = {}
    rows = []

    fin_rates = (financing or {}).get("rates") or {}
    fin_shift = float((financing or {}).get("spread", 0.0))
    fin_first, fin_final = (min(fin_rates), max(fin_rates)) if fin_rates else ("", "")

    for i in range(i0, i1):
        # --- S-22: one day's financing on the settled balance, before the day's sizing
        interest, prev_mark = 0.0, equity      # prev_mark is pre-interest: the charge has
        if fin_rates and i > i0:               # to land inside the day's return, not beside it
            days = (index[i].date() - index[i - 1].date()).days
            stamp = min(max(index[i].date().isoformat(), fin_first), fin_final)
            interest = rates.accrual(cash, fin_rates[stamp], days, fin_shift)
            cash += interest
            equity += interest
            equity_curve[-1] += interest

        # --- decide, on the information the convention allows
        lo = max(0, i - lag - params.history_bars)
        window = closes.iloc[lo:i - lag]                 # closes through i-1-lag
        targets, diag = sig.target_weights(window, equity_curve, params, state)
        state = diag.get("state", {})

        ref = {t: float(closes[t].iloc[i - 1]) for t in tickers
               if pd.notna(closes[t].iloc[i - 1])}
        px_fill_row = (opens if fill == "open" else closes).iloc[i]

        # --- plan, exactly as main.py:submit_targets does
        deltas = {}
        for t in tickers:
            p = ref.get(t, 0.0)
            held = int(positions.get(t, 0))
            target = 0 if p <= 0 else int(targets.get(t, 0.0) * equity / p)
            if abs(target - held) * max(p, 0.01) >= MIN_ORDER_VALUE * equity:
                deltas[t] = target - held

        # --- D-10: read-only, after the plan is fixed, so it cannot reach the order list
        if unsizable is not None:
            held_now = {t: float(positions.get(t, 0)) for t in tickers}
            for hit in sig.unsizable_targets(targets, ref, equity, held_now):
                unsizable.append({"date": index[i], **hit})

        # --- execute at the convention's price
        fees = turnover = 0.0
        for t, d in sorted(deltas.items(), key=lambda kv: kv[1]):     # sells before buys
            p = float(px_fill_row.get(t, np.nan))
            if not np.isfinite(p) or p <= 0:
                continue
            p_eff = p * (1 + np.sign(d) * slippage_bps / 1e4)
            fee = commission(d, p_eff)
            cash -= d * p_eff + fee
            positions[t] = positions.get(t, 0) + d
            fees += fee
            turnover += abs(d) * p_eff

        # --- mark to the close of the fill session
        mark = closes.iloc[i]
        value = cash + sum(n * float(mark[t]) for t, n in positions.items()
                           if t in mark.index and pd.notna(mark[t]))
        rows.append({"date": index[i], "equity": value, "prev": prev_mark,
                     "orders": len(deltas), "fees": fees, "turnover": turnover,
                     "interest": interest, "cash": cash,
                     "held": len([1 for n in positions.values() if n])})
        equity = value
        equity_curve.append(value)

    out = pd.DataFrame(rows)
    out["ret"] = out["equity"] / out["prev"] - 1.0
    return out


def summarize(book: pd.DataFrame, label: str) -> dict:
    ret = book["ret"].to_numpy()
    n = len(ret)
    years = n / 252.0
    curve = np.cumprod(1 + ret)
    car = 100 * (curve[-1] ** (1 / years) - 1) if years > 0 else float("nan")
    dd = 100 * float((1 - curve / np.maximum.accumulate(curve)).max())
    sd = ret.std(ddof=1)
    return {"cell": label, "sessions": n,
            "CAR": car, "Sharpe": (ret.mean() / sd * np.sqrt(252)) if sd else float("nan"),
            "MaxDD": dd, "std": sd * np.sqrt(252),
            "orders": int(book["orders"].sum()), "fees": float(book["fees"].sum()),
            "end_equity": float(book["equity"].iloc[-1])}


def table(rows: list[dict]) -> None:
    hdr = f"{'cell':<34}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}{'orders':>8}{'fees':>11}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['cell']:<34}{r['sessions']:>6}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}"
              f"{r['MaxDD']:>8.3f}{r['std']:>7.3f}{r['orders']:>8,}{r['fees']:>11,.0f}")


def paired(a: pd.DataFrame, b: pd.DataFrame, name_a: str, name_b: str) -> dict:
    """Daily return difference `a - b` in basis points, paired on the date."""
    m = a[["date", "ret"]].merge(b[["date", "ret"]], on="date", suffixes=("_a", "_b"))
    d = 1e4 * (m["ret_a"] - m["ret_b"]).to_numpy()
    return {"pair": f"{name_a} - {name_b}", "days": len(d), "bps_per_day": d.mean(),
            "t": tstat(d)}


# ------------------------------------------------------------------------------ LEAN rows

def lean_rows() -> list[dict]:
    """The S-19 cells already in the ledger, so the two harnesses print side by side."""
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("algorithm") == "s1_momo" and r.get("tag", "").startswith("S-19"):
            s = r.get("stats", {})
            out.append({"tag": r["tag"], "ts": r["ts"], "env": r.get("env", {}),
                        "orders": s.get("Total Orders"),
                        "CAR": s.get("Compounding Annual Return"),
                        "Sharpe": s.get("Sharpe Ratio"), "DD": s.get("Drawdown"),
                        "std": s.get("Annual Standard Deviation"),
                        "fees": s.get("Total Fees")})
    return out


def validate(book: pd.DataFrame, run_dir: str) -> None:
    """Score this book's daily returns against LEAN's own equity curve for the same cell.

    Nothing below the `backtest` row is worth reading unless this passes, because the whole
    claim of the script is that a pandas book can execute the shipped signal the way LEAN
    does and then be asked a question LEAN cannot express.

    Two traps, both found the hard way. (1) LEAN's `Strategy Equity` series carries several
    samples per session - midnight plus intraday marks - and taking the last of each date
    mixes a close with a mid-session value, which drops the correlation against a
    close-marked book from 0.997 to 0.804 for no reason at all. Only the midnight stamps
    (04:00/05:00 UTC, i.e. ET midnight either side of the daylight-saving switch) are used
    here. (2) A midnight point stamped D is the portfolio's value *after* the close of D-1,
    so the series has to be shifted back one session before it is compared to anything.
    """
    path = REPO / run_dir / "S1MomentumRotationAlgorithm.json"
    if not path.exists():
        print(f"  no LEAN result at {path}")
        return
    d = json.loads(path.read_text(encoding="utf-8"))
    vals = d["charts"]["Strategy Equity"]["series"]["Equity"]["values"]
    s = pd.Series([v[4] for v in vals],
                  index=pd.to_datetime([v[0] for v in vals], unit="s"))
    s = s[s.index.hour.isin([4, 5])]
    s.index = s.index.normalize()
    lean = s.groupby(level=0).last().shift(-1).dropna()

    j = pd.DataFrame({"lean": lean, "book": book.set_index("date")["equity"]}).dropna()
    rl = j["lean"].pct_change().dropna()
    rb = j["book"].pct_change().dropna()
    stats = d.get("statistics", {})
    print(f"  matched sessions            {len(j)}")
    print(f"  corr(daily returns)         {rl.corr(rb):.5f}")
    print(f"  annualized std   LEAN {rl.std(ddof=1) * np.sqrt(252):.4f}   book "
          f"{rb.std(ddof=1) * np.sqrt(252):.4f}")
    print(f"  mean annual ret  LEAN {rl.mean() * 252:.4f}   book {rb.mean() * 252:.4f}")
    print(f"  end equity       LEAN {j['lean'].iloc[-1]:,.0f}   book "
          f"{j['book'].iloc[-1]:,.0f}")
    print(f"  tracking sd of the daily difference   {1e4 * (rl - rb).std(ddof=1):.2f} bps")
    print(f"\n  LEAN *reports* Annual Standard Deviation {stats.get('Annual Standard Deviation')} "
          f"and Sharpe {stats.get('Sharpe Ratio')} for this run, against the "
          f"{rl.std(ddof=1) * np.sqrt(252):.3f} its own equity curve carries on trading days:")
    print("  the reported figure is resampled onto calendar days, so it is a LEAN reporting\n"
          "  convention and not a difference between the two books. Compare Sharpe within a\n"
          "  harness, never across the two tables this script prints.")


def record(label: str, book: pd.DataFrame, summary: dict, extra: dict) -> None:
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "daily/s19_clock", "class": "book", "tag": label, "commit": "",
           "run_dir": "", "track": "S-19",
           "params": {"min_order_value": MIN_ORDER_VALUE, "start_equity": START_EQUITY},
           "start": str(pd.Timestamp(book["date"].min()).date()),
           "end": str(pd.Timestamp(book["date"].max()).date()),
           "stats": {"Sessions": str(summary["sessions"]),
                     "Total Orders": str(summary["orders"]),
                     "Compounding Annual Return": f"{summary['CAR']:.3f}%",
                     "Sharpe Ratio": f"{summary['Sharpe']:.3f}",
                     "Drawdown": f"{summary['MaxDD']:.3f}%",
                     "Annual Standard Deviation": f"{summary['std']:.3f}",
                     "Total Fees": f"${summary['fees']:.2f}",
                     "End Equity": f"{summary['end_equity']:.2f}",
                     **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


# ---------------------------------------------------------------------------------- main

#: (label, extra staleness in sessions, where the order fills)
CONVENTIONS = [
    ("backtest / pre-open fix", 0, "open"),
    ("deployed 15:45 runner", 0, "close"),
    ("lag1 (LEAN's bound)", 1, "open"),
    ("lag1 + 15:45 fill", 1, "close"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--slippage-bps", type=float, default=0.0)
    ap.add_argument("--lean", action="store_true", help="print the S-19 LEAN ledger rows")
    ap.add_argument("--validate", metavar="RUN_DIR",
                    help="score the backtest-convention book against this LEAN run's own "
                         "equity curve, e.g. results/s1_momo/20260911T173818Z")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    params = sig.Params()
    tickers = sig.traded_universe(params)
    frames = load_ohlcv(tickers)
    print(f"store: {len(tickers)} tickers, {frames['close'].index[0].date()} .. "
          f"{frames['close'].index[-1].date()}")
    print(f"window {args.start} .. {args.end}   band {MIN_ORDER_VALUE:g} x equity   "
          f"spread {args.slippage_bps:g} bp\n")

    books, rows = {}, []
    for label, lag, fill in CONVENTIONS:
        b = simulate(frames, params, lag, fill, args.start, args.end, args.slippage_bps)
        books[label] = b
        rows.append(summarize(b, label))
    table(rows)

    base = CONVENTIONS[0][0]
    if args.validate:
        print(f"\nvalidation: the '{base}' book against LEAN {args.validate}")
        validate(books[base], args.validate)

    print(f"\npaired daily return difference against '{base}' (bps/day):")
    for label, _lag, _fill in CONVENTIONS[1:]:
        p = paired(books[label], books[base], label, base)
        print(f"  {p['pair']:<52}{p['bps_per_day']:>+8.3f}  t {p['t']:>+6.2f}  "
              f"({p['days']} days)")

    # The point of the whole script, in one line. LEAN can price `lag1` and cannot price
    # `deployed`; this book prices both, so the ratio between them converts the engine's
    # bound into the number the owner is actually being asked about.
    bt, dep, l1 = (summarize(books[c[0]], c[0])["CAR"] for c in CONVENTIONS[:3])
    if bt - l1 != 0:
        share = (bt - dep) / (bt - l1)
        print(f"\nbound calibration (this harness): the deployed clock costs "
              f"{bt - dep:.3f} CAR points against the lag1 bound's {bt - l1:.3f}, "
              f"i.e. {share:.0%} of it.")
        print("  Multiply LEAN's own lag1 gap by that share to price the deployed runner in "
              "the engine's units.")

    # Halves. S-12 was promoted on these two windows and S-18 re-ran them, so a clock cost
    # that lives in only one of them is a different fact from one that lives in both.
    print("\nhalves (CAR%, and the paired difference against the same convention's own half):")
    for lo, hi, name in [(args.start, "2019-12-31", "IS 2012-2019"),
                         ("2020-01-02", args.end, "OOS 2020-2026")]:
        sub = {}
        for label, lag, fill in CONVENTIONS[:3]:
            sub[label] = simulate(frames, params, lag, fill, lo, hi, args.slippage_bps)
        line = f"  {name:<16}"
        for label in sub:
            line += f"{summarize(sub[label], label)['CAR']:>9.3f}"
        p = paired(sub[CONVENTIONS[1][0]], sub[base], "dep", "bt")
        line += f"    deployed - backtest {p['bps_per_day']:>+7.3f} bps/day  t {p['t']:>+6.2f}"
        print(line)
    print(f"  {'':<16}" + "".join(f"{lbl[:9]:>9}" for lbl, _l, _f in CONVENTIONS[:3]))

    if args.lean:
        print("\nLEAN rows tagged S-19 (the same strategy in the engine):")
        for r in lean_rows():
            print(f"  {r['ts']}  {str(r['env']):<46} orders {r['orders']:>6}  "
                  f"CAR {r['CAR']:>8}  Sharpe {r['Sharpe']:>6}  DD {r['DD']:>8}  "
                  f"fees {r['fees']}")
            print(f"      {r['tag']}")

    if not args.no_record:
        for r in rows:
            book = books[r["cell"]]
            record(f"S-19 {r['cell']} (pandas book on the shared signals.py, "
                   f"{args.slippage_bps:g} bp spread)", book, r,
                   {"Turnover Per Day": f"{book['turnover'].mean():.0f}"})
        print(f"\n{len(rows)} rows appended to {LEDGER.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
