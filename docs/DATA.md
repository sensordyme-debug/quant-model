# Data: every store, what is verified about it, and what is not

Status of this document: an inventory of everything under `data/` and the LEAN data directory
as they stood on 2026-09-13 23:40 ET, at `HEAD = 4fbc22e` plus uncommitted changes. Every
count in it was measured read-only on that date; the command or the file:line is given beside
the number. Where a figure came from `AUDIT_REPORT.md`, `QUANT_MODEL_SYSTEM_AUDIT.md` or a
journal it was re-derived before being repeated, and where the re-derivation disagreed that is
said so (§12).

Nothing in this document writes to `data/`.

| claim | status | evidence |
|---|---|---|
| The four futures stores are structurally clean | **yes** | 0 duplicates, 0 out-of-order, 0 impossible bars, DST correct, 0 interior holes over 1,612,886 rows (§1) |
| The futures rolls are safe to hold through | **no** | raw stitches, +47 to +277 points, no marker anywhere (§2) |
| The spread is measured for every traded contract | **no** | ES and MES yes, NQ measured and **the model is wrong**, MNQ has no quote data at all (§3) |
| The validator catches everything it should | **no** | NaN bars, negative volume, tz-naive stamps and an open outside its own range all pass (§4) |
| Any dataset can be tied to the bytes a result read | **no** | zero content hashes anywhere; no manifest covers the futures stores at all (§5) |
| The options path is live | **no** | Theta lapsed to FREE 2026-09-12; every history endpoint returns HTTP 403 (§8) |

`data/` is **3.5 GB, 2,779 parquet files, and untracked** — `.gitignore:30` is the bare line
`data/`. Nothing in git records what any result was computed on.

---

## 0. Inventory

| store | writer | on disk | coverage | status |
|---|---|---|---|---|
| `data/futures/{ES,NQ,MES,MNQ}.parquet` | `scripts/futures_fetch_multi.py`, `scripts/futures_data.py` | 1,612,886 rows, 26 MB | ES/NQ 2025-06-08 -> 2026-09-10; MES/MNQ 2025-09-07 -> 2026-09-10 | live, manual |
| `data/futures/ES_quotes.parquet` | `futures_fetch_multi.py --quotes` | 447,600 rows, 6.7 MB | 2025-06-08 -> 2026-09-10 | live, manual; **read by nothing but tests** |
| `data/futures/.raw/` | same | 84 pages | ES/MES/NQ BID_ASK + MES/MNQ/NQ TRADES | fetch cache; **MES and NQ quote stores were never assembled** (§3) |
| `Lean/Data/equity/usa/daily/` | `scripts/fetch_data.py` | 82 symbols, 505,175 bars | 1998-01-02 -> 2026-09-04 (69 syms) / 09-10 (13) | live, manual, **adjusted-as-raw** (§6) |
| `data/minute/` | `scripts/intraday_data.py` | 16 symbols, 1,635,362 bars, 35 MB | 2025-08-26 -> 2026-09-11, 263 sessions | live, manual |
| `data/minute_alpaca/` | `scripts/alpaca_data.py` | 69 symbols, 69,261,896 bars, 1.3 GB | 2016-01-04 -> 2026-09-11 | live, manual |
| `Lean/Data/equity/usa/minute/` | `scripts/fetch_minute.py` | SPY only, 652,650 bars | 2020-01-02 -> 2026-09-08 | live, manual |
| `data/options/odte/SPY/` | `scripts/odte_data.py` | 1,891 files, 18,248,558 rows, 125 MB | 2016-01-08 -> **2026-09-10** | **frozen** (§8) |
| `data/options/raw/` | `scripts/iv_regime.py` | 491 files, 3,165,535 rows, 50 MB | 2017-01-06 -> 2026-10-16 | **frozen** |
| `data/options/iv_regime.{parquet,csv}` | `scripts/iv_regime.py` | 2,383 rows | 2017-01-03 -> 2026-09-09 | **frozen** |
| `data/events/earnings.json` | `scripts/events.py` | 568 bytes, 17 symbols | 2026-08-18 -> 2026-10-08 | live, plan-limited (§9) |
| `data/f1/`, `data/f3/` | `scripts/ml_f*.py`, `scripts/sweep_f3.py` | 1.9 GB / 34 MB | derived | derived from `minute_alpaca` and the daily store (§10) |
| `data/rates/`, `data/regime/`, `data/auctions/` | `rates.py`, `regime_data.py`, `sweep_s24.py` | 1.1 MB / 220 KB / 928 KB | see §10 | mixed |

---

## 1. The futures trade stores

Four parquet files, one per root, each a continuous front-month stitch.

**Schema** (identical in all four, read with `pyarrow`):

| column | type | meaning |
|---|---|---|
| `t` | `timestamp[us, tz=UTC]` | bar **start**, tz-aware |
| `o`, `h`, `l`, `c` | `double` | OHLC of the one-minute TRADES bar |
| `v` | `double` | volume |
| `contract` | `string` | the actual contract, e.g. `ESZ5` |

There is no index; `t` is a column, which matters because `core.dataquality.check_frame` reads
`df.index` and reports a spurious timezone failure if handed the frame as stored
(`tests/test_golden_futures.py::test_core_validator_on_a_stored_futures_frame_reports_a_spurious_timezone_failure`).

**Bar stamping is start-of-bar.** This is load-bearing everywhere: `futures_discover`'s
09:30-15:45 window is 376 stamps, not 375 or 377, and a 13:00 ET early close is 210 stamps.

