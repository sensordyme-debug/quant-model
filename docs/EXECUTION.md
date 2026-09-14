# Execution: how an order would reach a venue, and every safety device on that path

Status of this document: describes the working tree at commit `4fbc22e` (2026-09-13) **plus
uncommitted changes**. `scripts/intraday_trader.py`, `scripts/paper_trade.py`,
`quant_brain/markets/futures_cme/instruments.py`, `quant_brain/markets/futures_cme/execution_sim.py`
and `scripts/futures_discover.py` are all modified in the working tree and not yet committed
(`git status --porcelain`), so a reader who checks out `4fbc22e` will not see what is described
here. Every number below cites the file and function it came from, or the read-only command
that produced it.

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | partly | `tests/test_qb_adapter.py` (31 tests over the routing and the IBKR adapter), `tests/test_qb_mode.py`, `tests/test_intraday_p0.py` (32), `tests/test_qb_execution_sim.py` (44) — all passing as of this writing |
| LIVE EXECUTION VALIDATED | **no** | order transmission is hard-disabled in both runners; **nothing has been sent since the disable landed** |
| THE SYSTEM CAN SEND AN ORDER | **no** | Both runners refuse. The `--flatten` / HALT hole described below was real when this document was written and was closed the same day in `a6506fb`; `tests/test_no_order_can_be_transmitted.py` now enforces it |
| PROFITABILITY DEMONSTRATED | **no** | see `docs/BACKTESTING.md` |

---

## 1. The system cannot place an order today, and that is deliberate

Two runners can reach IB Gateway. Both have been hard-disabled for the current research
remediation phase (`docs/READINESS_REMEDIATION_REPORT.md`).

### `scripts/intraday_trader.py` — a module constant, checked in the one submit path

```python
# scripts/intraday_trader.py:55
ORDER_TRANSMISSION_ENABLED = False
```

```python
# scripts/intraday_trader.py:363-367
def submit(self, orders: dict[str, int], when, *, flatten: bool = False):
    if not ORDER_TRANSMISSION_ENABLED:
        log("order_transmission_refused", orders=orders, flatten=flatten,
            reason="research_remediation_hard_disable")
        return []
```

The check is the **first** statement of `LiveExecutor.submit`. It precedes the RTH refusal, the
`OrderIntent` construction, the risk chain and the adapter. The `flatten=True` case is refused
on the same line as an entry, which is unusual — everywhere else in this codebase a flatten
bypasses every gate (`quant_brain/core/risk.py`, `RiskEngine.__call__`) — and it is correct
here, because the intent of the disable is that no message reaches the venue at all.

That is the only door. Every submission in the file routes through `ex.submit(...)`:

| line | caller |
|---|---|
| `intraday_trader.py:742` | the per-bar trading step |
| `intraday_trader.py:855` | `--flatten-from-account` |
| `intraday_trader.py:869` | `--flatten` |
| `intraday_trader.py:881` | stale-book cleanup at start-up |
| `intraday_trader.py:944` | the end-of-run flatten |

`grep -n "placeOrder" scripts/intraday_trader.py` returns nothing: the file has no second path
to the broker. Pinned by `tests/test_intraday_p0.py::test_live_executor_hard_refuses_transmission_during_remediation`,
which constructs a bare `LiveExecutor` and asserts `submit(...) == []` and that
`order_transmission_refused` was logged.

**Two consequences of the disable that are not defects but are worth knowing.** The start-up
block at `intraday_trader.py:828-836` still calls `ib.cancelOrder` on stale `orderRef=INTRADAY`
orders — a write to the venue, just not a new order. And `--flatten-from-account`
(`intraday_trader.py:847-866`) clears `book.pos` and `book.cost` unconditionally after a submit
that now sends nothing, so it forgets positions the account still holds; it does report them
(`remaining intraday positions: ...`, exit code 2) rather than claiming success.

### `scripts/paper_trade.py` — an unconditional early return on the rebalance path

