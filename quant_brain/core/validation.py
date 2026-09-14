"""Purged, embargoed walk-forward cross-validation, and a holdout that can only be spent once.

Part 13. The existing statistics module already refuses to report an IID t-statistic on
overlapping labels - `stats.tstat_hac` will not accept a lag below h-1. This module closes
the other half of the same leak, the one that lives in how the folds are cut rather than in
how the statistic is computed.

WHY PLAIN K-FOLD IS INVALID HERE, CONCRETELY
---------------------------------------------
A label with a 21-bar horizon formed at time t is a function of prices through t+21. A naive
split that puts t in the training set and t+3 in the test set has trained on a label that
already contains 18 bars of the test period. The model does not need to generalise; it can
recall. This is not a small effect - AUD-18 in this repository watched F-3's t-statistic fall
from 2.41 to 0.79 on the horizon correction alone, on a signal that looked significant.

Two separate corrections are needed and they are not the same thing:

    PURGE     drop training observations whose LABEL WINDOW overlaps the test fold. Fixes the
              leak described above. Its width is the label horizon.
    EMBARGO   additionally drop training observations immediately AFTER the test fold. Fixes a
              subtler leak: serial correlation in features means a bar just after the test
              period carries information about it even when no label window overlaps. Its
              width is a judgement about feature persistence, not about the label.

Both are in Lopez de Prado's Advances in Financial Machine Learning (2018), ch. 7.

A finding worth stating up front, because the brief asks for "purged and embargoed
walk-forward" and the two words do not carry equal weight here: under STRICT WALK-FORWARD THE
EMBARGO IS STRUCTURALLY VACUOUS. Every training row precedes the test fold by construction,
so the set of training rows following the test fold is empty and the embargo removes nothing,
at any width. The purge does all of the work. An embargo becomes essential only when training
data exists on both sides of the test block, which is `purged_kfold` below - offered for
short histories, with the look-ahead that buys it stated plainly. Tests assert zero removed
in the first case and non-zero in the second, so this is measured rather than argued.

WHAT THIS MODULE WILL NOT DO
----------------------------
It will not guess a horizon. `purged_walk_forward` requires one, because the purge width IS
the horizon and defaulting it to zero would produce splits that look purged, pass every test,
and leak exactly as much as no purging at all. Silent zero is the dangerous default here.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


class LeakageError(AssertionError):
    """A split was constructed or used in a way that lets test information into training."""


@dataclass(frozen=True)
class Split:
    """One fold: the rows to train on, the rows to test on, and what was removed and why.

    `purged` and `embargoed` are kept as explicit counts rather than being folded into
    `train`, so a caller can see how much data the correction actually cost. When that number
    is a large fraction of the sample, the honest conclusion is usually that the horizon is
    too long for the history available - which is a finding, not a nuisance.
    """

    fold: int
    train: np.ndarray
    test: np.ndarray
    purged: int
    embargoed: int

    @property
    def train_size(self) -> int:
        return int(self.train.size)

    @property
    def test_size(self) -> int:
        return int(self.test.size)

    @property
    def dropped(self) -> int:
        return self.purged + self.embargoed

    def __str__(self) -> str:
        return (f"fold {self.fold}: train {self.train_size}, test {self.test_size}, "
                f"purged {self.purged}, embargoed {self.embargoed}")


def purged_walk_forward(n: int, *, horizon: int, folds: int = 5,
                        embargo: int | float = 0.0,
                        min_train: int = 1,
                        expanding: bool = True) -> list[Split]:
    """Walk-forward folds with the label horizon purged and an embargo after each test fold.

    Walk-forward rather than shuffled k-fold: every test fold lies strictly after its
    training data. A shuffled fold trains on the future to predict the past, which no amount
    of purging repairs.

    `horizon` is the label's forward span in ROWS - the same h that `stats.lag_for_overlap`
    takes, and the same h that makes overlapping labels an MA(h-1). It is required.

    `embargo` is either a row count or, when a float below 1, a fraction of `n`. It is
    accepted, computed, and reported - and under strict walk-forward it always removes ZERO
    rows. That is not a bug, and it is worth stating plainly rather than leaving the knob to
    imply otherwise: an embargo protects the test fold from training rows that come AFTER it,
    and in walk-forward every training row precedes the test fold by construction. The
    embargo does real work in `purged_kfold`, where training resumes on the far side of the
    test block. `test_qb_validation.py` asserts both facts, so neither has to be taken on
    trust.

    `expanding` grows the training window from the start; False gives a rolling window of
    roughly one fold's length, which is the right choice when the process is believed to
    drift and the wrong one when data is scarce.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if horizon < 0:
        raise ValueError(f"horizon must be non-negative, got {horizon}")
    if folds < 2:
        raise ValueError(f"folds must be at least 2, got {folds}")
    emb = int(round(embargo * n)) if 0 < embargo < 1 else int(embargo)
    if emb < 0:
        raise ValueError(f"embargo must be non-negative, got {embargo}")

    idx = np.arange(n)
    # Test folds tile the tail of the sample; the first block is training-only, because a
    # walk-forward scheme has nothing to train on before its first test fold.
    block = n // (folds + 1)
    if block < 1:
        raise ValueError(f"{n} observations cannot make {folds} walk-forward folds; "
                         f"each fold would be empty")

    splits: list[Split] = []
    for k in range(folds):
        test_start = block * (k + 1)
        test_end = n if k == folds - 1 else block * (k + 2)
        test = idx[test_start:test_end]

        # Training is everything before the test fold, minus the purge and the embargo.
        # An expanding window starts at 0; a rolling one keeps roughly one block.
        lo = 0 if expanding else max(0, test_start - block)
        candidate = idx[lo:test_start]

        # PURGE: a training row at time i carries a label spanning [i, i+horizon]. It leaks
        # if that span reaches the test fold, i.e. i + horizon >= test_start.
        keep = candidate[candidate + horizon < test_start]
        purged = int(candidate.size - keep.size)

        # EMBARGO: remove training rows in (test_end, test_end + emb]. Under strict
        # walk-forward this set is ALWAYS empty - see the note on `embargo` in the docstring -
        # so the computation is kept only because it is the definition, and a test asserts the
        # count is zero rather than letting the parameter imply work it does not do.
        keep, embargoed = _embargo(keep, test, emb)
        splits.append(Split(fold=k, train=keep, test=test, purged=purged,
                            embargoed=embargoed))

    if min_train > 0:
        short = [s for s in splits if s.train_size < min_train]
        if short:
            raise ValueError(
                f"folds {[s.fold for s in short]} have fewer than min_train={min_train} "
                f"training rows after purging {horizon} and embargoing {emb}. With "
                f"n={n} and {folds} folds the correction has eaten the sample; use a shorter "
                f"horizon, fewer folds, or accept that this history cannot support the test.")
    return splits


