# Research journal - `daily` track

The S-track (daily champion `s1_momo`, LEAN, `scripts/sweep_s*`, `scripts/evaluate.py`). Newest
first. The pre-2026-09-12 history of this track is in `research/journal.md`, which stays the
daily review's merge target; each entry here leaves a one-paragraph pointer there.

## 2026-09-13 - S-42: the ensemble loses on the signal axes, and on the way to finding that out it clears the incumbent of the charge S-40 convicted the crisis switch of

**Hypothesis (S-42, opened by S-41).** S-41's weight-blend of the 36-cell crisis-switch grid
failed the promotion bar on return and won on drawdown - a verdict S-41 itself said was
confounded, because the crisis switch is a RISK dial and "less CAR, less MaxDD" is a statement
about exposure rather than about ensembling. S-41 also found the 36 cells held the *identical
name set* on 86.83% of sessions: that ensemble was "a vote on GROSS", the one shape where
weight-averaging and return-averaging are the same object. Run the clean version on the axes
S-38 labelled FITTED that are **not** risk dials, where higher CAR at equal drawdown is
unambiguously better and the cells disagree about **membership** instead of size.

New `scripts/sweep_s42.py` (8 clauses pre-registered in the docstring before the first
simulation, `results/s42_full.txt`, 128 DIAGNOSTIC rows `daily/s42_blend`). Grid, every value
taken from S-38's own list for that axis and the shipped point inside each, 3 x 3 x 4 = **36
cells** so the count matches S-41 exactly: `mom_skip` {2, **5**, 10} x `mom_lookbacks[3]`
{220, **252**, 300} x `top_n` {2, **3**, 4, 5}. `rank_persist` and `entry_mode`/`min_momentum`
are excluded **and the exclusion is a decision, not an omission**: both are OFF in the shipped
book, so a grid over them is an on/off ablation with the incumbent on the boundary, and an
ensemble would mix "should the feature exist" with "at what level". No LEAN run, no parameter
moved, no shared-code change at all - S-41's `weights_fn` was already in place. `champion.json`,
`live/*`, `margin_budget`, `target_vol`, `target_exposure`, the drawdown cap and every scheduled
task untouched.

