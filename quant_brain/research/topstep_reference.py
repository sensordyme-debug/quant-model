"""An independent reference for the Topstep account path, written to disagree.

WHY A SECOND IMPLEMENTATION
---------------------------
`twin.TopstepTwin` is the least-verified component in the engine and the one whose output
is the mission's objective function: pass probability, payout count, and the buffer that
decides whether a strategy is fundable at all. Everything downstream of it inherits its
errors, and a unit test written by whoever wrote the simulator tends to encode the same
misreading twice - once in the code and once in the assertion.

So this module answers the same question a second time from the rulebook, and is built to
be STRUCTURALLY UNLIKE the production path so that a shared mistake has nowhere to hide:

    production                              this reference
    ----------                              --------------
    a mutable `TopstepAccount` whose         a pure function over an explicit list of
    limits are computed by @property         (level, kind) liquidation levels recomputed
    lookups at the moment they are read      from scratch at the top of every session
    a state machine (`advance()`) that       no state machine; the phase is a local
    moves one step per call                  variable and the transition is a rebuild
    the floor derived through                the floor written out as the two-line
    `PropFirmProfile.floor_for`              min() the rulebook states
    breach discovered by a `breached()`      breach discovered by comparing every mark
    predicate on an equity attribute         against a level fixed before the day starts

The two share no functions. They share the RULEBOOK - the constants in `topstep.py`, which
carry their citations - and nothing else. Constants are read from there on purpose: this is
a check on the ARITHMETIC and the SEQUENCING, not a second guess at what Topstep published.
Duplicating the numbers here would mean a rulebook correction silently stopped being tested.

WHAT IT DOES NOT DO
-------------------
It is not a fallback and it must never become one. It models the 50K Combine to Express
Funded path with the optional daily loss limit, one payout policy shape, and the documented
consistency reading. Anything outside that - scaling ladders, the Live Funded Account, the
consistency payout route, alternative readings - is refused rather than approximated, because
a reference that quietly guesses is worse than no reference at all.
"""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme.twin import TwinDay

#: The one account size this reference is written for. Everything below is arithmetic on
#: the 50K row of the published tables; a different size would need its own reading.
SIZE = 50_000


@dataclass(frozen=True)
class Level:
    """A price level the account dies at, or is flattened at, if equity reaches it.

    Named rather than inlined because WHICH of the two fired is the whole content of the
    daily-loss-limit rule: hitting the DLL ends the session, hitting the MLL ends the
    account, and on a coarse mark both can be below the equity at once.
    """

    kind: str          # "mll" or "dll"
    level: float


@dataclass
class Event:
    """One line of the transcript. The reconciliation compares these, not just the ending."""

    day: dt.date
    phase: str         # "combine" | "xfa"
    what: str          # "survived" | "dll_capped" | "breach_intraday" | "breach_eod"
                       # | "passed_combine" | "payout" | "payout_refused" | "restart_combine"
    balance: float
    floor: float
    detail: float = 0.0
    #: The limit the session was traded UNDER, fixed before its first mark. `floor` is the
    #: level after settlement; these differ on any session that moved the peak, and
    #: comparing one against the other is comparing two different instants.
    floor_at_open: float = 0.0


@dataclass
class ReferenceResult:
    """The reference's verdict, in the same vocabulary the twin reports."""

    terminal: str                      # "trading_combine" | "express_funded"
                                       # | "payout_eligible" | "liquidated"
    days: int = 0
    combine_attempts: int = 1
    combine_days: int | None = None
    reached_funding: bool = False
    breach_day: dt.date | None = None
    breach_kind: str = ""              # "intraday" | "eod" | "dll_at_the_floor" | ""
    final_balance: float = 0.0
    payouts: list[tuple[dt.date, float]] = field(default_factory=list)
    total_paid: float = 0.0
    min_buffer: float = 0.0
    min_buffer_funded: float = 0.0
    events: list[Event] = field(default_factory=list)
    #: The cross-check surface. Named separately from the transcript because a mismatch on
    #: one of these is a decision disagreement, whereas a transcript difference may only be
    #: a difference in how the same outcome was narrated.
    starting_balance: float = float(SIZE)
    peak_balance: float = float(SIZE)
    ending_mll: float = 0.0
    ending_dll: float | None = None
    target_reached: bool = False
    forced_flat_sessions: int = 0
    final_position: float = 0.0          # every session ends flat; recorded, not assumed


