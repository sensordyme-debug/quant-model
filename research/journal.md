# Research journal

Newest entry first. Each entry: what was tried, why, the result, the decision, the next step.

## 2026-09-08 - S-7 beat buy-and-hold: two levers rejected, one is a mirage

- **What.** The three S-7 candidates for beating QQQ's 19.9% CAR, tested on both sub-periods
  with `scripts/sweep_s1.py --mode s7`: momentum-proportional weighting, a wider `top_n`, and
  widening the ranking sleeve to the 50 megacaps D-1 put on disk. `signals.py` gained two
  parameters for it - `rank_universe` and `weight_mode` (`equal` / `rank` / `momentum`) - and
  `main.py` gained `S1_SLEEVE` and `S1_WEIGHT_MODE`.
- **Why.** S-1 clears SPY (18.1% vs 15.0%) but not QQQ, and the backlog named these three.

### 1. Momentum-proportional weighting loses, on both halves

| weight_mode | IS CAR | OOS CAR | full CAR | full Sharpe | full MaxDD |
| --- | --- | --- | --- | --- | --- |
| equal (shipped) | 16.3% | 21.5% | **18.7%** | **0.97** | 23.2% |
| rank | 12.1% | 20.2% | 15.8% | 0.81 | 24.4% |
| momentum | 11.6% | 21.5% | 16.1% | 0.83 | 25.9% |

Concentration costs 2.6-2.9 points of CAR and ~0.15 Sharpe, and it is *in-sample* that it
loses most, so this is not a regime accident. Rejected; `weight_mode` stays `equal`.

### 2. top_n=3 survives, but 5-6 is the interesting neighbour

| top_n | IS CAR | OOS CAR | full CAR | full Sharpe | full MaxDD | vol |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 10.8% | 15.9% | 13.2% | 0.69 | 24.4% | 21.4% |
| 3 | 16.3% | 21.5% | **18.7%** | 0.97 | 23.2% | 19.8% |
| 4 | 15.4% | 19.6% | 17.3% | 0.93 | 22.3% | 19.1% |
| 5 | 13.9% | 21.1% | 17.2% | 0.94 | 22.1% | 18.7% |
| 6 | 14.7% | 20.8% | 17.5% | **0.97** | **22.0%** | 18.4% |

The earlier "top_n=3 is a local peak" caution is only half right: 3 wins on return, but the
curve from 4 to 6 is flat and monotonically *cheaper* in drawdown and vol (OOS drawdown falls
16.7% at top_n=6 against 23.2% at 3, with equal Sharpe). No change to the champion, but this
is a lead for S-8: the binding constraint there is the 35% drawdown limit, and a wider book
buys drawdown headroom that the margin budget could then spend on size.

### 3. The wide sleeve is a survivorship mirage, and the harness could not see it

Adding the 50 megacaps to the ranking sleeve produces the best number this repo has ever
printed. LEAN, run `20260908T192552Z`, `S1_SLEEVE=wide S1_TOP_N=5`:

| | CAR | Sharpe | MaxDD | Orders | Fees | PSR |
| --- | --- | --- | --- | --- | --- | --- |
| wide sleeve | 43.9% | 1.19 | 32.2% | 7,830 | $243,278 | 52.5% |
| champion (ETF-9) | 18.1% | 0.69 | 25.2% | 3,410 | $38,630 | 5.1% |

`scripts/evaluate.py --candidate` said **BEATS champion**: 32.2% drawdown is inside the 35%
limit, 7,830 orders clears 30, and it wins on both must-beat metrics. It is still not real.
`MEGACAP_SLEEVE` is the megacap list *as of 2026*, so ranking it back to 2012 knows in advance
which fifty companies were going to survive and win. The two obvious defences both fail:

* **The IS/OOS split does not detect it.** IS 50.2% CAR vs OOS 54.3% - the halves agree,
  because the hindsight is in universe construction and is therefore spread evenly across
  the whole sample rather than fitted to one end of it.
* **It is not a late-IPO artifact.** Only 4 of the 50 (META, ABBV, NOW, UBER) listed after
  2012-01-03, and dropping them changes almost nothing (44.4% -> 41.8% CAR in the sweep,
  and 22.8% -> 22.4% for the passive basket).
  The bias is in *which names were on the list at all*.

The control that does work is holding the same universe passively
(`scripts/sweep_s1.py --mode s7bias`, 2012-2026):

| | CAR | Sharpe | Vol |
| --- | --- | --- | --- |
| SPY buy & hold | 15.0% | 0.93 | 16.5% |
| EW 50 megacaps (2026 list), no skill at all | **22.8%** | **1.27** | 17.4% |
| momentum top_n=5 on that same sleeve | 44.4% | 1.37 | 30.3% |

So simply *owning* the 2026 megacap list from 2012, equal weighted, beats SPY by 7.8 points
of annual return with a higher Sharpe than the strategy. Against its own basket the signal
adds +21.6% CAR at 1.74x the vol - which is very close to what levering the basket would
give - and only +0.10 Sharpe. Essentially all of the headline uplift is the universe and the
leverage; almost none of it is the ranking.

