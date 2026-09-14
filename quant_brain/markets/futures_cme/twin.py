"""The Topstep digital twin: one strategy's sessions, run through the whole lifecycle.

Part 4. `PropFirmSimulator` answers "does this account pass the evaluation?" That is the
wrong question for capital building, and answering only it would flatter Topstep badly.

Passing the Combine is not the payoff. It is the entry fee to a *second* absorbing barrier
that is materially harder than the first:

    Combine:  start at the size, $2,000 of room, hit a profit target.
    XFA:      start at $0, the SAME $2,000 of room, and no target - just payouts.

So an account that passes with a comfortable $3,100 of profit and a $2,000 buffer is
immediately reset to $0 profit with $2,000 of buffer, and now has to string together five
winning days of $150 before it can withdraw anything at all. Then the withdrawal itself takes
up to half the balance out while the MLL - locked at $0 by then - does not follow it down.
Every payout is therefore a risk decision that shortens the distance to liquidation, and the
twin exists to price that decision rather than assume it away.

WHAT THIS MODULE REFUSES TO DO
------------------------------
Topstep's Combine pricing was not on any page fetched, so `combine_fee` has no default. With
no fee supplied, `TwinResult.net_capital` is None and `gross_capital` is reported instead -
the twin will not quietly report a profit figure that omits the cost of the attempts. That is
Part 32's fail-closed rule applied to the economics rather than to the risk limits.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme.propfirm import PropFirmProfile


@dataclass(frozen=True)
class TwinDay:
    """One session, as the research harness already produces it, plus the intraday path.

    `path` is the within-session equity relative to the day's opening balance. It is optional
    because the existing harness does not emit it yet - but under Topstep's rule an absent
    path means the intraday breach test never runs, which understates risk. `strict_path`
    on the twin turns that silence into a refusal rather than an optimistic estimate.
    """

    day: dt.date
    pnl: float
    path: tuple[float, ...] = ()
    traded: bool = True

    @property
    def worst_mark(self) -> float:
        """The lowest point of the session, including the close."""
        return min((*self.path, self.pnl), default=self.pnl)


@dataclass(frozen=True)
class PayoutPolicy:
    """When to take money out. Not a formality - see the module docstring.

    `min_buffer_after` is the one parameter that matters. A payout reduces the balance while
    the MLL stays put, so withdrawing the full eligible amount the moment it is available
    maximises cash today and maximises the chance of losing the account tomorrow.
    """

    #: Never withdraw so much that less than this remains between equity and the MLL.
    min_buffer_after: float = 0.0
    #: Fraction of the eligible cap to request.
    fraction: float = 1.0
    #: Extra trading days to wait past first eligibility before withdrawing.
    wait_days: int = 0
    #: Stop withdrawing once this much has been taken in total. None means no ceiling.
    stop_after: float | None = None

    def amount(self, account: ts.TopstepAccount, days_eligible: int) -> float:
        if days_eligible < self.wait_days:
            return 0.0
        if self.stop_after is not None and account.total_paid_out >= self.stop_after:
            return 0.0
        want = account.payout_cap * self.fraction
        # The buffer floor binds against what is left after the withdrawal.
        room = account.distance_to_mll - self.min_buffer_after
        return max(0.0, min(want, room))


NEVER = PayoutPolicy(fraction=0.0)
#: Take everything the moment it is available. The aggressive baseline to measure against.
IMMEDIATE = PayoutPolicy()


@dataclass
class TwinResult:
    """What happened to one trader over one path of sessions."""

    terminal: ts.TopstepStage
    transitions: list[tuple[dt.date, ts.TopstepStage]] = field(default_factory=list)
    days: int = 0
    combine_attempts: int = 0
    combine_days: int | None = None          # days to pass the first Combine, None if never
    payouts: list[tuple[dt.date, float]] = field(default_factory=list)
    total_paid: float = 0.0
    fees_paid: float | None = None
    breach_day: dt.date | None = None
    breach_reason: str = ""
    min_buffer: float = 0.0
    min_buffer_funded: float = 0.0           # the buffer that matters after passing
    final_balance: float = 0.0
    path_supplied: bool = True

    @property
    def reached_funding(self) -> bool:
        return any(s.is_funded for _, s in self.transitions)

    @property
    def gross_capital(self) -> float:
        """Cash withdrawn. Not profit - fees are not deducted here."""
        return self.total_paid

    @property
    def net_capital(self) -> float | None:
        """Withdrawals net of the cost of the attempts, or None if the fee is unknown."""
        if self.fees_paid is None:
            return None
        return self.total_paid - self.fees_paid

    def summary(self) -> str:
        net = self.net_capital
        money = (f"net ${net:,.0f}" if net is not None
                 else f"gross ${self.gross_capital:,.0f} (fee unknown)")
        tail = f" breached {self.breach_day} - {self.breach_reason}" if self.breach_day else ""
        return (f"{self.terminal.value:<16} {self.days:>4}d  attempts {self.combine_attempts}  "
                f"payouts {len(self.payouts):>2} {money}  "
                f"min buffer ${self.min_buffer_funded:,.0f}{tail}")


class TopstepTwin:
    """Replays a strategy's sessions through the Topstep lifecycle, not just one evaluation.

    The account is rebuilt at each stage transition because Topstep genuinely rebuilds it:
    the XFA is a new account at $0, and a failed Combine means buying another one. Carrying a
    single mutable balance through would model a firm that does not exist.
    """

    def __init__(self, size: int, *, profit_target: float | None = None,
                 reading: str = ts.DEFAULT_READING,
                 daily_loss_limit: float | None = None,
                 consistency_route: bool = False,
                 payout_policy: PayoutPolicy = IMMEDIATE,
                 combine_fee: float | None = None,
                 max_combine_attempts: int = 1,
                 scaling: tuple[tuple[float, int], ...] | None = None,
                 strict_path: bool = True,
                 allow_unverified_target: bool = False):
        self.size = size
        self.reading = reading
        self.consistency_route = consistency_route
        self.policy = payout_policy
        # No default fee. Topstep's Combine pricing was not on any page fetched, and a
        # plausible-looking guess here would silently become the denominator of every
        # expected-capital number the branch produces.
        self.combine_fee = combine_fee
        self.max_combine_attempts = max_combine_attempts
        self.strict_path = strict_path
        self.combine_profile = ts.combine(
            size, profit_target=profit_target, reading=reading,
            daily_loss_limit=daily_loss_limit,
            allow_unverified_target=allow_unverified_target)
        self.xfa_profile = ts.express_funded(
            size, consistency_route=consistency_route,
            daily_loss_limit=daily_loss_limit, scaling=scaling)

    # -- one session, against whichever account is live -------------------------------------

    def _step(self, account: ts.TopstepAccount, day: TwinDay) -> tuple[bool, str]:
        """Apply one session. Returns (survived, reason).

        The order matters and follows the rulebook rather than convenience: the intraday
        breach test runs on every mark before the day is settled, because Topstep liquidates
        the moment equity touches the MLL and does not wait for the close.
        """
        dll = account.profile.daily_loss_limit
        # Both limits are equity LEVELS the day can fall through, and both are fixed for the
        # session: the MLL because it only advances at the close, the DLL because it is
        # measured from the day's opening balance. Which one fires is therefore decided by
        # which level is higher, not by the order the code happens to test them in - and
        # getting that backwards is not cosmetic. An armed DLL sitting above the MLL means
        # the account is flattened before it can ever reach the MLL, so arming it genuinely
        # removes intraday liquidation risk. An account already near its floor has the MLL
        # above the DLL, and then the DLL protects nothing.
        mll_level = account.mll
        dll_level = (account.balance - dll) if dll is not None else -math.inf

        for mark in day.path:
            account.mark(mark)
            hit_dll = account.equity <= dll_level
            hit_mll = account.equity <= mll_level
            if hit_dll and hit_mll:
                # Both crossed inside one coarse mark; the equity fell through the higher
                # level first, and that is the rule that actually fired.
                hit_mll = mll_level > dll_level
                hit_dll = not hit_mll
            if hit_mll:
                return False, (f"intraday equity {account.equity:,.0f} reached the MLL "
                               f"{mll_level:,.0f}")
            if hit_dll and dll is not None:      # dll_level is -inf when the DLL is off
                # 8284207: flat, cancelled, no new trades until 5 PM CT next session. The
                # day ends at the capped loss; the account survives.
                account.mark(0.0)
                account.settle_day(-dll, traded=day.traded)
                return (not account.breached()), "daily loss limit - session over"
        account.mark(0.0)
        pnl = day.pnl if dll is None else max(day.pnl, -dll)
        account.settle_day(pnl, traded=day.traded)
        if account.breached():
            return False, (f"end-of-day balance {account.balance:,.0f} reached the MLL "
                           f"{account.mll:,.0f}")
        return True, ""

    def run(self, sessions: Sequence[TwinDay]) -> TwinResult:
        if self.strict_path and any(not d.path for d in sessions):
            raise ValueError(
                "sessions without an intraday path cannot be run against Topstep's rules: "
                "the MLL breach is tested intraday on unrealized P&L, so an absent path "
                "silently skips the test and overstates survival. Supply `path`, or pass "
                "strict_path=False and treat the result as an upper bound.")

        result = TwinResult(terminal=ts.TopstepStage.TRADING_COMBINE,
                            path_supplied=all(bool(d.path) for d in sessions))
        account = ts.TopstepAccount(profile=self.combine_profile, reading=self.reading,
                                    consistency_route=self.consistency_route)
        result.combine_attempts = 1
        result.min_buffer = account.distance_to_mll
        result.min_buffer_funded = float("inf")
        days_eligible = 0
        started = 0

        for i, day in enumerate(sessions):
            result.days = i + 1
            survived, reason = self._step(account, day)
            # Only measured while the account is alive. Recording the distance on the
            # breaching day would make "minimum buffer" negative on every failed path, which
            # is not a buffer - it is the overshoot past a barrier the account never crossed
            # in reality, because Topstep liquidates at the touch.
            if survived:
                result.min_buffer = min(result.min_buffer, account.distance_to_mll)
                if account.stage.is_funded:
                    result.min_buffer_funded = min(result.min_buffer_funded,
                                                   account.distance_to_mll)
            if not survived:
                result.breach_day, result.breach_reason = day.day, reason
                if account.stage.is_funded:
                    # A funded account is gone for good; there is no re-entry inside a path.
                    account.stage = ts.TopstepStage.LIQUIDATED
                    result.transitions.append((day.day, account.stage))
                    break
                account.stage = ts.TopstepStage.LIQUIDATED
                result.transitions.append((day.day, account.stage))
                if result.combine_attempts >= self.max_combine_attempts:
                    break
                result.combine_attempts += 1
                started = i + 1
                account = ts.TopstepAccount(profile=self.combine_profile,
                                            reading=self.reading,
                                            consistency_route=self.consistency_route)
                result.transitions.append((day.day, ts.TopstepStage.TRADING_COMBINE))
                continue

            before = account.stage
            after = account.advance()
            if after is not before:
                result.transitions.append((day.day, after))
                if after is ts.TopstepStage.COMBINE_PASSED and result.combine_days is None:
                    result.combine_days = i + 1 - started
                if after is ts.TopstepStage.COMBINE_PASSED:
                    # Roll straight into the XFA: a new account at $0 with the same MLL.
                    account = ts.TopstepAccount(profile=self.xfa_profile,
                                                stage=ts.TopstepStage.EXPRESS_FUNDED,
                                                reading=self.reading,
                                                consistency_route=self.consistency_route)
                    result.transitions.append((day.day, ts.TopstepStage.EXPRESS_FUNDED))
                    result.min_buffer_funded = min(result.min_buffer_funded,
                                                   account.distance_to_mll)
                    days_eligible = 0

            if account.payout_eligible:
                days_eligible += 1
                amount = self.policy.amount(account, days_eligible)
                if amount > 0:
                    paid = account.take_payout(amount)
                    if paid > 0:
                        result.payouts.append((day.day, paid))
                        result.total_paid += paid
                        days_eligible = 0
                        result.min_buffer_funded = min(result.min_buffer_funded,
                                                       account.distance_to_mll)
            else:
                days_eligible = 0

        result.terminal = account.stage
        result.final_balance = account.balance
        if self.combine_fee is not None:
            result.fees_paid = self.combine_fee * result.combine_attempts
        if result.min_buffer_funded == float("inf"):
            # Never funded, so there is no funded buffer to report. 0.0 would read as "had
            # no room"; these paths simply never got there, and `reached_funding` says so.
            result.min_buffer_funded = 0.0
        return result


# ======================================================================================
# THE OBJECTIVE (Part 22)
# ======================================================================================

@dataclass
class TwinEvaluation:
    """The distribution over many paths. Part 6: not CAGR, not Sharpe.

    `p_funded` and `p_first_payout` are separated on purpose. Passing a Combine feels like
    the milestone and is the one most strategies are tuned for, but it earns nothing. The
    first payout is the first dollar, and the gap between the two rates is the cost of the
    second barrier.
    """

    label: str
    paths: int
    p_pass_combine: float
    p_funded: float
    p_first_payout: float
    p_liquidated: float
    median_days_to_pass: float | None
    mean_payouts: float
    mean_gross: float
    mean_net: float | None
    p05_net: float | None
    p05_min_buffer_funded: float
    fee_known: bool

    def summary(self) -> str:
        money = (f"E[net] ${self.mean_net:,.0f} (5th pct ${self.p05_net:,.0f})"
                 if self.mean_net is not None
                 else f"E[gross] ${self.mean_gross:,.0f} - FEE UNKNOWN, not a profit figure")
        days = (f"{self.median_days_to_pass:.0f}d" if self.median_days_to_pass is not None
                else "never")
        return (f"{self.label}: pass {self.p_pass_combine:.1%} -> paid "
                f"{self.p_first_payout:.1%} over {self.paths} paths, median to pass {days}, "
                f"{self.mean_payouts:.1f} payouts, {money}, "
                f"liquidated {self.p_liquidated:.1%}, "
                f"5th-pct funded buffer ${self.p05_min_buffer_funded:,.0f}")


def _pct(xs: Sequence[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    i = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return s[i]


def evaluate_twin(twin: TopstepTwin, paths: Sequence[Sequence[TwinDay]],
                  *, label: str = "") -> TwinEvaluation:
    """Run many session paths through the whole lifecycle and summarise the distribution.

    Paths are supplied rather than generated, for the same reason `propfirm.evaluate` does:
    how a strategy's sessions are resampled is a research decision with real statistical
    content, and baking one scheme in here would quietly override it.
    """
    results = [twin.run(p) for p in paths]
    n = len(results) or 1
    passed = [r for r in results if r.combine_days is not None]
    nets = [r.net_capital for r in results if r.net_capital is not None]
    days_to_pass = [r.combine_days for r in passed if r.combine_days is not None]
    return TwinEvaluation(
        label=label or twin.combine_profile.name,
        paths=len(results),
        p_pass_combine=len(passed) / n,
        p_funded=sum(r.reached_funding for r in results) / n,
        p_first_payout=sum(bool(r.payouts) for r in results) / n,
        p_liquidated=sum(r.terminal is ts.TopstepStage.LIQUIDATED for r in results) / n,
        median_days_to_pass=(statistics.median(days_to_pass) if days_to_pass else None),
        mean_payouts=sum(len(r.payouts) for r in results) / n,
        mean_gross=sum(r.gross_capital for r in results) / n,
        mean_net=(sum(nets) / len(nets)) if nets else None,
        p05_net=_pct(nets, 0.05) if nets else None,
        p05_min_buffer_funded=_pct([r.min_buffer_funded for r in results
                                    if r.reached_funding], 0.05),
        fee_known=twin.combine_fee is not None,
    )


def compare_policies(twin: TopstepTwin, paths: Sequence[Sequence[TwinDay]],
                     policies: dict[str, PayoutPolicy]) -> dict[str, TwinEvaluation]:
    """Price the payout decision, which is the twin's whole reason for existing.

    Withdrawing early converts buffer into cash that cannot be lost; withdrawing late keeps
    the buffer that lets the account survive to withdraw again. Neither dominates, and the
    answer depends on the strategy's own left tail - so it has to be measured per strategy
    rather than settled by a rule of thumb.
    """
    out: dict[str, TwinEvaluation] = {}
    for name, policy in policies.items():
        variant = _with_policy(twin, policy)
        out[name] = evaluate_twin(variant, paths, label=name)
    return out


def _with_policy(twin: TopstepTwin, policy: PayoutPolicy) -> TopstepTwin:
    clone = object.__new__(TopstepTwin)
    clone.__dict__.update(twin.__dict__)
    clone.policy = policy
    return clone


# ======================================================================================
# THE RISK BUDGET (Part 21)
# ======================================================================================

def risk_budget(account: ts.TopstepAccount, *, fraction: float = 0.25,
                floor: float = 0.0) -> float:
    """Dollars this account may risk on the next position.

    Anchored to `distance_to_mll` rather than to balance or equity, because the balance is
    not what kills the account, and the two diverge in both directions.

    A Combine at $53,000 with the floor locked at $50,000 has $3,000 of room. Sizing off the
    balance would put on roughly eighteen times the position the account can actually
    survive. An Express Funded Account three winning days in, at a $500 balance with the
    floor still at -$1,500, has $2,000 of room - four times its balance - and sizing off the
    balance there would leave a perfectly survivable account trading too small to make
    progress before the fee runs out.

    (The one case where the two agree is a locked XFA, where the floor sits at $0 and room
    is the balance by definition. That coincidence is why anchoring to the balance looks
    harmless until it is tried on a Combine.)
    """
    if fraction <= 0 or fraction > 1:
        raise ValueError(f"fraction must be in (0, 1], got {fraction}")
    return max(floor, account.distance_to_mll * fraction)


def max_contracts(account: ts.TopstepAccount, risk_per_contract: float, *,
                  fraction: float = 0.25, symbol: str | None = None) -> int:
    """Position size from the risk budget and the per-contract stop distance.

    Clamped by the firm's own contract ceiling, which is a hard rule rather than a
    preference. Returns 0 when the budget will not cover a single contract - which is the
    correct answer, not a rounding error to floor at one.

    `symbol` names the contract being sized, and the ceiling is then applied IN CONTRACTS OF
    IT: five ES or fifty MES on a $50K account, which is one allowance stated in two units.
    A root the account may not hold returns 0.

    Passing None keeps the historical clamp against `contracts_allowed`, which is the
    allowance in MICRO-EQUIVALENTS and is only a position size when the caller is sizing
    micros. It is not a safe default for a mini and it is not meant as one - it is the unit
    the account reports itself in, kept so that `max_contracts(a, 1.0)` still means "fifty
    micro-equivalents of room". Name the symbol whenever the answer will become an order.
    """
    if risk_per_contract <= 0:
        raise ValueError(f"risk_per_contract must be positive, got {risk_per_contract}")
    n = int(risk_budget(account, fraction=fraction) // risk_per_contract)
    cap = (account.contracts_allowed if symbol is None
           else account.max_contracts_for(symbol))
    return max(0, n if cap is None else min(n, cap))


# ======================================================================================
# PATH CONSTRUCTION
# ======================================================================================

def days_from_pnl(pnl: Sequence[float], start: dt.date = dt.date(2026, 1, 5), *,
                  path_fn: Callable[[float], tuple[float, ...]] | None = None,
                  ) -> list[TwinDay]:
    """Turn a session-P&L series into twin days on consecutive weekdays.

    `path_fn` builds the intraday path from the day's realized P&L. There is no default,
    because inventing an intraday shape is exactly the kind of assumption that decides
    whether a breach is seen - `u_shaped_path` is offered as an explicit, named choice with
    its own caveat rather than as a silent default.
    """
    out: list[TwinDay] = []
    day = start
    for x in pnl:
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        out.append(TwinDay(day=day, pnl=x, path=path_fn(x) if path_fn else ()))
        day += dt.timedelta(days=1)
    return out


def u_shaped_path(adverse: float = 1.5) -> Callable[[float], tuple[float, ...]]:
    """An intraday path that dips to `adverse` times the day's P&L before closing there.

    A crude stand-in for a real path and it must be labelled as one: it assumes every day's
    worst mark is proportional to its close, which is false in both directions - flat days
    can have violent excursions and big winners often had the worst drawdown of the month
    behind them. Use it to bound the sensitivity of a result to intraday shape, never as the
    estimate itself. The real fix is emitting the true path from the backtester.
    """
    if adverse < 1.0:
        raise ValueError("adverse must be at least 1.0, or the path never dips below "
                         "the close and the intraday test is decorative")

    def build(pnl: float) -> tuple[float, ...]:
        trough = -abs(pnl) * adverse if pnl >= 0 else pnl * adverse
        return (trough * 0.5, trough, pnl)

    return build


def with_daily_loss_limit(profile: PropFirmProfile, size: int) -> PropFirmProfile:
    """Switch on Topstep's optional DLL at the documented amount for the size."""
    return replace(profile, daily_loss_limit=ts.DLL_OPTIONAL[size].value)
