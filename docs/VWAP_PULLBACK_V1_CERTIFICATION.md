# V1.0.0_Frozen — golden synthetic test certification

Intraday Multi-Timeframe VWAP Pullback System. **Synthetic tests only. No historical data was
loaded, no backtest was run, no parameter was tuned, no order surface was touched.**

**Verdict: GREEN — ready for the historical-loader phase.** The owner's certification register
(2026-09-16) resolved every material ambiguity; `unresolved()` returns empty and a test asserts
it. One blocker remains before a backtest, and it is a missing loader, not a defect.

```
spec hash   NQ  1fe36d12eb631c96      MNQ  08c19f55b6382d72
execution   BASELINE_FROZEN (V1.0.0 exactly)
golden      255 tests, 255 pass       (58 indicators / 91 strategy / 106 governor)
suite       3,227 passed · 9 skipped · 14 xfailed
mutation    154 applied · 0 skipped · 154 caught · 100%   (193 as of the PHASE 2 release gate)
lint        clean     types  0 errors in quant_brain/strategies (repo baseline 410)
```

---

## 1. The owner's decisions, recorded

### A1 — ATR · **RESOLVED**

```
ATR_METHOD = WILDER     ATR_PERIOD = 14     TIMEFRAME = 5m (completed bars)     GATE >= 8.0
```

The simple-mean implementation is retained and tested so the choice stays inspectable, but it
is not the specification. The gate is tested at the engine's own decision point:
`7.999999 → reject · 8.000000 → accept · 8.000001 → accept`, by injecting the ATR at a trigger
minute that is not a 5-minute boundary so no bucket completion can overwrite it.

### A2 — governor mark-to-market · **RESOLVED**

```
MTM_MODE = CONSERVATIVE_INTRABAR_ADVERSE_EXTREME     THRESHOLD <= -$800.00
```

Realized + unrealised, where unrealised is marked at the **lowest** price reached in the
interval for a long and the **highest** for a short. Golden tests prove both sides: a long
whose close sits at −$720 but whose low reaches −$900 **halts**, and the close-based reading is
run beside it to show it would **not** have. Boundary tested end to end at
−799.99 / −800.00 / −800.01, on both directions.

This is the safety layer. It flattens a position no strategy rule would have closed, cancels
the working orders and ends the day.

### A12 — execution slippage · **RESOLVED FOR THE BASELINE**

| profile | entry | stop\* | target\*\* | market exit\*\*\* | = V1.0.0 |
|---|---|---|---|---|---|
| IDEAL | 0 | 0 | 0 | 0 | no |
| **BASELINE_FROZEN** | **1** | **1** | **0** | **0** | **yes** |
| STRESS_1TICK | 1 | 2 | 0 | 1 | no |
| STRESS_2TICK | 1 | 3 | 0 | 2 | no |

\* the initial stop **and** the break-even stop — DECISION 3 is explicit that a break-even stop
is a stop-out when it executes. \*\* a limit order; never charged in any profile.
\*\*\* the 15:45 flatten, the governor flatten and the +25 stall close.

**The baseline charges exactly what V1.0.0 states and invents nothing.** That is not a claim
that the three market exits are frictionless — it is a refusal to make up a number. The
unpriced gap is *measured* by the stress profiles, which are **diagnostic**: a test asserts
that changing the profile changes none of 28 strategy rules, and each profile carries its own
spec hash so a stress result can never be mistaken for the frozen one.

`AMBIGUITY A16` records the one reading the stress definition still needed: "all market exits"
is taken to **include a triggered stop**, since a stop is itself a market order — the more
conservative of the two readings.

---

## 2. C9 / C10 — specification characteristics, not defects

**C9.** `VWAP − 5m low <= 6.0` is satisfied by a candle lying **entirely above** the VWAP,
because the left-hand side is then negative:

```
VWAP = 20,000   5m low = 20,005   ->   20,000 − 20,005 = −5   ->   −5 <= 6   TRUE
```

A bar that never came near the VWAP therefore qualifies as a pullback regime.

**C10.** The exact mirror: `5m high − VWAP <= 6.0` is satisfied by a candle entirely **below**
the VWAP.

**The engine matches the frozen rule as written and has not reinterpreted it.** Proved three
ways: the arithmetic alone; end to end, where a 5-minute bucket placed entirely above the VWAP
still arms long (and entirely below still arms short); and structurally, by asserting the
source contains the inequality verbatim with no `abs()`. Two mutations insert an `abs()` on
each side and both are caught.

The rule is not vacuous — the 6-point limit still binds on the near side. A long bucket whose
low is 7.5 points *below* the VWAP gives `+7.5 > 6` and is refused, and that is tested too.

**Reported as a strategy-definition characteristic. Not changed.**

---

## 3. Defect found and fixed this phase

| severity | defect | how it was found |
|---|---|---|
| **P1** | **Market-exit slippage was accounted but never applied to the fill price, so it cancelled itself out exactly and the STRESS profiles measured nothing.** | the first stress test written |

`_close` reconstructs the ideal (unslipped) exit as `price + slippage × d` in order to report
gross and slippage on separate lines. A caller passing an **unslipped** price together with a
non-zero slippage therefore cancels its own charge:

```
net = (close + s − ideal_entry)·pv − (entry_s + s)·pv − comm
    = (close − ideal_entry)·pv − entry_s·pv − comm          ← s has vanished
```

Invisible under `BASELINE_FROZEN`, where the market-exit tick count is 0 — which is exactly
why it survived the previous phase. All three market-exit call sites now slip the price, as the
stop already did. Four mutations guard it (one per exit kind, plus a sign flip), and three
tests pin the exit price across the ladder for the hard flatten, the governor flatten and the
stall close.

