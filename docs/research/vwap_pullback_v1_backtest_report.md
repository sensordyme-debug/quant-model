# STRATEGY: VWAP_PULLBACK V1.0.0_FROZEN

# STATUS: HISTORICAL BACKTEST COMPLETE

No parameter was changed, no filter added, no trade removed, no sweep run, no instrument or
date selected after seeing a result. No order was transmitted and no live endpoint was
contacted.

---

## 1. Executive summary

**The strategy almost never triggers. On 311 NQ sessions it took 8 trades; on 252 MNQ
sessions it took 5.** That is 0.026 trades per session on NQ — **one trade per 39 sessions**,
about one every eight trading weeks — and 0.020 on MNQ, one per 50 sessions. Everything else
in this report is downstream of that number and inherits its weakness.

| | NQ (1 contract) | MNQ (10 contracts) |
|---|---|---|
| sessions | 311 | 252 |
| **trades** | **8** | **5** |
| net P&L (BASELINE_FROZEN) | **+$39.00** | **+$1,129.00** |
| win rate | 37.5% (3/8) | 60.0% (3/5) |
| profit factor | 1.03 | 2.78 |
| max drawdown | $1,152 | $634 |
| months with ≥1 trade | 6 of 16 | 5 of 13 |
| positive months | 2 of 16 (12.5%) | 3 of 13 (23.1%) |
| reached the $3,000 Combine target | **no** | **no** |
| Topstep MLL breach | none | none |

Three findings dominate, and none of them is about profitability:

**(a) The sample is too small to support any conclusion.** Eight trades produce a profit
factor of 1.03 on NQ; five produce 2.78 on MNQ. Both numbers are noise. Removing NQ's single
best trade turns +$39 into −$557.

**(b) The two instruments disagree almost completely.** NQ and MNQ track the same index at
near-identical prices, and on the 252 sessions they share they produce trades on only **2 of
11 dates — a 20% overlap.** The trade set is not a property of the market; it is a property
of which contract's tape was sampled. NQ says "flat"; MNQ says "+$1,129". Neither is evidence.

**(c) Most of the frozen specification was never exercised.** Only two exit reasons ever
fired: `stop` and `target`. The break-even stop armed three times and never closed a trade.
The stall rule fired once and never closed a trade. The −$800 killswitch, the +$1,200 profit
cap, the 4-trade cap, the 2-loss cooldown and the 15:45 forced flatten **never fired at all**.
Those rules are certified against synthetic bars and remain untested against the market.

The engine, the data path and the accounting are sound — reconciliation agrees to 1e-9 and
the run is bit-identical across invocations. The problem is the evidence, not the machinery.

---

## 2. Exact strategy and spec hash

```
strategy            V1.0.0_Frozen
spec hash NQ        1fe36d12eb631c96        1 contract    $20.00/point   $4.50 RT
spec hash MNQ       08c19f55b6382d72       10 contracts   $20.00/point  $12.20 RT
clock               America/New_York
unresolved material ambiguities                           NONE
```

No ambiguity in the frozen specification affected a trade decision during this run. The two
registered characteristics (C9/C10, the proximity inequalities that admit a 5-minute bar
lying entirely on one side of VWAP) were active — see §16 — but they loosen the *arming*
stage, which is not the binding constraint.

---

## 3. Dataset manifest

| | NQ | MNQ |
|---|---|---|
| manifest id | `9c4bb5d370e4a7e3` | `89d97f6f8c6405f9` |
| content hash | `c11d90747fc74b1d` | `73aeee0314a4d7c0` |
| file sha256 | `4a6b0a7754622d07…` | `a47c3f9541205057…` |
| bytes / rows | 7,565,738 / 447,596 | 6,133,258 / 358,845 |
| trading days | 2025-06-09 → 2026-09-10 | 2025-09-08 → 2026-09-10 |
| usable sessions | **311** | **252** |
| refused sessions | 16 | 10 |
| contract coverage | NQU5, NQZ5, NQH6, NQM6, NQU6 | MNQZ5, MNQH6, MNQM6, MNQU6 |
| loader | `vwap-anchored-1.0.0` | same |
| adjustment | CONTINUOUS_UNADJUSTED / NONE | same |

```
git             f4f9bcd87615e7e50372de6d44f6fc29b3fb646a   (clean)
python          3.14.7   Windows-11-10.0.26200-SP0
numpy / pandas  2.5.3 / 3.0.5
```

