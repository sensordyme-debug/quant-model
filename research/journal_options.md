# Options track journal (O-)

Newest first. The `options` scope: the Theta store, `scripts/odte_*`, `scripts/theta_data.py`,
`scripts/sweep_o*`. Evidence only - this track has never had, and does not ask for, a deployment.

---

## 2026-09-13 - O-8: the put wing does NOT forecast the day's downside tail. Against a baseline that already carries the chain's own symmetric magnitude, the asymmetry block loses on the pooled test (DM t **-0.401**), wins 2 of 5 clocks, gets 1 of 5 clocks on the regimes leg, and fits the DECLARED SIGN WRONG at 4 of 5 clocks. REFUSED on both legs. The secondary read is the positive one and it is real: `rn_half` cuts the OOS 5% VaR loss **-3.0% to -8.0%, rising monotonically through the day**, at 5 of 5 clocks. Nothing shipped.

**Why this item.** There was no open O-item - O-1 through O-7 are all closed - and O-7's closing
sentence was that everything this 176 MB store contains lives in ONE number, `rn_half`, a
*symmetric* scale, whose only consumer (position size) was then refused downstream by A-15. But
the chain also prices **asymmetry**, and this track has tested that exactly once, for exactly one
thing: O-5 asked whether `rn_skew` (0.5% of spot) and `rn_tail` (2.0%, the crash-premium tilt)
forecast the **direction** of the remaining move, found best cover 0.963 and zero cells above 1,
and closed direction.

A conditional **mean** and a conditional **quantile** are not the same object, and the gap between
them is this item's whole economics. The conditional mean of a return is a tradeable expectation;
if the chain knew it, the chain would price it away, so O-5's null is what efficiency is supposed
to look like. The 5th percentile is not a tradeable expectation in the same sense - the
risk-neutral left wing is a physical tail probability multiplied by a pricing kernel that is
largest exactly there, which makes the put wing a **biased** estimator of the physical tail and
says nothing about whether it is an **informative** one. And a downside tail has a consumer that
magnitude does not: A-15 refused `rn_half` as a size scaler because the sleeve is paid for the
volatility *surprise*, not the predictable part; nothing in A-15 is about the **left tail**, and a
de-risk/flatten switch is paid for avoiding drawdown, a functional of the lower quantile alone.

**Hypothesis.** The chain's risk-neutral asymmetry carries information about the LOWER conditional
quantile of the remaining session's move in SPY that is contained neither in the realized tape nor
in the chain's own symmetric magnitude `rn_half`.

**Design, pre-registered in `scripts/sweep_o8.py`'s docstring before any run.** No new feature, no
new clock, no new data: the chain side is O-5's frozen cache, and the tape panel, the five clocks,
the 250-session burn-in, the expanding-window protocol, the regime split and the DM statistic are
**imported from `sweep_o6.py`**. What is new is the target and the loss. Target = **`fwd` itself,
signed** - no absolute value and no log, because taking either destroys the asymmetry being
tested. Estimator = **linear quantile regression at tau = 0.05**, chosen over a binary exceedance
model precisely because binarising needs an arbitrary threshold, and the pinball loss at tau =
0.05 *is* the loss function of a 5% VaR, so the statistical test and the economic object are one
quantity. Three nested models, all in levels: **M0** = tape (`rv_sofar`, `rng_sofar`, `rv20`,
`absret_1`); **M1 = M0 + `rn_half`**; **M2 = M1 + {`rn_skew`, `rn_tail`} as a fixed two-column
block**. The test that decides the item is **M2 against M1**, not against the tape - if the
asymmetry block only beats the tape it has found O-6's result again through a wider door, and that
is a refusal here. `rn_drift` and `d_rn_skew` are in the cache, are *not* in the block, and were
declared unswappable. Declared sign: `rn_tail` = P_rn(move <= -2%) - P_rn(move >= +2%), so a
higher value is a fatter left wing and must push the 5% quantile **down** - coefficient NEGATIVE,
same for `rn_skew`. PASS needed **both** (i) M2 below M1 at >= 4 of 5 clocks and a pooled DM t >
+2.576, pooled by averaging the loss difference across clocks *within a session* first; and (ii)
the two-of-three regimes rule at >= 4 of 5 clocks.

**Gates.** Gate 0 (O-6's, O-5's control reproducing to 0.005) passes. Gate 1 is new and it is the
one this item could not have run without: `statsmodels` is not installed on this machine, so the
IRLS quantile-regression solver is written out in the file, and rather than trust it, it is checked
against an **exact `scipy.optimize.linprog` solution of the same program** - excess pinball loss
**0.0000 at both taus** (tolerance 1e-6). Gate 2, in-sample calibration, breaches 5.20-5.30% at
tau = 0.05 and 94.75-94.85% at tau = 0.95 across all five clocks. Panel: 8,754 feature-complete
rows, 1,855 sessions, 2016-02-05..2026-09-10.

**Stage C - decisive, and it is a clean refusal.**

| clock | pin M1 (+half) | pin M2 (+asym) | d_pin M2 vs M1 | DM t | regimes won | clock won |
|---|---|---|---|---|---|---|
| 10:00 | 0.000800 | 0.000798 | **-0.21%** | +0.12 | 1 | yes |
| 11:00 | 0.000700 | 0.000702 | +0.25% | -0.23 | 2 | no |
| 12:00 | 0.000600 | 0.000608 | +1.34% | -1.12 | 1 | no |
| 13:00 | 0.000500 | 0.000499 | **-0.21%** | +0.15 | 1 | yes |
| 14:00 | 0.000400 | 0.000402 | +0.43% | -0.61 | 1 | no |

Leg (i): clocks won **2 of 5**, pooled DM t **-0.401** against a bar of +2.576 - the block is
fractionally on the *wrong* side of zero, not merely short of significance. Leg (ii): 1 of 5
clocks reach two regimes. **Verdict REFUSED**, and the two legs agree, which is the cheapest kind
of refusal to believe.

**Stage F, and this is the part that says the refusal is about the mechanism and not about power.**
The declared sign is **wrong**. Fitted per-1-sd effects on the 5% quantile: `rn_skew` comes out
**positive at 4 of 5 clocks** (+14.8 / +3.8 / +4.2 / +4.6 / -0.8 bps) where the declaration said
negative, and `rn_tail` is negative at only 3 of 5 (+1.2 / -6.9 / -0.8 / -9.2 / +4.6). `rn_half`,
by contrast, is **-21.9 to -37.1 bps per sd at 5 of 5**, exactly as a scale must be. A block that
carried real tail information and merely lacked power would at least load in the declared
direction; this one does not.

**Stage A shows why, and the answer was visible before the verdict.** Both asymmetry reads have a
substantial Spearman with **|fwd|** (`rn_skew` -0.31 to -0.34, `rn_tail` +0.15 to +0.22) and an
almost null one with **signed fwd** (-0.08 to +0.08). On the worst 5% of days they *are* more
extreme (`rn_skew` mean -0.031 against -0.014 at 10:00), but the worst 5% of days are also the big
-move days, so that gap is a magnitude effect - and it is exactly the confound the M1 baseline was
built to absorb. It absorbed it. **The put wing's asymmetry, as this store measures it, is a
restatement of the chain's own width.**