```python
# scripts/paper_trade.py:788-794
    # This repository is in research/backtest remediation. Keep this guard before
    # any broker object so a CLI flag or stale approval cannot transmit an order.
    print("REFUSED: order transmission is hard-disabled during research remediation")
    log_event("refused", reason="research_remediation_hard_disable")
    notify("paper_trade REFUSED: order transmission is hard-disabled during research remediation. " + plan_text)
    ib.disconnect()
    return 3
```

There is no condition on it. Everything below — the `IBKRAdapter` at line 805, the
`RoutedExecutor` at 808, `routed.submit(...)` at 812 — is unreachable, and the file says so in
a comment. Exit code 3 is the repository's "refused by a safety gate" code
(`paper_trade.py` docstring, line 31).

### The hole that was here: `paper_trade.py --flatten` and `live/HALT`

**CLOSED 2026-09-14 in `a6506fb`.** The section below is kept as the description of the
defect, because a hole this shape can come back and the shape is the useful part. What
changed: the flatten branch now checks `ORDER_TRANSMISSION_ENABLED` before it constructs
anything, prints and logs `path="flatten"`, and pushes a message saying the positions are
STILL OPEN and need closing by hand. The rebalance guard, which used to be unconditional,
now reads the same constant, so one switch governs both paths instead of a half-thaw in
which the runner could close positions but not open them.


`docs/READINESS_REMEDIATION_REPORT.md` states that "the two existing IBKR runner paths are now
hard-refused before a broker order can be made." **For `paper_trade.py` that is true of the
rebalance path only.** The flatten branch runs at lines 657-682, roughly 130 lines *before* the
guard:

```python
# scripts/paper_trade.py:661-672
        if not args.dry_run and ib and positions:
            held = {s_: q_ for s_, q_ in positions.items() if q_}
            contracts = {s_: Stock(IB_SYMBOL_MAP.get(s_, s_), "SMART", "USD") for s_ in held}
            if contracts:
                ib.qualifyContracts(*contracts.values())
            routed = RoutedExecutor(RiskChain(),
                                    IBKRAdapter(ib, contracts, order_ref=ORDER_REF),
                                    authority=Authority.paper("ibkr", "daily"),
                                    on_event=lambda ev, **kw: log_event(ev, **kw))
            trades = [a.handle for a in routed.flatten(held, tag=ORDER_REF) if a.accepted]
```

`RoutedExecutor.flatten` builds `OrderType.FLATTEN` intents, which the risk chain is required
to pass unchanged (`core/risk.py` docstring), and `IBKRAdapter.submit` calls
`self.ib.placeOrder(contract, self._order(intent))` (`quant_brain/brokers/ibkr.py:76`). So
`python scripts/paper_trade.py --flatten` without `--dry-run`, or any run at all while
`live/HALT` exists, would send market orders to the connected paper account today. It reaches
that branch after the account-id check (`account_id.startswith("DU")`, line 649) and before the
approval-file check (line 779) — so it does not even require `live/APPROVED_PAPER.md`.

Whether that is a bug depends on what the disable is for. If the aim is "no new risk", flatten
is the one order you want to keep. If the aim is what the remediation report says — "no broker
order can be made" — it is a gap. It was resolved in favour of the second reading, and the
reasoning is worth stating because it is not obvious: refusing to flatten is safe here ONLY
because nothing in the repository can open a position. With no way in, there is no need for an
automatic way out, and a human closing a position deliberately beats a scheduled task doing it
quietly. That argument stops holding the moment either runner is thawed, which is why the two
paths now share one switch.

There is also now a test, which there was not: `tests/test_no_order_can_be_transmitted.py`, ten
assertions, in the 09:25 gating set so a failure stops the sleeve rather than warning.

### What would have to change to enable transmission

For the intraday sleeve, one line: `ORDER_TRANSMISSION_ENABLED = True` at
`intraday_trader.py:55`. The constant is not read from the environment, a config file or the
approval file, which is the point — the file's comment says "This code constant cannot be
overridden by an inherited environment or a stale scheduler approval file." Flipping it also
breaks `tests/test_intraday_p0.py::test_live_executor_hard_refuses_transmission_during_remediation`,
so the change cannot pass the preflight in `scripts/intraday_launch.py` (step 1 runs the
`runner`-marked tests) without also editing that test.

