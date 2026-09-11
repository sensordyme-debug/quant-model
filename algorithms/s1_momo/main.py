# Backlog S-1: volatility-regime momentum rotation with the risk overlay built in.
# The trading logic itself lives in signals.py (plain pandas) so that the IBKR paper
# runner (I-1) executes byte-identical code. This file is only the LEAN plumbing:
# subscribe, schedule, fetch history, call the signal, submit the targets.
#
# Every parameter can be overridden by an S1_* environment variable, which is how
# scripts/sweep_s1.py runs the in-sample / out-of-sample split and the sensitivity grid
# without editing the file (backlog E-2).
import os
from pathlib import Path

from AlgorithmImports import *

import signals as sig

#: S-21. IBKR Pro USD schedule, blended per tranche: a $600k loan pays +1.5% over the
#: benchmark on its first $100k and +1.0% on the rest. Kept here rather than imported from
#: scripts/rates.py because LEAN puts only the algorithm's own directory on sys.path;
#: scripts/rates.py holds the identical constants and the docstring that sources them.
FIN_DEBIT_TIERS = ((100_000, 1.50), (1_000_000, 1.00), (50_000_000, 0.75), (float("inf"), 0.50))
FIN_CREDIT_SPREAD = 0.50      # credit interest is paid at benchmark - this, floored at zero
FIN_CREDIT_MIN = 10_000.0     # and only on the balance above this
FIN_DAY_COUNT = 360.0


def _fin_accrual(cash, benchmark_pct, days, shift=0.0):
    """Signed interest in dollars on a settled balance of `cash` for `days` calendar days.

    Negative is a charge. Identical arithmetic to `scripts/rates.py:accrual`, which is what
    `scripts/sweep_s21.py` prices the same book with outside LEAN.
    """
    if days <= 0:
        return 0.0
    frac = days / FIN_DAY_COUNT
    if cash < 0:
        owed, lower, cost = abs(cash), 0.0, 0.0
        for upper, spread in FIN_DEBIT_TIERS:
            tranche = max(0.0, min(owed, upper) - lower)
            if tranche <= 0:
                break
            cost += tranche * (benchmark_pct + spread + shift) / 100.0 * frac
            lower = upper
        return -cost
    earning = max(0.0, cash - FIN_CREDIT_MIN)
    return earning * max(0.0, benchmark_pct - FIN_CREDIT_SPREAD - shift) / 100.0 * frac


def _env(name, default, cast=float):
    raw = os.environ.get("S1_" + name)
    return default if raw is None or raw == "" else cast(raw)


def _env_date(name, default):
    raw = os.environ.get("S1_" + name)
    if not raw:
        return default
    return tuple(int(x) for x in raw.split("-"))


