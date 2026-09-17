# Topstep $50K — one-week pass research program

**Result: NOTHING SURVIVED. Zero candidates are promoted.**

Fifteen intraday mechanisms were screened on NQ and MNQ. Five passed the entry-information
gate on the development split under FDR control and replicated across both instruments at the
screening level. All five then failed the robustness gates — three of five reversed sign out
of sample on NQ and four of five on MNQ, every one concentrates 69–2127% of its P&L in its ten
best trades, and three of five draw down more than the entire $2,000 Maximum Loss Limit on a
single contract before their holding period ends.

No strategy is recommended. No parameter was tuned to rescue one. This report exists so the
negative result is usable rather than repeated.

> The standing `infrastructure-freeze` rule (2026-09-15: the owner supplies strategies, the
> engine only tests them) is superseded for this phase by the owner's explicit commission of
> this program. Nothing here was promoted, committed, or connected to anything.

---

## 1. Economic requirement

```
account $50,000      target $3,000      MLL $2,000 (EOD-trailing, intraday breach test)
consistency  doc_calc: best single day <= 55% of TOTAL profit, inclusive
contract cap 5 NQ / 50 MNQ            mandatory flat 15:10 CT
DLL          optional in the Combine, not set on this profile
```

**Required average daily P&L**

| sessions | $/session |
|---|---|
| 3 | $1,000.00 |
| **5** | **$600.00** |
| 7 | $428.57 |
| 10 | $300.00 |
| 20 | $150.00 |

**The consistency ceiling is not the binding constraint at one week.** At exactly $3,000 of
profit the best single day may be $1,650, so a path needs at least two profitable days. Five
days averaging $600 puts the best day at roughly 20% of total — comfortable. A *big* day is
what hurts, because it raises the bar rather than helping:

| best single day | total profit then required |
|---|---|
| $800 | $1,454.55 (target alone suffices) |
| $1,650 | $3,000.00 (exactly at the ceiling) |
| $2,000 | **$3,636.36 — the target is no longer enough** |
| $2,500 | **$4,545.45** |

**Acceptable losing-day distributions.** Any path reaching +$3,000 works provided (a) no
intraday mark is ever $2,000 below the running EOD peak, and (b) the best day stays under 55%
of the eventual total. `+300/+500/+700/+800/+700` and `+600/+400/+900/+500/+600` both pass
easily. So does `+900/−400/+1,100/+700/+700`: a losing day is free, a large *winning* day is
not.

**Maximum drawdown compatible with the MLL.** The MLL starts at $48,000, trails the EOD peak
by $2,000 and locks at $50,000 once the EOD peak reaches $52,000. A five-day run to +$3,000
may never be $2,000 below its own running EOD high **at any tick**, because the breach test is
intraday on unrealized P&L.

**Required trade frequency against expectancy**, at $600/session:

| expectancy/trade | trades/session needed |
|---|---|
| $50 | 12.0 |
| $100 | 6.0 |
| $150 | 4.0 |
| $300 | 2.0 |
| $600 | 1.0 |

**The epistemic bar — and it is good news for a null.** Using the repository's measured
per-session sigma, the smallest edge detectable at t = 1.96 over the sessions we hold is
$24.88–$149.30/session on NQ (5–30% participation) and $3.00–$17.98 on MNQ. The economic bar
of $600/session is far above all of them:

> **A strategy good enough to pass in one week would be plainly visible in this sample.**
> A null result here is therefore evidence of absence, not merely absence of evidence. (This
> is not true at the 60-session horizon on NQ, where $50/session sits below the $74.65
> detection floor and a null would prove nothing.)

---

## 2. Candidate mechanisms

Fifteen hypotheses, each with parameters fixed a priori at conventional values and written
into `scripts/mechanism_screen.py`. **No mechanism was assumed to have an edge, and no
parameter was searched** — the script takes no parameter arguments, so it cannot be re-run
with different numbers.

