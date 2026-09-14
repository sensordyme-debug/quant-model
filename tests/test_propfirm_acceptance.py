"""Topstep acceptance: hand-computed money paths through the real account objects.

WHAT THIS IS
------------
Every test here drives the SHIPPED `TopstepAccount` / `TopstepTwin` / `PropFirmRiskEngine`
along a P&L path whose expected answer was worked out by hand and written into the docstring.
Nothing is recomputed by a parallel model in this file: if the arithmetic in the docstring and
the arithmetic in the module disagree, the module is wrong or the citation is wrong, and
either way somebody has to look.

OFFICIAL VALUES, retrieved 2026-09-13
-------------------------------------
$50K Trading Combine
    profit target            $3,000
    Maximum Loss Limit       $2,000, trails the END-OF-DAY balance, never moves down,
                             monitored intraday INCLUDING unrealized P&L, and LOCKS AT THE
                             STARTING BALANCE. There is no "+$100" anywhere in the rule and
                             this file asserts that there is not.
                             help.topstep.com/en/articles/8284204
    MLL after a payout       $0, permanently. help.topstep.com/en/articles/8284233
    Daily Loss Limit         optional $1,000; triggering it is a FORCED BREAK, not a rule
                             violation - flat, cancelled, resume next session.
                             help.topstep.com/en/articles/8284207
    consistency              55%. The official pages disagree on the DENOMINATOR (the
                             threshold sentence says "of your Profit Target", the worked
                             example divides by total profit) and on whether the boundary is
                             "<" or "<=". Both denominators are modelled; the boundary is not.
                             help.topstep.com/en/articles/8284208
    max position             5 minis / 50 micros at a 10:1 ratio, PER ACCOUNT
                             help.topstep.com/en/articles/8284197
    mandatory flat           3:10 PM CT
    payout minimum           $125
    round-turn commission    ES/NQ $3.78, MES/MNQ $1.22

ELEVEN DEFECTS, ALL NOW FIXED
-----------------------------
These were pinned with `xfail(strict=True)`: a tripwire in both directions, since the test had
to fail while the defect stood and the marker itself became an error the day it was fixed, so
no fix could be smuggled in by deleting the test. The mechanism worked. All eleven were fixed
on 2026-09-14, every marker is gone, and each test now carries a dated RATCHET CLEARED line
saying what landed. The list is kept because knowing what was once wrong is how a reader judges
what to re-check:

    consistency boundary  the < / <= reading is a hard-coded operator, not a reading
    payout minimum        a $75 payout is recorded; the published minimum is $125
    payout eligibility    tested on total profit, not net profit since the last payout
    payout day count      the consistency route's 3-day count never restarts
    position limits       raw contract counting, no 10:1 mini/micro equivalence
    position limits       an unlisted full-size root is capped at the MICRO number
    permitted products    there is no product list; 50 BTC is accepted
    XFA sizing            a $0-balance XFA is permitted full Combine size
    mandatory flat        enforced at 15:45 CT; the rule is 15:10 CT
    commissions           $4.00/$1.00 modelled against $3.78/$1.22 published
    contract ceiling      the allowance is in micro-equivalents and the sizer counted minis

Nothing here was weakened to make it green.

RUNNING
    python -m pytest tests/test_propfirm_acceptance.py -q -rxX
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import replace

import pytest

from quant_brain.core.execution import OrderIntent, Side
from quant_brain.markets.futures_cme import instruments as inst
from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme import twin as tw
from quant_brain.markets.futures_cme.propfirm import (
    AccountState,
    PropFirmRiskEngine,
    TrailingMode,
)

pytestmark = pytest.mark.acceptance

# ======================================================================================
# THE OFFICIAL NUMBERS, as constants so a test cannot quietly drift off them
# ======================================================================================

SIZE = 50_000
START = 50_000.0
MLL = 2_000.0
TARGET = 3_000.0
DLL = 1_000.0
CONSISTENCY = 0.55
PAYOUT_MINIMUM = 125.0
MANDATORY_FLAT_CT = dt.time(15, 10)
#: The calendar close the model's "minutes before close" is measured against.
CME_EQUITY_CLOSE_CT = dt.time(16, 0)
OFFICIAL_ROUND_TURN = {"ES": 3.78, "NQ": 3.78, "MES": 1.22, "MNQ": 1.22}

CENT = 0.01

MLL_DOC = "help.topstep.com/en/articles/8284204 (retrieved 2026-09-13)"
PAYOUT_DOC = "help.topstep.com/en/articles/8284233 (retrieved 2026-09-13)"
XFA_DOC = "help.topstep.com/en/articles/8284215 (retrieved 2026-09-13)"
COMBINE_DOC = "help.topstep.com/en/articles/8284197 (retrieved 2026-09-13)"
CONSISTENCY_DOC = "help.topstep.com/en/articles/8284208 (retrieved 2026-09-13)"
DLL_DOC = "help.topstep.com/en/articles/8284207 (retrieved 2026-09-13)"


# ======================================================================================
# HELPERS - construction only, never arithmetic under test
# ======================================================================================

def combine_account(*, reading: str = ts.DEFAULT_READING,
                    daily_loss_limit: float | None = None) -> ts.TopstepAccount:
    """A fresh $50K Combine account at its opening balance."""
    return ts.TopstepAccount(
        profile=ts.combine(SIZE, reading=reading, daily_loss_limit=daily_loss_limit),
        reading=reading)


def xfa_account(*, consistency_route: bool = False) -> ts.TopstepAccount:
    """A fresh Express Funded Account: $0 balance, the same $2,000 MLL."""
    return ts.TopstepAccount(
        profile=ts.express_funded(SIZE, consistency_route=consistency_route),
        stage=ts.TopstepStage.EXPRESS_FUNDED,
        consistency_route=consistency_route)


def engine(*, profile=None) -> PropFirmRiskEngine:
    """The real risk gate over a real $50K Combine account state."""
    return PropFirmRiskEngine(AccountState(profile=profile or ts.combine(SIZE)))


def day(index: int, pnl: float, path: tuple[float, ...] = ()) -> tw.TwinDay:
    """One session, `index` days after 2026-01-05."""
    return tw.TwinDay(day=dt.date(2026, 1, 5) + dt.timedelta(days=index),
                      pnl=pnl, path=path or (pnl,))


def minutes_to_close(when: dt.time, close: dt.time = CME_EQUITY_CLOSE_CT) -> int:
    """Minutes from a Central-Time wall clock to the session close the model measures against.

    `PropFirmRiskEngine.must_be_flat` takes minutes-to-close rather than a clock, which is the
    right shape (it stays correct on an early close). This converts a real Topstep deadline,
    which IS a wall clock, into that shape so the two can be compared at all.
    """
    return (close.hour * 60 + close.minute) - (when.hour * 60 + when.minute)


# ======================================================================================
# 1. THE MAXIMUM LOSS LIMIT
# ======================================================================================

def test_the_fifty_k_rulebook_matches_the_published_numbers():
    """The three figures every other test in this file rests on.

    $50K Combine: profit target $3,000, MLL $2,000, optional DLL $1,000. If any of these
    drifts, the hand arithmetic below is measuring the wrong account.
    """
    profile = ts.combine(SIZE)
    assert profile.profit_target == TARGET
    assert profile.max_drawdown == MLL
    assert ts.DLL_OPTIONAL[SIZE].value == DLL
    assert profile.trailing_mode is TrailingMode.EOD_TRAIL_INTRADAY_BREACH
    assert ts.COMBINE_CONSISTENCY_DOC.value == CONSISTENCY


@pytest.mark.parametrize("equity,expected,label", [
    (48_000.00, True, "exactly at the limit"),
    (48_000.00 + CENT, False, "one cent above"),
    (48_000.00 - CENT, True, "one cent below"),
])
def test_the_mll_breach_boundary_is_a_touch_not_a_crossing(equity, expected, label):
    """Hand arithmetic: 50,000 start - 2,000 MLL = an equity floor of 48,000.00.

        equity 48,000.00   BREACH   "If your balance hits it at any point during the
                                     trading day ... liquidated immediately" - a touch is
                                     a breach, so the comparison must be <=, not <.
        equity 48,000.01   alive    one cent of room left
        equity 47,999.99   BREACH   through the floor

    Source: """ + MLL_DOC
    account = combine_account()
    assert account.mll == 48_000.00
    account.equity = equity
    assert account.breached() is expected, label


def test_the_mll_is_tested_on_unrealized_pnl_not_just_the_balance():
    """A mark, not a settled day, is enough to breach.

    Hand arithmetic: balance 50,000, floor 48,000. `mark(-2,000)` moves equity to 48,000.00
    with the balance untouched at 50,000. Under a realized-only reading the account is fine;
    under Topstep's rule it is gone.

    "Both realized and unrealized P&L count toward it." """ + MLL_DOC
    account = combine_account()
    account.mark(-2_000.0)
    assert account.balance == 50_000.0
    assert account.equity == 48_000.0
    assert account.breached() is True
    assert account.advance() is ts.TopstepStage.LIQUIDATED


def test_an_intraday_touch_that_recovers_by_the_close_is_still_a_liquidation():
    """The session that ends green and kills the account anyway.

    Hand arithmetic, $50K Combine, floor 48,000.00:

        marks   -500     equity 49,500   alive
                -2,000   equity 48,000   TOUCH -> liquidated, immediately
                -300     never reached
        close   +100     never reached

    A model that only tested the close would book +100 and carry on. Source: """ + MLL_DOC
    twin = tw.TopstepTwin(SIZE, payout_policy=tw.NEVER)
    result = twin.run([day(0, 100.0, (-500.0, -2_000.0, -300.0, 100.0))])

    assert result.terminal is ts.TopstepStage.LIQUIDATED
    assert result.breach_day == dt.date(2026, 1, 5)
    assert "48,000" in result.breach_reason
    assert result.final_balance == 50_000.0, "liquidated on the mark; the day never settled"


def test_the_same_session_one_cent_shallower_survives_and_closes_green():
    """The control for the test above; without it the touch test proves only pessimism.

    Hand arithmetic: the deepest mark is -1,999.99, so equity bottoms at 48,000.01 - one cent
    above the floor. The day then settles at +100 and the balance is 50,100.00.
    """
    twin = tw.TopstepTwin(SIZE, payout_policy=tw.NEVER)
    result = twin.run([day(0, 100.0, (-500.0, -1_999.99, -300.0, 100.0))])

    assert result.terminal is ts.TopstepStage.TRADING_COMBINE
    assert result.breach_day is None
    assert result.final_balance == pytest.approx(50_100.0, abs=1e-9)


def test_the_mll_ratchets_up_on_the_end_of_day_balance_and_never_back_down():
    """The trailing rule, worked by hand over four sessions.

        session   pnl      balance    peak EOD    MLL = min(peak - 2,000, 50,000)
        ------------------------------------------------------------------------
        open       -       50,000     50,000      48,000
        1        +500      50,500     50,500      48,500      ratchets UP
        2        -300      50,200     50,500      48,500      does NOT follow down
        3      +1,800      52,000     52,000      50,000      reaches the lock
        4      +1,000      53,000     53,000      50,000      LOCKED, stays put

    "It rises as your end-of-day balance grows, but never moves down. Once it reaches your
    starting balance, it locks permanently." """ + MLL_DOC
    account = combine_account()
    assert account.mll == 48_000.0

    account.settle_day(500.0)
    assert (account.balance, account.mll) == (50_500.0, 48_500.0)

    account.settle_day(-300.0)
    assert account.balance == 50_200.0
    assert account.mll == 48_500.0, "the MLL must not follow a losing day down"

    account.settle_day(1_800.0)
    assert (account.balance, account.mll) == (52_000.0, 50_000.0)
    assert account.mll_locked is True

    account.settle_day(1_000.0)
    assert account.balance == 53_000.0
    assert account.mll == 50_000.0


