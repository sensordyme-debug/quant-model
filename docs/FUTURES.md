# Futures: the research path end to end

Status of this document: describes `quant_brain/markets/futures_cme/`, `quant_brain/research/
search.py` and `scripts/futures_discover.py` as they stand in the **working tree** on
2026-09-13 23:30 ET, at `HEAD = 4fbc22e` plus uncommitted changes in twelve source files
(`git status --porcelain`). It is pinned to a working tree rather than a commit because
several agents are editing this tree concurrently and two of the numbers below moved while
this document was being written; where that happened it is said so.

Every number here was either read out of the code or measured read-only from the stores. The
measurement is given beside the number. Nothing was copied from `AUDIT_REPORT.md` or
`QUANT_MODEL_SYSTEM_AUDIT.md` without re-deriving it, and three of their figures did not
survive that (§10).

| claim | status | evidence |
|---|---|---|
| CONTRACT ARITHMETIC VERIFIED | yes | all 12 roots match published CME terms, 14 of 14 independent P&L cases agree three ways (§1) |
| DATA VALIDATED | mostly | see `docs/DATA.md`; the stores are clean, but rolls are unmarked and the cost model's spread is measured for ES and MES, wrong for NQ, and unknown for MNQ |
| FUNNEL RUNS | yes | five gates, all reachable, exercised by 263 tests (§4) |
| **THE LEDGER DESCRIBES THE CURRENT FUNNEL** | **no** | all 817 rows predate the session filter, the leakage gate, the round-turn fix and the current commissions (§7) |
| STRATEGY VALIDATED | **no** | 817 hypotheses, 0 survivors that were not retracted (§7) |
| POWER SUFFICIENT TO HAVE FOUND ONE | **no** | 1.7% on MES, 0.2% on MNQ against a $20/session edge (§8) |
| LIVE FUTURES EXECUTION | **no** | nothing in this path can send an order; `docs/topstep/EXECUTION.md` |

---

## 1. The contract universe and its arithmetic

`quant_brain/markets/futures_cme/instruments.py` holds one table, `CONTRACTS`, of twelve
roots: ES, NQ, YM, RTY and their micros MES, MNQ, MYM, M2K; CL and MCL; GC and MGC. Each is a
`FuturesContract` wrapping a `core.instruments.InstrumentSpec` plus roll metadata (`cycle`,
`roll_days=8`, `parent`) and an indicative round-turn commission.

**Tick value is derived, not stored.** `InstrumentSpec.tick_value`
(`quant_brain/core/instruments.py:82`) returns `multiplier * tick`. The predecessor table
`scripts/futures_data.py:71` stores multiplier, tick *and* tick_value as three independent
numbers, which is three chances to disagree; that table still exists (§2).

**Verification performed for this document.** A hand-typed reference table of published CME
contract terms was compared against all twelve roots, and fourteen P&L cases were computed
three independent ways: `points * multiplier * contracts`, `ticks * tick_value * contracts`,
and the production helper `spec.notional(points, contracts)`.

```python
# run from the repo root, python 3.14
import sys; sys.path.insert(0, ".")
from quant_brain.markets.futures_cme import instruments as inst
CME = {  # hand-typed from published CME contract specifications
 "ES":(50.0,0.25,12.50), "NQ":(20.0,0.25,5.00), "YM":(5.0,1.00,5.00), "RTY":(50.0,0.10,5.00),
 "MES":(5.0,0.25,1.25), "MNQ":(2.0,0.25,0.50), "MYM":(0.5,1.00,0.50), "M2K":(5.0,0.10,0.50),
 "CL":(1000.0,0.01,10.00), "MCL":(100.0,0.01,1.00), "GC":(100.0,0.10,10.00), "MGC":(10.0,0.10,1.00)}
for s, c in inst.CONTRACTS.items():
    m, t, tv = CME[s]; sp = c.spec
    assert (sp.multiplier, sp.tick, round(sp.tick_value, 10)) == (m, t, tv), s
print("12 of 12 roots match")
for sym, q, ticks in [("ES",1,4),("ES",3,-7),("NQ",2,10),("MNQ",5,-3),("MES",10,1),("YM",1,25),
                      ("MYM",4,-25),("RTY",2,15),("M2K",6,-15),("CL",1,100),("MCL",3,-100),
                      ("GC",1,20),("MGC",8,-20),("MNQ",1,1)]:
    sp = inst.get(sym).spec; pts = ticks * sp.tick
    a = round(pts * sp.multiplier * q, 10)
    assert a == round(ticks * sp.tick_value * q, 10) == round(sp.notional(pts, q), 10), sym
print("14 of 14 P&L cases agree three ways")
```

Result: **12 of 12 roots match, 14 of 14 P&L cases agree.** Worked examples from that run:
ES 1 contract x +4 ticks = +1.00 pt = **+$50.00**; MNQ 5 x -3 ticks = -0.75 pt = **-$7.50**;
CL 1 x +100 ticks = +$1.00/bbl = **+$1,000.00**; MGC 8 x -20 ticks = -$2.00/oz = **-$160.00**.