### Measured clean

```python
import pandas as pd
for s in ("ES", "NQ", "MES", "MNQ"):
    df = pd.read_parquet(f"data/futures/{s}.parquet")
    t = pd.to_datetime(df["t"], utc=True)
    print(s, len(df),
          int(df.assign(_t=t).duplicated(subset=["_t", "contract"]).sum()),  # dup (t, contract)
          int(t.duplicated().sum()),                                        # dup t
          int((t.diff() < pd.Timedelta(0)).sum()),                          # backwards
          int((df["h"] < df["l"]).sum()),
          int(((df["c"] > df["h"]) | (df["c"] < df["l"])).sum()),
          int(((df["o"] > df["h"]) | (df["o"] < df["l"])).sum()),
          int(df.isna().sum().sum()))
```

| store | rows | dup (t,contract) | dup t | backwards | h<l | c outside [l,h] | o outside [l,h] | NaN |
|---|---|---|---|---|---|---|---|---|
| ES | 447,600 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| NQ | 447,596 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| MES | 358,845 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| MNQ | 358,845 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **total** | **1,612,886** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |

**Interior session holes: zero**, across all 1,612,886 rows, measured by
`dataquality._check_session_gaps` on the CME trade-date grouping (17:00 CT roll).

**DST is correct at both transitions.** Across all four stores every day's RTH bar count is
drawn from exactly `{210, 225, 376}` — a set with no 316 or 436 in it, which is what a
DST-shifted window would produce. Spot-checked at both 2026 transitions: the Sunday sessions
of 2025-11-02 and 2026-03-08 each hold 360 bars 18:00-23:59 ET at UTC offsets -05:00 and
-04:00 respectively, and the Mondays after each hold 1,380 bars 00:00-23:59 with no repeated
and no missing hour.

**Zero-volume bars inside the 09:30-15:45 ET window** — legitimate, not fatal. The feed emits
a bar for every minute of the session whether or not anything trades, which is what makes a
*missing* minute detectable at all:

| store | zero-volume RTH bars | of RTH rows |
|---|---|---|
| ES | 7 | 120,463 |
| NQ | 297 | 120,463 |
| MES | 70 | 96,672 |
| MNQ | 40 | 96,672 |

(Over the full Globex series, including the overnight, the counts are ES 1,354, NQ 4,258,
MES 2,340, MNQ 1,873.)

**One regime.** ES and NQ start 2025-06-08; MES and MNQ start 2025-09-07. Fifteen months of a
rising market. Nothing in this store contains a drawdown regime, and no walk-forward split of
it can manufacture one. This is the single largest limitation of the futures track and it is
not a code problem.

---

## 2. The rolls — the most serious open data problem

**The four series are raw stitches. Nothing marks a roll: not the store, not a manifest, not
the loader.** The `contract` column changes and that is the only signal there is.

Measured gaps, defined as the previous contract's last close against the new contract's first
open (which is what a position held across the boundary would book):

```python
import pandas as pd, numpy as np
for s in ("ES", "NQ", "MES", "MNQ"):
    df = pd.read_parquet(f"data/futures/{s}.parquet")
    et = pd.to_datetime(df["t"], utc=True).dt.tz_convert("America/New_York")
    c, o, k = df["c"].to_numpy(float), df["o"].to_numpy(float), df["contract"].to_numpy()
    for i in np.where(k[1:] != k[:-1])[0]:
        print(s, k[i], "->", k[i+1], et.iloc[i+1], f"{o[i+1]-c[i]:+.2f} pts")
```

| store | roll | when (ET) | prev close -> new open | gap | as a return |
|---|---|---|---|---|---|
| ES | ESU5 -> ESZ5 | 2025-09-11 18:00 | 6591.75 -> 6649.50 | **+57.75** | +0.876% |
| ES | ESZ5 -> ESH6 | 2025-12-11 **16:00** | 6908.00 -> 6967.75 | **+59.75** | +0.865% |
| ES | ESH6 -> ESM6 | 2026-03-12 18:00 | 6685.25 -> 6735.50 | **+50.25** | +0.752% |
| ES | ESM6 -> ESU6 | 2026-06-10 18:00 | 7267.00 -> 7320.00 | **+53.00** | +0.729% |
| NQ | NQU5 -> NQZ5 | 2025-09-11 18:00 | 24006.75 -> 24255.75 | **+249.00** | +1.037% |
| NQ | NQZ5 -> NQH6 | 2025-12-11 **16:00** | 25714.75 -> 25974.50 | **+259.75** | +1.010% |
| NQ | NQH6 -> NQM6 | 2026-03-12 18:00 | 24568.50 -> 24783.50 | **+215.00** | +0.875% |
| NQ | NQM6 -> NQU6 | 2026-06-10 18:00 | 28472.00 -> 28736.00 | **+264.00** | +0.927% |
| MES | MESZ5 -> MESH6 | 2025-12-11 **16:00** | 6908.00 -> 6967.25 | +59.25 | +0.858% |
| MES | MESH6 -> MESM6 | 2026-03-12 18:00 | 6685.25 -> 6733.00 | +47.75 | +0.714% |
| MES | MESM6 -> MESU6 | 2026-06-10 18:00 | 7267.00 -> 7325.25 | +58.25 | +0.802% |
| MNQ | MNQZ5 -> MNQH6 | 2025-12-11 **16:00** | 25714.75 -> 25972.75 | +258.00 | +1.003% |
| MNQ | MNQH6 -> MNQM6 | 2026-03-12 18:00 | 24567.25 -> 24768.50 | +201.25 | +0.819% |
| MNQ | MNQM6 -> MNQU6 | 2026-06-10 18:00 | 28471.50 -> 28748.00 | **+276.50** | +0.971% |

