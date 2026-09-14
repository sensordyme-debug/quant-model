"""Futures-specific data validation: the hazards a generic OHLCV check cannot see.

`quant_brain.core.dataquality` already refuses zero, NaN and negative prices, impossible
bars, duplicate or unsorted indices, tz-naive timestamps and bars on a holiday. All of that
applies here. None of it is about futures.

WHAT IS DIFFERENT ABOUT A FUTURES STORE
-----------------------------------------
A futures series is not one instrument. It is a sequence of contracts stitched together, and
every hazard below comes from that fact:

    ROLL GAP        the price jumps at the roll because the new contract trades at a
                    different level. A strategy that holds across it books a P&L that never
                    existed. This is the single most common way a futures backtest invents
                    money, and it is invisible to every price-level check.
    OVERLAP         two contracts quoting on the same date. Whichever one a naive groupby
                    picks is arbitrary, and the choice changes the answer.
    BACKWARDS ROLL  contracts out of chronological order, or a series that revisits an
                    expired contract after moving on.
    STALE QUOTE     a bar repeated unchanged for long enough that it is a feed artefact
                    rather than a quiet market.
    CROSSED BOOK    bid above ask. Impossible, and it appears in real vendor data.

Part 6 asks for exactly this list. The checks are severity-graded rather than all fatal,
because a roll gap is normal and expected - what is NOT acceptable is a roll gap nobody
knows about, so the default is to report every one and fail only on the things that cannot
be true.

AND THE THREE GENERIC HAZARDS THAT WERE MISSING ANYWAY
-------------------------------------------------------
The paragraph above assumed `core.dataquality` was also running. On the futures path it is
not: `futures_discover.load` calls `require_usable` from THIS module and nothing else, so
until `tests/test_golden_futures.py` pinned it, three hazards the core validator has always
caught had no gate at all here:

    SESSION GAP     bars missing from the middle of a session. Golden dataset I deletes
                    seven and the store passed. Every rolling feature and every per-session
                    statistic is computed inside a session, so a hole silently changes all
                    of them - and AUD-05 is what a hole costs once it reaches a live book.
    DUPLICATE BAR   the same minute twice. `is_monotonic_increasing` is evaluated
                    NON-strictly by pandas, so a repeat is "in order"; `_check_overlap` sees
                    it only when the two rows carry different contracts. A refetch that
                    overlapped a page boundary is the common case and it carries the SAME
                    contract, so it was invisible.
    IMPOSSIBLE BAR  high below low, or a close outside its own range. This module read `c`,
                    `v` and the quote columns and never `h`/`l`.

These are FAILs, not WARNs. A roll gap is a fact about futures that a strategy can be
written around; a hole, a repeat and an impossible bar are all statements that the store
does not say what happened, and Part 18's rule is that an unknown state is not a licence to
proceed.
"""
from __future__ import annotations

from quant_brain.core.calendar import SessionCalendar
from quant_brain.core.dataquality import Report, Severity, check_bar_structure

#: A same-contract move this large between consecutive bars is a data error rather than a
#: market move. ES has had 7% limit-down days; 20% inside one minute has not happened and
#: would be halted long before.
IMPOSSIBLE_RETURN = 0.20

#: Consecutive identical bars beyond this count are a feed artefact. Overnight CME sessions
#: genuinely go quiet, so this is deliberately loose - it is looking for a stuck feed, not
#: for a thin hour.
STALE_BARS = 120

#: The exchange clock the session boundary is expressed in. CME equity index is a Chicago
#: product quoted here in ET because every session filter in this repository is ET
#: (`futures_discover.OPEN_ET`/`CLOSE_ET`).
_ET = "America/New_York"

#: CME's trade date rolls at 17:00 CT = 18:00 ET: the Sunday 18:00 open belongs to Monday.
#: Adding six hours to the ET WALL clock maps 18:00 -> 00:00, so grouping on the shifted date
#: puts each Globex session in exactly one bucket and puts the daily 17:00-18:00 ET
#: maintenance halt on the boundary BETWEEN two buckets instead of inside one. Measured on
#: the store this matters: 249 of the 251 sub-four-hour non-one-minute steps in ES.parquet
#: are that halt, and every one of them is a boundary under this grouping, not a hole.
#: Six is the exchange's number, not a fitted one - it is 24:00 minus the 18:00 ET open.
TRADE_DATE_ROLL_HOURS = 6


