# Architecture audit

Phase 0 of the master directive. Written from a full read of the tree on 2026-09-13, not from
filenames. Every claim below names the file that supports it.

---

## Current architecture

```
quant_brain/
  core/           market-agnostic: instruments, calendar, execution, risk, mode, state,
                  provenance, stats, validation, multipletest, labels, dataquality,
                  resources, scheduler, knowledge
  markets/
    equity_us/    NYSE calendar (hand-typed 2016-2027)
    futures_cme/  instruments, topstep rulebook, propfirm engine, twin, paths (MC/stress),
                  execution_sim, features, dataquality, profiles
    lean_calendar CME sessions from LEAN's own market-hours database
  research/       registry (ledger), search (funnel), promotion (gate), robustness
  brokers/        ibkr, projectx   - the ONLY modules allowed to import a broker SDK
scripts/          ~90 files: two live runners, ~60 research sweeps, data fetchers, the gate,
                  the scorecard, launch/watchdog
tests/            1,550 tests across 54 files
research/         journals per track, experiments.jsonl (1,258 rows), experiments_futures.jsonl
docs/topstep/     rulebook (82 rules), API reference (21 ops), unknowns, versioning
```

Two interpreters by constraint: Python 3.11 hosts LEAN (pandas 2.2.3, no pyarrow); 3.14
runs the harness and both live tasks (pandas 3.0.5). `provenance.env_key` discriminates them
and the promotion gate refuses to compare across them.

Six agent tracks (iterate/ml/daily/options/critic/eng) edit one working tree concurrently
under OpenClaw. This is the single most consequential operational fact about the repository
and it shapes several decisions below.

---

## Strengths that must not be destroyed

| strength | where | why it matters |
|---|---|---|
| **The trial count is read from disk, not passed in** | `research/registry.py` `Ledger.verdict()` has no `n_trials` argument | Every multiplicity correction in the literature takes N as an input supplied by the person who wants significance. Here it cannot be understated. |
| **One path to a venue, through the risk chain, checked at construction** | `core/execution.py` `RoutedExecutor`, `core/mode.py` `Authority` | A process that could not legitimately trade cannot assemble the object that would. |
| **No broker SDK above `brokers/`** | `tests/test_qb_adapter.py` walks the AST of every other module | "Venue-swappable" is checkable, not claimed. |
| **Rules carry provenance and a confidence tier** | `markets/futures_cme/topstep.py` `Rule(value, quote, source, confidence, retrieved)` | Constructors refuse anything below DOC by default. Unverified numbers cannot silently become pass probabilities. |
| **Causality verified empirically, swept not sampled** | `markets/futures_cme/features.py` `assert_causal` | A single-probe version shipped a lookahead that produced the only funnel survivor ever. |
| **The funnel's gate order** | `research/search.py` — statistics first | Running statistics last means survivors were pre-selected by filters the correction cannot see. |
| **Refusal over estimation** | `execution_sim` refuses passive fills; `twin` refuses sessions without an intraday path; `dataquality` names an assumed spread as assumed | Every one of these is a place a plausible number would have been wrong. |
| **The HAC / horizon machinery** | `core/stats.py` | Correct, tested, and the reason F-3's t fell from 2.41 to 0.79. |
| **The gate and the scorecard** | `scripts/qb_check.py`, `scripts/qb_scorecard.py` | The scorecard measures the tree; three of its dimensions were found hard-capped today and fixed to measure. |

---

## Weaknesses

### In the execution layer (the directive's centre of gravity)

1. **No reason-code taxonomy.** `RiskDecision.binding` carries free-text rule names. A caller cannot
   switch on `RISK_DAILY_LOSS` versus `DATA_STALE` because neither exists as a code.
2. **No kill-switch family.** The chain evaluates limits on an intent; nothing trips on stale data,
   a dead connection, an unreconciled position, or an unverified bracket, and nothing stays
   tripped until a person resets it.
