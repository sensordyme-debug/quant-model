# V1.0.0_Frozen — integration plan and conflict register

Written BEFORE any code. The frozen specification cannot be expressed through the existing
`StrategySpec` pipeline; this document says exactly why, what is reused, what is new, and
every point where the frozen spec and the existing certified architecture disagree.

---

## 1. What the existing architecture provides, and whether it fits

| existing component | fits? | decision |
|---|---|---|
| `markets/futures_cme/instruments.py` — NQ/MNQ terms | **yes** | **reuse** (multiplier, tick, tick value) |
| `research/canonical_ledger.py` — `Fill`, `LedgerTrade`, `SessionLedger` | **yes** | **reuse** as the output types |
| `research/bracket_reference.py` — ambiguous-bar precedence, gap policy | **yes** | **reuse the policy** (STOP before TARGET, fill at the level) |
| `core/calendar.py` — `ET = ZoneInfo("America/New_York")` | **yes** | **reuse** the authoritative tz object |
| `core/protection.py` — `WorkingOrder`, protection states | **yes** | **reuse** the working-order shape |
| `core/idempotency.py` — `intent_id`, duplicate detection | partly | reuse the *idea*; the journal is file-backed and live-oriented |
| `scripts/engine_mutation_test.py` + `_mutation_specs.py` | **yes** | **reuse** |
| `research/strategy_spec.py` — `StrategySpec` | **NO** | see C1 |
| `research/exits.py` — `simulate_trade` | **NO** | see C2, C3 |
| `research/ledger_builder.py` — `build_ledger` | **NO** | see C4 |
| `markets/futures_cme/twin.py` — Topstep twin | **not for this** | see C5 |
| `research/session_source.py` — RTH session cutting | **NO** | see C6 |
| `markets/futures_cme/features.py` — `vwap_dist` | **NO** | see C7 |

---

## 2. Conflict register

Each conflict is a place where the frozen specification and certified existing code disagree.
**Nothing existing is modified.** The frozen strategy gets its own module and the existing
pipeline is left exactly as certified.

### C1 — `StrategySpec` is stateless; the frozen strategy is a state machine

`StrategySpec.signal` is `callable(feature_frame) -> array of -1/0/+1`, evaluated once per
session, with no memory between bars. The frozen strategy carries cross-bar state that a
per-bar array cannot express: ARMED regimes, the identity of the MFE bar, a three-bar stall
window, a 45-minute cooldown clock, per-day trade counts, realized P&L, and a halt flag.

**Resolution:** a new stateful engine in `quant_brain/strategies/vwap_pullback/`.
`StrategySpec` is untouched and every existing strategy still runs through it.

### C2 — break-even semantics differ

`exits.ExitArchitecture.breakeven_at_r` moves the stop **to the entry price**, triggered at a
multiple of **R**. The frozen rule moves the stop to **fill ± 0.25** (one tick beyond
break-even), triggered at a fixed **15.0 points** of intrabar excursion.

**Resolution:** the frozen exit manager implements the frozen rule. `exits.py` is untouched.

### C3 — the +25 MFE stall rule does not exist anywhere

No component implements MFE-bar identification, a bounded forward window, or a target
modification. Entirely new.

### C4 — fill-price anchoring and where slippage lives

`ledger_builder` fills at the decision bar's close and charges slippage as a **dollar cost
line**, leaving `entry_price` equal to the bar close. The frozen spec requires one tick of
slippage **moving the actual fill price**, and stop/target anchored to that **fill price**.
These are different models and produce different stop levels.

**Resolution:** the frozen engine moves the fill price. `ledger_builder` is untouched, and
`test_the_frozen_engine_anchors_brackets_to_the_slipped_fill_and_not_the_bar_close` pins the
difference so nobody later "harmonises" them by accident.

### C5 — the Topstep twin is session-granular; the frozen governor is intrabar

`twin.py` consumes `TwinDay` (one settled P&L plus a path) and enforces the MLL/DLL. The
frozen governor is a **different, stricter, intraday** layer: a −$800 mark-to-market
killswitch, a +$1,200 profit cap, a 4-trade limit, a 2-loss circuit breaker and a 15:45 hard
flatten. They are complementary, not competing: the governor decides whether the strategy may
trade; the twin decides what the prop account does with the result.

**Resolution:** a new `governor.py`. `twin.py` untouched. The twin is not exercised in this
phase (no historical data), and the frozen 15:45 flatten deliberately precedes Topstep's later
16:10 mandatory flat.

### C6 — session cutting is incompatible with an 18:00 VWAP anchor

