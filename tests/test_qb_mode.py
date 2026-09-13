"""Tests for the execution-authority ladder.

These are adversarial by design. The module's entire purpose is to make one specific accident
impossible - a research process reaching a real account - so the tests spend their time trying
to cause exactly that: by configuration, by environment, by a stale file, by an omitted
argument, by pointing a paper adapter at a live socket.

The brief's §44 is absolute: this work must not enable live trading. The strongest evidence
that it does not is a test that tries hard to and fails.
"""
from __future__ import annotations

import dataclasses
import os

import pytest

from quant_brain.core.execution import (
    OrderIntent,
    RoutedExecutor,
    Side,
    SimulatedAdapter,
)
from quant_brain.core.mode import (
    LIVE_ENV,
    Authority,
    Mode,
    NotPermitted,
    approval_for,
    from_environment,
    write_approval,
)
from quant_brain.core.risk import RiskChain


@pytest.fixture
def clean_env(monkeypatch):
    for var in (LIVE_ENV, "QB_ACCOUNT_MODE", "QB_VENUE", "QB_ACCOUNT"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# ======================================================================================
# THE LADDER
# ======================================================================================

def test_the_modes_are_ordered_so_comparison_is_the_permission_test():
    assert (Mode.RESEARCH < Mode.BACKTEST < Mode.VALIDATED < Mode.PAPER
            < Mode.PRACTICE < Mode.HUMAN_APPROVAL < Mode.EXECUTION_READY)


def test_only_the_top_rung_risks_real_money():
    risky = [m for m in Mode if m.risks_real_money]
    assert risky == [Mode.EXECUTION_READY]


def test_paper_and_above_touch_a_real_venue():
    assert not Mode.VALIDATED.touches_a_venue
    assert Mode.PAPER.touches_a_venue
    assert Mode.PRACTICE.touches_a_venue


def test_a_lower_authority_cannot_reach_a_higher_requirement():
    a = Authority.backtest()
    assert a.permits(Mode.BACKTEST)
    assert not a.permits(Mode.PAPER)
    with pytest.raises(NotPermitted) as e:
        a.require(Mode.PAPER, what="sending an order")
    assert "sending an order" in str(e.value)
    assert "BACKTEST" in str(e.value)


def test_authority_is_immutable():
    """A mutable authority would get raised mid-run, which is the whole failure mode."""
    a = Authority.research()
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.mode = Mode.EXECUTION_READY          # type: ignore[misc]


# ======================================================================================
# LIVE CANNOT BE REACHED BY ANY SINGLE MISTAKE
# ======================================================================================

def test_live_needs_the_explicit_argument(clean_env, tmp_path):
    clean_env.setenv(LIVE_ENV, "true")
    write_approval("topstep", "X1", approved_by="a person", statement="ok",
                   approval_dir=tmp_path)
    with pytest.raises(NotPermitted) as e:
        Authority.for_live("topstep", "X1", approval_dir=tmp_path)
    assert "i_understand_this_is_real_money" in str(e.value)


def test_live_needs_the_environment_variable(clean_env, tmp_path):
    write_approval("topstep", "X1", approved_by="a person", statement="ok",
                   approval_dir=tmp_path)
    with pytest.raises(NotPermitted) as e:
        Authority.for_live("topstep", "X1", i_understand_this_is_real_money=True,
                           approval_dir=tmp_path)
    assert LIVE_ENV in str(e.value)


def test_live_needs_the_approval_file(clean_env, tmp_path):
    clean_env.setenv(LIVE_ENV, "true")
    with pytest.raises(NotPermitted) as e:
        Authority.for_live("topstep", "X1", i_understand_this_is_real_money=True,
                           approval_dir=tmp_path)
    assert "no approval file" in str(e.value)


def test_an_empty_approval_file_is_not_an_approval(clean_env, tmp_path):
    clean_env.setenv(LIVE_ENV, "true")
    path = approval_for("topstep", "X1", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("   \n", encoding="utf-8")
    with pytest.raises(NotPermitted) as e:
        Authority.for_live("topstep", "X1", i_understand_this_is_real_money=True,
                           approval_dir=tmp_path)
    assert "empty" in str(e.value)


def test_all_three_together_do_grant_it(clean_env, tmp_path):
    """The positive case, so the refusals above are proved to be about the conditions."""
    clean_env.setenv(LIVE_ENV, "1")
    write_approval("topstep", "X1", approved_by="the owner",
                   statement="Approved for the 50K practice-graduated account.",
                   approval_dir=tmp_path)
    a = Authority.for_live("topstep", "X1", i_understand_this_is_real_money=True,
                           approval_dir=tmp_path)
    assert a.mode is Mode.EXECUTION_READY
    assert "the owner" in a.note


@pytest.mark.parametrize("value", ["", "0", "false", "no", "maybe", "TRUE ", " 1"])
def test_only_an_unambiguous_truthy_env_counts(clean_env, tmp_path, value):
    clean_env.setenv(LIVE_ENV, value)
    write_approval("topstep", "X1", approved_by="p", statement="s", approval_dir=tmp_path)
    if value.strip().lower() in {"1", "true", "yes"}:
        Authority.for_live("topstep", "X1", i_understand_this_is_real_money=True,
                           approval_dir=tmp_path)
    else:
        with pytest.raises(NotPermitted):
            Authority.for_live("topstep", "X1", i_understand_this_is_real_money=True,
                               approval_dir=tmp_path)


def test_an_approval_for_one_account_does_not_authorise_another(clean_env, tmp_path):
    """The substitution the per-account file exists to prevent."""
    clean_env.setenv(LIVE_ENV, "true")
    write_approval("topstep", "PRACTICE1", approved_by="p", statement="practice only",
                   approval_dir=tmp_path)
    Authority.for_live("topstep", "PRACTICE1", i_understand_this_is_real_money=True,
                       approval_dir=tmp_path)
    with pytest.raises(NotPermitted):
        Authority.for_live("topstep", "FUNDED9", i_understand_this_is_real_money=True,
                           approval_dir=tmp_path)


def test_an_approval_for_one_venue_does_not_authorise_another(clean_env, tmp_path):
    clean_env.setenv(LIVE_ENV, "true")
    write_approval("topstep", "A", approved_by="p", statement="s", approval_dir=tmp_path)
    with pytest.raises(NotPermitted):
        Authority.for_live("ibkr", "A", i_understand_this_is_real_money=True,
                           approval_dir=tmp_path)


# ======================================================================================
# CONFIGURATION CANNOT GRANT LIVE
# ======================================================================================

def test_configuration_defaults_to_research(clean_env):
    a = from_environment()
    assert a.mode is Mode.RESEARCH


def test_configuration_can_select_up_to_practice(clean_env):
    for name in ("BACKTEST", "VALIDATED", "PAPER", "PRACTICE"):
        clean_env.setenv("QB_ACCOUNT_MODE", name)
        assert from_environment().mode is Mode[name]


@pytest.mark.parametrize("name", ["HUMAN_APPROVAL", "EXECUTION_READY"])
def test_configuration_refuses_to_select_live(clean_env, name):
    """A config file that could grant live makes every deployment one typo from trading."""
    clean_env.setenv("QB_ACCOUNT_MODE", name)
    with pytest.raises(NotPermitted) as e:
        from_environment()
    assert "cannot select" in str(e.value)
    assert "for_live" in str(e.value)


def test_an_unknown_mode_is_refused_rather_than_defaulted(clean_env):
    clean_env.setenv("QB_ACCOUNT_MODE", "PROD")
    with pytest.raises(NotPermitted) as e:
        from_environment()
    assert "not a mode" in str(e.value)


def test_setting_only_the_live_env_var_grants_nothing(clean_env):
    """The env var is necessary, never sufficient."""
    clean_env.setenv(LIVE_ENV, "true")
    assert from_environment().mode is Mode.RESEARCH


# ======================================================================================
# THE ORDER PATH ENFORCES IT AT CONSTRUCTION
# ======================================================================================

def test_an_omitted_authority_is_research_and_reaches_nothing():
    """The safe reading of "the caller did not think about it"."""
    with pytest.raises(NotPermitted) as e:
        RoutedExecutor(RiskChain(), SimulatedAdapter())
    assert "RESEARCH" in str(e.value)


def test_a_backtest_authority_reaches_a_simulator():
    ex = RoutedExecutor(RiskChain(), SimulatedAdapter(), authority=Authority.backtest())
    acks = ex.submit([OrderIntent(symbol="ES", side=Side.BUY, quantity=1)])
    assert len(acks) == 1 and acks[0].accepted


def test_the_check_happens_at_construction_not_at_submit():
    """A process that could not legitimately trade cannot assemble the object that would."""
    class LiveOnly(SimulatedAdapter):
        name = "pretend-live"
        requires = Mode.EXECUTION_READY

    with pytest.raises(NotPermitted):
        RoutedExecutor(RiskChain(), LiveOnly(), authority=Authority.practice("topstep"))


def test_a_practice_authority_cannot_reach_a_live_adapter():
    class Funded(SimulatedAdapter):
        name = "funded"
        requires = Mode.EXECUTION_READY

    with pytest.raises(NotPermitted) as e:
        RoutedExecutor(RiskChain(), Funded(), authority=Authority.practice("topstep", "X"))
    assert "funded" in str(e.value)


def test_an_adapter_defaults_to_requiring_the_top_rung():
    """An adapter author who forgets to declare `requires` gets the safe answer."""
    from quant_brain.core.execution import ExecutionAdapter
    assert ExecutionAdapter.requires is Mode.EXECUTION_READY


def test_the_ibkr_adapter_is_paper_unless_told_otherwise():
    from quant_brain.brokers.ibkr import IBKRAdapter
    assert IBKRAdapter(None, {}).requires is Mode.PAPER
    assert IBKRAdapter(None, {}, live=True).requires is Mode.EXECUTION_READY


def test_pointing_ibkr_at_live_makes_a_paper_process_refuse_it():
    """Paper and live differ only by port, which is far too small a difference to leave
    implicit."""
    from quant_brain.brokers.ibkr import IBKRAdapter
    with pytest.raises(NotPermitted):
        RoutedExecutor(RiskChain(), IBKRAdapter(None, {}, live=True),
                       authority=Authority.paper("ibkr"))


# ======================================================================================
# THE APPROVAL ARTEFACT
# ======================================================================================

def test_an_approval_records_who_and_when(tmp_path):
    path = write_approval("topstep", "X1", approved_by="the owner",
                          statement="Approved after 20 practice sessions.",
                          approval_dir=tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "the owner" in text and "topstep" in text and "X1" in text
    assert "practice sessions" in text
    assert "when:" in text


def test_an_approval_must_say_who_and_what(tmp_path):
    for by, what in (("", "s"), ("p", ""), ("  ", "  ")):
        with pytest.raises(ValueError):
            write_approval("topstep", "X", approved_by=by, statement=what,
                           approval_dir=tmp_path)


def test_the_approval_path_is_sanitised(tmp_path):
    p = approval_for("top/step", "../../etc", tmp_path)
    assert ".." not in p.name and "/" not in p.name


# ======================================================================================
# THE REPOSITORY DEFAULT
# ======================================================================================

def test_this_checkout_is_not_configured_for_live():
    """A standing assertion about the repository itself, not about a fixture.

    If this ever fails, someone has committed a live-trading default, and that is exactly
    the thing the whole module exists to make impossible.
    """
    assert os.environ.get(LIVE_ENV, "").strip().lower() not in {"1", "true", "yes"}, (
        f"{LIVE_ENV} is truthy in the environment running the test suite")
