"""The control that decides whether the gate has SKILL or is merely selecting bigger days.

WHAT SURVIVED, AND WHY IT IS NOT YET BELIEVED
-----------------------------------------------
Gating the tournament mechanisms on the opportunity forecast beat a regime-matched random
control in 24 of 120 cells, against 6 expected by chance. Nineteen of the twenty-four are in
the trend family. That is the first positive signal in this research programme, and the whole
programme's credibility depends on it being attacked properly rather than celebrated.

THE CONFOUND
------------
Dollars per trade is not scale-neutral. The gate selects sessions with high forecast
volatility, and a high-volatility session has larger moves. Any mechanism whose per-trade
outcome scales with the size of the move will therefore post a different per-trade number on
gated sessions for a reason that has nothing to do with the gate knowing anything.

The direction of that bias is not obvious a priori, which is exactly why it must be measured
rather than reasoned about. A losing mechanism on a bigger day could lose more (adverse
capture scales) or lose less (fixed round-turn cost is amortised against a bigger move). The
measured result was "loses less", and both stories predict that under some conditions.

THE TEST
--------
Re-run the identical comparison with every session's profit and loss divided by that
session's own dollar range. In those units a session where the mechanism captured a tenth of
the available movement scores the same whether the day was wide or narrow, so pure scale
cancels and only skill survives.

    If the gate still beats its matched control in normalised units, it is selecting sessions
    the mechanism handles BETTER, which is real conditional information.

    If the advantage disappears, the gate is selecting sessions that are merely BIGGER, and
    the per-trade improvement was an accounting artefact of the denominator.

The same regime-matched random controls are used, so the only thing that changes between this
module and Phase 3 is the unit of account.

A SECOND DIAGNOSTIC
-------------------
Capture share - gross profit and loss divided by the total movement available in the session -
is reported alongside. It answers the same question from the other side: does the mechanism
convert a larger fraction of the day's movement into profit on gated sessions? That number is
scale-free by construction and needs no control to be interpretable.
"""
from __future__ import annotations

import argparse
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
from opportunity_gating import (FAMILY_KIND, build_gate,          # noqa: E402
                                matched_random_gates)
from strategy_tournament import build_strategies, calibrate       # noqa: E402

MIN_TRADES = 20


