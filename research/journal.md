# Research journal

Newest entry first. Each entry: what was tried, why, the result, the decision, the next step.

## 2026-09-08 - D-1 data pipeline (yfinance daily stopgap)

- **What.** Wrote `scripts/fetch_data.py`: fetches daily bars and writes LEAN-format
  `daily/<sym>.zip`, `map_files/<sym>.csv` and `factor_files/<sym>.csv` into
  `..\Lean\Data\equity\usa\`. Universe is the 19 ETFs from the backlog plus 50 megacaps
  (69 symbols, 1998-01-01 to 2026-09-04, ~430k bars). Existing LEAN sample files are
  backed up to `<name>.orig` before the first overwrite.
- **Why.** Every strategy result so far was a mechanics check on one sample week of SPY.
  Nothing in the backlog can be tested as alpha until real history exists.
- **Adjustment model.** Yahoo's OHLC are already split-adjusted, so the split factor stays
  1 and dividends are carried entirely by the price factor, accumulated backwards from 1
  as `(1 - D / C_prev)` per ex-date.
- **Two bugs the acceptance test caught, both silent:**
  1. Deriving factors from the `Adj Close / Close` ratio looks equivalent but Yahoo rounds
     `Adj Close`, so the ratio wobbles in the 7th decimal daily. SPY got 5490 factor rows
     instead of 117. Fixed by using explicit dividends.
  2. A symbol with no dividends produced a factor file containing only the `20501231`
     sentinel row, and **LEAN silently returned zero bars for it** - no error, no failed
     data request. GLD, UVXY and BRKB were dropped from the first smoke run this way.
     Fixed by always emitting a listing row at the first bar date; the validator now
     rejects a sentinel-only file.
  Also: Yahoo's bar for the in-progress session has `high < open`, so the default end date
  is now today (exclusive), with a clamp-and-report fallback for residual bad bars.
- **Result.** `d1_data_smoke` (20260908T162819Z) reports PASS: all 15 probed symbols deliver
  3690 bars over 2012-01-03 .. 2026-09-04 with no malformed bars. Independent checks: the
  computed factors agree with Yahoo's own `Adj Close` to within 0.003% worst-case across all
  69 symbols, and raw closes match known values (AAPL 2020-08-31 = 129.04, SPY 2020-03-23 =
  222.95, NVDA 2024-06-24 = 118.11).
- **Decision.** No champion. The run's headline numbers (8660% net profit, CAR 35.6%,
  Sharpe 0.80, drawdown 72.7%, 14 orders) are equal-weight buy-and-hold of 15 tickers
  including TQQQ/SOXL/UVXY across a 14-year bull run - a coverage probe, not a strategy.
  `evaluate.py` correctly refused it (14 orders < 30, drawdown 72.7% > 35%).
- **Next.** S-1 volatility-regime momentum rotation, which now has the ETF history it needs.
  Daily bars only: S-2 opening-range breakout still has no intraday data (see D-2).

## 2026-09-08 - Toolchain bring-up

- Built LEAN natively (.NET 10 SDK, Python 3.11, pythonnet) because Docker and WSL2 are
  unavailable on this machine.
- `python scripts/backtest.py _template` ran the SPY buy-and-hold template on the bundled
  sample week (2013-10-07 to 2013-10-11): 1 order, net profit 1.692%, Sharpe 8.85 on five days,
  which is meaningless as alpha and only proves the pipeline works.
- Decision: no champion yet. Next step is backlog D-1 (data pipeline); without real data every
  strategy result is a mechanics check, not evidence.
