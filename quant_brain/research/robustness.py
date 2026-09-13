"""Regimes and concentration: where the money came from, and whether it came from one path.

Parts 29 and 34. The funnel in `search.py` decides whether a hypothesis is significant. That
is a different question from whether it is *robust*, and a strategy can pass every gate there
while being, in substance, one very good Tuesday.

This module answers two questions with numbers.

    (1) WHEN did it work?  - `session_table`, the labellers, `regime_performance`
    (2) Is it ONE LUCKY PATH? - `concentration`, `ordering_null`, `parameter_sensitivity`

A REGIME LABEL IS A FEATURE, AND THEREFORE CAN LEAK
---------------------------------------------------
This is the whole reason the labelling half exists as code rather than as a groupby in a
notebook. Splitting a sample into "high volatility" and "low volatility" and reporting the
Sharpe of each is arithmetic anyone can do in one line - and the one line is almost always a
lookahead, because the natural way to write it is `pd.qcut(vol, 3)`, whose boundaries are a
function of the whole sample including the future. Every session then knows whether it is
about to be in the top third of the year's volatility, and the "high-vol regime" result is
partly a report on that knowledge.

This repository lost a full day to exactly that class of bug at a much smaller scale:
`features._opening_range_pos` divided by the first thirty bars' high-low range *from bar
zero*, so bar 5 already knew the extremes of bars 6-29. It came back as the single strongest
result of a 272-candidate search, t = +6.25 against a 3.56 multiplicity bar, five of five
walk-forward folds positive. A leak reads exactly like an edge.

So every labeller here computes its state and its boundaries from sessions STRICTLY BEFORE
the session it labels, and `assert_causal_labels` verifies that empirically the way
`features.assert_causal` does - by perturbing the future and checking that nothing earlier
moves. The sweep is weighted toward the start of the sample for the same reason it is there:
a leak confined to a warm-up window is invisible to a probe at 80% through the series.

TWO THINGS THAT ARE NOT REGIME LABELS
-------------------------------------
Time-of-day buckets and the overnight/RTH split are partitions *inside* a session, not labels
*on* one. They cannot leak from the price history, because their boundaries are clock times
known years in advance - but that immunity is a property of using a FIXED clock, and it is
lost the moment a boundary is chosen from the data ("the most profitable hour", "the window
where the effect is strongest"). Those are selections, and they need the same multiplicity
accounting as any other search. `intraday_attribution` takes the buckets as an argument and
does not choose them.

WHAT A CONCENTRATION METRIC CAN AND CANNOT SETTLE
-------------------------------------------------
Every number in `ConcentrationReport` is a measurement of one realised sample: it says what
happened, not what will. The interpretations in `METRIC_DOCS` separate the two honestly -
each entry carries a `basis` of "arithmetic" (the reading follows from the definition) or
"judgement" (someone has to decide how much is too much, and this module refuses to pretend
that decision is settled).

Where a threshold can be replaced by a measurement, it is. `ordering_null` answers "is this
losing streak unusual?" by reshuffling the strategy's own sessions instead of comparing
against a number someone made up, and `tail_null` does the same for profit concentration
against a stated Gaussian reference. Those p-values are measurements. "A best-day share above
25% is worrying" is a judgement, and is labelled as one.
"""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Protocol

import numpy as np
import pandas as pd

from quant_brain.core import stats

# =====================================================================================
# SESSION RECORDS
# =====================================================================================


class SessionRecord(Protocol):
    """One session's outcome. `twin.TwinDay` satisfies this structurally.

    Declared as a protocol rather than imported, because `research/` must not depend on one
    market's twin: the same concentration arithmetic applies to an equity sleeve whose
    session record is a different class entirely.

    Read-only properties rather than attributes, so a frozen dataclass satisfies it - which
    `TwinDay` is, and a protocol demanding mutable attributes would quietly exclude it.
    """

    @property
    def day(self) -> dt.date: ...

    @property
    def pnl(self) -> float: ...

    @property
    def path(self) -> tuple[float, ...]: ...


def pnl_and_dates(days: Sequence[SessionRecord]) -> tuple[np.ndarray, list[dt.date]]:
    """Split session records into the two arrays every metric below actually wants."""
    return (np.array([float(d.pnl) for d in days], dtype=float), [d.day for d in days])


# =====================================================================================
# CLOCK GEOMETRY (Part 29: time-of-day and overnight/RTH)
# =====================================================================================

DEFAULT_TZ = "America/New_York"
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
#: CME's trade date rolls at 18:00 ET: Sunday evening's bars belong to Monday's session.
GLOBEX_ROLLOVER = dt.time(18, 0)
#: The label given to sessions that precede a labeller's warm-up. Not NaN, because a NaN
#: silently vanishes from a groupby and the warm-up region then looks like it never existed.
WARMUP = "warmup"


@dataclass(frozen=True)
class Bucket:
    """A named span of the local clock. `end` is exclusive; a span may wrap midnight."""

    name: str
    start: dt.time
    end: dt.time

    def contains_minute(self, minute_of_day):
        a, b = _mins(self.start), _mins(self.end)
        if a <= b:
            return (minute_of_day >= a) & (minute_of_day < b)
        return (minute_of_day >= a) | (minute_of_day < b)

    @property
    def minutes(self) -> int:
        a, b = _mins(self.start), _mins(self.end)
        return (b - a) % 1440 or 1440


def _mins(t: dt.time) -> int:
    return t.hour * 60 + t.minute


#: The brief's three time-of-day buckets, over the US regular session.
DEFAULT_BUCKETS: tuple[Bucket, ...] = (
    Bucket("open", dt.time(9, 30), dt.time(10, 30)),
    Bucket("midday", dt.time(10, 30), dt.time(15, 0)),
    Bucket("close", dt.time(15, 0), dt.time(16, 0)),
)

#: The full CME trade date. `overnight` is the pre-RTH span, which is where the overnight vs
#: RTH question lives on a futures store; `post` is the 16:00-17:00 tail before the halt.
GLOBEX_BUCKETS: tuple[Bucket, ...] = (
    Bucket("overnight", GLOBEX_ROLLOVER, RTH_OPEN),
    *DEFAULT_BUCKETS,
    Bucket("post", RTH_CLOSE, dt.time(17, 0)),
)


# =====================================================================================
# SESSION STATISTICS FROM BARS
# =====================================================================================