All fourteen gaps are 0.71%-1.04% — consistent with genuine three-month carry, so these are
real calendar spreads and **not data errors**. That is exactly what makes them dangerous: no
price-level or jump check will ever flag them. `dataquality._check_within_contract_jumps`
groups by contract precisely so it does not fire on them.

### One roll behaves differently and it is a bug

The fetch page boundary is a fixed `"%Y%m%d-21:00:00"` stamp
(`scripts/futures_data.py:360`, `scripts/futures_fetch_multi.py:181`). In EDT that lands at
17:00 ET, which is the start of the daily maintenance halt, so the last bar of the old
contract starts 16:59 and the first bar of the new starts 18:00 — the stitch sits across a
1h01m gap that no rolling window can span. **In EST it lands at 16:00 ET, mid-Globex**, so the
December roll is a single one-minute bar-to-bar step carrying the whole calendar spread:

| store | December roll as a 1-minute return | its rank among all exactly-1-minute steps |
|---|---|---|
| ES | +0.8541% | 3rd of 447,273 |
| NQ | **+1.0286%** | **2nd of 447,269** |
| MES | +0.8577% | 4th of 358,583 |
| MNQ | +0.9946% | 3rd of 358,583 |

The audit's figure of "+1.0286%, 2nd largest of 447,269" reproduces exactly. This is the only
roll in any of the four stores that a one-bar return calculation can see.

### Why it is contained today, precisely

Three things, and only the third is deliberate:

1. **Every roll lands at 16:00 or 18:00 ET, outside the traded 09:30-15:45 ET window.** So no
   RTH session contains a roll bar.
2. **Consequently there are zero mixed-contract days inside the RTH window** — measured, all
   four stores. `futures_discover.load`'s one-contract filter is a live guard that currently
   **drops nothing**. (The "3-4 two-contract days" in `AUDIT_REPORT.md:243` are calendar dates
   in the full Globex series: ES 4, NQ 4, MES 3, MNQ 3. They are not RTH sessions. §12.)
3. **`futures_discover.build_features` builds every feature inside one session** and
   `session_accounting` computes P&L inside one session, so no window and no `.diff()` ever
   spans a session boundary.

Points 1 and 2 are properties of the current data, not of the code. Point 3 is the actual
containment, and it is one function call wide.

### Exactly what would break

Anything that differences across a session boundary books the calendar spread as a return.
Concretely:

- A **multi-day feature** — 5-day momentum, overnight gap, daily ATR, a weekly z-score —
  added to `features.library()`. `build` is called per session today; a feature with a
  cross-session window would need the frame concatenated, and the first `.diff()` over the
  roll returns +264 NQ points as a one-minute move.
- A **position held overnight.** `session_accounting` starts and ends flat by construction
  (`np.diff(pos, prepend=0.0, append=0.0)`), so this cannot happen today. Remove the flatten
  and one contract held over 2025-12-11 books $2,988 of NQ P&L that never existed.
- A **daily resample** of the store, or any `groupby(date)` over the full Globex series rather
  than the RTH window — the roll dates carry two contracts and whichever the groupby picks is
  arbitrary.
- **Any use of a root other than ES/NQ/MES/MNQ**, or any extension of these stores. Nothing
  guarantees a future roll will keep landing outside RTH; the December roll already proves the
  page boundary moves with DST.

`dataquality._check_rolls` reports every roll and warns on any above 0.5%, which all fourteen
are. But it is a **WARN**, and `require_usable` raises only on FAIL, so the funnel loads the
store and prints nothing. Running the validator by hand on all four stores today produces
`roll_gap` WARNs and `roll_overlap` WARNs and no FAIL at all.

**There is no back-adjusted series and no roll-adjustment code anywhere in the repository.**

---

## 3. Quote data and the spread

### `data/futures/ES_quotes.parquet`

447,600 rows, 2025-06-08 -> 2026-09-10. Schema `t, bid, ask, bid_low, ask_high, spread, c,
contract`; `spread` is exactly `ask - bid` on every row (`max |spread - (ask-bid)| = 0.0`).
0 duplicate timestamps, monotonic, 0 non-positive quotes.

| statistic | RTH (09:30-15:45 ET, 120,463 rows) | whole series (447,600 rows) |
|---|---|---|
| median spread | **1.000 tick** (0.25 pts) | 1.000 tick |
| mean | 1.0447 ticks | 1.1279 ticks |
| p90 | **1.00 tick** | **2.00 ticks** |
| p99 | 2.00 ticks | 2.00 ticks |
| max | 3.00 ticks (0.75 pts) | **13.00 ticks (3.25 pts)** |
| share at exactly one tick | 95.54% | 87.66% |

**Crossed and locked rows: 0 crossed, 30 locked.** No row has bid above ask. All 30 locked
rows (`bid == ask`) are consecutive minutes 08:00-08:29 ET on 2025-11-28 — Black Friday
morning, outside RTH. `dataquality._check_quotes` tests `bid > ask` strictly, so a locked
market passes, and so does `Quote.__post_init__` in `execution_sim`. That is defensible; it is
also unstated anywhere but here.