def check_futures_frame(symbol: str, df, *, contract_col: str = "contract",
                        time_col: str | None = None,
                        report: Report | None = None,
                        calendar: SessionCalendar | None = None,
                        impossible_return: float = IMPOSSIBLE_RETURN,
                        stale_bars: int = STALE_BARS,
                        roll_gap_warn: float = 0.005) -> Report:
    """Validate one futures series that carries a contract identity per row.

    `df` needs a price column `c` and a contract column. `time_col` names the timestamp
    column when the frame is not time-indexed, which is how the ES store on disk is shaped.

    `calendar` is optional and OFF by default. Without it the gap check compares each
    session only against itself, which needs no table and cannot be wrong. With it, the
    session's expected LENGTH comes from the calendar too, so a session truncated at both
    ends is caught as well as one with a hole in the middle. Pass the calendar for the
    instrument's own exchange and no other: `equity_us.CALENDAR` is the CASH clock, which
    shuts at 13:00 ET on an early close while CME equity-index futures run to 13:15, and the
    store's 225-bar early closes are correct data that the cash calendar calls nine bars too
    long.
    """
    rep = report or Report()
    rep.symbols += 1
    if df is None or len(df) == 0:
        rep.add("empty", Severity.FAIL, symbol, "no rows at all")
        return rep
    rep.rows += len(df)

    if contract_col not in df.columns:
        rep.add("contract_identity", Severity.FAIL, symbol,
                f"no {contract_col!r} column: a futures series without contract identity "
                "cannot be checked for roll errors, and a roll error is invisible in price")
        return rep

    import pandas as pd

    ts = pd.to_datetime(df[time_col]) if time_col else pd.Series(df.index)
    ts = pd.Series(pd.DatetimeIndex(ts))
    contract = pd.Series(df[contract_col].to_numpy(), index=ts.index)
    close = pd.Series(df["c"].to_numpy(dtype=float), index=ts.index)

    _check_ordering(symbol, ts, rep)
    _check_duplicates(symbol, ts, contract, rep)
    _check_session_gaps(symbol, ts, rep, calendar)
    check_bar_structure(symbol, df, rep)
    _check_overlap(symbol, ts, contract, rep)
    _check_contract_order(symbol, ts, contract, rep)
    _check_rolls(symbol, ts, contract, close, rep, roll_gap_warn)
    _check_within_contract_jumps(symbol, contract, close, rep, impossible_return)
    vol = (pd.Series(df["v"].to_numpy(dtype=float), index=ts.index)
           if "v" in df.columns else None)
    _check_stale(symbol, contract, close, rep, stale_bars, vol)
    _check_quotes(symbol, df, rep)
    return rep


# --------------------------------------------------------------------------------- checks

def _check_ordering(symbol, ts, rep) -> None:
    if not ts.is_monotonic_increasing:
        bad = int((ts.diff() < pd.Timedelta(0)).sum()) if (pd := _pd()) else 0
        rep.add("time_order", Severity.FAIL, symbol,
                "timestamps go backwards; every roll and gap check below reads the series "
                "in order and would silently mis-attribute", bad)


def _pd():
    import pandas as pd
    return pd


def _check_duplicates(symbol, ts, contract, rep) -> None:
    """The same minute of the same contract, twice. Unambiguously one row too many.

    `_check_ordering` cannot see this: `is_monotonic_increasing` is evaluated NON-strictly by
    pandas, so `[09:30, 09:31, 09:31, 09:32]` is monotonic. `_check_overlap` cannot see it
    either - it groups by DAY and counts distinct contracts, so it fires only when the two
    rows disagree about the instrument. The case that actually happens is a refetch whose
    pages overlapped, which appends the same minute of the SAME contract twice with two
    different last prints, and that was invisible to both.

    Keyed on (timestamp, contract) rather than on the timestamp alone on purpose: one minute
    carrying two DIFFERENT contracts is the roll-overlap hazard, which is a WARN because the
    research path already drops mixed-contract days whole (`futures_discover.load`). One
    minute carrying the same contract twice is not a hazard to weigh up, it is a wrong row:
    a groupby bar count goes up by one, a `.diff()` yields a zero-length interval whose
    return divides by a repeat, and any join on timestamp fans out.

    Measured on the store: ES, MES, NQ and MNQ hold zero duplicates of either kind across
    1,612,886 rows, so this fails nothing that exists today and refuses the day a refetch
    introduces one.
    """
    dupes = int(_pd().DataFrame({"t": ts, "k": contract}).duplicated().sum())
    if dupes:
        rep.add("duplicates", Severity.FAIL, symbol,
                "the same minute of the same contract appears more than once; a refetch "
                "overlapped a page boundary and every timestamp join now fans out", dupes)