Every session carried its full 18:00 ET → 15:45 ET anchored window (1,306 one-minute bars);
the RTH-only loader was not used anywhere. Refused sessions were excluded by the certified
completeness rule and carry `INCOMPLETE_SESSION`, never a calendar classification.

---

## 4. Execution assumptions

| profile | entry | stop | target | market exit | spec hash | = V1.0.0 |
|---|---|---|---|---|---|---|
| IDEAL | 0 | 0 | 0 | 0 | `b74e341cf6d0a814` | no |
| **BASELINE_FROZEN** | **1** | **1** | **0** | **0** | `1fe36d12eb631c96` | **yes** |
| STRESS_1TICK | 1 | 2 | 0 | 1 | `b082e80535b50eaa` | no |
| STRESS_2TICK | 1 | 3 | 0 | 2 | `640f87b5d65d8168` | no |

Ticks of adverse slippage. BASELINE_FROZEN is the headline.

### Bar-level interpretation, written out

- **Trigger-bar execution.** The trigger is decided on information available at the 1-minute
  bar's *close*: its own OHLCV, the VWAP and volume SMA updated through it, the last
  *completed* 5-minute bucket, and the previous bar's high/low. Entry fills at that close
  plus one tick adverse. No later bar is consulted.
- **15:45 flatten.** Executed *on* the 15:45 bar at its close. The bar is the decision point,
  not a look-ahead: the rule is time-based and fires because the clock reached 15:45, not
  because of anything the close revealed. (Not exercised historically — no trade survived to
  15:45.)
- **Stop/target same-bar ambiguity.** Written precedence: **stop before target.** If one bar
  touches both levels, the stop is taken. **0 trades were affected** in this run.
- **Gap through a stop.** Fills **at the stop level**, not at the gap price. This is the
  repository's declared policy and it is optimistic. 0 trades were affected.
- **Break-even.** Arms at the *end* of the bar whose excursion reached +15 points, so the
  original stop is in force for the whole of that bar (AMBIGUITY A15). Armed 3 times on NQ
  and 3 on MNQ; closed nothing.
- **Stall rule.** The +25 MFE bar is identified from that bar's own extreme. Three
  *subsequent completed* closes are then required before the target moves to +20. The
  modified target never applies retroactively to an earlier bar. Fired once on NQ.
- **Market-exit pricing.** Flatten, governor-flatten and stall-close price at the bar close
  plus the profile's market-exit ticks. Zero in BASELINE by the frozen spec — which is not a
  claim that those exits are frictionless, only a refusal to invent a number; STRESS_1TICK
  and STRESS_2TICK measure the gap.
- **Zero-volume bars.** Kept, and weightless: `TP × 0 = 0` contributes nothing to the
  volume-weighted average. They are never dropped, repaired or substituted. NQ traded through
  19 sessions containing at least one (2,045 bars); MNQ through 8 (1,173 bars).

---

## 5. NQ results — 1 contract, BASELINE_FROZEN

| id | date | dir | entry ET | entry | exit ET | exit | reason | net | R | min |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2025-07-07 | SHORT | 10:27 | 22,955.75 | 10:31 | 22,925.75 | target | +595.50 | +1.99 | 4 |
| 2 | 2025-10-29 | SHORT | 13:17 | 26,259.00 | 13:25 | 26,229.00 | target | +595.50 | +1.99 | 8 |
| 3 | 2025-12-05 | LONG | 13:44 | 25,735.50 | 13:51 | 25,720.25 | stop | −309.50 | −1.03 | 7 |
| 4 | 2025-12-10 | LONG | 12:12 | 25,633.00 | 12:20 | 25,617.75 | stop | −309.50 | −1.03 | 8 |
| 5 | 2025-12-22 | SHORT | 14:34 | 25,705.75 | 15:22 | 25,685.75 | target* | +395.50 | +1.32 | 48 |
| 6 | 2026-03-23 | LONG | 12:28 | 24,361.25 | 12:29 | 24,346.00 | stop | −309.50 | −1.03 | 1 |
| 7 | 2026-05-29 | LONG | 13:24 | 30,378.75 | 13:25 | 30,363.50 | stop | −309.50 | −1.03 | 1 |
| 8 | 2026-08-31 | SHORT | 10:59 | 29,415.75 | 11:00 | 29,431.00 | stop | −309.50 | −1.03 | 1 |

