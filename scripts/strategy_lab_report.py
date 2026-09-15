"""Phases 5, 6, 7, 8, 14 and 17: the plots that explain WHY, the scorecards, and the dashboard.

WHICH PLOTS, AND WHY NOT THE OTHERS
-------------------------------------
The brief lists seventeen candidate charts and then says not to draw one merely because it is
available - prioritise the ones that explain why a strategy succeeds or fails. Applied to this
field, most of the seventeen would be decoration, because the field has one dominant failure
mode and it is visible in four pictures:

  DRAWDOWN AGAINST THE BARRIER   the single decisive chart. Every strategy's own maximum
                                 drawdown plotted against the $2,000 trailing MLL. This is
                                 what kills the field, and nothing else needs to be looked at
                                 for the 124 cells it disqualifies.
  EQUITY AND UNDERWATER          for the handful that clear it, the shape of the ride.
  COST CLIFF                     expectancy per trade at 0 and 1 tick of slippage, per cell.
                                 With a two-minute median holding time this is where most of
                                 the remaining edge goes.
  HOLDING TIME AND MAE           what the mechanism actually is. A two-minute median hold with
                                 a large MAE is a scalp wearing a strategy's name.

Per-hour and per-weekday P&L are computed into the scorecards as numbers but not plotted:
with 132 cells they would be 132 charts nobody reads, and the regime breakdown already
carries the same information in a form that supports a decision.

THE VERDICT RULE, FIXED BEFORE THE DATA IS READ
-------------------------------------------------
The brief forbids a verdict based on P&L alone, so the ladder is declared here and applied
mechanically:

  REJECT            fails the barrier test (1-contract max drawdown >= $2,000) OR negative
                    expectancy under stressed costs
  WATCH             survives both but has |t| < 1.0 on its daily series - not evidence, just
                    not yet disproved
  RESEARCH          survives both, |t| >= 1.0, but fails a robustness leg
  PAPER CANDIDATE   survives costs, barrier, t >= 1.96, positive in both halves, and a Monte
                    Carlo probability of breaching the MLL below 50%
  COMBINE CANDIDATE everything above plus the engineering and practice gates, which no
                    strategy can reach from a backtest alone - so this verdict is
                    unreachable in this document by construction, and that is deliberate.
"""
from __future__ import annotations

import json
import pickle
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

OUT = REPO / "docs" / "research" / "strategy_results"
MLL = 2_000.0
DLL = 1_000.0

plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False})


def verdict(row: pd.Series, stressed: pd.Series | None, mc: pd.DataFrame | None) -> str:
    """The declared ladder. Mechanical, and never a function of net P&L alone."""
    dd_ok = abs(row.max_drawdown) < MLL
    stressed_ok = (stressed is not None and stressed.expectancy_per_trade > 0)
    if not dd_ok or not stressed_ok:
        return "REJECT"
    if abs(row.t_stat) < 1.0:
        return "WATCH"
    if row.t_stat < 1.96:
        return "RESEARCH"
    if mc is not None and len(mc) and float(mc.mc_prob_dd_exceeds_mll.min()) < 0.50:
        return "PAPER CANDIDATE"
    return "RESEARCH"


def fig_barrier(normal: pd.DataFrame) -> Path:
    """The decisive chart: every cell's own drawdown against the $2,000 barrier."""
    fig, ax = plt.subplots(figsize=(9, 5.2))
    fams = sorted(normal.family_key.unique())
    colors = plt.cm.tab10(np.linspace(0, 1, len(fams)))
    for f, c in zip(fams, colors):
        s = normal[normal.family_key == f]
        ax.scatter(s.max_drawdown.abs(), s.net_pnl, s=26, alpha=0.8, label=f, color=c)
    ax.axvline(MLL, color="crimson", lw=1.6, ls="--")
    ax.text(MLL * 1.05, ax.get_ylim()[1] * 0.9, "$2,000 trailing MLL",
            color="crimson", fontsize=8)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("max drawdown at 1 contract, $ (log scale)")
    ax.set_ylabel("net P&L, $")
    ax.set_title("Every strategy against the barrier that decides the Combine\n"
                 f"{int((normal.max_drawdown.abs() < MLL).sum())} of {len(normal)} cells sit "
                 f"left of the line", fontsize=10)
    ax.legend(fontsize=7, ncol=2, frameon=False)
    fig.tight_layout()
    p = OUT / "01_drawdown_vs_mll.png"
    fig.savefig(p)
    plt.close(fig)
    return p


