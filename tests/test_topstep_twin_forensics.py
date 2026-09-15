"""Forensic validation of the Topstep 50K digital twin. Every number here was hand-worked.

WHY THIS FILE EXISTS
--------------------
The twin is the engine's objective function. Pass probability, payout count and the funded
buffer all come out of it, and every downstream verdict - fundable or not - inherits its
arithmetic. It was also the least-verified component in the engine: 118 behavioural unit
tests across `test_qb_twin.py` and `test_qb_topstep.py`, but no end-to-end scenario whose
expected balances were computed in advance, and no second opinion.

Three things are done here that those files do not do.

    A. TWENTY KNOWN-ANSWER SCENARIOS. Each one states the arithmetic in its own docstring -
       the levels, the marks, the settlement - and asserts the full result. Every expected
       value below was worked out from the rulebook constants BEFORE it was run. Nothing is
       a recorded output.

    B. THE PATH-DEPENDENCE ATTACK. Topstep tests the Maximum Loss Limit intraday, so two
       session sequences with identical daily P&L must be able to end differently. A twin
       that answered from the P&L series alone would be catastrophically optimistic and
       would still pass every terminal-value test ever written for it. The attack proves the
       twin is genuinely path-sensitive, proves the sensitivity runs the right way, and
       reconciles it against `research.topstep_reference` - a second implementation written
       to be structurally unlike the first.

    C. EQUITY-PATH GRANULARITY. The twin can only see the marks it is handed. The study at
       the bottom measures what coarse marks cost in detection and pins the direction of the
       error: coarser is always more optimistic, never less. `docs/TOPSTEP_TWIN_AUDIT.md`
       carries the numbers.

THE CONSTANTS, HAND-CHECKED
---------------------------
Everything below is the published 50K row. They are asserted in `test_the_constants_this_
file_hand_computes_against` so that a rulebook correction fails HERE, at the arithmetic that
depends on it, rather than silently changing every expectation in the file.

    Combine    start $50,000   MLL $2,000 trailing, locking at $50,000   target $3,000
               minimum trading days 0     consistency 55% of total profit
    XFA        start $0        MLL $2,000 trailing, locking at $0
               5 winning days of $150+    payout min($125 floor, 50% of balance, $2,000 cap)
    DLL        $1,000, optional
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme import twin as tw
from quant_brain.research import topstep_reference as tr

MONDAY = dt.date(2026, 1, 5)

#: How the fuzz sections are sized. Large enough that a one-in-a-thousand disagreement shows
#: up, small enough that the suite stays a gate rather than a batch job.
FUZZ_PAIRS = 6000


def sessions(spec, start: dt.date = MONDAY) -> list[tw.TwinDay]:
    """`spec` is a list of (pnl, path) laid out on consecutive weekdays."""
    out, day = [], start
    for pnl, path in spec:
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        out.append(tw.TwinDay(day=day, pnl=float(pnl),
                              path=tuple(float(m) for m in path)))
        day += dt.timedelta(days=1)
    return out


def simple(pnls, start: dt.date = MONDAY) -> list[tw.TwinDay]:
    """Sessions whose only mark is the close: no excursion beyond the settled P&L."""
    return sessions([(p, (p,)) for p in pnls], start)


def run(spec, **kw) -> tw.TwinResult:
    kw.setdefault("payout_policy", tw.NEVER)
    return tw.TopstepTwin(50_000, **kw).run(sessions(spec))


def test_the_constants_this_file_hand_computes_against():
    """Every expectation below is arithmetic on these. If one moves, this fails first."""
    assert ts.MLL[50_000].value == 2_000.0
    assert ts.DLL_OPTIONAL[50_000].value == 1_000.0
    assert ts.COMBINE_PROFIT_TARGET[50_000].value == 3_000.0
    assert ts.COMBINE_MIN_DAYS.value == 0
    assert ts.CONSISTENCY_READINGS[ts.DEFAULT_READING][:2] == (0.55, "total")
    assert ts.XFA_WINNING_DAYS.value == 5
    assert ts.XFA_WINNING_DAY_MIN.value == 150.0
    assert ts.XFA_BALANCE_SHARE.value == 0.5
    assert ts.XFA_STANDARD_CAP_BY_SIZE[50_000].value == 2_000.0
    assert ts.PAYOUT_MINIMUM.value == 125.0
    assert ts.COMBINE_COST[50_000].value == 49.0

    combine = ts.combine(50_000)
    assert (combine.starting_balance, combine.trailing_locks_at) == (50_000.0, 50_000.0)
    xfa = ts.express_funded(50_000)
    assert (xfa.starting_balance, xfa.trailing_locks_at) == (0.0, 0.0)


# ======================================================================================
# A. TWENTY KNOWN-ANSWER SCENARIOS
# ======================================================================================
#
# Common opening state, used by every scenario below and written out once:
#
#     balance 50,000    peak end-of-day balance 50,000    MLL 50,000 - 2,000 = 48,000
#     room to the limit 2,000
#
# A path element is UNREALIZED P&L against the balance the day opened at, so mark `m` is
# tested as equity = opening balance + m. The limit is fixed for the whole session: it
# follows the end-of-day balance and nothing else.

def test_s01_a_normal_winning_day_moves_the_balance_and_the_limit_together():
    """+$500, dipping to -$200 first.

        marks   50,000 - 200 = 49,800 > 48,000        50,000 + 500 = 50,500 > 48,000
        settle  balance 50,500, peak 50,500, MLL 50,500 - 2,000 = 48,500
        room    50,500 - 48,500 = 2,000, unchanged - the limit followed the balance up
    """
    r = run([(500, (-200, 500))])
    assert r.terminal is ts.TopstepStage.TRADING_COMBINE
    assert r.final_balance == 50_500.0
    assert r.min_buffer == 2_000.0
    assert r.breach_day is None


def test_s02_the_limit_trails_the_close_not_the_intraday_high():
    """The rule that separates Topstep from an intraday-trailing firm.

        day 1  +$100 after touching +$900.
               peak end-of-day 50,100 -> MLL 48,100.
               Had the limit followed the intraday high it would sit at 50,900 - 2,000
               = 48,900.
        day 2  -$1,200. Equity 50,100 - 1,200 = 48,900.
               Against the real limit 48,900 > 48,100: survives with $800 of room.
               Against an intraday-trailed limit 48,900 <= 48,900: dead.

    The day-2 loss is chosen to land exactly on the wrong answer, so the test fails if the
    peak is ever taken from a mark instead of from a settled balance.
    """
    r = run([(100, (900, 100)), (-1200, (-1200,))])
    assert r.terminal is ts.TopstepStage.TRADING_COMBINE
    assert r.final_balance == 48_900.0
    assert r.min_buffer == 800.0


def test_s03_an_intraday_touch_kills_an_account_that_closes_flat():
    """Down $2,100 mid-session, back to unchanged by the bell.

        mark    50,000 - 2,100 = 47,900 <= 48,000   ->  liquidated on the touch

    The close is 50,000, a perfectly healthy balance. An end-of-day-only model reports this
    session as uneventful, which is the single most expensive mistake this twin can make.
    """
    r = run([(0, (-2100, 0))])
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert r.breach_day == MONDAY
    assert "intraday equity 47,900 reached the MLL 48,000" in r.breach_reason


def test_s04_the_close_is_tested_even_when_the_supplied_path_never_reaches_it():
    """-$2,000 on the day, with only one mark supplied at -$500.

        mark    49,500 > 48,000, survives the intraday test
        settle  balance 48,000 <= 48,000  ->  liquidated at the close

    A supplied path is a PREFIX of the session, not the whole of it: `worst_mark` and
    `robustness.intraday_attribution` both complete it to the close, and settlement tests
    the close against the same limit the marks were tested against. So a coarse path can
    misattribute WHEN the account died - here it reads as end-of-day rather than intraday -
    but it cannot let the account survive a fatal close. Section C measures the cost of that
    misattribution.
    """
    r = run([(-2000, (-500,))])
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert "end-of-day balance 48,000 reached the MLL 48,000" in r.breach_reason


def test_s05_the_combine_limit_stops_climbing_at_the_starting_balance():
    """Three wins that never reach the target, then a loss that lands one dollar clear.

        +1,400  balance 51,400  peak 51,400  MLL 49,400
        +1,400  balance 52,800  peak 52,800  MLL min(50,800, 50,000) = 50,000   LOCKED
          +100  balance 52,900  peak 52,900  MLL min(50,900, 50,000) = 50,000   still
        -2,899  equity 52,900 - 2,899 = 50,001 > 50,000, survives by one dollar

    Total profit is 2,900, below the 3,000 target, so the Combine is not passed and the
    account is still in it. The final dollar of room is what pins the lock level: if the
    limit had kept trailing it would sit at 50,900 and this day would be fatal.
    """
    r = run([(1400, (1400,)), (1400, (1400,)), (100, (100,)), (-2899, (-2899,))])
    assert r.terminal is ts.TopstepStage.TRADING_COMBINE
    assert r.final_balance == 50_001.0
    assert r.min_buffer == 1.0


def test_s06_and_one_dollar_below_the_lock_is_fatal():
    """The same path plus a -$1 day. Equity 50,001 - 1 = 50,000 <= 50,000.

    Together with S05 this brackets the lock level to the dollar from both sides.
    """
    r = run([(1400, (1400,)), (1400, (1400,)), (100, (100,)), (-2899, (-2899,)),
             (-1, (-1,))])
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert "intraday equity 50,000 reached the MLL 50,000" in r.breach_reason


def test_s07_three_equal_thousand_dollar_days_pass_the_combine():
    """+1,000 three times.

        total profit 3,000 >= the 3,000 target
        best day 1,000 is 33.3% of 3,000, inside the 55% consistency limit
        minimum trading days is 0, so three clears it

    Passing rebuilds the account as an Express Funded Account at $0 with the same $2,000 of
    room - which is why the final balance is 0 and not 53,000.
    """
    r = run([(1000, (1000,))] * 3)
    assert r.terminal is ts.TopstepStage.EXPRESS_FUNDED
    assert r.combine_days == 3
    assert r.final_balance == 0.0
    assert r.reached_funding is True
    assert r.min_buffer_funded == 2_000.0


def test_s08_the_consistency_rule_means_the_same_three_thousand_does_not_pass():
    """+2,000, +500, +500. The same $3,000, earned lopsidedly.

        best day 2,000 is 66.7% of the 3,000 total, above the 55% limit
        so the target rises to 2,000 / 0.55 = 3,636.36
        profit 3,000 < 3,636.36  ->  still in the Combine
    """
    r = run([(2000, (2000,)), (500, (500,)), (500, (500,))])
    assert r.terminal is ts.TopstepStage.TRADING_COMBINE
    assert r.combine_days is None
    assert r.final_balance == 53_000.0
    assert r.reached_funding is False


def test_s09_trading_on_past_the_raised_target_passes():
    """S08 plus a +$700 day.

        total 3,700, best day 2,000 -> 2,000 / 3,700 = 54.05%, now inside 55%
        so the target falls back to the base 3,000 and 3,700 clears it
    """
    r = run([(2000, (2000,)), (500, (500,)), (500, (500,)), (700, (700,))])
    assert r.terminal is ts.TopstepStage.EXPRESS_FUNDED
    assert r.combine_days == 4
    assert r.final_balance == 0.0


def test_s10_the_funded_account_opens_at_zero_with_the_same_two_thousand_of_room():
    """Pass in three days, then lose $1,999 on the first funded session.

        XFA balance 0, peak 0, MLL min(0 - 2,000, 0) = -2,000
        equity -1,999 > -2,000: survives with one dollar of room
    """
    r = run([(1000, (1000,))] * 3 + [(-1999, (-1999,))])
    assert r.terminal is ts.TopstepStage.EXPRESS_FUNDED
    assert r.final_balance == -1_999.0
    assert r.min_buffer_funded == 1.0


def test_s11_and_the_two_thousandth_dollar_is_fatal():
    """One more dollar: equity -2,000 <= -2,000. The funded account is gone."""
    r = run([(1000, (1000,))] * 3 + [(-1999, (-1999,)), (-1, (-1,))])
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert r.reached_funding is True
    assert "intraday equity -2,000 reached the MLL -2,000" in r.breach_reason


def test_s12_a_funded_account_is_never_re_bought_even_with_attempts_left():
    """The same path with three Combine attempts allowed.

    Attempts buy another EVALUATION. A liquidated funded account is not an evaluation, so
    the count stays at one and the path ends. Getting this wrong would let the twin report
    a trader who lost a funded account simply starting again for a $49 fee.
    """
    r = run([(1000, (1000,))] * 3 + [(-1999, (-1999,)), (-1, (-1,))],
            max_combine_attempts=3)
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert r.combine_attempts == 1


def test_s13_a_failed_combine_buys_another_one_and_another_fee():
    """Blow up on day 1, then pass on days 2-4 with two attempts allowed and a $49 fee.

        day 1   -2,100 intraday: 47,900 <= 48,000, liquidated, attempt 2 begins at 50,000
        days 2-4  +1,000 each: profit 3,000, best day 33.3% - passed
        combine_days counts from the START OF THE ATTEMPT: day 4 - 1 = 3
        fees 2 x 49 = 98

    `breach_day` still records the first attempt's liquidation even though the path ends
    funded. It is the last breach seen, not a statement about the terminal state.
    """
    r = run([(-2100, (-2100,))] + [(1000, (1000,))] * 3,
            max_combine_attempts=2, combine_fee=49.0)
    assert r.terminal is ts.TopstepStage.EXPRESS_FUNDED
    assert r.combine_attempts == 2
    assert r.combine_days == 3
    assert r.fees_paid == 98.0
    assert r.breach_day == MONDAY


def test_s14_the_daily_loss_limit_caps_the_session_instead_of_ending_the_account():
    """-$2,500 with the $1,000 DLL armed.

        DLL level 50,000 - 1,000 = 49,000     MLL 48,000
        mark 47,500 is below BOTH. Equity fell through 49,000 first, because that is the
        higher level, so the rule that fired is the daily loss limit.
        The platform flattens and the day is booked at exactly -1,000: balance 49,000,
        which is above the 48,000 limit. The account survives.
    """
    r = run([(-2500, (-2500,))], daily_loss_limit=1000.0)
    assert r.terminal is ts.TopstepStage.TRADING_COMBINE
    assert r.final_balance == 49_000.0
    assert r.min_buffer == 1_000.0


def test_s15_without_the_daily_loss_limit_the_same_session_is_fatal():
    """The identical day, unarmed: 47,500 <= 48,000 and the account is gone.

    S14 and S15 differ in exactly one flag, so the $2,500 the DLL is worth here is not
    confounded with anything else.
    """
    r = run([(-2500, (-2500,))])
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert "intraday equity 47,500 reached the MLL 48,000" in r.breach_reason


def test_s16_the_daily_loss_limit_protects_nothing_once_the_limit_sits_above_it():
    """Four sessions that walk the account down until the DLL is out of reach.

        +1,000  balance 51,000  peak 51,000  MLL 49,000            room 2,000
        -1,200  DLL level 50,000; equity 49,800 <= 50,000, capped at -1,000
                balance 50,000, peak unchanged, MLL still 49,000    room 1,000
          -800  DLL level 49,000; equity 49,200 clears both
                balance 49,200                                      room   200
          -500  DLL level 48,200, MLL 49,000. The LIMIT is now the higher level.
                equity 48,700 <= 49,000 and 48,700 > 48,200
                -> the MLL fires and the DLL never comes into play

    An armed daily loss limit is only protection while it sits above the maximum loss
    limit. On an account this close to its floor it is decorative, and a twin that reported
    the DLL as unconditional risk control would overstate survival exactly where it matters.
    """
    r = run([(1000, (1000,)), (-1200, (-1200,)), (-800, (-800,)), (-500, (-500,))],
            daily_loss_limit=1000.0)
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert r.days == 4
    assert "intraday equity 48,700 reached the MLL 49,000" in r.breach_reason
    assert r.min_buffer == 200.0


def test_s17_five_winning_days_earn_a_payout_of_half_the_balance():
    """Pass in three days, then five funded days of +$200.

        each +200 >= the $150 winning-day minimum, so five winning days
        balance 1,000, peak 1,000, MLL min(1,000 - 2,000, 0) = -1,000, room 2,000
        cap = min(50% of 1,000, the $2,000 ceiling) = 500
        paid 500 >= the $125 floor
        after: balance 500, the limit is PINNED at 0 by the payout, room 500
    """
    r = run([(1000, (1000,))] * 3 + [(200, (200,))] * 5,
            payout_policy=tw.IMMEDIATE)
    assert len(r.payouts) == 1
    assert r.payouts[0][1] == 500.0
    assert r.total_paid == 500.0
    assert r.final_balance == 500.0
    assert r.min_buffer_funded == 500.0


def test_s18_a_request_below_the_hundred_and_twenty_five_dollar_floor_is_refused_outright():
    """Five funded days of exactly $150, withdrawing 30% of the cap.

        balance 750, cap = min(375, 2,000) = 375, 30% of it = 112.50 < 125

    Refused means NOTHING moves. Not the balance, and above all not the limit: recording a
    payout the firm would have rejected pins the maximum loss limit at $0 permanently and
    clears the winning-day count, spending two irreversible things for cash that never
    arrived. The account is left standing at PAYOUT_ELIGIBLE with its buffer intact.
    """
    r = run([(1000, (1000,))] * 3 + [(150, (150,))] * 5,
            payout_policy=tw.PayoutPolicy(fraction=0.3))
    assert r.payouts == []
    assert r.total_paid == 0.0
    assert r.final_balance == 750.0
    assert r.terminal is ts.TopstepStage.PAYOUT_ELIGIBLE
    assert r.min_buffer_funded == 2_000.0


def test_s19_the_two_thousand_dollar_ceiling_binds_above_a_four_thousand_balance():
    """Five funded days of +$1,000.

        balance 5,000; half of it is 2,500, but the $50K ceiling is 2,000
        cap = min(2,500, 2,000) = 2,000, so 2,000 is withdrawn and 3,000 stays

    The ceiling is per ACCOUNT SIZE. Reading it from the $150K row would allow $5,000 here.
    """
    r = run([(1000, (1000,))] * 8, payout_policy=tw.IMMEDIATE)
    assert r.combine_days == 3
    assert len(r.payouts) == 1
    assert r.payouts[0][1] == 2_000.0
    assert r.final_balance == 3_000.0
    assert r.min_buffer_funded == 2_000.0


def test_s20_a_payout_pins_the_limit_at_zero_before_the_trail_would_have_got_there():
    """The case where the pin is a real rule and not just bookkeeping.

        five funded days of +150: balance 750, peak 750
        the TRAILING limit would be min(750 - 2,000, 0) = -1,250, so room 2,000
        cap = min(375, 2,000) = 375, withdrawn
        after the payout the limit is PINNED at 0, not -1,250:
            balance 375, room 375 - and not the 1,625 the trail alone would have given
        a -374 day then leaves exactly one dollar: equity 1 > 0

    Modelling the pin as "the trail has already reached the lock" would be wrong here, and
    wrong in the generous direction, by $1,250.
    """
    r = run([(1000, (1000,))] * 3 + [(150, (150,))] * 5 + [(-374, (-374,))],
            payout_policy=tw.IMMEDIATE)
    assert r.total_paid == 375.0
    assert r.final_balance == 1.0
    assert r.min_buffer_funded == 1.0
    assert r.terminal is ts.TopstepStage.EXPRESS_FUNDED


def test_s21_and_the_pinned_limit_is_what_kills_it():
    """One more dollar down: equity 0 <= 0, against a limit that a payout put there."""
    r = run([(1000, (1000,))] * 3 + [(150, (150,))] * 5 + [(-374, (-374,)), (-1, (-1,))],
            payout_policy=tw.IMMEDIATE)
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert r.total_paid == 375.0
    assert "intraday equity 0 reached the MLL 0" in r.breach_reason


# ======================================================================================
# B. THE PATH-DEPENDENCE ATTACK
# ======================================================================================

def test_identical_daily_pnl_with_a_deeper_path_dies():
    """The attack in its simplest form.

    Five sessions, +300 -400 +250 -150 +200, summing to +$200. Run twice: once with no
    excursion beyond the close, once dipping $2,500 below it first. Same P&L series, same
    order, same everything the account statement would show - and one of them is liquidated
    on the first session at 50,000 - 2,200 = 47,800.
    """
    pnls = [300.0, -400.0, 250.0, -150.0, 200.0]
    flat = run([(p, (p,)) for p in pnls])
    deep = run([(p, (p - 2500.0, p)) for p in pnls])
    assert flat.terminal is ts.TopstepStage.TRADING_COMBINE
    assert flat.final_balance == 50_200.0
    assert deep.terminal is ts.TopstepStage.LIQUIDATED
    assert "47,800" in deep.breach_reason


def test_the_same_two_sessions_in_the_other_order_die():
    """+2,500 then -2,100 survives; -2,100 then +2,500 does not.

        up first    day 1 lifts the peak to 52,500, so the limit locks at 50,000.
                    day 2 equity 50,400 > 50,000: survives, closing at 50,400.
        down first  day 1 has the limit still at 48,000 and equity 47,900: dead on day 1.

    Same two sessions, same $400 total. The limit only ever moves up, so the order in which
    a strategy earns and loses is part of its risk, and a twin that summed the days would
    price these identically.
    """
    up = run([(2500, (2500,)), (-2100, (-2100,))])
    down = run([(-2100, (-2100,)), (2500, (2500,))])
    assert up.terminal is ts.TopstepStage.TRADING_COMBINE
    assert up.final_balance == 50_400.0
    assert down.terminal is ts.TopstepStage.LIQUIDATED
    assert down.days == 1


def test_one_multiset_of_sessions_reordered_gives_both_verdicts():
    """+1,500 -1,400 +900 -1,300 +700, all 120 orderings.

    The multiset is fixed, so total P&L, mean, standard deviation, Sharpe, win rate and
    every other order-free statistic are identical across all 120. The outcomes are not.
    """
    import itertools
    base = [1500.0, -1400.0, 900.0, -1300.0, 700.0]
    verdicts = {}
    for perm in set(itertools.permutations(base)):
        r = run([(p, (p,)) for p in perm])
        key = r.terminal.value
        verdicts[key] = verdicts.get(key, 0) + 1
    assert sum(verdicts.values()) == 120
    assert verdicts["liquidated"] > 0
    assert verdicts["trading_combine"] > 0


def test_a_fixed_final_pnl_produces_both_survival_and_liquidation():
    """400 eight-session paths, every one summing to exactly +$1,200.

    If the twin could be answered from the final P&L, this would return one verdict 400
    times. The assertion is that BOTH appear - and, because the point is the size of the
    effect rather than its existence, that neither is a rounding artifact.
    """
    rng = np.random.default_rng(90210)
    total, n = 1200.0, 8
    verdicts = {}
    for _ in range(400):
        raw = rng.normal(0, 800, n)
        ps = raw - raw.mean() + total / n
        depth = rng.uniform(0, 2500, n)
        r = run([(float(p), (float(p - d), float(p))) for p, d in zip(ps, depth,
                                                                     strict=True)])
        assert float(np.sum(ps)) == pytest.approx(total)
        verdicts[r.terminal.value] = verdicts.get(r.terminal.value, 0) + 1
    assert verdicts.get("liquidated", 0) >= 40
    assert verdicts.get("trading_combine", 0) >= 5


def test_deepening_every_excursion_never_helps_the_account():
    """The direction of path sensitivity, over random paths.

    For each trial a P&L series is drawn, then two path shapes are built over the SAME
    series: one with a trough, one with a strictly deeper trough. Three things must hold,
    and each of them is a different way for the twin to be wrong:

        1. if the shallow path was liquidated, the deeper one must be too
        2. the deeper path can never last more sessions
        3. when both survive, the closing balances are IDENTICAL

    The third is the one that pins the mechanism. With no daily loss limit armed, the
    intraday path decides only WHETHER the account survives, never how much it earns -
    settlement is on the day's realised P&L and the marks are a barrier test. A twin that
    let an excursion leak into the balance would fail here even though its survival
    arithmetic was right.
    """
    rng = np.random.default_rng(20260914)
    differed = 0
    for _ in range(FUZZ_PAIRS):
        n = int(rng.integers(3, 12))
        ps = rng.normal(50, 700, n).round(2)
        base = rng.uniform(0, 1200, n).round(2)
        extra = rng.uniform(0, 900, n).round(2)
        shallow = run([(float(p), (float(p - d), float(p)))
                       for p, d in zip(ps, base, strict=True)])
        deeper = run([(float(p), (float(p - d - e), float(p)))
                      for p, d, e in zip(ps, base, extra, strict=True)])
        alive_s = shallow.terminal is not ts.TopstepStage.LIQUIDATED
        alive_d = deeper.terminal is not ts.TopstepStage.LIQUIDATED
        assert not (alive_d and not alive_s), "a deeper path outlived a shallower one"
        assert deeper.days <= shallow.days
        if alive_s and alive_d:
            assert deeper.final_balance == pytest.approx(shallow.final_balance)
        if shallow.terminal is not deeper.terminal:
            differed += 1
    # Not a property of the rules - a check that the fuzz is actually exercising the
    # boundary rather than drawing paths that all survive or all die.
    assert differed > FUZZ_PAIRS // 10


# --------------------------------------------------------------- the second opinion

def _reconcilable(rng):
    """One random configuration: sessions, the DLL, attempts and a payout share."""
    n = int(rng.integers(2, 26))
    sd = float(rng.choice([200, 450, 800, 1400]))
    ps = rng.normal(float(rng.uniform(-100, 250)), sd, n).round(2)
    deps = np.abs(rng.normal(0, sd * 1.2, n)).round(2)
    shape = int(rng.integers(2, 4))
    spec = []
    for p, d in zip(ps, deps, strict=True):
        p, d = float(p), float(d)
        spec.append((p, (p - d, p) if shape == 2
                     else (0.5 * (p - d), p - d, 0.5 * p, p)))
    dll = float(rng.choice([0.0, 1000.0])) or None
    return (sessions(spec), dll, int(rng.integers(1, 4)),
            float(rng.choice([0.0, 0.5, 1.0])), float(rng.choice([0.0, 0.0, 500.0])))


def test_the_twin_reconciles_against_an_independent_reference():
    """`research.topstep_reference` answers the same question from the rulebook.

    It is a pure function over an explicit list of liquidation levels with no state machine
    and no `PropFirmProfile`, sharing no code with the twin - only the cited constants. Over
    random session paths, random daily-loss-limit settings, one to three Combine attempts
    and three payout shares, the two must agree on everything that is a decision:

        the terminal stage, the number of sessions survived, the Combine attempt count and
        the day it was passed on, the day of any breach, whether funding was reached, the
        number and total of payouts, and both minimum buffers.

    The one field deliberately NOT compared here is `final_balance` on a liquidated path;
    `test_the_two_disagree_only_on_a_dead_accounts_reported_balance` covers exactly why.
    """
    rng = np.random.default_rng(4242)
    for trial in range(FUZZ_PAIRS):
        days, dll, attempts, frac, buf = _reconcilable(rng)
        a = tw.TopstepTwin(50_000, daily_loss_limit=dll, max_combine_attempts=attempts,
                           payout_policy=tw.PayoutPolicy(fraction=frac,
                                                         min_buffer_after=buf)).run(days)
        b = tr.run_reference(days, daily_loss_limit=dll, max_combine_attempts=attempts,
                             payout_fraction=frac, min_buffer_after=buf)
        where = f"trial {trial}: dll={dll} attempts={attempts} frac={frac} buffer={buf}"
        assert a.terminal.value == b.terminal, where
        assert a.days == b.days, where
        assert a.combine_attempts == b.combine_attempts, where
        assert a.combine_days == b.combine_days, where
        assert a.breach_day == b.breach_day, where
        assert a.reached_funding == b.reached_funding, where
        assert len(a.payouts) == len(b.payouts), where
        assert a.total_paid == pytest.approx(b.total_paid), where
        assert a.min_buffer == pytest.approx(b.min_buffer), where
        assert a.min_buffer_funded == pytest.approx(b.min_buffer_funded), where
        if a.terminal is not ts.TopstepStage.LIQUIDATED:
            assert a.final_balance == pytest.approx(b.final_balance), where


def test_the_two_disagree_only_on_a_dead_accounts_reported_balance():
    """The one divergence found, isolated and shown to be inert.

    When the daily loss limit is armed, a capped session moves the balance down by exactly
    the limit while the maximum loss limit stays put - so the NEXT session's daily-loss
    level can land exactly on the maximum-loss level. That tie is structural, not a floating
    point coincidence, and it appeared in 518 of 6,000 reconciliation paths.

    On the tie the twin books the day at -1,000 first and then finds the settled balance at
    the limit, reporting `final_balance` as the floor. The reference stops at the touch and
    reports the balance the session opened at. Both liquidate, on the same session.

    Below: the tie is reproduced exactly, both sides are shown to kill the account on the
    same day, and the difference is shown to be the size of one daily loss limit.
    """
    spec = [(1625.50, (330.60, 1625.50)),          # peak 51,625.50, limit 49,625.50
            (-1279.10, (-1692.30, -1279.10)),      # capped at -1,000 -> balance 50,625.50
            (-1456.80, (-2818.10, -1456.80))]      # DLL level 49,625.50 == the limit
    days = sessions(spec)
    a = tw.TopstepTwin(50_000, daily_loss_limit=1000.0,
                       payout_policy=tw.NEVER).run(days)
    b = tr.run_reference(days, daily_loss_limit=1000.0)

    assert a.terminal is ts.TopstepStage.LIQUIDATED and b.terminal == "liquidated"
    assert a.breach_day == b.breach_day == days[2].day
    assert a.final_balance == 49_625.50          # settled onto the floor
    assert b.final_balance == 50_625.50          # stopped at the touch
    assert b.final_balance - a.final_balance == ts.DLL_OPTIONAL[50_000].value


def test_the_tie_between_the_two_limits_can_never_change_survival():
    """Why the divergence above is a reporting convention and not a risk error.

    Both limits are levels the session can fall through. When they coincide, whichever rule
    is deemed to have fired, the outcome is the same: the daily loss limit books the day at
    exactly -DLL, which lands the balance on the maximum loss limit, which is a breach. So
    the tie-break decides the REASON STRING and the reported balance, never whether the
    account lives.

    Rather than argue it, both tie rules are replayed over random daily-loss-limit paths
    with a hand-written level model - deliberately not the twin and not the reference - and
    the survival verdicts are required to be identical every time.
    """
    def replay(pnls, deps, dll, prefer_mll_on_tie):
        balance, peak = 50_000.0, 50_000.0
        for pnl, dep in zip(pnls, deps, strict=True):
            mll = min(peak - 2_000.0, 50_000.0)
            dll_level = balance - dll
            capped = False
            for mark in (pnl - dep, pnl):
                equity = balance + mark
                hit_mll, hit_dll = equity <= mll, equity <= dll_level
                if hit_mll and hit_dll:
                    if mll > dll_level or (mll == dll_level and prefer_mll_on_tie):
                        return False
                    capped = True
                    break
                if hit_mll:
                    return False
                if hit_dll:
                    capped = True
                    break
            balance += -dll if capped else max(pnl, -dll)
            if balance <= mll:
                return False
            peak = max(peak, balance)
        return True

    rng = np.random.default_rng(555)
    for _ in range(20_000):
        n = int(rng.integers(2, 20))
        sd = float(rng.choice([300, 700, 1200]))
        ps = rng.normal(0, sd, n).round(2)
        deps = np.abs(rng.normal(0, sd * 1.2, n)).round(2)
        assert replay(ps, deps, 1000.0, True) == replay(ps, deps, 1000.0, False)


# ======================================================================================
# C. EQUITY-PATH GRANULARITY
# ======================================================================================
#
# The twin tests the limit at the marks it is given and is blind between them. That is not a
# defect to be fixed in the simulator - it is a property of the INPUT, and the only honest
# response is to measure which way the error runs and by how much. `strict_path=True` already
# refuses a session with no path at all; these tests pin what a coarse path costs.

def _walk(rng, bars: int, sd: float) -> np.ndarray:
    """One session's equity, relative to the opening balance, as a random walk."""
    return np.cumsum(rng.normal(0.0, sd, bars))