---

## 4. Mutation testing

**154 applied · 0 skipped · 154 caught · 100%.** PHASE 2 and its release gate added 39 more, all caught: 193 · 0 · 193 · 100%.

Five survivors appeared during this phase and all five were closed: two were genuine test gaps
(the governor flatten and the stall close were never exercised across the execution ladder),
one was a `needs_owner` flag hard-wired to `False` that no shipped register entry could
exercise, and **two were mutations I had written badly** — they inserted unused code and
changed nothing, which scores a hole as a catch. Both were rewritten to mutate real behaviour.

17 mutations are new this phase, covering the execution ladder (a baseline that invents a
market-exit tick, a baseline that charges the limit target, a stress that collapses onto the
baseline, a stress ordering inversion), the break-even stop being charged as a market exit
rather than a stop-out, an execution profile that also moves a strategy rule, both `abs()`
reinterpretations of C9/C10, the ATR gate boundary and its removal, a resolved ambiguity losing
its authority, and `needs_owner` ignoring the resolution status.

---

## 5. Historical data readiness — DECISION 9

`python scripts/vwap_data_readiness.py` — **inspection only; it reads bars and counts them.**

An anchored session runs 18:00 ET → 15:45 ET = **1,306** one-minute bars inclusive.

| | ES | NQ | MES | MNQ |
|---|---|---|---|---|
| coverage (ET) | 2025-06-08 → 2026-09-10 | same | 2025-09-07 → 2026-09-10 | same |
| anchored days | 327 | 327 | 262 | 262 |
| median bars/day | 1,306 (**100%**) | 1,306 | 1,306 | 1,306 |
| median overnight bars | 930 | 930 | 930 | 930 |
| days reaching the 18:00 anchor | 327 | 327 | 262 | 262 |
| days on one contract | 327 | 327 | 262 | 262 |
| **usable anchored sessions** | **326** | **326** | **261** | **261** |
| rolls | 4 | 4 | 3 | 3 |
| quality | WARN | WARN | WARN | WARN |

930 overnight bars is exactly 18:00→09:29 with **no holes**, and 930 + 376 = 1,306 is the full
inclusive span. Every percentile from p5 to p95 is 1,306.

| the frozen spec needs | present? |
|---|---|
| 18:00 ET → 15:45 ET coverage | **yes** — 100% of the span at every percentile |
| 1-minute OHLCV | **yes** |
| 5-minute OHLCV | **yes, derivable** — the engine aggregates causally from 1-minute |
| volume | **yes** (27–43 sessions per store contain at least one zero-volume bar; `SessionVwap` handles those without shifting the VWAP, and counts them) |
| contract identity per bar | **yes** — `contract_symbol` on every bar |
| roll information | **yes** — declared roll method, days-before-expiry and roll timestamps on the manifest |
| America/New_York timestamps | **yes** — stored UTC, converted at the point of use, DST by `zoneinfo` |
| VWAP from the complete anchored session | **yes** — the overnight bars exist |
| sufficient overnight data | **yes** |

**The data is sufficient. The loader is not.** `research/session_source` cuts RTH windows and
drops incomplete sessions, which discards the overnight half of every anchored session before
the engine could see it (CONFLICT C6).

---

> **§5 and limitation 1 below were superseded on 2026-09-16 by PHASE 2.** The anchored loader
> now exists and is certified in `docs/VWAP_ANCHORED_DATA_PIPELINE.md`. The counts in the §5
> table are the 80%-of-span readings this script produced; the loader's strict completeness
> rule gives 313 usable ES sessions, not 326. Phase 2 also found and fixed a DST defect in the
> trading-day roll that the readiness script shared.

## 6. Remaining limitations

1. ~~**THE BLOCKER: no 18:00-anchored loader exists.**~~ **RESOLVED in PHASE 2.** Written as
   `strategies/vwap_pullback/data.py` and equivalence-tested against `session_source` on the
   window where the two overlap.
2. **Market-exit friction is unpriced in the baseline by design.** Measure it with
   `STRESS_1TICK` / `STRESS_2TICK` and read those as diagnostics, never as the strategy.
3. **C9/C10** admit regimes that never approached the VWAP. Characteristic, not defect —
   but it will show up in historical results and should not surprise you.
4. **Stops and targets fill at their level even on a gap through it** — the repository's
   declared policy, reused, and optimistic.
5. **Partial fills, queue position, market impact and rejections are NOT MODELLED.**
6. **One position at a time**, enforced in both the FSM and the order book.
7. **The Topstep twin has not been exercised against this engine.** The governor is the owner's
   stricter intraday layer; the prop-firm account layer is a later phase.
8. **A15**: the break-even arms at the END of the bar that triggered it, so the original stop is
   in force for the whole of that bar. Deliberately differs from `bracket_reference`.
9. **Zero-volume bars exist** (27–43 sessions per store). They contribute no VWAP weight and are
   counted, but a session thick with them has a thinner VWAP than its bar count suggests.
10. **The store's quality status is WARN** on all four instruments, with written reasons
    (unexplained gaps, stale price, mixed-contract session). Carried from the canonical layer.
11. **Synthetic bars only.** Nothing here says the strategy works.

---

## 7. Reproducing

```powershell
python scripts/vwap_certify.py --run        # provenance, registers, and the golden suites
python scripts/vwap_data_readiness.py       # DECISION 9, inspection only
python -m pytest tests/test_vwap_indicators.py tests/test_vwap_strategy.py tests/test_vwap_governor.py -q
python scripts/engine_mutation_test.py
```
