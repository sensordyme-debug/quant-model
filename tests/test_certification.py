"""THE CERTIFICATION SUITE: the hostile audit, made permanent.

Everything here was written while trying to BREAK the engine before the first user strategy
was submitted, and everything here found something or proved something. It is kept as a
suite rather than as a report because a finding that is not a test decays into a paragraph
nobody reruns.

Four kinds of check:

  GOLDEN        synthetic strategies whose correct answer is arithmetic. The expected value is
                computed in the comment beside the assertion, not read out of the engine.
  RECONCILED    every headline number rebuilt from the trade ledger alone, by code that does
                not call the production aggregator, and compared.
  BOUNDARY      the Topstep rules at their exact edges - at the limit, one cent either side.
  ADVERSARIAL   attempts to manufacture a profitable or wrong result. Each must be refused or
                flagged; producing a pretty number silently is the failure.

THE FOUR DEFECTS THIS FILE EXISTS BECAUSE OF
----------------------------------------------
  P0  a direct +1 -> -1 reversal lost its second leg, and an alternating signal produced
      four trades ALL LONG - a different strategy, reported under the right hash.
  P1  the Monte Carlo ran a no-withdrawal payout policy while the account beside it withdrew,
      understating P(ruin) by 11.4 points in the flattering direction.
  P1  "ending STRATEGY equity" printed `starting_balance + ending_balance`, a number that is
      not any quantity at all.
  P1  the user-facing runner had no lookahead canary, while the funnel it replaced did.
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_brain.markets.futures_cme import instruments as inst  # noqa: E402
from quant_brain.markets.futures_cme import paths as pa  # noqa: E402
from quant_brain.markets.futures_cme import topstep as ts  # noqa: E402
from quant_brain.markets.futures_cme import twin as tw  # noqa: E402
from quant_brain.research import strategy_report as sr  # noqa: E402
from quant_brain.research import topstep_reference as tr  # noqa: E402
from quant_brain.research.account_result import PayoutRuleSet, build_account_result  # noqa: E402
from quant_brain.research.canonical_ledger import ExecutionPathMode  # noqa: E402
from quant_brain.research.ledger_builder import build_ledger  # noqa: E402
from quant_brain.research.session_source import Attrition, SessionSet, SessionWindow  # noqa: E402
from quant_brain.research.strategy_runner import monthly_table  # noqa: E402
from quant_brain.research.strategy_spec import (  # noqa: E402
    CostSpec,
    ExitSpec,
    RiskSpec,
    SessionSpec,
    SizingSpec,
    StrategySpec,
)

FREE = CostSpec(commission_round_turn=0.0, include_spread=False, slippage_ticks=0.0)
OPEN_ET, CLOSE_ET = "09:30", "09:39"
BARS = 10
D0 = dt.date(2026, 1, 5)

MULT = inst.get("MNQ").spec.multiplier        # 2.0
TICK = inst.get("MNQ").spec.tick              # 0.25
TICKV = inst.get("MNQ").spec.tick_value       # 0.50


# =====================================================================================
# FIXTURE HELPERS
# =====================================================================================

def sessions_from(rows, highs=None, lows=None, start=D0, open_et=OPEN_ET):
    out, day = [], start
    for k, closes in enumerate(rows):
        c = np.asarray(closes, dtype=float)
        h = c if highs is None else np.asarray(highs[k], dtype=float)
        low = c if lows is None else np.asarray(lows[k], dtype=float)
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        t0 = pd.Timestamp(f"{day} {open_et}", tz="America/New_York")
        idx = pd.DatetimeIndex([t0 + pd.Timedelta(minutes=i) for i in range(len(c))])
        out.append(pd.DataFrame({
            "t": idx.tz_convert("UTC"), "o": c, "h": h, "l": low, "c": c, "v": 100.0,
            "contract": "MNQH6", "day": day,
            "hm": idx.tz_convert("America/New_York").strftime("%H:%M")}))
        day += dt.timedelta(days=1)
    return out


def a_spec(*, instrument="MNQ", contracts=1, exit_spec=None, risk=None, session=None,
           cost=FREE, name="cert"):
    return StrategySpec(
        name=name, instrument=instrument, timeframe="1min",
        signal=lambda X: np.asarray(X["pos"], dtype=float),
        exit=exit_spec or ExitSpec(use_invalidation=True),
        sizing=SizingSpec(contracts=contracts),
        session=session or SessionSpec(open_et=OPEN_ET, close_et=CLOSE_ET),
        cost=cost, risk=risk or RiskSpec(), rationale="certification fixture")


def run(spec, sessions, pos_rows, *, mode=ExecutionPathMode.CLOSE_ONLY, slip=0.0):
    feats = [pd.DataFrame({"pos": p}) for p in pos_rows]
    return build_ledger(spec, sessions, feats, slip_ticks=slip, scenario="CERT", mode=mode)


def a_sset(sessions, *, instrument="MNQ", open_et=OPEN_ET, close_et=CLOSE_ET):
    n = sum(len(s) for s in sessions)
    return SessionSet(
        sessions=tuple(sessions), window=SessionWindow(open_et, close_et), path="canonical",
        instrument=instrument, source_file="synthetic",
        provenance={"feature_data": {"dataset_id": "synthetic", "manifest_id": "0" * 16,
                                     "frame_fingerprint": "0" * 16,
                                     "data_form": "CONTINUOUS_UNADJUSTED",
                                     "roll_method": "NONE", "adjustment_method": "NONE",
                                     "quality_status": "PASS"}},
        attrition=Attrition(n, n, len(sessions), 0, 0, len(sessions)))


def days(*specs, start=D0):
    out, d = [], start
    for pnl, worst in specs:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        out.append(tw.TwinDay(day=d, pnl=float(pnl), path=(0.0, float(worst), float(pnl))))
        d += dt.timedelta(days=1)
    return out


# =====================================================================================
# GOLDEN - the answer is arithmetic
# =====================================================================================

@pytest.mark.golden
def test_one_tick_lost_is_exactly_minus_one_tick_value():
    """Entry at 100.00, exit at 99.75. -0.25 pts x 2.0 multiplier = -$0.50 = -1 tick."""
    closes = [100.0, 100.0, 99.75] + [99.75] * 7
    led = run(a_spec(exit_spec=ExitSpec(time_stop_bars=1, use_invalidation=False)),
              sessions_from([closes]), [[0, 1] + [0] * 8])
    t = led.trade_frame()
    assert len(t) == 1
    assert float(t["gross_pnl"].iloc[0]) == pytest.approx(-TICKV)
    assert float(led.daily().iloc[0]) == pytest.approx(-TICKV)


@pytest.mark.golden
def test_the_short_side_is_the_exact_negative_of_the_long_side():
    closes = [100.0, 100.0, 100.25] + [100.25] * 7
    ex = ExitSpec(time_stop_bars=1, use_invalidation=False)
    lg = run(a_spec(exit_spec=ex), sessions_from([closes]), [[0, 1] + [0] * 8])
    sh = run(a_spec(exit_spec=ex), sessions_from([closes]), [[0, -1] + [0] * 8])
    assert float(lg.trade_frame()["gross_pnl"].iloc[0]) == pytest.approx(TICKV)
    assert float(sh.trade_frame()["gross_pnl"].iloc[0]) == pytest.approx(-TICKV)


@pytest.mark.golden
def test_ten_ticks_is_ten_tick_values_and_scales_linearly_in_contracts():
    """+2.50 pts. 1 lot = $5.00 = 10 x $0.50. 3 lots = $15.00, exactly three times."""
    closes = [100.0, 100.0, 102.5] + [102.5] * 7
    ex = ExitSpec(time_stop_bars=1, use_invalidation=False)
    one = run(a_spec(exit_spec=ex), sessions_from([closes]), [[0, 1] + [0] * 8])
    three = run(a_spec(exit_spec=ex, contracts=3), sessions_from([closes]),
                [[0, 1] + [0] * 8])
    assert float(one.trade_frame()["gross_pnl"].iloc[0]) == pytest.approx(10 * TICKV)
    assert float(three.trade_frame()["gross_pnl"].iloc[0]) == pytest.approx(30 * TICKV)


@pytest.mark.golden
def test_a_micro_is_exactly_a_tenth_of_its_parent_on_the_same_move():
    """NQ 20.0 / MNQ 2.0. The same +2.50 points: $50.00 against $5.00."""
    closes = [100.0, 100.0, 102.5] + [102.5] * 7
    ex = ExitSpec(time_stop_bars=1, use_invalidation=False)
    micro = run(a_spec(exit_spec=ex), sessions_from([closes]), [[0, 1] + [0] * 8])
    parent = run(a_spec(exit_spec=ex, instrument="NQ"), sessions_from([closes]),
                 [[0, 1] + [0] * 8])
    m = float(micro.trade_frame()["gross_pnl"].iloc[0])
    p = float(parent.trade_frame()["gross_pnl"].iloc[0])
    assert m == pytest.approx(5.0) and p == pytest.approx(50.0)
    assert p / m == pytest.approx(10.0)


@pytest.mark.golden
def test_a_stop_fills_at_its_level_and_a_target_fills_at_its_level():
    c = [100.0] * BARS
    lows = list(c)
    lows[2] = 97.0
    st_ = run(a_spec(exit_spec=ExitSpec(stop_points=2.0, use_invalidation=False,
                                        time_stop_bars=8)),
              sessions_from([c], lows=[lows]), [[0] + [1] * 9]).trade_frame()
    assert float(st_["exit_price"].iloc[0]) == 98.0
    assert float(st_["gross_pnl"].iloc[0]) == pytest.approx(-4.0)   # -2.00 pts x 2.0
    assert st_["exit_reason"].iloc[0] == "stop"

    highs = list(c)
    highs[2] = 104.0
    tg = run(a_spec(exit_spec=ExitSpec(target_points=3.0, use_invalidation=False,
                                       time_stop_bars=8)),
             sessions_from([c], highs=[highs]), [[0] + [1] * 9]).trade_frame()
    assert float(tg["exit_price"].iloc[0]) == 103.0
    assert float(tg["gross_pnl"].iloc[0]) == pytest.approx(6.0)     # +3.00 pts x 2.0
    assert tg["exit_reason"].iloc[0] == "target"


@pytest.mark.golden
def test_the_published_round_turn_cost_is_charged_exactly():
    """MNQ: $1.22 commission + one tick of spread $0.50 = $1.72, plus 1 tick slip $0.50."""
    c = [100.0] * BARS
    t = run(a_spec(cost=CostSpec(),
                   exit_spec=ExitSpec(time_stop_bars=1, use_invalidation=False)),
            sessions_from([c]), [[0, 1] + [0] * 8], slip=1.0).trade_frame()
    assert float(t["gross_pnl"].iloc[0]) == pytest.approx(0.0)
    assert float(t["commission_and_spread"].iloc[0]) == pytest.approx(1.72)
    assert float(t["slippage"].iloc[0]) == pytest.approx(0.50)
    assert float(t["net_pnl"].iloc[0]) == pytest.approx(-2.22)


@pytest.mark.golden
def test_a_strategy_that_never_trades_costs_nothing_and_ends_flat():
    led = run(a_spec(exit_spec=ExitSpec(time_stop_bars=1, use_invalidation=False)),
              sessions_from([[100.0] * BARS]), [[0] * BARS])
    assert len(led.trade_frame()) == 0
    assert float(led.daily().iloc[0]) == 0.0
    assert led.sessions[0].cost == 0.0
    assert led.sessions[0].ends_flat
    assert led.sessions[0].marks == (0.0,)


@pytest.mark.golden
def test_an_intrabar_mll_breach_kills_the_account_that_a_close_only_path_survives():
    """1 MNQ, a 1,100-point adverse excursion is -$2,200 against a $2,000 MLL.

    The session SETTLES at +$10 either way. CLOSE_ONLY never sees the excursion and survives;
    INTRABAR_CONSERVATIVE marks it and liquidates. That difference is the whole reason the
    conservative path mode is the headline.
    """
    c = [20000.0, 20000.0] + [20005.0] * 8
    lows = list(c)
    lows[2] = 20000.0 - 1100.0
    spec = a_spec(exit_spec=ExitSpec(time_stop_bars=8, use_invalidation=False))
    ses, pos = sessions_from([c], lows=[lows]), [[0] + [1] * 9]
    close = run(spec, ses, pos, mode=ExecutionPathMode.CLOSE_ONLY)
    intra = run(spec, ses, pos, mode=ExecutionPathMode.INTRABAR_CONSERVATIVE)

    assert float(close.daily().iloc[0]) == pytest.approx(float(intra.daily().iloc[0]))
    assert float(close.daily().iloc[0]) == pytest.approx(10.0)
    assert min(close.sessions[0].marks) == pytest.approx(0.0)
    assert min(intra.sessions[0].marks) == pytest.approx(-2200.0)

    rules = PayoutRuleSet.as_documented(50_000)
    assert not build_account_result(close, payout_rules=rules, reps=20).liquidated
    assert build_account_result(intra, payout_rules=rules, reps=20).liquidated


# =====================================================================================
# THE P0: REVERSALS
# =====================================================================================

def test_a_direct_reversal_keeps_both_legs():
    g = sessions_from([[100.0 + i for i in range(BARS)]])
    t = run(a_spec(exit_spec=ExitSpec(use_invalidation=True, time_stop_bars=8)),
            g, [[0, 1, 1, -1, -1, -1, 0, 0, 0, 0]]).trade_frame()
    assert t["direction"].tolist() == [1, -1]
    assert int(t["exit_bar"].iloc[0]) == int(t["entry_bar"].iloc[1]) == 3


def test_an_alternating_signal_is_not_silently_traded_one_sided():
    """The exact shape the P0 destroyed: four trades, all long, under the spec's own hash."""
    g = sessions_from([[100.0 + i for i in range(BARS)]])
    t = run(a_spec(exit_spec=ExitSpec(use_invalidation=True, time_stop_bars=8)),
            g, [[0, 1, -1, 1, -1, 1, -1, 1, 0, 0]]).trade_frame()
    dirs = t["direction"].tolist()
    assert len(set(dirs)) == 2, f"one-sided: {dirs}"
    assert all(a != b for a, b in zip(dirs, dirs[1:], strict=False)), dirs