def test_a_coarser_path_can_only_ever_miss_a_breach_never_invent_one():
    """The direction of the error, which is the part that matters for trusting a result.

    Subsampling drops marks. A dropped mark cannot create a touch that the full path did not
    have, so the coarse answer is always a SUBSET of the fine one: coarse is optimistic, and
    a coarse run that reports a breach has really breached.
    """
    rng = np.random.default_rng(7)
    for _ in range(300):
        equity = _walk(rng, 391, 90.0)
        fine = [tw.TwinDay(day=MONDAY, pnl=float(equity[-1]),
                           path=tuple(float(x) for x in equity))]
        fine_dead = tw.TopstepTwin(50_000, payout_policy=tw.NEVER).run(fine).terminal \
            is ts.TopstepStage.LIQUIDATED
        for step in (5, 15, 30, 60):
            idx = np.arange(step - 1, len(equity), step)
            coarse = [tw.TwinDay(day=MONDAY, pnl=float(equity[-1]),
                                 path=tuple(float(x) for x in equity[idx]))]
            coarse_dead = tw.TopstepTwin(50_000, payout_policy=tw.NEVER).run(
                coarse).terminal is ts.TopstepStage.LIQUIDATED
            assert not (coarse_dead and not fine_dead), (
                f"a {step}-minute path found a breach the minute path did not")


