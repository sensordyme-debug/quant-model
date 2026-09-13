# ML track journal (F-)

Newest first. The `ml` scope: the supervised intraday forecaster - `algorithms/intraday/ml/`,
`scripts/ml_*.py`, `scripts/sweep_f*.py`, and the `data/f1/` prediction caches. Evidence only;
this track has never shipped a deployed file and does not ask to.

---

## 2026-09-12 - F-12: forecast the denominator. The risk model works (rank IC +0.53 against the return model's +0.02) and using it makes the book worse, because this forecast's alpha scales as vol^1.49 and inverse-vol sizing is a bet on vol^1.0. Refused. The sizing axis is bounded on BOTH sides and neither end reaches t = 2.

**Hypothesis.** F-11 closed the track with a standing sentence: reopening the supervised class
needs *"a different instrument, a different frequency, or a different label family - not another
construction on this one."* F-12 is the third. F-7 moved the book, F-8 the label's horizon, F-10
the breadth, F-11 the cost - **all four are the numerator of the P&L and none is the denominator
of the t**. And three separate runs have reported the same incidental fact without acting on it:
*the only feature family that survives a retrain on this panel is the volatility family*
(F-11 (10): `vol_rel6` rank mean 6.8, `m_rvol_ratio` 7.5, `rvol_ratio` 7.9). A model asked for
direction keeps reaching for the volatility features, which is what a model does when the thing
it can resolve is not the thing it was asked for. So F-12 **fits a second model on a new label
family** - `|y_close|`, the absolute demeaned move to the flatten, i.e. the per-name risk
contribution of a dollar-neutral book - and spends it on **sizing** rather than selection:
`w_i proportional to sigma_hat_i^-p`, p in {0, 0.5, 1, 2}, p = 0 being F-8 exactly and **p = 1
the pre-registered primary** (the optimum is alpha/sigma^2, so p = 1 is right when alpha scales
with vol and p = 2 when it is constant; the two bracket every plausible view).

`scripts/ml_f12.py`, **22 DIAGNOSTIC ledger rows** under `intraday/f12_risksize` (18 pre-registered
cells in `data/f1/f12_risksize.csv`, 4 post-run). Eight clauses pre-registered in the module
docstring including clause 0, the prior, written before a number was read: *"sd down ~15%, mean
down ~10%, t from +1.47 to roughly +1.6, refused on clause 5."* The **return** predictions are
re-read frozen from `data/f1/f8_preds.parquet` - nothing about F-8's forecast is re-fitted - and
the only new fitted object is the risk model (`data/f1/f12_risk.parquet`, same 38 features, same
`GRID["mid"]` learner, same expanding walk-forward, 8 test years). **No shipped or runner-loaded
file was touched**, so no deploy gate and no `--replay` is owed. Run with
`INTRADAY_DATA_DIR=data/minute_alpaca`, `_splits.json` confirmed present.

**(1) Clause 1 identity is exact and this file has no turnover confound at all.** p = 0
reproduces F-8 to the printed digit: gross **4.256**, cost **2.724**, net **$305.7/day**, t
**+1.474** on 1,933 sessions. And uniquely among F-track constructions, **turnover is identical
in every cell to the dollar - $1,995,861/day, spread $0** - because each side still sums to
gross/2 on entry and to zero at the flatten however the dollars are split inside it. Every bps
column below is like-for-like by construction rather than by control.

**(2) The risk model is a genuinely good forecast, and 32x the return model's.** Per-timestamp
rank IC on `|y_close|`, by test year: **+0.3065 to +0.3563, mean +0.3302** (IC t-stats +100 to
+146), level R^2 **+0.251 to +0.350, mean +0.315**. The same walk-forward on the *signed* label
- F-8's own `close` predictions, re-measured here - gives mean rank IC **+0.01030**, and it is
**negative in 2026 (-0.00755)** while the risk model's worst year is +0.3065. Predicted session
risk runs **BRK.B 47 bps to SOXS 242 bps, a 5.1x cross-sectional spread**, which is the
dispersion F-8's equal-weight book was ignoring.

**(3) The lever does exactly what it was built to do on the risk side.** 1,933 out-of-sample
sessions, 2019-2026, turnover constant:

| p | eff. N | gross bps | cost bps | net $/day | t | sd $/day | worst |
|---|---|---|---|---|---|---|---|
| **0 (= F-8)** | 11.4 | 4.256 | 2.724 | **306** | **+1.47** | 9,118 | -51,431 |
| 0.5 | 10.9 | 3.708 | 2.580 | 225 | +1.31 | 7,575 | -37,352 |
| **1 (primary)** | 9.9 | **3.267** | 2.469 | **159** | **+1.06** | **6,622** | -32,402 |
| 2 | 7.8 | 2.656 | 2.326 | 66 | +0.49 | 5,923 | -27,421 |

**sd falls 27%** at p = 1 and 35% at p = 2, monotonically, and the worst day improves from
-$51,431 to -$27,421. Clause 0 predicted 10-25%; the risk side of the prior was right.

**(4) And the mean falls twice as fast, so it is refused.** **t +1.058 against a hurdle of 2.0**,
5/8 years positive. **REFUSE.** Clause 6(a): mean **x0.521**, sd **x0.726**, t **x0.718** - the
entire loss is the mean channel. Paired per session (clause 6(b)), p = 1 minus p = 0:

| component | mean $/day | paired t |
|---|---|---|
| gross given up | **-197** | **-2.28** |
| cost saved | +51 | +42.38 |
| **net** | **-146** | **-1.69** |

This is the **exact mirror of F-11**. There the cost saving was arithmetic (t +41.67) and the
gross it bought was noise (t -0.48); here the cost saving is the same arithmetic (t +42.38) and
**the gross given up is the significant term** (t -2.28). Same standing rule, opposite verdict,
and only the paired test shows it.

**(5) Clause 4(ii) FAILS, and the way it fails is the finding.** Scrambling `sigma_hat` per
timestamp keeps the weight *dispersion* and assigns it to the wrong names. Random dispersion
costs the book almost nothing - **t +1.400 +/- 0.065** against equal weight's +1.474 - while the
**correct** risk forecast costs it a great deal, **t +1.058**. *Sizing unequally is nearly free;
sizing by this forecast is expensive.* The better the risk forecast, the worse the book, because
it is better at finding exactly the names the book should be overweight. Clause 4(i) passes
(scrambled alpha under inverse-vol sizing earns gross t **-0.13**), so the lever is not a static
short-the-leveraged-sleeve tilt.

**(6) The free baseline beats the ML model at every rung.** Trailing 20-bar ATR - the panel's own
causal range feature, available to any desk for nothing - gives **t +1.41 / +1.28 / +0.93** at
p = 0.5/1/2 against the model's +1.31 / +1.06 / +0.49, and paired, `p1 - atr_p1` is **-$35/day at
t -1.55**. sigma_hat and atr are Spearman **+0.945** correlated, so the ML model is the same
object plus a refinement, and **the refinement is the part that loses money**. That is the
sharpest version of (5).

**(7) The elasticity, measured. This is the reusable number.** Clause 0 stated the analytic floor
in advance: by Cauchy-Schwarz, inverse-vol weighting is *weakly better* than equal weighting
whenever alpha is proportional to sigma, so a loss requires alpha to rise with vol **faster than
linearly**. Post-run, over 21,940 held name-days:

| sigma quintile | n | sigma bps | realised alpha bps | t | alpha/sigma |
|---|---|---|---|---|---|
| 1 (quietest) | 4,388 | 60.6 | **-0.76** | -0.49 | **-0.0125** |
| 2 | 4,388 | 90.5 | 3.94 | +1.77 | 0.0435 |
| 3 | 4,388 | 123.5 | 6.08 | +1.98 | 0.0492 |
| 4 | 4,388 | 170.2 | 10.20 | +2.40 | 0.0599 |
| 5 (loudest) | 4,388 | 275.2 | **20.51** | +3.00 | **0.0745** |

**log-log slope beta = +1.494.** Break-even for inverse-vol sizing is beta = 1. And the
`alpha/sigma` column - the per-name information ratio - **rises monotonically across the whole
range**: the forecast has *no edge at all* in the quietest fifth of its own holdings (-0.76 bps,
t -0.49) and its edge per unit of risk is 6x larger in the loudest. Harmonic/arithmetic mean of
sigma over held name-days is 0.751, which is the mean ratio the linear case predicts; the mean
actually fell to 0.521, i.e. **31% more than beta = 1 allows**. This is the same volatility
finding F-8 and F-11 reported as a regime split (low vol dead, high vol paying), measured in the
cross-section instead of the time series, and it says the two are one phenomenon.

**(8) The other direction is better and still does not clear the hurdle - which bounds the axis.**
Post-run and explicitly barred from clause 5 (test-set-selected, no control): p = -1 tilts *into*
the loud names and reads net **$499/day at t +1.57**, paired **+$194/day, gross t +2.03** - a
significant gross gain, unlike F-11's. But sd goes **9,118 -> 14,029** and the worst day
**-$51,431 -> -$82,537**, so t moves only +0.10. **The full sizing ladder p in [-1, 2] spans t
from +0.49 to +1.57 and never touches 2.0.** The axis is bounded on both sides.

**(9) Regimes, which the brief asks for explicitly.** Risk sizing makes the dead regime deader.
Low vol **-$69 -> -$200 -> -$299/day** at p = 0/1/2; mid vol $452 -> $272 -> $177; high vol $534
-> $407 -> $320. It helps nowhere. F-8's and F-11's volatility finding stands and (7) explains it.

**(10) Feature-importance stability, the brief's second criterion, and the contrast confirms the
premise.** Permutation importance over the same 8 test years and 38 features, both models:

| | mean pairwise Spearman | top-10 overlap | in the top 10 of every year |
|---|---|---|---|
| return model (F-8, `y_close`) | +0.434 (0.147..0.798) | 44% | **none** |
| risk model (F-12, `\|y_close\|`) | **+0.772** (0.598..0.957) | **61%** | **`vol_rel`, `vol_rel6`** |

The risk model's top two features are `vol_rel` (rank mean **1.9**, rank sd 1.0) and `vol_rel6`
(**2.2**, sd 1.4) - stable to within one rank across eight retrains, against a return model where
nothing survives. **And the return model's own most-persistent feature is `vol_rel6`** (rank mean
6.8), i.e. the #2 feature of the risk model: the direction model has been reaching for the risk
model's inputs all along, which is the observation F-12 was built on and is now measured rather
than inferred. **That stability bought nothing.** F-11 asked whether unstable importance was a
symptom of a weak forecast; the answer here is that the stable object is simply not the one the
book needs, and a forecast can be 32x more accurate, 1.8x more stable, and strictly harmful.