\* trade 5 is the one stall-rule activation: target moved from +30 to +20.

```
gross +$140.00   commission $36.00   slippage $65.00   NET +$39.00
by direction   SHORT 4 trades +$1,277.00      LONG 4 trades −$1,238.00
by exit        target 3 = +$1,586.50          stop 5 = −$1,547.50
MFE mean $273.75   MAE mean −$350.00
median holding 5.5 min   mean 9.75 min
```

Slippage is $5.00 per tick (0.25 tick x $20/point): eight entries at one tick plus five
stop-outs at one tick = $65.00.

Four of the five losers were stopped within one to eight minutes. Every long lost.

## 6. MNQ results — 10 contracts, BASELINE_FROZEN

| id | date | dir | entry ET | entry | exit ET | exit | reason | net | R | min |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2025-09-09 | LONG | 12:53 | 24,046.00 | 13:06 | 24,076.00 | target | +587.80 | +1.96 | 13 |
| 2 | 2025-10-29 | SHORT | 13:17 | 26,259.00 | 13:25 | 26,229.00 | target | +587.80 | +1.96 | 8 |
| 3 | 2026-05-29 | LONG | 13:24 | 30,378.75 | 13:25 | 30,363.50 | stop | −317.20 | −1.06 | 1 |
| 4 | 2026-07-08 | SHORT | 12:24 | 29,258.00 | 12:25 | 29,273.25 | stop | −317.20 | −1.06 | 1 |
| 5 | 2026-08-19 | SHORT | 14:04 | 29,562.50 | 14:06 | 29,532.50 | target | +587.80 | +1.96 | 2 |

```
gross +$1,225.00   commission $61.00   slippage $35.00   NET +$1,129.00
by exit  target 3 = +$1,763.40    stop 2 = −$634.40
MFE mean $427.00   MAE mean −$234.00
median holding 2 min   mean 5.0 min
```

Slippage is $5.00 per tick, as on NQ (0.25 tick x $20/point for the ten-lot): five entries
plus two stop-outs = $35.00. Commission is the only place the two instruments differ on cost
($4.50 versus $12.20 per round turn), which is AMBIGUITY A11 — the frozen spec states a rate
for NQ only and the repository's measured MNQ rate is used.

### The instrument equivalence check (required, and it fails)

NQ (1 contract, $20/pt) and MNQ (10 contracts, $20/pt) are intended to be the same dollar
exposure on the same index, and their prices confirm it — on the two shared dates both
entered at *identical* prices (26,259.00 and 30,378.75).

**On the 252 sessions both stores cover:**

| | |
|---|---|
| NQ trade dates | 7 |
| MNQ trade dates | 5 |
| **shared** | **2** |
| NQ-only | 5 |
| MNQ-only | 3 |
| **Jaccard overlap** | **20.0%** |

Why they diverge, measured on 2026-07-08 (an MNQ-only trade): the two tapes have identical
closes on only **13.6%** of the session's 1,306 bars, mean absolute close difference **0.66
points**, and MNQ's volume runs **~7.2×** NQ's. The frozen trigger is knife-edge on all three
axes — a 10-point zone around VWAP, a breakout of the previous bar's high/low, and volume
against *that contract's own* 10-bar average — so sub-tick tape differences flip individual
decisions.

**This is the single most important result in the report.** A strategy whose trade set
survives the choice of contract would produce nearly the same dates on both. This one does
not, and the P&L conclusions invert: NQ is flat, MNQ is up $1,129.

---

## 7. Execution ladder

| run | trades | net | PF | win | max DD | target hits | + months |
|---|---|---|---|---|---|---|---|
| NQ IDEAL | 8 | +$64.00 | 1.042 | 37.5% | $1,127 | 3 | 2/16 |
| **NQ BASELINE_FROZEN** | 8 | **+$39.00** | 1.025 | 37.5% | $1,152 | 3 | 2/16 |
| NQ STRESS_1TICK | 8 | +$14.00 | 1.009 | 37.5% | $1,177 | 3 | 2/16 |
| NQ STRESS_2TICK | 8 | **−$11.00** | 0.993 | 37.5% | $1,202 | 3 | 2/16 |
| MNQ IDEAL | 5 | +$1,139.00 | 2.824 | 60.0% | $624 | 3 | 3/13 |
| **MNQ BASELINE_FROZEN** | 5 | **+$1,129.00** | 2.780 | 60.0% | $634 | 3 | 3/13 |
| MNQ STRESS_1TICK | 5 | +$1,119.00 | 2.737 | 60.0% | $644 | 3 | 3/13 |
| MNQ STRESS_2TICK | 5 | +$1,109.00 | 2.695 | 60.0% | $654 | 3 | 3/13 |