def test_a_warmup_blocks_entry_up_to_its_own_bar_index_and_not_one_further():
    """`warmup_bars=N` means bar N is the FIRST bar an entry may open on.

    An off-by-one here admits a trade on a bar the spec excluded, which on an opening-range
    rule is the most information-rich bar of the session.
    """
    g = sessions_from([[100.0 + i for i in range(BARS)]])
    # An edge on every even bar, so each candidate bar is genuinely offered to the gate. A
    # constant signal has exactly one edge (bar 0) and would leave the gate untested.
    pos = [1.0 if i % 2 == 0 else 0.0 for i in range(BARS)]
    for warm in (0, 1, 3, 5):
        spec = a_spec(exit_spec=ExitSpec(time_stop_bars=1, use_invalidation=False),
                      session=SessionSpec(open_et=OPEN_ET, close_et=CLOSE_ET,
                                          warmup_bars=warm))
        t = run(spec, g, [pos]).trade_frame()
        first_even_at_or_after = warm if warm % 2 == 0 else warm + 1
        assert int(t["entry_bar"].iloc[0]) == first_even_at_or_after, (
            f"warmup {warm} opened on bar {int(t['entry_bar'].iloc[0])}, "
            f"expected {first_even_at_or_after}")


def test_a_stop_out_does_not_re_enter_on_an_unchanged_signal():
    """The behaviour the reversal fix had to PRESERVE.

    A position stopped out while the signal is still +1 must not immediately re-open: the
    signal has not said anything new. Only an edge opens a position.
    """
    c = [100.0] * BARS
    lows = list(c)
    lows[2] = 90.0
    t = run(a_spec(exit_spec=ExitSpec(stop_points=2.0, use_invalidation=False,
                                      time_stop_bars=8)),
            sessions_from([c], lows=[lows]), [[0] + [1] * 9]).trade_frame()
    assert len(t) == 1, f"re-entered on an unchanged signal: {len(t)} trades"


