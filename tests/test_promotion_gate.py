"""The promotion gate: the code that decides what reaches a real account.

Part 12: "A strategy must not be promoted simply because a script says it won. The promotion
pipeline itself must be trustworthy." Before this file, `scripts/evaluate.py` had no tests at
all - and it is the single highest-consequence module in the repository, because everything
downstream of a promotion is real money on a paper account that is one owner decision from
being live.

The audit's AUD-10 is the proof that untested is not the same as correct: `--promote` wrote
`stats` and left `stats_by_spread` alone, so the next candidate was judged against the
*previous* champion's numbers - the book that had just lost. It never bit only because the
file happened to be hand-edited each time. The `stale_note` guard now catches it; these tests
exist so it stays caught, and so the other refusals (window, cost column, bias tag) do too.

Every test builds its own champion and run dicts. Nothing here reads or writes the real
`research/champion.json` or `research/experiments.jsonl`.
"""
from __future__ import annotations

import json

import evaluate as ev
import pytest

# --------------------------------------------------------------------------- fixtures

def champ_stats(car="20.0%", sharpe="0.90", dd="20.0%", orders="500"):
    return {
        "Total Orders": orders, "Compounding Annual Return": car,
        "Sharpe Ratio": sharpe, "Drawdown": dd, "Net Profit": "100%",
        "Probabilistic Sharpe Ratio": "40%", "Total Fees": "$1000",
    }


def champion(*, run_dir="results/s1/AAA", columns=None, criteria=None):
    """A champion whose cost columns are its own book unless a test says otherwise."""
    if columns is None:
        columns = {"0.0": {**champ_stats(), "run_dir": run_dir}}
    return {
        "algorithm": "s1_momo", "class": "S1", "run_dir": run_dir,
        "stats": champ_stats(),
        "stats_by_spread": columns,
        "criteria": {
            "min_trades": 30, "max_drawdown_limit": "35%",
            "must_beat": ["Compounding Annual Return"],
            "sharpe_tolerance": 0.03, "drawdown_tolerance_points": 1.0,
            **(criteria or {}),
        },
    }


def run(*, car="26.0%", sharpe="0.95", dd="20.0%", orders="500", tag="", env=None,
        ts="20260912T000000Z", run_dir="results/s1/BBB"):
    return {
        "ts": ts, "algorithm": "s1_momo", "class": "S1", "tag": tag,
        "run_dir": run_dir, "env": env or {"S1_SLIPPAGE_BPS": "0"},
        "stats": {
            "Total Orders": orders, "Compounding Annual Return": car,
            "Sharpe Ratio": sharpe, "Drawdown": dd, "Net Profit": "150%",
            "Probabilistic Sharpe Ratio": "45%", "Total Fees": "$1200",
        },
    }


# ------------------------------------------------------------------ the happy path

def test_a_clean_winner_beats_the_champion():
    ok, reasons = ev.verdict(run(), champion())
    assert ok, reasons


def test_the_baseline_is_actually_discriminating():
    """Guards the fixtures: if everything passed, the rest of this file proves nothing."""
    ok, _ = ev.verdict(run(car="19.0%"), champion())
    assert not ok


# ---------------------------------------------------------------- AUD-10, locked in

def test_stale_champion_columns_refuse_every_comparison():
    """The defect: columns describing the book that just lost."""
    champ = champion(run_dir="results/s1/NEW",
                     columns={"0.0": {**champ_stats(), "run_dir": "results/s1/OLD"}})
    ok, reasons = ev.verdict(run(), champ)
    assert not ok
    assert any("run_dir" in r or "column" in r.lower() or "stale" in r.lower()
               for r in reasons), reasons


def test_a_champion_whose_columns_are_its_own_book_is_not_flagged():
    assert ev.stale_note(champion()) in (None, "")


def test_a_second_cost_column_from_another_run_is_legitimate():
    """S-18's 2 bp column is a re-run of the same book at another spread, not staleness.

    The invariant is 'the champion appears in its own columns', not 'every column is the
    champion's run' - otherwise the cost-model machinery the repo depends on would be
    unusable.
    """
    champ = champion(columns={
        "0.0": {**champ_stats(), "run_dir": "results/s1/AAA"},
        "2.0": {**champ_stats(car="18.0%"), "run_dir": "results/s1/AAA-2bp"},
    })
    assert ev.stale_note(champ) in (None, "")


def test_promotion_leaves_the_champion_detectably_inconsistent_if_columns_are_not_rewritten():
    """End-to-end statement of AUD-10, so a future refactor cannot quietly reintroduce it.

    Simulates what `--promote` does to the dict, then asserts the guard fires. If someone
    later makes promote rewrite the columns properly, this test should be updated to assert
    the columns ARE rewritten - either way the invariant is under test.
    """
    champ = champion()
    winner = run(run_dir="results/s1/BBB")
    champ.update({"run_dir": winner["run_dir"], "stats": winner["stats"]})   # promote's write
    assert ev.stale_note(champ), "champion with foreign columns must be flagged"