**NQ crosses from positive to negative between BASELINE and STRESS_2TICK.** Its entire 15-month
result is $39, and two extra ticks of stop slippage is $50 — the result is smaller than the
execution assumption. NQ's answer is therefore set by the slippage model, not by the market.

MLL breaches: 0 in every profile. Combine passes: 0 in every profile. Positive-month share:
unchanged across the ladder, because the ladder moves cents and the months are decided by
whether a trade happened at all.

Degradation per stress step is exactly $25 (NQ) and $10 (MNQ) per step — one tick of stop
slippage on the losers plus one tick of market-exit slippage on nothing, since no market exit
ever fired. The ladder is therefore **only measuring the stop**, which is itself a finding: the
three unpriced market exits could not be stressed because they never occurred.

---

## 8. Trade statistics (BASELINE_FROZEN)

| | NQ | MNQ |
|---|---|---|
| total trades / sessions | 8 / 311 | 5 / 252 |
| trades per session (mean) | 0.0257 | 0.0198 |
| trades per session (median) | 0 | 0 |
| sessions with a trade | 8 | 5 |
| gross / commission / slippage | +$140.00 / $36.00 / $65.00 | +$1,225.00 / $61.00 / $35.00 |
| **net P&L** | **+$39.00** | **+$1,129.00** |
| avg / median $ per trade | +$4.88 / −$309.50 | +$225.80 / +$587.80 |
| win / loss rate | 37.5% / 62.5% | 60.0% / 40.0% |
| avg winner / avg loser | +$528.83 / −$309.50 | +$587.80 / −$317.20 |
| payoff ratio | 1.708 | 1.853 |
| expectancy per trade | +$4.88 | +$225.80 |
| profit factor | 1.025 | 2.780 |
| max consecutive wins / losses | 2 / 3 | 2 / 2 |
| largest winner / loser | +$595.50 / −$309.50 | +$587.80 / −$317.20 |
| median / mean holding (min) | 5.5 / 9.75 | 2 / 5.0 |
| MFE mean / MAE mean | $273.75 / −$350.00 | $427.00 / −$234.00 |
| avg R / median R | +0.016 / −1.03 | +0.752 / +1.96 |
| R p05 / p95 | −1.03 / +1.97 | −1.06 / +1.96 |
| daily P&L mean / median | +$0.13 / $0.00 | +$4.48 / $0.00 |
| worst / best session | −$309.50 / +$595.50 | −$317.20 / +$587.80 |
| positive / negative sessions | 3 / 5 | 3 / 2 |

Descriptive breakdowns (NQ): **direction** SHORT 4 = +$1,277, LONG 4 = −$1,238;
**weekday** Mon 4 = +$372, Wed 2 = +$286, Fri 2 = −$619; **hour ET** 10:00 = +$286,
12:00 = −$619, 13:00 = −$24, 14:00 = +$396. With 8 trades every cell is one or two
observations. **These are descriptive only. No filter was derived from them.**

---

## 9. Monthly statistics — NQ, BASELINE_FROZEN

| month | sessions | trades | net | return on $50k | max intra-month DD |
|---|---|---|---|---|---|
| 2025-06 | 13 | 0 | $0.00 | 0.000% | $0.00 |
| 2025-07 | 21 | 1 | +$595.50 | +1.191% | $0.00 |
| 2025-08 | 21 | 0 | $0.00 | 0.000% | $0.00 |
| 2025-09 | 21 | 0 | $0.00 | 0.000% | $0.00 |
| 2025-10 | 23 | 1 | +$595.50 | +1.191% | $0.00 |
| 2025-11 | 18 | 0 | $0.00 | 0.000% | $0.00 |
| 2025-12 | 21 | 3 | −$223.50 | −0.447% | $619.00 |
| 2026-01 | 20 | 0 | $0.00 | 0.000% | $0.00 |
| 2026-02 | 19 | 0 | $0.00 | 0.000% | $0.00 |
| 2026-03 | 22 | 1 | −$309.50 | −0.619% | $309.50 |
| 2026-04 | 21 | 0 | $0.00 | 0.000% | $0.00 |
| 2026-05 | 20 | 1 | −$309.50 | −0.619% | $309.50 |
| 2026-06 | 21 | 0 | $0.00 | 0.000% | $0.00 |
| 2026-07 | 22 | 0 | $0.00 | 0.000% | $0.00 |
| 2026-08 | 21 | 1 | −$309.50 | −0.619% | $309.50 |
| 2026-09 | 7 | 0 | $0.00 | 0.000% | $0.00 |