For the daily runner, deleting the five lines at `paper_trade.py:790-794`. No test guards it.

Everything else that gates a live order is unchanged and still applies underneath: the
`DU`-prefix account check, `live/APPROVED_PAPER.md`, `live/HALT`, and `Authority.paper(...)`
being checked when the `RoutedExecutor` is constructed.

---

## 2. The path an order would take

These are the modules production actually loads, measured rather than asserted.
`tests/test_production_reachability.py` walks the import graph from six entry points
(`scripts/intraday_trader.py`, `paper_trade.py`, `intraday_launch.py`, `reconcile_state.py`,
`backtest.py`, `evaluate.py`) and pins six of them as required:

```
quant_brain.core.risk         the chain every order passes
quant_brain.core.execution    RoutedExecutor: the one path to a venue
quant_brain.core.governor     the limits actually armed by the intraday runner
quant_brain.core.mode         the authority ladder checked at construction
quant_brain.core.state        StateScope containment
quant_brain.brokers.ibkr      the only adapter that can reach a venue
```

`test_the_order_path_is_loaded_by_production` fails if any of them loses its last production
importer. All six pass.

The order of operations, from `RoutedExecutor.submit` (`core/execution.py:308-347`):

| # | stage | where | what it can do |
|---|---|---|---|
| 0 | transmission disable | `intraday_trader.py:364` | returns `[]`; nothing below runs |
| 1 | authority | `RoutedExecutor.__init__` -> `Authority.require(adapter.requires)` | raises `NotPermitted` at **construction**, not at the first order |
| 2 | idempotency journal | `RoutedExecutor._claim` | **inert** — no runner passes a `journal`, so it returns `None` immediately |
| 3 | risk chain | `self.risk(intent)` | deny, reduce, or allow. A denial is terminal; `RiskChain.merge` takes the most restrictive answer and no ordering re-permits |
| 4 | reduce-to-zero | `sized.quantity <= 0` | a reduction to zero is treated as a refusal however it was spelled |
| 5 | adapter | `IBKRAdapter.submit` | `ib.placeOrder`. Returns an `Ack`, never raises for an ordinary venue refusal |

A `FLATTEN` intent skips stage 3 entirely: `RiskEngine.__call__` returns
`RiskDecision.allow(intent.quantity)` before `evaluate()` is reached, for every engine and
therefore for the chain. The reasoning is in `core/risk.py`'s docstring — a risk layer that can
block the exit is not a risk layer. Stage 0 does **not** exempt it, deliberately.

### What is actually in the risk chain

`LiveExecutor.__init__` builds `RoutedExecutor(risk or RiskChain(), ...)` — an **empty** chain.
It is filled at runtime by `Trader._arm_governor` (`intraday_trader.py:565-581`), on the first
bar, once `nav_open` is known:

```python
limit = DAILY_LOSS_LIMIT * self.nav_open        # DAILY_LOSS_LIMIT = 0.025, intraday_common.py:72
self.governor = Governor(Limits(max_daily_loss=limit), self.view)
attached = bool(self.ex.attach_governor(self.governor))
```

So exactly **one** limit reaches the chain: a daily loss limit at 2.5% of start-of-day NAV.
`core/governor.py`'s `Limits` supports many more (per-trade risk, position size, drawdown, open
positions, contract count); none of them is configured here. The per-symbol cap (0.20) and gross
cap (1.6) from `intraday_common.py:70-71` are applied by *sizing code*, before an `OrderIntent`
exists, and therefore carry no reason code and cannot be seen in the chain's `decisions` list.

`paper_trade.py` passes a bare `RiskChain()` on both its paths (lines 668 and 808) and never
attaches anything. Its order path has **no risk rule at all**; its protections are the
account-prefix check, the approval file, the HALT file, the data-quality gate and a margin
ceiling, all of them procedural checks inside `main()` rather than engines in the chain.

### The authority ladder

