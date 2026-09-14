# Backtesting: the three harnesses, what a fill costs, and what none of it establishes

Status of this document: describes the working tree at commit `4fbc22e` (2026-09-13) **plus
uncommitted changes**. `scripts/futures_discover.py`,
`quant_brain/markets/futures_cme/{instruments,features,dataquality,propfirm,topstep}.py`,
`quant_brain/research/search.py` and several test files are modified and not yet committed
(`git status --porcelain`); a checkout of `4fbc22e` will not match. The order path and the
cost model as an *execution* device are in `docs/EXECUTION.md`; this document is about what a
backtest here measures and what it does not.

| claim | status | evidence |
|---|---|---|
| ENGINE VALIDATED | partly | `tests/test_qb_twin.py`, `test_qb_paths.py`, `test_futures_baseline.py`, `test_futures_funnel_costs.py` (21 pass), `test_leakage_redteam.py` (29 pass, 2 xfail), `test_qb_execution_sim.py` (44 pass). Note that the futures commission constants changed on 2026-09-13 while this was written |
| STRATEGY VALIDATED | **no** | the only strategy run end to end through the futures pipeline (`scripts/futures_topstep_baseline.py`) has HAC t = +0.23 and is liquidated on 100% of resampled paths. The equity champion was promoted on a criterion with no significance test |
| LIVE EXECUTION VALIDATED | **no** | nothing here touches a venue; order transmission is hard-disabled in both runners (`docs/EXECUTION.md`) |
| PROFITABILITY DEMONSTRATED | **no** | |
| THE LEDGERS REFLECT THE CURRENT CODE | **no** | every one of the 818 rows in `research/experiments_futures.jsonl` predates the round-turn fix, the leakage gate and the fill-convention reporting |

---

## 1. There are three backtest harnesses, and they share almost nothing

| harness | driver | instrument | decides on | fills at | costs charged |
|---|---|---|---|---|---|
| LEAN equity | `scripts/backtest.py` -> `algorithms/<name>/main.py` | daily US equities/ETFs | close of D | open of D+1 (see below) | IB fee model. **No spread, no financing** by default |
| Intraday minute | `scripts/intraday_backtest.py` -> `algorithms/intraday/<name>/signal.py` | 1-minute US equities | close of bar t | open of bar t+1, carried on the wire if the symbol does not print | `SLIPPAGE_BPS = 1.5` + IBKR commission (`scripts/intraday_common.py:65`) |
| Futures funnel | `scripts/futures_discover.py` | 1-minute CME equity-index futures | close of bar i | **the same close** | one `round_turn_cost` constant per round turn |

They do not share a cost model, a fill convention, a ledger schema or a promotion gate. A
number from one is not comparable with a number from another, and no code in the repository
enforces that.

The LEAN fill convention is worth stating precisely, because the engine has two branches
(`../Lean/Algorithm/QCAlgorithm.Trading.cs:245-280`). A market order submitted while the
exchange is **closed** is converted to `MarketOnOpen` and fills at the next open. A market
order submitted while the exchange is **open**, in backtest, on a daily-resolution-only
security, is converted to `MarketOnClose` — today's close — or to `MarketOnOpen` if it is
already inside the MOC submission buffer. `algorithms/s1_momo/main.py:328-340` takes the first
branch on purpose and records why: rebalancing is driven by the daily SPY bar in `on_data`, at
which point "a daily security's local time is its last bar stamp, so the exchange looks shut",
and the algorithm's comment notes that a 15:45 scheduled variant placed 9,095 orders and filled
none, while a 09:00 variant stacked two full targets and reached 12.7x gross against a 1.0 cap.
So the champion decides on D's close and fills at D+1's open. **The deployed runner does not**:
`scripts/paper_trade.py` runs at 15:45 ET on D+1 and fills near that session's close, one full
session later than the backtest. That gap is priced below.

`CLAUDE.md` says "Every backtest goes through `scripts/backtest.py` so it lands in
`research/experiments.jsonl`." That is not what happens. **44 scripts under `scripts/` append
to that file directly**, with at least two incompatible row schemas:

```
$ python -c "import pathlib,re; print(sum(1 for p in sorted(pathlib.Path('scripts').rglob('*.py')) \
  if '__pycache__' not in p.parts and 'experiments.jsonl' in p.read_text(encoding='utf-8',errors='replace') \
  and re.search(r'(EXPERIMENTS|LEDGER|ledger)\s*\.\s*open\(\s*[\"\']a', p.read_text(encoding='utf-8',errors='replace'))))"
44
```

