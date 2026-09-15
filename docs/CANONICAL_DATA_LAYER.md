# Canonical market-data layer

Priority 3. A research-integrity project, not a strategy project: no strategy was invented,
optimised, selected or modified, and no published result was changed.

Code: `quant_brain/data/` (2,313 lines, 7 modules) · `scripts/data_manifest.py`
Tests: `tests/test_canonical_data.py` (95 tests)
Companion documents: `docs/DATA_FLOW_FORENSICS.md` (the state before),
`docs/ROLL_ADJUSTMENT_FORENSICS.md` (Section 6 measurements)

---

## Status

**CANONICAL DATA LAYER — RESEARCH GRADE**, with the limitations listed at the end.

| criterion | status |
|---|---|
| canonical schema exists | **PASS** — 12 required fields, 5 optional |
| raw contracts are first-class | **PASS** — `RAW` datasets extractable from the spliced store |
| continuous contracts explicitly represented | **PASS** — 3 continuous forms, all distinct |
| roll methodology explicit | **PASS** — 6 methods, `UNKNOWN` is a legal and loud value |
| adjustment methodology explicit | **PASS** — 4 methods, must agree with the form |
| feature and execution data separable | **PASS** — `ResearchInputs`, adjusted refused for fills |
| provider adapters terminate at canonical schema | **PASS** — enforced by a test that greps the layer |
| missing metadata causes rejection | **PASS** — 11 distinct refusals |
| timezone/session semantics explicit | **PASS** — UTC storage, declared venue clock, no defaults |
| DST tested | **PASS** — spring, fall, straddling sessions, year/month/quarter boundaries |
| rollover tested | **PASS** — A=5000/B=5100, all four methods, exact |
| data quality gate exists | **PASS** — PASS/WARN/FAIL, WARN must argue for itself |
| dataset manifests exist | **PASS** — 8 written to `data/manifests/` |
| provenance complete | **PASS** — 3 independent hashes |
| existing results reproducible | **PASS** — canonical path reproduces the funnel bar-for-bar |
| adversarial tests pass | **PASS** — 17 attacks |
| mutation tests pass | **PASS** — **71/71, 100%** (33 on this layer) |
| performance measured | **PASS** — ~170,000 bars/s including the gate |
| actual historical coverage reported | **PASS** — and it is 15 months of futures |
| no live trading surface touched | **PASS** — 0 references, `live/` unmodified |

Suite: **2,872 passed**, 9 skipped, 15 xfailed. Lint clean.

---

## What Section 1 found

The forensic map came first, before any code changed. Seven findings, all measured:

1. **The roll boundary is a fixed UTC instant**, so it lands at 18:00 ET in summer and
   **16:00 ET in winter — inside the RTH window**. 2025-12-11 is the one ES session of 326
   carrying two contracts. The old loader filtered it out; nothing declared it.
2. **Three independent entry points** into the same store, each with its own normalisation.
3. **No dataset declared anything about itself.** The roll rule existed only as
   `ROLL_DAYS = 8` in the fetch script.
4. **Instrument and contract were conflated** at the API boundary.
5. The existing quality gate has **four gaps**, three already pinned as strict xfails.
6. The equity store is a **different schema entirely**, with the symbol in the filename.
7. Futures depth is **15 months and four rolls per instrument**.

None of that had produced a wrong published number — the loaders filter defensively and the
overnight work uses a trade-date convention that happens to align with the roll. "Happens to"
was the problem.

---

## The layer

```
quant_brain/data/
  schema.py        the canonical frame: 12 required fields, DataForm / RollMethod /
                   AdjustmentMethod, validation, content fingerprint
  contracts.py     ESU5 -> (ES, 2025-09). An explicit, bounded century window; refuses
                   anything it cannot resolve exactly
  manifest.py      what a dataset IS, hashed and required. 11 refusals.
  rolls.py         detection (measurement) and adjustment (transformation), kept apart
  quality.py       PASS / WARN / FAIL, deterministic, hashed onto the manifest
  adapters.py      the ONLY place a vendor's column names may appear
  cross_source.py  agreement between two feeds; deliberately cannot rank them
  loader.py        one way in, and the FEATURE vs EXECUTION split
```

### The declaration that makes a dataset admissible

Five things have no default and no inference:

| | |
|---|---|
| `data_form` | RAW · CONTINUOUS_UNADJUSTED · CONTINUOUS_BACK_ADJUSTED · CONTINUOUS_FORWARD_ADJUSTED · OTHER |
| `roll.method` | NONE · CALENDAR_DAYS_BEFORE_EXPIRY · VOLUME_CROSSOVER · OPEN_INTEREST_CROSSOVER · PROVIDER_DEFINED · UNKNOWN |
| `roll.adjustment` | NONE · DIFFERENCE · RATIO · UNKNOWN |
| `session_timezone` | the venue clock; required, never assumed |
| `reconstructible` | and if False, **a reason** |

