# Failed-Reversal Replication & Falsification

**Question.** Is the failed-reversal effect a repeatable market phenomenon, or a 343-trade
sample artifact?

## VERDICT: **A. REJECT**

The effect does not replicate. On **QQQ — the same index as MNQ, over the exact same dates —
the sign is opposite.**

Rule hash `8ed5bb73283cb506` · Date: 2026-09-14 · Replication/falsification only ·
No commits, no pushes, no ProjectX calls.

Plots: `docs/research/strategy_results/failed_reversal_replication/`

---

## 1. The frozen hypothesis

Transcribed verbatim from `scripts/strategy_tournament.py:230-237`, hashed, and verified
against the live implementation by behavioural equivalence on a synthetic frame.

```python
live = mins > 45
prev = np.concatenate(([0.0], orp[:-1]))
long  = live & (prev > q95) & (orp < q95)
short = live & (prev < q05) & (orp > q05)
```

**A correction to how this was described in the previous phase.** The exit study called it a
mechanism that "fades a failed move." That is backwards. The rule takes a position **in the
same direction as the original breakout**: an upside extension that pulls back below the 95th
percentile produces a **LONG**. The bet is that the *retracement* fails and the breakout
resumes. The name says so; the earlier prose did not.

The claim being replicated, in one sentence: *after a strong intraday extension retraces past
its own 95th-percentile opening-range level, the retracement fails more often than it
continues, over the next one to five minutes.*

### The one real ambiguity, documented rather than silently resolved

`q95`/`q05` are quantiles of the instrument's **own** train split, so the numeric threshold
differs per instrument. Two readings:

- **(a)** the rule is "the 95th percentile of this instrument's distribution" → recalibrate the
  same quantile level everywhere
- **(b)** the rule is MNQ's numeric threshold → transplant it unchanged

**(a) is primary**, because the quantile level is what was written down, and transplanting a
raw `opening_range_pos` value across instruments of different volatility applies a *different*
rule. The quantile levels, 45-minute warm-up, train fraction and direction convention are
identical everywhere and never re-fitted. Realised thresholds ranged +1.900/−1.435 (MNQ) to
+2.400/−1.440 (SPY) — close enough that the reading barely matters.

---

## 2. What the data can and cannot support — stated before results

| asked for | reality |
|---|---|
| M2K, RTY, MYM, YM | **DO NOT EXIST** in this repository. The `f1/*.dirty.parquet` hits are equity panels from an unrelated archive with no minute bars |
| 2018–2024 period replication on futures | **IMPOSSIBLE.** The futures store begins **2025-06-08**. Any such result would be fabricated |
| "four instruments" | **Two markets.** ES/MES are the same index; NQ/MNQ are the same index |

So the futures store supplies at most **one** independent cross-market comparison and **zero**
independent history.

**Where a real falsification test comes from:** the ETF minute stores — SPY, QQQ, IWM, DIA,
2016-01 → 2026-09, ~2,600 sessions each. The frozen rule needs only `opening_range_pos` and
`minutes_from_open`, both computable from OHLCV bars, so the identical rule runs unchanged.
That supplies four more instruments (two tracking indices the futures store does not cover),
eight calendar years never inspected for this rule, and ~30× the sessions.

### Contamination, stated plainly

| window | status |
|---|---|
| futures 2025-06 → 2026-09 | **CONTAMINATED.** Inspected in five prior phases, including the one that generated this hypothesis. Not a holdout and not described as one |
| ETF 2016-01 → 2023-12 | **CLEAN.** Never touched for this mechanism. The legitimate holdout |
| ETF 2024-01 → 2026-09 | Partially touched — one preregistered bucket test in an earlier phase, different question |

The split is the reverse of the brief's suggestion, deliberately: the hypothesis was generated
on 2025–26, so the *earlier* years are what could not have influenced it.

---

## 3. Cross-instrument replication (Phase 2)

Signed 1-bar forward return, $ per unit, with matched-control percentile:

