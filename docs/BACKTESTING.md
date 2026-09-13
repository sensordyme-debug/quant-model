# Backtesting: what a fill costs, what the account does to it, and what is not modelled

Status of this document: describes `quant_brain/markets/futures_cme/{execution_sim,twin,
paths}.py` and the two scripts that drive them, at commit `2a7367f` (2026-09-13). The equity
sleeves' harness (`scripts/intraday_backtest.py`, LEAN via `scripts/backtest.py`) uses a
different cost model and is out of scope here except where the contrast matters.

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | yes | `tests/test_qb_execution_sim.py`, `tests/test_qb_twin.py`, `tests/test_qb_paths.py`, `tests/test_futures_baseline.py`; the ES quote store agrees with the cost model to 1.000x at the same price |
| STRATEGY VALIDATED | **no** | the only strategy run end to end through this pipeline (`scripts/futures_topstep_baseline.py`) has HAC t = +0.23 and is liquidated on 100% of resampled paths |
| LIVE EXECUTION VALIDATED | **no** | nothing here touches a venue; the simulator is in-memory |
| PROFITABILITY DEMONSTRATED | **no** | |

---

## The execution simulator: `execution_sim.py`

`ExecutionSimulator(cost, symbol, flat_before_close=15, blackouts=(), max_position=None)`
turns an `OrderIntent` plus a `Quote` into a `Fill` or an `ExecutionResult` carrying a
`RejectReason`. It owns two things: the price a fill happens at, and whether it happens.
Position tracking stays in `core.execution.Position`.

### What is charged

| component | how | source |
|---|---|---|
| spread | a market order crosses to `Quote.touch(side)`: the ask for a buy, the bid for a sell | `fill_price` |
| commission | `CostModel.commission_per_side * quantity`. **No default**: `CostModel.for_contract(symbol)` raises unless `instruments.get(symbol).commission_round_turn` is recorded, because on a micro the commission can exceed the edge (`test_a_contract_without_a_recorded_commission_is_refused`) | `CostModel` |
| impact | linear in size beyond the resting quantity: `impact_ticks_per_book` ticks per multiple of `Quote.resting(side)`. Conservative for small orders, optimistic for very large ones; the docstring says so | `fill_price` |
| rounding | `round_to_tick` rounds **against** the trader (ceil for a buy, floor for a sell) | `round_to_tick` |
| slippage in the `Fill` | `(price - mid) * sign * multiplier * quantity`, so it is a cost on both sides | `execute` |

### What is refused

Every `RejectReason` is something a venue or a rulebook does in production:

| reason | when |
|---|---|
| `NO_PRICE` | `quote is None`. A price is not invented (`test_no_quote_means_no_fill_and_no_invented_price`) |
| `ZERO_QUANTITY` | `quantity <= 0` |
| `FLAT_BEFORE_CLOSE` | `minutes_to_close <= flat_before_close` and the intent is not a flatten |
| `BLACKOUT` | `now` inside a configured window; windows may wrap midnight |
| `POSITION_LIMIT` | the resulting absolute position would exceed `max_position` |
| `LIMIT_NOT_MARKETABLE` | a limit resting behind the touch. See below |

A `FLATTEN` intent bypasses the flatten cutoff, the blackout and the position cap, matching
`core.risk.RiskEngine` (`test_a_flatten_bypasses_every_gate_at_once`). It still needs a
quote (`test_a_flatten_still_needs_a_price`).

### Passive fills are refused, not modelled

`is_marketable` fills a limit only when the market has come to it. A limit resting behind the
touch is reported as not filled. The docstring calls this the single most consequential
modelling choice in the file: assuming a resting limit fills is how a backtest collects the
spread on every trade while ignoring that the fills it gets are the adverse ones. Estimating a
passive fill probability honestly needs queue position and trade prints, and the capability
audit measured 30 seconds as this repository's data floor. So a strategy that needs passive
fills cannot be evaluated here; the simulator says so instead of answering optimistically
(`test_a_passive_limit_behind_the_touch_is_refused_not_filled`).

### The cost is charged in ticks, and why

`round_turn_cost(quantity)` = `2 * commission_per_side * q + spread_ticks * tick * multiplier * q`.
`spread_ticks` defaults to 1.0 - the venue minimum, which was an assumption until the ES
quote store landed. `measure_spread_ticks(quotes, tick=)` now reads it off the tape: median,
mean, p90 and the share of bars at exactly one tick, with halt and rollover artefacts dropped
by the `low`/`high` bounds. The median is what feeds the model.

