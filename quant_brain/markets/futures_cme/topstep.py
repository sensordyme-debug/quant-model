"""Topstep, as a machine-readable rulebook where every number carries its source.

Part 2 of the brief: use the official documentation as the authoritative source, do not rely
on memory, do not invent rules, record the exact effective date and source for every rule.

That last clause is why this module does not simply hold constants. Every parameter is a
`Rule` carrying the sentence it came from, the help-centre URL, the date it was retrieved,
and a `Confidence` tier. `combine()` and `express_funded()` refuse by default to build a
profile out of anything below `Confidence.DOC`, so an unverified number cannot silently
become a pass-probability estimate. Fail closed, as Part 32 requires.

    DOC     quoted verbatim from a Topstep help-centre page fetched on the retrieval date
    SEARCH  from Topstep's own site via a search summary; NOT verified on the page itself
    OWNER   not published anywhere reachable; the account holder must supply it

Sources, all retrieved 2026-09-12:
    8284197   Trading Combine Parameters
    8284204   What is the Maximum Loss Limit
    8284207   Daily Loss Limit in the Trading Combine and Express Funded Account
    8284208   Consistency at Topstep
    8284215   Express Funded Account Parameters
    10657969  Live Funded Account Parameters

THE RULE THAT DID NOT FIT THE GENERIC MODEL
--------------------------------------------
Topstep's Maximum Loss Limit is a hybrid the profile could not express before this branch:

    "The MLL updates at the end of each trading day but is monitored in real time
     throughout the session."                                                    (8284204)
    "Both realized and unrealized P&L count toward it."                          (8284204)
    "If your balance hits it at any point during the trading day, including on unrealized
     P&L, your account is liquidated immediately."                               (8284204)
    "Once it reaches your starting balance, it locks permanently."               (8284204)

The threshold advances on END-OF-DAY balance; the breach is tested INTRADAY including
unrealized P&L. Modelling it as EOD never tests the intraday path and understates breach
risk; modelling it as INTRADAY ratchets the floor on unrealized highs the real rule ignores
and overstates the trailing. Both errors are large and they point in opposite directions,
which is why `TrailingMode.EOD_TRAIL_INTRADAY_BREACH` exists.

WHAT THE DOCUMENTATION CONTRADICTS ITSELF ON
----------------------------------------------
One page, two incompatible readings of the Combine consistency rule (8284208):

    threshold    "Your single best day of profit must stay at or below 55% of your Profit
                  Target."
    calculation  "Best Day Profit / Total Profit = Best Day %"

"55% of your Profit Target" and "Best Day / Total Profit" are different tests, and the second
is strictly harder while the account is below target. The brief additionally states 50%,
where the page states 55%.

Default: **50% of total profit** - the lower of the two thresholds in play, with the
denominator the page's own calculation line specifies. 50 is unambiguously the stricter
threshold; the denominators do not order so simply, and it is worth being exact about why.
Below the target, total profit is the smaller denominator and "total" is the harder test.
At the moment a Combine is checked, total profit has reached or passed the target, so
"target" becomes the harder one, by exactly the overshoot. The two coincide when the target
is hit on the nose. So no single reading dominates everywhere, and `owner_target`
(50% of target) is the strictest at the moment of the check.

The default is chosen for the error direction rather than for dominance: understating the
pass rate is the conservative error before money is spent, and a strategy designed to hold
its best day under half of cumulative profit is comfortably inside every reading here. The
alternatives are named so the gap can be measured rather than argued about - see
`CONSISTENCY_READINGS` and `with_reading`.

**Confirm the live figure on your own dashboard before an evaluation is purchased.**

ONE AMBIGUITY THAT TURNS OUT NOT TO MATTER
--------------------------------------------
Topstep describes the 50K/100K/150K label as buying power rather than a starting cash
balance, and no page fetched states the Combine's opening balance. It does not matter here:
the MLL is a *relative* $2,000/$3,000/$4,500 trailing amount, the profit target is a
*relative* gain, and the lock level is the starting balance itself. Every quantity is
measured from the start, so shifting `starting_balance` by any constant leaves outcomes
unchanged. `test_qb_topstep.py` asserts that invariance rather than asserting an opening
balance the documentation never gave.
"""
from __future__ import annotations

import datetime as dt
import enum
import math
from dataclasses import dataclass, field, replace
from typing import Generic, TypeVar

from quant_brain.markets.futures_cme import instruments as inst
from quant_brain.markets.futures_cme.propfirm import PropFirmProfile, TrailingMode

RETRIEVED = dt.date(2026, 9, 12)

_HC = "https://help.topstep.com/en/articles/"
MLL_DOC = _HC + "8284204-what-is-the-maximum-loss-limit"
COMBINE_DOC = _HC + "8284197-trading-combine-parameters"
DLL_DOC = _HC + "8284207-what-is-the-daily-loss-limit-and-what-happens-if-i-exceed-it"
CONSISTENCY_DOC = _HC + "8284208-what-is-the-consistency-target"
XFA_DOC = _HC + "8284215-express-funded-account-parameters"
LFA_DOC = _HC + "10657969-live-funded-account-parameters"
PAYOUT_DOC = _HC + "8284233"
PRICING = _HC + "14289835"

#: topstep.com rather than the help centre. Both are Topstep-owned and both are
#: authoritative; they are separated here because they disagree on one row - see
#: COMBINE_COST_NO_ACTIVATION.
NAF = "https://www.topstep.com/no-activation-fee"

T = TypeVar("T")


class Confidence(enum.IntEnum):
    """How well-sourced a number is. Ordered, so `>=` is a usable gate."""

    OWNER = 0    # not published on any page reached; the account holder must supply it
    SEARCH = 1   # from Topstep's own site via a search summary, not verified on the page
    DOC = 2      # quoted verbatim from a help-centre page fetched on `retrieved`


class UnverifiedRule(RuntimeError):
    """Raised when a profile would have to rely on a rule below the required confidence.

    This is the fail-closed path. A number Topstep never published must not quietly become
    an input to a pass-probability estimate the owner then spends money on.
    """


@dataclass(frozen=True)
class Rule(Generic[T]):
    """One rulebook parameter and the evidence for it."""

    value: T
    quote: str
    source: str
    confidence: Confidence
    retrieved: dt.date = RETRIEVED
    note: str = ""

    def require(self, minimum: Confidence = Confidence.DOC, *, what: str = "") -> T:
        if self.confidence < minimum:
            raise UnverifiedRule(
                f"{what or 'rule'} is {self.confidence.name}, below the required "
                f"{minimum.name}: {self.note or self.quote} "
                f"[{self.source}, retrieved {self.retrieved}]")
        return self.value

    def cite(self) -> str:
        return (f'"{self.quote}" - {self.source}, retrieved {self.retrieved} '
                f'({self.confidence.name})')


# ======================================================================================
# THE RULEBOOK
# ======================================================================================

SIZES: tuple[int, ...] = (50_000, 100_000, 150_000)

#: 8284197. "| Account Size | Max Contracts | Max Micros |" - stored as (minis, micros).
CONTRACTS: dict[int, Rule[tuple[int, int]]] = {
    50_000: Rule((5, 50), "$50K | 5 | 50", COMBINE_DOC, Confidence.DOC),
    100_000: Rule((10, 100), "$100K | 10 | 100", COMBINE_DOC, Confidence.DOC),
    150_000: Rule((15, 150), "$150K | 15 | 150", COMBINE_DOC, Confidence.DOC),
}

