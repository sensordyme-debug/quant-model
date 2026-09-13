# Quant Brain architecture

How this repository is organised, what belongs where, and what is deliberately not built yet.
`AGENTS.md` is the operating manual; this is the map. Read both.

Status 2026-09-12: the shared core exists and is enforced by a gate. The market branches are
one live (equity_us, two sleeves on IBKR paper) and one under construction (futures_cme).
Everything else in the target diagram is an interface, not an implementation, and that is on
purpose.

---

## 1. The shape

```text
                              QUANT BRAIN
                                   |
                          quant_brain/core/            market-agnostic only
                                   |
     +----------+----------+-------+-------+----------+----------+
     |          |          |               |          |          |
 instruments  calendar   costs*         execution   risk      state
   sizing*   provenance  knowledge      resources
                                   |
                          MARKET INTERFACE
              (SessionCalendar / CostModel / Sizer / InstrumentSpec)
                                   |
   +-------------------+-----------+------------+---------------------+
   |                   |                        |                     |
 EQUITY_US          FUTURES_CME              OPTIONS_US            (etf, btc,
 LIVE               IN PROGRESS              PARKED                 crypto:
   |                   |                        |                   interface
 calendar (NYSE     instruments (12          store retained,        only, no
 2016-2027,         contracts, 4 tick        O-3 measured the       directory)
 108 closures,      grids)                   edge at zero
 23 early closes)   propfirm (profile,
   |                risk engine,               |
 daily sleeve       simulator, evaluate)       |
 intraday sleeve      |                        |
   |                   |                       |
   +-------------------+-----------------------+
                                   |
                        EXECUTION INTERFACE
        Signal -> OrderIntent -> RiskChain -> ExecutionAdapter -> venue
                                   |
              +--------------------+--------------------+
              |                                         |
        quant_brain/brokers/                     PROP FIRM ADAPTERS
        IBKRAdapter (live, both runners)         interface defined,
        SimulatedAdapter (research + tests)      no live adapter yet
```

Alongside the market branches, and used by all of them:

```text
                       quant_brain/research/
                                   |
     +-----------------------------+-----------------------------+
     |                             |                             |
  registry.py                  search.py                  core/validation.py
  Experiment / Ledger          bounded funnel             purged walk-forward
  Stage ladder                 4 gates in cost order      write-once holdout
  trials counted from disk     resumable by fingerprint   embargo (k-fold only)
```

`*` costs and sizing currently live as constants in `scripts/intraday_common.py`. The ABCs
they will move behind are the next extraction; see §5.

### The two rules the shape enforces

**Nothing above `quant_brain/brokers/` may import a broker SDK.** Checked structurally:
`tests/test_qb_adapter.py` walks the AST of every other module and fails on an import of
`ib_async`, `ib_insync`, `ibapi`, `alpaca` or `polygon`. This is what makes a second venue
reachable without editing a trading loop.

**There is one path to a venue and it runs through the risk chain.** `RoutedExecutor` is that
path. A denied intent never reaches an adapter, a reduced intent arrives at the reduced size,
and no ordering of engines lets a later one re-permit what an earlier one denied. A `FLATTEN`
bypasses every engine, because a risk layer that can block the exit is not a risk layer.

---

## 2. What is in the core, and the rule for what may be

`quant_brain/core/` contains **only** logic that is true regardless of instrument, venue or
market. The test is simple and worth applying literally: if a module would need an `if
asset_class == ...`, it does not belong in the core.

| Module | Owns | Why it is core |
|---|---|---|
| `instruments.py` | `InstrumentSpec`, `AssetClass` | "one unit is worth X, ticks in Y" is true of every tradable thing. Roll rules and greeks are not, and are not here. |
| `calendar.py` | `SessionCalendar` ABC, `Session`, `minutes_before_close` | Every market has sessions. *Which* days is market-specific and lives in the branch. |
| `execution.py` | `OrderIntent`, `Fill`, `Position`, `Side` | An order intent is venue-free by construction. This is the seam that keeps strategies off broker APIs. |
| `risk.py` | `RiskDecision`, `RiskEngine`, `RiskChain` | Composition of constraints. Knows no limits itself. |
| `state.py` | `StateScope`, `StateStore` | Live/paper/dryrun/backtest/research separation, enforced by containment. |
| `provenance.py` | `Provenance`, `env_key` | Reproducibility metadata. |
| `knowledge.py` | `KnowledgeIndex` | "Have we tried this?" over the ledger and backlog. |
| `resources.py` | `ResourceSnapshot`, `plan_workers`, `ResourceRegistry` | Worker budgeting from RAM, commit charge and CPU. |