def test_the_lock_is_the_starting_balance_exactly_with_no_hundred_dollar_kicker():
    """The MLL locks at $50,000.00. Not $50,100.00.

    Several prop firms lock a trailing threshold one increment above the starting balance and
    the number gets copied between rulebooks. Topstep's does not: "Once it reaches your
    starting balance, it locks permanently." A $100 kicker would silently hand every account
    $100 of buffer it does not have, on the exact margin that decides liquidation.

    Hand arithmetic: after any peak >= 52,000 the threshold is min(peak - 2,000, 50,000) and
    that expression is pinned at 50,000.00 forever.

    Source: """ + MLL_DOC
    profile = ts.combine(SIZE)
    assert profile.trailing_locks_at == START
    assert ts.MLL_LOCKS.value is True

    account = combine_account()
    for pnl in (2_000.0, 1_000.0, 5_000.0):
        account.settle_day(pnl)
        assert account.mll == 50_000.00
        assert account.mll != 50_100.00
    # And the floor helper agrees at every peak above the lock.
    for peak in (52_000.0, 55_000.0, 100_000.0):
        assert profile.floor_for(peak) == 50_000.00


# ======================================================================================
# 2. PASSING, AND THE DAILY LOSS LIMIT
# ======================================================================================

def test_reaching_the_profit_target_passes_the_combine():
    """Four sessions of +$750 pass a $50K Combine. Hand arithmetic:

        total profit  4 x 750 = 3,000   == the published $3,000 target
        best day             750 / 3,000 = 25%   <= the 55% consistency limit
        trading days           4         >= the 0 Topstep publishes

    The twin rolls a passed Combine straight into the Express Funded Account - the XFA is a
    NEW account at a $0 balance - so the terminal stage is EXPRESS_FUNDED and COMBINE_PASSED
    appears in the transition log.

    Source: """ + COMBINE_DOC
    account = combine_account()
    for _ in range(4):
        account.settle_day(750.0)

    passed, why = account.combine_passed()
    assert passed is True, why
    assert account.total_profit == 3_000.0
    assert account.best_day == 750.0
    assert account.advance() is ts.TopstepStage.COMBINE_PASSED

    twin = tw.TopstepTwin(SIZE, payout_policy=tw.NEVER)
    result = twin.run([day(i, 750.0, (200.0, 750.0)) for i in range(4)])
    stages = [stage for _d, stage in result.transitions]
    assert ts.TopstepStage.COMBINE_PASSED in stages
    assert result.combine_days == 4
    assert result.terminal is ts.TopstepStage.EXPRESS_FUNDED


