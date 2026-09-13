# Operations: the CLI, the scheduled tasks, the watchdog, and what automation must never do

Status of this document: describes what runs on this machine at commit `2a7367f`
(2026-09-13): `quant_brain/__main__.py`, the four task installers under `scripts/`,
`scripts/intraday_launch.py`, `scripts/gateway_watchdog.py`, and the files they write. CLI
outputs quoted below were captured on 2026-09-13 from an unconfigured shell.

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | yes | `tests/test_launch_preflight.py`, `test_runner_entrypoints.py`, `test_gateway_watchdog.py`, `test_store_health.py` |
| STRATEGY VALIDATED | **no** | see `docs/RESEARCH.md` |
| LIVE EXECUTION VALIDATED | **no** | the two scheduled trading tasks trade an IBKR **paper** account (`DU...`), gated by a human-created `live/APPROVED_PAPER.md` |
| PROFITABILITY DEMONSTRATED | **no** | |

---

## The CLI: `python -m quant_brain <group> <command>`

Every command answers a question that is hard to answer otherwise; commands that would need
a venue connection are absent rather than stubbed (`__main__.py` docstring). All run on
`py -3.14`.

| command | answers | exit code |
|---|---|---|
| `mode` | what this process may do, from `QB_ACCOUNT_MODE` and `QB_LIVE_TRADING_ENABLED` | 0 |
| `broker list` | every adapter, the authority it requires, and whether this process reaches it | 0 |
| `research ledger [--path]` | trials, statistical passes and the current bar per family | 0; 1 if the ledger is missing |
| `topstep rules [--raw]` | every rule with its confidence tier; `--raw` prints citations | 0 |
| `topstep unresolved` | every rule below `DOC` | **1** when anything is unresolved |
| `topstep readiness` | seven conditions between here and a practice account | **1** when any is unmet |

From an unconfigured shell on 2026-09-13:

```
$ python -m quant_brain mode
  authority   RESEARCH - default; QB_ACCOUNT_MODE unset
  QB_LIVE_TRADING_ENABLED   not set
  what that permits:  yes RESEARCH | NO BACKTEST | NO VALIDATED | NO PAPER | NO PRACTICE
                      NO HUMAN_APPROVAL | NO EXECUTION_READY  <- real money

$ python -m quant_brain broker list
  this process holds RESEARCH
  SimulatedAdapter  BACKTEST         NO   in-memory; nothing leaves
  IBKRAdapter       PAPER            NO   IB Gateway paper by default
  ProjectXAdapter   EXECUTION_READY  NO   TopstepX; dry run by default, cannot send

$ python -m quant_brain topstep readiness
  NOT READY: 4 of 7 conditions unmet.
```

The `research ledger` table's `passed` column counts statistical-gate passes, not survivors;
every row in the futures ledger is `rejected` (`docs/RESEARCH.md`).

Those six commands are what `2a7367f` provided. Commit `7331797` adds `risk status --scope`,
`risk reasons`, `session readiness` and `intents recover`; they parse
(`python -m quant_brain risk --help`) and read the modules named in `docs/RISK.md`. Nothing in a scheduled task or runner publishes the state they read, so on
this machine today they describe modules that no live path feeds. They are not documented
further here.

Per-module entry points follow the older convention: `python -m quant_brain.core.resources`
(memory and commit-charge snapshot, worker budget, pressure) and
`python -m quant_brain.core.dataquality`.

---

## The scheduled tasks

All are registered for the interactive logon of user `ashur`, so they run only while that
user is logged on. Battery settings were corrected on 2026-09-12 after an audit found the two
trading tasks would be stopped on battery with positions open; every installer now passes
`-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable`.

| task | trigger | action | limits | installer |
|---|---|---|---|---|
| Quant Intraday Sleeve | 09:25 local, Mon-Fri (the installer warns if the zone is not Eastern) | `<python> scripts/intraday_launch.py`, cwd = repo | 7 h, `MultipleInstances IgnoreNew` | `scripts/install_intraday_task.ps1` |
| Quant Paper Rebalance | 15:45 local, Mon-Fri | `<python> scripts/paper_trade.py` | 20 min | `scripts/install_paper_task.ps1` |
| Quant Dashboard | at logon | `<python> scripts/dashboard.py` -> `http://127.0.0.1:8787`, IB clientId 81, read-only except `live/state/nav_history.jsonl` | no time limit, restart x3 at 1 min, `IgnoreNew` | `scripts/install_dashboard_task.ps1` |
| OpenClaw Gateway | at logon | the OpenClaw node gateway on `127.0.0.1:18789` | - | not in this repository |
| OpenClaw Gateway Watchdog | every 5 min + logon | `powershell -File scripts/gateway_watchdog.ps1` -> `py 3.14 scripts/gateway_watchdog.py` | 5 min, `IgnoreNew` | `scripts/install_gateway_watchdog.ps1` |

