#!/usr/bin/env bash
# S-18: promote S-16's (e+g) cell at the unchanged 0.75 margin budget, or refuse it.
#
# The cell is `S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0`: the same signal held in
# unlevered parents, no drawdown breaker, margin budget untouched. S-16 measured it at
# 24.403% against the champion's 24.404% - a dead heat refused by 0.001 CAR points - and
# S-17 showed that margin exists only at exactly zero spread, which is LEAN's default and
# not a choice (`DefaultBrokerageModel.GetSlippageModel` returns `NullSlippageModel`).
#
# S-18 supplies the three pieces S-17 named as missing, each a run and not a judgement:
#
#  (a) the in-sample 2012-2019 and out-of-sample 2020-2026 halves at this configuration,
#      at 0 bp AND at 2 bp, against the champion at the same spread on the same halves.
#      S-16 only produced halves for the budget-0.80 variant, and S-12 promoted the
#      champion on these two windows, so this is the like-for-like test.
#  (b) the like-for-like full-period comparison (already in the ledger from S-16/S-17)
#      is what `evaluate.py` must judge on; the halves decide whether the edge is one
#      regime deep, which is what killed S-12's allocation tilt in the S-15 attribution.
#  (c) the no-trade band on the *promoted* cell rather than on the champion: S-17 found
#      `min_order_value` 0.03 worth +0.57 CAR at 2 bp on the champion, and S-13's warning
#      that its fine structure is path luck still stands, so this is measured, not fitted.
#
# Full-period rows that already exist and are NOT re-run here:
#   champion  0 bp  24.404 / 0.921 / 25.100 / $45,695   (S-16 ctrl, S-17 ctrl)
#   champion  2 bp  22.926 / 0.865 / 29.200             (S-17 sl2)
#   (e+g)     0 bp  24.403 / 0.994 / 23.700 / $27.2k    (S-16 e_g)
#   (e+g)     2 bp  23.068 / 0.938 / 25.000 / $24.9k    (S-17 eg75_sl2)
#   (e+g)     1 bp  23.735 / 0.966 / 24.300             (S-17)
#
# Read the output with scripts/sweep_s18.py.
set -u
cd "$(dirname "$0")/.."

# One LEAN backtest runs for 2-5 minutes, so the whole file is longer than a single
# foreground command may take here. Pass cell names as arguments to run a subset; with no
# arguments every cell runs in order.
WANT="${*:-all}"

run () {
  name="$1"; shift
  tag="$1"; shift
  case " $WANT " in *" all "*|*" $name "*) ;; *) return 0 ;; esac
  echo "=== $name ==="
  env "$@" py -3.11 scripts/backtest.py s1_momo --quiet --tag "$tag" 2>&1 | tail -20
}

EG="S1_PROXY=off S1_DD_HALVE=9.0 S1_DD_FLAT=9.0"
IS="S1_START=2012-01-03 S1_END=2019-12-31"
OOS="S1_START=2020-01-02 S1_END=2026-09-04"

# (a) The halves, candidate and champion, at both spreads. The champion's 0 bp halves are
#     S-12's promotion runs (IS 19.18% / 0.884 / 25.1%, OOS 30.86% / 0.985 / 22.6%) and are
#     not re-run; its 2 bp halves have never existed and are the missing control.
run cand_is_sl0  "S-18 (e+g) budget 0.75 IS 2012-2019 at 0 bp"  $EG $IS
run cand_oos_sl0 "S-18 (e+g) budget 0.75 OOS 2020-2026 at 0 bp" $EG $OOS
run cand_is_sl2  "S-18 (e+g) budget 0.75 IS 2012-2019 at 2 bp"  $EG $IS  S1_SLIPPAGE_BPS=2
run cand_oos_sl2 "S-18 (e+g) budget 0.75 OOS 2020-2026 at 2 bp" $EG $OOS S1_SLIPPAGE_BPS=2
run champ_is_sl2  "S-18 champion IS 2012-2019 at 2 bp"  $IS  S1_SLIPPAGE_BPS=2
run champ_oos_sl2 "S-18 champion OOS 2020-2026 at 2 bp" $OOS S1_SLIPPAGE_BPS=2

# (c) The band on the candidate, full period, both spreads. S-17 measured it on the
#     champion; a band interacts with turnover and the candidate trades a different book.
run cand_band03_sl2 "S-18 (e+g) budget 0.75 + min_order_value 0.03 at 2 bp" $EG S1_MIN_ORDER_VALUE=0.03 S1_SLIPPAGE_BPS=2
run cand_band03_sl0 "S-18 (e+g) budget 0.75 + min_order_value 0.03 at 0 bp" $EG S1_MIN_ORDER_VALUE=0.03

echo "=== ALL DONE ==="