#: 8284204, Trading Combine table. The same figures carry to the Express Funded Account,
#: whose balance starts at $0 so the limit starts at minus the amount.
MLL: dict[int, Rule[float]] = {
    50_000: Rule(2_000.0, "$50K $2,000", MLL_DOC, Confidence.DOC),
    100_000: Rule(3_000.0, "$100K $3,000", MLL_DOC, Confidence.DOC),
    150_000: Rule(4_500.0, "$150K $4,500", MLL_DOC, Confidence.DOC),
}

MLL_TRAILS = Rule(
    TrailingMode.EOD_TRAIL_INTRADAY_BREACH,
    "The MLL updates at the end of each trading day but is monitored in real time "
    "throughout the session. Both realized and unrealized P&L count toward it.",
    MLL_DOC, Confidence.DOC,
    note="EOD-trailing threshold, intraday breach test. Neither plain EOD nor plain INTRADAY.")

MLL_LOCKS = Rule(
    True, "Once it reaches your starting balance, it locks permanently.",
    MLL_DOC, Confidence.DOC,
    note="For the XFA, whose balance starts at $0, this is the MLL amount reached: 'Once "
         "your balance reaches $2,000, the MLL locks at $0 permanently.'")

MLL_BREACH = Rule(
    "liquidate",
    "If your balance hits it at any point during the trading day, including on unrealized "
    "P&L, your account is liquidated immediately.",
    MLL_DOC, Confidence.DOC)

#: 8284207. Optional in the Combine and the XFA; automatic in the Live Funded Account.
DLL_OPTIONAL: dict[int, Rule[float]] = {
    50_000: Rule(1_000.0, "$50K Account: $1,000", DLL_DOC, Confidence.DOC),
    100_000: Rule(2_000.0, "$100K Account: $2,000", DLL_DOC, Confidence.DOC),
    150_000: Rule(3_000.0, "$150K Account: $3,000", DLL_DOC, Confidence.DOC),
}

DLL_IS_OPTIONAL = Rule(
    True,
    "The Daily Loss Limit (DLL) is optional in the Trading Combine and Express Funded "
    "Account (XFA). It's automatic in the Live Funded Account (LFA).",
    DLL_DOC, Confidence.DOC)

#: The value is the answer to "does a DLL hit end the account?" - it does not.
DLL_ENDS_ACCOUNT = Rule(
    False,
    "Triggering it is not a rule violation - it's a forced break for the rest of that "
    "session.",
    DLL_DOC, Confidence.DOC,
    note="Open positions flattened, pending orders cancelled, no new trades until 5 PM CT "
         "next session. 'Account stays eligible for funding. Resume tomorrow.'")

DLL_WINDOW = Rule(
    (dt.time(17, 0), dt.time(15, 10)),
    "Net P&L hits or exceeds the DLL during the trading day (5 PM CT - 3:10 PM CT)",
    DLL_DOC, Confidence.DOC, note="Central Time; the trading day wraps midnight.")

#: The wall-clock flat deadline. Same sentence as DLL_WINDOW, read for what it says about
#: the END of the trading day: the day runs 5 PM CT to 3:10 PM CT, so 3:10 PM CT is when the
#: book must be flat. The model used to enforce this as `flat_before_close_minutes=15`
#: against a 16:00 CT close - 15:45 CT, 35 minutes late - which made a position held from
#: 15:10 to 15:45 CT a rule violation the model reported as compliant, every single session.
MANDATORY_FLAT = Rule(
    dt.time(15, 10),
    "Net P&L hits or exceeds the DLL during the trading day (5 PM CT - 3:10 PM CT)",
    DLL_DOC, Confidence.DOC,
    note="A CLOCK, not an offset from the close. It is carried on the profile alongside "
         "`flat_before_close_minutes` and the EARLIER of the two binds, so the deadline is "
         "right at 15:10 CT on a normal day without losing the offset's correctness on an "
         "early close (AUD-07).")

#: The CME equity-index daily close in Central Time, which is the clock MANDATORY_FLAT is
#: measured against. An EXCHANGE fact rather than a Topstep rule, so it is a constant and not
#: a `Rule`: this module's tiers describe how well a TOPSTEP page supports a number, and
#: pinning a DOC tier on a cmegroup.com schedule would abuse them. A caller trading a complex
#: that closes elsewhere, or a day the bell moves, passes its own close to
#: `PropFirmRiskEngine.must_be_flat` and the deadline follows it.
CME_EQUITY_CLOSE = dt.time(16, 0)

# --- consistency ------------------------------------------------------------------------
COMBINE_CONSISTENCY_DOC = Rule(
    0.55, "Your single best day of profit must stay at or below 55% of your Profit Target.",
    CONSISTENCY_DOC, Confidence.DOC,
    note="The same page's calculation line uses a different denominator; see below.")

COMBINE_CONSISTENCY_DENOMINATOR = Rule(
    "total", "Best Day Profit / Total Profit = Best Day %",
    CONSISTENCY_DOC, Confidence.DOC,
    note="Contradicts the threshold sentence on the same page, which says 'of your Profit "
         "Target'. Both readings are kept in CONSISTENCY_READINGS.")

COMBINE_CONSISTENCY_OWNER = Rule(
    0.50, "the current documentation specifies a 50% threshold for the Trading Combine",
    "owner brief, 2026-09-12", Confidence.OWNER,
    note="Owner-asserted. Every Topstep page reachable on 2026-09-13 says 55%, and the "
         "consistency article settles the denominator with its own worked example "
         "(1,600/3,000 = 53%). Retained on the record; NOT the default.")

COMBINE_CONSISTENCY_EXCEEDED = Rule(
    "target_rises",
    "If it exceeds that, your Profit Target increases. You'll need to earn more to pass.",
    CONSISTENCY_DOC, Confidence.DOC,
    note="Exceeding consistency does NOT fail a Combine, it raises the bar. Modelled as "
         "not-yet-passed, never as Outcome.FAILED_CONSISTENCY.")

XFA_CONSISTENCY = Rule(
    0.40, "Your Consistency % must be 40% or below to be Payout eligible.",
    CONSISTENCY_DOC, Confidence.DOC)

XFA_CONSISTENCY_DENOMINATOR = Rule(
    "total", "Largest Single-Day Net Profit / Total Net Profit = Consistency %",
    CONSISTENCY_DOC, Confidence.DOC, note="Unambiguous for the XFA, unlike the Combine.")

XFA_CONSISTENCY_EXCEEDED = Rule(
    "keep_trading",
    "If your Consistency % exceeds 40%, keep trading. As you earn more net profit, the "
    "percentage will naturally come down.",
    CONSISTENCY_DOC, Confidence.DOC,
    note="Blocks a payout, does not fail the account.")

COMBINE_CONSISTENCY_BOUNDARY = Rule(
    "inclusive", "Your single best day of profit must stay AT OR BELOW 55% of your Profit "
                 "Target.",
    CONSISTENCY_DOC, Confidence.DOC, retrieved=dt.date(2026, 9, 13),
    note="'At or below' is inclusive, and 8284099's '<= 55% of total profits' agrees, so "
         "inclusive is the default. It is recorded as a READING rather than compiled into a "
         "comparison operator because a day at exactly 55.00% is where the two sides differ "
         "and where a pass is decided, and because the threshold sentence is also read as a "
         "strict bound elsewhere. Both are in CONSISTENCY_READINGS; nothing here picks one "
         "silently.")

