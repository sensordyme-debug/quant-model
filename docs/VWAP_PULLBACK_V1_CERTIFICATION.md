# V1.0.0_Frozen — golden synthetic test certification

Intraday Multi-Timeframe VWAP Pullback System. **Synthetic tests only. No historical data was
loaded, no backtest was run, no parameter was tuned, no order surface was touched.**

**Verdict: YELLOW — synthetic tests pass, known limitations remain.** Three ambiguities in the
specification are material and need the owner's confirmation before a historical backtest can
mean anything. Nothing is broken; three rules simply have two defensible readings and the
engine cannot pick for you.

```
spec hash   NQ  da1f18efba2cd5d2      MNQ  4058a53b56ab4b03
golden      219 tests, 219 pass
suite       3,191 passed · 9 skipped · 14 xfailed
mutation    137 applied · 0 skipped · 137 caught · 100%
lint        clean          types  0 errors in quant_brain/strategies (repo baseline: 441)
```

---

## 1. Where the strategy lives

```
quant_brain/strategies/vwap_pullback/
    spec.py         every frozen constant, hashed; the ambiguity and conflict registers
    indicators.py   SessionVwap (18:00-anchored, ONE array), FiveMinuteAggregator, Atr, VolumeSma
    orders.py       simulated OCO bracket, idempotent actions, a book audit after every bar
    governor.py     killswitch · profit cap · trade cap · loss breaker · windows
    engine.py       the FSM and the bar loop; emits canonical Fill / LedgerTrade
```

**Nothing already certified was modified.** `StrategySpec`, `exits.py`, `ledger_builder.py`,
`session_source.py`, `twin.py` and the whole `quant_brain/research` pipeline are byte-identical
to before this phase, and the 2,972 pre-existing tests still pass.

### What was reused rather than rebuilt

| reused | for |
|---|---|
| `markets/futures_cme/instruments` | NQ/MNQ multiplier, tick, tick value |
| `research/canonical_ledger` — `Fill`, `LedgerTrade` | the output types, so a later phase can feed the existing analytics |
| `research/bracket_reference` | the **declared ambiguous-bar policy**: STOP before TARGET, gaps fill at the level |
| `core/calendar.ET` | the one authoritative `ZoneInfo`, so no second clock can drift |
| `core/execution.Side` | order sides |
| `scripts/engine_mutation_test` + `_mutation_specs` | mutation testing |

---

## 2. Conflict register — nine places the frozen spec disagrees with certified code

Full text in `docs/VWAP_PULLBACK_INTEGRATION_PLAN.md` and in `spec.CONFLICTS`. Summary:

| # | component | disagreement | resolution |
|---|---|---|---|
| C1 | `StrategySpec` | certified interface is a **stateless** per-bar signal array; this strategy carries state across bars | separate stateful engine |
| C2 | `exits.breakeven_at_r` | certified BE moves the stop **to entry** at a multiple of **R**; frozen moves it to **fill ± 0.25** at a fixed 15 points | frozen exit manager |
| C3 | — | nothing implements MFE-bar identification or a bounded forward window | new |
| C4 | `ledger_builder` | certified path fills at the bar close and charges slippage as a **cost line**; frozen moves the **fill price** and anchors the bracket to it | frozen engine moves the fill; difference pinned by test |
| C5 | `twin.TopstepTwin` | twin is **session-granular**; frozen governor is **intraday** and stricter, and flattens 25 min before Topstep's 16:10 | separate governor |
| C6 | `session_source` | RTH cutting cannot supply the overnight bars an 18:00 VWAP anchor needs | engine takes a continuous stream — **see the known gap below** |
| C7 | `features.vwap_dist` | existing feature is **close-weighted, frame-anchored**; frozen is **TP-weighted, 18:00-anchored** | not reused; named `SessionVwap` |
| C8 | `instruments` NQ commission | repo cites Topstep's published **$3.78**; frozen says **$4.50** | frozen wins (§31), and it is the more conservative |
| C9 | timeframe guard | certified interface refuses non-1min because resampling is unaudited | 5m derived **inside** the engine, causally |

