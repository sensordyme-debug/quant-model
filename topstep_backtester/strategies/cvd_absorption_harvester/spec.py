"""CVD_ABSORPTION_HARVESTER / XFA_V2.0 — the owner's specification, as received.

No parameter here may be changed. This module is the authority; the rest of the package
implements it.

THE AMBIGUITY REGISTER IS THE POINT OF THIS FILE
------------------------------------------------
PART 39 of the brief lists fifteen places the written rules might admit more than one
reading, and instructs: resolve an item only where the upstream engine has a documented
deterministic behaviour that exactly corresponds to the specification, and otherwise stop
and ask. That is what the register below does, item by item, with the upstream source line
cited wherever a reading is taken.

Six items resolve - four against upstream's documented execution model, two against the
brief's own text. Eleven do not, and are recorded with ``resolved=False``. A spec with
unresolved ambiguities CANNOT be frozen - ``FrozenStrategySpec.freeze`` refuses it - and
therefore cannot run. That is deliberate: deciding these readings after seeing results is choosing
the reading that won.

ONE RESOLUTION WORTH READING BEFORE THE OTHERS
----------------------------------------------
A15. The zero-buffer killswitch cannot fire at exactly -$250 in this engine. Upstream
computes candidate fills against the order book as it stood at the start of the bar, and an
order created during a bar is stamped to the next one
(``execution/sim_broker.py``: "children created on an intrabar fill carry accepted_ts stamps
that defer them to the next bar"). So the emergency flatten is submitted on the record that
breached and fills on the record after it. At tick resolution that is one trade of drift; on
minute bars it would be a whole minute. The killswitch is therefore a soft floor, not a hard
one, and the realised loss on a killswitch exit will generally exceed $250. This is a
property of any bar-sequenced simulator and is reported rather than papered over.
"""
from __future__ import annotations

from decimal import Decimal

from topstep_backtester.strategies.spec import Ambiguity, FrozenStrategySpec

# ======================================================================================
# THE FROZEN PARAMETERS. PART 38 forbids changing any of these.
# ======================================================================================

INSTRUMENT = "ES"
CONTRACTS = 1

#: ES contract terms, restated so the arithmetic in this package is derivable without the
#: engine. A test asserts they equal upstream's SPECS["ES"].
TICK_SIZE = Decimal("0.25")
TICK_VALUE = Decimal("12.50")
POINT_VALUE = Decimal("50.00")

#: Venue clock. DST-aware; never a fixed offset.
TIMEZONE = "America/New_York"

#: CVD accumulation begins here, every trading day, from zero.
CVD_RESET_ET = "09:30:00"

#: Entry window. Whether the closing boundary itself is eligible is AMBIGUITY A1.
ENTRY_WINDOW_OPEN_ET = "09:45:00"
ENTRY_WINDOW_CLOSE_ET = "11:30:00"

#: Signal chart. CVD is sampled at the exact close of each completed bar.
BAR_INTERVAL = "1min"

#: Completed bars examined for the price extreme. Bar T itself is excluded.
LOOKBACK_BARS = 15

#: Bracket, in ticks from the ACTUAL fill price.
STOP_TICKS = 8
TARGET_TICKS = 16

#: Break-even management.
BE_TRIGGER_TICKS = 8
BE_STOP_OFFSET_TICKS = 1

#: Strategy governor thresholds. These are the STRATEGY's own rules and are not the same
#: thing as the Topstep account rules - see PART 27 and the report.
WINNING_DAY_LOCK_USD = Decimal("160")
KILLSWITCH_USD = Decimal("-250")
GOVERNOR_UNLOCK_ET = "17:00:00"

#: Declared execution costs.
COMMISSION_ROUND_TURN_USD = Decimal("4.14")
ENTRY_SLIPPAGE_TICKS = 1
STOP_SLIPPAGE_TICKS = 1
#: Not specified by the owner. Upstream never charges a limit order slippage - see A13.
TARGET_SLIPPAGE_TICKS = 0

# ======================================================================================
# THE AMBIGUITY REGISTER - PART 39, all fifteen items
# ======================================================================================