3. **No order lifecycle state machine.** `Ack` says accepted or not. There is no SUBMITTED →
   ACKNOWLEDGED → PARTIALLY_FILLED → FILLED → PROTECTED progression, so "is this position
   protected" has no answer.
4. **No bracket verification.** `POSITION OPEN + STOP UNKNOWN` is not a state the system can be in,
   which means it cannot be detected either.
5. **No idempotency.** An intent has no deterministic identity; a process restart or an API timeout
   can resubmit. This is the failure that costs the most money per occurrence.
6. **Reconciliation is a refusal, not an engine.** `projectx.reconcile()` correctly refuses to
   return an empty position set, but there is no generic compare-and-halt over positions, orders,
   fills and equity.
7. **No venue capability declaration.** An adapter either implements a method or raises
   `NotPermitted`; nothing declares up front what a venue supports, so `best_fit` and
   "never silently emulate" are not expressible.

### In research

8. **59 sweep scripts, zero import `core.stats`.** Measured and audited (`research/sweep_audit.md`):
   the realized exposure is one script (F-3); most t's are one-per-session where overlap does not
   apply. Retrofitting is other tracks' work. New research goes through the ledger.
9. **No general trade analytics.** MAE/MFE, expectancy, profit factor exist ad hoc inside
   individual sweeps, not as a shared module with UNAVAILABLE semantics.
10. **No position sizing beyond the twin's `risk_budget`.** No Kelly, no vol-targeting, no
    portfolio aggregation.
11. **History depth.** 395 sessions on the deepest futures series against ~2,000 measured as
    necessary. Four contracts over one 1.25-year window is one regime, not four samples.

### Operational

12. **Shared-tree commit races.** Six tracks commit continuously; `index.lock` is held most of the
    time; staged files leak across commits in both directions. Documented in
    `research/journal_futures.md` and by two other tracks. Mitigation: `git commit --only` plus
    lock polling. Root fix would be per-track worktrees, which is out of scope here.
13. **A third ledger writer without provenance** (`options/odte_o7_volstate`) dropped Research
    reproducibility from 8 to 6; the scorecard now names the writer.

---

## Duplication and competing abstractions

- `markets/futures_cme/propfirm.py` (generic `PropFirmProfile`) and `topstep.py` (Topstep rules
  producing a `PropFirmProfile`) are **layered, not duplicated** — the second configures the first.
  Keep both.
- `core/execution.py` has `ExecutionAdapter`; a `Venue` protocol with capabilities is being added
  in `venues/`. The two must compose: a Venue **wraps** an adapter and declares what it supports.
  It must not be a second adapter interface.
- `core/dataquality.py` (generic bars) and `markets/futures_cme/dataquality.py` (roll/stitch
  hazards) are complementary and both run on the futures store. Keep both.
- `scripts/futures_data.py` and `scripts/futures_fetch_multi.py` both fetch futures; the second
  is the multi-contract successor and validates before writing. The first has a latent `sys.path`
  bug (documented by the agent that wrote the second). **Candidate for retirement**, not now.
- Two live runners (`intraday_trader.py`, `paper_trade.py`) share the routed path but keep their
  own RTH refusal and approval-file checks. Deliberate; see `EXECUTION.md`.

## Dead code

- `markets/futures_cme/profiles.py` — archetype profiles that predate `topstep.py`. Referenced by
  tests only. Low value; harmless; leave.
- `core/knowledge.py` — TF-IDF index over journals; used by `already_tried()` and reads only
  `experiments.jsonl`, so the 817 futures-ledger rows are invisible to it. Functional but
  partially blind. Fix is a one-line path addition; noted, not done here.

## Fragile interfaces

- `Experiment.stage` is unguarded while `Candidate.stage` is protected by `ALLOWED`. Same name,
  same type, different guarantees. A refactor hazard.
- `Holdout.spend` records `forced` as "this look followed others", not "the caller passed
  force=True".
