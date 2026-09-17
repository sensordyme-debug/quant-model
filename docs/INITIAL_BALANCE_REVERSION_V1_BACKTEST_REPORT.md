# Initial Balance Statistical Reversion — ES V1.0_Frozen — backtest report

**The strategy lost money, and it lost money before costs.** Net −$12,634.68 over 313 ES
sessions under `BASELINE_FROZEN`; gross, before a cent of commission or slippage, was
−$6,775.00. The Topstep $50K account was liquidated on 2025-10-22 and never reached the $3,000
target under any execution profile.

No parameter was changed, no sweep was run, and nothing was altered after seeing the result.

```
strategy          ES_V1.0_Frozen        spec hash  09debab58c51c1d8
dataset           ES manifest ecf680404326fe37     content 92b9ad205458d566
                  sha256 781ec858f6edfcd9...       447,600 rows, 313 of 327 sessions usable
topstep profile   retrieved 2026-09-12             $50K / target $3,000 / MLL $2,000
git               f4f9bcd87615e7e50372de6d44f6fc29b3fb646a
environment       python 3.14.7, numpy 2.5.3, pandas 3.0.5, seed 20260917
ambiguities       10 declared, 0 unresolved
```

---

## 1. Results, all four profiles

| profile | trades | gross | commission | slippage | **net** | win | PF | max DD | worst day |
|---|---|---|---|---|---|---|---|---|---|
| IDEAL | 262 | −$7,700 | $1,085 | $0 | **−$8,785** | 39.7% | 0.788 | $12,532 | −$1,283 |
| **BASELINE_FROZEN** | 262 | **−$6,775** | $1,085 | $4,775 | **−$12,635** | 38.6% | 0.713 | $15,457 | −$1,321 |
| STRESS_1TICK | 262 | −$6,775 | $1,085 | $6,950 | −$14,810 | 38.6% | 0.677 | $17,328 | −$1,346 |
| STRESS_2TICK | 262 | −$6,750 | $1,085 | $9,125 | −$16,960 | 37.8% | 0.645 | $19,178 | −$1,371 |

**The loss is not a cost artefact.** Even at IDEAL — zero slippage everywhere — the strategy
loses $8,785, and its gross P&L is negative at every profile. Costs make a losing strategy
lose more; they did not create the loss.

### Why it loses, in one line of arithmetic

| | |
|---|---|
| median stop distance (entry → stop) | **7.25 points** |
| median target distance (entry → midpoint) | **8.88 points** |
| median reward : risk | **1.24 : 1** |
| break-even win rate at that ratio | **44.7%** |
| **actual win rate** | **38.6%** |

The stop is one tick beyond the excursion extreme, and the excursion is usually a wide
rejection bar — so the stop is *far*, not close. A 1.24:1 payoff needs 44.7% accuracy and the
strategy delivers 38.6%. That six-point gap is the whole result.

---

## 2. Trade statistics — BASELINE_FROZEN

| | |
|---|---|
| sessions analysed / in regime / traded | 313 / 181 / 156 |
| sessions skipped, IB range outside 10–35 | **132** |
| trades / per session / per traded session | 262 / 0.837 / 1.68 |
| average trade / median trade | −$48.22 / −$110.39 |
| average winner / average loser | +$310.09 / −$273.01 |
| payoff ratio / profit factor / expectancy | 1.136 / 0.713 / −$48.22 |
| max consecutive wins / losses | — / **13** |
| best / worst trade | +$766 / −$1,321 |
| MAE mean / MFE mean | −$186.59 / +$138.50 |
| median holding time | 15 minutes |
| Sharpe (unit = one trading session) | −0.127 |
| Sharpe annualised ×√252 | −2.023 |
| Sortino (session unit) | −0.143 |

> **Sharpe time unit is one TRADING SESSION**, computed on daily P&L and annualised with
> √252. It is not computed on trade P&L, where √252 would be meaningless.

### Exit reasons

