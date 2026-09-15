# Backtest Engine — Forensic Audit & Hardening

**Objective.** Not to produce impressive results. To make the engine hard to fool.

**Final status: RESEARCH-GRADE.** Not production-grade, not live-ready. The reasoning is in §12.

Date: 2026-09-14 · No commits, no pushes, no orders, `live/secrets.env` untouched.

---

## 1. Phase 0 — the actual execution graph

Traced by reading the code, not the documentation.

```
data/futures/<SYM>.parquet
  └─ fd.load()                     RTH filter, trade-date assignment, roll-day exclusion
      └─ fd.session_frames()       structural completeness: exactly SESSION_BARS bars,
      │                            first==open, last==close. Short days DROPPED, never padded
      └─ fd.build_features()       fe.library() + fe.audit_causality() ── RAISES on a leak
          └─ StrategySpec.signal   the frozen user callable → positions in {-1,0,+1}
              ├─ X.simulate_trade()      declarative exit; stop-first on ambiguous bars
              │   └─ trade ledger        entry/exit/MAE/MFE/R/reason/holding
              ├─ fd.session_accounting() vectorised equity path, per-leg cost
              └─ reference_ledger.run_reference()   INDEPENDENT loop implementation
                  └─ three-way reconciliation → ValidationReport
                      └─ slippage ladder (0 / 0.25 / 0.5 / 1 / 2 ticks)
                          └─ monthly table + distribution + provenance
                              └─ canonical result package
```

**Topstep simulation is a separate graph** and is not equivalent to the generic backtest:
`twin.TopstepTwin` + `paths.py` resamplers, driven by per-session equity paths, with
`strict_path=True` so a session lacking an intraday path is refused rather than scored.

### Reachable vs dead

| module | status |
|---|---|
| `futures_discover.session_accounting` | **live** — the core P&L identity |
| `futures_discover.evaluator` | live, used by the tournament path |
| `execution_sim.CostModel/ExecutionSimulator` | live |
| `instruments.py` | live — the single source of contract metadata |
| `features.py` + `audit_causality` | live, **wired into `build_features` and raising** |
| `twin.py`, `paths.py`, `propfirm.py`, `topstep.py` | live for the Topstep graph |
| `research/exits.py` | live — the exit simulator |
| `research/strategy_lab.py` | live — the trade extractor |
| `research/reference_ledger.py` | **new** — independent cross-check |
| `research/strategy_spec.py`, `strategy_runner.py` | **new** — the frozen interface |
| `algorithms/*` (LEAN) | **unreachable from the futures engine** — a separate equities path |
| `Quant Brain/**` | **archive** — equities, own engine, no path in |

### Duplicated and conflicting implementations

Three separate paths compute per-trade P&L: `session_accounting` (position-series),
`strategy_lab.extract_trades` (ledger), and `exits.simulate_trade` (bracketed). They agree
on the fill convention and cost, and are now reconciled by tests, but **they are three
implementations of one idea** and that is a standing P2 risk.

---

## 2. Findings

| # | finding | class | status |
|---|---|---|---|
| F1 | `round_turn_cost` includes a full spread crossing; five call sites called it "commission only" | **P1** | **FIXED** (labels corrected, test pins it) |
| F2 | No-entry-on-the-final-bar was an implicit runner rule, absent from the spec and the reference | **P1** | **FIXED** (named parameter on both sides) |
| F3 | Validation compared a 0.5-tick engine result against a 0-tick reference → spurious INVALID | **P1** | **FIXED** |
| F4 | Reference ledger deducted only the closing leg's cost — every net figure light by half a round turn | **P2** (in new code, never shipped) | **FIXED** |
| F5 | Test suite did not defend the target *fill price*; an optimistic-fill mutation survived | **P1** | **FIXED** (3 tests added) |
| F6 | Test suite did not defend *when* cost is charged; deferring it to the close survived | **P1** | **FIXED** (2 tests added) |
| F7 | Test suite did not defend MAE being populated | **P2** | **FIXED** |
| F8 | Three implementations of per-trade P&L | **P2** | documented, reconciled, not merged |
| F9 | `futures_discover.OPEN_ET/CLOSE_ET` default to a 15:45 close, wrong for Topstep | **P2** | overridden per-run; golden fixtures pin 376 bars so the default was not changed |
| F10 | `session_accounting` has no entry policy; the policy lives in callers | **P3** | documented and tested |

