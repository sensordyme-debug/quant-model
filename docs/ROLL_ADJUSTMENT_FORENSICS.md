# Roll adjustment forensics — what each method does to things a strategy uses

Priority 3, Section 6. Every figure below was measured on `data/futures/ES.parquet`
(447,600 one-minute bars, five contracts, 2025-06-08 → 2026-09-10) unless it is marked as a
hand-computed fixture.

Code: `quant_brain/data/rolls.py`. Tests: `tests/test_canonical_data.py`.

---

## The four answers, on a fixture where they can be checked by hand

Contract A flat at **5000**, contract B flat at **5100**. One roll, gap **+100 points
(+2.0%)**.

| direction | method | first bar becomes | last bar becomes | anchor |
|---|---|---|---|---|
| back | difference | 5000 + 100 = **5100** | 5100 | the **last** contract is real |
| back | ratio | 5000 × 1.02 = **5100** | 5100 | the **last** contract is real |
| forward | difference | 5000 | 5100 − 100 = **5000** | the **first** contract is real |
| forward | ratio | 5000 | 5100 ÷ 1.02 = **5000** | the **first** contract is real |

All four remove the gap exactly (`gap_free` → worst residual 0.0). They are not the same
series.

---

## What each method preserves, and what it destroys

Measured across the whole ES store. `UNADJUSTED` is the file as it sits on disk.

| variant | min close | roll-gap free | Σ\|point moves\| | mean high−low | ATR, first session | ATR, last session | off tick grid |
|---|---|---|---|---|---|---|---|
| UNADJUSTED | 5,971.75 | **no** (59.75 pts) | 420,473 | 1.7989 | 0.6847 | 1.9301 | 0.0000 |
| BACK_DIFFERENCE | 6,192.50 | yes | 420,263 | **1.7989** | **0.6847** | **1.9301** | **0.0000** |
| BACK_RATIO | 6,166.49 | yes | **426,337** | **1.8246** | **0.7071** | 1.9301 | **0.1250** |
| FORWARD_DIFFERENCE | 5,971.75 | yes | 420,263 | 1.7989 | 0.6847 | 1.9301 | 0.0000 |
| FORWARD_RATIO | 5,971.75 | yes | 412,873 | 1.7670 | 0.6847 | **1.8692** | **0.1250** |

Read the bolded cells as the distortion each method introduces.

### Difference: point moves survive, returns do not

`p' = p + offset`. A constant shift leaves every difference between two prices unchanged, so
**high−low is identical to the tick** (1.7989 in both), ATR in points is identical, and the
tick grid is preserved because the gaps themselves are whole ticks.

What it breaks: percentage returns. A 10-point move on a bar shifted from 5,971 up to 6,192
is a *different percentage* than the one that traded. And the shift accumulates — the ES
history is lifted by **+220.75 points** over four rolls. On a longer history of upward rolls
a back-difference series eventually goes **negative**, at which point every percentage, log
return and ratio downstream is meaningless. `AdjustmentResult.produced_non_positive` reports
it rather than letting it through.

### Ratio: returns survive, point moves do not

`p' = p × factor`. Every percentage change is preserved exactly. What it breaks:

- **the range scales.** Mean high−low goes 1.7989 → 1.8246, **+1.4%**.
- **ATR scales, and it scales more the further from the anchor.** On the first session ATR
  goes 0.6847 → 0.7071, **+3.3%**; on the last session (the anchor) it is unchanged.
- **the tick grid is destroyed.** Maximum distance from a 0.25 multiple: **0.1250** — half a
  tick. An adjusted price is generally not a price an order could rest on.
- **the spread scales too.** On a frame carrying bid/ask, a ratio adjustment multiplies the
  spread by the same factor, so the modelled cost of crossing it is larger on old bars than
  the market ever charged.

---

## What that costs a strategy, in dollars

A one-ATR stop, first session versus last session, ES at $50/point:

| variant | stop cost, first session | stop cost, last session |
|---|---|---|
| UNADJUSTED | $34.24 | $96.51 |
| BACK_DIFFERENCE | $34.24 | $96.51 |
| **BACK_RATIO** | **$35.35** | $96.51 |
| FORWARD_DIFFERENCE | $34.24 | $96.51 |
| **FORWARD_RATIO** | $34.24 | **$93.46** |

**Same rule, same bars, +3.2% more risk per trade** on the oldest data under back-ratio, and
**−3.2% on the newest data** under forward-ratio. Nothing about the strategy changed. Every R
multiple, every position size derived from the stop, and therefore every P&L figure moves
with it.

Forward-ratio is the worse of the two for this repository: it distorts the **recent** end,
which is the half a walk-forward test leans on hardest.

---

## The roll gaps that are in the file

| roll | gap (pts) | gap (%) | ET wall clock |
|---|---|---|---|
| ESU5 → ESZ5 | +57.75 | **+0.876%** | 18:00 (EDT) |
| ESZ5 → ESH6 | +59.75 | **+0.865%** | **16:00 (EST) — inside RTH** |
| ESH6 → ESM6 | +50.25 | **+0.752%** | 18:00 (EDT) |
| ESM6 → ESU6 | +53.00 | **+0.729%** | 18:00 (EDT) |

NQ runs **+0.875% to +1.037%**.

Gaps are measured as the new contract's first **open** against the old contract's last
**close** — the first price the new contract actually printed. A close-to-close reading gives
slightly different figures because it also contains the new bar's own intrabar move; that is
why the residual "gap" after a perfect adjustment reads as −0.03% to +0.02% on a close-to-close
basis rather than exactly zero. The adjustment is exact; the residual is the first bar's own
trading.

**The winter roll lands at 16:00 ET, the last bar of the RTH window.** See
`docs/DATA_FLOW_FORENSICS.md` FINDING 1 — the boundary is a fixed UTC instant and the venue
clock moves underneath it.

---

## Lookahead: back adjustment is not causal

The one that is easy to miss. A back-adjusted price at time *t* has been shifted by gaps that
had not happened yet at time *t*. Demonstrated rather than asserted, in
`test_attack_lookahead_through_continuous_series_construction`:

| series | first bar, back-difference adjusted |
|---|---|
| two contracts (5000 → 5100) | **5100.0** |
| three contracts (5000 → 5100 → 5250) | **5250.0** |

The **same first bar** takes two different values depending on how many rolls happen *after*
it. A feature computed on back-adjusted absolute price levels therefore embeds the future.
Returns are safe; levels are not.

Forward adjustment does not have this property — its anchor is the first contract, so an
early bar's value never changes as history is appended. It pays for that by falsifying the
recent end instead.

---

## Why neither is execution-valid

`DataForm.execution_valid` is True only for `RAW` and `CONTINUOUS_UNADJUSTED`.

- **difference** preserves points and breaks percentages
- **ratio** preserves percentages and breaks points, the tick grid, and the spread
- there is **no adjustment that preserves both**, because the roll gap is a real
  discontinuity in a real price and removing it has to cost something

A fill is a point event at a price. Both adjusted forms contain prices that were never
quoted, so `ResearchInputs` refuses either as an execution source and says so in the message.
Using one for **features** is fine and supported — the pair is declared, and the report
prints `FEATURE DATA and EXECUTION DATA DIFFER` with both manifest ids.

---

## Choosing

| you want | use | because |
|---|---|---|
| to simulate fills | `CONTINUOUS_UNADJUSTED` or `RAW` | every price was really quoted |
| returns, momentum, volatility | ratio-adjusted | returns are exact across the roll |
| point-based features (ATR, ranges, breakout distances) | difference-adjusted | ranges are exact |
| anything about one contract's own behaviour | `RAW` | no roll to argue about |
| to compute a return across a roll on the unadjusted store | **nothing** | it is +0.87% of fiction |

## The sample this rests on

**Four rolls per instrument. Sixteen in total.** Every statement above about roll behaviour is
an observation on that sample, not a distribution. The store holds fifteen months.
