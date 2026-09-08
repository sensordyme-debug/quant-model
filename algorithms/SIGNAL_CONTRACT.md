# Signal contract (shared between LEAN backtests and the IBKR paper runner)

Every strategy that can go to paper trading keeps its decision logic in a plain-pandas module
`algorithms/<name>/signal.py` that both `main.py` (LEAN) and `scripts/paper_trade.py` import.
No LEAN imports inside `signal.py`.

```python
UNIVERSE: list[str]            # Yahoo-style tickers, e.g. ["SPY", "TQQQ", "BRK-B"]
PARAMS: dict                   # default parameters, overridable

def target_weights(closes, as_of=None, params=None, state=None) -> dict[str, float]:
    """closes: DataFrame indexed by date (ascending), one column per UNIVERSE symbol,
    dividend/split-adjusted closes. as_of: last date to use (default: last row).
    state: optional dict with 'equity' and 'equity_high' for drawdown overlays.
    Returns {symbol: weight}. Weight is a fraction of net liquidation; positive = long,
    negative = short; omitted symbols mean zero. Sum of |weights| is the gross exposure."""
```

Rules

- Deterministic: same inputs, same output. No clock reads, no network calls.
- Only use data up to `as_of` (no look-ahead). The runner passes history through the previous
  close; the LEAN algorithm passes its `history()` frame.
- Round nothing inside the signal. Share rounding, minimum notional and order types belong to
  the runner and the LEAN execution model.
