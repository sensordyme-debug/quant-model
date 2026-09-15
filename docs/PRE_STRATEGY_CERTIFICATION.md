# Pre-strategy certification — zero-trust forensic audit

The final gate before the first user-supplied strategy. The system was assumed guilty. Six
defects were found and fixed, one of them P0. Everything below is a measurement, not an
assertion.

**Verdict: READY FOR FIRST USER STRATEGY**, with the limitations in §9 stated rather than
resolved.

---

## 1. The system map

Each stage names its module, its units, its timestamp semantics, and what verifies it.

| # | stage | module | in → out | units | timestamp | verified by |
|---|---|---|---|---|---|---|
| 1 | SOURCE | `data/futures/*.parquet` | file → rows | index points, contracts | UTC, µs | file hash on the manifest |
| 2 | CANONICAL | `data/adapters.py` → `schema.py` | rows → canonical frame | same | **UTC stored, declared** | `validate_frame`, 12 required columns |
| 3 | QUALITY | `data/quality.py` | frame → PASS/WARN/FAIL | — | venue clock declared | hashed report on the manifest |
| 4 | SESSIONISE | `research/session_source.py` | frame → session frames | same | **ET wall clock** | window/contract/completeness filters + attrition |
| 5 | FEATURES | `futures_cme/features.py` | session → feature frame | mixed, per feature | causal: bar *i* sees 0..*i* | `audit_causality`, refuses on leak |
| 6 | SPEC | `research/strategy_spec.py` | human → frozen spec | points · ticks · $ | ET wall clock | `ambiguities()`, sha256 hash |
| 7 | SIGNAL | the spec's callable | features → −1/0/+1 per bar | dimensionless | decision at bar *i*'s **close** | oracle-ceiling canary |
| 8 | ORDERS | `research/ledger_builder.py` | signal → entries | contracts | entry at bar *i*'s close | entry-gate tests, mutations |
| 9 | EXECUTION | `research/exits.py` | entry → exit | price points | bar-by-bar forward walk | golden fills, 15 exit mutations |
| 10 | FILLS | `research/canonical_ledger.py` | trades → `Fill` | signed contracts, $ | bar-stamped | fills net to zero per session |
| 11 | LEDGER | `canonical_ledger.py` | fills → `LedgerTrade` | **USD** | entry/exit timestamps | conservation law at every session |
| 12 | P&L | `CanonicalLedger.daily()` | trades → per-session $ | USD | session date | independent reconstruction |
| 13 | EQUITY | `equity_curve()` / `intraday_equity()` | sessions → path | USD | mark order | last mark == settled P&L (raises otherwise) |
| 14 | TOPSTEP | `futures_cme/twin.py` | marks → account | USD | session + intraday | `topstep_reference`, no shared code |
| 15 | MONTHLY | 3 calculators (see below) | ledger → months | USD, % | calendar month | all three vs a hand reconstruction |
| 16 | MONTE CARLO | `futures_cme/paths.py` | sessions → paths | USD | resampled order | deterministic per seed; observed sessions only |
| 17 | PAYOUT | `research/account_result.py` | account → payouts | USD | session date | versioned rules, cited |
| 18 | REPORT | `research/strategy_report.py` | all → scorecard | labelled | — | every headline rebuilt from the ledger |
| 19 | PROMOTION | `core/mode.py` + `research/promotion.py` | result → stage | — | — | three independent live conditions |

### Competing sources of truth, found and resolved

- **Three monthly calculators** (`strategy_runner.monthly_table`,
  `account_result._monthly`, `strategy_report._period_rows`). Kept — each serves a different
  consumer — but now **pinned against one another and against an independent reconstruction**
  (`test_all_three_monthly_calculators_agree_with_an_independent_reconstruction`). They agreed
  to the cent on 10 months.
- **`AccountResult.final_equity` duplicates `ending_balance`.** It is an account *level*, not a
  P&L. The report no longer reads it; the alias is documented and test-pinned.
- **Two t-statistics** in one output: the ladder's i.i.d. `t_stat` and the scorecard's
  Newey–West HAC `t`. Both now carry their method.
- **`LOOKAHEAD_CEILING_SHARE` duplicates `futures_discover.MAX_CEILING_SHARE`** deliberately
  (library must not import a script). A test asserts equality so they cannot drift.

---

## 2. Defects found

