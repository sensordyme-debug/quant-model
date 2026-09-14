# TOPSTEP STATUS — morning of 2026-09-14

## OVERALL STATUS: BLOCKED ON ONE THING, AND THE RESEARCH SAYS NO

Two headlines, and they are independent.

**Your ProjectX API key does not authenticate.** The venue returns `errorCode 3`,
`InvalidCredentials`. This is not a bug in the repository: the request reaches
`api.topstepx.com`, is accepted as well-formed, and is rejected on the credential pair
itself. Everything downstream of authentication is blocked on you.

**The strategy tournament found nothing, and that is a real result, not a shortfall.**
240 trials across 7 mechanism families, 4 instruments and 3 temporal splits on real minute
data. Zero cleared the multiplicity-corrected significance bar. One cleared the uncorrected
bar and then went negative out of sample. The final holdout was never touched.

---

## Gates

| | status | why |
|---|---|---|
| ProjectX auth | **FAIL** | `errorCode 3 InvalidCredentials`. Key or username wrong, or key not active |
| Account binding | **BLOCKED** | code written and tested; cannot verify against the venue |
| Historical data (ProjectX) | **BLOCKED** | needs auth |
| Historical data (on disk) | **PASS** | 1,612,886 real minute bars, ES/NQ/MES/MNQ, already validated |
| Realtime data | **BLOCKED** | needs auth |
| Backtest engine | **PASS** | post-fix; round turns, costs at the trading bar, leakage gate all verified |
| Data quality | **PASS** | 0 duplicates, 0 bad OHLC, 0 interior gaps across all four stores |
| Topstep simulator | **PASS** | rules model repaired; path reconstruction bug found, fixed and hand-tested |
| Strategy candidate | **FAIL** | 0 of 240 survived. See below |
| Shadow mode | **BLOCKED** | needs realtime, needs auth |
| Practice ready | **NO** | |
| Combine ready | **NO** | |

Order transmission stayed off all night. `/api/Order/place` was never called and cannot be
reached: the new read-only client holds a closed allow-list of 11 endpoints and refuses
before a socket opens. Nothing was pushed. Nothing was committed.

---

## Best strategy found

**None.** That is the finding, and a clean rejection is worth more than a manufactured
winner.

The nearest thing to a candidate, for completeness:

| | |
|---|---|
| Strategy | `INV::breakout.opening_range.q95` — fade a 95th-percentile opening-range break |
| Symbol | NQ, sized in MNQ |
| Timeframe | 1 minute, RTH 09:30–15:45 ET |
| Train net | +$757 over 156 sessions |
| Validation net | +$2,188 over 78 sessions, t = 1.99 |
| **Test net** | **−$1,018, t = −1.11** |
| Win rate | 24% |
| Profit factor | 3.32 |
| Max drawdown | −$508 |
| Topstep pass probability | 0.213 (valid, post-fix) |

It fails out of sample. The multiplicity-corrected bar at 240 trials is |t| = 3.71; this
reached 1.99 on the split it was selected on and went negative on the split it was not.

**Pass probabilities are now valid, and they were not this morning.** The audit's suspicion
was right and understated. `paths._rebuild` rescaled a template session's intraday shape by
`new_pnl / template_pnl`, an unbounded ratio: a template closing near flat divides by almost
zero, and a negative ratio flips the sign, so a −$900 trough could return as a +$90,000 peak
with the day recorded as having no drawdown. On a fixture whose worst mark anywhere was −$900
the median resampled path reached **−$476,410**. Fixed and covered by 19 hand-computed tests,
and the tournament was re-run afterwards, so every number on this page is post-fix.

The direction is the surprise. On the 325 real ES sessions the bug was **pessimistic**: pass
rate 1.7% before against 32.0% after, liquidation 100% against 97.3%, median worst mark
−$599,614 against −$1,917. It manufactured liquidations, so the funnel's Topstep gate was
throwing strategies away on paths that cannot happen. Every pass probability computed on real
paths before tonight is void, and biased against the strategy rather than for it.

