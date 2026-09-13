"""Trade analytics that return UNAVAILABLE rather than a number that was not measured.

Phase 14. `robustness.py` asks whether a strategy's P&L came from one path; this module
describes the trades themselves - the win rate, the expectancy, the excursions, the tails -
and its one design rule is that every field is either a measurement or an explicit refusal
carrying a reason. Nothing here is NaN, nothing is 0 where "not computable" is meant, and
nothing is estimated from a proxy when the thing itself was not recorded.

THE THREE REFUSALS THAT MATTER
------------------------------
MAE / MFE need the path. A trade's maximum adverse excursion is the worst mark it was held
through, and that is only known from marks observed while it was open. Given only entry and
exit prices it is UNAVAILABLE ("no intraday path recorded"), and it is NOT reconstructed from
the OHLC of the bars the trade overlapped: a bar's low is the low of the whole bar, and the
trade only saw it if it was open for the whole bar. A trade entered at 10:31:40 did not
experience the 10:31 bar's low printed at 10:31:05, and reporting that it did would overstate
every MAE by the part of the bar the trade was not in - which, on a one-minute store, is most
of the first and last bar of every short trade. Even a recorded path is a lower bound on the
true excursion at that path's resolution, and `METRIC_DOCS["mae"]` says so.

R multiples need the stop. `net_pnl / initial_risk` requires the risk that was actually on at
entry. Without a recorded stop distance the R multiple is UNAVAILABLE rather than derived from
the realised loss, the MAE or an ATR: each of those is a different quantity, and the first two
are circular.

Annualised ratios need a clock and a sample. Sharpe, Sortino and Calmar are stated on the
TRADE clock: per-trade net P&L, annualised by the realised number of trades per calendar year
between the first entry and the last exit. That is one convention among several and the
report carries it in `annualisation` rather than in a footnote. Under `min_trades_for_ratios`
(30) they are UNAVAILABLE: a Sharpe on twelve trades has a standard error near 0.3 on any
clock, and the number would be read as if it did not. A daily-clock Sharpe additionally needs
the number of sessions the strategy was LIVE, because a trade list cannot tell a session
traded flat from one that was never traded, and zero-filling versus dropping those sessions
moves the daily Sharpe by up to the square root of the traded fraction. Pass `trading_days`
to get it; without it `sharpe_daily` is UNAVAILABLE with that reason.

ARITHMETIC OR JUDGEMENT
-----------------------
Every field has an entry in `METRIC_DOCS` with the same `basis` split `robustness.py` uses:
"arithmetic" where the reading follows from the definition (a profit factor of 1.0 is
breakeven; negative skew means the losses are the large trades), "judgement" where somebody
has to decide how much is enough (how far above 1.0 a profit factor should be; how many
trades make a bucket trustworthy). The thin-bucket minimum is a judgement and is exposed as
one: buckets under `min_bucket_trades` are reported with `reliable=False` and an UNRELIABLE
note instead of being dropped or being printed like the others.

THE SENTINEL
------------
`Unavailable(reason)` is a frozen dataclass with no arithmetic. `report.sharpe * 2` on an
unavailable Sharpe raises TypeError, which is the point: a NaN would propagate silently into
whatever ranked the strategy, and a None would be caught by the next `or 0.0`. In JSON it is
`{"unavailable": reason}`, and `to_jsonable` refuses to serialise a non-finite float at all,
so the no-NaN invariant is enforced at the boundary and not merely intended.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, fields
from zoneinfo import ZoneInfo

import numpy as np

from quant_brain.core import stats
from quant_brain.research.robustness import (
    DEFAULT_BUCKETS,
    DEFAULT_TZ,
    Bucket,
    MetricDoc,
    drawdown_profile,
)

# =====================================================================================
# THE SENTINEL
# =====================================================================================


@dataclass(frozen=True)
class Unavailable:
    """A metric that could not honestly be computed, and why.

    No arithmetic, no ordering, no truthiness tricks: any attempt to use one as a number
    raises, which is what distinguishes it from the NaN it replaces. Compare with
    `multipletest.BootstrapTestResult`, which carries `pvalue=None` plus a `reason` - same
    idea, but here the refusal has to travel inside dicts and distributions, so it is a value.
    """

    reason: str

    def __post_init__(self) -> None:
        if not self.reason or not self.reason.strip():
            raise ValueError("Unavailable needs a reason; a bare refusal is as opaque as a NaN")

    def __str__(self) -> str:
        return f"UNAVAILABLE - {self.reason}"

    def to_json(self) -> dict[str, str]:
        return {"unavailable": self.reason}

    @classmethod
    def from_json(cls, value: object) -> Unavailable | None:
        """The sentinel back out of its serialised form, or None when `value` is not one."""
        if (isinstance(value, dict) and set(value) == {"unavailable"}
                and isinstance(value["unavailable"], str)):
            return cls(value["unavailable"])
        return None


Metric = float | Unavailable


def available(value: object) -> bool:
    """True when `value` is a real measurement rather than a refusal."""
    return not isinstance(value, Unavailable)


#: The reasons the tests pin, so a reworded refusal is a deliberate change.
NO_PATH = "no intraday path recorded"
NO_STOP = "no stop distance recorded"
NO_TRADES = "no trades"
NO_TRADING_DAYS = ("trading_days not supplied: a trade list cannot tell a session traded flat "
                   "from one never traded, and the daily clock needs to know how many there were")

#: Conventions, every one a judgement. Exposed as keyword arguments on `aggregate`.
MIN_TRADES_FOR_RATIOS = 30
MIN_BUCKET_TRADES = 20
CVAR_QUANTILE = 0.05
CALENDAR_DAYS_PER_YEAR = 365.25
SESSIONS_PER_YEAR = 252
#: Trades with no session or regime label land here rather than vanishing from the split,
#: for the reason `robustness.WARMUP` exists: a dropped row makes the shares stop adding up.
UNLABELLED = "unlabelled"
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# =====================================================================================
# TRADE RECORD
# =====================================================================================


class Direction(str, enum.Enum):
    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> int:
        return 1 if self is Direction.LONG else -1

    @classmethod
    def of(cls, signed_quantity: float) -> Direction:
        if signed_quantity == 0:
            raise ValueError("a zero quantity has no direction")
        return cls.LONG if signed_quantity > 0 else cls.SHORT


def _aware(when: dt.datetime, what: str) -> None:
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError(
            f"{what} is timezone-naive. Day-of-week and session buckets are wall-clock rules "
            "in an exchange timezone, and guessing which one a naive time is in is the "
            "off-by-an-hour class of bug this repository has already paid for (AUD-07).")


@dataclass(frozen=True)
class Trade:
    """One round trip, as recorded - never as inferred.

    P&L is DERIVED from the prices rather than stored beside them, so there is one source of
    truth: `gross_pnl = (exit - entry) * sign * size * multiplier`, and `net_pnl` subtracts
    `|commission| + |slippage|`, the same cost convention as `execution.Fill.cost()`.
    Slippage is therefore a dollar cost recorded separately, not something already inside the
    fill price; a record whose prices already include slippage should leave it at 0.

    `path` is the sequence of marks (prices) observed WHILE the trade was open, in time order,
    excluding the entry and exit prices, which are added at the ends. It is what MAE and MFE
    are computed from, and its absence makes them UNAVAILABLE. Do not fill it from bar lows
    and highs - see the module docstring.

    `stop_distance` is the initial stop in PRICE points, positive in either direction. It is
    what makes an R multiple meaningful; without it `r_multiple` is UNAVAILABLE.
    """

    entry_time: dt.datetime
    exit_time: dt.datetime
    entry_price: float
    exit_price: float
    direction: Direction
    size: float
    multiplier: float = 1.0
    commission: float = 0.0
    slippage: float = 0.0
    path: tuple[float, ...] = ()
    stop_distance: float | None = None
    session: str | None = None
    regime: str | None = None
    strategy_version: str | None = None
    parameter_hash: str | None = None
    symbol: str = ""
    tag: str = ""

    def __post_init__(self) -> None:
        _aware(self.entry_time, "entry_time")
        _aware(self.exit_time, "exit_time")
        if self.exit_time < self.entry_time:
            raise ValueError(f"exit_time {self.exit_time} precedes entry_time {self.entry_time}")
        object.__setattr__(self, "direction", Direction(self.direction))
        for name in ("entry_price", "exit_price", "size", "multiplier", "commission",
                     "slippage"):
            v = float(getattr(self, name))
            if not math.isfinite(v):
                raise ValueError(f"{name} is {v!r}; a trade record with a non-finite field is "
                                 "a hole in the sample, not a trade")
            object.__setattr__(self, name, v)
        if self.size <= 0:
            raise ValueError(f"size must be positive, got {self.size}; direction carries the "
                             "sign, as in execution.OrderIntent")
        if self.multiplier <= 0:
            raise ValueError(f"multiplier must be positive, got {self.multiplier}")
        path = tuple(float(p) for p in self.path)
        if any(not math.isfinite(p) for p in path):
            raise ValueError("path contains a non-finite mark")
        object.__setattr__(self, "path", path)
        if self.stop_distance is not None:
            sd = float(self.stop_distance)
            if not math.isfinite(sd) or sd <= 0:
                raise ValueError(f"stop_distance must be a positive price distance, got "
                                 f"{self.stop_distance!r}; pass None when no stop was recorded")
            object.__setattr__(self, "stop_distance", sd)

    # -- money ------------------------------------------------------------------------------

    @property
    def point_value(self) -> float:
        """Dollars per one point of price movement on this trade's size."""
        return self.size * self.multiplier

    @property
    def gross_pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.direction.sign * self.point_value

    @property
    def cost(self) -> float:
        """Frictional cost in dollars, always non-negative. Matches `Fill.cost()`."""
        return abs(self.commission) + abs(self.slippage)

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.cost

    @property
    def won(self) -> bool:
        return self.net_pnl > 0

    @property
    def lost(self) -> bool:
        return self.net_pnl < 0

    # -- time -------------------------------------------------------------------------------

    @property
    def holding_time(self) -> dt.timedelta:
        return self.exit_time - self.entry_time

    @property
    def holding_seconds(self) -> float:
        return self.holding_time.total_seconds()

    @property
    def day_of_week(self) -> str:
        """Weekday of the ENTRY, in the entry time's own timezone."""
        return WEEKDAYS[self.entry_time.weekday()]

    # -- excursions -------------------------------------------------------------------------

    @property
    def excursions(self) -> tuple[float, ...] | Unavailable:
        """Gross P&L at every recorded mark: entry (0), each path mark, exit.

        Gross rather than net because costs are not path-dependent: the trade's worst moment
        is the same whether or not a commission was later charged.
        """
        if not self.path:
            return Unavailable(NO_PATH)
        marks = (self.entry_price, *self.path, self.exit_price)
        k = self.direction.sign * self.point_value
        return tuple((m - self.entry_price) * k for m in marks)

    @property
    def mae(self) -> Metric:
        """Maximum adverse excursion in dollars, >= 0. UNAVAILABLE without a path."""
        ex = self.excursions
        if isinstance(ex, Unavailable):
            return ex
        return max(0.0, -min(ex))

    @property
    def mfe(self) -> Metric:
        """Maximum favourable excursion in dollars, >= 0. UNAVAILABLE without a path."""
        ex = self.excursions
        if isinstance(ex, Unavailable):
            return ex
        return max(0.0, max(ex))

    # -- risk -------------------------------------------------------------------------------

    @property
    def initial_risk(self) -> Metric:
        """Dollars at risk to the recorded stop. UNAVAILABLE without a stop distance."""
        if self.stop_distance is None:
            return Unavailable(NO_STOP)
        return self.stop_distance * self.point_value

    @property
    def r_multiple(self) -> Metric:
        """Net P&L as a multiple of the initial risk. UNAVAILABLE without a stop distance.

        Not derived from the realised loss (circular: every full-stop loss would be exactly
        -1R by construction, and every other trade's R would be relative to a stop it did not
        have) nor from MAE or a volatility proxy (different quantities). R is the risk that
        was actually on at entry, or it is nothing.
        """
        risk = self.initial_risk
        if isinstance(risk, Unavailable):
            return risk
        return self.net_pnl / risk

    def metrics(self) -> dict[str, object]:
        """Every per-trade figure, JSON-ready through `to_jsonable`."""
        return {
            "symbol": self.symbol,
            "tag": self.tag,
            "direction": self.direction.value,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "size": self.size,
            "multiplier": self.multiplier,
            "gross_pnl": self.gross_pnl,
            "commission": abs(self.commission),
            "slippage": abs(self.slippage),
            "net_pnl": self.net_pnl,
            "holding_seconds": self.holding_seconds,
            "mae": self.mae,
            "mfe": self.mfe,
            "path_marks": len(self.path),
            "initial_risk": self.initial_risk,
            "r_multiple": self.r_multiple,
            "session": self.session,
            "regime": self.regime,
            "day_of_week": self.day_of_week,
            "strategy_version": self.strategy_version,
            "parameter_hash": self.parameter_hash,
        }


