# Risk: the chain, the authority ladder, the adapters, and what is not there yet

Status of this document: describes `quant_brain/core/{risk,execution,mode}.py`,
`quant_brain/brokers/{ibkr,projectx}.py` and `quant_brain/markets/futures_cme/propfirm.py`'s
risk engine at commit `2a7367f` (2026-09-13), plus how the two live runners in `scripts/`
use them. Work another agent is building concurrently in the same working tree is named as
in progress and is not described as functionality.

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | yes | `tests/test_qb_adapter.py`, `test_qb_mode.py`, `test_qb_projectx.py`, `test_qb_propfirm.py` |
| STRATEGY VALIDATED | **no** | not a property of this layer; see `docs/RESEARCH.md` |
| LIVE EXECUTION VALIDATED | **no** | `ProjectXAdapter.submit()` raises on any live path; the IBKR adapter is used against a **paper** account only |
| PROFITABILITY DEMONSTRATED | **no** | |

---

## The chain: `core/risk.py`

`RiskDecision(allowed, quantity, reasons, binding)` has three outcomes: allowed unchanged,
allowed smaller, denied. A denial carries `quantity=0.0`, so a caller cannot accidentally use
a reduced size from a rejected decision. `binding` names the rule that bound.

`RiskDecision.merge` takes the more restrictive answer: denial beats reduction, the smaller
quantity beats the larger, and reasons accumulate. `RiskChain.evaluate` folds engines through
`merge` and short-circuits on the first denial, so **no ordering of engines lets a later one
re-permit what an earlier one denied**
(`test_no_ordering_of_engines_lets_a_later_one_re_permit`,
`test_merge_is_order_independent_and_always_takes_the_tighter_answer`).

`RiskEngine.__call__` is the one asymmetry: a `FLATTEN` intent returns
`RiskDecision.allow(intent.quantity)` before `evaluate()` is reached, for every engine and
therefore for the chain. AUD-06 and AUD-08 (`research/audit_2026-09-12.md`) are both cases
where the order that would have closed a position was suppressed by a sizing or ownership
rule. A risk layer that can block the exit is not a risk layer
(`test_a_flatten_bypasses_every_engine_at_once`, `test_flatten_bypasses_a_chain_containing_a_denier`).

An engine sees an `OrderIntent` and whatever state it was constructed with. There is no
parameter through which a model can pass a confidence, an override or a priority.

---

## The path: `core/execution.py`

```
Signal -> OrderIntent -> RiskChain -> RoutedExecutor -> ExecutionAdapter -> venue
```

`RoutedExecutor(risk, adapter, *, authority=None, on_event=None)`:

- checks `authority.require(adapter.requires)` **at construction**. An omitted authority is
  `Authority.research()`, which reaches nothing (`test_an_omitted_authority_is_research_and_reaches_nothing`,
  `test_the_check_happens_at_construction_not_at_submit`);
- `submit(intents)` consults the chain per intent; a denied intent is never passed to the
  adapter; a reduced intent arrives at the reduced size; a reduction to zero is a refusal
  however it was spelled (`test_a_denied_intent_never_reaches_the_adapter`,
  `test_the_adapter_receives_the_reduced_size_not_the_requested_one`);
- `flatten(positions)` builds `FLATTEN` intents, which the chain cannot touch;
- every verdict, allowed or not, is kept in `decisions`; `refused` lists what never reached
  the venue and why; each outcome emits a named event (`risk_denied`, `risk_reduced`,
  `risk_zeroed`, `order_sent`, `venue_rejected`, `flatten_requested`).

`Ack` is deliberately not a `Fill`: acceptance and execution are different events, and
conflating them is how a runner comes to believe a queued order is a done trade.
`ExecutionAdapter.working()` must report **remaining** quantity, not submitted (AUD-06).