| # | severity | area | defect |
|---|---|---|---|
| 1 | **P0** | execution / ledger | A direct `+1 → -1` reversal lost its second leg. |
| 2 | **P1** | Monte Carlo | The MC ran a *no-withdrawal* payout policy while the account beside it withdrew. |
| 3 | **P1** | reporting | "ending STRATEGY equity" printed `starting_balance + ending_balance`. |
| 4 | **P1** | research validity | The user-facing runner had **no lookahead canary**. |
| 5 | **P2** | reporting | "$3,000 target" / "P(reach $3,000)" mislabelled the Combine pass condition. |
| 6 | **P2** | reporting | Ladder Sharpe/Sortino annualised at √252 with no clock stated. |
| 7 | **P3** | reporting | "complete-account survival 249 of 71 sessions traded" — two different counters. |
| 8 | **P3** | statistics | The HAC standard error was reconstructed as `mean/t`, which divides by zero. |
| 9 | **P3** | test integrity | A mutation named the wrong defending suite; another's anchor had gone stale and was silently **skipped**. |

### DEFECT 1 — the P0, in detail

`ledger_builder` gated entries on `i > busy_until` where `busy_until = exit_bar`. When a
signal flips `+1 → -1` at bar *i*, `use_invalidation` closes the long **at** bar *i* and the
short wants to open **at** bar *i*. The entry was refused; and because the signal-edge test
then advanced `prev` past the flip, the run of `-1` that followed produced no edge either, so
the short leg was dropped for the rest of the run.

Measured on an alternating `+1/-1` signal:

```
BEFORE   4 trades, directions [1, 1, 1, 1]      <- all long
AFTER    7 trades, directions [1,-1, 1,-1, 1,-1, 1]
```

A spec saying *"long above, short below"* was tested as *"long above, flat below"* and
reported under its own hash. Nothing downstream could catch it: every layer agreed perfectly
about the trades that **were** taken. This is the single most dangerous class of defect this
engine can have, and it would have bitten the first always-in-market strategy submitted.

**Blast radius:** the frozen example strategy is unchanged (340 trades, $301.20) because its
signal is sparse and never flips directly. No published number moved.

### DEFECT 2 — measured, not argued

| payout policy | P(MLL breach) over 300 resampled paths |
|---|---|
| `fraction=0.0` (what the MC used) | **0.0 %** |
| `fraction=1.0` (what the account used) | **14.0 %** |

On the certification fixture the account takes 20 payouts. Withdrawing lowers the balance
while the MLL does not follow it down, so withdrawal is what makes ruin reachable. On a
120-session random sample the same defect measured 87.1 % against 98.5 %. Always optimistic.

### DEFECT 4 — the hole the causality audit structurally cannot close

`audit_causality` perturbs feature **inputs**. A signal is arbitrary Python, so a lookahead
written directly into the signal function is invisible to it. A planted oracle signal earned
**33.8 % of the one-bar-ahead profit ceiling** and produced a clean, attractive scorecard with
no warning anywhere on it. The funnel has refused this since 2026; the user-facing runner did
not. It does now, and a suspected lookahead is classified **UNTESTABLE** — a void
measurement, not a graded strategy.

---

## 3. Defects fixed

All nine. Each has a reproduction, a named regression test, and a mutation that reintroduces
it:

| defect | regression test | mutation |
|---|---|---|
| 1 | `test_a_direct_reversal_keeps_both_legs`, `test_an_alternating_signal_is_not_silently_traded_one_sided` | `cert__reversal_loses_its_second_leg__THE_P0` |
| 2 | `test_the_monte_carlo_uses_the_ACCOUNTS_payout_policy_not_a_kinder_one` | `cert__monte_carlo_uses_a_kinder_payout_policy_than_the_account` |
| 3 | `test_the_strategy_pnl_and_the_account_balance_are_not_confused` | `cert__strategy_equity_printed_from_the_account_balance` |
| 4 | `test_a_signal_that_indexes_the_future_is_caught_by_the_ceiling_canary` | 3 mutations (disarm, loosen, downgrade) |
| 5 | `test_the_combine_target_is_the_consistency_raised_one_not_three_thousand` | — (label asserted in-test) |
| 6 | `test_the_report_states_the_clock_behind_any_annualised_ratio` | — |
| 7 | rendered line asserted in `test_the_strategy_pnl_and_the_account_balance_are_not_confused` | — |
| 8 | covered by the HAC method string assertion | — |
| 9 | mutation re-pointed and anchor repaired | `builder__overlapping_positions_allowed` restored |