def session_of(when: dt.datetime, *, buckets: Sequence[Bucket] = DEFAULT_BUCKETS,
               tz: str = DEFAULT_TZ, other: str = "other") -> str:
    """The clock bucket a timestamp falls in, on `robustness`'s FIXED clock.

    Offered so a `Trade.session` label can be produced without choosing boundaries from the
    data; choosing them from the data turns the per-session split into a selection that needs
    multiplicity accounting (see `robustness`, "two things that are not regime labels").
    """
    _aware(when, "when")
    local = when.astimezone(ZoneInfo(tz))
    minute = local.hour * 60 + local.minute
    for b in buckets:
        if bool(b.contains_minute(minute)):
            return b.name
    return other


# =====================================================================================
# REPORT STRUCTURES
# =====================================================================================


@dataclass(frozen=True)
class Distribution:
    """Summary of a sample of per-trade values. Percentiles are numpy's linear interpolation.

    Only ever built from a non-empty sample; the parent field is UNAVAILABLE otherwise, so a
    reader never meets a distribution with n = 0 and a mean of something.
    """

    n: int
    mean: float
    min: float
    p25: float
    median: float
    p75: float
    max: float


@dataclass(frozen=True)
class BucketStats:
    """One slice of the trade list: a direction, a session, a regime, a weekday.

    `reliable` is the judgement `min_bucket_trades` encodes, made visible rather than acted
    on: a thin bucket is still reported - deleting it would hide where the trades were - but
    it carries the UNRELIABLE note so it cannot be read as if it were solid.
    """

    n: int
    share_of_trades: float
    total_net: float
    share_of_net: Metric
    expectancy: float
    win_rate: float
    profit_factor: Metric
    reliable: bool
    note: str


