# Research discovery report — 2026-09-15

Nothing was committed, nothing was pushed, no order endpoint was called. All four safety
flags remain false. ProjectX was used read-only throughout, through a transport whose
allow-list makes `/api/Order/place` unreachable.

---

## 1. The discovery

**Seventy-three per cent of the market data this repository holds had never been looked at,
and that is where all of the return is. It is also the part a Topstep Combine forbids you to
hold.**

The stores contain the full ~23-hour Globex cycle, a median of 1,380 one-minute bars a day.
Every backtest ever run here used the 09:30–15:45 window, 376 bars, because
`futures_discover.load` filters to it. That is an analysis convention, not a property of the
data, and nobody had revisited it.

Decomposing the whole cycle by trade date, roll-safe, one contract per date:

| | night 18:00–08:59 | open hour 09:00–09:59 | regular 10:00–15:59 |
|---|---|---|---|
| ES | **+911.0 pts** | +265.5 | **−170.0** |
| NQ | **+4,161.2** | −267.8 | **−475.0** |
| MES | **+714.0** | +257.0 | **−299.2** |
| MNQ | **+3,173.5** | +30.0 | **−1,047.8** |

Every instrument, the same shape. The entire fifteen-month advance happened overnight, and
the regular session — the only window we have ever studied — drifted **negative** on all four.

Three consequences, and the third is the one that matters.

**It explains the null results.** A 240-trial tournament found nothing in a window whose
underlying drift was negative. Long-biased mechanisms had a headwind and short-biased ones
were fighting a market that rose, just not while they were allowed to be in it.

**It is beta, not alpha.** Holding overnight is exposure, not skill. The number to compare it
against is buy-and-hold, and it is not a strategy edge.

**And a Combine cannot hold it.** Topstep requires a flat book at 15:10 CT. The only part of
the twenty-four hours that carried positive drift in this sample is precisely the part the
rules prohibit. A Combine strategy therefore cannot lean on drift at all; it needs genuine
intraday alpha, in the window where the drift was negative — and section 7 reports a
well-powered null for exactly that at a 30-minute horizon.

That is a harder problem than the one we thought we had, and knowing it is worth more than
another hundred backtests. No backtest found it. It came from questioning an assumption in
the loader.

## 2. What the research process now is

The prior loop was idea → backtest → fail. Three components were built to replace it, and the
order matters: the gate comes *before* the laboratory.

**`quant_brain/research/feasibility.py`** answers "has this hypothesis earned a backtest?"
before any data is spent, and distinguishes two failures that are usually conflated:

- **INFEASIBLE** — the edge does not pay its transaction costs even if captured perfectly. A
  property of the fee schedule. More data never fixes it.
- **UNTESTABLE_HERE** — it pays, but is too small to separate from noise in this sample. A
  property of the sample. More data fixes it; more cleverness does not.

**`quant_brain/research/genealogy.py`** records preregistered claims and their lineage. The
load-bearing field is `result_driven`: true when a hypothesis exists because of something we
saw in our own data. `effective_trials()` charges a result-driven lineage more against the
multiplicity bar than its member count, because each generation was a look at the data.
It refuses a duplicate claim, refuses a variant that does not say why it differs from its
parent, and refuses to skip a rung of the budget ladder.

**The existing engine is reused unchanged.** `registry.Ledger`, `robustness`, `promotion` and
the funnel already exist; the new layer sits around them rather than replacing them.

25 tests, all passing. Full suite green, lint clean.

---

## 3. ProjectX: read-only, working, bound

| | |
|---|---|
| Authentication | **PASS**, one attempt, no retry by design |
| Accounts visible | exactly 1 |
| Bound account | `id=27550191`, `50KTC-SKU-V2-DLL-679574-19137660`, $50,000, canTrade, simulated |
| Contracts | `CON.F.US.MNQ.U26`, `CON.F.US.ENQ.U26`, `CON.F.US.MES.U26`, `CON.F.US.EP.U26` |
| Endpoints reached | `Auth/loginKey`, `Auth/validate`, `Account/search`, `Contract/search`, `Contract/searchById`, `History/retrieveBars` |

