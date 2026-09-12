# ML track journal (F-)

Newest first. The `ml` scope: the supervised intraday forecaster - `algorithms/intraday/ml/`,
`scripts/ml_*.py`, `scripts/sweep_f*.py`, and the `data/f1/` prediction caches. Evidence only;
this track has never shipped a deployed file and does not ask to.

---

## 2026-09-12 - F-7: the lower-turnover expression of F-1's forecast. The construction lifts gross per dollar 8.5x, the pre-registered rule still refuses it, and a 2.5x power extension turns the one promising cell to zero. Refused. Nothing shipped.

**Hypothesis.** F-1 found this repository's first positive out-of-sample intraday edge and refused
it on arithmetic, not judgement: pooled IC **+0.01133 at t +4.74**, gross **+$1,102/day at t
+3.04**, and a book that turns **$13.83M/day on $1M** while the forecast is worth **0.797 bps per
dollar turned** against **0.892 bps** of commission plus regulatory fees and **2.392 bps** once the
shipped 1.5 bps slippage constant is charged. F-1's closing paragraph named the single thing that
would change that arithmetic - *a lower-turnover expression of the same forecast* - and then
followed only the **daily** route (F-3, refused: 0.304 bps per dollar turned, IC t +0.18). The
**within-session** route was never tried. It needs no new model, no new feature and no new label:
freeze F-1's out-of-sample predictions and vary only the book built on top of them.

`scripts/ml_f7.py`, **29 DIAGNOSTIC ledger rows** under `intraday/f7_turnover` (19 constructions,
5 scrambled controls, 5 power-extension cells). Eight clauses pre-registered in the module
docstring before a construction number was read. **No shipped or runner-loaded file was touched** -
`algorithms/intraday/active/signal.py` and `live/intraday_config.json` are untouched, so no deploy
gate and no `--replay` is owed.

**(1) Clause 1, identity, exact.** The frozen forecast run through this module's own simulator at
F-1's decile-0.10 book reproduces ledger row `20260911T155155Z` to the cent: gross **1,102.352**
vs 1,102, net **-2,206.101** vs -2,206, turnover **13,831,037.037** vs 13,831,037, gross bps
**0.797**, IC **+0.01133**. Everything below is F-1's forecast, unchanged.

**(2) Clause 2 predicted the wrong answer, and that is the first finding.** The persistence table -
IC(h) of the frozen prediction against the demeaned cumulative return h intervals ahead, computable
with no book at all - does **not** decay. It *rises*:

| h | minutes | IC(h) | t | IC(h)/IC(1) | cumulative multiple |
|---|---|---|---|---|---|
| 1 | 30 | +0.01133 | +4.74 | 1.000 | 1.000 |
| 2 | 60 | +0.01069 | +4.31 | 0.944 | 1.944 |
| 4 | 120 | +0.01447 | +5.22 | 1.277 | 4.264 |
| 7 | 210 | +0.02064 | +6.01 | 1.822 | 9.428 |
| 10 | 300 | +0.02115 | +3.96 | 1.868 | 14.534 |
| 11 | 330 | +0.01622 | +2.09 | 1.432 | 15.966 |

Best cumulative multiple **15.966 at k=11** against the **3.00x** needed to clear the shipped cost
and **1.12x** to clear commission alone, so clause 2 pre-registered **CAN**. The 30-minute horizon
F-1 trained on is the *worst* horizon its own forecast has; the signal is a multi-hour one being
harvested every 30 minutes. **That number, not the books below, is what F-7 is worth keeping.**

**(3) Clause 3: the construction does exactly what clause 2 said, and it is not enough.** Nineteen
cells - decile width, dwell (re-decide every k-th point), hysteresis bands, within-session EWMA of
the prediction, and a conviction gate that trades only names whose predicted |alpha| in bps exceeds
a multiple of the one-way cost:

| cell | gross bps | x F-1 | gross t | cost bps | turn/day | net $/day | t |
|---|---|---|---|---|---|---|---|
| base decile 0.10 (F-1) | 0.797 | 1.00 | 3.04 | 2.392 | 13,831,037 | -2,206 | -6.02 |
| dwell 6 (3 h) | 2.096 | 2.63 | 2.01 | 2.504 | 3,393,457 | -139 | -0.39 |
| dwell 11 (once a day) | 3.487 | 4.38 | 1.79 | 2.585 | 2,000,000 | +180 | +0.46 |
| ewma 0.25 | 2.113 | 2.65 | 2.79 | 2.454 | 5,024,469 | -171 | -0.45 |
| conv 2.0x cost | 4.193 | 5.26 | 2.36 | 4.090 | 3,726,469 | +38 | +0.06 |
| conv 2.0x, wide decile | 4.232 | 5.31 | 2.39 | 4.086 | 3,730,896 | +55 | +0.08 |
| **band 0.10/0.40 + conv 2.0x** | **6.797** | **8.53** | **3.08** | 3.883 | 3,435,835 | **+1,001** | **+1.33** |

Gross per dollar turned goes from 0.797 to **6.797 bps, 8.53x**, on **a quarter of the turnover**,
and the best cell is **net positive in 3 of 3 test years** (+1,598 / +460 / +913). It is still
**REFUSED: 0 of 19 cells pass**, because clause 7 asks for t > 2 pooled and the best cell reaches
**t +1.33**. On 675 sessions the construction produced a plausible book and no evidence.