def test_one_dollar_short_of_the_target_has_not_passed():
    """The control: 2,999.00 of profit is not 3,000.00 of profit."""
    account = combine_account()
    for _ in range(4):
        account.settle_day(749.75)
    assert account.total_profit == pytest.approx(2_999.0, abs=1e-9)
    passed, why = account.combine_passed()
    assert passed is False
    assert "below target" in why


def test_a_daily_loss_limit_hit_is_a_forced_break_and_the_account_survives():
    """The DLL ends the day, not the account. Hand arithmetic, $50K with the DLL armed:

        day 1 opening balance   50,000
        DLL level               50,000 - 1,000 = 49,000
        MLL level                            48,000     (below the DLL, so the DLL fires first)
        marks   -200   equity 49,800  alive
                -1,200 equity 48,800  <= 49,000 -> DLL fires; the day is BOOKED AT -1,000
        settled balance         49,000     the -1,500 the session would have lost is capped
        day 2   +300            49,300

    "Triggering it is not a rule violation - it's a forced break for the rest of that
    session ... Account stays eligible for funding. Resume tomorrow." Source: """ + DLL_DOC
    assert ts.DLL_IS_OPTIONAL.value is True
    assert ts.DLL_ENDS_ACCOUNT.value is False

    twin = tw.TopstepTwin(SIZE, daily_loss_limit=DLL, payout_policy=tw.NEVER)
    result = twin.run([
        day(0, -1_500.0, (-200.0, -1_200.0, -1_500.0)),
        day(1, 300.0, (100.0, 300.0)),
    ])

    assert result.terminal is ts.TopstepStage.TRADING_COMBINE, "not a violation"
    assert result.terminal.is_terminal is False
    assert result.breach_day is None
    assert result.final_balance == pytest.approx(49_300.0, abs=1e-9)
    assert result.transitions == [], "a forced break is not a state transition"


def test_the_daily_loss_limit_is_off_unless_it_is_asked_for():
    """It is optional in the Combine, so the default profile must not carry one.

    Modelling an unarmed DLL as armed would understate risk in the flattering direction: the
    limit flattens the book before it can reach the MLL. Source: """ + DLL_DOC
    assert ts.combine(SIZE).daily_loss_limit is None
    assert ts.combine(SIZE, daily_loss_limit=DLL).daily_loss_limit == DLL


# ======================================================================================
# 3. CONSISTENCY - two published readings, one unrecorded boundary
# ======================================================================================

def test_both_published_denominators_are_recorded_rather_than_silently_resolved():
    """8284208 contradicts itself, and the module keeps both readings instead of choosing.

        threshold sentence   "must stay at or below 55% of your Profit Target"
        calculation line     "Best Day Profit / Total Profit = Best Day %"

    Those are different denominators. Both are in `CONSISTENCY_READINGS`, both carry the
    quote they came from, and `with_reading` switches a built profile between them - which
    is what makes the disagreement measurable rather than an argument.

    Source: """ + CONSISTENCY_DOC
    assert ts.CONSISTENCY_READINGS["doc_calc"] == (CONSISTENCY, "total")
    assert ts.CONSISTENCY_READINGS["doc_text"] == (CONSISTENCY, "target")
    assert ts.COMBINE_CONSISTENCY_DENOMINATOR.value == "total"
    # each side of the contradiction quotes the page it came from, and says so
    assert "Profit Target" in ts.COMBINE_CONSISTENCY_DOC.quote
    assert "Total Profit" in ts.COMBINE_CONSISTENCY_DENOMINATOR.quote
    assert "ontradict" in (ts.COMBINE_CONSISTENCY_DENOMINATOR.note or "")

    profile = ts.combine(SIZE, reading="doc_calc")
    assert ts.with_reading(profile, "doc_text").max_single_day_profit_share is None
    assert ts.with_reading(profile, "doc_calc").max_single_day_profit_share == CONSISTENCY


def test_the_two_readings_give_opposite_verdicts_on_one_hand_computed_path():
    """A path where the ambiguity decides whether the Combine is passed. Hand arithmetic:

        sessions      +2,200, +900, +900     total profit 4,000, best day 2,200

        doc_calc  best / total  = 2,200 / 4,000 = 55.00%  <= 55%  -> COMPLIANT, PASSES
        doc_text  best / target = 2,200 / 3,000 = 73.33%  >  55%  -> REFUSED

    Same money, opposite answers. Recording both readings is therefore not bookkeeping; it is
    the difference between a passed evaluation and a raised target.

    Source: """ + CONSISTENCY_DOC
    verdicts = {}
    for reading in ("doc_calc", "doc_text"):
        account = combine_account(reading=reading)
        for pnl in (2_200.0, 900.0, 900.0):
            account.settle_day(pnl)
        verdicts[reading] = (account.consistency_pct, account.consistency_ok,
                             account.combine_passed()[0])

    assert verdicts["doc_calc"][0] == pytest.approx(0.55, abs=1e-12)
    assert verdicts["doc_calc"][1:] == (True, True)
    assert verdicts["doc_text"][0] == pytest.approx(2_200.0 / 3_000.0, abs=1e-12)
    assert verdicts["doc_text"][1:] == (False, False)


def test_a_day_at_exactly_fifty_five_percent_is_admitted_under_both_readings():
    """The boundary case, engineered so the two denominators coincide. Hand arithmetic:

        sessions   +1,650, +1,350     total profit 3,000 == the target, best day 1,650

        doc_calc  1,650 / 3,000 = 55.00%
        doc_text  1,650 / 3,000 = 55.00%

    Both read exactly 55.00% and both admit the day, because the shipped comparison is
    inclusive (`pct <= limit`, topstep.py). That is the "at or below" wording on 8284208 and
    it is the reading this repository has chosen; the test exists so that flipping the
    operator to a strict `<` cannot happen silently.

    Source: """ + CONSISTENCY_DOC
    for reading in ("doc_calc", "doc_text"):
        account = combine_account(reading=reading)
        account.settle_day(1_650.0)
        account.settle_day(1_350.0)
        assert account.consistency_pct == pytest.approx(0.55, abs=1e-12), reading
        assert account.consistency_ok is True, reading
        assert account.combine_passed()[0] is True, reading


