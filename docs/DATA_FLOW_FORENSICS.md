# Data-flow forensics — the current state, mapped before anything is changed

Priority 3, Section 1. Written **before** any code was modified, because the point of the
exercise is to find where the data assumptions live implicitly, and you cannot find those by
reading a design you are about to write.

Nothing in this document is inferred from a filename. Every claim was measured against the
files on disk.

---

## The flow as it actually runs

```
IBKR TWS API  (paper account DUT091359, server 178)
   │  scripts/futures_fetch_multi.py  --fetch / --quotes
   │  reqHistoricalData, TRADES and BID_ASK, 1-minute bars, per LOCAL SYMBOL
   ↓
data/futures/{ES,NQ,MES,MNQ}.parquet          ← 4-5 contracts SPLICED into one file
data/futures/ES_quotes.parquet                 ← BID_ASK, same timestamps
   │
   ├──→ scripts/futures_discover.py :: load()          the research funnel
   ├──→ scripts/overnight_panel.py :: load_full_session()   its own normalisation
   └──→ scripts/futures_topstep_baseline.py            its own read_parquet
   ↓
   pd.to_datetime(utc=True) → tz_convert("America/New_York") → day, hm
   ↓
   RTH filter: hm between OPEN_ET and CLOSE_ET (caller must now declare the window)
   ↓
   drop any day whose RTH bars carry more than one `contract`
   ↓
   session_frames(): keep only days with EXACTLY SESSION_BARS bars, opening on the
   window's first minute and closing on its last
   ↓
   build_features(): fe.audit_causality() then per-session feature build
   ↓
   spec.signal(X)  →  ledger_builder.build_ledger()  →  CanonicalLedger
   ↓
   P&L layer │ Topstep twin │ monthly / payout
```

---

## What the store actually is

Measured, not assumed:

| store | rows | contracts | coverage (UTC) |
|---|---|---|---|
| `ES.parquet` | 447,600 | ESU5, ESZ5, ESH6, ESM6, ESU6 | 2025-06-08 → 2026-09-10 |
| `NQ.parquet` | 447,596 | NQU5, NQZ5, NQH6, NQM6, NQU6 | 2025-06-08 → 2026-09-10 |
| `MES.parquet` | 358,845 | MESZ5, MESH6, MESM6, MESU6 | 2025-09-07 → 2026-09-10 |
| `MNQ.parquet` | 358,845 | MNQZ5, MNQH6, MNQM6, MNQU6 | 2025-09-07 → 2026-09-10 |

Columns: `t (datetime64[us, UTC])`, `o`, `h`, `l`, `c`, `v (float)`, `contract (str)`.
Quotes store: `t`, `bid`, `ask`, `bid_low`, `ask_high`, `spread`, `c`, `contract`.

**Zero duplicate timestamps. No overlapping contracts** — each contract's window ends exactly
where the next begins.

### The representation, named

| property | measured value |
|---|---|
| data form | **CONTINUOUS_UNADJUSTED** — raw contracts spliced end to end |
| roll trigger | **calendar**: `ROLL_DAYS = 8` days before last trade date |
| roll dates (ES) | 2025-09-11, 2025-12-11, 2026-03-12, 2026-06-10 |
| price adjustment | **none** |
| volume handling | carried through unchanged from each contract |
| open interest | **absent** — never fetched |
| reconstructible | **yes** — `contract` is preserved per bar, so the raw legs can be recovered |

### The roll gaps that are in the file right now

| roll | last price | first price | gap |
|---|---|---|---|
| ESU5 → ESZ5 | 6591.75 | 6647.50 | **+55.75 (+0.846%)** |
| ESZ5 → ESH6 | 6908.00 | 6967.00 | **+59.00 (+0.854%)** |
| ESH6 → ESM6 | 6685.25 | 6732.75 | **+47.50 (+0.711%)** |
| ESM6 → ESU6 | 7267.00 | 7321.25 | **+54.25 (+0.747%)** |
| NQ rolls | — | — | +0.860% to **+1.029%** |

A naive `close.pct_change()` over the whole file therefore contains four fabricated ~0.8%
moves per instrument. Nothing in the file says so.