### F1 in detail — the cost mislabel

| symbol | `round_turn_cost` | commission | spread component |
|---|---|---|---|
| ES | $16.28 | $3.78 | $12.50 (1 tick) |
| NQ | $13.78 | $3.78 | $10.00 (2 ticks, measured) |
| MES | $2.47 | $1.22 | $1.25 (1 tick) |
| MNQ | $1.72 | $1.22 | $0.50 (1 tick) |

Every prior phase labelled its baseline "commission only" and then added slippage **on top**.
The direction of the error is **conservative** — those runs charged more friction than they
claimed — but the labels were wrong, and the reported break-even slippage figures are
therefore *understated by one tick*. E.g. the exit study's "OOS break-even is exactly 1.00
tick" means one tick **on top of** a tick already charged.

---

## 3. Phase 1 — data integrity

| symbol | bars | duplicates | out-of-order | bad OHLC | price ≤ 0 | contracts | mixed-contract days |
|---|---|---|---|---|---|---|---|
| ES | 447,600 | **0** | **0** | **0** | **0** | 5 | 4 |
| NQ | 447,596 | **0** | **0** | **0** | **0** | 5 | 4 |
| MES | 358,845 | **0** | **0** | **0** | **0** | 4 | 3 |
| MNQ | 358,845 | **0** | **0** | **0** | **0** | 4 | 3 |

- **Zero-volume bars exist** (1,354–4,258 per store). Normal for thin minutes; not repaired.
- **Roll days are EXCLUDED, not stitched.** `fd.load` drops any trade date carrying more than
  one contract. No continuous contract is constructed, so there is no roll-gap adjustment to
  get wrong — and no back-adjustment that could leak future roll information.
- **DST**: both −0400 and −0500 offsets are present; conversion is via `tz_convert`, not a
  fixed offset. A test asserts 15:10 CT is 16:10 ET in both states.
- **Completeness is structural**: exactly `SESSION_BARS` bars, first bar at the open, last at
  the close. On MNQ that drops 11 of 260 RTH days. Short and early-close days are **excluded,
  never padded or scaled**.

**The engine fails closed.** A missing store raises; zero complete sessions raises; a feature
that fails the causality audit raises inside `build_features`.

---

## 4. Phase 2 — leakage

`fe.audit_causality` is wired into `build_features` and raises. It covers the feature library
only, so the audit added adversarial tests covering the rest of the path:

| attack | result |
|---|---|
| corrupt every bar after index k to 1e6, re-run | equity path before k **byte-identical** |
| synthetic dataset with an absurdly profitable future, strategy flat before it | gross **exactly 0.00** |
| position turns on *after* a +10 move already happened | earns **exactly 0.00** |
| corrupt bars after the exit simulator's exit bar | exit bar and P&L **unchanged** |

The one-bar lag is real and tested: a position decided on bar *i* earns from bar *i*'s close
to bar *i+1*'s close, never bar *i*'s own move.

---

## 5. Phase 4 — fills

| demanded | engine response |
|---|---|
| target above the bar's high | **not filled** |
| stop below the bar's low | **not filled** |
| both stop and target inside one bar | **STOP**, and `ambiguous=True` recorded |
| target with the bar closing far beyond it | fills **at the target**, not the close |
| stop gapped through, bar recovers by the close | fills **at the stop**, not the recovery |
| a long held all session | earns **exactly close-to-close**, never low-to-close |

Ambiguity is resolved pessimistically and **flagged**, never resolved toward profit. The
ambiguous share is carried on every trade row.

---

## 6. Phase 22 — independent cross-check

