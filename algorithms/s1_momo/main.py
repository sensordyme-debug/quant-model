# Backlog S-1: volatility-regime momentum rotation with the risk overlay built in.
# The trading logic itself lives in signals.py (plain pandas) so that the IBKR paper
# runner (I-1) executes byte-identical code. This file is only the LEAN plumbing:
# subscribe, schedule, fetch history, call the signal, submit the targets.
#
# Every parameter can be overridden by an S1_* environment variable, which is how
# scripts/sweep_s1.py runs the in-sample / out-of-sample split and the sensitivity grid
# without editing the file (backlog E-2).
import os

from AlgorithmImports import *

import signals as sig


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
    momentum, holding the top 3 through 3x proxies only while realized volatility is
    below its 1-year median, and sizing to a 50% vol target under a drawdown overlay,
    produces a high-return series whose drawdown stays under 35%.

    The three switches are deliberately separable so a failure is diagnosable:
    momentum picks *what*, the regime filter decides *whether*, the vol target and
    drawdown overlay decide *how much*.
    """

    def initialize(self):
        self.set_start_date(*_env_date("START", (2012, 1, 3)))
        self.set_end_date(*_env_date("END", (2026, 9, 4)))
        self.set_cash(100_000)

        self.params = sig.Params(
            mom_lookbacks=tuple(int(x) for x in
                                os.environ.get("S1_LOOKBACKS", "20,60,120").split(",")),
            top_n=_env("TOP_N", 3, int),
            trend_window=_env("TREND_WINDOW", 0, int),
            regime_vol_window=_env("REGIME_VOL_WINDOW", 20, int),
            regime_median_window=_env("REGIME_MEDIAN_WINDOW", 252, int),
            regime_threshold=_env("REGIME_THRESHOLD", 1.5),
            target_exposure=_env("TARGET_EXPOSURE", 1.75),
            vol_est_window=_env("VOL_EST_WINDOW", 60, int),
            target_vol=_env("TARGET_VOL", 0.40),
            scale_cap=_env("SCALE_CAP", 2.0),
            max_gross_weight=_env("MAX_GROSS_WEIGHT", 1.0),
            dd_halve=_env("DD_HALVE", 0.15),
            dd_flat=_env("DD_FLAT", 0.25),
            dd_cooldown=_env("DD_COOLDOWN", 21, int),
        )

        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.settings.minimum_order_margin_portfolio_percentage = 0.002

        self.symbols = {}
        for ticker in sig.TRADED_UNIVERSE:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            # This high leverage disables a LEAN accounting artifact, it does not buy
            # risk. MarketOnOpen orders do not settle until 09:30, so during a rotation
            # the outgoing and incoming legs are outstanding together and LEAN charges
            # initial margin on both without netting them. At 2x that rejected 1,467 of
            # 3,690 rebalances; the book then never reached target and churned trying,
            # burning $112k of commission. Real gross exposure is capped at 1.0 by the
            # share math in submit_targets and is measured every day in on_data, so the
            # run reports what leverage was actually carried rather than assuming it.
            equity.set_leverage(10.0)
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
        self.min_order_value = _env("MIN_ORDER_VALUE", 0.01)
        self.max_observed_gross = 0.0
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
        """Adjusted closes for the traded universe as a tickers-by-date DataFrame."""
        history = self.history(list(self.symbols.values()), self.params.history_bars,
                               Resolution.DAILY)
        if history.empty or "close" not in history.columns:
            return None
        closes = history["close"].unstack(level=0)
        # The unstacked columns are LEAN symbol keys ("SPY R735QTJ8P55O" or a Symbol
        # object, depending on the call); reduce both to the plain ticker signals.py wants.
        return closes.rename(columns=lambda c: str(c).split(" ")[0].upper())

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

    def rebalance(self):
        if self.is_warming_up:
            return
        self.equity_curve.append(float(self.portfolio.total_portfolio_value))

        prices = self.price_frame()
        if prices is None or prices.empty:
            self.debug(f"{self.time}: no history frame")
            return

        weights, diag = sig.target_weights(prices, self.equity_curve, self.params,
                                           self.overlay_state)
        self.overlay_state = diag.get("state", {})
        self.rebalances += 1
        if weights:
            self.risk_on_days += 1
            self.exposure_sum += float(diag.get("effective_exposure", 0.0))

        self.submit_targets(weights)

        if self.rebalances % 250 == 0:
            self.log(f"{self.time.date()} {diag.get('reason')} "
                     f"gross={diag.get('gross_weight')} exp={diag.get('effective_exposure')} "
                     f"scale={diag.get('vol_scale')} dd={diag.get('dd_multiplier')} "
                     f"{list(weights)}")

    def on_data(self, data: Slice):
        equity = float(self.portfolio.total_portfolio_value)
        if equity > 0:
            # Audit: submit_targets is supposed to hold this at or below max_gross_weight.
            # Measuring it is what makes the high set_leverage above safe to reason about.
            gross = sum(abs(float(h.holdings_value)) for h in self.portfolio.values()) / equity
            self.max_observed_gross = max(self.max_observed_gross, gross)

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
                 f"(cap {self.params.max_gross_weight})")
