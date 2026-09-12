# Research journal - `daily` track

The S-track (daily champion `s1_momo`, LEAN, `scripts/sweep_s*`, `scripts/evaluate.py`). Newest
first. The pre-2026-09-12 history of this track is in `research/journal.md`, which stays the
daily review's merge target; each entry here leaves a one-paragraph pointer there.

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
