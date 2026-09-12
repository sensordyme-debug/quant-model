"""AUD-25 / S-36: `Params.__post_init__` must widen `history_bars` for every price window.

The defect. The guard's own docstring says it exists so that "the horizon is what is being
tested", and before S-36 it computed `need` from `mom_lookbacks`, `mom_skip` and
`rank_persist` only. S-36 enumerated the eleven integer windows on `Params` and found **seven**
outside the guard, in two failure modes:

  SILENT-ZERO      `trend_window`, `regime_vol_window` - longer than the history and `risk_on`
                   returns False forever, so the book sits in the off-state for the whole
                   sample and the sweep prints a tidy 0% CAR. This is the S-9 failure the
                   guard was written for, and it is the one the audit named.
  SILENT-TRUNCATE  `alloc_vol_window`, `regime_median_window`, `vol_est_window`,
                   `mom_vol_window`, `trail_window` - `.iloc[-N:]` quietly yields fewer than N
                   bars, so two DIFFERENT values of the parameter are the SAME CELL. S-36
                   proved each of the five produced byte-identical weights at
                   `history_bars + 100` and at `+ 500`. The audit did not name this half and
                   it is the worse one: a zero CAR is visible in any table, a grid reporting a
                   flat shelf because its cells are the same run is not - and S-33 established
                   that on this sleeve a shelf is the only parameter result worth reporting.

What these tests defend, in order of how much it would cost to lose:

1. `test_defaults_unchanged` - the champion's `history_bars` is still 307 and `DEFAULTS ==
   Params()`. The widening is inert for the deployed book; if it ever is not, the patch has
   silently moved the strategy and must be withdrawn.
2. `test_every_price_window_widens` - the enumeration is re-derived from the dataclass rather
   than remembered, so a window field added to `Params` later fails this test instead of
   quietly joining the silent surface. This is the S-35 rule applied one class over: a guard
   must cover every axis, and that list has to come from the source.
3. `test_iv_scale_window_is_excluded` - the one deliberate exclusion, pinned with its reason
   so nobody "fixes" it later. `iv_scale_window` is read off the IV store, not off `prices`,
   so `history_bars` does not bound it and it already fails loudly.
4. `test_ml_rank_mode_gates_on_both_signs` - the OTHER half of AUD-25. `ML_MODE="rank"` funds
   a name only when its momentum score AND its forecast are positive. S-36 measured the second
   gate at **+0.286 CAR points** (it helps) over 3,690 sessions of `data/f3/ml_scores.csv`, so
   the code was kept and the docstring corrected. This test pins the behaviour the number was
   measured on, so a later reading of the prose cannot quietly remove a gate that pays.
"""
from __future__ import annotations

import sys
from dataclasses import fields, replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))

import signals as sig  # noqa: E402

#: Windows that are read off the `prices` frame the guard sizes, with the companion switch
#: that has to be on for the window to be read at all. Derived by S-36 from every `.iloc[-N:]`
#: and `rolling(N)` in the module; `test_every_price_window_widens` re-derives the field list
#: from the dataclass so that this map cannot silently fall behind `Params`.
PRICE_WINDOWS = {
    "alloc_vol_window": {"weight_mode": "invvol"},
    "trend_window": {},
    "regime_vol_window": {},
    "regime_median_window": {},
    "vol_est_window": {},
    "mom_vol_window": {"mom_score": "riskadj"},
    "trail_window": {"trail_stop": 0.10},
}

#: Read off the IV store, not off `prices`. Excluded on purpose - see the module docstring.
NON_PRICE_WINDOWS = {"iv_scale_window"}

#: Already covered before S-36, and covered by a different arithmetic (they lengthen the
#: momentum window rather than being compared against the whole history).
MOMENTUM_WINDOWS = {"mom_skip", "rank_persist", "mom_lookbacks", "mom_skip_min_lookback",
                    "dv_window", "history_bars", "min_history"}


def test_defaults_unchanged():
    """The widening must be inert for the deployed book."""
    p = sig.Params()
    assert p.history_bars == 307, (
        f"history_bars moved to {p.history_bars}; the champion is sized on 307 and S-25..S-36 "
        f"all reproduce 22.192150170492255% CAR on it")
    assert sig.DEFAULTS == sig.Params()


@pytest.mark.parametrize("field_name", sorted(PRICE_WINDOWS))
def test_every_price_window_widens(field_name):
    """A window longer than the default history must widen `history_bars`, not be truncated."""
    base = sig.Params()
    probe = base.history_bars + 100
    p = replace(base, **{field_name: probe}, **PRICE_WINDOWS[field_name])
    assert p.history_bars >= probe, (
        f"{field_name}={probe} left history_bars at {p.history_bars}: the parameter is "
        f"silently truncated or silently zeroed, which is exactly what this guard exists "
        f"to prevent (AUD-25)")