Contract mechanics were **independently confirmed against the venue**: tick 0.25 throughout,
tick values 0.5 / 5 / 1.25 / 12.5 for MNQ / NQ / MES / ES, which is $2, $20, $5 and $50 a
point. These match the repository's own table exactly.

Two data facts worth knowing. History is capped at **20,000 bars per request**. And every
contract, expired ones included, returns data only from **2025-09-15** — the subscription
floor, not the contract's life. Expired months *are* retrievable by id, so a roll-aware
continuous series can be built properly rather than stitched, but ProjectX adds correctness
rather than depth: about 12 months against the 15 already on disk.

---

## 4. The economics, measured

Break-even move — the smallest move that pays its own round turn, at a deliberately
pessimistic 50% capture assumption:

| | $/point | round turn | break-even | ticks |
|---|---|---|---|---|
| MES | 5 | $2.47 | 0.99 pt | 4.0 |
| MNQ | 2 | $1.72 | 1.72 pt | 6.9 |
| ES | 50 | $16.28 | 0.65 pt | 2.6 |
| NQ | 20 | $13.78 | 1.38 pt | 5.5 |

**Tradeability** — median absolute move over a horizon, divided by the break-even move. Pure
market arithmetic, no strategy, so no selection bias is possible:

| | 5m | 15m | 30m | 60m | 120m |
|---|---|---|---|---|---|
| MES | 4.55 | 8.10 | 11.64 | 16.70 | 24.80 |
| MNQ | 14.53 | 24.71 | 36.05 | 51.16 | 75.87 |
| ES | 6.91 | 12.29 | 16.89 | 24.57 | 33.78 |
| NQ | 17.42 | 29.39 | 41.00 | 57.69 | 77.65 |

The Nasdaq complex offers roughly **three times** the room of the S&P complex at every
horizon. This alone explains why every apparent survivor in the prior 240-trial tournament was
a Nasdaq contract and none was S&P.

**Required directional accuracy** at a 30-minute horizon: MNQ 51.4%, NQ 51.2%, ES 52.9%,
MES 54.3%.

---

## 5. The reframing: capture, not cost

The prior conclusion was that transaction costs are the binding constraint. That is a symptom.

| | needed to break even | actually captured |
|---|---|---|
| MNQ | 2.8% of a 30m move | 0.21% |
| NQ | 2.4% | 0.27% |
| ES | 5.8% | 0.13% |
| MES | 8.7% | 0.23% |

Median share of the theoretical one-bar-ahead ceiling captured across all 240 cells:
**0.239%**. The strategies were roughly **thirteenfold short** on signal, and high turnover
merely multiplied that deficit into a visible loss. A programme aimed at cutting costs or
cutting turnover is aimed at the wrong thing.

---

## 6. Which instruments the research should use

Combining two independent calculations — neither involving a strategy:

| | tradeability (15m) | a Combine-sized edge is | verdict |
|---|---|---|---|
| MNQ | 24.7 | visible above $8.99/session | **research here** |
| MES | 8.1 | visible above $4.12/session | best detectability, least room |
| ES | 12.3 | visible above $34.66/session | marginal |
| NQ | 29.4 | visible only above $74.65/session | **cannot adjudicate — drop** |

**NQ should be dropped from the search.** A strategy good enough to pass the Combine on NQ
would still be indistinguishable from noise in this sample, so a null result there is not
evidence of absence. MNQ is the unique contract that is both highly tradeable and where a
passing edge would be visible.

---

## 7. Experiments run, and what they found

**Directional predictability at 30 minutes, first attempt — a false positive I caught.**
Twenty of 68 feature-instrument pairs appeared to clear the break-even accuracy bar with
t up to 12.4. Every one of them was an always-positive feature: `rel_volume`, `rvol_30`,
`rvol_120`, `range_expansion`, `vol_of_vol`, `volume_accel`, `minutes_from_open`. Their "hit
rate" was simply the unconditional up-rate of the market — 52.1% to 52.5% across the four
instruments over this sample. It was measuring drift, not prediction.