The reversal fix also required preserving a behaviour it could easily have broken —
`test_a_stop_out_does_not_re_enter_on_an_unchanged_signal` pins that a position stopped out
while the signal is unchanged does **not** immediately re-open.

---

## 4. What was attacked and held

### Data (Part 2) — every corruption refused or flagged

| attack | outcome |
|---|---|
| duplicate bar | session **dropped**; quality gate **FAIL** |
| missing bar | session **dropped**; gate WARN with an exact count |
| out-of-order bars | 0 sessions kept; gate **FAIL** (`ordering`) |
| truncated final session | **dropped** |
| two contracts in one session | **dropped** entirely, counted in attrition |
| early close (225 bars) | **dropped**, never averaged in as a whole day |
| interior hole with correct ends | **dropped** |
| session starting one minute late | **dropped** |
| impossible OHLC (low > high) | gate **FAIL** (`ohlc_validity`, `ohlc_containment`) |
| zero price | gate **FAIL** (`non_positive_price`) |
| negative volume | gate **FAIL** (`volume_sign`) |
| NaN / infinite price | gate **FAIL** (`price_finite`) |
| adjusted series used for fills | **refused** at the adapter's front door |
| missing store | **fails closed**, no proxy substituted |

### Causality (Parts 4, 16)

| planted leak | outcome |
|---|---|
| next-close oracle feature | **refused** |
| `rolling(31, center=True)` | **refused** on any real session length |
| future high shifted back | **refused** |
| future volume shifted back | **refused** |
| whole-session high as a constant | **refused** |
| shipped feature library (control) | **clean** |
| oracle written into the signal itself | **now flagged** (defect 4) |

### Bar timing (Part 5)

Semantics are **(C): information available at the close of bar *t*, executed at the close of
bar *t*.** Confirmed empirically: a signal on bar 1 fills at bar 1's close (101.0), not bar 1's
open (99.5) and not bar 2's open (100.5); and it earns `c[2]−c[1]`, never `c[1]−c[0]`.

The assumption is **zero latency** and therefore optimistic. It is now priced: the report
states what the same trades would have made with entries at the next bar's open. On the
example strategy: **−$20.50** against **+$301.20** net — the edge is not the fill convention.

### Execution and intrabar (Parts 6, 7)

| case | behaviour |
|---|---|
| stop touched exactly (low == stop) | **filled** — conservative for a stop |
| stop missed by one cent | not filled |
| gap 18 points through the stop | filled **at the stop level** — optimistic, declared in every mode |
| stop and target in one bar | resolved as **STOP**, `ambiguous_bar=True` |
| one-bar trade | valid, charged a full round turn |
| reversal | **two trades**, two round turns |
| path mode ladder | settled P&L identical across modes; worst mark monotone non-improving |

### Strategy spec (Part 15) — 25 ambiguous specifications, 25 refused

Including: target in R with no stop, three simultaneous stop forms, fractional-tick distances,
pyramiding, entry cutoff at the flat, a time stop longer than the session, a warmup that
leaves no entry bar, an unknown instrument, a non-callable signal.

### Security (Part 26) — every bypass refused

```
no flag, no env, no file                  REFUSED
flag only                                 REFUSED
flag + env, no approval file              REFUSED
flag + env + EMPTY approval file          REFUSED
env turned off again                      REFUSED
flag + env + signed approval (all three)  -> EXECUTION_READY   (the intended path)
```

`strategy_report`, `ledger_builder`, `session_source`, `canonical_ledger` and `account_result`
contain **zero** transmission surface. A backtest Authority does not permit a venue.

---

## 5. Independent reference results

| reference | scope | result |
|---|---|---|
| hand-computed golden strategies | 39 arithmetic checks | **39/39** |
| independent ledger reconstruction | 108 reconciliations incl. 3 monthly calculators | **108/108** |
| `topstep_reference` (no shared code) | 1,200 adversarial paths parked on the MLL / target boundaries | **0 mismatches** |
| `topstep_reference` in-suite | 100 random runs, 17 fields | **0 mismatches** |
| contract economics by hand | ES $12.50/tick · NQ $5.00 · MES $1.25 · MNQ $0.50; micro = parent/10; RT = commission + 1 tick | **exact** |