| reason | trades | net | wins | avg |
|---|---|---|---|---|
| target | 81 | +$28,202.16 | 81 | +$348.17 |
| stop | 120 | −$35,721.80 | 0 | −$297.68 |
| time_stop | 40 | −$203.10 | 20 | −$5.08 |
| governor_killswitch | 14 | −$4,095.46 | 0 | −$292.53 |
| target_immediate (B4) | 7 | −$816.48 | 0 | −$116.64 |

By side: LONG 125 trades −$9,105 (40.0% win); SHORT 137 trades −$3,530 (37.2% win). Both lose.

---

## 3. Monthly

| month | sessions | trades | net | return on $50k | intra-month DD |
|---|---|---|---|---|---|
| 2025-06 | 15 | 16 | +$121 | +0.24% | $1,037 |
| 2025-07 | 21 | 26 | **+$1,880** | +3.76% | $821 |
| 2025-08 | 21 | 22 | −$516 | −1.03% | $1,337 |
| 2025-09 | 21 | 22 | +$121 | +0.24% | $1,212 |
| 2025-10 | 23 | 26 | −$1,970 | −3.94% | $2,741 |
| 2025-11 | 18 | 7 | −$91 | −0.18% | $1,125 |
| 2025-12 | 21 | 26 | −$1,670 | −3.34% | $2,395 |
| 2026-01 | 20 | 21 | −$724 | −1.45% | $1,487 |
| 2026-02 | 19 | 2 | −$658 | −1.32% | $658 |
| 2026-03 | 22 | 1 | +$21 | +0.04% | $0 |
| 2026-04 | 21 | 24 | −$624 | −1.25% | $3,662 |
| 2026-05 | 20 | 17 | −$820 | −1.64% | $2,571 |
| 2026-06 | 21 | 5 | −$2,283 | −4.57% | $2,283 |
| 2026-07 | 22 | 14 | −$1,933 | −3.87% | $3,137 |
| 2026-08 | 21 | 27 | −$2,562 | −5.12% | $2,978 |
| 2026-09 | 7 | 6 | −$925 | −1.85% | $1,217 |

```
16 months   mean -$790   median -$691   positive 4 / negative 12
best +$1,880 (2025-07)   worst -$2,562 (2026-08)
```

**16 months is not an estimate of long-run monthly performance.** Note also the trade-count
collapse in 2026-02, -03 and -06 (2, 1 and 5 trades): those are months where the IB range sat
outside 10–35 on most days, so the regime filter stood the strategy down.

### Strategy return vs account return

| | |
|---|---|
| **A. strategy net P&L** | **−$12,634.68** |
| **B. simulated account balance** | $50,000 → **$37,365.32** |
| **account return** | **−25.27%** — net account P&L ÷ $50,000, the declared metric |
| max drawdown | $15,456.98 = **30.91%** of the account |
| drawdown duration | 264 sessions (2025-08-19 → 2026-09-09), never recovered |
| max intraday adverse excursion | −$1,366.64 |

There is no separate "strategy return" denominator: one ES contract is not a capital
commitment of a stated size, and inventing one would be inventing the number.

---

## 4. Topstep $50K digital twin

The same canonical ledger, replayed through the certified twin. No second simulation.

| | |
|---|---|
| starting balance / profit target / MLL | $50,000 / $3,000 / $2,000 |
| MLL trailing | `eod_trail_intraday_breach` |
| DLL | not set (optional in the Combine) |
| max contracts | 5 mini / 50 micro (strategy uses 1) |
| days traded / profitable | 156 / 67 |
| **target reached** | **NO** |
| **MLL breached** | **YES — 2025-10-22** |
| breach detail | intraday equity 49,824 reached the MLL 50,000 |
| terminal stage | **liquidated** |
| minimum buffer to MLL | $962.74 |

The MLL had trailed up and locked at $50,000 after the July run carried EOD equity past
$52,000; the October drawdown then breached it intraday. The account was liquidated four and a
half months into the sample.

**The user's own governor is NOT a Topstep rule and is reported separately:** 146 sessions were
halted by it, of which **132 were the IB regime filter** refusing to trade at all, and 14 were
killswitch halts. Topstep halted the account once — terminally.

