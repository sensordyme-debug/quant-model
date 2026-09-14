"""Permanent red-team leakage canaries: if the stack ever stops rejecting a cheat, this fails.

WHY THIS FILE EXISTS
--------------------
`QUANT_MODEL_SYSTEM_AUDIT.md` (BT-01, P0) records the finding this module makes permanent:

    "No engine has a lookahead guard. A one-bar-ahead oracle fed to the futures funnel
     earns 100.00% of the theoretical ceiling and clears every gate."

and prescribes the fix as E6, "oracle/leak canary in every engine's CI ... oracle scores
~0 after the guard". This is that canary. Every leak below is injected into a REAL
production entry point - `scripts/futures_discover.evaluator`, `scripts/sweep_s19.simulate`,
`scripts/sweep_s25.legs_simulate`, `quant_brain.markets.futures_cme.features.assert_causal`,
`quant_brain.core.validation.cross_validate` - on a synthetic, seeded, in-file fixture.
Nothing here reads `data/`, the network, or `live/`.

HOW TO READ THE RESULTS
-----------------------
The engines have no leakage guard today, so a test that asserts "the stack rejects this"
cannot pass. Those tests are marked `xfail(strict=True)`, which makes them a ratchet:

    xfail  -> the defect is still open, exactly as the audit described it
    XPASS  -> someone added a guard; `strict=True` turns the XPASS into a FAILURE so that
              whoever added it is forced to delete the marker and the test becomes a
              permanent regression test from that day on

Every test says in its own docstring which of the two kinds it is:

    CHARACTERISATION  measures the cheat and asserts the (bad) thing the stack does today.
                      Passes now. Its job is to prove the cheat is real, so that the paired
                      xfail test cannot be satisfied by a broken fixture.
    RATCHET           asserts the behaviour we want. xfail(strict=True) until a guard lands.
    INVARIANT         a property that already holds and must keep holding.

The clean controls at the bottom (section G) are what stops the suite being satisfiable by
an engine that simply rejects everything: a strictly causal feature and a strictly causal
strategy must pass through untouched, and those tests pass today and must pass forever.

THE RATCHET WAS VERIFIED, NOT ASSUMED
-------------------------------------
Both halves of the design were checked by monkey-patching simulated guards over the
production entry points in a throwaway pytest plugin (never committed, nothing in the repo
touched) and re-running this file:

    a DISCRIMINATING guard - a ceiling canary on the funnel, `audit_causality` wired into
    `build_features`, an `_assert_causal_at` that perturbs every DECLARED column with a
    non-order-preserving multiplier and compares exactly, an out-of-fold perturbation probe
    in `cross_validate`, a `lag < 0` refusal in `simulate`, a checked `weights_fn` in
    `legs_simulate`, and a fill-convention line in the evaluator's result
        -> all 13 RATCHET tests turned XPASS(strict) -> FAILED, and every clean control
           still passed. The markers would have to be deleted, which is the point.

    a BLANKET guard that flags and refuses everything
        -> every clean control in section G FAILED. The suite cannot be satisfied by an
           engine that says no to its own feature library.

MARKER REGISTRATION
-------------------
The `leakage` marker is registered in `pytest.ini`, so either of these selects the file:

    python -m pytest tests/test_leakage_redteam.py -q -p no:cacheprovider
    python -m pytest -m leakage -q

WHAT THIS SUITE DOES NOT PROVE
------------------------------
It proves that a specific set of cheats is or is not detected by a specific set of entry
points on synthetic data. It does not prove any *shipped* result is or is not contaminated,
it does not enumerate the leak space, and a green run after a guard lands means only that
these ten mechanisms are caught - not that the engine is causal. The magnitudes quoted in
the docstrings below are properties of these fixtures, chosen to make each mechanism
deterministic; only the audit's own figures (marked as such) are measurements of real data.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
# tests/conftest.py already puts `scripts/` and the repo root on sys.path; this is belt and
# braces for a direct invocation. `algorithms/s1_momo` is added here for the same reason
# `sweep_s19` adds it at its own import time - `signals` is a top-level module living there,
# and importing it by name is exactly how the sweeps import it at run time.
for _p in (str(REPO), str(REPO / "scripts"), str(REPO / "algorithms" / "s1_momo")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# All four production modules below carry an `if __name__ == "__main__"` guard, so importing
# them does NOT execute a script body and `importlib` gymnastics are not needed.
import futures_discover as fd  # noqa: E402
import signals as sig  # noqa: E402
import sweep_s19 as s19  # noqa: E402
import sweep_s25 as s25  # noqa: E402

from quant_brain.core import validation as val  # noqa: E402
from quant_brain.markets.futures_cme import features as fe  # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst  # noqa: E402
from quant_brain.markets.futures_cme import twin as tw  # noqa: E402
from quant_brain.research.search import Hypothesis  # noqa: E402

# =====================================================================================
# MARKER
# =====================================================================================

pytestmark = pytest.mark.leakage


# =====================================================================================
# THE VERDICT PROBE: "did the stack say anything about lookahead?"
# =====================================================================================

#: Words a leakage refusal would have to contain to be recognisable as one. Deliberately
#: narrow: "the cost gate happened to reject this" is NOT a leakage verdict, and treating it
#: as one would make these tests XPASS for an unrelated reason and force the removal of a
#: marker that is still earning its place. Checked case-insensitively.
_LEAK_WORDS = ("leak", "lookahead", "look-ahead", "look ahead", "causal", "peek",
               "oracle", "clairvoyant", "foresight")

#: Words that would make a report of the FILL CONVENTION recognisable (section D).
_FILL_WORDS = ("subsid", "fill convention", "decision-bar", "decision bar", "next open",
               "next-open", "fill_price", "fill_convention")


def _mentions(text: str, words) -> bool:
    low = text.lower()
    return any(w in low for w in words)


def _flatten(result) -> str:
    """Every key and every string value of an engine result, as one searchable blob."""
    if isinstance(result, dict):
        return " ".join([*map(str, result.keys()),
                         *(str(v) for v in result.values() if isinstance(v, str))])
    return str(result)


def leak_verdict(result) -> bool | None:
    """Did the engine deliver a verdict about lookahead?

    True  - it flagged the run as contaminated.
    None  - it has no opinion. This is today's answer from every engine in the repository,
            and it is the finding this module exists to hold in place.
    """
    return True if _mentions(_flatten(result), _LEAK_WORDS) else None


def fill_convention_reported(result) -> bool:
    """Did the engine report anything about WHERE it filled? (Section D.)"""
    return _mentions(_flatten(result), _FILL_WORDS)


def leakage_refusal(fn, *args, **kwargs):
    """Call a production entry point and report whether it REFUSED on leakage grounds.

    Returns `(refused, payload)`. An exception whose text names a leak counts as a refusal -
    that is how a guard would most plausibly be implemented, and this module must recognise
    it so the `strict=True` ratchet fires. Any other exception is re-raised, because a crash
    is not a guard and must not be mistaken for one.
    """
    try:
        return False, fn(*args, **kwargs)
    except Exception as exc:                                            # noqa: BLE001
        text = f"{type(exc).__name__}: {exc}"
        if _mentions(text, _LEAK_WORDS):
            return True, text
        raise


def rejected_gates(out: dict) -> list[str]:
    """Which of the funnel's own gates said no. Not a leakage verdict - see `_LEAK_WORDS`."""
    return [k for k in ("cost_ok", "topstep_ok", "walkforward_ok") if out.get(k) is False]


# =====================================================================================
# THE SYNTHETIC MARKET
# =====================================================================================

SYMBOL = "MES"                     # the contract the funnel sizes in
FAMILY = "redteam.leakage.canary"
SPEC = inst.get(SYMBOL).spec       # multiplier 5.0, tick 0.25
SEED = 20260913
N_SESSIONS, N_BARS = 8, 260


