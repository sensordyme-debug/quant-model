"""Phases 6 and 9: does the null propagate to strategy economics, and what would costs do?

WHY THIS IS DELIBERATELY SMALL
--------------------------------
The brief asks for three arms per strategy family: baseline, volatility-conditioned, and
volatility-plus-second-variable conditioned.

The first two already exist. `research/opportunity_gating.csv` holds 120 cells of baseline
versus volatility-gated across 30 mechanisms and four instruments, with regime-matched and
scale-normalised random controls. Re-running it would spend trials to re-learn what is
already recorded.

The third arm cannot honestly be built. No second variable passed Phase 3. The brief's own
two-stage rule says a gate must first predict an independently measured opportunity variable
before it is allowed to touch strategy economics, and nothing did:

    4,788 window-matched tests. 0 clear Bonferroni in the search window AND replicate
    out of sample. The inverted-U alternative: 0 of 24 cells pass all three criteria.

Building a third arm from a variable that failed validation is exactly the error the two-stage
rule exists to prevent. So instead of a grid, this module runs ONE focused experiment that
closes the loop: take the strongest second-variable candidate BY SEARCH-WINDOW EVIDENCE - the
one a researcher who skipped the holdout would have chosen - build the conditioned gate, and
show what happens. That is the demonstration that the null propagates, and it costs three
mechanisms rather than thirty.

WHAT THE COST SECTION ADDS
----------------------------
Phase 9 asks for economics under four slippage assumptions. The previous phase established
that one tick erases 13 of 36 positive cells. This module extends that to the stress case and
reports the break-even slippage per mechanism - the number of ticks that takes each cell to
zero - which is more informative than a pass/fail at one assumed level.
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
from opportunity_gating import build_gate, matched_random_gates   # noqa: E402
from strategy_tournament import build_strategies, calibrate       # noqa: E402

#: One representative mechanism per family, named in advance rather than picked from results.
REPRESENTATIVES = ("trend.ret_30.q80", "breakout.range_expansion.q80", "revert.vwap.q90")

#: The strongest second-variable candidate by SEARCH-window evidence. It failed the holdout
#: (t fell from +5.54 to +0.19); it is used here precisely because a researcher who stopped at
#: the search window would have chosen it.
SECOND_VAR = "prev_rv_pct"

N_CONTROLS = 40
SLIPPAGE_TICKS = (0.0, 0.5, 1.0, 2.0)


def evaluate(strategy, sessions, feats, symbol: str, mask: np.ndarray,
             slip_ticks: float = 0.0, contracts: int = 1) -> dict:
    spec = inst.get(symbol).spec
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(symbol), symbol=symbol)
    cost = sim.round_turn_cost(contracts) + slip_ticks * spec.tick_value * contracts
    pnls, trades = [], 0.0
    mae, mfe = [], []
    for i, (g, X) in enumerate(zip(sessions, feats, strict=True)):
        if not mask[i]:
            continue
        pos = np.nan_to_num(np.asarray(strategy.signal(X), dtype=float), nan=0.0)
        path, turns, _ = fd.session_accounting(
            pos, g["c"].to_numpy(dtype=float), multiplier=spec.multiplier,
            contracts=contracts, round_turn_cost=cost)
        trades += turns
        if len(path):
            pnls.append(float(path[-1]))
            mae.append(float(np.min(path)))
            mfe.append(float(np.max(path)))
    a = np.asarray(pnls, dtype=float)
    if not len(a) or trades < 1:
        return {"n": 0, "trades": 0, "net": 0.0, "per_trade": np.nan}
    sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    wins, losses = a[a > 0].sum(), -a[a < 0].sum()
    eq = np.cumsum(a)
    run = best = 0
    for v in a:
        run = run + 1 if v < 0 else 0
        best = max(best, run)
    return {"n": len(a), "trades": int(round(trades)), "net": float(a.sum()),
            "per_trade": float(a.sum() / trades),
            "per_session": float(a.mean()),
            "t": float(a.mean() / (sd / np.sqrt(len(a)))) if sd > 0 else 0.0,
            "win_rate": float((a > 0).mean()),
            "profit_factor": float(wins / losses) if losses > 0 else np.inf,
            "max_dd": float((eq - np.maximum.accumulate(eq)).min()),
            "max_consec_losses": best,
            "mean_mae": float(np.mean(mae)), "mean_mfe": float(np.mean(mfe))}


def main() -> int:
    panel = pd.read_parquet(REPO / "research" / "opportunity_panel.parquet")
    eff = pd.read_parquet(REPO / "research" / "efficiency_futures.parquet")
    rng = np.random.default_rng(80808)
    rows, cost_rows = [], []

    print("=" * 108)
    print("PHASE 6 - DOES THE NULL PROPAGATE TO STRATEGY ECONOMICS?")
    print(f"three arms x {len(REPRESENTATIVES)} representative mechanisms x 4 instruments")
    print(f"second variable: {SECOND_VAR} (strongest in the SEARCH window; FAILED the holdout)")
    print("=" * 108)

    for symbol in ("ES", "NQ", "MES", "MNQ"):
        store = REPO / "data" / "futures" / f"{symbol}.parquet"
        if not store.exists():
            continue
        df = fd.load(store, symbol)
        sessions = fd.session_frames(df)
        if not sessions:
            continue
        feats = fd.build_features(sessions, fe.library())
        dates = [g["day"].iloc[0] for g in sessions]
        cal = calibrate(feats[:len(sessions) // 2], symbol)
        strategies = {s.name: s for s in build_strategies(cal)}

        evaluable, gate_vol, regime = build_gate(panel, symbol, dates, 0.5)

        # the second-variable gate, causal: above the trailing median of prev_rv_pct
        e = eff[eff.symbol == symbol].sort_values("tdate").reset_index(drop=True)
        thr = e[SECOND_VAR].shift(1).expanding(20).quantile(0.5)
        hi2 = dict(zip(e["tdate"], (e[SECOND_VAR] >= thr) & thr.notna()))
        gate_second = np.array([bool(hi2.get(d, False)) for d in dates])
        gate_both = evaluable & gate_vol & gate_second

        controls = matched_random_gates(gate_both, evaluable, regime, N_CONTROLS, rng)

        print(f"\n{symbol}: {int(evaluable.sum())} evaluable, vol-gate {int(gate_vol.sum())}, "
              f"vol+{SECOND_VAR} {int(gate_both.sum())}")
        print(f"  {'mechanism':30} {'arm':16} {'trades':>7} {'$/trade':>9} {'net $':>10} "
              f"{'PF':>6} {'win%':>6} {'maxDD $':>9} {'ctrl pct':>9}")

        for name in REPRESENTATIVES:
            s = strategies.get(name)
            if s is None:
                continue
            arms = (("baseline", evaluable), ("vol-gated", evaluable & gate_vol),
                    (f"vol+{SECOND_VAR}", gate_both))
            for arm, mask in arms:
                r = evaluate(s, sessions, feats, symbol, mask)
                if not r.get("trades"):
                    continue
                pct = np.nan
                if arm.startswith("vol+"):
                    cv = np.array([evaluate(s, sessions, feats, symbol, m)["per_trade"]
                                   for m in controls])
                    cv = cv[np.isfinite(cv)]
                    pct = float((cv < r["per_trade"]).mean()) if len(cv) else np.nan
                rows.append({"symbol": symbol, "mechanism": name, "arm": arm,
                             "ctrl_pctile": pct, **r})
                print(f"  {name[:30]:30} {arm[:16]:16} {r['trades']:7d} "
                      f"{r['per_trade']:9.2f} {r['net']:10.0f} {r['profit_factor']:6.2f} "
                      f"{r['win_rate']:6.1%} {r['max_dd']:9.0f} "
                      f"{pct if np.isfinite(pct) else float('nan'):9.1%}")

            # ---- Phase 9: slippage ladder on the best arm -----------------------------
            for slip in SLIPPAGE_TICKS:
                r = evaluate(s, sessions, feats, symbol, gate_both, slip_ticks=slip)
                if r.get("trades"):
                    cost_rows.append({"symbol": symbol, "mechanism": name,
                                      "slip_ticks": slip, "per_trade": r["per_trade"],
                                      "net": r["net"], "trades": r["trades"]})

    out = pd.DataFrame(rows)
    out.to_csv(REPO / "research" / "efficiency_families.csv", index=False)
    cost = pd.DataFrame(cost_rows)
    cost.to_csv(REPO / "research" / "efficiency_costs.csv", index=False)

    print("\n" + "=" * 108)
    print("ARM COMPARISON")
    print("=" * 108)
    if len(out):
        piv = out.pivot_table(index=["symbol", "mechanism"], columns="arm",
                              values="per_trade")
        print(piv.round(2).to_string())
        second = out[out.arm.str.startswith("vol+")]
        print(f"\n  vol+second arm beating its regime-matched control p95: "
              f"{int((second.ctrl_pctile > 0.95).sum())} of {len(second)} "
              f"(expected by chance {len(second) * 0.05:.1f})")
        print(f"  vol+second arm with POSITIVE $/trade: "
              f"{int((second.per_trade > 0).sum())} of {len(second)}")

    print("\n" + "=" * 108)
    print("PHASE 9 - SLIPPAGE LADDER")
    print("=" * 108)
    if len(cost):
        cp = cost.pivot_table(index=["symbol", "mechanism"], columns="slip_ticks",
                              values="per_trade")
        print(cp.round(2).to_string())
        print("\n  break-even slippage (ticks) for cells positive at zero:")
        any_pos = False
        for (sym, mech), r in cp.iterrows():
            if r.get(0.0, -1) > 0:
                any_pos = True
                spec = inst.get(sym).spec
                # linear interpolation of $/trade against ticks
                be = r[0.0] / max(1e-9, (r[0.0] - r[1.0])) if 1.0 in r else np.nan
                print(f"    {sym:5} {mech[:28]:28} breaks even at {be:.2f} ticks "
                      f"(1 tick = ${spec.tick_value:.2f})")
        if not any_pos:
            print("    none - no cell is positive even at zero slippage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