**What this verification is and is not.** The reference table is hand-typed from published
exchange specifications; it is not fetched from CME and nothing in the repository checks it
against the exchange. The repository's own automated pin covers **four** roots, not twelve:
`tests/test_golden_futures.py:88` (`EXPECTED_TERMS`) asserts ES, MES, NQ and MNQ only. YM,
RTY, MYM, M2K, CL, MCL, GC and MGC have no test that would catch a typo in their multiplier.

**A stale citation.** The module docstring of `instruments.py:6` says
`tests/test_qb_futures.py` pins every derived value. **That file does not exist.** The pin
lives in `tests/test_golden_futures.py`.

**Which roots have data.** `instruments.DATA_VERIFIED` is `{ES, MES, NQ, MNQ}`. The other
eight are architecturally supported and have no history in this repository at all.

---

## 2. Commissions and the cost model

`FuturesContract.commission_round_turn` is an all-in round-turn commission in USD per
contract. As of this working tree:

| root | round turn | source per the module docstring |
|---|---|---|
| ES, NQ | **$3.78** | Topstep's published all-in rate (help.topstep.com/en/articles/8284197, retrieved 2026-09-13) |
| MES, MNQ | **$1.22** | same |
| YM, RTY, CL, GC | $4.00 | indicative retail/prop default, **unverified** |
| MYM, M2K, MCL, MGC | $1.00 | indicative retail/prop default, **unverified** |

The ES/NQ/MES/MNQ figures replaced round $4.00/$1.00 placeholders during the writing of this
document. The docstring states the reason plainly and it is the right one: $1.00 against
$1.22 undercharges a micro round turn by 18% in the flattering direction, on the contract a
$50K Topstep account is permitted to trade, and `futures_discover` prices its whole funnel
off it. The remaining eight roots were deliberately left at the placeholder because no
per-product Topstep rate was verified for them; that is stated as a default, not a
measurement, and it should be read that way.

**`CostModel.for_contract(symbol)`** (`execution_sim.py:114`) halves the round turn into
`commission_per_side` and refuses outright if the root has no recorded commission — a futures
cost model with a zero commission is wrong rather than conservative.

**`ExecutionSimulator.round_turn_cost(q)`** (`execution_sim.py:283`) is
`2 * commission_per_side * q + spread_ticks * tick * multiplier * q`. With the default
`spread_ticks = 1.0`, the cost the model produces per contract today, measured by
constructing the simulator for each root:

| root | commission RT | 1 tick of spread | **model round turn** |
|---|---|---|---|
| ES | $3.78 | $12.50 | **$16.28** |
| NQ | $3.78 | $5.00 | **$8.78** |
| MES | $1.22 | $1.25 | **$2.47** |
| MNQ | $1.22 | $0.50 | **$1.72** |
| YM | $4.00 | $5.00 | $9.00 |
| RTY | $4.00 | $5.00 | $9.00 |
| MYM | $1.00 | $0.50 | $1.50 |
| M2K | $1.00 | $0.50 | $1.50 |
| CL | $4.00 | $10.00 | $14.00 |
| MCL | $1.00 | $1.00 | $2.00 |
| GC | $4.00 | $10.00 | $14.00 |
| MGC | $1.00 | $1.00 | $2.00 |

```python
import sys; sys.path.insert(0, ".")
from quant_brain.markets.futures_cme import instruments as inst, execution_sim as ex
for s in inst.CONTRACTS:
    print(s, "$%.2f" % ex.ExecutionSimulator(cost=ex.CostModel.for_contract(s), symbol=s).round_turn_cost(1.0))
```

**Two things in this area are currently inconsistent, both measured.**

1. *The `round_turn_cost` docstring is stale.* It states "The model charges 0.480 bps" at
   ES's median RTH price. That figure was computed with the old $4.00 commission
   ($4.00 + $12.50 = $16.50 over 6,872 x 50 = 0.480 bps). With $3.78 the model now charges
   **$16.28 = 0.474 bps** at the same price. F-2a's independently measured realised cost of
   0.488 bps is therefore 2.9% above the model, not the "within 2%" the docstring claims. The
   quarterly table in the same docstring (0.411 / 0.389 / 0.366 / 0.363 / 0.337 / 0.327 bps)
   is spread-only and is unaffected; I reproduced all six of those to three decimals from
   `data/futures/ES_quotes.parquet` (§3 of `docs/DATA.md`).