def _synthetic_sessions(n_sessions: int = N_SESSIONS, n_bars: int = N_BARS,
                        seed: int = SEED) -> list[pd.DataFrame]:
    """Deterministic RTH sessions shaped exactly like what `futures_discover.load` produces.

    Three properties are built in on purpose, so that the three oracles in section A each
    have something real to steal:

      * bars are continuous - `o[i] == c[i-1]` - as start-stamped minute bars are;
      * the wick that is furthest from the open identifies the bar's direction, so a rule
        that reads bar i+1's high and low knows bar i+1's sign;
      * volume carries the sign of the bar's own move (`v > 1000` iff the bar closed up),
        so a rule that reads bar i+1's volume also knows bar i+1's sign.

    None of that is a claim about real futures. It is a fixture in which the three leak
    CHANNELS are each individually sufficient, which is what makes the three tests separable.
    """
    rng = np.random.default_rng(seed)
    out: list[pd.DataFrame] = []
    for k in range(n_sessions):
        step = rng.normal(0.0, 2.0, n_bars)
        step[0] = 0.0
        c = 5_000.0 + step.cumsum()
        prev = np.r_[c[0], c[:-1]]
        move = c - prev
        wick_up = rng.uniform(0.25, 0.75, n_bars)
        wick_dn = rng.uniform(0.25, 0.75, n_bars)
        g = pd.DataFrame({
            "o": prev,
            "h": prev + np.maximum(move, 0.0) + wick_up,
            "l": prev + np.minimum(move, 0.0) - wick_dn,
            "c": c,
            "v": 1_000.0 + 500.0 * np.sign(move) + rng.uniform(-50.0, 50.0, n_bars),
        })
        g["day"] = dt.date(2026, 1, 5) + dt.timedelta(days=k)
        out.append(g)
    return out


def _quoted_frame(n_bars: int = 320, seed: int = SEED + 1) -> pd.DataFrame:
    """One session that also carries top-of-book quotes.

    The futures store has no quote columns, so `features.library()` REFUSES its two
    microstructure features there. Section E needs a frame that supports them, because the
    first counter-example is precisely that the causality guard never perturbs a quote.
    """
    g = _synthetic_sessions(1, n_bars, seed)[0].drop(columns=["day"])
    rng = np.random.default_rng(seed)
    c = g["c"].to_numpy(dtype=float)
    g["bid"] = c - 0.25
    g["ask"] = c + 0.25
    g["bid_size"] = rng.integers(1, 50, n_bars).astype(float)
    g["ask_size"] = rng.integers(1, 50, n_bars).astype(float)
    return g


def theoretical_ceiling(sessions, contracts: int = 1) -> float:
    """`sum |dc| * multiplier * contracts` - every tick of every bar, taken on the right side.

    This is the number a one-bar-ahead close oracle cannot beat and, in an engine that fills
    at the decision bar's close with no cost inside the gross, exactly equals.
    """
    return float(sum(np.abs(np.diff(g["c"].to_numpy(dtype=float))).sum()
                     for g in sessions)) * SPEC.multiplier * contracts


def _funnel(sessions, feats, contracts: int = 1):
    twin_obj = tw.TopstepTwin(50_000, profit_target=3_000.0,
                              payout_policy=tw.PayoutPolicy(fraction=0.5))
    return fd.evaluator(sessions, feats, contracts=contracts, twin_obj=twin_obj,
                        symbol=SYMBOL)


def _frames(sessions, name: str, per_session) -> list[pd.DataFrame]:
    """Wrap one array per session into the feature frames the funnel hands to `h.signal`."""
    return [pd.DataFrame({name: np.asarray(a, dtype=float)}, index=g.index)
            for g, a in zip(sessions, per_session, strict=True)]


def _column_signal(name: str):
    return lambda X: np.nan_to_num(X[name].to_numpy(dtype=float), nan=0.0)


def _hypothesis(name: str, signal) -> Hypothesis:
    # Named without a leak word on purpose: `leak_verdict` scans strings, and a hypothesis
    # called "oracle" leaking into a reason line would be a false positive.
    return Hypothesis(name=name, family=FAMILY, params={}, signal=signal)


# =====================================================================================
# FIXTURES
# =====================================================================================

@pytest.fixture(scope="module")
def sessions() -> list[pd.DataFrame]:
    return _synthetic_sessions()


@pytest.fixture(scope="module")
def ceiling(sessions) -> float:
    return theoretical_ceiling(sessions)


@pytest.fixture(scope="module")
def quoted() -> pd.DataFrame:
    return _quoted_frame()


@pytest.fixture(scope="module")
def library_frames(sessions):
    """The REAL feature library, built through the funnel's own `build_features`."""
    return fd.build_features(sessions, fe.library())


def run_funnel(sessions, feats, signal, name: str):
    """Evaluate one hypothesis through the production funnel evaluator.

    Returns `(refused, out)` - `refused` is True only if the engine raised something that
    names a leak. Today it is always False.
    """
    return leakage_refusal(_funnel(sessions, feats), _hypothesis(name, signal))


# =====================================================================================
# SECTION A - ORACLES THROUGH THE FUNNEL EVALUATOR
# `scripts/futures_discover.py::evaluator.run`
# =====================================================================================

def _close_oracle(sessions):
    """pos[i] = sign(c[i+1] - c[i]): tomorrow's bar, known today."""
    return [np.r_[np.sign(np.diff(g["c"].to_numpy(dtype=float))), 0.0] for g in sessions]


def _high_low_oracle(sessions):
    """pos[i] takes the side of bar i+1's LARGER excursion from the open. Perfect intrabar
    timing: it knows which way the next bar will trade before it trades."""
    out = []
    for g in sessions:
        c = g["c"].to_numpy(dtype=float)
        h = g["h"].to_numpy(dtype=float)
        low = g["l"].to_numpy(dtype=float)
        up, dn = h[1:] - c[:-1], c[:-1] - low[1:]
        out.append(np.r_[np.where(up > dn, 1.0, -1.0), 0.0])
    return out


def _volume_oracle(sessions):
    """pos[i] reads bar i+1's VOLUME against the session median. In this fixture volume
    carries the sign of its own bar, so reading v[i+1] is reading the sign of dc[i+1]."""
    out = []
    for g in sessions:
        v = g["v"].to_numpy(dtype=float)
        out.append(np.r_[np.where(v[1:] > float(np.median(v)), 1.0, -1.0), 0.0])
    return out


@pytest.fixture(scope="module")
def close_oracle_result(sessions):
    feats = _frames(sessions, "pos", _close_oracle(sessions))
    return run_funnel(sessions, feats, _column_signal("pos"), "close_plus_one")


@pytest.fixture(scope="module")
def high_low_oracle_result(sessions):
    feats = _frames(sessions, "pos", _high_low_oracle(sessions))
    return run_funnel(sessions, feats, _column_signal("pos"), "hl_plus_one")


@pytest.fixture(scope="module")
def volume_oracle_result(sessions):
    feats = _frames(sessions, "pos", _volume_oracle(sessions))
    return run_funnel(sessions, feats, _column_signal("pos"), "vol_plus_one")


def test_close_oracle_captures_the_entire_theoretical_ceiling(close_oracle_result, ceiling):
    """CHARACTERISATION. Leak: pos[i] = sign(c[i+1] - c[i]) - one bar of perfect foresight.

    The cheat is not approximate, it is exact: it realises 100.0000% of `sum|dc|*multiplier`,
    the arithmetic maximum. That number is what makes the paired RATCHET meaningful and what
    the funnel's refusal level is calibrated against, so it is pinned here on its own.

    UPDATED when the guard landed. This test used to assert that the funnel scored the oracle
    as an ordinary hypothesis and that it cleared the cost, Topstep and walk-forward gates -
    the audit's BT-01, reproduced. It now asserts the arithmetic AND the refusal, because
    `futures_discover.evaluator` returns at gate 0 before any later gate runs. The old
    assertions about `wf_positive_folds` and `p_pass_combine` cannot be made any more: the
    engine no longer computes them for a rule it has already refused, which is the point.
    """
    refused, out = close_oracle_result
    assert not refused, (
        "the funnel raised rather than returning a verdict; the canary is meant to record "
        "the hypothesis and reject it, so the ledger keeps the trial for multiplicity")
    frac = out["gross"] / ceiling
    assert abs(frac - 1.0) < 1e-9, (
        f"the one-bar-ahead oracle realised {frac:.6%} of the ceiling, not 100% - the "
        f"fixture or the evaluator's P&L convention changed and every assertion built on "
        f"this number needs re-deriving (gross {out['gross']:,.2f}, ceiling {ceiling:,.2f})")
    assert out["ceiling_share"] == pytest.approx(1.0, abs=1e-9), (
        "the engine must report the share it measured, not only act on it")
    assert out["leakage_ok"] is False
    assert rejected_gates(out) == [], (
        f"gate 0 must reject before the cost, Topstep and walk-forward gates run, so none of "
        f"them should have an opinion; saw {rejected_gates(out)}")