# RATCHET CLEARED 2026-09-13: CONSISTENCY_READINGS entries may now carry a boundary alongside the denominator, so the simulator and the account cannot apply opposite sides of 55.00%.
def test_the_boundary_reading_is_recorded_alongside_the_denominator_reading():
    """A reading must be able to say WHICH SIDE of 55.00% is compliant.

    The fix is a third element on the `CONSISTENCY_READINGS` tuples (threshold, denominator,
    boundary) or a `Rule` naming the operator, so `with_reading` can switch it exactly as it
    switches the denominator today.
    """
    boundary_aware = {name: value for name, value in ts.CONSISTENCY_READINGS.items()
                      if len(value) >= 3}
    assert boundary_aware, (
        "no entry in CONSISTENCY_READINGS distinguishes '< 55%' from '<= 55%'; the boundary "
        f"is decided by a hard-coded operator. readings: {ts.CONSISTENCY_READINGS}")


def test_exceeding_consistency_raises_the_target_and_never_fails_the_account():
    """8284208: "If it exceeds that, your Profit Target increases." It is not a failure.

    Hand arithmetic under doc_calc: sessions +2,000 and +500 give total 2,500 with a best day
    of 2,000, i.e. 80% - above the 55% limit. The smallest target consistent with the rule is
    the one that makes the best day exactly compliant:

        effective target = best_day / 0.55 = 2,000 / 0.55 = 3,636.36...

    which is above the 3,000 base. The account is NOT failed; it has further to go.

    Source: """ + CONSISTENCY_DOC
    assert ts.COMBINE_CONSISTENCY_EXCEEDED.value == "target_rises"
    account = combine_account(reading="doc_calc")
    account.settle_day(2_000.0)
    account.settle_day(500.0)

    assert account.consistency_pct == pytest.approx(0.80, abs=1e-12)
    assert account.consistency_ok is False
    assert account.effective_profit_target == pytest.approx(2_000.0 / 0.55, abs=1e-9)
    assert account.combine_passed()[0] is False
    assert account.advance() is ts.TopstepStage.TRADING_COMBINE, "not failed - still trying"


# ======================================================================================
# 4. PAYOUTS
# ======================================================================================

def test_a_payout_pins_the_mll_at_zero_and_spends_the_buffer():
    """The payout as a risk decision, worked by hand on an XFA.

        opening balance                  0        MLL = min(0 - 2,000, 0) = -2,000
        5 sessions of +160             800        peak 800, MLL = min(-1,200, 0) = -1,200
        distance to the MLL          2,000        800 - (-1,200)
        payout cap = min(50% x 800, 2,000) = 400
        take it:      balance          400
                      MLL                0        "resets to $0 permanently"
                      distance          400        the buffer fell 2,000 -> 400

    So $400 of cash cost $1,600 of the room that keeps the account alive. That is why the
    twin prices the decision instead of taking the maximum by default.

    Source: """ + PAYOUT_DOC
    account = xfa_account()
    for _ in range(5):
        account.settle_day(160.0)

    assert account.balance == 800.0
    assert account.winning_days == 5
    assert account.mll == -1_200.0
    assert account.distance_to_mll == 2_000.0
    assert account.payout_eligible is True
    assert account.payout_cap == 400.0

    paid = account.take_payout()
    assert paid == 400.0
    assert account.balance == 400.0
    assert ts.MLL_RESETS_ON_PAYOUT.value is True
    assert account.mll_reset_by_payout is True
    assert account.mll == 0.0
    assert account.distance_to_mll == 400.0


def test_a_payout_resets_the_winning_day_count_and_the_daily_series():
    """"your 5-day count restarts" - so the next payout needs five more winning days.

    Source: """ + PAYOUT_DOC
    account = xfa_account()
    for _ in range(5):
        account.settle_day(160.0)
    account.take_payout()

    assert account.winning_days == 0
    assert account.daily_pnl == []
    assert account.payouts_taken == 1
    assert account.total_paid_out == 400.0
    assert account.stage is ts.TopstepStage.EXPRESS_FUNDED
    assert account.payout_eligible is False, "five more winning days are required"


# RATCHET CLEARED 2026-09-13: PAYOUT_MINIMUM = Rule(125.0, DOC 8284233); take_payout returns 0.0 and mutates nothing below it, so a $75 request no longer clears the winning-day count or pins the MLL.
def test_a_payout_below_the_published_minimum_is_refused():
    """Hand arithmetic: balance 800, cap 400, a $75 request.

        $75 < the $125 minimum  ->  nothing is paid, nothing is reset, the MLL does not move

    Currently $75 is paid, the winning-day count is cleared and the MLL is pinned at $0 -
    three irreversible consequences bought with a request the firm would have rejected.
    """
    account = xfa_account()
    for _ in range(5):
        account.settle_day(160.0)
    assert account.payout_cap == 400.0

    paid = account.take_payout(PAYOUT_MINIMUM - 50.0)
    assert paid == 0.0, (
        f"paid ${paid:,.2f} on a request below the ${PAYOUT_MINIMUM:,.0f} minimum")


def test_the_payout_minimum_is_modelled_as_a_documented_rule():
    """UPDATED when the gap closed. This test used to assert the ABSENCE of a $125 rule.

    `topstep.py` carries a `Rule` for every published parameter it models, with a tier saying
    how well the number is known. The $125 payout minimum had none, which is why `take_payout`
    could not enforce it and would record a $75 withdrawal - irreversibly clearing the
    winning-day count and pinning the MLL for a payout that cannot happen. The rule now
    exists and is DOC tier, meaning it is read off a published Topstep page rather than
    inferred.
    """
    rules = {name: getattr(ts, name) for name in dir(ts)
             if isinstance(getattr(ts, name), ts.Rule)}
    minimum_rules = [n for n, r in rules.items()
                     if isinstance(r.value, (int, float)) and r.value == PAYOUT_MINIMUM]
    assert minimum_rules, f"no Rule carries the ${PAYOUT_MINIMUM:.0f} payout minimum"
    for n in minimum_rules:
        assert rules[n].confidence is ts.Confidence.DOC, (
            f"{n} holds the payout minimum at confidence {rules[n].confidence}; a published "
            f"figure must be read off the page, not inferred")
        assert rules[n].source.startswith("https://help.topstep.com/"), (
            f"{n} cites {rules[n].source!r}, which is not a Topstep help page")
        assert rules[n].quote, f"{n} carries no quoted text from the page"


