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


#: A run whose tag contains this marker can never be promoted, whatever its numbers say.
#: The rules below are all *statistical*, and no statistic can see a bias built into the
#: universe: S-7's wide sleeve ranks the megacaps of 2026 back to 2012, which scores
#: CAR 43.9% / Sharpe 1.19 / DD 32.2% and passes every rule here. An in/out-of-sample
#: split does not catch it either, because the hindsight is spread evenly over both halves.
#: Whoever runs a knowingly-biased experiment tags it; the tag survives in the ledger and
#: stops a later session, which has no memory of why, from promoting it.
NOT_PROMOTABLE = "not promotable"


def spread_bps(run) -> str:
    """The slippage the run was charged, as the key `stats_by_spread` uses.

    S-17 found that LEAN's default brokerage model charges no spread at all, so every row
    written before it is a zero-spread row. `S1_SLIPPAGE_BPS` prices the omission, and this
    reads it back off the environment `backtest.py` records with the run.
    """
    raw = (run.get("env") or {}).get("S1_SLIPPAGE_BPS", "0")
    try:
        return f"{float(raw or 0):.1f}"
    except (TypeError, ValueError):
        return "0.0"


def champion_stats(run, champion):
    """The champion's own numbers at the cost model this run was charged.

    S-18: a candidate charged 2 bp of spread cannot be judged against a champion row that
    paid none - the comparison is biased by the difference in turnover, which between these
    two books is 400 orders. `champion.json` therefore records a column per spread and this
    picks the matching one. With no matching column the comparison falls back to the headline
    stats and says so, because an unlabelled comparison is the defect, not the fallback.
    """
    columns = champion.get("stats_by_spread") or {}
    key = spread_bps(run)
    if key in columns:
        return columns[key], None
    if columns:
        return champion.get("stats") or {}, (
            f"champion has no column at {key} bp of spread (have {sorted(columns)}), so this "
            f"run is not comparable - re-run the champion at {key} bp before judging it")
    return champion.get("stats") or {}, None


def verdict(run, champion):
    crit = champion.get("criteria", {})
    stats = run.get("stats", {})
    reasons = []
    if NOT_PROMOTABLE in (run.get("tag") or "").lower():
        reasons.append(f"tagged '{NOT_PROMOTABLE}' by the run that produced it")
    trades = num(stats.get("Total Orders"))
    if trades < crit.get("min_trades", 30):
        reasons.append(f"only {int(trades)} orders (< {crit.get('min_trades', 30)})")
    limit = num(crit.get("max_drawdown_limit", "35%"))
    if num(stats.get("Drawdown")) > limit:
        reasons.append(f"drawdown {stats.get('Drawdown')} above {crit.get('max_drawdown_limit')}")
    champ_stats, note = champion_stats(run, champion)
    if note:
        reasons.append(note)
    if champ_stats:
        for metric in crit.get("must_beat", ["Sharpe Ratio", "Compounding Annual Return"]):
            if not num(stats.get(metric)) > num(champ_stats.get(metric)):
                reasons.append(f"{metric} {stats.get(metric)} does not beat champion {champ_stats.get(metric)}")
        # Return-first rule (owner decision 2026-09-09, see research/BLOCKERS.md): a run may
        # give up a little Sharpe for more return, but only within a stated tolerance and
        # never with a worse drawdown than the champion. Absent keys mean no tolerance.
        tol = crit.get("sharpe_tolerance")
        if tol is not None and "Sharpe Ratio" not in crit.get("must_beat", []):
            floor = num(champ_stats.get("Sharpe Ratio")) - float(tol)
            if not num(stats.get("Sharpe Ratio")) >= floor:
                reasons.append(f"Sharpe {stats.get('Sharpe Ratio')} below champion {champ_stats.get('Sharpe Ratio')} minus tolerance {tol}")
        dd_tol = crit.get("drawdown_tolerance_points")
        if dd_tol is not None:
            ceiling = num(champ_stats.get("Drawdown")) + float(dd_tol)
            if num(stats.get("Drawdown")) > ceiling:
                reasons.append(f"drawdown {stats.get('Drawdown')} worse than champion {champ_stats.get('Drawdown')} plus {dd_tol} points")
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