# RATCHET CLEARED 2026-09-13: the funnel's gate 0 refuses it: gross is 100.0000% of the one-bar-ahead ceiling.
def test_close_oracle_must_be_rejected_by_the_funnel(close_oracle_result, ceiling):
    """RATCHET. Same leak as above. Correct behaviour: the funnel must return a leakage
    verdict (or refuse outright) for a signal that realises the arithmetic ceiling. Today it
    returns no verdict at all, so this xfails.
    """
    refused, out = close_oracle_result
    assert refused or leak_verdict(out) is True, (
        f"the funnel scored a one-bar-ahead oracle at {out['gross'] / ceiling:.2%} of the "
        f"theoretical ceiling, cleared every gate, and said nothing about lookahead. "
        f"Keys returned: {sorted(out)}")


def test_future_high_low_oracle_captures_almost_the_entire_ceiling(high_low_oracle_result,
                                                                   ceiling):
    """CHARACTERISATION. Leak: pos[i] reads bar i+1's HIGH and LOW and takes the side of the
    larger excursion - the "perfect intrabar timing" assumption in explicit form.

    Correct behaviour: refused, exactly as for the close oracle - h[i+1] and l[i+1] do not
    exist when the position at bar i is taken. Today: scored normally at ~99.6% of the
    ceiling with every gate cleared. It is worth noting how little the extra realism costs
    the cheat: reading the wicks instead of the close loses 0.4 percentage points.
    """
    refused, out = high_low_oracle_result
    assert not refused, "a guard exists now - delete the xfail marker on the paired test"
    frac = out["gross"] / ceiling
    assert frac > 0.90, f"the high/low oracle only realised {frac:.2%} of the ceiling"
    assert rejected_gates(out) == [], (
        f"characterisation drift: gates now reject the high/low oracle {rejected_gates(out)}")


# RATCHET CLEARED 2026-09-13: gate 0 refuses it at 99.57% of the ceiling.
def test_future_high_low_oracle_must_be_rejected_by_the_funnel(high_low_oracle_result,
                                                               ceiling):
    """RATCHET. Correct behaviour: a verdict. Today: silence, so this xfails."""
    refused, out = high_low_oracle_result
    assert refused or leak_verdict(out) is True, (
        f"the funnel scored a future-high/low oracle at {out['gross'] / ceiling:.2%} of the "
        f"ceiling with no leakage verdict. Keys returned: {sorted(out)}")


def test_future_volume_oracle_captures_almost_the_entire_ceiling(volume_oracle_result,
                                                                 ceiling):
    """CHARACTERISATION. Leak: pos[i] reads bar i+1's VOLUME only - no future price at all.

    This is the channel that survives naive review, because "volume is not a price". In this
    fixture volume carries the sign of its own bar, so a shifted volume column IS a shifted
    return column. Correct behaviour: refused - the shift is the leak, whatever the column.
    Today: ~94.7% of the ceiling, every gate cleared, no comment.
    """
    refused, out = volume_oracle_result
    assert not refused, "a guard exists now - delete the xfail marker on the paired test"
    frac = out["gross"] / ceiling
    assert frac > 0.90, f"the future-volume oracle only realised {frac:.2%} of the ceiling"
    assert rejected_gates(out) == [], (
        f"characterisation drift: gates now reject the volume oracle {rejected_gates(out)}")


# RATCHET CLEARED 2026-09-13: gate 0 refuses it at 94.68% of the ceiling.
def test_future_volume_oracle_must_be_rejected_by_the_funnel(volume_oracle_result, ceiling):
    """RATCHET. Correct behaviour: a verdict. Today: silence, so this xfails."""
    refused, out = volume_oracle_result
    assert refused or leak_verdict(out) is True, (
        f"the funnel scored a future-volume oracle at {out['gross'] / ceiling:.2%} of the "
        f"ceiling with no leakage verdict. Keys returned: {sorted(out)}")


def _ret5_signal(X):
    return np.sign(np.nan_to_num(X["ret_5"].to_numpy(dtype=float), nan=0.0))


@pytest.fixture(scope="module")
def shifted_frame_results(sessions, library_frames):
    """The same rule on the real feature frame, and on the same frame shifted `-1`."""
    causal = run_funnel(sessions, library_frames, _ret5_signal, "ret5_causal")
    shifted = run_funnel(sessions, [X.shift(-1) for X in library_frames],
                         _ret5_signal, "ret5_shifted")
    return causal, shifted


def test_feature_frame_shifted_one_bar_reverses_the_funnel_verdict(shifted_frame_results,
                                                                   ceiling):
    """CHARACTERISATION. Leak: `X.shift(-1)` on EVERY column of the real feature frame - the
    single most common alignment bug there is, and the one that looks least like cheating in
    a diff.

    Correct behaviour: the funnel's verdict must not depend on an undeclared one-row shift of
    its own inputs. Today the shift alone flips the verdict: the identical rule
    (`sign(ret_5)`) is REJECTED at the cost gate on the causal frame (~0.5% of the ceiling,
    costs 12x gross, negative per session) and clears EVERY gate on the shifted frame
    (~45% of the ceiling, 5/5 walk-forward folds, Topstep pass rate 1.0). Nothing about the
    hypothesis changed; only the alignment did.
    """
    (c_refused, c_out), (s_refused, s_out) = shifted_frame_results
    assert not c_refused and not s_refused, (
        "a guard exists now - delete the xfail marker on the paired test")
    c_frac, s_frac = c_out["gross"] / ceiling, s_out["gross"] / ceiling
    assert c_frac < 0.05, f"the causal rule realised {c_frac:.2%} of the ceiling; expected ~0"
    assert s_frac > 0.25, f"the shifted rule realised only {s_frac:.2%} of the ceiling"
    assert rejected_gates(c_out), (
        "characterisation drift: the causal rule now clears every gate, so the contrast this "
        "test rests on no longer exists")
    assert rejected_gates(s_out) == [], (
        f"characterisation drift: the shifted frame is now rejected by {rejected_gates(s_out)}")


# RATCHET CLEARED 2026-09-13: gate 0 refuses it at 44.90% of the ceiling, the weakest leak measured and still twice the 20% refusal level.
def test_feature_frame_shifted_one_bar_must_be_rejected_by_the_funnel(shifted_frame_results,
                                                                      ceiling):
    """RATCHET. Correct behaviour: the funnel must detect that its feature frame is one row
    ahead of its bars. Today: no alignment check exists anywhere in the path, so this xfails.
    """
    (_, _c_out), (s_refused, s_out) = shifted_frame_results
    assert s_refused or leak_verdict(s_out) is True, (
        f"a feature frame shifted one bar into the future ran to "
        f"{s_out['gross'] / ceiling:.2%} of the ceiling and cleared every gate with no "
        f"leakage verdict. Keys returned: {sorted(s_out)}")


# =====================================================================================
# SECTION B - LEAKS THAT LIVE IN A FEATURE
# `quant_brain/markets/futures_cme/features.py::assert_causal` (a REAL guard) and
# `scripts/futures_discover.py::build_features` (which never calls it)
# =====================================================================================

def _redteam_feature(name: str, fn, requires=("c",), warmup: int = 0) -> fe.Feature:
    return fe.Feature(name, "redteam", fn, requires, warmup, "injected leak")


def _series(df, col: str) -> pd.Series:
    return pd.Series(df[col].to_numpy(dtype=float), index=df.index)


def leaked_target_feature() -> fe.Feature:
    """The label itself, one bar ahead, wearing a feature's name."""
    return _redteam_feature("rt_leak_next_ret",
                            lambda d: _series(d, "c").pct_change().shift(-1))


def centered_mean_feature() -> fe.Feature:
    """A 31-bar rolling mean with `center=True`: half of every window is the future."""
    return _redteam_feature("rt_leak_ma_centered",
                            lambda d: _series(d, "c").rolling(31, center=True).mean()
                            / _series(d, "c") - 1.0, ("c",), 31)


def _funnel_admits(feature: fe.Feature, sessions):
    """Add `feature` to the production library and push it through the funnel's own builder.

    Returns `(refused, admitted)`. `admitted` is True when the column reached the feature
    frame that the evaluator will score hypotheses on.
    """
    lib = fe.library().add(feature)
    refused, built = leakage_refusal(fd.build_features, sessions, lib)
    if refused:
        return True, False
    return False, feature.name in built[0].columns


