# Development: the two interpreters, the gate, the hook, and committing in a tree six agents share

Status of this document: describes the toolchain and the engineering gates as they exist at
commit `2a7367f` (2026-09-13), measured on this machine. Where the repository's own guidance
disagrees with what the tooling now enforces, both are stated.

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | yes | 1,550 tests collected in 54 files (`py -3.14 -m pytest --collect-only`, 2026-09-13, before the in-progress test files named in `docs/RISK.md` appeared in the tree); `scripts/qb_check.py` is green on `quant_brain/` and `tests/` at HEAD |
| STRATEGY VALIDATED | **no** | see `docs/RESEARCH.md` |
| LIVE EXECUTION VALIDATED | **no** | see `docs/RISK.md` |
| PROFITABILITY DEMONSTRATED | **no** | |

---

## Two interpreters

| | `py -3.11` | `py -3.14` (default `python`) |
|---|---|---|
| version | 3.11.9 | 3.14.7 |
| pandas / numpy | 2.2.3 / 2.4.6 | 3.0.5 / 2.5.3 |
| pyarrow | **absent** | present |
| runs | LEAN via pythonnet (`scripts/env.ps1` sets `LEAN_PYTHON_HOME`, `PYTHONNET_PYDLL`; `scripts/backtest.py` reads `PY_HOME`) and the `algorithms/*/main.py` it hosts | `quant_brain/`, the tests, every `scripts/*` that touches parquet, both scheduled trading tasks (the installers resolve `python` at registration time), the pre-commit hook, the watchdog |

Nothing in the repository guards on `sys.version_info` or `pandas.__version__`. pandas 3.0
changed copy-on-write, string dtype and resample semantics relative to 2.2, so two numbers
produced under different interpreters are not necessarily comparable. `quant_brain/core/
provenance.py` records an `env_key` digest of interpreter and numeric-stack versions with
every experiment, and `research/promotion.py` refuses to compare across environments
(`EnvironmentMismatch`). `ruff.toml` targets `py311` and `pyrightconfig.json` pins
`pythonVersion: 3.11` so that no modernisation is suggested that would break the LEAN-side
import. A 3.13 interpreter is also installed and is used by nothing here.

---

## The gate: `scripts/qb_check.py`

```
python scripts/qb_check.py              # blocking: ruff (core + tests + changed files), pyright, pytest
python scripts/qb_check.py --advisory   # also the whole-repo legacy debt, never fails
python scripts/qb_check.py --changed    # lint only what git reports as touched
python scripts/qb_check.py --quiet      # one line per stage, for hooks
```

| stage | scope | blocking |
|---|---|---|
| `ruff check` | `quant_brain/`, `tests/`, plus any changed `.py` elsewhere (staged, unstaged and untracked) | yes |
| `pyright --outputjson` | `quant_brain/`, `tests/` (`include` in `pyrightconfig.json`), mode `basic` | yes when installed; a missing pyright is a warning (`shutil.which`, because npm installs a `.cmd` shim on Windows) |
| `pytest -q` | the whole suite | yes |
| advisory lint | `scripts/`, `algorithms/` with `--isolated` so `per-file-ignores` do not hide the count | never |

The two-tier design is calibration, not preference: the strict ruleset reported 1,428
findings on `scripts/` + `algorithms/` and a handful on `quant_brain/` + `tests/` when
measured. A gate red on day one is a gate bypassed by Friday. The debt shrinks by deleting
lines from `per-file-ignores` in `ruff.toml`, one rule family per commit.

Two traps `ruff.toml` records rather than suppressing silently: `I001`'s autofix hoists
imports above the `sys.path.insert` that makes them importable in `scripts/` (a lint fix
becomes an `ImportError` in a runner), and `F821` on `scripts/ml_f7.py:295` is a verified
false positive (loop-carried names). `ruff format` is deliberately not in the gate; a
repo-wide reformat in a tree six tracks edit concurrently would produce merge chaos.

Toolchain measured 2026-09-13: ruff 0.16.7, pyright 1.1.414, pytest 9.1.1.

### The suite and the `runner` marker

