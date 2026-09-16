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
              "Wilder - the conventional meaning of ATR(14) in every charting package",
              material=True, both_implemented=True),
    Ambiguity("A2", "governor mark-to-market",
              "is unrealised P&L read at the bar close or at the bar's adverse extreme?",
              "the adverse extreme - a killswitch that only looks at closes does not protect "
              "against the move that breaches between them",
              material=True, both_implemented=True),
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
              "NO - the frozen spec names entry and stop-outs only, and §13 forbids applying "
              "it elsewhere silently. This is OPTIMISTIC for three exit kinds and is "
              "reported as such",
              material=True),
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
    Conflict("C9", "research.strategy_spec timeframe guard",
             "the certified interface refuses any timeframe but 1min because resampling is "
             "unaudited; this strategy needs 5-minute context",
             "5-minute bars are derived inside the engine, causally, from the 1-minute "
             "stream; no data-layer resampling is introduced"),
)


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
    #: Ticks of adverse slippage, applied to the FILL PRICE. AMBIGUITY A12: entry and
    #: stop-outs only - targets are limit fills and the three market-flatten kinds are not
    #: charged, which is optimistic and reported.
    slippage_ticks_entry: float = 1.0
    slippage_ticks_stop: float = 1.0
    slippage_ticks_target: float = 0.0
    slippage_ticks_flatten: float = 0.0

    notes: dict = field(default_factory=dict)

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
            f"COSTS        ${self.commission_round_turn:,.2f} round turn | slippage "
            f"entry {self.slippage_ticks_entry:g}t, stop {self.slippage_ticks_stop:g}t, "
            f"target {self.slippage_ticks_target:g}t, flatten "
            f"{self.slippage_ticks_flatten:g}t",
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
    """Ambiguities whose reading materially changes results and needs owner confirmation."""
    return tuple(a for a in AMBIGUITIES if a.material)


__all__ = ["AMBIGUITIES", "CONFLICTS", "FROZEN", "FROZEN_MNQ", "TIMEZONE", "VERSION",
           "Ambiguity", "Conflict", "FrozenSpec", "unresolved"]