**Explicitly not core**, per Part 3 of the brief and enforced by review: futures tick size and
roll, options greeks and exercise, crypto's 24/7 session, equity corporate actions.

---

## 3. Repository map: old to new

Nothing was moved. The core was added beside the existing tree, because six agent tracks edit
this working directory concurrently and the intraday sleeve is deployed on paper — a
relocation of `scripts/` would have broken in-flight work and a live runner on the same
afternoon. Migration is by **extraction with delegation**, not by `git mv`.

| Existing | Classification | Disposition |
|---|---|---|
| `scripts/intraday_common.py` | CORE + EQUITY | Constants (`SLIPPAGE_BPS`, `COMMISSION_PER_SHARE`, `SEC_FEE_RATE`, `TAF_*`, `FLATTEN_MINUTE`) are equity-specific and move behind `CostModel` / `SessionCalendar`. 33 importers, so it moves last and by delegation. |
| `scripts/paper_trade.py` | EXECUTION (equity, daily) | Now scope-routed through `core.state`. Next: `OrderIntent` + an IBKR adapter. |
| `scripts/intraday_trader.py` | EXECUTION (equity, intraday) | Same path. Untouched so far — it is the deployed runner. |
| `scripts/intraday_backtest.py` | RESEARCH (equity) | Will emit `SessionPnL` so prop-firm `evaluate()` can consume equity strategies too. |
| `scripts/evaluate.py` | RESEARCH (core) | The promotion gate. Now covered by 35 tests. Candidate for `core/` once it stops being LEAN-shaped. |
| `scripts/backtest.py` | RESEARCH (core) | LEAN launcher. Should record `Provenance` into each ledger row. |
| `scripts/futures_data.py` | FUTURES | `SPECS` superseded by `markets/futures_cme/instruments.py`; the IBKR fetch stays. |
| `scripts/odte_data.py`, `sweep_o*.py` | OPTIONS | Parked, store retained. See §6. |
| `scripts/sweep_*.py` (32 files) | RESEARCH archive | Kept as the executable record of a result. Not maintained code; lint is advisory on them. |
| `scripts/dashboard/` | OBSERVABILITY | Unchanged. Read-only, loopback. |
| `scripts/qb_check.py` | INFRASTRUCTURE | New. The completion gate. |
| `algorithms/*/signal.py` | Strategy | Unchanged. Both contracts still hold. |
| `research/*` | Knowledge | Unchanged, now indexed. |
| `lean` pip CLI, `docker` SDK | DELETE CANDIDATE | Structurally unusable — no virtualization on this machine, and `CLAUDE.md` bans `lean backtest`. |
| `project-x-py` | INVESTIGATE | Prop-firm futures client, referenced by zero files. Keep with a written reason or remove. |

---

## 4. The futures branch

Priority market (Part 24 P0). Data is unblocked: F-2a's probe returned 2,760 one-minute
TRADES bars each for ES/MES/NQ/MNQ on the existing IBKR paper account
(`research/futures_probe.json`, 2026-09-11), and measured the ES round trip at **0.488 bps**.

```text
Futures signal
      |
      v
Futures risk (position, exposure)
      |
      v
PropFirmRiskEngine          <-- deterministic; no model input reaches it
      |
      v
OrderIntent -> ExecutionAdapter
```

`markets/futures_cme/instruments.py` carries twelve contracts across **four distinct tick
grids** — assuming ES's 0.25 is wrong for five of them. `DATA_VERIFIED` names the four with
proven history; anything else is architecturally supported but unbacked, and a run using one
should say so.

`propfirm.py` models the thing a Sharpe ratio cannot see: an **absorbing barrier**. Three
trailing conventions (`none` / `eod` / `intraday`) because firms genuinely differ and it
drives survival more than any parameter choice. `evaluate()` returns a distribution — pass
rate, failure modes by cause, expected capital net of the entry fee — because Part 6 is
explicit that CAGR is the wrong objective here.