> **KNOWN GAP carried to the next phase.** No loader exists that hands the engine an
> 18:00-anchored continuous 1-minute stream from `data/futures/*.parquet`. `session_source`
> cuts RTH windows and drops incomplete sessions, which cannot supply the overnight bars.
> Synthetic-only makes this a non-blocker now; **the historical phase cannot start until that
> adapter exists and is equivalence-tested the way `session_source` was.**

---

## 3. Ambiguity register — thirteen, of which three are material

Every one is an explicit, hashed field on `FrozenSpec`; nothing was resolved silently.
`python scripts/vwap_certify.py` prints the full register.

### The three that need the owner's decision

**A1 — "5-minute ATR(14)": Wilder or a simple mean?**
Taken: **Wilder**, the conventional meaning. Both are implemented (`atr_method="wilder"|"sma"`)
and `test_the_two_atr_readings_genuinely_differ_so_the_ambiguity_is_real` demonstrates they
disagree on a series built to separate them. This decides whether the 8.0-point gate opens, so
it changes which bars are tradable at all.

**A2 — the governor's mark-to-market: bar close, or the bar's adverse extreme?**
Taken: **the adverse extreme**, the conservative reading. Both implemented
(`governor_mtm_basis="intrabar"|"close"`);
`test_the_two_mtm_readings_are_both_implemented_and_genuinely_differ` builds a bar whose low
breaches −$800 and whose close does not, and shows one halts while the other does not.

**A12 — slippage scope. This one is OPTIMISTIC and you should look at it.**
The frozen model names one tick on "entry and stop-outs". §13 forbids applying it elsewhere
silently, so the **15:45 hard flatten, the governor flatten and the stall market-close all fill
at the bar's close with zero slippage.** All three are market orders in real life and all three
would slip. The engine does what the spec says and flags it rather than quietly adding cost.

### The other ten, taken and recorded

A3 a bar stamped 15:30 is *at* the cutoff, not after (so 15:30 is the last entry bar) · A4
"touch or penetrate" = long `low <= VWAP`, short `high >= VWAP` · A5 the zone test reads the
**close** · A6 `SMA(volume,10)` **includes** the current bar · A7 a 5m bar entirely above VWAP
gives a negative distance, which passes `<= 6.0` — implemented **literally as written** · A8 a
"loss" is **net** of costs · A9 the cooldown runs from the **exit** · A10 "already beyond the
new target" = the modification bar's close is past fill+20 → market close · A11 the frozen cost
model states **no MNQ commission**, so the repo's $12.20 is used · A13 daily counters roll at
**18:00**, not midnight.

### One ambiguity the implementation itself raised

**A15 — when does the break-even take effect?** A single bar can touch both `fill+15` (arming
BE) and `fill−15` (the original stop). Arming first turns a full 15-point loss into a one-tick
win on an assumption about which tick came first. **The original stop is in force for the whole
bar it arms on**, and `test_the_break_even_does_not_rescue_a_bar_that_also_touched_the_original
_stop` pins it. Note `research/bracket_reference.py` arms *before* the test for the certified
engine — the two now differ deliberately, and that is recorded.

---

## 4. Critical verification