Across the whole tournament: 26 of 240 cells reached the twin, median pass probability 0.003,
six above the 10% survival floor, best 0.440 for a cell that is not a survivor.

---

## The one result worth acting on

Turnover, not direction, is what kills these strategies. Measured on validation across all
240 trials:

| round turns / session | cells | median net | positive | median gross ÷ cost |
|---|---|---|---|---|
| 1 – 3 | 24 | −$259 | 8 (33%) | **1.25×** |
| 3 – 10 | 102 | −$1,007 | 17 (17%) | 0.67× |
| over 10 | 114 | −$2,767 | 5 (4%) | 0.36× |

Median cost per round turn is **$2.10**. Median gross captured per round turn is **$1.04**.
The average trade in this entire tournament captures about half of its own cost.

Only the lowest-turnover bucket has median gross exceeding cost, and the fraction of
profitable cells falls monotonically as turnover rises. Eight of 240 cells were positive on
both train and validation; a zero-edge null predicts about 60. The systematic effect is
negative, and it is costs.

**Any viable Combine strategy on these instruments has to average under about 3 round turns
per session and capture more than $2.10 of gross per round turn.** Nothing tested does both.

Red team on the eight survivors: four of them are a single day. Remove each one's best day
and `MNQ revert.vwap.q95`, `MNQ INV::breakout.opening_range.q95`, `MNQ INV::trend.accel_confirm`
go negative, and `NQ revert.vwap.q95` drops from +$657 to +$13.

---

## Main risk

That you read the near-miss above as a lead. It was selected out of 240 trials on the split
it looks good on, and it lost money on the next one. The honest reading of tonight is that
this data, at these costs, does not contain an intraday edge in any of the seven mechanism
families tested.

The second risk is the credential. Do not retry it in a loop; a lockout during a Combine is
worse than a failed script. The client makes exactly one attempt by design.

The third is in the execution path, and it matters before any practice trading. Driving the
real risk and execution chain against a fake broker for the first time produced five proved
findings, each pinned as a failing-by-design test rather than written down and forgotten:
no production executor is given an intent journal, so nothing deduplicates; nothing connects
a fill to a position book, because there is no position book; the journal cannot represent a
fill at all; the adapter cannot report positions, so no restart can rebuild state; and
**a protective stop cannot be expressed as an order intent**, because the order model has
market, limit, market-on-close and market-on-open and no stop type. Bracket protection is not
unwired, it is not expressible.

A seventh finding is the one most likely to bite this specific mission. **The governor's
contract caps are direction-blind and block the exit.** Long 2 with a cap of 2, a sell of 2 is
denied; long 1 with a cap of 2, a sell of 2 is silently reduced to 1, leaving a position the
strategy believes it closed. It is harmless today only because the runner sets a daily-loss
limit and no contract cap. It goes live the moment you add the Topstep 5-contract cap, which
is exactly what a Combine needs.

---

## WHAT I SHOULD DO TOMORROW

**1. Fix the ProjectX credential.** Log in to the TopstepX platform, confirm you are using
your platform login username and not your email, generate a fresh API key, and paste it into
`live/secrets.env` exactly. Then run `python -m quant_brain config doctor`, and once it says
`READ_ONLY_READY`, the read-only probe can bind the account and pull real ProjectX history.
Everything from Gate 2 to Gate 10 is waiting on this and nothing else.

**2. Decide whether to keep searching at this turnover, or change the question.** The
evidence says a 1-minute intraday mechanism cannot pay $2.10 a round turn on these
instruments. The two honest directions are a much lower-frequency strategy, or a much larger
per-trade capture, and they are different research programmes. Choosing is yours, not the
machine's.

**3. Add a stop order type before anything touches a practice account.** Then the intent
journal, then the position book, in that order. Without the first, a live position cannot be
protected by construction.

Nothing was committed and nothing was pushed. `git status` shows 10 modified and 9 new files,
all listed in `docs/TOPSTEP_OVERNIGHT_REPORT.md`. The suite is green at 2,462 passed, 0
failed.
