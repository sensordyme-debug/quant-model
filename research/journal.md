# Research journal

Newest entry first. Each entry: what was tried, why, the result, the decision, the next step.

## 2026-09-11 - S-16: the 3x sleeve and the drawdown breaker are worth zero return between them

- **What.** S-15 removed each of the champion's switches one at a time. Two of them pointed the
  same way and were never run together: the **levered proxies** (cell e - better on every
  risk-adjusted measure when off) and the **drawdown overlay** (cell g - the only switch with a
  near-significant paired statistic, and the sign was against it). S-16 runs the interaction, then
  asks the question the attribution could not: when the unlevered book gives up exposure, what
  happens if that exposure is bought back with **account** leverage (`margin_budget`) instead of
  **instrument** leverage (UPRO/TQQQ/TMF)? Nine full-period LEAN cells plus two sub-period runs,
  all environment overrides of the shipped algorithm; `scripts/_s16_runs.sh` produces them,
  `scripts/sweep_s16.py` reads them. 11 ledger rows.
- **Why the two are the same question.** Reg-T charges 50% of notional for an ordinary ETF and
  IBKR marks a 3x ETF to 100%, so per unit of *economic exposure* the proxies cost **0.333** of
  margin and the unlevered names cost **0.5**. The 3x sleeve is 33% cheaper in margin - that, and
  not any signal, is why the champion reaches ~2.25x exposure on a 0.75 budget while the same
  signal held unlevered stops at 1.5x. S-15 measured the proxies with the exposure removed; that
  confounds the instrument with the size.
- **The control reproduces `OrderListHash 5246804e17a67af90028ffceead7d3b3`** (4,735 orders, CAR
  24.404%, Sharpe 0.921, DD 25.100%, fees $45,695.46), so every cell below is a pure override and
  the daily paper runner's path is untouched.

### 1. The table (full period 2012-01-03..2026-09-04)

| cell | budget | held | max exp | orders | CAR% | dCAR | Sharpe | MaxDD% | std | fees | PSR% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **champion (S-12, shipped)** | 0.75 | 3x proxies | 2.25 | 4,735 | **24.404** | | 0.921 | 25.1 | 0.170 | $45,695 | 23.0 |
| (e) proxies off | 0.75 | unlevered | 1.50 | 5,136 | 23.128 | -1.28 | 0.950 | 23.6 | 0.153 | $25,646 | 27.4 |
| (g) overlay off | 0.75 | 3x proxies | 2.25 | 4,768 | 25.998 | +1.59 | 0.967 | 27.2 | 0.174 | $48,970 | 28.5 |
| **(e+g) both off** | 0.75 | unlevered | 1.50 | 5,128 | **24.403** | **-0.00** | **0.994** | **23.7** | **0.155** | **$27,200** | 33.2 |
| (e) proxies off | 0.80 | unlevered | 1.60 | 5,226 | 24.551 | +0.15 | 0.964 | 25.5 | 0.162 | $29,312 | 28.7 |
| (e + wide overlay 0.20/0.30) | 0.80 | unlevered | 1.60 | 5,287 | 25.333 | +0.93 | 0.990 | 25.0 | 0.163 | $30,697 | 32.2 |
| (e+g) | 0.78 | unlevered | 1.56 | 5,219 | 25.307 | +0.90 | 1.003 | 24.6 | 0.160 | $29,800 | 34.0 |
| **(e+g)** | **0.80** | unlevered | 1.60 | 5,283 | **25.903** | **+1.50** | **1.008** | **25.1** | 0.164 | $31,622 | 34.5 |
| (e+g) | 0.82 | unlevered | 1.64 | 5,347 | **26.474** | **+2.07** | **1.012** | 25.7 | **0.168** | $33,530 | 34.9 |

Paired daily log returns, **cell minus champion** (the reverse of S-15's convention), on the 3,689
sessions both books are marked:

| cell | bps/day | t | ann.% | IS bps | IS t | OOS bps | OOS t |
| --- | --- | --- | --- | --- | --- | --- | --- |
| (e) proxies off, 0.75 | -0.41 | -1.21 | -1.03 | -0.50 | -1.26 | -0.30 | -0.52 |
| (g) overlay off, 0.75 | +0.51 | 1.93 | +1.28 | -0.11 | -0.62 | +1.25 | 2.35 |
| **(e+g) both off, 0.75** | **-0.00** | **-0.00** | **-0.00** | -0.49 | -1.25 | +0.59 | 0.84 |
| (e) proxies off, 0.80 | +0.05 | 0.17 | +0.12 | -0.17 | -0.52 | +0.30 | 0.65 |
| (e + wide overlay), 0.80 | +0.30 | 1.00 | +0.75 | -0.14 | -0.45 | +0.82 | 1.51 |
| (e+g), 0.78 | +0.29 | 0.82 | +0.73 | -0.25 | -0.75 | +0.94 | 1.42 |
| (e+g), 0.80 | +0.48 | 1.42 | +1.21 | -0.09 | -0.31 | +1.16 | 1.81 |
| **(e+g), 0.82** | **+0.66** | **2.02** | **+1.67** | +0.07 | 0.24 | +1.36 | **2.16** |

### 2. What it says

- **The two switches are worth exactly zero return between them.** Turn off the 3x proxies and the
  drawdown breaker at the same margin budget and the book earns **24.403%** against the champion's
  24.404% - **-0.00 bps/day at t = -0.00** on 3,689 paired sessions, which is as close to a dead
  heat as fourteen years can produce. It gets there at **0.155 realized vol instead of 0.170, a
  23.7% drawdown instead of 25.1%, PSR 33.2% instead of 23.0% and $27.2k of fees instead of
  $45.7k**. The champion is paying a wider risk footprint and 68% more commission for a return
  that is already there without either device.
- **The proxies buy margin efficiency, not edge.** Their whole contribution is that 2.25x of
  exposure fits inside a 0.75 budget. Give the unlevered book the same *risk* instead - budget
  0.82, realized vol 0.168 against the champion's 0.170 - and it earns **26.474% at Sharpe 1.012**,
  **+0.66 bps/day at t = 2.02**, the first t above 2 the S-track has produced *in favour of* a
  change rather than against one.
- **In an unlevered book the drawdown breaker costs return and buys no drawdown.** At budget 0.80:
  shipped overlay 24.551% / DD 25.5, widened to 0.20/0.30 **25.333% / DD 25.0**, off **25.903% /
  DD 25.1**. Monotone in return, flat-to-better in drawdown - a shelf, not a spike. This is S-8's
  re-arming problem: a step breaker that flattens at -25% and re-arms sells the bottom, and on a
  1.5x unlevered book the tail it is insuring against never justifies the sale.
- **The gain is out of sample, and the loop should say so.** Every cell is negative or flat in
  2012-2019 and positive in 2020-2026 (the winner: IS +0.07 bps/day at t 0.24, OOS +1.36 at
  t 2.16). Sub-periods for (e+g) at 0.80: **IS 18.894% / 0.923 / DD 25.1** against the champion's
  19.18% / 0.884 / 25.1, **OOS 34.687% / 1.124 / DD 23.6** against 30.86% / 0.985 / 22.6. It wins
  the half it did not come from and ties the half it did, which is the right way round, but the
  effect is one regime deep.
- **The budget response is a clean dial, not a cliff**: 0.75 -> 0.78 -> 0.80 -> 0.82 gives CAR
  24.403 / 25.307 / 25.903 / 26.474 at std 0.155 / 0.160 / 0.164 / 0.168 and Sharpe 0.994 / 1.003 /
  1.008 / 1.012. Sharpe *rises* with size here, where on the 3x book (O-1b) it fell.

### 3. Decision

**Nothing shipped and nothing promoted, and this time it is not a refusal.** Three cells - (e) at
0.80, (e+g) at 0.80 and (e+g) at 0.82 - **pass `scripts/evaluate.py` outright** ("BEATS champion":
more CAR, more Sharpe, drawdown inside the 1-point tolerance and far under the 35% cap). Every one
of them needs `margin_budget` above 0.75, and that constant is an **open owner question** opened by
O-1b on 2026-09-10 and still unanswered; `BLOCKERS.md` records that the loop will not move it on
its own, so it did not. The budget-neutral version, (e+g) at 0.75, is the one cell the loop could
have promoted by itself and it **misses by 0.001 CAR points** - `evaluate.py` reports "does NOT
beat champion: 24.403% does not beat 24.404%". The rule is the rule; it is refused, and the honest
description is a dead heat with strictly less risk.

**What went to the owner instead**: a fourth option on the open budget question, which dominates
the one O-1b put there. Option (b) was `margin_budget` 0.75 -> 0.792 keeping the 3x sleeve: about
+1.5 CAR bought at std 0.188. S-16's option (d) is the same +1.50 CAR (25.903% vs 24.404%) at
**std 0.164, the identical 25.1% drawdown, Sharpe 1.008 against 0.921 and 31% lower fees**, because
it spends the buffer on unlevered notional instead of stacking account leverage on top of
instrument leverage. The residual risk it does add is real and is stated there: the Reg-T excess
liquidity falls from 25% to 20% of equity, against economic exposure that falls from up to 2.25x
to 1.60x.

**Champion unchanged at S-12**, `research/champion.json` untouched, `live/` and the scheduled tasks
untouched, no file the daily runner or the intraday trader loads was modified (new scripts only, so
rule (a) owes no replay).

- **A-5 part 2 (standing job) had no new input**: this ran at 07:3x ET, before the open, so the
  ledger is still the single 2026-09-10 session - 32 fills, $1.87M, **+2.89 bps (se 1.33)** against
  the shipped 1.50, |diff|/se 1.05, ~6.8 sessions to settle it. `SLIPPAGE_BPS` untouched.

## 2026-09-11 - S-15: where the champion's 24.4% actually comes from, and it is mostly not skill

- **What.** The attribution S-14 asked for. Eight full-period LEAN runs, each the shipped
  algorithm with exactly one switch removed through an `S1_*` environment override, plus the
  control and a vol-matched steelman: (a) no ranking, (b) no regime filter, (d) no allocation
  tilt, (e) no levered proxies, (g) no drawdown overlay, (f) none of them at all.
  `scripts/_s15_runs.sh` produces the runs, `scripts/sweep_s15.py` reads their LEAN output.
  **Judged nothing**: the deliverable is the table and a sentence.
- **Why.** S-9 through S-14 are six consecutive iterations spent tuning the *ranker*, and S-14
  priced its entire cross-sectional contribution at +2.02 bps/day (t = 2.07). If that is the
  whole of selection, then most of a 24.4% CAR is something else, and nobody had measured what.
- **Two new knobs, both defaulting to the champion**: `S1_MIN_MOMENTUM` (the absolute entry
  floor, so "rank nothing" is expressible as `top_n=9` with the gate off) and `S1_PROXY=off`
  (drop the levered proxy map, hold every winner in its own unlevered name). The control run
  reproduces **`OrderListHash 5246804e17a67af90028ffceead7d3b3`** with 4,735 orders, CAR
  24.404%, Sharpe 0.921, fees $45,695.46 - bit-identical to the champion - so both are inert.

### 1. The table (full period 2012-01-03..2026-09-04)

| cell | orders | CAR% | dCAR | Sharpe | MaxDD% | std | fees | PSR% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **champion (S-12, shipped)** | 4,735 | **24.404** | | **0.921** | 25.1 | 0.170 | $45,695 | 23.0 |
| (a) no ranking (top 9, equal) | 1,704 | 17.700 | **-6.70** | 0.780 | 23.3 | 0.137 | $7,907 | 10.3 |
| (a2) no ranking, vol-matched | 2,332 | 20.745 | **-3.66** | 0.804 | 26.1 | 0.163 | $12,747 | 11.7 |
| (b) regime filter off | 5,495 | 22.383 | -2.02 | 0.781 | **31.4** | 0.189 | $46,318 | 9.6 |
| (d) allocation tilt off | 2,573 | 23.605 | -0.80 | 0.874 | 25.9 | 0.174 | $37,380 | 17.7 |
| (e) levered proxies off | 5,136 | 23.128 | -1.28 | **0.950** | **23.6** | 0.153 | $25,646 | **27.4** |
| (g) drawdown overlay off | 4,768 | **25.998** | **+1.59** | 0.967 | 27.2 | 0.174 | $48,970 | 28.5 |
| **(f) no skill at all** | 1,386 | **17.282** | **-7.12** | 0.711 | 28.8 | 0.149 | $3,357 | 6.1 |

Paired daily log returns, champion minus cell, on the 3,689 trading days both books are marked
(the same split S-12 was promoted on):

| switch removed | bps/day | t | ann.% | IS bps | IS t | OOS bps | OOS t |
| --- | --- | --- | --- | --- | --- | --- | --- |
| (a) no ranking | +2.20 | 1.76 | 5.71 | +1.77 | 1.27 | +2.73 | 1.24 |
| (a2) no ranking, vol-matched | +1.19 | 0.92 | 3.04 | +0.44 | 0.29 | +2.08 | 0.94 |
| (b) regime filter off | +0.65 | 0.53 | 1.66 | **-0.04** | -0.03 | +1.49 | 0.70 |
| (d) allocation tilt off | +0.26 | 0.82 | 0.65 | +0.52 | 1.45 | **-0.06** | -0.10 |
| (e) levered proxies off | +0.41 | 1.21 | 1.04 | +0.50 | 1.26 | +0.30 | 0.52 |
| (g) drawdown overlay off | **-0.51** | **-1.93** | -1.27 | +0.11 | 0.62 | **-1.25** | **-2.35** |
| (f) no skill at all | +2.35 | 1.37 | 6.09 | +1.04 | 0.56 | +3.92 | 1.30 |

### 2. What it says

- **71% of the champion's CAR is no skill of any kind.** Cell (f) - the nine ETFs held
  equal-weighted, every name unlevered, no ranking, no entry gate, no regime filter - earns
  **17.282%** through the vol target, the margin budget and the overlay alone, against the
  champion's 24.404%. The whole signal stack is worth **+7.12 CAR at t = 1.37**. The sizing
  machinery is doing the heavy lifting: the unlevered pool itself earns ~13.9%/yr (S-14's
  5.20 bps/day menu), and SPY over the same window compounds at 9.5%.
- **Nothing the loop has tuned is individually distinguishable from zero.** Not one switch
  reaches |t| = 2 on the paired daily series, and the only one that comes close is the drawdown
  overlay **with the sign against it** (-0.51 bps/day, t -1.93; OOS -1.25 at **t -2.35**).
- **The ranker is the biggest piece and a third of it is leverage, not selection.** Removing
  ranking costs 6.70 CAR, but it also drops realized vol 0.170 -> 0.137: hold 9 names instead of
  3 and the book is simply more diversified. Sized back to the champion's own volatility
  (`margin_budget` 0.93, std 0.163) the no-ranking book earns **20.745%**, so ranking is worth
  **+3.66 CAR at t = 0.92**, not +6.70. That is the same ~2 bps/day S-14 measured unlevered,
  arriving by a completely different route.
- **The regime filter is a drawdown instrument, not a return one.** +2.02 CAR at t = 0.53, and
  its in-sample contribution is **exactly zero** (-0.04 bps/day, t -0.03) - the whole of it is
  2020-2026, i.e. COVID and 2022. What it reliably buys is risk: drawdown **31.4 -> 25.1** and
  realized vol **0.189 -> 0.170**.
- **The 3x proxies buy volatility, not edge.** Held in their unlevered parents the same signal
  earns 23.128% at **Sharpe 0.950, drawdown 23.6%, std 0.153 and PSR 27.4%** - better than the
  champion on every risk-adjusted measure and on fees ($25.6k against $45.7k) - for 1.28 CAR.
  This is L-1's intraday finding on the daily sleeve: leveraged instruments supply volatility,
  and the vol target then hands most of that volatility back.
- **The last promotion is in-sample.** S-12's allocation tilt is +0.80 CAR overall, but
  **+0.52 bps/day (t 1.45) in 2012-2019 and -0.06 (t -0.10) in 2020-2026**. It was promoted on
  a full-period run that beat the champion on all three criteria; the halves say the edge is
  not there after 2020. Not a reason to demote - t is nowhere near 2 in either direction - but
  it is the honest read.

### 3. Decision

**Nothing shipped, nothing promoted, nothing refused.** `research/champion.json` is unchanged at
S-12, the control reproduces the deployed order list hash, and `live/` and the scheduled tasks
were not touched (all eight cells are environment overrides; the item owes no replay and the
intraday trader was not loaded). The sentence S-15 was asked for: **the champion is a levered
long-ETF-beta book with a volatility governor, and the four switches the research loop has spent
six iterations tuning are worth about seven CAR points between them, none of which is
individually distinguishable from zero on fourteen years of daily data.**

**What it changes.** Further ranker tuning is the lowest-value work available: its measured
contribution is +3.66 CAR at t = 0.92, and S-14 showed it does not survive dilution. The two
components with real, repeatable effects are the ones nobody has swept - the **vol target /
margin budget** (which produces 71% of the return) and the **regime filter** (which produces the
drawdown profile). Both are risk-posture parameters, so both run into the open owner questions in
`BLOCKERS.md` rather than into another backtest.

- **A-5 part 2 (standing job) had no new input**: this ran at 06:3x ET, before the open, so the
  ledger is still the single 2026-09-10 session - 32 fills, $1.87M, **+2.89 bps (se 1.33)**
  against the shipped 1.50, |diff|/se 1.05, ~6.8 sessions to settle it. `SLIPPAGE_BPS` untouched.

## 2026-09-11 - S-14: breadth, and the discovery that the champion's whole cross-sectional edge is one thin number

- **What.** The backlog closed its last open mechanism yesterday (S-2), so this iteration took
  the one direction the repository has repeatedly named and never measured: **breadth**. S-12's
  note says "what remains inside a three-name ETF book needs breadth (correlation-aware weights
  want more than nine names)" and the 2026-09-09 owner decision says volatility is to be earned
  by widening, not by leverage. The champion ranks **nine** unlevered ETFs and holds the top
  three, i.e. a third of its own universe - which is barely a selection at all.
- **Why it should have worked.** Cross-sectional momentum earns the spread between the names it
  picks and the names it passes over. With 9 candidates the top 3 is 33% of the menu; completing
  the GICS sector map (the sleeve carries only XLK/XLF/XLE) takes it to 18%, and the sectors it
  is missing are genuinely dispersed - utilities against energy can differ by forty points in a
  year. More candidates should mean a better top three.
- **Data.** Fetched the eight missing sector SPDRs and five asset-class ETFs from Yahoo through
  the shipped D-1 pipeline (XLV XLY XLP XLI XLU XLB XLRE XLC EFA HYG IEF SLV VNQ, 1998-2026, all
  validated, factor deviation 0.00000). Two of them list mid-sample (XLRE 2015-10-08, XLC
  2018-06-19) and the ranking gate in `target_weights` admits a name only once it has a full
  lookback of priced bars, so they enter on their own schedule and nothing is back-dated.
- **Three nested sleeves**, so the only thing that changes between runs is how many names the
  signal ranks: `etf9` (shipped, 9), `sector` (17), `broad` (22), added as presets in `main.py`.
  The pre-registered rule, fixed before the runs: promote only through `evaluate.py`, and only
  if the wider sleeve also wins **both** sub-periods and the two nested sleeves agree in sign.

### 1. LEAN, full period 2012-01-03..2026-09-04

| sleeve | ranked | orders | CAR | Sharpe | MaxDD | ann.std | fees | PSR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **etf9 (champion, control)** | 9 | 4,735 | **24.404%** | **0.921** | 25.1% | 0.170 | $45,695 | 23.0% |
| sector | 17 | 5,534 | 17.253% | 0.663 | 30.3% | 0.163 | $40,726 | 4.0% |
| broad | 22 | 5,629 | **11.622%** | **0.430** | 29.7% | 0.165 | $32,236 | 0.3% |
| sector, `top_n=5` | 17 | 7,696 | 19.625% | 0.826 | 21.7% | 0.147 | $41,693 | 13.9% |
| sector, `top_n=5`, budget 0.867 (vol-matched) | 17 | 8,279 | 22.879% | 0.872 | 23.6% | 0.168 | $57,670 | 17.6% |

**Monotone in the number of candidates, and monotone the wrong way**, at essentially unchanged
realized volatility (0.170 / 0.163 / 0.165). `evaluate.py` refuses all four candidates. The
control reproduces **`OrderListHash 5246804e17a67af90028ffceead7d3b3`** exactly, so the two new
constants are inert on the deployed path, and `compare_orders.py` still passes 3,689/3,689.

Sub-periods for the nearest candidate (`sector`, top_n 3) against the champion's recorded halves:
**IS 2012-2019 12.626% / 0.603 / 30.3%** against 19.18% / 0.884 / 25.1%, **OOS 2020-2026 22.929%
/ 0.739 / 20.1%** against 30.86% / 0.985 / 22.6%. It loses in both halves, so this is not a
regime artifact.

### 2. Why - the decomposition, with leverage and the vol target switched off

`scripts/sweep_s14.py` walks the same signal day by day with no drawdown overlay, no vol target,
no margin budget and no levered proxies, and splits the unlevered top-3 basket's daily return
into `selected = pool_mean + spread`: the quality of the **menu**, which the signal is not
responsible for, and the **spread**, which is the only part ranking earns.

| sleeve | selected | pool mean | spread | t | unlevered CAR | Sharpe | MaxDD | churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| etf9 | 7.21 bps/day | 5.20 | **+2.02** | **2.07** | 15.5% | 1.18 | 22.4% | 0.15 |
| sector17 | 5.73 | 4.90 | +0.82 | 0.81 | 12.0% | 0.96 | 15.7% | 0.20 |
| broad22 | 5.27 | 4.32 | +0.94 | 0.82 | 10.8% | 0.83 | 14.3% | 0.21 |

Paired on the 3,099 days both books are invested: **sector17 - etf9 = -1.37 bps/day (t -1.95)**,
**broad22 - etf9 = -1.89 (t -2.23)**. Of the -1.48 bps that separates etf9 from sector17, only
**-0.30 is the menu** and **-1.20 is the spread**: four fifths of the damage is the signal
picking worse, not the added names being worse assets. The spread falls in both halves
(etf9 1.69 / 2.43 against sector17 0.32 / 1.45).

**The finding that matters more than the verdict**: the champion's entire cross-sectional
contribution is **+2.02 bps/day at t = 2.07** over fourteen years, and it exists only at
top-3-of-9. Re-run at `top_n=5` the spreads collapse into each other and none is significant -
etf9 **+0.84 (t 1.16)**, sector17 +0.99 (1.32), broad22 +1.34 (1.59). So the champion is not a
broad momentum engine that happens to run on nine names; it is a concentrated bet whose edge is
thin, and every dilution of that concentration - more candidates, more holdings - costs it.

### 3. Two things breadth *does* buy, and what they cost

Composition (`--mode compose`): widening moves **38.4%** (sector) and **45.0%** (broad) of funded
slots into names the shipped sleeve does not have, and cuts the share of funded slots in names
that carry a 3x proxy from **32.7% to 17.6% / 15.8%** - the sleeve starts winning momentum races
with defensives (XLV 20%, XLU 17%, XLP 9%) and silver (SLV 22% in broad). **This is not why it
loses**: realized vol is unchanged across all three books, because the vol target and margin
budget lever the unlevered winners back up. The steelman confirms it - `top_n=5` on the wide
sleeve recovers 2.4 points of CAR and 8.6 points of drawdown, and **sized to the champion's own
0.17 std it still earns 22.879% at Sharpe 0.872 against 24.404% / 0.921, on 8,279 orders against
4,735 and $12k more commission.** What breadth genuinely delivers is diversification: the
unlevered basket's drawdown falls 22.4% -> 15.7% -> 14.3% and the vol-matched book's is 23.6%
against 25.1%. It buys a smoother path and pays 1.5 points of CAR and 75% more turnover for it.

### 4. Two defects fixed in the data tool on the way

- `fetch_data.py` **rewrote the whole manifest** from each run, so today's 13-symbol fetch erased
  the provenance record of the other 69. Same shape as the `alpaca_data.py --splits` landmine S-2
  fixed yesterday, and cheaper only because nothing reads this file. It now **merges** per symbol
  and prints `(n re-derived, m kept)`; the 69 lost entries were restored from git and a no-op
  re-fetch of SLV verifies the path (1 re-derived, 81 kept, 82 on disk).
- `--symbols <ONE>` **crashed**: yfinance ignores `group_by="ticker"` for a single-symbol batch
  and returns (field, ticker) MultiIndex columns, so the frame handed to `dropna` had no `Open`
  column. The ticker is now selected from whichever column level carries it. Verified: a
  one-symbol run reproduces the batch run's 5,124 SLV bars.

### 5. Decision

**Refused and closed; nothing shipped.** `research/champion.json` is unchanged at S-12, the daily
runner's order list is bit-identical (hash reproduced, deploy gate passes), and `live/` and the
scheduled tasks were not touched. The two new sleeve presets stay in the tree defaulted off
(`S1_SLEEVE=etf`), because the decomposition behind the refusal is worth being able to re-run.
**Do not re-open breadth as a "which names" question** - three nested pools, two holding counts
and a vol-matched control all point the same way, and the mechanism is measured: the ranking
spread does not survive dilution. The honest successor question is the opposite one, and it is
uncomfortable: if +2.02 bps/day at t = 2.07 is the whole cross-sectional edge, then most of the
champion's 24.4% CAR is the levered beta of a 3x proxy basket plus the regime filter, not
selection - which is worth measuring before any further work is spent on the ranker.
- **A-5 part 2 (standing job) had no new input**: this ran at 05:3x ET, before the open, so the
  ledger is still the single 2026-09-10 session - 32 fills, $1.87M, **+2.89 bps (se 1.33)**
  against the shipped 1.50, |diff|/se 1.05, ~6.8 sessions to settle it. `SLIPPAGE_BPS` untouched.

## 2026-09-11 - S-2: the index-ETF opening-range breakout, and the stop that makes both signs look profitable

- **What.** S-2 has been on the backlog since 2026-09-08 and was unblocked for SPY on 2026-09-09:
  an opening-range breakout as a **second sleeve** on SPY/QQQ/IWM, with TQQQ as the leveraged
  read. It is the last open research item in the repository that is not parked, an owner
  question, or infrastructure. The A-track already measured an ORB on sixteen single names at
  -$331/day, so the question here is narrow: the index ETFs are a **different universe** - an
  order of magnitude more liquid, a high enough share price that IBKR's per-share commission is
  near-invisible (the measured round trip here is **3.65 bps**, of which 3.0 is slippage, against
  the A-track universe's 4.70), no single-name event risk - and they are the only intraday
  instruments the daily champion could plausibly share.
- **Two stages, the cheap one first**, which is the standing lesson from L-1, X-1 and O-2:
  measure the mechanism on the whole history with nothing fitted, and build the expensive
  harness only if gross clears the cost floor. New `scripts/sweep_s2.py` is the event study;
  stage 2 is the **shipped ORB module through the deployed framework** (`intraday_backtest.py
  --strategy orb --symbols SPY QQQ IWM`), one run per regime, three ledger rows under
  `intraday/orb`. Data: SPY/QQQ/IWM fetched here from Alpaca SIP (2016-01-04..2026-09-10,
  ~1.046M bars each; the store is now 63 symbols).
- **The decision rule was fixed before the runs**: a cell passes only if the per-session net $
  series is positive at **t > 2 in at least two of the three a-priori regimes** (2016-2019 /
  2020-2023 / 2024-2026), and only if its own fade control does not also pass.

### 1. A landmine found on the way in, and fixed

`alpaca_data.py --splits` **replaced** the store's split table with only the symbols passed, and
`--symbols` defaults to the 16-name UNIVERSE while `--start` defaults to 2024-01-01. A bare
`python scripts/alpaca_data.py --splits` therefore rewrites a 60-symbol table as 16 symbols
measured over two years, and every dropped name then costs at `share_scale` 1.0 - which is the
exact defect A-10 spent an iteration fixing, worth up to 40x on the per-share commission, and it
would have been silent. `write_splits()` now **merges** into the existing file and prints how many
entries it kept against how many it re-derived. Verified: the table is 63 symbols, SPY/QQQ/IWM all
factor 1.0 (no splits in the sample, as expected for these three), and **all 60 pre-existing
factors are byte-identical** to the pre-run backup.

### 2. Stage 1: the mechanism, 2,687 sessions, nothing fitted

Opening range = the first `orb_min` minutes; a breakout is a bar whose **close** is beyond the
range and the fill is the **next bar's open** (the harness's causal convention); stop is one
range ('opp') or half a range ('mid') from the fill; otherwise the trip is closed on the last bar
of the session. One trip per session per symbol. $250,000 a trip, shipped costs.

**0 of 16 breakout cells pass, and every one of them loses money:**

| best four cells, net | trips/day | gross bps/trip | cost | net bps/trip | $/day all | t |
| --- | --- | --- | --- | --- | --- | --- |
| orb15 mid e120 | 2.94 | +2.11 | 3.65 | **-1.54** | -113 | -1.64 |
| orb60 mid e120 | 2.15 | +1.76 | 3.65 | -1.89 | -101 | -1.57 |
| orb15 opp e120 | 2.94 | +1.43 | 3.65 | -2.22 | -163 | -1.89 |
| orb30 mid e120 | 2.78 | +1.16 | 3.65 | -2.49 | -173 | -2.51 |

**The finding is why the gross looked positive.** Run the same machinery on the *fade* - the
falsification control - and it earns positive gross too, in **14 of 16 cells**. Both signs cannot
own a directional edge, so the gross splits into a part the signal owns, `(breakout - fade)/2`,
and a part both signs share, `(breakout + fade)/2`:

| | gross brk | gross fade | **directional edge** | stop convexity | cost/trip |
| --- | --- | --- | --- | --- | --- |
| orb15 mid e120 | +2.11 | +0.76 | **+0.67** | +1.43 | 3.65 |
| orb60 mid e120 | +1.76 | -0.42 | **+1.09** | +0.67 | 3.65 |
| orb5 opp e120 | +0.53 | +1.05 | **-0.26** | +0.79 | 3.65 |
| orb30 opp e390 | +0.43 | +0.97 | **-0.27** | +0.70 | 3.65 |

The shared part is **positive in all sixteen cells** (+0.33 to +1.43 bps) and it is not edge: a
stop plus a hold-to-close exit is convex in either direction, so a coin flip collects it, and it
is the reason a naive ORB study reports a "+2 bps" gross that no signal produced. **The largest
directional edge anywhere in the grid is +1.09 bps against a 3.65 bps round trip - 0.30x - and in
6 of 16 cells it is negative**, i.e. the fade beats the breakout. That is X-1's verdict on a
different instrument: the effect is real, tiny, and an order of magnitude under the cost floor.

**TQQQ, the leveraged read (8 cells): 0 of 8 pass, and the direction disappears entirely.** Cost
is **4.85 bps** a round trip, not 3.65, because the same per-share commission is charged on a much
lower share price. In the best cell the breakout earns **+$33.78/day and its own fade
+$33.79/day** - identical to the cent, so there is nothing directional left at all - and the
cell with the largest separation, `orb30 opp`, runs **+$225 / +$95 / -$396** across the three
regimes. Leverage supplies volatility here, not edge, which is exactly what L-1 measured.

### 3. Stage 2: the same thing through the shipped harness

The deployed ORB module (volume filter, midpoint stop, two entries a side, time stop, the daily
loss limit and the 15:38 flatten), `--symbols SPY QQQ IWM`, `weight` 0.12 x 3 names = **0.36x
gross on a $1M book**:

| regime | sessions | $/day | Sharpe | trades/day | costs/day | turnover/day | **implied gross/day** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2016-2019 | 1,006 | **-186** | -2.14 | 8.8 | 179 | 0.94x | -7 |
| 2020-2023 | 1,006 | **-211** | -1.67 | 8.5 | 157 | 0.88x | -54 |
| 2024-2026 | 675 | **-39** | -0.35 | 8.6 | 175 | 1.01x | +136 |
| **all** | **2,687** | **-158** | | 8.6 | 171 | | **+11** |

**0 of 3 regimes.** Backing the costs out is the cleanest statement this iteration produces:
over eleven years the index-ETF ORB generates **+$11/day of gross on a $1M book and pays $171/day
to collect it**, and the gross is negative in two of the three regimes separately. The two
instruments agree in sign and in magnitude once the different book sizes are lined up (the event
study's -$113/day at 0.75x gross scales to -$54/day at 0.36x against the harness's -$158; the
harness is the more negative because it takes 8.6 trips a day where the event study takes 3.0),
so no harness reconciliation is owed beyond this.

**Stage 1's known optimism only helps the strategy.** It closes an untouched trip at the last
minute bar, and D-2 measured the daily close diverging from that bar by up to ~1% on violent days
because the close is the auction print. Modelling the auction with a market-on-close order - the
thing backlog S-2 specifically asks for in LEAN - can only make these numbers worse, which is why
the refusal does not need the LEAN build.

### 4. Decision

**Refused and closed; nothing shipped.** No file the live trader or the daily runner loads was
touched. The only behaviour change anywhere is `alpaca_data.py --splits` merging instead of
replacing, which is a research-store fix that makes a silent cost-model regression impossible;
`live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*` and the scheduled tasks are
untouched, and the rule-(a) replay of 2026-09-08 with the exact deployed config reproduces the
sleeve to the digit: **34 trades, 368 decisions, flat at close, P&L -2,302 on 500k**. Champion
unchanged at S-12.

**Do not re-open S-2 as a range-length, stop, entry-window, symbol or resolution question** - the
grid spans the first four and the negative is on *gross*, in both signs, on 2,687 sessions and
through two independent instruments. What would be a different question, and is not on the
backlog, is a breakout with a **holding period longer than a session**; everything measured here
is about a book that must pay a round trip every day.

**On the mandate.** Daily P&L standard deviation is **$1,339-$1,954 on a $1M book at 0.36x
gross**, i.e. 0.13-0.20% of equity, or roughly 0.5% at 1x. Like L-1 (0.49%) and X-1 (0.27%) this
is two orders of magnitude short of the owner's 3-10%/day, before the sign is even considered.

**A-5 part 2 ran first, as the standing job, and had no new input**: `slippage_report.py` still
finds exactly one session with live intraday fills (2026-09-10, 32 fills, $1.87M, **+2.89 bps
notional-weighted, se 1.33** against the shipped 1.50; |diff|/se = 1.05, so `SLIPPAGE_BPS` was not
touched), because this ran at 04:3x ET, before today's open. ~6.8 more sessions settle it. Note
for whoever runs it next: it needs plain `python`, not `py -3.11` - the LEAN-side 3.11 has no
pyarrow and the script reads the parquet store.

**What is left.** With S-2 refused, the backlog holds no open research item with a stated
mechanism: A-8 is parked by A-4's power calculation, A-3 is settled by A-10, D-2b and E-2b are
infrastructure, and S-5 (the allocator) needs two sleeves with positive expected return and there
is one. Every remaining lever in this repository is an **owner decision** in `BLOCKERS.md` - the
`equity_frac` question on the intraday sleeve, `margin_budget` on the daily champion, the 35%
drawdown cap, and the dead alert channel.

## 2026-09-11 - A-11: the impossible fills are real, and they are not load-bearing

- **What.** A-5 measured that the sleeve's orders are **median 1.03%, p90 5.55%, p99 26.1% and at
  worst 199%** of the volume of the minute they fill in, on the 260-session IBKR store, and called
  it a cost-model defect rather than a lever: a fill of a fifth of a minute's volume at that
  minute's open with zero impact is not a fill. A-11 sizes the defect on ten years and asks the
  only question that matters - **what does the sleeve earn when the impossible fills are gone?**
  `scripts/sweep_a11.py` on the Alpaca SIP store (2,686 sessions, 2016-01-04..2026-09-09, the
  deployed allocation, which after A-10 is ORB alone), one backtest per (cell, calendar year) from
  a fresh $1M book, pooled into A-10's three a-priori regimes; 18 ledger rows under
  `intraday/active`. `RISK["part_cap"]` clips every order to a share of the **trailing median**
  volume of the minute it will fill in (`volume_limits()`, 20 prior sessions, strictly before the
  session, so the cap is knowable at decision time); a clipped order is *worked* over the following
  bars rather than dropped, and whatever the cap cannot work off by the close is dumped into the
  closing bar and counted.
- **Provenance, stated plainly.** The three sweeps (main grid, and the universe split in half by
  participation) ran to completion at 03:40-04:03 ET in the preceding iteration, which was cut off
  before it wrote anything. This iteration verified the outputs against the store, added the
  cost/gross decomposition and the paired liquid-vs-illiquid statistics below, ran the replay, and
  recorded the result. No sweep was re-run; nothing in the ledger was rewritten.
- **The decision rule was fixed before the runs** and cannot promote anything: A-10 measured this
  book at -$289/day and a cap can only make a losing book smaller. The outcomes that mattered were
  (a) capped materially *better* - the shipped numbers were dragged down by impossible fills;
  (b) materially *worse* - every A-track number is optimistic by that amount; (c) inside one
  standard error - the defect is real and immaterial, and the honest record is that it was measured.

### 1. The diagnostic: the defect is four times what the IBKR window showed

90,441 fills, 16 names, 2,686 sessions, each fill's size against the **actual** volume of the
minute the backtester assumed it filled in, notional-weighted:

| | p50 | p75 | p90 | p99 | max |
| --- | --- | --- | --- | --- | --- |
| A-5, 260 IBKR sessions | 1.03% | - | 5.55% | 26.1% | 199% |
| **A-11, 2,686 Alpaca sessions** | **1.46%** | **4.71%** | **18.80%** | **950%** | **38,759%** |

**24.1% of traded notional fills at more than 5% of its minute, 9.7% at more than 20%, and 4.1%
(3,651 fills) at more than 100%** - orders larger than everything that traded in the minute they
are booked at. It is one half of the universe:

| sym | notional % | median % | p90 % | p99 % | sym | notional % | median % | p90 % | p99 % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SMCI | 4.8 | **23.04** | **1733** | 4668 | NFLX | 7.0 | 1.86 | 7.23 | 26.3 |
| SOXL | 7.6 | 5.14 | 159 | 1400 | GOOGL | 7.0 | 1.58 | 6.30 | 23.1 |
| MSTR | 5.2 | 7.21 | 143 | 834 | NVDA | 7.1 | 0.50 | 5.24 | 33.9 |
| SOXS | 4.0 | 3.80 | 28.2 | 106 | TSLA | 7.2 | 0.27 | 4.33 | 23.5 |
| AVGO | 7.2 | 4.99 | 21.5 | 68.2 | MSFT | 7.1 | 0.91 | 4.25 | 13.0 |
| PLTR | 3.9 | 2.34 | 17.9 | 79.5 | META | 7.2 | 0.86 | 3.01 | 9.26 |
| COIN | 4.0 | 2.45 | 10.5 | 35.7 | AMZN | 7.1 | 0.55 | 2.02 | 6.93 |
| AMD | 6.8 | 0.86 | 9.97 | 491 | AAPL | 6.8 | 0.50 | 1.63 | 4.55 |

The store is split-adjusted on **both** price and volume - SMCI 2016-01-04 shows 4.34M adjusted
shares at an adjusted $2.39, i.e. 434k real shares at $23.88 - so the ratio is internally
consistent and these are real participations, not an adjustment artifact. That was checked against
the raw tape before any of the numbers below were believed.

### 2. The cap: removing the impossible fills costs the book nothing in gross

Paired against the uncapped control on the same 2,686 sessions, and decomposed against the cost
per day the ledger rows carry:

| cap | tr/day | $/day | t | vs off $/day | vs off t | costs/day | **implied Δgross** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| off (shipped) | 34.9 | -331 | -1.35 | | | 907 | |
| 0.10 | 95.3 | -336 | -1.39 | **-5** | -0.25 | 917 | **+5** |
| 0.05 | 137.2 | -367 | -1.52 | -36 | -1.24 | 941 | -2 |
| 0.02 | 206.8 | -430 | -1.83 | -99 | **-2.40** | 969 | -37 |

By regime the paired difference is -11 / -3 / +1 at the 0.10 cap (t -0.34 / -0.06 / +0.38) and
never reaches |t| = 2 except at 0.02 in 2016-2019. **Outcome (c), and sharply.** At the 0.10 cap
the backtester clips **213,338 orders** and refuses a cumulative **$4.78M/day** of intended
notional against $3.59M/day actually executed (the same intended position is re-clipped every
minute until it is worked off, so that flow is far larger than the book's turnover), and the book
moves by **-$5/day at t = -0.25** - of which **+$10/day is the extra commission and slippage of
slicing**. The gross is unchanged. Only at 0.02, where the sleeve is forced to 207 trades a day,
does gross itself erode ($37/day), and that is the cost of the slicing schedule, not lost alpha:
the cap also starts failing, dumping 261 fills and $2,269/day of un-workable residual into the
closing bar.

**So the fills nobody could get were not the ones making the money.** Every A-track number stands
where it is: the sleeve's negative result is not an artifact of impossible fills, and the shipped
`part_cap = 0` stays, because switching it on buys nothing and pays 3x the turnover for it.

### 3. The half of the universe whose fills are real is the half that never made money

The strongest thing in this iteration is not the cap. Running the same book on the 8 names whose
fills are executable and the 8 whose are not, as two disjoint $1M books over the same sessions:

| universe | fills > 5% of the minute | $/day, 2,684 sessions | t | Sharpe | tr/day | costs/day |
| --- | --- | --- | --- | --- | --- | --- |
| **liquid 8** (AAPL AMZN META MSFT TSLA NVDA GOOGL NFLX) | **8.8% of notional** | **-195** | **-1.89** | -0.54 | 18.1 | 385 |
| **illiquid 8** (SMCI SOXL MSTR SOXS AVGO PLTR COIN AMD) | **45.8%** | -164 | -0.83 | -0.23 | 15.1 | 553 |
| full 16 (deployed) | 24.1% | -329 | -1.34 | -0.37 | 34.9 | 907 |

The two halves are not redundant (corr of daily P&L 0.498) and the paired difference between them
is **-$31/day at t = -0.18**, i.e. indistinguishable - but the liquid half, where the median fill
is 0.89% of its minute and only 1.0% of notional exceeds 20%, is the **most significant negative
reading this sleeve has ever produced**. Restricting to the names where the backtest is believable
does not rescue it; it sharpens the loss.

And it accounts for the one piece of positive evidence the sleeve has:

| | fitted window (261 sessions, >= 2025-08-26) | t |
| --- | --- | --- |
| liquid 8 | **-$102/day** | -0.40 |
| illiquid 8 | **+$361/day** | +0.42 |
| full 16 | +$278/day | +0.29 |

**The only window in eleven years where this sleeve made money made all of it in the half of the
universe whose fills cannot be trusted** - the half where the median order is 4.12% of its minute,
p90 is 94% and 21.8% of notional exceeds a fifth of the minute's volume. That is the same finding
as A-9's holdout in another shape, and it is the last defence the sleeve had.

- **Decision. Refused and closed; nothing shipped.** `part_cap` stays 0 in the shared sizing code,
  `live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*` and the scheduled tasks were
  not touched, and the only file changed is `scripts/sweep_a11.py` (a `--label` flag so a subset
  run cannot be confused with the main one). Champion unchanged at **S-12**; the daily sleeve was
  not touched.
- **Rule (a) replay.** No file the live trader loads moved, so none was owed; run anyway against
  the deployed config - 2026-09-08, `--equity-frac 0.5` with the config's params: **34 trades, 368
  decisions, flat at close, P&L -2,302 on 500k**, identical to A-12's. (The toolchain note from
  2026-09-10 still bites: a *naive* `--replay` reads strategy defaults at `equity_frac` 1.0 and
  reports 217 trades / -10,051, which looks like a regression and is not one.)
- **A-5 part 2, the standing job: no input today.** `slippage_report.py` still finds exactly one
  session with live fills (2026-09-10, 32 fills, $1.87M): **+2.89 bps notional-weighted, se 1.33,
  against the shipped 1.50 - |diff|/se = 1.05**, not yet 2 se, so `SLIPPAGE_BPS` was not touched.
  ~6.8 more sessions settle it against A-5 part 1's 2.52 bps breakeven.
- **Next.** The A-track is now out of levers *and* out of defences: A-9 killed the entry gate, A-10
  killed the level, O-1 killed the regime conditioner, A-12 killed the re-entry filter, and A-11
  has now killed the last "the backtest was unfair to it" argument in both directions - the
  impossible fills were not helping, and the executable names lose at t = -1.89. The open owner
  question in `BLOCKERS.md` (keep `equity_frac` 0.5 to finish the slippage measurement, or retire
  the sleeve to 0.0) is the only thing left on it, and A-11 is appended there as evidence.

## 2026-09-11 - A-12: the ORB whipsaw lockout - the mechanism is real, measured, and points the other way

- **What.** The question the 2026-09-10 paper session left behind: the sleeve lost -6,779 and
  **-5,191 of it (77%) came from one pattern** - short SOXL/SOXS at 09:52 ET, stopped out into a
  rally at 10:25, long the same pair at 10:36, out into the fade at 12:35. The shipped ORB module
  permits that by construction, because `max_entries` is counted **per side**, so being stopped out
  of a short never consumes any of the long budget, and nothing in A-1..A-11 ever tested it. New
  `reentry_block` / `reentry_mode` on the ORB module (default **0 = off**, the shipped behaviour)
  and new `scripts/sweep_a12.py`; 18 ledger rows under `intraday/active`.
- **Why in two stages.** L-1's discipline: measure the mechanism where there is nothing to fit
  before pricing a parameter. Stage 1 labels the control's own round trips and fits nothing;
  stage 2 is the paired grid, one backtest per (variant, calendar year) from a fresh $1M book on
  2,686 sessions of the Alpaca SIP store, pooled into the three a-priori regimes.

### Stage 1: the premise is refuted at the root, and the sign is inverted

Every fill of the deployed control reconstructed into round trips per (symbol, session) - P&L is
the book's own cash change over the trip's fills, costs included, nothing re-priced - and each trip
labelled by what preceded it that day in that symbol:

| kind | trips | $/trip | t | win % | total $ |
| --- | --- | --- | --- | --- | --- |
| first entry of the session | 35,025 | **-25** | -2.66 | 40.2 | **-872,347** |
| `flip` (the 2026-09-10 pattern) | 4,841 | **+15** | +0.65 | 38.9 | **+70,708** |
| `same` (continuation re-entry) | 4,353 | -20 | -1.03 | 39.5 | -88,087 |
| ALL | 44,219 | -20 | -2.50 | 40.0 | -889,726 |

**The reversal re-entry is the only profitable category in the sleeve.** The loss is in first
entries - 98% of it - and a filter on re-entries cannot reach it. By regime the flip trip earns
+3 / -27 / +89 $/trip and is never the worst of the three. How long the effect lasts is the
sharpest part:

| gap since the last exit | flip n | flip $/trip | t | same n | same $/trip | t |
| --- | --- | --- | --- | --- | --- | --- |
| 0-15 min | 1,670 | **+78** | +1.72 | 1,036 | **-81** | **-1.96** |
| 15-30 | 1,368 | -26 | -0.66 | 1,456 | -14 | -0.38 |
| 30-60 | 1,333 | -12 | -0.34 | 1,412 | +13 | +0.41 |
| 60-120 | 470 | -14 | -0.25 | 449 | -7 | -0.12 |

Everything the data has to say is inside the **first fifteen minutes**, and it says the opposite of
the anecdote: a fast reversal is the sleeve's best trade and a fast continuation is its worst. So
the grid dropped the dead pre-registered lengths (30/120/999), added 15, and kept 60 as the
"inside an hour" reading of the live session.

### Stage 2: the paired grid, 2,686 sessions, and 0 of 5 cells pass

Paired daily difference against the deployed control (same sessions, same bars, only the entry
filter moves):

| cell | dtr/day | 2016-2019 d$ / t | 2020-2023 d$ / t | 2024-2026 d$ / t | ALL d$/day | t | regimes t>2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| flip 15 | -0.4 | -7 / -0.44 | -49 / -1.29 | -37 / -0.45 | **-31** | -1.17 | 0 |
| flip 60 | -2.0 | -15 / -0.42 | -43 / -0.47 | -100 / -0.73 | **-47** | -0.93 | 0 |
| any 15 | -0.5 | +10 / +0.63 | +40 / +0.63 | -65 / -0.76 | +3 | +0.08 | 0 |
| same 15 | -0.1 | +16 / +0.97 | +75 / +1.44 | +16 / +0.43 | **+38** | +1.69 | 0 |
| same 60 | -1.7 | +20 / +0.62 | -5 / -0.08 | +68 / +0.83 | +23 | +0.68 | 0 |

**Gate 1 (mechanism) fails for every cell, and the two cells with the hypothesised sign are the
two that lose.** Blocking the whipsaw reversal costs -$31 to -$47/day. The only cell with a
positive sign is `same`, which was written as the *falsification control* - and it is exactly what
stage 1 predicted, so the two instruments agree. It is not a candidate either: it was chosen after
seeing the gap table, i.e. in sample, it removes 0.1 trades/day, and it does not reach t = 2 in any
regime. **Gate 2 (deployability) fails for all five**: the book stays negative everywhere -
control **-$331/day, t -1.35**, best variant `same15` -$293/day, t -1.19, and no variant reaches
t > 2 in a single regime, let alone two.

### A free measurement: the corrected cost model, on the full sample

This control is the first full-sample re-run of the deployed sleeve since A-5 part 2 charged the US
sell-side regulatory pass-throughs. Trades/day are identical to A-10's rows to the decimal
(27.3 / 39.4 / 39.1), so the whole difference is the fee fix: **ORB alone moves from -$289/day to
-$331/day** (regimes -251 -> -287, -476 -> -522, -65 -> -112). Every A-track number quoted before
2026-09-10 noon is light by about $42/day on this configuration.

### Decision

**Refused; nothing shipped.** `live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*`
and the scheduled tasks were not touched; the parameter stays in the module defaulted off. Rule (a)
replay of 2026-09-08 against the current trader with the deployed config: **34 trades, 368
decisions, flat at close, P&L -2,302 on 500k** - identical to the post-fee-fix figure recorded on
2026-09-10, so the new code is inert on the live path. On the 261 sessions any A-track parameter
has ever seen - the window that produced every A-track false positive - the control earns +$278/day
and nothing here would have shipped from it either (`same60` +320, `flip60` +138, all t < 0.4).

**Do not re-open as a block-length, mode or symbol question.** The mechanism was measured on 44,219
round trips with nothing to fit and its sign is the reverse of the story; the grid then priced both
signs at two lengths and neither reaches the pre-registered bar. The durable lesson is the one A-9
taught in a different shape: **a single session's worst pattern is not evidence about the
population.** The day that motivated this item was a 4,841-trip category that earns +$15 a trip.

**Next.** The sleeve's loss is 98% first entries, so no re-entry rule can reach it - that is the
last signal-layer idea the 2026-09-10 session suggested, and it is closed. A-5 part 2 stays the
standing per-session job (~6-7 more sessions of fills to resolve `SLIPPAGE_BPS` against its 2.52
bps breakeven at two standard errors), and the binding constraint is unchanged: the three open
owner questions in `BLOCKERS.md`, to which this iteration adds a fourth, small one - live alerting
is dead for want of a channel the loop may not configure itself.

## Paper session 2026-09-10

Operations only, no research. Account DUT091359, NAV 989,100.58 at the 09:25 ET intraday start,
**977,119.53** at 15:50 ET (**-11,981, -1.21%** on the day across both sleeves).

| Sleeve | Trades | P&L (net) | Costs | Worst event |
|---|---|---|---|---|
| Intraday `active` (ORB, equity_frac 0.5) | 32 | **-6,778.79** | 91.97 commission | SOXL -2,782 and SOXS -2,409: a whipsaw in semis cost -5,191, 77% of the day's loss |
| Daily `s1_momo` (15:45 rebalance) | 3 | mark-to-market only; book unrealised **-14,727.12** | included in fills | TQQQ -6,999 unrealised, filled 2.20 below the 71.55 plan reference price |

**Intraday.** Started 09:25 ET, flat by 13:30 ET (ORB exits) and confirmed flat at the 15:42
`end` event: `positions: {}`, matching `live/state/intraday_book.json` (`pos: {}`). No
`loss_limit`, `halt` or `error` events. Equity curve by snapshot: -252 at 10:00, -3,925 at 10:30,
-6,336 at 13:00, -6,779 final — a one-way drift, not a single blow-up. Peak gross 818,518 at
11:30. **Step 4 not run: the book was already flat, so no `--flatten` was needed.**

**Daily rebalance, 15:45 ET.** Plan `s1_momo` as-of 2026-09-09, regime risk-on (vol 0.084 vs
median 0.127), targets XLE 0.5873 / XLK 0.4402 / TQQQ 0.2363 on net_liq 977,489.04, gross weight
1.2637, effective exposure 1.7363. Three market orders sent, all filled:

| Symbol | Action | Qty | Ref price | Fill |
|---|---|---|---|---|
| TQQQ | SELL | 473 | 71.55 | 69.35 |
| XLE | BUY | 1,456 | 65.31 | 65.09 |
| XLK | SELL | 326 | 187.87 | 185.45 |

Closing book: XLE 8,789 / XLK 2,290 / TQQQ 3,227, gross 1,220,496.93, cash -243,807.80.

**Two non-fatal defects.** (1) `notify_failed: no live/alerts.json` fired 15 times in the
intraday log and once in the daily log — alerting is silently dead and every alert today was
dropped. (2) `feed_probe: ib_delay_minutes 1045` again: IBKR is serving delayed quotes to the
paper account, so all intraday marks come from the minute-history path, not the live feed.
Also six `connect_failed` events against port 4002 between 06:19 and 06:45 ET before the gateway
came up; the 15:45 run connected fine.

**The semis whipsaw, in fills.** The sleeve trades SOXL and SOXS as one directional pair and was
stopped out twice in the same direction of error. Short semis at 09:52 ET (SOXL -520 @ 114.12,
SOXS +1,254 @ 47.29), out at 10:25 into a rally (SOXL @ 117.50, SOXS @ 46.11). It then flipped
long at 10:36 (SOXL +482 @ 118.15, SOXS -1,244 @ 45.89) and exited at 12:35 into the fade
(SOXL @ 116.02, SOXS @ 46.64). Two ORB entries, both on the wrong side of the same reversal —
this is a signal cost, not an execution defect.

**Next.** Fix `live/alerts.json` so the notifier stops swallowing alerts, and check whether the
ORB re-entry rule should be blocked after a same-symbol stop-out reverses direction inside an hour.

## 2026-09-10 - O-2: SPY 0DTE credit spreads - the first candidate with real gross, refused on the one assumption that makes it pay

- **What.** The last item on the owner's 3-10%/day list, and the only one that had never been
  measured: sell a same-day-expiry SPY vertical credit spread and price every fill at the quoted
  bid/ask. New `scripts/odte_data.py` built a 0DTE chain store from the Theta Terminal -
  **1,884 expirations, 2016-01-08 .. 2026-09-10, 5-minute bid/ask for both rights, +/-30 strikes,
  ~17.8M quote rows, 125 MB** - and new `scripts/sweep_o2.py` runs the study while
  `scripts/_o2_confirm.py` attacks the result. Sixteen ledger rows under `options/odte_put_spread`.
- **Why it needed no owner action to start.** The backlog carried O-2 as blocked on IBKR options
  permission. Permission blocks *deployment*, not research: Theta's STANDARD plan already serves
  every quote the study needs. Nothing here is deployable and nothing was deployed.

### Method, fixed before the runs

One session = one 0DTE expiration. The underlying is recovered by **put-call parity** (0DTE, so
carry is negligible) and the risk-neutral probability of finishing in the money is read off the
chain's own slope - `dP/dK` for puts, `-dC/dK` for calls - so strike selection uses no volatility
model and no external data. Short strike = the strike whose prob-ITM is closest to the target;
long strike = a fixed percentage of spot further out, snapped to the grid. **Entry sells the short
leg at the bid and buys the long leg at the ask; exit buys at the ask and sells at the bid. The mid
is a diagnostic and never a fill.** Commission $0.75 per contract per transaction. The decision
statistic is **return on risk** - P&L over the position's own maximum loss - so 2016 and 2026 are
comparable and a book that risks `risk_frac` of equity earns `risk_frac x ror`. Verdict rule, also
fixed in advance: **net positive at t > 2 in at least two of the three a-priori regimes.**

### The instrument was proved before its verdict was believed

`sweep_o2.py --audit` asks whether the chain's own slope is a calibrated probability. Over
1,749-1,890 sessions per cell, quoted against realized:

| side | quoted prob | realized breach | z |
| --- | --- | --- | --- |
| put 0.05 | 0.049 | 0.033 | -3.14 |
| put 0.10 | 0.098 | 0.080 | -2.68 |
| put 0.16 | 0.157 | 0.131 | -3.04 |
| put 0.25 | 0.247 | 0.220 | -2.72 |
| call 0.10 | 0.096 | 0.070 | -3.81 |
| call 0.16 | 0.155 | 0.125 | -3.65 |

Realized tracks quoted at every delta and on both rights - which proves the parity spot and the
slope - and sits **consistently below** it. That gap *is* the variance risk premium, measured
directly rather than assumed, and it is why this study's gross is positive where O-1, L-1 and X-1
had none.

### Stage 1: the pre-registered grid is a clean negative

36 cells (put / call / condor x 0.10 / 0.16 / 0.25 delta x 10:00 / 12:00 entry x stop 2x / none),
0.75% wide, closed at the quote at 15:50: **0 of 36 pass, every cell negative in every regime.**
The decomposition of the widest-sample cell says why - percentages are of the position's own risk,
per session:

| regime | n | gross | spread | commission | net | cover |
| --- | --- | --- | --- | --- | --- | --- |
| 2016-2019 | 480 | +0.547 | -1.732 | -1.402 | **-2.588** | 0.17 |
| 2020-2023 | 735 | +1.001 | -1.343 | -0.941 | **-1.282** | 0.44 |
| 2024-2026 | 674 | +0.713 | -1.122 | -0.639 | **-1.047** | 0.41 |
| **all** | **1,889** | **+0.783** | **-1.363** | **-0.950** | **-1.530** | **0.34** |

**The mid-price edge is a third of the cost of harvesting it**, and on a $355 risk unit the
commission alone is bigger than the entire gross. Making the trade as cheap as the data allows -
72 cells over width 0.75-5%, entry 10:00-14:00, with and without commission - the best net is
**+0.30% of risk at t = +0.94, and that is at zero commission**; with IBKR's fee the best
full-coverage cell is **-0.006%**.

### Stage 2: the exit convention is worth more than every parameter in the study

Closing a spread at the quote pays the spread twice. A real 0DTE book does not do that - it lets an
untouched position expire. Modelling exactly that (expire free only when nothing is in the money at
the bell, buy back at the quote otherwise) **flips the sign**, and the response to entry time is a
monotone shelf rather than a spike:

| entry | net % of risk | t | 2016-19 | 2020-23 | 2024-26 | win % | expired % | credit/width |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:35 | +0.090 | +0.19 | -1.099 | +0.604 | +0.379 | 80.0 | 78.0 | 0.074 |
| 11:00 | +0.437 | +1.12 | -0.808 | +1.005 | +0.703 | 80.3 | 78.7 | 0.062 |
| 12:00 | +0.685 | +2.09 | +0.349 | +0.899 | +0.691 | 80.4 | 79.4 | 0.055 |
| 13:30 | +0.851 | +3.16 | +0.514 | +0.924 | +1.008 | 82.4 | 82.1 | 0.046 |
| **14:00** | **+0.767** | **+3.05** | +0.268 | **+1.071** | **+0.786** | 82.5 | 82.4 | 0.042 |
| 14:30 | +0.907 | +4.32 | +0.125 | +1.269 | +1.064 | 82.1 | 82.6 | 0.038 |
| 15:30 | +0.684 | +5.20 | +0.311 | +0.883 | +0.721 | 83.8 | 86.0 | 0.025 |

Three of 36 exit-variant cells pass the pre-registered rule, all of them late-entry and
expire-at-the-bell; the same cells closed at the quote earn **-0.282%, t = -1.16, positive in
3 of 11 years** against the expire version's **+0.767%, t = +3.05, positive in 10 of 11 years**
(only 2018 negative). **The entire result is the exit.**

### And the exit assumption does not survive contact with settlement

SPY options settle on the official 16:00 print and can be exercised against until 17:30 ET, so a
position that is barely out of the money at the last quote is not a free expiry. Charging the
quoted spread whenever the close fails to clear the short strike by a buffer:

| buffer (of spot) | net % of risk | t | 2016-19 | 2020-23 | 2024-26 | regimes passing | expired % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.00% | +0.767 | +3.05 | +0.268 | +1.071 | +0.786 | 2 | 82.4 |
| 0.05% | +0.583 | +2.32 | +0.090 | +0.914 | +0.567 | 1 | 77.2 |
| 0.10% | +0.445 | +1.78 | -0.052 | +0.776 | +0.433 | **0** | 71.4 |
| 0.20% | +0.202 | +0.81 | -0.332 | +0.548 | +0.200 | 0 | 55.3 |
| 0.50% | -0.116 | -0.47 | -0.710 | +0.240 | -0.087 | 0 | 21.0 |

**The whole edge lives in the last few cents around the short strike at the bell.** The pin
distribution is the reason: the median session closes **0.28% of spot** from the short strike,
p25 = 0.14%, p10 = 0.06%, p5 = 0.03%, and **37.4% of sessions close within 0.2% of it**, 509 of
those 700 booked as free expiries. At **0.10% of spot - about 65 cents on today's SPY - the result
fails the pre-registered rule outright**, and 0.10% is a *generous* reading of when a desk would
stop paying to close.

### The mandate arithmetic, which refuses it a second time

Even taking the un-buffered +0.767% at face value, on ~175 0DTE sessions a year:

| equity at risk per session | mean %/day | sd %/day | worst day | 1st pct day | simple %/yr |
| --- | --- | --- | --- | --- | --- |
| 0.10 | +0.077 | 1.09 | -10.5% | -4.7% | +19.3% |
| 0.25 | +0.192 | 2.72 | -26.3% | -11.8% | +48.3% |
| 0.50 | +0.383 | 5.44 | -52.6% | -23.6% | +96.6% |
| 1.00 | +0.767 | 10.87 | **-105.2%** | -47.3% | +193.3% |

**A 3%/day book needs 3.9x equity at risk every session, and a defined-risk position posts its risk
in full as margin - so the ceiling is 1.0x and the mandate is unreachable by a factor of four.**
At 1.0x the worst session is ruin; at the 0.25x that keeps a bad day survivable the ledger row
scores CAR 21.5% at a **60.6% drawdown**, far outside the owner's 35% cap. (The worst day exceeds
100% of nominal risk because closing a breached vertical at the quote costs more than the width -
itself a real cost this study charges and most write-ups do not.)

- **Decision: refused, nothing shipped.** No file the live trader or the daily runner loads was
  touched, `live/` and the scheduled tasks were not opened, and the champion is unchanged at S-12.
  Rule (a) owes no replay: only new scripts were added.
- **Do not re-open O-2 as a delta, width, entry-time, structure or stop question.** The grid spans
  all five and the negative is decided one level above them, by the exit: at the quote the trade
  loses in 8 of 11 years, and the version that wins depends on a settlement convention this data
  cannot price. What *would* re-open it is different data - OPRA quotes through the close and a
  measured settlement print - which is an owner purchase, not a loop decision.
- **What is worth keeping.** The variance risk premium is real, calibrated and measurable
  (z = -2.7 to -3.8 across six delta-right cells), and it is the **first gross edge in this
  repository that survives crossing the bid/ask on entry**. Its size is ~0.8% of risk per session
  and the cost of harvesting it is 2.3%; the gap closes only by not paying the exit. That is a
  genuine finding about where an options sleeve could live, and a genuine reason not to fund one yet.

### A-5 part 2, the standing per-session job

First full paper session with intraday fills. **32 fills, $1,873,486 traded, 100% fill rate:
realized slippage +2.92 bps notional-weighted (se 1.32) against the shipped 1.50 - |diff|/se =
1.08, still inside two standard errors, so `SLIPPAGE_BPS` was not touched.** The direction matters:
the measurement has moved from +1.30 on yesterday's partial session to +2.92, i.e. **above A-5
part 1's 2.52 bps breakeven**, and if it holds the intraday sleeve's cost model is worse than
shipped rather than better. Power line: **215 fills, ~6.7 sessions** at this rate to resolve the
constant against breakeven at 2 se. Per-fill sd is 7.48 bps and the close-to-open gap is
-0.30 / sd 2.16, so the reference is still not what costs precision. Worst names SOXL +6.17,
COIN +8.63, MSTR +5.37 bps; PLTR is negative at -6.28.

- **Next.** The owner's 3-10%/day list is now **exhausted**: O-1, O-1b, L-1, X-1 and O-2 have each
  been measured on the full history and each refused. Nothing in this repository reaches the
  mandate, and the only edge that survives out of sample is the daily champion. The loop's
  remaining honest work is A-5 part 2 (about six more sessions settles the intraday sleeve's sign)
  and the open owner questions in `BLOCKERS.md`, one of which - the drawdown cap - is now the
  binding constraint on every candidate the mandate asks for.

## 2026-09-10 - X-1: fifty megacaps, eleven years, and an intraday cross-sectional edge worth a fourteenth of its own cost

- **What.** The last item on the owner's midday list that needs no options permission: rank the 50
  US megacaps every 30 minutes by intraday return against the basket, hold the top decile long and
  the bottom decile short, flat by 15:38. Fetched the 40 names the store lacked from Alpaca
  (**2016-01-04 .. 2026-09-10, ~1.04M regular-hours bars each**; the store is now 60 symbols, 357 MB
  -> 1.1 GB), re-derived every split factor, wrote `algorithms/intraday/xsect/signal.py` and
  `scripts/sweep_x1.py`, and judged it on A-10's three a-priori regimes.
- **Why breadth was worth one more iteration.** A-10 measured the deployed 16-name sleeve at
  -$697/day on 2,686 sessions and O-1/A-9/L-1 each refused a lever on it; the one structural
  criticism those results do not answer is that a 16-name book has no cross-section. A ranking
  strategy is also the only candidate on the owner's list that is dollar-neutral by construction,
  so it is the one whose P&L is not a disguised market bet.
- **Method: L-1's two stages, and L-1's weighting.** Stage 1 is a cost-free event study on the raw
  bars - at each rebalance minute the cross-section is demeaned, the top and bottom `k` are entered
  at the **next bar's open** (the harness's fill convention) and unwound `h` bars later at that
  bar's open, each leg scored **relative to the equal-weight basket** over the same window. The
  decision statistic is the **per-session sum** of leg returns, never the session-equal average that
  inverted L-1's verdict; both are printed. (For this study the two agree to 0.01 bps and
  `corr(legs/session, session mean gross) = +0.006, t = +0.32` - the L-1 pathology is specific to a
  strategy whose signal count varies with the tape, and a fixed-`k` ranking is not one.) Demeaning
  is exact bookkeeping rather than a choice here: with `k` longs and `k` shorts the basket term
  cancels out of the session sum identically.

### Stage 1: the effect is real, tiny, and the wrong order of magnitude

Sixteen parameter cells (lookback 15/30/60 minutes and since-the-open, hold 30/60 bars, k = 5/10),
2016-2026, **2,684 sessions and 267,000-587,000 legs per cell**:

| lookback | hold | k | legs | gross bps | t | cost bps | net bps | t net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| since open | 60 | 5 | 267,230 | **+0.36** | +2.00 | 4.70 | -4.34 | -23.9 |
| since open | 60 | 10 | 533,380 | +0.26 | +1.93 | 4.52 | -4.26 | -31.6 |
| since open | 30 | 5 | 294,060 | +0.19 | +1.96 | 4.70 | -4.51 | -45.6 |
| 30 min | 30 | 5 | 294,040 | +0.03 | +0.35 | 4.66 | -4.63 | -46.1 |
| 60 min | 60 | 10 | 479,760 | +0.14 | +1.09 | 4.51 | -4.37 | -35.0 |

**Gross is positive - momentum, not reversal - and it is 0.36 bps against a 4.70 bps round trip.**
The whole eleven-year edge is **7.7% of the cost of harvesting it**; the book would need a **13x**
larger spread to break even. Per regime the same cell is +0.35 / +0.27 / +0.51 bps (t = +1.44 /
+0.83 / +1.34): stable in sign, never significant on its own, and the pooled t of +2.00 is what
2,684 sessions buy. **No cell reaches t > 2 in two of three regimes on either sign - and that is
before costs**; net of costs the verdict is 0 of 32.

Two secondary readings, both consistent with the main one:

| entry | 10:00 | 10:30 | 11:00 | 13:00 | 14:00 | 14:30 | 15:00 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gross bps | +0.25 | **+0.63** | +0.48 | +0.35 | -0.26 | **-0.69** | -0.19 |
| t | +0.48 | +1.46 | +1.30 | +1.39 | -1.02 | **-2.80** | -0.70 |

Continuation in the morning, mean reversion in the afternoon, and the only |t| > 2 in the table is
the 14:30 **reversal** - a shape worth remembering, and still an order of magnitude under cost at
every hour. And the cost falls monotonically across the regimes (5.45 -> 4.42 -> 4.00 bps per round
trip) purely because the megacaps' share prices rose against a fixed per-share commission, which is
the only reason the net numbers improve at all.

### Stage 2: the harness agrees, and it agrees on both signs at once

`algorithms/intraday/xsect/signal.py` through the shipped framework (defaults: lookback 30, hold to
the next 30-minute re-rank, k = 5, 0.06 of equity per leg, 0.6 gross), **one year per regime**
(2018, 2022, 2025 - a full 11-year pass is ~45 minutes of wall clock per year at 50 names and buys
nothing stage 1 has not already settled):

| variant | $/day | t | Sharpe | 2016-19 | 2020-23 | 2024-26 | tr/day | costs/day |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| momentum | **-1,681** | **-16.9** | -10.2 | t -13.5 | t -9.4 | t -7.8 | 158.9 | $1,760 |
| reversal (control) | **-1,786** | **-18.8** | -11.2 | t -15.8 | t -9.1 | t -9.7 | 158.8 | $1,689 |

0/3 regimes for both signs, against the 2/3-at-t>2 rule fixed before the runs. **The two signs
losing the same amount is the whole result**: back out the modelled costs and the implied gross is
**+$79/day for momentum and -$97/day for reversal** on a $1M book - zero to within a few dollars a
day, in both directions, exactly as stage 1 said. Turnover is 8.07x equity per day, so the sleeve
pays $1,760/day for the privilege; the compounding of that bleed, not any drawdown of the signal, is
what makes the eleven-year equity curve read -80%.
- **The reconciliation is arithmetic, not luck.** Stage 1's cell for the module's own defaults
  (lookback 30, hold 30, k = 5) is +0.03 bps per leg on 109.6 legs/day, i.e. **+$20/day** at 0.06 of
  equity per leg; the harness's implied gross is +$79/day on the three sampled years. The two
  instruments are measuring the same nothing, so no audit of the harness was owed this time (L-1
  needed `_l1_reconcile.py` because they disagreed in *sign*).
- **On the mandate.** Daily P&L standard deviation is **$2,730 on $1M, 0.27% of equity**. Even
  levered to the framework's 1.5 gross cap this book moves a quarter of one percent on a typical
  day, so it was never a 3-10%/day candidate: a market-neutral ranking is the *least* volatile thing
  the owner's list contained, and its edge is smaller still.
- **Decision. X-1 is refused and closed.** Nothing shipped. `live/intraday_config.json`,
  `live/APPROVED_PAPER.md` and the scheduled tasks were not touched, and no file the live trader
  loads was edited - `algorithms/intraday/xsect/` is a new directory that only `scripts/sweep_x1.py`
  imports, so **rule (a) owes no replay** (the deployed `active` module, `base.py` and
  `intraday_common.py` are byte-identical to this morning's).
- **What did ship is data.** `data/minute_alpaca` now holds **60 symbols** (the 16-name sleeve, the
  six leveraged ETFs, and all 50 megacaps, 2016-2026, ~1.04M bars each), and `_splits.json` was
  re-derived for all 60 in one pass. That file is rewritten wholesale by `alpaca_data.py --splits`,
  so it had to be re-derived for the *union*, not the new names - **every pre-existing factor came
  back identical**, so A-10's and L-1's costed results are unaffected. The store is gitignored;
  rebuild with `python scripts/alpaca_data.py --symbols <names> --start 2016-01-01` (~4 min/symbol,
  three parallel processes stay inside Alpaca's 200 requests/minute).
- **Next.** The owner's list is now exhausted except **O-2**, which needs options permission on the
  paper account (open question in `BLOCKERS.md`), and the A-track refinements. Three of the four
  ideas that were supposed to deliver 3-10%/day have now been measured and refused on ten years of
  bars - O-1 (no forecastable regime), L-1 (no reversion in leveraged ETFs), X-1 (no cross-sectional
  spread) - and the honest summary for the owner is that **this repo has found exactly one edge that
  survives out of sample, and it is the daily champion S-12**. The next iteration should either take
  O-2 (options, which is the only untried instrument class with intrinsic convexity) or answer the
  standing question in `BLOCKERS.md` about whether the intraday sleeve should keep trading paper
  capital at all. **A-5 part 2 is still owed today**: the sleeve trades until 15:42 ET, so
  `python scripts/slippage_report.py --refresh` runs after the close, not inside this iteration.

## 2026-09-10 - L-1: leveraged ETFs do not revert intraday, and the statistic that said they did was weighted wrong

- **What.** The owner's midday mandate put L-1 at the top of the backlog: fade VWAP bands on the
  3x index ETFs, where the daily-reset construction and dealer hedging are supposed to push price
  away from fair value and back. Fetched the missing half of that universe from Alpaca
  (TQQQ, SQQQ, UPRO, SPXU: **2016-01-04 .. 2026-09-10, ~1.03-1.04M regular-hours bars each**,
  joining SOXL/SOXS), wrote `algorithms/intraday/lev_revert/signal.py` and `scripts/sweep_l1.py`,
  and judged it on the same three a-priori regimes A-10 uses.
- **Why in two stages.** Every A-track false positive came from fitting a strategy on one window
  and reading its P&L, so the mechanism is measured first with no strategy and nothing to fit:
  an **event study** on the raw bars. Whenever the deviation from session VWAP exceeds `z` of the
  name's own 14-bar ATR, buy the cheap side at the *next* bar's open - the harness's own fill
  convention - and unwind `h` bars later at that bar's open. Only a cell that clears cost earns a
  strategy run.

### The result: refused, in both instruments, in all three regimes

| | gross bps/round trip | cost bps | net bps | t (net) |
| --- | --- | --- | --- | --- |
| z >= 3, hold 5 (540,740 events) | **-0.28** | 7.32 | -7.60 | -62.1 |
| z >= 5, hold 30 (93,373) | **-1.79** | 7.14 | -8.94 | -15.5 |
| z >= 8, hold 30 (55,454) | **-1.18** | 6.83 | -8.01 | -11.6 |
| z >= 12, hold 30 (26,552) | **-1.68** | 6.46 | -8.15 | -9.7 |
| z >= 12, hold 60 (14,495) | **-3.16** | 6.47 | -9.63 | -6.1 |

**Gross is negative in all sixteen cells and for all six names**, before a cent of cost: a stretched
3x ETF drifts a little further, it does not come back. The drift is small (-0.04 to -3.30 bps) and
only reaches |t| ~ 3 at the loose thresholds, so the honest statement is that there is no
tradeable deviation in either direction - which the harness confirms by losing on the inverted
control too. **Stage 2, the module through the shipped framework, 2,686 sessions:**

| variant | $/day | t | Sharpe | 2016-19 | 2020-23 | 2024-26 | tr/day | costs/day |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fade, 6 names | **-902** | **-9.45** | -2.93 | t -7.09 | t -6.20 | t -3.42 | 17.5 | $738 |
| fade, 3 deployable names | -667 | -9.02 | -2.77 | t -6.81 | t -6.12 | t -3.25 | 10.6 | $542 |
| continuation control | -587 | -6.26 | -1.96 | t -5.93 | t -2.57 | t -3.32 | 17.6 | $787 |

0/3 regimes for every variant, against a rule of 2/3 at t > 2 fixed before the runs.

### The finding worth keeping: the aggregation chose the sign

Stage 1 originally **passed 3/3 regimes at +7.09 bps net, t = +6.56**. That number came from
averaging the events inside a session and then averaging the sessions - one vote per session. A
book does not do that: it puts the same notional on every event, so a session earns the **sum**,
not the average, and the money-weighted statistic is **-1.68 bps**. The two disagree by 15 bps and
in sign because the fade's payoff is inversely proportional to how much of it there is:

| sessions ranked by signal count (z >= 12, hold 30) | events/session | gross bps/event |
| --- | --- | --- |
| Q1 fewest | 2.4 | **+37.94** |
| Q2 | 6.9 | +16.37 |
| Q3 | 12.5 | +3.40 |
| Q4 most | 25.5 | **-10.60** |

`corr(events/session, session mean gross) = -0.340 at t = -17.5` (z >= 8: **-0.412 at t = -23.4**,
monotone in every quartile). On a quiet tape two stretches appear and both revert; on a violent
tape twenty-five appear, the book is fully deployed in all of them, and they run. **A per-event
average over sessions is not an estimate of what a strategy earns unless the strategy trades one
event per session**, and this repo now has a cell where that distinction is worth 15 bps and a
verdict. `sweep_l1.py` prints the session-equal number as a labelled diagnostic and decides on the
P&L-weighted one.
- **The harness was audited before it was believed.** When stage 1 and stage 2 disagreed in sign
  the first suspect was the backtester, so `scripts/_l1_reconcile.py` pairs the harness's own
  trade log into round trips and matches them to the event study entry by entry on 2023 Q1:
  **235 matched entries, event +1.12 bps vs harness +1.12 bps, corr 1.000, zero disagreements
  above 1 bp.** The two instruments agree per fill; only the weighting differed.
- **Cost is the second wall, and it is structural on this universe.** A round trip costs
  **6.4-8.2 bps** here against ~3.8 on the megacap sleeve, because the inverse ETFs trade at
  \$20-26 and IBKR charges per *share*: SOXS pays **13.58 bps** a round trip, SPXU 9.12, SQQQ 9.08,
  against TQQQ's 4.85 and UPRO's 4.79. A mechanism worth +/-1-3 bps cannot pay a 7 bps toll no
  matter which way it points, and the continuation control losing $587/day is that sentence
  measured.
- **Secondary observation, not the reason it loses.** In the reconciliation window 17 of 433 round
  trips exited early - the 2.5% daily loss limit or the 15:38 flatten - and those averaged **-93
  to -129 bps** against the full-length trades' -6.2. A loss limit truncates a fade at exactly the
  moment the fade is claiming to be right, so a mean-reverting sleeve would have to price that
  interaction. Irrelevant here, because gross is negative with or without them.
- **Decision. L-1 is refused and closed.** Nothing shipped. `live/intraday_config.json`,
  `live/APPROVED_PAPER.md` and the scheduled tasks were not touched; `algorithms/intraday/active/`
  is unchanged, so the live trader loads exactly the code it loaded this morning. The only shared
  file edited is `scripts/intraday_common.py`, which gains two module-level constants
  (`LEVERAGED_UNIVERSE`, `LEVERAGED_DEPLOYABLE`) and no behaviour; the 2026-09-08 replay was run
  anyway and reproduces the deployed sleeve exactly (see below). Two of the six names (TQQQ, UPRO)
  are the daily champion's own instruments, so only `LEVERAGED_DEPLOYABLE` could ever have been
  traded - the study carried all six so that "does leverage revert" was not confounded with "which
  leg was available", and the answer is the same on both sets.
- **On the mandate.** Even the passing version of this was never going to deliver 3-10% days: the
  book's daily P&L standard deviation is **0.49% of equity** at 0.9 gross on 3x ETFs, because the
  fade holds offsetting stretches for thirty minutes at a time. Leveraged instruments supply the
  *volatility*; they do not supply the *edge*, and a sleeve with no edge sized up to move 5% a day
  loses 5% a day just as often.
- **Next.** X-1, cross-sectional intraday momentum on the 50 megacaps - the last untried item on
  the owner's list that does not need options permission, and the only one whose premise (breadth,
  a market-neutral ranking) is not already refuted by an A-track measurement. Fetch the D-1 megacap
  list into `data/minute_alpaca` and judge it the same way: event study first, money-weighted, then
  the harness, three regimes, 2/3 at t > 2.

## 2026-09-10 - A-5 part 2: the first live fills say nothing about slippage and prove a missing cost

- **What.** The intraday sleeve placed real orders for the first time this morning, so A-5 part 2
  finally had an input. Ran `scripts/slippage_report.py` on the live log, read the fills against
  IBKR's own `commissionReport`, and re-baselined the harness against the 260-session store.
- **Why.** `SLIPPAGE_BPS = 1.5` is the only guessed number in the intraday harness and A-5 part 1
  showed the sleeve's sign is a property of it (breakeven 2.62-2.64 bps, P&L linear at $546/day
  per bp). Bars cannot pin it - every 1-minute spread estimator turned out to be measuring
  volatility - so only live fills can.

### The slippage measurement: not yet an answer, and now a dated one

Partial session, 19 orders / 19 fills at 12:0x ET (the sleeve trades until 15:42), $1,108,469
traded, fill rate 100%:

| | value |
| --- | --- |
| realized slippage, notional-weighted | **+1.30 bps** (se 1.65) |
| unweighted / median | +1.26 / +2.28 |
| shipped `SLIPPAGE_BPS` | +1.50 |
| \|measured - shipped\| / se | **0.12** |
| fill latency past the model | median **10 s**, worst 13 s |

**Not distinguishable, so nothing moved.** `SLIPPAGE_BPS` stays 1.5, which is what the rule
requires and what the script refuses to do by itself.

**The reference is not the problem, and the obvious model said it would be.** The store has no
bars for a session in progress, so at 11:04 all 17 fills were priced against the decision bar's
close instead of the next bar's open. The whole-store close-to-next-open gap has sd **6.20 bps**
on this symbol mix (SOXS alone 14.04), which predicts that the fallback carries 76% of the
variance and that refreshing the store would cut the sample needed from ~162 fills to ~39. **The
store caught up mid-session and refuted it directly.** Pricing the *same 17 fills* both ways:

| reference | wmean | median | per-fill sd | wse |
| --- | --- | --- | --- | --- |
| decision close (fallback) | +1.55 | -0.01 | **7.13** | 1.73 |
| next-bar open (what the backtester uses) | +1.10 | +2.28 | **7.55** | 1.83 |

The realized gap on those fills was mean -0.30 bps, sd **2.16**, and it correlates **-0.33** with
the fill error - so the fallback is very slightly *quieter*, not noisier. A population noise
estimate does not transfer to the minutes a strategy selects; the sleeve trades the liquid first
hour, not the average minute. **What is expensive is the ~10 seconds of detection latency**, and
that drift is mean-zero, so only fills buy precision: **166 fills, ~3-4 full sessions at A-5's
49 trades/day**, to resolve the shipped constant against breakeven at 2 standard errors.

### The finding that did land: the harness never charged the sell-side regulatory fees

IBKR's `commissionReport` matched `intraday_common.commission()` to **$0.004 on all twelve buys**
and undercharged **every one of the five sells**. Fitting the excess jointly on notional and share
count reproduces all five **exactly, to the cent** (residuals 0.000), which makes these posted
rates rather than estimates:

- **SEC Section 31 fee $20.60 per $1,000,000 of sell proceeds** (0.206 bps), sells only;
- **FINRA TAF $0.000198 per share**, sells only, capped $8.30.

Notional-weighted commission on the session: **0.501 bps actual against 0.434 modelled**; with the
fix, 0.501 modelled and every one of the 17 fills reproduced to rounding.

### What it costs, on the 260-session store, paired

Same parameters as A-5's control (`orb` 1.0 + `late_momo` 1.0, `per_symbol` 0.15, `gross` 1.5,
`disaster_atr` 4.0), 2025-08-26..2026-09-08:

| | trades | turnover/day | costs/day | $/day | CAR | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pre-fix (A-5's control) | 12,743 | 5.46x | $1,025 | **$610** | 15.3% | 0.689 | 14.39% |
| **with the fees charged** | 12,742 | 5.43x | **$1,078** | **$557** | **14.0%** | **0.640** | 14.67% |

**$53/day, 5.2% of the sleeve's modelled cost, 1.3 points of annualized return and 0.05 of
Sharpe.** The one-trade / 0.03x turnover difference is the cost feeding back into equity and
therefore sizing; decisions are otherwise identical. **The breakeven moves with it**: at $546/day
per bp the control's $557/day now runs out **1.02 bps above the shipped constant, so breakeven is
2.52 bps, not 2.62** - still well above 1.5, so this changes no verdict, only the target the
measurement has to reach. Scaled to the deployed half-size sleeve the fees are ~$22/day, so the
2,686-session Alpaca result moves from -$697/day to roughly -$740/day. Every one of these numbers
moves against the sleeve, which is the direction an omitted cost always moves.

- **Rule (a) replay, run twice because the trader changed under this iteration.** 2026-09-08 with
  the deployed config, against the trader as it stands after `9bb492a`: old model **P&L -2,280,
  34 trades, 368 decisions, costs 375, flat at close** - reproducing the A-10/O-1 journal to the
  digit - and new model **-2,302, 34 trades, 368 decisions, costs 397, flat at close**. Identical
  decisions and identical trades; the entire difference is the $22 of measured fees.
- **A no-op proved for free.** The old-model control reproduces A-5's recorded ledger row to every
  digit (12,743 / 15.867% / 15.343% / 0.689 / 14.390% / 49.0 / $610 / $1,025 / -28,368 / 12 / 260).
  That run went through the participation-cap code path an earlier interrupted session left
  uncommitted in `intraday_backtest.py`, so **A-11's `part_cap = 0.0` default is bit-for-bit
  inert**, as its author claimed but had not shown. It is committed here on that evidence; A-11
  itself is still unrun.
- **Decision.** Shipped the commission fix and the instrument work; refused to touch
  `SLIPPAGE_BPS`, `live/intraday_config.json`, `live/APPROVED_PAPER.md` or any scheduled task.
  `scripts/slippage_report.py` now splits the two references and never pools them, prices every
  fill under both where both exist, reports fill latency, and prints the fills-to-breakeven power
  line; `--refresh` pulls closed sessions into `data/minute` and refuses a session still trading
  (verified: it refused today at 11:09 ET).
- **Next.** Re-run `python scripts/slippage_report.py --refresh` after today's 15:42 close for the
  first complete session, and after every close after that. Note for whoever takes the next
  iteration: the owner's midday mandate (3-10%/day, priority O-1 / L-1 / X-1 / O-2) landed in the
  backlog at 11:40 ET while this was running, and it says every candidate is judged "with real
  costs" - those costs are now $53/day higher per $5.46M/day of turnover than they were this
  morning, so L-1 and X-1 should be judged against the corrected model from their first run.

## 2026-09-10 - O-1b: the implied-vol size dial is a leverage dial, and it pays 50% more turnover for it

- **What.** O-1's deferred half, on the daily champion instead of the intraday sleeve. A size
  multiplier on S-12's funded book, driven by SPY options-implied vol:
  `clip((trailing median IV / prior-day IV) ** iv_scale_power, iv_scale_min, iv_scale_max)`,
  applied to the final weights. `iv_scale_power = 0` is off and is the shipped default.
- **Why.** O-1 refused implied vol as a *gate* but measured a residual that survived every cut it
  tried: corr(SPY ATM IV, |intraday daily P&L|) = **+0.252 at t = +12.67**, positive in all three
  regimes for all three features. Implied vol forecasts how *big* a day will be and not which way.
  That is worthless on a book whose level is negative, and it is exactly what a size dial wants -
  so the only place it could pay is a book whose level is positive. S-12 is that book.
- **Plumbing.** `signals.py` gains `iv_regime_series` / `iv_size_factor` and five `Params` fields,
  `main.py` gains the matching `S1_IV_SCALE_*` overrides, and `scripts/iv_regime.py --export-csv`
  mirrors the parquet to `data/options/iv_regime.csv` because the LEAN-side Python 3.11 has no
  pyarrow. Two things kept honest by construction: the factor reads only store rows dated
  **strictly before** the last price bar, so it is causal under either harness's timestamp
  convention; and it multiplies the weights *after* the margin-budget shrink rather than folding
  into `scale`, because with a flat budget the vol target is already inert upwards (S-8) and a
  dial that can only cut is not a dial.
- **Coverage, stated rather than hidden.** The store runs 2017-01-03..2026-09-09 and the champion's
  sample starts 2012. Uncovered days get factor 1.0, i.e. they run as the champion, so the study is
  judged on the covered period **2017-04-03..2026-09-04** (the start is pushed to April so the
  60-row median window is full on day one). A full-period run would be a blend of a bit-identical
  half and the half measured below, so it can only move the verdict toward the control.

### Every cell, covered period, against its own control

| cell | orders | fees | CAR | Sharpe | MaxDD | ann.std | PSR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| control, dial off | 2,951 | $13,090 | 29.456% | 1.025 | 22.6% | 0.179 | 37.7% |
| power **+1.0** (inverse: cut when a big day is priced) | 4,991 | $19,128 | 27.692% | 0.950 | 21.1% | 0.182 | 29.5% |
| power **-0.5** (direct) | 4,550 | $17,963 | **31.376%** | **1.050** | 23.3% | 0.189 | **40.0%** |
| power **-1.0** (direct) | 4,966 | $21,937 | 31.705% | 1.025 | 24.6% | 0.198 | 36.7% |
| power **-2.0** (direct) | 4,768 | $23,702 | 29.772% | 0.939 | 25.4% | 0.204 | 27.4% |

**The inverse reading - the one the residual actually motivates - is the losing side.** Spending
less when the market prices a big day costs 1.76 points of CAR and 0.075 of Sharpe *while carrying
more vol than the control* (0.182 against 0.179), so it is worse on both axes at once. The side
that wins is the direct one: lever up when implied vol is high. That is not a risk dial, it is the
long-volatility reading A-10 found in the intraday sleeve, arriving on a book that is paid for it.

And the response in `power` is a **pure vol dial**: annualized std walks 0.179 -> 0.189 -> 0.198 ->
0.204 monotonically as the tilt strengthens, CAR peaks at -0.5/-1.0 and rolls over at -2.0, and
Sharpe peaks at -0.5 and then decays. That is the shape leverage plus compounding decay makes, not
the shape information makes.

### The benchmark that settles it: the same gross, with no IV in it

The mean factor is only **1.0198** at power -0.5, so most of the level is unchanged; the dial's
claim has to be about *timing*. Degenerating the clip (`iv_scale_min = iv_scale_max = c`) turns the
same code path into a constant gross-up with the IV timing removed:

| cell | orders | fees | CAR | Sharpe | MaxDD | ann.std | PSR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CONSTANT 1.0198 (matches the dial's mean gross) | 2,973 | $13,588 | 30.022% | 1.030 | 23.0% | 0.183 | 38.0% |
| CONSTANT 1.056 (matches the dial's realized vol) | 3,027 | $14,556 | 31.107% | 1.040 | 23.8% | **0.189** | 38.9% |
| IV dial, power -0.5 | 4,550 | $17,963 | 31.376% | 1.050 | 23.3% | **0.189** | 40.0% |

**At identical realized vol the whole of the dial's edge over a dumb constant gross-up is +0.27
points of CAR and +0.010 of Sharpe, bought with 50% more orders (4,550 vs 3,027) and 23% more
commission ($17,963 vs $14,556).** S-13 measured this harness's own path scatter on a parameter
with no mechanism at roughly +/-0.3 CAR and +/-0.01 Sharpe across neighbouring cells. The dial's
entire measured contribution is one unit of that scatter, and it is charged for.

Two thirds of the raw "gain" is not even timing: constant 1.0198 already earns +0.57 CAR over the
control for a 2% gross-up.

And the constant does not need the dial's code at all. Expressed as the knob the owner actually
sets - `margin_budget` 0.75 -> **0.792**, no IV feed, no new module - the same window gives
**3,039 orders / $14,530 / CAR 31.006% / Sharpe 1.042 / DD 22.8% / std 0.188 / PSR 39.1%**. That is
**+1.55 CAR over the shipped champion for +0.2 points of drawdown and 88 extra orders**, against the
dial's further +0.37 CAR for +0.5 points of drawdown and **1,511** extra orders. The dial is
strictly the worse way to buy the same thing.

- **Decision. Refused; nothing shipped.** `iv_scale_power` stays 0.0, the champion stays S-12, and
  `research/champion.json` is unchanged. The plumbing is kept in the tree defaulted off because it
  is the read path any future options study needs.
- **The no-op is proved, not asserted.** `signals.py` is the module the IBKR paper runner imports,
  so the shipped-defaults run was repeated on the full period: 4,735 orders, CAR 24.404%, Sharpe
  0.921, DD 25.100%, fees $45,695.46, end equity $2,467,638.72 and
  **`OrderListHash 5246804e17a67af90028ffceead7d3b3`** - bit-identical to the champion. The live
  paper path is unchanged and `live/` was not touched.
- **Do not re-open this as a feature or threshold question.** The negative is not that
  `iv_atm_1w` is the wrong field or 60 the wrong window: it is that the only thing implied vol can
  contribute to a *long-only-in-spirit* momentum book is the level of gross, and the level of gross
  is already available for free and without turnover through `margin_budget`. If the owner wants
  the extra 1.6 points of CAR that the covered period shows, the honest instrument is a one-line
  constant, not an options feed - and it is a risk-posture decision, so it goes to `BLOCKERS.md`.
- **Also this iteration: A-5 part 2 had no input.** `python scripts/slippage_report.py` at the top
  of the iteration reports no session on disk with live fills - the only intraday log with orders
  is still absent, and 2026-09-09's is the hand-started dry run. Today's 09:25 ET session (this
  iteration ran at 08:3x ET, before the open) is the first that can produce one, so the measurement
  moves to the post-close run.
- **Next.** After today's close: `scripts/slippage_report.py` for A-5 part 2, which is the only
  measurement that can still move `SLIPPAGE_BPS` and therefore the intraday sleeve's sign. The
  A-track has no untried lever left; O-2 (defined-risk 0DTE options) needs owner permissions.

## 2026-09-10 - O-1: implied vol forecasts the day this sleeve pays for, and pays nothing

- **What.** The last idea on the A-track with a measured mechanism behind it. `scripts/iv_regime.py`
  builds `data/options/iv_regime.parquet` from Theta Data's EOD greeks - **2,383 trading days,
  2017-01-03 .. 2026-09-09**, one row per day: SPY front-weekly ATM implied vol (strike-interpolated
  at the underlying, calls and puts averaged), the 25-delta put/call skew (delta-interpolated), and
  the 1w/1m term ratio. `scripts/sweep_o1.py` then asks whether that forecast separates the days
  the intraday sleeve earns on from the days it pays on, and `algorithms/intraday/orb/signal.py`
  carries the gate itself (`iv_gate` = `high` / `low` / off, default off).
- **Why.** A-10 left exactly one thing standing on a 2,686-session sample: the sleeve's daily P&L
  rides the universe's realized daily range at **corr +0.202, t = +10.70**, positive in all three
  regimes, while the *level* is negative in all three. So the question stopped being "how big" and
  became "when". A-9 had already refused the *opening* range as the handle, for a mechanical
  reason - ORB's stop is the range midpoint, so a wide opening scales the win and the loss
  together. Implied vol is the one candidate that is a **forecast** rather than a realization, and
  it is knowable before the open.
- **Method.** A day gate is all-or-nothing, so it needs no backtest per cell: the instrument is
  A-10's cached per-session P&L series (`results/a10/daily_orb.csv`, fresh $1M book each calendar
  year), partitioned by the gate state. Every cell is therefore a partition of one fixed sample,
  not a new fit. The gate value for session `d` is the **previous** trading day's EOD reading and
  its threshold is the trailing 60-day median of readings strictly before it
  (`iv_regime.load_gate`), so nothing is contemporaneous. Rule fixed before the runs (backlog O-1):
  the gated book must be positive at **t > 2 in at least two of three regimes**, or the feature is
  refused - and a feature that separates but leaves the ON side negative is still a refusal,
  because it would only shrink a losing book.

### The forecast works. The link to P&L does not exist.

| step | measure | ALL (n) | 2016-2019 | 2020-2023 | 2024-2026 |
| --- | --- | --- | --- | --- | --- |
| 1. forecast | corr(prior-day ATM IV, today's universe range) | **+0.598, t +36.4** (2,381) | +0.452 | +0.654 | +0.535 |
| 2. payoff | corr(prior-day ATM IV, today's ORB P&L) | **-0.030, t -1.46** (2,381) | +0.001 | -0.052 | +0.010 |
| 2. control | corr(*realized* range, today's ORB P&L) | **+0.260, t +13.95** (2,686) | +0.316 | +0.228 | +0.357 |

Implied vol predicts the realized range about as well as a daily forecast can - **t = +36** on
2,381 sessions, and it holds separately in every regime. The realized range predicts the P&L at
**t = +14**. And the composition of the two is **zero**. The other two features behave the same
way: `term_ratio` forecasts the range at t = +20.9 and the P&L at t = -0.77, `skew25_1w` at t =
+17.0 and t = **-2.81** - the only feature to reach |t| > 2 against P&L, with the wrong sign.

**The decomposition says why, and it is A-9's finding arriving with a real forecast.** Regressing
today's range on yesterday's IV and correlating the two parts with P&L separately:

| feature | corr(IV-forecast part of range, P&L) | corr(surprise part, P&L) |
| --- | --- | --- |
| iv_atm_1w | -0.030, t -1.46 | **+0.351, t +18.31** |
| term_ratio | -0.016, t -0.77 | **+0.292, t +14.29** |
| skew25_1w | -0.058, t -2.81 | **+0.299, t +15.31** |

and the surprise column is positive at t > 7 in **every feature x every regime**, nine of nine.
So the sleeve is not paid for volatility, it is paid for **volatility surprise** - the range the
day adds beyond what was priced in at yesterday's close. A-9 measured that shape with the opening
range and it could be dismissed as a within-session artefact of the midpoint stop. It is not:
the same shape holds against a genuinely forward-looking, market-priced forecast on ten times the
sample. What pays is, by construction, unknowable at entry.

### The gate, and the verdict

Six cells (three features x two signs), 2,190-2,381 covered sessions each:

| feature | gate | on days | on $/day | t on | off $/day | welch t(on-off) |
| --- | --- | --- | --- | --- | --- | --- |
| term_ratio | low | 1,091 | **+43** | **+0.13** | -491 | +0.97 |
| iv_atm_1w | low | 1,258 | -60 | -0.19 | -373 | +0.56 |
| skew25_1w | low | 1,212 | -142 | -0.40 | -279 | +0.25 |
| skew25_1w | high | 1,149 | -279 | -0.67 | -142 | -0.25 |
| iv_atm_1w | high | 1,104 | -373 | -0.81 | -60 | -0.56 |
| term_ratio | high | 1,080 | -491 | -1.15 | +43 | -0.97 |

**0 of 3 regimes at t > 2, for all six cells. The rule fires.** The best ON side in the whole
sweep is +$43/day at t = +0.13 - zero. The largest separation anywhere is Welch t = 2.26
(`term_ratio low`, 2016-2019, +$636/day against -$702), and it **inverts in 2024-2026** (-$632
against +$551, t = -0.88); `iv_atm_1w low` does the same, +$330/day in 2016-2019 and -$358/day in
2024-2026. That is the A-9 signature again: a lever that selects which part of the sample you are
looking at, not which trades you take.

**One thing survives, and it is not a gate.** corr(IV, |P&L|) is **+0.252 at t = +12.67** and
positive in all three regimes for all three features. Implied vol forecasts **how big the day
will be, not which way** - so it is a size scaler, not a filter. On a book whose level is negative
that is worth nothing on its own (scaling a loser by its own volatility is not an edge), but it is
the honest form of the residual signal, and it is what the deferred half of O-1 asked about for
the *daily* champion, where the level is positive.

### The gate itself works; it is the verdict that is negative

A partition of a cached series is not a backtest, so the `iv_gate` parameter was run through the
real backtester on one calendar year (`scripts/_o1_confirm_2024.py`, three ledger rows, ORB alone,
2024 = the most recent complete year and the least negative regime):

| gate | sessions | traded days | trades | $/day | Sharpe | CAR |
| --- | --- | --- | --- | --- | --- | --- |
| off | 252 | 252 | 10,131 | +524 | 0.62 | +13.20% |
| high | 252 | **118** | 4,850 | +452 | 0.62 | +11.39% |
| low | 252 | **131** | 5,164 | -23 | 0.02 | -0.57% |

The wiring does what the partition assumed: it blocks whole sessions, keeps about half of them,
118 + 131 = 249 rather than 252 because the three sessions the store does not cover **fail closed**,
and off is a no-op. **Read this table as a wiring check, not as evidence.** 2024 is a positive year
for ORB inside a regime that is -$65/day overall, and the side it favours (`high`) is the side the
full 2,381-session partition scores **worst** (-$373/day against -$60 for `low`). One year cannot
adjudicate that, which is the entire reason the verdict is taken on 2,686 sessions and three
regimes instead.

- **Decision. O-1 is refused; nothing shipped to `live/intraday_config.json`.** The gate stays in
  the tree defaulted off, together with the store builder and the sweep, so the negative is
  reproducible. Replay of 2026-09-08 with the deployed config after the ORB edit reproduces the
  A-10 replay exactly - **34 trades, 368 decisions, flat at close, P&L -2,280 on 500k of sleeve
  equity** - so the module change is a no-op for the live path (rule a).
- **`equity_frac` held at 0.5, not cut to 0.** The backlog's objective pre-committed to taking the
  sleeve to zero if O-1 failed, and the numbers alone support it. It is not being done unilaterally
  because the owner already has this exact question open in `BLOCKERS.md` as a three-way choice,
  and the loop's stated default there is (a) *keep it at 0.5 as a live execution experiment*, whose
  entire purpose - **A-5 part 2**, measuring real fill slippage against the 1.5 bps the harness
  assumes - has still never had a single live fill (checked again at the top of this iteration:
  `slippage_report.py` reports no session on disk with orders). Today at 09:25 ET is the first
  session that can produce one, and the breakeven slippage is 2.62 bps against a shipped 1.5, so
  that measurement can still move every number on this track. Cutting to zero this morning ends it
  before it starts. The `BLOCKERS.md` item is updated to say option (b) now has no candidate left.
- **What this closes.** A-10 measured the level: negative at t = -3.01 on 2,686 sessions. O-1
  measured the conditioner: there is none that is knowable at entry, because the regressor that
  pays is a surprise. Between them the A-track's mechanism is fully accounted for, and there is no
  twelfth lever worth pulling on this sleeve. Champion unchanged at S-12; the daily sleeve was not
  touched.
- **Also shipped, in the background (P-1, the broken alert path).** `intraday_common.notify()` and
  `paper_trade.notify()` now write every alert to **`live/log/alerts-<date>.jsonl`**
  (`{ts, event, source, text, delivered, error}`) *before* attempting the chat push, and the push
  is allowed to fail. The 2026-09-09 failure left only a `notify_failed` line inside that day's own
  trading log; a rejected order or a halted sleeve was effectively invisible. It is worse than the
  review found, in fact: `live/alerts.json` does not currently exist on this machine at all, so
  **both** notify paths were silent no-ops, not just the Telegram push. No credentials were
  touched - configuring the channel stays an owner item - but the failure is now recorded instead
  of swallowed, and the daily review reads one file for it. Self-tested from both modules, and
  `compare_orders.py` re-run after the `paper_trade.py` edit still passes 3,689/3,689.
- **Toolchain note that cost time here.** `py -3.11` has no `pyarrow`, so everything that touches
  the parquet stores - the intraday harness, `sweep_o1.py`, and the trader's `--replay` - must run
  on the system `python` (3.14.7). And `--replay` does **not** read `live/intraday_config.json`:
  it takes strategy defaults unless `--params` is passed and `--equity-frac` defaults to 1.0, so a
  naive replay reports 217 trades / -9,914 against the deployed 34 / -2,280 and looks like a
  regression that is not one. Both are now in `MEMORY.md`/`memory/2026-09-10.md`.
- **Next.** A-5 part 2 after today's close - the only open measurement on this track. Then O-1's
  deferred half, the *size scaler*, applied where the level is positive: the daily champion
  (carried as O-1b in the backlog).

## 2026-09-10 - A-10: with 2,686 sessions the sleeve is not unproven, it is negative

- **What.** The power test A-4 said could not be run on any reachable sample. `scripts/sweep_a10.py`
  runs the deployed mix and each sub-strategy alone on the Alpaca SIP store - the same 16 names,
  split-adjusted 1-minute bars, **2016-01-04 .. 2026-09-09, 2,686 sessions** against the IBKR
  store's 260 - as one backtest per calendar year from a fresh $1,000,000 book, then pools the
  daily series into three a-priori regimes. The yearly reset is deliberate: it makes a dollar in
  2016 comparable with a dollar in 2026, which is what a t-statistic on daily P&L needs, and it
  stops eleven years of compounding from letting the last two years own the sample.
- **Why.** A-4 measured Sharpe 0.69 at t = +0.61 and computed that ~2,120 sessions are needed to
  reject zero at two sigma. A-5 sharpened it: on the 77 sessions no A-track parameter had seen,
  gross P&L *before any slippage* was -$11/day. The Alpaca store is the first sample large enough
  to answer, and the decision rule was fixed before the runs (backlog A-10): positive at t > 2 in
  at least two of three regimes, or the size comes down.

### The cost-model bug that had to be fixed first

The Alpaca store is **split-adjusted**, which is right for features and wrong for a per-share
commission. A 2016 share of NVDA is priced at 1/40th of what it traded at, so a dollar position
buys 40x the shares that were really bought - and IBKR charges per share, capped at 1% of trade
value. The uncorrected model charged **$1,523/day of commission on 7 trades/day** in a two-name
2016 smoke test (it was pinned to the 1% cap, i.e. 100 bps a side). Worse, SOXS's cumulative
factor is 8.3e-08, so its adjusted 2016 price is in the tens of millions and the whole-share floor
silently sized every early SOXS position to **zero**.

Fixed in shared code, so the backtester and the live trader cannot drift: `alpaca_data.py --splits`
asks Alpaca for the same daily bars twice, raw and split-adjusted, and writes the ratio as
`data/minute_alpaca/_splits.json` (NVDA 40 -> 10 -> 1, TSLA 15 -> 3 -> 1, SOXS 8.3e-08 through
seven reverse splits - no split table to maintain and nothing to keep up to date by hand);
`intraday_common.share_scale()` reads it; `commission()` takes an optional scale so the per-share
term is charged on real shares while the 1% cap stays on notional; and the whole-share floor is
applied at the price that was really quoted. **The raw IBKR store has no such file, every factor
is 1.0, and the regression proves it is a no-op there**: A-5's control reproduces to the digit -
260 sessions, CAR 15.343%, Sharpe 0.689, $610/day, 12,743 fills, worst day -28,368, 12 loss-limit
days. Same 2016 smoke test after the fix: costs/day $222, not $1,523.

### The result

Deployed framework, shipped costs (1.5 bps + IBKR commission), $1M book, 2,686 sessions:

| variant | regime | sessions | $/day | t | Sharpe | CAR % | max DD % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **mix** | 2016-2019 | 1,006 | **-579** | **-2.42** | -1.18 | -15.0 | 50.0 |
| **mix** | 2020-2023 | 1,006 | **-1,127** | **-2.92** | -1.30 | -30.2 | 77.2 |
| **mix** | 2024-2026 | 674 | -231 | -0.37 | -0.24 | -9.1 | 52.5 |
| **mix** | ALL | 2,686 | **-697** | **-3.01** | -0.91 | -19.7 | 92.0 |
| orb | ALL | 2,686 | -289 | -1.17 | -0.32 | -8.6 | 67.2 |
| **fade** | ALL | 2,686 | **-468** | **-7.38** | -2.24 | -12.2 | 77.1 |
| mix | *(fitted window, >= 2025-08-26)* | 261 | +302 | +0.32 | +0.27 | +3.7 | 15.6 |

**0 of 3 regimes pass. The rule fires.** And the finding is stronger than the rule asked for: at
t = -3.01 on a sample above A-4's own 2,120-session threshold, the mix is not *unproven*, it is
**significantly negative**. The last row is the whole story - the only window in eleven years
where this sleeve makes money is the one its parameters were fitted on, and even there
**t = +0.32**. Year by year the mix is positive in 4 of 11 years and no year reaches |t| = 1.

**The late-day fade is the clearest negative the A-track has produced: -$468/day at t = -7.38**,
negative in every regime separately (-4.33 / -6.75 / -1.60) and on the fitted window too
(-$106/day). A-4 explicitly refused to drop it because on 260 IBKR sessions it scored +$65/day
marginal at t = +0.27. That sample could not see a 7-sigma effect; this one can. This is the
overfitting lesson A-9 predicted, arriving from the other direction.

**A-4's long-volatility mechanism survives, with power.** corr(daily P&L, universe mean range) is
**+0.202 at t = +10.70** over 2,686 sessions and positive in all three regimes separately
(+0.240 / +0.161 / +0.300) against A-4's +0.538 on 260. So the *variation* really is a range bet -
the level is just below zero. That keeps O-1 (options-implied regime features) alive as the one
remaining idea with a measured mechanism behind it, and kills size as a lever.

- **Shipped** (rule c, with a passed replay of 2026-09-08 first: 34 trades, 368 decisions, flat at
  close, P&L -2,280 on 500k of sleeve equity): `live/intraday_config.json` `alloc.late_momo`
  **1.0 -> 0.0**. It is refused at 7 sigma out of sample and costs nothing in sample - on the 261
  sessions any A-track parameter has seen, ORB alone earns +$322/day against the mix's +$302.
- **Held, not restored:** `equity_frac` stays at **0.5** (this morning's A-10 preliminary cut it
  from 1.0). What is left after dropping the fade is ORB alone at -$289/day, t = -1.17 - not
  proven to lose, not proven to earn. Restoring size to a book with no demonstrated edge is not
  something evidence supports, and taking it to zero would also end A-5 part 2 before it starts:
  the live slippage measurement needs the sleeve to place orders.
- **Next.** Not another size or stop lever - A-1, A-2, A-7, A-9 and now A-10 have between them
  spent the signal layer and the framework constants. The two live threads are **A-5 part 2**
  (run `scripts/slippage_report.py` after today's close, the first session that will place real
  orders) and **O-1**, whose regime gate is the only untried idea with a mechanism this study
  actually confirms. Whether the sleeve should trade paper capital at all in its current form is
  now a one-line question to the owner in `BLOCKERS.md`.

## 2026-09-10 - A-10 preliminary: the sleeve on ten years of Alpaca bars, and a size cut for today

- **What.** `scripts/alpaca_data.py` now holds split-adjusted SIP 1-minute bars for the 16-name
  universe from 2016-01-04 (~2,686 sessions each). Two runs of the deployed mix
  (`INTRADAY_DATA_DIR=data/minute_alpaca`), before the loop's split-factor commission fix
  landed, so costs are overstated on pre-split history (NVDA/AVGO/SMCI in H1 2024):
  (a) the A-6 window 2025-12-15..2026-09-09, split 2026-06-15: IS +11.5%/yr Sharpe 0.57,
  OOS +38.2%/yr Sharpe 1.33, 47-50 trades/day, 4 loss-limit days per half - same sign and
  shape as the IBKR store (+24.2/+55.3), smaller magnitude; (b) 2024-01-02..2026-09-09 (674
  sessions): -3.8%/yr, Sharpe -0.02, max drawdown 48.5%, 44 loss-limit days, best day +107k,
  worst -37k.
- **Reading.** The data source is not the story; the period is. 2024 to mid-2025 was a
  losing regime for this mix and the last nine months a winning one, consistent with A-4's
  finding that the sleeve is long the day's range. A-10 proper (three regimes, corrected
  costs, `scripts/sweep_a10.py`) is running in the loop.
- **Decision.** `live/intraday_config.json` `equity_frac` 1.0 -> 0.5 for the 2026-09-10 session
  (trade count unchanged, dollars halved, daily loss limit unchanged at 2.5% of NAV). Restore
  to 1.0 only if A-10 shows the mix positive in at least two of three regimes on the corrected
  cost model; otherwise keep 0.5 or lower and redirect the loop to regime gating (O-1 IV
  features, A-9 range gate) rather than size.
- **Next.** A-10 result; then the regime gate work.

## 2026-09-10 - A-5 (part 1): the sleeve breaks even at 2.6 bps of slippage, and it is charged 1.5

- **What.** A-5's live-fill measurement needs a paper session that actually placed orders and
  there is none yet, so this iteration did the half that does not: it priced the cost model from
  the same 260-session store the harness runs on. New `scripts/sweep_a5.py` with three phases
  (`spread`, `impact`, `breakeven`), a backtest-only `--slippage-bps` override in
  `scripts/intraday_backtest.py`, and `scripts/slippage_report.py` - the live-fill comparison
  itself, finished and self-tested, waiting on tonight's log. The control reproduces A-4 exactly:
  260 sessions, CAR 15.3%, Sharpe 0.689, $610/day, $1,025/day of costs, 12,743 fills.
- **Why.** Top open backlog item. `SLIPPAGE_BPS = 1.5` in `scripts/intraday_common.py` is the one
  number in the harness that was never measured, and it is charged on 49 trades/day - **$820/day
  of slippage plus $208 of commission against a $610/day modelled edge.** The cost model is
  bigger than the result it is judging, so its error bar is the sleeve's error bar.

### The decision number: breakeven slippage

Slippage is `|qty| * px * bps / 1e4` on every fill, so at fixed turnover P&L is linear in the
constant. Two confirming full-store runs bracket the shipped value and the line is straight to
$73/day:

| slippage | $/day | CAR % | Sharpe | costs/day |
| --- | --- | --- | --- | --- |
| 0.0 bps | **1,671** | 41.9 | 1.51 | 230 |
| **1.5 bps (shipped)** | **610** | 15.3 | 0.69 | 1,025 |
| 3.0 bps | **-231** | -5.8 | -0.11 | 1,660 |

**Breakeven is 2.64 bps from the runs, 2.62 bps analytically.** The sleeve turns over
**$5.46M/day on a $1M book - 5.5x equity a day** - so one basis point of slippage is $546/day and
the entire modelled edge is **1.1 bps wide**. Per window:

| window | sessions | notional/day | $/bp/day | $/day at 1.5 | $/day at 0 | breakeven | se in bps |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full store | 260 | $5.46M | 546 | +610 | +1,430 | **2.62 bps** | 1.84 |
| A-4 holdout | 77 | $5.34M | 534 | -813 | **-11** | **-0.02 bps** | 3.28 |
| tuning window | 183 | $5.52M | 552 | +1,209 | +2,036 | 3.69 bps | 2.22 |

**The holdout line reframes A-4.** Its breakeven is zero: on the 77 sessions no A-track parameter
ever saw, the sleeve's *gross* P&L before any slippage at all is **-$11/day**. The -$813/day A-4
reported is not a calmer regime earning less - it is a book with **no gross edge whatsoever**
paying $802/day of modelled costs. A-4's long-volatility explanation still holds for the
variation, but the level on unseen data is zero before costs.

### Bounding the constant from the bars: an upper bound, and why it is only that

Roll (1984) and Corwin-Schultz (2012) on 1-minute bars, per name, notional-weighted by what the
sleeve actually trades: **half-spread 2.65 bps**, unweighted mean 2.40, median 1.67. Taken at
face value that sits exactly on the 2.62 bps breakeven. It should **not** be taken at face value:
`corr(CS estimate, 1-minute return std) = +0.906` across the 16 names and the CS/vol ratio is
0.32-0.65 with a median of 0.34, i.e. the estimator is a rescaled volatility, not a spread - the
extreme is SOXS at 21.7 bps "spread" on 33 bps of per-minute vol. The hard lower bound, half of
one tick notional-weighted, is **0.36 bps**. So the honest statement is
**half-spread ∈ [0.36, 2.65] bps, breakeven 2.62 bps**: the constant cannot be shown wrong from
bars alone, and no estimator on this data will settle it. Only fills will.

### What the bars *can* prove is wrong: participation

Every fill's size against the volume of the minute it fills in, over 12,743 fills:

| | median | p75 | p90 | p99 | max |
| --- | --- | --- | --- | --- | --- |
| share of the fill minute's volume | 1.03% | 2.43% | 5.55% | **26.1%** | **199%** |

Notional-weighted mean 2.69%; mean fill $111.5k. The tail is concentrated and it is not random:
**SMCI (median 5.5%, p90 17.3%), SOXS (2.8% / 18.7%), COIN (3.1% / 10.6%) and MSTR (2.2% / 6.1%)
carry 30% of the sleeve's traded notional** while the megacaps sit at 0.2-0.9%. A fill of 199% of
a minute's volume at that minute's open, with zero impact, does not exist. This is a modelling
defect rather than a lever, so removing it is not a lever hunt and A-4's power argument does not
apply to it - it is the successor item **A-10**.

One thing the harness is *not* missing: the delay from deciding on bar t's close to filling at
bar t+1's open is **-0.12 bps notional-weighted (se 0.04)** - a hair in the sleeve's favour, not
a hidden cost. So the whole modelled cost of a fill is 1.50 slippage + 0.38 commission = **1.76
bps all-in**, and there is no cushion in the fill convention.

### The live half, ready and idle

`scripts/slippage_report.py` prices every live fill against the same next-bar open the backtester
uses, signed so positive means the fill cost more than the backtest assumed, and reports the
notional-weighted mean, its standard error, per-symbol and per-side breakdowns, fill rate and
latency, pooled across sessions. It **self-tests**: injected +2.75 bps on synthetic two-sided
fills is recovered as +2.75, and a buy filled below the reference reads negative. It refuses to
write the constant. Its input needs three small additions to the trader's logging, all made and
verified: `order` now carries the decision bar `t`, `fill` carries the IB order id and the
exchange's own `filled_at`, and `decision` carries the price the strategy saw (`ref`). Because
that touches `Trader.step` and `LiveExecutor`, a replay was run per AGENTS.md rule (a):
**2026-09-08 with the deployed params, 46 trades, flat at close, identical to the A-9 replay**,
and the log now carries `ref` on every decision that ordered.

Why there is no measurement yet: the only live log on disk, 2026-09-09, is a `--dry-run` started
by hand at 11:08 ET that stopped at 11:15, so it has 10 live decisions and zero orders. The
scheduled task is Ready with next run today 09:25 ET and no `--dry-run` in its arguments, and
`live/APPROVED_PAPER.md` exists, so tonight is the first session with fills.

- **Decision. Nothing shipped.** `SLIPPAGE_BPS` stays 1.5, `live/intraday_config.json` is
  untouched, no framework constant moved. The measurement that A-5 asks for does not exist yet
  and the bars cannot substitute for it; moving a constant that sets the sleeve's sign on an
  estimator that is provably measuring volatility would be worse than leaving it.
- **Next.** Run `python scripts/slippage_report.py` after tonight's close, every session, and
  accumulate - the pooled mean and its standard error are the deliverable, not one day. Then
  **A-10**: cap order size at a share of the fill minute's median volume and re-run the mix on
  both halves, because ~30% of the sleeve's notional is traded at a participation rate its cost
  model cannot support.

## 2026-09-10 - A-9: the day's range pays, but only the half of it that is unknowable at entry

- **What.** Added `range_atr_min` / `range_atr_max` to `algorithms/intraday/orb/signal.py` (both
  default 0 = off) gating the breakout on the opening range's width divided by ATR14 at the
  moment the range closes, and `scripts/sweep_a9.py`: an attribution phase (one ORB run, P&L
  attributed to each traded symbol-session, bucketed by width) and two grids (11 cells on the
  ORB module, 4 in the deployed mix), all on the 260-session store split at A-4's 2025-12-15
  holdout boundary.
- **Why.** Top open backlog item, and the only lever left with a measured mechanism behind it:
  A-4 found daily P&L correlating **+0.538 (t = +10.25, n = 260)** with the universe's same-day
  range, and ORB gates on volume alone. The opening range closes before the first entry, so its
  width is causal - the one piece of "today is a wide day" available in time to act on.

### The mechanism is real, and it is entirely in the part you cannot see

Decomposing each session's mean range across the universe into the opening 15 minutes and the
residual after regressing that out:

| predictor of ORB's daily P&L | all 260 | holdout 77 | tuning 183 |
| --- | --- | --- | --- |
| realized full-day range | **+0.568 (t +11.09)** | +0.622 (t +6.87) | +0.560 (t +9.10) |
| opening range (known at entry) | **+0.080 (t +1.28)** | **-0.009 (t -0.07)** | +0.101 (t +1.37) |
| residual (not known at entry) | **+0.665 (t +14.29)** | +0.725 (t +9.12) | +0.645 (t +11.37) |

A-4's correlation reproduces on the ORB module alone and is stable in both halves, so it is not
a fitting artifact. But the opening range - which is itself a decent proxy for the day's range,
**corr +0.626** - carries essentially none of the payoff, and none at all in the holdout. The
reason is mechanical: ORB's stop is the range midpoint, so the width *is* the risk unit. A wide
opening scales the win and the loss together and nets out; what pays is the range the day adds
**after** entry, which is unknowable by construction. **A-9's premise is refused at the root.**

Attribution agrees, on 3,731 traded symbol-sessions: corr(P&L, width/ATR14) = +0.029 (t +1.80),
and after demeaning within symbol it is +0.036 (t +2.19) - which splits into **TUNE +0.052
(t +2.65) and HOLDOUT -0.022 (t -0.73)**.

### The grid, which is the sharpest overfitting demonstration in the A-track so far

ORB module, deployed sub-params, both halves (control reproduces A-4's `orb` rows to the digit):

| cell | HOLD CAR / Sharpe / $day | TUNE CAR / Sharpe / $day | tr/day | paired t vs control |
| --- | --- | --- | --- | --- |
| control (no gate) | -2.0 / 0.05 / -80 | 25.8 / 1.02 / +990 | 36 | - |
| min 3.2 | -8.2 / -0.31 / -335 | 26.7 / 1.17 / +1,025 | 31 | -0.14 |
| **min 3.6** | **-20.5 / -1.19 / -878** | **49.7 / 2.17 / +1,861** | 26 | +0.75 |
| min 4.0 | -20.2 / -1.45 / -863 | 41.9 / 2.19 / +1,581 | 20 | +0.29 |
| min 4.4 | -3.3 / -0.21 / -131 | 40.8 / **2.43** / +1,542 | 15 | +0.52 |
| min 5.0 | +0.9 / 0.14 / +35 | 22.6 / 1.83 / +873 | 9 | -0.06 |
| max 4.4 | +0.6 / 0.12 / +24 | -9.4 / -0.49 / -377 | 22 | -1.52 |
| **max 3.6** | **+21.6 / 1.46 / +801** | **-13.9 / -1.27 / -561** | 11 | -1.02 |

**Every "keep the wide openings" cell beats the control in the tuning window and loses in the
holdout; every "keep the narrow openings" cell does the exact opposite.** The lever does not
select trades, it selects *which half of the sample you are looking at*. `min 3.6` nearly
doubles the tuning window's Sharpe to 2.17 - the best number this sleeve has ever produced -
while turning the holdout into -20.5% CAR at Sharpe -1.19. Its mirror, `max 3.6`, earns Sharpe
1.46 on the holdout and -1.27 on the tuning window. Paired against the control over all 260
sessions, **not one of the eleven cells reaches |t| = 1.6.**

In the deployed mix the pattern is identical and larger: `min 3.6` gives HOLD -31.8 / -1.96 /
-$1,432 against TUNE 58.6 / **2.32** / +$2,174 (paired t +0.92); `min 4.4` gives -16.3 / -1.27
against 49.5 / **2.53** (t +0.62); `max 3.6` gives +5.4 / 0.48 against -7.2 / -0.60 (t -1.02).
The mix control reproduces A-4 exactly (-19.1 / -0.73 / -$813 and 33.8 / 1.27 / +$1,289).

The wide-range names the backlog asked about separately (SOXL/SOXS/SMCI/MSTR) carry most of the
in-sample effect - split at the median width their mean symbol-session P&L is -158 vs +733
(SOXL), -23 vs +580 (SOXS), -176 vs +491 (MSTR), +74 vs +296 (SMCI) - and their width quintiles
are non-monotone (-12, -233, +30, +725, +256), i.e. the effect is one bucket in four names.

### Decision

**Refused. Nothing shipped.** `live/intraday_config.json` is untouched, `range_atr_min` and
`range_atr_max` stay at 0, and no framework constant moved. The gate has no OOS improvement, so
rule (c) forbids it; and had it been judged on the 183-session window every prior A-track
iteration used, `min 3.6` would have looked like the best result in the sleeve's history and
would have shipped. **That is the holdout earning its keep, and it is the reusable lesson.**

The signal edit is behaviour-preserving with the gates off - the control rows match A-4 to the
digit in both the module and the mix - and the ORB module is loaded by the live trader, so a
**replay of 2026-09-08 was run anyway: 46 trades, flat at close, P&L -4,881 on 368 decisions**,
identical to the replay recorded in the config when A-2 shipped.

- **Next.** A-9 was the last A-track item with a stated mechanism. A-8 (the entry window) is now
  the only open lever and A-4 already said to park it: it would produce the same table of
  statistically identical cells this one did. The binding constraint has not moved - the sleeve
  needs ~2,120 sessions to prove itself and has 260 - so the honest next step is **not another
  gate**. It is A-5: replace estimated slippage with slippage measured from the live log, which
  is the one number in the harness that is currently a guess rather than a measurement, and the
  paper account starts generating it today. Champion unchanged at S-12; the daily sleeve was not
  touched.

## 2026-09-09 - A-4: twelve months of sessions, and the sleeve's return is not distinguishable from zero

- **What.** `scripts/intraday_data.py --months 12` extended the minute store from 183 sessions
  (2025-12-15..2026-09-08, the window every A-track parameter was chosen on) to **260**
  (2025-08-26..2026-09-08, plus today's partial). The 77 sessions before 2025-12-15 are a
  genuine **holdout**: no allocation, stop, filter or constant in this sleeve has ever seen
  them. New `scripts/sweep_a4.py` runs the deployed mix and its two modules over both halves in
  a process pool; the headline is a single 260-session run of the deployed config.
- **Why.** Top open backlog item, and it was put there by A-7's own arithmetic: on 183 sessions
  one standard error on the sleeve's total P&L was $229.6k against a $221.2k total, so A-1, A-2
  and A-7 had all been judged with an instrument that cannot resolve the thing being judged.

### The data first: a truncation bug, found and fixed

`intraday_data.py` requested each month window ending at the **wall-clock time of the run**.
IBKR truncates the session `endDateTime` lands in, so the newest session of every window was
stored as a partial day - a 139-bar session that every strategy then treated as a full one and
booked a session P&L on two hours of tape. Fixed by snapping every request end to 20:00 ET on
its own day (`snap_after_close`), so a window boundary can now only ever fall *between*
sessions; added `--repair`, which re-fetches only the months holding a short session, and
`truncated_sessions()`, which `--status` now flags. The store is clean: **all 16 symbols hold
261 sessions, 101k bars each, with exactly two 210-bar days (2025-11-28 and 2025-12-24, real
NYSE half days) and one partial (today, still open).** Re-running A-7's control on the repaired
bars moves it by about a tenth of a point (IS 24.211/1.007 -> 24.322/1.010, OOS 55.328/1.731 ->
56.444/1.757, ledger `20260910T015251Z`), so **every
prior A-track conclusion stands on the repaired data**; the bug mattered for the fetch, not for
the record.

### The holdout

| cell | HOLD 77 sess: CAR / Sharpe / $day / worst | TUNE 183 sess: CAR / Sharpe / $day / worst | 260-sess total |
| --- | --- | --- | --- |
| **deployed mix (orb + late fade)** | **-19.1 / -0.73 / -813 / -28.2k** | **33.8 / 1.27 / +1,289 / -30.3k** | **$173,229** |
| orb only | -5.2 / -0.08 / -209 / -29.0k | 24.5 / 1.00 / +943 / -30.7k | $156,437 |
| late fade only | -13.5 / -2.46 / -563 / -15.8k | 6.2 / 1.09 / +243 / -19.1k | **$1,099** |

- **The deployed sleeve loses money on the sessions it was not tuned on.** -$813/day over 77
  sessions, against +$1,289/day over the 183 it was fitted to.
- **And that difference is not measurable either.** Welch t on daily P&L, holdout against
  tuning: mix **-0.96**, orb -0.51, late fade -1.65. The holdout's own mean is **-0.46**
  standard errors from zero. So the honest statement is not "the sleeve broke", it is *"the
  sleeve has never been measured"*.
- **The headline, a single 260-session run of the deployed config: net +15.87% on the $1M
  sleeve, CAR 15.3%, Sharpe 0.69, $610/day at std $16,222, t = +0.61.** A 95% interval on the
  year's total P&L is **[-$354k, +$671k]** around a point estimate of $158.6k. 12,743 trades
  (49.0/day, turnover 5.46x equity/day), costs $1,025/day, 45% winning days, worst day
  -$28,368, 12 loss-limit halts, max drawdown 14.4%. (The two half-runs summed give $173.2k
  rather than $158.6k because each half restarts at $1M; the single run is the honest figure.)
- **The late-day fade contributes nothing over a year.** Standalone it made **$1,099 across 260
  sessions** - four dollars a day, on 11.8 trades/day costing $232/day, i.e. its gross edge is
  spent entirely on its own turnover. Its marginal contribution *inside* the mix is +$65/day
  (t = +0.27), split -$604/day on the holdout and +$346/day on the tuning window. A-6 shipped it
  on the strength of the tuning window alone.

### The power calculation, which is the real result

At the measured Sharpe of 0.69, the sessions needed to reject "this sleeve earns zero" at two
standard errors are `(2/0.69)^2` years = **~8.4 years, about 2,120 sessions**. The store holds
260. **No achievable backtest sample can validate this sleeve at this effect size**, and it
follows that no A-track experiment run on this harness - A-1, A-2, A-7 and every cell in them,
all of which sought differences *smaller* than the base rate - was ever capable of returning an
answer. Doubling the universe with equally good uncorrelated signals buys sqrt(2) of Sharpe and
still needs four years. The lever hunt is finished not because the levers are spent but because
the measuring instrument does not exist.

### What does have a mechanism, and one unspent lever

Regressing daily sleeve P&L on the universe's mean daily range, 260 observations:

| instrument | corr | t | fitted $/day at 3.78% range (holdout mean) | at 4.44% (tuning mean) |
| --- | --- | --- | --- | --- |
| same-day range | **+0.538** | **+10.25** | -$2,613 | +$2,011 |
| prior-day range (causal) | +0.029 | +0.47 | +$514 | +$768 |

- **The sleeve is a long-volatility position, and that is measurable at t = +10.** ORB's payoff
  scales with the day's range while its cost floor does not, so it wins on wide days and bleeds
  on calm ones. The holdout is the calmer window by a wide margin - mean daily range 3.78% vs
  4.44%, mean absolute daily move 2.36% vs 2.96%, on comparable dollar volume - so the negative
  holdout is a **regime**, not a decayed signal. That is worth more than the holdout sign itself.
- **Yesterday's range does not predict today's** (t = +0.47), so a day-ahead volatility gate is
  not available. Split into terciles on the causal proxy the pattern is still suggestive - calm
  -$341/day, mid -$332/day, wild +$2,772/day, with the wild third carrying $238k against -$58k
  from the other two - but at |t| ~ 1 that is the same unmeasurable scatter as everything else.
- **The unspent lever is same-day and causal**: ORB enters after the 15-minute opening range, so
  the **width of that range relative to trailing ATR14 is known at entry**. ORB currently gates
  on volume (`vol_ratio_min = 1.2`) and never on range width. That is the one instrument that
  attacks the +0.54 correlation without look-ahead, and it is filed as **A-9**.

### Decision

- **Nothing shipped. `live/intraday_config.json` is untouched and the trader is byte-identical,
  so no replay was owed.** Dropping the late-day fade is the tempting move - it improves the
  holdout half from -$813 to -$209/day - but it *costs* $16.8k over the full 260 sessions at
  t = +0.27, so it fails AGENTS.md rule (c) on its face: there is no OOS improvement, only a
  different slice of the same noise. Changing a deployed book eleven hours before it trades on
  a coin flip would be the worst of both.
- **Shipped instead:** the extended and repaired 12-month store, the `snap_after_close` /
  `--repair` / `truncated_sessions` fix in `intraday_data.py`, and `scripts/sweep_a4.py`.
- **The finding goes to the owner** as a one-line question in `BLOCKERS.md`: the intraday
  sleeve's twelve-month backtest cannot distinguish its return from zero, and at this Sharpe no
  backtest ever will, so it can only be judged live on paper or shrunk.
- **A-4 is done and closed. A-9 is the new top item** - the opening-range-width gate, the only
  lever with a measured mechanism behind it rather than a table of indistinguishable cells.
  A-8 (the ORB entry window) stays parked for the reason A-7 gave and A-4 has now quantified.

## 2026-09-09 - A-7: the framework risk limits are a tail dial with no price. Nothing shipped

- **What.** The three shared constants in `scripts/intraday_common.py` that A-2 pointed at -
  `DAILY_LOSS_LIMIT`, `PER_SYMBOL_HARD_CAP` and the sleeve `gross` - swept on the deployed mix
  (ORB with the 4x ATR backstop + late-day fade) over the usual window 2025-12-15..2026-09-08,
  split 2026-06-15, 124 IS / 59 OOS sessions. Fifteen cells, 30 half-runs.
  `scripts/intraday_backtest.py` grew a `--risk` override that applies **to the backtest only**
  (`RISK` dict, defaults are exactly the shipped constants), so nothing under `scripts/` that
  the live trader executes changed and no replay was owed. `scripts/sweep_a7.py` runs the grid
  in a process pool, loading bars and causal features once per worker. The control reproduces
  A-1's mix run to the digit: IS 24.211% / 1.007, OOS 55.328% / 1.731.
- **Why.** Top open backlog item. A-2 measured that every *signal*-level control leaves the
  loss-limit days where they are unless it is tight enough to destroy the in-sample return, so
  the framework constants were the last untested surface on this sleeve.

### The daily loss limit (deployed 2.5%)

| limit | IS CAR / Sharpe | OOS CAR / Sharpe | halts (183 sess) | worst day | total P&L |
| --- | --- | --- | --- | --- | --- |
| 1.5% | 17.6 / 0.79 | 88.6 / 2.57 | 40 (21.9%) | -20,470 | 243,052 |
| 2.0% | 18.9 / 0.83 | 57.0 / 1.78 | 18 (9.8%) | -25,816 | 200,528 |
| **2.5% (shipped)** | **24.2 / 1.01** | **55.3 / 1.73** | **8 (4.4%)** | **-30,284** | **221,188** |
| 3.0% | 26.1 / 1.07 | 62.0 / 1.90 | 3 (1.6%) | -37,170 | 240,724 |
| 3.5% | 23.5 / 0.98 | 61.7 / 1.89 | 2 (1.1%) | -42,463 | 228,649 |
| off | 20.4 / 0.86 | 61.7 / 1.89 | 0 | -57,009 | 214,740 |

- **The tail response is monotone and mechanical; the return response is scatter.** The worst
  day walks -20.5k -> -25.8k -> -30.3k -> -37.2k -> -42.5k -> -57.0k across the range, i.e. the
  limit does exactly the one job it was written to do. Return does not walk with it at all:
  total P&L is 200.5k at 2.0% and 243.1k at 1.5%, with the shipped 2.5% in between and 3.0%
  near the top. **Nothing here is measurable.** Paired against the control on the same 183
  daily returns, every cell in the whole sweep scores |t| <= 1.06 (limit 3.0% t=+0.80,
  limit 1.5% t=+0.39, limit 2.0% t=-0.62, off t=-0.16); the control's own daily P&L std is
  $16,974, so one standard error on the 183-session total is $229.6k against a total of
  $221.2k. The sample cannot distinguish any of these cells from any other.
- **A-7's stated worry is refused: stopping early is free.** On the sessions each cell halted,
  compared with the limit-off run on those same dates: at 1.5% (40 halts) the halted book
  ended -1.57% against -1.63% for the same days run to the close, i.e. halting *saved* $453 per
  halt; at 2.5% it saved $1,053 per halt; at 3.0% $8,497 and at 3.5% $6,265. Only the 2.0% cell
  shows a cost, $697 per halt. So a day that has lost 1.5-2.5% by lunchtime is not a day that
  keeps falling, and it is not a day with edge left either - the remainder is a coin flip worth
  approximately zero, at every limit tested, even one that fires on a fifth of all sessions.
- **The limit overshoots its nominal level by 0.15-0.38 points of NAV** (2.5% delivers a -2.65%
  worst day, 1.5% delivers -1.88%), because the breach is detected on a marked-to-close bar and
  the flatten then pays spread. To bound the worst day at X, set the limit near X - 0.3.

### The per-symbol cap (deployed 0.15 in config, 0.20 as the framework backstop)

| cap | IS CAR / Sharpe | OOS CAR / Sharpe | total P&L |
| --- | --- | --- | --- |
| 0.06 | 10.4 / 0.82 | 32.4 / 2.06 | 117,581 |
| 0.08 | 15.7 / 0.94 | 45.0 / 2.07 | 165,105 |
| 0.10 | 22.9 / 1.09 | 57.4 / 2.04 | 218,702 |
| 0.12 / 0.15 / 0.20 / 0.25 | 24.2 / 1.01 | 55.3 / 1.73 | 221,188 |

- **The framework's `PER_SYMBOL_HARD_CAP = 0.20` has never bound, and neither has the config's
  0.15.** Cells at 0.12, 0.15, 0.20 and 0.25 are bit-identical - zero dollars of difference over
  183 sessions - so the deployed mix never asks for more than ~0.12 of equity in one name.
  Below 0.12 the cap stops being a risk control and becomes a **size dial**: it removes P&L
  roughly in proportion to the size it removes (221k -> 219k -> 165k -> 118k).
- **0.10 is a spike, not a shelf, and was refused.** It is the only cell that beats the control
  on IS Sharpe (1.09 vs 1.01) and it improves OOS Sharpe (2.04 vs 1.73) and drawdown in both
  halves, for a $2.5k P&L wash (t = -0.21). But its neighbours disagree: 0.08 loses on IS Sharpe
  (0.94) and 0.12 is the control. OOS Sharpe is flat at 2.04-2.07 from 0.06 to 0.10, which is
  the signature of a size dial against a fixed cost floor, not of a lever finding better risk.
- **Gross is monotone in the in-sample half and saturates at the deployed 1.5**: 1.00 gives
  17.9 / 0.96 IS and 54.1 / 2.02 OOS on 190.9k, 1.25 gives 20.5 / 0.93 and 58.9 / 1.90 on
  210.7k, the deployed 1.5 gives 24.2 / 1.01 and 55.3 / 1.73 on 221.2k, and 2.0 gives
  24.7 / 1.01 and 57.6 / 1.76 on 227.3k (t = +0.56). OOS Sharpe falls monotonically as gross
  rises, which is what leverage does. Gross 2.0 buys +2.7% of P&L for a step outside A-3's
  stated 1.0-1.5x target and outside the `GROSS_HARD_CAP = 1.6` rationale (it would put the two
  sleeves at ~3.2x against day-trading buying power), so it is a risk-posture decision for the
  owner, not an experiment result. Refused.
- **Decision. Nothing shipped.** `DAILY_LOSS_LIMIT` stays 0.025, `PER_SYMBOL_HARD_CAP` stays
  0.20, `GROSS_HARD_CAP` stays 1.6, and `live/intraday_config.json` was not touched, so the
  live trader is byte-identical and no replay was required. The finding is that this family of
  levers has **no measurable price and one real product**: a monotone bound on the worst day.
  That makes the limit a pure risk-posture dial, and risk posture belongs to the owner - the
  priced menu (1.5% caps the worst day near -2.0% of NAV and halts a fifth of sessions; the
  shipped 2.5% caps it near -2.7% and halts 4%; off leaves -5.0%) is now a one-line question in
  `BLOCKERS.md`.
- **What this closes.** With A-1, A-2 and A-7 all negative, both the signal layer and the risk
  layer of this sleeve are measured and spent at the current sample size. Every remaining
  difference is smaller than one standard error of 183 sessions, which is the real constraint:
  **the sleeve needs more sessions, not more levers.** That makes A-4 (extend the minute store
  to 12 months) the highest-value item, ahead of A-8's entry-window sweep, since A-8 would be
  judged with the same instrument that just failed to resolve a 20% swing in total P&L.
- **Next.** A-4, then A-8 on the longer sample.

## 2026-09-09 - A-1: the VWAP fade is repairable but not additive. Retired from the mix, alloc stays 0

- **What.** Eleven variants of `algorithms/intraday/vwap_trend/signal.py` plus six sleeve-level
  runs, fixed window 2025-12-15..2026-09-08, split 2026-06-15, 124 IS / 59 OOS sessions.
  The module was given the five levers A-1 named, every one defaulted to the shipped
  behaviour: `min_hold`, `skip_from`/`skip_to` (a midday blackout), `trend_align`/`trend_min`
  (a session-trend filter), `atr_expand_min` (a range-expansion gate on the session-so-far
  mean ATR14, accumulated causally) and `agg` (a coarser decision cadence). The refactor is
  exact - the control run reproduces the A-6 fade to the digit, IS -56.040% / OOS -10.132%.
- **Why.** Top backlog item. The fade is the sleeve's only turnover engine at ~98 trades/day
  and A-6 set its alloc to 0 because it loses -56%/yr in-sample. A-1's own exit criterion:
  make it positive in both halves after costs, or delete the alloc entry and close it.

### Standalone (annualized after costs, IS -> OOS)

| variant | IS CAR / Sharpe | OOS CAR / Sharpe | trades/day IS | $/trade OOS |
| --- | --- | --- | --- | --- |
| control (30/8, shipped) | -56.0 / -3.26 | -10.1 / -0.26 | 97.8 | -4 |
| band 50/12 + hold 12 | -50.9 / -2.92 | -11.1 / -0.35 | 67.8 | -6 |
| 5-minute cadence | -57.5 / -3.57 | -9.7 / -0.29 | 72.6 | -5 |
| skip 11:30-14:00 | -50.1 / -2.96 | -3.7 / -0.02 | 83.3 | -2 |
| **trend filter, 20 bps** | **-11.9 / -1.00** | **+16.9 / +1.23** | 31.7 | +18 |
| trend filter, 10 bps | -8.9 / -0.71 | +23.6 / +1.64 | 34.2 | +23 |
| trend filter, 40 bps | -5.3 / -0.49 | +15.6 / +1.16 | 26.1 | +19 |
| trend filter **inverted** | -46.3 / -2.78 | -5.5 / -0.13 | 74.9 | -3 |
| trend + 50/12 + hold 12 | -1.4 / -0.09 | +9.7 / +0.81 | 17.2 | +18 |
| trend + 50/12 + hold 12, 40 bps | -1.9 / -0.15 | +11.1 / +0.92 | 14.5 | +24 |
| **trend + 70/15 + hold 20** | **+0.8 / +0.13** | **+11.3 / +0.94** | 11.0 | +32 |
| + range expansion 1.2x | -0.7 / -0.27 | +5.4 / +2.45 | 0.8 | +263 |

- **Only one of the five levers is a mechanism.** Min hold, the midday blackout and the coarse
  cadence each remove trades roughly in proportion to the loss they remove and leave the
  module deeply negative - they shrink the position, they do not change the sign. The
  **session-trend filter does change the sign**: taking only the fades that lean *with* the
  day's direction (buy the dip below VWAP on an up day, short the pop above VWAP on a down
  day) moves the module from -56.0/-10.1 to -11.9/+16.9 while cutting turnover by two thirds.
  **Inverting the filter is the control and it fails as predicted** (-46.3/-5.5), so this is
  the mechanism and not a threshold that happened to land well: the fade was losing because it
  was fighting trend days, and the losses are concentrated in exactly the trades the filter
  removes. It is also a shelf - `trend_min` at 10, 20 and 40 bps all give OOS Sharpe 1.16-1.64
  and the same sign in both halves.
- **Range expansion is not usable.** Requiring atr14 >= 1.2x the session's mean kills the
  module: 0.8 trades/day, 104 trades over 124 sessions. The OOS Sharpe of 2.45 on 50 trades is
  not a result, it is an empty sample, and it is not carried forward.
- **Stacking the levers onto the trend filter walks a frontier, it does not climb.** Widening
  the band and adding a hold trades OOS return for IS return one-for-one - 20 bps alone is
  -11.9/+16.9, plus 50/12 and hold 12 is -1.4/+9.7, plus 70/15 and hold 20 is +0.8/+11.3.
  The best cell in both halves is the last one, and it is the only cell positive in both -
  by +0.8% CAR at Sharpe 0.13 on 124 sessions, which is indistinguishable from zero
  (SE of an annualized Sharpe on 124 days is ~1.4).

### The sleeve is what decides, and the sleeve says no

| mix (ORB 4x ATR + late fade, + trend-filtered fade at) | IS CAR / Sharpe / DD | OOS CAR / Sharpe / DD | trades/day | total P&L, 183 sessions |
| --- | --- | --- | --- | --- |
| **0 (deployed control)** | **24.21 / 1.007 / 14.5** | **55.33 / 1.731 / 7.30** | **46-49** | **$221,211** |
| 0.25 (70/15, hold 20, 20 bps) | 23.48 / 0.977 / 15.7 | 57.95 / 1.827 / 7.06 | 58.0 | $222,294 |
| 0.5 (70/15, hold 20, 20 bps) | 22.25 / 0.932 / 16.6 | 59.11 / 1.880 / 6.73 | 58.1 | $218,785 |
| 0.5 (50/12, hold 12, 40 bps) | 23.34 / 0.959 / 16.6 | 60.04 / 1.901 / 6.89 | 62.4 | $225,155 |
| 0.5 (70/15, hold 20, 40 bps) | 21.04 / 0.886 / 16.8 | 61.24 / 1.927 / 6.87 | 56.9 | $216,934 |
| 1.0 (70/15, hold 20, 20 bps) | 20.74 / 0.866 / 18.4 | 54.32 / 1.769 / 5.87 | 57.5 | $204,124 |

- **Every cell is the same trade: IS return and IS drawdown for OOS return.** The IS response
  is monotone in the allocation (24.21 -> 23.48 -> 22.25 -> 20.74) and IS drawdown widens by
  1.2-3.9 points in every one; OOS rises to a peak near 0.5 and falls again at 1.0. Three
  different fade parameter cells at 0.5 give the same shape, so this is a shelf and not a
  spike - the effect is real, it is just not a gain.
- **Over the whole window it is a wash bought with turnover.** Total P&L across all 183
  sessions is $221.2k deployed against $222.3k / $218.8k / $225.2k / $216.9k for the four
  cells at alloc 0.25-0.5 - a spread of +/-2% around doing nothing - and $204.1k at 1.0.
  The price of that wash is 22-34% more trades per day (46-49 -> 57-62) and 2 points of IS
  drawdown, on a sleeve whose live costs are only estimated (1.5 bps plus commission) and
  whose first live paper session is tomorrow morning.
- **Decision: refused. `vwap_trend` alloc stays 0 and `live/intraday_config.json` is not
  touched.** Rule (c) asks for OOS improvement and the fade does deliver that, but OOS
  improvement bought by an equal IS loss is the same regime rotation A-2 documented on the ORB
  stop, and here the two-half total does not move at all. Paying 25% more turnover for a
  measured zero is not a trade worth making the day before the sleeve goes live.
- **A-1 is closed.** The module is not deleted: the trend filter repaired it from -56%/yr to
  break-even, which is a genuine finding about *why* VWAP fading loses on these names, and all
  five levers ship in the module defaulted off with the control reproducing A-6 exactly. It
  stays available for A-5 to reconsider once measured live slippage replaces the estimate, or
  for a future allocator with a real regime signal - but it earns no capital on this evidence.
- **Next.** A-7: the daily loss limit and the per-symbol cap. A-2 and A-1 have now both
  measured that signal-level levers cannot move this sleeve's tail or its turnover economics,
  which leaves the framework constants in `scripts/intraday_common.py` as the untested surface.
  Any change there needs a replay per AGENTS.md rule (a).

## 2026-09-09 - Paper session 2026-09-09 (ops close)

End-of-day operations check. The daily sleeve rebalanced and filled; the intraday sleeve did
**not** run a live session today - the paper deploy date for it is 2026-09-10, and everything
in `live/log/intraday-2026-09-09.jsonl` is research replay plus two short dry-run launches.

| sleeve | trades | P&L | costs | worst event |
| --- | --- | --- | --- | --- |
| daily (`s1_momo`) | 3 fills (TQQQ 3700, XLE 7333, XLK 2616, all BUY MKT, all Filled) | -497.79 unrealised at 15:50 ET | not itemised in the log; slippage vs stale ref prices: XLE +0.96%, TQQQ -0.93%, XLK -0.01% | 4x `connect_failed` to 127.0.0.1:4002 between 09:38 and 09:46 ET (IB Gateway not yet up); the 15:45 run connected first try |
| intraday (`active`) | 0 live trades | 0 | 0 | 2 dry-run launches (11:08, 11:12 ET) ran ~7 min and were stopped; no `end` event, no live snapshot, no fills |

- **Daily rebalance, 15:45 ET.** Plan `s1_momo` as-of 2026-09-08, regime risk-on (vol 0.0832 vs
  median 0.127), winners XLE/XLK/QQQ, vol_scale 1.31, gross weight 1.2331, effective exposure
  1.7669. Targets XLE 0.4748, XLK 0.4913, TQQQ 0.2669 on net liq 1,000,344.32. Three market
  orders sent at 19:45:07-08 UTC, all filled by 19:46:38 UTC: TQQQ 3700 @ 71.49, XLE 7333 @
  65.39, XLK 2616 @ 187.8508. Post-trade gross position value 1,235,006.07 (1.23x net liq),
  cash -235,503.86, available funds 558,561.03, unrealised -497.79.
- **Intraday sleeve.** No live session. Preflight/replay ran repeatedly over 2026-09-04 and
  2026-09-08 (the last replay of 09-08 ends -5,271 P&L, 40 trades, 854 costs - research, not
  the paper book). Two `start` events today both carry `dry_run: true`. One `stale_book` event
  at 11:08 ET reported a leftover book (NVDA -667, AAPL -478, MSFT 202) from an earlier dry
  run; the 11:12 relaunch logged `ignored_book_file` and discarded it. `feed_probe` measured
  IB delayed quotes at 14.0 minutes, as expected on the paper data subscription.
- **Flat check.** `live/state/intraday_book.json` does not exist and the broker account holds
  only daily-sleeve names (XLK, XLE, TQQQ) - no intraday universe symbols. The sleeve is flat;
  no `--flatten` was required or run.
- **Loss limit / halt / error events.** None in either log today.
- **Open item.** `notify_failed` at 10:06 ET: Telegram bot token missing, so the daily plan
  notification did not send. Ops-only, does not affect trading.
- **Next.** Tomorrow is the intraday sleeve's first scheduled live paper session (09:25 ET task).
  Verify the preflight replay passes and that the launch is not `--dry-run`.

## 2026-09-09 - A-2: ORB tail control. The tail does not come off for free; what the stop does is rotate return between regimes

- **What.** Nine variants of `algorithms/intraday/orb/signal.py` on the 9-month store, fixed
  window 2025-12-15..2026-09-08 (the 09-09 session is still in progress), split 2026-06-15,
  124 IS / 59 OOS sessions. The module was rewritten to carry the levers as parameters, all
  defaulted to the shipped behaviour: `stop` ("mid" | "atr") with `stop_atr`, `range_minutes`,
  `scale_out`/`scale_r`/`scale_breakeven`, and `disaster_atr` (an ATR backstop *on top of* the
  midpoint stop, whichever triggers first). The refactor is exact: the control run reproduces
  the A-6 in-sample cell to the digit - 16.225% net, 4,359 trades, 35.739% CAR.
- **Why.** Top backlog item. ORB is positive in both halves but its worst days (-34k, -26k)
  are what trip the framework's 2.5% daily loss limit 3-4 times per half, and A-6 named those
  days as the sleeve's tail risk.

### The frontier (ORB standalone, annualized after costs, IS -> OOS)

| stop | IS CAR / Sharpe | OOS CAR / Sharpe | worst day IS / OOS | loss-limit days |
| --- | --- | --- | --- | --- |
| midpoint (shipped) | 35.7 / 1.31 | 10.7 / 0.51 | -33.9k / -26.4k | 3 / 4 |
| + 8x ATR backstop | 35.3 / 1.30 | 10.9 / 0.52 | -33.8k / -26.4k | 3 / 4 |
| + 6x ATR backstop | 34.7 / 1.27 | 13.3 / 0.60 | -33.4k / -26.2k | 3 / 3 |
| **+ 4x ATR backstop** | **31.4 / 1.19** | **19.3 / 0.80** | **-30.5k / -26.0k** | **3 / 4** |
| + 3x ATR backstop | 21.5 / 0.88 | 26.5 / 1.04 | -31.9k / -27.1k | 4 / 3 |
| pure 3.0x ATR | 25.1 / 0.99 | 19.8 / 0.83 | -32.6k / -26.7k | 4 / 3 |
| pure 1.5x ATR | -12.3 / -0.51 | 43.1 / 1.65 | -25.0k / -22.9k | 1 / 0 |
| pure 1.0x ATR | -0.3 / 0.08 | 36.8 / 1.56 | -21.4k / -18.0k | 0 / 0 |

- **The hypothesis as written is refused.** No variant cuts the tail while keeping the return.
  The tail only comes off materially at a *tight* stop - 1.0x ATR14 takes the worst day from
  -33.9k to -21.4k and the loss-limit days to zero in both halves - and that same stop takes
  the in-sample return to zero. Read across the table and the response is **monotone in the
  stop distance**: tightening does not create return, it moves it from the first half of the
  sample to the second. The mean of the two halves is roughly conserved (23% at the midpoint
  stop, 25% at 4x, 24% at 3x, 15% at 1.5x). That is a regime property, not an edge, and it is
  the same shape that got the VWAP fade removed in A-6 - only this time both ends stay
  positive over the window as a whole.
- **The other three levers all lose outright.** Scale-out of 50% at 1.5R with a breakeven stop:
  IS 24.8 / OOS 8.0, worse in both halves at the same worst day (it clips the best days,
  86k -> 60k, and the tail is not where it acts). A 30-minute opening range: 15.9 / -1.1.
  Volume filter at 1.6x instead of 1.2x: 15.0 / -9.8. All are worse than the control in both
  halves; none is carried forward.

### What shipped, and what it is worth

`disaster_atr = 4.0` on the ORB sub-strategy in `live/intraday_config.json`. At the sleeve
level (ORB 1.0 + late fade 1.0, per-symbol 0.15, gross 1.5, same window and split):

| mix | IS CAR / Sharpe | OOS CAR / Sharpe | worst day | loss-limit days |
| --- | --- | --- | --- | --- |
| deployed (no backstop) | 27.2 / 1.10 | 36.2 / 1.24 | -31.4k / -26.9k | 4 / 5 |
| + 4x ATR backstop | 24.2 / 1.01 | 55.3 / 1.73 | -30.3k / -26.9k | 4 / 4 |

- **Decision: ship it, with the reason stated plainly.** It satisfies AGENTS.md rule (c) - OOS
  improves, +19 points of CAR and +0.49 of Sharpe - both halves stay positive, the worst day
  is no worse, one loss-limit day comes off, and total P&L over the 183 sessions rises from
  $201k to $221k. It sits on a shelf, not a spike: 8x is indistinguishable from off, and 6x,
  4x and 3x walk the frontier smoothly, so 4x is a point on a monotone response rather than an
  argmax found by search. The mechanism is defensible before the fact - a breakout entered at
  the extreme of an unusually wide range has its midpoint stop very far away, and the backstop
  caps exactly those trades - which is why the 8x cell changes nothing (it almost never binds).
  **What it is not** is a free improvement: the in-sample half pays 3 points of CAR and 0.09
  of Sharpe for it, and if the next quarter looks like the first half of this sample rather
  than the second, this change will have cost money. Replay of 2026-09-08 with the deployed
  config passed before it was written (46 trades, flat at the close, -4,881 P&L on the day).
- **Next.** A-1 (make the VWAP fade pay on the long window, or retire the module). The tail
  itself is now a *framework* question rather than a signal one: the loss-limit days survive
  every signal-level control tried here, so the lever that actually bounds them is the 2.5%
  daily limit and the per-symbol cap, and sweeping those is A-7.

## 2026-09-09 - A-6: the deployed mix re-derived on 9 months (2025-12-15..2026-09-09, split 2026-06-15)

- **What.** With the minute store extended to 184 sessions per name, every strategy and both
  candidate mixes were re-run on a fixed window with a 124/60-session split.
- **Result (annualized after costs, IS -> OOS).** Late-day fade -4.5% (Sharpe -0.76) ->
  +26.4% (5.20): regime-dependent, carried by the last three months. VWAP fade (30/8/15)
  -56.0% (-3.26, 22 loss-limit days) -> -7.2%: **the A-0 out-of-sample number was a
  one-month regime, not an edge; removed.** ORB +35.7% (1.31) -> +8.2% (0.43): positive both
  halves, 34 trades/day, worst days -34k/-26k, 3-4 loss-limit days. Gap fade -4% both halves:
  dropped. The A-0 deployed mix (with VWAP fade) -18.0% -> +53.9%: fails the both-halves rule.
  ORB 0.5 + late fade 1.0: +11.8% (0.89) -> +34.6% (2.03), 46 trades/day, std ~9k.
  **ORB 1.0 + late fade 1.0: +27.2% (1.10) -> +32.6% (1.15), 46-49 trades/day, daily P&L
  std ~17k, best +77k, worst -31k, 4-5 loss-limit days per half, costs ~1k/day.**
- **Decision.** Deploy ORB 1.0 + late-day fade 1.0, VWAP fade 0, per-symbol 0.15, gross 1.5
  (`live/intraday_config.json`). It is the only candidate positive in both halves that also
  delivers the owner's volatility mandate (~27% annualized vol on the sleeve). The
  breakout's worst days are the sleeve's tail risk; the framework's 2.5% daily loss limit is
  what bounds them and it will fire roughly one day in twelve.
- **Next.** A-2 (ORB tail control: ATR stop, scale-out) and A-1 (make a VWAP fade pay on the
  long window, or retire it). Measure the sleeve's correlation with the daily champion from
  paper logs. Replay of 2026-09-08 with the final config passed before deployment.

## 2026-09-09 - A-0: the intraday active sleeve, first evidence and the deployed mix

- **What.** Built the intraday sleeve end to end (see AGENTS.md "The intraday active sleeve"):
  16-name disjoint universe, IBKR 1-minute store (`data/minute`, 3 months, being extended to
  9), causal features, four strategies (ORB, VWAP trend, late-day momentum, gap fade), a
  minute backtester with 1.5 bps slippage + IBKR commission, and a live trader with an offline
  replay. Deployed via the 09:25 ET task with a replay preflight.
- **Why.** Owner mandate: a volatile, high-turnover book on most of the capital by the
  2026-09-10 open. The daily champion runs ~16% vol; this sleeve is where the turnover lives.
- **Result (16 names, fixed window 2026-06-11..2026-09-09, split 2026-08-15, after costs).**
  Trend-following loses *before* costs at the 1-minute horizon: VWAP trend -82%/yr IS,
  -89%/yr OOS at ~150 trades/day; late-day momentum -25%/yr IS, -29%/yr OOS with 29% winning
  days. Their inverses are the edge: **late-day fade** +18%/yr Sharpe 2.9 IS, +25%/yr Sharpe
  8.2 OOS, 11 trades/day, worst day -1.7k OOS; **VWAP fade** (30 bps band, 8 bps exit,
  15-bar momentum) +124%/yr Sharpe 4.2 OOS at ~100 trades/day, but negative over the longer
  (unstable, extension-in-progress) in-sample window, so it is a regime bet. ORB is ~0 IS,
  +14%/yr OOS. Gap fade fails OOS (-31%/yr).
- **Deployed mix** (`live/intraday_config.json`): late fade x1.0, VWAP fade x0.5, ORB x0.5,
  per-symbol 0.15, gross 1.5. Fixed-window result: IS +22.6%/yr Sharpe 1.31 (45 sessions,
  1 loss-limit day, worst -27k), OOS +119%/yr Sharpe 9.5 (17 sessions, worst -7.6k), 133-146
  trades/day, turnover ~8x equity/day, costs ~$1.6k/day, daily P&L std $5-10k. The
  conservative alternative without VWAP fade: IS +15.6%, OOS +35%, 45 trades/day.
- **Caveats, stated plainly.** 62 sessions is a short sample; OOS is 17 sessions. The
  in-sample counts in the ledger rows from 15:4x-16:1x UTC differ because the 9-month
  extension was writing older sessions between runs; only rows with `--start 2026-06-11` are
  comparable. IBKR quotes are 15 minutes delayed without a subscription, so the live trader
  uses the Yahoo 1-minute feed (measured real-time) until the owner subscribes; paper fills
  may still be simulated on delayed data.
- **Next.** A-6: once the 9-month store lands, re-run every strategy and the mix on the full
  window with a 2-way split; re-derive the deployed mix from that; measure the sleeve's
  correlation with the daily champion; then A-1/A-2 refinements.

## 2026-09-09 - D-2: intraday data, and the month boundary that ate a session a month

**Why this.** `paper_trade.py --check` was the first thing run this iteration and it now
answers - account `DUT091359`, net liquidation $1,000,344, no positions. The 10141 disclaimer
has been accepted, so the IB API is open for the first time and **D-2 is the top open item**,
exactly as the backlog said it would be. Everything the owner decided yesterday routes through
it: volatility is to be earned with a second, uncorrelated intraday sleeve (S-2), and S-2 has
never had a bar to test on because Yahoo caps 1-minute history at ~30 days.

**What was built.** `scripts/fetch_minute.py`: IBKR `reqHistoricalData` at `1 min` /
`TRADES` / `useRTH=True`, written as LEAN minute files
(`equity/usa/minute/<sym>/<yyyyMMdd>_trade.zip` -> `<yyyyMMdd>_<sym>_minute_trade.csv`,
`<ms since midnight ET>,o,h,l,c,v`, prices x10000), reusing `fetch_data.py`'s
writer/validator shape. Three properties it needed and has: a sliding-window pacer for
IBKR's 60-requests-per-10-minutes rule, resumability by month chunk (an interrupted
backfill restarts by re-running the same command), and `clientId` 31, clear of the paper
runner's 17. Prices are raw; dividends stay in the D-1 factor files, as at every other
resolution.

**The bug worth recording.** The obvious chunking - `durationStr="1 M"` ending at 23:59 on
the month's last day - is wrong, and wrong *silently*. IBKR measures a duration backwards
from `endDateTime`, so a 1-month window ending 23:59 on 31 July begins 23:59 on 1 July,
which is **after that session's close**. The first session of every month is dropped. The
smoke run made it visible - 21 sessions for July 2026 when the daily file says 22, one
missing date, `20260701` - and at scale that is ~5% of the sample gone, in a shape that
looks like nothing: the bar counts are all exactly 390, every session that is present is
complete, and only a cross-check against an independent trading calendar shows the hole.
Fixed by requesting `5 W` (35 days, four days of slack on the longest month) and filtering
the overlap back to the chunk, so a session is still written exactly once. Re-run: 22
sessions for July, 0 missing.

**Result - SPY 2020-01-02 .. 2026-09-08 complete.**

| | |
| --- | --- |
| sessions | **1,679**, 0 missing against the daily calendar, 0 truncated |
| bars | **652,650** (mean 388.7/session; 12 half days at 210) |
| clamped bars | 0 |
| close vs D-1 daily, median | **0.007%** |
| close vs D-1 daily, worst | 0.957% (2025-04-09) |
| on disk | 14 MB |

**The acceptance test is a LEAN run, not a file check**, because D-1's worst bug was a file
that passed every structural check and made LEAN return *zero bars* with no error.
`algorithms/d2_minute_smoke` streams the whole backfill at minute resolution and asserts
seven properties: run `20260909T160005Z`, **all seven PASS**. LEAN sees 652,650 bars over
1,679 sessions - bit-identical to what the writer counted, so nothing was silently dropped -
every session opens at 09:31 and closes at 16:00 (1,667) or 13:00 (12 half days), no
inconsistent OHLC, 65 zero-volume bars out of 652,650. `evaluate.py` correctly refuses it:
0 orders, and it is tagged `not promotable`. Champion unchanged at S-12.

**The close deviation is real and is not a data error.** The six sessions deviating more
than 0.2% are 2020-03-13/17/18/19/23/24 and 2025-04-03/09 - the COVID crash and the April
2025 tariff selloff. On violent days the closing auction clears away from the last 1-minute
RTH trade, and the daily close is the auction print while the minute file's last bar is not.
**This is a design constraint for S-2, not a defect**: a sleeve that flattens at the close
must model the 16:00 auction, and assuming the 15:59 bar's close is a fill price will book
up to ~1% of free P&L on exactly the days an intraday strategy makes its money.

**Decision.** No promotion - D-2 is infrastructure. SPY is complete and validated end to end,
so **S-2 is unblocked on its primary instrument** and is the next item.

**Cost, honestly.** IBKR serves ~260-790 bars/s, so this is slow: one symbol-decade is
~40 minutes of wall clock and the full five-symbol set is a multi-hour job. That is why the
script is resumable by month, and why only SPY was taken to completion in one iteration.
QQQ, IWM, TQQQ and SQQQ are one command each (`--symbols QQQ --start 2020-01-01`) and are
the first thing to run in the background of the next iteration.

**Next.** S-2 opening-range breakout on SPY minute bars, judged on the same IS/OOS split and
promotion rules, with its correlation to the champion's daily returns as a first-class metric.

## 2026-09-09 - I-1: the paper runner would have placed twice the backtest's orders

**Why this and not a backtest.** Port 4002 answered at the top of this iteration for the
first time - Gateway is up and logged in - so I-1 became the top open item and I took it
instead of another sleeve experiment. It got exactly one step further before stopping:

```
Error 10141, reqId -1: Paper trading disclaimer must first be accepted for API connection.
```

A one-time acknowledgement inside Gateway's GUI, confirmed not to be a stale API session
(same error on a fresh `--client-id 91`). That is the human's click and is already filed;
the sibling review job filed the same finding independently this morning. So the question
became: **what part of I-1 can be finished today, with no connection?**

The answer is its last unbuilt piece. I-1's checklist ends with "compare the runner's order
list with what the LEAN backtest would have done on the same date" - the gate that decides
whether the thing about to trade real-shaped orders is the thing that was validated. It had
never been built, and it does not actually need IB.

**Hypothesis.** The signal cannot diverge - `signals.py` is imported by both LEAN and the
runner, which was the whole point of splitting it out in S-1. But *everything downstream of
the signal is duplicated*: `main.py:submit_targets` and `paper_trade.py:plan_orders` are two
independent implementations of "turn target weights into integer share deltas and drop the
ones too small to bother with". Nothing had ever compared them. Two implementations of one
rule, written weeks apart, are where I expected to find a divergence.

**Method.** `scripts/compare_orders.py` walks LEAN's own daily bars with the shipped
champion signal, maintains a share-level book the way `submit_targets` does, and at every
decision date hands *identical* inputs - same targets, same positions, same prices, same
equity - to both implementations, then diffs the two order lists. Because the inputs are
identical by construction, a difference cannot be a data or signal artifact; it can only be
the execution layer. It imports `plan_orders` from `paper_trade.py` rather than copying it,
so it tests the code that will actually trade, and it exits non-zero on any disagreement so
the deploy checklist can gate on it.

### Result: the runner and the backtest did not agree, and it was not close

| | decision dates | agreement | orders placed |
| --- | --- | --- | --- |
| **before** | 3,689 | **1,350 (36.6%)** | LEAN 4,653 / runner **9,196** (+98%) |
| **after** | 3,689 | **3,689 (100.0%)** | LEAN 4,653 / runner 4,653 (+0) |

**One cause, all 4,543 of them: `MIN_NOTIONAL = 200.0`.** The backtest bands orders at a
*fraction of equity* (`min_order_value = 0.01`); the runner banded at a *flat $200*. On the
$100k paper account those are $1,000 and $200 - a 5x tighter band - and the gap widens with
every dollar the book compounds, because LEAN's band grows to $24,000 by the end of the
sample while the runner's stays at $200. Every disagreement was the same shape and the same
sign: the runner sending a small drift adjustment the backtest bands out. Nothing subtle,
nothing offsetting, and it would have been invisible on the first day's trade (from flat,
all three orders are tens of thousands of dollars and clear both bands identically) and then
compounded silently from the second rebalance onward.

**What makes this more than a tidy-up is S-13, last night.** S-13 measured that ~63% of the
champion's orders are return-neutral - they buy nothing in backtest and cost a spread live -
and concluded the *research* question was closed. This is the same population of orders seen
from the execution side: the runner's tight band was about to opt the paper account into
roughly 4,500 extra small orders a decade, precisely the ones S-13 showed have no return in
them. The backtest would have looked fine and the paper account would have quietly
underperformed it on fills, which is the specific failure mode a paper stage exists to catch
and the hardest one to diagnose after the fact.

**Fix.** `plan_orders` now bands at `max(MIN_NOTIONAL, MIN_ORDER_VALUE * net_liq)` with
`MIN_ORDER_VALUE = 0.01` tracking `main.py`, and uses the same `max(px, 0.01)` notional. The
$200 survives only as an absolute floor for a small account, where it binds below ~$20k of
net liquidation; at the paper account's size the fraction dominates and the two agree
exactly. Both constants now carry a comment saying they must move together.

**Guarding against a test that passes for the wrong reason.** Re-run with
`--min-order-value 0.02`, i.e. a deliberately mismatched pair, and the gate fails with 442
divergent orders and exit code 1; at the matched value it exits 0. So it discriminates.

- **Decision. No promotion and no champion change** - and nothing under `algorithms/` was
  touched, so `OrderListHash 5246804e17a67af90028ffceead7d3b3` is unchanged by construction
  and needs no rebaselining run. What shipped is `scripts/compare_orders.py` (new) and a
  one-line band fix plus documentation in `scripts/paper_trade.py`. `--mock --dry-run`
  re-verified after the fix: unchanged 1.23x gross, margin 0.75, XLE/XLK/TQQQ - correctly,
  since from flat every order clears both bands.
- **Next.** The click is the whole critical path. The moment 10141 clears: `--check`,
  `--dry-run` against the real account, re-run `compare_orders.py`, then stop at
  `live/APPROVED_PAPER.md`, which is the human's. If it has not cleared by the next
  iteration, the honest offline work is the other half of this same audit - the runner and
  the backtest also disagree about *where prices come from* (yfinance `auto_adjust` against
  LEAN's adjusted bars), and that is measurable today with the same harness, without IB.


## 2026-09-09 - S-13: the execution band buys nothing and costs nothing, and that is the result

**Hypothesis.** S-12 bought 0.8 points of CAR by re-weighting the book as vol ratios drift,
and paid for it with 84% more orders (2,573 -> 4,735) and $8.3k more commission. Those extra
orders are by construction *small* - they are drift adjustments, not rotations. The execution
layer already has a no-trade band for exactly this, `min_order_value`, which skips any delta
worth less than that fraction of equity - and it has been pinned at 0.01 since S-1 and **never
swept**. If most of S-12's cost sits just above a 1% band, widening it should hand back the
commission and keep the risk-parity gain. Cheap to test: the knob is already wired to
`S1_MIN_ORDER_VALUE`, so no code changed and no control run was needed - the champion run
`20260909T042431Z` *is* the 0.01 cell.

### Result (LEAN, full period 2012-01-03 .. 2026-09-04, S-12 champion signal throughout)

| band | CAR | Sharpe | MaxDD | orders | fees |
| --- | --- | --- | --- | --- | --- |
| **0.01 (champion)** | 24.40% | **0.921** | **25.1%** | 4,735 | $45,695 |
| 0.015 | 24.35% | 0.919 | 26.9% | 3,887 | $44,239 |
| 0.02 | **24.54%** | **0.927** | 25.2% | 3,355 | $43,960 |
| 0.03 | 24.34% | 0.917 | 25.5% | 2,737 | $42,329 |
| 0.05 | 23.92% | 0.900 | 29.2% | 2,112 | $39,729 |
| 0.08 | 24.47% | 0.920 | 25.4% | 1,727 | $39,568 |

**The response is non-monotone and essentially flat.** Across a factor of eight in the band -
and a factor of 2.7 in order count - CAR walks 24.40, 24.35, 24.54, 24.34, 23.92, 24.47 and
Sharpe walks 0.921, 0.919, 0.927, 0.917, 0.900, 0.920. There is no trend, in either direction.
The one cell that visibly deviates, 0.05, deviates in *drawdown* (29.2%, four points wide of
every other cell) with no mechanism that explains why a 5% threshold should be worse than both
a 3% and an 8% one. That is the signature of path dependence: the band changes *which day* a
rebalance fires, and a different fill date reshuffles the entire subsequent equity path.

**So the honest reading is not "0.02 wins".** 0.02 does beat the champion on both `must_beat`
metrics at a 25.2% drawdown, and `scripts/evaluate.py --candidate 20260909T043527Z` returns
**BEATS champion**. Its sub-periods even agree in sign - IS 2012-2019 19.32% / 0.891 / 25.2%
against the champion's 19.18% / 0.884 / 25.1%, OOS 2020-2026 30.98% / 0.988 / 22.7% against
30.86% / 0.985 / 22.6%. **It was refused anyway**, on the shelf-not-spike rule that promoted
S-9, S-10 and S-12: both of 0.02's neighbours *lose* to the champion, so there is no shelf and
no dose-response, and the whole 0.01-0.03 region scatters by +/-0.1 points of CAR with 0.02's
margin (+0.14) sitting inside that scatter. Promoting it would be fitting an execution
threshold to path luck, which is the specific thing `AGENTS.md` says to fight. Both sub-periods
agreeing is worth less than it looks here: at +0.11 and +0.14 points they are two draws from
the same scatter, not independent confirmation.

**What the flatness is actually worth, which is more than a promotion would have been.**
Turnover between 1,727 and 4,735 orders is *return-neutral*. About 3,000 of the champion's
orders - 63% of them - buy nothing at all. In the backtest that costs only the $6.1k of
commission the 0.08 cell saves, which is why no cell wins: LEAN charges commission and the
fee difference is too small to move a 24% CAR. **Live it is not neutral**, because every one
of those orders also crosses a spread that the backtest does not model at all. S-3 measured
the commission floor at 2.1bps per unit of turnover; a half-spread on a liquid 3x ETF is of
the same order, so the true saving from the wide band is plausibly around double the modelled
$6.1k - and, more importantly, 63% fewer chances for a real fill to come back worse than the
close the signal decided on.

That makes the band a **live-execution decision rather than a research one**, and it is not
the loop's call to make three days before a paper deploy: switching to 0.08 would move the
order list and invalidate the `OrderListHash` I-1's pre-deploy comparison is built on, in
exchange for a backtest improvement of exactly zero. Filed for the human instead.

- **Decision. No promotion; the champion is unchanged at S-12.** No parameter shipped -
  `min_order_value` stays 0.01, the signal is untouched, and `OrderListHash
  5246804e17a67af90028ffceead7d3b3` still stands, so I-1 needs no rebaselining. The six-cell
  curve is recorded in `main.py` next to the parameter so a later session does not re-fit it,
  and the wide-band option is a one-line question in `BLOCKERS.md`.
- **Next.** This is the second iteration running (with S-11) to find that the champion's
  turnover cannot be converted into return, and now also that it cannot be *removed* for
  return - the sleeve is simply insensitive to execution timing at this frequency. Combined
  with S-12 spending the allocation step, the ETF-9 sleeve is out of cheap levers by
  measurement rather than by assumption. Ports 4002 and 7497 were checked again at the top of
  this iteration and are both still closed, so S-2 (a second sleeve), D-2 (intraday data) and
  the I-1 paper deploy all remain behind the IB Gateway login, and that login is now the only
  thing standing between this repo and its 2026-09-10 deadline.

## 2026-09-09 - S-12: risk parity inside the top 3, new champion at 24.4% / 0.92

**Hypothesis.** Every iteration since S-6 has changed *what* the signal picks (S-9's fourth
horizon, S-10's skip) or *whether* it re-picks (S-11's whipsaw controls). Nothing has touched
the last step: once momentum has chosen three names, the exposure budget is split 1/N between
them. Equal weight equalizes *notional*, not risk, and this sleeve is not homogeneous - GLD and
TLT run near 12% annualized vol while XLE and XLK run near 30%. So on any day the book holds a
quiet name and a violent one, the violent one supplies most of the variance and the quiet one is
close to decoration. **Weighting each winner by 1/sigma on its own trailing vol should raise
Sharpe**, and it should be nearly free in rotation turnover, because vol ratios move far more
slowly than rankings do.

Two implementation notes. The vol is measured on the **unlevered ranked series**, not on the
3x proxy actually traded, because the sizing step already divides by the proxy's leverage
multiple - the share being split is unlevered-equivalent exposure, so it has to be equalized
against unlevered-equivalent risk. And the tilt is a *dial*, not a mode: shares are
`(1/sigma) ** alloc_vol_power`, so power 0 is exactly equal weight and 0.5 is half the tilt.
That is what makes a dose-response test possible, which is the check that separates an effect
from a lucky cell.

**Control first.** LEAN run `20260909T034600Z` at the defaults reproduces
`OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf` bit for bit, so the new code is provably inert
until it is switched on.

### Result (LEAN, full period 2012-01-03 .. 2026-09-04, power 1.0 unless stated)

| cell | CAR | Sharpe | MaxDD | orders | fees | PSR |
| --- | --- | --- | --- | --- | --- | --- |
| S-10 champion (equal weight) | 23.61% | 0.874 | 25.9% | 2,573 | $37,380 | 17.7% |
| invvol window 10 | 22.77% | 0.857 | 29.4% | 6,318 | $50,184 | 16.2% |
| invvol window 20 | 24.25% | 0.915 | 25.4% | 4,768 | $45,982 | 22.3% |
| **invvol window 21 (shipped)** | **24.40%** | **0.921** | **25.1%** | 4,735 | $45,695 | **23.0%** |
| invvol window 30 | 24.18% | 0.911 | 25.1% | 4,102 | $42,997 | 21.8% |
| invvol window 40 | 23.74% | 0.893 | 27.4% | 3,644 | $40,034 | 19.8% |
| invvol window 60 | 23.40% | 0.879 | 25.5% | 3,239 | $39,162 | 18.4% |
| invvol window 21, power 0.5 | 24.10% | 0.902 | 25.1% | 3,680 | $41,186 | 20.8% |

**It is a shelf, not a spike, in both dimensions.** Across the vol window, 20/21/30 all beat
the champion on CAR, Sharpe *and* drawdown; 40 and 60 still beat it on Sharpe and drawdown but
give the CAR back as the tilt decays toward equal weight; 10 loses outright, which is what a
vol estimate made of noise should do. Across the tilt strength, half the power buys half the
gain (0.902 sits almost exactly between 0.874 and 0.921). A fitted cell does not have a
dose-response curve. **21 sessions is one trading month**, the a-priori point inside the
20-30 shelf; 20 is the argmax and is not what shipped, on the same rule S-9 and S-10 used.

**Sub-periods.** IS 2012-2019 **19.18% / 0.884 / 25.1%** against the champion's
17.64% / 0.801 / 25.9% - ahead on all three. OOS 2020-2026 **30.86% / 0.985 / 22.6%** against
31.09% / 0.972 / 21.5% - ahead on Sharpe, 0.23 points of CAR behind, 1.1 points of drawdown
worse. So the gain is concentrated in the in-sample half, and the out-of-sample half is a
wash. That is the same shape S-11 found for its whipsaw controls, and it is worth naming: the
2012-2019 half is the one that holds mixed baskets of quiet and violent names, and the
2020-2026 half is more often three correlated risk-on names at once, where 1/sigma and 1/N
are nearly the same weights.

**What it costs.** 84% more orders (2,573 -> 4,735) and $8.3k more commission, because the vol
ratios drift daily and the book re-weights between rotations. At S-3's measured 2.1bps cost
floor that is a real bill, and it is paid for here - 0.8 points of CAR and 0.047 of Sharpe
after fees - but it means the honest fallback if commission ever rises is a longer window
(30 keeps most of the gain for 633 fewer orders) rather than a smaller tilt.

**Harness agreement.** Unlike S-10, `sweep_s1.py` agreed on the *direction* - it scored the
shipped cell 22.1% / 1.09 against a 21.2% / 1.03 equal-weight baseline - but it understated the
size of the win and, as in every previous iteration, understated drawdown by about 6 points.
It also flagged window 20 as an isolated spike where LEAN sees a 20-30 shelf, so the sweep
remains a candidate generator only.

- **Decision. Promoted through `scripts/evaluate.py`** (run `20260909T042431Z`, 4,735 orders,
  drawdown 25.1% < 35%, beats the champion on both `must_beat` metrics). The shipped default
  is `weight_mode="invvol"`, `alloc_vol_window=21`, `alloc_vol_power=1.0`; `S1_WEIGHT_MODE=equal`
  restores S-10. New order list **`OrderListHash 5246804e17a67af90028ffceead7d3b3`**, and the
  I-1 pre-deploy comparison must now be made against that hash. `scripts/paper_trade.py
  --mock --dry-run` was re-verified against the new signal and reports the tilt in its
  diagnostics (`alloc_vols`).
- **Next.** The allocation step is now spent as an idea: momentum picks, risk parity sizes, and
  the levers left inside a three-name book (correlation-aware weights, an ex-ante covariance
  target) need more sleeve breadth than nine ETFs to bite. The two things that can still move
  return materially are a second uncorrelated sleeve (S-2) and intraday data (D-2), and both,
  like the I-1 paper deploy, wait on the IB Gateway login - checked again at the top of this
  iteration, ports 4002 and 7497 are both still closed.

## 2026-09-08 - S-11: the whipsaw is real, and suppressing it buys drawdown, not return

**Hypothesis.** S-10's calendar decomposition said the champion's losses are not crises and
not the out-of-sample half - they are 2014/2015/2016 and 2024, and the worst drawdown is a
16-month grind from 2015-07-20 - which is the signature of a ranking that rotates into
whichever sleeve member has just topped out. Three levers, all defaulted off, all of which
also cut turnover (the direction S-3's 2.1bps cost floor rewards): (a) **hysteresis** - an
incumbent's score is credited with `hysteresis` *cross-sectional standard deviations* of the
day's scores before the ranking is cut at `top_n`; (b) **min_hold** - a funded name keeps its
slot for N more decisions unless the entry gate itself refuses it; (c) **rank_persist** - a
name not already held must have led for k consecutive bars before it is funded.

Two implementation notes worth keeping. The hysteresis margin is measured in the day's own
score dispersion, not in return: the blended score is a mean of raw returns whose scale moves
by an order of magnitude between 2017 and 2020, so a fixed return margin would be inert in
one regime and binding in the other. And `rank_persist` is computed by **re-scoring truncated
price windows** rather than from remembered rankings, so it stays stateless and the I-1 paper
runner reproduces it from prices alone; (a) and (b) do need memory, and it rides in the
existing `state` dict (`held`, `held_age`) that the runner already persists. `drawdown_multiplier`
rebuilds that dict from scratch, so the incumbent set is read before it is called and written
back after - and every early return (risk-off, drawdown-flat, no winners, all stopped) leaves
`held` empty, because each of those is a decision to sit in cash and must not leave a phantom
incumbent to defend.

**Control first.** LEAN run `20260909T024906Z` at the defaults reproduces
`OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf` bit for bit, so the plumbing is provably inert.

### Result (LEAN, full period 2012-01-03 .. 2026-09-04)

| cell | CAR | Sharpe | MaxDD | orders | fees |
| --- | --- | --- | --- | --- | --- |
| champion (control) | **23.61%** | **0.874** | 25.9% | 2,573 | $37,380 |
| (a) hysteresis 0.05 sigma | 23.57% | 0.873 | 24.6% | 2,200 | $29,562 |
| (a) hysteresis 0.10 sigma | 23.12% | 0.858 | 23.8% | 1,998 | $25,673 |
| (a) hysteresis 0.20 sigma | 22.34% | 0.827 | 23.5% | 1,832 | $22,729 |
| (b) min_hold 10 | 23.15% | 0.860 | **22.8%** | 1,901 | $27,194 |
| (c) rank_persist 2 | 22.77% | 0.832 | 21.6% | 2,727 | $46,345 |

**The champion's rotation is not noise.** Every device that refuses a rank crossing takes
return with it, monotonically in the strength of the refusal: the frontier slides along, it
does not move up. Nothing here beats the champion on both CAR and Sharpe, and `evaluate.py`
refuses the best of them on exactly that (`Sharpe 0.873 does not beat 0.874`,
`CAR 23.568% does not beat 23.605%`).

**But the exchange rate is cheap in drawdown terms**, which matters because S-8 established
that drawdown, not vol, is what binds this book's size. `min_hold=10` gives up 0.45 points of
CAR and buys 3.1 points of drawdown and $10k of fees; hysteresis at 0.05 sigma gives up 0.04
points of CAR - a rounding error - for 1.3 points of drawdown, 373 fewer orders and $7.8k less
commission. Sub-periods on that cell say the gain lands exactly where S-10 diagnosed the
problem: **IS 2012-2019 17.73% / 0.806 / 24.6% beats the champion's 17.64% / 0.801 / 25.9% on
all three**, while OOS 2020-2026 30.85% / 0.965 / 21.5% is a hair behind 31.09% / 0.972 / 21.5%.
The whipsaw control fixes the whipsaw years and does nothing in the years that had no whipsaw.

**Spending the headroom on size does not recover the return.** Two frontier points:
hysteresis 0.05 + `margin_budget` 0.90 earns 25.21% CAR at 30.4% drawdown and 0.840 Sharpe;
`min_hold=10` + budget 0.85 earns **25.07% CAR at 25.7% drawdown** - matched with the champion
on drawdown, ahead by 1.47 points of CAR, cheaper by 306 orders and $2k of fees - but at 0.861
Sharpe. Return/vol is simply lower for these signals (1.30 vs 1.36), so no size setting fixes
it; the promotion rule that requires beating Sharpe *and* CAR is doing its job here rather
than getting in the way.

**Harness agreement, for the record.** The sweep and LEAN disagreed again on magnitude and on
the sign of the CAR effect (the sweep scored hysteresis 0.05 at 21.8% CAR / 1.06 against a
21.2% / 1.03 control, i.e. a clear win; LEAN says a hair worse) but they agreed on the two
things that decided the iteration: the drawdown improvement, and the fact that `rank_persist`
*raises* turnover (sweep 0.15 vs 0.13; LEAN 2,727 orders and $46k of fees against 2,573 and
$37k) because blocking an entry parks the book in cash and then buys it back.

- **Decision. No promotion; champion unchanged at S-10.** All three parameters ship defaulted
  off in `signals.py`/`main.py` (`S1_HYSTERESIS`, `S1_MIN_HOLD`, `S1_RANK_PERSIST`) with the
  measured numbers in the docstrings. S-11 closes as a *measured trade-off*, not a dead end:
  it says the champion's turnover is paid for, and it hands the human a concrete frontier
  point - 25.07% CAR at the same 25.9%-class drawdown for 0.013 of Sharpe - if the promotion
  rule's Sharpe clause is ever to be traded against the aggressive-return mandate.
- **Next.** The two things left that can move return without spending turnover are a *second*
  uncorrelated sleeve (S-5 has nothing to allocate to until S-2 exists) and intraday data
  (D-2). Both sit behind the IB Gateway login, which is also the only thing between the built
  I-1 runner and the 2026-09-10 paper deadline. That login is the binding constraint on this
  repository now, and it is in `research/BLOCKERS.md`.

## 2026-09-08 - S-10: the textbook skip-a-month is wrong, a skip-a-week is right (new champion)

**Hypothesis.** S-9 opened three follow-ups and this run answers all three on the honest
ETF-9 sleeve: (a) skip-a-month momentum - rank on returns that stop short of the recent
month, the standard 12-2 correction for short-term reversal; (b) horizon weighting - S-9 gave
four horizons an equal vote while its own shelf said the long one carries the information;
(c) why the 2012-2019 half improved so little.

**Two levers, both defaulted off, control run first.** `mom_skip` with
`mom_skip_min_lookback` (which horizons the gap applies to) and `mom_weights` (per-horizon
weights, normalized, matched to `mom_lookbacks` by position with a length guard). LEAN run
`20260909T005513Z` at the defaults reproduces `OrderListHash b763e292cb0eb9a2c81af5739188d437`,
so the plumbing is provably inert.

**Horizon weighting is rejected outright.** Every weight vector loses in the sweep, on both
halves, on the raw blend (`(1,1,1,2)` 18.7% CAR, `(1,1,1,3)` 18.9%, `(1,1,2,3)` 19.0%,
`(1,2,3,4)` 18.1%, against the champion's 21.0%) and also after standardizing the horizons
first, which is the only construction in which "equal vote" is even true (`zscore` alone
19.2%, `zscore` + `(1,1,2,4)` 19.6%). Overweighting the long horizon also *widens* drawdown,
21.1% -> 25-31%. The S-9 shelf was evidence that a 252-day horizon belongs in the blend, not
that it should outvote the others; under a raw-return blend it already dominates
arithmetically, and asking for more is asking for a slower book, not a better one.

**The skip is where the sweep and LEAN disagree in sign, and it matters.** The sweep rejects
every skip cell: skipping all horizons costs 3-4 points of CAR, and confined to
`lookbacks>=120` it decays monotonically from the control (21.0% CAR / 1.04 Sharpe) through
skip=5 (21.2% / 1.03, but drawdown 21.1% -> 31.2%) down to 16-17% at skip=25-40. Run the
same cells through LEAN and the picture inverts:

| skip (on lookbacks >= 120) | CAR | Sharpe | MaxDD | orders |
| --- | --- | --- | --- | --- |
| 0 - the S-9 champion | 20.9% | 0.782 | 28.9% | 2,870 |
| 2 | 19.8% | 0.741 | 26.0% | 2,613 |
| 3 | 23.0% | 0.859 | 20.8% | 2,555 |
| **5 (shipped)** | **23.6%** | **0.874** | **25.9%** | **2,573** |
| 8 | 23.6% | 0.872 | 21.5% | 2,449 |
| 10 | 22.7% | 0.840 | 21.9% | 2,563 |
| 15 | 19.1% | 0.702 | 27.0% | 2,681 |
| 20 - the textbook 12-2 skip | 19.6% | 0.715 | 29.4% | 2,425 |

That is a shelf over 3-10 sessions that collapses on both sides, so the effect is real but
the *textbook parameter is wrong*: on a daily-rebalanced sleeve of index ETFs the reversal
that contaminates a long-horizon momentum measure lives at a one-to-two-week horizon, not a
one-month one. 5 sessions is one trading week, the a-priori unit inside the shelf, chosen
the same way S-9 chose 252 over its 250 argmax.

**Where the skip belongs is measured, not assumed.** Applied to every horizon it loses
(19.2% / 0.704), because the 20-day horizon *is* the recent week or two and truncating it
leaves a stale signal. Confined to the 252-day horizon alone it earns 23.3% / 0.870 / 23.0% -
almost the whole gain - so the effect is a property of long-horizon momentum generally, not
of one lookback. Shipped on `lookbacks >= 120`.

**Result: promoted.** Full period CAR 20.9% -> **23.6%**, Sharpe 0.782 -> **0.874**, drawdown
28.9% -> **25.9%**, orders 2,870 -> 2,573, fees $37.3k -> $37.4k, probabilistic Sharpe 10.1%
-> 17.7%. Both halves win: IS 2012-2019 15.2%/0.70/28.9% -> **17.6%/0.80/25.9%**, OOS
2020-2026 28.0%/0.88/21.0% -> **31.1%/0.97/21.5%**. This is the second consecutive gain that
comes from the signal at *lower* turnover, which is the only kind S-3's 2.1bps cost floor
cannot tax away. `OrderListHash ff4a7cbaaf6e36e58ace2b82ab216bdf`, reproduced by the shipped
default with no environment variables. The I-1 paper runner re-verified `--mock --dry-run`
against it: 1.5x gross, margin 0.75, XLK/XLE/IWM.

**(c) The diagnostic, and where the drawdown actually lives.** Calendar-year decomposition of
the S-9 champion against SPY (sweep harness): the IS half is not uniformly weak, it is three
bad years inside a good decade - 2014 -4.9% excess, 2015 -5.9%, 2016 -11.3% - and the worst
drawdown is a single 16-month grind from 2015-07-20 to 2016-11-07. 2024 is the same failure
again (-17.0% excess). None of those are crises; the crisis-vol filter fires correctly in
2020 and 2022 (2022 is the strategy's best excess year, +33.3%). The failure mode is a
*whipsaw* market where the momentum ranking rotates the book into whichever sleeve just
topped out. That is a signal-persistence problem, not a sizing one, and it is the natural
next hypothesis - filed as S-11.

**Caveat that must not be lost.** `sweep_s1.py` and LEAN now disagree in *sign* on this
lever, not just in magnitude. Earlier calibrations (S-8: sweep understates drawdown by ~2
points at champion size; S-9: by 7.8 points) treated the sweep as a biased but monotone
ranker. It is not, at least where turnover timing matters: the sweep earns weights on the
next day's close-to-close return while LEAN fills MarketOnOpen the next morning and pays
IBKR's real fee schedule. Every future lever gets a LEAN confirmation before it is believed
or discarded - a sweep rejection is now grounds for one LEAN run, not for closing the idea.

**Next.** S-11: attack the 2015-2016 / 2024 whipsaw directly (rank persistence / minimum
holding period / hysteresis on entry and exit), judged against 23.6% / 0.874 / 25.9%.

## 2026-09-08 - S-9: the champion's momentum was too short-sighted (new champion)

**Hypothesis.** Everything since S-6 changed *size* or *universe* and none of it moved the
champion, so S-9 changed what the signal says. S-7 named two untried ideas - a second momentum
horizon scored per sleeve member, and cross-sectional ranking against the sleeve median instead
of the absolute `min_momentum` floor - and this run answers both, plus two variations, on the
honest ETF-9 sleeve with no new data and no survivorship caveat.

**Four levers, all defaulted off, control run first.** `mom_score` (`blend` | `zscore` |
`riskadj`), `mom_confirm`, `entry_mode` (`absolute` | `median`) with `min_rel_momentum`, and the
horizon set itself. LEAN run `20260908T234444Z` at the defaults reproduces
`OrderListHash 9f58b37cc2656b647ec88a5124daf02d`, so the plumbing is provably inert.

**Three of the four are rejected on the sweep** (`sweep_s1.py --mode s9`, full period, against
the champion's CAR 18.7% / Sharpe 0.97 / DD 23.2% / turnover 0.22 in that harness):

| lever | CAR | Sharpe | MaxDD | turn | verdict |
| --- | --- | --- | --- | --- | --- |
| `mom_score=zscore` (equalize horizon scale) | 17.8% | 0.94 | 22.8% | 0.26 | loses both halves |
| `mom_score=riskadj`, 60d vol | 17.6% | 0.93 | 24.4% | 0.21 | loses OOS by 2.1 pts |
| `mom_score=riskadj`, 20d vol | 19.7% | 1.03 | 21.1% | 0.22 | a ridge, see below |
| `mom_confirm` (all horizons positive) | 12.3% | 0.69 | 37.1% | 0.34 | badly worse |
| `entry=median +0%` | 17.9% | 0.94 | 23.4% | 0.22 | loses |
| `entry=median +3%` | 6.4% | 0.41 | 49.2% | 0.31 | catastrophic |

`mom_confirm` fails for a reason worth keeping: demanding agreement across horizons throws the
book out of a trend exactly when the short horizon is mid-shakeout, and it pays 55% more
turnover for the privilege. The median gate fails for the reason the parameter docstring
predicted - with `top_n=3` of nine names the top three always beat the median, so at +0% it is a
*looser* gate that keeps the book in the least-bad ETF through a decline; and asking for real
dispersion (+3%, +8%) strands it in cash through 2012-2019, which is where the -0.7% CAR and
49.2% drawdown come from.

**`riskadj` is a narrow ridge, and the ridge is the interesting part.** Its full-period Sharpe
is monotone in the vol window - 5d 0.91, 10d 0.96, 15d 1.02, 20d 1.03, 30d 0.99, 40d 0.95,
60d 0.93, 120d 0.85 - so only a 15-30 day window beats the champion at all, and it wins entirely
OOS at 15-20 and entirely IS at 30. That inconsistency is the fingerprint of noise, and the
margin (+1.0 CAR, +0.06 Sharpe) is inside the sweep's own known error. Not shipped, kept
available as `mom_score="riskadj"`.

**The fourth horizon is the real finding.** Adding a 250-day member to the blend scored CAR
22.6% / Sharpe 1.10 / DD 21.4% at *lower* turnover (0.16 vs 0.22). The first check made it look
like a fitted spike - a fourth horizon of 200 gives only 19.0%, and 300 returned a tidy 0.0%
CAR. That 0.0% was a **bug in the harness, not a result**: `history_bars` defaults to 300, and a
lookback past 298 makes `target_weights` bail with "only N bars" and hold cash for the whole
sample, silently. `Params.__post_init__` now widens the window to `max(lookback) + 50`, so a
horizon is what is being tested rather than the buffer around it. With that fixed the scan is a
**shelf, not a spike** - full-period Sharpe over the fourth horizon:

| 150 | 180 | 200 | 220 | 240 | 250 | 260 | 280 | 300 | 320 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.85 | 0.96 | 0.96 | 1.01 | 1.07 | **1.10** | 1.04 | 1.04 | 1.03 | 0.88 |

Everything from 220 to 300 beats the champion on CAR, Sharpe *and* drawdown; it collapses at
both edges. **252 sessions is shipped, not the 250 argmax** - one trading year is the a-priori
momentum horizon, it sits inside the shelf, and choosing it costs 0.06 of sweep Sharpe in
exchange for not tuning to the last basis point. Sensitivity holds either side: `top_n` 2/3/4
gives 0.93/1.04/0.98, and removing the crisis-vol filter still costs 12 points of drawdown, so
the S-1 regime overlay is not made redundant by the longer horizon.

**LEAN decides, and it agrees** (run `20260908T235647Z`, shipped default, no env vars):

| | Orders | CAR | Sharpe | MaxDD | Fees | PSR |
| --- | --- | --- | --- | --- | --- | --- |
| champion (20/60/120) | 3,410 | 18.14% | 0.693 | 25.2% | $38,630 | 5.1% |
| **S-9 (20/60/120/252)** | **2,870** | **20.89%** | **0.782** | 28.9% | $37,319 | **10.1%** |
| IS 2012-2019 | 1,551 | 15.18% | 0.701 | 28.9% | | 12.9% |
| OOS 2020-2026 | 1,328 | 28.01% | 0.883 | 21.0% | | 25.7% |

It beats the old champion on both halves (13.5%/0.64 IS and 23.8%/0.76 OOS) and on both
promotion metrics, at 16% fewer orders. `evaluate.py --promote 20260908T235647Z` passed and
**champion.json now points at it**. The economics are the honest attraction: the whole gain
comes with *less* trading, which is the only kind of improvement S-3's 2.1bps-per-turnover cost
floor cannot tax away.

**Two caveats, stated plainly.** Drawdown got worse, 25.2% -> 28.9%, still inside the 35% limit
but with less headroom - and it is all in the 2012-2019 half, where CAR only improved 13.5% ->
15.2%. Most of the headline is the OOS half. And the sweep understated LEAN drawdown by **7.8
points** here (21.1% vs 28.9%), far more than the +2 S-8 calibrated at the champion's size; a
longer horizon holds positions through deeper retracements than the crude sweep cost model
models. Sweeps rank, LEAN decides - again.

**Next.** I-1 is still the gate, and this promotion moves its target: the paper runner's order
list must now be compared against `b763e292cb0eb9a2c81af5739188d437`, not the S-6 hash.
`paper_trade.py --mock --dry-run` re-verified against the new signal and plans XLK/XLE/IWM at
1.50x gross, 0.75 margin.

## 2026-09-08 - S-3: the reversal sleeve is genuinely uncorrelated and genuinely worthless

- **What.** `algorithms/s3_reversal/`, built on the same split as S-1: `signals.py` (plain
  pandas, signed weights, so short = negative) plus `main.py` for LEAN plumbing, and
  `scripts/sweep_s3.py` for the offline walk-forward. Rank the point-in-time top-30 most
  liquid megacaps by trailing k-session return, buy the bottom `n_side`, short the top
  `n_side`, equal dollars per leg, hold one session. The S-1 drawdown overlay, vol helper
  and Reg-T margin table are *imported* from the S-1 module, not copied - loaded by path
  under the alias `s1_signals`, because this file is also called `signals` and a plain
  import from the sibling directory returns itself.
- **Why.** S-8 closed with the measurement that the ETF-9 sleeve cannot be pushed past
  ~20% realized vol inside the 35% drawdown limit by any amount of leverage. If the
  mandate is reachable at all, it is reachable by *adding uncorrelated return streams*.
  So the number that decides S-3 is the correlation with the champion, and the Sharpe
  second.

### The correlation is exactly what was hoped for

| | corr with champion | 50/50 blend Sharpe | blend vol | blend MaxDD |
| --- | --- | --- | --- | --- |
| S-3 reversal, zero cost | **-0.026** | 0.97 | 11.5% | 12.0% |
| S-1 champion alone | 1.000 | 0.97 | 19.8% | 23.2% |

A dollar-neutral single-name book really is orthogonal to a levered ETF momentum book.
The blend keeps the champion's Sharpe and halves its volatility - which is the *wrong*
direction for this mandate, and only because the sleeve added is a zero-return one. The
orthogonality is the finding worth keeping for S-5; the sleeve is not.

### There is no edge to allocate to, before costs and in both directions

30 configurations (lookback 1/2/3/5/10 x n_side 3/5/10 x vol-adjusted or raw), **all at
zero trading cost**, so this measures the signal and nothing else:

| | best cell | median cell | worst cell |
| --- | --- | --- | --- |
| Sharpe, zero cost | +0.27 | -0.11 | -0.72 |

24 of the 30 cells are negative and no cell reaches Sharpe 0.3. The shipped defaults are the *best* cell
(lookback 5, n_side 10, no vol adjustment), chosen with hindsight over the full sample, so
that what follows rejects the hypothesis at its strongest rather than at an unlucky
parameter. Two systematic patterns, both against the hypothesis: n_side 10 beats n_side 3
at every horizon, so the extreme movers are the *worst* part of the cross-section, not the
best; and the raw ranking beats the vol-adjusted one, so what little signal exists is a
vol effect rather than a reversal effect.

Splitting that best cell in half kills it:

| direction | window | CAR @0bps | Sharpe @0bps | CAR @5bps | Sharpe @5bps |
| --- | --- | --- | --- | --- | --- |
| reversal | IS 2012-2019 | +6.2% | 0.64 | -5.8% | -0.56 |
| reversal | OOS 2020-2026 | -1.1% | -0.01 | -11.0% | -0.71 |
| continuation | IS 2012-2019 | -6.0% | -0.58 | -16.6% | -1.88 |
| continuation | OOS 2020-2026 | -1.4% | -0.02 | -9.5% | -0.71 |

The entire zero-cost edge is in-sample, in a cell picked by looking at the full sample. And
flipping the sign - the obvious response to 25 negative cells - is not an edge either: the
mirror image is negative in-sample and flat out-of-sample. Both directions are inside the
noise, which is the honest reading of a cross-section that is 30 daily-rebalanced pairs of
megacaps.

### LEAN confirms, and LEAN is the *optimistic* number here

Run `20260908T224519Z`, 2012-01-03 .. 2026-09-04, shipped defaults:

| | CAR | Sharpe | MaxDD | Orders | Fees | Vol | Beta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S-3 | -0.14% | -0.19 | 48.6% | 44,353 | $64,721 | 10.1% | 0.07 |

Beta 0.07 and `mean_abs_net = 0.0000` at decision time (max 0.094 carried, from drift
between rebalances) - the book is dollar-neutral as designed, and max margin used 0.792
against a 0.75 budget, the same small overshoot S-1 shows. **$64,721 of commission on a
$100,000 account**: 4.4% of equity a year, which on 209 turnover units a year is 2.1bps per
unit of turnover. That is commission *only* - LEAN's IB model charges no spread and no
impact, so the honest cost is higher than the one that already ate the whole return. The
sweep's 5bps assumption is the realistic end and it gives -9.0% CAR.

- **Decision.** **No promotion; champion unchanged.** `evaluate.py` refused on all four
  grounds it has: the `not promotable` tag, 48.6% drawdown over the limit, Sharpe and CAR
  both below the champion. S-3 is closed negatively.
- **What it costs to have learned this.** Two things are now measured rather than assumed.
  (1) Daily-rebalanced single-name pairs cannot pay for themselves on a $100k account: 2.1bps
  of pure commission per unit of turnover against a gross edge of at most 2.6% a year. Any
  future sleeve that turns the book over daily has to clear roughly 5% a year gross before
  it is worth running at this account size. (2) The market-neutral construction *does*
  deliver orthogonality (-0.03), so S-5 remains a live idea - it just needs a sleeve with a
  return.
- **Also worth noting the bias that did not matter.** The megacap pool is a 2026 survivor
  list, and reversal is the strategy that survivorship flatters most (buying the biggest
  loser only pays if the loser comes back, and everything on disk came back). The result is
  negative *anyway*, so the delisted-data blocker did not need resolving to close this one.
- **Next.** Open strategy work is now S-2 (opening-range breakout), which is blocked on
  intraday data, which is blocked on the IB Gateway login - the same human gate as I-1. The
  loop's remaining unblocked lever is a different *signal* on daily bars for the ETF sleeve,
  not another sizing or universe change.

## 2026-09-08 - S-8: four ways to buy drawdown headroom, all four rejected, and the mandate is measured as unreachable

- **What.** The S-8 question: reach the 40-60% volatility mandate without breaching the 35%
  drawdown limit. Four levers, three of them new code in `signals.py`, every one defaulted
  off so the champion is untouched - `margin_budget_cap`/`margin_budget_floor` (an elastic,
  vol-responsive margin budget), `trail_stop`/`trail_window` (a stateless per-holding trailing
  stop), and `dd_mode="taper"` (a continuous drawdown overlay instead of the 1.0/0.5/0.0 step).
  Swept with `scripts/sweep_s1.py --mode s8` and `--mode s8vol`, then the two survivors
  confirmed in LEAN.
- **Why.** S-6 left the constraint on the drawdown limit rather than on execution: budget 1.0
  buys 2.07x exposure and 20.4% CAR but 35.4% drawdown. More size has to be *paid for*.

### The control is clean

Run `20260908T213829Z` at champion defaults reproduces `OrderListHash
9f58b37cc2656b647ec88a5124daf02d` and every statistic. Three new parameters, zero behaviour
change.

### 1. `top_n=5-6` does not survive the size increase

S-7 measured `top_n=6` as cheaper in drawdown at equal return, and the backlog told S-8 to
start there. At the champion's budget that is true; at budget 1.0 it inverts:

| top_n, budget=1.0 | full CAR | Sharpe | MaxDD | Vol |
| --- | --- | --- | --- | --- |
| 3 | **22.4%** | **0.95** | 27.4% | 24.4% |
| 5 | 19.4% | 0.88 | 27.4% | 23.3% |
| 6 | 20.4% | 0.92 | 29.9% | 23.0% |

The headroom S-7 found was a property of a small book, not of the wider one. Rejected.

### 2. An earlier breaker is dominated by simply carrying less size

| dd_halve/dd_flat, budget=1.0 | full CAR | Sharpe | MaxDD |
| --- | --- | --- | --- |
| 0.15/0.25 (shipped) | 22.4% | 0.95 | 27.4% |
| 0.10/0.25 | 16.6% | 0.81 | 23.3% |
| 0.08/0.20 | 16.3% | 0.82 | 22.3% |

Tightening to 0.10/0.25 lands on 16.6% CAR at 23.3% drawdown. The champion, in the same
harness, gets 18.7% at 23.2%. So the tighter breaker is strictly worse than turning the size
back down - it is a more expensive way to buy the same drawdown. Rejected.

### 3. The continuous taper re-creates the 2015 absorbing state

Full period **CAR -0.2%**, exposure 0.21x, invested 53.8% of days. The mechanism is exactly
the bug the journal already records once: the high-water mark only resets on a hard `dd_flat`
breach. A taper asymptotes to zero exposure *just below* `dd_flat`, so the breach never
happens, the peak never resets, and a book earning nothing can never climb back out. The step
function's brutality is load-bearing - it forces the hard breach that resets the mark.
Rejected, and worth keeping as the second instance of the same failure mode.

### 4. The trailing stop does not touch drawdown at all

Five (stop, window) settings, and `MaxDD` is 27.4% in every one of them, against 27.4% with
no stop. Portfolio drawdown here comes from the levered index proxies falling *together*, not
from one holding breaking down, so a per-name stop has nothing to bite on. Rejected.

### 5. The elastic budget: the diagnosis was right, the fix is a size dial

The first sweep showed the elastic budget doing almost nothing, and the reason is a real
finding about the shipped champion: **the vol target has never been active.** The book
realizes ~24% vol against a 40% target, so `target_vol / sigma` sits above every ceiling on
essentially every day, and the strategy therefore carries a *constant* margin through every
regime. Lowering the target to something reachable makes it bind - and that does trace a
better frontier in the sweep. But confirmed in LEAN it collapses:

| LEAN run | Vol | CAR | Sharpe | MaxDD | Orders | Fees |
| --- | --- | --- | --- | --- | --- | --- |
| champion, flat budget 0.75 | 16.5% | **18.1%** | **0.693** | 25.2% | 3,410 | $38,630 |
| elastic [0.2,1.0], tv=26% (`214625Z`) | 17.1% | 16.3% | 0.604 | 24.6% | 4,427 | $37,910 |
| elastic [0.2,1.0], tv=32% (`214218Z`) | 19.4% | 19.7% | 0.674 | 34.3% | 4,307 | $54,498 |
| flat budget 1.0 (S-6, measured) | 20.6% | 20.4% | 0.672 | 35.4% | 4,146 | $55,171 |

The matched-risk row is the verdict. At 17.1% vol against the champion's 16.5% - the same
risk - the elastic budget returns 1.8 points *less* and gives up 0.09 of Sharpe, while placing
30% more orders on a *smaller* book. A budget that moves with the vol estimate re-sizes the
whole portfolio every day, and daily rotation of 3x ETFs cannot afford that. It is a size
dial, not a shape improvement: at tv=32% it lands on the same frontier point as flat 1.0
(19.7%/0.674/34.3% against 20.4%/0.672/35.4%) - a hair less drawdown for a hair less return.

### The harness lied about drawdown, and it lies more as size goes up

Worth recording as a calibration, because every future sweep depends on it:

| config | sweep MaxDD | LEAN MaxDD | gap |
| --- | --- | --- | --- |
| champion (exp 1.62x) | 23.2% | 25.2% | +2.0 |
| elastic tv=32% (exp 1.94x) | 24.6% | 34.3% | +9.7 |
| flat budget 1.0 (exp 2.06x) | 27.4% | 35.4% | +8.0 |

`sweep_s1.py`'s flat 2bps turnover charge is fine for *ranking* at fixed size and badly
optimistic across size: it also scored the tv=26% elastic config at Sharpe 0.97, level with
the champion, where LEAN says 0.604 against 0.693. The docstring already says "choose here,
confirm in LEAN"; this is the magnitude of why.

- **Decision.** **No promotion; champion unchanged** (`evaluate.py` refused both candidates,
  on Sharpe for `214218Z` and on Sharpe *and* CAR for `214625Z`). The new parameters stay in
  the code, defaulted off and documented, because they are the evidence.
- **S-8 is closed, and it closes into a human decision.** The measured LEAN frontier above
  says the drawdown limit is already binding at 19-20% realized vol. The mandate asks for
  40-60%, roughly double again, which on this universe means a drawdown far past 35%. The two
  are not simultaneously reachable on the ETF-9 sleeve by any of the four levers, so this is
  now a risk-budget decision, filed in `BLOCKERS.md`. **Nothing about I-1 moves**: the
  champion's order list is unchanged and the paper deadline is untouched.
- **Next.** With S-8 closed, the open strategy work is a *different signal* rather than a
  different size: S-3 cross-sectional short-term reversal is the next sleeve, and it is the
  one that could raise vol by adding an uncorrelated return stream instead of leverage.
  I-1 remains the deadline gate and is still blocked on the IB Gateway login.

## 2026-09-08 - D-3 point-in-time universe: the timing bias is gone, the pool bias is 90% of it

- **What.** `algorithms/s1_momo/universe.py`: membership decided on each rebalance date from
  the trailing 60-day *median* dollar volume of bars already on disk, top N, with a 252-session
  minimum history. Wired into `signals.Params` as `universe_size` (0 = the fixed sleeve the
  champion ships, so the default is unchanged), into `main.py` behind `S1_UNIVERSE_SIZE`, and
  into `scripts/sweep_s1.py --mode d3`. `lean_prices.load_frames` now returns volume beside
  the adjusted closes.
- **Why.** S-7 printed CAR 43.9% by ranking the megacaps *of 2026* back to 2012. The backlog
  asked for the cheapest honest universe that needs no new data source, and liquidity is what
  the mandate cares about anyway.

### The selection is real, and it moves

Straight from the run log, 20 names picked out of the 59-name pool:

| as of | sleeve |
| --- | --- |
| 2012-12-31 | SPY AAPL IWM QQQ GOOGL **BAC** MSFT GLD **XOM** INTC **JPM** **GE** XLF XLE **WFC** AMZN **IBM** JNJ DIA **PFE** |
| 2024-12-02 | SPY TSLA QQQ **NVDA** AAPL **AMD** MSFT AMZN META IWM GOOGL **AVGO** ORCL GLD MU NFLX INTC LLY UNH DIA |

47 different names are selected at some point, 458 entries and exits, and only 10 of the 20
seats are held by the same ticker in 2026 as in 2012. The 2012 sleeve is full of the banks and
oil majors that then underperformed for a decade, which is exactly what a list built without
hindsight should look like.

### But the honest control says it barely helped

| passive, equal weight, 2012-2026 | CAR | Sharpe | Vol |
| --- | --- | --- | --- |
| EW 50 megacaps, 2026 list (S-7's control) | 22.8% | 1.27 | 17.4% |
| **EW top-20 point-in-time (D-3)** | **22.0%** | 1.09 | 20.2% |
| SPY buy & hold | 15.0% | 0.93 | 16.5% |

Point-in-time selection gives back **0.8 points of the 7.8** by which the biased basket beats
SPY. The remaining 7.0 are not a timing problem and D-3 cannot touch them: `fetch_data.py`
downloaded 69 tickers *that exist in 2026*, so Sprint, Yahoo, EMC and Dell were never
candidates in 2012 no matter what their dollar volume was, and those are disproportionately
the names that later failed. **About 90% of the universe bias is in the file, not in the
ranking date.** Promoted to a decision item in `BLOCKERS.md`.

### And the signal still does not beat its own sleeve

LEAN, run `20260908T203212Z`, `S1_SLEEVE=wide S1_UNIVERSE_SIZE=20 S1_TOP_N=3`:

| | CAR | Sharpe | MaxDD | Orders | Fees | PSR |
| --- | --- | --- | --- | --- | --- | --- |
| D-3 point-in-time sleeve | 32.1% | 0.90 | 32.3% | 4,816 | $69,571 | 16.8% |
| champion (fixed ETF-9) | 18.1% | 0.69 | 25.2% | 3,410 | $38,630 | 5.1% |
| *its own passive sleeve* | *22.0%* | *1.09* | *34.0%* | *0* | *~0* | - |

+14.0 points of CAR over the champion, and it clears QQQ's 19.9% - the thing S-7 wanted. It is
still not a win. Against the sleeve it actually trades, the strategy adds 10.1 points of CAR at
1.25x the vol and **gives up 0.19 of Sharpe** once LEAN's commission model is applied rather
than the sweep's flat 2bps. Buying the same 20 names and doing nothing is the better
risk-adjusted trade. That is the same verdict S-7 reached on the biased sleeve, and it survives
the fix - so the momentum ranking's edge over a liquid large-cap basket is leverage, not skill.

- **Decision.** **No promotion; champion unchanged.** The run is tagged `not promotable`
  and `evaluate.py` refused it on that tag alone - worth noting that it passed every
  statistical rule (32.3% drawdown inside the 35% limit, 4,816 orders, wins both must-beat
  metrics), so the E-3 guard is the only thing standing between a future session and a
  survivorship artifact. The control run `20260908T202809Z` reproduces
  `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`, so plumbing volume through `main.py`
  changed nothing the champion trades.
- **S-7 is closed, negatively.** All three named levers are now answered: momentum-proportional
  weighting loses, `top_n` is flat, and a wider sleeve wins only on borrowed vol and a
  survivor pool. Beating buy-and-hold on absolute return is not a universe problem.
- **I-1 untouched by design.** `paper_trade.py` calls the signal by introspecting its
  parameters and would simply not pass `volumes`; with the champion at `universe_size=0` that
  is correct behaviour, not a gap. If a point-in-time sleeve is ever promoted, the runner needs
  `fetch_history_yf` to return volume too and `call_signal` to forward it - deliberately not
  done today, two days before the paper deadline, for a code path nothing uses.
- **Next.** S-8 on the ETF-9 sleeve, which is the only universe here without a selection
  story: reach the volatility mandate by earning drawdown headroom (start from `top_n=5-6`),
  not by asking for size.

## 2026-09-08 - S-7 beat buy-and-hold: two levers rejected, one is a mirage

- **What.** The three S-7 candidates for beating QQQ's 19.9% CAR, tested on both sub-periods
  with `scripts/sweep_s1.py --mode s7`: momentum-proportional weighting, a wider `top_n`, and
  widening the ranking sleeve to the 50 megacaps D-1 put on disk. `signals.py` gained two
  parameters for it - `rank_universe` and `weight_mode` (`equal` / `rank` / `momentum`) - and
  `main.py` gained `S1_SLEEVE` and `S1_WEIGHT_MODE`.
- **Why.** S-1 clears SPY (18.1% vs 15.0%) but not QQQ, and the backlog named these three.

### 1. Momentum-proportional weighting loses, on both halves

| weight_mode | IS CAR | OOS CAR | full CAR | full Sharpe | full MaxDD |
| --- | --- | --- | --- | --- | --- |
| equal (shipped) | 16.3% | 21.5% | **18.7%** | **0.97** | 23.2% |
| rank | 12.1% | 20.2% | 15.8% | 0.81 | 24.4% |
| momentum | 11.6% | 21.5% | 16.1% | 0.83 | 25.9% |

Concentration costs 2.6-2.9 points of CAR and ~0.15 Sharpe, and it is *in-sample* that it
loses most, so this is not a regime accident. Rejected; `weight_mode` stays `equal`.

### 2. top_n=3 survives, but 5-6 is the interesting neighbour

| top_n | IS CAR | OOS CAR | full CAR | full Sharpe | full MaxDD | vol |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 10.8% | 15.9% | 13.2% | 0.69 | 24.4% | 21.4% |
| 3 | 16.3% | 21.5% | **18.7%** | 0.97 | 23.2% | 19.8% |
| 4 | 15.4% | 19.6% | 17.3% | 0.93 | 22.3% | 19.1% |
| 5 | 13.9% | 21.1% | 17.2% | 0.94 | 22.1% | 18.7% |
| 6 | 14.7% | 20.8% | 17.5% | **0.97** | **22.0%** | 18.4% |

The earlier "top_n=3 is a local peak" caution is only half right: 3 wins on return, but the
curve from 4 to 6 is flat and monotonically *cheaper* in drawdown and vol (OOS drawdown falls
16.7% at top_n=6 against 23.2% at 3, with equal Sharpe). No change to the champion, but this
is a lead for S-8: the binding constraint there is the 35% drawdown limit, and a wider book
buys drawdown headroom that the margin budget could then spend on size.

### 3. The wide sleeve is a survivorship mirage, and the harness could not see it

Adding the 50 megacaps to the ranking sleeve produces the best number this repo has ever
printed. LEAN, run `20260908T192552Z`, `S1_SLEEVE=wide S1_TOP_N=5`:

| | CAR | Sharpe | MaxDD | Orders | Fees | PSR |
| --- | --- | --- | --- | --- | --- | --- |
| wide sleeve | 43.9% | 1.19 | 32.2% | 7,830 | $243,278 | 52.5% |
| champion (ETF-9) | 18.1% | 0.69 | 25.2% | 3,410 | $38,630 | 5.1% |

`scripts/evaluate.py --candidate` said **BEATS champion**: 32.2% drawdown is inside the 35%
limit, 7,830 orders clears 30, and it wins on both must-beat metrics. It is still not real.
`MEGACAP_SLEEVE` is the megacap list *as of 2026*, so ranking it back to 2012 knows in advance
which fifty companies were going to survive and win. The two obvious defences both fail:

* **The IS/OOS split does not detect it.** IS 50.2% CAR vs OOS 54.3% - the halves agree,
  because the hindsight is in universe construction and is therefore spread evenly across
  the whole sample rather than fitted to one end of it.
* **It is not a late-IPO artifact.** Only 4 of the 50 (META, ABBV, NOW, UBER) listed after
  2012-01-03, and dropping them changes almost nothing (44.4% -> 41.8% CAR in the sweep,
  and 22.8% -> 22.4% for the passive basket).
  The bias is in *which names were on the list at all*.

The control that does work is holding the same universe passively
(`scripts/sweep_s1.py --mode s7bias`, 2012-2026):

| | CAR | Sharpe | Vol |
| --- | --- | --- | --- |
| SPY buy & hold | 15.0% | 0.93 | 16.5% |
| EW 50 megacaps (2026 list), no skill at all | **22.8%** | **1.27** | 17.4% |
| momentum top_n=5 on that same sleeve | 44.4% | 1.37 | 30.3% |

So simply *owning* the 2026 megacap list from 2012, equal weighted, beats SPY by 7.8 points
of annual return with a higher Sharpe than the strategy. Against its own basket the signal
adds +21.6% CAR at 1.74x the vol - which is very close to what levering the basket would
give - and only +0.10 Sharpe. Essentially all of the headline uplift is the universe and the
leverage; almost none of it is the ranking.

- **Decision.** **No promotion**, and the champion is unchanged. Rather than rely on
  remembering why, `evaluate.py` now refuses to promote any run whose tag contains
  `not promotable`, and the S-7 run is tagged that way - a later session reading the ledger
  cold would otherwise find a run that passes every statistical rule. The new
  `rank_universe` / `weight_mode` parameters ship defaulted to the current behaviour: the
  control run `20260908T192208Z` reproduces `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`,
  byte-identical to the champion's order list, so the refactor changed nothing that trades.
- **What S-7 actually needs.** A point-in-time universe: membership decided from information
  available on each rebalance date (index membership as of that date, or a rolling
  dollar-volume rank recomputed daily from bars already on disk), not a list downloaded in
  2026. The second option needs no new data source and is now backlog **D-3**. Until then the
  answer to "can a wider sleeve beat QQQ" is unknown, not yes.
- **Next.** D-3, which unblocks S-7 properly; S-8 can start from top_n=5-6 for drawdown room.
  I-1 remains the deadline gate and is still blocked on IB Gateway (`research/BLOCKERS.md`).

## 2026-09-08 - S-6 margin-budget sizing (new champion, exposure 1.27x -> 1.63x)

- **Hypothesis.** S-1's size was limited by a flat `max_gross_weight = 1.0`, which was never
  a risk preference - it was a workaround for LEAN charging un-netted initial margin on both
  legs of a MarketOnOpen rotation. With that execution problem already fixed (netted share
  deltas, sells first, daily-bar rebalance), replacing the flat cap with the constraint a
  broker actually enforces should buy materially more exposure at the same risk.
- **What.** `signals.py` now caps on `sum(weight_i * MARGIN_REQ[i]) <= margin_budget`, where
  `MARGIN_REQ` is Reg-T 50% for an ordinary ETF and 100% for a 3x ETF (IBKR multiplies the
  requirement by the leverage factor). `max_gross_weight` demotes to a hard notional ceiling
  at 2.0. `main.py` audits realized initial margin daily alongside gross. `sweep_s1.py`
  gained `--mode margin`. `paper_trade.py` gained an independent `MAX_MARGIN_USED = 1.0`
  backstop that aborts before sending orders, so a signal bug cannot silently place size.
- **Why this is not just "turn the leverage up".** The cap is asymmetric in exactly the way
  a real account is: three unlevered winners can now run at 1.5x gross, while three 3x ETFs
  are still held to 0.75x gross. The old flat cap punished the *safe* basket and let the
  levered one through, which is why mean effective exposure sat at 1.27x.

### Result (LEAN, `20260908T182554Z`, 2012-01-03 .. 2026-09-04)

| Window | CAR | Sharpe | MaxDD | Orders | Fees |
| --- | --- | --- | --- | --- | --- |
| Full 2012-2026 | **18.1%** | **0.69** | 25.2% | 3,410 | $38,630 |
| IS 2012-2019 | 13.5% | 0.64 | 25.2% | 1,776 | $22,062 |
| OOS 2020-2026 | 23.8% | 0.76 | 24.8% | 1,637 | $6,348 |

Against the outgoing champion: CAR 13.7% -> 18.1%, Sharpe 0.60 -> 0.69, drawdown 23.6% ->
25.2%, mean effective exposure 1.27x -> 1.63x, realized vol 13.3% -> 16.5%. Both sub-periods
improve, and out-of-sample is again the stronger half. Audit: max initial margin actually
carried 0.793 against a 0.75 budget (the 6% overshoot is intraday drift between the decision
close and the next open, not a sizing error), max gross 1.536 against the 2.0 ceiling.

- **Where the budget was set, and why not higher.** `--mode margin` shows return flat above
  budget 1.0 - `scale_cap = 2.0` binds first, so budgets of 1.0, 1.25, 1.5 and 2.0 all land
  on the same book. The full Reg-T budget of 1.0 *does* hit S-6's stated 2x target (LEAN:
  2.07x mean exposure, CAR 20.4%, Sharpe 0.67) but posts a **35.4% drawdown, over the 35%
  limit in `champion.json`**, so it is not promotable. 0.75 is that limit respected with a
  buffer, not a fitted optimum: a book sitting at a full budget has zero excess liquidity and
  any adverse move is a margin call. Both runs are in the ledger; the 1.0 result is the
  measured edge of the risk limit, recorded so the next iteration does not re-derive it.
- **Decision.** Promoted through `scripts/evaluate.py` (3,410 orders, drawdown 25.2% < 35%,
  beats the champion on both Sharpe and CAR). The default `margin_budget = 0.75` is set in
  the code, not passed by environment variable: a confirmation run with no env produced the
  identical `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`, so the champion reproduces from
  a clean checkout, and `paper_trade.py --mock --dry-run` now plans the same 1.5x gross book.
- **Honest limits.** 16.5% realized vol is still far short of the 40-60% mandate; the binding
  constraint has moved from the gross cap to `scale_cap` and the drawdown limit, which is a
  risk-budget conversation, not an execution bug. Fees grew $27k -> $39k on 12% more orders.
  It now beats SPY on return (18.1% vs 15.0%) but still not QQQ (19.9%), so S-7 stays open.
- **Next.** I-1 remains the deadline gate and is still blocked on IB Gateway being logged in.

## 2026-09-08 - S-1 volatility-regime momentum rotation (first champion)

- **What.** `algorithms/s1_momo/`, split into `signals.py` (plain pandas, prices in, target
  weights out) and `main.py` (LEAN plumbing only), so the I-1 paper runner can import the
  identical decision code. Supporting tools: `scripts/lean_prices.py` reads LEAN's own zips
  and factor files back into a DataFrame, and `scripts/sweep_s1.py` walks the shipped signal
  day by day outside the engine (~25s a config vs ~3.5 min for a LEAN run).
- **Why.** Top backlog item and the gate on the 2026-09-10 paper-trading objective.

### Two parts of the specified hypothesis did not survive contact with the data

1. **The regime filter as written is anti-predictive.** S-1 called for risk-on while 20-day
   realized vol sits below its 1-year median. On 2012-2026 SPY returns 4.7%/yr (Sharpe 0.58)
   on those "calm" days and 10.0% (Sharpe 0.75) on the days the filter excludes - vol peaks
   coincide with the sharpest rebounds. Applying it costs 13 points of annual return
   (18.8% -> 5.8% CAR). Replaced with a *crisis* filter: risk-off only once vol exceeds
   1.5x its median.
2. **A 200-day trend filter, the obvious substitute, also loses** - and loses on both halves
   independently (IS 14.7% vs 16.7% CAR, OOS 15.5% vs 21.2%), while buying no drawdown. Kept
   as an option, defaulted off. Deciding this on both sub-periods rather than the full sample
   is what makes it a finding rather than a fit.

### Three execution bugs, each of which silently faked a result

The signal was right early; every bad number came from execution. Worth recording because
they are all invisible in the summary statistics:

| Symptom | Cause |
| --- | --- |
| Stopped trading permanently in 2015 | "Flat until a new equity high" is an absorbing state - a flat book cannot print a high. |
| Every parameter set collapsed onto DD ~25% with erratic returns | Adding a cooldown but keeping the watermark: the breaker re-armed on release and traded 1 day in 22. Fixed by resetting the high-water mark when the breaker releases. |
| 9,095 orders, zero fills | Daily bars leave the exchange looking shut, so market orders degrade to MarketOnOpen, which IB rejects outside 04:00-09:28. |
| DD 87.5% at gross 1.3, then 57.6% at 1.0 | `set_holdings(PortfolioTarget(...))` sizes against *buying power*, so account leverage multiplies every target: same signals gave 27% vol at 2x and 43% at 4x against 16% on paper. Replaced with explicit share math. |
| Account wiped to $1.18, 264%/day turnover, 12.7x gross | MOO orders sent at 09:00 on day D were still unfilled at 09:00 on day D+1, so each rebalance read stale zero holdings and stacked another full target. Fixed by rebalancing on the daily bar, so one order batch is in flight at a time. |

The last one only became visible because `on_data` audits gross exposure actually carried
against the cap. That audit is now permanent; without it the blowup looked like a bad signal.

### Result (LEAN, `20260908T174548Z`, 2012-01-03 .. 2026-09-04)

| Window | CAR | Sharpe | MaxDD | Orders | Fees |
| --- | --- | --- | --- | --- | --- |
| Full 2012-2026 | 13.7% | 0.60 | 23.6% | 3,033 | $27,118 |
| IS 2012-2019 | 10.4% | 0.57 | 23.6% | 1,665 | $18,307 |
| OOS 2020-2026 | 17.8% | 0.64 | 20.8% | 1,373 | $4,200 |

Out-of-sample is the *stronger* half, which is the right direction for an honest fit.
Audited max gross carried 1.047 against a 1.0 cap, zero buying-power rejections, 83.7% of
days invested, mean effective exposure 1.27x.

Sensitivity (`--mode sensitivity`, +/-25% shocks): drawdown is robust, staying in 18.0-22.4%
across every shock. Return is not uniformly robust - halving the distance of the vol
threshold toward the median drops CAR to 7.7%, and `top_n=3` is a local peak (2 -> 10.2%,
4 -> 13.5%). No shock produces a loss or breaches the drawdown limit.

- **Decision.** Promoted to champion through `scripts/evaluate.py` (3,033 orders >= 30,
  drawdown 23.6% < 35%, no incumbent to beat). **It is a baseline, not a win.** Over the same
  period SPY compounds at ~15.0% and QQQ at ~19.9%, so S-1 does not beat buy-and-hold on
  absolute return; what it buys is drawdown, 23.6% against SPY's 33.7% and QQQ's 35.1%. It
  also does not meet the aggressive mandate: 13.3% realized vol, nowhere near the 40-60%
  target. Beating QQQ on return is the bar for the next champion.
- **Why it is not more aggressive.** Gross weight is capped at 1.0 because orders are
  MarketOnOpen and a rotation has both legs outstanding at once. At gross 1.3 LEAN rejected
  3,004 of 3,690 rebalances for buying power. Leverage is therefore limited to what is inside
  the 3x ETFs, and the vol target is inert - the gross cap binds first, which is why
  `target_vol` and `target_exposure` shocks move nothing. The risk control that actually
  works is the crisis filter plus the drawdown breaker.
- **Next.** I-1: the paper runner against IBKR, importing `signals.py` unchanged. The
  execution constraint above is the thing to fix to raise exposure, and it is an execution
  problem, not a signal problem.

## 2026-09-08 - D-1 data pipeline (yfinance daily stopgap)

- **What.** Wrote `scripts/fetch_data.py`: fetches daily bars and writes LEAN-format
  `daily/<sym>.zip`, `map_files/<sym>.csv` and `factor_files/<sym>.csv` into
  `..\Lean\Data\equity\usa\`. Universe is the 19 ETFs from the backlog plus 50 megacaps
  (69 symbols, 1998-01-01 to 2026-09-04, ~430k bars). Existing LEAN sample files are
  backed up to `<name>.orig` before the first overwrite.
- **Why.** Every strategy result so far was a mechanics check on one sample week of SPY.
  Nothing in the backlog can be tested as alpha until real history exists.
- **Adjustment model.** Yahoo's OHLC are already split-adjusted, so the split factor stays
  1 and dividends are carried entirely by the price factor, accumulated backwards from 1
  as `(1 - D / C_prev)` per ex-date.
- **Two bugs the acceptance test caught, both silent:**
  1. Deriving factors from the `Adj Close / Close` ratio looks equivalent but Yahoo rounds
     `Adj Close`, so the ratio wobbles in the 7th decimal daily. SPY got 5490 factor rows
     instead of 117. Fixed by using explicit dividends.
  2. A symbol with no dividends produced a factor file containing only the `20501231`
     sentinel row, and **LEAN silently returned zero bars for it** - no error, no failed
     data request. GLD, UVXY and BRKB were dropped from the first smoke run this way.
     Fixed by always emitting a listing row at the first bar date; the validator now
     rejects a sentinel-only file.
  Also: Yahoo's bar for the in-progress session has `high < open`, so the default end date
  is now today (exclusive), with a clamp-and-report fallback for residual bad bars.
- **Result.** `d1_data_smoke` (20260908T162819Z) reports PASS: all 15 probed symbols deliver
  3690 bars over 2012-01-03 .. 2026-09-04 with no malformed bars. Independent checks: the
  computed factors agree with Yahoo's own `Adj Close` to within 0.003% worst-case across all
  69 symbols, and raw closes match known values (AAPL 2020-08-31 = 129.04, SPY 2020-03-23 =
  222.95, NVDA 2024-06-24 = 118.11).
- **Decision.** No champion. The run's headline numbers (8660% net profit, CAR 35.6%,
  Sharpe 0.80, drawdown 72.7%, 14 orders) are equal-weight buy-and-hold of 15 tickers
  including TQQQ/SOXL/UVXY across a 14-year bull run - a coverage probe, not a strategy.
  `evaluate.py` correctly refused it (14 orders < 30, drawdown 72.7% > 35%).
- **Next.** S-1 volatility-regime momentum rotation, which now has the ETF history it needs.
  Daily bars only: S-2 opening-range breakout still has no intraday data (see D-2).

## 2026-09-08 - Toolchain bring-up

- Built LEAN natively (.NET 10 SDK, Python 3.11, pythonnet) because Docker and WSL2 are
  unavailable on this machine.
- `python scripts/backtest.py _template` ran the SPY buy-and-hold template on the bundled
  sample week (2013-10-07 to 2013-10-11): 1 order, net profit 1.692%, Sharpe 8.85 on five days,
  which is meaningless as alpha and only proves the pipeline works.
- Decision: no champion yet. Next step is backlog D-1 (data pipeline); without real data every
  strategy result is a mechanics check, not evidence.