`<python>` is whatever `python -c "import sys; print(sys.executable)"` resolved to at
registration - the 3.14 interpreter. Change a task by editing and re-running its installer,
not by an ad hoc `Set-ScheduledTask`; inspect with
`Get-ScheduledTask | Get-ScheduledTaskInfo`. The OpenClaw research jobs (hourly `iterate`,
2-hourly `ml` and `daily`, 3-hourly `options` and `eng`, 4-hourly `critic`, a 06:30 daily
review, `ops-open` 09:35 ET and `ops-close` 15:50 ET) live in `~/.openclaw/openclaw.json`
and are listed with `openclaw automations list --all`; they are not defined in this repository
and this document does not vouch for their current settings.

---

## The 09:25 preflight: `scripts/intraday_launch.py`

Any refusal alerts and does not trade:

| step | what | on failure |
|---|---|---|
| 1 | the `runner`-marked tests (`-m runner`, 241 tests, ~20 s) | exit **4** |
| 2 | replay the most recent **complete** stored session through `scripts/intraday_trader.py --replay` (a session's bars must span the bell; a half day is not complete - E-6) | exit **2** |
| 3 | IB Gateway reachable and the account starts with `DU` | exit **2** |
| 4 | no `live/HALT` or `live/HALT_INTRADAY`; `live/APPROVED_PAPER.md` present (unless `--dry-run`) | exit **3** |

Two things **report and never gate**, pinned by tests that walk the file's AST: the store
freshness report (`store_warnings`, replay lag against the calendar) and the full test suite,
which runs in a background thread beside the trader (`start_full_suite_report`). The trader
then runs in the foreground until 15:42 ET and its exit code is forwarded.
`--preflight-only` runs the gates and stops; `--dry-run` runs live bars without orders.

---

## The gateway watchdog: `scripts/gateway_watchdog.py`

An explicit state machine (`STARTING, HEALTHY, UNHEALTHY, RESTARTING, VERIFYING, FAILED`)
that replaced a sleep-45-s-then-probe-once script whose log for 2026-09-12 showed four of six
restarts "failing" purely because the machine was at 98% commit charge and the gateway took
longer than 45 s to bind. Constants: port 18789, 90 s starting grace, 240 s verification
budget polled every 3 s, at most 3 restarts per hour. The kill is scoped to the gateway's own
process, because the old version matched any node process whose command line contained
"openclaw" - including the research sessions the gateway had spawned.

```
python scripts/gateway_watchdog.py            # one check; restart if needed
python scripts/gateway_watchdog.py --probe    # health only, never restart
python scripts/gateway_watchdog.py --status   # the recorded history
```

State in `live/state/gateway_health.json`, log in `live/log/gateway_watchdog.jsonl`.

---

## Where things are written

| path | what | written by |
|---|---|---|
| `live/log/<date>.jsonl` | daily sleeve: every plan, order, fill, refusal | `scripts/paper_trade.py` |
| `live/log/intraday-<date>.jsonl` | intraday sleeve, including every `risk_denied` / `order_sent` event from `RoutedExecutor` | `scripts/intraday_trader.py` |
| `live/log/intraday-replay-<date>.jsonl` | the preflight replay | launcher |
| `live/log/alerts-<date>.jsonl` | every alert, with `delivered` recording whether the OpenClaw chat push left the machine (P-1: the push is allowed to fail; the file is the record) | `intraday_common.notify` |
| `live/log/audit-<date>.json` | end-of-session assertion pass (I-2) | assertion runner |
| `live/state/intraday_book.json` | the intraday sleeve's book; written only by real paper runs, never by `--replay` | trader |
| `live/state/last_run.json` | daily sleeve targets and equity high-water mark | `paper_trade.py` |
| `live/state/nav_history.jsonl` | NAV snapshots, at most one a minute | dashboard |
| `live/state/gateway_health.json` | watchdog state | watchdog |

`quant_brain/core/state.py` makes a simulation unable to name a live path: a caller chooses a
`StateScope`, gets a `StateStore`, and every resolved path is checked to be inside that
scope's root (AUD-04: seven `--mock` runs once wrote a fabricated equity curve into the live
state file). `live/log/`, `live/state/`, `live/HALT*` and `live/APPROVED_PAPER.md` are
gitignored.

---

## What to check when something breaks