```
months 16          mean +$2.44        median $0.00
mean return +0.005%                   median return 0.000%
stdev of monthly return 0.528%
positive 2 (12.5%)  negative 4 (25.0%)  FLAT, NO TRADES AT ALL 10 (62.5%)
best +$595.50   worst −$309.50   p25 −$232.13   p75 $0.00
```

**SAMPLE SIZE: 16 months, of which 10 contain no trade whatsoever.** A 15-month window is not
an estimate of long-run monthly performance and must not be read as one. The median month is
$0.00 because the median month has no trades.

---

## 10. Drawdown analysis

Built from the canonical ledger; there is no second P&L calculation anywhere in this report.

| | NQ | MNQ |
|---|---|---|
| **A. strategy P&L** | **+$39.00** | **+$1,129.00** |
| **B. simulated Combine balance** | **$50,039.00** | **$51,129.00** |
| starting balance | $50,000.00 | $50,000.00 |
| max drawdown $ / % of start | $1,152.00 / 2.304% | $634.40 / 1.269% |
| drawdown window | 2025-10-30 → 2026-08-31 | 2025-10-30 → 2026-07-08 |
| max drawdown duration | 207 sessions | 169 sessions |
| recovery after worst | never recovered in sample | never recovered in sample |
| worst session | −$309.50 | −$317.20 |
| worst week (Mon-start) | −$309.50 (w/c 2025-12-01) | −$317.20 (w/c 2026-05-25) |
| worst month | −$309.50 | −$317.20 |
| max intraday adverse excursion | −$365.00 | −$465.00 |
| **C. Topstep MLL state** | never breached; min buffer **$848.00** | never breached; min buffer **$1,365.60** |

A/B/C are three different quantities. **A** is what the strategy made. **B** is
`$50,000 + A`. **C** is the distance the trailing limit came to being hit, which is not
derivable from A or B.

---

## 11. Topstep $50K Combine simulation

The canonical ledger was replayed through the certified twin. No second trade simulation was
built.

```
source retrieved            2026-09-12
starting balance            $50,000
profit target               $3,000
maximum loss limit          $2,000        trailing: eod_trail_intraday_breach
MLL locks at start balance  yes           MLL resets to start on each payout: yes
daily loss limit            not set       (optional in the Combine)
DLL window (CT)             17:00 - 15:10
contract limit              5 mini / 50 micro
mandatory flat (CT)         15:10
minimum trading days        0
consistency reading         doc_calc (55% of TOTAL profits, inclusive boundary)
```

| | NQ | MNQ |
|---|---|---|
| sessions stepped | 311 | 252 |
| terminal stage | trading_combine | trading_combine |
| passed the Combine | **no** | **no** |
| breaches | **none** | **none** |
| MLL breach timestamp / balance | — | — |
| min buffer to MLL | $848.00 | $1,365.60 |
| final balance | $50,039.00 | $51,129.00 |

The account never passed and never breached. It sat in the Combine for the whole sample.
The strategy's own exits always closed positions before any Topstep limit was approached —
the largest single-session loss was one $309.50 stop against a $2,000 MLL.

### The user's internal governor (NOT Topstep rules)

| user rule | NQ | MNQ |
|---|---|---|
| −$800 mark-to-market killswitch | **0 events** | **0 events** |
| +$1,200 daily profit cap | **0 events** | **0 events** |
| 4-trade daily cap | **0 events** (max 1 trade/session) | **0 events** |
| 2-consecutive-loss breaker | **0 events** (max streak reached 1 within a day) | **0 events** |
| 45-minute cooldown | **0 events** | **0 events** |
| 15:30 entry cutoff | never bound — latest entry 14:34 ET | never bound — latest 14:04 ET |
| 15:45 forced flatten | **0 exits** — no trade lasted to 15:45 | **0 exits** |

