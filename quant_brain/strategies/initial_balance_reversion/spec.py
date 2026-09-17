"""THE FROZEN SPECIFICATION: Initial Balance Statistical Reversion, ES V1.0_Frozen.

Every constant the strategy obeys is here, once, on an immutable dataclass, hashed. Nothing
downstream carries a literal, so a number that moves cannot be mistaken for the same strategy.

WHAT "FROZEN" MEANS
---------------------
The owner supplied these values and this phase may not change them. `tests/` asserts each one
against a literal typed into the test, so an edit here fails the suite rather than silently
redefining the strategy. `AMBIGUITIES` records every place the written specification admits
more than one reading, with the reading taken and whether it is material - because a rule
decided silently is a rule nobody agreed to.

WHY IT REUSES `vwap_pullback.indicators`
------------------------------------------
`Bar`, `FiveMinuteAggregator`, `et`, `minute_of_day` and `trading_day` are already certified -
193 mutations, 3,345 tests - and building a second causal five-minute aggregator would mean
two implementations of the one thing most likely to leak. The session cut comes from the
certified `strategies.vwap_pullback.data` loader for the same reason.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from zoneinfo import ZoneInfo

from quant_brain.core.calendar import ET

VERSION = "ES_V1.0_Frozen"
TIMEZONE: ZoneInfo = ET

OPEN = "OPEN"
RESOLVED = "RESOLVED"


@dataclass(frozen=True)
class Ambiguity:
    """A rule with more than one defensible reading, and the reading taken."""

    ref: str
    rule: str
    question: str
    reading: str
    material: bool
    status: str = OPEN
    authority: str = ""

    @property
    def needs_owner(self) -> bool:
        return self.material and self.status != RESOLVED


@dataclass(frozen=True)
class Conflict:
    """A place the frozen spec disagrees with certified existing code."""

    ref: str
    component: str
    disagreement: str
    resolution: str


AMBIGUITIES: tuple[Ambiguity, ...] = (
    Ambiguity(
        "B1", "5-minute bar timestamp and the IB window",
        "does '09:30 <= bar time < 10:30' mean the bar's START or its CLOSE?",
        "START. A bucket stamped 09:30 covers 09:30:00-09:34:59, so the window admits the "
        "twelve buckets starting 09:30 through 10:25. The IB is complete the instant the "
        "10:25 bucket closes at 10:29:59 and is first readable by the 10:30 bucket. No bar "
        "at or after 10:30 can enter it.",
        material=False),
    Ambiguity(
        "B2", "60-minute time stop",
        "the data is 5-minute bars, so what exactly is 'within 60 minutes' of the fill?",
        "The fill happens at the CLOSE of the trigger bucket, i.e. at start+5:00. The "
        "deadline is fill_time + 60 minutes exactly, which on a 5-minute grid is the close "
        "of the twelfth bucket after entry. The position is flattened at the close of the "
        "first completed bucket whose close time is >= the deadline, and only if neither "
        "target nor stop has already executed on or before that bucket.",
        material=True, status=RESOLVED,
        authority="owner brief: 'document the exact historical timing convention used'"),
    Ambiguity(
        "B3", "trap and rejection on the same bucket",
        "may one bucket both establish the trap (low < Low_IB) and reject (close > Low_IB)?",
        "YES, taken literally: the specification requires price to trade below Low_IB and a "
        "completed candle to close back inside, and one candle can satisfy both. E_long is "
        "then that candle's own low. The alternative - requiring a prior candle to have "
        "traded outside - is not written.",
        material=True, status=RESOLVED,
        authority="literal reading; frequency measured and reported in the backtest"),
    Ambiguity(
        "B4", "target already passed at entry",
        "for a long, what if the rejection candle closes ABOVE IB_Midpoint?",
        "The target is a limit at IB_Midpoint. A sell limit below the market is marketable, "
        "so it executes immediately at the entry bucket's close - the trade opens and closes "
        "on the same bucket for a gross of zero and a loss of costs. The frequency of this "
        "is measured and reported rather than assumed to be zero.",
        material=True, status=RESOLVED,
        authority="literal reading of a limit order; frequency reported"),
    Ambiguity(
        "B5", "stop and target inside one bucket",
        "OHLCV cannot order two touches inside one bar",
        "STOP FIRST. The repository's declared conservative convention, reused unchanged "
        "from `research.bracket_reference`. Every affected trade is flagged and counted.",
        material=False),
    Ambiguity(
        "B6", "governor mark-to-market",
        "is the -$800 killswitch read at the bucket close or the adverse intrabar extreme?",
        "CONSERVATIVE_INTRABAR_ADVERSE_EXTREME - the lowest price of the bucket for a long, "
        "the highest for a short - so an OHLCV close cannot hide an excursion that would "
        "have tripped the governor. Matches the convention already ruled for this repository.",
        material=False),
    Ambiguity(
        "B7", "second trade from the same excursion",
        "may one breakout excursion produce more than one entry?",
        "NO. An excursion is consumed by the rejection that trades it. A new entry requires a "
        "NEW excursion: price must leave the IB again after the previous rejection. The daily "
        "cap of 2 remains authoritative and no cooldown is invented.",
        material=True, status=RESOLVED,
        authority="owner brief: 'do not generate duplicate entries from the same rejection "
                  "event'; a second independent breakout is permitted"),
    Ambiguity(
        "B8", "trap direction while a position is open",
        "does an excursion that begins while in a position count once flat again?",
        "The excursion tracker runs continuously, but an entry may only be taken when flat "
        "and armed. An excursion that began and rejected while in a position is not "
        "re-entered afterwards.",
        material=False),
    Ambiguity(
        "B10", "the IB midpoint is off-tick about half the time",
        "(High_IB + Low_IB)/2 lands on a 0.125 grid; a limit cannot rest there",
        "Rounded to a valid ES tick AWAY from the entry - up for a long, down for a short - "
        "so the target is strictly harder to reach. The specification permits rounding 'as "
        "required to maintain valid ES tick increments' and does not name a direction; the "
        "conservative one is taken and both the raw midpoint and the placed target are "
        "carried in the ledger so the effect is visible.",
        material=True, status=RESOLVED,
        authority="literal reading plus the repository's conservative-fill doctrine; "
                  "frequency and P&L effect reported"),
    Ambiguity(
        "B9", "market-exit slippage",
        "the spec prices entry and stop at one tick; what about the time stop and the "
        "15:45 flatten?",
        "BASELINE_FROZEN charges exactly what the specification states - one tick on the "
        "entry, one on the stop - and NOTHING on the time stop or the hard flatten, because "
        "the specification does not price them. That is not a claim that those exits are "
        "frictionless; it is a refusal to invent a number. STRESS_1TICK and STRESS_2TICK "
        "measure the unpriced gap.",
        material=True, status=RESOLVED,
        authority="owner brief: 'their slippage treatment must be explicitly reported "
                  "rather than silently assumed'"),
)

CONFLICTS: tuple[Conflict, ...] = (
    Conflict(
        "D1", "markets/futures_cme/instruments.py",
        "the repository carries ES round-turn commission $3.78, cited to Topstep's published "
        "rate (help.topstep.com/en/articles/8284197, retrieved 2026-09-13). The frozen "
        "specification says $4.14.",
        "The frozen spec wins for this strategy and is the more conservative of the two. The "
        "engine carries its own commission and does not read the instrument default. Both "
        "numbers are recorded."),
    Conflict(
        "D2", "strategies/vwap_pullback/data.py completeness rule",
        "the anchored loader requires an 18:00 ET anchor, which this strategy never uses.",
        "Reused unchanged. On ES it costs nothing: all 14 refused sessions also lack the "
        "15:45 bar this strategy flattens on, so none is wrongly excluded. Verified in "
        "Phase 1 rather than assumed."),
    Conflict(
        "D3", "research/exits.py and research/ledger_builder.py",
        "both implement bracket exits, but neither models an IB-anchored target, a "
        "swing-extreme stop, a 60-minute wall-clock stop or this governor.",
        "Not reused. A new engine, with the exit PRECEDENCE (stop before target, gaps fill "
        "at the level) taken from `research.bracket_reference` so the convention is shared "
        "even though the code is not."),
)


@dataclass(frozen=True)
class ExecutionProfile:
    """Ticks of ADVERSE slippage by exit kind. A profile changes fills, never a rule."""

    name: str
    intent: str
    entry_ticks: float
    stop_ticks: float
    target_ticks: float
    market_exit_ticks: float
    frozen_spec_exact: bool


IDEAL = ExecutionProfile(
    "IDEAL", "no friction anywhere; a ceiling, not a forecast", 0.0, 0.0, 0.0, 0.0, False)
BASELINE_FROZEN = ExecutionProfile(
    "BASELINE_FROZEN",
    "EXACTLY what ES V1.0_Frozen states: one tick on the market entry, one on the stop, "
    "nothing on the limit target, and nothing invented for the time stop or the 15:45 "
    "flatten, which the specification leaves unpriced.",
    1.0, 1.0, 0.0, 0.0, True)
STRESS_1TICK = ExecutionProfile(
    "STRESS_1TICK", "one extra tick on the stop and one on every market exit",
    1.0, 2.0, 0.0, 1.0, False)
STRESS_2TICK = ExecutionProfile(
    "STRESS_2TICK", "two extra ticks on the stop and two on every market exit",
    1.0, 3.0, 0.0, 2.0, False)

EXECUTION_LADDER: tuple[ExecutionProfile, ...] = (
    IDEAL, BASELINE_FROZEN, STRESS_1TICK, STRESS_2TICK)


@dataclass(frozen=True)
class FrozenSpec:
    """Every constant. Immutable, hashed, asserted against literals by test."""

    version: str = VERSION

    # -- session clock, as (hour, minute) on the venue clock -------------------------------
    ib_start: tuple[int, int] = (9, 30)
    ib_end: tuple[int, int] = (10, 30)
    execution_cutoff: tuple[int, int] = (14, 0)
    hard_flatten: tuple[int, int] = (15, 45)

    # -- the IB volatility regime filter, inclusive both ends -------------------------------
    ib_range_min: float = 10.0
    ib_range_max: float = 35.0

    # -- exits -------------------------------------------------------------------------------
    stop_offset_ticks: float = 1.0          # one tick beyond the excursion extreme
    time_stop_minutes: int = 60

    # -- governor -----------------------------------------------------------------------------
    daily_loss_killswitch: float = -800.0
    daily_profit_cap: float = 1200.0
    max_trades_per_day: int = 2
    governor_mtm_basis: str = "intrabar"

    # -- instrument ----------------------------------------------------------------------------
    instrument: str = "ES"
    contracts: int = 1
    point_value_per_contract: float = 50.0
    tick: float = 0.25
    commission_round_turn: float = 4.14

    # -- bars ------------------------------------------------------------------------------------
    bar_minutes: int = 5

    execution: ExecutionProfile = BASELINE_FROZEN
    notes: dict = field(default_factory=dict)

    # -- derived -----------------------------------------------------------------------------------

    @property
    def point_value(self) -> float:
        """Dollars per point for the WHOLE position."""
        return self.point_value_per_contract * self.contracts

    @property
    def tick_value(self) -> float:
        return self.tick * self.point_value

    def minute_of(self, which: str) -> int:
        h, m = getattr(self, which)
        return h * 60 + m

    def round_to_tick(self, price: float) -> float:
        """Snap to a valid ES increment. The only rounding the specification permits."""
        return round(round(price / self.tick) * self.tick, 10)

    def round_target_conservative(self, midpoint: float, direction: int) -> float:
        """The IB midpoint, moved to a placeable ES tick, AWAY from the entry.

        AMBIGUITY B10. `(High_IB + Low_IB) / 2` lies on a 0.125 grid, so it is off-tick
        whenever `(High_IB + Low_IB) / 0.25` is odd - about half of all sessions. A limit
        order cannot rest at 6,061.625 and a fill reported there is a fill at a price no venue
        quoted.

        The specification permits exactly this rounding ("except as required to maintain valid
        ES tick increments") and does not say which way. Rounding AWAY from the entry - up for
        a long, down for a short - makes the target strictly harder to reach, which is the
        conservative direction and the one consistent with every other convention in this
        repository. Rounding toward the entry would manufacture fills.
        """
        import math
        if direction > 0:
            return round(math.ceil(midpoint / self.tick) * self.tick, 10)
        return round(math.floor(midpoint / self.tick) * self.tick, 10)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def spec_hash(self) -> str:
        """sha256 over every declared constant. A changed number is a changed strategy."""
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, default=str).encode()).hexdigest()[:16]

    def describe(self) -> str:
        return "\n".join([
            f"STRATEGY     Initial Balance Statistical Reversion {self.version}",
            f"SPEC HASH    {self.spec_hash}",
            f"INSTRUMENT   {self.contracts} x {self.instrument}   "
            f"${self.point_value:,.2f}/point   tick {self.tick:g} = ${self.tick_value:,.2f}",
            f"CLOCK        {TIMEZONE.key}",
            f"IB           {self.ib_start[0]:02d}:{self.ib_start[1]:02d} -> "
            f"{self.ib_end[0]:02d}:{self.ib_end[1]:02d}   "
            f"range must be {self.ib_range_min:g}..{self.ib_range_max:g} inclusive",
            f"WINDOWS      entries until {self.execution_cutoff[0]:02d}:"
            f"{self.execution_cutoff[1]:02d} (exclusive) | hard flatten "
            f"{self.hard_flatten[0]:02d}:{self.hard_flatten[1]:02d}",
            "TARGET       IB midpoint (fixed before the armed window)",
            f"STOP         excursion extreme -/+ {self.stop_offset_ticks:g} tick",
            f"TIME STOP    {self.time_stop_minutes} minutes from the fill",
            f"GOVERNOR     kill <= ${self.daily_loss_killswitch:,.0f} "
            f"({self.governor_mtm_basis}) | cap >= ${self.daily_profit_cap:,.0f} | "
            f"max {self.max_trades_per_day} trades/day",
            f"COST         ${self.commission_round_turn:.2f} RT + {self.execution.name} "
            f"(entry {self.execution.entry_ticks:g}t, stop {self.execution.stop_ticks:g}t, "
            f"target {self.execution.target_ticks:g}t, "
            f"market exit {self.execution.market_exit_ticks:g}t)",
            f"BARS         {self.bar_minutes}-minute, start-stamped, completed only",
        ])


FROZEN = FrozenSpec()


def unresolved() -> list[Ambiguity]:
    """Material ambiguities the owner has not ruled on. Must be empty to certify."""
    return [a for a in AMBIGUITIES if a.needs_owner]


def resolved() -> list[Ambiguity]:
    return [a for a in AMBIGUITIES if a.status == RESOLVED]


def execution_table() -> str:
    rows = ["  profile            entry   stop  target  mkt exit   = V1.0",
            "  " + "-" * 58]
    for p in EXECUTION_LADDER:
        rows.append(f"  {p.name:18} {p.entry_ticks:>5.0f} {p.stop_ticks:>6.0f} "
                    f"{p.target_ticks:>7.0f} {p.market_exit_ticks:>9.0f} "
                    f"{str(p.frozen_spec_exact):>10}")
    rows.append("  ticks of ADVERSE slippage. The target is a limit and is never charged.")
    return "\n".join(rows)


__all__ = ["AMBIGUITIES", "BASELINE_FROZEN", "CONFLICTS", "EXECUTION_LADDER", "FROZEN",
           "IDEAL", "STRESS_1TICK", "STRESS_2TICK", "TIMEZONE", "VERSION", "Ambiguity",
           "Conflict", "ExecutionProfile", "FrozenSpec", "execution_table", "resolved",
           "unresolved"]
