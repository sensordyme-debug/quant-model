
## 2026-09-13 — where the multi-contract futures work actually landed

Recording this the way the daily track recorded S-39 in `560b0bb`, because the history is
otherwise misleading and this is the third instance today of the same hazard.

`98512df` ("ml: F-16 …") contains, under the ml track's message:

- `scripts/futures_fetch_multi.py` and `tests/test_futures_fetch_multi.py` — the multi-contract
  IBKR fetcher (clientId 77, historical only) and its 51 tests
- `research/futures_discovery_{es,mes,mnq}.json` — the corrected cross-contract funnel runs
- 408 lines of `research/experiments_futures.jsonl` — the ledger rows for those runs

What that commit actually delivered on this track:

  MES  358,845 bars  317d   NQ  447,596 bars  395d   MNQ  358,845 bars  317d
  all 0 FAIL / 2 WARN (roll_gap, roll_overlap), same profile as ES

  544 hypotheses across four contracts with the opening-range lookahead corrected:
  ES 124 statistical + 12 cost, MES 127 + 9, NQ 134 + 2, MNQ 135 + 1, ZERO survivors.

MES/MNQ stop a quarter short of ES/NQ because MESU5 and MNQU5 have aged out of IBKR
retention (error 200 by localSymbol and by contract month). Nothing was substituted.

THE RULE THAT LET IT HAPPEN, three times in one day and in both directions:
`git add -A` or a bare `git add <dir>` in a tree six tracks share. I did it to the S-39 files
and to `tests/test_intraday_splits.py` (split back out in `90704c4`); the ml track did it to
these. `AGENTS.md` already says "no more git add -A" — the missing half is that after clearing
a stale `.git/index.lock` you must check what is already staged before committing, because a
killed process leaves its staged files behind for whoever commits next.


## 2026-09-13 - the execution safety layer (master directive, Phases 0 and 6-10)

Phase 0 is `docs/ARCHITECTURE_AUDIT.md`. Its execution-layer findings were seven, and five
of them are closed by this commit, additively - `risk.py`, `execution.py`'s types, the
registry, the rulebook, the twin and the features are untouched beyond two small additions:

  core/governor.py     Reason (25 closed codes), Limits (frozen), AccountView (None = UNKNOWN),
                       LimitEngine (state limits deny, size limits reduce, unknown input ->
                       DATA_UNAVAILABLE), KillSwitch (reset only by a named person), Governor
                       (a RiskChain with every switch pre-installed; FLATTEN passes all of them)
  core/lifecycle.py    SessionMachine (no AUTHENTICATED->READY edge; READY needs all 13
                       Readiness fields), OrderMachine (PROTECTED vs UNPROTECTED are states)
  core/protection.py   verify() against the VENUE's working orders: acked + closing side +
                       protective side of entry + full size, or UNPROTECTED with the reason
  core/reconcile.py    Snapshot vs Snapshot -> named discrepancies; failure trips
                       POSITION_UNRECONCILED, a missing stop also trips BRACKET_UNVERIFIED,
                       a clean pass resets nothing
  core/idempotency.py  intent_id = hash of what the strategy knew; IntentJournal.claim() is
                       check+append under the ledger's lock; RoutedExecutor(journal=...)
                       refuses a duplicate AND an unlabelled intent before the chain
  core/locking.py      file_lock, lifted out of registry.py so both journals share it

Two defects found by the tests while writing them, both in my own code from earlier today:

  1. `registry._append` and the new journal appended without checking that the previous
     byte was a newline. A row torn by a crash mid-write would have swallowed the NEXT row -
     in the ledger that is a lost trial, in the journal a lost claim, which is a duplicate
     order. Both now start a row on its own line. Measured by writing a torn row and
     appending after it: before the fix the second row was unreadable.
  2. My first executor test built a RESEARCH authority against the simulated adapter and the
     authority ladder refused it at construction. Correct behaviour; wrong test. Left as a
     note because it is the property working.

CLI: `risk status --scope` reads a published governor.json through StateStore (scoped, so a
dryrun status cannot pass for paper); `risk reasons`; `session readiness`; `intents recover`
(non-zero when any intent is SUBMITTED with no outcome - reconcile, never resend).

Gate: ruff core+tests PASS, pyright PASS, pytest PASS (full suite). The one red stage is
`ruff (2 changed elsewhere)` on `scripts/intraday_backtest.py` and `scripts/sweep_a18.py`,
which are another track's uncommitted work and not touched here.

What is NOT done: no runner is wired to the governor; nothing connects to a venue; the
ProjectX live path is still `NotPermitted` by design. Wiring is a per-venue diff a person
reviews with the approval file in hand, not something this commit does on its own.


## 2026-09-13 - the intraday runner's chain is no longer empty

docs/RISK.md (written today) found both live runners construct `RoutedExecutor(RiskChain())`
with nothing in the chain: the sleeve's limits were applied by sizing code before an
OrderIntent existed. The seam the executor's own comment described had nothing in it.

Wired, in `scripts/intraday_trader.py`:
  - `Trader._arm_governor` on the first bar (nav_open is needed for the dollar limit):
    `Governor(Limits(max_daily_loss=DAILY_LOSS_LIMIT * nav_open))`, attached through a new
    `LiveExecutor.attach_governor()`. Same 2.5% the runner already enforces, now ALSO at the
    chain with a reason code (RISK_DAILY_LOSS) so no code path that forgets `stopped` can
    send an entry past it.
  - `Trader._refresh_governor` every bar: daily_pnl (None when a held symbol has no mark at
    all), positions, MANUAL_HALT tripped once by a HALT file, `publish()` to the PAPER
    StateStore on persisting runs so `risk status --scope paper` reads it.

One behaviour change, deliberate and flagged for the owner: a held symbol with NO price ever
seen (not the AUD-05 dropped-bar case, which is marked at the last level) now makes the
governor refuse NEW entries with DATA_UNAVAILABLE for that bar. Before, entries went through
on a partial P&L. Flatten is unaffected; the session is not ended.

The defect this exposed before a line of governor was attached: `Trader.step` called
`self.ex.submit(orders, t)` WITHOUT `flatten=`, so every loss-limit, HALT and 15:38 close-out
was a MARKET intent. Harmless only while the chain was empty; the first engine added could
have refused the order that closes the book - AUD-06/08 again, one layer up. The top-level
flattens (startup, --flatten) did pass the flag. Now `flatten=flatten` is passed and the test
asserts the loss-limit close-out arrives as a FLATTEN. SimExecutor and the two test fakes
accept the keyword.

8 tests in tests/test_intraday_governor.py; the 116 existing intraday tests still pass.
paper_trade.py is NOT wired - its chain is still empty and its daily sleeve has different
limits; that is the next reviewed diff, not this one.