- `IBKRAdapter.working()` keyed off `contract.symbol` until today; option legs collapsed into one
  bucket. Fixed; the class of bug (venue object introspection instead of caller's key) is worth
  watching for elsewhere.

## Missing tests

- The two live runners' end-to-end order path is tested through `test_intraday_p0.py` (29) and
  `test_paper_sizing.py`; there is no test that a `RoutedExecutor` refusal actually stops the
  runner from calling `placeOrder` — it is guaranteed by construction but not exercised.
- No failure-injection suite for the execution layer (network drop, token expiry, duplicate fill,
  corrupted state). These arrive with Phases 6–10 below.

## Dangerous assumptions

- **That an ES quote spread generalises.** Measured 1.00 tick in RTH for six quarters on ES only.
  MES/NQ/MNQ quotes were not fetched (MES refused on one crossed bar; NQ/MNQ stopped for time).
- **That 326 sessions can resolve anything.** They cannot, and the funnel says so with 0
  survivors; the danger is a future reader believing a survivor.
- **That the Topstep rules are stable.** They are versioned (`docs/topstep/VERSIONING.md`) but the
  code carries one version. A second version has never been exercised.

---

## Target architecture

```
DATA -> DATA VALIDATION -> FEATURES -> RESEARCH -> STRATEGY -> SIGNAL
  -> SIZING -> RISK GOVERNOR (reason codes, kill switches)
  -> VENUE COMPLIANCE (capabilities + rules)
  -> EXECUTION INTENT (deterministic id, journaled)
  -> EXECUTION ENGINE (lifecycle state machine, bracket verification)
  -> VENUE ADAPTER -> BROKER / PROP FIRM
  -> EVENTS -> RECONCILIATION (compare-and-halt) -> STATE STORE -> OBSERVABILITY
```

Of this, the following existed before today: DATA VALIDATION, FEATURES, RESEARCH, the intent
type, the risk chain, the authority ladder, and the adapters. Today adds: the governor with
reason codes and kill switches, the lifecycle state machine, bracket verification, idempotency,
venue capabilities, sizing, portfolio aggregation, and trade analytics.

## Migration plan

Additive only. Nothing existing is rewritten; new modules compose with existing types:

| new | composes with | how |
|---|---|---|
| `core/governor.py` | `core/risk.py` | `Governor` IS a `RiskEngine`; reason codes become `RiskDecision.binding` entries |
| `core/lifecycle.py` | `core/execution.py` | state machines over `OrderIntent`/`Ack`; no change to either |
| `core/protection.py` | `core/execution.py` `Position` | verifies against working orders; emits a kill-switch trip |
| `core/idempotency.py` | `RoutedExecutor` | optional journal; a duplicate intent id is refused before the chain |
| `venues/` | `brokers/*` | a `Venue` wraps an adapter and declares capabilities |
| `core/sizing.py`, `core/portfolio.py` | `twin.risk_budget`, `InstrumentSpec` | min'd against every limit above; whole contracts |
| `research/analytics.py` | `robustness.MetricDoc` | same arithmetic/judgement pattern |

## Files that should be modified

- `core/execution.py` — accept an optional idempotency journal (small, additive)
- `__main__.py` — `readiness` and `risk status` commands
- `ARCHITECTURE.md` — the new layers

## Files that should be created

Listed in the migration table, plus `docs/IMPLEMENTATION_REPORT.md`, `.env.example`, and the
Phase 49 documents.

## Files that should NOT be rewritten

- `core/risk.py`, `core/execution.py`'s existing types, `research/registry.py`,
  `markets/futures_cme/topstep.py`, `twin.py`, `features.py` — each carries tests written to
  defend a specific property, and each property was earned by a specific failure.
- The two live runners beyond the additive changes already made.
- Any `scripts/sweep_*.py` — other tracks' work.

---

## What this audit does not claim

It does not claim any strategy has an edge (544 hypotheses, 0 survivors, one retracted). It does
not claim the execution layer is live-capable (the ProjectX adapter's live path is unimplemented
by design). It does not claim the Topstep rulebook is complete (the scaling ladder is
owner-tier). It claims the research engine is validated, and nothing more.
