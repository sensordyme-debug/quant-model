# Full system forensic audit

> **Requested as an "IVT strategy" audit. There is no strategy, algorithm, module, document,
> experiment record or result artifact named IVT anywhere in this repository or in its git
> history.** Sections 7, 9, 12–15 and 19 of the requested structure are therefore reported as
> **NOT APPLICABLE — SUBJECT NOT FOUND**, not as PASS and not as FAIL. Everything else — the
> system, the backtest infrastructure, the research record and prop-firm readiness — was
> audited in full and is reported below.

Audit date 2026-09-18. Repo `C:\Users\ashur\Quant-Model\quant-model` @ `b769001` (tree dirty).
Read-only: nothing was deployed, no order was placed, no credential or account state touched.

---

## 1. Executive summary

**The system cannot currently transmit an order, and that is the only reason it is safe.**
Order transmission is blocked by two Python literals (`ORDER_TRANSMISSION_ENABLED = False` at
`scripts/intraday_trader.py:56` and `scripts/paper_trade.py:84`) plus an AND-gate in
`quant_brain/core/config.py:436`. Every *other* defence the documentation describes —
approval binding, the authority ladder, the idempotency journal, the promotion gate, bracket
protection, compare-and-halt reconciliation — is **built, tested, documented and not connected
to the order path**.

Three findings dominate:

1. **The deployed artifact is not the approved artifact, and nothing can detect that.**
   `live/APPROVED_PAPER.md` names commit `35ce0a9`; `research/champion.json` carries commit
   `d41aefe`, promoted 2026-09-11 — two days *after* the 2026-09-09 approval. The approval file
   is untracked by git and its contents are never read: both call sites test `.exists()` only
   (`paper_trade.py:828`, `intraday_trader.py:820`). **P0.**

2. **The research significance gate is sign-blind.** `quant_brain/research/registry.py:334`
   computes `passed = bool(abs(value) > threshold)`. Of 65 recorded "survivors" across 6,369
   futures experiments, **45 have negative t-statistics**, with effect sizes down to
   −$66/trade. They are recorded with the reason string *"survives N-trial correction"*, which
   reads as endorsement. **P1 (research validity).**

3. **Every LEAN backtest in this repository charges zero slippage and zero financing** unless
   explicitly overridden — verified in LEAN source, not inferred:
   `Lean/Common/Brokerages/DefaultBrokerageModel.cs:283` returns `NullSlippageModel`
   (`NullSlippageModel.cs:33-35` → `return 0`) and `:370` returns `MarginInterestRateModel.Null`.

**What is genuinely good, stated plainly because it is not window dressing:** the contract
mathematics is correct against CME across five independent tables; `quant_brain/brokers/
projectx.py:386` has *no live branch to reach* rather than a gated one; `tests/conftest.py:227-251`
fingerprints live-state mtimes around every test and caught a real leak; and
`tests/test_production_reachability.py` pins the repo's own unwired safety components as
**strict xfails**, which is why several findings below could be verified in minutes. That file
is the most honest artifact in the repository.

---

## 2. Architecture map

Exact owner of each stage on the **deployed** path (equities; there is no deployed futures path).

| Stage | File:line |
|---|---|
| DATA | `scripts/intraday_trader.py:470` `IBFeed`, `:494` `YahooFeed`, `:520 make_feed()`; stored bars via `scripts/intraday_common.py` |
| FEATURES | `algorithms/intraday/base.py:17 features(df)` — **shared** by live, replay and backtest |
| STRATEGY→SIGNAL | `intraday_trader.py:70 load_strategy()` `exec_module`s `algorithms/intraday/<name>/signal.py`; `:729 strategy.decide(...)` |
| RISK | `quant_brain/core/risk.py:71 RiskEngine`, `:93 RiskChain`; armed at `intraday_trader.py:576 _arm_governor()`. **`paper_trade.py:717,867` construct `RiskChain()` empty** |
| SIZING | inline at `intraday_trader.py:661 targets_to_orders()` / `paper_trade.py:455 plan_orders()`. **`quant_brain/core/sizing.py` (905 lines, 8 sizers) has no production caller** |
| ORDER INTENT | `quant_brain/core/execution.py:67 OrderIntent` |
| EXECUTION | `execution.py:259 RoutedExecutor.submit():308` — journal → risk → adapter |
| BROKER | `quant_brain/brokers/ibkr.py:76 self.ib.placeOrder(...)` — **the only such call in the repo** |
| FILL | `intraday_trader.py:420 LiveExecutor.settle()` — reads `tr.fills`, distrusts `orderStatus.status` (IBKR code 10349 incident) |
| POSITION | `intraday_trader.py:118 Book` / `:240 book_fill()` → `live/state/intraday_book.json` |
| RECONCILIATION | `intraday_trader.py:147 reconcile_book()`. **`paper_trade.py` reconciles nothing** |
| ACCOUNT/RISK STATE | `governor.py:361 Governor.publish()` → `StateStore(StateScope.PAPER)` |