| # | mechanism | definition (long leg; short is the mirror) |
|---|---|---|
| 1 | `vwap_pullback` | above VWAP, this bar's low touches VWAP, closes back above, green |
| 2 | `vwap_reclaim` | below VWAP for 5 bars, now closes above |
| 3 | `orb_continuation` | first close above the 09:30–09:44 opening-range high |
| 4 | `orb_failure` | previous bar poked outside the opening range, this one closes back inside |
| 5 | `trend_pullback` | above VWAP, three red bars, then a green close |
| 6 | `vol_expansion` | bar range > 2× ATR(14), with direction |
| 7 | `compression_break` | 20-bar range below half its trailing 120-bar mean, then a breakout |
| 8 | `failed_breakout` | made a 20-bar high last bar, closes back below it |
| 9 | `range_breakout` | closes above the 20-bar high on >1.2× average volume |
| 10 | `mean_reversion_z2` | close more than 2 VWAP-sigma below VWAP → fade |
| 11 | `prior_day_level` | tags the prior session's low and closes back above |
| 12 | `session_hl_rejection` | tags the running session low and closes back above |
| 13 | `momentum_after_compression` | 5-bar range inside ATR, close takes the 5-bar high, on volume |
| 14 | `tod_momentum_open` | first hour only, takes the 20-bar extreme |
| 15 | `tod_meanrev_late` | last 90 minutes only, fade a 1.5-sigma stretch |

Decision window 09:45–15:30 ET; forward outcomes may run to the 15:45 session end. Data is the
certified 18:00-anchored path (`vwap-anchored-1.0.0`), NQ manifest `9c4bb5d370e4a7e3`,
MNQ `89d97f6f8c6405f9`.

**Split, declared before any result was seen:** dev = first 60% of sessions (NQ 186, MNQ 151),
validation = next 20% (NQ 62, MNQ 50), **holdout = final 20%, NOT READ IN THIS PHASE.**

---

## 3. Opportunity frequency

Two counts, and they mean different things. *Raw events* is how often the condition appears.
*Tradeable* is how many survive thinning so that no two forward windows overlap — what one
account holding one position could actually act on. Classification is on tradeable frequency
at a 15-minute hold: **A ≥ 2/session, B ≥ 0.5, C < 0.5**.

| mechanism | raw/session | tradeable/session | class | % sessions ≥1 |
|---|---|---|---|---|
| `range_breakout` | 24.76 | 13.07 | A | 100% |
| `tod_meanrev_late` | 20.97 | 1.03 | B | 54% |
| `mean_reversion_z2` | 19.09 | 3.33 | A | 76% |
| `trend_pullback` | 17.45 | 7.28 | A | 99% |
| `orb_failure` | 10.94 | 2.76 | A | 89% |
| `orb_continuation` | 6.34 | 2.82 | A | 100% |
| `tod_momentum_open` | 5.83 | 2.02 | A | 98% |
| `vol_expansion` | 5.30 | 5.30 | A | 98% |
| `prior_day_level` | 5.09 | 3.88 | A | 59% |
| `session_hl_rejection` | 4.52 | 2.13 | A | 88% |
| `vwap_reclaim` | 3.71 | 3.11 | A | 77% |
| `vwap_pullback` | 3.67 | 3.09 | A | 72% |
| `compression_break` | 3.11 | 3.11 | A | 87% |
| `momentum_after_compression` | 0.17 | 0.17 | **C** | 10% |
| `failed_breakout` | 0.00 | 0.00 | **C** | 0% |

Thirteen of fifteen are class A — **opportunity frequency is not the problem here.** This
contrasts sharply with V1.0.0_Frozen, which fires once per 39 sessions and is class C by a
wide margin; a mechanism at that rate cannot address a one-week objective and is correctly
rejected for it regardless of its other merits.

`failed_breakout` never fires because a bar that makes a 20-bar high and the next bar closing
below that same high is a rarer joint event than the definition suggests. It is rejected on
frequency, not on economics.

---

## 4. Entry information

For each (mechanism, horizon) the signed forward displacement is compared with a **matched
control**: same session, same direction, same 30-minute time-of-day bucket, drawn only from
bars whose own forward window is complete. Inference is on **session means** — one observation
per session — because 30-minute windows started on consecutive bars share 29 minutes of
outcome and the naive event-level t counts the same information repeatedly. Eighty-four trials
per instrument, Benjamini-Hochberg FDR at α = 0.05, and survival additionally requires the
effect to point the way the hypothesis claims (a two-sided FDR rejects a reliable *loser* too,
which is a finding about its inverse, not a candidate).

