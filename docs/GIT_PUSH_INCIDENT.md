# The unexplained pushes: what actually happened

Investigation 2026-09-14. Read-only: nothing was committed, pushed, disabled, modified or
deleted. This file is deliberately left **untracked** so that reading it changes nothing.

---

## Answer in one line

**Cursor's built-in Git extension.** Not Claude Code, not OpenClaw, not a scheduled task, not
a hook, not CI. Somebody used the Source Control panel in Cursor, which has the repository
open, and its Sync / Push button ran `git push origin main:main`.

---

## The evidence

`%APPDATA%\Cursor\logs\20260909T093347\window1\exthost\vscode.git\Git.log` records every git
command that extension runs. Its push lines match this clone's `refs/remotes/origin/main`
reflog to the second, on all five occasions:

| Cursor `Git.log` | reflog entry | result |
|---|---|---|
| 2026-09-12 22:03:19.214 `git push -u origin main` | 22:03:19 `update by push` | ok |
| 2026-09-13 04:04:43.520 `git push origin main:main` | 04:04:43 `update by push` | ok |
| 2026-09-13 14:46:18.826 `git push origin main:main` | 14:46:18 `update by push` | ok |
| **2026-09-13 21:32:35.215** `git push origin main:main` | *no reflog entry* | **REJECTED** |
| 2026-09-14 00:50:36.345 `git push origin main:main` | 00:50:36 `update by push` | `6c8f919..822cf0b` |
| 2026-09-14 02:13:35.534 `git push origin main:main` | 02:13:35 `update by push` | `822cf0b..971d390` |

Two details confirm the mechanism rather than merely correlating with it.

`update by push` is written to `refs/remotes/origin/main`'s reflog only when a push is
executed **from this working copy**. A push from another clone would leave no trace here. So
the pusher had this directory as its working directory.

The 02:13:35 push was preceded 2 seconds earlier by `git pull --tags origin main`. Pull then
push is exactly what the **Sync Changes** button does. The 00:50 push had no preceding pull,
which is the plain **Push** action.

### The same tool made the two accidental vault commits

`Git.log` also shows `git add -A -- .` at:

- **2026-09-13 19:50:16** (took 19.6 s) — commit `592e11a`, message `dcfhtg`, 3,199 files
- **2026-09-13 21:31:05** (took 3.4 s) — commit `bb4bbf8`, message `igkhghk`, 3,200 files

followed at 21:31:07 by
`git -c user.useConfigOnly=true commit --quiet --allow-empty-message --file -`.

That is the Source Control panel's **Stage All Changes** button plus its commit box. The
junk commit messages are consistent with text typed into that box. This closes a question
left open in the earlier audit, which could not find `auto-commit.sh` or any other culprit:
there was never a script.

### The vault was pushed, and GitHub refused it

The 21:32:35 push carried the vault commit. It failed:

```
remote: error: File Quant Brain/_System/quantbrain/brain.db is 206.12 MB;
        this exceeds GitHub's file size limit of 100.00 MB
remote: error: GH001: Large files detected.
 ! [remote rejected] main -> main (pre-receive hook declined)
```

**The only thing that stopped the entire 3,200-file Obsidian vault from being published was
GitHub's 100 MB per-file limit.** Not `.gitignore`, which did not cover the vault at the
time. Not the pre-commit gate. A size limit on one file.

---

## A to L

**A. What process caused the push?** Cursor's `vscode.git` extension, running as the user,
from `C:\Users\ashur\Quant-Model\quant-model`. Cursor process tree rooted at PID 19252,
running since 2026-09-09.

**B. When?** Six push attempts between 2026-09-12 22:03 and 2026-09-14 02:13, five of which
succeeded. The two you asked about are 00:50:36 and 02:13:35 on 2026-09-14. Note that the
second happened *after* I reported the repository as one commit ahead, so the mechanism was
live during the investigation.

**C. What permissions did it have?** Everything the user account has. Git authenticates
through `credential.helper=manager` set in the **system** git config, so the GitHub
credential is in Windows Credential Manager and any process running as this user can push
without a prompt. That is the enabling condition for all of this.

**D. Could it read `live/secrets.env`?** Yes. It runs as the user and the file is readable.
There is no evidence it did, and nothing in git's data path would send it: the file has been
gitignored since before the incident, so `git add -A` never staged it.

**E. Could it have read ProjectX credentials?** Yes, by the same reasoning, if any had
existed. None exist. `PROJECTX_USERNAME` and `PROJECTX_API_KEY` are absent from
`live/secrets.env` and from the environment. Nothing could have read what is not there.

**F. Could it push arbitrary commits?** Yes, and did. It pushes whatever `main` points at,
with no review step and no confirmation beyond the button.

**G. Could it execute arbitrary shell commands?** The git extension itself runs only git.
But Cursor as a whole hosts an agent and a terminal, so the application can run anything.
Separately: five versions of the Claude Code Cursor extension are installed, and one Claude
Code process from that extension started at 02:12:50, 45 seconds before the 02:13 push.

**H. Was the pushed content clean?** **SAFE.** The pushed range `6c8f919..822cf0b` touches
50 files. No credential file, no `live/` file, no vault path. The only credential-shaped path
is `.env.example`, which is a placeholder template that is meant to be tracked and is
enforced to contain only `<angle-bracket>` markers. Checked separately, neither vault commit
contained `live/secrets.env` or any `.key`, `.pem` or `secrets.json`; the only matches were
two `.env.example` files. The remote holds `refs/heads/main` and nothing else, so the vault
recovery refs and the incident tag are **not** on GitHub.

