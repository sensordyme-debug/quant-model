# POSITIVE CONTROL for the ES tick probe. Identical logic, MINUTE resolution.
#
# Its only job is to distinguish two explanations of the tick probe's zero counts:
#   (a) this LEAN installation has no ES tick data, or
#   (b) the probe itself is misconfigured and would report zero whatever the data.
# If minute bars arrive here, (b) is ruled out and the tick result stands as a data fact.
#
# This is an INFRASTRUCTURE CHECK, not a strategy: it places no orders.
#
# It answers one question the CVD strategy depends on, and answers it from the engine rather
# than from documentation: WHAT ES FUTURES DATA DOES THIS LEAN INSTALLATION ACTUALLY DELIVER?
#
# Specifically, per trade and per quote:
#     timestamp, trade price, trade quantity, bid, ask, bid size, ask size, exchange, contract
# and whether trade and quote events can be causally aligned (a quote at or before each trade).
#
# WHY THIS EXISTS AS A LEAN ALGORITHM RATHER THAN A FILE SURVEY
# A directory listing tells you which .zip files sit on disk. It does not tell you what the
# engine resolves, maps, filters and hands to on_data - which is the only thing a strategy can
# actually consume. Contract filters, mapping and market hours all sit between the files and
# the algorithm, so the probe asks the engine.
from AlgorithmImports import *


