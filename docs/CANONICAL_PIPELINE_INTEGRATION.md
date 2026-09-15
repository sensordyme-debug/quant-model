# Canonical pipeline integration — closing GAP 1 and GAP 2

Phase gate before Priority 3. Two integration gaps were named:

1. **The canonical runner produced P&L but never ran the Topstep twin.** A strategy result
   was half a result.
2. **The intrabar excursion was an opt-in research utility with no canonical representation.**
   A measured optimistic bias with nowhere to live.

Both are closed. Nothing in this phase touched a strategy, a threshold, an entry rule or an
exit rule.

---

## The architecture now

```
RAW DATA
   ↓  futures_discover.load          (fails closed: no default session window)
DATA VALIDATION
   ↓  dataquality gate
CANONICAL SESSION / BAR REPRESENTATION
   ↓  futures_discover.session_frames
STRATEGY  (frozen StrategySpec, spec_hash covers the signal source)
   ↓  spec.signal(features)          features built with the causality audit armed
SIGNALS
   ↓
EXECUTION SIMULATOR                  quant_brain/research/ledger_builder.py
   ↓                                 the ONLY place a fill is simulated
CANONICAL TRADE / EVENT LEDGER       quant_brain/research/canonical_ledger.py
   ↓
   ├── P&L / TRADE ANALYTICS         run_strategy.scenario_from  (a view)
   ├── TOPSTEP DIGITAL TWIN          account_result.build_account_result
   └── MONTHLY / PAYOUT ANALYTICS    account_result._monthly, PayoutAnalysis
   ↓
FINAL RESULT OBJECT                  stamped with execution_path_mode
   ↓
REPORT                               headline = CONSERVATIVE, never IDEAL
```

**One source of truth, asserted rather than claimed.** `CanonicalLedger.twin_days()` hands the
account simulator the *same tuple objects* the P&L layer summed —
`test_the_account_layer_consumes_the_ledgers_own_marks_and_nothing_else` checks `is`, not
`==`. A mutation that rebuilds an equal-but-new path is caught
(`ledger__twin_gets_a_rebuilt_path_instead_of_the_ledgers_own`).

---

## GAP 1 — the account result

`AccountResult` carries all 24 required fields, every one derived from the one ledger:

| # | field | where |
|---|---|---|
| 1 | trade-level P&L | `ledger.trade_frame()` |
| 2 | equity curve | `ledger.equity_curve()` |
| 3 | intraday equity path | `ledger.intraday_equity()`, `SessionLedger.marks` |
| 4 | MLL state / path | `mll_path()["mll"]` — from `TwinResult.trace` |
| 5 | DLL state / path | `mll_path()["dll"]` |
| 6 | liquidation status | `liquidated` |
| 7 | liquidation session | `liquidation_session` |
| 8 | liquidation reason | `liquidation_reason` |
| 9 | target reached | `target_reached`, `combine_sessions` |
| 10 | forced-flat status | `forced_flatten_sessions`, `forced_flatten_pnl` |
| 11 | contract-limit status | `contract_limit_ok`, `contract_limit_detail` |
| 12 | maximum drawdown | `max_drawdown` |
| 13 | maximum intraday drawdown | `max_intraday_drawdown` |
| 14 | minimum MLL buffer | `min_mll_buffer`, `min_mll_buffer_intraday` |
| 15 | minimum DLL buffer | `min_dll_buffer`, `min_dll_buffer_intraday` |
| 16 | days survived | `days_survived` |
| 17 | days traded | `days_traded` |
| 18 | total trades | `total_trades` |
| 19 | winning / losing days | `winning_days`, `losing_days`, `flat_days` |
| 20 | monthly P&L | `monthly[].net_pnl` |
| 21 | monthly returns | `monthly[].return_on_account_pct` |
| 22 | P(survive the period) | `p_survive_period` |
| 23 | P(reach $3,000 before violating) | `p_target_before_violation` |
| 24 | P(payout eligibility) | `p_payout_eligible` |

The MLL and DLL paths are a **record**, not a recomputation: `TwinResult.trace` is populated
inside `_step` from the same locals the breach test reads, so the levels reported and the
levels enforced cannot drift apart.

### Four returns, never conflated

`ReturnBasis` reports all four side by side and labels the only one that is money:

- **on notional** — P&L over the contract value actually controlled
- **on account balance** — P&L over $50,000, which Topstep never asks anyone to post
- **per contract** — a scale-free unit, not a return
- **under account constraints** — what the ACCOUNT realised: the daily limit applied, the
  path stopped at liquidation, and a loss capped at the room the account had

That last one diverges hard. In `test_account_constrained_pnl_diverges_from_strategy_pnl_when_the_account_dies`
a strategy that ends **+$7,900** hands the account **−$2,000**, because it was liquidated on
session one and the later profit was never the account's to make.

### Payout layer, kept separate

`PayoutRuleSet` is **versioned** (`topstep-50k-2026-09-12`), built from `topstep.py`'s cited
rules rather than from literals repeated in the payout layer, and carries the help-centre
citation for every value plus an `unverified` list for anything below DOC confidence. The
withdrawal **policy** (how much to take, how much buffer to leave) is a separate object,
because a policy change must never look like a rule change.

The report answers each question on its own line: strategy profitable? account survives?
target reached? payout rules satisfied? amount, opportunities, time to first, probability.

### Probabilities are labelled

