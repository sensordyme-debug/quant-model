"""The "have we already tried this?" index.

AGENTS.md tells the loop not to repeat a run that is already in the ledger. With 735 rows
and a 307 KB backlog, and retrieval that is positional ("the last 20 lines"), that
instruction is not mechanically satisfiable - six concurrent tracks each reading only the
tail is a duplicate-work generator.

These tests use synthetic corpora so they do not drift when the real ledger grows, plus two
that run against the real files to prove the loaders cope with what is actually on disk.
"""
from __future__ import annotations

import json

import pytest

from quant_brain.core.knowledge import (
    Entry,
    KnowledgeIndex,
    load_backlog,
    load_experiments,
    tokenize,
)


def entry(title, kind="experiment", track="", outcome="", detail=""):
    return Entry(doc_id=title[:12], kind=kind, title=title, track=track,
                 outcome=outcome, detail=detail)


@pytest.fixture
def corpus():
    return KnowledgeIndex([
        entry("A-2 30-minute opening range breakout on leveraged ETFs", track="A"),
        entry("S-18 momentum rotation, unlevered book, drawdown overlay off", track="S"),
        entry("O-3 0DTE SPY variance risk premium, closed at the quote", track="O"),
        entry("F-1 supervised intraday forecaster, gradient boosted trees", track="F"),
        entry("L-1 leveraged ETF intraday mean reversion", track="L"),
    ])


# ------------------------------------------------------------------ it actually retrieves

def test_finds_the_prior_run_for_a_restated_idea(corpus):
    hits = corpus.search("opening range breakout on leveraged ETFs")
    assert hits and hits[0].entry.track == "A"


def test_ranks_the_right_track_first_for_each_topic(corpus):
    for query, track in [
        ("0DTE variance risk premium options", "O"),
        ("machine learning forecaster boosted trees", "F"),
        ("momentum rotation drawdown", "S"),
    ]:
        hits = corpus.search(query)
        assert hits, query
        assert hits[0].entry.track == track, f"{query} -> {hits[0].entry.title}"


def test_trigrams_bridge_the_repos_own_synonyms(corpus):
    """'reversion' and 'revert', 'momentum' and 'momo' are both used for the same ideas."""
    assert corpus.search("mean revert")
    assert any("L-1" in h.entry.title for h in corpus.search("leveraged ETF reversion"))


def test_scores_are_ordered_and_bounded(corpus):
    hits = corpus.search("leveraged ETF")
    assert hits == sorted(hits, key=lambda h: h.score, reverse=True)
    assert all(0.0 < h.score <= 1.0001 for h in hits)


def test_k_limits_the_result_count(corpus):
    assert len(corpus.search("ETF momentum options", k=2)) <= 2


def test_kind_filter(corpus):
    assert corpus.search("breakout", kinds=("backlog",)) == []
    assert corpus.search("breakout", kinds=("experiment",))


def test_unrelated_query_returns_nothing_rather_than_noise(corpus):
    assert corpus.search("sourdough bread proofing schedule") == []


def test_already_tried_applies_a_threshold(corpus):
    assert corpus.already_tried("30-minute opening range breakout leveraged ETFs")
    assert not corpus.already_tried("cocoa futures seasonality")


# ------------------------------------------------------------------------ degenerate input

def test_empty_index_and_empty_query_are_safe():
    assert KnowledgeIndex([]).search("anything") == []
    assert KnowledgeIndex([entry("x y z")]).search("") == []
    assert KnowledgeIndex([entry("x y z")]).search("the and of") == []


def test_stopwords_alone_do_not_match_everything():
    idx = KnowledgeIndex([entry("the momentum of the book"), entry("a reversal in the tape")])
    assert idx.search("the and of a") == []


def test_tokenize_drops_stopwords_and_emits_trigrams():
    toks = tokenize("The momentum of SPY")
    assert "momentum" in toks and "spy" in toks
    assert "the" not in toks and "of" not in toks
    assert "#mom" in toks                     # trigram from the long token
    assert not any(t.startswith("#sp") for t in toks)   # too short for trigrams


# --------------------------------------------------------------------------- loaders

def test_experiment_loader_survives_a_partial_line(tmp_path):
    """The ledger is appended by concurrent processes; a torn write must not kill the index."""
    p = tmp_path / "experiments.jsonl"
    good = json.dumps({"ts": "20260912T120000Z", "tag": "S-1 momentum",
                       "algorithm": "s1_momo", "track": "S",
                       "stats": {"Sharpe Ratio": "0.99"}})
    p.write_text(good + "\n{ partial write\n" + good + "\n\n", encoding="utf-8")
    entries = load_experiments(p)
    assert len(entries) == 2
    assert entries[0].date == "2026-09-12"
    assert "Sharpe" in entries[0].outcome


def test_experiment_loader_on_a_missing_file():
    assert load_experiments(__import__("pathlib").Path("nope.jsonl")) == []


def test_backlog_loader_distinguishes_done_from_open(tmp_path):
    p = tmp_path / "backlog.md"
    p.write_text(
        "## Open (highest value first)\n"
        "### S-40 Try a new thing\n"
        "## Done\n"
        "### S-2 Opening-range breakout\n"
        "- **F-2** Index futures track\n",
        encoding="utf-8")
    entries = {e.title.split()[0]: e for e in load_backlog(p)}
    assert entries["S-40"].outcome == "open"
    assert entries["S-2"].outcome == "done"
    assert entries["F-2"].outcome == "done"
    assert entries["S-2"].track == "S"


def test_backlog_loader_ignores_prose_lines(tmp_path):
    p = tmp_path / "backlog.md"
    p.write_text("## Done\nSome prose that mentions S-2 but is not an item.\n### S-2 Real\n",
                 encoding="utf-8")
    assert [e.title for e in load_backlog(p)] == ["S-2 Real"]


# ----------------------------------------------------- against the repository as it stands

def test_the_real_corpus_loads_and_is_substantial():
    idx = KnowledgeIndex.load()
    assert len(idx.entries) > 200, "the real ledger and backlog should produce many entries"
    assert {e.kind for e in idx.entries} >= {"experiment", "backlog"}


def test_a_known_completed_line_of_work_is_findable_in_the_real_corpus():
    """O-3 concluded the 0DTE variance risk premium is not conditional. Asking again should
    surface it rather than returning nothing."""
    hits = KnowledgeIndex.load().search("0DTE SPY variance risk premium options", k=5)
    assert hits
    assert any("O-3" in h.entry.title or h.entry.track == "options" for h in hits)
