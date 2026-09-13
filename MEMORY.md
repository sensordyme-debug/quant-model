# MEMORY.md - Durable decisions and facts

Long-lived facts the loop should not have to rediscover. Newest section first.
Daily raw notes live in `memory/YYYY-MM-DD.md`.

## A screen must be scored on data its own threshold never saw (learned 2026-09-13, F-16 -> F-17)

- **A train-window |IC| or |t| floor is an ANTI-selector once candidates come from stores with
  different regime exposure.** F-17 handed F-16's gate 17 parents from two disjoint stores. It
  admitted the five columns with the largest in-window |IC| (|t| 5.7-7.7) and **every one lost**;
  the three weakest (|t| 2.1-2.9) made all the money, and **the two ranges do not overlap**. The
  mechanism: a large in-window |t| on a store whose span contains one regime break is a measurement
  of that break, not of skill. `amihud30` and `ofi5` scored |t| 6.8 on 2016-2019 and lost $974/day
  in 2020. Any future screen must rank a candidate on data the floor did not read.
- **An abstention rate is a result, not a knob to minimise.** Same gate, same threshold, wider pool:
  abstained in 2 of 8 windows instead of 5, and lost $112/day for it ($412 -> $310). Report it, and
  treat a gate that became more active as a gate that got worse until shown otherwise.
- **Print the scramble control's NET, not only its paired t against base.** F-17's pooled arm beat
  base on gross *and* on paired t and still finished **below its own information-destroyed scramble**
  ($310 vs $319). A run that compared each arm only to `base` would have reported it harmless.

## A number quoted from a table is only a comparison if the rows share a session count (learned 2026-09-13, S-40 -> S-41; second instance of S-38 -> S-40)

- S-41 was opened on "the blend carried the best Sharpe 1.173 against the shipped cell's 1.159".
  The blend row was **2,684 sessions** (a walk-forward span) and the 1.159 was **3,689** (FULL).
  Span-matched, the shipped cell is **1.228** and the blend 1.174 - the claim reversed and was
  withdrawn. The drawdown half of the same sentence survived only because the 2020 crash lies inside
  both spans. **Before comparing two rows, print both session counts.** This shape has now bitten
  twice in one month on the same sleeve.
- Related, and it is a separate fact: **a promotion gate and a decision are different instruments.**
  The blend fails against the incumbent on CAR and Sharpe, and beats what a real-time selector
  actually gets by **+1.6 CAR / +0.16 Sharpe / -14.9 drawdown points**, because S-40 showed a
  walk-forward argmax picks the shipped cell in **0 of 11 years**. Both sentences are true.

## Re-quoting a gate number is not running a gate (learned 2026-09-13, C-6)

- `scripts/paper_trade.py` could not import for 83 minutes and **two commits reported its deploy
  gate passing in that window**, quoting a number that was true when measured and unreproducible at
  the HEAD they claimed it for. **If an entry claims a gate passed, the run must post-date the HEAD
  it claims.**
- **A sys.path guard is ordering-sensitive code.** The guard was already in the file, 15 lines
  *below* the `from quant_brain...` import it was written to protect. It must sit above the imports
  it protects, with a comment saying so, or the next import sort silently undoes it.
- **`tests/conftest.py` inserting `REPO` on `sys.path` hides this entire defect class.** 1,221 tests
  stayed green over a runner that could not start as deployed. A gate's own entry point has to be
  exercised **as an entry point** - subprocess, the scheduler's interpreter and cwd, no conftest help.

## In a tree six tracks share, `git add -A` loses authorship - and once it lost a live file (learned 2026-09-13)

- Six commits in one night carried another track's staged files. Five were bookkeeping. The sixth
  (`11f0308`) committed D-6's `scripts/intraday_common.py` calendar-trim fix - **a file the live
  trader imports** - under a garbled message from an unrelated cron, 97 minutes before the owning
  track's own commit.
- `AGENTS.md` step 7 already forbids `git add -A`. **The missing half: after clearing a stale
  `.git/index.lock`, inspect what is already staged before committing.** A killed process leaves its
  staged files behind for whoever commits next.
- Record the drift rather than rewriting another track's commit. Rewriting history over a wrong
  message on a right diff is the worse of the two failures.

## Price the harness before pricing the strategy (learned 2026-09-11/12, S-17 + S-19 + S-21 + S-22)

