# quant-model

Autonomous quant trading research stack on a single Windows machine:

| Layer | Tool | Where |
|---|---|---|
| Backtesting | QuantConnect LEAN engine, built natively (.NET 10 + Python 3.11) | `..\Lean` |
| Strategy code | LEAN Python algorithms | `algorithms/` |
| Research reasoning and coding | Claude Code (CLI and IDE) | this repo |
| 24/7 automation | OpenClaw gateway, agent `quant`, workspace = this repo | `~/.openclaw` |
| Execution | Interactive Brokers, paper first, live only after approval | `live/` |

Docker and WSL2 are not available on this machine (virtualization is disabled in firmware),
so everything runs natively. See `AGENTS.md` for the operating manual the agent follows and
`CLAUDE.md` for the short rules every coding session must respect.

## Quick start

```powershell
. .\scripts\env.ps1                                    # dotnet, python 3.11, LEAN_ROOT
python scripts/backtest.py _template --tag "smoke"     # native backtest of the template
openclaw gateway status                                # automation gateway health
openclaw automations list --all                        # scheduled research jobs
```

## Research loop

`research/backlog.md` holds ranked hypotheses. Each automated iteration implements one,
backtests it with `scripts/backtest.py`, appends the run to `research/experiments.jsonl`,
writes a `research/journal.md` entry, and commits. `research/champion.json` tracks the
current best strategy.

## Status

- LEAN native build and Python backtests: working (sample data only).
- OpenClaw gateway: installed as the "OpenClaw Gateway" scheduled task; agent `quant` runs
  Claude Code through the Claude Max login.
- Automations: `research-iterate` every 2 hours, `research-review` daily at 06:30 local.
- Data: 69 symbols of daily history (1998-2026) from yfinance in LEAN format; intraday data
  needs IBKR historical data (IB Gateway login) or a QuantConnect subscription.
- Paper trading: IB Gateway installed at `C:\Jts\ibgateway`; `scripts/paper_trade.py` runs the
  champion's signal against the paper account with safety gates (see `live/README.md`).
  Waiting on the human's Gateway login and `live/APPROVED_PAPER.md`.

## Operating the loop

```powershell
openclaw automations list --all                 # jobs and next run times
openclaw automations runs <job-id> --limit 10   # run history
openclaw automations run <job-id>               # fire an iteration now
openclaw automations disable <job-id>           # pause the loop
Get-Content research\journal.md -TotalCount 40  # what the agent learned
```

## Dashboard

`scripts/dashboard.py` serves a local single-page monitor: the IBKR paper account (NAV, cash,
exposure, positions, open orders, fills), the intraday and daily sleeves as read from
`live/log`, integrity checks across those sources, NAV history, 1-minute price charts with
trade markers, the research ledger (`research/experiments.jsonl`, champion, backlog, journal),
data-store coverage, and system state (OpenClaw automations, scheduled tasks, git log,
gateway log).

```powershell
python scripts/dashboard.py --open      # installs fastapi/uvicorn if missing, opens the browser
```

URL: <http://127.0.0.1:8787/> (loopback only; `--port` changes the port). The dashboard is
read-only: the only file it ever writes is `live/state/nav_history.jsonl`, one NAV snapshot
per minute while IB Gateway is up. It never places orders, never edits config, and never
serves `live/secrets.env`. It holds one read-only IB connection with `clientId=81`, so the
launcher refuses to start when the port is already taken - never run two instances.

To start it at logon, `.\scripts\install_dashboard_task.ps1` registers the "Quant Dashboard"
scheduled task (`-Remove` unregisters it).
