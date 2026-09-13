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
"""
from __future__ import annotations

from quant_brain.core.dataquality import Report, Severity

#: A same-contract move this large between consecutive bars is a data error rather than a
#: market move. ES has had 7% limit-down days; 20% inside one minute has not happened and
#: would be halted long before.
IMPOSSIBLE_RETURN = 0.20

#: Consecutive identical bars beyond this count are a feed artefact. Overnight CME sessions
#: genuinely go quiet, so this is deliberately loose - it is looking for a stuck feed, not
#: for a thin hour.
STALE_BARS = 120


def check_futures_frame(symbol: str, df, *, contract_col: str = "contract",
                        time_col: str | None = None,
                        report: Report | None = None,
                        impossible_return: float = IMPOSSIBLE_RETURN,
                        stale_bars: int = STALE_BARS,
                        roll_gap_warn: float = 0.005) -> Report:
    """Validate one futures series that carries a contract identity per row.

    `df` needs a price column `c` and a contract column. `time_col` names the timestamp
    column when the frame is not time-indexed, which is how the ES store on disk is shaped.
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
