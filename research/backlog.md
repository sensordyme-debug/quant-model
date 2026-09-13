# Research backlog

Ranked list of hypotheses and infrastructure work. The improvement loop takes the top open
item. Move finished items to the bottom under "Done" with a one-line result and the
experiment timestamp.

## Current objective (set 2026-09-08; **met 2026-09-09**, restated at the 2026-09-10 review)

Original: a backtest-validated strategy running on IBKR **paper** trading by **2026-09-10**.
**Done** - S-12 `s1_momo` is the champion via `scripts/evaluate.py`, `compare_orders.py` gates the
deploy, and the runner filled its first real paper orders at 15:46 ET on 2026-09-09.

Objective from here: **make the second (intraday) sleeve honest, or retire it.** It is deployed at
half size and measured negative on 2,686 sessions, so the work is (1) replace the estimated
slippage constant with measured fills (A-5 part 2, every session), (2) find a causal regime gate
for the long-volatility mechanism A-10 confirmed at t = +10.70 (O-1), judged on the Alpaca
regimes; and if that fails, say so and take the sleeve to zero rather than find a twelfth lever.
Live money stays off the table until the human signs off in `live/`.

**Review 2026-09-12 06:30 ET (`research/reports/2026-09-12.md`).** The objective above is now
answerable on its own terms. (1) *Make the intraday sleeve honest, or retire it*: the gate hunt is
finished - O-1 refused, A-11/A-12 refused, and F-6 removed the last intraday mechanism with a
permitted instrument (0 of 336, refused on **absence**). What is left is A-5 part 2, which is 1-2
sessions from settling the slippage constant; when it settles, the loop should **say the sleeve
cannot be validated and hand the owner (b)**, not look for another lever. (2) The daily sleeve's
leg-split program (hold / rank / size) closed with S-28, and S-29 closed the regime question. The
one untried construction is **S-30** below. (3) The honest deployed expectation of the daily
champion is **~20% CAR, not 24.4%** - see `champion.json`'s `deployed_expectation_note`.

Status 2026-09-12 17:0x UTC (S-33 / AUD-11, `daily` track - journal `research/journal_daily.md`):
**the champion's "OOS 2020-2026" label is wrong and its number is not, and the audit's own first
remedy would have cost 1.87 CAR points at t -2.18.** With the owner pile re-priced twice (S-31,
S-32) and both standing jobs again without new input on a Saturday (`daily_fills.py` 10 fills /
$2.37M / **+3.2 bps**, se 4.5), the highest-value act left in scope is the operator audit's own
daily items, and AUD-11 is the one that decides how every OOS-weighted claim in this repository
should be read. `scripts/sweep_s33.py`, seven clauses pre-registered, **60 DIAGNOSTIC rows** under
`daily/s33_oos`, **no shipped or runner-loaded file touched** so no deploy gate and no replay is
owed; identity exact at **22.192150% / 5,052**. The selection is re-done with 2020-2026 genuinely
withheld on the three axes whose grids are copied verbatim from the `signals.py` docstrings that
record how each shipped value was chosen. **(1) The shipped set is not even the full-period
argmax** - `mom_skip=10` beats the shipped 5 by 0.485 on the window the choice was made on and was
not taken, which is S-10's "a-priori point inside a shelf, not its argmax" rule visible in the
data rather than only in the prose. **(2) The audit's re-select remedy is REFUSED**: it moves one
axis (`alloc_vol_window` 21 -> 10), that cell is the **worst of its axis's six out of sample**,
and it costs **-1.865 CAR points, -0.569 bps/day, t -2.18** - past |t| = 2 and the first
non-arithmetic statistic this sleeve has produced that gets there. **(3) The contamination is
about half a point**: against the 18 unique cells the shipped set sits **+0.974 above the grid
mean (0.53 sd, 78th percentile)** and +0.492 above the median, under this iteration's own
pre-registered 0.5 threshold for "cosmetic". Both (2) and (3) follow from one number - the
**selection premium is -0.049 CAR points** pooled over 20 cells; the IS top three cells average
28.420 OOS against the IS bottom three at 28.283, and the single global IS-argmax lands *below*
the grid mean. Honest fully-charged (cell C) withheld half: shipped **25.967% / 1.151 / DD
24.040**, grid band ~20.0..27.7%. The relabel branch is **adopted** and the champion.json edit is
**owed, not taken** (that file is reserved to `--promote`, and AUD-10 should be fixed first); the
exact replacement sentence is filed under AUD-11 below. **What it changes for the loop**: on this
sleeve a parameter **shelf** is worth reporting and a parameter **argmax** is worth nothing, so
the convention S-9/S-10/S-12 already used is not conservatism but the only rule the data supports
- and when an audit names a defect *and* a fix, those are two claims, and here the expensive one
was the fix.

Status 2026-09-12 15:4x UTC (S-32, `daily` track - journal now `research/journal_daily.md`):
**the second open owner decision re-priced, and this one closes on its own conditional. The
no-trade band stays at 0.01.** Same rule as S-31 and for the same reason - both standing jobs ran
first and, Saturday, neither has new input (`daily_fills.py` 10 fills / $2.37M / **+3.2 bps**, se
4.5). `scripts/sweep_s32.py`, seven clauses pre-registered, 55 DIAGNOSTIC rows under
`daily/s32_band`, **no shipped or runner-loaded file touched** (`band=`/`skip=` added to the
research harness `sweep_s25.legs_simulate`, inert at their defaults, every earlier row
bit-identical) so **no deploy gate and no replay is owed**. Identity exact: **22.192150% / 5,052**
and **19.640168% / 1.047 / DD 24.037**. **The pre-registered premise HOLDS** - band 0.080 gains
+0.380 / +0.391 / +0.450 / **+0.519** at 0 / 1 / 2 / 3.2 bp - and **five bands pass the decision
cell on `champion.json`'s own criteria**, including the owner's 0.03, so this is the rare item
refused *after* its clauses passed. Three numbers do it: the **spread-attributable** part of band
0.080's +0.544 is **+0.139** and is the only column monotone across the whole grid (+0.045 /
+0.058 / +0.095 / +0.139 / +0.286) while the gain itself zig-zags (+0.090 / +0.013 / +0.313 /
+0.544 / +0.206); the **arithmetic ceiling** from turnover removed x the measured 3.2 bps is
**0.155% of equity a year**, so the CAR claim is **3.5x larger than the mechanism can produce**
and agrees with the +0.139 to 0.016 points; and the **placebo** - the same 67.5% of orders removed
at random - returns **-0.176 mean, sd 0.791**, with one seed of five beating the band outright
(permutation p 0.33) and drawdown swinging 20.26-28.10%. Paired t **+1.96** full period, +1.35 IS
/ +1.74 OOS; the owner's 0.03 is the local worst of the passing five (+0.013, **t +0.12**,
0.067%/yr). `BLOCKERS.md` item 4 gains the priced addendum and the conditional it was closed on
("widen to 0.03 if the measured spread cost is material") **resolves to "not material"**. **What
it changes for the loop**: a criteria pass is not a result - `champion.json`'s rules were designed
to compare *signals*, and against an *execution* change whose ceiling is 0.155%/yr they are
passed by path noise measuring sd 0.79. Any future execution-setting question needs its
arithmetic ceiling quoted before its CAR column.

Status 2026-09-12 13:1x UTC (S-31): **the owner's size decision - the largest of the six - was
priced on a book that does not exist. About half the advertised gain is not there, the Sharpe
argument for it reverses once the borrowing is charged, and option (c) is now answered in
advance.** Not a seventh lever: **both standing jobs ran first and neither has new input**
(Saturday - `slippage_report.py` 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90;
`daily_fills.py` 10 fills / $2.37M / +3.2 bps, `ref_price` the previous close 10 of 10), so the
highest-value remaining act is to make the binding constraint answerable on the right numbers.
New `scripts/sweep_s31.py`; **37 DIAGNOSTIC ledger rows** under `daily/s31_budget`; seven clauses
pre-registered; **no shipped or runner-loaded file touched**, so no deploy gate and no replay is
owed. **(1) Identity exact**: budget 0.75 gives **22.192150% / 5,052 orders** at zero cost and
**19.640168% / 1.047 / DD 24.037** fully charged, S-22's independent figure. **(2) The drawdown
calibration is pre-registered and passes, including a NEW LEAN RUN at the budget the answer
selects** - harness minus LEAN on the backtest convention is DD **-0.442 / -1.135 / -1.294** at
0.75 / 0.80 / **0.90** (run `20260912T130734Z`, 28.796% / 1.032 / DD 27.900%, `OrderListHash
7352a42d118919eec701e44af7a4dfff`), so the harness is optimistic and grows more so with size, and
every drawdown is quoted with that error added back. **(3) About half the gain is not there**:
against what the owner was shown, the gain over 0.75 at today's cost of money is **+0.428 /
+0.679 / +0.959 / +1.353 / +1.991 / +3.186** at 0.78 / 0.80 / 0.82 / 0.85 / 0.90 / 1.00 against
**+0.877 / +1.454 / +2.017 / +2.879 / +4.301 / +7.052** - **45-49% survives**, decaying with size
because the financed debit grows faster than the return. The CAR ordering does **not** reverse.
**(4) The risk-adjusted ordering does, and that is the headline**: Sharpe runs 1.247 -> 1.246
(flat) uncosted but **1.047 -> 1.003** costed and **1.023 -> 0.952** at today's rates. **Not a
convention artifact** - as excess return over the sample's own 1.6924% mean fed funds the uncosted
cell **rises 1.156 -> 1.176**, reproducing S-21's argument, and LEAN agrees directly (0.994 /
1.008 / **1.032** at 0.75 / 0.80 / 0.90), while the charged cells fall. Spending the buffer buys
return but no longer buys risk-adjusted return; it is a pure leverage lever. **(5) Option (c)
answered**: drawdown <= 25% -> budget **0.70**, *below* the shipped 0.75 (adjusted DD 25.2%);
<= 30% -> **0.90** at adjusted DD **26.3%**, +1.99 CAR at today's rates; <= 35% -> 0.90 as well.
**(6) The cap this file calls binding is not**: the 35% limit binds nowhere on the frontier;
**Reg-T** does, at 1.88x mark-to-market gross at 0.90 and **2.12x at 1.00**. And the reason it
stopped binding is **S-18** - S-6 measured 35.4% drawdown at budget 1.0 on the 3x book, the
unlevered book reaches ~30% there - so the only thing holding the budget at 0.75 is the
excess-liquidity buffer, which is a preference and the owner's. **(7) First statistic past 2
sigma in both halves on this sleeve** (paired vs 0.75, t +2.35..+2.40 IS and +2.00..+2.18 OOS at
every budget above 0.75) - and it is read as the significance of **arithmetic**, since a budget
change is a scaled version of the same book. **Nothing promoted, nothing shipped, no default
changed**: `margin_budget` stays 0.75, `live/*` and all three scheduled tasks untouched,
`champion.json` gains a `budget_note` and `BLOCKERS.md` the four-cell table. **What it changes for
the loop**: a cost correction measured on the champion does **not** transfer to a decision about
the champion's **size** - the three costs are independent of each other (S-22) but none is
independent of leverage.

Status 2026-09-12 11:5x UTC (I-2): **the end-of-session assertion pass ships, and it is validated
by the only test that matters for an alert - it FAILs the one day that had real defects and stays
quiet on the three that did not.** `scripts/session_audit.py`, 21 assertions over both live logs,
one verdict, exit code 0/1/2. Log-only, **no shipped or scheduled file touched**, so no gate and
no replay is owed. 2026-09-11 **FAIL** on exactly `daily.no_foreign_positions` (the S-18 TQQQ
orphan) and `intraday.pnl_reset` (`trades 32 > 0 fills logged by then`, 32 = 2026-09-10's fill
count); 2026-09-09 and 2026-09-10 WARN with no failure; 2026-09-08 PASS as pre-deployment. Four
false positives were removed by reading the runners rather than loosening thresholds, the most
useful being that **`effective_exposure` is not a limit** (1.77x on 2026-09-09 under the 3x
proxies) - the one shipped ceiling is `margin_used <= 0.75`, which held on every live plan. **One
new finding, not a defect**: the intraday book's mark-to-market gross peaked at **1.034x
`GROSS_HARD_CAP`** on 2026-09-10 because the cap is applied to decision-time targets while
`MIN_CHANGE` leaves 2% of drift per name (implied drift at that peak 0.0025), the backtest harness
caps identically so it is already priced, and total notional was ~2.09x of NAV against 4x DT
buying power - reported as a WARN, trader unchanged. **Standing jobs both ran first with no new
input** (Saturday): `slippage_report.py` 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90;
`daily_fills.py` 10 fills / $2.37M / +3.2 bps (se 4.5), `ref_price` the previous close 10 of 10.
**What it changes for the loop**: a verdict now exists but has no schedule and no delivery, and
both are barred to the loop - filed in `BLOCKERS.md` beside item 2.

Status 2026-09-12 09:4x UTC (S-29): **the market's volatility forecast is a quarter better than
the book's own and makes a measurably worse crisis switch - the sessions VIX removes are worth
twice the average session, and with the exposure held fixed the swap costs 2.6 bps a day at
t -3.06.** Volatility enters this book twice: S-28 priced the vol target (SIZE, binds on 2.8% of
sessions) and left the other one untouched - `risk_on`, the crisis switch, which decides
DIRECTION and has held the book in cash on 590 of 3,689 sessions since S-1 on a **trailing
20-session realized** estimate. S-29 swaps its input for the forward-looking one the market
quotes. New `scripts/sweep_s29.py` and `scripts/regime_data.py`; **30 DIAGNOSTIC ledger rows**
under `daily/s29_regime`; six clauses pre-registered and **no post-hoc column**; a third
default-inert hook in the shipped `signals.py` (`S1_REGIME_SERIES` / `set_regime_series`, F-3's
pattern) supplying the level the switch compares to its own median - the gate is scale-free, so
**no constant is re-tuned**. **Both deploy gates re-run after the edit**: `compare_orders.py`
3,689/3,689 at 5,021 orders, and a full LEAN control reproducing `OrderListHash
a6d6224ce9c70091e5bfa8e96f046bf3` (5,128 orders / 24.403% / 0.994 / 23.700%, run
`20260912T093609Z`). **(1) Two identities to the digit**: the shipped level through the hook
reproduces the deployed cell at **22.192150% / 5,052 orders**, and a standalone gate series
reproduces the book's own risk-off days **3,689/3,689**. **(2) The premise is not empty, it is
emphatic**: against the realized volatility of the next 21 sessions, log-log correlation
**0.4985 shipped, 0.6361 VIX, 0.5326 stale VIX, 0.6857 SPY 1-month ATM implied** on identical
samples. **(3) And the better forecast is the worse switch.** On an **ungated** version of this
book (the only non-circular reference), every session earns +10.01 bps; the sessions the
realized gate removes earn **+8.72**; the sessions **VIX removes earn +20.07**; and the **60
sessions VIX removes that realized does not earn +36.56 at t +2.01**, the only |t| > 2 in the
diagnostic - VIX sells the rebounds. **(4) Every book refused** at 2 bp + IBKR Pro financing:
primary **15.901% / 0.842 / DD 37.758** against the deployed **19.640 / 1.047 / 24.037**,
failing every criterion in the full period and **both** halves and breaching the 35% absolute
limit; the **pre-registered off-matched column** (threshold 1.2688 solved on the IS half alone
so the off-rate matches, which removes the exposure explanation) is the **worst** book at
**12.188% / 0.729 / 31.540, paired -2.612 bps/day at t -3.06** - the loss is in the TIMING.
**(5) The placebo triggers**: VIX made **stale by 5 sessions**, deliberately destroying a third
of its forecast advantage, makes the book **better** (16.666 full, 15.911 IS against 15.901 and
13.251) - nothing is paying for forecast quality. **(6) No threshold rescues it**: across
1.25/1.40/1.50/1.60/1.75/2.00 the VIX gate is worse than the realized gate at **every one** and
draws down 33-41% at every one, while the shipped 1.50 is confirmed a **shelf** (Sharpe maximum
of the realized row at 1.047). **(7) Not a VIX artifact**: the independent SPY ATM implied series
agrees in sign on 2018-2026 (15.926 / 0.791 / DD 35.193 against 21.219 / 1.036 / 24.040).
**(8) One number nobody asked for**: removing the switch entirely is worth **+2.68 CAR for +12.9
points of drawdown** (22.317 / DD 36.892) - **refused on the spot**, not filed as an owner
option, because 36.9% is past the 35% absolute limit. **Nothing shipped, nothing promoted, no
default changed**: `S1_REGIME_SERIES` unset everywhere, champion unchanged at S-18, `live/*` and
all three scheduled tasks untouched, `champion.json` gains a `regime_note` only. **Standing jobs
both ran first with no new input** (Saturday): `slippage_report.py` 66 fills / +2.22 bps / se
0.80 / |diff|/se 0.90; `daily_fills.py` 10 fills / $2.37M / **+3.2 bps (se 4.5)**, `ref_price`
the previous close 10 of 10. **What it changes for the loop**: the reusable rule is that **a risk
switch is not a forecasting problem** - this is the first refusal here where the input was
*improved* on its own terms and the book got worse with exposure held fixed, and the reason is
in the shipped docstring already (vol peaks coincide with the sharpest rebounds, so a realized
switch is valuable *because it is late* - a trailing stop denominated in volatility). Second, and
procedural: **the clause-2 diagnostic passed and the book still failed**, so a diagnostic pass is
a licence to read the book, never a substitute for it.

Status 2026-09-12 08:0x UTC (S-28): **the risk model is the one place the leg split changes the
book - the same return for 2.1 points less drawdown, refused by a return-first rule, and handed
to the owner as the cheapest of the three priced options.** S-25 found the alpha is an overnight
object; S-26 asked what to hold and S-27 what to rank on, both refused. S-28 asks the third and
last question, the one the sizing machinery poses: `target_vol / sigma` measures `sigma`
**close to close**, on a quantity 61% of whose variance is the leg the book is not paid for.
New `scripts/sweep_s28.py`; **18 DIAGNOSTIC ledger rows** under `daily/s28_volest`; six clauses
pre-registered plus one column labelled post hoc; a new **default-inert hook in the shipped
`signals.py`** (`S1_VOL_RETURNS` / `set_vol_returns`, F-3's `S1_ML_SCORES` pattern) that supplies
the vol target's return window and touches nothing else, with the **I-1 gate re-run after the
edit (3,689/3,689 dates, 5,021 orders both sides, PASS)**. **(1) Identity to the digit**:
`(1+on)(1+id)=(1+cc)` holds to **2.220e-16** and the close-to-close frame *through the hook*
reproduces the deployed cell at **22.192150% / 5,052 orders / $1,880,257.37**. **(2) The premise
is not empty**: pooled over the nine names on 59,662 observations, **every leg forecasts its own
next-21-session vol better than the pooled estimate does** - cc->cc 0.7260, **on->on 0.6764
against cc->on 0.6608**, id->id 0.7492 - while the two estimators sit 0.9029 correlated in log
level with `sigma_on/sigma_cc` = 0.5888, which is clause 6's written-down expectation.
**(3) All four books refused** at 2 bp + IBKR Pro financing: the **raw** legs are leverage and
nothing else (scale at its cap on **86.3%** of sessions, `on` 20.333% for **DD 32.031**, `id`
20.084 for 30.196 - they delete the crisis de-risking S-16 and O-1b already priced); the
**level-matched primary** `on_k` reads **19.400 / Sharpe 1.049 / DD 21.622** against the deployed
**19.640 / 1.047 / 24.037**, refused on CAR, paired **-0.100 bps/day at t -0.92**. **(4) The
placebo separates cleanly**: the identical construction on the leg the book is *not* paid in
moves it the **opposite way** (`id_k` +0.16 CAR for +1.43 DD against `on_k` -0.24 CAR for -2.42
DD), same machinery, same turnover to 4% - so this is the leg that pays, not any perturbation of
the estimator. **(5) The shortfall is a residual level effect, and the post-hoc column removes
it**: the causal match equalizes the average *name's* vol, not the portfolio's (mean estimate
0.2584 against 0.2380), so re-levered to the shipped book's own 0.1883 the primary earns
**19.613% / 1.046 / DD 21.931 - a dead heat in return (paired -0.009 bps/day, t -0.08) for 2.1
points less drawdown**, still **refused by 0.027 CAR points**, **passing OOS on every criterion
(26.007 vs 25.967, DD 20.67 vs 24.04) and failing IS (14.254 vs 14.317)**. **(6) Two episodes,
pointing opposite ways, and it is stated rather than hidden**: the vol target sizes the book on
**2.8%** of sessions (4.7% under `on_k`), nothing reaches |t| = 2, and the difference is 3.8
points off the 2022 drawdown against 0.7 points added to the 2015-16 one. **Nothing shipped,
nothing promoted, no default changed**: `S1_VOL_RETURNS` unset in every deployed path, champion
unchanged at S-18, `live/*` and all three scheduled tasks untouched, `champion.json` gains a
`risk_note` only. **Standing jobs both ran first with no new input** (Saturday):
`slippage_report.py` 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90; `daily_fills.py` 10 fills /
$2.37M / **+3.2 bps (se 4.5)**, `ref_price` the previous close 10 of 10. **What it changes for
the loop**: the reusable rule is that **a leg attribution is a statement about the risk model
before it is a statement about the signal** - S-27 showed the split does not tell you what to
rank on, S-28 shows it does change what to size on, by little in return and measurably in
drawdown. It closes the leg-split program and leaves the owner a third priced option, the
cheapest on file: no futures permission, no Reg-T decision, only a change of default.

Status 2026-09-12 07:0x UTC (F-6): **the overnight gap does not reverse during the session on the
56 names this sleeve may trade - the effect is ABSENT, not unaffordable, and S-27's by-product
does not transport.** S-27 filed one number post hoc and explicitly did not pursue it: on the
daily champion's nine ETFs an overnight-momentum score forecasts the next *intraday* leg at
**-2.230 bps/day, t -3.30**, sign-stable in both halves, parked because those nine names are
barred to the intraday sleeve by AGENTS.md's disjointness rule and because a tradable version
needs its own pre-registration and an instrument. F-6 supplies all three: the same shape at its
shortest horizon (the single overnight gap `open[d]/close[d-1]-1` fading during session `d`), on
the **56 permitted names**, on `data/minute_alpaca`. New `scripts/sweep_f6.py` on X-1's
primitives unchanged (`_panel_job`, `_cost_bps`, `_cluster_t`), so X-1, F-4 and F-6 span identical
calendars leg for leg; **2,647 sessions, 2016-01-05..2026-09-09, 14,510,968 legs**; nine clauses
pre-registered, one of them (9) labelled as a post-hoc extension and counted as one.
**(1) 0 of 336 net** (3 lookbacks x 7 entry minutes x 2 exits x 2 books x 2 selections, both
signs) and **0 of 168** on the second screen - *effect present but unaffordable?* - with **0 of
504 regime-cells** reaching t < -2 in the fade direction. **(2) Clause (6)'s written-down sign is
REFUTED, and that is the finding**: **156 of 168 pooled gross columns are POSITIVE** (the gap
extends, it does not fade) and **the largest |t| anywhere is 2.08**, 1.86 on the tradable
`flatten` exit. The pre-registered primary (dollar-neutral, all names, lookback 1) reads +0.10 /
+1.04 / **+1.29** / +1.02 / +0.06 bps at t +0.10 / +1.34 / **+1.86** / +1.83 / +0.16 entering
09:31 / 10:01 / 10:31 / 11:31 / 13:31, hit rate 49.5-50.1%, breadth -0.027. **(3) So this is NOT a
cost refusal, which separates it from most of the file**: L-1, X-1, F-1 and F-3 found something
and could not afford it; F-6 finds nothing to afford. Strongest pooled *fade* anywhere **-0.32 bps
at t -0.43**, a breakeven of **0.32 bps** against this store's **4.59** - **even F-2a's 0.488 ES
contract would not clear it**, and one future cannot carry a 56-name cross-section, so F-4's rule
applies a third time: a cheap instrument cannot buy a gross column that is the wrong sign and
insignificant. **(4) The post-hoc extension, run because the lookback-1 table does not close the
question S-27 posed** (its object is a 20/60/120/252-day blend, not one gap): the same grid at the
**compounded overnight return of the last 5 and 20 sessions**, with L=1 reproducing the first
table bit-for-bit as the identity check. 56 cells become 168, so ~15 chance passes would be
expected at t > 2 and the actual count is **zero**; pooled neutral/all best cells are **+0.94
(t +1.39)** at L=5 and **+0.36 (t +0.50)** at L=20. **S-27's by-product does not transport.**
**(5) The raw book fails F-5's control**: reversal-minus-always-long is negative at all 42 pooled
cells (best t -2.03) while the always-long drift over the same windows is +0.6 to +3.1 bps - a
small long-the-market bet with no forecasting content, exactly F-5's diagnosis on the indices.
**(6) Two contaminants stated in advance rather than assumed away**, both of which would have
*inflated* a fade: the store is split-adjusted but **dividend-raw** (ex-dates print spurious down
gaps on ~1% of name-days) and earnings gaps cannot be excluded historically (FMP basic serves only
a window around today), which is why `all` and `q20` were reported side by side. **Nothing
shipped, nothing promoted, no default changed**: champion unchanged at S-18, `champion.json`,
`live/*` and all three scheduled tasks untouched, `late_momo` still at alloc 0.0, one new script
only so rule (a) owes no replay and the I-1 gate is unaffected. **No ledger rows**, on F-4's and
F-5's precedent. **Standing jobs both ran first with no new input** (Saturday):
`slippage_report.py` 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90; `daily_fills.py` 10 fills /
$2.37M / **+3.2 bps (se 4.5)**, `ref_price` the previous close 10 of 10. **What it changes for the
loop**: the reusable rule is that **a post-hoc result measured on nine correlated ETFs is a
hypothesis about that universe, not about the mechanism** - a by-product filed from the daily
sleeve owes a transport test before it is treated as a lead for the intraday sleeve, and F-6 is
the cheapest form of that test. It also removes the last intraday item with a stated mechanism and
a permitted instrument, so the current objective's own instruction now applies: say so rather than
find a twelfth lever.

Status 2026-09-12 06:0x UTC (S-27): **the leg that pays is not forecast by its own history - the
champion's close-to-close score beats overnight momentum at predicting the overnight leg, so
S-25's split is an attribution and not a signal recipe.** S-25 and S-26 both asked what this
sleeve should *hold*; neither asked what it should *rank on*, and the shipped blend scores nine
ETFs on a quantity 94% composed of a leg the book is not paid for. New `scripts/sweep_s27.py`;
**12 ledger rows** under `daily/s27_rank`, all DIAGNOSTIC; **six clauses pre-registered**,
including (5), which wrote the expected outcome down first, and (4), a placebo that could have
withdrawn the primary even on a pass. Three synthetic indices per ticker - `cc`, `on`
(close[d-1]->open[d] compounded) and `id` - with leg identity `(1+on)(1+id)=(1+cc)` holding to
**2.22e-16**, and the champion's own blend on each handed to the shipped algorithm through
**F-3's `S1_ML_SCORES` hook in `ML_MODE="rank"`**, so **no runner-loaded file was modified**.
**(1) Identity passes to the digit and earned its place**: `cc` through the hook reproduces
**22.192150% / 5,052 orders / $1,880,257.37**, and the first attempt did not (20.676% / 5,260)
because a naive `pct_change` blend silently omits **S-10's 5-session skip on horizons >= 120** -
an end-to-end identity clause catches a vectorized reimplementation of a shipped signal, reading
the two formulas does not. **(2) The diagnostic is the finding and it inverts the hypothesis**:
rank IC against the next session's legs is **cc -> overnight +0.0574 (t +7.25)** and **on ->
overnight +0.0574 (t +7.32)** - *the same ordering to four decimals* - but the quantity the book
collects, the **top-3-minus-equal-weight spread**, is **+2.106 bps/day (t +3.24) for the shipped
score against +1.311 (t +2.04)** for the overnight one, in both halves (IS 2.176 vs 0.947, OOS
2.021 vs 1.740). Nothing forecasts the intraday leg (best cell cc +0.0141 at t +1.81, spread
**negative** at -0.727). **(3) The primary screen is refused on every criterion and is not close**:
charged 2 bp and IBKR Pro financing, overnight-ranked earns **11.751% / 0.656 / DD 35.210**
against the deployed **19.640% / 1.047 / 24.037**, paired **-2.619 bps/day at t -2.41**, worse in
both halves (7.693 vs 14.317 IS, 16.582 vs 25.967 OOS), and it breaches the absolute 35% drawdown
limit outright. **(4) The placebo is refused too** (intraday-ranked 13.167% / 0.778 / 27.591,
paired -2.270 at t -2.08), so this is not a case of any perturbation of the blend helping.
**(5) The refusal is about selection, not exposure**: mean gross **1.24x against 1.25x**, and
against the same-gross always-invested control the overnight excess is **+3.087 (t +4.20) cc,
+1.686 (t +1.86) on, +1.183 (t +1.51) id** - matched exposure, same nine names, same gate, and the
shipped ranking is **1.8x** the overnight one at forecasting the only leg this sleeve is paid in,
on *lower* turnover (131x equity/yr against 240x). **(6) Clause 5 held for the reason written
down**: only +3.087 of the +8.662 bps/day is selection, the rest is beta the control collects too,
and an overnight-only index compounds ~a third of the variance into a 252-day window - a noisier
estimate of the same trend, which is exactly "same IC, smaller spread". **(7) One by-product,
labelled post hoc and sign-stable**: the overnight score forecasts the next **intraday** leg
**negatively**, top-3-minus-EW **-2.230 bps/day at t -3.30** (IS -2.182 t -3.03, OOS -2.290
t -1.89) - recorded and not pursued, because the nine names are the daily champion's (AGENTS.md
disjointness), the gross sits under any realistic round trip, and a tradable version needs its own
pre-registration and an instrument. **Nothing shipped, nothing promoted, no default changed**:
`S1_ML_SCORES` unset in every deployed path, champion unchanged at S-18, `live/*` and all three
scheduled tasks untouched, one new script only so rule (a) owes no replay and the I-1 gate is
unaffected; `champion.json` gains a `rank_note` only. **Standing jobs both ran first with no new
input** (Saturday): `slippage_report.py` 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90;
`daily_fills.py` 10 fills / $2.37M / **+3.2 bps (se 4.5)**, `ref_price` the previous close 10 of
10. **What it changes for the loop**: the reusable rule is that **knowing which leg a book is paid
in does not tell you which leg to build the signal from** - the forecast horizon and the payment
window are different objects, so a leg attribution may not be read as a feature-selection
instruction without its own IC table. It closes the direction S-25 left open by the only route
that needed nothing new; what is left of that direction needs a different universe and a cost
model that survives it, not another score on these nine names.

Status 2026-09-12 05:0x UTC (S-26): **the one direction S-25 left open is now priced, and the book
that takes it is the first candidate in this repository whose edge survives its own execution and
dies on its risk.** S-25 named exactly one successor - target the overnight leg without paying for
a daily equity round trip - and the only instrument that can do that is a futures overlay on the
*other* leg, which is only worth asking because F-2a measured an ES round trip at 0.488 bps.
New `scripts/sweep_s26.py` plus **two default-inert arguments on `sweep_s25.legs_simulate`**
(`hedge=`, `scale=`, S-22's precedent); **10 ledger rows** under `daily/s26_hedge`, all DIAGNOSTIC;
seven clauses pre-registered, three of which could have invalidated the run. **(1) Identity passes
to the digit**: `hedge=None, scale=1.0` reproduces S-25's deployed cell at CAR 22.192150% / 5,052
orders / residual 5.33e-16, and the costed cell lands on S-22's **19.640%** a third time.
**(2) The proxy is validated, not assumed, and it is the tightest fit on file**: over F-2a's 313
ES sessions **corr(ES cash session, SPY open->close) = 0.9994, slope 0.9984, basis sd 2.1
bps/session**, so this overlay needs **no CME purchase at all**. **(3) Said before pricing
anything**: the intraday leg has no alpha but it does have a return - SPY's own intraday leg is
**+2.432 bps/day at t +1.86** (overnight +3.666 at t +3.33) - so the trade is one drift that has
never reached |t| = 2 against a certain variance reduction. **(4) The grid** (2 bp equity spread +
IBKR Pro financing + 0.488 bps futures round trip, trailing beta 1.12): unhedged **19.640% / 1.047
/ DD 24.04 / std 0.188**, then 18.972 / 18.174 / 17.263 / **16.224** at h = 0.25 / 0.50 / 0.75 /
1.00, with **Sharpe peaking at a HALF hedge (1.124)** and drawdown falling monotonically to 20.77 -
every basis point sold buys risk back. **(5) The primary screen is REFUSED, and on RISK rather than
on cost, sign or significance - a refusal mode this repository has not produced before.**
Vol-matched to the unhedged 0.1883 on the real machinery, **h=0.50 earns 20.837% / Sharpe 1.100
(+1.197 CAR points), beats the bar in both halves (+0.72 IS, +1.66 OOS) and stays inside Reg-T at
1.83x max gross - and is refused because its drawdown is 26.02 against 24.04, 1.99 points worse
against the champion's 1.0-point tolerance**; h=1.00 is refused on CAR full period and in both
halves. Paired **+0.395 at t +0.60**, so nothing reaches |t| = 2. Clause 5's written-down
expectation ("refused, and narrowly") held, but it expected the refusal from the drift being sold
and got it from the **leverage used to buy the risk saving back**. **(6) The placebo passes and is
the durable positive**: the identical overlay on the **overnight** leg costs **-4.310 bps/day at
t -4.14** (7.598% / DD 28.60) against the intraday overlay's -1.373 at t -1.02 - a factor of 3.1
and the only |t| > 2 in the file - so **S-25's split is confirmed by a second, independent route**
(a hedge rather than an attribution). **(7) The breakeven, the durable number**: at zero hedge cost
h=0.50 earns 21.821% on 0.65x of live equity a session -> **breakeven +1.108 bps a round trip**,
h=1.00 +0.316, against **ES 0.488** (full tick 0.856, MES 0.744) - **the half hedge clears the
cheapest instrument on file by 2.3x**. Granularity: the h=1.00 hedge is below one ES contract on
**65.4%** of sessions (below one MES on 8.2%). **One correction to a prior number, found by this
iteration**: a breakeven divides a growth-normalized edge, so its turnover divisor must be
growth-normalized too; S-25's (and this repo's `turn x/yr` column's) start-equity basis reads
1,447x/yr and +0.073 bps where the correct figures are 335x/yr and +0.316, a **4.3x compression**.
**S-25's conclusion is unaffected** (its variants lost at zero cost, so the sign holds on any
divisor) but its printed breakeven magnitudes should be read as signs, not sizes. **Nothing
shipped, nothing promoted, no default changed**: champion unchanged at S-18, `champion.json` gains
a `hedge_note` only, `live/*` and all three scheduled tasks untouched, no runner-loaded file
modified so rule (a) owes no replay. **Standing jobs both ran first with no new input**:
`slippage_report.py` 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90; `daily_fills.py` 10 fills /
$2.37M / **+3.2 bps (se 4.5)**, `ref_price` the previous close 10 of 10. **What it changes for the
loop**: the reusable rule is that **matching daily volatility is not matching drawdown, so a
vol-matched relever owes its own drawdown column** - the risk twin of S-15/S-20's vol-matched
control, which was written to catch a size decision dressed as return and says nothing about the
path. And what is left of the overlay is not a research item but an owner one: the *un-relevered*
h=0.50 book trades **1.47 CAR points for 1.58 points of drawdown and +0.08 of Sharpe**, a
risk-posture change, and it is written into `BLOCKERS.md` as a priced option rather than a
recommendation.

Status 2026-09-12 03:0x UTC (S-25): **the daily champion is paid while the market is shut - 94% of
its return and all of its measurable alpha is the overnight leg - and that re-prices both ops
routes the owner is holding.** With the intraday tracks closed by F-4/F-5 and the daily instrument
audit closed by S-22, this iteration measured the one thing about the deployed book nobody had ever
separated: a book that holds nine ETFs around the clock is paid twice a day, and every figure in
this repository is a close-to-close number. New `scripts/sweep_s25.py`, built on S-19's validated
share-level harness (corr 0.99650 against LEAN's own equity curve); 3,689 sessions 2012-2026;
**6 ledger rows** under `daily/s25_legs`, all tagged DIAGNOSTIC; five clauses pre-registered.
**(1) Identity passes to the digit**: the attributing book reproduces `sweep_s19`'s deployed cell
at 22.192150% / 5,052 orders, the leg residual is 5.33e-16 of equity on every session, and the
costed cell lands on S-22's independently-derived **19.640%**. **(2) The split**: +8.662 bps/day
total = **+8.103 overnight (t +6.80, 94%)** and **+0.738 intraday (t +0.47, 9%)**, with annualized
leg vol 0.115 / 0.151 against 0.188 total - **the leg paying 94% of the return carries 61% of the
risk**. **(3) The control is the finding**: against an always-invested book scaled daily to the
champion's own 1.25x gross, the selection difference is **+3.087 bps/day at t +4.20 overnight**
(SPY control +3.081, t +3.79) and **-0.314 at t -0.37 intraday**, with both halves agreeing
(+2.993 t +3.62 IS, +3.200 t +2.51 OOS). **Fourteen years find no intraday content in this
ranking at all.** **(4) Two artifacts ruled out**: the ex-date credit is +0.683 bps/day for the
book against +0.826 for the control, so price-only the excess is *larger* (+3.231, t +4.36); and
on S-24's official opening crosses the overnight leg reads +8.864 against the store's +8.887
(2,683 sessions), so it is not Yahoo's print convention. **(5) The strategy screen is refused and
the breakeven is negative**: overnight-only earns 13.113% at 0 bp (Sharpe 1.133 at 0.115 vol) and
**-0.555% at 2 bp**, intraday-only -3.032% and -18.269%, against the deployed 20.853% / 19.640%,
paired -7.785 (t -4.97) and -15.395 (t -12.19), failing in both halves - they lose **at zero cost**
(breakeven -0.751 and -9.988 bps one-way), so this is S-15/S-20's lesson again: a smaller book, not
a better one. **(6) Post hoc, labelled: the pre-open MOO move's entire payoff is intraday**
(+0.604 bps/day at t +1.43; overnight -0.006), which is structurally forced - both conventions hold
identical targets overnight - so **the owner's recommended move buys the leg where this strategy
has never shown an edge**, at a statistic that has never reached |t| = 2. The recommendation stands
(the defect is certain, the payoff is not) but the framing is sharper. **(7) The other route is
dead**: the in-place fix, priced as an upper bound (decide on close[D], fill at close[D]), earns
**22.374% against 22.192% - +0.18 CAR points** - because it buys the same intraday leg (+0.616) and
**gives it back overnight (-0.572, t -1.79)**. Feeding today's close into the signal makes the
overnight leg worse, which is S-9/S-10's skip lever rediscovered from the opposite side, and it
means **the paid real-time data subscription can no longer be justified by that fix**. **Nothing
shipped, nothing promoted, no default changed**: champion unchanged at S-18, `live/*` and all three
scheduled tasks untouched, one new script only so rule (a) owes no replay; `champion.json` gains a
`leg_note` and nothing else. **Standing jobs both ran first**: `daily_fills.py` 10 fills / $2.37M /
**+3.2 bps (se 4.5)**, `ref_price` the previous close 10 of 10 (2026-09-11's closes have published,
so F-4/F-5's +1.7 is confirmed as the benchmark-availability artifact); `slippage_report.py`
unchanged at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90. **What it changes for the loop**:
the reusable rule is the daily twin of F-5's always-long control - **a daily-sleeve return
statement must say which leg it lives in and be quoted against an always-invested control at the
same gross in that leg** - and any future candidate that spends turnover on what the book holds
*between* the open and the close is spending it where the evidence is zero.

Status 2026-09-12 02:0x UTC (F-5): **F-4's momentum column is about a third drift and the rest does
not reach significance, and the published market-intraday-momentum effect is not in this store at
all.** F-4 refused the afternoon reversal on sign and left one piece of arithmetic unfollowed: it
wrote the rule *a cost refusal is an argument for a cheaper instrument only when the gross column
has the right sign at |t| > 2* and then applied it **only to the sign its own table says is
wrong**. Charged F-2a's 0.488 bps ES round trip, F-4's raw 11:30 momentum cell reads **+2.24 -
0.49 = +1.75 bps** instead of -2.35. F-5 put that arithmetic to the instrument that would carry
it - the **index itself**, since a 56-name basket is not something a future holds. New
`scripts/sweep_f5.py`; store `data/minute_alpaca`, **SPY / QQQ / IWM**, **2,687 sessions /
367,872 legs, 2016-01-04..2026-09-10** - the three index ETFs no event study in this repository
had ever touched, because the disjointness rule excludes them from the sleeve. **Stated before the
first number and unchanged by the result: nothing measured here may ever be deployed on the
intraday equity sleeve**; the only instrument is the index future, so a survivor would have been
evidence for the CME purchase, not a strategy. Seven clauses pre-registered, two of which carry
the entry. **(1) A clean refusal: 0 of 144 cells** (3 indices x 2 signals x 2 exits x 12 entry
minutes) reach the pass mark of net positive at t > 2 in two of three regimes. **(2) Clause (5) -
the always-long control F-4 did not run - is the finding, and clause (6) predicted it.**
Session-clustered over the `todate`/`flatten` family the gross is **+1.55 bps at t +2.42**, F-4's
sign reproduced on the index; the **always-long book over the identical windows earns +0.54**; and
the difference that is the actual forecast is **+1.01 bps at t +0.89**, by regime **-0.78 / +1.83
/ +2.47 at t -0.51 / +0.81 / +1.22** - negative in the first third and never significant. Cell by
cell **5 of 138 beat the control at t > 2** against ~3.2 expected by chance, and all five sit at
the **same entry minute**. The signal is long on **52.6%** of sessions. **(3) So F-4 is identified
rather than contradicted**: the index reproduces its column at the same minutes and size (11:30
gross **+1.99 / +3.64 / +1.57** on SPY/QQQ/IWM against F-4's 56-name +2.24), which says the raw
book was a market-factor bet - and is why it was positive at 12 of 12 entry minutes. **(4) The
published effect is the weakest family in the file**: first-30-minute signal into a later window,
**13 of 33 cells positive net**, and the exact classic cell (enter 15:30, hold to the flatten) is
**gross -0.19 / +0.10 / +0.05 bps, |t| <= 0.73** - zero before any cost - with a best-t book at
**CAR 0.90% / Sharpe 0.25**. **(5) The nearest miss, post hoc and failing both clauses**: QQQ
`todate` 15:00 -> flatten, gross +2.52 (t +3.30), net **+2.03 (t +2.66)**, but **one** of three
regimes (+0.04 / +3.94 / +2.12 at t 0.04 / 2.56 / 1.78) and only +1.75 (t +1.54) over always-long;
as a 1x book **CAR 4.99% / Sharpe 0.82 / DD 8.4% / worst day -359 bps**, i.e. ~**10x** on the
future to reach the 3%/day mandate, where the worst session is -36%. **(6) One by-product**:
entering at **15:30** in the day's direction is gross **-0.05 / +0.10 / +0.07** and net -0.53
(t -2.09) / -0.39 / -0.41 - the last half hour is where X-1's reversal sign lives and it is a
**pure cost refusal**, with no gross to buy in either direction. **Nothing shipped, nothing
promoted, no default changed**: champion unchanged at S-18, `champion.json`, `live/*` and all
three scheduled tasks untouched, one new script only so rule (a) owes no replay. **No ledger
rows**, on F-4's precedent. **Standing jobs both ran first with no new input**: A-5 part 2 at 66
fills / +2.22 bps / se 0.80 / |diff|/se 0.90; `daily_fills.py` 10 fills / $2.37M / +1.7 bps
(se 5.3), `ref_price` the previous close **10 of 10**, still the benchmark-availability artifact
(2026-09-11's closes unpublished, today's four fills NaN). **What it changes for the loop**: the
reusable rule is that **a directional intraday book must be quoted against an always-long control
on the identical windows before its gross column may be called momentum** - the time-series twin
of the vol-matched control S-15/S-16/S-20 made compulsory on the daily sleeve. Applied backwards
it closes F-4's loose end: the arithmetic that opened F-5 is refused, so the CME purchase case
keeps the cost table and the 0.62% gross sd per contract and **loses this third leg too**.

Status 2026-09-12 01:0x UTC (F-4): **the afternoon reversal is refused, and it is refused on SIGN
rather than on cost - on 6,654,000 legs over 2,664 sessions the day's move extends, it does not
fade, and the only gross statistics past |t| = 2 anywhere in the grid are momentum.** F-2a opened
F-4 as the last item with a stated mechanism, on the strength of two by-products pointing the same
way: X-1's **-0.69 bps at t -2.80** into 14:30 on 2,684 sessions of equities and F-2a's **-2.415 at
t -2.56** into the close on 313 sessions of ES. New `scripts/sweep_f4.py`; store `data/minute_alpaca`,
universe the **56 names the intraday sleeve may trade** (50 megacaps + PLTR/MSTR/COIN/SMCI/SOXL/SOXS,
disjoint from the daily champion), 2016-01-04..2026-09-09; **seven clauses pre-registered in the
docstring before the first number**, including clause (5) which wrote the expected outcome down
first - *failure on cost, not on sign* - and clause (6) which put A-10's prior refusal of the
deployed form (**-$468/day at t -7.38**) on the record rather than leaving it to be rediscovered.
**(1) A clean refusal: 0 of 96 cells** (12 entry minutes x 2 books x 2 exits x 2 signs), with
**all 96 net columns negative** - best raw momentum at 11:30, **-2.35 bps at t -2.74** against a
pooled **4.59 bps** round trip (4.90 in 2016-2019 falling to 4.26 by 2024-2026, because per-share
commission shrinks in bps as prices rise). **(2) Clause (5) is itself refused, and that is the
finding.** The gross column is **positive at 12 of 12 entry minutes in the directional book and 10
of 12 in the dollar-neutral one**; every gross statistic reaching |t| > 2 is **momentum** - neutral
11:30 **+1.78 at t +3.54**, raw 11:30 +2.24 at +2.61, raw 15:00 +0.89 at +2.48, neutral 10:00 +1.56
at +2.39 - and the largest single-regime cell in the file is **2020-2023 at 15:00, +2.18 at t +3.38
(neutral +1.20 at +3.63): A-10's exact entry minute with the opposite sign.** The second screen -
effect present but unaffordable? - returns **0 of 48**. **(3) Where the sign survives it is a
whisper and only in the labelled diagnostic book**: neutral afternoons, 2024-2026 **-0.81 / -0.59 /
-0.42 bps** at 14:00 / 14:30 / 15:00 (**t -1.11 / -0.98 / -0.85**), 2016-2019 -0.22 / -0.16, against
2020-2023 at +0.87 / +0.24 - two of three regimes carrying the sign at a fifth to an eighth of cost
and never past |t| = 1.2. **This does not contradict X-1, it fails to reach it**: X-1 ranked a
15/30/60-minute lookback held 30-60 minutes, F-4's signal is the whole session's return held to the
flatten, so they are different objects and the session-long one is not there. **(4) The
counterfactual that corrects F-2a's own closing sentence**: hold the measured gross fixed, swap the
cost column for **F-2a's 0.488 bps ES round trip**, and the same legs give **0 of 24** with **every
cell still negative** (-0.37 neutral 14:30 to -2.73 raw 11:30). **A cost refusal is an argument for
a cheaper instrument only when the gross column has the right sign at |t| > 2; when the sign is
wrong, the cheap instrument buys a smaller loss rather than an edge.** F-2a's cost table stands - it
is a property of the instrument - but the purchase case may not lean on F-4. **(5) Stage 2 was not
run, on clause (7) rather than on convenience**: a framework run is earned by a stage-1 survivor and
there is none on three screens; a confirmation year was started and abandoned at >30 minutes per
year because it would have been fitting an already-refused book, and A-10 has run the deployed form
on 2,686 sessions in any case. **No ledger rows**: `record` is reached only from stage 2, and a
stage-1 event study measures bars rather than running a strategy. **Nothing shipped, nothing
promoted, no default changed**: champion unchanged at S-18, `champion.json`, `live/*` and all three
scheduled tasks untouched, `late_momo` still at alloc 0.0 and its module not edited, one new script
only so rule (a) owes no replay. **Standing jobs both ran first**: A-5 part 2 unchanged at 66 fills
/ +2.22 bps / se 0.80 / |diff|/se 0.90; `daily_fills.py` 10 fills / $2.37M / `ref_price` the
previous close **10 of 10**, with the pooled execution number reading **+1.7 bps (se 5.3)** tonight
against +3.2 this afternoon purely because the daily store has not yet published 2026-09-11's
closes, so today's four fills score NaN - a benchmark-availability artifact, not an execution
change. **What it changes for the loop**: F-4 closes the last open item with a stated mechanism, and
on a stronger footing than F-1 or F-3, which found real forecasts and could not afford them. The
only thing left genuinely open on this line is the object F-4 did **not** test and X-1 did - a
**short** lookback reversal at a **short** horizon - which is a different mechanism needing its own
pre-registration. The binding constraint remains the owner decisions in `BLOCKERS.md`.

Status 2026-09-12 00:4x UTC (F-2a): **the futures blocker was never a permission problem - this
account already fetches ES/NQ/MES/MNQ minute history with zero errors - and the one number that
survives the thin sample is that an ES round trip costs 0.488 bps against the 4.70-8.20 bps every
intraday refusal in this repository was written on.** With the standing jobs holding no new input,
the owner decisions blocked and S-24 closing the auction question, this iteration took the last
open item with a stated mechanism: **F-2**, carried since 2026-09-10 as "needs owner: IBKR futures
permission + CME data, or a Databento key" and **never once probed**. New `scripts/futures_data.py`
(probe / depth / front-quarter stitch) and `scripts/sweep_f2.py`; **4 ledger rows** under
`futures/f2_es`; three clauses pre-registered in the docstrings before the first request, including
that a resolving contract definition is *not* evidence of a data grant. **(1) The claim is wrong.**
The paper account returned 2,760 one-minute TRADES bars - two full 23-hour sessions - for **all four
of ES, MES, NQ, MNQ with zero errors** (no 354, no 162, no 10197), plus daily bars. Nothing needs to
be bought for access. **(2) What is missing is retention, and one wrong turn established it**: the
first probe's "expired contracts are gone" was an artifact of a **guessed expiry date** (`20260619`;
the real third Friday is the 18th). By `localSymbol` the expired quarterlies qualify and serve full
data - **ESM6 7,740 bars / 5.9M contracts, ESH6 6,540 / 6.3M, ESZ5 7,455 / 5.5M, ESU5 6,600 / 4.4M**
- while **ESM5 and older return no security definition**, so IBKR retains about **four expired
quarters**. CONTFUT is not a way around it: it **refuses an `endDateTime` outright (error 10339)**
and caps a 1-minute request at one month, so it cannot be paged; daily CONTFUT is the one long
series (**ES 826 sessions from 2023-06-19**, NQ 633, micros 499). **(3) The store**: five contracts
used only in their own front quarter, rolling 8 days before expiry, **447,600 one-minute bars /
313 cash sessions, 2025-06-09..2026-09-10**. **(4) The durable result, because it is a property of
the instrument and not of the sample**: one ES contract carries **$347,117** of notional, IBKR Pro
charges **$2.05 a side** all-in and the book is one tick wide, giving **0.488 bps a round trip**
(0.856 at a full tick, MES 0.744) against **L-1's 6.40-8.20**, **X-1's 4.70** and **F-1's 0.892 of
commission alone at zero spread** - **10x to 17x cheaper**. That reframes every intraday refusal on
file: F-1's forecast was real (OOS IC +0.0113, t +4.74) and died at 0.797 gross bps against a 0.892
floor; on this instrument it would have cleared by 60%. **(5) Both pre-registered mechanisms are
refused**: overnight-into-the-open earns **+1.161 bps at t +0.78** to 10:00 and is gone by 11:00
(-0.316, then -0.431 to the close), and day-momentum-into-the-last-30-minutes is **-2.415 bps at
t -2.56** - the only significant statistic in the table, **with the sign reversed from the premise**.
**(6) The reversal is recorded and labelled post hoc** (+2.415 gross / **+1.927 net at t +2.05**,
win 57%, halves -3.93 / -0.92, so it is concentrated in the first half) - but the *direction* was on
record before this table existed: **X-1 measured the same shape on megacap equities on 2026-09-10**
(+0.63 bps at 10:30, **-0.69 at t -2.80** at 14:30) over 2,684 sessions and filed it as "worth
keeping for a later idea". **(7) On the mandate**: the cash session's gross sd is **0.62% of
notional per contract before any leverage decision**, against the intraday equity sleeve's 0.49%
(L-1) and 0.27% (X-1) *after* leverage - the first instrument measured here where the owner's
3-10%/day range is reachable without sizing up an unproven signal. **Nothing shipped, nothing
promoted, no default changed**: champion unchanged at S-18, `champion.json`, `live/*` and all three
scheduled tasks untouched, no runner-loaded file modified so rule (a) owes no replay. **Standing
jobs both ran first with no new input**: A-5 part 2 at 66 fills / +2.22 bps / se 0.80 / |diff|/se
0.90, `daily_fills.py` at 10 fills / $2.37M / +3.2 bps (se 4.5), `ref_price` the previous close 10
of 10. **What it changes for the loop**: `BLOCKERS.md`'s futures request is rewritten from "needs
data" into a priced one - **CME history back to ~2016 for ES/NQ (Databento MDP-3 or equivalent),
not an IBKR permission** - and the reusable rule is that **a blocker nobody has probed is an
assumption**, which on this one was wrong in its subject (permission, not retention) and understated
in its value (the reason to buy is a 0.488 bps round trip, not any backtest above).

Status 2026-09-11 22:5x UTC (S-24): **the daily store's close is the official closing cross to the
cent and its open is not the opening cross - and once the pre-open book is filled at the price a
real MOO order actually receives, the move the owner is being asked for is worth +1.98 CAR points
rather than +2.13.** S-23 closed with one unmeasured assumption and an explicit instruction not to
re-open it *from that data*: the surcharge the opening auction might charge over the closing one,
bounded at a 3.10 bps breakeven and proxied by minute *ranges* (1.0x-2.0x) because the Alpaca
minute store carries no quotes. This iteration used different data - the same key serves
`/v2/stocks/auctions` (official cross prints, 2016-2026) and `/v2/stocks/quotes` (full SIP NBBO),
neither of which this repository had ever touched. New `scripts/sweep_s24.py`; **4 ledger rows**
under `daily/s24_auction`; three clauses pre-registered in the docstring **before any fetch**.
**(1) The identity clause failed, and how it failed is the finding**: only **82.18%** of sessions
match within 2 bps against the pre-registered 95%, and splitting the test by leg says why - the
implied *close* factor `store_close / sip_close` has a median day-over-day change of **exactly
0.000 bps for all nine names** while the implied *open* factor wobbles 0.6-1.5 bps a day for six of
them. **Yahoo's daily open is the first consolidated print, not the primary auction**; the deployed
15:45 convention has always been marked at exactly the right price, and the defect lands entirely
on the pre-open book. A useful instrument check came free: picking the official cross as "the
largest print by size" independently recovered each fund's listing venue (Arca for seven, NASDAQ
for QQQ/TLT) with no hard-coded table. **(2) So the surcharge was measured rather than estimated.**
The exact close leg makes `f = store_close / sip_close` recover each date's whole adjustment, so
`sip_open x f` puts the real cross on the book's basis and S-19's `simulate` needs no change.
On 2,683 sessions: deployed **22.007%**, pre-open at the store's open 24.134%, **pre-open at the
official cross 23.985%** - the benchmark defect costs **-0.149 CAR points** (paired -0.047 bps/day,
t -1.86), **8% of the move**. And it is the conservative end: an MOO order is matched in a call
auction and **crosses no spread**, so the 2 bp charged to that row is an overcharge; charged
nothing it earns **25.204%**, making the honest range **+1.98 to +3.20** and the recommendation
+1.98. **(3) The pre-registered clause-2 statistic was mis-specified and the placebo is what caught
it.** On 6,074 NBBO rows the opening cross sits **6.12 bps** from the mid 30 seconds later, which
read naively is a 5.75 bps surcharge that would refuse the move - but an unsigned deviation has no
direction, and the *next* 30 seconds with no auction in them move the same names **4.10 bps**.
Signed, the cross sits **-0.213 bps** from fair value with mixed signs. The arithmetic closes it
without the quotes at all: at S-17's **0.68 CAR points per bp**, a real 6.1 bps auction cost would
be worth ~4.2 CAR points, and re-filling the book found 0.149, i.e. **~0.22 bps** against a 3.10 bps
breakeven - **7% of the budget**. **What the quotes do establish is operational, not economic**: the
quoted spread at 09:30:00 is **4.63x** the closing one (XLK **12.7x**, XLE **11.7x**), far worse
than the range proxy, decaying within 30 seconds - not what an MOO order pays, but exactly what a
*fallback* market order would pay, which raises the value of S-23's 09:28 clock guard.
**Nothing shipped, nothing promoted, no default changed**: `--order-type` still defaults to `MKT`,
champion unchanged at S-18, `champion.json`, `live/*` and all three scheduled tasks untouched, and
no file either runner loads was modified, so rule (a) owes no replay and the I-1 gate is unaffected
(S-19's precedent). **Standing jobs both ran with no new input** (S-23 had already pooled today's
session): A-5 part 2 at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90, `daily_fills.py` at 10
fills / $2.37M / +3.2 bps (se 4.5), `ref_price` the previous close 10 of 10. **What it changes for
the loop**: the owner's cheapest decision is now fully priced with nothing left to assume, and the
reusable rule is that **an execution cost on this sleeve must be measured with a sign, or by
re-filling the book - never as an unsigned distance**, because an unsigned distance is mostly
volatility and the placebo proves it.

Status 2026-09-11 21:5x UTC (S-23): **the pre-open MOO path is written, clock-guarded and gated, and
the move it buys survives up to 3.1 bps of extra opening-auction cost - which the only evidence
available says is roughly what the opening auction might charge.** With the instrument audit closed
by S-22 and no open research item that is not blocked on the owner or on data the human must buy,
this iteration took the top item on the corrected priority list: the **pre-open task move**, the
cheapest and best-priced of the owner decisions at +1.85 CAR points. Two things were missing from
it and neither was a strategy question. **(1) The loop's half had never been written** - the page
has been promising `--order-type` OPG/MOO support since S-17, so the owner was being asked to
schedule a run the runner could not execute. **(2) Every version of the +1.85 assumed the opening
auction fills as cheaply as the closing one**, which is the assumption a reasonable person pushes
on. New `scripts/sweep_s23.py`, one new order type on `scripts/paper_trade.py` and a reference-price
fix on `scripts/daily_fills.py`; **4 ledger rows** under `daily/s23_preopen`.
**(1) Written and proved**: IBKR has no "MOO" order type - an opening-auction order is a `MKT`
carrying `tif="OPG"` - and it rejects `OPG` outside **04:00-09:28 ET** one order at a time, which
would leave the book half rebalanced, so the flag **checks the clock before it connects and
refuses** (verified live at 17:51 ET, exit 3, no socket opened). MOO/MOC fills are no longer waited
on, because they settle at an auction that has not happened yet. **(2) The payoff, reproduced on an
independent path**: both books fully charged (2 bp + IBKR Pro financing) through S-19's share-level
harness, the deployed row lands on S-22's **19.640%** to the digit, and pre-open earns **21.515%**
(**+1.875**); at today's cost of money 19.102 -> 20.946 (**+1.844**). Paired **+0.609 bps/day at
t +1.44**, so **nothing here reaches |t| = 2**, exactly as S-19 said; the gain is out-of-sample
weighted **more than three to one** (IS +0.963, OOS +3.222) and it costs a little risk this time
(DD 24.33 against 24.04, and $14.5k more financing, because an earlier fill carries the position a
session longer). **(3) The number this iteration exists for**: solving for indifference, **the
opening auction may cost up to 3.10 bps MORE than the closing auction (2 -> 5.10 bp all-in) before
the move stops paying**, 3.07 at today's rates - against a **measured +3.2 bps** of live 15:45
execution cost, so the opening auction would have to be about twice as expensive as the closing one
for the move to be a wash. **(4) And it might be.** The one read the data supports is a proxy -
Alpaca minute bars carry no quotes - but on 2,687 sessions the **opening minute is 1.0x to 2.0x as
wide as the closing minute** (SPY 1.04, QQQ 1.54, **IWM 2.00**, TQQQ 1.61) and thinner in every
name. At the 2.0x end the move is a wash rather than a gain. The proxy overstates the risk (a
minute's range is continuous trading; an MOO order fills in the opening *cross*), but **the margin
is thinner than +1.85 alone suggests and this is the first time anything has been put on the other
side of the trade**. The recommendation is unchanged - the defect is certain while its price tag is
not - and `daily_fills.py` now scores MOO fills against the **open** they aim at, so the first
post-move session measures whether the 1.85 was collected. **Nothing shipped, nothing promoted, no
default changed**: `--order-type` still defaults to `MKT`, the `--mock --dry-run` plan is identical
to before the change, the **I-1 gate passes 3,689/3,689 at 5,021 orders**, champion unchanged at
S-18, `champion.json`, `live/APPROVED_PAPER.md`, `live/HALT*`, `live/intraday_config.json` and all
three scheduled tasks untouched, and `signals.py`/`main.py` were not modified so rule (a) owes no
replay. **Standing jobs both ran first with no new input** (17:3x ET, after the S-22 iteration had
already pooled today's session): A-5 part 2 at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90,
`daily_fills.py` at 10 fills / $2.37M / +3.2 bps (se 4.5), `ref_price` the previous close 10 of 10.
**What it changes for the loop**: the owner's cheapest decision is now a one-line task change with
the loop's half already merged and gated, and the reusable rule is that **an execution change on
this sleeve should be quoted as a breakeven in the units `daily_fills.py` measures**, not as a CAR
delta against a costless counterfactual.

Status 2026-09-11 21:0x UTC (S-22): **the three instrument corrections are independent, they
compose, and the deployed daily book should be expected to earn about 20% CAR rather than the
champion's headline 24.4%.** S-17 (spread), S-19 (clock) and S-21 (financing) each priced one
harness defect alone; nobody had charged them together, and the owner had never been given one
number for the paper account. New `scripts/_s22_runs.sh` (7 LEAN cells) and `scripts/sweep_s22.py`
(`--report` = the 2^3 factorial and the composition test, `--book` = the pandas book), plus **one
optional argument on `scripts/sweep_s19.py`** (`simulate(..., financing=...)`, default `None`, so
every S-19 row stays bit-identical - the clean cells reproduce 24.077 / 22.192 / 20.965 to the
digit); **25 ledger rows**, control reproducing **`OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`**.
**The rule was pre-registered in `_s22_runs.sh` before any cell ran**, and its second clause wrote
down the answer first: composing the three singles multiplicatively predicts **18.81%** for the LEAN
triple, and the test was whether the measurement landed within 0.5 CAR points of it. **(1) It
landed within 0.026.** Full period: control 24.403 / spread 23.068 / financing 23.087 / clock bound
21.384 / spread+fin 21.745 / spread+clock 20.074 / fin+clock 20.095 / **all three 18.785**, every
pairwise interaction inside **0.021 points**. **The three corrections are independent**, so the loop
may keep pricing defects one at a time and compose them afterwards - which is the reusable half of
the result. **(2) The headline needs the book LEAN cannot be**: the engine cannot fill at the close
of the session it decided in, so its triple overstates the clock. The S-19 pandas book with the new
financing hook agrees with LEAN's financing drag at the backtest convention (**-1.357 against
-1.316**) and its fully-charged `lag1` cell translates to **18.755 against LEAN's 18.785 - two
harnesses 0.03 CAR points apart**. On that footing the deployed 15:45 convention, charged 2 bp of
spread and IBKR Pro financing, earns **19.640% (19.954% in LEAN units), i.e. -4.449 points**, and
**19.415% at today's 3.63% cost of money (-4.988)**. **The promoted headline is about 18% high.**
**(3) Out-of-sample weighted, again**: the triple's halves are **IS 14.194% against 17.698%**
(-2.98% in wealth terms) and **OOS 24.259% against 32.801% (-6.43%)**, more than two to one, for
S-21's reason. **And it costs return, not risk** - across the whole factorial drawdown moves
23.70 -> 23.00 and realized vol 0.155 -> 0.156. **(4) One owner number moves and it is not the risk
posture**: the pre-open task move is worth **+1.85 CAR points on an honestly-costed book at today's
rates** (19.415 -> 21.264), close to S-19's -1.9 on an uncosted one, precisely because the clock and
the two costs do not interact. **Nothing shipped, nothing promoted, no default changed**:
`S1_SLIPPAGE_BPS` 0.0, `S1_SIGNAL_LAG` 0 and `S1_FINANCING` off, champion unchanged at S-18,
`live/*` and the three scheduled tasks untouched, `signals.py`/`main.py` not modified so rule (a)
owes no replay, and the I-1 gate re-ran anyway at **3,689/3,689, 5,021 orders**. **Standing jobs**:
`daily_fills.py` **has new input** - the 15:51 TQQQ sale lands, pooling to **10 fills / $2.37M /
+3.2 bps (se 4.5)** with `ref_price` the previous close in **10 of 10**, a fourth confirmation of the
S-19 clock; A-5 part 2 unchanged at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90 (~4.4 sessions).
One instrument note: `slippage_report.py` needs the default `python` (no `pyarrow` under `py -3.11`),
which is what AGENTS.md prescribes for utility scripts. **What it changes for the loop: the
instrument audit is finished.** Spread, clock and financing are measured, composed and proved
independent; there is no fourth defect of that class left, and every daily-sleeve number from here
should be quoted against ~20% rather than 24.4%.

Status 2026-09-11 20:0x UTC (S-21): **the champion has been borrowing half its equity for free
for twenty-one iterations, that is worth 1.32 CAR points full period and 2.03 out of sample, and
82% of the money was spent in the last four years.** With the unblocked work down to two standing
measurements and four owner decisions, this iteration took the next instrument audit in the
S-17 / S-19 line. The defect is read off the engine source: `DefaultBrokerageModel.cs:368` returns
`MarginInterestRateModel.Null`, whose `ApplyMarginInterestRate` has an **empty method body**, and
`InteractiveBrokersBrokerageModel` does not override it - **LEAN charges no interest on a debit
balance and pays none on a credit balance**. New `scripts/rates.py` (FRED `DFF` = IBKR's USD "BM",
plus the Pro tier schedule), `scripts/sweep_s21.py` (`--probe`, `--schedule`, `--report`) and
`scripts/_s21_runs.sh`; one knob on the shipped algorithm (`S1_FINANCING`, **default off**) with
`S1_FIN_SPREAD` / `S1_FIN_RATES`; **8 ledger rows**, control reproducing **`OrderListHash
a6d6224ce9c70091e5bfa8e96f046bf3`**. **Say first what it is not**: S-17 and S-19 found defects that
could be *fixed*; this one cannot. The paper account has been paying it since its first fill, the
runner is fine, and the only thing wrong was the expectation. **The rule was pre-registered in
`_s21_runs.sh` before any full cell ran** and its first clause is that charging a cost can only
lower CAR, so **nothing here is promotable and `evaluate.py` is not the judge**; the a-priori
estimate (~1.45 points) was written down first so the accrual could be wrong rather than merely
reported, and a 2023Q1 smoke run matched a hand computation ($1,010.88 against $975) before any
full cell was believed. **(1) The state**: a debit balance on **3,073 of 3,689 sessions (83.3%)**,
mean gross 1.250x, mean debit **0.410x of equity overall and 0.493x on debit days**, and **616
sessions in credit (16.7%)** - S-20's risk-off count arriving by a different route. LEAN's own
accrual reports the identical state (mean debit 0.493x, credit within 1.4% of the probe) and 11%
less interest paid, which is the direction compounding predicts. **(2) The calendar is the
finding**: simple drag by year runs 0.16-1.24 CAR points through 2022 and then **3.115 (2023) /
2.535 (2024) / 1.477 (2025) / 1.689 (2026)**; **$106,621 of the sample's $129,406 - 82% - was
incurred in 2023-2026**, so the forward number at today's 3.63% benchmark is about **2.0 points a
year, not 1.3**. **(3) LEAN**, charged to the cash book so it compounds into the next day's sizing:
full period **23.087% / 0.939 / DD 24.1%** against 24.403% / 0.994 / 23.7% (**-1.316**), at 2 bp
21.745% against 23.068% (-1.323), **IS -0.907 (16.791 vs 17.698) and OOS -2.027 (30.774 vs
32.801)** - **out-of-sample weighted more than two to one**, which matters because the OOS half is
the one the S-18 promotion leaned on. **No t-statistic is quoted and none should be**: unlike
S-19's clock this is a deterministic charge. **(4) Half of it is the cost of money and half is the
price list**: same cash path, only the rate moving, gives benchmark-only **0.559** simple points
against IBKR Pro's **1.106** (+0.50pp 1.356), and the markup is the half a larger account pays less
of. One honest correction to the run set: the LEAN `floor` cell (-1.50pp, 24.136%) is **not** the
benchmark - that shift puts the tranches above $100k *below* it - so 0.559 is the floor, not 0.267.
**(5) The one decision it moves, pre-registered as such**: the owner's Reg-T question *is* a
decision about the size of a margin loan and has been asked with the loan free. Budget 0.75 / 0.80
/ 0.82 reads **23.087 / 24.296 / 24.742 financed** against 24.403 / 25.903 / 26.474 unfinanced, so
**the reward for spending the buffer is overstated by about a fifth** and the Sharpe argument thins
six-fold (financed 0.939 -> 0.945 against unfinanced 0.994 -> 1.012) while drawdown still climbs
2.1 points. **It flattens, it does not invert** - `BLOCKERS.md` carries both columns and the
recommendation is unchanged. **Nothing shipped, nothing promoted, no default changed**:
`S1_FINANCING` stays off so the ledger stays on one scale (S-17's precedent), `signals.py` was not
touched so rule (a) owes no replay, `live/*` and the three scheduled tasks are untouched, champion
unchanged at S-18, and the I-1 gate re-ran anyway at **3,689/3,689, 5,021 orders**. **One
instrument fix**: `evaluate.py` now refuses any run recorded with `S1_FINANCING=on` as not
comparable - S-18's same-cost-model rule on a third axis, and note the direction, because this one
*understates* a candidate rather than flattering it. **Standing jobs both ran after the close**:
A-5 part 2 unchanged at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90 (~4.4 sessions);
`daily_fills.py` **has new input** - today's 15:45 rebalance adds IWM/XLE/XLK for $720,338, pooling
to **9 fills / $2.14M / +3.9 bps (se 5.0)** against 6 fills / +2.9 bps, with `ref_price` the
previous close in **9 of 9**, confirming the S-19 clock for a third session. **What it changes for
the loop**: the daily sleeve's three instrument audits now read spread (S-17, 0.68 CAR per bp),
clock (S-19, -1.9, |t| < 2, fixable) and financing (**S-21, -1.32 full / -2.03 OOS / ~2.0 forward,
certain, not fixable**), and every future comparison between two *differently levered* cells on
this sleeve owes the financed column the way S-20 made the vol-matched column compulsory.

Status 2026-09-11 19:0x UTC (S-20): **the regime gate has had one off-state since S-1 - cash -
and giving it a second one adds 2.15 CAR points that the champion's own sizing machinery would
have paid more for. Refused.** With no open research item that is not blocked on the owner or on
data the human must buy, this iteration took the last thing on the daily sleeve that is neither a
ranker lever nor a risk-posture parameter. New `scripts/sweep_s20.py` (`--probe` measures the
*state*, `--report` reads the LEAN cells and adds a vol-matched column) and `scripts/_s20_runs.sh`;
three parameters on the shipped algorithm defaulting to the champion (`risk_off_sleeve` empty,
`risk_off_top_n`, `risk_off_exposure`) with `S1_RISK_OFF_*` overrides; **9 ledger rows**, control
reproducing **`OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`**. **The rule was pre-registered in
`_s20_runs.sh` before any cell ran**: pass `evaluate.py` at 0 bp *and* 2 bp, do not lose the OOS
half, and carry **TLT alone** as the a-priori control. **(1) The state**: the gate is off on
**590 of 3,690 sessions (16.0%)** in 29 episodes, median 15 sessions, longest 72
(2018-10-10..2019-01-24). Held a session forward, TLT earns **+1.68 bps/day (t 0.35)**, IEF +1.86
(0.96), **GLD +9.92 (2.20)**, SLV +7.36 (0.97), HYG +0.92 (0.26) - and **SPY itself +6.57 (0.88)**,
so the gate is not avoiding down markets, it is avoiding the -10.94% day. **Nothing is conditional
on the crisis**: risk-off minus risk-on is +1.39 / +1.50 / +8.07 bps at **t 0.28 / 0.73 / 1.66**.
**(2) LEAN**: the primary (shipped momentum ranking over TLT/IEF/GLD, top 1) earns **26.550% /
0.972 / DD 25.4% / std 0.177** against the champion's 24.403% / 0.994 / 23.7% / 0.155, i.e.
**+2.15 CAR at lower Sharpe and 2.2 more points of realized vol**; TLT alone 24.819% / 0.935 /
23.3%, top 2 of 3 25.968% / 1.004 / 25.4%, and the **post-hoc** GLD-alone cell 27.735% / **1.040** /
25.4%. The halves both gain (**IS 19.135% / 0.915 / 21.3** against 17.698 / 0.911 / 23.7, **OOS
35.905% / 1.074 / 25.4** against 32.801 / 1.108 / 23.3). **(3) The refusal is on the vol-matched
column, which S-15 made compulsory here**: scaling the control to each cell's own realized vol,
the excess is **primary -1.317, primary at 2 bp -2.885, a-priori TLT -2.103, top 2 -0.009** and
only the post-hoc GLD cell is positive (+0.656) - **every pre-registered cell is worse than simply
running the existing book bigger**. Paired daily: primary **+0.90 bps/day at t 0.83** (risk-off
sessions alone +4.85 at t 0.73), and the risk-on column **+0.15 at t 0.56**, which is the proof the
change touches only the state it claims to. `evaluate.py` **refuses the primary at 0 bp** (drawdown
25.400 against 23.700 + 1.0) and returns **"BEATS champion" at 2 bp** (24.982 vs 23.068) - the rule
required both, and unlike S-18's identical-looking split this refusal is a 0.7-point drawdown miss
with a falling Sharpe, not 0.001 CAR points. **(4) One instrument fact, worth more than the cell**:
`risk_off_exposure` is **inert over [0.5, 1.0]** - LEAN reproduced the 1.0 cell to every digit at
0.5 - because the vol target's `target_vol / sigma` exactly cancels an exposure request under a
flat margin budget; it only bites once `scale_cap` binds (0.25). That is S-8's finding restated for
the off-state and is now in the `Params` docstring. **Nothing shipped, nothing promoted, no default
changed**: champion unchanged at S-18, `live/*` and the three scheduled tasks untouched, and the
**I-1 gate was re-run because `signals.py` is a file the paper runner loads** - `compare_orders.py`
passes **3,689/3,689 at 5,021 orders**, unchanged from the S-18 baseline. **Standing jobs ran with
no new input** (14:5x ET, before the intraday close and before the 15:45 rebalance): A-5 part 2
unchanged at 66 fills / +2.22 bps / se 0.80 / |diff|/se 0.90 (~4.4 sessions to settle),
`daily_fills.py` unchanged at 6 fills / +2.9 bps. **What it changes for the loop**: S-15 (the
ranker), S-16 (the proxies and the breaker) and S-20 (the off-state) are three forms of one
finding - **on this sleeve anything that looks like new return is a size decision until it beats
the vol-matched control** - so that column belongs in every future daily-sleeve comparison, and the
binding constraint remains the owner's size question in `BLOCKERS.md`.

Status 2026-09-11 18:1x UTC (S-19): **the largest unblocked number on the daily sleeve was measured
on a strategy that no longer exists and with an instrument that could only bound it; re-measured, the
deployed runner's clock costs about 1.9 CAR points rather than 4.75, and nothing in the comparison
reaches |t| = 2.** With no open research item left that is not blocked on the owner or on data the
human must buy, this iteration took the top unblocked ops number instead of a twelfth mechanism. New
`scripts/_s19_runs.sh` (six LEAN cells) and `scripts/sweep_s19.py` (a share-level book that runs the
shared `signals.py`, fills wherever it is told, and scores itself against LEAN's own equity curve);
**10 ledger rows**, control reproducing **`OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`**.
**(1) The bound, re-run on the promoted champion**: `S1_SIGNAL_LAG=1` earns **21.384% / 0.860 /
DD 22.7%** against 24.403% / 0.994 / 23.7%, i.e. **-3.02 CAR at 0 bp** and **-2.99 at 2 bp**, against
S-17's -4.75 on the retired 3x book - **the S-18 promotion cut the cost of the clock by 36%**, which
is what a return cost does when economic exposure falls from 2.25x to 1.50x. The ladder is concave
(lag 1 costs 3.02, lag 2 a further 0.97) and the halves both lose, out-of-sample weighted (IS 16.443
vs 17.698, OOS 27.431 vs 32.801). **(2) The exact convention, which LEAN cannot express**: a daily
bar for D arrives stamped `D 16:00`, so nothing submitted then can fill at D's close, and
`S1_SIGNAL_LAG=1` is therefore one whole overnight gap staler than the deployed path rather than
equal to it. The pandas book prices all three - **backtest 24.077 / deployed 22.192 / lag1 20.965**,
paired **-0.599 bps/day (t -1.41)** and -0.994 (t -1.86) - after validating at **corr 0.99650**
against the control's own LEAN equity curve (annualized std 0.1863 / 0.1872, tracking sd 9.86
bps/day). **The deployed clock is 61% of the bound**, and the two harnesses agree to **0.09 CAR
points** on the one cell both can run, so **-1.9 CAR** is the number and it replaces -4.75 in
`BLOCKERS.md`. **(3) One instrument finding, in S-17's line**: LEAN reports Annual Standard Deviation
**0.155** and Sharpe **0.994** for a curve carrying **0.186** of trading-day volatility - resampling
onto *calendar* days reproduces 0.157 - so **every Sharpe in the ledger is on a calendar-day basis
and biased down by ~17%**. Cross-cell comparisons inside the ledger are unaffected; comparing a LEAN
Sharpe against one computed anywhere else is not safe, and `sweep_s19.py --validate` prints the
warning with both tables. **Nothing shipped, nothing promoted, no default changed**: champion
unchanged at S-18, `live/*` and the three scheduled tasks untouched, only two new scripts added so
rule (a) owes no replay and the I-1 gate is unaffected. **Standing jobs both ran**: A-5 part 2 has
new input - today's session adds **34 fills at +0.94 bps**, pooled **66 fills / +2.22 bps / se 0.80**
against the shipped 1.50, `|diff|/se 0.90`, ~4.4 sessions to settle; `daily_fills.py` unchanged at
6 fills / +2.9 bps (this ran before the 15:45 rebalance). **What it changes for the loop**: the ops
decision the owner holds is worth less than it looked and is still worth taking, and the honest
framing is that the defect is certain while its value is not.

Status 2026-09-11 17:1x UTC (F-3): **the supervised track is closed, and it closes on a comparison
rather than a tally: at a daily horizon the model's ranking is six times weaker than the momentum
blend it was built to replace, and the champion's own signal is worth 61.5 bps per dollar it turns
over.** The top item, opened by F-1's refusal, which was arithmetic and not a verdict: 0.797 gross
bps against a 0.892 bps floor at 13.8x daily turnover. F-3 ran the identical method where the
turnover is a hundredth. New `scripts/sweep_f3.py` (panel, walk-forward GBDT, book simulation,
falsification control, ridge baseline, `--diagnose`), a **128,882-row panel over 22 ETFs x 6,718
sessions** with 41 causal features, an exported forecast (`data/f3/ml_scores.csv`, 3,692 dates),
two defaulted-off knobs on the shipped algorithm (`S1_ML_SCORES`, `S1_ML_MODE`), an OHLC loader on
`lean_prices`, and **12 ledger rows**. Universe is the ETF sleeve **only** - the 50 megacaps are
excluded features and all, because that list is the 2026 survivor set (S-7). Selection on
train <= 2007 -> validate 2008-2011 picks the 5-day horizon in every cell; the walk-forward then
covers **2012-2026, the champion's own window**, retrained yearly on <= Y-2, so the LEAN comparison
is directly against `champion.json`. **The date convention was proved, not assumed**: `main.py` now
logs the history frame's last bar, and a two-month run shows `last_bar=2012-01-03 16:00:00` with
the store's own close, so an exact-date join of a score built from bars <= D is causal.
**The forecast is real and tiny**: pooled out-of-sample **IC +0.01133 at t +2.17**, but gross P&L
**t +0.18** and only **0.304 bps per dollar turned** - *less* than F-1's 0.797 - and the **ridge
baseline scores a higher IC than the tree (+0.01223)**, the opposite of F-1, so there are no
interactions to earn the complexity. Six of fifteen test years have negative IC. **LEAN refuses it
on every criterion, three times**: ML ranking with the champion's gate **10.322% / 0.408 / DD
36.6%**, with the ML gate 9.908% / 0.385 / 35.6%, and with no floor on the ML score at all (the
cell that answers "was it the gate?") **11.400% / 0.461 / 36.0%** - against the champion's 24.403%
/ 0.994 / 23.7%, and worse than S-15's *no ranking at all* (17.7%). **The diagnosis is the keeper**:
on the nine names the sleeve actually ranks, the forecast scores **IC +0.00691 (t +0.97)** against
the momentum blend's **+0.04268 (t +5.43)**, in both halves, with the two scores only **+0.091**
rank-correlated; as unlevered top-3-of-9 books the forecast earns $305/day at 9.29 bps per dollar
turned on 486k/day, the momentum blend **$617/day at 61.51 bps on 105k/day**. **Nothing shipped**:
control reproduces **`OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`** (5,128 orders, 24.403%,
$27,199.76) and the I-1 gate passes **3,689/3,689 at 5,021 orders**, so the knob is inert on the
deployed path; `live/*` and the scheduled tasks untouched; champion unchanged at S-18.
**One instrument defect fixed**: the two-month convention run annualizes to 47.3% CAR / 1.2% DD on
71 orders and `evaluate.py` would have called it "BEATS champion" - it now refuses any run whose
recorded environment moved `S1_START`/`S1_END` as not comparable, S-18's rule applied to the window
instead of the cost model. **Standing jobs both ran with no new input** (12:3x ET, before the
rebalance): A-5 part 2 unchanged at 58 fills / +2.42 bps / se 0.88 / |diff|/se 1.04 (~5.5 sessions
to settle), `daily_fills.py` unchanged at 6 fills / +2.9 bps. **What it changes for the loop**:
F-1 and F-3 together price the whole supervised class - the model finds IC ~ +0.011 wherever it is
pointed, and what decides its worth is the edge-to-cost ratio of the mechanism it rides, which on
both sleeves is weaker than what already ships. **The backlog holds no open research item that is
not blocked on the owner or on data the human must buy**; the top unblocked number is still the
runner's clock at -4.75 CAR.

Status 2026-09-11 15:5x UTC (F-1): **the machine learning track finds the first positive
out-of-sample gross edge the intraday side of this repository has ever produced, and it is worth
about half of its own commission.** The top backlog item, and the one mechanism class the loop had
never tried. New `scripts/sweep_f1.py` (panel builder, walk-forward GBDT, book simulation,
falsification control), a cached 1.59M-row panel over **56 tradable names x 2,682 sessions x 11
decision points**, 38 causal features, 5 ledger rows under `intraday/f1_gbdt`; `scikit-learn`
1.9.1 installed. Train 2016-2021, validate 2022-2023 (hyperparameters only), test 2024-2026 with a
yearly expanding retrain. **The signal is real**: pooled out-of-sample IC **+0.0113 at t = +4.74**
and gross **+$1,102/day at t = +3.04**, against a falsification control (labels shuffled within
each timestamp) at IC +0.0031 and gross **0.071 bps** per dollar turned - a ninth - and a ridge
baseline that finds almost nothing (validation IC +0.0027 vs the tree's +0.0105), so it lives in
the interactions. **And it is refused on arithmetic that no execution can reach**: the book turns
**$13.8M/day on $1M**, and per dollar traded it earns **0.797 bps against 0.892 bps of commission
and regulatory fees - at zero spread**. Breakeven slippage by decile: 0.04 **+0.129 bps**, 0.10
**-0.095**, 0.20 -0.229, 0.34 -0.360; the one cell that clears commission does so by 0.129 bps
against a half-cent tick worth 0.3-1.0 bps, and its worst day is **-$81,038** on a $1M book, past
the sleeve's own 2.5% loss limit. Net **-$2,206/day at t -6.02**, 0 of 3 test years positive,
**REFUSED** by the pre-registered rule. **The decay is the finding for the next step**: IC by test
year **+0.0192 -> +0.0113 -> -0.0001** and gross bps **1.293 -> 0.638 -> 0.293**, while permutation
importance is *stable* (rank correlation 0.66-0.77 across retrains, the same top features every
year: `vwap_atr`, its cross-sectional rank, `vol_rel`, `rng_atr`) - the model keeps its grip on
intraday VWAP reversion conditioned on relative volume and that mechanism's payoff is shrinking.
**Nothing shipped**: `live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*` and the
scheduled tasks untouched, no file either runner loads was modified, so rule (a) owes no replay;
champion unchanged at S-18's unlevered book. **What it changes for the loop**: F-1 is closed and
should not be re-opened as a feature, model or horizon question - the gap is a factor, not a
percent. The successor it opens is **F-3**: the same supervised method at a *daily* horizon on the
daily sleeve, where a hundredth of the turnover buys the same bps of edge. **Standing jobs both
ran**: A-5 part 2 now has **58 fills over 2 sessions** (+2.42 bps pooled, se **0.89**, |diff|/se
1.03 - today's 26 fills came in at +1.26 and halved the standard error; ~5.5 sessions to settle),
`daily_fills.py` unchanged at 6 fills / +2.9 bps because the 15:45 ET rebalance had not run.

Status 2026-09-11 15:1x UTC (S-18): **the champion is now the unlevered book - the first promotion
since S-12, and the first one whose case is risk rather than return.** S-17 left (e+g) at the
unchanged 0.75 budget as the top item with three missing pieces, each a run rather than a judgement;
all three are supplied. Eight new LEAN cells (`scripts/_s18_runs.sh`, read by `scripts/sweep_s18.py`)
plus three verification runs, 11 ledger rows. **The halves, which S-16 never ran** (candidate vs
champion, the windows S-12 itself was promoted on): IS 2012-2019 **17.698 / 0.911 / DD 23.7 against
19.180 / 0.884 / 25.1** (-1.48 CAR, paired -0.50 bps/day, t -1.25), OOS 2020-2026 **32.801 / 1.108 /
23.3 against 30.863 / 0.985 / 22.6** (+1.94 CAR, +0.58 bps/day, t +0.87); at 2 bp IS 16.349 vs
17.509 at **DD 25.0 vs 29.2** and OOS 31.477 vs 29.621. **So the return difference is out-of-sample
weighted and the risk difference holds in both halves** - the mirror image of S-15's reading of
S-12's tilt - while **nothing in the comparison reaches |t| = 2** and the full-period return
statistic is +0.05 bps/day at t +0.12. **What `evaluate.py` compares against is answered in code**:
`backtest.py` now records the `S1_*` environment with every run, `champion.json` carries
`stats_by_spread` (one column per cost model, each with its own `run_dir`), and `evaluate.py` picks
the column matching the candidate's own `S1_SLIPPAGE_BPS` and **refuses a run at a spread it has no
column for**. The gate then produced both verdicts: **2 bp BEATS champion** (23.068 / 0.938 / 25.0
against 22.926 / 0.865 / 29.2), **0 bp refused by 0.001 CAR points**, and the promotion was made on
the 2 bp row. **The two no-ops held**: the shipped defaults reproduce the tested cell exactly
(**5,128 orders, 24.403%, 0.994, 23.700%, $27,199.76, new `OrderListHash
a6d6224ce9c70091e5bfa8e96f046bf3`**) and `S1_PROXY=on S1_DD_HALVE=0.15 S1_DD_FLAT=0.25` reproduces
the retired champion bit-for-bit (**5246804e17a67af90028ffceead7d3b3**), which needed one structural
fix - `margin_requirement` reads `LEVERED_PROXY_3X`, because IBKR's 100% on TQQQ is a fact about
TQQQ and not about whether this strategy holds it. **I-1 gate re-run**: `compare_orders.py` passes
3,689/3,689 at 5,021 orders both sides, and `--mock --dry-run` plans XLE/XLK/IWM at 1.50x gross with
margin 0.75 - expect the next 15:45 ET paper session to rotate out of TQQQ. **The band was measured
on the new book and NOT changed**: 0.03 is worth +0.064 CAR at 0 bp and +0.103 at 2 bp (t +0.58 /
+0.94), a fifth of S-17's +0.57 on the 3x champion, because most of what it used to save was the
proxy sleeve's vol-drift re-weighting. **The case, stated as it should be read: not more return -
the same return with 0.073 more Sharpe, 1.5 points less realized vol, 4.2 fewer points of drawdown
at 2 bp, 40% less commission and 1.50x economic exposure against 2.25x.** `margin_budget` stays
0.75, `S1_SLIPPAGE_BPS` stays 0.0, the signal and regime filter are untouched, and `live/APPROVED_PAPER.md`,
`live/HALT*`, `live/intraday_config.json` and the scheduled tasks were not touched. **Standing jobs
both ran**: `daily_fills.py` unchanged at 6 fills / **+2.9 bps (se 6.8)**; `slippage_report.py` had
**new input for the first time since A-5 part 2** - today's partial session adds 23 fills at +1.11
bps, pooled **+2.42 vs the shipped 1.50, |diff|/se 0.99**, still inside 2 se so the constant is
untouched (~6.1 sessions to settle). **What it changes for the loop**: the daily sleeve's remaining
levers are all risk-posture ones, and the owner's Reg-T buffer question is now worth *more* (the
unlevered book at budget 0.78 / 0.80 / 0.82 earns 25.307 / 25.903 / 26.474 at rising Sharpe), while
the largest unblocked number on this sleeve is still the runner's clock (-4.75 CAR, S-17). The top
open item is now **F-1**.

Status 2026-09-11 13:3x UTC (S-17): **sixteen iterations have judged the daily sleeve on a harness
that charges no spread, and the deployed runner trades a signal one session stale - which is worth
4.75 CAR points and is the largest number on this sleeve since S-9.** With no open research item
left, this iteration audited the instrument instead of the strategy. Two knobs on the shipped
algorithm (`S1_SLIPPAGE_BPS`, `S1_SIGNAL_LAG`, both defaulting to the champion), twelve LEAN cells
(`scripts/_s17_runs.sh`, read by `scripts/sweep_s17.py`), a new live-fill instrument
(`scripts/daily_fills.py`), 12 ledger rows, control reproducing **`OrderListHash
5246804e17a67af90028ffceead7d3b3`**. **(1) The zero spread is LEAN's default, not a choice**:
`DefaultBrokerageModel.GetSlippageModel` returns `NullSlippageModel.Instance` and the IB model does
not override it, while `EquityFillModel.MarketOnOpenFill` *does* apply a model when set. The ladder:
**24.404 -> 23.699 (1bp) -> 22.926 (2bp) -> 21.129 (5bp) -> 18.216 (10bp)** at drawdown **25.1 ->
27.2 -> 29.2 -> 31.7 -> 32.3**, i.e. **0.68 CAR points per basis point** (paired t -1.84 / -3.48 /
-9.32 / -10.27), which implies the book pays spread on ~68x its equity a year. **Every cross-cell
comparison in the S-track is therefore biased toward turnover, and the cells differ by 2.7x in order
count.** **(2) The measured cost**: `daily_fills.py` on the 6 paper fills / $1.42M gives **+2.9 bps
(sd 16.7, se 6.8)** against the 15:45 close the runner aims at - the same size as the intraday
sleeve's +2.89. **(3) The deployed runner is a session late**, proved not inferred: `paper_trade.py`
reads `yf.download(period="2y")` at 15:45 ET, whose last *complete* bar is the previous close, and
`ref_price` equals it in **6 of 6 fills** while the runner's own `plan` event has been logging
`as_of = D-1` all along. So the backtest reads closes through D and fills at the open of D+1, while
live reads through D-1 and fills at the close of D. `S1_SIGNAL_LAG=1` (a tight upper bound, one
overnight gap staler than live) prices it at **19.649% / 0.736, -4.75 CAR, paired -1.55 bps/day at
t -2.65**, and **18.592% with the spread on top** - it costs return, not risk (drawdown *improves*,
23.7 vs 25.1). The fix is the pre-open MOO convention, which needs the scheduled task moved and is
in `BLOCKERS.md`. **(4) The spread re-ranks S-16's frontier and frees one cell from the owner's
question**: S-16's (e+g) at the **unchanged** 0.75 budget was refused by 0.001 CAR points, and that
margin exists only at exactly zero spread - **0 bp -0.001, 1 bp +0.036, 2 bp +0.142**, with Sharpe
0.938 vs 0.865, drawdown **25.0 vs 29.2** and fees $24.9k vs $41.9k at 2 bp. The crossover is at
~0.03 bp against a half-cent tick of 0.27-0.77 bp. Its return edge is still t = +0.12: the case is
same return for less risk and less cost, not more return. **(5) The owner's no-trade-band question
is answered**: at 2 bp, band **0.03 earns +0.57 CAR (t +1.22) and 3.8 fewer points of drawdown**
than the shipped 0.01, while 0.08 gives it back (+0.09) - the direction is evidence now, the level is
still S-13's path luck. **Nothing shipped, nothing promoted, no default changed**: `S1_SLIPPAGE_BPS`
stays 0.0 because 2 bps rests on six fills with se 6.8 (A-5 part 2's rule), the champion is unchanged
at S-12, `champion.json`, `live/` and the scheduled tasks are untouched, and neither new knob is in a
file the runners load, so rule (a) owes no replay. **What it changes for the loop**: the post-S-16
conclusion that only owner decisions remained was true about strategies and wrong about the
instrument - **S-18** (promote the unlevered cell properly) and the runner's clock are both real work
that no owner answer blocks.

Status 2026-09-11 12:1x UTC (S-16): **the champion's 3x sleeve and its drawdown breaker are worth
exactly zero return between them, and three cells that pass `evaluate.py` are now sitting behind one
unanswered owner question.** S-15 removed each switch alone; S-16 runs the two that pointed the same
way together and asks what the unlevered book does when its lost exposure is bought back with
*account* leverage instead of *instrument* leverage. Nine full-period LEAN cells plus two
sub-periods, all `S1_*` overrides (`scripts/_s16_runs.sh`, read by `scripts/sweep_s16.py`), 11
ledger rows, control reproducing **`OrderListHash 5246804e17a67af90028ffceead7d3b3`**. **The
structural fact behind it**: IBKR charges 0.333 of margin per unit of economic exposure on a 3x ETF
against 0.5 on an ordinary one, so the proxies' whole contribution is that 2.25x of exposure fits
inside a 0.75 budget. **The dead heat**: proxies off *and* overlay off at the unchanged 0.75 budget
earns **24.403% against the champion's 24.404%** - paired **-0.00 bps/day, t -0.00 on 3,689
sessions** - at **std 0.155 vs 0.170, drawdown 23.7 vs 25.1, PSR 33.2 vs 23.0 and $27.2k of fees vs
$45.7k**. **The frontier**: spending the freed risk through the budget is a clean dial, 0.75 ->
0.78 -> 0.80 -> 0.82 giving CAR 24.403 / 25.307 / 25.903 / 26.474 at std 0.155 / 0.160 / 0.164 /
0.168 and Sharpe **rising** 0.994 / 1.003 / 1.008 / 1.012 (on the 3x book, O-1b measured Sharpe
falling with size). At budget 0.82 the unlevered book matches the champion's realized vol (0.168 vs
0.170) and earns **26.474% / 1.012 / DD 25.7**, i.e. **+0.66 bps/day at t = 2.02** - the first t
above 2 the S-track has produced *in favour of* a change. **In an unlevered book the breaker is
strictly harmful**: at budget 0.80, shipped overlay 24.551 / DD 25.5, widened to 0.20/0.30 25.333 /
DD **25.0**, off 25.903 / DD 25.1 - monotone in return, flat-to-better in drawdown, a shelf and not
a spike (S-8's re-arming problem: a step breaker that flattens at -25% sells the bottom).
**Nothing shipped, and this is not a refusal**: (e) at 0.80, (e+g) at 0.80 and (e+g) at 0.82 each
return **"BEATS champion"** from `evaluate.py`, and every one of them needs `margin_budget` above
0.75 - the open owner question from O-1b, which `BLOCKERS.md` records as not the loop's to move. The
budget-neutral cell is the one the loop could have promoted alone and it **misses by 0.001 CAR
points**. Champion unchanged at S-12, `champion.json`, `live/` and the scheduled tasks untouched,
new scripts only so rule (a) owes no replay. **What it changes for the loop**: the owner question in
`BLOCKERS.md` now carries a fourth option that dominates O-1b's option (b) - the same +1.50 CAR at
**lower** realized vol, the identical 25.1% drawdown and 31% lower fees - and until it is answered
there is no daily-sleeve work left that is not behind it. The gain is also one regime deep (IS +0.07
bps/day at t 0.24, OOS +1.36 at t 2.16), which the entry says out loud. A-5 part 2 had no new input
(ran 07:3x ET, before the open; still 2026-09-10 alone: 32 fills, +2.89 bps, se 1.33, ~6.8 sessions
to settle).

Status 2026-09-11 11:1x UTC (S-15): **71% of the champion's 24.4% CAR is no skill of any kind, and
not one of the switches the loop has spent six iterations tuning is distinguishable from zero.**
The attribution S-14 asked for: eight full-period LEAN runs, each the shipped algorithm with one
switch removed through an `S1_*` override (`scripts/_s15_runs.sh` runs them, `scripts/sweep_s15.py`
reads them), 8 ledger rows, nothing judged. Two new knobs default to the champion
(`S1_MIN_MOMENTUM`, `S1_PROXY`) and the control reproduces **`OrderListHash
5246804e17a67af90028ffceead7d3b3`** exactly. **The table**: champion **24.404% / 0.921 / 25.1% DD
/ 0.170 std**; (f) **no skill at all** - nine ETFs equal-weighted, unlevered, no ranking, no entry
gate, no regime filter, only the vol target, margin budget and overlay - **17.282% / 0.711**, i.e.
the entire signal stack is worth **+7.12 CAR at t = 1.37**; (a) no ranking 17.700% / 0.780 at std
**0.137**, and **vol-matched (a2, budget 0.93, std 0.163) 20.745%**, so **ranking is +3.66 CAR at
t = 0.92**, not +6.70 - a third of its apparent value is just that three names carry more vol than
nine, and the +2.20 bps/day it scores is S-14's +2.02 arriving by another route; (b) regime filter
off 22.383% but **drawdown 31.4%** and std 0.189, with an in-sample contribution of **exactly zero**
(-0.04 bps/day, t -0.03) - it is a drawdown instrument, not a return one; (e) **levered proxies off
23.128% at Sharpe 0.950, DD 23.6%, std 0.153, PSR 27.4% and $25.6k of fees** - better than the
champion on every risk-adjusted measure for 1.28 CAR, which is L-1's finding on the daily sleeve:
**3x instruments supply volatility, not edge**; (g) overlay off **25.998%**, so the breaker costs
**1.59 CAR** and is the only near-significant statistic in the table, against it (-0.51 bps/day,
**t -1.93**, OOS **t -2.35**), buying 2.1 points of drawdown; (d) S-12's allocation tilt +0.80 CAR
overall but **+0.52 bps/day (t 1.45) in 2012-2019 and -0.06 (t -0.10) in 2020-2026** - the last
promotion's edge is in-sample. **Nothing shipped, nothing promoted, nothing refused**; champion
unchanged at S-12, `live/` and the scheduled tasks untouched, all eight cells are env overrides so
rule (a) owes no replay. **What it changes for the loop**: further ranker tuning is the
lowest-value work available (+3.66 CAR at t = 0.92, and S-14 showed it does not survive dilution);
the two components with real effects - the **vol target / margin budget**, which produces 71% of
the return, and the **regime filter**, which produces the drawdown profile - are risk-posture
parameters, so they run into the open owner questions in `BLOCKERS.md`, not into another backtest.
A-5 part 2 had no new input (ran 06:3x ET, before the open; still 2026-09-10 alone: 32 fills,
+2.89 bps, se 1.33, ~6.8 sessions to settle).

Status 2026-09-11 10:3x UTC (daily review, no experiments run): **ten iterations, 82 ledger rows,
nothing shipped to a deployed file, and the backlog is out of mechanisms.** In 24 hours the owner's
3-10%/day list was measured in full and refused in full (O-1, O-1b, L-1, X-1, O-2), the A-track
spent its last two defences (A-12, A-11), S-2 closed the last open S-track mechanism, and S-14
priced the champion's own ranking edge at **+2.02 bps/day, t = 2.07**. The champion is unchanged at
S-12 and reproduced `OrderListHash 5246804e17a67af90028ffceead7d3b3` three separate times.
**Priority for the next 24 hours: (1) A-5 part 2 after the close** - today is only the second
session that can produce fills, and the slippage constant is ~6.8 sessions from settling against a
2.52 bps breakeven; **(2) S-15**, the return attribution, which is the only remaining question whose
answer cannot be guessed from the ledger; (3) per-session ops. One new ops blocker carried forward:
`live/alerts.json` does not exist, so all 17 alerts raised on 2026-09-10 were dropped and the
intraday log is the only alert surface. One process gap recorded: **L-1 wrote zero ledger rows**
(`sweep_l1.py` does not record) - wire the ledger call into the next sweep script. Full review in
`research/reports/2026-09-11.md`.

Status 2026-09-11 10:2x UTC (S-14): **breadth is refused - more candidates make the daily champion
monotonically worse - and the measurement behind the refusal found that the champion's entire
cross-sectional edge is +2.02 bps/day at t = 2.07.** With the backlog out of open mechanisms
(S-2 closed the last one), this iteration took the direction S-12 and the 2026-09-09 owner
decision both name and nobody had measured: the sleeve ranks **nine** ETFs and holds three, so
completing the GICS sector map should make the top three a real selection. Fetched 13 ETFs
through the D-1 pipeline (XLV XLY XLP XLI XLU XLB XLRE XLC EFA HYG IEF SLV VNQ, 1998-2026, all
validated; XLRE/XLC list mid-sample and enter only when they have a full lookback), added two
nested sleeve presets and `scripts/sweep_s14.py`; 7 ledger rows. **LEAN, full period: CAR
24.404% / Sharpe 0.921 (etf9, control) -> 17.253% / 0.663 (17 names) -> 11.622% / 0.430 (22
names)**, at unchanged realized vol (0.170 / 0.163 / 0.165), and `evaluate.py` refuses all four
candidates. The nearest candidate loses **both** halves (IS 12.626% vs 19.18%, OOS 22.929% vs
30.86%). **The decomposition is the keeper**: with leverage, the vol target and the overlay
switched off, the unlevered top-3 basket's return splits into the menu and the ranking spread -
etf9 **7.21 = 5.20 + 2.02 bps/day (t 2.07)**, sector17 5.73 = 4.90 + 0.82, broad22 5.27 = 4.32 +
0.94; paired, **-1.37 bps/day (t -1.95)** and **-1.89 (t -2.23)** against the champion, of which
only -0.30 is the worse menu and **-1.20 is the signal picking worse**. At `top_n=5` every spread
collapses to insignificance (etf9 **+0.84, t 1.16**), so **the edge exists only at top-3-of-9 and
every dilution costs it**. The steelman does not rescue breadth: `top_n=5` on the wide sleeve
recovers 2.4 points of CAR, and **vol-matched to the champion's own 0.17 std it still earns
22.879% / 0.872 against 24.404% / 0.921 on 8,279 orders against 4,735**. What breadth does buy is
a smoother path (unlevered drawdown 22.4% -> 14.3%). **Refused and closed; nothing shipped** -
champion unchanged at S-12, the control reproduces `OrderListHash
5246804e17a67af90028ffceead7d3b3`, `compare_orders.py` passes 3,689/3,689, `live/` and the
scheduled tasks untouched. Two defects fixed in `fetch_data.py`: the manifest was **rewritten**
rather than merged (69 entries erased by a 13-symbol fetch; restored and the merge verified) and
`--symbols <ONE>` crashed on yfinance's single-symbol column layout. **The successor is S-15**,
the uncomfortable question this raises: if 2 bps/day is the whole selection edge, most of the
champion's 24.4% CAR is levered beta plus the regime filter, and that attribution should be
measured before more work is spent on the ranker. A-5 part 2 had no new input (ran 05:3x ET,
before the open; still 2026-09-10 alone: 32 fills, +2.89 bps, se 1.33, ~6.8 sessions to settle).

Status 2026-09-11 09:3x UTC (S-2): **the index-ETF opening-range breakout is refused before the
LEAN build, and the thing that made it look profitable is the stop, not the signal.** S-2 has been
open since 2026-09-08 and was the last research item on the backlog with a stated mechanism that
is not parked, an owner question or infrastructure. Fetched SPY/QQQ/IWM from Alpaca SIP
(2016-01-04..2026-09-10, ~1.046M bars each; the store is now 63 symbols), built the event study
(`scripts/sweep_s2.py`) and confirmed it through the shipped harness; 3 ledger rows under
`intraday/orb`. **Stage 1, 2,687 sessions with nothing fitted, 16 breakout cells and their 16 fade
controls: 0 of 16 pass** the pre-registered rule and every cell loses - the best on net is
`orb15 mid e120` at **gross +2.11 bps/trip against a 3.65 bps round trip, net -1.54, -$113/day,
t -1.64**. **The finding is the symmetry**: the fade earns positive gross too, in **14 of 16
cells**, so gross splits into the part a signal owns, `(brk - fade)/2`, and the part both signs
share, `(brk + fade)/2`. The shared part is **positive in all sixteen cells (+0.33 to +1.43 bps)**
and is pure stop convexity - a stop plus a hold-to-close exit is convex in either direction, so a
coin flip collects it - while **the largest directional edge anywhere is +1.09 bps against 3.65
bps of cost (0.30x), and in 6 of 16 cells it is negative.** TQQQ, the leveraged read, is worse:
cost **4.85 bps**, 0 of 8, and in its best cell the breakout earns **+$33.78/day against its own
fade's +$33.79** - no direction left at all. **Stage 2 through the deployed framework** (shipped
ORB module, `--symbols SPY QQQ IWM`, 0.36x gross on $1M): **-$186 / -$211 / -$39 per day by
regime, 0 of 3**, and backing out costs, **+$11/day of gross over eleven years against $171/day
paid to collect it**. Stage 1's one optimism - closing an untouched trip at the last minute bar
rather than the auction - only helps the strategy, so the LEAN build S-2 asks for could only make
this worse. **Refused and closed; nothing shipped**; the only behaviour change is a research-store
fix (`alpaca_data.py --splits` **merged** instead of replacing - a bare run used to silently
rewrite the 60-symbol split table as 16 symbols over a 2024+ window, re-introducing the exact
cost-model defect A-10 fixed; all 60 pre-existing factors verified byte-identical). `live/` and
the scheduled tasks untouched; the rule-(a) replay of 2026-09-08 with the exact deployed config
reproduces the sleeve to the digit (34 trades, 368 decisions, flat, P&L -2,302 on 500k). Champion
unchanged at S-12. A-5 part 2 ran first as the standing job and **had no new input** (still one
session: 2026-09-10, 32 fills, +2.89 bps, se 1.33 vs the shipped 1.50, |diff|/se 1.05, ~6.8
sessions to settle it) because this ran at 04:3x ET, before the open. **The backlog now holds no
open research item with a stated mechanism**: A-8 is parked by A-4's power calculation, A-3 is
settled by A-10, D-2b and E-2b are infrastructure, and S-5 needs two sleeves with positive
expected return where there is one. Everything that remains is an owner decision in `BLOCKERS.md`.

Status 2026-09-11 08:3x UTC (A-11): **the impossible fills are real, four times larger than the
IBKR window showed, and they are not load-bearing - and the half of the universe whose fills *are*
real is the half that never made money.** A-5 flagged the sleeve's participation as a cost-model
defect; A-11 sizes it on 2,686 Alpaca sessions with the deployed allocation (ORB alone), one
backtest per (cell, year) from a fresh $1M book, 18 ledger rows. (The three sweeps ran to
completion at 03:40-04:03 ET in a preceding iteration that was cut off before writing anything;
this iteration verified them against the store, added the cost/gross decomposition and the paired
liquid-vs-illiquid statistics, replayed, and recorded. No sweep was re-run.) **The diagnostic**:
90,441 fills, notional-weighted **p50 1.46% / p75 4.71% / p90 18.80% / p99 950% / max 38,759%**
against A-5's 1.03 / 5.55 / 26.1 / 199, with **24.1% of notional filling at >5% of its minute,
9.7% at >20% and 4.1% (3,651 fills) at >100%** - orders bigger than everything that traded in the
minute they are booked at. The store is split-adjusted on price *and* volume (SMCI 2016-01-04:
4.34M adjusted shares at $2.39 = 434k real at $23.88), checked before anything was believed, so
these are real participations. **The cap** (clip to a share of the trailing-median volume of the
fill minute, knowable at decision time, worked over following bars): **$/day off -331 -> 0.10
-336 -> 0.05 -367 -> 0.02 -430**, paired t **-0.25 / -1.24 / -2.40**, against costs/day
**907 -> 917 -> 941 -> 969** - so at the 0.10 cap the backtester clips **213,338 orders** refusing
a cumulative **$4.78M/day** of intended notional (vs $3.59M/day executed) and the book moves
**-$5/day, of which +$10/day is the slicing commission: implied Δgross +$5**. **Outcome (c): the
defect is real and immaterial.** The fills nobody could get were not the ones making the money, so
every A-track number stands and `part_cap` stays 0. **The finding is the universe split**: as two
disjoint books, the **liquid 8** (AAPL/AMZN/META/MSFT/TSLA/NVDA/GOOGL/NFLX, 8.8% of notional above
5% of the minute) earn **-$195/day at t = -1.89**, the **most significant negative reading this
sleeve has produced**, while the **illiquid 8** (SMCI/SOXL/MSTR/SOXS/AVGO/PLTR/COIN/AMD, 45.8%)
earn -$164 at -0.83; paired difference -$31/day, t -0.18, corr 0.498. **And on the 261-session
fitted window - the sleeve's only positive evidence in eleven years - liquid 8 earn -$102/day and
illiquid 8 +$361/day**: all of it is in the half whose fills cannot be trusted (median order 4.12%
of its minute, p90 94%). **Refused and closed; nothing shipped**, only `scripts/sweep_a11.py`
changed (a `--label` flag); `live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*` and
the scheduled tasks untouched, and the deployed-config replay of 2026-09-08 reproduces the sleeve
exactly (34 trades, 368 decisions, flat, P&L -2,302 on 500k). Champion unchanged at S-12. A-5
part 2 had no new input (still one session: 2026-09-10, 32 fills, **+2.89 bps, se 1.33** vs the
shipped 1.50, |diff|/se 1.05, ~6.8 sessions to settle it). **The A-track is now out of both levers
and defences** - A-11 was the last "the backtest was unfair to it" argument, and it fails in both
directions. The open `equity_frac` question in `BLOCKERS.md` is all that is left on this sleeve;
A-11 is appended there as evidence.

Status 2026-09-11 04:5x UTC (A-12): **the ORB whipsaw lockout is refused, and the event study that
refused it found the sign inverted - the reversal re-entry is the sleeve's only profitable trade
category.** The 2026-09-10 paper session lost 77% of its -6,779 in one stopped-out-then-flipped
pattern in semis, which the shipped module permits because `max_entries` is counted per *side*. New
`reentry_block`/`reentry_mode` on the ORB module (default **0 = off**) and `scripts/sweep_a12.py`;
18 ledger rows. **Stage 1, 44,219 round trips over 2,686 sessions with nothing fitted**: the
session's first entry earns **-$25/trip (t -2.66, total -$872,347)**, the `flip` re-entry **+$15
(+0.65, +$70,708)** and the `same` continuation -$20 (-1.03); **98% of the sleeve's loss is in first
entries**, which no re-entry filter can reach. The whole effect lives in the **first fifteen
minutes** and points the other way: gap 0-15 is **flip +$78/trip (t +1.72)** against **same -$81
(t -1.96)**, and every longer bucket is flat (|$| <= 26, |t| <= 0.66). **Stage 2, the paired grid
(5 cells, one backtest per variant-year, 2,686 sessions): 0 of 5 pass.** The two cells with the
hypothesised sign lose - flip15 **-$31/day (t -1.17)**, flip60 **-$47 (-0.93)** - and the only
positive cell is the falsification control, `same15` **+$38/day at t +1.69, 0 of 3 regimes**, chosen
after seeing the gap table and worth 0.1 trades/day. Deployability fails for all: control
**-$331/day (t -1.35)**, best variant -$293 (-1.19). **A free measurement fell out**: this control
is the first full-sample run since A-5 part 2 charged the sell-side regulatory fees, and with
trades/day identical to A-10's rows the whole delta is cost - **ORB alone -$289/day -> -$331/day**.
**Refused and closed; nothing shipped**, `live/intraday_config.json`, `live/APPROVED_PAPER.md`,
`live/HALT*` and the scheduled tasks untouched, and the rule-(a) replay of 2026-09-08 reproduces the
deployed sleeve exactly (34 trades, 368 decisions, flat at close, P&L -2,302). Champion unchanged at
S-12. **The durable lesson is A-9's in another shape: one session's worst pattern is not evidence
about the population** - the day that motivated this item belongs to a 4,841-trip category that
earns +$15 a trip. One ops blocker added: live alerting is dead (`no live/alerts.json`), which needs
a channel and credentials the loop may not configure.

Status 2026-09-10 20:4x UTC (O-2): **SPY 0DTE credit spreads are the first candidate in this
repository with a real, calibrated gross edge - and they are refused, because the only version that
pays depends on a settlement convention the data cannot price.** Built the 0DTE chain store
(`scripts/odte_data.py`: **1,884 expirations, 2016-01-08..2026-09-10, 5-minute bid/ask both rights,
+/-30 strikes, ~17.8M rows, 125 MB** from Theta), the study (`scripts/sweep_o2.py`) and the
confirmation (`scripts/_o2_confirm.py`); 16 ledger rows under `options/odte_put_spread`. **The
instrument was proved first**: the chain's own slope (`dP/dK`) is a calibrated probability -
realized breach tracks the quoted prob at every delta on both rights and sits **consistently below**
it at **z = -2.7 to -3.8** in six of six cells - which is the variance risk premium measured rather
than assumed, and the reason gross is positive here where O-1/L-1/X-1 had none. **Stage 1, the
pre-registered grid (36 cells, closed at the quote): 0 of 36 pass, every cell negative in every
regime.** Decomposition, as % of the position's own max loss per session: gross **+0.783**, quoted
spread **-1.363**, commission **-0.950**, net **-1.530** - **the mid edge is a third of the cost of
harvesting it**, and on a $355 risk unit IBKR's fee alone exceeds the whole gross. Made as cheap as
the data allows (72 cells, width 0.75-5%, entry 10:00-14:00, with and without commission) the best
net is **+0.30% at t = +0.94 and that is at zero commission**. **Stage 2 is the finding**: a real
0DTE book does not buy back an untouched position, it lets it expire, and modelling exactly that
**flips the sign** - entry time becomes a monotone shelf (**09:35 +0.09 / t 0.19 -> 12:00 +0.685 /
2.09 -> 14:30 +0.907 / 4.32 -> 15:30 +0.684 / 5.20**), the best cell earns **+0.767% of risk at
t = +3.05, positive in 10 of 11 years**, and 3 of 36 cells pass the rule. **The same cells closed at
the quote earn -0.282% at t = -1.16, positive in 3 of 11 years: the entire result is the exit.**
**And the exit does not survive settlement.** SPY settles on the official 16:00 print and is
exercisable against until 17:30 ET, so a barely-OTM close is not a free expiry; charging the quote
unless the close clears the short strike by a buffer walks the result **+0.767 (t 3.05, 2 regimes)
-> +0.583 (2.32, 1) -> +0.445 (1.78, **0**) at 0.10% of spot -> +0.202 (0.81) at 0.20%**. The pin
distribution is why: **the median session closes 0.28% of spot from the short strike** (p25 0.14%,
p10 0.06%, p5 0.03%) and **37.4% close within 0.2% of it**. At ~65 cents of buffer on today's SPY
the trade fails the pre-registered rule outright. **The mandate refuses it a second time**: at the
un-buffered best cell a book earns +0.767% per session per unit of equity at risk, so **3%/day needs
3.9x equity at risk and a defined-risk position posts its risk in full as margin** - ceiling 1.0x,
where the worst session is **-105%**. At a survivable 0.25x the ledger row is CAR 21.5% at a
**60.6% drawdown**, far outside the 35% cap. **Refused and closed; nothing shipped**, no file the
live trader or the daily runner loads was touched, `live/` and the scheduled tasks untouched, rule
(a) owes no replay (new scripts only). Champion unchanged at S-12. **A-5 part 2 ran as the standing
job on the first full session of intraday fills: 32 fills / $1.87M / 100% filled, realized slippage
+2.92 bps (se 1.32) against the shipped 1.50 - |diff|/se = 1.08, not yet 2 se, so `SLIPPAGE_BPS` was
not touched - but it has moved from +1.30 (partial session) to +2.92, i.e. above A-5 part 1's
2.52 bps breakeven; ~6.7 more sessions settle it.** **The owner's 3-10%/day list is now exhausted.**
O-1, O-1b, L-1, X-1 and O-2 have each been measured on the full history and each refused; nothing in
this repository reaches the mandate, and the only edge that survives out of sample is the daily
champion. The binding constraint is now an owner decision, not a missing idea.

Status 2026-09-10 19:3x UTC (X-1): **breadth does not rescue the intraday sleeve - fifty megacaps
carry a cross-sectional spread of +0.36 bps against a 4.70 bps round trip.** Fetched the 40 missing
megacaps (2016-2026, ~1.04M bars each; the Alpaca store is now 60 symbols) and re-derived
`_splits.json` for the union with every pre-existing factor identical. Stage 1, sixteen cells over
2,684 sessions: gross is **positive (momentum) and never above +0.36 bps per leg**, and **no cell
reaches t > 2 in two of three regimes before a cent of cost**; net, 0 of 32. Stage 2 through the
shipped framework, one year per regime: momentum **-$1,681/day (t = -16.9)** and the reversal
control **-$1,786/day (t = -18.8)** - **both signs losing the same amount**, i.e. gross of +$79 and
-$97/day on a $1M book against $1,760/day of costs at 8.07x turnover. Time-of-day residual worth
keeping: **+0.63 bps at 10:30, -0.69 bps (t = -2.80) at 14:30**. **Refused and closed; nothing
shipped**, no file the live trader loads was touched (rule (a) owes no replay). Champion unchanged
at S-12. **The owner's 3-10%/day list is now exhausted except O-2**, which needs options permission:
O-1, L-1 and X-1 have each been measured on ten years of bars and refused, and the only edge in this
repo that survives out of sample is the daily champion.

Status 2026-09-10 17:0x UTC (L-1): **leveraged ETFs do not revert intraday, and the statistic that
said they did was weighted wrong.** Event study on 2016-2026 Alpaca bars for SOXL/SOXS/TQQQ/SQQQ/
UPRO/SPXU (the last four fetched here): fading a `z`-ATR VWAP deviation at the next bar's open earns
**-0.28 to -3.16 gross bps per round trip in all sixteen cells and on all six names**, against a
**6.4-8.2 bps** cost. Through the shipped framework on 2,686 sessions the fade is **-$902/day at
t = -9.45** (three deployable names -$667/-9.02) and the **continuation control loses too**
(-$587/-6.26): 0/3 regimes everywhere. **The keeper is the weighting**: session-equal averaging
made the same study pass 3/3 at +7.09 bps, because `corr(events/session, session mean gross) =
-0.340 at t = -17.5` - a book puts the same notional on every event, so a session earns the sum.
`_l1_reconcile.py` proved the harness and the event study agree per fill (235 round trips,
corr 1.000) before either was believed. **Refused and closed; nothing shipped**, `live/` and the
scheduled tasks untouched, 2026-09-08 replay reproduces the deployed sleeve exactly. Champion
unchanged at S-12. **X-1 is the top open item.**

Status 2026-09-10 16:0x UTC (A-5 part 2): **the first live fills say nothing about slippage and
prove a cost the harness never charged.** The sleeve placed real orders for the first time this
morning. On the partial session (19 fills, $1.11M, 100% fill rate) realized slippage is **+1.30 bps
notional-weighted, se 1.65, against the shipped 1.50 - z = 0.12**, so `SLIPPAGE_BPS` was not
touched. **The reference worry is refuted by direct measurement**: the same 17 fills score +1.10 /
sd **7.55** against the next-bar open and +1.55 / sd **7.13** against the decision close (realized
gap sd 2.16, corr -0.33 with the fill error), even though the whole-store gap sd of 6.20 bps on
this symbol mix predicted the fallback would carry 76% of the variance - **a population noise
estimate does not transfer to the minutes a strategy selects.** What costs precision is the ~10 s
detection latency (median 10 s, worst 13 s), which is mean-zero drift, so only fills buy it:
**166 fills, ~3-4 full sessions**, to resolve the constant against breakeven at 2 se. **What did
land is a missing cost, measured exactly.** IBKR's `commissionReport` matched the harness to
$0.004 on all twelve buys and undercharged all five sells; fitting the excess on notional and
shares reproduces every sell **to the cent**, so the harness omitted the US sell-side regulatory
pass-throughs - **SEC Section 31 $20.60/$1M of proceeds (0.206 bps) and FINRA TAF $0.000198/share**
- now charged in `intraday_common.commission()` when `shares < 0` (measured commission 0.501 bps
against 0.434 modelled; 0.501 after). Paired 260-session control at A-5's parameters: costs/day
**$1,025 -> $1,078**, $/day **$610 -> $557**, CAR **15.3% -> 14.0%**, Sharpe **0.689 -> 0.640**,
trades 12,743 -> 12,742. **Breakeven slippage is therefore 2.52 bps, not 2.62**, the deployed
half-size sleeve pays ~$22/day of it, and the 2,686-session Alpaca result moves from -$697/day to
roughly -$740/day: every number moves against the sleeve, which is where omitted costs always
move. **Two no-ops proved**: the old-model control reproduces A-5's ledger row to every digit,
which incidentally proves the participation-cap path an interrupted session left uncommitted in
`intraday_backtest.py` is **bit-for-bit inert at `part_cap = 0.0`** (committed here on that
evidence; A-11 itself is still unrun), and the rule-(a) replay of 2026-09-08 against the current
trader gives identical 34 trades / 368 decisions / flat at close under both models, differing only
by the $22 of fees. `scripts/slippage_report.py` gains the two-reference split (never pooled),
per-fill pricing under both references, fill latency, a fills-to-breakeven power line and
`--refresh`. Nothing else shipped: `live/intraday_config.json`, `live/APPROVED_PAPER.md` and the
scheduled tasks were not touched, and the champion is unchanged at S-12. **Note for the next
iteration**: the owner's midday mandate (3-10%/day; priority O-1 / L-1 / X-1 / O-2) landed at
11:40 ET while this ran, and it judges every candidate "with real costs" - so L-1 and X-1 must be
run against the corrected model from their first backtest, not compared to pre-fix numbers.

Status 2026-09-10 12:5x UTC (O-1b): **the implied-vol size dial is a leverage dial, and it pays 50%
more turnover for it. Refused; nothing shipped.** O-1's deferred half, on the daily champion, where
the level is positive. `signals.py` gains `iv_regime_series` / `iv_size_factor` and five `Params`
fields (`iv_scale_power`, default **0.0 = off**, `iv_scale_field`, `iv_scale_window`,
`iv_scale_min/max`), `main.py` the matching `S1_IV_SCALE_*` overrides, and
`scripts/iv_regime.py --export-csv` mirrors the parquet to `data/options/iv_regime.csv` (the
LEAN-side Python 3.11 has no pyarrow). The factor multiplies the **final** weights - after the
margin-budget shrink, because with a flat budget the vol target is inert upwards (S-8) - and reads
only store rows dated **strictly before** the last price bar, so it is causal under either harness's
timestamp convention. Covered period **2017-04-03..2026-09-04** (uncovered days get factor 1.0 and
run as the champion, so a full-period run can only move the verdict toward the control). Against its
own control (2,951 orders / $13,090 / CAR 29.456% / Sharpe 1.025 / DD 22.6% / std 0.179 / PSR 37.7%):
**the inverse reading, the one the residual motivates, is the losing side** - power +1.0 gives
27.692% / 0.950 / 21.1% / std **0.182** / PSR 29.5%, worse on return *and* carrying more vol than
the control. The winning side is the direct one (lever up when IV is high, i.e. A-10's
long-volatility reading on a book that is paid for it), and its response is a **pure vol dial**:
std 0.179 -> 0.189 -> 0.198 -> 0.204 monotone in the tilt, CAR 29.46 / 31.38 / 31.71 / 29.77 rolling
over, Sharpe peaking at -0.5 (1.050) and decaying to 0.939. **The benchmark settles it**: degenerate
the clip into a constant gross-up and the IV timing is gone while the gross is identical - CONSTANT
1.056 scores 3,027 orders / $14,556 / **31.107% / 1.040 / 23.8% / std 0.189** / 38.9% against the
dial's 4,550 / $17,963 / 31.376% / 1.050 / 23.3% / std 0.189 / 40.0%. **At identical realized vol
the dial's entire edge over a dumb constant is +0.27 CAR and +0.010 Sharpe, bought with 50% more
orders and 23% more commission** - one unit of the +/-0.3 CAR path scatter S-13 measured on a
parameter with no mechanism. Two thirds of the raw gain is not timing at all: CONSTANT 1.0198
(the dial's own mean factor) already earns +0.57 CAR. **And the constant needs none of this code**:
`margin_budget` 0.75 -> **0.792** gives 3,039 orders / $14,530 / **31.006% / 1.042 / DD 22.8% /
std 0.188 / PSR 39.1%** - +1.55 CAR over the shipped champion for **+0.2 points of drawdown and 88
extra orders**, against the dial's further +0.37 CAR for +0.5 points and **1,511** extra orders.
**The no-op is proved**: the shipped-defaults
full-period run reproduces **`OrderListHash 5246804e17a67af90028ffceead7d3b3`** with 4,735 orders,
CAR 24.404%, Sharpe 0.921, DD 25.100%, fees $45,695.46 - bit-identical to the champion - so the
IBKR paper runner's path is unchanged and `live/` was not touched. **Do not re-open as a feature or
threshold question**: the only thing implied vol can give a momentum book is the *level* of gross,
and that level is free and turnover-less through `margin_budget`; the 1.6 points of CAR it buys is
a risk-posture decision, now a one-line question in `BLOCKERS.md`. **A-5 part 2 had no input**:
`slippage_report.py` at the top of this iteration still finds no session with live fills (this ran
at 08:3x ET, before today's open). Champion unchanged at S-12; the intraday sleeve was not touched.

Status 2026-09-10 11:4x UTC (O-1): **implied vol forecasts the day this sleeve is paid for, and
that forecast is worth nothing - the sleeve is paid for volatility *surprise*.** New
`scripts/iv_regime.py` builds `data/options/iv_regime.parquet` from Theta EOD greeks (**2,383 days,
2017-01-03..2026-09-09**: SPY front-weekly ATM IV, 25-delta skew, 1w/1m term ratio), new
`scripts/sweep_o1.py` partitions A-10's cached 2,686-session P&L series by the strictly prior-day
gate, and `algorithms/intraday/orb/signal.py` carries `iv_gate` (high/low/off, default off).
**The chain breaks in the middle**: corr(prior-day ATM IV, today's universe range) = **+0.598 at
t = +36.4**, corr(realized range, ORB P&L) = **+0.260 at t = +13.95**, and corr(IV, P&L) =
**-0.030 at t = -1.46** (regimes +0.001 / -0.052 / +0.010). Splitting the range into the part IV
saw coming and the part it did not: the forecast part scores -0.030 / -0.016 / -0.058 against P&L
and the **surprise part +0.351 / +0.292 / +0.299 at t = +18.3 / +14.3 / +15.3**, positive at t > 7
in **nine of nine feature-regime cells**. That is A-9's finding arriving against a real,
market-priced forecast on ten times the sample: what pays is unknowable at entry by construction.
**All six gate cells fail 0/3 regimes**; the best ON side in the sweep is `term_ratio low` at
**+$43/day, t = +0.13**, and the largest separation anywhere (Welch t 2.26, `term_ratio low`
2016-2019, +$636/day) **inverts to -$632/day in 2024-2026**. What does survive is not a gate:
corr(IV, **|P&L|**) = **+0.252 at t = +12.67**, positive in all three regimes for all three
features - implied vol forecasts how *big* the day is, not which way, i.e. a size scaler, which is
worthless on a book whose level is negative and is exactly O-1's deferred half for the *daily*
champion (now carried as **O-1b**). The gate parameter was confirmed in the real backtester on one
year (`scripts/_o1_confirm_2024.py`, three ledger rows: 2024 ORB alone, gate off 252 traded days /
+$524 day / Sharpe 0.62, high 118 / +$452 / 0.62, low 131 / -$23 / 0.02) - it blocks whole
sessions, keeps about half, and fails closed on the 3 uncovered days - but **that year is a wiring
check, not evidence**: 2024 is a positive year inside a regime that is -$65/day, and the side it
favours is the side the full partition scores worst. **Refused; nothing shipped,
`live/intraday_config.json` untouched**, and the
2026-09-08 replay with the deployed config reproduces A-10 to the digit (34 trades, 368 decisions,
flat at close, P&L -2,280 on 500k) so the ORB edit is a no-op on the live path. **`equity_frac`
held at 0.5, not cut to 0**: the owner's three-way question in `BLOCKERS.md` is still open and its
default (a) exists to feed **A-5 part 2**, which has still had zero live fills (re-checked at the
top of this iteration) and whose first chance is today's 09:25 ET session. **A-10 measured the
level, O-1 measured the conditioner, and there is no twelfth lever on this sleeve.** Champion
unchanged at S-12; the daily sleeve was not touched.

Status 2026-09-10 10:3x UTC (daily review, no experiments run): **the deadline was met and the
second sleeve was disproved in the same 24 hours.** The daily champion filled on IBKR paper at
15:46 ET on 2026-09-09 (TQQQ 3,700 @ 71.49, XLE 7,333 @ 65.39, XLK 2,616 @ 187.85, 1.23x gross on
DUT091359), so S-1 -> S-12 is now a live paper strategy and the 2026-09-10 objective is closed.
Twelve A-track iterations and 217 ledger rows later the intraday sleeve is measured at **-$697/day,
t = -3.01 on 2,686 sessions**; the late-day fade is dropped and `equity_frac` held at 0.5.
**Order of work for the next 24 hours: (1) A-5 part 2 after today's close** - today is the first
session that places real intraday orders and `scripts/slippage_report.py` is the only instrument
that can move the 1.5 bps constant that owns the sleeve's sign; **(2) O-1**, judged on the Alpaca
regimes; (3) per-session ops. Two ops items found in the review: IB Gateway's port 4002 is down
nightly ~02:15-02:45 ET and was open again at 06:30, so an off-hours connect failure is expected,
not the old blocker returning; and phone alerts are **broken** - `notify_failed`
(`TELEGRAM_BOT_TOKEN` missing) on 2026-09-09, so a live failure is invisible outside the logs.
Full review in `research/reports/2026-09-10.md`. Champion unchanged at S-12.

Status 2026-09-10 08:5x UTC (A-10): **with 2,686 sessions the sleeve is not
unproven, it is negative - and the late-day fade is refused at 7 sigma.** A-4 said ~2,120 sessions
were needed and unreachable; the Alpaca SIP store has 2,686 (2016-01-04..2026-09-09, same 16
names). New `scripts/sweep_a10.py` runs the deployed mix and each sub-strategy alone as one
backtest per calendar year from a fresh $1M book, pooled into three a-priori regimes.
**A cost-model bug had to be fixed first**: the store is split-adjusted, so a dollar position
bought up to 40x the shares really bought and the per-share commission pinned to its 1% cap
($1,523/day on 7 trades/day in a 2016 smoke test, $222 after the fix), while SOXS's 8.3e-08
cumulative factor put its adjusted 2016 price in the tens of millions and the whole-share floor
sized every early SOXS position to **zero**. Fixed in shared code - `alpaca_data.py --splits`
derives the factor by asking Alpaca for the same daily bars raw and adjusted and writes
`_splits.json`, `intraday_common.share_scale()` reads it, `commission()` takes a scale, and the
whole-share floor is applied at the price really quoted. **The raw IBKR store has every factor
1.0 and the regression proves the no-op**: A-5's control reproduces to the digit (260 sessions,
CAR 15.343%, Sharpe 0.689, $610/day, 12,743 fills). The result: mix **-$697/day at t = -3.01**
over 2,686 sessions, negative in all three regimes (**-$579 / t -2.42**, **-$1,127 / t -2.92**,
-$231 / t -0.37), positive in 4 of 11 years and no year at |t| = 1. **The only profitable window
in eleven years is the 261 sessions the parameters were fitted on, and even there t = +0.32.**
**The late-day fade alone is -$468/day at t = -7.38**, negative in every regime separately and on
the fitted window too - A-4 kept it on 260 IBKR sessions at t = +0.27 because that sample could
not see a 7-sigma effect. **A-4's mechanism survives with power**: corr(daily P&L, universe range)
**+0.202 at t = +10.70**, positive in all three regimes. **Shipped** after a passed 2026-09-08
replay (34 trades, 368 decisions, flat at close): `alloc.late_momo` **1.0 -> 0.0** in
`live/intraday_config.json` - refused at 7 sigma OOS and free in sample (ORB alone earns +$322/day
on the fitted window against the mix's +$302). **`equity_frac` held at 0.5**, not restored: what
is left is ORB alone at -$289/day, t = -1.17. Whether the sleeve should trade paper capital at all
is now the top question in `BLOCKERS.md`. **O-1 (options-implied regime gating) is the new top
item** - it is the only untried idea whose mechanism this study confirms; the participation cap
A-5 found is demoted, because it can only make a losing book smaller. Champion unchanged at S-12;
the daily sleeve was not touched.

Status 2026-09-10 06:3x UTC (A-5 part 1): **the sleeve breaks even at 2.6 bps of
slippage and is charged 1.5, so the cost constant owns its sign.** A-5's live-fill measurement
needs a session that placed orders and there is none yet, so this iteration priced the cost model
from the store instead. New `scripts/sweep_a5.py` (`spread` / `impact` / `breakeven`), a
backtest-only `--slippage-bps` override, and `scripts/slippage_report.py` - the live-fill
comparison, finished and self-tested, idle until tonight. Control reproduces A-4 exactly (260
sessions, CAR 15.3%, Sharpe 0.689, $610/day, 12,743 fills). **P&L is linear in the constant to
$73/day**: 0 bps -> **$1,671/day, CAR 41.9%, Sharpe 1.51**; 1.5 bps (shipped) -> $610, 15.3%,
0.69; 3.0 bps -> **-$231, -5.8%, -0.11**. The sleeve turns over **$5.46M/day on a $1M book, 5.5x
equity a day**, so one bp is $546/day and the whole modelled edge is **1.1 bps wide**; breakeven
is **2.64 bps from the runs, 2.62 analytically**. **The holdout's breakeven is -0.02 bps**: on the
77 sessions no A-track parameter ever saw, gross P&L *before any slippage* is **-$11/day**, so
A-4's -$813/day is not a weaker regime, it is **no gross edge at all** paying $802/day of costs.
Bounding the constant from bars fails on purpose: Roll and Corwin-Schultz give a
notional-weighted half-spread of **2.65 bps** - sitting exactly on the breakeven - but
`corr(estimate, 1-minute return std) = +0.906` with a CS/vol ratio of 0.32-0.65, so **the
estimator is measuring volatility, not spread**; the hard floor (half a tick) is 0.36 bps, so all
that is honest is **half-spread ∈ [0.36, 2.65] against a 2.62 breakeven** - only fills settle it.
What the bars *do* refute is participation: over 12,743 fills the order is **median 1.03%, p90
5.55%, p99 26.1% and at worst 199% of the volume of the minute it fills in**, concentrated in
**SMCI / SOXS / COIN / MSTR, which carry 30% of traded notional** at p90 6-19% against the
megacaps' 0.2-0.9%. That is a modelling defect, not a lever, so A-4's power argument does not
excuse it - it is the new top item **A-10**. The harness's fill convention is *not* hiding a cost:
the decision-close-to-next-open gap is **-0.12 bps (se 0.04)**, so the all-in modelled cost of a
fill is 1.50 + 0.38 commission = **1.76 bps**. **Nothing shipped**: `SLIPPAGE_BPS` stays 1.5,
`live/intraday_config.json` untouched, and a 2026-09-08 replay passed (46 trades, flat at close)
because three logging fields were added to the trader for the live report. Champion unchanged at
S-12; the daily sleeve was not touched.

Status 2026-09-10 05:2x UTC (A-9 iteration): **the day's range pays, and the half of it
that is knowable at entry pays nothing.** A-4 said ORB's P&L rides the same-day range; A-9 asked
whether the opening range, which closes before the first entry, can be used as the causal handle.
Decomposing each session's universe mean range into the opening 15 minutes and the residual:
ORB's daily P&L correlates **+0.568 (t = +11.09)** with the realized full-day range and
**+0.665 (t = +14.29)** with the residual - stable in both halves - but only **+0.080 (t = +1.28)**
with the opening range, and **-0.009** on the holdout, even though the opening range predicts the
day's range at corr +0.626. The reason is mechanical: **ORB's stop is the range midpoint, so the
width is the risk unit** - a wide opening scales the win and the loss together, and what pays is
the range added *after* entry. **A-9's premise is refused at the root.** The grid proves it in the
sharpest way the A-track has produced: with `range_atr_min` / `range_atr_max` added to the ORB
module (defaults 0 = off, control reproducing A-4 to the digit), **every "keep the wide openings"
cell beats the control on the tuning window and loses on the holdout, and every "keep the narrow
openings" cell does the exact opposite.** `min 3.6` reaches **TUNE Sharpe 2.17 / CAR 49.7%** - the
best number this sleeve has ever produced - against **HOLD -1.19 / -20.5%**; its mirror `max 3.6`
earns **HOLD 1.46** against **TUNE -1.27**. Paired against the control over all 260 sessions **no
cell in the eleven reaches |t| = 1.6**, and in the deployed mix the same cells give 2.32 and 2.53
tuning-window Sharpe against -1.96 and -1.27 on the holdout (paired t +0.92, +0.62). The lever
does not select trades, it selects which half of the sample you are looking at. **Refused; nothing
shipped, `live/intraday_config.json` untouched, both gates stay 0**, and a 2026-09-08 replay was
run anyway because the live trader loads this module (46 trades, flat at close, identical to the
A-2 replay). New `scripts/sweep_a9.py` and an opt-in `collect_trades` in the backtester. **The
durable lesson is that the holdout is now doing real work**: on the 183-session window every prior
A-track iteration used, `min 3.6` would have shipped. **A-5 is the new top item** - A-9 was the
last lever with a stated mechanism, A-8 stays parked, and measured slippage is the one number in
the harness that is still a guess. Champion unchanged at S-12; the daily sleeve was not touched.

Status 2026-09-10 02:2x UTC (A-4 iteration): **the minute store is now 260 sessions,
and on them the intraday sleeve's return is not distinguishable from zero.** The store was
extended to 12 months (2025-08-26..2026-09-08) and repaired - `intraday_data.py` was ending each
request at the wall-clock time of the run, so IBKR truncated the newest session of every window
into a partial day; `snap_after_close`, `--repair` and `truncated_sessions()` fix it, and all 16
symbols now hold 261 clean sessions with only the two real NYSE half days short. Re-running
A-7's control on the repaired bars moves it a tenth of a point, so **every prior A-track
conclusion stands**. The 77 sessions before 2025-12-15 are a true **holdout** - no A-track
parameter has ever seen them - and the deployed mix **loses -$813/day on them** (CAR -19.1%,
Sharpe -0.73) against +$1,289/day on the 183 it was fitted to. **But nothing here is
measurable**: Welch t between the halves is **-0.96** for the mix, and a single run over all 260
sessions earns $610/day at std $16,222 - net +15.87%, **CAR 15.3%, Sharpe 0.69, t = +0.61, 95%
CI on the year's total P&L [-$354k, +$671k]** around $158.6k, on 49.0 trades/day and $1,025/day
of costs. **The power calculation is the result**: at Sharpe
0.69 you need `(2/0.69)^2` years = **~8.4 years / 2,120 sessions** to reject zero at 2 sigma,
so no achievable backtest sample can validate this sleeve, and A-1/A-2/A-7 - all hunting
differences *smaller* than the base rate - were never capable of answering. The **late-day fade
is worth $1,099 over 260 sessions** ($4/day on $232/day of costs; marginal inside the mix +$65/day,
t = +0.27), so A-6 shipped it on the tuning window alone. What *is* measurable, at **t = +10.25**,
is that the sleeve is a **long-volatility position**: daily P&L correlates +0.538 with the
universe's same-day range, the holdout is the calmer window (mean range 3.78% vs 4.44%), and the
negative holdout is therefore a **regime, not decay**. Prior-day range does not predict it
(t = +0.47), but the **opening range's width relative to ATR14 is known at ORB's entry and is
never used** (ORB gates on volume only) - that is **A-9, the new top item**, the one lever with
a mechanism behind it. **Nothing shipped; `live/intraday_config.json` untouched**, so the trader
is byte-identical and no replay was owed - dropping the late fade improves the holdout but costs
$16.8k over the full store at t = +0.27, which is not the OOS improvement rule (c) requires.
The unmeasurability of the sleeve is now a one-line question to the owner in `BLOCKERS.md`.
Champion unchanged at S-12; the daily sleeve was not touched.

Status 2026-09-09 23:0x UTC (A-7 iteration): **the framework risk limits are a tail
dial with no price, and the sample is now the binding constraint.** Fifteen cells on the usual
9-month window (2025-12-15..2026-09-08, split 2026-06-15, 124/59 sessions), deployed mix, via a
new backtest-only `--risk` override and `scripts/sweep_a7.py`. The daily loss limit does exactly
one thing and does it monotonically: the worst day walks **-20.5k (1.5%) -> -30.3k (2.5%,
shipped) -> -57.0k (off)**, with a 0.15-0.38 point overshoot past nominal because the breach is
marked to close and the flatten pays spread. It does **nothing measurable to return**: total P&L
is 200.5k at 2.0% and 243.1k at 1.5% with the shipped 2.5% at 221.2k, and **paired against the
control every cell in the whole sweep scores |t| <= 1.06** on 183 daily returns. A-7's stated
worry is refused - **stopping early is free**: on halted sessions the halted book beat the
limit-off run on the same dates at every limit except 2.0% (saving $453/halt at 1.5%, which
fires on 22% of sessions, and $8,497/halt at 3.0%). `PER_SYMBOL_HARD_CAP` is **inert**: 0.12,
0.15, 0.20 and 0.25 are bit-identical, so the mix never asks for more than ~0.12 of equity in one
name, and below 0.12 the cap is a size dial (0.10 is a spike on IS Sharpe with losing neighbours,
refused). Gross saturates at the deployed 1.5; 2.0 buys +2.7% of P&L outside A-3's stated range
and is an owner decision. **Nothing shipped; no constant changed, `live/intraday_config.json`
untouched, so the trader is byte-identical and no replay was owed.** The durable conclusion is
that with A-1, A-2 and A-7 all negative, **the sleeve needs more sessions, not more levers** -
one standard error on the 183-session total is $229.6k against a $221.2k total. **A-4 (extend
the minute store to 12 months) is now the top open item**, ahead of A-8, because A-8 would be
judged with the same instrument that just failed to resolve a 20% swing in P&L. Champion
unchanged at S-12; the daily sleeve was not touched.

Status 2026-09-09 21:3x UTC (A-1 iteration): **the VWAP fade can be repaired, and it
still is not worth capital.** Eleven standalone variants and six sleeve runs on the 9-month
window (2025-12-15..2026-09-08, split 2026-06-15, 124/59 sessions). Only one of A-1's five
levers is a mechanism: the **session-trend filter** takes the module from IS -56.0 / OOS -10.1
to -11.9 / +16.9 at a third of the turnover, and **the inverted filter fails as predicted**
(-46.3 / -5.5), so the fade was losing by fighting trend days rather than by mistuning. Min
hold, a midday blackout and a 5-minute cadence only shrink the position; range expansion leaves
0.8 trades/day. The only cell positive in both halves is +0.8 / +11.3, and Sharpe 0.13 on 124
sessions is zero. **At the sleeve it is a wash bought with turnover**: three fade cells at
alloc 0.25-0.5 give total P&L $216.9-225.2k over 183 sessions against the deployed $221.2k,
with IS CAR falling monotonically in the allocation and IS drawdown 1.2-3.9 points wider, for
22-34% more trades per day. **Refused; `vwap_trend` alloc stays 0 and `live/intraday_config.json`
was not touched.** A-1 is closed. Champion unchanged at S-12; the daily sleeve was not touched.
**A-7 is now the top open item** - A-1 and A-2 together say the signal layer is spent and the
framework constants in `scripts/intraday_common.py` are the untested surface.

Status 2026-09-09 19:0x UTC (A-2 iteration): **the ORB tail does not come off for
free.** Nine variants on the 9-month window (2025-12-15..2026-09-08, split 2026-06-15, 124/59
sessions): the response to stop distance is **monotone and rotates return between the halves**
rather than adding any - midpoint (shipped) 35.7 IS / 10.7 OOS, +4x ATR backstop 31.4 / 19.3,
+3x 21.5 / 26.5, pure 1.5x ATR -12.3 / 43.1, with the two-half mean roughly conserved. The
worst day and the loss-limit days only fall materially at a stop tight enough to zero the
in-sample return (pure 1.0x ATR: worst -33.9k -> -21.4k, loss-limit days 0/0, IS CAR -0.3%),
so **A-2's stated hypothesis - cut the tail, keep the return - is refused**. Scale-out at 1.5R,
a 30-minute range and a 1.6x volume filter all lose in both halves. What shipped is the shelf
point on that frontier: `disaster_atr=4.0` on ORB in `live/intraday_config.json` (sleeve mix
IS 27.2/1.10 -> 24.2/1.01, OOS 36.2/1.24 -> 55.3/1.73, worst day flat, one fewer loss-limit
day), with a 2026-09-08 replay passed before the write. The ORB module now carries every lever
as a parameter and the control run reproduces A-6 to the digit. **Champion unchanged at S-12**;
the daily sleeve was not touched. Next is A-1, then A-7 (the tail is a framework-constant
question now, not a signal one).

Status 2026-09-09 16:0x UTC (D-2 iteration): **the intraday data blocker is gone for
SPY.** The 10141 disclaimer has been accepted - `paper_trade.py --check` answers on account
`DUT091359` ($1,000,344 net liq, no positions) - so D-2 became the top item and shipped:
`scripts/fetch_minute.py` pulls IBKR 1-minute TRADES bars and writes LEAN minute files, paced
for IBKR's 60-per-10-minutes rule, resumable by month chunk, `clientId` 31. **SPY 2020-01-02
.. 2026-09-08 is complete and validated: 1,679 sessions, 652,650 bars, 0 missing against the
daily calendar, 0 truncated, 0 clamped, 14 MB.** The acceptance test is a LEAN run
(`algorithms/d2_minute_smoke`, run `20260909T160005Z`) rather than a file check, because D-1's
worst bug was a file that passed structural validation and made LEAN return zero bars silently;
**all seven checks PASS** and LEAN's bar count matches the writer's exactly. One bug found and
fixed, worth remembering: `durationStr="1 M"` ending on the month's last day starts *after*
the first session's close, so IBKR silently drops **the first session of every month** - ~5% of
the sample, invisible because every session that survives is a complete 390 bars. Chunks are
now `5 W` with the overlap filtered back. Two durable facts: minute and daily closes agree to a
median 0.007%, but diverge up to ~1% on violent days (COVID, April 2025) because the daily
close is the **auction print** and the last minute bar is not - so **S-2 must model the 16:00
auction, not assume a 15:59 fill**; and IBKR serves ~260-790 bars/s, making a five-symbol
backfill a multi-hour job, which is why only SPY was completed. Champion unchanged at S-12.
**S-2 is now the top open item.**

Note for whoever takes S-2: a parallel session is building an intraday harness outside LEAN
(`scripts/intraday_backtest.py`, `algorithms/intraday/{orb,vwap_trend,late_momo,gap_fade}`)
and its ledger entries from 2026-09-09 15:4x-16:0x all split IS/OOS at 2026-08-15 - a ~30-day
sample, i.e. the Yahoo 1-minute cap. **That constraint is now lifted**: those signals can be
re-run against 6.7 years of SPY instead of one month, which is the difference between a
sample that can reject a hypothesis and one that cannot. Reconcile the two harnesses before
promoting anything from either - LEAN decides, per the S-10 methodology finding.

Status 2026-09-09 14:0x UTC (I-1 iteration): **the pre-deploy gate is built, and it
caught a real bug in the runner.** Gateway is up but the API is still refused by 10141, so
instead of a sleeve experiment this iteration finished I-1's last unbuilt piece:
`scripts/compare_orders.py`, which walks LEAN's own bars and hands *identical* inputs to
`main.py:submit_targets` and `paper_trade.py:plan_orders`, diffing the two order lists. Any
difference is therefore execution-layer by construction, not data or signal. **It failed on
first run**: the runner banded orders at a flat `MIN_NOTIONAL = $200` while the backtest bands
at `0.01 x equity` ($1,000 at $100k, $24,000 by the end of the sample), so the runner would
have placed **9,196 orders against the backtest's 4,653** and agreed on only **36.6%** of
decision dates - all 4,543 divergences the same shape, the runner sending small drift
adjustments LEAN bands out. These are exactly the orders S-13 measured as return-neutral, so
the paper account was about to pay a spread on ~4,500 orders with no return in them and
underperform its own backtest for a reason nothing would have surfaced. Fixed
(`max(MIN_NOTIONAL, MIN_ORDER_VALUE * net_liq)`, `MIN_ORDER_VALUE = 0.01` tracking `main.py`);
the gate now passes **3,689 / 3,689 dates with identical order counts**, and fails with exit 1
on a deliberately mismatched band, so it discriminates. **Nothing under `algorithms/` was
touched**, so `OrderListHash 5246804e17a67af90028ffceead7d3b3` stands unchanged and no
rebaselining run was needed. Champion unchanged at S-12.

Status 2026-09-09 13:40 UTC (daily review, no experiments run): **the Gateway blocker moved,
and it is now one dialog box.** Port 4002 is open and answering for the first time - Gateway is
running and logged in - but the API handshake is refused with `Error 10141: Paper trading
disclaimer must first be accepted for API connection`. That is a one-time tick-box inside
Gateway (Configure -> Settings -> API -> Settings), not work on this side, and it is the only
thing between the repo and tomorrow's deadline. Re-probe with `paper_trade.py --check` at the
top of every iteration; the moment it clears, **I-1 is the top item and everything else waits**,
with D-2 immediately behind it on the same connection. Full review in
`research/reports/2026-09-09.md`. If the API stays blocked, do **not** hunt for another lever on
the ETF-9 sleeve - S-11 and S-13 measured that there are none left cheaply; the useful offline
work is S-5 harness scaffolding and generalizing `sweep_s1.py` off S-1 (E-2's deferred half).

Status 2026-09-09: **S-13 closed negatively - the champion stands at S-12.** The
execution no-trade band (`min_order_value`, pinned at 0.01 since S-1 and never swept) was
tested at 0.015/0.02/0.03/0.05/0.08 to win back the commission S-12 spent. It cannot be won
back, because **there is nothing to win**: the response is non-monotone and flat, with CAR
walking 24.40 -> 24.35 -> 24.54 -> 24.34 -> 23.92 -> 24.47 across a factor of eight in the
band and a factor of 2.7 in order count. The 0.02 cell beats the champion and `evaluate.py`
says **BEATS champion**, and it was **refused** on the shelf-not-spike rule - both its
neighbours lose, so its +0.14 CAR is inside the region's own scatter. Nothing shipped;
`OrderListHash 5246804e17a67af90028ffceead7d3b3` is unchanged and I-1 needs no rebaselining.
The durable finding is the flatness: **~3,000 of the champion's 4,735 orders (63%) are
return-neutral**, free to remove in backtest and strictly *better* to remove live, where the
unmodelled spread is paid per order. That is a live-execution decision and is now a one-line
question in `BLOCKERS.md`. Ports 4002 and 7497 checked again at the top of this iteration:
both still closed.

Status 2026-09-09: **S-12 has promoted a new champion** - the same signal, but the
exposure budget is now split between the three winners by **1/sigma on their own trailing
one-month vol** instead of 1/N: CAR 23.61% -> **24.40%**, Sharpe 0.874 -> **0.921**, drawdown
25.9% -> **25.1%**, PSR 17.7% -> **23.0%**, at 84% more orders and $8.3k more commission. It is
a shelf in both dimensions (vol windows 20/21/30 all win; the tilt is monotone in strength) and
21 sessions is the a-priori one trading month inside it, not the argmax. IS 19.18%/0.884/25.1%
beats S-10 on all three; OOS 30.86%/0.985/22.6% wins on Sharpe and is flat on CAR, so the gain
is an in-sample-half gain. New order list
**`OrderListHash 5246804e17a67af90028ffceead7d3b3`**, and I-1's pre-deploy comparison must be
made against that hash, not `ff4a7cbaaf6e36e58ace2b82ab216bdf`. Ports 4002 and 7497 were checked
again at the top of this iteration and are both still closed, so I-1/D-2/S-2 remain blocked.
**With the allocation step now spent, this sleeve has no cheap levers left**: what remains
inside a three-name ETF book needs breadth (correlation-aware weights want more than nine
names), so the next real gains are still S-2 and D-2 behind the Gateway login.

Status 2026-09-08: **S-11 closed negatively - the champion stood at S-10.** Every
whipsaw control (hysteresis, minimum holding period, rank persistence) trades return for
drawdown roughly in proportion, so the champion's turnover is *paid for*: its rotation is
signal, not noise. What the iteration does leave behind is a priced frontier - `min_hold=10`
plus `margin_budget=0.85` earns 25.07% CAR at 25.7% drawdown (champion 23.61% at 25.9%) for
0.013 of Sharpe - which is now a one-line question to the human in `BLOCKERS.md`. Signal work
that adds return without adding turnover has therefore run out of cheap moves on this sleeve;
the next real gains are a second uncorrelated sleeve (S-2/S-5) and intraday data (D-2), and
both of those, like I-1, wait on the IB Gateway login.

Status 2026-09-08: **S-10 has promoted a new champion** - S-9 with the 120- and 252-day
momentum windows ending one trading week before the decision bar: CAR 20.9% -> **23.6%**,
Sharpe 0.78 -> **0.87**, drawdown 28.9% -> **25.9%**, at 10% fewer orders, beating the old
champion on both sub-periods. New order list:
**`OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf`**, and I-1's pre-deploy comparison must now
be made against that hash, not `b763e292cb0eb9a2c81af5739188d437`. The remaining gate is still
I-1, blocked on IB Gateway being logged in on this machine (see `research/BLOCKERS.md`); the
runner is built and re-verified `--mock --dry-run` against the new signal.

Three constraints stay measured rather than assumed: single-name sleeves are capped because the
pool on disk is a 2026 survivor list, leaving the ETF-9 sleeve as the only honest universe here
(S-7, D-3); the 40-60% volatility mandate is **unreachable** under the 35% drawdown limit on
that sleeve, at any size, by any of the four levers S-8 tried; and a daily-turnover book on this
$100k account pays ~2.1bps per unit of turnover in commission alone, which is more than the
whole gross edge S-3 could find. The first two are decisions for the human in `BLOCKERS.md`.
S-9 and S-10 are the only results to move the champion *without* spending more turnover, which
is the only kind of gain that cost floor cannot tax away - so signal work, not sizing work, is
where the next iteration should look too.

One methodology change, from S-10: **`sweep_s1.py` and LEAN now disagree in sign**, not only in
magnitude - the sweep rejected the skip lever that LEAN promoted, and inverted its drawdown
ranking. A sweep rejection is therefore grounds for one LEAN confirmation run, not for closing
an idea; the sweep is a cheap generator of candidates, and only LEAN decides.

## Open (highest value first)

- **C-7 (found by `critic` 2026-09-13 in C-6, fix belongs to `eng`): the suite proves the runners
  through a path the scheduler does not have, so "the deployed command starts" is untested.**
  C-6 found `scripts/paper_trade.py` unable to import for 83 minutes across two commits
  (`c1fc9b1` added `from quant_brain...` above the sys.path guard that was already in the file),
  while `pytest tests/` stayed green at 1,221 tests the whole time - because `tests/conftest.py`
  inserts `REPO` on `sys.path` and the scheduled task does not. The import defect is **fixed**
  (C-6, gate re-run at 3,689/3,689); the **hole that hid it is not**. Add a `runner`-marked test
  that launches `paper_trade.py` and `intraday_trader.py` as **subprocesses**, with the
  scheduler's own interpreter and working directory and **no conftest path help**, asserting
  `--help` exits 0. Cheap (one file, no data), and it converts a class of outage that currently
  needs a critic to notice into a gate failure at 09:25. Note for whoever takes it: the assertion
  must be on a *subprocess*, since an in-process import inherits pytest's already-fixed `sys.path`
  and would pass while deployed.

- **S-41 (`daily`, opened by S-40 2026-09-13): ensemble the crisis switch instead of choosing it.**
  S-40 proved no real-time selector can find the shipped `regime_threshold`/`regime_vol_window`
  cell (0 of 11 walk-forward years under two objectives, -1.389/-1.688 CAR points below the grid
  mean, worst drawdown of any book tested at 38.185%), while the **equal-weight blend of all 36
  cells** - which requires no selection at all - carried the best Sharpe (**1.173**) and the lowest
  drawdown (**23.389%**) of every book in S-40's table, beating even the hindsight-shipped cell's
  drawdown on FULL (23.389 vs 23.860) and OOS (23.407 vs 23.855). Build it properly: **average the
  36 cells' target WEIGHTS, not their returns** (S-40's number is a return-average, which is the
  right upper bound but not an implementable book), then price turnover, commission and the
  fractional risk-off boundary it necessarily holds, fully charged in S-22 cell C. The prize is
  not return - it gives up ~0.42 bps/day against the shipped cell on FULL at t -0.98, and the sign
  of that gap flips with the window - it is that the sleeve's single most fragile decision stops
  having to be made. Judge on Sharpe and drawdown against the shipped cell at equal cost, and on
  whether the blended weights are executable at the deployed order sizes. Needs no trading day and
  no owner. **Do not touch `margin_budget`, `target_vol`, `target_exposure` or the drawdown cap.**
  <!-- added by S-40, 2026-09-13 (daily). -->
- **S-42 (`daily`, opened by S-41 2026-09-13): the same ensemble trick on the axes where a CAR
  grid is a fair instrument.** S-41 built the weight-blend of the crisis switch and it failed the
  promotion bar on return while winning on drawdown - but the switch is a RISK dial, so every
  column in that comparison is confounded by the drawdown-for-return trade S-40 corrected S-38 on.
  The clean version of the experiment lives on the axes S-38 labelled FITTED that are *not* risk
  dials (`mom_lookbacks`, `mom_skip`, `rank_persist`, `entry_mode`/`min_momentum`, `top_n`), where
  higher CAR at equal drawdown is unambiguously better and an ensemble has nothing to hide behind.
  Reuse `sweep_s41.py` whole: `sweep_s25.legs_simulate(weights_fn=...)` is in place and clause 1b
  proves weight extraction is bit-identical to the in-loop call, so the work is a new grid and a
  new blend, not new machinery. Pre-register the grid before running it, keep the 36-ish cell count
  so the fractional-boundary arithmetic stays comparable, and carry S-41's clause 3b discipline:
  **every row on the same session count**. Judge fully charged in S-22 cell C against the shipped
  cell AND against the walk-forward selector (S-41 clause 7b's framing - the shipped cell is the
  promotion bar, the selector is the decision bar). Needs no trading day and no owner. **Do not
  touch `margin_budget`, `target_vol`, `target_exposure` or the drawdown cap.**
  <!-- added by S-41, 2026-09-13 (daily). -->

- **S-41 DONE 2026-09-13 (`daily` track; see `research/journal_daily.md`): the ensemble is worth
  having, the sentence it was opened on is not, and the two facts are independent.** New
  `scripts/sweep_s41.py` (7 clauses pre-registered, `results/s41_full.txt`, 21 DIAGNOSTIC rows
  `daily/s41_blend`); one default-inert `weights_fn` on the research harness
  `sweep_s25.legs_simulate` (S-26/S-28/S-30/S-32 precedent, clause 1a re-proves every earlier row
  bit-identical); no LEAN run, `champion.json`, `live/*` and all scheduled tasks untouched, no
  parameter moved. **Clause 1b is the new licence**: the shipped cell's target weights extracted
  day by day and fed back through the same simulator reproduce the deployed book to the digit on
  CAR *and* order count, so a blend of 36 extractions is executed through the deployed rebalance.
  **(a) Weight-averaging and return-averaging are the same book here** - agreement to 0.034 CAR
  points and 0.001 Sharpe on FULL/IS/OOS - because the blended target holds at most 3 names and on
  **86.83%** of sessions holds the *identical name set* as the shipped cell, differing only in
  size. The ensemble is a vote on GROSS, not on which names to own, so there is nothing to net and
  S-40's "36 independent rebalances" upper bound is attained, not approached. **(b) Correction to
  this item's own premise, and the second instance this month of the shape that made S-40 correct
  S-38**: the quoted "best Sharpe 1.173 / lowest drawdown 23.389%" is a **2,684-session** row
  (S-40's 2016-2026 walk-forward span) compared against a **3,689-session** FULL-window 1.159.
  Span-matched (clause 3b) the shipped cell is **1.228** and the blend **1.174** - the blend never
  had the best Sharpe, and the claim is withdrawn. The drawdown half survives only because the
  blend's worst drawdown is the 2020 crash, which lies inside both spans. Reusable rule: **a
  number quoted from a table is a comparison only if the row it is compared against has the same
  session count.** **(c) The verdict on the pre-registered bar is NOT a promotion candidate**:
  fully charged the blend is -1.096 CAR on FULL and -3.924 on OOS (paired t -0.92 / -1.64) to buy
  0.286 / 0.217 points of drawdown, and it trades **1.26x the orders at 0.99x the turnover**
  because gross ratchets in 1/36 steps across a fractional risk-off boundary live on **39.01%** of
  sessions. Executability was never the constraint: **0.002%** of blended target weight falls below
  the 0.01x no-trade band against a 10% bar, and deleting the shipped cell from the grid moves
  Sharpe by <= 0.005. **(d) The result, from clause 7b**: against what a real-time selector
  *actually gets* rather than against a cell S-40 proved unfindable, the blend beats the
  walk-forward CAR selector by **+1.587 CAR / +0.163 Sharpe / -14.858 drawdown points** and the
  Sharpe selector by +1.886 / +0.174 / -14.858. **The blend is not a better cell than the one that
  shipped; it is a better book than choosing a cell** - and the promotion gate compares to the
  incumbent, so the shipped cell keeps its place. Opens **S-42**.
  <!-- added by S-41, 2026-09-13 (daily). -->

- **S-40 DONE 2026-09-13 (`daily` track; see `research/journal_daily.md`): the crisis switch is a
  drawdown instrument that has been read as a return instrument, its shipped cell is unfindable in
  real time, and S-38's classification of its two dials is corrected.** New `scripts/sweep_s40.py`
  (7 clauses pre-registered, `results/s40_full.txt`, 118 DIAGNOSTIC rows `daily/s40_regime`); no
  LEAN run, `champion.json`, `live/*` and all scheduled tasks untouched, no parameter moved.
  Headline: on the joint 6x6 grid the shipped `thr=1.50 win=20` is **rank 1 of 36 on OOS 2020-2026
  (29.124%, 100th pct) and rank 24 of 36 on IS 2012-2019 (16.488%, 36th pct)** - AUD-11 as a single
  cell rather than an aggregate percentile, and the switch is where AUD-11 lives. A walk-forward
  selector seeing only a 31-December backtest picks it in **0 of 11 years** under both a CAR and a
  Sharpe objective and lands **-1.389 / -1.688 below the grid mean** with a 38.185% drawdown, so
  branch (c) fired: real-time selection on this dial is *harmful* and the shipped cell's distance
  above the grid mean is hindsight in full. First end-to-end ablation of `risk_on` since S-1: **off
  is +2.68 CAR at t +0.96 fully charged and +12.9 points of maximum drawdown** (24.037% ->
  36.892%), which the promotion gate refuses on its own terms (`max_drawdown_limit: "35%"` and
  `drawdown_tolerance_points: 1.0`), so the switch stays and nothing ships. **Correction owed to
  S-38**: it classified `regime_threshold` and `regime_vol_window` FITTED, but they trade return
  against drawdown by construction, so a CAR grid over them measures the risk dial doing its job -
  the same trap S-38's own FITTED/RISK-POSTURE split was built to avoid. S-38's **+1.25 to +2.07**
  is therefore biased upward by an unmeasured amount concentrated in those two axes; its *label*
  finding is unaffected and strengthened. Reusable rule: **weak rank information plus an argmax is
  worse than no selection** - IS-to-OOS Spearman across the 36 cells is +0.208 and the IS top-3
  beat the IS bottom-3 by +3.625 CAR points out of sample, yet the IS argmax pays **-2.102** against
  the grid mean, and the argmax is the only cell a selector takes. Opens **S-41**.
  <!-- added by S-40, 2026-09-13 (daily). -->

- **C-3 (found by `critic`, fix belongs to `eng`): the intraday sleeve's 09:25 launch gate is red,
  and the cause is a unit test that reads the machine's free memory.** On the interpreter the
  Windows task actually runs (`pythoncore-3.14-64\python.exe scripts\intraday_launch.py`),
  `--preflight-only` today returns *"INTRADAY preflight FAILED: unit suite failed, not trading"*,
  `1 failed, 614 passed`, and the single failure is
  `tests/test_qb_scheduler.py::test_resolve_workers_respects_a_smaller_request`
  (`assert 1 == 2`, from `9d67bef`). `resolve_workers` clamps through `plan_workers`, which reads
  current commit charge, so the assertion holds only on an idle machine: with a 12-worker sweep
  running it returns 1, idle it returns 2, same commit and interpreter twenty minutes apart. E-5
  made `pytest` exit 1 the one outcome that refuses the launch, and AGENTS.md runs several tracks
  concurrently by design, so an overnight sweep still holding memory at 09:25 ET stops the sleeve
  from trading and logs a reason that points at trading code that is fine. The fix is a one-line
  choice - pin the budget the test asserts against, or drop the environment-dependent assertion -
  plus the general rule that a test which reads the clock, the network or free memory must not sit
  inside a gate that decides whether the account trades. Evidence in `research/journal_critic.md`
  (C-2). **The critic ships nothing, so this is not fixed.**
  <!-- added by C-2, 2026-09-12 (critic). -->

- **C-5a/b/c DONE 2026-09-13 (`daily` track; see `research/journal_daily.md`, S-39).** All three
  fixed in one commit, because C-5a is the script that verifies S-37 and the other two could not
  be checked without repairing it. **C-5a**: `sweep_s37.py` clause 1 re-anchored on the gate's
  call site (`faults = data_faults(`) with a guard, so a source-grep can never again be the thing
  that fails; `--stage a` runs end to end and reproduces clause 2 to the digit. **C-5b**:
  corrected in place in `journal_daily.md` and `journal.md` to **two to four bad prints a year**;
  the MATERIAL verdict is unchanged and was never at risk, because the gate's cost is bounded by
  its false-positive rate (0 of 501 live sessions). **C-5c**: both ends closed -
  `fetch_history_ib` now applies the same date filter `fetch_history_yf` always had, and
  `data_faults` reports `day > prev` under its own message rather than as staleness, which is
  what S-37's "must not double-report" objection was protecting. The finding's own framing was
  incomplete in a way worth carrying: **the one-sidedness was deliberate** -
  `tests/test_paper_dataquality.py:104` asserted `== []` for this exact frame and named
  `fetch_history_ib` as the owner of the fix, which S-37 then did not make, so **a test made the
  assignment permanent**. Six further tests moved onto the live contract (`as_of ==
  previous_session(today)`), which they had been violating by one session and which only passed
  because the clause was one-sided. **Priced before it was closed** (new `scripts/sweep_s39.py`,
  5 clauses, nine names of Alpaca SIP minute bars, six of them fetched for this, all nine priced
  on 2,683 of 2,683 sessions): both books fill at the same real 15:45 print, so the only
  difference is whether the signal saw today's partial bar, and it is worth **-0.049 bps/day at
  t -0.08** fully charged (22.483% vs the deployed 22.602%, agreeing in both halves) **while
  rewriting the order list on 76.7% of sessions for 10.2% more orders** - noise in the last row
  of the ranking window, not fresher information, and the gap widens with the cost model. So it
  was a defect and not a latent clock change, and the pre-registered branch creates **no
  owner-facing option**. **By-product, and it is the durable one: S-19's ~1.9-2.1 CAR points are
  entirely a FILL-MOMENT effect.** S-19 never varied what the signal *reads* - both its rows read
  `close[i-1]` - and S-39's `bound` cell, which hands the signal `close[i]`, a price 15 minutes
  after it decides, still loses at -0.141 bps/day (t -0.24). Two controls make the store
  readable: `partial` fed a flat ratio reproduces `bound` at 0.000e+00, and isolating the fill
  alone shows S-19's `close[i]` stand-in was pessimistic by ~0.39 CAR points against the real
  15:45 print. Gates: `compare_orders.py` 3,689/3,689 at 5,021 orders both sides, full `tests/`
  green on py -3.14 (the launch gate's interpreter), identity exact at 22.192150170492255% /
  5,052. No LEAN run, no ledger row, no strategy parameter touched, `champion.json` and `live/*`
  untouched.
  <!-- closed by S-39, 2026-09-13 (daily). -->

- **C-5a (original text, kept for the pre-registration): `scripts/sweep_s37.py` cannot run on the code
  S-37 shipped, and the stage that breaks carries S-37's headline.** The script defaults to
  `--stage all`; `clause1` slices `scripts/paper_trade.py` as text on the literal
  `"missing = [s for s in universe"`, which S-37's own patch deleted. At HEAD it prints the
  identity and then raises `ValueError: substring not found` (`sweep_s37.py:282`) **before clause 2
  runs** - and clause 2 is the "two bad prints a year" break-even the commit message and
  `journal_daily.md` both quote. `--stage b1/b2/b3/c` still work. C-5 confirmed by bypassing the
  grep that the number itself is fine: all eight clause-2 cells reproduce to the digit. One-line
  fix - anchor on the shipped text, or drop the source-grep in favour of the `ast` walk the same
  function already does four lines above. General rule: a clause that verifies a patch by matching
  the *pre-patch* source text can only ever run once. Evidence in `research/journal_critic.md`
  (C-5). **The critic ships nothing, so this is not fixed.**
  <!-- added by C-5, 2026-09-12 (critic). -->

- **C-5b (original text, kept for the pre-registration): S-37's owner-facing break-even is quoted from
  a cell running at 11x the outage rate the sentence describes.** "The tightest break-even is 2.0
  outages a year" comes from the 1-in-21 cell (11.34 outages/yr). The cell matching the sentence's
  own rate (1-in-252, 0.93/yr) gives **2.6/yr at 2 bp and 3.6/yr at 0 bp**. S-37 defends the
  extrapolation as "the cost per outage is the same size in both"; measured it is **1.50x apart at
  0 bp and 1.33x at 2 bp**, and the headline takes the larger each time. Carrying S-37's own
  five-seed sd through, the matching cell is 2.6/yr with a ±1 sd band of **[1.5, 13.6]**, whose
  upper end is **past S-37's own pre-registered materiality threshold of 12**. The `MATERIAL`
  verdict and the decision both stand - the gate's cost is bounded by its false-positive rate,
  which C-5 measured at 0 of 501 live yfinance sessions, so shipping is right at any outage rate -
  but the sentence should read **"between two and four bad prints a year"**. Reproduce with
  `py -3.11 scripts/verify_c5.py --stage d`. **The critic ships nothing, so this is not fixed.**
  <!-- added by C-5, 2026-09-12 (critic). -->

- **C-5c (original text, kept for the pre-registration): the S-37 data gate is one-sided, and the side
  it misses is the one `--history ib` produces by construction.** `data_faults` tests
  `day < prev` only, so a frame ending on **today's unfinished session passes clean**. The two
  history sources sit on one line of `main()`: `fetch_history_yf` drops today's bar
  (`closes.index < today`) and `fetch_history_ib` applies **no date filter at all**, so
  `--history ib` at 15:45 ET returns today's partial bar, it becomes `as_of`, and the signal ranks
  and sizes on a mid-session print as if it were a close - through the gate that exists to stop
  that. The deployed task passes no arguments, so this is **latent, not live**. Fix is a symmetric
  clause (`day > prev` is equally a fault) or a date filter in `fetch_history_ib` matching the
  yfinance one. Reproduce with `py -3.11 scripts/verify_c5.py --stage b`.
  <!-- added by C-5, 2026-09-12 (critic). -->

- **C-5d (found by `critic`, fix belongs to `eng`/`ops`): the `foreign` positions filter in
  `scripts/paper_trade.py` inverts its own stated intent and reintroduces the TQQQ orphan the
  commit that added it was written to fix.** `foreign = {... if s in _INTRADAY_UNIVERSE}` then
  `if foreign: positions = {... if s in universe}` (`162083e`, `ops`). Retired names get a zero
  target **only while the intraday sleeve is flat**; the moment the sleeve holds anything at 15:45
  the filter drops retired names along with the sleeve's. Reproduced: `{TQQQ: 3227, SPY: 100}`
  keeps TQQQ targetable, and adding one `NVDA: 50` yields `{SPY: 100}` - TQQQ orphaned and never
  sold. Predicate should be `s not in _INTRADAY_UNIVERSE`. Needs a failed 15:40 flatten to fire,
  which is exactly the session on which the daily runner should still clean up. Nothing is orphaned
  today (`live/state/last_run.json` holds XLE/XLK/IWM). Reproduce with
  `py -3.11 scripts/verify_c5.py --stage c`. **The critic ships nothing, so this is not fixed.**
  <!-- added by C-5, 2026-09-12 (critic). -->

- **C-4 (critic): adversarially verify S-24, the pre-open MOO claim** - inherited unchanged from
  C-1's queue, deferred once because A-13 landed after C-1 was written and touched a live-loaded
  file and an owner-facing risk paragraph. Same gate as before: reproduce the control, re-run at a
  pinned window, and require `scripts/compare_orders.py` to still agree on 3,689/3,689 dates.
  Second target after it: **S-29**'s +36.56 bps VIX-removal attribution. Third: finish C-2's
  decomposition of A-13. 2016-2019 is done (fill **+$41.25/day**, nav **-$6.77**, closing to $0.45
  against the measured `all`, which reverses A-13 clause 2 on both defects); what is left is
  2020-2023 and an isolated `atr` cell on 2016-2019 -
  `python scripts/sweep_a13.py --workers 12 --years 2020 2021 2022 2023 --cells control fill nav atr all`
  (back up `results/a13/*.csv` first, the script overwrites them).
  <!-- added by C-2, 2026-09-12 (critic). C-2 itself: A-13's fixes and headline survive five
       attacks and reproduce on committed code and on a second window, but clause 2 credits the
       wrong defect (2016-2019: fill +$41.25/day, nav -$6.77) and clause 4's pre-registered 10%
       threshold fails there at 14.65% while its conclusion survives; the owner-facing "4.7% of the
       account" is 4.7% of the SLEEVE and 1.17% of the account, corrected in BLOCKERS.md. No
       promotion contested, champion.json byte-identical to 9197bd4. Reusable rules: a defect
       measured only where its mechanism cannot act has not been measured; a gate that runs the
       whole unit suite inherits every non-determinism in it. -->

**Reprioritized at the 2026-09-12 daily review, and again after S-30 closed it the same day.**
Twenty-two iterations closed in the previous 24 hours (S-15..S-30, F-1..F-6), one promotion (S-18),
and **both** tracks are now out of mechanisms with a stated premise and a permitted instrument.
S-30 was the last research item with one; what is below it is **two standing measurement jobs and
one ops job**, and the binding constraint on this repository is now unambiguously the **six owner
decisions in `BLOCKERS.md`**, three of which are priced to the basis point and two of which cost
nothing to take. **The Current objective's own instruction applies: say so rather than find a
twelfth lever.**

**Updated after I-2 closed (2026-09-12).** The ops job is done and shipped
(`scripts/session_audit.py`, validated against both live defects of the window), so **the only
open work in this file is the two standing measurement jobs** - A-5 part 2, which is ~4.4 sessions
<!-- amended after S-31 closed, 2026-09-12: still true. S-31 added no item; it re-priced the
     owner's `margin_budget` decision on the deployed, fully-charged book, which is the only kind
     of work left that does not need a trading day or an answer from the owner. When the standing
     jobs cannot advance, THAT is the pattern to repeat: re-price an open owner decision on the
     honest scale rather than open a new research track. -->
<!-- amended after S-32 closed, 2026-09-12: the pattern repeated and paid - S-32 re-priced the
     no-trade band and CLOSED it on its own 2026-09-09 conditional ("not material"), so the owner
     pile is one item lighter without an owner turn. Two of the six decisions are now answered by
     the loop's own numbers rather than waiting on one. The standing jobs remain the only open
     work; both still need a trading day. -->
<!-- amended after S-38 closed, 2026-09-12: S-36 and S-37 both signed off saying the `daily`
     track had no item left that needs no trading day. Both were wrong, and in the same way:
     an item marked "PRICED AND HALF-CLOSED" still has a half. AUD-11's LOWER BOUND clause was
     open, daily-owned, needed neither a trading day nor an owner, and S-38 closed it (+1.25 to
     +2.07 CAR points of selection inflation against S-33's +0.974 floor). Rule that came out
     of it: **before declaring a track out of work, re-read every item marked PRICED,
     HALF-CLOSED or BOUND - a bound is an open item wearing a closed item's label.** NOW the
     daily track's only remaining human-free work is the standing jobs, both of which need a
     trading day. -->

- **A-8 DONE 2026-09-12 (`iterate` track; see `research/journal.md`): REFUSED, 0 of 11 cells -
  the entry window and the time stop are not levers on this sleeve, and the event study pointed
  the wrong way on both ends.** `scripts/sweep_a8.py` (11 pre-registered cells + 1 labelled
  post-hoc, 2,686 Alpaca SIP sessions, 4 batches combined by `--combine`, 36 DIAGNOSTIC ledger
  rows, `results/a8/combined.log`). Control = the deployed config at **-$324/day, t -1.32,
  Sharpe -0.36, DD 69.6%, 34.9 tr/day**; clause 1 holds in decisions (sessions 1,006/1,006/674 and
  trades/day 27.3/39.4/39.1 identical to A-12's control) and is void in P&L because four commits
  changed this harness since A-12 (`f1c9968`, `1311586`, `25d30db`, `9d67bef`) - A-8's control
  agrees with **A-13's** recorded control on 2024-2026 (-133.7 vs -133) rather than A-12's -112.
  **Entry window: dead both ways.** Stage 1 found one positive bucket of six (90-119 min,
  +$43.2/trip, t +2.27, z +3.31 vs pooled -$20.1), and the labelled post-hoc cell that isolates
  it (`win90_119`) produces the **worst regime t on the page (-2.20)** on 21.8 tr/day - a 37%
  turnover cut that buys nothing; `after30/45/60` are 0/3 on clause 2, `before60/90/120` are
  0/3, 0/3, 1/3, and all six fail clause 3. **The one real finding is the time stop**, which the
  trip-level table said to leave alone: the book is **monotone in stop length with no interior
  optimum** (-954 / -340 / -324 / -160 / **+81** $/day at 120 / 180 / 240 / 300 / 368) and
  drawdown falls 95.3 -> 40.2 with it. `stop368` (hold to the 15:38 flatten) is **+$405/day
  paired, t +0.91 / +2.80 / -0.24**, at unchanged turnover (35.1 vs 34.9) and *higher* cost - so
  it is not a trade-reduction artifact, and it is still refused: clause 2 is 1 of 3, the sign
  flips in the newest regime, and +$81/day is 0.2 bps a session at t +0.25. `stop120` is the
  largest statistic in the study at **-$630/day paired, t -5.27**. Nothing shipped;
  `live/intraday_config.json` untouched, no runner-loaded file modified, no replay owed.
  **This was the last A-track item with a stated mechanism and a permitted instrument**, so the
  A-track's answer to the Current objective is the one it asked for: the ORB sleeve cannot be
  validated by moving its windows. **Opened by it: A-14** (below) - the time-stop ordering is the
  only monotone structure this sleeve has produced and it deserves the one test A-8 could not
  give it, an out-of-sample split rather than a three-regime paired table.
- **A-14 DONE 2026-09-13 (`iterate` track; see `research/journal.md`): REFUSED - the time stop is
  NOT pure cost, `stop368` is one regime, and the split test was the wrong instrument to say so.**
  `scripts/sweep_a14.py`, eight pre-registered clauses, **no backtest** (every number off A-8's
  persisted series plus S-29's VIX file), 4 DIAGNOSTIC rows under `intraday/active`, nothing
  shipped so no replay owed. Identity holds on all 14 checks. IS 2016-2023 selects `stop368`
  honestly at **+565.3 $/day, t +2.93**; OOS 2024-2026 is **-76.3 at t -0.24** - but clause 5
  vetoes reading that as a refutation: the OOS half detects only **$625/day at 2 se**, needs
  **939 sessions (3.7 y)** against its 674, and the block-bootstrap CI [-733, +584] contains both
  zero and the IS estimate. **Clause 6 decides it instead, and needs no power**: 91.8% of the
  $1.086M cumulative difference is 2020-2023, the best **27 sessions (top 1%) are 107.8%** of it,
  the **median session is -$225.9**, only **47.4%** of sessions are positive, and dropping the
  best 1% turns +404.3 into **-31.7**. So on the typical session the shipped 240-minute stop is
  mildly helpful and the whole gain is a bet on the next crash. Clause 7 names the mechanism and
  kills it: **+$59 per lagged VIX point at t +2.57** with IS terciles monotone
  (+85.8/+475.7/+1,134.2), against **t +0.56** and unordered terciles out of sample, and the
  VIX-conditional rule earns **+$9.5/day at t +0.04** on the withheld half. **The A-track closes
  on evidence**: A-8 was the last item with a stated mechanism, A-14 was the last question A-8
  left, and the sleeve's best remaining lever is a bet on the next 2020. Only A-5 part 2 stands
  between the loop and the Current objective's "say it cannot be validated" instruction.
  Reusable rule: when a paired mean is positive and its median is negative the mean is a tail
  statistic - quote median, positive-session share and trimmed mean **before** the t.
- **A-14 (original text, kept for the pre-registration): is the time stop pure cost, or is
  `stop368` the
  2020-2023 regime?** A-8's grid is monotone in `time_stop` and the extreme cell turns an
  eleven-year loss into zero at half the drawdown, but its whole significance is one regime
  (2020-2023, paired +$990.7/day at t +2.80) and the newest regime disagrees in sign (-$76.3,
  t -0.24). A-8's decision rule is a three-regime paired test, which cannot tell "pure cost" from
  "one volatile regime" - the honest next test is the harness's own `--split`: fit nothing, and
  ask whether `stop368` beats the control on 2024-01-01 onward after the constant was chosen on
  2016-2023. Cheap (the cells exist on disk: `results/a8/daily_control.csv`,
  `daily_stop300.csv`, `daily_stop368.csv`), needs no new backtest, and it is the only A-track
  question A-8 leaves with a stated mechanism. If it fails, the A-track closes on evidence rather
  than on exhaustion; if it passes, it is still not deployable until the sleeve itself is, because
  clause 4 is about the book and the book is at t +0.25.
- **D-4 DONE 2026-09-12 (`iterate` track; see `research/journal.md`): AUD-16 closed - the IBKR
  minute store had been frozen since 2026-09-11 12:35 ET and could not unfreeze itself, because
  the fetcher wrote a truncated session and then counted it as present.** Full detail under
  **AUD-16** in the audit section below. Headline: `snap_after_close`'s `min(20:00, now)` lands
  inside a live session on **78 of 288** probes across a regular day (**0** after the fix, on all
  three day types), and the count-based skip issued **0 requests for all 16 symbols** while every
  one of them held a 170-175-bar 2026-09-11. Repaired against the live gateway - 16 requests,
  6.1 min, **+3,483 bars**, `store_health` **0 fail / 0 warn** - and the preflight now replays the
  full session. The truncated day was worth **27% of its own trades** to research and a replay of
  **-149,012 against -9,489** to any consumer without E-6's shape guard. Suite **601 pass**, no
  ledger row, nothing under `live/` touched. **This lifts the data-side obstacle the objective
  names**: the execution-matched store can now reach A-5 part 2's end condition, which needs
  trading days rather than another fix. **Next `iterate` audit item that needs no trading day:
  AUD-15** [data] - the IBKR store is split-adjusted but treated as raw, so SOXS/NFLX per-share
  commission is understated up to 100x in IBKR-store backtests; it needs `data/minute/_splits.json`
  written first, which D-4's fetcher can now do without freezing the store. After it, **AUD-17**
  [data] (the LEAN daily store writes adjusted prices as raw with split factor 1) is the same
  defect one store over.
  <!-- AUD-15 closed by D-5 on 2026-09-13; the live next data item is on the D-5 bullet and names
       AUD-17. -->

- **D-5 DONE 2026-09-13 (`iterate` track; see `research/journal.md`): AUD-15 closed - the IBKR
  minute store is split-adjusted, `share_scale` was 1.0 for it, and that understated this sleeve's
  commission by 29.8% of its whole cost line out of 279 of 4,208 symbol-days.** Full detail under
  **AUD-15** in the audit section below. Headline: the IBKR-store book is **-$2,460/day, not
  -$1,924/day** (paired **-536.3 at t -4.08**, costs **+548.3**, Sharpe -3.22 -> -4.65, DD 50.60 ->
  64.70), from **one name** - SOXS, a $3.40 stock on the real tape and a $680 one in the store.
  Premise proven two ways (the store's own step across all three splits in its span, and a
  mixed-basis test the audit did not contain: monthly median IBKR/Alpaca ratio inside
  1.00000..1.00003 for all 16 symbols); table derived from yfinance's split **calendar** and
  agreeing with the Alpaca table on **4,208/4,208** symbol-days; `save_bars` now refuses a
  basis-changing merge (16/16 honest re-saves allowed, 16/16 rebasings caught). Suite 1,203 pass,
  preflight green, and the table is byte-identically inert for `intraday_trader.py --replay`.
  **The audit's ratio (1/200) is right and both of its levels are wrong**: 0.074 -> 14.706
  bps/side, not "1.25 versus ~100", because ~100 is the 1% cap and the cap never binds; it also
  omits a 90-session middle segment and calls NFLX an understatement when it is **over**charged.
  **Next `iterate` data item that needs no trading day: AUD-17** [data] - the LEAN daily store
  writes adjusted prices as raw with split factor 1, which is this defect one store over and on the
  sleeve that actually makes money, so it is worth more than its one-line audit entry suggests;
  `scripts/fetch_data.py` and `sweep_s19.py`'s 1% cap are both in it. **Opened by D-5: A-16**
  (below).
- **A-16 (`iterate`, latent): `intraday_trader.py`'s replay path costs the adjusted store as raw,
  the same defect D-5 just fixed in the harness.** `intraday_trader.py:295` calls
  `commission(q, px)` with no `scale` while reading `data/minute`, so a replay of any session in an
  affected window undercharges it - on SOXS, by 14.63 bps/side. **Unreachable from the deployed
  task**: `intraday_launch.last_session()` always picks the most recent COMPLETE session, which is
  days old at worst, and every factor in the current segment is 1.0 - proven by the replay being
  byte-identical with and without the table (-9,489 / 215 / $2,498 / flat). Left unfixed on purpose:
  the one-line fix edits a runner-loaded file for a path the runner cannot take, so it needs a
  `--replay` / `compare_orders.py` gate spent on a latent defect. Worth doing the next time the
  trader is opened for another reason, and worth doing BEFORE any study that replays a pinned
  historical session through the live code rather than the harness.
  <!-- added by D-5, 2026-09-13 (iterate). -->

- **A-13 DONE 2026-09-12 (`iterate` track; see `research/journal.md`): AUD-21 closed - the harness
  is corrected, the sleeve's eleven-year verdict is not, and the owner has been shown a tail
  $12,551 too small.** Full detail under **AUD-21** in the audit section below. Headline:
  -$344.9/day t -1.41 -> **-$309.6/day t -1.24** on 2,686 sessions (+$35.3 paired, t +0.69, sign
  flipping across all three regimes), 92 backtest stop-outs the live trader would never have taken
  removed, and the worst day widening from -$34,300 to **-$46,850**. Adds no research item and
  closes one audit item. **Next `iterate` audit item that needs no trading day: AUD-16** [data] -
  `scripts/intraday_data.py` cannot extend the store and truncates the current session (all 16
  symbols hold a 170-bar 2026-09-11), which is the thing keeping the execution-matched store from
  reaching A-5 part 2's end condition. **AUD-15** [data] (the IBKR store treated as raw when it is
  split-adjusted, per-share commission understated up to 100x) is the same shape and the larger
  number, but it needs `data/minute/_splits.json` written first.
  <!-- AUD-16 closed by D-4 later the same day; the pointer above is history, the live one is on
       the D-4 bullet and names AUD-15. -->


- **C-2 DONE 2026-09-12 - the slot was spent on A-13, not on S-24; S-24 is re-listed as C-4 at the
  top of this section.** A-13 landed after C-1 wrote this item and outranked it: newest claim,
  changes a live-loaded file, and rewrote an owner-facing risk paragraph. Result: A-13 survives,
  one owner-facing number corrected (4x), and the intraday launch gate found red (C-3). The
  original text of this item follows and is now C-4.

- **C-4 (was C-2) (critic): adversarially verify S-24, the pre-open MOO claim.** S-24 says the store's open is
  not the opening cross and that the pre-open move is worth **+1.98 CAR at the real MOO fill**. It is
  the highest-value unchecked claim of the last 24 hours because it proposes a change to the
  **execution clock** of the deployed book, so unlike a signal claim it has a hard gate:
  reproduce the control, re-run at a pinned window, and require `scripts/compare_orders.py` to still
  agree on 3,689/3,689 dates. An execution claim that cannot survive the gate is not deployable
  whatever its Sharpe. Second target after it: **S-29**'s +36.56 bps VIX-removal attribution.
  <!-- added by C-1, 2026-09-12. C-1 itself is in research/journal_critic.md: S-31 survived four
       attacks, its clause 7 (the owner-facing 25% drawdown solve in BLOCKERS.md) did not and is
       corrected there. No promotion contested; S-18 reproduces bit-exact and the deploy gate
       passes. Reusable rule that came out of it: a max-drawdown harness error is a single-path
       extremum, it is not monotone in size (0.442 / 1.155 / 1.135 / 1.294 at 0.75 / 0.78 / 0.80 /
       0.90), and it must never be interpolated or reused across cells - an inverse solve under a
       drawdown constraint needs the error measured AT the budget it selects. -->

from settling the intraday sleeve's slippage constant and thereby BLOCKERS.md item 6, and S-17
part 2 on the daily sleeve. Neither can advance on a non-trading day. **Everything else is the
owner's**, and I-2 added one more to that pile: the audit produces a verdict but has no schedule
and no delivery, both of which are barred to the loop.

- **S-37 DONE 2026-09-12 (`daily` track; see `research/journal_daily.md`): AUD-13 closed - the
  paper runner answered a broken history frame with a printed warning, and two bad yfinance
  prints a year cost this sleeve its whole measured selection premium.** Full detail under
  **AUD-13** in the audit section below. Headline: the defect is **reachable** (the scheduled
  task passes no arguments, so `--history yfinance`; 0 exits between the warning and
  `plan_orders`), the spurious flatten costs **0.138 / 0.252 CAR points per outage at 0 / 2 bp**
  for a break-even of **2.0 outages per year** against S-33's 0.5-point bar, an all-NaN column
  changes the funded set on **10.5%-83.6% of corrupted sessions for all nine names** while no
  CAR delta clears the seed sd, and **29.70% of name-days** move more than the no-trade band the
  stale-price path sizes through. The remedy's tail test was the instructive part: holding
  yesterday's book is 11x cheaper in CAR but **+0.602 worse in MaxDD than the flatten**, because
  the flatten's drawdown is *below the control's* - against the control it is **+0.046**.
  Identity exact, `compare_orders` 3,689/3,689, suite 593, launch preflight green,
  `signals.py` deliberately untouched. **Adds no research item, closes the last `daily`-owned
  audit item that needs no trading day, and files one `eng` item (AUD-13b: `CALENDAR.trading_days`
  answers past its own `coverage_end` instead of raising).** S-36's sign-off said this track had
  no such item left; AUD-13 was it, and the correction is that an item filed `[daily+eng]` is
  the daily track's whenever both of its named files are the daily sleeve's. **Now** there is
  none: what remains is S-17 part 2 and the two standing measurement jobs, all of which need a
  trading day, plus the owner pile in `BLOCKERS.md`.

- **S-36 DONE 2026-09-12 (`daily` track; see `research/journal_daily.md`): AUD-25 closed - the
  guard that exists to stop a silent 0% CAR covers one parameter out of eleven, and the audit
  named the smaller half of what it leaves open.** Full detail under **AUD-25** in the audit
  section below. Headline: **7 of the 11** integer windows on `Params` sit outside
  `__post_init__`, in **two** failure modes, and only the first is in the audit - SILENT-ZERO
  (2 fields, a whole sample in cash) and **SILENT-TRUNCATE** (5 fields, all five proven to give
  **byte-identical weights** at `history_bars + 100` and at `+ 500`, i.e. two grid cells that
  are one run). The truncation mode manufactures a flat parameter **shelf**, which is the exact
  artefact S-33 established as this sleeve's only reportable parameter result, so it corrupts
  the evidence standard rather than just a number. Of the other five claims the `ML_MODE="rank"`
  double gate is real on **10.79% of sessions** and worth **+0.286 CAR points in the code's
  favour** (prose fixed, code kept; S-27's rows are flattered by it), the **S-3 harness claim's
  sign is wrong** (the shipped convention *costs* that book **3.291 CAR points**, though at its
  own 5 bps both conventions are deeply negative so the cost refusal stands), and the remaining
  two are dead-code labels. Identity exact before and after, `compare_orders` **3,689/3,689**,
  suite **615**. **Adds no research item, closes the last `daily`-owned audit item, files one
  `eng` item (AUD-25b: `--history ib` reads the in-progress bar, unreachable from the deployed
  task).** **There is now no `daily` audit item that needs no trading day.** What remains for
  this track is S-17 part 2 and the two standing measurement jobs, all of which need a trading
  day, plus the owner pile in `BLOCKERS.md` - so the pattern S-31/S-32 established (re-price an
  open owner decision on the honest scale rather than open a new research track) is again the
  only thing that can advance without one.

- **S-35 DONE 2026-09-12 (`daily` track; see `research/journal_daily.md`): AUD-12 fixed and
  priced - one row in the ledger passed the promotion gate today and would have put a strategy
  on the paper account that the runner cannot trade, claiming +1.914 CAR points and delivering
  0.000 of them.** Full detail under **AUD-12** in the audit section below. Headline: the runner
  always trades `signals.DEFAULTS` (`paper_trade.py:196` reads a `PARAMS` attribute that does
  not exist) and the deploy gate builds `sig.Params()` too, so it agrees with itself whatever was
  promoted; 49 of the 56 `S1_*` names `main.py` reads reach that shared path; the two books hold
  different things on 13.6% of sessions; and the second-order damage is larger than the first -
  11 of 167 rows flip to "does not beat" against a bar no deployed book can reach, which is the
  **opposite** direction from AUD-10's slack. Fixed candidate-side and reader-side with
  `--promote` now recording the run's `env`; the audit's alternative remedy (plumb the env into
  the runner and the gate) is refused on merit. 167 verdicts re-judged, **1 moved and in the safe
  direction**, suite 543 pass, `champion.json` untouched, no live-runner edit. **Adds no research
  item and closes one audit item.** **Next daily audit item that needs no trading day: AUD-25**
  (`daily`) - `ML_MODE="rank"` gates on sign, the `Params` window guard is incomplete, and
  `--history ib` has a clock convention. It is the last `daily`-owned audit item; AUD-11's
  remaining half is a manual edit to a reserved file and stays the owner's or the critic's.

- **S-34 DONE 2026-09-12 (`daily` track; see `research/journal_daily.md`): AUD-10 fixed and
  priced - the promotion gate handed the next candidate 4.2 points of drawdown slack and 15
  ledger rows would have taken it.** Full detail under **AUD-10** in the audit section below.
  Headline: the defect is invisible in the CAR column (-0.001 at 0 bp) and 4.2x the drawdown
  tolerance in the risk column, because what S-18 promoted was risk rather than return; 15 of 167
  `s1_momo` rows flip and all 15 the dangerous way; fixed writer-side (`promoted_columns()`) and
  reader-side (`stale_note()`), with the 11 research notes in `stats_by_spread` preserved
  byte-identical against the audit's "delete the others"; 167 verdicts compared and **0 changed**,
  suite 241 pass, `champion.json` untouched. **Adds no research item and closes one audit item**,
  and corrects AUD-11's filed remedy: `--promote` has never written `note`, so no promotion can
  carry the relabel. **Next daily audit item that needs no trading day: AUD-12** (`daily+eng`) -
  the runner and the gate both trade `Params()` while `--promote` stores no `env`, so a run
  promoted with an `S1_*` override would pass the deploy gate and paper trade something else.
  Same shape as this one: a promotion that does not carry everything the champion is.

- **S-33 DONE 2026-09-12 (`daily` track; see `research/journal_daily.md`): AUD-11 priced - the
  "OOS 2020-2026" label is wrong and the number is not, and the audit's own re-select remedy is
  refused at t -2.18.** `scripts/sweep_s33.py`, seven clauses pre-registered, **60 DIAGNOSTIC
  rows** under `daily/s33_oos`, no shipped or runner-loaded file touched, identity exact
  (22.192150% / 5,052). Selection re-done with 2020-2026 withheld on the three axes whose grids
  come verbatim from the `signals.py` docstrings. Re-selecting on 2012-2019 moves
  `alloc_vol_window` 21 -> 10, the **worst of six** on that axis out of sample, for **-1.865 CAR
  points / -0.569 bps/day / t -2.18**. The contamination itself is **+0.974 above the grid mean
  (0.53 sd, 78th percentile of 18 cells)**, +0.492 above the median. Cause: the **selection
  premium is -0.049 CAR points** (IS top three 28.420 OOS vs IS bottom three 28.283; the global
  IS-argmax lands below the grid mean). Also: the shipped set is **not the full-period argmax**
  (`mom_skip=10` beats it by 0.485 there and was not taken). Cell C withheld half, shipped:
  **25.967% / 1.151 / DD 24.040**; grid band ~20.0..27.7%. **Adds no research item**; leaves one
  owed edit to `champion.json`'s label, blocked behind AUD-10 and the `--promote` gate, with the
  exact replacement text filed under AUD-11. Reusable rule: on this sleeve a parameter **shelf**
  is reportable and a parameter **argmax** is worth nothing, so every S-item's headline cell
  should be read against its axis's dispersion, not against its neighbours.

- **S-32 DONE 2026-09-12 (`daily` track; see `research/journal_daily.md`): the execution no-trade
  band stays at 0.01 - refused after its clauses PASSED, because the CAR column is 3.5x larger
  than the mechanism can produce.** `scripts/sweep_s32.py`, seven clauses pre-registered, **55
  DIAGNOSTIC rows** under `daily/s32_band`; `band=`/`skip=` added to `sweep_s25.legs_simulate`
  (S-26/S-28/S-30's precedent, default-inert, every earlier row bit-identical), **no shipped or
  runner-loaded file touched**, so no deploy gate and no replay owed. Identity exact (22.192150% /
  5,052; 19.640168% / 1.047 / DD 24.037). **Premise HOLDS** (band 0.080 gains +0.380 / +0.391 /
  +0.450 / **+0.519** at 0 / 1 / 2 / 3.2 bp) and **five bands pass cell C on `champion.json`'s own
  criteria** including the owner's 0.03 - then: spread-attributable part **+0.139** (the only
  monotone column: +0.045 / +0.058 / +0.095 / +0.139 / +0.286, against a gain column that
  zig-zags +0.090 / +0.013 / +0.313 / +0.544 / +0.206); **arithmetic ceiling 0.155% of equity a
  year** at the measured 3.2 bps, agreeing with the +0.139 to 0.016 points; **placebo** at the
  same 67.5% skip rate **-0.176 mean, sd 0.791**, one seed of five beating the band outright.
  Paired t **+1.96** full / +1.35 IS / +1.74 OOS; the owner's 0.03 is the local worst of the five
  (+0.013, t **+0.12**, 0.067%/yr). **The 2026-09-09 conditional resolves to "not material"**
  (measured cost +3.2 bps, se 4.5); `BLOCKERS.md` item 4 gains the priced addendum and the order
  list stays on `a6d6224ce9c70091e5bfa8e96f046bf3`. **Adds no item and closes one owner
  decision.** The reusable rule: `champion.json`'s criteria were written to compare *signals*;
  against an *execution* setting whose arithmetic ceiling is 0.155%/yr they are passed by path
  noise measuring sd 0.79, so **quote the ceiling before the CAR column** next time. The one
  thing that reopens it is `daily_fills.py` settling well above +3.2 bps - the prize is linear in
  the spread paid (~0.048%/yr per bp at band 0.080) and needs no new run.

- **S-30 DONE 2026-09-12 (see journal): refused on COST at every h - and the 'delta book' the
  item was built on does not exist, which one identity run settled in two minutes.**
  `scripts/sweep_s30.py`, 18 DIAGNOSTIC ledger rows under `daily/s30_delta`, seven clauses
  pre-registered and no post-hoc column. A fourth default-inert argument on the research harness
  (`flat_frac` on `sweep_s25.legs_simulate`, S-26/S-28's precedent); **no shipped or runner-loaded
  file was touched, so no deploy gate is owed**, and both identities are exact (`flat_frac=0.0`
  -> 22.192150% / 5,052 orders / residual 5.33e-16; `flat_frac=1.0` matches `mode="overnight"` on
  **3,689/3,689 sessions at max |difference| 0.000e+00**). **THE PREMISE IS REFUTED BY THAT SECOND
  IDENTITY**: the delta routing saves **0.0x equity/yr, 0.0%** against the pre-registered 10%
  threshold, because a book holding *nothing* through the session has no delta at the open (the
  whole position must go) and none at the close (the reload IS the rebalance) - S-25's overnight
  book and S-30's are the same book to the cent. The item's "~196x/yr" and "1,248x" were both
  un-normalized; growth-normalized the deployed book turns over **49.4x** and the overnight book
  **630.4x**, exactly 2 x its 1.2496x gross. **At zero cost the construction works and confirms
  S-25 a third time** - Sharpe 1.159 -> 1.246 / 1.321 / 1.337 and drawdown 23.860 -> 21.467 /
  19.051 / 19.113 at h = 0.25 / 0.50 / 0.75 - but the raw edge is **negative at every h** (-0.749
  to -3.050 bps/day, t -1.92 to -1.95), so the whole case is the relever, and **the pre-registered
  breakeven refuses it before any book is judged: 1.948 / 1.730 / 1.474 / 1.145 bps ONE WAY**
  against the 2 bp charged everywhere else, **highest where the construction does least** - no
  interior optimum, the signature of a cost problem rather than a tuning one. Quoted as books at
  2 bp + IBKR Pro financing (1.948 against 2.000 is 2.6% from the line, too narrow to leave as
  arithmetic): **14.689 / 0.937 / 21.909, 9.593 / 0.741 / 24.161, 4.497 / 0.427 / 29.405, -0.555 /
  0.009 / 50.206** against the deployed 19.640 / 1.047 / 24.037, **paired -1.875 / -3.819 / -5.792
  / -7.785 bps/day at t -4.79 / -4.88 / -4.93 / -4.97** - the most significant refusal in the
  daily file, and the contrast with the zero-cost column (|t| <= 1.95) *is* the spread. The exact
  vol-matched books are **worse** than the arithmetic that refused them (h=0.50 at scale 1.381
  earns 11.896 / 0.691 / DD 32.930, h=1.00 at 1.646 earns -3.470 / -0.093 / DD 71.825, **both
  breaching Reg-T** at 2.18x and 2.68x peak gross, both failing both halves), because levering the
  book levers the spread bill linearly while the edge is sublinear once the larger financed debit
  is charged. **Placebo passes**: shedding the leg that PAYS costs -15.395 bps/day at t -12.19
  against -7.785 at t -4.97, twice as expensive on identical turnover. **Do not re-open as an h,
  relever, netting or no-trade-band question** - the grid spans h from 0.25 to 1.00 and the
  breakeven is monotone in the wrong direction, the netting is measured at exactly zero, and the
  flatten legs clear the 0.01x band by an order of magnitude so a band cannot save it. Nothing is
  filed in `BLOCKERS.md` either, because **a refusal on cost is not an owner option**. Two durable
  pieces survive it: the **`flat_frac` argument** (any partial-flatten or intraday-exposure
  question now runs on the deployed book without editing it) and the rule that **when one
  construction can be expressed in two instruments, the refusal mode identifies the instrument
  rather than the idea** - S-26's futures version cleared its instrument's cost by 2.3x and died on
  *risk*, this equity version dies on *cost* at 2.0x below its instrument's round trip, and the
  ratio between the two verdicts is just ES's 0.488 bps against an equity 4.0 bps round trip. **It
  closes the leg-split program for good: hold (S-26), rank (S-27), size (S-28), shed (S-30) - the
  split is confirmed by three independent routes and monetized by none.**

- **S-31 DONE 2026-09-12 (see journal): the owner's size decision re-priced on the deployed,
  fully-charged book - about half the gain is gone, the Sharpe argument reverses, and option (c)
  is answered in advance. Not a new item and not a lever: it prices one that was already open.**
  `scripts/sweep_s31.py`, 37 DIAGNOSTIC ledger rows under `daily/s31_budget`, seven clauses
  pre-registered. Eight budgets (0.70 to the Reg-T corner at 1.00) x four cost cells; identity
  exact (22.192150% / 5,052 orders at zero cost, 19.640168% / 1.047 / DD 24.037 charged);
  **no shipped or runner-loaded file touched, so no deploy gate is owed**. Drawdown calibration
  against LEAN at three budgets including a new run at the selected one (DD error -0.442 / -1.135
  / -1.294 at 0.75 / 0.80 / 0.90; `20260912T130734Z`, 28.796% / 1.032 / DD 27.900%). **Gain over
  0.75 at today's cost of money: +0.428 / +0.679 / +0.959 / +1.353 / +1.991 / +3.186 against the
  +0.877 / +1.454 / +2.017 / +2.879 / +4.301 / +7.052 the owner was shown - 45-49% survives.**
  **Sharpe reverses**: flat uncosted (1.247 -> 1.246), 1.047 -> 1.003 costed, 1.023 -> 0.952 at
  today's rates, and it is not a convention artifact (excess-return Sharpe at the sample's own
  1.6924% *rises* 1.156 -> 1.176 uncosted, which is S-21's argument reproduced, and LEAN agrees at
  0.994 / 1.008 / 1.032). **Inverse solve**: <= 25% -> 0.70 (below the shipped budget), <= 30% and
  <= 35% -> 0.90. **The 35% cap binds nowhere; Reg-T does** (2.12x mark-to-market gross at budget
  1.00), and S-18 is why - the retired 3x book hit 35.4% at budget 1.0 where the unlevered one
  reaches ~30%. **Do not re-open as a budget-grid, cost-model or drawdown-target question** - the
  grid spans the shipped budget to the Reg-T corner, all three costs are charged in both the
  historical and today's-rates cells, and the three drawdown targets cover the range `criteria`
  permits. What is left is the **owner's preference about excess liquidity**, unchanged and now
  priced honestly in `BLOCKERS.md`. Two durable pieces survive it: the **four-cell convention**
  (any future comparison of two different-SIZED books is run in cells A/B/C/D rather than shifted)
  and the rule that **a cost correction measured on the champion does not transfer to a decision
  about the champion's size**, because none of the three costs is independent of leverage.

- **F-7 DONE 2026-09-12 (see `research/journal_ml.md`): the lower-turnover expression F-1 named is
  real - 8.53x gross per dollar turned on a quarter of the turnover - and it dies on POWER, not on
  cost. Refused; nothing shipped.** `scripts/ml_f7.py`, **29 DIAGNOSTIC ledger rows** under
  `intraday/f7_turnover`, eight clauses pre-registered. Identity exact against F-1's row
  `20260911T155155Z` (gross 1,102.352 / net -2,206.101 / turnover 13,831,037.037 / 0.797 bps /
  IC +0.01133). **Clause 2 pre-registered the wrong answer and that is the keeper**: IC(h) does not
  decay, it *rises* to **+0.02115 at h=10 (5 hours)**, cumulative multiple **15.966** against the
  3.00x needed - so the 30-minute horizon F-1 trains on is the worst horizon its own forecast has.
  **Clause 3 delivers what clause 2 promised**: `band 0.10/0.40 + conv 2.0x` earns **6.797 gross bps
  per dollar (8.53x F-1)** on **$3.44M/day** instead of $13.83M, **+$1,001/day, positive 3/3 test
  years - and t +1.33, so 0 of 19 cells pass the pre-registered t > 2.** **Clause 8 settles it**: the
  same cells at the same parameters on a **2019-2026 walk-forward, 1,933 sessions, nothing
  re-tuned**, where pooled IC *improves* to **+0.01392 at t +9.84** - the best cell's gross halves
  to **3.495 bps** and its net goes **+1,001 -> -$56/day at t -0.15, positive 4/8 years**. The 3/3
  was the 675-session sample. **Controls are clean on gross** (|t| <= 1.33 short, <= 0.21 extended,
  so the lift is the forecast) **and dirty on cost**: the conviction gate prices at 3.88-4.09 bps
  against the scrambled book's 2.13-2.19, because it selects the low-priced, reverse-split
  leveraged names - **1.7 of the 2.4 bps of extra cost is selection and no turnover cut removes it.**
  Feature importance is stably *ranked* between retrains (Spearman 0.665 / 0.699 / 0.767, VWAP
  displacement and relative volume on top) over **sign-flipping magnitudes**, which is what a weak
  true signal read through noise looks like. **Do not re-open as a dwell, band, EWMA,
  conviction-threshold or decile question** - the grid spans dwell 1-11, bands 0.04/0.20 to
  0.10/0.40, lambda 0.25/0.50, conviction 0.5x-2.0x, deciles 0.04-0.34 and the stacked cells, and the
  best of nineteen dies on 2.5x the window. Two durable pieces: the **persistence table**
  (`data/f1/f7_persistence.csv`; IC(h) on the demeaned cumulative return prices any forecast's
  natural holding period before a simulator exists) and a **reproducibility hazard now guarded in
  `ml_f7.py`** - every F-track script must run with **`INTRADAY_DATA_DIR=data/minute_alpaca`**,
  because `_splits.json` lives only in that store and without it `share_scale()` is 1.0, the
  commission is charged on split-adjusted share counts and **the cost line is understated by 0.28 bps
  of turnover (2.110 vs 2.392, 12%)** while gross, turnover and IC still match to the cent.

- **F-8 DONE 2026-09-12 (see `research/journal_ml.md`): the label ladder is real and the book still
  fails - this time on a power requirement the data cannot meet, so the F track CLOSES.**
  `scripts/ml_f8.py`, 24 DIAGNOSTIC rows under `intraday/f8_label`, 8 clauses pre-registered
  including the prior. Four labels fitted (h4/h7/h10 plus **`close` = hold to the 15:30 flatten,
  horizon 11 - slot**, which the backlog did not ask for and which is the one that wins: the fixed
  horizons are defined on only 8/5/2 of the 11 slots and confound horizon with time of day).
  **At constant book, constant turnover ($1,995,861/day = 2x equity) and constant learner, gross
  bps per dollar turned is monotone in the label's horizon: h1 1.501 -> h4 2.632 -> h7 3.293 ->
  h10 3.608 -> close 4.256, i.e. 2.84x for fitting the label the book actually holds**, and the
  book flips from -$232/day to +$306/day. It is the **first F-track cell whose gross clears its own
  cost line** (4.256 vs 2.724 = **+1.532 bps of edge**; F-7's best on the same window was -0.202),
  the five-seed scrambled control sits at -0.202 +/- 0.543 bps so the real cell is **8.2 control sd
  above the null**, and the cost-selection premium is +0.484 bps against F-7's +1.7. **REFUSED
  anyway, 0 of 20 cells**: clause 7 asks t > 2 pooled and it gets **t +1.47** on 5/8 positive years.
  The decisive number is the power arithmetic - **t +1.47 on 1,933 sessions needs 3,558 sessions
  (14.1 years) for t = 2, and the Alpaca store's ceiling after the walk-forward burn is ~7.7 years,
  so this cannot be resolved on data this repository can obtain.** Feature-importance stability got
  *worse* with the better label (Spearman 0.147-0.798 across 8 retrains, mean ~0.42 vs F-7's
  0.665-0.767; **0 of 38 features positive in all 8 retrains, 30 of 38 flip sign**). The effect is
  a volatility phenomenon: gross 2.369 / 4.970 / 5.421 bps by causal SPY vol tercile while h1 is
  flat at 1.7 / 1.5 / 1.3. **Do not re-open as a label, horizon, book or model question** - the
  label axis is now swept end to end and F-7 exhausted the book axis. Side effect: fixed a latent
  bug in `scripts/ml_f7.py` `vol_regime()` (date vs string keys) that made F-7's clause-6 regime
  table silently return "n/a" for every session.

- **F-14 DONE 2026-09-13 (REFUSED; see `research/journal_ml.md`): the FEATURE-SET axis is closed,
  and with it the panel.** Six axes were priced on one feature matrix - all 38 columns of
  `sweep_f1.FEATURES` are transforms of 5-minute OHLCV, which cannot encode *direction of flow*.
  F-14 built the two standard bar-level flow proxies at 1-minute resolution (tick-rule signed
  volume, Chaikin close-location value) plus path-shape and liquidity columns, 20 features,
  strictly causal, merged not inner-joined so the row set is F-8's exactly. Three arms at constant
  learner/split/label/book: `base` 38 = **IC +0.01030, $306/day, t +1.474** (clause 1 identity
  exact); `flow` 20 = **IC +0.00006**, **-$304/day, t -1.93**, paired **-$609 at t -2.70**;
  `both` 58 = IC +0.00843, $106/day, **t +0.528**, paired **-$199 at t -1.51**. **REFUSED.** The
  control is the finding: 20 columns of **scrambled** flow (permuted within timestamp) land at
  **+$29/day, t +0.29** - free - so the damage is the *information*, not the dimensionality.
  Post-run explains all of it: `ofi30` has univariate rank IC **-0.00928 (t -7.1)** and is **0.645
  correlated with `r6`**, whose IC is -0.00966, while `vwap_atr` already in the panel beats both at
  -0.01131; the genuinely orthogonal members (`eff30`, `eff5`, `dvol30`, median corr 0.004-0.015)
  have IC +0.0003 to +0.0025. **The tick rule is a noisier copy of the 30-minute return, and
  everything about it the return is not, is noise.** Importance stability collapses to mean
  pairwise Spearman **+0.036** (F-8's 38 scored +0.434, F-12's risk model +0.772) with only `gap`
  in every year's top 10. **Do not re-open on new columns built from the same OHLCV store.**
  Two reusable rules: **(a)** before fitting, measure a candidate feature's univariate IC *and* its
  max |Spearman| against the incumbent set - a 0.6-correlated column with a smaller IC is
  measurement error on an old signal and will cost money; this two-line check would have predicted
  the whole file in under a minute, against 32 walk-forward fits. **(b)** F-12's scrambled-signal
  rule generalises to feature sets: permute the columns you add, within timestamp, or you cannot
  tell "the extra width hurt" from "the information hurt".

- **F-15 DONE 2026-09-13 (REFUSED on the pre-registered arm; see `research/journal_ml.md`): the
  first F iteration outside the trade-bar store, and the gate was the deliverable.** Two channels
  neither computable from 5-minute OHLCV: the **auction tape** per name (Alpaca
  `/v2/stocks/auctions`, official opening/closing cross price+size, 2015-12..2026-09-11, one
  request per symbol, stored in `data/f1/f15_auctions/`) and the **SPY 0DTE chain** market-level
  (the local `data/options/odte/SPY` store, ATM straddle over spot = the market's own forecast of
  |move to the close|). `scripts/ml_f15.py`, 6 rows under `intraday/f15_altstore` (4
  pre-registered + 2 post-run), gate in `data/f1/f15_gate.csv`, per-year ICs in `f15_post.csv`.
  Clause 1 identity exact at IC +0.01030 / gross 4.256 / cost 2.724 / t +1.474, turnover identical
  across every arm to the dollar ($1,995,861/day, spread $0).
  **The gate passed 19 of 19** - nothing was a redundant copy, which is the opposite of F-14. The
  carrier is `auc_ofade` (how far the first five minutes of tape travelled from the opening cross):
  IC **-0.00690, t -4.9**, max |rho| **0.295** against the 38, and **sign-stable in 7 of 8 test
  years**, matching `prev_ret` and `r6`, the two best incumbents. `auc_ojump` is 0.905 correlated
  with `gap` and kept by the rule because `gap`'s own IC is -0.00086 against its -0.00532; their
  residual reads IC -0.00547 (t -3.38), so **the part of the overnight move only the auction print
  knows is the part that predicts**. `auc_cdrift`, the prior's favourite, is dead (t +0.3).
  **REFUSED on all three legs**: `both` (57 features) net **$158/day, t +0.799**, 4/8 years,
  paired -$148/day at t -0.913. F-14's scramble control reproduces exactly - 19 permuted columns
  cost **-$9/day (t -0.07)** and 19 real ones cost -$148/day, so the damage is the information,
  not the width.
  **The mechanism is NEW and it is the finding.** F-14's explanation (redundancy) is ruled out by
  the gate and F-14 (6)'s explanation (sign instability) by the 7/8 years. Post-run parsimony arms,
  test-set-selected and barred from clause 5: **`lean3`** (base + `auc_ofade` + its `x_` and `cs_`
  forms, 41 features) reads **$365/day, t +1.75, gross 4.643 bps** - the highest gross this track
  has measured - **paired +$60/day (t +0.49)**, and is the **first arm ever positive in the low-vol
  tercile** (+$103 against base's -$133). `lean1` (the raw column alone) reads $28/day, -$278
  paired at t -2.33. **The same family, same data, same learner: 19 columns cost $148/day and 3 of
  those 19 gain $60/day.** Importance stability collapses as in F-14 (mean pairwise Spearman
  **+0.001** against base's +0.434, no feature in every year's top 10, alt family taking 18-81% of
  positive importance).
  Reusable rules: **(a) the F-14 gate is necessary and NOT sufficient** - it screens the
  *redundant* and says nothing about the *weak and numerous*; add a second leg, **a candidate
  FAMILY is admitted only at the size justified by how many members clear the incumbent floor**
  (here 3, not 19). **(b) Add a column as a TRIPLE (raw + market residual + cross-sectional rank)
  or not at all** - for a book that ranks cross-sectionally the raw level alone is worse than
  nothing. **(c) Build alt features on the PANEL'S universe, not the sleeve's**: family A was first
  built on `intraday_common.UNIVERSE` (16 names) against the panel's 56, giving 27% coverage and
  `cs_*` ranks over the wrong cross-section, and it inverted two of the headline ICs before it was
  caught. **(d) F-14's closing statement is corrected, not overturned**: a store outside 5-minute
  OHLCV does hold an orthogonal, significant, sign-stable column, so part of the ceiling is the
  panel and not only the market - but **no arm of any construction has reached t = 2.0**, and a
  post-run, test-set-selected +1.75 is not a counterexample.
  **Per-name implied skew, F-15's own pre-registered favourite, was NOT tried and that is not a
  choice**: Theta history/quote returns HTTP 403 on a FREE subscription. Already open in
  `research/BLOCKERS.md` as O-3/O-4 (2026-09-12); F-15 adds a second track waiting on it and does
  not re-file it.

- **F-16 DONE 2026-09-13 (REFUSED; see `research/journal_ml.md`): the causal gate BEATS the oracle
  it was built to imitate, and it beats it by admitting NOTHING in 5 of 8 years. Closest this track
  has ever come to the hurdle - net t +1.969 against 2.0 - and still refused on the paired leg.**
  F-14 (a)'s redundancy rule plus F-15 (a)'s incumbent-floor rule, re-run inside the walk-forward at
  every retrain on train + validation only. `scripts/ml_f16.py`, 5 ledger rows under
  `intraday/f16_causalgate`, per-year gate in `data/f1/f16_gate.csv`, admitted sets in
  `f16_admitted.json`. No new data - F-15's parquet stores read unchanged. `base` reproduces F-8 to
  the digit (IC +0.01030, 4.256 gross bps, $305.7/day, t +1.474, 1,933 sessions); turnover identical
  across arms to the dollar.
  **The pre-registered floor (median incumbent |IC|) is nearly degenerate**: a TRAIN-window median
  reads 0.0077-0.0149, far above the 0.002-0.006 F-15 measured on the pooled test window, so it
  admits nothing in 5 of 8 years. A `q25` specification was added AFTER that pass was read, labelled
  post-hoc throughout and barred from the hurdle.
  **`lean3` is NOT confirmed as stated.** The causal gate admits `auc_ofade` - the column F-15's
  whole result rests on - in **2 of 8 years** (5 of 8 at q25). What it admits most often is
  `auc_osz_adv`, the opening cross size against ADV, which **F-15's own test-window gate rated at
  t -0.8, i.e. nothing**. Mean pairwise Jaccard of the admitted sets +0.393 (q50) / +0.512 (q25);
  no column admitted in every year.
  **And the book went up past the oracle anyway**: `causal` net **$412/day, t +1.969, gross 4.795
  bps - the highest this track has fitted** (base 4.256, `lean3` 4.643), paired +$106/day at t +1.42;
  `causal_scrambled` $284/day, paired -$22 at t -0.33. **REFUSED**: t +1.969 (FAIL by 0.031), 5/8
  years (PASS), paired t +1.416 (FAIL). Nothing deployed, `champion.json` untouched.
  **Why it beats the oracle, which is the reusable part**: in 2025 and 2026 the causal gate
  independently rediscovers `lean3`'s exact triple and the arms are identical to the dollar; in 2024
  it picks `auc_osz_adv` and earns $1,320 against $1,086; and in **2019-2023 it admits nothing**,
  which is where `lean3` - forced to carry `auc_ofade` every year - averages $74/day against base's
  $97, giving back $660/day in 2020 alone.
  **`lean3`'s headline low-vol result does not survive**: `causal` is -121 / +423 / +713 across
  realised-vol terciles - best arm in mid and high - but negative in low like every arm before F-15.
  Reusable rules: **(a) a feature gate earns its keep in the windows where it admits NOTHING**;
  report the abstention rate and treat a gate that always admits as unscreened. **(b) Never read the
  pooled t of an arm whose feature set varies by window** - 65% of `causal`'s sessions ARE base;
  the paired statistic on the active subset (+$303/day at t +1.42 on 675 sessions, against the
  scramble's -$63 at t -0.33 on the same 675) is the honest read. **(c) An incumbent floor
  calibrated on pooled TEST-window ICs is far stricter than intended once made causal**, because
  train-window ICs run roughly twice as high. **(d) The tighter floor is the better floor,
  confirming F-15 (a) from the other side**: q50 is active on 35% of sessions and worth $303/day
  per active session; q25 is active on 87% and worth $105.

- **F-18 (open, and it is now the only open item in the F scope).** F-17 refused the pooled gate and
  found why: **the floor ranks candidates in the wrong order.** The five admissions with the largest
  train-window |IC| (|t| 5.7-7.7, all flow) lost; the three smallest (|t| 2.1-2.9, all auction) made
  all the money, and the ranges do not overlap. The defect is that the gate scores a candidate on
  the window the model is fitted on, where a column that broke once looks strongest (`amihud30`,
  |t| 6.8 on 2016-2019, -$974/day in 2020). The causal fix costs nothing: **score the candidate on
  the VALIDATION year alone** - year Y-1, already held out of the model's own fit - with the floor
  recomputed on that same year. Still strictly causal, and it asks "did this column carry the last
  time it was out of sample" rather than "how strong is it in sample". Two arms against F-17's
  admitted sets as the reference: `val_floor` (no fit, ~10 min) and `val_contrib` (rank each
  candidate by the change in validation-year rank IC when added to the 38; 17 x 8 = 136 fits at
  ~8 s, ~20 min). Unchanged hurdle (net t > 2.0 AND >= 5 of 8 years AND paired t > 2.0); per
  F-17 (b) pre-register the abstention rate as an outcome, and pre-register the discriminating
  prediction: a validation-year floor **abstains in more than 2 of 8 windows** and **declines
  `amihud30` in 2020**. Everything is on disk; no data pull.

- **F-17 DONE 2026-09-13 (REFUSED; see `research/journal_ml.md`): the gate ranks candidates in the
  WRONG order, and the pooled arm finished below its own no-information scramble control.** Pooled
  17 parents (F-14's 11 flow + F-15's 6 auction), per-year causal floor, new within-pool redundancy
  leg. net t **+1.503** against 2.0, paired `pooled - base` **+0.043** - REFUSED. `pooled` $310/day
  against `pooled_scrambled` **$319/day**: permuting the admitted columns within each timestamp is
  not worse than reading them. Clause 1b PASSED - the auction-restricted gate reproduces F-16's
  admitted sets in all 8 years and its book to the dollar ($412/day, t +1.97), so widening the pool
  **cost $112/day at t +1.35**. **F-14's open question is answered and the answer is no**:
  `flow_only`, the flow family admitted at the size its own members justify, is $205/day against
  base's $306 (paired t -1.22, -$258/day on active sessions), and all of it is 2020 (-$974/day,
  t -1.90). Abstention fell from 5/8 windows to 2/8 and the book fell with it, which confirms
  F-16 (a) from the adversarial side. 5 diagnostic ledger rows under `intraday/f17_poolgate`.

- **F-17 DONE - original statement retained for the record.** F-16 built the first screen this
  track has that can rank a candidate **without spending the test window**, and it costs ~16 s per
  retrain window. Point it at the whole candidate space the track has accumulated: **F-14's 19 flow
  columns (`data/f1/f14_flow.parquet`) and F-15's auction family pooled into one candidate set**,
  per-year floor, per-year admission. F-14 refused its flow family **as a family** and F-15 (a)'s
  rule says a family should be admitted only at the size its members justify - which for flow may be
  one or two columns in some years and zero in others, and has never been measured. Pre-register the
  unchanged hurdle (net t > 2.0 AND >= 5 of 8 years AND paired t > 2.0) and, per F-16 (a),
  pre-register **the abstention rate and the paired-on-active statistic as reported outcomes**, not
  as diagnostics. Both stores are on disk: one file, no data pull, ~45 minutes. **Do not** re-run
  F-16 at more thresholds - F-16 (d) already says the tighter floor wins.

- **F-16 DONE - original statement retained for the record.** F-15 (7) measured that a 3-column
  subset of a 19-column family turns a -$148/day loss into a +$60/day gain and posts the highest
  gross and the first positive low-vol regime this track has seen - but `auc_ofade` was chosen
  **after seeing the test window**, so `lean3` is a selection artefact until the selection is made
  causally. **Make the gate causal: run it INSIDE the walk-forward.** At each retrain, screen every
  candidate on train + validation only (univariate per-timestamp rank IC, max |Spearman| against
  the incumbents, and F-15 (a)'s new floor test), admit the survivors that clear the incumbent
  floor, fit, and carry the admitted set forward as a per-year record. Pre-register: the hurdle is
  unchanged at net t > 2.0 pooled AND >= 5 of 8 years AND paired t > 2.0 against base; a secondary
  and reportable outcome is **which columns the causal gate admits in each year** - if it picks
  `auc_ofade` in most years the mechanism is confirmed, if the admitted set churns then F-15 (9)'s
  importance collapse is the whole story and F-14 stands as written. One file, ~40 minutes of
  compute, reuses `data/f1/f15_famA.parquet` and `f15_famB.parquet` unchanged so there is no new
  data pull. **Do not reopen F-15 as a "try more auction columns" item** - (a) says the opposite.

- **F-12 DONE 2026-09-12 (REFUSED; see `research/journal_ml.md`): the label-family axis is closed,
  and the measured elasticity beta = 1.494 is the finding.** The first F iteration to fit a new
  model on a new label family, and the first to act on the book's **sd** rather than its mean:
  a second walk-forward model on `|y_close|` (the per-name risk contribution of a dollar-neutral
  book), spent on sizing as `w_i ~ sigma_hat_i^-p`, p in {0, 0.5, 1, 2}, p = 1 pre-registered as
  primary. `scripts/ml_f12.py`, 22 DIAGNOSTIC rows under `intraday/f12_risksize`, clause 1 identity
  exact at gross 4.256 / cost 2.724 / t +1.474, and **turnover identical in every cell to the
  dollar ($1,995,861/day, spread $0)** because each side sums to gross/2 however it is split - the
  one F-track file with no turnover confound to control for. **The risk model is excellent**: rank
  IC **+0.3302** mean (+0.3065..+0.3563, IC t +100..+146), R^2 +0.315, against F-8's own signed
  `close` label re-measured at **+0.01030** and *negative in 2026* - a 32x IC. **The sizing works
  on the risk side**: sd 9,118 -> 6,622 (-27%) at p = 1, worst day -$51,431 -> -$27,421. **REFUSED
  on clause 5**: t **+1.058** against a hurdle of 2.0, because the **mean fell x0.521 while the sd
  fell only x0.726**. Paired (F-11's standing rule), p1 - p0 is the **exact mirror of F-11**: cost
  saved +$51 at t +42.38 (arithmetic), **gross given up -$197 at t -2.28 (significant, not noise)**,
  net -$146 at t -1.69. **Clause 4(ii) fails and the failure is the result**: scrambled sigma - the
  same weight dispersion on the wrong names - reads **t +1.400 +/- 0.065**, so random dispersion
  costs 0.07 of t and *the correct risk forecast costs 0.42*. The free trailing-ATR baseline beats
  the ML model at every rung (+1.41/+1.28/+0.93 vs +1.31/+1.06/+0.49; paired `p1 - atr_p1` -$35/day
  at t -1.55) despite Spearman +0.945 between them - **the refinement is the part that loses
  money**. Clause 4(i) passes (scrambled alpha under inverse-vol sizing, gross t -0.13). The
  mechanism, measured post-run over 21,940 held name-days: realised alpha by sigma quintile runs
  **-0.76 / 3.94 / 6.08 / 10.20 / 20.51 bps** and alpha/sigma **rises monotonically -0.0125 ->
  +0.0745**, i.e. **log-log beta = +1.494** where inverse-vol sizing breaks even at 1.0, and the
  forecast has *no edge at all* in the quietest fifth of its own holdings. The opposite direction
  (p = -1, post-run, test-set-selected, no control) reads net $499/day at **t +1.57** with sd
  14,029 and a -$82,537 worst day, so **the whole ladder p in [-1, 2] spans t +0.49 to +1.57 and
  never touches 2.0 - the sizing axis is bounded on both sides.** Regimes: sizing makes the dead
  regime deader (low vol -$69 -> -$200 -> -$299/day at p = 0/1/2), helps nowhere. Reusable rules:
  **(a) risk parity is a bet on beta = 1** - measure the log-log elasticity of realised alpha on
  predicted risk before applying any inverse-vol overlay, which no sleeve in this repository
  (daily champion or deployed intraday `active`) has ever done; **(b) a better forecast of the
  wrong quantity is worse than no forecast of it** - run any overlay against a *scrambled version
  of its own signal*, not only against a null book. Feature-importance stability (the brief's
  second criterion) confirms the premise the item was built on: the risk model's yearly rankings
  correlate at Spearman **+0.772** with `vol_rel` and `vol_rel6` in the top 10 of **every** year
  (rank means 1.9 and 2.2), against the return model's +0.434 and **no** feature in every year -
  and the return model's own most-persistent feature is `vol_rel6`, the risk model's #2, so the
  direction model had been reaching for the risk model's inputs all along. **Do not re-open as a
  sizing, risk-label, risk-learner or cap question** - both directions are priced and bounded.

- **F-13 (open, and it is NOT an F-track item - filed here because F-12 found it).** F-12 (7)
  measured that this forecast's realised alpha scales as **vol^1.49** and is **negative in the
  quietest fifth of its own holdings** (-0.76 bps, t -0.49, on 4,388 name-days). Every F
  construction has taken the 56-name universe as given and asked what to do with it. The question
  that opens is a **universe** question, not a model question: the sleeve carries names the
  forecast demonstrably cannot trade, and they are identifiable ex ante by predicted risk, which
  is the one thing F-12 proved is forecastable (rank IC +0.33). **Pre-register before running**, and
  inherit F-12's arithmetic rather than rediscovering it: the honest hurdle is still t > 2 pooled
  on >= 5 of 8 years, a sigma floor must be tested as a *continuous* penalty as well as an
  eligibility filter (F-11 (7): a continuous penalty strictly dominates a floor), and the cell must
  be run against a scrambled-sigma control per F-12 (b). **State the prior**: dropping the quietest
  quintile removes ~20% of name-days worth ~0 and concentrates the book, so the expected outcome is
  gross up, sd up and t roughly flat - which would close the universe question too. This belongs to
  whoever owns the sleeve's universe (A-track/D-track), not to `ml`; it is written down so the
  measurement is not lost.

- **F-11 DONE 2026-09-12 (REFUSED; see `research/journal_ml.md`): the cost axis is closed, and the
  paired test is the finding.** F-8 pays away 64% of its gross as cost, and cost is a property of
  the *names chosen*: IBKR's $0.005 per share makes a round trip run 3.40 bps (TMO at $516) to
  11.08 bps (SOXS at $13) of position, and a plain decile buys the widest predicted moves, which
  are the cheap leveraged names. F-11 ranks on alpha net of each name's own round trip
  (`long = pred - lambda*c_i`, `short = -pred - lambda*c_i`; lambda = 1 is the economically correct
  value and the pre-registered primary cell), nothing re-fitted. `scripts/ml_f11.py`, 13 DIAGNOSTIC
  rows under `intraday/f11_costaware`, clause 1 identity exact at gross 4.256 / cost 2.724 / t
  +1.474. **The lever works**: cost falls monotonically 2.724 -> 1.841 bps (72% of the addressable
  commission term), SOXS -634 name-days and NOW +413, and lambda = 1 reads net $362/day at **t
  +1.881** against F-8's $306 at +1.474. **REFUSED on clause 5** (hurdle t > 2). **The paired test
  is why that is not close**: per session, the cost saved is **+$95/day at t +41.67** - arithmetic
  on a known price - while the gross given up is **-$39/day at t -0.48**, so the net improvement is
  **+$56/day at t +0.70, positive on only 45% of sessions**, same sign and same non-significance in
  both halves of the window. Comparing 1.47 with 1.88 side by side shows none of that, and the same
  sentence disposes of the lambda = 2 cell's t +2.26 (selected on the test set). Controls pass as a
  gate on both limbs: zero-forecast gross stays flat at every lambda (t -0.90/-0.20/-0.34/-1.39) and
  the control's cost drop is 50% of the real one, which is F-7's +0.488 bps selection premium being
  removed. **The refusal is a bound, not a verdict**: slippage floors cost at 1.5 bps of turnover,
  lambda = 8 already removes 72% of everything above it, and the book still reaches only t +1.57 -
  so nothing on the cost axis can clear the hurdle. Reusable rules: (a) **an improvement that is
  certain on one side of a subtraction and noise on the other must be tested paired on the shared
  sessions, never by comparing the two books' t's**; (b) **a continuous cost penalty strictly
  dominates an eligibility filter** - hard price floors at $25/$50/$100 give net $286/$62/$256
  (non-monotone) because a floor destroys gross that lambda keeps. By-product for any
  execution-limited book: the net-score gate holds 4.5 names instead of 11.4 and turns $790k/day
  instead of $2.0M - **40% of the turnover for 95% of the net**, at 6.214 bps gross per dollar
  turned. Feature-importance stability over 8 test years: mean pairwise Spearman **+0.434**, top-10
  overlap 44%, **no feature in the top 10 of every year**; the volatility family persists
  (`vol_rel6`, `m_rvol_ratio`, `rvol_ratio`) but swings 20-30 ranks. All five axes of F-1's forecast
  are now priced (method, book, label/horizon, breadth, cost). **The ML track has nothing open;
  reopening the supervised class needs a new mechanism - a different instrument, frequency or label
  family - not another construction on this forecast.**

- **F-9 (REFUSED 2026-09-12 by F-10 - do not build the store on this rationale).** F-10 priced
  F-9's premise on the 56 names already on disk, with F-8's predictions frozen and only the book's
  universe subsampled (`scripts/ml_f10.py`, 9 DIAGNOSTIC rows under `intraday/f10_breadth`, clause 1
  identity exact at gross 4.256 / t +1.474). The breadth curve does rise - log-log slope **+0.776**,
  *above* F-9's assumed 0.500, extrapolating to t = 8.94 at 500 names - and it is **not usable**.
  **(a) Clause 4's pre-registered control fails**: the same curve on a scrambled prediction runs
  -1.54 to -4.05 with |t| slope **+0.408**, so a book with **no forecast at all** buys 57% of the
  real curve's slope, matching the real book's own sd channel of 0.441. **(b) The other 43% is the
  mean** (+0.334; net $150/day at N=8 against $306 at N=56, gross bps slope +0.106) - a selection
  effect that clause 5 pre-registered as **reversing** on extension, since names 57-500 are less
  liquid and weaker than the sleeve's chosen 56. **(c) The estimators span the boundary and the
  quantity is not identified**: the saturating fit pins rho at its 0.00000 boundary (ceiling 191.7,
  a misspecification signature - beta +0.776 exceeds the model's structural max of 0.5), and the
  same object fits rho 0.999 / 0.0119 / 0.0000 across the vol terciles, i.e. t(500) of -0.20 / 1.95
  / 3.37. The only correctly-specified finite estimator is the direct one: sub-book rho +0.1406
  de-aggregated to a per-name **0.01155**, giving **t(500) = 2.166 and a ceiling of 2.344**. **A
  ~500-name build chasing t = 2.0 against a theoretical maximum of 2.34 - an upper bound by clause
  5 - does not repay itself.** Fixed two defects in F-10's own first cut (clause 4 coded as a remark
  rather than a gate; estimator (C) using basket correlation as per-name correlation, which had
  understated the ceiling by 10x - the correction made the refusal *harder* and was applied in full).
  Reusable rule: **split a breadth or sample-size curve into its mean and variance channels and run
  the variance channel against a zero-forecast control before extrapolating it.** The ML track has
  nothing open; reopening the supervised class needs a new mechanism, not more cross-section.

- **F-9 (original text, kept for the pre-registration).** The only honest way to reopen the
  supervised class after four refusals is **more independent cross-section, not more history**: the
  pooled t is a breadth statistic as much as a length one, and the panel is 56 names. F-8's best
  cell needs 3,558 sessions at 56 names; ~4x the breadth would reach the same t on the ~1,900
  sessions that exist. That is a request for a **~500-name Alpaca SIP minute universe**
  (`scripts/alpaca_data.py`, paced, into `data/minute_alpaca`), after which F-8's exact grid can be
  re-run with nothing re-tuned. Until that store exists there is no ML work to do here.

- **F-8 (original text, kept for the pre-registration) (open, the only axis F-7 left, and it is a
  new forecast rather than a new book).** F-7's
  clause 2 measured that this feature set's IC **peaks at h = 7-10 intervals (3.5-5 hours), not at
  the 30 minutes F-1 trains on** (+0.01133 -> +0.02064 at h=7, +0.02115 at h=10). Every F-7
  construction harvests that persistence with a model fitted to the *wrong* label; F-8 fits the
  label directly - same panel, same walk-forward, same 38 features, label = the demeaned cumulative
  forward return over h intervals, h in {4, 7, 10}, one position per name per session held to the
  15:30 flatten. **Pre-register before running**, and inherit F-7's arithmetic rather than
  rediscovering it: the honest hurdle is **~3.7 bps per dollar turned** (the conviction book's own
  measured cost, not the 2.392 headline), the window is **2019-2026 from the start** (675 sessions
  cannot resolve a t of 1.3), and the scrambled-prediction control and the cost column of that
  control are both mandatory. **State the prior in the pre-registration**: three refusals at IC
  ~+0.011 to +0.014 say the likely outcome is a forecast worth ~3.5 bps against a 3.7 bps line, and
  F-8 should be the last item on this track unless it clears the hurdle outright. Run it as
  `py -3.14` with `INTRADAY_DATA_DIR=data/minute_alpaca`.

- **A-5 part 2 (STANDING, and now has an end condition that is close).** Measured intraday fill
  slippage against the harness's 1.50 bps assumption and the sleeve's **2.52 bps** breakeven.
  Re-quoted 2026-09-12 (Saturday, so unchanged from 2026-09-11's close): **66 fills over 2
  sessions, +2.22 bps notional-weighted, se 0.80, |measured - shipped| / se = 0.90** - the harness
  is optimistic by 0.72 bps but the two are **not yet distinguishable at 2 se**, which needs ~145
  fills, i.e. ~4.4 more sessions at the 33 fills/session seen so far.
  **Run it as `py -3.14`**: it reads the parquet minute store and only 3.14 has `pyarrow` installed
  on this machine (`py -3.11` dies with `ImportError: Unable to find a usable engine`).
  **Re-quote the mean and standard error every session.** When the constant is pinned to
  within two standard errors there is no further information the intraday sleeve can produce, and
  `BLOCKERS.md` item 6 ((a) keep at reduced size / (b) retire to `equity_frac` 0.0) becomes
  answerable. **Say so when it is, rather than finding a twelfth lever** - that is the Current
  objective's own instruction and F-6 removed the last candidate it applied to.

- **S-17 part 2 (STANDING).** The same measurement on the *daily* sleeve. Four sessions of fills
  now exist and `ref_price` has matched the previous session's close in **13 of 13**, which is the
  standing evidence for `BLOCKERS.md` item 1. It prices the 2 bp column in `stats_by_spread`
  directly, and after the pre-open move it also scores MOO fills against the **open** they aim at
  (`daily_fills.py`, extended in S-23), which is how the +1.98 gets confirmed or refuted live.

- **I-2 DONE 2026-09-12 (see journal): `scripts/session_audit.py` ships, and it is validated by
  reproducing BOTH live defects on the day they happened while staying quiet on the three clean
  days.** 21 assertions over `live/log/<date>.jsonl` and `live/log/intraday-<date>.jsonl`, one page,
  one rolled-up verdict, exit code 0/1/2, `--all` and `--json`. Log-only: **no IBKR connection, no
  order, and no shipped, runner-loaded or scheduled-task file touched**, so no deploy gate and no
  replay is owed. **The validation is the whole point**: 2026-09-08 PASS (pre-deployment),
  2026-09-09 WARN 0/3/5, 2026-09-10 WARN 0/5/12, **2026-09-11 FAIL on exactly
  `daily.no_foreign_positions` and `intraday.pnl_reset`** - the S-18 TQQQ orphan (`['TQQQ'] are NOT
  intraday-sleeve names`) and the rollover leak (`trades 32 > 0 fill(s) logged by then`, 32 being
  2026-09-10's fill count). Both fixes are already shipped, so those two rows are now **regression
  guards**. **Four false positives were removed by reading the code, not by loosening a
  threshold**, and each is a durable fact: (1) `effective_exposure` is **not a limit** (1.7363x on
  2026-09-10, 1.7669x on 2026-09-09, because a 3x proxy carries 3 units of economic exposure at
  0.333 of the margin - S-18's point); the one shipped ceiling is `margin_used <= 0.75`, which
  holds on every live plan, so the assertion moved there with a 2.30x runaway alarm beside it;
  (2) a `connect_failed` only costs a session if no live plan follows (six each on 09-09 and 09-10
  from manual attempts while IB Gateway was down, both rebalances went through); (3) a live plan
  wanting orders and logging none is a `--dry-run` outside 15:40-15:50 ET and a **lost session**
  inside it; (4) dates before the first real fills (daily 2026-09-09, intraday 2026-09-10) have no
  session to lose. **One new finding, and it is not a defect**: the intraday book's
  mark-to-market gross peaked at **1.034x `GROSS_HARD_CAP`** on 2026-09-10 (1 of 15 snapshots over,
  14 names), because the cap is applied to **decision-time targets** while `MIN_CHANGE` leaves a
  name alone until it drifts 2% of sleeve equity - the implied per-name drift at that peak is
  **0.0025 against the 0.02 band**, `intraday_backtest.py` caps identically from the same constants
  so the harness already prices it, and total notional was ~2.09x of NAV against 4x DT buying
  power. Reported as a WARN naming the band; **the trader was not changed**, because nothing
  warrants it and rule (a) would require a replay. **What is left of I-2 needs the owner**: the
  pass runs when the loop runs, and wiring it to ~16:00 ET from its own scheduled task is barred to
  the loop by AGENTS.md - filed in `BLOCKERS.md` beside item 2.

**Explicitly NOT to be re-opened** (each carries a do-not-re-open clause in its own entry, and each
was refused on a grid that spans the obvious knobs): S-27 as a ranking/score question, S-28 as an
estimator/window/level-match/leg question, S-29 as a threshold/staleness/instrument/implied-series
question, S-30 as an h/relever/netting/no-trade-band question, F-4/F-5/F-6 as an
entry-minute/lookback/selection/exit/book question, and any daily candidate that spends turnover on
what the book holds between the open and the close (S-25's rule). **The whole leg-split program is
closed** - hold (S-26), rank (S-27), size (S-28), shed (S-30) - and the one remaining way to
monetize the split would be an instrument whose round trip is an order of magnitude under the
equity spread, which is the futures decision already in `BLOCKERS.md`.

- **S-29 DONE 2026-09-12 (see journal): refused - and it is the first refusal here where the
  input was IMPROVED on its own terms and the book got worse. A risk switch is not a
  forecasting problem.** `scripts/sweep_s29.py` + `scripts/regime_data.py`, 30 DIAGNOSTIC
  ledger rows under `daily/s29_regime`, six clauses pre-registered and no post-hoc column.
  The question S-28 left: volatility decides this book's SIZE through the vol target (priced,
  binds on 2.8% of sessions) and its DIRECTION through `risk_on`, which flattens the book on
  **trailing realized** vol and has done so on 590 of 3,689 sessions since S-1. Third
  default-inert hook in the shipped `signals.py` (`S1_REGIME_SERIES` / `set_regime_series`),
  scale-free so no constant is re-tuned; **`compare_orders.py` 3,689/3,689 AND a full LEAN
  control reproducing `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`**. **Two identities to
  the digit** (22.192150% / 5,052 orders; the standalone gate reproduces the book's own
  risk-off days 3,689/3,689). **The premise passes emphatically**: forecasting the next 21
  sessions' realized vol, log-log corr **0.4985 shipped / 0.6361 VIX / 0.5326 stale VIX /
  0.6857 SPY ATM implied**. **The book says the opposite**: on an ungated reference book every
  session earns +10.01 bps, the realized gate removes sessions worth +8.72, **VIX removes
  sessions worth +20.07**, and the **60 sessions VIX removes that realized does not are worth
  +36.56 at t +2.01** - it sells the rebounds. Primary **15.901 / 0.842 / DD 37.758** against
  **19.640 / 1.047 / 24.037**, failing every criterion in the full period and both halves and
  breaching the 35% limit; the **pre-registered off-matched column** (threshold solved on the
  IS half so the off-rates are equal, which kills the exposure explanation) is the **worst
  book at 12.188 / 0.729 / 31.540, paired -2.612 bps/day at t -3.06**. **Placebo triggers**:
  a VIX made 5 sessions STALE does *better* (16.666 vs 15.901 full, 15.911 vs 13.251 IS).
  **Do not re-open as a threshold, staleness, instrument or implied-series question** - the
  shelf spans 1.25 to 2.00 and the VIX gate loses at every one of the six while drawing down
  33-41%, the independent SPY ATM implied series agrees in sign on its own window (15.926 /
  0.791 / DD 35.193 against 21.219 / 1.036 / 24.040), and a *worse* forecast is a *better*
  gate, which is a sign fact rather than a tuning one. Two things it settles in passing: the
  shipped 1.50 threshold is a **shelf, not a spike** (Sharpe maximum of the realized row at
  1.047, neighbours within 1.4 CAR points), and **removing the switch entirely is worth +2.68
  CAR for +12.9 points of drawdown** (22.317 / DD 36.892) - refused on the spot rather than
  filed for the owner, because 36.9% is past the 35% absolute limit, so the switch is the one
  thing keeping this book inside its own risk mandate. Three durable pieces survive it: the
  **`S1_REGIME_SERIES` hook** (a credit spread, a breadth measure or a term structure is now
  priced through the shipped algorithm unedited), **`scripts/regime_data.py`** (VIX 2005-2026
  and SPY ATM implied on disk as plain level files), and the **standalone `gate_series`
  identity**, which lets an off-rate be quoted without running a book.

- **S-28 DONE 2026-09-12 (see journal): refused - but it is the first place the leg split
  changes the book at all, and it costs 0.027 CAR points to buy 2.1 points of drawdown.**
  `scripts/sweep_s28.py`, 18 DIAGNOSTIC ledger rows under `daily/s28_volest`, six clauses
  pre-registered plus one column labelled post hoc. The question S-26 and S-27 left: the book
  is sized by `target_vol / sigma` and `sigma` is a **close-to-close** estimate of a quantity
  61% of whose variance is the leg the book is not paid for. New default-inert hook in the
  shipped `signals.py` (`S1_VOL_RETURNS` / `set_vol_returns`, F-3's pattern) supplies the vol
  target's return window and nothing else; **I-1 gate re-run, 3,689/3,689, PASS**, and
  `diag_out=` added to `sweep_s25.legs_simulate` leaves every S-25/S-26/S-27 row bit-identical.
  **Identity passes to the digit** (22.192150% / 5,052 orders; leg identity 2.220e-16).
  **The diagnostic is real**: every leg forecasts its own next-21-session vol better than the
  pooled estimate does (cc->cc 0.7260, on->on 0.6764 against cc->on 0.6608, id->id 0.7492 on
  59,662 observations), with the two estimators 0.9029 correlated in log level and
  `sigma_on/sigma_cc` 0.5888. **All four books refused** at 2 bp + IBKR Pro financing:
  raw `on` 20.333% / DD **32.031** and raw `id` 20.084 / 30.196 are pure leverage (scale at cap
  on 86.3% of sessions - they delete the crisis de-risking); the level-matched primary `on_k`
  is 19.400 / **1.049** / **21.622** against 19.640 / 1.047 / 24.037, refused on CAR, paired
  -0.100 bps/day at t -0.92. **The placebo separates**: `id_k` moves the book the opposite way
  (+0.16 CAR for +1.43 DD) while `on_k` moves it -0.24 CAR for -2.42 DD, same machinery and
  same turnover - so it is the leg that pays, not any alternative estimator. **Post hoc, at
  matched risk** (scale 1.015): **19.613 / 1.046 / 21.931, a dead heat in return (t -0.08) for
  2.1 points less drawdown**, refused by 0.027 CAR points, **passing OOS on every criterion
  (26.007 vs 25.967, DD 20.67 vs 24.04) and failing IS**. **Do not re-open as an estimator,
  window, level-match or leg question** - the grid spans both legs raw and matched, the primary
  already wins on risk and loses on return, and nothing here reaches |t| = 2 because the vol
  target sizes the book on only 2.8% of sessions (4.7% under `on_k`), i.e. two crisis episodes
  that point opposite ways (2022 -3.8 points, 2015-16 +0.7). Two durable pieces survive it: the
  **`S1_VOL_RETURNS` hook** (any future risk-model input priced through the shipped algorithm
  without editing it) and **`diag_out=`** (when the vol target rather than the margin budget
  sets the book's size is now one column). It closes the leg-split program - hold (S-26), rank
  (S-27), size (S-28) - and adds the **third priced owner option** in `BLOCKERS.md`, the
  cheapest of the three: no futures permission, no Reg-T decision, only a change of default.

- **F-6 DONE 2026-09-12 (see journal): refused, 0 of 336 - and refused on ABSENCE rather than on
  cost, which is a mode this file has produced only three times.** F-6 took the one number S-27
  filed post hoc and did not pursue (an overnight-momentum score forecasting the next *intraday*
  leg at -2.230 bps/day, t -3.30, on the daily champion's nine ETFs) and gave it the three things
  it was missing: a **permitted universe** (the 56 names disjoint from the daily sleeve), an
  **instrument this sleeve already owns**, and its own pre-registration.
  `scripts/sweep_f6.py` on X-1's primitives unchanged; **2,647 sessions / 14,510,968 legs,
  2016-01-05..2026-09-09**; nine clauses, one labelled post hoc and counted as one.
  **0 of 336 net** and **0 of 168** on the effect-present-but-unaffordable screen, with **0 of 504
  regime-cells** reaching t < -2 in the fade direction. **Clause (6)'s written-down sign is
  refuted**: **156 of 168** pooled gross columns are POSITIVE (the gap extends), and **the largest
  |t| anywhere is 2.08** - nothing reaches significance in either direction before a cent of cost.
  Primary (neutral, all names, single gap): +0.10 / +1.04 / **+1.29** / +1.02 / +0.06 bps at
  t +0.10 / +1.34 / **+1.86** / +1.83 / +0.16 entering 09:31 / 10:01 / 10:31 / 11:31 / 13:31, hit
  rate 49.5-50.1%. **Not a cost refusal**: the best pooled fade is -0.32 bps (t -0.43), a
  **0.32 bps breakeven** against this store's 4.59 - **even F-2a's 0.488 ES contract would not
  clear it**, and one future cannot carry a 56-name cross-section. **S-27's by-product does not
  transport**: the same grid at the compounded overnight return of the last 5 and 20 sessions
  (L=1 reproducing the first table bit-for-bit as the identity check) gives zero passes where ~15
  would be expected by chance, best cells +0.94 (t +1.39) and +0.36 (t +0.50). **The raw book
  fails F-5's always-long control** at all 42 pooled cells (best t -2.03). **Do not re-open as an
  entry-minute, lookback, selection, exit or book question** - the grid spans all five on 2.6M
  sessions-worth of legs and the gross column is the wrong sign at every one of them. One durable
  piece survives: the rule that **a post-hoc result measured on nine correlated ETFs is a
  hypothesis about that universe, not about the mechanism**, so a by-product filed from the daily
  sleeve owes a transport test before it becomes an intraday lead - and `sweep_f6.py` is that test
  in its cheapest form. **It also removes the last intraday item with a stated mechanism and a
  permitted instrument**, so the Current objective's own instruction applies from here: say so
  rather than find a twelfth lever.

- **S-27 DONE 2026-09-12 (see journal): refused - the overnight leg is not forecast by its own
  history, so S-25's split is an attribution and not a signal recipe.** `scripts/sweep_s27.py`,
  12 DIAGNOSTIC ledger rows under `daily/s27_rank`, six clauses pre-registered. The champion's own
  blend recomputed on a **close-to-open compounded index** and ranked through F-3's
  `S1_ML_SCORES` hook (`ML_MODE="rank"`, no runner-loaded file edited). **Identity passes to the
  digit** (22.192150% / 5,052 orders) *after* catching a real defect in this script - a naive
  `pct_change` blend omits S-10's 5-session skip on horizons >= 120. **The diagnostic inverts the
  hypothesis**: cc and on score the overnight leg at **the same rank IC (+0.0574, t +7.25 / +7.32)**
  but the top-3-minus-EW spread the book actually collects is **+2.106 bps/day (t +3.24) against
  +1.311 (t +2.04)**, in both halves; nothing forecasts the intraday leg at all. **Primary refused
  on every criterion**: 11.751% / 0.656 / **DD 35.210** (past the absolute 35% limit) against the
  deployed 19.640% / 1.047 / 24.037, paired **-2.619 bps/day at t -2.41**, worse in both halves.
  **Placebo refused too** (intraday-ranked 13.167%, paired -2.270 at t -2.08). **Not an exposure
  artifact**: gross 1.24x vs 1.25x, and the same-gross overnight excess is +3.087 (t +4.20) cc,
  +1.686 (t +1.86) on, +1.183 (t +1.51) id - the shipped ranking is **1.8x** the overnight one at
  forecasting the leg that pays, on lower turnover. **Do not re-open as a lookback, skip, weighting,
  gate-mode or leg-index question** - the IC table says the ordering is identical and the spread is
  smaller, which is a signal-to-noise fact, not a tuning one. Post hoc and recorded, not pursued:
  the overnight score forecasts the next **intraday** leg at **-2.230 bps/day, t -3.30**, sign-stable
  in both halves, on names the disjointness rule bars the intraday sleeve from. Two durable pieces
  survive it: **`score_frame` + the three leg indices** (any leg-conditional ranking question now
  runs through the shipped algorithm unedited), and the rule that **a leg attribution may not be
  read as a feature-selection instruction without its own IC table**.

- **S-26 DONE 2026-09-12 (see journal): refused - and the first refusal here that is about RISK
  rather than cost, sign or significance.** `scripts/sweep_s26.py` + two default-inert arguments
  on `sweep_s25.legs_simulate`; 10 DIAGNOSTIC ledger rows; seven clauses pre-registered. The
  overlay shorts `h x beta x equity` of the index over the intraday leg on a causal trailing beta,
  charged 2 bp of equity spread, IBKR Pro financing and F-2a's **0.488 bps** futures round trip.
  Identity passes to the digit (22.192150%, residual 5.33e-16) and the **proxy is validated, not
  assumed**: corr(ES cash session, SPY open->close) **0.9994**, slope 0.9984, basis sd 2.1 bps over
  313 sessions, so **this overlay needs no CME purchase**. Vol-matched, **h=0.50 earns 20.837% /
  Sharpe 1.100 against 19.640 / 1.047, wins both halves (+0.72 IS, +1.66 OOS), stays inside Reg-T -
  and is REFUSED on drawdown, 26.02 against 24.04 + 1.0**; h=1.00 is refused on CAR everywhere.
  Paired +0.395 at **t +0.60**. **The placebo is the durable positive**: the same overlay on the
  *overnight* leg costs **-4.310 bps/day at t -4.14** against the intraday overlay's -1.373 at
  t -1.02, the only |t| > 2 in the file, so **S-25's split is confirmed by a second route**.
  **Breakeven +1.108 bps a round trip at h=0.50 against ES's 0.488** - the edge clears the cheapest
  instrument on file by 2.3x and dies on risk instead. **Do not re-open as a hedge-ratio, beta-window,
  benchmark or instrument question** - the ratio grid spans 0 to 1, the best ratio already clears
  the cost by a factor, and a cheaper instrument cannot fix a drawdown. Three durable pieces survive
  it: the **`hedge=`/`scale=` arguments** (any future overlay or risk-matched column runs on the
  deployed book without editing it), the **validated ES-to-SPY proxy** (an index-overlay question
  can now be priced with no futures history), and the rule that **matching daily volatility is not
  matching drawdown, so a vol-matched relever owes its own drawdown column**. It also corrects one
  prior number: a breakeven's turnover divisor must be growth-normalized, so S-25's printed
  breakevens are compressed ~4.3x and are signs rather than sizes (its conclusion stands - those
  books lost at zero cost). **What it leaves open is not research but an owner decision**: the
  un-relevered h=0.50 book trades 1.47 CAR points for 1.58 points of drawdown and +0.08 of Sharpe,
  now priced in `BLOCKERS.md`.

- **S-25 DONE 2026-09-12 (see journal): measured, not judged - the champion's alpha is an
  overnight object, and the two ops routes in `BLOCKERS.md` are an order of magnitude apart.**
  `scripts/sweep_s25.py` on S-19's validated harness, 3,689 sessions, 6 DIAGNOSTIC ledger rows,
  five clauses pre-registered. **+8.103 bps/day overnight (t +6.80, 94% of the return) against
  +0.738 intraday (t +0.47)**; against an always-invested control at the book's own gross the
  selection difference is **+3.087 (t +4.20) overnight and -0.314 (t -0.37) intraday**, in both
  halves. Not a dividend artifact (price-only +3.231, t +4.36) and not a print artifact (official
  crosses +8.864 vs +8.887). Both conditional books **refused at negative breakeven** - they lose
  at zero cost. Post hoc: the pre-open MOO move is **100% intraday** (+0.604, t +1.43; overnight
  -0.006) and the in-place alternative is worth **+0.18 CAR points** because its overnight leg is
  -0.572 (t -1.79). **Do not re-open as a leg-timing strategy question** - the two variants turn
  the book over 1,248x and 444x equity a year and are behind before a cent of cost is charged.
  Two durable pieces survive it: the leg attribution itself (`legs_simulate`, which reproduces the
  deployed book exactly and can split any convention this harness can run) and the rule that a
  daily-sleeve return statement must name its leg and carry the same-gross always-invested control.
  **What it leaves genuinely open**: the overnight leg is the only place this sleeve has ever shown
  alpha and it has never been *targeted* - a candidate that trades the overnight leg without paying
  for a daily round trip (holding period measured in nights, not sessions; or a sleeve chosen for
  its overnight behaviour) is the one direction this result points to, and it needs its own
  pre-registration and a cost model that survives 1,248x turnover, which nothing here does.

Owner-side status 2026-09-11 09:40 ET: the daily review says the backlog is out of cheap
mechanisms - ten refusals in 24 hours, every intraday candidate negative on 2,686 sessions,
0DTE refused at the quote, breadth refused, and the champion's return traced to its sizing
machinery. That is a finding, not a failure. The next program has to bring NEW information,
not new rules on the same bars. Two tracks are opened below; the second needs the owner.

- **F-3 DONE 2026-09-11 (see journal): refused, and the refusal is a comparison.** Pooled
  out-of-sample **IC +0.01133 (t +2.17)** over 2012-2026 but gross P&L t **+0.18** and only **0.304
  bps per dollar turned**, *less* than F-1's 0.797; the **ridge baseline beats the tree on IC**
  (+0.01223), so there are no interactions here. In LEAN, three cells at **10.322% / 9.908% /
  11.400% CAR** against the champion's 24.403%, all with drawdown above the 35% limit, all refused
  by `evaluate.py` on all four criteria - and worse than S-15's no-ranking-at-all 17.7%. **The
  diagnosis**: on the nine names the sleeve ranks, the forecast is **IC +0.00691 (t +0.97)** against
  the momentum blend's **+0.04268 (t +5.43)**, the two are +0.091 rank-correlated, and as unlevered
  top-3-of-9 books the blend earns **61.51 bps per dollar turned on 105k/day against the model's
  9.29 on 486k/day**. `scripts/sweep_f3.py`, 12 ledger rows, nothing shipped, control reproduces
  `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`, I-1 gate 3,689/3,689. **Do not re-open as a
  feature, model, horizon or universe question** - a longer feature list does not close a six-fold
  gap in the direction the simple signal already points. Two durable pieces survive it:
  `S1_ML_SCORES`/`S1_ML_MODE` (any future external forecast can be ranked through the shipped
  algorithm without editing it) and `evaluate.py`'s new refusal of runs whose window was moved.
- **F-3 (original text, kept for the pre-registration) The same supervised method at a DAILY
  horizon, on the daily sleeve (opened
  by F-1).** F-1's refusal is arithmetic, not a verdict on machine learning: a cross-sectional
  forecast worth 0.8-1.6 bps per dollar traded cannot survive a 0.7-1.4 bps commission floor when
  the book turns 13.8x its equity a day. The same bps of edge spread over a *hundredth* of the
  turnover is a different trade. Build the panel on the daily LEAN store (69 symbols, 1998-2026,
  `scripts/fetch_data.py`; the ETF sleeve is the trusted universe - the single names are
  survivorship-biased and must be excluded from any tradable book, features only), target = next
  5-day or next 21-day cross-sectionally demeaned return, features the daily analogues of F-1's
  (multi-horizon momentum, distance from moving averages in ATR units, realized-vol ratios, volume
  against its own trailing median, the market's own features, cross-sectional ranks). Same
  discipline as F-1 and it is what made F-1 readable: walk-forward expanding retrain, a
  shuffled-label falsification control, a ridge baseline, and the decisive column reported as
  **gross bps per dollar turned over against the cost floor** rather than as P&L. Judge the book
  through LEAN (`scripts/backtest.py` + `scripts/evaluate.py`) against the champion at the same
  cost model (S-18's `stats_by_spread` rule), at 0 bp and at 2 bp. Pre-register before fitting:
  beats the champion on `evaluate.py`'s criteria in the 2020-2026 out-of-sample half, or it is
  refused. **Carry F-1's three usable facts forward**: the target must be in basis points or
  sklearn's absolute early-stopping `tol` silently stops the fit at iteration 1; early stopping
  must use an explicit time-ordered `X_val`/`y_val`, never `validation_fraction`; and the model's
  edge was in the interactions, so the ridge baseline is the control that says whether a tree is
  earning its complexity.
- **F-1 DONE 2026-09-11 (see journal): a real out-of-sample forecast - pooled IC +0.0113 at
  t = +4.74, gross +$1,102/day at t = +3.04 - refused because it earns 0.797 bps per dollar traded
  against a 0.892 bps commission floor at zero spread. Nothing shipped.** `scripts/sweep_f1.py`;
  1.59M-row panel (56 tradable names, 2,682 sessions, 11 decisions/session, 38 causal features),
  train 2016-2021 / validate 2022-2023 / test 2024-2026 with a yearly expanding retrain; 5 ledger
  rows under `intraday/f1_gbdt`. Net **-$2,206/day at t -6.02**, **0 of 3 test years positive**.
  Breakeven slippage by decile **+0.129 / -0.095 / -0.229 / -0.360 bps**; the only cell that clears
  commission does so by 0.129 bps against a 0.3-1.0 bps tick and posts a **-$81,038** worst day on
  $1M. Falsification control (labels shuffled within each timestamp) 0.071 gross bps, a ninth of
  the model's; ridge baseline validation IC +0.0027 against the tree's +0.0105. IC decays by test
  year **+0.0192 -> +0.0113 -> -0.0001** while permutation-importance ranks stay stable at
  0.66-0.77 correlation, the top features being VWAP deviation, its cross-sectional rank and
  relative volume. **Do not re-open as a feature, model, decile or retrain-frequency question** -
  the gap between edge and cost is a factor, not a percent, and every knob inside this design was
  measured. The successor is **F-3**, above: the same method where the turnover is a hundredth.
- **F-1 (original text, kept for the pre-registration) Supervised intraday forecaster on the
  ten-year minute store.** Stop hand-
  designing rules. Build a walk-forward machine-learning model on `data/minute_alpaca` for the
  50 megacaps + the 16-name universe: features per 5-minute bar (returns at 5/15/30/60 min,
  VWAP deviation, range/ATR ratios, volume vs 20-day same-time-of-day average, opening gap,
  time-of-day, day-of-week, cross-sectional rank of each feature across names, the market's
  own features), target = next-30-minute return net of the cost model. Gradient boosting
  (`lightgbm` or sklearn `HistGradientBoostingRegressor`), trained on 2016-2021, validated on
  2022-2023, tested on 2024-2026, retrained yearly (expanding window). Judge on out-of-sample
  P&L after costs of a long-top-decile / short-bottom-decile book rebalanced every 30 minutes,
  and on feature importance stability. Report honestly if it is zero; this is the one
  mechanism class the loop has not tried, and it is the one that scales with the data we now
  have. Pip installs allowed. Nothing deploys without positive in two of three regimes.
- **F-2a DONE 2026-09-11 (see journal): the blocker was mis-stated. Permission is not missing -
  retention is - and the instrument's round trip is 0.488 bps.** The account fetches ES/MES/NQ/MNQ
  1-minute TRADES bars with **zero errors**; IBKR keeps ~**four expired quarters** (ESU5 serves,
  ESM5 does not) and **CONTFUT refuses an `endDateTime` (error 10339)** and caps a minute request at
  one month, so the continuous series cannot be paged. Front-quarter stitch: **447,600 bars / 313
  sessions, 2025-06-09..2026-09-10** (`data/futures/ES.parquet`, gitignored). **Cost floor, the
  durable half**: $347,117 of notional, $2.05/side all-in, one tick wide -> **0.488 bps round trip**
  (0.856 full tick, MES 0.744) against L-1's 6.40-8.20, X-1's 4.70 and F-1's 0.892 of commission
  alone - **10x-17x cheaper**, which is decisive because every intraday refusal on file was a
  refusal on cost. **Both pre-registered mechanisms refused**: overnight-into-the-open +1.161 bps at
  **t +0.78** (gone by 11:00), day-momentum-into-the-last-30m **-2.415 at t -2.56**, i.e. significant
  with the premise's sign reversed. The reversal (+1.927 net, t +2.05) is recorded **post hoc** and
  is concentrated in the first half, but X-1 measured the same shape on equities over 2,684 sessions
  (**-0.69 bps at t -2.80** at 14:30). `scripts/futures_data.py`, `scripts/sweep_f2.py`, 4 ledger
  rows, nothing shipped, no runner-loaded file modified. **Do not re-open as a mechanism question on
  this store** - 313 sessions is 16% of A-4's power requirement and A-10 is the standing lesson.
  Two durable pieces survive it: the **cost table** (the number that justifies the purchase) and the
  **front-quarter stitcher**, so the day deeper history arrives the harness already runs.
- **F-2 (original text, kept for the pre-registration) Index futures track (needs owner: IBKR
  futures permission + CME data, or a Databento
  key for ES/NQ minute history).** ES/NQ trade 23 hours with 20x built-in leverage and no
  daily-reset decay; overnight session momentum into the cash open and the 15:30-16:00 futures
  flow are documented effects that the equity-only data cannot express. Prepare the harness
  (contract roll, tick value, CME fees) so the day the data arrives the tests run.
- **F-5 DONE 2026-09-12 (see journal): refused, 0 of 144 cells - and the always-long control is
  what refuses it, which retro-diagnoses F-4's own momentum column.** F-4 left one piece of
  arithmetic unfollowed (its rule about cheap instruments, applied only to the wrong sign); F-5
  put it to the instrument that could carry it. `scripts/sweep_f5.py`, **SPY / QQQ / IWM**,
  `data/minute_alpaca`, **2,687 sessions / 367,872 legs, 2016-01-04..2026-09-10**; seven clauses
  pre-registered. **Nothing measured here is deployable on the intraday equity sleeve** (the three
  index ETFs are the daily champion's, AGENTS.md disjointness) - the only instrument is the index
  future. **0 of 144** cells reach net t > 2 in two of three regimes. **The diagnosis is clause
  (5)**: session-clustered, `todate`/`flatten` gross is +1.55 bps (t +2.42) but the **always-long
  book on the identical windows earns +0.54** and the forecast difference is **+1.01 at t +0.89**,
  by regime **-0.78 / +1.83 / +2.47** - negative in the first third; **5 of 138 cells** beat the
  control at t > 2 against ~3.2 expected by chance, all five at one entry minute. The index
  reproduces F-4's column at the same minutes and size (11:30 gross +1.99 / +3.64 / +1.57 against
  F-4's +2.24), so **F-4's raw book was a market-factor bet and about a third of its gross is
  drift**. The **published market-intraday-momentum effect is absent**: the classic cell (first 30
  minutes -> 15:30 to the flatten) is gross **-0.19 / +0.10 / +0.05 bps at |t| <= 0.73**, best-t
  book CAR 0.90% / Sharpe 0.25. Nearest miss, post hoc and failing both clauses: QQQ 15:00 ->
  flatten, net +2.03 (t +2.66) but 1 of 3 regimes and +1.75 (t +1.54) over always-long; 1x book
  CAR 4.99% / Sharpe 0.82 / DD 8.4%, so ~10x on the future for the 3%/day mandate at a -36% worst
  session. **Do not re-open as an entry-minute, index, signal-definition or holding-period
  question** - the grid spans all four on 2,687 sessions and the control is what kills it, not the
  grid. Two durable pieces survive it: the **always-long control rule** (a directional intraday
  book is quoted against always-long on the identical windows before its gross is called
  momentum - the time-series twin of the daily sleeve's vol-matched control), and the closing of
  F-4's loose end, which removes the third leg of the CME purchase case in `BLOCKERS.md` while
  leaving the cost table and the 0.62% gross sd per contract standing.
- **F-4 DONE 2026-09-11 (see journal): refused, and refused on SIGN rather than on cost - which
  is the stronger refusal and the one clause (5) did not expect.** `scripts/sweep_f4.py`, 56
  names disjoint from the daily sleeve, **2,664 sessions / 6,654,000 legs, 2016-01-04..2026-09-09**
  - the largest sample this repository has put on one mechanism. **0 of 96 cells** pass the
  pre-registered mark (12 entry minutes x 2 books x 2 exit conventions x 2 signs) and **all 96 net
  columns are negative**, the best being raw momentum at 11:30, **-2.35 bps at t -2.74** against a
  **4.59 bps** pooled round trip. **The gross column is positive at 12 of 12 entry minutes in the
  directional book and 10 of 12 in the dollar-neutral one**: the day's move extends, it does not
  fade, and every gross statistic in the grid reaching |t| > 2 is momentum - neutral 11:30 +1.78
  (t +3.54), raw 11:30 +2.24 (t +2.61), raw 15:00 +0.89 (t +2.48), and the largest single-regime
  cell is **2020-2023 at 15:00, +2.18 at t +3.38 - A-10's exact entry minute with the opposite
  sign**. The second screen (is the effect there but unaffordable?) returns **0 of 48**. Where the
  sign does survive it is a whisper in the diagnostic book only: neutral afternoons, 2024-2026
  -0.81 / -0.59 / -0.42 bps at 14:00 / 14:30 / 15:00 (**t -1.11 / -0.98 / -0.85**) and 2016-2019
  -0.22 / -0.16, i.e. two of three regimes at a fifth to an eighth of cost and never past |t| = 1.2.
  **It does not contradict X-1, it fails to reach it**: X-1 ranked a 15/30/60-minute lookback held
  30-60 minutes; F-4's signal is the whole session's return held to the flatten. **The cheap
  instrument does not rescue it**: charged F-2a's 0.488 bps ES round trip the same legs give
  **0 of 24** and every cell is still negative (-0.37 to -2.73). Stage 2 was not run, on clause (7)
  - a framework run is earned by a stage-1 survivor and there is none - and no ledger rows are
  written, because a stage-1 event study measures bars rather than running a strategy. **Do not
  re-open as an entry-minute, universe, holding-period or magnitude-filter question.** One durable
  rule survives it: **a cost refusal is an argument for a cheaper instrument only when the gross
  column has the right sign at |t| > 2; when the sign is wrong the cheap instrument buys a smaller
  loss, not an edge** - which corrects F-2a's own closing sentence. The only thing left genuinely
  open is the object F-4 did not test and X-1 did: a SHORT lookback reversal at a SHORT horizon,
  a different mechanism that would need its own pre-registration.
- **F-4 (original text, kept for the pre-registration) the afternoon reversal, on the store that
  can actually resolve it.**
  Two independent samples now point the same way - X-1 on 2,684 sessions of megacap equities
  (**-0.69 bps at t -2.80** into 14:30) and F-2a on 313 sessions of ES (**-2.415 bps at t -2.56**
  into the close) - and in both cases it was filed as a by-product rather than tested as a
  mechanism. Test it properly where the power is: `data/minute_alpaca`, 60 symbols, 2016-2026,
  through the shipped intraday framework with the real per-share commission. Pre-register before
  fitting: the signal is the sign of the session's return to time T, the trade is T -> close, and it
  must be positive in **two of three regimes at t > 2** after costs, as every A-track candidate has
  been. **Expect it to fail on cost, not on sign** - that is what X-1's own +0.36 bps against a
  4.70 bps round trip predicts - in which case the result is not a strategy but the **third**
  measurement of an effect whose only viable instrument is the one with a 0.488 bps round trip, and
  that is an argument for the F-2 purchase rather than for a twelfth equity lever.

**2026-09-11 (S-2): the backlog now holds no open research item with a stated mechanism.** A-12,
A-11 and S-2 closed the last three. What remains under "Open" is parked (A-8, by A-4's power
calculation), settled elsewhere (A-3, by A-10), infrastructure (D-2b, E-2b), a standing
per-session measurement (A-5 part 2, ~6.8 sessions from settling), or blocked on a second positive
sleeve that does not exist (S-5). **The binding constraint is the four owner decisions in
`BLOCKERS.md`**, not a missing idea.

- **S-24 DONE 2026-09-11 (see journal): measured, not judged. The harness's "open" is not the
  opening cross, and at the price a real MOO order receives the pre-open move is worth +1.98 CAR
  points.** The daily store's **close is the official closing cross to the cent on every session of
  all nine names** (implied close factor, median day-over-day change exactly 0.000 bps); its
  **open is the first consolidated print, not the primary auction**, so the pre-open identity clause
  failed at **82.18% within 2 bps** against a pre-registered 95%. Re-filled at the official cross on
  2,683 sessions: deployed **22.007%**, S-23's assumption 24.134%, **the real MOO fill 23.985%** -
  the benchmark defect is **-0.149 CAR points** (paired -0.047 bps/day, t -1.86), and the 2 bp
  charged to a call-auction fill that crosses no spread is an overcharge, so the honest band is
  **+1.98 to +3.20**. The surcharge S-23 bounded at 3.10 bps measures **~0.22 bps**, 7% of the
  budget. The pre-registered unsigned statistic (6.12 bps) was **mis-specified and the matched
  placebo caught it**: 30 auction-free seconds move the same names 4.10 bps, signed the cross sits
  -0.213 bps from fair value, and at S-17's 0.68 CAR/bp a real 6.1 bps cost would have shown up as
  ~4.2 CAR points instead of 0.149. `scripts/sweep_s24.py`, 4 ledger rows, nothing shipped, no
  runner-loaded file modified so rule (a) owes no replay. **Do not re-open as an auction-cost
  question** - it is now measured on the official prints at both ends and the residual is a fifth of
  a basis point. Three durable pieces survive it: the **auction store** (`data/auctions/`, official
  opening and closing crosses for the sleeve, 2016-2026) and the `cross_frames` substitution, which
  let any future execution question be asked at real auction prices; the finding that **the store's
  close is exact and its open is not**, which every future "open" number in this repository is
  subject to; and the rule that **an execution cost must be measured with a sign, or by re-filling
  the book, never as an unsigned distance**.

- **S-23 DONE 2026-09-11 (see journal): the loop's half of the pre-open request is written and
  gated, and the move now has a breakeven instead of an assumption.**
  `scripts/paper_trade.py --order-type MOO` sends the order IBKR accepts (`MKT` + `tif="OPG"`) and
  **refuses before connecting** outside 04:00-09:28 ET, because IBKR rejects `OPG` one order at a
  time and a half-rebalanced book is worse than no rebalance (proved live, exit 3). `MKT` remains
  the default: the `--mock --dry-run` plan is unchanged and the **I-1 gate passes 3,689/3,689 at
  5,021 orders**. `scripts/sweep_s23.py` prices both conventions through S-19's book with S-22's
  financing hook: deployed **19.640%** (S-22's figure to the digit) against pre-open **21.515%**,
  **+1.875 CAR** (+1.844 at today's rates), paired **+0.609 bps/day at t +1.44** - *not* significant
  - and out-of-sample weighted more than three to one (IS +0.963, OOS +3.222). **The new number**:
  the opening auction may cost up to **3.10 bps more than the closing auction** before the move
  stops paying, against **+3.2 bps** of measured live execution cost and a minute-store proxy that
  puts the opening minute at **1.0x-2.0x** the closing minute's width (IWM 2.00). So the margin is
  real but thin, and the recommendation is unchanged. 4 ledger rows, nothing shipped, no default
  changed, no task touched. **Do not re-open as a "what is the real opening spread" question from
  this data** - the store has no quotes, so it cannot answer; `daily_fills.py` now scores MOO fills
  against the **open** they aim at, and the first post-move session settles it with live fills.
  Two durable pieces survive it: the `build_order()` helper (any future order type is one branch)
  and the rule that an execution change here is quoted as a **breakeven in `daily_fills.py`'s own
  units**, not as a CAR delta against a costless counterfactual.

- **S-22 DONE 2026-09-11 (see journal): measured, not judged. The three instrument corrections are
  independent, and the deployed daily book's honest expectation is ~20% CAR, not 24.4%.**
  LEAN full-period factorial: control 24.403 / spread 2 bp 23.068 / financing 23.087 / clock bound
  21.384 / **all three 18.785**, against a **pre-registered multiplicative null of 18.811** - an
  interaction of **-0.026 points**, every pair inside 0.021. The S-19 pandas book (new optional
  `financing=` argument, S-19's own rows bit-identical) prices the convention LEAN cannot express:
  the deployed 15:45 clock fully charged earns **19.640%, i.e. 19.954% in LEAN units, -4.449 points**,
  and **19.415% at today's 3.63% benchmark**; its `lag1` cell agrees with LEAN's to **0.03 CAR
  points**. Halves **IS 14.194 / OOS 24.259** against 17.698 / 32.801, out-of-sample weighted more
  than two to one, and drawdown is flat across the whole factorial (23.70 -> 23.00), so it costs
  return and not risk. `scripts/_s22_runs.sh`, `scripts/sweep_s22.py`, 25 ledger rows, nothing
  shipped, control reproduces `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`, I-1 gate 3,689/3,689
  at 5,021 orders. **Do not re-open as a fourth-defect or an interaction question** - the factorial
  is complete and the residual is a fortieth of a CAR point. Two durable pieces survive it: the
  financing hook on `sweep_s19.py` (any future execution question can now be asked on a financed
  book) and the rule that **defects on this sleeve compose multiplicatively**, so they may be priced
  one at a time and multiplied, which is what makes the three audits reusable rather than stale.

- **S-21 DONE 2026-09-11 (see journal): measured, not judged. LEAN charges no financing, and the
  champion's leverage costs 1.32 CAR points full period, 2.03 out of sample and about 2.0 a year
  forward.** `DefaultBrokerageModel.cs:368` -> `MarginInterestRateModel.Null` (empty
  `ApplyMarginInterestRate`), not overridden by the IB model. The book runs a debit balance on
  **83.3% of sessions averaging 0.493x of equity** and has never paid for it. Full period
  **23.087% / 0.939 / DD 24.1%** against 24.403% / 0.994 / 23.7%; IS -0.907, **OOS -2.027**;
  **82% of the sample's $129k of interest was incurred in 2023-2026** as the benchmark went from
  ~0.1% to 5%. Benchmark-only is 0.559 of the 1.106 simple points, so about half is irreducible
  and half is a markup a larger account pays less of. `scripts/rates.py`, `scripts/sweep_s21.py`,
  `scripts/_s21_runs.sh`, 8 ledger rows, `S1_FINANCING` **defaulted off**, control reproduces
  `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`, I-1 gate 3,689/3,689 at 5,021 orders.
  **Do not re-open as a rate-source, tier or day-count question** - the schedule sensitivity is
  already tabulated (`--schedule`) and the two implementations agree on the state. **It is not a
  defect to fix**: the paper account is already paying it and the runner is correct. Two durable
  pieces survive it: the corrected owner frontier in `BLOCKERS.md` (0.75 / 0.80 / 0.82 =
  23.087 / 24.296 / 24.742 financed, so the reward for spending the Reg-T buffer is a fifth
  smaller and its Sharpe argument six times weaker) and `evaluate.py`'s refusal of
  `S1_FINANCING=on` runs as not comparable.

- **S-20 DONE 2026-09-11 (see journal): refused. The regime gate's off-state stays cash, and the
  refusal is the vol-matched column.** The gate is off on **590 of 3,690 sessions (16.0%)** and has
  held nothing there since S-1. Giving it a defensive sleeve (shipped momentum ranking over
  TLT/IEF/GLD, top 1) earns **26.550% / 0.972 / DD 25.4% / std 0.177** against the champion's
  24.403% / 0.994 / 23.7% / 0.155 - +2.15 CAR at *lower* Sharpe - and **scaled to its own realized
  vol the champion would have earned 27.867%, so the mechanism is -1.32 CAR points worse than
  running the existing book bigger**. Paired +0.90 bps/day at t 0.83; `evaluate.py` refuses it at
  0 bp on the drawdown tolerance and passes it at 2 bp, and the pre-registered rule required both.
  The a-priori control (TLT alone) is -2.10 vol-matched; the only positive cell is the **post-hoc**
  GLD-alone pick (+0.656), chosen after reading the probe table, on a conditionality statistic of
  t = 1.66. `scripts/sweep_s20.py`, `scripts/_s20_runs.sh`, 9 ledger rows, nothing shipped, control
  reproduces `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`, I-1 gate 3,689/3,689 at 5,021 orders.
  **Do not re-open as a sleeve, `top_n` or threshold question** - what would change the answer is a
  defensive asset with a *conditional* crisis payoff, and there is none in this store. Two durable
  pieces survive it: `risk_off_sleeve`/`risk_off_top_n` (a future conditional asset can be tested
  without editing the algorithm) and the measurement that **`risk_off_exposure` is inert over
  [0.5, 1.0]** because the vol target cancels an exposure request under a flat margin budget -
  S-8's finding restated for the off-state.

- **S-19 DONE 2026-09-11 (see journal): the deployed daily runner's clock is worth ~1.9 CAR points,
  not 4.75, and the correction is two parts instrument and one part the S-18 promotion.** Six LEAN
  cells (`scripts/_s19_runs.sh`) and a validated pandas book (`scripts/sweep_s19.py`), 10 ledger
  rows, control reproducing `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`. On the promoted
  champion `S1_SIGNAL_LAG=1` is **-3.02 CAR at 0 bp / -2.99 at 2 bp** (S-17 measured -4.75 on the
  retired 3x book), and that cell is an *upper bound* because LEAN cannot fill at the close of the
  session it decided in; the book that can prices the deployed convention at **-1.885 CAR, paired
  -0.599 bps/day at t -1.41**, i.e. **61% of the bound**, after validating against the control's own
  LEAN equity curve at **corr 0.99650**. `BLOCKERS.md` is corrected in place. **Do not re-open as a
  "what is the real lag" question** - the convention is proved from the runner's own log and the
  arithmetic is now done at both ends. Two durable pieces survive it: `sweep_s19.py` can execute the
  shipped signal at any fill convention (the harness any future execution question needs), and the
  measurement that **LEAN's reported Sharpe and Annual Standard Deviation are resampled onto
  calendar days** and so sit ~17% below the same curve's trading-day figures - safe to compare
  within the ledger, never against a statistic computed elsewhere.

**Priority after F-2a (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing
per-session measurements, unchanged and both ~4.4 sessions from settling; (2) per-session ops;
(3) F-4, the afternoon reversal on the Alpaca store - the only open item with a mechanism, a
pre-registration and enough sessions to resolve it, opened above; (4) the owner decisions in
`BLOCKERS.md`, unchanged in order - the pre-open move (+1.98 CAR at the real MOO fill), the Reg-T
buffer, `equity_frac` on the intraday sleeve - now joined by a **fifth** that is a purchase rather
than a policy: CME history back to ~2016 for ES/NQ, which F-2a priced at a 0.488 bps round trip
against the 4.70-8.20 bps that has refused every intraday candidate on file.** F-2a opened F-4 and
closed the last "needs data" item that had never been checked; the reusable rule it leaves is that
**a blocker nobody has probed is an assumption**, and this one was wrong in its subject (retention,
not permission) and understated in its value. One column is added to the compulsory four: any future
candidate that could be expressed on futures owes **the cost floor of the instrument it would
actually trade on**, because on this repository's evidence that floor, not the signal, has decided
every intraday verdict.

Superseded, kept for the reasoning: **Priority after S-24 (2026-09-11): unchanged in order from S-23 below, with one item now fully
priced.** The pre-open move is no longer carrying an assumption - it is **+1.98 CAR points** at the
real MOO fill (band to +3.20), the surcharge is **~0.22 bps against a 3.10 bps breakeven**, and the
loop has nothing further to add to that decision. The compulsory columns are now four: vol-matched
(S-20), financed (S-21), the breakeven surcharge for anything that moves *where* an order fills
(S-23), and - new - **priced at the official auction print rather than the store's open** (S-24),
because the store's open is the first consolidated print and only its close is the real cross.

**Priority after S-23 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~4.4 sessions from settling, and `daily_fills.py` now carries the instrument that settles the S-23 breakeven the moment the task moves; (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, unchanged in order but with the top one now reduced to a single task change: the **pre-open move** (+1.844 CAR at today's rates, breakeven +3.10 bps of extra opening-auction cost, the loop's half merged and gated), then the Reg-T buffer (+1.209 / +1.655 financed at budget 0.80 / 0.82) and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** S-23 opened nothing: it finished a request rather than starting a line of research, and the one general thing it leaves behind is a framing rule - **an execution change on this sleeve is quoted as a breakeven in the units `daily_fills.py` measures on live fills**, because a CAR delta against a counterfactual that charges the other side nothing is not a decision, it is an assumption. The three compulsory columns are now vol-matched (S-20), financed (S-21) and, for anything that moves *where* an order fills, the breakeven surcharge (S-23).

Superseded, kept for the reasoning: **Priority after S-22 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~4.4 sessions from settling and `daily_fills.py` now gets input every rebalance (10 fills, +3.2 bps, se 4.5); (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, which remain the whole of the unblocked work, now in a corrected order of value: the **pre-open task move** is the cheapest and best-priced of them at **+1.85 CAR points on an honestly-costed book at today's rates**, then the Reg-T buffer (+1.209 / +1.655 financed at budget 0.80 / 0.82) and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** S-22 closed the instrument audit rather than opening anything: spread (S-17), clock (S-19) and financing (S-21) are now measured, composed and **proved independent to 0.026 CAR points**, so there is no fourth defect of that class to look for and no reason to re-run the three against each other. **One number replaces another everywhere on this sleeve**: the deployed daily book's honest expectation is **~20% CAR (19.95% at historical rates, 19.42% at today's)**, not the champion's 24.403%, and any future candidate quoted against the headline is being flattered by about 18%. The two compulsory columns from S-20 (vol-matched) and S-21 (financed) are unchanged, and S-22 adds the rule that makes them cheap: **corrections on this sleeve multiply**, so a cell may be priced against one defect at a time and composed afterwards.

Superseded, kept for the reasoning: **Priority after S-21 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~4.4 sessions from settling and `daily_fills.py` now gets input every rebalance (9 fills, +3.9 bps); (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, which remain the whole of the unblocked work and whose headline item has just been re-priced: the Reg-T buffer now reads +1.209 / +1.655 CAR at budget 0.80 / 0.82 rather than +1.500 / +2.071, with the Sharpe argument six times weaker; then the runner's clock (-1.9 CAR, S-19) and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** S-21 opened nothing and closed nothing that was open - it moved a number, and it is the third and last of the instrument audits that were available (spread S-17, clock S-19, financing S-21). **Two columns are now compulsory on any future daily-sleeve comparison**: the vol-matched one (S-20) whenever a cell changes realized volatility, and the financed one (S-21) whenever two cells carry *different amounts of leverage* - the second exists because the owner's own frontier was being judged on numbers that gave the borrowing away.

Superseded, kept for the reasoning: **Priority after S-20 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~4.4 sessions from settling and gets input every session; (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, which remain the whole of the unblocked work: the Reg-T buffer (budget 0.78 / 0.80 / 0.82 earn 25.307 / 25.903 / 26.474 at rising Sharpe on the unlevered book), the runner's clock (-1.9 CAR, S-19), and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** S-20 closed the last daily-sleeve item that was neither a ranker lever nor a risk-posture parameter, and it closed it by measuring that it *is* a risk-posture parameter in disguise. **Read every future daily-sleeve cell through the vol-matched column** (`sweep_s20.py --report`): S-15, S-16 and S-20 are three forms of one finding - on this sleeve anything that looks like new return is a size decision until it beats the control scaled to its own realized volatility.

Superseded, kept for the reasoning: **Priority after S-19 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~4.4 sessions from settling and gets input every session; (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, which remain the whole of the unblocked work, now in a corrected order of value: the Reg-T buffer (S-16/S-18: budget 0.78 / 0.80 / 0.82 earn 25.307 / 25.903 / 26.474 at rising Sharpe on the unlevered book), the runner's clock (**-1.9 CAR**, re-priced by S-19 and no longer the largest number on this sleeve), and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** S-19 did not open an item; it closed one and moved a number.

Superseded, kept for the reasoning: **Priority after F-3 (2026-09-11), in order: (1) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements - A-5 part 2 is ~5.5 sessions from settling and now gets input every session; (2) per-session ops; (3) the owner decisions in `BLOCKERS.md`, which are now the whole of the unblocked work, in order of the number attached to them: the runner's clock (-4.75 CAR, the largest unblocked number on the daily sleeve), the Reg-T buffer (S-16: budget 0.78 / 0.80 / 0.82 earn 25.307 / 25.903 / 26.474 at rising Sharpe on the now-unlevered book), and `equity_frac` on the intraday sleeve; (4) F-2, the index futures track, which needs data the human must buy.** The supervised track is closed by F-1 and F-3 together: the model finds an IC of about +0.011 wherever it is pointed, and on both sleeves it rides a weaker mechanism than the one already shipped - intraday it could not clear its commission, daily it could not out-rank a four-horizon momentum blend that is itself a t = +5.4 signal worth 61 bps per dollar turned.

Superseded, kept for the reasoning: **Priority after F-1 (2026-09-11), in order: (1) F-3, the
supervised method at a daily horizon -
F-1 proved the method finds real out-of-sample signal on this data and refused it on turnover
arithmetic, so the next run is the same method where the turnover is a hundredth; (2) A-5 part 2
and `daily_fills.py`, the two standing per-session measurements (A-5 part 2 is ~5.5 sessions from
settling and now gets input every session); (3) per-session ops; (4) the owner decisions in
`BLOCKERS.md` - the Reg-T buffer, which S-18 made more valuable, and the runner's clock, which is
the largest unblocked number on the daily sleeve at -4.75 CAR.** The intraday sleeve has now been
refused by a rule-based track (A-3 .. A-12), by every instrument the owner's mandate named (O-1,
O-1b, L-1, X-1, O-2, S-2) and by a supervised model with a measurably real forecast (F-1). Its
binding constraint is not a missing signal - it is that 13.8x daily turnover costs more than any
30-minute forecast measured here is worth.

Superseded, kept for the reasoning: **Priority after S-18 (2026-09-11), in order: (1) F-1, the
supervised intraday forecaster - the only
open item left with a mechanism, and the one class of model this loop has never tried; (2) A-5
part 2 and `daily_fills.py`, the two standing per-session measurements (A-5 part 2 is ~6 sessions
from settling and now has live input every session); (3) per-session ops; (4) the owner decisions in
`BLOCKERS.md` - the Reg-T buffer, which S-18 made more valuable, and the runner's clock, which is
the largest unblocked number on the daily sleeve at -4.75 CAR.** S-18 closed the daily sleeve's last
unblocked research item by promoting it; every remaining daily-sleeve lever is a risk-posture
parameter and therefore the owner's.

Superseded, kept for the reasoning: **Priority after S-17 (2026-09-11), in order: (1) S-18 - promote
the unlevered cell properly, which is the first daily-sleeve candidate since O-1b that no owner
answer blocks; (2) A-5 part 2 and `daily_fills.py`, the two standing per-session measurements;
(3) per-session ops; (4) the owner decisions in `BLOCKERS.md`, which now include the runner's
clock.** S-17 replaced the post-S-16
conclusion that only owner decisions remained: that was true about strategies and wrong about the
instrument. The harness charges no spread (0.68 CAR per bp, and the cells it has been ranking differ
by 2.7x in order count), and the deployed runner acts on a signal a session stale (-4.75 CAR). Both
are measurement defects, which is why sixteen iterations of sweeping could not see them. Everything
else under "Open" is parked, settled, infrastructure, or an owner decision. Do not open a new
intraday lever (the A-track is out of both levers and defences, and the S-track's last mechanism
closed with S-2), and **do not open a new ranker lever**: S-15 priced the ranker at +3.66 CAR at
t = 0.92 vol-matched, and S-14 showed it does not survive dilution. The two components that carry
the book - the vol target / margin budget (71% of the return) and the regime filter (the drawdown
profile) - are risk-posture parameters, so the next move on this sleeve is an owner decision, not
a backtest.

- **S-18 DONE 2026-09-11 (see journal): promoted. The champion is the unlevered book - same return,
  0.073 more Sharpe, 4.2 fewer points of drawdown at 2 bp, 40% less commission, 1.50x exposure
  against 2.25x.** Eight cells (`scripts/_s18_runs.sh`, `scripts/sweep_s18.py`) plus three
  verification runs; new `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`, and `S1_PROXY=on
  S1_DD_HALVE=0.15 S1_DD_FLAT=0.25` reproduces the retired champion bit-for-bit. Halves: IS
  **-1.48 CAR (t -1.25)**, OOS **+1.94 (t +0.87)**, Sharpe better in both. `evaluate.py` now
  compares at the same cost model (`champion.json.stats_by_spread`, `backtest.py` records the
  `S1_*` environment) and produced both verdicts: 2 bp BEATS, 0 bp refused by 0.001. Band measured
  on the new book and **not** changed (+0.103 CAR at 2 bp, t +0.94). **Do not re-open as a proxy or
  breaker question** - both are retired on three iterations of evidence and one environment variable
  away. **The successor is not another S-track cell**: what is left on this sleeve is the owner's
  margin-budget question (now worth more: 0.78 / 0.80 / 0.82 give 25.307 / 25.903 / 26.474 at rising
  Sharpe on the unlevered book) and the runner's clock (-4.75 CAR, S-17), both in `BLOCKERS.md`.
- **S-18 was opened by S-17 2026-09-11 as: promote S-16's (e+g) cell at the unchanged
  0.75 margin budget - the first daily-sleeve candidate since O-1b that no owner answer blocks.**
  The cell is `S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0` (unlevered parents, no drawdown
  breaker, budget untouched at 0.75, economic exposure 1.50x against the champion's 2.25x). At zero
  spread it is a dead heat refused by 0.001 CAR points; at any spread above ~0.03 bp it wins on CAR,
  Sharpe and drawdown at once (2 bp: **23.068 / 0.938 / DD 25.0 / $24.9k fees** against the
  champion's 22.926 / 0.865 / 29.2 / $41.9k). **Three pieces are missing and each is a run, not a
  judgement call:** (a) the in-sample 2012-2019 and out-of-sample 2020-2026 halves at this
  configuration, which S-16 only produced for the budget-0.80 variant, run both at 0 bp and at 2 bp;
  (b) a decision on what `evaluate.py` compares against, because the recorded champion stats are
  zero-spread and a candidate charged 2 bp cannot be measured against them - the like-for-like
  comparison is the one in journal section 4 and the promotion should be made on it, with
  `champion.json` recording both columns; (c) `scripts/compare_orders.py` re-run and a new
  `OrderListHash` baselined, since promotion moves the live order list (I-1's deploy gate). **Do not
  promote on the return difference** - it is +0.05 bps/day at t = +0.12. The case is identical
  return for 0.073 more Sharpe, 4.2 fewer points of drawdown and 40% less commission, and the
  write-up must say that. Related and cheap once (a) is running: `min_order_value` 0.03 is worth
  +0.57 CAR at 2 bp (t +1.22) with 3.8 fewer points of drawdown, so the band should be swept on the
  *promoted* cell rather than on the champion, and S-13's warning that its fine structure is path
  luck still stands.
- **S-17 DONE 2026-09-11 (see journal): the harness charges no spread and the deployed runner is a
  session late. Nothing shipped, nothing promoted, no default changed.** Two new knobs on the
  shipped algorithm, both defaulting to the champion (`S1_SLIPPAGE_BPS`, `S1_SIGNAL_LAG`), twelve
  full-period LEAN cells (`scripts/_s17_runs.sh`, `scripts/sweep_s17.py`), a new live-fill
  instrument (`scripts/daily_fills.py`), 12 ledger rows, control reproducing `OrderListHash
  5246804e17a67af90028ffceead7d3b3`. Spread ladder **24.404 / 23.699 / 22.926 / 21.129 / 18.216** at
  0 / 1 / 2 / 5 / 10 bp with drawdown **25.1 -> 32.3**, i.e. **0.68 CAR per bp**; measured execution
  cost on the 6 paper fills **+2.9 bps (se 6.8)**; signal lag of one session **-4.75 CAR at t
  -2.65**, proved from `ref_price` in 6 of 6 fills and the runner's own logged `as_of`. **Do not
  re-open as a "what should the constant be" question** - it is a standing measurement now
  (`daily_fills.py` after every paper close, same rule as A-5 part 2: move the default only at two
  standard errors). **Do re-use the knobs**: judge every future daily-sleeve cell at 0 bp *and* at a
  non-zero spread, because the zero-spread comparison is biased toward whichever cell trades most.
- **S-16 DONE 2026-09-11 (see journal): the 3x proxies and the drawdown overlay are worth zero
  return between them; three passing candidates are parked behind the margin-budget question.**
  Nine full-period cells plus two sub-periods (`scripts/_s16_runs.sh`, `scripts/sweep_s16.py`), 11
  ledger rows, control reproducing `OrderListHash 5246804e17a67af90028ffceead7d3b3`. **Both off at
  the unchanged 0.75 budget: 24.403% vs 24.404%, paired -0.00 bps/day (t -0.00, 3,689 days), at std
  0.155 / DD 23.7 / PSR 33.2 / $27.2k fees** against 0.170 / 25.1 / 23.0 / $45.7k. Budget dial with
  proxies off: 0.78 **25.307 / 1.003 / 24.6**, 0.80 **25.903 / 1.008 / 25.1**, 0.82 **26.474 / 1.012
  / 25.7 at std 0.168** (+0.66 bps/day, **t 2.02**; IS +0.07 / 0.24, OOS +1.36 / **2.16**). Overlay
  shelf at 0.80: shipped 24.551 / DD 25.5 -> wide 0.20/0.30 25.333 / **25.0** -> off 25.903 / 25.1.
  Sub-periods of the 0.80 cell: **IS 18.894 / 0.923 / 25.1**, **OOS 34.687 / 1.124 / 23.6**.
  `evaluate.py`: three cells "BEATS champion", the budget-neutral one refused by **0.001 CAR
  points**. **Do not re-open as a proxy-map, breaker-threshold or budget-grid question** - the
  frontier is measured and the remaining decision is the Reg-T buffer, which is the owner's. The
  evidence and a fourth option that dominates O-1b's (b) are appended to `BLOCKERS.md`.
- **S-15 DONE 2026-09-11 (see journal): 71% of the champion's CAR is no skill of any kind, and no
  single switch is distinguishable from zero. Nothing shipped, nothing judged.** Eight full-period
  LEAN cells, each the shipped algorithm with one switch removed through an `S1_*` override
  (`scripts/_s15_runs.sh`, read by `scripts/sweep_s15.py`); two new knobs, `S1_MIN_MOMENTUM` and
  `S1_PROXY`, both defaulting to the champion, with the control reproducing `OrderListHash
  5246804e17a67af90028ffceead7d3b3`. Champion **24.404 / 0.921 / 25.1 / 0.170**; **(f) no skill at
  all 17.282 / 0.711** (whole signal stack = **+7.12 CAR, t 1.37**); (a) no ranking 17.700 at std
  0.137 and **vol-matched 20.745** (**ranking = +3.66 CAR, t 0.92**); (b) regime off 22.383 at
  **DD 31.4** with **zero in-sample contribution** (-0.04 bps/day); (e) **proxies off 23.128 at
  Sharpe 0.950 / DD 23.6 / PSR 27.4 / $25.6k fees** - better risk-adjusted than the champion;
  (g) overlay off **25.998**, so the breaker costs 1.59 CAR (-0.51 bps/day, **t -1.93**, OOS
  **-2.35**) for 2.1 points of drawdown; (d) S-12's tilt +0.80 CAR but **+0.52 bps/day IS,
  -0.06 OOS**. **Do not re-open as a parameter question** - the answer is a table, and it says the
  levers left are risk-posture ones in `BLOCKERS.md`.

**Owner instruction 2026-09-10 (midday) - the list is now exhausted, 2026-09-10 20:4x UTC.**
O-1, O-1b, L-1, X-1 and O-2 have each been measured on the full history and each refused. Nothing
in this repository reaches 3-10%/day: the closest candidate, O-2, needs 3.9x equity at risk per
session against a defined-risk ceiling of 1.0x. What is left is not another lever - it is the three
open owner questions in `BLOCKERS.md`, of which the **drawdown cap** now binds every candidate the
mandate asks for. Original instruction: the strategy set is too weak and too calm. Target is
3-10% portfolio moves per day from fast, high-win-rate strategies. Volatility must come from
EDGE and instruments with intrinsic leverage, not from sizing up unproven signals (A-10 showed
the intraday mix has none yet). Research priority from here, in order: **O-1** (options-implied
regime gate, data ready), **L-1**, **X-1**, **O-2** (needs owner's options permission), then the
A-track refinements. Every candidate is judged on ten years of Alpaca bars with a three-regime
split and real costs; nothing is deployed without being positive in at least two regimes.

- **S-14 DONE 2026-09-11 (see journal): breadth makes the daily champion monotonically worse, and
  its whole cross-sectional edge is +2.02 bps/day at t = 2.07. Refused, nothing shipped.** Three
  nested ranking sleeves - etf9 (shipped), sector (17), broad (22) - after fetching 13 ETFs
  through the D-1 pipeline; presets in `main.py`, decomposition in `scripts/sweep_s14.py`, 7
  ledger rows. LEAN full period: **24.404% / 0.921 / 25.1% -> 17.253% / 0.663 / 30.3% -> 11.622%
  / 0.430 / 29.7%** at unchanged realized vol; `sector` loses both halves (IS 12.626%, OOS
  22.929%); `evaluate.py` refuses all four candidates. Leverage-free decomposition
  (`selected = pool_mean + spread`): **etf9 7.21 = 5.20 + 2.02 (t 2.07)**, sector17 5.73 = 4.90 +
  0.82, broad22 5.27 = 4.32 + 0.94, paired **-1.37 (t -1.95)** and **-1.89 (t -2.23)** bps/day,
  four fifths of it the spread rather than the menu. At `top_n=5` no sleeve's spread is
  significant (etf9 +0.84, t 1.16). Vol-matched steelman (`sector`, top_n 5, budget 0.867, std
  0.168): **22.879% / 0.872** on 8,279 orders. **Do not re-open as a "which names" question** -
  three pools, two holding counts and a vol-matched control agree. What breadth does buy is
  drawdown (unlevered 22.4% -> 14.3%), which is a risk-posture trade, not a return one. Control
  reproduces `OrderListHash 5246804e17a67af90028ffceead7d3b3` and `compare_orders.py` passes
  3,689/3,689, so the daily deploy path is untouched. Also fixed in `fetch_data.py`: the manifest
  is now **merged** rather than rewritten (a 13-symbol fetch had erased the other 69 entries;
  restored from git, merge verified at 1 re-derived / 81 kept) and a one-symbol `--symbols` run no
  longer crashes on yfinance's single-ticker column layout. Successor: **S-15**, above.
- **A-12 DONE 2026-09-11 (see journal): the ORB whipsaw lockout is refused - the reversal re-entry
  is the only profitable trip category in the sleeve, and 98% of the loss is in first entries.
  Nothing shipped.** Motivated by the 2026-09-10 paper session, where one stopped-out-then-flipped
  pattern in semis carried 77% of a -6,779 day; the shipped ORB module permits it because
  `max_entries` is counted per *side*. Built `reentry_block` / `reentry_mode` on the module
  (default **0 = off**, three modes so the mechanism can be separated from the mere loss of
  turnover) and `scripts/sweep_a12.py`; 18 ledger rows under `intraday/active`. **Stage 1 is an
  event study with nothing to fit**: 44,219 round trips over 2,686 sessions, each labelled by what
  preceded it that day - first entry **-$25/trip (t -2.66, -$872,347 total)**, `flip` **+$15
  (+0.65, +$70,708)**, `same` -$20 (-1.03, -$88,087) - and the effect is entirely inside the first
  fifteen minutes, with the sign reversed from the anecdote (**flip +$78/trip at t +1.72, same
  -$81 at t -1.96**, every longer gap flat). **Stage 2, the paired grid**: flip15 **-$31/day
  (t -1.17)**, flip60 -$47 (-0.93), any15 +$3 (+0.08), same15 **+$38 (+1.69)**, same60 +$23
  (+0.68); **0 of 5 cells reach t > 2 in any regime**, and the book stays negative in all of them
  (control **-$331/day, t -1.35**; best variant -$293, -1.19). The one positive cell is the
  falsification control and was chosen after seeing the gap table, so it is in sample by
  construction. **Do not re-open as a block-length, mode or symbol question** - the mechanism was
  measured on 44,219 trips and its sign is the reverse of the premise. Rule (a) replay passed
  (2026-09-08, deployed config: 34 trades, 368 decisions, flat, P&L -2,302, identical to the
  post-fee-fix figure), so the new parameter is inert on the live path. **A free measurement**: the
  control is the first full-sample run under A-5 part 2's corrected commission, with trades/day
  identical to A-10's rows, so **ORB alone is -$331/day, not the -$289 on record**.
- **L-1 DONE 2026-09-10 (see journal): leveraged ETFs do not revert intraday - gross is negative
  before costs, in both directions, on all six names. Refused, nothing shipped.** Two stages, the
  event study first so the mechanism was measured with nothing to fit: over 2016-2026 Alpaca bars
  (TQQQ/SQQQ/UPRO/SPXU fetched here, ~1.03M bars each, joining SOXL/SOXS), fading a VWAP deviation
  of `z` ATRs at the next bar's open and unwinding `h` bars later earns **-0.28 to -3.16 gross bps
  per round trip in all sixteen cells**, against a **6.4-8.2 bps** round-trip cost. Stage 2 through
  the shipped framework on 2,686 sessions: fade on six names **-$902/day at t = -9.45**, on the
  three deployable names -$667/-9.02, and the **continuation control also loses** (-$587/-6.26) -
  0/3 regimes for every variant against the 2/3-at-t>2 rule fixed before the runs. **The durable
  finding is a statistics one**: the same event study *passes* 3/3 regimes at +7.09 bps if sessions
  are equally weighted, because `corr(events per session, session mean gross) = -0.340 at t = -17.5`
  - quiet sessions produce 2.4 stretches that revert (+37.9 bps), violent ones produce 25.5 that do
  not (-10.6). **A per-event average over sessions is not an estimate of what a book earns**;
  `sweep_l1.py` now prints it as a labelled diagnostic and decides on the money-weighted number.
  The harness was audited before it was believed: `scripts/_l1_reconcile.py` matches 235 harness
  round trips to event-study entries at **corr 1.000** (+1.12 vs +1.12 bps). Cost is structural
  here - the inverse ETFs trade at $20-26 and IBKR charges per share, so SOXS pays 13.58 bps a
  round trip against TQQQ's 4.85. **Do not re-open as a threshold, horizon or name-selection
  question** - the negative is on gross, in both signs. Only `scripts/intraday_common.py` changed
  (two constants, no behaviour); the 2026-09-08 replay reproduces the deployed sleeve exactly.
  **On the mandate**: at 0.9 gross on 3x ETFs the book's daily P&L sd is 0.49% of equity - the
  leveraged instruments supply volatility, not edge.
- **X-1 DONE 2026-09-10 (see journal): the cross-sectional intraday spread on the megacaps is
  +0.36 bps against a 4.70 bps round trip - real, tiny, and 13x too small. Refused, nothing
  shipped.** Fetched the 40 missing megacaps (2016-2026, ~1.04M bars each; the Alpaca store is now
  60 symbols) and re-derived `_splits.json` for the union, every pre-existing factor identical.
  Stage 1, sixteen parameter cells over **2,684 sessions and 267k-587k legs each**: gross is
  **positive (momentum, not reversal) and never above +0.36 bps per leg**, best cell "since the
  open, hold 60, k=5" at t = +2.00 pooled and +1.44 / +0.83 / +1.34 by regime - **no cell reaches
  t > 2 in two of three regimes even before costs**, and net of costs the verdict is 0 of 32.
  Stage 2, the module through the shipped framework on one year per regime: momentum
  **-$1,681/day (t = -16.9)** and the reversal control **-$1,786/day (t = -18.8)**, 0/3 regimes
  both. **The symmetry is the finding**: backing out costs leaves +$79/day and -$97/day of gross
  on a $1M book - zero in both directions - while turnover of 8.07x equity/day pays $1,760/day.
  Stage 1 predicted +$20/day of gross at the module's defaults, so the two instruments agree and
  no harness audit was owed. **Do not re-open as a lookback, horizon, decile or rebalance-frequency
  question** - the grid spans all four and the mechanism is an order of magnitude under the cost
  floor everywhere. Worth keeping for a later idea: the gross effect is **+0.63 bps at 10:30 and
  -0.69 bps (t = -2.80) at 14:30** - continuation in the morning, reversion in the afternoon - and
  the per-share commission means the same strategy costs 5.45 bps in 2016-2019 and 4.00 in
  2024-2026. **On the mandate**: this book's daily P&L sd is 0.27% of equity, the least volatile
  thing on the owner's list.

Owner decisions of 2026-09-09 (see `BLOCKERS.md`): paper trading is approved and running,
the 35% drawdown cap stays, promotion is now return-first with a 0.03 Sharpe tolerance and a
1-point drawdown tolerance, delisted-inclusive data is deferred, the no-trade band stays 0.01.
Priority is therefore the **intraday active sleeve (A-track)**: volatility is to be earned with
a second, uncorrelated intraday sleeve, not by leverage on the ETF sleeve. IB Gateway is up.

Owner instruction 2026-09-09 (afternoon): by the 2026-09-10 open the paper account must run a
volatile, active, high-turnover book on most of the capital. The infrastructure for that now
exists (see AGENTS.md "The intraday active sleeve"): 16-name disjoint universe, IBKR minute
store, causal features, three strategies, a minute backtester, and a live trader with replay,
scheduled 09:25 ET. **The loop's job from here is signal quality**: the first honest numbers
(2 names, 62 sessions) were ORB +10% annualized / Sharpe 2.5, VWAP-trend -12% after costs,
late-day momentum flat. Every A-track iteration: pick one strategy, change one thing, run
`scripts/intraday_backtest.py --split <date>` on the full universe, keep it only if OOS
improves after costs, journal it, and update `live/intraday_config.json` only per AGENTS.md rule (c).

- **S-17 part 2 Measured fill slippage on the *daily* sleeve. Standing per-session job, opened
  2026-09-11.** Run `python scripts/daily_fills.py` after every paper close. It reports two numbers
  and they must not be pooled: **execution cost** against the 15:45 close the runner aims at
  (currently **+2.9 bps notional-weighted on 6 fills / $1.42M, per-fill sd 16.7, se 6.8**), and the
  **convention difference** against the D+1 open the backtest fills at (-16.9 bps, se 25.8, which is
  a whole session of price movement and is uninformative at this sample size - it is priced by
  `S1_SIGNAL_LAG` over fourteen years, not here). LEAN charges **0 bps** of spread by default, and
  each bp is worth **0.68 CAR points** on the champion, so this constant owns roughly 2 points of the
  reported return. Same decision rule as A-5 part 2: move `S1_SLIPPAGE_BPS`'s default only when the
  gap to the current value exceeds two standard errors, with a journal entry. At the observed sd of
  16.7 bps, ~130 fills are needed to place the constant within 1.5 bps, which at 3 fills a session is
  a long standing job - so judge candidates at a *bracket* (0 bp and 2 bp) rather than waiting for it.
- **A-5 part 2 Measured fill slippage. First fills measured 2026-09-10 (see journal); slippage is
  still open, the commission half is CLOSED and shipped. Standing per-session job.**
  **Slippage, still open**: 19 fills / $1.1M on the partial first session give **+1.30 bps
  notional-weighted (se 1.65) against the shipped 1.50, z = 0.12** - not distinguishable, so
  `SLIPPAGE_BPS` was not touched. **The reference question is settled and it was a red herring**:
  the same 17 fills priced against the next-bar open score +1.10 bps / sd **7.55** and against the
  decision-close fallback +1.55 / sd **7.13**, with the realized close-to-open gap at sd 2.16 and
  correlation -0.33 to the fill error, so the fallback is if anything *quieter*. The whole-store
  gap sd of 6.20 bps predicted the opposite; a population noise estimate does not transfer to the
  minutes a strategy selects. The cost is the **~10 s detection latency** (median 10 s, worst 13),
  which is mean-zero drift, so only fills buy precision: **166 fills, ~3-4 full sessions at 49
  trades/day**, to resolve the constant against breakeven at 2 se. Run
  `python scripts/slippage_report.py --refresh` after **every** paper close (`--refresh` pulls the
  closed sessions into `data/minute` and refuses a session still trading), report the running
  notional-weighted mean and its standard error, and move `SLIPPAGE_BPS` only when the gap exceeds
  two standard errors, with a replay and a journal entry (rule a). **Do not re-open the reference
  as a question.** **Commission, closed**: IBKR's own `commissionReport` matched the harness on all
  twelve buys to $0.004 and undercharged all five sells; fitting the excess reproduces every sell
  **to the cent**, so the harness was omitting the US sell-side regulatory pass-throughs - **SEC
  Section 31 $20.60 per $1M of proceeds (0.206 bps) and FINRA TAF $0.000198/share**, now charged in
  `intraday_common.commission()` when `shares < 0`. Paired 260-session control: costs/day
  $1,025 -> **$1,078**, $/day $610 -> **$557**, CAR 15.3% -> **14.0%**, Sharpe 0.689 -> **0.640**,
  trades 12,743 -> 12,742. **The breakeven is therefore 2.52 bps, not 2.62**, and every intraday
  number quoted before 2026-09-10 12:00 ET is 5.2% light on cost. Rule (a) replay passed twice
  (2026-09-08, deployed config, current trader): identical 34 trades / 368 decisions / flat at
  close, P&L -2,280 -> -2,302, the whole difference being the measured fees.
- **O-1b DONE 2026-09-10 (see journal): the implied-vol size dial is a leverage dial and costs 50%
  more turnover than the constant that replaces it. Refused, nothing shipped.** Built the dial on
  the champion (`iv_scale_power` etc. in `signals.py`, `S1_IV_SCALE_*` in `main.py`,
  `iv_regime.py --export-csv` for the pyarrow-free LEAN Python), causal by strict prior-day
  lookup, applied after the margin-budget shrink, uncovered pre-2017 days at factor 1.0 and the
  study judged on 2017-04-03..2026-09-04. **The inverse reading that the O-1 residual motivates
  loses on both axes** (CAR 27.69 vs 29.46 control, and std 0.182 vs 0.179). The direct reading is
  a pure vol dial - std monotone 0.179/0.189/0.198/0.204 in the tilt, Sharpe peaking at power -0.5
  and decaying - and **at matched realized vol a constant gross-up with no IV in it scores 31.107%
  / 1.040 / 0.189 against the dial's 31.376% / 1.050 / 0.189, on 3,027 orders against 4,550**. The
  shipped-defaults regression reproduces `OrderListHash 5246804e17a67af90028ffceead7d3b3` exactly.
  **Do not re-open as a field, window or threshold question** - the negative is that the only
  contribution available is the *level* of gross, which `margin_budget` already provides free.
  Kept for the record, the original item: O-1 refused the
  *gate* but measured a real residual: corr(SPY implied vol, |intraday daily P&L|) = **+0.252 at
  t = +12.67**, positive in all three regimes for all three features. Implied vol forecasts how
  big a day will be and not which way, which is worthless on a book whose level is negative - and
  potentially worth something on **S-12, where the level is positive**. Test it as a size scaler
  on the daily champion: scale gross by the inverse of prior-day SPY ATM IV against its trailing
  median (and test the direct sign too), judged through `scripts/backtest.py` + `scripts/evaluate.py`
  on both sub-periods with the shelf-not-spike rule, not as a new signal. `data/options/iv_regime.parquet`
  already covers 2017-2026; the daily champion's sample starts 2012, so the pre-2017 years are
  ungated and the study must say what it does with them rather than silently dropping them
  (Theta answers 403 before 2016 and 472 for 2016 greeks on this account's plan).
- **O-1 DONE 2026-09-10 (see journal): implied vol forecasts the day this sleeve is paid for and
  the forecast is worth nothing; the payoff is in the volatility *surprise*. Refused, nothing
  shipped.** Built `scripts/iv_regime.py` (Theta EOD greeks -> `data/options/iv_regime.parquet`,
  2,383 days 2017-01-03..2026-09-09: front-weekly ATM IV, 25-delta skew, 1w/1m term ratio; 491
  expirations cached under `data/options/raw/`, resumable, `--rebuild` free), `scripts/sweep_o1.py`
  (partitions A-10's cached 2,686-session series by a strictly prior-day gate, so every cell is a
  partition of one fixed sample rather than a new fit) and `iv_gate` on the ORB module, default
  off, failing closed on days the store does not cover. **corr(prior-day ATM IV, today's universe
  range) = +0.598 at t = +36.4** and **corr(realized range, ORB P&L) = +0.260 at t = +13.95**, but
  **corr(IV, P&L) = -0.030 at t = -1.46**; `term_ratio` +20.9 / -0.77 and `skew25_1w` +17.0 /
  **-2.81** (the only |t| > 2 against P&L, wrong sign). Range split into forecast and surprise:
  forecast -0.030 / -0.016 / -0.058, **surprise +0.351 / +0.292 / +0.299 at t = +18.3 / +14.3 /
  +15.3**, positive at t > 7 in nine of nine feature-regime cells. **All six gate cells fail 0/3
  regimes**; best ON side `term_ratio low` **+$43/day at t = +0.13**; the largest separation
  (Welch 2.26 in 2016-2019) inverts in 2024-2026. Replay of 2026-09-08 with the deployed config
  reproduced A-10 exactly. **Do not re-open this as a threshold, feature or horizon question** -
  the negative is that the payoff regressor is a surprise, so no forecast of any quality can reach
  it; the surviving residual is the size scaler now carried as O-1b. Kept for the record, the
  original item: A-10 measured the
  only mechanism this sleeve has that survives a 2,686-session sample: daily P&L correlates
  **+0.202 with the universe's mean daily range at t = +10.70**, positive in all three regimes
  separately. The level is negative everywhere, so the question is no longer "how big" but
  "when": is there a causal, known-at-entry regime signal that separates the range days the book
  earns on from the ones it pays on? A-9 proved the *opening range* is not it (the stop is the
  range midpoint, so width scales win and loss together). Options-implied volatility is the
  untried candidate and it is knowable before the open. Build `data/options/iv_regime.parquet`
  from `scripts/theta_data.py`: SPY ATM IV (nearest weekly), 25-delta put/call skew and the IV
  term ratio (1w/1m) per day and per 30-minute bucket, back to 2012. Gate ORB on it (trade only
  when IV is above/below its 60-day median, and test both signs) and judge it on the **Alpaca
  store with `scripts/sweep_a10.py`'s three regimes**, not on the 260-session IBKR window - that
  window is what produced every A-track false positive. Causal only: the bucket before the
  decision bar. A gate that does not reach t > 2 in at least two regimes is refused. Secondary
  use, carried over from the original O-1 statement and not to be done before the gate: the same
  features as a **size scaler for the daily champion**. Live note: the IV store is EOD, so a
  deployed gate needs the launcher to refresh it before the open - keep `iv_gate` defaulted off
  until a study justifies it. **Ordering (daily review 2026-09-10): A-5 part 2 runs first each
  day** - it is a ~1 minute job after the close and it is the only measurement that can move the
  cost constant every other A-track number depends on - **then O-1 takes the rest of the
  iteration.**
- **A-10 DONE 2026-09-10 (see journal): the sleeve is significantly negative on 2,686 sessions;
  the late-day fade is dropped.** Mix -$697/day at t = -3.01; regimes -$579/-2.42, -$1,127/-2.92,
  -$231/-0.37; ORB alone -$289/-1.17; late fade alone **-$468/-7.38**, negative in every regime
  and on the fitted window. The only profitable window in eleven years is the 261 sessions the
  parameters were chosen on (+$302/day, t = +0.32). Shipped `alloc.late_momo` 1.0 -> 0.0 after a
  passed replay; `equity_frac` held at 0.5. Also shipped the prerequisite cost fix (`--splits`,
  `share_scale()`, scaled `commission()`, whole-share floor at the real price) with an
  IBKR-store regression that reproduces A-5's control to the digit. **Do not re-open this as a
  parameter question** - the negative is about the level of the whole sleeve on unseen data.
  Kept for the record, the original item: A-4 proved the IBKR store
  (260 sessions) cannot resolve the deployed mix's edge (t = +0.61, ~2,000 sessions needed).
  `scripts/alpaca_data.py` now pulls consolidated 1-minute bars for any US symbol back to
  2016, free. Fetch the 16-name universe from 2016 (`--start 2016-01-01`, ~10 minutes), then
  re-run the deployed mix and each sub-strategy with `INTRADAY_DATA_DIR=data/minute_alpaca`
  and a 3-way split (2016-2019 / 2020-2023 / 2024-2026). Report t-stats per regime and the
  range-correlation from A-4. If the mix is not positive in at least two of three regimes at
  t > 2, cut its `gross` in `live/intraday_config.json` to 0.75 and say so in the journal:
  the owner asked for volatility, but not for noise dressed as edge. Also widen the universe
  test: the 50 megacaps from D-1 are now fetchable at minute resolution.
- **O-8 DONE 2026-09-13 (see `research/journal_options.md`): the 0DTE put wing does NOT forecast
  the day's DOWNSIDE TAIL. REFUSED on both pre-registered legs, and the declared sign is wrong.**
  `scripts/sweep_o8.py`, 21 DIAGNOSTIC rows under `options/odte_o8_tail`. There was no open
  O-item; this one exists because O-5 tested the chain's asymmetry (`rn_skew` at 0.5% of spot,
  `rn_tail` at 2.0%) for **direction** only, and a conditional mean and a conditional **quantile**
  are different objects - the first is a tradeable expectation the chain would price away, the
  second is a physical tail times a pricing kernel, and it has a consumer (a de-risk switch) that
  A-15's refusal of `rn_half`-as-size does not reach. Target = signed `fwd`, estimator = linear
  **quantile regression at tau = 0.05**, so the statistical loss and the economic object (a 5%
  VaR) are the same quantity. The decisive comparison is **M2 (tape + `rn_half` + asymmetry)
  against M1 (tape + `rn_half`)**, never against the tape - beating only the tape would be O-6
  found again through a wider door. Measurement side imported unmodified from `sweep_o6`; new
  solver (no `statsmodels` on this machine) gated against an exact `scipy.optimize.linprog`
  solution at excess pinball loss **0.0000**, and in-sample calibration 5.20-5.30% at tau=0.05.
  **Result**: M2 wins **2 of 5** clocks, pooled DM t **-0.401** (wrong side of zero, not merely
  insignificant), regimes leg 1 of 5. `rn_skew`'s fitted coefficient is **positive at 4 of 5
  clocks** where the declaration said negative, while `rn_half` is -21.9..-37.1 bps per sd at 5 of
  5 - a block short of power would still load in the declared direction, so this is a mechanism
  refusal. Stage A shows why: both asymmetry reads correlate with **|fwd|** (-0.31..-0.34, +0.15
  ..+0.22 Spearman) and not with signed `fwd` (-0.08..+0.08) - they restate the chain's own width,
  which M1 already carries. Economic leg null (book 5th-percentile moves -4.1%..+4.1%, no sign, no
  material cell). Placebo at tau=0.95 does not bite: the block is *worse* there too (pooled t
  -2.674), upper-tail improvement at 0 of 5 clocks. **The pre-registered secondary read is the
  only positive and cannot change the verdict**: `rn_half` over the tape alone cuts OOS 5%-VaR
  pinball loss **-2.96 / -3.43 / -5.79 / -7.21 / -8.03 %** at 10:00..14:00, DM t +2.66 / +2.24 /
  +2.90 / +2.78 / +3.16 (4 of 5 clear the 2.576 bar; 11:00 does not), with realised breach rate
  4.39-5.25% against a nominal 5% - so O-6's skill survives a change of target *and* loss
  function, and grows through the session. Limits stated rather than leaned on: `rn_tail` is
  exactly 0 on 23.8% of rows (but `rn_skew` is non-zero on 99.8% and fails too), the estimator is
  linear in levels, and the 2016-2019 regime is under the 100-row floor at the last two clocks -
  which made leg (ii) easier, and it still failed. **Consequence, pre-registered before the run:
  the chain's entire content is the one symmetric number O-6 found, and O-4's advice to stop
  scheduling this scope until Theta VALUE is restored is now UNCONDITIONAL rather than a
  judgement call.** Nothing shipped, no handoff opened (opening one off a REFUSED result would
  spend another track's slot on nothing), `sweep_o6.py`/`sweep_o7.py` unmodified.
- **O-7 DONE 2026-09-13 (see `research/journal_options.md`): O-6's magnitude skill is NOT a
  volatility-regime detector - it is present in **15 of 15** (clock x vol-state) cells and the
  sized-book benefit is **largest in the CALM state**, where a realized-vol sizer is blind. PASS on
  the pre-registered rule; nothing shipped.** `scripts/sweep_o7.py` (the only new file; it
  *imports* the panel, cache, baseline, target, clocks, burn-in and OOS protocol from `sweep_o6`
  rather than re-implementing them - the sole new object is the state variable), **46 DIAGNOSTIC
  rows** under `options/odte_o7_volstate`. There was no open O-item; this closes the one caveat
  O-6 named that is testable from disk (the SPY-only half cannot be, the store has one underlying
  and Theta was re-confirmed **HTTP 403** live). State = `rv20`, known *before* the forecast
  session opens; terciles assigned **causally** against strictly prior rows; splitting on
  `rv_sofar` was **rejected in advance in writing** (it is a fitted input of the baseline) and
  carried only as a secondary read. Gates: O-6's Gate 0 passes and its Stage C reproduces 5 of 5.
  **Stage 1**: dRMSE negative in all 15 cells (calm -0.85..-2.07%, mid -2.10..-4.14%, volatile
  -0.65..-3.12%), 3 of 3 states won at every clock; calm wins 5 of 5 clocks, pooled calm DM t
  **+2.613** on 632 sessions against a bar of +2.576. **Reported as the marginal thing it is**: no
  single clock's calm t reaches the bar, a post-hoc NW-lag sweep gives 2.487 / 2.532 / **2.613** /
  2.659 / 2.790 at lags 0/2/5/10/20 so leg (i) **fails at the two shortest lags**, and the
  secondary `rv_sofar` split gives PARTIAL at t +2.033. What is *not* marginal is leg (ii).
  **Stage 2** (the question actually asked): dOOSR2 calm 0.016-0.041, mid 0.037-0.071, volatile
  0.012-0.054 - **not vol-concentrated, so the regime-detector reading is refuted**. **Stage 3**:
  sd of the normalized move falls **-11.7% mean in calm** (MATERIAL 5 of 5 clocks), -2.9% mid,
  -13.7% volatile - **U-shaped with the trough in the middle state**, i.e. the chain adds most
  exactly where realized-vol sizing is most wrong. **Reported against itself**: the RAW 3-sigma
  breach count in calm moves the wrong way at 4 of 5 clocks (worse there than anywhere), the same
  level artifact O-6 hit. **Mask attack lands**: calm-state survival 93.9/88.4/83.8/81.3/**77.3**%
  and dropped cells are 2-3x quieter than kept (e.g. 19.6 vs 10.1 bps at 14:00), so **"calm" here
  means the busier end of calm** and no disk-only test extends it. **Why this closes the track
  rather than advancing it**: O-6's handoff A-15 has since been REFUSED by `iterate` on the
  mechanism (the sleeve is paid +$2,651/day per sd of volatility *surprise* and -$230/day per sd of
  the *predictable* part). O-7 does not contradict it - A-15 is about a book's P&L, O-6/O-7 about
  forecast accuracy on SPY. Together: **the chain's magnitude skill is real and general, and this
  repository contains no book paid for the predictable part of magnitude.** A retraction of the
  second VALUE justification O-6 wrote into `BLOCKERS.md` is appended there (SPXW untouched).
  **Next step: none on this track** - every disk-answerable question is answered; a second
  underlying and any session after 2026-09-10 both need VALUE restored, so O-4's advice not to
  schedule this scope is now unconditional.
- **O-6 DONE 2026-09-13 (see `research/journal_options.md`): the FIRST PASS on this track. The
  chain's magnitude skill is NOT a restatement of the tape - incremental out of sample at 5 of 5
  clocks, and it cuts the dispersion of a sized book 4-14%. Nothing shipped: it is a RISK input
  and sizing is not this track's scope.** `scripts/sweep_o6.py`, 40 DIAGNOSTIC rows under
  `options/odte_o6_magnitude`. O-5 printed `corr(rn_half, |fwd|) = +0.540 at t +60` as a Gate-0
  **control** and never asked whether that skill was incremental; a magnitude forecast changes
  **position size**, not entry, so the cost wall that killed O-2/O-3/O-5 cannot reach it. Built no
  new chain feature and used no new clock - the chain side is O-5's frozen cache. Pre-registered:
  target `log|fwd|`, tape baseline `rv_sofar`/`rng_sofar`/`rv20`/`absret_1` all causal at the
  clock, declared-positive `log(rn_half)`, Newey-West, Bonferroni |t| > 2.576, Stage C needs a
  lower OOS RMSE **and** two-of-three, Stage D MATERIAL declared in advance at sd -5% or breaches
  -10%. **Gate 0 reproduces O-5's control to +0.5396.** Stage A: `rn_half` is the best single
  predictor at **every** clock (0.40-0.44) ahead of `rv_sofar` (0.34-0.40). Stage B: t **+8.09 to
  +9.55**, sign as declared 5 of 5, mean dR2 +0.036. **Stage C: 5 of 5 pass, OOS R2 0.101-0.157 ->
  0.135-0.198, DM t +3.5 to +4.2** - though at 13:00/14:00 the burn-in leaves 2016-2019 under the
  100-row floor, so "2 of 3" there is **2 of 2 available**. Stage D: sd of the normalized move
  **-4.3/-8.5/-10.9/-14.3/-12.0%**, 4 of 5 clear the bar (10:00 misses). **Reported against
  itself**: the RAW 3-sigma breach count moves the wrong way at 13:00/14:00 (+10.4%/+14.5%);
  post-hoc, `exp(y_hat)` is a geometric mean not a sigma and the models sit at different levels,
  and rescaling to `mean(z)=1` gives -9% to -32% the right way - the verdict rests on the clean sd
  leg, not the post-hoc one. **Three attacks, none fatal**: a full-hour stale-chain buffer
  survives 4 of 4 at t +7.6..+10.8 (no sub-hour timing artifact available); a harder tape adding
  `rv_30m` and `rv5` survives 5 of 5 in and out of sample - **but absorbs ~56% of the 14:00
  increment** (t 9.31 -> 6.11) against 6-13% elsewhere, so the finding survives and its size at
  the last clock does not. Durable shape: **this chain is priced efficiently in DIRECTION (O-2,
  O-3, O-5 all land at cover ~= 1) and informative in MAGNITUDE, where there is nothing to
  charge.** No shipped or runner-loaded file touched, no deploy gate owed. Handoff is **A-15**
  below, not a continuation here.
- **A-15 DONE 2026-09-13 (`iterate` track; see `research/journal.md`): REFUSED on the MECHANISM,
  which closes the whole class rather than this one scaler.** `scripts/sweep_a15.py`, eleven
  clauses pre-registered, no backtest, **4 DIAGNOSTIC rows** under `intraday/active`; nothing
  shipped, `live/*` untouched, no replay owed. Clause 0 found the item's premise wrong - the
  sleeve has **no** realized-vol sizing to beat (`orb` 0.12 of equity per position, `vwap_trend`
  0.10, flat notional), so the tape control was built here and the item split into "does any
  causal magnitude forecast beat flat sizing" (free) and "does the chain beat it" (paid).
  Because the control book loses -$324/day, every statistic is gross-matched by an expanding
  causal prior-mean and reported as `cov(k,pnl) + (mean k - 1)·mean(pnl)`, with PASS on the
  covariance alone - otherwise "size a losing book down" scores as skill. **Clause 2 holds
  hugely**: sleeve P&L on realized |SPY move| is **+$2,789/day per 1 sd at t +11.67**, terciles
  -2,819 / -1,732 / +3,583. **Every causal scaler fails**: tape `rv20` cov -62.5 at t -1.05,
  `vix_lag` -70.0, chain `rn_half`@10:00 residual over tape **-157.6 at t -1.94, 0 of 2 available
  regimes**; the only positive variant (strictly pre-open lagged chain residual, +105.9, 3 of 3)
  is t +1.28 and is not claimed. **The ORACLE says what is being left**: perfect hindsight on
  magnitude pays **+$550/day** and turns the book -$324/day / Sharpe -0.36 / DD 69.6% into
  **+$222/day / +0.28 / 40.8%** - the largest improvement anything has produced on this sleeve.
  **Two pre-registered defences fired and were honoured**: clause 8's linearity bound FAILED (64
  and 55 NEW 2.5% loss-limit breaches, 2.38%/2.05% against a 2% bound), so the headline moved to
  a loss-limit-aware book calibrated on the control's own 93 stopped sessions (exactly the 93
  with `low_ret <= -2.5%`, realizing -2.598%), under which the tape scalers are **free rather
  than harmful** (+23.5 / +36.7 at t +0.34 / +0.50) and the chain is still -135.9 at t -1.51; and
  the single scramble landed at -139.5 rather than zero, so a **300-permutation null** was built
  (mean -11.9, sd 68.8, band [-121.4, +93.1]) - the tape scaler is inside it at z -0.42 and the
  chain at z -2.12, one of four comparisons, so the chain may not be called helpful and should
  not be called harmful. **Clause 10 is the finding**: splitting log|move| causally into
  forecastable and surprise, the sleeve is paid **+$2,651/day per 1 sd of SURPRISE at t +8.41**
  and **-$230/day per 1 sd of the PREDICTABLE part at t -0.73**; adding the chain moves the
  explained variance 0.090 -> **0.100** (O-6 reproduces, one point of R²) and the predictable
  part to -$662 at t -1.93. **90% of the magnitude this sleeve lives on is unforecastable and the
  10% that is not pays the wrong sign**, which is why all nine beta x band cells are a shelf of
  negatives. **DO NOT RE-OPEN as a better-magnitude-model question** - a longer chain, a second
  underlying or an ML nowcast cannot change a verdict that is about which component of volatility
  pays. Does not touch O-6's own claim, which is about SPY forecast accuracy and reproduces here.
  Volatility sizing survives only as a RISK dial (free under the correct book), never quoted as a
  P&L improvement.
  <!-- closed by A-15, 2026-09-13 (iterate). -->

- **A-15 (original text, kept for the pre-registration) (opened by O-6 2026-09-13, for whoever owns sizing - `iterate`/`ml`, NOT `options`):
  does an `rn_half`-based size scaler beat the intraday sleeve's realized-vol sizing on the
  sleeve's own P&L?** O-6 proved the chain's magnitude nowcast is incremental over the tape for
  SPY out of sample (above). The O-track cannot test the next step: sizing lives in the sleeve's
  files and the sleeve's universe is **disjoint from SPY by design**. Judge it on the sleeve's
  P&L after costs under the standing two-of-three rule, not on forecast RMSE. Caveats that travel
  with the finding: measured on SPY only, on a sample tilted volatile by O-3's mask (it drops calm
  sessions preferentially - mean |move| 13.3 bps where it drops out vs 38.7 bps where it survives),
  and never tested on a second underlying because the store has exactly one. Note the dependency:
  the input needs a live 0DTE chain, so it is only as deployable as the Theta VALUE ask.
  <!-- added by O-6, 2026-09-13 (options). Handoff item: the options track ships nothing. -->
- **O-5 DONE 2026-09-12 (see `research/journal_options.md`): the cost wall is NOT an options-market
  phenomenon. The same chain signal traded in the UNDERLYING is 68x cheaper and the edge shrank to
  match. Refused; nothing shipped.** `scripts/sweep_o5.py`, 40 DIAGNOSTIC rows under
  `options/odte_o5_direction`. Every prior refusal on this track (O-2 cost, O-3 selection ceiling,
  O-4 blind estimator) is about the cost of **transacting in options**, none about the chain's
  **information content** - so trade the chain's forecast in SPY itself, where the round trip is
  **3.41 bps of notional** (repository cost model) against O-2's ~230 bps of risked capital.
  Four causal chain features (`rn_skew`, `rn_tail` at 2%, `rn_drift` = the risk-neutral median vs
  spot, `d_rn_skew` = the intraday repricing) x five clocks, exit 15:50, **1,890 sessions / 9,445
  cells**, entered one full minute after the chain bar on **real consolidated SPY minute bars**.
  **Gate 0 passed and makes the null readable**: parity spot vs the tape median **0.23 bps**, and
  the control **corr(rn_half, |move|) = +0.540 at t = +60.0** - the chain forecasts MAGNITUDE
  superbly on this very sample, so a null on direction is about direction. **Stage A: 3 of 20 cells
  at nominal |t| > 2, 0 of 20 at Bonferroni |t| > 3.02**; all three carry the declared sign, and
  `rn_drift` is monotone at 10:00 (t +2.375) and 13:00 (t +2.187) and is **not** a stale chain
  (corr with the move already made +0.02..-0.05). **Stage B: 0 of 20 clear two-of-three**; best is
  `rn_drift` @ 10:00, gross **+3.28 bps** against the **3.41 bps** round trip = net **-0.13 bps at
  t -0.07**, long fraction 0.488, and **2016-2019 is negative in nearly every cell** (t -2.4..-2.9).
  **The bound that closes it: best `cover` = gross/round-trip over 20 cells with full hindsight is
  0.963, and ZERO cells exceed 1.** O-3's cover on the options version was 0.319/0.765; cutting the
  cost 68x moved it to 0.963 - still under one. **Three independent constructions on this chain all
  land at cover ~= 1**, so the wall is not the options spread, it is how much the chain knows: it
  prices magnitude superbly and direction at roughly the transaction cost of whatever instrument
  collects it. **Do not re-open as a feature, clock, horizon or instrument question.** Two
  pre-registration errors are recorded in the journal rather than patched away (a declared identity
  vs `sweep_o3.features` that failed on 3 of 8,777 cells, and `rn_tail` being 28-42% exact zeros);
  Stage A is reported on both masks and the answer does not move. `sweep_o2/o3.py` imported, **not
  modified**; no shipped file touched, no deploy gate owed. **Does not change O-4's advice**: the
  Theta 403 was re-confirmed live this run, SPXW is still the only live question, and with O-5 shut
  this track now has **no open item at all** until VALUE is restored.
- **O-4 DONE 2026-09-12 (see `research/journal_options.md`): trade-print options data cannot
  refuse a bad trade. The free fallback is disqualified and the O-track is BLOCKED on the human.**
  `scripts/sweep_o4.py`, 60 DIAGNOSTIC rows under `options/odte_o4_feed`. The Theta plan lapsed
  STANDARD -> FREE on 2026-09-12, so before porting this track to the only reachable free options
  source, measure what porting would do to its verdicts. O-2's own 60-cell grid, all 1,891 stored
  sessions, priced two ways from the same `run_session` columns (`sweep_o2.py` imported, **not
  modified**; no shipped file touched, no deploy gate owed): `NET_QUOTE = pnl/risk` (bid/ask, the
  truth) against `NET_PRINT = (pnl_gross - fees)/risk` (every fill at the mid, which is *generous*
  to the fallback). **The pre-registered headline came back 0 and had no power** - no cell reaches
  t > +2 under either estimator, so a statistic that only catches an invented *pass* is zero by
  degeneracy; this is stated in the output rather than reported as "usable". **The direction with
  power, declared post-hoc: 56 of 60 cells are decisively refused on quotes (t < -2); on prints 33
  of those 56 stop being decisive (59%) and 6 turn positive.** Best print cell put 0.35/1.50%/14:00
  reads +0.356% (t +1.28) and is really **-0.477% (t -1.54)**. Spread cost is non-negative by
  construction, so the error is a **one-directional bias averaging 2.72x the effect being
  measured** - Spearman(quote, print) = 0.776 is the trap: the ordering survives, the level does
  not. Identity exact: `quote% - print%` = the blind term at max |difference| 1.78e-15.
  **Also fixed here**: O-3's "every endpoint returns 478" diagnosis was half wrong and self-
  inflicted - `alive()` read any HTTP error as "terminal dead" and started a duplicate terminal
  whose login invalidated the live session. `theta_data.py` now separates `listening()` from
  `alive()`, refuses duplicate starts, and reports entitlement via `--check`. **The remaining ask
  is VALUE tier, not STANDARD** (`odte_data` calls only `/v3/option/history/quote`); STANDARD only
  rebuilds an `iv_regime.parquet` already on disk. **Do not schedule this track until VALUE is
  restored** - O-2 closed delta/width/entry/structure/stop, O-3 closed selection at net zero, O-4
  closed the free-substitute escape hatch, and the one live question (cash-settled **SPXW**, where
  O-2's fatal exit assumption becomes a fact and commission per unit of risk falls ~10x) is one
  `fetch_day` away behind the 403. Operational: `py -3.11` has no pyarrow; run `sweep_o*` on the
  default `python`.
- **O-3 DONE 2026-09-12 (see `research/journal_options.md`): the 0DTE variance risk premium is
  NOT conditional, and the ceiling on session selection is net zero. Refused; nothing shipped.**
  `scripts/sweep_o3.py`, 14 DIAGNOSTIC ledger rows under `options/odte_o3_select`, two features
  and two directions pre-registered in the file's docstring before any run. O-2 refused the SPY
  0DTE credit spread on COST and closed the delta, width, entry-time, structure and stop axes;
  **selection was the one lever that is none of those five**, and O-2's own conditioning test used
  only the *external* `iv_regime.parquet`. O-3 conditions on the traded chain's own state:
  `rn_skew` (the risk-neutral asymmetry from the chain's `dP/dK` at +/-0.5% of spot) and `vrp`
  (half the risk-neutral interquartile span minus the trailing-20-session realized half-span,
  strictly prior, therefore causal). **Both identities exact**: `sweep_o2.run_study` over the whole
  store reproduces the O-2 ledger row `20260910T203647Z` to every digit (1,889 sessions, -1.5301%,
  t -3.20) and matches O-3's control on the 1,848 feature-complete sessions at **max |difference|
  0.000e+00**; `sweep_o2.py` is imported, not modified, and **no shipped or runner-loaded file was
  touched, so no deploy gate is owed**. **0 of 4 feature/cell pairs clear Stage A**, so Stage B
  never ran: `rn_skew` t(T3-T1) = -1.61 / -0.76 and `vrp` +0.15 / **-0.52 monotone in the WRONG
  direction** - richer premium, lower gross, which is implied vol being high because realized is
  about to be high, measured here rather than assumed. **The result that closes the axis is one
  level up**: `cover` = gross/(spread+fee), and **cover = 1.000 IS net zero by construction**, so a
  filter must find cover > 1 out of sample. Unconditional cover is 0.319 on B1 (needs 3.14x) and
  0.765 on B2 (needs only 1.31x), per-session **corr(gross, cost) = -0.598 / -0.482** because the
  expensive sessions are the losing ones (a breached position is bought back through a wide
  quote), and **the best of twelve terciles chosen with full hindsight - B2 `rn_skew` T1, n 550 -
  reaches cover 1.043, net +0.052% at t +0.09.** That is the ceiling on selection and it is zero.
  **Do not re-open as a feature, threshold, quantile or conditioner question** - the bound is not a
  property of these two features, it is the -0.5 to -0.6 coupling between gross and cost, and no
  filter built from the same chain escapes it. Durable piece: **when a construction is refused on
  cost, measure `cover` per candidate subset before building a filter** - if cover is capped at 1
  with hindsight, no causal selection exists and the search is over in one pass.
  **Found in passing and filed in `BLOCKERS.md`: the Theta options subscription dropped from
  STANDARD to FREE between 2026-09-10 02:24 and 2026-09-12 10:32** (both lines in the terminal's
  log); every options endpoint returns HTTP 478 and the 2026-09-11 chain cannot be fetched. The
  store is frozen at 1,891 sessions ending 2026-09-10; O-3 ran entirely from disk. **With
  selection closed and the data path dead, the O-track has no item that can advance without the
  owner**; the one that would have been next - the same premium in cash-settled European **SPXW**,
  where O-2's fatal exit assumption becomes a fact and the commission per unit of risk falls ~10x -
  is one `fetch_day('SPXW', ...)` away and is blocked precisely by the 478.
- **O-2 DONE 2026-09-10 (see journal): the SPY 0DTE credit spread has a real, calibrated gross
  edge and it is still refused - at the quote it loses in 8 of 11 years, and the version that wins
  needs a settlement convention the data cannot price. Nothing shipped.** Research needed no owner
  action: permission blocks deployment, not measurement. Built `scripts/odte_data.py` (1,884
  expirations 2016-01-08..2026-09-10, 5-minute bid/ask both rights, +/-30 strikes, ~17.8M rows),
  `scripts/sweep_o2.py` and `scripts/_o2_confirm.py`; 16 ledger rows under `options/odte_put_spread`.
  **The instrument was proved before its verdict**: strike selection reads the risk-neutral prob-ITM
  off the chain's own slope (`dP/dK`, no vol model, no external data) and realized breach tracks the
  quoted probability at every delta on both rights while sitting **below** it at **z = -2.7 to -3.8
  in six of six cells** - the variance risk premium, measured. **Stage 1 (36 pre-registered cells,
  closed at the quote at 15:50): 0 of 36 pass.** As % of the position's own max loss per session:
  gross **+0.783**, quoted spread **-1.363**, commission **-0.950**, net **-1.530**; the mid edge is
  **a third** of the cost of harvesting it and on a $355 risk unit the commission alone exceeds the
  gross. Cheapest possible version (72 cells) tops out at **+0.30% at t = +0.94, at zero commission**.
  **Stage 2 is the whole result**: letting an untouched position expire instead of buying it back
  flips the sign to **+0.767% at t = +3.05, 10 of 11 years positive**, with entry time a monotone
  shelf (09:35 +0.09 / 12:00 +0.685 / 14:30 +0.907 / 15:30 +0.684, t rising 0.19 -> 5.20) - while the
  same cells closed at the quote earn **-0.282% at t = -1.16**. **The exit assumption is what fails**:
  SPY settles on the official 16:00 print and is exercisable against until 17:30 ET, so requiring the
  close to clear the short strike by a buffer walks the result +0.767 (2 regimes) -> +0.583 (1) ->
  **+0.445 at t = 1.78 and 0 regimes at a 0.10%-of-spot buffer** -> +0.202 at 0.20%. **The median
  session closes 0.28% of spot from the short strike** (p25 0.14%, p10 0.06%, p5 0.03%) and 37.4%
  close within 0.2%, so the edge lives in the last few cents at the bell. **On the mandate**: the
  best cell earns +0.767% per unit of equity at risk, so 3%/day needs **3.9x equity at risk** against
  a defined-risk ceiling of 1.0x, where the worst session is **-105%**; at a survivable 0.25x the
  ledger row is CAR 21.5% at a **60.6% drawdown**. **Do not re-open as a delta, width, entry-time,
  structure or stop question** - the grid spans all five and the negative is decided one level above
  them. What would re-open it is **different data**: OPRA quotes through the close plus a measured
  settlement print, which is an owner purchase (see `BLOCKERS.md`), not a loop decision.
- **A-11 DONE 2026-09-11 (see journal): the impossible fills are real, four times larger than the
  IBKR window showed, and they are not load-bearing - and the executable half of the universe is
  the half that never made money. Refused, nothing shipped, `part_cap` stays 0.** Diagnostic over
  90,441 fills / 2,686 Alpaca sessions: notional-weighted **p50 1.46% / p75 4.71% / p90 18.80% /
  p99 950% / max 38,759%** of the fill minute's volume (A-5 on 260 IBKR sessions: 1.03 / 5.55 /
  26.1 / 199), with **24.1% of notional above 5% of its minute, 9.7% above 20%, 4.1% above 100%**;
  the store is split-adjusted on price *and* volume, verified against the raw tape, so the ratios
  are real. The cap cells (clip to a share of the trailing-median volume of the fill minute,
  knowable at decision time, worked over following bars) give **-331 / -336 / -367 / -430 $/day**
  at paired t **-0.25 / -1.24 / -2.40** against costs/day **907 / 917 / 941 / 969**: at 0.10 the
  backtester clips 213,338 orders refusing a cumulative $4.78M/day of intended notional (vs
  $3.59M/day executed) and the book moves -$5/day, **+$10/day of which is the slicing commission,
  so implied Δgross is +$5**. **Outcome (c) of the pre-registered rule: the defect is real and
  immaterial** - the fills nobody could get were not the ones making the money, so every A-track
  number stands and switching the cap on buys nothing at 3x the turnover. **The finding is the
  universe split**: liquid 8 (8.8% of notional above 5% of the minute) **-$195/day at t = -1.89**,
  the sharpest negative this sleeve has produced; illiquid 8 (45.8%) -$164 at -0.83; paired
  difference -$31/day at t -0.18, corr 0.498. **On the 261-session fitted window the liquid half
  earns -$102/day and the illiquid half +$361/day**, so the sleeve's only positive evidence in
  eleven years lives entirely in the names whose fills cannot be trusted. **Do not re-open as a
  cap-level, helper or universe question** - the mechanism was measured on 90,441 fills and both
  directions are closed. 18 ledger rows under `intraday/active`; only `scripts/sweep_a11.py`
  changed (a `--label` flag). Rule (a) owed no replay (no file the trader loads moved); run anyway
  with the deployed config: 34 trades, 368 decisions, flat, P&L -2,302 on 500k.
  **Implementation status as of 2026-09-10 (A-5 part 2)**: an interrupted session left the whole
  thing in the tree, and it is now committed - `intraday_common.volume_limits()` (trailing median
  volume per session and minute-of-day, strictly prior sessions, so it is causal),
  `part_cap` in `intraday_backtest.py`'s `RISK` defaulted **0.0 = off** with the clip applied to
  what executes rather than to the no-trade band, and `scripts/sweep_a11.py`. **The default is
  proved bit-for-bit inert**: the A-5 part 2 control run went through that path and reproduced
  A-5's recorded ledger row to every digit. **No sweep has been run**, so the item itself is
  untouched; what remains is exactly the study below, and it must now be judged against the
  corrected commission model (breakeven 2.52 bps, control $557/day), not A-5's pre-fix numbers.
  Still a real cost-model defect - over 12,743 fills the order is median 1.03%, p90 5.55%, p99
  26.1% and at worst 199% of the minute's volume, concentrated in SMCI/SOXS/COIN/MSTR - but A-10
  measured the sleeve as negative *before* removing any impossible fill, so a participation cap
  can now only make a losing book smaller. Take it when a signal tests positive on the Alpaca
  regimes, and take it before any such signal is sized. Original statement: The one thing A-5
  found that the bars *prove* is wrong rather than merely leave uncertain. Over the deployed mix's
  12,743 fills on the 260-session store, the order is **median 1.03%, p75 2.43%, p90 5.55%, p99
  26.1% and at worst 199%** of the volume of the minute it fills in, and the tail is not random:
  **SMCI (median 5.5% / p90 17.3%), SOXS (2.8% / 18.7%), COIN (3.1% / 10.6%) and MSTR (2.2% /
  6.1%) carry 30% of the sleeve's traded notional**, against 0.2-0.9% for the megacaps. A fill of
  a fifth of a minute's volume at that minute's open with zero impact is not a fill, and 199% is
  not a trade at all - so an unknown part of the sleeve's $1,430/day gross is booked at prices that
  never existed. **This is a cost-model defect, not a lever**, so A-4's power argument (a real
  effect must be visible on 260 sessions) does not excuse leaving it: the question is not whether
  a cap earns more, it is what the sleeve earns when the impossible fills are removed.
  Implementation: a participation cap in `targets_to_orders` - clip `|delta|` to
  `part_cap * <trailing median volume of that minute-of-day for that symbol> ` (trailing, so it
  stays causal; the backtester and `scripts/intraday_trader.py` must use the same helper in
  `scripts/intraday_common.py` or they will drift). Sweep `part_cap` at 0.02 / 0.05 / 0.10 / off
  on both halves with `scripts/sweep_a5.py`'s cached control as the baseline. Expect the sleeve to
  get *smaller*, not better - the honest outcome is a lower gross with the same Sharpe, which
  would mean the shipped numbers were inflated by fills that cannot happen. Because it changes
  sizing in shared code it needs a replay before any config write (rule a) and OOS evidence
  before `live/intraday_config.json` moves (rule c). A full-store run is ~17 minutes; use the
  `results/a5/control*` cache and `--workers`.
- **A-5 Execution quality from the live log. Part 1 DONE 2026-09-10 (see journal); the live half
  is still open and is a standing per-session job.** What part 1 settled: the sleeve's **breakeven
  slippage is 2.62-2.64 bps against a shipped 1.5**, P&L is linear in the constant to $73/day
  (0 bps -> $1,671/day / CAR 41.9% / Sharpe 1.51; 1.5 -> $610 / 15.3% / 0.69; 3.0 -> -$231 /
  -5.8% / -0.11), turnover is **$5.46M/day on a $1M book** so one bp is $546/day, and **the
  holdout breaks even at -0.02 bps** - gross P&L before any slippage on the 77 unseen sessions is
  -$11/day, which reframes A-4's -$813/day as no gross edge rather than a weaker regime. Bars
  cannot pin the constant: Roll and Corwin-Schultz give a notional-weighted half-spread of 2.65
  bps but `corr(estimate, 1-min return std) = +0.906` and CS/vol is 0.32-0.65, so the estimator is
  volatility; the tick floor is 0.36, leaving **[0.36, 2.65] against a 2.62 breakeven**. The
  fill convention hides nothing: decision close -> next bar open is **-0.12 bps (se 0.04)**.
  **What remains is the measurement itself**, and the tool is built and self-tested:
  `python scripts/slippage_report.py` prices every live fill against the same next-bar open the
  backtester assumes (positive = worse than the backtest), pooling notional-weighted mean, its
  standard error, per-symbol and per-side breakdowns, fill rate and latency, across every
  `live/log/intraday-<date>.jsonl` on disk. Run it after **every** paper close and report the
  running mean and standard error; the first session with fills is 2026-09-10 (the only earlier
  log is a hand-started `--dry-run` with zero orders). Move `SLIPPAGE_BPS` only when
  |measured - 1.5| exceeds two standard errors, with a replay and a journal entry (rule a) - the
  script prints that test and refuses to write the constant itself.
- **A-9 DONE 2026-09-10 (see journal): the day's range pays, but only the part that is not
  knowable at entry; nothing shipped.** ORB's daily P&L correlates +0.568 (t = +11.09) with the
  realized full-day range and +0.665 (t = +14.29) with the part of it left after regressing out
  the opening range - both stable across halves - but only **+0.080 (t = +1.28)** with the
  opening range itself, and -0.009 on the holdout, despite the opening range predicting the
  day's range at corr +0.626. **Mechanical reason: ORB's stop is the range midpoint, so the
  width is the risk unit** - a wide opening scales win and loss together, and the payoff is in
  the range the day adds after entry. Attribution over 3,731 traded symbol-sessions agrees
  (corr +0.029 raw, +0.036 within-symbol, splitting TUNE +0.052 / HOLD -0.022). Shipped to the
  tree defaulted off: `range_atr_min` / `range_atr_max` on the ORB module (snapshotting ATR14
  when the range closes, so a session's gate is one number per symbol), `scripts/sweep_a9.py`
  (attribution + two grids), and an opt-in `collect_trades` in `scripts/intraday_backtest.py`.
  **The grid is the A-track's sharpest overfitting demonstration**: every wide-opening cell wins
  the tuning window and loses the holdout, every narrow-opening cell does the reverse, `min 3.6`
  scores TUNE Sharpe 2.17 against HOLD -1.19 and `max 3.6` scores HOLD 1.46 against TUNE -1.27,
  and no cell reaches |t| = 1.6 paired against the control on 260 sessions. Replay of 2026-09-08
  passed (46 trades, flat at close). **Do not re-open this as a "better threshold" question** -
  the negative is about what is available at entry, not about where the cut goes.
- **A-4 DONE 2026-09-09 (see journal): the store is 260 sessions and the sleeve's return is not
  distinguishable from zero; nothing shipped.** Store extended to 2025-08-26..2026-09-08 and a
  truncation bug fixed - requests ended at the wall-clock time of the run, so IBKR truncated the
  newest session of every window into a partial day that strategies then traded as a full one;
  `snap_after_close`, `--repair` and `truncated_sessions()` in `scripts/intraday_data.py` fix it,
  all 16 symbols now hold 261 sessions with only the two real NYSE half days short, and A-7's
  control reproduces on the repaired bars to a tenth of a point. New `scripts/sweep_a4.py`.
  Holdout (77 sessions never seen by any A-track parameter) vs tuning window (183):
  mix **-19.1% / -0.73 / -$813 day** vs **+33.8% / 1.27 / +$1,289 day**, orb only -5.2 / -0.08 /
  -$209 vs 24.5 / 1.00 / +$943, late fade only -13.5 / -2.46 / -$563 vs 6.2 / 1.09 / +$243.
  **None of it is measurable**: Welch t between halves -0.96 / -0.51 / -1.65, and pooled over
  260 sessions the mix is $610/day, std $16,222, **CAR 15.3%, Sharpe 0.69, t = +0.61, 95% CI on
  the year [-$354k, +$671k]** around $158.6k. **The power calculation is the durable result:
  ~8.4 years / 2,120 sessions are needed to reject zero at 2 sigma**, so no reachable sample validates this
  sleeve and no A-track lever hunt on this harness ever could. The late fade is worth **$1,099
  over 260 sessions** and +$65/day marginal (t = +0.27). Refused to drop it: it improves the
  holdout but costs $16.8k over the full store, which is not rule (c)'s OOS improvement.
  Successor is A-9; the owner question is in `BLOCKERS.md`.
- **A-7 DONE 2026-09-09 (see journal): the framework risk limits are a tail dial with no
  measurable price; nothing shipped.** The daily loss limit's tail response is monotone and
  mechanical - worst day -20.5k (1.5%), -25.8k (2.0%), -30.3k (2.5%, shipped), -37.2k (3.0%),
  -42.5k (3.5%), -57.0k (off) - with a 0.15-0.38 point overshoot past nominal, since the breach
  is marked to close and the flatten pays spread. Its return response is scatter: total P&L
  200.5k / 221.2k / 243.1k across 2.0% / 2.5% / 1.5%, and **paired on 183 daily returns every
  cell in the sweep scores |t| <= 1.06**. **Stopping early is free** - on halted sessions the
  halted book beat the limit-off run on the same dates at every limit except 2.0% ($453/halt
  saved at 1.5%, which fires on 22% of sessions; $8,497/halt at 3.0%) - so the stated worry that
  a frequent limit forfeits the session's edge is measured and refused. `PER_SYMBOL_HARD_CAP`
  is **inert**: 0.12/0.15/0.20/0.25 are bit-identical, the mix never asks for more than ~0.12 of
  equity in one name, and below 0.12 the cap is a size dial (0.10 is a spike on IS Sharpe with
  both neighbours losing, refused). Gross saturates at the deployed 1.5 and 2.0 is an
  owner-level risk decision. Nothing changed in `scripts/intraday_common.py` or
  `live/intraday_config.json`, so the trader is byte-identical and no replay was owed. Shipped
  instead: a backtest-only `--risk` override in `scripts/intraday_backtest.py` (`RISK` dict,
  defaults exactly the shipped constants, recorded in the ledger when non-default) plus
  `scripts/sweep_a7.py`, and `Worst Day` / `Loss Limit Days` are now ledger columns. The priced
  menu for the loss limit is a one-line question in `BLOCKERS.md`.
- **A-1 DONE 2026-09-09 (see journal): the VWAP fade is repairable but not additive; retired
  from the mix, alloc stays 0, `live/intraday_config.json` untouched.** Of the five levers,
  only the **session-trend filter** is a mechanism: taking only the fades that lean with the
  day's direction moves the module from IS -56.0 / OOS -10.1 to -11.9 / +16.9 at a third of
  the turnover, and **inverting the filter fails as predicted** (-46.3 / -5.5), so the fade was
  losing by fighting trend days. Min hold, a midday blackout and a 5-minute cadence only shrink
  the position (all still worse than -50 IS); range expansion leaves 0.8 trades/day and is an
  empty sample. Stacking levers walks a frontier rather than climbing: the only cell positive
  in both halves is trend 20 bps + band 70/15 + hold 20 at **+0.8 / +11.3**, and +0.8% CAR at
  Sharpe 0.13 on 124 sessions is indistinguishable from zero. **The sleeve decides and says
  no**: at alloc 0.25/0.5/1.0 across three fade cells, IS CAR falls monotonically
  (24.21 -> 23.48 -> 22.25 -> 20.74) and IS drawdown widens 1.2-3.9 points while OOS rises to a
  peak near 0.5, so total P&L over all 183 sessions is $221.2k deployed against $216.9-225.2k
  for the fade cells - a +/-2% wash bought with 22-34% more trades per day. Refused on that.
  The module and all five levers stay in the tree defaulted off, control reproducing A-6 to the
  digit; revisit only when A-5 replaces estimated slippage with measured.
- **A-2 DONE 2026-09-09 (see journal): shipped a 4x ATR14 disaster backstop on ORB; the
  stated hypothesis was refused.** No variant cuts the tail while keeping the return - the
  response to stop distance is monotone and *rotates* return from the IS half to the OOS half
  (midpoint 35.7/10.7, +4x ATR 31.4/19.3, +3x 21.5/26.5, pure 1.5x ATR -12.3/43.1), with the
  two-half mean roughly conserved. The tail only comes off at a stop tight enough to zero the
  in-sample return: pure 1.0x ATR takes the worst day -33.9k -> -21.4k and the loss-limit days
  to 0/0 at IS CAR -0.3%. Scale-out at 1.5R (24.8/8.0), a 30-minute range (15.9/-1.1) and a
  1.6x volume filter (15.0/-9.8) all lose in both halves and are not carried forward. Shipped
  `disaster_atr=4.0` on the sleeve mix (IS 27.2/1.10 -> 24.2/1.01, OOS 36.2/1.24 -> 55.3/1.73,
  worst day flat, one fewer loss-limit day, $201k -> $221k over 183 sessions) as a shelf point
  - 8x is indistinguishable from off, 6x/4x/3x walk the frontier smoothly. Follow-up is A-7.
- **A-6 DONE 2026-09-09 (see journal): deployed mix re-derived on 9 months = ORB 1.0 + late
  fade 1.0, no VWAP fade.** Kept for the record:
  A-0 found the edge in the *inverses*: late-day fade (robust in both halves) and VWAP fade
  (huge OOS, negative on the longer IS window, i.e. a regime bet at half size). Re-run
  `scripts/intraday_backtest.py` for orb, vwap_trend(direction -1, band 30/8, mom 15),
  late_momo(direction -1), gap_fade and the `active` mix with `--start <first session>
  --split <2/3 point>`; keep only strategies positive after costs in both halves; if VWAP fade
  is negative on the long window, set its alloc to 0.25 or 0. Record the mix change in the
  journal and `live/intraday_config.json`. Also verify the store has no dropped first-of-window
  sessions (compare session count to the daily calendar; `intraday_data.py` now overlaps
  windows, re-run `--months 9 --force` if gaps exist).
- **A-8 DONE 2026-09-12 - REFUSED, 0 of 11 cells; see the A-8 block at the head of this section
  and `research/journal.md`. The parked text below is kept as the pre-registration, including the
  power objection that expired when the Alpaca store reached 2,686 sessions.**
- **A-8 (original text, kept for the pre-registration) The one ORB lever A-2 did not spend: the entry window.** `entry_after` /
  `entry_before` / `time_stop` were left at 15 / 150 / 240 throughout A-2, and the frontier it
  found says the shipped edge is concentrated in *which* breakouts are taken, not in how they
  are stopped. Sweep the entry window and the time stop, and check the result separately on
  the leveraged ETFs (SOXL/SOXS) where the range is wider, since the backstop now scales with
  ATR and those names are where it binds most. **Parked, and A-4 says park it harder**: the
  extra 77 sessions did not buy the power A-7 was missing - at Sharpe 0.62 the sleeve needs
  ~2,600 sessions to prove *itself*, so an entry-window sweep would again produce a table of
  statistically identical cells. Take it only after A-9, and only if A-9 finds an effect large
  enough to be visible on 260 sessions.
- **A-3 Deployed mix.** Set `alloc` and `gross` in `live/intraday_config.json` from OOS
  evidence: strategies with negative OOS after costs get alloc 0 until fixed. Target gross
  1.0-1.5x of NAV so daily P&L swings are in the tens of thousands on the $1M account, with the
  framework's 2.5% daily loss limit as the floor.
- **P-1 DONE 2026-09-10 (O-1 iteration, background): the alert path can no longer fail silently.**
  `intraday_common.notify()` and `paper_trade.notify()` now always append the alert to
  **`live/log/alerts-<date>.jsonl`** - `{ts, event: "alert", source, text, delivered, error}` -
  and only then attempt the chat push, which is allowed to fail. `delivered: false` with the
  reason is the durable trace that was missing on 2026-09-09. **The daily review must read that
  file**; any `"delivered": false` line is an alert nobody received. No credentials were touched:
  the chat channel itself is still unconfigured (`live/alerts.json` does not currently exist on
  this machine, so both notify paths were silent no-ops, not just the Telegram one), and making it
  work remains an owner item. Verified by self-test from both modules and by re-running
  `compare_orders.py` after the `paper_trade.py` edit (3,689/3,689 dates, PASS). Kept for the
  record, the original item: `live/log/2026-09-09.jsonl` carries
  `notify_failed: Telegram bot token missing. Set TELEGRAM_BOT_TOKEN or channels.telegram.botToken`
  from the 2026-09-09 paper session, so `live/alerts.json`'s phone alerts never leave the machine
  and a live failure - a rejected order, a halted sleeve, a launcher preflight refusal - is visible
  only if someone reads the logs. Either configure the channel the loop is allowed to use or
  degrade the alert to something that cannot silently fail (append to a file the daily review
  reads, and surface it in the report). **Do not touch credentials**: if the fix needs a token,
  it is an owner item for `BLOCKERS.md`, not a loop item.
- **D-2b Extend the LEAN minute store past SPY.** SPY is done (see Done). QQQ, IWM, TQQQ and
  SQQQ are one command each - `py -3.11 scripts/fetch_minute.py --symbols QQQ --start 2020-01-01` -
  and the script is resumable by month, so an interrupted run is restarted by re-running it.
  Budget ~40 minutes of wall clock per symbol-decade; IBKR serves ~260-790 bars/s and that is
  the binding constraint, not pacing. Run it in the background of another iteration rather
  than spending a whole iteration on it.
- **S-2 DONE 2026-09-11 (see journal): the index-ETF opening-range breakout carries +1.09 bps of
  directional edge at most against a 3.65 bps round trip, and most of its apparent gross belongs
  to the stop, not the signal. Refused, nothing shipped, and the LEAN build was not owed.**
  Fetched SPY/QQQ/IWM from Alpaca SIP (2016-01-04..2026-09-10, ~1.046M bars each; the store is
  now 63 symbols) and built `scripts/sweep_s2.py`. **Stage 1, 2,687 sessions, 16 breakout cells
  and their 16 fade controls, nothing fitted: 0 of 16 pass** - best on net `orb15 mid e120`,
  gross +2.11 bps/trip, cost 3.65, net **-1.54**, -$113/day at t -1.64. **The keeper is the
  decomposition**: the fade earns positive gross in **14 of 16 cells**, so
  `(brk + fade)/2` - positive in **all sixteen**, +0.33 to +1.43 bps - is stop convexity that a
  coin flip collects, and only `(brk - fade)/2` belongs to the signal: **max +1.09 bps (0.30x
  cost), negative in 6 of 16 cells.** Any ORB study that reports gross without its own fade
  control is reporting this artifact. TQQQ (the leveraged read, 8 cells): cost **4.85 bps**, 0 of
  8, and in its best cell breakout **+$33.78/day** against fade **+$33.79** - identical, i.e. no
  direction at all - while its widest cell runs +$225 / +$95 / -$396 across the three regimes.
  **Stage 2**, the shipped ORB module through the deployed framework (`--symbols SPY QQQ IWM`,
  0.36x gross on $1M, 3 ledger rows): **-$186 / -$211 / -$39 per day, 0 of 3 regimes**, i.e.
  **+$11/day of gross over eleven years against $171/day of costs**, with gross negative in two
  regimes separately. **Do not re-open as a range-length, stop, entry-window, symbol or
  resolution question** - the grid spans the first four and the negative is on gross, in both
  signs, through two independent instruments. The one thing not tested and not on this backlog is
  a breakout held **longer than a session**; everything here pays a round trip every day. Stage
  1's only optimism (closing an untouched trip at the last minute bar instead of the auction)
  favours the strategy, so modelling the 16:00 auction in LEAN - what this item asked for - could
  only make it worse, which is why no LEAN run was owed. On the mandate: daily P&L sd is
  0.13-0.20% of equity at 0.36x gross, ~0.5% at 1x, alongside L-1's 0.49% and X-1's 0.27%. Kept
  for the record, the original item: intraday on SPY first, then QQQ/IWM as D-2b delivers them;
  enter on a break of the first 15-30 minute range with ATR stops, scale out into strength, flat
  at close; judge with the same IS/OOS split and the promotion rules, recording correlation with
  the champion's daily returns as a first-class metric; **model the 16:00 closing auction**,
  because D-2 measured the daily close diverging from the last 1-minute bar by up to ~1% on
  violent days.
- **S-5 Allocator.** Route capital across S-1, S-2 and any future sleeve by trailing 60-day
  Sharpe with a floor per sleeve. Scaffold now against the S-1 and S-3 return series.
- **I-1 IBKR paper runner: DONE 2026-09-09, paper trading approved and scheduled.**
  `scripts/paper_trade.py` (ib_async) already exists and passes `--mock --dry-run` against
  `algorithms/s1_momo/signals.py`: it introspects the signal signature, feeds back
  `diagnostics["state"]` and an equity curve, sizes whole shares, logs to `live/log/`, and
  refuses to trade without `live/APPROVED_PAPER.md`, a `DU` account, or with `live/HALT`
  present. `scripts/install_paper_task.ps1` schedules 15:45 ET weekdays. Do not rewrite it.
  Remaining work once the 10141 disclaimer is accepted, in order: `--check`, then a
  `--dry-run` on the real account, then `py -3.11 scripts/compare_orders.py`. **That last
  step is now automated and already passing** - it was the manual "compare the runner's order
  list with what the backtest would have done" item, and building it on 2026-09-09 caught the
  `MIN_NOTIONAL` band bug that would have doubled the paper account's order count (see the
  journal). It needs no IB connection, so re-run it after any change to `plan_orders`,
  `submit_targets` or `min_order_value`; exit 1 means the runner and the backtest have
  drifted apart and the deploy should stop. S-6 did not change netting or staging -
  `plan_orders()` already nets against current positions - but it did add the
  `MAX_MARGIN_USED = 1.0` backstop, and the mock plan is now a 1.5x gross book, so the
  paper account must have margin enabled or the first real order will be rejected.
  Re-verified `--mock --dry-run` against the **S-12** champion on 2026-09-09 (1.23x gross,
  margin 0.75, XLE/XLK/TQQQ, with the new `alloc_vols` tilt visible in the diagnostics); the
  pre-deploy comparison is against `OrderListHash 5246804e17a67af90028ffceead7d3b3`.
- **D-2 Intraday data (blocks S-2).** `fetch_data.py` writes daily bars only; Yahoo caps
  1-minute history at ~30 days, which is useless for backtesting. Once IB Gateway is logged
  in, pull minute bars with `ib_async` `reqHistoricalData` (1-day chunks, respect pacing
  limits) for SPY/QQQ/IWM/TQQQ/SQQQ first. LEAN minute format:
  `equity/usa/minute/<symbol>/<yyyyMMdd>_trade.zip` holding
  `<yyyyMMdd>_<symbol>_minute_trade.csv` with rows `<ms since midnight ET>,o,h,l,c,v`,
  prices scaled by 10000. Reuse the writer/validator structure already in `fetch_data.py`.
- **S-2 Opening-range breakout.** Intraday on SPY/QQQ/IWM (futures later). Enter on a
  break of the first 15-30 minute range with ATR stops, scale out into strength, flat at
  close. Hypothesis: high-frequency small edges compound into volatile but positive equity.
  **Blocked on D-2**, which is blocked on the IB Gateway login.
- **S-5 Allocator.** Route capital across S-1, S-2 and any future sleeve by trailing 60-day
  Sharpe with a floor per sleeve. Still worth building - S-3 proved the market-neutral
  construction really does deliver orthogonality (corr -0.03 with the champion) - but it
  has nothing to allocate *to* until a second sleeve has a positive expected return, so it
  sits behind S-2. **Its plumbing is the designated offline work** if the API stays blocked:
  it can be scaffolded and tested against the existing S-1 and S-3 return series without
  touching the champion.
- **E-2b Generalize `sweep_s1.py` off S-1.** Explicitly deferred when E-2 shipped; the second
  designated offline item. Needed before any second sleeve can be swept the same way.
## Done

- **E-11 The morning gate waited 105 s for 1,003 tests that could not change its answer.
  DONE 2026-09-13.** E-8 scoped the refusal to the `runner` tests and E-10 stopped a hang
  reaching round it; both left the verdict being reached *through* the full suite. Measured
  old against new on eleven repo shapes with real pytest, the verdict differs in **exactly
  one**: suite failed + marker missing, which refused - i.e. the full suite's only
  contribution to this gate was a self-inflicted outage of the shape E-5 forbids. It cost
  **105 s of a 119 s preflight** against a 09:30 open, and the suite grew **1,171 -> 1,470
  tests / 82 -> 145 s inside 30 hours** under five concurrent tracks, none of which owns that
  deadline; the 223 deciding tests are flat at ~19 s. So the gate is `-m runner` alone and the
  rest runs as `full_suite_report`, a daemon thread beside the trader at below-normal
  priority, logging `suite_report` and alerting - it cannot touch the exit code (AST-pinned,
  the E-9 shape). Time to the launch decision **118.7 s -> 36.3 s**, replay byte-identical
  (2026-09-11, P&L -2,080, 36 trades, flat). A missing marker now trades with a **GATE
  DISARMED** alert, because the test that would catch a broken marker is deselected by it.
  Found and fixed on the way: `test_the_real_suite_marks_the_trading_path` asserted a
  repo-wide collect returned 0, and at 06:12 it **refused to trade for real** because the
  futures track was mid-write on its own test files - the E-8 defect (a gating test whose
  verdict is a property of the machine) inside the gate's own file. It now reads the
  selection, not the exit code. Suite 1,470 + 56 in `test_launch_preflight.py`.
  **Next**, measured rather than guessed: collecting all 1,473 to deselect 1,243 costs
  **0.89 s**, so the gate's 19 s is execution, and `--durations` puts most of it in
  `test_launch_preflight.py` itself - the gate's own tests each launch a real pytest
  subprocess (0.5-2.0 s x ~25). Not urgent at 19 s against a 300 s window, but that is where
  the number lives if it ever needs to come down.

- **E-10 A hang anywhere in the suite skipped the one refusal that matters. DONE 2026-09-13.**
  E-8 scoped the power to stop the sleeve to the 216 `runner` tests, but that refusal is reached
  *through* the full suite, and `intraday_launch.unit_tests_ok` returned `True, "warn"` on
  `TimeoutExpired` without ever asking the subset. The whole suite shares one
  `PYTEST_TIMEOUT = 300`, five tracks commit into one `tests/` directory, and the suite grew
  **107 -> 1,171 tests (30 s -> 82 s) in a day**, so one hung test in any of the other 955 - a
  module-level network call, a Theta probe, a deadlock - abandoned the run before a verdict
  existed and the sleeve traded. Proven with real pytest: a failing `runner` test beside a
  sleeping file gave `may_trade=True`, and now gives `may_trade=False`; a *passing* runner test
  beside the same hang still trades, so E-5's asymmetry is intact. The answer was always cheap -
  `-m runner` deselects the hang, 12 s of the 82 s that timed out - so the fix is a budget of
  the subset's own (`SUBSET_TIMEOUT`), not a longer suite timeout the other tracks would grow
  past again. `_runner_subset_passed` became three-valued `_runner_subset_verdict`, because the
  two call sites have opposite defaults (exit 1 defaults to refuse, timeout defaults to trade)
  and each must keep its own when the answer is unreadable: the subset may move a verdict only
  when it can *prove* the trading path's state, never when it is merely silent. 7 tests in
  `test_launch_preflight.py`; `--preflight-only` exit 0 with live state byte-identical.

- **E-7 Why is the shared test suite 6x slower on 3.14 than on 3.11? ANSWERED 2026-09-13: it is
  not, and the comparison was never like-for-like.** The filed hypothesis (import cost under
  3.14) is wrong - `-X importtime` puts pytest's entire import tree at 203 ms - and the 6x was
  an artefact of *what 3.11 does not run*: it fails 9 tests and skips 7 more for want of a
  parquet engine, including the two most expensive in the suite (`test_futures_baseline`,
  10.7 s + 9.2 s on 3.14, ImportError in under a second on 3.11). Deselect the nine files that
  differ and 3.11 takes 56.7 s against 3.14's 63.1 s - **1.11x** - with fixed pytest launch cost
  0.31 s vs 0.44 s. Not worth engineering; the interpreter was never the story. The real finding
  under the timing was the suite's *growth* against a shared gate budget: see **E-10**. (None of
  the nine 3.11 failures is `runner`-marked, so E-8's narrowing already handles them correctly.)

- **E-9 Nothing consumed `store_health.py` on a schedule. DONE 2026-09-12.**
  `intraday_launch.store_warnings()` runs as preflight step 2a on the existing 09:25 task, over
  the 16 deployed symbols (2.0 s), and logs `preflight_store` every morning. Filed as wiring;
  the finding was that **E-6's own fix made the failure it guards against silent** - the shape
  test walks `last_session()` back to the newest complete session and prints `replay OK` whether
  that is yesterday or last month. On a copy of the live store with every symbol's last three
  sessions cut at 12:19, `last_session()` returned 2026-09-08 instead of 2026-09-11 and the
  morning was otherwise indistinguishable from a healthy one. `store_health`'s own `stale` WARN
  cannot see it (the store does hold bars stamped yesterday); the new `replay_lag` - closed
  sessions between the replayed day and today, counted over the trading calendar so a long
  weekend is not an alert - is the number that can. Report-only by construction: every failure
  path returns `"skipped"`, and a test walks the launcher's AST for any `if` on the outcome
  containing a `return`. Both branches proven through the real launcher (healthy -> ok, no
  alert, exit 0; dead tail -> warn incl. a store_health FAIL, one alert, **exit 0, still
  trades**), live book/approval/config byte-identical. 3.14 655 passed, 3.11 606 passed/7
  skipped; `--preflight-only` exit 0 in 1 m 11 s. Also fixed 2 pre-existing pyright errors in
  `tests/test_paper_dataquality.py` that were failing the shared `qb_check.py` gate for every
  track.

- **E-8 The launch gate could be tripped by the machine instead of the code. DONE 2026-09-12.**
  Filed as "install pyarrow into 3.11"; it was not a dependency chore. Reproducing it found a
  fifth failure the item did not name: `test_qb_scheduler`'s `resolve_workers(2, "futures") == 2`
  reads **live free memory** and returns 1 whenever commit charge is high (measured 1 at 81%),
  which is routine here because several tracks sweep concurrently - so E-5's one refusal could be
  triggered by another agent's RAM. Two more read the deployed parquet store, which a dead
  overnight fetch breaks (E-6 saw exactly that on 2026-09-11). Fixed at both levels: the five
  tests now state properties of the code (pinned `snap()` budget plus a live-machine test of the
  one-directional clamp, which holds under any load; `importorskip` for parquet), **and** the
  refusal is scoped to a `runner` marker applied from `tests/conftest.py::RUNNER_TESTS` (8 files,
  183 tests) - on exit 1 the launcher re-runs `-m runner` and that decides, with every unreadable
  answer (subset failed, no marker, nothing collected, re-run would not start) still refusing, so
  E-5's tests pass unchanged. Default is non-gating: a new test file must opt in to the power to
  stop the sleeve. 3.11 now 576 passed/6 skipped (was 5 failed), 3.14 624 passed; both gate
  branches proven on the real repo with a probe file differing only by the marker; full
  `--preflight-only` exit 0, replay of 2026-09-11 flat at end, live book byte-identical.
  A green morning still costs one pytest launch (asserted); the failure path adds 13 s.
- **E-6 Store-completeness checker. DONE 2026-09-12.** `scripts/store_health.py` +
  `tests/test_store_health.py` (27 tests). The design point: a bar count cannot tell a thin
  session (381/390, spans 09:30-15:59 - 5,710 in the Alpaca store, benign) from a dead fetch
  (170/390, last bar 12:19 - 262 there, 16 in the IBKR store, poisons a backtest). Each session
  is scored on `start_lag`/`end_lead`/`fill` against the calendar's own open and close, and only
  a contiguous hole is truncation. Report-only, findings rolled up **by date** not by symbol,
  `--strict`/`--json`/`--theta`; 63M rows in 98 s via `columns=[]`. Found: every IBKR symbol
  truncated on **2026-09-11** (~12:20 ET), 44 of 63 Alpaca symbols on **2026-09-10** - both need
  a refetch (D-track); the 0DTE store is whole (1,891 days, no missing expiry since SPY went
  daily). Also replaced `intraday_launch.last_session()`'s `>= 300 bars` guard with the shape
  test: the count rejected both complete 210-bar early closes in the store, so the morning gate
  could never replay an early close and never exercised AUD-07's calendar-aware flatten, while
  accepting a 310/390 fetch that died at 14:40. Verified by a full `--preflight-only` at exit 0,
  replay unchanged (2026-09-10, P&L -3,920, 45 trades, flat at end), live book untouched.
- **E-5 Unit suite wired into the launch preflight. DONE 2026-09-12.**
  `intraday_launch.unit_tests_ok()` runs as preflight step 1 (before the replay);
  `tests/test_launch_preflight.py` (19 tests) pins the mapping. **pytest exit 1 is the only
  refusal** (exit code 4, alert names the failing test); collection error, nothing collected,
  usage error, hang and "pytest not importable" all trade with a warning, because a missing dev
  dependency must never stop the sleeve. The trap: `python -m pytest` with pytest absent also
  exits 1, so importability is probed in a separate process first. All three branches verified
  against the real launcher with alerting stubbed (0 / 4 / 0), plus a full `--preflight-only`
  run with the replay at exit 0 in 1 m 41 s, live book and approval file untouched. Also added
  `--skip-tests` and `--preflight-only`. Corrected E-4's "0.5 s" suite claim - see **E-7**.
- **D-2 Intraday data, LEAN minute store. SPY DONE 2026-09-09**, acceptance run
  `20260909T160005Z` (`algorithms/d2_minute_smoke`, tagged not promotable; no champion change).
  `scripts/fetch_minute.py`: IBKR `reqHistoricalData` 1-min / TRADES / `useRTH=True` -> LEAN
  `equity/usa/minute/<sym>/<yyyyMMdd>_trade.zip`, raw prices with dividends left in the D-1
  factor files, sliding-window pacer for the 60-per-10-minutes rule, resumable by month chunk,
  `clientId` 31. **SPY 2020-01-02 .. 2026-09-08: 1,679 sessions, 652,650 bars, 0 missing
  against the daily calendar, 0 truncated, 0 clamped, 14 MB.** The acceptance test runs
  *through LEAN* and asserts seven properties - all PASS, and LEAN's bar count equals the
  writer's exactly - because D-1's worst bug was a file that passed structural validation and
  made LEAN return zero bars with no error; only asking the engine catches that class.
  **The bug found: `durationStr="1 M"` ending on the month's last day silently drops the first
  session of every month**, because IBKR measures the window back from `endDateTime` and lands
  after that session's close. ~5% of the sample, invisible - every surviving session is a
  complete 390 bars. Chunks are `5 W` with the overlap filtered back to the chunk.
  **Two durable facts.** (1) Minute and daily closes agree to a median 0.007%, but the six
  sessions over 0.2% are all violent days (2020-03-13/17/18/19/23/24, 2025-04-03/09): the
  daily close is the **auction print**, the last minute bar is not, so an intraday sleeve that
  flattens at the close must model the 16:00 auction or book up to ~1% of imaginary P&L on
  exactly its best days. (2) IBKR serves ~260-790 bars/s, so a symbol-decade is ~40 minutes
  and the five-symbol set is a multi-hour job - hence the resumability, and hence only SPY in
  one iteration. Remainder is D-2b. Complements, does not duplicate, `scripts/intraday_data.py`
  (parquet, clientId 61) which feeds the non-LEAN A-track harness.
- **S-13 The execution no-trade band. Closed negatively 2026-09-09**, runs
  `20260909T043527Z` (0.02), `045041Z` (0.015), `044105Z` (0.03), `044610Z` (0.05),
  `045910Z` (0.08), sub-periods `20260909T045454Z` / `045705Z`; the champion run
  `20260909T042431Z` is the 0.01 cell, so no control was needed and **no code changed** -
  `min_order_value` was already wired to `S1_MIN_ORDER_VALUE`. Full period: 0.01 24.40%/0.921/
  25.1%/4,735 orders, 0.015 24.35%/0.919/26.9%/3,887, 0.02 24.54%/0.927/25.2%/3,355,
  0.03 24.34%/0.917/25.5%/2,737, 0.05 23.92%/0.900/29.2%/2,112, 0.08 24.47%/0.920/25.4%/1,727.
  **Non-monotone and flat** - no trend in either direction across a factor of eight in the
  band, and the one deviant cell (0.05, drawdown 29.2%, four points wide of every neighbour)
  deviates in a metric no mechanism predicts, which is what path dependence looks like when a
  threshold moves *which day* a rebalance fires. 0.02 passes `evaluate.py` outright (and its
  sub-periods agree in sign: IS 19.32%/0.891/25.2% vs 19.18%/0.884/25.1%, OOS 30.98%/0.988/
  22.7% vs 30.86%/0.985/22.6%) and was **refused as a spike** - both neighbours lose to the
  champion, so there is no shelf and the +0.14 CAR sits inside the region's scatter. **The
  finding is the flatness**: ~3,000 of the champion's orders are return-neutral, worth only
  the $6.1k of commission the widest band saves in backtest, but worth that *plus* an
  unmodelled spread per order live. Filed as a live-execution question in `BLOCKERS.md`;
  the shipped default stays 0.01 precisely so the I-1 order list does not move.
- **S-12 Risk parity inside the top_n. PROMOTED 2026-09-09**, run `20260909T042431Z` (control
  `20260909T034600Z`, reproducing `ff4a7cbaaf6e36e58ace2b82ab216bdf`; window scan
  `20260909T034953Z` / `035356Z` / `035803Z` / `040157Z` / `040554Z` / `041013Z`; tilt-strength
  check `20260909T041912Z`; sub-periods `20260909T041413Z` / `041644Z`). Momentum still picks
  the three names; their share of the exposure budget is now `(1/sigma) ** alloc_vol_power` on
  the **unlevered** ranked series rather than 1/N, because equal weight equalizes notional and
  this sleeve spans 12% vol (GLD/TLT) to 30% (XLE/XLK). Shipped: `weight_mode="invvol"`,
  `alloc_vol_window=21`, `alloc_vol_power=1.0`; `S1_WEIGHT_MODE=equal` restores S-10.
  LEAN full period CAR 23.61% -> 24.40%, Sharpe 0.874 -> 0.921, drawdown 25.9% -> 25.1%,
  PSR 17.7% -> 23.0%; IS 19.18%/0.884/25.1% (beats 17.64%/0.801/25.9% on all three), OOS
  30.86%/0.985/22.6% (Sharpe ahead of 0.972, CAR 0.23 points behind). **Shelf in both
  dimensions**: windows 20/21/30 beat the champion on CAR, Sharpe and drawdown, 40/60 win on
  Sharpe and drawdown only, 10 loses; and the tilt is monotone in strength (power 0.5 gives
  24.10%/0.902, half the gain). 21 = one trading month is the a-priori point, 20 is the argmax.
  **The cost is turnover**: 2,573 -> 4,735 orders and $37.4k -> $45.7k of fees, because vol
  ratios drift and the book re-weights between rotations - so window 30 (4,102 orders) is the
  named fallback if commission ever rises. `weight_mode="rank"`, still never LEAN-tested, loses
  in the sweep (19.3%/0.93 against 21.2%/1.03) and was not carried forward.
- **S-11 The whipsaw. Closed negatively 2026-09-08**, runs `20260909T024906Z` (control,
  reproduces `OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf`), `20260909T025256Z` /
  `025647Z` / `030039Z` (hysteresis 0.05/0.10/0.20 sigma), `20260909T030434Z` (min_hold=10),
  `20260909T030824Z` (rank_persist=2), `20260909T031243Z` and `20260909T032059Z` (the two
  size-spend frontier points), `20260909T031632Z` / `031842Z` (sub-periods). No promotion.
  All three levers shipped in `signals.py` defaulted off (`hysteresis`, `min_hold`,
  `rank_persist`; env `S1_HYSTERESIS`, `S1_MIN_HOLD`, `S1_RANK_PERSIST`), plus
  `sweep_s1.py --mode s11`. **The core finding is that the champion's rotation is not
  noise**: refusing a rank crossing removes return monotonically in the strength of the
  refusal (hysteresis 0.05 -> 0.20 sigma walks CAR 23.57% -> 22.34% and Sharpe 0.873 ->
  0.827), so the frontier slides along rather than moving up. It is however a *cheap* trade
  in drawdown: `min_hold=10` costs 0.45 points of CAR and buys 3.1 points of drawdown and
  $10k of fees; hysteresis 0.05 costs 0.04 points of CAR (a rounding error) for 1.3 points of
  drawdown, 373 fewer orders and $7.8k less commission, and its sub-periods put the whole
  gain in the IS half where S-10 diagnosed the whipsaw (IS 17.73%/0.806/24.6% beats the
  champion's 17.64%/0.801/25.9% on all three; OOS is a hair behind). Spending the headroom on
  size does not recover the return - `min_hold=10` + `margin_budget=0.85` reaches 25.07% CAR
  at a matched 25.7% drawdown but 0.861 Sharpe, refused by `evaluate.py` on the Sharpe rule
  and now a named question for the human in `BLOCKERS.md`. `rank_persist` is the one lever
  both harnesses reject outright: blocking an entry parks the book in cash and buys it back,
  so it *raises* turnover (2,727 orders, $46k fees against 2,573 and $37k). Implementation
  note for I-1: (a) and (b) persist `held`/`held_age` in the existing `state` dict the runner
  already round-trips; (c) is stateless by construction.
- **S-10 Skip-a-month momentum and horizon weighting. PROMOTED 2026-09-08**, run
  `20260909T013820Z` (control `20260909T005513Z`, sub-periods `20260909T013359Z` /
  `20260909T013608Z`, LEAN skip scan `20260909T0059-0122`). Two levers, both defaulted off,
  the control reproducing S-9's `OrderListHash b763e292cb0eb9a2c81af5739188d437`.
  **Horizon weighting lost everywhere** - every vector overweighting the long horizon costs
  2-3 points of CAR and widens drawdown, on the raw blend and after standardizing
  (`mom_weights` stays in `signals.py`, defaulted empty). **The skip won, but not at the
  textbook parameter**: the 12-2 month skip (20 sessions) loses (19.6% / 0.72), the shelf is
  at 3-10 sessions (23.0-23.6% CAR, 0.84-0.87 Sharpe), and it collapses at 2 and at 15+.
  Shipped: `mom_skip=5` (one trading week) on `mom_skip_min_lookback=120`, i.e. the 120- and
  252-day horizons only - applying it to the 20-day horizon as well costs 4.4 points of CAR,
  and confining it to 252 alone earns 23.3%, so the effect belongs to long-horizon momentum
  generally. LEAN full period: CAR 20.9% -> 23.6%, Sharpe 0.782 -> 0.874, drawdown 28.9% ->
  25.9%, orders 2,870 -> 2,573, PSR 10.1% -> 17.7%; IS 17.6%/0.80/25.9%, OOS 31.1%/0.97/21.5%,
  both ahead of S-9's 15.2%/0.70 and 28.0%/0.88. **The methodology finding matters as much as
  the result**: `sweep_s1.py` rejected this cell and inverted its drawdown ranking, so the two
  harnesses disagree in sign and LEAN decides. Also delivered the S-9(c) diagnostic that
  became S-11.
- **S-9 A second signal on the ETF sleeve. PROMOTED 2026-09-08**, run `20260908T235647Z`
  (control `20260908T234444Z`, sub-periods `20260908T235224Z` / `20260908T235437Z`). Both
  ideas S-7 named were tested and **both lost**: cross-sectional ranking against the sleeve
  median is a *looser* gate than the absolute floor at `top_n=3` of nine (17.9% CAR) and
  asking for real dispersion strands the book in cash through 2012-2019 (6.4% CAR, 49.2%
  drawdown); horizon agreement (`mom_confirm`) costs 6 points of CAR and 14 of drawdown at
  55% more turnover. Risk-adjusted momentum (`mom_score="riskadj"`) beats the champion only
  in a 15-30 day vol window, wins IS at one end and OOS at the other, and is not shipped.
  **What won was a fourth momentum horizon of 252 sessions**: LEAN CAR 18.1% -> 20.9%,
  Sharpe 0.693 -> 0.782, orders 3,410 -> 2,870, fees $38.6k -> $37.3k, drawdown 25.2% ->
  28.9%; IS 15.2%/0.70, OOS 28.0%/0.88, both ahead of the old champion's 13.5%/0.64 and
  23.8%/0.76. It is a **shelf, not a spike** - every fourth horizon from 220 to 300 beats
  the champion on CAR, Sharpe and drawdown, collapsing at 150 and 320 - and 252 is shipped
  as the a-priori one trading year rather than the 250 argmax. Also fixed a harness bug the
  scan exposed: a lookback longer than `history_bars` made `target_weights` hold cash for
  the whole sample and print a plausible 0.0% CAR, so `Params.__post_init__` now widens the
  window to `max(lookback) + 50`. Recalibration: the sweep understated LEAN drawdown by 7.8
  points on this configuration, against the +2 S-8 measured at the champion's size.
- **S-3 Cross-sectional short-term reversal. Closed negatively 2026-09-08**, runs
  `20260908T223450Z` (2012-2013 plumbing smoke) and `20260908T224519Z` (full period), no
  promotion. `algorithms/s3_reversal/` (signals + LEAN plumbing, importing S-1's drawdown
  overlay and margin table rather than copying them) and `scripts/sweep_s3.py`. The sleeve
  is dollar-neutral as designed - beta 0.07, mean |net| 0.0000 at decision time - and its
  correlation with the champion is **-0.026**, which was the point of running it. But there
  is no return to allocate: **at zero trading cost**, 24 of 30 parameter cells score a
  negative Sharpe and the best reaches only 0.27, all of it in-sample (IS Sharpe 0.64, OOS
  -0.01) in a cell chosen with hindsight over the whole sample. Inverting the sign to
  short-term continuation is not an edge either. LEAN on the best cell: CAR -0.14%, Sharpe
  -0.19, MaxDD 48.6%, 44,353 orders, **$64,721 of commission on a $100k account** - 2.1bps
  per unit of turnover, commission only, before any spread. Two durable numbers came out of
  it: that 2.1bps cost floor for any daily-turnover book at this account size, and the
  confirmation that a market-neutral sleeve is genuinely orthogonal to the champion, which
  keeps S-5 alive. The survivorship caveat on the megacap pool did not need resolving - the
  result is negative even with the bias working in its favour.
- **S-8 Reach the volatility mandate without breaching the drawdown limit. Closed negatively
  2026-09-08**, runs `20260908T213829Z` (control), `20260908T214218Z`, `20260908T214625Z`, no
  promotion. All four named levers measured and rejected: `top_n=5-6` inverts at higher size
  (S-7's headroom was a small-book property); an earlier breaker (`dd_halve` 0.08-0.10) is
  strictly dominated by carrying less size; a continuous `dd_mode="taper"` re-creates the 2015
  absorbing state and returns -0.2% CAR, because the high-water mark only resets on a *hard*
  `dd_flat` breach; and a per-holding trailing stop leaves `MaxDD` bit-identical, since the
  drawdown comes from the levered index proxies falling together. The elastic vol-responsive
  budget (`margin_budget_cap`/`_floor`) did expose a real defect - the shipped vol target is
  *saturated*, so the champion has never actually vol-targeted, it carries constant margin -
  but fixing it is a size dial, not a shape improvement: at matched 17.1% vol it loses 1.8
  points of CAR and 0.09 Sharpe to the champion while placing 30% more orders. All three
  parameters remain in `signals.py` defaulted off; the control run reproduces
  `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`. **The mandate itself is now a human
  decision** - the LEAN frontier has drawdown binding at 19-20% vol, so 40-60% is unreachable
  under a 35% limit (see `BLOCKERS.md`). Also calibrated: `sweep_s1.py` understates drawdown
  by +2 points at the champion's size and by +8 to +10 at 2x exposure, so sweeps rank, LEAN
  decides.
- **D-3 Point-in-time universe.** 2026-09-08, run `20260908T203212Z`, no promotion.
  `algorithms/s1_momo/universe.py` picks the top N of a candidate pool by trailing 60-day
  median dollar volume on each rebalance, with a 252-session minimum history;
  `Params.universe_size=0` keeps the champion's fixed sleeve, so the default is unchanged
  (control run `20260908T202809Z` reproduces the champion's OrderListHash). Membership is
  genuinely dynamic - 47 names selected across the sample, 458 entries/exits, 2012 holds
  BAC/GE/XOM/WFC/IBM and 2026 holds NVDA/TSLA/AMD - and the strategy on it scores CAR 32.1% /
  Sharpe 0.90 / DD 32.3%, beating the champion and QQQ. **It is still not promotable**, for two
  measured reasons: point-in-time selection removes only 0.8 of the 7.8 points by which the
  megacap basket beats SPY (the other 7.0 are the survivor pool on disk), and the strategy
  gives up 0.19 of Sharpe against simply holding the same 20 names. Filed as a paid-data
  decision in `BLOCKERS.md`.
- **S-7 Beat buy-and-hold on absolute return. Closed negatively 2026-09-08.** S-1 compounds at
  18.1% against SPY's 15.0% and QQQ's 19.9%. All three named levers are answered:
  momentum-proportional weighting loses 2.6-2.9 points of CAR on both sub-periods; `top_n` is
  flat from 3 to 6 in return while getting cheaper in drawdown (3 kept, 5-6 handed to S-8);
  and the wide sleeve beats QQQ only because it is levered and drawn from a survivor pool -
  under D-3's point-in-time membership it still loses to its own basket on Sharpe. Beating
  buy-and-hold on absolute return is therefore not a universe problem, and the untried ideas
  (a second momentum horizon per sleeve, cross-sectional ranking against the sleeve median
  instead of an absolute `min_momentum` floor) belong to whatever replaces the S-1 signal.
- **E-3 Promotion guard against non-statistical bias.** 2026-09-08. `evaluate.py` refuses to
  promote any run whose ledger tag contains `not promotable`, because every other rule it
  applies is a statistic and no statistic can see a universe chosen with hindsight - S-7's
  wide sleeve passed all of them. Convention: tag a knowingly-compromised run at run time.
- **S-6 Raise S-1's exposure by fixing execution, not the signal.** 2026-09-08, run
  `20260908T182554Z`, promoted to champion. Flat `max_gross_weight = 1.0` replaced by a
  margin budget, `sum(w_i * MARGIN_REQ[i]) <= margin_budget`, with Reg-T 50% for ordinary
  ETFs and 100% for 3x ETFs. Mean effective exposure 1.27x -> 1.63x, CAR 13.7% -> 18.1%,
  Sharpe 0.60 -> 0.69, MaxDD 23.6% -> 25.2%; IS 13.5%/0.64/25.2%, OOS 23.8%/0.76/24.8%.
  Option (b) netting was already in place, and option (a) two-step rotation proved
  unnecessary - zero buying-power rejections, audited margin 0.793 vs a 0.75 budget.
  **The 2x target was measured but not banked:** budget 1.0 gives 2.07x exposure and 20.4%
  CAR but a 35.4% drawdown, over the 35% limit, so the shipped default is 0.75. Raising the
  drawdown limit is a human risk decision; going past 2x on merit is S-8.
- **S-1 Volatility-regime momentum rotation.** 2026-09-08, run `20260908T174548Z`, promoted
  to champion. Full period CAR 13.7%, Sharpe 0.60, MaxDD 23.6%, 3,033 orders; IS 2012-2019
  10.4%/0.57/23.6%, OOS 2020-2026 17.8%/0.64/20.8%. Sensitivity: drawdown holds in 18.0-22.4%
  under every +/-25% shock. Two specified components were rejected on evidence - the
  vol-below-median regime filter is anti-predictive (costs 13 points of CAR) and a 200-day
  trend filter loses on both sub-periods - so the regime switch is a crisis filter at 1.5x the
  median. Signal lives in `algorithms/s1_momo/signals.py` (named `signals` not `signal` to
  avoid shadowing the stdlib module on LEAN's PYTHONPATH). Gross exposure is capped at 1.0 by
  execution constraints, so the 40-60% vol target was *not* met; that shortfall is carried
  forward as S-6, and beating buy-and-hold on return as S-7.
- **E-2 Walk-forward and parameter sweeps** (partial). `scripts/sweep_s1.py` runs ablation,
  grid, sensitivity, regime-comparison and IS/OOS modes against the shipped signal code, and
  `scripts/lean_prices.py` reads LEAN's bars back into pandas. Still S-1-specific: generalize
  to any algorithm when a second strategy needs it.
- **D-1 Data pipeline.** 2026-09-08, run `20260908T162819Z`. `scripts/fetch_data.py` writes
  LEAN daily bars, map files and factor files for 69 symbols (19 ETFs + 50 megacaps),
  1998-01-01 to 2026-09-04. Acceptance algorithm `d1_data_smoke` returns PASS: 15/15 probed
  symbols stream 3690 bars over 2012-2026; factors agree with Yahoo `Adj Close` to 0.003%.
  Minute data deferred to D-2.
- **E-1 Evaluation harness.** `scripts/evaluate.py` compares runs with `champion.json`,
  enforces the min-trades and drawdown rules and promotes only on a pass. Verified on the
  D-1 run, which it correctly refused (14 orders < 30, drawdown 72.7% > 35%). Parameter
  sweeps split out to E-2.

## Audit 2026-09-12 (operator) - fix through the normal gates, one item per iteration

Full findings with file:line, failure scenario and fix: `research/audit_2026-09-12.md`. Items
carry the owning track in brackets; record each fix in that track's journal and keep the
`--replay`, `compare_orders.py` and `tests/` gates green. Order is by what it can cost.

- **AUD-02 [eng]** `paper_trade.py:411` no floor on `net_liq`; an empty account summary liquidates the book. Exit 3 + notify on `<= 0` or a >50% move vs `last_run.json`.
- **AUD-03 [eng]** `paper_trade.py:493-497` the foreign filter drops legacy holdings whenever an intraday position exists; use `s not in _INTRADAY_UNIVERSE`. Add a test.
- **AUD-04 [eng]** `paper_trade.py:506-522` mock/dry runs overwrite `live/state/last_run.json` (it holds `equity 100000` now); `held_age` counts runs not sessions.
- **AUD-05 [eng]** `intraday_trader.py:85` a symbol without a bar this minute is marked at $0 and can trip the loss limit; keep `last_px`, exclude unmarked names, alert.
- **AUD-06 [eng]** `intraday_trader.py:319-333` in-flight orders are invisible to sizing and the flatten (duplicate sends every minute); net pending qty from the executor; lazy `FakeExecutor` in tests.
- **AUD-07 [eng+iterate]** no exchange calendar: half-days never flatten live (`FLATTEN_MINUTE` unreachable, RTH feed stops at 12:59), the harness closes silently at 12:59, the Alpaca store keeps after-hours bars on 21 early closes; holidays fire both tasks. Next early close 2026-11-27.
- **AUD-08 [eng]** start-up/`--flatten` sell the book not the account; daily HALT path sells intraday names; outside-RTH submits queue to the next open. Reconcile against `ib.positions()`, cancel open INTRADAY orders at start-up, refuse outside RTH.
- **AUD-09 [eng]** `--feed auto` always Yahoo (09:25 probe), no IB re-subscribe on reconnect, uncaught crashes leave no alert, `notify()` before the loss-limit submit, NaN price skips the step.
- **AUD-10 [daily+critic] DONE 2026-09-12 by S-34** (`scripts/sweep_s34.py`, 7 clauses,
  `tests/test_evaluate_promote.py`, `research/journal_daily.md`; no LEAN run, no ledger row,
  `champion.json` untouched). **MATERIAL on its pre-registered threshold, and not where the
  audit implied.** Priced on the real S-12 -> S-18 promotion: the CAR gap is **-0.001 at 0 bp**
  (the dead heat S-18 itself reported) and the whole damage is in risk - the retired column hands
  a candidate **+1.400 / +4.200 points of drawdown headroom** at 0 / 2 bp against a
  `drawdown_tolerance_points` of **1.0**, i.e. 4.2x the width of the rule it is added to, because
  what S-18 bought was risk rather than return. **15 of the 167 `s1_momo` ledger rows flip, all
  15 in the dangerous direction**, including five S-16 budget-0.80 cells (`20260911T120010Z`:
  26.474% / 1.012 / DD 25.700%) that clear the retired ceiling and breach the champion's - live
  candidates, since S-31 re-priced that budget the same day. Fixed in two halves that do not
  depend on each other: `promoted_columns()` (writer - the promoted run becomes the only cost
  column) and `stale_note()` (reader - refuse every comparison when no column carries the
  champion's own `run_dir`, catching a bad file however it got there, including a hand-edit or an
  interrupted promotion). Deliberately NOT "every column must be the champion's run": S-18's 2 bp
  column is a different run of the same book at the same commit and that is correct. **The
  audit's one-line fix was wrong in one place**: "delete the others" destroys the **11 dated
  `*_note` keys** sharing `stats_by_spread` (the S-21..S-33 record, 47 KB), so columns and notes
  are now separated by `cost_columns()` and the notes are preserved byte-identical - they were
  also being listed as cost models in the "not comparable" message, which is fixed. Backward
  compatibility was the withdrawal condition and holds: **167 verdicts compared, 0 changed**,
  table output byte-for-byte identical, full suite **241 pass**. Reusable rule: **when pricing a
  gate defect, read the column the gate's TOLERANCE lives in, not the column its `must_beat`
  lives in** - here the two disagree by a factor of 4,200.
- **AUD-11 [daily] PRICED AND HALF-CLOSED 2026-09-12 by S-33** (`scripts/sweep_s33.py`, 60
  DIAGNOSTIC rows `daily/s33_oos`, `research/journal_daily.md`). The finding stands; its two
  remedies do not fare the same. **Re-select on 2012-2019: REFUSED on evidence.** It moves exactly
  one of the three documented axes (`alloc_vol_window` 21 -> 10), that cell is the *worst* of its
  axis's six out of sample, and it costs **-1.865 CAR points on 2020-2026, -0.569 bps/day,
  t -2.18** - past |t| = 2 and the first non-arithmetic statistic on this sleeve to get there.
  **Relabel: ADOPTED, and now quotable with a number.** Against the 18 unique grid cells the
  shipped set sits **+0.974 above the grid mean (0.53 sd, 78th percentile, rank 14 of 18)** and
  **+0.492 above the median**, i.e. selection on these three axes inflates the published
  2020-2026 figure by about **half a CAR point at 0 bp** - under S-33's own pre-registered 0.5
  threshold for "cosmetic". Both results follow from one number: the **selection premium is
  -0.049 CAR points** pooled over 20 cells (IS top three 28.420 OOS vs IS bottom three 28.283;
  the global IS-argmax lands *below* the grid mean). Also found: **the shipped set is not the
  full-period argmax either** - `mom_skip=10` beats the shipped 5 by 0.485 on the selection window
  and was not taken, which is S-10's docstring rule behaving as advertised. Honest fully-charged
  (cell C) withheld half: shipped **25.967% / 1.151 / DD 24.040**; grid band ~20.0..27.7%.
  ~~**LOWER BOUND:** three dials priced (`mom_skip`, `alloc_vol_window`, the 252 shelf) plus the
  band by S-32; `top_n`, `target_vol`, `regime_threshold`, `regime_vol_window` and
  `target_exposure` are not, so +0.5 is a floor on total selection inflation, not an estimate.~~
  **THE LOWER BOUND IS CLOSED 2026-09-12 by S-38** (`scripts/sweep_s38.py`, 7 clauses, 123
  unique books, `research/journal_daily.md`; no LEAN run, `champion.json` untouched). **The
  floor was not the estimate.** All eight axes run: the shipped set sits **+2.073 CAR points
  above the 32-cell fitted grid mean** on 2020-2026 (0.89 sd, 84th percentile), and **+1.254**
  when the null is restricted post-hoc to the 25 cells that pass `evaluate.py`'s own 1.0-point
  drawdown tolerance - **the honest range is +1.25 to +2.07**, against S-33's +0.974 on three
  axes. Three things worth carrying: (a) **S-33's published numbers reproduce only under two
  counting conventions it did not state** - unique cells (7+6+7 = 20 is **18 unique**) and an
  inclusive rank; under the obvious alternative the same grid gives +0.877 / 65th / rank 5 of
  20, so a percentile without its convention is not reproducible; (b) the two biggest
  contributors are **`regime_vol_window` (+3.596, the one dial in the parameter set with NO
  selection record anywhere)** and `regime_threshold` (+3.016), both halves of the crisis
  switch, while `mom_skip` is a dead heat at +0.074; (c) **coordinate deltas are not additive**
  - the full-period argmax set sums to +8.492 and delivers +4.004 jointly, so the pooled-grid
  estimator is the one to quote and any total built by adding axes overstates ~2x. Mechanism
  counted rather than argued: selection ran on 2012-2026, which *contains* the withheld half,
  and the shipped value is the **OOS argmax of its own axis on 3 of 6 fitted axes** against
  0.99 expected, Poisson-binomial **P = 0.060**. By-product: **`target_exposure` is inert** -
  byte-identical book from 0.875 to 10.0 because `target_vol / sigma` cancels it, `scale_cap`
  binds only below 0.875, so the shipped 1.75 is 2x above the point where the dial does
  anything and it is **not the leverage lever it reads as** (`target_vol`, `scale_cap` and
  `margin_budget` are).
  - **STILL OPEN, and it is a one-sentence edit the daily track may not make.** The wrong label
    lives in `champion.json`'s `note`; AGENTS.md reserves that file to `scripts/evaluate.py
    --promote`, and re-running `--promote` for a wording fix would rewrite the record and trip
    **AUD-10** on the way. ~~**Fix AUD-10 first, then have the next promotion carry this
    replacement**~~ **CORRECTED 2026-09-12 by S-34: AUD-10 is fixed and this plan still does not
    work.** `--promote` updates `algorithm`, `class`, `run_dir`, `stats`, `commit`, `tag`,
    `stats_by_spread` and `promoted_at` - it has **never written `note`**, and `note` is exactly
    where the wrong label is (3,415 chars of S-18's promotion write-up, which survives every
    future promotion untouched). So no promotion can carry this replacement, and the relabel is a
    **manual edit to a reserved file**: it needs the owner or the critic's restore-with-evidence
    path, not the next candidate. It is the same defect class as AUD-10 - a promotion that leaves
    the retired champion's content in place - in prose rather than in numbers, and S-34
    deliberately did not patch it, because having `--promote` delete or rewrite `note` would
    destroy the promotion record to fix a wording bug. The replacement text, unchanged, for the
    sentence beginning "So the return difference is out-of-sample weighted...": *"The 2020-2026
    half is NOT out-of-sample: every shipped parameter was chosen on
    full-period tables, so it is a sub-period check of the chosen set (AUD-11). S-33 priced the
    contamination on the three documented axes at ~+0.5 CAR points at 0 bp (78th percentile of 18
    cells, 0.53 sd above the grid mean) and measured the selection premium at -0.049, so the
    figures below are right to about half a point and wrong in their label. IBKR paper trading
    from 2026-09-09 is the only genuinely out-of-sample evidence this strategy has."*
    <!-- S-38, 2026-09-12: the replacement text above is SUPERSEDED - it quotes S-33's
         three-axis number and S-38 has now priced all eight. Use this instead: -->
    **Replacement text, updated by S-38 (use this one):** *"The 2020-2026 half is NOT
    out-of-sample: every shipped parameter was chosen on full-period tables, so it is a
    sub-period check of the chosen set (AUD-11). S-38 priced the contamination across all eight
    tunable axes at **+1.25 to +2.07 CAR points** at 0 bp (the shipped set sits +2.073 above its
    32-cell grid mean, 0.89 sd, 84th percentile; +1.254 against the 25 cells that also pass the
    drawdown tolerance), and the shipped value is the out-of-sample argmax of its own axis on 3
    of 6 fitted axes against 0.99 expected (P = 0.060). Selection itself carries no
    out-of-sample content here - the premium is -0.049 and the full-period argmax set is worse
    on both return and drawdown - so the figures below are right to about one to two CAR points
    and wrong in their label. IBKR paper trading from 2026-09-09 is the only genuinely
    out-of-sample evidence this strategy has."*
    <!-- S-40, 2026-09-13: the label finding is STRENGTHENED and the size is now known to be
         BIASED UPWARD, so the text above is still the best available but both halves need a
         caveat when it is finally written. Strengthened: on the joint 6x6 crisis-switch grid the
         shipped cell is rank 1 of 36 on 2020-2026 and rank 24 of 36 on 2012-2019 - a single cell
         carrying the whole claim, which no percentile argument can. Biased upward: S-38 classified
         `regime_threshold` and `regime_vol_window` FITTED, but both trade return against drawdown
         by construction (ablating the switch is +2.68 CAR and +12.9 drawdown points), so their
         +3.596 and +3.016 - the two largest contributors to the +1.25..+2.07 - are partly the risk
         dial doing its job rather than selection. Re-deriving the estimate with those two axes
         reclassified RISK-POSTURE is open work; nobody should quote +1.25..+2.07 as tight. -->
    <!-- S-40, 2026-09-13: still open and still not the daily track's edit to make. -->


- **AUD-11 [daily] (original text)** the "OOS 2020-2026" label is a sub-period of full-period parameter selection; relabel or re-select on 2012-2019.
- **AUD-12 [daily+eng] DONE 2026-09-12 by S-35** (`scripts/sweep_s35.py`, 7 clauses,
  `tests/test_evaluate_param_env.py`, `research/journal_daily.md`; no LEAN run, no ledger row,
  no live-runner edit, `champion.json` untouched).
  <!-- S-36 closed AUD-25 later the same day; with it the `daily` track has no audit item left
       that needs no trading day. The pointer below names AUD-25 and is history. -->
  **MATERIAL on its pre-registered threshold,
  and live: one row in the ledger passed `verdict()` before the patch.** `20260911T184723Z`
  (S-20's defensive off-state TLT/IEF/GLD at 2 bp) returned `(True, [])` - CAR 24.982% over the
  champion's 23.068%, Sharpe and drawdown both inside their tolerances - and promoting it would
  have left the account trading the **defaults**, i.e. the book it was already trading: **+1.914
  CAR points claimed, +0.000 delivered, 0%**. The two books hold different things on **503 of
  3,689 sessions (13.6%)**; the runner is flat on 590 where the promoted book is flat on 87, and
  its universe has no IEF at all, so it could not subscribe to the promoted book either.
  **The second-order damage is larger and points the opposite way from AUD-10**: with that
  champion in place the bar is 24.982% on a book the account cannot earn, and **11 of the 167
  rows flip from "beats" to "does not"** - real candidates refused for failing to beat a fiction -
  while the drawdown ceiling moves +0.700 points the loose way. Reach surface re-derived from
  `main.py` by AST: **56 `S1_*` names, 49 reaching the shared signal path, 7 inert**, so the fix
  is an **allow list** (a deny list would need re-deriving on every new knob) and it cannot be
  read off the `Params(...)` call, because `S1_PROXY` mutates a `signals.py` global instead.
  Fixed in two independent halves - `param_env_note()` (candidate: the fifth axis-mismatch rule)
  and `champion_env_note()` (reader: refuse everything when the champion file itself records a
  reaching override) - plus `--promote` now recording the run's `env`. **The audit's second
  remedy is refused on merit**: plumbing `champion.json["env"]` into the runner and the gate
  would widen the deployed surface to buy a capability nothing has asked for, and a parameter
  worth shipping belongs in `signals.py`'s `Params` defaults, which LEAN and the runner both
  read. Backward compatibility was the withdrawal condition and holds: **167 rows re-judged,
  exactly 1 verdict moved, `yes -> no`, on the tainted row**, 0 the dangerous way and 0 on a
  clean row; suite **543 pass**. Clause 7 found `paper_trade.py:196`'s `getattr(sig, "PARAMS",
  None)` to be dead code that *reads* as parameter support, and **deliberately did not patch the
  live runner** - the refusal closes the hole, so the edit would owe a `--replay` for zero
  measured gain; the invariant is pinned by a test instead. Reusable rule: **a gate must refuse
  every axis on which a run and the deployed book can differ, and that list has to be derived
  from the source rather than remembered** - four of `verdict()`'s five rules were each added
  after one instrument appeared; asking for the whole surface instead returned 56 and 7.
- **AUD-13 [daily+eng] DONE 2026-09-12 by S-37** (`scripts/sweep_s37.py`, 7 clauses,
  `tests/test_paper_dataquality.py`, `research/journal_daily.md`; no LEAN run, no ledger row,
  `champion.json` untouched). **MATERIAL on every clause that had a threshold, and reachable:
  the scheduled task passes no arguments, so the account runs `--history yfinance`, and there
  are 0 exits between the `warning: no history for [...]` print and `plan_orders`.** Each
  defect was corrupted into the real decision frame at the real decision site and run through
  the deployed book. **The loud one:** dropping `REGIME_TICKER` makes `risk_on` return
  `"SPY missing"` and the book flat; **0.138 CAR points per outage at 0 bp, 0.252 at 2 bp**, so
  the break-even against S-33's 0.5-point bar is **2.0 outages/year** vs a pre-registered
  threshold of 12 (t 3.10 / 3.85 on the 1-in-21 cells; the 1-in-252 cells are underpowered at
  t 0.90 / 1.24), and the round trip shows up as **5,395 orders against the control's 5,052**.
  **The silent one is broader than filed:** an all-NaN column changes the funded set on
  **10.5%-83.6% of corrupted sessions for all nine names** (SPY 83.6%, XLK - the audit's
  example - 60.8% and third), while **no** CAR delta clears the 1.689 seed sd and three print
  positive; the defect is noise in the portfolio rather than a bias, so there is no direction to
  correct and refusing is the only remedy. **The stale price is real in one half only:** 29.70%
  of 33,210 name-days move more than the 1% no-trade band (p95 2.441%, i.e. 2.4x the band the
  runner refuses to trade for), but *ranking* on a stale close is worth +0.033/+0.002/-0.095/
  -0.007 CAR points - nothing. **The audit's remedy is right and its tail is the wrong
  comparison**: holding yesterday's book costs **-0.209 CAR against the flatten's -2.338** (11x)
  and wins Sharpe, but is **+0.602 worse in MaxDD than the flatten** - because the flatten's
  drawdown is *below the control's*, random liquidation being accidental de-risking. Against the
  control, the book the runner exists to reproduce, holding costs **+0.046** drawdown points,
  4.6% of the promotion gate's own `drawdown_tolerance_points`. The gate's predicate was
  measured before it was written: the audit's version fires on **0 of 3,690** sessions of the
  reference store, so it is taken as filed, narrowed to names with established history anyway
  (free, and the runner reads yfinance not this store). Shipped `data_faults()` +
  `previous_session()` called **before `call_signal`**, pinned by a test on source order; held
  names outside the universe deliberately unchecked, so the retired-TQQQ sale is never blocked.
  **`signals.py` deliberately untouched** - the refusal makes `risk_on`'s string unreachable
  from the account and the LEAN side is the same 0/3,690 (S-35's precedent). Identity exact
  before and after, `compare_orders` **3,689/3,689**, gate clean on today's real yfinance frame
  and firing on all three defects injected into it, suite **593 pass / 6 skip**, intraday launch
  preflight **green** on the 3.14 interpreter (641 passed, replay OK). **Adds no research item
  and files one `eng` item (AUD-13b).** Reusable rule: **price a remedy against the thing it is
  supposed to restore, not against the defect it replaces** - a defect that destroys return by
  accident can reduce drawdown by accident, and then the remedy looks reckless against it.

- **AUD-13b [eng] (found by S-37):** `quant_brain.core.calendar` has two entry points and only
  one enforces its own coverage contract. `CALENDAR.check_covered(day)` raises
  `CalendarCoverageError` past `coverage_end` (2027-12-31 today), but `CALENDAR.trading_days(a, b)`
  keeps answering from the weekday rule, so after that date it silently returns holidays as
  trading days. Any caller that trusts `trading_days` alone gets an unverified calendar; in
  S-37's data gate that would mean a holiday returned as "the previous session" and the whole
  daily rebalance refused over it. Worked around in `paper_trade.previous_session` by calling
  `check_covered` explicitly and pinned by `test_previous_session_never_raises_outside_calendar_coverage`,
  but the fix belongs in the module: `trading_days` should check coverage on both endpoints.
  Same shape as AUD-16 one library over - the cheap instrument answers when the contract-checking
  one would have refused.
  <!-- added by S-37, 2026-09-12 (daily). -->

- **AUD-13 [daily+eng] (original text)** no data-completeness gate in the runner: a missing SPY column flattens the whole book.
- **AUD-14 [eng+critic]** no track guard in `evaluate.py`; intraday rows carry `commit ""`; `OrderListHash` not captured into the ledger.
- **AUD-15 [data] DONE 2026-09-13 by D-5** (`scripts/sweep_d5.py`, 8 clauses,
  `tests/test_intraday_splits.py`, 2 DIAGNOSTIC rows `intraday/active`, `research/journal.md`;
  nothing under `live/` touched, replay gate run anyway because the patch touches shared code).
  **CONFIRMED, FIXED and MATERIAL at 6.0x its own threshold - and the audit's ratio is right while
  both of its levels are wrong.** The store IS adjusted: the close-to-close step across all three
  splits in its span sits at 1.0 against the raw prediction (NFLX 0.9920 vs 10, SOXS 1.0325 vs
  0.05, 1.0684 vs 0.1), decided against each symbol's own overnight-gap q99. It is also not
  **mixed**, which the audit did not check and is the thing that decides whether a factor may be
  applied at all: the monthly median IBKR/Alpaca close ratio stays in **1.00000..1.00003 for all 16
  symbols over 14 months and ~101k bars each**, worst deviation 0.00%. Table derived from a split
  CALENDAR (yfinance) rather than Alpaca's price ratio and agreeing with it on **4,208/4,208
  symbol-days**, written by the new `intraday_data.py --splits`. **Ceiling, quoted before the P&L
  column**: SOXS 2025-08-26..2026-03-04 is charged **0.074 bps/side and should be 14.706** (131
  sessions), SOXS 2026-03-05..2026-07-14 **0.503 -> 5.028** (90 sessions, a segment the audit
  omits), NFLX 2025-08-26..2025-11-16 **0.416 -> 0.042** (58 sessions, **OVERcharged** - the audit
  is one-sided). So **279 affected symbol-days, not ~188**, and the error is **14.63 bps/side, not
  ~100**: the audit's "~100 bp" is the 1% commission cap and the cap never binds at a $3.40 raw
  price. **Priced on the shipped harness, 263 sessions, paired**: net **-$1,923.8 -> -$2,460.0
  $/day (-536.3, t -4.08)**, costs **1,839.1 -> 2,387.4 (+548.3, +29.8% of the whole cost line)**,
  Sharpe -3.22 -> -4.65, DD 50.60 -> 64.70, loss-limit days 10 -> 16, 373 fewer trades - from
  **6.6% of the symbol-days and one name**. Second half of the fix shipped too: `save_bars` refuses
  a merge whose overlapping closes disagree (`BasisMismatch`, median |ratio-1| > 2% on >= 10
  overlapping bars, `allow_rebasis` / `--rebasis` for the deliberate post-split re-fetch), proven on
  the real store at **16/16 honest re-saves allowed and 16/16 x10 rebasings caught**. Suite **1,203
  pass / 13 skip**, launch preflight **green**, and the table is **inert for the live path**:
  `intraday_trader.py --replay 2026-09-11` is byte-identical with and without it (-9,489 / 215 /
  $2,498 / flat, equal to D-4's recorded replay), because the trader prices the raw tape and never
  calls `share_scale`. **Files one item (A-16) and closes one audit item.** Reusable rules: **a cost
  defect's ratio and its level are two claims** - re-derive the level from the store's own prices,
  and read the *cap* as well as the rate; and **"adjusted" and "adjusted CONSISTENTLY" are different
  questions**, only the second answered by a second store known to be on the current basis.
- **AUD-15 [data] (original text)** the IBKR minute store is split-adjusted but treated as raw: SOXS/NFLX per-share commission understated up to 100x in IBKR-store backtests; write `data/minute/_splits.json`.
- **AUD-16 [data] DONE 2026-09-12 by D-4** (`scripts/sweep_d4.py`, 7 clauses,
  `tests/test_intraday_data_extend.py`, `research/journal.md`; no ledger row, nothing under
  `live/` touched). **Both halves confirmed, both fixed, and the store repaired against the live
  gateway.** The two defects hid each other: `snap_after_close` clamped with `min(20:00, now)`,
  which during regular hours is *inside* the session it exists to stay out of (**78 of 288**
  five-minute probes on a regular day, **42** on an early close, **0** after the fix on all
  three day types), so the fetcher wrote a truncated day; then `fetch_symbol`'s "15 or more
  sessions on disk" counted that day as present, so a `--months N` run issued **0 requests for
  all 16 symbols** and could never advance past its own truncation. The skip is now "is any
  CALENDAR session in this window missing or truncated", truncation is
  `store_health.session_shapes` **imported rather than re-drawn** (0 of 16 symbols disagree with
  E-6), `--repair` spans the calendar instead of the days on disk so a never-fetched session is
  finally visible, and the settle margin is the calendar's close + 15 min (13:15 on an early
  close, not a hard-coded 16:15). **Repair: 16 requests, 6.1 min, every symbol 101,99x ->
  102,210 bars**; `store_health --store minute` now reports **0 fail, 0 warn**. **The audit's
  gate implication is narrower than filed**: `intraday_launch.last_session()` already skipped a
  truncated day on E-6's shape test, so the preflight fell back to an older session rather than
  replaying a half day - the damage was that the store froze, not that the gate broke. What the
  truncated session was worth to a consumer without that guard, same $1M base: replay **-149,012
  / 175 decisions / 14 open positions at the close** against **-9,489 / 368 / flat**, while the
  research harness moves only **-9,920 -> -9,418 (+$502, 5.3%)** and yet books **158 trades
  against 215** - a truncated session hides **27% of the day's trading** while barely moving its
  P&L. Suite **601 pass**; preflight passes and now replays the full 2026-09-11. **Adds no
  research item and closes one audit item.** Reusable rule: **a fetcher's resume rule must be the
  completeness checker's rule, imported** - a bar count is always available and a calendar has to
  be imported, so the cheap instrument wins by default and the store freezes at exactly the
  defect the checker was written to find. **AUD-24 files the same shape** for the events and
  options caches ("marked complete when partial").
- **AUD-16 [data] (original text)** `intraday_data.py` cannot extend the store and truncates today's session (all 16 symbols hold a 170-bar 2026-09-11).
- **AUD-17 [data]** LEAN daily store writes adjusted prices as raw with split factor 1; per-share fees charged on adjusted share counts.
- **AUD-18 [ml]** F-3's IC t-stat is naive on overlapping 5-day labels (NW t ~1.2, not 2.17); no embargo.
- **AUD-19 [ml]** F-7 draft: persistence table is a composition artifact; best cell chosen on the test window; report 2019-23 separately.
- **AUD-20 [ml]** F-1 row-based shifts on an irregular 5-min grid (SOXS 16.6% of sessions affected).
- **AUD-21 [iterate] DONE 2026-09-12 by A-13** (`scripts/sweep_a13.py`, 7 clauses, 7 DIAGNOSTIC
  rows, `tests/test_intraday_harness_bias.py`, `research/journal.md`). **All six fixed; worth
  +$35.3/day (t +0.69) in the mean and 37% in the tail, and the audit's "all in its own favour" is
  wrong for the largest of them.** Priced on the deployed ORB book, Alpaca SIP, 2,686 sessions:
  control **-$344.9/day t -1.41** -> corrected **-$309.6/day t -1.24**, so the eleven-year answer
  in `BLOCKERS.md` is unchanged (A-10 published -$289) and no config moved. The paired difference
  **flips sign by regime** (+34.1 / -76.4 / +204.0 at t +3.12 / -1.00 / +1.22) - it is not a
  directional bias in the P&L column. What it IS is a tail: the harness charged the daily loss
  limit against **sleeve equity** where the live trader charges it against **account NAV**, so at
  `equity_frac` 0.25 it stopped the book **4x early** on **92 of 2,686 sessions**, and removing
  those stops widens the worst day in every regime (-26,826 -> -33,445, -30,902 -> -46,850,
  -34,300 -> -45,283). Filed to `BLOCKERS.md` as an addendum, not fixed: the live limit is a
  risk-posture setting. `atr14`'s overnight gap is **real and provably inert** - `orb` reads it
  only from minute 15 and `rolling(14)` there excludes bar 0 unless the open is sparse, which is
  **0 of 10,784** pairs on 2024-2026 and **0 of 4,208** on the whole IBKR store (7.47% over the
  full eleven years); the isolated cell moves the book 1.9e-11 $/day at a paired **t of +1.93**.
  Deploy gate passed: `base.py` is live-loaded, and replaying 2026-09-10 old-vs-new gives the
  identical session (P&L -3,920, 45 trades, 368 decisions, flat at close); suite **473 pass**.
  Reusable rule: **a harness bias can be conservative in the P&L column and reckless in the risk
  column at the same time** - read both before believing an audit's sign.
- **AUD-21 [iterate] (original text)** harness: missing-bar fills at the decision close, loss-limit base mismatch vs live, bar-0 true range includes the overnight gap.
- **AUD-22 [eng]** dashboard: open orders frozen at connect, unbounded `nav_history`, no TrustedHost, NAV-append failure drops the IB session, `/api/logs` unredacted.
- **AUD-24 [data]** events/options caches marked complete when partial; `iv_regime` holiday-week holes; error-162 silence; `save_bars` lock.
- **AUD-25 [daily] DONE 2026-09-12 by S-36** (`scripts/sweep_s36.py`, 7 clauses,
  `tests/test_signals_windows.py`, `research/journal_daily.md`; no LEAN run, no ledger row,
  `champion.json` untouched, `compare_orders.py` 3,689/3,689). **Six claims, priced one at a
  time: two material, one with the audit's SIGN reversed, two documentation, one refiled.**
  Headline: the `Params` window guard is the item. Its docstring says it exists so "the horizon
  is what is being tested" and it covered **1 of the 11** integer windows; enumerating them with
  each field's companion switch ON gives **7 outside the guard in TWO modes** - **SILENT-ZERO**
  (`trend_window`, `regime_vol_window`: risk-off for the whole sample, a tidy 0% CAR, the
  audit's own example) and **SILENT-TRUNCATE** (`alloc_vol_window`, `regime_median_window`,
  `vol_est_window`, `mom_vol_window`, `trail_window`: `.iloc[-N:]` yields fewer than N bars, so
  two different values are the SAME CELL - all five give **byte-identical weights** at
  `history_bars + 100` and at `+ 500`). **The second mode is not in the audit and is the worse
  one**, because it manufactures a flat parameter **shelf**, which is precisely what S-33
  established as this sleeve's only reportable parameter result. Fixed by taking `need` over
  every price window with each one's own prerequisite; **`iv_scale_window` excluded with its
  reason** (it reads the IV store, not `prices`, and already fails loudly) - an exclusion that
  was earned, since the first probe misclassified it by measuring `iv_scale_power=0` rather than
  the field. The other five: **`ML_MODE="rank"` really does gate on two signs**, on **398 of
  3,690 sessions (10.79%)**, 525 name-days of 8,086 - and it is worth **+0.286 CAR points**
  (11.086% vs 10.800%), i.e. **the undocumented gate helps**, so the code stands and the prose
  was fixed, and **S-27's twelve ranked rows are flattered by ~0.3 points rather than penalised**.
  **The S-3 harness claim has the wrong sign**: the close-to-close convention *costs* that book
  **3.291 CAR points** (2.559% / 0.268 against 5.851% / 0.516 at zero cost) because a reversal
  signal is on the losing side of the overnight gap, which is 49.9% of the average step - but at
  the harness's own 5 bps both are deeply negative (**-8.967%** vs **-4.811%**), so **S-3's
  refusal on cost stands** and only the published margin was overstated; fixed with a
  default-inert `step_mode` (S-26/S-30/S-32 precedent). `minimum_order_margin_portfolio_percentage`
  is **inert** on the `market_order` path (17 LEAN call sites, none of them it; the real band is
  `min_order_value`) and **labelled rather than removed**, because removal owes a LEAN rerun to
  prove `OrderListHash` for zero gain - S-35's trade on `paper_trade.py:196`. `blended_momentum`
  has **zero AST references** but is the written spec `sweep_f3.py:432` points at, so it is kept
  and documented. Identity exact before and after (22.192150170492255% / 5,052, `history_bars`
  still 307), suite **615 pass**. **Adds no research item, closes the last `daily`-owned audit
  item, and files one `eng` item (AUD-25b).** Reusable rule: **a silent failure that produces a
  WRONG number is easier to catch than one that produces the SAME number twice** - every guard
  here was built against the first kind, so **before quoting a shelf, check that its cells are
  different runs**.
- **AUD-25b [eng]** `scripts/paper_trade.py:234` `fetch_history_ib` passes `endDateTime=""` and,
  unlike `fetch_history_yf`, does not drop today's unfinished session, so `--history ib` ranks on
  a partial daily bar - a third clock convention. **PREVENTIVE**: S-36 confirmed the shipped
  scheduled task uses the `yfinance` default, so the deployed runner cannot reach it. The fix is
  two lines in a live runner and owes a `compare_orders.py` run, which is why the `daily` track
  filed it instead of making it.

- **AUD-25 [daily] (original text)** `ML_MODE="rank"` gates on sign; `Params` window guard incomplete; `--history ib` clock convention.
- **AUD-01 [ops]** DONE: installers carry the battery flags and both tasks were re-registered 2026-09-12 11:12 ET. **AUD-23 [ops]** DONE: gateway watchdog task.