def test_the_cost_of_a_coarse_path_is_measured_and_monotone():
    """How much detection each sampling interval throws away.

    3,000 synthetic 391-bar sessions at $90 per bar against a fresh Combine's $2,000 of
    room. Detection must fall as the interval widens - there is no interval at which
    dropping marks finds MORE - and the close-only figure is the number that matters most,
    because it is what a backtest with no intraday path silently assumes.

    The measured figures are in `docs/TOPSTEP_TWIN_AUDIT.md`. The assertions here are the
    shape of the curve rather than the exact counts, so a different numpy version cannot
    fail the suite over the last basis point.
    """
    rng = np.random.default_rng(7)
    grains = (1, 5, 15, 30, 60, 195, 390)
    detected = dict.fromkeys(grains, 0)
    close_only = 0
    truth = 0
    n = 3000
    for _ in range(n):
        equity = _walk(rng, 391, 90.0)
        breached = equity.min() <= -2_000.0
        truth += breached
        settled_dead = equity[-1] <= -2_000.0
        close_only += settled_dead
        for step in grains:
            idx = np.arange(step - 1, len(equity), step)
            if equity[idx].min() <= -2_000.0 or settled_dead:
                detected[step] += 1

    assert detected[1] == truth, "the full minute path IS the truth in this study"
    counts = [detected[g] for g in grains]
    assert counts == sorted(counts, reverse=True), "detection must fall as marks are dropped"
    assert close_only < detected[390] <= detected[1]
    # The headline: an hourly path misses roughly a fifth of the liquidations, and settling
    # on the close alone misses nearly half of them.
    assert 0.70 <= detected[60] / truth <= 0.85
    assert 0.45 <= close_only / truth <= 0.60