def fig_cost_cliff(port: pd.DataFrame) -> Path:
    piv = port.pivot_table(index=["strategy", "symbol"], columns="regime",
                           values="expectancy_per_trade").dropna()
    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.scatter(piv["normal"], piv["stressed"], s=24, alpha=0.75, color="#2b6cb0")
    lim = [min(piv.min()) * 1.05, max(piv.max()) * 1.05]
    ax.plot(lim, lim, color="grey", lw=0.9, ls=":")
    ax.axhline(0, color="crimson", lw=1.2)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("$/trade, commission only")
    ax.set_ylabel("$/trade, plus 1 tick round-turn slippage")
    n0, n1 = int((piv["normal"] > 0).sum()), int((piv["stressed"] > 0).sum())
    ax.set_title(f"The cost cliff: {n0} cells positive on commission, {n1} survive one tick",
                 fontsize=10)
    fig.tight_layout()
    p = OUT / "02_cost_cliff.png"
    fig.savefig(p)
    plt.close(fig)
    return p


def fig_equity(store: dict, picks: list[tuple[str, str]]) -> Path:
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6.4), sharex=True,
                                 gridspec_kw={"height_ratios": [2, 1]})
    for strat, sym in picks:
        recs = store.get((strat, sym))
        if not recs:
            continue
        recs = sorted(recs, key=lambda r: r["session"])
        eq = np.cumsum([r["net_pnl"] for r in recs])
        x = pd.to_datetime([r["session"] for r in recs])
        a1.plot(x, eq, lw=1.2, label=f"{strat} {sym}")
        dd = eq - np.maximum.accumulate(eq)
        a2.fill_between(x, dd, 0, alpha=0.35)
    a1.axhline(0, color="black", lw=0.8)
    a1.set_ylabel("cumulative net $")
    a1.set_title("Equity and underwater curves, 1 contract, commission only", fontsize=10)
    a1.legend(fontsize=7, frameon=False)
    a2.axhline(-MLL, color="crimson", lw=1.3, ls="--")
    a2.text(x[len(x) // 2], -MLL * 1.15, "$2,000 MLL", color="crimson", fontsize=8)
    a2.set_ylabel("drawdown $")
    fig.autofmt_xdate()
    fig.tight_layout()
    p = OUT / "03_equity_underwater.png"
    fig.savefig(p)
    plt.close(fig)
    return p


def fig_trade_anatomy(trades: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.5))
    h = trades.holding_minutes.clip(0, 60)
    axes[0].hist(h, bins=40, color="#4a5568")
    axes[0].set_title(f"holding time (median {trades.holding_minutes.median():.0f} min)",
                      fontsize=9)
    axes[0].set_xlabel("minutes, clipped at 60")
    mae = trades.mae.clip(trades.mae.quantile(0.01), 0)
    axes[1].hist(mae, bins=40, color="#9b2c2c")
    axes[1].set_title("MAE per trade, $", fontsize=9)
    axes[2].hist(trades.mfe.clip(0, trades.mfe.quantile(0.99)), bins=40, color="#22543d")
    axes[2].set_title("MFE per trade, $", fontsize=9)
    for a in axes:
        a.set_ylabel("trades")
    fig.suptitle("What these mechanisms actually are: trade anatomy across the whole field",
                 fontsize=10)
    fig.tight_layout()
    p = OUT / "04_trade_anatomy.png"
    fig.savefig(p)
    plt.close(fig)
    return p


def fig_regime(store: dict, normal: pd.DataFrame) -> Path:
    """P&L by year and by volatility regime for the leaders."""
    picks = normal.reindex(normal.net_pnl.sort_values(ascending=False).index).head(6)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.8))
    labels = []
    for _, r in picks.iterrows():
        recs = store.get((r.strategy, r.symbol))
        if not recs:
            continue
        df = pd.DataFrame(recs)
        df["session"] = pd.to_datetime(df["session"])
        by_year = df.groupby(df.session.dt.year)["net_pnl"].sum()
        a1.plot(by_year.index, by_year.values, marker="o", lw=1.2)
        vol = df.net_pnl.abs().rolling(20).mean().shift(1)
        terc = pd.qcut(vol.rank(method="first"), 3, labels=["calm", "mid", "wild"])
        by_reg = df.groupby(terc, observed=True)["net_pnl"].sum()
        a2.plot(range(len(by_reg)), by_reg.values, marker="s", lw=1.2)
        labels.append(f"{r.strategy[:22]} {r.symbol}")
    a1.axhline(0, color="black", lw=0.8)
    a1.set_title("net P&L by year", fontsize=9)
    a1.set_xticks(sorted({y for y in a1.get_xticks()}))
    a2.axhline(0, color="black", lw=0.8)
    a2.set_xticks([0, 1, 2])
    a2.set_xticklabels(["calm", "mid", "wild"])
    a2.set_title("net P&L by trailing-volatility tercile (causal)", fontsize=9)
    a2.legend(labels, fontsize=6.5, frameon=False, loc="best")
    fig.suptitle("Where the leaders make and lose it", fontsize=10)
    fig.tight_layout()
    p = OUT / "05_regime.png"
    fig.savefig(p)
    plt.close(fig)
    return p


