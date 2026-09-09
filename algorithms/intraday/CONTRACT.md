# Intraday (active sleeve) signal contract

The active sleeve trades a universe disjoint from the daily champion (see
`scripts/intraday_common.py:UNIVERSE`), evaluates every completed 1-minute bar, and is flat
before 15:40 ET so the daily runner at 15:45 only ever sees its own book.

Each strategy is a module `algorithms/intraday/<name>/signal.py`:

```python
NAME = "orb"
PARAMS = {...}                                   # defaults, JSON-serializable

def decide(now, feats, book, equity, state, params) -> dict[str, float]:
    """now:    pd.Timestamp (ET) of the bar that just COMPLETED (bar start time)
    feats:  {symbol: DataFrame} of causal per-bar features up to and including `now`
            (see algorithms/intraday/base.py:features); feats[s].iloc[-1] is the latest bar
    book:   {symbol: shares} currently held by THIS strategy (framework-tracked)
    equity: net liquidation in dollars
    state:  JSON-serializable dict persisted across calls (reset it yourself on a new session)
    params: PARAMS merged with overrides
    returns {symbol: target weight}; fraction of equity, +long / -short, omitted = 0."""
```

Rules

- Causal only: every feature in `base.features` uses bars up to its own row. `decide` may
  only look at `feats[s].iloc[:-k]` history and the current row. No clock reads, no network.
- Deterministic and stateless except through `state`. The same bar stream must produce the
  same orders in `scripts/intraday_backtest.py`, in `scripts/intraday_trader.py --replay`, and live.
- Sizing is in weights; the framework converts to whole shares, applies the per-symbol and
  gross caps, the minimum-change band, the daily loss limit, and the end-of-day flatten.
- Execution assumption: a decision made on the close of bar t is filled at the open of bar
  t+1 plus slippage (`intraday_common.SLIPPAGE_BPS`), which is what a market order sent at
  the minute boundary gets live.
