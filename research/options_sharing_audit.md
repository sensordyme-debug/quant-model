# Options branch sharing audit (Part 17)

**Date:** 2026-09-13. **Scope:** read-only. No code changed, nothing committed, no ledger row
appended. **Goal per the brief:** "Shared Quant Brain + market-specific intelligence" — identify
what the Options branch can share with the new market-agnostic machinery, what must stay
options-specific, and whether the futures work has broken anything on this track.

Everything below is measured on this working tree at commit `1d93102`. Where a claim in the
brief or in an existing document did not survive checking, the correction is stated.

Note on a moving tree: other agent tracks edited `quant_brain/research/registry.py`,
`scripts/paper_trade.py`, `scripts/sweep_s37.py` and two test files (uncommitted) while this
audit was running, and added `quant_brain/research/promotion.py`. HEAD did not move. All
measurements below are against HEAD; the one place where an in-flight edit changes a conclusion
is flagged in §2.1.

---

## 0. What was actually run

| Check | Result |
|---|---|
| `python -m pytest` (whole suite) | **1010 passed** in 55.9 s |
| `python -m pytest tests/test_store_health.py -k "chain or theta"` | **3 passed** — the only options-touching tests in the repo |
| import smoke on all 9 options modules | 9 of 9 import clean on Python 3.14 |
| `python scripts/theta_data.py --check` | `listening True serving True`; `history/quote` **HTTP 403 "you only have a FREE subscription"** |
| `python scripts/sweep_o6.py` | reproduces the journal exactly: Stage C 5 of 5, Stage D 4 of 5, Stage E 4 of 4, Stage F 5 of 5 |
| `python scripts/sweep_o5.py` | reproduces the journal exactly: 0 of 20, best cover **0.963**, zero cells above 1.0 |
| `python scripts/store_health.py --store odte` | 1 symbol, **18,248,558 rows, 0 fail, 1 warn -> usable** |
| `Ledger('research/experiments.jsonl').all()` | **0 experiments** (see §4.1) |

**The Options branch is not broken.** Every module imports, both reproducible sweeps reproduce
to the digit, the store validates, and the whole test suite is green.

---

## 1. Map of the Options branch

### 1.1 Code — 3,739 lines, entirely inside `scripts/`

| File | Lines | Role |
|---|---|---|
| `scripts/theta_data.py` | 234 | Theta Terminal HTTP client. `listening()`:64, `alive()`:82, `start_terminal()`:118, `expirations()`:142, `quotes()`:152, `implied_vol()`:166, `first_order_greeks()`:172, `eod_greeks()`:179, `open_interest()`:186, `nearest_expiration()`:196 |
| `scripts/odte_data.py` | 163 | 0DTE chain fetcher/store. `fetch_day()`:51, `load_day()`:77, `stored_dates()`:84 |
| `scripts/iv_regime.py` | 309 | Volatility-surface builder. `_slice_features()`:154 (ATM IV, 25-delta IV), `aggregate()`:184 (skew25, term ratio), `load_gate()`:230 |
| `scripts/sweep_o1.py` | 387 | O-1: IV-regime gate on the intraday sleeve. Refused |
| `scripts/sweep_o2.py` | 630 | O-2: 0DTE credit spread. **All the options pricing machinery lives here**: `Chain`:57, `spot()`:110 (put-call parity), `prob_itm()`:124 (`dP/dK`), `pick_strike()`:144, `snap_long()`:155, `Cfg`:166, `run_session()`:179 |
| `scripts/sweep_o3.py` | 430 | O-3: selection on `rn_skew` / `vrp`. Refused |
| `scripts/sweep_o4.py` | 257 | O-4: quote vs trade-print estimator. Feed disqualified |
| `scripts/sweep_o5.py` | 524 | O-5: chain direction traded in SPY. Refused |
| `scripts/sweep_o6.py` | 622 | O-6: chain magnitude vs the tape. **PASS** |
| `scripts/_o1_confirm_2024.py`, `_o2_confirm.py` | 183 | confirmation harnesses |

Plus the options-aware parts of shared files: `scripts/store_health.py:310` `check_odte_store()`
and `:391` `check_theta()`; `scripts/dashboard/sources.py:2041` `_options_fetch()` and `:3212`
the `options` API endpoint.

