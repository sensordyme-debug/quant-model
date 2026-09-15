# Topstep 50K digital twin — forensic validation

Scope: `quant_brain/markets/futures_cme/twin.py` and the `TopstepAccount` layer in
`topstep.py`, as exercised for the **$50,000 Combine → Express Funded** path.

Reason for the audit: the twin is the engine's objective function. Pass probability, payout
count and the funded buffer all come out of it, and every "is this strategy fundable"
verdict inherits its arithmetic. Before this pass it carried 118 behavioural unit tests and
**no end-to-end scenario whose expected balances were computed in advance, and no second
opinion**. It was named the least-verified component in the engine.

Evidence: `tests/test_topstep_twin_forensics.py` (39 tests),
`quant_brain/research/topstep_reference.py` (independent reference),
`quant_brain/research/intrabar_path.py` (the one defect found, and its bound).

Nothing in this document is a recorded output. Every expected value in section A was worked
out from the published constants before it was run.

---

## Verdict

| # | Question | Result |
|---|---|---|
| 1 | Do hand-computed scenarios reproduce? | **PASS** — 21 of 21, exactly |
| 2 | Is the twin genuinely path-dependent? | **PASS** — same P&L, both verdicts |
| 3 | Does path sensitivity run the right way? | **PASS** — 6,000 pairs, 0 violations |
| 4 | Does it agree with an independent implementation? | **PASS** — 6,000 paths, 0 decision-level disagreements |
| 5 | Is the DLL/MLL tie-break safe? | **PASS** — 20,000 paths, survival never changes |
| 6 | Is coarse-path error one-directional? | **PASS** — coarse can only miss, never invent |
| 7 | Does the close-only case fail closed? | **PASS** — refused, waiver marks the result |
| 8 | Is the equity path fed to the twin complete? | **FAIL** — see *The one defect* |

Status of the simulator itself: **verified for the 50K Combine → XFA path.** Status of its
**input**: one measured optimism, now bounded and documented, fix available and opt-in.

---

## The constants everything is computed against

The published 50K row, asserted in
`test_the_constants_this_file_hand_computes_against` so a rulebook correction fails at the
arithmetic that depends on it rather than silently moving every expectation.

| | |
|---|---|
| Combine | start $50,000 · MLL $2,000 trailing, locking at $50,000 · target $3,000 · minimum trading days 0 |
| Consistency | best day ≤ 55% of total profit; above it the target rises to `best_day / 0.55` |
| XFA | start $0 · MLL $2,000 trailing, locking at $0 |
| Payout | 5 winning days of $150+ · `min(50% of balance, $2,000)` · $125 floor · MLL pinned at $0 permanently |
| DLL | $1,000, optional |
| Fee | $49 per Combine attempt |

---

## A. Twenty-one known-answer scenarios

Each scenario states its levels, marks and settlement in its own docstring and asserts the
full result — terminal stage, balance, buffer, breach day and reason. The arithmetic was
worked out first; the code was run second; all 21 matched on the first run.

| | Scenario | Pins |
|---|---|---|
| S01 | +$500 with a −$200 dip | the limit follows the balance up, room stays $2,000 |
| S02 | +$100 after touching +$900, then −$1,200 | **the limit trails the CLOSE, not the intraday high** — the day-2 loss lands exactly on the wrong answer |
| S03 | −$2,100 intraday, closing flat | an intraday touch kills an account whose close is healthy |
| S04 | −$2,000 close, path supplied only to −$500 | the close is tested even when the path never reaches it |
| S05 | +1,400 +1,400 +100 −2,899 | the Combine limit stops climbing at $50,000, surviving by **one dollar** |
| S06 | …and −$1 more | the other side of the same dollar |
| S07 | +1,000 × 3 | passes; the XFA rebuilds at $0 with the same $2,000 |
| S08 | +2,000 +500 +500 | the same $3,000 earned lopsidedly does **not** pass — target rises to $3,636.36 |
| S09 | …plus +$700 | 2,000/3,700 = 54.05% is inside 55%, so the base target returns and it passes |
| S10 | funded, then −$1,999 | the XFA's floor is −$2,000; one dollar of room left |
| S11 | …and −$1 more | fatal |
| S12 | funded account dies, 3 attempts allowed | attempts buy an **evaluation**, never a funded account |
| S13 | blow up day 1, pass days 2–4, 2 attempts | `combine_days` counts from the attempt's start; fees $98 |
| S14 | −$2,500 with the DLL armed | capped at −$1,000; the account survives at $49,000 |
| S15 | the identical day, unarmed | dead. S14/S15 differ in one flag |
| S16 | four days walking down to $200 of room | **an armed DLL protects nothing once the MLL sits above it** |
| S17 | 5 funded days of +$200 | cap is half the balance: $500 |
| S18 | 5 days of +$150, requesting 30% | $112.50 < $125 → **refused outright**, nothing moves |
| S19 | 5 funded days of +$1,000 | the $2,000 per-size ceiling binds below half of $5,000 |
| S20 | 5 days of +$150, payout taken | the payout **pins** the floor at $0 before the trail got there — worth $1,250 |
| S21 | …and one dollar below it | killed by a floor the payout put there |