- **Decision.** **No promotion**, and the champion is unchanged. Rather than rely on
  remembering why, `evaluate.py` now refuses to promote any run whose tag contains
  `not promotable`, and the S-7 run is tagged that way - a later session reading the ledger
  cold would otherwise find a run that passes every statistical rule. The new
  `rank_universe` / `weight_mode` parameters ship defaulted to the current behaviour: the
  control run `20260908T192208Z` reproduces `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`,
  byte-identical to the champion's order list, so the refactor changed nothing that trades.
- **What S-7 actually needs.** A point-in-time universe: membership decided from information
  available on each rebalance date (index membership as of that date, or a rolling
  dollar-volume rank recomputed daily from bars already on disk), not a list downloaded in
  2026. The second option needs no new data source and is now backlog **D-3**. Until then the
  answer to "can a wider sleeve beat QQQ" is unknown, not yes.
- **Next.** D-3, which unblocks S-7 properly; S-8 can start from top_n=5-6 for drawdown room.
  I-1 remains the deadline gate and is still blocked on IB Gateway (`research/BLOCKERS.md`).

## 2026-09-08 - S-6 margin-budget sizing (new champion, exposure 1.27x -> 1.63x)

- **Hypothesis.** S-1's size was limited by a flat `max_gross_weight = 1.0`, which was never
  a risk preference - it was a workaround for LEAN charging un-netted initial margin on both
  legs of a MarketOnOpen rotation. With that execution problem already fixed (netted share
  deltas, sells first, daily-bar rebalance), replacing the flat cap with the constraint a
  broker actually enforces should buy materially more exposure at the same risk.
- **What.** `signals.py` now caps on `sum(weight_i * MARGIN_REQ[i]) <= margin_budget`, where
  `MARGIN_REQ` is Reg-T 50% for an ordinary ETF and 100% for a 3x ETF (IBKR multiplies the
  requirement by the leverage factor). `max_gross_weight` demotes to a hard notional ceiling
  at 2.0. `main.py` audits realized initial margin daily alongside gross. `sweep_s1.py`
  gained `--mode margin`. `paper_trade.py` gained an independent `MAX_MARGIN_USED = 1.0`
  backstop that aborts before sending orders, so a signal bug cannot silently place size.
- **Why this is not just "turn the leverage up".** The cap is asymmetric in exactly the way
  a real account is: three unlevered winners can now run at 1.5x gross, while three 3x ETFs
  are still held to 0.75x gross. The old flat cap punished the *safe* basket and let the
  levered one through, which is why mean effective exposure sat at 1.27x.

### Result (LEAN, `20260908T182554Z`, 2012-01-03 .. 2026-09-04)

| Window | CAR | Sharpe | MaxDD | Orders | Fees |
| --- | --- | --- | --- | --- | --- |
| Full 2012-2026 | **18.1%** | **0.69** | 25.2% | 3,410 | $38,630 |
| IS 2012-2019 | 13.5% | 0.64 | 25.2% | 1,776 | $22,062 |
| OOS 2020-2026 | 23.8% | 0.76 | 24.8% | 1,637 | $6,348 |

Against the outgoing champion: CAR 13.7% -> 18.1%, Sharpe 0.60 -> 0.69, drawdown 23.6% ->
25.2%, mean effective exposure 1.27x -> 1.63x, realized vol 13.3% -> 16.5%. Both sub-periods
improve, and out-of-sample is again the stronger half. Audit: max initial margin actually
carried 0.793 against a 0.75 budget (the 6% overshoot is intraday drift between the decision
close and the next open, not a sizing error), max gross 1.536 against the 2.0 ceiling.

- **Where the budget was set, and why not higher.** `--mode margin` shows return flat above
  budget 1.0 - `scale_cap = 2.0` binds first, so budgets of 1.0, 1.25, 1.5 and 2.0 all land
  on the same book. The full Reg-T budget of 1.0 *does* hit S-6's stated 2x target (LEAN:
  2.07x mean exposure, CAR 20.4%, Sharpe 0.67) but posts a **35.4% drawdown, over the 35%
  limit in `champion.json`**, so it is not promotable. 0.75 is that limit respected with a
  buffer, not a fitted optimum: a book sitting at a full budget has zero excess liquidity and
  any adverse move is a margin call. Both runs are in the ledger; the 1.0 result is the
  measured edge of the risk limit, recorded so the next iteration does not re-derive it.
- **Decision.** Promoted through `scripts/evaluate.py` (3,410 orders, drawdown 25.2% < 35%,
  beats the champion on both Sharpe and CAR). The default `margin_budget = 0.75` is set in
  the code, not passed by environment variable: a confirmation run with no env produced the
  identical `OrderListHash 9f58b37cc2656b647ec88a5124daf02d`, so the champion reproduces from
  a clean checkout, and `paper_trade.py --mock --dry-run` now plans the same 1.5x gross book.
- **Honest limits.** 16.5% realized vol is still far short of the 40-60% mandate; the binding
  constraint has moved from the gross cap to `scale_cap` and the drawdown limit, which is a
  risk-budget conversation, not an execution bug. Fees grew $27k -> $39k on 12% more orders.
  It now beats SPY on return (18.1% vs 15.0%) but still not QQQ (19.9%), so S-7 stays open.
- **Next.** I-1 remains the deadline gate and is still blocked on IB Gateway being logged in.

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
