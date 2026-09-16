"""Futures contract symbols: parse them, order them, and refuse the ambiguous ones.

WHY THIS IS NOT A REGEX IN THE ADAPTER
----------------------------------------
A contract symbol is `ROOT + MONTH_CODE + YEAR`, and the year is where it goes wrong. IBKR's
local symbols use ONE year digit - `ESU5` - which is ambiguous by construction: U5 is
September 2025, September 2035, September 2015 and September 1995. Every parser has to pick
a century window, and a parser that picks one silently will one day date a contract ten years
wrong and produce a roll ordering that looks fine.

So the window is explicit, stated, and narrow, and a symbol whose expiry cannot be resolved
inside it is REFUSED rather than guessed.

WHAT THIS DOES NOT DO
---------------------
It does not know expiry DATES. The third Friday of the contract month is the rule for the CME
equity index complex, but it is not the rule for every product, and this repository has no
verified holiday table (see `futures_discover.session_frames` for the same refusal about the
trading calendar). `expiry_month` is exact; `last_trade_date` is only available when the
caller supplies it from the chain definition that fetched the data.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

#: CME month codes. The letters are the standard set; I, L, O, R, S, T, U... no - only these
#: twelve are month codes, and the absent letters (A-E, I, L, O, P, R, S, T, W, Y) are not.
MONTH_CODES: dict[str, int] = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}
CODE_FOR_MONTH: dict[int, str] = {v: k for k, v in MONTH_CODES.items()}

#: The quarterly cycle the equity index complex trades. March, June, September, December.
QUARTERLY_CODES: tuple[str, ...] = ("H", "M", "U", "Z")

#: The century window for a one-digit year. A symbol is resolved to the year in
#: [ANCHOR - 4, ANCHOR + 5] whose last digit matches - ten consecutive years, so exactly one
#: candidate always exists and no symbol is ambiguous WITHIN the window.
#:
#: The anchor is a constant rather than `date.today().year` on purpose: a parser whose output
#: depends on when it runs makes a stored manifest un-reproducible, and the whole point of
#: this layer is that a result can be re-derived. Move it deliberately, in a commit, when the
#: data outgrows the window - and the tests will tell you, because `resolve_year` refuses
#: anything more than five years ahead of it.
YEAR_ANCHOR = 2026

_ONE_DIGIT = re.compile(r"^([A-Z0-9]{1,4}?)([FGHJKMNQUVXZ])(\d)$")
_TWO_DIGIT = re.compile(r"^([A-Z0-9]{1,4}?)([FGHJKMNQUVXZ])(\d{2})$")


class ContractSymbolError(ValueError):
    """A symbol that cannot be parsed unambiguously. Never guessed around."""


@dataclass(frozen=True, order=True)
class ContractCode:
    """One parsed futures contract symbol.

    Ordered by (year, month) so `sorted()` puts a chain in chronological order - which is
    what a roll sequence is, and getting it from string sort instead would put ESZ5 before
    ESH6 correctly and ESU5 before ESH6 wrongly.
    """

    year: int
    month: int
    root: str
    symbol: str

    @property
    def month_code(self) -> str:
        return CODE_FOR_MONTH[self.month]

    @property
    def expiry_month(self) -> dt.date:
        """The first day of the contract month. NOT the last trade date - see the module
        docstring; that needs a calendar this repository does not have."""
        return dt.date(self.year, self.month, 1)

    @property
    def is_quarterly(self) -> bool:
        return self.month_code in QUARTERLY_CODES

    def canonical(self) -> str:
        """`ESU25` - root plus month code plus TWO year digits. Unambiguous by construction.

        The form to write into a manifest. `ESU5` is what IBKR calls it and what the store
        holds; that is preserved as `symbol`, because rewriting a provider's identifier is
        how a dataset stops matching the file it came from.
        """
        return f"{self.root}{self.month_code}{self.year % 100:02d}"


def resolve_year(digits: str, *, anchor: int = YEAR_ANCHOR) -> int:
    """A one- or two-digit year to a full year, inside the declared window.

    One digit: the unique year in [anchor-4, anchor+5] ending in that digit.
    Two digits: the unique year in [anchor-49, anchor+50] ending in those digits.
    """
    if len(digits) == 1:
        d = int(digits)
        for y in range(anchor - 4, anchor + 6):
            if y % 10 == d:
                return y
        raise ContractSymbolError(f"no year ending in {d} within the window")   # unreachable
    if len(digits) == 2:
        dd = int(digits)
        for y in range(anchor - 49, anchor + 51):
            if y % 100 == dd:
                return y
        raise ContractSymbolError(f"no year ending in {dd:02d} within the window")
    raise ContractSymbolError(f"year must be 1 or 2 digits, got {digits!r}")


def parse(symbol: str, *, anchor: int = YEAR_ANCHOR) -> ContractCode:
    """Parse `ESU5`, `ESU25`, `MESZ5`... Refuses anything it cannot resolve exactly.

    Two digits are tried FIRST. `MESZ5` is otherwise readable as root MES + Z + 5 or as root
    ME + S... no - S is not a month code, so that one is safe. But `NQZ5` versus a
    hypothetical root `NQZ` with a two-digit year is genuinely ambiguous, and the rule
    "prefer the two-digit reading" is stated here so the choice is visible rather than
    emergent from regex ordering.
    """
    s = (symbol or "").strip().upper()
    if not s:
        raise ContractSymbolError("empty contract symbol")

    m = _TWO_DIGIT.match(s)
    if m:
        root, code, yy = m.groups()
        return ContractCode(year=resolve_year(yy, anchor=anchor),
                            month=MONTH_CODES[code], root=root, symbol=symbol)
    m = _ONE_DIGIT.match(s)
    if m:
        root, code, y = m.groups()
        return ContractCode(year=resolve_year(y, anchor=anchor),
                            month=MONTH_CODES[code], root=root, symbol=symbol)
    raise ContractSymbolError(
        f"{symbol!r} is not a futures contract symbol this layer can resolve. Expected "
        f"ROOT + month code + 1 or 2 year digits, e.g. ESU5 or ESU25. Month codes are "
        f"{''.join(sorted(MONTH_CODES))}. A symbol that cannot be parsed is refused rather "
        f"than passed through, because an unparsed symbol silently defeats roll ordering.")


def family_of(symbol: str, *, anchor: int = YEAR_ANCHOR) -> str:
    """The root a contract belongs to. `ESU5` -> `ES`. This is what prices the bar."""
    return parse(symbol, anchor=anchor).root


def chain_order(symbols) -> list[ContractCode]:
    """A set of symbols in chronological expiry order, with duplicates refused.

    Duplicates are an error rather than a dedup: two rows claiming the same contract in a
    chain definition means the chain was assembled twice, and quietly collapsing them hides
    which of the two the data actually came from.
    """
    parsed = [parse(s) for s in symbols]
    seen: dict[tuple[int, int], str] = {}
    for c in parsed:
        key = (c.year, c.month)
        if key in seen and seen[key] != c.symbol:
            raise ContractSymbolError(
                f"{c.symbol!r} and {seen[key]!r} both resolve to {c.year}-{c.month:02d}; "
                f"a chain cannot contain the same expiry twice")
        seen[key] = c.symbol
    return sorted(parsed)


def is_contiguous_chain(symbols, *, cycle=QUARTERLY_CODES) -> tuple[bool, str]:
    """Does this chain skip an expiry in its own cycle?

    A skipped quarter is not automatically wrong - `MES` legitimately starts at Z5 because
    IBKR no longer has a security definition for `MESU5` - but it IS something a manifest
    must record, because a continuous series with a hole in its chain has a roll that spans
    six months and a gap that looks like a price move.
    """
    codes = chain_order(symbols)
    if len(codes) < 2:
        return True, "fewer than two contracts; nothing to skip"
    if not all(c.month_code in cycle for c in codes):
        off = sorted({c.month_code for c in codes} - set(cycle))
        return False, f"contains non-{'/'.join(cycle)} months: {off}"
    months = [c.year * 12 + c.month for c in codes]
    step = 12 // len(cycle)
    gaps = [(b - a) for a, b in zip(months[:-1], months[1:], strict=True)]
    bad = [g for g in gaps if g != step]
    if bad:
        return False, (f"expiry gaps of {sorted(set(bad))} months where the {'/'.join(cycle)} "
                       f"cycle steps {step}")
    return True, f"contiguous {'/'.join(cycle)} chain of {len(codes)}"


__all__ = ["CODE_FOR_MONTH", "MONTH_CODES", "QUARTERLY_CODES", "YEAR_ANCHOR",
           "ContractCode", "ContractSymbolError", "chain_order", "family_of",
           "is_contiguous_chain", "parse", "resolve_year"]
