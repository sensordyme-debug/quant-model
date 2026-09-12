"""AUD-10 / S-34: what a PROMOTION writes - the writer half of the promotion gate.

`tests/test_promotion_gate.py` (`eng`, same day) covers the reader: `stale_note()` flagging a
champion whose columns are not its own book, `cost_columns()` keeping the research notes out of
a metric lookup. It does not touch `promoted_columns()` or the `--promote` write path, which is
where the defect actually lived, so this file is the other half and deliberately does not repeat
the reader-side cases.

The defect: `--promote` wrote `stats` and never touched `stats_by_spread`, which
`champion_stats()` prefers - so the first candidate judged after a promotion was compared
against the book that had just lost. S-34 priced it on the real S-12 -> S-18 promotion. The CAR
column is harmless (-0.001 at 0 bp, the dead heat S-18 itself reported); the damage is
**+4.2 points of drawdown headroom at the 2 bp column** against a `drawdown_tolerance_points`
of 1.0, and **15 of the 167 `s1_momo` ledger rows flip to "beats" because of it, all 15 in the
dangerous direction**.

It never bit in production because the file was hand-edited after each of this repository's two
promotions. These tests are that habit written down, which is the only form of it that survives
a session with no memory of why.
"""
from __future__ import annotations

import json

import evaluate as ev
import pytest

CHAMPION_STATS = {"Total Orders": "5128", "Compounding Annual Return": "24.403%",
                  "Sharpe Ratio": "0.994", "Drawdown": "23.700%"}
RETIRED_STATS = {"Total Orders": "4735", "Compounding Annual Return": "24.404%",
                 "Sharpe Ratio": "0.921", "Drawdown": "25.100%"}


@pytest.fixture
def champion():
    """A champion file with the two shapes that matter: a cost column and a research note."""
    return {
        "algorithm": "s1_momo", "class": "S1MomentumRotationAlgorithm",
        "run_dir": r"results\s1_momo\NEW", "commit": "d41aefe",
        "stats": dict(CHAMPION_STATS),
        "stats_by_spread": {
            "0.0": dict(CHAMPION_STATS, run_dir=r"results\s1_momo\NEW"),
            "2.0": {"Compounding Annual Return": "23.068%", "Sharpe Ratio": "0.938",
                    "Drawdown": "25.000%", "run_dir": r"results\s1_momo\NEW2BP"},
            "leg_note": "S-25: prose about the champion, not a book.",
        },
        "criteria": {"min_trades": 30, "must_beat": ["Compounding Annual Return"],
                     "sharpe_tolerance": 0.03, "drawdown_tolerance_points": 1.0,
                     "max_drawdown_limit": "35%"},
    }


def run(ts="20260912T000000Z", stats=None, env=None, run_dir=r"results\s1_momo\CAND"):
    return {"ts": ts, "algorithm": "s1_momo", "class": "S1MomentumRotationAlgorithm",
            "run_dir": run_dir, "commit": "abc1234", "tag": "candidate",
            "env": env, "stats": stats or dict(CHAMPION_STATS)}


# --- what a promotion writes ------------------------------------------------------------

def test_promotion_retires_the_previous_columns(champion):
    """The retired book's columns must not survive the promotion - that is the whole defect."""
    cols = ev.promoted_columns(run(env={"S1_SLIPPAGE_BPS": "2"}), champion)
    assert sorted(k for k in cols if ev.COLUMN_KEY.match(k)) == ["2.0"]
    assert cols["2.0"]["run_dir"] == r"results\s1_momo\CAND"


def test_promotion_keeps_the_research_notes(champion):
    """The audit's one-line fix was "delete the others", which destroys 11 dated notes."""
    before = {k: v for k, v in champion["stats_by_spread"].items() if not ev.COLUMN_KEY.match(k)}
    cols = ev.promoted_columns(run(), champion)
    assert {k: v for k, v in cols.items() if not ev.COLUMN_KEY.match(k)} == before


def test_promoted_champion_is_self_consistent_and_judges_its_own_spread(champion):
    cand = run(env={"S1_SLIPPAGE_BPS": "2"})
    promoted = dict(champion, run_dir=cand["run_dir"], stats=cand["stats"],
                    stats_by_spread=ev.promoted_columns(cand, champion))
    assert ev.stale_note(promoted) is None
    seen, note = ev.champion_stats(cand, promoted)
    assert note is None and seen["run_dir"] == cand["run_dir"]