### 1.2 Data — 176 MB

| Path | Size | Contents |
|---|---|---|
| `data/options/odte/SPY/*.parquet` | 125 MB | **1,891 sessions, 2016-01-08 .. 2026-09-10**, 18,248,558 rows. Columns: `strike, right, timestamp, bid, ask, bid_size, ask_size` (5-minute snapshots, ±30 strikes) |
| `data/options/raw/SPY_*.parquet` | ~50 MB | 491 cached EOD-greeks expirations feeding `iv_regime` |
| `data/options/iv_regime.parquet` / `.csv` | 0.5 MB | 2,383 days 2017-01-03 .. 2026-09-09: `iv_atm_1w, iv_call25_1w, iv_put25_1w, skew25_1w, iv_atm_1m, term_ratio, dte_front, dte_back` |
| `results/options/o5_features.parquet` | 0.8 MB | O-5's frozen chain-feature cache (gitignored). O-6 reads it, does not rebuild |
| `results/options/o4_feed_grid.csv`, `results/o1/*.csv` | 0.1 MB | grids |

Note: the "176 MB store" figure quoted in `research/BLOCKERS.md` and `ARCHITECTURE.md:232` is
the whole `data/options/` tree. The **0DTE store alone is 125 MB**.

### 1.3 Ledger — 170 rows, all in `research/experiments.jsonl`

| Family | Rows |
|---|---|
| `options/odte_put_spread` (O-2) | 16 |
| `options/odte_o3_select` | 14 |
| `options/odte_o4_feed` | 60 |
| `options/odte_o5_direction` | 40 |
| `options/odte_o6_magnitude` | 40 |
| **total** | **170** (154 tagged DIAGNOSTIC, 16 not; **0 carry `env_key` / provenance**) |

### 1.4 The state of the track — verified, and the brief undercounts it

The brief said: "three edge constructions refused and one pass (O-6)". Verified against
`research/journal_options.md` and `research/backlog.md`, the actual tally is **seven items**:

| Item | Verdict | What it measured |
|---|---|---|
| O-1 | **refused** | prior-day IV regime gate on the intraday sleeve — "the payoff is the volatility *surprise*" |
| O-1b | **refused** | IV-scaled sizing on the daily champion — "a leverage dial, 50% more turnover" |
| O-2 | **refused** | SPY 0DTE credit spread at the quote. Gross +0.783% of max loss, spread −1.363%, commission −0.950%, net **−1.530% at t −3.20** |
| O-3 | **refused** | selection on the chain's own features. **0 of 4 pairs clear Stage A**; ceiling with full hindsight `cover 1.043, +0.052% at t +0.09` |
| O-4 | **feed disqualified** | quote vs trade-print. 56 of 60 cells refused on quotes; **33 of those lose decisiveness on prints, 6 turn positive**; blind term 2.72x the effect |
| O-5 | **refused** | the same chain signal traded in SPY at 3.41 bps. **0 of 20 cells**, best cover **0.963**, **zero above 1.0** |
| O-6 | **PASS** | chain magnitude (`rn_half`) vs a causal realized-vol baseline. 5 of 5 clocks incremental OOS, DM t +3.5..+4.2, sd of the sized book −4.3% to −14.3% |

So: **five refusals, one data-source disqualification, one pass** — not three and one. And the
brief's characterisation of O-6 as "a risk input rather than a tradeable edge" is exactly right,
with one thing added below that the brief could not have known.

**The blocker is real and current.** Re-probed live during this audit: `theta_data.py --check`
returns `listening True serving True` with `history/quote` at **HTTP 403 "requires a value
subscription … you only have a FREE subscription"**. The store is frozen at 2026-09-10; today is
2026-09-13, so **two sessions (09-11, 09-12) are permanently missing** unless VALUE is restored.
`store_health` does **not** flag this — `check_odte_store` computes missing days only over
`trading_days(window_start, last)`, and `last` is the freeze date, so the gap after the freeze is
invisible to the completeness check and falls to the `stale` rule, which is not tripping.