**Dev-split survivors, both instruments:**

| mechanism | NQ t vs control | MNQ t vs control | survives FDR on both |
|---|---|---|---|
| `mean_reversion_z2` | +10.64 | +7.11 | **yes** |
| `session_hl_rejection` | +6.21 | +8.02 | **yes** |
| `orb_failure` | +3.99 | +3.95 | **yes** |
| `tod_meanrev_late` | +3.49 | +3.48 | **yes** |
| `trend_pullback` | +3.09 | +3.74 | **yes** |
| `orb_continuation` | −3.88 | −4.61 | no (reliably negative) |
| `range_breakout` | −16.67 | −14.53 | no (reliably negative) |
| `tod_momentum_open` | −7.64 | −6.21 | no (reliably negative) |
| `vol_expansion` | −4.11 | −4.28 | no |
| `vwap_reclaim` | −4.97 | −2.96 | no |
| `compression_break` | −2.53 | −2.14 | no |
| `vwap_pullback` | +1.16 | +0.36 | no |
| `prior_day_level` | +0.17 | +0.71 | no |
| `momentum_after_compression` | −1.38 | −1.98 | no |
| `failed_breakout` | — | — | no events |

Five mechanisms cleared the gate on both instruments. That is a real and reproducible
screening result, and §7–8 are where it dies.

### Three defects found in this harness, and fixed

Reported because each of them *manufactured* an edge, and two of them would have survived
casual review:

1. **Whole-session denominator lookahead.** `compression_break` compared the 20-bar range to
   the median range of the *entire session*, including bars in the future. Replaced with a
   trailing 120-bar mean. This is the pattern `leak-patterns` records as replicating out of
   sample.
2. **Overlap illusion.** The first version measured every qualifying bar and multiplied mean
   displacement by events/session. `tod_meanrev_late` then showed $2,896/session — a Combine
   pass per day — because twenty-one 30-minute windows in one afternoon are twenty-one
   readings of the same move. Fixed by thinning to non-overlapping events, which is also the
   only thing one account could hold.
3. **Control not time-matched.** Controls were drawn from the whole session and those near the
   close were silently dropped for having a NaN outcome, so a late-afternoon mechanism was
   compared against a morning-biased control. `tod_meanrev_late` showed a control mean of
   −14.6 points and an apparent 21-point edge. Fixed by matching the 30-minute bucket and
   drawing only from bars with complete forward windows.

---

## 5. Exit research

**Not reached, and deliberately not run.** The program's own rule is that exits are designed
only once an entry survives. No entry survived §7–8, and fitting exits to a rejected entry is
how a dead mechanism is resurrected by search.

The one exit used in screening is the minimum needed to measure anything: hold for the
dev-selected horizon. The scorecard additionally records what a fixed stop would have to
absorb (§8, MAE columns), which is what disqualifies three of the five on risk grounds before
any exit design could begin.

---

## 6. Costs

Round-turn cost including assumed spread, from the repository's fee table:

| size | $/point | round turn | break-even move |
|---|---|---|---|
| NQ ×1 | $20 | $13.78 | 0.69 pts |
| NQ ×5 | $100 | $68.90 | 0.69 pts |
| MNQ ×10 | $20 | $17.20 | 0.86 pts |
| MNQ ×50 | $100 | $86.00 | 0.86 pts |

(The frozen V1.0.0 spec carries $4.50 for NQ, which is commission only. The higher figure here
includes spread and is the one used throughout this report.)

**The cost ladder was not run per-candidate** because none reached that gate. Its question is
answerable analytically: the control-adjusted edges observed were 1–5 points per event. One
tick is 0.25 points, so a 1-tick stress removes 5–25% of the edge and a 3-tick stress removes
15–75%. Any mechanism at the low end of that range is a cost artefact, which is exactly what
`feasibility.py` records from the prior 240-trial study on this same data — median cost $2.10
per round turn against median gross captured $1.04.

---

## 7. Out-of-sample

The dev-selected horizon was frozen and carried unchanged into validation. **Holdout was not
read.**