def _bar_interval(ts):
    """The store's own bar grid, read from the data instead of assumed.

    The modal positive step. Not a threshold and not tuned: it is the resolution the store
    was fetched at, so a one-minute store is checked against one minute and a five-minute
    store against five, with nothing to keep in sync by hand. 447,273 of ES.parquet's 447,599
    consecutive steps are exactly one minute, so the mode is not a close call.
    """
    pd = _pd()
    d = ts.diff()
    positive = d[d > pd.Timedelta(0)]
    if not len(positive):
        return None
    return positive.mode().iloc[0]


def _session_key(ts):
    """Each bar's CME trade date, as a normalised wall-clock timestamp.

    See `TRADE_DATE_ROLL_HOURS`. Built on the ET WALL clock rather than on UTC so the
    boundary is the exchange's 18:00 and not an hour either side of it for half the year;
    a tz-naive frame is taken at face value, since there is nothing else it could be.
    """
    pd = _pd()
    et = ts.dt.tz_convert(_ET) if ts.dt.tz is not None else ts
    wall = et.dt.tz_localize(None) if et.dt.tz is not None else et
    return (wall + pd.Timedelta(hours=TRADE_DATE_ROLL_HOURS)).dt.normalize()


def _check_session_gaps(symbol, ts, rep, calendar=None) -> None:
    """Bars missing from inside a session. The hazard `futures_discover` had no gate for.

    WHY THIS IS A FAIL AND NOT THE CORE VALIDATOR'S WARN
    ----------------------------------------------------
    `core.dataquality.gaps` reports a hole as a WARN because its consumer is the live runner,
    which now carries the last known mark across one (AUD-05). This module's consumer is
    `futures_discover.load`, and its output goes straight into `session_frames` ->
    `FeatureSet.build`, where every rolling window is computed WITHIN a session. A hole there
    does not announce itself: the window still returns a number, it is just a number over the
    wrong minutes, and every per-session statistic downstream inherits it. There is no
    caller to warn.

    WHY A MISSING MINUTE IS ABSENCE AND NOT A QUIET MARKET
    -------------------------------------------------------
    The feed emits a bar for every minute of the session whether or not anything trades - the
    1,354 zero-volume bars in ES.parquet, 2,340 in MES, 4,258 in NQ and 1,873 in MNQ are that
    behaviour made visible. So the grid is complete by construction and a missing minute is a
    row that was dropped, not a minute nobody wanted. That is why the tolerance is zero
    absent bars rather than a number somebody picked.

    WHAT IS DELIBERATELY NOT CHECKED WITHOUT A CALENDAR
    ----------------------------------------------------
    Only holes INTERIOR to a session, measured against that session's own first and last bar.
    Whether a session is the right LENGTH is a calendar question and the answer is not the US
    cash-equity one. Every short RTH session in the store is one of exactly two correct
    shapes: 210 bars ending 12:59 ET on a CME part-holiday (ES and NQ 10 each, the micros 7,
    which start later) and 225 bars ending 13:14 ET on an equity early close (3 and 2), the
    second being the 13:15 futures close that the 13:00 cash calendar would call nine bars
    too long. Pass `calendar` to have the length checked too; leave it None and this check
    still catches golden dataset I, whose seven deleted bars sit in the middle of an
    otherwise complete session.

    Measured on the four real stores: zero interior holes in 1,612,886 rows.
    """
    pd = _pd()
    if len(ts) < 3:
        return
    step = _bar_interval(ts)
    if step is None or step <= pd.Timedelta(0):
        return
    session = _session_key(ts)
    delta = ts.diff()
    holes = (delta > step) & (session.eq(session.shift()))
    n = int(holes.sum())
    if n:
        gap = delta[holes]
        absent = int(round(float((gap / step).sum())) - n)
        worst = gap.max()
        first = ts[holes].iloc[0]
        rep.add("session_gap", Severity.FAIL, symbol,
                f"{n} hole(s) inside a session: {absent} bar(s) absent from a "
                f"{step.total_seconds() / 60:.0f}m grid, worst "
                f"{worst.total_seconds() / 60:.0f}m ending {first}. Every rolling feature "
                "and every per-session statistic is computed across the hole as if the "
                "minutes either side were adjacent", n)

    if calendar is None:
        return
    _check_session_length(symbol, ts, session, step, calendar, rep)


