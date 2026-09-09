# Research journal

Newest entry first. Each entry: what was tried, why, the result, the decision, the next step.

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