def _combine_floor(peak_eod: float) -> float:
    """8284204: the limit trails the end-of-day balance and stops at the starting balance."""
    return min(peak_eod - ts.MLL[SIZE].value, float(SIZE))


def _xfa_floor(peak_eod: float, pinned: bool) -> float:
    """Same trail, locking at $0 - and pinned there permanently by any payout (8284233)."""
    if pinned:
        return 0.0
    return min(peak_eod - ts.MLL[SIZE].value, 0.0)


def _effective_target(best_day: float, total_profit: float) -> float:
    """8284208 under the documented calculation: the target rises until the best day complies.

    Written as the inequality the page states rather than as the production property, so a
    sign or a boundary flipped in one place does not flip in both.
    """
    base = ts.COMBINE_PROFIT_TARGET[SIZE].value
    limit = ts.CONSISTENCY_READINGS[ts.DEFAULT_READING][0]
    if total_profit <= 0:
        return base
    if best_day <= limit * total_profit:
        return base
    return max(base, best_day / limit)


def run_reference(sessions: Sequence[TwinDay], *,
                  daily_loss_limit: float | None = None,
                  max_combine_attempts: int = 1,
                  payout_fraction: float = 0.0,
                  min_buffer_after: float = 0.0) -> ReferenceResult:
    """Replay one strategy's sessions through the 50K path and return a full transcript.

    `payout_fraction` is the share of the eligible cap withdrawn at the first opportunity;
    0.0 never withdraws. This is deliberately the only policy shape supported - the twin's
    `PayoutPolicy` also carries `wait_days` and `stop_after`, and reproducing every knob
    here would make the reference a copy rather than a check.
    """
    if any(not d.path for d in sessions):
        raise ValueError("every session must carry an intraday path; the reference will "
                         "not run the breach test against a close-only day")

    res = ReferenceResult(terminal="trading_combine")
    phase = "combine"
    alive = True
    balance = float(SIZE)
    peak_eod = float(SIZE)
    pinned = False
    daily: list[float] = []
    winning = 0
    started_at = 0                       # index the current Combine attempt began on
    balance_at_last_payout: float | None = None
    res.min_buffer = balance - _combine_floor(peak_eod)
    funded_buffers: list[float] = []

    def floor_now() -> float:
        return _combine_floor(peak_eod) if phase == "combine" else _xfa_floor(peak_eod, pinned)

    for i, day in enumerate(sessions):
        res.days = i + 1
        floor = floor_now()
        # BOTH levels are fixed before the first mark. The MLL cannot move intraday because
        # it only follows the end-of-day balance, and the DLL is measured from the balance
        # the day opened at - so neither is recomputed inside the loop, which is the point.
        dll_level = (balance - daily_loss_limit) if daily_loss_limit is not None else -math.inf
        levels = (Level("mll", floor), Level("dll", dll_level))

        outcome = "survived"
        for mark in day.path:
            equity = balance + mark
            reached = [lv for lv in levels if equity <= lv.level]
            if not reached:
                continue
            # Equity fell through the HIGHER level first. On a coarse mark both can be
            # below at once, and the order the code tests them in must not decide which
            # rule fired - the levels' own ordering does.
            fired = max(reached, key=lambda lv: lv.level)
            outcome = "breach_intraday" if fired.kind == "mll" else "dll_capped"
            break

        breached_kind = ""
        if outcome == "breach_intraday":
            res.events.append(Event(day.day, phase, outcome, balance, floor,
                                    floor_at_open=floor))
            breached_kind = "intraday"
        else:
            booked = (-daily_loss_limit if outcome == "dll_capped"      # type: ignore[operator]
                      else (day.pnl if daily_loss_limit is None
                            else max(day.pnl, -daily_loss_limit)))
            balance += booked
            daily.append(booked)
            if booked >= ts.XFA_WINNING_DAY_MIN.value:
                winning += 1
            if balance <= floor:
                # The close is tested against the SAME level the marks were: the limit
                # advances after settlement, never before it.
                res.events.append(Event(day.day, phase, "breach_eod", balance, floor,
                                        booked, floor_at_open=floor))
                breached_kind = "dll_at_the_floor" if outcome == "dll_capped" else "eod"

        if breached_kind:
            res.breach_day, res.breach_kind = day.day, breached_kind
            if phase == "xfa" or res.combine_attempts >= max_combine_attempts:
                alive = False
                break
            # Another Combine is a NEW account. Nothing survives the liquidation.
            res.combine_attempts += 1
            res.events.append(Event(day.day, "combine", "restart_combine", float(SIZE),
                                    _combine_floor(float(SIZE))))
            phase, balance, peak_eod, pinned = "combine", float(SIZE), float(SIZE), False
            daily, winning, balance_at_last_payout = [], 0, None
            started_at = i + 1
            res.min_buffer = min(res.min_buffer, balance - _combine_floor(peak_eod))
            continue

        floor_at_open = floor
        peak_eod = max(peak_eod, balance)                  # the ONE place the limit advances
        floor = floor_now()
        res.min_buffer = min(res.min_buffer, balance - floor)
        if phase == "xfa":
            funded_buffers.append(balance - floor)
        res.events.append(Event(day.day, phase, outcome, balance, floor, booked,
                                floor_at_open=floor_at_open))

        if phase == "combine":
            profit = balance - SIZE
            target = _effective_target(max(daily, default=0.0), profit)
            if profit >= target:
                res.events.append(Event(day.day, phase, "passed_combine", balance, floor,
                                        target))
                if res.combine_days is None:
                    res.combine_days = i + 1 - started_at
                res.reached_funding = True
                # The XFA is a NEW account: $0, the same $2,000 of room, nothing carried.
                phase = "xfa"
                balance, peak_eod, pinned = 0.0, 0.0, False
                daily, winning, balance_at_last_payout = [], 0, None
                funded_buffers.append(balance - _xfa_floor(peak_eod, pinned))
            continue

        # -- funded: eligibility and the withdrawal ----------------------------------------
        base = 0.0 if balance_at_last_payout is None else balance_at_last_payout
        eligible = (balance - base) > 0 and winning >= ts.XFA_WINNING_DAYS.value
        if not eligible:
            res.terminal = "express_funded"
            continue
        res.terminal = "payout_eligible"
        cap = max(0.0, min(balance * ts.XFA_BALANCE_SHARE.value,
                           ts.XFA_STANDARD_CAP_BY_SIZE[SIZE].value))
        room = (balance - _xfa_floor(peak_eod, pinned)) - min_buffer_after
        amount = max(0.0, min(cap * payout_fraction, room))
        if min(amount, cap) < ts.PAYOUT_MINIMUM.value:
            # Refused outright. Nothing moves: not the balance, not the counts, and above
            # all not the limit, which a recorded payout would pin at $0 forever.
            res.events.append(Event(day.day, phase, "payout_refused", balance,
                                    _xfa_floor(peak_eod, pinned), amount))
            continue
        paid = min(amount, cap)
        balance -= paid
        pinned = True
        daily, winning = [], 0
        balance_at_last_payout = balance
        res.payouts.append((day.day, paid))
        res.total_paid += paid
        res.terminal = "express_funded"
        funded_buffers.append(balance - _xfa_floor(peak_eod, pinned))
        res.events.append(Event(day.day, phase, "payout", balance,
                                _xfa_floor(peak_eod, pinned), paid))

    if not alive:
        res.terminal = "liquidated"
    elif phase == "combine":
        res.terminal = "trading_combine"
    elif res.terminal != "payout_eligible":
        # Funded and still alive. Reached here when the Combine was passed on the very last
        # session, so the funded branch never ran and never named the stage.
        res.terminal = "express_funded"
    res.final_balance = balance
    res.min_buffer_funded = min(funded_buffers) if funded_buffers else 0.0
    res.peak_balance = peak_eod
    res.ending_mll = floor_now()
    res.ending_dll = (balance - daily_loss_limit) if daily_loss_limit is not None else None
    res.target_reached = res.reached_funding
    res.forced_flat_sessions = sum(1 for d in sessions if not d.traded)
    return res
