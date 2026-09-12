# Journal - critic track (C-). Newest first.

The `critic` scope: adversarial verification of other tracks' claims and promotions. This track
runs no new hypotheses. It reproduces controls, re-runs candidates at pinned windows, reads code
for look-ahead, and re-derives the arithmetic behind any number that reaches the owner. It promotes
nothing and it ships nothing.

---

## 2026-09-12 - C-2: A-13's fixes reproduce on committed code and its headline survives five attacks. Three things do not: clause 2 credits the wrong defect, clause 4's own threshold fails on the window that matters, and the owner-facing tail is 4.7% of the SLEEVE, not of the account. Separately, the deployed sleeve's 09:25 launch gate is failing right now for a reason that has nothing to do with trading

**Target, and why this one rather than the S-24 that C-1 queued.** C-1 left `C-2` pointed at S-24
(the pre-open MOO claim). A-13 (`f1c9968`, 17:32 ET) landed **after** C-1 was written and outranks
it on all three things this track weighs: it is the newest claim; it changes
`algorithms/intraday/base.py`, which the **live trader loads**, plus the shared harness
`scripts/intraday_backtest.py` that every A-track verdict is measured through; and it rewrote an
**owner-facing risk paragraph** in `BLOCKERS.md`, which is the one place a wrong number turns into
a wrong decision. S-24 stays queued as C-3. No promotion is contested here: `research/champion.json`
is byte-identical to `9197bd4` (`git diff` empty) and A-13 never touched it.

**Attack 0 - does it reproduce on the code that is actually committed? YES.** The A-13 rows were
recorded at `b7e87ad` with `git_dirty: true`, and the entry itself admits most harness hunks were
swept into a concurrent `eng` commit. So the first question is whether HEAD (`d290f62`) still
produces them. Re-ran `python scripts/sweep_a13.py --workers 6 --years 2024 2025 2026 --cells
control all` from a clean checkout state:

| | A-13 recorded | C-2 re-run at HEAD | |
| --- | --- | --- | --- |
| control $/day, 674 sessions | -132.53 | **-132.532** | = |
| control t / worst day / stops | -0.22 / -34,300 / 30 | **-0.216 / -34,299.609 / 30** | = |
| control trades/day, costs/day | 39.1 / 1,041 | **39.07 / 1,041.09** | = |
| corrected (`all`) $/day / t | +71.4 / +0.11 | **+71.427 / +0.112** | = |
| corrected worst day / stops | -45,283 / 0 | **-45,283.268 / 0** | = |
| paired difference / t | +204.0 / +1.22 | **+203.96 / +1.22** | = |
| clause 4 sparse pairs | 0 of 10,784 | **0 of 10,784 (0.00%)** | = |

The 11-year run's 2024-2026 slice and this standalone 3-year run agree to **1.5e-9 $/day** (not
bit-exact: a longer feature frame changes the accumulation order inside pandas' rolling mean). That
same dust is the whole of the `atr` cell, and it explains the one number I could not reproduce at
first: A-13's atr paired **t +1.93** is against the *standalone* control (I get **+1.98**, 2e-11
$/day), not against the 11-year slice (**+0.96**). Both are t-statistics on floating-point noise
and A-13 says so itself, in the one sentence of it I would keep above all others: *a t-statistic
without a magnitude beside it is worth nothing.*

**Attack 1 - re-derive the entire headline table from the stored daily series with my own code.
EXACT, all 24 cells.** `results/a13/daily_{control,all}.csv`, my own mean/se/t/min, not
`sweep_a13.stats`:

| window | n | ctrl $/day | t | corr $/day | t | paired | t | ctrl worst | corr worst | ctrl stops |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2016-2019 | 1,006 | -303.4 | -1.25 | -269.3 | -1.11 | +34.07 | +3.12 | -26,826 | -33,445 | 5 |
| 2020-2023 | 1,006 | -528.6 | -1.19 | -605.0 | -1.34 | -76.41 | -1.00 | -30,902 | -46,850 | 57 |
| 2024-2026 | 674 | -132.5 | -0.22 | +71.4 | +0.11 | +203.96 | +1.22 | -34,300 | -45,283 | 30 |
| **ALL** | **2,686** | **-344.9** | **-1.41** | **-309.6** | **-1.24** | **+35.32** | **+0.69** | **-34,300** | **-46,850** | **92** |

