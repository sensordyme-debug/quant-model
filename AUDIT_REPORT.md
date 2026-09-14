# AUDIT REPORT — quant-model

> **ERRATA, added 2026-09-14.** This report is preserved as the record of what was found
> and when. Four of its measurements did not survive re-derivation and are corrected here so
> no reader takes them from this file:
>
> 1. **"9,110 of 18,114 lines (50.3%) unreachable"** (sections at lines 82, 625, 703) is an
>    over-count. It wrongly included `sizing.py`, which is reachable through a function-local
>    import at `governor.py:105`, and `lean_calendar.py`, reachable through a package
>    `__init__`. The corrected figure at the time was 17 modules / 8,023 lines / 44.3%. As of
>    2026-09-14 it is 16 modules / 7,581 lines / 40.0%.
> 2. **"30 crossed/locked quotes (ask <= bid)"** (line 247) is 0 crossed and 30 locked. All
>    thirty are consecutive, 08:00-08:29 ET on 2025-11-28, and outside regular trading hours.
> 3. **The claim that the funnel's verdict compared a dollar mean to a t-threshold** is wrong.
>    `Ledger.verdict` compares `abs(t.t)` to `bonferroni_threshold(n)`. It is dimensionally
>    correct. `Verdict.metric` holds the dollar mean and takes no part in the decision.
> 4. **"two-contract days are dropped"** describes a filter that drops nothing. There are zero
>    mixed-contract days inside the 09:30-15:45 ET window in any of the four stores.
>
> The report's central finding - that the validation and execution-safety apparatus is
> disconnected from production - held under re-measurement and is the reason for most of the
> work recorded in `SYSTEM_READINESS.md` and `QUANT_MODEL_REBUILD_PLAN.md`.

**Full, hostile, independent forensic audit** of the repository, its research, its knowledge base and its execution path.

| | |
|---|---|
| Repository | `C:\Users\ashur\Quant-Model\quant-model` (origin `github.com/sensordyme-debug/quant-model`, branch `main`, no other branches, no CI) |
| HEAD at audit start | `6c8f919` — 240 commits, 2026-09-08 → 2026-09-13, one git identity (`quant`), unsigned |
| Audit date | 2026-09-13 |
| Question asked | *Can this repository eventually be trusted as the research, validation, risk and execution foundation for a serious quantitative futures trading operation whose immediate objective is a legitimate strategy capable of surviving and potentially passing a Topstep $50K Trading Combine?* |
| Answer | **Not today. Eventually — plausibly yes, and sooner than the finding count suggests, because almost every defect is in wiring, discipline and sample size rather than in the ideas.** The detail is in §1 and §22. |

---

## 0. Method, scope and disclosure

**Method.** Read-only. Eight parallel auditors covering the vault, data/contract mechanics, backtest/leakage, statistics/multiplicity/ML/ledger, Topstep, risk/execution/recovery, security/reproducibility/tests/AI-safety, and architecture/strategies, plus the lead. Five completed; three (vault forensics, data/contracts, security/repro/tests) were killed by an API rate limit before producing anything, and **the lead re-executed those three domains personally** — every number in §3, §4 and §9 was measured by the lead in this session.

Evidence standard: `file:line` for every code claim, measured output for every data claim, URL + retrieval date for every external rule. Where something could not be established it says **UNKNOWN — REQUIRES VERIFICATION**. Nothing is inferred from a docstring.

**What was NOT done, deliberately.** No file under the repository was created, modified or deleted except this one. Nothing was committed. No script in `scripts/` was executed. No test suite was run against `live/`. No credential file was opened. No broker or venue was contacted. Live trading was not enabled. The Obsidian vault was not reorganised, rewritten or cleaned.

**Verification caveat.** The working tree was being modified by other automated tracks throughout the audit. One auditor recorded uncommitted ledger rows and three untracked scripts disappearing from the tree with HEAD unchanged and no trace in `git log`; that auditor issued no git write commands. Treat all tree-state observations as of `6c8f919`.

**Disclosure of conflict.** The lead auditor's own earlier session in this conversation authored `quant_brain/core/{governor,lifecycle,protection,reconcile,idempotency,locking}.py`, the briefs for the venue/sizing/analytics agents, `docs/IMPLEMENTATION_REPORT.md`, and commit `f7afd6d` (the intraday-runner governor wiring), all on 2026-09-13. That work is audited here at least as hostilely as everything else. Findings **RISK-03, RISK-04, RISK-05, RISK-15, ARCH-02, ARCH-15, TEST-04** and the scorecard critique in §5.4 are against it. The prior session's own "Implementation Report" scored Execution Safety 9.0/10 and called the layer "the right seam"; this audit scores the same layer 22/100 and finds two P0 defects in the runner it claimed to have improved.

---

## 1. THE ANSWER, UP FRONT

**Three findings dominate everything else.**

**(1) The deployed intraday paper runner is broken in two independent ways, both introduced *after* the last live session, and neither is covered by any test or by the launch preflight.**
`scripts/intraday_trader.py:891` reads the local `t` before it is assigned at `:922`, inside the `while True:` loop spanning 887–931 — proven by `symtable` (`t` is_local=True) and AST (LOADS at 891, 923, 929; STORE at 922 only). The first iteration of the live loop raises `UnboundLocalError`. Behind it, `LiveExecutor.__init__:349` aliases `self.open = self.adapter.open` and `settle():444` rebinds `self.open = still`, so from the first `settle()` onward every adapter-placed trade is invisible: fills are never booked, the book stays empty, `pending_qty()` reads 0, the same delta is re-sent every bar, and both the 2.5% daily-loss limit and the newly armed Governor read a frozen book. A fake-IB reproduction produced 4 orders / 4,000 shares for a strategy that wanted 1,000 once, with `book.pos == {}` and the 15:38 flatten computing `{}`. The crash currently masks the second defect. **Fix the crash alone and the sleeve accumulates unbounded exposure with a blind loss limit and no exit.**

**(2) The research evidence base does not survive contact with its own record.** The repository has an excellent, tested, *unused* statistics library and a research loop that mostly does not call it. `research/experiments.jsonl` (1,653 rows, 62 writers) has **no experiment id, family, trial count, threshold or verdict in any row**; `research/experiments_futures.jsonl` (817 rows) is the only multiplicity-accounted track and **every one of its 817 rows has `provenance: null`**. Against ~10⁴ statistics actually computed and looked at, 817 are accounted. The daily champion was promoted six times in four days on full-sample CAR with no significance test, no multiplicity and no holdout, and its own S-33/S-38/S-40 audits establish that the window labelled "OOS 2020-2026" was inside the selection set (S-38: *"Selection ran on FULL 2012-2026, which CONTAINS 2020-2026"*; S-40: the shipped crisis-switch cell is OOS rank 1 of 36 and IS rank 24 of 36). Its LEAN Probabilistic Sharpe Ratio is **33.2%**, and its headline 24.4% CAR is the **zero-slippage, zero-financing** column. `core/validation.Holdout` and `purged_walk_forward` have zero research callers and **no holdout has ever been carved**.

**(3) The "Obsidian foundry" of the brief does not exist as a pipeline, and the thing occupying its place is a different company's project.** `Quant Brain/` (4.2 GB, untracked, **not gitignored**) is an options-research operating system authored on macOS under `/Users/donov/`, created 2026-08-21→26 — *before this repository's first commit*. It contains a second complete codebase (`QuantModel/` → `github.com/DonovanWillis/QuantModel`, package `catalyst`, 332 source files, 3,917 test functions, ~250k cached parquet files, dangling submodule pointer) and a third Python package (`_System/quantbrain/`, 30 files). It contains **zero Topstep, prop-firm, ProjectX or MNQ content**. **No code in this repository reads it**; `quant_brain/core/knowledge.py` — the only knowledge-retrieval component — indexes `research/experiments.jsonl`, `backlog.md` and `journal*.md` only. **Zero journal, doc or ledger rows cite it.** It ships 244 files under `.claude/` including hooks that `exec node .claude/helpers/hook-handler.cjs` on every tool call, and 30 agent skills **which auto-registered into this very audit session** merely because the directory sits under the working directory.

**What this means for the stated goal.** The repository is *not* a fraud and is *not* an edifice of self-deception. Its most important single output — "544 futures hypotheses, 0 survivors, one look-ahead retracted" — is honest, and the refusal culture is real (10 of 11 items refused on the final day; 432 ledger rows tagged "not promotable"; the critic track attacks its own best result). But that headline is also **a statement about power, not about the market**: at n=395 sessions and σ≈$300/session, the minimum detectable effect at the family's own bar is **$66/session**, and the power to detect a genuine $20/session edge is **1.3%**. The system has not yet been able to find an edge; it has also not yet been able to *rule one out*.

---

## 2. PART A — INVENTORY AND SYSTEM MAP (Phases 1, 5 / 1)

### 2.1 Repository census (tracked)

| area | measured |
|---|---|
| tracked files | 389 — scripts 153 (135 `.py`), tests 69, `quant_brain` 53 `.py`, research 31, memory 26, docs 20, algorithms 19, live 2 |
| `quant_brain/` | 53 modules, **18,114 lines**, 83 intra-package import edges |
| tests | **1,895 collected across 65 files** (1,687 `def test_`) |
| research scripts | ~93 `sweep_*` / `ml_*` / `verify_*`; **0 import `quant_brain.core.stats`; 0 contain `purge` or `embargo`** |
| ledgers | `experiments.jsonl` 1,653 rows; `experiments_futures.jsonl` 817 + 1 retraction |
| data | `data/` 3.5 GB, 2,779 parquet — **untracked (`.gitignore:30`), unhashed** |
| results | `results/` 2,052 files — gitignored |
| dependency pinning | **NONE** — no `requirements.txt`, `pyproject.toml`, lockfile or `environment.yml` at the repo root |
| coverage tooling | **NONE** (`pytest.ini` has no `--cov`; no `.coveragerc`) |
| interpreters | 3.14.7 (harness, pandas 3.0.5) + 3.11.9 (LEAN, pandas 2.2.3, no pyarrow); a third (3.13) inside the vault |
| CI | none (`.github/` absent) |
| scheduled reality | `Quant Intraday Sleeve` 09:25 Mon–Fri → `intraday_launch.py`; `Quant Paper Rebalance` 15:45 → `paper_trade.py`; `Quant Dashboard` at logon; **OpenClaw Gateway + Watchdog `Disabled`** |
| commit velocity | 20 / 24 / 24 / 28 / 70 / 74 per day — **144 commits in the last two days**, six concurrent unattended tracks sharing one index |

### 2.2 The architecture that exists vs the architecture that is documented

The brief's diagram (OBSIDIAN FOUNDRY → AI RESEARCH LAYER → QUANT ENGINE → DECISION/RISK → EXECUTION) and the repository's own (`ARCHITECTURE.md` §4a-ii, `docs/IMPLEMENTATION_REPORT.md`) describe: `DATA → VALIDATION → FEATURES → SIGNAL → sizing.Sizer → idempotency.intent_id → RoutedExecutor[journal → Governor → adapter → journal] → OrderMachine → protection.verify → Reconciler`.

**What the two live runners actually execute:**

```
pandas frame
  -> signal dict {symbol: weight}
  -> hand-rolled weight->share sizing with caps read from a scripts/ constants file
  -> OrderIntent  (no intent_id, no journal)
  -> RiskChain containing NOTHING            (paper_trade.py:797)
     or ONE duplicate daily-loss limit       (intraday_trader.py:567)
  -> IBKRAdapter.submit -> ib.placeOrder
```

**Every limit that binds is applied to weights before an `OrderIntent` exists**, by convention, in **nine inconsistent copies** (`intraday_common.py:69-74` 0.20/1.6/2.5%; `live/intraday_config.json` 0.15/1.5; `active/signal.py` PARAMS 0.15/1.0; `lev_revert`/`xsect` 0.20/0.10 & 1.20; `intraday_backtest.RISK`; `dashboard/sources.py:77` hard-codes `368, 372, 1.5`; `governor.Limits`; `sizing.SizeLimits`; `propfirm.PropFirmProfile`).

**9,110 of 18,114 lines (50.3%) of `quant_brain/` are unreachable from any script, runner or the CLI** — verified by AST reachability from all 21 entry points. Thirteen modules have zero non-test callers: `sizing` (860), `portfolio` (440), `multipletest` (1,076), `robustness`+`analytics` (2,674), `venues/` (1,939), `promotion` (584), `validation` (455), `protection` (176), `reconcile` (232), `knowledge` (311), `lean_calendar` (214), `profiles` (119). About **520 tests (31% of the suite) exercise code nothing calls.** `docs/ARCHITECTURE_AUDIT.md` claims two dead modules.