**The one thing that has changed since O-6 and is not written down anywhere.** O-6's PASS was
handed to the sizing tracks as **A-15**, and A-15 has since been run and **refused it**
(`cc14f9e`, `research/journal.md:7-104`): *"conditioning size on any predictor of realized
volatility is refused on the mechanism, not on the sample … O-6's finding should not be
re-proposed as a sizing input for the A-track."* A-15 is explicit that this does **not**
contradict O-6's own forecasting claim, which it reproduces. But the practical consequence is
that **the only named downstream consumer of the only positive result this track has produced
has closed the door**, and `research/BLOCKERS.md:57-72` still cites that consumer as the second,
cheaper justification for buying VALUE. That justification has lapsed and nobody has said so.

### 1.5 Two shipped-but-disabled hooks

The options data is not purely research. Two strategy files read it:

- `algorithms/intraday/orb/signal.py:72` — `iv_gate` param, default `""` (off), reads
  `iv_regime.load_gate` at `:97`.
- `algorithms/s1_momo/signals.py:381` — `iv_scale_power`, default `0.0` (off), reads
  `iv_regime_series` at `:472`.

Neither is set in `live/intraday_config.json` or `research/champion.json`, so **no live position
depends on options data today**. But the code paths ship, and `_iv_pass` "fails closed" (no
store -> no trades), so a store deletion would silently change ORB behaviour if the gate were
ever switched on.

---

## 2. What the Options branch could adopt TODAY, and what each costs

### 2.1 `quant_brain/research/registry.py` — the experiment ledger

**Verdict: usable as-is on the API; needs one named decision about which file it writes to.**

The module is completely market-agnostic. `Ledger.verdict()` (`registry.py:290`) takes a series
and a horizon and reads the trial count off disk via `Ledger.trials()` (`:244`). Nothing in it
knows what a future is.

**What adoption would buy, measured.** The options track currently sets its own Bonferroni bar
per item, by hand and per item only: O-5 used `|t| > 3.02` for its own 20 cells, O-6 used
`|t| > 2.576` for its own 5 clocks. Neither counts the other. At the **170 options rows already
on disk**, `stats.bonferroni_threshold(170) = 3.62`. Measured consequences:

- O-6 Stage B survives comfortably (NW t +8.09 .. +9.55 against 3.62).
- O-6 Stage C's Diebold-Mariano t values are **+3.84 / +3.54 / +4.24 / +3.52 / +3.97**. If the
  family bar were applied to those, **11:00 and 13:00 would fall below 3.62**. Stage C's
  pre-registered rule is RMSE-plus-two-of-three, not a t threshold, so this does not overturn
  the verdict — but it is the size of the correction the track is currently not paying.

**The cost, and it is the whole cost.** `Ledger` reads and writes the `Experiment` schema
(`hypothesis`, `family`, `params`, `metrics`, `stage`, `verdict`). The options track writes a
LEAN-shaped row (`ts`, `algorithm`, `class`, `tag`, `track`, `params`, `stats`) with a plain
`open("a")` — `sweep_o2.py:512`, `sweep_o5.py:403`, `sweep_o6.py:504`. The two schemas do not
mix, and this was measured, not assumed:

- **`Ledger('research/experiments.jsonl').all()` returns 0 experiments.** All 1,206 rows are
  skipped by the `KeyError` guard in `registry.py:229-239`. `trials('options/odte_o6_magnitude')`
  returns **0**. Pointing a `Ledger` at the existing file today gives a *vacuous* correction —
  the worst possible outcome, because it looks rigorous and counts nothing.
- Going the other way is worse. I appended one real `Experiment` row to a scratch copy of
  `experiments.jsonl` and ran the existing consumers against it:
  - `scripts/evaluate.py:348` raises **`KeyError: 'ts'`** — the promotion gate stops working.
  - `scripts/dashboard/sources.py:1054` `_augment_row` does **not** crash but silently mislabels
    the row `algorithm=None, track="daily"`, inflating the dashboard's daily count.