# RATCHET CLEARED 2026-09-13: balance_at_last_payout and net_profit_since_payout; payout_eligible reads the window rather than total profit (DOC 8284215).
def test_eligibility_is_measured_since_the_last_payout_not_from_the_start():
    """Hand arithmetic, XFA, standard route:

        5 sessions of +800          balance 4,000   winning days 5   eligible
        payout: min(50% x 4,000, 2,000) = 2,000     balance 2,000    MLL pinned at 0
        then    -900                balance 1,100
        then    5 x +150            balance 1,850   winning days 5

        net profit SINCE the payout = 1,850 - 2,000 = -150   -> NOT eligible
        total profit since inception = 1,850 - 0    = +1,850 -> reported eligible

    The account is down since it last took money out and the model offers it another payout.
    """
    account = xfa_account()
    for _ in range(5):
        account.settle_day(800.0)
    assert account.take_payout() == 2_000.0
    balance_after_payout = account.balance
    assert balance_after_payout == 2_000.0

    account.settle_day(-900.0)
    for _ in range(5):
        account.settle_day(150.0)

    assert account.balance == 1_850.0
    assert account.winning_days == 5
    net_since_payout = account.balance - balance_after_payout
    assert net_since_payout == -150.0
    assert account.payout_eligible is False, (
        f"net since the last payout is ${net_since_payout:,.0f}; 8284215 requires it above "
        f"zero, but total_profit ${account.total_profit:,.0f} was tested instead")


# RATCHET CLEARED 2026-09-13: take_payout zeroes trading_days alongside winning_days (DOC 8284233, the 5-day count restarts).
def test_the_consistency_route_day_count_restarts_after_a_payout():
    """Hand arithmetic, XFA on the consistency route (3 days, best day <= 40% of total):

        3 sessions of +700     balance 2,100   trading days 3   best 700 / 2,100 = 33% <= 40%
        payout: min(50% x 2,100, 3,000) = 1,050 -> balance 1,050

        after it: days traded since the payout = 0, so the 3-day count must read 0 and the
        account must not be eligible again until it has traded three more sessions.

    Today `trading_days` is still 3 and `payout_eligible` is True with zero sessions traded.
    """
    account = xfa_account(consistency_route=True)
    for _ in range(3):
        account.settle_day(700.0)
    assert account.trading_days == 3
    assert account.payout_eligible is True
    assert account.take_payout() == 1_050.0

    assert account.trading_days == 0, (
        f"{account.trading_days} trading days survived the payout, so the account is "
        f"immediately eligible again (payout_eligible={account.payout_eligible})")


# ======================================================================================
# 5. POSITION LIMITS
# ======================================================================================

def test_five_es_is_the_documented_ceiling_and_a_sixth_is_refused():
    """8284197: a $50K account may hold 5 minis. The 5th is allowed, the 6th is not.

    Hand arithmetic: holding 0, an order for 5 ES fills at 5. Holding 5, an order for 1 more
    has room for 0, and a reduction to zero is a refusal however it is spelled.

    Source: """ + COMBINE_DOC
    assert ts.CONTRACTS[SIZE].value == (5, 50)

    gate = engine()
    first = gate(OrderIntent("ES", Side.BUY, 5))
    assert first.allowed is True and first.quantity == 5

    gate.state.contracts["ES"] = 5
    sixth = gate(OrderIntent("ES", Side.BUY, 1))
    assert sixth.allowed is False
    assert sixth.quantity == 0.0
    assert "max_contracts_per_symbol" in sixth.binding


def test_an_oversized_mini_order_in_a_listed_root_is_cut_to_the_cap():
    """30 ES on a 5-mini account is reduced to 5, not filled at 30.

    This is the half of the contract rule that DOES work, and it works only for the six roots
    `_caps()` names explicitly. The half that does not is pinned below.
    """
    decision = engine()(OrderIntent("ES", Side.BUY, 30))
    assert decision.allowed is True
    assert decision.quantity == 5
    assert "max_contracts_per_symbol" in decision.binding


# RATCHET CLEARED 2026-09-13: PropFirmProfile.contract_equivalence counts a listed symbol in micro-equivalents from the published per-symbol table, so 5 ES + 45 MES is 95 units against a 50-unit account.
def test_minis_and_micros_share_one_account_limit_at_ten_to_one():
    """Hand arithmetic on a $50K account, limit 50 micro-equivalents:

        5 ES   = 5 x 10 = 50 micro-equivalents   -> the account is FULL
        + 1 MES        = 51                      -> over the limit, must be refused
        + 45 MES       = 95                      -> 1.9x the limit

    `max_total_contracts` is 50 and the engine sees 5 + 45 = 50 raw contracts, so nothing
    binds.
    """
    gate = engine()
    gate.state.contracts["ES"] = 5           # the account is already at its mini ceiling

    one_more = gate(OrderIntent("MES", Side.BUY, 1))
    assert one_more.allowed is False, (
        "5 ES is 50 micro-equivalents, the whole $50K allowance; a 51st was accepted")


# RATCHET CLEARED 2026-09-13: the same equivalence, second face: an unlisted full-size root no longer slips the cap.
def test_an_unlisted_mini_root_is_still_held_to_the_five_contract_ceiling():
    """Hand arithmetic: ZB is a full-size contract, so 30 ZB is 6x a 5-mini allowance.

    `max_contracts_per_symbol` has no ZB entry, so `cap_sym` is None; the only remaining
    check is the total, which is 50 because it was populated from the MICRO column.
    """
    decision = engine()(OrderIntent("ZB", Side.BUY, 30))
    assert decision.quantity <= 5, (
        f"30 ZB was accepted at {decision.quantity:g} on a five-mini account")


# RATCHET CLEARED 2026-09-13: permitted_products is enforced before any sizing, and Topstep's list is built by calling instruments.get on each root at import, so a root this repo cannot resolve can never reach the list.
def test_a_product_the_account_may_not_trade_is_refused():
    """An unlisted, unspecced, unpriceable symbol must not reach a venue.

    Hand arithmetic is beside the point here: the correct size for a product the account may
    not hold is zero, whatever the caps say.
    """
    with pytest.raises(KeyError):
        inst.get("BTC")

    decision = engine()(OrderIntent("BTC", Side.BUY, 50))
    assert decision.allowed is False, (
        f"50 BTC accepted at {decision.quantity:g} with no permitted-products check")


def test_the_micro_column_is_ten_times_the_mini_column_at_every_size():
    """The 10:1 ratio the account-wide limit above should have been built on.

    The published table already encodes it; nothing consumes it as a ratio.
    Source: """ + COMBINE_DOC
    for size in ts.SIZES:
        minis, micros = ts.CONTRACTS[size].value
        assert micros == minis * 10, size