2. *The tests lagged the constant for about half an hour, and no longer do.*
   `python -m pytest tests/test_golden_futures.py tests/test_qb_futures_dq.py
   tests/test_futures_funnel_costs.py tests/test_leakage_redteam.py
   tests/test_qb_execution_sim.py --tb=no` returned **7 failed / 250 passed** at 23:12 ET,
   **5 failed / 255 passed** at 23:25 ET and **260 passed / 2 skipped / 1 xfailed / 0 failed**
   at 23:45 ET. Every failure in the first two runs was an assertion of the old `$4.00` /
   `$1.00` (`test_the_round_turn_is_commission_plus_one_tick`,
   `test_commission_scales_with_quantity`, `test_totals_accumulate_across_fills`,
   `test_round_turn_cost_is_commission_plus_one_tick_of_spread`,
   `test_micros_cost_more_per_dollar_of_exposure_than_their_parent`,
   `test_a_market_order_crosses_exactly_the_quoted_spread`); another agent closed them while
   this was being written. Recorded because it is the shape of the risk in a shared tree:
   for half an hour the constant and its pins disagreed and only the test run said so.
   **Re-run the command before quoting a pass count.**

**Three contract tables exist, and two of them disagree on commission.** Besides
`futures_cme/instruments.py` there is `scripts/futures_data.py:71` (four roots; multiplier,
tick, tick_value; no commission) and `scripts/sweep_f2.py:54` (ES and MES; an IBKR Pro fee
breakdown of exec $0.85 + exchange $1.18 + NFA $0.02 = **$4.10** round turn on ES, and
$0.25 + $0.37 + $0.02 = **$1.28** on MES). The disagreement with $3.78 / $1.22 is not an
error — they model different venues — but nothing in the code says so, and a reader who moves
between the two files will get two answers. The audit's claim of *six* spec tables is not
reproducible: a repo-wide grep for a literal `"multiplier"` key finds three.

**What is not charged.** The simulator's spread is an assumption for every root but ES, and
`impact_ticks_per_book` only bites when order size exceeds the resting quantity, which
nothing in the funnel supplies. Passive fills are refused rather than modelled
(`is_marketable`), which is the correct refusal and is documented at length in the source.

---

## 3. The session model

`scripts/futures_discover.py` trades one window: `OPEN_ET = "09:30"`, `CLOSE_ET = "15:45"`.
`SESSION_BARS` is **derived from that window, not written down**:

```python
SESSION_BARS = int((datetime.strptime(CLOSE_ET, "%H:%M")
                  - datetime.strptime(OPEN_ET, "%H:%M")).total_seconds() // 60) + 1   # = 376
```

376 because the bars are **start-stamped**: 09:30 through 15:45 inclusive is 376 distinct
one-minute stamps. Changing the window cannot leave a stale constant behind.

`load()` reads the parquet, runs the futures validator, filters to the ET window, and drops
any day whose RTH bars carry more than one contract. `session_frames()` then keeps a day only
if all three hold: exactly `SESSION_BARS` rows, first bar at 09:30, last bar at 15:45. Those
three together admit no interior hole, because 376 distinct minutes cannot fit inside a
376-minute span with a gap in it — and duplicate timestamps, which would defeat that counting
argument, are a FAIL in the validator `load()` runs first.

**The defect this replaced.** The old filter was `len(g) > 200`. A 13:00 ET early close is 210
start-stamped RTH bars — 55.9% of a session — and cleared that threshold by ten. Half days
were averaged in with whole ones in `mean_per_session`, in the walk-forward fold means, and in
the `TwinDay` paths the Topstep twin resamples.

### There is no CME futures calendar, and the equity one is measurably wrong here

The obvious fix is `SessionCalendar.session_minutes`, and it is not available: this repository
has **no CME futures calendar**. The only calendar it has,
`quant_brain/markets/equity_us/calendar.py::USEquityCalendar`, describes the US **cash**
market, and cash and CME equity-index futures do not keep the same hours on a short day.
Measured across all four stores, 1,174 session-days:

| date | store holds | `USEquityCalendar.session_minutes` says |
|---|---|---|
| 2025-07-03 | **225 bars**, last 13:14 ET | 210 |
| 2025-11-28 | **225 bars**, last 13:14 ET | 210 |
| 2025-12-24 | **225 bars**, last 13:14 ET | 210 |

The cash market shuts at 13:00 ET on those days; CME equity-index futures run to 13:15. So
09:30-13:14 inclusive is 225 start-stamped minutes and **the store is right and the calendar
is wrong**. (MES and MNQ carry only two of these three dates; their history begins
2025-09-07.) The mismatch runs the other way too: ES and NQ each hold ten days of full RTH
bars on dates the equity calendar calls non-trading — 2025-06-19, 2025-07-04, 2025-09-01,
2025-11-27, 2026-01-19, 2026-02-16, 2026-05-25, 2026-06-19, 2026-07-03, 2026-09-07 — each of
them a 210-bar CME part-holiday. MES and MNQ hold seven of the ten.

Building a CME holiday table from memory would be a guess wearing the costume of a calendar,
so `session_frames` tests completeness structurally instead. `check_futures_frame` will use a
calendar if one is passed but defaults to `None` for the same reason.

