"""Account-level results, built from the canonical ledger and nothing else.

WHAT THIS ANSWERS THAT P&L DOES NOT
-------------------------------------
A strategy result is not complete when the P&L is known. Two strategies with the same net
profit can differ completely at the account level, because the account has a floor that
moves, a daily limit, a target, a size ceiling and a payout clock. This module reports the
second half:

    strategy profitable?     the P&L layer answers that
    account survives?        this layer
    target reached?          this layer
    payout rules satisfied?  the payout layer below, kept deliberately separate

Those four are never collapsed into one number. A strategy can be profitable and unfundable,
and reporting only "net P&L +$4,200" for such a run would be the most flattering thing this
engine could say.

ONE LEDGER, TWO CONSUMERS
--------------------------
`CanonicalLedger.twin_days()` is the ONLY input to the account simulation. The fills, the
prices, the costs and the intraday marks are the same objects the P&L layer summed. Nothing
here re-walks a bar or re-derives a fill.

FOUR RETURNS THAT ARE NOT THE SAME NUMBER
-------------------------------------------
`ReturnBasis` reports all four separately because conflating them is how a backtest reports
an impossible percentage:

    on notional          P&L over the contract value actually controlled. The number a
                         futures trader means by "return", and the smallest of the four.
    on account balance   P&L over the $50,000 the account is denominated in. Topstep does
                         not require that capital to be posted, so this flatters badly.
    per contract         P&L divided by contracts held. A scale-free unit, not a return.
    under constraints    what the ACCOUNT actually realised once the floor, the daily
                         limit and liquidation are applied. This is the only one that
                         corresponds to money.

THE PAYOUT RULES ARE CONFIGURATION, NOT CONSTANTS
---------------------------------------------------
`PayoutRuleSet` is versioned, carries the source of every value, and records the confidence
`topstep.py` assigns it. A rule below DOC confidence is listed in `unverified` and travels
with the result rather than being silently applied as though published.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_brain.markets.futures_cme import paths as pa
from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme import twin as tw
from quant_brain.research import topstep_reference as tr
from quant_brain.research.canonical_ledger import CanonicalLedger, ExecutionPathMode

#: Sessions per resampled path when estimating the probabilities. Equal to the real sample
#: by default, so "probability of surviving the test period" means exactly that.
DEFAULT_REPS = 400
DEFAULT_BLOCK = 10


# ======================================================================================
# PAYOUT RULES - EXPLICIT AND VERSIONED
# ======================================================================================

@dataclass(frozen=True)
class PayoutRuleSet:
    """The payout rules in force for a run, with their provenance attached.

    Versioned because Topstep changes them and a result computed under last quarter's rules
    is not comparable to one computed under this quarter's. `sources` carries the help-centre
    citation for every value, and `unverified` names any rule this repository could not
    confirm at DOC confidence - those are reported, never quietly assumed.
    """

    version: str
    account_size: int
    retrieved: dt.date
    winning_days_required: int
    winning_day_minimum: float
    balance_share: float
    ceiling: float
    minimum: float
    profit_split: float
    mll_resets_on_payout: bool
    sources: dict[str, str] = field(default_factory=dict)
    unverified: tuple[str, ...] = ()

    @classmethod
    def as_documented(cls, size: int = 50_000) -> PayoutRuleSet:
        """Built from `topstep.py`'s cited rules, never from literals repeated here.

        Repeating the numbers would mean a rulebook correction stopped reaching the payout
        layer - the values would still agree with the old page and nothing would fail.
        """
        rules = {
            "winning_days_required": ts.XFA_WINNING_DAYS,
            "winning_day_minimum": ts.XFA_WINNING_DAY_MIN,
            "balance_share": ts.XFA_BALANCE_SHARE,
            "ceiling": ts.XFA_STANDARD_CAP_BY_SIZE[size],
            "minimum": ts.PAYOUT_MINIMUM,
            "profit_split": ts.PROFIT_SPLIT,
            "mll_resets_on_payout": ts.MLL_RESETS_ON_PAYOUT,
        }
        weak = tuple(name for name, rule in rules.items()
                     if rule.confidence < ts.Confidence.DOC)
        return cls(
            version=f"topstep-{size // 1000}k-{ts.RETRIEVED.isoformat()}",
            account_size=size, retrieved=ts.RETRIEVED,
            winning_days_required=int(ts.XFA_WINNING_DAYS.value),
            winning_day_minimum=float(ts.XFA_WINNING_DAY_MIN.value),
            balance_share=float(ts.XFA_BALANCE_SHARE.value),
            ceiling=float(ts.XFA_STANDARD_CAP_BY_SIZE[size].value),
            minimum=float(ts.PAYOUT_MINIMUM.value),
            profit_split=float(ts.PROFIT_SPLIT.value),
            mll_resets_on_payout=bool(ts.MLL_RESETS_ON_PAYOUT.value),
            sources={name: rule.cite() for name, rule in rules.items()},
            unverified=weak)

    def to_policy(self, *, fraction: float = 1.0,
                  min_buffer_after: float = 0.0) -> tw.PayoutPolicy:
        """The withdrawal DECISION, kept separate from the withdrawal RULES.

        How much of the eligible cap to take and how much buffer to leave behind is a
        trader's choice with real risk consequences; what makes a payout legal is Topstep's.
        Mixing them would make a policy change look like a rule change.
        """
        return tw.PayoutPolicy(fraction=fraction, min_buffer_after=min_buffer_after)


@dataclass
class PayoutAnalysis:
    """Payout eligibility, reported apart from profitability on purpose."""

    rules: PayoutRuleSet
    policy_fraction: float
    policy_min_buffer_after: float
    eligible_sessions: int
    first_eligible_session: dt.date | None
    sessions_to_first_eligible: int | None
    payouts: list[tuple[dt.date, float]]
    total_paid: float
    trader_share_of_total: float
    p_reach_payout_eligibility: float
    notes: list[str] = field(default_factory=list)


# ======================================================================================
# THE ACCOUNT RESULT
# ======================================================================================

@dataclass
class ReferenceCrossCheck:
    """Production twin versus `topstep_reference`, field by field."""

    fields_compared: int
    mismatches: list[str] = field(default_factory=list)

    @property
    def agrees(self) -> bool:
        return not self.mismatches


@dataclass
class MonthlyAccountRow:
    month: str
    sessions: int
    starting_equity: float
    ending_equity: float
    gross_pnl: float
    net_pnl: float
    return_on_account_pct: float
    trades: int
    win_rate: float
    average_trade: float
    median_trade: float
    profit_factor: float
    max_drawdown: float
    max_intraday_drawdown: float
    min_mll_buffer: float
    dll_breaches: int
    liquidated: bool
    target_reached: bool
    forced_flatten_pnl: float


@dataclass
class ReturnBasis:
    """Four different denominators. Never one number called "the return"."""

    net_pnl: float
    mean_notional: float
    return_on_notional_pct: float
    account_starting_balance: float
    return_on_account_pct: float
    pnl_per_contract: float
    pnl_under_account_constraints: float
    note: str = ("`pnl_under_account_constraints` is what the ACCOUNT realised - the daily "
                 "limit applied and the path stopped at liquidation. The other three are "
                 "strategy-level and ignore the account entirely.")


@dataclass
class AccountResult:
    """The account half of a canonical result. Every field is a fact about one ledger."""

    # -- identity ---------------------------------------------------------------------
    execution_path_mode: ExecutionPathMode
    scenario: str
    slippage_ticks: float
    account_size: int
    combine_profile: str
    xfa_profile: str
    daily_loss_limit: float | None

    # -- the account trajectory -------------------------------------------------------
    terminal_stage: str
    liquidated: bool
    liquidation_session: dt.date | None
    liquidation_reason: str
    target_reached: bool
    combine_sessions: int | None
    combine_attempts: int

    days_survived: int
    days_traded: int
    total_trades: int
    winning_days: int
    losing_days: int
    flat_days: int
    forced_flatten_sessions: int
    forced_flatten_pnl: float

    contract_limit_ok: bool
    contract_limit_detail: str

    max_drawdown: float
    max_intraday_drawdown: float
    min_mll_buffer: float
    min_mll_buffer_funded: float
    min_dll_buffer: float | None
    #: The closest the account came to its limit at ANY mark, not just at a close. This is
    #: the number the path mode moves; `min_mll_buffer` is measured post-settlement and a
    #: deeper intraday path can leave it untouched.
    min_mll_buffer_intraday: float
    min_dll_buffer_intraday: float | None
    dll_capped_sessions: int

    starting_balance: float
    ending_balance: float
    peak_balance: float
    ending_mll: float
    ending_dll: float | None
    final_position: float
    final_equity: float

    # -- state paths ------------------------------------------------------------------
    trace: list[tw.DayState]
    intraday_equity: np.ndarray

    # -- analytics --------------------------------------------------------------------
    monthly: list[MonthlyAccountRow]
    returns: ReturnBasis
    payout: PayoutAnalysis

    # -- probabilities, resampled -----------------------------------------------------
    resample_reps: int
    resample_block: int
    p_survive_period: float
    p_target_before_violation: float
    p_payout_eligible: float
    probability_note: str

    # -- the second opinion -----------------------------------------------------------
    cross_check: ReferenceCrossCheck

    def mll_path(self) -> pd.DataFrame:
        """The limit levels the breach test actually used, one row per session."""
        return pd.DataFrame([{
            "session": d.day, "phase": d.phase, "opening_balance": d.opening_balance,
            "closing_balance": d.closing_balance, "mll": d.mll, "dll": d.dll,
            "buffer_mll": d.buffer_mll, "buffer_dll": d.buffer_dll,
            "worst_buffer_mll": d.worst_buffer_mll,
            "worst_buffer_dll": d.worst_buffer_dll, "worst_mark": d.worst_mark,
            "settled_pnl": d.settled_pnl, "survived": d.survived, "event": d.event,
        } for d in self.trace])


# ======================================================================================
# BUILDING IT
# ======================================================================================

def _contract_limit(ledger: CanonicalLedger, size: int) -> tuple[bool, str]:
    """Was the position ever larger than the firm allows on this account?

    Checked against the root actually traded rather than against the micro-equivalent
    allowance, because five ES and fifty MES are one allowance stated in two units and
    applying the micro number to a mini overstates it tenfold.
    """
    # The published ceiling (5 minis / 50 micros on a $50K account), taken from the Combine
    # profile. NOT the Express Funded scaling ladder: that is a separate, UNVERIFIED rule
    # that throttles size by profit, and applying it here reported one ES contract as a
    # breach of a limit that is actually five.
    profile = ts.combine(size)
    cap = profile.max_contracts_for(ledger.instrument, profit=0.0, held_equivalents=0.0)
    held = ledger.contracts
    if cap is None:
        return False, (f"{ledger.instrument} is not a product this account may trade; "
                       f"permitted roots are {', '.join(ts.PERMITTED_PRODUCTS)}")
    if held > cap:
        return False, (f"{held} {ledger.instrument} exceeds the {cap} permitted on a "
                       f"${size:,} account")
    return True, f"{held} of {cap} {ledger.instrument} permitted"


def _monthly(ledger: CanonicalLedger, result: tw.TwinResult,
             account_size: int) -> list[MonthlyAccountRow]:
    """Calendar-month analytics from the SAME ledger the account was simulated on."""
    trades = ledger.trade_frame()
    by_day = {d.day: d for d in result.trace}
    rows: list[MonthlyAccountRow] = []
    running = 0.0
    months: dict[str, list] = {}
    for s in ledger.sessions:
        months.setdefault(str(pd.Timestamp(s.day).to_period("M")), []).append(s)

    for month, group in months.items():
        start_equity = running
        net = float(sum(s.realized_net for s in group))
        gross = float(sum(s.realized_gross for s in group))
        running += net
        daily = np.asarray([s.realized_net for s in group], dtype=float)
        eq = np.cumsum(daily)
        tsub = trades[trades["month"] == month] if len(trades) else trades
        nt = tsub["net_pnl"].to_numpy(dtype=float) if len(tsub) else np.array([])
        wins, losses = nt[nt > 0], nt[nt < 0]
        buffers = [by_day[s.day].worst_buffer_mll for s in group if s.day in by_day]
        rows.append(MonthlyAccountRow(
            month=month, sessions=len(group),
            starting_equity=start_equity, ending_equity=running,
            gross_pnl=gross, net_pnl=net,
            return_on_account_pct=100.0 * net / float(account_size),
            trades=int(len(tsub)),
            win_rate=float((nt > 0).mean()) if len(nt) else 0.0,
            average_trade=float(nt.mean()) if len(nt) else 0.0,
            median_trade=float(np.median(nt)) if len(nt) else 0.0,
            profit_factor=(float(wins.sum() / -losses.sum())
                           if len(losses) and losses.sum() < 0 else float("nan")),
            max_drawdown=float((eq - np.maximum.accumulate(eq)).min()) if len(eq) else 0.0,
            max_intraday_drawdown=min((s.max_intraday_drawdown for s in group), default=0.0),
            min_mll_buffer=float(min(buffers)) if buffers else float("nan"),
            dll_breaches=sum(1 for s in group
                             if s.day in by_day and by_day[s.day].event == "dll_capped"),
            liquidated=any(s.day in by_day and not by_day[s.day].survived for s in group),
            target_reached=False,
            forced_flatten_pnl=float(sum(t.net_pnl for s in group for t in s.trades
                                         if t.forced_flatten)),
        ))
    if rows and result.combine_days is not None:
        passed_on = ledger.sessions[min(result.combine_days - 1,
                                        len(ledger.sessions) - 1)].day
        stamp = str(pd.Timestamp(passed_on).to_period("M"))
        for r in rows:
            if r.month == stamp:
                r.target_reached = True
    return rows


def _cross_check(a: tw.TwinResult, b: tr.ReferenceResult,
                 dll: float | None) -> ReferenceCrossCheck:
    """Every decision-relevant field, production twin versus independent reference."""
    checks: list[tuple[str, object, object]] = [
        ("terminal_stage", a.terminal.value, b.terminal),
        ("days_survived", a.days, b.days),
        ("combine_attempts", a.combine_attempts, b.combine_attempts),
        ("combine_sessions", a.combine_days, b.combine_days),
        ("liquidated", a.terminal is ts.TopstepStage.LIQUIDATED, b.terminal == "liquidated"),
        ("liquidation_session", a.breach_day, b.breach_day),
        ("target_reached", a.reached_funding, b.target_reached),
        ("payout_count", len(a.payouts), len(b.payouts)),
        ("total_paid", round(a.total_paid, 6), round(b.total_paid, 6)),
        ("min_buffer", round(a.min_buffer, 6), round(b.min_buffer, 6)),
        ("min_buffer_funded", round(a.min_buffer_funded, 6),
         round(b.min_buffer_funded, 6)),
        ("peak_balance", round(_peak(a), 6), round(b.peak_balance, 6)),
        # The limit IN FORCE during the last session, taken from both sides at the same
        # moment - before that session's marks. An earlier version compared the twin's
        # pre-session level against the reference's post-settlement one and reported a
        # mismatch on every profitable run; the two were simply different instants.
        ("mll_at_last_session_open",
         round(a.trace[-1].mll, 6) if a.trace else 0.0,
         round(_last_session_floor(b), 6)),
        # WHICH rule ended the account, not the sentence describing it. The two
        # implementations narrate a breach in different words on purpose - comparing the
        # strings would fail on wording and pass on substance, which is backwards.
        ("liquidation_kind", _twin_breach_kind(a, dll), _ref_breach_kind(b, dll)),
        ("final_position_is_flat", 0.0, b.final_position),
        ("starting_balance",
         round(float(a.trace[0].opening_balance), 6) if a.trace else 0.0,
         round(b.starting_balance, 6)),
    ]
    if a.terminal is not ts.TopstepStage.LIQUIDATED:
        checks.append(("ending_balance", round(a.final_balance, 6),
                       round(b.final_balance, 6)))
    else:
        # A dead account's reported balance is a naming convention, not a decision; the
        # divergence is measured and explained in docs/TOPSTEP_TWIN_AUDIT.md.
        pass
    if dll is not None:
        checks.append(("dll_armed", True, b.events is not None))

    out = ReferenceCrossCheck(fields_compared=len(checks))
    for name, x, y in checks:
        if x != y:
            out.mismatches.append(f"{name}: twin={x!r} reference={y!r}")
    return out


#: The ONE equivalence the cross-check accepts, and only with the daily limit armed.
#:
#: A capped session moves the balance down by exactly the daily limit while the maximum-loss
#: limit stays put, so the next session's daily level can land EXACTLY on it. On that tie the
#: twin books the day at -DLL and finds the settled balance at the floor ("dll_at_the_floor")
#: while the reference stops at the touch and calls it an MLL breach ("intraday"). Both
#: liquidate, on the same session. Flipping the tie rule was replayed over 20,000 DLL-armed
#: paths in `test_the_tie_between_the_two_limits_can_never_change_survival` and changed
#: survival ZERO times - it moves the reason string and a dead account's reported balance and
#: nothing else. Named here rather than skipped, so the exception is visible in the code that
#: grants it. See docs/TOPSTEP_TWIN_AUDIT.md.
_TIE_EQUIVALENT = frozenset({"dll_at_the_floor", "intraday"})


def _twin_breach_kind(a: tw.TwinResult, dll: float | None) -> str:
    """Reduce the twin's breach SENTENCE to the rule that fired, so it can be compared.

    The reference reports a token; the twin reports a human sentence. Comparing the strings
    would fail on wording and pass on substance, which is backwards.
    """
    if a.terminal is not ts.TopstepStage.LIQUIDATED:
        return ""
    reason = a.breach_reason
    kind = ("intraday" if reason.startswith("intraday equity")
            else "eod" if reason.startswith("end-of-day balance")
            else "dll_at_the_floor" if reason.startswith("daily loss limit")
            else reason)
    return "tie" if (dll is not None and kind in _TIE_EQUIVALENT) else kind


def _ref_breach_kind(b: tr.ReferenceResult, dll: float | None) -> str:
    """The reference's token, folded through the same equivalence."""
    kind = b.breach_kind
    return "tie" if (dll is not None and kind in _TIE_EQUIVALENT) else kind