def test_a_session_with_no_path_at_all_is_refused_rather_than_estimated():
    """The end of the granularity scale, and the one point on it the twin will not run.

    Close-only detects roughly half the liquidations. `strict_path=True` therefore refuses
    the input outright rather than returning a number that is optimistic by that much, and
    the waiver marks the result as an upper bound.
    """
    days = [tw.TwinDay(day=MONDAY, pnl=-3_000.0)]
    with pytest.raises(ValueError, match="cannot be run against Topstep's rules"):
        tw.TopstepTwin(50_000, payout_policy=tw.NEVER).run(days)

    waived = tw.TopstepTwin(50_000, payout_policy=tw.NEVER, strict_path=False).run(days)
    assert waived.path_supplied is False
    assert waived.terminal is ts.TopstepStage.LIQUIDATED   # the close alone is still tested


def test_the_reference_makes_the_same_refusal():
    """A second implementation that quietly accepted a close-only day would be worse than
    none: it would reconcile against the twin's waived mode and call it agreement."""
    with pytest.raises(ValueError, match="will not run the breach test"):
        tr.run_reference([tw.TwinDay(day=MONDAY, pnl=-3_000.0)])


# ======================================================================================
# D. THE EXCURSION INSIDE THE BAR
# ======================================================================================
#
# Section C measured what dropping marks costs. This section is about the marks that were
# never there: `session_accounting` builds its path from minute CLOSES, and a position held
# through a bar is marked at that bar's low or high before the close prints. The platform
# liquidates on the touch, so a close-built path is optimistic by exactly that excursion.
# `research.intrabar_path` restores it as an explicit, opt-in bound.