`session_source` cuts RTH windows (09:30–16:00) and drops incomplete sessions. The frozen VWAP
anchors at **18:00 ET the previous evening** and must be one continuous array across the
overnight session. RTH-cut frames do not contain those bars.

**Resolution:** the engine consumes a **continuous 1-minute stream**, not RTH session frames.

> **KNOWN GAP, carried to the next phase:** no loader exists that hands the engine an
> 18:00-anchored continuous stream from `data/futures/*.parquet`. This phase is synthetic-only
> so it is not a blocker, but the historical phase cannot start until that adapter exists and
> is equivalence-tested the way `session_source` was.

### C7 — `features.vwap_dist` is a different VWAP

The existing feature is **close-weighted** and anchored at the **start of the frame**. The
frozen VWAP is **typical-price weighted** and anchored at **18:00 ET**. Same word, different
quantity.

**Resolution:** not reused, and named `SessionVwap` to avoid the collision.

### C8 — the frozen commission contradicts the repository's cited rate

`instruments.py` carries NQ round-turn **$3.78**, cited to Topstep's published rate
(help.topstep.com/en/articles/8284197, retrieved 2026-09-13). The frozen spec says **$4.50**.

**Resolution:** the frozen spec wins for this strategy — §31 forbids changing it, and it is
the more conservative of the two. The frozen engine carries its own commission and does **not**
read the instrument default. Both numbers are recorded.

### C9 — multi-timeframe against a 1-minute-only contract

`StrategySpec` refuses any timeframe other than `1min` because resampling is unaudited. The
frozen strategy needs 5-minute context.

**Resolution:** the engine derives 5-minute bars from the 1-minute stream **internally and
causally** — a 5-minute bar exists only once its final minute has closed. No data-layer
resampling is introduced.

---

## 3. Ambiguity register — rules with more than one defensible reading

§31 says to report rather than silently change. None of these is resolved silently: each is an
explicit, declared, hashed field on the frozen spec, and where the readings differ materially
**both are implemented and tested**.

| # | rule | ambiguity | reading taken | material? |
|---|---|---|---|---|
| A1 | "5-minute ATR(14)" | Wilder smoothing or simple mean of TR | **Wilder** (the conventional meaning of ATR(14)) | **YES — needs confirmation** |
| A2 | governor MTM | evaluated on the bar close, or on the intrabar adverse extreme | **intrabar** (conservative, matches engine doctrine) | **YES — needs confirmation** |
| A3 | "no new entries after 15:30:00" | is a bar stamped 15:30 after the cutoff? | **inclusive** — the 15:30 bar is the last entry bar | moderate |
| A4 | "touch or penetrate VWAP" | which extreme | long: `low <= VWAP`; short: `high >= VWAP` | low |
| A5 | "the current 1-minute price" in the zone test | close, or any part of the bar | **close** | low |
| A6 | `SMA(volume, 10)` | includes the current bar or the prior 10 | **includes the current bar** (standard) | low |
| A7 | 5m regime `VWAP - low <= 6.0` | a bar entirely above VWAP gives a negative value, which passes | implemented **literally as written** | moderate |
| A8 | "a loss" for the streak | gross or net of costs | **net** | low |
| A9 | cooldown start | from entry or from exit of the 2nd loss | **exit** | low |
| A10 | stall "already beyond the new target" | which direction counts | long: `close >= fill+20` at the modification bar → market close | low |
| A11 | MNQ commission | frozen spec gives NQ only | repo's MNQ rate, $1.22 × 10 = **$12.20** | **flagged** |
| A12 | slippage scope | flatten / governor / stall exits | **none** — the spec names entry and stop-outs only | **optimistic, flagged** |
| A13 | trading-day boundary for counters | midnight or 18:00 | **18:00 ET**, matching the VWAP anchor and the halt release | low |

---

## 4. Module layout

```
quant_brain/strategies/vwap_pullback/
    spec.py         frozen constants, version, hash, ambiguity + conflict registers
    indicators.py   SessionVwap (18:00 anchored, one array), FiveMinuteAggregator,
                    Atr14 (Wilder and SMA), VolumeSma
    orders.py       Bracket / OCO with idempotent actions, built on core.protection shapes
    governor.py     MTM killswitch, profit cap, trade cap, loss streak, cooldown, hard flatten
    engine.py       the FSM and the bar loop; emits canonical Fill / LedgerTrade
```

Tests: `tests/test_vwap_indicators.py`, `tests/test_vwap_strategy.py`,
`tests/test_vwap_governor.py`. Mutations appended to `scripts/_mutation_specs.py`.

## 5. Out of scope for this phase

No historical data, no sweeps, no optimisation, no Monte Carlo, no payout analysis, no live
surface. The engine is exercised only on hand-built synthetic bars.