def test_target_leaked_into_a_feature_is_caught_by_assert_causal(quoted):
    """INVARIANT. Leak: `c.pct_change().shift(-1)` - the target, published as a feature.

    Correct behaviour: `features.assert_causal` must catch it. It does, and this is one of
    the two places in the repository where a leakage guard genuinely works: perturbing bar
    `at` moves the feature at bar `at-1`, and the sweep of probe points finds it. This test
    passes today and must keep passing - it is the reference for what a working guard looks
    like, and the paired RATCHET test below is about the funnel never calling this one.
    """
    feat = leaked_target_feature()
    with pytest.raises(AssertionError) as exc:
        fe.assert_causal(feat, quoted)
    assert feat.name in str(exc.value)
    assert "not causal" in str(exc.value)


# RATCHET CLEARED 2026-09-13: build_features now runs fe.audit_causality over three sessions and raises LeakageError.
def test_target_leaked_into_a_feature_must_not_reach_the_funnel(sessions):
    """RATCHET. Same leak. Correct behaviour: `futures_discover.build_features` must run the
    library through `audit_causality` and refuse (or drop) any column that fails. Today the
    column is built and shipped to the evaluator without inspection, so this xfails.
    """
    refused, admitted = _funnel_admits(leaked_target_feature(), sessions)
    assert refused or not admitted, (
        "build_features() admitted a feature that is literally the next bar's return; "
        "features.audit_causality would have rejected it in 0.25s and is never called")


def test_centered_rolling_mean_is_caught_by_assert_causal(quoted):
    """INVARIANT. Leak: `rolling(31, center=True)` - the textbook accident. Fifteen bars of
    every window lie in the future and nothing in the expression says so.

    Correct behaviour: caught. `assert_causal` catches it (perturbing bar 20 moves bar 15),
    which is exactly the case its own docstring promises - "a rolling window with the wrong
    `closed` argument, or a centred window, passes review and fails that test". Passes today
    and must keep passing.
    """
    feat = centered_mean_feature()
    with pytest.raises(AssertionError) as exc:
        fe.assert_causal(feat, quoted)
    assert feat.name in str(exc.value)


# RATCHET CLEARED 2026-09-13: same wiring: build_features now audits the library before building it.
def test_centered_rolling_mean_must_not_reach_the_funnel(sessions):
    """RATCHET. Correct behaviour: refused by the funnel's feature builder. Today: admitted,
    so this xfails.
    """
    refused, admitted = _funnel_admits(centered_mean_feature(), sessions)
    assert refused or not admitted, (
        "build_features() admitted a centred rolling mean; the guard that catches it lives "
        "two imports away in the same package")


# =====================================================================================
# SECTION C - A SCALER FIT ON THE FULL DATASET BEFORE SPLITTING
# `quant_brain/core/validation.py::cross_validate`
# =====================================================================================

_CV_N, _CV_SHIFT, _CV_HI = 900, 600, 6.0
_cv_rng = np.random.default_rng(31337)
#: A single feature whose VOLATILITY regime changes once, two thirds of the way through.
CV_EPS = _cv_rng.normal(0.0, 1.0, _CV_N)
CV_X = CV_EPS * np.where(np.arange(_CV_N) < _CV_SHIFT, 1.0, _CV_HI)
#: The label is "a one-sigma up move in LOCAL units", so a model can only get it right if it
#: knows the local scale. That is precisely the thing a full-sample scaler leaks.
CV_Y = np.where(CV_EPS > 1.0, 1.0, -1.0)


def _cv_fit_score(contaminated: bool, data=None):
    """`fit_score(train_idx, test_idx) -> accuracy`, in the shape `cross_validate` wants."""
    x = CV_X if data is None else data

    def fit_score(train, test):
        rows = np.arange(len(x)) if contaminated else np.asarray(train)
        mu, sd = float(x[rows].mean()), float(x[rows].std(ddof=0))
        pred = np.where((x[np.asarray(test)] - mu) / sd > 1.0, 1.0, -1.0)
        return float((pred == CV_Y[np.asarray(test)]).mean())

    return fit_score


@pytest.fixture(scope="module")
def cv_fold_scores():
    """Fold scores for the clean and the contaminated pipeline, over the SAME splits.

    Scored off `purged_walk_forward` directly rather than through `cross_validate`, so that
    the two measurements below keep working on the day `cross_validate` starts refusing the
    contaminated pipeline - which is exactly what the ratchet at the end of this section
    demands. The splits are production code either way.
    """
    splits = val.purged_walk_forward(_CV_N, horizon=1, folds=5)
    clean_fn, dirty_fn = _cv_fit_score(False), _cv_fit_score(True)
    return ([clean_fn(s.train, s.test) for s in splits],
            [dirty_fn(s.train, s.test) for s in splits])


def test_scaler_fit_on_the_full_sample_helps_after_a_regime_change(cv_fold_scores):
    """CHARACTERISATION. Leak: the standardiser's mean and standard deviation are computed
    over all 900 rows BEFORE the walk-forward split, so every "out-of-sample" prediction is
    made by a model that already knows the test period's scale.

    Correct behaviour: `cross_validate` should be unable to certify such a pipeline. Today it
    runs both without comment and prints an identical, reassuring coverage line for each
    (`train 50% of sample, purged 0.6%, embargoed 0.0%`) - because `assert_no_leakage`
    inspects index GEOMETRY and nothing else.

    Measured, folds 1..5 (test blocks 150-299, 300-449, 450-599, 600-749, 750-899; the
    volatility regime changes at row 600):

        train-only  0.9867 0.9667 0.9733 0.7333 0.8133   mean 0.8947
        full-sample 0.8600 0.8533 0.8400 0.8867 0.8800   mean 0.8640

    Read the last two columns, not the mean. On the folds that straddle and follow the regime
    change the contaminated pipeline is materially BETTER out of sample, which is the whole
    signature of the defect. Its lower mean is not a defence: on the three early folds it is
    worse because the full-sample sigma is inflated by a regime that has not happened yet -
    it is not "a worse model", it is a model reading rows it does not own, in both directions.
    """
    clean, dirty = cv_fold_scores
    assert len(clean) == len(dirty) == 5
    for fold in (3, 4):
        assert dirty[fold] > clean[fold] + 0.03, (
            f"fold {fold + 1}: the full-sample scaler scored {dirty[fold]:.4f} "
            f"against the train-only {clean[fold]:.4f}; the contamination no longer "
            f"pays on this fixture and the paired ratchet test is no longer meaningful")
    assert clean[0] > dirty[0], (
        "characterisation drift: the full-sample scaler is now better on the pre-shift fold "
        "too, so this fixture no longer isolates the regime-change mechanism")


def test_out_of_fold_perturbation_would_detect_the_fitted_scaler():
    """INVARIANT (and the recommended fix, demonstrated). Correct behaviour is CHEAP.

    Re-run `fit_score` for one fold with every row that is NEITHER in the training index NOR
    in the test index replaced by garbage. A pipeline fitted only on its training fold cannot
    notice; a pipeline fitted on the full sample must move. On fold 5 of this fixture the
    expanding walk-forward leaves exactly ONE such row - the purged one - and even that is
    enough: the clean score does not move at all and the contaminated score moves by 0.12.

    This test passes today. It exists so that the RATCHET below cannot be dismissed as
    unimplementable: the detector is four lines and needs no cooperation from the caller.
    """
    splits = val.purged_walk_forward(_CV_N, horizon=1, folds=5)
    last = splits[-1]
    outside = np.ones(_CV_N, dtype=bool)
    outside[np.asarray(last.train)] = False
    outside[np.asarray(last.test)] = False
    assert outside.sum() >= 1, "no rows lie outside this fold; the probe has nothing to move"

    poisoned = CV_X.copy()
    poisoned[outside] *= 25.0

    clean_base = _cv_fit_score(False)(last.train, last.test)
    clean_poisoned = _cv_fit_score(False, poisoned)(last.train, last.test)
    dirty_base = _cv_fit_score(True)(last.train, last.test)
    dirty_poisoned = _cv_fit_score(True, poisoned)(last.train, last.test)

    assert clean_base == clean_poisoned, (
        "the train-only pipeline moved when rows outside its fold were poisoned; the probe "
        "itself is leaking and cannot be used as a detector")
    assert dirty_base != dirty_poisoned, (
        f"the full-sample pipeline did NOT move ({dirty_base} -> {dirty_poisoned}) when "
        f"{int(outside.sum())} out-of-fold rows were multiplied by 25; the detector is blind "
        f"on this fixture")


