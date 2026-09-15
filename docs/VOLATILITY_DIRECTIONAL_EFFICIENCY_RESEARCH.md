# Volatility × Directional Efficiency

**Core question.** Can a second variable, available before the trade decision, separate
"high expected volatility + high directional efficiency" from "high expected volatility + low
directional efficiency"?

**Answer: NO.** Comprehensively, and with the machinery demonstrably capable of detecting a
signal if one existed.

Date: 2026-09-14 · No commits, no pushes, no ProjectX calls, no credentials touched.

---

## 1. Executive conclusion

Four independent lines of evidence, each capable of producing a positive result, all negative:

| test | result |
|---|---|
| **Is high forecast volatility a mixture?** | **No.** Efficiency's standard deviation is flat across every forecast-volatility quintile on all 8 instruments — sd(Q5)/sd(Q1) runs 0.948–1.011; IQR flat; bimodality at chance. There is nothing to separate. |
| **Does any second variable predict efficiency?** | **No.** 4,788 window-matched tests. 69 clear Bonferroni in the search window; **0 replicate** in the holdout. Overnight 0/924, opening 0/840, prior-RTH 0/3,024. |
| **Does conditioning on volatility rescue a weak variable?** | **No.** 0 weak main effects rescued. Interactions beat their own main effect 51% of the time — exactly chance. |
| **Is the relationship non-monotone (inverted-U)?** | **No.** Curvature is negative in 18/24 search cells and **flips sign in the holdout in 15 of them**. 0 of 24 pass all three criteria. |

**The two results that nearly became the headline were both artifacts** — and both replicated
out-of-sample on all four ETFs at |t| up to 20. That is the most transferable lesson in this
report: **out-of-sample replication protects against overfitting, not against a predictor that
contains its own answer.** A leak replicates perfectly.

**The pipeline is not broken.** A positive control detects an injected signal down to
ρ ≈ 0.054 (t = 2.80) — the theoretical limit for n = 2,600. A shuffle control returns a 5.8%
false-positive rate against a 5.0% nominal expectation, and 0.00% at the Bonferroni bar. The
nulls are real nulls.

**What survives is structural, not predictive.** Median `eff_vol` — net displacement over the
random-walk expectation σ√n — is **0.655 to 0.738 on all eight instruments across both panels
and eleven years**. Intraday index sessions displace *less* than a random walk. That is the
mechanical reason directional mechanisms are hard on this asset class, and it is not something
a second variable was ever going to fix.

---

## 2. Definitions of directional efficiency (Phase 1)

All five computed, all five reported, none chosen for its backtest.

| definition | formula | median (ETF / futures) |
|---|---|---|
| `eff_range` | \|close−open\| / (high−low) | 0.467–0.490 / 0.453–0.477 |
| `eff_path` | \|close−open\| / Σ\|Δclose\| | 0.046–0.051 / 0.044–0.049 |
| `eff_vol` | \|close−open\| / (σ√n) | 0.669–0.738 / 0.655–0.693 |
| `eff_mfe` | max(high−open, open−low) / range | 0.783–0.792 / 0.782–0.797 |
| `cost_opp_usd` | MFE in dollars − one round turn | $198–290 / $239–4,544 |

**They are not five independent choices.** Spearman correlations: `eff_range`, `eff_path` and
`eff_vol` sit at **0.948–0.998** with each other — one target under three names. `eff_mfe` is
distinct (0.53–0.61), `cost_opp_usd` more so (0.19–0.43). So the effective researcher degree
of freedom is 3, not 5, which lowers the multiplicity burden rather than raising it.

**`cost_opp_usd` is flagged wherever it appears.** It is not scale-free: it grows with the size
of the day whatever the shape. The volatility forecast "predicts" it at ρ ≈ 0.6, t ≈ 38. That
says big days are big. It is not an efficiency result and is never treated as one.

---

## 3. Volatility-state analysis (Phase 2)

The forecast itself works on both panels — OOS R² for path: ETF **0.650–0.719**, futures
0.455–0.507. (The ETF forecast is stronger because it has ten years of training history.)

**Continuous test first**, as the brief asks. Rank correlation of the forecast against each
efficiency target:

| panel | eff_range | eff_vol | eff_mfe |
|---|---|---|---|
| SPY | +0.054 (2.8) | +0.060 (3.1) | −0.032 (−1.6) |
| QQQ | +0.065 (3.3) | +0.057 (2.9) | −0.032 (−1.6) |
| ES | +0.002 (0.0) | +0.014 (0.2) | −0.089 (−1.4) |
| NQ | −0.030 (−0.5) | −0.017 (−0.3) | −0.128 (−2.0) |

Nominally significant on two ETFs at ρ ≈ 0.06 — economically nothing, and the *opposite* sign
on futures.

### The mixture test

A mixture of trend days and chop days must show a rising spread. It does not:

| panel | sym | sd Q1 | sd Q5 | sd trend | reading |
|---|---|---|---|---|---|
| ETF | SPY | 0.262 | 0.255 | −0.52 | no mixture |
| ETF | QQQ | 0.265 | 0.262 | −0.16 | no mixture |
| ETF | IWM | 0.257 | 0.256 | +0.08 | no mixture |
| ETF | DIA | 0.262 | 0.262 | −0.41 | no mixture |
| FUT | ES | 0.258 | 0.245 | −0.62 | no mixture |
| FUT | MES | 0.251 | 0.246 | −0.57 | no mixture |
| FUT | MNQ | 0.235 | 0.234 | −0.11 | no mixture |
| FUT | NQ | 0.251 | 0.253 | — | no mixture |

Bimodality: a matched unimodal (normal) reference has a median dip ratio of 0.611 and a 5th
percentile of 0.456. Observed cells: median 0.574, and **2 of 20 below the unimodal 5th
percentile** — which is what chance gives.

**High forecast volatility is not a mixture. It is the same distribution, shifted a hair.**

---

## 4. Candidate second-variable results (Phase 3)

~30 candidates × 3 targets × 8 instruments × {main, interaction}, split 70% search / 30%
holdout. **4,788 window-matched tests, Bonferroni |t| > 4.40.**

| predictor family | tests | nominal \|t\|>1.96 | expected | Bonferroni | **replicating** |
|---|---|---|---|---|---|
| opening | 840 | 118 | 42 | 2 | **0** |
| overnight | 924 | 21 | 46 | 0 | **0** |
| prior RTH | 3,024 | 764 | 151 | 67 | **0** |

The prior-RTH family's 764 nominal hits against 151 expected is volatility clustering showing
through — and **none of it survives the holdout**. The strongest candidate, `prev_rv_pct` →
`rest15_eff_vol`, runs ρ = +0.127 (t = 5.54) in search and **+0.007 (t = 0.19)** in the holdout.

Overnight's 21 hits against 46 expected is *below* chance.

---

## 5. Interaction results (Phase 4)

- Interaction beats its own main effect in **986 of 1,928 pairs (51%)** — precisely chance.
- Weak main effects (|t| < 1.96) rescued to above-Bonferroni by conditioning on the volatility
  forecast: **0**.

Conditioning on expected volatility does not make a weak variable informative.

---

## 6. Path-shape analysis (Phase 5)

What high-forecast-volatility days actually are, by quintile (pooled):

**ETF** — flat. Turns 10.0 → 11.0, trend-day share 23.3% → 27.1%, chop share 31.8% → 33.8%,
max-run/range constant at ~0.71.

**FUTURES** — the top quintile is measurably the worst:

| quintile | turns | eff_range | eff_vol | trend % | chop % |
|---|---|---|---|---|---|
| 1 | 10.50 | 0.434 | 0.602 | 24.0% | 40.0% |
| 2 | 9.00 | **0.536** | **0.836** | **33.6%** | 26.8% |
| 3 | 9.12 | 0.514 | 0.824 | 25.5% | 27.0% |
| 4 | 10.00 | 0.483 | 0.716 | 24.3% | 32.5% |
| 5 | **11.38** | **0.394** | **0.503** | 23.5% | **44.1%** |

The highest-forecast-volatility quintile has the most direction changes, the lowest efficiency,
and the highest chop share. **High expected volatility means a choppier session, not a more
directional one** — the mechanism behind the whole programme's difficulty.

### The inverted-U, tested and rejected

Both panels show a rise-then-fall that a rank correlation is blind to. Tested with three
pre-stated criteria — negative curvature significant in both halves, stable peak location, and
beating a straight line out of sample:

| criterion | result |
|---|---|
| negative curvature in search | 18 of 24 |
| negative in **both** halves | 3 of 24 |
| significant and negative in both | **0** |
| quadratic beats a line out of sample | 5 of 24 |
| **passing all three** | **0** |

Curvature flips sign out of sample in 15 of the 18. The shape is search-window overfit.

---

## 7. Opening-transition results (Phase 8)

This is where the two artifacts were caught, and they are the most instructive part of the study.

### Artifact 1 — an accounting identity

`open30_absret_pct` → `eff_mfe`: ρ = **+0.235 to +0.357**, t = 12.5 to 19.7, replicating on all
four ETFs and in the holdout. It would have been the headline.

`eff_mfe` is measured over the **whole session**, which *contains* the first thirty minutes. A
large opening move is literally part of the maximum favourable excursion it appears to predict.

Measured on the session **after** minute 30:

| | SPY | QQQ | IWM | DIA |
|---|---|---|---|---|
| whole-session `eff_mfe` | +0.235 (12.5) | +0.357 (19.7) | +0.340 (18.6) | +0.289 (15.3) |
| **remainder only** | **+0.010 (0.53)** | **+0.028 (1.47)** | **−0.023 (−1.18)** | **+0.015 (0.77)** |

The quintile table shows it directly: whole-session `eff_mfe` climbs 0.748 → 0.883 across
opening-move quintiles while remainder `eff_mfe` stays flat at 0.770–0.797.

### Artifact 2 — a look-ahead