### Measured effect of the filter

```python
import sys; sys.path.insert(0, ".")
from pathlib import Path
from scripts import futures_discover as fd
for s in ("ES", "NQ", "MES", "MNQ"):
    df = fd.load(Path(f"data/futures/{s}.parquet"), s)
    ses = fd.session_frames(df)
    print(s, df["day"].nunique(), "->", len(ses), sorted({len(g) for g in ses}))
```

| store | RTH days | kept | every kept session |
|---|---|---|---|
| ES | 326 | **313** | 376 bars |
| NQ | 326 | **313** | 376 bars |
| MES | 261 | **252** | 376 bars |
| MNQ | 261 | **252** | 376 bars |

Every dropped day is one of exactly two correct shapes — 210 bars ending 12:59 ET, or 225
bars ending 13:14 ET. No day was dropped for a hole or a truncation. The filter cannot tell a
legitimate early close from an outage, and excludes both; that is the safe direction, and it
costs 13 ES sessions of real data that a verified CME calendar would let the funnel keep and
scale.

**A correction to something widely repeated in this repo.** The one-contract filter in
`load()` currently **drops nothing**. All four stores have **zero** mixed-contract days inside
09:30-15:45 ET, because every roll in the store lands at 16:00 or 18:00 ET. The "3-4
two-contract days" cited in `AUDIT_REPORT.md:243` are real, but they are calendar dates in the
**full Globex series** (ES and NQ 4 each, MES and MNQ 3 each), not RTH sessions. Containment
of the roll comes from the roll being outside the traded window and from features being built
per session — not from the mixed-day drop. See `docs/DATA.md` §2.

---

## 4. The discovery funnel and its five gates

`scripts/futures_discover.py main()` builds the grid, `quant_brain/research/search.py::search`
runs it, and `futures_discover.evaluator()` supplies the per-hypothesis judgement. Defaults:
`--price-source ES`, `--contracts 1`, `--max-experiments 200`, `--max-seconds 900`,
`--profit-target 3000`; `Limits(min_sessions=100)` is hard-coded at the call site.

The grid is `threshold_hypotheses(features, thresholds=(-1.0, -0.5, 0.5, 1.0),
directions=(1, -1))` — go long when a feature clears a threshold. On an OHLCV store the
feature library (`futures_cme/features.py::library`) declares 19 features and builds **17**;
`spread_bps` and `quote_imbalance` are **refused** because the store has no `bid`/`ask` or
`bid_size`/`ask_size`. 17 x 4 x 2 = **136 hypotheses** per run. The grid is deliberately dumb;
its purpose is to exercise and measure the funnel, not to find an edge.

Before any hypothesis runs, `build_features` calls `fe.audit_causality` on three sessions
(first, middle, last) and raises `LeakageError` if any feature moves when the future is
perturbed. That guard existed two imports away and this funnel never called it.

### Gate 0 — leakage, and the ceiling canary

The evaluator computes, once per run, what a perfect one-bar-ahead oracle would earn on the
exact price series: `sum |c[i+1] - c[i]| * multiplier * contracts` over every session. Each
hypothesis's `ceiling_share = |gross| / ceiling` is compared against
`MAX_CEILING_SHARE = 0.20`; above it, the hypothesis is refused before any statistic is
computed. `search.py` records the refusal in the ledger so the trial still counts toward
multiplicity.

**Where 0.20 comes from.** It is read off a measured gap, not tuned.
`tests/test_leakage_redteam.py` runs thirteen planted cheats and several clean controls
through this same evaluator and pins each one's share of the ceiling:

```
close oracle  sign(c[i+1]-c[i])    100.0000%   cheat   (test_leakage_redteam.py:386)
future high/low                      99.57%    cheat   (:425)
future volume                        94.68%    cheat   (:452)
whole-frame X.shift(-1)              44.90%    cheat   (:500) — the weakest leak measured
------------------------------------------------------ the empty band, 11x wide
best clean causal rule                3.97%    honest  (:1324)
```

0.20 sits in the middle of that band on a log scale. **The canary is one-sided.** A high share
is strong evidence of a leak; a low share is evidence of nothing, because a rule in the market
for a tenth of the session has a tenth of the opportunity. It also uses the absolute value
deliberately: a perfectly *wrong* oracle is the same bug with the sign flipped, and the funnel
has already produced 40 PASS verdicts with negative t.

`ceiling_share` is now written into the result dict on **every** hypothesis, passing or
failing, so the distribution is readable rather than only the refusals. Measured over the full
136-hypothesis grid on the current code (read-only, no ledger write):

| priced on | sessions | ceiling | ceiling_share min / median / max |
|---|---|---|---|
| ES (sized MES) | 313 | $874,565 | 0.0163% / 0.1138% / **0.4997%** |
| MES | 252 | $750,326 | 0.0288% / 0.0735% / **0.6176%** |