Measured on `data/futures/ES_quotes.parquet`, regular hours, 125,156 bars (commit
`63477e4`): median 1.00 tick, mean 1.04, p90 1.00, one tick on 95.6% of bars. At ES's median
price of 6,872 that is **0.480 bps** of round turn; the model charges 0.480 bps; F-2a's
independently measured realised cost was 0.488 bps. Three numbers within 2%
(`test_the_real_es_spread_confirms_the_one_tick_assumption`).

By quarter, from the `round_turn_cost` docstring and pinned by
`test_the_spread_is_stable_in_ticks_while_its_bps_cost_decays`:

```
quarter   spread      cost       median price
2025Q2    1.00 ticks  0.411 bps  6,086
2025Q3    1.00 ticks  0.389 bps  6,431
2025Q4    1.00 ticks  0.366 bps  6,830
2026Q1    1.00 ticks  0.363 bps  6,888
2026Q2    1.00 ticks  0.337 bps  7,412
2026Q3    1.00 ticks  0.327 bps  7,647
```

The spread is pinned at exactly one tick in all six quarters while its cost in basis points
falls 20%, entirely because the index rose. A tick is a fixed 0.25 points; a basis point is
not fixed at all. A hard-coded bps constant would silently cheapen execution every year the
market goes up. Charging in ticks is right at every price.

The corollary is that the bps figure is **price-dependent** and must only be compared against
a measurement at the same price. The same model reads 0.569 bps at 5,800 and 0.480 at 6,872.
Two readings of this number have already gone wrong by comparing across price levels - once
"17% conservative", once "overcharging by 56%" - and the test now asserts agreement at the
same price.

Overnight is wider: median still 1.00 tick, mean 1.13, p90 2.00, 87.7% of bars at one tick
(commit `63477e4`). The model does not switch spread by session; a caller trading overnight
should pass a measured `spread_ticks`.

`cost_per_dollar_exposure(price)` and `compare_granularity(symbol, price)` exist because a
micro is a tenth of the notional at a similar commission: MES costs several times more per
dollar of exposure than ES, and that is the price of the sizing granularity a $50K account
needs (`test_every_micro_is_more_expensive_per_dollar_than_its_parent`).

### How the drivers actually use it

Neither `scripts/futures_discover.py` nor `scripts/futures_topstep_baseline.py` calls
`execute()`. Both construct the simulator to read `round_turn_cost(contracts)` and charge that
constant per round turn on a close-to-close P&L with a one-bar position lag
(`futures_discover.py:92-108`). The fill-price walk, tick rounding, blackout, flatten-window
and position-limit refusals are exercised by `tests/test_qb_execution_sim.py` and by nothing
else. A strategy evaluated through the funnel has paid the measured spread and commission; it
has not been refused an order it should not have been able to place.

---

## The twin: `twin.py`

`PropFirmSimulator` in `propfirm.py` answers "does this account pass the evaluation?".
`TopstepTwin` answers the question that decides capital: what happens **after** passing.
Passing a Combine resets the account to $0 with the same $2,000 of room, five winning days of
$150 are needed before a dollar can be withdrawn, and a withdrawal lowers the balance while
the Maximum Loss Limit does not follow it down. The twin replays a strategy's sessions
through that whole lifecycle, rebuilding the account at each transition because Topstep does.