@dataclass(frozen=True)
class Annualisation:
    """The clock every annualised ratio in the report assumes, stated in the report."""

    span_days: Metric
    trades_per_year: Metric
    trading_days: int | None
    trade_clock: str = (
        "per-trade net P&L in dollars; mean / sd scaled by sqrt(trades_per_year), where "
        "trades_per_year = n / (calendar days from first entry to last exit / 365.25); "
        "treats trades as the sampling unit and assumes they do not overlap")
    daily_clock: str = (
        "net P&L summed by exit date, zero-filled to `trading_days` sessions, scaled by "
        "sqrt(252); only available when trading_days is supplied")


@dataclass(frozen=True)
class Config:
    """The conventions this report was built under. Inputs, not metrics."""

    min_trades_for_ratios: int = MIN_TRADES_FOR_RATIOS
    min_bucket_trades: int = MIN_BUCKET_TRADES
    cvar_quantile: float = CVAR_QUANTILE
    trading_days: int | None = None

    def __post_init__(self) -> None:
        if self.min_trades_for_ratios < 2:
            raise ValueError("min_trades_for_ratios must be at least 2; a standard deviation "
                             "needs two observations")
        if self.min_bucket_trades < 1:
            raise ValueError("min_bucket_trades must be at least 1")
        if not (0.0 < self.cvar_quantile < 1.0):
            raise ValueError(f"cvar_quantile must lie in (0, 1), got {self.cvar_quantile}")
        if self.trading_days is not None and self.trading_days < 1:
            raise ValueError(f"trading_days must be positive when supplied, got "
                             f"{self.trading_days}")


@dataclass(frozen=True)
class TradeReport:
    """Everything `aggregate` measures. Every field is a value or an `Unavailable`.

    Interpretations and the arithmetic/judgement split are in `METRIC_DOCS`; `readings()`
    pairs them with the values. Trade-ordered statistics (drawdowns, streaks, recovery) are
    computed in EXIT-time order, because that is when P&L is realised.
    """

    n: int
    n_winners: int
    n_losers: int
    n_flat: int
    win_rate: Metric
    loss_rate: Metric
    expectancy: Metric
    expectancy_t: Metric
    median_trade: Metric
    average_winner: Metric
    average_loser: Metric
    largest_winner: Metric
    largest_loser: Metric
    total_gross: float
    total_net: float
    total_costs: float
    gross_profit: float
    gross_loss: float
    profit_factor: Metric
    payoff_ratio: Metric
    breakeven_win_rate: Metric
    max_drawdown: Metric
    average_drawdown: Metric
    n_drawdowns: int
    recovery_trades: Metric
    recovery_seconds: Metric
    longest_underwater_trades: Metric
    underwater_fraction: Metric
    sharpe: Metric
    sortino: Metric
    calmar: Metric
    sharpe_daily: Metric
    sortino_daily: Metric
    volatility: Metric
    skew: Metric
    kurtosis: Metric
    cvar: Metric
    cvar_quantile: float
    cvar_trades: int
    longest_win_streak: int
    longest_loss_streak: int
    expectancy_r: Metric
    path_coverage: Metric
    stop_coverage: Metric
    holding_time: Distribution | Unavailable
    mae: Distribution | Unavailable
    mfe: Distribution | Unavailable
    r_multiple: Distribution | Unavailable
    by_direction: dict[str, BucketStats]
    by_session: dict[str, BucketStats]
    by_regime: dict[str, BucketStats]
    by_weekday: dict[str, BucketStats]
    annualisation: Annualisation
    config: Config


# =====================================================================================
# AGGREGATION
# =====================================================================================


