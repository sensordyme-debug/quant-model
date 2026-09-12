#!/usr/bin/env python3
"""F-2: what an ES front-month book can and cannot be asked, on the history IBKR retains.

    python scripts/sweep_f2.py --costs
    python scripts/sweep_f2.py --report [--record]

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
`scripts/futures_data.py --probe --depth` settled the data question F-2 has carried since
2026-09-10, and settled it differently from the way the backlog stated it.  **Permission
is not missing**: this paper account fetches ES / MES / NQ / MNQ 1-minute TRADES bars for
the full 23-hour session with zero subscription errors.  What is missing is **retention**.
IBKR refuses an `endDateTime` on a continuous future (error 10339) and caps a 1-minute
continuous request at one month, so CONTFUT cannot be paged; dated quarterlies can be, but
IBKR carries only about four expired quarters (ESU5 answers, ESM5 and older return "no
security definition").  The stitched front-month store is therefore ~15 months.

A-4 measured this repository's own power requirement at **~2,000 sessions**, and A-10 is
the standing lesson about ignoring it: a 260-session IBKR sample kept a strategy that
2,686 Alpaca sessions killed at t = -7.38.  So the rule is pre-registered here before any
number is computed, and it has an unusual second half:

  (1) A mechanism SURVIVES stage 1 only if its pooled gross per round trip exceeds the
      round-trip cost floor, at |t| > 2, with the sign holding in both halves.
  (2) **Nothing in this file is promotable, deployable or a candidate, whatever it
      prints.** The sample is ~15% of what A-4 says is needed to resolve an edge on this
      repository's data.  A survivor is evidence for BUYING HISTORY, not for trading.
  (3) The number that is worth having regardless of (1) is the **cost floor**, because it
      is a property of the instrument rather than of the sample, and every intraday
      refusal this repository has written - L-1 (6.4-8.2 bps a round trip), X-1 (4.70),
      F-1 (0.892 of commission alone) - was a refusal on cost rather than on signal.

So read the cost table first.  It is the part of F-2 that 15 months of data is enough for.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
STORE = REPO / "data" / "futures"
LEDGER = REPO / "research" / "experiments.jsonl"
ET = "America/New_York"

# CME / IBKR contract facts.  Multiplier and tick are CME specifications; the commission is
# IBKR's published Pro rate for US futures - $0.85 execution plus exchange and regulatory
# fees, which for ES is $1.18 CME + $0.02 NFA.  Kept explicit so a reader can substitute
# their own tier rather than trust a single number.
SPECS = {
    "ES": {"multiplier": 50.0, "tick": 0.25, "exec_fee": 0.85, "exch_fee": 1.18,
           "nfa_fee": 0.02},
    "MES": {"multiplier": 5.0, "tick": 0.25, "exec_fee": 0.25, "exch_fee": 0.37,
            "nfa_fee": 0.02},
}


def tstat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


# ------------------------------------------------------------------------------ cost floor


def cost_table(px: float = 6800.0) -> pd.DataFrame:
    """Round-trip cost of one contract, in dollars and in basis points of notional.

    Two spread assumptions, because the difference matters and neither is obviously right:
    `half tick` is what a marketable order pays when it crosses a one-tick book (half the
    spread each way); `full tick` is the pessimistic case where every entry and exit lifts
    the whole spread.  ES is one tick wide essentially all session, so the truth is between
    them and much closer to the first outside the open.
    """
    rows = []
    for sym, s in SPECS.items():
        notional = px * s["multiplier"]
        comm_side = s["exec_fee"] + s["exch_fee"] + s["nfa_fee"]
        comm_rt = 2 * comm_side
        tick_usd = s["tick"] * s["multiplier"]
        for label, spread_rt in (("half tick", tick_usd), ("full tick", 2 * tick_usd)):
            rows.append({
                "sym": sym, "spread": label, "notional": notional,
                "commission_rt_$": comm_rt, "spread_rt_$": spread_rt,
                "total_rt_$": comm_rt + spread_rt,
                "commission_bps": 1e4 * comm_rt / notional,
                "spread_bps": 1e4 * spread_rt / notional,
                "total_bps": 1e4 * (comm_rt + spread_rt) / notional,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------- panel


def load(sym: str) -> pd.DataFrame:
    path = STORE / f"{sym}.parquet"
    if not path.exists():
        raise SystemExit(f"no store at {path}; run scripts/futures_data.py --fetch")
    df = pd.read_parquet(path)
    df["t"] = pd.to_datetime(df["t"], utc=True).dt.tz_convert(ET)
    return df.sort_values("t").reset_index(drop=True)


def _at(day_bars: pd.DataFrame, hh: int, mm: int, how: str = "open") -> float:
    """First bar at or after hh:mm on this session; NaN if the session has no such bar."""
    mins = day_bars["t"].dt.hour * 60 + day_bars["t"].dt.minute
    sel = day_bars[mins >= hh * 60 + mm]
    if sel.empty:
        return float("nan")
    return float(sel.iloc[0][{"open": "o", "close": "c"}[how]])


def sessions(df: pd.DataFrame) -> pd.DataFrame:
    """One row per cash session, carrying the prices both mechanisms need.

    The futures day runs 18:00 ET to 17:00 ET, so the overnight window that precedes cash
    session D belongs to two calendar dates.  Everything here is anchored on the CASH date
    and every price is read at or after its stated clock time, never before it, so no row
    can see a price that had not printed when the decision it feeds would have been made.
    """
    df = df.copy()
    df["date"] = df["t"].dt.date
    df["mins"] = df["t"].dt.hour * 60 + df["t"].dt.minute
    # Assign every bar to the cash session it precedes or belongs to: bars from 18:00 on
    # belong to the NEXT calendar session.
    nxt = df["mins"] >= 18 * 60
    df["cash_date"] = df["date"]
    df.loc[nxt, "cash_date"] = df.loc[nxt, "date"] + pd.Timedelta(days=1)

    rows = []
    for cash_date, g in df.groupby("cash_date", sort=True):
        g = g.sort_values("t")
        prior = g[g["mins"] >= 18 * 60]           # last evening's Globex
        early = g[(g["mins"] < 9 * 60 + 30) & (g["mins"] >= 0)]
        cash = g[(g["mins"] >= 9 * 60 + 30) & (g["mins"] <= 16 * 60)]
        if prior.empty or cash.empty or len(cash) < 200:
            continue                              # holiday, half day, or a roll gap
        rows.append({
            "day": cash_date,
            "globex_open": float(prior.iloc[0]["o"]),
            "px_0915": _at(early, 9, 15) if not early.empty else float("nan"),
            "px_0930": float(cash.iloc[0]["o"]),
            "px_1000": _at(cash, 10, 0),
            "px_1100": _at(cash, 11, 0),
            "px_1530": _at(cash, 15, 30),
            "px_1600": float(cash.iloc[-1]["c"]),
            "cash_bars": len(cash),
            "contract": g.iloc[-1]["contract"],
        })
    s = pd.DataFrame(rows).dropna(subset=["px_0915", "px_1000", "px_1530"])
    return s.reset_index(drop=True)


# ------------------------------------------------------------------------------ mechanisms


def event_study(s: pd.DataFrame) -> pd.DataFrame:
    """The two effects F-2 was opened on, measured gross, with nothing fitted.

    M1 'overnight momentum into the cash open': the sign of the Globex move from the
    18:00 reopen to 09:15 predicts the direction of the cash session that follows it.
    M2 'the 15:30-16:00 flow': the sign of the cash day so far predicts the last half hour.

    Both are sign trades - no threshold, no ranking, no sizing - because a threshold is a
    fitted parameter and this sample cannot afford one.
    """
    out = []
    s = s.copy()
    s["overnight"] = 1e4 * (s["px_0915"] / s["globex_open"] - 1.0)
    s["day_to_1530"] = 1e4 * (s["px_1530"] / s["px_0930"] - 1.0)

    for label, sig, entry, exits in [
        ("M1 overnight -> open", "overnight", "px_0930",
         [("10:00", "px_1000"), ("11:00", "px_1100"), ("16:00", "px_1600")]),
        ("M2 day -> last 30m", "day_to_1530", "px_1530", [("16:00", "px_1600")]),
    ]:
        for hlabel, col in exits:
            leg = 1e4 * (s[col] / s[entry] - 1.0)
            direction = np.sign(s[sig])
            pnl = direction * leg
            pnl = pnl[np.isfinite(pnl)]
            half = len(s) // 2
            a = (direction * leg).iloc[:half].dropna()
            b = (direction * leg).iloc[half:].dropna()
            out.append({
                "mechanism": label, "exit": hlabel, "n": len(pnl),
                "gross_bps": pnl.mean(), "t": tstat(pnl.to_numpy()),
                "sd_bps": pnl.std(ddof=1),
                "hit": 100 * (pnl > 0).mean(),
                "h1_bps": a.mean(), "h1_t": tstat(a.to_numpy()),
                "h2_bps": b.mean(), "h2_t": tstat(b.to_numpy()),
                "signal_sd": s[sig].std(ddof=1),
            })
    return pd.DataFrame(out)


def book(s: pd.DataFrame, mech: str, floor_bps: float) -> pd.DataFrame:
    """One-contract-equivalent daily book for a mechanism, net of the cost floor."""
    s = s.copy()
    if mech == "M1":
        sig = np.sign(1e4 * (s["px_0915"] / s["globex_open"] - 1.0))
        leg = 1e4 * (s["px_1600"] / s["px_0930"] - 1.0)
    elif mech == "M1b":
        # The only horizon at which M1 is positive at all. Still not significant, and the
        # horizon was chosen after reading stage 1, so it is in sample by construction.
        sig = np.sign(1e4 * (s["px_0915"] / s["globex_open"] - 1.0))
        leg = 1e4 * (s["px_1000"] / s["px_0930"] - 1.0)
    elif mech == "M2R":
        # POST HOC. Stage 1 measured M2's momentum form at t = -2.56, so its reversal is
        # positive by arithmetic rather than by evidence: the sign was chosen after seeing
        # the table. Recorded so the number exists with that label attached, exactly as
        # A-12 recorded its own falsification control, and NOT as a candidate.
        sig = -np.sign(1e4 * (s["px_1530"] / s["px_0930"] - 1.0))
        leg = 1e4 * (s["px_1600"] / s["px_1530"] - 1.0)
    else:
        sig = np.sign(1e4 * (s["px_1530"] / s["px_0930"] - 1.0))
        leg = 1e4 * (s["px_1600"] / s["px_1530"] - 1.0)
    gross = sig * leg
    return pd.DataFrame({"day": s["day"], "gross_bps": gross,
                         "net_bps": gross - floor_bps}).dropna()


# ------------------------------------------------------------------------------------ io


def record(tag: str, bk: pd.DataFrame, extra: dict) -> None:
    net = bk["net_bps"].to_numpy()
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "futures/f2_es", "class": "book", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-2",
           "start": str(bk["day"].min()), "end": str(bk["day"].max()),
           "stats": {"Sessions": str(len(bk)),
                     "Gross Bps Per Round Trip": f"{bk['gross_bps'].mean():.3f}",
                     "Net Bps Per Round Trip": f"{net.mean():.3f}",
                     "t": f"{tstat(net):.2f}",
                     "Win Rate": f"{100 * (net > 0).mean():.0f}%",
                     "Worst Day Bps": f"{net.min():.1f}",
                     **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--costs", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--symbol", default="ES")
    args = ap.parse_args()

    pd.set_option("display.width", 150)
    pd.set_option("display.max_columns", 40)

    ct = cost_table()
    if args.costs or args.report:
        print("=== Stage 0: the round-trip cost floor (the part 15 months IS enough for) ===")
        print(ct.round(3).to_string(index=False))
        print()
        print("  For comparison, this repository's own measured equity round trips:")
        print("    L-1 leveraged ETFs   6.40 - 8.20 bps      X-1 megacap legs   4.70 bps")
        print("    F-1 intraday book    0.892 bps of commission alone, at zero spread")
        print("    A-5 part 2 realized  +2.22 bps of slippage per intraday equity fill")
        print()
    if not args.report:
        return 0

    df = load(args.symbol)
    s = sessions(df)
    days = len(s)
    print(f"=== Store: {len(df):,} one-minute bars, {days} cash sessions "
          f"{s['day'].min()} .. {s['day'].max()} ===")
    print(f"    contracts stitched: {sorted(df['contract'].unique())}")
    print(f"    A-4's power requirement is ~2000 sessions; this is {100*days/2000:.0f}% of it.")
    print()

    es = event_study(s)
    print("=== Stage 1: the two effects, gross, nothing fitted ===")
    print(es.round(3).to_string(index=False))
    print()

    floor = float(ct[(ct.sym == "ES") & (ct.spread == "half tick")]["total_bps"].iloc[0])
    print(f"=== Stage 2: as a book, charged the {floor:.3f} bps half-tick floor ===")
    LABEL = {"M1": "overnight -> full cash session (pre-registered)",
             "M1b": "overnight -> 10:00 (POST HOC horizon)",
             "M2": "day momentum -> last 30m (pre-registered)",
             "M2R": "day REVERSAL -> last 30m (POST HOC sign)"}
    for mech in ("M1", "M1b", "M2", "M2R"):
        bk = book(s, mech, floor)
        net = bk["net_bps"].to_numpy()
        print(f"  {mech:4s} {LABEL[mech]:42s} gross {bk['gross_bps'].mean():+.3f}  "
              f"net {net.mean():+.3f} bps  t {tstat(net):+.2f}  "
              f"win {100*(net>0).mean():.0f}%  worst {net.min():.1f}")
        if args.record:
            record(f"F-2 {mech} ({LABEL[mech]}) ES front-month stitch 2025-06..2026-09, "
                   f"half-tick floor {floor:.3f} bps round trip - NOT PROMOTABLE, "
                   f"{len(bk)} sessions against A-4's ~2000", bk,
                   {"Gross Floor Bps": f"{floor:.3f}", "Symbol": args.symbol,
                    "Gross Bps": f"{bk['gross_bps'].mean():.3f}"})
    print()
    print("  Pre-registered (2): nothing here is promotable at 15 months, whatever it says.")
    print("  Session gross sd is the mandate-relevant number: one ES contract carries")
    print(f"  {s['px_0930'].mean()*SPECS['ES']['multiplier']:,.0f} of notional and the cash")
    print("  session's own sd is 0.62% of it, before any leverage decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
