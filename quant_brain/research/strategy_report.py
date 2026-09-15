"""The strategy scorecard: everything a frozen spec's result has to say, in one object.

WHAT THIS IS
------------
`run_strategy.py` produces a canonical ledger and an account result per execution mode. This
module turns those into the report a human reads, and it computes nothing that the ledger did
not already record - every number here is a VIEW of the same trade stream the Topstep twin
consumed, never a second simulation.

    A  STRATEGY SUMMARY        what was tested, on what data, under what rules
    B  TRADE STATISTICS        the trades themselves
    C  RISK                    drawdown, streaks, excursions, exposure
    D  TIME DISTRIBUTION       month, quarter, year
    E  TOPSTEP                 the account, from `AccountResult`
    F  PAYOUT                  separated from performance, deliberately
       MONTE CARLO             resampled paths, labelled as resampling
       REGIME                  the full distribution, never the best bucket
       STATISTICS              sample size, confidence, concentration, dependence
       CLASSIFICATION          one of six verdicts, on criteria fixed in advance

THE THREE THINGS THIS MODULE REFUSES TO DO
--------------------------------------------
1. **It does not annualise a short sample.** Fifteen months of futures is what is on disk.
   A Sharpe scaled to a year from it is a number with a standard error nobody prints beside
   it, so the monthly distribution is reported as months and left as months.

2. **It does not call a backtest profit a payout.** Section F is computed from the account
   simulation's own payout clock and is reported separately from Section B, because a
   strategy that made $8,000 in a window where the account was liquidated on day nine made
   the account nothing.

3. **It does not present the best bucket.** Every regime split prints every bucket, with the
   trade count beside it, and the module has no function that selects one.

THE MAE / MFE BASIS, STATED ONCE
----------------------------------
`analytics.py` refuses to compute MAE from bar extremes, and it is right: a trade entered
mid-bar did not experience that bar's whole range. The canonical ledger's MAE and MFE ARE
bar-derived, because the exit simulator walks bars and that is the only resolution the store
has. So they are reported here as what they are - an UPPER BOUND on adverse excursion at
one-minute resolution - and `MAE_BASIS` is printed next to them rather than kept in a docstring.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_brain.core import stats as st
from quant_brain.markets.futures_cme import paths as pa
from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme import twin as tw
from quant_brain.research import robustness as rb
from quant_brain.research.account_result import AccountResult
from quant_brain.research.canonical_ledger import CanonicalLedger

MAE_BASIS = ("bar-resolution extreme: the worst price printed by any one-minute bar the trade "
             "was open across. An UPPER BOUND on what the trade experienced, because a trade "
             "entered part-way through a bar did not see all of that bar's range.")

#: The verdict thresholds. Fixed HERE, in the module, so they are visible before any result
#: exists. A threshold chosen after seeing a number is not a threshold, it is a decision
#: wearing one - which is the same reasoning `futures_discover.MAX_CEILING_SHARE` carries.
COMBINE_TARGET_NOTE = (
    "NOT simply 'profit >= $3,000'. It is Topstep's Combine pass condition: profit at or "
    "above the target AFTER the consistency rule has been applied, plus the minimum trading "
    "days. The consistency rule RAISES the target when one day carries too much of the "
    "profit - a single +$3,100 day is 100% of profit against a 55% limit and lifts the "
    "target to $5,636, so it does NOT pass. Every 'target' figure in this report is the "
    "Combine condition, never the raw $3,000.")

#: Gross P&L as a share of the one-bar-ahead oracle ceiling, above which a result is treated
#: as a suspected lookahead rather than a strategy. THE SAME measured band as
#: `futures_discover.MAX_CEILING_SHARE`, and `tests/test_certification.py` asserts the two
#: constants are equal so they cannot drift: the red team measured every planted cheat at
#: >= 44.9% of the ceiling and the best clean causal rule at 3.97%, an 11x empty band, and
#: 20% sits in the middle of it on a log scale.
#:
#: ONE-SIDED. A high share is strong evidence of a leak; a low share is evidence of nothing,
#: because a rule that is in the market a tenth of the session has a tenth of the opportunity.
LOOKAHEAD_CEILING_SHARE = 0.20

MIN_TRADES_FOR_A_VERDICT = 30        # below this, no expectancy statistic means anything
MIN_SESSIONS_FOR_A_VERDICT = 60      # a quarter of trading days
MIN_MONTHS_FOR_A_VERDICT = 6
MIN_MONTHS_FOR_ROBUST = 24           # two years; the 15-month store cannot reach this
SIGNIFICANT_T = 2.0                  # ~5% two-sided, before any multiplicity correction
CONCENTRATION_LIMIT = 0.50           # top 5% of sessions carrying more than half the net
SINGLE_MONTH_LIMIT = 0.60            # one month carrying more than this share of the net
MIN_POSITIVE_MONTH_SHARE = 0.50

ROBUST_POSITIVE = "ROBUST POSITIVE"
PROMISING = "PROMISING"
INCONCLUSIVE = "INCONCLUSIVE"
FRAGILE = "FRAGILE"
NEGATIVE = "NEGATIVE"
UNTESTABLE = "UNTESTABLE"

CRITERIA = f"""\
UNTESTABLE       fewer than {MIN_TRADES_FOR_A_VERDICT} trades, or fewer than
                 {MIN_SESSIONS_FOR_A_VERDICT} sessions, or fewer than
                 {MIN_MONTHS_FOR_A_VERDICT} months. The sample cannot support any verdict.
NEGATIVE         headline (CONSERVATIVE) net P&L <= 0.
FRAGILE          positive under CONSERVATIVE, but at least one of: negative under STRESS;
                 the top 5% of sessions carry > {CONCENTRATION_LIMIT:.0%} of net; one month
                 carries > {SINGLE_MONTH_LIMIT:.0%} of net; under half the months positive;
                 the Topstep account is liquidated on the historical path.
INCONCLUSIVE     positive and not fragile, but the expectancy t-statistic is below
                 {SIGNIFICANT_T} - the sample cannot distinguish it from zero.
PROMISING        positive, not fragile, t >= {SIGNIFICANT_T}, survives STRESS - but under
                 {MIN_MONTHS_FOR_ROBUST} months of data, or no clean holdout exists.
