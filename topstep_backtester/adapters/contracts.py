"""Contract identity: canonical ``contract_symbol`` in, upstream ``contract_id`` out.

THE TWO VOCABULARIES
--------------------
    canonical (this repo)   instrument "ES" + contract_symbol "ESU5"
    upstream (the engine)   contract_id  "CON.F.US.ES.U25"

The engine derives the instrument spec - tick size, tick value, session class - from the
contract id by splitting on dots and taking field 3
(``core/instruments.py:symbol_of_contract_id``). Everything downstream of that, including
every dollar of P&L, therefore depends on this translation being right. It is worth its own
module and its own tests.

THE SINGLE-DIGIT YEAR PROBLEM
-----------------------------
CME floor codes carry one year digit: ``ESU5`` is September 2025 - or September 2015, or
September 2035. The digit does not say. Guessing "the current decade" is the kind of
assumption that silently mis-sources a backtest, so this module refuses to guess: a
single-digit year requires a reference date (the session the bar belongs to) and resolves to
the nearest matching year, which for a listed future is never more than a couple of years
out. With no reference date, a single-digit year raises.
"""
from __future__ import annotations

import datetime as dt
import re

from topstep_backtester.upstream import SPECS, symbol_of_contract_id

#: CME month codes. Ordered by month so the table reads as a calendar.
MONTH_CODES: dict[str, int] = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}
#: The inverse, for building a code from a month number.
CODE_FOR_MONTH: dict[int, str] = {m: c for c, m in MONTH_CODES.items()}

#: ``ESU5`` / ``ESZ25`` / ``MNQH26``. Root is greedy-but-alphabetic, then one month code,
#: then one or two year digits.
_FLOOR_CODE = re.compile(r"^(?P<root>[A-Z0-9]{1,4}?)(?P<month>[FGHJKMNQUVXZ])(?P<year>\d{1,2})$")

#: How far from the reference date a listed contract can plausibly be. Quarterly equity
#: index futures list about a year out; this is deliberately generous and still rules out
#: the decade-scale ambiguity that the single year digit creates.
_MAX_YEARS_FROM_REFERENCE = 5


class ContractIdError(ValueError):
    """A contract identity that cannot be translated without guessing."""


def contract_id(symbol: str, *, year: int, month: int) -> str:
    """Build the upstream contract id for a product and expiry.

    >>> contract_id("ES", year=2025, month=12)
    'CON.F.US.ES.Z25'
    """
    if symbol not in SPECS:
        raise ContractIdError(
            f"{symbol!r} has no upstream instrument spec; the engine covers {sorted(SPECS)}. "
            f"A product the engine cannot price is a product this pipeline cannot backtest."
        )
    if month not in CODE_FOR_MONTH:
        raise ContractIdError(f"month {month} is not 1-12")
    if not 2000 <= year <= 2099:
        raise ContractIdError(
            f"year {year} is outside 2000-2099; the two-digit year field cannot express it"
        )
    return f"CON.F.US.{symbol}.{CODE_FOR_MONTH[month]}{year % 100:02d}"


def parse_floor_code(code: str, *, reference: dt.date | None = None) -> tuple[str, int, int]:
    """Split ``ESU5`` into ``("ES", 2025, 9)``.

    ``reference`` is the session date the code was observed on, and is REQUIRED when the
    year is a single digit - see the module docstring. It is ignored for two-digit years,
    which are unambiguous.
    """
    match = _FLOOR_CODE.match(code.strip().upper())
    if match is None:
        raise ContractIdError(
            f"{code!r} is not a CME floor code (root + month letter + 1-2 year digits, "
            f"e.g. ESU5 or ESZ25)"
        )
    root = match["root"]
    month = MONTH_CODES[match["month"]]
    digits = match["year"]

    if len(digits) == 2:
        return root, 2000 + int(digits), month

    if reference is None:
        raise ContractIdError(
            f"{code!r} carries a single year digit ({digits}) and no reference date was "
            f"given. 'U5' is September 2025, 2015 and 2035 equally; this pipeline resolves "
            f"it from the session the bar belongs to rather than assuming a decade. Pass "
            f"reference=<session_date>."
        )

    wanted = int(digits)
    candidates = [
        year
        for year in range(reference.year - _MAX_YEARS_FROM_REFERENCE,
                          reference.year + _MAX_YEARS_FROM_REFERENCE + 1)
        if year % 10 == wanted
    ]
    if not candidates:  # pragma: no cover - the range always spans a full decade
        raise ContractIdError(f"no year ending in {wanted} near {reference}")
    best = min(candidates, key=lambda year: abs(year - reference.year))
    return root, best, month


def contract_id_from_floor_code(code: str, *, instrument: str,
                                reference: dt.date | None = None) -> str:
    """Translate a canonical ``contract_symbol`` into an upstream contract id.

    ``instrument`` is the canonical economic exposure and is checked against the root parsed
    out of the code. A disagreement means the frame is mislabelled, which is exactly the
    conflation ``quant_brain.data.schema`` was written to prevent, so it raises.
    """
    root, year, month = parse_floor_code(code, reference=reference)
    if root != instrument:
        raise ContractIdError(
            f"contract_symbol {code!r} has root {root!r} but the frame declares instrument "
            f"{instrument!r}. One of the two is wrong and guessing which would put a "
            f"multiplier on the wrong prices."
        )
    return contract_id(instrument, year=year, month=month)


def assert_resolves(cid: str, *, expect: str) -> None:
    """Confirm the ENGINE reads the id the way we intended.

    This is the check that matters. Our grammar could be perfectly self-consistent and still
    disagree with upstream about which field carries the product; asking upstream directly
    removes that whole class of doubt.
    """
    got = symbol_of_contract_id(cid)
    if got != expect:
        raise ContractIdError(
            f"the engine reads {cid!r} as product {got!r}, not {expect!r}. Layer B and the "
            f"engine disagree about contract identity; every price in this run would be "
            f"scaled by the wrong tick value."
        )


__all__ = [
    "CODE_FOR_MONTH",
    "MONTH_CODES",
    "ContractIdError",
    "assert_resolves",
    "contract_id",
    "contract_id_from_floor_code",
    "parse_floor_code",
]