def session_table(bars, *, time_col: str = "t", tz: str = DEFAULT_TZ,
                  rollover: dt.time | None = GLOBEX_ROLLOVER,
                  buckets: Sequence[Bucket] = GLOBEX_BUCKETS) -> pd.DataFrame:
    """Per-session market statistics, indexed by trade date and sorted.

    This is raw description, not a label: nothing here is shifted, because the row for a
    session is allowed to describe that session. The causality requirement lands on the
    LABELLERS, which may only read rows before the one they are labelling.

    Columns: `bars`, `ret`, `rvol`, `volume`, `range_frac`, `efficiency`, `trend_strength`,
    and the same set again prefixed by each bucket's name.

    `efficiency` is the Kaufman ratio, |net move| / summed absolute move: 1.0 for a session
    that went one way, near 0 for one that ended where it started having travelled a long
    way. That is the trending/range-bound axis Part 29 asks for, and unlike a trend
    regression it needs no window length, so there is one fewer knob to fit.
    `trend_strength` is the same ratio with its bar-count dependence divided out - see
    `_aggregate` - and is the one the trend labeller uses.

    `rollover=None` treats the local calendar date as the session, which is what an
    RTH-only equity store wants. On CME the trade date rolls at 18:00 ET and using the
    calendar date instead splits every overnight in half.
    """
    if time_col not in getattr(bars, "columns", ()):
        raise ValueError(f"session_table needs a {time_col!r} column; got "
                         f"{list(getattr(bars, 'columns', []))}")
    _check_buckets(buckets)
    ts = pd.DatetimeIndex(pd.Series(bars[time_col]))
    if ts.tz is None:
        raise ValueError(
            f"{time_col!r} is timezone-naive. Session boundaries, the RTH window and the "
            "18:00 rollover are all wall-clock rules in an exchange timezone, and guessing "
            "which one a naive column is in has already produced one silent off-by-an-hour "
            "class of bug in this repository (AUD-07).")
    # Wall clock, deliberately: every boundary below is a local-clock rule, and DST arithmetic
    # on an absolute timestamp puts a fall-back session on the wrong trade date. The rollover
    # is applied by adding a day to the NAIVE local clock for the same reason - adding 24
    # hours to a tz-aware timestamp lands on 23:00 of the same date across a fall-back.
    local = pd.Series(pd.DatetimeIndex(ts.tz_convert(tz).tz_localize(None)))
    minute = (local.dt.hour * 60 + local.dt.minute).to_numpy(dtype=int)
    today = local.dt.date.to_numpy()
    if rollover is None:
        session = today
    else:
        tomorrow = (local + pd.Timedelta(days=1)).dt.date.to_numpy()
        session = np.where(minute >= _mins(rollover), tomorrow, today)

    work = pd.DataFrame({
        "session": session,
        "minute": minute,
        # Sorted on the TIMESTAMP, never on minute-of-day. A CME trade date runs 18:00 to
        # 17:00, so ordering its bars by wall-clock minute puts midnight first and the
        # previous evening last: the session return then measures 18:00-to-23:59 instead of
        # open-to-close, and the wrap adds a spurious jump to every path-length statistic.
        # Measured on data/futures/ES.parquet, 327 sessions, with the buggy sort against the
        # correct one: mean |session return| 9.0e-5 against 6.0e-3, and mean efficiency
        # 4.6e-4 against 3.3e-2. Two orders of magnitude, and no error anywhere.
        "ts": local.to_numpy(),
        "c": np.asarray(bars["c"], dtype=float),
        "v": (np.asarray(bars["v"], dtype=float) if "v" in bars.columns
              else np.zeros(len(ts), dtype=float)),
    })
    for col in ("h", "l"):
        work[col] = (np.asarray(bars[col], dtype=float) if col in bars.columns
                     else work["c"].to_numpy())
    work = work.sort_values("ts", kind="stable").reset_index(drop=True)

    out = _aggregate(work, "session")
    out.index.name = "session"
    for b in buckets:
        mask = b.contains_minute(work["minute"].to_numpy())
        part = _aggregate(work.loc[mask], "session", prefix=f"{b.name}_")
        out = out.join(part, how="left")
        out[f"{b.name}_bars"] = out[f"{b.name}_bars"].fillna(0).astype(int)
    return out


def _series(x) -> pd.Series:
    """A float Series out of whatever a groupby aggregation handed back.

    Deliberate: `grouped["c"].first()` is typed as a union wide enough that every later
    operator becomes untyped, and the arithmetic below is the part worth having checked.
    """
    return pd.Series(np.asarray(x, dtype=float), index=getattr(x, "index", None))


def _nonzero(s: pd.Series) -> pd.Series:
    """Zeros to NaN before a division, matching `features._nz`: a zero denominator here is an
    empty window, not a ratio of zero, and letting it through makes an inf nothing catches."""
    return s.where(s != 0.0)


