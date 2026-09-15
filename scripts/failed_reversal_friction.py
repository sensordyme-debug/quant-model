"""Phase 7 (mandatory friction gate), Phase 10 (not run, and why), and the plots.

THE FRICTION GATE IS MANDATORY AND IT USES THE REPOSITORY'S OWN FEE MODEL
---------------------------------------------------------------------------
Not a generic transaction cost: `quant_brain.markets.futures_cme.execution_sim.CostModel`,
which carries the published Topstep round-turn commissions already documented in this
repository. Slippage is added on top at 0, 0.25, 0.5, 1 and 2 ticks of the ROUND TURN.

The Phase 16 finding to verify: on MNQ, roughly one tick of slippage eliminates the
out-of-sample expectancy.

PHASE 10 IS NOT RUN, DELIBERATELY
-----------------------------------
The brief gates the Combine digital twin on the replication evidence being "positive enough to
justify this section". It is not:

    QQQ over the EXACT futures dates (2025-06..2026-09) has the OPPOSITE sign to MNQ
    at 1, 3 and 5 bars, on a comparable number of entries (451 vs 343), on the SAME index.

    QQQ over its clean 2016-2023 holdout is also negative.

    Across ~44 instrument-years only 2 classify as REPLICATES, which is what chance gives.

Running a Combine simulation on a rejected hypothesis would produce a pass rate, and a pass
rate in a document gets quoted. The section is skipped and the reason is recorded, which is
what the brief asks for.

The one Topstep-relevant number that IS reported here is the barrier ratio, because it costs
nothing and it is descriptive rather than promotional.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402
import pandas as pd               # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from failed_reversal_replication import (HORIZONS, TRAIN_FRACTION, build,  # noqa: E402
                                         calibrate_thresholds, collect,
                                         etf_sessions, futures_sessions)
from failed_reversal_spec import rule_hash  # noqa: E402
from quant_brain.markets.futures_cme import execution_sim as ex   # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst   # noqa: E402

OUT = REPO / "docs" / "research" / "strategy_results" / "failed_reversal_replication"
SLIP = (0.0, 0.25, 0.5, 1.0, 2.0)
ETF_MULT, ETF_TICK, ETF_COMM = 100.0, 1.0, 1.00
plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False})


def costs_for(sym: str, panel: str) -> tuple[float, float]:
    """(round-turn commission, tick value) from the repository's own model."""
    if panel == "futures":
        spec = inst.get(sym).spec
        sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(sym), symbol=sym)
        return sim.round_turn_cost(1), spec.tick_value
    return ETF_COMM, ETF_TICK


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 108)
    print(f"PHASE 7 - ECONOMIC FRICTION GATE   rule hash {rule_hash()}")
    print("using the repository's own Topstep fee model, not generic costs")
    print("=" * 108)

    data = {}
    for panel, syms, loader, mult in (("futures", ("MNQ", "NQ", "MES", "ES"),
                                       futures_sessions, None),
                                      ("etf", ("SPY", "QQQ", "IWM", "DIA"),
                                       etf_sessions, ETF_MULT)):
        for sym in syms:
            sess = loader(sym)
            feats = build(sess)
            hi, lo = calibrate_thresholds(feats, int(len(sess) * TRAIN_FRACTION))
            m = mult if mult else inst.get(sym).spec.multiplier
            recs, _ = collect(sess, feats, hi, lo, m)
            data[(panel, sym)] = recs

    rows = []
    print(f"\n  {'panel':8} {'sym':5} {'n':>6} {'gross $/tr':>11} "
          + "".join(f"{str(s) + 't':>9} " for s in SLIP) + " classification")
    for (panel, sym), recs in data.items():
        if not len(recs):
            continue
        gross = float(recs["fwd_1"].mean())
        comm, tick = costs_for(sym, panel)
        nets = [gross - comm - s * tick for s in SLIP]
        cls = ("ROBUST AFTER COSTS" if nets[3] > 0.5 * abs(gross) and nets[3] > 0
               else "MARGINAL AFTER COSTS" if nets[3] > 0
               else "ZERO AFTER COSTS" if abs(nets[3]) < 0.02 * max(1e-9, abs(gross))
               else "NEGATIVE AFTER COSTS")
        rows.append({"panel": panel, "symbol": sym, "entries": len(recs), "gross": gross,
                     "commission": comm, "tick": tick,
                     **{f"net_{s}t": n for s, n in zip(SLIP, nets, strict=True)},
                     "classification": cls})
        print(f"  {panel:8} {sym:5} {len(recs):6d} {gross:11.3f} "
              + "".join(f"{n:9.3f} " for n in nets) + f" {cls}")
    fr = pd.DataFrame(rows)
    fr.to_csv(REPO / "research" / "fr_replication_friction.csv", index=False)

    m = fr[(fr.panel == "futures") & (fr.symbol == "MNQ")].iloc[0]
    print(f"\n  MNQ verification of the Phase 16 finding:")
    print(f"    gross $/trade at 1 bar        {m.gross:+.3f}")
    print(f"    commission (repo fee model)   {m.commission:.2f}")
    print(f"    one tick                      {m.tick:.2f}")
    print(f"    net at 1 tick                 {m['net_1.0t']:+.3f}")
    be = (m.gross - m.commission) / m.tick if m.tick else np.nan
    print(f"    break-even slippage           {be:.2f} ticks")
    print(f"    => the Phase 16 finding is {'CONFIRMED' if 0.5 < be < 5 else 'NOT confirmed'}"
          f" on the full sample")

    print("\n" + "=" * 108)
    print("PHASE 10 - COMBINE FEASIBILITY: NOT RUN")
    print("=" * 108)
    print("  The brief gates this section on replication evidence being positive enough.")
    print("  It is not. QQQ - the same index as MNQ - has the OPPOSITE sign over the exact")
    print("  same dates, and is negative over its clean 2016-2023 holdout. Simulating a")
    print("  Combine on a rejected hypothesis produces a pass rate that would get quoted.")
    print("\n  The one descriptive number worth recording:")
    fut = data[("futures", "MNQ")]
    daily = fut.groupby("session")["fwd_1"].sum()
    eq = np.cumsum(daily.to_numpy())
    dd = float((eq - np.maximum.accumulate(eq)).min())
    print(f"    MNQ 1-contract gross max drawdown  ${dd:,.0f}")
    print(f"    Topstep trailing MLL               $2,000")
    print(f"    ratio                              {abs(dd) / 2000:.2f}x")

    # ------------------------------- plots -------------------------------------------------
    print("\n" + "=" * 108)
    print("PLOTS")
    print("=" * 108)
    inst_df = pd.read_csv(REPO / "research" / "fr_replication_instruments.csv")
    era = pd.read_csv(REPO / "research" / "fr_replication_eras.csv")
    per = pd.read_csv(REPO / "research" / "fr_replication_periods.csv")
    reg = pd.read_csv(REPO / "research" / "fr_replication_regimes.csv")

    # 1. effect vs horizon, normalised so instruments are comparable
    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    for _, r in inst_df.iterrows():
        v = np.array([r[f"mean_{n}"] for n in HORIZONS], dtype=float)
        sd = np.nanstd(v) or 1.0
        ax.plot(HORIZONS, v / abs(r["mean_1"]) if r["mean_1"] else v,
                marker="o", lw=1.3,
                label=f"{r['symbol']} ({r['panel']})",
                ls="-" if r["panel"] == "futures" else "--")
    ax.axhline(0, color="black", lw=0.9)
    ax.set_xlabel("horizon, bars"); ax.set_ylabel("effect, scaled to its own 1-bar value")
    ax.set_title("Effect size vs horizon — the claimed 1→3→5 rise decaying by 10\n"
                 "solid = futures (2025-26), dashed = ETF (2016-26)", fontsize=10)
    ax.legend(fontsize=7, ncol=2, frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "01_effect_vs_horizon.png"); plt.close(fig)

    # 2. treatment vs matched control
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    y = np.arange(len(inst_df))
    ax.barh(y - 0.2, inst_df["mean_1"], height=0.38, label="treatment", color="#2b6cb0")
    ax.barh(y + 0.2, inst_df["ctrl_1"], height=0.38, label="matched control", color="#a0aec0")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r.symbol} ({r.panel})" for _, r in inst_df.iterrows()])
    ax.axvline(0, color="black", lw=0.9)
    ax.set_xlabel("mean signed 1-bar forward return, $ per unit")
    ax.set_title("Treatment vs bar-of-session-and-direction-matched control", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "02_treatment_vs_control.png"); plt.close(fig)

    # 3. cross-instrument percentile
    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    cols = ["#22543d" if p > 0.95 else "#9b2c2c" if p < 0.05 else "#a0aec0"
            for p in inst_df["ctrl_pctile_1"]]
    ax.bar(range(len(inst_df)), inst_df["ctrl_pctile_1"], color=cols)
    ax.axhline(0.95, color="#22543d", ls="--", lw=1)
    ax.axhline(0.05, color="#9b2c2c", ls="--", lw=1)
    ax.set_xticks(range(len(inst_df)))
    ax.set_xticklabels([f"{r.symbol}\n{r.panel}" for _, r in inst_df.iterrows()], fontsize=8)
    ax.set_ylabel("percentile vs matched control, 1 bar")
    ax.set_title("Cross-instrument replication: green clears the control, red is inverted",
                 fontsize=10)
    fig.tight_layout(); fig.savefig(OUT / "03_cross_instrument.png"); plt.close(fig)

    # 4. historical period
    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    p = per[per.entries >= 100].copy()
    p["year"] = pd.to_numeric(p["period"], errors="coerce")
    for sym, g in p.dropna(subset=["year"]).groupby("symbol"):
        ax.plot(g.year, g.mean_1, marker="o", lw=1.2, label=sym)
    ax.axhline(0, color="black", lw=0.9)
    ax.axvspan(2025, 2026.7, color="#fed7d7", alpha=0.5)
    ax.text(2025.05, ax.get_ylim()[1] * 0.85, "futures era\n(contaminated)", fontsize=7.5,
            color="#9b2c2c")
    ax.set_xlabel("calendar year"); ax.set_ylabel("mean 1-bar forward return, $")
    ax.set_title("Historical-period replication, ETF panel (futures 2018-2024 do not exist)",
                 fontsize=10)
    ax.legend(fontsize=8, frameon=False, ncol=4)
    fig.tight_layout(); fig.savefig(OUT / "04_period_replication.png"); plt.close(fig)

    # 5. cost ladder
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    for _, r in fr.iterrows():
        ax.plot(SLIP, [r[f"net_{s}t"] for s in SLIP], marker="o", lw=1.2,
                label=f"{r.symbol} ({r.panel})",
                ls="-" if r.panel == "futures" else "--")
    ax.axhline(0, color="crimson", lw=1.3)
    ax.set_xlabel("round-turn slippage, ticks"); ax.set_ylabel("net $/trade")
    ax.set_title("Cost / slippage expectancy ladder, repository fee model", fontsize=10)
    ax.legend(fontsize=7, ncol=2, frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "05_cost_ladder.png"); plt.close(fig)

    # 6. regime
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    order = ["LOW", "MID", "HIGH"]
    w = 0.1
    for i, (sym, g) in enumerate(reg.groupby("symbol")):
        g = g.set_index("regime").reindex(order)
        ax.bar(np.arange(3) + i * w - 0.35, g.mean_1.fillna(0), width=w, label=sym)
    ax.axhline(0, color="black", lw=0.9)
    ax.set_xticks(range(3)); ax.set_xticklabels(order)
    ax.set_ylabel("mean 1-bar forward return, $")
    ax.set_title("Volatility-regime comparison (descriptive; no filter introduced)",
                 fontsize=10)
    ax.legend(fontsize=7, ncol=4, frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "06_regime.png"); plt.close(fig)

    # 7. the decisive era chart
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    e = era[era.symbol.isin(["QQQ", "MNQ", "NQ", "SPY", "ES", "MES"])].copy()
    e["key"] = e.symbol + "\n" + e.period.str.replace(r"\s*\(.*\)", "", regex=True)
    cols = ["#22543d" if v > 0 else "#9b2c2c" for v in e.mean_1]
    ax.bar(range(len(e)), e.mean_1, color=cols)
    ax.axhline(0, color="black", lw=0.9)
    ax.set_xticks(range(len(e)))
    ax.set_xticklabels(e.key, fontsize=6.5, rotation=30, ha="right")
    ax.set_ylabel("mean 1-bar forward return, $")
    ax.set_title("The decisive test: QQQ and MNQ track the SAME index over the same dates",
                 fontsize=10)
    fig.tight_layout(); fig.savefig(OUT / "07_decisive_era.png"); plt.close(fig)

    for pth in sorted(OUT.glob("*.png")):
        print(f"  wrote {pth.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