Topstep boundary cases, all hand-computed and all correct: MLL breaches at the touch and not a
cent above; an intraday dip liquidates even when the session closes positive; the MLL trails
the EOD balance and not the intraday high; it locks at breakeven once the balance reaches
start + MLL; an armed DLL **caps** the session rather than liquidating it; liquidation is
absorbing.

**The finding that matters most for reading a report:** a single +$3,100 day does **not** pass
a $3,000 Combine. The consistency rule (best day ≤ 55 % of profit) raises the effective target
to **$5,636**. Every "target" label now says so.

---

## 6. Test and mutation results

```
full suite          2,972 passed · 9 skipped · 14 xfailed
certification       47 tests (golden · reconciled · boundary · adversarial)
mutation testing    93 applied · 0 skipped · 93 caught · 100%
lint                clean
canonical equivalence   MNQ 636 / ES 660 comparisons · 0 unexplained differences
```

Mutation testing found **five holes in the new certification tests** and one in the catalogue
itself (a mutation naming the wrong suite scores a hole as a catch; another's anchor had gone
stale and was *silently skipped*). All six closed.

22 new mutations cover the audit's own findings, including: the reversal, the cooldown, the
warmup off-by-one, the trade cap, the forced flat, the MC payout policy, three ways to disarm
the lookahead canary, the strategy/account equity confusion, month-boundary drops, win-rate
inversion, profit-factor inversion, drawdown halving, streak accumulation, and regime labels
read from equity instead of price.

---

## 7. Reproducibility (Part 18)

Two identical runs produce byte-identical trade frames, fill frames, equity curves, intraday
equity, account results, Monte Carlo probabilities, **and rendered report text**. The twin is
deterministic; resampling is deterministic per seed and moves with the seed. All RNG in the
strategy path is explicitly seeded — no unseeded `np.random` anywhere in
`quant_brain/research/` or `quant_brain/markets/futures_cme/`.

---

## 8. Performance (Part 24)

| stage | full MNQ store (249 sessions, 97,359 bars) |
|---|---|
| canonical load + gates + sessionisation | 19.4 s |
| features + causality audit | 2.0 s |
| 4 ledgers + 4 Topstep accounts | 5.3 s |
| scorecard + 1,000-path Monte Carlo | 3.0 s |
| scorecard + 5,000-path Monte Carlo | 14.8 s |
| **end-to-end with 5,000 paths** | **≈ 67 s** |

Scaling is linear: 3.19 / 3.17 / 3.40 ms per session at 62 / 124 / 249 sessions. Peak memory
123 MB. **No calculation was approximated for speed.** The quality gate runs on every load and
is 70 % of the load cost; that is the trade being made, deliberately.

---

## 9. Remaining limitations — stated, not resolved

1. **Data depth.** ES/NQ: **310 sessions, 1.25 years, 16 calendar months, 4 roll transitions**.
   MES/MNQ: **249 sessions, 1.00 years, 13 months, 3 rolls**. Sixteen rolls in total across
   the whole store.
2. **Regimes present.** Session-ATR spread 5.9× (ES) to 11.7× (NQ) between the quietest and
   most violent quintile; 19 % of ES sessions move > +0.5 %, 15 % move < −0.5 %. **Worst
   session in the entire store: −3.03 % (ES), −4.15 % (NQ).** There is no crisis regime in this
   data — no 2018, no 2020, no 2022. Claims about behaviour in a real dislocation cannot be
   made from it at all.
3. **`ROBUST POSITIVE` is unreachable** on this store, by construction (needs 24 months).
4. **Zero-latency fills.** Priced and reported, not eliminated.
5. **Stops and targets fill at their level even on a gap through it.** Optimistic; declared in
   every mode's assumption table and asserted by test.
6. **Partial fills, queue position and market impact are NOT MODELLED** in any mode.
7. **MAE/MFE are bar-resolution upper bounds.** A trade entered mid-bar did not experience the
   whole bar's range. Stated beside the numbers.
8. **One position at a time.** Pyramiding and scaling are refused, not approximated.
9. **Units cannot be mind-read.** The engine refuses fractional-tick distances, but an author
   who writes `stop_points=10` meaning ten *ticks* has written a legal spec. Mitigated by
   printing every distance in points, ticks **and** dollars before the run.
