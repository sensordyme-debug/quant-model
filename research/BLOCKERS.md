# Blockers needing the human

Items the agent cannot resolve alone. Remove an item when it is resolved and note the date.

- **2026-09-08 Intraday market data (decision requested, blocks S-2).** Daily bars are done:
  D-1 shipped 69 symbols of free `yfinance` daily history, 1998-2026, and LEAN reads them.
  Intraday is still missing - Yahoo caps 1-minute history at about 30 days, too short to
  backtest. To unblock S-2 (opening-range breakout) the human should pick one of: IBKR
  historical data (needs IB Gateway logged in on this machine, no extra cost) or a
  QuantConnect data subscription (`lean data download`, needs `lean login`, paid).
  Until then the loop runs daily-frequency strategies only.
- **2026-09-08 Daily data quality (FYI, not blocking).** The `yfinance` stopgap is
  survivorship-biased (the universe is today's liquid names, so backtests before ~2015
  flatter momentum strategies) and carries no borrow costs or delisted tickers. Treat
  pre-2015 results as indicative. A paid feed would fix this.
- **2026-09-08 IBKR paper account.** Install IB Gateway and log in with the paper account so
  backlog I-1 can be built and tested. LEAN expects API port 4002 (Gateway) or 7497 (TWS).
