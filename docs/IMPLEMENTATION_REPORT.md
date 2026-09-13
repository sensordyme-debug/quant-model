# Implementation report

The master directive's closing deliverable. Written 2026-09-13 against `f7afd6d`, gate and scorecard re-measured at `0285d12`. Every number
below was measured on this machine; every claim names the file or test that carries it.

## Validation status

| tier | status | evidence |
|---|---|---|
| ENGINE VALIDATED | **yes** | 1,895 tests collected across 65 files; gate `ruff` core+tests, `pyright`, `pytest` green at `7331797` and re-run at `f7afd6d` (see "Gate") |
| STRATEGY VALIDATED | **no** | 544 hypotheses across ES/MES/NQ/MNQ, **0 survivors**, one survivor retracted after a lookahead was found (`research/journal_futures.md`, `research/experiments_futures.jsonl`: every row REJECTED) |
| LIVE EXECUTION VALIDATED | **no** | the ProjectX live path raises `NotPermitted` by design; no order has been sent to any prop firm; the IBKR paper sleeve has traded, which is PAPER, not live |
| PROFITABILITY DEMONSTRATED | **no** | nothing to demonstrate it with; see the row above it |

Nothing in this report moves any tier. That is the correct outcome for a research platform
whose funnel keeps saying "no edge found".

## What landed today

Six commits, each a unit, each committed with `--only` and its own paths:

| commit | unit | new tests |
|---|---|---|
| `ec12d30` | `quant_brain/venues/` - capability declarations with evidence; prop-firm framework; ProjectX declares AUTH only | 69 |
| `be75937` | `core/sizing.py`, `core/portfolio.py` - eight sizers behind one `@final size()`; portfolio exposure and correlated risk | 91 |
| `7331797` | `core/governor.py`, `lifecycle.py`, `protection.py`, `reconcile.py`, `idempotency.py`, `locking.py`; `OrderIntent.intent_id`; `RoutedExecutor(journal=)`; four CLI commands; `docs/ARCHITECTURE_AUDIT.md` | 204 |
| `017c2cc` | `research/analytics.py` - trade analytics with UNAVAILABLE semantics | 36 |
| `5a3891f` | `docs/{RESEARCH,BACKTESTING,VALIDATION,RISK,PROP_FIRM,DEVELOPMENT,OPERATIONS}.md`, `.env.example` | - |
| `f7afd6d` | `scripts/intraday_trader.py` - the governor armed in the live paper runner; in-loop close-outs made FLATTEN intents | 8 |

Baseline at the start of the directive (`2a7367f`): 1,550 tests in 54 files. Now: 1,895 in 65.

Four of the six units were built by parallel agents from written specifications and were
verified independently before commit (each agent's own `pytest`/`ruff`/`pyright`, then the
whole-repository gate). The audit, the execution-safety core, the CLI, the runner wiring and
the reviews of the agents' work were done directly.

## The architecture now

```
DATA -> DATA VALIDATION -> FEATURES -> RESEARCH (ledger, funnel, multiplicity) -> SIGNAL
  -> sizing.Sizer.size()             whole units; min'd against strategy / governor / venue / prop-firm
  -> idempotency.intent_id()         deterministic identity from what the strategy knew
  -> RoutedExecutor.submit()
       journal.claim()               duplicate or unlabelled intent -> refused before the chain
       Governor                      kill switches first, then limits; a Reason code on every refusal
       venue adapter                 the only call that reaches a venue
       journal.advance()             SUBMITTED -> ACKED | FAILED; a crash leaves SUBMITTED
  -> lifecycle.OrderMachine          ... FILLED -> PROTECTED | UNPROTECTED
  -> protection.verify()             against the venue's working orders, not our outbox
  -> reconcile.Reconciler.run()      local vs broker; any difference trips POSITION_UNRECONCILED
  -> StateStore (scoped)             governor.json published for `risk status`
```

`ARCHITECTURE.md` §4a-ii carries the same diagram with the five properties and the tests that
defend each. `docs/ARCHITECTURE_AUDIT.md` is the Phase 0 audit this was built against; of its
seven execution-layer weaknesses, six are closed (1-5 and 7) and one is partly closed (6,
reconciliation: the engine exists; no runner calls it yet).

## Safety properties, and the test that would fail if each were lost