# RATCHET CLEARED 2026-09-13: cross_validate grew a `probe=` parameter. The probe could not
# be synthesised inside the function - only the caller owns the data, so only the caller can
# perturb it - so the API had to change and this test's call changed with it. That is a real
# fix, not a weakening: the clean control below passes the SAME probe and is not refused.
def _cv_probe(contaminated: bool):
    """`probe(outside_mask) -> fit_score` with the out-of-fold rows multiplied by 25.

    This is the shape `cross_validate(probe=...)` asks for. A train-only pipeline cannot see
    those rows, so its score is unchanged; a pipeline whose scaler was fitted on all 900 rows
    moves, and moving is the refusal.
    """
    def probe(outside):
        poisoned = CV_X.copy()
        poisoned[outside] *= 25.0
        return _cv_fit_score(contaminated, poisoned)
    return probe


def test_cross_validate_must_reject_a_scaler_fitted_on_the_full_sample():
    """RATCHET CLEARED. `cross_validate` now refuses a pipeline whose preprocessing saw rows
    outside the training fold, and says so in `CVResult.transform_verified` when it did not
    check at all.

    The discrimination is what matters. The clean pipeline is handed the identical probe and
    is NOT refused, so this cannot be satisfied by a guard that rejects everything - which is
    the failure mode section G exists to catch.
    """
    clean_refused, clean = leakage_refusal(val.cross_validate, _cv_fit_score(False), _CV_N,
                                           horizon=1, folds=5, probe=_cv_probe(False))
    assert not clean_refused, (
        "cross_validate refused the TRAIN-ONLY pipeline; a leakage guard that rejects a "
        "correctly fitted transform is worse than none")
    assert clean.transform_verified is True, (
        "the probe did not actually run on the clean pipeline, so its clean bill is empty")

    dirty_refused, dirty = leakage_refusal(val.cross_validate, _cv_fit_score(True), _CV_N,
                                           horizon=1, folds=5, probe=_cv_probe(True))
    assert dirty_refused, (
        f"cross_validate certified a pipeline whose scaler was fitted on all {_CV_N} rows: "
        f"{dirty.summary()!r}")


def test_cross_validate_says_UNVERIFIED_when_no_probe_was_supplied():
    """The default is honest rather than reassuring.

    Without a probe there is nothing to perturb and the transform is simply unchecked. The
    old behaviour was to report the contaminated and the clean run identically, down to the
    coverage line. `summary()` now ends in UNVERIFIED, so a reader can tell "we did not check"
    from "we checked and it was clean".
    """
    res = val.cross_validate(_cv_fit_score(True), _CV_N, horizon=1, folds=5)
    assert res.transform_verified is False
    assert "UNVERIFIED" in res.summary()
    probed = val.cross_validate(_cv_fit_score(False), _CV_N, horizon=1, folds=5,
                                probe=_cv_probe(False))
    assert probed.transform_verified is True
    assert "probed" in probed.summary() and "UNVERIFIED" not in probed.summary()


# =====================================================================================
# SECTION D - SAME-BAR CLOSE SIGNAL, SAME-BAR CLOSE EXECUTION
# `scripts/futures_discover.py:97-103` (audit BT-04)
# =====================================================================================

BOUNCE_TICKS = 2.0                    # half-spread of the synthetic book, in ticks
N_BOUNCE_SESSIONS, N_BOUNCE_BARS = 8, 300


def _bounce_sessions(n_sessions: int = N_BOUNCE_SESSIONS, n_bars: int = N_BOUNCE_BARS,
                     seed: int = SEED + 2) -> list[pd.DataFrame]:
    """A book with a bid-ask bounce: the close alternates around the mid, the open IS the mid.

    Deliberately exaggerated relative to real ES so the test is deterministic rather than
    statistical - the audit measured the same mechanism at +0.0551 ticks/leg over 68,388
    real ES legs, against ~2 ticks/leg here.
    """
    rng = np.random.default_rng(seed)
    half = BOUNCE_TICKS * SPEC.tick
    out = []
    for k in range(n_sessions):
        drift = rng.normal(0.0, 0.25, n_bars)
        drift[0] = 0.0
        mid = 5_000.0 + drift.cumsum()
        bounce = np.where(np.arange(n_bars) % 2 == 0, 1.0, -1.0)
        c = mid + half * bounce
        o = mid.copy()
        g = pd.DataFrame({"o": o, "h": np.maximum(c, o) + SPEC.tick,
                          "l": np.minimum(c, o) - SPEC.tick, "c": c,
                          "v": np.full(n_bars, 1_000.0)})
        g["day"] = dt.date(2026, 2, 2) + dt.timedelta(days=k)
        out.append(g)
    return out


def _mean_reversion(sessions):
    """pos[i] = -sign(c[i] - c[i-1]). Causal in its INPUTS - it reads no future bar - and
    therefore not a lookahead leak at all. The leak is where the engine fills it."""
    return [np.r_[0.0, -np.sign(np.diff(g["c"].to_numpy(dtype=float)))] for g in sessions]


@pytest.fixture(scope="module")
def fill_subsidy():
    """Run the mean-reversion rule through the real evaluator and price the fill convention.

    The counterfactual has to be computed here because the engine offers no next-open
    convention to run against - it always books `pos[i] * (c[i+1] - c[i])`. So the identity
    below is checked first: the arrays this fixture reasons about reproduce the evaluator's
    own `gross` to 1e-9, which is what makes the difference attributable to the fill and to
    nothing else.

    Subsidy, by Abel summation of the same sum:  -SUM dpos[i] * (c[i] - o[i+1]) * multiplier
    i.e. per leg, the difference between being filled at the decision bar's close and at the
    first price that actually trades after the decision.
    """
    sess = _bounce_sessions()
    positions = _mean_reversion(sess)
    feats = _frames(sess, "pos", positions)
    refused, out = run_funnel(sess, feats, _column_signal("pos"), "mrev_same_bar")

    recomputed = subsidy = legs = 0.0
    for g, pos in zip(sess, positions, strict=True):
        c = g["c"].to_numpy(dtype=float)
        o = g["o"].to_numpy(dtype=float)
        n = len(c)
        step = np.diff(c, prepend=c[0]) * SPEC.multiplier
        recomputed += float(np.cumsum(pos[:-1] * step[1:])[-1])
        dpos = np.diff(pos, prepend=0.0)[:n - 1]
        subsidy += -float((dpos * (c[:n - 1] - o[1:])).sum()) * SPEC.multiplier
        legs += float(np.abs(dpos).sum())
    return {"refused": refused, "out": out, "recomputed": recomputed, "subsidy": subsidy,
            "legs": legs,
            "ticks_per_leg": subsidy / (SPEC.multiplier * SPEC.tick * legs),
            "gross_ex_subsidy": out["gross"] - subsidy}


def test_decision_bar_close_fill_is_the_entire_edge(fill_subsidy):
    """CHARACTERISATION. Leak: the funnel decides on bar i's close and fills at bar i's close.
    The signal reads no future bar; the EXECUTION does - it trades at a price that has already
    printed.

    Correct behaviour: fill at the first price that trades after the decision (bar i+1's
    open), or charge the difference. Today: neither. Measured on this fixture, against a
    next-open fill on identical data and an identical position path:

        legs                       4,760
        subsidy                    +2.0003 ticks/leg   ($11,901.65)
        gross as the engine books it  +$11,923.05
        gross without the subsidy         +$21.40      (0.18% of it)

    (Audit, real ES: +0.0551 ticks/leg over 68,388 legs, worth +51% of gross on a
    mean-reversion signal. This fixture uses a two-tick half-spread to make the same
    mechanism deterministic rather than statistical.)

    So 99.8% of the reported gross is the fill convention and the residual is indistinguish-
    able from zero - and the rule clears the cost gate (45.1%), the Topstep gate (pass rate
    1.0) and 5/5 walk-forward folds on the way through.
    """
    fs = fill_subsidy
    assert not fs["refused"], "a guard exists now - delete the xfail marker on the paired test"
    assert abs(fs["out"]["gross"] - fs["recomputed"]) < 1e-9, (
        f"identity check failed: this fixture recomputes gross as {fs['recomputed']:,.6f} "
        f"against the evaluator's {fs['out']['gross']:,.6f}; the subsidy below is not "
        f"attributable until these agree")
    assert fs["ticks_per_leg"] > 1.5, (
        f"the fill subsidy measured only {fs['ticks_per_leg']:.4f} ticks/leg over "
        f"{fs['legs']:,.0f} legs")
    assert fs["subsidy"] / fs["out"]["gross"] > 0.95, (
        f"the fill subsidy is only {fs['subsidy'] / fs['out']['gross']:.2%} of the gross the "
        f"engine reports; this fixture no longer shows a rule whose entire edge is its fill")
    assert abs(fs["gross_ex_subsidy"]) < 0.02 * fs["out"]["gross"], (
        f"the rule should be worth ~nothing once filled at the next open: gross "
        f"{fs['out']['gross']:,.2f}, gross ex-subsidy {fs['gross_ex_subsidy']:,.2f}")
    assert rejected_gates(fs["out"]) == [], (
        f"characterisation drift: the gates now reject it {rejected_gates(fs['out'])}, so it "
        f"no longer demonstrates a subsidy that survives the funnel")


