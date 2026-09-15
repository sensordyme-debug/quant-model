# Conditional Opportunity Research

**Core question.** Can overnight information tell us *when* a directional RTH strategy has
enough expected movement to trade, even though overnight information cannot predict direction?

Date: 2026-09-14 · No commits, no pushes, no ProjectX calls, no credentials touched.

---

## 1. Executive conclusion

**Yes to the signal. No to the economics.**

Overnight information produces a genuine, robust, out-of-sample forecast of regular-session
**realised volatility** (OOS R² 0.457–0.506; incremental +0.077 to +0.192 over a yesterday-only
benchmark; consistent sign in *every* regime partition tested).

That forecast, used as a gate, **beats a regime-matched, scale-normalised random control** in
38 of 120 mechanism-instrument cells against 6 expected by chance — concentrated in the trend
family (25 of 36, consistent across all four instruments) with the reversion family showing
the *opposite* sign (0 of 20). This is not the previous study's "trading less" artifact: it
survives matching on regime distribution and survives normalising by each session's own range,
and the improvement appears in **gross capture share**, before costs.

**But it does not produce a tradable edge.** The gate improves losing mechanisms toward
less-losing. Of 120 cells, zero clear the multiplicity bar for the 240-evaluation grid they
were selected from — and none of the 36 positive cells reaches even a nominal 1.96 (max |t| = **1.16**). One tick of slippage
erases 13 of the 36 positive cells. No Combine simulation was run, because running one on a
mechanism with no established edge would produce a pass rate that would get quoted.

**Why it fails is mechanistically specific and is the study's most useful result.** The
opportunity model forecasts **path**, not **displacement**:

| target | OOS R² |
|---|---|
| realised volatility (path) | **+0.457 … +0.506** |
| range (path) | +0.216 … +0.282 |
| \|net move\| (displacement) | +0.030 … +0.083 |
| efficiency = \|move\|/range | **negative** |

A directional trade is paid for displacement. Sorting by the forecast, ES median range grows
86% from the low tercile to the high while median net move grows only 31%, so efficiency
*falls* from 0.467 to 0.409. High-forecast-volatility sessions are **choppier, not more
directional**. The gate can tell you the day will be big; it cannot tell you the day will go
anywhere.

---

## 2. Opportunity prediction results (Phase 1)

`scripts/opportunity_panel.py`, `scripts/opportunity_model.py`,
`quant_brain/research/opportunity.py`

Fourteen predictors were built as specified. All are computable at 09:29 ET; causality is
tested by perturbation, not by inspection (`tests/test_opportunity.py`).

**Cost is never the binding constraint.** P(RTH range > 20 round turns) = **1.000** on all
four instruments. Even at 20 round turns per session the day's range covers the cost
essentially always.

**Model selection.** Six candidate feature sets were compared on OOS R². The three-predictor
set won on every instrument; the full fifteen-predictor set was *worse* than the benchmark on
two.

| feature set | ES | NQ | MES | MNQ |
|---|---|---|---|---|
| prev-day only (benchmark) | 0.363 | 0.413 | 0.385 | 0.411 |
| ATR alone | 0.449 | 0.461 | 0.426 | 0.404 |
| **ATR + vol ratio + prev RV** | **0.485** | **0.506** | **0.469** | **0.457** |
| all 15 | 0.456 | 0.536 | 0.355 | 0.452 |

*(target: RTH realised volatility; OOS R² vs expanding mean)*

**Disclosure:** the specific set was chosen by looking at these scores, so the reported
incremental magnitude is optimistically biased. What is *not* biased: every candidate set
containing an overnight term beat the benchmark on ≥3 of 4 instruments, and more predictors
was strictly worse. The direction of the conclusion is robust; the number 0.192 is not.

**Locked model:** `FEATURES = ("on_atr_pct", "on_vol_ratio", "prev_rth_rv_pct")`, ridge = 1.0
(declared, never tuned), expanding window, min 60 training sessions, refit daily.

**Control that must fail, and does:** asked to forecast *signed* return, the same model gives
OOS R² of −0.138 to −0.216. No leak.

---

## 3. Conditional directional results (Phase 2)

`scripts/conditional_direction.py` · 110 cells · Bonferroni |t| > 3.50

Five conditioners (overnight range, volume ratio, close location, normalised move, move
magnitude) × six declared buckets (0-10, 10-25, 25-50, 50-75, 75-90, 90-100) × four
instruments. All buckets are **trailing** percentiles — a session's bucket is decided from
history only.

