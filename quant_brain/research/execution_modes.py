"""The four execution profiles every canonical run is evaluated under, assumptions declared.

WHY FOUR, AND WHY THE HEADLINE IS NOT THE FIRST ONE
-----------------------------------------------------
A backtest has to choose what it believes about execution, and every one of those beliefs is
worth money. Left implicit, they drift towards the flattering end one at a time and the
result becomes a number no one can defend. So the choices are enumerated, named, and run all
four times; the report shows the whole ladder and takes its headline from CONSERVATIVE.

IDEAL exists to be shown next to the others, not to be quoted. It is the frictionless bound:
no spread, no slippage, and a close-only equity path. Nothing can be executed there. A
strategy that is positive only under IDEAL has found the cost model, not an edge, and the
runner says so in those words.

WHAT EACH MODE FIXES
--------------------
Every field below is an execution assumption, not a strategy parameter. None of them touches
the signal, the entry rule, the exit rule or any threshold - the same frozen spec runs in all
four, and the fills differ only because the execution model differs.

    field                what it decides
    -----                ---------------
    slippage_ticks       round-turn slippage in ticks, ON TOP of commission and spread
    include_spread       whether crossing the bid-ask is charged
    path_mode            how the within-bar equity path is read (see `canonical_ledger`)
    stop_execution       the price a stop is assumed to fill at
    target_execution     the price a target is assumed to fill at
    flatten_execution    the price the bell flattens at
    partial_fills        whether an order can fill in pieces
    ambiguous_bar        what happens when a stop and a target are both reachable in one bar

NOT MODELLED, IN EVERY MODE
-----------------------------
Stated once here rather than discovered later:

    partial fills        every order fills in full or not at all. One-minute OHLCV carries no
                         size, so there is nothing to model a partial against. At one to five
                         contracts on ES/NQ this is a small assumption; at the fifty-micro
                         ceiling in a thin session it is not, and it is NOT MODELLED either
                         way.
    queue position       no notion of resting orders, priority, or being filled because the
                         market traded THROUGH a level rather than to it.
    market impact        the account's own orders never move the price.
    sub-bar sequencing   whether a bar's high came before its low is unknowable from OHLCV.
                         The path modes handle this by assuming the adverse ordering; the
                         fill logic handles it by resolving an ambiguous bar as a stop.
    overnight gaps       positions never survive the bell, so gap risk between sessions never
                         reaches the account. That is a property of the strategies this
                         engine runs, not a modelling shortcut - a spec that held overnight
                         would need this filled in first.
"""
from __future__ import annotations

from dataclasses import dataclass

from quant_brain.research.canonical_ledger import ExecutionPathMode


@dataclass(frozen=True)
class ExecutionProfile:
    """One fully-specified set of execution assumptions. Nothing is left to a default."""

    name: str
    slippage_ticks: float
    include_spread: bool
    path_mode: ExecutionPathMode
    stop_execution: str
    target_execution: str
    flatten_execution: str
    partial_fills: str
    ambiguous_bar: str
    intent: str

    def as_row(self) -> dict:
        return {
            "execution_mode": self.name,
            "execution_path_mode": self.path_mode.value,
            "slippage_ticks_round_turn": self.slippage_ticks,
            "spread_charged": self.include_spread,
            "stop_execution": self.stop_execution,
            "target_execution": self.target_execution,
            "flatten_execution": self.flatten_execution,
            "partial_fill_model": self.partial_fills,
            "ambiguous_bar_model": self.ambiguous_bar,
        }


_STOP = "filled at the stop price; no gap-through penalty beyond the mode's slippage"
_TARGET = "filled at the target price only if the bar traded through it"
_FLAT = "filled at the last bar's close, which is the mandatory flatten"
_NO_PARTIAL = "NOT MODELLED - every order fills in full or not at all"
_AMBIG = "resolved as a STOP and flagged `ambiguous_bar`, never as a target"