- **LEAN charges neither spread nor financing, and cannot express the deployed runner's clock.**
  `DefaultBrokerageModel` returns `NullSlippageModel` and `GetMarginInterestRateModel` returns
  `MarginInterestRateModel.Null` (an empty `ApplyMarginInterestRate` body, not overridden by the
  IB model). The engine also cannot fill at the close of the session it decided in, which is what
  the 15:45 runner does. So a headline from `backtest.py` is a **zero-cost, wrong-clock** number.
- **The three defects are INDEPENDENT and may be priced one at a time.** S-22 pre-registered the
  factorial before any cell ran: the LEAN triple prints 18.785% against a multiplicative null of
  18.811, every pairwise interaction inside 0.021 CAR points. Compose corrections; do not re-run
  the grid.
- **The champion's headline is 24.403% and its honest deployed expectation is ~20%** (19.640% in
  LEAN units, 19.415% at today's cost of money). Read every figure in `champion.json` against that.
  This is not a defect and nothing is broken - the paper account has paid all three since its first
  fill; the only thing that was wrong was the expectation.
- **Financing is out-of-sample weighted.** 82% of the whole sample's interest was incurred in
  2023-2026, so the historical drag (-1.32 CAR) understates the forward one (~2.0 at 3.63%).
  Half is the irreducible cost of money; half is the broker's markup, which a larger account pays
  less of.
- **Keep the ledger on one scale.** `S1_SLIPPAGE_BPS`, `S1_FINANCING` and `S1_SIGNAL_LAG` all
  default off/0, and `evaluate.py` **refuses** a run recorded at a cost model with no matching
  champion column rather than judging it against the wrong one.
- **The daily store's close IS the official closing cross to the cent** on all nine sleeve names
  (S-24, 2,683 sessions). Its **open is not** - Yahoo's open is the first consolidated print and
  misses the primary auction by ~1 bp (XLE by 8-11 on some sessions). Any pre-open result must be
  re-filled at the real cross before it is quoted.

## A risk switch is not a forecasting problem (learned 2026-09-12, S-29)

- **A strictly better volatility forecast made a strictly worse crisis gate.** Against the next 21
  sessions' realized vol, log-log corr is 0.4985 for the shipped trailing-realized estimate, 0.6361
  for VIX and 0.6857 for SPY ATM implied - and swapping the input in cost **-2.612 bps/day at
  t -3.06** with the off-rate held fixed (the pre-registered column that kills the "it is just more
  exposure" explanation).
- **Why**: vol peaks coincide with the sharpest rebounds. On an ungated reference book every
  session earns +10.01 bps, the sessions the realized gate removes earn +8.72, the sessions VIX
  removes earn +20.07, and **the 60 sessions VIX removes that realized does not earn +36.56**. A
  realized switch is valuable **because it is late**: it is a trailing stop denominated in
  volatility, acting on damage already done. A forward-looking input converts it into an
  anti-predictive "risk-off above the median" filter.
- **The placebo is the tell**: making VIX five sessions **stale** - deliberately destroying a third
  of its forecast advantage - made the book **better**. When a worse input gives a better book,
  nothing is being paid for forecast quality and the mechanism is not what you wrote down.
- **The crisis switch is the only thing keeping the daily book inside its own risk mandate**:
  removing it is +2.68 CAR for **+12.9 points of drawdown** (DD 36.9%, past the 35% absolute cap).
  Its 1.50 threshold is a **shelf, not a spike** (Sharpe maximum, neighbours within 1.4 CAR points).

## An attribution is not a signal recipe (learned 2026-09-12, S-25 -> S-28)

- **Where the daily champion is paid**: **+8.103 bps/day overnight (t +6.80), 94% of the total**,
  against **+0.738 intraday (t +0.47)**; against a same-gross always-invested control the ranking
  adds **+3.087 bps/day overnight (t +4.20)** and **-0.314 intraday (t -0.37)**, in both halves.
  The leg that pays 94% of the return carries 61% of the risk. Ruled out rather than assumed:
  dividends (price-only the excess is *larger*) and the Yahoo open (official crosses agree).
- **The obvious inference is wrong.** Ranking on the leg that pays does **not** rank better: the
  close-to-close score and the overnight score have the same rank IC on the next overnight leg
  (+0.0574, t +7.25 / +7.32), but the quantity the book actually collects - the top-3-minus-EW
  spread - is **+2.106 bps/day for the shipped score against +1.311** for the overnight one, in
  both halves and on 45% less turnover. **The leg that pays is better forecast by the whole trend
  than by its own history.**
- **A candidate that spends turnover on what the book holds between the open and the close is
  spending it where fourteen years of evidence measure zero.** That is the standing rule the split
  leaves behind.
- **The one place it does change the book is the risk model, not the signal** (S-28): sizing on a
  level-matched overnight vol estimate is a **dead heat in return (t -0.08) for 2.1 points less
  drawdown** - refused by 0.027 CAR points under a return-first rule, and filed as an owner option.
- **Isolating a leg by trading the equity book is arithmetically dead**: 1,248x equity of annual
  turnover, negative **before** a cent of cost. The only viable route is an overlay.

## The four ways a candidate dies, and why the mode matters (learned 2026-09-11/12, F-track + S-track)

- **Cost** (F-1, X-1, L-1, O-2): real gross edge, smaller than the round trip. *A cheaper
  instrument can rescue this - but only if the gross sign is right at |t| > 2.*
- **Sign** (F-4, S-2, A-12): the gross is the opposite of the premise. A cheaper instrument buys a
  **smaller loss**, not a profit. F-4 and F-5 between them withdrew both signs of the intraday
  day-move mechanism; what survives is only the **cost table** (a property of the contract).
- **Absence** (F-6, F-5): nothing is there in either direction before costs. 0 of 336 net, 156 of
  168 gross columns the wrong sign, largest |t| anywhere 2.08. Do not re-open on a parameter.
- **Risk** (S-26, S-28): the edge clears the instrument and the book is refused on drawdown or by a
  return-first rule. **These are the only refusals that are the owner's to overturn**, and they
  belong in `BLOCKERS.md` with a price tag, not in the backlog.
- **A post-hoc result measured on nine correlated ETFs is a hypothesis about that universe, not
  about the mechanism.** S-27's by-product (overnight score forecasting the next intraday leg at
  t -3.30) vanished completely on the 56 permitted names (F-6). A by-product filed from one sleeve
  **owes a transport test** before it becomes a lead on another.