| mechanism | NQ dev $/s | NQ val $/s | NQ | MNQ dev $/s | MNQ val $/s | MNQ |
|---|---|---|---|---|---|---|
| `mean_reversion_z2` | +49.71 | +62.28 | same | −14.82 | +180.53 | **FLIP** |
| `orb_failure` | +347.85 | **−132.22** | **FLIP** | +418.08 | **−551.97** | **FLIP** |
| `session_hl_rejection` | +11.23 | +150.25 | same | +10.82 | +544.68 | same |
| `tod_meanrev_late` | +118.19 | **−14.97** | **FLIP** | +38.09 | **−235.79** | **FLIP** |
| `trend_pullback` | +73.22 | +196.81 | same | +434.02 | **−205.57** | **FLIP** |

Three of five reverse sign on NQ; four of five on MNQ. The two largest dev results —
`orb_failure` at +$348/session and `trend_pullback` at +$434/session on MNQ — are also the two
that reverse hardest.

---

## 8. NQ/MNQ replication, concentration, and risk

Same index, same dollar exposure (NQ ×1 and MNQ ×10 are both $20/point).

| mechanism | dev→val sign agrees on both? | top-10 trades as % of total P&L (NQ / MNQ) | MAE p95 (NQ) | vs $2,000 MLL |
|---|---|---|---|---|
| `mean_reversion_z2` | no | 262% / −1057% | $1,815 | under |
| `orb_failure` | flips on both | 71% / 69% | $2,420 | **OVER** |
| `session_hl_rejection` | **yes** | **1634% / 2127%** | $2,489 | **OVER** |
| `tod_meanrev_late` | flips on both | 110% / 405% | $1,607 | under |
| `trend_pullback` | no | 323% / 79% | $2,199 | **OVER** |

**Concentration is fatal everywhere.** A top-10 share above 100% means the mechanism is
negative without its ten best trades. `session_hl_rejection`, the only one whose sign holds on
both instruments in both splits, is 1634% concentrated on NQ: it is ten trades and noise.

**Risk is fatal on three.** The 95th-percentile adverse excursion on a *single* contract is
$1,607–$2,489 against a $2,000 MLL. A mechanism whose ordinary bad trade consumes the entire
Combine buffer cannot be sized up toward $600/session, because the drawdown scales with the
size that produces the profit.

---

## 9. Topstep simulation · 10. Monte Carlo · 11. One-week target analysis

**Not run. Zero candidates reached these gates.**

This is a deliberate refusal, not an omission. Running a 10,000-path Monte Carlo or a Topstep
twin on a mechanism that reversed sign out of sample would produce a distribution of pass
probabilities for something already known to be noise, and the number would be quoted
afterwards. The program's own Part 13 requires a candidate to clear entry edge, costs,
frequency, OOS, replication and risk *before* path simulation.

What can be said analytically about the one-week question is §1 and the frontier below.

### The structural contradiction

For NQ ×1 at $600/session:

| trades/session | net $/trade | gross pts needed | assessment |
|---|---|---|---|
| 1 | $600.00 | 30.7 | larger than a typical 30-minute move |
| 2 | $300.00 | 15.7 | larger than a typical 30-minute move |
| 3 | $200.00 | 10.7 | large but conceivable |
| 5 | $120.00 | 6.7 | large but conceivable |
| 8 | $75.00 | 4.4 | plausible magnitude |
| 12 | $50.00 | 3.2 | plausible magnitude |
| 20 | $30.00 | 2.2 | plausible magnitude |
| 40 | $15.00 | 1.4 | below the observed noise floor |

The plausible-magnitude band needs 8–20 trades a session. The mechanisms that fire that often
(`range_breakout` at 13/session, `trend_pullback` at 7.3) are precisely the ones with negative
or sign-unstable edges. The mechanisms with the largest measured edges hold 30 minutes and
draw down $1,600–$2,700 per contract — more than the whole MLL — so they cannot be scaled to
close the gap.

**At every size the arithmetic is the same**, because the MLL is fixed in dollars while the
edge and the drawdown both scale with contracts:

| size | net points/session needed | MLL expressed in points |
|---|---|---|
| NQ ×1 | 30.0 | 100.0 |
| NQ ×5 | 6.0 | 20.0 |
| MNQ ×10 | 30.0 | 100.0 |
| MNQ ×50 | 6.0 | 20.0 |