AMBIGUITIES: tuple[Ambiguity, ...] = (
    Ambiguity(
        ref="A1",
        question=(
            "Is a bar completing at exactly 11:30:00 ET eligible for entry, or is the "
            "window half-open at [09:45:00, 11:30:00)?"
        ),
        reading_taken="",
        authority="",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A2",
        question=(
            "Which quote is the 'prevailing' bid/ask for a trade: the last quote strictly "
            "BEFORE the trade, or the last quote at-or-before it? On a locked or fast market "
            "the two differ and the classification flips with them."
        ),
        reading_taken="",
        authority="",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A3",
        question=(
            "When bid == ask (a locked market), a trade at that price satisfies PART 7 CASE 1 "
            "(at ask, +volume) and CASE 2 (at bid, -volume) simultaneously. Which wins?"
        ),
        reading_taken="",
        authority="",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A4",
        question=(
            "Are the three PART 7 cases an ORDERED cascade (so CASE 1 is tested first and a "
            "price equal to both bid and ask classifies as +volume) or an unordered set of "
            "mutually exclusive conditions?"
        ),
        reading_taken="",
        authority="",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A5",
        question=(
            "PART 7 specifies that a trade with a missing bid or ask is recorded UNCLASSIFIABLE "
            "rather than guessed. What it does NOT specify is the data-quality policy: how many "
            "unclassifiable ticks a session may contain before the session is rejected."
        ),
        reading_taken=(
            "the recording half IS specified and is implemented: an unclassifiable tick "
            "contributes zero delta, is counted, and never receives an invented sign. The "
            "THRESHOLD is not specified and no default is invented."
        ),
        authority="PART 7 (explicit); the threshold has no source",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A6",
        question=(
            "A midpoint trade whose price equals the previous trade price takes 'delta = "
            "previous_delta'. At the 09:30:00 CVD reset there is no previous delta. What is "
            "the delta of that first trade?"
        ),
        reading_taken="",
        authority="",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A7",
        question=(
            "Which is the first 1-minute bar that may establish swing memory? CVD resets at "
            "09:30 and 15 completed bars exist by 09:45, so swing memory could legitimately be "
            "seeded from the 09:30-09:45 bars (first eligible entry 09:45) or only begin "
            "accumulating at 09:45 (first eligible entry 10:00)."
        ),
        reading_taken="",
        authority="",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A8",
        question="Can a long and a short signal fire on the same 1-minute bar?",
        reading_taken=(
            "NO - impossible by construction. PART 12 condition 4 requires Close[T] > Open[T] "
            "and PART 13 condition 4 requires Close[T] < Open[T]. No bar satisfies both, so "
            "the two signal sets are mutually exclusive and no tie-break rule is needed."
        ),
        authority="the specification's own rules, PART 12.4 and PART 13.4",
        material=False,
        resolved=True,
    ),
    Ambiguity(
        ref="A9",
        question=(
            "May more than one position be open at once? PART 3 states a position size of 1 ES "
            "contract, which reads as a cap, but the specification never says what happens to a "
            "fresh signal while a position is already open - ignore it, or add to the position?"
        ),
        reading_taken="",
        authority="",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A10",
        question=(
            "After a trade closes, is the strategy immediately re-armed, or is the day finished?"
        ),
        reading_taken="",
        authority="",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A11",
        question=(
            "If the strategy is re-armed after a close, may the very next completed bar produce "
            "an entry, or is there a cooling-off period? Relatedly, does the swing memory that "
            "produced the closed trade persist or reset?"
        ),
        reading_taken="",
        authority="",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A12",
        question="What exactly does a market order fill at?",
        reading_taken=(
            "the OPEN of the record AFTER the one that produced the signal, slipped one tick "
            "adverse. PART 14 directs us to the upstream execution model, and that model is "
            "explicit: a market order is accepted at the signal record's close, becomes active "
            "on the next record, and fills at that record's open moved adverse by "
            "market_slippage_ticks. The fill is therefore NEVER the signal bar's close."
        ),
        authority=(
            "PART 14 (defers to the engine) + upstream fills/bar_fill.py::_market "
            "('MARKET: fill at the open, slipped ADVERSE') and execution/sim_broker.py:491"
        ),
        material=True,
        resolved=True,
    ),
    Ambiguity(
        ref="A13",
        question="Is the profit target charged slippage?",
        reading_taken=(
            "NO. The target is a resting limit and upstream never charges a limit order "
            "slippage; with fill_limit_on_touch=False it additionally requires the market to "
            "trade THROUGH the price rather than merely touch it, which is the conservative "
            "reading. PART 6 forbids inventing a target slippage, so none is applied and the "
            "assumption is reported."
        ),
        authority=(
            "PART 6 (forbids invention) + upstream fills/bar_fill.py::_limit and the "
            "BarFillConfig.fill_limit_on_touch default of False"
        ),
        material=True,
        resolved=True,
    ),
    Ambiguity(
        ref="A14",
        question="What does 'locked until 17:00:00 ET' mean in engine terms?",
        reading_taken=(
            "locked for the remainder of the current trading day. 17:00 ET is the close of the "
            "Globex trading day upstream already enforces (18:00 ET -> 17:00 ET, with a "
            "17:00-18:00 maintenance halt), so a lock to 17:00 and a lock to the day roll are "
            "the same instant. The next session begins at 18:00 ET as a new trading day with a "
            "fresh governor. Immaterial in practice: the entry window is 09:45-11:30 ET, so a "
            "lock can never reach into the next session's window anyway."
        ),
        authority=(
            "upstream core/time.py trading_day_of and the TOPSTEP_SESSION 18:00-17:00 ET "
            "boundary the kernel and validator both enforce"
        ),
        material=False,
        resolved=True,
    ),
    Ambiguity(
        ref="A15",
        question=(
            "What happens when the governor triggers on the same record as an entry or exit "
            "event? Can the emergency flatten fill at the breaching price?"
        ),
        reading_taken=(
            "NO. The flatten is a market order submitted on the breaching record and filling "
            "on the record AFTER it, because upstream computes candidate fills against the "
            "bar-start order book and defers orders created during a bar to the next one. The "
            "-$250 killswitch is therefore a SOFT floor: the realised loss on a killswitch "
            "exit will generally exceed $250, by one record's price movement plus stop "
            "slippage. Reported, not corrected - it is a property of any bar-sequenced "
            "simulator, and pretending otherwise would understate the strategy's worst case."
        ),
        authority=(
            "upstream execution/sim_broker.py:491 and :943 (accepted_ts defers to the next bar)"
        ),
        material=True,
        resolved=True,
    ),
    # ---- beyond PART 39's list. It says "identify ANY unresolved ambiguity" and then
    # ---- names fifteen to verify specifically; these two surfaced while implementing.
    Ambiguity(
        ref="A16",
        question=(
            "A minute in which no trade prints produces no 1-minute bar. Is the PART 10 "
            "lookback therefore the last 15 BARS THAT TRADED, or the last 15 CLOCK MINUTES "
            "with the empty ones treated as missing? The two windows differ whenever the "
            "session has a quiet minute, and they reference different prices."
        ),
        reading_taken="",
        authority="",
        material=True,
        resolved=False,
    ),
    Ambiguity(
        ref="A17",
        question=(
            "How is a print with zero or negative volume classified? It would contribute a "
            "delta of zero whatever sign it received."
        ),
        reading_taken=(
            "as bad data, not as a trade: recorded UNCLASSIFIABLE, counted in the "
            "data-quality report, contributing zero and never advancing the previous-delta "
            "state. PART 22 lists zero and negative volume as validation items, and PART 7 "
            "forbids silently classifying a tick whose classification is not determined, so "
            "this is the only reading that invents nothing."
        ),
        authority="PART 22 (validation list) + PART 7 (no silent classification)",
        material=False,
        resolved=True,
    ),
)