**Reachability, re-measured with the repo's own algorithm:** 96 `quant_brain` modules — 18
production-reachable, 54 research-only, **24 unreachable from any non-test importer** (including
`core.protection`, `core.reconcile`, `core.portfolio`, `research.promotion`, both ProjectX
brokers, all of `venues/`).

**Competing implementations — the single biggest structural problem:**
- **≥7 ledger/P&L builders** (`intraday_trader.Book`, `core/execution.Position`,
  `research/canonical_ledger.py` "the one source of truth", `research/ledger_builder.py`,
  `research/reference_ledger.py`, `research/bracket_reference.py`,
  `topstep_backtester/reporting/ledger.py`) — four are deliberate adversarial references, the
  rest are duplication.
- **≥8 session-boundary definitions** (`intraday_common.py:45-46`,
  `markets/equity_us/calendar.py:89-90`, `markets/lean_calendar.py`, `core/calendar.py:94`,
  `futures_discover.py:65-67` mutable globals, `research/robustness.py:107-152`,
  `futures_cme/topstep.py:214`, free-text `session_window` on specs).
- **≥6 backtest engines** (LEAN via `scripts/backtest.py`; `scripts/intraday_backtest.py` a
  parallel reimplementation; `scripts/run_strategy.py`; `topstep_backtester/run.py`;
  `vwap_pullback/engine.py`; `initial_balance_reversion/engine.py`).
- **A 332-file unversioned parallel system.** `Quant Brain/QuantModel/src/catalyst/` contains
  four more backtest engines (`lean.py`, `lean_docker.py`, `native.py`, `nautilus.py`) and four
  broker adapters, one with a functional Alpaca order path (`brokers/alpaca.py:193`). It is
  **gitignored** (`.gitignore:72`), last modified 2026-08-27, not imported by the main repo and
  not pip-installed — dead, but unversioned and order-capable. **P2.**

*Correction to my own prior report:* the LEAN migration audit stated "ACTIVE CUSTOM BACKTEST
ENGINES: 0". That claim was made without examining `Quant Brain/`. The engines there are not
*active* (nothing imports them), so the conclusion survives — but it was asserted without the
evidence to support it.

---

## 3. System engineering audit — findings by severity

### P0

| # | Finding | Evidence |
|---|---|---|
| 1 | **Approval is `.exists()` only.** No commit, hash, strategy name, date or signature is read | `paper_trade.py:828`; `intraday_trader.py:820`; `grep APPROVAL` shows 3 sites, none reading contents |
| 2 | **Champion already drifted past approval** — approved `35ce0a9`/OrderListHash `5246804e…` (2026-09-09), deployed `d41aefe` (promoted 2026-09-11). Approval file **untracked by git** | `live/APPROVED_PAPER.md:6-7` vs `research/champion.json` |
| 3 | **Autonomous promote→deploy.** `scripts/evaluate.py --promote <ts>` writes `champion.json` with no confirmation; the scheduled runner reads it at run time | `evaluate.py:382-399`; `paper_trade.py:735`; `install_paper_task.ps1` |
| 4 | **No idempotency in production.** All three `RoutedExecutor` sites omit `journal=`; no `intent_id` is minted, so attaching one would refuse every order | `intraday_trader.py:352`; `paper_trade.py:717,867`; demonstrated live by `tests/test_execution_integration.py:281-294` |

### P1