# RATCHET CLEARED 2026-09-13: express_funded defaults to a one-rung fallback ladder recorded as XFA_SCALING_FALLBACK, and XFA_SCALING stays an OWNER-tier gap saying the real rungs were never published.
def test_the_xfa_is_not_permitted_full_combine_size_at_a_zero_balance():
    """Hand arithmetic: the XFA opens at $0 with a $2,000 MLL.

    Five ES is $250 a point. A 40-point session range - ordinary for ES - is $10,000 against
    $2,000 of room. The Combine's 5 minis cannot be the XFA's opening allowance.
    """
    combine = ts.combine(SIZE)
    xfa = ts.express_funded(SIZE)
    assert xfa.starting_balance == 0.0
    assert xfa.max_drawdown == combine.max_drawdown == MLL

    assert xfa.contracts_allowed_at(0.0) < combine.contracts_allowed_at(0.0), (
        f"an XFA at a $0 balance is permitted {xfa.contracts_allowed_at(0.0)} contracts, the "
        f"same as a funded $50,000 Combine; XFA_SCALING is empty: {ts.XFA_SCALING.value!r}")


# ======================================================================================
# 6. THE MANDATORY FLAT DEADLINE
# ======================================================================================

def test_the_repo_already_records_the_three_ten_central_end_of_day():
    """`DLL_WINDOW` quotes the trading day as 5 PM CT - 3:10 PM CT.

    So the 15:10 CT deadline in the xfail below is not an outside claim: it is already in
    this module, quoted from Topstep, and simply not consulted by the flat rule.
    Source: """ + DLL_DOC
    assert ts.DLL_WINDOW.value[1] == MANDATORY_FLAT_CT
    assert "3:10 PM CT" in ts.DLL_WINDOW.quote


# RATCHET CLEARED 2026-09-13: flat_at_local_time 15:10 CT alongside flat_before_close_minutes, and flat_deadline_minutes takes the EARLIER of the two so the early-close behaviour of AUD-07 is kept.
def test_a_position_open_at_three_eleven_central_is_a_violation():
    """Hand arithmetic against a 16:00 CT close:

        15:10 CT  mandatory flat            minutes to close = 50
        15:11 CT  one minute late           minutes to close = 49   -> must_be_flat -> True
        15:45 CT  what the model enforces   minutes to close = 15

    The model answers False at 49 minutes, so 15:11 CT reads as a legal time to be long.
    """
    gate = engine()
    offset = gate.state.profile.flat_before_close_minutes
    assert offset == 15
    late = minutes_to_close(dt.time(15, 11))
    assert late == 49

    enforced = (dt.datetime.combine(dt.date(2026, 1, 5), CME_EQUITY_CLOSE_CT)
                - dt.timedelta(minutes=offset)).time()
    slip = minutes_to_close(MANDATORY_FLAT_CT) - offset
    assert gate.must_be_flat(late) is True, (
        f"at 15:11 CT ({late} minutes to a {CME_EQUITY_CLOSE_CT:%H:%M} CT close) the model "
        f"says the book may stay open; the deadline it enforces is "
        f"{enforced:%H:%M} CT, {slip} minutes past the published "
        f"{MANDATORY_FLAT_CT:%H:%M} CT")


def test_the_flat_rule_is_still_correct_in_shape_on_an_early_close():
    """Whatever the deadline should be, expressing it relative to the close is right.

    On a 13:00 CT early close a wall-clock constant would be 2h10m late; minutes-to-close is
    not. Asserted so a fix to the deadline does not throw away the property that is already
    correct (AUD-07).
    """
    import datetime as dt
    gate = engine()

    # On the SCHEDULED close the binding deadline is now the wall clock, 15:10 CT, which is
    # 50 minutes before a 16:00 CT close. That is the fix: the model used to enforce 15:45 CT,
    # 35 minutes late. Both of these were True-then-False around 15 minutes before the change.
    assert gate.must_be_flat(minutes_to_close=49) is True
    assert gate.must_be_flat(minutes_to_close=51) is False

    # On a 13:00 CT early close the wall clock is 2h10m stale and the minutes-to-close term
    # is what binds. Handing the gate the real close is what keeps AUD-07 intact: the deadline
    # is the EARLIER of the two, so it tracks the bell instead of a constant.
    assert gate.must_be_flat(minutes_to_close=15, session_close=dt.time(13, 0)) is True
    assert gate.must_be_flat(minutes_to_close=14, session_close=dt.time(13, 0)) is True
    assert gate.must_be_flat(minutes_to_close=16, session_close=dt.time(13, 0)) is False


def test_overnight_and_weekend_holds_are_both_refused():
    """Topstep is flat-by-close; neither an overnight nor a weekend carry is permitted."""
    profile = ts.combine(SIZE)
    assert profile.allow_overnight is False
    assert profile.allow_weekend is False
    gate = engine()
    assert gate.must_be_flat(5, is_last_session_of_week=True) is True
    assert gate.must_be_flat(5, is_last_session_of_week=False) is True


# ======================================================================================
# 7. COMMISSIONS
# ======================================================================================

# RATCHET CLEARED 2026-09-13: commission_round_turn is the published Topstep rate: ES/NQ 3.78, MES/MNQ 1.22.
def test_the_round_turn_commissions_are_the_published_topstep_rates():
    """Hand arithmetic on the size that matters:

        MES modelled  $1.00 round turn
        MES official  $1.22 round turn      -> 22 cents, 18% of the charge, undercharged
        ES  modelled  $4.00 round turn
        ES  official  $3.78 round turn      -> 22 cents overcharged (the safe direction)

    A 1,000-round-turn year in MES is $220 of edge the backtest keeps and the account does
    not.
    """
    modelled = {sym: inst.get(sym).commission_round_turn for sym in OFFICIAL_ROUND_TURN}
    assert modelled == OFFICIAL_ROUND_TURN, (
        f"modelled {modelled} vs official {OFFICIAL_ROUND_TURN}")


def test_the_cost_model_reads_the_commission_from_the_instrument_and_halves_it():
    """Whatever the constant is, `CostModel.for_contract` must be per SIDE, not per turn.

    This is the arithmetic between the constant above and every cost gate, so it is asserted
    separately: a fix to the constant must not be able to double the charge by accident.
    """
    from quant_brain.markets.futures_cme import execution_sim as ex
    for sym in ("ES", "MES"):
        model = ex.CostModel.for_contract(sym)
        assert model.commission_per_side == inst.get(sym).commission_round_turn / 2


# ======================================================================================
# 8. THE STATE MACHINE
# ======================================================================================
# The brief names five states: ACTIVE, PASSED, FAILED, LIQUIDATED, PAYOUT_ELIGIBLE. Topstep's
# progression is finer than that because Topstep's progression IS finer than that - passing a
# Combine and being funded are different states, and the XFA is a new account. The mapping is
# asserted explicitly rather than assumed, and then the exercises below are required to stay
# inside the declared set.

BRIEF_TO_TOPSTEP = {
    "ACTIVE": (ts.TopstepStage.TRADING_COMBINE, ts.TopstepStage.EXPRESS_FUNDED,
               ts.TopstepStage.LIVE_FUNDED),
    "PASSED": (ts.TopstepStage.COMBINE_PASSED,),
    "FAILED": (ts.TopstepStage.FAILED,),
    "LIQUIDATED": (ts.TopstepStage.LIQUIDATED,),
    "PAYOUT_ELIGIBLE": (ts.TopstepStage.PAYOUT_ELIGIBLE,),
}


