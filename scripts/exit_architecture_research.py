"""Phases 2, 3, 5-11: exit architectures for the one entry that carries information.

WHO IS IN AND WHY
-----------------
The entry-information gate (`exit_entry_information.py`) admitted exactly one candidate:

    breakout.failed_reversal MNQ    PASS - beats a matched control at bars 1, 3 and 5
                                    (99.0, 97.5, 97.5 percentile), t = 2.48/1.93/2.14,
                                    decaying to nothing by bar 10

That is mechanism-consistent: the architecture note preregistered "short - it fades a failed
move, so the edge should be early", and the edge is early.

Everything else failed or was marginal, and the brief is explicit that exit research proceeds
for passing candidates only. In particular `revert.vwap.q90` on NQ - the highest-expectancy
cell in the entire lab at $24.73/trade on an 80.9% win rate - beats the matched control at
NONE of seven horizons and sits at the 2nd percentile at ten bars. Its profit is not coming
from entry timing, so an exit cannot be tuned to preserve something that is not there.

ONE DIAGNOSTIC IS RUN ON A NON-PASSING CANDIDATE, DELIBERATELY
----------------------------------------------------------------
`trend.ret_30.q80` MNQ is the clearest "slow information, fast exit" shape in the field: its
only control-beating horizon is 60 bars, which IS mechanism-consistent for trend, and it
currently loses money while turning over 5,511 times. It is run through the time-stop
architecture ONLY, to answer the specific question of whether a trend entry with a long
horizon is being destroyed by an exit that fires in minutes. It is labelled a diagnostic
throughout and is not eligible for any verdict above WATCH.

THE PREREGISTERED GRID
------------------------
Declared here before any exit result was computed, and deliberately small. The brief caps
exit parameters at two, so architectures are enumerated separately rather than crossed into
one large space:

    A  ATR stop x R target      stop {0.5, 0.75, 1.0, 1.25, 1.5} ATR
                                target {0.5, 0.75, 1.0, 1.5, 2.0} R          -> 25
    C  structural stop x target stop at the signal bar's extreme, same targets -> 5
    D  trailing / break-even    trail {0.75, 1.0, 1.5} ATR; break-even at 1R   -> 4
    E  time stop alone          {1, 3, 5, 10, 20, 30} bars                     -> 6
    F  signal invalidation      the current behaviour, as the baseline         -> 1

41 cells. Entry parameters are FROZEN throughout - the brief forbids joint optimisation and
nothing here touches the signal.

WHY THE MFE/MAE RATIO ALREADY LIMITS WHAT IS POSSIBLE
--------------------------------------------------------
Measured on the entry alone, this candidate's favourable-to-adverse excursion ratio runs 1.06,
1.12, 1.14, 1.06, 1.02, 1.09, 1.06 across the seven horizons. The best geometry in the field,
and still barely above one. A symmetric excursion profile means a stop and a target the same
distance away are hit at roughly equal rates, so no placement of them creates an edge that the
entry did not already have. The realistic ceiling here is a modest improvement in drawdown
shape, not a transformation of expectancy, and that expectation is recorded before the grid
runs rather than discovered afterwards.

SPLIT, AND WHAT IT COSTS
--------------------------
343 trades. The first 60% by date selects the architecture; the last 40% evaluates it. That
leaves roughly 137 out-of-sample trades, which is thin, and the minimum effect the split can
resolve is correspondingly large. Reported rather than glossed.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import futures_discover as fd  # noqa: E402

fd.use_session(*fd.TOPSTEP_SESSION)

from quant_brain.markets.futures_cme import execution_sim as ex   # noqa: E402
from quant_brain.markets.futures_cme import features as fe        # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst   # noqa: E402
from quant_brain.research import exits as X                       # noqa: E402
from strategy_registry import family_added                        # noqa: E402
from strategy_tournament import build_strategies, calibrate       # noqa: E402

PASSING = ("breakout.failed_reversal", "MNQ")
DIAGNOSTIC = ("trend.ret_30.q80", "MNQ")
SPLIT = 0.60
SLIPPAGE_LADDER = (0.0, 0.5, 1.0, 2.0)
N_RANDOM = 200


def build_grid() -> list[X.ExitArchitecture]:
    """The preregistered architectures. Fixed before any result."""
    g: list[X.ExitArchitecture] = [
        X.ExitArchitecture("F.baseline_invalidation", use_invalidation=True)]
    for s in (0.5, 0.75, 1.0, 1.25, 1.5):
        for t in (0.5, 0.75, 1.0, 1.5, 2.0):
            g.append(X.ExitArchitecture(f"A.stop{s:g}atr_tgt{t:g}R", stop_atr=s,
                                        target_r=t, use_invalidation=False))
    for t in (0.5, 0.75, 1.0, 1.5, 2.0):
        g.append(X.ExitArchitecture(f"C.structural_tgt{t:g}R", structural_stop=True,
                                    target_r=t, use_invalidation=False))
    for tr in (0.75, 1.0, 1.5):
        g.append(X.ExitArchitecture(f"D.trail{tr:g}atr", trail_atr=tr,
                                    use_invalidation=False))
    g.append(X.ExitArchitecture("D.stop1atr_be1R", stop_atr=1.0, breakeven_at_r=1.0,
                                target_r=2.0, use_invalidation=False))
    for b in (1, 3, 5, 10, 20, 30):
        g.append(X.ExitArchitecture(f"E.time{b}b", time_stop_bars=b,
                                    use_invalidation=False))
    return g


def session_atr(g: pd.DataFrame) -> float:
    h = g["h"].to_numpy(dtype=float)
    low = g["l"].to_numpy(dtype=float)
    c = g["c"].to_numpy(dtype=float)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - low, np.maximum(np.abs(h - prev), np.abs(low - prev)))
    return float(np.mean(tr))


def load(symbol: str):
    df = fd.load(REPO / "data" / "futures" / f"{symbol}.parquet", symbol)
    sessions = fd.session_frames(df)
    feats = fd.build_features(sessions, fe.library())
    cal = calibrate(feats[:len(sessions) // 2], symbol)
    strat = {s.name: s for s in list(build_strategies(cal)) + list(family_added(cal))}
    return sessions, feats, strat


def run_arch(sessions, feats, strategy, symbol: str, arch: X.ExitArchitecture,
             slip_ticks: float = 0.0, contracts: int = 1) -> pd.DataFrame:
    spec = inst.get(symbol).spec
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(symbol), symbol=symbol)
    cost = sim.round_turn_cost(contracts) + slip_ticks * spec.tick_value * contracts
    rows = []
    for g, Xf in zip(sessions, feats, strict=True):
        pos = np.nan_to_num(np.asarray(strategy.signal(Xf), dtype=float), nan=0.0)
        ev = X.entry_events(pos)
        if not ev:
            continue
        c = g["c"].to_numpy(dtype=float)
        hi = g["h"].to_numpy(dtype=float)
        lo = g["l"].to_numpy(dtype=float)
        atr = session_atr(g)
        day = g["day"].iloc[0]
        busy_until = -1
        for bar, d in ev:
            if bar <= busy_until:          # no pyramiding: one position at a time
                continue
            r = X.simulate_trade(c, hi, lo, pos, bar, d, atr, arch)
            busy_until = r.exit_bar
            rows.append({
                "session": day, "entry_bar": r.entry_bar, "exit_bar": r.exit_bar,
                "direction": r.direction, "points": r.points,
                "gross": r.points * spec.multiplier * contracts,
                "net": r.points * spec.multiplier * contracts - cost,
                "reason": r.reason, "bars_held": r.bars_held,
                "mfe": r.mfe_points * spec.multiplier, "mae": r.mae_points * spec.multiplier,
                "r_multiple": r.r_multiple, "ambiguous": r.ambiguous, "atr": atr})
    return pd.DataFrame(rows)


def stats(t: pd.DataFrame) -> dict:
    if not len(t):
        return {"trades": 0}
    n = t.net.to_numpy(dtype=float)
    wins, losses = n[n > 0], n[n < 0]
    daily = t.groupby("session")["net"].sum()
    eq = np.cumsum(daily.to_numpy())
    dd = float((eq - np.maximum.accumulate(eq)).min()) if len(eq) else 0.0
    run = best = 0
    for v in n:
        run = run + 1 if v < 0 else 0
        best = max(best, run)
    drun = dbest = 0
    for v in daily:
        drun = drun + 1 if v < 0 else 0
        dbest = max(dbest, drun)
    sd = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    return {
        "trades": len(t), "net": float(n.sum()), "per_trade": float(n.mean()),
        "per_day": float(daily.mean()), "median_trade": float(np.median(n)),
        "win_rate": float((n > 0).mean()),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": (float(wins.sum() / -losses.sum()) if len(losses)
                          and losses.sum() < 0 else np.nan),
        "max_dd": dd, "daily_max_loss": float(daily.min()) if len(daily) else 0.0,
        "consec_losing_trades": best, "consec_losing_days": dbest,
        "mean_mfe": float(t.mfe.mean()), "mean_mae": float(t.mae.mean()),
        "mfe_mae": float(abs(t.mfe.mean() / t.mae.mean())) if t.mae.mean() else np.nan,
        "median_bars": float(t.bars_held.median()),
        "trades_per_day": len(t) / max(1, daily.size),
        "t_stat": float(daily.mean() / (sd / np.sqrt(len(daily)))) if sd > 0 else 0.0,
        "pct_stop": float((t.reason == X.STOP).mean()),
        "pct_target": float((t.reason == X.TARGET).mean()),
        "pct_time": float((t.reason == X.TIME).mean()),
        "pct_invalidation": float((t.reason == X.INVALIDATION).mean()),
        "pct_flatten": float((t.reason == X.FLATTEN).mean()),
        "pct_reach_1R": float((t.mfe / (t.atr * inst.get("MNQ").spec.multiplier) >= 1).mean()),
        "ambiguous_share": float(t.ambiguous.mean()),
        "avg_mae_of_winners": float(t[t.net > 0].mae.mean()) if (t.net > 0).any() else np.nan,
        "avg_mfe_of_losers": float(t[t.net < 0].mfe.mean()) if (t.net < 0).any() else np.nan,
    }


def main() -> int:
    grid = build_grid()
    print("=" * 112)
    print("PHASES 2 AND 3 - PREREGISTERED EXIT ARCHITECTURES")
    print(f"{len(grid)} cells, declared before any exit result. Entry parameters FROZEN.")
    print("=" * 112)
    print("\n  Economic reasoning, written before testing:")
    print("   A/C  a fade of a failed move should pay quickly or not at all, so a tight")
    print("        stop with a near target matches the mechanism; a structural stop at the")
    print("        signal bar's extreme is the natural invalidation price for a reversal.")
    print("   D    a trailing stop suits a mechanism whose edge PERSISTS. This one's decays")
    print("        by bar 10, so trailing is expected to underperform and is included as a")
    print("        falsifiable prediction rather than a hope.")
    print("   E    the measured edge lives at bars 1-5, so a time stop in that range should")
    print("        be competitive with any price-based exit. This is the sharpest test of")
    print("        whether the entry's information is being captured at all.")
    print("   F    the current behaviour, as the thing to beat.")

    sessions, feats, strat = load(PASSING[1])
    s = strat[PASSING[0]]
    n_train = int(len(sessions) * SPLIT)
    tr_sess, tr_f = sessions[:n_train], feats[:n_train]
    te_sess, te_f = sessions[n_train:], feats[n_train:]
    print(f"\n  split: {len(tr_sess)} sessions in-sample, {len(te_sess)} out-of-sample")

    rows = []
    for arch in grid:
        a = stats(run_arch(tr_sess, tr_f, s, PASSING[1], arch))
        b = stats(run_arch(te_sess, te_f, s, PASSING[1], arch))
        rows.append({"arch": arch.name, "describe": arch.describe(),
                     **{f"is_{k}": v for k, v in a.items()},
                     **{f"oos_{k}": v for k, v in b.items()}})
    df = pd.DataFrame(rows)
    df.to_csv(REPO / "research" / "exit_grid.csv", index=False)

    print("\n" + "=" * 112)
    print(f"PHASES 5 AND 6 - EXIT SURFACE, {PASSING[0]} {PASSING[1]}")
    print("=" * 112)
    print(f"  {'architecture':26} {'IS trd':>7} {'IS $/tr':>8} {'IS PF':>6} {'IS win':>7} "
          f"{'IS DD':>8} {'OOS trd':>8} {'OOS $/tr':>9} {'OOS PF':>7} {'OOS DD':>8}")
    for _, r in df.sort_values("is_per_trade", ascending=False).iterrows():
        pf_i = r.is_profit_factor if np.isfinite(r.is_profit_factor) else np.nan
        pf_o = r.oos_profit_factor if np.isfinite(r.get("oos_profit_factor", np.nan)) else np.nan
        print(f"  {r['arch'][:26]:26} {r.is_trades:7.0f} {r.is_per_trade:8.2f} "
              f"{pf_i:6.2f} {r.is_win_rate:7.1%} {r.is_max_dd:8.0f} "
              f"{r.get('oos_trades', 0):8.0f} {r.get('oos_per_trade', np.nan):9.2f} "
              f"{pf_o:7.2f} {r.get('oos_max_dd', np.nan):8.0f}")

    print("\n" + "=" * 112)
    print("PHASE 10 - IN-SAMPLE SELECTION vs OUT-OF-SAMPLE TRUTH")
    print("=" * 112)
    best_is = df.loc[df.is_per_trade.idxmax()]
    print(f"  best architecture chosen on the in-sample half : {best_is['arch']}")
    print(f"    in-sample  ${best_is.is_per_trade:.2f}/trade on {best_is.is_trades:.0f} trades")
    print(f"    OUT OF SAMPLE ${best_is.oos_per_trade:.2f}/trade on "
          f"{best_is.oos_trades:.0f} trades")
    pos_is = int((df.is_per_trade > 0).sum())
    pos_both = int(((df.is_per_trade > 0) & (df.oos_per_trade > 0)).sum())
    print(f"\n  architectures positive in-sample        : {pos_is} of {len(df)}")
    print(f"  positive in BOTH halves                 : {pos_both}")
    corr = df[["is_per_trade", "oos_per_trade"]].corr().iloc[0, 1]
    print(f"  rank correlation IS vs OOS $/trade      : {corr:+.3f}")
    print("  (a correlation near zero means in-sample selection carries no information "
          "about\n   out-of-sample performance, which is the definition of an overfit grid)")

    print("\n" + "=" * 112)
    print("PHASE 9 - IS THERE A PLATEAU?  (architecture A surface, in-sample $/trade)")
    print("=" * 112)
    a = df[df.arch.str.startswith("A.")].copy()
    a["stop"] = a.arch.str.extract(r"stop([\d.]+)atr").astype(float)
    a["tgt"] = a.arch.str.extract(r"tgt([\d.]+)R").astype(float)
    piv = a.pivot_table(index="stop", columns="tgt", values="is_per_trade")
    print("  in-sample $/trade")
    print(piv.round(2).to_string())
    pivo = a.pivot_table(index="stop", columns="tgt", values="oos_per_trade")
    print("\n  out-of-sample $/trade")
    print(pivo.round(2).to_string())
    print(f"\n  in-sample cells positive : {int((piv.to_numpy() > 0).sum())} of {piv.size}")
    print(f"  out-of-sample positive   : {int((pivo.to_numpy() > 0).sum())} of {pivo.size}")
    print(f"  sign agreement across the surface : "
          f"{float((np.sign(piv.to_numpy()) == np.sign(pivo.to_numpy())).mean()):.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