def _rules() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    entry = (
        f"CVD resets to 0 at {CVD_RESET_ET} ET each trading day; delta is assigned per TRADE "
        f"by PART 7 (at ask +size, at bid -size, inside/midpoint by the previous trade price, "
        f"zero-tick inherits the previous delta)",
        f"signals are evaluated only at the close of a COMPLETED {BAR_INTERVAL} bar, with CVD "
        f"sampled at that exact close",
        f"LONG at close of bar T when all four hold: Low[T] <= min(Low[T-{LOOKBACK_BARS}] .. "
        f"Low[T-1]); Low[T] < Prev_Low_Price; CVD[T] > Prev_Low_CVD; Close[T] > Open[T]",
        f"SHORT at close of bar T when all four hold: High[T] >= max(High[T-{LOOKBACK_BARS}] .. "
        f"High[T-1]); High[T] > Prev_High_Price; CVD[T] < Prev_High_CVD; Close[T] < Open[T]",
        f"entries are accepted only within {ENTRY_WINDOW_OPEN_ET}-{ENTRY_WINDOW_CLOSE_ET} ET "
        f"(closing boundary semantics unresolved, AMBIGUITY A1)",
        f"order is a market order for {CONTRACTS} {INSTRUMENT} contract; no additional filter "
        f"may be added",
    )
    exit_rules = (
        f"OCO bracket anchored to the ACTUAL fill price: stop {STOP_TICKS} ticks, target "
        f"{TARGET_TICKS} ticks",
        f"break-even: once unrealized MFE reaches {BE_TRIGGER_TICKS} ticks, the stop moves to "
        f"fill price +/- {BE_STOP_OFFSET_TICKS} tick in the direction of the trade",
        "the target is a resting limit and is charged no slippage (AMBIGUITY A13)",
    )
    risk = (
        f"strategy winning-day lock: realized daily P&L >= +${WINNING_DAY_LOCK_USD} cancels "
        f"working orders, blocks new setups and holds HALTED_SUCCESS until "
        f"{GOVERNOR_UNLOCK_ET} ET",
        f"strategy killswitch: realized + unrealized <= ${KILLSWITCH_USD} flattens, cancels "
        f"and holds HALTED_FAIL until {GOVERNOR_UNLOCK_ET} ET (soft floor, AMBIGUITY A15)",
        f"{CONTRACTS} contract maximum; concurrency and re-arm behaviour unresolved "
        f"(AMBIGUITIES A9, A10, A11)",
    )
    return entry, exit_rules, risk