`scripts/backtest.py` writes `{ts, algorithm, class, tag, commit, run_dir, env, stats,
provenance, env_key, reproducible}`. The sweeps and the intraday harness write
`{algorithm, timestamp, start, end, params, stats, tag}`. Of the 1,653 rows, 169 are `s1_momo`
LEAN runs; the rest are `intraday/*`, `daily/s*`, `options/odte_*` and ML rows written by other
scripts.

### No file under `algorithms/` imports `quant_brain`

```
$ grep -rn "quant_brain" algorithms/ | wc -l
0
```

Seventeen Python files, zero mentions. The strategy code that the LEAN champion and the
intraday sleeve actually run has no dependency on the risk engine, the execution boundary, the
instrument metadata, the validation module or the promotion gate. Whatever `quant_brain`
guarantees, it does not guarantee anything about `algorithms/`.

---

## 2. The futures funnel: `scripts/futures_discover.py`

326 ES or NQ sessions (261 for MES/MNQ), 136 threshold hypotheses per family, five gates.
Sessions come from `session_frames`, which admits a day only if it holds exactly
`SESSION_BARS = 376` start-stamped minutes from 09:30 to 15:45 ET inclusive, opening on the
first and closing on the last. There is no CME calendar in this repository, so a legitimate
early close and a truncated outage are both dropped — measured cost, 3 of 326 ES sessions.

### Round-turn accounting: `session_accounting` (`futures_discover.py:189-236`)

The old count was `int(abs(diff(pos, prepend=0)).sum() / 2)`. It supplies the opening leg and
never the closing one, then truncates the odd total downwards. A session starts flat and must
end flat — the funnel trades a 09:30-15:45 window and Topstep requires a flat book at 3:10 PM
CT — so the exit is always traded and was never charged. **A rule that is simply long all
session reported zero round turns and paid zero cost, then failed the 40-trade floor as "not a
strategy" before the Topstep and walk-forward gates ever ran.**

Verified against the ledger, read-only:

```
$ python -c "import json; rows=[json.loads(l) for l in open('research/experiments_futures.jsonl',encoding='utf-8') if l.strip()]; \
m=[r.get('metrics') or {} for r in rows]; s=[x for x in m if 'trades' in x]; \
print(len(rows), len(s), sum(1 for x in s if x['trades']==0 and x['costs']==0.0))"
818 816 624
```

818 lines; **816 scored hypotheses; 624 of them (76.5%) recorded `trades: 0` and
`costs: 0.0`**. It is exactly 104 of 136 in every one of the six threshold families, including
the three `.v2` families — the defect is a property of the grid, not of one run.

The fix appends the flatten:

```python
# futures_discover.py:228
legs = np.abs(np.diff(pos, prepend=0.0, append=0.0))
turns = float(legs.sum()) / 2.0
```

Checked directly (`python -c "from futures_discover import session_accounting; ..."`):
always-long over 10 bars -> **1.0** round turn (was 0); one flip -> **2.0** (was 1); flat -> 0.
`tests/test_futures_funnel_costs.py` passes (21 collected).

### When the cost lands

Cost used to be spread across the session with `linspace(0, cost, n)`. The terminal P&L is
identical either way, but this path is what `TwinDay(path=...)` hands the Topstep twin, and the
trailing maximum loss limit tracks **peak equity intraday**. Cost not yet charged is equity the
twin believes the account has. Each leg is now paid at the bar it trades:

```python
# futures_discover.py:232-236
paid = np.cumsum(legs) * (round_turn_cost / 2.0)     # half a round turn per leg
incurred = paid[1:n].copy()
incurred[-1] = paid[-1]                               # the closing flatten settles on the last point
return gross_path - incurred, turns, float(gross_path[-1])
```

### The one-bar lag

`gross_path = np.cumsum(pos[:-1] * step[1:])` — the position decided on bar `i` earns bar
`i+1`'s move. That is what separates a backtest from a look-ahead and it is unchanged.

### The fill convention is the largest realism problem, and it is reported not fixed

The lag is applied to the *return*, not to the *fill*: the position is decided on bar `i`'s
close and booked at that same close, a price that has already printed. `docs/EXECUTION.md` §6
has the full measurement. In short: the red team measured a mean-reversion rule whose entire
edge — **$11,901.65 of an $11,923.05 gross, 99.8%** — was the convention, at **+2.0003 ticks
per leg over 4,760 legs**, and it cleared the cost gate, the Topstep gate and 5/5 walk-forward
folds on the way through. The audit measured the same mechanism on real ES data at **+0.0551
ticks/leg over 68,388 legs**, worth +51% of gross on a mean-reversion signal.