def _last_session_floor(b: tr.ReferenceResult) -> float:
    """The floor the reference's last TRADED session opened under.

    `passed_combine`, `payout` and `restart_combine` are bookkeeping entries in the middle
    of a day, not sessions, and they carry no opening floor. Reading the transcript's last
    row blindly would compare a session's limit against a payout's.
    """
    sessions = ("survived", "dll_capped", "breach_intraday", "breach_eod")
    for ev in reversed(b.events):
        if ev.what in sessions:
            return ev.floor_at_open
    return 0.0


def _peak(a: tw.TwinResult) -> float:
    """The highest end-of-day balance the trace recorded, on the account that was live."""
    if not a.trace:
        return 0.0
    combine = [d for d in a.trace if d.phase == "trading_combine"]
    funded = [d for d in a.trace if d.phase != "trading_combine"]
    pool = funded or combine
    start = pool[0].opening_balance
    return max([start, *[d.closing_balance for d in pool if d.survived]])


def _probabilities(days, twin_obj: tw.TopstepTwin, *, reps: int, block: int,
                   seed: int) -> tuple[float, float, float, str]:
    """Resampled survival, target and payout rates, with the method stated on the tin.

    Moving-block bootstrap over the SAME `TwinDay` objects the deterministic run used, so
    the intraday paths resampled are the real ones and not a reconstruction. The block keeps
    losing runs intact, which is the dependence that decides a barrier problem.

    These are PATH-MODEL SCENARIO ESTIMATES over the historical sample, not forecasts.
    """
    if len(days) < 2:
        return (float("nan"), float("nan"), float("nan"),
                "fewer than 2 sessions: not resampleable")
    sample = pa.moving_block(days, block=block, reps=reps, seed=seed)
    results = [twin_obj.run(p) for p in sample]
    n = len(results)
    survive = sum(r.terminal is not ts.TopstepStage.LIQUIDATED for r in results) / n
    target = sum(r.combine_days is not None for r in results) / n
    payout = sum(bool(r.payouts) or r.terminal is ts.TopstepStage.PAYOUT_ELIGIBLE
                 for r in results) / n
    note = (f"HISTORICAL / PATH-MODEL SCENARIO ESTIMATE from {n} moving-block resamples "
            f"(block {block}) of the {len(days)} observed sessions. Not a forecast: it "
            f"reuses the same sessions in a different order and inherits every bias in "
            f"the sample.")
    return survive, target, payout, note