---

## FINDING 1 — the roll boundary is a fixed UTC instant, so it moves in ET across DST

| roll | last bar of old contract | first bar of new | ET wall clock |
|---|---|---|---|
| ESU5 → ESZ5 | 2025-09-11 16:59 ET | 2025-09-11 **18:00 ET** | EDT, outside RTH |
| ESZ5 → ESH6 | 2025-12-11 15:59 ET | 2025-12-11 **16:00 ET** | **EST, the LAST BAR of RTH** |
| ESH6 → ESM6 | 2026-03-12 16:59 ET | 2026-03-12 18:00 ET | EDT, outside RTH |
| ESM6 → ESU6 | 2026-06-10 16:59 ET | 2026-06-10 18:00 ET | EDT, outside RTH |

In summer the roll lands at 18:00 ET, comfortably outside the 09:30–16:00 RTH window. In
**winter it lands at 16:00 ET — inside it**, because the boundary is a constant UTC time and
ET moves an hour underneath it.

Consequence, measured on ES: **2025-12-11 is the one RTH day of 326 that carries two
contracts** — 391 bars, ESZ5 for 09:30–15:59 and ESH6 for the 16:00 print.

`futures_discover.load` drops it (`groupby("day")["contract"].nunique() == 1`), so **no
published result is contaminated.** But:

- the protection is a filter, not a declaration — nothing states that the roll boundary is
  UTC-fixed or that it is expected to intrude on RTH twice a year;
- the filter depends entirely on the `contract` column existing. A provider file without one
  raises `KeyError` — fail-closed by accident, not by design;
- one session per winter roll is silently lost, and the loss is not reported anywhere.

---

## FINDING 2 — three independent entry points into the same store

| entry point | normalisation it does |
|---|---|
| `futures_discover.load()` | quality gate, UTC→ET, `day`/`hm`, RTH filter, one-contract-per-day filter |
| `overnight_panel.load_full_session()` | UTC→ET, **trade date = ET + 6h**, one-contract-per-*trade-date* filter. No quality gate. |
| `futures_topstep_baseline.py` | `read_parquet` and its own handling |

Three normalisations of one file. They happen to agree today; nothing enforces that they
continue to.

The trade-date convention in `overnight_panel` is the correct one for overnight work and it
is *why* the overnight research is clean: the roll boundary (18:00 ET / 16:00 ET) and the
trade-date boundary coincide, so every overnight return is computed within a single contract.
That safety is real but **incidental** — it follows from two independently chosen constants
lining up, not from a stated invariant.

---

## FINDING 3 — no dataset declares anything about itself

There is no place on disk that records, for any store:

- what economic representation it is (raw / continuous / adjusted, and which adjustment)
- what the roll methodology was
- which provider produced it, at what time, with what parameters
- what timezone its timestamps are in (recoverable from the dtype; not *declared*)
- what the bar interval is (assumed 1 minute; `SESSION_BARS` is computed in minutes)
- what the coverage window is
- a hash of the bytes

The roll rule exists **only as a Python constant in the fetch script** (`ROLL_DAYS = 8`,
`CHAINS`). Re-fetch with a different constant and every downstream result changes with no
signal anywhere.

---

## FINDING 4 — instrument and contract are conflated at the API boundary

`load(store, symbol)` takes `symbol="ES"` and uses it only as a label for the quality report.
The `contract` column carries `ESU5`… and is used only for the one-per-day filter. Nothing
in the type system or the schema distinguishes:

- **instrument** — `ES`, the economic exposure, which owns the multiplier, tick size and
  tick value;
- **contract** — `ESM26`, a physical deliverable with an expiry and its own liquidity.

`quant_brain/markets/futures_cme/instruments.py` resolves terms by **root**, so a bar
labelled `ESU5` and a bar labelled `ESZ5` are priced identically — correct for ES, and an
assumption nothing states.

---

## FINDING 5 — what the existing quality gate does and does not cover

`futures_cme/dataquality.check_futures_frame` is genuinely substantial and already checks:
ordering, duplicates, bar interval, session gaps, session length, contract overlap, contract
ordering, **roll jumps**, within-contract jumps, stale prices, and quotes.