**Decision.** **REFUSE.** Nothing deployed, nothing promoted, `champion.json` untouched.

**What it changes for the loop.** Two reusable rules. **(a) Risk parity is a bet on beta = 1.**
Equal-risk sizing is only optimal when a forecast's alpha scales linearly with the name's own
volatility; measure the log-log elasticity of realised alpha on predicted risk *before* applying
any inverse-vol overlay, and if beta > 1 the overlay is a tax. This applies to every sleeve in
this repository, including the daily champion and the deployed intraday `active` book, neither of
which has ever measured its own beta. **(b) A better forecast of the wrong quantity is worse than
no forecast of it.** The scrambled-sigma control here beat the real one: random dispersion cost
0.07 of t, the correct risk forecast cost 0.42. Any future overlay must be run against a
*scrambled version of its own signal*, not only against a null book.

**Next.** The label-family axis is now priced alongside the other five, and with (8) the sizing
axis is bounded on both sides. The honest reading is that **this feature set on this panel does
not support a t = 2 book by any construction available in this scope.** The one direction (7)
opens that is not a construction is a *universe* question rather than a model question - the
forecast's edge is concentrated where beta is largest and is negative in its own quietest
quintile - but that is A-track/D-track territory (which names belong in the sleeve), not F-track.
Filed as **F-13** for whoever wants it, pre-registered and unread.

---

## 2026-09-12 - F-11: rank on alpha net of the name's own round trip. The cost saving is real to five decimal places, the gross it buys back is pure noise, and the improvement in t is therefore not an improvement at all. Refused. The cost axis closes.

**Hypothesis.** F-8 and F-10 both tried to make the numerator bigger - a better label, then more
breadth. Neither touched the other side of the subtraction, and that is where most of the money
is: **F-8 pays away 64% of its gross as cost** (4.256 bps per dollar turned against 2.724). The
cost is not a constant of the book. IBKR charges $0.005 per **share**, so a round trip costs
`2*1.5 + 2*50/price + 0.206 + 1.98/price` bps of the position, and on this universe that runs
**3.40 bps (TMO at $516) to 11.08 bps (SOXS at $13)** - a 7.7 bps spread against a gross of ~8.5
bps of position. **One name's round trip can eat the entire edge and another's costs nothing.**

And a plain decile walks into it: ranking on predicted alpha alone buys the widest predicted
moves, which here are the low-priced leveraged and reverse-split names. F-7 measured the premium
from the other side ("1.7 bps of the 2.4 bps of extra cost is selection, not construction") and
its conviction gate made it worse **by design**; the inverse has never been tried. F-11 changes
the ranking and nothing else - `long = pred - lambda*c_i`, `short = -pred - lambda*c_i`, with
**lambda = 1 the economically correct value** (both terms are basis points of the same position,
so lambda = 1 is literally "rank on net alpha") and therefore the primary cell, fixed before any
number was read.

`scripts/ml_f11.py`, **13 DIAGNOSTIC ledger rows** under `intraday/f11_costaware` (the 12 control
cells are in `data/f1/f11_costaware.csv`). Nine clauses pre-registered in the module docstring,
including clause 0, the prior, written before a number was read: *"a partial win - cost down ~0.4
bps, gross down ~0.3 bps, edge up ~0.1 bps, t landing near 1.6, better and still under the
hurdle."* **Nothing is re-fitted**: F-8's frozen walk-forward predictions are re-read and only the
*ranking* changes. **No shipped or runner-loaded file was touched**, so no deploy gate and no
`--replay` is owed. Run with `INTRADAY_DATA_DIR=data/minute_alpaca`, `_splits.json` confirmed
present.

**(1) Clause 1 identity is exact.** lambda = 0 reproduces F-8 to the printed digit: gross
**4.256**, cost **2.724**, net **$305.7/day**, t **+1.474** on 1,933 sessions.

**(2) The lever does what it was built to do, and the ladder has a genuine interior optimum.**
1,933 out-of-sample sessions, 2019-2026, turnover held at $1,995,861/day at every rung:

| lambda | gross bps | cost bps | edge bps | net $/day | t | sd $/day |
|---|---|---|---|---|---|---|
| 0 (= F-8) | 4.256 | 2.724 | 1.532 | 306 | +1.47 | 9,118 |
| 0.25 | 4.349 | 2.520 | 1.829 | 365 | +1.79 | 8,985 |
| 0.5 | 4.309 | 2.398 | 1.911 | 381 | +1.93 | 8,690 |
| **1 (primary)** | **4.063** | **2.250** | **1.813** | **362** | **+1.88** | 8,457 |
| 2 | 4.178 | 2.090 | 2.089 | 417 | +2.26 | 8,101 |
| 4 | 3.557 | 1.942 | 1.616 | 322 | +1.89 | 7,513 |
| 8 | 3.080 | 1.841 | 1.238 | 247 | +1.57 | 6,934 |

