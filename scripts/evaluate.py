#!/usr/bin/env python
"""Compare backtest runs against the champion and optionally promote one.

Usage:
    python scripts/evaluate.py                       # table of the last 20 runs vs champion
    python scripts/evaluate.py --algorithm s1_momo   # only runs of one algorithm
    python scripts/evaluate.py --promote <ts>        # promote the run with that timestamp
    python scripts/evaluate.py --candidate <ts>      # verdict for one run, exit 0 if it beats

Promotion rules (research/champion.json "criteria"):
  * at least `min_trades` orders
  * beats the champion on every metric in `must_beat` (higher is better)
  * drawdown not above `max_drawdown_limit`
A run that violates a rule is reported, never promoted.
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "research" / "experiments.jsonl"
CHAMPION = REPO / "research" / "champion.json"

SHOW = ["Total Orders", "Net Profit", "Compounding Annual Return", "Sharpe Ratio",
        "Drawdown", "Probabilistic Sharpe Ratio", "Total Fees"]


def num(value) -> float:
    """Parse LEAN stat strings such as '12.5%', '$3.44', '-0.005' into floats."""
    if value is None:
        return float("nan")
    s = str(value).strip().replace(",", "")
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else float("nan")


def load_runs():
    if not LEDGER.exists():
        return []
    runs = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            runs.append(json.loads(line))
    return runs


def load_champion():
    return json.loads(CHAMPION.read_text(encoding="utf-8")) if CHAMPION.exists() else {"stats": {}, "criteria": {}}


def verdict(run, champion):
    crit = champion.get("criteria", {})
    stats = run.get("stats", {})
    reasons = []
    trades = num(stats.get("Total Orders"))
    if trades < crit.get("min_trades", 30):
        reasons.append(f"only {int(trades)} orders (< {crit.get('min_trades', 30)})")
    limit = num(crit.get("max_drawdown_limit", "35%"))
    if num(stats.get("Drawdown")) > limit:
        reasons.append(f"drawdown {stats.get('Drawdown')} above {crit.get('max_drawdown_limit')}")
    champ_stats = champion.get("stats") or {}
    if champ_stats:
        for metric in crit.get("must_beat", ["Sharpe Ratio", "Compounding Annual Return"]):
            if not num(stats.get(metric)) > num(champ_stats.get(metric)):
                reasons.append(f"{metric} {stats.get(metric)} does not beat champion {champ_stats.get(metric)}")
    return (len(reasons) == 0), reasons


def table(runs, champion):
    header = ["ts", "algorithm", "tag"] + SHOW + ["beats?"]
    rows = []
    for r in runs:
        ok, _ = verdict(r, champion)
        rows.append([r["ts"], r["algorithm"], (r.get("tag") or "")[:28]] +
                    [str(r["stats"].get(k, "")) for k in SHOW] + ["yes" if ok else "no"])
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)] if rows else [len(h) for h in header]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*header))
    for row in rows:
        print(fmt.format(*row))
    champ = champion.get("algorithm")
    print(f"\nchampion: {champ or 'none'} " + (json.dumps({k: champion['stats'].get(k) for k in SHOW if k in champion.get('stats', {})}) if champ else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--algorithm")
    ap.add_argument("--last", type=int, default=20)
    ap.add_argument("--candidate", help="timestamp of a run to judge")
    ap.add_argument("--promote", help="timestamp of a run to promote to champion (must pass the rules)")
    args = ap.parse_args()

    runs = load_runs()
    champion = load_champion()
    if args.algorithm:
        runs = [r for r in runs if r["algorithm"] == args.algorithm]

    target_ts = args.promote or args.candidate
    if target_ts:
        matches = [r for r in runs if r["ts"] == target_ts]
        if not matches:
            sys.exit(f"no run with ts {target_ts} in {LEDGER}")
        run = matches[-1]
        ok, reasons = verdict(run, champion)
        print(f"{run['algorithm']}::{run['class']} @ {run['ts']}: {'BEATS champion' if ok else 'does NOT beat champion'}")
        for reason in reasons:
            print(f"  - {reason}")
        if args.promote:
            if not ok:
                print("promotion refused")
                return 1
            champion.update({
                "algorithm": run["algorithm"], "class": run["class"], "run_dir": run["run_dir"],
                "stats": run["stats"], "commit": run.get("commit"), "tag": run.get("tag"),
                "promoted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            })
            CHAMPION.write_text(json.dumps(champion, indent=2) + "\n", encoding="utf-8")
            print(f"promoted; champion.json updated")
        return 0 if ok else 1

    table(runs[-args.last:], champion)
    return 0


if __name__ == "__main__":
    sys.exit(main())