def test_the_five_named_states_all_map_onto_declared_stages():
    """Every state the brief names exists in `TopstepStage`, and nothing is left unmapped."""
    mapped = {stage for stages in BRIEF_TO_TOPSTEP.values() for stage in stages}
    assert mapped == set(ts.TopstepStage), (
        f"unmapped stages: {set(ts.TopstepStage) - mapped}")
    assert ts.TopstepStage.FAILED.is_terminal
    assert ts.TopstepStage.LIQUIDATED.is_terminal
    assert not ts.TopstepStage.TRADING_COMBINE.is_terminal
    for stage in (ts.TopstepStage.EXPRESS_FUNDED, ts.TopstepStage.PAYOUT_ELIGIBLE,
                  ts.TopstepStage.LIVE_FUNDED):
        assert stage.is_funded


def test_no_undeclared_state_appears_anywhere_in_the_exercised_lifecycle():
    """Run the four lifecycle paths and collect every stage they produce.

    Paths: liquidation on an intraday touch, a Combine passed into an XFA, a payout round
    trip through PAYOUT_ELIGIBLE and back, and the external promotion to LIVE_FUNDED. Every
    stage observed must be a declared `TopstepStage`, and the transitions must be the ones
    the rulebook describes.
    """
    seen: set[ts.TopstepStage] = set()

    # (a) liquidation
    twin = tw.TopstepTwin(SIZE, payout_policy=tw.NEVER)
    liquidated = twin.run([day(0, 100.0, (-2_000.0, 100.0))])
    seen.add(liquidated.terminal)
    seen.update(stage for _d, stage in liquidated.transitions)

    # (b) Combine -> XFA
    passed = twin.run([day(i, 750.0, (200.0, 750.0)) for i in range(4)])
    seen.add(passed.terminal)
    seen.update(stage for _d, stage in passed.transitions)

    # (c) payout eligibility gained, taken, and lost again
    account = xfa_account()
    seen.add(account.stage)
    for _ in range(5):
        account.settle_day(160.0)
    seen.add(account.advance())
    assert account.stage is ts.TopstepStage.PAYOUT_ELIGIBLE
    account.take_payout()
    seen.add(account.stage)
    assert account.stage is ts.TopstepStage.EXPRESS_FUNDED
    seen.add(account.advance())

    # (d) the Risk Team's decision, which the strategy can never trigger by itself
    seen.add(account.promote_to_live())

    assert seen <= set(ts.TopstepStage), f"undeclared states: {seen - set(ts.TopstepStage)}"
    assert {ts.TopstepStage.LIQUIDATED, ts.TopstepStage.COMBINE_PASSED,
            ts.TopstepStage.EXPRESS_FUNDED, ts.TopstepStage.PAYOUT_ELIGIBLE,
            ts.TopstepStage.LIVE_FUNDED} <= seen
    # FAILED is declared and never entered by this path: a Topstep account that breaks a rule
    # is LIQUIDATED, and consistency raises the target rather than failing (8284208). Stated
    # so that a future state producing FAILED is a deliberate change, not a surprise.
    assert ts.TopstepStage.FAILED not in seen


def test_liquidation_is_absorbing_and_a_dead_account_refuses_every_order():
    """Nothing revives a liquidated account, and the risk gate stops trading immediately."""
    account = combine_account()
    account.mark(-2_500.0)
    assert account.advance() is ts.TopstepStage.LIQUIDATED
    account.mark(5_000.0)
    assert account.advance() is ts.TopstepStage.LIQUIDATED, "terminal means terminal"

    gate = engine()
    gate.state.balance = 47_000.0            # below the 48,000 floor
    decision = gate(OrderIntent("ES", Side.BUY, 1))
    assert decision.allowed is False
    assert "trailing_drawdown" in decision.binding


def test_going_live_is_an_external_decision_and_never_a_threshold():
    """10657969 makes the LFA a Risk Team decision, so `advance()` must never reach it."""
    account = xfa_account()
    for _ in range(20):
        account.settle_day(1_000.0)
        account.advance()
    assert account.stage is not ts.TopstepStage.LIVE_FUNDED
    assert account.promote_to_live() is ts.TopstepStage.LIVE_FUNDED

    dead = combine_account()
    dead.mark(-2_500.0)
    dead.advance()
    with pytest.raises(ValueError):
        dead.promote_to_live()


def test_outcomes_do_not_depend_on_the_unpublished_starting_balance():
    """Topstep never published the XFA's internal starting balance, so nothing may turn on it.

    The same P&L path is run against profiles opened at $50,000 and at $1,000,000. Every
    outcome - liquidation, the pass, the distance to the MLL - is stated relative to the
    start, so both must agree. If they ever diverge, an absolute balance has leaked into a
    rule that should be relative.
    """
    path = [day(0, -1_500.0, (-1_900.0, -1_500.0)), day(1, 900.0, (900.0,)),
            day(2, 3_700.0, (1_000.0, 3_700.0))]
    results = []
    for start in (50_000.0, 1_000_000.0):
        profile = ts.combine(SIZE, starting_balance=start)
        account = ts.TopstepAccount(profile=profile)
        for session in path:
            for mark in session.path:
                account.mark(mark)
                if account.breached():
                    break
            account.mark(0.0)
            account.settle_day(session.pnl)
            account.advance()
        results.append((account.stage, account.total_profit, account.distance_to_mll,
                        account.mll - profile.starting_balance))
    assert results[0] == results[1], f"outcome moved with the starting balance: {results}"


# ======================================================================================
# 9. THE RULEBOOK'S OWN GUARDS
# ======================================================================================

def test_an_unverified_rule_cannot_become_a_number_without_being_asked_for():
    """Fail closed: a below-DOC rule must raise rather than quietly supply a default."""
    owner_rule = ts.Rule(1.0, "not published", "owner brief", ts.Confidence.OWNER)
    with pytest.raises(ts.UnverifiedRule):
        owner_rule.require(ts.Confidence.DOC, what="a number that decides money")
    assert owner_rule.require(ts.Confidence.OWNER) == 1.0


def test_every_unresolved_rule_is_listed_so_it_can_be_read_before_spending_money():
    """`unresolved()` must name each below-DOC rule; a silent gap is the failure mode."""
    gaps = ts.unresolved()
    assert gaps, "unresolved() is empty - either everything is verified, or it stopped looking"
    assert all(rule.confidence < ts.Confidence.DOC for rule in gaps.values())
    assert gaps.get("xfa_scaling_plan") is ts.XFA_SCALING, (
        "the XFA scaling ladder is unpublished and its absence is exactly what makes "
        "test_the_xfa_is_not_permitted_full_combine_size_at_a_zero_balance fail; it must "
        f"stay on the unresolved list until the rungs are supplied. listed: {sorted(gaps)}")