- **Concurrency.** At HEAD (`1d93102`), `Ledger.record()` (`registry.py:263-283`) implements its
  atomic append as read-whole-file + write-temp + `os.replace`. That is correct against another
  `Ledger`, and it **destroys** a concurrent `open("a")` append from a sweep. Today the two never
  meet because futures writes to a separate file (`futures_discover.py:46`,
  `futures_topstep_baseline.py:60` both use `research/experiments_futures.jsonl`, 137 rows). If
  options adopts the registry into the shared file while any sweep still appends the legacy way,
  this becomes a live data-loss path.
  **Live caveat, noticed during this audit:** another track is concurrently rewriting exactly
  this method in the working tree (uncommitted, `registry.py` +116 lines, plus a new
  `quant_brain/research/promotion.py`). The in-progress version replaces read-modify-write with
  a plain `open("a")` append under a cross-process `O_CREAT|O_EXCL` lock file. That removes the
  clobber **between two `Ledger` writers**, but its own docstring records that Python emulates
  `O_APPEND` on Windows as seek-then-write, so a legacy sweep that appends *without* taking the
  lock still races. The conclusion for options is unchanged and slightly strengthened: a sweep
  that adopts the registry must adopt `Ledger.record()`, not keep its own `open("a")`.

**And the mirror-image cost of the separate-file route.** `quant_brain/core/knowledge.py:200`
loads **only** `research/experiments.jsonl`. Measured: the index holds 1,206 experiment entries
and 148 backlog entries, and `search("0DTE variance risk premium options chain")` returns O-3's
backlog item and four O-6 ledger rows. **The 137 futures rows are invisible to `already_tried()`
today.** If options moves to `experiments_options.jsonl` it inherits that blindness.

**Recommended shape, since the brief asks for cost not opinion:** a separate
`research/experiments_options.jsonl` for registry rows (matching what futures did), plus a
one-line addition to `knowledge.py:200` to glob `experiments*.jsonl`. That is roughly 1 line in
`knowledge.py` + ~15 lines per sweep to build an `Experiment`. Anything that writes registry rows
into `experiments.jsonl` must first fix `evaluate.py:348`.

**One honest limitation.** The registry removes the `n_trials` *argument*, but the `family`
string is still author-chosen, and family granularity is the same soft number wearing a
different hat. Five families is `bonferroni_threshold(40) = 3.23`; one family is 3.62. Nothing
in `registry.py` or `test_qb_research.py` constrains that choice.

### 2.2 `quant_brain/research/search.py` — the bounded funnel

**Verdict: usable with one named change, and it is a small one.**

The four gates (`search.py:172-206`) are statistics, cost, **Topstep survival**, walk-forward.
Gate 3 reads `result.get("topstep_ok", True)`, so a caller that does not supply the key passes
it by default — the module is not futures-specific in mechanism, only in the gate's *name*. The
honest change is renaming gate 3 to something market-neutral (`survival_ok` / `barrier_ok`) and
letting `futures_cme` supply the Topstep meaning; the options analogue is a real one (an
assignment/pin-risk barrier), so the slot earns its place.

`Limits.min_sessions = 100` (`search.py:64`) and `max_experiments = 200` fit this store
comfortably — 1,891 sessions, and O-4's grid was 60 cells.

**The reason to want it here specifically.** O-2 ran 60 cells, O-4 re-ran the same 60 two ways,
O-5 ran 20 and O-6 ran 25 in Stage A. None of them recorded a funnel. `Funnel.table()`
(`search.py:87`) is precisely the artefact this track keeps writing by hand in prose.

**Cost:** the gate rename (1 module + its tests), plus an `evaluate(hypothesis) -> dict` shim per
sweep. It cannot be adopted before §2.1, because `search()` takes a `Ledger`.

### 2.3 `quant_brain/core/validation.py` — purged walk-forward and write-once holdout

**Verdict: usable as-is, zero changes. This is the single highest-value adoption on the list.**

The module takes `n`, `horizon`, and numpy arrays (`purged_walk_forward`:91, `Holdout`:282,
`make_holdout`:379). There is not one futures assumption in 455 lines.

**Two separate things, and they are worth very different amounts here:**

1. **The purge is nearly a no-op for the track as it stands.** O-6's own expanding-window OOS
   (`sweep_o6.py:337-347`) fits on `X[:i]` and predicts row `i`. Its label is intraday — measured
   from the clock to the 15:50 open of the *same* session — so with one row per session the
   horizon is 1 and the purge removes 0 rows. `purged_walk_forward` would confirm the existing
   result rather than change it. It would start earning its keep the moment this track touches a
   multi-session label (weekly expiries, SPXW term structure), which is exactly what a restored
   VALUE tier buys.