Note the p90 depends on the window. **The commonly quoted "p90 2 ticks" is the whole-series
figure; inside RTH the p90 is 1 tick.** Both are above.

### The spread the cost model actually uses

`CostModel.spread_ticks` defaults to `1.0` and **nothing in the repository ever passes a
different value.** A repo-wide grep for `spread_ticks` outside `tests/` returns three hits,
all inside `execution_sim.py` itself. `measure_spread_ticks` — the function whose whole purpose
is to replace the assumption with the tape — is called only from
`tests/test_qb_execution_sim.py` and `tests/test_golden_futures.py`.
`data/futures/ES_quotes.parquet` is read by those tests and by an existence check in
`quant_brain/__main__.py:115`. **No research path reads it.** The measured ES spread agrees
with the assumption, but nothing wires the one to the other.

### MES and NQ quotes exist on disk, unassembled — and one of them contradicts the model

`data/futures/.raw/` holds the paged BID_ASK fetches. `scripts/futures_fetch_multi.py --quotes`
assembles them into `<SYM>_quotes.parquet`; that was done for ES and not for the others:

| root | BID_ASK raw pages | rows | assembled store |
|---|---|---|---|
| ES | 19 | 567,735 | **yes** |
| MES | 15 | 447,480 | **no** |
| NQ | 1 | 30,120 | **no** |
| MNQ | **0** | — | no data at all |

Restricting the raw pages to the front month by joining on the `(t, contract)` pairs the trade
store already carries — the same roll rule — and measuring the RTH window:

```python
import pandas as pd, glob
raw = pd.concat([pd.read_parquet(f) for f in glob.glob("data/futures/.raw/NQ_*BID_ASK*.parquet")])
raw["t"] = pd.to_datetime(raw["t"], utc=True)
tr = pd.read_parquet("data/futures/NQ.parquet")[["t", "contract"]]
tr["t"] = pd.to_datetime(tr["t"], utc=True)
q = raw.drop_duplicates(["t", "contract"]).merge(tr, on=["t", "contract"])
hm = q["t"].dt.tz_convert("America/New_York").dt.strftime("%H:%M")
sp = q[(hm >= "09:30") & (hm <= "15:45")]["spread"]
print(sp.median() / 0.25, (sp <= 0.25001).mean())      # -> 2.0  0.0475
```

| root | RTH rows | coverage | median spread | one-tick share | model assumes | **measured** |
|---|---|---|---|---|---|---|
| ES | 120,463 | 2025-06-08..2026-09-10 | 1.000 tick | 95.54% | $12.50 | $12.50 — correct |
| MES | 96,672 | 2025-09-07..2026-09-10 | 1.000 tick | 93.62% | $1.25 | $1.25 — correct |
| **NQ** | 8,106 | 2025-08-12..2025-09-11 | **2.000 ticks** | **4.75%** | $5.00 | **$10.00 — the model is half** |
| MNQ | — | — | **unmeasurable** | — | $0.50 | unknown |

**The NQ finding is material and is new here.** NQ's tick is 0.25 index points on a ~24,000
index — about 3.5x finer, relative to price, than ES's 0.25 on ~6,800 — and the book sits two
to three ticks wide accordingly. Only 4.75% of RTH minutes are one tick wide, and the p90 is
3 ticks. The cost model charges one tick, so a modelled NQ round turn is
$3.78 + $5.00 = **$8.78** where the measured spread implies $3.78 + $10.00 = **$13.78**. The
model undercharges the NQ round turn by **36%**.

Two caveats, both real: the NQ sample is a single fetch page, 8,106 RTH bars over one month
(2025-08-12 to 2025-09-11), so the median is well determined but the period is not
representative of fifteen months; and the funnel prices its NQ grid on NQ bars but **sizes in
MNQ**, so what the cost gate actually charges is MNQ's spread, which is the one contract with
no quote data at all. If MNQ tracks NQ the way MES tracks ES, MNQ's spread is also ~2 ticks
and its round turn is $2.22 rather than the modelled $1.72 — a 29% undercharge. **That last
sentence is a conjecture, not a measurement.** Fetching MNQ BID_ASK would settle it.

---

## 4. The data validators

`futures_discover.load` runs exactly one gate:
`quant_brain.markets.futures_cme.dataquality.require_usable(symbol, df, time_col="t")`. It does
**not** run `quant_brain.core.dataquality.check_frame`. That matters, because the core
validator's zero/NaN/negative-price, tz-naive and holiday checks therefore never run on the
futures path.

`check_futures_frame` currently calls, in order: `_check_ordering`, `_check_duplicates`,
`_check_session_gaps` (+ `_check_session_length` only if a calendar is passed, and the default
is `None`), `core.dataquality.check_bar_structure`, `_check_overlap`, `_check_contract_order`,
`_check_rolls`, `_check_within_contract_jumps`, `_check_stale`, `_check_quotes`.

Only FAIL findings raise. What each severity means in practice, probed against a 400-bar
synthetic frame (read-only; the probe constructs the frame in memory):