10. **Four Topstep rules sit below DOC confidence** (`combine_min_trading_days`,
    `combine_consistency_owner_figure`, `xfa_scaling_plan`, `xfa_scaling_fallback`) and are
    listed as unverified in the rules block.
11. **The independent Topstep reference covers the $50,000 path only.** Other sizes report
    `cross_check.agrees = False` with the reason rather than passing unchecked.
12. **No verified CME holiday calendar.** Completeness is structural, so a legitimate early
    close is dropped rather than scaled — measured cost, 3 of 326 ES sessions.
13. **Multiplicity is not carried across sessions.** The report states that one spec was run
    and that the correction for how the spec was *chosen* is invisible to it.

---

## 10. Certification matrix

| category | status | tests performed | defects found → fixed | independent verification |
|---|---|---|---|---|
| CODE | **GREEN** | lint, dead/global/path scans, 2,972 tests | 0 → 0 | ruff, reachability ratchets |
| DATA | **GREEN** | 14 corruption attacks, 3 gates | 0 → 0 | canonical equivalence, 2 gates in series |
| TIME | **GREEN** | DST, roll, session boundary, wall-clock rules | 0 → 0 | UTC storage + declared venue clock |
| CAUSALITY | **GREEN** | 6 planted leaks + signal-level oracle | 1 → 1 | oracle-ceiling canary + feature audit |
| EXECUTION | **GREEN** | 7 fill cases, 15 exit mutations | 0 → 0 | golden fills, hand-computed |
| P&L | **GREEN** | 39 golden checks, conservation at every session | 0 → 0 | independent reconstruction |
| FUTURES MATH | **GREEN** | tick/point/multiplier/micro ratios | 0 → 0 | hand calculation vs CME terms |
| LEDGER | **GREEN** | 108 reconciliations, 3 modes | 1 (**P0**) → 1 | independent reconstruction |
| TOPSTEP | **GREEN** | 16 boundary cases, 1,200 adversarial paths | 0 → 0 | `topstep_reference`, no shared code |
| INTRABAR | **GREEN** | mode monotonicity, ambiguous bars | 0 → 0 | settled-P&L invariance across modes |
| MONTHLY | **GREEN** | 3 calculators vs hand reconstruction | 0 → 0 | independent, 10 months to the cent |
| MONTE CARLO | **GREEN** | policy, path length, determinism, labelling | 1 (**P1**) → 1 | rebuilt twin per policy |
| STATISTICS | **YELLOW** | HAC t, CI, concentration, multiplicity | 1 → 1 | **see limitation 13** |
| STRATEGY SPEC | **GREEN** | 25 ambiguous specs | 0 → 0 | all 25 refused |
| PROVENANCE | **GREEN** | manifest id, fingerprint, spec hash, git | 0 → 0 | equivalence run |
| REPRODUCIBILITY | **GREEN** | byte-identical reruns incl. report text | 0 → 0 | double-run comparison |
| FAIL-CLOSED | **GREEN** | missing store, bad window, zero sessions, FAIL data | 0 → 0 | every path raises |
| SECURITY | **GREEN** | 7 bypass attempts | 0 → 0 | all refused; zero transmission surface |
| PERFORMANCE | **GREEN** | 4 workloads, scaling, memory | 0 → 0 | linear, nothing approximated |
| REPORTING | **GREEN** | every headline rebuilt from the ledger | 4 → 4 | independent reconstruction |
| **DATA DEPTH** | **RED** | 15 months, 16 rolls, no crisis regime | — | **not fixable by code** |

**STATISTICS is YELLOW** because the engine cannot see how a strategy was selected. If a spec
was chosen after looking at this data, its multiplicity correction lives in that choice and no
number in the report accounts for it. The report says so; it cannot do better.

**DATA DEPTH is RED and stays RED.** It is not a defect and no amount of engineering closes it.
Every report declares it.

---

## 11. Blockers

**None.** No P0 or P1 defect is open. No unexplained discrepancy remains between any pair of
independent implementations.

## Reproducing

```powershell
python -m pytest tests/test_certification.py -q
python -m pytest -q
python scripts/engine_mutation_test.py
python scripts/canonical_equivalence.py
python scripts/run_strategy.py --spec examples.example_strategy:SPEC
```
