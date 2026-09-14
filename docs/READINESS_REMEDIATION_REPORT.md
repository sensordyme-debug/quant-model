# Research and Prop-Firm Readiness Remediation Report

**Status:** Phase 0 partially complete; the platform is **not** backtest-ready,
practice-ready, or Combine-ready.  This report records only verified facts.

## Safety contract

All order transmission is disabled for this remediation phase.  ProjectX already
refuses transmission by design.  The two existing IBKR runner paths are now
hard-refused before a broker order can be made.  The documented operational
defaults are `DRY_RUN=true`, `LIVE_TRADING_ENABLED=false`,
`EXECUTION_ENABLED=false`, and `ORDER_TRANSMISSION_ENABLED=false`.

No credentials were read, changed, printed, stored, or used.  No network or
broker endpoint was contacted.

## Verified Phase 0 changes

* `scripts/intraday_trader.py` no longer reads the unassigned local bar time at
  the first live-loop iteration.  The session-exit gate uses the current
  wall-clock date until a completed bar exists.
* `LiveExecutor.settle()` now treats `adapter.open` as the single source of
  truth and updates it in place.  This prevents a fill-book/pending-order split
  that could resend the same target delta.
* Intraday and daily paper runner submission is hard-disabled.  An existing
  approval file or command-line invocation cannot override this during the
  remediation phase.
* Regression coverage exercises the concrete `LiveExecutor` fill collection,
  the hard transmission refusal, and the corrected live-loop guard.

## Verification evidence

* `py -3.11 -m pytest tests/test_intraday_p0.py -q` with an isolated writable
  base temp directory: **32 passed**.
* `py -3.11 -m py_compile scripts/intraday_trader.py scripts/paper_trade.py`:
  **passed**.
* `git diff --check`: **passed**.

The default system temporary test directory was not readable in this execution
environment; the initial test invocation failed before test setup for that
environmental reason.  The isolated test run above is the validity evidence.

## Mandatory gates still open

These items are drawn from the hostile audit and remain blockers, not future
claims:

1. Create one mandatory experiment ledger with immutable hypothesis/family IDs,
   dataset and code fingerprints, trial accounting, provenance, and retractions.
2. Hash data and record source, timestamps, contract/roll treatment, session,
   and adjustment policy.  Mark futures rolls; do not call Obsidian market-data
   ground truth.
3. Correct the futures cost model (including mandatory flatten round turns),
   run the reachable simulator, and make costed results the headline metric.
4. Carve and lock a forward holdout before further selection.  Add causal
   guards, purged/embargoed walk-forward evaluation, block/bootstrap uncertainty,
   path reconstruction, and multiple-testing controls to the *actual* funnel.
5. Wire a single risk/execution path: intent identity and journal, deterministic
   policy chain, account/order reconciliation, restart recovery, and verified
   protection.  The present runners do not yet call those modules.
6. Build the Topstep digital twin only from current, verified rule sources.
   Unknown ProjectX account, working-order, bracket, flatten/cancel semantics
   must remain explicit unknowns until read-only or practice verification.
7. Add dependency lockfiles, CI, coverage, static analysis, adversarial tests,
   and reproducible run manifests.  The audit found none at the repository root.
8. Treat the existing Quant Brain vault as knowledge/context only after it is
   isolated from executable hooks and assigned an explicit provenance status.

## Promotion policy

No strategy may advance to practice or any Combine account until every gate is
implemented, reachable from the supported command path, independently tested,
and recorded with reproducible evidence.  A human must approve any later
controlled deployment change.  This report grants no trading authorization.
