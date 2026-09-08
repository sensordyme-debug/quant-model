# Template LEAN algorithm (Python, snake_case API).
# Copy this directory to algorithms/<strategy-name>/ and rename the class.
# Conventions the research loop relies on:
#   * exactly one QCAlgorithm subclass per main.py (scripts/backtest.py auto-detects it)
#   * keep tunable parameters as class attributes so experiments are diffable
#   * document the hypothesis in the class docstring
from AlgorithmImports import *


class TemplateAlgorithm(QCAlgorithm):
    """Hypothesis: buy-and-hold SPY baseline used to validate the toolchain."""

    def initialize(self):
        self.set_start_date(2013, 10, 7)
        self.set_end_date(2013, 10, 11)
        self.set_cash(100_000)
        self.symbol = self.add_equity("SPY", Resolution.MINUTE).symbol
        self.set_benchmark(self.symbol)

    def on_data(self, data: Slice):
        if not self.portfolio.invested and data.contains_key(self.symbol):
            self.set_holdings(self.symbol, 1.0)
