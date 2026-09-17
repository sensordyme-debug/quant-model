# Initial Balance Statistical Reversion — ES V1.0_Frozen

The owner's specification, as implemented. **No parameter here may be changed.** `spec.py` is
the authority; this document explains it and records every place the written rules admitted
more than one reading.

```
spec hash    09debab58c51c1d8
instrument   1 x ES    $50.00/point    tick 0.25 = $12.50    commission $4.14 round turn
clock        America/New_York, DST by zoneinfo
bars         5-minute, start-stamped, COMPLETED only
```

---

## 1. The rules, and where each lives

| rule | value | implemented in |
|---|---|---|
| IB window | 09:30:00 → 10:30:00 ET | `indicators.InitialBalance` |
| regime filter | `10.00 <= IB_Range <= 35.00`, inclusive | `InitialBalance.in_regime` |
| armed window | 10:30 → before 14:00 | `governor.may_enter` |
| long trap | a bucket trades `low < Low_IB` | `indicators.Excursion` |
| long rejection | a completed bucket closes `> Low_IB` | `Excursion.rejected` |
| `E_long` | lowest low of the **continuous trip**, sealed at rejection | `Excursion.extreme` |
| target | `IB_Midpoint`, both directions | `engine._maybe_enter` |
| stop | `E ∓ 0.25` — one ES tick beyond the extreme | `engine._maybe_enter` |
| time stop | 60 minutes from the fill | `engine._manage` |
| killswitch | realized + unrealized ≤ −$800 → flatten, halt | `governor.killswitch_breached` |
| profit cap | realized ≥ +$1,200 → no new entries, open trade runs on | `governor.profit_cap_reached` |
| trade cap | 2 per day | `governor.trade_cap_reached` |
| hard flatten | 15:45:00 ET | `engine._manage` |

## 2. The state machine

```
                 ┌──────────────┐  IB range outside 10-35
   session ─────▶│ BUILDING_IB  │──────────────────────────┐
                 └──────┬───────┘                          │
                        │ IB sealed at 10:30, in regime    ▼
                        ▼                            ┌────────────┐
                  ┌──────────┐   rejection           │ HALTED_DAY │
          ┌──────▶│  ARMED   │───────────────┐       └────────────┘
          │       └──────────┘               │             ▲
          │ flat again                       ▼             │ killswitch, or
          │                          ┌──────────────┐      │ profit cap once flat
          └──────────────────────────│ IN_POSITION  │──────┘
                                     └──────┬───────┘
                                            │ stop / target / time / flatten
                                            ▼
                                   ┌─────────────────┐
                                   │ TRADE_COMPLETE  │
                                   └─────────────────┘
```

Tracked per session: IB high/low/range/midpoint, trap direction, trap extreme, trade count,
realized P&L, position, entry time and price, stop, target, time-stop deadline, governor state.
An illegal transition raises rather than repairing itself.

## 3. Bar semantics, written out once

A bucket stamped `09:30` covers **09:30:00–09:34:59** and is COMPLETE at **09:35:00**, which is
when the engine sees it. Therefore, for every signal:

```
bar_start       10:40:00        the bucket's first minute
bar_end         10:44:59        its last
signal_time     10:45:00        the completion instant - when the engine is shown the bucket
decision_time   10:45:00        the same instant
execution_time  10:45:00        the same instant
execution_price bucket close +/- one tick adverse
```

The IB is exactly the **twelve** buckets starting 09:30 through 10:25. It is sealed when the
first bucket starting at or after 10:30 arrives, and no bar at or after 10:30 can enter it.

## 4. Ambiguity register

Ten places the written specification admits more than one reading. None was decided silently.