The whole clean grid sits two orders of magnitude below the refusal level. Gate 0 rejects
nothing today, which is what a canary looks like when the air is good.

### Gates 1-4

| # | gate | level | where |
|---|---|---|---|
| 1 | statistics | HAC t must clear `bonferroni_threshold(trials in family)` — 1.96 at the first trial, 3.5623 at the 136th | `Ledger.verdict`, `search.py:200` |
| 2 | cost / execution | at least `MIN_TRADES = 40` round turns, and `costs / abs(gross) <= MAX_COST_SHARE = 0.60` | `futures_discover.py:MIN_TRADES`, `MAX_COST_SHARE` |
| 3 | Topstep survival | `p_pass_combine >= MIN_PASS_RATE = 0.10` over 150 moving-block resamples (block 10, seed 0) through `TopstepTwin(50_000, profit_target=3_000, PayoutPolicy(fraction=0.5))` | `futures_discover.py`, `twin.py`, `paths.moving_block` |
| 4 | walk-forward | at least `MIN_WF_FOLDS = 3` of 5 equal folds have a positive mean | `futures_discover.py:MIN_WF_FOLDS` |

The order is not arbitrary and the reason given in `search.py` is the right one: the
multiplicity penalty must be paid on every hypothesis *tried*, so the statistical gate cannot
sit downstream of filters whose selection is invisible to the correction. Every outcome —
duplicate, too-short, and all five rejection classes — is recorded in the ledger.

The thresholds are named constants with stated derivations, but only `MAX_CEILING_SHARE` has a
measured one. 40 trades, 60% cost share, 10% pass rate and 3-of-5 folds are asserted to be
untuned; nothing in the repository demonstrates that they were not chosen after seeing a
result. Treat them as conventions, not as measurements.

---

## 5. The fill convention

The engine books `pos[i] * (c[i+1] - c[i])`: a position is decided on bar *i*'s close and
filled at that same close. It earns bar *i+1*'s move, so it is not a look-ahead in its inputs
— but the price it transacts at has already printed.

**Why this matters.** On a book with any bid-ask bounce, the decision-close fill collects half
the bounce on every leg. The signal reads no future bar; the *execution* does. The red team
demonstrates the extreme case on a synthetic two-tick book
(`tests/test_leakage_redteam.py:865`): 4,760 legs, subsidy **+2.0003 ticks/leg = $11,901.65**
of a reported gross of $11,923.05 — **99.8% of the edge is the fill convention**, and the rule
clears the cost gate at 45.1%, the Topstep gate at pass rate 1.0, and 5 of 5 walk-forward
folds on the way through.

The result dict now names the convention and prices it:

```python
"fill_convention":      "decision_bar_close",
"gross_next_open_fill": <same positions, filled at bar i+1's open>,
"fill_subsidy":         gross - gross_next_open_fill,
```

`gross_next_open_fill` is `None` unless every session carried an `o` column, so a store
without opens reports absence rather than a zero.

**Measured magnitudes on real bars** (313 ES sessions, sized in MES, current code):

| rule | gross | next-open gross | subsidy | share of gross |
|---|---|---|---|---|
| `ret_5 > +0.50 dir +1` (always-in) | -$995.00 | -$960.00 | -$35.00 | 3.5% |
| `opening_range_pos > +0.50 dir -1` | -$4,110.00 | -$4,005.00 | -$105.00 | 2.6% |
| `z_60 > +1.00 dir +1` | -$4,325.00 | -$3,302.50 | -$1,022.50 | 23.6% |
| `rel_volume > +1.00 dir -1` | -$187.50 | +$430.00 | -$617.50 | **329%** |

Across the whole 136-hypothesis ES grid: median `|subsidy| / |gross|` **3.5%**, p90 **30.9%**,
max **329.3%**, and **6 of 136** hypotheses have a subsidy larger than their entire gross. On
the MES grid: median 2.0%, p90 29.7%, max 338.1%, 2 of 136.

A direct measurement of the mechanism, using a one-bar mean-reversion rule
(`pos[i] = -sign(c[i] - c[i-1])`, causal in its inputs) on real bars:

| store | legs | subsidy | ticks/leg | subsidy as share of gross |
|---|---|---|---|---|
| ES -> MES, 313 sessions | 118,498 | $4,431.25 | **+0.0297** | 32.5% |
| NQ -> MNQ, 313 sessions | 118,826 | $2,573.50 | +0.0459 | 12.3% |
| MES, 252 sessions | 95,414 | $6,112.50 | +0.0511 | 42.4% |
| MNQ, 252 sessions | 95,446 | $2,748.50 | +0.0632 | 21.1% |

A random-signal control on the same bars and the same leg count gives **+0.0019** (ES) and
**-0.0037** (MES) ticks/leg — the subsidy is conditional on the signal, which is what makes it
a subsidy rather than a drift.