**(4) The conviction gate buys its gross partly by trading more expensive names, and the control
is what exposes it.** Clause 4 re-runs every construction on a per-timestamp permutation of the
prediction - same breadth, same turnover profile, forecast destroyed. The controls are clean on
gross (**-0.298 / -0.336 / -0.308 / +0.488 / -0.115 bps**, |t| <= 1.33, so the improvement is the
forecast and not the construction's arithmetic) but their **cost column is not**: every control
prices at **2.13-2.19 bps** while the real conviction books pay **3.88-4.09**. The gate does not
select names at random from the decile - it selects the ones with the widest predicted moves, which
are the low-priced, high-commission, reverse-split leveraged names. **1.7 bps of the 2.4 bps of
extra cost is selection, not construction**, and no turnover reduction removes it.

**(5) Clause 8, the power extension, is the verdict.** 675 sessions cannot resolve a t of 1.33, so
the identical cells at the identical parameters were re-run on a walk-forward started in **2019
instead of 2024** - **1,933 out-of-sample sessions, 2.5x the window, nothing re-tuned**, and early
test years training on less history, which biases *against* the finding. Pooled IC on the longer
window is **+0.01392 at t +9.84**, i.e. the forecast is more significant, not less. The books are
not:

| cell | gross bps | x F-1 | cost bps | turn/day | net $/day | t | positive years |
|---|---|---|---|---|---|---|---|
| base decile 0.10 | 0.752 | 0.94 | 2.530 | 15,179,186 | -2,698 | -13.45 | 0/8 |
| dwell 6 (3 h) | 1.387 | 1.74 | 2.598 | 3,490,352 | -423 | -2.19 | 1/8 |
| conv 1.0x cost | 1.676 | 2.10 | 3.475 | 7,450,897 | -1,340 | -3.44 | 2/8 |
| conv 2.0x cost | 2.202 | 2.76 | 3.834 | 2,935,178 | -479 | -1.39 | 2/8 |
| band 0.10/0.40 + conv 2.0x | 3.495 | 4.39 | 3.697 | 2,764,265 | **-56** | -0.15 | 4/8 |

**The best cell's gross per dollar halves (6.797 -> 3.495) and its net goes from +$1,001/day to
-$56/day at t -0.15, positive in 4 of 8 years - a coin flip.** Its three-for-three year record on
the short window was the 675-session sample, not a property of the book: the five years F-7's own
grid never saw are 2019 -183, 2020 +174, 2021 -781, 2022 -1,526, 2023 -808. The extended controls
confirm the gross is still the forecast's (**-0.042 / +0.058 bps**, |t| <= 0.21) - **what fails is
not the signal, it is that the signal is worth ~3.5 bps per dollar turned against a cost line that
prices at 3.7 when you select for it.** Refused on the pre-registered rule at 0 of 5 cells.

**(6) Feature-importance stability (the second thing the job asks to judge on).** Permutation
importance on each retrain's validation year, 38 features, `data/f1/importance_f7.csv`. Spearman
rank correlation between retrains **0.665 (2024/2026) / 0.699 (2024/2025) / 0.767 (2025/2026)** -
the model reads a recognisably similar object each year. The top of the ranking is the VWAP
displacement family (`vwap_atr`, `cs_vwap_atr`), relative volume (`vol_rel`, `rvol_ratio`) and
range (`rng_atr`), which is the same mean-reversion-against-VWAP story the hand-written intraday
strategies encode. **But the magnitudes flip sign year to year on the same feature** - `cs_vwap_atr`
is +1.38e-2 / -1.05e-2 / +4.10e-2 and `rvol_ratio` -1.52e-2 / +9.07e-2 / +9.38e-3 - and a negative
permutation importance means shuffling the feature *improved* validation MSE. A stable ranking over
unstable, sign-flipping magnitudes is what a weak true signal read through noise looks like. It is
consistent with IC +0.011 to +0.014 and it is not evidence of anything the book can spend.

**Decision: REFUSED, and the supervised class is now priced three ways rather than two.** F-1
refused the 30-minute book on cost, F-3 refused the daily horizon on absence of edge, F-7 refuses
the low-turnover *construction* on power - and the three together say the same thing with different
arithmetic: **this feature set forecasts at IC ~ +0.011 to +0.014 wherever it is pointed, that is
worth single-digit bps per dollar turned at best, and this instrument's round trip costs 2.4 to 4.1
bps.** Nothing in F-7 moves toward deployment. `champion.json` untouched; nothing filed in
`BLOCKERS.md`, because a refusal on cost and power is not an owner option.

**Do not re-open as a dwell, band, EWMA, conviction-threshold or decile question.** The grid spans
dwell 1 to 11 (one decision to once a day), bands from 0.04/0.20 to 0.10/0.40, EWMA lambda 0.25 and
0.50, conviction 0.5x to 2.0x cost, deciles 0.04 to 0.34, and the stacked cells of the two that
moved the number most - and the best of all nineteen dies on a 2.5x window with nothing re-tuned.
The one axis F-7 did **not** close is the one clause 2 identified and the harness cannot express:
**the forecast's IC peaks at h = 7-10 intervals (3.5-5 hours), and the label F-1 trains on is the
30-minute one.** A model trained directly on the multi-hour label is a different forecast, not a
different book, so it is a new pre-registration - filed below as **F-8** - and it inherits F-7's
cost arithmetic: it needs ~3.7 bps per dollar turned, and the honest prior after three refusals is
that it will find IC ~ +0.014 and be worth ~3.5.

**Two durable pieces survive the refusal.** (a) **The persistence table is reusable and cheap** -
`data/f1/f7_persistence.csv`, and the method (IC(h) on the demeaned cumulative return, computed
from the frozen prediction with no book) prices any forecast's natural holding period before a
simulator is written. (b) **A reproducibility hazard was found and fixed in this file**: F-1's cost
model depends on `data/minute_alpaca/_splits.json`, which only exists in the Alpaca store, so
running any F-track script **without `INTRADAY_DATA_DIR=data/minute_alpaca` silently understates
cost by 0.28 bps of turnover** (2.110 vs 2.392 on the base book - 12% of the cost line) while gross,
turnover and IC all still match to the cent. The mechanism is the reverse-split leveraged names
(`SQQQ` factor 0.0001, `SPXU` 0.0025, `SOXS` ~0): without the file `share_scale()` is 1.0, the
per-share commission is charged on split-*adjusted* share counts that are four orders of magnitude
too few, and most of those orders collapse to the $1.00 minimum. `ml_f7.py` now prints the store it
is costing against and names this as the first suspect when clause 1 fails. **Any future F-track
run must be started with that variable set**; the first clause-1 failure of this iteration was
exactly this and nothing else.

**Standing jobs**: neither belongs to this track (A-5 part 2 and S-17 part 2 are `iterate`/`daily`),
and it is a Saturday, so no new fills exist to re-quote.

**Next**: F-8 as filed in the backlog - retrain on the multi-hour label clause 2 identified, with
F-7's cost arithmetic and the power extension as the pre-registered window from the start.