#: The readings in play, so the difference between them can be measured instead of argued.
#: An entry is (threshold, denominator) or (threshold, denominator, boundary):
#:
#:     threshold    the share of the denominator the best day may reach
#:     denominator  "total" divides by total profit, "target" by the profit target
#:     boundary     "inclusive" admits a day AT the threshold, "exclusive" refuses it
#:
#: A two-element entry means the boundary the page's own wording gives - "at or below", i.e.
#: inclusive - which is why the four published readings keep that shape and why the
#: exclusive halves are named separately rather than replacing them. `_reading` normalises
#: both forms, so a reading is always (threshold, denominator, boundary) by the time anything
#: compares a number with it, and `with_reading` switches the boundary exactly as it switches
#: the denominator. Before this, the denominator was a reading and the boundary was a
#: hard-coded `<=` in one property - an ambiguity resolved in an operator, where nobody could
#: see it or measure it.
CONSISTENCY_READINGS: dict[str, tuple[float, str] | tuple[float, str, str]] = {
    "doc_calc": (0.55, "total"),      # DEFAULT: settled by the page's own worked example
    "doc_text": (0.55, "target"),     # the threshold sentence read literally
    "strict": (0.50, "total"),        # the owner brief's figure; unsupported on any page
    "owner_target": (0.50, "target"),
    # The same two published denominators read with a STRICT boundary. 8284208 says "at or
    # below", so these are not the default; they exist so the cost of the other reading can
    # be measured on a real path instead of asserted, exactly as the denominators are.
    "doc_calc_exclusive": (0.55, "total", "exclusive"),
    "doc_text_exclusive": (0.55, "target", "exclusive"),
}

#: What a reading means when it does not name a boundary.
DEFAULT_BOUNDARY = COMBINE_CONSISTENCY_BOUNDARY.value

#: RESOLVED 2026-09-13. The ambiguity recorded above was real but is now settled, and by the
#: article's own worked example rather than by argument:
#:
#:     "$50K account: $1,600 best day / $3,000 total profit = 53%  Consistency Target met."
#:
#: 1,600/3,000 = 53%, so the denominator is TOTAL PROFIT, not the profit target - the
#: calculation line was right and the threshold sentence's "of your Profit Target" is loose
#: wording. And the threshold is 55%: topstep.com/no-activation-fee prints "55%" beside every
#: account size, and 8284099 says "best trading day <= 55% of total profits".
#:
#: The 50% figure came from the owner's brief and is supported by no page reachable today. It
#: is kept as `strict` because designing to it is harmless, but it is no longer the default:
#: modelling a rule stricter than the real one understates the pass rate, and a research
#: platform should model the rule that exists.
DEFAULT_READING = "doc_calc"

# --- passing the Combine --------------------------------------------------------------
#: VERIFIED 2026-09-13 on topstep.com/no-activation-fee, which prints the profit target
#: beside the monthly price for each size, and independently corroborated by the worked
#: example on the consistency article ("$50K account: $1,600 best day / $3,000 total
#: profit") and by the LFA page quoting the same three figures as reserve-unlock targets.
#: This was the repository's single largest owner blocker and it is now closed.
COMBINE_PROFIT_TARGET: dict[int, Rule[float]] = {
    50_000: Rule(3_000.0, "$50K Buying Power ... Profit Target $3,000", NAF, Confidence.DOC),
    100_000: Rule(6_000.0, "$100K Buying Power ... Profit Target $6,000", NAF, Confidence.DOC),
    150_000: Rule(9_000.0, "$150K Buying Power ... Profit Target $9,000", NAF, Confidence.DOC),
}

#: Monthly cost. Two published paths, and the two official pages DISAGREE on the
#: no-activation-fee row - recorded rather than reconciled, because picking one silently
#: would bury a real discrepancy in a number that feeds every expected-capital figure.
COMBINE_COST: dict[int, Rule[float]] = {
    50_000: Rule(49.0, "$50K ... $49/month (Standard)", PRICING, Confidence.DOC),
    100_000: Rule(99.0, "$100K ... $99/month (Standard)", PRICING, Confidence.DOC),
    150_000: Rule(199.0, "$150K ... $199/month (Standard)", PRICING, Confidence.DOC),
}
COMBINE_COST_NO_ACTIVATION: dict[int, Rule[float]] = {
    50_000: Rule(95.0, "$50K ... $95/month (No Activation Fee)", PRICING, Confidence.DOC,
                 note="topstep.com/no-activation-fee says $85 for the same row. The two "
                      "official pages disagree; confirm at checkout."),
    100_000: Rule(149.0, "$100K ... $149/month (No Activation Fee)", PRICING, Confidence.DOC,
                  note="topstep.com/no-activation-fee says $129 for the same row."),
    150_000: Rule(229.0, "$150K ... $229/month (No Activation Fee)", PRICING, Confidence.DOC,
                  note="topstep.com/no-activation-fee says $199 for the same row."),
}

COMBINE_MIN_DAYS = Rule(
    0, "NOT STATED", COMBINE_DOC, Confidence.OWNER,
    note="No minimum-trading-days requirement appeared on any Combine page fetched. "
         "Modelled as none. If your dashboard shows one, pass min_trading_days.")

# --- Express Funded Account ---------------------------------------------------------------
XFA_STARTS_AT_ZERO = Rule(
    0.0, "Each Express Funded Account starts with a $0 balance", XFA_DOC, Confidence.DOC)
XFA_WINNING_DAYS = Rule(
    5, "5 winning days with at least $150 profit each", XFA_DOC, Confidence.DOC)
XFA_WINNING_DAY_MIN = Rule(
    150.0, "at least $150 profit each", XFA_DOC, Confidence.DOC)
#: PER ACCOUNT SIZE. The previous single constant used the $150K row for every size, which
#: overstated a $50K account's payout ceiling by 2.5x - in the flattering direction, on the
#: size most people actually trade. The source page states the $150K figures unqualified in
#: its summary text and only the table is per-size, which is how the error survived review.
XFA_STANDARD_CAP_BY_SIZE: dict[int, Rule[float]] = {
    50_000: Rule(2_000.0, "$50K | XFA Standard | $2,000", PAYOUT_DOC, Confidence.DOC),
    100_000: Rule(3_000.0, "$100K | XFA Standard | $3,000", PAYOUT_DOC, Confidence.DOC),
    150_000: Rule(5_000.0, "$150K | XFA Standard | $5,000", PAYOUT_DOC, Confidence.DOC),
}
XFA_CONSISTENCY_CAP_BY_SIZE: dict[int, Rule[float]] = {
    50_000: Rule(3_000.0, "$50K | XFA Consistency | $3,000", PAYOUT_DOC, Confidence.DOC),
    100_000: Rule(4_000.0, "$100K | XFA Consistency | $4,000", PAYOUT_DOC, Confidence.DOC),
    150_000: Rule(6_000.0, "$150K | XFA Consistency | $6,000", PAYOUT_DOC, Confidence.DOC),
}

#: "Max Payout per request: 50% of your account balance up to the cap below." (8284233)
XFA_STANDARD_CAP = Rule(
    5_000.0, "max 50% of balance up to $5,000", XFA_DOC, Confidence.DOC,
    note="The $150K row. Kept for the $150K case only; use XFA_STANDARD_CAP_BY_SIZE.")
XFA_BALANCE_SHARE = Rule(
    0.50, "50% of balance", XFA_DOC, Confidence.DOC)