| # | Finding | Evidence |
|---|---|---|
| 5 | Daily sleeve runs an **empty `RiskChain()`** — no engines, nothing enforced | `paper_trade.py:717,867`; `risk.py:96-107` |
| 6 | `Authority.for_live` three-key ladder has **zero production callers**; `live/approvals/` does not exist | `mode.py:125-155`; grep |
| 7 | **`live/HALT` fails open** — absence means go; any stat error reads as absent; paper runner checks once per run | `paper_trade.py:673`; `intraday_trader.py:706` |
| 8 | Disconnect → 10 retries → `break` → flatten attempted **on a dead socket**; positions left open | `intraday_trader.py:917-928, 954-958` |
| 9 | `paper_trade.py` performs **no reconciliation** on restart | pinned `tests/test_production_reachability.py:229-231` |
| 10 | **Every open position is UNPROTECTED all session** — neither runner places a protective order | pinned `tests/test_production_reachability.py:226-228` (strict xfail, repo's own words) |
| 11 | No futures execution cost model exists. `projectx.py` has **zero** commission/fee references; `venues/registry.py:96 fee_per_unit=0.0` default, never wired to `CONTRACTS` | grep count 0; `registry.py:96` |

### P2 (selected)

- `--flatten` reaches the venue **155 lines before** the approval check (`paper_trade.py:673` vs `:828`).
- `intraday_trader --dry-run --flatten` ignores `--dry-run` (`:865-866`, `:878-880`) where the stale-book path does check it (`:891-892`).
- Order-path guard scans only **3 hardcoded files** (`test_no_order_can_be_transmitted.py:49-50`); a fourth order path is invisible to every guard.
- No runtime network guard in the test suite.
- Four research scripts open IB sockets **without `readonly=True`** (`fetch_minute.py:258`, `intraday_data.py:391`, `futures_data.py:110,208,342`, `futures_fetch_multi.py:348`).
- `file_lock` force-breaks after 10 s under contention (`locking.py:46-53`) — correct for a research ledger, wrong for an order journal.
- Two slippage ladders share rung names with incompatible meanings: "BASELINE" = 0.5 round-turn ticks (`research/execution_modes.py:104`) vs 1 stop-tick/0 market-tick (`topstep_backtester/profiles/execution.py:128`).

---

## 4–5. Backtest engine and LEAN audit

**Engine:** QuantConnect LEAN, official remote, commit `23b735d99a357807dc0df9f4c51d30f05fe0d277`,
`git describe` 18056, launcher sha256/16 `6cf8d2c19a3068b6`, dotnet 10.0.400, LEAN CLI 1.0.229.
**Docker is not installed**, so `lean backtest` is unusable; the repo drives the compiled launcher
natively — same engine, no container. Engine identity is now recorded in every run
(`quant_brain/core/lean_engine.py`, wired at `scripts/backtest.py`).

**Fidelity findings, verified in LEAN source:**

| Model | LEAN default | Consequence |
|---|---|---|
| Slippage | `DefaultBrokerageModel.cs:283` → `NullSlippageModel` → `return 0` (`NullSlippageModel.cs:33-35`) | **zero slippage in every backtest** unless overridden |
| Margin interest | `DefaultBrokerageModel.cs:370` → `MarginInterestRateModel.Null` | **zero financing cost on leverage** |

The repository already knows both, and its champion record documents the repricing honestly
(`research/champion.json` notes S-17, S-21, S-22). Measured effect on the champion:
CAR 24.403% at 0 spread → 23.068% at 2 bp; financing still uncharged.

**Reproducibility: PASS.** Two identical runs of `f3_es_minute_probe` produced identical stats,
identical engine provenance and identical probe counters.

---

## 6. Data audit

| Store | Reality |
|---|---|
| Repo futures store | `data/futures/ES.parquet` 447,600 rows, **minimum inter-record gap 60 s, zero simultaneous prints**, 2025-06-08→2026-09-10, 5 contracts |
| Repo futures quotes | `ES_quotes.parquet` — one bid/ask **per minute**, not per trade |
| LEAN bundled futures | `Lean/Data/future/cme/` — **16 ES dates** (2013 + 2020), minute/hour/daily only; **no `tick/` or `second/` directory** |
| QuantConnect account | **not configured** — `~/.lean` absent, `api-access-token` empty |

Measured from the engine, not assumed: an ES probe at `Resolution.TICK` returned **0 ticks**;
the identical probe at `Resolution.MINUTE` returned **10,800 trade bars + 10,800 quote bars**
across 3,600 slices. The probe works; the tick data does not exist.
(`algorithms/f2_es_tick_probe`, `algorithms/f3_es_minute_probe`.)

**Any strategy requiring order flow, CVD, delta, bid/ask-per-trade or intrabar event
chronology cannot be validated on this machine today.** The repo's own tournament recorded
the same limit: the microstructure family was *not run* because "bar stores carry no bid/ask"
(`research/tournament_2026_09_14_final.json`).

---

## 7. IVT strategy reconstruction — **NOT APPLICABLE, SUBJECT NOT FOUND**

Exhaustive search: content search across both repos excluding `data/`/`.git`; filename search;
`git log --all -i --grep` and `git log --all --name-only` across all three branches; all
experiment ledgers. **Zero hits.**

The complete real inventory is:

- **`research/strategy_registry.json`** — 33 tournament strategies across 7 families
  (`trend.*`, `breakout.*`, `revert.*`, `session.*`, `vol.*`, `volume.*`, `added.*`).
- **`research/experiments.jsonl`** — 1,657 LEAN runs, 63 distinct algorithms.
- **`research/experiments_futures.jsonl`** — 6,369 records, 23 families.
- **`research/hypotheses.jsonl`** — 117 records with parent lineage.
- **`research/champion.json`** — one champion, `s1_momo`, promoted 2026-09-11.
- Stateful strategy packages: `vwap_pullback`, `initial_balance_reversion`,
  `cvd_absorption_harvester`.

Nearest-name candidates and why none is IVT: `vol.expansion_trend` (scored REJECT);
`intraday/vwap_trend`; `initial_balance_reversion` (abbreviated **IB** throughout, never IVT);
implied-volatility work exists only as experiment `O-1`, verdict *refused*.

**Please tell me which strategy you meant.** If "IVT" is a working name from outside the repo,
the specification needs to be supplied before it can be audited.

---

## 8. Leakage audit

Cannot be performed on IVT. What exists for the system generally:

- **Leakage canaries exist** as a pytest marker (`pytest.ini:12-14`): *"red-team lookahead/leakage
  canaries; each one executes a real production entry point with a planted cheat. an XPASS here
  means a guard landed."* This is the right design — the test fails when the guard is absent.
- `quant_brain/core/validation.py` (the leakage guard) is reachable **only** via
  `scripts/futures_discover.py::build_features` — asserted at
  `tests/test_production_reachability.py:173-182`. **It is not on the live path.**
- Prior audited work did find and fix real leakage of exactly the kinds listed in the brief:
  window-overlap inflation, denominator look-ahead, and a control not matched on time-of-day.
  Those fixes are in `scripts/mechanism_screen.py`; the fix was **not applied systemically**
  (see §10).

---

## 9–11. Statistical audit, genealogy, OOS

### Scale of search

**8,026 recorded experiments** — 1,657 LEAN + 6,369 futures — in **17 active days**
(2026-09-08 → 2026-09-18), peaking at **481 runs in one day**. 63 distinct backtest windows.
The largest single family, `futures.directional_efficiency.v1.search`, is **4,788 runs**.

### The good news: correction is applied

`quant_brain/research/registry.py:317 verdict()` sizes the threshold from trials **already in
the ledger** and takes no `n_trials` parameter — a deliberate design that cannot be gamed by
under-declaring. Observed thresholds: |t| ≥ 4.40 for the 4,788-run family, 3.4–3.7 elsewhere.
6,303 of 6,369 futures experiments were **rejected**.

### The bad news: three defects

**(a) The gate is sign-blind — P1.** `registry.py:334`:

```python
passed = bool(abs(value) > threshold) and math.isfinite(value)
```

45 of the 65 "survivors" have **negative** t (−3.44 to −7.67) with metrics to −$66/trade. Every
ES/MES/MNQ threshold-grid survivor is negative. Downstream consumers branch on `verdict.passed`
with no sign check (`research/search.py:217`, `scripts/futures_topstep_baseline.py:165`). A
two-sided test is defensible for *detecting an effect*; the defect is that nothing distinguishes
"reliably profitable" from "reliably unprofitable", while the vocabulary — `passed`, *"survives
N-trial correction"* — reads as endorsement. This is the same defect class previously fixed in
`mechanism_screen.py`; it recurs here in a different code path.

**(b) The correction family grows as records are appended — P2.** `registry.py:331` uses
`n = prior + 1`. Survivors were judged at trials = 65, 66, … 134 inside a family that eventually
held 136. The docstring states this sequential design openly, so it is a known trade-off rather
than an accident — but early results in a family are under-corrected relative to the final size.

**(c) The same hypothesis space was searched twice under two family names — P2.**
`futures.es.threshold_grid` (136) and `futures.es.threshold_grid.v2` (136) are corrected
*separately*, halving the effective correction over the combined search.

### OOS: there is none, and the repo says so

`docs/BACKTESTING.md:200-201`: **"There is no holdout.** All 326 sessions feed all five gates.
`Stage.VALIDATION` means 'eligible for the holdout'; no holdout has ever been carved and
`Holdout.spend()` has never run." And `:597`: *"A holdout of any kind, on any track."*

The ledger corroborates: the apparent OOS window 2020-01-02→2026-09-04 was run **189 times**;
`daily/s38_selection` alone ran its train window 47× and its "OOS" window 50×. A window
inspected 189 times is not a holdout.

The machinery to do it properly exists and is unused: `quant_brain/research/promotion.py:336
spend_holdout()` implements a write-once, candidate-stamped holdout read back from an on-disk
ledger. It has **no caller**.

**Genealogy verdict: C — heavily selected.** Not by dishonesty: the correction machinery is
real and rejects aggressively. But with 8,026 trials, no holdout, a sign-blind pass flag and a
promotion path that applies none of it, the final selection cannot be treated as out-of-sample.

---

## 12. Cost / slippage analysis — **cannot be run for IVT**

For the system generally: LEAN charges zero slippage and zero financing by default (§4). The
only cost ladder actually executed on the champion is 0 bp vs 2 bp spread (CAR 24.403% → 23.068%).
The six-scenario ladder the brief asks for is not reproducible without a strategy to run it on.

**Cost constants are inconsistent across the repo** — contract *mathematics* is correct
everywhere, but:

| Symbol | repo table | upstream pip | frozen specs | scripts |
|---|---|---|---|---|
| ES | $3.78 | $3.80 | **$4.14** | $3.78 |
| NQ | $3.78 | $3.80 | **$4.50** (vwap spec) | $3.78 |
| MES/MNQ | $1.22 | **$1.24** | — | $1.22 |
| MGC | $1.00 | **$2.74** | — | — |

The ES divergence is documented and test-pinned; the **micro divergence is invisible** — the
string `1.24` appears nowhere in the repo — and MGC is understated 2.7×, every micro error in
the flattering direction. **P1.**

Verified correct and worth stating: tick size, tick value and multiplier for ES/MES/NQ/MNQ (and
8 more roots) match CME across **five independent tables**; the P&L identity is implemented four
times and agrees every time; `topstep_backtester/reference/arithmetic.py:176-180` demands exact
Decimal equality with no tolerance.

---

## 13–15. Prop-firm simulation, sizing, Monte Carlo — **cannot be run for IVT**

The prop-firm rule layer itself is **the strongest research component in the repo**:
`quant_brain/markets/futures_cme/propfirm.py` models `TrailingMode` NONE/EOD/INTRADAY,
`FAILED_TRAILING` / `FAILED_CONSISTENCY` outcomes, `trailing_locks_at`, contract caps and flat
deadlines. `tests/test_qb_propfirm.py` carries 39 genuinely behavioural adversarial tests —
a trailing floor that fails an account still in profit (`:186`), the lock saving the path the
unlocked profile kills (`:198`), intraday trailing killing a path EOD survives (`:206`).

`quant_brain/markets/futures_cme/topstep.py` registers the live rule conflict rather than
resolving it silently: owner asserts 50% consistency, "every Topstep page reachable on
2026-09-13 says 55%" (`:252-256`).

**Monte Carlo trust: UNKNOWN for any IVT claim (no subject); MEDIUM for the prop-firm kernel**
— the rule kernel is validated against known synthetic paths, but no end-to-end path
reconstruction was exercised in this audit.

---

## 16. ProjectX execution audit

**The best-designed component in the repository.** `quant_brain/brokers/projectx.py:375-386`
routes every submission into a dry-run recorder and raises `NotPermitted` — **there is no live
branch to reach**. Absence of code, not a flag.

`projectx_readonly.py:50-107` enforces a closed allow-list of 11 read endpoints plus a redundant
fragment blacklist, both firing before any socket; `/api/Order/place` is absent from both.

Both modules are **unreachable from any non-test importer**. There is no futures execution path
at all — which is consistent, since there is no futures strategy cleared to trade.

---

## 17. Test-suite audit

3,695 passed / 9 skipped / 13 xfailed; 2,994 test functions across 113 files. **The headline
number averages two very different populations, and that is the finding.** Roughly 90% of the
work defends a backtest engine that is not connected to the thing that would place an order.

**Genuinely strong — this is not window dressing:**
- **Zero `unittest.mock` in 113 files.** Instead `tests/fakes/broker.py` (395 lines) is a
  hand-built adversarial venue keeping its *own* position book, with separate
  `fills`/`delivered`/`dropped` ledgers so a dropped fill is expressible, subclassing the real
  `ExecutionAdapter` so `RoutedExecutor` runs unmodified.
- `tests/conftest.py:151-251` — autouse isolation that fingerprints real `live/state` and
  `live/log` mtimes around **every** test. It exists because the suite was measured rewriting
  the real `live/state/governor.json`.
- `tests/test_leakage_redteam.py` (1,343 lines, 31 tests) — plants real cheats into real
  production entry points and measures what they earn against a theoretical ceiling (a
  one-bar-ahead oracle captures 100.00% of it), **with clean controls at `:1302`/`:1318`** so
  the suite cannot be satisfied by an engine that refuses everything. Best file in the repo.
- `tests/test_golden_futures.py` — 12 hand-designed synthetic datasets, literal expected values,
  and an explicit warning at `:110-112` against deriving expectations the way the code does.

**Verified weaknesses:**

| # | Finding | Evidence |
|---|---|---|
| a | **The "225/225, 100%" mutation score covers no order-path code.** Grep of `scripts/_mutation_specs.py` for `core/risk`, `core/execution`, `core/governor`, `brokers/ibkr`, `intraday_trader`, `paper_trade` returns **0, 0, 0, 0, 0, 0**. It says nothing about whether an order can be duplicated, mis-sized or lost | verified by grep |
| b | **The mutation harness docstring is false.** `scripts/engine_mutation_test.py:18-19` states "Nothing is written to the source tree"; `:84` is `f.write_text(original.replace(find, replace, 1))`. There is a `finally` restore at `:94`, but a kill mid-run leaves the tree mutated | verified |
| c | **No git hooks are installed at all** — `.git/hooks/` contains only `.sample` files — despite `tests/conftest.py:218` referring to "the pre-commit hook". Nothing re-runs the mutation suite: no CI, no hook, no scheduled job | verified |
| d | The 100% is a **groomed** number: `_mutation_specs.py:962-967` documents a mutation rewritten because it correctly survived, and `:237-241` documents an anchor that went stale and silently SKIPped | file text |
| e | **`tests/test_no_order_can_be_transmitted.py` — the file with the strongest title — is `str.count()` over raw source** (`:329-335`). A comment mentioning the constant three times satisfies it | file text |
| f | **`test_certification.py:68-70` derives its `golden` expectations from the production instruments table.** If MNQ's multiplier were wrong, all 8 golden tests still pass — the exact anti-pattern `test_golden_futures.py:110-112` warns against | file text |
| g | **Zero tests** for reconnect (`intraday_trader.py:917-928`), `startup_reconcile` (`:226-237`), the `live()` loop's feed-error/stale-data/per-step exception swallows (`:930-952`), or `paper_trade.main()` (~315 lines) | grep: `reconnect` → 0 test files |
| h | **The 09:25 preflight gate runs 282 of 2,994 tests** (`conftest.py:84-115`) and is **fail-open**: pytest exit code 5 ("nothing collected") maps to *trade* (`test_launch_preflight.py:83-90`) | file text |
| i | **Machine-state-dependent green.** Module-level `skipif(not <artifact>.exists())` in ≥4 files; `data/` is gitignored, so several hundred tests evaporate into skips on a clean clone and the suite still reports pass | `.gitignore:47` |
| j | `topstep_backtester/tests/` (212 tests) has **no `conftest.py`** — no `isolate_live`, no live-state fingerprint. Self-contained in practice, unprotected structurally | verified absent |
| k | The conftest fingerprint covers only `live/state` and `live/log` (`:229-233`); **`live/APPROVED_PAPER.md`, `live/secrets.env` and `live/intraday_config.json` sit at the top level and are not fingerprinted** | file text |
| l | No replay tests. `replay_book` (`intraday_trader.py:773`) has zero test references; 10 days of `live/log/*.jsonl` are never used as a corpus | grep |

**TEST CONFIDENCE: research/backtest engine MEDIUM-HIGH; live trading path LOW.**

## 18. AI autonomy audit

**An agent can autonomously go research → backtest → promote → configure. It cannot trade.**

The chain is fully automated: `AGENTS.md:78-80` defines six concurrent agent tracks;
`scripts/backtest.py` records runs; **`scripts/evaluate.py:382-399` writes `champion.json` with
no human confirmation**; `paper_trade.py:735` reads it at run time; the Windows scheduled task
invokes the runner with no arguments.

Promotion criteria are `must_beat = ["Sharpe Ratio", "Compounding Annual Return"]`
(`evaluate.py:321`) — **no significance test, no multiplicity correction, no OOS requirement,
no approval reference anywhere in the file.** The rigorous `PromotionGate` is unwired.

Human approval is **not cryptographically or version-bound**. It is one untracked file whose
contents are never read. The instruction protecting it (`AGENTS.md:140` "never touch
`live/APPROVED_PAPER.md`") is prompt-level, not a filesystem permission.

**Scheduled tasks verified on this machine:** `Quant Intraday Sleeve` **Ready**,
`Quant Paper Rebalance` **Ready**, `Quant Dashboard` **Running**, both OpenClaw tasks Disabled.
The trading tasks run daily and cannot transmit.

---

## 19. IVT scorecard — **NOT SCORED, SUBJECT NOT FOUND**

Scoring a strategy that does not exist would be the single worst thing this report could do.
No dimension is scored. This is **UNKNOWN**, not zero and not failure.

## 20. Prop-firm readiness scorecard (system, not IVT)

| Dimension | Score | Basis |
|---|---:|---|
| Contract mathematics | **92** | correct across 5 tables; P&L identity agrees 4 ways |
| Prop-firm rule modelling | **85** | strong kernel, 39 adversarial tests, conflict registered |
| Backtest engine identity | **80** | LEAN pinned to commit + launcher hash, reproducible |
| Data quality (equities) | **70** | canonical layer, quality gate, manifests |
| Research hygiene (correction applied) | **60** | real Bonferroni; undermined by sign-blindness |
| Test suite | **55** | strong isolation, honest ratchets, gaps unguarded |
| Execution safety *today* | **50** | safe, but by two literals |
| Cost-model consistency | **40** | 4 ES figures, invisible micro split, MGC 2.7× low |
| Data quality (futures order flow) | **15** | no ticks anywhere |
| OOS discipline | **10** | no holdout has ever been carved |
| Approval integrity | **5** | `.exists()`; already drifted |
| Idempotency in production | **0** | not wired; duplicate demonstrated by test |
| Position protection | **0** | every open position unprotected all session |

---

## 21. Critical blockers

1. Approval not bound to an artifact, **and already stale** (P0)
2. No idempotency on the order path (P0)
3. Autonomous promotion into the deployed slot (P0)
4. Unprotected positions all session (P1)
5. Empty risk chain on the daily sleeve (P1)
6. HALT fails open; disconnect leaves positions open (P1)
7. No holdout on any track (P1, research)
8. Sign-blind significance gate (P1, research)
9. No futures order-flow data (P1, blocks the futures thesis entirely)

---

## 22. Evidence table

| Area | Finding | Evidence | Severity | Status |
|---|---|---|---|---|
| Architecture | ≥7 ledgers, ≥8 session definitions, ≥6 engines; 24 unreachable modules | §2 | P2 | VERIFIED |
| Architecture | 332-file unversioned parallel system, order-capable | `.gitignore:72`; `catalyst/brokers/alpaca.py:193` | P2 | VERIFIED |
| Data | Futures store min gap 60 s, zero simultaneous prints | `data/futures/ES.parquet` | P1 | VERIFIED |
| Data | LEAN has no ES tick data; probe 0 ticks vs 21,600 minute bars | `algorithms/f2_es_tick_probe`, `f3_es_minute_probe` | P1 | VERIFIED |
| LEAN | Zero slippage, zero financing by default | `DefaultBrokerageModel.cs:283,370` | P1 | VERIFIED |
| LEAN | Engine pinned; two runs bit-identical | `core/lean_engine.py` | — | PASS |
| IVT | Does not exist | exhaustive search incl. git history | — | NOT FOUND |
| Leakage | Guard not on the live path | `test_production_reachability.py:173-182` | P2 | VERIFIED |
| Statistics | Sign-blind gate; 45/65 survivors negative | `registry.py:334` | P1 | VERIFIED |
| Statistics | Growing correction family; duplicate search families | `registry.py:331` | P2 | VERIFIED |
| OOS | No holdout has ever been carved | `docs/BACKTESTING.md:200-201,597` | P1 | VERIFIED (self-reported) |
| Costs | 4 ES figures; micro split undocumented; MGC 2.7× low | §12 | P1 | VERIFIED |
| Slippage | Two ladders share rung names | `execution_modes.py:104` vs `profiles/execution.py:128` | P2 | VERIFIED |
| Risk | Daily sleeve empty RiskChain | `paper_trade.py:717,867` | P1 | VERIFIED |
| Prop rules | Strong kernel; 50%/55% conflict registered | `propfirm.py`, `topstep.py:252` | — | PASS |
| ProjectX | No live branch exists | `projectx.py:386` | — | PASS |
| Reconciliation | paper_trade reconciles nothing; reconcile.py unwired | `test_production_reachability.py:229-231` | P1 | VERIFIED |
| Testing | 0 mutations on any order-path module; harness docstring false; no git hooks installed | §17 a-c | P1 | VERIFIED |
| Testing | Preflight gate fail-open on 'nothing collected'; 282/2,994 tests | `test_launch_preflight.py:83-90` | P1 | VERIFIED |
| Testing | Zero tests for reconnect, restart recovery, live-loop error handling | §17 g | P1 | VERIFIED |
| AI autonomy | promote→deploy autonomous; approval unbound | `evaluate.py:382-399` | P0 | VERIFIED |
| Practice | Blocked by P0 1–4 | §21 | P0 | BLOCKED |
| Combine | No futures strategy, no data, no holdout | §6, §9 | P0 | BLOCKED |

---

## 23–24. Final decisions and remediation

See the summary delivered alongside this report. Remediation is **specified, not implemented** —
no defect found in this audit was silently fixed.

### P0 — before any market execution
1. **Bind approval to an artifact.** Read `APPROVED_PAPER.md`, parse commit + OrderListHash +
   strategy, compare against `champion.json` and the current tree at run time; refuse on
   mismatch. Track the file in git. *Validate:* a test that promotes a new champion and asserts
   the runner refuses. *Accept:* drift is impossible to ignore.
2. **Wire the idempotency journal.** Mint `intent_id` in both runners; pass `journal=` at all
   three `RoutedExecutor` sites. *Validate:* flip `tests/test_execution_integration.py:309-318`
   from strict-xfail to pass. *Accept:* double `submit()` puts one order on the wire.
3. **Gate promotion behind a human.** Require a signed/typed confirmation or move promotion
   behind `PromotionGate`. *Accept:* `--promote` alone cannot change what the scheduled task trades.

### P1 — before Practice
4. Wire `core/protection.py`; refuse to hold an unbracketed position.
5. Give `paper_trade.py` a real `RiskChain` and a reconciliation step.
6. Make HALT fail **closed**; treat stat errors as halt; re-check during the fill wait.
7. On terminal disconnect, alert loudly and persist an explicit "positions open, unmanaged" state.
8. Reconcile the four ES/NQ commission figures and the micro split against a real blotter.

### P2 — before Combine
9. Add a sign requirement (or a separate `profitable` flag) to `registry.verdict`.
10. Carve a real holdout via `promotion.spend_holdout`; treat everything to date as in-sample.
11. Acquire genuine ES trade+quote tick data, or drop every order-flow thesis.
12. Collapse the duplicate ledgers/session definitions, or declare one authoritative and mark
    the rest references.

### P3 — before scale
13. Version or delete `Quant Brain/QuantModel/`.
14. Add a network guard to the test suite; widen the order-path scan beyond 3 files.
15. Apply `topstep_backtester/safety.py`'s posture-as-constants pattern to `scripts/`.