# ------------------------------------------------------- cost model / axis refusals

def test_a_run_at_a_spread_the_champion_has_no_column_for_is_refused():
    """S-18: an unlabelled comparison is the defect, not the fallback."""
    ok, reasons = ev.verdict(run(env={"S1_SLIPPAGE_BPS": "2.0"}), champion())
    assert not ok
    assert any("spread" in r for r in reasons), reasons


def test_matching_cost_column_is_the_one_used():
    champ = champion(columns={
        "0.0": {**champ_stats(car="20.0%"), "run_dir": "results/s1/AAA"},
        "2.0": {**champ_stats(car="40.0%"), "run_dir": "results/s1/AAA-2bp"},
    })
    # 26% beats the 0.0 column's 20% but loses to the 2.0 column's 40%.
    ok, _ = ev.verdict(run(env={"S1_SLIPPAGE_BPS": "2.0"}), champ)
    assert not ok
    ok2, _ = ev.verdict(run(env={"S1_SLIPPAGE_BPS": "0"}), champ)
    assert ok2


def test_spread_key_parsing_is_robust():
    assert ev.spread_bps({"env": {"S1_SLIPPAGE_BPS": "2"}}) == "2.0"
    assert ev.spread_bps({"env": {}}) == "0.0"
    assert ev.spread_bps({}) == "0.0"
    assert ev.spread_bps({"env": {"S1_SLIPPAGE_BPS": "junk"}}) == "0.0"
    assert ev.spread_bps({"env": {"S1_SLIPPAGE_BPS": None}}) == "0.0"


def test_research_notes_are_never_mistaken_for_cost_columns():
    """`stats_by_spread` mixes numeric columns with dated prose notes (S-21..S-33).

    A note quoted as a comparison basis would be a silent catastrophe: prose parses to nan
    through `num()`, and `nan > nan` is False, so every metric would 'fail to beat'.
    """
    champ = champion()
    champ["stats_by_spread"]["risk_note"] = "S-28: prose about the champion, not a book"
    champ["stats_by_spread"]["leg_note"] = "S-25: more prose"
    cols = ev.cost_columns(champ)
    assert set(cols) == {"0.0"}


# ------------------------------------------------ window / train-test boundary refusals

def test_a_moved_backtest_window_is_refused():
    """F-3: a two-month diagnostic annualised to 47.3% CAR and passed every rule."""
    ok, reasons = ev.verdict(
        run(env={"S1_SLIPPAGE_BPS": "0", "S1_START": "2024-01-01"}), champion())
    assert not ok
    assert any("window" in r for r in reasons), reasons


def test_both_window_bounds_are_caught():
    for key in ("S1_START", "S1_END"):
        ok, reasons = ev.verdict(
            run(env={"S1_SLIPPAGE_BPS": "0", key: "2020-01-01"}), champion())
        assert not ok and any("window" in r for r in reasons)


# ------------------------------------------------------ leakage / bias refusals

def test_a_run_tagged_not_promotable_can_never_win():
    """S-7: a survivorship-biased sleeve scores 43.9% CAR and passes every statistical rule.

    No statistic can see a bias built into the universe, so the tag is the only defence and
    it must be unconditional.
    """
    ok, reasons = ev.verdict(
        run(car="43.9%", sharpe="1.19", dd="32.2%", tag="S-7 wide sleeve, NOT PROMOTABLE"),
        champion())
    assert not ok
    assert any("not promotable" in r.lower() for r in reasons)


def test_the_bias_tag_is_case_insensitive():
    for tag in ("not promotable", "NOT PROMOTABLE", "Not Promotable"):
        ok, _ = ev.verdict(run(car="99.0%", tag=tag), champion())
        assert not ok, tag


# ------------------------------------------------------------ the statistical criteria

def test_minimum_trade_count_is_enforced():
    ok, reasons = ev.verdict(run(orders="29"), champion())
    assert not ok and any("orders" in r for r in reasons)


def test_trade_count_boundary_is_inclusive_at_the_minimum():
    assert ev.verdict(run(orders="30"), champion())[0]
    assert not ev.verdict(run(orders="29"), champion())[0]


def test_absolute_drawdown_ceiling_is_enforced():
    ok, reasons = ev.verdict(run(dd="36.0%"), champion())
    assert not ok and any("drawdown" in r for r in reasons)


