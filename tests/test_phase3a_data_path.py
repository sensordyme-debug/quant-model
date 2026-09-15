"""Phase 3A: the canonical data layer is the strategy backtester's authoritative input.

Two kinds of test here, and the distinction matters.

FAST, SYNTHETIC - the adapter's own rules. Built from frames written in the test, so a
refusal is provably a refusal and not an accident of the real store's contents.

SLOW, REAL (`acceptance`) - the equivalence itself, run over the actual parquet store through
the actual runner code. `scripts/canonical_equivalence.py` compares 636+ fields per
instrument; this pins the handful whose divergence would reprice the research history, so that
a regression fails in CI rather than in a report.

WHAT IS NOT TESTED HERE
-----------------------
That the canonical representation is CORRECT - that ES really is continuous-unadjusted with an
8-day calendar roll. That is `tests/test_canonical_data.py` and `docs/CANONICAL_DATA_LAYER.md`.
This file tests only that routing the backtester through it changed no number.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_brain.data import loader as L  # noqa: E402
from quant_brain.data import schema as S  # noqa: E402
from quant_brain.data.manifest import RollSpec  # noqa: E402
from quant_brain.research import session_source as ssrc  # noqa: E402

FUTURES = REPO / "data" / "futures"
#: MES is the smallest complete store, so the acceptance run is the cheapest one that still
#: exercises a real roll, a real early close and a real multi-contract session.
ACCEPTANCE_INSTRUMENT = "MES"

pytestmark = pytest.mark.filterwarnings("ignore::FutureWarning")


# ======================================================================================
# THE WINDOW
# ======================================================================================

def test_the_bar_count_is_inclusive_of_both_ends():
    """09:30..16:00 is 391 one-minute bars. 390 is the off-by-one that drops every session.

    `futures_discover.SESSION_BARS` had to be recomputed by hand whenever the close moved,
    and forgetting silently discarded the whole sample. Here the count is derived from the
    window and cannot be set separately from it.
    """
    assert ssrc.SessionWindow("09:30", "16:00").bars == 391
    assert ssrc.SessionWindow("09:30", "15:45").bars == 376
    assert ssrc.SessionWindow("09:30", "09:31").bars == 2


def test_a_window_that_ends_before_it_starts_is_refused():
    with pytest.raises(ssrc.SessionSourceError, match="not after"):
        ssrc.SessionWindow("16:00", "09:30")
    with pytest.raises(ssrc.SessionSourceError, match="not after"):
        ssrc.SessionWindow("09:30", "09:30")


@pytest.mark.parametrize("bad", ["9:30", "0930", "09:60", "24:00", "", "09:3"])
def test_a_window_that_is_not_a_wall_clock_time_is_refused(bad):
    """Parsed strictly. A window nobody can read is a window nobody checked."""
    with pytest.raises(ssrc.SessionSourceError, match="HH:MM"):
        ssrc.SessionWindow(bad, "16:00")


def test_the_window_comes_from_the_frozen_spec_and_not_from_a_default():
    from quant_brain.research.strategy_spec import SessionSpec, StrategySpec

    spec = StrategySpec(name="w", instrument="MES", timeframe="1min",
                        signal=lambda X: np.zeros(len(X)),
                        session=SessionSpec(open_et="10:00", close_et="15:00"))
    w = ssrc.SessionWindow.from_spec(spec)
    assert (w.open_et, w.close_et, w.bars) == ("10:00", "15:00", 301)


# ======================================================================================
# THE THREE FILTERS
# ======================================================================================

def _bars(day: str, contract: str, *, first: str = "09:30", n: int = 391,
          skip: set[int] | None = None) -> pd.DataFrame:
    """A synthetic ET session: `n` consecutive minutes from `first`, minus `skip`."""
    start = pd.Timestamp(f"{day} {first}", tz="America/New_York")
    idx = [i for i in range(n) if not (skip and i in skip)]
    t = pd.DatetimeIndex([start + pd.Timedelta(minutes=i) for i in idx]).tz_convert("UTC")
    return pd.DataFrame({
        "t": t, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 10.0, "contract": contract})


def test_a_session_spanning_two_contracts_is_dropped_entirely():
    """A session built from two physical contracts prices a roll gap as a return.

    Not partially kept, not spliced - dropped, and counted in the attrition record so the
    reader can see it happened.
    """
    good = _bars("2026-03-02", "MESH6")
    split = pd.concat([_bars("2026-03-03", "MESH6").iloc[:200],
                       _bars("2026-03-03", "MESM6").iloc[200:]], ignore_index=True)
    frame = pd.concat([good, split], ignore_index=True)
    w = ssrc.SessionWindow("09:30", "16:00")
    kept, attr = ssrc._cut(frame, w, bars_in_file=len(frame))

    assert [str(s["day"].iloc[0]) for s in kept] == ["2026-03-02"]
    assert attr.sessions_dropped_multi_contract == 1
    assert attr.multi_contract_days == ("2026-03-03",)
    assert attr.sessions_kept == 1


def test_an_early_close_is_dropped_rather_than_averaged_in_as_a_whole_day():
    """225 bars is a real CME half-day and 391 is a whole one. Mixing them is the defect."""
    frame = pd.concat([_bars("2026-03-02", "MESH6"),
                       _bars("2026-03-03", "MESH6", n=225)], ignore_index=True)
    kept, attr = ssrc._cut(frame, ssrc.SessionWindow("09:30", "16:00"), bars_in_file=616)
    assert [str(s["day"].iloc[0]) for s in kept] == ["2026-03-02"]
    assert attr.incomplete_days == ("2026-03-03",)


def test_an_interior_hole_is_dropped_even_when_the_ends_are_right():
    """Opens on the first minute, closes on the last, and is missing a minute in between."""
    frame = _bars("2026-03-02", "MESH6", skip={137})
    kept, attr = ssrc._cut(frame, ssrc.SessionWindow("09:30", "16:00"), bars_in_file=390)
    assert kept == []
    assert attr.sessions_dropped_incomplete == 1


def test_a_session_that_starts_late_is_dropped_even_at_the_right_bar_count():
    """391 bars starting at 09:31 is not the 09:30 session; the count alone cannot see it."""
    frame = _bars("2026-03-02", "MESH6", first="09:31")
    kept, _ = ssrc._cut(frame, ssrc.SessionWindow("09:30", "16:00"), bars_in_file=391)
    assert kept == []


def test_bars_outside_the_window_are_excluded_and_counted():
    """The overnight session is not RTH. It is filtered, and the filter is reported."""
    overnight = _bars("2026-03-02", "MESH6", first="04:00", n=60)
    frame = pd.concat([overnight, _bars("2026-03-02", "MESH6")], ignore_index=True)
    kept, attr = ssrc._cut(frame, ssrc.SessionWindow("09:30", "16:00"),
                           bars_in_file=len(frame))
    assert len(kept) == 1 and len(kept[0]) == 391
    assert attr.bars_in_file == 451 and attr.bars_in_window == 391


# ======================================================================================
# THE REFUSALS THE LEGACY PATH COULD NOT MAKE
# ======================================================================================

def _synthetic_store(tmp_path: Path) -> Path:
    """A two-session IBKR-layout parquet, so the real adapter can read it."""
    p = tmp_path / "MES.parquet"
    pd.concat([_bars("2026-03-02", "MESH6"), _bars("2026-03-03", "MESH6")],
              ignore_index=True).to_parquet(p)
    return p


def _dataset(tmp_path: Path) -> L.ResearchDataset:
    return L.load("ibkr_futures", _synthetic_store(tmp_path), instrument="MES")


def test_an_adjusted_series_is_refused_as_an_execution_source(tmp_path):
    """The central rule of the canonical layer, enforced at the backtester's front door.

    A back-adjusted price is a return series wearing price clothing: filling an order at one
    is filling at a number that did not exist. The legacy path had no way to know, because
    nothing in the parquet said what the prices were - and would have simulated the fills
    anyway.

    The SAME frame is used for both this test and the control below; only the declaration
    moves. That is the point: the refusal is about what the series IS, and the bytes cannot
    tell you.
    """
    import dataclasses

    ds = _dataset(tmp_path)
    adjusted = dataclasses.replace(
        ds.manifest, data_form=S.DataForm.CONTINUOUS_BACK_ADJUSTED,
        roll=RollSpec(method=S.RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                      adjustment=S.AdjustmentMethod.DIFFERENCE, days_before_expiry=8,
                      contracts=ds.manifest.roll.contracts, reconstructible=True))
    bad = L.ResearchDataset(frame=ds.frame, manifest=adjusted, report=ds.report)
    with pytest.raises(L.LoaderError, match="execution"):
        ssrc.from_dataset(bad, ssrc.SessionWindow("09:30", "16:00"))


def test_an_unadjusted_series_is_accepted_as_an_execution_source(tmp_path):
    """The control for the test above: the refusal is about the FORM, not about the file."""
    sset = ssrc.from_dataset(_dataset(tmp_path), ssrc.SessionWindow("09:30", "16:00"))
    assert len(sset) == 2
    assert sset.manifest.execution_valid
    assert sset.manifest.data_form is S.DataForm.CONTINUOUS_UNADJUSTED


def test_a_missing_store_fails_closed_rather_than_substituting_a_proxy(tmp_path):
    with pytest.raises(ssrc.SessionSourceError, match="fails closed"):
        ssrc.from_canonical(tmp_path / "nope.parquet", "MES",
                            ssrc.SessionWindow("09:30", "16:00"))


def test_a_window_with_no_complete_session_refuses_rather_than_returning_nothing(tmp_path):
    """Zero sessions is not an empty result, it is a misconfigured run. It raises."""
    with pytest.raises(ssrc.SessionSourceError, match="zero complete sessions"):
        ssrc.from_dataset(_dataset(tmp_path), ssrc.SessionWindow("09:30", "16:01"))


def test_an_unknown_data_path_is_refused_rather_than_defaulted():
    from quant_brain.research.strategy_spec import StrategySpec

    spec = StrategySpec(name="x", instrument="MES", timeframe="1min",
                        signal=lambda X: np.zeros(len(X)))
    with pytest.raises(ssrc.SessionSourceError, match="unknown data path"):
        ssrc.build(spec, data_path="whatever")


def test_the_canonical_path_carries_the_provenance_the_legacy_path_cannot(tmp_path):
    """Manifest id, frame fingerprint, data form, roll method, adjustment, quality status."""
    sset = ssrc.from_dataset(_dataset(tmp_path), ssrc.SessionWindow("09:30", "16:00"))
    fd_ = sset.provenance["feature_data"]
    assert fd_["data_form"] == "CONTINUOUS_UNADJUSTED"
    assert fd_["roll_method"] == "CALENDAR_DAYS_BEFORE_EXPIRY"
    assert fd_["adjustment_method"] == "NONE"
    assert len(fd_["manifest_id"]) == 16 and len(fd_["frame_fingerprint"]) == 16
    assert fd_["quality_status"] in ("PASS", "WARN")
    assert sset.provenance["gates_run"] == [
        "schema.validate_frame", "data.quality.check",
        "futures_cme.dataquality.require_usable"]
    # The legacy block is the same shape and honestly empty, so a reader comparing two
    # results never meets a missing key where a declaration should be.
    legacy = ssrc.from_legacy(FUTURES / "MES.parquet", "MES",
                              ssrc.SessionWindow("09:30", "16:00")) \
        if (FUTURES / "MES.parquet").exists() else None
    if legacy is not None:
        assert set(legacy.provenance) >= {"feature_data", "execution_data", "gates_run"}
        assert legacy.provenance["feature_data"]["data_form"] is None


def test_the_backtester_column_contract_is_exactly_what_the_engine_reads():
    """`ledger_builder` reads c/h/l/t/day and the feature library reads o/h/l/c/v.

    Pinned so that adding a column to the canonical schema cannot silently change the frame
    the engine iterates.
    """
    assert ssrc.BACKTESTER_COLUMNS == ("t", "o", "h", "l", "c", "v", "contract", "day", "hm")


def test_run_strategy_takes_the_canonical_path_unless_told_otherwise():
    """The default is the whole point of the phase. Asserted on the parser, not on prose."""
    import run_strategy as rs

    assert rs.load_sessions.__defaults__ == ("canonical",)


# ======================================================================================
# THE ACCEPTANCE RUN - real store, real runner, both paths
# ======================================================================================

@pytest.mark.acceptance
@pytest.mark.skipif(not (FUTURES / f"{ACCEPTANCE_INSTRUMENT}.parquet").exists(),
                    reason="futures store absent")
def test_the_two_data_paths_produce_the_same_bars_on_the_real_store():
    """Bar for bar, label for label, price for price. The rest of the engine is downstream."""
    w = ssrc.SessionWindow("09:30", "16:00")
    store = FUTURES / f"{ACCEPTANCE_INSTRUMENT}.parquet"
    a = ssrc.from_canonical(store, ACCEPTANCE_INSTRUMENT, w)
    b = ssrc.from_legacy(store, ACCEPTANCE_INSTRUMENT, w)

    assert len(a) == len(b) > 100
    assert [str(s["day"].iloc[0]) for s in a.sessions] == \
           [str(s["day"].iloc[0]) for s in b.sessions]

    ca = pd.concat(a.frames, ignore_index=True)
    cb = pd.concat(b.frames, ignore_index=True)
    assert list(ca.columns) == list(cb.columns) == list(ssrc.BACKTESTER_COLUMNS)
    assert (ca["t"].to_numpy() == cb["t"].to_numpy()).all()
    assert list(ca["contract"].astype(str)) == list(cb["contract"].astype(str))
    for col in ("o", "h", "l", "c", "v"):
        assert (ca[col].to_numpy() == cb[col].to_numpy()).all(), col
    # The one figure that is allowed to differ, and the reason it does.
    assert a.attrition.sessions_kept == b.attrition.sessions_kept
    assert a.attrition.bars_in_window >= b.attrition.bars_in_window


@pytest.mark.acceptance
@pytest.mark.skipif(not (FUTURES / f"{ACCEPTANCE_INSTRUMENT}.parquet").exists(),
                    reason="futures store absent")
def test_the_two_data_paths_produce_the_same_trades_pnl_and_topstep_result():
    """End to end on the frozen reference spec: signals, fills, trades, P&L, MAE/MFE, account.

    This is the property the phase gate turns on. If it ever fails, the canonical path must
    stop being authoritative until the difference is attributed - and it must NOT be closed
    by changing the strategy or by loosening the comparison.
    """
    import dataclasses

    import canonical_equivalence as ce

    from examples.example_strategy import SPEC

    spec = dataclasses.replace(SPEC, instrument=ACCEPTANCE_INSTRUMENT)
    a = ce.run_one(spec, ssrc.CANONICAL, account_size=50_000, daily_loss_limit=None, reps=50)
    b = ce.run_one(spec, ssrc.LEGACY, account_size=50_000, daily_loss_limit=None, reps=50)
    cmp = ce.compare(a, b)

    assert not cmp.failures, "\n".join(c.row() for c in cmp.failures)
    assert sum(1 for c in cmp.checks if c.status == "MATCH") > 500
    # The comparison must actually have had something to compare.
    head = a.ledgers["CONSERVATIVE"]
    assert len(head.trade_frame()) > 50
    assert head.spec_hash == b.ledgers["CONSERVATIVE"].spec_hash == spec.spec_hash
