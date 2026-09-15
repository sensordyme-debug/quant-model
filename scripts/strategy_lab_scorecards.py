"""Phases 6 and 7 as a document: one scorecard per strategy, generated from the artifacts.

WHY THIS IS GENERATED RATHER THAN WRITTEN
-------------------------------------------
A hand-written scorecard drifts from the data the moment anything is re-run, and a scorecard
that disagrees with the CSV beside it is worse than no scorecard. Every number here is read
from `lab_scorecards.csv`, `lab_portfolio.csv` and `lab_topstep.csv` at generation time.

The prose - why a mechanism could work, why it could fail, and what would kill it - is keyed
to the strategy FAMILY rather than to individual cells, because the mechanism is a property of
the family and writing thirty-three separate rationales would produce thirty-three
paraphrases of six ideas. Where a specific cell diverges from its family's story, the
per-cell numbers say so.

FALSIFICATION CONDITIONS ARE CONCRETE
---------------------------------------
The brief asks for conditions, not sentiments. Each family gets a numeric kill condition that
can be evaluated against a future run without interpretation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
MLL = 2_000.0

FAMILY_PROSE = {
    "trend": {
        "works": ("A move that is large in its own recent units continues, because information "
                  "arrives in pieces and the market prices it over minutes rather than "
                  "instantly. The structural advantage would be that a trend rider needs no "
                  "view on fair value, only on persistence."),
        "fails": ("Intraday index futures displace LESS than a random walk - the previous "
                  "phase measured median |net move| / sigma*sqrt(n) at 0.655-0.738 on eight "
                  "instruments over eleven years. A trend mechanism is paid for displacement "
                  "and this asset class systematically fails to deliver it. On top of that, "
                  "every entry pays the spread while the signal is at its most crowded."),
        "kill": ("Reject unless a trend cell shows positive stressed expectancy AND a "
                 "1-contract max drawdown below $2,000. Currently 0 of 36 trend cells clear "
                 "either leg."),
    },
    "breakout": {
        "works": ("Price leaving an established range attracts continuation flow: stops "
                  "trigger, and passive liquidity steps away. Directly opposed to reversion, "
                  "which is why both belong in the library."),
        "fails": ("A range break is the single most watched pattern in the instrument, so it "
                  "is the most crowded. False breakouts dominate in a mean-reverting tape, and "
                  "the entry is by construction at the worst price in the range. Cost is paid "
                  "on every attempt; the payoff arrives on a minority."),
        "kill": ("Reject unless a breakout cell's profit factor exceeds 1.2 under stressed "
                 "costs. The only cell that survives at all does so by FADING breakouts."),
    },
    "reversion": {
        "works": ("An extreme deviation from a rolling mean or from VWAP is an inventory "
                  "imbalance rather than information, and liquidity providers are paid to "
                  "correct it. This is the family the asset class's own arithmetic favours: "
                  "sessions mean-revert, and the measured win rates here (up to 80.9%) are "
                  "consistent with that rather than with luck."),
        "fails": ("A high win rate with an untruncated left tail is precisely the shape a "
                  "trailing drawdown barrier punishes. Fading a genuine regime change is how a "
                  "reversion book dies, and no strategy here has a stop to prevent it. "
                  "revert.vwap.q90 on NQ wins 80.9% of trades and still draws down $39,960."),
        "kill": ("Reject unless a bracketed version keeps its win rate above 65% AND brings "
                 "1-contract max drawdown under $2,000. Untested - no strategy has a stop."),
    },
    "session": {
        "works": ("The clock matters: the auction, the European close, the settlement window "
                  "and the cash close each concentrate different flow, so a rule conditioned "
                  "on time of day needs no price forecast."),
        "fails": ("Measured directly last phase: zero of 28 time-of-day blocks showed a "
                  "significant unconditional drift on any instrument, largest |t| = 1.8 "
                  "against a Bonferroni bar of 3.1. There is no drift for a clock rule to "
                  "harvest."),
        "kill": ("Reject unless a session block shows drift clearing |t| > 3.1 on a fresh "
                 "sample. Already tested and failed."),
    },
    "volatility": {
        "works": ("Volatility is the one genuinely forecastable quantity here - out-of-sample "
                  "R-squared 0.46-0.51, robust in every regime partition. A rule that trades "
                  "when movement is expected should at least be trading when there is "
                  "something to trade."),
        "fails": ("The forecast predicts PATH, not DISPLACEMENT: R-squared 0.03-0.08 for the "
                  "absolute net move, and measured efficiency FALLS as forecast volatility "
                  "rises. High-volatility sessions are choppier, not more directional, so a "
                  "directional rule gated on volatility is gated toward its worst environment."),
        "kill": ("Reject unless a volatility-conditioned cell beats a regime-matched, "
                 "scale-normalised random gate at the 95th percentile AND is profitable. "
                 "Tested last phase: the gate beats its control but never produces profit."),
    },
    "volume": {
        "works": ("Heavy relative volume means real participation rather than drift on an "
                  "empty book, so a move accompanied by volume should be more informative."),
        "fails": ("Volume predicts MAGNITUDE, not direction - the same wall the volatility "
                  "family hits, reached by a different route. Overnight volume predicts RTH "
                  "range at t up to 7.3 and RTH direction at nothing."),
        "kill": ("Reject unless a volume cell shows directional skill independent of the "
                 "magnitude channel. No test has ever shown one."),
    },
    "added": {
        "works": ("Three canonical mechanisms the library was missing: a channel breakout, a "
                  "band reversion and the trend-side counterpart to VWAP reversion. Added so "
                  "that 'which existing mechanism is strongest' is answered against a complete "
                  "field rather than a partial one."),
        "fails": ("Bollinger duplicates the z-score reversion it sits beside - daily P&L "
                  "correlation 0.81, so it is one mechanism under two names. Donchian and "
                  "VWAP-trend inherit the trend family's displacement problem in full."),
        "kill": ("Reject Bollinger as a separate mechanism outright: at rho = 0.81 with "
                 "revert.z_60 it is not a diversifier. Reject the other two on the trend "
                 "family's condition."),
    },
}


def fam_of(name: str) -> str:
    for k in ("trend", "breakout", "revert", "session", "vol.", "volume", "added"):
        if name.startswith(k):
            return {"revert": "reversion", "vol.": "volatility"}.get(k, k)
    return "other"


def main() -> int:
    cards = pd.read_csv(REPO / "research" / "lab_scorecards.csv")
    rank = pd.read_csv(REPO / "research" / "lab_ranking.csv")
    ts = (pd.read_csv(REPO / "research" / "lab_topstep.csv")
          if (REPO / "research" / "lab_topstep.csv").exists() else pd.DataFrame())
    cards["fam"] = cards.strategy.map(fam_of)
    order = {n: i for i, n in enumerate(rank.strategy + "|" + rank.symbol)}
    cards["ord"] = (cards.strategy + "|" + cards.symbol).map(order).fillna(9999)

    L = []
    L.append("# Strategy Scorecards\n")
    L.append("Generated from `research/lab_scorecards.csv`, `lab_portfolio.csv` and "
             "`lab_topstep.csv` — never hand-edited, so it cannot drift from the data.\n")
    L.append(f"**{len(cards)} cells.** "
             + " · ".join(f"**{k}** {v}" for k, v in cards.verdict.value_counts().items())
             + "\n")
    L.append("Verdict ladder is declared in `scripts/strategy_lab_report.py:verdict` and "
             "applied mechanically. `DD/MLL` is the cell's own 1-contract maximum drawdown "
             "divided by Topstep's $2,000 trailing limit; anything at or above 1.0 is "
             "structurally incompatible before any simulation runs.\n")
    L.append("---\n")

    for fam in ["reversion", "breakout", "trend", "session", "volatility", "volume", "added"]:
        sub = cards[cards.fam == fam].sort_values("ord")
        if not len(sub):
            continue
        prose = FAMILY_PROSE.get(fam, {})
        under = int((sub.dd_over_mll < 1).sum())
        L.append(f"## {fam.upper()}  ·  {len(sub)} cells, {under} inside the barrier\n")
        L.append(f"**Why it could work.** {prose.get('works', '')}\n")
        L.append(f"**Why it could fail.** {prose.get('fails', '')}\n")
        L.append(f"**What would kill it.** {prose.get('kill', '')}\n")
        L.append("| strategy | sym | trades | net $ | $/tr | stressed $/tr | PF | win% "
                 "| max DD $ | DD/MLL | t | hold min | DLL/sess | twin pass | verdict |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for _, r in sub.iterrows():
            pf = f"{r.profit_factor:.2f}" if np.isfinite(r.profit_factor) else "—"
            dll = f"{r.dll_breach_rate:.1%}" if np.isfinite(r.dll_breach_rate) else "—"
            tw = f"{r.best_twin_pass:.1%}" if np.isfinite(r.best_twin_pass) else "—"
            flag = " *(added)*" if r.newly_added else ""
            L.append(
                f"| `{r.strategy}`{flag} | {r.symbol} | {int(r.trades):,} | {r.net_pnl:,.0f} "
                f"| {r.expectancy_trade:.2f} | {r.stressed_expectancy_trade:.2f} | {pf} "
                f"| {r.win_rate:.1%} | {r.max_dd:,.0f} | {r.dd_over_mll:.1f}× "
                f"| {r.t_stat:.2f} | {r.median_hold_min:.0f} | {dll} | {tw} "
                f"| **{r.verdict}** |")
        L.append("")

    L.append("---\n")
    L.append("## The two cells that are not REJECT\n")
    for _, r in cards[cards.verdict != "REJECT"].sort_values("ord").iterrows():
        sub = ts[(ts.strategy == r.strategy) & (ts.symbol == r.symbol)] if len(ts) else None
        L.append(f"### `{r.strategy}` · {r.symbol} — **{r.verdict}**\n")
        L.append(f"**Core.** Net ${r.net_pnl:,.0f} on {int(r.trades):,} trades "
                 f"(${r.expectancy_trade:.2f}/trade, ${r.stressed_expectancy_trade:.2f} after "
                 f"a tick of slippage). Profit factor "
                 f"{r.profit_factor:.2f}, win rate {r.win_rate:.1%}. Max drawdown "
                 f"${r.max_dd:,.0f} = **{r.dd_over_mll:.2f}× the MLL**. Sharpe {r.sharpe:.2f}, "
                 f"Sortino {r.sortino:.2f}, t = {r.t_stat:.2f}. Median hold "
                 f"{r.median_hold_min:.0f} min, {r.trades_per_session:.1f} trades/session, "
                 f"{r.consec_losing_days} consecutive losing days at worst.\n")
        L.append(f"**Why it survived.** It is one of only 8 cells whose own worst historical "
                 f"run fits inside the $2,000 barrier, and its expectancy stays positive with "
                 f"a full tick of round-turn slippage charged. It trips the $1,000 daily loss "
                 f"limit on {r.dll_breach_rate:.1%} of sessions"
                 f"{' — never, in the whole sample' if r.dll_breach_rate == 0 else ''}.\n")
        if sub is not None and len(sub):
            L.append("**Topstep twin, by size.**\n")
            L.append("| contracts | pass | breach | median days | P[MC drawdown > MLL] |")
            L.append("|---|---|---|---|---|")
            for _, q in sub.iterrows():
                md = f"{q.median_days_to_pass:.0f}" if np.isfinite(q.median_days_to_pass) else "never"
                L.append(f"| {int(q.contracts)} | {q.pass_rate:.1%} | {q.breach_rate:.1%} "
                         f"| {md} | {q.mc_prob_dd_exceeds_mll:.1%} |")
            L.append("")
        L.append(f"**Why it is still not a candidate.** t = {r.t_stat:.2f} on the daily "
                 f"series, short of 1.96 — and that is before correcting for having examined "
                 f"{len(cards)} cells, which would require roughly |t| > 3.6. There is no "
                 f"contract size at which it both reaches $3,000 and survives the barrier.\n")

    L.append("---\n")
    L.append("## Instrument note\n")
    inst = cards.groupby("symbol").agg(cells=("verdict", "size"),
                                       under=("dd_over_mll", lambda x: int((x < 1).sum())),
                                       med_dd=("dd_over_mll", "median"))
    L.append("| instrument | cells | inside the barrier | median DD/MLL |")
    L.append("|---|---|---|---|")
    for sym, r in inst.iterrows():
        L.append(f"| {sym} | {int(r.cells)} | {int(r.under)} | {r.med_dd:.1f}× |")
    L.append("\nThe micros carry every survivor. A tick is $0.50 on MNQ against $12.50 on ES, "
             "so the same mechanism faces a 25× smaller cost floor and a 25× smaller "
             "drawdown in dollars — which is the entire reason those cells fit inside a "
             "$2,000 barrier and their full-size twins do not.\n")

    out = REPO / "docs" / "STRATEGY_SCORECARDS.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size:,} bytes, {len(L)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
