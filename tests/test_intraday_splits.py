"""AUD-15 / D-5: the IBKR store's split table and the merge guard that keeps it meaningful.

Two halves of one defect. `data/minute` holds SPLIT-ADJUSTED bars (IBKR serves them on the basis
current at fetch time) while `intraday_common.share_scale` returned 1.0 for it, so IBKR's per-share
commission was charged on the adjusted share count - measured at 14.63 bps/side too little on SOXS
for 131 sessions and 0.37 bps/side too much on NFLX for 58, against a 1.5 bps slippage line. The
table fixes the cost model; the `save_bars` guard is what stops the next split from re-creating the
problem one basis deeper, by refusing a merge whose overlapping bars disagree.
"""
from __future__ import annotations

import datetime as dt

import intraday_common as ic
import intraday_data as idata
import pandas as pd
import pytest

# ----------------------------------------------------------------- split_segments (derivation)

def _events(pairs) -> pd.Series:
    idx = pd.to_datetime([d for d, _ in pairs])
    return pd.Series([r for _, r in pairs], index=idx)


def test_a_forward_split_leaves_earlier_days_priced_a_tenth_of_the_tape():
    """NFLX 10-for-1 on 2025-11-17: every earlier adjusted close is 1/10 of what traded, so the
    factor (raw/adjusted) on those days is 10 and the real share count is adjusted/10."""
    segs = idata.split_segments("NFLX", dt.date(2025, 8, 26), dt.date(2026, 9, 11),
                                events=_events([("2025-11-17", 10.0)]))
    assert segs == [["2025-08-26", 10.0], ["2025-11-17", 1.0]]


def test_a_reverse_split_runs_the_other_way():
    """SOXS 1-for-20 on 2026-03-05: earlier adjusted closes are 20x the tape, factor 0.05."""
    segs = idata.split_segments("SOXS", dt.date(2025, 8, 26), dt.date(2026, 4, 1),
                                events=_events([("2026-03-05", 0.05)]))
    assert segs == [["2025-08-26", 0.05], ["2026-03-05", 1.0]]


def test_stacked_splits_compound_and_reproduce_the_real_soxs_table():
    """The real store's span holds both SOXS reverse splits; the factor before the first is the
    PRODUCT of both ratios. These three numbers are what data/minute_alpaca/_splits.json holds,
    derived independently from Alpaca's raw/adjusted price ratio (D-5 clause 3)."""
    segs = idata.split_segments("SOXS", dt.date(2025, 8, 26), dt.date(2026, 9, 11),
                                events=_events([("2026-03-05", 0.05), ("2026-07-15", 0.1)]))
    assert segs[0][1] == pytest.approx(0.005)
    assert segs[1] == ["2026-03-05", pytest.approx(0.1)]
    assert segs[2] == ["2026-07-15", 1.0]


def test_splits_outside_the_stored_span_are_ignored():
    """A split before the store starts has already been applied to every stored bar, and one after
    the store ends has not happened to any of them. Including either would rebase a correct file."""
    segs = idata.split_segments("NVDA", dt.date(2025, 8, 26), dt.date(2026, 9, 11),
                                events=_events([("2021-07-20", 4.0), ("2026-09-12", 2.0)]))
    assert segs == [["2025-08-26", 1.0]]


def test_a_split_on_the_first_stored_day_is_already_in_the_bars():
    """`first < d` is deliberate: bars stamped on the split date trade on the new basis."""
    segs = idata.split_segments("X", dt.date(2025, 8, 26), dt.date(2026, 1, 1),
                                events=_events([("2025-08-26", 10.0)]))
    assert segs == [["2025-08-26", 1.0]]


def test_share_scale_reads_a_written_table(tmp_path, monkeypatch):
    monkeypatch.setattr(ic, "DATA_DIR", tmp_path)
    monkeypatch.setattr(idata, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ic, "_SPLITS", None)
    monkeypatch.setattr(idata, "store_span", lambda s: (dt.date(2025, 8, 26), dt.date(2026, 9, 11)))
    monkeypatch.setattr(idata, "split_segments",
                        lambda s, a, b, events=None: [["2025-08-26", 0.005],
                                                      ["2026-03-05", 0.1], ["2026-07-15", 1.0]])
    idata.write_splits(["SOXS"])
    ic._SPLITS = None
    assert ic.share_scale("SOXS", dt.date(2025, 9, 2)) == pytest.approx(0.005)
    assert ic.share_scale("SOXS", dt.date(2026, 3, 5)) == pytest.approx(0.1)
    assert ic.share_scale("SOXS", dt.date(2026, 9, 11)) == 1.0
    ic._SPLITS = None