# =====================================================================================
# RECONCILED - rebuilt from the ledger, no production aggregator
# =====================================================================================

@pytest.fixture(scope="module")
def long_run():
    """200 sessions crossing a year boundary, with real stops and targets."""
    rng = np.random.default_rng(11)
    day, sessions, poss = dt.date(2025, 11, 3), [], []
    n = 30
    while len(sessions) < 200:
        if day.weekday() < 5:
            walk = 20000.0 + np.cumsum(rng.normal(0, 4, n))
            t0 = pd.Timestamp(f"{day} 09:30", tz="America/New_York")
            idx = pd.DatetimeIndex([t0 + pd.Timedelta(minutes=i) for i in range(n)])
            sessions.append(pd.DataFrame({
                "t": idx.tz_convert("UTC"), "o": walk,
                "h": walk + np.abs(rng.normal(0, 2, n)),
                "l": walk - np.abs(rng.normal(0, 2, n)), "c": walk, "v": 1.0,
                "contract": "MNQH6", "day": day,
                "hm": idx.tz_convert("America/New_York").strftime("%H:%M")}))
            poss.append(list(rng.choice([-1.0, 0.0, 1.0], size=n, p=[0.2, 0.6, 0.2])))
        day += dt.timedelta(days=1)
    spec = StrategySpec(
        name="reconcile", instrument="MNQ", timeframe="1min",
        signal=lambda X: np.asarray(X["pos"], dtype=float),
        exit=ExitSpec(stop_points=6.0, target_r=2.0, time_stop_bars=10),
        sizing=SizingSpec(contracts=2),
        session=SessionSpec(open_et="09:30", close_et="09:59"), cost=CostSpec())
    led = build_ledger(spec, sessions, [pd.DataFrame({"pos": p}) for p in poss],
                       slip_ticks=1.0, scenario="CONSERVATIVE",
                       mode=ExecutionPathMode.INTRABAR_CONSERVATIVE)
    acct = build_account_result(led, payout_rules=PayoutRuleSet.as_documented(50_000),
                                payout_fraction=1.0, reps=100)
    sset = a_sset(sessions, open_et="09:30", close_et="09:59")
    ladder = [{"scenario": "CONSERVATIVE", "net_pnl": float(led.daily().sum()),
               "per_trade": 0.0, "max_drawdown": 0.0, "liquidated": acct.liquidated,
               "p_target": 0.0, "p_payout": 0.0}]
    rep = sr.build(led, acct, spec=spec, sset=sset, ladder=ladder, engine_version="cert",
                   mc_paths=200, mc_block=10, daily_loss_limit=None)
    return led, acct, rep, sset