The result dict now names it (`futures_discover.py:292-294`): `fill_convention:
"decision_bar_close"`, `gross_next_open_fill` (the same position path re-priced at bar i+1's
open) and `fill_subsidy` (the difference). Nothing rejects a hypothesis on the subsidy — it is
a number a reader can subtract, not a gate. And **no ledger row carries any of those keys**:
all 818 rows predate the change (last funnel run 2026-09-13T02:49 by the `created` field;
`futures_discover.py` was last edited at 23:08 the same day). Reading a real subsidy requires
re-running the funnel.

### The five gates, in the order they run

Order is set in `quant_brain/research/search.py::search`; the thresholds are module constants
at the top of `futures_discover.py` (lines 56-86 at the time of writing — that file is being
edited concurrently, so prefer the constant names to the line numbers).

Three cheap filters run before gate 0, and all three reject rather than warn: a
duplicate-fingerprint check, `Limits.min_sessions = 100`, and a degeneracy check added on
2026-09-13 (below).

| # | gate | rejects when | where |
|---|---|---|---|
| 0 | **leakage** | `abs(gross) / ceiling > MAX_CEILING_SHARE = 0.20`, where `ceiling = sum abs(diff(close)) * multiplier * contracts` is what a perfect one-bar-ahead oracle earns | `evaluator.run`, `leakage_ok` |
| 1 | **statistics** | `abs(t_hac) <= bonferroni_threshold(n_trials_in_family)`. The count includes this experiment and every earlier trial in the family, so at 136 trials the bar is **3.562**, not 1.96 | `research/registry.py::Ledger.verdict`, called from `search.py:196` |
| 2 | **cost** | fewer than `MIN_TRADES = 40` round turns, or `costs / abs(gross) > MAX_COST_SHARE = 0.60` | `evaluator.run`, `cost_ok` |
| 3 | **Topstep survival** | `p_pass_combine < MIN_PASS_RATE = 0.10` over a 150-rep moving-block resample (block 10) through `TopstepTwin(50_000, profit_target=3_000, payout fraction 0.5)` | `evaluator.run`, `topstep_ok` |
| 4 | **walk-forward** | fewer than `MIN_WF_FOLDS = 3` of 5 folds have a positive mean | `evaluator.run`, `walkforward_ok` |


Four things about that table are true and uncomfortable.

**Gate 0 is one-sided and it says so.** A high ceiling share is strong evidence of a leak; a low
share is evidence of nothing, because a rule in the market a tenth of the session has a tenth
of the opportunity. It compares `abs(gross)`, because a perfectly *wrong* oracle is the same bug
with the sign flipped and the funnel has already produced 40 PASS verdicts with negative t (the
worst at -11.92). The 0.20 level is read off a measured gap in `tests/test_leakage_redteam.py`,
not tuned: the weakest planted cheat measured 44.90% of the ceiling, the best clean causal rule
3.97%, and 0.20 sits in the middle of that band on a log scale.

**Gate 1's multiplicity correction is real for the futures funnel and absent everywhere else.**
`Ledger.verdict` has no `n_trials` parameter by design. But `research/experiments.jsonl` — the
equity ledger, 1,653 rows — applies no correction at all, and `Ledger.all()` parses **0** of its
rows because the two schemas share no keys
(`tests/test_production_reachability.py::test_the_multiplicity_ledger_can_read_the_main_experiment_log`,
a strict xfail). `quant_brain/core/multipletest.py` — Holm, BH, BY, Reality Check, SPA, deflated
Sharpe, PBO — has no caller of any kind.

**Gate 4 is not walk-forward.** It is `np.array_split(pnl, 5)` with at least three chunks
positive: a five-block sign test on the same in-sample P&L, with no refit, no purge and no
embargo. `quant_brain/core/validation.purged_walk_forward` exists and is not called by it. The
funnel's own output table, the ledger notes and this gate's name all say "walk-forward".

**There is no holdout.** All 326 sessions feed all five gates. `Stage.VALIDATION` means
"eligible for the holdout"; no holdout has ever been carved and `Holdout.spend()` has never run.
`quant_brain.core.validation` became research-reachable on 2026-09-13 only because
`build_features` now raises `LeakageError` when the feature library fails its own causality
audit — a narrow foothold, and reachability is not use.

### The degeneracy filter, and what it says about the grid

`threshold_hypotheses` emits `np.where(x >= thr, 1, -1) * direction`, so every rule in the grid
is always in the market, and a threshold the feature never crosses collapses the whole
hypothesis to a constant. A candidate whose position takes one distinct value across every bar
of every session is now returned with `degenerate: True` and a reason, before gate 0, and
`search.py:186-191` counts it on its own line of the attrition table.

