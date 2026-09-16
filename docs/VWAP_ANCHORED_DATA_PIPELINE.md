# PHASE 2 — the 18:00-anchored historical data path

Certification of the data the frozen V1.0.0 strategy will run on. **No strategy was run. No
P&L, Sharpe, win rate, drawdown, payout probability or Topstep pass probability was computed,
and `run_strategy.py` was not called.** This document is about whether the bars are right.

---

## 1. The data flow as it actually is

Every step below was read, not assumed. Where a step behaves differently from what its name
suggests, the difference is written down rather than tidied.

```
  RAW STORE            data/futures/{ES,NQ,MES,MNQ}.parquet
                       columns t,o,h,l,c,v,contract — 1-minute TRADES bars, UTC-stamped,
                       written by scripts/futures_fetch_multi.py. Each contract was fetched
                       separately over a window ending 8 days before its last trade date,
                       then CONCATENATED WITH NO PRICE ADJUSTMENT.
        |
        |  quant_brain/data/adapters.py :: ibkr_futures
        |  the only place the vendor's column names appear. Declares — does not infer —
        |  DataForm.CONTINUOUS_UNADJUSTED, RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY(8),
        |  AdjustmentMethod.NONE, and refuses a file whose contracts resolve to more than
        |  one root or to a root the caller did not ask for.
        v
  CONTRACT NORMALISATION
                       instrument / contract_symbol / contract_family on EVERY bar.
                       There is no separate normalisation step: the physical contract is
                       carried per bar and never collapsed.
        |
        |  quant_brain/data/schema.py :: validate_frame     (structure: 12 required columns,
        |                                                    tz-aware UTC, one bar interval)
        |  quant_brain/data/quality.py :: check             (content: duplicates, gaps,
        |                                                    impossible bars, stale runs,
        |                                                    mixed-contract sessions →
        |                                                    PASS/WARN/FAIL, hashed)
        v
  CANONICAL FRAME      + DatasetManifest (source file hashes, roll spec, quality summary,
                       manifest_id). A FAIL raises; research cannot see it.
        |
        |  quant_brain/strategies/vwap_pullback/data.py :: load_anchored      ← NEW
        v
  ANCHORED SESSION     one trading day = 18:00 ET on the previous calendar day → 15:45 ET.
                       ONE continuous session. It is not split at midnight, not split at
                       09:30, and not split at the calendar date change.
        |
        |  _to_bars
        v
  1-MINUTE Bar[]       the engine's only input type, validated per bar (tz-aware, OHLC
                       consistent, volume >= 0).
        |
        |  FiveMinuteAggregator, INSIDE the engine — no data-layer resampling exists
        v
  5-MINUTE BARS        clock-aligned on the venue clock; a bucket becomes visible only once
                       its final minute has closed and the next bucket has begun.
        |
        |  SessionVwap, INSIDE the engine
        v
  VWAP INPUT           one array per anchored session, typical-price and volume weighted,
                       reset at 18:00 ET and nowhere else.
        v
  STRATEGY ENGINE      not exercised in this phase.
```

### What did NOT survive inspection unchallenged

- **`research/session_source` is the wrong tool and stays the wrong tool.** It cuts
  09:30–16:00 and drops incomplete days, which throws away 930 of every 1,306 bars before
  the engine could see them (CONFLICT C6). It is reused for the equivalence check and
  otherwise untouched — it remains certified for RTH work.