XFA_CONSISTENCY_MIN_DAYS = Rule(
    3, "at least 3 days with at least 1 trade per day", XFA_DOC, Confidence.DOC)
XFA_CONSISTENCY_CAP = Rule(
    6_000.0, "up to $6,000", XFA_DOC, Confidence.DOC,
    note="The $150K row. Use XFA_CONSISTENCY_CAP_BY_SIZE; the ceiling is per size.")

#: "After each Payout: Your Maximum Loss Limit (MLL) resets to $0 permanently, and your
#: 5-day count restarts." (8284233, retrieved 2026-09-13)
MLL_RESETS_ON_PAYOUT = Rule(
    True,
    "After each Payout: Your Maximum Loss Limit (MLL) resets to $0 permanently, and your "
    "5-day count restarts.",
    PAYOUT_DOC, Confidence.DOC,
    note="This is what makes a payout a risk decision rather than a cash transfer: the "
         "balance falls by the amount withdrawn and the floor does NOT follow it down. "
         "Taking the maximum at the first opportunity therefore buys cash by spending the "
         "entire buffer that keeps the account alive.")
#: The floor on a withdrawal REQUEST. Enforced in `TopstepAccount.take_payout`, and the
#: enforcement is not cosmetic: a payout clears the winning-day count and pins the MLL at the
#: lock level permanently, so recording a $75 withdrawal the firm would have rejected spends
#: two irreversible things to buy cash that never arrives.
PAYOUT_MINIMUM = Rule(
    125.0, "Minimum Payout Request: $125", PAYOUT_DOC, Confidence.DOC,
    retrieved=dt.date(2026, 9, 13),
    note="A twin that can withdraw below the minimum overstates cash available early and "
         "understates the buffer it costs, on the exact decision the twin exists to price.")

PROFIT_SPLIT = Rule(0.90, "90/10", XFA_DOC, Confidence.DOC, note="90% to the trader.")
MAX_ACTIVE_XFA = Rule(5, "up to 5 active Express Funded Accounts", XFA_DOC, Confidence.DOC)

XFA_SCALING = Rule(
    (),
    "Follow the Scaling Plan - the max contracts you can hold at a time - based on your "
    "current account balance",
    XFA_DOC, Confidence.OWNER,
    note="The rule exists and is quoted; the ladder's rungs were not published. Populate "
         "`scaling` from your own account before trading an XFA, or simulated size will be "
         "too large at low balances - which is the direction that flatters results.")

XFA_SCALING_FALLBACK = Rule(
    0.10,
    "Follow the Scaling Plan - the max contracts you can hold at a time - based on your "
    "current account balance",
    XFA_DOC, Confidence.OWNER, retrieved=dt.date(2026, 9, 13),
    note="A STAND-IN, not Topstep's ladder, and it is in force whenever `scaling` is not "
         "supplied. The rungs are unpublished (see XFA_SCALING) but the previous behaviour - "
         "no ladder at all - simulated a $0 XFA at the full Combine allowance, 5 minis "
         "against the same $2,000 MLL a funded $50,000 Combine has. Five ES is $250 a point: "
         "an ordinary 40-point session range is $10,000 against $2,000 of room, so full size "
         "there is where accounts actually die, and it is the flattering direction. The "
         "stand-in permits a TENTH of the account-wide allowance at every balance - five "
         "micro-equivalents at $50K, so no mini at all - which is the smallest whole rung of "
         "the 10:1 ratio the published contract table is built on, and is conservative by "
         "construction rather than a guess at what Topstep publishes in an image. Supply "
         "`scaling` from your own dashboard before trading an XFA.")

# --- Live Funded Account --------------------------------------------------------------------
LFA_DLL: dict[int, Rule[float]] = {
    50_000: Rule(2_000.0, "$50K LFA Daily Loss Limit: $2,000", LFA_DOC, Confidence.DOC),
    100_000: Rule(3_000.0, "$100K LFA Daily Loss Limit: $3,000", LFA_DOC, Confidence.DOC),
    150_000: Rule(4_500.0, "$150K LFA Daily Loss Limit: $4,500", LFA_DOC, Confidence.DOC),
}
LFA_RESERVE_UNLOCK: dict[int, Rule[float]] = {
    50_000: Rule(3_000.0, "Profit Target to Unlock Reserve: $3,000", LFA_DOC, Confidence.DOC),
    100_000: Rule(6_000.0, "Profit Target to Unlock Reserve: $6,000", LFA_DOC, Confidence.DOC),
    150_000: Rule(9_000.0, "Profit Target to Unlock Reserve: $9,000", LFA_DOC, Confidence.DOC),
}
LFA_TRADEABLE_SHARE = Rule(
    0.20, "20% available to trade immediately - minimum $10,000", LFA_DOC, Confidence.DOC)
LFA_RESERVE_INCREMENTS = Rule(
    4, "80% held in Reserve - released in 4 increments of 25%", LFA_DOC, Confidence.DOC)
LFA_ENTRY = Rule(
    "risk_team",
    "Once the Risk Team determines you're ready, your options are to move to Live or close "
    "your Express Funded Account.",
    LFA_DOC, Confidence.DOC,
    note="Discretionary, not a mechanical threshold. The state machine models the LFA "
         "transition as an external decision the strategy cannot trigger.")


def unresolved() -> dict[str, Rule]:
    """Every rule below DOC confidence. Print this before spending money.

    Shorter than it was: the Combine profit target and the monthly cost were verified on
    2026-09-13 and moved to DOC, which closed the largest owner blocker this repository
    had. What remains is genuinely unpublished rather than merely unfound.
    """
    return {
        "combine_min_trading_days": COMBINE_MIN_DAYS,
        # Published only as an image on the XFA page - no text, alt-text or caption anywhere.
        "xfa_scaling_plan": XFA_SCALING,
        # The number actually in force while the rungs above stay unpublished. Listed
        # separately because "the ladder is unknown" and "here is what we size on instead"
        # are two different things to read before spending money.
        "xfa_scaling_fallback": XFA_SCALING_FALLBACK,
        # Retained so the owner's figure stays on the record, but no longer the default:
        # 55% is what every official page says today.
        "combine_consistency_owner_figure": COMBINE_CONSISTENCY_OWNER,
    }