IDEAL = ExecutionProfile(
    name="IDEAL", slippage_ticks=0.0, include_spread=False,
    path_mode=ExecutionPathMode.CLOSE_ONLY,
    stop_execution=_STOP, target_execution=_TARGET, flatten_execution=_FLAT,
    partial_fills=_NO_PARTIAL, ambiguous_bar=_AMBIG,
    intent=("The frictionless bound. Not executable and never the headline: it exists so "
            "the distance between it and CONSERVATIVE is visible as a number."))

BASELINE = ExecutionProfile(
    name="BASELINE", slippage_ticks=0.5, include_spread=True,
    path_mode=ExecutionPathMode.CLOSE_ONLY,
    stop_execution=_STOP, target_execution=_TARGET, flatten_execution=_FLAT,
    partial_fills=_NO_PARTIAL, ambiguous_bar=_AMBIG,
    intent=("Commission, spread and half a tick of round-turn slippage, on the close-only "
            "equity path every historical number in this repository used. The comparable "
            "case."))

CONSERVATIVE = ExecutionProfile(
    name="CONSERVATIVE", slippage_ticks=1.0, include_spread=True,
    path_mode=ExecutionPathMode.INTRABAR_CONSERVATIVE,
    stop_execution=_STOP, target_execution=_TARGET, flatten_execution=_FLAT,
    partial_fills=_NO_PARTIAL, ambiguous_bar=_AMBIG,
    intent=("A full tick of round-turn slippage and an equity path that marks every held "
            "bar at the extreme which hurts the position. THE HEADLINE."))

STRESS = ExecutionProfile(
    name="STRESS", slippage_ticks=2.0, include_spread=True,
    path_mode=ExecutionPathMode.STRESS,
    stop_execution=_STOP, target_execution=_TARGET, flatten_execution=_FLAT,
    partial_fills=_NO_PARTIAL, ambiguous_bar=_AMBIG,
    intent=("Two ticks round turn and the most conservative path OHLCV supports: the exit "
            "bar is marked at its worst tick even when a stop fired. A strategy that "
            "survives here is not relying on the cost model."))

#: The ladder, in the order it is always reported. Never reordered by result.
LADDER: tuple[ExecutionProfile, ...] = (IDEAL, BASELINE, CONSERVATIVE, STRESS)

#: The mode the report leads with. Deliberately not IDEAL and deliberately not the best one.
HEADLINE = "CONSERVATIVE"

BY_NAME = {p.name: p for p in LADDER}


def get(name: str) -> ExecutionProfile:
    if name not in BY_NAME:
        raise KeyError(f"unknown execution mode {name!r}; the ladder is "
                       f"{', '.join(BY_NAME)}")
    return BY_NAME[name]


def assumptions_table() -> str:
    """The execution assumption report, as required before any result is believed."""
    lines = ["EXECUTION ASSUMPTIONS - every mode, every field, no omissions", "=" * 92]
    for p in LADDER:
        lines.append(f"\n{p.name}")
        lines.append(f"  intent              {p.intent}")
        lines.append(f"  slippage            {p.slippage_ticks} ticks per round turn")
        lines.append(f"  spread              {'charged' if p.include_spread else 'NOT charged'}")
        lines.append(f"  intrabar path       {p.path_mode.value}")
        lines.append(f"  stop execution      {p.stop_execution}")
        lines.append(f"  target execution    {p.target_execution}")
        lines.append(f"  forced flatten      {p.flatten_execution}")
        lines.append(f"  partial fills       {p.partial_fills}")
        lines.append(f"  ambiguous bar       {p.ambiguous_bar}")
    lines.append("\nNOT MODELLED IN ANY MODE: queue position, market impact, sub-bar "
                 "sequencing beyond the")
    lines.append("adverse assumption, overnight gaps (no position survives the bell).")
    return "\n".join(lines)


__all__ = ["BASELINE", "BY_NAME", "CONSERVATIVE", "HEADLINE", "IDEAL", "LADDER", "STRESS",
           "ExecutionProfile", "assumptions_table", "get"]