Profiles are named by **rule shape, never by firm**. A profile called `topstep_50k` frozen in
source looks authoritative and becomes a liability the first time the rulebook changes.
`from_dict` rejects unknown keys so a typo'd rule fails loudly instead of silently disabling
a limit.

---

## 4a. Venues, brokers, and what may reach them

Two independent questions, kept apart because conflating them is how prop-firm integrations
fire unintended orders.

```text
  Authority  (quant_brain/core/mode.py)      what may this PROCESS do?
    RESEARCH -> BACKTEST -> VALIDATED -> PAPER -> PRACTICE -> HUMAN_APPROVAL -> EXECUTION_READY

  ConnectionState (per adapter)              what can this SOCKET do?
    DISCONNECTED -> AUTHENTICATING -> AUTHENTICATED -> PRACTICE_READY / DRY_RUN
                                                    -> EXECUTION_READY | HALTED
```

`AUTHENTICATED` means a token exists. It grants read access and nothing else; a test asserts
`EXECUTION_READY` is the only connection state whose `can_send` is true.

```text
Signal -> OrderIntent -> RiskChain -> RoutedExecutor -> ExecutionAdapter -> venue
                                          |
                            checks Authority >= adapter.requires
                            AT CONSTRUCTION, not at submit
```

| adapter | requires | reaches |
|---|---|---|
| `SimulatedAdapter` | BACKTEST | nothing, in-memory |
| `IBKRAdapter` | PAPER | IB Gateway paper |
| `IBKRAdapter(live=True)` | EXECUTION_READY | IB Gateway live |
| `ProjectXAdapter` (dry run) | PRACTICE | nothing; records `would_send` |
| `ProjectXAdapter` (armed) | EXECUTION_READY | TopstepX |
| base class default | EXECUTION_READY | an author who forgets gets the strictest answer |

**Reaching EXECUTION_READY needs three independent things** and no single edit supplies all
three: an explicit `i_understand_this_is_real_money` argument, `QB_LIVE_TRADING_ENABLED` set
outside the code, and a per-venue-per-account approval file written by a person.
`QB_ACCOUNT_MODE` can select up to PRACTICE and is refused above it.

**Nothing above `quant_brain/brokers/` may import a broker SDK** — checked by walking the AST
of every other module.

Full detail, including what is safe to point at a practice account today and the eight things
still required before live execution, is in `docs/topstep/EXECUTION.md`.

---

## 4b. The research engine

`quant_brain/research/` is market-agnostic and is what the Options branch will share when it
restarts. Three pieces:

**`registry.py` — the ledger.** An append-only JSONL record of every experiment, written
atomically because six agent tracks share this tree. Its one non-negotiable property is that
`Ledger.verdict()` has **no `n_trials` parameter**. It counts the distinct experiments already
recorded in the same family and sizes the Bonferroni threshold from that. Measured: the same
series faces |t| > 1.96 as the first hypothesis in a family and |t| > 3.66 as the 202nd, with
nobody asked. A test asserts the signature exposes no `n_trials`, `trials`, `alpha`,
`override` or `force`, because a keyword like that would be used by exactly the person who
wants the result to be significant.

Experiment identity is a fingerprint over the hypothesis and parameters, deliberately
excluding metrics, timestamp and verdict. Re-running a specification is therefore idempotent:
a search cannot launder its multiplicity by repeating itself, and equally cannot inflate its
own penalty for nothing. **Rejected experiments stay in the ledger and stay in the
denominator** — a system that forgets its rejections flatters its survivors.

**`search.py` — the funnel.** Four gates in increasing order of cost: statistics, cost and
execution, Topstep survival, walk-forward. The order is load-bearing rather than an
optimisation. Running the statistical gate last would mean the survivors had been pre-selected
by filters the multiplicity correction cannot see, and the reported t would be a claim about a
much smaller search than actually happened. Bounded by an experiment budget, a wall-clock
budget and a machine-pressure check between candidates; resumable because duplicates are
detected by fingerprint before they run.