def test_write_splits_merges_and_never_drops_a_symbol(tmp_path, monkeypatch):
    """alpaca_data.write_splits learned this the hard way: a bare run used to rewrite a 60-symbol
    table as 16, and every dropped name then costs at scale 1.0 with nothing to show for it."""
    import json
    monkeypatch.setattr(ic, "DATA_DIR", tmp_path)
    monkeypatch.setattr(idata, "DATA_DIR", tmp_path)
    (tmp_path / ic.SPLITS_FILE).write_text(json.dumps({"ZZZZ": [["2016-01-04", 7.0]]}),
                                          encoding="utf-8")
    monkeypatch.setattr(idata, "store_span", lambda s: (dt.date(2025, 1, 2), dt.date(2026, 1, 2)))
    monkeypatch.setattr(idata, "split_segments",
                        lambda s, a, b, events=None: [["2025-01-02", 1.0]])
    out = idata.write_splits(["NVDA"])
    assert out["ZZZZ"] == [["2016-01-04", 7.0]] and "NVDA" in out


# ------------------------------------------------------------------ the save_bars merge guard

def _bars(day: str, n: int, px: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range(f"{day} 09:30", periods=n, freq="1min", tz=ic.ET).tz_convert("UTC")
    return pd.DataFrame({"o": px, "h": px, "l": px, "c": px, "v": 1000}, index=idx)


def test_identical_bars_merge_cleanly():
    a = _bars("2026-09-11", 60)
    assert ic.basis_mismatch(a, a) is None


def test_a_few_revised_bars_do_not_trip_the_guard():
    """IBKR revises individual bars; the statistic is a MEDIAN so a handful cannot move it."""
    a = _bars("2026-09-11", 60)
    b = a.copy()
    b.iloc[:5, b.columns.get_loc("c")] *= 1.5
    assert ic.basis_mismatch(a, b) is None


def test_a_rebased_history_is_caught_both_ways():
    a = _bars("2026-09-11", 60)
    fwd, rev = a.copy(), a.copy()
    fwd["c"] = fwd["c"] * 10.0           # the store is pre-split, the fetch is post-split
    rev["c"] = rev["c"] * 0.05
    for bad in (fwd, rev):
        m = ic.basis_mismatch(a, bad)
        assert m is not None and m["overlap"] == 60


def test_too_small_an_overlap_is_not_evidence():
    """A 5-bar overlap at a window boundary cannot distinguish a split from a thin session, and
    refusing on it would freeze the store - which is the failure D-4 had just finished repairing."""
    a = _bars("2026-09-11", 60)
    b = a.iloc[:ic.REBASIS_MIN_BARS - 1].copy()
    b["c"] = b["c"] * 10.0
    assert ic.basis_mismatch(a, b) is None


def test_save_bars_refuses_a_rebased_merge_and_accepts_it_when_told(tmp_path, monkeypatch):
    monkeypatch.setattr(ic, "DATA_DIR", tmp_path)
    first = _bars("2026-09-10", 60, px=100.0)
    assert ic.save_bars("ZZZZ", first) == 60
    rebased = _bars("2026-09-10", 60, px=1000.0)
    with pytest.raises(ic.BasisMismatch):
        ic.save_bars("ZZZZ", rebased)
    stored = pd.read_parquet(ic.parquet_path("ZZZZ"))
    assert stored["c"].max() == pytest.approx(100.0)          # the refusal left the file alone
    assert ic.save_bars("ZZZZ", rebased, allow_rebasis=True) == 60
    stored = pd.read_parquet(ic.parquet_path("ZZZZ"))
    assert stored["c"].min() == pytest.approx(1000.0)


def test_save_bars_still_appends_a_disjoint_session(tmp_path, monkeypatch):
    """The ordinary fetch: no overlap, nothing to compare, the guard must be invisible."""
    monkeypatch.setattr(ic, "DATA_DIR", tmp_path)
    ic.save_bars("ZZZZ", _bars("2026-09-10", 60, px=100.0))
    n = ic.save_bars("ZZZZ", _bars("2026-09-11", 60, px=1000.0))
    assert n == 120


def test_save_bars_still_overlaps_and_deduplicates(tmp_path, monkeypatch):
    """month_ends overlaps consecutive windows by ~5 days on purpose (IBKR drops the first session
    of a window). That overlap is the guard's input, so honest re-fetches must pass it."""
    monkeypatch.setattr(ic, "DATA_DIR", tmp_path)
    ic.save_bars("ZZZZ", _bars("2026-09-10", 60, px=100.0))
    n = ic.save_bars("ZZZZ", pd.concat([_bars("2026-09-10", 60, px=100.0),
                                        _bars("2026-09-11", 60, px=100.0)]))
    assert n == 120