**Inputs.** `TwinDay(day, pnl, path=(), traded=True)`; `path` is the within-session equity
relative to the day's open. `TopstepTwin(size, *, profit_target=None, reading=DEFAULT_READING,
daily_loss_limit=None, consistency_route=False, payout_policy=IMMEDIATE, combine_fee=None,
max_combine_attempts=1, scaling=None, strict_path=True, allow_unverified_target=False)`.

**The strict-path refusal.** With `strict_path=True` (the default), `run()` raises on any
session without a path: Topstep tests the MLL intraday on unrealized P&L, so an absent path
silently skips the test and overstates survival. Passing `strict_path=False` is allowed and
the result records `path_supplied=False` so it can only be read as an upper bound
(`test_sessions_without_an_intraday_path_are_refused`,
`test_a_partial_path_still_trips_the_refusal`). `paths._extend` was corrected because
zero-filled padding days tripped exactly this guard, which is the guard doing its job.

**Order of tests inside a session** (`_step`). The MLL and the DLL are both equity levels
fixed for the session; which fires is decided by which level is higher, not by code order.
An armed DLL above the MLL removes intraday liquidation risk; a DLL below the MLL protects
nothing (`test_an_armed_daily_loss_limit_above_the_mll_prevents_liquidation`,
`test_a_daily_loss_limit_below_the_mll_protects_nothing`). A DLL hit ends the day at the
capped loss and the account survives (8284207).

**Payouts are a risk decision.** `PayoutPolicy(min_buffer_after, fraction, wait_days,
stop_after)`; `IMMEDIATE` takes everything at first eligibility, `NEVER` takes nothing.
`compare_policies` prices the choice per strategy;
`test_taking_less_can_earn_more_because_the_account_survives` shows the direction is not
obvious. `TopstepAccount.take_payout` pins the MLL at the lock level permanently
(`mll_reset_by_payout`, per 8284233).

**Fees.** `combine_fee` has no default. With none supplied, `TwinResult.net_capital` is
`None` and `TwinEvaluation.summary()` prints `E[gross] ... FEE UNKNOWN, not a profit figure`
(`test_the_evaluation_refuses_to_call_gross_a_profit`). Note that `topstep.COMBINE_COST` is
now DOC-tier ($49/$99/$199 standard) but the twin does **not** read it; a caller who wants a
net figure passes the fee explicitly.

**Outputs.** `TwinEvaluation` separates `p_pass_combine`, `p_funded`, `p_first_payout` and
`p_liquidated` on purpose: passing earns nothing, the first payout is the first dollar, and
the gap is the cost of the second barrier (`test_the_pass_rate_and_the_paid_rate_are_different_numbers`).

**Sizing helpers.** `risk_budget(account, fraction=0.25)` is anchored to `distance_to_mll`,
not balance: a $53,000 Combine with the floor at $50,000 has $3,000 of room, and sizing off
the balance would put on roughly eighteen times what the account can survive.
`max_contracts` clamps to the firm's ceiling and returns 0 rather than rounding up to 1.

**`u_shaped_path(adverse)`** is a synthetic intraday shape offered as a named, caveated
choice for sensitivity work, never as a default (`days_from_pnl` has no default `path_fn`).
`scripts/futures_topstep_baseline.py` uses real per-minute paths from the ES bars instead.

---

## Paths and Monte Carlo: `paths.py`

A backtest is one ordering of one set of sessions. Against an absorbing barrier the
distribution over orderings is the answer and the realised ordering is the least interesting
draw, because it is the one the strategy was selected on.

**Resamplers.** `moving_block(days, *, block, reps=1000, seed=0)` is the default; `block`
must be chosen and should be at least the length of a typical losing run.
`stationary_bootstrap(mean_block=)` is the Politis-Romano alternative. `iid()` is a
**sensitivity reference, not a conservative bound**: clustering raises the variance of
cumulative P&L, which hurts against the drawdown barrier and helps against a nearby profit
target; on an AR(0.9) series the block bootstrap passed the Combine 15 percentage points
*more* often than IID (module docstring; `clustering_premium` reports the signed gap without
asserting a sign). Intraday paths are rescaled with the resampled day rather than reused
verbatim (`_rebuild`).

**Scenarios** (`DEFAULT_SCENARIOS`) carry no probability, on purpose, so they cannot be
averaged into an expected value:

| scenario | what it assumes | `pin_prefix` |
|---|---|---|
| `losses +50%` | every losing day 1.5x worse | 0 |
| `cost +$25/day` | commission or spread wrong by $25 a session | 0 |
| `worst 10d first` | the worst ten-day stretch moved to day one | 10 |
| `-$1,000 shock on day 1` | a gap day before any buffer exists, sized to survive the day | 1 |
| `edge decays to zero` | the mean fades linearly, the noise stays | 0 |
| `intraday 1.5x deeper` | same closes, worse excursions | 0 |

`pin_prefix` exists because an ordering scenario is destroyed by a bootstrap: before it,
"worst 10 days first" measured as **safer** than the base case (93.2% against 91.2%), because
the resample shuffled the losing run back into the middle. `resample_with_prefix` holds the
prefix and bootstraps the tail (`test_the_prefix_pin_changes_the_answer_on_an_ordering_scenario`).

**`break_even_shock`** bisects for the per-session cost increase that drags the payout rate
to a target - a number an owner can weigh against experience. **`size_sweep`** shows the
interior optimum Sharpe cannot see: too small never reaches the target before the fee runs
out, too large breaches (`test_the_size_sweep_optimum_is_interior_not_at_an_end`).

---

## The one end-to-end run, and what it says

`scripts/futures_topstep_baseline.py` pushes 447,600 one-minute ES bars (125,156 in RTH,
325 usable sessions) through one pre-registered strategy, the measured costs, real intraday
paths, the twin, the resamplers and the stress scenarios. The artefact is
`research/futures_topstep_baseline.json`:

```
sessions 325   mean/session $2.39   HAC t +0.23 vs 1.96 at 1 trial   -> verdict FAIL
twin        p_pass_combine 0.01  p_first_payout 0.00  p_liquidated 1.00  median days to pass 58
stress      every scenario: pass 0.00, paid 0.00, liquidated 1.00
size sweep  pass 0.00 at 0.25x-0.75x, 0.01 at 1.0x, 0.05 at 1.5x, 0.06 at 2.0x; liquidated 1.00 at every size
clustering  block pass 0.01, iid pass 0.02
```

The script's own docstring quotes slightly different numbers (2.5% / 0.2% / 2.0% -> 6.0%)
from an earlier run; the JSON on disk is the record. The reading is the same: with no drift
the only route to a profit target is variance, so bigger size raises the pass rate while
liquidation stays at 100%. A pipeline that said anything more flattering about this strategy
would be broken. This run is a statement about the pipeline, not about the market: 325
sessions is about a sixth of what A-4 measured as necessary to resolve an intraday edge.

---

## Data the simulator stands on

- `instruments.DATA_VERIFIED = {ES, MES, NQ, MNQ}`: twelve contracts are specified across
  four tick grids; four have stored, validated history (`BLOCKERS.md` OWNER-3: 395 sessions
  for ES/NQ, 317 for MES/MNQ, 2025-06 to 2026-09).
- `markets/futures_cme/dataquality.check_futures_frame` reports roll gaps and same-day
  contract overlap as WARN and refuses impossible returns, stale runs and crossed books;
  `require_usable` is called by both drivers before any bar is used.
- A quote store exists for **ES only**. MES, NQ and MNQ quotes were not fetched
  (`docs/ARCHITECTURE_AUDIT.md`, "Dangerous assumptions"), so the one-tick measurement is an
  ES fact applied to the micros by assumption.

---

## Not modelled, stated plainly

- **No order book.** There is no matching engine and no book reconstruction; the repository
  has no tick data (30-second floor), and a book built from bars would be interpolation with
  a confident face (module docstring).
- **Passive fills are refused**, not estimated. No queue position, no fill probability.
- **No latency model.** A fill happens at the quote passed in; there is no delay between
  intent and fill, no stale-quote detection, no cancel/replace timing.
- **No partial fills over time.** A fill is whole; impact is a linear price walk, not a
  sequence of prints.
- **One spread for all sessions.** `spread_ticks` is a single number; the measured overnight
  widening is not applied automatically.
- **Impact is linear in size** beyond the resting quantity, which is optimistic for orders
  that matter to the book.
- **The drivers do not route through `execute()`.** The funnel charges the round-turn constant
  and never exercises the refusals.
- **No LEAN link for futures.** `scripts/backtest.py` runs LEAN for the equity algorithms;
  the futures pipeline is the parquet store plus these modules.
- **The equity sleeves use a different cost model**: `scripts/intraday_common.py` charges
  `SLIPPAGE_BPS = 1.5` plus IBKR commission in basis points, with a measured breakeven of
  2.62-2.64 bps (A-5). Nothing in this document applies to that harness.

## Not implemented

- A fill model for resting orders, a latency model, or an order book.
- Automatic use of `topstep.COMBINE_COST` by the twin; the fee must be passed.
- Spread measurement for MES, NQ, MNQ, or for the overnight session as a separate parameter.
- Any path from a funnel survivor to a twin evaluation beyond the 150-rep gate inside
  `futures_discover.py`; nothing has survived to need one.

## What this document does not claim

It does not claim the simulator predicts realised slippage; it charges a measured median
spread and a recorded commission and refuses what it cannot price. It does not claim the twin's
pass rates are forecasts; they are distributions over resampled orderings of one strategy's
own sessions under one version of the rulebook. It does not claim the baseline strategy has
any edge; the point of that run is that the pipeline reports none. It does not claim the
one-tick ES spread holds for the micros or overnight; it was measured on ES in regular hours.