`quant_brain/research/reference_ledger.py` recomputes P&L with plain Python loops and an
explicit position/cash ledger. It imports nothing from the engine.

Reconciled across 8 hand-built position series × 4 multiplier/size combinations, plus the
full 25-session run inside the runner's validation gate. **Agreement to 1e-9.**

The reference immediately earned its keep: it was itself wrong first (F4), then found F2 and
F3 in the runner.

---

## 7. Phase 17 — mutation testing

18 deliberate defects, applied one at a time to the live source, suite re-run, source restored.

**Score: 18 caught / 0 survived = 100%.**

Two survived the first pass and both were real holes in the suite:

- `target_fills_at_bar_close_not_target_price` — nothing defended the fill *price*
- `cost_charged_only_at_the_close_not_per_leg` — terminal P&L is identical either way, but the
  intraday path is what the Topstep twin reads, and the trailing MLL tracks peak equity
  intraday. Cost not yet charged is equity the twin believes the account has.

Both are now covered. A third (`mae_recorded_as_zero`) also survived and is covered.

Catalogue: `scripts/_mutation_specs.py`. Harness: `scripts/engine_mutation_test.py`.

---

## 8. Phase 23 — regression against existing results

The example run reports **340 trades / $471** where the lab published **343 / $499.04**.
Attributed exactly:

| configuration | trades | net |
|---|---|---|
| **old lab published** | 343 | **$499.04** |
| new engine, calibrated thresholds, last-bar entries allowed | 343 | **$499.04** ✓ |
| new engine, calibrated thresholds, last-bar entries blocked | 340 | $504.20 |
| example spec (rounded threshold literals), last-bar blocked | 340 | $471.20 |

**There is no engine regression.** The new engine reproduces the old number to the cent under
identical assumptions.

Two changes explain the rest:

1. **+$5.16 — the last-bar rule (F2).** Three zero-duration trades that could never have been
   held, each costing a round turn, are now refused. **The old result was slightly wrong**; it
   counted trades that cannot exist.
2. **−$33.00 — the example's rounded literals.** The example hardcodes `HI=1.900` against the
   calibrated `1.900224932605374`; 4 of 343 signal bars differ. This is a property of the
   example, deliberately chosen so the example needs no hidden calibration step.

---

## 9. What the engine now guarantees

- **Three-way reconciliation on every run.** Trade ledger = equity curve = independent
  reference, to one cent, or the result is `INVALID` and says why.
- **The equity curve is reconstructible from the ledger.** Tested.
- **Every completed round turn is charged**, including the forced flatten. Tested against
  mutation.
- **Cost is charged at the leg**, so the intraday path the Topstep twin reads never shows
  money the account does not have.
- **The five-scenario ladder always runs** — IDEAL / OPTIMISTIC / REALISTIC / CONSERVATIVE /
  STRESS. The zero-slippage figure is reported, never hidden, and a strategy positive only
  there is **flagged in the summary**.
- **The headline is the REALISTIC scenario**, never the ideal one.
- **Provenance on every result**: spec hash (covering the signal *body*), dataset hash, git
  SHA, dirty flag, data range, session count, library versions, run timestamp.
- **Determinism verified**: two identical runs produce identical hashes and identical numbers.

---

## 10. Phase 19/20 — the frozen strategy interface

```bash
python scripts/run_strategy.py --spec examples.example_strategy:SPEC
```

The spec (`quant_brain/research/strategy_spec.py`) is a frozen dataclass carrying instrument,
timeframe, signal callable, declarative exit, sizing, session and cost assumptions. It is
hashed including the signal's source text.

**The engine refuses ambiguity rather than choosing:**

| the caller does | the engine does |
|---|---|
| sets both `stop_atr` and `structural_stop` | **refuses** — two different stops |
| sets no exit at all | **refuses** — must state session-close-only explicitly |
| sets `close_et` past 16:10 ET | **refuses** — past the mandatory flat |
| asks for a 5-minute timeframe | **refuses** — resampling is unaudited for leakage |
| sets `contracts` above `max_contracts` | **refuses** |

