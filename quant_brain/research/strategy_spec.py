"""The frozen-strategy interface: what a human supplies, and what the engine may not change.

THE CONTRACT
------------
The human supplies a `StrategySpec`. The engine runs it. The engine does not tune it, does not
select among variants, does not substitute defaults for missing fields, and does not silently
reinterpret anything. A field the caller did not set is either a documented default recorded in
the provenance block, or the run refuses to start.

The spec is hashed. Every result carries the hash. If the spec changes, the hash changes, and
a result carrying the old hash cannot be confused with the new strategy.

WHAT A CALLER CAN STATE
-----------------------
    instrument                 StrategySpec.instrument
    timeframe                  StrategySpec.timeframe
    session / window           SessionSpec.open_et, close_et
    entry conditions           StrategySpec.signal  (a callable over the feature frame)
    long / short conditions    the sign of what `signal` returns: +1 long, -1 short, 0 flat
    position sizing            SizingSpec.contracts
    stop                       ExitSpec.stop_points | stop_atr | structural_stop
    target                     ExitSpec.target_points | target_r
    trailing logic             ExitSpec.trail_points | trail_atr, breakeven_at_r
    time-based exit            ExitSpec.time_stop_bars
    forced-flat behaviour      SessionSpec.flat_by_et, and the venue's own mandatory flat
    max simultaneous positions RiskSpec.max_open_positions
    cooldown                   RiskSpec.cooldown_bars
    max trades / session       RiskSpec.max_trades_per_session
    strategy-specific state    StrategySpec.params  (declared, hashed, reported)

WHY THE SIGNAL IS A CALLABLE AND THE EXIT IS DECLARATIVE
----------------------------------------------------------
Entry logic is where strategies genuinely differ, and any declarative language rich enough to
express real entries becomes a programming language with a worse debugger. So the entry is a
plain Python callable over a feature frame - the same shape the existing library uses - and its
source is hashed so it cannot change without the hash changing.

Exit logic is the opposite: a small number of well-understood primitives (stop, target, trail,
break-even, time, invalidation) that benefit from being declarative because that is what makes
them auditable and what stops an exit quietly becoming a second entry model.

TWO DISTANCES, NEVER TRANSLATED INTO EACH OTHER
-------------------------------------------------
Every price-based leg can be given as INDEX POINTS or as an ATR MULTIPLE, and the engine will
not convert one into the other. "A ten-point stop" and "a 1.4-ATR stop" are different
strategies: the second one is a different distance on every session. A leg given both ways is
refused rather than resolved, because resolving it would mean choosing on the author's behalf.

WHAT THE ENGINE ENFORCES REGARDLESS OF WHAT THE CALLER ASKS FOR
-----------------------------------------------------------------
Four things are not negotiable, because they are properties of the venue rather than of the
strategy:

    - the session ends flat. Topstep's mandatory flat is 15:10 CT and is not a parameter.
    - every completed round turn is charged. There is no zero-cost mode that is reachable by
      accident; gross is reported alongside net, never instead of it.
    - a position decided on bar i is filled at bar i's close and earns from bar i's close
      onward. A caller cannot request a fill at a price that existed before the information
      the decision used.
    - a resting price must be a whole number of ticks. A stop 10.1 points away on a 0.25-tick
      instrument is an order no exchange would accept, so it is refused rather than rounded.

A spec that conflicts with any of these is rejected at construction rather than quietly
adjusted.

AMBIGUITY IS AN ERROR, NOT A DEFAULT
--------------------------------------
`StrategySpec.ambiguities()` lists every under-specified rule it can find, and construction
raises on any of them. The list exists because the failure mode this interface is built against
is not a wrong number - it is a right number computed from a rule the author never stated. The
clearest case: `target_r` means "R multiples of the initial stop", and with no stop the exit
simulator would fall back to the session ATR. That silent substitution is refused.
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
EXIT_PRIMITIVES = ("stop_atr", "stop_points", "target_r", "target_points", "structural_stop",
                   "trail_atr", "trail_points", "breakeven_at_r", "time_stop_bars",
                   "use_invalidation")

#: Wall-clock times are compared as strings throughout the engine, which is only safe in a
#: fixed-width zero-padded format. Parsed here so a malformed one cannot reach a comparison.
_TIME_LEN = 5


class SpecError(ValueError):
    """A spec the engine will not run. Always raised at construction, never at run time."""


class AmbiguousSpec(SpecError):
    """A rule with more than one reasonable reading. The engine refuses to pick one."""


def _minutes(hhmm: str, what: str) -> int:
    """Minutes past midnight on the venue clock, parsed strictly."""
    if not isinstance(hhmm, str) or len(hhmm) != _TIME_LEN or hhmm[2] != ":":
        raise SpecError(f"{what} is {hhmm!r}; it must be a zero-padded HH:MM wall-clock "
                        f"time such as '09:30'")
    try:
        h, m = int(hhmm[:2]), int(hhmm[3:])
    except ValueError as exc:
        raise SpecError(f"{what} is {hhmm!r}; it must be HH:MM") from exc
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise SpecError(f"{what} is {hhmm!r}; it is not a valid time of day")
    return h * 60 + m


@dataclass(frozen=True)
class ExitSpec:
    """Declarative exit. `None` means the leg is absent, never zero.

    Each of the three price legs has a POINTS form and an ATR form. Set one or neither.
    """

    #: Initial stop as an ATR multiple of the entry session's average true range.
    stop_atr: float | None = None
    #: Initial stop as a fixed distance in index points.
    stop_points: float | None = None
    #: Target in multiples of R, where R is the INITIAL STOP DISTANCE. Requires a stop.
    target_r: float | None = None
    #: Target as a fixed distance in index points from the entry price.
    target_points: float | None = None
    #: Stop at the signal bar's own extreme rather than at a measured distance.
    structural_stop: bool = False
    #: Trailing stop distance as an ATR multiple.
    trail_atr: float | None = None
    #: Trailing stop distance in index points.
    trail_points: float | None = None
    #: Move the stop to the entry price once this many R of favourable excursion is reached.
    #: Requires a stop, for the same reason `target_r` does.
    breakeven_at_r: float | None = None
    #: Hard exit this many bars after entry.
    time_stop_bars: int | None = None
    #: Exit when the originating signal stops being true.
    use_invalidation: bool = True

    def __post_init__(self) -> None:
        stops = [n for n in ("stop_atr", "stop_points") if getattr(self, n) is not None]
        if self.structural_stop:
            stops.append("structural_stop")
        if len(stops) > 1:
            raise AmbiguousSpec(
                f"{', '.join(stops)} are {len(stops)} different stops. Set exactly one. "
                f"Silently preferring any of them would make the result depend on an "
                f"undocumented choice.")
        if self.target_r is not None and self.target_points is not None:
            raise AmbiguousSpec(
                "target_r and target_points are two different targets. A target in R moves "
                "with the stop distance and a target in points does not; they are the same "
                "number only by coincidence. Set one.")
        if self.trail_atr is not None and self.trail_points is not None:
            raise AmbiguousSpec(
                "trail_atr and trail_points are two different trails. Set one.")

        for name in ("stop_atr", "stop_points", "target_r", "target_points", "trail_atr",
                     "trail_points", "breakeven_at_r"):
            v = getattr(self, name)
            if v is not None and (not isinstance(v, (int, float)) or v <= 0):
                raise SpecError(
                    f"{name} must be a positive distance, got {v!r}. A non-positive stop or "
                    f"target is an immediate exit, not a level.")
        if self.time_stop_bars is not None and self.time_stop_bars < 1:
            raise SpecError("time_stop_bars must be at least 1 bar")

        # R is the initial stop distance. Without a stop the exit simulator falls back to the
        # session ATR as a nominal R for reporting - and if a target were allowed to read that
        # fallback, "2R" would silently mean "2 ATR", which is a different strategy.
        if not self.has_stop:
            for name in ("target_r", "breakeven_at_r"):
                if getattr(self, name) is not None:
                    raise AmbiguousSpec(
                        f"{name} is stated in multiples of R, but this exit has no initial "
                        f"stop, so R is undefined. The engine will NOT substitute the session "
                        f"ATR for R. State the stop (stop_points / stop_atr / "
                        f"structural_stop), or state the target in points via target_points.")

        if not any([self.stop_atr, self.stop_points, self.structural_stop, self.trail_atr,
                    self.trail_points, self.target_r, self.target_points,
                    self.time_stop_bars, self.use_invalidation]):
            raise SpecError(
                "this exit has no way to close a position except the session-end flatten. "
                "That is legal but must be stated explicitly: set use_invalidation=False "
                "AND time_stop_bars to the session length if it is what you mean.")

    @property
    def has_stop(self) -> bool:
        """Whether an INITIAL stop exists. A trail is not one - it starts at the entry and
        only becomes binding later, so it cannot define the risk that was on at entry."""
        return (self.structural_stop or self.stop_atr is not None
                or self.stop_points is not None)

    @property
    def price_legs(self) -> dict[str, float]:
        """The legs expressed in POINTS, for the tick-validity check. ATR legs are excluded:
        their distance is not known until the session is loaded."""
        return {n: getattr(self, n) for n in ("stop_points", "target_points", "trail_points")
                if getattr(self, n) is not None}

    def describe(self) -> str:
        bits = []
        if self.structural_stop:
            bits.append("stop at the signal bar's extreme")
        elif self.stop_points is not None:
            bits.append(f"stop {self.stop_points:g} pts")
        elif self.stop_atr is not None:
            bits.append(f"stop {self.stop_atr:g} ATR")
        else:
            bits.append("NO STOP")
        if self.target_points is not None:
            bits.append(f"target {self.target_points:g} pts")
        elif self.target_r is not None:
            bits.append(f"target {self.target_r:g}R")
        if self.trail_points is not None:
            bits.append(f"trail {self.trail_points:g} pts")
        elif self.trail_atr is not None:
            bits.append(f"trail {self.trail_atr:g} ATR")
        if self.breakeven_at_r is not None:
            bits.append(f"break-even at {self.breakeven_at_r:g}R")
        if self.time_stop_bars is not None:
            bits.append(f"time stop {self.time_stop_bars} bars")
        bits.append("exit on signal invalidation" if self.use_invalidation
                    else "no signal-invalidation exit")
        return "; ".join(bits)


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
            raise SpecError("contracts must be at least 1")
        if self.max_contracts is not None and self.contracts > self.max_contracts:
            raise SpecError(f"contracts {self.contracts} exceeds max_contracts "
                            f"{self.max_contracts}")

    def describe(self) -> str:
        return (f"{self.contracts} contract(s) per trade, fixed"
                + (f", ceiling {self.max_contracts}" if self.max_contracts else ""))


@dataclass(frozen=True)
class RiskSpec:
    """How many trades may be open, how often, and how many in a session.

    These were IMPLICIT in the engine before they were fields here: one position at a time,
    re-entry permitted on the bar after an exit, unlimited trades per session. Naming them
    puts them in the spec hash and in the report, so a reader of a result knows which rules
    produced it rather than having to read the ledger builder.
    """

    #: Positions open at once. The engine simulates ONE and refuses anything else rather than
    #: approximating a pyramid; see the message below.
    max_open_positions: int = 1
    #: Bars that must pass after an exit before a new entry is permitted. 0 means the very
    #: next bar may re-enter, which is the engine's historical behaviour.
    cooldown_bars: int = 0
    #: Hard cap on entries within one session. None means no cap.
    max_trades_per_session: int | None = None

    def __post_init__(self) -> None:
        if self.max_open_positions != 1:
            raise SpecError(
                f"max_open_positions={self.max_open_positions}: the execution simulator "
                f"models ONE position at a time. It cannot scale in, scale out, or hold two "
                f"directions at once, and approximating a multi-position strategy as a "
                f"single position would be a different strategy reported under this one's "
                f"name. This is a stated engine limitation, not a preference - if the "
                f"strategy needs more, say so and it becomes a scoped engine change with "
                f"its own tests.")
        if self.cooldown_bars < 0:
            raise SpecError("cooldown_bars cannot be negative")
        if self.max_trades_per_session is not None and self.max_trades_per_session < 1:
            raise SpecError("max_trades_per_session must be at least 1, or None for no cap")

    def describe(self) -> str:
        return (f"{self.max_open_positions} position at a time; "
                f"cooldown {self.cooldown_bars} bar(s); "
                + (f"max {self.max_trades_per_session} trades/session"
                   if self.max_trades_per_session is not None
                   else "no cap on trades/session"))


@dataclass(frozen=True)
class SessionSpec:
    """Trading window and forced-flat behaviour. The venue's own flatten is not a parameter."""

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
    #: The same rule stated as a wall-clock time, which is how a trader states it. Resolved
    #: to a bar index against the actual window at run time. Mutually exclusive with
    #: `last_entry_bar` - two ways of saying it is one way too many.
    last_entry_et: str | None = None
    #: The strategy's OWN forced flat, inside the session. None means the session close does
    #: it. This is distinct from the venue's mandatory flat, which applies either way.
    flat_by_et: str | None = None

    def __post_init__(self) -> None:
        o = _minutes(self.open_et, "open_et")
        c = _minutes(self.close_et, "close_et")
        if c <= o:
            raise SpecError(f"close_et {self.close_et} is not after open_et {self.open_et}")
        if self.close_et > "16:10":
            raise SpecError(
                f"close_et {self.close_et} is after the Topstep mandatory flat of 15:10 CT "
                f"(16:10 ET). The engine will not model a position held past the deadline.")
        if self.warmup_bars < 0:
            raise SpecError("warmup_bars cannot be negative")
        if self.last_entry_bar is not None and self.last_entry_et is not None:
            raise AmbiguousSpec(
                "last_entry_bar and last_entry_et both set. They are two spellings of one "
                "rule and can disagree. Set one.")
        if self.last_entry_bar is not None and self.last_entry_bar < 0:
            raise SpecError("last_entry_bar cannot be negative")
        if self.last_entry_et is not None:
            le = _minutes(self.last_entry_et, "last_entry_et")
            if not (o <= le <= c):
                raise SpecError(
                    f"last_entry_et {self.last_entry_et} is outside the session "
                    f"{self.open_et}-{self.close_et}")
        if self.flat_by_et is not None:
            fb = _minutes(self.flat_by_et, "flat_by_et")
            if not (o < fb <= c):
                raise SpecError(
                    f"flat_by_et {self.flat_by_et} is outside the session "
                    f"{self.open_et}-{self.close_et}")
            if self.last_entry_et is not None and _minutes(self.last_entry_et, "x") >= fb:
                raise SpecError(
                    f"last_entry_et {self.last_entry_et} is at or after flat_by_et "
                    f"{self.flat_by_et}: an entry there could never be held for a bar.")

    def describe(self) -> str:
        bits = [f"{self.open_et}-{self.close_et} ET"]
        if self.warmup_bars:
            bits.append(f"no entry for the first {self.warmup_bars} bars")
        if self.last_entry_et:
            bits.append(f"no new entry after {self.last_entry_et}")
        elif self.last_entry_bar is not None:
            bits.append(f"no new entry after bar {self.last_entry_bar}")
        else:
            bits.append("no new entry on the final bar")
        bits.append(f"forced flat at {self.flat_by_et}" if self.flat_by_et
                    else "forced flat at the session close")
        return "; ".join(bits)


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

    def describe(self) -> str:
        c = ("repository-measured commission" if self.commission_round_turn is None
             else f"commission ${self.commission_round_turn:g}/round turn")
        return (f"{c}; spread {'charged' if self.include_spread else 'NOT charged'}; "
                f"spec slippage {self.slippage_ticks:g} ticks "
                f"(the execution ladder adds its own on top)")


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
    risk: RiskSpec = field(default_factory=RiskSpec)
    #: Strategy-specific state: thresholds, lookbacks, anything the signal is parameterised
    #: by. Declared here so it is hashed and printed in the report. The engine never reads
    #: it - the signal closes over its own literals - but a result whose parameters are not
    #: written down anywhere is a result nobody can reproduce.
    params: dict = field(default_factory=dict)
    #: Free text describing the mechanism. Recorded, never parsed.
    rationale: str = ""
    #: Anything else the author wants carried into the provenance block.
    notes: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeframe != "1min":
            raise SpecError(
                f"timeframe {self.timeframe!r} is not supported. The data store is 1-minute "
                f"bars; resampling to another timeframe is a data transformation that has "
                f"not been audited for leakage and will not be done silently.")
        if not callable(self.signal):
            raise TypeError("signal must be a callable over the feature frame")
        if not self.name or not self.name.strip():
            raise SpecError("a strategy needs a name; the result files are keyed on it")
        bad = self.ambiguities()
        if bad:
            raise AmbiguousSpec(
                "this spec has rules with more than one reading, and the engine will not "
                "choose between them:\n  - " + "\n  - ".join(bad))

    # -- validation ---------------------------------------------------------------------

    def ambiguities(self) -> list[str]:
        """Every under-specified rule, named. Empty means the spec states what it will do.

        Checked at construction, and available to a caller that wants to inspect a spec
        without building one. Instrument-dependent checks live here rather than on `ExitSpec`
        because a tick size belongs to the instrument, and `ExitSpec` does not know it.
        """
        out: list[str] = []
        tick = self._tick_size()
        if tick is None:
            out.append(
                f"instrument {self.instrument!r} is not in the contract registry, so no tick "
                f"size, multiplier or commission is known for it. The engine will not price "
                f"a trade on an instrument it cannot describe.")
        else:
            for name, pts in self.exit.price_legs.items():
                n = pts / tick
                if abs(n - round(n)) > 1e-9:
                    lo, hi = int(n) * tick, (int(n) + 1) * tick
                    out.append(
                        f"{name}={pts:g} is {n:.4f} ticks on {self.instrument} "
                        f"(tick {tick:g}). A resting order at a fraction of a tick is an "
                        f"order the exchange would reject, and a fill simulated there is a "
                        f"fill at a price that could not exist. Use {lo:g} or {hi:g}.")
        if (self.exit.time_stop_bars is not None
                and self.exit.time_stop_bars >= self._session_bars()):
            out.append(
                f"time_stop_bars={self.exit.time_stop_bars} is at least the whole session "
                f"({self._session_bars()} bars), so it can never fire before the forced "
                f"flat. Either shorten it or drop it and say the exit is the flatten.")
        if self.session.warmup_bars >= self._session_bars() - 1:
            out.append(
                f"warmup_bars={self.session.warmup_bars} leaves no bar on which an entry is "
                f"permitted in a {self._session_bars()}-bar session.")
        return out

    def _tick_size(self) -> float | None:
        """The instrument's tick, or None when the registry does not know the instrument.

        Only `KeyError` is caught - that is the registry's own "I do not know this root".
        A broader catch would turn a real bug in the instrument layer into the misleading
        message "not in the contract registry".
        """
        from quant_brain.markets.futures_cme import instruments as inst
        try:
            return float(inst.get(self.instrument).spec.tick)
        except KeyError:
            return None

    def _multiplier(self) -> float | None:
        """Dollars per point, or None when the registry does not know the instrument."""
        from quant_brain.markets.futures_cme import instruments as inst
        try:
            return float(inst.get(self.instrument).spec.multiplier)
        except KeyError:
            return None

    def _session_bars(self) -> int:
        return (_minutes(self.session.close_et, "close_et")
                - _minutes(self.session.open_et, "open_et") + 1)

    # -- identity -----------------------------------------------------------------------

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
            "risk": asdict(self.risk), "params": self.params,
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

    # -- what the engine will report it tested -------------------------------------------

    def describe(self) -> str:
        """The exact statement of what is being tested. Printed before every run.

        A reader who disagrees with a line here has found a misunderstanding BEFORE the
        result exists, which is the only time it is cheap to find one.
        """
        lines = [
            f"STRATEGY        {self.name}   spec hash {self.spec_hash}",
            f"INSTRUMENT      {self.instrument} @ {self.timeframe}",
            f"SESSION         {self.session.describe()}",
            f"ENTRY           {getattr(self.signal, '__name__', '<lambda>')}() over the "
            f"feature frame; +1 long, -1 short, 0 flat",
            f"SIZING          {self.sizing.describe()}",
            f"EXIT            {self.exit.describe()}",
            f"TRADE LIMITS    {self.risk.describe()}",
            f"COSTS           {self.cost.describe()}",
        ]
        legs = self.exit.price_legs
        tick = self._tick_size()
        if legs and tick:
            # THE UNIT CHECK A READER CAN MAKE. The engine cannot tell that an author who
            # typed `stop_points=10` meant ten TICKS (2.5 points) - both are legal distances
            # and both are whole ticks. Printing every distance in all three units puts the
            # mistake in front of the person who can recognise it, before the run.
            mult = self.sizing.contracts * (self._multiplier() or 0.0)
            lines.append("DISTANCES       " + " | ".join(
                f"{name.replace('_points', '')} {v:g} pts = {v / tick:g} ticks = "
                f"${v * mult:,.2f}" for name, v in sorted(legs.items())))
        if self.params:
            lines.append("PARAMETERS      " + ", ".join(f"{k}={v!r}"
                                                        for k, v in sorted(self.params.items())))
        lines.append("ALWAYS ENFORCED the session ends flat; every round turn is charged; a "
                     "position decided on bar i fills at bar i's close")
        if self.rationale:
            lines.append(f"RATIONALE       {self.rationale}")
        return "\n".join(lines)


__all__ = ["AmbiguousSpec", "CostSpec", "EXIT_PRIMITIVES", "ExitSpec", "RiskSpec",
           "SessionSpec", "SizingSpec", "SpecError", "StrategySpec"]