| symptom | look at |
|---|---|
| the sleeve did not start at 09:25 | `Get-ScheduledTask 'Quant Intraday Sleeve' \| Get-ScheduledTaskInfo` for the last result; `live/log/alerts-<date>.jsonl` for the refusal; exit 4 = runner tests, 2 = replay or gateway, 3 = HALT present or approval missing |
| the sleeve started and traded nothing | `live/log/intraday-<date>.jsonl` for `risk_denied`, `venue_rejected`, `halt`, and the feed selection; IBKR quotes are 15 minutes delayed without a subscription and the trader falls back to Yahoo |
| the OpenClaw gateway is down or research jobs were "interrupted by gateway restart" | `python scripts/gateway_watchdog.py --status`, then `--probe`; the 2026-09-12 incident (node died silently, task stayed Running) is the shape to expect |
| IB Gateway | `python scripts/paper_trade.py --check` prints the `DU...` account; port 4002 paper; a weekly IB Key re-login is required and the first API connection needs the paper disclaimer clicked in Gateway's own window |
| stores stale or truncated | `python scripts/store_health.py --store minute -v`; `--strict` exits 1 on a FAIL; a truncated **last** session is a FAIL because it means the fetcher died |
| the gate is red | `python scripts/qb_check.py`; if the failure is in a file another track has modified and uncommitted, it is their mid-write, not yours (C-13 is the standing example) |
| the machine is starved | `python -m quant_brain.core.resources`; commit charge, not free RAM, is the binding leg on this box |
| how many hypotheses have been tried | `python -m quant_brain research ledger` |
| the dashboard will not start | a zombie `dashboard.py` still holds port 8787 and IB clientId 81; it must be killed by hand, by PID |
| a commit carried another track's files | `git log --stat`; the track journals record each instance; do not rewrite history - other agents are committing against this branch |
| something needs a person | `BLOCKERS.md` (root; `research/BLOCKERS.md` is superseded) |

---

## What automation must never do

The master directive's Phase 55 text is not in this repository. This list is assembled from
the sources named, each of which is enforced or stated in the tree.

| never | source |
|---|---|
| place a live order, run the LEAN launcher with `ib-trading-mode=live`, or run `environment=live-*` without `live/APPROVED_PAPER.md` | `CLAUDE.md`; `AGENTS.md` red lines |
| create `live/APPROVED_PAPER.md` or any `live/approvals/<venue>-<account>.md` | `live/README.md` ("Never create it from an automated job"); `mode.write_approval` ("Never called by automation") |
| set `QB_LIVE_TRADING_ENABLED`, pass `i_understand_this_is_real_money=True`, or point `IBKRAdapter(live=True)` at a socket | `core/mode.py`: the three locks exist so that no single actor can supply them |
| delete `live/HALT` or `live/HALT_INTRADAY`; deleting resumes trading and is a human decision | `live/README.md` |
| edit credentials or `live/secrets*`; commit anything under `live/` that `.gitignore` excludes | `AGENTS.md`; `.gitignore` |
| change trader execution, risk or flatten code without running `--replay <date>` and reading the log | `AGENTS.md`, intraday rules (a) |
| change the deployed `live/intraday_config.json` without OOS evidence recorded in the journal | `AGENTS.md`, intraday rules (c) |
| modify `research/champion.json` except through `scripts/evaluate.py --promote` (daily track) or a critic restore from git with written evidence | `AGENTS.md`, parallel tracks |
| change scheduled tasks or OpenClaw config without inspecting and preserving existing state; change task settings other than by re-running the repo installer | `AGENTS.md` red lines; the `gateway_watchdog.ps1` header |
| `git add -A`, a bare `git add <dir>`, `git commit` without a pathspec, force-push, or rewrite shared history | `AGENTS.md`; `.githooks/pre-commit` |
| `taskkill /IM python.exe` or any process-wide kill on this machine | `research/journal_critic.md` C-14 |
| spend money - purchase a Combine, a data tier, a subscription - or change risk posture; ask in the reply and stop | `AGENTS.md` red lines; `BLOCKERS.md` |
| clear a ProjectX halt in code; nothing in the module does, and a halt requires a person and a restart | `brokers/projectx.py` |
| send external messages or posts beyond the configured alert channel | `AGENTS.md` red lines |

## Not implemented

- **Paging.** Nothing gets a person to look when the sleeve breaks outside a session; the
  chat push through OpenClaw is optional (`live/alerts.json`) and allowed to fail
  (`BLOCKERS.md` OWNER-2).
- Any operational procedure for a futures or prop-firm account. There is no account, no
  adapter that can send, and no scheduled task that references `quant_brain/brokers/projectx.py`.
- Automatic restart of the intraday trader inside a session (`IgnoreNew`; a crash means a
  flat-check by `ops-close` and a person).
- A governor or session state that any runner publishes. The `risk status` /
  `session readiness` / `intents recover` commands read state files that no scheduled task,
  runner or preflight writes yet; the modules behind them are committed but unwired
  (`docs/RISK.md`).
- Any command that connects to a venue from `python -m quant_brain`, by design.
- A dashboard panel for the futures ledger or the twin; the dashboard reads the equity
  sleeves, `research/*` and the stores.

## What this document does not claim

It does not claim the OpenClaw job schedule is as described; that lives outside the
repository and is quoted from memory notes. It does not claim the scheduled tasks' current
settings match the installers without re-running them; re-register to be sure. It does not
claim a person is alerted when something fails; a file is written and a chat push is
attempted. It does not claim the Phase 55 list above is the directive's list; it is the
repository's own boundaries, gathered in one place.
