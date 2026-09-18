# CVD_ABSORPTION_HARVESTER — XFA_V2.0

**Status: HISTORICAL BACKTEST BLOCKED.** No strategy P&L, no monthly economics, no Combine
pass probability and no payout figure is reported below, because none can be computed from
the data this repository holds. What *is* reported: the specification and its hash, the
precise data gap, the seventeen-item ambiguity register, and a governor integration test
that verifies the plumbing.

```
strategy              CVD_ABSORPTION_HARVESTER
version               XFA_V2.0
spec_id               CVD_ABSORPTION_HARVESTER/XFA_V2.0@834bc61035af1616
parent                (none — new root node)
engine                topstep-backtest 0.4.0   API fingerprint fbc36b5fa62afdad
Layer B code hash     f0f02e66bb660e37
account profile       TOPSTEP_50K_COMBINE/v1
execution profile     BASELINE/v1
dataset hash          (none — no dataset satisfied the tick contract)
genealogy status      BLOCKED
ACTIVE_STRATEGIES     0
```

---

## 1. Specification

Implemented verbatim in `topstep_backtester/strategies/cvd_absorption_harvester/`. Every
frozen parameter is asserted against the owner's numbers by test, and the ES contract terms
restated in the spec are asserted equal to upstream's own `SPECS["ES"]` so the arithmetic in
this package cannot drift from the real contract.

| | |
|---|---|
| instrument | 1 × ES, tick 0.25 = $12.50, point $50.00 |
| clock | America/New_York, DST-aware via `zoneinfo`, never a fixed offset |
| CVD reset | 09:30:00 ET, daily, from zero |
| entry window | 09:45:00 – 11:30:00 ET (closing boundary **unresolved**, A1) |
| signal chart | 1-minute, CVD sampled at the exact close |
| lookback | 15 completed bars, **excluding** bar T |
| bracket | stop 8 ticks, target 16 ticks, from the **actual fill** |
| break-even | at +8 ticks MFE, stop → fill ± 1 tick |
| governor | +$160 realized locks the day; −$250 on realized+unrealized kills it |
| costs | $4.14 round turn declared; 1 tick entry slippage, 1 tick stop slippage |

**The spec is deliberately NOT frozen.** `FrozenStrategySpec.freeze()` refuses a spec with
unresolved ambiguities, and eleven of seventeen are unresolved (§4). The strategy class
therefore cannot even be constructed — asserted by test. That is the designed state: PART 39
says stop and request clarification, and deciding these readings after seeing results would
be choosing the reading that won.

## 2. Data — the blocking finding

**TICK DATA REQUIREMENT NOT SATISFIED.**

All 2,779 parquet files in `data/` were scanned on two independent properties — timestamp
granularity and per-trade columns — rather than by filename. Reproduce with:

```
$ python -m topstep_backtester.scripts.survey_tick_data
...
FILES THAT LOOK LIKE A TRADE SEQUENCE (gap <= 1.0s AND tied stamps): 0
sub-second files REJECTED on missing required fields: 1
  data/auctions/s24_quote_windows.parquet  missing ['price', 'volume']
TICK-LEVEL ORDER FLOW: NONE FOUND
$ echo $?
1
```

Filenames are ignored deliberately: this store contains `ES_*_BID_ASK_*.parquet` and
`MES_*_TRADES_*.parquet` files whose names promise order flow their contents do not carry.

| granularity | files |
|---|---:|
| 300 s grid (5-minute) | 1,891 |
| no usable time column | 625 |
| **1-minute bars** | **174** |
| daily bars | 67 |
| 1,800 s grid (30-minute) | 21 |
| sub-second | 1 |

Total 152,947,251 rows. The single sub-second file is
`data/auctions/s24_quote_windows.parquet` — 6,074 rows of **ETF** quote snapshots (SPY, QQQ,
IWM, …) at five named auction windows, carrying no ES, no trade price and no trade size. It
is not time & sales.

### What exists for ES

| file | rows | grid | columns |
|---|---:|---|---|
| `data/futures/ES.parquet` | 447,600 | 60 s | `t, o, h, l, c, v, contract` |
| `data/futures/ES_quotes.parquet` | 447,600 | 60 s | `t, bid, ask, bid_low, ask_high, spread, c, contract` |

