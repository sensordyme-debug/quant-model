"""Deterministic synthetic futures bar datasets: the permanent fixtures A-L.

WHY THESE EXIST
---------------
Every number this repository has published about futures came out of
`data/futures/{ES,MES,NQ,MNQ}.parquet` - 447,600 real bars whose contents nobody can state
in a test. A regression suite built on that store can only ever assert what the store
happens to contain today, and the store is refetched. So the properties that actually
matter - "a roll gap is never earned", "an early close is not a full session", "a round turn
is charged for the flatten" - have no test that can fail for the right reason.

These generators are the other half. Each one is a pure function of its arguments with no
randomness that is not seeded, emitting a frame in EXACTLY the real store's schema and
dtypes (`t,o,h,l,c,v,contract`; `t` tz-aware UTC microsecond, start-stamped), with one
hazard deliberately built in and its magnitude stated as a module constant. A test can then
assert the production code's answer against a number that was decided here, not observed
there.

THE SCHEMA IS PART OF THE FIXTURE
---------------------------------
`schema_reference()` is asserted against a real parquet file when one is present
(`tests/test_golden_futures.py::test_generated_schema_matches_the_real_store`). If the real
store's shape ever changes, that test fails and these generators are wrong - which is the
correct outcome, because a fixture that has drifted from the thing it stands in for is
worse than no fixture.

CONVENTIONS EVERY GENERATOR HOLDS TO
------------------------------------
  * `t` is START-stamped and tz-aware UTC at microsecond resolution, matching the store.
  * RTH is 09:30-15:45 ET inclusive => 376 one-minute bars on a full session.
  * An early close (13:00 ET) is 09:30-12:59 => 210 bars, which is the number that slips
    through a `len(g) > 200` "full session" filter.
  * Prices sit on the 0.25 tick grid. OHLC is always internally consistent unless the
    generator's whole point is that it is not (`impossible_ohlc`).
  * Volume is strictly positive, so a `zero_volume` warning never confuses a test that is
    about something else.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- constants

#: The store's column order, verbatim. Order is asserted, not just membership: a frame with
#: the right columns in the wrong order round-trips through parquet differently.
COLUMNS: tuple[str, ...] = ("t", "o", "h", "l", "c", "v", "contract")

ET = "America/New_York"
UTC = "UTC"
TICK = 0.25

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(15, 45)
#: 09:30 -> 15:45 inclusive, start-stamped, one minute apart.
FULL_SESSION_BARS = 376
#: 09:30 -> 12:59 inclusive: the 13:00 ET early close. 210 > 200, which is the defect.
EARLY_CLOSE_BARS = 210

#: One seed for the whole module. Nothing here is actually stochastic - the jitter below is
#: a deterministic integer pattern - but the seed is fixed so that if a future generator
#: does need noise, there is exactly one place it comes from.
SEED = 20260913

# --- dataset-specific facts, stated here so a test asserts a decided number ---------------

#: B: close rises by exactly one tick per bar over a full session.
B_START = 5000.00
B_TICKS_PER_BAR = 1
#: (376 - 1) bars * 0.25 = 93.75 points from the first close to the last.
B_TOTAL_POINTS = (FULL_SESSION_BARS - 1) * B_TICKS_PER_BAR * TICK

#: C: a symmetric triangle wave. 9 full cycles of 40 bars, plus the closing bar that lands
#: back on the opening value, so the total move is exactly zero and the mean of the 360-bar
#: prefix is exactly the base price.
C_BASE = 5000.00
C_CYCLE = 40
C_CYCLES = 9
C_BARS = C_CYCLE * C_CYCLES + 1          # 361
C_AMPLITUDE_TICKS = 10

#: E: the quoted spread profile. The first 20 bars of the session quote 4 ticks wide, the
#: remaining 100 quote 1 tick.
E_BARS = 120
E_WIDE_BARS = 20
E_WIDE_TICKS = 4
E_NARROW_TICKS = 1
E_MEDIAN_SPREAD_TICKS = 1.0
E_ONE_TICK_SHARE = (E_BARS - E_WIDE_BARS) / E_BARS      # 0.8333...

#: F: the roll. +57.75 points is the real ES September->December stitch measured in the
#: store audit; it is unadjusted, so a strategy that holds across it books money that never
#: existed.
F_GAP_POINTS = 57.75
F_FRONT = "ESM6"
F_BACK = "ESU6"
F_DAY_ONE = dt.date(2026, 6, 5)          # Friday
F_DAY_TWO = dt.date(2026, 6, 8)          # Monday - the roll lands at this session's open
#: Where a mid-session roll lands in the `mid_session=True` variant.
F_MID_SESSION_BAR = 100

#: G: one long ES contract from 5000.00 falling one tick a bar. A $50K Topstep Combine has a
#: $2,000 MLL, so equity touches the limit at 40.00 points = 160 bars, and not before.
G_START = 5000.00
G_BARS = 200
G_MULTIPLIER = 50.0                      # ES
G_BREACH_BAR = 160
G_LOSS_AT_BREACH = G_BREACH_BAR * TICK * G_MULTIPLIER    # $2,000.00

#: H: the look-ahead column. `oracle_next_ret` is literally next bar's return, materialised
#: into the frame. Nothing in production may produce a column that behaves like it.
H_BARS = 200
H_ORACLE_COL = "oracle_next_ret"

#: I: seven bars removed from the middle of a session, leaving an eight-minute hole.
I_FIRST_MISSING_BAR = 100
I_MISSING_BARS = 7
I_HOLE_MINUTES = I_MISSING_BARS + 1

#: J: one bar's timestamp repeated.
J_DUPLICATE_BAR = 50
J_DUPLICATES = 1

#: K: the two US DST transitions the store actually spans.
K_SPRING_FORWARD = dt.date(2026, 3, 8)
K_FALL_BACK = dt.date(2025, 11, 2)
#: `scripts/futures_fetch_multi.py:181` stamps every roll page at this UTC hour, which is
#: 17:00 ET under EDT and 16:00 ET under EST. Neither is the 18:00 ET Globex open.
K_HARDCODED_PAGE_UTC_HOUR = 21
K_GLOBEX_OPEN_ET = dt.time(18, 0)

#: L: the two session lengths the funnel must be able to tell apart.
L_EARLY_CLOSE_DAY = dt.date(2025, 11, 28)      # day after Thanksgiving, 13:00 ET close
L_FULL_DAY = dt.date(2025, 12, 1)

DEFAULT_CONTRACT = "ESZ5"


# --------------------------------------------------------------------------- primitives

def _et_stamps(day: dt.date, bars: int, start: dt.time = RTH_OPEN,
               step_minutes: int = 1) -> pd.DatetimeIndex:
    """Start-stamped minute timestamps for one session, returned as UTC microseconds.

    Built in ET and converted, never the other way round: the session is defined by the
    exchange's wall clock, and a UTC-first construction silently moves the open by an hour
    twice a year. Nothing here spans a DST transition (RTH never does), so localising the
    wall clock is unambiguous; `globex_open_utc` handles the stamps that do.
    """
    first = pd.Timestamp(dt.datetime.combine(day, start), tz=ET)
    idx = pd.date_range(first, periods=bars, freq=f"{step_minutes}min")
    return pd.DatetimeIndex(idx).tz_convert(UTC).as_unit("us")


def _snap(prices) -> np.ndarray:
    """Put a price array on the tick grid, half away from zero."""
    a = np.asarray(prices, dtype=float)
    return np.round(a / TICK) * TICK


def _ohlc_from_close(closes) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Consistent OHLC around a close path: open is the prior close, range spans both.

    Deliberately the tightest bar that can contain the move rather than an invented wick.
    An invented wick is a free parameter, and a fixture with a free parameter in it is a
    fixture whose numbers cannot be recomputed by hand.
    """
    c = _snap(closes)
    o = np.empty_like(c)
    o[0] = c[0]
    o[1:] = c[:-1]
    return o, np.maximum(o, c), np.minimum(o, c), c