| panel | sym | entries | 1b | t | 3b | 5b | 10b | ctl%1b | verdict |
|---|---|---|---|---|---|---|---|---|---|
| futures | **MNQ** | 343 | **+3.203** | +2.5 | +4.341 | +6.240 | +1.879 | **99.0%** | REPLICATES |
| futures | NQ | 470 | +14.426 | +1.5 | +35.736 | +64.805 | +58.799 | 89.5% | REPLICATES |
| futures | MES | 449 | +0.062 | +0.1 | +0.474 | +0.916 | −0.490 | 50.0% | MARGINAL |
| futures | ES | 364 | +4.006 | +0.6 | +1.761 | +5.041 | +14.848 | 77.5% | MARGINAL |
| etf | SPY | 4,395 | +0.465 | +1.6 | −0.065 | −0.150 | −0.140 | 95.5% | FAILS |
| etf | **QQQ** | 4,124 | **−0.668** | **−2.2** | −0.777 | −1.561 | −2.365 | **0.5%** | FAILS |
| etf | IWM | 3,719 | −0.057 | −0.3 | −0.245 | +0.039 | −0.743 | 37.0% | FAILS |
| etf | DIA | 3,912 | +0.260 | +1.1 | +0.112 | +0.628 | +0.598 | 92.5% | MARGINAL |

NQ "replicating" is not independent evidence — it is the same index as MNQ in a larger
contract.

**QQQ is the falsification.** Same index as MNQ. Twelve times the entries. **Opposite sign,
and significant**: t = −2.2 at 1 bar, sitting at the **0.5th percentile** of matched controls
— worse than 99.5% of random draws.

---

## 4. The decisive test: period effect or artifact? (Phase 4)

Only two explanations survive that contradiction. Either the mechanism is real in 2025–26 and
absent earlier (a **period** effect), in which case QQQ restricted to those dates must agree
with MNQ — or the MNQ result is an **artifact** of 343 entries, in which case QQQ still
disagrees.

| series | entries | 1b | t | 3b | 5b | ctl%1b |
|---|---|---|---|---|---|---|
| **MNQ** 2025-06 … 2026-09 | 343 | **+3.203** | +2.48 | **+4.341** | **+6.240** | **99.3%** |
| **QQQ** 2025-06 … 2026-09 | 451 | **−0.799** | −0.55 | **−3.040** | **−3.786** | **15.3%** |
| QQQ 2016–2023 (clean holdout) | 3,031 | −0.331 | −1.17 | +0.324 | +0.373 | 20.7% |
| QQQ 2024–2026 | 1,093 | −1.602 | −1.90 | −3.829 | −6.921 | 0.7% |
| SPY 2025-06 … 2026-09 | 478 | +2.426 | +2.51 | +0.721 | +0.822 | 100.0% |
| SPY 2016–2023 (clean holdout) | 3,242 | +0.378 | +1.32 | +0.473 | +0.658 | 95.3% |
| ES 2025-06 … 2026-09 | 364 | +4.006 | +0.65 | +1.761 | +5.041 | 82.7% |
| MES 2025-06 … 2026-09 | 449 | +0.062 | +0.12 | +0.474 | +0.916 | 47.3% |

**Same index, same dates, comparable samples (451 vs 343), opposite sign at all three short
horizons.** It is not a period effect. **The MNQ result does not describe the Nasdaq.**

The S&P side is weakly positive (SPY +0.378 at t = 1.32 over the clean holdout, percentile
95.3%), but it fails the shape test — see §6 — and MES, the instrument that should agree with
SPY most closely, is at the 47.3rd percentile, i.e. exactly chance.

---

## 5. Calendar-period replication (Phase 3)

ETF panel, per instrument-year. Futures years do not exist.

Across **52 instrument-years, 3 classify as REPLICATES** — SPY 2022, DIA 2018 and MNQ 2026.
Two of the three sit at t = 1.56 and t = 0.18; only MNQ 2026 (t = 1.83) is the mechanism's
own contaminated window. That is what chance gives at this cell count.

| instrument | REPLICATES | MARGINAL | FAILS |
|---|---|---|---|
| SPY | 1 (2022) | 4 | 6 |
| QQQ | **0** | 5 | 6 |
| IWM | **0** | 7 | 4 |
| DIA | 1 (2018) | 3 | 7 |
| MNQ | 1 (2026, contaminated) | 1 | 0 |
| NQ | 0 | 2 | 0 |
| MES | 0 | 1 | 1 |
| ES | 0 | 2 | 0 |

QQQ never replicates in any of its eleven years. Its last four run −0.413, −1.590, −1.221,
−2.376.

---

## 6. Short-horizon decay (Phase 6)

The claimed shape is a rise through 1→3→5 bars decaying by ~10.

