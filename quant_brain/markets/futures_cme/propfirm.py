"""Prop-firm account rules, as a deterministic risk engine and a simulator.

WHY THIS IS THE CENTRE OF THE FUTURES BRANCH
--------------------------------------------
Part 25: the strategic objective is to pass futures prop-firm evaluations, build capital,
and deploy it into options later. Part 6 states the consequence bluntly - "Do NOT optimize
futures solely for CAGR or Sharpe." A prop-firm account is not a portfolio. It is a game
with an absorbing barrier: one breach of a trailing threshold ends the account regardless of
what the equity curve did before it. A strategy with a higher Sharpe and a fatter left tail
is *worse* here than a duller one that never touches the floor.

So the objective this module is built to measure is:

    maximize   E[capital accumulated]
    subject to P(breach) small, under real costs and real slippage

which needs three things the existing harness cannot express: the rules themselves
(`PropFirmProfile`), a gate that cannot be argued with (`PropFirmRiskEngine`), and a way to
run a strategy's session P&L through those rules many times to get a *distribution* rather
than a single backtest number (`PropFirmSimulator`, `evaluate`).

WHAT IS DELIBERATELY GENERIC
----------------------------
Part 5: "Do not hard-code one firm's rules into the core." No firm name appears in this
module. `PropFirmProfile` is a set of parameters; concrete firms are configuration in
`profiles.py`. The three trailing-drawdown conventions in the wild (none, end-of-day, and
intraday including unrealized) are a mode on the profile, because they are the single
biggest driver of whether a given strategy survives and firms genuinely differ on it.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from quant_brain.core.execution import OrderIntent
from quant_brain.core.risk import RiskDecision, RiskEngine


class TrailingMode(str, enum.Enum):
    """How a firm's drawdown threshold follows the account up.

    The difference is not cosmetic. On the same equity path, INTRADAY can fail an account
    that EOD would pass, because it trails the highest *unrealized* mark - a trade that goes
    +$800 and comes back to +$100 has raised the floor by $800 under INTRADAY and by nothing
    under EOD until the day closes.
    """

    NONE = "none"          # static floor from the starting balance
    EOD = "eod"            # trails the highest end-of-day balance
    INTRADAY = "intraday"  # trails the highest intraday equity, unrealized included


class Outcome(str, enum.Enum):
    PASSED = "passed"
    FAILED_TRAILING = "failed_trailing"
    FAILED_DAILY_LOSS = "failed_daily_loss"
    FAILED_MAX_DRAWDOWN = "failed_max_drawdown"
    FAILED_CONSISTENCY = "failed_consistency"
    IN_PROGRESS = "in_progress"

    @property
    def is_failure(self) -> bool:
        return self.name.startswith("FAILED")


@dataclass(frozen=True)
class PropFirmProfile:
    """One account's rule set. Pure configuration - no firm-specific code anywhere.

    Money amounts are USD and absolute, not percentages, because that is how every firm
    states them and converting to percent loses the distinction between a $2,000 limit on a
    $50k account and the same limit after the account has grown.
    """

    name: str
    starting_balance: float

    # --- the two limits that end accounts ------------------------------------------------
    #: Loss from the day's starting balance that ends the day (or the account - see
    #: `daily_loss_ends_account`). None disables.
    daily_loss_limit: float | None = None
    #: Size of the trailing drawdown window in dollars. With TrailingMode.NONE this is a
    #: static floor at `starting_balance - max_drawdown`.
    max_drawdown: float | None = None
    trailing_mode: TrailingMode = TrailingMode.EOD
    #: Level at which the trailing threshold stops following. Many firms lock the threshold
    #: once it reaches the starting balance, so the account can never fail below breakeven
    #: after it has earned the buffer. None means it trails forever.
    trailing_locks_at: float | None = None
    #: Some firms treat a daily-loss breach as "day over, come back tomorrow", others as an
    #: account failure. Both exist; the difference changes expected capital materially.
    daily_loss_ends_account: bool = True

    # --- passing -------------------------------------------------------------------------
    profit_target: float | None = None
    min_trading_days: int = 0
    #: Consistency: no single day may contribute more than this fraction of total profit.
    #: Checked at the moment the target is reached, which is when firms check it.
    max_single_day_profit_share: float | None = None

    # --- position constraints ------------------------------------------------------------
    #: Total contracts across all symbols.
    max_total_contracts: int | None = None
    #: Per-symbol contract cap, e.g. {"MES": 10, "ES": 1}.
    max_contracts_per_symbol: dict[str, int] = field(default_factory=dict)
    #: Notional exposure ceiling in dollars, if the firm states one.
    max_notional: float | None = None

    # --- session constraints ---------------------------------------------------------------
    allow_overnight: bool = False
    #: Minutes before the session close by which the book must be flat. Expressed relative to
    #: the close so it is correct on an early close - the AUD-07 lesson, applied here rather
    #: than repeated as a literal bar index.
    flat_before_close_minutes: int = 15
    #: Windows in which new risk may not be opened, as (start, end) local times. News
    #: restrictions are the usual reason.
    blackout_windows: tuple[tuple[dt.time, dt.time], ...] = ()

    # --- economics -------------------------------------------------------------------------
    #: What passing is worth, and what an attempt costs. Needed for expected capital, which
    #: is the objective - a 90% pass rate on a $600 evaluation that pays $2,000 is a
    #: different business from a 40% pass rate on a $150 evaluation that pays $3,000.
    evaluation_fee: float = 0.0
    payout_on_pass: float = 0.0
    profit_split: float = 0.9

    def floor_for(self, peak: float) -> float:
        """The equity level at which this account is dead, given the running peak.

        With TrailingMode.NONE the peak is ignored and the floor is static. With a lock
        level the threshold stops climbing once it reaches it.
        """
        if self.max_drawdown is None:
            return -math.inf
        if self.trailing_mode is TrailingMode.NONE:
            return self.starting_balance - self.max_drawdown
        threshold = peak - self.max_drawdown
        if self.trailing_locks_at is not None:
            threshold = min(threshold, self.trailing_locks_at)
        return threshold

    def to_json(self) -> str:
        d = dataclasses.asdict(self)
        d["trailing_mode"] = self.trailing_mode.value
        d["blackout_windows"] = [[a.isoformat(), b.isoformat()] for a, b in self.blackout_windows]
        return json.dumps(d, indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict) -> PropFirmProfile:
        d = dict(d)
        d["trailing_mode"] = TrailingMode(d.get("trailing_mode", "eod"))
        d["blackout_windows"] = tuple(
            (dt.time.fromisoformat(a), dt.time.fromisoformat(b))
            for a, b in d.get("blackout_windows", [])
        )
        d["max_contracts_per_symbol"] = dict(d.get("max_contracts_per_symbol", {}))
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = set(d) - known
        if unknown:
            # A typo'd rule name silently disabling a limit is exactly the failure this
            # whole module exists to prevent. Refuse the profile instead.
            raise ValueError(f"{d.get('name','profile')}: unknown rule(s) {sorted(unknown)}")
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def load(cls, path: str | Path) -> PropFirmProfile:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class AccountState:
    """Live account arithmetic, shared by the risk engine and the simulator.

    Kept mutable and separate from the profile so one profile can drive many accounts (the
    Monte Carlo path in `evaluate` runs hundreds).
    """

    profile: PropFirmProfile
    balance: float = 0.0                 # realized only
    peak: float = 0.0                    # drives the trailing floor
    day_start_balance: float = 0.0
    unrealized: float = 0.0
    contracts: dict[str, int] = field(default_factory=dict)
    trading_days: int = 0
    daily_pnl: list[float] = field(default_factory=list)
    outcome: Outcome = Outcome.IN_PROGRESS

    def __post_init__(self) -> None:
        if self.balance == 0.0:
            self.balance = self.profile.starting_balance
        self.day_start_balance = self.balance
        self.peak = max(self.peak, self.balance)

    @property
    def equity(self) -> float:
        """Balance plus open P&L. The number an INTRADAY trailing rule watches."""
        return self.balance + self.unrealized

    @property
    def floor(self) -> float:
        return self.profile.floor_for(self.peak)

    @property
    def buffer(self) -> float:
        """Dollars between current equity and the floor. The account's real risk budget."""
        return self.equity - self.floor

    @property
    def day_pnl(self) -> float:
        return self.equity - self.day_start_balance

    @property
    def total_contracts(self) -> int:
        return sum(abs(v) for v in self.contracts.values())

    def mark_peak(self, *, intraday: bool) -> None:
        """Advance the trailing peak under the profile's convention."""
        mode = self.profile.trailing_mode
        if mode is TrailingMode.INTRADAY and intraday:
            self.peak = max(self.peak, self.equity)
        elif mode is TrailingMode.EOD and not intraday:
            self.peak = max(self.peak, self.balance)