Four gaps, three of them already pinned as `xfail(strict=True)` in
`tests/test_golden_futures.py`:

1. missing bars **inside** a session are not seen
2. duplicate timestamps are not seen by the futures validator's own check
3. impossible OHLC (`h < l`, close outside its range) is **not checked at all** on the
   futures path — `load()` calls only this validator
4. no check that a declared representation matches the data (there is no declared
   representation to check against)

It also has no notion of PASS / WARN / FAIL as a **gate on entry to research** — it raises on
FAIL, but a WARN is printed and forgotten, and nothing records which report a given backtest
ran under.

---

## FINDING 6 — the equity store is a different schema entirely

`data/minute_alpaca/*.parquet`: a `DatetimeIndex` named `date` in UTC, columns `o h l c v`
with `v` as `int64`. No `contract`, no symbol column — the symbol is the **filename**.
1,045,073 rows for AAPL, 2016-01-04 onward.

So the repository already has two incompatible physical layouts, and the symbol for one of
them is carried by the filesystem. Any "provider-agnostic" claim has to survive that.

---

## FINDING 7 — actual historical depth

Stated plainly, because the schema being able to accept more is not the same as having more:

| store | actual coverage | depth |
|---|---|---|
| futures ES / NQ | 2025-06-08 → 2026-09-10 | **15 months**, 326 RTH sessions |
| futures MES / MNQ | 2025-09-07 → 2026-09-10 | **12 months**, ~249 RTH sessions |
| equity minute (Alpaca) | 2016-01-04 → 2026-09 | **10.7 years**, ~2,600 sessions/symbol |

The futures store holds **four rolls per instrument**. Any statement about roll behaviour
rests on four observations per instrument, sixteen in total. That is a sample size, not a
distribution.

Open interest: **not held for any instrument**. Settlement prices: **not held**. A
volume-triggered or open-interest-triggered roll cannot be reproduced from what is on disk,
only a calendar one.

---

## Every implicit assumption, listed

| # | assumption | where it lives | status |
|---|---|---|---|
| 1 | the file is a continuous unadjusted splice | nowhere — inferred | **undeclared** |
| 2 | roll is calendar, 8 days before expiry | `futures_fetch_multi.ROLL_DAYS` | **undeclared to consumers** |
| 3 | prices are unadjusted | nowhere | **undeclared** |
| 4 | the `contract` column exists | `groupby("contract")` | KeyError if absent |
| 5 | timestamps are tz-aware UTC | `pd.to_datetime(utc=True)` coerces | silently coerced |
| 6 | the session timezone is America/New_York | hardcoded in ≥86 places | **hardcoded** |
| 7 | bars are 1 minute | `SESSION_BARS` computed in minutes | assumed |
| 8 | `v` is contract volume | column name only | assumed |
| 9 | the instrument's terms come from the root | `instruments.get(root)` | assumed |
| 10 | the roll never intrudes on RTH | false — see Finding 1 | **filtered, not prevented** |
| 11 | one contract per session | enforced in `load` | enforced |
| 12 | overnight returns never cross a roll | true by coincidence of two constants | **incidental** |
| 13 | no OHLC validity check on the futures path | `check_futures_frame` | **xfail-pinned gap** |
| 14 | the symbol of an equity file is its filename | `data/minute_alpaca/` | **filesystem-carried** |
| 15 | the store has not changed since a result was produced | no hash recorded | **unverifiable** |

---

## What this implies for the build

1. A canonical schema must carry **instrument and contract as separate fields**, and a
   **declared `data_form`** with no default.
2. Roll and adjustment metadata must live **with the dataset**, not in the script that
   happened to fetch it.
3. The three entry points must collapse to one canonical loader, with the others becoming
   callers of it.
4. The DST-mobile roll boundary must be **detected and reported**, not merely filtered.
5. A dataset with no declared representation must be **rejected**, in the same way the 15:45
   session default was removed rather than corrected.
6. Feature data and execution data must be separable, because an adjusted series is
   defensible for the first and not for the second.
7. Every result must reference a **manifest** that pins the bytes it ran on.
