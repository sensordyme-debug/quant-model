"""Phases 1, 4 and 16: do these entries contain information at all, before any exit is built?

WHY THIS RUNS FIRST
-------------------
The brief's Phase 16 is the gate on everything else: if an entry has no favourable-excursion
advantage, exit optimisation must not be used to rescue it. Building the exit machinery first
and discovering afterwards that the entries are empty would be spending a week to learn
something a day answers.

So this module measures the ENTRY alone. No stop, no target, no exit rule - just: at the
moment this signal fires, what does the next N bars do in the signal's own direction, and how
does that compare to firing at random?

THE CONTROL IS THE WHOLE TEST
-------------------------------
A raw forward return tells you nothing. Index futures have a time-of-day pattern, an
unconditional drift and a direction mix, and a signal that fires mostly long in the morning
will post a positive signed forward return for reasons that have nothing to do with the signal.

So every candidate is measured against a control matched on BOTH of the things that could
manufacture the result:

    time of day    the control draws its entry bars from the same bar-of-session distribution
    direction      the control inherits the candidate's own long/short sequence

What is left after that matching is what the signal actually knows. The statistic reported is
the candidate's mean signed forward return minus the control's, expressed in dollars per
contract and as a percentile against the control distribution.

WHAT COUNTS AS PASSING
------------------------
Declared before running:

    PASS       mean signed forward excursion exceeds the 95th percentile of the matched
               control at two or more horizons, on a mechanism-consistent horizon
    MARGINAL   exceeds it at exactly one horizon
    FAIL       exceeds it nowhere

A mechanism-consistent horizon matters: a reversion signal with a 3-minute median hold should
show its advantage early and give it back later, and a trend signal should do the opposite.
An advantage that appears only at a horizon the mechanism never holds for is not that
mechanism's edge.

THE CANDIDATE SET, AND WHY EACH ONE
-------------------------------------
Six cells, four families, chosen from evidence already on disk and fixed before this ran.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import futures_discover as fd  # noqa: E402

fd.use_session(*fd.TOPSTEP_SESSION)

from quant_brain.markets.futures_cme import features as fe        # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst   # noqa: E402
from strategy_registry import family_added                        # noqa: E402
from strategy_tournament import build_strategies, calibrate       # noqa: E402

HORIZONS = (1, 3, 5, 10, 20, 30, 60)
N_CONTROLS = 200


@dataclass(frozen=True)
class Candidate:
    strategy: str
    symbol: str
    family: str
    reason: str
    expected_horizon: str


#: PREREGISTERED. Fixed before any entry-information number was computed.
CANDIDATES: tuple[Candidate, ...] = (
    Candidate("breakout.failed_reversal", "MNQ", "failed breakout",
              "Named in the brief. Best barrier-relative profile in the whole lab: "
              "+$0.95/trade after a tick of slippage, drawdown 0.09x the MLL, and zero DLL "
              "breaches in the sample. 343 trades is thin, which is the reason it is a "
              "RESEARCH verdict rather than a candidate.",
              "short - it fades a failed move, so the edge should be early"),
    Candidate("revert.vwap.q95", "MNQ", "reversion",
              "Strongest positive-expectancy reversion that already fits inside the barrier "
              "(0.90x MLL). 80.8% win rate on 755 trades, +$3.17/trade stressed. The family "
              "the asset class's mean-reversion favours.",
              "short - reversion pays on the snap back"),
    Candidate("revert.vwap.q90", "NQ", "reversion",
              "The canonical 'good entry, bad exit?' test case. Highest expectancy in the "
              "entire lab at $24.73/trade and an 80.9% win rate, REJECTED solely because its "
              "drawdown is 20x the barrier. If any cell has a good entry ruined by having no "
              "exit, it is this one.",
              "short - same mechanism as above on the full-size contract"),
    Candidate("session.midday_reversion", "MNQ", "session",
              "Sub-barrier (0.69x) on 1,797 trades from a different family, so the candidate "
              "set is not four flavours of one idea. Near-zero expectancy, which makes it a "
              "clean test of whether an exit alone can move a coin flip.",
              "short - a midday fade"),
    Candidate("trend.ret_30.q80", "MNQ", "trend",
              "CONTRAST, not a hope. The best trend cell in the lab is still -$1.62/trade "
              "with a 24.1% win rate and t = -1.99, i.e. reliably losing. Included because "
              "the answer to Phase 16 is only interpretable if a family expected to fail is "
              "measured alongside the families expected to pass.",
              "long - trend needs time to pay"),
    Candidate("breakout.range_expansion.q80", "MNQ", "breakout",
              "Best pure breakout on the micros (-$1.20/trade, 39.0% win, 1.84x MLL). The "
              "brief asks for a breakout contrast and failed_reversal is a fade, not a "
              "breakout.",
              "long - a breakout that works should keep going"),
)


def entry_events(pos: np.ndarray) -> list[tuple[int, int]]:
    """(bar, direction) for every moment the signal OPENS a position.

    A flip from long to short is one close and one open, so it appears once here as the new
    direction. Holding is not an event: this measures what the signal knew when it decided,
    not what it earned while it waited.
    """
    out = []
    prev = 0.0
    for i, p in enumerate(pos):
        if p != 0 and p != prev:
            out.append((i, int(np.sign(p))))
        prev = p
    return out


def excursions(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray,
               bar: int, direction: int, h: int) -> tuple[float, float, float]:
    """Signed forward return, MFE and MAE over the next h bars, in POINTS per contract."""
    end = min(bar + h, len(closes) - 1)
    if end <= bar:
        return np.nan, np.nan, np.nan
    entry = closes[bar]
    fwd = (closes[end] - entry) * direction
    seg_hi = highs[bar + 1:end + 1]
    seg_lo = lows[bar + 1:end + 1]
    if direction > 0:
        mfe, mae = float(seg_hi.max() - entry), float(seg_lo.min() - entry)
    else:
        mfe, mae = float(entry - seg_lo.min()), float(entry - seg_hi.max())
    return float(fwd), mfe, mae


def measure(sessions, feats, strategy, symbol: str, rng: np.random.Generator) -> dict:
    """Signed forward excursions for the real signal and for matched random controls."""
    spec = inst.get(symbol).spec
    mult = spec.multiplier
    real: dict[int, list] = {h: [] for h in HORIZONS}
    mfe_by_h: dict[int, list] = {h: [] for h in HORIZONS}
    mae_by_h: dict[int, list] = {h: [] for h in HORIZONS}
    bar_hist: list[int] = []
    dir_hist: list[int] = []
    per_session: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []

    for g, X in zip(sessions, feats, strict=True):
        pos = np.nan_to_num(np.asarray(strategy.signal(X), dtype=float), nan=0.0)
        c = g["c"].to_numpy(dtype=float)
        hi = g["h"].to_numpy(dtype=float)
        lo = g["l"].to_numpy(dtype=float)
        per_session.append((c, hi, lo))
        ev = entry_events(pos)
        for bar, d in ev:
            bar_hist.append(bar)
            dir_hist.append(d)
            for h in HORIZONS:
                f, mfe, mae = excursions(c, hi, lo, bar, d, h)
                if np.isfinite(f):
                    real[h].append(f * mult)
                    mfe_by_h[h].append(mfe * mult)
                    mae_by_h[h].append(mae * mult)

    n_ev = len(bar_hist)
    out = {"n_entries": n_ev, "long_share": float(np.mean(np.array(dir_hist) > 0))
           if n_ev else np.nan}
    if n_ev < 50:
        return out

    # ---- matched controls: same bar-of-session distribution, same direction sequence -------
    bar_arr = np.array(bar_hist)
    dir_arr = np.array(dir_hist)
    n_sess = len(per_session)
    ctrl_means: dict[int, list] = {h: [] for h in HORIZONS}
    for _ in range(N_CONTROLS):
        vals: dict[int, list] = {h: [] for h in HORIZONS}
        sess_idx = rng.integers(0, n_sess, n_ev)
        for k in range(n_ev):
            c, hi, lo = per_session[sess_idx[k]]
            bar = int(bar_arr[k])
            if bar >= len(c) - 2:
                continue
            for h in HORIZONS:
                f, _, _ = excursions(c, hi, lo, bar, int(dir_arr[k]), h)
                if np.isfinite(f):
                    vals[h].append(f * mult)
        for h in HORIZONS:
            if vals[h]:
                ctrl_means[h].append(float(np.mean(vals[h])))

    for h in HORIZONS:
        r = np.array(real[h], dtype=float)
        cm = np.array(ctrl_means[h], dtype=float)
        out[f"fwd_{h}"] = float(r.mean()) if len(r) else np.nan
        out[f"fwd_{h}_sd"] = float(r.std(ddof=1)) if len(r) > 1 else np.nan
        out[f"fwd_{h}_t"] = (float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r))))
                             if len(r) > 1 and r.std(ddof=1) > 0 else np.nan)
        out[f"ctrl_{h}"] = float(np.median(cm)) if len(cm) else np.nan
        out[f"ctrl_{h}_p95"] = float(np.percentile(cm, 95)) if len(cm) else np.nan
        out[f"ctrl_{h}_pctile"] = (float((cm < r.mean()).mean())
                                   if len(cm) and len(r) else np.nan)
        out[f"mfe_{h}"] = float(np.mean(mfe_by_h[h])) if mfe_by_h[h] else np.nan
        out[f"mae_{h}"] = float(np.mean(mae_by_h[h])) if mae_by_h[h] else np.nan
        out[f"mfe_mae_{h}"] = (abs(out[f"mfe_{h}"] / out[f"mae_{h}"])
                               if out[f"mae_{h}"] not in (0, np.nan) else np.nan)
    return out


def main() -> int:
    rng = np.random.default_rng(20260914)
    rows = []
    by_symbol: dict[str, tuple] = {}

    print("=" * 112)
    print("PHASE 1 - PREREGISTERED CANDIDATE SET")
    print("=" * 112)
    for c in CANDIDATES:
        print(f"\n  {c.strategy}  ·  {c.symbol}  ·  {c.family}")
        print(f"    {c.reason}")
        print(f"    expected edge horizon: {c.expected_horizon}")

    for sym in sorted({c.symbol for c in CANDIDATES}):
        store = REPO / "data" / "futures" / f"{sym}.parquet"
        df = fd.load(store, sym)
        sessions = fd.session_frames(df)
        feats = fd.build_features(sessions, fe.library())
        cal = calibrate(feats[:len(sessions) // 2], sym)
        strat = {s.name: s for s in list(build_strategies(cal)) + list(family_added(cal))}
        by_symbol[sym] = (sessions, feats, strat)

    print("\n" + "=" * 112)
    print("PHASES 4 AND 16 - DOES THE ENTRY CONTAIN INFORMATION?")
    print(f"signed forward excursion in $ per contract, against {N_CONTROLS} controls "
          f"matched on bar-of-session AND direction")
    print("=" * 112)

    for cand in CANDIDATES:
        sessions, feats, strat = by_symbol[cand.symbol]
        s = strat.get(cand.strategy)
        if s is None:
            print(f"  {cand.strategy}: NOT FOUND")
            continue
        m = measure(sessions, feats, s, cand.symbol, rng)
        m.update({"strategy": cand.strategy, "symbol": cand.symbol,
                  "family": cand.family})
        rows.append(m)
        print(f"\n--- {cand.strategy} · {cand.symbol} · {cand.family} "
              + "-" * max(0, 50 - len(cand.strategy)))
        print(f"    {m['n_entries']:,} entries, {m['long_share']:.0%} long")
        print(f"    {'bars':>5} {'fwd $':>9} {'t':>7} {'ctrl med':>9} {'ctrl p95':>9} "
              f"{'pctile':>8} {'MFE $':>8} {'MAE $':>8} {'MFE/MAE':>8}")
        for h in HORIZONS:
            if f"fwd_{h}" not in m:
                continue
            flag = " <<<" if m[f"ctrl_{h}_pctile"] > 0.95 else ""
            print(f"    {h:5d} {m[f'fwd_{h}']:9.3f} {m[f'fwd_{h}_t']:7.2f} "
                  f"{m[f'ctrl_{h}']:9.3f} {m[f'ctrl_{h}_p95']:9.3f} "
                  f"{m[f'ctrl_{h}_pctile']:8.1%} {m[f'mfe_{h}']:8.2f} "
                  f"{m[f'mae_{h}']:8.2f} {m[f'mfe_mae_{h}']:8.2f}{flag}")

    out = pd.DataFrame(rows)
    out.to_csv(REPO / "research" / "exit_entry_information.csv", index=False)

    print("\n" + "=" * 112)
    print("THE GATE  (declared before running)")
    print("=" * 112)
    print("  PASS     beats the matched control's 95th percentile at 2+ horizons")
    print("  MARGINAL beats it at exactly 1")
    print("  FAIL     beats it nowhere\n")
    verdicts = {}
    for _, r in out.iterrows():
        n_beat = sum(1 for h in HORIZONS
                     if f"ctrl_{h}_pctile" in r and np.isfinite(r[f"ctrl_{h}_pctile"])
                     and r[f"ctrl_{h}_pctile"] > 0.95)
        v = "PASS" if n_beat >= 2 else "MARGINAL" if n_beat == 1 else "FAIL"
        verdicts[(r.strategy, r.symbol)] = v
        hz = [h for h in HORIZONS if f"ctrl_{h}_pctile" in r
              and np.isfinite(r[f"ctrl_{h}_pctile"]) and r[f"ctrl_{h}_pctile"] > 0.95]
        print(f"  {r.strategy[:30]:30} {r.symbol:5} {v:9} "
              f"beats control at {n_beat}/{len(HORIZONS)} horizons"
              + (f"  ({', '.join(str(x) + 'b' for x in hz)})" if hz else ""))
    (REPO / "research" / "exit_entry_gate.json").write_text(
        json.dumps({f"{k[0]}|{k[1]}": v for k, v in verdicts.items()}, indent=1),
        encoding="utf-8")

    n_pass = sum(1 for v in verdicts.values() if v == "PASS")
    print(f"\n  {n_pass} of {len(verdicts)} candidates carry entry information.")
    if n_pass == 0:
        print("\n  PHASE 16 ANSWER: the library has BAD ENTRIES. Exit architecture cannot")
        print("  rescue a signal with no forward advantage, and the brief forbids trying.")
    else:
        print("\n  Exit research proceeds for the passing candidates ONLY.")
    print(f"\nwrote {REPO / 'research' / 'exit_entry_information.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
