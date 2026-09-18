# topstep_backtester — ARCHIVED

```
STATUS:                 FROZEN / ARCHIVED
ACTIVE_BACKTEST_ENGINE: NO
ARCHIVED_ON:            2026-09-18
SUPERSEDED_BY:          QuantConnect LEAN
WRAPPED_ENGINE:         topstep-backtest 0.4.0 (pip, site-packages, never modified)
```

## Why

The CVD_ABSORPTION_HARVESTER specification requires genuine tick-level trade and quote
information to reconstruct cumulative volume delta: each trade classified against the bid and
ask standing at that trade. The data available to this path does not provide sufficient
Time & Sales / order-flow information — a survey of all 2,779 parquet files in `data/` found a
minimum inter-record gap of **60 seconds** and **zero simultaneous prints**, which is a
resampled grid rather than a trade sequence.

Rather than approximating the required inputs, or continuing to expand a custom engine until
it grew a tick pipeline of its own, the project migrated to **QuantConnect LEAN**, which
natively supports futures tick, trade and quote data.

## What freezing means

| | |
|---|---|
| code deleted | **no** — every module stays where it is |
| results deleted | **no** — recorded results must stay reproducible |
| behaviour changed | **no** — see below |
| starts a new backtest | **no** — `run_backtest` refuses by default |
| reproduces an archived result | **yes** — pass `allow_archived=True` at the call site |

`archive.assert_active()` gates every entry point. The escape is a keyword argument rather
than a config value or an environment variable, so it has to appear at the call site where a
reader can see that the call is archival rather than new research.

## What must not happen to this package

No behaviour changes. Not the fill model, not the data handling, not the remaining
specification ambiguities, not the tick-data problem. Changing a frozen engine invalidates
every result recorded under it **while leaving those results looking current**, which is worse
than either keeping it or deleting it. If it needs to change, it is not archived any more, and
that is a decision with a date on it.

## What is preserved here

- `docs/PIPELINE_CERTIFICATION.md` — the forensic integration audit (verdict YELLOW)
- `docs/UPSTREAM_FINDINGS.md` — five findings against `topstep-backtest` 0.4.0
- `docs/CVD_ABSORPTION_HARVESTER_XFA_V2.0_REPORT.md` — the blocked-backtest report
- `strategies/cvd_absorption_harvester/` — the frozen spec, its 17-item ambiguity register,
  the CVD classifier, the divergence detector and the governor, all tested
- 212 passing tests, including the governor integration test and the lookahead canaries

The CVD work is **not lost**. The specification, the ambiguity register and the governor are
engine-independent, and the eleven unresolved register items still need owner rulings before
any engine can run the strategy.