def _aggregate(work: pd.DataFrame, key: str, *, prefix: str = "") -> pd.DataFrame:
    """Session statistics over whatever slice of bars is handed in."""
    if not len(work):
        cols = [f"{prefix}{c}" for c in ("bars", "ret", "rvol", "volume", "range_frac",
                                         "efficiency", "trend_strength")]
        empty = pd.Index([], dtype=object, name=key)
        return pd.DataFrame({c: pd.Series(dtype=float, index=empty) for c in cols},
                            index=empty)
    grouped = work.groupby(key, sort=True)
    first_close = _series(grouped["c"].first())
    last_close = _series(grouped["c"].last())

    # Bar-to-bar returns, with the first bar of each slice cut: a diff across a session
    # boundary is an overnight gap, not a bar return, and leaving it in makes every session's
    # realised volatility a function of the previous session's close.
    close = work["c"].to_numpy()
    same = np.r_[False, work[key].to_numpy()[1:] == work[key].to_numpy()[:-1]]
    step = np.full(len(close), np.nan)
    step[1:] = np.diff(close)
    step = np.where(same, step, np.nan)
    prev = np.where(same, np.r_[np.nan, close[:-1]], np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        ret_bar = np.where(prev > 0, step / prev, np.nan)
    tmp = pd.DataFrame({key: work[key].to_numpy(), "r": ret_bar, "absd": np.abs(step)})
    by = tmp.groupby(key, sort=True)

    travelled = _series(by["absd"].sum(min_count=1))
    net = (last_close - first_close).abs()
    size = _series(grouped.size())
    efficiency = net / _nonzero(travelled)
    out = pd.DataFrame({
        f"{prefix}bars": size.astype(int),
        f"{prefix}ret": last_close / _nonzero(first_close) - 1.0,
        f"{prefix}rvol": _series(by["r"].std(ddof=0)),
        f"{prefix}volume": _series(grouped["v"].sum()),
        f"{prefix}range_frac": ((_series(grouped["h"].max()) - _series(grouped["l"].min()))
                                / _nonzero(first_close)),
        f"{prefix}efficiency": efficiency,
        # The raw Kaufman ratio falls off as 1/sqrt(bars) under a random walk, so on a
        # minute store it is ~0.027 for 1,380 bars and mechanically LARGER on a short
        # session. Measured on data/futures/ES.parquet: mean efficiency 0.033 against the
        # 0.027 a random walk would give, and the store's early closes run 915 bars. A
        # trend regime built on the raw ratio would therefore label half-day holidays as
        # trending. Multiplying by sqrt(bars) removes the length term: 1.0 is a random
        # walk, above is directional, below is mean-reverting.
        f"{prefix}trend_strength": efficiency * np.sqrt(size),
    })
    return out


def _check_buckets(buckets: Sequence[Bucket]) -> None:
    if not buckets:
        raise ValueError("at least one bucket is required")
    seen: set[str] = set()
    for b in buckets:
        if b.name in seen:
            raise ValueError(f"duplicate bucket name {b.name!r}; two spans with one name is a "
                             "silent overwrite in every column below")
        seen.add(b.name)


def coverage(table: pd.DataFrame, bucket: str) -> float:
    """Fraction of sessions with at least one bar in `bucket`.

    The honest answer to "does this store distinguish overnight from RTH?". An RTH-only store
    returns 0.0 for `overnight`, and the correct response is to report the split as
    unavailable rather than to compute one from the bars that do exist - the same refusal
    `features.FeatureSet.missing` makes about microstructure columns.
    """
    col = f"{bucket}_bars"
    if col not in table.columns or not len(table):
        return 0.0
    return float((table[col].to_numpy() > 0).mean())


# =====================================================================================
# REGIME LABELLERS - CAUSAL BY CONSTRUCTION, VERIFIED EMPIRICALLY
# =====================================================================================

LabelFn = Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class RegimeLabeller:
    """One named split of the sample, and what the session table must carry to compute it."""

    name: str
    family: str
    fn: LabelFn
    requires: tuple[str, ...] = ("rvol",)
    #: Sessions consumed before the first real label. Everything before is `WARMUP`.
    warmup: int = 0
    describe: str = ""

    def available(self, columns) -> bool:
        return all(c in columns for c in self.requires)

    def label(self, table: pd.DataFrame) -> pd.Series:
        if not self.available(table.columns):
            missing = tuple(c for c in self.requires if c not in table.columns)
            raise ValueError(f"{self.name} needs {missing}, which this table does not carry")
        return pd.Series(np.asarray(self.fn(table), dtype=object), index=table.index,
                         dtype=object)


def _state(x, short: int) -> pd.Series:
    """The regime state entering each session: a mean over sessions STRICTLY before it.

    `shift(1)` first, then roll. Rolling first and shifting after is the same thing here, but
    only by accident of the mean being linear - writing the shift first makes the causality
    survive someone swapping the mean for a quantile.
    """
    return _series(_series(x).shift(1).rolling(short, min_periods=short).mean())


def _binary(table: pd.DataFrame, col: str, *, short: int, long: int,
            high: str, low: str) -> pd.Series:
    """High/low against the median of the state's OWN recent history.

    The baseline is a trailing median of the same smoothed series, not of the raw column: a
    5-session mean is less dispersed than a single session, so comparing one against the
    other's quantiles would classify almost everything as "mid".
    """
    state = _state(table[col], short)
    base = _series(state.rolling(long, min_periods=long).median())
    out = pd.Series(WARMUP, index=table.index, dtype=object)
    ok = state.notna() & base.notna()
    out[ok & (state > base)] = high
    out[ok & (state <= base)] = low
    return out


def _tercile(table: pd.DataFrame, col: str, *, short: int, long: int,
             names: tuple[str, str, str]) -> pd.Series:
    """Terciles whose boundaries are a trailing window, never the whole sample.

    `pd.qcut(x, 3)` is the version of this that everybody writes and it is a lookahead: the
    cut points are a statistic of the entire series, so a session in January is labelled using
    December's volatility. That single line is the bug this module is built to make hard.
    """
    state = _state(table[col], short)
    lo = _series(state.rolling(long, min_periods=long).quantile(1.0 / 3.0))
    hi = _series(state.rolling(long, min_periods=long).quantile(2.0 / 3.0))
    out = pd.Series(WARMUP, index=table.index, dtype=object)
    ok = state.notna() & lo.notna() & hi.notna()
    out[ok & (state <= lo)] = names[0]
    out[ok & (state > lo) & (state <= hi)] = names[1]
    out[ok & (state > hi)] = names[2]
    return out


def labellers(*, short: int = 5, long: int = 60) -> list[RegimeLabeller]:
    """The standard regime set: volatility, trend, volume.

    `short` is how many prior sessions define "the state right now" and `long` is the window
    the state is judged against. Both are JUDGEMENTS, not estimates - 5 and 60 are a week and
    a quarter, chosen because they are conventional, and a result that changes materially when
    they move is a result about the windows. `parameter_sensitivity` is the tool for checking
    that, and these two are as fair a target for it as any strategy parameter.
    """
    return [
        RegimeLabeller(
            "vol_regime", "volatility",
            lambda t: _binary(t, "rvol", short=short, long=long,
                              high="high_vol", low="low_vol"),
            ("rvol",), short + long,
            "realised volatility of the prior week against its own quarter median"),
        RegimeLabeller(
            "vol_tercile", "volatility",
            lambda t: _tercile(t, "rvol", short=short, long=long,
                               names=("vol_low", "vol_mid", "vol_high")),
            ("rvol",), short + long,
            "trailing terciles of realised volatility"),
        RegimeLabeller(
            "trend_regime", "trend",
            lambda t: _binary(t, "trend_strength", short=short, long=long,
                              high="trending", low="ranging"),
            ("trend_strength",), short + long,
            "Kaufman efficiency ratio, bar-count neutral: 1.0 is a random walk"),
        RegimeLabeller(
            "volume_regime", "volume",
            lambda t: _binary(t, "volume", short=short, long=long,
                              high="high_volume", low="low_volume"),
            ("volume",), short + long,
            "session volume of the prior week against its own quarter median"),
    ]


def label_table(table: pd.DataFrame, labs: Sequence[RegimeLabeller] | None = None,
                *, strict: bool = True) -> pd.DataFrame:
    """One column of labels per labeller, aligned to the session index.

    `strict` refuses when the table cannot support a labeller, for the reason
    `FeatureSet.build` does: quietly returning three regimes where four were asked for means
    the reader is looking at a different partition than the one they believe they asked for.
    """
    labs = list(labs if labs is not None else labellers())
    unsupported = {lab.name: tuple(c for c in lab.requires if c not in table.columns)
                   for lab in labs if not lab.available(table.columns)}
    if unsupported and strict:
        detail = "; ".join(f"{k} needs {v}" for k, v in unsupported.items())
        raise ValueError(f"this session table cannot support {len(unsupported)} labeller(s): "
                         f"{detail}")
    return pd.DataFrame({lab.name: lab.label(table)
                         for lab in labs if lab.name not in unsupported},
                        index=table.index)


def assert_causal_labels(labeller: RegimeLabeller, table: pd.DataFrame,
                         *, at: int | None = None, seed: int = 0) -> None:
    """Verify empirically that a labeller does not read the future.

    Rewrites the session table from row `at` onward and checks that no EARLIER label moves.
    A whole-sample `qcut`, an unshifted rolling window, or a centred window all pass code
    review and all fail this.

    The probe points are weighted toward the START of the sample, and that weighting is not
    decoration: `features.assert_causal` originally tested a single index at 80% through the
    series, and that is precisely how `opening_range_pos` shipped with a leak confined to its
    first thirty bars. Warm-up regions are where a labeller reaches forward.
    """
    if not labeller.available(table.columns):
        return
    n = len(table)
    if at is not None:
        points = [at]
    else:
        candidates = [3, 5, 10, 20, labeller.warmup + 2, labeller.warmup + 10,
                      int(n * 0.25), int(n * 0.5), int(n * 0.8)]
        points = sorted({p for p in candidates if 0 < p < n - 1})
    if not points:
        raise ValueError(f"{labeller.name}: a table of {n} sessions is too short to test "
                         "causality")
    for p in points:
        _assert_causal_at(labeller, table, p, seed)


def _assert_causal_at(labeller: RegimeLabeller, table: pd.DataFrame, at: int,
                      seed: int) -> None:
    base = labeller.label(table).to_numpy(dtype=object)
    numeric = [c for c in table.columns if pd.api.types.is_numeric_dtype(table[c])]
    bumped = table.copy()
    for c in numeric:
        bumped[c] = bumped[c].astype(float)
    if not numeric:
        return
    rng = np.random.default_rng(seed)
    block = bumped.iloc[at:][numeric].to_numpy(dtype=float)
    scale = float(np.nanstd(block)) if bool(np.isfinite(block).any()) else 1.0
    # Scale AND jitter. A pure scale leaves the ordering of the tail intact, and a labeller
    # that only reads ranks would survive it while still being a lookahead.
    bumped.iloc[at:, [bumped.columns.get_loc(c) for c in numeric]] = (
        block * 4.0 + rng.normal(0.0, 1.0 + scale, size=block.shape))
    after = labeller.label(bumped).to_numpy(dtype=object)

    head_base, head_after = base[:at], after[:at]
    differs = head_base != head_after
    if differs.any():
        first = int(np.argmax(differs))
        raise AssertionError(
            f"{labeller.name} is not causal: rewriting session {at} changed the label at "
            f"session {first} ({head_base[first]!r} -> {head_after[first]!r}). A whole-sample "
            f"quantile, a rolling window without the leading shift, or a centred window are "
            f"the usual causes.")


def audit_label_causality(labs: Sequence[RegimeLabeller],
                          table: pd.DataFrame) -> dict[str, str]:
    """Run `assert_causal_labels` over a set. Returns the failures, empty when clean."""
    out: dict[str, str] = {}
    for lab in labs:
        try:
            assert_causal_labels(lab, table)
        except AssertionError as exc:
            out[lab.name] = str(exc)
        except Exception as exc:                                        # noqa: BLE001
            out[lab.name] = f"{type(exc).__name__}: {exc}"
    return out


# =====================================================================================
# PERFORMANCE PER REGIME
# =====================================================================================

@dataclass(frozen=True)
class RegimeRow:
    """One regime's slice of the record."""

    regime: str
    n: int
    sessions_share: float
    total: float
    mean: float
    share_of_net: float
    share_of_gross_profit: float
    win_rate: float
    t: float

    @property
    def carry(self) -> float:
        """Profit share divided by session share. 1.0 is its fair share of the P&L.

        The number that answers "does one regime carry everything?": a regime that is 12% of
        the sessions and 80% of the profit reads 6.7, and the strategy is a bet on that
        regime recurring whether or not its author meant it to be.
        """
        return (self.share_of_net / self.sessions_share
                if self.sessions_share > 0 else float("nan"))


def regime_performance(pnl, labels, *, drop_warmup: bool = True) -> list[RegimeRow]:
    """Per-session P&L grouped by regime label, sorted by total contribution.

    `t` is HAC (Newey-West) rather than iid, because session P&L within a regime is not
    independent - regimes are persistent by construction, so a regime's sessions are mostly
    consecutive and their P&L is serially correlated. It is still a t on a subsample that was
    chosen after seeing the data, and reading it as a significance test would be the AUD-19
    error; it is here to show which regimes have enough sessions to say anything at all.
    """
    x = np.asarray(pnl, dtype=float)
    lab = np.array([str(v) for v in list(labels)], dtype=object)
    if len(x) != len(lab):
        raise ValueError(f"pnl has {len(x)} sessions and labels has {len(lab)}; aligning "
                         "them by position requires the same length. Use align_sessions().")
    keep = np.ones(len(x), dtype=bool) if not drop_warmup else (lab != WARMUP)
    x, lab = x[keep], lab[keep]
    total = float(x.sum())
    gross = float(x[x > 0].sum())
    rows: list[RegimeRow] = []
    for name in sorted({str(v) for v in lab}):
        sel = x[lab == name]
        if not len(sel):
            continue
        t = stats.tstat_hac(sel)
        rows.append(RegimeRow(
            regime=name,
            n=len(sel),
            sessions_share=len(sel) / len(x),
            total=float(sel.sum()),
            mean=float(sel.mean()),
            share_of_net=(float(sel.sum()) / total if total > 0 else float("nan")),
            share_of_gross_profit=(float(sel[sel > 0].sum()) / gross if gross > 0
                                   else float("nan")),
            win_rate=float((sel > 0).mean()),
            t=float(t.t)))
    return sorted(rows, key=lambda r: r.total, reverse=True)


def carried_by(rows: Sequence[RegimeRow]) -> RegimeRow | None:
    """The regime with the largest share of net profit, or None when nothing is positive."""
    live = [r for r in rows if math.isfinite(r.share_of_net)]
    return max(live, key=lambda r: r.share_of_net) if live else None


def align_sessions(days: Sequence[SessionRecord],
                   table: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    """Match session records to session-table rows by date. Returns (pnl, aligned table).

    Sessions the table does not cover are DROPPED rather than labelled from a neighbour,
    because a regime carried over from an adjacent date is a fabricated label, and it will be
    fabricated exactly on the days the store is thin - which are not a random subset.
    """
    index = {d: i for i, d in enumerate(table.index)}
    pos = [(i, index[d.day]) for i, d in enumerate(days) if d.day in index]
    if not pos:
        raise ValueError("no session record's date appears in the session table; check the "
                         "trade-date convention (rollover=) before assuming the data is bad")
    keep_days = [days[i] for i, _ in pos]
    return (np.array([float(d.pnl) for d in keep_days], dtype=float),
            table.iloc[[j for _, j in pos]])


# =====================================================================================
# INTRADAY ATTRIBUTION (time-of-day buckets, overnight vs RTH)
# =====================================================================================

def bucket_spans(buckets: Sequence[Bucket], *, session_start: dt.time,
                 session_end: dt.time) -> list[tuple[str, float, float]]:
    """Each bucket as a fraction of the declared session, in order."""
    _check_buckets(buckets)
    origin = _mins(session_start)
    span = (_mins(session_end) - origin) % 1440 or 1440

    def rel(t: dt.time, *, is_end: bool) -> float:
        m = (_mins(t) - origin) % 1440
        if is_end and m == 0:
            m = span
        return m / span

    out = []
    for b in buckets:
        a, z = rel(b.start, is_end=False), rel(b.end, is_end=True)
        if not (0.0 <= a < z <= 1.0):
            raise ValueError(
                f"bucket {b.name!r} ({b.start}-{b.end}) does not lie inside the declared "
                f"session {session_start}-{session_end}; attributing P&L to a span outside "
                "the session would invent it")
        out.append((b.name, a, z))
    return out


def intraday_attribution(days: Sequence[SessionRecord], *,
                         buckets: Sequence[Bucket] = DEFAULT_BUCKETS,
                         session_start: dt.time = RTH_OPEN,
                         session_end: dt.time = RTH_CLOSE) -> dict[str, float]:
    """Total P&L attributed to each clock bucket, from the sessions' intraday paths.

    ASSUMPTION, STATED RATHER THAN BURIED: the marks in `path` are evenly spaced across the
    declared session. That is true of a path emitted per bar by a backtester and false of
    `twin.u_shaped_path`, which is a three-point caricature - so this refuses any path with
    fewer marks than buckets instead of returning a split of a shape that has none.

    Contributions sum to the strategy's total P&L by construction, which is the invariant
    worth checking after any change here: an attribution that does not add up is assigning
    money to a bucket it did not come from.
    """
    spans = bucket_spans(buckets, session_start=session_start, session_end=session_end)
    out = dict.fromkeys((name for name, _, _ in spans), 0.0)
    for d in days:
        marks = _marks(d)
        if len(marks) - 1 < len(spans):
            raise ValueError(
                f"session {d.day} has a {len(marks) - 1}-segment path and {len(spans)} "
                "buckets were requested. Splitting it would hand whole buckets a zero that "
                "reads as 'made nothing here' rather than 'was never measured'. Emit a "
                "per-bar path, or ask for fewer buckets.")
        last = len(marks) - 1
        for name, a, z in spans:
            i, j = int(round(a * last)), int(round(z * last))
            out[name] += float(marks[j] - marks[i])
    return out


def _marks(day: SessionRecord) -> tuple[float, ...]:
    """The session's equity path as marks from 0, guaranteed to end at the session's P&L."""
    path = tuple(float(m) for m in getattr(day, "path", ()) or ())
    if not path:
        raise ValueError(
            f"session {day.day} has no intraday path, so it cannot be attributed to a time "
            "of day. This is the same refusal `TopstepTwin.strict_path` makes: an absent "
            "path is missing information, not a flat one.")
    marks = (0.0, *path)
    if not math.isclose(marks[-1], float(day.pnl), rel_tol=1e-9, abs_tol=1e-9):
        marks = (*marks, float(day.pnl))
    return marks


# =====================================================================================
# CONCENTRATION (Part 34)
# =====================================================================================

@dataclass(frozen=True)
class ConcentrationReport:
    """Is this one lucky path? Every field is a measurement of one realised sample.

    Interpretations, and which of them are judgements, are in `METRIC_DOCS`; `readings()`
    pairs them with the values so a report can be printed without a reader having to
    remember which direction is bad.
    """

    n: int
    n_winners: int
    total: float
    gross_profit: float
    gross_loss: float
    net_positive: bool
    best_day: float
    best_day_share: float
    best_day_share_gross: float
    best_week_share: float
    best_month_share: float
    best_window_share: dict[int, float] = field(default_factory=dict)
    top_share: dict[float, float] = field(default_factory=dict)
    herfindahl: float = float("nan")
    effective_sessions: float = float("nan")
    gini: float = float("nan")
    gini_floor: float = float("nan")
    gini_winners: float = float("nan")
    without_best: dict[int, float] = field(default_factory=dict)
    days_to_zero: int = 0
    longest_losing_streak: int = 0
    max_drawdown: float = 0.0
    longest_underwater: int = 0
    underwater_fraction: float = 0.0

    def table(self) -> str:
        rows = [
            ("sessions", f"{self.n}  ({self.n_winners} winners)"),
            ("total / gross profit", f"{self.total:,.0f} / {self.gross_profit:,.0f}"),
            ("best day", f"{self.best_day:,.0f}  "
                         f"{self.best_day_share:.1%} of net, "
                         f"{self.best_day_share_gross:.1%} of gross"),
            ("best week / month", f"{self.best_week_share:.1%} / "
                                  f"{self.best_month_share:.1%} of net"),
            ("top 1/5/10% of sessions", "  ".join(
                f"{self.top_share.get(q, float('nan')):.1%}" for q in (0.01, 0.05, 0.10))),
            ("Herfindahl / effective days", f"{self.herfindahl:.4f} / "
                                            f"{self.effective_sessions:.1f}"),
            ("Gini (floor / winners)", f"{self.gini:.3f} "
                                       f"({self.gini_floor:.3f} / {self.gini_winners:.3f})"),
            ("total without best 1/5/10", "  ".join(
                f"{self.without_best.get(k, float('nan')):,.0f}" for k in (1, 5, 10))),
            ("best days to zero", "already <= 0" if not self.days_to_zero
                                  else str(self.days_to_zero)),
            ("longest losing streak", f"{self.longest_losing_streak} sessions"),
            ("max drawdown", f"{self.max_drawdown:,.0f}"),
            ("time under water", f"{self.longest_underwater} sessions max, "
                                 f"{self.underwater_fraction:.0%} of the sample"),
        ]
        width = max(len(k) for k, _ in rows)
        return "\n".join(f"  {k:<{width}}  {v}" for k, v in rows)


def concentration(pnl, *, dates: Sequence[dt.date] | None = None,
                  tops: Sequence[float] = (0.01, 0.05, 0.10),
                  drop: Sequence[int] = (1, 5, 10),
                  windows: Sequence[int] = (5, 21)) -> ConcentrationReport:
    """The full concentration battery over a per-session P&L series.

    THE DENOMINATOR PROBLEM, HANDLED EXPLICITLY. "Share of total profit" is only a share when
    the total is positive. On a losing strategy `best_day / total` is negative, and on a
    breakeven one it is enormous - in both cases it is arithmetic noise rather than a finding.
    So every `_share` against the net total is NaN when the total is <= 0, `net_positive`
    says why, and the `_gross` variants (against the sum of winning sessions) are reported
    alongside because they are well defined whenever anything was ever made.
    """
    x = np.asarray(pnl, dtype=float)
    n = len(x)
    if n == 0:
        raise ValueError("concentration needs at least one session")
    if not bool(np.isfinite(x).all()):
        # Dropping them would silently change the denominator of every share and, where
        # `dates` is supplied, misalign the calendar groupings against the P&L.
        raise ValueError(f"{int((~np.isfinite(x)).sum())} of {n} sessions are NaN or inf; "
                         "decide what they mean (untraded is 0.0, missing is a hole in the "
                         "sample) before asking how concentrated the profit is")
    if dates is not None and len(dates) != n:
        raise ValueError(f"{len(dates)} dates for {n} sessions")

    total = float(x.sum())
    wins = x[x > 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-x[x < 0].sum())
    net_positive = total > 0

    def share(v: float) -> float:
        return v / total if net_positive else float("nan")

    def share_gross(v: float) -> float:
        return v / gross_profit if gross_profit > 0 else float("nan")

    order = np.sort(x)[::-1]
    best_day = float(order[0])
    tops_out = {float(q): share(float(order[:max(1, int(math.ceil(q * n)))].sum()))
                for q in tops}
    window_out = {int(k): share(_best_window(x, int(k))) for k in windows}

    week_share, month_share = float("nan"), float("nan")
    if dates is not None:
        keys_w = [(d.isocalendar()[0], d.isocalendar()[1]) for d in dates]
        keys_m = [(d.year, d.month) for d in dates]
        week_share = share(_best_group(x, keys_w))
        month_share = share(_best_group(x, keys_m))

    hhi = _hhi(wins, gross_profit)
    without = {int(k): float(order[int(k):].sum()) if int(k) < n else 0.0 for k in drop}
    dd = drawdown_profile(x)

    return ConcentrationReport(
        n=n,
        n_winners=int(len(wins)),
        total=total,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_positive=net_positive,
        best_day=best_day,
        best_day_share=share(best_day),
        best_day_share_gross=share_gross(best_day),
        best_week_share=week_share,
        best_month_share=month_share,
        best_window_share=window_out,
        top_share=tops_out,
        herfindahl=hhi,
        effective_sessions=(1.0 / hhi if hhi > 0 else float("nan")),
        gini=_gini(np.maximum(x, 0.0)),
        gini_floor=(1.0 - len(wins) / n),
        gini_winners=(_gini(wins) if len(wins) else float("nan")),
        without_best=without,
        days_to_zero=_days_to_zero(order, total),
        longest_losing_streak=int(dd["longest_losing_streak"]),
        max_drawdown=float(dd["max_drawdown"]),
        longest_underwater=int(dd["longest_underwater"]),
        underwater_fraction=float(dd["underwater_fraction"]),
    )


def _best_group(x: np.ndarray, keys: Sequence[object]) -> float:
    sums: dict[object, float] = {}
    for k, v in zip(keys, x.tolist(), strict=True):
        sums[k] = sums.get(k, 0.0) + float(v)
    return max(sums.values())


def _best_window(x: np.ndarray, k: int) -> float:
    """Best rolling k-session sum. Calendar-free, so it cannot be flattered by alignment."""
    if k <= 0 or k > len(x):
        return float("nan")
    return float(np.convolve(x, np.ones(k), mode="valid").max())


def _hhi(wins: np.ndarray, gross_profit: float) -> float:
    """Herfindahl over each winning session's share of gross profit.

    Losing sessions contribute 0, which is right: they did not concentrate the profit, they
    reduced it, and that shows up in `gross_loss` and the drawdown fields instead. Running a
    Herfindahl over signed P&L is meaningless - the shares would not sum to one and squaring a
    negative share would make a loss look like concentration.
    """
    if gross_profit <= 0 or not len(wins):
        return float("nan")
    s = wins / gross_profit
    return float((s * s).sum())


def _gini(x: np.ndarray) -> float:
    """Gini over a non-negative vector. 0 = perfectly even, 1 = one observation has it all."""
    a = np.sort(np.asarray(x, dtype=float))
    n = len(a)
    if n == 0 or a.sum() <= 0:
        return float("nan")
    i = np.arange(1, n + 1, dtype=float)
    return float((2.0 * (i * a).sum()) / (n * a.sum()) - (n + 1.0) / n)


def _days_to_zero(order_desc: np.ndarray, total: float) -> int:
    """How many of the best sessions have to be deleted before the strategy stops making
    money. 0 means it already does not."""
    if total <= 0:
        return 0
    running = total
    for k, v in enumerate(order_desc.tolist(), start=1):
        running -= float(v)
        if running <= 0:
            return k
    return len(order_desc)


def drawdown_profile(pnl) -> dict[str, float]:
    """Losing streak, drawdown depth, and time under water, in session units.

    Time under water counts sessions where cumulative P&L is below its running peak, with the
    peak starting at zero - so a strategy that loses on day one is under water from day one,
    which is what the account holder experiences. The recovery session itself is not counted
    as under water: the peak is regained at its close.
    """
    x = np.asarray(pnl, dtype=float)
    if not len(x):
        return {"longest_losing_streak": 0.0, "max_drawdown": 0.0,
                "longest_underwater": 0.0, "underwater_fraction": 0.0}
    equity = np.cumsum(x)
    peak = np.maximum.accumulate(np.maximum(equity, 0.0))
    under = equity < peak
    return {
        # A flat session breaks a losing streak, because the account did not lose money that
        # day. Untraded days are common in this repo's sleeves and counting them as losses
        # would inflate every streak reported here.
        "longest_losing_streak": float(_longest_run(x < 0)),
        "max_drawdown": float((peak - equity).max()),
        "longest_underwater": float(_longest_run(under)),
        "underwater_fraction": float(under.mean()),
    }


def _longest_run(flags) -> int:
    best = run = 0
    for f in np.asarray(flags, dtype=bool).tolist():
        run = run + 1 if f else 0
        best = max(best, run)
    return best


# =====================================================================================
# NULLS - measurements where a threshold would otherwise be invented
# =====================================================================================

def ordering_null(pnl, *, reps: int = 2000, seed: int = 0) -> dict[str, float]:
    """Are the streak and the drawdown unusual FOR THESE SESSIONS in a different order?

    Reshuffles the realised session P&Ls and recomputes the order-dependent metrics. The null
    is exchangeability - the same sessions, arrival order irrelevant - and nothing else is
    assumed: no distribution is fitted and no threshold is invented. Returned values are the
    fraction of shuffles at least as extreme as the observed one, so 0.02 means "only 2% of
    orderings of your own sessions were this bad".

    This is only meaningful for order-dependent metrics. Best-day share, the top-q shares,
    Gini and Herfindahl are permutation-INVARIANT, so shuffling tells you nothing about them;
    `tail_null` is the reference for those, and it has to assume a distribution to say
    anything at all.
    """
    x = np.asarray(pnl, dtype=float)
    if len(x) < 3:
        raise ValueError(f"need at least 3 sessions to shuffle, got {len(x)}")
    obs = drawdown_profile(x)
    rng = np.random.default_rng(seed)
    hits = {k: 0 for k in ("longest_losing_streak", "max_drawdown", "longest_underwater")}
    for _ in range(reps):
        sim = drawdown_profile(rng.permutation(x))
        for k in hits:
            if sim[k] >= obs[k]:
                hits[k] += 1
    return {f"p_{k}": hits[k] / reps for k in hits}


def tail_null(pnl, *, reps: int = 2000, seed: int = 0) -> dict[str, float]:
    """How concentrated would the profit look if the sessions were Gaussian and independent?

    THE ASSUMPTION IS THE POINT AND IS STATED: draws come from a normal with this series' own
    mean and standard deviation. That is a reference, not a belief about markets - session
    P&L is fat-tailed, so a real strategy will usually look more concentrated than this null,
    and the size of the gap is the useful part. A p-value near zero says "even allowing for
    the luck a Gaussian of the same size produces, this much of the profit came from this few
    days", which is a stronger statement than any fixed cut-off.
    """
    x = np.asarray(pnl, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        raise ValueError(f"need at least 3 sessions, got {len(x)}")
    obs = concentration(x)
    rng = np.random.default_rng(seed)
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    keys = ("best_day_share_gross", "herfindahl", "gini")
    hits = dict.fromkeys(keys, 0)
    for _ in range(reps):
        sim = concentration(rng.normal(mu, sd, size=len(x)))
        for k in keys:
            a, b = getattr(sim, k), getattr(obs, k)
            if math.isfinite(a) and math.isfinite(b) and a >= b:
                hits[k] += 1
    return {f"p_{k}": hits[k] / reps for k in keys}


# =====================================================================================
# PARAMETER SENSITIVITY (Part 34: a cliff means fragility)
# =====================================================================================

@dataclass(frozen=True)
class SensitivityReport:
    """How fast performance decays around the chosen parameter point."""

    best_key: tuple[float, ...]
    best_score: float
    n_points: int
    n_neighbours: int
    neighbour_mean: float
    neighbour_min: float
    neighbour_ratio: float
    worst_neighbour_ratio: float
    neighbour_sign_agreement: float
    plateau_fraction: float
    positive_fraction: float
    median_score: float
    per_axis_ratio: dict[str, float] = field(default_factory=dict)

    def table(self) -> str:
        rows = [
            ("best point", f"{self.best_key} -> {self.best_score:,.4g}"),
            ("grid", f"{self.n_points} points, median {self.median_score:,.4g}, "
                     f"{self.positive_fraction:.0%} positive"),
            ("neighbours", f"{self.n_neighbours}: mean {self.neighbour_mean:,.4g}, "
                           f"worst {self.neighbour_min:,.4g}"),
            ("neighbour ratio", f"mean {self.neighbour_ratio:.2f}, "
                                f"worst {self.worst_neighbour_ratio:.2f}, "
                                f"same sign {self.neighbour_sign_agreement:.0%}"),
            ("plateau", f"{self.plateau_fraction:.0%} of the grid within tolerance"),
        ]
        for axis, r in self.per_axis_ratio.items():
            rows.append((f"axis {axis}", f"ratio {r:.2f}"))
        width = max(len(k) for k, _ in rows)
        return "\n".join(f"  {k:<{width}}  {v}" for k, v in rows)


def parameter_sensitivity(scores: Mapping[tuple[float, ...], float], *,
                          axis_names: Sequence[str] | None = None,
                          tolerance: float = 0.5,
                          best_key: Sequence[float] | None = None) -> SensitivityReport:
    """Decay around the best point of a parameter grid. A cliff means fragility.

    `scores` maps a parameter tuple to a performance number where higher is better. Neighbours
    are the grid points one step away along exactly one axis, found by index in each axis's
    sorted unique values - so an irregular or partially-filled grid still works, and only
    points that actually exist are counted.

    WHY THE RATIO AND NOT THE DIFFERENCE. `neighbour_ratio` is mean(neighbour) / best, which
    is unit-free and comparable across strategies and objectives. Its reading is arithmetic at
    the ends: 1.0 means the neighbours are as good as the chosen point and the parameter is
    not doing much, while <= 0 means one step away the strategy loses money and the reported
    result exists only at that coordinate. Everything between is a judgement, and this module
    does not make it - see `METRIC_DOCS["neighbour_ratio"]`.

    `best_key` overrides the argmax. Pass it when the point of interest is the one a strategy
    actually ships with rather than the grid's best, which is the more honest question: the
    shipped point was chosen on this same grid, so its own maximum is selection.
    """
    if not scores:
        raise ValueError("parameter_sensitivity needs a non-empty grid")
    keys = [tuple(float(v) for v in k) for k in scores]
    vals = {tuple(float(v) for v in k): float(s) for k, s in scores.items()}
    dims = {len(k) for k in keys}
    if len(dims) != 1:
        raise ValueError(f"grid keys have differing lengths {sorted(dims)}; a neighbour is "
                         "one step along one axis and that is undefined here")
    ndim = dims.pop()
    names = list(axis_names) if axis_names is not None else [f"p{i}" for i in range(ndim)]
    if len(names) != ndim:
        raise ValueError(f"{len(names)} axis names for a {ndim}-dimensional grid")

    axes = [sorted({k[i] for k in keys}) for i in range(ndim)]
    pos = [{v: j for j, v in enumerate(axis)} for axis in axes]
    chosen = (tuple(float(v) for v in best_key) if best_key is not None
              else max(vals, key=lambda k: vals[k]))
    if chosen not in vals:
        raise ValueError(f"best_key {chosen} is not a point in the grid")
    best = vals[chosen]

    neighbours: dict[str, list[float]] = {n: [] for n in names}
    for i, name in enumerate(names):
        j = pos[i][chosen[i]]
        for step in (-1, 1):
            if 0 <= j + step < len(axes[i]):
                cand = list(chosen)
                cand[i] = axes[i][j + step]
                key = tuple(cand)
                if key in vals:
                    neighbours[name].append(vals[key])
    flat = [v for vs in neighbours.values() for v in vs]

    def ratio(v: float) -> float:
        # Undefined against a non-positive best point: dividing by it flips the sign of the
        # comparison and would report a cliff as a plateau.
        return v / best if best > 0 else float("nan")

    all_scores = np.array(list(vals.values()), dtype=float)
    if best > 0:
        within = float(np.mean(all_scores >= best * (1.0 - tolerance)))
    else:
        within = float("nan")
    return SensitivityReport(
        best_key=chosen,
        best_score=best,
        n_points=len(vals),
        n_neighbours=len(flat),
        neighbour_mean=(float(np.mean(flat)) if flat else float("nan")),
        neighbour_min=(float(np.min(flat)) if flat else float("nan")),
        neighbour_ratio=(ratio(float(np.mean(flat))) if flat else float("nan")),
        worst_neighbour_ratio=(ratio(float(np.min(flat))) if flat else float("nan")),
        neighbour_sign_agreement=(float(np.mean([np.sign(v) == np.sign(best) for v in flat]))
                                  if flat else float("nan")),
        plateau_fraction=within,
        positive_fraction=float(np.mean(all_scores > 0)),
        median_score=float(np.median(all_scores)),
        per_axis_ratio={n: (ratio(float(np.mean(vs))) if vs else float("nan"))
                        for n, vs in neighbours.items()},
    )


# =====================================================================================
# INTERPRETATION - and an honest line between measurement and judgement
# =====================================================================================

@dataclass(frozen=True)
class MetricDoc:
    """What a number means, what value should worry a reader, and on whose authority."""

    metric: str
    interpretation: str
    concern: str
    #: "arithmetic" - the reading follows from the definition and needs no opinion.
    #: "judgement" - somebody has to decide how much is too much. Nobody has, here.
    basis: str

    def __post_init__(self) -> None:
        if self.basis not in ("arithmetic", "judgement"):
            raise ValueError(f"basis must be arithmetic or judgement, got {self.basis!r}")


def _doc(metric: str, interpretation: str, concern: str, basis: str) -> MetricDoc:
    return MetricDoc(metric, interpretation, concern, basis)


METRIC_DOCS: dict[str, MetricDoc] = {d.metric: d for d in (
    _doc("n", "Sessions in the sample.",
         "Below roughly a hundred sessions every metric below is dominated by sampling noise "
         "and `search.Limits.min_sessions` already refuses at that floor - but the floor "
         "itself is a convention, not a derived number.", "judgement"),
    _doc("n_winners", "Sessions with positive P&L.",
         "Not a worry on its own; it is the denominator that makes `gini_floor` readable. A "
         "low count with a high total is the concentration story, and the fields below "
         "measure it directly.", "arithmetic"),
    _doc("total", "Net P&L over the sample.",
         "A total at or below zero makes every share against it meaningless, which is why "
         "those fields go NaN. Read `net_positive` first.", "arithmetic"),
    _doc("gross_profit", "Sum of winning sessions.",
         "The denominator for the `_gross` shares. Well defined whenever anything was ever "
         "made, which is why those variants exist.", "arithmetic"),
    _doc("gross_loss", "Sum of losing sessions, as a positive number.",
         "gross_loss close to gross_profit means the net is a small difference of two large "
         "numbers, so a small error in the cost model moves the result a lot. That is a "
         "statement about sensitivity, not about the sign of the edge.", "arithmetic"),
    _doc("net_positive", "Whether the sample made money at all.",
         "False invalidates every share taken against the net total. Nothing subtle.",
         "arithmetic"),
    _doc("best_day", "Largest single-session profit.",
         "Compare it with `mean * n`. Interesting only via the shares below.", "arithmetic"),
    _doc("best_day_share", "Best session's P&L as a fraction of the net total.",
         "1.0 means one session IS the strategy and the rest nets to nothing, and it can "
         "exceed 1.0 when the rest of the sample loses money - that is not an error, it is "
         "the worst case this metric describes. The arithmetic "
         "anchor is 1/n - what a single session contributes when every session contributes "
         "equally - so compare against that rather than a fixed number. Where to draw the "
         "line above it is a judgement; `tail_null` replaces it with a measurement.",
         "judgement"),
    _doc("best_day_share_gross", "Best session as a fraction of gross profit.",
         "Defined whenever anything was made, so it stays readable on a breakeven or losing "
         "sample where `best_day_share` cannot be. Same 1/n_winners anchor.", "arithmetic"),
    _doc("best_week_share", "Best ISO calendar week as a fraction of the net total.",
         "A week is five sessions, so the even-contribution anchor is about 5/n. A value "
         "several times that says the edge arrived in one week; whether that disqualifies "
         "the strategy depends on whether the week is explicable (an event, a regime) and "
         "that is a research judgement, not a threshold.", "judgement"),
    _doc("best_month_share", "Best calendar month as a fraction of the net total.",
         "Anchor is about 21/n. On a one-year sample a month is 8% of the sessions; a month "
         "carrying most of the year is a seasonal or single-event bet.", "judgement"),
    _doc("best_window_share", "Best ROLLING k-session run, as a fraction of the net total.",
         "Reported because the calendar variants can be flattered or punished by where the "
         "week boundary happens to fall. The rolling version is always at least as large as "
         "the calendar one for the same k, so it is the conservative reading.", "arithmetic"),
    _doc("top_share", "Profit share of the top 1% / 5% / 10% of sessions.",
         "The even-contribution anchors are 1%, 5% and 10%. The top decile producing the "
         "whole net total is common and not by itself damning - most trend strategies look "
         "like that - so the number to argue about is the top 1%, where a large share means "
         "a handful of sessions that may not recur.", "judgement"),
    _doc("herfindahl", "Sum of squared shares of gross profit, over winning sessions.",
         "Read it through `effective_sessions`, which is its reciprocal and is on a scale "
         "people can reason about.", "arithmetic"),
    _doc("effective_sessions", "1 / Herfindahl: the number of equally-sized winning sessions "
         "that would produce this much concentration.",
         "This is the honest headline for 'is it one lucky path'. It is an arithmetic "
         "identity, not a convention: 5.0 means the gross profit is as concentrated as five "
         "identical winning days, whatever the sample length. Compare it against "
         "`n_winners` - the ratio is how evenly the winning was spread - and against the "
         "number of independent bets the strategy claims to make.", "arithmetic"),
    _doc("gini", "Gini coefficient over per-session contributions to gross profit, with "
         "losing sessions entered as zero.",
         "0 is every session contributing equally, 1 is one session contributing everything. "
         "It cannot fall below `gini_floor`, so read the pair, never the Gini alone.",
         "arithmetic"),
    _doc("gini_floor", "1 - n_winners/n: the Gini a strategy would show if every winning "
         "session were identical.",
         "An arithmetic floor imposed by the loss rate, not a property of the strategy. A "
         "Gini of 0.6 on a sample that loses 60% of the time is perfectly even.",
         "arithmetic"),
    _doc("gini_winners", "Gini among winning sessions only, floor removed.",
         "This is the one to quote when comparing two strategies with different hit rates. "
         "Above roughly 0.6 the winning itself is lopsided - and 'roughly 0.6' is a "
         "judgement offered as a starting point, not an established threshold.", "judgement"),
    _doc("without_best", "Net total with the best 1, 5 and 10 sessions deleted.",
         "The blunt version of every metric above, and the one non-specialists read "
         "correctly. A total that goes negative after removing a handful of sessions from a "
         "multi-hundred-session sample is a strategy whose edge is those sessions.",
         "arithmetic"),
    _doc("days_to_zero", "How many of the best sessions must be deleted before the net total "
         "reaches zero.",
         "The single most quotable number here, and a fact about the sample rather than an "
         "opinion: 'this strategy is three days'. There is no threshold - the number itself "
         "is the argument, read against the sample length.", "arithmetic"),
    _doc("longest_losing_streak", "Longest run of consecutive losing sessions.",
         "Matters operationally rather than statistically: it is what the account holder has "
         "to sit through, and against a prop firm's trailing drawdown it is what liquidates. "
         "`ordering_null` says whether the run is unusual for these sessions in a different "
         "order, which is a measurement; any fixed 'more than N in a row is bad' is not.",
         "arithmetic"),
    _doc("max_drawdown", "Deepest fall of cumulative P&L below its running peak, with the "
         "peak starting at zero.",
         "Compare against the account's own limit rather than against a percentage: on a "
         "Topstep account the only threshold that exists is the MLL, and `twin` prices that "
         "properly including the intraday path this daily series cannot see.", "arithmetic"),
    _doc("longest_underwater", "Longest run of sessions spent below a previous peak.",
         "Time, not depth, is what ends most live deployments - a shallow drawdown lasting "
         "half the sample is harder to hold than a deep one that recovers in a week. Read "
         "with `p_longest_underwater` from `ordering_null`.", "arithmetic"),
    _doc("underwater_fraction", "Fraction of sessions spent below a previous peak.",
         "Near 1.0 with a positive total means the equity curve is a single late run-up: the "
         "strategy was losing or flat for almost the whole sample and made its money at the "
         "end, which is the pattern most easily produced by chance.", "arithmetic"),
    _doc("carry", "A regime's share of net profit divided by its share of sessions.",
         "1.0 is a fair share. A regime well above 1.0 is carrying the strategy, which is "
         "not automatically wrong - a volatility strategy SHOULD earn in high volatility - "
         "but it converts the result into a forecast that the regime recurs, and that "
         "forecast has to be argued separately.", "arithmetic"),
    _doc("neighbour_ratio", "Mean score of the immediate grid neighbours divided by the "
         "chosen point's score.",
         "At the ends the reading is arithmetic: at or above 1.0 the parameter barely "
         "matters, and at or below 0 the strategy loses money one grid step away and the "
         "result exists only at that coordinate. In between, where the cliff starts is a "
         "judgement - and it depends on the grid spacing, since a fine grid always looks "
         "flatter than a coarse one over the same parameter range.", "judgement"),
    _doc("worst_neighbour_ratio", "The single worst neighbour, same denominator.",
         "The mean can hide one bad side. An asymmetric decay - fine in one direction, a "
         "cliff in the other - usually means the parameter is standing in for something "
         "structural, like a threshold crossing the point where trades stop triggering.",
         "arithmetic"),
    _doc("plateau_fraction", "Share of the grid scoring within `tolerance` of the best point.",
         "Depends entirely on how wide a grid was searched, so it compares points within one "
         "study and nothing across studies. Both the tolerance and the grid bounds are "
         "choices.", "judgement"),
    _doc("positive_fraction", "Share of the grid with a positive score.",
         "The most robust thing a grid can tell you. If most of the neighbourhood makes "
         "money, the effect is not a coordinate; if one point of forty does, the search "
         "found the noise and the multiplicity correction should be paid on all forty.",
         "arithmetic"),
    _doc("neighbour_sign_agreement", "Share of neighbours with the same sign as the best.",
         "Below 1.0 means an adjacent parameter flips the direction of the result. Sign "
         "instability is worse than magnitude decay, because no amount of position sizing "
         "fixes it.", "arithmetic"),
    _doc("p_longest_losing_streak", "Fraction of random reorderings of the same sessions with "
         "a losing streak at least this long.",
         "A measurement with no distributional assumption. Near 1.0 the streak is ordinary "
         "for a series with this many losers; near 0 the losses clustered more than chance "
         "would arrange, which is the case where a block bootstrap matters (see "
         "`paths.clustering_premium`).", "arithmetic"),
    _doc("p_max_drawdown", "Same, for drawdown depth.",
         "Near 0 means the realised ordering was unusually unkind - the strategy's own "
         "sessions in a different order would mostly have drawn down less.", "arithmetic"),
    _doc("p_longest_underwater", "Same, for time under water.", "As above.", "arithmetic"),
    _doc("p_best_day_share_gross", "Fraction of Gaussian samples, matched on this series' own "
         "mean and standard deviation, whose best-day share is at least as large.",
         "Small means the profit is more concentrated than a same-sized Gaussian sample "
         "would usually produce. It is a reference, not a test: the Gaussian null is known "
         "to be wrong for session P&L, and it is stated rather than hidden.", "arithmetic"),
    _doc("p_herfindahl", "Same, for the Herfindahl index.", "As above.", "arithmetic"),
    _doc("p_gini", "Same, for the Gini coefficient.", "As above.", "arithmetic"),
)}


@dataclass(frozen=True)
class Reading:
    """One metric's value with its documentation attached."""

    metric: str
    value: object
    interpretation: str
    concern: str
    basis: str


#: Identifiers and raw inputs rather than metrics: they say WHERE on the grid a reading came
#: from, or feed a ratio that is documented in their place. Everything else must be in
#: METRIC_DOCS, and `undocumented()` is the check that keeps that true.
_NOT_METRICS = frozenset({
    "best_key", "best_score", "n_points", "n_neighbours", "neighbour_mean", "neighbour_min",
    "median_score", "per_axis_ratio",
})


def readings(report: ConcentrationReport | SensitivityReport) -> list[Reading]:
    """Pair every reported metric with its documented interpretation.

    Refuses on an undocumented field rather than skipping it: a metric with no stated
    interpretation is a number a reader will interpret anyway, and usually in whichever
    direction flatters the strategy.
    """
    out: list[Reading] = []
    for f in fields(report):
        if f.name in _NOT_METRICS:
            continue
        doc = METRIC_DOCS.get(f.name)
        if doc is None:
            raise KeyError(f"{f.name} has no entry in METRIC_DOCS; every reported metric "
                           "needs a documented interpretation")
        out.append(Reading(f.name, getattr(report, f.name), doc.interpretation,
                           doc.concern, doc.basis))
    return out


def undocumented() -> set[str]:
    """Report fields with no METRIC_DOCS entry. Empty is the only acceptable answer."""
    named = {f.name for f in fields(ConcentrationReport)}
    named |= {f.name for f in fields(SensitivityReport)}
    return (named - _NOT_METRICS) - set(METRIC_DOCS)


def judgements() -> list[str]:
    """Every metric whose worrying value is somebody's opinion. Print it next to a report."""
    return sorted(k for k, v in METRIC_DOCS.items() if v.basis == "judgement")


__all__ = [
    "Bucket", "ConcentrationReport", "DEFAULT_BUCKETS", "DEFAULT_TZ", "GLOBEX_BUCKETS",
    "GLOBEX_ROLLOVER", "METRIC_DOCS", "MetricDoc", "RTH_CLOSE", "RTH_OPEN", "Reading",
    "RegimeLabeller", "RegimeRow", "SensitivityReport", "SessionRecord", "WARMUP",
    "align_sessions", "assert_causal_labels", "audit_label_causality", "bucket_spans",
    "carried_by", "concentration", "coverage", "drawdown_profile", "intraday_attribution",
    "judgements", "label_table", "labellers", "ordering_null", "parameter_sensitivity",
    "pnl_and_dates", "readings", "regime_performance", "session_table", "tail_null",
    "undocumented",
]