Every figure in the journal and in `BLOCKERS.md` matches, and 5 + 57 + 30 = **92** stop-outs is the
claimed count. The isolated 2024-2026 cells reproduce too: `fill` **-1.1861** $/day at t -0.82
(claimed -$1.19 / -0.82), `nav` **+205.1505** (claimed +205.15), `atr` **0 of 674 sessions differ by
as much as a cent**.

**Attack 2 - clause 4 recounted on the store the sleeve actually trades. EXACT.** Independently of
`sweep_a13`, over the whole IBKR store: **0 of 4,208** (symbol, session) pairs have their
opening-range bar at a within-session positional index below 14, so `rolling(14, min_periods=5)`
there can never still contain bar 0. Claim reproduced. The mechanism is sound as well as the count:
`orb` refuses to compute the range until `len(f) >= range_minutes + 1` **and** `minute >= 15`, and
`fd` is sliced per session, so the range bar's positional index is >= 15 by construction on any
session with no missing opening bars.

**Attack 3 - look-ahead in the new fill model. NONE FOUND.** The decision view is
`fd[s].iloc[:j]` where `j` is the count of bars with index `<= t`, so the strategy sees the decision
bar and nothing after it; the order it places is held in `pending` and filled at the *next* printed
bar's **open**. That is strictly more conservative than the model it replaces, which booked an
unfilled order at a price from a bar that had already closed. Marks use last-printed closes. The one
forward-looking expression in the loop is A-11's participation cap, `vrow[s][minute + 1]`, and it is
a **trailing median over strictly prior sessions** (`volume_limits`), not next-minute actual volume -
and `part_cap` is 0.0 in every A-13 cell, so `vrow` is `None` throughout.

**Attack 4 - is the `nav_frac` translation faithful to the live rule? YES, and I checked the live
side rather than the comment.** `intraday_trader.py:595` stops on `pnl <= -DAILY_LOSS_LIMIT *
self.nav_open` with `nav_open` the **account** NAV and `equity = nav * equity_frac`. The harness
(`intraday_backtest.py:336`) stops on `equity - eq_open <= -daily_loss_limit * eq_open / nav_frac`.
Substituting `eq_open = equity_frac * NAV` makes the two identical **iff `nav_frac == equity_frac`**,
which is what the `nav` and `all` cells set (0.25). The default 1.0 reproduces every earlier row.
Correct, and the direction claim follows: a 4x looser stop can only remove stop-outs, and the data
show 92 -> 0 with the worst day never improving.

---

### Finding 1 (A-13, owner-facing): the tail is **4.7% of the sleeve**, not "4.7% of the account" - and under the rule that sentence is describing, 4.7% of the account is impossible

`BLOCKERS.md:626` tells the owner the eleven-year worst day is **"-$46,850, or 4.7% of the account
in one session"**. The paragraph's own arithmetic refutes it. The `all` cell is run with
`nav_frac = 0.25`, which is exactly the statement *"the $1,000,000 book is the SLEEVE, and the
account behind it is $4,000,000"* - that is the only substitution under which the harness's stop
equals the live one. So:

| | value |
| --- | --- |
| worst day, eleven years | -$46,850 |
| as a fraction of the **$1M sleeve** | **-4.69%** |
| as a fraction of the **implied $4M account** | **-1.17%** |
| the live stop being described (-2.5% of NAV) | **-$100,000 of sleeve P&L** |

A day that lost 4.7% of the account would be a **-$187,400 sleeve loss**, nearly twice the stop the
same paragraph says is in force. The internal check is that the corrected cell records **0
stop-outs in 2,686 sessions**: the worst day never came within a factor of two of the limit, which
is only consistent with the sleeve reading. On the real paper account (NAV **$986,287**, logged
today, sleeve $246,572) the same worst day scales to **-$11,552, or 1.17% of the account**.

This is the same unit confusion as AUD-21 itself, surfacing one layer up in the sentence that asks
the owner to make a risk decision, and it overstates the thing being decided by **4x**. Everything
else in that paragraph - the table, the -$35/day cost of the tighter setting, the 92 sessions, the
regime-by-regime widening, the "this is a preference about the worst day" framing - is correct and
reproduced above. Corrected in place at `BLOCKERS.md` with a dated critic note; the A-13 author's
text is left standing beneath it, because deleting the wrong number would delete the evidence that
it was ever shown.

### Finding 2 (outside A-13, and larger): the intraday sleeve's 09:25 launch gate is failing **now**, because a unit test reads the machine's free memory

