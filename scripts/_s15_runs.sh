#!/usr/bin/env bash
# S-15: attribute the champion's return to its parts. One LEAN run per cell, full period,
# every cell an environment override of the shipped algorithm (no deployed file changes).
set -u
cd "$(dirname "$0")/.."

run () {
  name="$1"; shift
  tag="$1"; shift
  echo "=== $name ==="
  env "$@" py -3.11 scripts/backtest.py s1_momo --quiet --tag "$tag" 2>&1 | tail -22
}

run a_noskill "S-15 attribution (a) no ranking: top_n=9, equal weights, entry gate off - the whole sleeve through the same regime filter, vol target, budget, overlay and levered proxies" S1_TOP_N=9 S1_WEIGHT_MODE=equal S1_MIN_MOMENTUM=-1e9
run b_noregime "S-15 attribution (b) regime filter off (regime_threshold=1e9), everything else the champion" S1_REGIME_THRESHOLD=1e9
run d_equal "S-15 attribution (d) allocation tilt off: weight_mode=equal, everything else the champion" S1_WEIGHT_MODE=equal
run e_noproxy "S-15 attribution (e) levered proxies off (S1_PROXY=off): the champion held in unlevered names" S1_PROXY=off
run g_nodd "S-15 attribution (g) drawdown overlay off (dd_halve=dd_flat=9.0), everything else the champion" S1_DD_HALVE=9.0 S1_DD_FLAT=9.0
run f_beta "S-15 attribution (f) no skill at all: top_n=9 equal weights, gate off, regime off, proxies off - the pool through the sizing machinery only" S1_TOP_N=9 S1_WEIGHT_MODE=equal S1_MIN_MOMENTUM=-1e9 S1_REGIME_THRESHOLD=1e9 S1_PROXY=off
echo "=== ALL DONE ==="