def build_account_result(ledger: CanonicalLedger, *, account_size: int = 50_000,
                         daily_loss_limit: float | None = None,
                         payout_rules: PayoutRuleSet | None = None,
                         payout_fraction: float = 0.0,
                         payout_min_buffer_after: float = 0.0,
                         max_combine_attempts: int = 1,
                         reps: int = DEFAULT_REPS, block: int = DEFAULT_BLOCK,
                         seed: int = 0) -> AccountResult:
    """Run the account simulation on one canonical ledger. No second trade stream."""
    rules = payout_rules or PayoutRuleSet.as_documented(account_size)
    days = ledger.twin_days()
    policy = rules.to_policy(fraction=payout_fraction,
                             min_buffer_after=payout_min_buffer_after)
    twin_obj = tw.TopstepTwin(account_size, daily_loss_limit=daily_loss_limit,
                              max_combine_attempts=max_combine_attempts,
                              payout_policy=policy)
    result = twin_obj.run(days)

    ref = None
    cross = ReferenceCrossCheck(fields_compared=0,
                                mismatches=["reference not run: it covers the $50,000 "
                                            "path only"])
    if account_size == tr.SIZE:
        ref = tr.run_reference(days, daily_loss_limit=daily_loss_limit,
                               max_combine_attempts=max_combine_attempts,
                               payout_fraction=payout_fraction,
                               min_buffer_after=payout_min_buffer_after)
        cross = _cross_check(result, ref, daily_loss_limit)

    # What the ACCOUNT realised, which is not the strategy's P&L. Surviving sessions settle
    # normally; the session that liquidates the account settles at the level it was closed
    # out on, because Topstep flattens AT the limit. A strategy that lost $2,100 on the day
    # it was liquidated cost the account exactly its $2,000 of room, and reporting the
    # strategy figure would overstate the loss - just as reporting the profit it made after
    # liquidation would overstate the gain.
    under_constraints = 0.0
    for d in result.trace:
        if d.survived:
            under_constraints += d.settled_pnl
        elif d.event == "breach_intraday":
            under_constraints += d.mll - d.opening_balance
        else:
            under_constraints += d.settled_pnl
    net_pnl = float(ledger.daily().sum())
    prices = [t.entry_price for s in ledger.sessions for t in s.trades]
    mean_notional = (float(np.mean(prices)) * ledger.multiplier * ledger.contracts
                     if prices else 0.0)

    daily_vals = ledger.daily().to_numpy(dtype=float)
    intraday = ledger.intraday_equity()
    dll_close = [d.buffer_dll for d in result.trace if d.buffer_dll is not None]
    dll_worst = [d.worst_buffer_dll for d in result.trace
                 if d.worst_buffer_dll is not None]

    p_survive, p_target, p_payout, note = _probabilities(
        days, twin_obj, reps=reps, block=block, seed=seed)

    ok, detail = _contract_limit(ledger, account_size)
    monthly = _monthly(ledger, result, account_size)
    eligible = sum(1 for d in result.trace if d.phase == "payout_eligible")
    first = next((d.day for d in result.trace if d.phase == "payout_eligible"), None)
    order = [s.day for s in ledger.sessions]

    payout = PayoutAnalysis(
        rules=rules, policy_fraction=payout_fraction,
        policy_min_buffer_after=payout_min_buffer_after,
        eligible_sessions=eligible, first_eligible_session=first,
        sessions_to_first_eligible=(order.index(first) + 1 if first in order else None),
        payouts=list(result.payouts), total_paid=result.total_paid,
        trader_share_of_total=result.total_paid * rules.profit_split,
        p_reach_payout_eligibility=p_payout,
        notes=([f"rules below DOC confidence, applied but flagged: "
                f"{', '.join(rules.unverified)}"] if rules.unverified else []))

    return AccountResult(
        execution_path_mode=ledger.mode, scenario=ledger.scenario,
        slippage_ticks=ledger.slippage_ticks, account_size=account_size,
        combine_profile=twin_obj.combine_profile.name,
        xfa_profile=twin_obj.xfa_profile.name, daily_loss_limit=daily_loss_limit,
        terminal_stage=result.terminal.value,
        liquidated=result.terminal is ts.TopstepStage.LIQUIDATED,
        liquidation_session=result.breach_day, liquidation_reason=result.breach_reason,
        target_reached=result.reached_funding, combine_sessions=result.combine_days,
        combine_attempts=result.combine_attempts,
        days_survived=result.days, days_traded=ledger.days_traded,
        total_trades=ledger.total_trades,
        winning_days=int((daily_vals > 0).sum()), losing_days=int((daily_vals < 0).sum()),
        flat_days=int((daily_vals == 0).sum()),
        forced_flatten_sessions=sum(1 for s in ledger.sessions if s.forced_flatten),
        forced_flatten_pnl=float(sum(t.net_pnl for s in ledger.sessions
                                     for t in s.trades if t.forced_flatten)),
        contract_limit_ok=ok, contract_limit_detail=detail,
        max_drawdown=float((ledger.equity_curve()
                            - np.maximum.accumulate(ledger.equity_curve())).min())
        if len(ledger.sessions) else 0.0,
        max_intraday_drawdown=float((intraday - np.maximum.accumulate(intraday)).min())
        if intraday.size else 0.0,
        min_mll_buffer=result.min_buffer, min_mll_buffer_funded=result.min_buffer_funded,
        min_dll_buffer=float(min(dll_close)) if dll_close else None,
        min_mll_buffer_intraday=float(min((d.worst_buffer_mll for d in result.trace),
                                          default=0.0)),
        min_dll_buffer_intraday=float(min(dll_worst)) if dll_worst else None,
        dll_capped_sessions=sum(1 for d in result.trace if d.event == "dll_capped"),
        starting_balance=float(twin_obj.combine_profile.starting_balance),
        ending_balance=result.final_balance,
        peak_balance=_peak(result),
        ending_mll=result.trace[-1].mll if result.trace else 0.0,
        ending_dll=result.trace[-1].dll if result.trace else None,
        final_position=0.0, final_equity=result.final_balance,
        trace=result.trace, intraday_equity=intraday,
        monthly=monthly,
        returns=ReturnBasis(
            net_pnl=net_pnl, mean_notional=mean_notional,
            return_on_notional_pct=(100.0 * net_pnl / mean_notional
                                    if mean_notional else float("nan")),
            account_starting_balance=float(account_size),
            return_on_account_pct=100.0 * net_pnl / float(account_size),
            pnl_per_contract=net_pnl / ledger.contracts if ledger.contracts else float("nan"),
            pnl_under_account_constraints=under_constraints),
        payout=payout,
        resample_reps=reps, resample_block=block,
        p_survive_period=p_survive, p_target_before_violation=p_target,
        p_payout_eligible=p_payout, probability_note=note,
        cross_check=cross)


__all__ = ["AccountResult", "MonthlyAccountRow", "PayoutAnalysis", "PayoutRuleSet",
           "ReferenceCrossCheck", "ReturnBasis", "build_account_result"]