Coverage 2025-06-08 → 2026-09-10, 395 calendar days, contracts ESU5/ESZ5/ESH6/ESM6/ESU6.
**Minimum inter-record gap: 60 seconds. Simultaneous timestamps: zero.** A real ES trade
feed prints in bursts within a millisecond, so this is a resampled grid, not a trade
sequence. The per-contract `.raw/ES_*_BID_ASK_*.parquet` and `MES_*_TRADES_*.parquet` files
are IBKR historical **bar** requests (`whatToShow=BID_ASK` / `TRADES`), also on a 60-second
grid — not `reqHistoricalTicks` output.

### Which required fields are missing

Checked mechanically by `tick_schema.check_frame`, including against the best case available
(ES bars inner-joined to ES quotes on timestamp and contract):

| field | ES.parquet | ES_quotes.parquet | joined (best case) |
|---|---|---|---|
| timestamp | present (`t`) | present (`t`) | present |
| **price** (trade price) | **MISSING** | **MISSING** | **MISSING** |
| volume | present (`v`) | MISSING | present |
| **bid** | **MISSING** | present | present, but one per **minute** |
| **ask** | **MISSING** | present | present, but one per **minute** |

Plus two derived state requirements that need a trade sequence and therefore cannot exist
here at all: `previous_trade_price` and `previous_delta`.

`c` is a bar *close*, not a trade price. And even in the joined frame, one bid and one ask
per minute cannot say how many of that minute's contracts traded at the offer — which is the
entire content of CVD.

### Why no approximation was attempted

Signing a minute's volume by its candle direction produces a series that looks like CVD and
is not: it is candle direction wearing an order-flow name. Every divergence signal derived
from it would be an artefact of the approximation rather than a fact about who was lifting
offers, and the resulting equity curve would be indistinguishable in a report from a real
one. PART 2 forbids it; `tick_schema.require_tick_data` enforces the refusal in code so it
cannot be talked past.

### What would unblock it

A per-trade ES feed carrying `timestamp, price, volume, bid, ask` — IBKR
`reqHistoricalTicks(whatToShow="TRADES")` joined to `BID_ASK` ticks, or a Databento /
CME MDP3 extract. **The engine is not the obstacle:** upstream was verified to accept
`AggregateBarUnit.TICK` bars at arbitrary sub-second spacing, so one trade print becomes one
`Bar` and the strategy receives `on_bar` per trade — which is what tick-level break-even and
killswitch evaluation require. This is a pure data gap.

## 3. Data quality

No tick dataset exists, so the PART 22 tick-quality checks could not be exercised against
real data. They are implemented and unit-tested: sorted timestamps, duplicate prints,
missing bid, missing ask, crossed quote (`bid > ask`), trade outside the quote, non-positive
volume, DST boundaries, session boundaries, contract identity.

Two policies worth stating because they are refusals rather than handling:

- a trade **outside** the quote is recorded `UNCLASSIFIABLE`, never forced into a branch;
- a trade with a **missing** bid or ask is recorded `UNCLASSIFIABLE`, contributing zero
  delta and never advancing the previous-delta state, so one bad print cannot silently zero
  the next zero-tick.

The **threshold** — how many unclassifiable ticks a session may contain before the session
is rejected — is not specified by the owner and no default was invented (A5).

## 4. Ambiguity register

Seventeen items: PART 39's fifteen plus two found while implementing. **Eleven require the
owner.** Full text in `spec.py`; questions abbreviated here.

### Resolved — six: four against upstream's documented determinism, two from the brief's own text

| ref | reading taken | authority |
|---|---|---|
| **A8** | a long and a short **cannot** coexist — PART 12.4 needs Close>Open and PART 13.4 needs Close<Open, so no bar satisfies both and no tie-break is needed | the specification's own rules |
| **A12** | a market order fills at the **open of the record after the signal**, slipped one tick adverse — never at the signal bar's close | PART 14 defers to the engine; `fills/bar_fill.py::_market` |
| **A13** | the target is a resting limit and is charged **no** slippage, and with `fill_limit_on_touch=False` must trade *through* the price | PART 6 forbids invention; `fills/bar_fill.py::_limit` |
| **A14** | "locked until 17:00 ET" = locked for the remainder of the trading day; 17:00 ET *is* the Globex day close, so the lock and the day roll are the same instant. Immaterial: the entry window is 09:45–11:30, so a lock can never reach the next session's window | `core/time.py::trading_day_of`, TOPSTEP_SESSION |
| **A15** | the killswitch is a **soft floor** — see below | `execution/sim_broker.py:491, :943` |
| **A17** | a zero/negative-volume print is bad data, recorded `UNCLASSIFIABLE`, not a trade | PART 22 validation list + PART 7 |

