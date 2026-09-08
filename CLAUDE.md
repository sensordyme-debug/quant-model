# CLAUDE.md

Quant trading research repo. Strategies are LEAN (QuantConnect) Python algorithms, backtested
natively on Windows and later paper-traded on Interactive Brokers. An OpenClaw agent runs the
improvement loop unattended; `AGENTS.md` is the full operating manual and applies to every
session in this repo.

## Commands

```powershell
. .\scripts\env.ps1                                   # toolchain env (dotnet, python 3.11, LEAN_ROOT)
python scripts/backtest.py <algorithm> --tag "why"    # native LEAN backtest, records the run
py -3.11 -c "import pandas"                           # LEAN's Python is 3.11, not the default 3.14
dotnet build ..\Lean\Launcher\QuantConnect.Lean.Launcher.csproj -c Release   # rebuild LEAN
```

## Rules

- One QCAlgorithm subclass per `algorithms/<name>/main.py`, snake_case LEAN API
  (`initialize`, `on_data`, `set_holdings`, `add_equity`).
- Every backtest goes through `scripts/backtest.py` so it lands in `research/experiments.jsonl`.
- Do not use `lean backtest` (needs Docker, unavailable here). Do not run the LEAN launcher
  with `environment=live-*` unless `live/APPROVED_PAPER.md` exists, and never with
  `ib-trading-mode=live`.
- Ignore the pythonnet GIL finalizer exception the engine prints on shutdown; success is the
  presence of `<Class>-summary.json` in the run directory.
- Never commit secrets. IBKR credentials come from environment variables or `live/secrets.json`
  (gitignored).
