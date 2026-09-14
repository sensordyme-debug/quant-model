# Risk: the freeze, the chain, the authority ladder, and the parts nothing calls

Status of this document: describes `quant_brain/core/{risk,execution,mode,governor,protection,
reconcile,portfolio,lifecycle,sizing,idempotency}.py`, `quant_brain/brokers/{ibkr,projectx}.py`,
`quant_brain/markets/futures_cme/propfirm.py`'s risk engine, and the two live runners in
`scripts/`, at `HEAD = 28fa331` (2026-09-13 23:54 ET). Every measurement below was re-run
against that tree on 2026-09-14 and the command that produced it is given beside it. Other
tracks are editing this tree concurrently; nothing they have in flight touches the runners,
the risk chain or the authority ladder (`git status --porcelain`), so everything below is
true of the working tree as well as of the commit.

| claim | status | evidence |
|---|---|---|
| **THE SYSTEM CAN SEND AN ORDER** | **no** | `ORDER_TRANSMISSION_ENABLED = False` in both runners; `tests/test_no_order_can_be_transmitted.py` (8 tests, in the 09:25 gating set) |
| ENGINE VALIDATED | yes | `tests/test_qb_adapter.py` (31), `test_qb_mode.py` (36), `test_qb_projectx.py`, `test_qb_propfirm.py` (39), `test_qb_governor.py` (38) |
| STRATEGY VALIDATED | **no** | not a property of this layer; see `docs/RESEARCH.md` |
| LIVE EXECUTION VALIDATED | **no** | nothing has been transmitted since the freeze landed; the last live orders were 34 on 2026-09-11 (`live/log/intraday-2026-09-11.jsonl`) |
| PROFITABILITY DEMONSTRATED | **no** | |

Full suite at this commit: `python -m pytest -p no:cacheprovider` -> **2,220 passed,
9 skipped, 9 xfailed in 111 s** (2,238 collected). Every xfail is a deliberate ratchet:
seven are documented-but-unwired components (§7), one is the ledger-schema mismatch that
would make a Bonferroni denominator read zero, and one is the open leakage hole in
`sweep_s25` (`docs/VALIDATION.md`).

---

## 1. Order transmission is frozen, and that is the headline

Both runners carry a module-level constant, and it is the literal `False`:

```python
# scripts/intraday_trader.py:55
ORDER_TRANSMISSION_ENABLED = False
# scripts/paper_trade.py:75
ORDER_TRANSMISSION_ENABLED = False
```

**This system cannot currently place an order at any venue.** Not "will not without an
approval file", not "only in dry run" - cannot. The two mechanisms differ, because the two
runners are shaped differently, and both are pinned by
`tests/test_no_order_can_be_transmitted.py`, which is in `conftest.py`'s `RUNNER_TESTS` and
therefore gates the 09:25 scheduled launch (`scripts/intraday_launch.py` step 1 runs
`pytest -m runner` and refuses to start on a failure).

### `intraday_trader.py` - one chokepoint

`LiveExecutor.submit` (line 363) refuses on its **first statement**, before the RTH check,
before any `OrderIntent` exists, before the risk chain, before the adapter:

```python
# scripts/intraday_trader.py:363-367
def submit(self, orders: dict[str, int], when, *, flatten: bool = False):
    if not ORDER_TRANSMISSION_ENABLED:
        log("order_transmission_refused", orders=orders, flatten=flatten,
            reason="research_remediation_hard_disable")
        return []
```

`flatten=True` is refused on the same line as an entry. Everywhere else in this codebase a
flatten bypasses every gate (`core/risk.py`, `RiskEngine.__call__:87`); here it does not,
because the point of the freeze is that no message reaches the venue at all. Every submission
in the file routes through this one method, and `grep -n placeOrder scripts/intraday_trader.py`
returns nothing.

### `paper_trade.py` - two guards, on two paths, and they are not the same kind of guard

The **flatten** branch fires on `--flatten` or on the mere existence of `live/HALT`. It is
guarded at line 668, conditionally on the switch, and it is loud:

```python
# scripts/paper_trade.py:664-697 (abridged)
if HALT.exists() or args.flatten:
    if not ORDER_TRANSMISSION_ENABLED and not args.dry_run and ib and positions:
        print(f"REFUSED: order transmission is hard-disabled; {len(positions)} position(s) "
              f"were NOT closed and need a human: {positions}")
        log_event("refused", reason="research_remediation_hard_disable", path="flatten", ...)
        notify(... "position(s) are STILL OPEN and must be closed by hand in TWS" ...)
        return 3
```

