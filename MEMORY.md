# MEMORY.md - Durable decisions and facts

Long-lived facts the loop should not have to rediscover. Newest section first.
Daily raw notes live in `memory/YYYY-MM-DD.md`.

## LEAN data format gotchas (learned 2026-09-08, backlog D-1)

- **A factor file containing only the `20501231,1,1,0` sentinel makes LEAN return zero bars
  for that symbol, silently.** No exception, no entry in `failed-data-requests-*.txt` - the
  symbol simply never appears in the `Slice`. This bites any symbol that has never paid a
  dividend (GLD, UVXY, BRKB, NOW, UBER). Always emit a listing row at the first bar date:
  `<first_bar_date>,<earliest_factor>,1,1`. `scripts/fetch_data.py` validates this now.
- Because of the above, an algorithm that gates on "all symbols present" will place zero
  orders and still exit 0 with a clean-looking summary. Log per-symbol bar counts in any
  data acceptance test rather than trusting the statistics block.
- Factor file rows are `date,price_factor,split_factor,reference_price`, ascending, where a
  row's date is the **last** bar date its factor applies to (LEAN takes the first row with
  `date >= bar date`). Real files carry one row per corporate action, ~117 for a
  dividend-paying name since 1998.
- Daily zips: `equity/usa/daily/<sym>.zip` holding `<sym>.csv`, rows
  `yyyyMMdd 00:00,o,h,l,c,v`, OHLC scaled by 10000 as integers.

## yfinance quirks (learned 2026-09-08)

- Yahoo's OHLC are **already split-adjusted**; only `Adj Close` adds dividends. So LEAN
  split factors stay 1 and dividends go entirely into the price factor.
- Do **not** derive price factors from `Adj Close / Close`: Yahoo rounds `Adj Close`, so the
  ratio drifts in the 7th decimal every day and generates a factor row per bar (5490 rows
  for SPY instead of 117). Use the explicit `Dividends` column from `actions=True` and
  accumulate `(1 - D / C_prev)` backwards from the most recent bar.
  `Adj Close` is still useful as an *independent cross-check* - agreement was within 0.003%.
- The in-progress session's bar is a live snapshot with `high < open`. Always end the fetch
  window exclusive of today.

## Toolchain (learned 2026-09-08)

- `git` had no identity in this repo; set locally to `quant / sensordyme@gmail.com`.
  Backtests run before the first commit record `"commit": "unknown"` in the ledger.
- `scripts/backtest.py` ignores the engine's exit code on purpose (pythonnet raises a
  harmless GIL finalizer error at shutdown); success is judged by the summary file existing.
