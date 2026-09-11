#!/usr/bin/env bash
# S-20: give the regime gate a second off-state.
#
# `signals.risk_on` switches the whole book off in a volatility crisis - 590 of 3,690
# sessions, 16.0%, in 29 episodes with a median length of 15 sessions. S-15 priced that
# switch and it stays: turning it off earns +2.02 CAR and costs 6.3 points of drawdown, so
# it is a drawdown instrument. What it has never had is anywhere to go. The off-state has
# been cash since S-1, and a volatility crisis is exactly the state in which Treasuries and
# gold are supposed to be bid.
#
# PRE-REGISTERED BEFORE ANY LEAN CELL RAN (the probe in scripts/sweep_s20.py --probe is a
# measurement of the *state*, not of the strategy, but it was run first and it is honest to
# say what it showed):
#
#   over the 590 risk-off sessions, held one session forward, bps/day and t against cash
#     TLT  +1.68 / t 0.35     IEF  +1.86 / 0.96     GLD  +9.92 / 2.20
#     SLV  +7.36 / 0.97       HYG  +0.92 / 0.26     SPY  +6.57 / 0.88
#   the shipped momentum blend picking among TLT/IEF/GLD: +5.35 / t 1.13
#   conditionality (risk-off minus risk-on) for the same three: +1.39 / +1.50 / +8.07,
#     t 0.28 / 0.73 / 1.66 - i.e. NOT clearly a crisis effect for any of them
#
# so the cells below are split into three classes and the write-up must keep them apart:
#
#   PRIMARY (the mechanism as designed, not chosen from the table): the shipped momentum
#     ranking run over a three-name defensive sleeve, same score, same absolute entry
#     floor, cash when nothing is trending.
#   A-PRIORI CONTROL: TLT alone, which is what a researcher would have written down before
#     seeing any of the above, and which the probe says is worth nothing.
#   POST-HOC: GLD alone. It is the probe's winner and it was chosen after looking. It is
#     run so the primary can be read against it, and it is NOT promotable on this evidence.
#
# PROMOTION RULE, fixed here: the primary cell must pass scripts/evaluate.py at 0 bp AND at
# 2 bp (S-18's same-cost-model rule), and must not lose the 2020-2026 out-of-sample half.
# Anything else is refused and written up as refused.
#
# Read the output with scripts/sweep_s20.py --report.
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
SLEEVE="S1_RISK_OFF_SLEEVE=TLT,IEF,GLD"

# The no-op: shipped defaults must still reproduce OrderListHash
# a6d6224ce9c70091e5bfa8e96f046bf3 (5,128 orders / 24.403% / 0.994 / 23.700% / $27,199.76).
run ctrl     "S-20 control: shipped defaults (off-state = cash), 0 bp"

# PRIMARY.
run defn     "S-20 defensive sleeve TLT/IEF/GLD, top 1, 0 bp"                  $SLEEVE
run defn2    "S-20 defensive sleeve TLT/IEF/GLD, top 1, 2 bp"                  $SLEEVE S1_SLIPPAGE_BPS=2

# A-PRIORI CONTROL and POST-HOC cell.
run tlt      "S-20 a-priori control: TLT alone as the off-state, 0 bp"         S1_RISK_OFF_SLEEVE=TLT
run gld      "S-20 post-hoc: GLD alone as the off-state, 0 bp"                 S1_RISK_OFF_SLEEVE=GLD

# Dose response on the only two dials the mechanism has. If the effect is real it should
# survive holding two defensive names instead of one, and it should scale with exposure.
run top2     "S-20 defensive sleeve, top 2 of 3, 0 bp"                         $SLEEVE S1_RISK_OFF_TOP_N=2
run half     "S-20 defensive sleeve, top 1 at half exposure, 0 bp"             $SLEEVE S1_RISK_OFF_EXPOSURE=0.5

# Halves for the primary. The champion's own halves at 0 bp already exist from S-18
# (IS 17.698 / 0.911 / 23.7, OOS 32.801 / 1.108 / 23.3) and are not re-run.
run defn_is  "S-20 defensive sleeve, IS 2012-2019, 0 bp"                       $SLEEVE $IS
run defn_oos "S-20 defensive sleeve, OOS 2020-2026, 0 bp"                      $SLEEVE $OOS

echo "=== ALL DONE ==="