## Default-inert hooks are how to price a shipped algorithm without editing it (learned 2026-09-11/12)

- Four now exist in the shipped `signals.py`, all unset in every deployed path: `S1_ML_SCORES`
  (F-3, ranking), `S1_VOL_RETURNS` (S-28, the vol target's return window), `S1_REGIME_SERIES`
  (S-29, the crisis gate's input), plus `S1_SLIPPAGE_BPS` / `S1_SIGNAL_LAG` / `S1_FINANCING`.
- **The discipline that makes them safe**: after every edit, re-run **both** deploy gates -
  `compare_orders.py` (3,689/3,689 at 5,021 orders) **and** a full LEAN control reproducing
  `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3` - and quote an **identity cell** in the harness
  (the deployed book is 22.192150% / 5,052 orders; the leg identity holds to 2.2e-16).
- Prefer a scale-free hook where possible (S-29's gate reads a level, so no constant is re-tuned).

## Judge a signal by its edge per dollar turned over, not by its IC (learned 2026-09-11, F-1 + F-3)

- **The supervised track is closed, on both sleeves, and the reason is arithmetic.** A
  gradient-boosted cross-sectional forecaster finds an out-of-sample **IC of about +0.011 wherever
  it is pointed** - 5-minute bars on 56 names with 38 features (F-1) or daily bars on 22 ETFs with
  41 features (F-3). The IC is real and it is not the question. The question is **gross basis points
  per dollar of turnover against the cost of turning that dollar**, and that ratio decides
  everything:

  | mechanism | gross bps / $ turned | cost bps | turnover/day | verdict |
  | --- | --- | --- | --- | --- |
  | F-1 intraday GBDT | 0.797 | 0.892 | 13.8x equity | refused |
  | F-3 daily GBDT (long-short) | 0.304 | 3.31 | 0.59x equity | refused |
  | F-3 daily GBDT (top 3 of 9) | 9.29 | 3.01 | 0.49x equity | refused anyway |
  | **shipped champion's momentum blend** | **61.51** | **2.93** | **0.11x equity** | in production |

- **The champion's own ranking is a t = +5.4 signal.** On the nine names it ranks, the four-horizon
  momentum blend scores **IC +0.04268 (t +5.43)** pooled, **+0.03265 in-sample and +0.05475 out of
  sample**. The GBDT forecast on the same names scores +0.00691 (t +0.97) and is only **+0.091**
  rank-correlated with it. Do not spend another iteration looking for a better ranker for this
  sleeve; S-14 already measured that diluting it costs money.
- **A high IC with a flat gross P&L t-statistic means the correlation lives where nothing moves.**
  F-3's pooled IC t was +2.17 while its gross P&L t was +0.18. Always report both.
- **If a ridge baseline matches or beats the tree, the model has no interactions to sell.** F-1's
  tree beat ridge four to one on validation IC and the result was worth reading; F-3's ridge scored
  a *higher* IC than the tree, and nothing in it survived.
- **LEAN's daily history frame is stamped with the bar's own session date**, not the next midnight
  (proved 2026-09-11: `last_bar=2012-01-03 16:00:00` carrying the store's 2012-01-03 close). The
  algorithm decides on D's close and fills at D+1's open, so an exact-date join of any external
  table built from bars <= D is causal. `main.py` logs `FRAME ...` for the first three rebalances so
  the next person joining a table onto that index can check rather than assume.
- **`S1_ML_SCORES` / `S1_ML_MODE` outlive F-3**: any external daily forecast can be ranked through
  the shipped algorithm, at any time, without editing it. Both default to off and the no-environment
  run still reproduces `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`.

## Attribute a strategy's return before tuning any part of it again (learned 2026-09-11, S-15)

- **Most of the champion is not skill.** The nine-ETF pool held equal-weighted and unlevered, with
  no ranking, no entry gate and no regime filter, run through only the vol target, margin budget
  and drawdown overlay, earns **17.282% CAR (Sharpe 0.711)** against the shipped **24.404% /
  0.921** - so **71% of the return is the sizing machinery on ETF beta** and the entire signal
  stack is worth **+7.12 CAR at t = 1.37** over 3,689 paired trading days. Every switch was priced
  by re-running the shipped algorithm with one `S1_*` override; none reaches |t| = 2.
- **Vol-match before crediting any concentration lever.** Dropping ranking costs 6.70 CAR *and*
  drops realized vol 0.170 -> 0.137 (three names instead of nine). Re-sized to the champion's own
  std (`margin_budget` 0.93) the no-ranking book earns 20.745%, so ranking is **+3.66 CAR at
  t = 0.92**, not +6.70. A third of the apparent value of "hold fewer names" is leverage in
  disguise, and with a flat margin budget the vol target will hand it to either side on request.
- **Price a crisis switch on risk, not on return.** The regime filter's in-sample (2012-2019)
  contribution is **exactly zero** (-0.04 bps/day, t -0.03); all of its +2.02 CAR is 2020-2026.
  What it delivers in every regime is drawdown 31.4 -> 25.1 and vol 0.189 -> 0.170.
- **Leveraged instruments supply volatility, not edge** - now measured on both sleeves. Holding
  the same daily signal in unlevered parents instead of the 3x proxies gives **23.128% at Sharpe
  0.950, DD 23.6%, PSR 27.4% and $25.6k of fees** - better than the champion on every
  risk-adjusted measure for 1.28 CAR. L-1 reached the same conclusion intraday.
- **Two LEAN result-file traps** (`scripts/sweep_s15.py` documents both): the `Strategy Equity`
  chart is marked on every **calendar** day, so 1,669 zero-return weekend/holiday rows divide a
  paired bps/day by 1.45 (the t is unaffected); and the `Benchmark` series is plotted one day late
  with repeated values, so it finds 2,317 "sessions" instead of 3,690. Take the trading calendar
  from `lean_prices.load_closes(["SPY"]).index`.

## Every directional study needs its own inverted control (learned 2026-09-11, S-2 and A-12)

- **An exit rule can manufacture the gross a signal appears to earn.** S-2's opening-range breakout
  looked profitable on gross until the mirrored *fade* was run on the same bars: the fade earns
  positive gross in **14 of 16 cells**. A stop plus a hold-to-close exit is convex in either
  direction, so a coin flip collects it. Split gross into the part both signs share,
  `(signal + inverse)/2` - **positive in all sixteen cells, +0.33 to +1.43 bps, and it is the
  stop** - and the part the signal owns, `(signal - inverse)/2`, which peaked at **+1.09 bps
  against a 3.65 bps round trip and was negative in 6 of 16 cells**. On TQQQ the two sides
  finished at +$33.78 and +$33.79 a day: no direction left at all. **Run the inverted control in
  the same pass as the signal, always** - X-1 and L-1 were saved by the same test.
- **One session's worst pattern is not evidence about the population.** A-12 existed because the
  2026-09-10 paper session lost 77% of a -6,779 day to a stopped-out-then-flipped trade in semis.
  Over 44,219 round trips the `flip` re-entry is the sleeve's **only profitable trip category**
  (+$15/trip) and **98% of the loss is in first entries**, which no re-entry filter can reach.
  When a live day motivates a research item, label the whole population by that day's feature and
  read the base rate *before* building the fix.
- **A cell chosen after seeing the diagnostic is in sample, however good its t looks.** A-12's only
  positive grid cell (`same15`, +$38/day at t +1.69) was picked after reading the gap table, is
  worth 0.1 trades/day, and passes 0 of 3 regimes. Name it a falsification control in the write-up
  rather than a candidate.

## Split the universe by executability, not only the sample by time (learned 2026-09-11, A-11)

- **Run the holdout across names, not just across dates.** A-11 split the intraday universe into
  the 8 names whose orders are a believable share of their fill minute (8.8% of notional above 5%
  of the minute) and the 8 whose are not (45.8%). Over 2,684 sessions they score -$195/day at
  **t = -1.89** and -$164 at -0.83 - but on the 261-session window every A-track parameter was
  fitted to, the liquid half earns **-$102/day and the illiquid half +$361/day**. **The sleeve's
  only profitable window in eleven years was entirely in the fills that cannot happen.** Whenever a
  book's edge is concentrated in its least liquid names, split the universe by participation and
  re-read the result before anything else.
- **An execution-realism cap is a diagnostic, not a lever, and it can only answer one question.**
  Clipping every order to 10% of the trailing median volume of its fill minute refused $4.78M/day
  of intended notional over 213,338 orders and moved the book **-$5/day (t = -0.25)**, of which
  +$10/day was the added commission of slicing - i.e. **implied Δgross +$5: the impossible fills
  carried no gross at all.** Ask "what does the book earn when the impossible fills are gone", size
  the answer against the added slicing cost, and then leave the cap off; tightening it to 0.02
  only buys 207 trades/day and $62/day of commission.
- **Check that a store adjusts volume as well as price before believing any participation ratio.**
  The Alpaca store does: SMCI 2016-01-04 is 4.34M adjusted shares at $2.39, i.e. 434k real shares
  at $23.88, so adjusted-shares / adjusted-volume is the real ratio. If it adjusted only price,
  every participation number would be inflated by the split factor (40x on NVDA, 15x on SOXL).

## Forecast vs surprise: why the regime gate failed (learned 2026-09-10, O-1)

- **Decompose a regressor into forecast and surprise before building a gate on it.** The intraday
  sleeve's P&L rides the day's realized range (t = +14). SPY's prior-day implied vol forecasts that
  range about as well as anything can (**corr +0.598, t = +36.4** on 2,381 sessions) - and
  correlates **-0.030 (t = -1.46)** with the P&L. Split the range into the part the forecast saw
  coming and the residual: the forecast part is worth nothing (-0.03 / -0.02 / -0.06 for three
  different IV features) and the **surprise part is worth +0.35 / +0.29 / +0.30 at t = +14 to +18**,
  in nine of nine feature-regime cells. **A book can be paid for volatility *surprise* rather than
  volatility, and surprise is unknowable at entry by construction** - so no forecast of any quality
  reaches it, and no better feature, threshold or horizon will change that. Run this two-line
  decomposition before spending an iteration on a regime gate.
- **"Forecasts |P&L|" is a size scaler, not a gate.** Implied vol correlates **+0.252 (t = +12.67)**
  with the *magnitude* of the sleeve's daily P&L, positive in every regime and for every feature,
  while correlating with nothing about its sign. That is worth zero on a book whose level is
  negative (scaling a loser by its own vol is not an edge) and is only worth testing where the
  level is already positive. Always test the |P&L| link alongside the signed one - it tells you
  which of the two kinds of thing you have found.

## Intraday sleeve: what 2,686 sessions taught (learned 2026-09-09/10, A-4 through A-10)

- **Compute the power before the experiment, not after.** At Sharpe 0.69 a sleeve needs
  `(2/S)^2` years - ~8.4 years, ~2,120 sessions - to reject "earns zero" at two sigma. A-1, A-2
  and A-7 all hunted differences *smaller* than that base rate on 183-260 sessions and were
  never capable of answering. Ask "how many sessions would make this visible?" first; if the
  answer exceeds the store, the iteration is a lever hunt on noise.
- **A big enough sample can flip a shipped decision by 7 sigma.** A-4 kept the late-day fade at
  t = +0.27 on 260 IBKR sessions; on 2,686 Alpaca sessions it is **-$468/day at t = -7.38**,
  negative in every regime and on its own fitted window. A small-sample "no evidence to drop it"
  is not evidence to keep it.
- **The tuning window is a liar and the holdout is the instrument.** A-9's `min 3.6` cell scored
  TUNE Sharpe 2.17 - the best number the sleeve ever produced - and HOLD -1.19; its mirror did
  the exact reverse. When every cell of a grid wins one half and loses the other, the lever is
  selecting which half of the sample you are looking at, not which trades you take.
- **A high-turnover sleeve's sign is owned by the cost constant.** The sleeve turns over $5.46M/day
  on a $1M book, so **one basis point is $546/day** and the whole modelled edge was 1.1 bps wide;
  breakeven slippage 2.62 bps against a charged 1.5. Bar-based spread estimators cannot settle it
  - Roll and Corwin-Schultz give 2.65 bps but correlate +0.906 with 1-minute return std, i.e. they
  measure volatility. Only measured fills settle it (`scripts/slippage_report.py`).
- **Split-adjusted bars break per-share commission and whole-share sizing.** A dollar position on
  adjusted 2016 prices buys up to 40x the real shares, pinning IBKR's per-share charge to its 1%
  cap ($1,523/day vs $222 after the fix), and a reverse-split name (SOXS, factor 8.3e-08) prices in
  the tens of millions so the whole-share floor sizes every early position to **zero**. Derive the
  factor from the data vendor itself (raw vs adjusted daily bars) rather than maintaining a split
  table; charge per-share on real shares and keep the cap on notional.
- **A correlation is not a level.** The sleeve's daily P&L correlates +0.202 with the universe's
  daily range at t = +10.70 over 2,686 sessions - the long-volatility mechanism is real and
  survives every sample - while the level is -$697/day at t = -3.01. A confirmed mechanism buys
  you a *gating* question ("when?"), never a sizing answer ("more").
- **A stop that is a fraction of the signal's own width cannot be gated on that width.** ORB's stop
  is the opening-range midpoint, so a wide range scales the win and the loss together: P&L
  correlates +0.665 with the range added *after* entry and only +0.080 with the opening range
  itself. Check whether a candidate filter is also the risk unit before testing it.

## IBKR connection states (learned 2026-09-09, daily review)

- **Port 4002 goes down nightly.** IB Gateway refused connections 02:19-02:45 ET on 2026-09-10
  (its restart window) and was open again by 06:30. A connect failure outside market hours is
  expected; re-probe rather than treating it as the blocker returning.


- **An open port 4002 does not mean the API is usable.** Gateway accepts the TCP connection,
  then refuses the handshake with `Error 10141: Paper trading disclaimer must first be
  accepted for API connection` and drops the socket; `ib_async` surfaces this as a generic
  `TimeoutError` plus "clientId already in use?", which is misleading - the client id is fine.
  Always read the 10141 line above the traceback before diagnosing anything else.
- So the port probe and the API probe are **different checks**. `paper_trade.py --check` is
  read-only, takes seconds and gives the real answer; run it rather than a socket test whenever
  the Gateway blocker is being re-evaluated.

## Research method lessons (learned 2026-09-08/09, S-8 through S-13)

- **Promotion requires a shelf, not a spike.** A cell that beats the champion on every gate
  while both of its neighbours lose is path luck, not an effect - S-13's `min_order_value=0.02`
  passed `evaluate.py` and agreed in sign on both sub-periods, and was still correctly refused.
  Sub-period agreement at margins inside the region's own scatter is two draws from that
  scatter, not independent confirmation.
- **Prefer the a-priori parameter to the argmax inside a shelf.** S-9 shipped 252 over 250,
  S-10 shipped a 5-session skip, S-12 shipped a 21-session vol window over the 20 argmax.
- **`sweep_s1.py` and LEAN can disagree in sign, not only in magnitude** (S-10). The sweep also
  understates drawdown: ~+2 points at champion size, ~+6 on S-12's cell, +8 to +10 at 2x
  exposure. Sweeps generate candidates; LEAN decides. A sweep rejection buys one confirmation
  run, never a closed idea.
- **The ETF-9 sleeve is out of cheap levers, by measurement.** S-11 showed the champion's
  turnover cannot be converted into return (suppressing rotation removes return monotonically -
  the rotation is signal); S-13 showed it cannot be removed for return either (the band is flat
  and non-monotone across a factor of eight, so ~63% of orders are return-neutral). S-12 spent
  the allocation step. What remains needs breadth or a second sleeve, i.e. D-2/S-2, not another
  parameter on this sleeve.
- **Backtest-neutral is not live-neutral.** LEAN charges commission but models no spread at
  all, so a change that is worth $0 in the ledger (a wider no-trade band) can still be worth
  real money live. Route those to the human as execution decisions rather than closing them as
  negative research results.
- **Commission floor at this account size is 2.1bps per unit of turnover** (S-3), before any
  spread - more than the entire gross edge a daily-turnover reversal sleeve could find.

## LEAN data format gotchas (learned 2026-09-08, backlog D-1)

- **A factor file containing only the `20501231,1,1,0` sentinel makes LEAN return zero bars
  for that symbol, silently.** No exception, no entry in `failed-data-requests-*.txt` - the
  symbol simply never appears in the `Slice`. This bites any symbol that has never paid a
  dividend (GLD, UVXY, BRKB, NOW, UBER). Always emit a listing row at the first bar date:
  `<first_bar_date>,<earliest_factor>,1,1`. `scripts/fetch_data.py` validates this now.
- Because of the above, an algorithm that gates on "all symbols present" will place zero
  orders and still exit 0 with a clean-looking summary. Log per-symbol bar counts in any
  data acceptance test rather than trusting the statistics block.
- Factor file rows are `date,price_factor,split_factor,reference_price`, ascending, where a
  row's date is the **last** bar date its factor applies to (LEAN takes the first row with
  `date >= bar date`). Real files carry one row per corporate action, ~117 for a
  dividend-paying name since 1998.
- Daily zips: `equity/usa/daily/<sym>.zip` holding `<sym>.csv`, rows
  `yyyyMMdd 00:00,o,h,l,c,v`, OHLC scaled by 10000 as integers.

## yfinance quirks (learned 2026-09-08)

- Yahoo's OHLC are **already split-adjusted**; only `Adj Close` adds dividends. So LEAN
  split factors stay 1 and dividends go entirely into the price factor.
- Do **not** derive price factors from `Adj Close / Close`: Yahoo rounds `Adj Close`, so the
  ratio drifts in the 7th decimal every day and generates a factor row per bar (5490 rows
  for SPY instead of 117). Use the explicit `Dividends` column from `actions=True` and
  accumulate `(1 - D / C_prev)` backwards from the most recent bar.
  `Adj Close` is still useful as an *independent cross-check* - agreement was within 0.003%.
- The in-progress session's bar is a live snapshot with `high < open`. Always end the fetch
  window exclusive of today.

## Toolchain (learned 2026-09-08)

- `git` had no identity in this repo; set locally to `quant / sensordyme@gmail.com`.
  Backtests run before the first commit record `"commit": "unknown"` in the ledger.
- `scripts/backtest.py` ignores the engine's exit code on purpose (pythonnet raises a
  harmless GIL finalizer error at shutdown); success is judged by the summary file existing.

## LEAN order execution on daily bars (learned 2026-09-08, S-1)

Every one of these produced a plausible-looking backtest rather than an error. On daily
resolution the statistics block cannot be trusted until execution is verified separately.

- **A daily-resolution security's local time is its last bar stamp**, so the exchange looks
  closed to any intraday scheduled event. Market orders silently degrade to MarketOnOpen,
  and the IB brokerage model rejects MOO submitted outside 04:00-09:28. Symptom: thousands
  of orders, zero fills, `Total Fees $0`, equity exactly unchanged.
- **Do not rebalance from a pre-open scheduled event on daily data.** MOO orders sent at
  09:00 on day D are still unfilled at 09:00 on day D+1, so the next rebalance reads stale
  holdings and stacks another full target. This reached 12.7x gross against a 1.0 cap and
  wiped the account. Rebalance from `on_data` on the daily bar instead: decide on day D's
  close, fill at day D+1's open, exactly one order batch in flight.
- **`set_holdings(PortfolioTarget(symbol, w))` sizes `w` against buying power, not equity.**
  Account leverage therefore multiplies every target: identical signals gave 27% annualized
  vol at 2x leverage and 43% at 4x, against 16% on paper. For anything leverage-sensitive,
  compute share counts from `portfolio.total_portfolio_value` and send `market_order` deltas,
  sells first. That is also the order-list logic a live IBKR runner needs.
- **LEAN charges initial margin on both legs of a rotation** because pending MOO orders do
  not net. At gross 1.0 with default 2x this rejected 1,467 of 3,690 rebalances; at gross 1.3,
  3,004 of 3,690. Raising `set_leverage` fixes the artifact, but only do so alongside an audit
  of the gross exposure actually carried - otherwise a real sizing bug becomes invisible.
- **Always audit realized gross exposure** (`sum(abs(holdings_value)) / total_portfolio_value`)
  against the intended cap and log it at end of algorithm. That single line is what
  distinguished "the signal is bad" from "the orders are wrong" in every case above.

## Research-method notes (learned 2026-09-08, S-1)

- A drawdown rule of "go flat until a new equity high" is an **absorbing state**: a flat book
  earns nothing, so it can never print a new high. Adding a cooldown is not enough either -
  if the high-water mark survives, the breaker re-arms the moment it releases and trades one
  day in N forever. Reset the watermark when the breaker releases.
- Validate a signal outside the engine first. `scripts/sweep_s1.py` runs a config in ~25s
  against LEAN's own bars via `scripts/lean_prices.py`, versus ~3.5 min for a LEAN run, and
  it imports the shipped signal module so the two cannot silently diverge. Sweep to choose
  parameters, then confirm in LEAN - and treat any large gap between them as an execution
  bug, because that is what it was every time.
- Judge a component on each sub-period independently, not on the full sample. That is what
  justified dropping both the vol-below-median filter and the 200-day trend filter from S-1.

## Research-method notes (learned 2026-09-08, S-11)

- **A turnover reduction is only free if the turnover was noise.** Three independent whipsaw
  controls on the S-1 champion (score hysteresis, minimum holding period, rank persistence)
  each removed return roughly in proportion to the drawdown they removed, monotonically in
  the strength of the control. When suppressing rotation costs return, the rotation was
  carrying information and the cost floor is being paid for something. Measure the exchange
  rate (CAR points given up per drawdown point bought) before treating a cost saving as a win.
- **A lever that blocks an entry is not automatically a lever that cuts trading.** Rank
  persistence *raised* order count 6% and fees 24% in LEAN, because refusing to fund a name
  parks the book in cash and then buys it back a few days later. Check realized order counts,
  not just the intent of the rule.
- **Path-dependent signal state must be threaded, not rebuilt.** `drawdown_multiplier`
  returns a fresh state dict, so any new persistent field (here `held` / `held_age`) has to be
  read before that call and written back after it. Every early return that means "sit in cash"
  must clear the field, or the next call defends holdings that do not exist.
- **Measure the size of the edge you are tuning.** S-14 isolated the daily champion's
  cross-sectional selection edge - the only part the ranker is responsible for - at **+2.02
  bps/day, t = 2.07** over 3,099 invested days, and it exists only at top-3-of-9: at five
  holdings no sleeve's spread is significant. Six iterations (S-9 to S-14) were spent tuning
  that component. Before optimizing a piece of a strategy, price the piece.
- **Breadth is not free diversification.** Widening a momentum ranking pool (9 -> 17 -> 22 ETFs)
  made the champion monotonically worse (CAR 24.4 -> 17.3 -> 11.6) at unchanged realized vol, and
  four fifths of the damage was the ranking spread collapsing, not the added names being worse
  assets. What it did buy was drawdown (unlevered 22.4% -> 14.3%), which is a risk-posture trade.
  Split any such comparison into `selected = pool_mean + spread`, and vol-match before blaming
  leverage access.
- **Audit the harness, not just the strategy, when the backlog runs out of levers.** After S-15
  and S-16 the daily sleeve appeared to have nothing left but owner decisions. Two of the three
  largest numbers found since then were measurement defects invisible to sweeping: LEAN's IB
  brokerage model returns `NullSlippageModel`, so sixteen iterations compared cells that differ
  by 2.7x in order count on a harness that charges **no spread** (0.68 CAR points per bp on the
  champion), and the deployed runner reads yfinance's last *complete* daily bar at 15:45 ET, so it
  trades a signal **one session stale** (-4.75 CAR, t -2.65). Neither is a parameter. When the
  levers are exhausted, price the instrument and the deploy path.
- **A cost set to zero is not a neutral assumption, it is a thumb on the scale for turnover.**
  S-16's unlevered candidate was refused for missing the champion's CAR by 0.001 points; that
  margin existed only at exactly zero spread, and the crossover sits at ~0.03 bp against a
  half-cent tick worth 0.27-0.77 bp. Judge every cell at zero *and* at a non-zero cost bracket,
  and never compare a cell that pays a cost against a baseline that does not.
- **Check what the live runner's signal is as-of, not just what orders it produced.**
  `compare_orders.py` had been passing 3,689/3,689 for days while the deployed path acted on a
  close a session older than the backtest's, because an order-list comparison on historical dates
  cannot see a clock difference. The fact was in the runner's own `plan` log (`as_of`) the whole
  time; nobody had compared it to the backtest's convention.