**`core/multipletest.py` — the correction suite.** Holm, Benjamini-Hochberg,
Benjamini-Yekutieli, White's Reality Check, Hansen's SPA, the Deflated Sharpe Ratio and PBO.
Each documents the assumption it rests on and refuses when it is violated rather than
returning a plausible number. SPA is the default over Reality Check because RC is corrupted by
padding: measured, a marginal edge among 20 candidates gives RC p = 0.032, and adding 80
hopeless variants pushes it to 0.129 while SPA is unchanged at 0.015.

**`research/robustness.py` — regimes and concentration.** Causal regime labelling (every label
computed from sessions strictly before the one it labels) plus the metrics that answer "is
this one lucky path": best-day/week/month share, effective sessions, Gini against its
arithmetic floor, totals with the best N days removed, time under water, parameter-neighbour
decay. Every metric declares whether its reading is arithmetic or a judgement.

**`core/validation.py` — purged walk-forward and the holdout.** Label-horizon purging, and a
final holdout whose ledger is keyed by a fingerprint of the data, so a second evaluation next
week from a fresh process is still refused. One finding worth carrying: **under strict
walk-forward the embargo is structurally vacuous** — every training row precedes the test fold
by construction, so no embargo width can remove one. It is `purged_kfold` that needs it.

### Withdrawing a result

`Ledger.retract(id, why=...)` appends a retraction; `all()` applies it on read by moving the
experiment to REJECTED with the reason in its notes. The original row stays byte-identical and
`trials()` is unchanged — a retracted experiment is still a trial and still belongs in the
denominator of every later correction. Built because a hypothesis that survived the funnel at
t = +6.25 turned out to be produced by a lookahead, and neither deleting it nor leaving it as
a survivor was acceptable.

### The promotion ladder

`RESEARCH -> VALIDATION -> CHALLENGER -> PAPER -> CHAMPION`, with `REJECTED` terminal from
anywhere. Skipping a rung raises. Surviving the funnel promotes a candidate to `VALIDATION`
and no further; champion straight from research is the failure the ladder exists to prevent.

---

### Options branch, current state (2026-09-13)

Seven items, not the three a stale note recorded: five refusals (O-1, O-1b, O-2, O-3, O-5),
one feed disqualification (O-4), and one PASS (O-6 — the chain's magnitude skill as a risk
input, not a tradeable edge). O-6's PASS currently has **no consumer**: it was handed to the
A-track and A-15 refused the whole class on mechanism.

The branch is functional and was NOT broken by the futures work — 1,010 tests green, all nine
options modules import, `sweep_o5`/`sweep_o6` reproduce their journals to the digit. It is
blocked on the Theta VALUE tier (OWNER-5).

Its real structural weakness is unprotected intelligence: `Chain`, parity spot, `prob_itm`,
`pick_strike` and the round-trip cost model all live inside `scripts/sweep_o2.py`, imported by
four other items, excluded from ruff-strict and pyright, with **no test covering the pricing
path**. Extracting those into `quant_brain/markets/options_us/` is the highest-value options
work that needs no data at all.

---

## 5. What has not been done, and why

Honest list. None of these are blocked; they are sequenced.

1. **`CostModel` and `Sizer` ABCs are not extracted.** `intraday_common.py` has 33 importers
   and feeds a deployed runner. The calendar was extracted first because it fixes a live
   defect (AUD-07) and pays for itself immediately.
2. **The runners do not emit `OrderIntent` yet.** `paper_trade.py` and `intraday_trader.py`
   still build `ib_async` objects inline. The abstraction exists and is tested; wiring it is
   a live-money change that needs `--replay` and `compare_orders.py` evidence.
3. **No prop-firm execution adapter.** Deliberate: there is no funded account, and Part 27
   says not to build for what does not exist.
4. **`etf`, `bitcoin`, `crypto` have no directories.** Also deliberate. The registry and the
   ABCs already accept them; creating empty packages to match a diagram is the overengineering
   Part 27 warns against. ETF is not a separate branch at all — it is already the daily
   sleeve's universe.
5. **The Portfolio Brain is not built.** The two live sleeves are kept safe by *universe
   disjointness*, which is cheap and correct for two sleeves and does not generalise to five.
   A real allocator is needed when the third branch goes live, not before.