2. **The write-once holdout is a real, currently-missing control.** O-3, O-5 and O-6 all report
   their headline "chosen with full hindsight" over the whole 1,891-session store, and O-6 layers
   three post-hoc stages (D's rescaling, E, F) on the same sample it passed on. That is stated
   honestly in the journal every time — but honesty is not a mechanism.
   `Holdout.spend()` (`validation.py:342`) refuses a second look unless `force=True` and records
   the count. Nothing in the options track has that today.

**Cost:** zero to the shared module. Per sweep: ~10 lines to carve the holdout and a ledger path.
The awkward part is political, not technical — the existing three items have already spent their
holdout, so this applies to O-7 onward.

### 2.4 `quant_brain/core/execution.py` + `quant_brain/brokers/ibkr.py`

**Verdict: single-leg options are reachable today; multi-leg is genuinely not, and there is one
concrete latent defect. This is the most futures/equity-shaped layer of the five.**

What works today with no change:

- `AssetClass.OPTION` already exists (`instruments.py:38`).
- `IBKRAdapter.submit` (`ibkr.py:56`) looks up `self.contracts.get(intent.symbol)` — an arbitrary
  string key. A caller can hand it `{"SPY 260910P00650000": Option(...)}` and route a single leg
  through `RoutedExecutor` -> `RiskChain` -> IBKR with zero edits.

What does not work, in order of severity:

1. **`IBKRAdapter.working()` is wrong for options.** Line `ibkr.py:78` reads
   `sym = tr.contract.symbol`. Verified against the installed `ib_async` 2.1.0:
   `Option('SPY','20260910',650,'P','SMART').symbol == 'SPY'` while `Stock('NVDA').symbol ==
   'NVDA'`. So the submit key and the working key are the same string for equities and futures
   and **diverge for options**: every SPY option leg collapses into one `"SPY"` bucket, and a
   long call plus a short put net against each other. `working()` exists specifically to prevent
   AUD-06 double-sizing; on options it would reintroduce it. This is a latent defect, not a
   live one — nothing routes options today — but it is in shared code and it should be named.
2. **No multi-leg / combo intent.** `OrderIntent` (`execution.py:65`) is one symbol, one side,
   one quantity. O-2's whole construction is a two-leg vertical, and O-2's refusal turns
   *entirely* on the spread crossed on each leg (−1.363% of max loss against +0.783% gross).
   Submitting two independent intents is legging risk, which is a different and worse trade than
   the one O-2 priced. An IBKR `BAG` contract with `comboLegs` has no representation in this
   layer.
3. **No option identity in `InstrumentSpec`.** `instruments.py:44` carries
   `symbol/asset_class/multiplier/tick/currency/exchange`. There is no strike, expiry, right, or
   exercise style, and `instruments.py:16` says so on purpose: *"options greeks and exercise
   style"* belong in `markets/`. That is the right call, and it means an options branch owes a
   `markets/options_us/instruments.py`.
4. **`OrderType`** — `MARKET_ON_CLOSE` / `MARKET_ON_OPEN` (`execution.py:52-58`) are genuinely
   venue-independent and fine. Options need nothing added here, though a real options runner
   would want a mid-peg / relative type that does not exist yet.

**Cost to make single-leg options routable and correct:** ~5 lines in `ibkr.py:72-83` to key
`working()` off `localSymbol or symbol`, plus a test. **Cost for spreads:** a new multi-leg
intent type and a combo path in the adapter — that is a design change to the shared boundary,
not an adoption, and it should not be attempted before the track has a reason to place an
options order.

### 2.5 `quant_brain/markets/futures_cme/dataquality.py` — as a template

**Verdict: the *template* is exactly right; the *checks* are futures-specific and none transfer.**

The file's own docstring (`dataquality.py:1-27`) is the pattern to copy: the core
(`core/dataquality.py`) handles zero/NaN/negative prices, impossible bars, duplicate indices,
tz-naive timestamps and holiday bars; the market module adds only the hazards that come from the
instrument's own structure. Severity-graded, not all-fatal (`Severity` at
`core/dataquality.py:34`), with `require_usable()` at the write boundary.