| area | verified |
|---|---|
| **VWAP** | brief's worked example exact: `(100·100 + 102·300)/400 = 101.5`. One continuous array — 61 bars from 18:00 into 09:45 with **zero resets**. Reset at exactly 18:00 (17:59 does not, 18:00 does). TP-weighted, **not** close-weighted, demonstrated on asymmetric bars. |
| **σ** | `(100·1.5² + 300·0.5²)/400 = 0.75`, σ = √0.75 = 0.8660254. Volume-weighted **Welford**, not `E[x²]−μ²`: matches the literal double-sum formula to 1e-9 over 1,380 NQ-scale bars, and gives exactly 0 on a flat market instead of a negative variance. |
| **ATR** | TR = max(H−L, \|H−C₋₁\|, \|L−C₋₁\|) hand-checked incl. a gap (17.0). Wilder and SMA each match an independent reference to 1e-9. Built from `FiveMinuteBar` **by signature**, so a 1-minute bar cannot reach it. Gate closed at 8.0. |
| **5m/1m unity** | the 5m bar carries `vwap_at_close` **recorded** from the 1-minute array. Not recomputed — there is no second VWAP in the package. |
| **FSM** | 6 states, declared transition table covering all of them. 15 legal transitions pass; **8 illegal ones raise**, including every exit from `HALTED_DAY`, which releases only at the 18:00 roll. |
| **OCO** | one linked group, correct side, correct quantity, both prices from the fill. Filled leg **cancels the other**. Second bracket refused; second entry refused; release with a working leg refused; rejected entry leaves no orphan. A book audit runs after **every bar** inside the engine. |
| **fill anchoring** | trigger close 20,001.50 → fill **20,001.75** → stop **19,986.75**, target **20,031.75**. Anchoring to the close would give 19,986.50 — one tick, $5, and the test asserts the difference. `attach_bracket` **cannot see** the signal bar: its only price input is the entry order's fill. |
| **break-even** | fires on the bar's **HIGH** (+16) even when the close is only +5 — a close-only implementation fails this test. Boundary 14.99 / 15.00 / 15.01. Arms once. Short side mirrors on the low. |
| **+25 stall** | **the critical lookahead test passes**: t+1 no break, t+2 no break, **t+3 breaks → NO modification**; the identical sequence with t+3 not breaking **does** modify. A break at t+1 also prevents it. Boundary 24.99/25.00/25.01. MFE bar is the **first** to reach +25 and a later higher bar does not move it. Target modified once. Short mirrors. Already-through → market close. |
| **governor** | killswitch `<=` −800 on **realized + unrealised**, nine boundary cases incl. the brief's own (−500 realized, −300 open). Fires **from the engine with a position open**. Realized-only would miss it — demonstrated. |
| **cooldown** | 1 loss no, 2 losses yes; 44:59 blocked, 45:00 eligible; a win resets; **a scratch neither increments nor resets**. |
| **hard flatten** | 15:44 normal, 15:45 flattens, 15:46 no trading. A full session walked bar by bar ends flat with `hard_flatten`. |
| **DST** | 09:45 / 15:30 / 15:45 / 18:00 hold their minute-of-day across **both** 2026 transitions (6 days × 4 times). Same wall clock = different UTC hour (14:00 winter, 13:00 summer). One 18:00 reset across a spring-forward. No hard-coded offset anywhere. |
| **NQ/MNQ** | same path, same fills, same gross ($605.00), same slippage ($5.00). Only the commission differs, by exactly $7.70. 1·NQ and 10·MNQ are both $20/point and $5/tick. |
| **causality** | mutating every bar after a cut point leaves every earlier outcome byte-identical. `on_bar` takes **one bar**; every indicator's `update` takes **one bar**; the package holds no forward index. |

### Golden accounting, hand-computed

```
stop-out   gross (19,986.75 − 20,001.50) × 20 = −295.00
           slippage (0.25 + 0.25) × 20        =  −10.00
           commission                          =   −4.50
           net                                 = −309.50
target     gross (20,031.75 − 20,001.50) × 20 = +605.00
           slippage 0.25 × 20                  =   −5.00
           commission                          =   −4.50
           net                                 = +595.50
```

Both routes agree: `net == gross − slippage − commission` **and** `net == fill-to-fill −
commission`. If slippage were double-counted the two would differ by exactly the slippage.

---

## 5. Defects found and fixed during implementation

