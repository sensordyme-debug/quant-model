"""The FROZEN specification: Intraday Multi-Timeframe VWAP Pullback System V1.0.0_Frozen.

Every number the strategy obeys is here, once, as a named field on a frozen dataclass. Nothing
downstream carries a literal. The spec is hashed, and the hash is recorded on every result, so
a number that moves cannot be mistaken for the same strategy.

WHAT "FROZEN" MEANS HERE
--------------------------
The values in `FROZEN` are the owner's, and this phase may not change them. `tests/` asserts
each one against a literal written in the test, so an edit to this file fails the suite rather
than silently redefining the strategy.

THE TWO REGISTERS
-----------------
`AMBIGUITIES` and `CONFLICTS` are part of the specification, not commentary. A rule with two
readings is recorded with the reading taken and whether the difference is material; a place
where the frozen spec disagrees with certified existing code is recorded with the resolution.
Both print in the certification report. `docs/VWAP_PULLBACK_INTEGRATION_PLAN.md` is the long
form.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from zoneinfo import ZoneInfo

from quant_brain.core.calendar import ET

VERSION = "V1.0.0_Frozen"

#: The venue clock. Imported from `core.calendar` rather than constructed here: one tz object
#: for the repository, and no chance of a second one drifting. DST is handled by zoneinfo;
#: nothing in this package may hard-code a UTC offset.
TIMEZONE: ZoneInfo = ET


#: An ambiguity's lifecycle. OPEN means the engine picked a reading and the owner has not
#: confirmed it; RESOLVED means the owner ruled, and `authority` records who and when.
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
    #: True when the alternative reading is also implemented and tested, so the owner can see
    #: what the choice costs before confirming it.
    both_implemented: bool = False
    status: str = OPEN
    #: Who ruled, and on what. Empty while the status is OPEN.
    authority: str = ""

    @property
    def needs_owner(self) -> bool:
        """Material AND unresolved. The only combination that blocks certification."""
        return self.material and self.status != RESOLVED


@dataclass(frozen=True)
class Conflict:
    """A place the frozen spec disagrees with certified existing code."""

    ref: str
    component: str
    disagreement: str
    resolution: str


AMBIGUITIES: tuple[Ambiguity, ...] = (
    Ambiguity("A1", "5-minute ATR(14)",
              "Wilder smoothing or a simple mean of true range?",
              "WILDER, period 14, on COMPLETED 5-minute bars. The threshold stays at exactly "
              "8.0 points and the period is not a tunable. The simple-mean implementation is "
              "retained and tested so the choice remains inspectable, but it is not the "
              "specification.",
              material=True, both_implemented=True, status=RESOLVED,
              authority="owner, V1.0.0_Frozen certification register, 2026-09-16 - DECISION 1"),
    Ambiguity("A2", "governor mark-to-market",
              "is unrealised P&L read at the bar close or at the bar's adverse extreme?",
              "CONSERVATIVE_INTRABAR_ADVERSE_EXTREME. Realized + unrealised, where unrealised "
              "is marked at the LOWEST price reached in the interval for a long and the "
              "HIGHEST for a short, so an OHLCV close cannot hide an intrabar drawdown that "
              "would have tripped the governor. The threshold stays at <= -$800.00. This is "
              "the SAFETY layer and may override strategy behaviour; it is not trade exit "
              "logic.",
              material=True, both_implemented=True, status=RESOLVED,
              authority="owner, V1.0.0_Frozen certification register, 2026-09-16 - DECISION 2"),
    Ambiguity("A3", "no new entries after 15:30:00",
              "is a bar STAMPED 15:30 'after' the cutoff?",
              "no - the 15:30 bar is the last bar an entry may be decided on",
              material=False),
    Ambiguity("A4", "the trigger bar must touch or penetrate VWAP",
              "which extreme of the bar has to reach VWAP?",
              "long: low <= VWAP; short: high >= VWAP",
              material=False),
    Ambiguity("A5", "the current 1-minute price must qualify within the zone",
              "which price - close, or any part of the bar's range?",
              "the trigger bar's close",
              material=False),
    Ambiguity("A6", "SMA(volume, 10)",
              "does the window include the current bar or the ten before it?",
              "includes the current bar, the standard reading; the current bar's volume is "
              "known at its own close so this is causal either way",
              material=False),
    Ambiguity("A7", "5m regime: VWAP - low <= 6.0",
              "a 5m bar entirely ABOVE VWAP gives a negative value, which passes the test",
              "implemented literally as written - the condition admits it",
              material=False),
    Ambiguity("A8", "two consecutive losses",
              "is a loss measured gross or net of costs?",
              "net. A trade that is gross-positive but net-negative cost money",
              material=False),
    Ambiguity("A9", "45-minute cooldown",
              "measured from the entry or the exit of the second loss?",
              "the exit",
              material=False),
    Ambiguity("A10", "stall: already beyond the new target",
              "what counts as 'beyond in the unfavorable direction'?",
              "long: the modification bar's close is already >= fill+20, so the new target is "
              "immediately marketable and the position closes at market",
              material=False),
    Ambiguity("A11", "MNQ commission",
              "the frozen cost model states a round turn for NQ only",
              "the repository's measured MNQ rate, $1.22 x 10 contracts = $12.20",
              material=False),
    Ambiguity("A12", "one tick of slippage on entry and stop-outs",
              "do the 15:45 flatten, the governor flatten and the stall market-close also "
              "slip?",
              "RESOLVED FOR THE BASELINE. `BASELINE_FROZEN` charges exactly what V1.0.0 "
              "states - one tick on the entry, one on stop-outs INCLUDING the break-even "
              "stop - and charges nothing for the three market exits the specification "
              "leaves unpriced. That is NOT a claim that those exits are frictionless: it is "
              "a refusal to invent a number. The unpriced gap is measured instead by the "
              "STRESS_1TICK and STRESS_2TICK profiles, which are DIAGNOSTIC and alter no "
              "strategy rule.",
              material=True, both_implemented=True, status=RESOLVED,
              authority="owner, V1.0.0_Frozen certification register, 2026-09-16 - DECISION 3"),
    Ambiguity("A16", "STRESS profiles: 'additional slippage on all market exits'",
              "does 'all market exits' include a triggered STOP, which is itself a market "
              "order, or only the three flattens the frozen spec leaves unpriced?",
              "INCLUDES THE STOP - the more conservative reading. STRESS_1TICK charges the "
              "stop 2 ticks and each flatten 1; STRESS_2TICK charges 3 and 2. The narrower "
              "reading would isolate the unpriced gap more cleanly but understates a "
              "stressed tape. Diagnostic only: no strategy rule reads a stress profile.",
              material=False, status=RESOLVED,
              authority="engine reading, recorded for the owner to overturn"),
    Ambiguity("A13", "the trading day for daily counters",
              "midnight or the 18:00 anchor?",
              "18:00 ET, matching the VWAP anchor and the halt release",
              material=False),
)

CONFLICTS: tuple[Conflict, ...] = (
    Conflict("C1", "research.strategy_spec.StrategySpec",
             "the certified interface is a stateless per-bar signal array; this strategy "
             "carries state across bars (armed regime, MFE bar, stall window, cooldown "
             "clock, per-day counters)",
             "a separate stateful engine; StrategySpec untouched"),
    Conflict("C2", "research.exits.ExitArchitecture.breakeven_at_r",
             "the certified break-even moves the stop TO the entry at a multiple of R; the "
             "frozen rule moves it to fill +/- 0.25 at a fixed 15.0 points",
             "the frozen exit manager implements the frozen rule; exits.py untouched"),
    Conflict("C3", "nothing",
             "no component implements MFE-bar identification, a bounded forward window, or "
             "target modification",
             "new"),
    Conflict("C4", "research.ledger_builder.build_ledger",
             "the certified path fills at the bar close and charges slippage as a dollar "
             "cost, leaving entry_price == bar close; the frozen spec moves the FILL PRICE "
             "and anchors the bracket to it",
             "the frozen engine moves the fill price; ledger_builder untouched and the "
             "difference is pinned by test"),
    Conflict("C5", "markets.futures_cme.twin.TopstepTwin",
             "the twin is session-granular; the frozen governor is intraday and stricter, "
             "and its 15:45 flatten deliberately precedes Topstep's 16:10 mandatory flat",
             "a separate governor; the twin is the account layer for a later phase"),
    Conflict("C6", "research.session_source",
             "RTH session cutting cannot supply the overnight bars an 18:00-anchored VWAP "
             "needs",
             "the engine consumes a continuous 1-minute stream. KNOWN GAP: no historical "
             "loader for an 18:00-anchored stream exists yet"),
    Conflict("C7", "markets.futures_cme.features.vwap_dist",
             "the existing feature is close-weighted and frame-anchored; the frozen VWAP is "
             "typical-price weighted and 18:00-anchored. Same word, different quantity",
             "not reused; named SessionVwap"),
    Conflict("C8", "markets.futures_cme.instruments NQ commission",
             "the repository cites Topstep's published $3.78 round turn; the frozen spec "
             "says $4.50",
             "the frozen spec wins for this strategy and is the more conservative of the "
             "two; the engine does not read the instrument default"),
    # DECISION 4. The owner's register assigns C9 and C10 to the proximity inequalities, so
    # the timeframe conflict that previously held C9 is renumbered C11. No content changed;
    # `docs/VWAP_PULLBACK_INTEGRATION_PLAN.md` still describes it under its old ref and says
    # so.
    Conflict("C9", "the frozen 5-minute LONG regime proximity inequality",
             "`VWAP - 5m low <= 6.0` is satisfied by a candle lying ENTIRELY ABOVE the VWAP, "
             "because the left-hand side is then negative. With VWAP 20,000 and a 5m low of "
             "20,005 the expression is -5 <= 6, which is true. A bar that never came near "
             "the VWAP therefore qualifies as a pullback regime.",
             "NOT AN IMPLEMENTATION DEFECT. The engine matches the literal frozen rule and "
             "`tests/test_vwap_strategy.py` proves the literal behaviour on both a candle "
             "spanning the VWAP and one entirely above it. Reported as a STRATEGY-DEFINITION "
             "CHARACTERISTIC; the inequality is NOT to be reinterpreted without an explicit "
             "instruction."),
    Conflict("C10", "the frozen 5-minute SHORT regime proximity inequality",
             "the exact mirror: `5m high - VWAP <= 6.0` is satisfied by a candle lying "
             "ENTIRELY BELOW the VWAP. With VWAP 20,000 and a 5m high of 19,995 the "
             "expression is -5 <= 6.",
             "NOT AN IMPLEMENTATION DEFECT. Literal behaviour implemented and tested on both "
             "sides. Reported as a strategy-definition characteristic."),
    Conflict("C11", "research.strategy_spec timeframe guard",
             "the certified interface refuses any timeframe but 1min because resampling is "
             "unaudited; this strategy needs 5-minute context",
             "5-minute bars are derived inside the engine, causally, from the 1-minute "
             "stream; no data-layer resampling is introduced"),
)


@dataclass(frozen=True)
class ExecutionProfile:
    """How much adverse slippage each KIND of fill carries, in ticks.

    DECISION 3. The frozen specification states one tick on the entry and one on stop-outs,
    and says nothing at all about the three MARKET exits it also defines - the 15:45 safety
    flatten, the -$800 governor flatten and the +25 stall close. Those are genuine market
    orders and are not realistically frictionless; the specification simply does not price
    them, and inventing a number would be a strategy change wearing a modelling costume.

    So the baseline charges EXACTLY what V1.0.0 states and nothing more, and the stress
    profiles exist beside it to measure what the silence is worth. The stress profiles are
    DIAGNOSTIC: nothing in the engine chooses between them, and no strategy rule reads them.

        profile          entry   stop*   target**  market exit***
        IDEAL              0       0        0           0
        BASELINE_FROZEN    1       1        0           0        <- V1.0.0 exactly
        STRESS_1TICK       1       2        0           1
        STRESS_2TICK       1       3        0           2

          *  the initial stop AND the break-even stop. DECISION 3 is explicit that a
             break-even stop is a stop-out when it executes, so it carries the stop's tick.
          ** a LIMIT order. It fills at its price or it does not fill; no profile charges it.
          *** the 15:45 flatten, the governor flatten and the stall market close.

    THE READING TAKEN, stated because "all market exits" admits two. A triggered stop IS a
    market order, so the stress adds its ticks to the stop as well as to the three flattens -
    the more conservative of the two readings. The alternative, adding only to the three
    exits the frozen spec leaves unpriced, would isolate the gap more cleanly but understates
    a stressed tape. Recorded as AMBIGUITY A16.
    """

    name: str
    intent: str
    entry_ticks: float
    stop_ticks: float
    target_ticks: float
    market_exit_ticks: float
    #: True for the one profile that charges exactly what V1.0.0 states, and no more.
    frozen_spec_exact: bool = False

    def as_row(self) -> dict:
        return {"name": self.name, "entry_ticks": self.entry_ticks,
                "stop_ticks": self.stop_ticks, "target_ticks": self.target_ticks,
                "market_exit_ticks": self.market_exit_ticks,
                "frozen_spec_exact": self.frozen_spec_exact, "intent": self.intent}


IDEAL = ExecutionProfile(
    name="IDEAL",
    intent="the frictionless bound. Not executable, and never a headline: it exists so the "
           "distance between it and the baseline is visible as a number.",
    entry_ticks=0.0, stop_ticks=0.0, target_ticks=0.0, market_exit_ticks=0.0)

BASELINE_FROZEN = ExecutionProfile(
    name="BASELINE_FROZEN",
    intent="EXACTLY what V1.0.0 states: one tick on the entry, one on stop-outs (including "
           "the break-even stop), nothing on the target, and NOTHING invented for the three "
           "market exits the specification leaves unpriced.",
    entry_ticks=1.0, stop_ticks=1.0, target_ticks=0.0, market_exit_ticks=0.0,
    frozen_spec_exact=True)

STRESS_1TICK = ExecutionProfile(
    name="STRESS_1TICK",
    intent="diagnostic: one additional tick of adverse slippage on every market-executed "
           "exit. Measures what the specification's silence about the flattens is worth.",
    entry_ticks=1.0, stop_ticks=2.0, target_ticks=0.0, market_exit_ticks=1.0)

STRESS_2TICK = ExecutionProfile(
    name="STRESS_2TICK",
    intent="diagnostic: two additional ticks on every market-executed exit. A strategy that "
           "survives here is not relying on the unpriced exits.",
    entry_ticks=1.0, stop_ticks=3.0, target_ticks=0.0, market_exit_ticks=2.0)

#: The ladder, in order. `BASELINE_FROZEN` is the only one that is the frozen specification;
#: the others are measurements taken beside it.
EXECUTION_LADDER: tuple[ExecutionProfile, ...] = (IDEAL, BASELINE_FROZEN, STRESS_1TICK,
                                                  STRESS_2TICK)
EXECUTION_PROFILES: dict[str, ExecutionProfile] = {p.name: p for p in EXECUTION_LADDER}


def execution_profile(name: str) -> ExecutionProfile:
    try:
        return EXECUTION_PROFILES[name]
    except KeyError:
        raise KeyError(f"unknown execution profile {name!r}; known: "
                       f"{', '.join(EXECUTION_PROFILES)}") from None


def execution_table() -> str:
    """The assumption table, printed before any run that uses a profile."""
    head = (f"  {'profile':17} {'entry':>6} {'stop':>6} {'target':>7} {'mkt exit':>9}  "
            f"{'= V1.0.0':>9}")
    rows = [head, "  " + "-" * (len(head) - 2)]
    for pr in EXECUTION_LADDER:
        rows.append(f"  {pr.name:17} {pr.entry_ticks:6.0f} {pr.stop_ticks:6.0f} "
                    f"{pr.target_ticks:7.0f} {pr.market_exit_ticks:9.0f}  "
                    f"{str(pr.frozen_spec_exact):>9}")
    rows.append("  ticks of ADVERSE slippage. The target is a limit order and is never "
                "charged.")
    rows.append("  stop covers the initial stop AND the break-even stop (DECISION 3).")
    return "\n".join(rows)


@dataclass(frozen=True)
class FrozenSpec:
    """Every constant the strategy obeys. Immutable, hashed, and asserted by test."""

    version: str = VERSION

    # -- session and clock ----------------------------------------------------------------
    #: The VWAP anchor and the trading-day boundary, as (hour, minute) on the venue clock.
    session_anchor: tuple[int, int] = (18, 0)
    monitor_start: tuple[int, int] = (9, 45)
    last_entry: tuple[int, int] = (15, 30)
    hard_flatten: tuple[int, int] = (15, 45)
    #: A bar stamped exactly at `last_entry` is the LAST bar an entry may be decided on.
    last_entry_inclusive: bool = True

    # -- 5-minute context -----------------------------------------------------------------
    atr_period: int = 14
    atr_method: str = "wilder"              # AMBIGUITY A1. "sma" is the alternative.
    atr_minimum: float = 8.0
    context_max_distance: float = 6.0

    # -- 1-minute trigger -----------------------------------------------------------------
    long_zone: tuple[float, float] = (-8.0, 2.0)     # offsets from VWAP
    short_zone: tuple[float, float] = (-2.0, 8.0)
    volume_sma_period: int = 10
    volume_multiple: float = 1.2
    invalidation_distance: float = 15.0

    # -- brackets -------------------------------------------------------------------------
    stop_points: float = 15.0
    target_points: float = 30.0
    breakeven_trigger: float = 15.0
    breakeven_offset: float = 0.25
    stall_mfe: float = 25.0
    stall_window: int = 3
    stall_target: float = 20.0

    # -- governor -------------------------------------------------------------------------
    daily_loss_killswitch: float = -800.0
    daily_profit_cap: float = 1200.0
    max_trades_per_day: int = 4
    consecutive_losses_for_cooldown: int = 2
    cooldown_minutes: int = 45
    governor_mtm_basis: str = "intrabar"    # AMBIGUITY A2. "close" is the alternative.

    # -- instrument and costs -------------------------------------------------------------
    instrument: str = "NQ"
    contracts: int = 1
    #: The frozen round turn, in dollars for the WHOLE position. CONFLICT C8: the repository
    #: cites $3.78 for NQ; the frozen spec says $4.50 and the frozen spec wins here.
    commission_round_turn: float = 4.50
    #: Ticks of adverse slippage per fill kind, applied to the FILL PRICE. The default is
    #: BASELINE_FROZEN - exactly what V1.0.0 states. The stress profiles are diagnostic and
    #: are selected explicitly; nothing in the engine chooses between them.
    execution: ExecutionProfile = BASELINE_FROZEN

    notes: dict = field(default_factory=dict)

    # -- slippage, read through the profile so the two can never disagree --------------------

    @property
    def slippage_ticks_entry(self) -> float:
        return self.execution.entry_ticks

    @property
    def slippage_ticks_stop(self) -> float:
        """The initial stop AND the break-even stop: a break-even stop is a stop-out."""
        return self.execution.stop_ticks

    @property
    def slippage_ticks_target(self) -> float:
        return self.execution.target_ticks

    @property
    def slippage_ticks_market_exit(self) -> float:
        """The 15:45 flatten, the governor flatten and the stall market close."""
        return self.execution.market_exit_ticks

    def with_execution(self, name: str) -> FrozenSpec:
        """The same strategy under a different execution profile. Changes NO strategy rule."""
        import dataclasses
        return dataclasses.replace(self, execution=execution_profile(name))

    def __post_init__(self) -> None:
        if self.atr_method not in ("wilder", "sma"):
            raise ValueError(f"atr_method {self.atr_method!r} is not one of wilder, sma")
        if self.governor_mtm_basis not in ("intrabar", "close"):
            raise ValueError(
                f"governor_mtm_basis {self.governor_mtm_basis!r} is not one of "
                f"intrabar, close")
        if self.contracts < 1:
            raise ValueError("contracts must be at least 1")
        if self.stall_window < 1:
            raise ValueError("stall_window must be at least 1 bar")

    # -- derived instrument economics -------------------------------------------------------

    @property
    def point_value(self) -> float:
        """Dollars per index point for the WHOLE position. NQ x1 and MNQ x10 both give 20."""
        from quant_brain.markets.futures_cme import instruments as inst
        return float(inst.get(self.instrument).spec.multiplier) * self.contracts

    @property
    def tick(self) -> float:
        from quant_brain.markets.futures_cme import instruments as inst
        return float(inst.get(self.instrument).spec.tick)

    @property
    def tick_value(self) -> float:
        """Dollars per tick for the WHOLE position."""
        return self.tick * self.point_value

    def anchor_minute(self) -> int:
        return self.session_anchor[0] * 60 + self.session_anchor[1]

    def minute_of(self, which: str) -> int:
        h, m = getattr(self, which)
        return h * 60 + m

    # -- identity ---------------------------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def spec_hash(self) -> str:
        """sha256 over every declared constant. A changed number is a changed strategy."""
        blob = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def describe(self) -> str:
        pv, tk = self.point_value, self.tick
        return "\n".join([
            f"STRATEGY     Intraday Multi-Timeframe VWAP Pullback {self.version}",
            f"SPEC HASH    {self.spec_hash}",
            f"INSTRUMENT   {self.contracts} x {self.instrument}   "
            f"${pv:,.2f}/point   tick {tk:g} = ${self.tick_value:,.2f}",
            f"CLOCK        {TIMEZONE.key}; VWAP anchor "
            f"{self.session_anchor[0]:02d}:{self.session_anchor[1]:02d}",
            f"WINDOWS      monitor {self.monitor_start[0]:02d}:{self.monitor_start[1]:02d} | "
            f"last entry {self.last_entry[0]:02d}:{self.last_entry[1]:02d}"
            f"{' (inclusive)' if self.last_entry_inclusive else ''} | "
            f"hard flatten {self.hard_flatten[0]:02d}:{self.hard_flatten[1]:02d}",
            f"5m CONTEXT   ATR({self.atr_period}) [{self.atr_method}] >= "
            f"{self.atr_minimum:g} pts; within {self.context_max_distance:g} pts of VWAP",
            f"1m TRIGGER   long zone VWAP{self.long_zone[0]:+g}..{self.long_zone[1]:+g} | "
            f"short zone VWAP{self.short_zone[0]:+g}..{self.short_zone[1]:+g} | "
            f"volume >= {self.volume_multiple:g}x SMA({self.volume_sma_period})",
            f"INVALIDATION {self.invalidation_distance:g} pts beyond VWAP",
            f"BRACKET      stop {self.stop_points:g} | target {self.target_points:g} | "
            f"BE at +{self.breakeven_trigger:g} -> fill{self.breakeven_offset:+g}",
            f"STALL        MFE +{self.stall_mfe:g}, {self.stall_window} bars, "
            f"target -> fill{self.stall_target:+g}",
            f"GOVERNOR     kill {self.daily_loss_killswitch:+,.0f} MTM "
            f"[{self.governor_mtm_basis}] | cap {self.daily_profit_cap:+,.0f} realized | "
            f"max {self.max_trades_per_day} trades | "
            f"{self.consecutive_losses_for_cooldown} losses -> "
            f"{self.cooldown_minutes}m cooldown",
            f"COSTS        ${self.commission_round_turn:,.2f} round turn",
            f"EXECUTION    {self.execution.name}"
            + ("  (V1.0.0 EXACTLY)" if self.execution.frozen_spec_exact
               else "  DIAGNOSTIC - not the frozen specification")
            + f" | entry {self.slippage_ticks_entry:g}t, stop "
              f"{self.slippage_ticks_stop:g}t, target {self.slippage_ticks_target:g}t, "
              f"market exit {self.slippage_ticks_market_exit:g}t",
        ])


#: The single frozen instance. NQ, one contract.
FROZEN = FrozenSpec()

#: The MNQ override: ten micros, identical $20/point exposure. CONFLICT/AMBIGUITY A11 - the
#: frozen cost model states no MNQ commission, so the repository's measured rate is used.
FROZEN_MNQ = FrozenSpec(instrument="MNQ", contracts=10, commission_round_turn=12.20,
                        notes={"commission_source": "AMBIGUITY A11: the frozen spec states a "
                                                    "round turn for NQ only. $1.22 x 10 is "
                                                    "the repository's measured MNQ rate."})


def unresolved() -> tuple[Ambiguity, ...]:
    """Material ambiguities the owner has NOT ruled on. Empty is what certification needs."""
    return tuple(a for a in AMBIGUITIES if a.needs_owner)


def resolved() -> tuple[Ambiguity, ...]:
    return tuple(a for a in AMBIGUITIES if a.status == RESOLVED)


def characteristics() -> tuple[Conflict, ...]:
    """Register entries that are properties of the SPECIFICATION, not defects in the code."""
    return tuple(c for c in CONFLICTS if c.ref in ("C9", "C10"))


__all__ = ["AMBIGUITIES", "BASELINE_FROZEN", "CONFLICTS", "EXECUTION_LADDER",
           "EXECUTION_PROFILES", "FROZEN", "FROZEN_MNQ", "IDEAL", "OPEN", "RESOLVED",
           "STRESS_1TICK", "STRESS_2TICK", "TIMEZONE", "VERSION", "Ambiguity", "Conflict",
           "ExecutionProfile", "FrozenSpec", "characteristics", "execution_profile",
           "execution_table", "resolved", "unresolved"]
