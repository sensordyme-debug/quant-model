"""CME/CBOT/NYMEX/COMEX futures - the priority market branch.

The session calendar comes from LEAN's own market-hours database rather than a hand-typed
table: it already carries all nine target roots with the 17:00-18:00 maintenance break, 169
early closes and 119 late opens per contract, and it is maintained upstream. Audited before
being trusted - it agrees with this repository's independently-typed NYSE table on every
probe (see tests/test_qb_lean_calendar.py).
"""
from quant_brain.markets.futures_cme.instruments import CONTRACTS, DATA_VERIFIED, get, micros_of
from quant_brain.markets.lean_calendar import cme_future


def calendar(root: str, *, rth: bool = False):
    """The session calendar for a futures root. Globex span by default, not RTH."""
    return cme_future(root, rth=rth)


__all__ = ["CONTRACTS", "DATA_VERIFIED", "calendar", "cme_future", "get", "micros_of"]