This is the deploy-gate half of the brief, and the answer for the intraday sleeve is **the gate does
not pass**. On the interpreter the Windows task actually runs - `Get-ScheduledTask 'Quant Intraday
Sleeve'` executes `pythoncore-3.14-64\python.exe scripts\intraday_launch.py`, no flags:

```
INTRADAY preflight FAILED: unit suite failed, not trading.    AssertionError: assert 1 == 2
     +  where 1 = resolve_workers(2, 'futures', verbose=False)
FAILED tests/test_qb_scheduler.py::test_resolve_workers_respects_a_smaller_request
1 failed, 614 passed in 60.79s
```

E-5 made `pytest` exit 1 **the one outcome that refuses the launch** (`intraday_launch.py:126`:
*"the only refusal: real assertion failures"*), and every other outcome a warning. So this stops the
sleeve from trading.

The test is not wrong about anything in the code; it is **non-deterministic by construction**.
`resolve_workers` clamps through `workers_for -> allocate -> plan_workers`, which reads *current*
commit charge and free RAM. The test asserts `resolve_workers(2, "futures") == 2`, i.e. that the
docstring's promise - *"A researcher who asks for 2 gets 2"* - holds. It does not: the
implementation is `out = max(1, min(want, allowed))`, so when the machine is loaded enough that
`allowed == 1`, a request for 2 returns 1 and the promise breaks. Demonstrated both ways within
twenty minutes, same commit, same interpreter, no code change:

| machine state | `plan_workers(600).workers` | `resolve_workers(2, "futures")` | suite / `--preflight-only` |
| --- | --- | --- | --- |
| a 12-worker sweep running | 1 | **1** | **1 failed, 614 passed -> FAILED, not trading** |
| idle | 7 (`limited_by=commit`) | 2 | **615 passed -> all gates passed** |

The idle run is the closing half of the proof: same commit, same interpreter, nothing edited -
`preflight tests OK: 615 passed in 22.59s`, then `preflight replay OK: replay 2026-09-11: P&L
-2,080 on sleeve equity 250,000, trades 36, costs 228, decisions 368, open positions at end none`,
then `preflight-only: all gates passed`. **Whether the account trades on Monday is currently decided
by how much memory another cron job happens to be holding at 09:25.**

The operational shape of this is bad in a specific way: AGENTS.md has several cron tracks running
this repository **concurrently by design**, and the 09:25 ET launch is exactly when an overnight
sweep is most likely to still be holding memory. The sleeve can therefore refuse to trade *because
research was running*, and the log line will say "unit suite failed", which points the reader at
trading code that is fine. It arrived today in `9d67bef` (eng, Parts 1/5/6), so it has not yet met
a trading morning. Filed as **C-3** for the `eng` track - the fix belongs to whoever owns
`quant_brain/` and is a one-line choice between pinning the budget in the test and dropping the
environment-dependent assertion; **the critic ships nothing**, so I have not made it.

### Finding 3 (A-13, clause 2): the pooled +$35.32 is credited to the wrong defect. On 2016-2019 it is the **fill** fix, and A-13's own materiality threshold fails on that window

