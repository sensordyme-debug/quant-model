#!/usr/bin/env bash
# S-19: re-price the deployed daily runner's clock on the PROMOTED champion, and put an
# exact number where S-17 could only put an upper bound.
#
# Two things make S-17's -4.75 CAR stale rather than wrong:
#
#  (1) It was measured on the S-12 champion - 3x proxies, drawdown breaker, 2.25x economic
#      exposure. S-18 retired both. The book the runner actually trades today is the
#      unlevered one, and a staleness cost is a return cost, so it does not have to be the
#      same size on a book carrying two thirds of the exposure.
#  (2) `S1_SIGNAL_LAG=1` is an upper bound by construction, not the live convention:
#      it hides the last close from the signal AND still fills at the next open, so it is
#      one overnight gap staler than the deployed path (which fills at the close of the
#      same session it decided in). The exact convention cannot be expressed with daily
#      bars in LEAN - a bar for D arrives stamped D 16:00, so an order placed then cannot
#      fill at D's close - and is priced instead by scripts/sweep_s19.py, which runs the
#      shared signals.py through a book that fills wherever it is told.
#
# The ladder below (lag 0 / 1 / 2) is what makes the pandas number checkable: the LEAN cost
# per session of staleness has to bracket it.
#
# Read the output with scripts/sweep_s19.py --lean.
set -u
cd "$(dirname "$0")/.."

WANT="${*:-all}"

run () {
  name="$1"; shift
  tag="$1"; shift
  case " $WANT " in *" all "*|*" $name "*) ;; *) return 0 ;; esac
  echo "=== $name ==="
  env "$@" py -3.11 scripts/backtest.py s1_momo --quiet --tag "$tag" 2>&1 | tail -20
}

IS="S1_START=2012-01-03 S1_END=2019-12-31"
OOS="S1_START=2020-01-02 S1_END=2026-09-04"

# The control: shipped defaults must still reproduce OrderListHash
# a6d6224ce9c70091e5bfa8e96f046bf3 (5,128 orders / 24.403% / 0.994 / 23.700% / $27,199.76).
run ctrl      "S-19 control: shipped defaults, promoted champion, 0 bp"

# The staleness ladder on the promoted book.
run lag1_sl0  "S-19 signal lag 1 session on the promoted champion, 0 bp"         S1_SIGNAL_LAG=1
run lag2_sl0  "S-19 signal lag 2 sessions on the promoted champion, 0 bp"        S1_SIGNAL_LAG=2
run lag1_sl2  "S-19 signal lag 1 session on the promoted champion, 2 bp"         S1_SIGNAL_LAG=1 S1_SLIPPAGE_BPS=2

# Is the clock cost one regime deep? The champion's own halves at 0 bp already exist from
# S-18 (IS 17.698 / 0.911 / 23.7, OOS 32.801 / 1.108 / 23.3) and are not re-run.
run lag1_is   "S-19 signal lag 1, IS 2012-2019, 0 bp"                            S1_SIGNAL_LAG=1 $IS
run lag1_oos  "S-19 signal lag 1, OOS 2020-2026, 0 bp"                           S1_SIGNAL_LAG=1 $OOS

echo "=== ALL DONE ==="