def aggregate(trades: Sequence[Trade], *,
              min_trades_for_ratios: int = MIN_TRADES_FOR_RATIOS,
              min_bucket_trades: int = MIN_BUCKET_TRADES,
              cvar_quantile: float = CVAR_QUANTILE,
              trading_days: int | None = None) -> TradeReport:
    """The full battery over a list of trades. Deterministic; input order is irrelevant.

    An empty list is not an error: an unattended loop can legitimately produce a session with
    no trades, and the honest report of that is counts of zero, totals of zero (a sum over
    nothing IS zero) and every rate, mean and ratio UNAVAILABLE with the reason "no trades".

    `trading_days` is the number of sessions the strategy was live over the sample, which
    unlocks the daily-clock Sharpe and Sortino. It must be at least the number of distinct
    exit dates; fewer is a caller error and raises.
    """
    cfg = Config(min_trades_for_ratios=min_trades_for_ratios,
                 min_bucket_trades=min_bucket_trades, cvar_quantile=cvar_quantile,
                 trading_days=trading_days)
    ordered = sorted(trades, key=lambda t: (t.exit_time, t.entry_time))
    n = len(ordered)
    x = np.array([t.net_pnl for t in ordered], dtype=float)
    wins, losses = x[x > 0], x[x < 0]
    n_w, n_l = len(wins), len(losses)
    total_net = float(x.sum())
    gross_profit, gross_loss = float(wins.sum()), float(-losses.sum())

    ann = _annualisation(ordered, cfg.trading_days)
    daily = _daily_pnl(ordered)
    if cfg.trading_days is not None and cfg.trading_days < len(daily):
        raise ValueError(f"trading_days={cfg.trading_days} is fewer than the {len(daily)} "
                         "distinct exit dates in the trade list")

    average_winner = _mean(wins, "no winning trades")
    average_loser = _mean(losses, "no losing trades")
    payoff = _div(average_winner, _abs(average_loser), zero="average loser is zero")
    breakeven = (Unavailable(payoff.reason) if isinstance(payoff, Unavailable)
                 else 1.0 / (1.0 + payoff))
    if n == 0:
        profit_factor: Metric = Unavailable(NO_TRADES)
    elif gross_loss == 0:
        profit_factor = Unavailable("no losing trades; a profit factor is a ratio against "
                                    "zero gross loss")
    else:
        profit_factor = gross_profit / gross_loss

    dd = _drawdowns(ordered, x)
    cvar, cvar_k = _cvar(x, cfg.cvar_quantile)

    with_path = [t for t in ordered if t.path]
    with_stop = [t for t in ordered if t.stop_distance is not None]
    r_values = _floats(t.r_multiple for t in ordered)
    if n == 0:
        expectancy_r: Metric = Unavailable(NO_TRADES)
    elif len(with_stop) < n:
        expectancy_r = Unavailable(
            f"{n - len(with_stop)} of {n} trades have {NO_STOP}; an R expectancy over the "
            "remainder would silently drop the trades most likely to have been unmanaged")
    else:
        expectancy_r = float(np.mean(r_values))

    split = _splitter(ordered, x, total_net, cfg.min_bucket_trades)

    return TradeReport(
        n=n,
        n_winners=n_w,
        n_losers=n_l,
        n_flat=n - n_w - n_l,
        win_rate=(n_w / n if n else Unavailable(NO_TRADES)),
        loss_rate=(n_l / n if n else Unavailable(NO_TRADES)),
        expectancy=_mean(x, NO_TRADES),
        expectancy_t=_expectancy_t(x),
        median_trade=(float(np.median(x)) if n else Unavailable(NO_TRADES)),
        average_winner=average_winner,
        average_loser=average_loser,
        largest_winner=(float(wins.max()) if n_w else Unavailable("no winning trades")),
        largest_loser=(float(losses.min()) if n_l else Unavailable("no losing trades")),
        total_gross=float(sum(t.gross_pnl for t in ordered)),
        total_net=total_net,
        total_costs=float(sum(t.cost for t in ordered)),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        payoff_ratio=payoff,
        breakeven_win_rate=breakeven,
        max_drawdown=dd.max_drawdown,
        average_drawdown=dd.average_drawdown,
        n_drawdowns=dd.n_drawdowns,
        recovery_trades=dd.recovery_trades,
        recovery_seconds=dd.recovery_seconds,
        longest_underwater_trades=dd.longest_underwater,
        underwater_fraction=dd.underwater_fraction,
        sharpe=_sharpe(x, cfg, ann),
        sortino=_sortino(x, cfg, ann),
        calmar=_calmar(total_net, dd.max_drawdown, n, cfg, ann),
        sharpe_daily=_sharpe_daily(daily, n, cfg),
        sortino_daily=_sortino_daily(daily, n, cfg),
        volatility=_volatility(x),
        skew=_skew(x),
        kurtosis=_kurtosis(x),
        cvar=cvar,
        cvar_quantile=cfg.cvar_quantile,
        cvar_trades=cvar_k,
        longest_win_streak=_longest_run(x > 0),
        longest_loss_streak=_longest_run(x < 0),
        expectancy_r=expectancy_r,
        path_coverage=(len(with_path) / n if n else Unavailable(NO_TRADES)),
        stop_coverage=(len(with_stop) / n if n else Unavailable(NO_TRADES)),
        holding_time=_distribution([t.holding_seconds for t in ordered], NO_TRADES),
        mae=_distribution(_floats(t.mae for t in ordered), f"{NO_PATH} on any trade"),
        mfe=_distribution(_floats(t.mfe for t in ordered), f"{NO_PATH} on any trade"),
        r_multiple=_distribution(r_values, f"{NO_STOP} on any trade"),
        by_direction=split(lambda t: t.direction.value, order=("long", "short")),
        by_session=split(lambda t: t.session),
        by_regime=split(lambda t: t.regime),
        by_weekday=split(lambda t: t.day_of_week, order=WEEKDAYS),
        annualisation=ann,
        config=cfg,
    )


# -- small arithmetic with refusals -----------------------------------------------------------


def _mean(a: np.ndarray, reason: str) -> Metric:
    return float(a.mean()) if len(a) else Unavailable(reason)


def _abs(v: Metric) -> Metric:
    return v if isinstance(v, Unavailable) else abs(v)


def _div(num: Metric, den: Metric, *, zero: str) -> Metric:
    if isinstance(num, Unavailable):
        return num
    if isinstance(den, Unavailable):
        return den
    if den == 0:
        return Unavailable(zero)
    return num / den


def _floats(values: Iterable[Metric]) -> list[float]:
    return [v for v in values if not isinstance(v, Unavailable)]


def _longest_run(flags: np.ndarray) -> int:
    best = run = 0
    for f in flags.tolist():
        run = run + 1 if f else 0
        best = max(best, run)
    return best


def _distribution(values: Sequence[float], none_reason: str) -> Distribution | Unavailable:
    a = np.asarray(values, dtype=float)
    if not len(a):
        return Unavailable(none_reason)
    q = np.percentile(a, [25.0, 50.0, 75.0])
    return Distribution(n=int(len(a)), mean=float(a.mean()), min=float(a.min()),
                        p25=float(q[0]), median=float(q[1]), p75=float(q[2]),
                        max=float(a.max()))


# -- significance, moments, tails -----------------------------------------------------------


def _expectancy_t(x: np.ndarray) -> Metric:
    """HAC t of the mean trade. Newey-West with the automatic lag, because consecutive
    trades share a session and a regime and are not independent draws."""
    n = len(x)
    if n < 3:
        return Unavailable(f"{n} trade(s); a HAC t-statistic needs at least 3")
    t = stats.tstat_hac(x)
    if not math.isfinite(t.t):
        return Unavailable("zero variance across trades")
    return float(t.t)


def _volatility(x: np.ndarray) -> Metric:
    if len(x) < 2:
        return Unavailable(f"{len(x)} trade(s); a standard deviation needs at least 2")
    return float(x.std(ddof=1))


def _central(x: np.ndarray, k: int) -> float:
    d = x - x.mean()
    return float(np.mean(d ** k))


def _skew(x: np.ndarray) -> Metric:
    """Bias-corrected sample skewness (the G1 pandas reports)."""
    n = len(x)
    if n < 3:
        return Unavailable(f"{n} trade(s); sample skewness needs at least 3")
    m2 = _central(x, 2)
    if m2 <= 0:
        return Unavailable("zero variance across trades")
    g1 = _central(x, 3) / m2 ** 1.5
    return float(g1 * math.sqrt(n * (n - 1)) / (n - 2))


def _kurtosis(x: np.ndarray) -> Metric:
    """Bias-corrected EXCESS kurtosis (the G2 pandas reports): 0 is Gaussian."""
    n = len(x)
    if n < 4:
        return Unavailable(f"{n} trade(s); sample kurtosis needs at least 4")
    m2 = _central(x, 2)
    if m2 <= 0:
        return Unavailable("zero variance across trades")
    g2 = _central(x, 4) / m2 ** 2 - 3.0
    return float(((n + 1) * g2 + 6.0) * (n - 1) / ((n - 2) * (n - 3)))


def _cvar(x: np.ndarray, q: float) -> tuple[Metric, int]:
    """Mean net P&L of the worst `q` fraction of trades (signed, so a loss is negative), and
    how many trades that tail holds. Refused until one whole trade lies in the tail."""
    n = len(x)
    need = math.ceil(1.0 / q)
    if n < need:
        return Unavailable(f"{n} trade(s) cannot resolve the {q:g} tail; at least {need} are "
                           "needed for one whole trade to lie in it"), 0
    k = math.ceil(q * n)
    return float(np.sort(x)[:k].mean()), k