**Corrected, against the base rate.** Restricting to sign-varying features and comparing to
each instrument's own up-rate: **32 of 40 pairs are significant, and every one is negative.**
Momentum and trend features *anti-predict* the next 30 minutes by about three percentage
points (NQ `ma_dist_30` 48.93% against a 52.09% base, t = −14.0). Short-term extension
reverts.

**The reversion gradient is monotone.** Fade hit rate rises with |z_60| on every instrument:
MNQ 49.13 → 49.66 → 52.69%, NQ 50.23 → 51.05 → 52.18 → 53.52%. That shape across four
instruments is what a real mechanism looks like.

**And it vanishes under a correct sample.** Thirty-minute forward windows sampled every bar
are roughly thirty-fold redundant. Re-run on non-overlapping samples, the best cell — NQ,
|z_60| in the 90–95th percentile — falls from 53.52% (t = +2.2, n = 2,229) to **45.45%
(t = −1.01, n = 77)**. It was entirely an overlap artefact.

**The three-point anti-prediction was too.** Correcting my own result above: the "momentum
anti-predicts by about 3 percentage points, 32 of 40 pairs significant" finding was itself
measured on overlapping windows. It does not survive. See the next section.

**THE DECISIVE EXPERIMENT: the full session, non-overlapping.** Acting on section 1, the
30-minute measurement was re-run on the whole Globex session with non-overlapping samples:

| | window | independent obs | base up-rate | fade hit | edge vs base | t |
|---|---|---|---|---|---|---|
| MNQ | RTH | 2,519 | 0.5200 | 0.5073 | −0.0127 | −1.28 |
| MNQ | **FULL** | **10,815** | 0.5175 | 0.5093 | −0.0082 | −1.71 |
| MES | RTH | 2,496 | 0.5220 | 0.5056 | −0.0164 | −1.64 |
| MES | **FULL** | **10,640** | 0.5188 | 0.5154 | −0.0034 | −0.70 |
| NQ | RTH | 3,129 | 0.5139 | 0.5155 | +0.0016 | +0.18 |
| NQ | **FULL** | **13,481** | 0.5176 | 0.5120 | −0.0056 | −1.31 |
| ES | RTH | 3,102 | 0.5193 | 0.5152 | −0.0042 | −0.47 |
| ES | **FULL** | **13,236** | 0.5178 | 0.5119 | −0.0059 | −1.36 |

Four times the data, and nothing. Every |t| below 1.71, every effect under one percentage
point, and all of them the wrong sign for a fade.

**This is now a well-powered null rather than an underpowered one, and that is the result.**
At roughly 11,000 independent observations the smallest detectable effect is 0.93 percentage
points. We can therefore state, for the first time with the power to mean it: **there is no
30-minute directional edge larger than about one percentage point in these four contracts,
in either session window, over this sample.** The earlier three-point figure was overlap
inflation and the correction runs against my own prior conclusion.

**One trap worth naming.** The base up-rate on MNQ over the full session is 51.75% and the
break-even accuracy is 51.39%. Always-long clears the bar arithmetically. That is not a
strategy, it is a bet that a fifteen-month rise continues, and it is exactly the degenerate
case the tournament's constant-position filter exists to catch.

**Second-generation hypothesis, preregistered and rejected.** The six distinct survivors of
the prior tournament were all reversion in character and all on the Nasdaq complex. Stated as
one claim — "on the Nasdaq complex, fade-character strategies have positive mean net on data
not used for their selection" — and tested on the untouched test split: mean **−$818 per
cell, t = −5.11**. Not supported. The S&P complex was worse (−$1,330), which is the
tradeability result showing through, not an edge.

---

## 8–10. Strategies with positive discovery, OOS survival, cost-stress survival

**None, in all three categories.** No hypothesis tested in this session or the prior one
survives to a positive out-of-sample result at any defensible significance bar. The final
holdout has never been read.

---

## 11–13. Pass probabilities, MLL breach, cost analysis