def rulebook() -> str:
    """The whole rulebook with its citations, for the provenance record (Part 27)."""
    lines = [f"TOPSTEP RULEBOOK - retrieved {RETRIEVED}", "=" * 78]
    groups: list[tuple[str, dict[str, Rule]]] = [
        ("contracts", {f"${k // 1000}K": v for k, v in CONTRACTS.items()}),
        ("maximum loss limit", {f"${k // 1000}K": v for k, v in MLL.items()}),
        ("MLL mechanics", {"trails": MLL_TRAILS, "locks": MLL_LOCKS, "breach": MLL_BREACH}),
        ("daily loss limit", {f"${k // 1000}K": v for k, v in DLL_OPTIONAL.items()}),
        ("DLL mechanics", {"optional": DLL_IS_OPTIONAL, "ends account": DLL_ENDS_ACCOUNT,
                           "window": DLL_WINDOW}),
        ("session", {"mandatory flat": MANDATORY_FLAT}),
        ("consistency", {"combine": COMBINE_CONSISTENCY_DOC,
                         "combine denominator": COMBINE_CONSISTENCY_DENOMINATOR,
                         "combine boundary": COMBINE_CONSISTENCY_BOUNDARY,
                         "combine (owner)": COMBINE_CONSISTENCY_OWNER,
                         "combine exceeded": COMBINE_CONSISTENCY_EXCEEDED,
                         "xfa": XFA_CONSISTENCY,
                         "xfa denominator": XFA_CONSISTENCY_DENOMINATOR,
                         "xfa exceeded": XFA_CONSISTENCY_EXCEEDED}),
        ("profit target", {f"${k // 1000}K": v for k, v in COMBINE_PROFIT_TARGET.items()}
         | {"min days": COMBINE_MIN_DAYS}),
        ("express funded", {"starts at": XFA_STARTS_AT_ZERO, "winning days": XFA_WINNING_DAYS,
                            "winning day min": XFA_WINNING_DAY_MIN,
                            "standard cap": XFA_STANDARD_CAP,
                            "balance share": XFA_BALANCE_SHARE,
                            "consistency days": XFA_CONSISTENCY_MIN_DAYS,
                            "consistency cap": XFA_CONSISTENCY_CAP,
                            "payout minimum": PAYOUT_MINIMUM,
                            "profit split": PROFIT_SPLIT, "max accounts": MAX_ACTIVE_XFA,
                            "scaling": XFA_SCALING,
                            "scaling stand-in": XFA_SCALING_FALLBACK}),
        ("live funded", {f"DLL ${k // 1000}K": v for k, v in LFA_DLL.items()}
         | {f"reserve unlock ${k // 1000}K": v for k, v in LFA_RESERVE_UNLOCK.items()}
         | {"tradeable": LFA_TRADEABLE_SHARE, "increments": LFA_RESERVE_INCREMENTS,
            "entry": LFA_ENTRY}),
    ]
    for title, rules in groups:
        lines.append("")
        lines.append(title.upper())
        for key, rule in rules.items():
            lines.append(f"  {key:<22} {rule.value!r:<34} {rule.confidence.name}")
            lines.append(f"  {'':<22} {rule.cite()}")
            if rule.note:
                lines.append(f"  {'':<22} NOTE: {rule.note}")
    return "\n".join(lines)


# ======================================================================================
# PROFILES
# ======================================================================================

def _reading(name: str) -> tuple[float, str, str]:
    """One reading, always as (threshold, denominator, boundary).

    A two-element entry in CONSISTENCY_READINGS means the boundary the page's own wording
    gives, so it is filled in here rather than at each of the four call sites - the whole
    point of the change is that no caller decides the boundary in a comparison operator.
    """
    if name not in CONSISTENCY_READINGS:
        raise KeyError(f"unknown consistency reading {name!r}; "
                       f"known: {sorted(CONSISTENCY_READINGS)}")
    entry = CONSISTENCY_READINGS[name]
    threshold, denominator = entry[0], entry[1]
    boundary = entry[2] if len(entry) >= 3 else DEFAULT_BOUNDARY
    return threshold, denominator, boundary


#: The roots a Topstep account may hold, as this repository is able to model them. Topstep
#: publishes a product list per account (8284197); these are the roots on it for which
#: `instruments` carries a contract spec, which is the honest boundary of what can be sized
#: or costed here. `_permitted_products` refuses at IMPORT time if one of them ever stops
#: resolving, because a permitted product with no multiplier is a wrong position waiting to
#: happen rather than an error anybody would see.
MINI_ROOTS: tuple[str, ...] = ("ES", "NQ", "RTY", "YM", "CL", "GC")
MICRO_ROOTS: tuple[str, ...] = ("MES", "MNQ", "M2K", "MYM", "MCL", "MGC")


def _permitted_products() -> tuple[str, ...]:
    for sym in MINI_ROOTS + MICRO_ROOTS:
        inst.get(sym)          # KeyError here is the fail-closed path, at import
    return MINI_ROOTS + MICRO_ROOTS


PERMITTED_PRODUCTS: tuple[str, ...] = _permitted_products()


def _caps(size: int) -> tuple[int, dict[str, int]]:
    """(account-wide allowance in MICRO-equivalents, per-symbol contract caps).

    The two are one allowance in two units - 5 minis OR 50 micros at 10:1, per account
    (8284197) - which is why the profile is built with `contract_equivalence=True`: the
    engine reads the ratio off this table instead of counting 5 ES and 45 MES as 50 raw
    contracts on a 50-micro account.
    """
    minis, micros = CONTRACTS[size].require(what=f"contract caps at ${size:,}")
    per_symbol = {sym: minis for sym in MINI_ROOTS}
    per_symbol.update({sym: micros for sym in MICRO_ROOTS})
    return micros, per_symbol


def _fallback_scaling(size: int) -> tuple[tuple[float, int], ...]:
    """The stand-in XFA ladder, in the same micro-equivalent units as `_caps`.

    See XFA_SCALING_FALLBACK for why a tenth of the account-wide allowance, and why a
    stand-in exists at all rather than the profile refusing to build: an XFA profile that
    cannot be constructed cannot be checked, simulated or compared, and the twin's second
    barrier - which is the binding one - would simply disappear from every estimate.
    """
    micros, _ = _caps(size)
    rung = max(1, int(round(micros * XFA_SCALING_FALLBACK.value)))
    return ((0.0, rung),)


def combine(size: int, *, profit_target: float | None = None,
            reading: str = DEFAULT_READING,
            daily_loss_limit: float | None = None,
            min_trading_days: int | None = None,
            starting_balance: float | None = None,
            allow_unverified_target: bool = False) -> PropFirmProfile:
    """A Trading Combine profile.

    `profit_target` is required in substance: pass the number from your own dashboard, or
    set `allow_unverified_target=True` to accept the SEARCH-tier figure knowingly. Omitting
    both raises `UnverifiedRule` rather than guessing at the one number that decides whether
    a simulated account passes.

    `daily_loss_limit` defaults to None because the DLL is optional in the Combine
    (8284207). Pass `DLL_OPTIONAL[size].value` to model it switched on.

    `starting_balance` defaults to the size label. Outcomes are invariant to it - see the
    module docstring - and it is exposed only so that invariance can be tested.
    """
    if size not in SIZES:
        raise KeyError(f"no documented Topstep account at ${size:,}; known: {list(SIZES)}")
    if profit_target is None:
        profit_target = COMBINE_PROFIT_TARGET[size].require(
            Confidence.SEARCH if allow_unverified_target else Confidence.DOC,
            what=f"Combine profit target at ${size:,}")
    threshold, denominator, boundary = _reading(reading)
    micros, per_symbol = _caps(size)
    start = float(size) if starting_balance is None else float(starting_balance)
    return PropFirmProfile(
        name=f"TOPSTEP_COMBINE_{size // 1000}K",
        starting_balance=start,
        trailing_mode=MLL_TRAILS.require(what="MLL trailing convention"),
        max_drawdown=MLL[size].require(what=f"MLL at ${size:,}"),
        trailing_locks_at=start if MLL_LOCKS.value else None,
        daily_loss_limit=daily_loss_limit,
        daily_loss_ends_account=DLL_ENDS_ACCOUNT.value,
        profit_target=profit_target,
        min_trading_days=(COMBINE_MIN_DAYS.value if min_trading_days is None
                          else min_trading_days),
        # The generic engine's consistency check divides by total profit, which is exactly
        # the "total" reading. Under "target" the denominator is different, so the engine is
        # given no share to enforce and `TopstepAccount` makes the comparison instead -
        # otherwise the two layers would apply two different tests and the stricter would
        # silently win.
        max_single_day_profit_share=(threshold if denominator == "total" else None),
        # The boundary travels with the threshold so the engine and `TopstepAccount` cannot
        # end up applying opposite sides of 55.00% to the same day.
        max_single_day_share_boundary=boundary,
        max_total_contracts=micros,
        max_contracts_per_symbol=per_symbol,
        contract_equivalence=True,
        permitted_products=PERMITTED_PRODUCTS,
        allow_overnight=False,
        allow_weekend=False,
        flat_at_local_time=MANDATORY_FLAT.require(what="mandatory flat deadline"),
        regular_close_local_time=CME_EQUITY_CLOSE,
        profit_split=PROFIT_SPLIT.value,
    )