**Stage D - the economic leg is a null in both directions.** The de-risk switch the 5% quantile
would feed, at matched mean exposure: the book's 5th-percentile return moves +0.00 / +1.86 /
+4.08 / -4.09 / -1.26 percent - no sign, no material cell (bar was -5%). Calibration is worth
noting on its own: **M1's realised breach rate is 4.39-5.25% against a nominal 5%** at every
clock, so the `rn_half` VaR is honest out of sample; M2's is 4.91-5.83%, marginally worse.

**Stage E - the placebo, which did not have to bite and did not.** At tau = 0.95 the asymmetry
block is **worse** than M1 at 5 of 5 clocks (pooled DM t **-2.674**), and the upper tail improves
at least as much as the lower one at **0 of 5** clocks. So the refusal is not "a symmetric scale
leaked in beside `rn_half`" - the block is simply fitting noise, and it costs more on the side
where the store's sample is richer.

**The secondary read, which is the only positive here and was pre-registered as unable to change
the verdict.** M1 against M0 asks a question nobody had asked: does O-6's magnitude skill survive
a change of *target* and *loss function*, from `log|move|` under squared error to a signed lower
quantile under pinball loss? It does, at **5 of 5 clocks**, and the gain **grows monotonically
through the session**: d_pin **-2.96 / -3.43 / -5.79 / -7.21 / -8.03 percent** at 10:00 .. 14:00,
DM t **+2.66 / +2.24 / +2.90 / +2.78 / +3.16**. Four of five clear the 2.576 Bonferroni bar; 11:00
at +2.24 does not, and that is said rather than rounded away. The same feature also improves the
tau = 0.95 quantile (-5.6% to -7.9%, t +1.85 to +3.20), which is the coherence check this reading
needed: `rn_half` is a *symmetric* scale and it should help both tails about equally, and it does.

**Reported against itself - three limits, none of which the verdict leans on.** (1) `rn_tail` is
**exactly 0 on 23.8% of rows** - on calm days both 2% wings are worthless - so a quarter of that
column is a constant and the test is weaker for `rn_tail` specifically. It is not weaker for
`rn_skew`, which is non-zero on 99.8% of rows and fails the declared sign at 4 of 5 clocks, so the
refusal does not rest on the mass point. (2) The estimator is **linear in levels**; a nonlinear
tail response at these two distances would be missed, and the honest claim is therefore "linear,
at 0.5% and 2.0% of spot, out of sample, over and above tape + `rn_half`: nothing", not "the chain
has no tail information at any functional form". (3) The 250-session burn-in leaves the 2016-2019
regime with 32-187 OOS rows, so at 13:00 and 14:00 it falls under the 100-row floor and "2 of 3"
is judged as 2 of 2 available - which, if anything, made leg (ii) *easier* to pass, and it still
failed. The store remains frozen at 1,891 sessions ending 2026-09-10 (Theta FREE, `history/quote`
403), and the sample carries O-3's both-rights mask and is therefore tilted volatile, identically
for all three models.

**Decision: REFUSED, and it closes the store on evidence rather than on exhaustion.** The
pre-registered meaning of this outcome, written before the run, was that the chain's entire
content is the one symmetric number O-6 found, that the asymmetry the put wing is famous for is a
pricing kernel rather than a forecast, and that **O-4's advice to stop scheduling this scope until
Theta VALUE is restored becomes unconditional rather than a judgement call.** All three now hold.
Eight items, one PASS (O-6), one characterisation of it (O-7), and a downstream refusal of the
product (A-15). The residue this track leaves behind is a single well-calibrated fact for whoever
wants it: **`rn_half` is a better same-day 5% VaR for SPY than the tape alone, by 3 to 8 percent
of pinball loss, increasing through the day** - measured, out of sample, and not shipped.

**Nothing shipped.** No shipped file, no runner-loaded file, no config, no `champion.json`, no
deploy gate owed. The only new file is `scripts/sweep_o8.py`, which imports its measurement side
from `sweep_o6` rather than re-implementing it; `scripts/sweep_o6.py` and `sweep_o7.py` are
**unmodified**. 21 DIAGNOSTIC rows under `options/odte_o8_tail`; the full console run is kept at
`results/options/o8_run.txt` (gitignored) and the verdict reproduced exactly on the recorded
second pass.

**No handoff opened.** O-6 opened A-15 and A-15 was refused; opening another item off a REFUSED
result would be spending another track's slot on nothing.

**Provenance note, so the history is not misleading.** `.git/index.lock` was held by other tracks
for most of this run. Between this track's `git add` and its `git commit`, a concurrent track
committed - taking these four staged paths out of the index - and then staged its own. The result
is that **commit `30abec5` carries this item's commit message but seven files belonging to the
`eng`/futures tracks** (`quant_brain/core/mode.py`, `quant_brain/brokers/ibkr.py`,
`quant_brain/core/execution.py`, `scripts/intraday_trader.py`, `scripts/paper_trade.py`,
`tests/test_qb_adapter.py`, `tests/test_qb_mode.py`) and **none of O-8's**. Nothing was lost and
nothing of another track's was altered - only the message is attached to the wrong files. History
was deliberately NOT rewritten (other agents are committing against this branch right now, and an
amend would move a commit out from under them); O-8's own four paths are committed separately in
the commit that follows this line, which is the one to read for this item. Same failure mode and
same remedy as `C-6` on 2026-09-12.

---

## 2026-09-13 - O-7: O-6's magnitude skill is NOT a volatility-regime detector - it is there in 15 of 15 (clock x vol-state) cells and the sized-book benefit is LARGEST in the calm state, where a realized-vol sizer is blind. PASS on the pre-registered rule, and the calm leg clears its bar by 0.037 of a t, which is reported as the marginal thing it is. Nothing shipped - and the product this characterizes was already refused downstream by A-15, so this closes the track rather than advancing it.

**Why this item.** There was no open O-item: O-1 through O-6 are all closed. O-6 is the only PASS
this track has produced, and it wrote down, in its own caveats, the one thing that would make it
overstated and never tested:

> "measured on SPY only, on a sample tilted volatile by O-3's mask (it drops calm sessions
> preferentially - O-5 measured mean |move| 13.3 bps where it drops out against 38.7 bps where it
> survives)"

The SPY-only half cannot be closed from disk - the store has exactly one underlying and Theta was
re-checked live at the top of this run (`listening True serving True`, `history/quote` **HTTP 403,
"you only have a FREE subscription"**), so the store is still frozen at 1,891 sessions ending
2026-09-10. The volatility half **can** be, and it is the half that matters economically. A sizing
rule needs no help on a day the tape is already screaming; `rv_sofar` at 12:00 on a 3% day tells it
everything. **The expensive error is the quiet morning that ends in a move** - the state where a
realized-vol sizer is structurally blind and a forward-looking risk-neutral measure is the only
thing that could see. If O-6's increment lived only in the volatile state, what it found was a
regime detector largely redundant with the tape's own regime read.

**Hypothesis.** The chain's incremental magnitude skill over the tape is a GENERAL input to
position size, not a volatility-state detector: it survives out of sample in the CALM state.