No pass probability is quoted, because no candidate exists to quote one for. The twin itself
is now trustworthy — a path-reconstruction defect that manufactured liquidations was fixed and
hand-tested — but a valid simulator applied to a non-existent strategy produces nothing.

Cost analysis is section 4 and 5 above. The headline is that costs are **not** prohibitive:
the median 30-minute MNQ move is 36 times its break-even. The deficit is signal.

---

## 14–16. Cross-market, regime, and failed-strategy insights

**Cross-market.** The four contracts are two underlyings at correlation above 0.9. Treating
them as four independent tests overstates the evidence roughly twofold; two of the eight prior
survivors were literally the same strategy on NQ and MNQ. There is no cross-section to sort
here, which rules out the cross-sectional form of several published effects.

**Regime.** Not yet tested properly. The monotone |z_60| gradient in section 7 is the closest
thing to a regime result and it did not survive the overlap correction.

**Failed-strategy insight.** The most valuable one is that the prior tournament's failure was
misdiagnosed. "Costs kill it" was the wrong lesson; "these mechanisms carry almost no
directional information, and cost converts that into a loss" is the right one. The two lead
to completely different next steps.

---

## 17–18. ML and information theory

No ML was run, deliberately. Section 5 shows the non-ML baselines capture 0.24% of available
movement; there is no baseline worth beating yet, and fitting a model to a signal this weak
would produce a memorised price path.

The information-theoretic work in section 7 is the substitute and it was more useful: a direct
measurement of directional information, which is what an ML model would be trying to extract.
The answer at 30 minutes, on the regular session, with non-overlapping samples, is that there
is not enough of it to measure.

---

## 18b. Two caveats that weaken every null in this report

Both were raised by external research and both were verified here against our own store.

**Our sample is a low-volatility regime, at roughly half the long-run amplitude.** ES intraday
realised volatility over 322 sessions: median **7.83%** annualised, p90 14.53%, max 23.16%,
against a long-run S&P figure near 16%. Only **6.8%** of our sessions exceed 16%.

That matters because signal amplitude scales with volatility while the dollar cost does not.
At long-run volatility the median gross of $1.04 a round turn becomes roughly $2.12, which is
parity with the $2.10 cost rather than half of it. So the capture deficit reported in section
5 is real *in this sample* and should not be extrapolated to a normal market without saying
so. The honest version of "costs are not the barrier, capture is" is: **amplitude is the
barrier, and in a calmer-than-usual fifteen months amplitude was low.**

The remedy is a wider sample, not a cleverer signal. Reaching 2018–2020 and 2022 would put a
genuine high-volatility regime in the data for roughly $42 a quarter of vendor history, and
that is the highest-value purchase available to this project.

**Our session window excludes the largest fifteen minutes of the day.** Volume share of RTH by
15-minute bucket: **15:45 is 10.58%**, the single largest bucket, ahead of the 09:30 open at
7.45%. The 09:30–15:45 window drops **13.9%** of regular-session volume, and it is the part
where the closing auction and the settlement flows live — which is exactly the window the
intraday-momentum literature is about. A null measured on two thirds of that window is not a
test of the published effect.

**One correction to the external critique.** It reported that "every trial was a single-feature
threshold, no interaction was ever tested". That is true of the older 818-row funnel and not
of the 240-trial tournament, which tested conditional mechanisms throughout: momentum gated on
a volatility z-score, reversion gated on range expansion, and three explicitly
volatility-conditioned families. The interaction critique stands against the historic ledger
and not against the current one.

---

## 19. Data limitations

- History floor 2025-09-15 on ProjectX; ~15 months on disk. Roughly one market regime.
- **The ES quote file has no sizes.** `quote_imbalance` is unbuildable, not merely untested.
- No Level 2, no tick data, no options, no VIX, no economic calendar.
- Two underlyings, not four instruments.
- 73% of the held data is unexamined — a limitation of practice, and the one that is fixable
  tonight rather than by buying anything.

---

## 20. Statistical limitations