def _volume(n: int, base: float = 100.0) -> np.ndarray:
    """Deterministic, strictly positive, and not constant.

    Not constant on purpose: a constant volume makes `rel_volume` degenerate and would let a
    feature bug hide behind a divide-by-its-own-mean of exactly 1.0.
    """
    return base + (np.arange(n) % 7) * 10.0


def frame(stamps, o, h, lo, c, v, contract) -> pd.DataFrame:
    """Assemble the store's exact schema. The single place any generator builds a frame."""
    n = len(stamps)
    contracts = [contract] * n if isinstance(contract, str) else list(contract)
    if len(contracts) != n:
        raise ValueError(f"contract length {len(contracts)} != {n} bars")
    df = pd.DataFrame({
        "t": pd.DatetimeIndex(stamps).as_unit("us"),
        "o": np.asarray(o, dtype=float),
        "h": np.asarray(h, dtype=float),
        "l": np.asarray(lo, dtype=float),
        "c": np.asarray(c, dtype=float),
        "v": np.asarray(v, dtype=float),
        # Inferred from a list of `str`, which is what `read_parquet` produces on both
        # interpreters: `str` dtype under pandas 3.x, `object` under 2.2.3. Forcing either
        # explicitly would make this frame match one interpreter and not the other.
        "contract": contracts,
    })
    return df[list(COLUMNS)]