def express_funded(size: int, *, consistency_route: bool = False,
                   daily_loss_limit: float | None = None,
                   scaling: tuple[tuple[float, int], ...] | None = None) -> PropFirmProfile:
    """An Express Funded Account profile.

    Starts at a $0 balance with the MLL from the Combine size passed, and the MLL locks at $0
    once the balance reaches that MLL amount - which `trailing_locks_at=0` produces on its
    own, with no separate per-size lock constant to get wrong.

    `scaling` defaults to the STAND-IN ladder in `XFA_SCALING_FALLBACK`, not to nothing. The
    real rungs are unpublished and still listed in `unresolved()`; what changed is that an
    absent ladder used to mean "the full Combine allowance", so a $0-balance XFA carrying the
    same $2,000 MLL as a funded $50,000 Combine was simulated at 5 minis. Pass your own
    `scaling` before trading one.
    """
    if size not in SIZES:
        raise KeyError(f"no documented Topstep account at ${size:,}; known: {list(SIZES)}")
    micros, per_symbol = _caps(size)
    return PropFirmProfile(
        name=f"TOPSTEP_XFA_{size // 1000}K" + ("_CONSISTENCY" if consistency_route else ""),
        starting_balance=XFA_STARTS_AT_ZERO.require(what="XFA starting balance"),
        trailing_mode=MLL_TRAILS.require(what="MLL trailing convention"),
        max_drawdown=MLL[size].require(what=f"MLL at ${size:,}"),
        trailing_locks_at=0.0,
        daily_loss_limit=daily_loss_limit,
        daily_loss_ends_account=DLL_ENDS_ACCOUNT.value,
        profit_target=None,          # an XFA has no target; it has payout eligibility
        min_trading_days=(XFA_CONSISTENCY_MIN_DAYS.value if consistency_route
                          else XFA_WINNING_DAYS.value),
        max_single_day_profit_share=(XFA_CONSISTENCY.value if consistency_route else None),
        max_total_contracts=micros,
        max_contracts_per_symbol=per_symbol,
        contract_equivalence=True,
        permitted_products=PERMITTED_PRODUCTS,
        allow_overnight=False,
        allow_weekend=False,
        flat_at_local_time=MANDATORY_FLAT.require(what="mandatory flat deadline"),
        regular_close_local_time=CME_EQUITY_CLOSE,
        payout_on_pass=(XFA_CONSISTENCY_CAP_BY_SIZE[size].value if consistency_route
                        else XFA_STANDARD_CAP_BY_SIZE[size].value),
        profit_split=PROFIT_SPLIT.value,
        # XFA_SCALING.value is still () - the published rungs remain unknown - so an omitted
        # ladder falls back to the documented stand-in rather than to no limit at all.
        scaling=(scaling if scaling is not None
                 else (XFA_SCALING.value or _fallback_scaling(size))),
    )


def with_reading(profile: PropFirmProfile, reading: str) -> PropFirmProfile:
    """The same profile under a different reading of the consistency rule.

    Switches the boundary as well as the denominator: both are reading-level ambiguities in
    Topstep's own pages, and a switch that moved one while leaving the other compiled into an
    operator would make the comparison unmeasurable in exactly the case that decides a pass.
    """
    threshold, denominator, boundary = _reading(reading)
    return replace(profile, name=f"{profile.name}_{reading}",
                   max_single_day_profit_share=(threshold if denominator == "total"
                                                else None),
                   max_single_day_share_boundary=boundary)


def profiles(*, allow_unverified_target: bool = True) -> dict[str, PropFirmProfile]:
    """Ready-made profiles for every documented size and route.

    `allow_unverified_target` defaults True here and False in `combine()` on purpose: this
    helper exists for exploration and tests, where the SEARCH-tier target is fine once it is
    acknowledged, while the constructor's default protects the path to a purchase decision.
    """
    out: dict[str, PropFirmProfile] = {}
    for size in SIZES:
        k = size // 1000
        out[f"combine_{k}k"] = combine(size, allow_unverified_target=allow_unverified_target)
        out[f"xfa_{k}k"] = express_funded(size)
        out[f"xfa_{k}k_consistency"] = express_funded(size, consistency_route=True)
    return out


# ======================================================================================
# THE ACCOUNT AS A STATE MACHINE
# ======================================================================================

class TopstepStage(str, enum.Enum):
    """Where an account sits in the Topstep progression.

    `FAILED` and `LIQUIDATED` are absorbing. `PAYOUT_ELIGIBLE` is a state rather than an
    event because eligibility is a standing condition that can be lost again - a payout
    resets the winning-day count, and a large day can push the consistency percentage back
    above 40%.
    """

    TRADING_COMBINE = "trading_combine"
    COMBINE_PASSED = "combine_passed"
    EXPRESS_FUNDED = "express_funded"
    PAYOUT_ELIGIBLE = "payout_eligible"
    LIVE_FUNDED = "live_funded"
    #: RESERVED, and deliberately unreachable today. Nothing in this module produces FAILED:
    #: every way a Topstep account ends is a LIQUIDATION (8284204 - the MLL liquidates
    #: immediately), a DLL hit is a forced break and not a violation (8284207), and exceeding
    #: consistency RAISES the target rather than failing the account (8284208). It is
    #: declared because the brief's five-state vocabulary names it and because a firm-level
    #: rule violation that is not a liquidation - a banned product, a prohibited strategy - is
    #: a real category this progression would need. The day something enters it, say so
    #: loudly: `tests/test_propfirm_acceptance.py` asserts that no exercised path produces it,
    #: so making it reachable is a deliberate change to that test and not a side effect.
    FAILED = "failed"
    LIQUIDATED = "liquidated"

    @property
    def is_terminal(self) -> bool:
        return self in (TopstepStage.FAILED, TopstepStage.LIQUIDATED)

    @property
    def is_funded(self) -> bool:
        """Trading firm capital rather than an evaluation."""
        return self in (TopstepStage.EXPRESS_FUNDED, TopstepStage.PAYOUT_ELIGIBLE,
                        TopstepStage.LIVE_FUNDED)