Larger size lowers the points needed *and* lowers the points of drawdown tolerated, in exact
proportion. **Sizing cannot solve this. It is a ratio problem, not a scale problem.**

---

## 12. Practice validation plan (unused)

No candidate reached it. Recorded so the next one has a plan rather than an improvisation:
run the frozen spec on TopstepX Practice for at least ten full sessions with no changes during
the run; record actual bid/ask, fill latency and realised slippage per fill; compare each live
fill against what the simulator would have produced for the same bar; feed the resulting
Practice ledger — not a re-simulation — into the $50K digital twin; and only then seek human
approval. The engine and data path for all of that already exist and are certified.

---

## 13. Surviving candidates

**None.**

| gate | mechanisms remaining |
|---|---|
| defined | 15 |
| fires often enough (class A/B) | 13 |
| entry beats a matched control, FDR-controlled, both instruments | **5** |
| holds its sign out of sample on NQ | 3 |
| holds its sign out of sample on **both** instruments | **1** (`session_hl_rejection`) |
| not dependent on its ten best trades | **0** |
| 95th-percentile adverse excursion inside the $2,000 MLL | 0 of the above |

`session_hl_rejection` is the closest thing to a survivor and it is not one: its sign holds in
all four cells, and its top-10 trades are 1634% (NQ) and 2127% (MNQ) of total P&L, meaning it
is deeply negative without them, on an adverse excursion that exceeds the MLL.

## 14. Rejected candidates, and why

| mechanism | rejected at |
|---|---|
| `failed_breakout` | frequency — never fires |
| `momentum_after_compression` | frequency — 0.17/session, class C |
| `orb_continuation`, `range_breakout`, `tod_momentum_open`, `vol_expansion`, `vwap_reclaim`, `compression_break` | entry gate — reliably *negative* versus matched control (a finding about their inverses, not a candidate) |
| `vwap_pullback`, `prior_day_level` | entry gate — indistinguishable from control (t = +1.16, +0.17) |
| `orb_failure`, `tod_meanrev_late` | out-of-sample sign reversal on **both** instruments |
| `mean_reversion_z2`, `trend_pullback` | no NQ/MNQ replication; concentration |
| `session_hl_rejection` | concentration (1634% / 2127%); MAE p95 exceeds the MLL |
| **V1.0.0_Frozen** | frequency — one trade per 39 sessions, class C. Unsuitable for a one-week objective irrespective of its other properties. |

---

## 15. Remaining uncertainty

1. **The holdout has not been read.** By design. It is spent only on a candidate that has
   already cleared everything else, and there is none.
2. **Fifteen months, one regime.** NQ rose 22,040 → 24,578 across the dev split alone
   (+6.3 pts/session of drift). A mean-reversion or trend mechanism measured here is measured
   in one regime. The time-matched control absorbs drift in expectation; it does not make the
   sample representative.
3. **Exits were not designed.** A stop would cap the adverse excursions in §8 and might make a
   mechanism MLL-compatible that is not compatible unstopped. It would also cut the edge,
   since the measured edge comes from holding through the excursion. This is untested, and
   testing it on a mechanism that failed out of sample would be search.
4. **Fifteen mechanisms is a small census of a large space.** Nothing here shows that no
   one-week strategy exists — only that none of these fifteen is one, on this data, under
   these gates.
5. **The prior 240-trial study on this same data** found cost the binding constraint, with
   8 of 240 cells positive where a null predicts ~60. This program's result is consistent with
   it and adds 30 more trials pointing the same way.
6. **What would change the answer:** more history (the store is one venue and 15 months), or
   an instrument whose tick value is smaller relative to its noise, or a mechanism with a
   genuinely larger per-event edge than the 1–5 points observed here. Not more parameters.

---

## Reproducing

```powershell
python scripts/mechanism_screen.py --instrument NQ  --split dev
python scripts/mechanism_screen.py --instrument MNQ --split dev
python scripts/mechanism_scorecard.py
```

Artefacts: `research/mechanisms/{NQ,MNQ}_dev.json`, `research/mechanisms/scorecard.json`.
Nothing was committed. No order was placed. No connection to Topstep was made. V1.0.0_Frozen
was not modified or optimised.