- **`scripts/vwap_data_readiness.py` counted 326 usable ES sessions.** That used an
  80%-of-span threshold, which was the right question for DECISION 9 ("is there enough
  data?") and is the wrong question for a backtest. It now says so and defers to the loader,
  which counts **313**.
- **Seven defects were found and fixed**, three of them in code that was already certified
  or already shipped. §6.

---

## 2. The session, and the number of bars in it

An anchored session runs from **18:00:00 ET on the previous calendar day** to **15:45:00 ET**,
inclusive of both endpoints, on 1-minute **start-stamped** bars. That is the repository's
existing convention — `session_source` treats 09:30–16:00 as 391 bars, not 390 — and it is
applied here unchanged.

**The expected bar count is derived per session, never assumed.** `expected_minutes()`
localises 18:00 and 15:45 with `zoneinfo`, converts both to UTC and walks minute by minute.
The count is whatever that walk produces:

| session | bars | why |
|---|---|---|
| ordinary | **1,306** | 360 (18:00–23:59) + 945 (00:00–15:44) + 1 |
| spanning a spring-forward | **1,246** | 02:00–02:59 ET does not exist |
| spanning a fall-back | **1,366** | 01:00–01:59 ET happens twice |

**No real anchored session spans a DST transition**, and that is permanent rather than lucky:
US DST changes at 02:00 on a Sunday and the week's first anchored session opens at 18:00 that
same evening. Measured across all 327 ES sessions, every one has exactly one UTC offset. The
1,246 and 1,366 cases are therefore tested on the *hypothetical* Saturday-anchored session
(18:00 Sat → 15:45 Sun), which does span both — the same arithmetic, exercised where it can
actually be observed. The fall-back case also produces two bars labelled 01:30, so the
completeness scan works on POSITIONS rather than wall-clock labels.

Boundaries are pinned to the second — 17:59:59 / 18:00:00 / 18:00:01, 09:44:59 / 09:45:00,
15:29:59 / 15:30:00 / 15:30:01, 15:44:59 / 15:45:00 / 15:45:01 — in a table that states which
bar each instant falls in, whether it is inside the session, and which trading day it belongs
to.

---

## 3. The completeness rule

A session is **COMPLETE**, and only then fed to the strategy, when all four hold:

1. the **18:00 anchor bar** is present,
2. the **15:45 flatten bar** is present,
3. every minute between them is present **exactly once**,
4. **one contract** covers all of them.

Anything else is kept in the dataset with a measured reason and excluded from the strategy
feed. `AnchoredSession.bars` is empty for a refused session, so a caller cannot use one by
forgetting to check.

| status | meaning | fed to the strategy |
|---|---|---|
| `COMPLETE` | all four hold | **yes** |
| `TRUNCATED_END` | whole from the anchor to a close earlier than 15:45 | no |
| `HOLED` | a gap inside the session | no |
| `NO_ANCHOR` | never reached 18:00 | no |
| `MULTI_CONTRACT` | two physical contracts in one session | no |
| `CORRUPT` | duplicate stamps, impossible OHLC, negative volume | no |

An **empty dataset is refused outright**, not returned. A backtest that silently scores zero
sessions reports no loss, no drawdown and no trades, and reads exactly like a strategy that
never triggered — the shape of `flatten_leg_dropped__the_original_2026_defect`.

### Why it is not a percentage

**NQ 2025-06-10 is 1,305 of 1,306 bars — 99.92% complete — and unusable.** The one absent
minute is 18:00 itself. Under any threshold rule it passes; the VWAP then anchors at 18:01
against a series the specification never defined, and every band, zone test and regime
decision for the whole day is computed off it. (NQ 2025-06-11 is the same defect, three
minutes wide.) These two are the entire difference between NQ's 311 usable sessions and ES's
313 — the stores are otherwise identical in shape.

### Why a short session is refused rather than shortened

Fourteen ES sessions have no 15:45 bar; their last bar falls at 12:59, 13:14 or 09:14 ET. They
are *whole* up to that point; the overnight is complete. They are refused because the frozen
specification flattens at **15:45** and on those days 15:45 does not exist. Running them would
mean either inventing a substitute flatten time — a change to a frozen rule — or leaving a
position open into the 18:00 roll, which the engine treats as an invariant violation. Refusing
costs 14 of 327 sessions (4.3%) and invents nothing.

**WHY those bars are absent is not determined, and the record says so.** An earlier draft of
this document called them holidays and half-days. That was an inference: this repository has a
hand-verified NYSE table (`markets/equity_us/calendar.py`) and **nothing for CME**, and the two
genuinely differ — most visibly at Good Friday, where NYSE closes all day and CME equity-index
trades to 09:15. Under the owner's release gate (2026-09-16) no refused session is classified,
and every refusal carries the same code:

```
rejection_code = "INCOMPLETE_SESSION"
```

`SessionStatus` still distinguishes the measured SHAPES — `TRUNCATED_END` for one contiguous
run reaching the session's final minute, `HOLED` for a gap in the middle — because a census is
unreadable otherwise. Neither is a claim about cause, and both are refused.

---

## 4. Data policy

| policy | decision |
|---|---|
| price adjustment | **none.** `CONTINUOUS_UNADJUSTED`, `AdjustmentMethod.NONE`. No back-adjustment, no forward-adjustment, no splice offset, no roll-gap normalisation. An **adjusted series is refused outright** as an execution source: its levels are arithmetic, not quotes. |
| roll discontinuities | **preserved and measured.** ES gaps of +50.25 to +59.75 points (+0.73% to +0.88%) sit in the series exactly as the venue left them. |
| contract selection | **not made here.** The `contract` column was written at fetch time by a calendar rule (8 days before last trade date). This loader reads it. There is no volume crossover, no open-interest test — the store has no open interest at all — and no look at what later turned out to be liquid. |
| repair | **none.** No interpolation, no forward fill, no reindex-and-fill, no gap bridging. Asserted structurally against the module's parsed AST, so its own prose cannot satisfy the check. |
| zero volume | **counted, kept, weightless.** `TP × 0 = 0`, so the bar adds nothing to a volume-weighted average and moves neither the VWAP nor its sigma. It is never dropped, never repaired, never substituted, and **never a reason to reject a session** — no threshold exists in the frozen specification and none is invented. A session that is *entirely* zero-volume is still fed; its VWAP is NaN rather than a silent zero. |
| a session that cannot be described | **refused**, with the reason recorded. |
| an empty dataset | **refused**, never returned. |
| provenance | every load produces a deterministic manifest with a content hash and a manifest id, carrying the source file hashes and the upstream quality verdict. |
| data source | **agnostic.** `adapter` names a reader and `**adapter_kwargs` reaches it unchanged; `ibkr_futures` is the default because it is the store this repository has. A differently-shaped file loads through `generic_table` and produces bar-identical sessions — demonstrated, not asserted. |

### The rolls, measured

| when (ET) | from → to | gap | `position` |
|---|---|---|---|
| 2025-09-11 18:00 | ESU5 → ESZ5 | +57.75 (+0.876%) | `AT_THE_ANCHOR` — opens a session, contaminates none |
| 2025-12-11 16:00 | ESZ5 → ESH6 | +59.75 (+0.865%) | `BETWEEN_SESSIONS` — in the 15:46–17:59 break |
| 2026-03-12 18:00 | ESH6 → ESM6 | +50.25 (+0.752%) | `AT_THE_ANCHOR` |
| 2026-06-10 18:00 | ESM6 → ESU6 | +53.00 (+0.729%) | `AT_THE_ANCHOR` |

Three of the four land exactly ON an 18:00 anchor and the fourth lands at 16:00, in the dead
zone between 15:45 and 18:00. **No anchored session on any of the four stores contains a
contract change.** That is measured, not assumed, and it is why `MULTI_CONTRACT` has zero
occurrences on real data — the case is covered by a constructed one instead.

The 16:00 roll is also the one place the two loaders legitimately disagree: it falls *inside*
the 09:30–16:00 RTH window, so `session_source` correctly drops 2025-12-11 as mixed-contract,
and *outside* the anchored window, so the anchored session for that day is ESZ5 throughout.

---

## 5. Coverage

| | ES | NQ | MES | MNQ |
|---|---|---|---|---|
| span (ET trading days) | 2025-06-09 → 2026-09-10 | same | 2025-09-08 → 2026-09-10 | same |
| anchored sessions found | 327 | 327 | 262 | 262 |
| **COMPLETE — usable** | **313** | **311** | **252** | **252** |
| `TRUNCATED_END` | 14 | 14 | 10 | 10 |
| `NO_ANCHOR` | 0 | 2 | 0 | 0 |
| `HOLED` / `MULTI_CONTRACT` / `CORRUPT` | 0 | 0 | 0 | 0 |
| bars in usable sessions | 408,778 | 406,166 | 329,112 | 329,112 |
| of which overnight (18:00–09:29) | 291,090 | 289,230 | 234,360 | 234,360 |
| zero-volume bars (all sessions) | 1,306 | 4,100 | 2,288 | 1,818 |
| rolls | 4 | 4 | 3 | 3 |
| upstream quality | WARN | WARN | WARN | WARN |
| manifest id | `49db9cd2a5e16841` | `67bf71df1ffdfd9d` | `9a387f4a2ef971b7` | `bfe357ba6a745f92` |
| content hash | `92b9ad205458d566` | `c11d90747fc74b1d` | `40ff5226d7122b0a` | `73aeee0314a4d7c0` |

Every usable session is exactly 1,306 bars — there is no partial-session tail in the usable
set at all.

**The overnight half is 71% of every session and `session_source` discarded all of it.** That
is the single largest change this phase makes to what the strategy can see.

### The upstream WARN, fully attributed

The canonical layer WARNs on all four stores. Rather than carry that forward as an unexamined
caveat, each reason was reconciled against the anchored census:

**`unexplained_gaps`.** There are **326** places in the ES series where consecutive bars are
more than a minute apart. **312** begin at or after 15:45 — the daily maintenance break,
extended over weekends. The other **14** begin *before* 15:45, and they are exactly, one for
one, the 14 sessions the anchored loader refuses as `TRUNCATED_END`. There is no third kind.
**Not one gap falls inside a session the strategy would be fed**, and `HOLED` is empty.

**`stale_price`.** The flagged run is 645 consecutive bars with an unchanged close, starting
2025-11-27 21:44 ET — the Thanksgiving overnight. **All 645 print zero volume.** Because the
VWAP is volume-weighted, a zero-weight bar cannot move it: fed through the real accumulator,
100 such bars leave `value` and `sigma` bit-identical while `bars_in_session` advances. The
session is one of the fourteen refused anyway, but the reasoning does not depend on that.

**`mixed_contract_session`.** Four ES sessions hold two contracts *under the canonical layer's
trade-day convention*, because a roll at 18:00 lands inside a trade day. Under the anchored
convention 18:00 is the boundary, so the same roll lands between two sessions and neither is
mixed. Same file, same rolls, two correct answers — which is why the anchored loader measures
contract identity itself rather than inheriting the verdict.

### Zero-volume concentration

Among the 313 usable ES sessions, 40 contain at least one zero-volume bar, 658 bars in total.
The worst is **2025-06-10 with 273 (21% of the session), 268 of them overnight** — the first
days of the store are the thinnest. Those bars contribute no VWAP weight, so the VWAP on such
a session rests on fewer weighted observations than its bar count suggests. The count travels
per session in the manifest.

**No threshold is applied, by the owner's ruling of 2026-09-16.** The frozen specification
contains no zero-volume rule, so inventing an exclusion would be inventing a strategy rule.
The arithmetic is stated rather than hidden: VWAP is computed from the available
volume-weighted observations, a bar with `Volume = 0` contributes `TP × 0 = 0`, and no price
or volume is substituted in its place.

---

## 6. Defects found and fixed

### P1 — the trading-day roll used absolute 24-hour arithmetic (found by the DST test)

`work["_day"] = (et + pd.to_timedelta((mins >= anchor).astype(int), unit="D")).dt.date`

`pd.to_timedelta(1, "D")` adds twenty-four **absolute** hours. That is not one calendar day on
either side of a DST transition. On a spring-forward session it moved **every bar from 23:00 ET
onward into the following trading day** — splitting one anchored session into two, each with a
wrong anchor and therefore a wrong VWAP for its whole length.

Python's aware-datetime arithmetic, which `indicators.trading_day` uses, is wall-clock and does
not have this property. So the loader and the engine agreed about which day a bar belonged to
on 363 days a year and disagreed on two, silently, in opposite directions.

Fixed to calendar arithmetic on dates. The same pattern was present in
`scripts/vwap_data_readiness.py` and is fixed there too. Pinned by the mutation
`data__the_day_roll_returns_to_absolute_twenty_four_hours` and by
`test_a_session_spanning_the_spring_forward_loses_an_hour`.

### P1 — `.gitignore` hid the entire canonical data layer from every commit

Line 44 read `data/`. A gitignore pattern with a trailing slash and **no leading slash matches
a directory of that name at any depth**, so it matched `quant_brain/data/` as well as the
intended bar store. Nine source files — `adapters.py`, `schema.py`, `quality.py`,
`manifest.py`, `loader.py`, `rolls.py`, `contracts.py`, `cross_source.py`, `__init__.py` —
**have never been committed**. `git show HEAD:quant_brain/data/loader.py` fails.

Every certification from Phase 3A onward rests on those modules, and until now they existed
only in the working tree: a clean clone of this repository could not import `quant_brain.data`
at all, and nothing but the working copy stood between the layer and its loss.

Found by accident and for an uncomfortable reason: a background mutation run was killed
mid-flight, left a mutation applied to `rolls.py`, and `git checkout` could not restore the
file because git had never seen it. Fixed by anchoring the pattern to the repository root
(`/data/`), which still ignores `data/futures/*.parquet` and no longer ignores source.

**This is a repository-state finding, not a data finding. The nine files are now visible to
git and need committing; that is the owner's call, not this phase's.**

### P1 — `generic_table` was unreachable through the canonical loader

`L.load` declares a `session_timezone` parameter, so Python bound any caller's keyword of that
name to the loader and it never reached `**adapter_kwargs`. `generic_table` *requires*
`session_timezone`, so calling it through `L.load` raised `TypeError` — always. Every call site
in the repository reached past the loader and invoked the adapter directly, which is why nobody
had noticed: **the "source-agnostic" property of the canonical layer had never been exercised
end to end.**

`L.load` now forwards the value when, and only when, the adapter declares a parameter of that
name, so no existing call changes behaviour. Pinned by
`data__the_session_timezone_stops_reaching_the_adapter` and by the test that loads the same
bars from a differently-shaped file.

### P2 — the manifest id changed with how the caller typed the path

`manifest_id` hashed the whole body, and the body carries `source.files` — the path as the
CALLER spelled it. So `load_anchored("data/futures/ES.parquet", ...)` and
`load_anchored(REPO / "data/futures/ES.parquet", ...)` produced **different ids for
byte-identical input**, with the same `file_hashes` and the same upstream manifest id. A
result quoting one and a result quoting the other would read as two runs on different data.

Found by noticing that `scripts/vwap_data_certify.py` and a direct call printed different ids
for ES in the same session — the script builds an absolute path and the direct call did not.

The id now hashes everything except that path. The file's sha256 is in the hashed body and
settles identity exactly; the path stays in the emitted manifest for a human to follow.
Pinned by `data__the_manifest_id_depends_on_how_the_path_was_typed` and by
`test_the_manifest_id_does_not_depend_on_how_the_path_was_typed`.

### P2 — the completeness scan used a hard-coded epoch divisor

The first implementation compared timestamps as `int64 // 10**9`, which is seconds only if the
frame stamps nanoseconds. This store stamps **microseconds**, so every minute of every session
was reported absent and all 327 sessions were refused. Caught immediately because the result
was absurd; replaced with `DatetimeIndex` set arithmetic, which is unit-agnostic. Pinned by
`data__the_completeness_scan_uses_a_fixed_epoch_divisor`.

### P3 — a roll at the anchor was reported as contaminating the session it opens

`RollEvent` carried `inside_an_anchored_session: bool`, computed as
`minute >= anchor or minute <= flat`. Three of the four ES rolls land exactly ON 18:00, so all
three recorded `True` — and the certification printed "INSIDE A SESSION" beside each.

Every word of that is true of the bar and the impression is the opposite of the fact. A roll
at 18:00 is the FIRST bar of a new session, so that session is entirely the new contract and
nothing is mixed; the store's contaminated-session count is zero, and the report appeared to
say three. Replaced with a three-valued `position` — `AT_THE_ANCHOR` / `BETWEEN_SESSIONS` /
`INSIDE_A_SESSION` — so the manifest states which of the three it is. Pinned by
`data__a_roll_at_the_anchor_is_reported_as_polluting_the_session_it_opens` and by a
constructed roll that IS inside a session, so the third label is not vacuous.

### P3 — an unreachable guard

`expected_minutes` refused a session whose end preceded its anchor, a condition that cannot
arise because the anchor is always on the previous calendar day. Replaced with the invariant
that actually matters: a session end at or after the anchor minute would run into the *next*
session's anchor and two sessions would claim the same bars.

---

## 7. The release gate (2026-09-16)

The owner's pre-backtest gate ruled on the three questions the previous certification left
open, and froze the pipeline. Every ruling is implemented, tested and mutation-covered.

### The rulings

| # | ruling | how it is enforced |
|---|---|---|
| **No invented calendar** | a refused session is `INCOMPLETE_SESSION`, never `HOLIDAY` | `SessionQuality.rejection_code`; reason strings say the cause is *not determined*; a structural test forbids `holiday`, `is_trading_day` or `calendar.` anywhere in the module's code |
| **No zero-volume threshold** | zero-volume bars stay, weightless, counted; never a reason to reject | a session that is *entirely* zero-volume is still fed, and its VWAP is NaN rather than a silent zero |
| **The pipeline is frozen** | session, clock, completeness, roll and adjustment policy are stated in every manifest | `release/V1.0.0_Frozen.json`, rebuilt and diffed by `scripts/vwap_release.py --verify` |

### The frozen definition, as the manifest states it

```
timezone              America/New_York
vwap reset            18:00:00 ET          and nowhere else
data session          18:00:00 ET -> 15:45:00 ET, ONE continuous session
no reset at           00:00, 09:30, 09:45, 15:30, calendar date change
entry window          09:45 -> 15:30 ET    (15:30 inclusive)
hard flatten          15:45 ET
completeness          anchor present, endpoint present, every minute between present
                      exactly once, one contract, valid OHLC, non-negative volume
rejection code        INCOMPLETE_SESSION
adjustment            CONTINUOUS_UNADJUSTED / NONE
roll                  CALENDAR_DAYS_BEFORE_EXPIRY, read from the store's contract column
zero volume           kept, TP x 0 = 0, counted, never repaired, never a rejection
repair                none
```

### The release manifest

`release/V1.0.0_Frozen.json` is the single machine-readable record tying the strategy to the
bytes. Every field is DERIVED — from `spec.FROZEN`, `spec.FROZEN_MNQ` and the loaders — so the
file cannot disagree with the code; and because that arrangement would let both drift
together, `tests/test_vwap_data.py` asserts the released values against literals typed by
hand from the owner's gate. That is the one place a literal belongs.

`python scripts/vwap_release.py --verify` rebuilds every field and refuses on the first
disagreement, so a drifted parameter or a re-fetched store fails a check instead of quietly
re-releasing itself.

### Loader performance

Measured, not tuned. `python scripts/vwap_data_certify.py --perf`.

| store | rows | sessions | usable | bars | seconds | bars/sec | peak MiB |
|---|---|---|---|---|---|---|---|
| ES | 447,600 | 327 | 313 | 408,778 | 5.86 | 76,374 | 231.1 |
| NQ | 447,596 | 327 | 311 | 406,166 | 6.62 | 67,647 | 230.4 |
| MES | 358,845 | 262 | 252 | 329,112 | 4.89 | 73,359 | 185.7 |
| MNQ | 358,845 | 262 | 252 | 329,112 | 4.91 | 73,140 | 185.7 |

Time is from an untraced run; peak memory from a second, traced one, because `tracemalloc`
costs roughly 4x the runtime — timing a traced run and calling it the loader's speed would
overstate the cost by a factor no reader could see. The peak is Python-level allocation only,
so read it as a floor rather than as resident set size. Nothing was optimised: the loader runs
once per backtest.

---

## 8. Remaining limitations

1. **No verified CME calendar exists in this repository**, so the cause of every refusal is
   left undetermined. Nothing is classified as a holiday or an early close; every refused
   session carries `INCOMPLETE_SESSION` and a measured description of its shape. This limits
   what can be SAID about the refusals, not what enters the backtest — all fourteen are
   refused either way. `markets/lean_calendar.py` could read LEAN's market-hours database if
   a verified CME source is ever wanted; it is deliberately not used here, because a
   calendar in the data path is calendar knowledge in the backtest.
2. **The fall-back DST session cannot be tested on real data**, and never will be on this
   store: the transition always precedes the week's first anchor, and the store ends
   2026-09-10 anyway. It is tested on a constructed session.
3. **Zero-volume bars are concentrated in the early store and post-roll**, worst at 21% of
   2025-06-10 (268 of its 273 overnight). Under the owner's ruling of 2026-09-16 they are
   kept, weightless and counted — the frozen specification has no zero-volume rule and none
   was invented. The consequence to carry into a result: the VWAP on such a session rests on
   fewer weighted observations than its bar count implies, and the per-session counts in the
   manifest are how those sessions would be found afterwards.
4. **Sessions are refused, never repaired**, so a day with a single absent overnight minute is
   lost entirely. NQ loses two sessions this way. That is the intended trade.
5. **The equivalence check against a second implementation covers 09:30–15:45 only**, because
   that is the whole of the overlap between the two loaders. The overnight half — 71% of each
   session — is instead checked against the **raw parquet read with pandas alone**, bypassing
   the adapter, the canonical frame, the schema and the quality gate. That is a structurally
   independent path, but it is a check against the FILE, not against a second interpretation
   of it.
6. **The store is one venue and 15 months.** 313 ES sessions is what exists. Nothing about
   this phase changes the sample-size limits recorded elsewhere.
7. **Reproducibility is restored but the store itself is not in git.** The nine canonical
   source files are now tracked (§6); `data/futures/*.parquet` remains ignored by design, so
   a clone reproduces the CODE and must re-fetch or receive the bars. The release manifest
   records each file's sha256 and byte size so a received store can be checked against the
   one this certification ran on.
8. **No strategy has been run on any of this.** Nothing here says the data is profitable to
   trade; it says the data is what it claims to be.

---

## 9. Verification

```
tests        3,345 passed · 9 skipped · 14 xfailed        (118 in test_vwap_data.py)
mutation     193 applied · 0 skipped · 193 caught · 100%  (39 new this phase)
lint         clean across quant_brain/, tests/, scripts/, examples/
types        0 errors in quant_brain/strategies/, the new suite and the new script
             (quant_brain/data/loader.py carries 9 pre-existing errors at lines 77-98;
              this phase's change to it added none)
```

The 39 new mutations cover every rule this phase introduced: the anchor moved an hour in each
direction, the session end moved to 15:30 and to 16:10, the venue clock replaced by UTC, the
expected count frozen to 1,306, the minute walk stripped of its timezone conversion, the day
roll returned to absolute 24-hour arithmetic, the session split at midnight, the window cut to
RTH only, the overnight half dropped, the VWAP reset at midnight and again at the cash open,
five-minute buckets offset from the venue clock, roll gaps back-adjusted, the roll instant
shifted off the bar that changed, contract identity taken from the end of the session, absent
minutes forgiven, a duplicate timestamp forgiven, an early close fed to the strategy, the
completeness scan given a fixed epoch divisor, the quality gate disabled, every bar stamped a
minute late, one bar of the next session leaked into this one, an adjusted series accepted, an
empty dataset returned, the adapter hard-wired to IBKR, the session timezone blocked from
reaching the adapter, both manifest-identity defects, a roll at the anchor reported as polluting the session
it opens, and the release-gate policies: a refusal claiming a calendar reason, a rejection
code that stops distinguishing refused from fed, an invented zero-volume threshold,
zero-volume bars dropped from a session, a day roll adding twenty-four ABSOLUTE hours, and
three manifest fields that stop being recorded.

One mutation had to be REWRITTEN. `data__the_engine_day_roll_returns_to_datetime_arithmetic`
swapped `local.date() + timedelta(days=1)` for `(local + timedelta(days=1)).date()` and
survived - correctly, because Python's arithmetic on an aware datetime is wall-clock and the
two are identical. A mutation that changes no behaviour proves nothing about the suite. It
was replaced by the form that genuinely differs, twenty-four ABSOLUTE hours, which diverges
for bars stamped 23:00-23:59 the evening before a spring-forward - and the DST sweep, which
had started at the transition day itself and so covered none of those minutes, was extended
back a day. The rewritten mutation is caught on exactly the divergent minute.

## 10. Reproducing

```powershell
python scripts/vwap_data_certify.py                              # the census
python scripts/vwap_data_certify.py --instrument ES --rejected   # every refused session
python scripts/vwap_data_certify.py --instrument ES --manifest   # the provenance block
python scripts/vwap_data_certify.py --perf                       # loader performance
python scripts/vwap_release.py --verify                          # the release manifest
python -m pytest tests/test_vwap_data.py -q
python scripts/engine_mutation_test.py
```