# RATCHET CLEARED 2026-09-13: the result dict now carries fill_convention, gross_next_open_fill and fill_subsidy, so the subsidy is a number the reader can subtract.
def test_decision_bar_close_fill_must_be_refused_or_reported(fill_subsidy):
    """RATCHET. Correct behaviour: the engine must either refuse to fill at the decision
    bar's close, or report the subsidy beside the P&L so a reader can subtract it. Today it
    returns `pnl / sessions / trades / gross / costs / mean_per_session` and the gate keys -
    not one word about where the fill happened - so this xfails.
    """
    fs = fill_subsidy
    assert fs["refused"] or fill_convention_reported(fs["out"]), (
        f"the engine filled at the decision bar's close for a subsidy of "
        f"{fs['ticks_per_leg']:.4f} ticks/leg (${fs['subsidy']:,.0f} of a ${fs['out']['gross']:,.0f} "
        f"gross) and reported neither the convention nor the subsidy. "
        f"Keys returned: {sorted(fs['out'])}")


# =====================================================================================
# SECTION E - COUNTER-EXAMPLES TO features.assert_causal
# `_assert_causal_at` perturbs only c, h, l, o, v and compares with np.isclose
# =====================================================================================

def quote_leak_feature() -> fe.Feature:
    """Tomorrow's BID. A blatant leak in a column the guard never touches."""
    return _redteam_feature("rt_leak_next_bid",
                            lambda d: _series(d, "bid").shift(-1), ("bid", "c"))


def tail_argmax_feature() -> fe.Feature:
    """Where the session's high sits among its last five bars, broadcast to every bar.

    An ORDER statistic over the future. The guard's perturbation multiplies every bar from
    `at` onwards by 1.05, and its probe points never reach past 0.8*n, so the whole five-bar
    tail is scaled by the same factor - which leaves an argmax exactly where it was.
    """
    def fn(d):
        c = np.asarray(d["c"], dtype=float)
        k = min(5, len(c))
        return pd.Series(float(int(np.argmax(c[-k:]))), index=d.index)
    return _redteam_feature("rt_leak_tail_argmax", fn)


def sub_tolerance_feature() -> fe.Feature:
    """The next bar's direction, at amplitude 1e-9 on a base of 1.0.

    `_assert_causal_at` compares with `np.isclose` (rtol 1e-5, atol 1e-8), so a perturbation
    of 2e-9 is "close" and the guard reports the feature clean. The SIGN of the leak survives
    float64 intact, so nothing about its usefulness is small.
    """
    def fn(d):
        c = _series(d, "c")
        return 1.0 + 1e-9 * np.sign(c.diff().shift(-1))
    return _redteam_feature("rt_leak_sub_tolerance", fn)


def _guard_probe_point(n: int) -> int:
    """The latest bar `assert_causal` will ever perturb on a frame of `n` rows."""
    return int(n * 0.8)


def test_quote_column_leak_is_invisible_to_the_guards_perturbation(quoted):
    """CHARACTERISATION (and the fix, demonstrated). Leak: `bid.shift(-1)`.

    `_assert_causal_at` bumps `c, h, l, o` by 1.05 and `v` by 3.0. It never touches `bid`,
    `ask`, `bid_size` or `ask_size`, so a feature built purely from a quote column is
    bit-identical before and after the perturbation and the guard reports it clean. This test
    proves both halves: the shipped bump leaves the feature untouched, and a bump that
    INCLUDES the quote columns finds the leak immediately (at bar 207 of 320). The fix is four
    column names.
    """
    feat = quote_leak_feature()
    at = _guard_probe_point(len(quoted))
    base = np.asarray(feat.fn(quoted), dtype=float)

    shipped = quoted.copy()
    for col in ("c", "h", "l", "o"):
        shipped.iloc[at:, shipped.columns.get_loc(col)] *= 1.05
    shipped.iloc[at:, shipped.columns.get_loc("v")] *= 3.0
    assert np.array_equal(np.asarray(feat.fn(shipped), dtype=float), base, equal_nan=True), (
        "the shipped perturbation now moves a quote-only feature; the blind spot may be "
        "closed - check whether the paired ratchet test XPASSes")

    quote_aware = quoted.copy()
    for col in ("bid", "ask", "bid_size", "ask_size"):
        quote_aware.iloc[at:, quote_aware.columns.get_loc(col)] *= 1.05
    after = np.asarray(feat.fn(quote_aware), dtype=float)
    both_nan = np.isnan(base[:at]) & np.isnan(after[:at])
    differs = ~both_nan & ~np.isclose(base[:at], after[:at], equal_nan=True)
    assert differs.any(), (
        "a bump that includes the quote columns did not find the leak either; this fixture "
        "no longer demonstrates the blind spot")


# RATCHET CLEARED 2026-09-13: _assert_causal_at now perturbs EVERY numeric column present, not the hard-coded c/h/l/o/v, so a bid.shift(-1) leak is caught at bar 1 (4997.875 -> 15711.614). spread_bps and quote_imbalance were never actually tested before this.
def test_quote_column_leak_must_be_caught_by_assert_causal(quoted):
    """RATCHET. Correct behaviour: `assert_causal` must catch `bid.shift(-1)`. Today it
    returns cleanly, so this xfails. Fix: perturb every column the feature DECLARES in
    `requires`, rather than a hard-coded OHLCV list.
    """
    with pytest.raises(AssertionError):
        fe.assert_causal(quote_leak_feature(), quoted)


def test_future_argmax_survives_the_guards_uniform_bump(quoted):
    """CHARACTERISATION. Leak: the position of the maximum close among the session's last
    five bars, known at bar 0.

    The guard's perturbation is a UNIFORM multiplicative bump of the tail, and a uniform
    positive scaling preserves order - so an argmax, a rank, an "is the high before the low"
    comparison, or any other order statistic taken over a window that lies entirely inside
    the bumped region is invariant to it. This test proves the feature really does read the
    future (reversing the last five closes changes it) while being bit-identical under the
    guard's own bump.
    """
    feat = tail_argmax_feature()
    base = np.asarray(feat.fn(quoted), dtype=float)
    at = _guard_probe_point(len(quoted))
    assert at < len(quoted) - 5, (
        "the guard now probes inside the five-bar tail, which would break the order "
        "invariance this counter-example depends on")

    bumped = quoted.copy()
    for col in ("c", "h", "l", "o"):
        bumped.iloc[at:, bumped.columns.get_loc(col)] *= 1.05
    assert np.array_equal(np.asarray(feat.fn(bumped), dtype=float), base), (
        "the uniform bump moved an order statistic over the bumped region; the guard may "
        "have been changed - check whether the paired ratchet test XPASSes")

    reordered = quoted.copy()
    tail = reordered.index[-5:]
    reordered.loc[tail, "c"] = reordered.loc[tail, "c"].to_numpy()[::-1]
    assert not np.array_equal(np.asarray(feat.fn(reordered), dtype=float), base), (
        "reversing the last five closes did not change the feature, so it is not reading "
        "the future and this counter-example is vacuous")