There is no parameter selection anywhere in the runner. It takes one spec and reports one
result per execution scenario, with no notion of a "best" one.

---

## 11. Residual risks and limitations

**Data**
- Futures store spans **2025-06-08 → 2026-09-10 only** (ES/NQ; MES/MNQ from 2025-09-07).
  249–312 complete sessions. Any monthly distribution is 12–15 months.
- No RTY/M2K/YM/MYM. No tick or order-book data. No quote data except `ES_quotes.parquet`.
- Roll days excluded rather than stitched — correct, but it means ~3–4 sessions/year are absent.

**Execution**
- **Intrabar sequencing is unknowable from OHLCV.** The engine resolves ambiguity as
  stop-first and flags it; it does not pretend to know.
- Partial fills, order queue position, rejections and cancellations are **not modelled**. Every
  order is assumed filled in full at the modelled price.
- Market impact beyond the modelled spread is **not modelled**. At 50 micros this is probably
  immaterial; at scale it is not.
- The MNQ spread is the **one-tick fallback, not measured** (`spread_measured=False`).

**Topstep model**
- Trailing-MLL locking at breakeven is modelled from the documented rule. The interaction
  between *intraday unrealised* P&L and the EOD trailing advance is the least-verified part of
  the whole system.
- `min_trading_days` is 0 in the profile; Topstep's actual minimum is not established here.
- Consistency-rule thresholds carry a **documented source conflict** (55% vs 50%) recorded in
  `topstep.py` rather than resolved.

**Engine**
- Three P&L implementations (F8). Reconciled, not unified.
- The independent reference models signal-driven positions only; for **price-based exits the
  independent leg is skipped** and the result says so in `validation.failures`. That is the
  largest remaining gap in the cross-check.

---

## 12. Final status: **RESEARCH-GRADE**

Not `HIGH-FIDELITY RESEARCH-GRADE`, because the independent cross-check does not cover
bracketed exits, partial fills and queue position are unmodelled, and the Topstep
unrealised-P&L/EOD-trailing interaction is not independently verified.

Not production-grade or live-ready, and passing tests would not make it so.

### Can you hand it a new frozen strategy and trust the output?

**Yes, for serious human evaluation, with three stated caveats.**

Independently verified:

- P&L arithmetic reconciles with a from-scratch implementation across 12 position/size/
  multiplier combinations and a full 25-session run, to 1e-9
- contract math checked against hand-written CME specs: tick × multiplier = tick value on all
  four instruments; micro is exactly 1/10 of mini; ±1 tick and ±1 point verified per instrument
- no future information reaches a decision — verified by corrupting the future and observing
  a byte-identical past
- no impossible fill — verified by demanding prices the bar never traded
- every round turn is charged, at the leg — verified by mutation
- the ledger reconstructs the equity curve — verified
- 100% mutation score on 18 deliberate defects
- runs are deterministic and carry full provenance

The caveats:

1. **Bracketed exits have no independent cross-check.** Ledger and equity still reconcile; the
   third leg is skipped and the result says so.
2. **The sample is 12–15 months.** The engine will faithfully report a monthly distribution
   built on 13 months. That is a data limitation, not an engine one, and the engine states it.
3. **Fills assume full execution at the modelled price.** No partials, no queue, no impact
   beyond spread.

A bad strategy will look bad: the example — a mechanism this repository already rejected — is
reported at a REALISTIC Sharpe of 0.87 with a median month of **−$3** and 46% of months
positive, which is exactly what it deserves.

---

## 13. Reproducibility

```bash
python scripts/run_strategy.py --spec examples.example_strategy:SPEC
python scripts/engine_mutation_test.py
python -m pytest tests/test_engine_forensics.py tests/test_strategy_interface.py -q
```

Artifacts: `research/strategy_runs/<name>_<hash>_{trades,monthly,scenarios}.csv` and
`_result.json`; `research/_mutations/mutation_results.txt`.
