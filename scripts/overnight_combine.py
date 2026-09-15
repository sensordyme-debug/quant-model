"""Section 6: put the overnight finding through the actual Combine, with real intraday paths.

WHY A SIMULATION AND NOT A SHARPE RATIO
---------------------------------------
Everything up to here has been measured in percent per session and annualised Sharpe. Those
are the right units for asking whether an effect exists and the wrong units for asking
whether it passes a Combine, because a Combine is not a Sharpe test. It is a barrier problem:
reach +$3,000 before a $2,000 trailing drawdown is touched, where the drawdown trails the
intraday high-water mark and is tested on unrealised P&L, tick by tick.

Those two questions can disagree completely. A strategy with a superb Sharpe and a fat left
tail fails a Combine most of the time, and the failure happens on the intraday path rather
than on the daily close. So this module hands the repository's own `TopstepTwin` real
minute-by-minute equity paths built from the actual bars, with `strict_path=True` so that a
session without a path is refused rather than silently scored as safe.

WHAT IS BEING PUT THROUGH IT
----------------------------
Three constructions, all long-only, all at a range of sizes:

  overnight   long from the 18:00 ET open, flat at 09:30 ET. This is the beta trade. It is
              permitted - Topstep's trading day runs 17:00 CT to 15:10 CT, so the overnight
              session is inside it - and the question is whether it survives the barrier.
  rth         long from 09:30 ET, flat at 16:00 ET. The buy-and-hold null for the day session.
  vol_gated   the same RTH trade, taken only when the overnight session predicts a QUIET day.
              This is the one construction that uses the surviving finding, and it is here to
              test whether a range forecast that cannot pick direction can still help by
              picking WHEN to take the beta.

THE SIZING SWEEP IS THE POINT
------------------------------
A directionless positive drift can always be made to hit $3,000 by trading it bigger, and can
always be made safe by trading it smaller, and the two cannot usually be satisfied at once.
Sweeping size exposes that tradeoff instead of quietly picking the contract count that makes
the result look best - which is why the sweep is reported in full, including the sizes that
fail.

BLOCK BOOTSTRAP, NOT IID RESAMPLING
------------------------------------
There are only ~312 sessions per instrument, which is one path, and one path tells you
nothing about a pass RATE. Paths are therefore resampled in contiguous blocks of 20 sessions,
which preserves the volatility clustering that the whole barrier problem turns on. Resampling
single sessions independently would destroy exactly the clustering that kills accounts, and
would produce a pass rate that is optimistic for a reason that is easy to miss.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))

from quant_brain.markets.futures_cme import topstep as ts          # noqa: E402
from quant_brain.markets.futures_cme.twin import TopstepTwin, TwinDay  # noqa: E402

POINT_VALUE = {"ES": 50.0, "NQ": 20.0, "MES": 5.0, "MNQ": 2.0}
#: Published Topstep round-turn commissions, from the repository's cost model.
ROUND_TURN = {"ES": 3.78, "NQ": 3.78, "MES": 1.22, "MNQ": 1.22}
BLOCK = 20
N_PATHS = 400
MAX_DAYS = 120


def session_paths(symbol: str, leg: str) -> list[tuple[dt.date, np.ndarray]]:
    """Per-session equity paths in POINTS per contract, from the real bars.

    `leg` is "overnight" (18:00 ET -> 09:30 ET) or "rth" (09:30 ET -> 16:00 ET). The path is
    the running mark-to-market of a one-contract long opened at the leg's first print, which
    is what the MLL is tested against.
    """
    from overnight_panel import load_full_session
    df = load_full_session(symbol)
    out = []
    for tdate, g in df.groupby("tdate"):
        if leg == "overnight":
            seg = g[(g["hm"] >= "18:00") | (g["hm"] < "09:30")]
            need = 200
        else:
            seg = g[(g["hm"] >= "09:30") & (g["hm"] <= "16:00")]
            need = 300
        if len(seg) < need:
            continue
        c = seg["c"].to_numpy(dtype=float)
        out.append((tdate, c - c[0]))
    return out


def to_twin_days(paths: list[tuple[dt.date, np.ndarray]], symbol: str, n_contracts: int,
                 take: np.ndarray | None = None) -> list[TwinDay]:
    """Convert point paths to dollar TwinDays at a given size, charging the round turn."""
    pv, rt = POINT_VALUE[symbol], ROUND_TURN[symbol]
    days = []
    for i, (d, p) in enumerate(paths):
        if take is not None and not take[i]:
            days.append(TwinDay(day=d, pnl=0.0, path=(0.0,), traded=False))
            continue
        dollars = p * pv * n_contracts - rt * n_contracts
        # Subsample the path: the MLL cares about the extremes, and 1,400 points per session
        # times 400 paths is a lot of arithmetic for no extra fidelity on the minimum.
        step = max(1, len(dollars) // 120)
        pts = tuple(float(x) for x in dollars[::step]) + (float(dollars[-1]),)
        days.append(TwinDay(day=d, pnl=float(dollars[-1]), path=pts, traded=True))
    return days


def block_bootstrap_indices(n: int, length: int, rng: np.random.Generator) -> np.ndarray:
    """Contiguous blocks, wrapping, so volatility clusters survive the resampling."""
    idx = []
    while len(idx) < length:
        start = int(rng.integers(0, n))
        idx.extend(((start + k) % n) for k in range(BLOCK))
    return np.array(idx[:length])


def run_sweep(symbol: str, leg: str, sizes: list[int], gate: np.ndarray | None = None,
              label: str = "") -> list[dict]:
    paths = session_paths(symbol, leg)
    if not paths:
        return []
    rng = np.random.default_rng(20260914)
    n = len(paths)
    rows = []
    for size in sizes:
        base = to_twin_days(paths, symbol, size, take=gate)
        passed = breached = 0
        days_to_pass, min_buffers = [], []
        for _ in range(N_PATHS):
            idx = block_bootstrap_indices(n, MAX_DAYS, rng)
            seq = [base[i] for i in idx]
            # Dates must be strictly increasing for the account's day accounting.
            seq = [TwinDay(day=dt.date(2025, 1, 1) + dt.timedelta(days=k), pnl=s.pnl,
                           path=s.path, traded=s.traded) for k, s in enumerate(seq)]
            twin = TopstepTwin(50_000, strict_path=True, allow_unverified_target=True)
            res = twin.run(seq)
            if res.combine_days is not None:
                passed += 1
                days_to_pass.append(res.combine_days)
            if res.breach_day is not None:
                breached += 1
            min_buffers.append(res.min_buffer)
        rows.append({
            "symbol": symbol, "leg": label or leg, "contracts": size,
            "pass_rate": passed / N_PATHS, "breach_rate": breached / N_PATHS,
            "median_days_to_pass": float(np.median(days_to_pass)) if days_to_pass else np.nan,
            "median_min_buffer": float(np.median(min_buffers)),
        })
    return rows


def main() -> int:
    from overnight_hypotheses import futures_features
    fut = futures_features(pd.read_parquet(REPO / "research" / "overnight_panel.parquet"))

    print("=" * 96)
    print("THE COMBINE, WITH REAL INTRADAY PATHS AND THE INTRADAY MLL TEST ARMED")
    print(f"$50,000 account, $3,000 target, $2,000 trailing MLL, {MAX_DAYS} sessions allowed,")
    print(f"{N_PATHS} block-bootstrapped paths per cell, round turn charged per contract.")
    print("=" * 96)

    all_rows = []
    for symbol in ["MES", "MNQ", "ES", "NQ"]:
        sizes = [1, 2, 5, 10, 20] if symbol.startswith("M") else [1, 2, 5]
        for leg in ["overnight", "rth"]:
            all_rows.extend(run_sweep(symbol, leg, sizes))

    df = pd.DataFrame(all_rows)
    print(f"\n{'sym':5} {'leg':11} {'n':>4} {'pass rate':>10} {'breach rate':>12} "
          f"{'med days':>9} {'med min buffer':>15}")
    for sym, g in df.groupby("symbol", sort=False):
        for _, r in g.iterrows():
            print(f"{r['symbol']:5} {r['leg']:11} {int(r['contracts']):4d} "
                  f"{r['pass_rate']:10.1%} {r['breach_rate']:12.1%} "
                  f"{r['median_days_to_pass']:9.0f} ${r['median_min_buffer']:14,.0f}")
        print()

    print("=" * 96)
    print("THE ONE CONSTRUCTION THAT USES THE SURVIVING FINDING")
    print("=" * 96)
    print("The range forecast cannot pick direction, so the only thing it can do is pick when")
    print("to be on. Gate: take the RTH long only when the overnight range is in the lowest")
    print("tercile of a TRAILING window - decision made at 09:29 with no future information.\n")
    gated = []
    for symbol in ["MES", "MNQ"]:
        g = fut[fut.symbol == symbol].sort_values("tdate").reset_index(drop=True)
        thresh = g["on_range_pct"].expanding(60).quantile(0.33).shift(1)
        quiet = (g["on_range_pct"] <= thresh).to_numpy()
        loud = (g["on_range_pct"] > thresh).to_numpy() & np.isfinite(thresh.to_numpy())
        paths = session_paths(symbol, "rth")
        # Align the gate to the sessions that actually produced a path.
        pdates = {d for d, _ in paths}
        mask_q = np.array([bool(q) for d, q in zip(g["tdate"], quiet) if d in pdates])
        mask_l = np.array([bool(x) for d, x in zip(g["tdate"], loud) if d in pdates])
        print(f"  {symbol}: {mask_q.sum()} quiet sessions, {mask_l.sum()} loud, "
              f"{len(paths)} total")
        gated.extend(run_sweep(symbol, "rth", [5, 10, 20], gate=mask_q, label="rth|quiet"))
        gated.extend(run_sweep(symbol, "rth", [5, 10, 20], gate=mask_l, label="rth|loud"))
    gdf = pd.DataFrame(gated)
    print(f"\n{'sym':5} {'leg':11} {'n':>4} {'pass rate':>10} {'breach rate':>12} "
          f"{'med days':>9} {'med min buffer':>15}")
    for _, r in gdf.iterrows():
        print(f"{r['symbol']:5} {r['leg']:11} {int(r['contracts']):4d} "
              f"{r['pass_rate']:10.1%} {r['breach_rate']:12.1%} "
              f"{r['median_days_to_pass']:9.0f} ${r['median_min_buffer']:14,.0f}")

    out = pd.concat([df, gdf], ignore_index=True)
    out.to_csv(REPO / "research" / "overnight_combine.csv", index=False)
    print(f"\nwrote {REPO / 'research' / 'overnight_combine.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