# -- drawdowns ------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Drawdowns:
    max_drawdown: Metric
    average_drawdown: Metric
    n_drawdowns: int
    recovery_trades: Metric
    recovery_seconds: Metric
    longest_underwater: Metric
    underwater_fraction: Metric


def _episodes(x: np.ndarray) -> list[tuple[int, int, int | None, float]]:
    """(start, trough, recovery index or None, depth) for each spell below the running peak.

    Peak starts at zero, as in `robustness.drawdown_profile`: a strategy that loses on its
    first trade is in drawdown from its first trade. Recovery is the index of the trade that
    regains the peak; None when the sample ends first.
    """
    equity = np.cumsum(x)
    peak = np.maximum.accumulate(np.maximum(equity, 0.0))
    under = (equity < peak).tolist()
    gap = peak - equity
    out: list[tuple[int, int, int | None, float]] = []
    i, n = 0, len(x)
    while i < n:
        if not under[i]:
            i += 1
            continue
        start = i
        while i < n and under[i]:
            i += 1
        seg = gap[start:i]
        trough = start + int(np.argmax(seg))
        out.append((start, trough, (i if i < n else None), float(seg.max())))
    return out


def _drawdowns(ordered: Sequence[Trade], x: np.ndarray) -> _Drawdowns:
    if not len(x):
        none = Unavailable(NO_TRADES)
        return _Drawdowns(none, none, 0, none, none, none, none)
    prof = drawdown_profile(x)
    eps = _episodes(x)
    if not eps:
        flat = Unavailable("equity never fell below its running peak")
        return _Drawdowns(0.0, flat, 0, flat, flat, float(prof["longest_underwater"]),
                          float(prof["underwater_fraction"]))
    deepest = max(eps, key=lambda e: e[3])          # first on ties: max() keeps the first
    _, trough, recovery, _ = deepest
    if recovery is None:
        open_reason = Unavailable("the maximum drawdown had not recovered by the last trade")
        rec_trades: Metric = open_reason
        rec_seconds: Metric = open_reason
    else:
        rec_trades = float(recovery - trough)
        rec_seconds = (ordered[recovery].exit_time - ordered[trough].exit_time).total_seconds()
    return _Drawdowns(
        max_drawdown=float(prof["max_drawdown"]),
        average_drawdown=float(np.mean([e[3] for e in eps])),
        n_drawdowns=len(eps),
        recovery_trades=rec_trades,
        recovery_seconds=rec_seconds,
        longest_underwater=float(prof["longest_underwater"]),
        underwater_fraction=float(prof["underwater_fraction"]),
    )


# -- clocks and annualised ratios -----------------------------------------------------------


def _annualisation(ordered: Sequence[Trade], trading_days: int | None) -> Annualisation:
    if not ordered:
        return Annualisation(Unavailable(NO_TRADES), Unavailable(NO_TRADES), trading_days)
    first = min(t.entry_time for t in ordered)
    last = max(t.exit_time for t in ordered)
    span = (last - first).total_seconds() / 86400.0
    if span <= 0:
        tpy: Metric = Unavailable("the sample spans no time (first entry equals last exit), "
                                  "so there is nothing to annualise over")
    else:
        tpy = len(ordered) / (span / CALENDAR_DAYS_PER_YEAR)
    return Annualisation(span_days=span, trades_per_year=tpy, trading_days=trading_days)


def _daily_pnl(ordered: Sequence[Trade]) -> np.ndarray:
    """Net P&L summed by the exit's calendar date in its own timezone, one entry per traded
    day, in date order."""
    sums: dict[dt.date, float] = {}
    for t in ordered:
        d = t.exit_time.date()
        sums[d] = sums.get(d, 0.0) + t.net_pnl
    return np.array([sums[d] for d in sorted(sums)], dtype=float)


def _too_few(n: int, cfg: Config) -> Unavailable | None:
    if n < cfg.min_trades_for_ratios:
        return Unavailable(f"{n} trade(s) is below the {cfg.min_trades_for_ratios}-trade "
                           "minimum for an annualised ratio")
    return None


def _sharpe(x: np.ndarray, cfg: Config, ann: Annualisation) -> Metric:
    few = _too_few(len(x), cfg)
    if few is not None:
        return few
    if isinstance(ann.trades_per_year, Unavailable):
        return ann.trades_per_year
    sd = float(x.std(ddof=1))
    if sd <= 0:
        return Unavailable("zero variance across trades")
    return float(x.mean()) / sd * math.sqrt(ann.trades_per_year)


def _sortino(x: np.ndarray, cfg: Config, ann: Annualisation) -> Metric:
    few = _too_few(len(x), cfg)
    if few is not None:
        return few
    if isinstance(ann.trades_per_year, Unavailable):
        return ann.trades_per_year
    downside = math.sqrt(float(np.mean(np.minimum(x, 0.0) ** 2)))
    if downside <= 0:
        return Unavailable("no losing trades; the downside deviation is zero")
    return float(x.mean()) / downside * math.sqrt(ann.trades_per_year)


def _calmar(total_net: float, max_dd: Metric, n: int, cfg: Config,
            ann: Annualisation) -> Metric:
    few = _too_few(n, cfg)
    if few is not None:
        return few
    if isinstance(ann.span_days, Unavailable):
        return ann.span_days
    if ann.span_days <= 0:
        return Unavailable("the sample spans no time; nothing to annualise over")
    if isinstance(max_dd, Unavailable):
        return max_dd
    if max_dd <= 0:
        return Unavailable("equity never fell below its running peak; Calmar is a ratio "
                           "against zero drawdown")
    annualised = total_net * CALENDAR_DAYS_PER_YEAR / ann.span_days
    return annualised / max_dd


def _sharpe_daily(daily: np.ndarray, n: int, cfg: Config) -> Metric:
    few = _too_few(n, cfg)
    if few is not None:
        return few
    if cfg.trading_days is None:
        return Unavailable(NO_TRADING_DAYS)
    days = cfg.trading_days
    if days < 2:
        return Unavailable("one session; a daily standard deviation needs at least 2")
    # Zero-filled moments need only the traded days' P&L and the total count: the untraded
    # sessions contribute 0 to every sum, so WHICH days they were does not matter here.
    mean = float(daily.sum()) / days
    var = (float((daily ** 2).sum()) - days * mean ** 2) / (days - 1)
    if var <= 0:
        return Unavailable("zero variance across sessions")
    return mean / math.sqrt(var) * math.sqrt(SESSIONS_PER_YEAR)


def _sortino_daily(daily: np.ndarray, n: int, cfg: Config) -> Metric:
    few = _too_few(n, cfg)
    if few is not None:
        return few
    if cfg.trading_days is None:
        return Unavailable(NO_TRADING_DAYS)
    days = cfg.trading_days
    mean = float(daily.sum()) / days
    downside = math.sqrt(float((np.minimum(daily, 0.0) ** 2).sum()) / days)
    if downside <= 0:
        return Unavailable("no losing session; the downside deviation is zero")
    return mean / downside * math.sqrt(SESSIONS_PER_YEAR)


# -- splits ---------------------------------------------------------------------------------