| ref | question | reading taken | material |
|---|---|---|---|
| **B1** | is `09:30 <= bar time < 10:30` the bar's start or close? | **start**; twelve buckets, 09:30–10:25 | no |
| **B2** | what is "within 60 minutes" on a 5-minute grid? | fill is at the bucket close; the deadline is fill + 60 min exactly, which is the close of the twelfth bucket after entry | **yes** |
| **B3** | may one bucket both trap and reject? | **yes**, literally — `E` is then that bucket's own low/high | **yes** |
| **B4** | what if the rejection closes past the midpoint? | the limit is marketable and fills at once; the trade opens and closes on the same bucket for a gross of zero | **yes** |
| **B5** | stop and target in one bucket? | **stop first** — the repository's declared conservative convention; every case flagged | no |
| **B6** | killswitch on the close or the adverse extreme? | **adverse intrabar extreme** | no |
| **B7** | two entries from one excursion? | **no** — a new entry needs price to leave the IB again; the 2/day cap still binds | **yes** |
| **B8** | does an excursion that begins while in a position count? | the tracker runs continuously; entry is gated separately | no |
| **B9** | slippage on the time stop and the 15:45 flatten? | **none in BASELINE** — the spec does not price them, and nothing is invented; the stress profiles measure the gap | **yes** |
| **B10** | the IB midpoint is off-tick about half the time | rounded to a valid ES tick **away from the entry**; both the raw midpoint and the placed target are in the ledger | **yes** |

Every material reading is RESOLVED against either the literal text or an authority named on the
register. `unresolved()` returns empty and a test asserts it.

### B10 deserves its own note

`(High_IB + Low_IB) / 2` lies on a 0.125 grid, so it is not a placeable ES price whenever
`(High_IB + Low_IB) / 0.25` is odd — about half of all sessions. Filling a target at 6,061.625
is a fill at a price no venue quoted. The specification permits exactly this rounding ("except
as required to maintain valid ES tick increments") and does not name a direction; **away from
the entry** is taken, which makes the target strictly harder to reach.

## 5. Conflict register

| ref | component | disagreement | resolution |
|---|---|---|---|
| **D1** | `instruments.py` | repo carries ES commission **$3.78** (Topstep published, retrieved 2026-09-13); the frozen spec says **$4.14** | the frozen spec wins and is the more conservative; the engine carries its own rate and does not read the instrument default |
| **D2** | anchored loader completeness | it requires an 18:00 anchor this strategy never uses | reused unchanged — verified in Phase 1 that all 14 ES refusals also lack the 15:45 bar, so none is wrongly excluded |
| **D3** | `research/exits.py`, `ledger_builder.py` | neither models an IB-anchored target, a swing-extreme stop, a wall-clock time stop or this governor | not reused; a new engine, borrowing only the exit **precedence** from `bracket_reference` |

## 6. Execution ladder

| profile | entry | stop | target | market exit | = V1.0 |
|---|---|---|---|---|---|
| IDEAL | 0 | 0 | 0 | 0 | no |
| **BASELINE_FROZEN** | **1** | **1** | **0** | **0** | **yes** |
| STRESS_1TICK | 1 | 2 | 0 | 1 | no |
| STRESS_2TICK | 1 | 3 | 0 | 2 | no |

Ticks of adverse slippage. The target is a limit and is never charged. A profile moves fills
and never a rule — asserted by test across all four.

## 7. Files

```
quant_brain/strategies/initial_balance_reversion/
    spec.py          frozen constants, hash, ambiguity and conflict registers
    indicators.py    InitialBalance (sealed at 10:30), Excursion (the trip and its extreme)
    governor.py      killswitch, profit cap, trade cap, cutoff
    orders.py        the OCO bracket with a time fuse
    engine.py        the state machine and the bar loop

tests/
    conftest_ib.py                        hand-computable session builder
    test_initial_balance_reversion.py     38 goldens
    test_initial_balance_causality.py     18 future-corruption attacks
    test_initial_balance_execution.py     56 fill, cost and reconciliation tests
    test_initial_balance_governor.py      23 risk-rule boundary tests
```

Reused unchanged, not duplicated: `vwap_pullback.indicators.{Bar, FiveMinuteAggregator}` and
`vwap_pullback.data.load_anchored` — all certified, so there is no second causal five-minute
aggregator and no second session cut.