Structural, and tested: nothing outside `quant_brain/brokers/` imports `ib_async`,
`ib_insync`, `ibapi`, `alpaca` or `polygon` -
`tests/test_qb_adapter.py::test_nothing_outside_the_brokers_package_imports_a_broker_sdk`
walks the AST of every other module.

---

## The authority ladder: `core/mode.py`

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
the file's shape and is, per its docstring, never called by automation.

`from_environment()` reads `QB_ACCOUNT_MODE` (and `QB_VENUE`, `QB_ACCOUNT` alongside it) and
can select any mode **up to PRACTICE**. `HUMAN_APPROVAL` and `EXECUTION_READY` are refused
with `NotPermitted` (`test_configuration_refuses_to_select_live`). Setting only the live
environment variable grants nothing (`test_setting_only_the_live_env_var_grants_nothing`).
`test_this_checkout_is_not_configured_for_live` asserts the tree you are reading is not.

`NotPermitted` subclasses `PermissionError` and is documented as always fatal, never caught
and downgraded.

---

## Adapters and `requires`

| adapter | `requires` | reaches | notes |
|---|---|---|---|
| `SimulatedAdapter` | `BACKTEST` | nothing; in-memory | not `RESEARCH`, because a research context should not be constructing order paths at all |
| `IBKRAdapter(ib, contracts)` | `PAPER` | IB Gateway paper endpoint | sets `tif`, `outsideRth=False`, `orderRef` explicitly - each a defect already paid for (module docstring) |
| `IBKRAdapter(..., live=True)` | `EXECUTION_READY` | IB Gateway live endpoint | paper and live differ only by port, so the adapter assumes paper and `live=True` must be written down |
| `ProjectXAdapter(dry_run=True)` | `PRACTICE` | nothing; records `would_send` | the transport is never reached in dry run; there is no `send=False` flag on a live code path |
| `ProjectXAdapter(dry_run=False)` | `EXECUTION_READY` | TopstepX, in principle | `submit()` on a live path raises `NotPermitted("live order submission is not implemented")` |
| `ExecutionAdapter` base default | `EXECUTION_READY` | - | an author who forgets to declare gets the strictest answer |

`python -m quant_brain broker list` prints this table against the authority the current
process holds; from an unconfigured shell every row reads `NO` because the process holds
`RESEARCH`.

`ProjectXAdapter` keeps a second, independent axis, `ConnectionState`
(`DISCONNECTED, AUTHENTICATING, AUTHENTICATED, PRACTICE_READY, DRY_RUN, EXECUTION_READY,
HALTED`). `AUTHENTICATED` means a token exists and grants read access only;
`can_send` is `True` for `EXECUTION_READY` alone (`test_only_execution_ready_can_send`).
`arm()` on a non-dry-run session requires `confirmed_practice` established by a venue query,
not by the caller's belief. `halt()` is terminal; nothing in the module clears it.
`reconcile()` refuses rather than returning an empty position set, because an empty stub
would look like agreement with any local state. Full detail: `docs/topstep/EXECUTION.md`.

---

## What the live runners actually wire today

Both runners construct the path above. Neither puts an engine in the chain.

```python
# scripts/intraday_trader.py:346
self.routed = RoutedExecutor(risk or RiskChain(), self.adapter,
                             authority=Authority.paper("ibkr", ORDER_REF), ...)
# scripts/paper_trade.py:650 (HALT / --flatten path) and :765 (the rebalance)
routed = RoutedExecutor(RiskChain(), adapter, authority=Authority.paper("ibkr", "daily"), ...)
```

`risk` defaults to `None` in `LiveExecutor.__init__`, so the chain is empty in production. The
comment beside it says so: "An empty chain today. It is the seam." The limits the intraday
sleeve actually enforces live in `scripts/intraday_common.py` and are applied by the sizing
code in `scripts/intraday_trader.py` **before** an `OrderIntent` exists:

| limit | value | where applied |
|---|---|---|
| `PER_SYMBOL_HARD_CAP` | 0.20 of equity | `intraday_trader.py:602` |
| `GROSS_HARD_CAP` | 1.6x | `intraday_trader.py:589` |
| `DAILY_LOSS_LIMIT` | 2.5% of start-of-day NAV, then flatten and stop | `intraday_trader.py:638` |
| `FLATTEN_MINUTE` | 15:38 ET | `intraday_common.py:73` |

The outside-RTH refusal is deliberately **not** a `RiskEngine`: a flatten bypasses every
engine, and an order sent outside RTH with `outsideRth=False` is queued to the next open with
nothing tracking it (AUD-08/09) - just as dangerous for a flatten as for an entry. So it is a
submission precondition on the whole batch (`LiveExecutor` docstring).

The file kill switches for the equity sleeves are `live/HALT` and `live/HALT_INTRADAY`:
`intraday_trader.py` flattens and stops when either exists (`HALT_FILES`, line 629),
`paper_trade.py` flattens on `live/HALT` (line 639), and `scripts/intraday_launch.py`
refuses to start with exit code 3. These are checked by the runners, not by anything in
`quant_brain/`.

So the structural claim in `ARCHITECTURE.md` - one path to the venue, through the chain,
authority checked at construction - is true. The chain that path runs through has no engines
in it, and the sleeve's risk rules are runner code.

---

## The one `RiskEngine` implementation at HEAD: `PropFirmRiskEngine`

`quant_brain/markets/futures_cme/propfirm.py`. Reads an `AccountState` and its
`PropFirmProfile`; takes an `OrderIntent` and nothing else. Denies on a dead account, a
daily-loss breach (`day_pnl <= -daily_loss_limit`) and equity at or below the trailing floor;
reduces to the room left under `max_contracts_per_symbol` and under the total cap, where the
total cap is read from the scaling ladder at the account's **live** profit
(`test_the_risk_engine_enforces_the_ladder_from_live_account_state`). `in_blackout(when)` and
`must_be_flat(minutes_to_close, is_last_session_of_week=)` are asked separately because they
gate the clock, not the size; the flat deadline is relative to the close so early closes are
correct (AUD-07).

Callers outside its tests: `scripts/qb_scorecard.py`, which instantiates it to measure the
tree. It is in no runner's chain. There is no futures runner.

---

## Landed today - committed, NOT wired into any live path

Written at ~12:10 ET on 2026-09-13 while the following were untracked; they have since
landed as `ec12d30` (venues), `be75937` (sizing, portfolio), `7331797` (governor, lifecycle,
protection, reconcile, idempotency, locking, CLI) and `017c2cc` (analytics). Everything below
about what they do NOT do still holds at those commits:

```
quant_brain/core/governor.py      quant_brain/core/lifecycle.py     quant_brain/core/idempotency.py
quant_brain/core/locking.py       quant_brain/core/protection.py    quant_brain/core/reconcile.py
quant_brain/core/sizing.py        quant_brain/core/portfolio.py     quant_brain/research/analytics.py
quant_brain/venues/               docs/ARCHITECTURE_AUDIT.md
tests/test_qb_governor.py  test_qb_lifecycle.py  test_qb_idempotency.py  test_qb_protection.py
tests/test_qb_reconcile.py  test_qb_sizing.py  test_qb_analytics.py
```

and modifications to tracked files (in `7331797`): `quant_brain/core/execution.py` gains
an optional `OrderIntent.intent_id` field and a `RoutedExecutor(..., journal=None)` parameter
that, when a journal is attached, refuses duplicate and unidentified non-flatten intents
before the chain; `quant_brain/research/registry.py` re-exports its file lock from
`core/locking.py`; `quant_brain/__main__.py` gains `risk status`, `risk reasons`,
`session readiness` and `intents recover`; `ARCHITECTURE.md` gains core-table rows for the new
modules, plus `tests/test_qb_cli_safety.py` and `tests/test_qb_venues.py`. Their intent, from their own docstrings and from the author's entry in
`research/journal_futures.md` ("the execution safety layer", 2026-09-13): reason codes and
stateful kill switches (`governor`), session and order state machines (`lifecycle`),
deterministic intent identity and an append-only journal (`idempotency`), bracket verification
(`protection`), compare-and-halt reconciliation (`reconcile`). That journal entry itself says
"no runner is wired to the governor; nothing connects to a venue".

