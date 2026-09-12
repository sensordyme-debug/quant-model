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
                     OrderIntent -> ExecutionAdapter
                                   |
              +--------------------+--------------------+
              |                                         |
        BROKER ADAPTERS                          PROP FIRM ADAPTERS
        ib_async (live)                          interface defined,
                                                 no live adapter yet
```

`*` costs and sizing currently live as constants in `scripts/intraday_common.py`. The ABCs
they will move behind are the next extraction; see §5.

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