def _splitter(ordered: Sequence[Trade], x: np.ndarray, total_net: float,
              min_bucket: int) -> Callable[..., dict[str, BucketStats]]:
    n = len(ordered)

    def split(key: Callable[[Trade], str | None], *,
              order: Sequence[str] | None = None) -> dict[str, BucketStats]:
        groups: dict[str, list[int]] = {}
        for i, t in enumerate(ordered):
            groups.setdefault(key(t) or UNLABELLED, []).append(i)
        names = sorted(groups)
        if order is not None:
            names = [k for k in order if k in groups] + [k for k in names if k not in order]
        out: dict[str, BucketStats] = {}
        for name in names:
            sel = x[groups[name]]
            wins, losses = sel[sel > 0], sel[sel < 0]
            gl = float(-losses.sum())
            pf: Metric = (float(wins.sum()) / gl if gl > 0
                          else Unavailable("no losing trades in this bucket"))
            share: Metric = (float(sel.sum()) / total_net if total_net > 0
                             else Unavailable("whole-sample net is not positive; a share "
                                              "against it is not a share"))
            k = len(sel)
            out[name] = BucketStats(
                n=k,
                share_of_trades=k / n,
                total_net=float(sel.sum()),
                share_of_net=share,
                expectancy=float(sel.mean()),
                win_rate=float((sel > 0).mean()),
                profit_factor=pf,
                reliable=k >= min_bucket,
                note=("" if k >= min_bucket
                      else f"UNRELIABLE: {k} trade(s), below the {min_bucket}-trade minimum"),
            )
        return out

    return split


# =====================================================================================
# JSON
# =====================================================================================


def to_jsonable(obj: object) -> object:
    """Plain JSON types only. `Unavailable` becomes {"unavailable": reason}.

    Raises on a non-finite float rather than emitting NaN or null: a NaN reaching this
    boundary is a bug in this module, and JSON's `NaN` token is exactly the silent value the
    sentinel exists to replace.
    """
    if isinstance(obj, Unavailable):
        return obj.to_json()
    if isinstance(obj, bool) or obj is None or isinstance(obj, str | int):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"non-finite value {obj!r} reached the report boundary; every "
                             "metric must be a number or an Unavailable")
        return obj
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return to_jsonable(float(obj))
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, dt.datetime | dt.date):
        return obj.isoformat()
    if isinstance(obj, dt.timedelta):
        return obj.total_seconds()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [to_jsonable(v) for v in obj]
    raise TypeError(f"cannot serialise {type(obj).__name__} into a report")


def report(trades: Sequence[Trade], *,
           min_trades_for_ratios: int = MIN_TRADES_FOR_RATIOS,
           min_bucket_trades: int = MIN_BUCKET_TRADES,
           cvar_quantile: float = CVAR_QUANTILE,
           trading_days: int | None = None) -> dict[str, object]:
    """`aggregate` as a JSON-serialisable dict that round-trips through `json`."""
    out = to_jsonable(aggregate(trades, min_trades_for_ratios=min_trades_for_ratios,
                                min_bucket_trades=min_bucket_trades,
                                cvar_quantile=cvar_quantile, trading_days=trading_days))
    if not isinstance(out, dict):                                    # pragma: no cover
        raise TypeError("aggregate did not serialise to a dict")
    return out


def trade_records(trades: Sequence[Trade]) -> list[dict[str, object]]:
    """Per-trade metrics, one JSON-ready dict each, in the input order."""
    out: list[dict[str, object]] = []
    for t in trades:
        row = to_jsonable(t.metrics())
        if not isinstance(row, dict):                                # pragma: no cover
            raise TypeError("trade metrics did not serialise to a dict")
        out.append(row)
    return out


# =====================================================================================
# INTERPRETATION
# =====================================================================================


def _doc(metric: str, interpretation: str, concern: str, basis: str) -> MetricDoc:
    return MetricDoc(metric, interpretation, concern, basis)


_LOWER_BOUND = ("Every excursion is a lower bound on the true one at the path's resolution: "
                "a minute path misses what happened inside the minute. It is still the only "
                "honest number - an OHLC reconstruction would be an upper bound of a "
                "different quantity, the bar's range, which the trade need not have seen.")