---

## 5. Time to target — Monte Carlo

10,000 paths, seed 20260917, **bootstrapping complete trading days** so within-day trade
clustering and the daily P&L distribution are preserved.

| | |
|---|---|
| median ending P&L | −$12,677 |
| p10 / p25 / p75 / p90 | −$19,801 / −$16,257 / −$8,872 / −$5,516 |
| P(negative) | **98.9%** |
| P(MLL breach before target) | **94.3%** |
| P(target before MLL) | 5.6% |
| median max drawdown / p90 | $14,354 / $20,993 |
| **P(target within 5 sessions)** | **0.01%** |
| **P(target within 10 sessions)** | **0.06%** |
| **P(target within 20 sessions)** | **0.36%** |

> **CONDITIONAL SIMULATION on the observed daily distribution.** Not a prediction of future
> profitability and not a probability of passing. It resamples 313 observed sessions; a
> strategy with a different edge would produce different numbers, and this one has a
> measured negative edge, so the simulation mostly restates that.

---

## 6. Econometric test

**Question.** Does a false breakout of the IB increase P(midpoint touch), given a 10–35 point
IB range?

**Design.** Unit = one eligible event. 675 false breakouts against 1,350 matched controls
(in-IB bars, same session, same 30-minute bucket, same barrier distance), over 158 sessions.
Terminal event: midpoint touched, versus stop level breached OR 60 minutes elapsed OR 15:45,
whichever first; the stop resolves first inside an ambiguous bucket.

**Raw touch rates: events 29.78%, controls 35.41%.**

Logit, cluster-robust (CR0) SEs on trading day:

| term | coef | robust SE | z | p | odds ratio | 95% CI (OR) |
|---|---|---|---|---|---|---|
| intercept | +1.8850 | 0.4023 | +4.69 | <0.0001 | 6.586 | [2.99, 14.49] |
| **false_breakout** | **+0.4109** | 0.0989 | **+4.15** | **0.00003** | **1.508** | **[1.242, 1.831]** |
| ib_range | −0.0390 | 0.0167 | −2.34 | 0.0195 | 0.962 | [0.931, 0.994] |
| distance_to_mid / range | −6.1376 | 0.6203 | −9.89 | <0.0001 | 0.002 | [0.001, 0.007] |
| minutes_since_ib | +0.0017 | 0.0018 | +0.98 | 0.327 | 1.002 | [0.998, 1.005] |
| direction | −0.0758 | 0.1040 | −0.73 | 0.466 | 0.927 | [0.756, 1.137] |

N = 2,025, clusters = 158, McFadden pseudo-R² = 0.116.

### The marginal and conditional answers have OPPOSITE SIGNS, and both are the answer

- **Unconditionally, a false breakout touches the midpoint LESS often** (29.8% vs 35.4%),
  because it starts at the IB edge and therefore further from the midpoint. Distance dominates
  everything: its coefficient is −6.14.
- **Holding distance fixed, a false breakout has ~1.5× the odds** of touching (OR 1.508,
  p = 0.00003).

So the mechanism the strategy is built on is **real but insufficient**. There is genuine
information in a false breakout — but it is not worth the extra distance the trade must travel
to collect it, and the stop sits between the two.

**Chronological out-of-sample** (train < 2026-04-20, 1,434 rows; test ≥, 591 rows): train
coefficient +0.4404 (p = 0.00035); test touch rate 29.4% events vs 37.3% controls — the same
sign and the same marginal gap. Test Brier 0.1964 against a base-rate Brier of 0.2268, so the
model carries some information out of sample.

**ASSOCIATION, NOT CAUSATION.** Controls are matched, not randomised. A bar that has just
broken the IB differs from one that has not in ways this specification does not observe.

`research/initial_balance_regression.R` is the specified deliverable and reproduces this
specification. **R is not installed in this environment**, so the numbers above were produced
by the equivalent Python estimator in `scripts/ib_event_study.py` (Newton-Raphson logit, CR0
cluster-robust sandwich). Running the R script independently is the check.