`tests/conftest.py` puts `scripts/` and the repo root on `sys.path` so the runners import the
way they import each other at run time, and its `isolate_live` fixture redirects every write
to `live/state/` and every alert to a recorder, so a test cannot corrupt the deployed book.
`RUNNER_TESTS` (ten files, 241 tests on 2026-09-13) is the set allowed to stop the 09:25
sleeve; `scripts/intraday_launch.py` runs `-m runner` as its gate and everything else as a
report that cannot change the exit code (E-8, E-11). A new test file has to opt in to the
power to cause an outage. `conftest.run_as_scheduler` runs a script the way Task Scheduler
does - absolute path, repo as cwd, `PYTHONPATH` stripped - because 1,221 green tests once
hid an 83-minute `ModuleNotFoundError` in the deployed 15:45 command (C-6, C-7).

---

## The pre-commit hook: `.githooks/pre-commit`

Enabled per clone with `git config core.hooksPath .githooks`; this clone has it set. Two
steps, in this order:

1. `py -3.14 scripts/commit_scope.py` - instant; refuses a commit that would take files its
   author did not name (below).
2. `py -3.14 scripts/qb_check.py --quiet --no-types` - lint and the full suite. Pyright is
   skipped in the hook; run it yourself or via `qb_check` without `--no-types`.

Because step 2 runs the whole suite, a commit holds `.git/index.lock` for two to three
minutes (C-11 measured ~175 s). `git commit --no-verify` bypasses both steps; the hook's own
text and `AGENTS.md` ask that the reason go in the commit message.

---

## The shared-tree hazard

Six OpenClaw tracks (`iterate`, `ml`, `daily`, `options`, `critic`, `eng`) commit to this
working tree concurrently. `AGENTS.md` forbids `git add -A`. That was never the mechanism.

**`git add <paths>` followed by `git commit` is not atomic.** `git commit` with no pathspec
commits the **index**, and another agent's `git add` lands in the seconds between your two
commands. On 2026-09-12/13 that put files under the wrong track's message at least six
times, in both directions:

| commit | what it carried | recorded by |
|---|---|---|
| `0193f21` | the daily track's S-39 files under a `scorecard:` message | `560b0bb` |
| `98512df` | the futures fetcher, three funnel runs and 408 ledger rows under `ml: F-16` | `8d5ddb6`, `3a7b764`, `research/journal_futures.md` |
| `30abec5` / `2aa33f5` / `43816d1` / `b749cbb` | the options track's O-8 scattered across four commits, and a daily backlog item deleted as collateral | `379ad1b` |
| `861c70a` | four of the daily track's files under `critic: C-8` | `7c54074`, `3ee9a03` |
| `11f0308` ("vcjikyftr") | `scripts/intraday_common.py`, which the live trader imports, 97 minutes before its owning track committed | `research/journal_eng.md` E-12 |

Two related traps. Clearing a stale `.git/index.lock` after a killed process **leaves that
process's staged files behind** for whoever commits next
(`research/journal_futures.md`). And with every track's hook holding the lock for minutes,
the wait itself becomes a storm: C-11 lost 14 consecutive attempts across ~9 minutes.

**`taskkill /F /IM python.exe` is process-wide** on a machine where five other tracks are
running; C-14 records killing five processes belonging to other tracks that way. Kill by PID
or set a timeout.

---

## The `git commit --only` discipline

Name the paths in the commit itself:

```
git commit -m "<track>: <name> - <result>" -- <path> [<path> ...]
git commit --only <path> [<path> ...] -m "..."      # same thing
```

Why the hook can tell the difference (measured on git 2.55.0.windows.5,
`scripts/commit_scope.py` docstring):

| form | `GIT_INDEX_FILE` the hook sees | commits |
|---|---|---|
| `git add a && git commit -m m` | `.git/index` | a + whatever else is staged |
| `git commit -m m -- a` | `.git/next-index-<pid>.lock` | a |
| `git commit --only a -m m` | `.git/next-index-<pid>.lock` | a |
| `git commit -am m` | `.git/index.lock` | a + whatever else is staged |
| `git commit --include a -m m` | `.git/index.lock` | a + whatever else is staged |
| `git commit --amend` | `.git/index` | the index |