**A number I could not reproduce.** `QUANT_MODEL_SYSTEM_AUDIT.md:229` and
`tests/test_leakage_redteam.py:793` both cite "+0.0551 ticks/leg over 68,388 real ES legs,
worth +51% of gross". The mechanism reproduces and the magnitude is the right order, but I
could not reproduce either the leg count or the exact rate with the mean-reversion rule on any
of the four stores under either session filter. Whatever rule or sample produced 68,388 legs
is not recorded. Use the table above, which names its rule.

**What is still not fixed.** The engine reports the subsidy; it does not refuse it and does
not offer a next-open fill convention to run against. The counterfactual is computed inline in
the evaluator. Subtracting it is the reader's job.

---

## 6. Round-turn accounting

`futures_discover.session_accounting(pos, close, *, multiplier, contracts, round_turn_cost)`
returns one session's net equity path, its round-turn count, and its gross P&L.

**Counting the legs.** A session starts flat and must end flat — the funnel trades to 15:45 ET
and Topstep requires a flat book at 3:10 PM CT — so the exit is always traded:

```python
legs = np.abs(np.diff(pos, prepend=0.0, append=0.0))
turns = float(legs.sum()) / 2.0
```

`prepend=0.0` supplies the opening leg; **`append=0.0` supplies the closing one**. The previous
count was `int(abs(diff(pos, prepend=0)).sum() / 2)`, which had the entry and not the exit and
then truncated the odd total downward. A rule that is simply long all session therefore
reported **zero** round turns and was charged **zero** cost.

**What that cost, measured on the ledger:** 624 of the 816 scored hypotheses — **76%** —
recorded `trades: 0` and `costs: 0.0`, and were then discarded by the 40-trade floor as "not
a strategy" before the Topstep and walk-forward gates ever ran.

```python
import json, collections
rows = [json.loads(l) for l in open("research/experiments_futures.jsonl", encoding="utf-8") if l.strip()]
exp = [r for r in rows if "hypothesis" in r]
m = [r.get("metrics") or {} for r in exp]
print(sum("trades" in x for x in m), sum(x.get("trades") == 0 for x in m),
      sum(x.get("costs") == 0.0 for x in m))          # -> 816 624 624
```

With the fix, the same always-in rule on 313 ES sessions now records **313 round turns and
$773.11 of cost** — exactly one MES round turn ($2.47) per session — and **0 of 136**
hypotheses in either grid fall below the 40-trade floor. The 76% of the grid that used to be
silently free now reaches the cost gate.

**When the cost lands.** Cost used to be spread across the session with
`linspace(0, cost, n)`. Terminal P&L is identical either way, but this path is what
`TwinDay(path=...)` hands the Topstep twin, and the trailing maximum loss limit tracks peak
equity intraday. Cost not yet charged is equity the twin believes the account has. Each leg is
now paid at the bar it trades — half a round turn in, half out — with the closing flatten
settled on the last point.

---

## 7. What the discovery funnel actually did

`research/experiments_futures.jsonl` is written through `quant_brain.research.Ledger` by
`scripts/futures_discover.py` and `scripts/futures_topstep_baseline.py`. Verified read-only:

```python
import json, collections
rows = [json.loads(l) for l in open("research/experiments_futures.jsonl", encoding="utf-8") if l.strip()]
exp  = [r for r in rows if "hypothesis" in r]
p    = [r for r in exp if (r.get("verdict") or {}).get("passed")]
print(len(rows), len(exp), len(rows) - len(exp))                       # 818 817 1
print(collections.Counter(r["family"] for r in exp))                   # 7 families
print(len(p), sum(r["verdict"]["t"] < 0 for r in p))                   # 41 40
print(sum(r.get("provenance") is not None for r in exp))               # 0
```

| fact | measured |
|---|---|
| lines in the file | **818** |
| experiment rows | **817** |
| non-experiment rows | **1** — a retraction record, `{"_retraction": "0100e0062ede61b4", ...}` |
| distinct families | **7** |
| PASS verdicts | **41** |
| PASS verdicts with **negative** t | **40** (worst -11.9194) |
| PASS verdicts with positive t | **1** |
| rows with non-null `provenance` | **0** |
| rows containing the string `commit` | **0** |
| rows reaching `stage: validation` | **1** |

Every figure in the brief for this section checked out.

The seven families are `futures.{es,nq}.threshold_grid` (136 each),
`futures.{es,nq,mes,mnq}.threshold_grid.v2` (136 each) and `futures.es.intraday_momentum` (1,
the Topstep baseline). The four `.v2` families are the **544 hypotheses, 0 survivors** run:
520 died at the statistical gate, 24 at the cost gate, 0 at Topstep, 0 at walk-forward
(`research/futures_discovery_{es,nq,mes,mnq}.json`).

