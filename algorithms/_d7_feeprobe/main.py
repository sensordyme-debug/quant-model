# D-7 / AUD-17 probe. NOT a strategy - a one-question instrument, kept in the repo because the
# answer decides whether the fix AUD-17 prescribes fixes anything.
#
# AUD-17's remedy is "store true raw prices with real split factors". That only helps if LEAN's
# per-share fee is charged on a share count the split factor has touched. LEAN's own sample data
# gives a free control: `Lean/Data/equity/usa/factor_files/aig.csv` carries split_factor 20 on
# every row before 2009-06-30 (AIG's 1:20 reverse split) and 1 after, over stored RAW prices -
# exactly the file this repo's fetcher does NOT write.
#
# So: buy a fixed DOLLAR amount of AIG once inside the split_factor == 20 era and once inside the
# split_factor == 1 era, in the ADJUSTED normalization mode every algorithm here uses, and log the
# price seen, the share count and the fee charged.
#
#   If the fee tracks the ADJUSTED share count in both eras, the split factor never reaches the fee
#   model, and rewriting the daily store as raw-plus-factors leaves the mis-charge exactly where it
#   is - the remedy has to be a fee model, not a data migration.
#   If the pre-split leg is charged ~20x the adjusted share count, the factor does reach it and
#   AUD-17's remedy is correct as written.
from AlgorithmImports import *

LEGS = [(2009, 6, 25), (2010, 6, 25)]   # split_factor 20 era, then split_factor 1 era
NOTIONAL_FRACTION = 0.10                # $10k of a $100k account, the sleeve's own order size


class D7FeeProbeAlgorithm(QCAlgorithm):
    """Hypothesis: LEAN's IB per-share fee is charged on the ADJUSTED share count regardless of
    the split factor, so AUD-17's prescribed store rewrite cannot change any fee."""

    def initialize(self):
        self.set_start_date(2009, 6, 20)
        self.set_end_date(2010, 7, 10)
        self.set_cash(100_000)
        self.equity = self.add_equity("AIG", Resolution.DAILY,
                                      data_normalization_mode=DataNormalizationMode.ADJUSTED)
        self.symbol = self.equity.symbol
        self.set_benchmark(self.symbol)
        self.legs = [datetime(*d).date() for d in LEGS]
        self.done = set()

    def on_data(self, data: Slice):
        today = self.time.date()
        for leg in self.legs:
            if leg in self.done or today < leg or not data.contains_key(self.symbol):
                continue
            price = float(self.securities[self.symbol].price)
            if price <= 0:
                continue
            qty = int((self.portfolio.total_portfolio_value * NOTIONAL_FRACTION) // price)
            self.log(f"D7PROBE leg={leg} date={today} adjusted_price={price:.6f} "
                     f"order_qty={qty} notional={qty * price:.2f}")
            if qty > 0:
                self.market_order(self.symbol, qty)
            self.done.add(leg)

    def on_order_event(self, order_event: OrderEvent):
        if order_event.status != OrderStatus.FILLED:
            return
        fee = float(order_event.order_fee.value.amount)
        qty = float(order_event.fill_quantity)
        px = float(order_event.fill_price)
        self.log(f"D7PROBE FILL date={self.time.date()} qty={qty} fill_price={px:.6f} "
                 f"notional={qty * px:.2f} fee={fee:.4f} "
                 f"fee_per_share={fee / abs(qty) if qty else 0:.6f} "
                 f"implied_shares_at_0.005={fee / 0.005:.1f}")
