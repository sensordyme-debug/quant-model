#!/usr/bin/env python
"""S-2 stage 1: does an opening-range breakout on the index ETFs have gross edge?

Backlog S-2 asks for an opening-range breakout as a *second sleeve* on SPY/QQQ/IWM (and TQQQ
as the leveraged read), judged in LEAN with the 16:00 auction modelled. This script is the
cheap stage that has to pass first, for the reason L-1, X-1 and O-2 all recorded: measure the
mechanism on the whole history with nothing fitted, and only build the expensive harness if
gross clears the cost floor. The A-track already measured an ORB on sixteen single names at
-$331/day, so the question here is narrow and specific - the index ETFs are a different
universe (one order of magnitude more liquid, a third of the per-share commission per dollar
traded, and no single-name event risk), and they are the only intraday instruments the daily
sleeve could ever also hold.

Method, fixed before the runs:
  * Opening range = the first `orb_min` minutes of the session (bars stamped at their START,
    so mod 0 is 09:30). Breakout = a bar whose CLOSE is beyond the range; the fill is the NEXT
    bar's open, which is the same causal convention scripts/intraday_backtest.py uses.
  * One trip per session per symbol, whichever side triggers first, entries allowed until
    `entry_before` minutes after the open.
  * Stop = the opposite end of the range ('opp') or its midpoint ('mid', what the deployed ORB
    module uses); detected on a bar close, exited at the next bar's open.
  * Otherwise the trip is closed at the last bar of the session. That is stage 1's known
    optimism - D-2 measured the daily close diverging from the last minute bar by up to ~1% on
    violent days - and it is exactly what stage 2 in LEAN would have to model with a
    market-on-close order. Stage 1 cannot promote anything; it can only refuse.
  * Costs are the shipped model (intraday_common): SLIPPAGE_BPS per leg plus the real IBKR
    per-share commission and the sell-side regulatory fees, on a fixed `--notional` per trip.
  * `fade` is the falsification control. L-1 and X-1 both found books that lost in BOTH signs,
    which is how you tell "no edge" from "wrong sign".

Decision rule, fixed before the runs: a cell is worth a LEAN build only if the per-session net
$ series is positive at t > 2 in at least two of the three a-priori regimes (2016-2019 /
2020-2023 / 2024-2026), and only if its fade control does not also pass.

Usage:
    python scripts/sweep_s2.py                       # the pre-registered grid
    python scripts/sweep_s2.py --symbols SPY --orb 15 --detail
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intraday_common as ic  # noqa: E402

#: The index ETFs backlog S-2 names. TQQQ is carried as the leveraged read and reported
#: separately: it is the daily champion's own instrument, so it could only ever be traded by
#: this sleeve, never by both.
INDEX_ETFS = ["SPY", "QQQ", "IWM"]
LEVERAGED = ["TQQQ"]

#: A-10's three a-priori regimes, used unchanged so this result is comparable with the A-track.
REGIMES = [("2016-2019", "2016-01-01", "2019-12-31"),
           ("2020-2023", "2020-01-01", "2023-12-31"),
           ("2024-2026", "2024-01-01", "2026-12-31")]

SESSION_MINUTES = 390


def panel(symbol: str) -> dict:
    """Session x minute-of-day panels of o/h/l/c for one symbol, NaN where a bar is missing."""
    df = ic.load_bars(symbol)
    if df.empty:
        return {}
    mod = (df.index.hour - 9) * 60 + df.index.minute - 30
    days = pd.Index(sorted(set(df.index.date)))
    cols = pd.RangeIndex(SESSION_MINUTES)
    out = {}
    for f in ("o", "h", "l", "c"):
        piv = df[f].groupby([df.index.date, mod]).last().unstack()
        out[f] = piv.reindex(index=days, columns=cols).to_numpy(dtype=float)
    out["days"] = days
    return out


def _first_true(mask: np.ndarray) -> np.ndarray:
    """Column index of the first True per row, or -1 if the row is all False."""
    any_ = mask.any(axis=1)
    idx = mask.argmax(axis=1)
    return np.where(any_, idx, -1)


def trips(pan: dict, orb_min: int, stop_mode: str, entry_before: int,
          fade: bool) -> pd.DataFrame:
    """One row per session that traded: entry/exit price, direction, gross bps."""
    o, h, l, c = pan["o"], pan["h"], pan["l"], pan["c"]
    n = o.shape[0]
    valid = ~np.isnan(c)
    last_idx = SESSION_MINUTES - 1 - np.argmax(valid[:, ::-1], axis=1)
    enough = valid[:, :orb_min].sum(axis=1) >= max(2, orb_min // 2)

    with np.errstate(invalid="ignore"):
        or_hi = np.nanmax(h[:, :orb_min], axis=1)
        or_lo = np.nanmin(l[:, :orb_min], axis=1)

    win = np.zeros(SESSION_MINUTES, dtype=bool)
    win[orb_min:entry_before] = True
    up = (c > or_hi[:, None]) & win & valid
    dn = (c < or_lo[:, None]) & win & valid
    f_up, f_dn = _first_true(up), _first_true(dn)

    # whichever side breaks first; -1 on both sides means no trade that session
    has_up, has_dn = f_up >= 0, f_dn >= 0
    sig_idx = np.where(has_up & has_dn, np.minimum(f_up, f_dn),
                       np.where(has_up, f_up, np.where(has_dn, f_dn, -1)))
    direction = np.where(sig_idx < 0, 0, np.where(sig_idx == f_up, 1, -1)).astype(float)
    if fade:
        direction = -direction

    entry_idx = sig_idx + 1                      # fill at the NEXT bar's open
    traded = (sig_idx >= 0) & enough & (entry_idx < last_idx)
    rows = np.flatnonzero(traded)
    if rows.size == 0:
        return pd.DataFrame()

    ei = entry_idx[rows]
    d = direction[rows]
    entry_px = o[rows, ei]
    ok = np.isfinite(entry_px) & (entry_px > 0)
    rows, ei, d, entry_px = rows[ok], ei[ok], d[ok], entry_px[ok]
    if rows.size == 0:
        return pd.DataFrame()

    # The stop is a RISK UNIT measured from the fill, not an absolute level. The deployed ORB
    # module stops at the absolute range midpoint, which is the same thing for a breakout
    # (the midpoint sits ~half a range below a long's fill) but is degenerate for the fade
    # control: a faded short entered above the range is already through an absolute midpoint
    # stop, so it exits on its own entry bar 99.8% of the time and the control measures
    # nothing. Anchoring to the fill makes both signs carry the same risk.
    rng = or_hi[rows] - or_lo[rows]
    stop_dist = rng if stop_mode == "opp" else rng / 2.0
    stop = entry_px - d * stop_dist

    cols = np.arange(SESSION_MINUTES)[None, :]
    after = cols > ei[:, None]
    cc = c[rows]
    breach = np.where(d[:, None] > 0, cc <= stop[:, None], cc >= stop[:, None])
    hit = breach & after & ~np.isnan(cc)
    s_idx = _first_true(hit)
    li = last_idx[rows]
    stopped = (s_idx >= 0) & (s_idx + 1 <= li)
    exit_idx = np.where(stopped, s_idx + 1, li)
    exit_px = np.where(stopped, o[rows, exit_idx], c[rows, li])
    # a stop on the very last bar has no next open: close it at that bar's close instead
    bad = ~np.isfinite(exit_px)
    exit_px = np.where(bad, c[rows, li], exit_px)

    gross_bps = d * (exit_px / entry_px - 1.0) * 1e4
    return pd.DataFrame({
        "day": pd.Index(pan["days"])[rows],
        "dir": d, "entry_px": entry_px, "exit_px": exit_px,
        "stopped": stopped, "hold": exit_idx - ei, "gross_bps": gross_bps,
    })


def cost_bps(sym: str, t: pd.DataFrame, notional: float) -> np.ndarray:
    """Round-trip cost in bps of notional under the shipped model, per trip."""
    out = np.empty(len(t))
    for i, (day, ep, xp) in enumerate(zip(t["day"], t["entry_px"], t["exit_px"])):
        sc = ic.share_scale(sym, day)
        sh = np.floor(notional / ep)
        c_in = ic.commission(sh, ep, sc)
        c_out = ic.commission(-sh, xp, sc)
        out[i] = 2 * ic.SLIPPAGE_BPS + (c_in + c_out) / notional * 1e4
    return out


def build(symbols, orb_min, stop_mode, entry_before, fade, notional, panels) -> pd.DataFrame:
    """Per-session net P&L in dollars, summed over symbols (money-weighted by construction)."""
    parts = []
    for s in symbols:
        t = trips(panels[s], orb_min, stop_mode, entry_before, fade)
        if t.empty:
            continue
        t["sym"] = s
        t["cost_bps"] = cost_bps(s, t, notional)
        t["net_bps"] = t["gross_bps"] - t["cost_bps"]
        t["gross_$"] = t["gross_bps"] / 1e4 * notional
        t["net_$"] = t["net_bps"] / 1e4 * notional
        parts.append(t)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def session_series(tr: pd.DataFrame, days: pd.Index) -> pd.DataFrame:
    """Every session in the store gets a row, including the ones with no trade (P&L 0)."""
    g = tr.groupby("day")[["gross_$", "net_$"]].sum()
    n = tr.groupby("day").size().rename("trips")
    out = pd.concat([g, n], axis=1).reindex(days).fillna(0.0)
    out.index = pd.to_datetime(out.index)
    return out


def tstat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / np.sqrt(len(x)))) if len(x) > 1 and sd > 0 else 0.0


def report_cell(name: str, ser: pd.DataFrame, tr: pd.DataFrame) -> dict:
    row = {"cell": name, "trips": int(tr.shape[0]),
           "trips/day": tr.shape[0] / max(len(ser), 1),
           "gross bps/trip": float(tr["gross_bps"].mean()),
           "cost bps/trip": float(tr["cost_bps"].mean()),
           "net bps/trip": float(tr["net_bps"].mean()),
           "hold": float(tr["hold"].mean()), "stop%": float(tr["stopped"].mean() * 100)}
    passes = 0
    for label, a, b in REGIMES:
        s = ser[(ser.index >= a) & (ser.index <= b)]
        if s.empty:
            continue
        row[f"$/day {label}"] = float(s["net_$"].mean())
        t = tstat(s["net_$"].to_numpy())
        row[f"t {label}"] = t
        if s["net_$"].mean() > 0 and t > 2:
            passes += 1
    row["$/day all"] = float(ser["net_$"].mean())
    row["t all"] = tstat(ser["net_$"].to_numpy())
    row["gross $/day"] = float(ser["gross_$"].mean())
    row["regimes"] = passes
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="*", default=None, help="default: the index ETFs")
    ap.add_argument("--orb", nargs="*", type=int, default=[5, 15, 30, 60])
    ap.add_argument("--stop", nargs="*", default=["opp", "mid"])
    ap.add_argument("--entry-before", nargs="*", type=int, default=[120, 390])
    ap.add_argument("--notional", type=float, default=250_000.0,
                    help="dollars per trip; a $1M book running up to 4 names at ~1x gross")
    ap.add_argument("--detail", action="store_true", help="also print the per-symbol breakdown")
    ap.add_argument("--csv", default="", help="write the cell table here")
    args = ap.parse_args()

    symbols = args.symbols or INDEX_ETFS
    print(f"store   {ic.DATA_DIR}")
    panels = {}
    for s in symbols:
        p = panel(s)
        if not p:
            sys.exit(f"no bars for {s} in {ic.DATA_DIR}")
        panels[s] = p
        print(f"  {s:<5} {len(p['days'])} sessions  {p['days'][0]} .. {p['days'][-1]}")
    days = pd.Index(sorted(set().union(*[set(p["days"]) for p in panels.values()])))
    print(f"universe {symbols}   {len(days)} sessions   ${args.notional:,.0f}/trip   "
          f"slippage {ic.SLIPPAGE_BPS} bps/leg\n")

    rows, detail = [], []
    for orb_min, stop_mode, eb, fade in itertools.product(
            args.orb, args.stop, args.entry_before, [False, True]):
        name = (f"orb{orb_min} {stop_mode} e{eb} "
                f"{'fade' if fade else 'brk'}")
        tr = build(symbols, orb_min, stop_mode, eb, fade, args.notional, panels)
        if tr.empty:
            continue
        ser = session_series(tr, days)
        rows.append(report_cell(name, ser, tr))
        if args.detail:
            for s in symbols:
                sub = tr[tr["sym"] == s]
                if not sub.empty:
                    detail.append(report_cell(f"{name} [{s}]",
                                              session_series(sub, days), sub))

    tab = pd.DataFrame(rows).set_index("cell")
    pd.set_option("display.width", 220, "display.max_columns", 40)
    gross_cols = ["trips/day", "gross bps/trip", "cost bps/trip", "net bps/trip", "hold", "stop%"]
    print("=== stage 1: the mechanism, per round trip ===")
    print(tab[gross_cols].round(2).to_string())
    money = [c for c in tab.columns if c.startswith(("$/day", "t ", "gross $"))] + ["regimes"]
    print("\n=== stage 1: what a book earns, per session (the decision statistic) ===")
    print(tab[money].round(2).to_string())

    if args.detail and detail:
        print("\n=== per symbol ===")
        d = pd.DataFrame(detail).set_index("cell")
        print(d[gross_cols + ["$/day all", "t all"]].round(2).to_string())

    # The symmetry decomposition, which is what actually decides this. A stop plus a
    # hold-to-close exit is convex in BOTH directions, so a breakout and its own fade can each
    # show positive gross without any directional edge existing - L-1 and X-1 both had to
    # separate these. The part of gross that a direction-picking signal owns is
    # (breakout - fade)/2; the part both signs share is the stop's convexity and is free to
    # anyone, including a coin flip.
    sym_rows = []
    for name in [c for c in tab.index if c.endswith("brk")]:
        f = name[:-3] + "fade"
        if f not in tab.index:
            continue
        b, fa = tab.loc[name, "gross bps/trip"], tab.loc[f, "gross bps/trip"]
        sym_rows.append({"cell": name[:-4], "gross brk": b, "gross fade": fa,
                         "directional edge": (b - fa) / 2, "stop convexity": (b + fa) / 2,
                         "cost/trip": tab.loc[name, "cost bps/trip"],
                         "edge/cost": (b - fa) / 2 / tab.loc[name, "cost bps/trip"]})
    if sym_rows:
        sd = pd.DataFrame(sym_rows).set_index("cell")
        print("\n=== stage 1: where the gross comes from (bps per round trip) ===")
        print(sd.round(2).to_string())
        print(f"largest directional edge anywhere: "
              f"{sd['directional edge'].max():+.2f} bps against a "
              f"{sd['cost/trip'].min():.2f} bps round trip "
              f"({sd['edge/cost'].max():.2f}x)")

    brk = tab[[not c.endswith("fade") for c in tab.index]]
    winners = brk[(brk["regimes"] >= 2)]
    print(f"\ncells passing the pre-registered rule (>0 at t>2 in 2 of 3 regimes): "
          f"{len(winners)} of {len(brk)}")
    if len(winners):
        print(winners[money].round(2).to_string())
    best = brk["net bps/trip"].idxmax()
    print(f"best breakout cell on net bps/trip: {best}  "
          f"({brk.loc[best, 'net bps/trip']:+.2f} bps, "
          f"${brk.loc[best, '$/day all']:+,.0f}/day, t {brk.loc[best, 't all']:+.2f})")
    if args.csv:
        tab.to_csv(args.csv)
        print(f"wrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