Moving-block bootstrap over the same `TwinDay` objects the deterministic run used, carrying
the sentence *"HISTORICAL / PATH-MODEL SCENARIO ESTIMATE … Not a forecast"*. Monthly output
prints a **SMALL SAMPLE** banner under 24 months and nothing is annualised or extrapolated.

---

## GAP 2 — the intrabar path as an explicit mode

Three accounting modes, on the ladder, stamped on every record:

| mode | slippage | spread | path |
|---|---|---|---|
| `IDEAL` | 0.0 | not charged | `CLOSE_ONLY` |
| `BASELINE` | 0.5 | charged | `CLOSE_ONLY` |
| **`CONSERVATIVE`** | **1.0** | **charged** | **`INTRABAR_CONSERVATIVE`** ← headline |
| `STRESS` | 2.0 | charged | `STRESS` |

Every mode also declares stop execution, target execution, forced-flatten execution, the
partial-fill model (`NOT MODELLED` in all four) and the ambiguous-bar model. The assumption
table prints before every run and is saved with the result.

**No historical result was rewritten.** `CLOSE_ONLY` is preserved exactly, and the legacy
research scripts still use it. `docs/INTRABAR_FORENSICS.md` covers what OHLCV knows, what is
unknowable, the equity bounds, long/short treatment, how stops/targets/flatten interact with
the bound, ambiguous same-bar events, and whether the bound is pessimistic or bounded.

### The monotonic safety property, at the integrated level

120 random multi-session runs through all three modes. At every step of the ladder:

| invariant | violations |
|---|---|
| settled P&L unchanged | **0** |
| a liquidated account is never rescued | **0** |
| days survived never increases | **0** |
| resampled survival probability never increases | **0** |
| maximum intraday drawdown never improves | **0** |
| minimum buffer never improves while alive | **0** |

The test also requires at least one run to flip surviving → liquidated, so a fuzz that never
reached the boundary cannot pass silently.

---

## Independent cross-check

Every canonical run cross-checks itself against `topstep_reference` — a second implementation
with **no shared code**, only the cited constants. **17 fields** compared: terminal stage,
days survived, Combine attempts, Combine day, liquidation, liquidation session, liquidation
*kind*, target status, payout count, total paid, both minimum buffers, peak balance, starting
balance, ending balance (surviving paths), MLL at the last session's open, final position
flat.

- **100 randomly generated strategy/event paths**, varying instrument size, DLL, path mode and
  payout policy: **0 mismatches**.
- Plus the 6,000-path reconciliation from the prior phase: **0 decision-level mismatches**.

### The one accepted equivalence, named in code

When the daily limit is armed, a capped session moves the balance down by exactly the DLL
while the MLL stays put, so the next session's DLL level can land **exactly** on the MLL. On
that tie the twin reports `dll_at_the_floor` and the reference reports `intraday`. Both
liquidate, on the same session. Flipping the tie rule over **20,000 DLL-armed paths** changed
survival **zero** times. `_TIE_EQUIVALENT` grants the exception explicitly, with the reason,
in the code that grants it — not by skipping the field.

---

## Acceptance criteria

| criterion | status |
|---|---|
| canonical runner executes the Topstep twin | **PASS** |
| canonical runner executes intrabar accounting | **PASS** — CONSERVATIVE is the headline |
| execution/accounting mode explicit in every result | **PASS** — trades, fills, scenarios, account, JSON |
| P&L and twin consume the same canonical ledger | **PASS** — identity-asserted |
| production twin agrees with the independent reference | **PASS** — 17 fields, 100 runs, 0 mismatches |
| monthly results derive from the canonical ledger | **PASS** — rows sum back to it |
| payout analysis derives from the canonical ledger | **PASS** |
| IDEAL / BASELINE / CONSERVATIVE / STRESS distinct | **PASS** — 4 distinct slippages, 3 distinct paths |
| adversarial integration tests pass | **PASS** — 51 tests |
| mutation tests catch planted integration defects | **PASS** — 38/38, **100%** |
| no live order endpoint reachable | **PASS** — asserted in-suite |
| no API transmission code added | **PASS** |
| no credentials/secrets touched | **PASS** — `live/` untouched |
| no strategy rules modified | **PASS** — spec hash stable across a run |
| no strategy optimization | **PASS** |

**Status: HIGH-FIDELITY RESEARCH-GRADE BACKTEST ENGINE.**

Suite: **2,772 passed, 9 skipped, 15 xfailed.** Lint clean.

---

## Known limitations carried forward

These are stated, not hidden. None blocks the gate; all are honest bounds on what the engine
claims.

1. **The independent reference covers the $50,000 path only.** Other sizes return
   `cross_check.agrees = False` with the reason, rather than passing unchecked.
2. **The intrabar bound is not retro-applied.** Legacy research scripts stay on `CLOSE_ONLY`
   so their published numbers remain reproducible; only the canonical runner defaults to the
   conservative path.
3. **Partial fills, queue position and market impact are NOT MODELLED**, in every mode, and
   say so in the result.
4. **Stops and targets fill at their levels even on a gap** — optimistic, declared in every
   mode, and asserted by test so it cannot change silently.
5. **The runner reads `data/futures/*.parquet` only.** A data-source-agnostic canonical input
   schema, and the RAW / CONTINUOUS / ROLL-ADJUSTED distinction, are Priority 3.
6. **The consistency-route payout path, scaling ladders, alternative readings and the Live
   Funded Account** remain outside the reference's scope, covered by `test_qb_topstep.py`
   alone.
