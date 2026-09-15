# How to hand over a strategy

```powershell
cp examples/strategy_template.py examples/my_strategy.py     # edit it
python scripts/run_strategy.py --spec examples.my_strategy:SPEC
```

That is the whole loop. The engine validates the spec, freezes and hashes it, runs the
backtest on canonical data, runs the Topstep twin, builds the monthly analysis and the Monte
Carlo, and prints a scorecard ending in one of six classifications.

**The engine will not optimise, tune, filter, re-time, resize or otherwise improve what you
write.** The first run of any strategy is a frozen-specification test. Parameter search is a
separate experiment that has to be asked for by name.

---

## What you can state

| you want to say | field |
|---|---|
| instrument | `StrategySpec.instrument` — `ES` · `NQ` · `MES` · `MNQ` |
| timeframe | `StrategySpec.timeframe` — `"1min"`, the only one on disk |
| session / window | `SessionSpec.open_et`, `close_et` |
| entry conditions | `StrategySpec.signal` — a callable over the feature frame |
| long / short conditions | the sign it returns: `+1` long, `-1` short, `0` flat |
| position sizing | `SizingSpec.contracts` |
| stop | `ExitSpec.stop_points` · `stop_atr` · `structural_stop` |
| target | `ExitSpec.target_points` · `target_r` |
| trailing logic | `ExitSpec.trail_points` · `trail_atr` · `breakeven_at_r` |
| time-based exit | `ExitSpec.time_stop_bars` |
| forced-flat behaviour | `SessionSpec.flat_by_et` (yours) — the venue's is enforced anyway |
| no new entries after a time | `SessionSpec.last_entry_et` |
| max simultaneous positions | `RiskSpec.max_open_positions` |
| cooldown | `RiskSpec.cooldown_bars` |
| max trades per session | `RiskSpec.max_trades_per_session` |
| strategy-specific state | `StrategySpec.params` — hashed and printed |
| why it should work | `StrategySpec.rationale` — recorded, never parsed |

### Points or ATR — and never a translation between them

Every price leg takes a fixed **point** distance or an **ATR multiple**. "A ten-point stop" and
"a 1.4-ATR stop" are different strategies: the second is a different distance every session. A
leg given both ways is refused rather than resolved, because resolving it would mean choosing
on your behalf.

`target_r` and `breakeven_at_r` are multiples of **R, the initial stop distance**, so they
require a stop. Without one the exit simulator would fall back to the session ATR and "2R"
would silently mean "2 ATR". That combination is refused by name.

---

## What is enforced whatever you write

1. **The session ends flat.** Topstep's mandatory flat is 15:10 CT and is not a parameter.
2. **Every completed round turn is charged.** Gross is reported beside net, never instead.
3. **A position decided on bar *i* fills at bar *i*'s close** and earns from there. You cannot
   ask for a fill at a price that existed before the information the decision used.
4. **A resting price must be a whole number of ticks.** A 10.1-point stop on a 0.25-tick
   instrument is refused, with the two valid neighbours named — not rounded.
5. **No new position opens on the forced-flat bar.** It could not be held and could only lose a
   round turn.

---

## Ambiguity is an error

`StrategySpec.ambiguities()` runs at construction and raises on anything with two readings. The
engine never picks. What it refuses today:

- two stop forms, two target forms, or two trail forms at once
- `target_r` or `breakeven_at_r` with no stop — R would be undefined
- `last_entry_bar` and `last_entry_et` together — two spellings of one rule that can disagree
- an entry cutoff at or after the forced flat
- a stop/target/trail that is not a whole number of ticks on this instrument
- a `time_stop_bars` at least as long as the session — a rule that can never fire
- a `warmup_bars` that leaves no bar on which an entry is permitted
- `max_open_positions != 1` — a stated engine limitation, not a preference: the simulator
  models one position and will not approximate a pyramid as a single position
- an instrument the contract registry does not know

If a rule you need is not expressible, say so rather than working around it. Working around it
produces a result for a different strategy under your strategy's name.

---

## What comes back

One scorecard, printed and written to `research/strategy_runs/<name>_<hash>_report.txt`, with
the full JSON beside it.

**A** summary — hash, instrument, coverage, sessions, bars, the data manifest, the execution
mode, the Topstep rules version, and whether long-history validation is available (it is not).
**B** trade statistics — counts, win rate, mean/median/sd, best/worst, profit factor,
expectancy, gross profit and loss, fees, slippage, hold times, exits by reason.
**C** risk — max drawdown, max intraday drawdown, consecutive losses, consecutive losing days,
MAE and MFE distributions with their basis stated, risk per trade, worst day, worst session,
exposure, time under water.
**D** time — P&L by month, quarter and year, with trades, win rate and drawdown per month, and
the monthly distribution. Two denominators, never mixed: **% of $50K** (a scale — Topstep
requires no such capital) and **% of notional** (the contract value actually controlled).
**E** Topstep — balances, MLL, DLL, minimum buffers, liquidation, target, forced flats,
contract limits, survival, and the cross-check against the independent reference.
**F** payout — eligibility, timing, amount under the configured policy, and the probabilities.
Reported separately from performance, because **a backtest profit is not a payout**.

Then: the four-mode execution ladder (headline is CONSERVATIVE, never IDEAL); Monte Carlo over
1,000–5,000 resampled paths, labelled as path risk and explicitly not evidence of edge; the
full regime distribution with every bucket shown and none recommended; statistical confidence
including the expectancy CI, concentration and the dependence caveats; explicit limitations;
and the classification.

### The six classifications

Criteria are constants at the top of `quant_brain/research/strategy_report.py`, fixed before any
result exists.

| | |
|---|---|
| **UNTESTABLE** | under 30 trades, 60 sessions or 6 months |
| **NEGATIVE** | net P&L ≤ 0 under CONSERVATIVE |
| **FRAGILE** | positive, but negative under STRESS, or the top 5% of sessions carry > 50% of net, or one month carries > 60%, or under half the months are positive, or the account is liquidated |
| **INCONCLUSIVE** | positive and not fragile, but expectancy *t* < 2.0 |
| **PROMISING** | positive, not fragile, *t* ≥ 2.0, survives STRESS — but under 24 months or no clean holdout |
| **ROBUST POSITIVE** | all of the above plus ≥ 24 months **and** a clean holdout. **Not reachable on the current 15-month store, by construction.** |

---

## The limits of the current data

```
CURRENT HISTORICAL DEPTH:   ES/NQ 2025-06-08 → 2026-09-10   (310 sessions)
                            MES/MNQ 2025-09-07 → 2026-09-10 (249 sessions)
LONG-HISTORY VALIDATION:    NOT AVAILABLE
```

Roughly fifteen months, four rolls per instrument. Fifteen months is not long-term validation,
and a strategy that looks exceptional over this window should be read as exceptional **over
this window**. Every report says so in its own limitations section.

If you have a strategy designed independently and before seeing this data, say so and pass
`--holdout "..."` describing the split. Otherwise the report prints **NO CLEAN HOLDOUT**, which
is the honest reading — a holdout carved out after seeing the result is not one.