METRIC_DOCS: dict[str, MetricDoc] = {d.metric: d for d in (
    _doc("n", "Trades in the sample.",
         "Under about thirty every ratio below is dominated by sampling noise, which is why "
         "the annualised ones refuse there - but thirty is a convention, not a derived "
         "number, and `min_trades_for_ratios` says so by being an argument.", "judgement"),
    _doc("n_winners", "Trades with positive net P&L.", "The numerator of `win_rate`.",
         "arithmetic"),
    _doc("n_losers", "Trades with negative net P&L.", "The numerator of `loss_rate`.",
         "arithmetic"),
    _doc("n_flat", "Trades that netted exactly zero.",
         "Counted in neither rate and breaking both streaks, because the account neither "
         "made nor lost money on them. Many of them usually means costs are being ignored.",
         "arithmetic"),
    _doc("win_rate", "Winning trades over all trades.",
         "Meaningless alone. The breakeven rate is 1 / (1 + payoff_ratio), an identity, and "
         "the reading is the gap between the two - reported as `breakeven_win_rate`.",
         "arithmetic"),
    _doc("loss_rate", "Losing trades over all trades.",
         "1 - win_rate - flat share. Reported so the flat share is visible.", "arithmetic"),
    _doc("expectancy", "Mean net P&L per trade, in dollars.",
         "The sign is the whole reading; how far from zero it is relative to its noise is "
         "`expectancy_t`. Per trade, not per unit of risk - `expectancy_r` is that.",
         "arithmetic"),
    _doc("expectancy_t", "HAC (Newey-West, automatic lag) t-statistic of the mean trade.",
         "A measurement of noise, not a verdict. It is a t on ONE specification; read "
         "against `stats.bonferroni_threshold` for the number of specifications the ledger "
         "says were tried (AUD-19), never against 1.96 alone.", "judgement"),
    _doc("median_trade", "Median net P&L per trade.",
         "A median well below the mean says the expectancy is carried by a few large "
         "winners - the trade-level version of `robustness.days_to_zero`.", "arithmetic"),
    _doc("average_winner", "Mean net P&L of winning trades.", "Numerator of the payoff ratio.",
         "arithmetic"),
    _doc("average_loser", "Mean net P&L of losing trades, negative.",
         "Compare with the intended stop: an average loser much larger than one R means the "
         "stops are not being honoured, or slippage through them is.", "arithmetic"),
    _doc("largest_winner", "Best single trade, net.", "Read through `median_trade`.",
         "arithmetic"),
    _doc("largest_loser", "Worst single trade, net.",
         "Against the stop distance this is the slippage-through-the-stop figure; against "
         "the account it is the number a prop firm's daily loss limit is tested by.",
         "arithmetic"),
    _doc("total_gross", "Sum of gross P&L before commission and slippage.",
         "The difference from `total_net` is what the cost model took.", "arithmetic"),
    _doc("total_net", "Sum of net P&L.", "The headline, and the least informative number here.",
         "arithmetic"),
    _doc("total_costs", "Sum of commission and slippage, positive.",
         "Costs close to the gross edge make the net a small difference of two large "
         "numbers, which is a sensitivity statement (S-31 was this).", "arithmetic"),
    _doc("gross_profit", "Sum of winning trades' net P&L.", "Numerator of the profit factor.",
         "arithmetic"),
    _doc("gross_loss", "Sum of losing trades' net P&L, as a positive number.",
         "Denominator of the profit factor.", "arithmetic"),
    _doc("profit_factor", "gross_profit / gross_loss.",
         "1.0 is breakeven and that reading is arithmetic; how far above 1.0 is 'enough' is "
         "a judgement that depends on the sample size and the cost model, and the common "
         "1.5 is folklore. UNAVAILABLE with no losing trades rather than infinite.",
         "judgement"),
    _doc("payoff_ratio", "average_winner / |average_loser|.",
         "Read with `win_rate` through `breakeven_win_rate`. Alone it distinguishes a "
         "trend profile (high payoff, low hit rate) from a mean-reversion one, not good from "
         "bad.", "arithmetic"),
    _doc("breakeven_win_rate", "1 / (1 + payoff_ratio): the hit rate at which this payoff "
         "profile nets zero.",
         "An identity. The margin between the realised win rate and this is the edge in hit "
         "rate terms; a margin of a few points on a hundred trades is inside the noise.",
         "arithmetic"),
    _doc("max_drawdown", "Deepest fall of cumulative net P&L below its running peak, peak "
         "starting at zero, in exit-time order.",
         "Compare with the account's own limit, not with a percentage. The trade sequence "
         "cannot see intraday marks, so this is a lower bound on the drawdown a prop-firm "
         "MLL would have measured; `twin` prices that properly.", "arithmetic"),
    _doc("average_drawdown", "Mean depth over drawdown episodes (a spell below the peak "
         "from first trade under to the trade that regains it).",
         "Read against `max_drawdown`: a maximum far above the average is one bad episode, "
         "which is the concentration story on the loss side.", "arithmetic"),
    _doc("n_drawdowns", "Number of drawdown episodes.",
         "Many shallow episodes and a high `underwater_fraction` is a choppy equity curve; "
         "few deep ones is a strategy whose losses cluster.", "arithmetic"),
    _doc("recovery_trades", "Trades from the trough of the maximum drawdown to the trade "
         "that regained the prior peak.",
         "UNAVAILABLE when it had not recovered by the end of the sample, which is itself "
         "the finding. Time, not depth, ends most live deployments.", "arithmetic"),
    _doc("recovery_seconds", "Same, in wall-clock seconds between the two exits.",
         "The trade count is the statistic; this is what the account holder lived through.",
         "arithmetic"),
    _doc("longest_underwater_trades", "Longest run of trades spent below a prior peak.",
         "As `robustness.longest_underwater`, on the trade clock.", "arithmetic"),
    _doc("underwater_fraction", "Fraction of trades closed below a prior peak.",
         "Near 1.0 with a positive total is a late run-up, the pattern most easily produced "
         "by chance.", "arithmetic"),
    _doc("sharpe", "Mean / sd of per-trade net P&L, annualised on the TRADE clock: scaled "
         "by sqrt(trades per calendar year) over the span first entry to last exit.",
         "Stated so it can be disagreed with. Not comparable to a daily-clock Sharpe, and "
         "inflated when trades overlap (the P&L is then double counted as independent). "
         "What counts as good is a convention; UNAVAILABLE under `min_trades_for_ratios`.",
         "judgement"),
    _doc("sortino", "Mean / downside deviation (root mean square of losses, over ALL "
         "trades) of per-trade net P&L, same annualisation as `sharpe`.",
         "Same caveats as `sharpe`. UNAVAILABLE with no losing trade: a zero downside "
         "deviation is not an infinite ratio, it is a sample with no losses yet.",
         "judgement"),
    _doc("calmar", "Annualised net P&L (total * 365.25 / span days) over max drawdown.",
         "Calendar-clock numerator, trade-clock denominator, both stated. Highly sensitive "
         "to the single worst episode and to the span; a short sample annualises a few "
         "weeks' P&L into a year's.", "judgement"),
    _doc("sharpe_daily", "Mean / sd of net P&L per session, sessions with no exit counted as "
         "zero, scaled by sqrt(252). Requires `trading_days`.",
         "The clock most people assume. UNAVAILABLE without the session count, because the "
         "trade list cannot distinguish a flat session from a missing one and the two "
         "treatments differ by up to sqrt(traded fraction).", "judgement"),
    _doc("sortino_daily", "Session-clock Sortino, same construction.", "As `sharpe_daily`.",
         "judgement"),
    _doc("volatility", "Sample standard deviation (ddof=1) of per-trade net P&L, dollars.",
         "The denominator of `sharpe`, reported so a Sharpe change can be attributed to the "
         "mean or the spread.", "arithmetic"),
    _doc("skew", "Bias-corrected sample skewness of per-trade net P&L.",
         "Negative means the large trades are the losses - the profile of a strategy that "
         "sells insurance and of a stop that is not honoured. The sign is the reading; the "
         "estimator's sampling error on a few hundred trades is large.", "arithmetic"),
    _doc("kurtosis", "Bias-corrected excess kurtosis; 0 is Gaussian.",
         "Above zero the tails are fatter than a Gaussian's, which is normal for trade P&L "
         "and is what makes `cvar` more informative than `volatility`. The estimator is "
         "dominated by the single largest |trade| on small samples.", "arithmetic"),
    _doc("cvar", "Mean net P&L of the worst `cvar_quantile` fraction of trades, signed.",
         "Divide by `expectancy` for how many average trades one tail trade erases - an "
         "identity. UNAVAILABLE until at least one whole trade lies in the tail; on a small "
         "sample it is the single worst trade, and `cvar_trades` says so.", "arithmetic"),
    _doc("cvar_trades", "How many trades the tail mean was taken over.",
         "1 means `cvar` is `largest_loser` under another name.", "arithmetic"),
    _doc("longest_win_streak", "Longest run of consecutive winning trades.",
         "Operational, not statistical: `robustness.ordering_null` is the measurement of "
         "whether a streak is unusual for these trades reordered.", "arithmetic"),
    _doc("longest_loss_streak", "Longest run of consecutive losing trades; flat trades break "
         "it.", "As above. Against a prop firm's trailing drawdown it is what liquidates.",
         "arithmetic"),
    _doc("expectancy_r", "Mean R multiple: net P&L over the dollars risked to the recorded "
         "stop, per trade.",
         "The size-free expectancy. UNAVAILABLE unless EVERY trade recorded a stop: an R "
         "expectancy over the subset that did would silently drop the unmanaged trades, "
         "which are not a random subset.", "arithmetic"),
    _doc("path_coverage", "Fraction of trades that recorded an intraday path.",
         "The MAE and MFE distributions describe only this fraction. Below 1.0 they are "
         "conditional on whichever trades were recorded, which is rarely random.",
         "arithmetic"),
    _doc("stop_coverage", "Fraction of trades that recorded a stop distance.",
         "The `r_multiple` distribution covers only this fraction; `expectancy_r` refuses "
         "below 1.0.", "arithmetic"),
    _doc("holding_time", "Distribution of holding time in seconds, entry to exit.",
         "A wide spread between p25 and p75 usually means two exit mechanisms (a stop and a "
         "time exit) with different economics, and the split by direction or session "
         "usually shows which is which.", "arithmetic"),
    _doc("mae", "Distribution of maximum adverse excursion in dollars, over trades with a "
         "recorded path.", _LOWER_BOUND + " Against the stop distance it shows how often "
         "the stop was nearly hit on trades that went on to win.", "arithmetic"),
    _doc("mfe", "Distribution of maximum favourable excursion in dollars, over trades with a "
         "recorded path.", _LOWER_BOUND + " MFE far above the average winner is profit the "
         "exit rule gives back.", "arithmetic"),
    _doc("r_multiple", "Distribution of R multiples over trades with a recorded stop.",
         "A cluster at exactly -1.0 is stops honoured; a tail below -1.0 is slippage through "
         "them or gaps.", "arithmetic"),
    _doc("by_direction", "The battery per long / short.",
         "Two strategies wearing one name are common; a positive total made of one sign is "
         "a directional bet the label does not admit to. Thin buckets carry an UNRELIABLE "
         "note under `min_bucket_trades`, and that minimum is a judgement.", "judgement"),
    _doc("by_session", "The battery per session bucket label, `unlabelled` where none was "
         "recorded.",
         "Only honest when the labels came from a FIXED clock (`session_of`); a bucket "
         "chosen from the data is a selection. Thin buckets are UNRELIABLE.", "judgement"),
    _doc("by_regime", "The battery per regime label, `unlabelled` where none was recorded.",
         "Only honest when the label was causal (`robustness.labellers`). A regime with a "
         "large `share_of_net` and a small `share_of_trades` is carrying the strategy. Thin "
         "buckets are UNRELIABLE.", "judgement"),
    _doc("by_weekday", "The battery per weekday of entry.",
         "A fixed clock, so it cannot leak - but seven buckets is seven looks at the data, "
         "and the best weekday is a selection. Thin buckets are UNRELIABLE.", "judgement"),
    # -- BucketStats -------------------------------------------------------------------------
    _doc("bucket.n", "Trades in the bucket.", "Read `bucket.reliable` first.", "arithmetic"),
    _doc("bucket.share_of_trades", "Bucket trades over all trades.",
         "Denominator of the carry: compare with `bucket.share_of_net`.", "arithmetic"),
    _doc("bucket.total_net", "Net P&L in the bucket.", "Sums to `total_net` across buckets.",
         "arithmetic"),
    _doc("bucket.share_of_net", "Bucket net over whole-sample net; UNAVAILABLE when the "
         "whole-sample net is not positive.",
         "`robustness.carry` is this over `bucket.share_of_trades`: 1.0 is a fair share.",
         "arithmetic"),
    _doc("bucket.expectancy", "Mean net P&L per trade in the bucket.", "As `expectancy`.",
         "arithmetic"),
    _doc("bucket.win_rate", "Win rate within the bucket.", "As `win_rate`.", "arithmetic"),
    _doc("bucket.profit_factor", "Profit factor within the bucket.", "As `profit_factor`.",
         "judgement"),
    _doc("bucket.reliable", "Whether the bucket holds at least `min_bucket_trades` trades.",
         "False means every number in the bucket is a description of a handful of trades, "
         "and the minimum that decides it is a convention.", "judgement"),
    _doc("bucket.note", "The UNRELIABLE marker with its count, or empty.",
         "Printed next to the bucket so it cannot be read as solid.", "judgement"),
    # -- Distribution ------------------------------------------------------------------------
    _doc("dist.n", "Sample size behind the distribution.",
         "Percentiles on under about twenty observations are interpolations between a few "
         "points.", "arithmetic"),
    _doc("dist.mean", "Sample mean.", "", "arithmetic"),
    _doc("dist.min", "Sample minimum.", "", "arithmetic"),
    _doc("dist.p25", "25th percentile, linear interpolation.", "", "arithmetic"),
    _doc("dist.median", "50th percentile.", "", "arithmetic"),
    _doc("dist.p75", "75th percentile, linear interpolation.", "", "arithmetic"),
    _doc("dist.max", "Sample maximum.", "", "arithmetic"),
    # -- per-trade only ----------------------------------------------------------------------
    _doc("gross_pnl", "(exit - entry) * direction * size * multiplier.",
         "Before costs.", "arithmetic"),
    _doc("net_pnl", "gross_pnl - |commission| - |slippage|.",
         "The number every aggregate is built on.", "arithmetic"),
    _doc("initial_risk", "stop_distance * size * multiplier: dollars at risk to the recorded "
         "stop.", "UNAVAILABLE without a recorded stop.", "arithmetic"),
)}