ROBUST POSITIVE  everything PROMISING requires, plus >= {MIN_MONTHS_FOR_ROBUST} months AND a
                 clean out-of-sample holdout. NOT REACHABLE on a 15-month store, by
                 construction."""


# ======================================================================================
# A - STRATEGY SUMMARY
# ======================================================================================

@dataclass(frozen=True)
class Summary:
    strategy: str
    spec_hash: str
    engine_version: str
    instrument: str
    timeframe: str
    coverage_start: str
    coverage_end: str
    coverage_months: float
    sessions_tested: int
    bars_tested: int
    data_path: str
    dataset_id: str
    manifest_id: str | None
    frame_fingerprint: str | None
    data_form: str | None
    roll_method: str | None
    adjustment_method: str | None
    quality_status: str | None
    execution_mode: str
    intrabar_mode: str
    topstep_rules_version: str
    long_history_validation: str

    def lines(self) -> list[tuple[str, str]]:
        return [
            ("strategy", f"{self.strategy}   version/hash {self.spec_hash}"),
            ("engine", self.engine_version),
            ("instrument", f"{self.instrument} @ {self.timeframe}"),
            ("historical coverage", f"{self.coverage_start} .. {self.coverage_end}   "
                                    f"({self.coverage_months:.1f} months)"),
            ("sessions / bars", f"{self.sessions_tested:,} / {self.bars_tested:,}"),
            ("data path", self.data_path),
            ("data manifest", f"{self.dataset_id} | manifest {self.manifest_id} | "
                              f"frame {self.frame_fingerprint}"),
            ("data representation", f"{self.data_form} | roll {self.roll_method} | "
                                    f"adjustment {self.adjustment_method} | "
                                    f"quality {self.quality_status}"),
            ("execution mode", f"{self.execution_mode} (intrabar {self.intrabar_mode})"),
            ("Topstep rules", self.topstep_rules_version),
            ("LONG-HISTORY VALIDATION", self.long_history_validation),
        ]


# ======================================================================================
# B - TRADE STATISTICS
# ======================================================================================

@dataclass(frozen=True)
class TradeStats:
    total: int
    longs: int
    shorts: int
    winners: int
    losers: int
    scratches: int
    win_rate: float | None
    average_trade: float | None
    median_trade: float | None
    stdev_trade: float | None
    best_trade: float | None
    worst_trade: float | None
    profit_factor: float | None
    expectancy: float | None
    gross_profit: float
    gross_loss: float
    net_pnl: float
    fees: float
    slippage: float
    average_hold_minutes: float | None
    median_hold_minutes: float | None
    by_exit_reason: dict[str, int]
    long_net: float
    short_net: float

    def lines(self) -> list[tuple[str, str]]:
        return [
            ("trades", f"{self.total}   long {self.longs} / short {self.shorts}"),
            ("winners / losers / flat",
             f"{self.winners} / {self.losers} / {self.scratches}"),
            ("win rate", _pct(self.win_rate)),
            ("average trade", _money(self.average_trade)),
            ("median trade", _money(self.median_trade)),
            ("standard deviation", _money(self.stdev_trade)),
            ("best / worst trade", f"{_money(self.best_trade)} / {_money(self.worst_trade)}"),
            ("profit factor", _num(self.profit_factor)),
            ("expectancy per trade", _money(self.expectancy)),
            ("gross profit / gross loss",
             f"${self.gross_profit:,.2f} / ${self.gross_loss:,.2f}"),
            ("net P&L", f"${self.net_pnl:,.2f}"),
            ("fees (commission+spread)", f"${self.fees:,.2f}"),
            ("slippage", f"${self.slippage:,.2f}"),
            ("hold time avg / median",
             f"{_num(self.average_hold_minutes)} / {_num(self.median_hold_minutes)} min"),
            ("net by direction",
             f"long ${self.long_net:,.0f} / short ${self.short_net:,.0f}"),
            ("exits by reason", ", ".join(f"{k} {v}" for k, v in
                                          sorted(self.by_exit_reason.items())) or "none"),
        ]


# ======================================================================================
# C - RISK
# ======================================================================================

@dataclass(frozen=True)
class Distribution:
    n: int
    mean: float
    p05: float
    p25: float
    median: float
    p75: float
    p95: float
    minimum: float
    maximum: float

    def line(self) -> str:
        return (f"n={self.n}  mean {self.mean:,.0f}  p5 {self.p05:,.0f}  "
                f"p25 {self.p25:,.0f}  med {self.median:,.0f}  p75 {self.p75:,.0f}  "
                f"p95 {self.p95:,.0f}  min {self.minimum:,.0f}  max {self.maximum:,.0f}")


@dataclass(frozen=True)
class RiskStats:
    max_drawdown: float
    max_intraday_drawdown: float
    max_consecutive_losses: int
    max_consecutive_losing_days: int
    mae: Distribution | None
    mfe: Distribution | None
    mae_basis: str
    average_risk_per_trade: float | None
    risk_basis: str
    worst_daily_loss: float
    worst_session: str | None
    best_daily_gain: float
    exposure: float
    longest_underwater_sessions: int
    underwater_fraction: float

    def lines(self) -> list[tuple[str, str]]:
        return [
            ("max drawdown (session close)", f"${self.max_drawdown:,.0f}"),
            ("max intraday drawdown", f"${self.max_intraday_drawdown:,.0f}"),
            ("max consecutive losing trades", str(self.max_consecutive_losses)),
            ("max consecutive losing days", str(self.max_consecutive_losing_days)),
            ("MAE distribution ($)", self.mae.line() if self.mae else "no trades"),
            ("MFE distribution ($)", self.mfe.line() if self.mfe else "no trades"),
            ("MAE/MFE basis", self.mae_basis),
            ("average risk per trade", _money(self.average_risk_per_trade)),
            ("risk basis", self.risk_basis),
            ("worst daily loss", f"${self.worst_daily_loss:,.0f}"
                                 + (f"  on {self.worst_session}" if self.worst_session
                                    else "")),
            ("best daily gain", f"${self.best_daily_gain:,.0f}"),
            ("exposure", f"{self.exposure:.1%} of session bars holding a position"),
            ("time under water", f"{self.longest_underwater_sessions} sessions max, "
                                 f"{self.underwater_fraction:.0%} of the sample"),
        ]


# ======================================================================================
# D - TIME DISTRIBUTION
# ======================================================================================

@dataclass(frozen=True)
class PeriodRow:
    period: str
    trades: int
    net_pnl: float
    win_rate: float | None
    max_drawdown: float
    sessions: int
    pnl_over_account_pct: float
    pnl_over_notional_pct: float | None


@dataclass(frozen=True)
class TimeDistribution:
    monthly: list[PeriodRow]
    quarterly: list[PeriodRow]
    yearly: list[PeriodRow]
    months: int
    positive_months: int
    positive_month_share: float
    mean_monthly: float
    median_monthly: float
    stdev_monthly: float
    best_month: PeriodRow | None
    worst_month: PeriodRow | None
    small_sample: bool
    account_size: int
    mean_notional: float

    def table(self) -> str:
        head = (f"  {'month':9} {'trades':>7} {'sessions':>9} {'net $':>11} "
                f"{'win%':>6} {'maxDD $':>10} {'% of 50K':>9} {'% notional':>11}")
        rows = [head, "  " + "-" * (len(head) - 2)]
        for r in self.monthly:
            notional = ("n/a" if r.pnl_over_notional_pct is None
                        else f"{r.pnl_over_notional_pct:.3f}%")
            rows.append(
                f"  {r.period:9} {r.trades:7d} {r.sessions:9d} {r.net_pnl:11,.0f} "
                f"{_pct(r.win_rate, width=6)} {r.max_drawdown:10,.0f} "
                f"{r.pnl_over_account_pct:8.2f}% {notional:>11}")
        return "\n".join(rows)


# ======================================================================================
# MONTE CARLO
# ======================================================================================

@dataclass(frozen=True)
class MonteCarlo:
    ran: bool
    reason: str
    paths: int
    block: int
    sessions_per_path: int
    p_mll_breach: float | None
    p_dll_hit: float | None
    dll_armed: bool
    p_reach_target: float | None
    p_payout_eligible: float | None
    median_days_to_target: float | None
    ending_pnl_percentiles: dict[str, float]
    account_ending_balance_percentiles: dict[str, float]
    worst_drawdown_percentiles: dict[str, float]
    max_losing_streak_percentiles: dict[str, float]
    label: str

    def lines(self) -> list[tuple[str, str]]:
        if not self.ran:
            return [("Monte Carlo", f"NOT RUN - {self.reason}")]
        def pct(d):
            return "  ".join(f"p{k} {v:,.0f}" for k, v in d.items())
        return [
            ("paths", f"{self.paths:,} moving-block resamples, block {self.block}, "
                      f"{self.sessions_per_path} sessions each"),
            ("P(MLL breach)", _pct(self.p_mll_breach)),
            ("P(DLL hit)", _pct(self.p_dll_hit) if self.dll_armed else "DLL not armed"),
            ("P(pass the Combine)", _pct(self.p_reach_target)),
            ("P(payout eligible)", _pct(self.p_payout_eligible)),
            ("median days to target",
             "never in over half the paths" if self.median_days_to_target is None
             else f"{self.median_days_to_target:.0f}"),
            ("ending strategy P&L", pct(self.ending_pnl_percentiles)),
            ("ending ACCOUNT balance", pct(self.account_ending_balance_percentiles)),
            ("worst drawdown", pct(self.worst_drawdown_percentiles)),
            ("max losing streak", pct(self.max_losing_streak_percentiles)),
            ("what this is", self.label),
        ]


# ======================================================================================
# REGIME
# ======================================================================================

@dataclass(frozen=True)
class Bucket:
    name: str
    trades: int
    net_pnl: float
    win_rate: float | None
    share_of_trades: float
    thin: bool


@dataclass(frozen=True)
class RegimeBreakdown:
    splits: dict[str, list[Bucket]]
    note: str

    def table(self) -> str:
        out = []
        for name, buckets in self.splits.items():
            out.append(f"  {name}")
            for b in buckets:
                flag = "  THIN" if b.thin else ""
                out.append(f"    {b.name:22} {b.trades:5d} trades  "
                           f"{b.share_of_trades:5.1%}  net ${b.net_pnl:10,.0f}  "
                           f"win {_pct(b.win_rate, width=6)}{flag}")
        return "\n".join(out)


# ======================================================================================
# STATISTICS AND CLASSIFICATION
# ======================================================================================

@dataclass(frozen=True)
class Integrity:
    """The two checks that ask whether the RESULT ITSELF is believable, before its statistics.

    Both exist because `run_strategy` had neither. The funnel refuses a hypothesis whose gross
    exceeds a share of the one-bar oracle ceiling, and measures what the fill convention is
    worth; the user-facing strategy path - the one about to be handed real strategies - did
    both of nothing. A signal is arbitrary Python, so the feature-library causality audit
    cannot see a lookahead written directly into it. This can.
    """

    oracle_ceiling: float
    gross_pnl: float
    ceiling_share: float
    ceiling_limit: float
    lookahead_suspected: bool
    entry_fill_convention: str
    entry_fill_sensitivity: float | None
    entry_fill_note: str

    def lines(self) -> list[tuple[str, str]]:
        verdict = ("*** SUSPECTED LOOKAHEAD *** gross is above the refusal level; no causal "
                   "rule measured in this repository has ever earned this share"
                   if self.lookahead_suspected else
                   "below the refusal level (which is evidence of nothing on its own - a "
                   "rule that is rarely in the market earns a small share either way)")
        sens = ("not computable (no open price on the store)"
                if self.entry_fill_sensitivity is None
                else f"${self.entry_fill_sensitivity:+,.2f} over the whole run")
        return [
            ("one-bar oracle ceiling", f"${self.oracle_ceiling:,.0f}  "
                                       f"(what a perfect one-bar-ahead forecast would earn)"),
            ("gross as a share of it", f"{self.ceiling_share:.2%}  "
                                       f"limit {self.ceiling_limit:.0%}"),
            ("lookahead canary", verdict),
            ("entry fill convention", self.entry_fill_convention),
            ("entry fill sensitivity", sens),
            ("what that sensitivity is", self.entry_fill_note),
        ]


@dataclass(frozen=True)
class Statistics:
    trades: int
    sessions: int
    months: int
    expectancy_per_session: float
    expectancy_t: float | None
    expectancy_ci95: tuple[float, float] | None
    t_method: str
    multiple_testing: str
    top5pct_session_share: float
    best_month_share: float
    best_day_share: float
    without_best_5_sessions: float
    positive_month_share: float
    regime_dependent: str
    instrument_dependence: str
    window_dependence: str
    holdout: str
    drawdown_uncertainty: str

    def lines(self) -> list[tuple[str, str]]:
        ci = ("not computable" if self.expectancy_ci95 is None
              else f"[{self.expectancy_ci95[0]:,.2f}, {self.expectancy_ci95[1]:,.2f}]")
        return [
            ("sample", f"{self.trades} trades over {self.sessions} independent sessions "
                       f"and {self.months} months"),
            ("expectancy / session", f"${self.expectancy_per_session:,.2f}"),
            ("expectancy t", _num(self.expectancy_t) + f"   ({self.t_method})"),
            ("expectancy 95% CI / session", ci),
            ("multiple-testing exposure", self.multiple_testing),
            ("top 5% of sessions carry", _share(self.top5pct_session_share)),
            ("best single day carries", _share(self.best_day_share)),
            ("best single month carries", _share(self.best_month_share)),
            ("net without the best 5 sessions", f"${self.without_best_5_sessions:,.0f}"),
            ("positive months", _pct(self.positive_month_share)),
            ("regime dependence", self.regime_dependent),
            ("instrument dependence", self.instrument_dependence),
            ("time-window dependence", self.window_dependence),
            ("drawdown uncertainty", self.drawdown_uncertainty),
            ("OUT-OF-SAMPLE", self.holdout),
        ]


@dataclass(frozen=True)
class Classification:
    verdict: str
    reasons: list[str]
    blocking: list[str]
    criteria: str = CRITERIA


# ======================================================================================
# THE REPORT
# ======================================================================================

@dataclass(frozen=True)
class StrategyReport:
    summary: Summary
    trades: TradeStats
    risk: RiskStats
    time: TimeDistribution
    account: AccountResult
    ladder: list[dict]
    monte_carlo: MonteCarlo
    regime: RegimeBreakdown
    integrity: Integrity
    statistics: Statistics
    classification: Classification
    limitations: list[str] = field(default_factory=list)

    def render(self) -> str:
        w = 100
        out = [
            "=" * w,
            f"STRATEGY SCORECARD   {self.summary.strategy}   {self.summary.spec_hash}",
            "=" * w,
            _block("A. STRATEGY SUMMARY", self.summary.lines()),
            _block("B. TRADE STATISTICS", self.trades.lines()),
            _block("C. RISK", self.risk.lines()),
            "\nD. TIME DISTRIBUTION",
            self.time.table(),
            _block("   monthly distribution", _monthly_lines(self.time)),
            _block("   quarterly", [(r.period, f"${r.net_pnl:,.0f}  {r.trades} trades")
                                    for r in self.time.quarterly]),
            _block("   yearly", [(r.period, f"${r.net_pnl:,.0f}  {r.trades} trades")
                                 for r in self.time.yearly]),
            _block("E. TOPSTEP ACCOUNT",
                   _topstep_lines(self.account, self.summary.sessions_tested)),
            _block("F. PAYOUT ANALYSIS", _payout_lines(self.account)),
            "\nEXECUTION SCENARIO LADDER",
            _ladder_table(self.ladder),
            _block("MONTE CARLO / PATH SIMULATION", self.monte_carlo.lines()),
            "\nREGIME ANALYSIS  (" + self.regime.note + ")",
            self.regime.table(),
            _block("RESULT INTEGRITY  (is this result believable at all?)",
                   self.integrity.lines()),
            _block("STATISTICAL CONFIDENCE", self.statistics.lines()),
            "\nEXPLICIT LIMITATIONS",
            "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(self.limitations)),
            "\n" + "=" * w,
            f"CLASSIFICATION: {self.classification.verdict}",
            "=" * w,
        ]
        for r in self.classification.reasons:
            out.append(f"  + {r}")
        for r in self.classification.blocking:
            out.append(f"  - {r}")
        out.append("\nCRITERIA (fixed before the run, in quant_brain/research/"
                   "strategy_report.py)")
        out.append("\n".join("  " + ln for ln in self.classification.criteria.splitlines()))
        return "\n".join(out)

    def to_json(self) -> dict:
        import dataclasses
        return {
            "summary": dataclasses.asdict(self.summary),
            "trade_statistics": dataclasses.asdict(self.trades),
            "risk": dataclasses.asdict(self.risk),
            "time_distribution": dataclasses.asdict(self.time),
            "execution_ladder": self.ladder,
            "monte_carlo": dataclasses.asdict(self.monte_carlo),
            "regime": dataclasses.asdict(self.regime),
            "integrity": dataclasses.asdict(self.integrity),
            "statistics": dataclasses.asdict(self.statistics),
            "classification": dataclasses.asdict(self.classification),
            "limitations": list(self.limitations),
        }


# ======================================================================================
# BUILDERS
# ======================================================================================

def build(ledger: CanonicalLedger, account: AccountResult, *, spec, sset, ladder: list[dict],
          engine_version: str, mc_paths: int = 5000, mc_block: int = 10,
          daily_loss_limit: float | None = None, seed: int = 0,
          holdout: str | None = None) -> StrategyReport:
    """The whole scorecard from one ledger and its account result.

    `ladder` is the list of per-mode rows the runner already built; it is passed in rather
    than recomputed so the report cannot disagree with the runner about what each mode did.
    """
    trades = ledger.trade_frame()
    daily = ledger.daily()
    feat = sset.provenance.get("feature_data", {})
    months = _month_index(daily)

    summary = Summary(
        strategy=spec.name, spec_hash=spec.spec_hash, engine_version=engine_version,
        instrument=spec.instrument, timeframe=spec.timeframe,
        coverage_start=str(sset.first_day), coverage_end=str(sset.last_day),
        coverage_months=_months_between(sset.first_day, sset.last_day),
        sessions_tested=len(sset), bars_tested=sum(s.bars for s in ledger.sessions),
        data_path=sset.path, dataset_id=feat.get("dataset_id", "?"),
        manifest_id=feat.get("manifest_id"), frame_fingerprint=feat.get("frame_fingerprint"),
        data_form=feat.get("data_form"), roll_method=feat.get("roll_method"),
        adjustment_method=feat.get("adjustment_method"),
        quality_status=feat.get("quality_status"),
        execution_mode=ledger.scenario, intrabar_mode=ledger.mode.value,
        topstep_rules_version=account.payout.rules.version,
        long_history_validation=_long_history(sset))

    ts_ = _trade_stats(trades)
    risk = _risk_stats(ledger, account, trades, daily, spec)
    time = _time_distribution(ledger, account, trades, daily)
    mc = _monte_carlo(ledger, account, paths=mc_paths, block=mc_block,
                      daily_loss_limit=daily_loss_limit, seed=seed)
    regime = _regime(sset, trades)
    integrity = _integrity(ledger, sset, trades)
    statistics = _statistics(ledger, daily, trades, time, spec, sset, holdout)
    classification = _classify(ts_, time, statistics, account, ladder, ledger, integrity)
    return StrategyReport(
        summary=summary, trades=ts_, risk=risk, time=time, account=account, ladder=ladder,
        monte_carlo=mc, regime=regime, integrity=integrity, statistics=statistics,
        classification=classification,
        limitations=_limitations(sset, ledger, account, time, months))


def _trade_stats(t: pd.DataFrame) -> TradeStats:
    if not len(t):
        return TradeStats(0, 0, 0, 0, 0, 0, None, None, None, None, None, None, None, None,
                          0.0, 0.0, 0.0, 0.0, 0.0, None, None, {}, 0.0, 0.0)
    net = t["net_pnl"].to_numpy(dtype=float)
    wins, losses = net[net > 0], net[net < 0]
    gp, gl = float(wins.sum()), float(-losses.sum())
    long_mask = t["direction"].to_numpy() > 0
    return TradeStats(
        total=len(t), longs=int(long_mask.sum()), shorts=int((~long_mask).sum()),
        winners=len(wins), losers=len(losses), scratches=int((net == 0).sum()),
        win_rate=len(wins) / len(net),
        average_trade=float(net.mean()), median_trade=float(np.median(net)),
        stdev_trade=float(net.std(ddof=1)) if len(net) > 1 else None,
        best_trade=float(net.max()), worst_trade=float(net.min()),
        profit_factor=(gp / gl) if gl > 0 else None,
        expectancy=float(net.mean()),
        gross_profit=gp, gross_loss=gl, net_pnl=float(net.sum()),
        fees=float(t["commission_and_spread"].sum()),
        slippage=float(t["slippage"].sum()),
        average_hold_minutes=float(t["holding_minutes"].mean()),
        median_hold_minutes=float(t["holding_minutes"].median()),
        by_exit_reason=dict(Counter(t["exit_reason"].tolist())),
        long_net=float(net[long_mask].sum()), short_net=float(net[~long_mask].sum()))


def _dist(values) -> Distribution | None:
    v = np.asarray(values, dtype=float)
    if not v.size:
        return None
    q = np.percentile(v, [5, 25, 50, 75, 95])
    return Distribution(n=len(v), mean=float(v.mean()), p05=float(q[0]), p25=float(q[1]),
                        median=float(q[2]), p75=float(q[3]), p95=float(q[4]),
                        minimum=float(v.min()), maximum=float(v.max()))


def _risk_stats(ledger, account, t: pd.DataFrame, daily: pd.Series, spec) -> RiskStats:
    d = daily.to_numpy(dtype=float)
    worst_i = int(np.argmin(d)) if d.size else -1
    con = rb.concentration(d, dates=[s.day for s in ledger.sessions]) if d.size else None
    risk_basis = (f"the spec's declared stop ({spec.exit.describe()})"
                  if spec.exit.has_stop else
                  "NO STOP DECLARED: risk per trade is undefined, so the figure above is the "
                  "realised average loss on losing trades, which is not the same quantity")
    if spec.exit.has_stop and len(t):
        # R is the initial stop distance; the ledger records the R multiple, so the dollar
        # risk is recoverable where the trade actually moved.
        with np.errstate(divide="ignore", invalid="ignore"):
            r = t["r_multiple"].to_numpy(dtype=float)
            g = t["gross_pnl"].to_numpy(dtype=float)
            per = np.where(np.abs(r) > 1e-9, np.abs(g / r), np.nan)
        avg_risk = float(np.nanmean(per)) if np.isfinite(per).any() else None
    elif len(t):
        losses = t["net_pnl"].to_numpy(dtype=float)
        losses = losses[losses < 0]
        avg_risk = float(-losses.mean()) if losses.size else None
    else:
        avg_risk = None
    return RiskStats(
        max_drawdown=abs(account.max_drawdown),
        max_intraday_drawdown=abs(account.max_intraday_drawdown),
        max_consecutive_losses=_longest_run(t["net_pnl"].to_numpy(dtype=float) < 0)
        if len(t) else 0,
        max_consecutive_losing_days=_longest_run(d < 0) if d.size else 0,
        mae=_dist(t["mae"].to_numpy()) if len(t) else None,
        mfe=_dist(t["mfe"].to_numpy()) if len(t) else None,
        mae_basis=MAE_BASIS,
        average_risk_per_trade=avg_risk, risk_basis=risk_basis,
        worst_daily_loss=float(d.min()) if d.size else 0.0,
        worst_session=str(ledger.sessions[worst_i].day) if worst_i >= 0 else None,
        best_daily_gain=float(d.max()) if d.size else 0.0,
        exposure=(sum(tr.holding_minutes for s in ledger.sessions for tr in s.trades)
                  / max(1, sum(s.bars for s in ledger.sessions))),
        longest_underwater_sessions=con.longest_underwater if con else 0,
        underwater_fraction=con.underwater_fraction if con else 0.0)


def _month_index(daily: pd.Series) -> pd.PeriodIndex:
    return pd.PeriodIndex(pd.to_datetime(pd.Index(daily.index)), freq="M")


def _period_rows(ledger, t: pd.DataFrame, daily: pd.Series, freq: str,
                 account_size: int, mean_notional: float) -> list[PeriodRow]:
    if not len(daily):
        return []
    idx = pd.PeriodIndex(pd.to_datetime(pd.Index(daily.index)), freq=freq)
    tper = (pd.PeriodIndex(pd.to_datetime(t["session"]), freq=freq) if len(t)
            else pd.PeriodIndex([], freq=freq))
    out = []
    for p in sorted(set(idx)):
        mask = idx == p
        vals = daily.to_numpy(dtype=float)[mask]
        tm = (tper == p) if len(t) else np.zeros(0, dtype=bool)
        sub = t[tm] if len(t) else t
        net = float(vals.sum())
        eq = np.concatenate([[0.0], np.cumsum(vals)])
        dd = float((eq - np.maximum.accumulate(eq)).min())
        wins = int((sub["net_pnl"] > 0).sum()) if len(sub) else 0
        out.append(PeriodRow(
            period=str(p), trades=len(sub), net_pnl=net,
            win_rate=(wins / len(sub)) if len(sub) else None,
            max_drawdown=abs(dd), sessions=int(mask.sum()),
            pnl_over_account_pct=100.0 * net / account_size,
            pnl_over_notional_pct=(100.0 * net / mean_notional) if mean_notional else None))
    return out


def _time_distribution(ledger, account, t, daily) -> TimeDistribution:
    size = account.account_size
    notional = account.returns.mean_notional
    monthly = _period_rows(ledger, t, daily, "M", size, notional)
    m = np.array([r.net_pnl for r in monthly], dtype=float)
    pos = int((m > 0).sum())
    return TimeDistribution(
        monthly=monthly,
        quarterly=_period_rows(ledger, t, daily, "Q", size, notional),
        yearly=_period_rows(ledger, t, daily, "Y", size, notional),
        months=len(monthly), positive_months=pos,
        positive_month_share=(pos / len(monthly)) if len(monthly) else 0.0,
        mean_monthly=float(m.mean()) if m.size else 0.0,
        median_monthly=float(np.median(m)) if m.size else 0.0,
        stdev_monthly=float(m.std(ddof=1)) if m.size > 1 else 0.0,
        best_month=max(monthly, key=lambda r: r.net_pnl) if monthly else None,
        worst_month=min(monthly, key=lambda r: r.net_pnl) if monthly else None,
        small_sample=len(monthly) < MIN_MONTHS_FOR_ROBUST,
        account_size=size, mean_notional=notional)


def _monte_carlo(ledger, account, *, paths: int, block: int,
                 daily_loss_limit: float | None, seed: int) -> MonteCarlo:
    days = ledger.twin_days()
    if len(days) < 2 * block:
        return MonteCarlo(
            ran=False,
            reason=f"{len(days)} sessions is under twice the {block}-session block; a "
                   f"moving-block resample of it would reuse the same few blocks and report "
                   f"its own construction",
            paths=0, block=block, sessions_per_path=len(days), p_mll_breach=None,
            p_dll_hit=None, dll_armed=daily_loss_limit is not None, p_reach_target=None,
            p_payout_eligible=None, median_days_to_target=None, ending_pnl_percentiles={},
            account_ending_balance_percentiles={}, worst_drawdown_percentiles={},
            max_losing_streak_percentiles={}, label="")

    # THE POLICY MUST BE THE ACCOUNT'S OWN.
    #
    # This used to hardcode `fraction=0.0` - never withdraw - while the account result beside
    # it ran the CLI's policy (default: withdraw the whole eligible cap). A payout lowers the
    # balance while the MLL stays put, so a no-withdrawal twin has a buffer the reported
    # account does not, and the Monte Carlo understated ruin in the flattering direction.
    # Measured on a 120-session sample: P(breach) 87.1% at fraction=0.0 against 98.5% at
    # fraction=1.0, an 11.4-point understatement of the number a reader uses to decide
    # whether to risk the fee.
    twin_obj = tw.TopstepTwin(account.account_size, daily_loss_limit=daily_loss_limit,
                              payout_policy=account.payout.rules.to_policy(
                                  fraction=account.payout.policy_fraction,
                                  min_buffer_after=account.payout.policy_min_buffer_after))
    sample = pa.moving_block(days, block=block, reps=paths, seed=seed)
    ends, balances, dds, streaks = [], [], [], []
    breach = dll_hit = target = payout = 0
    to_target = []
    for path in sample:
        r = twin_obj.run(path)
        p = np.array([d.pnl for d in path], dtype=float)
        ends.append(float(p.sum()))
        balances.append(r.final_balance)
        eq = np.concatenate([[0.0], np.cumsum(p)])
        dds.append(float((eq - np.maximum.accumulate(eq)).min()))
        streaks.append(_longest_run(p < 0))
        if r.terminal is ts.TopstepStage.LIQUIDATED or r.breach_day is not None:
            breach += 1
        if any(d.event == "dll_capped" for d in r.trace):
            dll_hit += 1
        if r.combine_days is not None:
            target += 1
            to_target.append(r.combine_days)
        if r.payouts or r.terminal is ts.TopstepStage.PAYOUT_ELIGIBLE:
            payout += 1
    n = len(sample)
    return MonteCarlo(
        ran=True, reason="", paths=n, block=block, sessions_per_path=len(days),
        p_mll_breach=breach / n, p_dll_hit=(dll_hit / n), dll_armed=daily_loss_limit is not None,
        p_reach_target=target / n, p_payout_eligible=payout / n,
        median_days_to_target=(float(np.median(to_target))
                               if len(to_target) > n / 2 else None),
        ending_pnl_percentiles=_pcts(ends),
        account_ending_balance_percentiles=_pcts(balances),
        worst_drawdown_percentiles=_pcts(dds),
        max_losing_streak_percentiles=_pcts(streaks),
        label=("BOOTSTRAP / PATH SIMULATION, not historical replay and not independent "
               "evidence of an edge. It reorders the SAME sessions, so it inherits every "
               "bias in the sample and cannot discover one that is not already there. What "
               "it measures is PATH RISK: how differently the same sessions could have been "
               "arranged against a moving loss limit."))


def _pcts(v) -> dict[str, float]:
    a = np.asarray(v, dtype=float)
    return {str(q): float(np.percentile(a, q)) for q in (5, 25, 50, 75, 95)}


def _integrity(ledger: CanonicalLedger, sset, trades: pd.DataFrame) -> Integrity:
    """The lookahead canary and the fill-convention sensitivity.

    THE CEILING. A perfect one-bar-ahead oracle earns sum|c[i+1]-c[i]| x multiplier x
    contracts over the sessions actually traded - every tick of every bar, always on the right
    side. No causal rule comes near it. Computed on the SAME frames the ledger was built from,
    so the denominator is the opportunity this run actually had.

    THE FILL SENSITIVITY. Every entry here is filled at its DECISION bar's close, which
    assumes zero latency between seeing a price and trading at it. The honest alternative is
    the next bar's open. Holding the exits fixed, this reprices each entry at the next bar's
    open and reports the difference: a strategy whose edge IS the convention shows up as a
    large number with the same sign as its P&L.
    """
    mult, ct = ledger.multiplier, ledger.contracts
    ceiling = 0.0
    opens: dict = {}
    for g in sset.frames:
        c = g["c"].to_numpy(dtype=float)
        ceiling += float(np.abs(np.diff(c)).sum()) * mult * ct
        if "o" in g.columns:
            opens[g["day"].iloc[0]] = g["o"].to_numpy(dtype=float)

    gross = float(trades["gross_pnl"].sum()) if len(trades) else 0.0
    share = abs(gross) / ceiling if ceiling else 0.0

    sens = None
    if len(trades) and len(opens) == len(sset.frames):
        delta = 0.0
        ok = True
        for _, r in trades.iterrows():
            o = opens.get(r["session"])
            nb = int(r["entry_bar"]) + 1
            if o is None or nb >= len(o):
                ok = False
                break
            # Paying the next bar's open instead of this bar's close moves the entry price;
            # the P&L moves by the price difference against the direction held.
            delta += (float(o[nb]) - float(r["entry_price"])) * -int(r["direction"]) * mult * ct
        sens = delta if ok else None

    return Integrity(
        oracle_ceiling=ceiling, gross_pnl=gross, ceiling_share=share,
        ceiling_limit=LOOKAHEAD_CEILING_SHARE,
        lookahead_suspected=bool(ceiling and share > LOOKAHEAD_CEILING_SHARE),
        entry_fill_convention="decision bar's CLOSE, zero latency (declared, and optimistic: "
                              "no one trades at a price they have just finished observing)",
        entry_fill_sensitivity=sens,
        entry_fill_note="what the SAME trades would have gained or lost if every entry had "
                        "filled at the NEXT bar's open instead, exits held fixed. A large "
                        "figure with the same sign as net P&L means the edge is the fill.")


def _regime(sset, t: pd.DataFrame) -> RegimeBreakdown:
    """Every split, every bucket. There is no function here that picks one."""
    if not len(t):
        return RegimeBreakdown({}, "no trades")
    entry = pd.to_datetime(t["entry_time"], utc=True).dt.tz_convert("America/New_York")
    vol = _session_vol_terciles(sset)
    trend = _session_trend(sset)
    keys = {
        "direction": np.where(t["direction"].to_numpy() > 0, "long", "short"),
        "hour of day (ET)": entry.dt.strftime("%H:00").to_numpy(),
        "day of week": entry.dt.day_name().str.slice(0, 3).to_numpy(),
        "month": pd.PeriodIndex(pd.to_datetime(t["session"]), freq="M").astype(str),
        "year": pd.PeriodIndex(pd.to_datetime(t["session"]), freq="Y").astype(str),
        "session volatility tercile": np.array([vol.get(d, "unlabelled")
                                                for d in t["session"]]),
        "session trend": np.array([trend.get(d, "unlabelled") for d in t["session"]]),
        "exit reason": t["exit_reason"].to_numpy(),
    }
    splits: dict[str, list[Bucket]] = {}
    net = t["net_pnl"].to_numpy(dtype=float)
    for name, k in keys.items():
        buckets = []
        for label in sorted(set(map(str, k))):
            m = np.asarray([str(x) == label for x in k])
            sub = net[m]
            buckets.append(Bucket(
                name=label, trades=int(m.sum()), net_pnl=float(sub.sum()),
                win_rate=float((sub > 0).mean()) if sub.size else None,
                share_of_trades=float(m.mean()), thin=int(m.sum()) < 20))
        splits[name] = buckets
    return RegimeBreakdown(
        splits,
        "every bucket is shown, including thin ones; buckets under 20 trades are marked THIN "
        "and no bucket is selected or recommended by this report")


def _session_vol_terciles(sset) -> dict:
    """Terciles of each session's PRICE volatility, measured the way the engine measures it.

    The engine's own `session_atr` - mean true range over the session's bars - so the label a
    trade carries and the ATR its exit distances were scaled by are the same quantity.

    MEASURED FROM PRICES, NOT FROM EQUITY. Labelling sessions by the strategy's own equity
    range would make every split circular: the strategy does well in the sessions where it
    does well. The tercile boundaries are read off the whole sample, which makes this a
    DESCRIPTIVE split and not a tradable rule; nothing in the engine gates on it.
    """
    from quant_brain.research.ledger_builder import session_atr

    rng = {g["day"].iloc[0]: session_atr(g) for g in sset.frames}
    if not rng:
        return {}
    v = np.array(list(rng.values()), dtype=float)
    lo, hi = np.percentile(v, [33.333, 66.667])
    return {d: ("low ATR" if x <= lo else "high ATR" if x > hi else "mid ATR")
            for d, x in rng.items()}


def _session_trend(sset) -> dict:
    """Each session's own directional move, from the PRICES.

    Open-to-close over the traded window, in ATR units, so "trending" means the same thing on
    a quiet day and a violent one. Again from prices: a trend label taken from the strategy's
    P&L would say only that the strategy made money when it made money.
    """
    from quant_brain.research.ledger_builder import session_atr

    out = {}
    for g in sset.frames:
        c = g["c"].to_numpy(dtype=float)
        atr = session_atr(g) or 1e-9
        move = (c[-1] - c[0]) / atr
        out[g["day"].iloc[0]] = ("up trend" if move > 1.0 else
                                 "down trend" if move < -1.0 else "range-bound")
    return out


def _statistics(ledger, daily: pd.Series, t: pd.DataFrame, time: TimeDistribution,
                spec, sset, holdout: str | None) -> Statistics:
    d = daily.to_numpy(dtype=float)
    con = rb.concentration(d, dates=[s.day for s in ledger.sessions]) if d.size else None
    tstat = None
    ci = None
    method = "not computable"
    if d.size >= 2:
        # HAC because session P&L on an intraday strategy is not guaranteed independent -
        # a regime persists across days, and the i.i.d. t would overstate the evidence.
        # The estimator reports its own standard error. Reconstructing it as mean/t divides
        # by zero on a sample whose mean is zero and silently returned the i.i.d. error there.
        hac = st.tstat_hac(d)
        tstat = float(hac.t)
        ci = (float(hac.mean) - 1.96 * float(hac.se), float(hac.mean) + 1.96 * float(hac.se))
        method = f"{hac.method}, lag {hac.lag}, n {hac.n}"
    return Statistics(
        trades=len(t), sessions=len(d), months=time.months,
        expectancy_per_session=float(d.mean()) if d.size else 0.0,
        expectancy_t=tstat, expectancy_ci95=ci, t_method=method,
        multiple_testing=(
            "ONE spec was run, hashed, and reported. No search was performed inside this "
            "run, so no multiplicity correction applies to it. That does NOT cover how the "
            "spec was arrived at: if it was selected after looking at this data, the "
            "correction belongs to that selection and this report cannot see it."),
        top5pct_session_share=(con.top_share.get(0.05, float("nan")) if con else float("nan")),
        best_month_share=(con.best_month_share if con else float("nan")),
        best_day_share=(con.best_day_share if con else float("nan")),
        without_best_5_sessions=(con.without_best.get(5, float("nan")) if con
                                 else float("nan")),
        positive_month_share=time.positive_month_share,
        regime_dependent=(
            "see the REGIME ANALYSIS table - every bucket is shown. A result carried by one "
            "bucket is visible there as that bucket's share of net"),
        instrument_dependence=(
            f"tested on {spec.instrument} only. Nothing in this report is evidence about any "
            f"other instrument, and the ES/MES cross-source finding in "
            f"docs/CANONICAL_DATA_LAYER.md shows that even the 'same' index on two contracts "
            f"is not the same series over every window."),
        window_dependence=(
            f"one contiguous window, {sset.first_day} .. {sset.last_day}. The yearly and "
            f"monthly tables above are the only view of within-window stability this sample "
            f"supports."),
        holdout=holdout or (
            "NO CLEAN HOLDOUT. The whole available history was used. This is stated rather "
            "than manufactured: carving a holdout out of the sample AFTER seeing the result "
            "would not be one."),
        drawdown_uncertainty=(
            "the maximum drawdown is ONE observation from ONE ordering of these sessions. "
            "The Monte Carlo section's worst-drawdown percentiles are the honest range; the "
            "single historical figure is not a bound."))


def _classify(t: TradeStats, time: TimeDistribution, s: Statistics, account: AccountResult,
              ladder: list[dict], ledger, integrity: Integrity) -> Classification:
    good, bad = [], []
    # Before any statistic: is the result believable? A suspected lookahead is not a FRAGILE
    # strategy, it is a void measurement, and grading it on a scale of profitability would
    # dignify it.
    if integrity.lookahead_suspected:
        return Classification(UNTESTABLE, [], [
            f"SUSPECTED LOOKAHEAD: gross is {integrity.ceiling_share:.1%} of the one-bar "
            f"oracle ceiling, above the {integrity.ceiling_limit:.0%} refusal level. No "
            f"causal rule measured in this repository has earned this. Find the leak in the "
            f"signal before reading any number below it."])
    if (t.total < MIN_TRADES_FOR_A_VERDICT or s.sessions < MIN_SESSIONS_FOR_A_VERDICT
            or time.months < MIN_MONTHS_FOR_A_VERDICT):
        return Classification(UNTESTABLE, [], [
            f"{t.total} trades (need {MIN_TRADES_FOR_A_VERDICT}), {s.sessions} sessions "
            f"(need {MIN_SESSIONS_FOR_A_VERDICT}), {time.months} months "
            f"(need {MIN_MONTHS_FOR_A_VERDICT})"])

    if t.net_pnl <= 0:
        return Classification(NEGATIVE, [], [
            f"net P&L under the headline {ledger.scenario} mode is ${t.net_pnl:,.0f}"])
    good.append(f"net ${t.net_pnl:,.0f} under {ledger.scenario} over {s.sessions} sessions")

    stress = next((r for r in ladder if r.get("scenario") == "STRESS"), None)
    if stress is not None and stress.get("net_pnl", 0.0) <= 0:
        bad.append(f"STRESS execution turns it negative (${stress['net_pnl']:,.0f}): the "
                   f"result depends on the cost assumption")
    if s.top5pct_session_share == s.top5pct_session_share and \
            s.top5pct_session_share > CONCENTRATION_LIMIT:
        bad.append(f"the top 5% of sessions carry {s.top5pct_session_share:.0%} of net "
                   f"(limit {CONCENTRATION_LIMIT:.0%})")
    if s.best_month_share == s.best_month_share and s.best_month_share > SINGLE_MONTH_LIMIT:
        bad.append(f"one month carries {s.best_month_share:.0%} of net "
                   f"(limit {SINGLE_MONTH_LIMIT:.0%})")
    if time.positive_month_share < MIN_POSITIVE_MONTH_SHARE:
        bad.append(f"only {time.positive_month_share:.0%} of months are positive "
                   f"(limit {MIN_POSITIVE_MONTH_SHARE:.0%})")
    if account.liquidated:
        bad.append(f"the Topstep account is LIQUIDATED on the historical path "
                   f"({account.liquidation_session}: {account.liquidation_reason})")
    if bad:
        return Classification(FRAGILE, good, bad)

    if s.expectancy_t is None or s.expectancy_t < SIGNIFICANT_T:
        return Classification(INCONCLUSIVE, good, [
            f"expectancy t is {_num(s.expectancy_t)} against a floor of {SIGNIFICANT_T}: "
            f"this sample cannot distinguish the edge from zero"])
    good.append(f"expectancy t {s.expectancy_t:.2f} ({s.t_method})")
    good.append(f"{time.positive_month_share:.0%} of months positive, "
                f"survives STRESS execution")

    blocking = []
    if time.months < MIN_MONTHS_FOR_ROBUST:
        blocking.append(f"{time.months} months of data, under the {MIN_MONTHS_FOR_ROBUST} "
                        f"required for ROBUST POSITIVE")
    if s.holdout.startswith("NO CLEAN HOLDOUT"):
        blocking.append("no clean out-of-sample holdout")
    if blocking:
        return Classification(PROMISING, good, blocking)
    return Classification(ROBUST_POSITIVE, good, [])


def _limitations(sset, ledger, account, time: TimeDistribution, months) -> list[str]:
    out = [
        f"CURRENT HISTORICAL DEPTH: {sset.first_day} .. {sset.last_day} "
        f"({len(sset)} complete sessions spanning {time.months} calendar months). "
        + _long_history(sset),
        "Partial fills, queue position and market impact are NOT MODELLED in any execution "
        "mode.",
        "Stops and targets fill AT their level even on a gap through it - optimistic, and "
        "declared in every mode's assumption table.",
        f"MAE and MFE are {MAE_BASIS}",
        "The monthly '% of 50K' column is P&L over the account's nominal size. Topstep "
        "requires no such capital to be posted, so it is a scale, not a return on capital.",
        "The Monte Carlo section resamples THESE sessions. It measures path risk, not edge, "
        "and cannot be evidence that the edge exists.",
        "One instrument, one contiguous window, one execution simulator. Nothing here has "
        "been reproduced on an independent data source.",
    ]
    if not account.cross_check.agrees:
        out.append("The independent Topstep reference did NOT agree with the production "
                   "twin on this run: " + "; ".join(account.cross_check.mismatches))
    return out


# ======================================================================================
# FORMATTING
# ======================================================================================

def _long_history(sset) -> str:
    months = _months_between(sset.first_day, sset.last_day)
    if months >= MIN_MONTHS_FOR_ROBUST:
        return f"LONG-HISTORY VALIDATION: AVAILABLE ({months:.0f} months)"
    return (f"LONG-HISTORY VALIDATION: NOT AVAILABLE - {months:.1f} months on disk. "
            f"Nothing in this report is long-term validation, and a result that looks "
            f"exceptional over this window should be read as exceptional OVER THIS WINDOW.")


def _months_between(a, b) -> float:
    a = a if isinstance(a, dt.date) else pd.Timestamp(a).date()
    b = b if isinstance(b, dt.date) else pd.Timestamp(b).date()
    return (b - a).days / 30.4375


def _longest_run(flags) -> int:
    best = run = 0
    for f in np.asarray(flags, dtype=bool):
        run = run + 1 if f else 0
        best = max(best, run)
    return int(best)


def _pct(v, width: int = 0) -> str:
    s = "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.1%}"
    return f"{s:>{width}}" if width else s


def _share(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "not meaningful (net P&L is not positive)"
    return f"{v:.0%} of net"


def _money(v) -> str:
    return "n/a" if v is None else f"${v:,.2f}"


def _num(v) -> str:
    return "n/a" if v is None else f"{v:,.2f}"


def _block(title: str, rows) -> str:
    rows = list(rows)
    if not rows:
        return f"\n{title}\n  (nothing to report)"
    w = max(len(str(k)) for k, _ in rows)
    body = "\n".join(f"  {k:<{w}}  {v}" for k, v in rows)
    return f"\n{title}\n{body}"


def _monthly_lines(t: TimeDistribution) -> list[tuple[str, str]]:
    out = [
        ("months", f"{t.months}" + ("   *** SMALL SAMPLE: nothing below is annualised or "
                                    "extrapolated ***" if t.small_sample else "")),
        ("positive months", f"{t.positive_months} / {t.months}  "
                            f"({t.positive_month_share:.0%})"),
        ("mean monthly P&L", f"${t.mean_monthly:,.0f}"),
        ("median monthly P&L", f"${t.median_monthly:,.0f}"),
        ("stdev of monthly P&L", f"${t.stdev_monthly:,.0f}"),
    ]
    if t.best_month:
        out.append(("best month", f"{t.best_month.period}  ${t.best_month.net_pnl:,.0f}"))
    if t.worst_month:
        out.append(("worst month", f"{t.worst_month.period}  ${t.worst_month.net_pnl:,.0f}"))
    out.append(("TWO DENOMINATORS",
                f"'% of 50K' is P&L over the account's nominal size (no capital is posted); "
                f"'% notional' is P&L over the ~${t.mean_notional:,.0f} of contract value "
                f"actually controlled. They are not the same quantity."))
    return out


def _topstep_lines(a: AccountResult, sessions_tested: int) -> list[tuple[str, str]]:
    # `AccountResult.final_equity` is an ALIAS of `ending_balance` - an account LEVEL, not a
    # P&L. This function used to print `starting_balance + final_equity` as "ending strategy
    # equity", which on a $50,000 account that ended at $48,095 rendered as $98,095 with a
    # "P&L" of $48,095. The strategy's own result is `returns.net_pnl`, which is the sum the
    # ledger settled; the two differ by exactly what the account's rules took away.
    strategy_pnl = a.returns.net_pnl
    return [
        ("starting balance", f"${a.starting_balance:,.0f}"),
        ("ending STRATEGY equity", f"${a.starting_balance + strategy_pnl:,.0f}  "
                                   f"(strategy P&L ${strategy_pnl:+,.0f}, unconstrained)"),
        ("ending ACCOUNT equity", f"${a.ending_balance:,.0f}  "
                                  f"(P&L under the account's rules "
                                  f"${a.returns.pnl_under_account_constraints:+,.0f})"),
        ("MLL at the end", f"${a.ending_mll:,.0f}"),
        ("minimum MLL buffer", f"${a.min_mll_buffer:,.0f}   "
                               f"intraday ${a.min_mll_buffer_intraday:,.0f}"),
        ("DLL", "not armed" if a.min_dll_buffer is None
                else f"minimum buffer ${a.min_dll_buffer:,.0f}, "
                     f"{a.dll_capped_sessions} capped sessions"),
        ("liquidation", f"{a.liquidated}" + (f" on {a.liquidation_session} - "
                                             f"{a.liquidation_reason}" if a.liquidated
                                             else "")),
        ("Combine target reached", f"{a.target_reached}"
         + (f" after {a.combine_sessions} sessions" if a.combine_sessions else "")),
        ("what 'target' means here", COMBINE_TARGET_NOTE),
        ("forced flat", f"{a.forced_flatten_sessions} sessions, "
                        f"${a.forced_flatten_pnl:,.0f}"),
        ("maximum contracts", a.contract_limit_detail),
        ("contract-limit violations", "0" if a.contract_limit_ok else "SEE ABOVE"),
        # `days_survived` counts sessions the account was STEPPED through; `days_traded`
        # counts sessions on which a trade actually happened. Printing them as "X of Y
        # sessions traded" read as 249 of 71, which is not a sentence.
        ("complete-account survival",
         f"survived {a.days_survived} of {sessions_tested} sessions"
         + (f", traded on {a.days_traded}" if a.days_traded != a.days_survived else "")
         + f"; terminal stage {a.terminal_stage}"),
        ("cross-check vs independent reference",
         f"{'AGREES' if a.cross_check.agrees else 'MISMATCH'} "
         f"({a.cross_check.fields_compared} fields)"),
    ]


def _payout_lines(a: AccountResult) -> list[tuple[str, str]]:
    p = a.payout
    return [
        ("rules version", p.rules.version),
        ("P(pass the Combine before a violation)", _pct(a.p_target_before_violation)),
        ("P(payout eligibility)", _pct(a.p_payout_eligible)),
        ("P(survive the period)", _pct(a.p_survive_period)),
        ("payout-eligible sessions", str(p.eligible_sessions)),
        ("first eligible", str(p.first_eligible_session) if p.first_eligible_session
         else "never within the sample"),
        ("sessions to first eligible", str(p.sessions_to_first_eligible)
         if p.sessions_to_first_eligible else "n/a"),
        ("payouts taken under the policy", f"{len(p.payouts)}  total ${p.total_paid:,.0f}"),
        ("trader share", f"${p.trader_share_of_total:,.0f}"),
        ("NOT A PAYOUT", "A backtest profit is not a payout. Everything above is the "
                         "account simulation's own payout clock; nothing on this line is "
                         "money that was withdrawn."),
        ("probability basis", a.probability_note),
    ]


def _ladder_table(ladder: list[dict]) -> str:
    head = (f"  {'mode':13} {'net $':>11} {'expectancy $':>13} {'maxDD $':>10} "
            f"{'MLL survives':>13} {'P(target)':>10} {'P(payout)':>10}")
    rows = [head, "  " + "-" * (len(head) - 2)]
    for r in ladder:
        rows.append(
            f"  {r['scenario']:13} {r['net_pnl']:11,.0f} {r.get('per_trade', 0.0):13,.2f} "
            f"{r.get('max_drawdown', 0.0):10,.0f} "
            f"{str(not r.get('liquidated', False)):>13} "
            f"{r.get('p_target', float('nan')):10.1%} "
            f"{r.get('p_payout', float('nan')):10.1%}")
    rows.append("  The headline is CONSERVATIVE. IDEAL is printed only so the distance "
                "between them is visible as a number.")
    rows.append("  NOTE: the Sharpe and Sortino printed in the run's own EXECUTION LADDER "
                "table are DAILY-clock ratios scaled by sqrt(252). On a sample this short "
                "that is an arithmetic rescaling, not an annual expectation; nothing in "
                "this scorecard is annualised.")
    return "\n".join(rows)


__all__ = ["CRITERIA", "Classification", "Distribution", "FRAGILE", "INCONCLUSIVE",
           "MAE_BASIS", "MonteCarlo", "NEGATIVE", "PROMISING", "PeriodRow",
           "ROBUST_POSITIVE", "RegimeBreakdown", "RiskStats", "Statistics",
           "StrategyReport", "Summary", "TimeDistribution", "TradeStats", "UNTESTABLE",
           "build"]
