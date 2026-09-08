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

## LEAN order execution on daily bars (learned 2026-09-08, S-1)

Every one of these produced a plausible-looking backtest rather than an error. On daily
resolution the statistics block cannot be trusted until execution is verified separately.

- **A daily-resolution security's local time is its last bar stamp**, so the exchange looks
  closed to any intraday scheduled event. Market orders silently degrade to MarketOnOpen,
  and the IB brokerage model rejects MOO submitted outside 04:00-09:28. Symptom: thousands
  of orders, zero fills, `Total Fees $0`, equity exactly unchanged.
- **Do not rebalance from a pre-open scheduled event on daily data.** MOO orders sent at
  09:00 on day D are still unfilled at 09:00 on day D+1, so the next rebalance reads stale
  holdings and stacks another full target. This reached 12.7x gross against a 1.0 cap and
  wiped the account. Rebalance from `on_data` on the daily bar instead: decide on day D's
  close, fill at day D+1's open, exactly one order batch in flight.
- **`set_holdings(PortfolioTarget(symbol, w))` sizes `w` against buying power, not equity.**
  Account leverage therefore multiplies every target: identical signals gave 27% annualized
  vol at 2x leverage and 43% at 4x, against 16% on paper. For anything leverage-sensitive,
  compute share counts from `portfolio.total_portfolio_value` and send `market_order` deltas,
  sells first. That is also the order-list logic a live IBKR runner needs.
- **LEAN charges initial margin on both legs of a rotation** because pending MOO orders do
  not net. At gross 1.0 with default 2x this rejected 1,467 of 3,690 rebalances; at gross 1.3,
  3,004 of 3,690. Raising `set_leverage` fixes the artifact, but only do so alongside an audit
  of the gross exposure actually carried - otherwise a real sizing bug becomes invisible.
- **Always audit realized gross exposure** (`sum(abs(holdings_value)) / total_portfolio_value`)
  against the intended cap and log it at end of algorithm. That single line is what
  distinguished "the signal is bad" from "the orders are wrong" in every case above.

## Research-method notes (learned 2026-09-08, S-1)

- A drawdown rule of "go flat until a new equity high" is an **absorbing state**: a flat book
  earns nothing, so it can never print a new high. Adding a cooldown is not enough either -
  if the high-water mark survives, the breaker re-arms the moment it releases and trades one
  day in N forever. Reset the watermark when the breaker releases.
- Validate a signal outside the engine first. `scripts/sweep_s1.py` runs a config in ~25s
  against LEAN's own bars via `scripts/lean_prices.py`, versus ~3.5 min for a LEAN run, and
  it imports the shipped signal module so the two cannot silently diverge. Sweep to choose
  parameters, then confirm in LEAN - and treat any large gap between them as an execution
  bug, because that is what it was every time.
- Judge a component on each sub-period independently, not on the full sample. That is what
  justified dropping both the vol-below-median filter and the 200-day trend filter from S-1.