def test_an_unknown_account_size_is_refused_rather_than_interpolated():
    """There is no $75K Topstep account, so there is no $75K answer."""
    with pytest.raises(KeyError):
        ts.combine(75_000)
    with pytest.raises(KeyError):
        ts.express_funded(75_000)
    with pytest.raises(KeyError):
        ts.combine(SIZE, reading="whatever_i_like")


def test_a_profile_round_trips_through_json_without_losing_a_rule():
    """A rule that disappears through serialisation is a limit that stops being enforced."""
    from quant_brain.markets.futures_cme.propfirm import PropFirmProfile

    original = ts.combine(SIZE, daily_loss_limit=DLL)
    import json
    restored = PropFirmProfile.from_dict(json.loads(original.to_json()))
    assert restored == original
    # And an unknown key is refused rather than ignored - a typo'd rule name silently
    # disabling a limit is the failure this whole module exists to prevent.
    payload = json.loads(original.to_json())
    payload["max_drawdwon"] = 999.0
    with pytest.raises(ValueError):
        PropFirmProfile.from_dict(payload)


def test_the_hybrid_trailing_mode_is_neither_eod_nor_intraday():
    """Modelling Topstep as either of the two common conventions is wrong in a known direction.

    Hand arithmetic on one session: the account marks +800 and closes +100.

        INTRADAY  peak follows the 800 mark -> floor rises to 48,800 on unrealized profit
        EOD       breach never tested intraday -> a -2,000 mark inside the day is invisible
        Topstep   floor advances on the CLOSE (+100 -> 48,100), breach tested on every mark

    Source: """ + MLL_DOC
    account = combine_account()
    account.mark(800.0)
    assert account.mll == 48_000.0, "an unrealized high must not ratchet the floor"
    account.mark(0.0)
    account.settle_day(100.0)
    assert account.mll == 48_100.0, "the close does ratchet it"
    assert ts.MLL_TRAILS.value is TrailingMode.EOD_TRAIL_INTRADAY_BREACH


def test_the_dll_protects_only_while_it_sits_above_the_mll():
    """Which limit fires is decided by which level is higher, not by test order.

    Hand arithmetic, $50K with the DLL armed at $1,000, after the balance has fallen to
    48,500 (peak still 50,000, so the MLL is 48,000):

        DLL level = 48,500 - 1,000 = 47,500
        MLL level =                  48,000    <- higher, so the equity reaches it FIRST

    An armed DLL therefore stops protecting the account exactly when it is needed most, and a
    model that tested the DLL first would report a survivable forced break where the real
    account is liquidated. Source: """ + DLL_DOC
    twin = tw.TopstepTwin(SIZE, daily_loss_limit=DLL, payout_policy=tw.NEVER)
    result = twin.run([
        day(0, -1_500.0, (-1_500.0,)),        # capped at -1,000 -> balance 49,000
        day(1, -500.0, (-500.0,)),            # balance 48,500
        day(2, -800.0, (-600.0, -800.0)),     # equity 47,700 -> through the 48,000 MLL
    ])
    assert result.terminal is ts.TopstepStage.LIQUIDATED
    assert "MLL" in result.breach_reason
    assert result.breach_day == dt.date(2026, 1, 7)


def test_a_profile_cannot_be_mutated_after_it_is_built():
    """`PropFirmProfile` is frozen: a rule set that can be edited at run time is not a rule set."""
    profile = ts.combine(SIZE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.max_drawdown = 10_000.0        # type: ignore[misc]
    # The supported way to vary one is an explicit copy, which is visible in a diff.
    looser = replace(profile, max_drawdown=10_000.0)
    assert profile.max_drawdown == MLL and looser.max_drawdown == 10_000.0


# ======================================================================================
# THE ELEVENTH, CLEARED 2026-09-14
# ======================================================================================

# RATCHET CLEARED 2026-09-14: the unit mismatch is fixed and the strict xfail that pinned it
# is gone. `MllAccount` gained a third member, `max_contracts_for(symbol) -> int | None`,
# implemented on `PropFirmProfile` (where the mini/micro equivalence table lives) and on
# `TopstepAccount` (which nets it against the open book). `core.sizing.enforce` and
# `twin.max_contracts` now ask for the ceiling in contracts of the symbol being sized
# instead of reading `contracts_allowed`, which stays and stays in micro-equivalents for
# display. ES on a fresh $50K Combine went from 5 / 10 / 20 / 40 contracts at a 2 / 1 / 0.5
# / 0.25-point stop to 5 at every one of them, binding "prop_firm" rather than
# "strategy_signal". `tests/test_contract_ceiling.py` is the full pin; this stays as the
# acceptance-level one.
def test_the_contract_ceiling_is_enforced_in_the_unit_the_caller_is_trading():
    """The account allowance and the sizer must agree on what a contract is."""
    from quant_brain.core import sizing as sz
    from quant_brain.markets.futures_cme import instruments as finst

    account = ts.TopstepAccount(ts.combine(SIZE))
    assert account.contracts_allowed == 50, "the published $50K total column, in micros"

    sizer = sz.PropFirmSizer()
    spec = finst.get("ES").spec
    worst = 0
    for stop_points in (2.0, 1.0, 0.5, 0.25):
        ctx = sz.SizeContext(spec=spec, prop_account=account, stop_distance=stop_points,
                             price=6_000.0, requested=1_000)
        decision = sz.enforce(sizer.name, ctx, sizer.propose(ctx))
        worst = max(worst, decision.contracts)
    assert worst <= 5, (
        f"the sizer proposed up to {worst} ES contracts on an account permitted five. The "
        f"allowance is in micro-equivalents and the sizer is counting minis.")


def test_the_micro_case_is_unaffected_which_is_why_this_has_not_bitten_yet():
    """Never an xfail: on a micro the two units coincide, so the cap was always enforced.

    This is the control that stopped the pin above from being read as "sizing is broken". It
    was broken for minis and correct for micros, and the futures funnel trades micros - which
    is exactly why a live unit mismatch sat here without producing a wrong number anyone
    noticed. It stays green across the fix, which is the point of a control.
    """
    from quant_brain.core import sizing as sz
    from quant_brain.markets.futures_cme import instruments as finst

    account = ts.TopstepAccount(ts.combine(SIZE))
    sizer = sz.PropFirmSizer()
    spec = finst.get("MES").spec
    ctx = sz.SizeContext(spec=spec, prop_account=account, stop_distance=0.25,
                         price=6_000.0, requested=1_000)
    decision = sz.enforce(sizer.name, ctx, sizer.propose(ctx))
    assert decision.contracts <= 50, (
        f"{decision.contracts} micros against a 50-micro allowance; the cap failed even in "
        f"the unit it is written in")