def _independent_daily(led):
    """Per-session P&L summed from the TRADE rows, not from `ledger.daily()`."""
    by = defaultdict(float)
    for _, r in led.trade_frame().iterrows():
        by[r["session"]] += float(r["net_pnl"])
    return {s.day: by.get(s.day, 0.0) for s in led.sessions}


def test_all_three_monthly_calculators_agree_with_an_independent_reconstruction(long_run):
    """The system ships THREE monthly aggregators. They must not be three answers.

    `strategy_runner.monthly_table`, `account_result._monthly` and
    `strategy_report._period_rows` are compared against a dict built by summing the trade
    rows by calendar month here, with no production call in the reconstruction.
    """
    led, acct, rep, _ = long_run
    ind = defaultdict(float)
    for d, v in _independent_daily(led).items():
        ind[f"{d.year:04d}-{d.month:02d}"] += v

    m1 = monthly_table(led.daily())
    m2 = {r.month: r for r in acct.monthly}
    m3 = {r.period: r for r in rep.time.monthly}
    assert len(ind) == len(m1) == len(m2) == len(m3) > 6
    for k, want in ind.items():
        assert float(m1[m1["month"] == k]["net_pnl"].iloc[0]) == pytest.approx(want)
        assert m2[k].net_pnl == pytest.approx(want)
        assert m3[k].net_pnl == pytest.approx(want)
    assert sum(r.net_pnl for r in rep.time.monthly) == pytest.approx(
        float(led.daily().sum()))


def test_monthly_trade_counts_and_win_rates_reconcile(long_run):
    led, _, rep, _ = long_run
    tr_ = led.trade_frame()
    counts, wins, sess = defaultdict(int), defaultdict(int), defaultdict(int)
    for _, r in tr_.iterrows():
        k = f"{r['session'].year:04d}-{r['session'].month:02d}"
        counts[k] += 1
        wins[k] += float(r["net_pnl"]) > 0
    for s in led.sessions:
        sess[f"{s.day.year:04d}-{s.day.month:02d}"] += 1
    for row in rep.time.monthly:
        assert row.trades == counts[row.period]
        assert row.sessions == sess[row.period]
        if counts[row.period]:
            assert row.win_rate == pytest.approx(wins[row.period] / counts[row.period])


def test_every_section_b_number_reconciles_with_the_trade_rows(long_run):
    led, _, rep, _ = long_run
    t = led.trade_frame()
    net = t["net_pnl"].to_numpy(dtype=float)
    wins, losses = net[net > 0], net[net < 0]
    b = rep.trades
    assert b.total == len(net)
    assert b.longs == int((t["direction"] > 0).sum())
    assert b.shorts == int((t["direction"] < 0).sum())
    assert b.winners == len(wins) and b.losers == len(losses)
    assert b.win_rate == pytest.approx(len(wins) / len(net))
    assert b.average_trade == pytest.approx(float(net.mean()))
    assert b.median_trade == pytest.approx(float(np.median(net)))
    assert b.stdev_trade == pytest.approx(float(net.std(ddof=1)))
    assert b.best_trade == pytest.approx(float(net.max()))
    assert b.worst_trade == pytest.approx(float(net.min()))
    assert b.gross_profit == pytest.approx(float(wins.sum()))
    assert b.gross_loss == pytest.approx(float(-losses.sum()))
    assert b.profit_factor == pytest.approx(float(wins.sum() / -losses.sum()))
    assert b.net_pnl == pytest.approx(float(net.sum()))
    assert b.fees == pytest.approx(float(t["commission_and_spread"].sum()))
    assert b.slippage == pytest.approx(float(t["slippage"].sum()))
    # the cost identity: gross - fees - slippage == net
    assert float(t["gross_pnl"].sum()) - b.fees - b.slippage == pytest.approx(b.net_pnl)


def test_every_section_c_number_reconciles_with_the_session_series(long_run):
    led, _, rep, _ = long_run
    d = np.asarray([v for _, v in sorted(_independent_daily(led).items())], dtype=float)
    eq = np.cumsum(d)
    assert rep.risk.max_drawdown == pytest.approx(
        abs(float((eq - np.maximum.accumulate(eq)).min())))
    assert rep.risk.worst_daily_loss == pytest.approx(float(d.min()))
    assert rep.risk.best_daily_gain == pytest.approx(float(d.max()))

    def longest(flags):
        best = run_ = 0
        for f in flags:
            run_ = run_ + 1 if f else 0
            best = max(best, run_)
        return best

    net = led.trade_frame()["net_pnl"].to_numpy(dtype=float)
    assert rep.risk.max_consecutive_losses == longest(net < 0)
    assert rep.risk.max_consecutive_losing_days == longest(d < 0)