**A15 deserves emphasis.** Upstream computes candidate fills against the order book as it
stood at the start of a bar, and an order created during a bar is deferred to the next one.
The emergency flatten is therefore submitted on the record that breached −$250 and fills on
the record *after* it. **The realised loss on a killswitch exit will generally exceed $250**,
by one record's price movement plus stop slippage. At tick resolution that is one trade of
drift; on minute bars it would be a whole minute. This is a property of any bar-sequenced
simulator. `Governor.breach_equity` records the equity that tripped it so the overshoot is
measurable rather than assumed.

### Unresolved — owner input required before any historical run

| ref | material | question |
|---|---|---|
| **A1** | yes | Is a bar completing at exactly 11:30:00 ET eligible, or is the window `[09:45, 11:30)`? |
| **A2** | yes | Is the "prevailing" quote the last one **strictly before** the trade, or **at-or-before** it? The two differ on a fast market and the classification flips with them. |
| **A3** | yes | When `bid == ask` (locked market), a trade at that price satisfies CASE 1 (+volume) and CASE 2 (−volume) simultaneously. Which wins? |
| **A4** | yes | Are the three PART 7 cases an **ordered cascade** or an unordered mutually-exclusive set? |
| **A5** | yes | How many `UNCLASSIFIABLE` ticks may a session contain before it is rejected? |
| **A6** | yes | A midpoint zero-tick takes `delta = previous_delta`. After the 09:30 reset there **is** no previous delta. What is the first such trade's delta? |
| **A7** | yes | First bar that may establish swing memory: seeded from 09:30–09:45 (first entry 09:45), or accumulation starts at 09:45 (first entry 10:00)? |
| **A9** | yes | May more than one position be open? "1 ES contract" reads as a cap, but the spec never says what a fresh signal does while a position is open. |
| **A10** | yes | After a trade closes, is the strategy re-armed or is the day finished? |
| **A11** | yes | If re-armed, may the very next bar produce an entry, and does swing memory persist or reset? |
| **A16** | yes | A minute with no prints produces no bar. Is the lookback the last 15 **bars that traded**, or the last 15 **clock minutes**? |

A2 is not academic: `QuoteBook` implements both policies and a test asserts they return
different quotes for the same trade, so the choice is demonstrably material.

## 5. Implementation — how it maps onto the engine

| concern | owner |
|---|---|
| fills, P&L, drawdown, MLL, consistency, verdict | **upstream engine**, unmodified |
| tick classification, CVD, minute aggregation, swing memory, divergence | Layer B `cvd_absorption_harvester` |
| order submission, bracket, break-even | Layer B **calls** upstream (`buy`/`sell`/`move_stop`) |

One trade print becomes one `Bar` (`o=h=l=c=` trade price, `volume=` trade size) with
`unit=TICK`, so `on_bar` fires per trade and break-even and the killswitch are evaluated per
trade — no tick-level behaviour is downgraded to bar-close behaviour.

**One integration constraint to record:** upstream's `Bar` carries OHLCV and nothing else —
there is no bid or ask on it. Order-flow data therefore cannot travel through the engine's
feed and is supplied to the strategy as a side channel (`QuoteBook`, aligned by timestamp).
The engine still owns every fill and every dollar; the quote book only feeds signal
computation. But the alignment rule is consequently *ours*, which is precisely why A2 must
be resolved by the owner and why `QuoteBook` has no default policy.

The bracket is placed by passing **tick offsets** to `buy`/`sell` so upstream anchors the
OCO children to the real fill price, rather than by computing prices from the signal close —
which would anchor to a fill that never happened.

### Causality

Three separate guards, plus upstream's own:

1. the 15-bar window is built from closed bars only; bar T is not in the deque when it is
   judged;
2. a swing is decided at its **own** close with its **own** CVD — no later bar is ever
   consulted, which is structural rather than checked, because `observe` takes no future
   argument;
3. CVD is sealed in the same operation that seals the bar, so a swing cannot pair with a CVD
   read after its close.

Lookahead canaries (PART 23) plant divergent futures and assert the already-emitted signal
set is byte-identical, and assert a planted later CVD cannot rewrite a stored swing.

## 6. Governor integration test (PART 20)

**This is a plumbing test. It is NOT a strategy backtest and its P&L is not evidence about
this strategy.** It contains no CVD, no swing memory and no divergence test — it cannot,
because those need the missing data. Its entry rule is a bar index. It has its own spec
(`cvd_governor_plumbing_probe/1.0.0@bdb4b0621c1523c9`) so it cannot borrow the strategy's
identity.