The comment recording the measurement says: on the real ES store, **104 of 136 cells are
constants**, and the 136 cells produce only **32 distinct position paths**, two of which (52
cells each) are plain always-long and always-short. That is the same 104 per family that showed
up as `trades: 0` in the ledger. It is the difference between reporting "817 hypotheses, 0
survivors" and reporting "of 817 candidates, three quarters were buy-and-hold with a sign".
Pinned by `tests/test_futures_funnel_costs.py::test_a_constant_position_is_reported_as_degenerate_not_scored`
and its control.

### Causality is now audited before the search, and that is new

`build_features` (`futures_discover.py:156-186`) runs `fe.audit_causality` on three probe
sessions — first, middle, last — and refuses to search if any feature moves when the future of
an input column is perturbed. The measured consequence, from `tests/test_leakage_redteam.py`: a
feature holding the leaked target, and a feature built on `rolling(31, center=True)`, are both
caught by that guard and were both admitted before it existed. The one hypothesis that ever
survived this funnel (t = +6.25) was produced by a lookahead in `_opening_range_pos`; it was
caught, fixed, and retracted **while keeping its trial in the multiplicity denominator**.

---

## 3. The execution simulator: `execution_sim.py`

`ExecutionSimulator(cost, symbol, flat_before_close=15, blackouts=(), max_position=None)` turns
an `OrderIntent` plus a `Quote` into a `Fill` or an `ExecutionResult` carrying a
`RejectReason`. It owns the price a fill happens at and whether it happens; position tracking
stays in `core.execution.Position`.

### What is charged

| component | how | source |
|---|---|---|
| spread | a market order crosses to `Quote.touch(side)` | `fill_price` |
| commission | `CostModel.commission_per_side * quantity`. **No default**; `for_contract` raises unless the instrument has a recorded rate | `CostModel` |
| impact | linear beyond the resting quantity: `impact_ticks_per_book` ticks per multiple of `Quote.resting(side)` | `fill_price` |
| rounding | `round_to_tick` rounds **against** the trader | `round_to_tick` |
| slippage in the `Fill` | `(price - mid) * sign * multiplier * quantity`, a cost on both sides | `execute` |

### What is refused

`NO_PRICE` (a price is not invented), `ZERO_QUANTITY`, `FLAT_BEFORE_CLOSE`, `BLACKOUT`
(windows may wrap midnight), `POSITION_LIMIT`, `LIMIT_NOT_MARKETABLE`. A `FLATTEN` bypasses the
flatten cutoff, the blackout and the position cap, matching `core.risk.RiskEngine`, and still
needs a quote.

**Passive fills are refused, not modelled.** A limit resting behind the touch is reported as
not filled. The docstring calls this the single most consequential modelling choice in the
file: assuming a resting limit fills is how a backtest collects the spread on every trade while
ignoring that the fills it gets are the adverse ones. Estimating a passive fill probability
honestly needs queue position and trade prints; this repository's data floor is 30 seconds. So
a strategy that needs passive fills cannot be evaluated here, and the simulator says so.

### The round turn, in ticks, and the commission numbers as they stand today

```python
# execution_sim.py:337-338
spread = self.cost.spread_ticks * self.tick * self.multiplier
return 2 * self.cost.commission_per_side * quantity + spread * quantity
```

`spread_ticks` defaults to 1.0 — the venue minimum, which was an assumption until the ES quote
store landed. `measure_spread_ticks(quotes, tick=)` now reads it off the tape and the median is
what feeds the model. Measured on `data/futures/ES_quotes.parquet`, regular hours: **median
1.00 tick, mean 1.04, p90 1.00, one tick on 95.6% of bars**
(`test_the_real_es_spread_confirms_the_one_tick_assumption`). Overnight is wider — median still
1.00, mean 1.13, p90 2.00, 87.7% at one tick — and the model does **not** switch spread by
session.

`instruments.py:100-106` now carries Topstep's published all-in round-turn commissions
(help.topstep.com/en/articles/8284197, retrieved 2026-09-13): **ES $3.78, NQ $3.78, MES $1.22,
MNQ $1.22**, replacing round $4.00 / $1.00 placeholders. YM, RTY, CL, GC and their micros keep
the unverified $4.00 / $1.00 default and are labelled as such. The resulting round turns:

| symbol | commission/side | one tick | `round_turn_cost(1)` |
|---|---|---|---|
| ES | $1.89 | $12.50 | **$16.28** |
| NQ | $1.89 | $5.00 | **$8.78** |
| MES | $0.61 | $1.25 | **$2.47** |
| MNQ | $0.61 | $0.50 | **$1.72** |