class F3EsMinuteProbeAlgorithm(QCAlgorithm):
    """Hypothesis: none. Reports what ES data LEAN can serve at TICK resolution.

    PASSES (for CVD purposes) only if trade ticks AND quote ticks both arrive with the
    fields the tick test needs. Anything less is reported as-is; the probe never fabricates
    or interpolates a field it did not receive.
    """

    # The window LEAN's bundled sample data covers. Deliberately small: the question is
    # whether the fields exist at all, not how many of them there are.
    start = (2013, 10, 6)
    end = (2013, 10, 16)

    def initialize(self):
        self.set_start_date(*self.start)
        self.set_end_date(*self.end)
        self.set_cash(100_000)

        # America/New_York for every session rule this repository expresses. Never the
        # machine's local zone.
        self.set_time_zone(TimeZones.NEW_YORK)

        # RAW prices: an adjusted continuous series contains prices that were never quoted,
        # and a fill against one could not have happened. For a probe it also keeps what we
        # observe identical to what is on disk.
        future = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            Resolution.MINUTE,
            data_normalization_mode=DataNormalizationMode.RAW,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            contract_depth_offset=0,
        )
        future.set_filter(0, 182)
        self.continuous = future.symbol

        # ---- counters. Everything reported is counted, never inferred. ----
        self.slices = 0
        self.trade_ticks = 0
        self.quote_ticks = 0
        self.openinterest_ticks = 0
        self.other_ticks = 0

        # field presence, counted separately from tick counts so a field that is present but
        # always zero is distinguishable from one that is absent
        self.have_price = 0
        self.have_quantity = 0
        self.have_bid = 0
        self.have_ask = 0
        self.have_bid_size = 0
        self.have_ask_size = 0
        self.have_exchange = 0

        # causal alignment: for each trade, was a quote seen at or before its timestamp?
        self.trades_with_prior_quote = 0
        self.trades_without_prior_quote = 0
        self._last_quote_time = {}

        self.contracts_seen = {}
        self.first_tick_time = None
        self.last_tick_time = None
        self.sample_rows = []

        # bar-resolution fallback, so the report can say what IS available when ticks are not
        self.trade_bars = 0
        self.quote_bars = 0

    def on_data(self, data: Slice):
        self.slices += 1

        # ---- ticks ----
        ticks = getattr(data, "ticks", None)
        if ticks:
            for symbol in ticks.keys():
                for tick in ticks[symbol]:
                    self._record_tick(symbol, tick)

        # ---- bars, to characterise the fallback resolutions ----
        if getattr(data, "bars", None):
            for symbol in data.bars.keys():
                if symbol.security_type == SecurityType.FUTURE:
                    self.trade_bars += 1
        if getattr(data, "quote_bars", None):
            for symbol in data.quote_bars.keys():
                if symbol.security_type == SecurityType.FUTURE:
                    self.quote_bars += 1

    def _record_tick(self, symbol, tick):
        key = str(symbol.value)
        self.contracts_seen[key] = self.contracts_seen.get(key, 0) + 1

        if self.first_tick_time is None:
            self.first_tick_time = tick.time
        self.last_tick_time = tick.time

        kind = tick.tick_type
        if kind == TickType.TRADE:
            self.trade_ticks += 1
            # causality: a trade may only be classified against a quote that already exists
            prior = self._last_quote_time.get(key)
            if prior is not None and prior <= tick.time:
                self.trades_with_prior_quote += 1
            else:
                self.trades_without_prior_quote += 1
            if tick.price:
                self.have_price += 1
            if tick.quantity:
                self.have_quantity += 1
        elif kind == TickType.QUOTE:
            self.quote_ticks += 1
            self._last_quote_time[key] = tick.time
            if tick.bid_price:
                self.have_bid += 1
            if tick.ask_price:
                self.have_ask += 1
            if tick.bid_size:
                self.have_bid_size += 1
            if tick.ask_size:
                self.have_ask_size += 1
        elif kind == TickType.OPEN_INTEREST:
            self.openinterest_ticks += 1
        else:
            self.other_ticks += 1

        if getattr(tick, "exchange", ""):
            self.have_exchange += 1

        if len(self.sample_rows) < 12:
            self.sample_rows.append(
                f"{tick.time} {key} {kind} px={tick.price} qty={tick.quantity} "
                f"bid={tick.bid_price} ask={tick.ask_price} "
                f"bsz={tick.bid_size} asz={tick.ask_size} exch='{tick.exchange}'"
            )

    def on_end_of_algorithm(self):
        total = self.trade_ticks + self.quote_ticks + self.openinterest_ticks + self.other_ticks

        self.log("==== ES TICK PROBE ====")
        self.log(f"PROBE slices={self.slices} total_ticks={total}")
        self.log(
            f"PROBE trade_ticks={self.trade_ticks} quote_ticks={self.quote_ticks} "
            f"openinterest_ticks={self.openinterest_ticks} other={self.other_ticks}"
        )
        self.log(f"PROBE trade_bars={self.trade_bars} quote_bars={self.quote_bars}")
        self.log(
            f"PROBE fields price={self.have_price} qty={self.have_quantity} "
            f"bid={self.have_bid} ask={self.have_ask} "
            f"bid_size={self.have_bid_size} ask_size={self.have_ask_size} "
            f"exchange={self.have_exchange}"
        )
        self.log(
            f"PROBE causality trades_with_prior_quote={self.trades_with_prior_quote} "
            f"trades_without_prior_quote={self.trades_without_prior_quote}"
        )
        self.log(f"PROBE window first_tick={self.first_tick_time} last_tick={self.last_tick_time}")
        self.log(f"PROBE contracts={sorted(self.contracts_seen.items())[:10]}")
        for row in self.sample_rows:
            self.log(f"PROBE sample {row}")

        # The verdict, stated by the probe rather than left to a reader of the counters.
        cvd_ready = (
            self.trade_ticks > 0
            and self.quote_ticks > 0
            and self.have_price > 0
            and self.have_quantity > 0
            and self.have_bid > 0
            and self.have_ask > 0
        )
        self.log(f"PROBE MINUTE_CONTROL bars_seen={self.trade_bars + self.quote_bars}")
        self.log(f"PROBE CVD_RECONSTRUCTABLE={'YES' if cvd_ready else 'NO'}")
        if not cvd_ready:
            missing = []
            if self.trade_ticks == 0:
                missing.append("trade ticks")
            if self.quote_ticks == 0:
                missing.append("quote ticks")
            if self.have_bid == 0:
                missing.append("bid")
            if self.have_ask == 0:
                missing.append("ask")
            if self.have_quantity == 0:
                missing.append("trade quantity")
            self.log(f"PROBE MISSING={missing}")

        # Surfaced as statistics so scripts/backtest.py records them in experiments.jsonl.
        self.set_runtime_statistic("TradeTicks", str(self.trade_ticks))
        self.set_runtime_statistic("QuoteTicks", str(self.quote_ticks))
        self.set_runtime_statistic("TradeBars", str(self.trade_bars))
        self.set_runtime_statistic("QuoteBars", str(self.quote_bars))
        self.set_runtime_statistic("CvdReconstructable", "YES" if cvd_ready else "NO")
