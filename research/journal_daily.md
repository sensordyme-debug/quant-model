# Research journal - `daily` track

The S-track (daily champion `s1_momo`, LEAN, `scripts/sweep_s*`, `scripts/evaluate.py`). Newest
first. The pre-2026-09-12 history of this track is in `research/journal.md`, which stays the
daily review's merge target; each entry here leaves a one-paragraph pointer there.

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