def schema_reference() -> dict[str, object]:
    """The dtype of every column, taken from a generated frame.

    Returned rather than hard-coded so that the assertion in the test suite is
    generated-vs-real, not generated-vs-a-string-someone-typed. A hard-coded `"str"` would
    pass on pandas 3.x and fail on 2.2.3 for a reason that has nothing to do with the data.
    """
    df = dataset_a_flat()
    return {c: df[c].dtype for c in COLUMNS}


def _session_close(day: dt.date, bars: int) -> dt.time:
    """The ET wall time of the last start-stamped bar of a `bars`-long session."""
    end = dt.datetime.combine(day, RTH_OPEN) + dt.timedelta(minutes=bars - 1)
    return end.time()


# --------------------------------------------------------------------------- A: flat

def dataset_a_flat(day: dt.date = dt.date(2025, 12, 1), price: float = 5000.00,
                   bars: int = FULL_SESSION_BARS,
                   contract: str = DEFAULT_CONTRACT) -> pd.DataFrame:
    """A: a full session at one unchanging price.

    The degenerate case every statistic has to survive: zero variance, zero return, zero
    range. A Sharpe, a z-score and a realised volatility all divide by something that is
    exactly zero here, and a cost model charged against a zero gross edge is where
    `costs / abs(gross)` becomes `inf`. Nothing about this frame is invalid, so no validator
    may FAIL it - but a futures validator SHOULD notice 376 unchanged prints with volume
    behind them, because that is also what a stuck feed looks like.
    """
    c = np.full(bars, price, dtype=float)
    o, h, lo, c = _ohlc_from_close(c)
    return frame(_et_stamps(day, bars), o, h, lo, c, _volume(bars), contract)


# --------------------------------------------------------------------------- B: trend

def dataset_b_linear_trend(day: dt.date = dt.date(2025, 12, 2), start: float = B_START,
                           bars: int = FULL_SESSION_BARS,
                           ticks_per_bar: int = B_TICKS_PER_BAR,
                           contract: str = DEFAULT_CONTRACT) -> pd.DataFrame:
    """B: one tick up per bar, so the total move is a number decided here, not measured.

    `B_TOTAL_POINTS` = 93.75 points from the first close to the last. That is the whole
    point of this fixture: P&L over it is `points x multiplier x contracts` with no rounding
    anywhere, so a contract-arithmetic test can assert to the cent and a wrong multiplier
    cannot hide inside a plausible-looking dollar figure.
    """
    c = start + np.arange(bars) * ticks_per_bar * TICK
    o, h, lo, c = _ohlc_from_close(c)
    return frame(_et_stamps(day, bars), o, h, lo, c, _volume(bars), contract)


def b_total_points(df: pd.DataFrame) -> float:
    """First close to last close, recomputed from the frame rather than trusted."""
    c = df["c"].to_numpy(dtype=float)
    return float(c[-1] - c[0])


# --------------------------------------------------------------------------- C: mean reversion

def _triangle(n: int, cycle: int, amplitude_ticks: int) -> np.ndarray:
    """A symmetric triangle wave in ticks, centred on zero over each full cycle."""
    half = cycle // 2
    k = np.arange(n) % cycle
    up = np.where(k <= half, k, cycle - k).astype(float)      # 0..half..0
    scaled = up * (2.0 * amplitude_ticks / cycle)             # peak = amplitude_ticks
    return scaled - scaled[:cycle].mean()