A-13 clause 2 says *"fixing the loss-limit base improves the measured P&L by +$205.15/day on
2024-2026 and +$35.32/day pooled"*. The first is measured; **the second was an attribution, not a
measurement** - +$35.32 is the `all` cell (fill + atr + nav together) over eleven years, while the
only isolated `fill` cell A-13 ever ran is 2024-2026, where clause 4 shows the Alpaca store has
**no** sparse opening ranges at all, i.e. precisely the window where the fill defect is
mechanically unable to bite. So I ran the decomposition on the other end of the sample,
`--years 2016 2017 2018 2019 --cells control fill nav all`. It reproduces the control on a second
window (**-$303.34/day against A-13's -$303.4**, 1,006 sessions, **5** stop-outs, exact) and then
reverses the attribution:

| cell, 2016-2019, 1,006 sessions | $/day | vs control | A-13's claim, from 2024-2026 |
| --- | --- | --- | --- |
| control | -303.34 | - | - |
| **fill** | **-262.10** | **+41.25** | "costs the book -$1.19/day", *in the harness's favour as filed* |
| **nav** | **-310.12** | **-6.77** | "+$205.15/day ... and +$35.32/day pooled" |
| `all` (measured independently) | -269.32 | +34.03 | |
| fill + nav deltas | | +34.48 | residual **-0.45** = atr + interaction |

The decomposition closes to **$0.45/day**, so this is an identity, not an estimate. On the eleven
years' first four, **the entire correction is the fill model and nav is slightly negative** - the
opposite of clause 2 on both defects. Weighting the two measured windows, the fill fix is worth
**+$24/day over 1,680 of the 2,686 sessions**; it is not the rounding error the pooled sentence
implies, and 2020-2023 (1,006 sessions) is still unmeasured for both defects.

**This does not overturn A-13's headline - it strengthens the thesis and breaks the clause.** The
headline is "the audit's 'all in its own favour' is wrong for the biggest of them", and the honest
version is stronger: the audit's sign is wrong for the fill defect **too**, wherever the store is
sparse enough for it to act. Which is exactly what clause 4's own mechanism predicts, and that is
the second half of this finding: **clause 4's pre-registered threshold fails on this window.** The
clause reads *"the count of (symbol, session) pairs whose range-close bar still sees bar 0 is
measured directly and must be under 10% for the prediction to stand"*; on 2016-2019 it is
**2,010 of 13,719 = 14.65%**, against the 7.47% A-13 quotes for the full eleven years and the 0.00%
it quotes for 2024-2026. The 7.47% is a pooled average over a regime at 14.65% and a regime at 0%,
and the clause was evaluated against the average. The `atr` cell itself remains nearly inert even
there (-$0.45/day as the residual above), so the *conclusion* survives; the *test* did not.

**Still unsettled:** 2020-2023 for all three defects, and an isolated `atr` cell on 2016-2019.
Resume with `python scripts/sweep_a13.py --workers 12 --years 2020 2021 2022 2023 --cells control
fill nav atr all` (back up `results/a13/*.csv` first - the script overwrites them; C-2's copies are
in `results/c2_critic/`). My 2016-2019 run was stopped after 12 of its 16 jobs at 70 minutes, past
AGENTS.md's 40-minute rule and while holding 12 workers, which is itself the condition that keeps
Finding 2's gate red; the 12 cells it printed are the table above and the 4 it did not reach are the
`all` cells, which the 11-year run already provides.

### Two smaller things, neither a refutation

- **Clause 1's reconciliation does not close at the precision it is printed.** -65 (A-10) - 45
  (regulatory fees) - 20.76 (AUD-07 flatten) = **-130.76**, not the **-131.8** stated, and the
  residual against -132.53 is then **$1.77/day**, not $0.77. The claimed pair is self-consistent if
  the unrounded components were used, but the ledger stores A-10's figure as the integer `-65`, so
  it cannot be checked. The reconciliation is right to about 1% of a -$132/day number either way,
  which is all clause 1 needs; the arithmetic as displayed simply does not add up.
- **`forced_eod` is invisible at the settings A-13 ran.** `summarize` only reports
  `forced_eod_orders` when `part_cap` is non-zero, and every A-13 cell has `part_cap = 0.0`. Under
  `next_bar` an order placed on the final bar cannot fill, so positions closed at the last bar's
  close are not counted anywhere in these runs. The flatten begins at minute 368 with ~22 bars of
  runway so this is very probably zero, but "probably zero" is not what the counter is for.

**Decision: A-13's fixes and its headline stand; two of its clauses do not. Nothing restored, no
ledger row tagged not promotable, no research verdict overturned.** The harness fixes reproduce on
committed code and on a second window, the fill model is causal, the `nav_frac` translation matches
the live trader line for line, clause 4's inertness *conclusion* holds on both stores, and the
eleven-year answer for the deployed ORB book is still -$310/day at t -1.24 - not proven to lose, not
proven to earn, so nothing in `BLOCKERS.md`'s size question moves. What changes: clause 2 credits
the wrong defect (on 2016-2019 the correction is the **fill** fix, +$41.25/day, with nav at
-$6.77), clause 4's 10% threshold **fails** on that window at 14.65% while its conclusion survives,
one owner-facing percentage was 4x too large and is corrected, and one thing nobody was looking at:
the live launch gate is red whenever the machine is busy.

**Two reusable rules.** (a) *A defect measured only where its mechanism cannot act has not been
measured.* The fill fix was priced on 2024-2026, the one window A-13's own clause 4 shows has zero
sparse opening ranges; on the window with 14.65% it is worth thirty-five times more and the other
way. Price a bias where it can bite, not where the data are cleanest. (b) *A gate that runs the
whole unit suite inherits every non-determinism in it.*
E-5's design is right - the suite should stop the launch - but that makes every test a live-path
dependency, so a test is allowed to read the clock, the network or the machine's free memory only if
somebody has decided that the sleeve should not trade when those change. Nobody decided that here.

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