# RATCHET CLEARED 2026-09-13: the bump is now a per-row random scale-and-jitter instead of a uniform x1.05, so it no longer preserves order and a future argmax is caught at bar 0 (0.0 -> 3.0).
def test_future_argmax_leak_must_be_caught_by_assert_causal(quoted):
    """RATCHET. Correct behaviour: `assert_causal` must catch an order statistic taken over
    future bars. Today the perturbation is order-preserving, so it does not, and this xfails.
    """
    with pytest.raises(AssertionError):
        fe.assert_causal(tail_argmax_feature(), quoted)


def test_sub_tolerance_leak_is_exploitable_to_the_entire_ceiling(sessions, ceiling):
    """CHARACTERISATION. Leak: `1.0 + 1e-9 * sign(c.diff().shift(-1))`.

    The perturbation the guard applies does move this feature - but by 2e-9, and
    `np.isclose(rtol=1e-5, atol=1e-8)` calls that unchanged. A leak's AMPLITUDE and a leak's
    VALUE are different things: `sign(x - 1.0)` recovers the next bar's direction exactly,
    and pushed through the funnel it realises 100.00% of the theoretical ceiling and clears
    every gate. This test proves the leak is worth the maximum possible amount despite
    sitting nine orders of magnitude below the guard's tolerance.
    """
    feat = sub_tolerance_feature()
    feats = [pd.DataFrame({feat.name: np.asarray(feat.fn(g), dtype=float)}, index=g.index)
             for g in sessions]
    refused, out = run_funnel(
        sessions, feats,
        lambda X: np.nan_to_num(np.sign(X[feat.name].to_numpy(dtype=float) - 1.0), nan=0.0),
        "sub_tol")
    assert not refused, "a guard exists now - delete the xfail marker on the paired test"
    frac = out["gross"] / ceiling
    assert abs(frac - 1.0) < 1e-9, (
        f"a 1e-9 leak realised {frac:.6%} of the ceiling; expected the full 100%")
    assert rejected_gates(out) == [], (
        f"characterisation drift: gates now reject the sub-tolerance leak "
        f"{rejected_gates(out)}")


# RATCHET CLEARED 2026-09-13: the comparison is exact `!=` instead of isclose(atol=1e-8); measured worst head deviation across all 19 shipped features at all 9 probe points is exactly 0.0, so no tolerance was needed. The 2e-9 leak is caught at bar 1.
def test_sub_tolerance_leak_must_be_caught_by_assert_causal(quoted):
    """RATCHET. Correct behaviour: caught. Today `np.isclose` swallows it, so this xfails."""
    with pytest.raises(AssertionError):
        fe.assert_causal(sub_tolerance_feature(), quoted)


# =====================================================================================
# SECTION F - THE TWO PANDAS BOOKS
# `scripts/sweep_s19.py::simulate` and `scripts/sweep_s25.py::legs_simulate`
# =====================================================================================

#: `signals` reads these at import and, when set, loads CSVs off disk that would change the
#: books below. Skip rather than produce a number that depends on the ambient shell.
_S1_ENV = ("S1_ML_SCORES", "S1_VOL_RETURNS", "S1_REGIME_SERIES")
_s1_overridden = sorted(k for k in _S1_ENV if os.environ.get(k))
needs_shipped_signals = pytest.mark.skipif(
    bool(_s1_overridden),
    reason=f"signals.py is overridden by the environment: {_s1_overridden}")

#: Short momentum horizons so the book runs in seconds AND so the leak bites: every lookback
#: here is below `mom_skip_min_lookback` (120), so `horizon_returns` ends each window at
#: `prices.iloc[-1]` with no skip - which is what makes the last row of the window the thing
#: the signal actually reads.
FAST_PARAMS = sig.Params(mom_lookbacks=(2, 3, 5, 10), regime_median_window=40,
                         regime_vol_window=10, vol_est_window=20, alloc_vol_window=10,
                         trail_window=20, mom_vol_window=20, history_bars=70)
_EQ_N = 260


@pytest.fixture(scope="module")
def equity_frames():
    """A deterministic close/open panel over the shipped traded universe."""
    tickers = sig.traded_universe(FAST_PARAMS)
    rng = np.random.default_rng(SEED + 3)
    index = pd.bdate_range("2023-01-02", periods=_EQ_N)
    closes = pd.DataFrame(
        {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.013, _EQ_N))) for t in tickers},
        index=index)
    opens = closes.shift(1).bfill() * (1.0 + rng.normal(0.0, 0.002, (_EQ_N, len(tickers))))
    return {"close": closes, "open": opens}


@pytest.fixture(scope="module")
def s19_books(equity_frames):
    """`sweep_s19.simulate` at the deployed convention and at `lag=-2`.

    `lag` is documented as "extra sessions of STALENESS": 0 is the deployed runner. Nothing
    in the function asserts `lag >= 0`, and a negative value simply widens the decision
    window - `closes.iloc[lo:i - lag]` - into and then past the session the orders fill in.
    """
    index = equity_frames["close"].index
    start, end = str(index[0].date()), str(index[-1].date())
    out = {}
    for label, lag in (("deployed", 0), ("one_day_ahead", -2)):
        refused, book = leakage_refusal(s19.simulate, equity_frames, FAST_PARAMS, lag,
                                        "close", start, end)
        out[label] = {"refused": True} if refused else s19.summarize(book, label)
    return out


@needs_shipped_signals
def test_sweep_s19_negative_lag_is_refused_and_the_deployed_lag_is_not(s19_books):
    """RETIRED CHARACTERISATION, kept as the record of what the leak was worth.

    Leak: `sweep_s19.simulate(..., lag=-2, fill="close")`. The decision window became
    `closes.iloc[lo:i+2]`, so the momentum score was computed with tomorrow's close as its
    last bar while the orders still filled at today's. The only bound on `lag` was
    `i0 = max(searchsorted(start) + 1, lag + history_bars)`, and a negative value makes that
    bound SMALLER rather than illegal - it loosened the one line that looked like a check.

    Measured on identical prices before the guard landed:

        deployed  lag  0 / close   CAR    18.65%   Sharpe  1.043   MaxDD 11.08%
        oracle    lag -2 / close   CAR 1,369.21%   Sharpe 15.403   MaxDD  1.79%

    The audit measured CAR 2,057% / Sharpe 18.21 for the same cheat on the real panel.

    What this now asserts is the discrimination, which is the part that can go wrong in the
    future: the negative lag is refused AND the deployed convention still runs and still
    produces the book it always did. A guard that refused both would satisfy the ratchet and
    destroy the harness.
    """
    dep, oracle = s19_books["deployed"], s19_books["one_day_ahead"]
    assert oracle.get("refused") is True, (
        "simulate() no longer refuses lag=-2; the guard has been removed or weakened")
    assert not dep.get("refused"), (
        "simulate() refused the DEPLOYED lag=0 convention - the guard is a false-positive "
        "machine and the whole S-19 harness is broken")
    assert 10.0 < dep["CAR"] < 30.0, (
        f"the deployed book's CAR moved to {dep['CAR']:,.2f}; it was 18.65% and this fixture "
        f"is supposed to be deterministic")
    assert 0.5 < dep["Sharpe"] < 2.0, f"deployed Sharpe {dep['Sharpe']:.3f}"


@needs_shipped_signals
# RATCHET CLEARED 2026-09-13: sweep_s19.simulate raises LeakageError on lag < 0. The
# guard discriminates: lag=0, the deployed convention, is untouched.
def test_sweep_s19_must_refuse_a_window_that_reaches_past_the_fill(equity_frames):
    """RATCHET. Correct behaviour: `simulate` must raise when `lag < 0`, i.e. when the closes
    it hands the signal include the fill session or later. Today it silently produces the
    book measured above, so this xfails.
    """
    index = equity_frames["close"].index
    refused, _ = leakage_refusal(s19.simulate, equity_frames, FAST_PARAMS, -2, "close",
                                 str(index[0].date()), str(index[-1].date()))
    assert refused, (
        "simulate() accepted lag=-2, which puts closes[i+1] into the window the signal reads "
        "while the orders fill at close[i]; it neither raised nor flagged")


def _weights_from(table: pd.DataFrame, n_top: int = 3):
    """A `weights_fn` in the shape S-41 defined: called as `weights_fn(index[i])`, returns a
    target-weight dict. It is handed a TIMESTAMP and nothing else, so whether the row it
    looks up is causal is entirely a matter of what the caller closed over."""
    def weights_fn(ts):
        row = table.loc[ts].dropna()
        if row.empty:
            return {}
        return {t: 1.0 / n_top for t in row.sort_values(ascending=False).head(n_top).index}
    return weights_fn