6. **Options are parked on a measurement, not neglect.** O-3 found the 0DTE variance risk
   premium is not conditional (best of twelve terciles with hindsight: cover 1.043, +0.052%
   at t 0.09) and the Theta subscription has lapsed to FREE. The 176 MB store is retained.

---

## 6. Engineering gates

```text
change -> scripts/qb_check.py -> ruff + pyright + pytest -> commit
                                        |
                        (live runners also: --replay, compare_orders.py)
```

Two-tier by measurement, not by preference: the strict ruleset reports ~1,350 findings on
`scripts/` + `algorithms/` and zero on `quant_brain/` + `tests/`. Blocking on the core and on
changed files; advisory on the research surface via `--advisory`, so the debt stays visible
instead of being deleted from the config. It shrinks by removing lines from
`per-file-ignores` in `ruff.toml`, one rule family per commit.

Two traps recorded in `ruff.toml` rather than silently suppressed:

- **`I001`'s autofix is dangerous in `scripts/`.** Those modules `sys.path.insert` then import
  siblings by bare name (hence `# noqa: E402`). Sorting the block hoists the import above the
  path setup and turns a lint fix into an `ImportError` in a runner.
- **`F821` on `ml_f7.py:295`** is a verified false positive: `last_px`/`last_syms` are
  loop-carried and the first iteration is guarded by an empty `prev_w`.

---

## 7. Resources

`quant_brain/core/resources.py` budgets workers off **both** physical memory and Windows
commit charge, and reports which bound. The commit leg is the point:

```text
observed 2026-09-12, one hour apart
  sweeps at --workers 1          41.8 GB free, 16 threads idle       under-subscribed
  3x sweep_a8 --workers 11       34.7 GB free (55%, reads healthy)
                                 commit 81.5/83.4 GB = 98%           2 GB from failure
```

A free-RAM budget authorises ~35 workers in the second state. `plan_workers` returned 1,
`limited_by="commit"`. Windows fails a commit long before physical memory runs out.

```powershell
python -m quant_brain.core.resources          # snapshot + budget + pressure
```

---

## 8. Adding a market

1. `quant_brain/markets/<name>/` with `instruments.py` and `calendar.py`.
2. Implement `SessionCalendar`; set `coverage_end` honestly — past it, the calendar raises
   rather than guessing, per Part 18's `UNKNOWN STATE = DO NOT TRADE`.
3. Add contract terms as `InstrumentSpec`s. Derive `tick_value`; never store it.
4. Strategies stay under `algorithms/`, behind the existing contracts.
5. Risk limits go in the branch, composed via `RiskChain`. Never in the core.
6. Tests before wiring: the calendar's session lengths and the risk engine's refusals are
   what everything else assumes.

---

## 9. Which components can touch what

| component | research | simulation | paper / practice | execution-capable |
|---|---|---|---|---|
| `core/stats`, `core/multipletest`, `core/validation` | yes | — | — | no |
| `research/registry`, `search`, `robustness`, `promotion` | yes | — | — | no |
| `markets/futures_cme/*` (rules, twin, paths, features) | yes | yes | — | no |
| `markets/futures_cme/execution_sim` | yes | yes | — | no |
| `core/execution` (`OrderIntent`, `RiskChain`, `RoutedExecutor`) | — | yes | yes | yes, gated |
| `brokers/ibkr` | — | — | yes (paper) | only with `live=True` + EXECUTION_READY |
| `brokers/projectx` | — | — | dry run only | **no** — submission is unimplemented |

Nothing in this repository is execution-capable against a prop firm today. The ProjectX
adapter's `submit()` raises on a live path by design: an implementation present but gated is
one edit from an accident, and an implementation absent is not.

---

## 10. Command line

`python -m quant_brain <group> <command>`, following the existing per-module `_main`
convention.

```text
mode                what this process is allowed to do, and why
topstep rules       every rule with its source and confidence tier (--raw for citations)
topstep unresolved  what still needs the owner; exits non-zero
topstep readiness   the gate between here and a practice account
broker list         every adapter and the authority it demands
research ledger     trials and verdicts by family
```

Commands needing a venue connection are absent rather than stubbed.