---

## 7. Ambiguity and data quality

| condition | count |
|---|---|
| ambiguous buckets (stop and target both touched) | **1** |
| trades decided by the stop-first convention | 1 |
| gap-through-stop trades | 0 |
| **same-bucket traps (B3)** | **232 of 262 trades (88.5%)** |
| **immediate-target trades (B4)** | **7** |
| sessions rejected by the data path | 14 of 327 |
| sessions skipped, IB out of regime | 132 |
| roll sessions inside a trade | 0 |

**B3 is the largest single interpretive fact in this backtest.** In 88.5% of trades the "trap"
and the "rejection" occur on the SAME 5-minute bucket: one bar pokes outside the IB and closes
back inside. The multi-bar excursion described in the specification is the exception, not the
rule, and `E` is therefore usually just that one bar's extreme. A reading that required a
*prior* bar to have traded outside would produce a different and much smaller strategy.

---

## 8. Verification

| | |
|---|---|
| goldens / causality / execution / governor | 38 / 18 / 56 / 23 = **135 tests** |
| independent reconciliation | **262 trades, 0 mismatches at 1e-9** against `reference_ledger` |
| hand-calculated contract-math scenarios | 25, all agreeing |
| CSV → daily → equity roll-up | exact |
| two identical runs | ledger, daily, statistics, equity, Topstep and seeded Monte Carlo **byte-identical**; only `run_utc` differs |
| mutation testing | **225 applied · 0 skipped · 225 caught · 100%** (32 new for this strategy) |

### The two mutations that survived the first pass

Reported because a mutation score is worth nothing without the story of its failures.

**`ib__killswitch_reads_the_close_not_the_adverse_extreme` — a genuine test hole.** The
golden test used a bucket whose low was 4984 and whose close was 4985. One point apart, so
BOTH readings of AMBIGUITY B6 tripped the -$800 threshold and the test could not distinguish
them. Replaced with a bucket where the low trips (-$862.50) and the close does not
(-$162.50), with the stop far enough below that no resting order stands in front of the
governor. The mutation is now caught on exactly that discrimination.

**`ib__a_consumed_excursion_can_be_traded_twice` — a near-no-op.** The engine closes every
trip on the same bucket that consumes it, so the `consumed` guard is unreachable from the bar
loop and removing it changed no engine output. It is still part of the `Excursion` contract -
one breakout, one entry, AMBIGUITY B7 - so it is pinned by a direct unit test of the object
rather than deleted on the grounds that nothing currently reaches it.

Neither test was weakened to make a mutation pass. Both add discrimination that was missing.

Result hashes (BASELINE_FROZEN): ledger `269a0595a1a35bb1`, daily `8168d21733e894f3`,
summary `3083c2ad3e1cb867`.

---

## 9. Limitations

1. **313 sessions, 15 months, one venue.** 262 trades is enough to call this negative with
   confidence, and not enough to characterise the tails.
2. **The regime filter stands the strategy down on 42% of sessions.** ES IB ranges have a
   median of 30.5 points and a 75th percentile of 43.75, so the 10–35 window excludes most of
   the upper half of the distribution. In three months it left 1–5 trades.
3. **Gap-through-stop fills at the stop level** — declared, optimistic, and untested here
   because no trade gapped.
4. **Partial fills, queue position and market impact are not modelled.**
5. **The 14 refused sessions** are refused on measured shape; no holiday calendar exists in
   the repository and none was invented.
6. **The Monte Carlo resamples one negative-edge sample.** Its percentiles describe that
   sample re-ordered.

---

## 10. Reproducing

```powershell
python scripts/backtest_initial_balance.py --out research/ib_reversion
python scripts/ib_event_study.py --out research/ib_reversion
Rscript research/initial_balance_regression.R     # R not installed here
python -m pytest tests/test_initial_balance_*.py -q
python scripts/engine_mutation_test.py
```

Artefacts: `research/ib_reversion/backtest.json`, `ledger_<PROFILE>.csv`, `ib_events.csv`,
`ib_event_study.json`.