**Two corrections to what the source still says.** The `round_turn_cost` docstring quotes
0.480 bps at ES's median price of 6,872; at $3.78 the same call returns **0.4738 bps** (that
figure was computed at $4.00). And the by-quarter table in the same docstring — 0.411 / 0.389 /
0.366 / 0.363 / 0.337 / 0.327 bps — is **spread only**: 12.50/(6,888x50) is exactly 0.363 bps.
Two numbers in one docstring on two different bases. The tests were updated to the new
constants while this document was being written (`test_the_round_turn_is_commission_plus_one_tick`
now pins $1.89/side and `MES/ES = 1.517`); the prose inside `round_turn_cost` was not.

What survives all of that is the reason the cost is charged in **ticks, not basis points**: the
spread is pinned at exactly one tick in all six measured quarters while its cost in bps falls
20%, entirely because the index rose. A tick is a fixed 0.25 points; a basis point is not fixed
at all. The bps figure is therefore price-dependent and must only be compared against a
measurement at the same price — two readings of this number have already gone wrong by
comparing across price levels, once "17% conservative", once "overcharging by 56%".

`cost_per_dollar_exposure(price)` and `compare_granularity(symbol, price)` exist because a
micro is a tenth of the notional at a similar commission: MES costs several times more per
dollar of exposure than ES, and that is the price of the sizing granularity a $50K account
needs.

### The drivers do not route through `execute()`

`grep -rn "\.execute(" scripts/` finds no caller. `futures_discover.py:242` and
`futures_topstep_baseline.py:108` construct an `ExecutionSimulator` solely to read
`round_turn_cost(contracts)` and charge that constant per round turn. The fill-price walk, tick
rounding, blackout, flatten-window and position-limit refusals are exercised by
`tests/test_qb_execution_sim.py` and by nothing else. A strategy evaluated through the funnel
has paid a measured spread and a published commission; it has never been refused an order.

---

## 4. The twin: `twin.py`

`PropFirmSimulator` in `propfirm.py` answers "does this account pass the evaluation?".
`TopstepTwin` answers the question that decides capital: what happens **after** passing.
Passing a Combine resets the account to $0 with the same $2,000 of room, five winning days of
$150 are needed before a dollar can be withdrawn, and a withdrawal lowers the balance while the
Maximum Loss Limit does not follow it down. The twin replays a strategy's sessions through that
whole lifecycle, rebuilding the account at each transition because Topstep does.