def test_the_intrabar_bound_never_moves_the_settled_pnl():
    """The one thing it must not do.

    `TwinDay.pnl` is the day's realised P&L and the path is a barrier test around it. A
    path builder that changed the terminal value would be rewriting the account statement,
    not adding fidelity. Two bars, a long lot, and a low well below both closes.
    """
    from quant_brain.research import intrabar_path as ip
    close = np.array([100.0, 101.0, 102.0])
    high = np.array([100.0, 101.5, 102.0])
    low = np.array([100.0, 96.0, 101.0])
    pos = np.array([1.0, 1.0, 1.0])
    net = np.array([50.0, 100.0])          # +1 point then +1 point at $50 a point, no cost
    out = ip.with_intrabar_marks(net, pos, close, high, low, multiplier=50.0, contracts=1)
    assert out[-1] == 100.0
    # bar 1 fell to 96.0 from a 100.0 entry: -4 points = -$200 against a $0 opening equity
    assert min(out) == -200.0


def test_a_long_is_marked_at_the_low_and_a_short_at_the_high():
    """The sign of the bound. Marking a short at the low would flatter it, not stress it."""
    from quant_brain.research import intrabar_path as ip
    close = np.array([100.0, 100.0])
    high = np.array([100.0, 103.0])
    low = np.array([100.0, 97.0])
    for direction, expected in ((1.0, -150.0), (-1.0, -150.0), (0.0, 0.0)):
        marks = ip.adverse_marks(np.array([direction, direction]), close, high, low,
                                 multiplier=50.0, contracts=1)
        assert marks[0] == expected, direction