Cost falls **monotonically, 2.724 to 1.841** - and 1.5 bps of that is slippage, a shipped
constant, so the ~1.22 bps commission-and-fees term is cut by **72%**. The mechanism is exactly
the one claimed: name-days held move **SOXS -634, PLTR -325, INTC -210, UBER -206** and **NOW
+413, COST +410, AVGO +338, LLY +285**, i.e. the book stops renting the most expensive names.
Clause 0's prior was close to right and if anything pessimistic (cost -0.47, gross -0.19, edge
+0.28, t 1.88).

**(3) And it is refused, on the clause fixed before the run.** Clause 5 reads **lambda = 1 only**:
**t +1.881 against a hurdle of 2.0**, 5/8 years positive against a hurdle of 5. **REFUSE.** The
best cell on the test set is lambda = 2 at **t +2.26**, and clause 5 forbids reading it - it is
selected on the same sessions it is scored on, and section (4) says why that matters more than
usual here.

**(4) The finding is the paired test, and it deflates everything above.** Comparing two separately
noisy t's (+1.47 against +1.88) is the wrong statistic when both books trade the same sessions.
Paired per session, lambda = 1 minus lambda = 0:

| component | mean $/day | paired t |
|---|---|---|
| cost saved | **+95** | **+41.67** |
| gross given up | -39 | -0.48 |
| **net** | **+56** | **+0.70** |

**The cost saving is deterministic - t +41.67, it is arithmetic on a known price - and the gross
it costs is indistinguishable from noise.** The net improvement is therefore **+$56/day at t
+0.70, positive on only 45% of sessions**: the median session is *worse* and the mean is carried
by a right tail. So "t 1.47 -> 1.88" is **not a measured improvement**; it is one draw of a
difference this data cannot resolve, and the same sentence disposes of the lambda = 2 cell's
+2.26. Split in half by time the paired delta is **+$42 (t +0.35)** on 2019-01..2022-10 and
**+$71 (t +0.67)** on 2022-11..2026-09 - same sign, same non-significance, in both halves.

**(5) Clause 4's control passes on both limbs, and coded as a gate this time.** (F-10's post-run
defect (i) was a clause written as a gate and coded as a remark.) Per-timestamp scrambled
predictions, 3 seeds per cell: the zero-forecast book's **gross stays at zero under cost-aware
ranking at every lambda** (mean gross t **-0.90 / -0.20 / -0.34 / -1.39**), so the lever is not a
static short-the-leveraged-sleeve tilt dressed up as a forecast. And the control's cost falls too,
2.236 to 1.998 - **50% of the real book's 0.475 bps drop** - which passes clause 4(ii) and also
explains the other half: the real book started at 2.724 against the control's 2.236, i.e. it was
carrying F-7's **+0.488 bps selection premium**, and lambda removes the premium *and* part of the
base. That is the mechanism claimed, measured from the null side.

**(6) Clause 6's decomposition says the change is a mean effect, which is the good direction.**
mean x1.184, sd x0.928, t x1.276 - 72% of the t change is the mean channel. Unlike F-10's breadth
curve, this is not a smoothing artifact. It is simply too small to resolve.

**(7) The blunt version is worse, and non-monotonically so.** Hard price floors at lambda = 0:
$25 -> net $286 (t +1.56), **$50 -> net $62 (t +0.39)**, $100 -> net $256 (t +1.56). A floor
throws the name out of the *universe*; lambda only makes it pay for its place, so a floor
destroys gross (2.25 bps at $50) that lambda keeps. **A continuous cost penalty strictly dominates
an eligibility filter** - the one clean, reusable result in this file.

**(8) The gate is the cell a live desk would actually want, and it still does not pass.** Trading
only names whose own net score is positive holds **4.5 names instead of 11.4** and turns
**$790k/day instead of $1.996M** - **40% of the turnover for 95% of the net** ($289/day, t +1.85),
at **6.214 bps gross per dollar turned**, the highest gross-per-dollar anywhere on this track
except F-7's conviction cell. If any F-track construction is ever revived for an execution-limited
book, this is the one; it is not revived here, because its t is 1.85.

**(9) Regimes, which the brief asks for explicitly.** The cost cut helps everywhere and does not
rescue the dead regime: low vol goes **-$69/day (t -0.22) to +$22/day (t +0.08)**, mid vol $452 ->
$464, high vol **$534 (t +1.28) -> $601 (t +1.60)**. F-8's and F-10's volatility finding stands -
low vol is flat at best - and the improvement is broad rather than concentrated in one third.

**(10) Feature-importance stability, the brief's second criterion.** Over F-8's 8 test years and
38 features: mean pairwise Spearman of the yearly rankings **+0.434** (min +0.147, max +0.798),
mean top-10 overlap between year pairs **44%**, and **no feature is in the top 10 of every year**.
The volatility family is what persists (`vol_rel6` rank mean 6.8, `m_rvol_ratio` 7.5,
`rvol_ratio` 7.9, `cs_rvol_ratio` 10.1) but each swings by 20-30 ranks across years. **The model
re-selects its inputs substantially at every retrain**, which is consistent with a forecast whose
IC is +0.02 and whose book cannot reach t = 2: there is a persistent volatility signal underneath
and a lot of year-specific noise on top.

