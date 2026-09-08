# Backlog S-3: cross-sectional short-term reversal, dollar neutral.
# Decision logic lives in signals.py (plain pandas) so the I-1 paper runner can execute
# byte-identical code; this file is LEAN plumbing only.
#
# Every parameter is overridable by an S3_* environment variable, which is how
# scripts/sweep_s3.py and the IS/OOS split run without editing the file.
import os

from AlgorithmImports import *

import signals as sig


def _env(name, default, cast=float):
    raw = os.environ.get("S3_" + name)
    return default if raw is None or raw == "" else cast(raw)


def _env_date(name, default):
    raw = os.environ.get("S3_" + name)
    if not raw:
        return default
    return tuple(int(x) for x in raw.split("-"))


class S3ReversalAlgorithm(QCAlgorithm):
    """Hypothesis: among the most liquid single names, the biggest 1-5 day losers
    out-perform the biggest 1-5 day winners over the following session, and trading that
    spread dollar-neutral produces a return stream uncorrelated with the S-1 momentum
    champion - which is the only way left to raise portfolio volatility after S-8 measured
    that leverage on the ETF sleeve cannot buy it inside the 35% drawdown limit.

    Read the correlation before the Sharpe: a mediocre Sharpe at zero correlation is worth
    more to the S-5 allocator than a good Sharpe that just re-buys the champion's risk.
    """

    def initialize(self):
        self.set_start_date(*_env_date("START", (2012, 1, 3)))
        self.set_end_date(*_env_date("END", (2026, 9, 4)))
        self.set_cash(100_000)

        self.params = sig.Params(
            pool=os.environ.get("S3_POOL", "megacap"),
            universe_size=_env("UNIVERSE_SIZE", 30, int),
            dv_window=_env("DV_WINDOW", 60, int),
            min_history=_env("MIN_HISTORY", 252, int),
            lookback=_env("LOOKBACK", 5, int),
            vol_adjust=bool(_env("VOL_ADJUST", 0, int)),
            vol_window=_env("VOL_WINDOW", 20, int),
            n_side=_env("N_SIDE", 10, int),
            direction=_env("DIRECTION", 1, int),
            gross=_env("GROSS", 2.0),
            vol_est_window=_env("VOL_EST_WINDOW", 60, int),
            target_vol=_env("TARGET_VOL", 0.20),
            scale_cap=_env("SCALE_CAP", 2.0),
            margin_budget=_env("MARGIN_BUDGET", 0.75),
            max_gross_weight=_env("MAX_GROSS_WEIGHT", 3.0),
            dd_halve=_env("DD_HALVE", 0.15),
            dd_flat=_env("DD_FLAT", 0.25),
            dd_cooldown=_env("DD_COOLDOWN", 21, int),
            dd_mode=os.environ.get("S3_DD_MODE", "step"),
        )

        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.settings.minimum_order_margin_portfolio_percentage = 0.002

        self.symbols = {}
        for ticker in sig.traded_universe(self.params):
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            # Same reasoning as S-1: market orders on daily bars fill at the next open, so
            # during a rotation both legs are outstanding and LEAN charges un-netted
            # initial margin on each. The real constraint is the margin budget inside
            # signals.py, and on_data audits the gross and margin actually carried.
            equity.set_leverage(10.0)
            self.symbols[ticker] = equity.symbol
        self.by_symbol = {s: t for t, s in self.symbols.items()}

        self.set_benchmark(self.symbols[sig.TRIGGER_TICKER])
        self.set_warm_up(self.params.history_bars, Resolution.DAILY)

        self.equity_curve = []
        self.overlay_state = {}
        self.min_order_value = _env("MIN_ORDER_VALUE", 0.01)
        self.max_observed_gross = 0.0
        self.max_observed_margin = 0.0
        self.max_observed_net = 0.0
        self.rebalances = 0
        self.invested_days = 0
        self.gross_sum = 0.0
        self.net_sum = 0.0
        # Daily equity marks, written to results/ so the sleeve's correlation with the
        # champion can be computed from the engine's own numbers rather than the sweep's.
        self.marks = []

    def price_frame(self):
        """`(adjusted closes, share volume)` for the subscribed universe, dates by ticker."""
        history = self.history(list(self.symbols.values()), self.params.history_bars,
                               Resolution.DAILY)
        if history.empty or "close" not in history.columns:
            return None, None

        def frame(column):
            if column not in history.columns:
                return None
            return history[column].unstack(level=0).rename(
                columns=lambda c: str(c).split(" ")[0].upper())
        return frame("close"), frame("volume")

    def submit_targets(self, weights):
        """Signed target weights -> netted share deltas, sells (and shorts) first.

        `int()` truncates toward zero, so a short target rounds to the smaller short - the
        conservative direction on both sides.
        """
        equity = float(self.portfolio.total_portfolio_value)
        deltas = {}
        for ticker, symbol in self.symbols.items():
            price = float(self.securities[symbol].price)
            held = float(self.portfolio[symbol].quantity)
            target = 0.0 if price <= 0 else int(weights.get(ticker, 0.0) * equity / price)
            if abs(target - held) * max(price, 0.01) >= self.min_order_value * equity:
                deltas[symbol] = target - held

        if self.rebalances <= 3:
            self.log(f"SIZING {self.time} equity={equity:.0f} " + " ".join(
                f"{self.by_symbol[s]}:px={float(self.securities[s].price):.2f}"
                f",held={float(self.portfolio[s].quantity):.0f},d={d:.0f}"
                for s, d in deltas.items()))

        for symbol in sorted(deltas, key=lambda s: deltas[s]):
            self.market_order(symbol, deltas[symbol])

    def rebalance(self):
        if self.is_warming_up:
            return
        equity = float(self.portfolio.total_portfolio_value)
        self.equity_curve.append(equity)
        self.marks.append((self.time.date().isoformat(), equity))

        prices, volumes = self.price_frame()
        if prices is None or prices.empty:
            self.debug(f"{self.time}: no history frame")
            return

        weights, diag = sig.target_weights(prices, self.equity_curve, self.params,
                                           self.overlay_state, volumes=volumes)
        self.overlay_state = diag.get("state", {})
        self.rebalances += 1
        if weights:
            self.invested_days += 1
            self.gross_sum += float(diag.get("gross_weight", 0.0))
            self.net_sum += abs(float(diag.get("net_weight", 0.0)))

        self.submit_targets(weights)

        if self.rebalances % 250 == 0:
            self.log(f"{self.time.date()} {diag.get('reason')} "
                     f"gross={diag.get('gross_weight')} net={diag.get('net_weight')} "
                     f"margin={diag.get('margin_used')} scale={diag.get('vol_scale')} "
                     f"portvol={diag.get('portfolio_vol')} dd={diag.get('dd_multiplier')}")
            self.log(f"  long {diag.get('longs')} / short {diag.get('shorts')}")

    def on_data(self, data: Slice):
        equity = float(self.portfolio.total_portfolio_value)
        if equity > 0:
            gross, margin, net = 0.0, 0.0, 0.0
            for holding in self.portfolio.values():
                value = float(holding.holdings_value)
                gross += abs(value)
                net += value
                margin += abs(value) * sig.MARGIN_REQ.get(
                    self.by_symbol.get(holding.symbol, ""), sig.BASE_MARGIN_REQ)
            self.max_observed_gross = max(self.max_observed_gross, gross / equity)
            self.max_observed_margin = max(self.max_observed_margin, margin / equity)
            self.max_observed_net = max(self.max_observed_net, abs(net) / equity)

        if not self.is_warming_up and data.bars.contains_key(self.symbols[sig.TRIGGER_TICKER]):
            self.rebalance()

    def on_end_of_algorithm(self):
        self.log("=== S-3 SUMMARY ===")
        self.log(f"params: pool={self.params.pool} universe_size={self.params.universe_size} "
                 f"lookback={self.params.lookback} vol_adjust={self.params.vol_adjust} "
                 f"n_side={self.params.n_side} direction={self.params.direction} "
                 f"gross={self.params.gross} "
                 f"target_vol={self.params.target_vol} budget={self.params.margin_budget}")
        self.log(f"rebalances={self.rebalances} invested_days={self.invested_days} "
                 f"({self.invested_days / max(1, self.rebalances):.1%}) "
                 f"mean_gross={self.gross_sum / max(1, self.invested_days):.2f} "
                 f"mean_abs_net={self.net_sum / max(1, self.invested_days):.4f}")
        self.log(f"max gross carried {self.max_observed_gross:.3f} "
                 f"(ceiling {self.params.max_gross_weight}), "
                 f"max margin used {self.max_observed_margin:.3f} "
                 f"(budget {self.params.margin_budget}), "
                 f"max |net| carried {self.max_observed_net:.3f}")
        # One line per session so the allocator work (S-5) has a return series to correlate.
        self.log("=== S-3 EQUITY CURVE ===")
        for date, value in self.marks:
            self.log(f"MARK {date} {value:.2f}")
