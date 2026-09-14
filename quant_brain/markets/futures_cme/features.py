"""The futures feature library: families, provenance, and a refusal to invent data.

Part 7. Each feature declares what it needs and is REFUSED if the store cannot supply it.
That is the whole design, and it exists because of one line in the brief: "Never fabricate
microstructure features from OHLCV."

That line is easy to agree with and easy to violate. Bar-level "order flow" reconstructed
from OHLCV is the classic case - it looks like microstructure, it is named like
microstructure, and it is a noisier copy of the return. This repository already measured
exactly that: F-14 found reconstructed bar-level flow was 0.65-correlated with the 30-minute
return and that twenty columns of SCRAMBLED flow performed the same as the real ones. So
`REQUIRES` is enforced rather than documented: a feature needing `bid`/`ask` on a store that
has neither is not computed, not approximated, and not silently zero-filled. It is absent,
and `missing()` names it.

NO-LOOKAHEAD IS A PROPERTY, NOT A CONVENTION
----------------------------------------------
Every feature here is causal by construction: it is a function of bars at or before its own
timestamp. `assert_causal` verifies that empirically rather than trusting the arithmetic - it
perturbs a future bar and checks nothing earlier moves. A rolling window with the wrong
`closed` argument, or a centred window, passes review and fails that test.

The perturbation itself has to be WIDE (every column present, not a hard-coded OHLCV tuple),
DISORDERED (a per-row random draw, not a uniform scale) and compared EXACTLY (not
`np.isclose`). Each of those three is a leak the first version of this guard measurably let
through; `_assert_causal_at` records which, and what each one was worth.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

FeatureFn = Callable[..., object]


@dataclass(frozen=True)
class Feature:
    """One named column, its family, and what the store must contain to build it."""

    name: str
    family: str
    fn: FeatureFn
    requires: tuple[str, ...] = ("c",)
    #: Bars of history consumed. Used to trim the warm-up region, which otherwise carries
    #: NaNs or - worse - partially-formed values that look like data.
    warmup: int = 0
    describe: str = ""

    def available(self, columns) -> bool:
        return all(c in columns for c in self.requires)


@dataclass
class FeatureSet:
    """A library of features, built against one frame, refusing what it cannot support."""

    features: list[Feature] = field(default_factory=list)

    def add(self, feature: Feature) -> FeatureSet:
        if any(f.name == feature.name for f in self.features):
            raise ValueError(f"duplicate feature name {feature.name!r}; two columns with one "
                             "name is a silent overwrite in every downstream join")
        self.features.append(feature)
        return self

    def families(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for f in self.features:
            out.setdefault(f.family, []).append(f.name)
        return out

    def missing(self, columns) -> dict[str, tuple[str, ...]]:
        """Features this store cannot support, and the columns each one wanted.

        The point of the exercise. A store with no quotes must produce an empty
        microstructure family and say so, rather than a plausible one built from OHLCV.
        """
        cols = set(columns)
        return {f.name: tuple(c for c in f.requires if c not in cols)
                for f in self.features if not f.available(cols)}

    def build(self, df, *, strict: bool = True):
        """Compute every supported feature. Returns (frame, skipped).

        `strict` refuses to proceed when a feature is unsupported, which is the right default
        for a research run: silently returning a narrower matrix than the caller asked for is
        how a model comes to be trained on a different feature set than its author believes.
        """
        import pandas as pd

        cols = set(df.columns)
        skipped = self.missing(cols)
        if skipped and strict:
            detail = "; ".join(f"{k} needs {v}" for k, v in skipped.items())
            raise ValueError(
                f"this store cannot support {len(skipped)} feature(s): {detail}. "
                "Fetch the missing columns, or pass strict=False and accept a narrower "
                "matrix - but the narrower matrix is what your model will actually see.")
        out = {}
        for f in self.features:
            if f.name in skipped:
                continue
            out[f.name] = f.fn(df)
        return pd.DataFrame(out, index=df.index), skipped

    @property
    def warmup(self) -> int:
        return max((f.warmup for f in self.features), default=0)


# =====================================================================================
# THE FAMILIES (Part 7)
# =====================================================================================

def _c(df):
    import pandas as pd
    return pd.Series(df["c"].to_numpy(dtype=float), index=df.index)


def _v(df):
    import pandas as pd
    return pd.Series(df["v"].to_numpy(dtype=float), index=df.index)


def _nz(x):
    """Zeros to NaN before a division. A zero denominator here is an empty window, not a
    ratio of zero, and letting it through produces an inf that survives every later check."""
    import pandas as pd
    return pd.Series(x).replace(0.0, float("nan"))


def _ret(df, n):
    c = _c(df)
    return c.pct_change(n)


def _zscore(x, n):
    m = x.rolling(n).mean()
    s = x.rolling(n).std(ddof=0)
    return (x - m) / s.replace(0.0, float("nan"))


def library() -> FeatureSet:
    """The standard futures feature set. Every entry names its family and its inputs."""
    fs = FeatureSet()

    # --- price / momentum ---------------------------------------------------------------
    for n in (5, 15, 30, 60):
        fs.add(Feature(f"ret_{n}", "momentum", (lambda d, n=n: _ret(d, n)), ("c",), n,
                       f"{n}-bar return"))
    fs.add(Feature("accel_30", "momentum",
                   lambda d: _ret(d, 15) - _ret(d, 30).shift(15), ("c",), 45,
                   "change in 15-bar momentum, i.e. acceleration"))

    # --- mean reversion -------------------------------------------------------------------
    fs.add(Feature("vwap_dist", "meanrev",
                   lambda d: (_c(d) - (_c(d) * _v(d)).cumsum() / _v(d).cumsum().replace(0, 1))
                   / _c(d), ("c", "v"), 0,
                   "distance from session VWAP, as a fraction of price"))
    for n in (30, 120):
        fs.add(Feature(f"ma_dist_{n}", "meanrev",
                       (lambda d, n=n: _c(d) / _c(d).rolling(n).mean() - 1.0), ("c",), n,
                       f"distance from the {n}-bar moving average"))
    fs.add(Feature("z_60", "meanrev", lambda d: _zscore(_c(d), 60), ("c",), 60,
                   "60-bar z-score of price"))

    # --- volatility -------------------------------------------------------------------------
    for n in (30, 120):
        fs.add(Feature(f"rvol_{n}", "volatility",
                       (lambda d, n=n: _c(d).pct_change().rolling(n).std(ddof=0)),
                       ("c",), n, f"{n}-bar realised volatility"))
    fs.add(Feature("range_expansion", "volatility",
                   lambda d: ((_hl(d)).rolling(15).mean() / (_hl(d)).rolling(120).mean()),
                   ("h", "l", "c"), 120,
                   "short-window range over long-window range; >1 is expansion"))
    fs.add(Feature("vol_of_vol", "volatility",
                   lambda d: _c(d).pct_change().rolling(30).std(ddof=0)
                   .rolling(120).std(ddof=0), ("c",), 150,
                   "instability of the volatility estimate itself"))

    # --- volume ------------------------------------------------------------------------------
    fs.add(Feature("rel_volume", "volume",
                   lambda d: _v(d) / _nz(_v(d).rolling(120).mean()),
                   ("v",), 120, "volume relative to its own 120-bar mean"))
    fs.add(Feature("volume_accel", "volume",
                   lambda d: _v(d).rolling(15).mean() / _nz(_v(d).rolling(60).mean()),
                   ("v",), 60, "short over long volume"))

    # --- session / time -----------------------------------------------------------------------
    fs.add(Feature("minutes_from_open", "session", _minutes_from_open, ("c",), 0,
                   "bars elapsed since the session's first bar"))
    fs.add(Feature("opening_range_pos", "session", _opening_range_pos, ("h", "l", "c"), 0,
                   "position within the first 30 minutes' range"))

    # --- microstructure: DECLARED, and absent unless the store can support it ---------------
    # These are the reason `requires` is enforced. On an OHLCV store they must not appear at
    # all - a reconstructed version would be a noisier copy of the return wearing a
    # microstructure name, which F-14 already measured in this repository.
    fs.add(Feature("spread_bps", "microstructure",
                   lambda d: (d["ask"] - d["bid"]) / _c(d) * 10_000.0,
                   ("bid", "ask", "c"), 0, "quoted spread in basis points"))
    fs.add(Feature("quote_imbalance", "microstructure",
                   lambda d: (d["bid_size"] - d["ask_size"])
                   / (d["bid_size"] + d["ask_size"]).replace(0, float("nan")),
                   ("bid_size", "ask_size"), 0, "top-of-book size imbalance"))
    return fs


def _hl(df):
    import pandas as pd
    return (pd.Series(df["h"].to_numpy(dtype=float), index=df.index)
            - pd.Series(df["l"].to_numpy(dtype=float), index=df.index))


def _minutes_from_open(df):
    import numpy as np
    import pandas as pd
    return pd.Series(np.arange(len(df), dtype=float), index=df.index)


def _opening_range_pos(df):
    """Position within the opening range, using only bars that have already happened.

    THE BUG THIS REPLACES, because it is worth keeping in front of whoever reads this next.
    The first version took the max and min of the first 30 bars and divided every bar of the
    session by that range - INCLUDING the first 30. So at bar 5 the feature already knew the
    high and low of bars 6 through 29. It is a small window and an easy thing to write.

    It was not a small effect. It was the only hypothesis to survive the discovery funnel
    across 272 candidates on two contracts, at t = +6.25 against a 3.56 multiplicity bar,
    5 of 5 walk-forward folds positive, and $140.75 per session on a single MNQ - roughly 70
    NQ points of daily edge, which is the number that gave it away. A leak reads exactly like
    a strong edge, and the stronger it reads the more likely that is what it is.

    Now expanding: at bar i the range covers bars 0..min(i, 29), so the denominator can only
    use information that exists at i. After bar 30 it is the fixed opening range, which is
    what the feature was always meant to be.
    """
    import pandas as pd
    h = pd.Series(df["h"].to_numpy(dtype=float), index=df.index)
    low = pd.Series(df["l"].to_numpy(dtype=float), index=df.index)
    c = _c(df)
    n = min(30, len(df))
    # Expanding within the opening window, frozen at its close.
    hi = h.expanding().max()
    lo = low.expanding().min()
    if len(df) > n:
        hi.iloc[n:] = hi.iloc[n - 1]
        lo.iloc[n:] = lo.iloc[n - 1]
    rng = (hi - lo).replace(0.0, float("nan"))
    return ((c - lo) / rng).fillna(0.0)


# =====================================================================================
# CAUSALITY
# =====================================================================================

def assert_causal(feature: Feature, df, *, at: int | None = None, seed: int = 0) -> None:
    """Verify empirically that a feature does not read the future.

    Perturbs a bar and checks that no EARLIER value of the feature moves. Arithmetic review
    does not catch a centred rolling window or a wrong `closed` argument; this does.

    WHY IT SWEEPS RATHER THAN PROBING ONCE
    The first version tested a single index at 80% through the series, and that is how
    `opening_range_pos` shipped with a lookahead: its leak was confined to the first 30 bars,
    so a perturbation at bar 310 could not possibly reveal it, and the check passed with a
    clean bill of health on a feature that already knew the future. A single probe only tests
    the window it lands in. This sweeps early, middle and late, and the early points are the
    ones that earned their place.
    """
    if not feature.available(set(df.columns)):
        return
    n = len(df)
    if at is not None:
        points = [at]
    else:
        # Deliberately weighted toward the start. Session-anchored features - opening ranges,
        # first-N-bar statistics, anything with a warm-up - leak there and nowhere else.
        candidates = [3, 5, 10, 20, 31, feature.warmup + 2,
                      int(n * 0.25), int(n * 0.5), int(n * 0.8)]
        points = sorted({p for p in candidates if 0 < p < n - 1})
    if not points:
        raise ValueError(f"{feature.name}: frame of {n} rows is too short to test causality")
    for point in points:
        _assert_causal_at(feature, df, point, seed)


def _assert_causal_at(feature: Feature, df, at: int, seed: int = 0) -> None:
    """Rewrite every column from bar `at` onward and require the head to be bit-identical.

    THREE BLIND SPOTS THIS CLOSES. Each was measured against the version that shipped before
    it, by the counter-examples in `tests/test_leakage_redteam.py` section E.

    WIDE, NOT OHLCV. The first version perturbed the hard-coded tuple ("c", "h", "l", "o")
    plus "v" and nothing else, so `bid.shift(-1)` - tomorrow's bid, a leak wearing no
    disguise at all - came back bit-identical and the guard called it clean. A bump that
    included the quote columns found the same leak at bar 207 of 320. The consequence was
    worse than one missed counter-example: the library's own microstructure family declares
    `bid`, `ask`, `bid_size` and `ask_size`, the guard touched none of them, and so
    `spread_bps` and `quote_imbalance` had never once been tested by the audit that reports
    them clean. `requires` is the floor here, not the ceiling - `fn` is handed the WHOLE
    frame, so stopping at the declared set would exempt any feature that under-declares the
    columns it actually reads.

    RANDOM, NOT A UNIFORM SCALE. The first version multiplied the tail by a constant (1.05
    for prices, 3.0 for volume), and a uniform positive multiplier PRESERVES ORDER. Anything
    reading only the order of future bars - an argmax, a rank, "which came first", any order
    statistic over a window that lies wholly inside the bumped region - is exactly invariant
    to it. A feature returning the argmax of the session's last five closes was bit-identical
    under the shipped bump and is caught by a per-row draw. The draw is seeded, and the seed
    defaults to a constant, because a guard whose verdict changes between runs is not a
    guard: a leak that fails on one run and passes on the next gets re-run until it passes.

    EXACT, NOT `np.isclose`. The first version compared with rtol 1e-5 / atol 1e-8. A leak
    carried at amplitude 1e-9 on a base of 1.0 sits inside that tolerance and was reported
    clean - and its SIGN recovers the next bar's direction exactly, which the red team
    pushed through the funnel for 100.00% of the theoretical profit ceiling. A leak's
    amplitude and a leak's value are different quantities, and an absolute floor confuses
    them. The comparison is now exact, and it can afford to be: every feature in this library
    is elementwise or forward-cumulative (`cumsum`, `rolling`, `expanding`), so a head row is
    computed from the same inputs in the same order before and after and comes back
    bit-identical - verified on the shipped nineteen over both quoted fixtures and the
    adversarial golden series. If a future feature ever genuinely needs slack, scale it to
    that column's own dispersion; an absolute atol is the thing that made 1e-9 invisible.
    """
    import numpy as np
    import pandas as pd

    base = np.asarray(feature.fn(df), dtype=float)
    bumped = df.copy()
    rng = np.random.default_rng(seed)
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            # A timestamp or a contract code has no magnitude to scale. Nothing in this
            # library declares a non-numeric input; one that did would need a permutation,
            # not this perturbation, and this is the place to add it.
            continue
        vals = df[col].to_numpy(dtype=float).copy()
        tail = vals[at:]
        # Scale AND jitter. Zero is a fixed point of a pure multiplier, so an empty-volume
        # or all-zero stretch would otherwise be handed to the feature unchanged.
        spread = float(np.nanstd(tail))
        if not np.isfinite(spread) or spread == 0.0:
            spread = 1.0
        vals[at:] = (tail * rng.uniform(1.5, 4.5, tail.shape)
                     + rng.normal(0.0, spread, tail.shape))
        bumped[col] = vals
    after = np.asarray(feature.fn(bumped), dtype=float)

    head_base, head_after = base[:at], after[:at]
    both_nan = np.isnan(head_base) & np.isnan(head_after)
    # `!=`, not `np.isclose` - see EXACT above. NaN != NaN, so `both_nan` is what stops a
    # legitimate warm-up NaN from reading as a change.
    differs = ~both_nan & (head_base != head_after)
    if differs.any():
        first = int(np.argmax(differs))
        raise AssertionError(
            f"{feature.name} is not causal: perturbing bar {at} changed the value at bar "
            f"{first} ({head_base[first]} -> {head_after[first]}). A centred window, a wrong "
            f"`closed` argument, or a session-anchored statistic applied inside its own "
            f"anchoring window are the usual causes.")


def audit_causality(fs: FeatureSet, df) -> dict[str, str]:
    """Run `assert_causal` over a whole library. Returns the failures, empty when clean."""
    out: dict[str, str] = {}
    for f in fs.features:
        try:
            assert_causal(f, df)
        except AssertionError as exc:
            out[f.name] = str(exc)
        except Exception as exc:                                        # noqa: BLE001
            out[f.name] = f"{type(exc).__name__}: {exc}"
    return out