| planted defect | caught? | as |
|---|---|---|
| the same minute of the same contract twice | **FAIL** | `duplicates` |
| 7 bars deleted from mid-session | **FAIL** | `session_gap` |
| timestamps out of order | **FAIL** | `time_order` |
| high < low | **FAIL** | `impossible_bar` |
| close outside [low, high] | **FAIL** | `impossible_bar` |
| >20% move inside one contract | **FAIL** | `impossible_move` |
| a whole bar of zeros | **FAIL** | `impossible_move` only — incidentally, via the jump rule |
| contract reappears after the series moved on | FAIL | `roll_backwards` |
| bid above ask | FAIL | `crossed_book` |
| **a NaN close (or a whole NaN bar)** | **NO** | passes silently |
| **NaN volume** | **NO** | passes silently |
| **negative volume** | **NO** | passes silently |
| **open outside [low, high]** | **NO** | `check_bar_structure` reads `h`, `l`, `c` and never `o` |
| **tz-naive timestamps** | **NO** | the core validator's check, not run here |
| a roll gap of any size | WARN only | `roll_gap` — does not block |
| two contracts on one date | WARN only | `roll_overlap` |
| an unchanged price run with real volume | WARN only | `stale_quote` |
| no bid/ask columns at all | INFO | `quotes`: "the spread is ASSUMED by the cost model" |

The duplicate, session-gap and bar-structure checks are recent — the module docstring records
that until `tests/test_golden_futures.py` pinned them, three hazards the core validator has
always caught had no gate on the futures path at all, and that golden dataset I (seven deleted
bars) passed.

Run against the four real stores today, **all four pass** (`rep.failed is False`), with these
findings:

```
ES   WARN roll_overlap  4 date(s) carry more than one contract (first 2025-09-11)
ES   INFO rolls         4 roll(s); largest unadjusted gap 0.85%
ES   WARN roll_gap      4 roll(s) gap at least 0.5% unadjusted
ES   INFO stale_quote   1 unchanged run of 120+ bars (longest 645), negligible volume
ES   INFO quotes        no bid/ask columns: the spread is ASSUMED by the cost model
```

with NQ, MES and MNQ identical in shape (NQ largest gap 1.03%, MES 0.86%, MNQ 0.99%; the
micros have 3 rolls, not 4). `ES_quotes.parquet` also passes and, having bid/ask columns,
emits no `quotes` INFO.

The 645-bar stale run is Thanksgiving night 2025 — 21:44 to 08:29 ET with six contracts of
total volume. A closed market, correctly graded INFO rather than WARN because the volume test
distinguishes a shut exchange from a frozen feed.

### What the validator still does not do

- **No session-length check for futures**, because there is no CME calendar to check against
  (see `docs/FUTURES.md` §3). The `calendar` argument defaults to `None` and passing
  `equity_us.CALENDAR` reports the caller rather than the data.
- **No positivity or finiteness check on `o`/`h`/`l`/`c`/`v`.** Four of the five gaps in the
  table above are this one gap.
- **No cross-store consistency check.** ES and MES quote the same underlying and nothing
  compares them; a corrupted MES page would have to be caught by eye.
- **No coverage check.** Nothing asserts that a store reaches a particular date, so a fetch
  that silently stopped early is a shorter store, not an error.
- **No hash, no provenance, no record of what produced the file.** §5.

---

## 5. The manifests carry no content hash — and none of them covers the futures stores

There are two manifests and one capability probe:

| file | written by | describes | hash? |
|---|---|---|---|
| `research/data_manifest.json` | `scripts/fetch_data.py:312` | the LEAN **daily equity** store: 82 symbols, per-symbol `bars, first, last, clamped_bars, factor_rows, adj_close_dev` | **no** |
| `research/minute_manifest.json` | `scripts/fetch_minute.py:48` | the LEAN **minute** store, **`spy` only**: 1,679 sessions, 652,650 bars | **no** |
| `research/futures_capability.json` | `scripts/futures_capability_audit.py` | an **IBKR capability probe** — which bar types and resolutions the account can request. Not a data manifest at all | **no** |

```python
import json, re
for f in ("research/data_manifest.json", "research/minute_manifest.json",
          "research/futures_capability.json"):
    print(f, bool(re.search(r"sha|hash|md5|checksum|digest", open(f, encoding="utf-8").read(), re.I)))
# -> False False False
```

**Verified: no content hash, checksum or digest of any kind appears in any of the three.**

**There is no manifest for `data/futures/` at all.** The 1.6 M futures bars every result in
`docs/FUTURES.md` rests on have no manifest, no hash, no row count on record and no fetch
timestamp outside the parquet file's mtime.

`data/minute/` (the IBKR intraday store) also has no manifest; `research/minute_manifest.json`
describes a different store.

Hashing does exist in this repository, and it hashes **code**, never file bytes:
`scripts/sweep_f1.py:204` and `scripts/ml_f20.py:545` fingerprint the *source text* of their
builder functions plus a repr of the feature constants; `core/provenance.py:132` hashes a
config dict; `core/validation.py:393` hashes an in-memory holdout array;
`core/idempotency.py:36` hashes an order payload. The `.meta.json` sidecars in `data/f1/`
show the pattern exactly — a code digest, and for the store only a file **count** and an
**mtime**:

```
{"panel":"panel.parquet","code":"055ba590491cb8e9","store_dir":"data\\minute_alpaca",
 "store_files":69,"store_newest":1789276248.049,"stamped":"2026-09-13T15:06:34+00:00"}
```

A file count and an mtime do not identify bytes. **No result in this repository can be tied to
the data it read.**

---

## 6. Daily equity store (LEAN format)

