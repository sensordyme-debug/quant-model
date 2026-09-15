# Phase 3A — the canonical data layer becomes the backtester's authoritative input

Minimal integration only. No research funnel was rewritten, no strategy was invented, tuned or
modified, and no published number moved. What changed is which code path the strategy
backtester reads its bars through, and what that path is able to say about them.

---

## The adapter

```
CANONICAL DATA
   quant_brain/data/    adapter → schema.validate_frame → quality.check → DatasetManifest
        ↓
   quant_brain/research/session_source.py      ← THE ADAPTER, and nothing else
        ↓  window · one contract per session · structural completeness
STRATEGY BACKTESTER
   ledger_builder → canonical_ledger → account_result → strategy_report
```

`scripts/run_strategy.py` previously called `futures_discover.load` — a provider-shaped read of
`data/futures/*.parquet` with no statement anywhere of what the price series was. It now calls
`session_source.build(spec)`, which defaults to `canonical`. The old reader is still reachable
as `--data-path legacy` and exists **only** so the two can be compared.

`futures_discover.py` was not edited. Making the new path a reimplementation rather than an
import is deliberate: importing the filters would make "the two paths agree" a tautology
instead of a measurement.

### What the canonical path can say that the legacy path cannot

| | canonical | legacy |
|---|---|---|
| data form | `CONTINUOUS_UNADJUSTED` | — |
| roll method / adjustment | `CALENDAR_DAYS_BEFORE_EXPIRY` / `NONE` | — |
| manifest id | `e0f411ac6298e690` | — |
| frame fingerprint | `33275bc8f5bf9148` | — |
| quality status | `WARN`, with reasons, hashed | — |
| execution-validity refusal | **enforced** | impossible |
| gates run | schema + canonical quality + futures validator | futures validator |

The execution-validity refusal is the one that matters. An adjusted continuous price is a
number no venue ever quoted; a fill simulated at one is a fill at a fiction. The canonical path
refuses such a series as an execution source. The legacy path could not have known.

---

## The equivalence run

```powershell
python scripts/canonical_equivalence.py --spec examples.example_strategy:SPEC
python scripts/canonical_equivalence.py --instrument ES      # and NQ, MES
```

The same **frozen** spec, hash asserted identical on both sides, run twice — once per data
path — and compared field by field from the raw bars to the Topstep account result, for **all
four execution profiles**, not just the headline.

| instrument | sessions | comparisons | MATCH | EXPLAINED | **DIFFER** |
|---|---|---|---|---|---|
| ES | 310 | 660 | 654 | 6 | **0** |
| NQ | 310 | 660 | 654 | 6 | **0** |
| MES | 249 | 636 | 630 | 6 | **0** |
| MNQ | 249 | 636 | 630 | 6 | **0** |
| | | **2,592** | **2,568** | **24** | **0** |

Compared, per profile: bars · timestamps · session dates · wall-clock stamps · contract labels
· open · high · low · close · volume · every feature · signals · entry count · fills (every
column) · the trade ledger (every column: prices, P&L, MAE, MFE, R multiple, exit reason, hold
time, ambiguity flag) · daily P&L · equity curve · intraday equity · net P&L · monthly rows ·
and ~45 Topstep account fields including the MLL/DLL path frame.

Price and volume compare at tolerance **0.0** — exact. Money compares at 1e-9, and every
comparison reports the worst observed difference, so a real drift could not hide under a
tolerance. Every worst-difference was 0.000e+00.

### The six differences, each explained

None is a data difference. No bar, price, signal, fill, trade or dollar differs at all.

1. **`attrition.bars_in_window`** — 100,450 vs 100,059 on MNQ. The two paths *count at
   different points*. `fd.load` applies the window and the contract filter in one function, so
   its count is already net of the multi-contract session; the canonical path counts the window
   first. The difference is exactly the 391 bars of the dropped session, and the **kept**
   sessions are identical.
2. **`attrition.sessions_in_window`** — 261 vs 260. Same mechanism.
3. **`attrition.sessions_dropped_multi_contract`** — 1 vs −1. The legacy path reports *unknown*
   because `fd.load` has already discarded those days by the time it returns. Stated as
   unknown rather than guessed at.
4. **`provenance`** — the canonical path declares form, roll, adjustment, manifest id,
   fingerprint and quality; the legacy path declares none of them. That asymmetry **is** the
   reason for the migration.
5. **`gates_run`** — three gates versus one. The canonical path runs every check the legacy
   path runs, and more, so it is strictly stronger.
6. **`wall_clock`** — ~25 s versus ~9 s. The cost of running the schema validation and the full
   quality gate on every load. A cost, not a different answer.

`EXPECTED_DIFFERENCES` in `scripts/canonical_equivalence.py` holds these explanations. Anything
**not** on that list that differs fails the run, and the script exits non-zero.

---

## Regression protection

`tests/test_phase3a_data_path.py` — 22 fast tests plus 2 `acceptance` tests.

Fast, on synthetic frames, so a refusal is provably a refusal:

- the bar count is inclusive (391, not 390) and cannot be set apart from the window
- a malformed or reversed window is refused
- a session spanning two contracts is dropped **entirely** and counted
- an early close (225 bars) is dropped rather than averaged in as a whole day
- an interior hole is dropped even when both ends are right
- a 391-bar session starting at 09:31 is dropped
- an **adjusted** series is refused as an execution source — and the identical frame declared
  unadjusted is accepted, so the refusal is provably about the declaration
- a missing store fails closed; an unknown data path is refused, not defaulted
- `run_strategy.load_sessions` defaults to `canonical` (asserted on the function, not on prose)

Acceptance, on the real store through the real runner: the two paths produce the same bars, and
the same trades, P&L, excursions and Topstep result, with >500 matching comparisons and no
unexplained difference.

---

## Infrastructure freeze

Equivalence is demonstrated, so the rule from here is:

> **No further general infrastructure unless a concrete user-supplied strategy exposes a
> correctness defect.** When one does: fix the defect, add a regression test, continue.

The promotion pipeline the phase asks for **already exists** and was not rebuilt:

| requested stage | where it lives |
|---|---|
| BACKTEST | `core.mode.Mode.BACKTEST` — simulated adapters only |
| VALIDATION | `Mode.VALIDATED` + `research.promotion.PromotionGate` |
| ROBUSTNESS | `strategy_report.Classification` — PROMISING or better |
| PRACTICE | `Mode.PRACTICE` — prop-firm practice account, real rules, fake money |
| HUMAN APPROVAL | `Mode.HUMAN_APPROVAL` — a signed file in `live/approvals/` |
| COMBINE | `Mode.EXECUTION_READY` — needs an explicit argument **and** `QB_LIVE_TRADING_ENABLED` **and** the approval file, all three at once |

No AI-generated strategy can promote itself: `registry.TRANSITIONS` refuses a skipped rung, and
the three independent conditions on `EXECUTION_READY` cannot be satisfied by one edit.
Nothing in this phase touched `live/`, credentials, or any transmission surface.

---

## Reproducing

```powershell
python scripts/canonical_equivalence.py                      # MNQ, the frozen reference spec
python scripts/canonical_equivalence.py --instrument ES      # and NQ, MES
python -m pytest tests/test_phase3a_data_path.py -q
python scripts/run_strategy.py --spec examples.example_strategy:SPEC
```