These are the owner's private risk rules and are stricter than Topstep's. **None of them ever
fired on historical data.** They remain certified against synthetic bars only.

---

## 12. Historical path pass analysis

Every session start was walked forward to the end of the sample (starts with fewer than 20
remaining sessions are reported as insufficient rather than dropped, so nothing selects for
starts that resolved).

| | NQ | MNQ |
|---|---|---|
| attempts evaluated | 292 | 233 |
| attempts insufficient | 19 | 19 |
| **PASS** | **0** | **0** |
| MLL breach first | 0 | 0 |
| DLL breach first | 0 | 0 |
| unfinished at sample end | 292 | 233 |
| **HISTORICAL PATH PASS RATE** | **0.0%** | **0.0%** |

**This is a HISTORICAL PATH PASS RATE, not a probability of passing.** The 292 paths overlap
almost completely and share the same eight trades; they are not independent attempts. The
honest statement is simpler than the table: **on this sample the account never reached $3,000
from any starting point, and never lost $2,000 either.** It did essentially nothing.

---

## 13. Payout eligibility simulation

Policy version: `doc_calc` — best single day at or below **55% of total profits**, inclusive
boundary, retrieved 2026-09-12.

| | NQ | MNQ |
|---|---|---|
| winning days (net > $0) | 3 | 3 |
| total net profit | $39.00 | $1,129.00 |
| profit target | $3,000 | $3,000 |
| **target reached** | **no** | **no** |
| best single day | $595.50 | $587.80 |
| consistency satisfied | **no** | yes |
| effective target given best day | $1,082.73 | $1,068.73 |
| payout opportunities | **0** | **0** |
| amount eligible | $0.00 | $0.00 |
| days to first eligibility | n/a | n/a |

**No payout occurs, and not merely because $3,000 was not reached.** On NQ the consistency
rule is independently violated: a $595.50 best day against $39.00 of total profit is 1,527%
of total, far beyond the 55% ceiling, so even a hypothetical account at the target would fail.
Reaching $3,000 is necessary and not sufficient — this run demonstrates both halves.

Because no payout ever occurs, the post-withdrawal balance, the MLL-after-withdrawal
relationship and future payout eligibility are all undefined in this sample.

---

## 14. Monte Carlo — conditional historical resampling

Seed `20260916`, 2,000 reps for A–C, 200 for D. Resampled from the observed ledger; no trade
was manufactured and nothing was optimised inside the simulation.

### NQ (resampling **8 distinct trades** / 311 sessions)

| method | median | p05 | p25 | p75 | p95 | P(neg) | P(MLL) | P(target first) |
|---|---|---|---|---|---|---|---|---|
| A trade bootstrap | +$39 | −$1,771 | — | — | +$1,849 | 46.0% | 4.0% | 1.1% |
| B daily bootstrap | +$16 | −$1,857 | — | — | +$2,070 | 49.4% | 5.1% | 1.4% |
| C moving block (20) | +$80 | −$1,571 | — | — | +$2,049 | 45.4% | 3.9% | 0.8% |

max drawdown: median $1,041 / p95 $2,344 (A). D — Topstep path simulation, 200 resampled
paths through the certified twin: **1 passed, 8 breached, 191 unfinished.**

### MNQ (resampling **5 distinct trades** / 252 sessions)

| method | median | p05 | p95 | P(neg) | P(MLL) | P(target first) |
|---|---|---|---|---|---|---|
| A trade bootstrap | +$1,129 | −$681 | +$2,939 | 8.8% | 0.0% | 0.0% |
| B daily bootstrap | +$1,082 | −$681 | +$2,939 | 17.2% | 0.1% | 5.3% |
| C moving block (20) | +$541 | −$952 | +$2,034 | 34.0% | 0.1% | 0.2% |

D: **1 passed, 0 breached, 199 unfinished.**

**These are conditional historical resampling estimates and not probabilities of future
success.** With eight and five distinct trades the bootstrap is drawing from eight and five
numbers; the percentile spread describes those numbers, not the strategy. The gap between
MNQ's A/B (+$1,100) and C (+$541) is itself a warning — once short-run ordering is preserved,
half the apparent edge disappears, which is what one expects when three winners happen to be
adjacent.

---

## 15. Withdrawal-path Monte Carlo

