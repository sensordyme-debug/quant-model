# Signal contract (shared between LEAN backtests and the IBKR paper runner)

Every strategy that can go to paper trading keeps its decision logic in a plain-pandas module
`algorithms/<name>/signal.py` (or `signals.py`) that both `main.py` (LEAN) and
`scripts/paper_trade.py` import. No LEAN imports inside it.

```python
UNIVERSE: list[str]            # or TRADED_UNIVERSE: every ticker that must be subscribed/fetched
                               # Yahoo-style tickers, e.g. ["SPY", "TQQQ", "BRK-B"]

def target_weights(prices, equity_curve=(), params=None, state=None):
    """prices: DataFrame indexed by date (ascending), one column per universe symbol,
    dividend/split-adjusted closes, only rows up to the decision date (no look-ahead).
    equity_curve: sequence of portfolio equity values, oldest first (for drawdown overlays).
    params: strategy parameter object or None for defaults.
    state: JSON-serializable dict returned by the previous call (cooldowns, latches).
    Returns either {symbol: weight} or ({symbol: weight}, diagnostics) where
    diagnostics["state"] is the dict to feed back next time.
    Weight is a fraction of net liquidation; positive = long, negative = short; omitted
    symbols mean zero. Sum of |weights| is the gross exposure."""
```

The runner introspects the signature and passes only the arguments the function declares
(`as_of` is also accepted), so simpler signals can drop parameters they do not use.

Rules

- Deterministic: same inputs, same output. No clock reads, no network calls.
- Only use data up to the last row of `prices`. The runner passes history through the
  previous close; the LEAN algorithm passes its `history()` frame.
- Round nothing inside the signal. Share rounding, minimum notional and order types belong to
  the runner and the LEAN execution model.
- Keep `state` small and JSON-serializable; the runner persists it in `live/state/last_run.json`.
