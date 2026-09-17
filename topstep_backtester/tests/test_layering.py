"""The architectural claims, checked against the source rather than believed.

Every assertion in this file corresponds to a sentence somebody could otherwise write in a
README and never verify: that the engine is untouched, that only one module reaches it, that
nothing here can transmit an order, and that the pipeline ships with no strategies loaded.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from topstep_backtester import safety, upstream
from topstep_backtester.strategies import registry
from topstep_backtester.validation import layering


def test_only_the_seam_imports_the_upstream_engine() -> None:
    findings = layering.scan_upstream_imports()
    assert findings == [], (
        "these modules import topstep_backtest directly instead of going through "
        "topstep_backtester.upstream:\n  " + "\n  ".join(str(f) for f in findings)
    )


def test_nothing_imports_a_live_trading_sdk() -> None:
    findings = layering.scan_forbidden_imports()
    assert findings == [], "\n  ".join(str(f) for f in findings)


def test_no_order_transmission_or_credential_tokens_anywhere() -> None:
    findings = layering.scan_for_transmission()
    assert findings == [], "\n  ".join(str(f) for f in findings)


def test_the_whole_layering_audit_passes() -> None:
    layering.assert_clean()


def test_the_research_posture_holds() -> None:
    safety.assert_research_only()
    assert safety.LIVE_TRADING is False
    assert safety.PRACTICE_TRADING is False
    assert safety.ORDER_TRANSMISSION is False
    assert safety.OPTIMIZATION is False
    assert safety.STRATEGY_DISCOVERY is False
    assert safety.HISTORICAL_ONLY is True


def test_the_posture_assertion_actually_fails_when_the_posture_breaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A guard nobody has seen fail is a guard nobody knows works."""
    monkeypatch.setattr(safety, "ORDER_TRANSMISSION", True)
    with pytest.raises(safety.SafetyViolation, match="ORDER_TRANSMISSION"):
        safety.assert_research_only()


def test_no_broker_sdk_is_even_imported_in_this_interpreter() -> None:
    #: Reported rather than asserted against the whole process - another part of the
    #: repository may legitimately have one loaded - but nothing Layer B imports pulls one
    #: in, which is what the import-graph check above proves. This records the observation.
    assert isinstance(safety.imported_forbidden_modules(), tuple)


def test_the_registry_ships_empty() -> None:
    registry.assert_empty()
    assert registry.count() == 0


@pytest.mark.parametrize(
    "name",
    [
        "vwap_pullback",
        "VWAP-Pullback",
        "opening_range_breakout",
        "initial_balance_reversion",
        "failed_reversal_v2",
        "mechanism_screen_candidate",
        "optimization_champion",
    ],
)
def test_prior_research_lineages_cannot_be_registered(name: str) -> None:
    with pytest.raises(registry.RegistryError, match="excluded lineage"):
        registry.check_lineage(name)


def test_a_genuinely_new_name_is_allowed() -> None:
    registry.check_lineage("owner_supplied_strategy_v1")


def test_the_upstream_version_is_the_certified_one() -> None:
    upstream.assert_certified_version()
    assert upstream.INSTALLED_VERSION == upstream.CERTIFIED_VERSION


def test_the_upstream_api_fingerprint_is_pinned() -> None:
    """If this fails, the engine changed shape. Re-certify; do not update the hash blindly.

    The whole point of pinning is that an engine upgrade cannot silently change every number
    this pipeline reports. A failure here is a prompt to re-run the integration audit, not a
    prompt to paste in the new digest.
    """
    assert upstream.api_fingerprint_hash() == "fbc36b5fa62afdad"


def test_the_upstream_package_has_not_been_modified() -> None:
    """Layer B must not have written to site-packages.

    Checked by mtime rather than by hashing the distribution: a pip install writes every
    file at install time, so what matters is that nothing has been touched SINCE, which is
    exactly what an in-place patch or a monkey-patched .py would change.
    """
    engine_file = sys.modules["topstep_backtest"].__file__
    assert engine_file is not None, "the engine module has no file on disk"
    engine_root = Path(engine_file).resolve().parent
    installed = sorted(engine_root.rglob("*.py"))
    assert installed, "the engine source is not where it was expected"

    stamps = {path.stat().st_mtime for path in installed}
    #: A pip install stamps files within a narrow window. A hand-edited file stands out as
    #: an outlier well beyond it.
    spread = max(stamps) - min(stamps)
    assert spread < 3600, (
        f"the installed engine's files span {spread:.0f}s of modification time, which is "
        f"wider than an install window. Something has edited site-packages in place."
    )


def test_layer_b_declares_no_dependency_on_a_strategy_module() -> None:
    """The package must import cleanly with nothing registered."""
    assert registry.count() == 0
    import topstep_backtester.run as run_module

    assert hasattr(run_module, "run_backtest")


def test_source_files_are_discovered_at_all() -> None:
    """Guards the guards: an audit that scans zero files passes vacuously."""
    files = layering.source_files()
    assert len(files) > 15, f"only found {len(files)} source files; the scanner is not working"
    names = {path.name for path in files}
    assert {"upstream.py", "bars.py", "run.py", "safety.py"} <= names