| panel | sym | 1b | 3b | 5b | 10b | 15b | 30b | shape |
|---|---|---|---|---|---|---|---|---|
| futures | MNQ | 3.203 | 4.341 | 6.240 | 1.879 | 2.587 | 7.179 | consistent |
| futures | NQ | 14.43 | 35.74 | 64.81 | 58.80 | 62.75 | 70.58 | **NOT the claimed shape** — rises to 30b |
| futures | MES | 0.062 | 0.474 | 0.916 | −0.490 | −0.953 | −2.971 | consistent |
| futures | ES | 4.006 | 1.761 | 5.041 | 14.85 | 21.10 | 38.67 | **NOT** — rises to 30b |
| etf | SPY | 0.465 | −0.065 | −0.150 | −0.140 | 0.563 | 0.918 | **NOT** |
| etf | QQQ | −0.668 | −0.777 | −1.561 | −2.365 | −3.110 | −3.437 | monotonically negative |
| etf | IWM | −0.057 | −0.245 | 0.039 | −0.743 | −0.625 | −0.709 | negative |
| etf | DIA | 0.260 | 0.112 | 0.628 | 0.598 | 0.556 | −1.340 | flat |

**The decay shape does not replicate.** Only MNQ and MES show it. NQ and ES keep *rising* to 30
bars — a completely different mechanism from the one claimed. SPY is flat-to-negative through
the short horizons and rises later.

A shape that behaves oppositely on the same index (MNQ vs NQ both Nasdaq; ES vs MES both S&P)
is not a mechanism.

---

## 7. Controls (Phase 5)

**Matched control** — bar-of-session and direction, 200 replications: reported in §3. MNQ
99.0%; QQQ 0.5%.

**Negative control (shuffled direction labels)** — the same entry bars with direction permuted:

| panel | sym | real 1b | shuffled median | real percentile |
|---|---|---|---|---|
| futures | MNQ | 3.203 | 0.058 | 97.0% |
| futures | NQ | 14.426 | −0.441 | 95.0% |
| futures | MES | 0.062 | −0.033 | 53.0% |
| futures | ES | 4.006 | 0.298 | 79.0% |
| etf | SPY | 0.465 | −0.034 | 96.0% |
| etf | **QQQ** | −0.668 | 0.025 | **0.0%** |
| etf | IWM | −0.057 | 0.027 | 34.0% |
| etf | DIA | 0.260 | 0.017 | 92.0% |

The shuffle correctly collapses every series to ~0, confirming the control machinery works.

**Positive control** — carried over from the previous phase's verified pipeline, which detects
an injected signal down to ρ ≈ 0.054 (t = 2.80) at n = 2,600 and returns a 5.8% false-positive
rate against a 5.0% nominal. The pipeline can find a small real effect; it is not finding one
here.

---

## 8. Economic friction gate (Phase 7) — mandatory

Repository fee model (`execution_sim.CostModel`), not generic costs. Net $/trade:

| panel | sym | gross | 0t | 0.25t | 0.5t | **1t** | 2t | classification |
|---|---|---|---|---|---|---|---|---|
| futures | MNQ | +3.203 | +1.483 | +1.358 | +1.233 | **+0.983** | +0.483 | **MARGINAL AFTER COSTS** |
| futures | NQ | +14.426 | +0.646 | −0.604 | −1.854 | −4.354 | −9.354 | NEGATIVE |
| futures | MES | +0.062 | −2.408 | −2.721 | −3.033 | −3.658 | −4.908 | NEGATIVE |
| futures | ES | +4.006 | −12.274 | −15.399 | −18.524 | −24.774 | −37.274 | NEGATIVE |
| etf | SPY | +0.465 | −0.535 | −0.785 | −1.035 | −1.535 | −2.535 | NEGATIVE |
| etf | QQQ | −0.668 | −1.668 | −1.918 | −2.168 | −2.668 | −3.668 | NEGATIVE |
| etf | IWM | −0.057 | −1.057 | −1.307 | −1.557 | −2.057 | −3.057 | NEGATIVE |
| etf | DIA | +0.260 | −0.740 | −0.990 | −1.240 | −1.740 | −2.740 | NEGATIVE |

**Seven of eight are NEGATIVE AFTER COSTS at every slippage level.** MNQ alone is marginal.

### On the Phase 16 comparison — two different measurements