def test_the_bound_is_never_shallower_than_the_close_path():
    """The direction of the correction, over random OHLC.

    Restoring an excursion can only add depth. If a session's bars never traded through
    their own closes the two paths are identical; they can never diverge the other way.
    """
    from quant_brain.research import intrabar_path as ip
    rng = np.random.default_rng(11)
    identical = 0
    for _ in range(500):
        n = int(rng.integers(3, 40))
        close = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
        wick = np.abs(rng.normal(0, 0.4, n))
        high = np.maximum(close, np.roll(close, 1)) + wick
        low = np.minimum(close, np.roll(close, 1)) - wick
        high[0], low[0] = close[0], close[0]
        pos = rng.choice([-1.0, 0.0, 1.0], n)
        net = np.cumsum(pos[:-1] * np.diff(close) * 50.0)
        out = ip.with_intrabar_marks(net, pos, close, high, low, multiplier=50.0,
                                     contracts=1)
        assert out[-1] == pytest.approx(net[-1])
        assert min(out) <= min(net) + 1e-9
        assert len(out) >= len(net)
        if len(out) == len(net):
            identical += 1
    # A zero-wick session must round-trip exactly; the fuzz above rarely draws one, so the
    # case is asserted directly rather than relied on.
    flat_close = np.array([100.0, 101.0, 102.0])
    flat = ip.with_intrabar_marks(np.array([50.0, 100.0]), np.array([1.0, 1.0, 1.0]),
                                  flat_close, flat_close, flat_close,
                                  multiplier=50.0, contracts=1)
    assert flat == (50.0, 100.0)