None of the six futures checks apply: roll gap, contract overlap, backwards roll, within-contract
jump, stale bars, crossed book — the last is the only one an options chain shares, and
`sweep_o2.Chain` already enforces it inline at `sweep_o2.py:88` (`ca >= cb`).

**What an options validator would check instead, and none of it exists anywhere in the repo:**

| Hazard | Why it is options-only | Currently checked? |
|---|---|---|
| Strike-grid completeness / holes | a missing strike silently moves `np.interp`'s bracketing neighbours — O-5 measured this: relaxing O-3's mask changed 3 of 8,777 cells, worst 0.501 | no |
| Both-rights coverage per timestamp | parity spot needs both rights quotable | inline only, `sweep_o2.py:87` |
| Put-call parity deviation | O-5's Gate 0 measured median 0.23 bps / p99 2.19 bps against the tape — a data check dressed as a research gate | inline in `sweep_o5.py:277` `integrity()` |
| No-arbitrage monotonicity of `dP/dK` | `prob_itm` (`sweep_o2.py:124`) clips to [0,1] and moves on; a non-monotone chain is a data error, not a market | no |
| Wing degeneracy | O-5 found `rn_tail` **28% exactly zero overall, 42% by 14:00** — silently degenerate, discovered mid-study | no |
| Selection bias in quotability | O-3's mask drops **calm** sessions preferentially: mean \|move\| **13.3 bps where it drops out vs 38.7 bps where it survives**. A completeness check that reports only a count would miss this entirely | no |
| Expiry / DTE consistency | file date vs the expiration it claims | no |
| Truncated session | last quote well before the close | **yes** — `store_health.py:353-364` |
| Missing session | trading day with no chain file | **yes** — `store_health.py:372-379` (but blind to days after the freeze, §1.4) |

**Cost:** a new `quant_brain/markets/options_us/dataquality.py` of roughly the same size as the
futures one (256 lines), reusing `Report`/`Severity`/`Finding` unchanged, plus lifting the three
checks that currently live inline in `sweep_o2.py` and `sweep_o5.py`. The selection-bias check is
the one worth building first, because it is the only one on this list that has already changed a
result.

---

## 3. What must stay options-specific