class PropFirmRiskEngine(RiskEngine):
    """The gate between a futures signal and execution. Deterministic, non-negotiable.

    Reads `AccountState` and the profile; knows nothing about models, predictions or
    confidence. There is no argument a caller can make to this class - it takes an
    `OrderIntent` and nothing else. That is the Part 5 requirement made structural.

    Flatten intents bypass everything via `RiskEngine.__call__`, which is why the account can
    always be closed even when every other rule is breached.
    """

    name = "propfirm"

    def __init__(self, state: AccountState, *, contract_size: dict[str, int] | None = None):
        self.state = state
        #: How many contracts one unit of `intent.quantity` represents. Futures intents are
        #: already in contracts, so this defaults to 1 and exists for callers that size in
        #: something else.
        self.contract_size = contract_size or {}

    def evaluate(self, intent: OrderIntent) -> RiskDecision:
        p, s = self.state.profile, self.state
        sym = intent.symbol

        if s.outcome.is_failure:
            return RiskDecision.deny(f"account already {s.outcome.value}", "account_dead")

        # --- the two limits that end accounts, checked before any sizing -------------------
        if p.daily_loss_limit is not None and s.day_pnl <= -p.daily_loss_limit:
            return RiskDecision.deny(
                f"daily loss {s.day_pnl:,.0f} at or beyond limit {-p.daily_loss_limit:,.0f}",
                "daily_loss_limit")

        if s.equity <= s.floor:
            return RiskDecision.deny(
                f"equity {s.equity:,.0f} at or below floor {s.floor:,.0f}", "trailing_drawdown")

        per_unit = self.contract_size.get(sym, 1)
        want = int(abs(intent.quantity)) * per_unit
        if want <= 0:
            return RiskDecision.deny("zero-size intent", "zero_size")

        held = s.contracts.get(sym, 0)
        signed = intent.side.sign * want
        resulting_sym = abs(held + signed)
        resulting_total = s.total_contracts - abs(held) + resulting_sym

        decision = RiskDecision.allow(intent.quantity)

        # --- contract caps ------------------------------------------------------------------
        cap_sym = p.max_contracts_per_symbol.get(sym)
        if cap_sym is not None and resulting_sym > cap_sym:
            room = max(0, cap_sym - abs(held))
            decision = decision.merge(RiskDecision.reduce(
                room / per_unit if per_unit else 0,
                f"{sym} cap {cap_sym}: holding {abs(held)}, room for {room}",
                "max_contracts_per_symbol"))

        if p.max_total_contracts is not None and resulting_total > p.max_total_contracts:
            room = max(0, p.max_total_contracts - (s.total_contracts - abs(held)) - abs(held))
            decision = decision.merge(RiskDecision.reduce(
                room / per_unit if per_unit else 0,
                f"total cap {p.max_total_contracts}: holding {s.total_contracts}, room for {room}",
                "max_total_contracts"))

        return decision

    # -- session rules, asked separately because they gate the clock rather than the size ----

    def in_blackout(self, when: dt.time) -> bool:
        """True inside a configured news/blackout window."""
        for start, end in self.state.profile.blackout_windows:
            if start <= end:
                if start <= when <= end:
                    return True
            elif when >= start or when <= end:   # window wraps midnight
                return True
        return False

    def must_be_flat(self, minutes_to_close: int) -> bool:
        """True once the flat-before-close deadline has arrived.

        Takes minutes-to-close rather than a wall clock so it is automatically correct on an
        early close, per AUD-07. The caller gets that number from the market's
        `SessionCalendar`, not from a constant.
        """
        p = self.state.profile
        if p.allow_overnight:
            return False
        return minutes_to_close <= p.flat_before_close_minutes


