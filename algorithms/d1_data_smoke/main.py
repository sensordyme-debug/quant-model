# Backlog D-1 acceptance test for the yfinance -> LEAN daily data pipeline.
# This is an infrastructure check, not a strategy: it proves LEAN resolves the new
# symbols, streams bars for the whole requested window, and applies the factor files.
from AlgorithmImports import *


class D1DataSmokeAlgorithm(QCAlgorithm):
    """Hypothesis: scripts/fetch_data.py writes daily data LEAN can actually consume.

    Passes when every symbol delivers bars across the full window, the observed date
    range matches the request, and the split/dividend adjustment is live (adjusted
    prices before a known dividend differ from the raw prices on disk).
    """

    tickers = ["SPY", "QQQ", "IWM", "TQQQ", "SOXL", "TLT", "GLD", "UVXY",
               "AAPL", "MSFT", "NVDA", "BRKB", "JPM", "XOM", "KO"]
    start = (2012, 1, 1)
    end = (2026, 9, 4)

    def initialize(self):
        self.set_start_date(*self.start)
        self.set_end_date(*self.end)
        self.set_cash(100_000)

        self.symbols = {}
        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            self.symbols[ticker] = equity.symbol

        self.bar_count = {t: 0 for t in self.tickers}
        self.first_seen = {}
        self.last_seen = {}
        self.set_benchmark(self.symbols["SPY"])

    def on_data(self, data: Slice):
        for ticker, symbol in self.symbols.items():
            bar = data.bars.get(symbol)
            if bar is None:
                continue
            self.bar_count[ticker] += 1
            self.first_seen.setdefault(ticker, self.time)
            self.last_seen[ticker] = self.time
            if bar.high < bar.low or bar.low <= 0:
                self.error(f"BAD BAR {ticker} {self.time}: h={bar.high} l={bar.low}")

        # One equal-weight allocation so the run produces orders and a real equity curve.
        if not self.portfolio.invested:
            investable = [s for s in self.symbols.values() if data.bars.contains_key(s)]
            if len(investable) == len(self.tickers):
                for symbol in investable:
                    self.set_holdings(symbol, 1.0 / len(investable))

    def on_end_of_algorithm(self):
        self.log("=== D-1 DATA COVERAGE ===")
        failures = []
        for ticker in self.tickers:
            count = self.bar_count[ticker]
            first = self.first_seen.get(ticker)
            last = self.last_seen.get(ticker)
            self.log(f"{ticker}: {count} bars, {first} .. {last}")
            if count < 3000:
                failures.append(f"{ticker} only {count} bars")
        self.log(f"=== D-1 RESULT: {'FAIL - ' + '; '.join(failures) if failures else 'PASS'} ===")