`core/mode.py` orders seven modes, `RESEARCH < BACKTEST < VALIDATED < PAPER < PRACTICE <
HUMAN_APPROVAL < EXECUTION_READY`, and an adapter declares the minimum it needs.
`IBKRAdapter.requires` is `Mode.PAPER` unless constructed with `live=True`, in which case it is
`Mode.EXECUTION_READY`. Both runners construct `Authority.paper("ibkr", ...)`, so a
`live=True` adapter would raise `NotPermitted` at construction.

`Authority.for_live()` is the only route to `EXECUTION_READY` and needs three independent
things: the keyword `i_understand_this_is_real_money=True` written in code, the environment
variable `QB_LIVE_TRADING_ENABLED` set truthy outside the process, and a non-empty approval
file at `live/approvals/<venue>-<account>.md`. `from_environment()` refuses to produce anything
at or above `HUMAN_APPROVAL` from configuration. Nothing in the repository calls `for_live`
outside tests (`grep -rn "for_live" scripts/ algorithms/` returns nothing).

---

## 3. The broker adapter boundary

`quant_brain/brokers/ibkr.py` is the only module above the script layer that names `ib_async`.
`tests/test_qb_adapter.py::test_nothing_outside_the_brokers_package_imports_a_broker_sdk` walks
the AST of every file under `quant_brain/` except `quant_brain/brokers/` and fails on any
`Import`/`ImportFrom` whose root package is in `{ib_async, ib_insync, ibapi, alpaca, polygon}`.
It is parsed and not grepped because `core/execution.py` names `ib_async` in prose.
`tests/test_qb_adapter.py::test_the_check_above_would_actually_catch_an_offender` proves the
walk sees a real import. A second, cheaper copy of the same check lives in
`tests/test_production_reachability.py::test_no_broker_sdk_is_importable_above_the_broker_package`.

**The check does not cover `scripts/`.** Fourteen import sites in eight scripts import
`ib_async` directly, including both runners:

```
$ grep -rn "from ib_async" scripts/*.py
scripts/fetch_minute.py:255            scripts/intraday_data.py:210,219,389
scripts/futures_capability_audit.py:81 scripts/intraday_trader.py:808
scripts/futures_data.py:89,194,339     scripts/paper_trade.py:265,606
scripts/futures_fetch_multi.py:216,342 scripts/reconcile_state.py:92
```

Most are data fetchers, where a connection is the point. The two in the runners are the
`IB()` connection object and the `Stock(...)` contract constructor — the *orders* go through the
adapter. So the property that holds is "the library `quant_brain` does not depend on a broker
SDK", not "no code outside `quant_brain/brokers/` names a broker".

Three details in `ibkr.py` that each cost a defect once, and are pinned by tests:
`tif` is always set explicitly (an empty TIF makes IBKR emit code 10349, which `ib_async` reads
as a cancellation — it marked live orders Cancelled on 2026-09-10 while they filled seconds
later); `outsideRth=False` is explicit and the caller is expected to refuse out-of-hours
submission *before* the adapter; and `working()` computes remaining quantity from executions
rather than from the status flag, because a half-filled order has half its size still on the
wire and a sizer that nets the submitted amount doubles up.

The second adapter, `quant_brain/brokers/projectx.py` (ProjectX / TopstepX), is complete up to
the order endpoint and then stops: `submit()` either records the translated body as a dry run
or raises `NotPermitted("live order submission is not implemented in this module")`. Its own
docstring gives the reason — an implementation present but gated is one edit from an accident,
whereas an implementation absent is not. It has no non-test importer (see §4).

---

## 4. What an order does NOT pass through today

This is the part of the system that is documented and not executed. Measured, not asserted:

```
$ python -c "import importlib.util,pathlib; \
p=pathlib.Path('tests/test_production_reachability.py'); \
s=importlib.util.spec_from_file_location('t',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); \
prod=m._reachable_from(m.PRODUCTION_ENTRY_POINTS); res=m._reachable_from(m._research_entry_points()); \
allm=m._all_quant_brain_modules(); print(len(allm),len(prod),len(res),len(allm-res))"
53 15 34 19
```