def test_the_strategy_pnl_and_the_account_balance_are_not_confused(long_run):
    """P1 DEFECT. `AccountResult.final_equity` is an ALIAS of `ending_balance` - a LEVEL.

    The report printed `starting_balance + final_equity` as "ending strategy equity", which
    on a $50,000 account ending at $48,046 rendered $98,046 with a "P&L" of $48,046. The
    strategy's own result is `returns.net_pnl`.
    """
    led, acct, rep, _ = long_run
    assert acct.final_equity == acct.ending_balance, "final_equity is an alias, not a P&L"
    assert acct.returns.net_pnl == pytest.approx(float(led.daily().sum()))
    text = rep.render()
    strategy_line = [ln for ln in text.splitlines() if "ending STRATEGY equity" in ln][0]
    assert f"{acct.starting_balance + acct.returns.net_pnl:,.0f}" in strategy_line
    assert f"{acct.starting_balance + acct.ending_balance:,.0f}" not in strategy_line


def test_accounting_conservation_holds_at_every_session_in_every_mode():
    """sum(trade net) == realized_net == last mark; fills net to zero; costs reconcile."""
    rng = np.random.default_rng(7)
    rows = [list(20000.0 + np.cumsum(rng.normal(0, 3, BARS))) for _ in range(40)]
    poss = [list(rng.choice([-1.0, 0.0, 1.0], size=BARS)) for _ in range(40)]
    spec = a_spec(cost=CostSpec(),
                  exit_spec=ExitSpec(stop_points=5.0, target_r=2.0, time_stop_bars=6))
    ses = sessions_from(rows)
    for mode in ExecutionPathMode:
        led = run(spec, ses, poss, mode=mode, slip=1.0)
        for s in led.sessions:
            tn = sum(t.net_pnl for t in s.trades)
            tg = sum(t.gross_pnl for t in s.trades)
            tc = sum(t.commission_and_spread + t.slippage for t in s.trades)
            assert tn == pytest.approx(s.realized_net)
            assert tg - tc == pytest.approx(s.realized_net)
            assert s.marks[-1] == pytest.approx(s.realized_net)
            assert sum(f.signed_quantity for f in s.fills) == pytest.approx(0.0)
            assert sum(f.cost for f in s.fills) == pytest.approx(s.cost)


def test_the_path_mode_changes_the_path_and_never_the_settled_pnl():
    rng = np.random.default_rng(7)
    rows = [list(20000.0 + np.cumsum(rng.normal(0, 3, BARS))) for _ in range(40)]
    poss = [list(rng.choice([-1.0, 0.0, 1.0], size=BARS)) for _ in range(40)]
    spec = a_spec(exit_spec=ExitSpec(stop_points=5.0, target_r=2.0, time_stop_bars=6))
    ses = sessions_from(rows)
    base = run(spec, ses, poss, mode=ExecutionPathMode.CLOSE_ONLY, slip=1.0)
    for mode in (ExecutionPathMode.INTRABAR_CONSERVATIVE, ExecutionPathMode.STRESS):
        other = run(spec, ses, poss, mode=mode, slip=1.0)
        assert float(other.daily().sum()) == pytest.approx(float(base.daily().sum()))
        for b, o in zip(base.sessions, other.sessions, strict=True):
            assert min(o.marks) <= min(b.marks) + 1e-9, "a path mode improved the account"


# =====================================================================================
# BOUNDARY - the Topstep rules at their exact edges
# =====================================================================================

@pytest.mark.acceptance
@pytest.mark.parametrize("worst,liquidates", [(-2000.0, True), (-1999.99, False)])
def test_the_mll_breaches_at_the_touch_and_not_a_cent_above(worst, liquidates):
    r = tw.TopstepTwin(50_000).run(days((0.0, worst)))
    assert (r.terminal is ts.TopstepStage.LIQUIDATED) is liquidates


@pytest.mark.acceptance
def test_an_intraday_dip_liquidates_even_when_the_session_closes_positive():
    r = tw.TopstepTwin(50_000).run(days((500.0, -2100.0)))
    assert r.terminal is ts.TopstepStage.LIQUIDATED


@pytest.mark.acceptance
def test_the_mll_trails_the_eod_balance_and_not_the_intraday_high():
    r = tw.TopstepTwin(50_000).run(days((1000.0, 0.0), (-1900.0, -1900.0)))
    assert r.trace[1].mll == pytest.approx(49_000.0)
    assert r.terminal is not ts.TopstepStage.LIQUIDATED
    # and an unrealised high does not move it at all
    r2 = tw.TopstepTwin(50_000).run([tw.TwinDay(day=D0, pnl=0.0, path=(0.0, 3000.0, 0.0))])
    assert r2.trace[0].mll == pytest.approx(48_000.0)


@pytest.mark.acceptance
def test_the_mll_locks_at_breakeven_and_never_moves_again():
    r = tw.TopstepTwin(50_000).run(days((2000.0, 0.0), (5000.0, 0.0)))
    assert r.trace[-1].mll == pytest.approx(50_000.0)
    r2 = tw.TopstepTwin(50_000).run(days((1999.99, 0.0)))
    assert r2.trace[0].mll == pytest.approx(48_000.0)


@pytest.mark.acceptance
def test_an_armed_daily_limit_caps_the_session_instead_of_liquidating_it():
    t = tw.TopstepTwin(50_000, daily_loss_limit=1_000.0)
    r = t.run(days((-5000.0, -5000.0)))
    assert r.trace[0].event == "dll_capped"
    assert r.trace[0].settled_pnl == pytest.approx(-1000.0)
    assert r.terminal is not ts.TopstepStage.LIQUIDATED
    rec = t.run(days((-1000.0, -1000.0), (1500.0, 0.0)))
    assert rec.final_balance == pytest.approx(50_500.0)


@pytest.mark.acceptance
def test_the_combine_target_is_the_consistency_raised_one_not_three_thousand():
    """+$3,100 in ONE day is more than $3,000 and does NOT pass.

    Best day 100% of profit against a 55% limit lifts the effective target to $5,636. This
    is why every 'target' label in the report says Combine and not $3,000.
    """
    one_big = tw.TopstepTwin(50_000).run(days((3100.0, 0.0)))
    assert one_big.combine_days is None
    spread = tw.TopstepTwin(50_000).run(
        days((1000.0, 0.0), (1000.0, 0.0), (1100.0, 0.0)))
    assert spread.combine_days == 3
    assert sr.COMBINE_TARGET_NOTE.startswith("NOT simply")