**Zero of 110 cells cleared even a nominal |t| > 1.96.** Maximum |t| across the entire grid
was **1.9**, against 5.5 cells expected to clear by chance. Every monotonicity trend statistic
fell between −0.35 and +1.51.

### The one pattern, and its falsification

The 75–90 bucket came out positive in **all 20** of its cells (5 conditioners × 4 instruments),
t between 1.2 and 1.9. The cells are heavily dependent — the conditioners are correlated and
ES/MES and NQ/MNQ are the same two indices — so this was taken to independent data rather than
re-tested where it was found.

**Preregistered confirmation test** (`scripts/conditional_confirm.py`): SPY and QQQ, 2016–2026,
2,600 sessions, different vendor and venue. Prediction fixed before running: positive signed
continuation at |t| > 1.96 on both.

| | n | mean % | t | verdict |
|---|---|---|---|---|
| SPY 75–90 | 441 | **−0.0299** | **−0.62** | NOT CONFIRMED |
| QQQ 75–90 | 469 | **−0.0180** | **−0.35** | NOT CONFIRMED |

Negative on both — opposite sign to the prediction. Trend across all buckets on ten years:
SPY r = +0.005 (t = 0.24), QQQ r = −0.015 (t = −0.78). **The 20-of-20 agreement was
multiplicity across correlated cells.** Registered as `OPP-4`, REJECTED.

---

## 4. Volatility-gating results (Phase 3)

`scripts/opportunity_gating.py` · 30 existing tournament mechanisms × 4 instruments · 40
regime-matched random controls each

No new mechanisms were invented. The gate is `forecast RV ≥ trailing median`, decided at 09:29,
threshold from a trailing expanding quantile.

**Two-stage rule honoured:** the forecast was validated against realised volatility — a
quantity measured with no reference to any strategy's P&L — *before* being allowed to gate
anything. No gate is fitted to P&L anywhere in this study.

**Primary metric is $/trade, not net profit.** Every mechanism in the library loses money, so
switching one off for most of the calendar "improves" net profit mechanically. Per-trade
expectancy cannot be gamed that way.

### The preregistered predictions, and how they did

| | prediction | result |
|---|---|---|
| **1** | gate HURTS trend/breakout per-trade (efficiency falls with vol) | **FALSIFIED** — trend +$1.01, breakout +$1.21 median |
| **2** | gate HELPS reversion per-trade | **FALSIFIED** — reversion −$0.73 median |
| **3** | nothing beats the regime-matched control | **FALSIFIED** — 24 of 120 beat control p95 vs 6 expected |

I got 1 and 2 exactly backwards, and the reason is worth recording: I conflated *efficiency*
(a ratio, which falls with volatility) with *per-trade dollars* (an absolute). Displacement
still grows +31% into the high tercile while round-turn cost stays fixed, so per-trade
economics improve even as efficiency deteriorates. The *structure* of the prediction — trend
and reversion responding oppositely — was correct; the sign was not.

---

## 5. Random-gate controls (Phases 4 and the scale control)

Two independent controls were required to believe the Phase 3 result.

### Control 1 — regime-matched random gates

The previous study's failure mode was a gate that improved results by trading less. Random
gates here are matched on **trade frequency, session frequency, sample size, and regime
distribution** — the last one sampling the same number of sessions from within each trailing-
volatility tercile, which the previous study did not do.

**Result: 24 of 120 cells beat control p95** (6.0 expected).

### Control 2 — scale normalisation

$/trade is not scale-neutral: the gate selects bigger-move days, and per-trade outcomes scale
with move size. `scripts/gating_scale_control.py` re-runs the identical comparison with every
session's P&L divided by that session's own dollar range, so pure scale cancels.

**The advantage survived, and strengthened:**

| | raw $/trade | scale-free $/trade |
|---|---|---|
| cells beating control p95 | 24 / 120 | **38 / 120** (6 expected) |
| Phase 3 winners replicating | — | **23 of 24** |
| median capture-share delta (winners) | — | **+0.00311** |

Capture share is gross P&L over total available movement — scale-free by construction and
computed *before* costs. It improves, so this is not cost arithmetic.

### Where the effect lives