Full-sample break-even on MNQ is **2.97 ticks**. Phase 16 reported **1.00 tick**. Both are
correct and they measure different things:

- **this figure**: full sample (343 entries), gross 1-bar forward return minus commission
- **Phase 16**: the out-of-sample half only (104 trades), net through the exit simulator

**The out-of-sample figure is the relevant one**, and it is three times worse. The full-sample
number is inflated by the in-sample half that produced the hypothesis.

---

## 9. Regime and session-bucket robustness (Phases 8, 9) — descriptive only

**Volatility regime**, 1-bar mean, sign consistency across LOW/MID/HIGH:

| panel | sym | LOW | MID | HIGH | signs |
|---|---|---|---|---|---|
| futures | MNQ | 2.875 | 4.401 | 1.801 | AGREE |
| futures | NQ | 17.270 | 1.225 | 32.934 | AGREE |
| futures | ES | 7.723 | 1.894 | −0.171 | **DISAGREE** |
| futures | MES | −0.247 | 0.220 | 0.239 | **DISAGREE** |
| etf | QQQ | −0.172 | −1.336 | −0.509 | AGREE (negative) |
| etf | SPY | −0.036 | 0.640 | 0.725 | **DISAGREE** |
| etf | IWM | −0.166 | 0.466 | −0.390 | **DISAGREE** |
| etf | DIA | 0.503 | −0.058 | 0.327 | **DISAGREE** |

Five of eight flip sign across regimes.

**Session buckets** — the effect is *not* concentrated in one narrow slice, but nor is it
broadly present: positive in 25% of instruments in 10:15–11:00, 62% mid-session, 88% in
14:00–16:00. The futures instruments have no 10:15–11:00 entries at all (the 45-minute warm-up
plus the `opening_range_pos` threshold means the first firing is later).

This is the one robustness dimension the mechanism does not obviously fail — but a signal
whose sign depends on the instrument cannot be rescued by being spread evenly across the day.

---

## 10. Phase 10 — Combine feasibility: **NOT RUN**

The brief gates the digital twin on the replication evidence being "positive enough to justify
this section." It is not. Running a Combine simulation on a rejected hypothesis produces a pass
rate, and a pass rate in a document gets quoted out of context.

The one descriptive number worth recording: MNQ's 1-contract gross maximum drawdown is
**−$132**, or **0.07× the $2,000 MLL**. The mechanism's *risk shape* was always its most
attractive property — and a favourable risk shape around a non-existent edge is not tradable.

---

## 11. Multiple-test accounting (Phase 11)

This was a replication study, not a discovery sweep. Tests preregistered in §1–2 and executed
as specified.

| category | count |
|---|---|
| instruments | 8 (4 futures, 4 ETF) — **2 independent markets on futures, 4 on ETF** |
| sessions | futures 71–90 with entries (of 251–312); ETF 827–990 with entries (of ~2,600) |
| entries analysed | **17,776** total (1,626 futures, 16,150 ETF) |
| confirmatory tests | 8 instruments × 6 horizons = 48 |
| period tests | 52 instrument-years |
| era tests | 15 |
| control replications | 200 matched + 100 shuffled per instrument |
| regime / bucket cells | 24 + 28 (descriptive) |

**Exploratory, and labelled as such:** the observation that the S&P complex is weakly positive
while the Nasdaq complex is negative was noticed *from* these results and is not a
preregistered finding. It cannot be used for promotion. If pursued it needs its own
preregistration and its own holdout.

---

## 12. Promotion gate

| requirement for PAPER CANDIDATE | met? |
|---|---|
| replicates on >1 independent instrument OR clearly independent period | **NO** — QQQ inverts on the same index; 3 of 52 instrument-years replicate, one of them being the contaminated MNQ window itself |
| short-horizon decay is mechanism-consistent | **NO** — NQ and ES rise to 30 bars; SPY is flat |
| matched-control comparison positive | **NO** — QQQ at the 0.5th percentile |
| final holdout positive | **NO** — QQQ's clean 2016–2023 holdout is negative |
| expectancy positive after realistic costs | **NO** — 7 of 8 negative at every slippage level |
| no single narrow regime/day/time bucket explains it | partially — buckets are broad, but 5 of 8 instruments flip sign across volatility regimes |
| Monte Carlo / path risk not structurally implausible | not reached |
| no parameter optimization required | **YES** — none was performed |