**Design, pre-registered in `scripts/sweep_o7.py`'s docstring before any run.** Nothing on the
measurement side is new: the panel, O-5's frozen chain cache, the four-predictor tape baseline, the
target `log|fwd|`, the five clocks, the 250-session burn-in and the expanding-window OOS protocol
are **imported from `sweep_o6.py` and re-run unmodified**. The only new object is the state
variable the out-of-sample errors are partitioned by: **`rv20`**, the prior 20 sessions'
close-to-close vol - known *before* the forecast session opens, so the partition cannot be
contaminated by the outcome, and deliberately not the strongest tape predictor. Splitting on
`rv_sofar` was **rejected in advance and written down as rejected**, because it is one of the
baseline's own fitted inputs; it is carried as an explicitly secondary read that cannot overturn.
Terciles are assigned **causally** (33.3/66.7 percentiles of strictly prior rows, 100-session
minimum), never by a full-sample quantile. PASS required **both** (i) the chain beating the tape in
the calm state at >= 4 of 5 clocks **and** a pooled calm DM t > +2.576, pooled by averaging the
loss difference across clocks *within a session* first so one session is one observation and not
five; **and** (ii) the two-of-three rule applied to volatility states instead of calendar regimes,
at >= 4 of 5 clocks. PARTIAL was defined in advance as (ii) without (i) - "real but
volatility-conditional, re-label the handoff".

**Gates.** O-6's own Gate 0 passes and its Stage C reproduces at 5 of 5 clocks, so there was a
result to condition. 7,007 of 7,507 OOS rows label (calm 2,665 / mid 2,838 / volatile 1,504).

**Stage 1 - decisive. The chain wins in 15 of 15 cells.**

| clock | calm dRMSE% (DM t) | mid dRMSE% (DM t) | volatile dRMSE% (DM t) | states won |
|---|---|---|---|---|
| 10:00 | -1.38 (+2.15) | -2.10 (+2.88) | -1.60 (+1.85) | 3 of 3 |
| 11:00 | -0.85 (+0.94) | -2.44 (+3.38) | -1.15 (+1.25) | 3 of 3 |
| 12:00 | -1.37 (+1.22) | -2.47 (+2.65) | -3.12 (+2.28) | 3 of 3 |
| 13:00 | -2.07 (+2.56) | -2.10 (+2.59) | -0.65 (+0.49) | 3 of 3 |
| 14:00 | -1.72 (+1.67) | -4.14 (+4.07) | -2.41 (+1.80) | 3 of 3 |

Leg (ii) passes 5 of 5. Leg (i): calm wins 5 of 5 clocks, pooled calm DM t **+2.613** on 632
sessions against a bar of **+2.576**. **Verdict PASS.**

**And leg (i) clears by 0.037 of a t, which is said out loud rather than rounded away.** No
individual clock's calm DM t reaches the Bonferroni bar; the calm leg is carried entirely by
consistency of sign across clocks. A post-hoc sensitivity (Stage 5, added after the first run and
labelled as such, and it does not move the verdict, which stands on the pre-registered lag 5)
shows the pooled calm t at Newey-West lags 0 / 2 / 5 / 10 / 20 = **2.487 / 2.532 / 2.613 / 2.659 /
2.790** - it **fails at the two shortest lags**. And the secondary state variable (Stage 4b,
`rv_sofar`) gives calm wins at 5 of 5 clocks but a pooled calm t of only **+2.033**: PARTIAL. So
the calm-specific *statistical* claim is directionally consistent under both state variables and
statistically marginal under both. **What is not marginal is leg (ii)**: 15 of 15 cells negative,
3 of 3 states at every clock.

**Stage 2 - where the skill lives, and this is the part that answers the question asked.** Delta
OOS R-squared by state: calm **0.016-0.041**, mid **0.037-0.071**, volatile **0.012-0.054**. The
increment is **not concentrated in the volatile state** - if anything the trough is the volatile
state at 13:00 (0.012) and the peak is the *mid* state at 14:00 (0.071). **The regime-detector
reading is refuted.**

**Stage 3 - the economic leg, and it is the strongest thing here.** sd of the normalized move
`|fwd|/exp(y_hat)`, by state, mean over the five clocks: **calm -11.7%**, mid -2.9%, volatile
-13.7%. In the calm state it is MATERIAL (the >= 5% bar O-6 set) at **5 of 5 clocks**
(-3.3 / -10.1 / -11.4 / -18.3 / -15.4). So the benefit is **U-shaped with the trough in the middle
state**: exactly where a realized-vol sizer is least wrong, the chain adds least, and where it is
most wrong - a quiet tape that does not stay quiet - the chain adds most. The pre-registered
primary breach count (level-scaled, a correction O-6 justified post hoc and this item adopted
*before* running) improves in calm at 5 of 5, -4.5% to -17.6%.

**Reported against itself.** The **raw** 3-sigma breach count in the calm state moves the *wrong*
way at 4 of 5 clocks (11:00 66->72, 12:00 75->78, 13:00 67->81, 14:00 77->90; only 10:00 improves,
81->78). That is the same level artifact O-6 hit, and it is **worse in the calm state than
anywhere else**, which is consistent with the story above and is still a real caveat for anyone
building a hard risk limit off `exp(y_hat)` without recalibrating its level.

**Stage 4a, the mask attack, and it lands.** The feature-complete mask survives 93.9 / 88.4 / 83.8
/ 81.3 / **77.3**% of calm-state cells across the clocks, and the cells it drops are far quieter
than the ones it keeps (calm kept mean |fwd| 35.0 / 30.4 / 27.5 / 23.9 / 19.6 bps against dropped
15.9 / 14.5 / 11.0 / 10.9 / 10.1 bps - a factor of 2 to 3). **So "calm" here means the busier end
of calm**: the quietest sessions in the bucket are preferentially absent, and at 14:00 nearly a
quarter of them are. The calm claim is about the sessions that survive, and no disk-only test can
extend it to the ones that do not.

**Decision: PASS on the pre-registered rule - and it closes this track rather than advancing it.**
The reason is not the statistics. O-6 handed its next step to the sizing tracks as **A-15**, and
A-15 has since been run by `iterate` and **REFUSED on the mechanism**: the intraday sleeve is paid
**+$2,651/day per 1 sd of the volatility SURPRISE at t +8.41** and **-$230/day per 1 sd of the
PREDICTABLE part at t -0.73**, and adding the chain moves the explained variance 0.090 -> 0.100 -
one point of R-squared on the half of magnitude that does not pay. O-7 does not contradict that and
does not try to: A-15 is about a *book's P&L*, O-6 and O-7 are about *forecast accuracy on SPY*,
and both can be true at once. Read together they are the track's closing sentence: **the chain's
magnitude skill is real, it is general across volatility states, it is economically material to
anything sized to |move| - and this repository contains no book that is paid for the predictable
part of magnitude.**

**Nothing shipped.** No shipped file, no runner-loaded file, no config, no `champion.json`; the
only new file is `scripts/sweep_o7.py`, which imports its measurement from `sweep_o6` rather than
re-implementing it. No deploy gate owed.

**Correction filed against this track's own record.** O-6 appended a second justification for the
Theta VALUE ask to `BLOCKERS.md` on the strength of the sizing product. A-15 has since removed that
product. An addendum recording the retraction is appended there - the SPXW justification is
untouched, but the loop should not be quoting a benefit that has since been measured and refused.

**Ledger**: 46 DIAGNOSTIC rows under `options/odte_o7_volstate`.
`python scripts/sweep_o7.py` reruns every number here from disk in ~3 min.