@dataclass(frozen=True)
class Reading:
    """One metric's value with its documentation attached."""

    metric: str
    value: object
    interpretation: str
    concern: str
    basis: str


#: Inputs and statements rather than measurements.
_NOT_METRICS = frozenset({"cvar_quantile", "annualisation", "config"})


def readings(rep: TradeReport) -> list[Reading]:
    """Pair every top-level metric with its documented interpretation; refuses on a gap."""
    out: list[Reading] = []
    for f in fields(rep):
        if f.name in _NOT_METRICS:
            continue
        doc = METRIC_DOCS.get(f.name)
        if doc is None:
            raise KeyError(f"{f.name} has no entry in METRIC_DOCS; every reported metric "
                           "needs a documented interpretation")
        out.append(Reading(f.name, getattr(rep, f.name), doc.interpretation, doc.concern,
                           doc.basis))
    return out


def undocumented() -> set[str]:
    """Report fields with no METRIC_DOCS entry. Empty is the only acceptable answer."""
    named = {f.name for f in fields(TradeReport)} - _NOT_METRICS
    named |= {f"bucket.{f.name}" for f in fields(BucketStats)}
    named |= {f"dist.{f.name}" for f in fields(Distribution)}
    return named - set(METRIC_DOCS)


def judgements() -> list[str]:
    """Every metric whose worrying value is somebody's opinion."""
    return sorted(k for k, v in METRIC_DOCS.items() if v.basis == "judgement")


__all__ = [
    "CALENDAR_DAYS_PER_YEAR", "CVAR_QUANTILE", "MIN_BUCKET_TRADES", "MIN_TRADES_FOR_RATIOS",
    "METRIC_DOCS", "NO_PATH", "NO_STOP", "NO_TRADES", "NO_TRADING_DAYS", "SESSIONS_PER_YEAR",
    "UNLABELLED", "WEEKDAYS", "Annualisation", "BucketStats", "Config", "Direction",
    "Distribution", "Metric", "Reading", "Trade", "TradeReport", "Unavailable", "aggregate",
    "available", "judgements", "readings", "report", "session_of", "to_jsonable",
    "trade_records", "undocumented",
]
