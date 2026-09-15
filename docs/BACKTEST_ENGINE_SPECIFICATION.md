# Backtest Engine — Specification

The contract the engine honours. Anything not stated here is not guaranteed.

## Fill convention

A position decided from bar *i*'s feature frame is **filled at bar *i*'s close** and earns from
bar *i*'s close to bar *i+1*'s close. There is no path by which a strategy receives a price
that existed before the information it used.

A position open on the session's final bar is **flattened at that bar's close** and pays its
closing leg. A NEW position may not be opened on the final bar: it could not be held, so it
would be entered and closed at the same price and could only lose a round turn
(`SessionSpec.last_entry_bar`, default `n - 2`).

## Order semantics implemented

| type | implemented | fill rule |
|---|---|---|
| market (signal-driven) | yes | bar close |
| stop (ATR or structural) | yes | **at the stop price**, when the bar's low (long) or high (short) reaches it |
| target (R multiple) | yes | **at the target price**, when the bar's high (long) or low (short) reaches it |
| trailing stop | yes | at the trailed level |
| break-even stop | yes | armed once MFE reaches the declared R |
| time stop | yes | at the close of the bar `n` bars after entry |
| signal invalidation | yes | at the close of the bar the signal changes |
| limit orders | **NOT implemented** | — |
| stop-limit | **NOT implemented** | — |
| partial fills | **NOT modelled** | every order fills in full |
| queue position / rejection / cancellation | **NOT modelled** | — |

## Intrabar ambiguity

OHLCV cannot say whether the high or the low came first. When a bar's range spans both the
stop and the target the engine takes the **STOP** and records `ambiguous=True` on the trade.
It never resolves toward the profitable side, and the ambiguous share is reported.

## Cost

Charged **per leg, at the bar the leg trades** — half a round turn in, half out. Not deferred
to the close, because the intraday equity path is what the Topstep twin reads and its trailing
limit tracks peak equity intraday.

`ExecutionSimulator.round_turn_cost` = `2 × commission_per_side + spread_ticks × tick_value`.
**It includes a spread crossing.** It is not commission alone.

Slippage is added on top, expressed as a **round-turn total in ticks**, never per leg.

## Execution scenario ladder

Every run computes all five. The headline is REALISTIC, never IDEAL.

| scenario | round-turn slippage |
|---|---|
| IDEAL | 0 ticks |
| OPTIMISTIC | 0.25 |
| REALISTIC | 0.5 |
| CONSERVATIVE | 1.0 |
| STRESS | 2.0 |

## Session

Window is `SessionSpec.open_et` to `close_et`, default 09:30–16:00 ET. A `close_et` past
16:10 ET is **refused**: 15:10 CT is Topstep's mandatory flat, verified as a wall clock in
America/Chicago across both DST states.

Only **structurally complete** sessions are used: exactly `SESSION_BARS` bars, first bar at the
open, last at the close. Short and early-close days are excluded, never padded or scaled.

## Data

Roll days (any trade date carrying more than one contract) are **excluded**. No continuous
contract is constructed and no back-adjustment is applied.

The engine **fails closed**: a missing store, zero complete sessions, or a feature failing
`audit_causality` all raise rather than substituting a default.

## What the engine will not do

- tune, select among, or modify a `StrategySpec`
- resample to another timeframe
- choose between two conflicting stop definitions
- report a net figure without also reporting gross
- report a result that does not reconcile three ways