def test_promoted_champion_refuses_a_candidate_at_an_unpriced_spread(champion):
    """S-18's rule survives the rewrite: refuse rather than judge at the wrong cost model."""
    cand = run(env={"S1_SLIPPAGE_BPS": "2"})
    promoted = dict(champion, run_dir=cand["run_dir"], stats=cand["stats"],
                    stats_by_spread=ev.promoted_columns(cand, champion))
    _, note = ev.champion_stats(run(ts="20260912T010000Z"), promoted)   # 0 bp, no column
    assert note and "not comparable" in note


def test_the_refusal_message_lists_columns_and_not_notes(champion):
    """It used to print all thirteen keys, so `leg_note` read as a cost model."""
    _, note = ev.champion_stats(run(env={"S1_SLIPPAGE_BPS": "5"}), champion)
    assert note and "['0.0', '2.0']" in note and "leg_note" not in note


def test_a_champion_with_no_columns_at_all_still_promotes(champion):
    """Backward compatibility: a pre-S-18 champion file has no `stats_by_spread`."""
    champion.pop("stats_by_spread")
    cols = ev.promoted_columns(run(), champion)
    assert sorted(cols) == ["0.0"] and cols["0.0"]["run_dir"] == r"results\s1_momo\CAND"


# --- the defect itself, as a regression ---------------------------------------------------

def test_the_retired_column_would_have_promoted_a_worse_drawdown(champion):
    """The 4.2 points of slack S-34 measured, as a single real candidate.

    26.474% CAR at DD 25.700% is a real ledger row (`20260911T120010Z`, S-16 budget 0.80) and
    one of the 15 that flip. It clears the retired book's 25.100 + 1.0 ceiling and breaches the
    champion's 23.700 + 1.0 - and it beats both on CAR, so `must_beat` never sees the problem.
    """
    cand = run(stats={"Total Orders": "5219", "Compounding Annual Return": "26.474%",
                      "Sharpe Ratio": "1.012", "Drawdown": "25.700%"})
    assert not ev.verdict(cand, champion)[0]

    stale = json.loads(json.dumps(champion))
    stale["run_dir"] = r"results\s1_momo\PROMOTED"
    stale["stats_by_spread"]["0.0"] = dict(RETIRED_STATS, run_dir=r"results\s1_momo\OLD")
    ok_stale, reasons = ev.verdict(cand, stale)
    assert not ok_stale and any("AUD-10" in r for r in reasons), (
        "the guard is the only thing standing between this candidate and a promotion")


# --- end to end, through main() -------------------------------------------------------------

def test_promote_writes_a_self_consistent_file_and_the_next_candidate_is_judged_on_it(
        champion, tmp_path, monkeypatch, capsys):
    """The defect lived in `main()`, not in a helper, so the write path is tested for real.

    Two candidates in sequence: the first is promoted, then the second - which beats the RETIRED
    champion on drawdown and loses to the promoted one - must be refused. Under the old code it
    was promoted, because `stats_by_spread` still described the book it had just beaten.
    """
    winner = run(ts="20260912T100000Z", run_dir=r"results\s1_momo\WIN",
                 stats={"Total Orders": "5200", "Compounding Annual Return": "26.000%",
                        "Sharpe Ratio": "1.010", "Drawdown": "22.000%"})
    follower = run(ts="20260912T110000Z", run_dir=r"results\s1_momo\FOLLOW",
                   stats={"Total Orders": "5200", "Compounding Annual Return": "25.000%",
                          "Sharpe Ratio": "0.999", "Drawdown": "24.500%"})
    ledger = tmp_path / "experiments.jsonl"
    ledger.write_text("".join(json.dumps(r) + "\n" for r in (winner, follower)), encoding="utf-8")
    champ_file = tmp_path / "champion.json"
    champ_file.write_text(json.dumps(champion), encoding="utf-8")
    monkeypatch.setattr(ev, "LEDGER", ledger)
    monkeypatch.setattr(ev, "CHAMPION", champ_file)

    monkeypatch.setattr("sys.argv", ["evaluate.py", "--promote", winner["ts"]])
    assert ev.main() == 0
    written = json.loads(champ_file.read_text(encoding="utf-8"))
    assert written["run_dir"] == winner["run_dir"]
    assert sorted(ev.cost_columns(written)) == ["0.0"]
    assert written["stats_by_spread"]["0.0"]["run_dir"] == winner["run_dir"]
    assert written["stats_by_spread"]["leg_note"] == champion["stats_by_spread"]["leg_note"]
    assert ev.stale_note(written) is None
    assert written["criteria"] == champion["criteria"]

    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["evaluate.py", "--candidate", follower["ts"]])
    assert ev.main() == 1, "the follower beats the retired champion and loses to the new one"
    out = capsys.readouterr().out
    assert "26.000%" in out and "does NOT beat" in out