_entry, _exit, _risk = _rules()

#: THE SPECIFICATION. Constructed, hashed, and deliberately NOT frozen: eleven ambiguities are
#: unresolved, and freeze() refuses a spec that cannot say which reading it took.
SPEC = FrozenStrategySpec(
    name="CVD_ABSORPTION_HARVESTER",
    version="XFA_V2.0",
    instrument=INSTRUMENT,
    bar_interval=BAR_INTERVAL,
    session_window=f"{ENTRY_WINDOW_OPEN_ET}-{ENTRY_WINDOW_CLOSE_ET} ET",
    entry_rules=_entry,
    exit_rules=_exit,
    risk_rules=_risk,
    parameters={
        "contracts": CONTRACTS,
        "lookback_bars": LOOKBACK_BARS,
        "stop_ticks": STOP_TICKS,
        "target_ticks": TARGET_TICKS,
        "be_trigger_ticks": BE_TRIGGER_TICKS,
        "be_stop_offset_ticks": BE_STOP_OFFSET_TICKS,
        "winning_day_lock_usd": str(WINNING_DAY_LOCK_USD),
        "killswitch_usd": str(KILLSWITCH_USD),
        "governor_unlock_et": GOVERNOR_UNLOCK_ET,
        "cvd_reset_et": CVD_RESET_ET,
        "entry_window_open_et": ENTRY_WINDOW_OPEN_ET,
        "entry_window_close_et": ENTRY_WINDOW_CLOSE_ET,
        "commission_round_turn_usd": str(COMMISSION_ROUND_TURN_USD),
        "entry_slippage_ticks": ENTRY_SLIPPAGE_TICKS,
        "stop_slippage_ticks": STOP_SLIPPAGE_TICKS,
        "target_slippage_ticks": TARGET_SLIPPAGE_TICKS,
        "timezone": TIMEZONE,
    },
    ambiguities=AMBIGUITIES,
    hypothesis=(
        "A price extreme that penetrates a prior swing while cumulative volume delta refuses "
        "to confirm it indicates absorption of the aggressive flow, and the subsequent "
        "rejection print marks a reversion worth harvesting at a 2:1 reward-to-risk."
    ),
    notes=(
        "Requires genuine tick-level trade-and-quote data. CVD may not be approximated from "
        "OHLCV under any circumstances (PART 2).",
        "The +$160 and -$250 thresholds are STRATEGY governor rules and are not Topstep "
        "account rules; the two are reported separately (PART 27, PART 30).",
    ),
)


def unresolved_refs() -> tuple[str, ...]:
    return tuple(a.ref for a in SPEC.unresolved())


def register_summary() -> str:
    lines = ["| ref | material | status | question |", "|---|---|---|---|"]
    for item in AMBIGUITIES:
        status = "RESOLVED" if item.resolved else "**OWNER INPUT REQUIRED**"
        lines.append(
            f"| {item.ref} | {'yes' if item.material else 'no'} | {status} | {item.question} |"
        )
    return "\n".join(lines)


__all__ = [
    "AMBIGUITIES",
    "BAR_INTERVAL",
    "BE_STOP_OFFSET_TICKS",
    "BE_TRIGGER_TICKS",
    "COMMISSION_ROUND_TURN_USD",
    "CONTRACTS",
    "CVD_RESET_ET",
    "ENTRY_SLIPPAGE_TICKS",
    "ENTRY_WINDOW_CLOSE_ET",
    "ENTRY_WINDOW_OPEN_ET",
    "GOVERNOR_UNLOCK_ET",
    "INSTRUMENT",
    "KILLSWITCH_USD",
    "LOOKBACK_BARS",
    "POINT_VALUE",
    "SPEC",
    "STOP_SLIPPAGE_TICKS",
    "STOP_TICKS",
    "TARGET_SLIPPAGE_TICKS",
    "TARGET_TICKS",
    "TICK_SIZE",
    "TICK_VALUE",
    "TIMEZONE",
    "WINNING_DAY_LOCK_USD",
    "register_summary",
    "unresolved_refs",
]