**(1) The licence, and one clause S-41 did not need.** 1a reproduces the deployed cell at
`delta 0.00e+00 / +0 orders` (22.192150170492%, 5,052). 1b re-earns S-41's weight-extraction
licence on this grid - extracted weights fed back match to the digit on CAR *and* order count.
1c is new and is specific to these axes: unlike the regime pair, they **move `history_bars`**
(5 distinct values, 307 to 360, against a constant 307 in S-41's grid), which would silently
give cells different session counts and break S-41's own "every row on the same session count"
rule. Asserted rather than assumed: 2012-01-03 sits at index 3,524 of a 7,213-bar store, so the
window start dominates `history_bars` and all 36 cells share **one** date set (3,689 FULL /
1,677 OOS, 1 distinct set each). Every path-fed book is then executed with the *shipped*
`Params()`, which is exact because `legs_simulate` reads `params` only for `i0` and the traded
universe once `weights_fn` is supplied - so all 36 cells, both blends and both selectors run
through one identical rebalance and differ in nothing but their weights.

**(2) The finding that was not the hypothesis, and it is the more valuable half.** Clause 3 is
S-40's own diagnostic - where does the shipped cell rank in its grid - re-run on the axes that
pick names. It comes out the **opposite way round**:

| window | shipped CAR | grid mean | vs mean | rank | S-40's crisis switch, same window |
| --- | --- | --- | --- | --- | --- |
| IS 2012-2019 | 16.488 | 14.144 | **+2.344** | **4 of 36** | -0.932, **24 of 36** |
| FULL 2012-2026 | 22.192 | 19.468 | +2.724 | 2 of 36 | +1.341, 14 of 36 |
| OOS 2020-2026 | 29.124 | 25.963 | **+3.161** | **5 of 36** | +4.260, **1 of 36** |

S-40 found the crisis-switch cell is the **argmax of its own grid on the half labelled OOS and
below the median on the half labelled IS** - the signature that located AUD-11. The signal cell
is top-decile on **both** halves and above the grid mean by a similar margin in each. Post hoc
(clause 3b, labelled as such): IS-to-OOS rank correlation across the 36 cells is **Spearman
-0.206 / Pearson -0.323** - *negative*, against S-40's +0.208 / +0.330 - the IS top-3 cells land
at OOS ranks 18, 30 and 16, and **0 of 36 cells beat the shipped cell on CAR in both halves**.
Said with its own limits, because this is the sentence a critic should attack: on a surface with
negative cross-half correlation the expected number of cells anywhere in the grid that are
top-5 in both halves is 36 x (5/36)^2 = **0.69**, and exactly one was observed, so "some cell is
top-5 twice" is at chance. What is not at chance is that it is the **pre-specified incumbent**:
for one cell named in advance that is a ~1.9% event under independence and rarer under the
measured negative correlation. **The selection inflation S-38 priced on this sleeve lives in the
crisis switch, not on the axes that choose names** - and on these axes S-38's distance-above-
grid-mean is realized in *both* halves rather than being hindsight.

**(3) The hypothesis itself. The ensemble is a membership vote here, exactly as predicted, and
it loses anyway.** Clause 4b's pre-registered contrast fires hard: the blend's name set is
identical to the shipped cell's on **1.90% of FULL sessions (4.15% OOS)** against S-41's 86.83%,
it holds **4.88 names** against the shipped 2.47, and it owns 2.87 names per session the
incumbent does not. So this really is the shape weight-blending was supposed to be good at - and
clause 6 confirms the netting is real, the first time that has been shown on this book:

| FULL, fully charged | orders | ord/yr | turn/yr | fees |
| --- | --- | --- | --- | --- |
| shipped | 5,054 | 345 | **49.4** | 19,121 |
| weight-blend36 | 11,472 | 784 | **33.9** | 16,662 |
| ratio | 2.27x | - | **0.69x** | 0.87x |

S-41's blend traded 1.26x the orders at 0.99x the turnover; this one trades 2.27x the orders at
**0.69x** the turnover for 0.87x the fees. Netting 36 membership opinions into one order list
saves 31% of turnover - the pre-registered "if turnover falls, the netting story is real" branch.

**(4) And it is still refused, fully charged in S-22 cell C.**

| book | FULL CAR / Sharpe / MaxDD | OOS CAR / Sharpe / MaxDD |
| --- | --- | --- |
| shipped | 19.640 / 1.047 / 24.037 | 25.967 / 1.151 / 24.040 |
| weight-blend36 | 17.482 / 0.986 / **23.397** | 23.177 / 1.098 / **23.397** |

Paired against the shipped cell: FULL **-0.784 bps/day at t -2.08**, OOS -0.994 at t -1.54.
Clause 7: Sharpe FAILS both windows, CAR FAILS both (-2.158 FULL, -2.790 against a -1.0
allowance), MaxDD PASSES both, band test PASSES (0.086% of target weight below the 0.01x band
against a 10% bar). **NOT a promotion candidate.** Clause 4c: deleting the shipped cell from the
grid moves Sharpe by -0.0000 / +0.0012 / -0.0036 - the blend is a property of the ensemble, not
a costume for the incumbent. Note the FULL t of **-2.08**: this sleeve's fourth statistic past
|t| = 2 after S-31's arithmetic, S-33's re-selection and S-38's, and it is *against* the
candidate.

**The mechanism, and it is the reusable rule.** The blend loses 2.158 CAR points while trading
31% less turnover and paying 13% less commission, so the loss is **not cost - it is dilution**.
A book that holds 3 names at 1.25x gross and is handed 4.88 instead is funding names the
momentum score ranked 4th to 9th out of nine, at the same total exposure. On the crisis switch
the 36 cells agreed on membership and voted on gross, so averaging cost nothing; here they vote
on membership, and **averaging a concentrated ranking is the same operation as widening it**.
That is why the drawdown improves (0.64 points, in both windows) and the return does not: the
blend is a de-concentration dressed as an ensemble.

**(5) The decision bar, clause 8 - and this is where S-42 diverges from S-41 completely.** The
selector is built here rather than quoted, because these axes had none, and it is built better
than S-40's: the selection is expressed as a **weights path** (`wf[t] = w of the cell chosen for
year(t)`) and executed through `weights_fn`, so each boundary switch is a real trade at a real
spread and S-40's year-stitch bound is gone rather than estimated. 2,684 sessions, fully charged:

| book (2016-01-04..2026-09-04, cell C) | CAR | Sharpe | MaxDD |
| --- | --- | --- | --- |
| **shipped** | **21.951** | **1.114** | 24.037 |
| weight-blend36 | 19.615 | 1.063 | **23.397** |
| walk-forward, CAR selector | 17.970 | 0.943 | 25.769 |
| walk-forward, Sharpe selector | 17.251 | 0.989 | 25.172 |

Both selectors pick the shipped cell in **0 of 11 years** (7 and 4 boundary switches) and both
lose to it by **~4 CAR points** - real-time selection is harmful on these axes too, which is
what a negative cross-half rank correlation predicts. The blend beats both selectors (+1.645 /
+2.365 CAR, +0.120 / +0.074 Sharpe, -2.4 / -1.8 drawdown points), reproducing S-41's clause 7b
result. **But unlike S-41, the incumbent beats everything on the decision bar as well as on the
promotion bar.** S-41's two-sentence verdict was "the blend is not a better cell than the one
that shipped; it is a better book than choosing a cell". S-42's is one sentence: on the axes
that choose names, **the cell that shipped is better than the blend and better than choosing** -
so the ensemble's only remaining argument, that the incumbent is unfindable, does not apply here.

**Decision: nothing promoted, nothing moved, nothing filed for the owner.** The blend is refused
on its own pre-registered bars. The incumbent's parameters are not touched - they are, if
anything, better supported than before this ran.

**Next.** The dilution diagnosis is testable and it is the item worth taking: the ensemble's
gain (0.64 drawdown points, 31% less turnover) and its loss (2.16 CAR points) may be separable,
because the loss is the blend's **width** and the gain is its **smoothness**. The object that
keeps one without the other is a rank VOTE rather than a weight AVERAGE - blend the 36 cells'
rankings, truncate the result to `top_n=3` by blended weight, renormalize to the deployed gross,
and execute that. If truncation recovers the CAR while keeping the drawdown and turnover gains,
the ensemble is worth having and it was only ever mis-specified. Filed as **S-43**.

## 2026-09-13 - S-41: the ensemble is worth having, the reason it was opened is not, and the two facts are independent

**Hypothesis (S-41, opened by S-40).** S-40 proved no real-time selector can find the shipped
`regime_threshold=1.50 / regime_vol_window=20` cell - a walk-forward argmax over the same 36 cells
picks it in **0 of 11 years** under either objective - while the equal-weight blend of all 36,
which requires no selection at all, carried the best Sharpe and the lowest drawdown in S-40's
table. S-40's blend averaged the 36 cells' **returns**, which is 36 accounts each paying its own
commission. Build the implementable object: average their target **WEIGHTS**, one account, one
order list, netting 36 opinions before anything trades, fully charged in S-22 cell C.

New `scripts/sweep_s41.py` (7 clauses pre-registered, `results/s41_full.txt`, 21 DIAGNOSTIC rows
`daily/s41_blend`). No LEAN run, no parameter moved; `champion.json`, `live/*` and every scheduled
task untouched. One shared-code change: a default-inert `weights_fn` on the RESEARCH harness
`sweep_s25.legs_simulate` (S-26/S-28/S-30/S-32 precedent), re-proved bit-identical by clause 1a.

**(1) The licence.** Clause 1a reproduces the deployed cell at `delta 0.00e+00 / +0 orders`
(CAR 22.192150170492%, 5,052 orders). Clause 1b is the one that matters and is new: the shipped
cell's weights are **extracted day by day and fed back** through the same simulator, and the
resulting book matches to the digit on CAR *and* order count. Extraction is the same object the
in-loop call produces, so a blend of 36 extractions is executed through the deployed rebalance and
not through a friendlier one. Everything below stands on that; nothing below would have been
readable without it.

**(2) Weight-averaging and return-averaging turn out to be the same book here.** This was the open
question the item was built on, and the answer is that the distinction the item worried about does
not exist on this sleeve:

| window | weight-blend CAR / Sharpe / MaxDD | S-40 return-average | gap |
| --- | --- | --- | --- |
| FULL | 20.980 / 1.127 / 23.327 | 20.992 / 1.127 / 23.389 | -0.012 / 0.000 / **-0.062** |
| IS | 17.451 / 1.146 / 20.273 | 17.485 / 1.147 / 20.250 | -0.034 / -0.001 / +0.023 |
| OOS | 25.082 / 1.138 / 23.346 | 25.076 / 1.137 / 23.407 | +0.006 / +0.001 / -0.061 |

Three windows, agreement to 0.034 CAR points and 0.001 Sharpe. Clause 4 says why, and it is a fact
about the book rather than about averaging: the blended target holds at most **3 names**, and on
**86.83%** of FULL sessions (85.61% OOS) it holds the *identical name set* as the shipped cell and
differs only in size. On 0.00% of sessions does the shipped cell hold something the blend does not.
**The ensemble is a vote on GROSS, not on which names to own** - so there is almost nothing to net
across the 36 opinions, and the return-average's "36 independent rebalances" advantage is worth
0.03 CAR points because the 36 rebalances are nearly the same rebalance.

**(3) The correction, and it withdraws this item's own opening sentence.** S-41 was opened on "the
blend carried the best Sharpe (**1.173**) ... beating even the hindsight-shipped cell's drawdown on
FULL (23.389 vs 23.860)". Those numbers are not from comparable rows. S-40's blend row is
`grid equal-weight (same span)`, **2,684 sessions** - the 2016-2026 walk-forward span - while
`shipped` at 1.159/23.860 is **3,689 sessions** of FULL. Put every book on S-40's own span
(clause 3b):

| 2,684 sessions, zero cost | CAR | Sharpe | MaxDD |
| --- | --- | --- | --- |
| shipped | 24.705 | **1.228** | 23.860 |
| weight-blend36 | 22.932 | **1.174** | 23.327 |
| off | 28.021 | 1.169 | 36.619 |

My 1.174 reproduces S-40's return-average 1.173 to 0.001 - a third confirmation of clause 2 - but
the shipped cell on those sessions is **1.228, not 1.159**. **The blend never had the best Sharpe.**
The drawdown half of the claim survives by luck: the blend's worst drawdown is the 2020 crash,
which lies inside both spans, so 23.389 really is the same number either way. The Sharpe half does
not survive and is withdrawn. Reusable rule, and this is the second time this month the same shape
has bitten (S-40 corrected S-38): **a number quoted from a table is only a comparison if the row it
is compared against has the same session count.** 2,684 against 3,689 is not a finding, it is a
span.

**(4) Fully charged, S-22 cell C (2 bp one-way spread + IBKR Pro financing on the historical EFFR).**

| book | FULL CAR / Sharpe / MaxDD | OOS CAR / Sharpe / MaxDD |
| --- | --- | --- |
| shipped | 19.640 / 1.047 / 24.037 | 25.967 / 1.151 / 24.040 |
| weight-blend36 | 18.544 / 1.016 / **23.751** | 22.043 / 1.025 / **23.823** |
| off | 22.317 / 1.026 / 36.892 | 26.759 / 1.045 / 36.909 |

Paired daily difference against the shipped cell: FULL **-0.396 bps/day t -0.92**, OOS **-1.296
bps/day t -1.64**. Said out loud as always: neither crosses |t| = 2, and nothing on this sleeve has
except S-31's arithmetic, S-33's re-selection and S-38's.

**(5) Costing halves the only prize.** The drawdown gain is **-0.533 points** at zero cost on FULL
and **-0.286** once charged; OOS **-0.509** becomes **-0.217**. The blend's entire claim is about a
quarter of a drawdown point.

**(6) The netting saving did not happen, and the reason is the mechanism working.** The blend
trades **1.26x the orders** of the shipped cell at **0.99x the turnover** for **1.01x the fees**
(6,353 vs 5,054 orders; 434/yr vs 345/yr). More orders, the same turnover: gross now ratchets in
1/36 steps instead of jumping 0 -> 1, because on **39.01% of FULL sessions (40.19% OOS)** between 1
and 35 cells are risk-off and the book holds a fractional position no single cell holds. That
fractional boundary is the smoothing that buys the drawdown point, and its cost is paid in order
count. Executability is not the constraint anyone expected it to be: only **0.002%** of blended
target weight (0.005% OOS) falls below the 0.01x no-trade band, against a pre-registered 10% bar,
and the band is a fraction of equity so the verdict does not move with account size.

**(7) The blend does not lean on the cell that shipped.** Deleting the shipped cell and blending
the other 35 moves Sharpe by **-0.0013 FULL / +0.0030 IS / -0.0048 OOS** - ties on a 0.05 bar. The
result is a property of the ensemble, not a costume for the incumbent.

**Decision on the pre-registered bar: NOT a promotion candidate.** Against the shipped cell, fully
charged, Sharpe FAILS on both windows (1.016 vs 1.047; 1.025 vs 1.151), MaxDD PASSES on both, CAR
FAILS on both (-1.096 FULL, -3.924 OOS against a -1.0 allowance). Nothing ships, and nothing could
have: a 36-cell blend is not expressible in one `Params()`.

**And the bar the decision above is the wrong instrument for (clause 7b).** Clause 7 compares the
blend to the shipped cell, which is correct for a promotion and wrong for a decision, because S-40
proved the shipped cell is not on the menu - a selector picks it in 0 of 11 years. Against what a
selector *actually gets*, on the identical 2,684 sessions:

| book | CAR | Sharpe | MaxDD | source |
| --- | --- | --- | --- | --- |
| shipped (hindsight) | 24.705 | 1.228 | 23.860 | S-40 |
| **weight-blend36** | **22.932** | **1.174** | **23.327** | clause 3b |
| grid mean of per-cell CAR | 22.734 | n/a | n/a | S-40 |
| walk-forward, CAR selector | 21.345 | 1.011 | **38.185** | S-40 |
| walk-forward, Sharpe selector | 21.046 | 1.000 | **38.185** | S-40 |

The blend beats the CAR selector by **+1.587 CAR / +0.163 Sharpe / -14.858 drawdown points** and
the Sharpe selector by **+1.886 / +0.174 / -14.858**, and it edges the grid mean itself (+0.198)
because rebalancing between the cells is not the same as averaging their accounts. **The blend is
not a better cell than the one that shipped; it is a better book than choosing a cell.** Both
sentences are true and together they are the whole result: the shipped cell keeps its place because
the promotion gate compares to the incumbent, and the ensemble is what this dial should have been
built as if the question were being asked fresh today.

**Next.** The comparison that would actually move the book is not another blend of this dial - it
is whether the same ensemble trick pays on the axes S-38 labelled FITTED that are *not* risk dials,
where a CAR grid is a fair instrument and the drawdown-for-return trade S-40 corrected does not
confound it. Filed as S-42. A shipped 36-cell blend would also need a signal-level change to
`algorithms/s1_momo/signals.py` plus its own LEAN run; that is real work and it is not worth doing
for a quarter of a drawdown point, so it is filed and not started.

## 2026-09-13 - S-40: the crisis switch is a drawdown instrument nobody could have tuned, and the shipped cell is the best of 36 on the half labelled out-of-sample and below median on the half labelled in-sample

**What this iteration is.** S-38 closed AUD-11's lower bound and left one number sitting on the
table: the two biggest contributors to this sleeve's selection inflation, by a wide margin, are
the two halves of the crisis switch - `regime_vol_window` **+3.596** ("the one dial in the
parameter set with NO selection record anywhere") and `regime_threshold` **+3.016**, against
`mom_skip` at +0.074. S-38 measured how far the shipped cell sits above its grid mean, which is a
statement about hindsight. It never asked the question that decides whether those 6.6 points are
an asset or an accounting artefact: **could a selector running in real time have found that
cell?** And, prior to that, **is the switch worth anything at all?** `risk_on` has been in this
book since S-1 and has never been ablated end to end - S-1 refused the *original* below-median
filter and a 200-day trend filter, and the crisis multiple that replaced them was adopted on a
table and never revisited. New `scripts/sweep_s40.py`, seven clauses pre-registered in the
docstring before the first simulation; console output in `results/s40_full.txt`; 118 DIAGNOSTIC
rows under `daily/s40_regime`.

**(1) Identity.** `22.192150170492255% / 5,052 orders`, delta `0.00e+00` - the cell S-25, S-26,
S-28, S-30, S-31, S-32, S-33, S-36, S-37 and S-39 each quote.

**(2) The ablation, and the assertion that licenses the walk-forward.** `regime_threshold = 1e9`
against a maximum observed `vol / median` of **7.80** makes the gate unreachable, so the switch is
off; the shipped cell fires on **590 of 3,689** sessions in 29 episodes, and mean gross on those
sessions is **0.122x against 1.464x** on the rest, which is the vectorized mask agreeing with the
simulation. Separately, and this is what makes clause 4 exact rather than approximate: at the
shipped defaults `dd_halve = dd_flat = 9.0` while `drawdown_multiplier`'s `dd = 1 - last/peak` is
bounded by 1.0, so the overlay returns 1.0 on every session and `equity_curve` - its **only**
consumer in `target_weights` - cannot reach the weights. Target weights are a pure function of
(prices, params), so a year-by-year stitch is exact up to the one rebalance at each boundary,
which clause 4 counts (3 and 4 switches, **<= 0.024 CAR points**) instead of waving at.

**(3) The joint 6x6 surface, zero cost - and the smoking gun for AUD-11.** Where the shipped
`thr=1.50 win=20` ranks among the 36 cells:

| window | shipped CAR | grid mean | vs mean | percentile | rank |
| --- | --- | --- | --- | --- | --- |
| IS 2012-2019 | 16.488% | 17.420% | **-0.932** | 36th | **24 of 36** |
| FULL 2012-2026 | 22.192% | 20.851% | +1.341 | 64th | 14 of 36 |
| OOS 2020-2026 | 29.124% | 24.864% | **+4.260** | 100th | **1 of 36** |

**The shipped crisis-switch cell is the argmax of its own grid on the half this repository labels
out-of-sample, and below the median on the half it labels in-sample.** S-33 and S-38 argued
AUD-11 from aggregate percentiles; this is the same claim as a single cell, and it is not
survivable as a coincidence - the chance a cell chosen without reference to 2020-2026 lands rank 1
of 36 there is 1 in 36. The switch is where AUD-11 lives.

**(4) The walk-forward, which is the hypothesis. The selector never once finds the shipped cell,
and loses to a coin flip.** Each year Y from 2016, the selector sees only 2012-01-03..(Y-1)-12-31 -
a backtest anyone could have run on 31 December - and takes that window's argmax. Two objectives,
because the choice of objective is itself a researcher degree of freedom. 2,684 sessions:

| book (2016-01-04..2026-09-04) | CAR | Sharpe | maxDD |
| --- | --- | --- | --- |
| walk-forward, argmax CAR | 21.345% | 1.011 | **38.185%** |
| walk-forward, argmax Sharpe | 21.046% | 1.000 | **38.185%** |
| grid equal-weight (all 36) | 22.916% | **1.173** | **23.389%** |
| grid mean of per-cell CAR | 22.734% | - | - |
| shipped (hindsight) | 24.705% | 1.228 | 23.860% |
| off (switch never fires) | 28.021% | 1.169 | 36.619% |

`CAR` picks 1.75/30 -> 1.75/40 -> 2.00/20 -> 1.75/40; `Sharpe` picks 1.75/30 -> 1.75/40 ->
2.00/20 -> 1.50/60 -> 1.75/40. **The shipped cell is chosen in 0 of 11 years by both.**
Walk-forward minus grid mean is **-1.389** (CAR) and **-1.688** (Sharpe) CAR points, which is the
pre-registered **branch (c): selecting this dial in real time is HARMFUL and the shipped cell's
distance above the grid mean is hindsight in full.** It is worse than that, because the
walk-forward book also carries the **worst drawdown of the six**, 38.185% - so real-time selection
is dominated by turning the switch off on both axes at once (+6.675 CAR, -1.565 DD points) and
dominated by the do-nothing ensemble on risk. The mechanism is visible in the ranks: IS-to-OOS CAR
across the 36 cells is weakly positive (Spearman **+0.208**, Pearson +0.330) and the IS **top-3
average +3.625 CAR points above the IS bottom-3** out of sample, so the grid is not pure noise -
but the **IS argmax specifically pays -2.102 against the grid mean**, and the argmax is the only
cell a selector takes. Weak rank information plus an argmax is worse than no selection.

**(5) So is the switch worth anything? Yes - and not one point of it is return.** Fully charged
(2 bp one-way plus IBKR Pro financing on the historical effective fed funds rate, S-22's cell C):

| window | cell | CAR | Sharpe | maxDD | paired vs shipped |
| --- | --- | --- | --- | --- | --- |
| FULL | shipped | 19.640% | 1.047 | 24.037% | - |
| FULL | off | 22.317% | 1.026 | **36.892%** | +1.139 bps/day, **t +0.96** |
| OOS | shipped | 25.967% | 1.151 | 24.040% | - |
| OOS | off | 26.759% | 1.045 | **36.909%** | +0.608 bps/day, **t +0.30** |

**Turning the crisis switch off buys +2.68 CAR points at t +0.96 and costs 12.9 points of maximum
drawdown**, and it costs Sharpe on both windows (-0.021 FULL, -0.106 OOS). The return difference
is not resolved at |t| >= 2 on either window; the drawdown difference is not a statistic at all,
it is a fact about 2020-02 and 2022. **The switch is a drawdown instrument that has been read as
a return instrument, which is why its grid looks so wide: a CAR grid over a risk dial measures
the risk dial doing its job, exactly the trap S-38 built its FITTED/RISK-POSTURE classification
to avoid - and S-38 classified both these axes FITTED.** That classification is the one thing in
S-38 this iteration corrects: `regime_threshold` and `regime_vol_window` are dials that trade
return against drawdown by construction, so their +3.596 and +3.016 are not cleanly selection
inflation, and S-38's headline **+1.25 to +2.07** is an over-estimate by an unmeasured amount
concentrated in those two axes. The *label* finding (AUD-11) survives untouched and is in fact
strengthened by clause 3; the *size* of the inflation is now known to be biased upward.

**DECISION: keep the switch, ship nothing.** The ablation is refused by the promotion gate on its
own terms and I did not have to make the call - `champion.json`'s `criteria` carry
`max_drawdown_limit: "35%"` and `drawdown_tolerance_points: 1.0`, and `off` breaches both (36.892%
absolute, +12.9 points against the champion). The drawdown cap is the owner's and I do not touch
it. No parameter moved, `champion.json` untouched, `live/*` and all scheduled tasks untouched, no
LEAN run.

**(6) The by-product, and it is the only thing here worth building.** The equal-weight blend of all
36 cells needs **no selection at all** and over the walk-forward span delivers **Sharpe 1.173 and
maxDD 23.389%** - the best Sharpe and the lowest drawdown of every book in the table, and it beats
the hindsight-shipped cell's drawdown on FULL (23.389 vs 23.860) and OOS (23.407 vs 23.855).
Against the shipped cell it gives up return, and the gap is entirely the hindsight: -0.421 bps/day
at t -0.98 on FULL, -1.304 at t -1.64 on OOS, +0.316 at t +0.74 on IS - the sign flips with the
window, which is what a hindsight advantage looks like. Filed as **S-41**. It is implementable
(average the 36 cells' target weights, not their returns) and it converts the sleeve's single most
fragile decision into one that does not have to be made. What it is NOT is free: the blend holds a
fractional book on every risk-off boundary, so its turnover and its live tracking need pricing
before any claim.

**Gates.** No shipped or runner-loaded file touched, so no `--replay` and no `compare_orders.py`
is owed; `scripts/sweep_s40.py` is new and standalone and imports `sweep_s19`, `sweep_s25` and
`sweep_s31` read-only. `tests/` unchanged. `research/champion.json`, `live/APPROVED_PAPER.md`,
`live/HALT*` and the three scheduled tasks untouched.

**Provenance, and it is the same defect S-39 recorded yesterday, one day later.**
`scripts/sweep_s40.py` and this iteration's `research/backlog.md` edits are in **`3a7b764`**,
whose message belongs to the `futures` track (*"record where the multi-contract work landed, and
the rule that keeps losing it"*). My `git commit -F msg -- <paths>` - the exact form S-39
prescribed - lost a HEAD race (`cannot lock ref 'HEAD': is at 3a7b764 but expected 8d5ddb6`) and,
in the seconds between my `git add` and that retry, the `futures` track committed **without a
pathspec** and swept the shared index. Nothing is lost or altered; both files are byte-correct in
`3a7b764`. **S-39's rule was necessary but not sufficient:** `git commit -- <paths>` protects you
from someone else's *staged* work, but it cannot protect your own staged work from someone else's
pathspec-less commit, and a new file must be staged to be committed at all. The complete rule is
therefore **both halves** - commit with an explicit pathspec, *and* never `git add` until the
commit is the very next command - and even then a track that commits without a pathspec can take
an untracked file you staged. That last hole is a property of the shared index, not of my
sequencing, and it has now cost two consecutive iterations their commit message.

**Next.** S-41 (the ensemble) is now this track's highest-value open item and needs no trading day
and no owner. Behind it: S-17 part 2 is still starved (10 fills over 3 sessions, unchanged since
2026-09-11 - 2026-09-12 planned but placed no orders), and AUD-11's relabel is still a manual edit
to a reserved file that only the owner or the critic may make - though clause 3 above means the
replacement text should now cite the switch as the mechanism, not just a percentile.

---

## 2026-09-13 - S-39 (C-5a/b/c): the gate was one-sided because the fix was assigned to a source that was never fixed - and the frame it admitted is worth nothing, which is why it is a defect

**What this iteration is.** `critic` filed three defects against S-37, all three owned by this
track. C-5c is the one that could cost money, so it is the hypothesis; C-5a and C-5b are closed
alongside it because C-5a is the script that *verifies* S-37 and I could not re-run S-37's own
numbers without repairing it first.

**(C-5c) The defect, and the thing the finding did not say.** `scripts/paper_trade.py:main()`
picks its history on one line:

```
closes = fetch_history_yf(...) if (args.history == "yfinance" or ib is None) else fetch_history_ib(ib, ...)
```

and the two sources had **opposite conventions**. `fetch_history_yf` dropped today's unfinished
bar (`closes.index < today`); `fetch_history_ib` applied **no date filter at all**, so
`reqHistoricalData(endDateTime="")` at the deployed 15:45 ET task time returned a bar for the
session **in progress**. That row became `as_of`, the signal ranked on it, `plan_orders` sized
shares at it - and `data_faults` passed it, because its staleness clause tested `day < prev`
only. The part the finding did not say, and the part worth carrying: **the one-sidedness was
deliberate.** `tests/test_paper_dataquality.py:104` asserted `== []` for exactly this frame,
under the docstring *"That is a different defect and this gate must not double-report it as
staleness"* - and S-37 then never fixed the source it had just assigned the defect to. The hole
was held shut by nothing but the deployed task passing no arguments. **A defect assigned to a
fix is not a defect fixed, and a test can make the assignment permanent.**

**The fix, both ends, because half the argument was right.** `fetch_history_ib` now applies the
same date filter as `fetch_history_yf` (the source), and `data_faults` reports `day > prev`
under **its own message** rather than as staleness (the gate) - which is precisely what S-37's
"must not double-report" objection was protecting, so nothing is given up. A new test asserts
the two messages are disjoint and that exactly one can fire. **Six existing tests moved**: they
passed `good.index[-2].date()` as `prev_session` while `as_of` was `good.index[-1]` - an
off-by-one against the live contract, where `fetch_history_yf` drops today and so the frame's
last row **IS** `previous_session(today)` (`previous_session`'s own docstring says so, and
`verify_c5.py --stage b` prints the live frame at `as_of == prev`). They were only ever passing
because the clause was one-sided.

**(C-5c, the measurement) What the admitted frame actually did to the book - new
`scripts/sweep_s39.py`, 5 clauses pre-registered in the docstring before the first simulation.**
Closing the hole was never in question; **what kind of hole it was** was. A 15:45 print of
session D is *fresher* than the close of D-1, so the frame the gate admitted might well have
made the book more money - which would make this a latent unauthorized **clock change** (the
BLOCKERS.md pre-open question, acquired by accident) rather than a latent data corruption. Same
fix, completely different journal entry, and the loop does not get to guess.

Both books **fill at the same real 15:45 print**, so they are paired to the instant and differ
in one thing only - whether the signal saw today's partial bar. Decision price is the close of
the **15:44** ET bar and the fill the close of the **15:45** bar, so nothing reads a price it
could not have had; both are carried onto the daily store's adjusted scale as a within-day ratio
`px_adj = close_adj x (px_raw / close_raw)` (S-24's implied-factor trick), which cancels every
difference between a split-adjusted minute store and a split-and-dividend-adjusted daily one.
Data: six ETFs (`DIA GLD TLT XLE XLF XLK`) fetched into the Alpaca SIP store to join the three
already there; **all nine priced on 2,683 of 2,683 sessions**, the same count S-24 found.

**(1) Identity.** `22.192150170492255% / 5,052 orders`, delta `0.00e+00`. **(2) Two controls.**
`partial` fed a flat ratio reproduces `bound` at max |equity difference| **0.000e+00**, so the
ratio store injects a price and nothing else; and isolating the *fill* alone, S-19's stand-in
(close[i]) reads 22.211% against the real 15:45 print's **22.602%**, so S-19's convention was
mildly pessimistic by ~0.39 CAR points. **(3) The cells**, 2016-2026, fully charged (2 bp +
IBKR Pro financing):

| cell | signal window ends | CAR | Sharpe | maxDD | orders |
| --- | --- | --- | --- | --- | --- |
| deployed | close[i-1] | **22.602%** | 1.145 | 23.887% | 3,617 |
| partial (the hole) | px[i, 15:44] | 22.483% | 1.147 | 24.346% | 4,009 |
| bound (impossible) | close[i] | 22.162% | 1.134 | 24.103% | 3,976 |

**THE FRAME THE HOLE ADMITTED IS WORTH -0.049 BPS/DAY AT t -0.08** (-0.032, t -0.05 at 0 bp).
Not better, not worse, not resolved at |t| >= 2 - which triggers the pre-registered branch that
creates **no owner-facing option**. Both halves agree (2016-2019 16.466 vs 16.660; 2020-2026
38.285 vs 38.500).

**(4) And yet it rewrites the order list on 76.7% of sessions** - 1,757 of 2,682 with a
*different set of names*, only 299 with the same names at different sizes - for **+10.2% more
orders (4,002 vs 3,630) and no return**. That is the whole finding in one line: the partial bar
is pure noise (it sits 24-32 bps sd from its own session's close) injected into the last row of
the ranking window, it flips the top-3 on three sessions in four, and the gap against `deployed`
**widens with the cost model** (-0.067 CAR at 0 bp, -0.119 fully charged) because the only thing
it reliably buys is turnover. **A decision input that changes the decision three-quarters of the
time and the P&L not at all is not fresher information; it is a coin flip with a commission
bill.**

**(5) The reusable result, and it is about S-19 rather than about C-5c.** `bound` gives the
signal **close[i] - a price 15 minutes after it decides** - and it still loses, -0.141 bps/day
at t -0.24. S-19 priced this sleeve's clock at ~1.9-2.1 CAR points and it is easy to read that
as "fresher data is worth money"; **S-19 never varied what the signal reads.** Both of its rows
(backtest and deployed) read `close[i-1]` and differ only in where the order *fills*. This is
the first cell on this sleeve to move the **read** instead, and it is worth **zero even with
look-ahead**. So the pre-open move in BLOCKERS.md is a **fill-moment** question end to end, and
nothing about it gets better by giving the signal a fresher input - consistent with S-25, which
found the payoff is overnight and the intraday content is nil.

**(C-5a) The verification script could not run on the code S-37 shipped.** `sweep_s37.py`
clause 1 sliced `paper_trade.py` as text on `"missing = [s for s in universe"` - **S-37's own
pre-patch text, which S-37's patch deleted** - so at HEAD it raised `ValueError: substring not
found` and took clause 2, the script's headline, down with it before it ran. Re-anchored on the
gate's call site (`faults = data_faults(`), with a guard so a source-grep can never again be the
thing that fails, and `--stage a` now runs end to end and reproduces clause 2 to the digit.
**A clause that verifies a patch by matching the text the patch removes can only ever run once.**

**(C-5b) The owner-facing break-even was quoted from the wrong cell** - corrected in place
above and in `research/journal.md`: **two to four bad prints a year**, not 2.0. The MATERIAL
verdict is unchanged and was never at risk.

**Gates.** `scripts/compare_orders.py` **PASS, 3,689/3,689 dates, 5,021 orders both sides**.
`tests/` **all pass on py -3.14**, the interpreter the 09:25 launch gate runs (`exit=0`); on
py -3.11 the only four failures are the `futures` track's parquet tests, which fail at HEAD for
want of `pyarrow` on that interpreter and have nothing to do with this change.
`tests/test_paper_dataquality.py` is 19 pass, up from 16. No LEAN run, no ledger row, **no
strategy parameter touched**, `champion.json` untouched, `live/*` and all scheduled tasks
untouched. The deployed path (yfinance, no arguments) produced an identical frame before and
after this commit; the new fault is a belt-and-braces assertion that should fire on zero
sessions.

**Next.** C-4 is the only open non-owner item left on this track's queue and it belongs to
`critic`. The standing S-17 part 2 (measured daily fill slippage against the 15:45 print) is now
much cheaper than it was, because this iteration built the nine-name 15:45 price store it needs.

**Provenance, because the hash does not say `daily`.** All seven files of this iteration landed
in **`0193f21`**, whose message is the `eng` track's (`scorecard: name the writer that is missing
provenance...`). They were staged and awaiting a `.git/index.lock` held by a concurrent track for
ten minutes; that track then committed **without a pathspec** and swept the whole shared index,
this iteration included. Nothing is lost or altered - every file above is byte-correct in
`0193f21` and was verified there - and nothing is rewritten, because another track's work is in
that commit. This entry is the record instead. The operational lesson is for AGENTS.md's own
rule: "commit ONLY the files you touched" needs to be **`git commit -- <paths>`** rather than
`git add <paths> && git commit`, because the second still commits whatever another track has
staged in the shared index while you were waiting for the lock. `git add -A` is not the only way
to take someone else's work.

---

## 2026-09-12 - S-38 (AUD-11 part 2): the floor was not the estimate, and the two dials with the weakest paper trail are the two that move it most

**What this iteration is.** S-33 priced AUD-11 on three of this sleeve's dials, measured the
shipped set at **+0.974 CAR points above its 18-cell grid mean** on 2020-2026, and closed with
an explicit caveat: `top_n`, `target_vol`, `regime_threshold`, `regime_vol_window` and
`target_exposure` are unpriced, so **"+0.5 is a floor on total selection inflation, not an
estimate."** That sentence is the only open, human-free, no-trading-day item this track had
left, and this iteration closes it by running **all eight** axes - S-33's three verbatim as a
reproduction check, plus the five it named.

**Provenance and scope.** New `scripts/sweep_s38.py` (seven clauses pre-registered in the
docstring before the first simulation; console output in `results/s38_full.txt` and
`results/s38_full_v4.txt`, cell cache `results/s38_cache.pkl`). **No LEAN run, no strategy
parameter changed, no shipped or runner-loaded file touched**, so no deploy gate and no
`--replay` is owed; `champion.json`, `live/*` and all three scheduled tasks are untouched.
`target_vol`, `target_exposure` and `margin_budget` are the owner's and are **read** here,
never changed. 123 unique books, 10 workers, 410 s.

**(1) Identity.** The harness reproduces the cell nine previous iterations agree on exactly -
**22.192150170492255% / 5,052 orders**, 2012-2026 at zero cost.

**(2) The five are not one kind of thing, and this was written down before the grid ran.**
Classifying each axis from the record that set it is the clause that could have made the whole
estimate wrong, because summing a CAR grid over a *size* dial would charge selection inflation
for the owner's own risk decision:

| axis | class | what set the value |
| --- | --- | --- |
| `mom_skip`, `alloc_vol_window`, `mom_lb4` | FITTED | S-10 / S-12 / S-9 full-period tables |
| `top_n` | FITTED | S-7/S-8 CAR grids ("`top_n=3` is a local peak") |
| `regime_threshold` | FITTED | a table value; re-run as a shelf by S-29 |
| `regime_vol_window` | **UNRECORDED** | **no table and no stated rationale anywhere** |
| `target_vol`, `target_exposure` | RISK-POSTURE | the owner's mandate and leverage budget |

An UNRECORDED value is treated as FITTED, because a value nobody wrote a reason for cannot be
defended as a priori. So **6 of 8 axes enter the estimate** and the two risk dials are reported
but not summed.

**(3) Clause 4 was meant to be a formality and it is the first finding.** S-33's three axes,
re-run cell for cell, gave **+0.877 / 65th percentile / rank 5 of 20** against its published
**+0.974 / 78th / 14 of 18**. Nothing had changed in the code: the gap is entirely **two
counting conventions S-33 used and did not state**. (a) The shipped cell sits on every axis and
is *one book*, so it is counted **once** per pool - 7 + 6 + 7 = 20 cells is **18 unique**.
(b) "rank 14 of 18" counts the cells at **or below** the shipped one, so the percentile is
`<=`, not `<`. Under both, all five statistics reproduce to the third decimal - **+0.974,
77.778th, 14 of 18, premium -0.049** - and only then is the eight-axis number reportable.
**Reusable rule: a published percentile or rank is not reproducible without its counting
convention; state "unique cells, inclusive rank" or the same grid gives two different answers
0.1 CAR points apart.**

**(4) The estimate. The floor roughly doubles, and the pre-registered branch is (c).**
Shipped OOS CAR 29.124% at 0 bp, against the grid it was chosen from:

| pool | unique cells | grid mean | grid sd | shipped - mean | sd | pct |
| --- | --- | --- | --- | --- | --- | --- |
| S-33's three axes | 18 | 28.150 | 1.832 | **+0.974** | +0.53 | 78 |
| the three new fitted axes | 15 | 25.871 | 2.284 | **+3.253** | +1.42 | 93 |
| risk-posture (not summed) | 9 | 28.736 | 1.638 | +0.388 | +0.24 | 78 |
| **ESTIMATE - all fitted axes** | **32** | **27.051** | **2.331** | **+2.073** | **+0.89** | **84** |

**+2.073** clears the pre-registered 2.0 boundary into branch (c) - *"the label is not the
problem, the number is"* - by 0.073 points, which is too close to the line to state without its
own attack. So the obvious one was run rather than left to the critic.

**(5) POST-HOC, and it pulls the number back: a null that includes cells the promotion gate
would refuse is too weak.** Seven of the 32 fitted cells breach the shipped drawdown plus
`evaluate.py`'s own 1.0-point tolerance (`regime_threshold=2.0` at **38.19%** OOS MaxDD,
`regime_vol_window=10` at 30.56%, `top_n=5/6`, `mom_lb4=300`, `regime_threshold=1.75`,
`regime_vol_window=15`). A selector could never have shipped them. Restricted to the **25
risk-feasible** cells the estimate falls to **+1.254** (+0.69 sd, 80th percentile), which is
branch (b). **The honest range is +1.25 to +2.07 CAR points**, and both ends say the same
thing: **S-33's floor of ~+0.5 was not the estimate.**

**(6) The mechanism, countable rather than argued.** Selection ran on FULL 2012-2026, and
2020-2026 is *inside* it, so a full-period argmax is partly an out-of-sample argmax. That is
AUD-11's whole thesis and it can simply be counted: **the shipped value is the OUT-OF-SAMPLE
best cell of its own axis on 3 of the 6 fitted axes** - `mom_lb4`, `regime_threshold`,
`regime_vol_window` - against **0.99 expected** under no selection. Exact Poisson-binomial
**P(X >= 3) = 0.060**. Suggestive, short of 0.05, and said out loud as such.

**(7) The two axes that carry it are the two with the weakest paper trail, and both are the
crisis switch.** Per-axis, shipped minus grid mean: `mom_skip` **+0.074** (57th percentile - a
dead heat, exactly as S-33 found), `alloc_vol_window` +0.565, `top_n` +1.826, `mom_lb4` +1.947,
`regime_threshold` **+3.016** (1.45 sd), `regime_vol_window` **+3.596** (1.32 sd). The largest
single contributor is the one axis in the whole parameter set for which **no selection record
exists** - grep finds `regime_vol_window` only in S-36's window-guard audit and in AUD-11's own
list, never in a table - and the second largest is its partner in `risk_on`. The sleeve's
momentum dials are honestly placed; its **regime switch is where the 2020-2026 figure was
bought**, and S-29 already reported that removing that switch entirely earns +2.68 CAR points.

**(8) `target_exposure` is inert, and the range was measured rather than asserted.** All five
grid values give a **byte-identical book** (29.124% / 1.262 / 23.855% / 2,267 orders, grid sd
**0.000**). The mechanism was already in `signals.py:351-352` - `sigma` is proportional to the
exposure request, so `target_vol / sigma` cancels it - but the *range* was not: probing
0.25 .. 10.0 puts the cancellation break at **0.875**, where `scale_cap=2.0` starts to bind.

| `target_exposure` | 0.25 | 0.5 | 0.875 | 1.0 | **1.75\*** | 3.0 | 5.0 | 10.0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OOS CAR% | 10.035 | 20.304 | 29.124 | 29.124 | **29.124** | 29.124 | 29.124 | 29.124 |
| mean gross | 0.408 | 0.816 | 1.206 | 1.206 | **1.206** | 1.206 | 1.206 | 1.206 |

The shipped 1.75 sits **2.0x above the point where the dial does anything at all**. It
contributes exactly zero selection inflation, it cannot be tuned, and - the part that matters
to a reader of `BLOCKERS.md` - it is **not the leverage lever it reads as**. The book's size is
set by `target_vol`, `scale_cap` and `margin_budget`; `target_exposure` only matters if someone
turns it *below* 0.875.

**(9) Clause 6: a sum of coordinate deltas is not a joint delta, by a factor of two.** The
full-period argmax over the fitted axes is `mom_skip=10 regime_threshold=2.0
regime_vol_window=60`. Its coordinate deltas sum to **+8.492**; run jointly the delta is
**+4.004** (additivity error **-4.488**, against a pre-registered 0.5). So the coordinate sum of
**+11.023** over all six axes is rejected and **+2.073 / +1.254 - the shipped set's position
against the pooled grid, which is S-33's estimator and comparable to its +0.974 - is the number
to quote.** Anyone totalling selection inflation by adding axes will overstate it about 2x.

**(10) The honest number, and nothing here reaches |t| = 2.** Fully charged (cell C: 2 bp
one-way plus IBKR Pro financing on the historical effective fed funds rate) the shipped set
prints **25.967% / 1.151 / DD 24.040%** on 2020-2026. The joint full-period argmax set prints
**21.707% / 0.931 / DD 40.191%** - *worse on both axes*, paired **-1.174 bps/day at t -0.65** -
which is S-33's -0.049 selection premium showing up as a book rather than a statistic: choosing
every axis on the full period buys nothing out of sample and costs 16 points of drawdown. The
cell-C charge on this book is **-3.157** points, and the fitted grid's 0 bp OOS range is
22.201 .. 30.846 (median 27.320), so **the honest fully-charged 2020-2026 band of this
parameterization is roughly 19.0 .. 27.7%, median 24.2%**, against the 25.967% the shipped set
prints.

**Decision. Nothing promoted, nothing shipped, no default changed.** `champion.json`,
`live/*`, `signals.py` and the scheduled tasks are untouched; the one thing this iteration
earns is a **number for AUD-11's still-open relabel**, whose replacement text in
`research/backlog.md` said "~+0.5 CAR points" and now says **+1.25 to +2.07**. That edit is a
manual write to `champion.json`'s `note`, which AGENTS.md reserves and which S-34 established
no promotion can carry (`--promote` has never written `note`), so it stays where S-33 and S-34
left it - the owner's or the critic's restore-with-evidence path. **No new `BLOCKERS.md` item
was filed**: the ask is unchanged and already recorded, only its magnitude moved, and the owner
should not be asked the same question twice.

**One disclosure.** The first run of `sweep_s38.py` wrote **145** ledger rows under
`daily/s38_selection` of which **123 are unique**: the shipped cell sits on all eight axes and
the writer emitted it once per axis. The 22 repeats are identical copies of a correct row. The
ledger is append-only so they stay; the writer now deduplicates, and the corrected clause-4/5
analysis was re-run with `--no-record` against a cached grid rather than appending a second
copy of the whole sweep.

**Standing jobs both ran and neither had new input.** `daily_fills.py`: unchanged at 3
sessions / 10 fills / $2.37M, execution **+3.2 bps** against the auction it aimed at (per-fill
sd 14.1, **se 4.5**), `ref_price` the previous close in 10 of 10. S-17 part 2 still needs
trading days, not another sweep.

**Next.** This track's last human-free, trading-day-free research item is now closed. What
remains is S-17 part 2 (needs fills), the owner pile in `BLOCKERS.md`, and one thing this
iteration opened that is *not* a research item: **`regime_vol_window=20` is the largest single
contributor to the published OOS figure and has no written rationale.** The honest next move
is not to re-tune it - S-33's -0.049 premium says tuning it predicts nothing - but to record
why 20, or to record that nobody knows.

## 2026-09-12 - S-37 (AUD-13): two bad prints a year spend the whole selection premium, and the audit's own remedy is right for a reason its tail test gets backwards

**What this iteration is.** S-36 signed off saying the `daily` track had no audit item left that
needs no trading day. That was wrong about **AUD-13**, which is filed `[daily+eng]`, names the
daily signal module and the daily runner, and requires nothing from the account. So this one
took it. It is three defects filed as one bullet, and they are not the same kind of thing: two
are *silent* - the book holds a different portfolio and nothing in the log says so - and one is
*loud and wrong*, liquidating the whole account under `regime_reason "SPY missing"`, a string
that reads like a risk decision.

**Provenance and scope.** New `scripts/sweep_s37.py` (seven clauses pre-registered before the
first number; console output in `results/s37_stage_{a,b1,b2,b3,c}.txt`), a patch to
`scripts/paper_trade.py`, `tests/test_paper_dataquality.py` (17 tests) and one line in
`tests/conftest.py`. **No LEAN run, no ledger row, no strategy parameter changed**, and
`research/champion.json` was not touched. `paper_trade.py` IS the live runner, so the deploy
gate is owed here and was run. No shared research code was modified either: `legs_simulate`
calls `sig.target_weights` by module attribute, so the defect injector installs itself on that
attribute and corrupts the **real decision frame at the real decision site** - every number
below is what the shipped signal, the shipped rebalance and the shipped cost model actually do
with bad data, not what an assumed flatten would cost.

**(1) Identity, and this one the account can reach.** The offline book reproduces the cell eight
previous iterations agree on **exactly** - 22.192150170492255% / 5,052 orders, delta 0.00e+00 -
both before and after the patch. The scheduled task "Quant Paper Rebalance" passes **no
arguments**, so the account runs `--history yfinance`, the path this defect lives on. Walking
the source from the `warning: no history for [...]` print to `plan_orders` finds **0 exits**:
the warning was the entire response. With SPY present the signal funds 3 names and reports
`risk-on`; with the column dropped it funds **0** and reports `SPY missing`. So unlike S-32..S-36
this is not a preventive report.

**(2) The flatten, priced at an outage rate, and the number the owner can act on.** Dropping
`REGIME_TICKER` from the decision frame on a random p of sessions, five seeds:

| cost | rate | events/yr | CAR% | cost | per outage | break-even | t |
|---|---|---|---|---|---|---|---|
| 0 bp | 1 in 252 | 0.93 | 22.064 | -0.128 | -0.138 | 3.6 /yr | 0.90 |
| 0 bp | 1 in 21 | 11.34 | 19.854 | -2.338 | -0.206 | 2.4 /yr | 3.10 |
| 2 bp | 1 in 252 | 0.93 | 20.820 | -0.176 | -0.190 | 2.6 /yr | 1.24 |
| 2 bp | 1 in 21 | 11.34 | 18.137 | -2.860 | -0.252 | 2.0 /yr | 3.85 |

**MATERIAL: between two and four bad prints a year** against a pre-registered threshold of 12.
~~**the tightest break-even is 2.0 outages a year** ... i.e. two bad yfinance prints in a year
cost 0.5 CAR points~~ **CORRECTED 2026-09-13 by S-39 (C-5b, found by `critic`).** "2.0 outages
a year" is the 1-in-21 cell's break-even, and that cell runs at **11.34 outages/yr - 11x the
rate the sentence itself describes**. The cell matching the sentence's own rate (1-in-252,
0.93/yr) gives **2.6/yr at 2 bp and 3.6/yr at 0 bp**, so the honest range is two to four. The
defence offered for quoting across cells - "the cost per outage is the same size in both" - is
measured at **1.50x apart at 0 bp and 1.33x at 2 bp**, and the original sentence took the
larger each time. Carrying the five-seed sd through, the matching cell is 2.6/yr with a +/- 1 sd
band of **[1.5, 13.6]**, whose upper end is past the materiality threshold of 12. **The MATERIAL
verdict and the decision are unchanged and were never at risk**: the gate's cost is bounded by
its FALSE-POSITIVE rate, which C-5 measured at 0 of 501 live yfinance sessions, so shipping it
is right at any outage rate. The low-rate cells are underpowered on their own (t 0.90 / 1.24,
13.6 events) and **the 1-in-21 cells carry the significance** (t 3.10 / 3.85) - which is exactly
why the break-even must be read off the matching cell and the t-stat off the powered one, rather
than both off whichever is more flattering. Reproduce with `py -3.11 scripts/verify_c5.py
--stage d`, or read the table above, where the 2.6 and 3.6 have always been printed. The cost rises with the cost model - 0.138 -> 0.190 at 0 -> 2 bp - so the
audit's "a full round trip at real spread" is right, and the round trip is visible in the order
count too: the flatten arm sends **5,395 orders against the control's 5,052**.

**(3) The all-NaN column: the audit's example is the third worst, and the CAR column is the
wrong one to read.** `target_weights` runs `dropna(axis=1, how="all")` first, so a failed
download is not an error, it is a smaller universe. Corrupting each traded name in turn, 171
sessions, 1 in 21, seed 11:

| name | CAR delta | funded set differs | | name | CAR delta | funded set differs |
|---|---|---|---|---|---|---|
| SPY | +0.245 | **83.6%** | | XLF | -0.008 | 29.8% |
| XLK | -0.562 | 60.8% | | IWM | +0.198 | 21.6% |
| QQQ | -0.291 | 53.2% | | GLD | -0.619 | 19.3% |
| | | | | XLE | -0.149 | 14.0% |
| | | | | DIA | +0.094 | 12.9% |
| | | | | TLT | +0.044 | 10.5% |

**MATERIAL, but not on the column the pre-registration listed first.** The CAR column is a
single seed and clause 2 measured the seed sd at this rate at **1.689**, so *none* of these CAR
deltas clears noise and three of them print positive. What clears is the set column: every one
of the nine names changes the funded set on **10.5% to 83.6%** of corrupted sessions, 10x to
84x the 1% threshold. That is the finding, and it is a stronger one than a CAR number would
have been: **the defect is not a bias, it is noise injected into the portfolio**, so there is
no direction to correct for and the only available remedy is to refuse. The audit names
XLK->QQQ; XLK is 60.8% and ranks third, behind SPY at 83.6% and QQQ at 53.2%.

**(4) The stale price is real in one of its two halves.** Over 33,210 name-days the one-session
move on this universe is median **0.593%**, p75 1.134%, p90 1.841%, **p95 2.441%**, p99 4.124%,
and **29.70% of name-days move more than the 1% no-trade band**. A last-row NaN is
forward-filled, `paper_trade.py` then sizes shares at that stale close, so the realized weight
is wrong by the move: at p95 the runner mis-sizes by **2.4x the amount it refuses to trade
for**. MATERIAL. But *ranking* on a stale close is worth **+0.033 / +0.002 / -0.095 / -0.007**
CAR points across the four cells - nothing, against a seed sd of 1.7. **The damage is entirely
in the sizing column and none of it is in the signal**, which the audit filed as one defect.

**(5) The clause that decides the fix, and the reference column that decides the clause.** The
audit prescribes `exit 3`, i.e. hold yesterday's book for a session. Both responses on the same
corrupted sessions, five seeds, 1 in 21:

| arm | CAR% | delta | Sharpe | MaxDD% | worst day% | orders |
|---|---|---|---|---|---|---|
| control | 22.192 | - | 1.159 | 23.860 | -8.143 | 5,052 |
| flatten | 19.854 | -2.338 | 1.076 | 23.304 | -8.143 | 5,395 |
| hold | 21.983 | **-0.209** | 1.150 | 23.906 | -8.143 | 4,921 |

Holding is **11x cheaper** than flattening in CAR and wins Sharpe. The pre-registered tail test
compared the two arms to each other and **failed** - hold's MaxDD 23.906 is 0.602 points worse
than flatten's 23.304 - and that test asked the wrong question, because **the flatten arm's
drawdown is BELOW the control's**: randomly liquidating the book is accidental de-risking, so
the defect flatters itself in exactly the column the remedy is being judged on. Against the
book the runner exists to reproduce, holding costs **+0.046 drawdown points**, 4.6% of the
promotion gate's own `drawdown_tolerance_points` of 1.0 (S-34). The audit's prescription is
taken, and the tail statement is the corrected one. Worst day is -8.143% in all three arms: no
outage landed on the worst session in any seed, so neither arm is being priced on a tail event.

**(6) The gate's false positives, counted before the gate was written.** The audit's predicate
as filed - "any universe column has a NaN close" - fires on **0 of 3,690 sessions** of the
reference daily store, so the withdrawal condition did not trigger and it is taken as filed.
The narrowing to names that have already printed a close is kept anyway and is free at 0/3,690:
the store the runner actually reads is yfinance, not this one, and a universe name added before
its own inception must not be able to stop the account.

**(7) What shipped, and what was refused.** `data_faults()` returns every fault in one list
(missing column, all-NaN column, last-row NaN, empty frame, `as_of` older than the previous
session) and `previous_session()` supplies the clock; the runner calls them **before
`call_signal`**, which is the whole safety property and is pinned by a test that reads the
source order. Held-but-untargeted names are deliberately not checked - refusing over the
retired TQQQ would block the sale this runner exists to make. **`signals.py` was not touched**:
the runner now refuses before `risk_on` can be reached from the account, the LEAN side is
covered by clause 6's 0/3,690, and an edit to a live-loaded file that buys nothing measurable
is refused on S-35's precedent.

**Gates.** Post-patch identity **exact** (delta 0.00e+00, 5,052 orders); `compare_orders.py`
**3,689/3,689**; the gate run against today's real yfinance frame is **clean** (`as_of`
2026-09-11 = `previous_session` 2026-09-11) and fires correctly on all three defects injected
into that same frame; suite **593 pass / 6 skip** on 3.11 and the intraday launch preflight on
the 3.14 interpreter is **green** (641 passed, replay OK).

**Two things found on the way.** (a) The new test file tripped E-8's
`test_every_runner_importer_is_classified` - a file importing a live runner must be declared
gating or not - and it is declared **gating**, because every assertion is on pinned dates and a
fabricated frame, so it cannot fail for a reason outside the code. That is C-3's rule satisfied
rather than dodged. (b) **`CALENDAR.trading_days` does not enforce the calendar's own coverage
contract.** Past `coverage_end` (2027-12-31) it keeps answering from the weekday rule instead
of raising; only `check_covered` raises. A gate trusting `trading_days` alone would be handed a
holiday as "the previous session" and would refuse the entire rebalance over it. Worked around
here by calling `check_covered` explicitly and pinned by a test; filed as **AUD-13b [eng]**
because the fix belongs in `quant_brain`.

**Reusable rule.** *Price a remedy against the thing it is supposed to restore, not against the
defect it replaces.* A defect that destroys return by accident can also reduce drawdown by
accident, and then a remedy that fixes the return looks reckless in the risk column against it.
Holding costs 0.602 drawdown points against the flatten and 0.046 against the control; only the
second number is about the remedy.

**Next.** No `daily` audit item remains that needs no trading day - AUD-11's residue is a manual
edit to a reserved file and stays the owner's or the critic's. What is left for this track is
S-17 part 2 and the two standing measurement jobs, all of which need a trading day, plus the
owner pile in `BLOCKERS.md`.

## 2026-09-12 - S-36 (AUD-25): the guard that exists to stop a silent 0% CAR covers one parameter out of eleven, and the audit named the smaller half of the defect

**What this iteration is.** S-35 named **AUD-25** as the last `daily`-owned audit item that
needs no trading day, and it is the reason no earlier iteration took it: it is six separate
claims filed as one bullet, with no single number that decides it. So this one priced each on
its own pre-registered threshold and shipped only what earned it. Two are material, one has the
wrong **sign** in the audit, two are documentation, and one belongs to another track.

Both standing measurement jobs ran first, as on every iteration since S-31, and it being a
Saturday neither has new input: `daily_fills.py` still reads **10 fills / $2,373,115 /
+3.2 bps** against the auction the runner aims at (per-fill sd 14.1, se 4.5), `ref_price` the
previous close 10 of 10.

**Provenance and scope.** New `scripts/sweep_s36.py` (seven clauses pre-registered before the
first number; console output in `results/s36_stage_{a,b,c}.txt`), patches to
`algorithms/s1_momo/signals.py`, `algorithms/s1_momo/main.py` (comment only) and
`scripts/sweep_s3.py`, and `tests/test_signals_windows.py` (14 tests). **No LEAN run, no ledger
row, no strategy parameter changed**, and `research/champion.json` was not touched. `signals.py`
IS loaded by the paper runner, so unlike S-32..S-35 the deploy gate is owed here and was run.

**(1) Identity, and the deployed book stands outside four of the six.** The offline book
reproduces the cell seven previous iterations agree on **exactly** - 22.192150170492255% /
5,052 orders, delta 0.00e+00 - both before and after the patch. `S1_ML_SCORES` is unset,
`trend_window` is 0, the paper task runs `--history yfinance`, and `blended_momentum` is on no
deployed path, so **(a), (b), (c) and (e) are all unreachable from the account**. Only (d) is
executed on every LEAN run, and it is inert. So this is a preventive report about the
*research machinery*, and that is what makes clause 3 the item rather than clause 2.

**(2) The window guard, which is the real finding, and the audit named its smaller half.**
`Params.__post_init__` says in its own docstring that it exists so "the horizon is what is
being tested", and it computed `need` from `mom_lookbacks`, `mom_skip` and `rank_persist` only.
Enumerating all eleven integer windows and probing each with its companion switch ON gives
**7 of 11 outside the guard, in TWO failure modes**:

| class | count | fields |
|---|---|---|
| SILENT-ZERO | 2 | `trend_window`, `regime_vol_window` |
| SILENT-TRUNCATE | 5 | `alloc_vol_window`, `regime_median_window`, `vol_est_window`, `mom_vol_window`, `trail_window` |
| SAFE | 4 | `iv_scale_window`, `mom_skip`, `rank_persist`, `mom_lookbacks` |

The audit named the SILENT-ZERO half (its example is `trend_window`). **SILENT-TRUNCATE is the
worse one and it is not in the audit.** `.iloc[-N:]` quietly yields fewer than N bars, so two
different values of the parameter are the *same cell*: all five produce **byte-identical
weights** at `history_bars + 100` and at `+ 500`. A zero CAR is visible in any table. A grid
that reports a flat shelf because its cells are the same run is not - and S-33 established on
this very sleeve that **a shelf is the only parameter result worth reporting**, so this defect
manufactures exactly the artefact this track treats as its strongest evidence.

Fixed by making `need` the max over every price window, each carrying its own prerequisite (a
window over `pct_change` needs one extra row; the regime median runs on a series a rolling std
has already shortened by `regime_vol_window`). **`iv_scale_window` is deliberately excluded**
and the exclusion is pinned with its reason: it reads the IV store, not `prices`, so
`history_bars` does not bound it and it already fails loudly with `iv_scale_reason="uncovered"`.
That exclusion was earned, not assumed - the first pass of the probe classified it
SILENT-TRUNCATE because `iv_scale_power=0` made the whole function return early, i.e. it was
measuring the feature's default rather than the field. Re-probing with the switch on, and then
classifying on the collapse test itself rather than on a reason string, moved it to SAFE.

**(3) The ML rank gate: the audit is right about the code and the fix is the prose.**
`ML_MODE="rank"` adds the momentum floor to `eligible`, then overwrites `score` with the
forecast, after which the caller's own `scores[t] > floor` applies `min_momentum` to the
*forecast* as well - two positive numbers where the docstring promised one. On the real export
(`data/f3/ml_scores.csv`, 3,690 sessions) the second gate removes a funded name on **398 of
them (10.79%)**, **525 name-days of 8,086**. It reaches a lot of sessions and it is worth
**+0.286 CAR points** - 11.086% / 0.699 shipped against 10.800% / 0.686 as documented - i.e.
**the undocumented gate helps**, and by less than S-33's 0.5-point "cosmetic" bar. Per the
pre-registration ("a gate that has been measured and works is not changed to match prose") the
code stands and the docstring is corrected. **The consequence for S-27 is worth stating: its
twelve ranked rows were run WITH this gate, so they are flattered by ~0.3 points, not
penalised by it** - which is the opposite of what "gated on two signs" reads like.

**(4) The S-3 harness gap, where the audit's SIGN is wrong.** `sweep_s3.simulate` earns
`close[i] -> close[i+1]` on a decision made at close[i]; LEAN fills at the next open, so the
`close[i] -> open[i+1]` segment is credited to a position that did not exist. The overnight gap
is **49.9% of the average close-to-close step** on that 59-name universe, so the exposure is
large. But "credits the gap" implies the harness is flattered, and it is **penalised**: zero
cost, full period, **c2c 2.559% CAR / 0.268 Sharpe against o2o 5.851% / 0.516** - the shipped
convention costs the S-3 book **3.291 CAR points**. A reversal signal is on the losing side of
the overnight segment (the gap continues the move; the reversal is intraday), so crediting it
the gap is a charge, not a gift. **It does not revive S-3**: at the harness's own 5 bps both
conventions are deeply negative (**-8.967% / -0.732** against **-4.811% / -0.330**), so the
refusal stands for the reason it was given, which was cost. What changes is that the published
margin was never as wide as the table said. Fixed with a default-inert `step_mode` argument
(the S-26/S-30/S-32 precedent) so every earlier row stays bit-identical.

**(5) and (6), the two that are documentation.**
`minimum_order_margin_portfolio_percentage = 0.002` at `main.py:191` is **inert**: the engine
reads it at 17 call sites across `Common/` and `Algorithm/` - `PortfolioTarget.Percent`,
`ImmediateExecutionModel`, `BuyingPowerModel.GetMaximumOrderQuantityFor{Target,Delta}` - and
**none is on the `MarketOrder` path**, which is the only path `submit_targets` uses. The band
that actually binds is the repository's own `min_order_value` (0.01, S-32 re-priced and kept
it). The line is **labelled rather than removed**, because removing it would owe a LEAN rerun
to prove `OrderListHash` unchanged for zero measured gain - the same trade S-35 made on
`paper_trade.py:196`. `blended_momentum` has **zero call sites and zero load references** by
AST over all 158 python files, so the audit's arithmetic is right - but it is **not
unreferenced**: `sweep_f3.py:432` names it as the spec its own momentum rebuild must match,
which is how the F-3 forecast and the champion's score are held comparable. Deleting it would
turn that comparison's only written definition into a prose claim, and `sweep_f3.py` is the
`ml` track's. Kept and documented.

**(7) `--history ib`, which is PREVENTIVE and not this track's to fix.** `fetch_history_yf`
drops today's unfinished session explicitly; `fetch_history_ib` passes `endDateTime=""` and
does not, so it would rank on a partial bar. **The shipped scheduled task uses the yfinance
default**, so the deployed runner cannot reach it. The fix is a two-line edit to a live runner
and belongs to `eng` with a `--replay`; filed as **AUD-25b** rather than made here.

**Withdrawal condition, which was backward compatibility as in S-34 and S-35, and it holds.**
Identity re-run after the patch: **exact, delta 0.00e+00**, `history_bars` still 307 and
`DEFAULTS == Params()`. `scripts/compare_orders.py`: **3,689/3,689 dates, LEAN 5,021 / runner
5,021, +0, PASS**. `sweep_s3` at its default `step_mode="c2c"`: **2.559% / 0.268 / 36.034**,
unchanged. Full suite **615 pass** (601 + this item's 14), 0 fail.

*(Note on the suite: under `py -3.11` four `test_qb_*` tests fail on a missing `pyarrow` in
that interpreter - a pre-existing environment gap unrelated to this diff, since none of them
imports anything S-36 touched. The suite is green on the interpreter that has `pyarrow`.)*

**Adds no research item and closes one audit item** - the last `daily`-owned one. It files one
new audit item, **AUD-25b** (`eng`), for the half of (c) that needs a live-runner edit.

**Reusable rule.** *A silent failure that produces a WRONG number is easier to catch than one
that produces the SAME number twice.* Every guard in this repository was written against the
first kind (S-9's 0% CAR, AUD-16's truncated day, AUD-10's stale column) because a wrong number
shows up in a table. The five fields S-36 found collapse two grid cells into one identical run,
which renders as a clean flat shelf - and a shelf is precisely what S-33 taught this track to
trust. **So before quoting a shelf, check that its cells are different runs.**

## 2026-09-12 - S-35 (AUD-12): one row in the ledger passes the gate today and would put a strategy on the paper account that the runner cannot trade - it claims +1.914 CAR points and delivers 0.000 of them

**What this iteration is.** S-34 named **AUD-12** as the next daily audit item that needs no
trading day, and named the shape it expected: *"same as this one: a promotion that does not carry
everything the champion is."* That is right and it understates it. AUD-10 left the wrong *number*
behind after a promotion; AUD-12 leaves the wrong *strategy* on the account.

The mechanism, three files deep and each one individually reasonable. `algorithms/s1_momo/main.py`
builds its `sig.Params(...)` from `S1_*` environment variables - that is how every sweep in this
repository moves a parameter without editing a shipped file, and it is deliberate (E-2). Nothing
carries those overrides anywhere else:

- `scripts/paper_trade.py:196` asks for `getattr(sig, "PARAMS", None)`. `signals.py` defines
  `DEFAULTS`, never `PARAMS`, so the expression is `None` on every run and `target_weights` falls
  through to `params or DEFAULTS`. **The live runner always trades the defaults.**
- `scripts/compare_orders.py:158` builds `sig.Params()`. **The deploy gate compares the defaults
  with the defaults**, so it agrees with itself whatever was promoted - 3,689/3,689, every time.
- `scripts/evaluate.py --promote` wrote `stats`, `run_dir`, `commit`, `tag` and `stats_by_spread`
  and **no `env` at all**, so after the promotion the override was not even in the record.

Both standing measurement jobs ran first, as on every iteration since S-31, and it being a
Saturday neither has new input: `daily_fills.py` still reads **10 fills / $2,373,115 / +3.2 bps**
against the auction the runner aims at (per-fill sd 14.1, se 4.5), `ref_price` the previous close
10 of 10.

**Provenance and scope.** New `scripts/sweep_s35.py` (seven clauses pre-registered before the
first number; console output in `results/s35_stage_{a,b,c}.txt`), a patch to `scripts/evaluate.py`,
and `tests/test_evaluate_param_env.py` (20 tests). **No LEAN run, no ledger row, no strategy
parameter and no runner-loaded file** - `evaluate.py` is shared code but nothing in `live/` imports
it, so no `--replay` is owed. `research/champion.json` was **not** modified: `git diff` on it is
empty, and both the promotion clause and the end-to-end promotion tests write to scratch copies.

**(1) Identity, and the defect is preventive.** The offline book reproduces the cell six previous
iterations agree on **exactly** - 22.192150170492255% / 5,052 orders - and it does so on the
**union** price frame both books of clause 5 need, so adding IEF to the frame is *proven* inert
rather than assumed, and the two books are comparable on one load. Today's champion is clean:
`champion.json` carries no `env` key and its own ledger row `20260911T145705Z` recorded `{}`. So,
as with AUD-10, the answer to "has the deployed book ever been the wrong one" is **no**.

**(2) The reach surface, and why the fix has to be an allow list.** Re-derived from `main.py` by
AST rather than from memory: it reads **56** `S1_*` names, of which **49 reach the code the runner
shares** and **7 do not** (`S1_START`, `S1_END`, `S1_SLIPPAGE_BPS`, `S1_SIGNAL_LAG`,
`S1_FINANCING`, `S1_FIN_SPREAD`, `S1_FIN_RATES`; `S1_NOOP` is allow-listed and no longer read at
all). A deny list would have to name 49 keys and be re-derived every time a knob is added. The
allow list names 7 and fails safe, and one of the 49 is why the derivation cannot simply read the
`Params(...)` call: **`S1_PROXY` is not a Params argument** - it mutates `signals.LEVERED_PROXY`,
a module global, so a promoted 3x book would paper trade unlevered parents.

**(3) The defect reproduces on a real row, not a constructed one.** `20260911T184723Z` - S-20's
defensive off-state TLT/IEF/GLD at 2 bp - **passed `verdict()` today**, `(True, [])`, on every
criterion: CAR 24.982% against the champion's 23.068%, Sharpe 0.914 within the 0.03 tolerance of
0.938, drawdown 25.700% within the 1.0-point tolerance of 25.000%. Promoted into a scratch
champion it writes CAR 24.982% and **no `env` key**. Meanwhile the runner's `risk_off_sleeve` is
`()` - cash - and its universe has **no IEF at all**, so it could not subscribe to the promoted
book even if it knew about it.

**(4) The blast radius on the record.** Of **167** `s1_momo` rows, **36** record any `env`, **15**
carry a reaching key, and **1 passes today's gate**. That 15 is a **floor, not an estimate**:
`backtest.py:126` began recording `env` with S-18 on 2026-09-11, so every earlier row reads as
clean whatever it was actually run with.

**(5) The price, in the unit that matters - and it is not a CAR gap.** At the row's own cost model
(2 bp, no financing), the promoted parameters and the defaults the runner would trade instead:

| book | CAR | Sharpe | MaxDD | orders |
| --- | --- | --- | --- | --- |
| promoted parameters | 21.886% | 1.027 | 30.330% | 5,258 |
| what the runner trades | 20.996% | 1.107 | 23.963% | 5,062 |

Paired **+0.5093 bps/day at t +0.47** over 3,689 sessions - which is S-20's own refusal arriving
by a second route - and the two books **hold different things on 503 of 3,689 sessions (13.6%)**.
The runner is flat on **590 sessions (16.0%)** where the promoted book is flat on 87.

The decisive column is LEAN's, because that is what decides the promotion:

| | CAR | Sharpe | DD |
| --- | --- | --- | --- |
| champion, 2 bp column | 23.068% | 0.938 | 25.000% |
| candidate claims | 24.982% | 0.914 | 25.700% |
| **what the account then trades** | **23.068%** | **0.938** | **25.000%** |

**The promotion buys +1.914 CAR points and delivers +0.000 of them - 0%** - because what the
runner trades after the promotion is the book it was already trading. The pre-registered test
was "material iff the runner-traded CAR is at or below the champion's"; it is **equal to it by
construction**, so: MATERIAL.

**The second-order damage is larger than the first and points the opposite way from AUD-10.**
With that champion in place the bar becomes 24.982% CAR on a book the account cannot earn, and
**11 of the 167 rows flip from "beats" to "does not"** - real candidates refused for failing to
beat a fiction - while the drawdown ceiling moves **+0.700 points** the loose way. AUD-10 handed
a candidate slack it had not earned; AUD-12 denies the account improvements it had.

**(6) The fix, and backward compatibility as the withdrawal condition.** The audit offered two
remedies; this iteration takes the first and refuses the second on its merits. Plumbing
`champion.json["env"]` into the runner and the gate would *enable* trading overridden parameters,
which widens the deployed surface and edits a live runner to buy a capability nothing has asked
for. Refusing is the whole fix and it is not a limitation: **a parameter worth shipping belongs
in `signals.py`'s `Params` defaults**, which LEAN and the runner both read. An override is a
research instrument, and the gate is the one place that could otherwise turn one into a deployment.

Two halves that do not depend on each other, matching S-34's shape:
- **candidate side** - `param_env_note()` refuses any run carrying a reaching key, the fifth
  axis-mismatch rule after the spread, window, financing and environment rules, and it names the
  remedy in the message;
- **reader side** - `champion_env_note()` refuses *every* comparison when the champion file itself
  records a reaching override, which catches a hand-edit or an interrupted promotion however it
  got there. Silent when `env` is absent, because every promotion before today recorded nothing.
- and `--promote` now records the run's `env` on the champion, so the record states the
  environment the book was measured in. It can only ever be the inert set or empty, which is the
  point: a champion that says nothing about its environment is indistinguishable from one that hid
  an override.

Withdrawal condition, as in S-34: **167 rows re-judged old against new. Exactly 1 verdict moved,
`yes -> no`, on the tainted row - 0 moved the dangerous way and 0 moved on a clean row.** The 14
other tainted rows were already refused for other reasons and did not move. Full suite **543 pass**.

**(7) The runner's dead lookup, and a deliberate non-edit.** `hasattr(signals, "PARAMS")` is
`False` and `DEFAULTS == Params()`, so `paper_trade.py:196` resolves to the identical object on
every run: the lookup is dead code that *reads* as parameter support, which is how AUD-12 stayed
invisible for as long as it did. **This iteration does not edit the live runner.** The refusal
above closes the hole completely - nothing reaching can be promoted - so a cosmetic edit to
`paper_trade.py` would owe a `--replay` for zero measured risk reduction. The invariant it relies
on is pinned by a test instead: if `signals.PARAMS` ever appears, the runner starts trading
something `compare_orders.py` does not check, and the suite says so.

**Decision.** AUD-12 closed; the gate refuses a promotion whose parameters the account cannot
trade, and the champion now records its environment. **Adds no research item.** The one
consequence worth stating for the other tracks: any future S-item that wants to ship a parameter
must change the default in `signals.py` and re-run, not promote a sweep cell.

**Next daily audit item that needs no trading day: AUD-25** (`daily`) - `ML_MODE="rank"` gates on
sign, the `Params` window guard is incomplete, and `--history ib` has a clock convention. It is
the last `daily`-owned audit item; AUD-11's remaining half is a manual edit to a reserved file
and stays the owner's or the critic's.

**Reusable rule.** *A gate that judges a run must refuse every axis on which the run and the
deployed book can differ, and the list of axes has to be derived from the source rather than
remembered.* Four of the five rules in `verdict()` were each added after one specific instrument
appeared (spread, window, financing, interpreter). This one was found by asking the opposite
question - what is the full surface, and which parts of it are safe - and the answer was 56 and 7.

---

## 2026-09-12 - S-34 (AUD-10): the promotion gate hands the next candidate 4.2 points of drawdown slack, 15 rows already in the ledger would take it, and the fix moves no existing verdict

**What this iteration is.** S-33 closed by naming its own blocker: the AUD-11 relabel "is a
one-sentence edit the daily track may not make" until **AUD-10** is fixed, because re-running
`--promote` for a wording fix would trip AUD-10 on the way. So AUD-10 is the highest-value open
daily item and the only one that can advance on a Saturday. The finding: `evaluate.py --promote`
writes `stats`, `run_dir`, `commit` and `tag` and **never touches `stats_by_spread`**, while
`champion_stats()` *prefers* that dict - so the first candidate judged after any promotion is
compared against the book that just lost. It has never bitten because the file was hand-edited
after each of this repository's two promotions, which is a habit and not a gate.

This is a tooling fix, and this track does not ship one whose size it has not measured. The
question that decides whether AUD-10 is cosmetic or material is a number: **how much slack does a
retired column hand a candidate**, and does anything on the record actually take it.

Both standing measurement jobs ran first, as on every iteration since S-31, and it being a
Saturday neither has new input: `daily_fills.py` still reads **10 fills / $2,373,115 / +3.2 bps**
against the auction the runner aims at (per-fill sd 14.1, se 4.5), `ref_price` the previous close
10 of 10.

**Provenance and scope.** New `scripts/sweep_s34.py` (seven clauses pre-registered before the
first number; console output in `results/s34_run.txt`), a patch to `scripts/evaluate.py`, and
`tests/test_evaluate_promote.py` (13 tests). **No LEAN run, no ledger row, no strategy parameter
and no runner-loaded file** - `evaluate.py` is shared code but nothing in `live/` imports it, so
no `--replay` is owed; the gate it *does* owe is backward compatibility, which is clause 5.
`research/champion.json` was **not** modified: `git diff` on it is empty, and the end-to-end
promotion test writes to `tmp_path`.

**(1) Identity.** Today's champion file is self-consistent: 2 cost columns and **11 research
notes**, column `0.0` carries the champion's own `run_dir` and agrees with `champion["stats"]` on
every shared key. The defect is therefore preventive rather than already-bitten - which is the
answer to "has the shipped champion ever been judged against the wrong column": no.

**(2) The defect reproduces.** Promote the real run `20260911T150558Z` (the S-18 candidate at
2 bp) through the old code path, then ask `champion_stats()` for a 2 bp candidate: it returns
**22.926% from `20260911T125421Z`**, the *retired* S-12 book, **0.142 CAR points** from the run
that was just promoted.

**(3) The blast radius, and it is not the CAR column.** On the real S-12 -> S-18 promotion, the
slack a later candidate is handed:

| column | stale CAR | true CAR | dCAR | stale Sharpe | true Sharpe | dSharpe | stale DD | true DD | **dDD** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 bp | 24.404% | 24.403% | -0.001 | 0.921 | 0.994 | +0.073 | 25.100% | 23.700% | **+1.400** |
| 2 bp | 22.926% | 23.068% | +0.142 | 0.865 | 0.938 | +0.073 | 29.200% | 25.000% | **+4.200** |

**The return column is harmless and the risk column is not.** At 0 bp the two books are the dead
heat S-18 already reported (-0.001 CAR), so anyone reading only `must_beat` would call this
cosmetic. The damage is in `drawdown_tolerance_points`, which is **1.0**: the retired column hands
a candidate **4.2 points** of drawdown headroom at 2 bp, i.e. **4.2x the entire width of the risk
rule it is added to**, and 1.4x at 0 bp. That is the whole point of S-18 - it promoted a book that
carried the *same* return with *less* risk, so every part of the difference it bought sits in
precisely the column the stale comparison gives back.

**(4) Fifteen rows on the record would take it.** Replaying all **167** `s1_momo` ledger rows
through `verdict()` against the true post-S-18 champion and against the columns the old
`--promote` would have left: **15 rows flip, and all 15 flip in the dangerous direction** (the
stale column says BEATS where the true champion says no). They are not contrived - they include
`20260911T120010Z` (S-16, budget 0.80: **26.474% / 1.012 / DD 25.700%**), which clears the retired
book's 25.100 + 1.0 ceiling and breaches the champion's 23.700 + 1.0, and four more S-16
budget-0.80 cells of the same shape. Those are live candidates: S-31 re-priced that exact budget
question six hours ago. **Zero rows flip the harmless way.**

One correction to this clause, because the first version of it measured the patch instead of the
bug: with the new guard installed, the stale champion is refused outright, which turned every row
into "no" and reported 12 flips that were the fix working. The stale arm has to be judged with the
*old* semantics (`stale_note` bypassed for that arm alone) or the number is meaningless. 15, not
12, and the direction reverses.

**(5) Backward compatibility - the fix's own identity.** Pre-registered as the withdrawal
condition, because a promotion gate that silently moves an existing judgment is a worse defect
than the one being repaired. **167 rows compared, 0 verdicts changed**, and
`evaluate.py --algorithm s1_momo --last 200` is **byte-for-byte identical** before and after the
patch (`diff` clean).

**(6) and (7) The fix, in two halves that do not depend on each other.** *Writer:*
`promoted_columns()` makes the promoted run the only cost column, keyed at its own spread and
pointing at its own `run_dir`. *Reader:* `stale_note()` refuses every comparison when **no**
column carries the champion's `run_dir`, which catches a bad file however it got that way -
hand-edit, interrupted promotion, or a future writer. Deliberately **not** "every column must be
the champion's run", because S-18's 2 bp column is a different run of the same book
(`20260911T150558Z` against `20260911T145705Z`, same commit `d41aefe`) and that is correct.

Two things the audit's one-line fix ("write the run's column and delete the others") would have
got wrong and this does not. **`stats_by_spread` is not a dict of books** - it holds 2 columns and
**11 dated `*_note` keys**, the S-21..S-33 research record, 47 KB of it. "Delete the others" as
written destroys all eleven. They are preserved byte-identical (clause 6 asserts it), and the
reader now goes through `cost_columns()` so a note can never be quoted as a comparison basis -
which it previously was, in the "not comparable" message, which listed all thirteen keys as if
`leg_note` were a cost model. Second: after a promotion a candidate at a spread the new champion
has not been re-run at is **refused as not comparable** rather than judged, which is S-18's own
rule rather than a new one; the remedy is one re-run of the new champion at that spread, exactly
what S-18 did by hand.

**(8) A finding that was not in the audit, and it corrects AUD-11's filed plan.** Checking which
top-level keys `--promote` leaves alone turned up **`note`** - 3,415 characters of prose
describing the S-18 promotion, which survives every future promotion untouched. **That is where
AUD-11's wrong "OOS 2020-2026" label lives.** So AUD-11's remedy as filed - "have the next
promotion carry this replacement" - **cannot work**: no promotion has ever written that field and
none will. The relabel is a manual edit to a file AGENTS.md reserves to `--promote`, and fixing
AUD-10 does not unblock it. It is the same defect class as AUD-10 (promotion leaves the retired
champion's content in place) in prose rather than in numbers, and it is deliberately **not**
patched here: `note` is documentation that no code reads for judgment, and having `--promote`
delete or rewrite it would destroy the promotion record to fix a wording bug. Filed under AUD-11,
where the plan is, rather than opened as a new item.

**(9) A parallel-track collision, and it left HEAD broken for about twenty minutes.** While this
iteration was running, the `eng` track committed **bae4866**, whose
`tests/test_promotion_gate.py` calls `ev.stale_note()` and `ev.cost_columns()` - functions that
existed only in *this* track's uncommitted working copy. `git show HEAD:scripts/evaluate.py |
grep -c "stale_note\|cost_columns"` returns **0**, so those tests could not have passed on a
clean checkout: the suite was green only because my working tree was supplying the
implementation, and E-5 makes that suite the gate on the 09:25 launch. Committing this patch is
what repairs it, which is why it is going in rather than being split. Two consequences worth
carrying: **(a)** a track that writes tests against another track's working tree has committed a
dependency it cannot see, and the shared-code rule in AGENTS.md ("keep the change backward
compatible, run the affected gate") needs the reading to be *run the gate from a clean checkout*,
not from your own tree; **(b)** the duplication was real - their file covers the **reader**
(`stale_note`, `cost_columns` against metric lookup) and never touches `promoted_columns()` or
the `--promote` write path, **which is where the defect actually was**. So
`tests/test_evaluate_promote.py` was trimmed from 13 tests to **8**, dropping every reader-side
case that their file already owns and keeping the writer half plus the real-ledger regression
and the end-to-end `main()` test. The two files now partition the gate instead of overlapping it.

**Decision.** Fix shipped: `scripts/evaluate.py` patched, 8 tests added (43 across both promotion
files), full suite **241 pass**.
AUD-10 is **MATERIAL** on its pre-registered threshold (4.2 points against a 1.0 tolerance) and is
closed. Nothing promoted, nothing demoted, `champion.json` untouched, no number in it moved.

**Next.** AUD-12 (`daily+eng`): the runner and the gate both trade `Params()` while `--promote`
stores no `env`, so a run promoted with any `S1_*` override would pass the deploy gate and paper
trade something else. It is the same shape as this one - a promotion that does not carry
everything the champion is - and it is the last daily audit item that needs no trading day.

**The reusable rule.** *A comparison basis must be able to prove it is the champion's own.*
`stats_by_spread` was correct for eleven months because a human retyped it twice; the invariant
that makes it correct without a human is that the champion's `run_dir` appears in its own columns.
And when pricing a gate defect, read the column the gate's *tolerance* lives in, not the column
its `must_beat` lives in - here the two disagree by a factor of 4,200.

## 2026-09-12 - S-33 (AUD-11): the label is wrong and the number is not; choosing a parameter on 2012-2019 buys -0.05 CAR points on 2020-2026, and the audit's own first remedy makes the book worse at t -2.18

**What this iteration is.** The operator's 2026-09-12 platform audit filed **AUD-11 [daily]**: the
champion's "OOS 2020-2026" is a sub-period of a full-period fit, so "the honest ~20% CAR is fully
in-sample, and the 33% PSR says the same", and "every OOS-weighted claim (S-18, S-22, S-26, S-28)
inherits it". Its proposed fix has two branches - *re-select on 2012-2019 and report 2020-2026
once*, or *relabel and treat paper trading as the only out-of-sample evidence*. The finding is
correct as a matter of record and I am not contesting it. What it does not say is what the
contamination is **worth**, and that is the only form of the question the loop can act on: a label
that overstates by 0.1 CAR points is a documentation fix, one that overstates by 5 is a different
strategy than the one in `champion.json`. This iteration measures it, by re-doing the selection
with 2020-2026 genuinely withheld and reading the withheld half once.

Both standing measurement jobs ran first, as on every iteration since S-31, and it being a
Saturday neither has new input: `daily_fills.py` still reads **10 fills / $2,373,115 / +3.2 bps**
against the auction the runner aims at (per-fill sd 14.1, se 4.5), `ref_price` the previous close
10 of 10.

**Provenance and scope.** New `scripts/sweep_s33.py`, seven clauses pre-registered before the
first number; **60 DIAGNOSTIC ledger rows** under `daily/s33_oos` (stamp `20260912T170105Z`); full
console output recovered to `results/s33_run.txt`. **No shipped or runner-loaded file was
touched** - the shipped `Params()` defaults, `live/*`, `champion.json` and all three scheduled
tasks are unchanged - so no deploy gate and no `--replay` is owed. Nothing is promotable.

**(1) Identity, to the digit.** The shipped `Params()` over 2012-2026 at zero cost reproduces
**CAR 22.192150% / 5,052 orders**, the cell S-25, S-26, S-28, S-30, S-31 and S-32 each quote
independently. The grid below is the deployed book with one parameter moved.

**(2) The grid is the selection record, not a new search.** Three axes, each copied verbatim from
the `signals.py` docstring that records how the shipped value was chosen - S-10's `mom_skip` walk,
S-12's `alloc_vol_window` table, S-9's fourth-horizon shelf - and taken coordinate-wise from the
shipped set, which is how the record shows the three were actually chosen (one iteration each).
IS is 2012-2019, OOS is 2020-2026, zero spread, because zero spread is the cell all three of those
tables were read in.

| axis | shipped | FULL 2012-2026 argmax | IS 2012-2019 argmax | moved? |
| --- | --- | --- | --- | --- |
| `mom_skip` | 5 | **10** (22.677 vs 22.192) | 5 | no |
| `alloc_vol_window` | 21 | 21 | **10** (16.560 vs 16.488) | **YES** |
| fourth `mom_lookbacks` horizon | 252 | 252 | 252 | no |

Read the middle column before the right one, because it is the first thing that is not what the
audit expects: **the shipped set is not the full-period argmax either.** `mom_skip=10` beats the
shipped 5 by 0.485 CAR points on the very window the choice was made on, and it was not taken -
because S-10's docstring says in as many words that 5 is "one trading week, the a-priori unit
inside that shelf, not its argmax". Whatever else is true of this parameterization, it was not
fitted to its argmax, and that is visible in the data and not only in the prose.

**(3) The withheld half, read once.**

| set | parameters | OOS CAR% | Sharpe | MaxDD% | orders |
| --- | --- | --- | --- | --- | --- |
| shipped | - | **29.124** | 1.262 | 23.855 | 2,267 |
| IS-selected | `alloc_vol_window=10` | 27.260 | 1.193 | 23.396 | 2,963 |
| FULL-selected | `mom_skip=10` | 30.552 | 1.317 | 22.392 | 2,203 |

**The audit's first remedy is refused on evidence.** Re-selecting on 2012-2019 moves one axis, and
that move costs **-1.865 CAR points** on the withheld half at **-0.569 bps/day over 1,677
sessions, t -2.18** - past |t| = 2, and the first thing on this sleeve to get there that is not
S-31's arithmetic. Worse, `alloc_vol_window=10` is not merely a loss, it is the **worst of the six
cells on its own axis out of sample** (27.260 against 27.993 / 28.875 / 28.961 / 29.124 / 29.144).
The first half's best cell is the second half's last.

**(4) Which means the -1.865 is not the contamination, and the pre-registered branch label was
imprecise.** Clause 4 fired branch **(b) CONTAMINATED**, because I defined the gap as
*IS-selected minus shipped* and it cleared the 0.5-point threshold. That is the right number for
"what does the audit's remedy cost" and the **wrong** number for "how much is the published OOS
inflated by selection", which is what AUD-11 alleges. Inflation is measured against a *typical*
cell, not against one particular unlucky draw. On the 18 unique cells of the grid:

| statistic | OOS CAR% |
| --- | --- |
| grid minimum | 23.166 |
| grid mean | 28.150 (sd 1.832) |
| grid median | 28.632 |
| **shipped set** | **29.124** |
| grid maximum | 30.846 |

The shipped set sits **+0.974 above the grid mean, 0.53 sd, 78th percentile (rank 14 of 18)** and
**+0.492 above the median** - i.e. under the pre-registered 0.5-point threshold by which this
iteration called a finding cosmetic. **So the correct reading is: the label is wrong and the
number is not.** Selection on these three axes inflates the published 2020-2026 figure by about
**half a CAR point at zero cost**, not by the 1-3 the hypothesis expected.

**(5) The selection premium - the part of this that generalizes past the champion.** One draw is
one draw. The durable question is whether choosing a parameter on this sleeve's first half
predicts anything at all about its second:

| axis | cells | rho(IS CAR, OOS CAR) | OOS of the IS-argmax | OOS of the median cell | premium |
| --- | --- | --- | --- | --- | --- |
| `mom_skip` | 7 | +0.000 | 29.124 | 29.124 | +0.000 |
| `alloc_vol_window` | 6 | **-0.257** | 27.260 | 28.918 | **-1.658** |
| fourth horizon | 7 | +0.607 | 29.124 | 27.613 | +1.511 |
| **pooled** | 20 | +0.323 | | | **-0.049** |

And on the 18 unique cells, split by what the first half said about them:

| | mean OOS CAR% |
| --- | --- |
| the IS **top** three cells | 28.420 |
| the IS **bottom** three cells | 28.283 |
| every cell | 28.150 |
| the single global IS-argmax | **27.260** (below the grid mean) |

**Picking the best third of 2012-2019 instead of the worst third buys 0.137 CAR points on
2020-2026.** The pooled premium against the median cell is **-0.049**. The single best cell of the
first half is a below-average cell in the second. On these three axes, selection on 2012-2019
carries **no out-of-sample content** - which is simultaneously why the published OOS is only half
a point inflated (there was nothing to inflate it with) and why the audit's re-selection remedy
cannot work (there is nothing for it to select on).

**(6) The honest number.** Cell C is the deployed 15:45 convention charged 2 bp of one-way spread
plus IBKR Pro financing on the historical effective fed funds rate - S-22's honest historical
book, the cell `champion.json`'s `deployed_expectation_note` is quoted in (full period 19.640%).
On the withheld half:

| set | OOS CAR% | Sharpe | MaxDD% |
| --- | --- | --- | --- |
| shipped | **25.967** | 1.151 | 24.040 |
| IS-selected | 23.922 | 1.073 | 23.575 |

The cell-C charge on this half is **-3.157 points**, so applied to the grid's own 0 bp dispersion
the honest fully-charged 2020-2026 band of this parameterization is roughly **20.0 .. 27.7%,
centre ~25.0-25.5%**. That is a *parameter-selection* band, not a forecast interval; it says how
much of the 25.967 is a property of the strategy rather than of three dials, and the answer is
most of it.

**(7) Significance, stated rather than discovered.** The only statistic here past |t| = 2 is
**t -2.18**, and it is against the audit's own proposed fix rather than for anything. Nothing in
the selection-premium table is significant and none of it is claimed to be.

**Decision.** AUD-11's **first remedy (re-select on 2012-2019) is refused**: it lands on the worst
out-of-sample cell of the one axis it moves, costs -1.865 CAR points at t -2.18, and the pooled
premium of -0.049 says it could not have done better than chance. AUD-11's **second remedy
(relabel, and treat paper trading as the only out-of-sample evidence) is adopted**, and it can now
be quoted with a number rather than a caveat: **the three documented axes inflate the published
2020-2026 figure by ~0.5 CAR points at 0 bp (78th percentile of 18 cells, 0.53 sd above the grid
mean), so every OOS-weighted claim that inherits the label - S-18, S-22, S-26, S-28 - is wrong in
its wording and right to within about half a point in its arithmetic.** Nothing is promoted,
nothing is defaulted, `champion.json` is untouched.

**The one part of AUD-11 I could not close, and why.** The wrong label physically lives in
`champion.json`'s `note` ("OOS 2020-2026 at 0 bp 32.801% ... the return difference is
out-of-sample weighted"), and AGENTS.md's "Parallel tracks" rule says `champion.json` may be
changed only through `scripts/evaluate.py --promote` or restored from git by the critic. There is
no promotion here, and re-running `--promote` to carry a one-sentence label fix would rewrite the
whole record and trip **AUD-10** (stale `stats_by_spread`) on the way. So the edit is **owed, not
taken**; the exact replacement sentence is filed against AUD-11 in `research/backlog.md` for the
next promotion to carry, and AUD-10 should be fixed before it.

**Lower bound, said plainly.** This prices **three** of the champion's dials. `top_n`,
`target_vol`, `regime_threshold`, `regime_vol_window` and `target_exposure` were also chosen on
full-period tables and are not priced here; the band was, by S-32, and came out the same shape
(criteria pass, no mechanism underneath). So **+0.5 CAR points is a lower bound on the total
selection inflation**, not an estimate of it.

**What it changes for the loop.** Two things, both durable. (1) A selection premium of -0.049 over
20 cells is a statement about **every** S-item in this repository, not just this one: on this
sleeve, a parameter shelf is worth reporting and a parameter argmax is worth nothing, and the
a-priori-point-inside-a-shelf convention that S-9, S-10 and S-12 already used is not conservatism,
it is the only defensible rule the data supports. (2) When an audit names a defect **and** a fix,
they are two separate claims and the fix is the one more likely to be wrong - here the finding was
right and its first remedy, applied literally, would have cost 1.87 CAR points out of sample at
the only t past 2 sigma this sleeve has produced from an actual book.

**Reproduce:** `py -3.11 scripts/sweep_s33.py --stage all` (~25 min; `--stage a` for the grid
alone). Output: `results/s33_run.txt`.

## 2026-09-12 - S-32: the no-trade band's CAR column is 3.5x larger than the mechanism can produce, and one random skip in five beats it

**Provenance, stated first.** `scripts/sweep_s32.py` and its 55 DIAGNOSTIC ledger rows under
`daily/s32_band` were produced by an earlier run of this job today (ledger stamp
`20260912T144940Z`) that ended before it journaled or committed - the console output was lost
with it. This iteration re-ran `--stage b --no-record` (deterministic: fixed placebo seeds, and
clause 1 re-checks the identity), recovered the full output to `results/s32_stage_b.txt`, and is
the write-up the earlier run owed. No rows were written twice.

**Why this iteration exists.** Same reason as S-31 and by the same rule: the backlog says to stop
finding levers and make the owner decisions in `BLOCKERS.md` answerable. Both standing measurement
jobs ran first and, this being a Saturday, neither has new input - `daily_fills.py` still reads
**10 fills / $2,373,115 / +3.2 bps** against the auction the runner aims at (per-fill sd 14.1,
se 4.5), `ref_price` the previous close 10 of 10. So the highest-value act is to re-price the one
remaining owner decision that is pure execution: the **no-trade band**, open since 2026-09-09 and
answered conditionally - *"keep 0.01 ... revisit with measured paper slippage after two weeks of
fills; if the measured spread cost per order is material, widen to 0.03 and rebaseline the hash."*
That conditional is now testable, because the measured spread cost exists.

**Hypothesis.** Everything the owner was shown about this decision (S-13's flat walk 24.40 / 24.35
/ 24.54 / 24.34 / 23.92 / 24.47 while orders fall 4,735 -> 1,727; S-18's +0.064 / +0.103) is on a
book that charges **zero spread**. A band is a turnover lever and nothing else - it buys back
spread - so charging zero prices the one thing the band is for at zero. Charge it, on the deployed
15:45 convention, with the borrowing and at the live-measured execution cost, and the band should
show a gain that **grows with the spread charged**. Seven clauses pre-registered before the first
number; the whole thing is DIAGNOSTIC and **no shipped or runner-loaded file was touched** (the
two new arguments `band=` and `skip=` are on the research harness `sweep_s25.legs_simulate`,
S-26/S-28/S-30's precedent, and both are inert at their defaults), so no deploy gate and no replay
is owed.

**(1) Identity, to the digit.** At the shipped band 0.010 the harness reproduces the deployed cell
at **CAR 22.192150% / 5,052 orders** at zero cost and **19.640168% / Sharpe 1.047 / DD 24.037%**
fully charged - the figure S-22, S-26, S-28, S-30 and S-31 each quote independently. The band
argument filters orders; it does not change the book.

**(2) The premise HOLDS, and that is the weakest true thing that can be said for it.** Gain over
the shipped 0.010 in the same spread column, no financing so the only thing moving across a row is
execution cost:

| band | orders removed | 0 bp | 1 bp | 2 bp | **3.2 bp (measured)** |
| --- | --- | --- | --- | --- | --- |
| 0.000 | -88.8% | -0.170 | -0.181 | -0.207 | -0.215 |
| 0.005 | -30.3% | -0.078 | -0.080 | -0.105 | -0.103 |
| 0.010 | 0.0% | +0.000 | +0.000 | +0.000 | +0.000 |
| 0.020 | 30.3% | +0.060 | +0.066 | +0.049 | +0.106 |
| 0.030 | 45.2% | -0.032 | -0.004 | +0.020 | +0.026 |
| 0.050 | 58.4% | +0.274 | +0.299 | +0.252 | +0.369 |
| **0.080** | 67.4% | **+0.380** | **+0.391** | **+0.450** | **+0.519** |
| 0.120 | 73.6% | -0.131 | -0.020 | +0.046 | +0.155 |

Band 0.080 - the band clause 4 selects - rises monotonically left to right, so the pre-registered
premise clause passes. But read the row the other way: **+0.380 of the +0.519 is already there at
zero spread**, where the only cost the band can save is $3,564 of commission over fourteen years
on a book that compounds $100k to $2.4M. The spread the premise is about buys the *difference*,
and that difference is the one column in this table that behaves like a mechanism:

| band | 0.020 | 0.030 | 0.050 | 0.080 | 0.120 |
| --- | --- | --- | --- | --- | --- |
| gain(3.2 bp) - gain(0 bp) | +0.045 | +0.058 | +0.095 | **+0.139** | +0.286 |

Monotone in the band, every cell, with no exceptions - which is exactly what charging a per-trade
cost to a book that trades less must produce. **The mechanism is real and it is worth +0.139 CAR
points at band 0.080.** The other +0.380 is path difference, and the rest of this entry is about
how large that is.

**(3) The four cost cells.** Deployed convention at 0 bp (A), +2 bp (B), +2 bp and IBKR Pro
financing on the historical effective fed funds rate (C, the decision cell, S-22's honest
historical book), and the live-measured 3.2 bps at today's 3.63% cost of money (D). The band
column moves the same way in all four; the whole frontier drops **22.19 -> 21.00 -> 19.64 ->
18.38** at the shipped band as the costs go on, which is the S-22 correction and not news here.

**(4) By `champion.json`'s own criteria, five bands pass - including the owner's 0.03.** In cell C
against the shipped 0.010 (19.640 / 1.047 / DD 24.037):

| band | CAR% | gain | dSharpe | dDD | orders | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 0.020 | 19.730 | +0.090 | +0.004 | -0.049 | 3,537 | passes |
| 0.030 | 19.654 | +0.013 | +0.001 | -0.094 | 2,764 | passes |
| 0.050 | 19.953 | +0.313 | +0.013 | -0.134 | 2,110 | passes |
| **0.080** | **20.184** | **+0.544** | **+0.021** | **-0.606** | **1,641** | **passes, best** |
| 0.120 | 19.846 | +0.206 | +0.003 | -0.481 | 1,336 | passes |

and 0.080 also wins **both halves** (IS 2012-2019 +0.423, OOS 2020-2026 +0.869), which is the
clause's last condition. On the letter of the rule, band 0.080 is recommendable. Three things say
it should not be recommended anyway.

**(5) The placebo: one random skip in five beats it.** At band 0.080's own measured rate, 67.5% of
the shipped band's candidate orders dropped **at random** instead - same number removed, different
ones, five seeds, cell C:

| | CAR% | gain | Sharpe | MaxDD% | orders | bps/day | t |
| --- | --- | --- | --- | --- | --- | --- | --- |
| band 0.080 | 20.184 | **+0.544** | 1.068 | 23.431 | 1,641 | +0.185 | +1.96 |
| random seed 1 | 19.302 | -0.338 | 1.028 | 26.750 | 2,236 | -0.106 | -0.20 |
| random seed 2 | 20.254 | **+0.614** | 1.072 | 21.295 | 2,253 | +0.208 | +0.40 |
| random seed 3 | 18.190 | -1.451 | 0.973 | 20.263 | 2,208 | -0.467 | -0.81 |
| random seed 4 | 19.687 | +0.047 | 1.045 | 28.100 | 2,214 | +0.022 | +0.04 |
| random seed 5 | 19.889 | +0.249 | 1.039 | 25.092 | 2,233 | +0.116 | +0.18 |

Random mean **-0.176**, sd **0.791**. The band's +0.544 sits **0.91 sd** above the random mean and
**seed 2 beats it outright**, so the permutation p-value on five draws is 2/6 = 0.33. Random
skipping also swings drawdown from **20.26% to 28.10%** around the shipped band's 24.04%: at this
skip rate the CAR and drawdown columns are a lottery with a ±0.8-point standard deviation, and the
band's entire +0.544 is one draw from it. Stated against the placebo honestly: the null is matched
on the **per-candidate skip probability**, not on realized orders - a randomly skipped order
leaves the position off-target so the next day's delta is larger, and the placebo ends up trading
2,236 orders against the band's 1,641. It is an imperfect null. It is still wide enough to contain
the result.

**(6) Significance, said out loud as always.** Full-period paired daily difference against the
shipped band in cell C: 0.020 **t +1.30**, 0.030 **t +0.12**, 0.050 **t +1.69**, 0.080 **t +1.96**,
0.120 **t +0.53**. By half, band 0.080 is **+1.35** IS and **+1.74** OOS. Nothing on this sleeve
has crossed |t| = 2 except S-31's arithmetic and this does not either. And the shape of the band
column is the tell: **0.020 +0.090, 0.030 +0.013, 0.050 +0.313, 0.080 +0.544, 0.120 +0.206**. A
cost effect is monotone in the band until tracking error eats it; this zig-zags, and 0.030 - the
band the owner named - is the local worst of the five that pass.

**(7) The live consequence, which is the number that ends the argument.** Turnover removed,
charged the live-measured 3.2 bps one way:

| band | orders/yr | turn/yr | turnover removed | **spread bill saved, %equity/yr** |
| --- | --- | --- | --- | --- |
| 0.010 (shipped) | 345 | 49.4 | - | - |
| 0.020 | 242 | 48.3 | +1.1 | **0.035%** |
| 0.030 | 189 | 47.3 | +2.1 | **0.067%** |
| 0.050 | 144 | 46.0 | +3.4 | **0.108%** |
| 0.080 | 112 | 44.5 | +4.9 | **0.155%** |
| 0.120 | 91 | 42.7 | +6.7 | **0.213%** |

**The arithmetic ceiling on the prize at band 0.080 is 0.155% of equity a year. The CAR column
claims +0.544. The claim is 3.5x larger than the mechanism is capable of** - and the ceiling
agrees, to within 0.016 points, with the spread-attributable component clause 2 isolated
independently (+0.139). Two routes, same answer: the band is worth about a seventh of what cell C
advertises, and the other six-sevenths is the path noise the placebo measures at sd 0.79.

**Decision.** **Keep 0.01. The 2026-09-09 conditional resolves to "not material".** The owner's
standing instruction was to widen to 0.03 if the measured spread cost per order turned out to be
material; the measured cost is **+3.2 bps with se 4.5** - not yet distinguishable from zero - and
at that cost band **0.03 buys 0.067% of equity a year**, the local *worst* of the five passing
bands, at t +0.12. Nothing here justifies moving the live order list off `OrderListHash
a6d6224ce9c70091e5bfa8e96f046bf3` and rebaselining `compare_orders.py`. A `BLOCKERS.md` addendum
carries the priced version of the question so the owner is not asked twice.

**What would change the answer, and it is not another sweep.** The band's value is linear in the
spread actually paid and the prize is quoted per basis point in clause 7 (0.155% per year at 3.2
bps at band 0.080, i.e. ~0.048% per bp). If `daily_fills.py` settles at a materially higher number
than +3.2 bps as fills accumulate, the same table answers the question again without re-running
anything - and if the owner ever wants the band widened for *operational* reasons (112 orders a
year instead of 345, a two-thirds cut in order count), the case for **0.08** is better than the
case for 0.03 on every column in this entry. That is an operations argument, not a research
result, and it is the owner's to make.