def test_drawdown_tolerance_relative_to_champion_is_enforced():
    """20% champion + 1.0 point tolerance: 21.5% is worse, 20.5% is allowed."""
    assert not ev.verdict(run(dd="21.5%"), champion())[0]
    assert ev.verdict(run(dd="20.5%"), champion())[0]


def test_sharpe_tolerance_lets_return_win_but_only_within_the_stated_band():
    """Owner decision 2026-09-09, return-first: give up <=0.03 Sharpe for more CAR."""
    assert ev.verdict(run(car="26.0%", sharpe="0.88"), champion())[0]      # -0.02
    assert not ev.verdict(run(car="26.0%", sharpe="0.80"), champion())[0]  # -0.10


def test_must_beat_metric_requires_strictly_greater_not_equal():
    ok, _ = ev.verdict(run(car="20.0%"), champion())
    assert not ok, "a tie is not a win"


def test_every_failing_reason_is_reported_not_just_the_first():
    ok, reasons = ev.verdict(run(car="10.0%", orders="5", dd="40.0%"), champion())
    assert not ok
    assert len(reasons) >= 3, reasons


# ------------------------------------------------------------------- stat parsing

@pytest.mark.parametrize("raw,want", [
    ("12.5%", 12.5), ("$3.44", 3.44), ("-0.005", -0.005), ("1,234", 1234.0),
    ("0", 0.0), ("-12.5%", -12.5),
])
def test_num_parses_lean_stat_strings(raw, want):
    assert ev.num(raw) == pytest.approx(want)


def test_num_is_nan_only_when_there_is_no_digit_anywhere():
    import math
    assert math.isnan(ev.num(None))
    assert math.isnan(ev.num("prose with no digits"))
    assert math.isnan(ev.num(""))
    # The property that matters where nan does occur: it can never win a comparison.
    assert not (ev.num(None) > 0)
    assert not (ev.num("prose") > ev.num("prose"))


def test_num_extracts_the_first_number_from_any_string_which_is_a_latent_hazard():
    """`num()` is permissive: it finds the first number ANYWHERE, it does not require the
    string to be one. So a dated research note parses to a number rather than to nan:

        num("S-28: prose about the champion")  ->  -28.0

    That is currently harmless because no prose reaches `num()` as a comparison basis - the
    `stats_by_spread` notes are filtered out by `cost_columns()` before any metric lookup,
    which the test below pins. It is recorded here because the safety is entirely in the
    caller: any future path that reads a `*_note` value, or a LEAN stat that ever contains a
    hyphenated identifier, would compare against a silently fabricated number instead of
    failing. Left as-is deliberately rather than tightened - `num()` is shared with the
    daily track's tooling and changing its parsing could move existing results.
    """
    assert ev.num("S-28: prose about the champion") == -28.0
    assert ev.num("run 20260912T000000Z") == 20260912.0


def test_the_actual_protection_is_cost_columns_not_num():
    """Belt-and-braces on the hazard above: notes never become a comparison basis."""
    champ = champion()
    champ["stats_by_spread"]["risk_note"] = "S-28: prose"
    stats, _ = ev.champion_stats(run(), champ)
    assert stats.get("Compounding Annual Return") == "20.0%"   # the column, not the note


# ------------------------------------------------------------- experiment registration

def test_ledger_rows_round_trip_as_jsonl(tmp_path, monkeypatch):
    ledger = tmp_path / "experiments.jsonl"
    rows = [run(ts="20260101T000000Z"), run(ts="20260102T000000Z")]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(ev, "LEDGER", ledger)
    assert [r["ts"] for r in ev.load_runs()] == ["20260101T000000Z", "20260102T000000Z"]


def test_blank_lines_in_the_ledger_are_tolerated(tmp_path, monkeypatch):
    """The ledger is appended to by many concurrent processes; a stray newline must not
    break every downstream reader."""
    ledger = tmp_path / "experiments.jsonl"
    ledger.write_text(json.dumps(run()) + "\n\n\n", encoding="utf-8")
    monkeypatch.setattr(ev, "LEDGER", ledger)
    assert len(ev.load_runs()) == 1


def test_a_missing_ledger_is_empty_not_an_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "LEDGER", tmp_path / "nope.jsonl")
    assert ev.load_runs() == []


# --------------------------------------------------------------- champion integrity

def test_a_champion_with_no_columns_falls_back_to_headline_stats():
    champ = champion(columns={})
    champ.pop("stats_by_spread")
    stats, note = ev.champion_stats(run(), champ)
    assert stats and not note


def test_missing_champion_file_yields_an_empty_but_valid_champion(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "CHAMPION", tmp_path / "nope.json")
    c = ev.load_champion()
    assert c == {"stats": {}, "criteria": {}}
    # And an empty champion must not silently promote everything.
    ok, _ = ev.verdict(run(orders="5"), c)
    assert not ok