The dominant one. With non-overlapping 30-minute samples the regular session yields 2,364
independent training observations, and resolving a two-point edge needs 2,401. Every
significance figure computed on overlapping windows in this repository's history is inflated
by roughly the square root of the overlap factor — about 5.5x at a 30-minute horizon.

---

## 21. Top research risks

1. Overlapping-window inflation, present in most prior work here.
2. Analysing 27% of the data and generalising to the market.
3. Treating four contracts as four independent tests.
4. Result-driven hypotheses tested on the data that inspired them.
5. Base-rate confusion: a rising market makes any always-positive feature look predictive.
6. Selecting on the noisiest instrument, then believing the selection.
7. A single day carrying a result — four of eight prior survivors.
8. Fifteen months is one regime.
9. Published effects measured on other markets and other decades.
10. Two Fed results central to intraday futures research have been **retracted by their own
    authors**, and both dead zones contain our entire sample.
11. VPIN's predictive power is an artefact of its own estimator.
12. Published lead-lag effects are explicitly unprofitable after the spread.
13. Cost is charged flat while liquidity withdraws exactly when signals fire.
14. Intraday periodicity makes fixed thresholds fire at clock times, not events.
15. The holdout is spendable exactly once.
16. Micros are the cheapest per contract and the most expensive per unit of notional.
17. A twin that was pessimistic for months discarded strategies on impossible paths.
18. Capture assumptions default to optimism unless forced.
19. Evolutionary overfitting across generations of one lineage.
20. Confusing "we found nothing" with "there is nothing" when power is this low.

---

## 22. Top unknowns

Whether the full Globex session contains the signal the regular session does not; whether the
reversion gradient survives with four times the data; what the overnight-to-regular
relationship looks like here; whether liquidity-adjusted costs change the ranking; what an
hourly or daily horizon looks like, entirely untested; whether the two underlyings behave
differently for a reason or by chance; what the closing auction does; whether announcement
windows are separable without a calendar; what the roll does to a continuous series; whether
MES's better detectability beats MNQ's better tradeability; and whether a strategy that only
decides *when not to trade* beats one that predicts direction.

---

## 23. Most promising directions

1. ~~Re-run everything on the full session.~~ **DONE, this session.** It quadrupled
   independent observations and returned a clean, well-powered null at the 30-minute horizon.
   The remaining directions below now matter more, not less: the cheap horizon has been
   properly excluded.
2. **Overnight gap into regular-session behaviour.** One round turn a session; ES costs 0.33
   points against a typical gap many times that. The right shape for this cost structure.
3. **Longer horizons.** Nothing above two hours has ever been tested here.
4. **Liquidity-conditioned cost.** CME's own data shows depth collapsing as volume spikes;
   a flat cost may be systematically wrong in the direction that flatters signals.
5. **Periodicity filtering before thresholding**, so triggers fire on events not clocks.
6. **A cross-instrument placebo** — ES against MES at one minute must return zero, and if the
   funnel finds an edge there it is a bug report about the funnel.

---

## 24. Exact next experiments

1. Add a `session` argument to `futures_discover.load` so the full Globex session can be
   selected, and re-run the 30-minute non-overlapping predictability measurement on it. This
   is the one experiment that changes what every later experiment can conclude.
2. Measure the overnight gap against the first-hour regular-session return, non-overlapping,
   one observation per day, both underlyings. About 395 independent observations.
3. Run the ES-versus-MES placebo through the funnel and confirm it returns nothing.
4. Assemble the raw MES and NQ `BID_ASK` pages already in `data/futures/.raw/` and measure
   per-instrument spread, replacing the assumption that every contract trades at ES's tick.
   The NQ round turn of $13.78 is $4.68 above what tick-plus-commission predicts and rests on
   an unverified constant.
5. Extend the window to 16:15 ET. It costs nothing, and it restores the largest fifteen
   minutes of the trading day plus the settlement window the momentum literature is about.
6. Buy history back to 2018. Every null in this report was measured at half the long-run
   volatility, and no amount of analysis fixes a sample that contains one regime.
