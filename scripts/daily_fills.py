#!/usr/bin/env python
"""S-17: fill quality on the *daily* sleeve - the counterpart of scripts/slippage_report.py.

`slippage_report.py` measures the intraday sleeve's fills against the bar its decision was
made on. The daily champion has been placing real paper orders since 2026-09-09 and nothing
measured them, so two separate things were unpriced:

1. **Execution cost.** `scripts/paper_trade.py` sends MKT orders at 15:45 ET, so its intended
   fill reference is the session's own close. The gap between the fill and that close is the
   only part of the divergence the runner can control, and it is the number that belongs
   beside the 0 bps of spread LEAN charges (see `S1_SLIPPAGE_BPS`).

2. **The fill-timing convention**, which is much larger and is not slippage at all. The
   backtest decides on the close of day D and fills at the **open of D+1**. The runner reads
   the last *complete* yfinance daily bar at 15:45 ET - which is **D-1's close** - and fills
   at **D's close**. Both act on the same signal date; they fill a full session apart. This
   script reports the difference per fill so the size of the convention gap is on the record,
   but it cannot *price* it: the difference has the standard deviation of a whole session's
   move, so six fills say nothing. `S1_SIGNAL_LAG` in the algorithm is the instrument for
   that, over fourteen years.

    python scripts/daily_fills.py            # every session with fills
    python scripts/daily_fills.py --json     # machine-readable

Prices come from yfinance (`auto_adjust=True`), the same source the runner's signal uses, so
the reference and the decision agree by construction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
LOGS = REPO / "live" / "log"


def load_sessions() -> dict[str, list[dict]]:
    """date -> [{sym, action, qty, ref_price, fill_price}], live daily-runner logs only."""
    out: dict[str, list[dict]] = {}
    for path in sorted(LOGS.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].jsonl")):
        orders: dict[str, dict] = {}
        fills: dict[str, dict] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("event") == "order":
                orders[e["symbol"]] = e
            elif e.get("event") == "fill" and e.get("status") == "Filled":
                fills[e["symbol"]] = e
        rows = []
        for sym, o in orders.items():
            f = fills.get(sym)
            if not f or not f.get("avg_price"):
                continue
            rows.append({"sym": sym, "action": o["action"], "qty": float(f["filled"]),
                         "ref_price": float(o["ref_price"]), "fill": float(f["avg_price"]),
                         "type": str(o.get("type", "MKT"))})
        if rows:
            out[path.stem] = rows
    return out


def bars(symbols, start, end) -> pd.DataFrame:
    import yfinance as yf
    pad_start = (pd.Timestamp(start) - pd.Timedelta(days=14)).date().isoformat()
    pad_end = (pd.Timestamp(end) + pd.Timedelta(days=5)).date().isoformat()
    d = yf.download(sorted(symbols), start=pad_start, end=pad_end,
                    auto_adjust=True, progress=False, group_by="column")
    return d


def signed(action: str) -> int:
    return 1 if action.upper() == "BUY" else -1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sessions = load_sessions()
    if not sessions:
        print("no daily-runner session has filled an order yet")
        return 0

    syms = sorted({r["sym"] for rows in sessions.values() for r in rows})
    data = bars(syms, min(sessions), max(sessions))
    closes, opens = data["Close"], data["Open"]

    records = []
    for day, rows in sessions.items():
        ts = pd.Timestamp(day)
        idx = closes.index
        if ts not in idx:
            print(f"=== {day}: not a session in the price data, skipped")
            continue
        i = idx.get_loc(ts)
        for r in rows:
            sym, sgn = r["sym"], signed(r["action"])
            close_d = float(closes[sym].iloc[i])          # the runner's intended reference
            open_d = float(opens[sym].iloc[i])            # what the backtest fills at
            prev_close = float(closes[sym].iloc[i - 1])   # the close the signal read
            notional = abs(r["qty"]) * r["fill"]
            # S-23: the price the order aimed at depends on the order type. A 15:45 MKT or a
            # MOC order aims at this session's close; a pre-open MOO order aims at this
            # session's OPEN, which is also what the backtest fills at - so for MOO the
            # execution and convention columns collapse onto each other, and that collapse
            # is exactly what moving the task is supposed to buy.
            otype = r.get("type", "MKT")
            aim = open_d if otype == "MOO" else close_d
            records.append({
                "date": day, "sym": sym, "action": r["action"], "qty": r["qty"],
                "type": otype,
                "notional": notional, "fill": r["fill"],
                "signal_close": prev_close, "ref_price": r["ref_price"],
                "bt_fill": open_d, "session_close": close_d, "aim": aim,
                # Positive = the fill was worse for the book than the reference.
                "exec_bps": sgn * (r["fill"] / aim - 1) * 1e4,
                "conv_bps": sgn * (r["fill"] / open_d - 1) * 1e4,
            })

    df = pd.DataFrame(records)
    # The runner's ref_price should be the close of the session *before* the one it trades in:
    # that is the yfinance bar that is complete at 15:45 ET. Assert it rather than assume it.
    stale = (df["ref_price"] - df["signal_close"]).abs() / df["signal_close"]
    df["ref_is_prev_close"] = stale < 5e-4

    if args.json:
        print(df.to_json(orient="records", indent=2))
        return 0

    for day, g in df.groupby("date"):
        print(f"=== {day} ===")
        print(g[["sym", "action", "qty", "fill", "session_close", "bt_fill",
                 "exec_bps", "conv_bps"]].to_string(index=False,
                                                    float_format=lambda x: f"{x:,.2f}"))
        w = g["notional"]
        print(f"  notional ${w.sum():,.0f}   "
              f"exec vs the close it aimed at {(g['exec_bps'] * w).sum() / w.sum():+.1f} bps   "
              f"convention vs the backtest's open "
              f"{(g['conv_bps'] * w).sum() / w.sum():+.1f} bps")

    w = df["notional"]
    n = len(df)
    ex = (df["exec_bps"] * w).sum() / w.sum()
    cv = (df["conv_bps"] * w).sum() / w.sum()
    print(f"\n=== POOLED over {df['date'].nunique()} session(s), {n} fills, "
          f"${w.sum():,.0f} traded ===")
    print(f"  execution vs the auction the runner aimed at       {ex:+.1f} bps "
          f"(per-fill sd {df['exec_bps'].std():.1f}, se {df['exec_bps'].std() / n ** 0.5:.1f})")
    if df["type"].nunique() > 1:
        print("  by order type (S-23: the breakeven in BLOCKERS.md is an OPEN-minus-CLOSE "
              "difference,\n  so the two rows below are what settles it):")
        for ot, g in df.groupby("type"):
            wg, ng = g["notional"], len(g)
            print(f"    {ot:<5}{ng:>4} fills  ${wg.sum():>12,.0f}  "
                  f"{(g['exec_bps'] * wg).sum() / wg.sum():+7.2f} bps  "
                  f"se {g['exec_bps'].std() / ng ** 0.5:.2f}")
    print(f"  LEAN charges                                        0.0 bps of spread "
          f"(NullSlippageModel) -> price it with S1_SLIPPAGE_BPS")
    print(f"  convention: fill vs the backtest's D+1 open        {cv:+.1f} bps "
          f"(per-fill sd {df['conv_bps'].std():.1f}, se {df['conv_bps'].std() / n ** 0.5:.1f})")
    print(f"  the runner's ref_price was the previous close in "
          f"{int(df['ref_is_prev_close'].sum())} of {n} fills")
    print("\n  Read the two numbers differently. The first is execution cost and is small "
          "enough that\n  a few dozen fills will settle it. The second is a whole session of "
          "price movement, so its\n  per-fill dispersion is ~100x the first - it is priced "
          "over fourteen years by S1_SIGNAL_LAG,\n  not here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