def _embargo(train: np.ndarray, test: np.ndarray, emb: int) -> tuple[np.ndarray, int]:
    """Drop training rows in the `emb` rows immediately following the test fold.

    This is the definition, applied to one fold against its own test set. An earlier draft
    of this function banned rows following *earlier* test folds from *later* training sets,
    which discards data without protecting anything: the leak an embargo prevents is
    information flowing from a training row into the test fold being scored right now, and a
    row that follows fold 0's test set is ordinary history by the time fold 2 trains.
    """
    if emb <= 0 or train.size == 0 or test.size == 0:
        return train, 0
    t1 = int(test[-1])
    keep = train[(train <= t1) | (train > t1 + emb)]
    return keep, int(train.size - keep.size)


def purged_kfold(n: int, *, horizon: int, folds: int = 5,
                 embargo: int | float = 0.01) -> list[Split]:
    """Interior test folds with training on BOTH sides - where the embargo earns its keep.

    Use this only when the history is too short for walk-forward to leave usable folds. It
    buys test coverage of the whole sample by training on data that comes after the test
    fold, which is a look-ahead in the FITTING even though the labels are purged. That is a
    real concession: a model tuned this way has seen the future's regime, and its score is an
    upper bound on what walk-forward would give. Lopez de Prado accepts the trade in the
    combinatorial purged scheme; this repository's default should stay walk-forward.

    Here the embargo is not decorative. Training resumes immediately after the test fold, so
    without it the first rows of training are serially correlated with the last rows of test.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if horizon < 0:
        raise ValueError(f"horizon must be non-negative, got {horizon}")
    if folds < 2:
        raise ValueError(f"folds must be at least 2, got {folds}")
    emb = int(round(embargo * n)) if 0 < embargo < 1 else int(embargo)
    if emb < 0:
        raise ValueError(f"embargo must be non-negative, got {embargo}")

    idx = np.arange(n)
    edges = np.linspace(0, n, folds + 1).astype(int)
    out: list[Split] = []
    for k in range(folds):
        t0, t1 = int(edges[k]), int(edges[k + 1])
        if t1 <= t0:
            raise ValueError(f"{n} observations cannot make {folds} folds; fold {k} is empty")
        test = idx[t0:t1]
        candidate = np.concatenate([idx[:t0], idx[t1:]])
        # Purge on the left: label windows reaching into the test fold.
        keep = candidate[(candidate + horizon < t0) | (candidate >= t1)]
        purged = int(candidate.size - keep.size)
        keep, embargoed = _embargo(keep, test, emb)
        out.append(Split(fold=k, train=keep, test=test, purged=purged, embargoed=embargoed))
    return out


def assert_no_leakage(split: Split, *, horizon: int, embargo: int = 0,
                      walk_forward: bool = True) -> None:
    """Verify a split really is purged and embargoed. Cheap, so run it in anger.

    A split-generating function is exactly the kind of code that looks right, passes its
    unit tests on toy sizes, and quietly stops purging at some boundary. This checks the
    property directly rather than the implementation.

    `walk_forward` also requires that no training row follows the test fold. It must be
    switched off for `purged_kfold`, whose whole purpose is training on both sides - passing
    a k-fold split with it on is not a leak, it is the wrong checker.
    """
    if split.train.size == 0 or split.test.size == 0:
        return
    t0, t1 = int(split.test[0]), int(split.test[-1])
    overlap = split.train[(split.train + horizon >= t0) & (split.train <= t1)]
    if overlap.size:
        raise LeakageError(
            f"fold {split.fold}: {overlap.size} training rows have label windows reaching "
            f"the test fold [{t0}, {t1}] at horizon {horizon}, first at index "
            f"{int(overlap[0])}")
    if embargo:
        inside = split.train[(split.train > t1) & (split.train <= t1 + embargo)]
        if inside.size:
            raise LeakageError(
                f"fold {split.fold}: {inside.size} training rows fall inside the "
                f"{embargo}-row embargo after the test fold, first at {int(inside[0])}")
    if walk_forward and int(split.train.max()) > t1:
        raise LeakageError(
            f"fold {split.fold}: training row {int(split.train.max())} lies after the test "
            f"fold ending at {t1}; this is not walk-forward")


def coverage(splits: Sequence[Split], n: int) -> dict[str, float]:
    """What the correction cost, as fractions. Report this beside any CV result.

    A result from folds that used 30% of the data is a different claim from one that used
    90%, and the difference is invisible in the score itself.
    """
    if not splits:
        return {"train": 0.0, "test": 0.0, "purged": 0.0, "embargoed": 0.0}
    tested = np.unique(np.concatenate([s.test for s in splits])).size
    return {
        "train": float(np.mean([s.train_size for s in splits]) / n),
        "test": float(tested / n),
        "purged": float(sum(s.purged for s in splits) / n),
        "embargoed": float(sum(s.embargoed for s in splits) / n),
    }


# ======================================================================================
# THE FINAL HOLDOUT
# ======================================================================================

@dataclass
class Holdout:
    """A block of data at the end of the sample that may be evaluated once.

    Part 13 asks for a strict final holdout. "Strict" is the whole content of the idea: a
    holdout that gets looked at after each modelling attempt is a validation set with a
    misleading name, and its out-of-sample claim is worth nothing. The only way to make it
    strict is to make re-use detectable, so every evaluation is appended to a ledger on disk
    keyed by the data's own fingerprint, and a second evaluation of the same holdout raises
    unless the caller says out loud that it is spending another look.

    This cannot stop a determined user - nothing can, it is their machine - but it stops the
    thing that actually happens, which is a holdout being spent by accident across sessions
    and nobody noticing.
    """

    n: int
    fraction: float
    ledger_path: Path
    fingerprint: str
    label: str = ""

    @property
    def start(self) -> int:
        return self.n - self.size

    @property
    def size(self) -> int:
        return max(1, int(round(self.n * self.fraction)))

    @property
    def train_index(self) -> np.ndarray:
        return np.arange(self.start)

    @property
    def test_index(self) -> np.ndarray:
        return np.arange(self.start, self.n)

    def purged_train_index(self, horizon: int) -> np.ndarray:
        """Training rows whose label windows do not reach into the holdout.

        The same purge the CV folds get. Omitting it here is a common and expensive slip:
        the holdout is the one number that gets quoted, and a leak in it is a leak in the
        headline.
        """
        idx = self.train_index
        return idx[idx + horizon < self.start]

    def looks(self) -> list[dict]:
        """Every evaluation recorded against this fingerprint."""
        if not self.ledger_path.exists():
            return []
        out = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("fingerprint") == self.fingerprint:
                out.append(rec)
        return out

    def spend(self, *, result: dict, note: str, force: bool = False) -> dict:
        """Record one evaluation of the holdout. Raises on a second look unless forced.

        `note` is required and is not decoration: the ledger is only useful if a later reader
        can tell what was tried, and "why did I look again" is the question the ledger exists
        to answer.
        """
        if not note.strip():
            raise ValueError("a holdout evaluation must be recorded with a note saying what "
                             "was evaluated and why; the ledger is worthless without it")
        prior = self.looks()
        if prior and not force:
            first = prior[0]
            raise LeakageError(
                f"this holdout ({self.label or self.fingerprint[:12]}) has already been "
                f"evaluated {len(prior)} time(s), first on {first.get('when')} - "
                f"{first.get('note')!r}. Every further look makes the out-of-sample claim "
                f"weaker, and the second look is where most of the damage is done. If you "
                f"genuinely intend to spend another, pass force=True; the ledger will record "
                f"that this was look number {len(prior) + 1}.")
        rec = {
            "when": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "fingerprint": self.fingerprint,
            "label": self.label,
            "look": len(prior) + 1,
            "forced": bool(prior),
            "n": self.n,
            "holdout_size": self.size,
            "note": note,
            "result": result,
        }
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
        return rec


def make_holdout(data, *, fraction: float = 0.2, ledger_path: str | Path,
                 label: str = "") -> Holdout:
    """Carve the final `fraction` of a series off as a write-once holdout.

    The fingerprint is taken from the data itself, so the same series carved the same way is
    the same holdout across sessions and processes - which is what makes the ledger able to
    notice a second look taken next week rather than only one taken in this function call.
    """
    arr = np.asarray(data)
    if arr.ndim == 0 or arr.size == 0:
        raise ValueError("cannot build a holdout from an empty series")
    if not 0 < fraction < 1:
        raise ValueError(f"fraction must be in (0, 1), got {fraction}")
    n = int(arr.shape[0])
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(arr, dtype=np.float64).tobytes())
    digest.update(f"|{n}|{fraction}|{label}".encode())
    return Holdout(n=n, fraction=fraction, ledger_path=Path(ledger_path),
                   fingerprint=digest.hexdigest(), label=label)


# ======================================================================================
# RUNNING A MODEL OVER THE FOLDS
# ======================================================================================

@dataclass
class CVResult:
    """Per-fold scores plus the honest caveats that belong beside them."""

    scores: list[float]
    splits: list[Split]
    coverage: dict[str, float] = field(default_factory=dict)
    horizon: int = 0
    embargo: int = 0
    #: Whether the PIPELINE was checked, as opposed to the index geometry. False means no
    #: `probe` was supplied and nothing established that the transform inside `fit_score` was
    #: fitted on training rows only. That is the default, and it is reported rather than
    #: assumed away: a scaler fitted on the full sample produces a `CVResult` numerically
    #: indistinguishable from a clean one, and every field above it is silent about that.
    transform_verified: bool = False

    @property
    def mean(self) -> float:
        return float(np.mean(self.scores)) if self.scores else float("nan")

    @property
    def std(self) -> float:
        return float(np.std(self.scores, ddof=1)) if len(self.scores) > 1 else float("nan")

    def summary(self) -> str:
        cov = self.coverage
        return (f"{self.mean:+.4f} +/- {self.std:.4f} over {len(self.scores)} folds "
                f"(h={self.horizon}, embargo={self.embargo}; "
                f"train {cov.get('train', 0):.0%} of sample, "
                f"purged {cov.get('purged', 0):.1%}, "
                f"embargoed {cov.get('embargoed', 0):.1%}; "
                f"transform {'probed' if self.transform_verified else 'UNVERIFIED'})")


def cross_validate(fit_score, n: int, *, horizon: int, folds: int = 5,
                   embargo: int | float = 0.0, expanding: bool = True,
                   check: bool = True, probe=None) -> CVResult:
    """Run `fit_score(train_idx, test_idx) -> float` over purged, embargoed folds.

    `check` verifies every split against `assert_no_leakage` before it is used. It defaults
    on because the cost is a boolean mask and the failure it catches is one that produces a
    plausible, publishable, wrong number.

    WHAT `check` CANNOT SEE, AND WHAT `probe` IS FOR
    ------------------------------------------------
    `assert_no_leakage` inspects index GEOMETRY: which rows are in the training fold, which
    are purged, which are embargoed. It says nothing about what the code inside `fit_score`
    actually read, and a standardiser fitted on the whole sample before the split is invisible
    to it. Measured on a 900-row fixture whose volatility regime changes at row 600, folds
    1..5 out-of-sample accuracy:

        train-only   0.9867 0.9667 0.9733 0.7333 0.8133
        full-sample  0.8600 0.8533 0.8400 0.8867 0.8800

    On the two folds that straddle and follow the regime change the contaminated pipeline is
    materially BETTER out of sample, which is the signature. Its lower mean is not a defence.
    `cross_validate` reported the two runs identically, down to the coverage line.

    `probe(rows)` closes that. The caller owns the data, so only the caller can perturb it;
    `probe` takes a boolean mask of the rows OUTSIDE a fold and returns a `fit_score`
    equivalent in every way except that those rows have been changed. If the score moves, the
    pipeline read rows it does not own, and this raises `LeakageError`. If it does not move,
    the transform is train-only and `CVResult.transform_verified` says so.

    Only the LAST fold is probed. It has the largest training set and, on an expanding
    walk-forward, the smallest out-of-fold remainder, so it is the hardest fold to detect
    contamination on: a probe that fires there would fire on any earlier one. Probing one
    fold costs one extra `fit_score` call rather than `folds` of them.

    `probe` is optional because it cannot be synthesised - without it there is no data to
    perturb. It is NOT defaulted to a no-op that quietly passes: when it is absent
    `transform_verified` is False and `summary()` prints UNVERIFIED, because "we did not
    check" and "we checked and it was clean" must not read the same.
    """
    splits = purged_walk_forward(n, horizon=horizon, folds=folds, embargo=embargo,
                                 expanding=expanding)
    emb = int(round(embargo * n)) if 0 < embargo < 1 else int(embargo)
    scores: list[float] = []
    for s in splits:
        if check:
            assert_no_leakage(s, horizon=horizon, embargo=emb)
        scores.append(float(fit_score(s.train, s.test)))

    verified = False
    if probe is not None and splits:
        verified = _probe_transform(fit_score, probe, splits[-1], n)

    return CVResult(scores=scores, splits=splits, coverage=coverage(splits, n),
                    horizon=horizon, embargo=emb, transform_verified=verified)


def _probe_transform(fit_score, probe, split: Split, n: int) -> bool:
    """Perturb every row outside `split` and require the fold's score not to move.

    Raises `LeakageError` when it moves. Returns True when the probe genuinely ran, and False
    when this fold leaves no row outside it to perturb - on an expanding walk-forward the last
    fold can cover the whole sample, and a probe with nothing to move proves nothing. Saying
    False there is the honest answer; claiming a clean bill from a probe that could not fire
    is the failure mode this whole function exists to prevent.
    """
    outside = np.ones(n, dtype=bool)
    outside[np.asarray(split.train, dtype=int)] = False
    outside[np.asarray(split.test, dtype=int)] = False
    if not outside.any():
        return False

    base = float(fit_score(split.train, split.test))
    moved = float(probe(outside)(split.train, split.test))
    if base != moved:
        raise LeakageError(
            f"the pipeline's score on the last fold moved from {base!r} to {moved!r} when "
            f"{int(outside.sum())} rows OUTSIDE that fold were perturbed. Something inside "
            f"fit_score read rows it does not own - most often a scaler, imputer or encoder "
            f"fitted before the split rather than inside it. Index geometry is not the "
            f"problem here; assert_no_leakage passed."
        )
    return True


def iter_splits(n: int, *, horizon: int, **kw) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """sklearn-style `(train, test)` pairs, for code that expects a splitter."""
    for s in purged_walk_forward(n, horizon=horizon, **kw):
        yield s.train, s.test
