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
    EOD = "eod"            # trails the highest end-of-day balance, breach tested EOD
    INTRADAY = "intraday"  # trails the highest intraday equity, breach tested intraday
    #: Topstep's actual rule, and neither of the two above. The threshold advances on the
    #: END-OF-DAY balance ("It rises as your end-of-day balance grows, but never moves down")
    #: while the BREACH is tested in real time against unrealized P&L ("monitored in real
    #: time throughout the session. Both realized and unrealized P&L count toward it" /
    #: "If your balance hits it at any point during the trading day, including on unrealized
    #: P&L, your account is liquidated immediately").
    #: help.topstep.com/en/articles/8284204, retrieved 2026-09-12.
    #:
    #: Modelling Topstep as EOD understates breach risk, because it never tests the intraday
    #: path. Modelling it as INTRADAY overstates the trailing, because it ratchets the floor
    #: up on unrealized highs the real rule ignores. Both errors are large and they point in
    #: opposite directions, which is why this is a distinct mode rather than an approximation.
    EOD_TRAIL_INTRADAY_BREACH = "eod_trail_intraday_breach"


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
    #: WHICH SIDE of that share is compliant: "inclusive" admits a day at exactly the share
    #: ("must stay at or below 55%"), "exclusive" refuses it (a strict bound). A parameter
    #: rather than an operator because the published wording genuinely differs between a
    #: firm's own pages, and the two readings disagree at exactly the threshold - which is
    #: exactly where a pass is decided. See `topstep.CONSISTENCY_READINGS`, which carries the
    #: boundary alongside the denominator so the difference can be measured rather than
    #: argued about.
    max_single_day_share_boundary: str = "inclusive"

    # --- position constraints ------------------------------------------------------------
    #: The account-wide position ceiling, in the units `contract_equivalence` selects: raw
    #: contracts by default, or units of the equivalence scale when that flag is set.
    max_total_contracts: int | None = None
    #: Per-symbol contract cap, e.g. {"MES": 10, "ES": 1}.
    max_contracts_per_symbol: dict[str, int] = field(default_factory=dict)
    #: True when `max_total_contracts` and `max_contracts_per_symbol` are two views of ONE
    #: account-wide allowance rather than two independent counts. Topstep's is one allowance:
    #: 5 minis OR 50 micros at a 10:1 ratio, PER ACCOUNT
    #: (help.topstep.com/en/articles/8284197, retrieved 2026-09-13). The published table
    #: already encodes the ratio - 5 in the mini column, 50 in the micro column - so one
    #: contract of a listed symbol consumes `max_total_contracts / max_contracts_per_symbol`
    #: of the allowance: 10 units for ES, 1 for MES. Nothing consumed that ratio before, so
    #: 5 ES + 45 MES counted as 50 raw contracts and passed a 50-MICRO account holding 95
    #: micro-equivalents - 1.9x the permitted size.
    #:
    #: Default False, which keeps the historical raw count for every profile that does not
    #: opt in: a firm whose per-symbol caps are independent limits rather than the same
    #: allowance in another unit would be LOOSENED by the ratio, and loosening a limit is
    #: never the safe default.
    contract_equivalence: bool = False
    #: The roots the account may trade at all. Empty means the firm published no list and the
    #: universe is open. A non-empty list is enforced by the risk engine BEFORE any cap, so a
    #: product the account may not hold is refused at zero whatever the caps say - and a root
    #: this repository cannot resolve to a contract spec, and therefore could not size or cost
    #: if it wanted to, can never appear on it. Topstep publishes a product list per account
    #: (8284197).
    permitted_products: tuple[str, ...] = ()
    #: Notional exposure ceiling in dollars, if the firm states one.
    max_notional: float | None = None

    # --- session constraints ---------------------------------------------------------------
    allow_overnight: bool = False
    #: Separate from `allow_overnight` on purpose. Several firms permit an overnight hold on a
    #: weekday and still require flat into the weekend, because a Friday-to-Sunday gap is the
    #: one move no intraday stop can protect against. Collapsing the two would make that
    #: distinction unrepresentable, and it is a rule a real rulebook states explicitly.
    allow_weekend: bool = False
    #: Minutes before the session close by which the book must be flat. Expressed relative to
    #: the close so it is correct on an early close - the AUD-07 lesson, applied here rather
    #: than repeated as a literal bar index.
    flat_before_close_minutes: int = 15
    #: A WALL-CLOCK flat deadline in the market's local time, when the firm states one that
    #: way. Topstep's mandatory flat is 3:10 PM CT - a clock, not an offset - and modelling it
    #: as `flat_before_close_minutes=15` against a 16:00 CT close enforced 15:45 CT, so a
    #: position held from 15:10 to 15:45 was a rule violation the model called compliant every
    #: session. Both deadlines apply and the EARLIER one binds: the offset keeps the rule
    #: correct on an early close (AUD-07), the clock keeps it correct on a normal one.
    #: Requires `regular_close_local_time`, which is what makes the clock comparable with the
    #: offset - a deadline nobody can anchor is a deadline nobody enforces.
    flat_at_local_time: dt.time | None = None
    #: The session close `flat_at_local_time` is measured against when the caller does not say
    #: what today's close is: the SCHEDULED close, in the same local time as the deadline.
    regular_close_local_time: dt.time | None = None
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

    #: Contract ladder: [(profit_above_start, max_total_contracts), ...]. Many firms scale
    #: permitted size with the account's own profit, so a strategy sized for the funded
    #: ceiling is untradeable on day one. Empty means the flat `max_total_contracts` applies
    #: at every balance. The firm supplies the numbers; this only supplies the shape.
    scaling: tuple[tuple[float, int], ...] = ()

    def __post_init__(self) -> None:
        # Fail closed on a rule set that cannot be evaluated, at construction rather than at
        # the order it would have mis-sized.
        if self.max_single_day_share_boundary not in ("inclusive", "exclusive"):
            raise ValueError(
                f"{self.name}: max_single_day_share_boundary must be 'inclusive' or "
                f"'exclusive', got {self.max_single_day_share_boundary!r}")
        if self.flat_at_local_time is not None and self.regular_close_local_time is None:
            raise ValueError(
                f"{self.name}: flat_at_local_time {self.flat_at_local_time} has no "
                f"regular_close_local_time to measure it against, so it could not be compared "
                f"with flat_before_close_minutes and would silently never bind")

    def contract_units(self, symbol: str) -> float:
        """How much of `max_total_contracts` one contract of `symbol` consumes.

        1.0 unless the profile opted into `contract_equivalence`, in which case the published
        per-symbol cap says how many of that symbol fill the account and the ratio follows:
        with a total of 50 and an ES cap of 5, one ES is 10 units and one MES (cap 50) is 1.
        A symbol the table does not list gets 1.0 and is refused by `permitted_products`
        instead - inventing a weight for an unknown product is the flattering direction.
        """
        if not self.contract_equivalence or self.max_total_contracts is None:
            return 1.0
        cap = self.max_contracts_per_symbol.get(symbol)
        if not cap or cap <= 0:
            return 1.0
        return self.max_total_contracts / cap

    def permits(self, symbol: str) -> bool:
        """Is this root tradeable here? True when the firm published no product list."""
        return not self.permitted_products or symbol.upper() in self.permitted_products

    def max_contracts_for(self, symbol: str, *, profit: float = 0.0,
                          held_equivalents: float = 0.0) -> int | None:
        """The ceiling on `symbol`, IN CONTRACTS OF `symbol`. None means the firm sets none.

        `max_total_contracts` is written in the profile's OWN allowance unit, and under
        `contract_equivalence` that unit is not contracts of whatever is being traded:
        Topstep's 50 is fifty micros or five minis. `contracts_allowed_at` therefore cannot
        be used as a position size, and every caller that did so was permitting 50 ES on a
        five-ES account. This method is that conversion, done in the one module that holds
        the ratio, so a `core` sizer can ask for a number it is allowed to act on without
        `core` ever learning what a micro is.

        `held_equivalents` is the book already open, in the same allowance unit
        (`AccountState.total_equivalents`), so the answer is the HEADROOM for new contracts
        rather than a standalone ceiling. Three ES against a 50-micro-equivalent allowance
        consume thirty units and leave room for twenty MES, not fifty; a ceiling that
        ignored the open book would let a mixed account carry 1.6x the permitted size,
        which is the same defect `contract_equivalence` was added to close.

        Fails CLOSED at zero rather than at a permissive default in two cases: a symbol the
        firm does not permit, and a symbol with no entry in an equivalence table that is in
        force. In the second case one contract consumes an unknown share of the allowance,
        and `contract_units` already refuses to invent a weight for it - inventing one is
        always the flattering direction.
        """
        sym = symbol.upper()
        if not self.permits(sym):
            return 0
        per_symbol = self.max_contracts_per_symbol.get(sym)
        if self.contract_equivalence and not (per_symbol and per_symbol > 0):
            return 0
        caps: list[int] = []
        if per_symbol is not None:
            caps.append(max(0, int(per_symbol)))
        total = self.contracts_allowed_at(profit)
        if total is not None:
            units = self.contract_units(sym)
            if units <= 0:
                return 0
            room = max(0.0, float(total) - max(0.0, held_equivalents))
            # Round DOWN. Half a permitted contract is no contract - the same rule the risk
            # engine applies to `room_units` below and `twin.max_contracts` to its budget.
            caps.append(int(room // units))
        if not caps:
            return None
        return max(0, min(caps))

    def flat_deadline_minutes(self, session_close: dt.time | None = None) -> int:
        """Minutes before the close at which the book must be flat, both deadlines applied.

        The wall clock and the offset are two statements of the same rule and the EARLIER one
        binds, which in minutes-before-close is the LARGER number. The clock is converted
        against today's close when the caller supplies it and against the scheduled close
        otherwise; a clock that falls at or after the close (an early close: 15:10 CT against
        a 13:00 CT bell) cannot bind, and the offset alone applies - which is the AUD-07
        property this must not lose.
        """
        offset = self.flat_before_close_minutes
        if self.flat_at_local_time is None:
            return offset
        close = session_close or self.regular_close_local_time
        if close is None:
            return offset
        deadline = self.flat_at_local_time
        before_close = ((close.hour * 60 + close.minute)
                        - (deadline.hour * 60 + deadline.minute))
        return max(offset, before_close)

    def contracts_allowed_at(self, profit: float) -> int | None:
        """The contract cap at a given profit above the starting balance.

        Returns the flat cap when no ladder is configured. With a ladder, the highest rung
        whose threshold has been reached wins, and below the first rung the FIRST rung's cap
        applies - a ladder that left a fresh account with no permitted size would be a
        misreading of every rulebook I have seen.
        """
        if not self.scaling:
            return self.max_total_contracts
        rungs = sorted(self.scaling)
        cap = rungs[0][1]
        for threshold, allowed in rungs:
            if profit >= threshold:
                cap = allowed
        if self.max_total_contracts is not None:
            cap = min(cap, self.max_total_contracts)
        return cap

    def floor_for(self, peak: float) -> float:
        """The equity level at which this account is dead, given the running peak.

        With TrailingMode.NONE the peak is ignored and the floor is static. With a lock
        level the threshold stops climbing once it reaches it.
        """
        if self.max_drawdown is None:
            return -math.inf
        if self.trailing_mode is TrailingMode.NONE:
            return self.starting_balance - self.max_drawdown
        # EOD_TRAIL_INTRADAY_BREACH trails exactly like EOD; the difference is only in WHEN
        # the breach is tested, which is the simulator's concern rather than the floor's.
        threshold = peak - self.max_drawdown
        if self.trailing_locks_at is not None:
            threshold = min(threshold, self.trailing_locks_at)
        return threshold

    def to_json(self) -> str:
        d = dataclasses.asdict(self)
        d["trailing_mode"] = self.trailing_mode.value
        d["blackout_windows"] = [[a.isoformat(), b.isoformat()] for a, b in self.blackout_windows]
        # A time is not JSON. A rule that cannot be written down is a rule that stops being
        # enforced the first time a profile is reloaded, so both clocks go out as ISO strings.
        for key in ("flat_at_local_time", "regular_close_local_time"):
            value = getattr(self, key)
            d[key] = None if value is None else value.isoformat()
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
        # JSON has no tuple, so a round-tripped ladder arrives as a list of lists. Coerce it
        # back or a reloaded profile compares unequal to the one that was written - which the
        # round-trip test caught, and which would otherwise only show up as a confusing
        # inequality the first time a profile was reloaded from disk.
        d["scaling"] = tuple((float(a), int(b)) for a, b in d.get("scaling", ()))
        # Same reason as `scaling`: JSON has no tuple, and a reloaded product list that
        # compares unequal to the one written is a limit nobody notices has changed shape.
        d["permitted_products"] = tuple(d.get("permitted_products", ()))
        for key in ("flat_at_local_time", "regular_close_local_time"):
            if d.get(key) is not None and not isinstance(d[key], dt.time):
                d[key] = dt.time.fromisoformat(d[key])
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
        """Raw contracts held, whatever they are. Reported; not what the total cap counts."""
        return sum(abs(v) for v in self.contracts.values())

    @property
    def total_equivalents(self) -> float:
        """The position in the units `max_total_contracts` is expressed in.

        Equals `total_contracts` for every profile that has not opted into
        `contract_equivalence`, so the two are the same number until a firm says otherwise.
        """
        return sum(self.profile.contract_units(sym) * abs(v)
                   for sym, v in self.contracts.items())

    def mark_peak(self, *, intraday: bool) -> None:
        """Advance the trailing peak under the profile's convention."""
        mode = self.profile.trailing_mode
        if mode is TrailingMode.INTRADAY and intraday:
            self.peak = max(self.peak, self.equity)
        elif mode in (TrailingMode.EOD, TrailingMode.EOD_TRAIL_INTRADAY_BREACH) and not intraday:
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

        # The product list is checked BEFORE any sizing: the correct size for a product the
        # account may not hold is zero, whatever the caps say, and a root with no contract
        # spec in this repository cannot be sized or costed by anything downstream either.
        # Flatten intents never reach here (RiskEngine.__call__ passes them through), so an
        # open position in a product that has since left the list can always be closed.
        if not p.permits(sym):
            return RiskDecision.deny(
                f"{sym} is not on {p.name}'s permitted-products list "
                f"({', '.join(p.permitted_products)})", "permitted_products")

        per_unit = self.contract_size.get(sym, 1)
        want = int(abs(intent.quantity)) * per_unit
        if want <= 0:
            return RiskDecision.deny("zero-size intent", "zero_size")

        held = s.contracts.get(sym, 0)
        signed = intent.side.sign * want
        resulting_sym = abs(held + signed)
        # The total cap is counted in the profile's own units, which are raw contracts unless
        # the firm's per-symbol table is a ratio (see `contract_equivalence`). One ES against
        # a 50-micro Topstep allowance is 10 of those units, not 1.
        units = p.contract_units(sym)
        resulting_total = s.total_equivalents + units * (resulting_sym - abs(held))

        decision = RiskDecision.allow(intent.quantity)

        # --- contract caps ------------------------------------------------------------------
        cap_sym = p.max_contracts_per_symbol.get(sym)
        if cap_sym is not None and resulting_sym > cap_sym:
            room = max(0, cap_sym - abs(held))
            decision = decision.merge(RiskDecision.reduce(
                room / per_unit if per_unit else 0,
                f"{sym} cap {cap_sym}: holding {abs(held)}, room for {room}",
                "max_contracts_per_symbol"))

        # The ladder, when configured, is the binding total cap - and it moves with the
        # account's own profit, so it is read from live state rather than from the profile.
        cap_total = p.contracts_allowed_at(s.balance - p.starting_balance)
        if cap_total is not None and resulting_total > cap_total:
            # Room is in the cap's units; convert it back into contracts of THIS symbol
            # before it can become an order size, and round DOWN - half a permitted contract
            # is no contract.
            room_units = max(0.0, cap_total - s.total_equivalents)
            room = int(room_units / units) if units else 0
            decision = decision.merge(RiskDecision.reduce(
                room / per_unit if per_unit else 0,
                f"total cap {cap_total}: holding {s.total_equivalents:g}, room for {room}",
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

    def must_be_flat(self, minutes_to_close: int, *, session_close: dt.time | None = None,
                     is_last_session_of_week: bool = False) -> bool:
        """True once the flat-by-the-close deadline has arrived.

        Takes minutes-to-close rather than a wall clock so it is automatically correct on an
        early close, per AUD-07. The caller gets that number from the market's
        `SessionCalendar`, not from a constant.

        A firm may state the deadline as a CLOCK instead - Topstep's mandatory flat is 3:10 PM
        CT - and then BOTH deadlines apply and the earlier one binds. `session_close` is
        today's actual close, and supplying it is what lets the clock be read correctly on a
        day the bell moves: against a 13:00 CT early close, 15:10 CT is after the close and
        cannot bind, so the offset alone applies. Left out, the profile's scheduled close is
        used, which is right on a normal day and conservative (never late) on a short one.
        """
        p = self.state.profile
        deadline = p.flat_deadline_minutes(session_close)
        # Friday is decided by the weekend rule, not the overnight one.
        if is_last_session_of_week and not p.allow_weekend:
            return minutes_to_close <= deadline
        if p.allow_overnight:
            return False
        return minutes_to_close <= deadline


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
            if (p.trailing_mode in (TrailingMode.INTRADAY,
                                    TrailingMode.EOD_TRAIL_INTRADAY_BREACH)
                    and s.intraday_equity):
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
        # Which side of the share is compliant is a published reading, not a house style; a
        # day at EXACTLY the share is the case the two readings decide differently.
        if self.profile.max_single_day_share_boundary == "exclusive":
            return best < share * profit
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