**(11) Two defects in this file's own first cut, declared separately from the pre-registration.**
**(i) The units were wrong.** `sweep_f1.fit_predict` trains on `y * 1e4`, so **`pred` is already
in basis points**; the first cut multiplied it by 1e4 again, making lambda = 1 behave as
lambda = 1e-4 and flattening the whole ladder to within $14/day. **Clause 1 caught it** - the
identity check failed, the run was declared void by its own rule, and nothing was read. That is
the second time a clause written before the numbers has stopped a wrong result on this track.
**(ii) The greedy selection broke exact prediction ties in the opposite direction from F-8's
`argsort`**, which the tree emits often (identical leaf values); it moved the base cell by $5/day
and 0.03 of t on 316 of 1,933 sessions. lambda = 0 now delegates to F-8's own `_decile` so the
identity is exact by construction, and a `lambda 0 (greedy)` rung is reported beside it so the
ladder's first step is not read as a cost effect.

**Decision.** **REFUSE.** The cost axis is now closed, and it closes with a bound rather than a
verdict: cost is floored by slippage at 1.5 bps of turnover, lambda = 8 already removes 72% of
everything above that floor, and the book still reaches only t +1.57. **Removing the entire
commission dispersion cannot clear the hurdle, so nothing on this axis can.** Nothing deployed,
nothing promoted, `champion.json` untouched.

**What it changes for the loop.** The reusable rule is a paired one, and it is the twin of F-10's:
**an improvement that is a certainty on one side of a subtraction and noise on the other must be
tested paired on the shared sessions, not by comparing the two books' t's.** Here a cost saving
with t = +41.67 bought a net improvement with t = +0.70, because the gross it sacrificed has a
standard error twenty times its mean - and a side-by-side reading of 1.47 against 1.88 shows none
of that. The secondary rule is (7): **a continuous cost penalty dominates an eligibility filter**,
which applies to every sleeve in this repository that has ever considered a price or liquidity
floor.

**Next.** Nothing open on the ML track. F-1/F-3 priced the method, F-7 the book, F-8 the label and
horizon, F-10 the breadth, and F-11 the cost. All five axes of F-1's forecast are now measured and
the forecast clears its cost line by +1.8 bps per dollar turned and cannot reach t = 2 on the data
that exists. Reopening the supervised class needs a **new mechanism** - a different instrument, a
different frequency, or a different label family - not another construction on this one.

---

## 2026-09-12 - F-10: breadth does not buy the power F-9 assumed. 57% of the curve is a channel a zero-forecast book gets too, 43% is a channel clause 5 says reverses, and the only correctly-specified ceiling is 2.34. F-9 refused; the D track does not build a 500-name store on this rationale.

**Hypothesis.** F-8 closed the F track with a positive edge column (+1.532 bps per dollar turned)
and a refusal on power - t +1.47 where clause 7 asked for t > 2 - and parked its only reopening as
**F-9**: *"the pooled t is a breadth statistic as much as a length one... ~4x the breadth would
reach the same t on the ~1,900 sessions that exist. That is a request for a ~500-name Alpaca SIP
minute universe."* That sentence contains an untested assumption and it is the whole of F-9's case:
"4x the breadth reaches the same t" is the claim t ~ sqrt(N), which holds only for *independent*
contributors. A dollar-neutral decile book over the most liquid US equities shares a market, a
handful of sectors and, in the leveraged sleeve, literally the same underlying index. F-10 measures
the breadth curve on the 56 names **already on disk**, before the D track spends weeks paging a
500-name store out of Alpaca.

**Resumed, not started.** `scripts/ml_f10.py` was written in a prior run that was cut off with
114 of 129 simulations cached and no ledger rows or journal entry. This run finished the remaining
15 (the N=56 control and the 12 partition sub-books), found two defects in the file's own first
cut, fixed them, and recorded. **9 DIAGNOSTIC ledger rows** under `intraday/f10_breadth`. Nothing
is re-fitted and nothing is re-tuned: F-8's frozen walk-forward predictions are re-read and only
the *book's* universe is subsampled, so this measures the **diversification** channel of breadth
and not the training channel (clause 2/6a). **No shipped or runner-loaded file was touched**, so no
deploy gate and no `--replay` is owed. Run with `INTRADAY_DATA_DIR=data/minute_alpaca`, `_splits.json`
confirmed present.

**(1) Clause 1 identity is exact.** The full-universe cell reproduces F-8 to the printed digit:
gross **4.256**, cost **2.724**, net **$306/day**, t **+1.474** on 1,933 sessions. The run is valid.

**(2) The curve rises, and that is not the finding - what it is made of is.** 12 seeded subsets per
width, 1,933 out-of-sample sessions, 2019-2026:

| N | runs | gross bps | cost bps | net $/day | t mean | t sd |
|---|---|---|---|---|---|---|
| 8 | 12 | 3.591 | 2.835 | 150 | +0.267 | 0.642 |
| 12 | 12 | 3.361 | 2.367 | 197 | +0.588 | 0.892 |
| 16 | 12 | 4.271 | 2.772 | 298 | +0.872 | 0.950 |
| 24 | 12 | 3.456 | 2.407 | 209 | +0.765 | 0.734 |
| 32 | 12 | 4.049 | 2.716 | 266 | +1.051 | 0.350 |
| 40 | 12 | 3.993 | 2.601 | 278 | +1.218 | 0.328 |
| 48 | 12 | 4.539 | 2.778 | 351 | +1.519 | 0.254 |
| **56** | 1 | **4.256** | **2.724** | **306** | **+1.474** | - |