**I. Is the mechanism still active?** **Yes.** The repository is open in Cursor right now,
the credential is cached, and the button is one click away. It pushed during this
investigation window.

**J. What should be disabled or changed?** Recommendations below. Nothing has been changed.

**K. What should remain enabled?** Also below.

**L. Is it safe to add ProjectX credentials to `live/secrets.env` now?** **Yes**, with one
caveat worth acting on first. See the last section.

---

## What was ruled out, and how

**OpenClaw.** Its two scheduled tasks are `Disabled`, last run 2026-09-13 12:25 and 13:15.
Its state database and logs stop at 2026-09-13 13:16. Its `lastRunCommand` is `onboard`. It
*is* configured with this repository as its `workspace`, so it is capable, but every push is
already accounted for by Cursor and none falls in a window when OpenClaw was active.

**Windows Task Scheduler.** The three Quant tasks last ran 2026-09-10 and 2026-09-11. No
task ran near either push.

**Git hooks.** `core.hooksPath = .githooks`, which contains only `pre-commit`. No
`pre-push`, `post-commit`, `post-checkout` or `post-merge` hook exists anywhere; `.git/hooks`
holds only `.sample` files.

**CI.** There is no `.github/`, no workflow, no `.gitlab-ci.yml`, no pipeline file.

**Scripts.** No file in the working tree runs `git push`. The four matches are prose in
documents that discuss the hazard. No Python subprocess call in the repository invokes
anything but read-only git verbs.

**OpenAI Codex.** Running since 2026-09-13 21:41 with shell access and an active log
database, so it was a serious candidate. Its `config.toml` trusts exactly one project, a
directory under `Documents\codex\`, not this repository, and its logs contain no `git push`.

**Claude Code.** No hooks are configured in `~/.claude/settings.json`. Of the session
transcripts in this project, only one other was active near a push and it contains no push
command. My own session ran none.

---

## The other thing this found

**The pre-commit gate did not run for Cursor's commits.** Cursor commits with
`git -c user.useConfigOnly=true commit --quiet --allow-empty-message --file -`, which does
**not** pass `--no-verify`, so the hook should have fired. Yet those commits completed in
2.4 s and 28 s, and the gate runs the full test suite, which takes about 110 s.

The guard itself works. Invoked now the way git would invoke it, it refuses:

```
GIT_INDEX_FILE=.git/index py -3.14 scripts/commit_scope.py   ->  exit 1
"this commit would take the SHARED INDEX, not a set you named"
```

So a Cursor-style commit is exactly what `commit_scope.py` exists to refuse, and it would
refuse one today. The most likely explanation for 2026-09-13 is that `core.hooksPath` was
configured after those two commits. That cannot be established from the artifacts, and it is
worth settling by experiment rather than assumption.

---

## Recommended remediation

Nothing here has been done. In priority order.

**1. Settle whether Cursor's commits run the hook.** Make one trivial commit from the Cursor
Source Control panel and watch whether the gate runs. If it does not, the Source Control
panel is a hole straight through `commit_scope.py` and the completion gate, and it is the
same hole that produced both vault commits. This is the single most valuable follow-up.

**2. Stop using Cursor's Source Control panel for this repository.** Its Stage All Changes
button is `git add -A`, which is precisely what `AGENTS.md` step 7 forbids and what
`commit_scope.py` was written to prevent. It caused both vault commits. Commit from the
command line with `git commit --only -- <paths>`.

**3. Decide whether pushing should be manual.** It currently is manual, just not deliberate.
If you want a review step, the cheapest is a `pre-push` hook that refuses when the push
would carry more than N files or would include any path under `Quant Brain/`. There is no
such hook today.

**4. Never use Push All or Push Follow Tags from that panel.** The two recovery refs and the
`incident/2026-09-13-vault-commit` tag still hold the whole vault, 636 MiB, 99% of the pack.
`git push origin main:main` cannot carry them; `git push --all` or `--tags` would try. The
100 MB file limit would probably reject that too, but relying on it twice is not a control.

**5. Resolve the recovery refs.** Still your decision. They are the only copy of that
snapshot, and they are also the thing that makes an accidental `--tags` dangerous.

### What should stay as it is

- `.gitignore` now covers `Quant Brain/`, `.obsidian/`, `.env.*`, `live/*.env` and
  `live/approvals/`. This is what makes a future `git add -A` harmless where the earlier one
  was not, and it is verified with `git check-ignore` rather than by reading the file.
- `credential.helper=manager` can stay. Removing it would mean a prompt on every push, and
  the exposure it creates is bounded by the ignore rules and by the absence of any credential
  in a tracked file.
- The `pre-commit` gate stays.
- Cursor itself stays. The editor is not the problem; one button in it is.

---

## On adding ProjectX credentials

It is safe, and here is the actual reasoning rather than a reassurance.

`live/secrets.env` is gitignored, is not tracked, and `git ls-files` confirms git is tracking
no credential file at all. `git add -A` cannot stage it, which is the exact path that caused
every incident here. The push mechanism only ever sends tracked content.

The residual risk is not git. It is that Cursor, Claude Code, OpenClaw and Codex all run as
your user and can all read any file you can. That is true today, is true whether or not you
add the credentials, and is the normal condition of a developer machine.

The one thing I would do first is item 1 above, because if the Source Control panel bypasses
the pre-commit gate, then the guard you are relying on to keep the next accident small is not
actually in the path.