**Inputs.** `TwinDay(day, pnl, path=(), traded=True)`; `path` is the within-session equity
relative to the day's open. `TopstepTwin(size, *, profit_target=None, reading=DEFAULT_READING,
daily_loss_limit=None, consistency_route=False, payout_policy=IMMEDIATE, combine_fee=None,
max_combine_attempts=1, scaling=None, strict_path=True, allow_unverified_target=False)`.

**The strict-path refusal.** With `strict_path=True` (the default), `run()` raises on any
session without a path: Topstep tests the MLL intraday on unrealized P&L, so an absent path
silently skips the test and overstates survival. `strict_path=False` is allowed and the result
records `path_supplied=False` so it can only be read as an upper bound.

**Order of tests inside a session** (`_step`). The MLL and the DLL are both equity levels fixed
for the session; which fires is decided by which level is higher, not by code order. An armed
DLL above the MLL removes intraday liquidation risk; a DLL below the MLL protects nothing.

**Payouts are a risk decision.** `PayoutPolicy(min_buffer_after, fraction, wait_days,
stop_after)`; `compare_policies` prices the choice per strategy, and
`test_taking_less_can_earn_more_because_the_account_survives` shows the direction is not
obvious. `TopstepAccount.take_payout` pins the MLL at the lock level permanently.

**Fees.** `combine_fee` has no default. With none supplied, `TwinResult.net_capital` is `None`
and `TwinEvaluation.summary()` prints `E[gross] ... FEE UNKNOWN, not a profit figure`.
`topstep.COMBINE_COST` is DOC-tier ($49/$99/$199 standard) and the twin does **not** read it.

**Outputs.** `TwinEvaluation` separates `p_pass_combine`, `p_funded`, `p_first_payout` and
`p_liquidated` on purpose: passing earns nothing, the first payout is the first dollar, and the
gap is the cost of the second barrier.

**Sizing helpers.** `risk_budget(account, fraction=0.25)` is anchored to `distance_to_mll`, not
balance: a $53,000 Combine with the floor at $50,000 has $3,000 of room, and sizing off the
balance would put on roughly eighteen times what the account can survive. `max_contracts`
clamps to the firm's ceiling and returns 0 rather than rounding up to 1.

`u_shaped_path(adverse)` is a synthetic intraday shape offered as a named, caveated choice for
sensitivity work, never as a default (`days_from_pnl` has no default `path_fn`).

---

## 5. Paths and Monte Carlo: `paths.py`

A backtest is one ordering of one set of sessions. Against an absorbing barrier the
distribution over orderings is the answer and the realised ordering is the least interesting
draw, because it is the one the strategy was selected on.

**Resamplers.** `moving_block(days, *, block, reps=1000, seed=0)` is the default; `block` must
be chosen and should be at least the length of a typical losing run.
`stationary_bootstrap(mean_block=)` is the Politis-Romano alternative. `iid()` is a
**sensitivity reference, not a conservative bound**: clustering raises the variance of
cumulative P&L, which hurts against the drawdown barrier and helps against a nearby profit
target; on an AR(0.9) series the block bootstrap passed the Combine 15 percentage points *more*
often than IID. Intraday paths are rescaled with the resampled day rather than reused verbatim.

**Scenarios** (`DEFAULT_SCENARIOS`) carry no probability, on purpose, so they cannot be averaged
into an expected value:

| scenario | what it assumes | `pin_prefix` |
|---|---|---|
| `losses +50%` | every losing day 1.5x worse | 0 |
| `cost +$25/day` | commission or spread wrong by $25 a session | 0 |
| `worst 10d first` | the worst ten-day stretch moved to day one | 10 |
| `-$1,000 shock on day 1` | a gap day before any buffer exists | 1 |
| `edge decays to zero` | the mean fades linearly, the noise stays | 0 |
| `intraday 1.5x deeper` | same closes, worse excursions | 0 |

`pin_prefix` exists because an ordering scenario is destroyed by a bootstrap: before it, "worst
10 days first" measured as **safer** than the base case (93.2% against 91.2%), because the
resample shuffled the losing run back into the middle.

**`break_even_shock`** bisects for the per-session cost increase that drags the payout rate to a
target. **`size_sweep`** shows the interior optimum Sharpe cannot see: too small never reaches
the target before the fee runs out, too large breaches.

---

## 6. The one end-to-end futures run, and what it says

`scripts/futures_topstep_baseline.py` pushes 447,600 one-minute ES bars (325 usable sessions)
through one pre-registered strategy — direction from the first 30 minutes, held to 15:45, sized
in MES — the measured costs, real intraday paths, the twin, the resamplers and the stress
scenarios. The artefact is `research/futures_topstep_baseline.json`, read back here directly:

```
sessions 325   mean/session $2.39   total $777.50   win rate 52.6%
HAC t +0.227 vs 1.96 at 1 trial                              -> verdict FAIL
twin        p_pass_combine 0.01  p_first_payout 0.00  p_liquidated 1.00  median days to pass 58
stress      every scenario: pass 0.00, paid 0.00, liquidated 1.00
```

The script's own docstring quotes different numbers from an earlier run; the JSON on disk is
the record. The reading is the same: with no drift the only route to a profit target is
variance, so bigger size raises the pass rate while liquidation stays at 100%. A pipeline that
said anything more flattering about this strategy would be broken.

Two caveats. This run is a statement about the pipeline, not about the market: 325 sessions is
about a sixth of what A-4 measured as necessary to resolve an intraday edge. And the JSON was
written 2026-09-13T00:39, before the commission change, so its per-session cost is the old MES
$2.25 rather than $2.47 — one round turn per session, so the strategy's mean would fall by
about $0.22 a day. `session_accounting`'s round-turn bug never touched it: this strategy enters
once and exits once, and the baseline charges the full round turn at the first bar of the path
(`futures_topstep_baseline.py:128`), which is the conservative direction for a trailing MLL.

---

## 7. The champion, honestly

`research/champion.json`, read directly:

```
algorithm  s1_momo   class S1MomentumRotationAlgorithm   commit d41aefe
promoted   2026-09-11T15:09:32+00:00   run_dir results\s1_momo\20260911T145705Z
stats      Compounding Annual Return 24.403%   Sharpe 0.994   Drawdown 23.700%
           Total Orders 5128   Total Fees $27,199.76   Probabilistic Sharpe 33.210%
criteria   min_trades 30, must_beat ["Compounding Annual Return"],
           sharpe_tolerance 0.03, drawdown_tolerance_points 1.0, max_drawdown_limit "35%"
