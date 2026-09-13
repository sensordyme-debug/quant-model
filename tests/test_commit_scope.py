"""E-12 / C-10: the pre-commit scope gate.

Deliberately **not** in `conftest.RUNNER_TESTS`. E-8's asymmetry decides the tier: a test may
stop the 09:25 sleeve only when its failure means the arithmetic the trader is about to use is
provably wrong. A commit hook says nothing about the book, so a broken one must not be able to
cost the sleeve a trading day.

Three tiers here, and the last two are what stop the file being vacuous:

1. `check()` on the two facts the hook reads - the rules, with no repository.
2. A **control on git's own behaviour**: rule 1 rests entirely on git preparing a partial
   commit in a `next-index-*` file, which is observed behaviour, not documented API. If a git
   upgrade renamed it, every assertion in tier 1 would still pass while the deployed hook
   refused every commit in the repo. So the shape is re-measured against real git here.
3. The **race itself**, reproduced: a concurrent `git add` between one agent's `git add` and
   its `git commit`, which is the exact mechanism behind all six cross-track commits.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from commit_scope import check, journal_owner, names_its_paths  # noqa: I001 (conftest: sys.path)

REPO = Path(__file__).resolve().parents[1]
SCOPE_SCRIPT = REPO / "scripts" / "commit_scope.py"
HOOK = REPO / ".githooks" / "pre-commit"

TEMP_INDEX = ".git/next-index-12345.lock"   # what git hands a partial commit
SHARED_INDEX = ".git/index"                 # what git hands everything else


# --------------------------------------------------------------------------- tier 1: rules

def test_a_pathspec_commit_is_allowed():
    ok, lines = check(TEMP_INDEX, ["research/journal_eng.md"])
    assert ok and lines == []


@pytest.mark.parametrize("index_file", [SHARED_INDEX, ".git/index.lock", None, ""])
def test_a_shared_index_commit_is_refused(index_file):
    """`git commit`, `git commit -am`, `--include` and `--amend` all commit the index."""
    ok, lines = check(index_file, ["scripts/intraday_common.py"])
    assert not ok
    assert "SHARED INDEX" in lines[0]


def test_the_refusal_prints_a_command_that_would_work():
    """A refusal that does not say what to type instead gets answered with --no-verify."""
    ok, lines = check(SHARED_INDEX, ["scripts/a.py", "research/journal_eng.md"])
    assert not ok
    suggestion = next(ln for ln in lines if "git commit -m" in ln).strip()
    # -m before --, because everything after -- is a path.
    assert suggestion.index("-m") < suggestion.index(" -- ")
    assert suggestion.endswith("scripts/a.py research/journal_eng.md")
    # and it names every path that would land, so nothing is silently dropped
    assert all(p in suggestion for p in ("scripts/a.py", "research/journal_eng.md"))


def test_an_empty_commit_is_not_refused():
    """`--amend` with nothing staged cannot take another track's file."""
    assert check(SHARED_INDEX, []) == (True, [])


def test_a_path_with_a_space_is_quoted_in_the_suggestion():
    ok, lines = check(SHARED_INDEX, ["research/a file.md"])
    assert not ok
    assert '"research/a file.md"' in next(ln for ln in lines if "git commit -m" in ln)


# ------------------------------------------------------------------- tier 1: journal owners

@pytest.mark.parametrize(("path", "owner"), [
    ("research/journal_eng.md", "eng"),
    ("research/journal_critic.md", "critic"),
    ("research/journal_futures.md", "futures"),
    ("research/journal.md", "daily/iterate"),
    ("research/journal_daily.md", "daily/iterate"),
    ("scripts/intraday_common.py", None),
    ("research/backlog.md", None),
    ("research/journal_eng.md.bak", None),
])
def test_journal_owner(path, owner):
    assert journal_owner(path) == owner


def test_the_daily_pair_is_one_owner_not_two():
    """The correction to C-10 as filed.

    C-10 asked for "refuses a commit whose staged set spans more than one track's journal
    file". Run as written over all 219 commits that fires 14 times and 12 are this pair -
    AGENTS.md makes `research/journal.md` the `daily`/`iterate` history AND the daily review's
    merge target, so `daily` writes both routinely. With the pair counted once: 2 of 219, both
    true positives (861c70a, 3a7b764).
    """
    ok, _ = check(TEMP_INDEX, ["research/journal.md", "research/journal_daily.md",
                               "research/backlog.md"])
    assert ok


def test_two_tracks_journals_are_refused():
    ok, lines = check(TEMP_INDEX, ["research/journal_critic.md", "research/journal_futures.md"])
    assert not ok
    assert "critic" in lines[0] and "futures" in lines[0]


def test_the_journal_rule_does_not_fire_on_a_shared_file():
    """backlog.md and experiments.jsonl are shared by construction; they own nothing."""
    ok, _ = check(TEMP_INDEX, ["research/backlog.md", "research/experiments.jsonl",
                               "research/journal_eng.md"])
    assert ok


# ------------------------------------------------------- tier 2: control on git's own behaviour

def _git(cwd, *args, **kw):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                          check=False, **kw)