@pytest.fixture(scope="module")
def s25_books(equity_frames):
    closes = equity_frames["close"]
    index = closes.index
    start, end = str(index[0].date()), str(index[-1].date())
    past = closes / closes.shift(1) - 1.0           # yesterday's return: causal
    forward = closes.shift(-1) / closes - 1.0       # tomorrow's return: known to nobody
    out = {}
    for label, table in (("causal", past), ("one_day_ahead", forward)):
        refused, book = leakage_refusal(s25.legs_simulate, equity_frames, FAST_PARAMS,
                                        "both", start, end,
                                        weights_fn=_weights_from(table))
        out[label] = {"refused": True} if refused else s19.summarize(book, label)
    return out


@needs_shipped_signals
def test_sweep_s25_weights_fn_bypasses_the_causality_window(s25_books):
    """CHARACTERISATION. Leak: S-41's `weights_fn`, given a table of TOMORROW's returns.

    `legs_simulate` computes a causality window - `closes.iloc[lo:i - lag]` - and then, when
    `weights_fn` is supplied, does not use it: the branch is `targets = weights_fn(index[i])`.
    The hook receives a timestamp and returns weights, so the window that the whole function
    is organised around is bypassed by construction, and the docstring's own guarantee
    ("everything downstream ... is untouched") is about the EXECUTION, not the information
    set.

    Correct behaviour: a supplied weight path must be checked against the same causality
    window the built-in signal is held to. Today, silently, on identical prices:

        weights from closes[i]/closes[i-1]     CAR    24.21%   Sharpe  1.826   MaxDD 8.03%
        weights from closes[i+1]/closes[i]     CAR 2,554.97%   Sharpe 36.552   MaxDD 0.00%

    A maximum drawdown of exactly zero over 190 sessions is what a leak looks like from the
    outside, and nothing in the pipeline says so. The audit measured CAR 2,133% /
    Sharpe 18.95 for the same cheat on the real panel.
    """
    causal, oracle = s25_books["causal"], s25_books["one_day_ahead"]
    assert not oracle.get("refused"), (
        "legs_simulate() now refuses a future-reading weights_fn - a guard landed; delete "
        "the xfail marker on the paired test and retire this characterisation")
    assert not causal.get("refused"), (
        "legs_simulate() refused a CAUSAL weights_fn; the new guard is a false-positive "
        "machine")
    assert oracle["Sharpe"] > 10.0, (
        f"the future-weights path only reached Sharpe {oracle['Sharpe']:.3f}")
    assert oracle["CAR"] > 500.0, f"CAR {oracle['CAR']:,.2f}; expected four figures"
    assert oracle["Sharpe"] > causal["Sharpe"] + 20.0, (
        f"Sharpe {oracle['Sharpe']:.3f} against the causal control's {causal['Sharpe']:.3f}; "
        f"the contrast this test rests on has gone")
    assert oracle["MaxDD"] < causal["MaxDD"], (
        f"MaxDD {oracle['MaxDD']:.2f}% against the causal control's {causal['MaxDD']:.2f}%")


@needs_shipped_signals
@pytest.mark.xfail(strict=True, reason=(
    "sweep_s25.legs_simulate hands weights_fn a bare timestamp and accepts whatever dict "
    "comes back. It has the causality window in hand on the same line and does not use it. "
    "ATTEMPTED AND REVERTED 2026-09-13: requiring the hook to accept `window=` and passing it "
    "the causal panel was implemented and measured, and it refuses the CAUSAL control too - "
    "{'causal': {'refused': True}, 'one_day_ahead': {'refused': True}} - because a legacy "
    "one-argument hook is refused whether or not it cheats. That is the false-positive "
    "machine this file exists to catch, so it was reverted rather than shipped. The contract "
    "change is necessary and not sufficient: a hook can accept the window and still read a "
    "closure. A guard that actually discriminates has to test the WEIGHTS - e.g. their "
    "association with the next session's realised return against a causal baseline, the "
    "equity-path analogue of the futures funnel's ceiling canary - and that is a real piece "
    "of work, not an API tweak."))
def test_sweep_s25_must_refuse_a_weights_fn_that_reads_the_future(equity_frames):
    """RATCHET. Correct behaviour: refuse (or detect) a weight path that cannot be reproduced
    from the closes through `i - lag`. Today the hook is trusted absolutely, so this xfails.
    """
    closes = equity_frames["close"]
    index = closes.index
    forward = closes.shift(-1) / closes - 1.0
    refused, _ = leakage_refusal(s25.legs_simulate, equity_frames, FAST_PARAMS, "both",
                                 str(index[0].date()), str(index[-1].date()),
                                 weights_fn=_weights_from(forward))
    assert refused, (
        "legs_simulate() executed a weight path built entirely from closes[i+1] and neither "
        "raised nor flagged; the causality window it computes on the line above was never "
        "consulted")


# =====================================================================================
# SECTION G - THE CLEAN CONTROLS
# Without these the suite would be satisfiable by an engine that rejects everything.
# =====================================================================================

def clean_feature() -> fe.Feature:
    """A strictly causal 10-bar return. Nothing about it may ever be flagged."""
    return _redteam_feature("rt_clean_ret_10",
                            lambda d: _series(d, "c").pct_change(10), ("c",), 10)


def test_production_feature_library_is_strictly_causal(quoted):
    """INVARIANT. No leak injected. The whole shipped `features.library()` - all 19 columns,
    including the two microstructure features that only exist on a quoted frame - must pass
    `audit_causality` with an empty dict.

    This is the audit's own "proven strong" finding held in place, and it is what stops the
    ratchets above from being satisfied by a guard that simply refuses everything: the day
    `assert_causal` starts catching quote leaks, order leaks and 1e-9 leaks, it must still
    pass all nineteen of these.
    """
    lib = fe.library()
    assert lib.missing(set(quoted.columns)) == {}, (
        "the quoted fixture no longer supports the whole library, so this control is not "
        "exercising the microstructure family")
    failures = fe.audit_causality(lib, quoted)
    assert failures == {}, f"the shipped feature library is no longer causal: {failures}"


def test_a_strictly_causal_feature_is_admitted_and_not_flagged(quoted, sessions):
    """INVARIANT. No leak injected. A hand-written, strictly causal feature must pass
    `assert_causal` AND be admitted by the funnel's feature builder.

    The second half is the one that matters after a guard lands: a builder that started
    rejecting `pct_change(10)` would make every ratchet in section B pass for the wrong
    reason. This test must pass today and forever.
    """
    feat = clean_feature()
    fe.assert_causal(feat, quoted)                      # must not raise
    refused, admitted = _funnel_admits(feat, sessions)
    assert not refused and admitted, (
        f"the funnel refused a strictly causal feature (refused={refused}, "
        f"admitted={admitted}); a leakage guard has become a false-positive machine")


def test_a_strictly_causal_strategy_is_not_flagged_and_stays_far_from_the_ceiling(
        sessions, library_frames, ceiling):
    """INVARIANT. No leak injected. `-sign(z_60)` - a causal mean-reversion rule on the real
    library - must never be flagged as a leak, must stay far from the theoretical ceiling,
    and must be discriminated against by the gates that every oracle above walks through.

    Measured on this fixture: 3.97% of the ceiling and rejected at the Topstep gate, against
    100% and cleared for the close oracle. That gap IS the discrimination the funnel is
    supposed to have and today does not; when a leakage guard lands it must widen the gap,
    not close it from the wrong end.
    """
    refused, out = run_funnel(
        sessions, library_frames,
        lambda X: -np.sign(np.nan_to_num(X["z_60"].to_numpy(dtype=float), nan=0.0)),
        "z60_meanrev")
    assert not refused, "a leakage guard refused a strictly causal strategy"
    assert leak_verdict(out) is not True, (
        f"a strictly causal strategy was flagged as a leak: {out}")
    frac = out["gross"] / ceiling
    assert frac < 0.10, (
        f"the causal control realised {frac:.2%} of the theoretical ceiling; on random-walk "
        f"bars it should be near zero, and a control that approaches the ceiling is not a "
        f"control")
    assert rejected_gates(out), (
        "the funnel's gates cleared a causal random-walk rule; they no longer discriminate "
        "between it and the oracles above, which is the only bad outcome for this suite")