def test_restoring_the_excursion_can_only_make_the_twin_stricter():
    """The property that makes this safe to turn on: it never rescues an account.

    A deeper path is a superset of the touches the shallow path had, so a session the close
    path calls liquidated must stay liquidated. Anything else would mean the bound was
    letting an account through, which is the one failure mode that matters.
    """
    from quant_brain.research import intrabar_path as ip
    rng = np.random.default_rng(12)
    stricter = 0
    for _ in range(400):
        # Sized so the equity path actually approaches the $2,000 limit. A gentler walk
        # never reaches the barrier and the test would pass while proving nothing, which
        # is what the final assertion guards against.
        n = 200
        close = 5000.0 + np.cumsum(rng.normal(0, 2.0, n))
        wick = np.abs(rng.normal(0, 1.5, n))
        high = np.maximum(close, np.roll(close, 1)) + wick
        low = np.minimum(close, np.roll(close, 1)) - wick
        high[0], low[0] = close[0], close[0]
        pos = np.ones(n)
        net = np.cumsum(np.diff(close) * 50.0)
        aug = ip.with_intrabar_marks(net, pos, close, high, low, multiplier=50.0,
                                     contracts=1)
        shallow = [tw.TwinDay(day=MONDAY, pnl=float(net[-1]),
                              path=tuple(float(x) for x in net))]
        deep = [tw.TwinDay(day=MONDAY, pnl=float(net[-1]), path=aug)]
        a = tw.TopstepTwin(50_000, payout_policy=tw.NEVER).run(shallow)
        b = tw.TopstepTwin(50_000, payout_policy=tw.NEVER).run(deep)
        dead_a = a.terminal is ts.TopstepStage.LIQUIDATED
        dead_b = b.terminal is ts.TopstepStage.LIQUIDATED
        assert not (dead_a and not dead_b), "the intra-bar bound rescued a dead account"
        stricter += dead_b and not dead_a
    assert stricter > 0, "the fuzz never exercised a flip; the test proves nothing"


def test_mismatched_bar_arrays_are_refused_rather_than_broadcast():
    """Fail closed. Silently broadcasting a short array would align the wrong bar's low
    with the wrong bar's position, which is a leak dressed as a shape error."""
    from quant_brain.research import intrabar_path as ip
    with pytest.raises(ValueError, match="same length"):
        ip.adverse_marks(np.ones(4), np.ones(4), np.ones(3), np.ones(4),
                         multiplier=50.0, contracts=1)
    with pytest.raises(ValueError, match="describe the same session"):
        ip.with_intrabar_marks(np.zeros(2), np.ones(4), np.ones(4), np.ones(4),
                               np.ones(4), multiplier=50.0, contracts=1)