@pytest.fixture
def scratch(tmp_path):
    """A real repository whose pre-commit hook is the real `commit_scope.py`.

    Not the repo's own hook file: that also runs the `qb_check` completion gate, which has
    nothing to measure in a two-file scratch tree. `test_the_deployed_hook_runs_the_scope_gate`
    covers the wiring of the real file.
    """
    repo = tmp_path / "scratch"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "eng@test")
    _git(repo, "config", "user.name", "eng")
    hooks = repo / ".githooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{SCOPE_SCRIPT}"\n'.replace("\\", "/"),
        encoding="utf-8", newline="\n",
    )
    hook.chmod(0o755)
    _git(repo, "config", "core.hooksPath", ".githooks")
    (repo / "mine.txt").write_text("base\n", encoding="utf-8")
    (repo / "theirs.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "mine.txt", "theirs.txt")
    _git(repo, "commit", "-qm", "base", "--no-verify")
    return repo


def test_git_still_prepares_partial_commits_in_a_next_index_file(scratch):
    """The control. Rule 1 is only as true as this observed git behaviour.

    Without it a git upgrade that renamed the temporary index would leave every other test in
    this file green while the deployed hook refused every commit in the repo.
    """
    probe = scratch / ".githooks" / "pre-commit"
    probe.write_text('#!/bin/sh\necho "IDX=[${GIT_INDEX_FILE}]"\n',
                     encoding="utf-8", newline="\n")
    (scratch / "mine.txt").write_text("changed\n", encoding="utf-8")

    # git forwards hook output to its own stderr, so read both streams.
    def idx(proc):
        both = proc.stdout + proc.stderr
        assert "IDX=[" in both, both
        return both.split("IDX=[")[1].split("]")[0]

    named = idx(_git(scratch, "commit", "-m", "p", "--", "mine.txt"))
    assert Path(named).name.startswith("next-index-"), named
    assert names_its_paths(named), "the discriminator must accept what git actually emits"

    (scratch / "mine.txt").write_text("again\n", encoding="utf-8")
    _git(scratch, "add", "mine.txt")
    shared = idx(_git(scratch, "commit", "-m", "q"))
    assert not names_its_paths(shared), shared


def test_the_race_that_produced_six_cross_track_commits_is_refused(scratch):
    """C-10's mechanism, reproduced rather than argued.

    Agent A stages its file; agent B's `git add` lands before A's `git commit`; A's commit
    with no pathspec takes both. This is 11f0308, in which a memory-dreaming cron committed
    `scripts/intraday_common.py` - a file `intraday_trader.py` imports - under the message
    "vcjikyftr", 97 minutes before the owning track's own commit.
    """
    (scratch / "mine.txt").write_text("A's work\n", encoding="utf-8")
    _git(scratch, "add", "mine.txt")                       # agent A stages
    (scratch / "theirs.txt").write_text("B's work\n", encoding="utf-8")
    _git(scratch, "add", "theirs.txt")                     # agent B, in between

    refused = _git(scratch, "commit", "-m", "A: my work")
    assert refused.returncode != 0
    assert "SHARED INDEX" in refused.stderr
    assert "theirs.txt" in refused.stderr                  # the offender is named
    head = _git(scratch, "log", "-1", "--pretty=%s").stdout.strip()
    assert head == "base", "the cross-track commit must not exist"

    # The form the refusal told A to use takes A's file and leaves B's staged and uncommitted.
    ok = _git(scratch, "commit", "-m", "A: my work", "--", "mine.txt")
    assert ok.returncode == 0, ok.stderr
    landed = _git(scratch, "show", "--name-only", "--pretty=format:", "HEAD").stdout.split()
    assert landed == ["mine.txt"]
    assert "theirs.txt" in _git(scratch, "diff", "--cached", "--name-only").stdout


def test_two_tracks_journals_are_refused_through_real_git(scratch):
    for name in ("research/journal_eng.md", "research/journal_critic.md"):
        p = scratch / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("entry\n", encoding="utf-8")
    _git(scratch, "add", "research")
    out = _git(scratch, "commit", "-m", "eng: x", "--",
               "research/journal_eng.md", "research/journal_critic.md")
    assert out.returncode != 0
    assert "journals" in out.stderr
    assert _git(scratch, "log", "-1", "--pretty=%s").stdout.strip() == "base"


def test_no_verify_still_bypasses(scratch):
    """The documented deliberate exception has to keep working, or the gate is a trap."""
    (scratch / "mine.txt").write_text("x\n", encoding="utf-8")
    _git(scratch, "add", "mine.txt")
    out = _git(scratch, "commit", "-m", "deliberate", "--no-verify")
    assert out.returncode == 0, out.stderr


# ------------------------------------------------------------- tier 3: the deployed hook file

def test_the_repo_actually_runs_its_hooks():
    """C-7's lesson one level out: a gate nothing invokes is not a gate.

    `.git/hooks/` holds only `*.sample` here, so every assertion above is vacuous unless
    `core.hooksPath` points at the tracked directory.
    """
    got = _git(REPO, "config", "--get", "core.hooksPath").stdout.strip()
    assert got == ".githooks", (
        f"core.hooksPath is {got!r}; run: git config core.hooksPath .githooks"
    )
    assert HOOK.is_file()


def test_the_deployed_hook_runs_the_scope_gate_and_exits_on_it():
    body = HOOK.read_text(encoding="utf-8")
    scope = next(ln for ln in body.splitlines() if "commit_scope.py" in ln and not ln.startswith("#"))
    assert "exit 1" in scope, "a scope failure must stop the commit, not scroll past"
    # ...and before the slow completion gate, so a mis-scoped commit fails fast.
    assert body.index("commit_scope.py") < body.index("qb_check.py")