```

### What the promotion criterion is

`must_beat` is a one-element list: **Compounding Annual Return**. There is no significance
test, no multiplicity correction, and no out-of-sample requirement. Sharpe and drawdown appear
only as *tolerances* — a candidate may be up to 0.03 Sharpe below the champion and up to 1.0
drawdown point worse — so they can constrain a promotion but never cause one. The `note` in
`criteria` records this as an owner decision on 2026-09-09: "return-first".

`scripts/evaluate.py` implements exactly that (`verdict()`, lines 312-334). The gate that does
exist and is worth crediting: since S-18 a candidate is compared against the champion's column
**at the same cost model** (`champion_stats`, `spread_bps`), a run recorded with
`S1_FINANCING=on` is refused as not comparable, a run from a different Python/pandas stack is
refused (`env_note`), and `stale_note` refuses every comparison when no cost column carries the
champion's own `run_dir`. Those are real and they were each added after a measured defect.
`quant_brain/research/promotion.py`, the `PromotionGate` the architecture documents describe,
has no caller.

### The headline stats block is the zero-cost column

Every one of the seven metrics in `stats_by_spread["0.0"]` matches `stats` exactly, and the two
name the same `run_dir` (`20260911T145705Z`) — same 5,128 orders, same 24.403%, same 0.994,
same 23.700%. The headline block *is* the zero-cost column. That column is LEAN's default
brokerage model, which charges **no spread** (`NullSlippageModel`) and **no financing**
(`MarginInterestRateModel.Null`).

### The promotion decision was made on the 2 bp column, not the headline one

From the S-18 entry in `research/journal.md:4085-4115`, candidate minus champion:

| window | spread | candidate | champion | dCAR |
|---|---|---|---|---|
| full 2012-2026 | 0 bp | 24.403 | 24.404 | **-0.001** |
| full 2012-2026 | 2 bp | 23.068 | 22.926 | **+0.142** |
| IS 2012-2019 | 0 bp | 17.698 | 19.180 | -1.482 |
| OOS 2020-2026 | 0 bp | 32.801 | 30.863 | +1.938 |

At 0 bp the candidate **loses** by 0.001 CAR points. Under `must_beat: ["Compounding Annual
Return"]` the zero-cost column does not promote it; the 2 bp column does. So the number in the
`stats` block is from the comparison the champion did not win, and the journal is explicit that
"nothing in this comparison reaches |t| = 2" — the full-period paired statistic on return is
t = +0.12. The real case for the promotion, as the entry itself argues, was structural (less
leverage, better Sharpe in both halves, 40% less commission) rather than a return win.

### The all-in figure is 18.785%, and the repository says so in its own file

`champion.json["stats_by_spread"]["deployed_expectation_note"]` records S-22's pre-registered
full-period LEAN factorial, charging the three known instrument corrections together:

```
control 24.403 | spread 2bp 23.068 | financing 23.087 | clock bound lag1 21.384
all three 18.785      (multiplicative null 18.811, interaction -0.026 CAR points)
```

The same note adds that on the deployed 15:45 book — the one the paper account actually trades
— charged 2 bp of spread and IBKR Pro financing, the figure is **19.640%** (19.954% in LEAN
units), and **19.415%** at today's 3.63% cost of money. Its own instruction: "Read every figure
in this file against ~20%, not 24.4%: the headline is about 18% high."

Three things follow. Both the 18.785% and the ~19.6% are *unpromoted research columns*:
`S1_SLIPPAGE_BPS` stays 0.0, `S1_SIGNAL_LAG` stays 0 and `S1_FINANCING` stays off, so the whole
ledger remains on the zero-cost scale and `evaluate.py` refuses a financed row as not
comparable. The correction is out-of-sample weighted more than two to one (IS 14.194% against
17.698%, OOS 24.259% against 32.801%). And none of it is a defect in the runner: the paper
account has been paying all three costs since its first fill.

### The out-of-sample split is not a holdout

`sweep_s38.py:466-470` says so in a comment I have read: "Selection ran on FULL 2012-2026,
which CONTAINS 2020-2026, so a full-period argmax is partly an out-of-sample argmax." The split
is also not gapped or embargoed — `s1_momo` runs with `set_warm_up(history_bars=300,
Resolution.DAILY)`, so the warm-up window for the first "OOS" decision is drawn from the
in-sample half. It is a second in-sample period with a later start date. (The audit adds a
count of ledger rows recorded on that window; I did not re-derive it, because the LEAN rows in
`experiments.jsonl` carry no `start`/`end` fields to count against.)

---

## 8. Data the harnesses stand on

```
$ python -c "import pandas as pd; [print(s, len(df:=pd.read_parquet(f'data/futures/{s}.parquet')), \
  pd.to_datetime(df['t'],utc=True).dt.tz_convert('America/New_York').dt.date.nunique()) for s in ('ES','NQ','MES','MNQ')]"
ES   447,600 bars  395 days   2025-06-08 -> 2026-09-10
NQ   447,596 bars  395 days   2025-06-08 -> 2026-09-10
MES  358,845 bars  317 days   2025-09-07 -> 2026-09-10
MNQ  358,845 bars  317 days   2025-09-07 -> 2026-09-10
```

- `instruments.DATA_VERIFIED = {ES, MES, NQ, MNQ}`. Twelve contracts are specified across four
  tick grids; four have stored, validated history. Fifteen months is the entire futures sample.
- `markets/futures_cme/dataquality.check_futures_frame` reports roll gaps and same-day contract
  overlap as WARN and refuses impossible returns, stale runs and crossed books; `require_usable`
  is called by both drivers before any bar is used.
- **The store is not back-adjusted.** Sessions with two contracts are dropped rather than
  stitched; a roll gap is a WARN, not a correction.
- A quote store exists for **ES only**. MES, NQ and MNQ quotes were never fetched, so the
  one-tick spread is an ES fact applied to the micros by assumption.
- Equity daily data is 69 symbols of yfinance history 1998-2026, survivorship-biased for single
  names; the ETF sleeve is the trusted universe (`AGENTS.md`).

---

## 9. What a backtest here does NOT establish

Read this before quoting any number above.

1. **That the strategy would have made money.** No harness in this repository has ever produced
   a result that clears its own promotion criteria plus a significance test plus an untouched
   holdout, because no such combination is implemented on any path. The futures funnel has
   promoted nothing. The equity champion cleared a criterion with one metric in it.
2. **That the fills are achievable.** The futures funnel fills at a price that has already
   printed, and the red team measured a rule whose entire edge was that. The equity paths fill
   at the next open, which is right, but LEAN charges zero spread by default and the champion's
   headline column is that default.
3. **That the costs are right.** Futures: one measured ES spread applied to three contracts
   whose spreads were never measured, plus a commission constant that changed today and whose
   tests have not caught up. Intraday: `SLIPPAGE_BPS = 1.5` against **+2.22 bps** measured on
   66 real fills (se 0.80, `research/journal.md` A-5). LEAN champion: no spread, no
   financing, in the promoted column.
4. **That the out-of-sample result is out of sample.** Neither the equity split nor the
   intraday split is a holdout; both were selected on data that contains them. The futures
   funnel has no split at all.
5. **That the search was corrected for.** The Bonferroni denominator is real inside one futures
   family and nowhere else. 1,653 equity rows carry no correction and cannot be read by the
   ledger that would apply one.
6. **That "walk-forward" was performed.** It is a five-block sign test with no refit.
7. **That the ledger reflects the code.** Every futures row predates the round-turn fix, the
   leakage gate and the fill-convention reporting. The numbers on disk were produced by a
   version of the funnel that undercharged 76% of its hypotheses.
8. **That a backtested strategy could be traded.** Order transmission is hard-disabled
   (`docs/EXECUTION.md`), there is no bracket verification, no reconciliation and no order state
   machine on any live path, and no futures venue adapter that can submit at all.

## Not modelled

- **No order book.** No matching engine, no book reconstruction; the data floor is 30 seconds.
- **Passive fills are refused**, not estimated. No queue position, no fill probability.
- **No latency model** anywhere. A fill happens at the quote passed in.
- **No partial fills over time.** A fill is whole; impact is a linear price walk.
- **One spread for all sessions.** The measured overnight widening is not applied.
- **Impact is linear in size** beyond the resting quantity, optimistic for orders that matter.
- **No stops or targets in the futures funnel.** The hypothesis family is always-in at +/-1;
  the exit is implicit at the last RTH bar.
- **No financing in the equity paths.** LEAN's `MarginInterestRateModel.Null` charges nothing;
  the champion's book carries 1.50x gross against 1.00x of equity and has never paid interest.
- **No LEAN link for futures**, and no `quant_brain` link for LEAN.

## Not implemented

- A holdout of any kind, on any track. `Holdout.spend()` has never run.
- Purged, embargoed walk-forward in the funnel (`validation.purged_walk_forward` has no caller).
- Any multiplicity control on the equity ledger; the two ledger schemas are disjoint.
- A promotion gate with a significance test (`research/promotion.py` has no caller).
- Spread measurement for MES, NQ, MNQ, or for the overnight session as a separate parameter.
- Automatic use of `topstep.COMBINE_COST` by the twin; the fee must be passed.
- A next-open fill convention in the futures funnel; the subsidy is reported, not removed.
- Any path from a funnel survivor to a twin evaluation beyond the 150-rep gate inside
  `futures_discover.py`; nothing has survived to need one.

## What this document does not claim

It does not claim the simulator predicts realised slippage; it charges a measured median ES
spread and a published Topstep commission and refuses what it cannot price. It does not claim
the twin's pass rates are forecasts; they are distributions over resampled orderings of one
strategy's own sessions under one version of the rulebook. It does not claim the baseline
strategy has any edge; the point of that run is that the pipeline reports none. It does not
claim the champion is wrong — only that 24.403% is the zero-cost column, that the promotion
turned on a different column, and that the repository's own all-in figure is 18.785%.
