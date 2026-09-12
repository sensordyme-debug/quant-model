#!/usr/bin/env python
"""Controlled reconciliation of the daily runner's live state file.

    python scripts/reconcile_state.py                 # inspect + plan, writes nothing
    python scripts/reconcile_state.py --apply         # back up, then write the reconciled file

WHY NOT JUST DELETE IT
----------------------
`live/state/last_run.json` was written by simulated runs (AUD-04): its `equity`,
`equity_high` and `equity_curve` are `paper_trade.MockAccount.net_liq = 100_000`, not the
IBKR account, and `held_age` counted RUNS rather than sessions and reached 15. New writes can
no longer contaminate it - `save_state` is scope-routed - but the file on disk is still wrong.

Deleting it looks like the clean fix and is not. The file carries two kinds of field:

  FABRICATED   equity, equity_high, equity_curve   - MockAccount's number, must be replaced
               dry_run                             - the marker that it was simulated
  REAL         signal, as_of, targets              - produced by the actual signal module
               signal_state.held / held_age        - the strategy's own carry state

Deleting throws away the second group. `held_age` in particular feeds the champion's holding
logic, and resetting it silently changes what the next rebalance decides - a strategy change
disguised as a cleanup. So: replace what is fabricated, preserve what is real, and take the
equity from the account rather than from anywhere in the old file.

WHAT IT DOES
------------
1. back up every file in live/state/ to live/state/backup/<utc timestamp>/
2. classify each field of last_run.json as fabricated or real
3. read the ACTUAL account: NetLiquidation and positions, read-only, clientId 18
4. build the reconciled document
5. validate it (equity positive and account-sourced, no dry_run marker, real fields intact)
6. write it only with --apply, stamped as PAPER scope

It never places an order, never cancels one, and opens the IB connection read-only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

LIVE = REPO / "live"
STATE_DIR = LIVE / "state"
LAST_RUN = STATE_DIR / "last_run.json"
BACKUP_ROOT = STATE_DIR / "backup"

#: Fields whose value came from the simulation and must not survive reconciliation.
FABRICATED = ("equity", "equity_high", "equity_curve", "dry_run")
#: Fields produced by the real signal module, which must survive it.
PRESERVE = ("signal", "as_of", "targets", "signal_state")

#: Distinct from the paper runner (17), minute backfill (31), futures probe (41), intraday
#: store (61), live trader (71) and dashboard (81). Read-only, and released immediately.
CLIENT_ID = 18


def backup(dest_root: Path = BACKUP_ROOT) -> Path:
    """Copy the whole state directory before touching anything. Returns the backup path."""
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_root / stamp
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(STATE_DIR.glob("*.json")):
        shutil.copy2(f, dest / f.name)
    for f in sorted(STATE_DIR.glob("*.jsonl")):
        shutil.copy2(f, dest / f.name)
    return dest


def classify(state: dict) -> tuple[dict, dict]:
    """Split a state document into (fabricated, preserved)."""
    fab = {k: state[k] for k in FABRICATED if k in state}
    keep = {k: state[k] for k in PRESERVE if k in state}
    return fab, keep


def read_account(host: str, port: int, client_id: int) -> dict:
    """NetLiquidation and positions from IB Gateway. Read-only; never raises.

    Returns {} when the Gateway is unreachable, so the caller can report "cannot determine
    the account" rather than reconciling against a guess. Part 18: an unknown state is not a
    licence to invent one.
    """
    try:
        from ib_async import IB
    except ImportError:
        return {"error": "ib_async not importable"}
    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=20, readonly=True)
        account = ib.managedAccounts()[0]
        summary = {r.tag: r.value for r in ib.accountSummary(account)
                   if r.currency in ("USD", "BASE", "")}
        positions = {p.contract.symbol: int(p.position)
                     for p in ib.positions(account) if p.position}
        return {
            "account": account,
            "net_liquidation": float(summary.get("NetLiquidation", 0) or 0),
            "positions": positions,
            "is_paper": account.startswith("DU"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}
    finally:
        try:
            ib.disconnect()
        except Exception:  # noqa: BLE001
            pass


def reconcile(state: dict, account: dict) -> tuple[dict, list[str]]:
    """Build the reconciled document and the list of reasons it is or is not valid."""
    problems: list[str] = []
    _fab, keep = classify(state)
    nav = float(account.get("net_liquidation") or 0.0)

    if account.get("error"):
        problems.append(f"cannot read the account: {account['error']}")
    if not account.get("is_paper", False) and not account.get("error"):
        problems.append(f"account {account.get('account')} is not a DU paper account")
    if nav <= 0:
        problems.append(f"account NetLiquidation is {nav}, refusing to write it as equity")

    out = dict(keep)
    # `signal_state.peak` is equity-derived and therefore fabricated too, even though the
    # rest of signal_state is real strategy carry. Reseeding it matters more than the
    # top-level fields: it is the strategy's OWN drawdown reference, so leaving it at
    # MockAccount's 100,000 against a 988,031 account means the drawdown overlay is
    # measuring against a baseline ten times too low for as long as the file survives.
    sig = dict(out.get("signal_state") or {})
    if "peak" in sig:
        out["_peak_reconciled_from"] = sig["peak"]
        sig["peak"] = nav
        out["signal_state"] = sig
    # `held_age` is also wrong - AUD-04 notes it counted RUNS rather than sessions and reached
    # 15 after seven runs on one signal date. It is deliberately NOT corrected here: the true
    # value is unknowable from this file (XLE/XLK read 15 while IWM reads 6), and held_age
    # feeds the champion's holding decisions, so changing it is a strategy change disguised
    # as a cleanup. Reported instead, for the daily track to decide.
    out["equity"] = nav
    out["equity_high"] = nav
    # A single-point curve, not the fabricated four. The drawdown breaker measures against
    # equity_high; seeding it with one true observation says "no history yet", which is
    # accurate. Carrying forward four fake points would say "flat for four sessions".
    out["equity_curve"] = [nav]
    out["reconciled_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    out["reconciled_from"] = {
        "equity": state.get("equity"), "equity_high": state.get("equity_high"),
        "equity_curve": state.get("equity_curve"), "dry_run": state.get("dry_run"),
    }
    return out, problems


def validate(out: dict, account: dict, before: dict) -> list[str]:
    """Post-conditions. Anything here failing means do not write."""
    bad: list[str] = []
    if out.get("dry_run"):
        bad.append("dry_run marker survived")
    nav = float(account.get("net_liquidation") or 0.0)
    if out.get("equity") != nav or out.get("equity_high") != nav:
        bad.append("equity is not the account's NetLiquidation")
    if out.get("equity_curve") != [nav]:
        bad.append("equity_curve was not reseeded from the account")
    nav_ = nav
    for k in PRESERVE:
        if k not in before:
            continue
        if k == "signal_state":
            was, now = dict(before[k]), dict(out.get(k) or {})
            if "peak" in was and now.get("peak") != nav_:
                bad.append("signal_state.peak was not reseeded from the account")
            if {x: v for x, v in was.items() if x != "peak"} !=                {x: v for x, v in now.items() if x != "peak"}:
                bad.append("signal_state carry fields other than peak were altered")
            continue
        if out.get(k) != before[k]:
            bad.append(f"real field {k!r} was altered")
    try:
        from quant_brain.core.state import is_contaminated
        if is_contaminated(out):
            bad.append("the reconciled document still reads as contaminated")
    except Exception as exc:  # noqa: BLE001
        bad.append(f"could not run the contamination check: {exc}")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the reconciled file")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=CLIENT_ID)
    args = ap.parse_args(argv)

    if not LAST_RUN.exists():
        print(f"{LAST_RUN} does not exist; nothing to reconcile.")
        return 0
    before = json.loads(LAST_RUN.read_text(encoding="utf-8"))

    print("=== 1. current state ===")
    fab, keep = classify(before)
    print("  FABRICATED (from MockAccount, to be replaced):")
    for k, v in fab.items():
        print(f"    {k:<14} {json.dumps(v)[:80]}")
    print("  REAL (produced by the signal, to be preserved):")
    for k, v in keep.items():
        print(f"    {k:<14} {json.dumps(v)[:80]}")

    print("\n=== 2. actual account (read-only) ===")
    account = read_account(args.host, args.port, args.client_id)
    if account.get("error"):
        print(f"  {account['error']}")
    else:
        print(f"  account          {account['account']} (paper={account['is_paper']})")
        print(f"  NetLiquidation   {account['net_liquidation']:,.2f}")
        print(f"  positions        {account['positions'] or 'none'}")

    print("\n=== 3. reconciliation plan ===")
    out, problems = reconcile(before, account)
    for k in ("equity", "equity_high", "equity_curve"):
        print(f"  {k:<14} {json.dumps(before.get(k))[:44]}  ->  {json.dumps(out.get(k))[:44]}")
    print(f"  {'dry_run':<14} {json.dumps(before.get('dry_run'))}  ->  removed")
    print(f"  {'signal_state.peak':<14} {json.dumps(before.get('signal_state', {}).get('peak'))}"
          f"  ->  {json.dumps(out.get('signal_state', {}).get('peak'))}")
    print(f"  preserved      {', '.join(sorted(keep)) or 'nothing'} (signal_state carry kept, peak reseeded)")
    ages = (before.get("signal_state") or {}).get("held_age") or {}
    if ages:
        print(f"  NOT CORRECTED  held_age {ages} - counts runs, not sessions (AUD-04). The true")
        print("                 value is unknowable from this file and it drives holding")
        print("                 decisions, so changing it is the daily track's call.")

    if problems:
        print("\n  REFUSED:")
        for p in problems:
            print(f"    - {p}")
        return 3

    bad = validate(out, account, before)
    if bad:
        print("\n  VALIDATION FAILED:")
        for b in bad:
            print(f"    - {b}")
        return 3
    print("\n  validation: all post-conditions hold")

    if not args.apply:
        print("\n(dry run - pass --apply to back up and write)")
        return 0

    dest = backup()
    print(f"\n=== 4. backed up to {dest} ===")
    from quant_brain.core.state import StateScope, StateStore
    store = StateStore.open(StateScope.PAPER, base=STATE_DIR)
    written = store.write_json("last_run.json", out)
    print(f"=== 5. wrote {written} (scope=paper) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