**Operational**: unchanged - `py -3.11` has no pyarrow; run `sweep_o*` on the default `python`.

**Next step: none on this track.** Every question this store can answer from disk is now answered
(O-2 cost, O-3 selection, O-4 feeds, O-5 direction, O-6 magnitude-incrementality, O-7
magnitude-generality), and the two that remain - a second underlying, and any session after
2026-09-10 - both need the Theta subscription restored. O-4's advice stands and is now
unconditional: **do not schedule this scope again until VALUE is restored.**

---

## 2026-09-13 - O-6: the first PASS this track has produced. The chain's magnitude skill is NOT a restatement of the tape - it is incremental out of sample at all five clocks and cuts the dispersion of a sized book by 4-14%. It is a RISK input, not a return signal, so the cost wall never applies to it. Nothing shipped; the O-track is evidence-only and sizing is not its scope.

**Why this item, when O-5 said the axis was closed and O-4 said the track should not be
scheduled.** Both of those verdicts are about *collecting an edge*, and both are correct. O-2
refused the SPY 0DTE credit spread on the options round trip, O-3 closed selection at cover 1.043,
O-4 disqualified free trade-print feeds, and O-5 moved the same chain signal into SPY - cutting
the round trip 68x to 3.41 bps - and watched the *directional* edge shrink to match, best cover
0.963, zero cells above 1. O-5's closing instruction, "do not re-open as a feature, clock, horizon
or instrument question", is about **direction**, which is what all 20 of its cells traded.

But O-5 printed one number it never examined. Its Gate-0 control was
**corr(`rn_half`, |forward move|) = +0.540 at t = +60.0** over 8,777 cells, reported only as
evidence that feature extraction was not broken, and its own closing sentence conceded the chain
"forecasts magnitude superbly". That is the largest statistic this track has produced, it is about
**magnitude**, and a magnitude forecast is not a return signal - **it changes position size, and
sizing is free.** The cost wall that killed O-2/O-3/O-5 cannot reach it. So the last open question
on this store was never whether the chain knows something. It was whether **what the chain knows
is already on the tape** - which O-5 could not have answered, because it never regressed the chain
against the realized tape available at the same instant.

**Theta re-checked live first, as every run on this track does:** `theta_data.py --check` returns
`listening True serving True`, `history/quote` **HTTP 403 "you only have a FREE subscription"**.
The store is still frozen at 1,891 sessions ending 2026-09-10. O-6 ran entirely from disk and
**built no new chain feature and used no new clock** - the chain side is read from O-5's frozen
cache, not rebuilt.

**Hypothesis.** At a fixed intraday clock, the chain's risk-neutral half-interquartile span
(`rn_half`) carries information about the magnitude of the **remaining** session's move in SPY
that is not contained in the realized tape observable at the same instant.

**Design, pre-registered in `scripts/sweep_o6.py`'s docstring before any run.** Target
`y = log(max(|fwd|, 1e-5))`, where `fwd` is O-5's own forward return (entered one full minute
after the clock, exited at the 15:50 open, on real consolidated SPY minute bars). Tape baseline,
all strictly causal at the clock and all from the same Alpaca file O-5 priced its trades on:
`rv_sofar` (realized vol of 1-minute returns 09:30 -> clock), `rng_sofar` (high-low range so far),
`rv20` and `absret_1` (strictly prior sessions). Chain predictor `log(rn_half)`, **declared
positive**. Everything enters in logs, so no predictor is advantaged by the transform. Both models
are fitted on exactly the feature-complete subset. Five clocks, Bonferroni **|t| > 2.576**,
Newey-West at 5 lags because realized vol is persistent and OLS t's would be overstated.
Pre-registered pass for Stage C required **both** a lower OOS RMSE overall **and** two-of-three
regimes; pre-registered MATERIAL for Stage D was declared in advance as a >= 5% cut in the sd of
the normalized move or >= 10% fewer 3-sigma breaches.

**Gate 0 reproduces O-5 exactly**: control +0.5396 against the +0.540 on record, t +60.04, n
8,777.

**Stage A - `rn_half` is the single best predictor of |move| at every clock, beating the tape's
own nowcast.**

| clock | `rv_sofar` | `rng_sofar` | `rv20` | `absret_1` | **`rn_half`** |
|---|---|---|---|---|---|
| 10:00 | 0.352 | 0.351 | 0.298 | 0.113 | **0.401** |
| 12:00 | 0.346 | 0.319 | 0.259 | 0.100 | **0.403** |
| 14:00 | 0.403 | 0.351 | 0.292 | 0.146 | **0.442** |

(Pearson on logs; Spearman on the raw target agrees at 0.42-0.47 for `rn_half`.)

**Stage B - incremental in sample, 5 of 5 clocks, and not marginally.** t on the `rn_half`
coefficient runs **+8.09 to +9.55** against a Bonferroni bar of 2.576, the declared positive sign
holds 5 of 5, and mean delta-R-squared from adding the chain is **+0.036**.

**Stage C - the decisive stage. Causal, expanding-window, out of sample: 5 of 5 clocks pass
two-of-three.**

| clock | OOS R2 tape | OOS R2 +chain | d RMSE | DM t | regimes won |
|---|---|---|---|---|---|
| 10:00 | 0.1213 | **0.1488** | -1.58% | +3.84 | 3 of 3 |
| 11:00 | 0.1289 | **0.1583** | -1.70% | +3.54 | 3 of 3 |
| 12:00 | 0.1087 | **0.1534** | -2.54% | +4.24 | 3 of 3 |
| 13:00 | 0.1012 | **0.1348** | -1.89% | +3.52 | 2 of 2 available |
| 14:00 | 0.1570 | **0.1983** | -2.48% | +3.97 | 2 of 2 available |

Out-of-sample explained variance of log|move| rises by **+0.027 to +0.044**, a 23-41% relative
gain, with Diebold-Mariano t **+3.5 to +4.2** on the squared-error difference. **Stated plainly
because the table hides it**: at 13:00 and 14:00 the 250-session burn-in plus the shrinking
feature-complete subset leaves 2016-2019 under the 100-row floor, so "2 of 3" there is **2 of 2
available**, not 2 of 3 attempted. The three clocks that do have all three regimes win all three.

**Stage D - and here the pre-registered rule passes while one leg of it points the other way.**
The sd of the normalized move `|fwd| / exp(y_hat)` falls **-4.31 / -8.52 / -10.88 / -14.28 /
-11.99 %** across the five clocks, so **4 of 5 clear the pre-registered 5% bar** (10:00 misses at
-4.31% and is reported as a miss). But the **raw** 3-sigma breach count moves the *wrong* way at
13:00 (+10.4%) and 14:00 (+14.5%). That is not buried: a forecast that tightens the middle while
fattening the tail is exactly the wrong trade for a sizing rule, and it was worth chasing.
**Post-hoc, and labelled as such**: `exp(y_hat)` is a conditional geometric mean rather than a
sigma, and the two models sit at different levels (`mean(z)` 1.6501 tape vs 1.6656 chain at
13:00), so a fixed 3.0 cut charges the level difference as a tail difference. Rescaling each model
to `mean(z) = 1` and re-counting gives **-31.6 / -11.1 / -15.1 / -23.0 / -9.1 %** - the right way
at all five. The pre-registered verdict rests on the sd leg, which is clean; the scaled breach
numbers are post-hoc and are reported beside the raw ones, never instead of them.