S05/S06, S10/S11 and S20/S21 bracket their limit from both sides to the dollar. S14/S15 and
the flat/deep pair in section B differ in exactly one input, so the effect is not confounded.

---

## B. The path-dependence attack

Topstep tests the maximum loss limit **intraday**. A twin that answered from the daily P&L
series would be catastrophically optimistic and would still pass every terminal-value test
ever written for it. Four attacks, then a second opinion.

**Same P&L, different shape.** Five sessions summing to +$200. With no excursion beyond the
close: survives at $50,200. Dipping $2,500 below each close first: liquidated on session one
at $47,800. Identical account statement, opposite outcome.

**Same two sessions, reordered.** +2,500 then −2,100 survives at $50,400, because day one
lifts the peak and locks the floor at $50,000. −2,100 then +2,500 dies on day one. Same $400.

**One multiset, all 120 orderings.** Total P&L, mean, standard deviation, Sharpe and win rate
are identical across all 120 permutations. Both verdicts appear.

**Fixed final P&L, 400 draws.** Eight sessions forced to sum to exactly +$1,200, random
intraday depth: **372 liquidated, 28 survived.** The twin is emphatically not P&L-blind.

**Direction of sensitivity — 6,000 random pairs, zero violations.** For each trial the same
P&L series is given a trough and then a strictly deeper trough:

- a deeper path never outlived a shallower one — 0 violations
- a deeper path never lasted more sessions — 0 violations
- when both survived, closing balances were **identical** — 0 violations

The third is the one that pins the mechanism: with no DLL armed, the intraday path decides
only *whether* the account survives, never how much it earns. A twin that let an excursion
leak into the balance would fail here even with correct survival arithmetic. 1,316 of the 6,000 pairs
(21.9%) changed verdict, confirming the fuzz was actually working the boundary.

### The second opinion

`quant_brain/research/topstep_reference.py` answers the same question from the rulebook and
is built to be **structurally unlike** the production path:

| production | reference |
|---|---|
| mutable `TopstepAccount`, limits via `@property` at read time | pure function over an explicit list of `(kind, level)` liquidation levels rebuilt at the top of each session |
| a state machine (`advance()`) stepping once per call | no state machine; the phase is a local variable and a transition is a rebuild |
| floor via `PropFirmProfile.floor_for` | the floor written out as the two-line `min()` the rulebook states |
| breach via a `breached()` predicate on an equity attribute | breach by comparing every mark against a level fixed before the day starts |

They share **no functions** — only the cited constants in `topstep.py`, deliberately, so a
rulebook correction cannot stop being tested.

Over **6,000 random paths** (2–25 sessions, four volatility regimes, DLL on and off, one to
three Combine attempts, three payout shares, two path shapes), the two agree on **every field
that is a decision**, with zero mismatches:

    terminal stage · sessions survived · Combine attempts · day the Combine was passed
    breach day · whether funding was reached · payout count · total paid
    minimum buffer · minimum funded buffer · final balance on every surviving path

Building the reference found one real bug — **in the reference**, which reported
`trading_combine` when the Combine was passed on the very last session. Fixed there. The twin
was right.

### The one divergence, and why it is inert

`final_balance` differs on **518 of 6,000** paths. All 518 are liquidated, and all 518 have
the DLL armed.

The cause is structural, not floating point. A DLL-capped session moves the balance down by
exactly $1,000 while the maximum loss limit stays put, so the *next* session's DLL level can
land exactly on the MLL. On that tie the twin books the day at −$1,000 first and finds the
settled balance at the floor, reporting the floor; the reference stops at the touch and
reports the balance the session opened at. **Both liquidate, on the same session.**

Whether the tie could ever change survival was not argued — it was measured. Both tie rules
were replayed over **20,000 DLL-armed paths** with a third, hand-written level model:

- survival verdict differed: **0**
- reported balance differed: 4,855

So the tie-break decides the reason string and a dead account's reported balance, never
whether the account lives. `final_balance` on a liquidated path is not an input to any
decision. Recorded as a **reporting convention**, not a defect.

---

## C. Equity-path granularity

The twin sees only the marks it is handed and is blind between them. That is a property of
the *input*, and the only honest response is to measure which way the error runs.

**Direction: one-way.** Subsampling drops marks, and a dropped mark cannot create a touch the
full path did not have. Verified over 300 sessions × 4 intervals: a coarse path never found a
breach the minute path missed. **Coarse is optimistic; a coarse run that reports a breach has
really breached.**

**Magnitude.** 3,000 synthetic 391-bar sessions at $90 per bar against a fresh Combine's
$2,000 of room. 771 sessions (25.7%) truly breach:

| marks sampled | detected | share of truth | missed |
|---|---|---|---|
| every minute | 771 | 100.0% | 0 |
| every 5 min | 729 | 94.6% | 42 |
| every 15 min | 681 | 88.3% | 90 |
| every 30 min | 639 | 82.9% | 132 |
| hourly | 594 | 77.0% | 177 |
| twice a session | 472 | 61.2% | 299 |
| once a session | 423 | 54.9% | 348 |
| **close only** | **407** | **52.8%** | **364** |

An hourly path misses roughly a fifth of the liquidations. **Settling on the close alone
misses nearly half.**

**The close-only case fails closed.** `strict_path=True` refuses a session with no path
rather than returning a number that is optimistic by that much, and `strict_path=False`
records `path_supplied=False` so the result is marked an upper bound. The reference makes the
same refusal — a second implementation that quietly accepted a close-only day would reconcile
against the twin's waived mode and call it agreement.

**What production actually supplies.** `futures_discover.session_accounting` returns the full
per-minute equity path and `evaluator` hands all ~390 marks to `TwinDay(path=...)`. Production
sits on the **top row** of that table. Coarse sampling is not the live exposure.

---

## The one defect: the excursion inside the bar

The residual is not coarse sampling — it is **sub-minute**. `session_accounting` builds its
path from minute **closes**. A long position held through a bar is marked at that bar's
**low** before the close prints, and the platform liquidates on the touch. A close-built path
never shows it.

Measured on the futures store, always long one lot, 09:30–16:00 ET:

| | ES (310 sessions) | MES (249 sessions) |
|---|---|---|
| worst mark from closes, median | −$1,075 | −$119 |
| worst mark using the bar low, median | −$1,162 | −$132 |
| hidden depth, median | **$75** | $9 |
| hidden depth, 90th pct | $175 | $19 |
| hidden depth, max | $725 | $76 |
| sessions surviving on closes but breaching on the bar low | **8 (2.6%)** | 0 (0.0%) |

So on the mini the omission is worth ~2.6% of sessions in the **optimistic** direction — the
direction that matters. On the micro the same points are a tenth of the dollars and it is
immaterial.

**The bound.** `quant_brain/research/intrabar_path.py` restores it: each bar is marked at the
extreme that hurts the position held (low for a long, high for a short, close for flat), and
those marks are interleaved before their closes. Verified on the real ES store — terminal
value changed on 0 of 310 sessions, the path was shallower on 0 of 310, and it flips exactly
the 8 sessions predicted. Tested for: the settled P&L never moves, a long is marked at the
low and a short at the high, the path is never shallower than the close path, mismatched
arrays are refused rather than broadcast, and — the property that makes it safe to enable —
**restoring the excursion can only make the twin stricter; it never rescues a dead account.**

It is a **bound, not a reconstruction**. For a position held through the whole bar it is
exact. For a bar on which the position changes it is conservative, because the fill happens
somewhere inside the bar and the trader may not have held through the extreme. One-minute
OHLC cannot say which, so the engine takes the conservative reading and says so. Whether the
low came before or after the high inside a bar is **NOT MODELLED** and cannot be from OHLC;
the conservative reading already assumes the worse ordering.

**It is opt-in, deliberately.** Enabling it changes twin verdicts — strictly towards more
breaches — so every pass rate previously published in this repository was computed without
it. Making it the silent default would rewrite those numbers with no record of why they
moved. Callers ask for it explicitly.

---

## Gaps left open

1. **The canonical strategy runner does not run the twin.** `scripts/run_strategy.py` and
   `quant_brain/research/strategy_runner.py` — the entry point built for user-supplied
   strategies — produce the five-scenario cost ladder, the three-way reconciliation and the
   validation report, but **no Topstep feasibility verdict**. The twin is reachable only
   through `futures_discover.evaluator` and the lab scripts. A user-supplied strategy
   currently gets a P&L answer and no account-path answer.
2. **The intra-bar bound is not wired into any caller.** It exists, it is tested, and nothing
   calls it yet. Until it is, every twin verdict in the repository carries the ES optimism
   measured above.
3. **Sizes other than $50,000 have no independent reference.** `topstep_reference.py` refuses
   them rather than approximating; the $100K and $150K rows rest on the unit tests alone.
4. **The consistency-route payout path, scaling ladders, alternative readings and the Live
   Funded Account** are outside the reference's scope and are covered only by
   `test_qb_topstep.py`.
5. **Combine pricing** remains the documented $49/month with a recorded disagreement;
   `net_capital` stays `None` when no fee is supplied rather than defaulting.

---

## Reproducing

```powershell
. .\scripts\env.ps1
python -m pytest tests/test_topstep_twin_forensics.py -q      # 39 tests, ~4s
python -m pytest tests/test_qb_twin.py tests/test_qb_topstep.py -q   # the 118 behavioural tests
```

Full suite after this pass: **2,721 passed, 9 skipped, 15 xfailed.**