@dataclass
class TopstepAccount:
    """The Topstep-specific layer over the generic account arithmetic.

    Deliberately separate from `propfirm.AccountState`, which stays firm-agnostic. This holds
    the progression, the payout bookkeeping and the consistency percentage - none of which
    belongs in a class shared with every other firm.
    """

    profile: PropFirmProfile
    stage: TopstepStage = TopstepStage.TRADING_COMBINE
    #: NaN is the "not supplied" sentinel rather than None or 0.0. None would make every
    #: downstream arithmetic expression Optional for no benefit, and 0.0 cannot be a
    #: sentinel here because it is the Express Funded Account's real opening balance.
    balance: float = math.nan
    equity: float = math.nan
    peak_eod_balance: float = math.nan
    daily_pnl: list[float] = field(default_factory=list)
    winning_days: int = 0
    trading_days: int = 0
    payouts_taken: int = 0
    total_paid_out: float = 0.0
    #: The balance immediately AFTER the most recent payout, or None while none has been
    #: taken. 8284215 measures payout eligibility on net profit SINCE the last payout, which
    #: `total_profit` (balance - starting_balance) never restarts: an account down $150 since
    #: it last withdrew was being reported eligible to withdraw again.
    balance_at_last_payout: float | None = None
    consistency_route: bool = False
    reading: str = DEFAULT_READING
    #: Set by the first payout and never cleared. See MLL_RESETS_ON_PAYOUT.
    mll_reset_by_payout: bool = False
    #: Contracts currently open, by root; only the absolute size is read, so either sign
    #: works. Empty is a flat book, which is what an account between trades is.
    #:
    #: Here rather than only on `propfirm.AccountState` because `max_contracts_for` has to
    #: answer with the HEADROOM under the account-wide allowance, and headroom is not a
    #: property of the profile. Three ES consume thirty of the fifty micro-equivalents; a
    #: ceiling that ignored them would hand the same fifty out again to the next symbol.
    open_contracts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if math.isnan(self.balance):
            self.balance = self.profile.starting_balance
        if math.isnan(self.equity):
            self.equity = self.balance
        self.peak_eod_balance = (self.balance if math.isnan(self.peak_eod_balance)
                                 else max(self.peak_eod_balance, self.balance))
        _reading(self.reading)          # fail fast on a typo'd reading name

    # -- the numbers Part 3 requires the account to expose ---------------------------------

    @property
    def mll(self) -> float:
        """The Maximum Loss Limit right now, as an equity level.

        A payout pins it at the lock level permanently (8284233: "resets to $0 permanently"),
        which for an XFA is $0. Modelled explicitly rather than relying on the trailing
        arithmetic having already reached the lock, because a payout can be taken before it
        has - and in that case the real rule is more generous than the trailing model.
        """
        if self.mll_reset_by_payout and self.profile.trailing_locks_at is not None:
            return self.profile.trailing_locks_at
        return self.profile.floor_for(self.peak_eod_balance)

    @property
    def mll_locked(self) -> bool:
        """True once the threshold has stopped following the balance up."""
        lock = self.profile.trailing_locks_at
        if lock is None or self.profile.max_drawdown is None:
            return False
        return self.peak_eod_balance - self.profile.max_drawdown >= lock

    @property
    def distance_to_mll(self) -> float:
        """Dollars of equity between here and liquidation. The real risk budget."""
        return self.equity - self.mll

    @property
    def total_profit(self) -> float:
        return self.balance - self.profile.starting_balance

    @property
    def best_day(self) -> float:
        return max(self.daily_pnl, default=0.0)

    @property
    def consistency_denominator(self) -> str:
        return _reading(self.reading)[1]

    @property
    def consistency_limit(self) -> float:
        return _reading(self.reading)[0]

    @property
    def consistency_boundary(self) -> str:
        """Which side complies: "inclusive" admits a day AT the limit, "exclusive" does not."""
        return _reading(self.reading)[2]

    @property
    def consistency_pct(self) -> float | None:
        """Best day over the denominator this account's reading uses.

        None when the denominator is unavailable - no profit yet under "total", or no target
        configured under "target". None means "not yet measurable", never "compliant".
        """
        if self.consistency_denominator == "target":
            target = self.profile.profit_target
            return None if not target else self.best_day / target
        if self.total_profit <= 0:
            return None
        return self.best_day / self.total_profit

    @property
    def consistency_ok(self) -> bool:
        """Compliant under THIS account's reading, boundary included.

        The comparison used to be a hard-coded `<=`, which resolved a published ambiguity in
        an operator: 8284208 says "at or below 55%" and 8284099 says "<= 55% of total
        profits", but the threshold sentence is also read as a strict bound, and a day at
        exactly 55.00% is precisely where the two differ and precisely where a pass is
        decided. The boundary is now part of the reading, like the denominator.
        """
        pct = self.consistency_pct
        if pct is None:
            return True
        if self.consistency_boundary == "exclusive":
            return pct < self.consistency_limit
        return pct <= self.consistency_limit

    @property
    def profit_target_remaining(self) -> float | None:
        target = self.effective_profit_target
        return None if target is None else max(0.0, target - self.total_profit)

    @property
    def effective_profit_target(self) -> float | None:
        """The target after the consistency penalty (8284208: "your Profit Target increases").

        The page does not say by how much. The smallest increase consistent with the rule is
        the one that makes the best day exactly compliant - earn until best_day / total_profit
        falls to the limit - so that is what is modelled. It is a lower bound on the real
        penalty rather than a guess at its size, which keeps the error on the optimistic side
        of a number Topstep did not publish, and `unresolved()` records that it is unknown.
        """
        target = self.profile.profit_target
        if target is None:
            return None
        if self.consistency_denominator == "target" or self.consistency_ok:
            return target
        return max(target, self.best_day / self.consistency_limit)

    @property
    def contracts_allowed(self) -> int | None:
        """The account-wide allowance at this balance, in MICRO-EQUIVALENTS.

        The unit matters: the published table's total column is the micro count, and since
        `contract_equivalence` a mini consumes ten of these units. 50 here means fifty micros
        or five minis, not fifty of whatever a caller happens to be trading.

        THIS IS NOT A POSITION SIZE. It is kept, in this unit, because the CLI and the twin
        report the allowance the way Topstep publishes it, and because it is the denominator
        `open_equivalents` is measured against. Anything sizing an order wants
        `max_contracts_for`, which returns the ceiling in contracts of the symbol being
        traded; reading this number as one permitted 50 ES on a five-ES account.
        """
        return self.profile.contracts_allowed_at(self.total_profit)

    @property
    def open_equivalents(self) -> float:
        """The open book measured in the allowance's own unit (micro-equivalents).

        Mirrors `propfirm.AccountState.total_equivalents`, which counts the same thing for
        the simulated book; this counts the live one so the ceiling can be net of it.
        """
        return sum(self.profile.contract_units(sym.upper()) * abs(qty)
                   for sym, qty in self.open_contracts.items())

    def max_contracts_for(self, symbol: str) -> int | None:
        """The ceiling on `symbol` right now, IN CONTRACTS OF `symbol`. None means none set.

        The member of the `core.sizing.MllAccount` protocol that carries the unit. `core`
        may not import `markets`, so the mini/micro equivalence cannot travel to the sizer
        as a table; it travels as an answer, computed here where the table lives, to a
        question the sizer is able to ask - "how many of THIS may I hold?".

        On a fresh $50K Combine: 5 for ES or NQ, 50 for MES or MNQ, 0 for a root Topstep
        does not permit. Net of `open_contracts`, so three ES leave room for twenty MES.
        """
        return self.profile.max_contracts_for(
            symbol, profit=self.total_profit, held_equivalents=self.open_equivalents)

    @property
    def net_profit_since_payout(self) -> float:
        """Profit since the last withdrawal - what 8284215 measures eligibility on.

        Identical to `total_profit` until the first payout, and the two diverge permanently
        after it. `total_profit` is balance minus the STARTING balance and never restarts, so
        an account that has lost money since it last took cash out still reads as profitable
        against a $0 XFA opening balance.
        """
        base = (self.profile.starting_balance if self.balance_at_last_payout is None
                else self.balance_at_last_payout)
        return self.balance - base

    @property
    def payout_eligible(self) -> bool:
        """Whether a payout could be requested now, on this account's route (8284215).

        Measured SINCE THE LAST PAYOUT, not from inception: 8284215 requires net profit above
        zero since the last withdrawal, and 8284233 restarts the day count with it. The
        consistency route's percentage uses the same window, because `daily_pnl` is cleared by
        a payout and dividing a since-payout best day by an inception-to-date total would mix
        two clocks and read low - in the flattering direction.

        The XFA consistency denominator is unambiguous in the source, so this uses net profit
        directly rather than the Combine's configurable reading.
        """
        net = self.net_profit_since_payout
        if not self.stage.is_funded or net <= 0:
            return False
        if self.consistency_route:
            pct = self.best_day / net
            return (self.trading_days >= XFA_CONSISTENCY_MIN_DAYS.value
                    and pct <= XFA_CONSISTENCY.value)
        return self.winning_days >= XFA_WINNING_DAYS.value

    @property
    def payout_cap(self) -> float:
        """The most withdrawable now: 50% of balance, capped by the route's ceiling.

        The ceiling is per ACCOUNT SIZE and the profile carries it, rather than being read
        from a module constant - the constant was the $150K row and applying it to a $50K
        account overstated the ceiling 2.5x.
        """
        cap = self.profile.payout_on_pass or float("inf")
        return max(0.0, min(self.balance * XFA_BALANCE_SHARE.value, cap))

    # -- transitions ------------------------------------------------------------------------

    def settle_day(self, pnl: float, *, traded: bool = True) -> None:
        """Book one session and advance the end-of-day trailing peak."""
        self.balance += pnl
        self.equity = self.balance
        self.daily_pnl.append(pnl)
        if traded:
            self.trading_days += 1
        if pnl >= XFA_WINNING_DAY_MIN.value:
            self.winning_days += 1
        # The MLL advances here and nowhere else. This single line is the difference between
        # Topstep's rule and an intraday-trailing firm's.
        self.peak_eod_balance = max(self.peak_eod_balance, self.balance)

    def mark(self, unrealized: float) -> None:
        """Move the intraday mark. Does NOT advance the MLL - Topstep's does not."""
        self.equity = self.balance + unrealized

    def breached(self) -> bool:
        """Equity at or below the MLL. Tested on EQUITY because unrealized P&L counts."""
        return self.equity <= self.mll

    def combine_passed(self) -> tuple[bool, str]:
        """Has the Combine been passed? Refuses rather than guessing at an unknown target."""
        if self.profile.profit_target is None:
            return False, ("no profit target configured; Topstep published none on any page "
                           "fetched. Supply it from your dashboard.")
        base = self.profile.profit_target
        target = self.effective_profit_target or base
        if self.consistency_denominator == "target" and not self.consistency_ok:
            return False, (f"best day {self.best_day:,.0f} is "
                           f"{self.consistency_pct:.0%} of the {base:,.0f} target, above the "
                           f"{self.consistency_limit:.0%} limit")
        if self.total_profit < target:
            if target > base:
                return False, (
                    f"profit {self.total_profit:,.0f} below the consistency-raised target "
                    f"{target:,.0f} (base {base:,.0f}; best day {self.best_day:,.0f} is "
                    f"{self.consistency_pct:.0%} of profit, limit "
                    f"{self.consistency_limit:.0%})")
            return False, f"profit {self.total_profit:,.0f} below target {target:,.0f}"
        if self.trading_days < self.profile.min_trading_days:
            return False, (f"{self.trading_days} trading days, "
                           f"{self.profile.min_trading_days} required")
        return True, f"target {target:,.0f} met within the consistency limit"

    def advance(self) -> TopstepStage:
        """Move the state machine one step if the conditions for a move are met.

        LIVE_FUNDED is never entered here: 10657969 makes it a Risk Team decision rather than
        a threshold, so nothing the strategy does may trigger it. `promote_to_live()` exists
        to make that an explicit external act.
        """
        if self.stage.is_terminal:
            return self.stage
        if self.breached():
            self.stage = TopstepStage.LIQUIDATED
            return self.stage
        if self.stage is TopstepStage.TRADING_COMBINE and self.combine_passed()[0]:
            self.stage = TopstepStage.COMBINE_PASSED
        elif self.stage is TopstepStage.COMBINE_PASSED:
            self.stage = TopstepStage.EXPRESS_FUNDED
        elif self.stage is TopstepStage.EXPRESS_FUNDED and self.payout_eligible:
            self.stage = TopstepStage.PAYOUT_ELIGIBLE
        elif self.stage is TopstepStage.PAYOUT_ELIGIBLE and not self.payout_eligible:
            self.stage = TopstepStage.EXPRESS_FUNDED
        return self.stage

    def promote_to_live(self) -> TopstepStage:
        """The Risk Team's decision, modelled as an external input (LFA_ENTRY)."""
        if not self.stage.is_funded:
            raise ValueError(f"cannot go live from {self.stage.value}")
        self.stage = TopstepStage.LIVE_FUNDED
        return self.stage

    def take_payout(self, amount: float | None = None) -> float:
        """Withdraw, and reset everything a payout resets. Returns what was actually paid.

        8284233: "After each Payout: your Maximum Loss Limit resets to $0 permanently, and
        your 5-day count restarts." So the winning-day count, the daily series and the
        TRADING-day count all restart, and the profit clock restarts with them (8284215
        measures the next payout on net profit since this one). The trading-day count is the
        consistency route's whole eligibility test - three days with a trade - and leaving it
        standing made an account eligible again the instant a payout settled, having traded
        nothing since.

        A request below the published $125 minimum is REFUSED outright rather than paid in
        part: nothing moves, no count clears, the MLL stays where it is. That is not
        pedantry - recording a payout the firm would have rejected clears the winning-day
        count and pins the MLL at the lock level permanently, spending two irreversible
        things for cash that never arrives.

        The balance falls by the amount withdrawn while the MLL does not follow it down -
        which is why a payout is a risk decision and not just a cash transfer, and why
        `distance_to_mll` should be checked after taking one.
        """
        if not self.payout_eligible:
            return 0.0
        want = self.payout_cap if amount is None else amount
        paid = max(0.0, min(self.payout_cap, want))
        if paid < PAYOUT_MINIMUM.value:
            return 0.0
        self.balance -= paid
        self.equity = self.balance
        self.total_paid_out += paid
        self.payouts_taken += 1
        self.mll_reset_by_payout = True
        self.winning_days = 0
        self.trading_days = 0
        self.daily_pnl.clear()
        # The next payout is measured from HERE, not from the account's opening balance.
        self.balance_at_last_payout = self.balance
        self.stage = TopstepStage.EXPRESS_FUNDED
        return paid

    def describe(self) -> str:
        pct = self.consistency_pct
        return (f"{self.stage.value:<16} bal {self.balance:>10,.0f}  "
                f"MLL {self.mll:>10,.0f}{'L' if self.mll_locked else ' '} "
                f"room {self.distance_to_mll:>9,.0f}  "
                f"days {self.trading_days:>3} win {self.winning_days:>3}  "
                f"consistency {f'{pct:.0%}' if pct is not None else '   -'}  "
                f"size {self.contracts_allowed}")