**Three attacks, all pre-committed to code before the write-up, none of which kills it.**

- **Stage E, the stale-chain test.** The store is 5-minute bid/ask *snapshots* stamped at the
  interval tick, and O-5 enters a full minute later, so a leak would need the stamp to mean
  something other than it says. Rather than argue from a column name, the gap was widened to a
  full hour: every predictor read at clock C, target measured from C+60m to 15:50. **Survives 4 of
  4 pairs at t +7.60 to +10.79.** No sub-hour timing artifact is available to explain this.
- **Stage F, the harder baseline** - the commonest way an "incremental information" claim is
  wrong. Added `rv_30m` (realized vol of the last 30 minutes before the clock, the tape's own
  nowcast and the closest realized analogue of what a 0DTE chain prices) and `rv5`. **Survives 5
  of 5 in sample and 5 of 5 out of sample** (d RMSE -1.16% to -2.50%, DM t +2.97 to +4.17).
  **One place where the attack lands and it is recorded**: at 14:00 the harder tape lifts R-squared
  0.1655 -> 0.2004 and cuts the chain's increment from +0.0455 to +0.0199, t 9.31 -> 6.11. So
  **about 56% of the 14:00 increment was baseline weakness**, against 6-13% at the other clocks.
  The finding survives; its size at the last clock does not.

**Decision: PASS on the pre-registered rule - and nothing ships, because shipping is not this
track's scope.** O-6 measures a forecast, not a trade. The thing it improves is *position size*,
which lives in the intraday (`iterate`) and `ml` sleeves, and AGENTS.md keeps this track inside
`scripts/sweep_o*`, `scripts/odte_*` and `scripts/theta_data.py`. No shipped file, no
runner-loaded file, no config and no `champion.json` was touched, so **no deploy gate is owed**.
`sweep_o2.py` / `sweep_o3.py` were not even imported this time; the only inputs are O-5's frozen
parquet and the Alpaca minute store.

**The durable finding, in one line.** Five items on this chain now agree on a single shape:
**the chain is priced efficiently in direction and informative in magnitude.** O-2, O-3 and O-5
each measured a directional or premium-harvesting construction and each landed at cover ~= 1 - the
market charges almost exactly what the signal is worth. O-6 measures the second moment instead,
where there is nothing to charge, and finds skill that the tape does not already contain and that
survives a one-hour buffer and a strengthened baseline. **The cost wall was never a statement
about the chain's information; it was a statement about what can be sold back to the people who
priced it.**

**What this does and does not change for the human.** It does **not** re-open O-2, O-3 or O-5, and
it is **not** a reason to trade options. It does add a second, cheaper justification to the VALUE
ask already in `BLOCKERS.md`: the frozen store now has a demonstrated product, and every session
after 2026-09-10 that the subscription stays FREE is a session this input cannot be computed for -
which matters for a *risk* input in a way it never did for a refused trade. Appended there.

**Ledger**: 40 DIAGNOSTIC rows under `options/odte_o6_magnitude` (5 stages x 5 clocks, plus Stage
A's 25). `python scripts/sweep_o6.py` reruns every number here from O-5's cache in ~90 s.

**Operational**: `py -3.11` still has no pyarrow - run `sweep_o*` on the default `python`.

**Next step, and it is a handoff rather than a continuation.** The O-track has taken this as far as
its scope allows. The open question is now **the `iterate`/`ml` one**: does an `rn_half`-based size
scaler beat the sleeve's current realized-vol sizing on the sleeve's own P&L, after costs and
under the two-of-three rule? That is a different universe (the intraday sleeve is disjoint from
SPY) and a different file set, so it is filed as **A-15** for whoever owns sizing, not done here.
The honest caveat travels with it: this is measured on SPY, on a sample tilted volatile by O-3's
mask (it drops calm sessions preferentially - O-5 measured mean |move| 13.3 bps where it drops out
against 38.7 bps where it survives), and it has **never** been tested on another underlying,
because the store has exactly one.

---

## 2026-09-12 - O-5: the cost wall is not an options-market phenomenon. Moved the same chain signal into the underlying, cut the round trip 68x, and the edge shrank to match it. Refused; nothing shipped.

**Why this item, when O-4 said the track should not be scheduled.** O-4's conclusion was that no
item can advance *from the Theta feed* - correct, and re-confirmed live at the top of this run:
`theta_data.py --check` returns `listening True serving True` with `history/quote` at **HTTP 403,
"you only have a FREE subscription"**. SPXW is still one `fetch_day` behind that 403. But O-4's
survey of remaining questions was of *options trades*, and every refusal this track has produced -
O-2 on cost, O-3 on the ceiling of selection, O-4 on the blind estimator - is about the cost of
**transacting in options**. None is about the **information content of the chain**. An
options-derived signal does not have to be harvested in options. That is the one lever never
pulled, it needs nothing but disk, and it is what O-5 tests.

**Hypothesis.** The SPY 0DTE chain's risk-neutral state at a fixed intraday clock carries a
*directional* forecast of the rest of the session's move in SPY, big enough to pay an **equity**
round trip - 3.41 bps of notional on this repository's own cost model, against the ~230 bps of
risked capital that killed O-2. A factor of **68**. If the chain knows anything about direction,
this is the cheapest possible way to collect it.

**Why this is not O-1 re-opened.** O-1 refused an IV gate and its negative was "the payoff
regressor is a volatility *surprise*, so no forecast can reach it" - measured on *prior-day,
end-of-day, 1-week* IV against **|P&L|**. Two things differ. (a) The observation is
**same-session and intraday**: the 0DTE chain at 12:00 prices the move that has not happened yet,
conditional on everything that has, so it is a nowcast of the residual session, not a forecast of
the whole day. (b) The target is the **sign**, which O-1 never tested - its own words were
"implied vol forecasts how big a day will be and not which way". O-1's single |t| > 2 against P&L
was `skew25_1w` at t = -2.81, a *direction* reading it left unexamined.

**Design, pre-registered in `scripts/sweep_o5.py`'s docstring before any run.** Four features x
five clocks {10:00, 11:00, 12:00, 13:00, 14:00}, exit 15:50, **1,890 sessions / 9,445 cells**,
2016-01-08..2026-09-10. Features are read from the chain bar at the clock; the SPY position is
entered at the **open of the minute bar one full minute later** and exited at the open of the
15:50 bar, priced on **real consolidated SPY minute bars** (`data/minute_alpaca/SPY.parquet`), not
on the synthetic parity spot. Every Stage-B threshold is a trailing 60-session median, shifted one
session. Directions were declared up front and the gate is **two-sided**, so it can find either
sign and a pass against the declaration is reported as such.

| feature | definition, at the clock | declared |
|---|---|---|
| `rn_skew` | `p_put(S(1-0.005)) - p_call(S(1+0.005))` off the chain's own `dP/dK` (O-3's) | high -> negative |
| `rn_tail` | the same read at 2.0% of spot - crash-premium tilt, not near-body tilt | high -> negative |
| `rn_drift` | `(K_med - S)/S`, `K_med` = strike where the put's prob-ITM crosses 0.5 | above spot -> positive |
| `d_rn_skew` | `rn_skew(clock) - rn_skew(09:35)` - the intraday *repricing*, O-1's surprise | steepening -> negative |
| `rn_half` | **control, not traded**: half the risk-neutral interquartile span | must predict \|move\| |