It drives the **real** `Governor` class through the **real** engine over 30 synthetic
sessions (1,800 bars, upstream validation clean), cycling three shapes with outcomes decided
in advance.

Arithmetic worked out before running — the target is a limit and pays no slippage, while the
stop pays the declared tick and is therefore **nine** ticks wide, not eight:

```
win   +16 ticks = +$200.00 gross − $3.80 round turn = +$196.20 realized  →  ≥ $160 → lock
loss  −(8+1) ticks = −$112.50 gross − $3.80         = −$116.30 realized
      two losses = −$232.60; a third entry ½ point under water adds −$25.00 unrealized
      −$232.60 + −$25.00 = −$257.60 ≤ −$250  →  killswitch
```

### Result

| shape | sessions | expected | observed |
|---|---:|---|---|
| WIN | 10 | HALTED_SUCCESS | **HALTED_SUCCESS ×10** |
| KILL | 10 | HALTED_FAIL | **HALTED_FAIL ×10** |
| QUIET | 10 | ACTIVE | **ACTIVE ×10** |

- governor transitions: **20** (10 success + 10 fail), zero illegal
- engine round trips matched the hand arithmetic exactly: wins `{196.20}`, full stops
  `{−116.30}`
- the governor's realized figure **reconciles** with the engine's round-trip net
  (`196.20`), after fixing a defect where per-half-turn costs meant only one side's
  commission was counted
- observed killswitch trip: `realized −232.60 + unrealized −25.00 = −257.60 ≤ −250` —
  exactly as documented

The governor was also unit-tested at the boundaries: the lock is realized-only (an
unrealized +$500 does **not** trip it), inclusive at exactly +$160; the killswitch reads
realized+unrealized and fires at exactly −$250; when both hold the killswitch wins; and a
terminal state cannot be left except by the day roll.

### Execution sensitivity on the fixture (plumbing, not strategy)

| rung | ending balance | worst stop | SUCCESS / FAIL / ACTIVE |
|---|---:|---:|---|
| IDEAL | $49,335.00 | −$103.80 | 10 / 10 / 10 |
| BASELINE | $49,085.00 | −$116.30 | 10 / 10 / 10 |
| STRESS_1TICK | $48,873.00 | −$128.80 | 10 / 10 / 10 |
| STRESS_2TICK | $48,373.00 | −$141.30 | 10 / 10 / 10 |

The worst stop widens monotonically exactly as the slippage rungs imply, confirming the
ladder is live; the governor fires identically at every rung, confirming the plumbing is not
sensitive to execution assumptions. **These balances are properties of the fixture.**

## 7–9. Monthly economics, Combine, first payout

**NOT RELIABLY ESTIMABLE — BLOCKED.**

Every figure in these sections is a function of a trade series that does not exist. There
are zero historical trades, zero sessions and zero months of this strategy. Reporting a
monthly return, a `P(pass ≤ N days)` or a payout distribution would require either
fabricating the trade series or approximating CVD, both forbidden.

