"""Phase 7: could any of this make money inside the Topstep 50K constraints?

THE ORDER THE BRIEF ASKS FOR, AND WHY IT MATTERS
--------------------------------------------------
"Do NOT optimize specifically to pass the Combine. The scientific objective is positive
expected trading economics first."

So this module asks the questions in that order, and stops as soon as one of them is answered
no - because running a Combine simulation on a mechanism with negative expectancy would
produce a pass rate, and a pass rate is a number, and a number in a report gets quoted.

    1. Does any mechanism have positive expectancy at all?
    2. Does that expectancy survive the multiplicity bar for having looked at 120 cells?
    3. Does it survive realistic slippage on top of commission?
    4. Only then: what does it do inside the Combine's barriers?

MULTIPLICITY IS THE WHOLE STORY HERE
--------------------------------------
Phase 3 evaluated 30 mechanisms across 4 instruments, twice each (gated and ungated). Picking
the best-looking cell from that grid and reporting its profit is the single most common way a
backtest lies. Thirteen of the 120 ungated cells have positive dollars per trade; with 120
draws from a distribution centred near zero, that is roughly what pure noise produces.

The defence is a t-statistic on the per-session series and a Bonferroni threshold that counts
the whole grid. At 240 evaluations the two-sided 5% bar is about |t| > 3.7. That is a hard
bar and it is meant to be: it is the price of having looked at everything.

SLIPPAGE, WHICH THE PREVIOUS PHASES DID NOT CHARGE
----------------------------------------------------
Phases 3 and 4 charged the published Topstep round-turn commission and nothing else. That is
the right choice for a CONTROLLED comparison, because slippage would apply equally to the gate
and its control and would only add noise to the difference.

It is the wrong choice for an economics question. A market order crossing the spread pays at
least half a tick each way on a liquid contract and more when the book is thin - which is
disproportionately the high-volatility sessions the gate selects. So this module re-prices
every surviving candidate at one full tick of round-turn slippage on top of commission, and
reports both numbers.
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
from quant_brain.markets.futures_cme.twin import TopstepTwin, TwinDay  # noqa: E402
from opportunity_gating import build_gate                          # noqa: E402
from strategy_tournament import build_strategies, calibrate        # noqa: E402

#: Total evaluations in the Phase 3 grid: 30 mechanisms x 4 instruments x {gated, ungated}.
N_EVALUATIONS = 240
BLOCK = 20
N_PATHS = 300
MAX_DAYS = 120


def bonferroni_t(n_trials: int, alpha: float = 0.05) -> float:
    return float(np.sqrt(2) * _erfinv(1 - alpha / n_trials))


def _erfinv(y: float) -> float:
    a = 0.147
    ln = np.log(1 - y * y)
    term = 2 / (np.pi * a) + ln / 2
    return float(np.sign(y) * np.sqrt(np.sqrt(term * term - ln / a) - term))


def session_series(strategy, sessions, feats, symbol: str, contracts: int,
                   mask: np.ndarray, slip_ticks: float = 0.0):
    """Per-session P&L and intraday path, with optional slippage on every round turn."""
    spec = inst.get(symbol).spec
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(symbol), symbol=symbol)
    tick_cost = sim.round_turn_cost(contracts)
    slip = slip_ticks * spec.tick_value * contracts
    out = []
    for i, (g, X) in enumerate(zip(sessions, feats, strict=True)):
        if not mask[i]:
            continue
        pos = np.nan_to_num(np.asarray(strategy.signal(X), dtype=float), nan=0.0)
        net_path, turns, _ = fd.session_accounting(
            pos, g["c"].to_numpy(dtype=float), multiplier=spec.multiplier,
            contracts=contracts, round_turn_cost=tick_cost + slip)
        out.append((g["day"].iloc[0], np.asarray(net_path, dtype=float), turns))
    return out


def main() -> int:
    panel = pd.read_parquet(REPO / "research" / "opportunity_panel.parquet")
    prior = pd.read_csv(REPO / "research" / "opportunity_gating.csv")
    t_bar = bonferroni_t(N_EVALUATIONS)

    print("=" * 104)
    print("PHASE 7 - TOPSTEP ECONOMICS")
    print(f"Bonferroni bar for {N_EVALUATIONS} evaluations in the Phase 3 grid: "
          f"|t| > {t_bar:.2f}")
    print("=" * 104)

    print("\n--- STEP 1: does anything have positive expectancy? " + "-" * 50)
    pos_base = prior[prior.base_per_trade > 0]
    pos_gate = prior[prior.gated_per_trade > 0]
    print(f"  cells with positive $/trade, ungated : {len(pos_base):3d} of {len(prior)}")
    print(f"  cells with positive $/trade, gated   : {len(pos_gate):3d} of {len(prior)}")
    print(f"  with 120 draws centred near zero, roughly half would be positive by chance;")
    print(f"  {len(pos_base)} and {len(pos_gate)} are FEWER than chance would give.")

    print("\n--- STEP 2: does any of it survive the multiplicity bar? " + "-" * 45)
    print(f"  {'symbol':7} {'strategy':32} {'variant':8} {'$/trade':>9} {'net $':>10} "
          f"{'t':>7}  verdict")
    survivors = []
    for _, r in prior.iterrows():
        for variant, pt, net, t in (("ungated", r.base_per_trade, r.base_net, r.base_t),
                                    ("gated", r.gated_per_trade, r.gated_net, r.gated_t)):
            if pt <= 0:
                continue
            ok = abs(t) > t_bar and net > 0
            if ok:
                survivors.append((r.symbol, r.strategy, variant, pt, net, t))
            if net > 3000:      # only print the economically interesting ones
                print(f"  {r.symbol:7} {r.strategy[:32]:32} {variant:8} {pt:9.2f} "
                      f"{net:10.0f} {t:7.2f}  "
                      f"{'SURVIVES' if ok else 'does not clear the bar'}")
    print(f"\n  cells clearing |t| > {t_bar:.2f} with positive net: {len(survivors)}")

    if not survivors:
        print("\n" + "=" * 104)
        print("STEPS 3 AND 4 ARE NOT RUN")
        print("=" * 104)
        print("  No mechanism has expectancy that survives the multiplicity bar for the grid")
        print("  it was selected from. Charging slippage would only lower these numbers, and")
        print("  running a Combine simulation would produce a pass rate for a strategy with")
        print("  no established edge - a number that would get quoted out of context.")
        print("\n  The honest statement is: the best-looking cells in a 120-cell grid are")
        print("  what a 120-cell grid produces when there is nothing there.")

    print("\n" + "=" * 104)
    print("FOR SCALE: what the best-looking cell would need to be true")
    print("=" * 104)
    best = prior.loc[prior.gated_net.idxmax()]
    print(f"  best gated net in the grid: {best.symbol} {best.strategy}")
    print(f"    net ${best.gated_net:,.0f} over {int(best.gated_trades)} trades "
          f"on {int(best.gate_on)} sessions, t = {best.gated_t:.2f}")
    print(f"    its ungated twin: ${best.base_net:,.0f} over {int(best.base_trades)} trades, "
          f"t = {best.base_t:.2f}")
    print(f"    the gate {'HELPED' if best.gated_per_trade > best.base_per_trade else 'HURT'} "
          f"per-trade expectancy "
          f"({best.base_per_trade:+.2f} -> {best.gated_per_trade:+.2f})")
    print(f"    control percentile: {best.ctrl_pt_pctile:.0%} "
          f"({'beats' if best.ctrl_pt_pctile > 0.95 else 'does not beat'} its matched random "
          f"gate)")

    # ---- slippage sensitivity on the whole grid, which is cheap and informative ----------
    print("\n" + "=" * 104)
    print("STEP 3 ANYWAY: how much slippage would erase the grid's positive cells?")
    print("=" * 104)
    print("  Re-priced at one tick of round-turn slippage on top of commission.")
    rows = []
    for symbol in ["ES", "NQ", "MES", "MNQ"]:
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
        evaluable, gate_hi, _ = build_gate(panel, symbol, dates, 0.5)
        sub = prior[(prior.symbol == symbol)
                    & ((prior.base_per_trade > 0) | (prior.gated_per_trade > 0))]
        for _, r in sub.iterrows():
            s = strategies.get(r.strategy)
            if s is None:
                continue
            for variant, mask in (("ungated", evaluable), ("gated", gate_hi)):
                for slip in (0.0, 1.0):
                    ser = session_series(s, sessions, feats, symbol, 1, mask, slip)
                    pnl = np.array([p[-1] if len(p) else 0.0 for _, p, _ in ser])
                    tr = sum(t for _, _, t in ser)
                    rows.append({"symbol": symbol, "strategy": r.strategy,
                                 "variant": variant, "slip_ticks": slip,
                                 "net": float(pnl.sum()), "trades": int(round(tr)),
                                 "per_trade": float(pnl.sum() / tr) if tr else np.nan})
    sl = pd.DataFrame(rows)
    sl.to_csv(REPO / "research" / "opportunity_economics.csv", index=False)
    if len(sl):
        piv = sl.pivot_table(index=["symbol", "strategy", "variant"],
                             columns="slip_ticks", values="per_trade")
        piv.columns = ["no_slip", "one_tick"]
        piv = piv.dropna().sort_values("no_slip", ascending=False)
        print(f"\n  {'symbol':7} {'strategy':32} {'variant':8} {'$/tr no slip':>13} "
              f"{'$/tr 1 tick':>12}  survives?")
        for (sym, strat, var), row in piv.head(20).iterrows():
            print(f"  {sym:7} {strat[:32]:32} {var:8} {row.no_slip:13.2f} "
                  f"{row.one_tick:12.2f}  {'yes' if row.one_tick > 0 else 'NO'}")
        n_pos_0 = int((piv.no_slip > 0).sum())
        n_pos_1 = int((piv.one_tick > 0).sum())
        print(f"\n  positive at zero slippage : {n_pos_0} of {len(piv)}")
        print(f"  positive at one tick      : {n_pos_1} of {len(piv)}")
        print(f"  one tick of slippage erases {n_pos_0 - n_pos_1} of the {n_pos_0} "
              f"positive cells.")
    print(f"\nwrote {REPO / 'research' / 'opportunity_economics.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