| family | n | beat scale-free p95 | median capture delta | median gated $/trade |
|---|---|---|---|---|
| **trend** | 36 | **25** | **+0.00240** | −4.09 |
| breakout | 24 | 7 | +0.00035 | −1.79 |
| volume | 12 | 5 | +0.00127 | −3.60 |
| session | 16 | 1 | −0.00006 | −3.28 |
| **reversion** | 20 | **0** | **−0.00093** | +0.34 |
| volatility | 12 | 0 | −0.00058 | −4.77 |

Per instrument, trend cells beating p95: ES 7/9, MES 7/9, MNQ 4/9, NQ 7/9 — consistent across
both independent index complexes. Reversion shows the opposite sign. **That is a coherent
pattern, not scatter**, and it is why the result is registered as a real discovery rather than
dismissed.

**The caveat that governs everything:** the last column. Median gated $/trade for trend is
**−$4.09**. The gate makes losing mechanisms lose less. ES `trend.ret_60.q80` gated still nets
**−$37,463**.

---

## 6. Cross-market results (Phase 5)

`scripts/cross_market.py` · 2,571 common trade dates, 2016–2026 · 126 tests · Bonferroni
|t| > 3.54

**There is no RTY or M2K in the futures store** — it holds ES, NQ, MES, MNQ, which is two
indices, not three. A three-way dispersion is not computable there. The ETF store supplies
SPY, QQQ, **IWM (the Russell 2000, the brief's RTY)** and DIA over ten years.

**Magnitude: 15 survivors.**

| feature → RTH range | SPY | QQQ | IWM | DIA |
|---|---|---|---|---|
| dispersion | +0.278 (14.7) | +0.287 (15.2) | **+0.330 (17.7)** | +0.283 (15.0) |
| leader spread | +0.278 (14.6) | +0.285 (15.1) | +0.331 (17.8) | +0.283 (15.0) |
| mean overnight | −0.152 (−7.8) | −0.145 (−7.4) | −0.143 (−7.3) | −0.150 (−7.7) |

Cross-market dispersion is a strong, independent magnitude predictor. (The negative sign on
mean overnight return is the leverage effect: up nights precede narrower days.)

**Direction: 1 survivor of 36, and it does not survive a split-half test.**

`spread_SPY_DIA → rth_ret_DIA`, r = +0.072, t = +3.68 on the full sample. Split:

| | n | r | t |
|---|---|---|---|
| first half | 1,285 | **+0.159** | +5.76 |
| second half | 1,286 | **−0.0003** | −0.01 |

Positive 2016–2020, noise or negative 2021–2026. Economically it is 5.9 bp per 1-sd spread,
R² = 0.53%. **Rejected** (`OPP-6`).

**Spread continuation/reversal:** all six pairs null (|t| ≤ 1.83).

---

## 7. Opening-transition results (Phase 6)

`scripts/opening_transition.py` · 24 cells · both panels

For each decision point (5, 15, 30, 60 min) the remainder of the session was forecast three
ways: overnight only, opening only, and both plus their interaction. Reporting all three is
what makes "the overnight added something" distinguishable from "the opening did all the work".

**23 of 24 cells have negative out-of-sample R².** The single positive (SPY at 30m, +0.0104) is
1 of 24 and is contradicted by SPY at 5, 15 and 60 minutes, all negative.

**The interaction model was worse than the best single model in 22 of 24 cells.** Adding
overnight information to opening information actively hurts.

Cost of deferring: median remaining range falls from 0.807% (full RTH) to 0.635% at 60 minutes
on ES — roughly 21% of the opportunity spent waiting for a signal that never arrives.

---

## 8. Topstep economics (Phase 7)

`scripts/opportunity_economics.py`

The brief's order was followed, and the sequence terminated at step 2.

**Step 1 — positive expectancy?** 13 of 120 cells ungated, 23 of 120 gated. With 120 draws
centred near zero, that is *fewer* than chance would give.

**Step 2 — survives multiplicity?** The grid is 30 mechanisms × 4 instruments × {gated,
ungated} = **240 evaluations**; two-sided 5% Bonferroni is **|t| > 3.70**.

| symbol | strategy | variant | $/trade | net | t |
|---|---|---|---|---|---|
| NQ | revert.vwap.q90 | ungated | 25.54 | 42,548 | **0.97** |
| NQ | session.midday_reversion | ungated | 12.08 | 18,204 | **1.16** |
| NQ | breakout.compression_expansion | gated | 17.72 | 12,136 | **0.57** |
| ES | revert.vwap.q95 | gated | 11.36 | 8,385 | **0.52** |

**Zero cells clear the bar.** Across all 36 positive (cell, variant) pairs the maximum |t| is **1.16** — not one of them reaches even a *nominal* 1.96, before any multiplicity correction at all.

**Steps 3 and 4 were not run as a gate on the Combine.** Running a Combine simulation on a
mechanism with no established edge produces a pass rate, and a pass rate in a report gets
quoted out of context. Slippage was measured anyway:

| | cells positive |
|---|---|
| commission only | 36 of 48 |
| **+ one tick round-turn slippage** | **23 of 48** |

One tick erases 13 of 36. The best-looking cell in the whole grid (NQ revert.vwap.q90,
$42,548) had the gate **hurt** it (+25.54 → +12.73) and sits at the **20th percentile** of its
own random control.

---

## 9. Regime robustness (Phase 8)

`scripts/opportunity_robustness.py`

The one surviving result gets the harshest treatment, because it is the only one anybody would
act on.

| partition | signs agree? | R² path range |
|---|---|---|
| whole sample | — | 0.457 – 0.506 |
| trailing volatility regime (L/M/H) | **all four instruments AGREE** | 0.275 – 0.613 |
| trend regime (up/down) | **AGREE** | 0.355 – 0.597 |
| calendar year | **AGREE** | 0.457 – 0.522 |
| overnight range tercile | **AGREE** | 0.217 – 0.575 |
| overnight volume tercile | **AGREE** | 0.302 – 0.643 |
| first vs second half | **AGREE**, second half stronger | 0.371 – 0.529 |

No partition inverts. Incremental-over-yesterday dips slightly negative in three MID/LOW cells
(−0.096 to −0.019) but is positive in the large majority.

**The path/displacement gap holds in every partition.** R² for |net move| stays between −0.026
and +0.148 everywhere. There is no regime in which the forecast becomes directionally useful —
which is exactly why the gating result cannot be converted into profit.

---

## 10. Statistical and multiple-testing accounting (Phase 9)

**Trials spent by this study: 500**, all written to `research/experiments_futures.jsonl`
(356 rows) under family `futures.conditional_opportunity.v1`.

| phase | tests | bar | survivors |
|---|---|---|---|
| 2 conditional direction | 110 | \|t\| > 3.50 | 0 (0 at nominal 1.96) |
| 5 cross-market | 126 | \|t\| > 3.54 | 15 magnitude, 1 direction (rejected on split-half) |
| 6 opening transition | 24 | OOS R² > 0 | 1 of 24 |
| 3 gating | 120 | control p95 | 24 |
| 4 scale control | 120 | control p95 | 38 |
| 7 economics | 240 evaluations | \|t\| > 3.70 | **0** |

**Discovery vs confirmation**, kept separate in `research/hypotheses.jsonl`:

| ID | claim | stage | result-driven | effective trials |
|---|---|---|---|---|
| OPP-1 | overnight forecasts RTH realised vol | **ROBUSTNESS** | no | 1 |
| OPP-5 | cross-market dispersion forecasts range | **VALIDATION** | no | 1 |
| OPP-8 | gate improves trend-mechanism capture | **DISCOVERY** | **yes** | **2** |
| OPP-2 | model forecasts displacement | REJECTED | no | 1 |
| OPP-3 | direction conditionally predictable | REJECTED | no | 1 |
| OPP-4 | 75–90 bucket is real | REJECTED | **yes** | 2 |
| OPP-6 | cross-market spreads forecast direction | REJECTED | no | 1 |
| OPP-7 | overnight useful after the open | REJECTED | no | 1 |
| OPP-9 | any gated mechanism is tradable | REJECTED | no | 2 |

**No untouched holdout was inspected.** The 2016–2026 ETF panel was used once as a
confirmation set for OPP-4 (a preregistered, single, falsifying test) and otherwise only for
questions the futures panel cannot answer. It is *not* clean for future directional
model-selection and must be treated as spent for that purpose.

**Budget statement:** the futures panel (312/251 sessions) is now heavily used. Five hundred
trials have been recorded against it across two studies. It should be considered exhausted for
directional discovery. Further directional work needs new data, not new hypotheses.

---

## 11. Failed hypotheses — preserved deliberately

1. **Unconditional overnight direction** — 8 framings, 46 tests, negative OOS R² (prior study).
2. **Conditional overnight direction** — 110 cells, max |t| = 1.9, zero at nominal 1.96.
3. **The 75–90 continuation bucket** — 20/20 sign agreement on futures, falsified on 2,600
   independent ETF sessions with the *opposite* sign.
4. **Quiet-overnight Combine gate** (prior study) — the canonical example: 16.8% → 45.8% pass
   rate, entirely explained by trading less.
5. **Overnight drift as alpha** (prior study) — calendar artifact; SPY over the same 313 dates
   reproduces it, ten years inverts it.
6. **Cross-market directional spreads** — 1 of 36 survivors, first-half only.
7. **Opening transition** — 23 of 24 cells negative; interaction worse than best single in 22.
8. **Displacement forecasting** — R² 0.03–0.08 against path's 0.46–0.51, in every regime.
9. **My own Predictions 1 and 2 in Phase 3** — falsified, sign backwards, cause identified
   (efficiency ratio confused with per-trade dollars).
10. **Gating as an economic remedy** — beats its controls, improves nothing into profit.

---

## 12. Surviving hypotheses

### OPP-1 — the opportunity forecast · CONFIRMATION

| | |
|---|---|
| hypothesis | overnight ATR + volume ratio + prior-day RV forecast RTH realised volatility |
| sample | 232 (ES/NQ), 171 (MES/MNQ) out-of-sample forecasts |
| instruments | ES, NQ, MES, MNQ |
| period | 2025-06-09 … 2026-09-10 |
| effect | OOS R² 0.457–0.506 vs mean; **+0.077 to +0.192 vs yesterday-only** |
| OOS R² | yes — that *is* the metric; expanding window, refit daily, causal |
| cost-adjusted | n/a (a forecast, not a trade) |
| regime stability | consistent sign in **all** partitions tested |
| multiple testing | 6 feature sets compared; magnitude biased, direction robust |
| genealogy | `OPP-1`, stage ROBUSTNESS, effective trials 1 |
| **status** | **CONFIRMATION** |

### OPP-5 — cross-market dispersion → range · VALIDATION

| | |
|---|---|
| sample | 2,571 common trade dates |
| instruments | SPY, QQQ, IWM, DIA |
| period | 2016-01-05 … 2026-09-10 |
| effect | r = 0.278–0.331 |
| CI (Fisher, n=2571) | ±0.038 → [0.240, 0.316] at the low end |
| t | 14.7 – 17.8 |
| multiple testing | Bonferroni over 126 tests, |t| > 3.54 — cleared by 4× |
| genealogy | `OPP-5`, stage VALIDATION, effective trials 1 |
| **status** | **VALIDATION** (not confirmed on futures — the futures store lacks a third index) |

### OPP-8 — the gate improves trend capture · DISCOVERY ONLY

| | |
|---|---|
| hypothesis | gating a trend mechanism to high-forecast-vol sessions raises scale-normalised per-trade capture above a regime-matched random control |
| sample | 36 trend cells (9 mechanisms × 4 instruments), 40 controls each |
| period | 2025-06-09 … 2026-09-10, evaluable window only |
| effect | 25 of 36 beat control p95; median capture-share delta **+0.0024** |
| per instrument | ES 7/9, MES 7/9, MNQ 4/9, NQ 7/9 |
| falsifier passed | survives regime-matching **and** scale normalisation; gross capture improves |
| contrast | reversion 0/20, opposite sign |
| cost-adjusted | **median gated $/trade −$4.09 — still losing** |
| multiple testing | **fails** — 0 of 240 evaluations clear \|t\| > 3.70; best t = 1.16 |
| genealogy | `OPP-8`, stage DISCOVERY, **result_driven=True**, effective trials 2 |
| **status** | **DISCOVERY. Not confirmed. Not tradable.** |

---

## 13. Recommended next experiments

Ranked by expected information per unit of remaining data budget.

1. **Confirm OPP-8 on data it has never seen.** It is the only live positive and it is
   result-driven on 250 sessions. The ETF panel can host a trend mechanism and the same
   volatility gate over 2,600 sessions. This is the single highest-value next step and it is
   free.
2. **Test the gate on displacement-insensitive mechanisms.** The gate selects choppy sessions.
   Every mechanism in the current library is displacement-paid. A mechanism paid for *path* —
   a scalper, a range-fader with a hard stop — is the natural counterpart, and none exists in
   the library. This is the one case where the brief's "only if a genuinely new mechanism is
   revealed" condition is met.
3. **Use the volatility forecast for sizing, not gating.** It predicts path at R² ≈ 0.5, which
   is a risk input. Test volatility-scaled position sizing against fixed sizing **at matched
   average contract-days** — the exposure-matched control that gating failed in the prior study.
4. **Characterise the 15:10–16:00 block directly.** Still the heaviest quarter-hour, still
   excluded from the shared loader's default window, still uncharacterised.
5. **Do not run another directional tournament on the futures panel.** 500 trials are recorded
   against 250–312 sessions. The bar is now punitive and correctly so.

---

## 14. Exact reproducibility commands

```bash
# Phase 1 - opportunity panel and forecast
python scripts/opportunity_panel.py
python scripts/opportunity_model.py

# Phase 2 - conditional direction, and its out-of-sample falsification
python scripts/conditional_direction.py
python scripts/conditional_confirm.py

# Phases 3 and 4 - gating and the regime-matched random control  (~60 min)
python scripts/opportunity_gating.py --controls 40

# The scale control that decides whether the gate has skill  (~60 min)
python scripts/gating_scale_control.py --controls 40

# Phase 5 - cross-market
python scripts/cross_market.py

# Phase 6 - opening transition
python scripts/opening_transition.py

# Phase 7 - Topstep economics and slippage sensitivity
python scripts/opportunity_economics.py

# Phase 8 - regime robustness
python scripts/opportunity_robustness.py

# Phase 9 - ledgers  (appends; run once)
python scripts/opportunity_ledger.py

# regression tests
python -m pytest tests/test_opportunity.py tests/test_overnight_panel.py -q
```

Determinism: every random control is seeded (`31337` gating, `90210` scale control, `7717`
prior study). Re-running reproduces the tables exactly.

---

## 15. Data coverage

| store | span | sessions | used for |
|---|---|---|---|
| `data/futures/ES,NQ.parquet` | 2025-06-09 … 2026-09-10 | 312 | all futures phases |
| `data/futures/MES,MNQ.parquet` | 2025-09-08 … 2026-09-10 | 251 | all futures phases |
| `data/minute_alpaca/SPY,QQQ.parquet` | 2016-01-04 … 2026-09-10 | 2,687 | OPP-4 confirmation, Phase 6 |
| `data/minute_alpaca/IWM,DIA.parquet` | 2016-01-04 … 2026-09-10 | 2,687 | Phase 5 cross-market |

**Not available:** RTY / M2K futures. The brief's ES-vs-RTY and NQ-vs-RTY pairs were tested via
IWM on the ETF panel instead.

**Session window:** 09:30–16:00 ET, ten minutes inside the Topstep 15:10 CT (16:10 ET) flatten.
Note this differs from the shared loader's default of 09:30–15:45; the constant is overridden
locally in the gating scripts because golden fixtures pin 376 bars. **This is a live
inconsistency in the repo** — `scripts/futures_discover.py:53` still defaults to the truncated
window, and any study using it without overriding discards the heaviest quarter-hour of the
session.

Minimum detectable correlation: **0.111** (futures, n=312), **0.124** (micros, n=251),
**0.038** (ETF, n=2,662).

---

## 16. Provenance

**Git:** HEAD `4141e88`, matching `origin/main`. **No commit, no push, no pull, no fetch was
performed by this session.** All work is left uncommitted in the working tree for human review.

*(Note carried from the prior session: HEAD moved `d899460` → `4141e88` at 11:02:28 with the
message "srfgrws" without any git write command being issued here — the same signature as the
incident in `docs/GIT_PUSH_INCIDENT.md`.)*

**Config:** `dry_run=True`, `live_trading_enabled=False`, `execution_enabled=False`,
`order_transmission_enabled=False` — verified unchanged at the end of the session.

**Network:** zero ProjectX calls. No order-placement endpoint was reached. All data read from
local parquet stores.

**Secrets:** `live/secrets.env` untouched; no credential read, printed, or logged.

**Tests:** full suite green; 25 new regression tests in `tests/test_opportunity.py` pinning
causality by perturbation, the positive finding, and — deliberately, at equal strength — the
nulls.

**New artifacts:** `research/opportunity_panel.parquet`, `opportunity_model.csv`,
`conditional_direction.csv`, `cross_market.csv`, `opening_transition.csv`,
`opportunity_gating.csv`, `gating_scale_control.csv`, `opportunity_economics.csv`,
`opportunity_robustness.csv`, `hypotheses.jsonl`; 356 rows appended to
`experiments_futures.jsonl`.