**Gate 0 passed, and it is what makes the rest readable.** The chain's put-call-parity spot agrees
with the real tape at **median 0.23 bps, p99 2.19 bps**, so the join and the parity spot are sound.
The control is emphatic: **corr(`rn_half`, |forward move|) = +0.540 at t = +60.0**. The chain
forecasts *magnitude* extremely well on this very sample - which is precisely why a null on
direction is a statement about direction and not about broken feature extraction.

**Two pre-registration errors, both found before any forward return was looked at, both stated
rather than quietly patched.** (1) I declared `rn_skew` would be *identical* to
`sweep_o3.features`. It is not: relaxing O-3's both-rights-two-sided mask to a per-right one also
moves `np.interp`'s bracketing neighbours, so **3 of 8,777 cells differ** (worst 5.01e-01, exact on
**99.97%**, Spearman 0.9993). The check was replaced with an agreement criterion *after* it failed;
no forward return enters it either way, it compares two features with each other. The looser mask
is kept as primary for a reason worth recording: **O-3's mask does not drop cells at random - it
drops the calm ones**, mean |move| **13.3 bps where it drops out against 38.7 bps where it
survives**, because the far wings go no-bid on quiet days. Stage A is reported on **both** masks
and the answer does not move. (2) `rn_tail` is **degenerate**: 28% of cells are exactly zero
overall, **42% by 14:00**, because a 2%-of-spot move prices to zero on *both* wings as the session
decays. Terciles collapse; the groups are reported with their realized sizes rather than presented
as equal thirds.

**Stage A - is there a directional signal at all? 3 of 20 cells reach nominal |t| > 2, 0 of 20
survive Bonferroni (|t| > 3.02 at 20 tests, where ~0.7 nominal passes are expected by chance).**