class S1MomentumRotationAlgorithm(QCAlgorithm):
    """Hypothesis: ranking a liquid unlevered ETF sleeve by blended 20/60/120-day
    momentum, holding the top 3 only while realized volatility is below its 1-year
    median, and sizing them to a vol target inside a fixed margin budget, produces a
    high-return series whose drawdown stays under 35%.

    The switches are deliberately separable so a failure is diagnosable: momentum picks
    *what*, the regime filter decides *whether*, the vol target and the margin budget
    decide *how much*.

    S-18 retired two of the original mechanisms, each on a measurement rather than a
    preference: the 3x proxies (which supplied exposure, not edge - S-15/S-16) and the
    drawdown breaker (which cost return in every window it was measured in and bought no
    drawdown once the book was unlevered - S-15/S-16). Both are one environment variable
    away (`S1_PROXY=on`, `S1_DD_HALVE=0.15 S1_DD_FLAT=0.25`).
    """

    def initialize(self):
        self.set_start_date(*_env_date("START", (2012, 1, 3)))
        self.set_end_date(*_env_date("END", (2026, 9, 4)))
        self.set_cash(100_000)

        # S-18 shipped the unlevered book, so the default is now "off" and needs no code:
        # signals.LEVERED_PROXY is empty and every winner is held in its own parent ETF.
        # S1_PROXY=on restores the 3x map, which reproduces the S-12 champion (with
        # S1_DD_HALVE=0.15 S1_DD_FLAT=0.25, the other half of the promotion) including its
        # OrderListHash 5246804e17a67af90028ffceead7d3b3. MARGIN_REQ is computed from
        # LEVERED_PROXY_3X and so is unaffected by this switch - see signals.py.
        if os.environ.get("S1_PROXY", "off").lower() == "on":
            sig.LEVERED_PROXY = dict(sig.LEVERED_PROXY_3X)

        # S-7 knobs: the ranking sleeve is a named preset ("etf", "wide", "megacap") rather
        # than a ticker list, so a sweep cannot silently subscribe to something the data
        # pipeline never wrote.
        sleeves = {
            "etf": tuple(sig.RANK_UNIVERSE),
            "wide": tuple(sig.RANK_UNIVERSE) + tuple(sig.MEGACAP_SLEEVE),
            "megacap": tuple(sig.MEGACAP_SLEEVE),
            # S-14 breadth: nested supersets of the shipped sleeve, so the only thing that
            # changes between them is how many candidates momentum gets to choose from.
            "sector": tuple(sig.RANK_UNIVERSE) + tuple(sig.SECTOR_SLEEVE),
            "broad": (tuple(sig.RANK_UNIVERSE) + tuple(sig.SECTOR_SLEEVE)
                      + tuple(sig.MACRO_SLEEVE)),
        }
        self.params = sig.Params(
            rank_universe=sleeves[os.environ.get("S1_SLEEVE", "etf")],
            # S-12: the shipped default is risk parity over a one-month vol window.
            # S1_WEIGHT_MODE=equal restores the S-10/S-11 champion's equal weighting, and
            # S1_ALLOC_VOL_POWER=0 is the same thing expressed as a zero tilt.
            weight_mode=os.environ.get("S1_WEIGHT_MODE", "invvol"),
            alloc_vol_window=_env("ALLOC_VOL_WINDOW", 21, int),
            alloc_vol_power=_env("ALLOC_VOL_POWER", 1.0),
            # D-3: 0 keeps the sleeve fixed (the shipped champion); a positive value makes
            # the sleeve above a candidate *pool* and re-picks that many members by
            # trailing dollar volume on each rebalance, using only bars up to that date.
            universe_size=_env("UNIVERSE_SIZE", 0, int),
            dv_window=_env("DV_WINDOW", 60, int),
            min_history=_env("MIN_HISTORY", 252, int),
            mom_lookbacks=tuple(int(x) for x in
                                os.environ.get("S1_LOOKBACKS", "20,60,120,252").split(",")),
            top_n=_env("TOP_N", 3, int),
            trend_window=_env("TREND_WINDOW", 0, int),
            regime_vol_window=_env("REGIME_VOL_WINDOW", 20, int),
            regime_median_window=_env("REGIME_MEDIAN_WINDOW", 252, int),
            regime_threshold=_env("REGIME_THRESHOLD", 1.5),
            target_exposure=_env("TARGET_EXPOSURE", 1.75),
            vol_est_window=_env("VOL_EST_WINDOW", 60, int),
            target_vol=_env("TARGET_VOL", 0.40),
            scale_cap=_env("SCALE_CAP", 2.0),
            margin_budget=_env("MARGIN_BUDGET", 0.75),
            max_gross_weight=_env("MAX_GROSS_WEIGHT", 2.0),
            # S-18: the drawdown overlay ships off (9.0 is an unreachable 900% drawdown).
            # S1_DD_HALVE=0.15 S1_DD_FLAT=0.25 restores the S-12 champion's breaker.
            dd_halve=_env("DD_HALVE", 9.0),
            dd_flat=_env("DD_FLAT", 9.0),
            dd_cooldown=_env("DD_COOLDOWN", 21, int),
            # S-8: all three default to the champion's behaviour. MARGIN_BUDGET_CAP=0
            # keeps the flat budget, TRAIL_STOP=0 disables the per-holding stop and
            # DD_MODE=step keeps the 1.0 / 0.5 / 0.0 breaker.
            margin_budget_cap=_env("MARGIN_BUDGET_CAP", 0.0),
            margin_budget_floor=_env("MARGIN_BUDGET_FLOOR", 0.0),
            trail_stop=_env("TRAIL_STOP", 0.0),
            trail_window=_env("TRAIL_WINDOW", 60, int),
            dd_mode=os.environ.get("S1_DD_MODE", "step"),
            # S-9: all four default to the champion's behaviour. MOM_SCORE=blend is the
            # plain mean of the trailing returns, MOM_CONFIRM=0 asks no horizon agreement
            # and ENTRY_MODE=absolute keeps the min_momentum floor.
            mom_score=os.environ.get("S1_MOM_SCORE", "blend"),
            mom_vol_window=_env("MOM_VOL_WINDOW", 60, int),
            mom_confirm=bool(_env("MOM_CONFIRM", 0, int)),
            entry_mode=os.environ.get("S1_ENTRY_MODE", "absolute"),
            min_rel_momentum=_env("MIN_REL_MOMENTUM", 0.0),
            # S-15 attribution: the absolute entry floor, exposed so the "no ranking at
            # all" control (S1_TOP_N=9 with the gate off) can be run without editing this
            # file. 0.0 is the champion's floor and leaves the order list unchanged.
            min_momentum=_env("MIN_MOMENTUM", 0.0),
            # S-10: the shipped skip is 5 sessions (one trading week) on the 120- and
            # 252-day horizons only; MOM_SKIP=0 restores the S-9 champion. MOM_WEIGHTS
            # empty gives the horizons an equal vote (S-10 rejected every weighting) and
            # S1_MOM_WEIGHTS is a comma list aligned with S1_LOOKBACKS.
            mom_skip=_env("MOM_SKIP", 5, int),
            mom_skip_min_lookback=_env("MOM_SKIP_MIN_LOOKBACK", 120, int),
            mom_weights=tuple(float(x) for x in
                              os.environ.get("S1_MOM_WEIGHTS", "").split(",") if x.strip()),
            # S-11: all three default to the champion's behaviour (no hysteresis, no
            # holding lock, no persistence requirement), so an unset environment
            # reproduces the S-10 order list exactly.
            hysteresis=_env("HYSTERESIS", 0.0),
            min_hold=_env("MIN_HOLD", 0, int),
            rank_persist=_env("RANK_PERSIST", 0, int),
            # O-1b: the options-implied size dial. IV_SCALE_POWER=0 is off and reproduces
            # the S-12 champion exactly; positive is the inverse reading (smaller book when
            # the market prices a big day), negative the direct one.
            iv_scale_power=_env("IV_SCALE_POWER", 0.0),
            iv_scale_field=os.environ.get("S1_IV_SCALE_FIELD", "iv_atm_1w"),
            iv_scale_window=_env("IV_SCALE_WINDOW", 60, int),
            iv_scale_min=_env("IV_SCALE_MIN", 0.5),
            iv_scale_max=_env("IV_SCALE_MAX", 1.5),
            # S-20: what the book holds while the regime gate is pulled. Empty is the
            # champion (the off-state is cash) and reproduces OrderListHash
            # a6d6224ce9c70091e5bfa8e96f046bf3. S1_RISK_OFF_SLEEVE is a comma list of
            # tickers that must exist in the daily store; they are added to the subscribed
            # universe automatically by signals.traded_universe.
            risk_off_sleeve=tuple(x.strip().upper() for x in
                                  os.environ.get("S1_RISK_OFF_SLEEVE", "").split(",")
                                  if x.strip()),
            risk_off_top_n=_env("RISK_OFF_TOP_N", 1, int),
            risk_off_exposure=_env("RISK_OFF_EXPOSURE", 1.0),
        )

        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.settings.minimum_order_margin_portfolio_percentage = 0.002

        # S-17, two execution assumptions this algorithm has never charged for. Both default
        # to the champion's behaviour, so a run with no environment override must still
        # reproduce OrderListHash 5246804e17a67af90028ffceead7d3b3.
        #
        #   S1_SLIPPAGE_BPS  a constant half-spread on every fill (see set_slippage_model
        #                    below). LEAN charges none at all.
        #   S1_SIGNAL_LAG    trading days of extra staleness between the last close the
        #                    signal reads and the open it fills at. The backtest decides on
        #                    the close of D and fills at the open of D+1 (one overnight gap).
        #                    `scripts/paper_trade.py` sends MKT orders at 15:45 ET off the
        #                    last complete yfinance daily bar, which during the session may
        #                    be D-1's close - one whole extra session of lag. This prices it.
        self.slippage_bps = _env("SLIPPAGE_BPS", 0.0)
        self.signal_lag = _env("SIGNAL_LAG", 0, int)

        # S-21, the third assumption of the same kind, and the only one with a sign that
        # depends on the calendar. LEAN charges **no financing at all**:
        # `DefaultBrokerageModel.GetMarginInterestRateModel` returns
        # `MarginInterestRateModel.Null`, whose `ApplyMarginInterestRate` is an empty method,
        # and `InteractiveBrokersBrokerageModel` does not override it. So a backtest of a book
        # that carries 1.50x gross borrows 0.50x of equity for nothing, and a book sitting in
        # cash through a risk-off episode earns nothing on it. Both are real at a broker.
        #
        #   S1_FINANCING       "on" accrues interest on the settled USD balance every day,
        #                      actual/360 on *calendar* days so a weekend costs three.
        #                      Default "off" is the champion, bit-identical.
        #   S1_FIN_SPREAD      shift (percentage points) applied to every tier spread and to
        #                      the credit spread, so the result can be read as a function of
        #                      the schedule rather than of one broker's price list. -1.5 puts
        #                      the loan at the benchmark itself.
        #   S1_FIN_RATES       benchmark CSV (default data/rates/usd_benchmark.csv, written by
        #                      scripts/rates.py from FRED's DFF - IBKR's USD "BM").
        #
        # The charge is applied to the cash book, so it flows into total_portfolio_value and
        # therefore into the next day's share sizing: this costs return the way a real debit
        # balance does, by compounding against the book, not as a reported statistic.
        self.financing = os.environ.get("S1_FINANCING", "off").lower() == "on"
        self.fin_spread = _env("FIN_SPREAD", 0.0)
        self.fin_rates, self.fin_last_day = {}, None
        self.fin_paid, self.fin_earned, self.fin_debit_days, self.fin_debit_sum = 0.0, 0.0, 0, 0.0
        if self.financing:
            import pandas as _pd
            rel = os.environ.get("S1_FIN_RATES", "data/rates/usd_benchmark.csv")
            path = Path(rel)
            if not path.exists():
                path = Path(__file__).resolve().parents[2] / rel
            frame = _pd.read_csv(path)
            self.fin_rates = dict(zip(frame["date"].astype(str), frame["rate_pct"].astype(float)))
            if not self.fin_rates:
                raise ValueError(f"S1_FINANCING=on but {path} holds no rates")
            self.fin_first, self.fin_final = min(self.fin_rates), max(self.fin_rates)
            self.log(f"FINANCING on: {len(self.fin_rates):,} benchmark days "
                     f"{self.fin_first}..{self.fin_final} spread_shift={self.fin_spread:+.2f}pp")

        self.symbols = {}
        for ticker in sig.traded_universe(self.params):
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            # This high leverage disables a LEAN accounting artifact, it does not buy
            # risk. MarketOnOpen orders do not settle until 09:30, so during a rotation
            # the outgoing and incoming legs are outstanding together and LEAN charges
            # initial margin on both without netting them. At 2x that rejected 1,467 of
            # 3,690 rebalances; the book then never reached target and churned trying,
            # burning $112k of commission. Real size is capped by the margin budget in
            # signals.py (S-6) and both gross notional and initial margin are measured
            # every day in on_data, so the run reports what was actually carried rather
            # than trusting LEAN's un-netted intraday margin accounting to enforce it.
            equity.set_leverage(10.0)
            # S-17: LEAN's IB brokerage model returns NullSlippageModel, so every backtest
            # in this repository has filled at the exact opening print with no spread and no
            # impact - `DefaultBrokerageModel.GetSlippageModel` returns
            # `NullSlippageModel.Instance` and the IB model does not override it. Commission
            # is charged, spread is not. This override charges a constant half-spread per
            # fill (`EquityFillModel.MarketOnOpenFill` applies the model: +slip on a buy,
            # -slip on a sell), so the cost the harness has never modelled can be priced.
            # Default 0.0 keeps the champion bit-identical.
            if self.slippage_bps > 0:
                equity.set_slippage_model(ConstantSlippageModel(self.slippage_bps / 1e4))
            self.symbols[ticker] = equity.symbol
        self.by_symbol = {s: t for t, s in self.symbols.items()}

        self.set_benchmark(self.symbols["SPY"])
        self.set_warm_up(self.params.history_bars, Resolution.DAILY)

        # Overlay state. equity_curve is the daily mark the drawdown breaker measures;
        # overlay_state carries its high-water mark and cooldown counter between days.
        self.equity_curve = []
        self.overlay_state = {}
        # Skip rebalancing trades worth less than this fraction of equity; daily
        # rotation on 3x ETFs otherwise pays commission on a stream of tiny adjustments.
        #
        # S-13 swept this for the first time (it had been pinned at 0.01 since S-1) to try to
        # win back the $8.3k of commission S-12's risk parity added. LEAN, full period:
        #
        #   band   CAR     Sharpe  MaxDD   orders  fees
        #   0.01   24.40%  0.921   25.1%   4,735   $45,695   <- shipped
        #   0.015  24.35%  0.919   26.9%   3,887   $44,239
        #   0.02   24.54%  0.927   25.2%   3,355   $43,960
        #   0.03   24.34%  0.917   25.5%   2,737   $42,329
        #   0.05   23.92%  0.900   29.2%   2,112   $39,729
        #   0.08   24.47%  0.920   25.4%   1,727   $39,568
        #
        # The response is **non-monotone and essentially flat**: across a factor of eight in
        # the band, and a factor of 2.7 in order count, CAR moves 24.40 -> 24.35 -> 24.54 ->
        # 24.34 -> 23.92 -> 24.47 with no trend. So this parameter does not have a best value
        # to find - the differences between neighbouring cells are path luck (a threshold
        # changes *which* day a rebalance fires, which reshuffles the whole subsequent path;
        # note the 4-point drawdown swing at 0.05, which no mechanism explains). 0.02 beats
        # the champion and `evaluate.py` would promote it; it was refused as a spike, because
        # both of its neighbours lose to 0.01. Do not re-fit this parameter.
        #
        # The useful reading is the flatness itself: ~3,000 of the champion's 4,735 orders
        # buy **nothing**, so a wide band is close to free *in backtest* and strictly better
        # live, where the spread the backtest does not model is paid per order. That is a
        # live-execution decision, not a research one - see BLOCKERS.md - so the shipped
        # default stays 0.01 and the I-1 OrderListHash is unchanged.
        self.min_order_value = _env("MIN_ORDER_VALUE", 0.01)
        self.max_observed_gross = 0.0
        self.max_observed_margin = 0.0
        self.rebalances = 0
        self.risk_on_days = 0
        self.exposure_sum = 0.0

        # Rebalancing is driven by the daily SPY bar (on_data), not by a scheduled event.
        #
        # The backlog asked for 15 minutes before the close, which daily bars cannot do:
        # a daily security's local time is its last bar stamp, so the exchange looks shut
        # at 15:45, LEAN downgrades market orders to MarketOnOpen, and IB rejects those
        # outside 04:00-09:28. Two runs placed 9,095 orders and filled none.
        #
        # A 09:00 scheduled event is worse in a subtler way. MarketOnOpen orders sent at
        # 09:00 on day D are still unfilled at 09:00 on day D+1, so the next rebalance
        # reads stale holdings of zero and stacks a second full target on top of the
        # first. Gross exposure reached 12.7x against a 1.0 cap and the account was wiped
        # out. Deciding on day D's close and filling at day D+1's open keeps exactly one
        # order batch in flight, and is what the I-1 runner can reproduce against IBKR.

    def price_frame(self):
        """`(adjusted closes, share volume)` for the traded universe, dates by ticker.

        Volume is only used by the D-3 point-in-time universe; it is fetched
        unconditionally because it arrives in the same history call and costs nothing.
        """
        history = self.history(list(self.symbols.values()),
                               self.params.history_bars + self.signal_lag,
                               Resolution.DAILY)
        if history.empty or "close" not in history.columns:
            return None, None
        # The unstacked columns are LEAN symbol keys ("SPY R735QTJ8P55O" or a Symbol
        # object, depending on the call); reduce both to the plain ticker signals.py wants.
        def frame(column):
            if column not in history.columns:
                return None
            out = history[column].unstack(level=0).rename(
                columns=lambda c: str(c).split(" ")[0].upper())
            # S-17: hide the last `signal_lag` sessions from the signal. The extra bars were
            # requested above, so the lookback windows keep their full length and the only
            # thing that changes is how stale the newest close is. Sizing still uses the
            # current price in submit_targets, so this isolates signal staleness from a
            # stale share count.
            return out.iloc[:-self.signal_lag] if self.signal_lag > 0 else out
        return frame("close"), frame("volume")

    def submit_targets(self, weights):
        """Turn target weights into share deltas and send them, sells first.

        Deliberately *not* `set_holdings(PortfolioTarget(...))`. That overload sizes a
        percentage against buying power rather than equity, so the account's leverage
        silently multiplies every target: identical signals produced 27% annualized vol
        at 2x and 43% at 4x, against the 16% the same weights produce on paper. Shares
        computed from equity are unambiguous, and this is also the order-list logic the
        IBKR runner in I-1 needs, so the two stay comparable.
        """
        equity = float(self.portfolio.total_portfolio_value)
        deltas = {}
        for ticker, symbol in self.symbols.items():
            price = float(self.securities[symbol].price)
            held = float(self.portfolio[symbol].quantity)
            target = 0.0 if price <= 0 else int(weights.get(ticker, 0.0) * equity / price)
            if abs(target - held) * max(price, 0.01) >= self.min_order_value * equity:
                deltas[symbol] = target - held

        if self.rebalances <= 6:
            self.log(f"SIZING {self.time} equity={equity:.0f} " + " ".join(
                f"{self.by_symbol[s]}:px={float(self.securities[s].price):.2f}"
                f",held={float(self.portfolio[s].quantity):.0f},d={d:.0f}"
                for s, d in deltas.items()))

        for symbol in sorted(deltas, key=lambda s: deltas[s]):   # sells before buys
            self.market_order(symbol, deltas[symbol])

    def accrue_financing(self):
        """Charge one day's interest on the settled USD balance (S-21).

        Called from `on_data`, before the rebalance, so the day's sizing already sees
        yesterday's financing. Days are *calendar* days since the last accrual, which is how
        a broker bills: a Friday debit balance is charged three days of interest by Monday.
        The benchmark table is forward-filled by `scripts/rates.py`, and a date past the end
        of it holds the last published rate rather than silently accruing nothing - the store
        ends at FRED's last publication, a few days behind a backtest that runs to today.
        """
        day = self.time.date()
        if self.fin_last_day is None:              # first live bar: start the clock, no charge
            self.fin_last_day = day
            return
        days = (day - self.fin_last_day).days
        if days <= 0:
            return
        self.fin_last_day = day
        cash = float(self.portfolio.cash_book["USD"].amount)
        stamp = min(max(day.isoformat(), self.fin_first), self.fin_final)
        benchmark = self.fin_rates[stamp]
        interest = _fin_accrual(cash, benchmark, days, self.fin_spread)
        if cash < 0:
            self.fin_debit_days += 1
            self.fin_debit_sum += -cash / max(1.0, float(self.portfolio.total_portfolio_value))
        if interest < 0:
            self.fin_paid -= interest
        else:
            self.fin_earned += interest
        if interest:
            self.portfolio.cash_book["USD"].add_amount(interest)

    def rebalance(self):
        if self.is_warming_up:
            return
        self.equity_curve.append(float(self.portfolio.total_portfolio_value))

        prices, volumes = self.price_frame()
        if prices is None or prices.empty:
            self.debug(f"{self.time}: no history frame")
            return

        # The date convention of the history frame, printed rather than assumed. LEAN can
        # stamp a daily bar either with its own session date or with the next midnight, and
        # anything that joins an external table onto this index (F-3's forecast file) is a
        # look-ahead bug if it guesses wrong. Log-only: compare `last_bar` and `spy_close`
        # against the store to see which date the last close really belongs to.
        if self.rebalances < 3:
            self.log(f"FRAME {self.time} last_bar={prices.index[-1]} "
                     f"spy_close={float(prices['SPY'].iloc[-1]):.4f} bars={len(prices)}")

        weights, diag = sig.target_weights(prices, self.equity_curve, self.params,
                                           self.overlay_state, volumes=volumes)
        self.overlay_state = diag.get("state", {})
        self.rebalances += 1
        if weights:
            self.risk_on_days += 1
            self.exposure_sum += float(diag.get("effective_exposure", 0.0))

        self.submit_targets(weights)

        if self.rebalances % 250 == 0:
            self.log(f"{self.time.date()} {diag.get('reason')} "
                     f"gross={diag.get('gross_weight')} margin={diag.get('margin_used')} "
                     f"exp={diag.get('effective_exposure')} "
                     f"scale={diag.get('vol_scale')} dd={diag.get('dd_multiplier')} "
                     f"{list(weights)}")
            if diag.get("universe_members"):
                # The sleeve as of this date. Printed so the run log itself is the evidence
                # that membership moved with the data rather than being fixed in 2026.
                self.log(f"  universe({diag.get('n_ranked')}/{diag.get('n_history_ok')}): "
                         f"{' '.join(diag['universe_members'])}")

    def on_data(self, data: Slice):
        equity = float(self.portfolio.total_portfolio_value)
        if equity > 0:
            # Audit: submit_targets is supposed to hold these at or below max_gross_weight
            # and margin_budget. Measuring them is what makes the high set_leverage above
            # safe to reason about - LEAN's own margin model is deliberately slack here, so
            # the broker-realistic constraint has to be checked against actual holdings.
            gross, margin = 0.0, 0.0
            for holding in self.portfolio.values():
                notional = abs(float(holding.holdings_value))
                gross += notional
                margin += notional * sig.MARGIN_REQ.get(
                    self.by_symbol.get(holding.symbol, ""), sig.BASE_MARGIN_REQ)
            self.max_observed_gross = max(self.max_observed_gross, gross / equity)
            self.max_observed_margin = max(self.max_observed_margin, margin / equity)

        if self.financing and not self.is_warming_up:
            self.accrue_financing()

        if not self.is_warming_up and data.bars.contains_key(self.symbols["SPY"]):
            self.rebalance()

    def on_end_of_algorithm(self):
        invested_share = self.risk_on_days / max(1, self.rebalances)
        mean_exposure = self.exposure_sum / max(1, self.risk_on_days)
        self.log("=== S-1 SUMMARY ===")
        self.log(f"params: lookbacks={self.params.mom_lookbacks} top_n={self.params.top_n} "
                 f"regime_threshold={self.params.regime_threshold} "
                 f"target_vol={self.params.target_vol} dd={self.params.dd_halve}/{self.params.dd_flat}")
        self.log(f"rebalances={self.rebalances} invested_days={self.risk_on_days} "
                 f"({invested_share:.1%}) mean_effective_exposure={mean_exposure:.2f}x")
        self.log(f"max gross exposure actually carried: {self.max_observed_gross:.3f} "
                 f"(ceiling {self.params.max_gross_weight})")
        budget = (f"elastic [{self.params.margin_budget_floor}, {self.params.margin_budget_cap}]"
                  if self.params.margin_budget_cap > 0 else str(self.params.margin_budget))
        self.log(f"max initial margin actually used: {self.max_observed_margin:.3f} "
                 f"(budget {budget})")
        if self.financing:
            days = max(1, self.fin_debit_days)
            self.log(f"financing: paid ${self.fin_paid:,.2f} earned ${self.fin_earned:,.2f} "
                     f"net ${self.fin_earned - self.fin_paid:,.2f} on {self.fin_debit_days} "
                     f"debit days, mean debit {self.fin_debit_sum / days:.3f}x equity "
                     f"(spread shift {self.fin_spread:+.2f}pp)")