What this document records about them is only what can be verified from the tree: they
exist and are committed. The intraday runner (`scripts/intraday_trader.py`, commit "the
intraday runner's chain is no longer empty") now arms a `Governor` with the sleeve's 2.5%
daily-loss limit on its first bar and attaches it to `LiveExecutor`'s chain, told UNKNOWN on an
unmarked position and tripped MANUAL_HALT by a HALT file; the same commit makes the in-loop
close-outs FLATTEN intents, which they were not. `scripts/paper_trade.py`'s chain is still empty;
neither runner sets an `intent_id` or passes a `journal`, no scheduled task or preflight publishes the state the new
CLI commands read, and the 1,550-test count quoted elsewhere in these documents was taken
before their test files appeared (the suite is larger now; `docs/IMPLEMENTATION_REPORT.md`
carries the current count). Nothing in this section is a claim that any of it protects a live
order today: a module that no runner constructs protects nothing, and that wiring is a
reviewed, per-venue diff, not a side effect of these commits.

## Not implemented

At `2a7367f`, the HEAD this document was measured against, none of the following existed.
The commits named above add the modules; none of them is wired into a live path, so each
item below should be read as "exists in `quant_brain/core/`, enforced nowhere yet".

- **No kill-switch family in `quant_brain/`.** The chain evaluates limits on an intent;
  nothing in the committed core trips on stale data, a dead connection, an unreconciled
  position or an unverified stop, and nothing stays tripped until a person resets it. The only
  kill switches in use are the `live/HALT*` files read by the equity runners.
- **No bracket verification.** There is no notion of a protected position; "position open,
  stop unknown" is not a state the committed system can represent or detect.
- **No idempotency in any live path.** At `HEAD` an `OrderIntent` has no identity; in the
  working tree the field exists but neither runner sets it or attaches a journal.
- **No reason-code taxonomy.** `RiskDecision.binding` carries free-text rule names.
- **No order lifecycle state.** `Ack` is accepted or not; there is no submitted -> acknowledged
  -> partially filled -> filled -> protected progression in anything a runner uses.
- **No reconciliation engine.** `projectx.reconcile()` refuses; there is no compare-and-halt
  over positions, orders, fills and equity for any venue in use.
- **No prop-firm engine in a live chain**, and no futures runner to put one in.
- **No live submission in `ProjectXAdapter`**, and no verified order, position or fill
  endpoint (`docs/topstep/API_UNKNOWNS.md`, Tier 1).
- **No paging.** Refusals are logged with the rule that bound (`live/log/*.jsonl`); nothing
  gets a person to look (`BLOCKERS.md` OWNER-2).
- **No test that a `RoutedExecutor` refusal stops a runner from calling `placeOrder`**
  end to end; it is guaranteed by construction and exercised at the unit level only
  (`docs/ARCHITECTURE_AUDIT.md`, "Missing tests").

## What this document does not claim

It does not claim the live sleeves' risk limits are enforced by `RiskChain`; they are enforced
by runner code and the chain is empty. It does not claim any kill switch, bracket check,
idempotency guard or reconciliation exists in a committed or wired form; the in-progress files
are named as in progress and nothing in a live path calls them. It does not claim the
authority ladder has ever been raised above `PAPER` on this machine; the tests and the CLI say
it has not. It does not claim any order has ever reached a prop firm from this code; the
adapter cannot send one.