Fitted log-log slope **beta = +0.776**, which is *above* F-9's assumed 0.500 and would extrapolate
to **t = 8.94 at N = 500**. Taken at face value that funds F-9 outright. It should not be taken at
face value.

**(3) The decomposition is the iteration. t = mean / sd, and only one of those is breadth.**

| channel | log-log slope | share of the curve |
|---|---|---|
| t | +0.776 | 100% |
| mean (net $/day) | +0.334 | **43%** |
| sd (implied) | -0.441 | **57%** |

**43% of the curve is the book's mean improving with N** - $150/day at 8 names against $306 at 56,
with gross bps per dollar turned sloping +0.106 (clause 6a). That is not diversification; it is the
book selecting better out of a deeper cross-section. And it is precisely the channel **clause 5
pre-registered as running the wrong way on extension**: names 57-500 are less liquid, cost more per
dollar turned and carry weaker signal than the sleeve's deliberately-chosen 56. So the larger half
of the extrapolation rests on a channel that clause 5 says reverses.

**(4) Clause 4 fails, and it fails against the other 57%.** The pre-registered control - the same
curve on a per-timestamp scrambled prediction - was required to be "flat and indistinguishable from
zero at **every** N", on pain of "no extrapolation of it means anything". It is neither: it runs
**-1.54 at N=8 to -4.05 at N=48**, log-log slope of |t| **+0.408**. A book with **no forecast at
all** buys 0.408 of the real curve's 0.776 - and 0.408 sits right on top of the real book's sd
channel of 0.441. The two measurements agree, and together they say the smoothing half of the curve
is a property of the *construction*, not of the forecast. Both sub-tests fail: max |control t| =
4.05 against a threshold of 2, and the control slope is 0.408 against 0.25 x 0.776 = 0.194.

**(5) So the three estimators span the decision boundary and the quantity is not identified.**

| estimator | t(500) | ceiling t(inf) | status |
|---|---|---|---|
| (A) naive power law | 8.94 | none by construction | no ceiling exists in the form |
| (B) saturating fit | 4.285 | **191.7** | rho pinned at the 0.00000 boundary |
| (C) direct rho, as first shipped | 1.543 | 1.552 | **aggregation bug** |
| **(C) direct rho, corrected** | **2.166** | **2.344** | the only finite, correctly-specified one |

(B)'s rho = 0 is a **misspecification signature, not a measurement**: a saturating model is bounded
above by sqrt(N), the observed beta is +0.776, so the fit returns the least-saturating value it
owns. Its "ceiling" of 191.7 is the claim that 56 leveraged-and-liquid US equities have literally
zero common P&L factor, which (C) measures directly at **+0.1406 between disjoint sub-books**. The
regime table makes the non-identification plain: the same object fits rho **0.999 / 0.0119 / 0.0000**
across the causal SPY vol terciles, extrapolating to t(500) of **-0.20 / 1.95 / 3.37**. An estimator
that swings from -0.2 to 3.4 depending on which third of the sessions it is fed is not measuring a
structural constant. (Low vol is flat-to-negative at every width, which is F-8's volatility finding
again.)

**(6) Two defects in this file's own first cut, declared separately from the pre-registration.**
**(i) Clause 4 was written as a gate and coded as a remark** - the first cut printed the control
slope and then let clause 7 read (B) regardless. Applying a clause pre-registered before any number
was read is not a retro-fit; failing to apply it was the error. **(ii) Estimator (C) conflated
basket correlation with per-name correlation.** The partitions measure the correlation between two
*14-name sub-books*; the saturating model is parameterised on the correlation between two *names*.
Under equicorrelation corr(basket) = m*rho/(1+(m-1)*rho), so the per-name figure is **0.01155**, not
0.1406, and the first cut understated the ceiling by ~10x. **The correction moves (C) from 1.55 to
2.34 - from one side of the hurdle to the other, in the direction that makes the refusal harder**,
which is the direction an author's own correction should cut. It is applied in full.

**(7) The refusal, and it does not need the estimator dispute settled.** Clause 7 may not be
executed on (B), so it is applied to (C) corrected: **t(500) = 2.166, ceiling t(inf) = 2.344**. Even
the most favourable correctly-specified estimator caps the **entire program at t = 2.34 at infinite
breadth** - and by clause 5 every number here is an **upper bound**, because subsampling down from
56 measures a curve whose mean channel extension will degrade. A multi-week 500-name data build,
chasing a t = 2.0 hurdle, against a theoretical maximum of 2.34 before the haircut, does not repay
itself. **REFUSE F-9.** Consistency check on the same estimator: it over-predicts the small-N end
badly (model 0.685 at N=8 against an observed 0.267), so even (C) cannot reproduce the curve it sits
beside - one more reason not to spend weeks on its extrapolation.

**Decision.** F-9 is **refused and retired from the backlog**, not parked. The F track stays closed
on clause 8's terms. Nothing deployed, nothing promoted, `champion.json` untouched.

**What it changes for the loop.** This is the first item in the repository to refuse a *data
purchase* rather than a strategy, and the reusable rule is the decomposition: **a breadth or
sample-size curve must be split into its mean and its variance channel before it is extrapolated,
and the variance channel must be run against a zero-forecast control.** Here 57% of a curve that
looked like t ~ N^0.78 was available to a book with no forecast, and 43% was a selection effect
pointing the wrong way for the extension being argued for. Any future "more data would fix the t"
argument on this repository - and F-8's own power arithmetic was one - owes the same two columns.