| Concern | Exists in this repo? | Where |
|---|---|---|
| **Chain container / dense [time, strike] grids** | **yes** | `sweep_o2.py:57` `Chain` — 88 lines, in a sweep script |
| **Risk-neutral prob-ITM from `dP/dK`** | **yes** | `sweep_o2.py:124` `prob_itm()` |
| **Put-call-parity spot** | **yes** | `sweep_o2.py:110` `spot()` |
| **Strike selection** | **yes** | `sweep_o2.py:144` `pick_strike()` (prob-ITM targeting), `:155` `snap_long()` (width snapping) |
| **Volatility surface** | **yes, partial** | `iv_regime.py:154` ATM IV + 25-delta IV by strike/delta interpolation; `:184` skew25 and 1w/1m term ratio. **Two points on two tenors, not a surface** — no smile fit, no interpolation in tenor, no forward variance |
| **Greeks** | **feed-level only** | `theta_data.py:172` `first_order_greeks()`, `:179` `eod_greeks()`, `:166` `implied_vol()`. **No greek is computed in this repo**; `iv_regime.py:68` consumes vendor `delta` and `implied_vol`. There is no pricer, no solver, no delta/gamma/vega/theta of a position, and no portfolio greek aggregation |
| **Expiration handling** | **thin** | `theta_data.py:142` `expirations()`, `:196` `nearest_expiration()`, `odte_data.py:44` `expiration_dates()`. **0DTE only** — no term structure, no roll, no exercise style, no early-assignment model, no cash-vs-physical settlement distinction (which is exactly what O-2's fatal exit assumption and the unanswered SPXW question turn on) |
| **Options execution model** | **backtest only** | `sweep_o2.py:179` `run_session()` — sell at bid, buy at ask, reverse on exit, `$0.75`/contract/transaction, plus an `expire_otm` branch and a `pin_buffer` (`:262-265`). No live options order path anywhere |
| **Options risk** | **rudimentary** | `sweep_o2.py:221` `risk = max_w * 100 - credit * 100` (defined-risk max loss), `record(risk_frac=0.25)` at `:484`. **No `RiskEngine` implementation for options**, no margin model, no assignment risk, no pin risk beyond the backtest's `pin_buffer`, no greek limits |
| **Options data validation** | **no** | see §2.5 |
| **Options instrument spec** | **no** | `AssetClass.OPTION` is declared (`instruments.py:38`) and `scheduler.py:79` budgets an options market at 900 MB/worker, but `quant_brain/markets/options_us/` **does not exist** |

**The structural finding.** Every piece of genuine options intelligence this repository owns —
the chain container, the parity spot, the risk-neutral density, strike selection, the round-trip
cost model — lives inside `scripts/sweep_o2.py`, a 630-line research script that
`ARCHITECTURE.md:121` classifies as *"Parked, store retained"* and `ruff.toml`/`pyrightconfig.json`
exclude from enforcement. It is imported by `sweep_o3`, `sweep_o4`, `sweep_o5` and `_o2_confirm`,
which is four dependents on an unenforced, untested file.

**Measured:** of 1,010 tests in the suite, **3** touch anything options-shaped, and all three are
in `tests/test_store_health.py` (two on chain-store completeness, one on Theta probe safety).
There is **zero** test coverage of `Chain`, `spot`, `prob_itm`, `pick_strike`, `snap_long`,
`run_session`, `iv_regime._slice_features`, or `odte_data.fetch_day`. By contrast the futures
branch shipped with `test_qb_futures_dq.py` (234 lines), `test_qb_execution_sim.py` (345),
`test_qb_paths.py` (405), `test_qb_topstep.py` (706) and `test_qb_twin.py` (456).

That asymmetry is the real answer to "what must stay options-specific": nothing on the list above
is wrong, but almost none of it is protected, and `sweep_o2.py` is the single point of failure for
five of the seven O-items.

---

## 4. Where the futures work has broken or degraded the Options branch

`git diff --stat 9fce240..HEAD` (O-6's commit to HEAD) covers 50 files. **Not one options file is
among them.** No `sweep_o*.py`, no `odte_data.py`, no `theta_data.py`, no `iv_regime.py`, no
`store_health.py`, no `intraday_common.py`. The only shared artefact touched is
`research/experiments.jsonl` (+193 rows, all legacy-schema, appended by `ml_f14`, `sweep_a14`,
`sweep_a15`, `sweep_s38`, `verify_c5`).

**No functional breakage.** Confirmed by the reproductions in §0: O-5 and O-6 both reproduce to
the digit, the whole suite is green, and the one shared module any options file imports
(`odte_data.py:97` -> `quant_brain.core.scheduler.resolve_workers`, wrapped in a bare
`except Exception` fallback at `:100`) is unchanged and unbroken.

The specific vectors the brief asked about are clean:

- `OrderType.MARKET_ON_CLOSE` / `MARKET_ON_OPEN` are additive enum members
  (`execution.py:52-58`); nothing in the options track constructs an `OrderIntent`.
- The `paper_trade.py` adapter migration is invisible to options — the track has no runner and
  no live path.
- The AST guard in `tests/test_qb_adapter.py:359` walks **`quant_brain/` only**, not `scripts/`,
  so it cannot bite an options script. (Aside: `BLOCKERS.md`'s Resolved entry claims the test
  walks "every module outside `quant_brain/brokers/`". It does not — 12 files under `scripts/`
  still import `ib_async` directly, e.g. `paper_trade.py:584`. Not an options issue, but the
  claim is broader than the test.)

**Three real degradations, all documentary, all caused by the new work:**

### 4.1 The Options blocker vanished from the file that now presents itself as the blocker list

`BLOCKERS.md` at the repo root was **created** by `1d93102` (the futures docs commit). It opens
with *"Things that cannot be resolved from the repository … Everything here needs the owner"*,
is stamped *"Last reviewed: 2026-09-13"*, and lists OWNER-1 through OWNER-4 — three futures items
and one alerting item.

**Measured: `grep -ciE "theta|option|value|0dte" BLOCKERS.md` returns 0.** The Theta VALUE-tier
ask — the single thing blocking the entire Options track, worth 68 lines of endpoint-by-endpoint
evidence — is **not in it**.

It is still in `research/BLOCKERS.md:5-94`, which `AGENTS.md:44` and `:67` name as the canonical
location and which `scripts/dashboard/sources.py:1416` reads. So no agent and no dashboard has
lost sight of it. But a human opening the repo root now finds a short, current-looking,
authoritative-sounding blocker list with the options ask absent, sitting beside a 90 KB
`research/BLOCKERS.md` that the new file supersedes by name and date. That is the degradation:
the Options track's only open request is now one directory further from the person who has to
act on it, and the file that looks like the answer says nothing about it.

### 4.2 `ARCHITECTURE.md`'s options entries are stale by three items

- `ARCHITECTURE.md:230-232`: *"Options are parked on a measurement… O-3 found the 0DTE variance
  risk premium is not conditional (best of twelve terciles with hindsight: cover 1.043, +0.052%
  at t 0.09) and the Theta subscription has lapsed to FREE. The 176 MB store is retained."*
  Written after O-3, and stops there. O-4 (feed disqualified, 60 cells), O-5 (0 of 20, cover
  0.963) and O-6 (**the track's only PASS**) are all absent.
- `ARCHITECTURE.md:30-34`, the branch diagram: `OPTIONS_US … PARKED … O-3 measured the edge at
  zero`. Same vintage.
- `ARCHITECTURE.md:121`: `scripts/odte_data.py, sweep_o*.py | OPTIONS | Parked, store retained.`

`ARCHITECTURE.md:171` does say *"`quant_brain/research/` is market-agnostic and is what the
Options branch will share when it restarts"* — the intent is on the record, which is good. The
factual summary beside it is three items behind.

### 4.3 The options blocker's second justification has lapsed and the file still asserts it

Covered in §1.4. `research/BLOCKERS.md:57-72` argues for VALUE partly on the grounds that O-6's
`rn_half` is a live risk input that "cannot be computed for any session after 2026-09-10", with
the caveat that the sleeve question "is filed as **A-15** … and is not proven". A-15 ran the same
day (`cc14f9e`) and **refused the whole class** on mechanism. The blocker text has not been
updated. This is a futures-era commit changing the standing of an options ask without the options
document noticing — the cross-track handoff worked, the write-back did not.

---

## 5. Bottom line

**Is the Options branch in worse shape than described?** Functionally, no — it is in better shape
than "blocked" implies. It reproduces, it validates, it is green, and it has produced a genuine
statistical result (O-6, 5 of 5 clocks out of sample, DM t +3.5 to +4.2). Structurally, yes, and
in two ways the brief did not name:

1. **Its only positive result now has no consumer.** A-15 refused the O-6 handoff on mechanism,
   which means the second and cheaper argument for buying VALUE has quietly evaporated. What
   remains is the original SPXW question, which is real but is the expensive one.
2. **Its intelligence is unprotected.** 3,739 lines, 3 tests, 0 of them on the pricing path, and
   the load-bearing 630-line file (`sweep_o2.py`) is imported by four other items while being
   excluded from both ruff-strict and pyright.

**The adoption order that follows from the costs measured above**, when the track restarts:

1. `core/validation.py` — free, zero changes, and the write-once holdout is the control this
   track most visibly lacks. Do this first.
2. Extract `sweep_o2.Chain` / `spot` / `prob_itm` / `pick_strike` into
   `quant_brain/markets/options_us/`, with the tests that four dependents have been doing without.
3. `markets/options_us/dataquality.py` on the futures template, starting with the
   quotability-selection check (the one hazard that has already moved a number).
4. `research/registry.py` into a **separate** `experiments_options.jsonl`, plus the one-line
   `knowledge.py:200` glob fix so neither non-equity branch goes missing from `already_tried()`.
   Do not write registry rows into `experiments.jsonl` until `evaluate.py:348` tolerates them.
5. `research/search.py` after the registry, with gate 3 renamed off "Topstep".
6. `core/execution.py` last, and only if an options order is ever going to be placed. Fix
   `ibkr.py:78` (`localSymbol or symbol`) whether or not that happens — it is a latent AUD-06
   in shared code.

**Documentary fixes that are owed regardless and cost minutes:** put the Theta VALUE ask into the
root `BLOCKERS.md`; refresh `ARCHITECTURE.md:121`, `:230-232` and the `:30` diagram through O-6;
and record A-15's refusal against the O-6 justification in `research/BLOCKERS.md`.