Only a partial commit is prepared in a temporary `next-index-*` index, so
`basename(GIT_INDEX_FILE).startswith("next-index-")` is exactly "the author named the paths".
Rule 1 of `commit_scope.py` refuses everything else and prints the command to re-run with
the paths it would have taken. Rule 2 refuses a commit naming two tracks' journals
(`research/journal.md` + `research/journal_daily.md` count as one owner; run literally, the
original rule fired 14 times over 219 commits with 12 false positives - E-12).
`tests/test_commit_scope.py` (25 tests, not `runner`-marked) includes a control that real git
still emits `next-index-*` and a reproduction of the concurrent-add race.

What `--only` cannot do, stated because the hook's silence would imply otherwise: it protects
paths you did **not** name, never a shared path you did. `research/backlog.md` is edited by
every track; if another agent has edited a file you name, the working-tree content the
partial commit reads includes their edit (F-17, `86d0479`). Only a disjoint file scope fixes
that. So: small targeted edits to shared files, your own journal (`research/journal_<track>.md`),
and after clearing a stale lock, `git diff --cached --name-only` before anything else.

`AGENTS.md` step 7 still teaches `git add <paths> && git commit -m "..."`. The hook now
refuses that form. Until the file is updated (it is the owner's), the refusal message is
where agents learn the correct one.

---

## Secrets and `.env`

`.gitignore` line 10 is `.env`. Lines 11-14 add `*.key`, `*.pem`, `live/secrets*.json`,
`live/secrets.env`; lines 15-20 keep `live/log/`, `live/state/`, `live/HALT`,
`live/APPROVED_PAPER.md` and `live/alerts.json` out of git so automation can never commit
them. `.env.example` is not matched by the `.env` pattern and is meant to be committed.

`.env.example` at the repository root lists the seven variables `quant_brain` reads, with
placeholder values only. Two facts about it:

- **Nothing loads a `.env` file.** There is no `python-dotenv` in the tree and no code that
  parses `.env`. `quant_brain/core/mode.py` reads `QB_ACCOUNT_MODE`, `QB_VENUE`, `QB_ACCOUNT`
  and `QB_LIVE_TRADING_ENABLED` from `os.environ`; `quant_brain/brokers/projectx.py` reads
  `PROJECTX_USERNAME`, `PROJECTX_API_KEY`, `PROJECTX_BASE_URL` the same way and refuses
  credentials from any other source. Values have to be in the process environment - set by
  the shell, or by the Task Scheduler action. Copying `.env.example` to `.env` documents your
  intent and is gitignored; it does not configure anything by itself.
- The other API keys (Alpaca, Theta, FMP, Telegram) are a different mechanism:
  `scripts/apikeys.py` parses `live/secrets.env`, also gitignored.

`tests/test_qb_projectx.py::test_no_credential_appears_in_the_source_of_this_package` scans
every `.py` under `quant_brain/` for `sk-...`, JWT `eyJ...` and `Bearer ...` shapes, and
`test_the_secret_is_absent_from_every_printable_form` covers `repr`, `str`, f-strings and
event payloads of the credential objects. `test_this_checkout_is_not_configured_for_live`
asserts the tree cannot reach `EXECUTION_READY` as configured.

---

## Not implemented

- A CI server. The gate runs on this machine, in the hook and by hand.
- Type checking of `scripts/` and `algorithms/`; both are `exclude`d in `pyrightconfig.json`
  so the scope can widen one module at a time.
- `ruff format` in the gate, or any automated import tidying in `scripts/`.
- Pyright in the pre-commit hook (`--no-types`).
- Per-track worktrees. `docs/ARCHITECTURE_AUDIT.md` names them as the root fix for the commit
  races and out of scope; the hook is the mitigation.
- Any enforcement of file ownership beyond journal files. `commit_scope.journal_owner`
  classifies only `research/journal_*.md`; a general path-to-track map would rot.
- Loading of `.env`.

## What this document does not claim

It does not claim the gate proves the strategies are correct; it proves the core lints,
type-checks in `basic` mode and passes its tests. It does not claim the hook prevents a track
from committing another track's edit to a file both touched; it prevents committing files the
author did not name. It does not claim `AGENTS.md` and the hook currently agree on the commit
command; they do not. It does not claim `.env.example` configures anything; it documents
variable names.