**Next.** Nothing open on the ML track. If the supervised class is ever reopened it needs a new
mechanism, not more cross-section and not more history: F-1/F-3 priced the method, F-7 the book,
F-8 the label and horizon, and F-10 now prices the only scaling argument that was left.

---

## 2026-09-12 - F-8: fit the label the forecast actually has. The right label is worth 2.84x on gross per dollar turned and flips the book positive, and it still fails - not on cost this time, but on a power requirement this data set cannot meet. Refused. The track closes.

**Hypothesis.** F-7 closed every construction axis on F-1's forecast and left exactly one open, and
it was not a book axis: clause 2 measured that this feature set's IC **rises** with horizon
(+0.01133 at 30 minutes, +0.02064 at 3.5 hours, +0.02115 at 5 hours), so every F-7 construction was
harvesting a multi-hour signal with a model fitted to **the worst horizon that signal has**. F-8
changes the label and nothing else: same panel, same 38 features, same learner
(`sweep_f1.GRID["mid"]`, `random_state=0`), same walk-forward, same books, same costs.

`scripts/ml_f8.py`, **24 DIAGNOSTIC ledger rows** under `intraday/f8_label` (20 book x label cells,
4 scrambled controls). Eight clauses pre-registered in the module docstring - including clause 0,
the prior, written before a number was read: *"the honest prior is that F-8 finds IC ~+0.02 on a
longer label, converts it to ~3.5 bps per dollar turned, and fails a cost line that prices at
2.5-3.7."* **No shipped or runner-loaded file was touched**, so no deploy gate and no `--replay` is
owed. Run with `INTRADAY_DATA_DIR=data/minute_alpaca` (F-7's documented cost hazard); the module
prints the store it costed against and the run confirms `_splits.json` present.

**(1) The labels, and the one that mattered was not on the backlog's list.** Consecutive decision
slots chain exactly (`fwd[k]` ends where `fwd[k+1]` begins), so the h-interval label is the sum of
h consecutive `fwd` values inside one session, invalidated by any missing slot. The backlog asked
for h in {4, 7, 10}; those are defined on only 8, 5 and 2 of the 11 slots, which confounds horizon
with time of day and throws away 27%/55%/82% of the panel. So a fourth label was added and it is
the one that wins: **`close`, hold to the 15:30 flatten, horizon 11 - slot, defined at every slot**
(1,574,099 rows vs 285,252 for h10). It is also the only label that matches what the sleeve's
flatten actually does.

**(2) The label ladder is what this iteration is worth keeping.** Same book, same turnover
($1,995,861/day, exactly 2x equity - one round trip), same names available, same costs. The only
thing that moves is what the model was asked to predict. 1,933 out-of-sample sessions, 2019-2026:

| label | horizon | gross bps per $ turned | x h1 | gross t | net $/day | t |
|---|---|---|---|---|---|---|
| h1 (F-1's own) | 30 min | 1.501 | 1.00 | +1.53 | **-232** | -1.19 |
| h4 | 2 h | 2.632 | 1.75 | +2.77 | -15 | -0.08 |
| h7 | 3.5 h | 3.293 | 2.19 | +3.38 | +116 | +0.60 |
| h10 | 5 h | 3.608 | 2.40 | +3.70 | +191 | +0.98 |
| **close** | 11 - slot | **4.256** | **2.84** | **+4.10** | **+306** | **+1.47** |

**Monotone in horizon, five for five, at constant construction and constant turnover.** F-7's
clause-2 prediction was that the persistence is real and harvestable; this is the same claim read
through a book instead of through an IC table, and it holds. Fitting the label the book actually
holds is worth **2.84x on gross per dollar turned** and it is the difference between a book that
loses $232/day and one that makes $306/day.

**(3) It is the first F-track cell whose gross clears its own cost line, and the margin is real.**
`session <- close` prices at **4.256 gross against 2.724 cost = +1.532 bps of edge per dollar
turned**. F-7's best cell on this same window was 3.495 against 3.697, i.e. **-0.202**. Five
scrambled-prediction seeds put the control at **-0.202 +/- 0.543 bps**, so the real cell sits
**8.2 control sd above the null** - the gross is the forecast, not the construction. Clause 4's
cost check is also much cleaner than F-7's: the selection premium (real cost minus its own
control's cost) is **+0.484 bps** here against F-7's +1.7, because a plain decile at one decision a
day does not preferentially buy the low-priced reverse-split leveraged names the conviction gate
went hunting for.

**(4) And it is refused, on the clause that was fixed before the run.** Clause 7 asks for t > 2
pooled and >= 5 of 8 positive years. It gets **5/8 years** (2019 -317, 2020 +1,273, 2021 +595,
2022 -642, 2023 -422, 2024 +865, 2025 +350, 2026 +923) and **t +1.47**. **0 of 20 cells pass.**
The 20-cell grid is not a search that got unlucky - it is four books x five labels with every
parameter fixed in advance, and its best cell is the one the ladder predicts.

**(5) The decisive number is the power arithmetic, and it closes the track rather than deferring
it.** t scales as sqrt(sessions), so t +1.47 on 1,933 sessions needs **3,558 sessions - 14.1 years
of out-of-sample** - to reach t = 2 at this effect size. The Alpaca SIP store begins 2016-01-04,
the walk-forward burns three years to train and validate, and the ceiling is therefore **~7.7
years**. **This finding cannot be resolved on the data this repository can obtain, ever.** F-7 was
refused for lack of power and could at least name a longer window; F-8 is refused for lack of power
and the window does not exist. That is a different and final kind of refusal.

**(6) Regimes: the label effect is concentrated exactly where the mandate wants it, which does not
rescue it.** By causal trailing 20-session SPY realized-volatility tercile:

| regime | sessions | gross bps (close) | gross bps (h1) | cost bps | net $/day | t |
|---|---|---|---|---|---|---|
| low vol | 645 | 2.369 | 1.728 | 2.714 | -69 | -0.22 |
| mid vol | 644 | 4.970 | 1.496 | 2.709 | +452 | +1.31 |
| high vol | 644 | 5.421 | 1.279 | 2.751 | +534 | +1.28 |

The h1 column is flat-to-falling across the terciles while the `close` column more than doubles, so
the horizon effect is a volatility effect: in calm markets a 30-minute and a five-hour forecast are
worth the same and neither is worth much; in volatile ones the multi-hour forecast is worth 4.2x
the 30-minute one. Conditioning on the high-vol tercile is not a rescue - it is the same t (+1.28)
on a third of the data, and the tercile cut is itself a parameter that was not pre-registered as a
book.

**(7) Feature-importance stability got WORSE with the better label, and that is the strongest
argument against the finding.** Permutation importance per retrain on the `close` label, 38
features, 8 retrains, `data/f1/importance_f8.csv`. Spearman rank correlation between retrains runs
**0.147 to 0.798, mean ~0.42**, against F-7's 0.665-0.767 on three retrains, and **0 of 38 features
have a positive importance in all 8 retrains** while **30 of 38 flip sign**. The top of the ranking
has also moved: F-7's `close`-free model led with the VWAP-displacement family, this one leads with
the volume family (`vol_rel6`, `m_rvol_ratio`, `rvol_ratio`, `cs_rvol_ratio`) and `vwap_atr` has
fallen to 15th. A model whose validation-set importances change sign every year is not reading a
stable object, and the honest reading of (2) + (7) together is that **the horizon effect is real and
the model that exploits it is not stable** - which is exactly the shape of an edge too small to
resolve.

**Decision: REFUSED, and the F track closes.** The supervised class is now priced four ways.
F-1 refused the 30-minute book on cost (0.797 bps against 2.392). F-3 refused the daily horizon on
absence (0.304 bps, IC t +0.18). F-7 refused the low-turnover construction on power (3.495 against
3.697, t -0.15 on this same 1,933-session window). F-8 refuses the correctly-labelled forecast on
power again - but this time **with a positive edge column (+1.532 bps) and a named, unreachable
data requirement (14.1 years)**. Clause 0 said F-8 should be the last item on this track unless it
clears the hurdle outright; it did not clear it, so the track closes. `champion.json` untouched,
`live/` untouched, nothing filed in `BLOCKERS.md` - a finding that needs 14 years of minute data
nobody sells is not an owner option.

**Do not re-open as a label, horizon, book or model question.** The label axis is now swept end to
end (30 min / 2 h / 3.5 h / 5 h / to-the-flatten), the book axis was exhausted by F-7 (dwell, band,
EWMA, conviction, decile, and the stacked cells), and the learner was deliberately held fixed so
the label effect would be readable - swapping in LightGBM would confound the one clean comparison
this iteration produced. The only honest way to reopen the class is **more independent
cross-section**, not more history: the panel is 56 names, and the pooled t is a breadth statistic
as much as a length one. That is a data-track question (a 500-name Alpaca universe), not an ML one,
and it is filed as **F-9 (parked, needs the D track first)** rather than as an open ML item.

**Three durable pieces survive the refusal.**
(a) **The label ladder method**: hold the book, the turnover and the learner fixed and vary only the
training label, then read gross bps per dollar turned. It converts F-7's cheap persistence table
into a book number and it is reusable by any future forecaster on this repo.
(b) **`close` is the right label for this sleeve** and `h4`/`h7`/`h10` are not, because a fixed
horizon is only defined on the early slots and silently confounds horizon with time of day. Any
future intraday supervised work should train on time-to-flatten.
(c) **A bug fix in `scripts/ml_f7.py`**: `vol_regime()` reindexed SPY's `datetime.date` keys against
the panel's string day keys, so **F-7's clause-6 regime table silently returned "n/a" for every
session**. Both sides are now normalised to `str`. F-7's published conclusion does not depend on it
(F-7 was refused on the power extension, not on regimes), but its regime clause was never actually
answered and now can be.

**Standing jobs**: none on this track. A-5 part 2 and S-17 part 2 belong to `iterate`/`daily`.

**Next**: nothing on the F track. F-9 is parked behind a D-track universe expansion; if the `daily`
or `iterate` tracks ever want the horizon finding, the one transferable claim is that **on this
universe a multi-hour intraday forecast is worth ~3x a 30-minute one per dollar traded, and the
gap is entirely a high-volatility phenomenon.**

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
