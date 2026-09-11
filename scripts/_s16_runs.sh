#!/usr/bin/env bash
# S-16: is the champion's instrument leverage (the 3x proxies) the cheapest way to buy its
# volatility? S-15 cell (e) showed the same signal held in unlevered parents is better on
# every risk-adjusted measure and on fees for 1.28 points of CAR, and cell (g) showed the
# drawdown overlay is the only switch whose paired statistic is near-significant, with the
# sign against it. This runs the interaction S-15 never ran, then buys the lost exposure
# back with *account* leverage (margin_budget) instead of *instrument* leverage.
#
# Structural fact the cells are pricing: Reg-T charges 50% of notional for an ordinary ETF
# and IBKR marks a 3x ETF to 100%, so per unit of economic exposure the proxies cost 0.333
# of margin and the unlevered names 0.5. Gross therefore stops at 2 x budget unlevered and
# at 1 x budget levered - for three times the exposure.
#
# Every cell is an environment override of the shipped algorithm. Nothing deployed changes.
# Read the output with scripts/sweep_s16.py. Cells (e) and (g) at budget 0.75 are S-15's and
# are not re-run here.
set -u
cd "$(dirname "$0")/.."

run () {
  name="$1"; shift
  tag="$1"; shift
  echo "=== $name ==="
  env "$@" py -3.11 scripts/backtest.py s1_momo --quiet --tag "$tag" 2>&1 | tail -20
}

# 0. Control: the shipped champion, must reproduce OrderListHash 5246804e17a67af90028ffceead7d3b3.
run ctrl "S-16 control: shipped champion defaults (must reproduce OrderListHash 5246804e17a67af90028ffceead7d3b3)"

# 1. The interaction: both switches off at the unchanged budget. Unlevered names free 1.5
#    points of drawdown (S-15 e) and the overlay costs 1.59 CAR for 2.1 points (S-15 g).
run e_g "S-16 (e+g) levered proxies off AND drawdown overlay off, margin_budget unchanged at 0.75" S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0

# 2. The budget dial with both switches off: the freed risk bought back as account leverage.
#    0.82 is the cell that matches the champion's own realized volatility.
run e_g_b078 "S-16 (e+g) shelf: proxies off, overlay off, margin_budget 0.78" S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0 S1_MARGIN_BUDGET=0.78
run e_g_b080 "S-16 (e+g, budget 0.80) proxies off, overlay off, margin_budget 0.80 - the freed risk bought back with account leverage" S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0 S1_MARGIN_BUDGET=0.80
run e_g_b082 "S-16 (e+g) shelf: proxies off, overlay off, margin_budget 0.82" S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0 S1_MARGIN_BUDGET=0.82

# 3. The overlay shelf at the same budget: shipped 0.15/0.25 -> widened 0.20/0.30 -> off,
#    so "off" cannot be a cliff dressed up as a result.
run e_b080 "S-16 (e only, budget 0.80) proxies off, shipped overlay 0.15/0.25 kept, margin_budget 0.80" S1_PROXY=off S1_MARGIN_BUDGET=0.80
run e_w_b080 "S-16 (e+dd wide, budget 0.80) proxies off, overlay widened to 0.20/0.30, margin_budget 0.80 - the shelf between shipped overlay and off" S1_PROXY=off S1_DD_HALVE=0.20 S1_DD_FLAT=0.30 S1_MARGIN_BUDGET=0.80

# 4. Sub-periods of the leading cell, on the halves S-12 was promoted on.
run e_g_b080_is "S-16 (e+g, budget 0.80) IS 2012-2019" S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0 S1_MARGIN_BUDGET=0.80 S1_START=2012-01-03 S1_END=2019-12-31
run e_g_b080_oos "S-16 (e+g, budget 0.80) OOS 2020-2026" S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0 S1_MARGIN_BUDGET=0.80 S1_START=2020-01-02 S1_END=2026-09-04

echo "=== ALL DONE ==="