@pytest.mark.acceptance
def test_liquidation_is_absorbing():
    r = tw.TopstepTwin(50_000).run(days((-2500.0, -2500.0), (50_000.0, 0.0)))
    assert r.terminal is ts.TopstepStage.LIQUIDATED


@pytest.mark.acceptance
def test_the_twin_agrees_with_the_independent_reference_on_adversarial_paths():
    """1,200 paths deliberately parked ON the boundaries, against a no-shared-code reference."""
    rng = np.random.default_rng(99)
    mismatches = []
    for _ in range(1200):
        n = int(rng.integers(2, 30))
        ds, d = [], D0
        for _ in range(n):
            while d.weekday() >= 5:
                d += dt.timedelta(days=1)
            style = int(rng.integers(0, 4))
            if style == 1:
                pnl, worst = -2000.0, -2000.0          # exactly the MLL
            elif style == 2:
                pnl, worst = 3000.0, 0.0               # exactly the raw target
            else:
                pnl = float(rng.normal(0, 1800))
                worst = min(0.0, pnl) - abs(float(rng.normal(0, 400)))
            ds.append(tw.TwinDay(day=d, pnl=pnl, path=(0.0, worst, pnl)))
            d += dt.timedelta(days=1)
        dll = float(rng.choice([0, 1000, 2000])) or None
        a = tw.TopstepTwin(50_000, daily_loss_limit=dll,
                           payout_policy=tw.PayoutPolicy(fraction=0.0)).run(ds)
        b = tr.run_reference(ds, daily_loss_limit=dll, payout_fraction=0.0)
        if ((a.terminal is ts.TopstepStage.LIQUIDATED) != (b.breach_day is not None)
                or (a.combine_days is not None) != (b.combine_days is not None)):
            mismatches.append(ds)
    assert not mismatches, f"{len(mismatches)} decision-level mismatches"


# =====================================================================================
# MONTE CARLO
# =====================================================================================

@pytest.fixture(scope="module")
def payout_run():
    """A PROFITABLE run, so the account actually reaches payout eligibility.

    The policy defect is invisible on a losing sample: if no payout is ever taken, withdrawing
    100% and withdrawing 0% describe the same account. The fixture has to earn first.
    """
    rng = np.random.default_rng(21)
    day, sessions, poss = dt.date(2025, 11, 3), [], []
    n = 20
    k = 0
    while len(sessions) < 140:
        if day.weekday() < 5:
            # Mostly winning days so the account reaches payout eligibility, with a loser
            # every seventh session. Tuned so the DIFFERENCE is visible: on this sample the
            # account takes 20 payouts, and P(breach) is 0.0% if it never withdraws against
            # 14.0% if it withdraws the cap - the withdrawal is what makes ruin reachable,
            # because the balance falls and the MLL does not follow it down.
            slope = -60.0 if k % 7 == 6 else 30.0
            walk = 20000.0 + np.linspace(0.0, slope, n) + rng.normal(0, 3, n)
            t0 = pd.Timestamp(f"{day} 09:30", tz="America/New_York")
            idx = pd.DatetimeIndex([t0 + pd.Timedelta(minutes=i) for i in range(n)])
            sessions.append(pd.DataFrame({
                "t": idx.tz_convert("UTC"), "o": walk, "h": walk + 1.0, "l": walk - 1.0,
                "c": walk, "v": 1.0, "contract": "MNQH6", "day": day,
                "hm": idx.tz_convert("America/New_York").strftime("%H:%M")}))
            poss.append([0.0] + [1.0] * (n - 2) + [0.0])
            k += 1
        day += dt.timedelta(days=1)
    spec = StrategySpec(
        name="payout", instrument="MNQ", timeframe="1min",
        signal=lambda X: np.asarray(X["pos"], dtype=float),
        exit=ExitSpec(use_invalidation=True, time_stop_bars=15),
        sizing=SizingSpec(contracts=5),
        session=SessionSpec(open_et="09:30", close_et="09:49"), cost=FREE)
    led = build_ledger(spec, sessions, [pd.DataFrame({"pos": p}) for p in poss],
                       slip_ticks=0.0, scenario="CERT", mode=ExecutionPathMode.CLOSE_ONLY)
    return spec, led, a_sset(sessions, open_et="09:30", close_et="09:49")


def _report_at(spec, led, sset, fraction):
    acct = build_account_result(led, payout_rules=PayoutRuleSet.as_documented(50_000),
                                payout_fraction=fraction, reps=100, seed=0)
    rep = sr.build(led, acct, spec=spec, sset=sset,
                   ladder=[{"scenario": "CERT", "net_pnl": float(led.daily().sum())}],
                   engine_version="cert", mc_paths=300, mc_block=10, seed=0)
    return acct, rep


def test_the_monte_carlo_uses_the_ACCOUNTS_payout_policy_not_a_kinder_one(payout_run):
    """P1 DEFECT. A payout lowers the balance while the MLL stays put.

    The Monte Carlo hardcoded `fraction=0.0` - never withdraw - while the account beside it
    withdrew the whole eligible cap, so it reported the ruin probability of an account nobody
    was running. Measured on a 120-session sample: P(breach) 87.1% against 98.5%.

    Pinned two ways: the figure must MOVE when the policy moves, and at each policy it must
    equal a twin rebuilt here from that account's own declared policy.
    """
    spec, led, sset = payout_run
    a0, r0 = _report_at(spec, led, sset, 0.0)
    a1, r1 = _report_at(spec, led, sset, 1.0)
    assert a1.payout.payouts, "the fixture never took a payout; the test would prove nothing"
    assert r0.monte_carlo.ran and r1.monte_carlo.ran
    assert r0.monte_carlo.p_mll_breach != r1.monte_carlo.p_mll_breach, (
        "the Monte Carlo did not respond to the withdrawal policy at all")

    for acct, rep in ((a0, r0), (a1, r1)):
        twin = tw.TopstepTwin(acct.account_size, daily_loss_limit=None,
                              payout_policy=acct.payout.rules.to_policy(
                                  fraction=acct.payout.policy_fraction,
                                  min_buffer_after=acct.payout.policy_min_buffer_after))
        sample = pa.moving_block(led.twin_days(), block=10, reps=300, seed=0)
        results = [twin.run(path) for path in sample]
        breach = sum(1 for r in results
                     if r.terminal is ts.TopstepStage.LIQUIDATED or r.breach_day is not None)
        assert rep.monte_carlo.p_mll_breach == pytest.approx(breach / len(sample), abs=1e-12)


