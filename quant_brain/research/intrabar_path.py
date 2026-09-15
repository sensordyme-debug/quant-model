"""The equity path the Topstep twin should see, with the excursion inside each bar restored.

WHAT THIS FIXES
---------------
`futures_discover.session_accounting` builds its equity path from minute CLOSES. That is the
correct series for P&L - the close is where the money actually is at the end of the bar - but
it is the wrong series for a barrier test, and the Topstep maximum loss limit is a barrier
test. A long position held through a bar is marked at that bar's LOW at some point inside it,
and the platform liquidates on the touch. A path made of closes never shows that touch.

Measured on the futures store, always long one lot, 09:30-16:00 ET:

    ES    310 sessions   worst mark from closes, median -$1,075
                         worst mark using the bar low,  median -$1,162
                         hidden depth: median $75, 90th percentile $175, max $725
                         8 sessions (2.6%) survive the $2,000 limit on the close path
                         and breach it on the bar low

    MES   249 sessions   hidden depth: median $9, 90th percentile $19, max $76
                         0 sessions flip

So on the mini the omission is worth a few percent of sessions in the OPTIMISTIC direction,
which is the direction that matters. On the micro it is immaterial, because the same points
are a tenth of the dollars.

WHAT IT DOES NOT CLAIM
----------------------
This is a BOUND, not a reconstruction. It marks each bar at the extreme that hurts the
current position, which assumes the adverse extreme is reached while the position is on. For
a position held through the whole bar that is exactly right. For a bar on which the position
CHANGES it is conservative, because the fill happens somewhere inside the bar and the trader
may not have held through the extreme. The engine cannot tell which from one-minute OHLC, so
it takes the conservative reading and says so, rather than taking the flattering one silently.

Sub-bar sequencing is still not modelled and cannot be from OHLC: whether the low came before
or after the high inside a bar is unknowable here. That only matters for a path that would
touch the limit on one of them and recover, and the conservative reading already assumes the
worse ordering.

WHY IT IS OPT-IN
----------------
Turning it on changes twin verdicts - strictly towards more breaches - so every previously
published pass rate in this repository was computed WITHOUT it. Making it the silent default
would rewrite those numbers with no record of why they moved. Callers ask for it explicitly,
the result records that they did, and `docs/TOPSTEP_TWIN_AUDIT.md` carries the measurement.
"""
from __future__ import annotations

import numpy as np


def adverse_marks(pos, close, high, low, *, multiplier: float, contracts: int,
                  ) -> np.ndarray:
    """The worst intra-bar equity mark for each bar, in the same units as the close path.

    Element `j` is the gross equity, relative to the session open, at the worst moment
    inside bar `j+1` - the bar whose move position `pos[j]` earns under the one-bar lag.
    Long is marked at the low, short at the high, flat at the close.

    Returns an array the same length as `session_accounting`'s gross path, so the two can be
    interleaved point for point.
    """
    pos = np.nan_to_num(np.asarray(pos, dtype=float), nan=0.0)
    close = np.asarray(close, dtype=float)
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(pos)
    if n < 2:
        return np.zeros(0)
    if not (len(close) == len(high) == len(low) == n):
        raise ValueError(f"pos, close, high and low must be the same length; got "
                         f"{n}, {len(close)}, {len(high)}, {len(low)}")

    scale = multiplier * contracts
    held = pos[:-1]
    step_close = np.diff(close) * scale
    equity = np.cumsum(held * step_close)
    #: Equity ENTERING each bar, which is what the excursion is measured from.
    entering = np.concatenate([[0.0], equity[:-1]])

    #: The adverse extreme for the position held: the low hurts a long, the high hurts a
    #: short. `np.where` rather than a branch because the position can differ bar to bar.
    adverse_px = np.where(held > 0, low[1:], np.where(held < 0, high[1:], close[1:]))
    return entering + held * (adverse_px - close[:-1]) * scale


def with_intrabar_marks(net_path, pos, close, high, low, *, multiplier: float,
                        contracts: int) -> tuple[float, ...]:
    """Interleave each bar's worst mark before its close, keeping the settled P&L exact.

    The output alternates (worst mark of bar j+1, close mark of bar j+1) and therefore ENDS
    on the session's realised P&L, which is what `TwinDay.pnl` must agree with. Costs are
    carried by `net_path` and are not re-derived here: the excursion is applied as a gross
    offset to the same point the close path reports, so a mark is never charged twice and
    never charged less than the close beside it.

    A mark that is not adverse is dropped rather than emitted, so a session with no
    excursion produces exactly the close path and the twin's answer cannot change.
    """
    net = np.asarray(net_path, dtype=float)
    if net.size == 0:
        return ()
    worst_gross = adverse_marks(pos, close, high, low, multiplier=multiplier,
                                contracts=contracts)
    if worst_gross.size != net.size:
        raise ValueError(f"the net path has {net.size} points but the bars imply "
                         f"{worst_gross.size}; they must describe the same session")

    scale = multiplier * contracts
    held = np.nan_to_num(np.asarray(pos, dtype=float), nan=0.0)[:-1]
    close_arr = np.asarray(close, dtype=float)
    gross_close = np.cumsum(held * np.diff(close_arr) * scale)
    #: The cost already deducted at each point, taken from the close path so the two series
    #: are charged identically. The excursion moves only the gross part.
    excursion = worst_gross - gross_close

    out: list[float] = []
    for j in range(net.size):
        if excursion[j] < 0.0:
            out.append(float(net[j] + excursion[j]))
        out.append(float(net[j]))
    return tuple(out)
