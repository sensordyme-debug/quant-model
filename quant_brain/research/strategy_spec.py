"""The frozen-strategy interface: what a human supplies, and what the engine may not change.

THE CONTRACT
------------
The human supplies a `StrategySpec`. The engine runs it. The engine does not tune it, does not
select among variants, does not substitute defaults for missing fields, and does not silently
reinterpret anything. A field the caller did not set is either a documented default recorded in
the provenance block, or the run refuses to start.

The spec is hashed. Every result carries the hash. If the spec changes, the hash changes, and
a result carrying the old hash cannot be confused with the new strategy.

WHY THE SIGNAL IS A CALLABLE AND THE EXIT IS DECLARATIVE
----------------------------------------------------------
Entry logic is where strategies genuinely differ, and any declarative language rich enough to
express real entries becomes a programming language with a worse debugger. So the entry is a
plain Python callable over a feature frame - the same shape the existing library uses - and its
source is hashed so it cannot change without the hash changing.

Exit logic is the opposite: a small number of well-understood primitives (stop, target, trail,
break-even, time, invalidation) that benefit from being declarative because that is what makes
them auditable and what stops an exit quietly becoming a second entry model.

WHAT THE ENGINE ENFORCES REGARDLESS OF WHAT THE CALLER ASKS FOR
-----------------------------------------------------------------
Three things are not negotiable, because they are properties of the venue rather than of the
strategy:

    - the session ends flat. Topstep's mandatory flat is 15:10 CT and is not a parameter.
    - every completed round turn is charged. There is no zero-cost mode that is reachable by
      accident; gross is reported alongside net, never instead of it.
    - a position decided on bar i is filled at bar i's close and earns from bar i's close
      onward. A caller cannot request a fill at a price that existed before the information
      the decision used.

A spec that conflicts with any of these is rejected at construction rather than quietly
adjusted.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

#: The only exit primitives the engine implements. Anything else must be added to the engine
#: and tested, not smuggled in through a lambda.
EXIT_PRIMITIVES = ("stop_atr", "target_r", "structural_stop", "trail_atr",
                   "breakeven_at_r", "time_stop_bars", "use_invalidation")


@dataclass(frozen=True)
class ExitSpec:
    """Declarative exit. `None` means the leg is absent, never zero."""

    stop_atr: float | None = None
    target_r: float | None = None
    structural_stop: bool = False
    trail_atr: float | None = None
    breakeven_at_r: float | None = None
    time_stop_bars: int | None = None
    use_invalidation: bool = True

    def __post_init__(self) -> None:
        if self.structural_stop and self.stop_atr is not None:
            raise ValueError(
                "structural_stop and stop_atr are two different stops. Set one. Silently "
                "preferring either would make the result depend on an undocumented choice.")
        if self.target_r is not None and self.target_r <= 0:
            raise ValueError("target_r must be positive; a non-positive target is an "
                             "immediate exit, not a target")
        if (self.stop_atr is not None and self.stop_atr <= 0):
            raise ValueError("stop_atr must be positive")
        if self.time_stop_bars is not None and self.time_stop_bars < 1:
            raise ValueError("time_stop_bars must be at least 1 bar")
        if not any([self.stop_atr, self.structural_stop, self.trail_atr,
                    self.time_stop_bars, self.use_invalidation]):
            raise ValueError(
                "this exit has no way to close a position except the session-end flatten. "
                "That is legal but must be stated explicitly: set use_invalidation=False "
                "AND time_stop_bars to the session length if it is what you mean.")


@dataclass(frozen=True)
class SizingSpec:
    """Position sizing. Fixed only - anything adaptive must name the information it uses."""

    contracts: int = 1
    max_contracts: int | None = None
    #: Micro-equivalents. Topstep counts 1 mini as 10 micros; the engine enforces the
    #: instrument's own ceiling and will not let a caller exceed it by mislabelling.
    max_micro_equivalent: int | None = 50

    def __post_init__(self) -> None:
        if self.contracts < 1:
            raise ValueError("contracts must be at least 1")
        if self.max_contracts is not None and self.contracts > self.max_contracts:
            raise ValueError(f"contracts {self.contracts} exceeds max_contracts "
                             f"{self.max_contracts}")


@dataclass(frozen=True)
class SessionSpec:
    """Trading window. The flatten is not a parameter."""

    open_et: str = "09:30"
    close_et: str = "16:00"
    #: Bars after the open before an entry is permitted.
    warmup_bars: int = 0
    #: Last bar index at which a NEW position may be opened. None means `n - 2`: the final
    #: bar is EXCLUDED, because a position opened there cannot be held (the session ends
    #: flat) and can only lose a round turn. This was an implicit rule inside the runner
    #: until the independent reference disagreed with it by exactly one round turn; it is
    #: named here so it appears in the spec hash and in the provenance block.
    last_entry_bar: int | None = None

    def __post_init__(self) -> None:
        if self.close_et > "16:10":
            raise ValueError(
                f"close_et {self.close_et} is after the Topstep mandatory flat of 15:10 CT "
                f"(16:10 ET). The engine will not model a position held past the deadline.")


@dataclass(frozen=True)
class CostSpec:
    """Execution assumptions. Slippage is the ROUND-TURN total, in ticks."""

    #: None means "read the repository's measured commission for this instrument". An
    #: explicit 0.0 is permitted for gross reporting and is recorded as such.
    commission_round_turn: float | None = None
    slippage_ticks: float = 0.0
    #: When True the modelled spread crossing is included. The repository's
    #: `round_turn_cost` includes it by default; setting this False isolates commission.
    include_spread: bool = True


@dataclass(frozen=True)
class StrategySpec:
    """One frozen strategy. Immutable input to the engine."""

    name: str
    instrument: str
    timeframe: str
    #: Callable(feature_frame) -> array of positions in {-1, 0, +1}, one per bar.
    signal: Callable[[Any], Any]
    exit: ExitSpec = field(default_factory=ExitSpec)
    sizing: SizingSpec = field(default_factory=SizingSpec)
    session: SessionSpec = field(default_factory=SessionSpec)
    cost: CostSpec = field(default_factory=CostSpec)
    #: Free text describing the mechanism. Recorded, never parsed.
    rationale: str = ""
    #: Anything else the author wants carried into the provenance block.
    notes: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeframe != "1min":
            raise ValueError(
                f"timeframe {self.timeframe!r} is not supported. The data store is 1-minute "
                f"bars; resampling to another timeframe is a data transformation that has "
                f"not been audited for leakage and will not be done silently.")
        if not callable(self.signal):
            raise TypeError("signal must be a callable over the feature frame")

    @property
    def signal_source(self) -> str:
        """The signal's source text, so the hash covers the logic and not just its name."""
        try:
            return inspect.getsource(self.signal)
        except (OSError, TypeError):
            return f"<unavailable: {getattr(self.signal, '__name__', repr(self.signal))}>"

    def to_dict(self) -> dict:
        d = {
            "name": self.name, "instrument": self.instrument, "timeframe": self.timeframe,
            "signal_name": getattr(self.signal, "__name__", "<lambda>"),
            "signal_source": self.signal_source,
            "exit": asdict(self.exit), "sizing": asdict(self.sizing),
            "session": asdict(self.session), "cost": asdict(self.cost),
            "rationale": self.rationale, "notes": self.notes,
        }
        return d

    @property
    def spec_hash(self) -> str:
        """Covers the logic, the parameters and the execution assumptions.

        Deliberately includes `signal_source`: two strategies with the same name and different
        bodies must not share a hash, and a result carrying a hash must be traceable to the
        exact code that produced it.
        """
        blob = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


__all__ = ["CostSpec", "EXIT_PRIMITIVES", "ExitSpec", "SessionSpec", "SizingSpec",
           "StrategySpec"]