def dataset_c_mean_reverting(day: dt.date = dt.date(2025, 12, 3), base: float = C_BASE,
                             bars: int = C_BARS, cycle: int = C_CYCLE,
                             amplitude_ticks: int = C_AMPLITUDE_TICKS,
                             contract: str = DEFAULT_CONTRACT) -> pd.DataFrame:
    """C: a deterministic oscillation that ends exactly where it began.

    Nine full 40-bar cycles plus the bar that closes the ninth, so:
        * total move over the frame is exactly 0.00 points,
        * the mean of the 360-bar prefix is exactly `C_BASE`,
        * one-bar returns alternate sign every half cycle, so any momentum rule loses and
          any reversion rule wins - by construction, which is what makes it a fixture and
          not a strategy result.
    A trend-following gate that scores positively on this frame is reading the future.
    """
    c = base + _triangle(bars, cycle, amplitude_ticks) * TICK
    o, h, lo, c = _ohlc_from_close(c)
    return frame(_et_stamps(day, bars), o, h, lo, c, _volume(bars), contract)


# --------------------------------------------------------------------------- D: round turns

#: The position patterns whose true round-turn count is known by construction. "True"
#: includes the forced end-of-session flatten: a futures session ends flat, and the trade
#: that makes it flat costs the same as any other.
D_PATTERNS: dict[str, int] = {
    # Enter long on bar 0, never change, get flattened at the close. One round turn.
    "always_in_long": 1,
    # Long, then flip short at the midpoint, then flattened. Two round turns.
    "flip_once": 2,
    # Long / flat / long / flat / long, then flattened. Three round turns.
    "three_pulses": 3,
    # Never in the market. Zero round turns, and zero is the honest answer here.
    "never_in": 0,
}