Additionally, and independently of the data gap, the funded-account stages cannot be modelled
at all: the upstream engine models the **Combine only** (`metrics/economics.py`: *"Funded is
parked"*), and ships no funded rule kernel, no XFA mechanics and no payout schedule.
`EvalEconomics.pass_value` is a **caller-supplied scalar** for what passing is worth, not a
simulated payout — feeding it a number and reporting the output as an expected payout would
be circular. Registered U1–U4 as **UNMODELED** in `reporting/unmodeled.py`.

So the XFA questions in PART 29 would remain unanswerable **even with perfect tick data**,
until an upstream funded kernel and a cited XFA rulebook exist.

### Strategy governor vs Topstep account rules (PART 27 / 30)

These are different things and must not be conflated:

| | strategy governor (owner's rules) | Topstep account (profile `TOPSTEP_50K_COMBINE/v1`) |
|---|---|---|
| daily stop | −$250 on realized+unrealized, self-imposed | no Personal Daily Loss Limit (`dll=None`) |
| daily target | +$160 realized locks the day | no per-day target exists |
| account floor | — | $2,000 trailing MLL, ratcheting on closed balance |
| pass condition | — | balance ≥ $53,000 **and** profit > 0 **and** best day ≤ 0.50 × total profit |

The consistency rate is itself a divergence: upstream hardcodes **0.50**, this repository's
cited rulebook reads **0.55**. The profile defaults to upstream's 0.50 because it is the
*harder* test, so the divergence cannot flatter a result.

There is a structural interaction with the owner's +$160 lock worth knowing **before** any
data arrives, and it runs in two directions:

- the lock makes the consistency rule **easy**. A day is halted once realized reaches
  roughly $196, so the best day is capped near $196 — comfortably under the $1,500 that 50%
  of a $3,000 profit would allow. Consistency is therefore very unlikely to be the binding
  constraint for this strategy;
- the same cap makes the **target slow**. At about $196 of realized profit per locked
  winning day, $3,000 needs at least 16 winning days even with no losing days at all, and
  every losing day adds more. Whether the strategy produces that many winning days inside a
  Combine is exactly the question the missing data would answer.

## 10. Monte Carlo

**NOT RUN.** Upstream's `monte_carlo` block-bootstraps whole trading days from a completed
`BacktestResult`. There is no result to resample. Running it on the governor fixture would
produce a distribution describing the fixture, which would be a fabricated strategy figure.

The methodology that *would* be used is documented and fixed in
`reporting/montecarlo.py`: day-block bootstrap, `seed=0`, `paths=2000`,
`block_length=5`, horizons 5/10/20/30/unbounded. The seed is not a parameter — the horizon
is varied, not the seed, because running several seeds and reporting the best is the
cleanest way to manufacture a pass probability. Note in advance that upstream's
`PROVISIONAL_DAY_FLOOR` is 30 days, so any Combine-length sample will carry the
`provisional` flag.

## 11. Execution sensitivity

For the strategy: **BLOCKED**. The declared assumptions are implemented and carried in the
profile — $4.14 round turn declared by the owner (the ladder currently resolves to upstream's
$3.80 default; the divergence is recorded), 1 tick entry slippage, 1 tick stop slippage, and
**no** target slippage (A13, not invented). The fixture table in §6 demonstrates the ladder
mechanism operates.

## 12. Sample size

```
tick count            0        no tick dataset exists
sessions              0
months                0
strategy trades       0
Monte Carlo paths     0        not run

governor-test days   30        SYNTHETIC — plumbing only, not evidence
governor-test trades 50        SYNTHETIC — properties of the fixture
Layer B tests       208        passing
```

> **VERY LOW SAMPLE — NO ECONOMIC ESTIMATE OF ANY KIND IS AVAILABLE.** The 30 synthetic
> sessions are a plumbing test. They say nothing about whether this strategy makes money.

## 13. Limitations

1. **No tick data.** Minimum granularity in the repository is 60 seconds with zero
   simultaneous prints. CVD is not computable and was not approximated.
2. **Ten unresolved ambiguities.** The spec cannot be frozen, so the strategy cannot run,
   independently of the data gap. Both blocks must clear.
3. **Funded / XFA / payout are UNMODELED upstream.** Not closeable by Layer B work.
4. **The −$250 killswitch is a soft floor** (A15). Realised killswitch losses will exceed
   $250; the overshoot is recorded but its size on real data is unknown.
5. **Quotes cannot travel through the engine's feed.** `Bar` has no bid/ask, so the quote
   side channel and its alignment rule (A2) are Layer B's responsibility.
6. **The declared $4.14 round turn differs from upstream's $3.80** default and this
   repository's $3.78 table. The profile names its fee source; the divergence is unresolved.
7. **No exchange-holiday calendar** exists in either layer, by deliberate agreement.
8. **`TickDataHandler` is strict by design** and raises on a locked market or a session's
   first midpoint trade. On real data those occur regularly, so A3/A4/A6 are not edge cases
   to defer — they will fire on day one.
9. **The governor fixture is not a market.** Its bar shapes were built to reach two
   thresholds. Nothing about its P&L generalises.
10. **`registry.GENEALOGY` is process-local, not persisted.** The node recorded for PART 40
    lives for the life of an interpreter; the durable record of this strategy's identity is
    the `spec.py` module in git plus the header of this report. A genealogy store that
    survives across sessions does not exist yet, so a count of hypotheses examined *across*
    sessions cannot be produced mechanically today.

## 14. Final status

> **BACKTEST BLOCKED** — required tick data unavailable, and specification ambiguities
> unresolved.
>
> Governor integration test: **PASSED** (30/30 sessions halted exactly as planned).
>
> Results: **NOT RESEARCH-GRADE** — there are no strategy results at all. The implementation
> is complete and tested and will run unchanged once (a) a per-trade ES trade-and-quote feed
> is supplied and (b) the ten register items are ruled on.

No recommendation is offered on whether to pursue this strategy. That is the owner's
decision.
