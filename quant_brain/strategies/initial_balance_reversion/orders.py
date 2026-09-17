"""The bracket this strategy places, as a value rather than as scattered fields.

There is exactly one shape: a market entry with an OCO stop and limit target, plus a
wall-clock deadline. It is kept here so the ledger, the tests and the engine all describe the
same object, and so a reader can see in one place what "cancel all brackets" cancels.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class Bracket:
    """A resting stop and a resting limit, one-cancels-other, with a time fuse."""

    direction: int
    quantity: int
    stop_price: float
    target_price: float
    deadline: dt.datetime

    def stop_touched(self, high: float, low: float) -> bool:
        return low <= self.stop_price if self.direction > 0 else high >= self.stop_price

    def target_touched(self, high: float, low: float) -> bool:
        return high >= self.target_price if self.direction > 0 else low <= self.target_price

    def ambiguous(self, high: float, low: float) -> bool:
        """Both legs touched inside one bar. OHLCV cannot order them."""
        return self.stop_touched(high, low) and self.target_touched(high, low)

    def expired(self, when: dt.datetime) -> bool:
        return when >= self.deadline


__all__ = ["Bracket"]
