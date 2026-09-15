"""The canonical data layer, attacked.

WHAT THIS FILE IS FOR
---------------------
`docs/DATA_FLOW_FORENSICS.md` mapped a data path whose every safety property was a filter
sitting downstream of an assumption nobody had written down. The layer under test replaces
those with declarations, and a declaration is only worth anything if the thing that checks it
cannot be talked around.

So this file is adversarial by construction. Section by section it tries to get a dataset
into research that should not be there: with no declared representation, with an adjusted
price series as the execution source, with two contracts inside one session, with a timestamp
that lies about its timezone, with a roll adjusted twice, with a provider's column names
leaking past the adapter. Every one of those must be refused, and the refusal must say why.

Every synthetic frame below is built bar by bar so the arithmetic is checkable by hand. The
figures quoted against the REAL store were measured, and the tests that assert them are
marked so they can be told apart from the hand-computed ones.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_brain.data import adapters as AD
from quant_brain.data import contracts as C
from quant_brain.data import cross_source as X
from quant_brain.data import loader as L
from quant_brain.data import quality as Q
from quant_brain.data import rolls as R
from quant_brain.data import schema as S
from quant_brain.data.manifest import (
    DatasetManifest,
    ManifestError,
    QualitySummary,
    RollSpec,
    hash_file,
)

REPO = Path(__file__).resolve().parents[1]
FUTURES = REPO / "data" / "futures"
TZ = "America/New_York"
MONDAY = dt.date(2026, 1, 5)


# ======================================================================================
# FIXTURES - hand-built, every value chosen
# ======================================================================================

def bars(closes, *, instrument="ES", contract="ESH6", start="2026-01-05 14:30",
         freq="1min", tz="UTC", highs=None, lows=None, volume=None,
         session=None, interval="1min"):
    """A canonical frame from a list of closes. Highs/lows default to the closes."""
    c = np.asarray(closes, dtype=float)
    n = len(c)
    ts = pd.date_range(pd.Timestamp(start, tz=tz), periods=n, freq=freq)
    csym = contract if isinstance(contract, str) else list(contract)
    return S.build_frame(
        instrument=instrument, contract_symbol=csym,
        contract_family=instrument, timestamp=ts,
        session_date=(session if session is not None
                      else pd.Series(ts).dt.tz_convert(TZ).dt.date),
        bar_interval=interval,
        open_=c, high=c if highs is None else highs, low=c if lows is None else lows,
        close=c, volume=np.ones(n) if volume is None else volume)


def a_manifest(**kw) -> DatasetManifest:
    base = dict(
        dataset_id="probe", provider="test", instrument="ES", contract_family="ES",
        data_form=S.DataForm.CONTINUOUS_UNADJUSTED,
        roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                      adjustment=S.AdjustmentMethod.NONE, days_before_expiry=8,
                      reconstructible=True),
        bar_interval="1min", timezone="UTC", session_timezone=TZ,
        coverage_start="2026-01-05T14:30:00+00:00",
        coverage_end="2026-01-05T14:40:00+00:00", bars=10, sessions=1)
    base.update(kw)
    return DatasetManifest(**base)


def a_dataset(frame=None, **kw) -> L.ResearchDataset:
    f = bars([5000.0, 5001.0, 5002.0]) if frame is None else frame
    man = a_manifest(**kw)
    rep = Q.check(f, dataset_id=man.dataset_id, session_timezone=man.session_timezone)
    return L.ResearchDataset(frame=f, manifest=man.with_quality(
        QualitySummary(status=rep.status.value, report_hash=rep.report_hash)), report=rep)


needs_store = pytest.mark.skipif(
    not (FUTURES / "ES.parquet").exists(),
    reason="the real futures store is not present on this machine")


# ======================================================================================
# 2 + 3. THE SCHEMA, AND THE REFUSAL TO INFER
# ======================================================================================

def test_the_canonical_schema_names_every_field_the_brief_requires():
    """The column contract, asserted so it cannot shrink by accident."""
    required = set(S.REQUIRED_COLUMNS)
    assert required == {
        "instrument", "contract_symbol", "contract_family", "timestamp",
        "timestamp_timezone", "session_date", "bar_interval",
        "open", "high", "low", "close", "volume"}
    assert set(S.OPTIONAL_COLUMNS) == {"open_interest", "bid", "ask", "bid_size",
                                       "ask_size"}


def test_instrument_and_contract_are_separate_fields():
    """The distinction the whole layer exists to hold. `ES` is not `ESU5`.

    The instrument owns the multiplier and the tick; the contract owns an expiry and a price
    that differs from the instrument's by carry. Collapsing them is how a +0.85% roll gap
    becomes a return.
    """
    f = bars([5000.0, 5001.0], contract="ESU5")
    assert set(f["instrument"]) == {"ES"}
    assert set(f["contract_symbol"].astype(str)) == {"ESU5"}
    assert C.family_of("ESU5") == "ES"
    assert C.parse("ESU5").canonical() == "ESU25"


def test_a_frame_missing_a_required_column_is_refused():
    f = bars([5000.0, 5001.0]).drop(columns=["contract_symbol"])
    with pytest.raises(S.SchemaError, match="missing"):
        S.validate_frame(f)


def test_a_timezone_naive_timestamp_is_refused():
    """A naive timestamp is an unstated assumption about the venue's clock, and FINDING 1
    in the forensics is a roll boundary that moved underneath exactly that assumption."""
    f = bars([5000.0, 5001.0])
    f["timestamp"] = f["timestamp"].dt.tz_localize(None)
    with pytest.raises(S.SchemaError, match="timezone-NAIVE"):
        S.validate_frame(f)


def test_a_frame_stored_in_a_venue_clock_is_refused():
    """Canonical storage is UTC. One frame must not be able to carry two clocks."""
    f = bars([5000.0, 5001.0])
    f["timestamp"] = f["timestamp"].dt.tz_convert(TZ)
    with pytest.raises(S.SchemaError, match="not UTC"):
        S.validate_frame(f)


def test_a_frame_whose_declaration_disagrees_with_its_dtype_is_refused():
    """The shape that survives review: it SAYS one timezone and STORES another."""
    f = bars([5000.0, 5001.0])
    f["timestamp_timezone"] = "America/New_York"
    with pytest.raises(S.SchemaError, match="declaration and the dtype must agree"):
        S.validate_frame(f)


def test_two_instruments_in_one_frame_are_refused():
    f = pd.concat([bars([5000.0], instrument="ES", contract="ESH6"),
                   bars([20000.0], instrument="NQ", contract="NQH6")], ignore_index=True)
    with pytest.raises(S.SchemaError, match="distinct values of `instrument`"):
        S.validate_frame(f)


def test_the_frame_fingerprint_moves_when_a_bar_moves_and_not_otherwise():
    f = bars([5000.0, 5001.0, 5002.0])
    same = f.copy()
    assert S.frame_fingerprint(f) == S.frame_fingerprint(same)
    reordered = same[list(reversed(list(same.columns)))]
    assert S.frame_fingerprint(f) == S.frame_fingerprint(reordered), \
        "column order is not content"
    moved = f.copy()
    moved.loc[1, "close"] = 5001.25
    assert S.frame_fingerprint(f) != S.frame_fingerprint(moved)


# ======================================================================================
# 4. RAW CONTRACTS ARE FIRST CLASS
# ======================================================================================

def test_contract_symbols_parse_or_are_refused_never_guessed():
    assert C.parse("ESU5").month == 9 and C.parse("ESU5").year == 2025
    assert C.parse("MESZ5").root == "MES"
    # the same expiry, and NOT the same object: `symbol` preserves the provider's
    # spelling, because rewriting a vendor identifier is how a dataset stops matching the
    # file it came from. `canonical()` is the unambiguous form.
    assert C.parse("ESU25").canonical() == C.parse("ESU5").canonical() == "ESU25"
    assert C.parse("ESU25").symbol != C.parse("ESU5").symbol
    for bad in ("SPY", "", "ES", "ESA5", "ES5"):
        with pytest.raises(C.ContractSymbolError):
            C.parse(bad)


def test_the_one_digit_year_window_is_declared_and_bounded():
    """`ESU5` is September 2025, 2035, 2015 and 1995. The window picks one, and says so."""
    assert C.YEAR_ANCHOR == 2026
    assert C.resolve_year("5", anchor=2026) == 2025
    assert C.resolve_year("9", anchor=2026) == 2029
    assert C.resolve_year("2", anchor=2026) == 2022
    # the window is ten consecutive years, so exactly one candidate always exists
    got = {C.resolve_year(str(d), anchor=2026) for d in range(10)}
    assert len(got) == 10 and min(got) == 2022 and max(got) == 2031


def test_a_chain_is_ordered_by_expiry_not_by_string():
    """String sort puts ESU5 before ESH6. Expiry sort does not."""
    syms = ["ESZ5", "ESU5", "ESU6", "ESH6", "ESM6"]
    assert [c.symbol for c in C.chain_order(syms)] == [
        "ESU5", "ESZ5", "ESH6", "ESM6", "ESU6"]
    assert sorted(syms) != [c.symbol for c in C.chain_order(syms)]


def test_a_chain_that_skips_a_quarter_is_reported_not_silently_accepted():
    ok, why = C.is_contiguous_chain(["ESU5", "ESZ5", "ESH6"])
    assert ok and "contiguous" in why
    bad, why = C.is_contiguous_chain(["ESU5", "ESH6", "ESM6"])
    assert not bad and "6" in why


@needs_store
def test_a_single_contract_can_be_extracted_as_a_first_class_raw_dataset():
    """Raw contracts are first-class: the store holds them, so they can be used as RAW -
    the one form with no roll in it anywhere and nothing to argue about."""
    frame, man = AD.ibkr_futures_single_contract(
        FUTURES / "ES.parquet", instrument="ES", contract_symbol="ESZ5")
    assert man.data_form is S.DataForm.RAW
    assert man.roll.method is S.RollMethod.NONE
    assert set(frame["contract_symbol"].astype(str)) == {"ESZ5"}
    assert R.detect_rolls(frame) == []
    assert man.execution_valid is True


# ======================================================================================
# 5 + 9. ROLLOVER, ON SYNTHETIC CONTRACTS WITH KNOWN ANSWERS
# ======================================================================================

def two_contracts(a: float = 5000.0, b: float = 5100.0, n: int = 4) -> pd.DataFrame:
    """Contract A flat at `a`, contract B flat at `b`. A clean, hand-checkable +100 gap."""
    return bars([a] * n + [b] * n, contract=["ESH6"] * n + ["ESM6"] * n,
                highs=[a + 1] * n + [b + 1] * n, lows=[a - 1] * n + [b - 1] * n)


def test_the_roll_is_detected_where_the_contract_changes():
    ev = R.detect_rolls(two_contracts())
    assert len(ev) == 1
    e = ev[0]
    assert (e.from_contract, e.to_contract) == ("ESH6", "ESM6")
    assert e.gap_points == pytest.approx(100.0)
    assert e.gap_pct == pytest.approx(2.0)
    assert e.index == 4


@pytest.mark.parametrize(
    ("direction", "method", "first", "last"),
    [("back", S.AdjustmentMethod.DIFFERENCE, 5100.0, 5100.0),
     ("back", S.AdjustmentMethod.RATIO, 5100.0, 5100.0),
     ("forward", S.AdjustmentMethod.DIFFERENCE, 5000.0, 5000.0),
     ("forward", S.AdjustmentMethod.RATIO, 5000.0, 5000.0)])
def test_each_adjustment_produces_exactly_the_expected_series(direction, method,
                                                              first, last):
    """A=5000, B=5100, gap +100. Every one of the four answers is written out.

        back    the LAST contract is the real one, so A is lifted to B's level
                difference: 5000 + 100 = 5100
                ratio:      5000 * (5100/5000) = 5100
        forward the FIRST contract is real, so B is pushed down to A's level
                difference: 5100 - 100 = 5000
                ratio:      5100 / (5100/5000) = 5000
    """
    res = R.adjust(two_contracts(), method=method, direction=direction, tick_size=0.25)
    c = res.frame["close"].to_numpy()
    assert c[0] == pytest.approx(first)
    assert c[-1] == pytest.approx(last)
    gap_free, worst = R.gap_free(res.frame)
    assert gap_free and worst == pytest.approx(0.0)


def test_difference_preserves_point_moves_and_ratio_does_not():
    """The property that decides whether a points-based stop survives the adjustment."""
    src = two_contracts()
    raw_hl = (src["high"] - src["low"]).to_numpy()
    d = R.adjust(src, method=S.AdjustmentMethod.DIFFERENCE, direction="back").frame
    r = R.adjust(src, method=S.AdjustmentMethod.RATIO, direction="back").frame
    assert np.allclose((d["high"] - d["low"]).to_numpy(), raw_hl), \
        "a difference adjustment must not change a bar's range"
    assert not np.allclose((r["high"] - r["low"]).to_numpy(), raw_hl), \
        "a ratio adjustment scales the range; a points-based stop is a different stop"


def test_ratio_preserves_returns_and_difference_does_not():
    """The mirror property. Neither adjustment preserves both; that is why neither is
    execution-valid."""
    src = two_contracts()
    def rets(f):
        c = f["close"].to_numpy(float)
        return np.diff(c) / c[:-1]
    within_raw = rets(src)[:3]           # inside contract A, before the roll
    r = rets(R.adjust(src, method=S.AdjustmentMethod.RATIO, direction="back").frame)[:3]
    assert np.allclose(r, within_raw), "a ratio adjustment must preserve returns exactly"
    # A is flat here so all three are zero; use a moving contract to separate them
    moving = bars([5000.0, 5010.0, 5020.0, 5100.0, 5110.0, 5120.0],
                  contract=["ESH6"] * 3 + ["ESM6"] * 3)
    base = rets(moving)[:2]
    dd = rets(R.adjust(moving, method=S.AdjustmentMethod.DIFFERENCE,
                       direction="back").frame)[:2]
    rr = rets(R.adjust(moving, method=S.AdjustmentMethod.RATIO,
                       direction="back").frame)[:2]
    assert np.allclose(rr, base)
    assert not np.allclose(dd, base)


def test_a_ratio_adjustment_leaves_the_tick_grid_and_a_difference_does_not():
    """A price off the tick grid is a price no order could rest on."""
    src = two_contracts()
    d = R.adjust(src, method=S.AdjustmentMethod.DIFFERENCE, direction="back",
                 tick_size=0.25)
    r = R.adjust(src, method=S.AdjustmentMethod.RATIO, direction="back", tick_size=0.25)
    assert d.max_tick_grid_error == pytest.approx(0.0)
    assert r.max_tick_grid_error > 0.0


def test_double_adjustment_is_refused_at_the_type_level():
    """The attack: adjust an already-adjusted series.

    Re-running `adjust` on adjusted bars would measure gaps of zero and change nothing,
    so the damage only appears when a STORED offset table is applied twice - and by then it
    is invisible. The guard is therefore on the DECLARED source form, which the second
    caller has to lie about.
    """
    once = R.adjust(two_contracts(), method=S.AdjustmentMethod.DIFFERENCE,
                    direction="back")
    with pytest.raises(R.RollError, match="DOUBLE ADJUSTED"):
        R.adjust(once.frame, method=S.AdjustmentMethod.DIFFERENCE, direction="back",
                 source_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED)


def test_an_unknown_adjustment_cannot_be_applied():
    with pytest.raises(R.RollError, match="cannot be APPLIED"):
        R.adjust(two_contracts(), method=S.AdjustmentMethod.UNKNOWN, direction="back")


def test_interleaved_contracts_are_refused_rather_than_adjusted():
    """A contract that appears, disappears and returns is not a chain, and applying one
    contract two different offsets is not an adjustment."""
    f = bars([5000.0, 5100.0, 5000.0, 5100.0],
             contract=["ESH6", "ESM6", "ESH6", "ESM6"])
    with pytest.raises(R.RollError, match="interleaved"):
        R.adjust(f, method=S.AdjustmentMethod.DIFFERENCE, direction="back")


def test_a_strategy_computation_changes_across_the_roll_when_the_adjustment_changes():
    """The point of section 6, on a fixture: same rule, four series, different stop.

    A one-ATR stop on the FIRST session of the series. The unadjusted and difference-adjusted
    answers agree because a difference adjustment does not touch a bar's range; the
    ratio-adjusted answer does not, and the difference is real money.
    """
    src = bars([5000.0, 5004.0, 5002.0, 5100.0, 5104.0, 5102.0],
               contract=["ESH6"] * 3 + ["ESM6"] * 3,
               highs=[5002.0, 5006.0, 5004.0, 5102.0, 5106.0, 5104.0],
               lows=[4998.0, 5002.0, 5000.0, 5098.0, 5102.0, 5100.0])

    def first_bar_range(f):
        return float(f["high"].iloc[0] - f["low"].iloc[0])

    raw = first_bar_range(src)
    d = first_bar_range(R.adjust(src, method=S.AdjustmentMethod.DIFFERENCE,
                                 direction="back").frame)
    r = first_bar_range(R.adjust(src, method=S.AdjustmentMethod.RATIO,
                                 direction="back").frame)
    assert d == pytest.approx(raw)
    assert r == pytest.approx(raw * (5100.0 / 5002.0), rel=1e-9)
    assert r != pytest.approx(raw)


# ======================================================================================
# 7. FEATURE DATA vs EXECUTION DATA
# ======================================================================================

def test_an_adjusted_series_is_refused_as_the_execution_source():
    """The central rule. A back-adjusted price was never quoted, so a fill at one is a fill
    at a number no venue printed."""
    adj = a_dataset(data_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED,
                    roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                                  adjustment=S.AdjustmentMethod.RATIO,
                                  days_before_expiry=8, reconstructible=True))
    with pytest.raises(L.LoaderError, match="never quoted by any venue"):
        L.ResearchInputs(features=adj, execution=adj)


def test_an_unknown_representation_is_refused_as_the_execution_source():
    other = a_dataset(data_form=S.DataForm.OTHER,
                      data_form_description="a vendor series of unstated construction",
                      roll=RollSpec(method=S.RollMethod.UNKNOWN,
                                    adjustment=S.AdjustmentMethod.UNKNOWN,
                                    reconstructible=False,
                                    non_reconstructible_reason="the vendor did not say"))
    assert other.manifest.execution_valid is False
    with pytest.raises(L.LoaderError):
        L.ResearchInputs(features=other, execution=other)


def test_features_and_execution_may_differ_and_the_report_says_so():
    exec_ds = a_dataset()
    feat_ds = a_dataset(dataset_id="probe-backadj",
                        data_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED,
                        roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                                      adjustment=S.AdjustmentMethod.DIFFERENCE,
                                      days_before_expiry=8, reconstructible=True))
    inputs = L.ResearchInputs(features=feat_ds, execution=exec_ds)
    text = inputs.describe()
    assert inputs.identical is False
    assert "FEATURE DATA and EXECUTION DATA DIFFER" in text
    assert "CONTINUOUS_BACK_ADJUSTED" in text and "CONTINUOUS_UNADJUSTED" in text
    prov = inputs.provenance()
    assert prov["features_identical_to_execution"] is False
    assert prov["feature_data"]["manifest_id"] != prov["execution_data"]["manifest_id"]


def test_the_ordinary_case_states_that_one_series_does_both_jobs():
    inputs = L.same_for_both(a_dataset())
    assert inputs.identical is True
    assert "SAME series" in inputs.describe()


def test_two_instruments_cannot_be_paired_by_accident():
    a = a_dataset()
    b = a_dataset(instrument="NQ", contract_family="NQ")
    with pytest.raises(L.LoaderError, match="not something this loader will"):
        L.ResearchInputs(features=a, execution=b)


# ======================================================================================
# 3 + 13. NO SILENT FALLBACKS
# ======================================================================================

def test_a_manifest_without_a_declared_data_form_cannot_be_built():
    with pytest.raises(ManifestError, match="must be a DataForm"):
        a_manifest(data_form="continuous")


def test_other_requires_a_description():
    with pytest.raises(ManifestError, match="requires `data_form_description`"):
        a_manifest(data_form=S.DataForm.OTHER,
                   roll=RollSpec(method=S.RollMethod.UNKNOWN,
                                 adjustment=S.AdjustmentMethod.UNKNOWN,
                                 reconstructible=False, non_reconstructible_reason="x"))


def test_a_continuous_series_cannot_claim_it_has_no_roll():
    with pytest.raises(ManifestError, match="is a spliced series, so it HAS a roll"):
        a_manifest(roll=RollSpec.none())


def test_a_raw_series_cannot_carry_a_roll():
    with pytest.raises(ManifestError, match="is one contract and cannot have roll"):
        a_manifest(data_form=S.DataForm.RAW)


def test_the_form_and_the_adjustment_must_agree_in_both_directions():
    with pytest.raises(ManifestError, match="One of the two is wrong"):
        a_manifest(data_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED)
    with pytest.raises(ManifestError, match="UNadjusted form but the roll declares"):
        a_manifest(roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                                 adjustment=S.AdjustmentMethod.RATIO,
                                 days_before_expiry=8, reconstructible=True))


def test_a_session_timezone_is_required():
    with pytest.raises(ManifestError, match="`session_timezone` is required"):
        a_manifest(session_timezone="")


def test_a_non_reconstructible_roll_must_say_why():
    with pytest.raises(ManifestError, match="must say why"):
        RollSpec(method=S.RollMethod.PROVIDER_DEFINED,
                 adjustment=S.AdjustmentMethod.UNKNOWN, reconstructible=False)


def test_a_roll_method_that_cannot_be_rebuilt_cannot_claim_it_can():
    with pytest.raises(ManifestError, match="cannot be reconstructible"):
        RollSpec(method=S.RollMethod.PROVIDER_DEFINED,
                 adjustment=S.AdjustmentMethod.UNKNOWN, reconstructible=True)


def test_a_calendar_roll_without_its_parameter_is_not_a_rule():
    with pytest.raises(ManifestError, match="needs `days_before_expiry`"):
        RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                 adjustment=S.AdjustmentMethod.NONE, reconstructible=True)


def test_an_unknown_adapter_is_refused_rather_than_guessed_at(tmp_path):
    with pytest.raises(L.LoaderError, match="unknown adapter"):
        L.load("mystery_provider", tmp_path / "x.parquet")


# ======================================================================================
# 12. PROVENANCE - TWO REPRESENTATIONS MUST NEVER LOOK ALIKE
# ======================================================================================

def test_the_same_bytes_read_two_ways_have_different_manifest_ids():
    """The single most important provenance property in the layer."""
    unadj = a_manifest()
    adj = a_manifest(data_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED,
                     roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                                   adjustment=S.AdjustmentMethod.RATIO,
                                   days_before_expiry=8, reconstructible=True))
    assert unadj.manifest_id != adj.manifest_id
    assert unadj.execution_valid and not adj.execution_valid


def test_changing_the_roll_rule_changes_the_manifest_id():
    """`ROLL_DAYS = 8` versus `5` used to be invisible downstream. Now it is not."""
    eight = a_manifest()
    five = a_manifest(roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                                    adjustment=S.AdjustmentMethod.NONE,
                                    days_before_expiry=5, reconstructible=True))
    assert eight.manifest_id != five.manifest_id


def test_the_manifest_id_ignores_when_it_was_built_and_what_the_gate_said():
    """Re-running the gate is not a new dataset. Re-reading it as adjusted is."""
    a = a_manifest(canonicalized_at="2026-01-01T00:00:00+00:00")
    b = a_manifest(canonicalized_at="2026-06-01T00:00:00+00:00")
    assert a.manifest_id == b.manifest_id
    assert a.with_quality(QualitySummary(status="WARN")).manifest_id == a.manifest_id


def test_a_manifest_round_trips_through_json(tmp_path):
    m = a_manifest()
    p = m.write(tmp_path / "m.json")
    back = DatasetManifest.read(p)
    assert back.manifest_id == m.manifest_id
    assert back.data_form is m.data_form
    assert back.roll.days_before_expiry == 8


def test_the_source_hash_is_the_bytes(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello")
    h1 = hash_file(p)
    p.write_bytes(b"hello!")
    assert hash_file(p) != h1


# ======================================================================================
# 8. TIME AND SESSION FORENSICS
# ======================================================================================

def test_the_spring_dst_transition_is_handled_without_a_fixed_offset():
    """2026-03-08: America/New_York goes UTC-5 to UTC-4. 09:30 ET is 14:30 UTC then 13:30."""
    before = pd.Timestamp("2026-03-06 14:30", tz="UTC").tz_convert(TZ)
    after = pd.Timestamp("2026-03-10 13:30", tz="UTC").tz_convert(TZ)
    # Compared as timedeltas, not as their repr: the string form of a negative offset is a
    # pandas/datetime detail and pinning it would make this a test of formatting.
    assert before.strftime("%H:%M") == after.strftime("%H:%M") == "09:30"
    assert before.utcoffset() == dt.timedelta(hours=-5)      # EST
    assert after.utcoffset() == dt.timedelta(hours=-4)       # EDT
    # the SAME wall clock is a DIFFERENT UTC instant on the two sides
    assert (after - before) != dt.timedelta(days=4)


def test_the_fall_dst_transition_is_handled_without_a_fixed_offset():
    """2026-11-01: UTC-4 back to UTC-5."""
    before = pd.Timestamp("2026-10-30 13:30", tz="UTC").tz_convert(TZ)
    after = pd.Timestamp("2026-11-03 14:30", tz="UTC").tz_convert(TZ)
    assert before.strftime("%H:%M") == after.strftime("%H:%M") == "09:30"
    assert before.utcoffset() != after.utcoffset()


def test_the_gate_reports_how_many_utc_offsets_a_dataset_spans():
    spring = pd.date_range("2026-03-06 14:30", periods=3, freq="1min", tz="UTC")
    autumn = pd.date_range("2026-03-10 13:30", periods=3, freq="1min", tz="UTC")
    ts = spring.append(autumn)
    f = S.build_frame(instrument="ES", contract_symbol="ESH6", contract_family="ES",
                      timestamp=ts,
                      session_date=pd.Series(ts).dt.tz_convert(TZ).dt.date,
                      bar_interval="1min", open_=[1.0] * 6, high=[1.0] * 6,
                      low=[1.0] * 6, close=[1.0] * 6, volume=[1.0] * 6)
    rep = Q.check(f, dataset_id="dst", session_timezone=TZ)
    assert rep.stats["dst_transitions_spanned"] == 1
    assert "19:00:00" in rep.stats["utc_offsets_seen"]
    assert "20:00:00" in rep.stats["utc_offsets_seen"]


def test_a_session_that_straddles_a_dst_change_is_flagged():
    """The CME weekly session legitimately spans the Sunday change; it is a WARN, not a
    FAIL, and the WARN has to say why research may continue."""
    ts = pd.DatetimeIndex([pd.Timestamp("2026-03-08 06:30", tz="UTC"),
                           pd.Timestamp("2026-03-08 07:30", tz="UTC")])
    f = S.build_frame(instrument="ES", contract_symbol="ESH6", contract_family="ES",
                      timestamp=ts, session_date=[dt.date(2026, 3, 8)] * 2,
                      bar_interval="60min", open_=[1.0, 1.0], high=[1.0, 1.0],
                      low=[1.0, 1.0], close=[1.0, 1.0], volume=[1.0, 1.0])
    rep = Q.check(f, dataset_id="straddle", session_timezone=TZ)
    finding = [x for x in rep.findings if x.check == "dst_within_session"]
    assert finding and finding[0].level is Q.Level.WARN
    assert finding[0].why_allowed


@pytest.mark.parametrize("boundary", ["2025-12-31 20:00", "2026-01-31 20:00",
                                      "2026-03-31 20:00"])
def test_year_month_and_quarter_boundaries_do_not_break_session_assignment(boundary):
    ts = pd.date_range(pd.Timestamp(boundary, tz="UTC"), periods=4, freq="1min")
    f = S.build_frame(instrument="ES", contract_symbol="ESH6", contract_family="ES",
                      timestamp=ts, session_date=pd.Series(ts).dt.tz_convert(TZ).dt.date,
                      bar_interval="1min", open_=[1.0] * 4, high=[1.0] * 4,
                      low=[1.0] * 4, close=[1.0] * 4, volume=[1.0] * 4)
    S.validate_frame(f)
    assert len(set(f["session_date"])) == 1
    rep = Q.check(f, dataset_id="boundary", session_timezone=TZ)
    assert not rep.failed


def test_an_unusable_session_timezone_is_a_fail_not_a_fallback():
    f = bars([5000.0, 5001.0])
    rep = Q.check(f, dataset_id="badtz", session_timezone="Mars/Olympus_Mons")
    assert rep.failed
    assert any(x.check == "session_timezone" for x in rep.of(Q.Level.FAIL))


# ======================================================================================
# 11. THE QUALITY GATE
# ======================================================================================

def test_a_clean_dataset_passes():
    rep = Q.check(bars([5000.0, 5001.0, 5002.0]), dataset_id="clean", session_timezone=TZ)
    assert rep.status is Q.Level.PASS
    assert rep.findings == []


def test_duplicate_bars_fail():
    f = pd.concat([bars([5000.0, 5001.0])] * 2, ignore_index=True).sort_values("timestamp")
    f = f.reset_index(drop=True)
    rep = Q.check(f, dataset_id="dup", session_timezone=TZ)
    assert rep.failed and any(x.check == "duplicates" for x in rep.of(Q.Level.FAIL))


def test_out_of_order_bars_fail():
    f = bars([5000.0, 5001.0, 5002.0])
    f = f.iloc[[0, 2, 1]].reset_index(drop=True)
    rep = Q.check(f, dataset_id="order", session_timezone=TZ)
    assert rep.failed and any(x.check == "ordering" for x in rep.of(Q.Level.FAIL))


def test_impossible_ohlc_fails():
    """The gap `futures_cme.dataquality` has pinned as a strict xfail: nothing on the
    futures path checks bar structure at all."""
    f = bars([5000.0, 5001.0], highs=[4999.0, 5001.0], lows=[5001.0, 5000.0])
    rep = Q.check(f, dataset_id="ohlc", session_timezone=TZ)
    assert rep.failed
    assert any(x.check == "ohlc_validity" for x in rep.of(Q.Level.FAIL))


def test_a_close_outside_its_own_range_fails():
    f = bars([5000.0, 5001.0], highs=[5000.0, 5000.5], lows=[4999.0, 5000.0])
    rep = Q.check(f, dataset_id="contain", session_timezone=TZ)
    assert any(x.check == "ohlc_containment" for x in rep.of(Q.Level.FAIL))


def test_a_zero_or_negative_price_fails():
    rep = Q.check(bars([5000.0, 0.0]), dataset_id="zero", session_timezone=TZ)
    assert any(x.check == "non_positive_price" for x in rep.of(Q.Level.FAIL))


def test_negative_volume_fails():
    rep = Q.check(bars([5000.0, 5001.0], volume=[1.0, -5.0]), dataset_id="v",
                  session_timezone=TZ)
    assert any(x.check == "volume_sign" for x in rep.of(Q.Level.FAIL))


def test_a_mixed_resolution_frame_fails():
    ts = pd.DatetimeIndex([pd.Timestamp("2026-01-05 14:30", tz="UTC"),
                           pd.Timestamp("2026-01-05 14:31", tz="UTC"),
                           pd.Timestamp("2026-01-05 14:31:30", tz="UTC")])
    f = S.build_frame(instrument="ES", contract_symbol="ESH6", contract_family="ES",
                      timestamp=ts, session_date=[MONDAY] * 3, bar_interval="1min",
                      open_=[1.0] * 3, high=[1.0] * 3, low=[1.0] * 3, close=[1.0] * 3,
                      volume=[1.0] * 3)
    rep = Q.check(f, dataset_id="mixed", session_timezone=TZ)
    assert any(x.check == "timestamp_grid" for x in rep.of(Q.Level.FAIL))


def test_a_warn_must_state_why_research_is_still_allowed():
    """A warning with no argument is a finding somebody decided to ignore."""
    rep = Q.QualityReport(dataset_id="x")
    with pytest.raises(ValueError, match="must state why"):
        rep.add("something", Q.Level.WARN, "a thing happened")
    rep.add("something", Q.Level.WARN, "a thing happened", why_allowed="because")
    assert rep.findings[0].why_allowed == "because"


def test_every_warn_the_gate_can_emit_carries_a_reason():
    """Enforced on the real store rather than on a fixture, because that is where the
    warnings actually come from."""
    f = bars([5000.0] * 80 + [5001.0], contract=["ESH6"] * 40 + ["ESM6"] * 41)
    rep = Q.check(f, dataset_id="warns", session_timezone=TZ)
    for finding in rep.of(Q.Level.WARN):
        assert finding.why_allowed, f"{finding.check} warns without saying why"


def test_the_gate_is_deterministic():
    f = bars([5000.0, 5001.0, 5002.0])
    a = Q.check(f, dataset_id="d", session_timezone=TZ)
    b = Q.check(f.copy(), dataset_id="d", session_timezone=TZ)
    assert a.report_hash == b.report_hash


def test_a_fail_blocks_entry_to_research():
    f = bars([5000.0, 0.0])
    with pytest.raises(Q.DataQualityError, match="must not enter research"):
        Q.require_usable(f, dataset_id="blocked", session_timezone=TZ)


def test_scheduled_breaks_are_separated_from_unexplained_holes():
    """Measured on the real store, 249 of 326 gaps are one identical 61-minute break at
    16:59 ET. Reporting that as "17,565 missing bars" buries the two real holes under it.

    The gate has no calendar and must not pretend to one, so it measures RECURRENCE instead:
    the same gap at the same venue clock time, seen often enough, is a schedule.
    """
    ts = []
    base = pd.Timestamp("2026-01-05 22:00", tz="UTC")     # 17:00 ET
    for day in range(12):
        d = base + pd.Timedelta(days=day)
        ts += [d - pd.Timedelta(minutes=1), d + pd.Timedelta(minutes=59)]
    ts = pd.DatetimeIndex(sorted(ts))
    n = len(ts)
    f = S.build_frame(instrument="ES", contract_symbol="ESH6", contract_family="ES",
                      timestamp=ts, session_date=pd.Series(ts).dt.tz_convert(TZ).dt.date,
                      bar_interval="1min", open_=[1.0] * n, high=[1.0] * n,
                      low=[1.0] * n, close=[1.0] * n, volume=[1.0] * n)
    rep = Q.check(f, dataset_id="breaks", session_timezone=TZ,
                  recurring_gap_min_count=10)
    assert rep.stats["recurring_break_patterns"] != "none"
    assert rep.stats["bars_absent_in_recurring_breaks"] > 0
    assert rep.stats["bars_absent_unexplained"] == 0
    assert not any(x.check == "unexplained_gaps" for x in rep.findings)


# ======================================================================================
# 10. PROVIDER AGNOSTICISM
# ======================================================================================

def test_no_provider_column_name_escapes_the_adapter_layer():
    """The rule that makes the engine provider-agnostic, checked mechanically.

    `t`, `contract`, `o/h/l/c/v` are IBKR-store spellings. They may appear in `adapters.py`
    and nowhere else in the layer - the moment one leaks into the loader or the schema, the
    engine has learned a provider.
    """
    import quant_brain.data.loader as _l
    import quant_brain.data.quality as _q
    import quant_brain.data.rolls as _r
    import quant_brain.data.schema as _s
    # Matched as COLUMN ACCESS - `df["t"]` - rather than as bare strings. A bare `"h"` is
    # also a time-unit suffix and a bare `"o"` is a legitimate dict key; testing for those
    # would fail on things that are not provider knowledge at all.
    banned = ('["t"]', "['t']", '["contract"]', "['contract']",
              '["o"]', '["h"]', '["l"]', '["c"]', '["v"]',
              '["date"]', '["bid_low"]', '["ask_high"]')
    for mod in (_s, _q, _r, _l):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        code = "\n".join(line for line in src.splitlines()
                         if not line.strip().startswith("#"))
        for token in banned:
            assert token not in code, (
                f"{mod.__name__} reads the provider column {token} - only adapters.py may "
                f"know a vendor's spellings")


def test_the_generic_adapter_refuses_to_guess_a_column(tmp_path):
    p = tmp_path / "x.csv"
    pd.DataFrame({"ts": ["2026-01-05T14:30:00Z"], "Open": [1.0], "High": [1.0],
                  "Low": [1.0], "Close": [1.0], "Vol": [1.0]}).to_csv(p, index=False)
    with pytest.raises(AD.AdapterError, match="no column mapping"):
        AD.generic_table(p, instrument="X", data_form=S.DataForm.RAW,
                         roll=RollSpec.none(), session_timezone=TZ, bar_interval="1min",
                         columns={"timestamp": "ts", "open": "Open"})


def test_the_generic_adapter_requires_an_explicit_data_form(tmp_path):
    p = tmp_path / "x.csv"
    pd.DataFrame({"ts": ["2026-01-05T14:30:00Z"], "o": [1.0], "h": [1.0], "l": [1.0],
                  "c": [1.0], "v": [1.0]}).to_csv(p, index=False)
    with pytest.raises(AD.AdapterError, match="explicit DataForm"):
        AD.generic_table(p, instrument="X", data_form="raw", roll=RollSpec.none(),
                         session_timezone=TZ, bar_interval="1min",
                         columns={"timestamp": "ts", "open": "o", "high": "h",
                                  "low": "l", "close": "c", "volume": "v"})


def test_two_providers_produce_the_same_canonical_shape(tmp_path):
    """The acceptance test for provider agnosticism: different files in, one schema out."""
    ibkr = tmp_path / "ES.parquet"
    pd.DataFrame({"t": pd.date_range("2026-01-05 14:30", periods=3, freq="1min", tz="UTC"),
                  "o": [1.0, 1.0, 1.0], "h": [1.0, 1.0, 1.0], "l": [1.0, 1.0, 1.0],
                  "c": [1.0, 1.0, 1.0], "v": [1.0, 1.0, 1.0],
                  "contract": ["ESH6"] * 3}).to_parquet(ibkr)
    other = tmp_path / "thing.csv"
    pd.DataFrame({"when": ["2026-01-05T14:30:00Z", "2026-01-05T14:31:00Z"],
                  "OPEN": [1.0, 1.0], "HIGH": [1.0, 1.0], "LOW": [1.0, 1.0],
                  "LAST": [1.0, 1.0], "QTY": [1.0, 1.0]}).to_csv(other, index=False)

    a, _ = AD.ibkr_futures(ibkr, instrument="ES")
    b, _ = AD.generic_table(
        other, instrument="ES", data_form=S.DataForm.RAW, roll=RollSpec.none(),
        session_timezone=TZ, bar_interval="1min", provider="whoever",
        columns={"timestamp": "when", "open": "OPEN", "high": "HIGH", "low": "LOW",
                 "close": "LAST", "volume": "QTY"})
    assert list(a.columns) == list(b.columns)
    S.validate_frame(a)
    S.validate_frame(b)


def test_the_ibkr_adapter_refuses_a_file_with_no_contract_column(tmp_path):
    p = tmp_path / "ES.parquet"
    pd.DataFrame({"t": pd.date_range("2026-01-05", periods=2, freq="1min", tz="UTC"),
                  "o": [1.0, 1.0], "h": [1.0, 1.0], "l": [1.0, 1.0], "c": [1.0, 1.0],
                  "v": [1.0, 1.0]}).to_parquet(p)
    with pytest.raises(AD.AdapterError, match="contract"):
        AD.ibkr_futures(p, instrument="ES")


def test_the_ibkr_adapter_refuses_when_the_caller_names_the_wrong_instrument(tmp_path):
    p = tmp_path / "x.parquet"
    pd.DataFrame({"t": pd.date_range("2026-01-05", periods=2, freq="1min", tz="UTC"),
                  "o": [1.0, 1.0], "h": [1.0, 1.0], "l": [1.0, 1.0], "c": [1.0, 1.0],
                  "v": [1.0, 1.0], "contract": ["NQH6"] * 2}).to_parquet(p)
    with pytest.raises(AD.AdapterError, match="Refusing rather than trusting"):
        AD.ibkr_futures(p, instrument="ES")


def test_a_file_holding_two_roots_is_refused(tmp_path):
    p = tmp_path / "x.parquet"
    pd.DataFrame({"t": pd.date_range("2026-01-05", periods=2, freq="1min", tz="UTC"),
                  "o": [1.0, 1.0], "h": [1.0, 1.0], "l": [1.0, 1.0], "c": [1.0, 1.0],
                  "v": [1.0, 1.0], "contract": ["ESH6", "NQH6"]}).to_parquet(p)
    with pytest.raises(AD.AdapterError, match="more than one root"):
        AD.ibkr_futures(p, instrument="ES")


# ======================================================================================
# 17 + 20. THE HOSTILE AUDIT: MANUFACTURING FALSE ALPHA THROUGH THE DATA LAYER
# ======================================================================================
#
# An adversarial researcher wants a profitable backtest and is willing to shape the data to
# get one. Each attack below is a real way to do it. The layer must refuse, or flag loudly
# enough that the result cannot be read as clean.

def test_attack_a_roll_discontinuity_presented_as_a_return():
    """The cheapest false alpha available: buy the day before every roll.

    An unadjusted splice puts a +0.85% jump in the series at a KNOWN date. A rule that is
    long into it earns that jump four times a year for free. The defence is that the form is
    declared CONTINUOUS_UNADJUSTED and the roll timestamps are ON the manifest, so the jump
    is locatable rather than hidden.
    """
    f = two_contracts(5000.0, 5100.0)
    events = R.detect_rolls(f)
    assert len(events) == 1 and events[0].gap_pct == pytest.approx(2.0)
    man = a_manifest(roll=RollSpec(
        method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
        adjustment=S.AdjustmentMethod.NONE, days_before_expiry=8,
        contracts=("ESH6", "ESM6"),
        roll_timestamps=(str(events[0].timestamp),), reconstructible=True))
    assert man.roll.roll_timestamps, "the roll instants must be discoverable from provenance"
    assert man.data_form is S.DataForm.CONTINUOUS_UNADJUSTED


def test_attack_filling_orders_at_adjusted_prices():
    """Back-adjust, then execute on it: every fill is at a price that never traded."""
    adj = a_dataset(data_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED,
                    roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                                  adjustment=S.AdjustmentMethod.DIFFERENCE,
                                  days_before_expiry=8, reconstructible=True))
    with pytest.raises(L.LoaderError):
        L.ResearchInputs(features=adj, execution=adj)


def test_attack_double_adjustment_to_flatten_a_drawdown():
    with pytest.raises(R.RollError):
        R.adjust(R.adjust(two_contracts(), method=S.AdjustmentMethod.RATIO,
                          direction="back").frame,
                 method=S.AdjustmentMethod.RATIO, direction="back",
                 source_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED)


def test_attack_hiding_the_adjustment_metadata():
    """Adjust the prices and declare the series unadjusted. The manifest catches the lie."""
    with pytest.raises(ManifestError, match="One of the two is wrong"):
        a_manifest(data_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED,
                   roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                                 adjustment=S.AdjustmentMethod.NONE,
                                 days_before_expiry=8, reconstructible=True))


def test_attack_shifting_timestamps_to_manufacture_foresight():
    """Move the prices one bar earlier and the signal sees the future.

    The layer cannot know a shift happened - but the frame fingerprint moves, so a result
    that claims to run on a given dataset can be checked against it.
    """
    honest = bars([5000.0, 5001.0, 5002.0, 5003.0])
    shifted = honest.copy()
    for col in ("open", "high", "low", "close"):
        shifted[col] = shifted[col].shift(-1).ffill()
    assert S.frame_fingerprint(honest) != S.frame_fingerprint(shifted)


def test_attack_relabelling_the_timezone_to_move_the_session():
    """Claim ET timestamps are UTC and every session slides five hours."""
    f = bars([5000.0, 5001.0])
    f["timestamp_timezone"] = "UTC"
    f["timestamp"] = f["timestamp"].dt.tz_convert(TZ)
    with pytest.raises(S.SchemaError, match="not UTC"):
        S.validate_frame(f)


def test_attack_substituting_a_contract_mid_file():
    """Swap in a different contract's prices without changing the label.

    Undetectable from the labels alone - which is why the layer reports contract SPANS and
    a revisit is a FAIL: real chains never go back.
    """
    f = bars([5000.0, 5100.0, 5000.0], contract=["ESH6", "ESM6", "ESH6"])
    rep = Q.check(f, dataset_id="sub", session_timezone=TZ)
    assert any(x.check == "contract_interleaving" for x in rep.of(Q.Level.FAIL))


def test_attack_an_unannounced_roll():
    """A contract change with no declaration. `detect_rolls` reads the DATA, so the roll is
    found whether or not anybody declared it."""
    f = bars([5000.0] * 3 + [5100.0] * 3, contract=["ESH6"] * 3 + ["ESM6"] * 3)
    assert len(R.detect_rolls(f)) == 1


def test_attack_duplicating_the_best_bars():
    f = bars([5000.0, 5100.0])
    doubled = pd.concat([f, f.iloc[[1]]], ignore_index=True)
    rep = Q.check(doubled, dataset_id="dupbest", session_timezone=TZ)
    assert rep.failed


def test_attack_deleting_the_worst_bars():
    """Deleting a bar cannot be detected as a lie - but it leaves a hole, and the hole is
    reported. A one-off gap is a WARN with a stated reason, not silence."""
    ts = pd.DatetimeIndex([pd.Timestamp("2026-01-05 14:30", tz="UTC"),
                           pd.Timestamp("2026-01-05 14:31", tz="UTC"),
                           pd.Timestamp("2026-01-05 14:40", tz="UTC")])
    f = S.build_frame(instrument="ES", contract_symbol="ESH6", contract_family="ES",
                      timestamp=ts, session_date=[MONDAY] * 3, bar_interval="1min",
                      open_=[1.0] * 3, high=[1.0] * 3, low=[1.0] * 3, close=[1.0] * 3,
                      volume=[1.0] * 3)
    rep = Q.check(f, dataset_id="holes", session_timezone=TZ)
    gaps = [x for x in rep.findings if x.check == "unexplained_gaps"]
    assert gaps and gaps[0].count == 8


def test_attack_corrupting_volume_to_fake_liquidity():
    rep = Q.check(bars([5000.0, 5001.0], volume=[1.0, float("nan")]),
                  dataset_id="v", session_timezone=TZ)
    assert any(x.check == "volume_finite" for x in rep.of(Q.Level.FAIL))


def test_attack_corrupting_ohlc_to_hit_a_stop_that_never_traded():
    """Widening a low reaches a stop that never printed. h<l is a FAIL; a low BELOW the real
    one cannot be caught from the file alone and is why the source hash exists."""
    rep = Q.check(bars([5000.0, 5001.0], highs=[5000.0, 5001.0], lows=[5010.0, 5000.0]),
                  dataset_id="wick", session_timezone=TZ)
    assert rep.failed


def test_attack_mixing_a_raw_and_an_adjusted_series_in_one_frame():
    """Two forms in one frame is a lie the manifest cannot express: a manifest declares ONE
    data form, so the mixture has to be presented as two datasets and then differ in id."""
    raw = a_manifest(data_form=S.DataForm.RAW, roll=RollSpec.none())
    adj = a_manifest(data_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED,
                     roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                                   adjustment=S.AdjustmentMethod.RATIO,
                                   days_before_expiry=8, reconstructible=True))
    assert raw.manifest_id != adj.manifest_id
    assert raw.execution_valid and not adj.execution_valid


def test_attack_a_provider_column_mismatch_that_swaps_high_and_low(tmp_path):
    """Map `high` to the low column. The mapping is explicit, so the swap is visible in the
    manifest - and the resulting frame fails the OHLC check anyway."""
    p = tmp_path / "x.csv"
    pd.DataFrame({"ts": ["2026-01-05T14:30:00Z"], "o": [5000.0], "hi": [5001.0],
                  "lo": [4999.0], "c": [5000.0], "v": [1.0]}).to_csv(p, index=False)
    frame, man = AD.generic_table(
        p, instrument="X", data_form=S.DataForm.RAW, roll=RollSpec.none(),
        session_timezone=TZ, bar_interval="1min",
        columns={"timestamp": "ts", "open": "o", "high": "lo", "low": "hi",
                 "close": "c", "volume": "v"})
    assert man.adapter_params["columns"]["high"] == "lo"
    rep = Q.check(frame, dataset_id="swap", session_timezone=TZ)
    assert any(x.check == "ohlc_validity" for x in rep.of(Q.Level.FAIL))


def test_attack_a_contract_multiplier_mismatch():
    """`instrument` is what prices a bar. A frame labelled MES whose contracts are ES roots
    would be priced at a tenth; the adapter refuses the mismatch."""
    assert C.family_of("MESZ5") == "MES"
    assert C.family_of("ESZ5") == "ES"
    assert C.family_of("MESZ5") != C.family_of("ESZ5")


def test_attack_lookahead_through_continuous_series_construction():
    """The subtle one: BACK adjustment uses gaps that happen in the FUTURE.

    Every bar of contract A in a back-adjusted series has been shifted by a number that was
    not knowable until contract B started trading. The series is not causal, and a feature
    computed on absolute back-adjusted price levels therefore embeds the future.

    Demonstrated here rather than asserted: the same early bar takes a different value
    depending on how many rolls happen AFTER it.
    """
    short = bars([5000.0] * 2 + [5100.0] * 2, contract=["ESH6"] * 2 + ["ESM6"] * 2)
    long = bars([5000.0] * 2 + [5100.0] * 2 + [5250.0] * 2,
                contract=["ESH6"] * 2 + ["ESM6"] * 2 + ["ESU6"] * 2)
    a = R.adjust(short, method=S.AdjustmentMethod.DIFFERENCE,
                 direction="back").frame["close"].iloc[0]
    b = R.adjust(long, method=S.AdjustmentMethod.DIFFERENCE,
                 direction="back").frame["close"].iloc[0]
    assert a == pytest.approx(5100.0)
    assert b == pytest.approx(5250.0)
    assert a != b, ("the SAME first bar takes two values depending on future rolls - a "
                    "back-adjusted price level is not knowable at the time of the bar")
    # forward adjustment does not have this property: the anchor is the first contract
    fa = R.adjust(short, method=S.AdjustmentMethod.DIFFERENCE,
                  direction="forward").frame["close"].iloc[0]
    fb = R.adjust(long, method=S.AdjustmentMethod.DIFFERENCE,
                  direction="forward").frame["close"].iloc[0]
    assert fa == fb == pytest.approx(5000.0)


# ======================================================================================
# 14 + 15 + 16. CROSS-SOURCE, DEPTH, REGRESSION - AGAINST THE REAL STORE
# ======================================================================================

@needs_store
def test_the_real_store_is_what_the_forensics_says_it_is():
    """Measured, not hand-computed: the figures in docs/DATA_FLOW_FORENSICS.md."""
    ds = L.load("ibkr_futures", FUTURES / "ES.parquet", instrument="ES")
    m = ds.manifest
    assert m.data_form is S.DataForm.CONTINUOUS_UNADJUSTED
    assert m.roll.method is S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY
    assert m.roll.days_before_expiry == 8
    assert m.roll.adjustment is S.AdjustmentMethod.NONE
    assert m.roll.reconstructible is True
    assert m.roll.contracts == ("ESU5", "ESZ5", "ESH6", "ESM6", "ESU6")
    assert len(m.roll.roll_timestamps) == 4
    assert m.bars == 447_600
    assert m.execution_valid is True
    events = R.detect_rolls(ds.frame)
    assert len(events) == 4
    assert all(0.5 < e.gap_pct < 1.2 for e in events), [e.gap_pct for e in events]


@needs_store
def test_the_roll_boundary_moves_in_the_venue_clock_across_dst():
    """FINDING 1, pinned as a test. The boundary is a fixed UTC instant, so it lands at
    18:00 ET in summer and 16:00 ET in winter - inside the RTH window."""
    ds = L.load("ibkr_futures", FUTURES / "ES.parquet", instrument="ES")
    events = R.detect_rolls(ds.frame)
    local = [e.timestamp.tz_convert(TZ).strftime("%H:%M") for e in events]
    assert local == ["18:00", "16:00", "18:00", "18:00"], local
    winter = [e for e, t in zip(events, local, strict=True) if t == "16:00"]
    assert winter, "the winter roll that intrudes on RTH must still be detectable"


@needs_store
def test_actual_historical_coverage_is_reported_not_claimed():
    """Section 15: architecture support is not data coverage.

    The schema can hold decades. The store holds fifteen months of futures and four rolls
    per instrument. Anything said about roll behaviour rests on those four.
    """
    depth = {}
    for sym in ("ES", "NQ", "MES", "MNQ"):
        p = FUTURES / f"{sym}.parquet"
        if not p.exists():
            continue
        ds = L.load("ibkr_futures", p, instrument=sym)
        span = (pd.Timestamp(ds.manifest.coverage_end)
                - pd.Timestamp(ds.manifest.coverage_start)).days
        depth[sym] = (span, len(R.detect_rolls(ds.frame)))
    assert depth["ES"][0] < 500, "ES coverage is months, not years"
    assert depth["ES"][1] == 4, "four rolls is the entire roll sample for ES"
    assert depth["MES"][0] < depth["ES"][0], "the micros start a quarter later"


@needs_store
def test_cross_source_es_and_mes_track_the_same_underlying():
    """Section 14: two independent series for one economic exposure.

    ES and MES are separate contracts on the same index, fetched separately. They are not
    required to be identical - they are different books with different ticks - but their
    returns must agree, and a divergence would mean one of the two feeds is wrong.

    Deliberately NOT a test of which one has the higher P&L.
    """
    es = L.load("ibkr_futures", FUTURES / "ES.parquet", instrument="ES")
    mes = L.load("ibkr_futures", FUTURES / "MES.parquet", instrument="MES")
    rep = X.compare(es.frame, mes.frame, left_id="ibkr-ES", right_id="ibkr-MES")

    assert rep.shared_bars > 300_000
    assert rep.return_correlation > 0.98, rep.return_correlation
    # On MATCHED expiries the two feeds agree to a tick half the time and to three ticks
    # at the 99th percentile. That is the number that says they describe one process.
    assert rep.price_diff_p50 == pytest.approx(0.0)
    assert rep.price_diff_p99 <= 1.0

    # THE FINDING: 2025-09-07..2025-09-11 the two stores are on DIFFERENT contracts,
    # because IBKR had already retired MESU5 so the micro chain starts a quarter later.
    # The ~55-point difference there is the Sep/Dec calendar spread, not a feed error - and
    # nothing in the old data path could have said so.
    assert rep.mismatched_expiry_bars == 5_520
    assert len(rep.mismatched_windows) == 1
    start, end, ca, cb, mean_gap = rep.mismatched_windows[0]
    assert (ca, cb) == ("ESU5", "MESZ5")
    assert start.startswith("2025-09-07") and end.startswith("2025-09-11")
    assert -60.0 < mean_gap < -50.0
    assert any("DIFFERENT contract expiries" in m for m in rep.material_findings)


@needs_store
def test_loading_the_real_store_twice_is_byte_identical():
    """Section 16: reproducibility. Same file, same config, same bars and same hashes."""
    a = L.load("ibkr_futures", FUTURES / "ES.parquet", instrument="ES")
    b = L.load("ibkr_futures", FUTURES / "ES.parquet", instrument="ES")
    assert a.fingerprint == b.fingerprint
    assert a.manifest.manifest_id == b.manifest.manifest_id
    assert a.manifest.source_hashes == b.manifest.source_hashes
    assert a.report.report_hash == b.report.report_hash


@needs_store
def test_the_canonical_layer_agrees_with_the_existing_loader_on_the_bars_it_keeps():
    """Section 16, the part that matters: the new layer must not silently change results.

    `futures_discover.load` applies the RTH window and the one-contract-per-session filter.
    Reproducing both on the canonical frame must give the SAME bars - if it does not, every
    published futures number would move the day the funnel is switched over.
    """
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    import futures_discover as fd

    fd.use_session(*fd.TOPSTEP_SESSION)
    old = fd.load(FUTURES / "ES.parquet", "ES")

    ds = L.load("ibkr_futures", FUTURES / "ES.parquet", instrument="ES")
    f = ds.frame
    et = f["timestamp"].dt.tz_convert(TZ)
    hm = et.dt.strftime("%H:%M")
    rth = f[(hm >= "09:30") & (hm <= "16:00")].copy()
    rth["day"] = et[rth.index].dt.date
    per = rth.groupby("day")["contract_symbol"].nunique()
    new = rth[rth["day"].isin(per[per == 1].index)]

    assert len(new) == len(old), f"canonical keeps {len(new)}, funnel keeps {len(old)}"
    assert np.allclose(new["close"].to_numpy(), old["c"].to_numpy())
    assert list(new["contract_symbol"].astype(str)) == list(old["contract"].astype(str))


# ======================================================================================
# HOLES FOUND BY MUTATION TESTING, NOW CLOSED
# ======================================================================================

def test_the_adjustment_method_alone_changes_the_manifest_id():
    """Two back-adjusted readings of one file that differ ONLY in how.

    `test_the_same_bytes_read_two_ways_have_different_manifest_ids` moves the data form and
    the adjustment together, so it still passed with the adjustment dropped from the hash.
    Difference and ratio produce genuinely different price series - different ATR, different
    stop distances, different R multiples - so two results computed under them must never
    share a provenance record.
    """
    def m(adj):
        return a_manifest(
            dataset_id="probe", data_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED,
            roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                          adjustment=adj, days_before_expiry=8, reconstructible=True))

    diff = m(S.AdjustmentMethod.DIFFERENCE)
    ratio = m(S.AdjustmentMethod.RATIO)
    assert diff.data_form is ratio.data_form           # the ONLY difference is the method
    assert diff.manifest_id != ratio.manifest_id


def test_the_roll_method_alone_changes_the_manifest_id():
    """The same, for the trigger rather than the adjustment."""
    cal = a_manifest()
    vol = a_manifest(roll=RollSpec(method=S.RollMethod.VOLUME_CROSSOVER,
                                   adjustment=S.AdjustmentMethod.NONE,
                                   reconstructible=True))
    assert cal.manifest_id != vol.manifest_id


def test_the_fingerprint_covers_the_prices_and_not_only_the_labels():
    """A hash that ignored the prices would call a corrupted frame unchanged."""
    f = bars([5000.0, 5001.0, 5002.0])
    base = S.frame_fingerprint(f)
    for col in ("open", "high", "low", "close", "volume"):
        moved = f.copy()
        moved.loc[1, col] = float(moved.loc[1, col]) + 0.25
        assert S.frame_fingerprint(moved) != base, f"{col} does not reach the fingerprint"
    shifted = f.copy()
    shifted["timestamp"] = shifted["timestamp"] + pd.Timedelta(minutes=1)
    assert S.frame_fingerprint(shifted) != base


def test_an_adjustment_moves_the_quotes_with_the_trades():
    """Quotes are prices too.

    Adjusting `close` and leaving `bid`/`ask` where they were manufactures a spread that
    grows with the cumulative offset - a cost model built out of an accounting error. On a
    +100 back adjustment the first contract's bid/ask must move by the same +100 as its
    trades, so the spread is unchanged.
    """
    n = 3
    ts = pd.date_range("2026-01-05 14:30", periods=2 * n, freq="1min", tz="UTC")
    px = np.array([5000.0] * n + [5100.0] * n)
    f = S.build_frame(
        instrument="ES", contract_symbol=["ESH6"] * n + ["ESM6"] * n,
        contract_family="ES", timestamp=ts,
        session_date=pd.Series(ts).dt.tz_convert(TZ).dt.date, bar_interval="1min",
        open_=px, high=px + 1, low=px - 1, close=px, volume=np.ones(2 * n),
        bid=px - 0.25, ask=px + 0.25)

    res = R.adjust(f, method=S.AdjustmentMethod.DIFFERENCE, direction="back")
    out = res.frame
    assert "bid" in out.columns and "ask" in out.columns
    # the first contract lifted by the full +100 gap, quotes included
    assert out["bid"].iloc[0] == pytest.approx(5100.0 - 0.25)
    assert out["ask"].iloc[0] == pytest.approx(5100.0 + 0.25)
    # and the spread is untouched everywhere
    spread = (out["ask"] - out["bid"]).to_numpy()
    assert np.allclose(spread, 0.5), spread
    # the columns an adjustment must touch, asserted so the list cannot silently shrink
    assert set(R.ADJUSTABLE_COLUMNS) == {"open", "high", "low", "close", "bid", "ask"}


def test_a_ratio_adjustment_also_moves_the_quotes():
    n = 2
    ts = pd.date_range("2026-01-05 14:30", periods=2 * n, freq="1min", tz="UTC")
    px = np.array([5000.0] * n + [5100.0] * n)
    f = S.build_frame(
        instrument="ES", contract_symbol=["ESH6"] * n + ["ESM6"] * n,
        contract_family="ES", timestamp=ts,
        session_date=pd.Series(ts).dt.tz_convert(TZ).dt.date, bar_interval="1min",
        open_=px, high=px, low=px, close=px, volume=np.ones(2 * n),
        bid=px - 0.25, ask=px + 0.25)
    out = R.adjust(f, method=S.AdjustmentMethod.RATIO, direction="back").frame
    factor = 5100.0 / 5000.0
    assert out["bid"].iloc[0] == pytest.approx((5000.0 - 0.25) * factor)
    # NOTE the consequence: a ratio adjustment SCALES the spread, so the modelled cost of
    # crossing it is 2% larger on the oldest bars than the market ever charged.
    assert (out["ask"].iloc[0] - out["bid"].iloc[0]) == pytest.approx(0.5 * factor)
    assert (out["ask"].iloc[0] - out["bid"].iloc[0]) > 0.5