Contradictions are refused, not reconciled: an adjusted form with `AdjustmentMethod.NONE`, a
`RAW` series with a roll, a continuous series claiming `RollMethod.NONE`, a calendar roll with
no `days_before_expiry`, `PROVIDER_DEFINED` claiming to be reconstructible.

### Three hashes, three questions

| hash | answers |
|---|---|
| `source_hashes` | is this the same **file**? |
| `manifest_id` | is this the same **interpretation** of that file? |
| `frame_fingerprint` | are these the same **bars** that reached research? |

The same parquet read as unadjusted and as back-adjusted shares a source hash and **must not**
share a manifest id. Mutation testing found that the id was blind to the adjustment method
alone; that hole is closed.

### FEATURE vs EXECUTION

The central rule. An adjusted continuous series is legitimate for features and **is refused
as an execution source**:

```
ibkr-ES-1min-backadj: CONTINUOUS_BACK_ADJUSTED prices were never quoted by any venue,
so a fill simulated at one is a fill at a number that did not exist.
```

A run that wants features from one series and fills from another says so, and the report
prints both manifest ids and both fingerprints under `FEATURE DATA and EXECUTION DATA DIFFER`.

---

## What the store turned out to be

Declared now, in `data/manifests/`:

| dataset | form | roll | coverage | bars | quality |
|---|---|---|---|---|---|
| ibkr-ES-1min | CONTINUOUS_UNADJUSTED | calendar, 8 days, **no adjustment** | 2025-06-08 → 2026-09-10 | 447,600 | WARN |
| ibkr-NQ-1min | CONTINUOUS_UNADJUSTED | calendar, 8 days | 2025-06-08 → 2026-09-10 | 447,596 | WARN |
| ibkr-MES-1min | CONTINUOUS_UNADJUSTED | calendar, 8 days | 2025-09-07 → 2026-09-10 | 358,845 | WARN |
| ibkr-MNQ-1min | CONTINUOUS_UNADJUSTED | calendar, 8 days | 2025-09-07 → 2026-09-10 | 358,845 | WARN |
| alpaca-{SPY,QQQ,IWM,DIA}-1min | RAW | none | 2016-01-04 → 2026-09 | ~1,045,000 each | WARN |

Every futures store carries **four rolls of +0.73% to +1.04%** with no adjustment. Every WARN
carries a written reason for why research may still proceed.

### Actual coverage, not architecture support

The schema can hold decades. What is on disk:

- **futures: 15 months**, 326 RTH sessions, **four rolls per instrument, sixteen in total**
- **equities: 10.7 years**, ~2,687 sessions per symbol
- **open interest: none.** A volume- or OI-triggered roll **cannot be reproduced** from this
  store; only a calendar one can. The manifests say so.
- **settlement prices: none.**

Any statement about roll behaviour rests on sixteen observations.

---

## Section 14 — cross-source, and what it found

`cross_source.compare` measures agreement between two feeds for one underlying. It has **no
function that ranks sources**, by P&L or anything else.

ES vs MES, 358,845 shared bars:

- minute-return correlation **0.9875**
- on matched expiries, price difference **p50 0.00, p99 0.50 points**
- **3 of 353,325 matched bars differ by more than 5 points** (worst 52.00, two adjacent
  minutes on 2026-03-23 at 07:05–07:06 ET) — a transient feed divergence, flagged

**The finding:** 5,520 shared bars from **2025-09-07 to 2025-09-11** have ES on **ESU5**
(September) and MES on **MESZ5** (December), because IBKR had already retired MESU5 so the
micro chain starts a quarter later. The mean price difference there is **−54.74 points** —
the Sep/Dec calendar spread, not a feed error.

**Any cross-instrument comparison of ES and MES over that window is comparing two different
expiries.** Nothing in the old data path could have said so.

---

## Section 16 — regression protection

`test_the_canonical_layer_agrees_with_the_existing_loader_on_the_bars_it_keeps` reproduces
the funnel's RTH window and one-contract-per-session filter on the canonical frame and
requires **the same bar count, the same closes and the same contract labels** as
`futures_discover.load`.

No published result changed. The legacy path still runs unmodified; the canonical layer sits
alongside it. Switching the funnel over is a separate, deliberate step.

---

## Section 17 + 20 — the hostile audit

Seventeen attacks, each an actual way to manufacture a profitable backtest through the data:

| attack | outcome |
|---|---|
| roll discontinuity presented as a return | form declared, roll instants on the manifest |
| filling orders at adjusted prices | **refused** |
| double adjustment | **refused** at the declared-source-form level |
| hiding the adjustment metadata | **refused** — form and adjustment must agree |
| shifting timestamps for foresight | fingerprint moves |
| relabelling the timezone | **refused** |
| substituting a contract mid-file | **FAIL** — contract interleaving |
| an unannounced roll | detected from the data, not from a declaration |
| duplicating the best bars | **FAIL** |
| deleting the worst bars | WARN with an exact bar count |
| corrupting volume | **FAIL** |
| corrupting OHLC to reach a stop | **FAIL** |
| mixing raw and adjusted in one frame | inexpressible — one manifest, one form |
| provider column mismatch swapping high/low | mapping recorded, and the frame **FAILs** |
| contract multiplier mismatch | roots resolved and compared |
| **lookahead through continuous construction** | **demonstrated**: the same first bar takes two values depending on future rolls |
| adjusted execution series | **refused** |

The lookahead one is the subtlest and is worth restating: a **back-adjusted price level is not
knowable at the time of the bar.** Returns are safe; levels embed the future.

### Mutation testing

**71 mutations, 71 caught, 100%** — 33 planted in this layer. Three survived the first pass
and were real holes:

- the manifest id was blind to the adjustment method alone
- the fingerprint mutation was too weak to prove anything (fixed the mutation)
- **no test adjusted a frame carrying bid/ask** — so leaving quotes unadjusted, which
  manufactures a spread that grows with the cumulative offset, went unnoticed

All three closed.

---

## Section 18 — performance

Timing and memory measured in **separate passes**: `tracemalloc` inflates wall time ~15x on
this workload, and one number measured under it would understate the engine by an order of
magnitude.

| dataset | MB disk | bars | load s | bars/s | stream s | frame MB | peak MB |
|---|---|---|---|---|---|---|---|
| ibkr-ES-1min | 6.7 | 447,600 | 2.67 | 167,628 | 0.04 | 46.6 | 153 |
| ibkr-MES-1min | 5.3 | 358,845 | 2.08 | 172,666 | 0.04 | 37.7 | 123 |
| alpaca-SPY-1min | 24.1 | 1,046,818 | 6.26 | 167,336 | 0.16 | 97.4 | 351 |
| alpaca-DIA-1min | 20.9 | 1,040,304 | 6.12 | 170,017 | 0.16 | 96.7 | 349 |

`load s` includes the adapter, schema validation **and the full quality gate**. `stream s`
iterates every session via `ResearchDataset.sessions()`, a generator — the store is never
held as N separate DataFrames, which is what `futures_discover.session_frames` does today and
what would not survive ten years of minutes.

Nothing was traded away for this. The gate runs on every load.

---

## Reproducing

```powershell
python scripts/data_manifest.py --scan          # canonicalise and report, write nothing
python scripts/data_manifest.py --write         # write data/manifests/*.json
python scripts/data_manifest.py --cross-source  # ES vs MES, NQ vs MNQ
python scripts/data_manifest.py --benchmark
python -m pytest tests/test_canonical_data.py -q
python scripts/engine_mutation_test.py
```

---

## Remaining limitations

Stated, not hidden.

1. **The research funnel does not use this layer yet.** `futures_discover.load`,
   `overnight_panel` and `futures_topstep_baseline` still read the parquet directly. The
   canonical path is proved bar-for-bar equivalent, but switching them over is a separate
   change with its own regression risk, and doing it silently inside this phase would have
   violated "do not change existing published results".
2. **No trading calendar.** Completeness is still tested structurally (first minute, last
   minute, exact count) rather than against a verified CME holiday table, so a legitimate
   early close is dropped rather than scaled. The gate now separates recurring venue breaks
   from unexplained holes by measuring recurrence, which is as far as one can honestly go
   without a calendar.
3. **Open interest and settlement prices are absent** from every store, so
   `OPEN_INTEREST_CROSSOVER` rolls are declarable but not reconstructible here.
4. **Corporate actions are not modelled.** `RAW` on an equity series means no futures roll —
   it asserts nothing about splits or dividends, and the manifests say so explicitly.
5. **The quotes store is not yet canonicalised.** `data/futures/ES_quotes.parquet` has its own
   layout (`bid`, `ask`, `bid_low`, `ask_high`, `spread`) and the schema has the optional
   columns for it, but no adapter reads it yet.
6. **Sixteen rolls.** Everything this layer says about roll behaviour rests on four rolls per
   instrument across fifteen months.
7. **The one-digit-year window is anchored at 2026** and admits 2022–2031. It is a constant
   rather than a clock so that manifests stay reproducible; it will need moving, deliberately,
   before 2032.