The **rebalance** path is guarded at lines 826-832 by an **unconditional** early return -
`ORDER_TRANSMISSION_ENABLED` is not even read there. Everything below it, including the
`IBKRAdapter` at 843 and the `RoutedExecutor` at 846, is dead code and the file says so
("The code below remains intentionally unreachable until a reviewed controlled deployment
change removes the remediation guard"). Exit code 3 is the repository's "refused by a safety
gate" code.

### What the freeze costs right now, and it is not zero

The daily paper account is **not flat**. `live/state/nav_history.jsonl` (last row,
2026-09-13T14:43:41Z) reads NAV $988,031.55 against gross $1,492,497.74, and
`live/state/last_run.json` names the holdings: XLE, XLK, IWM, held since 2026-09-10. So a
`live/HALT` file today would print the refusal above and leave a 1.5x-gross book open for a
person to close by hand in TWS. That is the deliberate trade named in the code comment
beside the guard: nothing can OPEN a position, so nothing needs an automatic way out, and a
human closing a position deliberately beats a scheduled task doing it silently. It is still
worth stating plainly, because the alternative reading - "HALT flattens the book" - is what
the file's own header comment (line 7) still says.

The intraday book is flat (`live/state/intraday_book.json`: `"pos": {}`, dated 2026-09-11).

### What would have to change to send one order

| runner | change | what else breaks |
|---|---|---|
| `intraday_trader.py` | `ORDER_TRANSMISSION_ENABLED = True` at line 55 | `test_the_runner_declares_the_switch_and_it_is_off`, `test_the_two_runners_agree`, and `tests/test_intraday_p0.py::test_live_executor_hard_refuses_transmission_during_remediation`. All three are `runner`-marked, so `intraday_launch.py` refuses to start the 09:25 task until the tests are edited too. |
| `paper_trade.py` flatten | `ORDER_TRANSMISSION_ENABLED = True` at line 75 | the same two switch tests, plus `test_the_flatten_path_refuses_and_says_the_positions_are_still_open` |
| `paper_trade.py` rebalance | **also** delete lines 826-832 | nothing. No test guards that deletion. |

The constant is not read from the environment, a config file or the approval file. The
comment at line 53 says why: "This code constant cannot be overridden by an inherited
environment or a stale scheduler approval file." Underneath it, everything else still
applies - the `DU`-prefix account check (`paper_trade.py:656`), `live/APPROVED_PAPER.md`
(line 817), `live/HALT`, and the `Authority.paper(...)` check at `RoutedExecutor`
construction.

### What the freeze test cannot see

It is a source-structure test and says so. Two specific holes, from reading it:

- `_guarded_chokepoints` collects function **names**. Once `LiveExecutor.submit` is guarded,
  every call to anything named `submit` in that file is exempt - including
  `SimExecutor.submit` (line 294), which is harmless today because it is the in-memory replay
  executor, and including any future `submit` that is not.
- It proves nothing about a path that reaches a venue through a name outside
  `VENUE_CALLS = ("placeOrder", "flatten", "submit")`.
  `test_the_venue_call_list_still_matches_the_code` catches a rename, not an addition.

---

## 2. The chain: `core/risk.py`

`RiskDecision(allowed, quantity, reasons, binding)` has three outcomes: allowed unchanged,
allowed smaller, denied. A denial carries `quantity=0.0`, so a caller cannot accidentally use
a reduced size from a rejected decision. `binding` names the rule that bound.

`RiskDecision.merge` takes the more restrictive answer: denial beats reduction, the smaller
quantity beats the larger, and reasons accumulate. `RiskChain.evaluate` folds engines through
`merge` and short-circuits on the first denial, so **no ordering of engines lets a later one
re-permit what an earlier one denied**
(`tests/test_qb_adapter.py::test_no_ordering_of_engines_lets_a_later_one_re_permit`,
`tests/test_qb_propfirm.py::test_merge_is_order_independent_and_always_takes_the_tighter_answer`).

`RiskEngine.__call__` is the one asymmetry: a `FLATTEN` intent returns
`RiskDecision.allow(intent.quantity)` before `evaluate()` is reached, for every engine and
therefore for the chain. AUD-06 and AUD-08 (`research/audit_2026-09-12.md`) are both cases
where the order that would have closed a position was suppressed by a sizing or ownership
rule. A risk layer that can block the exit is not a risk layer
(`test_a_flatten_bypasses_every_engine_at_once`, `test_flatten_bypasses_a_chain_containing_a_denier`).

An engine sees an `OrderIntent` and whatever state it was constructed with. There is no
parameter through which a model can pass a confidence, an override or a priority.

---

## 3. The path: `core/execution.py`

```
Signal -> OrderIntent -> RiskChain -> RoutedExecutor -> ExecutionAdapter -> venue
```

`RoutedExecutor(risk, adapter, *, authority=None, on_event=None, journal=None)`:

- checks `authority.require(adapter.requires)` **at construction**. An omitted authority is
  `Authority.research()`, which reaches nothing (`test_an_omitted_authority_is_research_and_reaches_nothing`,
  `test_the_check_happens_at_construction_not_at_submit`);
- `submit(intents)` consults the chain per intent; a denied intent is never passed to the
  adapter; a reduced intent arrives at the reduced size; a reduction to zero is a refusal
  however it was spelled (`test_a_denied_intent_never_reaches_the_adapter`,
  `test_the_adapter_receives_the_reduced_size_not_the_requested_one`);
- `flatten(positions)` builds `FLATTEN` intents, which the chain cannot touch;
- every verdict, allowed or not, is kept in `decisions`; `refused` lists what never reached
  the venue and why; each outcome emits a named event - `duplicate_refused`, `risk_denied`,
  `risk_reduced`, `risk_zeroed`, `order_sent`, `venue_rejected`, `flatten_requested`
  (`_emit` call sites, `core/execution.py:315-389`);
- `journal` is optional and, when attached, refuses duplicate and unidentified non-flatten
  intents before the chain (`RoutedExecutor._claim`, line 349). **Neither runner passes one**, and
  neither sets `OrderIntent.intent_id`: `grep -n "intent_id\|journal" scripts/intraday_trader.py
  scripts/paper_trade.py` returns nothing.

`Ack` is deliberately not a `Fill`: acceptance and execution are different events, and
conflating them is how a runner comes to believe a queued order is a done trade.
`ExecutionAdapter.working()` must report **remaining** quantity, not submitted (AUD-06).

Structural, and tested: nothing outside `quant_brain/brokers/` imports `ib_async`,
`ib_insync`, `ibapi`, `alpaca` or `polygon` -
`tests/test_qb_adapter.py::test_nothing_outside_the_brokers_package_imports_a_broker_sdk`
walks the AST of every other module, and
`tests/test_production_reachability.py::test_no_broker_sdk_is_importable_above_the_broker_package`
repeats the cheap version.

---

## 4. The authority ladder: `core/mode.py`

`Mode` is an ordered `IntEnum`, so `>=` is the permission test:

```
RESEARCH(0)  BACKTEST(1)  VALIDATED(2)  PAPER(3)  PRACTICE(4)  HUMAN_APPROVAL(5)  EXECUTION_READY(6)
                                        ^ touches_a_venue from here          ^ risks_real_money only here
```

`Authority` is frozen. Constructors: `research()`, `backtest()`, `paper(venue, account)`,
`practice(venue, account)`, and `for_live(venue, account, *, i_understand_this_is_real_money,
approval_dir)`.

### The three locks

`for_live` is the only way to `EXECUTION_READY` and it refuses unless all three hold:

| lock | what | why one alone is an accident |
|---|---|---|
| 1 | `i_understand_this_is_real_money=True`, a keyword that has to be typed and cannot arrive by `**kwargs` from a config file | a default is an accident |
| 2 | `QB_LIVE_TRADING_ENABLED` in `{1, true, yes}` in the process environment | a stray environment variable is a stale-shell accident |
| 3 | a non-empty file at `live/approvals/<venue>-<account>.md`, written by a person | a file alone is a stale-artefact accident |

Per venue **and** per account, so a practice approval cannot authorise a funded account
(`test_an_approval_for_one_account_does_not_authorise_another`,
`test_an_approval_for_one_venue_does_not_authorise_another`). `write_approval()` documents
the file's shape and is, per its docstring, never called by automation. **`live/approvals/`
does not exist** on this machine (`ls live/`), so lock 3 fails for every venue and account.

`from_environment()` reads `QB_ACCOUNT_MODE` (and `QB_VENUE`, `QB_ACCOUNT` alongside it) and
can select any mode **up to PRACTICE**. `HUMAN_APPROVAL` and `EXECUTION_READY` are refused
with `NotPermitted` (`test_configuration_refuses_to_select_live`). Setting only the live
environment variable grants nothing (`test_setting_only_the_live_env_var_grants_nothing`).
`test_this_checkout_is_not_configured_for_live` asserts the tree you are reading is not.

`NotPermitted` subclasses `PermissionError` and is documented as always fatal, never caught
and downgraded.

---

## 5. Adapters and `requires`

| adapter | `requires` | reaches | notes |
|---|---|---|---|
| `SimulatedAdapter` | `BACKTEST` | nothing; in-memory | not `RESEARCH`, because a research context should not be constructing order paths at all |
| `IBKRAdapter(ib, contracts)` | `PAPER` | IB Gateway paper endpoint | sets `tif`, `outsideRth=False`, `orderRef` explicitly - each a defect already paid for (module docstring) |
| `IBKRAdapter(..., live=True)` | `EXECUTION_READY` | IB Gateway live endpoint | paper and live differ only by port, so the adapter assumes paper and `live=True` must be written down |
| `ProjectXAdapter(dry_run=True)` | `PRACTICE` | nothing; records `would_send` | the transport is never reached in dry run; there is no `send=False` flag on a live code path |
| `ProjectXAdapter(dry_run=False)` | `EXECUTION_READY` | TopstepX, in principle | `submit()` on a live path raises `NotPermitted("live order submission is not implemented")` (`brokers/projectx.py:351-370`) |
| `ExecutionAdapter` base default | `EXECUTION_READY` | - | an author who forgets to declare gets the strictest answer |

`python -m quant_brain broker list`, run from an unconfigured shell on 2026-09-14:

```
  this process holds RESEARCH

  adapter              requires          reachable  notes
  SimulatedAdapter     BACKTEST          NO         in-memory; nothing leaves
  IBKRAdapter          PAPER             NO         IB Gateway paper by default
  ProjectXAdapter      EXECUTION_READY   NO         TopstepX; dry run by default, cannot send
```

`ProjectXAdapter` keeps a second, independent axis, `ConnectionState`
(`DISCONNECTED, AUTHENTICATING, AUTHENTICATED, PRACTICE_READY, DRY_RUN, EXECUTION_READY,
HALTED`). `AUTHENTICATED` means a token exists and grants read access only;
`can_send` is `True` for `EXECUTION_READY` alone (`test_only_execution_ready_can_send`).
`arm()` on a non-dry-run session requires `confirmed_practice` established by a venue query,
not by the caller's belief. `halt()` is terminal; nothing in the module clears it.
`reconcile()` refuses rather than returning an empty position set, because an empty stub
would look like agreement with any local state. Full detail: `docs/topstep/EXECUTION.md`.

---

## 6. What the live runners actually wire

### `scripts/intraday_trader.py` - a chain with one engine in it

```python
# scripts/intraday_trader.py:351
self.routed = RoutedExecutor(risk or RiskChain(), self.adapter,
                             authority=Authority.paper("ibkr", ORDER_REF), ...)
```

`risk` still defaults to `None`, so the chain starts empty - but it no longer stays empty.
`Trader._arm_governor` (line 565) builds a `core.governor.Governor` on the first bar, once
`nav_open` is known, with `Limits(max_daily_loss=DAILY_LOSS_LIMIT * nav_open)`, and attaches
it through `LiveExecutor.attach_governor` (line 355). `_refresh_governor` (line 583) feeds it
the book every bar, sets `daily_pnl = None` when a position has no mark (which makes the
governor deny new entries with `DATA_UNAVAILABLE` rather than act on a partial sum - AUD-05),
and trips `Reason.MANUAL_HALT` when a HALT file appears. `Governor` carries 24 reason codes
(`python -c "from quant_brain.core.governor import Reason; print(len(list(Reason)))"` -> 24;
the commit message for `7331797` says 25).

**The governor has never been armed in a live session.** `grep -l governor_armed live/log/*.jsonl`
returns nothing across every log file in the directory. The last session that placed orders
was 2026-09-11 (34 `order` events), before the governor landed; 2026-09-12 and 2026-09-13
were a weekend and recorded preflight events only.

`python -m quant_brain risk status --scope paper` does print a governor state, dated
`2026-09-13T17:39:36Z`, with `max_daily_loss 25000.0`. That implies a start-of-day NAV of
exactly $1,000,000, which this account has never had. It is a test artefact left in
`live/state/governor.json` from before commit `0bababd` stopped the suite writing there, not
the record of a session.

### `scripts/paper_trade.py` - an empty chain, on unreachable code

Both `RoutedExecutor` constructions in this file (line 706 on the flatten path, line 846 on
the rebalance path) pass a bare `RiskChain()`, and both sit behind a guard that returns
before them.

### The limits that actually bind the intraday sleeve

They live in `scripts/intraday_common.py` and are applied by the sizing code in
`scripts/intraday_trader.py` **before** an `OrderIntent` exists - so the governor is a second
opinion on the daily-loss limit, not the only one:

| limit | value | where applied |
|---|---|---|
| `PER_SYMBOL_HARD_CAP` | 0.20 of equity | `intraday_common.py:70`, applied `intraday_trader.py:666` |
| `GROSS_HARD_CAP` | 1.6x | `intraday_common.py:71`, applied `intraday_trader.py:653` |
| `DAILY_LOSS_LIMIT` | 2.5% of start-of-day NAV, then flatten and stop | `intraday_common.py:72`, applied `intraday_trader.py:704`, and armed on the governor at `:575` |
| `FLATTEN_MINUTE` | 368 minutes after 09:30 = 15:38 ET | `intraday_common.py:73`; `flatten_minute_for()` at `intraday_trader.py:92` scales it on an early close |

The outside-RTH refusal is deliberately **not** a `RiskEngine`: a flatten bypasses every
engine, and an order sent outside RTH with `outsideRth=False` is queued to the next open with
nothing tracking it (AUD-08/09) - just as dangerous for a flatten as for an entry. So it is a
submission precondition on the whole batch (`LiveExecutor.submit`, after the freeze check).

The file kill switches for the equity sleeves are `live/HALT` and `live/HALT_INTRADAY`:
`intraday_trader.py` sets `stopped` and issues a flatten when either exists (`HALT_FILES`,
line 45; checked at line 695) - which `LiveExecutor.submit` then refuses, so the HALT stops
new decisions and does not close a book; `paper_trade.py` takes its flatten branch on
`live/HALT` (line 664) and refuses there too; and `scripts/intraday_launch.py:373` refuses to
start with exit code 3. These are checked by the runners, not by anything in `quant_brain/`.
Neither HALT file exists today (`ls live/`).

So the structural claim in `ARCHITECTURE.md` - one path to the venue, through the chain,
authority checked at construction - is true, and the intraday chain now has an engine in it.
The path itself ends in a refusal.

---

## 7. The risk components with no production caller

`tests/test_production_reachability.py` walks the import graph from six entry points
(`intraday_trader`, `paper_trade`, `intraday_launch`, `reconcile_state`, `backtest`,
`evaluate`) and from every non-test file that mentions `quant_brain`. Measured on
2026-09-14: **15 of 53 `quant_brain` modules are production-reachable, 19 more are
research-reachable, and 19 are reachable from nothing outside the test suite.**

Seven of those nineteen are pinned with `xfail(strict=True)` because the architecture
documents describe them as part of the system:

| module | what it would do | what stands in for it today |
|---|---|---|
| `core/protection.py` | bracket verification against the venue's working orders; `POSITION OPEN + STOP UNKNOWN -> UNPROTECTED` | nothing. Neither runner places a protective order, so **by this module's own definition every open position is UNPROTECTED for the whole session** - including the XLE/XLK/IWM book open right now |
| `core/reconcile.py` | two `Snapshot`s in, a `ReconcileResult` out, trips the governor's `POSITION_UNRECONCILED` and halts on any difference | `intraday_trader.reconcile_book` (line 146), which converges the book to the account for the sleeve's own universe and logs each discrepancy. It compares positions only - no orders, no fills, no equity, no staleness check - and it converges rather than halting. `paper_trade.py` reconciles nothing. |
| `core/portfolio.py` | portfolio exposure and correlated risk | the runner's `GROSS_HARD_CAP` scalar |
| `research/promotion.py` | `PromotionGate` | `scripts/evaluate.py`, whose criteria are CAR-first with no significance test, no multiplicity and no OOS requirement |
| `core/multipletest.py` | Holm / BH / BY / Reality Check / SPA / DSR / PBO | `stats.bonferroni_threshold` in one place; see `docs/VALIDATION.md` |
| `research/analytics.py` | trade analytics with UNAVAILABLE semantics | nothing |
| `research/robustness.py` | regime labelling, concentration and ordering nulls | nothing |

`core/lifecycle.py` (`SessionMachine`, `OrderMachine`, `Readiness`) is **not** on that list
and is unreachable all the same: its only importers are `core/reconcile.py` and
`quant_brain/__main__.py`, and both are themselves unreachable from any entry point. So there
is no submitted -> acknowledged -> partially filled -> filled -> protected progression in
anything a runner uses. It has 19 tests and no caller.

Two more modules are production-*reachable* without being production-*used*, and the
distinction matters:

- `core/idempotency.py` is reachable only because `core/execution.py` imports `IntentJournal`
  for its optional `journal=` parameter. No runner attaches one.
- `core/sizing.py` is reachable only because `core/governor.py:105` imports `SizeLimits`
  inside `Limits.size_limits()`. No runner constructs a `Sizer`.

Reachability is not use, and the reachability test says so in its own docstring.

---

## 8. The one `RiskEngine` implementation for futures: `PropFirmRiskEngine`

`quant_brain/markets/futures_cme/propfirm.py:400`. Reads an `AccountState` and its
`PropFirmProfile`; takes an `OrderIntent` and nothing else. In order:

1. denies on a dead account;
2. denies on a daily-loss breach (`day_pnl <= -daily_loss_limit`);
3. denies on equity at or below the trailing floor;
4. **denies a product not on `profile.permitted_products`, before any sizing** - the correct
   size for a product the account may not hold is zero whatever the caps say (added
   2026-09-13; `docs/PROP_FIRM.md`);
5. reduces to the room left under `max_contracts_per_symbol`, and under the total cap read
   from the scaling ladder at the account's **live** profit
   (`test_the_risk_engine_enforces_the_ladder_from_live_account_state`).

The total cap is now counted in the profile's own units. With `contract_equivalence=True` one
ES consumes ten units of a 50-unit Topstep allowance rather than one
(`PropFirmProfile.contract_units`, line 213). `in_blackout(when)` and
`must_be_flat(minutes_to_close, *, session_close=, is_last_session_of_week=)` are asked
separately because they gate the clock, not the size; the flat deadline is now the EARLIER of
a wall clock and the minutes-to-close offset, so 15:10 CT binds on a normal day and the
offset still binds on an early close (AUD-07).

Callers outside its tests: `quant_brain/venues/propfirm.py::TopstepRules.risk_engine`, which
nothing in a runner constructs, and `scripts/qb_scorecard.py`, which greps for the class to
measure the tree. It is in no runner's chain. There is no futures runner.

---

## 9. Not implemented

- **No bracket verification in any live path.** `core/protection.py` exists, has 23 tests and
  no caller. "Position open, stop unknown" is a state the system can represent in a library
  and cannot detect in a session.
- **No idempotency in any live path.** The field and the journal exist; neither runner sets
  or attaches them, so a duplicate submission after a restart is indistinguishable from a new
  one.
- **No compare-and-halt reconciliation.** `core/reconcile.py` has no caller;
  `projectx.reconcile()` refuses; the intraday runner's own `reconcile_book` converges
  positions and halts on nothing.
- **No order lifecycle state.** `Ack` is accepted or not.
- **No prop-firm engine in a live chain**, and no futures runner to put one in.
- **No live submission in `ProjectXAdapter`**, and no verified order, position or fill
  endpoint (`docs/topstep/API_UNKNOWNS.md`, Tier 1).
- **No paging.** Refusals are logged with the rule that bound (`live/log/*.jsonl`) and pushed
  to the chat channel by `notify()`; nothing escalates if nobody reads it (`BLOCKERS.md`
  OWNER-2).
- **No end-to-end test that a `RoutedExecutor` refusal stops a runner from calling
  `placeOrder`.** It is guaranteed by construction and exercised at the unit level
  (`docs/ARCHITECTURE_AUDIT.md`, "Missing tests"). `tests/test_no_order_can_be_transmitted.py`
  is a nearer relative but it is an AST test, not a behavioural one, and it says so.
- **No failure-injection suite** for the execution layer: network drop, token expiry,
  duplicate fill, corrupted state.

## 10. What this document does not claim

It does not claim any order can be sent from this tree; both runners refuse, and the one test
in the gating set that could catch a thaw is a source-structure test with two named blind
spots (§1). It does not claim the sleeve's risk limits are enforced by `RiskChain` alone -
the caps are runner code applied before an intent exists, and the governor duplicates only
the daily-loss limit. It does not claim the governor has ever run in production; it has not
(§6). It does not claim any position is protected, reconciled or idempotent; the modules that
would do those things have no caller (§7). It does not claim the authority ladder has ever
been raised above `PAPER` on this machine; `live/approvals/` does not exist and
`test_this_checkout_is_not_configured_for_live` asserts the rest. It does not claim any order
has ever reached a prop firm from this code; the adapter cannot send one.
