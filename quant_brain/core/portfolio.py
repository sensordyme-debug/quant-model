"""Portfolio risk aggregation: what the book adds up to across strategies and instruments.

Phase 37 foundations. The sizers in `sizing.py` decide one position at a time, and a set
of individually sound positions can still be one bad book: three strategies each long a
quarter of the room to the MLL on ES, NQ and RTY are not three quarter-positions, they are
one position at three quarters of the room with a 0.9 correlation between the legs. This
module exists to see that.

It aggregates exposure four ways - gross and net, per instrument, per strategy, per venue -
and combines dollars at risk under a correlation matrix. It then checks the lot against a
`PortfolioLimits` and reports EVERY breach with a reason code, not only the first, because
the caller that acts on one breach still needs to know about the other two.

Two refusals are built in and neither is negotiable:

  * A correlation matrix that is not positive semi-definite is not a correlation matrix. It
    can make combined risk imaginary, or - worse - small, and the second failure is silent.
    The computation is refused with `PORTFOLIO_CORRELATION_NOT_PSD`.
  * A matrix that has no row for an instrument in the book is refused rather than padded.
    Assuming zero correlation for a missing instrument is the optimistic guess, and the
    optimistic guess is the one that gets taken when nobody is looking.

And the module-wide rule from `sizing.py` holds here too: anything that cannot be computed
from the inputs given comes back as an unavailable `Metric` with a reason, and a configured
limit whose metric is unavailable is reported as a breach (`PORTFOLIO_UNVERIFIABLE`). A
limit that cannot be checked has not been passed.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from quant_brain.core.instruments import InstrumentSpec

# Reason codes. Listed once so a dashboard or a test can enumerate them.
GROSS_EXPOSURE = "PORTFOLIO_GROSS_EXPOSURE"
NET_EXPOSURE = "PORTFOLIO_NET_EXPOSURE"
LEVERAGE = "PORTFOLIO_LEVERAGE"
INSTRUMENT_EXPOSURE = "PORTFOLIO_INSTRUMENT_EXPOSURE"
STRATEGY_EXPOSURE = "PORTFOLIO_STRATEGY_EXPOSURE"
VENUE_EXPOSURE = "PORTFOLIO_VENUE_EXPOSURE"
TOTAL_RISK = "PORTFOLIO_TOTAL_RISK"
CORRELATED_RISK = "PORTFOLIO_CORRELATED_RISK"
UNVERIFIABLE = "PORTFOLIO_UNVERIFIABLE"

NO_EQUITY = "PORTFOLIO_NO_EQUITY"
NO_RISK = "PORTFOLIO_NO_RISK"
NO_CORRELATION = "PORTFOLIO_NO_CORRELATION"
CORRELATION_MISSING = "PORTFOLIO_CORRELATION_MISSING_INSTRUMENT"
CORRELATION_NOT_PSD = "PORTFOLIO_CORRELATION_NOT_PSD"
CORRELATION_MALFORMED = "PORTFOLIO_CORRELATION_MALFORMED"

BREACH_CODES: tuple[str, ...] = (
    GROSS_EXPOSURE, NET_EXPOSURE, LEVERAGE, INSTRUMENT_EXPOSURE, STRATEGY_EXPOSURE,
    VENUE_EXPOSURE, TOTAL_RISK, CORRELATED_RISK, UNVERIFIABLE,
)


# ======================================================================================
# INPUTS
# ======================================================================================


@dataclass(frozen=True)
class Exposure:
    """One line of the book: a strategy's position in one instrument, marked at a price.

    `quantity` is signed (short is negative). `risk_dollars` is what this line loses if its
    stop is hit - the same number `SizeDecision.risk_dollars` carries - and it is optional
    because not every position has a stop; a line without one simply makes the risk
    aggregates unavailable rather than counting as zero risk.
    """

    strategy: str
    spec: InstrumentSpec
    quantity: float
    price: float
    venue: str = ""
    risk_dollars: float | None = None

    def __post_init__(self) -> None:
        if not self.strategy:
            raise ValueError("an Exposure needs a strategy name; attribution is the point")
        if not math.isfinite(self.price) or self.price <= 0:
            raise ValueError(f"{self.spec.symbol}: price must be finite and positive, "
                             f"got {self.price}")
        if not math.isfinite(self.quantity):
            raise ValueError(f"{self.spec.symbol}: quantity must be finite, got {self.quantity}")
        if self.risk_dollars is not None and (
                not math.isfinite(self.risk_dollars) or self.risk_dollars < 0):
            raise ValueError(f"{self.spec.symbol}: risk_dollars must be finite and "
                             f"non-negative, got {self.risk_dollars}")

    @property
    def symbol(self) -> str:
        return self.spec.symbol

    @property
    def venue_name(self) -> str:
        """The venue this line trades on. Falls back to the spec's exchange, then 'unknown'.

        'unknown' is a real bucket, not a default: a per-venue limit applied to a book with
        unknown venues will report the unknown bucket by name.
        """
        return self.venue or self.spec.exchange or "unknown"

    @property
    def notional(self) -> float:
        """Signed dollar notional."""
        return self.spec.notional(self.price, self.quantity)

    @property
    def signed_risk(self) -> float | None:
        """Dollars at risk, signed by direction, for correlation-aware combination.

        A long and a short in two perfectly correlated instruments should net to zero;
        signing the risk by the position's direction is what makes that arithmetic work.
        """
        if self.risk_dollars is None:
            return None
        if self.quantity == 0:
            return 0.0
        return math.copysign(self.risk_dollars, self.quantity)


@dataclass(frozen=True)
class Slice:
    """Exposure of one bucket (an instrument, a strategy, a venue)."""

    net: float = 0.0
    gross: float = 0.0
    long: float = 0.0
    short: float = 0.0   # magnitude; always >= 0

    def add(self, notional: float) -> Slice:
        return Slice(
            net=self.net + notional,
            gross=self.gross + abs(notional),
            long=self.long + max(0.0, notional),
            short=self.short + max(0.0, -notional),
        )


@dataclass(frozen=True)
class Metric:
    """A number, or an explanation of why there is no number."""

    value: float | None
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.value is not None

    @property
    def code(self) -> str:
        return self.reason.split(":", 1)[0] if self.reason else ""

    @classmethod
    def unavailable(cls, code: str, detail: str) -> Metric:
        return cls(None, f"{code}: {detail}")


@dataclass(frozen=True)
class CorrelationMatrix:
    """A labelled correlation matrix with its own admissibility check.

    Shape errors (wrong number of rows, duplicate symbols) are typos and raise at
    construction. Value errors - asymmetry, a diagonal that is not one, an entry outside
    [-1, 1], a non-finite entry, a negative eigenvalue - are what an estimator produces on
    bad data, so they are reported by `problem()` and turned into a refusal by the caller
    rather than raised, because the caller needs the reason in its own result.
    """

    symbols: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        n = len(self.symbols)
        if len(set(self.symbols)) != n:
            raise ValueError(f"duplicate symbols in correlation matrix: {self.symbols}")
        if len(self.values) != n or any(len(row) != n for row in self.values):
            raise ValueError(f"correlation matrix for {n} symbols must be {n}x{n}")

    @classmethod
    def identity(cls, symbols: Sequence[str]) -> CorrelationMatrix:
        """Uncorrelated. A named, explicit choice - never a fallback the module makes."""
        syms = tuple(symbols)
        return cls(syms, tuple(tuple(1.0 if i == j else 0.0 for j in range(len(syms)))
                               for i in range(len(syms))))

    def array(self) -> np.ndarray:
        return np.asarray(self.values, dtype=float)

    def problem(self) -> str:
        """Empty string if admissible, otherwise `CODE: detail`."""
        a = self.array()
        if a.size == 0:
            return ""
        if not np.all(np.isfinite(a)):
            return f"{CORRELATION_MALFORMED}: contains NaN or inf"
        if not np.allclose(a, a.T, atol=1e-9, rtol=0.0):
            return f"{CORRELATION_MALFORMED}: not symmetric"
        if not np.allclose(np.diag(a), 1.0, atol=1e-9, rtol=0.0):
            return f"{CORRELATION_MALFORMED}: diagonal is not 1"
        if np.any(np.abs(a) > 1.0 + 1e-9):
            return f"{CORRELATION_MALFORMED}: an entry lies outside [-1, 1]"
        smallest = float(np.linalg.eigvalsh(a).min())
        if smallest < -1e-8 * a.shape[0]:
            return (f"{CORRELATION_NOT_PSD}: smallest eigenvalue {smallest:.3e}; this is not "
                    f"a correlation matrix and combined risk under it is meaningless")
        return ""

    @property
    def is_psd(self) -> bool:
        a = self.array()
        if a.size == 0:
            return True
        if not np.all(np.isfinite(a)):
            return False
        return float(np.linalg.eigvalsh(a).min()) >= -1e-8 * a.shape[0]

    def missing(self, symbols: Sequence[str]) -> tuple[str, ...]:
        have = set(self.symbols)
        return tuple(sorted(s for s in symbols if s not in have))

    def submatrix(self, symbols: Sequence[str]) -> np.ndarray:
        """The rows and columns for `symbols`, in that order. Caller checks `missing` first."""
        idx = [self.symbols.index(s) for s in symbols]
        return self.array()[np.ix_(idx, idx)]


def _check_limit(name: str, value: float | None) -> None:
    if value is not None and (not math.isfinite(value) or value < 0):
        raise ValueError(f"{name} must be a finite, non-negative number, got {value}")


@dataclass(frozen=True)
class PortfolioLimits:
    """The book-level ceilings. All in dollars except `max_leverage` (gross / equity).

    Every field is optional and None means "not configured", which is different from
    "unlimited" only in that nothing is reported for it. A configured limit that cannot be
    evaluated from the book's inputs is a breach, not a pass.
    """

    max_gross_exposure: float | None = None
    max_net_exposure: float | None = None
    max_leverage: float | None = None
    max_instrument_exposure: float | None = None
    max_strategy_exposure: float | None = None
    max_venue_exposure: float | None = None
    max_total_risk: float | None = None
    max_correlated_risk: float | None = None

    def __post_init__(self) -> None:
        for name in ("max_gross_exposure", "max_net_exposure", "max_leverage",
                     "max_instrument_exposure", "max_strategy_exposure",
                     "max_venue_exposure", "max_total_risk", "max_correlated_risk"):
            _check_limit(name, getattr(self, name))


@dataclass(frozen=True)
class Breach:
    """One limit that did not hold, and by how much."""

    code: str
    detail: str
    limit: float
    value: float | None
    key: str = ""

    def __str__(self) -> str:
        where = f" [{self.key}]" if self.key else ""
        return f"{self.code}{where}: {self.detail}"


# ======================================================================================
# THE BOOK
# ======================================================================================


class Portfolio:
    """A snapshot of every line across every strategy, and the arithmetic on it.

    Immutable by use: build one per check from the current positions. There is no
    `add()` because a book that mutates between the aggregate and the check is a book whose
    check answered a different question than the one it was asked.
    """

    def __init__(self, lines: Sequence[Exposure], *, equity: float | None = None):
        if equity is not None and not math.isfinite(equity):
            raise ValueError(f"equity must be finite, got {equity}")
        self.lines: tuple[Exposure, ...] = tuple(lines)
        self.equity = equity

    # -- exposure -------------------------------------------------------------------------

    def gross_exposure(self) -> float:
        """Sum of absolute notional. What the book would move if every leg moved together."""
        return float(sum(abs(x.notional) for x in self.lines))

    def net_exposure(self) -> float:
        """Signed sum of notional. Positive is net long."""
        return float(sum(x.notional for x in self.lines))

    def leverage(self) -> Metric:
        """Gross exposure over equity. Unavailable without a positive equity."""
        if self.equity is None:
            return Metric.unavailable(NO_EQUITY, "leverage needs equity and none was supplied")
        if self.equity <= 0:
            return Metric.unavailable(
                NO_EQUITY, f"equity is {self.equity:,.0f}; leverage is undefined at or "
                           f"below zero (and any open exposure is already a breach)")
        return Metric(self.gross_exposure() / self.equity)

    def _by(self, key) -> dict[str, Slice]:
        out: dict[str, Slice] = {}
        for x in self.lines:
            k = key(x)
            out[k] = out.get(k, Slice()).add(x.notional)
        return out

    def by_instrument(self) -> dict[str, Slice]:
        return self._by(lambda x: x.symbol)

    def by_strategy(self) -> dict[str, Slice]:
        return self._by(lambda x: x.strategy)

    def by_venue(self) -> dict[str, Slice]:
        return self._by(lambda x: x.venue_name)

    # -- risk -----------------------------------------------------------------------------

    def _risk_vector(self) -> tuple[dict[str, float], str]:
        """Signed dollars at risk per instrument, or the reason there is no such vector."""
        out: dict[str, float] = {}
        for x in self.lines:
            r = x.signed_risk
            if r is None:
                return {}, (f"{NO_RISK}: {x.strategy}/{x.symbol} has no risk_dollars; a "
                            f"line without a stop cannot be counted as zero risk")
            out[x.symbol] = out.get(x.symbol, 0.0) + r
        return out, ""

    def total_risk(self) -> Metric:
        """Every stop hit at once, no offsets. The worst case, and the number to size by
        when the correlation matrix is not trusted."""
        _, why = self._risk_vector()
        if why:
            return Metric(None, why)
        return Metric(float(sum(x.risk_dollars or 0.0 for x in self.lines)))

    def correlated_risk(self, correlation: CorrelationMatrix | None) -> Metric:
        """sqrt(r' C r) over signed per-instrument dollars at risk.

        Requires the matrix to be admissible and to cover every instrument in the book. An
        empty book has zero risk without needing a matrix; anything else needs one.
        """
        risk, why = self._risk_vector()
        if why:
            return Metric(None, why)
        if not risk:
            return Metric(0.0)
        if correlation is None:
            return Metric.unavailable(
                NO_CORRELATION, f"{len(risk)} instrument(s) in the book and no correlation "
                                f"matrix supplied; use total_risk() for the uncorrelated "
                                f"worst case")
        problem = correlation.problem()
        if problem:
            return Metric(None, problem)
        missing = correlation.missing(list(risk))
        if missing:
            return Metric.unavailable(
                CORRELATION_MISSING, f"no correlation row for {', '.join(missing)}; "
                                     f"refusing to assume zero")
        symbols = list(risk)
        r = np.asarray([risk[s] for s in symbols], dtype=float)
        c = correlation.submatrix(symbols)
        variance = float(r @ c @ r)
        # A PSD matrix cannot make this negative except by rounding; clamp the rounding,
        # never a real negative (which the PSD check above already refused).
        return Metric(math.sqrt(max(0.0, variance)))

    # -- the check ------------------------------------------------------------------------

    def check(self, limits: PortfolioLimits, *,
              correlation: CorrelationMatrix | None = None) -> list[Breach]:
        """Every configured limit that does not hold, each with a reason code.

        Unverifiable limits are breaches. The list is empty only when every configured
        limit was both computable and satisfied.
        """
        out: list[Breach] = []

        def scalar(code: str, name: str, limit: float | None, metric: Metric,
                   what: str) -> None:
            if limit is None:
                return
            if metric.value is None:
                out.append(Breach(UNVERIFIABLE, f"{name} is configured but {metric.reason}",
                                  limit, None, key=name))
            elif metric.value > limit:
                out.append(Breach(code, f"{what} {metric.value:,.2f} exceeds {limit:,.2f}",
                                  limit, metric.value))

        def buckets(code: str, limit: float | None, slices: dict[str, Slice],
                    what: str) -> None:
            if limit is None:
                return
            for key, s in sorted(slices.items()):
                if s.gross > limit:
                    out.append(Breach(code, f"{what} {key} gross {s.gross:,.2f} exceeds "
                                            f"{limit:,.2f}", limit, s.gross, key=key))

        scalar(GROSS_EXPOSURE, "max_gross_exposure", limits.max_gross_exposure,
               Metric(self.gross_exposure()), "gross exposure")
        scalar(NET_EXPOSURE, "max_net_exposure", limits.max_net_exposure,
               Metric(abs(self.net_exposure())), "absolute net exposure")
        scalar(LEVERAGE, "max_leverage", limits.max_leverage, self.leverage(), "leverage")
        buckets(INSTRUMENT_EXPOSURE, limits.max_instrument_exposure, self.by_instrument(),
                "instrument")
        buckets(STRATEGY_EXPOSURE, limits.max_strategy_exposure, self.by_strategy(),
                "strategy")
        buckets(VENUE_EXPOSURE, limits.max_venue_exposure, self.by_venue(), "venue")
        scalar(TOTAL_RISK, "max_total_risk", limits.max_total_risk, self.total_risk(),
               "total dollars at risk")
        scalar(CORRELATED_RISK, "max_correlated_risk", limits.max_correlated_risk,
               self.correlated_risk(correlation), "correlated dollars at risk")
        return out

    def describe(self) -> str:
        lev = self.leverage()
        leverage = f"{lev.value:.2f}x" if lev.value is not None else "n/a"
        return (f"{len(self.lines)} lines  gross ${self.gross_exposure():,.0f}  "
                f"net ${self.net_exposure():+,.0f}  leverage {leverage}")
