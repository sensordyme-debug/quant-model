# LEAN migration and engine audit

QuantConnect LEAN is now the sole authoritative backtesting engine in this repository. This
document records what was audited, what was frozen, what LEAN can actually serve, and what
remains blocked.

**No strategy was backtested in this task. No profitability result, payout probability or
optimisation appears below.**

---

## A. Environment

```
LEAN_ROOT             C:\Users\ashur\Quant-Model\Lean
LEAN_REMOTE           https://github.com/QuantConnect/Lean.git   (official)
LEAN_GIT_COMMIT       23b735d99a357807dc0df9f4c51d30f05fe0d277
LEAN_VERSION          18056  (git describe)
LEAN_HEAD_SUBJECT     "Add the published 2027 CME holiday dates and hours (#9733)"
LAUNCHER              Lean/Launcher/bin/Release/QuantConnect.Lean.Launcher.exe
LAUNCHER_SHA256_16    6cf8d2c19a3068b6      (162,816 bytes, built 2026-09-08T15:45:04Z)
LEAN_CLI_VERSION      lean.exe 1.0.229
DOTNET_VERSION        10.0.400
PYTHON (LEAN)         3.11  (pythonnet host)
PYTHON (tooling)      3.14.7
OS                    Windows-11-10.0.26200-SP0
DOCKER_VERSION        NOT INSTALLED
EXECUTION_PATH        native compiled launcher (no Docker)
```

### The one deviation from the documented LEAN workflow, stated up front

The brief specifies the official LEAN CLI / Docker workflow (`lean backtest`, `LEAN_DOCKER_IMAGE`).
**Docker is not available on this machine** — `docker` is not on PATH, and the repository's
standing constraint records that no virtualisation (WSL2/Docker) can be installed here. The
LEAN CLI is installed (1.0.229) but its `backtest`, `optimize` and `research` commands all
run the engine inside Docker and are therefore unusable.

This repository instead drives the **compiled LEAN launcher directly**, natively on Windows,
through `scripts/backtest.py`. That is the same engine — same commit, same binary, same fill
models, same statistics — run without the container. It is not a reimplementation and not a
workaround around LEAN.

Consequences, so nobody has to rediscover them:

- `LEAN_DOCKER_IMAGE` has no value to record; the launcher hash pins the engine instead, and
  is strictly more specific (it identifies the binary that actually ran, not the image that
  could have).
- `lean data download`, `lean cloud` and `lean research` remain available in principle, since
  they call the QC API rather than Docker — but see §C, they need an account.

## B. Engine inventory (PART 1)

| engine / component | location | purpose | active? | used by | disposition |
|---|---|---|---|---|---|
| **QuantConnect LEAN** | `../Lean` (git, built) | market simulation, fills, portfolio, statistics | **YES** | all future backtests | **KEEP — sole engine** |
| LEAN native runner | `scripts/backtest.py` | runs the launcher, records the run | **YES** | all backtests | KEEP |
| `topstep-backtest` 0.4.0 | site-packages (pip) | prop-firm bar engine | no | (was) Layer B | **FROZEN** |
| `topstep_backtester/` | repo | integration layer over the above | no | CVD, probe | **FROZEN** — see `ARCHIVED.md` |
| `quant_brain/data/` | repo | canonical schema, adapters, quality gate, manifests | yes | data prep | KEEP (data layer, not an engine) |
| `quant_brain/research/*ledger*` | repo | ledger builders, reference arithmetic | yes | verification only | KEEP as **cross-check only** (PART 28) |
| `quant_brain/markets/futures_cme/` | repo | Topstep rulebook, twin, instruments | yes | reporting layer | KEEP (rules, not simulation) |
| `quant_brain/core/lean_engine.py` | repo | **new** — LEAN provenance | **YES** | every run | KEEP |
| `scripts/futures_discover.py` | repo | futures session discovery | dormant | prior research | FREEZE from active path |
| `scripts/sweep_*.py` (~40) | repo | one-shot historical experiments | archive | prior research | KEEP as archive, not runnable path |
| `scripts/backtest_initial_balance.py`, `intraday_backtest.py`, `vwap_analyze.py`, `strategy_lab_topstep.py`, `failed_reversal_replication.py` | repo | prior custom simulators / MC | archive | prior research | FREEZE from active path |
| `quant_brain/brokers/ibkr.py` | repo | IBKR order adapter (`placeOrder`) | **see §G** | paper sleeve | **UNCHANGED — out of scope** |
| `quant_brain/brokers/projectx.py` | repo | ProjectX adapter | no | none | KEEP — structurally cannot submit |
| `quant_brain/brokers/projectx_readonly.py` | repo | read-only ProjectX client | no | none | KEEP — closed allow-list |