`algorithms/` imports **zero** `quant_brain`. **143 files mutate `sys.path`** — including `quant_brain/core/dataquality.py:272`, which hacks into `scripts/` from inside the "market-agnostic core". **118 script→script import edges** make the "archive" a live dependency graph seven levels deep (`sweep_s43 → s42 → s41 → s40 → s25 → s19 → lean_prices`); `sweep_s19.commission` was wrong (1% vs LEAN's 0.5% cap) until S-44 and fed S-22…S-39.

Two hidden import cycles (`core.execution ↔ core.risk` via a lazy in-function import; `venues.base ↔ venues.propfirm` via TYPE_CHECKING). Two of everything: two ledgers with different schemas, two audits, two BLOCKERS files, three "the architecture now" diagrams written within 24 hours, two promotion ladders (one dead), two reconciliations (one dead), two walk-forwards (one dead), two calendars (one dead), two `Book` classes with a false "shared" docstring, five P&L models, twelve session-logic copies, five instrument tables, **seven cost models** (an eighth in the vault).

Stale maps, measured: `ARCHITECTURE.md:125,259,354-355` says the runners build `ib_async` objects inline and no runner has the governor — both false at HEAD. `AGENTS.md` names `algorithms/intraday/ml/`, which does not exist. `docs/ARCHITECTURE_AUDIT.md` says "~90 scripts / ~60 sweeps / 1,258 ledger rows"; measured 135 / 93 / 1,653.

### 2.3 Scalability

Abstractions exist on every axis (strategy identity, portfolio, per-account state, instruments, brokers, venue registry, prop firms). **A second concrete instance is exercised on none of them** except sub-strategy composition inside one sleeve. Specific corruption hazards: `governor.json` is keyed by `StateScope`, not by sleeve or account (two governors overwrite one file); `paper_trade.py:701-710` loads the other sleeve's universe by `sys.path` hack with `except Exception: _INTRADAY_UNIVERSE = []` — **on an import failure the daily runner treats the intraday book as its own and sells it**; the daily sleeve's orders carry an **empty** `orderRef`.

---

## 3. PART B — THE OBSIDIAN KNOWLEDGE BASE (Phases 2–4, 38–42 / 2–6, 40–42)

*Measured by the lead after the vault auditor was rate-limited.*

### 3.1 What it is

`Quant Brain/` — 4.2 GB, **untracked and NOT gitignored** (`git check-ignore` returns nothing for it or for the root `.obsidian/`). File census: **251,522 `.parquet`**, 1,128 `.md`, 737 `.py`, 706 `.json`, 630 `.pyc`, 328 `.txt`, **192 `.pdf`**, 121 `.csv`, 95 `.js`, 76 `.html`.

It is **a different project**: `_System/04 SYSTEM STATUS.md` names the vault path `/Users/donov/Quant Brain` (macOS, Obsidian pid 38504, `/opt/homebrew`); `.gitmodules` points `QuantModel` at `https://github.com/DonovanWillis/QuantModel.git`; a `__MACOSX/Quant Brain` copy in `~/Documents` shows it arrived as a zip. Note `created:` dates run **2026-08-21 → 2026-08-26** — the vault stopped moving twelve days before this repository's first commit.

Three codebases now coexist in the working tree:

| | repo `quant_brain/` | vault `QuantModel/src/catalyst/` | vault `_System/quantbrain/` |
|---|---|---|---|
| size | 53 files / 18,114 lines | 332 files / ~70k lines | 30 files |
| tests | 1,687 `def test_` | **3,917** | 14 files |
| interpreter | 3.11 + 3.14 | **3.13** | uv |
| domain | equity/futures, IBKR + LEAN, Topstep | **options convexity around catalysts**, Alpaca/Schwab/IBKR | vault tooling |
| Topstep content | 879 + 610 + 503 lines | **zero** | zero |
| data | `data/` 3.5 GB | `data_cache` 224,550 + `data_snapshots` 26,828 parquet | `brain.db` |

`QuantModel/.git` is a 35-byte gitlink to `../.git/modules/QuantModel`, which does not exist: **the nested repository's history, authorship and remotes are unrecoverable from this machine.**

### 3.2 Note inventory and classification

927 notes outside `.claude/`/`.obsidian/`. Folders: Sources 249 (**230 of them YouTube video notes**; only 9 notes over 114 research-paper PDFs), Backtests 211 (+70 PDFs, 42 `.py` "Rushed Backtests"), Thinkorswim 92, Reports 62, Quant Fundamentals 42, Strategies 37, model decisions 32, Hypotheses 22, backtesting 19, Claims 15, Templates 13, Options 13, Contradictions 9, Dashboard 9, Market Microstructure 7, experiments 6.

Frontmatter census (the vault self-classifies, which is itself a strength):

| declared | count |
|---|---|
| `type: source` | 290 (`status: transcribed` 212 — machine-transcribed YouTube) |
| `type: concept` | 72 |
| `type: report` | 42 · `type: moc` 37 · `type: strategy` 35 · `type: decision` 30 |
| backtest-result types (`rushed-backtest`, `updated-returns-result`, …) | 138 |
| **`authoritative: false`** | **189** |
| **`validated: false`** | **154** |
| **`confidence: VERY LOW`** | **51** · `confidence: speculative` 33 · `confidence: LOW` 17 |
| `evidence-class: "...MACHINE-GENERATED-ASR..."` | 32 |

**494 of 927 notes (53%) contain no source, citation or URL.** 8,622 wikilinks; the most-linked hubs are `_Trial Ledger` (111), `Transaction Cost Modelling` (106), **`Multiple Testing Problem` (106)**, `Walk-Forward Validation` (79), `Deflated Sharpe Ratio` (79) — the knowledge graph is centred on exactly the right methodological concepts.

### 3.3 Provenance and quality — the uncomfortable finding

The vault's methodology is **better than the repository's**. Three samples read in full:

- `Quant Fundamentals/Multiple Testing Problem.md` — *"Test enough hypotheses and some will pass by chance; report only the winner and you have manufactured a result."* Sourced (`quantpaper13.pdf`, `quantmodel18.pdf`), `formula-status: standard-reference`.
- `backtesting/Backtesting Master Specification.md` — *"What any run must satisfy **before** its number may be believed… contains **no results and no thresholds invented ahead of evidence**. Where a limit must be empirical, it says `TO BE DERIVED`."* Requires **next-bar-open or later fills** and *"a final holdout is touched once. Optimising against it, ever, voids the run."*
- `Contradictions/C-0003 VRP Gross Expensiveness vs Net Break-Even.md` — a properly constructed contradiction record: external side (Gârleanu–Pedersen–Poteshman, SPX 8.7% average excess IV 1996–2001, with the mechanism and the dealer-P&L magnitude), internal side (Catalyst v8: +0.07%/mo train, −0.07%/mo test), `severity: high`, **`resolution: none — deliberately unresolved`**.

`_System/_Source of Truth.md` defines an authority hierarchy (empirical result > trial ledger > schema > claims > strategies > hypotheses > contradictions > sources > **indexes are views, never authorities**) and records the incident that produced it. `_System/11 OVERFITTING CONTROLS.md` is a contract, not advice, and opens with the failure it exists to stop: *"`results/PROVENANCE.md` records a +47.6% CAGR that was a bug."* `Hypotheses/_Trial Ledger.md` declares `trials-issued-vault: 22`, `trials-prior-catalyst: 90`, **`trials-combined: 112`**, with the rule *"A trial is issued when a hypothesis is **recorded**, not when it is run"* and *"Variants count separately."*

**The repository violates all three of those rules.** Its funnel fills at the decision bar's close, not the next open. Its "holdout" has never been carved and its S-track OOS window was scored 189 times. Its ledger counts only what a writer chose to record, and `verdict()` can be called fifty times without recording once. **The best knowledge-management practice in the entire system is in the vault that no code reads and no journal cites.**

### 3.4 Topstep and futures coverage: zero

`grep -ril topstep` over the vault's markdown → **0 files**. Same for `prop firm`, `ProjectX`, `MNQ`. Apparent hits for "combine" (141) and "MES" (590) are `combined`/`times`/`names`. Every "OBSIDIAN VALUE" column in the Topstep rule table (§7) is therefore **"none"**. The repository's Topstep knowledge lives entirely in `docs/topstep/*.md` and `quant_brain/markets/futures_cme/topstep.py`.

### 3.5 The knowledge → hypothesis → experiment pipeline (Phase 6)

**It does not exist across the vault boundary.** Traces attempted, all negative:
- No module in `quant_brain/`, `scripts/`, `algorithms/`, `tests/` references the vault path (`grep` for "Quant Brain"/".obsidian"/"obsidian" matches only the package's own name).
- `core/knowledge.py:200-205` indexes `research/experiments.jsonl`, `research/backlog.md`, `research/journal*.md`. It is itself dead code (zero non-test callers) and, per `docs/ARCHITECTURE_AUDIT.md`, blind to the 818-row futures ledger.
- Zero hits for "Quant Brain", "vault", "obsidian", "QuantModel", "catalyst", "S-0012", "ruvector", "claude-flow" across all seven journals, `backlog.md`, both ledgers, `AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE.md`, `docs/`.

Inside the repository the pipeline that does exist is: **backlog item → sweep script with pre-registered docstring clauses → ledger row / journal entry → LLM interpretation → next backlog item**. That is a real loop with real discipline in the docstrings, and it is *not* knowledge-driven — it is incumbent-driven (`AGENTS.md:54`: *"Pick the highest-value open hypothesis, **or a promising variation of the champion**"*).

### 3.6 Confirmation bias and disconfirming evidence (Phase 40)

The vault preserves disconfirming evidence well: a dedicated `Contradictions/` folder with seven records and two registries, `Failure and Unrun Index`, `backtesting/unsuccessful/`, `_Superseded - 2023 Observed Campaign`, and 189 notes self-marked `authoritative: false`. The repository preserves it too, in prose (432 "not promotable" ledger rows; the critic journal). **Neither is machine-queryable**: `knowledge.py` indexes free-text tags with TF-IDF and cannot distinguish "evidence for X" from "X was refused", and it is not called by anything. An AI retrieving support for a strategy would find the supportive note and the refutation with equal probability and no ranking — which is better than one-sided, and worse than a system that surfaces the refutation first.

### 3.7 Knowledge decay (Phase 41)

The vault stamps `created:` on nearly every note and `verified-at:` with a verification method on system notes (`04 SYSTEM STATUS.md`: *"7-agent parallel sweep, 52 live checks"*). It has **no review-date, expiry or revalidation mechanism**. The repository has a better scheme on paper — `docs/topstep/VERSIONING.md` plus per-`Rule` `retrieved` dates and DOC/SEARCH/OWNER confidence tiers — but it is applied to one subject (Topstep) and, as §7 shows, one of its DOC-tier citations is a **404** and the `RETRIEVED` date is a module-level default pinned by a test.

### 3.8 Knowledge risks (top 20 → §16) and vault findings

| ID | SEV | finding | evidence |
|---|---|---|---|
| OBS-01 | **P1** | `Quant Brain/` is untracked **and not gitignored**; `git add -A` would stage 3,173 files including a foreign `.claude/` payload | `git check-ignore` returns nothing; `.gitignore` shown in §9.1; six mis-attributed commits already occurred in one night |
| OBS-02 | **P1** | The vault ships Claude Code hooks (`exec node .claude/helpers/hook-handler.cjs` on PreToolUse/PostToolUse/UserPromptSubmit/SessionStart/Stop/PreCompact/Subagent*/Notification), `enableAllProjectMcpServers: true`, `Bash(npx @claude-flow*)` allow-rules, and **30 agent skills that auto-registered into this audit session** | `Quant Brain/.claude/settings.json`; the skill list was injected into this session's context on first read of a vault file |
| OBS-03 | **P1** | A second complete trading codebase (`catalyst`, 332 files, 3,917 tests, own RiskManager/backtester/brokers) and a third package (`_System/quantbrain`) sit in the working tree with **three self-declared canonical sources** and no cross-reference | vault `CLAUDE.md:70-72`; `QuantModel/CLAUDE.md:10-11`; `_System/_Source of Truth.md`; repo `ARCHITECTURE.md` §1 |
| OBS-04 | **P2** | Identifier collision: repo `S-12` (risk-parity momentum, the live champion) vs vault `S-0012` ("Cross-Sectional Rotational Momentum", `Status: HYPOTHESIS. Not tested."); repo `C-`/`E-` vs vault `C-####` (contradictions) / `E-####` (experiments) | both trees grep from the repo root |
| OBS-05 | **P2** | 53% of notes (494/927) carry no source or URL; 230 of 249 "Sources" are machine-transcribed YouTube; 114 research-paper PDFs have 9 notes between them | frontmatter census §3.2 |
| OBS-06 | **P2** | Six machine-generated `Claims 2026-08-24 — Corpus Completion Batch N.md` files of 149–212 KB (4,120 claims from 331 sources) are the vault's bulk; a claim ledger of 60 rows indexes them | file sizes; `Claims/_Claim Ledger.md` 16 KB / 60 rows |
| OBS-07 | **P2** | The vault's methodology rules (record-time trials, one-look holdout, next-open fills, combined 112-trial deflation) are **stricter than the repository's practice and un-inherited** | §3.3 vs §5, §6 |
| OBS-08 | P3 | `karpathywiki` plugin is installed and, by the vault's own status note, **FAILED** (`llm_config_status: failed`); `dataview` and `graph-context-for-claude-code` are active | `.obsidian/community-plugins.json`; `04 SYSTEM STATUS.md` |
| OBS-09 | P3 | A stray 942-byte `Usersashur.openclawspawn-hook.log` sits untracked in the repo root recording process spawns | `ls`, `git ls-files` |
| OBS-10 | P3 | The vault's own returns table is 12-month, `APPROXIMATED / BEST-GUESS / VERY LOW`, `authoritative: false` — and sits under the same `S-` prefix as the live champion | `Backtests/Returns/Strategy Returns Ranking.md` |

**Knowledge-base quality scores (0–100, with the reason):**

| dimension | score | why |
|---|---|---|
| Source quality | 45 | 230 of 249 sources are machine-transcribed YouTube; 114 real papers exist as PDFs with almost no notes; the concept notes that *do* cite papers cite them correctly (C-0003's GPP reference is accurate) |
| Recency | 20 | Every note frozen 2026-08-26; the domain it describes (options/Catalyst) is not the domain now being traded |
| Provenance | 55 | Excellent *structure* (frontmatter `sources:`, `evidence-class`, `authoritative:`, an authority hierarchy) applied to only ~47% of notes |
| Internal consistency | 70 | A live `Contradictions/` register with severity and deliberate non-resolution is better than most professional research groups manage |
| Mathematical rigor | 75 | The DSR formula matches Bailey–López de Prado exactly; the SPA note correctly warns "the declared universe is the searched universe"; Newey-West and walk-forward notes are correct |
| Empirical support | 15 | Its own results are self-labelled `validated: false`, "BEST-GUESS", "VERY LOW"; 112 declared trials with 22 tested |
| Implementation relevance | **5** | Zero code reads it; zero journals cite it; zero Topstep content; it describes a different codebase in a different asset class |
| Reproducibility | 30 | The Catalyst repo it depends on has an unrecoverable git history on this machine |

**Top valuable notes** (keep, do not modify): `_System/_Source of Truth.md`; `backtesting/Backtesting Master Specification.md`; `_System/11 OVERFITTING CONTROLS.md`; `Quant Fundamentals/{Multiple Testing Problem, Deflated Sharpe Ratio, Newey-West Standard Errors, Walk-Forward Validation, Transaction Cost Modelling}.md`; `backtesting/Data-Snooping Tests (Reality Check & SPA).md`; `Bootstrap Null Models for Strategy Evaluation.md`; `Contradictions/C-0001..C-0007`; `Hypotheses/_Trial Ledger.md`; `_System/{00 SCHEMA, 01 PIPELINE, 09 METRICS STANDARD, 10 RANKING FRAMEWORK}.md`.

**Most dangerous notes** (do not delete — quarantine by not citing): the six `Claims … Batch N.md` machine-generated bulk (4,120 unreviewed claims); `Backtests/Returns/Strategy Returns Ranking.md` and the 138 `*-backtest-result` notes (12-month, best-guess, VERY LOW confidence, but formatted as results tables); `Backtests/Rushed Backtests/**` (74 notes + 42 runner scripts + 70 PDFs from a campaign the vault itself marks `_Superseded`); `Strategies/S-00xx` (34 specs colliding with live strategy IDs); `QuantModel/archive/AUDIT_2026-08-20.md` (375 KB of audit findings about a codebase nobody here maintains).

---

## 4. PART C — DATA ENGINE AND FUTURES MECHANICS (Phases 6–7 / 10–11)

*Measured by the lead after the data auditor was rate-limited. All figures from a read-only pandas probe.*

### 4.1 The futures stores

| | ES | MES | NQ | MNQ |
|---|---|---|---|---|
| rows | 447,600 | 358,845 | 447,596 | 358,845 |
| schema | `t, o, h, l, c, v, contract` — `t` is `datetime64[us, **UTC**]`, tz-aware | same | same | same |
| ET coverage | 2025-06-08 18:00 → 2026-09-10 16:59 | 2025-09-07 → 2026-09-10 | 2025-06-08 → 2026-09-10 | 2025-09-07 → 2026-09-10 |
| **RTH sessions (09:30–15:45)** | **326** | **261** | **326** | **261** |
| duplicate timestamps | 0 | 0 | 0 | 0 |
| out-of-order | 0 | 0 | 0 | 0 |
| bad OHLC (h<l, c/o outside, ≤0) | **0** | 0 | 0 | 0 |
| zero-volume bars in RTH | 7 | 70 | **297** | 40 |
| flat-OHLC bars in RTH (o=h=l=c) | 66 (0.05%) | 208 (0.22%) | **551 (0.46%)** | 127 (0.13%) |
| sessions with < 376 RTH bars | 13 | 9 | 13 | 9 |
| contract months stitched | 5 | 4 | 5 | 4 |

**Bar semantics: START-stamped, verified.** The first bar of a Sunday is 18:00 ET (Globex open) and the last bar of a weekday is 23:59 ET on 327 of the days — the store covers the full 24-hour Globex session and the funnel slices RTH out of it by string comparison. Minute `t` is the bar's opening minute; a bar labelled 15:45 is the 15:45–15:46 bar, so the funnel's "exit at the 15:45 bar's close" is an exit at **15:46 ET**, five hours and thirty-six minutes after Topstep's mandatory-flat deadline is irrelevant (Topstep's 3:10 PM CT = 16:10 ET is later) — but see §7.1: the *model* of the flat rule is wrong in the other direction.

**DST is handled correctly.** The store is UTC and converted on read; the first ET bar on both 2025-11-03 (fall back) and 2026-03-09 (spring forward) is 00:00 ET, i.e. no duplicated or missing hour appears in ET.

**Early closes exist and are silently treated as normal sessions.** Last-bar-of-day counts include `12:59` (3 days) and `13:14` (2 days) — CME early closes. The minimum RTH session is **210 bars**, and `session_frames()` drops sessions with **≤200 bars**, so a 210-bar early close *survives the filter and is evaluated as a full session*. Combined with §7 (Topstep requires flat 15 minutes before an early close), this pattern would carry into a runner.

### 4.2 Rollover — the store is NOT back-adjusted

Every series is a raw stitch of consecutive contract months with the full calendar-spread jump at the seam:

| roll | prev close → new open | jump |
|---|---|---|
| ESU5→ESZ5 (2025-09-11 18:00 ET) | 6591.75 → 6649.50 | **+57.75** |
| ESZ5→ESH6 (2025-12-11 16:00 ET) | 6908.00 → 6967.75 | **+59.75** |
| NQU5→NQZ5 | 24006.75 → 24255.75 | **+249.00** |
| NQZ5→NQH6 | 25714.75 → 25974.50 | **+259.75** |
| MNQM6→MNQU6 | 28471.50 → 28748.00 | **+276.50** |

Magnitudes (0.86–1.08%) are consistent with genuine three-month carry, so these are real spreads and not data errors. **The exposure is contained today** — `futures_discover.py` builds features per session and drops the 3–4 days that carry two contracts, so no window crosses a roll — but the containment is incidental, not designed: nothing in the store, the manifest or the loader marks a roll, and the first multi-day feature (a 5-day momentum, an overnight gap, a daily ATR) added to `features.library()` would silently ingest a 260-point jump as a return. **DATA-01 (P1).**

### 4.3 Quotes and the cost model

`ES_quotes.parquet` (447,600 rows; `t, bid, ask, bid_low, ask_high, spread, c, contract`): median spread **0.25 pt = exactly 1 tick**, p90 **0.50 pt = 2 ticks**, max 3.25 pt, and **30 crossed/locked quotes (ask ≤ bid)**. Only ES was ever fetched.

Cost model as configured (`CostModel.for_contract`, measured by instantiating it):

| | commission/side | RT commission | spread charged | **model RT cost, 1 lot** | official Topstep RT commission (8284213, 2026-07-28) |
|---|---|---|---|---|---|
| ES | $2.00 | $4.00 | 1 tick = $12.50 | **$16.50** | $3.78 |
| NQ | $2.00 | $4.00 | 1 tick = $5.00 | **$9.00** | $3.78 |
| MES | $0.50 | $1.00 | 1 tick = $1.25 | **$2.25** | **$1.22** |
| MNQ | $0.50 | $1.00 | 1 tick = $0.50 | **$1.50** | **$1.22** |

Three defects: (a) the micro commissions are **18% low** against the venue the project intends to trade, and MCL/MGC are 34%/48% low; (b) the ES spread is charged at the **median**, while the 09:30 entry minute the always-in family trades is the widest minute of the day and p90 is double; (c) **MES/NQ/MNQ spreads were never measured** — the 1-tick assumption is inherited from ES. `impact_ticks_per_book=1.0` exists and is never used, because the research path calls only `round_turn_cost()`. **DATA-02 (P2), DATA-03 (P2).**

### 4.4 Contract mechanics — independently verified, and correct

Tick value is **derived** (`multiplier × tick`), not stored, which structurally removes the classic three-way disagreement. All twelve contracts check out against published CME specifications:

| | mult | tick | derived tick value | CME | P&L test (code vs hand) |
|---|---|---|---|---|---|
| ES | 50 | 0.25 | **$12.50** | $12.50 | +0.25 pt × 1 = +$12.50 ✓ |
| NQ | 20 | 0.25 | **$5.00** | $5.00 | −10 pt × 2 = −$400.00 ✓ |
| YM | 5 | 1.00 | $5.00 | $5.00 | ✓ |
| RTY | 50 | 0.10 | $5.00 | $5.00 | ✓ |
| **MES** | 5 | 0.25 | **$1.25** | $1.25 | +1.25 pt × 1 = +$6.25 ✓ |
| **MNQ** | 2 | 0.25 | **$0.50** | $0.50 | +100 pt × 3 = +$600.00 ✓ |
| MYM | 0.5 | 1.00 | $0.50 | $0.50 | ✓ |
| M2K | 5 | 0.10 | $0.50 | $0.50 | ✓ |
| CL | 1000 | 0.01 | $10.00 | $10.00 | ✓ |
| MCL | 100 | 0.01 | $1.00 | $1.00 | ✓ |
| GC | 100 | 0.10 | $10.00 | $10.00 | ✓ |
| MGC | 10 | 0.10 | $1.00 | $1.00 | ✓ |

**14 of 14 P&L cases match hand arithmetic exactly; 0 mismatches.** Micro-vs-mini multipliers are correct and the parent links are right. `spec_for()` raises rather than returning `None` for an unknown symbol. *(One caveat: the CME contract-specification page fetch timed out during the audit, so this is verification against standard published values and internal consistency, not against a page retrieved today — **UNKNOWN by direct retrieval, VERIFIED by arithmetic and by the Topstep commission page's own contract list**.)*

**This is the single cleanest subsystem in the repository.**

### 4.5 Data validation, manifests and hashing

`research/data_manifest.json` top-level keys: `generated_at, source, start, end, symbols_written, symbols_missing, symbols_failed, symbols_on_disk, clamped_bars_total, symbols_factor_check, data`. **No content hash anywhere** (`'hash' in text` → False for all three manifests). `data/` is gitignored and regenerable, so **no ledger row can be tied to the bytes it read**, and `reproducible: true` appears on **0 of 1,653** ledger rows. `dataquality` modules are report-only and are invoked on the futures path (`futures_discover.py:63 fdq.require_usable`) but not on the equity/LEAN path. **DATA-04 (P1).**

### 4.6 Bias exposure from data

| bias | exposure |
|---|---|
| **Survivorship** | **HIGH** on equities: the 16-name intraday universe was chosen in 2026 and backtested to 2016 (PLTR listed 2020-09, COIN 2021-04); `s3_reversal`, `xsect` and `s1_momo`'s `MEGACAP_SLEEVE` all rank a 2026 survivor list. The futures stores are contract-based and immune |
| **Selection** | **HIGH**: one window (2012-01-03) starts 527 of 913 daily runs; four futures contracts over one 1.25-year window |
| **Rollover** | contained today by per-session processing; **latent** (§4.2) |
| **Session** | early closes pass the ≥200-bar filter as full sessions (§4.1) |
| **Timestamp** | **LOW** — UTC storage, correct DST, start-stamped bars, zero duplicates/out-of-order |
| **Missing-data** | **LOW** in futures (13 short sessions of 326); the equity intraday feed's dropped bars are handled by the AUD-05 last-mark logic |
| **Lookahead from data shape** | **LOW** — no daily field is joined onto intraday rows in the futures path; the equity path's known instance was found and fixed |

---

## 5. PART D — BACKTEST ENGINE, LEAKAGE, VALIDATION, PARITY, COSTS (Phases 8–10, 16–17, 30–31 / 12–14, 20–21, 32–33)

### 5.1 What each engine actually does

**`ExecutionSimulator` is not a bar-driven simulator.** No event loop, no bar iteration, no stop/target logic. It is a fill-price + refusal model over a `Quote` (`execute()` 231-280; linear book walk 192-216; passive limits refused 169-190). **The research funnel calls only `round_turn_cost()`.** `execute()`, `fill_price()`, impact, blackouts, the flatten cutoff and position limits have **zero research call sites** — the module docstring's "four things that separate a research P&L from a brokerage statement" reduce, on the path that judged 544 hypotheses, to one constant per round turn.

**The futures funnel** (`futures_discover.py:94-111`): position on bar *i* from `X[i]`, earning `c[i+1]−c[i]` — a fill at the **decision bar's close**. Not lookahead (the ~half-tick optimism is inside the charged spread), but it violates the vault's own specification of "next-bar-open or later". No stops, no targets, no intrabar ambiguity — the family is always-in ±1. Exit implicit at the last RTH bar.

> **BT-01 (P1) — the funnel systematically under-charges every hypothesis it tested.** `turns = int(abs(diff(pos, prepend=0)).sum() / 2)` never charges the forced end-of-session flatten and truncates the odd half-turn. Reproduced: `ones(10)` → charged 0 RT, true 1; one flip → charged 1, true 2. **104 of 136 ES `.v2` ledger rows record `trades=0`** — constant-position rules that in reality trade one round turn per session. On ES at $16.50/RT that is **$5,379 of uncharged cost per rule** over 326 sessions. The 60%-of-gross cost gate was therefore applied to costs that omitted, for the largest sub-family, *the entire cost*.

**The intraday harness** is the best-built backtester in the repo: decide on bar *t*'s close, **fill at bar t+1's open**, orders carried when a symbol does not print (matching a resting live order), forced EOD fills counted and optionally fatal. Features computed once over the full frame and sliced — safe only because every column was verified causal by hand; **no automated causality guard exists for this library** (BT-17).

**LEAN champion**: fill semantics **proven in the engine source** (`QCAlgorithm.Trading.cs:250-277` converts a daily-resolution market order to MOO/MOC to avoid the stale previous close; `EquityFillModel.cs:462,540` fills MOO at `tradeBar.Open`). Decide on D's close → fill at D+1's open. **No fill lookahead.** But `NullSlippageModel` and `MarginInterestRateModel.Null` are the defaults, and `champion.json["stats"]` is the **0 bp / no-financing** column (BT-10).

### 5.2 Leakage forensics

Repo-wide greps for `shift(-`, `center=True`, `merge_asof`, `np.roll`, `resample`, `groupby().transform`, full-frame statistics, scaler fits, `iloc[-1]`, `expanding/cummax/cummin`.

**The known instance is fixed and was handled correctly**: `_opening_range_pos` used the first-30-bar high/low at *every* bar, produced the only funnel survivor ever (t +6.25), was caught, fixed to expanding-then-frozen, and the survivor was **retracted while keeping its trial in the denominator**. That is exemplary.

> **BT-06 (P2) — the guard that was supposed to catch the next one is porous.** `_assert_causal_at` perturbs only `c,h,l,o` (×1.05) and `v` (×3.0). A constructed counter-example suite produced **four of six leaking features that PASS**: next-bar quote imbalance and next-bar spread (the `bid/ask/bid_size/ask_size` columns the library's own `requires` tuples name are **never perturbed**), a bars-until-session-high feature whose extremum lies after the last probe (a uniform multiplicative bump preserves *order*), and a leak below the `np.isclose` tolerance. Worse: `assert_causal`/`audit_causality` are called **only from tests**, never by `futures_discover.py`, and the test fixture sets `bid_size`/`ask_size` to constants, so a genuinely leaking quote feature would produce a constant column and pass.

Everything else checked clean, including `intraday/base.py` column by column, ORB's opening range, `s1_momo`'s `iv_size_factor`/`risk_on`/`horizon_returns`, the VIX/IV/regime labellers, `volume_limits`, and `paper_trade`'s history fetch. Minor hindsight items confined to attribution tables: `ml_f7.py:436` (tercile cut points over the whole test window), `sweep_o1.py:231` (full-sample polyfit contradicting its own "expanding" comment), `sweep_a15.py:245-246` (same-day range as an explanandum). `sweep_f3.py:565-567` crosses a year boundary with 21-session labels **unpurged** (BT-13).

### 5.3 Train / test / validation — every split

| track | split | holdout status |
|---|---|---|
| Futures funnel | **NONE.** All 326/261 sessions feed all four gates | `Stage.VALIDATION` = "eligible for the holdout"; **no holdout exists** |
| `purged_walk_forward` / `cross_validate` / `make_holdout` / `Holdout.spend` | correct by construction (purge = horizon; embargo provably vacuous under walk-forward) | **ZERO research callers; no holdout ledger file on disk** — `docs/VALIDATION.md:96` admits it |
| LEAN champion | IS 2012-2019 / "OOS" 2020-2026, **zero-session gap**, 307-bar warm-up crosses it | **NOT a holdout.** `sweep_s38.py:466-470`: *"Selection ran on FULL 2012-2026, which CONTAINS 2020-2026"*; ≥16 tagged OOS runs plus **189 ledger rows** on that window |
| Intraday A-track | "HOLDOUT" = data **before** 2025-12-15 (reverse-chronological) | **SPENT.** 285 ledger rows starting before the split were recorded after A-4 first ran; a14/a15/a17 then re-split the same data IS 2016-23 / OOS 2024+ |
| ml_f8 | argmax over 20 cells **on the test window**, then a "pre-registered" rule on the winner | test spent by selection (f11/f12 later fixed the discipline) |

**"Walk-forward" in the funnel is `np.array_split(pnl, 5)` with ≥3 chunks positive — a five-block sign test on in-sample P&L, with no refit, no purge, no embargo** (BT-09/STRAT-04). `docs/RESEARCH.md:123` admits this in prose while the funnel table, the ledger notes and the code all call it walk-forward.

### 5.4 Backtest ↔ live parity

| axis | backtest | live |
|---|---|---|
| decision latency | zero | second ≥5 of the next minute; Yahoo feed "about a minute behind", staleness flagged only above 3 min |
| fill | next bar open + **1.5 bps** | MKT at market; **measured +2.22 bps (se 0.80, n=66); breakeven 2.6 bps** |
| sizing equity | re-marked every bar | `nav` fetched **once** at start, reused all day |
| loss limit base | sleeve equity | account NAV (1/`equity_frac` looser) |
| partial fills / rejections | none | real |
| **runs at all** | yes | **NO — `UnboundLocalError` (RISK-01)** |

LEAN champion vs `paper_trade.py`: identical signal module and an order-diff harness (`compare_orders.py`) — genuinely good — but the runner decides at 15:45 on D with closes through D−1 and fills near D's close, i.e. **one full session later** than the backtest (S-19 priced this at ~1.9 CAR points; S-22 all-in 18.8% vs the 24.4% headline).

### 5.5 Cost model classification

| engine | commission | slippage/spread | impact | financing | class |
|---|---|---|---|---|---|
| Futures funnel | FIXED, unsourced, micros 18% low | 1 tick, ES-measured only | none | n/a | **FIXED; entry+flatten RT uncharged** |
| Intraday harness | IBKR schedule + SEC/TAF fitted to **one session's 5 sells** | 1.5 bps vs 2.22 measured | none | none | **STATIC, under-costed** |
| LEAN champion | IB fee model | **ZERO** | none | **ZERO** | **ZERO-COST HEADLINE** |

**Every believed positive number in this repository rests on an under-costed or zero-cost column.**

---

## 6. PART E — STATISTICS, MULTIPLICITY, MONTE CARLO, ML, LEDGER, RESEARCH FACTORY (Phases 11, 13–15, 18–20, 39–40 / 6–9, 15, 18–19, 22, 39)

### 6.1 The repository does not account for its own research history

- `experiments.jsonl`: 1,653 rows, 62 writers, **10 distinct key-sets**; `experiment_id` 0/1653, `family` 0, `trials` 0, `verdict` 0; `commit` is `"unknown"`/`""` on **1,398**; `run_dir` empty on 1,474; `provenance` on **59 (3.6%)**; `reproducible: true` on **0**. `intraday_backtest.py --no-record` exists and `AGENTS.md:91` recommends it. **It is a run log, not an experiment ledger.**
- `experiments_futures.jsonl`: 817 experiments through `registry.Ledger` — the only multiplicity-accounted track — and **817/817 have `provenance: null`** with **0 commit hashes**. `promotion.refuse_cross_environment` would refuse every existing row, which is consistent and is also why no script calls the gate.
- Statistics computed and interpreted: **~10⁴** (daily grids ~5,500; intraday ~1,500 headline + ~10⁴ per-trip cells; ML 700–900; options 400–600; futures 816). Ledger coverage by statistics looked at: **15–25%**; multiplicity-accounted: **~10%**, and 0% outside futures. Examples with zero rows: `sweep_f6` (1,008 regime t's), `sweep_s2` (128 t's), `sweep_f5` (~690).

### 6.2 The ledger's guarantees, tested on a copy

| claimed property | tested result |
|---|---|
| "trial count read from disk, not passed in" | **TRUE** — no keyword; a test forbids one. Genuinely good. |
| trial count cannot be reset | **FALSE** — the family string is free text; a new name gives `trials=1, threshold=1.960`. Already exercised: `futures.es.threshold_grid` and `.v2` hold **byte-identical t-values row for row** (STAT-03) |
| looking counts as a trial | **FALSE** — 50 `verdict()` calls, count unchanged (STAT-10) |
| a re-run is recorded | **FALSE** — the fingerprint excludes data window, code version and cost model, so a corrected re-run is **silently dropped** and the stale row returned. This is *why* the `.v2` split happened: idempotency and multiplicity are in tension and the design resolves it by resetting N (STAT-04) |
| the pass rule identifies winners | **FALSE** — it is two-sided on the t of mean net P&L. **40 of 41 `passed: true` rows have t between −3.44 and −11.92.** One row literally reads "survives 112-trial correction" at t = −11.92. The funnel then reports these as "rejected: cost" — the "ES 124 + 12, MES 127 + 9, NQ 134 + 2, MNQ 135 + 1" line in `journal_futures.md:20` is exactly the per-family count of *significant losers*. **No positive-t hypothesis other than the retracted look-ahead has ever reached gates 2–4** (STAT-05) |
| retraction withdraws the verdict | **PARTIAL** — the stage flips to REJECTED but `verdict.passed` stays `True`; `retract()` accepts non-existent ids; malformed rows are skipped silently, *lowering* N (STAT-16, STAT-26) |

### 6.3 Formula audit — known-answer results

`multipletest.py` is **correct**: Holm/BH/BY reproduce textbook adjusted p-values; White Reality Check size 5.3% at nominal 5%; `expected_max_sharpe` within 1% of simulation; the DSR formula matches Bailey–López de Prado; PBO 0.47 on pure noise and 0.19 with one real configuration. Hansen SPA measured 8.0% size (150 sims, SE 1.8% — **UNKNOWN** whether noise). **It has zero callers outside tests.**

> **STAT-06 (P1) — the HAC correction under-corrects overlapping labels by construction.** Bartlett with `L = h−1` recovers only `h + (h−1)(2h−1)/3` of the `h²` long-run variance — 68% at h=5, ⅔ asymptotically — so t is inflated **×1.22 after "correction"**. Measured size at nominal 5%: **10.6%** (h=5, n=500), **12.1%** (h=21), **35.8%** (h=21, n=60, where the lag is silently capped at n//4). Every "HAC-corrected" figure in `sweep_audit.md` and `validation.py:13-14` is still optimistic: F-3's corrected 0.79 is really ≈0.65; `ml_f8`'s `h10` 2.90 is ≈2.4, **below the bar the audit itself quotes**.

> **STAT-07 (P1) — the Monte Carlo rebuilds intraday paths by division.** `paths._rebuild` re-lays a resampled session P&L onto another day's intraday shape scaled by `k = x / template.pnl`: **inverted when the signs differ** (49.3% of resampled days in one synthetic test) and **unbounded when the template is near flat**. Measured: one template day with pnl +$1 and a −$900 trough produced a median worst mark of **−$51,947** (minimum −$547,270) across 200 paths, and moved the Topstep pass rate from **0.163 to 0.253**. This feeds the funnel's Topstep gate, every `stress()` scenario, `size_sweep`, `break_even_shock` and the promotion gate's `topstep_pass_rate`. Real threshold-rule series contain many near-flat sessions; **the magnitude on the actual ES/NQ data is UNKNOWN** because per-session P&L is not stored in the ledger.

Also: the gate uses **150 bootstrap reps at seed 0, never varied** — SE at the 10% floor is 2.4 pp and at the promotion gate's 35% floor is 3.9 pp, so a gate decision near the floor is a seed artefact (STAT-17).

### 6.4 Selection contamination, in the repository's own words

| category | quote |
|---|---|
| winner kept after the fact | `journal.md:6548` (A-0) *"Trend-following loses before costs … **Their inverses are the edge**"* — the deployed mix was a sign flip chosen after reading 62 sessions and deployed the next morning |
| measured negative, still deployed | `journal.md:6169` (A-4) *"**The deployed sleeve loses money on the sessions it was not tuned on.** −$813/day over 77 sessions"*; `:5834` (A-10) *"with 2,686 sessions the sleeve is not unproven, it is negative"* |
| OOS is a fit | `journal.md:1474` (S-33/AUD-11) *"**every shipped parameter was chosen on full-period tables, so the published OOS is a sub-period of a fit**"* |
| OOS argmax | `journal.md:1150` (S-38) *"the shipped value is the out-of-sample argmax of its own axis on 3 of 6 fitted axes"*; `:701` (S-40) *"rank 1 of 36 [OOS] … rank 24 of 36 [IS] … hindsight in full"* |
| post-hoc justification | `journal_options.md:504` (O-7) *"Correction filed against this track's own record. O-6 appended a second justification"*; `ml_f16.py` docstring *"the 3 columns were chosen **AFTER reading the test window**"* |
| window reuse | 189 S-track rows on 2020-2026; 61 intraday IS/OOS pairs at one split (36 on the deployed strategy); 189 options rows on one window |

**Expected max |t| over N independent nulls:** N=136 → 2.85; N=816 → 3.38; N=1,653 → 3.57; N≈5,000 → ~3.9. Against that: the champion's own note says *"nothing in the comparison reaches |t| = 2"* and LEAN's PSR is 33.2%; A-17's PASS collapses under the critic's block-length attack (median year +2.5%, 5/10 years positive, sign test p = 1.000, 2022 holding 44 of 118 tail sessions); O-7's decisive leg clears its per-clock Bonferroni by **0.037 t** and flips to PARTIAL under the pre-registered secondary state variable; F-1's IC t 4.74 is real, non-overlapping — and **net −$2,206/day after commission**.

### 6.5 "0 survivors" is a power statement, not a market statement

At n = 395 sessions, σ ≈ $300/session for 1 MNQ held through RTH (se = **$15.1/session**):

| bar | MDE at 80% power | power to detect a real $20/session edge |
|---|---|---|
| single test, 1.96 | $42/session | 26% |
| family bar at 136 trials, 3.56 | **$66/session** | **1.3%** |
| honest all-grid bar at 816, 4.01 | $73/session | **0.36%** |

The cost gate compounds it: a genuine $20/session edge at the grid's ~6 round turns/day already fails `MAX_COST_SHARE` regardless of significance. **A correctly functioning funnel returns 0 survivors on a market with no edge *and* on a market with a modest one.** What it does prove: the plumbing runs end to end, the ledger counts, the look-ahead was caught, and single-feature threshold rules are cost-dominated at bar frequency.

### 6.6 ML

No model beats its simplest baseline anywhere, **by the track's own record**: F-12 *"The free baseline beats the ML model at every rung"* (trailing 20-bar ATR t +1.41/+1.28/+0.93 vs the model's +1.31/+1.06/+0.49; the two are Spearman +0.945 correlated, "the refinement is the part that loses money"); F-3 *"this time the hand-built signal wins"*; F-17's pooled arm sits **below its own scrambled control** ($310 vs $319/day); F-14 *"scrambled flow is free, real flow costs $199/day"*; F-23 found **0 of 6 gate admissions in the track's history turn on a resolvable margin**. F-1 is the exception — a real, non-overlapping OOS IC of +0.011 at t 4.74 — and it is worth 0.8 bps against 2.4 bps of cost. Zero purge/embargo in all 16 F files; 5 hand-written GBDT cells; no calibration; prediction caches went stale (F-19). **The ML track's most valuable output is negative and it says so.**

### 6.7 The research factory

`AGENTS.md:50-68`: read backlog + `champion.json` + **the last 20 lines** of a 1,653-row ledger + the latest journal → *"pick the highest-value open hypothesis, or a promising variation of the champion"* → backtest → *"compare with the champion"* → promote on CAR (no significance test, no multiplicity, no OOS) → journal → repeat, six scopes in parallel, ~100 commits/day, with an LLM performing the interpret-and-choose-next step. **This is GENERATE → BACKTEST → SELECT BEST → MODIFY → REPEAT with hill-climbing stated as policy.**

Ways a failed experiment can vanish, all tested or observed: never write it (`--no-record`); `verdict()` without `record()`; rename the family; re-run under the same fingerprint (dropped); edit the plain-text ledger; a malformed row lowers N; restore `champion.json` from git; free-text "DIAGNOSTIC" tags. **Observed live during this audit:** uncommitted ledger rows and three untracked scripts disappeared from the shared tree with HEAD unchanged and no trace in `git log`.

---

## 7. PART F — TOPSTEP (Phases 21–24, 45–46 / 23–26, 46)

Every official value below was retrieved **2026-09-13** from help.topstep.com / topstep.com / gateway.docs.projectx.com. **The vault contributes nothing** (§3.4), so the OBSIDIAN column is "none" throughout.

### 7.1 Current-rule table — $50K Combine (abridged; 45 rows in full)

| rule | CODE (`topstep.py`, self-assigned tier) | CURRENT OFFICIAL (2026-09-13) | STATUS |
|---|---|---|---|
| Profit target $3,000/$6,000/$9,000 | `:289-293` DOC | topstep.com/no-activation-fee; corroborated by 10657969 | **VERIFIED** |
| MLL $2,000; trails EOD balance; **intraday breach on unrealized**; locks at **starting balance** | `:165-188` | 8284204 — *"rises as your end-of-day balance grows, but never moves down"*; *"including on unrealized P&L … liquidated immediately"*; *"Once it reaches your starting balance, it locks permanently"* | **VERIFIED — and there is NO "+$100"** on any official page. The brief's "+$100" is not Topstep's rule |
| MLL → $0 after first payout | `:354-362` | 8284233 | **VERIFIED** |
| DLL optional $1,000; forced break, not a violation | `:191-215` DOC citing **article 8284207** | values confirmed at **10490293**; **8284207 returns HTTP 404** | values VERIFIED / **citation INCORRECT** (`README.md:68` says it "still resolves") |
| Consistency 55% | `:218` | 8284208 / 8284197 / 8284099 | **VERIFIED 55%**; the owner's 50% is OUTDATED |
| Consistency denominator | `"total"`, comment claims *"RESOLVED by the article's own worked example"* | both examples on 8284208 have total = target ($3,000) and cannot distinguish; 8284208/8284197 say *"of your Profit Target"*, 8284099 says *"of total profits"* | **CONTRADICTED between official pages; the code's stated reasoning is invalid** (its choice is the stricter one, so the outcome is safe) |
| Consistency boundary | `pct <= limit` | 8284208 *"at or below"* vs 8284197/8284099 *"below"* | **CONTRADICTED**; code took the lenient reading; the twin **passes at exactly 55.00%** |
| Max position 5 minis / 50 micros, **10:1**, **per account** | `:157-161` values DOC; applied as **per-symbol** caps at `:470-474` | 8284197 | values VERIFIED / **ENFORCEMENT INCORRECT** |
| Permitted products | **no whitelist in code** | 8284206: ~55 roots, *"No products outside this list"* | **MISSING** |
| **Mandatory flat 3:10 PM CT** (last entry 3:08) | `flat_before_close_minutes=15` against a calendar close the repo reports as **16:00 CT → flat at 15:45 CT** | 8284206 | **INCORRECT — 35 minutes after Topstep liquidates.** (The brief's "4:10 PM CT" is also wrong; it is 3:10 PM CT) |
| XFA scaling plan | `XFA_SCALING = ()` OWNER; twin runs the XFA at **50 micros from $0** | 8284223: *"$50K XFA, 2-lot Scaling Plan: 2 Minis, OR 20 Micros"*; ladder published only as an image | UNVERIFIED ladder; **model FLATTERING** |
| Payout minimum **$125** | absent | 8284233 | **INCORRECT** — the twin paid **$75** |
| "≥ $0.01 net **since last payout**" | tests `balance > 0` | 8284233 | **INCORRECT** — eligible with net −$450 since the payout |
| Consistency-route 3-day restart | `trading_days` never reset; denominator = balance | 8284233 *"your 3-day count restarts"* | **INCORRECT** — re-eligible the next day |
| Commissions | ES/NQ **$4.00** RT, all micros **$1.00** RT ("indicative") | 8284213: ES/NQ **$3.78**, **MES/MNQ $1.22**, MCL $1.52, MGC $1.92 | **INCORRECT** — micros 18–48% low |
| Fees over time | one flat fee per attempt | rebill **every 30 days** (8284121); **$149** XFA activation (14289835/8284217); **$29/mo** API (11187768) | **INCORRECT** — a 160-session Combine was charged $49 |
| **Automation** | adapter exists; U1 filed as a *blocking unknown* | 11187768: bots allowed subject to the HFT ban. **10657969: "Automated trading via the ProjectX API is prohibited in the LFA."** ToU: VPS/VPN/remote prohibited, personal device only | **KNOWLEDGE FLAW** — the repo's blocking unknown has a published negative answer it never recorded |
| News / elevated-vol / holidays | none modelled | 13613539 (CPI ±5 min; CL/GC cut to 3; SI/HG/PL blocked); 13350348 (flat 15 min before an early close) | **MISSING** |

### 7.2 Digital twin — boundary simulation

**Matches official:** balance exactly at MLL → liquidated; one cent above survives; one cent below liquidated; intraday unrealized touch then recovery → **liquidated** (the `EOD_TRAIL_INTRADAY_BREACH` semantics are right — the threshold advances only in `settle_day`); lock at $50,000 with no +$100; XFA lock at $0; MLL → $0 on payout; DLL as a forced break; correct precedence when MLL and DLL are crossed in the same mark.

**Diverges, every one in the flattering direction:** 30 mini contracts accepted on a 5-mini account (5 each of ES/NQ/RTY/YM/CL/GC); 5 ES + 45 MES accepted (9.5 mini-equivalents); 50 ZN / 50 6E / **50 BTC** accepted (no whitelist); $75 payout recorded; consistency-route re-eligible the day after a payout; standard route eligible with net −$450; fresh XFA at 50 micros against a published 2-lot; 160 sessions charged one $49 fee; consistency passes at exactly 55.00%.

### 7.3 Objective and pass-probability capability

The default objective (`venues/propfirm.Scoring`: `value_weight=1, ruin_penalty=0, days_penalty=0, max_p_ruin=None`) is **expected net capital after fees, with no ruin constraint and no time cost**. `paths.best_size` maximises `p_first_payout`. Two inconsistent floors coexist (0.35 in `promotion.py:159`, 0.10 in `futures_discover.py:57`), both on *Combine pass* — the outcome the twin's own docstring says "earns nothing". Position size can be compared honestly; **stop distances and exits cannot** (no re-simulation).

The machinery for Phase 24 exists — block bootstrap over 325 real MES sessions with minute paths, stress/size/clustering sweeps — and produced an **honest negative** (p_pass 1%, p_first_payout 0%, p_liquidated 100%, HAC t 0.23). **It cannot yet produce an honest positive**: eight biases all point the flattering way (XFA size, $125 minimum, consistency restart, net-since-payout, fee model, MES commission, an undisclosed horizon equal to the sample length ≈ 15 months, minute-close marks) and the path resampler is defective (§6.3). **Major missing capability.**

### 7.4 Enforcement and legitimacy

Every Topstep check is **advisory**: `PropFirmRiskEngine.evaluate/must_be_flat/in_blackout` have no caller that trades; `TopstepRules` is attached only to the dry-run ProjectX venue whose `submit` raises `NotPermitted`. **There is no Topstep P0 solely because nothing can reach a Topstep account today.**

Legitimacy: nothing in the repository currently depends on gaming the evaluation, and the code refuses rather than guesses when a rule is unknown — good. Two latent hazards: (a) the default objective with unlimited `max_combine_attempts` and a `size_sweep` that raises p_pass with size while p_liquidated stays 100% **is** the "hit the MLL, buy another, repeat" pattern that 10305426 names as prohibited conduct; (b) nothing guards against a research loop converging on tight brackets / auto-breakeven whose edge exists only in SIM fills, which the same page names.

One real incident: on 2026-09-13 08:49 UTC the intraday preflight failed closed with `NameError: NAF` because the rulebook was mid-edit in the shared tree (the constant landed 14 minutes later). The gate worked; the repo found it and narrowed the gate (E-11). **The fail-closed preflight is proven by a real event, not just by a test.**

---

## 8. PART G — RISK, EXECUTION, RECOVERY, ADVERSARIAL (Phases 25–29, 35, 46 / 27–31, 37, 47)

### 8.1 The two P0s (proven)

**RISK-01 — `scripts/intraday_trader.py:891`.** `symtable`: `t` is_local=True in `live()`. AST: LOADS at 891, 923, 929; STORE at 922 only; the `while True:` loop spans 887–931. **First iteration → `UnboundLocalError`.** Introduced `80aa3c1` (Sat 2026-09-12 15:33), after the last live session (Fri 09-11). The launcher preflight replays `replay_book()`, which never enters `live()`; **no test in the suite drives `live()`** (verified: zero test files reference it). Result on Monday: connect → cancel stale orders → reconcile → flatten leftovers → crash, exit 4. Fails closed; the sleeve does not trade.

**RISK-02 — `intraday_trader.py:349` + `:444` with `brokers/ibkr.py:80`.** `self.open = self.adapter.open` aliases; `settle()` ends `self.open = still`, rebinding. From the first `settle()` (which runs before the first order) the adapter's list and the executor's list diverge permanently. Fake-IB reproduction: **4 bars → 4 orders / 4,000 shares** for a strategy that wanted 1,000 once; `book.pos == {}`; governor `daily_pnl 0.0`; the 15:38 flatten computes `{}` → **position carried overnight**. Bounded only by IBKR buying-power rejections. **Masked today only by RISK-01.**

### 8.2 Enforced vs advisory — the honest table

| control | on a real runner path? | verdict |
|---|---|---|
| daily loss (2.5% NAV) | yes, intraday only (runner check + one chain limit) | ENFORCED for MARKET entries; **blind under RISK-02**; FLATTEN bypasses |
| per-symbol / gross weight caps | yes, pre-intent | ENFORCED by runner code, scaled by an unbounded `equity_frac` |
| outside-RTH refusal; HALT files; approval-file existence; authority-at-construction | yes | ENFORCED (approval is **existence-only**) |
| stale data | partial (unmarked position → `DATA_UNAVAILABLE` for entries) | PARTIAL; the `DATA_STALE` switch has no caller |
| broker/local mismatch | startup only; no periodic reconcile | PARTIAL |
| disconnect | 10 × 15 s reconnects then `break` "book left as is" — no flatten, no HALT, no switch | **ADVISORY (alert only)** |
| max risk/trade, profit stop, drawdown, MLL buffer, contract & micro limits, trades/day, consecutive losses, cooldown, volatility scaling | **NO CALLER**; `AccountView.trades_today/consecutive_losses/risk_per_contract` never populated | **ADVISORY** |
| bracket verification | **NO CALLER**; neither runner places a stop (`ibkr.py:147-161` builds MKT/LMT/MOC/MOO only) | **ADVISORY — every deployed position is UNPROTECTED all day by the module's own rule** |
| idempotency journal / `intent_id` | **NO CALLER** | **ADVISORY** |
| session readiness (`lifecycle`) | **NO CALLER** (`__main__.py:241` prints the list) | **ADVISORY** |
| `paper_trade.py` chain | `RiskChain()` at `:668` and `:797` | **EMPTY — no risk engine at all on the 15:45 runner** |

### 8.3 FLATTEN is a trusted label (RISK-04, P1)

`risk.py:85-89` lets any `OrderType.FLATTEN` bypass every engine and every tripped switch; nothing verifies that a FLATTEN's side and quantity **reduce** a broker-sourced position; `LiveExecutor.submit(flatten=True)` labels **every order in the batch**; the in-loop flatten derives from `book.pos + pending`, never from the account. Proven: a BUY 5,000 labelled FLATTEN passed a halted, breached governor; a +700 BUY reached the venue past a halted governor because its dict carried `flatten=True`. **With a wrong book — which RISK-02 guarantees — the unrefusable exit becomes an unrefusable entry.**

### 8.4 Adversarial probes (in memory, against fakes)

- **Governor:** NaN `daily_pnl` / `drawdown` / `distance_to_mll` / `risk_per_contract` all **pass**; NaN or negative `Limits` silently disable or invert a limit (a negative `max_daily_loss` denies *winning* days); `max_notional` skips on `None`, contradicting the module's own "unknown is a denial"; a naive/aware datetime mix raises *out of* the chain; `OrderIntent` accepts NaN/inf/0 quantities; `reset(by="bot")` and `reset(by="\u200b")` accepted; `LimitEngine.limits` and `RiskChain.engines` are plain mutable attributes (`g.engines.clear()` disarms everything). None is reachable from the runner today (marks are `isfinite`-filtered), but *"PROBABLY OKAY IS NOT A STATE"* is false for NaN.
- **Sizing:** `risk = stop_distance × multiplier × contracts`, **no cost term**; `stop_distance=1e-300` → ~1e302 contracts "available"; `enforce()` **raises `ValueError`** on a NaN `distance_to_mll` instead of returning a coded refusal. No runner uses it; the intraday sleeve has no stop at all.
- **State machines:** the Phase-27 states `ENTRY_PENDING/POSITION_OPEN/EXIT_PENDING/FLAT` are absent; `PARTIALLY_FILLED → CANCELLED` is terminal and drops the filled part's exposure; **no fill ids**, so a replayed fill is indistinguishable from a venue overfill; `fill(nan)` accepted; `Readiness` is caller-asserted with nothing binding `protection_verified` to `protection.verify`.
- **Protection:** with `avg_price=None` the price test is skipped and a sell stop **above** a long's entry reports **PROTECTED**; a NaN stop price reports PROTECTED (NaN comparisons are False); a stop-limit with limit 1.0 reports PROTECTED; there is no account field; **no runner calls it and no fail-safe is ever constructed.**
- **Locking/idempotency:** exactly-once holds under 8 threads and 2 processes at normal speed, but the stale-lock break is **non-exclusive** (waiter B acquired at 12.6 s while A still held; A's `finally` then unlinked B's lock) and a torn `pending` row lets the same intent be claimed again — precisely the crash-mid-write case the journal exists for.
- **Authority:** `Authority(Mode.EXECUTION_READY)` constructs directly; `write_approval()` + in-process env + `for_live()` reach EXECUTION_READY in three lines; `adapter.requires` is reassignable; `ProjectXAdapter.submit` is overridable by a subclass. The ladder blocks **configuration accidents, not code** — `ARCHITECTURE.md` and `EXECUTION.md` claim more. The AST "no SDK above `brokers/`" test walks `quant_brain/` only; the runners import `ib_async` directly and `exec_module` strategy code **inside the process that owns the IB socket**.

### 8.5 The live state file was written by a unit test (RISK-03, P1)

`live/state/governor.json` carries `_scope: paper`, `published_at 2026-09-13T17:39:36Z` (a Sunday, no session) and `max_daily_loss 25,000` = 0.025 × the test constant `NAV = 1_000_000`. Path: `tests/test_intraday_gates.py:235 make(mode="live")` → `persist=True` → `_publish_governor` → `StateStore.open(StateScope.PAPER)` → the real file. `conftest.isolate_live` patches log/notify/HALT/approval but **not `StateStore`**. The 09:25 gate and the background suite will overwrite the live sleeve's published status during a session, so `risk status --scope paper` can display a test's "halted: false" during a real halt.

### 8.6 Recovery

Crash yesterday with an open position, reboot at 09:30: approval → connect → **DU-prefix check** → NAV read once → load book → cancel every `orderRef == "INTRADAY"` order (good) → `startup_reconcile` adopts account positions (AUD-08, verified) → stale-book flatten (booked, because it is the *first* `settle`) → **crash at `:891`**. Mid-session disconnect: reconnect ×10 then `break` with no flatten, no HALT, no switch, no re-reconcile, and `LiveExecutor.open` never rebuilt from `ib.openTrades()`. `paper_trade.py` reads positions fresh (good) but never queries open orders, so a rerun after a crash can duplicate a working MOC/MOO; its HALT/`--flatten` branch closes **every** account position including the other sleeve's before the ownership filter runs.

---

## 9. PART H — SECURITY, REPRODUCIBILITY, TESTS, AI SAFETY (Phases 32–34, 46–47 / 34–37, 47)

*Measured by the lead after the security auditor was rate-limited. **No secret value was printed at any point.***

### 9.1 Secrets — clean

| check | result |
|---|---|
| secret-shaped patterns in **all tracked files** (api key / token / bearer / password assignments ≥12 chars, JWT `eyJ…`, `BEGIN … PRIVATE KEY`, `xox[baprs]-`, `sk-…`, `AKIA…`) | **0 matches** |
| the same patterns across **all of git history** (`git log --all -p`) | **0 matches** |
| `live/secrets.env` (283 bytes, exists, never opened) | gitignored `.gitignore:14`; **0 commits ever touched it** |
| `.env`, `live/secrets.json` | gitignored `.gitignore:10`, `:13`; **0 commits** |
| IBKR account identifiers in tracked files | 2 files (`scripts/paper_trade.py`, `tests/test_reconcile_state.py`) — paper `DU…` form, low sensitivity, but they are account identifiers in a public repository |
| credential redaction in code | `projectx.Credentials`/`Session` redact in `__repr__`/`__str__`; a test asserts no credential appears in the package source |
| `.env.example` | placeholders only; correctly states nothing loads a `.env` |

**This is the strongest dimension in the audit.** The one blemish is the paper account id and a stray untracked 942-byte `Usersashur.openclawspawn-hook.log` in the repo root recording process spawns.

**`.gitignore` in full** (relevant): `results/`, `*.log`, `__pycache__/`, `.env`, `*.key`, `*.pem`, `live/secrets*.json`, `live/secrets.env`, `live/log/`, `live/state/`, `live/HALT`, **`live/APPROVED_PAPER.md`**, `live/alerts.json`, `data/`. **`Quant Brain/` and `.obsidian/` are not listed** (OBS-01).

> **SEC-01 (P2) — the sole human authorisation gate is an untracked file.** `live/APPROVED_PAPER.md` is gitignored, so any process with write access can create it and **its creation leaves no trace in version control**. It is checked for *existence only* (`paper_trade.py:779`, `intraday_trader.py:799`, `intraday_launch.py:377`), and its text authorises a champion (`S-12`, hash `5246804e…`) that **no longer trades** (the running champion is S-18, `a6d6224c…`).

### 9.2 Reproducibility — the weakest dimension after research process

| requirement | state |
|---|---|
| dependency pinning | **NONE.** No `requirements.txt`, `pyproject.toml`, lockfile or `environment.yml`. The import census shows pandas, numpy, plus `ib_async`, `yfinance`, `pyarrow`, `scikit-learn`, `pythonnet` reachable only by reading imports |
| interpreter pinning | documented in prose (`ruff.toml:19-20`, `pyrightconfig.json:5-6`), enforced nowhere; a third interpreter (3.13) sits in the vault |
| dataset hashing | **NONE** — manifests carry file lists and dates, no content hash; `data/` is gitignored and regenerable |
| seeds | `seed=0` hard-coded in the funnel's Monte Carlo; never varied; ML seeds fixed but unswept |
| commit hash in results | 255 of 1,653 equity rows (15%); **0 of 817** futures rows |
| environment fingerprint | `provenance.env_key` exists; present on 59 rows (3.6%); **`reproducible: true` on 0 of 1,653** |
| CI | none |

**Another machine cannot reproduce any result in this repository.** It would need: an unpinned Python environment reconstructed by hand, a 3.5 GB regenerable data store with no hash to check against, a locally built LEAN engine, IBKR history entitlements and Alpaca keys.

### 9.3 Test suite — what is NOT tested

1,895 tests / 65 files, all green at HEAD, `--strict-markers`, one custom marker (`runner`, applied by module name in `conftest`). What that green does **not** cover:

- **No test drives `intraday_trader.live()`** — verified. This is exactly why RISK-01 shipped.
- **No property-based testing.** The word "hypothesis" appears in 3 test files as the domain term; `from hypothesis` / `@given` → **zero hits**.
- **No mutation testing, no coverage measurement** (no `.coveragerc`, no `--cov`, no `pyproject.toml`).
- **No end-to-end test that a risk refusal stops `placeOrder`** on a runner: `placeOrder` appears in `test_qb_adapter.py` and `test_qb_venues.py` only — the property is asserted against the adapter and the fakes, never against `Trader.step`.
- **No test against a real IB Gateway**; ProjectX is tested only in dry-run.
- **~520 tests (31%) exercise the 13 modules nothing calls** — they defend properties of code that cannot fail in production because it never runs.
- **6 test files depend on wall-clock time** (`datetime.now`/`date.today`), a latent flakiness and a latent gate failure at 09:25.
- **The `isolate_live` fixture does not redirect `StateStore`** — proven by `live/state/governor.json` (§8.5). Tests write into the live state directory.
- Tests that assert implementation details rather than invariants exist (e.g. `test_commit_scope.py:181` asserts the temp index filename starts with `next-index-`; `test_daily_unsizable.py:57,86` assert exact ticker and reason strings).

The gate itself (`scripts/qb_check.py` + `.githooks/pre-commit`) is real, fails closed, and was **proven by a live incident** (§7.4) — but it is bypassable with `--no-verify`, which its own message invites; it skips the replay preflight and `compare_orders`; and its "changed elsewhere" ruff stage is routinely red on other tracks' uncommitted files, training the reader to ignore a red gate.

### 9.4 AI safety — research autonomy vs execution authority

Verified deployment reality: one OpenClaw agent (`quant`), `workspace = the repo`, three Windows scheduled tasks running **agent-edited Python with no LLM in the loop** (09:25 intraday, 15:45 daily, dashboard at logon); the OpenClaw Gateway and its watchdog are currently **Disabled**. The agent's own directive files (`SOUL.md`, `IDENTITY.md`, `USER.md`, `MEMORY.md`, `DREAMS.md`, `memory/dreaming/**`) are **tracked in the repository the agent edits**.

| capability | mechanism | verdict |
|---|---|---|
| enable live IBKR trading | `account.startswith("DU")` in the runner; the Gateway login is human-held | **PREVENTED BY INSTRUCTION** in code; the real lock is the human-held login |
| enable live ProjectX trading | no order endpoint exists; `submit()` raises | **PREVENTED BY MECHANISM** (absence of code) |
| alter risk limits | `intraday_common.py:69-74` constants, `live/intraday_config.json` (3 agent commits, unbounded `equity_frac`), the `Governor(Limits(...))` built in the runner | **NOT PREVENTED** |
| change Topstep/MLL logic | `topstep.py` Rule values are code; the pinning tests were **co-edited in the same commits** (`b749cbb`, `752ffb6`); no test fetches a source | **PREVENTED BY INSTRUCTION ONLY** |
| insert credentials | `.gitignore` + env-only reads; **no secret scan in the pre-commit hook** | PARTLY BY MECHANISM |
| bypass risk | any code in `scripts/`/`algorithms/` can call `ib.placeOrder`, label an intent FLATTEN, or set `routed.risk = RiskChain()`; strategies are `exec_module`d in the socket-owning process | **NOT PREVENTED** |
| alter OOS data | `data/` gitignored, unhashed | **NOT PREVENTED** |
| delete or hide experiments | the ledger is append-only *by convention* in a plain tracked file; `results/` gitignored; unsigned commits; branch protection **UNKNOWN** | **PREVENTED BY INSTRUCTION ONLY** |
| **promote a strategy into paper execution** | `evaluate.py --promote` applies criteria stored **in the same agent-editable `champion.json`**, writes `champion.json`, and the 15:45 runner trades whatever it names; the approval file is existence-only and names a superseded champion | **NOT PREVENTED — no human step exists between an agent promotion and paper execution** |
| create false conclusions | journals/reports/backlog are free text; nothing links a claimed number to a ledger row | **NOT PREVENTED** |

> **AI-01 (P1).** Research autonomy and execution authority are separated by **markdown**, a `DU` string prefix, and a human-held Gateway login — not by mechanism. The one genuine mechanism (the pre-commit gate) is bypassable and provenance-blind. Add to this OBS-02: an imported third-party agent-orchestration payload with tool-call hooks sits inside the working tree, outside every gate.

---

## 10. PART I — STRATEGY INVENTORY AND ECONOMIC VALIDITY (Phases 12–13, 36–37 / 16–17, 38)

| strategy | mechanism | claimed edge | own-funnel verdict | motivation | STATUS |
|---|---|---|---|---|---|
| **`s1_momo`** (LEAN daily champion, **paper-trading since 09-09**) | 20/60/120/252-day momentum over 9 ETFs + SPY vol-regime switch + inverse-vol sizing | CAR 24.4% / Sharpe 0.99 / DD 23.7% / **PSR 33.2%**, at **0 bp and no financing** | in-sample by AUD-11/S-33; runner one session late (~1.9 CAR); "nothing reaches \|t\| = 2"; **0 of 913 runs cover 2000-02 or 2008-09** despite 1998+ data | BOTH | **INSUFFICIENT EVIDENCE** — LEAN Beta 0.54 / Alpha 0.13: mostly equity beta plus regime timing |
| **`orb`** (intraday, **deployed at `equity_frac 0.25`**) | 15-min opening-range breakout on ≥1.2× volume | A-6 +$322/day on a 9-month fit | **A-10 −$289/day t −1.17 on 2,686 sessions; D-5 −$310/day t −1.24**; live −$6,779 (09-10) and −$202 | EMPIRICAL | **REJECTED BY OWN FUNNEL, STILL DEPLOYED** as a "plumbing test" |
| `late_momo` (deployed as a fade until A-10) | last-hour continuation/fade of a ≥60 bp move | — | **−$468/day, t −7.38**, negative in all three regimes | THEORETICAL (closing-auction/LETF flow); **sign chosen empirically** | REJECTED — and the |t| = 7.4 says the *opposite* trade was systematically right. **Never costed.** |
| `vwap_trend`, `gap_fade`, `lev_revert`, `xsect` | VWAP continuation; gap half-fill; LETF stretch reversion; intraday cross-section | — | alloc 0; t 0.03; "leveraged ETFs do not revert intraday"; "an edge worth a fourteenth of its own cost" | mixed | REJECTED. `lev_revert` cites a mechanism (LETF rebalancing) that predicts the **opposite sign** |
| ML F-1…F-24 | GBDT decile books | F-16 $412/day at t 1.97 (refused) | F-23: **0 of 6 gate admissions resolvable**; scramble ranked above real arms | EMPIRICAL | REJECTED |
| A-17 de-risk switch (overlay) | expanding 5% quantile regression on pre-open tape | ES5 cut +11.08% | C-11: 2022 carries it; median year +2.5%; 5/10 years; sign test p = 1.000 | THEORETICAL (vol clustering) | **PROMISING BUT INCOMPLETE** — a sound overlay with no winning book beneath it |
| Futures `threshold_grid` ×6 | `feature ≥ thr` → ±1 | none claimed | 544 tested, **0 survivors**; 1 look-ahead retracted | UNEXPLAINED (grid) | REJECTED BY DESIGN — a funnel calibration, not a strategy search |
| Futures `intraday_momentum` baseline | first-30-min direction, 10:00 entry, 1 MES | pre-registered | HAC t **+0.23**; twin p_pass 1%, p_liquidated 100% | EMPIRICAL | REJECTED |
| Options O-1…O-10 | 0DTE VRP, IV gates, chain signals | **O-6 PASS**: option-implied magnitude forecasts realised \|move\| (DM t +3.5…+4.2, 5/5 clocks) | O-5: *"cut the round trip 68× and the edge shrank to match"*; O-7 marginal | BOTH | REJECTED as an edge; **O-6 is real information with no product** |
| Vault `S-0001…S-0034` | YouTube/paper templates | 12-month "BEST-GUESS / VERY LOW" table, `validated: false` | not referenced by the repo | — | INSUFFICIENT (and not claimed as evidence by its own author) |

**Economic validity.** `s1_momo` exploits documented momentum and vol-timing premia — robust to its own parameter perturbations, **UNKNOWN across regimes** (no run before 2012), **FRAGILE to execution** (slippage, financing, a one-session lag). `orb` exploits nothing that survived measurement; the other side is market makers at 0.5–1 bp half-spread on the most liquid names in the world, and breakeven is 2.6 bps against 1.5 charged. O-6 is the textbook IV→RV channel, priced away by 0DTE spreads. **The mandate itself ("volatile, high-turnover, highly liquid") selects for exactly the class the repository's own cost analysis kills.**

**The one unexploited lead in the entire repository:** the strongest intraday statistic (late-day fade, −$468/day at **t −7.38**, negative in all three regimes, on 2,686 sessions) implies that the **continuation** trade was systematically right; it has a real mechanism (closing-auction and LETF rebalancing flow *amplifies* the day's move); and it was **removed rather than inverted and costed**.

---

## 11. CONTRADICTION REGISTER (Phase 39 / 5)

| # | SOURCE A | SOURCE B | conflict | which is correct | severity |
|---|---|---|---|---|---|
| 1 | `ARCHITECTURE.md` §4a-ii, `docs/IMPLEMENTATION_REPORT.md` "The architecture now" | `intraday_trader.py:346-378`, `paper_trade.py:797` | Documented pipeline (sizing → intent_id → journal → governor → OrderMachine → verify → Reconciler) vs one chain limit / an empty chain and no journal | **CODE**; the docs describe a target | **P1** |
| 2 | `docs/IMPLEMENTATION_REPORT.md` "one live path now runs through it"; scorecard Execution Safety **9.0** | RISK-01 (the path crashes), RISK-02 (fills invisible) | A layer declared operational on a runner that cannot complete one loop iteration | **CODE** | **P0** |
| 3 | `ARCHITECTURE.md:125,259,354-355` | HEAD | "runners build `ib_async` inline", "no runner has been wired to the governor" — both false | **CODE** | P2 |
| 4 | `docs/ARCHITECTURE_AUDIT.md` "Dead code: 2 items", "~90 scripts", "1,258 rows" | measured 13 modules / 9,110 lines, 135 scripts, 1,653 rows | The Phase-0 audit under-counts its own subject | **MEASUREMENT** | P2 |
| 5 | `topstep.py:267-281` "RESOLVED … by the article's own worked example" | 8284208 (both examples have total = target) | The stated resolution is logically impossible from that evidence | **OFFICIAL**; the choice is safe, the reasoning is not | P2 |
| 6 | `topstep.py` DLL rules cite article **8284207** (DOC tier); `docs/topstep/README.md:68` "still resolves" | HTTP **404** twice | A DOC-tier provenance claim pointing at a dead page | **OFFICIAL** (10490293) | P3 |
| 7 | Official 8284208 *"at or below 55%"* | Official 8284197 / 8284099 *"below 55%"* / *"of total profits"* | Topstep contradicts itself on the boundary and the denominator | **UNKNOWN — flag, do not guess.** Code took the lenient boundary | P2 |
| 8 | `docs/topstep/API_UNKNOWNS.md:22-42` U1 "blocking unknown: can a live account trade via API?" | Official 10657969 *"Automated trading via the ProjectX API is prohibited in the LFA"* | A published answer filed as unknown | **OFFICIAL** | **P1** |
| 9 | `search.py:96` "SURVIVED to holdout"; `Stage.VALIDATION` = "eligible for the holdout" | `make_holdout` has zero callers; no holdout file exists | A funnel stage naming an artefact that has never existed | **CODE** | **P1** |
| 10 | The funnel's `walkforward_ok` gate; ledger notes; the funnel table | `np.array_split(pnl, 5)` sign counting | "Walk-forward" is a five-block sign test on in-sample P&L | **CODE**; `docs/RESEARCH.md:123` already admits it | **P1** |
| 11 | `journal_futures.md:20` "ES 124 statistical + 12 cost …" | 40 of 41 `passed:true` rows have t ∈ [−11.92, −3.44] | "Rejected on cost" is the count of **significant losers** | **LEDGER** | **P1** |
| 12 | `champion.json` "OOS 2020-2026"; `APPROVED_PAPER.md` | `sweep_s38.py:466-470`; S-40; AUD-11 | The OOS half was inside the selection window | **THE REPO'S OWN AUDITS** — the relabel is "owed, not taken" | **P1** |
| 13 | Vault `Backtesting Master Specification.md:31,38` (next-bar-open fills; a holdout is touched once) | `futures_discover.py` (decision-close fills); 189 looks at the S-track OOS | The vault's methodology is not the repository's practice | **VAULT is right on method; CODE is what runs** | P2 |
| 14 | Vault `_Trial Ledger.md` (112 combined trials, "use this for deflation") | Repo ledgers (817 accounted, 0 DSR ever computed) | Two disjoint trial universes, neither deflating the other | **BOTH INCOMPLETE** | P2 |
| 15 | Vault `CLAUDE.md:70-72` / `QuantModel/CLAUDE.md:10` ("the canonical repository") | repo `ARCHITECTURE.md` §1-2 | Three trees each declared canonical | **UNRESOLVED — an owner decision** | **P1** |
| 16 | `live/APPROVED_PAPER.md` (authorises S-12, hash `5246804e…`) | `research/champion.json` (S-18, `a6d6224c…`) | The human approval names a book that no longer trades | **CODE trades S-18** | P2 |
| 17 | `governor.py` docstring "PROBABLY OKAY IS NOT A STATE" | NaN in any `AccountView` field passes every limit | The module's central claim is false for NaN | **CODE** | P2 |
| 18 | `topstep.py:663-671` "the real rule is more generous than the trailing model" | The arithmetic (pinning at $0 is *stricter* while the trailing floor is negative) | The sentence is backwards; the arithmetic is right | **ARITHMETIC** | P4 |
| 19 | `stats.py` `block_bootstrap_t` docstring "One-sided" | `np.abs(centred) >= abs(observed)` | Two-sided (conservative), mislabelled | **CODE** | P3 |
| 20 | `AGENTS.md` "algorithms/intraday/ml/" | the directory does not exist | The operating manual names a phantom scope | **FILESYSTEM** | P3 |

---

## 12. ASSUMPTION REGISTER (Phase 40 / —)

| assumption | where relied on | type | confidence | consequence if wrong | how to verify |
|---|---|---|---|---|---|
| Futures bars are start-stamped; a decision at bar *i*'s close can fill at `c[i]` | funnel P&L | empirical | **HIGH** (verified §4.1) | half-tick optimism per side | tick data; none exists |
| One tick is the ES spread at every minute a hypothesis flips | funnel cost | empirical | MEDIUM — median verified, **p90 is 2 ticks** and 09:30 is the widest minute | costs understated at the entry minute | per-minute spread table from `ES_quotes` |
| MES/MNQ/NQ spreads equal ES's in ticks | funnel cost for the contracts actually intended | **assumed** | **LOW** | micro economics wrong | fetch `BID_ASK` for the three |
| MES round-turn commission is $1.00 | twin, funnel, baseline | **INCORRECT** | — | 18% under-charge on the contract the MLL forces | official 8284213 ($1.22) |
| The Topstep flat rule is "15 min before the calendar close" | `PropFirmProfile`, any future runner | **INCORRECT** | — | auto-liquidation 35 min before the code acts | 8284206 (3:10 PM CT) |
| The XFA can be simulated at Combine size | twin, p_first_payout, E[net] | **assumed, flattering** | LOW | funded-stage economics are fiction | read the ladder off a dashboard |
| The 2012-2026 window is representative | every S-track number | **FALSE by omission** | — | no 2000-02, no 2008-09 | one pre-registered 1999-2011 run |
| The 9-ETF momentum premium is not equity beta | champion promotion | untested | LOW | the "edge" is index exposure | Beta/Alpha vs SPY (LEAN says 0.54 / 0.13) |
| 1.5 bps is the intraday sleeve's slippage | harness, live expectation | **uncalibrated** | LOW | breakeven is 2.6 bps; measured 2.22 ± 0.80 | finish A-5 part 2 |
| The two sleeves never hold the same symbol | both runners | **convention** (a Python list, with an `except: []` fallback) | MEDIUM | one sleeve liquidates the other | make the fallback fatal |
| `intent_id`/journal prevents resends | `IMPLEMENTATION_REPORT` property #5 | **FALSE on the money path** | — | a restart can resend | wire it, then replay a crash |
| Bartlett `L = h−1` corrects overlap | every "HAC-corrected" number | **FALSE** (recovers ⅔) | — | t inflated ×1.22 after correction | the size simulation in §6.3 |
| Resampled intraday paths represent real ones | every Topstep probability | **FALSE** for near-flat templates | — | survival probabilities measured on paths that never happened | object-level resampling |
| `ib.managedAccounts()[0]` is the account orders route to | both runners | **UNKNOWN** | — | orders to an unintended account | set `order.account` explicitly |
| The vault is not a source of evidence | implicit | TRUE today | HIGH | — | it is stated nowhere |

---

## 13. SINGLE POINTS OF FAILURE (Phase 41 / 48)

**What single mistake could cause the largest financial loss?**
**The `Book` object.** It is the sole source for P&L, the daily-loss limit, the Governor's `AccountView` and every in-loop and end-of-day flatten, and it is fed only by `LiveExecutor.settle` — which RISK-02 disconnects from the venue. One wrong list rebinding produces unbounded accumulation with a blind limit and no exit. Second: **FLATTEN trust** (RISK-04) turns the one unrefusable path into an entry path whenever the book is wrong. Third: **strategy code `exec_module`d inside the socket-owning process** — the "model proposes, infrastructure disposes" boundary is a convention for anything the runners load.

**What single mistake could make the entire research program invalid?**
**The absence of an untouched sample.** No holdout has ever been carved, the S-track "OOS" was inside the selection window, and the intraday holdout was spent and re-split. Everything downstream — the champion, the sleeve, the ML gates, the promotion criteria — was chosen on data it had already seen. Adjacent: the **yfinance daily store written adjusted-as-raw** (AUD-17, open) sits under every LEAN number ever promoted; `scripts/intraday_common.py` (67 importers, live constants, mutated at runtime by research scripts) is one bad edit from the 09:25 launch; and **the 2012-01-03 start date across 527 runs** means a program that never looks at 2008 cannot be falsified by 2008.

By category: **DATA** — untracked, unhashed, one regime, adjusted-as-raw equities. **KNOWLEDGE** — an unread vault and a free-text journal that nothing reconciles against the ledger. **AI** — an agent that can promote a strategy into paper execution with no human step. **RESEARCH** — no holdout. **STATISTICS** — multiplicity accounted for 10% of the search. **SOFTWARE** — 50% unreachable code and nine copies of the limits. **RISK** — one limit in one chain, fed by a frozen book. **EXECUTION** — a runner that cannot start. **BROKER** — a `DU` string prefix. **TOPSTEP** — a flat-time model 35 minutes late and a twin that flatters the funded stage six ways. **INFRASTRUCTURE** — six unattended tracks sharing one git index.

---

## 14. TOP 50 FINDINGS, RANKED

Ranked by (1) financial impact, (2) research-invalidating potential, (3) safety, (4) probability, (5) difficulty of detection. Severity: **P0** catastrophic · **P1** major blocker · **P2** important · **P3** improvement · **P4** cosmetic.

| # | ID | SEV | CATEGORY | FILE:LINE | FINDING | CONF |
|---|---|---|---|---|---|---|
| 1 | RISK-02 | **P0** | BUG / EXECUTION | `intraday_trader.py:349,444`; `brokers/ibkr.py:80` | `LiveExecutor.settle` rebinds the aliased adapter order list; every fill after the first settle is invisible → same delta re-sent each bar, book frozen, loss limit and governor blind, EOD flatten empty, position carried overnight | HIGH |
| 2 | RISK-01 | **P0** | BUG / EXECUTION | `intraday_trader.py:891` (bound `:922`) | `live()` reads local `t` before assignment inside the loop → `UnboundLocalError` on the first iteration; the sleeve cannot trade; preflight and tests cannot see it | HIGH |
| 3 | STAT-01 | **P0** | RESEARCH | `research/experiments.jsonl`; 62 writers | Main ledger has no experiment id, family, trial count, threshold or verdict in any of 1,653 rows; multiplicity accounted for ~10% of ~10⁴ statistics | HIGH |
| 4 | ARCH-01 / OBS-03 | **P0** | ARCHITECTURE / AI-SAFETY | `Quant Brain/` (untracked, un-ignored) | Three codebases with three self-declared canonical sources, colliding strategy IDs, a dangling submodule, ~250k parquet files, and a 244-file agent payload whose skills auto-loaded into this session | HIGH |
| 5 | STRAT-01 | **P0** | STRATEGY | `live/intraday_config.json`; `algorithms/intraday/orb/` | The deployed intraday strategy is negative on 2,686 sessions (t −1.24) and its shipped mix was −$697/day; it places real paper orders daily as a "plumbing test" | HIGH |
| 6 | RISK-04 | **P1** | DESIGN / EXECUTION | `core/risk.py:85-89`; `intraday_trader.py:374-378,714-723` | FLATTEN is a caller-supplied label that bypasses every engine and switch with no reduce-only check; a BUY 5,000 labelled FLATTEN passed a halted, breached governor | HIGH |
| 7 | BT-02 / STAT-13 | **P1** | RESEARCH | `core/validation.py`; `research/promotion.py` | Purged walk-forward, `Holdout` and the promotion gate have zero research callers; **no holdout has ever been carved**; the funnel's `Stage.VALIDATION` points at an artefact that does not exist | HIGH |
| 8 | BT-03 / STAT-08 | **P1** | RESEARCH | `sweep_s38.py:466-470`; `champion.json` | The champion's "OOS 2020-2026" was inside the selection window; 189 ledger rows scored it; six promotions in four days on full-sample CAR with no significance test; PSR 33.2% | HIGH |
| 9 | STAT-05 | **P1** | STATISTICS | `registry.py:335`; `search.py:172-190` | The pass rule is two-sided on net P&L: **40 of 41 "PASS" verdicts have t ∈ [−11.92, −3.44]**; the funnel's attrition table is a count of significant losers | HIGH |
| 10 | BT-01 | **P1** | BUG / BACKTEST | `futures_discover.py:104` | Round-turn count never charges the forced flatten and truncates the odd half-turn; 104 of 136 ES rows record `trades=0` and $0 cost for rules that trade one RT/session ($5,379 uncharged per rule) | HIGH |
| 11 | STAT-07 / BT-07 | **P1** | BUG / STATISTICS | `paths.py:59-79` | Monte-Carlo paths rebuilt by dividing by the template's P&L: inverted on sign change (49% of days), unbounded near zero (median worst mark −$51,947 vs −$900; pass rate 0.163→0.253) | HIGH |
| 12 | STAT-06 | **P1** | STATISTICS | `core/stats.py:90-151` | Bartlett HAC with `L = h−1` recovers ⅔ of the long-run variance; measured size 10.6%/12.1%/35.8% at nominal 5%; every "HAC-corrected" number is still ×1.22 too large | HIGH |
| 13 | RISK-05 | **P1** | DESIGN / DOCUMENTATION | `ARCHITECTURE.md`; `IMPLEMENTATION_REPORT.md`; `paper_trade.py:797` | The documented safety pipeline is executed by no runner; the intraday chain holds one limit; the daily chain is empty; no kill switch but MANUAL_HALT is ever tripped | HIGH |
| 14 | STAT-02 | **P1** | REPRODUCIBILITY | `search.py:49-51` | Provenance is `null` on **817 of 817** futures rows and present on 3.6% of equity rows; the promotion gate would refuse every existing row | HIGH |
| 15 | TS-03 | **P1** | TOPSTEP | `propfirm.py:135-138,363-377` | Mandatory flat modelled as 15 min before a 16:00 CT calendar close → **15:45 CT, 35 minutes after Topstep's 3:10 PM CT liquidation** | HIGH |
| 16 | TS-01 | **P1** | TOPSTEP | `propfirm.py:318-347`; `topstep.py:470-474` | Position limits counted in raw contracts per symbol: 30 minis accepted on a 5-mini account; 5 ES + 45 MES accepted; no 10:1 conversion, no account-wide cap | HIGH |
| 17 | AI-01 / RISK-21 | **P1** | AI-SAFETY | `evaluate.py:388-398`; `paper_trade.py:779` | An agent promotion writes `champion.json` and the 15:45 runner trades it the same afternoon; the approval file is existence-only, gitignored, and names a superseded champion | HIGH |
| 18 | RISK-03 | **P1** | BUG / OBSERVABILITY | `conftest.py:137-208`; `test_intraday_gates.py:235` | A unit test writes the real `live/state/governor.json`; the 09:25 gate and the background suite overwrite the live sleeve's published status during a session | HIGH |
| 19 | ARCH-02 | **P1** | ARCHITECTURE | `quant_brain/` (13 modules) | 9,110 of 18,114 lines (50.3%) unreachable from any script, runner or CLI; ~520 tests defend code nothing calls | HIGH |
| 20 | ARCH-03 | **P1** | DESIGN / RISK | `intraday_common.py:69-74` + 8 others | Every binding limit is applied to weights pre-intent, in nine inconsistent copies (0.20/1.6 vs 0.15/1.5 vs 0.15/1.0 vs a dashboard hard-code) | HIGH |
| 21 | TS-04 | **P1** | KNOWLEDGE / TOPSTEP | `docs/topstep/API_UNKNOWNS.md:22-42` | Official: *"Automated trading via the ProjectX API is prohibited in the LFA"* — the repo files this exact question as a blocking unknown and never records the published answer | HIGH |
| 22 | TS-05 | **P1** | RESEARCH / TOPSTEP | `topstep.py:366-374`; `twin.py:276-285` | The XFA is simulated at Combine size (50 micros from $0) against a published day-one 2-lot; no refusal, no reason string | HIGH |
| 23 | BT-04 | **P1** | RESEARCH | `sweep_a4/a14/a15/a17.py` | The intraday "holdout" was spent by A-4 and re-used: 285 ledger rows on it afterwards, then re-split IS 2016-23 / OOS 2024+ | HIGH |
| 24 | STAT-03 | **P1** | DESIGN / STATISTICS | `registry.py:136-139`; `futures_discover.py:166` | A new family name resets the trial count to 1 (bar 1.96); `.v2` already exists with byte-identical t-values | HIGH |
| 25 | STAT-04 | **P1** | BUG / STATISTICS | `registry.py:145-155,283-295` | The fingerprint excludes data, code and cost model, so a corrected re-run is silently dropped and the stale row returned — the reason the family split happened | HIGH |
| 26 | DATA-04 | **P1** | DATA / REPRODUCIBILITY | `research/data_manifest.json`; `.gitignore:30` | 3.5 GB of data is untracked and **content-hashed nowhere**; `reproducible: true` on 0 of 1,653 rows; no result can be tied to the bytes it read | HIGH |
| 27 | RISK-08 | **P1** | SECURITY / DESIGN | `intraday_trader.py:64-70`; `paper_trade.py:179-201` | Strategy modules are `exec_module`d inside the process owning the IB socket; the AST broker-SDK ban covers `quant_brain/` only | HIGH |
| 28 | STAT-10 | **P1** | DESIGN / STATISTICS | `registry.py:317-345` | `verdict()` neither records nor requires a prior `record()`; fifty looks leave the count at zero | HIGH |
| 29 | STRAT-02 | **P1** | RESEARCH | `s1_momo/main.py:78`; ledger | The champion has never been run through 2000-02 or 2008-09 although the store starts 1998 — the two regimes that break momentum + vol-timing | HIGH |
| 30 | DATA-01 | **P1** | DATA | `data/futures/*.parquet` | Continuous series are raw stitches with +50 to +277 point roll jumps and **no roll marker anywhere**; containment today is incidental (per-session features), not designed | HIGH |
| 31 | BT-09 / STRAT-04 | **P1** | RESEARCH | `futures_discover.py:140-147` | "Walk-forward" is `np.array_split(pnl,5)` with ≥3 positive chunk means — a sign test on in-sample P&L, no refit, no purge | HIGH |
| 32 | BT-10 | **P1** | COST / DOCUMENTATION | `s1_momo/main.py:217-279`; `champion.json` | The champion's headline and the promotion comparison basis are the **zero-slippage, zero-financing** column; the honest all-in figure (18.8% vs 24.4%) lives only in prose | HIGH |
| 33 | ARCH-04 | **P1** | BUG / DESIGN | `paper_trade.py:701-710` | Sleeve isolation is a `sys.path` import with `except Exception: _INTRADAY_UNIVERSE = []` — an import failure makes the daily runner sell the intraday sleeve's book | HIGH |
| 34 | ARCH-07 | **P1** | ARCHITECTURE | `scripts/` (118 edges) | The "research archive" is a live dependency graph seven levels deep; `sweep_s19.commission` was wrong until S-44 and fed S-22…S-39 | HIGH |
| 35 | BT-06 | **P2** | BUG / LEAKAGE | `features.py:284-305` | The causality guard perturbs only OHLCV, preserves order under a uniform scale, and is never called by the funnel — 4 of 6 constructed leaks PASS | HIGH |
| 36 | TS-02 | **P2** | TOPSTEP | `topstep.py:470-474` | No permitted-products list: 50 ZN, 50 6E and 50 BTC all admitted | HIGH |
| 37 | TS-06/07/08/09/10 | **P2** | TOPSTEP | `twin.py`, `topstep.py`, `instruments.py` | Funded-stage economics flatter in five independent ways: no $125 minimum ($75 paid), no 3-day restart, balance instead of net-since-payout, one fee per attempt (160 sessions charged $49), MES commission 18% low | HIGH |
| 38 | RISK-06/07 | **P2** | BUG / RISK | `core/governor.py:75-95,167-279` | NaN in any `AccountView` field passes every limit; NaN or negative `Limits` disable or invert one; `max_notional` skips on `None`; `engines`/`limits` are mutable; `reset(by="bot")` accepted | HIGH |
| 39 | REPRO-01 | **P2** | REPRODUCIBILITY | repo root | **No dependency manifest of any kind**, no lockfile, no CI, no coverage tooling; two (three with the vault) interpreters pinned only in prose | HIGH |
| 40 | TEST-01 | **P2** | TESTING | `tests/` | No test drives `live()`; no property tests; no mutation testing; no coverage; 31% of tests exercise unreachable modules; `isolate_live` does not redirect `StateStore` | HIGH |
| 41 | BT-12 / STRAT-08 | **P2** | DATA / RESEARCH | `intraday_common.py:29` | A 16-name universe chosen in 2026 is backtested to 2016 (PLTR listed 2020-09, COIN 2021-04); three strategies rank a 2026 survivor list | HIGH |
| 42 | DATA-02/03 | **P2** | DATA / COST | `instruments.py:83-96`; `execution_sim.py:105` | Commissions hard-coded with no broker statement (micros 18–48% low vs official); the ES **median** spread is charged at the widest minute of the day; MES/NQ/MNQ spreads never measured | HIGH |
| 43 | STAT-17 / BT-19 | **P2** | STATISTICS | `futures_discover.py:131` | The Topstep gate runs 150 bootstrap reps at seed 0 with no CI; SE at the 10% floor is 2.4 pp — a gate that can flip on the seed | HIGH |
| 44 | RISK-12 | **P2** | TOPSTEP / EXECUTION | `core/protection.py:70-143` | `verify` reports PROTECTED for a NaN stop price, an unreachable stop-limit, and a wrong-side stop when `avg_price` is unknown; **no runner places or verifies a stop at all** | HIGH |
| 45 | RISK-15 | **P2** | BUG | `core/locking.py:45-54`; `idempotency.py:105-156` | The stale-lock break is non-exclusive (B acquired at 12.6 s while A held; A then unlinked B's lock); a torn `pending` row lets the same intent be claimed again | HIGH |
| 46 | STAT-20 / BT-13 | **P2** | RESEARCH | `backlog.md:891,2633`; 2 ledger rows | The refuted F-3 claim ("IC +0.01133 at t +2.17") still stands as evidence; `experiments.jsonl` has no retraction mechanism | HIGH |
| 47 | SEC-01 | **P2** | SECURITY / AI-SAFETY | `.gitignore`; `live/APPROVED_PAPER.md` | The sole human authorisation gate is a gitignored file, checked for existence only, whose text authorises a superseded champion; its creation leaves no trace in git | HIGH |
| 48 | TS-12 | **P2** | TOPSTEP COMPLIANCE | `venues/propfirm.py:96-99`; `paths.py:475-495` | Default objective = E[net] with `ruin_penalty=0`, `max_p_ruin=None` and unlimited attempts; the size sweep raises p_pass while p_liquidated stays 100% — the shape of prohibited account stacking | MEDIUM-HIGH |
| 49 | ARCH-14 | **P2** | DESIGN | `s1_momo/signals.py:710-960` | The deployed daily signal reads `S1_ML_MODE` from the environment at import and lazily loads parquet tables into module globals — production behaviour depends on the scheduler's environment | HIGH |
| 50 | STRAT-06 | **P2** | RESEARCH | `late_momo/signal.py`; A-10 | The strongest intraday statistic (t −7.38, all regimes) implies the continuation trade; it was removed rather than inverted and costed — the one unexploited, mechanism-backed lead | MEDIUM |

*Below the cut, still real:* ARCH-05 (core→scripts layer inversion), ARCH-06 (ten ledger schemas), ARCH-08 (research rebinds live constants), ARCH-09..19, STAT-11..28, TS-11..28, RISK-09..26, BT-11..22, OBS-04..10, DATA-05 (early closes pass the ≥200-bar filter as full sessions), STRAT-03/05/07/09/10/11/12.

---

## 15. TOP 20 UNKNOWNS (Phase 51 / 50)

UNKNOWN is a legitimate result. None of these is guessed at anywhere in this report.

1. **The magnitude of the `_rebuild` path artefact on the real ES/NQ series** — per-session P&L is not stored in the ledger, so it cannot be recomputed without re-running the evaluator.
2. **The XFA scaling-plan ladder** — published only as an image; the single datapoint is "a $50K XFA is a 2-lot".
3. **Whether the Combine "best day" is net of commissions** — the XFA formula says net; the Combine formula is silent.
4. **The MLL end-of-day snapshot clock** — Topstep publishes 3:10 PM CT (flat), 4:00 PM CT (day locks for payouts) and 5:00 PM CT (new trading day), and no clock for the MLL snapshot.
5. **Topstep's numeric HFT threshold** — no page states one.
6. **Whether an unattended personal workstation satisfies "personal device"** under the VPS/remote prohibition.
7. **Realised IBKR slippage for the intraday sleeve** — 2.22 bps ± 0.80 on n = 66; breakeven is 2.6.
8. **MES/MNQ/NQ quoted spreads** — never fetched; assumed equal to ES in ticks.
9. **Whether the champion's parameters survive 1999-2011** — never run.
10. **Whether LEAN's in-`on_data` `history()` includes day D's own bar** — the FRAME log was written to answer this; the result was never read.
11. **Whether the F-3 forecast CSV consumed by `ml_scores` was built through D−1** — a same-day join would be a lookahead; default off.
12. **Whether `spa()`'s 8% measured size is Monte-Carlo noise** — needs 2,000+ simulations.
13. **The nested `QuantModel` repository's history and authorship** — the gitdir is missing.
14. **Whether any vault or Catalyst result seeded the repository's 2026-09-08 backlog** — no textual trace either way.
15. **Whether `ib.managedAccounts()[0]` is the account orders route to** — `Order.account` is never set.
16. **Whether the remote `origin/main` is protected against force-push** and whether commits are required to be signed (all 240 are unsigned).
17. **Whether OpenClaw holds cron entries in `openclaw.sqlite`** — not inspected.
18. **The effective number of distinct P&L series per futures family** — 32 distinct gross values for 136 ES cells; the statistical bar should be argued from that, not from 136.
19. **Whether the No-Activation-Fee $50K price is $95 or $85** — two official pages disagree today.
20. **What actually removed uncommitted ledger rows and three untracked scripts from the working tree during this audit**, with HEAD unchanged and no `git log` trace.

---

## 16. TOP 20 KNOWLEDGE RISKS (Phase 51 of brief 2)

| # | CLAIM | SOURCE | WHY DANGEROUS | VERIFY BY | IMPACT |
|---|---|---|---|---|---|
| 1 | "OOS 2020-2026" describes out-of-sample performance | `champion.json`, `APPROVED_PAPER.md` | It is a sub-period of the fit; the repo's own audits say so and the label was never changed | relabel per AUD-11 | the deployed book's headline |
| 2 | "544 hypotheses, 0 survivors → the branch says no" | `journal_futures.md`, `reports/2026-09-13.md` | It is a power result, not a market result (1.3% power at $20/session) | print MDE and power beside every funnel table | could abandon a viable branch |
| 3 | "Topstep $50K profit target is $3,000" carried at SEARCH tier in `BLOCKERS.md` | OWNER-1 | It is now VERIFIED but the blocker still says otherwise; a reader trusts the stale file | sync `BLOCKERS.md` | planning |
| 4 | "The DLL rules are DOC-tier" | `topstep.py:95` citing 8284207 | The cited article is a **404**; the tier claims a provenance that no longer exists | repoint to 10490293 | rulebook trust |
| 5 | "Consistency denominator resolved by the worked example" | `topstep.py:267-281` | Logically impossible from that evidence; two official pages disagree | cite 8284099; record the conflict | pass/fail arithmetic |
| 6 | "Automated trading via the API is an open question" | `API_UNKNOWNS.md` U1 | Officially answered and negative for the LFA; the mission's end-state is unreachable by an automated system | record the rule | strategic |
| 7 | MES round turn is $1.00 | `instruments.py:88` "indicative" | 18% low against the venue actually intended; flips a near-breakeven strategy | official 8284213 | every futures P&L |
| 8 | "HAC-corrected t" | `sweep_audit.md`, `validation.py:13` | Still ×1.22 too large; a marginal survivor is not corrected | the size simulation | every overlapping-label result |
| 9 | "The trial count cannot be understated" | `registry.py` docstring | Family renaming, look-without-record and fingerprint drops all defeat it | the three copy tests | multiplicity |
| 10 | "Walk-forward gate" | funnel, ledger notes | A five-block sign test with no refit | rename or use `purged_walk_forward` | validity |
| 11 | "One live path now runs through the safety layer" | `IMPLEMENTATION_REPORT.md` | That path crashes and cannot book a fill | run `live()` under a fake feed | false safety |
| 12 | "Execution safety 9.0/10" | `qb_scorecard.py` | A self-graded score counting *pieces present*, not *engines called* | count runner-called engines | false confidence |
| 13 | Vault "Strategy Returns Ranking" (S-0012 +3.10%/mo) | `Quant Brain/Backtests/Returns/` | Sits under the same `S-` prefix as the live champion, self-labelled BEST-GUESS / VERY LOW | ID-namespace the vault | future citation error |
| 14 | 4,120 machine-generated claims | `Claims … Batch N.md` | Bulk unreviewed extraction presented in a ledgered folder | sample-audit 20 claims | knowledge poisoning |
| 15 | "The sleeve is a plumbing test" | `live/intraday_config.json` | It places real orders daily on a strategy measured negative on 2,686 sessions | set `equity_frac 0` or a no-order mode | ongoing loss |
| 16 | "1.5 bps slippage" | `intraday_common.py:65` | Measured 2.22 ± 0.80 against a 2.6 breakeven | finish A-5 | the sleeve's sign |
| 17 | "The intraday holdout is a holdout" | A-track docstrings | Spent by A-4, re-used 285 times, then re-split | date-forward freeze | intraday validity |
| 18 | "F-3 IC +0.01133 at t +2.17" | `backlog.md`, 2 ledger rows | Refuted by the repo's own audit; still quotable and indexable | retraction convention for `experiments.jsonl` | ML validity |
| 19 | "A-17 cuts the tail by 11%" | `journal.md` A-17 | 2022 carries it; median year +2.5%; sign test p = 1.000 | year-balanced reporting | risk-overlay decisions |
| 20 | "The vault is the knowledge foundry" | the brief's own architecture | Nothing reads it; it describes a different codebase in a different asset class with zero Topstep content | one line in `ARCHITECTURE.md` stating its status | strategic misdirection |

---

## 17. TOP 20 STRONGEST COMPONENTS (Phase 52)

**PROVEN STRONG** — a defect was measured, then closed by shape, with a test that fails if it reopens:

1. **`RiskDecision.merge` / `RiskChain`** — denial is terminal, order-independent, no engine can re-permit. Verified by construction and by adversarial probe.
2. **`RoutedExecutor.submit`** — never passes a denied, zeroed or unsized MARKET intent to an adapter.
3. **The AST ban on broker SDKs above `brokers/`**, with a self-test proving the ban catches an offender.
4. **`StateScope` / `StateStore` containment** — all four path-traversal attempts refused; scope stamped into every document.
5. **`Ledger.verdict()` takes no trial-count argument**, and a test forbids one from ever being added. This is a genuinely original safeguard.
6. **The retraction mechanism** — a wrong result was withdrawn while its trial stayed in the multiplicity denominator. Exercised on the real look-ahead.
7. **`markets/futures_cme/instruments.py`** — tick value derived, not stored; **14 of 14 P&L cases match hand arithmetic; 0 mismatches**; micro/mini multipliers all correct.
8. **The futures data store** — UTC, tz-aware, start-stamped, correct DST, **0 duplicates, 0 out-of-order bars, 0 bad OHLC** across 1.6 million rows.
9. **LEAN daily fill semantics**, verified in the engine's own source: decide on D's close, fill at D+1's open. No fill lookahead in the champion.
10. **The intraday harness's fill model** — next-bar open, orders carried when a symbol does not print, forced EOD fills counted and optionally fatal.
11. **`tests/test_runner_entrypoints.py`** — subprocess start under the scheduler's exact recipe; closes the class of failure that hid a dead runner for 83 minutes.
12. **The fail-closed preflight**, proven by a real event (2026-09-13 08:49 UTC: refused to trade on a mid-edit `NameError`).
13. **Secrets hygiene** — zero secret-shaped matches in the entire tree *and* the entire history; credential redaction in `__repr__`; a test asserting no credential is in the package source.
14. **`core/multipletest.py`** — Holm, BH, BY, White RC, DSR, PBO all reproduce known answers.
15. **`Rule` / `Confidence` / `UnverifiedRule`** — constructors refuse below-DOC values by default, and `unresolved()` is honest about the gaps it knows.
16. **The critic track** — C-11's block-length attack on the repository's own best result is the single best piece of statistical work in the tree.
17. **The self-audits** — S-33, S-38, S-40 and `sweep_audit.md` measured the repository's own selection premium, OOS-argmax rate and statistical debts, and wrote them down.
18. **The refusal culture** — 10 of 11 items refused on the final day; 432 rows tagged "not promotable"; every ML item refused on its pre-registered clause.
19. **The vault's epistemic framework** — an authority hierarchy, an overfitting contract, and a live contradictions register with `resolution: none — deliberately unresolved`.
20. **`compare_orders.py`** — diffs the LEAN backtest's planned orders against the live runner's on identical inputs, every date. Exactly the right parity test.

**WELL DESIGNED BUT UNPROVEN** (correct in isolation, never exercised where it matters): `purged_walk_forward` / `assert_no_leakage` / `Holdout`; `PromotionGate`; `ExecutionSimulator.execute/fill_price/is_marketable`; the kill-switch vocabulary and `DATA_UNAVAILABLE` semantics; `Reconciler` trip-and-never-reset; `protection.verify`'s side/size logic; `IntentJournal.recover()`; venue capability gating; `Authority.for_live`'s three conditions; `PayoutPolicy` / `compare_policies`.

**PROMISING BUT INCOMPLETE:** the intraday Governor wiring (right seam, one limit, fed by a disconnected book); the funnel's gate order and attrition reporting (needs depth and a real walk-forward); the Topstep twin's Combine model (careful; its funded stage and cost model are not); A-17 as a risk overlay (needs a winning book and a size input); O-6's magnitude signal (real information, no product); `sweep_a14/a15`'s stationary bootstrap and permutation nulls (best practice, applied to a spent holdout on a hindsight universe).

---

## 18. REQUIRED EXPERIMENTS (Phase 54 / 53)

Ordered by capacity to invalidate the whole system.

| # | EXPERIMENT | PURPOSE | DATA | METHOD | PASS | FAIL |
|---|---|---|---|---|---|---|
| E1 | **Drive `live()` under a stubbed `ib_async` for ≥3 loop iterations with a fake feed and fake fills** | Prove the deployed runner can complete a loop, book a fill, and flatten | none | subprocess or in-process with a fake IB; assert `book.pos` reflects fills and no order is re-sent | one order per intended delta; book non-empty; flatten computed from a correct book | any re-send, empty book, or exception |
| E2 | **Re-run the entire futures funnel with the flatten round turn charged** | Determine whether BT-01 changed any verdict, and what the honest cost share is | existing stores | re-run `futures_discover` with a corrected turn count; diff `cost_share` and gate outcomes per row | outcomes unchanged (0 survivors either way) and cost shares restated | a different attrition table — every prior funnel claim must be restated |
| E3 | **Object-level bootstrap for the Topstep twin** | Quantify STAT-07 on real data | `futures_topstep_baseline` session objects | resample `(pnl, path)` pairs jointly; compare `p_liquidated`, `p_pass` against the current `_rebuild` | the two agree within Monte-Carlo error | any material gap ⇒ every published Topstep probability is void |
| E4 | **Power/MDE statement for every funnel family** | Convert "0 survivors" into a falsifiable claim | ledger | compute σ per family, se, MDE at the family bar, power for a $10/$20/$40 per-session edge | published beside the funnel table | — |
| E5 | **A genuine date-forward holdout** | Restore the ability to make an out-of-sample claim | all tracks | `make_holdout` on everything after a frozen date; a one-look ledger; refuse a second look | one look per candidate, recorded | any second look voids the run |
| E6 | **Champion through 1999-2011** | Test the two regimes that break momentum + vol timing | the 1998+ daily store (ETF inception permitting) | one pre-registered LEAN run, 2 bp + financing on | pre-registered thresholds met | the champion's regime robustness is disproven |
| E7 | **Champion at honest costs as the headline** | Remove the zero-cost basis | existing | re-promote on the 2 bp + financing column; make `evaluate.py` refuse a 0 bp comparison | the ranking survives | the promotion was a cost artefact |
| E8 | **Causality guard v2 against the six constructed leaks** | Close BT-06 | synthetic | perturb every numeric column in `requires`, add jitter, tighten tolerance, call it from the funnel | all six CAUGHT | the guard remains blind |
| E9 | **`late_momo direction=+1`, costed, on 2,686 sessions** | Test the one mechanism-backed, strongly-signed unexploited lead | Alpaca store | pre-register clauses first; A-track controls; block bootstrap at block ≥ τ | a positive net result at the corrected bar | the mechanism is priced |
| E10 | **Measure MES/MNQ/NQ spreads** | Replace an assumption with a measurement on the contracts actually intended | IBKR `BID_ASK` | same method as `ES_quotes`; report median, p90 and the 09:30 minute separately | measured tables in the cost model | — |
| E11 | **Full-suite run with `isolate_live` extended to `StateStore`, asserting `live/state` mtimes unchanged** | Close RISK-03 | none | run the suite; compare mtimes | unchanged | tests are polluting live state |
| E12 | **Two-process idempotency and lock stress with an artificially slow holder** | Quantify RISK-15 | scratch | 2 processes, holder paused 15 s | exactly-once holds | the journal is fail-open under load |
| E13 | **Reconciliation drill**: crash the runner mid-session with an open position and a working order, then restart | Prove recovery | paper account, out of hours | scripted kill and restart | positions and orders reconciled before READY | anything adopted silently |
| E14 | **A Topstep practice-account dry run** with `PropFirmRiskEngine` in the chain and a 3:10 PM CT wall-clock flat | Convert every Topstep rule from advisory to enforced, before money | practice account | route every intent through the engine; assert the decision log is non-empty | no rule violation in a full week | any breach ⇒ do not buy a Combine |
| E15 | **Sample-audit 20 vault claims against their cited sources** | Establish whether the 4,120-claim corpus is trustworthy | vault + PDFs | random sample; check each claim against the paper | ≥18 of 20 accurate | the corpus cannot be cited |

---

## 19. REMEDIATION PLAN (Phase 53 / 54)

**No new capability until the phase above it is green.** Nothing in Phase 0–3 adds a feature.

**PHASE 0 — catastrophic safety / correctness (today, before the next 09:25).**
Fix RISK-01 and RISK-02 together (never RISK-01 alone — that is the dangerous order); add E1 as a `runner`-marked test. Set the intraday sleeve to `equity_frac 0` or a no-order plumbing mode until it has a positive pre-registered result (STRAT-01). Make `isolate_live` redirect `StateStore` (RISK-03). Make the daily runner's sleeve-isolation import fatal (ARCH-04).

**PHASE 1 — knowledge and data integrity.** Decide the vault's status in one sentence in `ARCHITECTURE.md` and either move it out of the working tree or gitignore it **and** neutralise its `.claude/` payload (ARCH-01/OBS-01/OBS-02). Content-hash `data/` into the manifests and verify on load (DATA-04). Mark rolls in the futures store (DATA-01). Add a dependency manifest and a lockfile (REPRO-01).

**PHASE 2 — backtest correctness.** Charge the flatten round turn and re-run the funnel (BT-01/E2). Make the costed column the headline and the comparison basis everywhere (BT-10/E7). Record the official Topstep commission table (TS-10). Measure the three missing spreads (E10).

**PHASE 3 — leakage and statistical validity.** Causality guard v2, called by the funnel (BT-06/E8). One-sided pass rule on a declared direction (STAT-05). HAC bandwidth ≈1.5–2h or a block bootstrap as primary (STAT-06). Object-level path resampling (STAT-07/E3). ≥1,000 bootstrap reps with a Wilson interval on any gate (STAT-17).

**PHASE 4 — experiment infrastructure.** One ledger schema with a mandatory family, fingerprint including the dataset, commit and provenance; `record()` refuses `provenance is None`; `verdict()` writes a stub row; family registration with declared parents; a retraction convention for `experiments.jsonl` (STAT-01/02/03/04/10/20, ARCH-06). Carve the date-forward holdout (E5). Publish MDE and power beside every funnel table (E4).

**PHASE 5 — strategy research.** Only now: E6, E9, and a re-examination of the funnel with depth. Re-state the mandate in terms of expected edge per unit cost (STRAT-10).

**PHASE 6 — Topstep model.** Wall-clock 3:10 PM CT flat and 3:08 last entry; micro-equivalent position units with the 10:1 conversion; the permitted-products list; the $125 minimum, net-since-payout and 3-day restart; month-denominated fees with activation and API; a `budget_months` horizon; the XFA ladder read off a dashboard or a refusal (TS-01…TS-11).

**PHASE 7 — practice.** E13, E14. `PropFirmRiskEngine` in a real chain; `protection.verify` with a real fail-safe; the intent journal wired; startup reconciliation through `core/reconcile`.

**PHASE 8 — controlled deployment.** Only after a strategy has survived a genuine holdout at honest costs and a practice account has run a clean week.

---

## 20. SCORECARD (Phase 55)

0–100. These are the auditor's scores, not the repository's self-assessment (`qb_scorecard.py` reports a composite of 7.96/10 by counting *pieces present*; §14 #12 explains why that number is not comparable).

| dimension | score | why |
|---|---|---|
| **Software architecture** | **35** | Correct central ideas (one path to a venue, authority at construction, an AST-enforced adapter boundary) buried under 50.3% unreachable code, nine copies of the limits, 143 `sys.path` mutations, two hidden cycles, a core→scripts inversion and three "current architecture" documents written in 24 hours |
| **Data quality** | **58** | The futures store is genuinely clean (0 duplicates, 0 bad OHLC, correct DST, start-stamped); against that: unhashed and untracked, un-adjusted rolls with no marker, one regime, equities adjusted-as-raw, a hindsight universe |
| **Backtest correctness** | **40** | LEAN fill semantics proven in source and the intraday harness's next-open model are right; the funnel under-charges every hypothesis it judged, never calls its own execution simulator, and fills at the decision bar's close |
| **Leakage protection** | **45** | The one real leak was found, fixed and *retracted correctly* — the best single episode in the repository. The guard that should catch the next one passes 4 of 6 constructed leaks and is not on the research path |
| **Statistical validity** | **30** | A correct, tested multiplicity library with zero callers; HAC under-corrects overlap by ×1.22; a two-sided pass rule that passes significant losers; a Monte Carlo that inverts paths; 150 reps at one seed |
| **Research process** | **22** | ~10⁴ statistics looked at, 817 accounted, 0 provenance on those; no holdout ever carved; the OOS window was inside the selection set; promotion is a full-sample CAR contest. Rescued from single digits by an exceptional written record and a real refusal culture |
| **Strategy quality** | **12** | Zero validated strategies. One deployed strategy rejected by its own research; a champion that is mostly beta with PSR 33%; 544 futures hypotheses with 0 survivors at 1.3% power |
| **Robustness** | **25** | Parameter shelves are checked and the critic attacks block lengths; no strategy has been tested across regimes, on other instruments, at honest costs, or with delayed fills |
| **ML** | **35** | Methodologically sound where it matters (causal features, pipelines fit on train, early stop on a later year, scrambled controls) and honest about the answer: nothing beats the free baseline |
| **Risk engine** | **28** | The chain's shape is correct and provable; exactly one limit is in it, fed by a book the same day's refactor disconnected; every other control is advisory; NaN passes everything |
| **Execution engine** | **22** | Two P0s in the deployed runner; FLATTEN is an unverified label; no stop is ever placed; no journal; recovery gives up silently on disconnect |
| **Topstep model** | **48** | The Combine boundary logic is right and simulation-verified; the flat time is 35 minutes wrong; the funded stage flatters in six independent ways; position units are wrong |
| **Topstep compliance** | **55** | Nothing can reach a Topstep account, the rulebook carries provenance tiers and refuses below-DOC values, and no strategy depends on gaming the evaluation. Offset by an unrecorded LFA API prohibition and an objective that can reward stacking |
| **Security** | **88** | Zero secret-shaped matches in the tree *and* the history; correct gitignore; redaction in `__repr__`; a test guarding the package source. Deductions for a gitignored sole authorisation gate, a paper account id in tracked files, and a foreign hook payload inside the working tree |
| **Reproducibility** | **15** | No dependency manifest, no lockfile, no CI, no dataset hash, `reproducible: true` on 0 of 1,653 rows, provenance on 0 of 817 futures rows. Another machine cannot reproduce anything |
| **Knowledge base** | **30** | Real intellectual quality (contradiction records, an authority hierarchy, correct formula notes) in a vault that is frozen, 53% unsourced, about a different asset class, and read by nothing |
| **Obsidian provenance** | **25** | Excellent structure applied to under half the corpus; 4,120 machine-generated claims; no review or expiry mechanism |
| **AI-safety boundaries** | **30** | The gate, the authority ladder and the `DU` check are real and have caught real failures; but an agent can alter limits, edit rule values together with their pinning tests, and promote a strategy into paper execution with no human step |
| | | |
| **COMPOSITE** | **~34 / 100** | A serious, unusually self-aware engineering effort whose foundations (levels 1–5) are not yet trustworthy and whose two live paths are unsafe today |

---

## 21. READINESS MATRIX (Phase 56)

| | verdict | what blocks it |
|---|---|---|
| **RESEARCH READY** | **NO** | No experiment identity, family or trial count on 1,653 of 2,470 rows; provenance on 0 of 817 futures rows; no dataset hash; `verdict()` can be called without recording; family renaming resets the bar |
| **BACKTEST READY** | **NO** | The funnel under-charges every hypothesis it judged (BT-01) and never calls its own execution simulator; the champion's headline is a zero-cost column; the causality guard is porous and unwired |
| **OOS READY** | **NO** | No holdout has ever been carved; the S-track "OOS" was inside the selection window and was scored 189 times; the intraday holdout was spent and re-split |
| **ROBUSTNESS READY** | **NO** | One regime (1.25 years, 4 contracts) for futures; no pre-2012 run for the champion; Monte-Carlo paths are reconstructed by division; 150 reps at one seed |
| **PAPER READY** | **NO** | RISK-01 (the runner cannot start) and RISK-02 (fills invisible, unbounded re-sends, blind loss limit, no EOD flatten); the deployed strategy is negative on 2,686 sessions; the daily runner's chain is empty; a unit test writes the live state file |
| **TOPSTEP PRACTICE READY** | **NO** | No prop-firm engine is in any chain; the flat rule is 35 minutes late; position limits are counted in the wrong units; no permitted-products list; no stop is placed or verified anywhere |
| **TOPSTEP COMBINE DEPLOYMENT READY** | **NO** | All of the above, plus: no candidate strategy exists (0 survivors at 1.3% power), the pass-probability tool cannot yet produce an honest positive, and the funded-stage model flatters in six ways |
| **LIVE BROKER READY** | **NO** | Everything above, plus an authority ladder that blocks configuration accidents rather than code, and a `DU` string prefix as the only account gate |

---

## 22. FINAL RED TEAM (Phase 48 / 57)

*Answering as an adversary trying to prove this project has no real edge.*

**1. How could the backtest be lying?** It is, in three measurable ways: the futures funnel omits one round turn per session for every hypothesis (and *all* cost for the 104 constant-position rules); the champion's headline charges zero slippage and zero financing; the intraday harness charges 1.5 bps against a measured 2.22 with a 2.6 breakeven. Nothing needs to be malicious — every one is a default that flatters.

**2. How could the data be lying?** The equity daily store is written adjusted-as-raw (AUD-17, open) under every LEAN number ever promoted; the intraday universe was picked in 2026 and run back to 2016; the futures store is one regime deep with un-marked rolls. The futures store itself is clean — that is the exception, not the rule.

**3. How could the knowledge base be misleading?** By being a different project's. It contains zero Topstep content, is frozen at 2026-08-26, is 53% unsourced, carries 4,120 machine-generated claims, and uses an `S-00xx` ID space that collides with the live champion's `S-xx`. Its greatest danger is that its *methodology* is better than the code's, so a reader who trusts it will believe the repository follows rules it does not.

**4. How could AI create confirmation bias?** It already has: `AGENTS.md` instructs "a promising variation of the champion"; the loop's memory is "the last 20 lines" of a 1,653-row ledger; the interpret-and-choose-next step is an LLM; and the free-text journals are reconciled against no ledger row. Against that, this project's LLM has refused far more than it promoted — the bias is structural, not behavioural.

**5. How could multiple testing manufacture a winner?** ~10⁴ statistics looked at, 817 accounted. E[max |t|] over 5,000 nulls is ≈3.9. The champion is the CAR-argmax of ~46 structural items × ~20 cells × 3 windows; the crisis switch is OOS rank 1 of 36 and IS rank 24 of 36. A "winner" has already been manufactured twice and caught twice by the repo's own critic — which is the only reason this answer is not worse.

**6. How could execution invalidate the backtest?** The deployed runner cannot complete a loop iteration; if it could, it would re-send the full delta every bar with a frozen book. The daily runner trades one session later than the backtest (~1.9 CAR). No stop is placed anywhere. FLATTEN is an unverified label. The realised-vs-modelled slippage gap alone exceeds the sleeve's expectancy.

**7. How could risk fail?** One limit in one chain, reading a book the executor disconnected; every other limit, every kill switch, the bracket verifier, the reconciler and the journal have no caller; NaN passes every check; `engines.clear()` disarms the chain; a mislabelled FLATTEN bypasses everything. The daily runner has no risk engine at all.

**8. How could Topstep behave differently from the simulator?** It would liquidate at 3:10 PM CT while the model waits until 15:45 CT; it would reject a 30-mini order the engine approved; it would refuse a $75 payout the twin recorded; it would charge $1.22 per MES round turn, a rebill every 30 days, $149 to activate an XFA and $29/month for the API; and it would cap a fresh XFA at a 2-lot the twin runs at 50 micros.

**9. How could the research process contaminate OOS?** It already has, by the repository's own audits: 189 looks at the S-track "OOS", 285 rows on the spent intraday holdout, an OOS argmax on 3 of 6 axes, and columns chosen after reading the test window. `Holdout` exists, is correct, and has never been instantiated.

**10. How could the system appear sophisticated while being fundamentally wrong?** Exactly as it does: 18,114 lines of core with half unreachable, 1,895 green tests of which a third exercise code nothing calls, a 3,919-line rulebook for a firm with no account, a 20-capability venue protocol with one adapter that cannot send, eight position sizers with none wired, seven multiplicity corrections with no caller, and a self-generated scorecard of 7.96/10 — over two live paths that carry one limit between them and a runner that raises `UnboundLocalError` on its first loop.

---

## 23. FINAL STRATEGIC ASSESSMENT (Phase 58)

1. **Is this a trustworthy quantitative research platform today?** **No.** It cannot reproduce a result, cannot count its own trials outside one branch, and has never held data back.
2. **Is it capable of discovering a genuinely robust futures strategy?** **Not yet** — not at 1.3% power on 395 sessions of one regime, with a cost model that omits the flatten. The *machinery* is capable; the sample and the cost model are not.
3. **Is it capable of proving a strategy has an edge?** **No.** Proof requires an untouched sample, and none exists.
4. **Is it capable of estimating a legitimate Topstep pass probability?** **Partly.** It can produce an honest *negative* — and it did. It cannot yet produce an honest *positive*: eight biases point one way and the path resampler is defective.
5. **Is it safe for Topstep practice?** **No.** No prop-firm engine is in a chain, the flat rule is 35 minutes late, and no stop is ever placed or verified.
6. **Is it safe for a real Combine?** **No**, by a wide margin, and the repository's own posture agrees — the ProjectX live path raises `NotPermitted` by design.
7. **Largest research-validity problem:** no holdout has ever been carved, and the window called out-of-sample was inside the selection set.
8. **Largest software problem:** the deployed runner's two P0s — it cannot start, and if it could, it could not see its own fills.
9. **Largest knowledge-base problem:** the foundry is a different project's, connected to nothing, containing zero Topstep knowledge, while shipping executable agent configuration into the trading repo's working tree.
10. **Largest Topstep problem:** the funded stage is modelled in six flattering ways and the mandatory-flat time is wrong by 35 minutes — the twin would tell you that you passed while Topstep liquidated you.
11. **Largest statistical problem:** the multiplicity machinery covers ~10% of the search, and the ×1.22 HAC under-correction means even the "corrected" numbers are not corrected.
12. **What should be built next?** Nothing new. Fix the two P0s together, stop trading a strategy your own research rejected, carve a date-forward holdout, and charge the flatten round turn. Four items; none of them is a feature.

---

## 24. THE THREE ANSWERS (Phase 58 / 59)

> ### What is the single biggest thing this project is doing wrong?
>
> **It is generating conclusions faster than it can validate them, and then building on the conclusions.**
>
> Concretely: 240 commits in six days, ~10⁴ statistics looked at, 817 accounted, **zero** ever held back for a genuine out-of-sample test — while a strategy the project's own research measured at −$310/day trades a paper account daily, an execution-safety layer for a prop firm with no account was written in a single day on top of data one regime deep, and the runner that layer was attached to cannot complete one loop iteration. Every individual decision was defensible in the hour it was made. The compound is a system that knows a great deal about itself and can prove almost none of it.

> ### What is the single biggest thing it gets right?
>
> **It tells the truth about its own results, in writing, including when the truth is that the work was wrong.**
>
> The look-ahead that produced the only funnel survivor was found, fixed, and the survivor **retracted while keeping its trial in the multiplicity denominator** — a discipline most professional research groups do not maintain. `journal.md:6169` reads *"The deployed sleeve loses money on the sessions it was not tuned on."* S-33 measured its own selection premium and found it nil. S-40 recorded that its shipped cell was the OOS argmax and the IS 24th of 36. F-23 concluded the ML track's own gate had never resolved anything. The critic track attacks the repository's best result on purpose. **That habit is the rarest and most valuable asset here, and it is the reason this audit could be written at all** — most of the damning evidence in this report came from the project's own journals. Foundations can be rebuilt; that habit cannot be installed later.

> ### What is the single highest-value next action?
>
> **Fix RISK-01 and RISK-02 in the same change, before Monday's 09:25 launch — and set the intraday sleeve to place no orders until it has a positive pre-registered result.**
>
> Not because it is the most intellectually interesting item, but because it is the only one on this list that can lose money this week, and because the order matters: **fixing the crash alone un-masks the fill-blindness**, turning a runner that safely does nothing into one that re-sends its full position every minute with a blind loss limit and no end-of-day exit.
>
> Then, in order: carve a date-forward holdout and stop scoring the old ones (E5); charge the flatten round turn and re-run the funnel (E2); decide in one sentence what `Quant Brain/` is and move it out of the working tree.

---

*Prepared read-only at HEAD `6c8f919`. No repository file other than this one was created, modified or deleted; nothing was committed; no credential was opened; no venue was contacted; live trading was not enabled. Where a fact could not be established it is marked **UNKNOWN — REQUIRES VERIFICATION** and is listed in §15.*