Written by `scripts/fetch_data.py` from yfinance (`fetch_data.py:88`, `auto_adjust=False,
actions=True`) into `../Lean/Data/equity/usa/{daily,map_files,factor_files}`. Universe:
19 ETFs (`fetch_data.py:48`) + 50 megacaps (`fetch_data.py:54`) = 69 with `--universe all`;
82 symbols are on disk and in the manifest. Per symbol: `daily/<sym>.zip` holding CSV rows
`yyyyMMdd 00:00,o,h,l,c,v` with OHLC scaled x10,000 as integers (`fetch_data.py:44,112`), a
map file, and a factor file `yyyyMMdd,price_factor,split_factor,reference_price`.

Measured from the manifest: **82 symbols, 505,175 bars, 6,703 factor rows**, earliest first bar
1998-01-02, `last` = 2026-09-04 for 69 symbols and 2026-09-10 for 13. **The store is not
uniformly current.** Max `adj_close_dev` across all 82 is 3.3e-05, well inside the 0.01 check
threshold (`fetch_data.py:300`). 13 further zips in the same directory (`aaa, aig, bno, eem,
fb, foxa, gooav, goocv, goog, nwsa, uw, wm, wmi`) are untouched LEAN sample data.

**AUD-17, adjusted-as-raw: confirmed, and reproduced.** Yahoo's OHLC are already
split-adjusted, and `fetch_data.py:164` writes a literal `1` into the split column of every
factor row. Measured:

```python
import json, csv, os
d = json.load(open("research/data_manifest.json", encoding="utf-8"))["data"]
base = "C:/Users/ashur/Quant-Model/Lean/Data/equity/usa/factor_files"
n = bad = 0
for sym in d:
    for row in csv.reader(open(os.path.join(base, f"{sym}.csv"))):
        if len(row) >= 3:
            n += 1; bad += float(row[2]) != 1.0
print(n, bad)          # -> 6703 0
```

**0 of 6,703 factor rows across all 82 symbols carries a split factor other than 1.** The
consequence is visible in the bars: `nvda.zip`'s earliest close (1999-01-22) is **$0.041** and
`soxs.zip`'s earliest close (2010-03-11) is **$580,032,004,096 per share** — split adjustment
applied backwards into the price series with the factor file claiming no splits ever happened.

Its prescribed remedy was **refused with evidence**, which is the part usually left out.
D-7 (`scripts/sweep_d7.py`) measured that rewriting the store with true raw prices and real
split factors "would move 430,639 bars and correct nothing", because the fee mis-charge
belongs to `DataNormalizationMode.ADJUSTED` plus a per-share fee, not to the factor files. At
champion size the measured effect is fees of $27,199.76 charged against $21,320.92 true —
**an overcharge of $5,878.84, -21.61% of fees and -0.248% of net profit**
(`research/journal.md:405`). The defect is open as a data defect; the follow-ons are D-8 (fee
model), D-9 (whole-share orders round to zero on 10,541 sessions, SOXS on 95.2% of its
history) and S-44. `AUDIT_REPORT.md:673` and `QUANT_MODEL_SYSTEM_AUDIT.md:298` still list it as
simply open, which understates what is known about it.

Status: **live, manual, partially stale.** No scheduled task fetches it — the four
`install_*.ps1` scripts install the intraday sleeve, the paper trader, the dashboard and the
gateway watchdog, and none of them calls a fetcher.

---

## 7. Minute stores

### IBKR — `data/minute/`

`scripts/intraday_data.py` (clientId 61, pacer 45 requests / 10 min at
`intraday_data.py:55`), path from `intraday_common.py:23`. **16 symbols** — the
`intraday_common.UNIVERSE` sleeve: AAPL AMD AMZN AVGO COIN GOOGL META MSFT MSTR NFLX NVDA PLTR
SMCI SOXL SOXS TSLA — **1,635,362 bars**, 35 MB, 2025-08-26 13:30 UTC -> 2026-09-11 19:59 UTC,
263 sessions each. Schema `o,h,l,c: double, v: double`, index `date: timestamp[us, tz=UTC]`.
Note `v` is a **double** here and an **int64** in the Alpaca store.

`data/minute/_splits.json` holds per-symbol cumulative split factors (NFLX 10.0 -> 1.0,
SOXS 0.005 -> 0.1 -> 1.0, the rest flat).

Verified: 0 rows at or after the session close and 0 rows on a full-day closure, measured
against `quant_brain.markets.equity_us.CALENDAR` (`research/journal.md:585`).
`scripts/store_health.py` reports 16 truncated sessions. **No manifest.**

### Alpaca SIP — `data/minute_alpaca/`

`scripts/alpaca_data.py`, `feed="sip"`, `adjustment="split"`, target dir forced at
`alpaca_data.py:30`. **69 symbols, 69,261,896 bars, 1.3 GB**, 2016-01-04 -> 2026-09-11 (ragged
by symbol: 2026-09-09 for 16, 09-10 for 48, 09-11 for 6; late listings start later — COIN
2021-04-14, PLTR 2020-09-30, UBER 2019-05-10). Schema `o,h,l,c: double, v: int64`, index
`date: timestamp[us, tz=UTC]`. Keys `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` required at
`alpaca_data.py:232` and present in `live/secrets.env`. The free plan withholds the last
15 minutes, clamped at `alpaca_data.py:59`.

Known defects, all measured elsewhere and repeated here with their scope:
- 22,081 post-close rows (0.1494%) on 21 early closes — but that figure is over the **16-name
  intraday universe only** (14,781,245 rows), not the 69-symbol store.