Nothing was deleted. Historical research is preserved in full.

## C. Data source and acquisition

LEAN resolves ES futures correctly — security master, contract filter, mapping and market
hours all work (proved in §D). What it does **not** have locally is tick data.

```
Lean/Data/future/cme/
    universes/es/     37 security-master dates
    minute/es/        16 dates  x {trade, quote, openinterest}
    hour/es_*.zip     trade, quote, openinterest
    daily/es_*.zip    trade, quote, openinterest
    map_files/es.csv
    (no tick/ directory, no second/ directory)
```

That is LEAN's bundled **sample** dataset: 2013-10-06 → 2013-12-20 plus 2020-01-05/06.

### Acquisition path

| option | status |
|---|---|
| local bundled data | present, sample only, **no ticks** |
| `lean data download` (QC Datasets) | available, but it is a **purchase** flow requiring a QuantConnect account, API credentials and payment |
| QuantConnect cloud backtest | requires an account |
| `lean login` / credentials | **not configured** — `~/.lean` absent; `Launcher/config.json` has empty `api-access-token` and `job-organization-id` |

Acquiring ES tick data therefore requires the owner's QuantConnect account and a dataset
purchase. That is a spending decision and is not something this task performs.

`DATASET_MANIFEST` for the data currently in use:

```
DATASET_PROVIDER   QuantConnect (LEAN bundled sample data)
DATASET_VERSION    as shipped with LEAN commit 23b735d9
DATA_RANGE         2013-10-06 .. 2013-12-20, plus 2020-01-05..06
CONTRACTS          ES (continuous, front month via OpenInterest mapping) -> ESZ13, ESH14, ESM14
RESOLUTION         minute, hour, daily
TICK_TYPE          trade, quote, openinterest   (NO tick resolution)
DOWNLOAD_DATE      bundled with the LEAN checkout
```

Large or purchased datasets are not committed to git.

## D. Data coverage — measured, not assumed

Two LEAN algorithms were run to answer this from the engine rather than from documentation.
Neither places orders.

### `algorithms/f2_es_tick_probe` — Resolution.TICK

```
PROBE slices=1 total_ticks=0
PROBE trade_ticks=0 quote_ticks=0 openinterest_ticks=0 other=0
PROBE fields price=0 qty=0 bid=0 ask=0 bid_size=0 ask_size=0 exchange=0
PROBE causality trades_with_prior_quote=0 trades_without_prior_quote=0
PROBE CVD_RECONSTRUCTABLE=NO
PROBE MISSING=['trade ticks', 'quote ticks', 'bid', 'ask', 'trade quantity']
```

LEAN's own data-request log: **15 succeeded, 741 failed**, all
`future/cme/universes/es/<date>.csv`.

### `algorithms/f3_es_minute_probe` — Resolution.MINUTE (positive control)

Identical code, one line changed. Its only job is to rule out "the probe is broken":

```
PROBE slices=3600 total_ticks=0
PROBE trade_bars=10800 quote_bars=10800
PROBE MINUTE_CONTROL bars_seen=21600
```

**This is the load-bearing comparison.** The same probe that reported zero at tick resolution
reported 21,600 bars at minute resolution. The subscription, the contract filter, the security
master, the mapping and the market-hours handling are all working. The tick result is
therefore a fact about the data, not about the probe.

### Verdict

| requirement | available? |
|---|---|
| timestamp | yes (minute bars) |
| trade price | **only as a minute OHLC bar**, not per trade |
| trade quantity | only as minute bar volume |
| bid / ask | present at minute resolution, **one pair per minute** |
| bid size / ask size | not delivered |
| exchange | not delivered |
| per-trade sequence | **no** |
| trade/quote causal alignment | **untestable** — zero trade ticks, zero quote ticks |

## E–F. Strategy and execution model

Not applicable to this task. Per PART 32 the CVD strategy was **not** migrated into an active
LEAN project, and per the HARD STOP no strategy was backtested. `ACTIVE_STRATEGIES = 0`.

LEAN's execution model will be documented from the engine — not invented — when a strategy is
actually run, in the same way §D documented the data from the engine.

## G. Order transmission and live trading

Verified for the new LEAN path:

- no LEAN live environment is configured or invoked; `scripts/backtest.py` runs backtest mode only
- no QuantConnect credentials exist, so no cloud live deployment is reachable
- `topstep_backtester` remains research-only, and its layering audit still reports
  0 upstream-import violations, 0 broker-SDK imports, 0 transmission tokens