@dataclass
class SessionPnL:
    """One trading session's outcome, as the research harness already produces it.

    `intraday_equity` is the within-session path relative to the day's start, and is only
    consulted under TrailingMode.INTRADAY. Supplying it is optional precisely because the
    existing harness does not produce it yet - a profile using EOD trailing gives a correct
    answer without it, and one using INTRADAY says so rather than pretending.
    """

    day: dt.date
    pnl: float
    intraday_equity: list[float] = field(default_factory=list)
    traded: bool = True


@dataclass
class SimulationResult:
    """What happened to one account over one path."""

    outcome: Outcome
    days: int
    final_balance: float
    peak_balance: float
    max_drawdown_seen: float
    min_buffer: float
    breach_day: dt.date | None
    breach_reason: str
    daily_pnl: list[float]
    profile: str

    @property
    def passed(self) -> bool:
        return self.outcome is Outcome.PASSED

    @property
    def net_profit(self) -> float:
        return self.final_balance - self.peak_start

    peak_start: float = 0.0


class PropFirmSimulator:
    """Run a session-P&L path through one firm's rules.

    Deliberately not a bar-level simulator. The research harness already produces
    per-session P&L net of commission and slippage (`intraday_backtest.py` does exactly
    this), and re-simulating at bar level here would duplicate that machinery and let the two
    disagree. What this adds is the part the harness cannot express: the absorbing barrier.

    The one place bar-level detail genuinely matters is INTRADAY trailing, and that is
    handled by consuming the optional `intraday_equity` path rather than by rebuilding it.
    """

    def __init__(self, profile: PropFirmProfile):
        self.profile = profile

    def run(self, sessions: list[SessionPnL]) -> SimulationResult:
        p = self.profile
        state = AccountState(profile=p)
        start = p.starting_balance
        peak_balance = start
        max_dd = 0.0
        min_buffer = state.buffer
        breach_day: dt.date | None = None
        reason = ""

        for s in sessions:
            state.day_start_balance = state.balance
            state.unrealized = 0.0

            # --- within-session path, only if the profile's trailing rule looks at it -------
            if p.trailing_mode is TrailingMode.INTRADAY and s.intraday_equity:
                for mark in s.intraday_equity:
                    state.unrealized = mark
                    state.mark_peak(intraday=True)
                    min_buffer = min(min_buffer, state.buffer)
                    if state.equity <= state.floor:
                        state.outcome = Outcome.FAILED_TRAILING
                        breach_day, reason = s.day, (
                            f"intraday equity {state.equity:,.0f} <= floor {state.floor:,.0f}")
                        break
                    if p.daily_loss_limit is not None and state.day_pnl <= -p.daily_loss_limit:
                        state.outcome = (Outcome.FAILED_DAILY_LOSS if p.daily_loss_ends_account
                                         else Outcome.IN_PROGRESS)
                        breach_day, reason = s.day, (
                            f"intraday daily loss {state.day_pnl:,.0f} <= "
                            f"{-p.daily_loss_limit:,.0f}")
                        break
                if state.outcome.is_failure:
                    break
                if reason and not p.daily_loss_ends_account:
                    # Day stopped out but the account survives: book the capped loss and move on.
                    state.balance -= p.daily_loss_limit or 0.0
                    state.unrealized = 0.0
                    state.daily_pnl.append(-(p.daily_loss_limit or 0.0))
                    state.trading_days += 1
                    reason = ""
                    continue

            # --- settle the session --------------------------------------------------------
            state.unrealized = 0.0
            realized = s.pnl
            if p.daily_loss_limit is not None and realized <= -p.daily_loss_limit:
                realized = -p.daily_loss_limit          # the stop-out caps the day
                if p.daily_loss_ends_account:
                    state.balance += realized
                    state.outcome = Outcome.FAILED_DAILY_LOSS
                    breach_day, reason = s.day, f"daily loss {s.pnl:,.0f} breached limit"
                    state.daily_pnl.append(realized)
                    break

            state.balance += realized
            state.daily_pnl.append(realized)
            if s.traded:
                state.trading_days += 1

            state.mark_peak(intraday=False)
            peak_balance = max(peak_balance, state.balance)
            max_dd = max(max_dd, peak_balance - state.balance)
            min_buffer = min(min_buffer, state.buffer)

            if state.balance <= state.floor:
                state.outcome = (Outcome.FAILED_MAX_DRAWDOWN
                                 if p.trailing_mode is TrailingMode.NONE
                                 else Outcome.FAILED_TRAILING)
                breach_day, reason = s.day, (
                    f"balance {state.balance:,.0f} <= floor {state.floor:,.0f}")
                break

            # --- passing ---------------------------------------------------------------------
            if p.profit_target is not None and state.balance - start >= p.profit_target:
                if state.trading_days < p.min_trading_days:
                    continue        # target hit but not enough days yet; keep going
                if not self._consistent(state, start):
                    state.outcome = Outcome.FAILED_CONSISTENCY
                    breach_day, reason = s.day, (
                        f"best day is more than {p.max_single_day_profit_share:.0%} of profit")
                    break
                state.outcome = Outcome.PASSED
                breach_day, reason = s.day, "profit target reached"
                break

        result = SimulationResult(
            outcome=state.outcome, days=len(state.daily_pnl), final_balance=state.balance,
            peak_balance=peak_balance, max_drawdown_seen=max_dd, min_buffer=min_buffer,
            breach_day=breach_day, breach_reason=reason, daily_pnl=list(state.daily_pnl),
            profile=p.name,
        )
        result.peak_start = start
        return result

    def _consistent(self, state: AccountState, start: float) -> bool:
        share = self.profile.max_single_day_profit_share
        if share is None:
            return True
        profit = state.balance - start
        if profit <= 0:
            return True
        best = max(state.daily_pnl, default=0.0)
        return best <= share * profit


