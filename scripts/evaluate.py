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

Promotion also rewrites `stats_by_spread` to the promoted run's own cost column and retires
the others (AUD-10 / S-34): they belong to the book that just lost, and leaving them in place
judged the next candidate against a retired champion. The `*_note` keys are kept. A champion
whose columns do not contain its own run is reported stale and every comparison is refused.
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


#: A key of `stats_by_spread` that names a cost column rather than a research note. The
#: dict carries both: a column keyed by the spread in bps ("0.0", "2.0") whose value is a
#: book, and a dated `*_note` (S-21..S-33) whose value is prose about the champion. Every
#: reader of a column goes through `cost_columns` or a note ends up quoted as a comparison
#: basis - and every writer leaves the notes alone, because git is the only thing that
#: should ever delete one.
COLUMN_KEY = re.compile(r"^\d+(\.\d+)?$")


def cost_columns(champion) -> dict:
    """The numeric spread columns of `stats_by_spread`, without the research notes."""
    columns = champion.get("stats_by_spread") or {}
    return {k: v for k, v in columns.items() if COLUMN_KEY.match(k) and isinstance(v, dict)}


def stale_note(champion):
    """AUD-10: refuse every comparison when the columns are not the champion's own book.

    `--promote` wrote `stats` and left `stats_by_spread` untouched, so the first candidate
    after a promotion was judged against the *previous* champion's numbers - and the previous
    champion is by construction the book that just lost. The defect never bit only because
    this file was hand-edited after each promotion, which is a habit and not a gate.

    The invariant that makes it detectable without trusting the writer: the champion's own run
    must appear in its own columns. It is deliberately not "every column must be the champion's
    run", because a column at another cost model is a legitimate re-run of the same book at
    another spread - S-18's 2 bp column is run `20260911T150558Z` against the champion's
    `20260911T145705Z`, same commit `d41aefe`, and that is correct.
    """
    run_dir = champion.get("run_dir")
    columns = cost_columns(champion)
    if not columns or not run_dir:
        return None
    if any(col.get("run_dir") == run_dir for col in columns.values()):
        return None
    return (f"champion.json is stale (AUD-10): none of its cost columns {sorted(columns)} was "
            f"produced by the champion's own run {run_dir}, so every comparison would be "
            f"against a retired book - re-promote through scripts/evaluate.py --promote")


def promoted_columns(run, champion) -> dict:
    """The `stats_by_spread` a promotion must leave behind.

    The promoted run becomes the only cost column, because the other columns describe the book
    that just lost. The `*_note` keys beside them are kept: they are the dated research record
    and each one names the run it was measured on. A later candidate charged a spread this
    champion has not been re-run at is then refused by `champion_stats` as not comparable,
    which is S-18's rule working as intended - the remedy is one re-run of the new champion at
    that spread, which is exactly what S-18 did by hand.
    """
    kept = {k: v for k, v in (champion.get("stats_by_spread") or {}).items()
            if not COLUMN_KEY.match(k)}
    kept[spread_bps(run)] = dict(run.get("stats") or {}, run_dir=run["run_dir"])
    return kept


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
    columns = cost_columns(champion)
    key = spread_bps(run)
    if key in columns:
        return columns[key], None
    if columns:
        return champion.get("stats") or {}, (
            f"champion has no column at {key} bp of spread (have {sorted(columns)}), so this "
            f"run is not comparable - re-run the champion at {key} bp before judging it")
    return champion.get("stats") or {}, None


def env_note(run, champion):
    """Refuse a comparison across software environments. The fourth axis-mismatch rule.

    `evaluate.py` already refuses three mismatched comparisons: a different cost model
    (S-18), a moved backtest window (F-3) and a financed-vs-unfinanced book (S-21). This is
    the same principle applied to the software that produced the numbers.

    This repository runs LEAN on Python 3.11 with pandas 2.2.3 and everything touching
    parquet on 3.14 with pandas 3.0.5, and both append to `experiments.jsonl`. pandas 3.0
    changed copy-on-write, string dtype and resample semantics, so two rows produced under
    different interpreters are not necessarily comparable.

    Deliberately silent when either side lacks an `env_key`: provenance stamping began on
    2026-09-12 and every earlier row - including the current champion - predates it. Refusing
    those would block every promotion over a fact nobody can now establish. It fires only
    when both sides state an environment and the two disagree, which is exactly when the
    comparison is knowably unsound.
    """
    run_env = run.get("env_key")
    champ_env = champion.get("env_key")
    if run_env and champ_env and run_env != champ_env:
        return (f"run was produced under {run_env} and the champion under {champ_env}; "
                f"different interpreter or numeric stack, so the two are not comparable - "
                f"re-run the champion under {run_env} before judging this candidate")
    return None


def window_note(run):
    """Refuse a run whose backtest window is not the champion's.

    F-3 recorded a two-month diagnostic run (a log-only check of LEAN's daily-bar date
    convention) whose annualized numbers were 47.3% CAR at a 1.2% drawdown on 71 orders -
    every criterion passed, and it is not a strategy at all. `S1_START` / `S1_END` are the
    only way that window can be moved and `backtest.py` records them, so a short run is
    detectable rather than merely discouraged. Same principle as the spread rule above: a
    comparison across different axes is refused, not judged against the wrong column.
    """
    env = run.get("env") or {}
    moved = {k: env[k] for k in ("S1_START", "S1_END") if k in env}
    if moved:
        return (f"run used {', '.join(f'{k}={v}' for k, v in sorted(moved.items()))}, so its "
                f"window is not the champion's - not comparable")
    # S-21, the third axis of the same rule. LEAN charges no financing at all
    # (DefaultBrokerageModel returns MarginInterestRateModel.Null), so `S1_FINANCING=on`
    # produces a run that has paid for its own leverage against a champion column that has
    # not. That candidate is *understated* rather than flattered, which is the direction
    # that quietly buries a good strategy rather than promoting a bad one - and it is still
    # a comparison across different axes. `champion.json` carries the financed figure as a
    # recorded note, not as a promotable column, so this is a refusal and not a lookup.
    if env.get("S1_FINANCING", "off").lower() == "on":
        return ("run charged margin financing (S1_FINANCING=on) and the champion's columns "
                "do not - not comparable; see S-21 in the journal")
    return None


def verdict(run, champion):
    crit = champion.get("criteria", {})
    stats = run.get("stats", {})
    reasons = []
    note = stale_note(champion)
    if note:
        reasons.append(note)
    note = window_note(run)
    if note:
        reasons.append(note)
    note = env_note(run, champion)
    if note:
        reasons.append(note)
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
    warning = stale_note(champion)
    if warning:
        print(f"WARNING: {warning}\n")
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
            columns = promoted_columns(run, champion)
            champion.update({
                "algorithm": run["algorithm"], "class": run["class"], "run_dir": run["run_dir"],
                "stats": run["stats"], "commit": run.get("commit"), "tag": run.get("tag"),
                "stats_by_spread": columns,
                "promoted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            })
            CHAMPION.write_text(json.dumps(champion, indent=2) + "\n", encoding="utf-8")
            print("promoted; champion.json updated")
            print(f"  cost columns now {sorted(cost_columns(champion))} at "
                  f"{spread_bps(run)} bp; every other column was retired with the old champion, "
                  f"so a candidate at another spread is refused until this book is re-run there")
        return 0 if ok else 1

    table(runs[-args.last:], champion)
    return 0


if __name__ == "__main__":
    sys.exit(main())
