"""A hand-computable ES session builder for the Initial Balance Reversion goldens.

Every golden test states its expected numbers as arithmetic worked out in the test, not as a
recorded output, so a test can fail because the engine changed rather than because the engine
and the fixture drifted together.

THE BUCKET CONSTRUCTION
-------------------------
The engine consumes 1-minute bars and aggregates them itself - the same certified aggregator
the VWAP strategy uses - so the builder writes five 1-minute bars whose aggregate is exactly
the (O, H, L, C) asked for:

    bar 1   (O, O, O, O)
    bar 2   (O, H, O, H)        high reached
    bar 3   (H, H, L, L)        low reached
    bar 4   (L, L, L, L)
    bar 5   (L, max(L,C), L, C) close set

which requires H >= max(O, C) and L <= min(O, C) - asserted, so a test that asks for an
impossible bar fails at build time rather than producing a quietly different one.
"""
from __future__ import annotations

import datetime as dt

from quant_brain.strategies.initial_balance_reversion.engine import Engine
from quant_brain.strategies.initial_balance_reversion.spec import FROZEN, TIMEZONE, FrozenSpec
from quant_brain.strategies.vwap_pullback.indicators import Bar

OPEN_MIN = 9 * 60 + 30
END_MIN = 15 * 60 + 45
DAY = dt.date(2026, 6, 10)


def at(day: dt.date, minute: int) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, minute // 60, minute % 60,
                       tzinfo=TIMEZONE)


class Session:
    """A 09:30-15:45 ES session, written one 5-minute bucket at a time."""

    def __init__(self, day: dt.date = DAY, base: float = 5000.0):
        self.day = day
        self.base = base
        self.blocks: dict[int, tuple[float, float, float, float]] = {}

    def block(self, hhmm: str, o: float, h: float, lo: float, c: float) -> Session:
        """Set one 5-minute bucket by its START time, e.g. '10:35'."""
        hh, mm = hhmm.split(":")
        minute = int(hh) * 60 + int(mm)
        assert minute % 5 == 0, f"{hhmm} is not a 5-minute boundary"
        assert h >= max(o, c) and lo <= min(o, c), f"{hhmm}: impossible bar"
        self.blocks[minute] = (o, h, lo, c)
        return self

    def ib(self, high: float, low: float) -> Session:
        """Build the 09:30-10:25 window so its aggregate high/low are exactly these."""
        mid = (high + low) / 2.0
        self.block("09:30", mid, mid, mid, mid)
        self.block("09:35", mid, high, mid, mid)          # the high
        self.block("09:40", mid, mid, low, mid)           # the low
        for m in range(9 * 60 + 45, 10 * 60 + 30, 5):
            self.block(f"{m // 60:02d}:{m % 60:02d}", mid, mid, mid, mid)
        return self

    def quiet(self, frm: str, to: str, price: float) -> Session:
        """Fill a span with flat buckets at one price."""
        hh, mm = frm.split(":")
        a = int(hh) * 60 + int(mm)
        hh, mm = to.split(":")
        b = int(hh) * 60 + int(mm)
        for m in range(a, b, 5):
            self.block(f"{m // 60:02d}:{m % 60:02d}", price, price, price, price)
        return self

    def bars(self) -> list[Bar]:
        """Every 1-minute bar of the session, buckets filled and gaps held flat."""
        out: list[Bar] = []
        last = self.base
        for minute in range(OPEN_MIN, END_MIN + 1):
            start = minute - (minute % 5)
            if start in self.blocks:
                o, h, lo, c = self.blocks[start]
                k = minute - start
                spec = [(o, o, o, o), (o, h, o, h), (h, h, lo, lo), (lo, lo, lo, lo),
                        (lo, max(lo, c), lo, c)][k]
                last = c
            else:
                spec = (last, last, last, last)
            out.append(Bar(timestamp=at(self.day, minute), open=spec[0], high=spec[1],
                           low=spec[2], close=spec[3], volume=1000.0))
        return out


def run(session: Session, spec: FrozenSpec = FROZEN, engine: Engine | None = None) -> Engine:
    """Feed one session to a fresh engine (or a supplied one, to carry state across days)."""
    eng = engine or Engine(spec=spec)
    bars = session.bars()
    eng.start_session(session.day, bars[0].timestamp)
    for b in bars:
        eng.on_bar(b)
    eng.end_session(bars[-1].timestamp)
    return eng


__all__ = ["DAY", "END_MIN", "OPEN_MIN", "Session", "at", "run"]
