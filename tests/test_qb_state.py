"""State scoping: a simulation must be structurally unable to write the live files.

Part 19 asks for this "enforced architecturally, not merely by naming files differently".
So the tests are about what is *impossible*, not about what is discouraged - a store built
for a dry run has no reachable path into the live directory, and every attempt to construct
one raises.

The regression these guard is AUD-04, which is live on disk right now: seven `--mock` /
`--dry-run` runs wrote `MockAccount.net_liq = 100_000` into `live/state/last_run.json`,
including the equity curve the drawdown breaker reads.
"""
from __future__ import annotations

import dataclasses

import pytest

from quant_brain.core.state import (
    StateScope,
    StateScopeError,
    StateStore,
    is_contaminated,
    root_for,
    scope_of,
)


@pytest.fixture
def base(tmp_path):
    return tmp_path / "state"


# ------------------------------------------------------- the separation is real, not naming

def test_simulated_scopes_get_different_roots_from_the_real_one(base):
    live = StateStore.open(StateScope.PAPER, base=base)
    dry = StateStore.open(StateScope.DRYRUN, base=base)
    research = StateStore.open(StateScope.RESEARCH, base=base)
    roots = {live.root, dry.root, research.root}
    assert len(roots) == 3
    assert live.root not in (dry.root, research.root)


def test_a_dry_run_write_cannot_land_on_the_live_file(base):
    """The AUD-04 scenario, run through the new machinery."""
    live = StateStore.open(StateScope.PAPER, base=base)
    dry = StateStore.open(StateScope.DRYRUN, base=base)

    live.write_json("last_run.json", {"equity": 250_000.0, "source": "real"})
    dry.write_json("last_run.json", {"equity": 100_000.0, "source": "MockAccount"})

    assert live.read_json("last_run.json")["equity"] == 250_000.0   # untouched
    assert dry.read_json("last_run.json")["equity"] == 100_000.0
    assert live.path("last_run.json") != dry.path("last_run.json")


def test_path_traversal_out_of_a_simulated_scope_raises(base):
    dry = StateStore.open(StateScope.DRYRUN, base=base)
    for escape in ("../last_run.json", "../../last_run.json", "a/../../last_run.json"):
        with pytest.raises(StateScopeError):
            dry.path(escape)


def test_absolute_paths_are_refused(base):
    dry = StateStore.open(StateScope.DRYRUN, base=base)
    with pytest.raises(StateScopeError):
        dry.path(str(base / "last_run.json"))


def test_nested_names_within_the_scope_are_allowed(base):
    dry = StateStore.open(StateScope.DRYRUN, base=base)
    p = dry.path("sub/dir/file.json")
    assert p.is_relative_to(dry.root)


def test_a_store_cannot_change_its_own_scope(base):
    """Frozen: code handed a DRYRUN store cannot promote itself.

    FrozenInstanceError specifically, not a blind Exception - asserting on `Exception` would
    also pass if the attribute name were simply wrong, which would test nothing.
    """
    dry = StateStore.open(StateScope.DRYRUN, base=base)
    with pytest.raises(dataclasses.FrozenInstanceError):
        dry.scope = StateScope.PAPER          # type: ignore[misc]


# ----------------------------------------------------- flag derivation cannot fail open

@pytest.mark.parametrize("flags,expected", [
    ({}, StateScope.PAPER),
    ({"dry_run": True}, StateScope.DRYRUN),
    ({"mock": True}, StateScope.RESEARCH),
    ({"backtest": True}, StateScope.BACKTEST),
    ({"research": True}, StateScope.RESEARCH),
    # Combinations must resolve to the LEAST privileged scope, never to PAPER.
    ({"mock": True, "dry_run": True}, StateScope.RESEARCH),
    ({"backtest": True, "dry_run": True}, StateScope.BACKTEST),
    ({"mock": True, "backtest": True, "dry_run": True}, StateScope.RESEARCH),
])
def test_scope_derivation(flags, expected):
    assert StateScope.for_run(**flags) is expected


def test_only_the_no_flags_case_reaches_a_real_scope():
    """The property that matters: you cannot accidentally get PAPER."""
    for flags in ({"mock": True}, {"dry_run": True}, {"backtest": True}, {"research": True}):
        assert not StateScope.for_run(**flags).is_real


def test_is_real_is_true_only_for_live_and_paper():
    assert StateScope.LIVE.is_real and StateScope.PAPER.is_real
    assert not any(s.is_real for s in
                   (StateScope.DRYRUN, StateScope.BACKTEST, StateScope.RESEARCH))


# --------------------------------------------------------------------- scope stamping

def test_writes_are_stamped_with_their_scope(base):
    dry = StateStore.open(StateScope.DRYRUN, base=base)
    dry.write_json("s.json", {"equity": 1.0})
    assert scope_of(dry.read_json("s.json")) is StateScope.DRYRUN


def test_jsonl_records_are_stamped_too(base):
    import json
    research = StateStore.open(StateScope.RESEARCH, base=base)
    research.append_jsonl("nav.jsonl", {"nav": 1.0})
    research.append_jsonl("nav.jsonl", {"nav": 2.0})
    lines = research.path("nav.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert all(json.loads(x)["_scope"] == "research" for x in lines)


def test_scope_of_tolerates_unstamped_and_junk_documents():
    assert scope_of({"equity": 1}) is None
    assert scope_of({"_scope": "nonsense"}) is None
    assert scope_of("not a dict") is None
    assert scope_of(None) is None


# ------------------------------------------------- detecting the file that is wrong today

def test_the_currently_deployed_file_shape_is_detected_as_contaminated():
    """Verbatim shape of live/state/last_run.json as of 2026-09-12.

    No `_scope` stamp - it predates this module - so detection has to rest on the legacy
    `dry_run` flag that `paper_trade.save_state` already writes into the file it corrupts.
    """
    deployed = {
        "equity": 100000.0, "equity_high": 100000.0,
        "equity_curve": [100000.0, 100000.0, 100000.0, 100000.0],
        "signal": "s1_momo", "as_of": "2026-09-10",
        "ran_at": "2026-09-11T22:06:32+00:00", "dry_run": True,
    }
    assert is_contaminated(deployed)


def test_a_genuine_paper_run_is_not_flagged():
    assert not is_contaminated({"equity": 250_000.0, "dry_run": False, "_scope": "paper"})
    assert not is_contaminated({"equity": 250_000.0})          # unstamped but not a dry run


def test_a_stamped_simulation_in_a_real_location_is_flagged():
    assert is_contaminated({"equity": 100_000.0, "_scope": "research"})
    assert is_contaminated({"equity": 100_000.0, "_scope": "backtest"})


def test_is_contaminated_tolerates_non_dict_input():
    assert not is_contaminated(None)
    assert not is_contaminated("string")


# ------------------------------------------------------------------------- read paths

def test_missing_and_corrupt_documents_return_the_default(base):
    store = StateStore.open(StateScope.RESEARCH, base=base)
    assert store.read_json("nope.json", default={"d": 1}) == {"d": 1}
    store.path("bad.json").write_text("{not json", encoding="utf-8")
    assert store.read_json("bad.json", default={"d": 2}) == {"d": 2}


def test_live_and_paper_share_a_root_deliberately(base):
    """Documented choice: 'live' here IS an IBKR paper account. Separate members so the
    split is a one-line change when a funded account appears."""
    assert root_for(StateScope.LIVE, base=base) == root_for(StateScope.PAPER, base=base)