Of **53** modules in `quant_brain`, **15** are reachable from the six production entry points,
**34** from any non-test importer, and **19** from nothing outside the test suite. Those 19
total roughly **8,600** lines, about **45%** of the package — the line figure moves by tens
between runs because several files are being edited concurrently; the module counts do not.
(The docstring of `test_production_reachability.py` still says 17 modules / 8,023 lines /
44.3%. That count is stale, and the drift is in the worse direction, not the better one.)

The nineteen with no non-test caller:

```
quant_brain                            quant_brain.core.protection
quant_brain.__main__                   quant_brain.core.reconcile
quant_brain.brokers                    quant_brain.markets
quant_brain.brokers.projectx           quant_brain.markets.futures_cme.profiles
quant_brain.core.knowledge             quant_brain.research.analytics
quant_brain.core.lifecycle             quant_brain.research.promotion
quant_brain.core.multipletest          quant_brain.research.robustness
quant_brain.core.portfolio             quant_brain.venues
                                       quant_brain.venues.base
                                       quant_brain.venues.propfirm
                                       quant_brain.venues.registry
```

Seven of them are pinned as strict xfails by
`test_documented_safety_components_are_reachable`, so the day one of them acquires a caller the
suite fails and whoever wired it must delete the marker. `python -m pytest
tests/test_production_reachability.py -q` prints `........xxxxxxxx` — 8 passing invariants, 8
expected failures, none of them unexpectedly passing.

### The four that matter most for execution

**`quant_brain/core/protection.py` — bracket verification. No caller.** The module's rule is
`POSITION OPEN + STOP UNKNOWN -> UNPROTECTED -> the configured fail-safe, now`, and "unknown"
covers a stop that was submitted but not acknowledged, a stop the strategy believes it placed,
a stop for the wrong quantity and a stop on the wrong side. `verify()` takes what the **venue**
reports as working, not what the process sent. Neither runner places a protective order of any
kind: `grep -cn "StopOrder\|stopPrice\|StopLimit\|auxPrice"` returns **0** for
`scripts/intraday_trader.py`, `scripts/paper_trade.py` and `quant_brain/brokers/ibkr.py`, and
`build_ib_order` can only construct `MarketOrder`, `LimitOrder`, MOC and MOO. So by this module's own definition **every position the intraday sleeve opens is
UNPROTECTED for the whole session**, from the entry fill until the 15:38 ET flatten. The
sleeve's actual protection is a flat-by-the-bell rule plus a 2.5%-of-NAV daily loss limit
evaluated once per minute bar in the runner's own loop — a process-side control, not a resting
order at the exchange. If the runner dies, nothing at the venue closes the position.

**`quant_brain/core/reconcile.py` — compare-and-halt. No caller.** It takes two `Snapshot`s
(local and broker) and reports every difference in both directions — unexplained position,
phantom position, quantity mismatch, unexplained order, missing order, order mismatch, equity
mismatch, stale — and auto-corrects none of them, because "adopt the broker's view" sounds
reasonable until the broker's view includes a position a bug opened. On a discrepancy the
`Reconciler` trips the governor's `POSITION_UNRECONCILED` switch and nothing new opens.

What actually runs instead: `intraday_trader.py` carries its own `reconcile_book`
(`intraday_trader.py:146-182`) called from `startup_reconcile` on every start-up path. It
**adopts the account** silently-but-logged, over the sleeve's own universe only, and drops the
cost basis for an adopted position. It compares positions only — no working orders, no equity,
no staleness check — and it halts nothing. `paper_trade.py` reconciles nothing at all; it reads
`ib.positions(account_id)` and treats anything outside the intraday sleeve's universe as its
own responsibility. `scripts/reconcile_state.py` is a separate, human-run tool that repairs
`live/state/last_run.json` and explicitly "never places an order, never cancels one, and opens
the IB connection read-only" — it does not use `core/reconcile.py` either.

