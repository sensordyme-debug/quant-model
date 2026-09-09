# MEMORY.md - Durable decisions and facts

Long-lived facts the loop should not have to rediscover. Newest section first.
Daily raw notes live in `memory/YYYY-MM-DD.md`.

## IBKR connection states (learned 2026-09-09, daily review)

- **An open port 4002 does not mean the API is usable.** Gateway accepts the TCP connection,
  then refuses the handshake with `Error 10141: Paper trading disclaimer must first be
  accepted for API connection` and drops the socket; `ib_async` surfaces this as a generic
  `TimeoutError` plus "clientId already in use?", which is misleading - the client id is fine.
  Always read the 10141 line above the traceback before diagnosing anything else.
- So the port probe and the API probe are **different checks**. `paper_trade.py --check` is
  read-only, takes seconds and gives the real answer; run it rather than a socket test whenever
  the Gateway blocker is being re-evaluated.

## Research method lessons (learned 2026-09-08/09, S-8 through S-13)

- **Promotion requires a shelf, not a spike.** A cell that beats the champion on every gate
  while both of its neighbours lose is path luck, not an effect - S-13's `min_order_value=0.02`
  passed `evaluate.py` and agreed in sign on both sub-periods, and was still correctly refused.
  Sub-period agreement at margins inside the region's own scatter is two draws from that
  scatter, not independent confirmation.
- **Prefer the a-priori parameter to the argmax inside a shelf.** S-9 shipped 252 over 250,
  S-10 shipped a 5-session skip, S-12 shipped a 21-session vol window over the 20 argmax.
- **`sweep_s1.py` and LEAN can disagree in sign, not only in magnitude** (S-10). The sweep also
  understates drawdown: ~+2 points at champion size, ~+6 on S-12's cell, +8 to +10 at 2x
  exposure. Sweeps generate candidates; LEAN decides. A sweep rejection buys one confirmation
  run, never a closed idea.
- **The ETF-9 sleeve is out of cheap levers, by measurement.** S-11 showed the champion's
  turnover cannot be converted into return (suppressing rotation removes return monotonically -
  the rotation is signal); S-13 showed it cannot be removed for return either (the band is flat
  and non-monotone across a factor of eight, so ~63% of orders are return-neutral). S-12 spent
  the allocation step. What remains needs breadth or a second sleeve, i.e. D-2/S-2, not another
  parameter on this sleeve.
- **Backtest-neutral is not live-neutral.** LEAN charges commission but models no spread at
  all, so a change that is worth $0 in the ledger (a wider no-trade band) can still be worth
  real money live. Route those to the human as execution decisions rather than closing them as
  negative research results.
- **Commission floor at this account size is 2.1bps per unit of turnover** (S-3), before any
  spread - more than the entire gross edge a daily-turnover reversal sleeve could find.

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

## Research-method notes (learned 2026-09-08, S-11)

- **A turnover reduction is only free if the turnover was noise.** Three independent whipsaw
  controls on the S-1 champion (score hysteresis, minimum holding period, rank persistence)
  each removed return roughly in proportion to the drawdown they removed, monotonically in
  the strength of the control. When suppressing rotation costs return, the rotation was
  carrying information and the cost floor is being paid for something. Measure the exchange
  rate (CAR points given up per drawdown point bought) before treating a cost saving as a win.
- **A lever that blocks an entry is not automatically a lever that cuts trading.** Rank
  persistence *raised* order count 6% and fees 24% in LEAN, because refusing to fund a name
  parks the book in cash and then buys it back a few days later. Check realized order counts,
  not just the intent of the rule.
- **Path-dependent signal state must be threaded, not rebuilt.** `drawdown_multiplier`
  returns a fresh state dict, so any new persistent field (here `held` / `held_age`) has to be
  read before that call and written back after it. Every early return that means "sit in cash"
  must clear the field, or the next call defends holdings that do not exist.