| property | test |
|---|---|
| A refusal carries a machine-readable code | `test_qb_governor::test_denial_binding_is_a_reason_code_not_free_text` |
| A configured limit with an unknown input denies, never skips | `test_qb_governor::test_configured_limit_with_unknown_input_denies_with_data_unavailable` |
| A tripped kill switch stays tripped; only a named person resets it | `test_qb_governor::test_switch_reset_requires_a_named_person` |
| FLATTEN passes every tripped switch and every breached limit | `test_qb_governor::test_governor_in_routed_executor_flatten_survives_every_trip` |
| AUTHENTICATED is not READY; READY needs all thirteen preconditions | `test_qb_lifecycle::test_authenticated_cannot_jump_to_ready`, `::test_ready_requires_a_complete_readiness_and_names_what_is_missing` |
| A submitted-but-unacknowledged stop is not protection | `test_qb_protection::test_a_stop_the_process_sent_but_the_venue_has_not_acked_is_pending_not_protected` |
| A stop on the wrong side, wrong symbol or short size is not protection | `test_qb_protection::test_stop_on_the_wrong_side_of_entry_does_not_count`, `::test_undersized_stop_is_unprotected_for_the_uncovered_part` |
| A reconciliation failure trips a switch; a later clean pass does not reset it | `test_qb_reconcile::test_failure_trips_position_unreconciled_and_a_pass_does_not_reset_it` |
| Stale snapshots refuse to compare | `test_qb_reconcile::test_stale_snapshot_fails_before_any_comparison_is_made` |
| The same decision cannot be sent twice, including after a restart | `test_qb_idempotency::test_replay_after_restart_is_refused_by_a_fresh_executor` |
| A crash between send and ack leaves the intent SUBMITTED, and the replay is refused | `test_qb_idempotency::test_adapter_exception_leaves_intent_submitted_for_recovery` |
| Eight concurrent claims of one id admit exactly one | `test_qb_idempotency::test_concurrent_claims_of_one_id_admit_exactly_one` |
| An executor with a journal refuses an unlabelled intent | `test_qb_idempotency::test_executor_with_journal_refuses_an_intent_without_id` |
| A venue declaring nothing refuses all 20 capabilities by name | `test_qb_venues` (table walk) |
| A dry-run submit is not ORDER_SUBMIT | `test_qb_venues::test_projectx_dry_run_submit_is_not_order_submission` |
| Every sizer is clamped by every ceiling; whole units only | `test_qb_sizing` (parametrised over the sizer family) |
| Kelly refuses noise | `test_qb_sizing` (40 fixed zero-edge seeds, all refused) |
| A live-path close-out is a FLATTEN intent | `test_intraday_governor::test_loss_limit_close_out_reaches_the_executor_as_a_flatten` |
| No broker SDK is importable above `brokers/` | `test_qb_adapter` (AST walk, pre-existing) |
| Live authority needs three independent conditions | `test_qb_mode` (pre-existing) |

## Defects found and fixed while building

1. **In-loop close-outs were MARKET intents.** `Trader.step` called `self.ex.submit(orders, t)`
   without `flatten=`. Every loss-limit, HALT and 15:38 close-out in the deployed intraday
   runner went out as a MARKET intent, which a risk engine may refuse. It was harmless only
   because the chain was empty - which `docs/RISK.md` had just found. Fixed in `f7afd6d`
   before attaching anything to the chain.
2. **Torn-row hazard in both append-only journals.** `registry._append` (the research ledger)
   appended without checking that the previous byte was a newline; a row torn by a crash
   would swallow the next one. In the ledger that is a lost trial; in the new intent journal
   it would be a duplicate order. Measured by writing a torn row and appending after it, then
   fixed in both (`7331797`).
3. **A first test was refused by the authority ladder.** A `RoutedExecutor` built with a
   RESEARCH authority against the simulated adapter raised `NotPermitted` at construction.
   The ladder working; the test was wrong. Noted because it is the property doing its job.

## The one live-path change, stated plainly

`f7afd6d` changes what the 09:25 intraday paper runner does:

- It arms a `Governor` with the sleeve's existing 2.5% daily-loss limit and attaches it to the
  executor's chain. The same limit, enforced a second time at the layer no code path can skip.
- A held symbol with **no price ever seen** now makes the governor refuse NEW entries for that
  bar with `DATA_UNAVAILABLE`. Before, entries went through on a partial P&L. The AUD-05 case
  (a dropped bar after a price) is unchanged - it marks at the last level. Flatten is
  unaffected; the session is not ended.
- On persisting paper runs it publishes `live/state/governor.json` each bar.

`scripts/paper_trade.py` is **not** wired; its chain is still empty.

## What is not done

- **No runner calls `reconcile`, `protection.verify` or the `OrderMachine`.** They are
  engines with tests and no caller. The venue layer's `Reconciliation` is a thin position diff
  that could feed `reconcile.Snapshot`; that wiring is a reviewed diff per venue.
- **No intent journal is attached to any runner.** `RoutedExecutor(journal=)` exists; the two
  runners build intents without an `intent_id`.