def test_the_monte_carlo_resamples_paths_as_long_as_the_sample(long_run):
    """A shorter path is a kinder barrier problem: fewer sessions, fewer chances to breach."""
    led, _, rep, _ = long_run
    assert rep.monte_carlo.sessions_per_path == len(led.sessions)
    sample = pa.moving_block(led.twin_days(), block=rep.monte_carlo.block,
                             reps=rep.monte_carlo.paths, seed=0)
    assert all(len(path) == len(led.sessions) for path in sample)


def test_the_monte_carlo_only_ever_reuses_observed_sessions():
    base = days(*[(float(v), min(0.0, float(v)) - 100.0)
                  for v in np.random.default_rng(4).normal(30, 500, 60)])
    sample = pa.moving_block(base, block=10, reps=100, seed=0)
    observed = {round(d.pnl, 9) for d in base}
    drawn = {round(d.pnl, 9) for p in sample for d in p}
    assert drawn.issubset(observed), "the resample invented P&L that never happened"
    assert all(len(p) == len(base) for p in sample)
    assert all(len(d.path) == 3 for p in sample for d in p), "the path must travel"


def test_the_monte_carlo_is_labelled_as_path_risk_and_never_as_evidence(long_run):
    _, _, rep, _ = long_run
    label = rep.monte_carlo.label.lower()
    assert "not" in label and "independent evidence" in label or "not historical replay" in label
    assert "path risk" in label


def test_the_monte_carlo_refuses_a_sample_too_short_to_resample():
    rng = np.random.default_rng(2)
    rows = [list(20000.0 + np.cumsum(rng.normal(0, 3, BARS))) for _ in range(8)]
    poss = [list(rng.choice([-1.0, 0.0, 1.0], size=BARS)) for _ in range(8)]
    spec = a_spec(exit_spec=ExitSpec(time_stop_bars=3, use_invalidation=False))
    ses = sessions_from(rows)
    led = run(spec, ses, poss)
    acct = build_account_result(led, payout_rules=PayoutRuleSet.as_documented(50_000),
                                reps=20)
    rep = sr.build(led, acct, spec=spec, sset=a_sset(ses),
                   ladder=[{"scenario": "CERT", "net_pnl": 0.0}], engine_version="cert",
                   mc_paths=100, mc_block=10)
    assert not rep.monte_carlo.ran
    assert "block" in rep.monte_carlo.reason


# =====================================================================================
# RESULT INTEGRITY - the lookahead canary
# =====================================================================================

def test_the_lookahead_constant_matches_the_funnels_measured_band():
    """Two copies of one measured number. They must not drift apart."""
    import futures_discover as fd
    assert sr.LOOKAHEAD_CEILING_SHARE == fd.MAX_CEILING_SHARE


def test_a_signal_that_indexes_the_future_is_caught_by_the_ceiling_canary():
    """P1 DEFECT. The feature audit cannot see a leak written into the signal itself.

    A signal is arbitrary Python: `fe.audit_causality` perturbs feature INPUTS and cannot
    reach a function that indexes the price array directly. The funnel has always refused a
    hypothesis whose gross exceeds a share of the one-bar oracle ceiling; the user-facing
    runner had no such canary at all, so a strategy with an accidental lookahead would have
    produced a spectacular scorecard with no warning anywhere on it.
    """
    rng = np.random.default_rng(3)
    rows = [list(20000.0 + np.cumsum(rng.normal(0, 4, BARS))) for _ in range(80)]
    oracle = []
    for w in rows:
        c = np.asarray(w)
        oracle.append(list(np.concatenate([np.sign(np.diff(c)), [0.0]])))
    spec = a_spec(exit_spec=ExitSpec(time_stop_bars=1, use_invalidation=False))
    ses = sessions_from(rows)
    led = run(spec, ses, oracle)
    acct = build_account_result(led, payout_rules=PayoutRuleSet.as_documented(50_000),
                                reps=20)
    rep = sr.build(led, acct, spec=spec, sset=a_sset(ses),
                   ladder=[{"scenario": "CERT", "net_pnl": float(led.daily().sum())}],
                   engine_version="cert", mc_paths=100, mc_block=10)
    assert rep.integrity.lookahead_suspected, (
        f"an oracle signal earned {rep.integrity.ceiling_share:.1%} of the ceiling and was "
        f"not flagged")
    assert rep.classification.verdict == sr.UNTESTABLE
    assert any("LOOKAHEAD" in b for b in rep.classification.blocking)
    assert "SUSPECTED LOOKAHEAD" in rep.render()


def test_an_honest_rule_is_not_flagged_by_the_canary(long_run):
    """The control. The canary is one-sided and must not fire on a real signal."""
    _, _, rep, _ = long_run
    assert not rep.integrity.lookahead_suspected
    assert rep.integrity.ceiling_share < sr.LOOKAHEAD_CEILING_SHARE
    assert rep.integrity.oracle_ceiling > 0


def test_the_entry_fill_convention_and_its_sensitivity_are_reported(long_run):
    """The zero-latency assumption, priced. Recomputed here from the frames and the trades."""
    led, _, rep, sset = long_run
    assert "CLOSE" in rep.integrity.entry_fill_convention
    assert "NEXT bar" in rep.integrity.entry_fill_note

    opens = {g["day"].iloc[0]: g["o"].to_numpy(dtype=float) for g in sset.frames}
    want = 0.0
    for _, r in led.trade_frame().iterrows():
        nb = int(r["entry_bar"]) + 1
        want += ((float(opens[r["session"]][nb]) - float(r["entry_price"]))
                 * -int(r["direction"]) * led.multiplier * led.contracts)
    assert rep.integrity.entry_fill_sensitivity == pytest.approx(want)
    assert rep.integrity.entry_fill_sensitivity != 0.0, (
        "a sensitivity of exactly zero over this many trades is a stub, not a measurement")