**FAILED_REVERSAL_REPLICATION = A. REJECT**

---

## 13. Final scorecard

| | |
|---|---|
| **Mechanism** | After an intraday extension retraces past its own 95th-percentile opening-range level, the retracement fails and the breakout resumes |
| **Evidence** | MNQ 2025–26: +$3.20/trade at 1 bar, t = 2.48, 99th percentile vs matched control, on 343 entries over 71 sessions |
| **Replication** | **FAILS.** QQQ (same index, same dates, 451 entries): −$0.80 at 1 bar, 15.3rd percentile. QQQ full sample: t = −2.2, 0.5th percentile. 3 of 52 instrument-years replicate, one being MNQ's own contaminated window |
| **OOS** | **FAILS.** ETF 2016–2023 is the only clean holdout; QQQ −0.331, IWM negative, DIA mixed, SPY +0.378 (t = 1.32) |
| **Cost robustness** | **FAILS.** 7 of 8 instruments NEGATIVE AFTER COSTS at all slippage levels. MNQ marginal; its OOS break-even is 1.00 tick |
| **Regime robustness** | **WEAK.** 5 of 8 instruments flip sign across volatility terciles |
| **Topstep feasibility** | Not assessed — gated off. Risk shape is excellent (0.07× MLL) around no edge |
| **Statistical confidence** | The single positive result is 343 entries over 71 sessions and is contradicted by 4,124 entries on the same index |
| **Fragility** | Maximal: the sign depends on which contract of the same index is used |
| **VERDICT** | **REJECT** |

---

## 14. What this changes, and what to do next

1. **The mechanism is closed.** It was the last live candidate from the strategy library. All
   132 lab cells are now REJECT or unpromotable.
2. **The `revert.vwap.q90` NQ lesson generalises.** Both the highest-earning cell and the only
   information-carrying cell turned out to be contract-specific artifacts. The futures store's
   251–312 sessions cannot distinguish a mechanism from a sample.
3. **Adopt the ETF panel as the primary screen, permanently.** It supplied 16,150 entries
   against the futures store's 1,626 and settled in one run a question 343 futures trades could
   not. Any future intraday mechanism should be screened there *before* it earns futures time.
4. **The one exploratory thread**, if anyone wants it: the S&P complex is weakly positive
   (SPY +0.378 over the clean holdout, 95.3rd percentile) where the Nasdaq is negative. That is
   a *new* hypothesis discovered from these results, needs its own preregistration and its own
   holdout, and must not inherit this study's evidence.

---

## 15. Reproducibility

```bash
python scripts/failed_reversal_spec.py          # Phase 1 - freeze + hash
python scripts/failed_reversal_replication.py   # Phases 2, 5, 6 - ~50 min
python scripts/failed_reversal_periods.py       # Phases 3, 4, 8, 9 - ~55 min
python scripts/failed_reversal_friction.py      # Phase 7 + plots - ~45 min
python -m pytest tests/test_failed_reversal.py -q
```

Seeds: 20260914 (replication), 31415 (periods), 7 (spec verification). Deterministic.

**Artifacts:** `research/failed_reversal_spec.json`, `fr_replication_instruments.csv`,
`fr_replication_periods.csv`, `fr_replication_eras.csv`, `fr_replication_regimes.csv`,
`fr_replication_buckets.csv`, `fr_replication_friction.csv`; 7 plots.

---

## 16. Data periods used

| store | span | sessions with entries | entries |
|---|---|---|---|
| futures MNQ | 2025-09-07 … 2026-09-10 | 71 | 343 |
| futures NQ | 2025-06-08 … 2026-09-10 | 81 | 470 |
| futures MES | 2025-09-07 … 2026-09-10 | 90 | 449 |
| futures ES | 2025-06-08 … 2026-09-10 | 88 | 364 |
| ETF SPY | 2016-01-05 … 2026-09-10 | 990 | 4,395 |
| ETF QQQ | 2016-01-05 … 2026-09-10 | 905 | 4,124 |
| ETF IWM | 2016-01-05 … 2026-09-10 | 827 | 3,719 |
| ETF DIA | 2016-01-05 … 2026-09-11 | 835 | 3,912 |

**Contamination: YES, and it is the futures window.** 2025-06 → 2026-09 generated the
hypothesis and has been inspected five times. ETF 2016–2023 is clean.
