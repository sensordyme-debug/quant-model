"""Tests for the sizers (Phase 36) and portfolio aggregation (Phase 37 foundations).

Three properties are load-bearing and most tests are built around one of them: every sizer's
answer is min'd against every limit above it and the decision names the binding level; a
Kelly size is never produced from a sample that cannot support it; and anything that cannot
be computed from the inputs comes back unavailable with a reason rather than as a number.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from quant_brain.core import portfolio as pf
from quant_brain.core import sizing as sz
from quant_brain.core.instruments import AssetClass, InstrumentSpec, equity
from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme import twin as tw

ES = InstrumentSpec("ES", AssetClass.FUTURE, multiplier=50.0, tick=0.25, exchange="CME")
NQ = InstrumentSpec("NQ", AssetClass.FUTURE, multiplier=20.0, tick=0.25, exchange="CME")
RTY = InstrumentSpec("RTY", AssetClass.FUTURE, multiplier=50.0, tick=0.10, exchange="CME")
MES = InstrumentSpec("MES", AssetClass.FUTURE, multiplier=5.0, tick=0.25, exchange="CME")
NVDA = equity("NVDA")
BTC = InstrumentSpec("BTC", AssetClass.CRYPTO, multiplier=1.0, tick=0.01)


def ctx(**kw) -> sz.SizeContext:
    kw.setdefault("spec", ES)
    return sz.SizeContext(**kw)


class FakeAccount:
    """Anything with the three members is a prop-firm account to the sizer.

    `max_contracts_for` ignores the symbol: this stands in for a firm whose allowance is
    already stated per contract, so the number needs no conversion. The real Topstep case,
    where it does, is `combine_account()` and `tests/test_contract_ceiling.py`.
    """

    def __init__(self, room: float, allowed: int | None):
        self._room = room
        self._allowed = allowed

    @property
    def distance_to_mll(self) -> float:
        return self._room

    @property
    def contracts_allowed(self) -> int | None:
        return self._allowed

    def max_contracts_for(self, symbol: str) -> int | None:
        return self._allowed


def combine_account(profit: float = 0.0) -> ts.TopstepAccount:
    acct = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    if profit:
        acct.settle_day(profit)
    return acct


# ======================================================================================
# KNOWN ANSWERS, ONE PER SIZER
# ======================================================================================

def test_fixed_risk_fraction_of_equity():
    # 0.5% of $100k = $500; a 4-point ES stop is $200 a contract; 2.5 rounds DOWN to 2.
    d = sz.FixedRiskSizer().size(ctx(equity=100_000.0, stop_distance=4.0))
    assert d.available and d.contracts == 2
    assert d.risk_dollars == pytest.approx(400.0)
    assert d.binding is sz.Binding.STRATEGY_SIGNAL
    assert d.signal == 2


def test_fixed_risk_in_dollars():
    d = sz.FixedRiskSizer(risk_dollars=1_000.0).size(ctx(stop_distance=4.0))
    assert d.contracts == 5 and d.risk_dollars == pytest.approx(1_000.0)


def test_fixed_risk_rounds_down_never_up():
    # $500 / $101 = 4.95 -> 4, not 5.
    d = sz.FixedRiskSizer().size(ctx(equity=100_000.0, stop_distance=2.02))
    assert d.contracts == 4


def test_zero_is_a_valid_answer_and_is_not_floored_to_one():
    # $500 / $1,000 = 0.5 -> 0. Available, decided, zero.
    d = sz.FixedRiskSizer().size(ctx(equity=100_000.0, stop_distance=20.0))
    assert d.available and d.contracts == 0 and d.risk_dollars == 0.0
    assert d.binding is sz.Binding.STRATEGY_SIGNAL


def test_volatility_target_known_answer():
    # 16% annual / sqrt(256) = 1% per day of $1m = $10,000 per day.
    # ES at 5,000 with 1% daily vol moves $2,500 a contract a day -> 4 contracts.
    d = sz.VolatilityTargetSizer(target_vol=0.16, periods_per_year=256).size(
        ctx(equity=1_000_000.0, price=5_000.0, volatility=0.01))
    assert d.contracts == 4
    # Volatility is not a stop: with no stop, dollars at risk are unknown, not zero.
    assert d.risk_dollars is None and "SIZING_RISK_UNKNOWN" in d.codes


def test_volatility_target_reports_risk_when_a_stop_is_supplied():
    d = sz.VolatilityTargetSizer(target_vol=0.16, periods_per_year=256).size(
        ctx(equity=1_000_000.0, price=5_000.0, volatility=0.01, stop_distance=4.0))
    assert d.contracts == 4 and d.risk_dollars == pytest.approx(800.0)


def test_atr_sizer_known_answer_and_owns_its_stop():
    # 0.5% of $100k = $500; 2 x ATR 5 = 10 points = $500 a contract -> exactly 1.
    d = sz.ATRSizer().size(ctx(equity=100_000.0, atr=5.0))
    assert d.contracts == 1 and d.risk_dollars == pytest.approx(500.0)
    # A different stop in the context does not change the ATR sizer's own risk figure.
    d2 = sz.ATRSizer().size(ctx(equity=100_000.0, atr=5.0, stop_distance=4.0))
    assert d2.contracts == 1 and d2.risk_dollars == pytest.approx(500.0)


def test_signal_sizer_passes_the_request_through():
    d = sz.SignalSizer().size(ctx(requested=3.0, stop_distance=4.0))
    assert d.contracts == 3 and d.binding is sz.Binding.STRATEGY_SIGNAL


def test_whole_units_for_futures_and_shares():
    # $500 / (3.4 x 50 = $170) = 2.94 -> 2.
    assert sz.FixedRiskSizer().size(ctx(equity=100_000.0, stop_distance=3.4)).contracts == 2
    # Equities: $500 / $2 a share = 250 shares.
    d = sz.FixedRiskSizer().size(ctx(spec=NVDA, equity=100_000.0, stop_distance=2.0))
    assert d.contracts == 250 and d.risk_dollars == pytest.approx(500.0)


def test_crypto_has_no_lot_size_and_is_refused_rather_than_guessed():
    d = sz.FixedRiskSizer().size(ctx(spec=BTC, equity=100_000.0, stop_distance=100.0))
    assert not d.available and d.contracts == 0 and d.binding is None
    assert "SIZING_UNSUPPORTED_ASSET_CLASS" in d.codes


# ======================================================================================
# THE HIERARCHY IS STRUCTURAL
# ======================================================================================

def test_fifty_contracts_on_a_five_contract_venue_gets_five_bound_by_venue():
    limits = sz.SizeLimits(venue_max_contracts=5)
    d = sz.SignalSizer().size(ctx(requested=50.0, limits=limits))
    assert d.contracts == 5
    assert d.binding == "venue"
    assert d.binding is sz.Binding.VENUE
    assert d.signal == 50
    assert "LIMIT_VENUE" in d.codes


def test_every_level_is_applied_and_the_tightest_is_named():
    limits = sz.SizeLimits(strategy_max_contracts=20, governor_max_contracts=10,
                           venue_max_contracts=5, prop_firm_max_contracts=3)
    d = sz.SignalSizer().size(ctx(requested=50.0, limits=limits))
    assert d.contracts == 3 and d.binding is sz.Binding.PROP_FIRM
    # Every level that would have reduced the ask is on the record, not only the tightest.
    assert {"LIMIT_STRATEGY_RISK", "LIMIT_GOVERNOR", "LIMIT_VENUE", "LIMIT_PROP_FIRM"} <= set(d.codes)


def test_a_lower_level_cannot_out_permit_a_higher_one():
    # Strategy says 50 is fine, governor says 10, venue says 20: venue is looser than the
    # governor and that does not help the strategy. The governor binds.
    limits = sz.SizeLimits(strategy_max_contracts=50, governor_max_contracts=10,
                           venue_max_contracts=20)
    d = sz.SignalSizer().size(ctx(requested=50.0, limits=limits))
    assert d.contracts == 10 and d.binding is sz.Binding.GOVERNOR


def test_ties_are_credited_to_the_higher_level():
    d = sz.SignalSizer().size(ctx(requested=5.0, limits=sz.SizeLimits(venue_max_contracts=5)))
    assert d.contracts == 5 and d.binding is sz.Binding.VENUE


def test_nothing_binding_names_the_signal():
    limits = sz.SizeLimits(strategy_max_contracts=10, governor_max_contracts=10,
                           venue_max_contracts=10, prop_firm_max_contracts=10)
    d = sz.SignalSizer().size(ctx(requested=2.0, stop_distance=4.0, limits=limits))
    assert d.contracts == 2 and d.binding is sz.Binding.STRATEGY_SIGNAL and d.codes == ()


def test_dollar_limits_convert_through_the_stop():
    # Governor allows $300 of risk; $200 a contract -> 1 contract.
    d = sz.SignalSizer().size(ctx(requested=10.0, stop_distance=4.0,
                                  limits=sz.SizeLimits(governor_max_risk=300.0)))
    assert d.contracts == 1 and d.binding is sz.Binding.GOVERNOR
    assert d.risk_dollars == pytest.approx(200.0)


def test_a_dollar_limit_without_a_stop_is_a_refusal_not_a_skipped_limit():
    d = sz.SignalSizer().size(ctx(requested=3.0, limits=sz.SizeLimits(governor_max_risk=1_000.0)))
    assert not d.available and d.contracts == 0
    assert "SIZING_NO_STOP" in d.codes


ALL_SIZERS = [
    ("fixed_risk", sz.FixedRiskSizer(), dict(equity=100_000.0, stop_distance=4.0)),
    ("vol_target", sz.VolatilityTargetSizer(target_vol=0.16, periods_per_year=256),
     dict(equity=1_000_000.0, price=5_000.0, volatility=0.01, stop_distance=4.0)),
    ("atr", sz.ATRSizer(), dict(equity=200_000.0, atr=5.0)),
    ("kelly", sz.KellySizer(max_risk_fraction=0.25),
     dict(equity=100_000.0, stop_distance=4.0, trades=[1.0] * 600 + [-1.0] * 400)),
    ("drawdown", sz.DrawdownAwareSizer(sz.FixedRiskSizer()),
     dict(equity=100_000.0, stop_distance=4.0, drawdown=0.0)),
    ("confidence", sz.ConfidenceWeightedSizer(sz.FixedRiskSizer()),
     dict(equity=100_000.0, stop_distance=4.0, confidence=1.0)),
    ("prop_firm", sz.PropFirmSizer(), dict(stop_distance=2.0, prop_account=FakeAccount(2_000.0, 50))),
    ("signal", sz.SignalSizer(), dict(requested=7.0, stop_distance=4.0)),
]


@pytest.mark.parametrize("label,sizer,fields", ALL_SIZERS, ids=[s[0] for s in ALL_SIZERS])
def test_every_sizer_is_clamped_by_the_venue(label, sizer, fields):
    free = sizer.size(ctx(**fields))
    assert free.available and free.contracts >= 2, f"{label} fixture must propose at least 2"
    capped = sizer.size(ctx(limits=sz.SizeLimits(venue_max_contracts=1), **fields))
    assert capped.contracts == 1 and capped.binding is sz.Binding.VENUE, label
    assert capped.signal == free.contracts


def test_a_prop_account_in_context_binds_every_sizer_by_the_full_room():
    # Fixed risk on $1m at 0.5% wants $5,000. A 10-point ES stop is $500 a contract, so the
    # strategy asks for 10 - but a fresh $50K Combine has $2,000 of room, and four contracts
    # is the most it can lose without dying.
    #
    # The stop is 10 points rather than 4 so that the ROOM is the cap being tested. At a
    # 4-point stop the account's five-ES contract ceiling binds first and this test would
    # pass whatever the room arithmetic did - which is the failure mode the ceiling fix
    # exposed here on 2026-09-14.
    acct = combine_account()
    assert acct.distance_to_mll == pytest.approx(2_000.0)
    assert acct.max_contracts_for("ES") == 5, "the ceiling must NOT be what binds below"
    d = sz.FixedRiskSizer().size(ctx(equity=1_000_000.0, stop_distance=10.0, prop_account=acct))
    assert d.contracts == 4 and d.binding is sz.Binding.PROP_FIRM
    assert "LIMIT_PROP_FIRM" in d.codes


def test_the_prop_firm_contract_ceiling_binds_any_sizer():
    d = sz.FixedRiskSizer().size(ctx(equity=100_000.0, stop_distance=1.0,
                                     prop_account=FakeAccount(100_000.0, 1)))
    assert d.contracts == 1 and d.binding is sz.Binding.PROP_FIRM


def test_a_prop_account_without_a_stop_refuses_rather_than_ignoring_the_mll():
    d = sz.SignalSizer().size(ctx(requested=3.0, prop_account=FakeAccount(2_000.0, 50)))
    assert not d.available and "SIZING_NO_STOP" in d.codes


def test_size_is_final_so_a_subclass_cannot_bypass_the_funnel():
    assert getattr(sz.Sizer.size, "__final__", False) is True


def test_limits_reject_negative_numbers():
    with pytest.raises(ValueError):
        sz.SizeLimits(venue_max_contracts=-1)
    with pytest.raises(ValueError):
        sz.SizeLimits(governor_max_risk=float("nan"))


# ======================================================================================
# KELLY
# ======================================================================================

def test_kelly_closed_forms():
    assert sz.kelly_binary(0.6, 1.0) == pytest.approx(0.2)
    assert sz.kelly_binary(0.5, 1.0) == pytest.approx(0.0)
    assert sz.kelly_binary(0.4, 1.0) < 0
    assert sz.kelly_fraction(0.2, 0.96) == pytest.approx(0.2 / 0.96)
    with pytest.raises(ValueError):
        sz.kelly_fraction(0.2, 0.0)


def test_kelly_known_answer_half_kelly():
    # 600 wins of +1R, 400 losses of -1R: mean 0.2, sample variance 960/999.
    trades = [1.0] * 600 + [-1.0] * 400
    est = sz.estimate_kelly(trades)
    assert est.admissible and est.n == 1000
    assert est.mean == pytest.approx(0.2)
    assert est.variance == pytest.approx(960.0 / 999.0)
    full = 0.2 * 999.0 / 960.0
    assert est.full == pytest.approx(full)
    # Half Kelly of $100k at $200 a contract: 0.5 x f* x 100,000 / 200 = 52.03 -> 52.
    d = sz.KellySizer(max_risk_fraction=0.25).size(
        ctx(equity=100_000.0, stop_distance=4.0, trades=trades))
    assert d.contracts == math.floor(0.5 * full * 100_000.0 / 200.0) == 52
    assert "KELLY" in d.codes and "KELLY_CAPPED" not in d.codes


def test_kelly_default_cap_is_two_percent_of_equity():
    trades = [1.0] * 600 + [-1.0] * 400
    d = sz.KellySizer().size(ctx(equity=100_000.0, stop_distance=4.0, trades=trades))
    assert d.contracts == 10            # 2% of $100k = $2,000 / $200
    assert "KELLY_CAPPED" in d.codes


def test_quarter_kelly_is_half_of_half():
    trades = [1.0] * 600 + [-1.0] * 400
    half = sz.KellySizer(fraction=0.5, max_risk_fraction=1.0).size(
        ctx(equity=100_000.0, stop_distance=4.0, trades=trades))
    quarter = sz.KellySizer(fraction=0.25, max_risk_fraction=1.0).size(
        ctx(equity=100_000.0, stop_distance=4.0, trades=trades))
    assert quarter.contracts == math.floor(0.25 * 0.2 * 999.0 / 960.0 * 100_000.0 / 200.0)
    assert quarter.contracts <= half.contracts // 2 + 1


def test_full_kelly_is_permitted_only_explicitly_and_is_flagged():
    trades = [1.0] * 600 + [-1.0] * 400
    d = sz.KellySizer(fraction=1.0, max_risk_fraction=1.0).size(
        ctx(equity=100_000.0, stop_distance=4.0, trades=trades))
    assert "KELLY_FRACTION_ABOVE_HALF" in d.codes
    with pytest.raises(ValueError):
        sz.KellySizer(fraction=1.5)


def _refusal(trades, **kw) -> sz.SizeDecision:
    d = sz.KellySizer(**kw).size(ctx(equity=100_000.0, stop_distance=4.0, trades=trades))
    assert not d.available and d.contracts == 0 and d.binding is None
    return d


def test_kelly_refuses_too_few_trades():
    d = _refusal([1.0] * 12 + [-1.0] * 8)
    assert "KELLY_TOO_FEW_TRADES" in d.codes


def test_kelly_minimum_trade_count_is_configurable():
    # Same 20 trades; lowering the floor moves the refusal to the next gate rather than
    # producing a size - 12/8 over 20 trades is nowhere near significant.
    d = _refusal([1.0] * 12 + [-1.0] * 8, min_trades=10)
    assert "KELLY_TOO_FEW_TRADES" not in d.codes
    assert "KELLY_EDGE_NOT_SIGNIFICANT" in d.codes


def test_kelly_refuses_a_negative_edge():
    d = _refusal([1.0] * 40 + [-1.0] * 60)
    assert "KELLY_NEGATIVE_EDGE" in d.codes


def test_kelly_refuses_an_edge_whose_interval_reaches_zero():
    # 55/45 over 100 trades: mean 0.1, se ~0.1. Not distinguishable from zero at 99%.
    d = _refusal([1.0] * 55 + [-1.0] * 45)
    assert "KELLY_EDGE_NOT_SIGNIFICANT" in d.codes
    # ...nor at 95%.
    assert "KELLY_EDGE_NOT_SIGNIFICANT" in _refusal([1.0] * 55 + [-1.0] * 45, confidence=0.95).codes


def test_kelly_refuses_a_degenerate_sample():
    assert "KELLY_DEGENERATE" in _refusal([1.0] * 50).codes


def test_kelly_refuses_non_finite_outcomes():
    assert "KELLY_NON_FINITE" in _refusal([1.0] * 49 + [float("nan")]).codes


def test_kelly_refuses_without_a_sample():
    d = sz.KellySizer().size(ctx(equity=100_000.0, stop_distance=4.0))
    assert not d.available and "KELLY_NO_TRADES" in d.codes


def test_kelly_never_sizes_pure_noise():
    """Forty zero-edge samples of 200 trades each. The 99% interval passes one zero-edge
    sample in two hundred by construction, so this is a deterministic pin on fixed seeds
    rather than a proof - the docstring on `estimate_kelly` says so. What it does prove is
    that nothing in the sizer turns 'not refused' into a size larger than the cap allows,
    and that the refusal path is the common one on noise."""
    sized = 0
    for seed in range(40):
        x = np.random.default_rng(seed).standard_normal(200)
        d = sz.KellySizer().size(ctx(equity=100_000.0, stop_distance=4.0, trades=list(x)))
        if d.available:
            sized += 1
            assert d.risk_dollars is not None and d.risk_dollars <= 0.02 * 100_000.0 + 1e-9
    assert sized == 0, f"{sized} of 40 zero-edge samples produced a size"


# ======================================================================================
# DRAWDOWN-AWARE AND CONFIDENCE-WEIGHTED
# ======================================================================================

def test_drawdown_aware_is_monotonically_non_increasing():
    sizer = sz.DrawdownAwareSizer(sz.FixedRiskSizer(risk_dollars=10_000.0))
    sizes = [sizer.size(ctx(stop_distance=4.0, drawdown=dd)).contracts
             for dd in np.linspace(0.0, 0.2, 41)]
    assert sizes[0] == 50                                  # $10,000 / $200 at the peak
    assert all(a >= b for a, b in itertools.pairwise(sizes))
    assert sizes[-1] == 0                                  # gone by the 10% stop, default
    assert sizer.size(ctx(stop_distance=4.0, drawdown=0.05)).contracts == 25


def test_drawdown_aware_never_scales_above_one():
    sizer = sz.DrawdownAwareSizer(sz.FixedRiskSizer(risk_dollars=10_000.0), start=0.02)
    assert sizer.factor(0.0) == 1.0 and sizer.factor(0.02) == 1.0
    assert sizer.size(ctx(stop_distance=4.0, drawdown=0.0)).contracts == 50


def test_drawdown_aware_needs_the_drawdown():
    d = sz.DrawdownAwareSizer(sz.FixedRiskSizer()).size(ctx(equity=100_000.0, stop_distance=4.0))
    assert not d.available and "SIZING_NO_DRAWDOWN" in d.codes


def test_drawdown_aware_propagates_the_base_refusal():
    d = sz.DrawdownAwareSizer(sz.FixedRiskSizer()).size(ctx(equity=100_000.0, drawdown=0.0))
    assert not d.available and "SIZING_NO_STOP" in d.codes


def test_drawdown_aware_rejects_a_nonsense_curve():
    with pytest.raises(ValueError):
        sz.DrawdownAwareSizer(sz.FixedRiskSizer(), start=0.1, stop=0.05)
    with pytest.raises(ValueError):
        sz.SizeContext(spec=ES, drawdown=-0.01)


def test_confidence_weighting_can_only_shrink():
    base = sz.FixedRiskSizer(risk_dollars=10_000.0)
    sizer = sz.ConfidenceWeightedSizer(base)
    full = base.size(ctx(stop_distance=4.0)).contracts
    assert full == 50
    sizes = [sizer.size(ctx(stop_distance=4.0, confidence=c)).contracts
             for c in np.linspace(0.0, 1.0, 21)]
    assert all(a <= b for a, b in itertools.pairwise(sizes))
    assert max(sizes) == full and sizes[-1] == full
    assert sizer.size(ctx(stop_distance=4.0, confidence=0.5)).contracts == 0
    assert sizer.size(ctx(stop_distance=4.0, confidence=0.75)).contracts == 25


def test_confidence_above_one_is_rejected_at_the_door():
    with pytest.raises(ValueError):
        sz.SizeContext(spec=ES, confidence=1.2)


def test_confidence_weighting_needs_the_confidence():
    d = sz.ConfidenceWeightedSizer(sz.FixedRiskSizer()).size(
        ctx(equity=100_000.0, stop_distance=4.0))
    assert not d.available and "SIZING_NO_CONFIDENCE" in d.codes


# ======================================================================================
# PROP FIRM
# ======================================================================================

@pytest.mark.parametrize("fraction", [0.25, 0.5, 1.0])
@pytest.mark.parametrize("rpc", [100.0, 250.0, 700.0])
def test_prop_firm_sizer_agrees_with_the_twin(fraction, rpc):
    acct = combine_account()
    d = sz.PropFirmSizer(fraction=fraction).size(
        ctx(stop_distance=rpc / ES.multiplier, prop_account=acct))
    assert d.available
    # `symbol` on both sides: the context is sized on the ES spec, so the twin has to be
    # asked for its ceiling in ES too or the two are comparing different units.
    assert d.contracts == tw.max_contracts(acct, rpc, fraction=fraction, symbol="ES")
    assert d.risk_dollars == pytest.approx(d.contracts * rpc)
    assert "PROP_FIRM_BUDGET" in d.codes


def test_prop_firm_sizes_off_the_room_not_the_balance():
    # An XFA three winning days in: $500 balance, MLL still at -$1,500, $2,000 of room.
    xfa = ts.TopstepAccount(profile=ts.express_funded(50_000),
                            stage=ts.TopstepStage.EXPRESS_FUNDED)
    xfa.settle_day(500.0)
    assert xfa.balance == 500.0 and xfa.distance_to_mll == pytest.approx(2_000.0)
    # Fixed-fraction-of-equity sizing sees $500 of equity and puts on nothing.
    off_equity = sz.FixedRiskSizer().size(ctx(equity=xfa.balance, stop_distance=2.0))
    assert off_equity.contracts == 0
    # The prop-firm sizer sees the room: 0.25 x $2,000 / $10 a MES contract = 50 wanted,
    # and the XFA's five-micro-equivalent scaling rung is what stops it at 5. Either way it
    # is trading, which sizing off a $500 balance never would be.
    off_room = sz.PropFirmSizer().size(ctx(spec=MES, stop_distance=2.0, prop_account=xfa))
    assert off_room.contracts == 5
    # ES on the same account is zero, and that is not a regression: XFA_SCALING_FALLBACK
    # permits a tenth of the allowance - five micro-equivalents, "so no mini at all" in its
    # own words - and one ES consumes ten of them. Before 2026-09-14 this sized 5 ES, which
    # is $250 a point against $2,000 of room.
    off_room_mini = sz.PropFirmSizer().size(ctx(stop_distance=2.0, prop_account=xfa))
    assert off_room_mini.contracts == 0 and off_room_mini.binding is sz.Binding.PROP_FIRM


def test_prop_firm_at_the_floor_sizes_zero():
    d = sz.PropFirmSizer().size(ctx(stop_distance=2.0, prop_account=FakeAccount(0.0, 50)))
    assert d.available and d.contracts == 0 and d.binding is sz.Binding.PROP_FIRM


def test_an_account_that_cannot_name_its_ceiling_in_contracts_is_refused():
    """An `MllAccount` missing `max_contracts_for` is unavailable, not silently uncapped.

    The tempting fallback is `contracts_allowed`, and that is precisely the defect: it is in
    the firm's own allowance unit, it is larger than the true ceiling for every non-micro,
    and a cap that is silently too large is worse than no answer.
    """
    class Legacy:
        distance_to_mll = 2_000.0
        contracts_allowed = 50

    d = sz.PropFirmSizer().size(ctx(stop_distance=2.0, prop_account=Legacy()))
    assert not d.available and "SIZING_ACCOUNT_PROTOCOL" in d.codes
    assert d.contracts == 0


def test_prop_firm_refusals():
    assert "SIZING_NO_PROP_ACCOUNT" in sz.PropFirmSizer().size(ctx(stop_distance=2.0)).codes
    assert "SIZING_NO_STOP" in sz.PropFirmSizer().size(
        ctx(prop_account=FakeAccount(2_000.0, 50))).codes
    with pytest.raises(ValueError):
        sz.PropFirmSizer(fraction=0.0)
    with pytest.raises(ValueError):
        sz.PropFirmSizer(fraction=1.5)


# ======================================================================================
# UNAVAILABLE MEANS UNAVAILABLE
# ======================================================================================

@pytest.mark.parametrize("sizer", [
    sz.FixedRiskSizer(), sz.VolatilityTargetSizer(), sz.ATRSizer(), sz.KellySizer(),
    sz.DrawdownAwareSizer(sz.FixedRiskSizer()), sz.ConfidenceWeightedSizer(sz.FixedRiskSizer()),
    sz.PropFirmSizer(), sz.SignalSizer(),
], ids=lambda s: s.name)
def test_an_empty_context_yields_an_unavailable_decision_not_a_number(sizer):
    d = sizer.size(ctx())
    assert not d.available
    assert d.contracts == 0 and d.binding is None and d.risk_dollars is None
    assert d.codes and all(c.startswith(("SIZING_", "KELLY_")) for c in d.codes)
    assert "UNAVAILABLE" in d.describe()


def test_context_rejects_non_positive_measurements():
    for bad in ({"price": 0.0}, {"stop_distance": -1.0}, {"volatility": float("inf")},
                {"atr": 0.0}, {"requested": -1.0}, {"equity": float("nan")}):
        with pytest.raises(ValueError):
            ctx(**bad)


# ======================================================================================
# PORTFOLIO
# ======================================================================================

def book() -> pf.Portfolio:
    return pf.Portfolio([
        pf.Exposure("trend", ES, 2.0, 5_000.0, risk_dollars=400.0),           # +500,000
        pf.Exposure("meanrev", NQ, -5.0, 18_000.0, risk_dollars=1_000.0),     # -1,800,000
        pf.Exposure("trend", NVDA, 100.0, 120.0, risk_dollars=200.0),         # +12,000
    ], equity=1_000_000.0)


def test_gross_and_net_exposure():
    b = book()
    assert b.gross_exposure() == pytest.approx(2_312_000.0)
    assert b.net_exposure() == pytest.approx(-1_288_000.0)
    assert b.leverage().value == pytest.approx(2.312)


def test_exposure_by_instrument_strategy_and_venue():
    b = book()
    inst = b.by_instrument()
    assert inst["ES"].net == pytest.approx(500_000.0)
    assert inst["NQ"].net == pytest.approx(-1_800_000.0) and inst["NQ"].short == pytest.approx(1_800_000.0)
    assert inst["NVDA"].gross == pytest.approx(12_000.0)
    strat = b.by_strategy()
    assert strat["trend"].net == pytest.approx(512_000.0) and strat["trend"].gross == pytest.approx(512_000.0)
    assert strat["meanrev"].net == pytest.approx(-1_800_000.0)
    venue = b.by_venue()
    assert venue["CME"].gross == pytest.approx(2_300_000.0)
    assert venue["CME"].net == pytest.approx(-1_300_000.0)
    assert venue["SMART"].gross == pytest.approx(12_000.0)


def test_leverage_is_unavailable_without_equity():
    b = pf.Portfolio(book().lines)
    m = b.leverage()
    assert not m.available and m.code == pf.NO_EQUITY


def test_total_risk_is_the_sum_of_stops_or_unavailable():
    assert book().total_risk().value == pytest.approx(1_600.0)
    b = pf.Portfolio([pf.Exposure("s", ES, 1.0, 5_000.0)])
    m = b.total_risk()
    assert not m.available and m.code == pf.NO_RISK


@pytest.mark.parametrize("rho,expected", [(1.0, 2_000.0), (0.0, math.sqrt(2.0) * 1_000.0),
                                          (-1.0, 0.0), (0.5, math.sqrt(3.0) * 1_000.0)])
def test_correlated_risk_known_answers(rho, expected):
    b = pf.Portfolio([pf.Exposure("a", ES, 1.0, 5_000.0, risk_dollars=1_000.0),
                      pf.Exposure("b", NQ, 1.0, 18_000.0, risk_dollars=1_000.0)])
    c = pf.CorrelationMatrix(("ES", "NQ"), ((1.0, rho), (rho, 1.0)))
    assert b.correlated_risk(c).value == pytest.approx(expected, abs=1e-9)


def test_a_hedge_in_perfectly_correlated_instruments_nets_to_zero():
    b = pf.Portfolio([pf.Exposure("a", ES, 1.0, 5_000.0, risk_dollars=1_000.0),
                      pf.Exposure("b", NQ, -1.0, 18_000.0, risk_dollars=1_000.0)])
    c = pf.CorrelationMatrix(("ES", "NQ"), ((1.0, 1.0), (1.0, 1.0)))
    assert b.correlated_risk(c).value == pytest.approx(0.0, abs=1e-9)


def test_two_strategies_in_one_instrument_net_before_correlation():
    b = pf.Portfolio([pf.Exposure("a", ES, 2.0, 5_000.0, risk_dollars=1_000.0),
                      pf.Exposure("b", ES, -1.0, 5_000.0, risk_dollars=400.0)])
    assert b.correlated_risk(pf.CorrelationMatrix.identity(["ES"])).value == pytest.approx(600.0)


def test_non_psd_correlation_is_refused():
    # 0.9 with A and B each, yet A and B at -0.9: impossible, and the determinant says so.
    c = pf.CorrelationMatrix(("ES", "NQ", "RTY"),
                             ((1.0, 0.9, 0.9), (0.9, 1.0, -0.9), (0.9, -0.9, 1.0)))
    assert not c.is_psd and c.problem().startswith(pf.CORRELATION_NOT_PSD)
    b = pf.Portfolio([pf.Exposure("a", ES, 1.0, 5_000.0, risk_dollars=100.0),
                      pf.Exposure("a", NQ, 1.0, 18_000.0, risk_dollars=100.0),
                      pf.Exposure("a", RTY, 1.0, 2_000.0, risk_dollars=100.0)])
    m = b.correlated_risk(c)
    assert not m.available and m.code == pf.CORRELATION_NOT_PSD
    breaches = b.check(pf.PortfolioLimits(max_correlated_risk=1_000_000.0), correlation=c)
    assert [x.code for x in breaches] == [pf.UNVERIFIABLE]
    assert pf.CORRELATION_NOT_PSD in breaches[0].detail


def test_a_matrix_missing_an_instrument_is_refused_not_padded():
    b = pf.Portfolio([pf.Exposure("a", ES, 1.0, 5_000.0, risk_dollars=100.0),
                      pf.Exposure("a", NQ, 1.0, 18_000.0, risk_dollars=100.0)])
    m = b.correlated_risk(pf.CorrelationMatrix.identity(["ES"]))
    assert not m.available and m.code == pf.CORRELATION_MISSING and "NQ" in m.reason
    # Extra symbols in the matrix are fine; only missing ones are a problem.
    assert b.correlated_risk(pf.CorrelationMatrix.identity(["ES", "NQ", "RTY"])).value == pytest.approx(
        math.sqrt(2.0) * 100.0)


def test_malformed_matrices():
    with pytest.raises(ValueError):
        pf.CorrelationMatrix(("ES", "NQ"), ((1.0, 0.0),))
    with pytest.raises(ValueError):
        pf.CorrelationMatrix(("ES", "ES"), ((1.0, 0.0), (0.0, 1.0)))
    asym = pf.CorrelationMatrix(("ES", "NQ"), ((1.0, 0.2), (0.5, 1.0)))
    assert asym.problem().startswith(pf.CORRELATION_MALFORMED)
    diag = pf.CorrelationMatrix(("ES", "NQ"), ((0.9, 0.2), (0.2, 1.0)))
    assert diag.problem().startswith(pf.CORRELATION_MALFORMED)
    big = pf.CorrelationMatrix(("ES", "NQ"), ((1.0, 1.2), (1.2, 1.0)))
    assert big.problem().startswith(pf.CORRELATION_MALFORMED)
    assert pf.CorrelationMatrix.identity(["ES", "NQ"]).problem() == ""


def test_no_matrix_means_no_number_unless_the_book_is_empty():
    b = pf.Portfolio([pf.Exposure("a", ES, 1.0, 5_000.0, risk_dollars=100.0)])
    m = b.correlated_risk(None)
    assert not m.available and m.code == pf.NO_CORRELATION
    assert pf.Portfolio([]).correlated_risk(None).value == 0.0


TIGHT = pf.PortfolioLimits(
    max_gross_exposure=1_000_000.0,
    max_net_exposure=500_000.0,
    max_leverage=2.0,
    max_instrument_exposure=400_000.0,
    max_strategy_exposure=400_000.0,
    max_venue_exposure=400_000.0,
    max_total_risk=1_000.0,
    max_correlated_risk=1_000.0,
)


def test_check_fires_every_reason_code():
    breaches = book().check(TIGHT, correlation=pf.CorrelationMatrix.identity(["ES", "NQ", "NVDA"]))
    codes = {x.code for x in breaches}
    # UNVERIFIABLE stands in for a code whose metric could not be computed, so the two are
    # mutually exclusive per limit; with a fully specified book every real code fires.
    assert codes == set(pf.BREACH_CODES) - {pf.UNVERIFIABLE}
    by_code = {}
    for x in breaches:
        by_code.setdefault(x.code, []).append(x)
    assert {x.key for x in by_code[pf.INSTRUMENT_EXPOSURE]} == {"ES", "NQ"}
    assert {x.key for x in by_code[pf.STRATEGY_EXPOSURE]} == {"trend", "meanrev"}
    assert {x.key for x in by_code[pf.VENUE_EXPOSURE]} == {"CME"}
    assert by_code[pf.LEVERAGE][0].value == pytest.approx(2.312)
    assert by_code[pf.CORRELATED_RISK][0].value == pytest.approx(math.sqrt(400.0**2 + 1_000.0**2 + 200.0**2))
    assert all(str(x).startswith(x.code) for x in breaches)


def test_unverifiable_replaces_the_code_it_could_not_check():
    # Same limits, no equity: leverage cannot be computed, and that is a breach in its own
    # right rather than a pass.
    breaches = pf.Portfolio(book().lines).check(
        TIGHT, correlation=pf.CorrelationMatrix.identity(["ES", "NQ", "NVDA"]))
    codes = {x.code for x in breaches}
    assert pf.LEVERAGE not in codes and pf.UNVERIFIABLE in codes
    unverifiable = [x for x in breaches if x.code == pf.UNVERIFIABLE]
    assert [x.key for x in unverifiable] == ["max_leverage"]
    assert pf.NO_EQUITY in unverifiable[0].detail


def test_a_clean_book_has_no_breaches_and_unconfigured_limits_are_silent():
    b = book()
    assert b.check(pf.PortfolioLimits()) == []
    generous = pf.PortfolioLimits(max_gross_exposure=5_000_000.0, max_leverage=5.0,
                                  max_total_risk=10_000.0)
    assert b.check(generous) == []


def test_a_configured_limit_that_cannot_be_checked_is_a_breach():
    b = pf.Portfolio([pf.Exposure("a", ES, 1.0, 5_000.0)])       # no risk on the line
    breaches = b.check(pf.PortfolioLimits(max_total_risk=1_000.0))
    assert len(breaches) == 1 and breaches[0].code == pf.UNVERIFIABLE
    assert pf.NO_RISK in breaches[0].detail and breaches[0].value is None


def test_portfolio_inputs_are_validated():
    with pytest.raises(ValueError):
        pf.Exposure("", ES, 1.0, 5_000.0)
    with pytest.raises(ValueError):
        pf.Exposure("a", ES, 1.0, 0.0)
    with pytest.raises(ValueError):
        pf.Exposure("a", ES, 1.0, 5_000.0, risk_dollars=-1.0)
    with pytest.raises(ValueError):
        pf.PortfolioLimits(max_gross_exposure=-1.0)
    with pytest.raises(ValueError):
        pf.Portfolio([], equity=float("nan"))