- **The ProjectX adapter cannot send an order**, by design, and declares AUTH only. Fifteen
  further capabilities are `documented_only` with `docs/topstep/API.md` citations. No token
  has ever been requested from this repository.
- **`paper_trade.py`** has an empty chain and different limits from the intraday sleeve.
- **The Topstep rulebook** still carries the XFA scaling ladder as OWNER-tier and its
  `unresolved()` omits two items `docs/topstep/RULES.md` marks OWNER (`docs/RISK.md` item 14).
- **`docs/RISK.md` lists fourteen places** where the code does less than existing prose
  implied; two are closed by `f7afd6d` (the empty chain, the flatten flag). The other twelve
  are open and named there, including: the funnel's walk-forward gate is a 5-way sign test,
  not `core/validation.purged_walk_forward`; the funnel never calls
  `ExecutionSimulator.execute()`; the holdout has never been carved; `multipletest.py` and
  `robustness.py` have no production callers.
- **History depth.** 395 sessions on the deepest futures series against ~2,000 measured as
  necessary; MESU5/MNQU5 have aged out of IBKR retention.

## Gate

At `7331797` (before the runner unit): `ruff (core + tests)` PASS, `pyright` PASS, `pytest`
PASS - full suite. The one red stage, `ruff (2 changed elsewhere)`, lints two scripts another
track has modified and not committed (`scripts/intraday_backtest.py`, `scripts/sweep_a18.py`);
they are not touched by any commit here.

At `f7afd6d`: `ruff (core + tests)` PASS, `pyright` PASS, `pytest` **FAIL** - one test,
`test_launch_preflight::test_every_runner_importer_is_classified`, because the new
`tests/test_intraday_governor.py` imports the live runner and was in neither of `conftest`'s
classification sets. That test exists so that a new runner test is a decision, never an
accident; the decision taken is that it GATES the 09:25 launch (`conftest.RUNNER_TESTS`), so a
failure in the governor or the FLATTEN close-out refuses to trade. The stage
`ruff (5 changed elsewhere)` covered five scripts other tracks had modified and not committed.
The full-suite result after the classification commit is the last line of this section.

At `0285d12` (final): `ruff (core + tests)` PASS, `pyright` PASS, `pytest` **PASS** - the full
suite, 1,895 tests, 153 s. The only red stage is `ruff (10 changed elsewhere)`: ten scripts
other tracks have modified and not committed, none touched by any commit here.

## Scorecard

`scripts/qb_scorecard.py` measures the tree; it is not asserted about it. Run at `f7afd6d`,
while the suite was red on the one classification test above:

| dimension | score | what it measured |
|---|---|---|
| Execution safety | 9.0 | 6/6 boundary pieces; both runners route through an adapter; 3 adapters; the gap named is "no prop-firm adapter can send" - true by design |
| Observability, State isolation, Data integrity | 9.0 each | unchanged from the baseline |
| Live safety, Type safety, Research harness, Resource management, Architecture | 8.0 each | pyright 0 errors; ruff 0 findings on core+tests; 0 open P0s |
| ML pipeline integrity | 7.5 | 7/8 corrections; the ML sweeps still do not adopt HAC |
| Orchestration, Deployment safety | 7.0 each | judgement dimensions; no canary or staged rollout |
| Testing | 6.0 | 1,895 tests / 65 files, **suite RED at measurement** (the classification test); ML sweeps have no unit tests; coverage unmeasured |
| Research reproducibility | 6.0 | provenance on 0/40 of the most recent ledger rows - every recent writer is another track's sweep that does not stamp it |

Composite **7.82/10 at that moment**. Re-run at `0285d12` with the suite green: Testing rises
to 8.0 (its remaining weaknesses are the untested ML sweeps and unmeasured coverage), every
other dimension unchanged, composite **7.96/10 - the 8/10 target is still NOT MET**, by
0.04. What holds it under is Research reproducibility at 6.0 (0/40 recent ledger rows carry
provenance; every recent writer is another track's sweep) and the two judgement dimensions at
7.0 (no canary, no staged rollout). Neither is improved by claiming otherwise.

## Security

No credential, token or key appears in any file committed today; `.env` is gitignored (line
10) and `.env.example` carries `<placeholder>` values only. `QB_LIVE_TRADING_ENABLED` remains
necessary but not sufficient (`Authority.for_live` also needs the typed argument and the
per-account approval file). No live trading was enabled, no real order was placed, no
credential was requested.

## What this report does not claim

That any strategy has an edge. That the execution layer is live-capable. That the governor
protects `paper_trade.py`. That the Topstep rulebook is complete. It claims the research
engine is validated, that the safety layer exists with tests that defend each property, and
that exactly one live path (the intraday paper sleeve) now runs through it.