**The one positive result was retracted.** `opening_range_pos > +0.50 dir -1` in
`futures.nq.threshold_grid`, experiment `0100e0062ede61b4`, t = **+6.2549** against a 3.5584
bar, 5 of 5 folds, $140.75 per session on a single MNQ. It was a look-ahead:
`_opening_range_pos` took the max and min of the first 30 bars and divided *every* bar of the
session by that range, the first 30 included. The retraction row and the docstring at
`features.py:221` both record it. On the current causal feature it is gross -$4,110 over 313
ES sessions and fails the cost gate at 223%.

**40 PASS verdicts with negative t is not a bug in the ledger.** `Ledger.verdict` tests
|t| > threshold, which is two-sided, and a strongly and reliably *losing* rule passes it. The
cost gate then rejects it. This is why gate 0 uses `abs(ceiling_share)`.

### The ledger does not describe the funnel that exists

This is the most important thing in this document and it is not in the audit. Every one of the
817 rows was written between **2026-09-13T00:31:36-04:00 and 02:49:14-04:00**, and every one
of them predates the current code:

| current behaviour | evidence it postdates the whole ledger |
|---|---|
| 376-bar session filter | every row records `sessions: 326` or `261` — the RTH day count, i.e. the old `len(g) > 200` filter. The current filter would give 313 / 252 |
| gate 0 (leakage) | `ceiling_share` appears on **0 of 817** rows; `rejected_leakage` is absent from all five `futures_discovery*.json` funnel outputs |
| `fill_convention`, `gross_next_open_fill`, `fill_subsidy` | appear on **0 of 817** rows |
| `append=0.0` round-turn fix | 624 rows still carry `trades: 0` |
| $3.78 / $1.22 commissions | every `costs` value was computed at $4.00 / $1.00 |
| causal `opening_range_pos` | the retracted survivor is in the file |

**Nothing in `research/experiments_futures.jsonl` can be quoted as a result of the current
system.** The multiplicity denominators it carries are still real — a trial was paid for even
if it was scored by older code — but every metric in it needs re-running.

### Provenance

All 817 rows carry `provenance: null`. `core.provenance.Provenance.capture()` exists and
records `git_commit`, `git_dirty`, `git_branch` and an `env_key` digest of interpreter and
numeric-stack versions, but it is called only from `scripts/backtest.py:145` and
`scripts/intraday_backtest.py:632`. Neither `futures_discover.py` nor
`futures_topstep_baseline.py` nor `search.py` calls it, and `Hypothesis.experiment()`
constructs an `Experiment` with no provenance argument. The equity ledger is only marginally
better: 258 of 1,653 rows in `research/experiments.jsonl` carry a non-empty `commit`.

The consequence is concrete: this repository runs two interpreters (3.11 with pandas 2.2.3 for
LEAN, 3.14 with pandas 3.0.5 for everything else) and no futures row records which one
produced it.

---

## 8. Statistical power — the section that decides what the other seven mean

"544 hypotheses, 0 survivors" reads as a statement about the market. It is mostly a statement
about power.

**Measured per-session P&L standard deviation of a 1-lot always-in rule.** One contract, long
from 09:30, flat at 15:45, no costs — so this is the dispersion the market hands the funnel
before any strategy exists.

```python
import sys; sys.path.insert(0, ".")
import numpy as np
from pathlib import Path
from scripts import futures_discover as fd
from quant_brain.markets.futures_cme import instruments as inst
for s in ("ES", "NQ", "MES", "MNQ"):
    df = fd.load(Path(f"data/futures/{s}.parquet"), s)
    m = inst.get(s).spec.multiplier
    p = np.array([(g["c"].to_numpy(float)[-1] - g["c"].to_numpy(float)[0]) * m
                  for _, g in df.groupby("day", sort=True)])
    print(s, len(p), round(p.std(ddof=1), 1))
```

| contract | sessions | **sigma per session** |
|---|---|---|
| ES | 326 | **$2,085.9** |
| NQ | 326 | **$4,492.2** |
| MES | 261 | **$222.7** |
| MNQ | 261 | **$485.5** |

All four match the brief exactly. On the 376-bar kept sessions the numbers are barely
different (ES $2,124.4 / 313, NQ $4,578.0 / 313, MES $226.4 / 252, MNQ $493.6 / 252); the
choice of filter is not what drives any of this.

**Power against a genuine $20/session edge.** The funnel judges the *traded* instrument, and
`TRADED = {"ES": "MES", "NQ": "MNQ"}` — the grid is priced on the parent and sized in the
micro, because a $50K account with a $2,000 limit cannot carry an ES point. So the relevant
sigmas are the micro ones. Using the HAC standard error the funnel itself computes
(`stats.tstat_hac(series, horizon=1)`, which at horizon 1 reduces to lag 0) and the funnel's
own multiplicity bar (`stats.bonferroni_threshold(136) = 3.5623`):