def test_window_enumeration_is_pinned_to_params():
    """A new `*_window` field on `Params` must be classified, not silently left out.

    This is the test that keeps the guard honest over time. Before S-36 the guard covered one
    window because each of the others was added by an item that did not think about history,
    and nothing failed. Now adding one fails here until it is put in exactly one of the three
    buckets above.
    """
    known = set(PRICE_WINDOWS) | NON_PRICE_WINDOWS | MOMENTUM_WINDOWS
    found = {f.name for f in fields(sig.Params)
             if f.name.endswith(("_window", "_bars", "_lookbacks", "_skip", "_persist"))}
    unclassified = found - known
    assert not unclassified, (
        f"unclassified window field(s) on Params: {sorted(unclassified)}. Add each to "
        f"PRICE_WINDOWS (and to __post_init__'s `need`), to NON_PRICE_WINDOWS with its "
        f"reason, or to MOMENTUM_WINDOWS.")


def test_iv_scale_window_is_excluded_with_its_reason():
    """`iv_scale_window` reads the IV store; widening the PRICE window for it would be cargo."""
    base = sig.Params()
    p = replace(base, iv_scale_window=base.history_bars + 100, iv_scale_power=1.0)
    assert p.history_bars == base.history_bars, (
        "iv_scale_window must NOT widen the price window: it is bounded by the IV store and "
        "already fails loudly with iv_scale_reason='uncovered'")
    src = (REPO / "algorithms" / "s1_momo" / "signals.py").read_text(encoding="utf-8")
    assert "iv_scale_window` is deliberately NOT here" in src, (
        "the exclusion lost its written reason; a later reader will 'fix' it")


def test_silent_zero_is_closed():
    """The audit's own example: a long `trend_window` used to mean risk-off forever."""
    base = sig.Params()
    long_trend = base.history_bars + 100
    p = replace(base, trend_window=long_trend)
    assert p.history_bars >= long_trend
    # And the guard inside `risk_on` is now unreachable for a window the guard has sized:
    # `len(spy) >= trend_window` holds by construction on a full `history_bars` window.
    spy = pd.Series(np.linspace(100.0, 200.0, p.history_bars),
                    index=pd.bdate_range("2020-01-01", periods=p.history_bars))
    prices = pd.DataFrame({sig.REGIME_TICKER: spy})
    _, diag = sig.risk_on(prices, p)
    assert diag.get("regime_reason") != "insufficient trend history"


def test_ml_rank_mode_gates_on_both_signs():
    """`ML_MODE="rank"` funds a name only if BOTH its momentum score and its forecast pass.

    Measured, not assumed: S-36 priced the second gate at +0.286 CAR points over 3,690
    sessions, which is why the code was kept and the docstring fixed instead.
    """
    p = sig.Params()
    idx = pd.bdate_range("2020-01-01", periods=p.history_bars)
    # Two names, both with strongly positive momentum, so the FIRST gate passes for both.
    prices = pd.DataFrame({
        "A": np.linspace(100.0, 300.0, len(idx)),
        "B": np.linspace(100.0, 250.0, len(idx)),
    }, index=idx)

    # Forecast: A positive, B negative. Under the docstring's old wording B would still be
    # fundable (reordered, not re-gated); under the shipped code it is refused.
    table = pd.DataFrame({"A": [2.0], "B": [-2.0]},
                         index=pd.DatetimeIndex([idx[-1].normalize()]))
    saved = (sig._ML_TABLE, sig._ML_LOADED, sig.ML_MODE)
    sig._ML_TABLE, sig._ML_LOADED, sig.ML_MODE = table, True, "rank"
    try:
        scores, eligible = sig.momentum_scores(prices, p)
        assert bool(eligible["A"]) and bool(eligible["B"]), (
            "both names clear the momentum floor, so the FIRST gate is not what refuses B")
        assert scores["A"] == 2.0 and scores["B"] == -2.0, (
            "in rank mode the returned score IS the forecast")
        funded = sig.leaders(scores, eligible, p)
        assert funded == ["A"], (
            f"expected the negative forecast to be refused by the second gate, got {funded}")
    finally:
        sig._ML_TABLE, sig._ML_LOADED, sig.ML_MODE = saved


def test_ml_docstring_records_the_measurement():
    """The corrected prose has to carry the number that justified keeping the code."""
    src = (REPO / "algorithms" / "s1_momo" / "signals.py").read_text(encoding="utf-8")
    assert "+0.286 CAR points" in src
    assert "two positive numbers" in src


def test_main_py_marks_the_inert_lean_setting():
    """AUD-25(d): `minimum_order_margin_portfolio_percentage` is inert on the market_order path.

    S-36 confirmed from the LEAN source that the setting is read in `PortfolioTarget.Percent`,
    `ImmediateExecutionModel` and `BuyingPowerModel.GetMaximumOrderQuantityFor{Target,Delta}`,
    and at none of those does `market_order(symbol, shares)` arrive. The line is kept (removing
    it would owe a LEAN rerun to prove `OrderListHash` unchanged, for zero gain) and labelled,
    so it cannot be read as a second execution band. `min_order_value` is the real one.
    """
    src = (REPO / "algorithms" / "s1_momo" / "main.py").read_text(encoding="utf-8")
    assert "INERT ON THIS ALGORITHM'S PATH" in src
    assert "self.market_order(" in src
    assert "self.min_order_value" in src