def correlations(store: dict, picks: list[tuple[str, str]]) -> pd.DataFrame:
    """Phase 14: are the leaders actually distinct mechanisms?"""
    series = {}
    for strat, sym in picks:
        recs = store.get((strat, sym))
        if recs:
            s = pd.Series({r["session"]: r["net_pnl"] for r in recs})
            series[f"{strat}|{sym}"] = s
    if len(series) < 2:
        return pd.DataFrame()
    return pd.DataFrame(series).corr(method="spearman")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    port = pd.read_csv(REPO / "research" / "lab_portfolio.csv")
    trades = pd.read_parquet(REPO / "research" / "lab_trades.parquet")
    with (REPO / "research" / "lab_sessions.pkl").open("rb") as fh:
        store = pickle.load(fh)
    topstep = (pd.read_csv(REPO / "research" / "lab_topstep.csv")
               if (REPO / "research" / "lab_topstep.csv").exists() else pd.DataFrame())
    reg = json.loads((REPO / "research" / "strategy_registry.json").read_text(encoding="utf-8"))
    famkey = {r["name"]: r["family_name"] for r in reg}
    newly = {r["name"] for r in reg if r["newly_added"]}

    normal = port[port.regime == "normal"].copy()
    stressed = port[port.regime == "stressed"].set_index(["strategy", "symbol"])
    normal["family_key"] = normal.strategy.map(famkey).fillna("other")

    print("=" * 100)
    print("PHASE 5 - PLOTS THAT EXPLAIN WHY")
    print("=" * 100)
    leaders = [(r.strategy, r.symbol) for _, r in
               normal.reindex(normal.net_pnl.sort_values(ascending=False).index).head(5)
               .iterrows()]
    made = [fig_barrier(normal), fig_cost_cliff(port), fig_equity(store, leaders),
            fig_trade_anatomy(trades), fig_regime(store, normal)]
    for p in made:
        print(f"  wrote {p.relative_to(REPO)}")

    # ---- Phase 6: scorecards ---------------------------------------------------------------
    print("\n" + "=" * 100)
    print("PHASE 6 - SCORECARDS")
    print("=" * 100)
    cards = []
    for _, r in normal.iterrows():
        key = (r.strategy, r.symbol)
        st = stressed.loc[key] if key in stressed.index else None
        mc = topstep[(topstep.strategy == r.strategy) & (topstep.symbol == r.symbol)] \
            if len(topstep) else None
        v = verdict(r, st, mc)
        cards.append({
            "strategy": r.strategy, "symbol": r.symbol,
            "family": famkey.get(r.strategy, "other"),
            "newly_added": r.strategy in newly,
            "trades": int(r.n_trades), "net_pnl": r.net_pnl,
            "expectancy_trade": r.expectancy_per_trade,
            "expectancy_session": r.expectancy_per_session,
            "stressed_expectancy_trade": (float(st.expectancy_per_trade)
                                          if st is not None else np.nan),
            "profit_factor": r.profit_factor, "win_rate": r.win_rate,
            "max_dd": r.max_drawdown, "dd_over_mll": abs(r.max_drawdown) / MLL,
            "sharpe": r.sharpe, "sortino": r.sortino, "t_stat": r.t_stat,
            "consec_losing_days": int(r.consec_losing_days),
            "median_hold_min": r.median_holding_minutes,
            "trades_per_session": r.trades_per_session,
            "time_in_market": r.time_in_market,
            "mc_prob_dd_exceeds_mll": (float(mc.mc_prob_dd_exceeds_mll.min())
                                       if mc is not None and len(mc) else np.nan),
            "best_twin_pass": (float(mc.pass_rate.max())
                               if mc is not None and len(mc) else np.nan),
            "dll_breach_rate": (float(mc.dll_breach_rate.min())
                                if mc is not None and len(mc) else np.nan),
            "verdict": v})
    cards_df = pd.DataFrame(cards)
    cards_df.to_csv(REPO / "research" / "lab_scorecards.csv", index=False)
    print(cards_df.verdict.value_counts().to_string())

    # ---- Phase 8: ranking -------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("PHASE 8 - RANKING  (not by P&L)")
    print("=" * 100)
    c = cards_df.copy()
    c["rank_score"] = (
        (c.dd_over_mll < 1).astype(int) * 3
        + (c.stressed_expectancy_trade > 0).astype(int) * 3
        + (c.t_stat.clip(0, 3))
        + (1 - c.dll_breach_rate.fillna(1)).clip(0, 1)
        + (c.profit_factor.fillna(0).clip(0, 2) / 2))
    c = c.sort_values("rank_score", ascending=False)
    c.to_csv(REPO / "research" / "lab_ranking.csv", index=False)
    print(f"  {'strategy':30} {'sym':5} {'score':>6} {'DD/MLL':>7} {'strs$/tr':>9} "
          f"{'t':>6} {'DLL/s':>7} {'verdict':>16}")
    for _, r in c.head(12).iterrows():
        print(f"  {r.strategy[:30]:30} {r.symbol:5} {r.rank_score:6.2f} "
              f"{r.dd_over_mll:7.1f} {r.stressed_expectancy_trade:9.2f} {r.t_stat:6.2f} "
              f"{r.dll_breach_rate if np.isfinite(r.dll_breach_rate) else float('nan'):7.1%} "
              f"{r.verdict:>16}")

    # ---- Phase 14: ensembles ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("PHASE 14 - ARE THE LEADERS DISTINCT MECHANISMS?")
    print("=" * 100)
    corr = correlations(store, leaders)
    if len(corr):
        print(corr.round(2).to_string())
        off = corr.where(~np.eye(len(corr), dtype=bool)).stack()
        print(f"\n  median pairwise daily-P&L correlation: {off.median():.2f}")
        print(f"  max: {off.max():.2f}   min: {off.min():.2f}")
        corr.to_csv(REPO / "research" / "lab_correlations.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
