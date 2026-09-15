# Backtest Trust Checklist

Run through this before believing any result. A `VALIDATED` status means every box in
section A passed automatically.

## A. Automatic — enforced by the engine, reported in `_result.json`

- [x] trade ledger total == daily total (to $0.01)
- [x] equity curve endpoint == daily total (to $0.01)
- [x] independent reference agrees — **skipped and reported** for bracketed exits
- [x] every trade carries a non-zero cost, unless commission was explicitly set to 0
- [x] session ends flat
- [x] no feature failed `audit_causality` (it raises inside `build_features`)
- [x] provenance present: spec hash, dataset hash, git SHA, dirty flag, versions
- [x] deterministic — two identical runs produce identical output

## B. Read these before trusting a number

- [ ] Is the **REALISTIC** row positive, not just IDEAL? A strategy positive only at zero
      slippage is flagged by the runner and is non-viable.
- [ ] What is the **ambiguous-bar share**? A high share means the result leans on the
      stop-first convention.
- [ ] How many **sessions** and how many **months**? The futures store is 12–15 months.
- [ ] Is **max drawdown below $2,000** at the traded size? If not, it is Topstep-incompatible
      regardless of P&L.
- [ ] What is the **DLL breach rate**? A strategy tripping the $1,000 daily limit weekly
      cannot compound.
- [ ] Does the **monthly median** agree in sign with the mean? A positive mean with a negative
      median is a lottery, not an income stream.
- [ ] What fraction of exits are **forced_flatten**? A high share means the exit rule is not
      really doing the work.
- [ ] Was the strategy **selected** from a set? The multiplicity bar then applies, and this
      engine does not enforce it.

## C. Things the engine cannot check for you

- whether the strategy was fitted to this data before you froze it
- whether the sample period is representative of the future
- whether the instrument will keep behaving this way
- partial fills, queue position, market impact beyond the modelled spread
- whether the Topstep rules have changed since `topstep.py` was last verified

## D. Red flags that should stop a promotion

| flag | why |
|---|---|
| `status != VALIDATED` | the arithmetic does not reconcile; the number is not a measurement |
| IDEAL positive, REALISTIC negative | the edge is the spread |
| drawdown > $2,000 at 1 contract | cannot be sized into compliance; the edge scales down with it |
| median month negative, mean positive | tail-carried; most months lose |
| < 100 trades | the standard error on $/trade will exceed the estimate |
| ambiguous share > 10% | the result is a convention, not a measurement |