@dataclass
class Evaluation:
    """The distribution Part 6 asks for, rather than a single backtest number."""

    profile: str
    paths: int
    pass_rate: float
    failure_rates: dict[str, float]
    median_days_to_resolve: float
    expected_capital: float
    mean_max_drawdown: float
    p05_min_buffer: float

    def summary(self) -> str:
        fails = ", ".join(f"{k}={v:.1%}" for k, v in sorted(self.failure_rates.items()) if v)
        return (f"{self.profile}: pass {self.pass_rate:.1%} over {self.paths} paths, "
                f"E[capital] ${self.expected_capital:,.0f}, "
                f"median {self.median_days_to_resolve:.0f}d, "
                f"mean maxDD ${self.mean_max_drawdown:,.0f}, "
                f"5th-pct buffer ${self.p05_min_buffer:,.0f}"
                + (f" | {fails}" if fails else ""))


def evaluate(profile: PropFirmProfile, paths: list[list[SessionPnL]]) -> Evaluation:
    """Run many session paths through one profile and summarise the distribution.

    `paths` are supplied by the caller rather than generated here, deliberately: how you
    resample a strategy's sessions (day-block bootstrap, regime-stratified, walk-forward
    slices) is a research decision with real statistical content, and this repository
    already has strong opinions about it - `research/audit_2026-09-12.md` notes F-1's
    2,000-rep day-block bootstrap. Baking one resampling scheme in here would quietly
    override that judgement.

    Expected capital is net of the evaluation fee and applies the profit split, so a high
    pass rate on an expensive evaluation is not flattered.
    """
    sim = PropFirmSimulator(profile)
    results = [sim.run(p) for p in paths]
    n = len(results) or 1

    passed = [r for r in results if r.passed]
    counts: dict[str, int] = {}
    for r in results:
        if r.outcome.is_failure:
            counts[r.outcome.value] = counts.get(r.outcome.value, 0) + 1

    # A passing account earns the payout plus its split of profit above the target; a failing
    # one loses the fee. Both legs are needed or the objective is not capital accumulation.
    capital = 0.0
    for r in results:
        if r.passed:
            capital += profile.payout_on_pass + profile.profit_split * max(
                0.0, r.final_balance - profile.starting_balance)
        capital -= profile.evaluation_fee
    return Evaluation(
        profile=profile.name,
        paths=len(results),
        pass_rate=len(passed) / n,
        failure_rates={k: v / n for k, v in counts.items()},
        median_days_to_resolve=statistics.median([r.days for r in results]) if results else 0.0,
        expected_capital=capital / n,
        mean_max_drawdown=(statistics.fmean([r.max_drawdown_seen for r in results])
                           if results else 0.0),
        p05_min_buffer=(sorted(r.min_buffer for r in results)[max(0, int(0.05 * n) - 1)]
                        if results else 0.0),
    )
