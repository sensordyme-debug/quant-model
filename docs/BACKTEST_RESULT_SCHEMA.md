# Backtest Result Schema

Every run writes four artifacts to `research/strategy_runs/<name>_<spec_hash>_*`.

## `_trades.csv` — the canonical trade ledger

```
trade_id, strategy, instrument, session, direction, quantity,
entry_bar, exit_bar, entry_time, exit_time, entry_price, exit_price,
gross_pnl, commission_and_spread, slippage, net_pnl,
mae, mfe, r_multiple, exit_reason, holding_minutes, ambiguous_bar,
day_of_week, month
```

**The equity curve must be reconstructible from this file.** If it is not, the result is
INVALID by definition, and `validate()` enforces that.

`exit_reason` is one of `stop`, `target`, `trail`, `time_stop`, `signal_invalidation`,
`forced_flatten`. There are no others; the engine cannot produce an exit it has no name for.

`r_multiple` is measured against the architecture's own initial risk. Where the spec declares
no stop it is measured against the entry session's ATR and is **not** a stop-based R — stated
here because the two are routinely confused.

`ambiguous_bar` is `True` when the exit bar's range spanned both the stop and the target. Those
trades were resolved as stops.

## `_monthly.csv`

```
month, sessions, net_pnl, mean_daily, best_day, worst_day,
positive_days, negative_days, win_rate_days, max_drawdown, longest_losing_streak
```

## `_scenarios.csv`

One row per execution scenario:

```
slippage_ticks, scenario, trades, gross_pnl, commission, slippage_cost, net_pnl,
per_trade, per_session, win_rate, profit_factor, max_drawdown,
sharpe, sortino, t_stat, consec_losing_days, exposure
```

Gross is always present alongside net. There is no mode in which only net is reported.

## `_result.json`

| block | contents |
|---|---|
| `spec` | the full spec **including the signal's source text** |
| `spec_hash` | sha256[:16] over spec + signal body + execution assumptions |
| `provenance` | `engine_version, git_sha, git_dirty, data_source, data_hash, data_start, data_end, sessions, python, numpy, pandas, run_at, seed` |
| `validation` | `ledger_reconciles, equity_reconciles, independent_reconciles, every_trade_charged, ends_flat, no_future_leak, status, failures` |
| `monthly_distribution` | `months, mean, median, std, positive_share, negative_share, worst, best, p05, p25, p75, p95` |

`status` is one of:

- **VALIDATED** — every check passed
- **LIMITED** — checks failed but the arithmetic reconciles; the result is interpretable with
  the listed caveats
- **INVALID** — the arithmetic does not reconcile; the number is not a measurement

Reasons always travel with the status in `failures`.

## Sentinels

An undefined metric returns `NaN`, never a flattering default. Profit factor with no losing
trade is `NaN`, not `inf` — an `inf` beside a real 1.13 corrupts a ranking.

## Determinism

The spec hash covers the signal body, so two strategies with the same name and different logic
cannot share a hash. The dataset hash covers the actual bars used, so a data change invalidates
a stale result. Verified: two identical runs produce identical hashes and identical numbers.