`open{W}_vol_share` → `rest{W}_eff_*`: ρ = −0.116 to −0.185, t = −5.9 to −9.7, replicating on
all four ETFs at all four windows, with a plausible story attached ("front-loaded volume means
the news was priced at the open").

The share divides by the **day's total volume**, which is not known at minute *W*. It encodes
the rest of the session: correlation of the leaky share with rest-of-day volume is **−0.249
(t = −13.3)**.

Replaced with a causal ratio (opening volume ÷ its own trailing 20-day mean):

| | SPY | QQQ | IWM | DIA |
|---|---|---|---|---|
| leaky share (t) | −9.71 | −8.96 | −7.57 | −7.90 |
| **causal ratio (t)** | **−0.30** | **−0.31** | **+0.24** | **+0.55** |

### After both fixes

With window-matching enforced in code (`overlaps()`, unit-tested), the opening family gives
**0 of 840 replicating**. There is no opening-transition signal for directional efficiency.

---

## 8. Strategy-family conditioning (Phase 6)

Deliberately compact. The baseline and volatility-gated arms already exist in
`research/opportunity_gating.csv` (120 cells, 30 mechanisms, regime-matched and
scale-normalised controls). **The third arm cannot honestly be built**: no second variable
passed Phase 3, and the brief's two-stage rule forbids letting an unvalidated gate touch
strategy economics.

So one focused experiment closes the loop — build the gate from the candidate a researcher who
*skipped the holdout* would have chosen (`prev_rv_pct`, search t = +5.54, holdout t = +0.19),
across 3 representative mechanisms × 4 instruments:

| symbol | mechanism | baseline | vol-gated | vol + prev_rv_pct |
|---|---|---|---|---|
| ES | trend.ret_30.q80 | −18.54 | −12.90 | −13.80 |
| ES | breakout.range_expansion.q80 | −16.23 | −4.93 | −6.97 |
| ES | revert.vwap.q90 | −1.30 | 1.22 | 4.62 |
| NQ | trend.ret_30.q80 | −14.02 | −2.40 | −2.87 |
| NQ | revert.vwap.q90 | **25.54** | 12.73 | 16.50 |
| MNQ | breakout.range_expansion.q80 | −1.30 | 1.70 | 2.82 |

*($/trade, 1 contract)*

- vol+second arm beating its regime-matched control p95: **1 of 12** (0.6 expected by chance).
- On NQ `revert.vwap.q90` the conditioning actively **hurts** (25.54 → 16.50).

The null propagates. Adding an unvalidated second variable does nothing a random gate does not.

---

## 9. Random, shuffle and time-shift controls (Phase 7)

| control | purpose | result |
|---|---|---|
| **positive** | can the pipeline find anything? | Detects injected signals at ρ = 0.705, 0.292, 0.131 and **0.054 (t = 2.80)**; loses one at ρ ≈ 0. **The machinery works.** |
| **shuffle** | empirical false-positive rate | 1,500 permuted tests: **5.8%** at \|t\|>1.96 (5.0% nominal), **0.00%** at the Bonferroni bar. Correctly calibrated. |
| **regime-matched random gates** | is an improvement just trading less? | 1 of 12 beats p95 (0.6 expected). |
| **time-shift** | is it autocorrelation, not information? | See below. |

**The time-shift control needs interpreting rather than quoting.** Shifting `fc_vol` *forward*
one session gives t = +10.68 and +14.85 — far above the real alignment's +2.77 and +2.86. That
is not a defect in the analysis; it is the control firing correctly. Tomorrow's forecast is
built from `prev_rth_rv`, which *is* today's realised volatility, so a forward shift
manufactures a leak. It confirms the control is sensitive to exactly the thing it is meant to
catch.

The informative rows are `prev_rv_pct` and `trail_rv_20`, where shifted ≈ real (3.27 vs 3.27,
4.29 vs 4.26). Their relationship with efficiency is **not specific to the day's alignment** —
it is a slow-moving level effect, i.e. autocorrelation rather than a day-specific signal.

---

## 10. Cost analysis (Phase 9)

$/trade under a slippage ladder, on the vol+second-variable arm:

| symbol | mechanism | 0 ticks | 0.5 | 1.0 | 2.0 |
|---|---|---|---|---|---|
| ES | revert.vwap.q90 | 4.62 | −1.63 | −7.88 | −20.38 |
| ES | trend.ret_30.q80 | −13.80 | −20.05 | −26.30 | −38.80 |
| MES | revert.vwap.q90 | 0.50 | −0.12 | −0.75 | −2.00 |
| MNQ | breakout.range_expansion.q80 | 2.82 | 2.57 | 2.32 | 1.82 |
| NQ | revert.vwap.q90 | 16.50 | 14.00 | 11.50 | 6.50 |

**Break-even slippage:**

| symbol | mechanism | breaks even at |
|---|---|---|
| ES | revert.vwap.q90 | **0.37 ticks** ($12.50/tick) |
| MES | revert.vwap.q90 | **0.40 ticks** ($1.25/tick) |
| NQ | breakout.range_expansion.q80 | 2.83 ticks ($5.00/tick) |
| MNQ | revert.vwap.q90 | 5.85 ticks ($0.50/tick) |

The ES and MES cells die below half a tick — under any realistic execution assumption. The
NQ/MNQ cells tolerate more, and they are also the noisiest cells in the grid (per-session
t < 1.2, from the previous phase's accounting).

---

## 11. Topstep feasibility

**No Combine simulation was run.** The brief is explicit: *"Do not run Combine pass simulations
unless a strategy first establishes genuine positive expected value."* Nothing did. The
prerequisite from the previous phase still stands — 0 of 240 evaluations clear the multiplicity
bar, and no positive cell reaches even a nominal 1.96.

Constraints that would apply, unchanged and verified: $3,000 target, $2,000 trailing MLL tested
intraday, $1,000 DLL under RTP, 5 minis / 50 micros, mandatory flat 15:10 CT (16:10 ET), and
the eligible session window 09:30–16:00 ET used throughout.

---

## 12. Regime robustness

The nulls hold in every partition examined. The one positive (EFF-7, the structural fact) is
robust by construction:

| | |
|---|---|
| instruments | 8 (4 futures, 4 ETF) |
| span | 2016-01-05 … 2026-09-11 (ETF), 2025-06-09 … 2026-09-10 (futures) |
| median `eff_vol` | **0.655 – 0.738**, below 1.0 on every one |
| by volatility quintile | below 1.0 in every cell of both panels |

The efficiency *spread* is flat across volatility quintiles, trend regimes, and both halves —
which is precisely why no separator exists.

---

## 13. Multiple-testing accounting (Phase 10)

**Records written this study: 5,016**, of which 4,788 are individual search tests, all appended
to `research/experiments_futures.jsonl` under `futures.directional_efficiency.v1`.

Cumulative ledger state: **6,008 rows** in `research/experiments_futures.jsonl` — 4,788 from this study, 356 from the conditional-opportunity study, 46 from the overnight study, and 818 pre-existing. Counting the tests that were tallied but not individually rowed (quintile cells, path-shape cells, cost ladders), this study spent **5,016** and the three together spent roughly **5,560** on top of the pre-existing 818.

| ID | claim | stage | result-driven | eff. trials |
|---|---|---|---|---|
| EFF-7 | intraday sessions displace less than a random walk | **ROBUSTNESS** | no | 1 |
| EFF-1 | high forecast vol is a mixture | REJECTED | no | 1 |
| EFF-2 | a second variable predicts efficiency | REJECTED | no | 1 |
| EFF-3 | conditioning rescues a weak variable | REJECTED | no | 1 |
| EFF-4 | efficiency is an inverted-U in forecast vol | REJECTED | **yes** | 2 |
| EFF-5 | opening move predicts excursion efficiency | REJECTED (**artifact**) | **yes** | 2 |
| EFF-6 | opening volume share predicts remainder efficiency | REJECTED (**artifact**) | **yes** | 2 |
| EFF-8 | vol+second gate improves economics | REJECTED | **yes** | 2 |

**Nothing reached VALIDATION or CONFIRMATION.** EFF-7 is descriptive, not predictive, so it has
no path upward.

**Holdout hygiene.** The ETF panel's last 30% was used as the holdout for the Phase 3 search and
is now spent for that question. It had already been touched once (the OPP-4 bucket test). Any
future directional work on it must treat it as inspected, not pristine.

---

## 14. Failed hypotheses — preserved

1. **High forecast volatility is a mixture** — spread flat on all 8 instruments.
2. **A second variable predicts efficiency** — 0 of 4,788 replicate.
3. **Conditioning rescues a weak variable** — 0 rescued; interactions win at exactly chance.
4. **Inverted-U in forecast volatility** — curvature flips sign out of sample in 15 of 18.
5. **Opening move → excursion efficiency** — *artifact*, accounting identity.
6. **Opening volume share → remainder efficiency** — *artifact*, look-ahead in the denominator.
7. **vol+second-variable gate improves economics** — 1 of 12 beats control, 0.6 expected.
8. Carried forward, still preserved: overnight direction null; quiet-overnight random-gate
   failure; the overnight-drift calendar artifact; the high-volatility gate's lack of
   directional profitability; conditional directional nulls; improvements explained by lower
   trade frequency; results destroyed by realistic slippage.

### Defects found and fixed in this study's own code

- **Turn counter returned zero for every session.** With `direction == 0`, both the up- and
  down-tracking branches updated a single running extreme, so it followed the latest price and
  no retracement ever confirmed. The giveaway was `max_run_pts` collapsing to exactly
  \|close−open\|. Rewritten as a zig-zag with separate high/low tracking and unit-tested on
  four synthetic paths.
- **My own Phase-2-to-Phase-3 ordering was right and worth keeping**: testing for the mixture
  *before* hunting a separator is what made the negative cheap.

---

## 15. Surviving hypotheses

### EFF-7 — intraday sessions displace less than a random walk · ROBUSTNESS

| | |
|---|---|
| hypothesis | median \|net move\| ÷ σ√n is below 1.0 on every index instrument |
| sample | 2,576–2,662 sessions per ETF; 251–312 per futures contract |
| instruments | SPY, QQQ, IWM, DIA, ES, NQ, MES, MNQ |
| period | 2016-01-05 … 2026-09-11 (ETF); 2025-06-09 … 2026-09-10 (futures) |
| effect size | median `eff_vol` **0.655 – 0.738** |
| stability | below 1.0 in every volatility quintile of both panels |
| statistic | descriptive; not a predictive claim, so no t is quoted |
| cost-adjusted | n/a |
| control results | n/a — it is a property of the data, not a gate |
| genealogy | `EFF-7`, ROBUSTNESS, effective trials 1 |
| **status** | **structural fact, not a tradable edge** |

This is the only thing to carry forward, and what it says is negative in implication: a
mechanism paid for displacement is fighting the asset class's own arithmetic.

**There are no other surviving hypotheses.**

---

## 16. Recommended next research

1. **Stop looking for a directional signal in this data.** Three studies, ~5,560 recorded
   trials on 251–2,662 sessions, and every directional avenue has closed: unconditional, conditional, cross-market,
   opening-transition, volatility-conditioned, and now efficiency-conditioned. The remaining
   probability mass is not in a variable nobody has tried; it is in data nobody has.
2. **Take EFF-7 seriously as a design constraint.** `eff_vol` < 1 means mean-reversion is the
   asset class's default. Every mechanism in the library is displacement-paid. A *path*-paid
   mechanism — one that profits from traverse rather than displacement, with a hard stop — is
   the untested category, and the volatility forecast (OOS R² ≈ 0.5–0.72) is exactly the right
   input for sizing it. This is the one place the validated forecast has a job.
3. **Use the volatility forecast for risk, which is what it is good at.** Volatility-scaled
   sizing against fixed sizing at matched average contract-days. Still untested; still free.
4. **If directional work continues, it needs new data**, not new hypotheses: a different asset
   class, or order-book/tick data this repo does not hold.

---

## 17. Reproducibility commands

```bash
# Phase 1 - the efficiency panel (both stores)
python scripts/efficiency_panel.py

# Phase 2 - volatility state and the mixture test
python scripts/efficiency_volatility.py

# Phases 3, 4, 8 - the search. Run the CLEAN one; the first is kept only to
# document the overlap artefact it produced.
python scripts/efficiency_search.py            # artefact-producing version
python scripts/efficiency_search_clean.py      # window-matched, the real result

# Phases 5 and 7 - path shape, positive/shuffle/time-shift controls
python scripts/efficiency_pathshape.py

# the non-monotone alternative
python scripts/efficiency_nonlinear.py

# Phases 6 and 9 - arm comparison and the slippage ladder
python scripts/efficiency_families.py

# Phase 10 - ledgers (appends; run once)
python scripts/efficiency_ledger.py

# regression tests
python -m pytest tests/test_efficiency.py -q
```

Seeds: 4242 (dip reference), 5150 (positive/shuffle controls), 80808 (Phase 6 controls),
31337 / 90210 (prior phases). Re-running reproduces every table.

---

## 18. Data coverage

| store | span | sessions | role |
|---|---|---|---|
| `data/minute_alpaca/SPY,QQQ,IWM,DIA` | 2016-01-05 … 2026-09-11 | 2,576–2,662 each | primary; carries the power |
| `data/futures/ES,NQ` | 2025-06-09 … 2026-09-10 | 312 | confirmation |
| `data/futures/MES,MNQ` | 2025-09-08 … 2026-09-10 | 251 | confirmation |

Minimum detectable ρ: **0.038** (ETF, n≈2,600), **0.111** (ES/NQ), **0.124** (micros).

Session window 09:30–16:00 ET throughout, ten minutes inside the 16:10 ET flatten. **The shared
loader `scripts/futures_discover.py:53` still defaults to 15:45 and is still wrong**; it is
overridden locally in every script that touches it, because golden fixtures pin 376 bars.

Not available: RTY/M2K futures (IWM substitutes on the ETF panel); order-book or tick data.

---

## 19. Provenance

**Git:** HEAD `4141e88`, matching `origin/main`. **No commit, no push, no pull, no fetch.** All
work left uncommitted for review.

**Config:** `dry_run=True`, `live_trading_enabled=False`, `execution_enabled=False`,
`order_transmission_enabled=False` — verified at completion.

**Network:** zero ProjectX calls; no order-placement endpoint referenced in any new module. All
data read from local parquet.

**Secrets:** `live/secrets.env` untouched.

**Tests:** 21 new in `tests/test_efficiency.py`, including both artifacts pinned from *both*
sides (the identity must persist; the corrected version must stay null), the turn-counter fix
on synthetic paths, and the positive control as a test. Full suite green.

**New artifacts:** `research/efficiency_etf.parquet`, `efficiency_futures.parquet`,
`efficiency_volatility.csv`, `efficiency_spread.csv`, `efficiency_search.csv`,
`efficiency_search_clean.csv`, `efficiency_pathshape.csv`, `efficiency_nonlinear.csv`,
`efficiency_families.csv`, `efficiency_costs.csv`; 4,788 rows appended to
`experiments_futures.jsonl`; 8 hypotheses in `hypotheses.jsonl`.
