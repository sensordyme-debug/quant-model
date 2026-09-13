"""Refuse a commit that takes files its author did not name (E-12 / C-10).

Six commits on 2026-09-12/13 carried another track's files. `AGENTS.md` step 7 already
forbids `git add -A`, so the rule was never the gap. The gap is that **`git add <paths>`
then `git commit` is not atomic in a tree six agents share**: `git commit` with no pathspec
commits *the index*, and a concurrent agent's `git add` lands in the seconds between the two
commands. C-8 watched its own commit `861c70a` sweep four of the `daily` track's files under
a `critic:` message after `git status` had been checked and shown three.

The fix C-8 identified is `git commit -m "..." -- <paths>`, which reads the named paths from
the working tree and ignores the rest of the index. This module makes that form mandatory.

**How the hook can tell.** Measured on git 2.55.0.windows.5, not assumed:

    git add a && git commit -m m       GIT_INDEX_FILE=.git/index                commits a + whatever else is staged
    git commit -m m -- a               GIT_INDEX_FILE=.git/next-index-<pid>.lock  commits a
    git commit --only a -m m           GIT_INDEX_FILE=.git/next-index-<pid>.lock  commits a
    git commit -am m                   GIT_INDEX_FILE=.git/index.lock           commits a + whatever else is staged
    git commit --include a -m m        GIT_INDEX_FILE=.git/index.lock           commits a + whatever else is staged
    git commit --amend                 GIT_INDEX_FILE=.git/index                commits the index

A partial commit - and only a partial commit - is prepared in a temporary `next-index-*`
index. So `basename(GIT_INDEX_FILE).startswith("next-index-")` is exactly "the author named
the paths", and every other form is exactly "this commit takes the shared index". That is
rule 1, and it is mechanical: no ownership map to maintain, nothing to rot.

**Rule 2 is the C-10 text, corrected.** C-10 asked for a hook that refuses a commit whose set
"spans more than one track's journal file". Run as written over all 219 commits that rule
fires **14** times and **12 are legitimate**, because `AGENTS.md` gives the `daily` track two
journals - `research/journal.md` is the `daily`/`iterate` history *and* the daily review's
merge target, so `daily` writes it alongside `journal_daily.md` routinely. A rule that is
wrong 12 times out of 14 trains its users to reach for `--no-verify`, taking the `qb_check`
gate with it. Counting that pair as one owner drops it to **2 of 219, both true positives**
(`861c70a`, critic sweeping daily; `3a7b764`, futures sweeping critic).

**What this cannot do**, stated because the hook's silence would otherwise imply it: `--only`
protects paths you did **not** name, never a shared path you did (F-17). If another agent has
edited a file you name, the working-tree content the partial commit reads includes their edit.
Nothing in git fixes that; only a disjoint file scope does.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# `research/journal.md` is the `daily`/`iterate` history and the daily review's merge target
# (AGENTS.md, "Parallel tracks"), so the daily track owning both of these is correct and
# routine - 12 of the 14 naive firings. They are one owner.
JOURNAL_PAIR = frozenset({"research/journal.md", "research/journal_daily.md"})
_JOURNAL_PREFIX = "research/journal_"


def journal_owner(path: str) -> str | None:
    """The track that owns `path`, or None if it is not a journal file.

    Only journal files are classified. Every other path is deliberately unowned: a general
    path-to-track map would be a guess about six concurrent scopes and would rot the first
    time a track picked up a new directory, and rule 1 already closes the mechanism without
    one.
    """
    p = path.replace("\\", "/")
    if p in JOURNAL_PAIR:
        return "daily/iterate"
    if p.startswith(_JOURNAL_PREFIX) and p.endswith(".md"):
        return p[len(_JOURNAL_PREFIX):-len(".md")]
    return None


def names_its_paths(index_file: str | None) -> bool:
    """True when git prepared this commit from a pathspec (`--only` / `-- <paths>`)."""
    if not index_file:
        return False
    return Path(index_file).name.startswith("next-index-")


def _quote(path: str) -> str:
    return f'"{path}"' if any(c in path for c in ' \t"\'') else path


def check(index_file: str | None, committed: list[str]) -> tuple[bool, list[str]]:
    """Decide on a commit. Returns (ok, message lines).

    Pure: takes the two facts the hook reads from git so the rules are testable without
    building a repository per case.
    """
    if not committed:
        # Nothing to take from anyone. `git commit --amend` with no staged change and the
        # empty-commit path both land here; neither can carry another track's file.
        return True, []

    if not names_its_paths(index_file):
        return False, [
            "pre-commit: this commit would take the SHARED INDEX, not a set you named.",
            "",
            "  `git add <paths>` then `git commit` is not atomic in a tree six tracks share:",
            "  `git commit` with no pathspec commits the index, so a concurrent agent's",
            "  `git add` in between lands in your commit under your message (C-10, E-12).",
            "",
            f"  It would commit these {len(committed)} path(s):",
            *(f"      {p}" for p in committed),
            "",
            "  Re-run naming the ones that are yours:",
            "",
            f"      git commit -m \"<msg>\" -- {' '.join(_quote(p) for p in committed)}",
            "",
            "  (order matters: everything after `--` is a path, so `-m` comes first)",
        ]

    owners = sorted({o for o in (journal_owner(p) for p in committed) if o})
    if len(owners) > 1:
        offenders = sorted(p for p in committed if journal_owner(p))
        return False, [
            f"pre-commit: this commit names {len(owners)} tracks' journals: {', '.join(owners)}.",
            "",
            *(f"      {p}  -> {journal_owner(p)}" for p in offenders),
            "",
            "  One commit per track (AGENTS.md, 'Parallel tracks'). Drop the journals that",
            "  are not yours from the pathspec and let their own track commit them.",
        ]

    return True, []


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False,
    ).stdout


def committed_paths() -> list[str]:
    """The paths this commit will actually write, read from the index git handed the hook.

    Under a partial commit `GIT_INDEX_FILE` is the temporary index, so this is the pathspec's
    resolved set; under a plain commit it is the whole staged set. Either way it is what would
    land, which is the only thing worth judging.
    """
    out = _git("diff", "--cached", "--name-only", "-z")
    if not out:
        # No HEAD yet (first commit): `git diff --cached` has nothing to diff against.
        out = _git("ls-files", "--cached", "-z")
    return [p.replace("\\", "/") for p in out.split("\0") if p]


def main() -> int:
    ok, lines = check(os.environ.get("GIT_INDEX_FILE"), committed_paths())
    if ok:
        return 0
    print("", file=sys.stderr)
    for line in lines:
        print(line, file=sys.stderr)
    print("", file=sys.stderr)
    print("  Deliberate exception: git commit --no-verify, and say why in the message.", file=sys.stderr)
    print("", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