All were found by the tests or by mutation testing, before any result existed.

| severity | defect | fix | regression test |
|---|---|---|---|
| P2 | `_previous_bar` read a history list appended by the **caller**, so a driver that forgot would silently give the trigger a stale previous bar | `on_bar` records history itself | the trigger tests exercise it on every run |
| P2 | five holes in the golden suite, found by mutation testing (see §6) | five tests added | listed below |
| P3 | 46 `Optional` type errors — each a latent `AttributeError` if an invariant broke | position passed explicitly; `Order.resting_price()`; guarded bucket close; `_stamp()` | pyright: **0 errors** |
| P3 | two mutation anchors went stale after the type refactor and were **silently skipped** | re-pointed | mutation run reports `0 skipped` |

No defect was found in the frozen specification's arithmetic. The five suite holes mutation
testing found were: the VWAP fixtures all used symmetric bars where TP == close (so a
close-weighted VWAP was invisible); the entry-cutoff boundary was tested only through the
engine while the mutation named the governor suite; and three anchors that had moved.

---

## 6. Mutation testing

**137 applied · 0 skipped · 137 caught · 100%.** 44 are new and cover exactly the list the
brief names:

`>=`→`>` and `<=`→`<` on the killswitch, profit cap, cooldown, hard flatten and entry cutoff ·
15→14.99 · 30→29.99 · BE 15→14.99 · MFE 25→24.99 · stall window 3→2 · VWAP reset removed ·
wrong timezone · close-based BE · realized-only governor · −800→−801 · 1200→1201 · 4→5 trades ·
2→3 losses · 45→44 minutes · 15:30 moved · 15:45 moved · 18:00 anchor moved · NQ point value
doubled · fill = bar close (bracket anchors to it) · bracket re-derives the signal close ·
entry/stop slippage sign flipped · **missing OCO cancellation** · **duplicate BE modification** ·
ambiguous bar resolving as the target · the forming 5-minute bar becoming visible · TP replaced
by the close · Welford using the stale mean · volume SMA excluding the current bar · the book
accepting a second position · the day never rolling.

Mutation testing found **five holes in the suite and one in the catalogue itself** (a mutation
naming the wrong defending suite scores a hole as a catch). All closed.

---

## 7. Remaining limitations

1. **A12: three exit kinds carry no slippage** (hard flatten, governor flatten, stall close).
   Optimistic, per the frozen spec, flagged. This is the largest single optimism in the model.
2. **A1 and A2 unconfirmed** — the ATR smoothing and the MTM basis change results.
3. **No historical loader for an 18:00-anchored stream** (C6). Blocks the next phase.
4. **Stops and targets fill at their level even on a gap through it** — the repository's
   declared modelling choice, reused, and optimistic.
5. **Partial fills, queue position, market impact and rejections are NOT MODELLED.** The order
   layer can express a rejection (`reject_entry`) and refuses to orphan a bracket on one, but
   the engine never generates one.
6. **One position at a time** — structural in both the FSM and the book.
7. **The Topstep twin has not been exercised against this engine.** The governor is the
   owner's stricter layer; the prop-firm account layer is a later phase.
8. **A7 admits a 5m bar entirely above VWAP** as a long regime, because that is what the
   condition literally says. Worth a second look before the historical run.
9. **Synthetic bars only.** Nothing here says the strategy works, and nothing here was
   measured on a real tape.

---

## 8. Reproducing

```powershell
python scripts/vwap_certify.py              # provenance, ambiguities, conflicts
python scripts/vwap_certify.py --run        # and the three golden suites
python -m pytest tests/test_vwap_indicators.py tests/test_vwap_strategy.py tests/test_vwap_governor.py -q
python scripts/engine_mutation_test.py
```

No randomness: the package imports no generator, seeded or otherwise, and
`test_the_engine_is_deterministic_and_carries_no_randomness` runs the same scenario twice and
compares the trades.
