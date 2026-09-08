# Research journal

Newest entry first. Each entry: what was tried, why, the result, the decision, the next step.

## 2026-09-08 - S-1 volatility-regime momentum rotation (first champion)

- **What.** `algorithms/s1_momo/`, split into `signals.py` (plain pandas, prices in, target
  weights out) and `main.py` (LEAN plumbing only), so the I-1 paper runner can import the
  identical decision code. Supporting tools: `scripts/lean_prices.py` reads LEAN's own zips
  and factor files back into a DataFrame, and `scripts/sweep_s1.py` walks the shipped signal
  day by day outside the engine (~25s a config vs ~3.5 min for a LEAN run).
- **Why.** Top backlog item and the gate on the 2026-09-10 paper-trading objective.

### Two parts of the specified hypothesis did not survive contact with the data

1. **The regime filter as written is anti-predictive.** S-1 called for risk-on while 20-day
   realized vol sits below its 1-year median. On 2012-2026 SPY returns 4.7%/yr (Sharpe 0.58)
   on those "calm" days and 10.0% (Sharpe 0.75) on the days the filter excludes - vol peaks
   coincide with the sharpest rebounds. Applying it costs 13 points of annual return
   (18.8% -> 5.8% CAR). Replaced with a *crisis* filter: risk-off only once vol exceeds
   1.5x its median.
2. **A 200-day trend filter, the obvious substitute, also loses** - and loses on both halves
   independently (IS 14.7% vs 16.7% CAR, OOS 15.5% vs 21.2%), while buying no drawdown. Kept
   as an option, defaulted off. Deciding this on both sub-periods rather than the full sample
   is what makes it a finding rather than a fit.

### Three execution bugs, each of which silently faked a result

The signal was right early; every bad number came from execution. Worth recording because
they are all invisible in the summary statistics:

| Symptom | Cause |
| --- | --- |
| Stopped trading permanently in 2015 | "Flat until a new equity high" is an absorbing state - a flat book cannot print a high. |
| Every parameter set collapsed onto DD ~25% with erratic returns | Adding a cooldown but keeping the watermark: the breaker re-armed on release and traded 1 day in 22. Fixed by resetting the high-water mark when the breaker releases. |
| 9,095 orders, zero fills | Daily bars leave the exchange looking shut, so market orders degrade to MarketOnOpen, which IB rejects outside 04:00-09:28. |
| DD 87.5% at gross 1.3, then 57.6% at 1.0 | `set_holdings(PortfolioTarget(...))` sizes against *buying power*, so account leverage multiplies every target: same signals gave 27% vol at 2x and 43% at 4x against 16% on paper. Replaced with explicit share math. |
| Account wiped to $1.18, 264%/day turnover, 12.7x gross | MOO orders sent at 09:00 on day D were still unfilled at 09:00 on day D+1, so each rebalance read stale zero holdings and stacked another full target. Fixed by rebalancing on the daily bar, so one order batch is in flight at a time. |

The last one only became visible because `on_data` audits gross exposure actually carried
against the cap. That audit is now permanent; without it the blowup looked like a bad signal.

### Result (LEAN, `20260908T174548Z`, 2012-01-03 .. 2026-09-04)

| Window | CAR | Sharpe | MaxDD | Orders | Fees |
| --- | --- | --- | --- | --- | --- |
| Full 2012-2026 | 13.7% | 0.60 | 23.6% | 3,033 | $27,118 |
| IS 2012-2019 | 10.4% | 0.57 | 23.6% | 1,665 | $18,307 |
| OOS 2020-2026 | 17.8% | 0.64 | 20.8% | 1,373 | $4,200 |

Out-of-sample is the *stronger* half, which is the right direction for an honest fit.
Audited max gross carried 1.047 against a 1.0 cap, zero buying-power rejections, 83.7% of
days invested, mean effective exposure 1.27x.

Sensitivity (`--mode sensitivity`, +/-25% shocks): drawdown is robust, staying in 18.0-22.4%
across every shock. Return is not uniformly robust - halving the distance of the vol
threshold toward the median drops CAR to 7.7%, and `top_n=3` is a local peak (2 -> 10.2%,
4 -> 13.5%). No shock produces a loss or breaches the drawdown limit.

- **Decision.** Promoted to champion through `scripts/evaluate.py` (3,033 orders >= 30,
  drawdown 23.6% < 35%, no incumbent to beat). **It is a baseline, not a win.** Over the same
  period SPY compounds at ~15.0% and QQQ at ~19.9%, so S-1 does not beat buy-and-hold on
  absolute return; what it buys is drawdown, 23.6% against SPY's 33.7% and QQQ's 35.1%. It
  also does not meet the aggressive mandate: 13.3% realized vol, nowhere near the 40-60%
  target. Beating QQQ on return is the bar for the next champion.
- **Why it is not more aggressive.** Gross weight is capped at 1.0 because orders are
  MarketOnOpen and a rotation has both legs outstanding at once. At gross 1.3 LEAN rejected
  3,004 of 3,690 rebalances for buying power. Leverage is therefore limited to what is inside
  the 3x ETFs, and the vol target is inert - the gross cap binds first, which is why
  `target_vol` and `target_exposure` shocks move nothing. The risk control that actually
  works is the crisis filter plus the drawdown breaker.
- **Next.** I-1: the paper runner against IBKR, importing `signals.py` unchanged. The
  execution constraint above is the thing to fix to raise exposure, and it is an execution
  problem, not a signal problem.

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