| clock | feature | T1 / T2 / T3 (bps) | t(T3-T1) | monotone? |
|---|---|---|---|---|
| 10:00 | `rn_skew` | +10.16 / -4.76 / -0.72 | **-2.449** | no - T2 is the lowest |
| 10:00 | `rn_drift` | -3.63 / +1.25 / +7.07 | **+2.375** | **yes** |
| 13:00 | `rn_drift` | -2.67 / +0.73 / +4.34 | **+2.187** | **yes** |
| 10:00 | `o3_rn_skew` (robustness, O-3's mask) | +10.85 / -5.33 / -1.20 | **-2.662** | no |

All three nominal passes carry the **declared** sign, and the 10:00 `rn_skew` reading is *stronger*
on O-3's stricter mask, so it is not an artifact of the mask choice. `rn_drift` is the honest
survivor: monotone at two clocks, in the declared direction. It is also **not a stale chain
re-reading the tape** - corr(`rn_drift`, the SPY move already made that session) is **+0.02 to
-0.05**, and corr with the parity-vs-tape gap is **<= 0.10**. It is real chain information.

**Stage B - does it survive equity costs? 0 of 20 cells clear two-of-three. The best cell is a
coin flip sitting exactly on the cost line.**

| | best cell |
|---|---|
| rule | `rn_drift` @ 10:00, causal long/short on the trailing-60 median, held to 15:50 |
| gross | **+3.28 bps** |
| round trip | **-3.41 bps** |
| net | **-0.13 bps at t = -0.07**, n 1,829, long fraction 0.488 |

The long fraction near 0.49 everywhere is the median split doing its job: these are balanced
long/short books, not a buy-and-hold in disguise (buy-and-hold over the same 10:00->15:50 window
is +1.35 bps). And the regime pattern is decisive against the signal rather than merely
inconclusive: **2016-2019 is negative in nearly every cell** (t -2.4 to -2.9 across `rn_drift`,
`rn_skew` and their clocks), while 2020-2023 is mixed and 2024-2026 negative. Nothing here is
stable across the three regimes in the direction it was declared.

**The result that generalises, and the reason this closes the axis rather than one feature.**
Printed as the `BOUND` block and labelled post-hoc, deliberately in O-3's units:

- `cover` = gross / round trip. **Best of 20 cells, chosen with full hindsight: 0.963.**
  **Zero cells have cover > 1** - not one construction's gross edge covers even the equity cost,
  before any question of significance.
- O-3's cover on the options version of the same chain was **0.319 / 0.765**. O-5 cut the cost by
  **68x** by moving the trade into the underlying, and cover moved to **0.963** - still under one.
  The edge shrank almost exactly as fast as the cost.

**Decision: refused, and the "trade the chain's information somewhere cheaper" escape is closed.**
Nothing shipped, nothing promoted, no config touched, no owner risk posture changed. The durable
finding is the one that took three iterations to see and is now visible in one line: **three
independent constructions on this chain - a credit spread (O-2), a selected credit spread (O-3),
and a directional equity trade (O-5) - all land at cover ~= 1.** The cost wall was never a property
of the options market's spreads; it is a property of how much this chain actually knows. It
forecasts *magnitude* superbly (+0.540 at t +60) and *direction* at the level of the transaction
cost of whatever instrument you use to collect it. **Do not re-open as a feature, clock, horizon or
instrument question** - a fourth construction on the same chain will find cover ~= 1 again.

**Ledger**: 40 DIAGNOSTIC rows under `options/odte_o5_direction` (20 Stage A, 20 Stage B). Feature
cache at `results/options/o5_features.parquet` (gitignored); `python scripts/sweep_o5.py` rebuilds
it in ~3 minutes and reruns every number here from cache in seconds. `sweep_o2.py` and
`sweep_o3.py` were **imported, not modified**; no shipped or runner-loaded file was touched, so no
deploy gate is owed.

**Operational**: `py -3.11` still has no pyarrow - run `sweep_o*` on the default `python`.

**Next step.** With O-5 closed, every question this store can answer has been answered and the
remaining one - **cash-settled European SPXW**, where O-2's fatal exit assumption becomes a fact
and commission per unit of risk falls ~10x - is unchanged behind the **VALUE-tier 403** already in
`BLOCKERS.md`. O-4's advice stands and O-5 does not weaken it: **this track should not be scheduled
again until VALUE is restored.** The one thing O-5 adds to the ask is that it is now the *only*
open item, so the scheduler is otherwise idle on this scope.

---

## 2026-09-12 - O-4: the free options feed cannot refuse a bad trade. Trade prints disqualified; the track is blocked on the human. Also: half of O-3's blocker diagnosis was wrong and this repository caused it.

**Housekeeping first, because it changes how this entry should be read.** O-4 was designed, run
and recorded by the previous run on this track at 17:56 UTC (60 DIAGNOSTIC rows under
`options/odte_o4_feed`), which then ended without journaling or committing anything. This entry
lands that work, and it does not take it on trust. Before writing a word of it:

- the full 60-cell grid was **rerun from scratch over all 1,891 stored sessions** (141 s) and
  reproduces the recorded numbers exactly - sign flips 10, decision flips 0, 56 decisive refusals,
  33 lost, 6 turned positive, blind term 1.610, Spearman 0.776;
- the load-bearing *external* claim was **re-probed live on the Alpaca key**:
  `/v1beta1/options/quotes` is **HTTP 404**, while `/bars` and `/trades` return 200 on the same
  contract and `/snapshots/SPY` returns only a *current* bid/ask;
- the Theta entitlement was **re-checked live** with the new `--check`: `listening True serving
  True`, `history/quote` is **HTTP 403 "requires a value subscription ... you only have a FREE
  subscription"**. The blocker is still open as of 20:4x UTC today.

**Correction to O-3, and the loop caused the error.** O-3 reported "every options endpoint returns
HTTP 478" and read 478 as the lapsed entitlement. It never was. The body says *Invalid session ID.
This can occur if more than one terminal is running* - and more than one was running because
`theta_data.alive()` treated **any** HTTP error as "terminal is dead", so `start_terminal()`
launched a second instance at 10:32. It could not bind the port (`Address 127.0.0.1:25503 already
in use`, in `terminal.out`) but its login invalidated the live instance's session, turning a
recoverable 403 into a dead data path. Stopping both and starting exactly one restored the listing
endpoints immediately. Fixed in `scripts/theta_data.py`: `listening()` now separates "nothing bound
to the port" from "bound and answering with an error", `alive()` no longer reads an HTTP error as
death, `start_terminal()` **refuses** to start a duplicate, and `--check` reports terminal state and
entitlement in one call. **The other half of O-3's diagnosis stands**: the subscription really did
lapse, STANDARD -> FREE between 2026-09-10 02:24 and 2026-09-12 13:32.

**The ask is cheaper than O-3 implied.** The 0DTE store is built by `odte_data.py`, which calls
exactly one endpoint, `/v3/option/history/quote`, and that needs **VALUE**, not STANDARD. VALUE
unfreezes the store, catches up the missing sessions and buys SPXW. STANDARD is needed only by
`scripts/iv_regime.py`, whose output is already on disk. Recorded in `BLOCKERS.md`.

**Hypothesis.** Before this track spends an iteration porting itself to the only reachable free
options source, measure what porting would do to its verdicts. O-2 refused the SPY 0DTE credit
spread on **cost**, not edge, and the decisive term was the spread crossed on every fill (-1.363%
of the position's own max loss against gross +0.783%). A trade-print dataset cannot see that term.
So: **re-price the same trades two ways and count the decisions that change.**

**Design, pre-registered in `scripts/sweep_o4.py`'s docstring before any run.** Same sessions, same
trades, same columns out of `sweep_o2.run_session` - `sweep_o2.py` is imported, **not modified**,
and no shipped or runner-loaded file was touched, so no deploy gate is owed.

| estimator | definition | what it represents |
|---|---|---|
| `NET_QUOTE` | `pnl / risk` - short leg sold at the bid, long bought at the ask, reversed on exit, plus commission | O-2's method, and the truth |
| `NET_PRINT` | `(pnl_gross - fees) / risk` - every fill at the mid, plus commission | the best a trade-print dataset can do |

`NET_PRINT` is deliberately **generous**: real prints sit nearer the far touch on a marketable
order, so an honest Alpaca backtest is at least this wrong. Every number below is an upper bound on
the fallback's accuracy. Grid is O-2's own axes unchanged, so no new tuning enters:
`{put, call} x target {0.05, 0.10, 0.16, 0.25, 0.35} x width {0.30%, 0.75%, 1.50%} x entry
{10:00, 14:00}`, exit 15:50, fee $0.75 = **60 cells x 1,891 sessions**. Verdict rule is O-2's,
applied identically to both: mean > 0 at t > 2 in >= 2 of 3 regimes.

**Result on the pre-registered statistics - and the headline had no power.**

| statistic | value |
|---|---|
| cells evaluated | 60 |
| 1. SIGN FLIP (print > 0 >= quote) | **10** (16.7% of the grid) |
| 2. DECISION FLIP (passes on print, fails on quote) | **0** <- the declared headline |
| 3. FALSE NEGATIVE | 0 |
| 4. BLIND TERM `spread_cost / risk` | mean **1.610** points of max loss (min 0.335, max 8.313) |

Statistic (2) is zero for a degenerate reason, not a reassuring one: **no cell reaches t > +2 under
either estimator**, so a test that only detects a fallback *inventing a pass* is identically zero
here whatever the fallback does. Stating that plainly rather than reporting "0 false positives, the
feed is usable" is the whole point. The identity holds exactly - `quote% - print%` equals the blind
term by construction at max |difference| **1.78e-15** - which is the arithmetic check that the two
estimators differ in the spread and in nothing else.

**The direction that does have power, declared post-hoc and labelled post-hoc in the output.**
Every O-item to date has ended in a refusal, so the question this track actually depends on is the
mirror image: **can the fallback still refuse?**

| | |
|---|---|
| cells decisively refused on quotes (t < -2) | **56 of 60** |
| of those, no longer decisive on prints (t > -2) | **33 (59% of the refusals lost)** |
| of those, prints report a **positive** mean | **6** |
| bias / effect: mean blind term vs mean \|print%\| | **2.72x** |
| Spearman(quote%, print%) across the grid | 0.776 |

The single cell a trade-print study would have picked as its best is
**put 0.35, 1.50% wide, entry 14:00: print +0.356% (t +1.28)** - which at the quote is
**-0.477% (t -1.54)**. The fallback's error is not noise that averages out over 1,891 sessions: the
spread cost is non-negative by construction, so it is a **one-directional bias**, and it is 2.7x
the size of the effect being measured. Rank correlation of 0.776 is the trap - the ordering mostly
survives, so the fallback *looks* usable, while the level that every verdict on this track turns on
is displaced by more than the verdict.

**Decision: trade-print data is disqualified for cost-sensitive options research on this track, and
the track is blocked on the human.** Nothing shipped, nothing promoted, no owner risk posture
changed. This is a negative result about a *data source*, not about a strategy, and it closes the
"can we work around the lapsed subscription for free?" question that would otherwise have consumed
several iterations. A feed that cannot refuse a bad trade is not a fallback for a track whose every
result so far has been a refusal.

**Ledger**: 60 DIAGNOSTIC rows under `options/odte_o4_feed` (already appended by the run that
produced them; this entry adds none). Grid CSV at `results/options/o4_feed_grid.csv` (gitignored).

**Operational note for the next run on this track**: `py -3.11` has **no pyarrow**, so every
`sweep_o*` script that touches the parquet store must be run with the default `python` (3.14).
`py -3.11 scripts/sweep_o4.py` dies in `pd.read_parquet` before doing any work.

**Next step, and there is only one that is not the owner's.** The store is intact and frozen at
1,891 SPY sessions (2016-01-08..2026-09-10, 176 MB) and every question it can answer has been
answered: O-2 closed delta, width, entry time, structure and stop; O-3 closed selection and bounded
it at net zero; O-4 closed the free-substitute escape hatch. The one remaining question -
**price the same premium in cash-settled European SPXW**, where O-2's fatal exit assumption becomes
a fact and commission per unit of risk falls roughly tenfold - is one `fetch_day('SPXW', ...)` away
and is blocked precisely by the 403. **VALUE tier on Theta is the whole ask**; it is in
`BLOCKERS.md` with the endpoint-by-endpoint evidence. Until it is answered this track should not be
scheduled - it has no item that can advance from disk.

---

## 2026-09-12 - O-3: the 0DTE variance risk premium is not conditional, and the ceiling on selection is net zero. Refused. Nothing shipped.

**Hypothesis.** O-2 refused the SPY 0DTE credit spread on COST, not on edge: it measured a real,
calibrated variance risk premium (the chain's quoted breach probability exceeds the realized
breach rate at z = -2.7 to -3.8 in six of six delta/right cells) and then showed that harvesting
it costs more than it pays - gross +0.783% of the position's own max loss against spread -1.363%
and commission -0.950%, net -1.530%. O-2 closed the delta, width, entry-time, structure and stop
axes. **One lever survived all five: selection.** Every cost term is paid per session traded, so a
filter that keeps only the sessions where the premium is richest raises gross per unit of cost
without touching a single parameter of the trade. O-2's own conditioning test (STRESS 2) used only
`iv_regime.parquet` - the ATM 1-week implied level and the term ratio, both *external* to the
traded chain. The chain the trade is written on carries information that study never used.

**Design, pre-registered in `scripts/sweep_o3.py`'s docstring before any run.** Two features,
two directions, terciles formed *within* regime, both reported whatever they say:

| feature | definition (causal, from the entry-timestamp chain and strictly prior sessions) | declared direction |
|---|---|---|
| `rn_skew` | `p_put(S(1-0.005)) - p_call(S(1+0.005))`, interpolated on the strike grid from the chain's own `dP/dK` - the asymmetry of the risk-neutral distribution | sell the side the market overpays for -> top tercile |
| `vrp` | `rn_half - rz_half`: half the risk-neutral interquartile span (distance to the 0.25-prob-ITM strike, both rights, as a fraction of spot) minus the median `\|spot_exit/spot_entry - 1\|` over the previous 20 stored sessions on the same clock | sell when the premium is rich -> top tercile |

Base cells taken **unchanged from O-2's own verdict list**, so no new tuning enters here: **B1** =
put 0.16 prob-ITM, 0.75% wide, enter 10:00, close at the quote 15:50 (O-2's default); **B2** = put
0.25, 1.50% wide, enter 14:00, close 15:55 (O-2's best cell). Both closed at the quote - the
expire-free branch is deliberately excluded, because O-2 showed the exit assumption is what fails.
Gates: **Stage A** gross monotone across terciles *and* `|t(T3-T1)| > 2`; **Stage B** net > 0 at
t > 2 in >= 2 of 3 regimes; **placebo** the complement must not also pass; n >= 100 per cell.

**Identity, both exact.** `sweep_o2.run_study(B1)` over the whole store reproduces the ledger row
O-2's verdict rests on (`20260910T203647Z`) to every recorded digit - **1,889 sessions, -1.5301%,
t -3.20** - and restricted to O-3's 1,848 feature-complete sessions it equals O-3's control at
**max |difference| = 0.000e+00**. The gap between the two is 41 dropped sessions and nothing else;
no line of the trade was re-implemented. `scripts/sweep_o3.py --identity` reruns both.

**Result: 0 of 4 feature/cell pairs clear Stage A. Stage B never ran.**

| cell | control net% (t) | feature | gross T1 / T2 / T3 | t(T3-T1) | Stage A |
|---|---|---|---|---|---|
| B1 | -1.575 (-3.22), n 1,848 | `rn_skew` | 2.365 / -0.884 / 0.723 | -1.61 | FAIL (non-monotone, wrong sign) |
| B1 | | `vrp` | 1.143 / 0.865 / 0.561 | -0.52 | FAIL (monotone, **wrong direction**, null) |
| B2 | -0.242 (-0.88), n 1,645 | `rn_skew` | 1.271 / 0.337 / 0.748 | -0.76 | FAIL (non-monotone) |
| B2 | | `vrp` | 0.908 / 0.411 / 1.009 | +0.15 | FAIL (non-monotone) |

**The `vrp` row is the informative one.** On B1 it is cleanly monotone over 1,768 sessions and it
runs the *opposite* way to the declared direction: the richer the premium the chain is handing the
seller, the *lower* the gross return. That is the textbook reason implied vol is not a free lunch -
it is high because realized is about to be high - and it is now measured on this store rather than
assumed. Selling more when the premium looks rich is the wrong trade here, and selling less does
not help either, because the difference is null at t -0.52.

**The result that generalises, and the reason this closes the axis rather than one feature.**
Printed as the `BOUND` block, labelled post-hoc:

- `cover` = gross / (spread + fee). **`cover = 1.000` IS net zero by construction**, so any filter
  must find sessions with cover > 1 out of sample. Unconditional cover is **0.319 on B1** (needs a
  3.14x lift) and **0.765 on B2** (needs only 1.31x).
- Per-session **corr(gross, cost) = -0.598 (B1) / -0.482 (B2)**. The expensive sessions are the
  *losing* ones - a breached position is bought back through a wide quote - so cost and edge are
  adversely coupled and cannot be pulled apart by choosing sessions.
- **The best of twelve terciles, chosen with full hindsight: B2 `rn_skew` T1, n 550, cover 1.043,
  net +0.052% at t +0.09.** That is the ceiling. Even the single most favourable sixth of the
  sample, selected after seeing every answer, is a coin flip at exactly zero. Two cells reach
  cover ~= 1.0 (1.043, 0.997) and both are net ~= 0, which is the identity restating itself.

**Decision: refused, and the selection axis is closed with the other five.** O-2's five axes plus
this one now span every lever on the SPY 0DTE credit spread that does not require different data.
**Do not re-open as a feature, threshold, quantile or conditioner question** - the bound is not a
property of `rn_skew` or `vrp`, it is the -0.5 to -0.6 coupling between gross and cost, and no
filter built from the same chain escapes a correlation that strong. What O-2 said re-opens it is
still the only thing that does: **OPRA quotes through the closing auction plus the official
settlement print**, which is an owner purchase.

**Ledger**: 14 DIAGNOSTIC rows under `options/odte_o3_select` (both controls, all twelve
terciles). Only `scripts/sweep_o3.py` was added; **`sweep_o2.py` is imported, not modified**, and
no shipped or runner-loaded file was touched, so no deploy gate is owed.

**Blocker found in passing, and it is the bigger news for this track.** The Theta Data options
subscription **dropped from STANDARD to FREE between 2026-09-10 02:24 and 2026-09-12 10:32** (both
lines are in the terminal's own log). Every options endpoint now returns **HTTP 478**, including
the cheapest one: `expirations('SPY')` fails, and the missing 2026-09-11 0DTE chain cannot be
fetched. **The 0DTE store is frozen at 1,891 sessions ending 2026-09-10** and is the only options
data this repository will have until the plan is restored. Filed in `BLOCKERS.md`. O-3 was run
entirely from disk and is unaffected; anything after it is blocked.

**Next step.** With selection closed and the data path dead, the O-track has no item that can
advance without the owner. The one that would have been next - pricing the same premium in a
**cash-settled European index option (SPXW)**, where O-2's fatal exit assumption becomes a fact
rather than an assumption and the commission per unit of risk falls roughly tenfold - is a
`fetch_day('SPXW', ...)` away and is blocked precisely by the 478. It is named in `BLOCKERS.md` as
what the restored subscription would buy.