Four policies were run through the twin: no withdrawal, first-eligible-full, first-eligible
keeping a $1,000 buffer, and repeated-half.

| policy | funded | payouts | paid out | final balance | MLL breach |
|---|---|---|---|---|---|
| no withdrawal | no | 0 | $0.00 | $50,039 / $51,129 | none |
| first eligible, full | no | 0 | $0.00 | identical | none |
| first eligible, keep $1,000 | no | 0 | $0.00 | identical | none |
| repeated half | no | 0 | $0.00 | identical | none |

**All four are identical, and the comparison is therefore uninformative.** The account never
passes the Combine, so it never becomes funded, so no withdrawal is ever possible under any
policy. The previously-audited effect — that a payout resets the MLL to the starting balance
and so spends the buffer keeping the account alive — **could not be exercised by this
strategy**. That is a statement about this backtest, not a retraction of the finding.

---

## 16. Ambiguity and data-quality report

| condition | NQ | MNQ |
|---|---|---|
| ambiguous stop/target bars (both touched) | **0** | **0** |
| gap-through-stop trades | **0** | **0** |
| trades on sessions containing zero-volume bars | 0 of 8 | 0 of 5 |
| sessions traded that contain a zero-volume bar | 19 of 311 (2,045 bars) | 8 of 252 (1,173 bars) |
| incomplete sessions excluded | 16 | 10 |
| roll sessions excluded | 0 — no anchored session spans a roll | 0 |
| upstream data-quality status | WARN (attributed, §3 of the data certification) | WARN |
| trades affected by a WARN condition | 0 | 0 |

**Frozen rules that never fired on historical data**, and therefore remain tested only against
synthetic bars: break-even *exit* (armed 3+3, closed 0), stall market-close (fired 1 on NQ,
closed 0), −$800 killswitch, +$1,200 profit cap, 4-trade cap, 2-loss cooldown, 45-minute
cooldown, 15:45 forced flatten, and every governor halt path.

**C9/C10 were active.** The 5-minute proximity inequalities admitted bars lying entirely on
one side of the VWAP, which is why the strategy *armed* on ~24% of bars while trading on
0.03%. The binding constraint was elsewhere — see below.

### Why the strategy trades so rarely (measured, not inferred)

Funnel over 406,166 NQ bars:

```
entry-window bars with a ready VWAP               107,606
  5-minute regime armed                            98,950   ATR gate rejected only 21
    trigger actually evaluated                     98,346   (the rest: already in position)
      volume >= 1.2x SMA(10)                       21,600   78.0% rejected
        1-minute close inside the VWAP zone           564   97.4% rejected  <-- BINDING
          touched VWAP, correct colour, breakout        8
```

The zone requires the 1-minute close within **VWAP−8..+2** (long) or **VWAP−2..+8** (short).
Measured over 107,606 entry-window bars, NQ's distance from its own session VWAP has median
**73 points** and p95 **256 points**; only **3.6%** of bars fall inside the long zone. A
10-point window on a 22,000-index is 0.045% — the parameters behave like ES-scale distances
applied to an NQ-scale instrument. **This is a property of the frozen specification, not a
defect**: the VWAP, the ATR and the session are all correct, and the strategy simply requires
a configuration the market rarely presents.

---

## 17. Independent reconciliation

Every trade was recomputed through `quant_brain.research.reference_ledger`, which shares no
code with the strategy engine — plain Python arithmetic, explicit cost per contract per leg.

| | result |
|---|---|
| runs checked | 8 (2 instruments × 4 profiles) |
| trades checked | 52 |
| fields per trade | gross_pnl, commission, slippage_cost, net_pnl |
| daily roll-ups checked | 2,252 sessions |
| equity totals checked | 8 |
| tolerance | 1e-9 |
| **mismatches** | **0** |
| **verdict** | **AGREES** |

### Reproducibility

The full backtest was run twice from a clean tree:

| run | ledger hash | daily hash | summary hash | identical |
|---|---|---|---|---|
| NQ BASELINE_FROZEN | `6109c1980d364ce3` | `0805334f113b55e8` | `6c3b1cb009f2a011` | yes |
| NQ IDEAL | `6a87fdc93b956e18` | `7bc87620d530a11d` | `2587220d43d6de8c` | yes |
| NQ STRESS_1TICK | `af3fe33099fa97f4` | `352d33e39fabe5e0` | `4490cbbac5f3f171` | yes |
| NQ STRESS_2TICK | `8123068adb9d3e73` | `5aceaddee6a63176` | `94e6659a302fc327` | yes |
| MNQ BASELINE_FROZEN | `8502322c4dcc0d0c` | `4d985217ac03378f` | `8bce2949b20082a6` | yes |
| MNQ IDEAL | `1a1c3c28d21d87fd` | `fd3524c94671c6b7` | `c111dbb2983bb7ad` | yes |
| MNQ STRESS_1TICK | `a4a9bfe105731041` | `2f7c96349166c0ec` | `b63c5262f22ae26d` | yes |
| MNQ STRESS_2TICK | `0cda253c133b21b3` | `c4f77524aa43e06f` | `e621b3b7bc3347ce` | yes |

The only field that differed between the two invocations was `seconds` (wall-clock runtime).

---

## 18. Limitations

1. **8 and 5 trades.** No statistic computed from them is reliable. Confidence intervals on a
   37.5% win rate with n=8 span essentially the whole unit interval.
2. **The two instruments disagree on 80% of trade dates** (§6). This is the strongest single
   argument that the observed trades are noise.
3. **10 of 16 NQ months contain no trade at all.** "Monthly performance" is mostly the
   performance of not trading.
4. **Most of the frozen rule set was never exercised** (§16). A backtest that never fires the
   killswitch has not tested the killswitch.
5. **NQ's sign is decided by the execution assumption**: +$39 at BASELINE, −$11 at
   STRESS_2TICK. The result is smaller than the uncertainty in the cost model.
6. **The Combine was never passed and never breached**, so the Topstep layer, the payout
   layer and the withdrawal-policy comparison are all untested by this strategy.
7. **15 months, one venue, one regime.** The store spans 2025-06 → 2026-09 only.
8. **Gap-through-stop fills at the stop level** — optimistic, and untested here because no
   trade gapped. Every exit in this run was a clean stop or target touch.
9. **Partial fills, queue position, market impact and rejections are not modelled.** With
   1-contract NQ this is a small concern; it is not zero.
10. **The moving-block Monte Carlo halves MNQ's edge** relative to the iid bootstrap, which is
    what adjacent-winner clustering looks like.

---

## 19. Reproducibility commands

```powershell
python scripts/vwap_release.py --verify                       # spec + dataset identifiers
python scripts/vwap_backtest.py --all --out research/vwap_v1  # the deterministic run
python scripts/vwap_analyze.py                                # twin, passes, payout, MC
```

Artefacts: `research/vwap_v1/backtest.json`, `analysis.json`, and per-run
`ledger_<INSTRUMENT>_<PROFILE>.csv` / `daily_<INSTRUMENT>_<PROFILE>.csv`.

---

## 20. FINAL DECISION GATE — the strategy, not the engine

### `YELLOW`

The methodology is sound. The ledger reconciles to 1e-9 against an independent
implementation, the run is bit-identical across invocations, execution assumptions are
explicit and laddered, the Topstep path is valid, no lookahead was found, and the frozen rules
were followed exactly — no parameter was touched.

The **evidence** is what fails, on four of the YELLOW criteria at once:

- **very few trades** — 8 and 5 over 15 months;
- **insufficient history** — 10 of 16 months contain no trade;
- **execution-sensitive** — NQ changes sign across the declared ladder;
- **historical edge inconsistent** — 20% trade-date overlap between two instruments tracking
  the same index, with opposite P&L conclusions.

It is not RED: nothing about the machinery is broken, and the low trade count was traced to a
measured property of the specification (§16) rather than to a defect.

**Plainly: this is economically poor as it stands.** Not because it loses money — on this
sample it makes $39 on NQ and $1,129 on MNQ — but because it produces too few observations to
distinguish either outcome from zero, and the two instruments that should agree do not. A
strategy that trades once every six weeks needs years of history before its win rate means
anything, and this store holds fifteen months.

The most actionable measured fact, offered as an observation and **not** as a change: the
binding constraint is the ±8/±2-point VWAP zone, which admits 3.6% of NQ bars because NQ sits
a median 73 points from its session VWAP. Whether that zone is intended at NQ's price scale is
a question for you. **No parameter was altered, no alternative was tested, and no sweep was
run.**

GREEN would require more history, or an instrument and zone that produce enough trades to
measure. Neither is a change I will make.