# =====================================================================================
# REPRODUCIBILITY
# =====================================================================================

def test_two_identical_runs_produce_identical_everything():
    rng = np.random.default_rng(5)
    rows = [list(20000.0 + np.cumsum(rng.normal(0, 3, BARS))) for _ in range(60)]
    poss = [list(rng.choice([-1.0, 0.0, 1.0], size=BARS)) for _ in range(60)]
    spec = a_spec(exit_spec=ExitSpec(stop_points=5.0, target_r=2.0, time_stop_bars=6))
    ses = sessions_from(rows)
    outs = []
    for _ in range(2):
        led = run(spec, ses, poss, mode=ExecutionPathMode.INTRABAR_CONSERVATIVE, slip=1.0)
        acct = build_account_result(led, payout_rules=PayoutRuleSet.as_documented(50_000),
                                    payout_fraction=1.0, reps=100, seed=0)
        rep = sr.build(led, acct, spec=spec, sset=a_sset(ses),
                       ladder=[{"scenario": "CERT", "net_pnl": float(led.daily().sum())}],
                       engine_version="cert", mc_paths=200, mc_block=10, seed=0)
        outs.append((led, acct, rep))
    (l1, a1, r1), (l2, a2, r2) = outs
    pd.testing.assert_frame_equal(l1.trade_frame(), l2.trade_frame())
    pd.testing.assert_frame_equal(l1.fill_frame(), l2.fill_frame())
    assert np.array_equal(l1.equity_curve(), l2.equity_curve())
    assert np.array_equal(l1.intraday_equity(), l2.intraday_equity())
    assert a1.ending_balance == a2.ending_balance
    assert a1.p_survive_period == a2.p_survive_period
    assert r1.monte_carlo.p_mll_breach == r2.monte_carlo.p_mll_breach
    assert r1.render() == r2.render()
    assert r1.classification.verdict == r2.classification.verdict


def test_the_spec_hash_is_stable_and_the_ledger_carries_it():
    spec = a_spec(exit_spec=ExitSpec(stop_points=5.0, time_stop_bars=6))
    led = run(spec, sessions_from([[100.0] * BARS]), [[0] + [1] * 9])
    assert led.spec_hash == spec.spec_hash == a_spec(
        exit_spec=ExitSpec(stop_points=5.0, time_stop_bars=6)).spec_hash


# =====================================================================================
# REPORTING - a headline number a reader cannot rebuild is a defect
# =====================================================================================

def test_the_report_states_the_clock_behind_any_annualised_ratio(long_run):
    _, _, rep, _ = long_run
    text = rep.render()
    assert "sqrt(252)" in text
    assert "nothing in" in text.lower() and "annualised" in text


def test_the_report_separates_the_two_monthly_denominators(long_run):
    _, _, rep, _ = long_run
    text = rep.render()
    assert "% of 50K" in text and "% notional" in text
    assert "not the same quantity" in text


def test_the_report_never_calls_a_backtest_profit_a_payout(long_run):
    _, _, rep, _ = long_run
    assert "NOT A PAYOUT" in rep.render()


def test_the_report_states_the_mae_basis_where_the_numbers_are(long_run):
    """Beside the distributions, not only in the limitations list at the foot of the page."""
    _, _, rep, _ = long_run
    assert rep.risk.mae_basis == sr.MAE_BASIS
    assert "UPPER BOUND" in sr.MAE_BASIS
    lines = rep.render().splitlines()
    basis = [i for i, ln in enumerate(lines) if "MAE/MFE basis" in ln]
    assert basis, "the RISK section does not carry the basis line"
    assert "UPPER BOUND" in lines[basis[0]]
    mae_row = [i for i, ln in enumerate(lines) if "MAE distribution" in ln][0]
    assert basis[0] - mae_row < 5, "the basis is not next to the numbers it qualifies"


def test_the_report_declares_the_data_depth_and_refuses_to_call_it_validation(long_run):
    _, _, rep, _ = long_run
    text = rep.render()
    assert "LONG-HISTORY VALIDATION: NOT AVAILABLE" in text
    assert "CURRENT HISTORICAL DEPTH" in text


def test_robust_positive_is_unreachable_on_a_short_sample(long_run):
    """Stated as a property, not as prose: the store cannot produce the top verdict."""
    _, _, rep, _ = long_run
    assert rep.time.months < sr.MIN_MONTHS_FOR_ROBUST
    assert rep.classification.verdict != sr.ROBUST_POSITIVE


def test_the_regime_split_is_built_from_prices_and_not_from_the_strategys_own_pnl(long_run):
    """A trend label taken from the strategy's P&L would make every split circular.

    Both defects were real in the first draft: volatility terciles were computed from equity
    marks, and 'trend' from `realized_net`, which produced buckets that said only that the
    strategy made money when it made money.
    """
    _, _, rep, _ = long_run
    vol = {b.name for b in rep.regime.splits["session volatility tercile"]}
    trend = {b.name for b in rep.regime.splits["session trend"]}
    assert vol == {"low ATR", "mid ATR", "high ATR"}, vol
    assert trend <= {"up trend", "down trend", "range-bound"}, trend
    # a tercile split must actually split
    counts = sorted(b.trades for b in rep.regime.splits["session volatility tercile"])
    assert counts[0] > 0, "the volatility split collapsed into one bucket"


def test_every_regime_bucket_is_shown_and_none_is_recommended(long_run):
    _, _, rep, _ = long_run
    for name, buckets in rep.regime.splits.items():
        assert sum(b.share_of_trades for b in buckets) == pytest.approx(1.0), name
    assert not hasattr(rep.regime, "best")
    assert "no bucket is selected" in rep.regime.note
