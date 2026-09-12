"""Controlled reconciliation of the contaminated live state file.

The file on disk had `equity`, `equity_high` and `equity_curve` set to
`MockAccount.net_liq = 100_000` while the real account held **988,031.55** - understated by
roughly ten times - and `signal_state.peak`, the strategy's own drawdown reference, carried
the same fabricated number.

Deleting the file would have been the easy fix and the wrong one: `signal`, `as_of`,
`targets` and the strategy's carry state are real, and `held_age` feeds holding decisions, so
resetting it is a strategy change wearing a cleanup's clothes. These tests pin the split.
"""
from __future__ import annotations

import json

import pytest
import reconcile_state as rs

CONTAMINATED = {
    "equity": 100000.0,
    "equity_high": 100000.0,
    "equity_curve": [100000.0, 100000.0, 100000.0, 100000.0],
    "signal_state": {"peak": 100000.0, "flat_countdown": 0,
                     "held": ["XLE", "XLK", "IWM"],
                     "held_age": {"XLE": 15, "XLK": 15, "IWM": 6}},
    "signal": "s1_momo",
    "as_of": "2026-09-10",
    "targets": {"XLE": 0.515377, "XLK": 0.375511, "IWM": 0.609112},
    "ran_at": "2026-09-11T22:06:32+00:00",
    "dry_run": True,
}

ACCOUNT = {"account": "DUT091359", "net_liquidation": 988031.55, "is_paper": True,
           "positions": {"XLK": 2004, "IWM": 2093, "XLE": 7847}}


# --------------------------------------------------------------------------- classification

def test_the_fabricated_fields_are_exactly_the_equity_ones_plus_the_marker():
    fab, keep = rs.classify(CONTAMINATED)
    assert set(fab) == {"equity", "equity_high", "equity_curve", "dry_run"}
    assert set(keep) == {"signal", "as_of", "targets", "signal_state"}


# --------------------------------------------------------------------------- reconciliation

def test_equity_comes_from_the_account_not_from_the_file():
    out, problems = rs.reconcile(CONTAMINATED, ACCOUNT)
    assert not problems
    assert out["equity"] == out["equity_high"] == 988031.55
    assert out["equity_curve"] == [988031.55]


def test_the_dry_run_marker_does_not_survive():
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    assert "dry_run" not in out
    from quant_brain.core.state import is_contaminated
    assert not is_contaminated(out)


def test_the_strategys_own_peak_is_reseeded_too():
    """The field that matters most: peak is the drawdown reference the overlay measures
    against. Left at 100,000 on a 988,031 account it is ten times too low."""
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    assert out["signal_state"]["peak"] == 988031.55
    assert out["_peak_reconciled_from"] == 100000.0


def test_the_real_fields_are_preserved_untouched():
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    for k in ("signal", "as_of", "targets"):
        assert out[k] == CONTAMINATED[k]
    for k in ("held", "held_age", "flat_countdown"):
        assert out["signal_state"][k] == CONTAMINATED["signal_state"][k]


def test_held_age_is_deliberately_not_corrected():
    """Wrong (it counted runs, not sessions) but unknowable from here, and it drives holding
    decisions. Changing it silently would be a strategy change disguised as a cleanup."""
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    assert out["signal_state"]["held_age"] == {"XLE": 15, "XLK": 15, "IWM": 6}


def test_the_original_values_are_recorded_for_audit():
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    assert out["reconciled_from"]["equity"] == 100000.0
    assert out["reconciled_from"]["dry_run"] is True
    assert out["reconciled_at"]


# ------------------------------------------------------- refusals: never invent an account

def test_an_unreachable_gateway_refuses_rather_than_guessing():
    """Part 18: UNKNOWN STATE = DO NOT TRADE, and equally, do not fabricate."""
    _out, problems = rs.reconcile(CONTAMINATED, {"error": "TimeoutError: no gateway"})
    assert problems and any("cannot read the account" in p for p in problems)


def test_a_zero_nav_is_refused():
    """AUD-02's shape: an empty accountSummary during a Gateway resync reads as zero."""
    _out, problems = rs.reconcile(CONTAMINATED, {**ACCOUNT, "net_liquidation": 0.0})
    assert problems and any("NetLiquidation is 0" in p for p in problems)


def test_a_non_paper_account_is_refused():
    _out, problems = rs.reconcile(
        CONTAMINATED, {**ACCOUNT, "account": "U1234567", "is_paper": False})
    assert problems and any("not a DU paper account" in p for p in problems)


# --------------------------------------------------------------------------- validation

def test_validation_passes_on_a_correct_reconciliation():
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    assert rs.validate(out, ACCOUNT, CONTAMINATED) == []


def test_validation_catches_a_surviving_dry_run_marker():
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    out["dry_run"] = True
    assert any("dry_run" in b for b in rs.validate(out, ACCOUNT, CONTAMINATED))


def test_validation_catches_an_unreseeded_peak():
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    out["signal_state"] = {**out["signal_state"], "peak": 100000.0}
    assert any("peak" in b for b in rs.validate(out, ACCOUNT, CONTAMINATED))


def test_validation_catches_a_mutated_real_field():
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    out["targets"] = {"SPY": 1.0}
    assert any("targets" in b for b in rs.validate(out, ACCOUNT, CONTAMINATED))


def test_validation_catches_altered_strategy_carry():
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    out["signal_state"] = {**out["signal_state"], "held": []}
    assert any("carry" in b for b in rs.validate(out, ACCOUNT, CONTAMINATED))


def test_validation_catches_equity_not_taken_from_the_account():
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    out["equity"] = 123.0
    assert any("NetLiquidation" in b for b in rs.validate(out, ACCOUNT, CONTAMINATED))


# --------------------------------------------------------------------------- backup

def test_backup_copies_every_state_document(tmp_path, monkeypatch):
    src = tmp_path / "state"
    src.mkdir()
    (src / "last_run.json").write_text(json.dumps(CONTAMINATED), encoding="utf-8")
    (src / "intraday_book.json").write_text("{}", encoding="utf-8")
    (src / "nav_history.jsonl").write_text('{"nav":1}\n', encoding="utf-8")
    monkeypatch.setattr(rs, "STATE_DIR", src)
    dest = rs.backup(tmp_path / "backup")
    assert {p.name for p in dest.iterdir()} == {
        "last_run.json", "intraday_book.json", "nav_history.jsonl"}
    assert json.loads((dest / "last_run.json").read_text(encoding="utf-8")) == CONTAMINATED


def test_reconciling_an_already_clean_file_is_stable():
    """Idempotence: running it twice must not drift the numbers."""
    once, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    twice, problems = rs.reconcile(once, ACCOUNT)
    assert not problems
    assert twice["equity"] == once["equity"] == 988031.55
    assert twice["signal_state"]["peak"] == 988031.55
    assert rs.validate(twice, ACCOUNT, once) == []


@pytest.mark.parametrize("field", ["equity", "equity_high"])
def test_every_equity_field_ends_up_at_the_account_value(field):
    out, _ = rs.reconcile(CONTAMINATED, ACCOUNT)
    assert out[field] == ACCOUNT["net_liquidation"]