**`quant_brain/core/lifecycle.py` — `OrderMachine` and `SessionMachine`. No caller.** The
session machine forbids reaching `READY` unless thirteen `Readiness` preconditions are
simultaneously true (connection verified, account identified, market data healthy, clock
synchronised, session valid, venue rules loaded, local state reconciled, broker state
reconciled, no unexplained orders, no unexplained positions, risk budget computed, protection
verified, explicit enable). The order machine forbids `SUBMITTED` without `APPROVED` and
`PROTECTED` without `FILLED`, and raises on an illegal transition rather than logging it. The
only references to either class outside the module are in `tests/test_qb_lifecycle.py`. The
runners track order state with a dict of `ib_async` `Trade` objects and a `_seen` timestamp map
(`intraday_trader.py:409-440`).

**`quant_brain/core/portfolio.py` — cross-strategy exposure and correlated risk. No caller.**
It aggregates gross/net exposure per instrument, strategy and venue, combines dollars at risk
under a correlation matrix, refuses a matrix that is not positive semi-definite and refuses to
pad a missing instrument with zero correlation. Nothing computes portfolio-level risk across
the two sleeves today; they are kept apart by a disjoint universe convention
(`intraday_common.UNIVERSE` versus the champion's), not by a measurement.

### Also not on the path

- **Order idempotency.** `RoutedExecutor` accepts a `journal: IntentJournal` and, when one is
  present, refuses a duplicate `intent_id` and refuses any non-flatten intent that has no id at
  all. No caller passes one (`grep -rn "journal=" scripts/` returns nothing), and neither runner
  ever sets `intent_id`, so `_claim` returns `None` on the first line every time.
  `quant_brain.core.idempotency` counts as production-reachable only because
  `core/execution.py` imports it lazily inside that dead branch.
- **`quant_brain/venues/`** — the venue registry and the prop-firm venue base, 3 modules, no
  caller. `RoutedExecutor` is built by hand in both runners instead.
- **`quant_brain/core/multipletest.py`** — Holm/BH/BY, White's Reality Check, Hansen's SPA,
  deflated Sharpe, PBO. No caller. The futures funnel uses only
  `stats.bonferroni_threshold`; the equity ledger applies no correction at all.
- **`quant_brain/research/promotion.py`** — the `PromotionGate`. No caller. The real promotion
  path is `scripts/evaluate.py`; see `docs/BACKTESTING.md` §"The champion, honestly".

---

## 5. Simulated execution: what a fill costs

`quant_brain/markets/futures_cme/execution_sim.py` is the only place in the repository that
prices a futures fill. `docs/BACKTESTING.md` covers the spread measurement and the refusals;
this section covers the two functions on the cost path.

### `CostModel.for_contract(symbol)`

```python
c = inst.get(symbol)
if not c.commission_round_turn:
    raise ValueError(f"{symbol} has no commission recorded ...")
return cls(commission_per_side=c.commission_round_turn / 2, **kw)
```

There is **no default commission**. A contract with none recorded raises rather than
simulating at zero, because on a micro the commission can exceed the edge
(`test_a_contract_without_a_recorded_commission_is_refused`). The rate is read off the
contract's own metadata in `quant_brain/markets/futures_cme/instruments.py`, which keeps it
per-contract rather than per-notional — the thing an equity cost model gets structurally wrong.

### The commission constants changed today; this is what the file says now

`instruments.py:100-106` currently records Topstep's published all-in round-turn rates,
citing `help.topstep.com/en/articles/8284197` retrieved 2026-09-13:

| symbol | multiplier | tick | `commission_round_turn` | source |
|---|---|---|---|---|
| ES | 50.0 | 0.25 | **$3.78** | Topstep published |
| NQ | 20.0 | 0.25 | **$3.78** | Topstep published |
| MES | 5.0 | 0.25 | **$1.22** | Topstep published |
| MNQ | 2.0 | 0.25 | **$1.22** | Topstep published |
| YM, RTY, CL, GC | | | $4.00 | indicative default, **not** verified |
| MYM, M2K, MCL, MGC | | | $1.00 | indicative default, **not** verified |

These replaced round $4.00 / $1.00 placeholders. The comment records why the micro figure was
the one that mattered: $1.00 against $1.22 undercharged a micro round turn by 18% in the
flattering direction, on the contract a $50K account is permitted to trade.

The change landed while this document was being written. Four tests in
`tests/test_qb_execution_sim.py` pinned the old $2.00/side and failed for part of that time;
they now pin $1.89 and `MES/ES = 1.517`, and the file passes (44 tests). What did **not** get
updated is the arithmetic quoted in prose — see the two corrections under `round_turn_cost`
below. Treat the table above as the current state of the source, not as a settled interface.

### `ExecutionSimulator.round_turn_cost(quantity)`

```python
# execution_sim.py:337-338
spread = self.cost.spread_ticks * self.tick * self.multiplier
return 2 * self.cost.commission_per_side * quantity + spread * quantity
```

Two per-side commissions plus one tick of spread, per contract. `spread_ticks` defaults to 1.0
and is a measurement on ES rather than an assumption: `measure_spread_ticks` on
`data/futures/ES_quotes.parquet` reads a median of exactly 1.00 tick with 95.6% of RTH bars at
one tick. It is **charged in ticks, not basis points**, because the tick is fixed at 0.25 points
while its cost in bps fell 20% across six quarters purely because the index rose.

At the constants in the file today
(`py -3.11 -c "from quant_brain.markets.futures_cme import execution_sim as ex; ..."`):

| symbol | commission/side | one tick | `round_turn_cost(1)` |
|---|---|---|---|
| ES | $1.89 | $12.50 | **$16.28** |
| NQ | $1.89 | $5.00 | **$8.78** |
| MES | $0.61 | $1.25 | **$2.47** |
| MNQ | $0.61 | $0.50 | **$1.72** |

The docstring of `round_turn_cost` still quotes **0.480 bps** at ES's median price of 6,872.
That figure was computed at the superseded $4.00 commission; at $3.78 the same call returns
**0.4738 bps**. The paired test survives only because it asserts `approx(0.480, abs=0.02)`.
Separately, the by-quarter table inside the same docstring (0.411 / 0.389 / 0.366 / 0.363 /
0.337 / 0.327 bps) is **spread only** — 12.50/(6,888x50) is exactly 0.363 bps — so it is not on
the same basis as the 0.480 headline beside it. Two numbers in one docstring, two different
definitions.

### The refusals exist and the research drivers never reach them

`ExecutionSimulator.execute()` refuses `NO_PRICE`, `ZERO_QUANTITY`, `FLAT_BEFORE_CLOSE`,
`BLACKOUT`, `POSITION_LIMIT` and `LIMIT_NOT_MARKETABLE`, rounds against the trader, walks the
price linearly past the resting size, and refuses a passive limit rather than assuming it fills.
`grep -rn "\.execute(" scripts/` finds no caller. `scripts/futures_discover.py:242` and
`scripts/futures_topstep_baseline.py:108` construct an `ExecutionSimulator` **solely** to call
`round_turn_cost(contracts)` and charge that constant. A strategy scored by the funnel has paid
a measured spread and a recorded commission; it has never been refused an order.

---

## 6. The fill convention, and why it is the largest execution-realism issue

The futures funnel books

```python
# scripts/futures_discover.py:224
gross_path = np.cumsum(pos[:-1] * step[1:])        # step = diff(close) * multiplier * contracts
```

`pos[i] * (c[i+1] - c[i])`. The position is decided on bar `i`'s close and filled at **that same
close** — a price that has already printed. The signal reads no future bar, so this is not a
lookahead in the feature; the *execution* is the leak.

`tests/test_leakage_redteam.py` §D measures it. On a synthetic book with a two-tick half-spread
and a `pos[i] = -sign(c[i] - c[i-1])` mean-reversion rule run through the **real** evaluator:

```
legs                            4,760
subsidy                         +2.0003 ticks/leg   ($11,901.65)
gross as the engine books it            +$11,923.05
gross without the subsidy                   +$21.40   (0.18% of it)
```

99.8% of the reported gross is the fill convention, and the rule clears the cost gate (45.1%),
the Topstep gate (pass rate 1.0) and 5/5 walk-forward folds on the way through. The fixture
exaggerates on purpose so the test is deterministic; the audit measured the same mechanism on
real data at **+0.0551 ticks/leg over 68,388 ES legs**, worth +51% of gross on a mean-reversion
signal. The fixture first proves it reproduces the evaluator's own `gross` to 1e-9, which is
what makes the difference attributable to the fill and nothing else.

The engine offers no next-open convention to run against, so it now **reports** the subsidy
instead of refusing it (`futures_discover.py:292-294`):

```python
"fill_convention": "decision_bar_close",
"gross_next_open_fill": gross_next_open if priced_at_open else None,
"fill_subsidy": (gross - gross_next_open) if priced_at_open else None,
```

`gross_next_open_fill` re-prices the identical position path at bar `i+1`'s open and earns to
bar `i+2`'s open; both keys are `None` unless every session in the sample carries an `o` column.
This is reporting, not a gate: nothing rejects a hypothesis on its `fill_subsidy`.

**No row in the ledger carries these keys yet.** All 818 rows in
`research/experiments_futures.jsonl` predate the change — `python -c "import json; rows=[json.loads(l)
for l in open('research/experiments_futures.jsonl',encoding='utf-8') if l.strip()]; print(sum('fill_convention'
in (r.get('metrics') or {}) for r in rows))"` prints `0`. The last funnel run was
2026-09-13T02:49 (from the `created` field); the reporting landed afterwards. Reading the
subsidy off a real search requires re-running the funnel.

For contrast: the intraday equity harness (`scripts/intraday_backtest.py:390`) fills a pending
order at the **next** bar's open, holds it on the wire when the symbol prints no bar, and
matches the live runner's convention. LEAN, for the daily champion, decides on D's close and
fills at D+1's open. The futures funnel is the only one of the three that fills at the price it
decided on.

---

## 7. Not built

- **No live order has been sent since the disable.** There is no post-disable fill data of any
  kind, and no measurement of realised slippage against the model for futures at all.
- **No protective order.** Neither runner places a stop, a bracket or an OCO. `core/protection.py`
  has no caller; a killed process leaves an open position with nothing at the venue to close it.
- **No compare-and-halt reconciliation.** `core/reconcile.py` has no caller. The intraday
  runner's own version compares positions in one universe and adopts the account; the daily
  runner compares nothing.
- **No order or session state machine.** `core/lifecycle.py` has no caller. `READY` is not a
  state anything computes; the thirteen preconditions are not checked anywhere.
- **No portfolio-level risk.** `core/portfolio.py` has no caller. Sleeve isolation is a naming
  convention.
- **No idempotency.** No `intent_id` is ever minted; a restart mid-batch could resend.
- **No latency, partial-fill or queue model in the simulator.** A fill is whole and instant at
  the quote passed in.
- **No matching engine and no order book.** The repository's data floor is 30 seconds; a book
  built from bars would be interpolation with a confident face (`execution_sim.py` docstring).
- **No live-execution path for futures at all.** `brokers/projectx.py` raises on submit and has
  no caller. The only adapter that reaches a venue is IBKR, and it trades equities on a paper
  account.
- ~~No test on `paper_trade.py`'s transmission refusal~~ — added in `a6506fb`, extended in
  `f0bf65a`'s follow-up. The remaining limit is stated in the test's own docstring: it is a
  source-structure test and cannot prove the ABSENCE of an order path, only that the paths
  which exist are guarded.

## What this document does not claim

It does not claim the disable is airtight: §1 names the branch it does not cover. It does not
claim the risk chain is a meaningful constraint today — one limit is armed on one runner and
none on the other. It does not claim the cost model predicts realised slippage; it charges a
measured median ES spread and a published Topstep commission and refuses what it cannot price.
It does not claim the unwired modules are wrong, only that they do not run, and that a reader
planning against `docs/IMPLEMENTATION_REPORT.md` or `ARCHITECTURE.md` is planning against a
machine that does not exist.