def run_normalised(strategy, sessions, feats, symbol: str, contracts: int,
                   mask: np.ndarray, denom: np.ndarray) -> dict:
    """Per-trade profit in raw dollars AND in units of the session's own dollar range.

    `denom[i]` is session i's high-low range in dollars at this contract count. Dividing each
    session's profit by it makes a wide day and a narrow day directly comparable, which is
    the entire point of the module.
    """
    spec = inst.get(symbol).spec
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(symbol), symbol=symbol)
    tick_cost = sim.round_turn_cost(contracts)

    raw, norm, trades, gross, avail = 0.0, 0.0, 0.0, 0.0, 0.0
    for i, (g, X) in enumerate(zip(sessions, feats, strict=True)):
        if not mask[i]:
            continue
        pos = np.nan_to_num(np.asarray(strategy.signal(X), dtype=float), nan=0.0)
        c = g["c"].to_numpy(dtype=float)
        net_path, turns, sg = fd.session_accounting(
            pos, c, multiplier=spec.multiplier, contracts=contracts,
            round_turn_cost=tick_cost)
        pnl = float(net_path[-1]) if len(net_path) else 0.0
        raw += pnl
        if denom[i] > 0:
            norm += pnl / denom[i]
        trades += turns
        gross += sg
        # total movement actually available in the session, for the capture share
        avail += float(np.abs(np.diff(c)).sum()) * spec.multiplier * contracts
    if trades < 1:
        return {"trades": 0, "per_trade": np.nan, "per_trade_norm": np.nan,
                "capture": np.nan, "net": raw}
    return {"trades": int(round(trades)), "per_trade": raw / trades,
            "per_trade_norm": norm / trades, "capture": gross / avail if avail else np.nan,
            "net": raw}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["ES", "NQ", "MES", "MNQ"])
    ap.add_argument("--contracts", type=int, default=1)
    ap.add_argument("--quantile", type=float, default=0.5)
    ap.add_argument("--controls", type=int, default=40)
    ap.add_argument("--only-winners", action="store_true",
                    help="restrict to the cells that beat the control in Phase 3")
    ap.add_argument("--out", type=Path,
                    default=REPO / "research" / "gating_scale_control.csv")
    args = ap.parse_args()

    panel = pd.read_parquet(REPO / "research" / "opportunity_panel.parquet")
    prior = pd.read_csv(REPO / "research" / "opportunity_gating.csv")
    winners = set(zip(prior[prior.ctrl_pt_pctile > 0.95].symbol,
                      prior[prior.ctrl_pt_pctile > 0.95].strategy))
    rng = np.random.default_rng(90210)
    rows = []

    print("=" * 112)
    print("SCALE CONTROL - the same gate, scored in units of the session's own range")
    print(f"{args.controls} regime-matched random gates per mechanism")
    print("=" * 112)

    for symbol in args.symbols:
        store = REPO / "data" / "futures" / f"{symbol}.parquet"
        if not store.exists():
            continue
        df = fd.load(store, symbol)
        sessions = fd.session_frames(df)
        if not sessions:
            continue
        feats = fd.build_features(sessions, fe.library())
        dates = [g["day"].iloc[0] for g in sessions]
        spec = inst.get(symbol).spec
        denom = np.array([
            (float(g["h"].max()) - float(g["l"].min())) * spec.multiplier * args.contracts
            for g in sessions])

        cal = calibrate(feats[:len(sessions) // 2], symbol)
        strategies = build_strategies(cal)
        evaluable, gate_hi, regime = build_gate(panel, symbol, dates, args.quantile)
        controls = matched_random_gates(gate_hi, evaluable, regime, args.controls, rng)

        print(f"\n{symbol}: {int(evaluable.sum())} evaluable, gate ON {int(gate_hi.sum())}")
        print(f"  {'mechanism':32} {'kind':10} {'base/tr':>9} {'gate/tr':>9} "
              f"{'base norm':>10} {'gate norm':>10} {'ctrl p50':>10} {'pctile':>7} "
              f"{'base cap':>9} {'gate cap':>9}")

        for s in strategies:
            if args.only_winners and (symbol, s.name) not in winners:
                continue
            base = run_normalised(s, sessions, feats, symbol, args.contracts,
                                  evaluable, denom)
            hi = run_normalised(s, sessions, feats, symbol, args.contracts, gate_hi, denom)
            if base["trades"] < MIN_TRADES or hi["trades"] < MIN_TRADES:
                continue
            cvals = np.array([
                run_normalised(s, sessions, feats, symbol, args.contracts,
                               m, denom)["per_trade_norm"]
                for m in controls])
            cvals = cvals[np.isfinite(cvals)]
            pct = float((cvals < hi["per_trade_norm"]).mean()) if len(cvals) else np.nan
            kind = FAMILY_KIND.get(s.family.split(".")[0], s.family)
            rows.append({
                "symbol": symbol, "strategy": s.name, "kind": kind,
                "base_per_trade": base["per_trade"], "gated_per_trade": hi["per_trade"],
                "base_per_trade_norm": base["per_trade_norm"],
                "gated_per_trade_norm": hi["per_trade_norm"],
                "base_capture": base["capture"], "gated_capture": hi["capture"],
                "ctrl_norm_p50": float(np.median(cvals)) if len(cvals) else np.nan,
                "ctrl_norm_p95": float(np.percentile(cvals, 95)) if len(cvals) else np.nan,
                "ctrl_norm_pctile": pct,
                "was_phase3_winner": (symbol, s.name) in winners,
            })
            print(f"  {s.name[:32]:32} {kind:10} {base['per_trade']:9.2f} "
                  f"{hi['per_trade']:9.2f} {base['per_trade_norm']:10.4f} "
                  f"{hi['per_trade_norm']:10.4f} "
                  f"{np.median(cvals) if len(cvals) else float('nan'):10.4f} {pct:7.1%} "
                  f"{base['capture']:9.4f} {hi['capture']:9.4f}")

    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)

    print("\n" + "=" * 112)
    print("VERDICT")
    print("=" * 112)
    if len(out):
        w = out[out.was_phase3_winner]
        print(f"  cells re-tested                                  {len(out)}")
        print(f"  of which beat the control on RAW $/trade (Ph 3)  {int(out.was_phase3_winner.sum())}")
        print(f"  beating the control on NORMALISED $/trade        "
              f"{int((out.ctrl_norm_pctile > 0.95).sum())}  "
              f"(expected by chance {len(out) * 0.05:.1f})")
        if len(w):
            print(f"\n  the Phase 3 winners, re-scored in normalised units:")
            print(f"    still beating control p95: "
                  f"{int((w.ctrl_norm_pctile > 0.95).sum())} of {len(w)}")
            print(f"    median normalised delta:   "
                  f"{(w.gated_per_trade_norm - w.base_per_trade_norm).median():+.5f}")
            print(f"    median capture-share delta: "
                  f"{(w.gated_capture - w.base_capture).median():+.5f}")
        print(f"\n  ALL cells: median raw $/trade delta        "
              f"{(out.gated_per_trade - out.base_per_trade).median():+.3f}")
        print(f"             median normalised delta         "
              f"{(out.gated_per_trade_norm - out.base_per_trade_norm).median():+.5f}")
        print(f"             median capture-share delta      "
              f"{(out.gated_capture - out.base_capture).median():+.5f}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
