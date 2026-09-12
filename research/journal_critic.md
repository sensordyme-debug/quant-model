# Journal - critic track (C-). Newest first.

The `critic` scope: adversarial verification of other tracks' claims and promotions. This track
runs no new hypotheses. It reproduces controls, re-runs candidates at pinned windows, reads code
for look-ahead, and re-derives the arithmetic behind any number that reaches the owner. It promotes
nothing and it ships nothing.

---

## 2026-09-12 - C-1: S-31 survives four attacks, and the one clause that recommends an action is refused - a 25% drawdown cap does NOT ask the owner to shrink

**Target, and why this one.** The latest promotion is S-18's champion (`promoted_at`
2026-09-11T15:09), but the strongest *claim* of the last 24 hours is S-31 (`9197bd4`), because it
is the only one that has been written into an owner-facing decision table: `BLOCKERS.md`'s open
`margin_budget` question, options (a)/(b)/(c)/(d+), unanswered since 2026-09-10. S-31 re-priced
that decision and concluded "half the advertised gain is not there" and "the Sharpe argument
reverses". If either is wrong the owner is being steered with bad numbers; if clause 7 is wrong the
owner is being handed a wrong *recommendation*, which is worse. A previous critic run left
`scripts/verify_s31.py` written with three attacks pre-registered in its docstring and never
executed - no journal entry, no commit. This run executed it, added a fourth attack, and fixed one
unit bug in it.

**The control, first, because nothing else counts if this fails.** `py -3.11 scripts/backtest.py
s1_momo` with no environment override, fresh run `20260912T151859Z`:

| | champion.json | C-1 re-run | |
| --- | --- | --- | --- |
| Total Orders | 5128 | 5128 | = |
| Compounding Annual Return | 24.403% | 24.403% | = |
| Sharpe / Sortino | 0.994 / 0.987 | 0.994 / 0.987 | = |
| Drawdown | 23.700% | 23.700% | = |
| Total Fees | $27,199.76 | $27,199.76 | = |
| End Equity | 2,467,326.63 | 2,467,326.63 | = |
| PSR | 33.210% | 33.210% | = |
| **OrderListHash** | `a6d6224ce9c70091e5bfa8e96f046bf3` | **`a6d6224ce9c70091e5bfa8e96f046bf3`** | **=** |

All 16 statistics identical, hash bit-exact. **The deploy gate still passes**:
`scripts/compare_orders.py` -> 3,689/3,689 decision dates in agreement, 5,021 orders on the LEAN
side and 5,021 on the runner side, +0. The two LEAN runs S-31 and `BLOCKERS.md` cite were also
checked against disk: `20260911T145705Z` really does log `a6d6224c...` and the new 0.90 run
`20260912T130734Z` really does log `7352a42d118919eec701e44af7a4dfff`. **Nothing about the
promotion is restored or contested.** As a free corroboration, the eng track's E-4 suite runs clean
on 3.11: 107 passed.

**Attack 0 - the identity S-31 says it stops on if it fails. REPRODUCED to six decimals.** The
critic recomputes CAR, Sharpe and drawdown from the daily return series with its own `metrics()`
rather than calling `sweep_s19.summarize`, so the agreement is not a shared code path: fully
charged budget 0.75 gives **19.640168%** against S-31's **19.640168%**, difference **+0.000000**.
One nuisance checked first: `scripts/sweep_s25.py` has uncommitted S-32 edits (`band`, `skip`)
which `legs_simulate` is imported from. Both are inert at their defaults - `band=None` restores
`MIN_ORDER_VALUE` and `skip_p=0` short-circuits before the RNG is drawn - so the identity above is
also the evidence that S-32's in-flight change has not disturbed any earlier row.

**Attack 1 - the missing error bar on the headline. S-31 SURVIVES, and is stronger than it
claimed.** S-31 deflated its own CAR t-stat as "the significance of arithmetic" and then quoted the
Sharpe reversal with no error bar at all. Because a budget change is a near-scalar multiple of one
book (rho 0.996-0.9999), the correct test is Jobson-Korkie with Memmel's correction on the paired
daily returns, not two independent standard errors:

| cell | 0.78 | 0.80 | 0.90 | 1.00 | reading |
| --- | --- | --- | --- | --- | --- |
| A (zero cost) | -0.27 | -0.29 | -0.19 | -0.03 | **null, as it must be** |
| C (2 bp + historic financing) | **-2.18** | **-2.46** | **-2.33** | **-2.01** | significant |
| D (2 bp + today's 3.63%) | **-3.78** | **-4.04** | **-3.64** | **-3.26** | significant |

The attack designed to break the claim confirms it and supplies the number S-31 omitted. Cell A
being null at every budget is the control that matters: raw Sharpe is genuinely flat in size when
nothing is charged, so the decline in C and D is the cost and not the sizing. Extending the grid
*downward* - which S-31 never did - makes the ladder monotone across the whole range at today's
rates: **1.041 (0.70) -> 1.023 -> 1.012 -> 1.004 -> 0.975 -> 0.952 (1.00)**, and the 0.70 step is
itself significant at **t +3.34**. The same caveat S-31 applied to its CAR t-stat applies here and
is not waived: this establishes the *sign*, not a large effect.

**Attack 2 - the risk-free path, the one a priori real weakness. S-31 SURVIVES; the shortcut was
immaterial.** S-31 rebuts the "it is only a Sharpe convention" objection with a *single constant*
rate (the sample's mean effective fed funds, 1.6924%) - the one choice guaranteed to be wrong in
both regimes, since rates were ~0.1% to 2021 and 4-5% from 2023 while the book's leverage was not
constant either. Recomputed by subtracting the **actual daily rate path**, accrued over each
session's own calendar gap on actual/360:

| cell | 0.75 -> 1.00, daily rf path | S-31's constant rate | verdict |
| --- | --- | --- | --- |
| A (zero cost) | **1.155 -> 1.175, rises** | 1.156 -> 1.176 | reproduced to 0.001 |
| C (charged) | **0.956 -> 0.932, falls** | 0.957 -> 0.933 | reproduced to 0.001 |
| D (today's rates) | **0.932 -> 0.881, falls** | - | same direction, steeper |

The regime structure the constant rate ignores does not move the answer at all. S-31's sentence
"subtracting a fixed rate from a numerator while the denominator grows manufactures a rising Sharpe
out of a flat one" stands on the honest path too. (A unit bug in this critic's own script printed
the sample mean as 169.03% on the first pass - `rates.load()` is already in percent - and is fixed;
the corrected mean is **1.6903%** against S-31's 1.6924%.)

**Attack 3 - is the budget dial a scale or a different book? SURVIVES.** Clause 7's inverse solve
is only meaningful if the dial sizes the book, which S-31 verifies at 0.75 alone and then assumes
everywhere. Regressing each budget's daily returns on the shipped book's: **R^2 0.9930 to 0.9999**,
slope monotone **0.938 (0.70) -> 1.283 (1.00)**, in all three cost cells. It is one book scaled.
The Reg-T claim also holds to the digit: peak mark-to-market gross **1.878-1.884x at 0.90** (S-31
said 1.88) and **2.109-2.116x at 1.00** (S-31 said 2.12, over the 2.0 ceiling).

**Attack 4 - THE ONE THAT LANDS. Clause 7's 25% row is refused, and it is refused against S-31's
own calibration.** This is the only clause in S-31 that tells the owner to do something.
`BLOCKERS.md` says: *"The 25% row is the surprising one: the shipped 0.75 book's own drawdown is
25.2%, so a 25% cap is a request to shrink"*, and the table answers a 25% cap with **0.70**, i.e.
below where the book runs, at **-0.79 CAR**. S-31's own stated method is "the harness is optimistic
on drawdown by 0.44 / 1.14 / 1.29 points at 0.75 / 0.80 / 0.90 and **that error is added back**".
Apply it:

| budget | C DD raw | + measured error at that budget | + worst case (1.294) | + nothing |
| --- | --- | --- | --- | --- |
| 0.70 | 23.728 | 24.17 | 25.02 | 23.73 |
| **0.75 shipped** | 24.037 | **24.48** | 25.33 | 24.04 |
| 0.78 | 24.272 | **25.43** | 25.57 | 24.27 |
| 0.80 | 24.475 | 25.61 | 25.77 | 24.48 |
| 0.90 | 25.027 | 26.32 | 26.32 | 25.03 |

**24.037 + 0.44 = 24.48%, not 25.2%.** The 25.2% figure is what you get by adding the error
measured at **0.80** to the **0.75** cell: the calibration table was read off by one row. The
consequence is not cosmetic - it inverts the recommendation:

| cap | S-31 says | measured error | worst case | no adjustment |
| --- | --- | --- | --- | --- |
| **25%** | **0.70 (-0.79 CAR)** | **0.75, no change (0.00)** | **nothing in grid** | 0.80 (+0.68) |
| 30% | 0.90 (+1.99) | 0.90 (+1.99) | 0.90 (+1.99) | 0.90 (+1.99) |
| 35% | 0.90 (+1.99) | 0.90 (+1.99) | 0.90 (+1.99) | 0.90 (+1.99) |

**0.70 is not the answer under any self-consistent rule.** The 30% and 35% rows are untouched.
Because the corrected answer sat 0.13 points from the next budget up on an *interpolated* error,
that gap was closed with a **new LEAN run at 0.78** (`20260912T153817Z`, 25.307% / 1.003 / DD
24.600%, `OrderListHash 50ab65f95bba8ec716934846fa4c6b60`): the measured error there is **1.155**,
larger than the 0.858 interpolation assumed, so 0.78 adjusts to **25.43%** and breaches the cap.
The corrected 25% answer is **0.75, empirically and not by interpolation**. That run also
reproduces S-16's published 0.78 figure of **25.307%** exactly, which is a second claim
corroborated for free.

**The finding behind the finding, which is the reusable part.** The harness drawdown error is
**0.442 / 1.155 / 1.135 / 1.294** at 0.75 / 0.78 / 0.80 / 0.90 - it is *not* monotone in size, it
jumps by 0.7 points between 0.75 and 0.78 and is flat after. S-31 described it as "optimistic on
drawdown and grows more so with size", which is true in level and false in shape, and the shape is
what an inverse solve consumes. **A maximum drawdown is a single-path extremum; its error is a
lumpy statistic and must not be interpolated, extrapolated or reused across cells.** Any clause
that solves for a parameter under a drawdown constraint needs a measured error *at the budget it
selects*, or it needs to be quoted under the worst case and admit that the answer may be "none".
This critic made the same mistake in its own first pass (rule M interpolated 0.858 at 0.78, the
truth was 1.155) and only a real engine run caught it.

**Look-ahead, survivorship, cost model - checked, nothing found.** Causality: `legs_simulate`'s
deployed convention decides on closes through i-1 and fills at i, and the budget enters only
through `sig.Params.margin_budget` in the sizing call, so no feature crosses the decision bar;
the four cost cells differ only in the spread and financing arguments, never in the signal path.
Survivorship: the universe is `sig.traded_universe(p)`, the ETF sleeve, which AGENTS.md names as
the trusted one - the single-name survivorship bias does not reach this book. Cost model: cell C
charges 2 bp one-way plus IBKR Pro financing on the historic effective fed funds series and cell D
the same at 3.63%; both are stricter than the zero-financing LEAN convention the frontier was
originally quoted at, which was S-31's whole point.

**Decision.** S-31 stands on clauses 1-6 and on its headline; **clause 7's 25% row is refused and
corrected in place in `BLOCKERS.md`**, attributed, with S-31's original wording quoted rather than
deleted so the owner can see what changed. **No promotion is contested and no champion is
restored** - S-18 reproduces bit-exact and the gate passes, so there is nothing to roll back.
`margin_budget` is still 0.75; no shipped, runner-loaded, `live/*` or scheduled-task file was
touched, and the only behaviour change anywhere is a corrected table row.

**Ledger.** Two rows appended by `scripts/backtest.py`, both LEAN, both honest runs of the shipped
algorithm: the control reproduction (`20260912T151859Z`) and the 0.78 calibration run
(`20260912T153817Z`). **The 0.78 row is DIAGNOSTIC and not promotable** - it exists to measure a
harness error, it is not a candidate, and its 25.307% must not be read as a proposal to raise the
budget. Every S-31 row already carries its own DIAGNOSTIC tag and none of them is promotable
either, which this run confirms rather than changes.

**Next step for this track.** The two other claims of the last 24 hours that reach a decision and
have not been adversarially checked are **S-24** ("the pre-open move is worth +1.98 CAR at the real
MOO fill") and **S-29** ("the 60 sessions VIX removes that realized does not are worth +36.56
bps"). S-24 is the higher-value target because it proposes a change to the *execution clock* of the
deployed book, and an execution claim that cannot survive `compare_orders.py` is not deployable
whatever its Sharpe. Reproduce with `py -3.11 scripts/verify_s31.py` (~13 min, 18 harness runs).