def _check_session_length(symbol, ts, session, step, calendar, rep) -> None:
    """With a calendar in hand, a session must also be the length the calendar says.

    Split out so the calendar-free path above stays the thing that cannot be wrong. The
    expected length is `SessionCalendar.session_minutes`, which is the documented API and the
    same number the equity loader trims to; nothing here hard-codes 210, 225, 376 or 390.
    Days the calendar calls closed, and days past its `coverage_end`, are skipped rather than
    guessed at - `check_covered` raising is the calendar refusing to answer, and Part 18 says
    an unknown state is not a licence to invent one.

    The calendar must describe the SAME window the frame holds, or this reports the caller
    and not the data. Two measurements of what that costs, both on the real ES store: hand
    `equity_us.CALENDAR` the RTH-filtered frame and 313 correct 09:30-15:45 sessions are
    called short because the cash session runs to 16:00 (376 < 390); hand it the full Globex
    frame and it finds nothing at all, because a 1,380-bar trade date is never short of a
    390-minute session. Neither answer is about the store. Hence the default of None.
    """
    from quant_brain.core.calendar import CalendarCoverageError

    step_minutes = step.total_seconds() / 60.0
    if step_minutes <= 0:
        return
    short: list[tuple[object, int, int]] = []
    for day, count in ts.groupby(session).size().items():
        try:
            minutes = calendar.session_minutes(day.date())
        except CalendarCoverageError:
            continue
        if not minutes:
            continue
        expected = int(round(minutes / step_minutes))
        if int(count) < expected:
            short.append((day.date(), int(count), expected))
    if short:
        day, got, want = short[0]
        rep.add("session_short", Severity.FAIL, symbol,
                f"{len(short)} session(s) hold fewer bars than {calendar.name} says the "
                f"session is long, e.g. {day}: {got} < {want}. A session that stops early "
                "is not a short session, it is a session whose tail is missing", len(short))


def _check_overlap(symbol, ts, contract, rep) -> None:
    """Two contracts quoting on the same date. Whichever one a groupby picks is arbitrary."""
    pd = _pd()
    day = pd.Series(ts.dt.date.to_numpy(), index=ts.index)
    per_day = contract.groupby(day).nunique()
    overlapping = per_day[per_day > 1]
    if len(overlapping):
        rep.add("roll_overlap", Severity.WARN, symbol,
                f"{len(overlapping)} date(s) carry more than one contract; a session built "
                f"from these mixes instruments (first: {overlapping.index[0]})",
                int(len(overlapping)))


def _check_contract_order(symbol, ts, contract, rep) -> None:
    """A series that revisits a contract after moving on is stitched wrong."""
    seen: dict[str, int] = {}
    revisits = 0
    prev = None
    for i, c in enumerate(contract.to_numpy()):
        if c != prev:
            if c in seen:
                revisits += 1
            seen[c] = i
            prev = c
    if revisits:
        rep.add("roll_backwards", Severity.FAIL, symbol,
                f"{revisits} contract(s) reappear after the series had moved on; the "
                "stitching is not chronological", revisits)


def _check_rolls(symbol, ts, contract, close, rep, warn_at) -> None:
    """Report every roll and the gap it carries. A gap nobody knows about is the hazard."""
    changed = contract.ne(contract.shift())
    changed.iloc[0] = False
    idx = list(changed[changed].index)
    if not idx:
        rep.add("rolls", Severity.INFO, symbol, "single contract; no roll in this series")
        return
    big = 0
    worst = 0.0
    for i in idx:
        pos = close.index.get_loc(i)
        if pos == 0:
            continue
        before, after = float(close.iloc[pos - 1]), float(close.iloc[pos])
        if before <= 0:
            continue
        gap = abs(after - before) / before
        worst = max(worst, gap)
        if gap >= warn_at:
            big += 1
    rep.add("rolls", Severity.INFO, symbol,
            f"{len(idx)} roll(s); largest unadjusted gap {worst:.2%}", len(idx))
    if big:
        rep.add("roll_gap", Severity.WARN, symbol,
                f"{big} roll(s) gap at least {warn_at:.1%} unadjusted. Holding across one "
                "books P&L that never existed; either adjust the series or never hold "
                "through a roll", big)


