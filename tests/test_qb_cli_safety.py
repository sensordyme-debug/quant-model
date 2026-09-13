"""The safety-layer CLI commands: they read state, never invent it, and exit non-zero on a
condition that blocks."""
from __future__ import annotations

from quant_brain.__main__ import main
from quant_brain.core.governor import AccountView, Governor, Limits, Reason
from quant_brain.core.idempotency import IntentJournal, IntentState
from quant_brain.core.state import StateScope, StateStore


def test_risk_status_with_nothing_published_says_so_and_blocks(tmp_path, capsys):
    rc = main(["risk", "status", "--scope", "dryrun", "--base", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1 and "no governor status published" in out


def test_risk_status_reads_what_a_governor_published(tmp_path, capsys):
    g = Governor(Limits(max_daily_loss=500), AccountView(daily_pnl=-120.0))
    store = StateStore.open(StateScope.DRYRUN, base=tmp_path)
    g.publish(store)
    rc = main(["risk", "status", "--scope", "dryrun", "--base", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0 and "halted: no" in out and "max_daily_loss" in out and "-120.0" in out
    assert "scope dryrun" in out

    g.trip(Reason.DATA_STALE, "last bar 90s old")
    g.publish(store)
    rc = main(["risk", "status", "--scope", "dryrun", "--base", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1 and "halted: YES" in out and "DATA_STALE" in out and "90s old" in out
    assert "named person" in out


def test_risk_status_reports_unknown_view_fields_as_unknown(tmp_path, capsys):
    Governor(Limits(), AccountView()).publish(StateStore.open(StateScope.DRYRUN, base=tmp_path))
    main(["risk", "status", "--base", str(tmp_path)])
    out = capsys.readouterr().out
    assert "UNKNOWN" in out


def test_risk_status_does_not_cross_scopes(tmp_path, capsys):
    Governor(Limits(), AccountView()).publish(StateStore.open(StateScope.DRYRUN, base=tmp_path))
    rc = main(["risk", "status", "--scope", "backtest", "--base", str(tmp_path)])
    assert rc == 1 and "no governor status" in capsys.readouterr().out


def test_risk_reasons_lists_every_code_and_marks_switches(capsys):
    assert main(["risk", "reasons"]) == 0
    out = capsys.readouterr().out
    for r in Reason:
        assert r.value in out
    assert "* DATA_STALE" in out and "  RISK_DAILY_LOSS" in out


def test_session_readiness_lists_all_thirteen_unmet(capsys):
    assert main(["session", "readiness"]) == 0
    out = capsys.readouterr().out
    assert out.count("[ ]") == 13 and "AUTHENTICATED is not READY" in out


def test_intents_recover_blocks_on_unresolved_and_passes_when_clean(tmp_path, capsys):
    p = tmp_path / "intents.jsonl"
    assert main(["intents", "recover", "--path", str(p)]) == 0
    j = IntentJournal(p)
    j.claim("aaa", note="MES buy 1")
    j.claim("bbb")
    j.advance("bbb", IntentState.SUBMITTED)
    j.claim("ccc")
    j.advance("ccc", IntentState.ACKED)
    rc = main(["intents", "recover", "--path", str(p)])
    out = capsys.readouterr().out
    assert rc == 1 and "2 of 3" in out and "aaa" in out and "bbb" in out and "ccc" not in out
    assert "Do not resend" in out
