# live/ - paper and live deployment

Nothing here is ever committed with credentials. IB Gateway holds the login; the runner only
talks to it over the local API socket.

## Files

- `APPROVED_PAPER.md` - **the human's go-ahead**. `scripts/paper_trade.py` refuses to send
  paper orders while this file is missing. Create it (any content, ideally the date and the
  champion name) when the champion is approved for paper trading. Never create it from an
  automated job.
- `HALT` - kill switch. If present, the next run flattens every position and stops. Delete it
  to resume.
- `log/YYYY-MM-DD.jsonl` - every plan, order, fill and refusal, one JSON object per line.
- `state/last_run.json` - last targets, equity high-water mark used by drawdown overlays.

## IB Gateway setup (one time, human)

1. Start `C:\Jts\ibgateway\ibgateway.exe`, choose **Paper Trading**, log in, approve IB Key.
2. Configure -> Settings -> API -> Settings: enable "ActiveX and Socket Clients", socket port
   **4002**, uncheck "Read-Only API", trusted IP `127.0.0.1`, keep "Download open orders on
   connection" checked.
3. Configure -> Settings -> Lock and Exit: set auto-restart so the session survives the daily
   reset (a weekly re-login with IB Key is still required by IBKR).
4. Verify: `python scripts/paper_trade.py --check` prints the `DU...` account and net liquidation.

## Daily operation

- `python scripts/paper_trade.py --dry-run` shows what the champion would do right now.
- `.\scripts\install_paper_task.ps1` registers the 15:45 ET weekday rebalance task.
- Live (real money) is not wired up on purpose. It requires a separate, human-only decision.