- ProjectX adapters remain structurally incapable of placing an order (closed allow-list)

**One pre-existing item the owner should be aware of, which I did not touch.**
`quant_brain/brokers/ibkr.py:76` calls `ib.placeOrder(...)`, `ib_async 2.1.0` is installed, and
`live/APPROVED_PAPER.md` — dated 2026-09-09, signed by the account owner — authorises
`scripts/paper_trade.py` to send orders to IBKR **paper** account DUT091359 at a scheduled
15:45 ET weekday rebalance.

That is an existing, owner-approved, paper-only sleeve for the equities champion. It is
unrelated to this migration and to futures. I left it exactly as it was: the brief says not to
modify live credentials or create a live deployment, and deleting `APPROVED_PAPER.md` would
freeze the owner's book — a destructive change that is the owner's call, not mine. Flagging it
here so the "live trading impossible" claim is precise rather than sweeping: **nothing in the
LEAN backtesting path can transmit an order; a separate, previously approved paper path
exists and is untouched.**

## H. Reproducibility

Every run now records the engine that produced it. `scripts/backtest.py` gained a
`lean_engine` block sourced from `quant_brain/core/lean_engine.py`:

```json
{"lean_commit": "23b735d99a357807dc0df9f4c51d30f05fe0d277",
 "lean_describe": "18056",
 "launcher_sha256_16": "6cf8d2c19a3068b6",
 "dotnet_version": "10.0.400",
 "docker_available": false,
 "lean_cli_version": "lean.exe 1.0.229",
 "execution_path": "native compiled launcher (no Docker)",
 "pinned": true}
```

The launcher hash is the field that matters: the commit says what was checked out, the hash
says what was actually **compiled and executed**, and those diverge the moment someone edits
the tree without rebuilding.

Two identical runs of `f3_es_minute_probe` were compared:

```
stats identical:            True
engine provenance identical: True
probe counters identical:    True  (11 log lines)
```

## I. What remains blocked

**CVD_ABSORPTION_HARVESTER XFA V2.0 is still BLOCKED, now for two independent reasons:**

1. **LEAN DATA INSUFFICIENT FOR EXACT CVD.** No ES trade ticks and no ES quote ticks are
   available to this installation. The tick test cannot be applied to bars, and CVD may not be
   approximated from OHLCV, candle volume, bid/ask bar volume, minute volume, VWAP, price
   changes or synthetic ticks.
2. **Eleven specification ambiguities remain unresolved** (A1–A7, A9–A11, A16), recorded in
   `topstep_backtester/strategies/cvd_absorption_harvester/spec.py`. These are engine-independent
   — migrating to LEAN does not resolve a single one — and they need owner rulings.

Migrating engines changed the first blocker's *shape*, not its existence: LEAN can serve tick
data, this installation has not got any.

## J. Limitations

1. **Docker unavailable**, so the documented `lean backtest` CLI path cannot be used. The
   compiled launcher is driven directly instead — same engine, different invocation.
2. **No QuantConnect account configured**, so cloud data, cloud backtests and dataset purchase
   are all out of reach without owner action.
3. **Bundled sample data only** — 16 ES dates. Any study on it would be about the sample, not
   the market. PART 24's "deepest available ES dataset" is not reachable until §C is resolved.
4. **Execution model not yet documented from the engine**, because no strategy has been run.
5. **Timezone/DST not yet exercised on futures sessions** beyond LEAN's own handling; the
   probe set `TimeZones.NEW_YORK` but the sample window contains no DST transition.
6. **~40 archived sweep scripts and several prior simulators remain in the tree.** They are
   frozen from the active path by convention and inventory, not by a mechanical guard — only
   `topstep_backtester` has an enforced gate.
7. The IBKR paper sleeve in §G is untouched and remains capable of transmitting paper orders.

## K. Reproducibility manifest

```
repo commit           b769001 (working tree dirty at time of writing)
LEAN commit           23b735d99a357807dc0df9f4c51d30f05fe0d277
LEAN describe         18056
launcher sha256/16    6cf8d2c19a3068b6
dotnet                10.0.400
python (tooling)      3.14.7
python (LEAN host)    3.11
OS                    Windows-11-10.0.26200-SP0
docker                not installed
lean CLI              1.0.229
data dir              Lean/Data  (bundled sample)
probes                algorithms/f2_es_tick_probe, algorithms/f3_es_minute_probe
runs recorded         research/experiments.jsonl
test suite            212 Layer B tests passing; repo suite green
```