- `store_health.py`: 5,710 sparse sessions (benign) and 262 truncated sessions.
- SOXS: 440,528 of 935,770 bars (47.1%) have `v == 0`, and the zero-volume fraction is 1.000
  for every year 2016-2019 — split-adjusted volume truncated to int64. Max close
  $768,499,200 per share (`QUANT_MODEL_SYSTEM_AUDIT.md:298`).

**No manifest, no hash.**

### LEAN minute — `Lean/Data/equity/usa/minute/`

`research/minute_manifest.json`, generated 2026-09-09, source "IBKR reqHistoricalData 1 min
TRADES useRTH=True". **`spy` only**: 1,679 sessions, 652,650 bars, 2020-01-02 -> 2026-09-08,
0 missing sessions, 0 short sessions, 0 clamped bars, `close_dev` 0.009569 on 2025-04-09. Nine
other symbol folders exist with 4-12 files each; those are LEAN sample data.

---

## 8. Options — Theta Data, currently LAPSED

**Plan: FREE.** `scripts/theta_data.py:7` records it: "Options FREE as of 2026-09-12 13:32
(it was STANDARD on 2026-09-10 02:24; both `Subscriptions:` lines are in the terminal's own
terminal.out)". On FREE only `/v3/option/list/*` answers.

**Error: HTTP 403**, body "you only have a FREE subscription" (`BLOCKERS.md:111`,
`research/journal_options.md:22,403,543,673,817`).

An earlier diagnosis of **HTTP 478** was wrong and the journal corrects itself at
`journal_options.md:821`: 478 is "Invalid session ID", produced by running two Theta Terminals
at once, not an entitlement error. `theta_data.py:64` and `:118` now refuse to start a second
terminal. **478 is not the code; 403 is.** The oldest entry in the journal
(`journal_options.md:1001`) still says 478 and should be read as superseded.

Tier needed to restore the 0DTE path: **VALUE** (`/v3/option/history/quote`). STANDARD is
needed only by `scripts/iv_regime.py` for greeks and EOD rows.

Frozen stores:

| store | files | rows | last date |
|---|---|---|---|
| `data/options/odte/SPY/` | 1,891 | **18,248,558** | **2026-09-10** |
| `data/options/raw/` (per-expiration EOD greeks) | 491 | 3,165,535 | expirations to 2026-10-16 |
| `data/options/iv_regime.parquet` / `.csv` | 1 each | 2,383 | 2026-09-09 |

0DTE schema (`odte_data.py:35`): `strike: float32, right: large_string (C/P),
timestamp: timestamp[us], bid: float32, ask: float32, bid_size: int32, ask_size: int32`,
5-minute bars, +/-30 strikes, zstd. `scripts/sweep_o2.py` prices every fill at the quote,
never the mid.

`data/regime/spy_iv.csv` (2,192 rows, to 2026-09-09) is a re-export of `iv_regime.csv` and is
therefore frozen too.

Status: **BLOCKED**, filed as owner blocker OWNER-5 (`BLOCKERS.md:102`).

---

## 9. Events — FMP

`scripts/events.py`, endpoint `financialmodelingprep.com/stable/earnings-calendar`
(`events.py:27`), key `FMP_API_KEY` (`events.py:83`, present). **Basic plan**: the docstring at
`events.py:9` records that only the earnings calendar is served — economic-calendar and news
endpoints are not on this plan (checked 2026-09-10). HTTP 402/403 windows are skipped rather
than raised (`events.py:39`), so a plan refusal produces a smaller file, not an error.

`data/events/earnings.json` is **568 bytes**: `generated` 2026-09-10, **17 symbols, 17 dates**,
spanning 2026-08-18 -> 2026-10-08. The default `--days-back 400` window is mostly refused by
the plan, which is why so little landed. Consumed by `events.earnings_window()`
(`events.py:62`).

Status: live, plan-limited, 3 days stale.

---

## 10. Derived stores

| path | writer | contents |
|---|---|---|
| `data/f1/` | `scripts/ml_f7..f23.py` | **1.9 GB**, 65 top-level entries + 2 subdirs. F-track ML panels and predictions: `panel.parquet` 171 MB, `f21_panel62.parquet` 188 MB, `f14_flow.parquet` 98 MB, `f19_panel*.parquet` 171/172 MB, plus `*_arms.csv`, `*_gate.csv`, `*_admitted.json`. Subdirs `f10_cache/` (127 files) and `f15_auctions/` (57 files, Alpaca `/v2/stocks/auctions`). All derived from `data/minute_alpaca`; no raw market data. |
| `data/f3/` | `scripts/sweep_f3.py --build` | **34 MB**, 2 files. `panel.parquet` 128,882 rows x 49 columns built from the LEAN daily store; `ml_scores.csv` 796 KB, the LEAN-consumable export. |
| `data/rates/` | `scripts/rates.py:49` (FRED `DFF`, no API key), `scripts/sweep_s21.py:150` | `usd_benchmark.csv` 26,369 rows 1954-07-01..2026-09-09; `usd_flat_2026.csv` same shape, a today's-benchmark counterfactual used by the S-track sweeps; `_s21_book.csv` 3,689 rows. |
| `data/regime/` | `scripts/regime_data.py:41` | `vix.csv` 5,459 rows 2005-01-03..2026-09-11 (Yahoo `^VIX`); `spy_iv.csv` 2,192 rows, a re-export of the frozen Theta IV store. |
| `data/auctions/` | `scripts/sweep_s24.py:72` (Alpaca auctions + quotes) | 9 sleeve names x 2,688 rows 2016-01-04..2026-09-10 with `open_px, open_sz, open_x, close_px, close_sz, close_x`; plus `s24_quote_windows.parquet`, 6,074 rows over 5 intraday windows. |
| `data/daily_splits.json` | `scripts/sweep_d7.py:98` | 6,750 bytes. The validated split calendar D-7 built as a sidecar **instead of** migrating the daily store (§6). |