| contract | n | sigma | HAC s.e. | power at \|t\|>1.96 | **power at \|t\|>3.5623** |
|---|---|---|---|---|---|
| ES | 326 | $2,085.9 | $115.35 | 5.34% | 0.044% |
| NQ | 326 | $4,492.2 | $248.42 | 5.07% | 0.038% |
| **MES** | 261 | $222.7 | $13.76 | 30.66% | **1.75%** |
| **MNQ** | 261 | $485.5 | $29.99 | 10.23% | **0.19%** |

**1.7% on MES. 0.2% on MNQ.** A funnel with a 1.7% chance of detecting a real edge that
rejects 136 hypotheses has told you almost nothing about whether an edge was there. At 1.7%
power you would expect to reject a genuine $20/session MES edge 98.3 times out of 100.

Sessions needed for 80% power against the same $20/session edge at the same bar:

| contract | sessions needed | at ~252/year |
|---|---|---|
| MES | **2,410** | ~10 years |
| MNQ | 11,430 | ~45 years |
| ES (1 lot) | 210,970 | ~837 years |
| NQ (1 lot) | 978,430 | ~3,883 years |

### The caveat, stated plainly

**Sigma here is for an always-in rule.** A strategy that is in the market less often has a
smaller sigma and therefore better power for the same dollar edge. On the current ES grid the
median hypothesis trades 1.0 round turns per session and the busiest 61.7, so exposure varies
by nearly two orders of magnitude across the grid and a single power number cannot cover all
of it. The always-in figure is the right *reference* — it is the maximum exposure a 1-lot rule
can have, so it bounds the sigma of any 1-lot rule from above and the power from below — but
it is a bound, not the power of any particular hypothesis. A rule in the market 10% of the
time with the same $20/session edge would face roughly sigma/sqrt(10) and materially better
power.

Two things follow, and they are the honest reading of the whole futures track:

1. **"0 survivors" is not evidence that no edge exists.** It is consistent with no edge and
   equally consistent with a real $20/session edge that this sample cannot see.
2. **Adding hypotheses makes it worse.** Every new candidate raises the Bonferroni bar for
   every candidate in its family — 1.96 at the first trial, 3.5623 at the 136th, 3.9110 at
   the 544th — so a wider grid on the same 261 sessions lowers power further. The binding
   constraint on this track is **sessions**, and it is not close.

---

## 9. What is not built

Stated explicitly, because the failure mode this repository is guarding against is describing
things as though they run.

- **No CME futures calendar.** `session_frames` works around its absence; `check_futures_frame`
  defaults its `calendar` argument to `None` for the same reason. Early closes are dropped
  rather than scaled.
- **No live futures execution.** Nothing in `futures_cme/` can place an order.
  `quant_brain/brokers/projectx.py` and `venues/propfirm.py` exist; `docs/topstep/EXECUTION.md`
  is the reference for what they cannot do.
- **No next-open fill convention.** The subsidy is reported, not charged and not avoidable.
- **No provenance on any futures experiment.** §7.
- **No measured spread wired into the cost model, for any root.** `CostModel.spread_ticks`
  is 1.0 everywhere and nothing ever passes a different value. Measured for `docs/DATA.md` §3:
  ES and MES really are one tick, but **NQ's front-month RTH median is two ticks**, so the
  model undercharges the NQ round turn by 36%. MNQ has no quote data at all.
- **No roll marker in the stores, and no back-adjusted series.** `docs/DATA.md` §2.
- **No commission verified for eight of the twelve roots.**
- **Only one market regime.** ES and NQ history begins 2025-06-08, MES and MNQ 2025-09-07.
  Fifteen months of one rising market is not a sample over regimes, and no walk-forward split
  of it can create one.
- **The 817-row ledger cannot be quoted.** §7.

---

## 10. Where I corrected the record

Three claims taken from the audit documents or from the brief for this document did not
survive re-measurement:

1. **"`futures_discover` drops the 3-4 days that carry two contracts"** (`AUDIT_REPORT.md:243`,
   `QUANT_MODEL_SYSTEM_AUDIT.md:207`). The two-contract days are real but exist only in the
   full Globex series; there are **zero** inside the traded RTH window in any of the four
   stores, so the filter drops nothing. Containment of the roll comes from the roll landing
   outside 09:30-15:45 ET, not from this filter. §3.
2. **"+0.0551 ticks/leg over 68,388 real ES legs"** (`QUANT_MODEL_SYSTEM_AUDIT.md:229`). Not
   reproducible; neither the rate nor the leg count matches any rule I could construct on any
   of the four stores. The mechanism and the order of magnitude do reproduce. §5.
3. **"Six hard-coded spec tables"** (`QUANT_MODEL_SYSTEM_AUDIT.md:207`). Three exist in
   production code. §2.

And two things in the source are themselves now stale:

4. `instruments.py:6` cites `tests/test_qb_futures.py`, which does not exist. §1.
5. `execution_sim.round_turn_cost`'s docstring says the model charges 0.480 bps; after the
   commission change it charges 0.474 bps. §2.