def _check_within_contract_jumps(symbol, contract, close, rep, limit) -> None:
    """A jump this large inside ONE contract is a data error, not a market move.

    Grouped by contract deliberately: comparing across a roll would flag every roll as a
    bad print, which is how a check like this gets turned off.
    """
    ret = close.groupby(contract.to_numpy()).pct_change().abs()
    bad = ret[ret > limit]
    if len(bad):
        rep.add("impossible_move", Severity.FAIL, symbol,
                f"{len(bad)} bar(s) move more than {limit:.0%} within a single contract "
                f"(max {float(bad.max()):.1%})", int(len(bad)))


def _check_stale(symbol, contract, close, rep, limit, volume=None) -> None:
    """An unchanged price run, graded by whether anything actually traded during it.

    The distinction matters and the first version of this check missed it. Run against the
    real ES store it found exactly one run of 645 bars and called it a possible stuck feed;
    the run turned out to be Thanksgiving night 2025 - 21:44 to 08:29 ET with SIX contracts
    of total volume. That is a closed market, not a broken feed.

    So: a flat price with no volume is INFO, because it is what a shut exchange looks like.
    A flat price WITH volume is a WARN, because trades printing at an unchanging price is
    what a stuck feed looks like, and that one can silently poison a backtest.
    """
    same = close.eq(close.shift()) & contract.eq(contract.shift())
    runs: list[tuple[int, int]] = []
    run = 0
    for i, v in enumerate(same.to_numpy()):
        if v:
            run += 1
        else:
            if run >= limit:
                runs.append((run, i - 1))
            run = 0
    if run >= limit:
        runs.append((run, len(same) - 1))
    if not runs:
        return

    longest = max(r for r, _ in runs)
    traded = 0
    if volume is not None:
        for length, end in runs:
            seg = volume.iloc[max(0, end - length): end + 1]
            if float(seg.sum()) > length:      # more than ~1 contract a minute
                traded += 1
    if traded:
        rep.add("stale_quote", Severity.WARN, symbol,
                f"{traded} unchanged run(s) of {limit}+ bars carry real volume; a feed that "
                "prints trades at a frozen price is the failure mode that poisons a "
                "backtest silently", traded)
    else:
        rep.add("stale_quote", Severity.INFO, symbol,
                f"{len(runs)} unchanged run(s) of {limit}+ bars (longest {longest}), all "
                "with negligible volume - a closed or holiday-thin session, not a feed fault",
                len(runs))


def _check_quotes(symbol, df, rep) -> None:
    """Crossed or missing books. Only runs when the store actually carries quotes."""
    has_bid, has_ask = "bid" in df.columns, "ask" in df.columns
    if not (has_bid and has_ask):
        rep.add("quotes", Severity.INFO, symbol,
                "no bid/ask columns: the spread is ASSUMED by the cost model, not measured. "
                "Fetch BID_ASK to replace an assumption with a number")
        return
    import pandas as pd
    # Series-typed explicitly: pd.to_numeric's return union includes scalars, so the
    # comparisons below are not statically known to be elementwise without this.
    bid = pd.Series(pd.to_numeric(df["bid"], errors="coerce"))
    ask = pd.Series(pd.to_numeric(df["ask"], errors="coerce"))
    crossed = int((bid > ask).sum())
    if crossed:
        rep.add("crossed_book", Severity.FAIL, symbol,
                f"{crossed} bar(s) have bid above ask, which cannot be true", crossed)
    nonpos = int(((bid <= 0) | (ask <= 0)).sum())
    if nonpos:
        rep.add("quote_nonpositive", Severity.FAIL, symbol,
                f"{nonpos} bar(s) have a non-positive bid or ask", nonpos)


def require_usable(symbol: str, df, **kw) -> Report:
    """Validate and raise if the store must not be traded or researched on.

    The counterpart to `core.dataquality.require_usable`, for a futures frame. Fails closed:
    a caller that ignores the return value still cannot proceed on a broken store.
    """
    from quant_brain.core.dataquality import DataQualityError
    rep = check_futures_frame(symbol, df, **kw)
    if rep.failed:
        lines = "\n".join(f.line() for f in rep.findings if f.severity is Severity.FAIL)
        raise DataQualityError(f"{symbol}: futures store is not usable\n{lines}")
    return rep