None of these carries a content hash of its inputs; the `.meta.json` sidecars record a code
digest plus a file count and mtime (§5).

---

## 11. Credentials

`scripts/apikeys.py:14` reads `live/secrets.env` (gitignored at `.gitignore:14`) and
`apikeys.py:26` also accepts these names from the environment. **Names only; no value was read
or printed:**

```
ALPACA_API_KEY   ALPACA_SECRET_KEY   THETADATA_API_KEY   FMP_API_KEY
POLYGON_API_KEY  FINNHUB_API_KEY     NASDAQ_DATA_LINK_API_KEY   TELEGRAM_BOT_TOKEN
```

`live/secrets.env` defines four of the eight: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`,
`THETADATA_API_KEY`, `FMP_API_KEY`. `THETADATA_API_KEY` is not read by any Python file — the
Theta Terminal jar consumes it (`theta_data.py:3`). The remaining four names are anticipated
by `apikeys.py` and not used by any fetcher.

`.env.example` declares a separate, execution-side set (`QB_ACCOUNT_MODE`, `QB_VENUE`,
`QB_LIVE_TRADING_ENABLED`, `DRY_RUN`, `PROJECTX_USERNAME`, `PROJECTX_API_KEY`, ...) with
placeholders only.

**Not verified: whether the Alpaca or FMP keys still authenticate.** No network call was made
for this document. "Live" for those two means the key name is present, the code path is
unblocked, and the data is recent. Theta is the only source where the code records a currently
failing probe.

---

## 12. Where I corrected the record

1. **"`futures_discover` drops the 3-4 days that carry two contracts"**
   (`AUDIT_REPORT.md:243`). There are **zero** mixed-contract days inside the traded
   09:30-15:45 ET window in any of the four stores; the one-contract filter drops nothing
   today. The 3-4 dates are calendar dates in the full Globex series. §2.
2. **"the spread for MES/NQ/MNQ was never measured"** (widely repeated, and true of the
   *code*). MES and NQ BID_ASK data are already on disk in `data/futures/.raw/`. Measured for
   this document: MES median 1.00 tick (the assumption is right), **NQ median 2.00 ticks (the
   assumption is wrong by a factor of two)**. Only MNQ genuinely has no quote data. §3.
3. **`research/minute_manifest.json` described as the manifest for `data/minute`.** It is not;
   it describes the LEAN minute store and covers `spy` only. `data/minute` has no manifest. §7.
4. **The Theta entitlement error is HTTP 403, not 478.** The journal corrects its own earlier
   478 diagnosis at `journal_options.md:821`; 478 was two terminals fighting over a session
   ID. §8.
5. **"the Alpaca store, 14,781,245 rows."** That is the 16-name intraday universe. The store is
   **69,261,896 rows across 69 symbols**, 4.7x larger. §7.
6. **AUD-17 described as simply open.** It is open as a data defect but its prescribed
   remedy was measured and refused with evidence (D-7): rewriting the store would move 430,639
   bars and correct nothing, and the actual mis-charge is an **overcharge** of $5,878.84. §6.

---

## 13. What would make this data trustworthy, and is not done

In the order a day of work would buy the most:

1. **Content hashes on every manifest, verified on load.** Zero digests exist today (§5).
   Hashing the whole 3.68 GB tree costs ~9 seconds, so there is no cost argument. Until this
   exists, no result can be tied to the bytes it read, and `reproducible: true` appears on 0 of
   1,653 rows of `research/experiments.jsonl`.
2. **A manifest for `data/futures/` at all.** The store every futures result rests on has none:
   no row count, no coverage, no fetch time, no hash (§5).
3. **A roll marker in the futures stores**, and preferably a back-adjusted companion series.
   Today the containment of a +276-point stitch is one design decision in one function, and
   the first multi-day feature anyone adds removes it (§2). A boolean `is_roll` column and a
   `_check_rolls` promotion from WARN to FAIL-unless-acknowledged would both be cheap.
4. **A measured spread per contract, wired into `CostModel.spread_ticks`.** MES and NQ can be
   assembled from raw pages already on disk in minutes; MNQ needs one fetch. The NQ measurement
   already invalidates the assumption for that root (§3), and nothing currently passes a
   measured value to the cost model even for ES.
5. **A verified CME futures calendar.** Its absence forces `session_frames` to discard 13 of
   326 ES sessions of perfectly good early-close data, and makes `check_futures_frame`'s
   session-length check unusable (`docs/FUTURES.md` §3).
6. **Positivity and finiteness checks in the futures validator.** A NaN bar, a NaN or negative
   volume, and an open outside its own range all pass today (§4).
7. **A second market regime in the futures store.** Fifteen months of one rising market
   (§1). This is a data-acquisition problem, not a code problem, and it is the binding
   constraint on the whole futures track.
8. **Restore the Theta VALUE tier** to unfreeze the 0DTE store, or accept that
   `data/options/` is a fixed historical archive ending 2026-09-10 (§8).