def dataset_d_round_turns(pattern: str = "always_in_long",
                          day: dt.date = dt.date(2025, 12, 4),
                          bars: int = FULL_SESSION_BARS,
                          contract: str = DEFAULT_CONTRACT
                          ) -> tuple[pd.DataFrame, np.ndarray, int]:
    """D: a session plus a position path whose true round-turn count is decided here.

    Returns `(frame, positions, true_round_turns)`. The price path is a gentle deterministic
    drift; it is irrelevant to the cost arithmetic and is only there so the frame is a valid
    session. What matters is `positions` and the third element.

    THE ARITHMETIC, WRITTEN OUT
    A round turn is one entry plus one exit. Counting them from a position array means
    counting the contracts traded and halving - and the array must be book-ended by flat at
    BOTH ends, because the session starts flat and ends flat:

        turns = |diff(concat([0], pos, [0]))|.sum() / 2

    `always_in_long` is the case that separates this from the shortcut: pos = [1]*376 gives
    |diff([0,1,...,1,0])|.sum() = 2, so exactly one round turn. Dropping the trailing zero
    gives 1, and `int(1/2) == 0` - the strategy is booked as never having traded.
    """
    if pattern not in D_PATTERNS:
        raise KeyError(f"unknown D pattern {pattern!r}; known: {sorted(D_PATTERNS)}")

    c = 5000.00 + np.arange(bars) * 0.05
    o, h, lo, c = _ohlc_from_close(c)
    df = frame(_et_stamps(day, bars), o, h, lo, c, _volume(bars), contract)

    pos = np.zeros(bars, dtype=float)
    if pattern == "always_in_long":
        pos[:] = 1.0
    elif pattern == "flip_once":
        pos[: bars // 2] = 1.0
        pos[bars // 2:] = -1.0
    elif pattern == "three_pulses":
        block = bars // 5
        for k in (0, 2, 4):
            pos[k * block: (k + 1) * block] = 1.0
        pos[5 * block:] = 0.0
    return df, pos, D_PATTERNS[pattern]


def true_round_turns(pos: np.ndarray) -> int:
    """The correct count: flat before the first bar and flat after the last.

    This is the expectation the cost tests encode. It is deliberately NOT imported from
    production - production is the thing under test - but it is four lines long and every
    term of it is justified in `dataset_d_round_turns`'s docstring.
    """
    p = np.asarray(pos, dtype=float)
    book_ended = np.concatenate(([0.0], p, [0.0]))
    return int(round(float(np.abs(np.diff(book_ended)).sum()) / 2.0))


# --------------------------------------------------------------------------- E: spread

def dataset_e_spread_profile(day: dt.date = dt.date(2025, 12, 5), bars: int = E_BARS,
                             wide_bars: int = E_WIDE_BARS, wide_ticks: int = E_WIDE_TICKS,
                             narrow_ticks: int = E_NARROW_TICKS, base: float = 5000.00,
                             contract: str = DEFAULT_CONTRACT) -> pd.DataFrame:
    """E: a session carrying a quoted book with a spread profile decided in advance.

    Columns beyond the store's schema (`bid`, `ask`, `spread`) are a deliberate SUPERSET:
    the real store has no quotes, `futures_cme.dataquality._check_quotes` says so explicitly,
    and `execution_sim.measure_spread_ticks` exists precisely to replace that assumption once
    a quote store appears. This fixture is the shape that store will have.

    The profile is the real one in miniature - wide at the open, one tick for the rest of the
    session - so the measured median is 1.00 tick and the one-tick share is exactly 0.8333.
    Both are asserted, because a spread measurement that reports the MEAN would read 1.50
    here and would silently overcharge every backtest by 50%.

    Book construction: the last trade prints at the bid, so `bid == c` and `ask == c + k*tick`.
    Both sides stay on the tick grid, which a symmetric `c +/- k*tick/2` would not for odd k.
    """
    c = base + _triangle(bars, 20, 4) * TICK
    o, h, lo, c = _ohlc_from_close(c)
    ticks = np.where(np.arange(bars) < wide_bars, wide_ticks, narrow_ticks).astype(float)
    df = frame(_et_stamps(day, bars), o, h, lo, c, _volume(bars), contract)
    df["bid"] = c
    df["ask"] = c + ticks * TICK
    df["spread"] = ticks * TICK
    return df


# --------------------------------------------------------------------------- F: roll

def dataset_f_roll(*, mid_session: bool = False, gap_points: float = F_GAP_POINTS,
                   base: float = 5000.00) -> tuple[pd.DataFrame, pd.Timestamp]:
    """F: two contracts stitched raw, with the gap and its timestamp both known.

    Returns `(frame, roll_timestamp)`. The stitch carries no marker of any kind, which is
    what the real store does: `contract` changes value and nothing else says a roll happened.
    The back month trades `gap_points` higher, so the bar-to-bar return across the stitch is
    about +1.15% - money that a holder never made and that no price-level check can see.

    `mid_session=False` puts the roll at the open of the second session, which is where three
    of the store's four rolls land.
    `mid_session=True` puts it at bar 100 of the second session, which is where the DECEMBER
    roll lands, because `scripts/futures_fetch_multi.py:181` stamps its page at a hard-coded
    21:00 UTC and that is 16:00 ET rather than 18:00 ET once the clocks go back. A day
    carrying two contracts is not one session, and the funnel's loader must drop it.
    """
    day_one = dataset_b_linear_trend(day=F_DAY_ONE, start=base, contract=F_FRONT)
    last = float(day_one["c"].to_numpy()[-1])

    n = FULL_SESSION_BARS
    stamps_two = _et_stamps(F_DAY_TWO, n)
    if mid_session:
        pre = last + np.arange(F_MID_SESSION_BAR) * TICK
        post = pre[-1] + gap_points + np.arange(n - F_MID_SESSION_BAR) * TICK
        c2 = np.concatenate([pre, post])
        contracts = [F_FRONT] * F_MID_SESSION_BAR + [F_BACK] * (n - F_MID_SESSION_BAR)
        roll_at = pd.Timestamp(stamps_two[F_MID_SESSION_BAR])
    else:
        c2 = last + gap_points + np.arange(n) * TICK
        contracts = [F_BACK] * n
        roll_at = pd.Timestamp(stamps_two[0])

    o2, h2, lo2, c2 = _ohlc_from_close(c2)
    if mid_session:
        # The stitch bar's own open must be the back month's level, not the front month's;
        # otherwise the bar itself carries the gap as a range and h/l hide the jump.
        o2[F_MID_SESSION_BAR] = c2[F_MID_SESSION_BAR]
        h2[F_MID_SESSION_BAR] = c2[F_MID_SESSION_BAR]
        lo2[F_MID_SESSION_BAR] = c2[F_MID_SESSION_BAR]

    day_two = frame(stamps_two, o2, h2, lo2, c2, _volume(n), contracts)
    # Same fix at the session boundary: bar 0's open is its own close, so the gap lives
    # strictly between two bars and only the contract column reveals it.
    out = pd.concat([day_one, day_two], ignore_index=True)
    return out, roll_at


# --------------------------------------------------------------------------- G: drawdown

def dataset_g_drawdown(day: dt.date = dt.date(2025, 12, 8), start: float = G_START,
                       bars: int = G_BARS,
                       contract: str = DEFAULT_CONTRACT) -> tuple[pd.DataFrame, int]:
    """G: a path that reaches a known liquidation level on a known bar.

    Returns `(frame, breach_bar)`. One long ES contract from 5000.00, one tick down a bar:
    unrealised P&L at bar i is exactly `-i * 0.25 * 50 = -12.50 * i` dollars. A $50K Topstep
    Combine's MLL sits $2,000 below the starting balance, so equity touches it at bar 160 and
    at no earlier bar - bar 159 is -$1,987.50, which is $12.50 clear.

    The fixture is built around the boundary deliberately. An off-by-one in a breach test is
    not a rounding difference; `breached()` is `equity <= mll`, and a `<` would let the
    account trade on at exactly the limit.
    """
    c = start - np.arange(bars) * TICK
    o, h, lo, c = _ohlc_from_close(c)
    return frame(_et_stamps(day, bars), o, h, lo, c, _volume(bars), contract), G_BREACH_BAR


def g_unrealized(df: pd.DataFrame, bar: int, multiplier: float = G_MULTIPLIER,
                 contracts: int = 1) -> float:
    """Mark-to-market of a long opened on bar 0, at `bar`."""
    c = df["c"].to_numpy(dtype=float)
    return float((c[bar] - c[0]) * multiplier * contracts)


# --------------------------------------------------------------------------- H: look-ahead

def dataset_h_lookahead(day: dt.date = dt.date(2025, 12, 9), bars: int = H_BARS,
                        base: float = 5000.00,
                        contract: str = DEFAULT_CONTRACT) -> pd.DataFrame:
    """H: a frame with next bar's return materialised into a column.

    `oracle_next_ret[i] = c[i+1]/c[i] - 1`, NaN on the last bar. This is the thing a
    look-ahead detector has to catch, sitting in plain sight so that a test can prove the
    detector catches it rather than assuming it would.

    The price path is adversarial on purpose: 180 quiet bars around the base, then a hard
    20-bar ramp. Any statistic computed over the WHOLE series rather than a trailing window
    has a different value in the quiet stretch depending on whether the ramp exists - so a
    full-sample z-score, a centred rolling window or a session-anchored range that forgot to
    anchor causally all change their early values when the tail is perturbed. On a flat or
    monotone series they would not, and the leak would pass unnoticed.
    """
    quiet = base + _triangle(180, 20, 1) * TICK
    ramp = quiet[-1] + (np.arange(bars - 180) + 1) * 2.00
    c = np.concatenate([quiet, ramp])
    o, h, lo, c = _ohlc_from_close(c)
    df = frame(_et_stamps(day, bars), o, h, lo, c, _volume(bars), contract)
    nxt = np.empty(bars, dtype=float)
    nxt[:-1] = c[1:] / c[:-1] - 1.0
    nxt[-1] = np.nan
    df[H_ORACLE_COL] = nxt
    return df


def oracle_next_return(df: pd.DataFrame) -> np.ndarray:
    """The future return recomputed from `c`. What no production feature may equal."""
    c = df["c"].to_numpy(dtype=float)
    out = np.empty_like(c)
    out[:-1] = c[1:] / c[:-1] - 1.0
    out[-1] = np.nan
    return out


# --------------------------------------------------------------------------- I: missing bars

def dataset_i_missing_bars(day: dt.date = dt.date(2025, 12, 10),
                           first_missing: int = I_FIRST_MISSING_BAR,
                           n_missing: int = I_MISSING_BARS,
                           contract: str = DEFAULT_CONTRACT) -> pd.DataFrame:
    """I: a full session with seven consecutive bars deleted from the middle.

    Leaves one eight-minute hole and 369 rows. Every timestamp present is real and in order,
    every price is valid - the ONLY thing wrong is the absence, which is exactly the failure
    mode Part 17 exists for. AUD-05 was this bug reaching the live book: one dropped bar
    became `prices.get(s, 0.0)`, a $30k position marked at zero, and a flattened book.

    A validator that reports nothing here reports nothing about the one hazard that has
    already cost this repository money.
    """
    df = dataset_b_linear_trend(day=day, contract=contract)
    keep = np.ones(len(df), dtype=bool)
    keep[first_missing: first_missing + n_missing] = False
    return df.loc[keep].reset_index(drop=True)


# --------------------------------------------------------------------------- J: duplicates

def dataset_j_duplicate_timestamps(day: dt.date = dt.date(2025, 12, 11),
                                   at: int = J_DUPLICATE_BAR,
                                   contract: str = DEFAULT_CONTRACT) -> pd.DataFrame:
    """J: one bar repeated, so a timestamp appears twice.

    The duplicate carries a DIFFERENT close, which is the realistic form: a refetch that
    overlapped a page boundary and appended the same minute twice with two different last
    prints. The frame is still monotonically non-decreasing, so an ordering check alone does
    not see it; only an explicit duplicate check does.

    Downstream this is not cosmetic. A groupby-by-day bar count goes up by one, a `.diff()`
    produces a zero-length interval whose return is a divide-by-a-repeat, and any join on
    timestamp fans out.
    """
    df = dataset_b_linear_trend(day=day, contract=contract)
    dupe = df.iloc[[at]].copy()
    dupe["c"] = dupe["c"] + TICK
    dupe["h"] = np.maximum(dupe["h"], dupe["c"])
    out = pd.concat([df.iloc[: at + 1], dupe, df.iloc[at + 1:]], ignore_index=True)
    return out


# --------------------------------------------------------------------------- K: DST

def dataset_k_dst(transition: str = "spring") -> pd.DataFrame:
    """K: the RTH session either side of a DST transition, in one frame.

    `transition` is "spring" (2026-03-08) or "fall" (2025-11-02). The frame holds the last
    regular session before the change and the first one after it, both 09:30-15:45 ET.

    The property under test is that the ET wall clock is IDENTICAL on both days while the
    UTC stamps differ by exactly one hour. Every session filter in this repository is written
    in ET wall time (`futures_discover.OPEN_ET`/`CLOSE_ET` are the strings "09:30"/"15:45"),
    so a pipeline that filters in UTC is wrong for half the year and its results are wrong on
    a set of days nobody enumerates.
    """
    if transition == "spring":
        before, after = dt.date(2026, 3, 6), dt.date(2026, 3, 9)      # Fri EST, Mon EDT
    elif transition == "fall":
        before, after = dt.date(2025, 10, 31), dt.date(2025, 11, 3)   # Fri EDT, Mon EST
    else:
        raise ValueError(f"transition must be 'spring' or 'fall', got {transition!r}")

    parts = []
    price = 5000.00
    for d in (before, after):
        df = dataset_b_linear_trend(day=d, start=price, contract=DEFAULT_CONTRACT)
        price = float(df["c"].to_numpy()[-1]) + TICK
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def globex_open_utc(sunday: dt.date) -> pd.Timestamp:
    """The UTC stamp of the 18:00 ET Globex open on `sunday`.

    23:00 UTC under EST, 22:00 UTC under EDT. `K_HARDCODED_PAGE_UTC_HOUR` is neither, which
    is the whole content of the `futures_fetch_multi.py:181` defect.
    """
    return pd.Timestamp(dt.datetime.combine(sunday, K_GLOBEX_OPEN_ET),
                        tz=ET).tz_convert(UTC).as_unit("us")


def hardcoded_page_stamp_et(day: dt.date) -> dt.time:
    """What the hard-coded 21:00 UTC page stamp actually means in ET on `day`."""
    utc = pd.Timestamp(dt.datetime.combine(day, dt.time(K_HARDCODED_PAGE_UTC_HOUR, 0)),
                       tz=UTC)
    return utc.tz_convert(ET).time()


# --------------------------------------------------------------------------- L: session length

def dataset_l_sessions(contract: str = DEFAULT_CONTRACT) -> pd.DataFrame:
    """L: one 210-bar early close followed by one 376-bar full session.

    2025-11-28 is the day after Thanksgiving; the equity-index complex closes at 13:00 ET, so
    the last start-stamped RTH bar is 12:59 and the session holds 210 bars. 2025-12-01 is a
    regular Monday: 376 bars.

    210 is not a near miss. It is 55.9% of a session, and it clears a `len(g) > 200` filter
    by ten bars - so a funnel that calls that filter "full sessions" is averaging a half day
    in with whole ones, and every per-session statistic it reports is a blend of two
    different things.
    """
    early = dataset_b_linear_trend(day=L_EARLY_CLOSE_DAY, start=5000.00,
                                   bars=EARLY_CLOSE_BARS, contract=contract)
    last = float(early["c"].to_numpy()[-1])
    full = dataset_b_linear_trend(day=L_FULL_DAY, start=last + TICK,
                                  bars=FULL_SESSION_BARS, contract=contract)
    return pd.concat([early, full], ignore_index=True)


def early_close_last_bar_et() -> dt.time:
    """12:59 ET - the last start-stamped bar of a 13:00 close."""
    return _session_close(L_EARLY_CLOSE_DAY, EARLY_CLOSE_BARS)


def full_session_last_bar_et() -> dt.time:
    """15:45 ET - the last start-stamped bar of a regular session."""
    return _session_close(L_FULL_DAY, FULL_SESSION_BARS)


# --------------------------------------------------------------------------- corruptions

def impossible_ohlc(df: pd.DataFrame, at: int = 42) -> pd.DataFrame:
    """Swap high and low on one bar, leaving everything else untouched.

    The corruption is deliberately SMALL - a single bar, a quarter-point inversion - because
    a large one would be caught by a magnitude check for the wrong reason and the test would
    prove nothing about whether the validator understands bar structure. After the swap,
    `h < l` AND `c > h`: two independent impossibilities on one row.
    """
    out = df.copy()
    h = float(out.loc[at, "h"])
    low = float(out.loc[at, "l"])
    if h == low:
        # A flat bar cannot be inverted by swapping; widen it first so the swap bites.
        h, low = low + TICK, low
    out.loc[at, "h"] = low
    out.loc[at, "l"] = h
    return out


def zero_price(df: pd.DataFrame, at: int = 42, column: str = "c") -> pd.DataFrame:
    """Set one price to exactly 0.0 - the value Part 17 forbids treating as a price."""
    out = df.copy()
    out.loc[at, column] = 0.0
    return out


# --------------------------------------------------------------------------- registry

#: Every generator that emits a plain store-schema frame, for the schema/dtype sweep.
#: D, F and G return tuples and E returns a superset, so they are adapted here rather than
#: excluded - a generator left out of this list is a generator whose schema is unchecked.
SCHEMA_CASES: dict[str, object] = {
    "A_flat": lambda: dataset_a_flat(),
    "B_linear_trend": lambda: dataset_b_linear_trend(),
    "C_mean_reverting": lambda: dataset_c_mean_reverting(),
    "D_round_turns": lambda: dataset_d_round_turns()[0],
    "E_spread_profile": lambda: dataset_e_spread_profile()[list(COLUMNS)],
    "F_roll": lambda: dataset_f_roll()[0],
    "F_roll_mid_session": lambda: dataset_f_roll(mid_session=True)[0],
    "G_drawdown": lambda: dataset_g_drawdown()[0],
    "H_lookahead": lambda: dataset_h_lookahead()[list(COLUMNS)],
    "I_missing_bars": lambda: dataset_i_missing_bars(),
    "J_duplicate_timestamps": lambda: dataset_j_duplicate_timestamps(),
    "K_dst_spring": lambda: dataset_k_dst("spring"),
    "K_dst_fall": lambda: dataset_k_dst("fall"),
    "L_sessions": lambda: dataset_l_sessions(),
}

#: The datasets that are CLEAN: no validator may FAIL any of them.
CLEAN_CASES: dict[str, object] = {
    "A_flat": lambda: dataset_a_flat(),
    "B_linear_trend": lambda: dataset_b_linear_trend(),
    "C_mean_reverting": lambda: dataset_c_mean_reverting(),
    "D_round_turns": lambda: dataset_d_round_turns()[0],
    "E_spread_profile": lambda: dataset_e_spread_profile(),
}
