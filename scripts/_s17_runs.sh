#!/usr/bin/env bash
# S-17: what does the daily champion's 24.404% assume about execution, and what does each
# assumption cost?
#
# Two omissions, both found by reading the engine and the live log rather than by tuning:
#
#  1. SPREAD. `DefaultBrokerageModel.GetSlippageModel` returns `NullSlippageModel.Instance`
#     and `InteractiveBrokersBrokerageModel` does not override it, so every LEAN run in this
#     repository has filled at the exact opening print. Commission is charged, spread and
#     impact are not. The champion places 4,735 orders over 14 years and S-13 measured that
#     ~63% of them are return-neutral in backtest - each of those still pays a spread live.
#     `EquityFillModel.MarketOnOpenFill` does apply a slippage model (+slip on a buy, -slip
#     on a sell), so `S1_SLIPPAGE_BPS` prices it directly.
#
#  2. FILL TIMING. The backtest decides on the close of day D and fills at the open of D+1:
#     one overnight gap. `scripts/paper_trade.py` sends MKT orders at 15:45 ET off the last
#     *complete* yfinance daily bar, and the 2026-09-09/2026-09-10 live logs show that bar
#     can be D-1's close (XLK's sizing `ref_price` is byte-identical on both sessions), so
#     the deployed path can carry a whole extra session of staleness. `S1_SIGNAL_LAG` prices
#     that, holding the sizing price current so the effect is signal staleness alone.
#
# Both knobs default to 0 and the control must reproduce
# OrderListHash 5246804e17a67af90028ffceead7d3b3. Nothing deployed changes.
# Read the output with scripts/sweep_s17.py.
set -u
cd "$(dirname "$0")/.."

run () {
  name="$1"; shift
  tag="$1"; shift
  echo "=== $name ==="
  env "$@" py -3.11 scripts/backtest.py s1_momo --quiet --tag "$tag" 2>&1 | tail -20
}

# 1. The spread dial on the shipped champion. 1 bp is the floor for a penny spread on a
#    $100 ETF; A-5 part 2 measured +2.89 bps on the intraday sleeve's single-name fills, and
#    the daily sleeve trades the most liquid ETFs in the market at the opening auction, so
#    the honest bracket is 1-5 bps with 10 as the pessimistic bound.
run sl1  "S-17 spread: champion + 1 bp constant slippage per fill"  S1_SLIPPAGE_BPS=1
run sl2  "S-17 spread: champion + 2 bp constant slippage per fill"  S1_SLIPPAGE_BPS=2
run sl5  "S-17 spread: champion + 5 bp constant slippage per fill"  S1_SLIPPAGE_BPS=5
run sl10 "S-17 spread: champion + 10 bp constant slippage per fill" S1_SLIPPAGE_BPS=10

# 2. The fill-timing convention: one extra session between the last close the signal reads
#    and the open it fills at, which is what the live runner can do when yfinance has not
#    yet published the current session's bar.
run lag1 "S-17 lag: champion + 1 session of signal staleness (decide off D-1 close, fill at D+1 open)" S1_SIGNAL_LAG=1
run lag1_sl2 "S-17 lag+spread: champion + 1 session of signal staleness and 2 bp slippage" S1_SIGNAL_LAG=1 S1_SLIPPAGE_BPS=2

# 3. Does the spread re-rank S-16's parked frontier? Those cells trade MORE orders (5,128
#    and 5,283 against 4,735) but hold unlevered ETFs, so the charge is not neutral between
#    them and the champion. Their 0 bp rows already exist from S-16.
run eg75_sl2 "S-17 spread on S-16 (e+g) budget 0.75: proxies off, overlay off, 2 bp slippage" S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0 S1_SLIPPAGE_BPS=2
run eg80_sl2 "S-17 spread on S-16 (e+g) budget 0.80: proxies off, overlay off, 2 bp slippage" S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0 S1_MARGIN_BUDGET=0.80 S1_SLIPPAGE_BPS=2

# 4. The owner's open no-trade-band question, now decidable. S-13 swept the band with zero
#    spread and found CAR flat (24.40 / 24.34 / 24.47 at 0.01 / 0.03 / 0.08) while orders
#    fell 4,735 -> 2,737 -> 1,727, and left the call to the owner precisely because the
#    saving is a spread the backtest does not model. Charge the spread and the sweep decides.
run band03_sl2 "S-17 band at 2 bp slippage: min_order_value 0.03" S1_MIN_ORDER_VALUE=0.03 S1_SLIPPAGE_BPS=2
run band08_sl2 "S-17 band at 2 bp slippage: min_order_value 0.08" S1_MIN_ORDER_VALUE=0.08 S1_SLIPPAGE_BPS=2

echo "=== ALL DONE ==="
