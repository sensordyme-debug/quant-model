"""I-2: one-page end-of-session assertion pass over the two live logs.

Why this exists
---------------
`live/alerts.json` is missing (BLOCKERS.md item 2), so the JSONL log files are the only
alert surface this repository has. Two live defects in the 2026-09-09..2026-09-11 window
were caught only by reading them by hand, days after the fact:

  * the S-18 TQQQ orphan - the daily runner treated a name the champion had stopped
    targeting as "foreign" and left 3,227 shares in the account after the rebalance
    (`foreign_positions_ignored` on 2026-09-11 at 15:45 ET, fixed in `c34ff7b`);
  * the intraday book's closed P&L, costs and trade count not resetting on session
    rollover, which would have tripped the -2.5% loss limit about $6.8k early
    (fixed in `c16cca4`).

Both have a signature that is visible in the log on the day. This script asserts the
signatures, plus the invariants the two runners are supposed to hold, and prints one
page with a single verdict. It reads only `live/log/*.jsonl` - it never connects to
IBKR, never places an order and never writes to `live/` except the optional
`live/log/audit-<date>.json` artifact under `--json`.

Usage
-----
    py -3.11 scripts/session_audit.py                  # the latest date with a log
    py -3.11 scripts/session_audit.py --date 2026-09-11
    py -3.11 scripts/session_audit.py --all            # every date on disk, one line each
    py -3.11 scripts/session_audit.py --json           # also write live/log/audit-<date>.json

Exit code: 0 PASS, 1 WARN, 2 FAIL - so the scheduler or a wrapper can act on it.

Reading the verdict
-------------------
FAIL is an invariant the runner is supposed to hold and did not (an order that never
filled, a book not flat at 15:38 ET, an exposure past the margin budget, a P&L that
carried over). WARN is a condition that is either expected on this machine or a
deliberate operator action (IBKR's delayed feed, a mid-session relaunch, a
`moo_window` refusal from a manual test, a `notify_failed` from the missing alerts
credential). INFO is context.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
LOG_DIR = REPO / "live" / "log"
sys.path.insert(0, str(REPO / "scripts"))

from intraday_common import (FLATTEN_MINUTE, EXIT_MINUTE, GROSS_HARD_CAP, MIN_CHANGE,  # noqa: E402
                             UNIVERSE as INTRADAY_UNIVERSE)

#: `scripts/paper_trade.py`'s MockAccount net liquidation. A `plan` carrying exactly this
#: figure is a pipeline test (`--mock`), not a session, and is excluded from every
#: assertion below. Kept as a constant because it is the only way the log distinguishes
#: the two: paper_trade.py logs no `start` event the way the intraday trader does.
MOCK_NET_LIQ = 100_000.0

#: The daily runner's one shipped ceiling (`algorithms/s1_momo/signals.py`): 0.75 of Reg-T
#: margin. `effective_exposure` is DERIVED from it and is not itself a limit - it was
#: 1.7363x on 2026-09-10 under the S-12 champion, because a 3x proxy carries three units
#: of economic exposure per unit of notional at 0.333 of the margin (S-18's whole point).
#: So the assertion is on the budget, and exposure gets a loose runaway bound only.
MARGIN_BUDGET = 0.75
EXPOSURE_ALARM = 2.30       # just past the retired S-12 book's own 2.25x economic ceiling
TOL = 1e-6

#: ET window the scheduled 15:45 rebalance submits in. A live plan that wants orders and
#: logs none is a `--dry-run` outside it and a lost session inside it.
REBALANCE_ET = (dt.time(15, 40), dt.time(15, 50))

#: First session the daily runner filled real paper orders (15:46 ET). Logs before it are
#: pipeline tests against a mock account, so "no live plan" is the expected state and not a
#: lost session. The intraday sleeve's own first live session was 2026-09-10.
DAILY_DEPLOY_DATE = "2026-09-09"
INTRADAY_DEPLOY_DATE = "2026-09-10"

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"
RANK = {INFO: 0, PASS: 0, WARN: 1, FAIL: 2}


# ----------------------------------------------------------------------------- helpers
def read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"event": "_unparseable", "line_no": i, "raw": line[:200]})
    return out


def in_rebalance_window(ts: str) -> bool:
    """Is this UTC `ts` inside the scheduled 15:45 ET submission window?"""
    try:
        et = dt.datetime.fromisoformat(ts).astimezone(ZoneInfo("America/New_York"))
    except (ValueError, TypeError):
        return False
    lo, hi = REBALANCE_ET
    return lo <= et.time() <= hi


def minute_of(t: str) -> int | None:
    """Minute index from the trader's own `t` string ("2026-09-11 15:32:00-04:00")."""
    try:
        clock = t.split(" ")[1]
        h, m = int(clock[0:2]), int(clock[3:5])
        return (h - 9) * 60 + m - 30
    except (IndexError, ValueError):
        return None


class Checks:
    """An ordered list of (status, name, detail) with a rolled-up verdict."""

    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.rows.append((status, name, detail))

    def verdict(self) -> str:
        worst = max((RANK[s] for s, _, _ in self.rows), default=0)
        return {0: PASS, 1: WARN, 2: FAIL}[worst]

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for r, _, _ in self.rows if r == s) for s in (FAIL, WARN, PASS, INFO)}


# ----------------------------------------------------------------------------- daily sleeve
def split_runs(recs: list[dict]) -> list[dict]:
    """Segment the daily log into runs. A `plan` event starts one; anything logged before
    the first plan (a clock refusal, a failed connection) is its own run with plan=None."""
    runs: list[dict] = []
    cur = {"plan": None, "recs": []}
    for r in recs:
        if r.get("event") == "plan":
            if cur["plan"] is not None or cur["recs"]:
                runs.append(cur)
            cur = {"plan": r, "recs": []}
        else:
            cur["recs"].append(r)
    if cur["plan"] is not None or cur["recs"]:
        runs.append(cur)
    for run in runs:
        plan = run["plan"]
        run["mock"] = bool(plan) and float(plan.get("net_liq", 0.0)) == MOCK_NET_LIQ
        run["live"] = bool(plan) and not run["mock"]
    return runs


def audit_daily(date: str, ck: Checks) -> dict:
    path = LOG_DIR / f"{date}.jsonl"
    recs = read_log(path)
    if not recs:
        ck.add(FAIL, "daily.log_present", f"{path.name} missing or empty")
        return {"log": path.name, "runs": 0}

    runs = split_runs(recs)
    live_runs = [r for r in runs if r["live"]]
    mock_runs = [r for r in runs if r["mock"]]
    ck.add(INFO, "daily.runs", f"{len(runs)} run(s): {len(live_runs)} live, {len(mock_runs)} mock "
                               f"(net_liq == {MOCK_NET_LIQ:,.0f})")

    if not live_runs:
        conn = [r for r in recs if r.get("event") == "connect_failed"]
        if date < DAILY_DEPLOY_DATE:
            ck.add(INFO, "daily.ran", f"no live plan, and {date} predates the first real fills on "
                                      f"{DAILY_DEPLOY_DATE} - mock pipeline tests only, nothing to audit")
        elif conn:
            ck.add(FAIL, "daily.ran", f"no live plan and {len(conn)} connect_failed - the session was lost")
        else:
            ck.add(WARN, "daily.ran", "no live plan in the log (weekend, holiday, or the task did not fire)")
        return {"log": path.name, "runs": len(runs), "live_runs": 0}

    ck.add(PASS, "daily.ran", f"{len(live_runs)} live plan(s), last at {live_runs[-1]['plan']['ts']}")

    # -- hard refusals and connection failures -------------------------------------------
    hard = {"not_paper_account", "no_champion", "no_approval_file"}
    bad = [r for r in recs if r.get("event") == "refused" and r.get("reason") in hard]
    ck.add(FAIL if bad else PASS, "daily.no_hard_refusal",
           "; ".join(f"{r['reason']}" for r in bad) or "no not_paper_account / no_champion / no_approval_file")
    # A connect_failed only costs a session if no live plan followed it. On 2026-09-09 and
    # 2026-09-10 the log carries six each from manual attempts while IB Gateway was down,
    # and the scheduled rebalance still went through - that is a WARN, not a lost session.
    conn = [r for r in recs if r.get("event") == "connect_failed"]
    if conn:
        ck.add(WARN, "daily.connected", f"{len(conn)} connect_failed, but {len(live_runs)} live plan(s) "
                                        f"followed - IB Gateway was down for a manual attempt, not for the session")
    else:
        ck.add(PASS, "daily.connected", "no connect_failed")
    moo = [r for r in recs if r.get("event") == "refused" and r.get("reason") == "moo_window"]
    if moo:
        ck.add(WARN, "daily.moo_window", f"{len(moo)} MOO clock refusal(s) - a manual out-of-window run, "
                                         "harmless; the scheduled task submits inside the window")

    # -- the TQQQ-orphan signature -------------------------------------------------------
    # Post-c34ff7b `foreign` is exactly the intraday sleeve's universe, and that sleeve is
    # flat by 15:38 ET. So at the 15:45 rebalance this event can only mean the intraday book
    # did not flatten - or that the fix regressed and a daily name is being skipped again.
    foreign = [r for r in recs if r.get("event") == "foreign_positions_ignored"]
    if foreign:
        syms = sorted({s for r in foreign for s in (r.get("positions") or {})})
        off = [s for s in syms if s not in INTRADAY_UNIVERSE]
        detail = f"positions {syms} left alone"
        if off:
            detail += f" - {off} are NOT intraday-sleeve names (the S-18 orphan signature)"
        else:
            detail += " - all intraday-sleeve names, so that sleeve was not flat at the rebalance"
        ck.add(FAIL, "daily.no_foreign_positions", detail)
    else:
        ck.add(PASS, "daily.no_foreign_positions", "no position skipped at the rebalance")

    flat = [r for r in recs if r.get("event") == "flatten"]
    if flat:
        ck.add(FAIL, "daily.no_flatten", f"{len(flat)} flatten event(s), reason(s) "
                                         f"{[r.get('reason') for r in flat]}")

    # -- plan reconciliation and fills ---------------------------------------------------
    placed = filled_ok = 0
    problems: list[str] = []
    dry: list[str] = []
    for run in live_runs:
        plan = run["plan"]
        want = {o["symbol"]: int(o["delta"]) for o in plan.get("orders", []) if int(o.get("delta", 0)) != 0}
        orders = [r for r in run["recs"] if r.get("event") == "order"]
        fills = [r for r in run["recs"] if r.get("event") == "fill"]
        got = {o["symbol"]: (int(o["qty"]) if o.get("action") == "BUY" else -int(o["qty"])) for o in orders}
        if not orders:
            if want and in_rebalance_window(plan["ts"]):
                problems.append(f"{plan['ts']}: the 15:45 ET plan wanted {want} and logged no order - "
                                f"the scheduled session lost its orders")
            elif want:
                dry.append(f"{plan['ts']}: plan wanted {want}, no order logged (a --dry-run "
                           f"outside the {REBALANCE_ET[0]:%H:%M}-{REBALANCE_ET[1]:%H:%M} ET window)")
            continue
        placed += len(orders)
        if got != want:
            problems.append(f"{plan['ts']}: orders {got} != plan {want}")
        by_sym: dict[str, dict] = {}
        for f_ in fills:
            by_sym[f_["symbol"]] = f_
        for o in orders:
            f_ = by_sym.get(o["symbol"])
            if f_ is None:
                problems.append(f"{plan['ts']}: {o['symbol']} {o['action']} {o['qty']} has no fill")
            elif f_.get("status") != "Filled" or abs(float(f_.get("filled", 0)) - abs(int(o["qty"]))) > TOL \
                    or float(f_.get("remaining", 0) or 0) != 0.0:
                problems.append(f"{plan['ts']}: {o['symbol']} {f_.get('status')} "
                                f"filled {f_.get('filled')}/{abs(int(o['qty']))} "
                                f"remaining {f_.get('remaining')}")
            else:
                filled_ok += 1
    ck.add(FAIL if problems else PASS, "daily.fills_reconcile",
           "; ".join(problems) if problems else f"{filled_ok}/{placed} order(s) fully filled and matching the plan")
    if dry:
        ck.add(WARN, "daily.dry_runs", "; ".join(dry))

    # -- sizing ceiling ------------------------------------------------------------------
    breach, alarm = [], []
    for run in live_runs:
        d = (run["plan"].get("diagnostics") or {})
        mu, ee = float(d.get("margin_used", 0.0)), float(d.get("effective_exposure", 0.0))
        if mu > MARGIN_BUDGET + TOL:
            breach.append(f"{run['plan']['ts']}: margin_used {mu:.3f} > {MARGIN_BUDGET}")
        if ee > EXPOSURE_ALARM:
            alarm.append(f"{run['plan']['ts']}: effective_exposure {ee:.3f}x")
    last = (live_runs[-1]["plan"].get("diagnostics") or {})
    ck.add(FAIL if breach else PASS, "daily.margin_budget",
           "; ".join(breach) if breach else
           f"margin_used {float(last.get('margin_used', 0)):.2f} <= {MARGIN_BUDGET} on every live plan")
    ck.add(FAIL if alarm else INFO, "daily.exposure",
           "; ".join(alarm) if alarm else
           f"gross_weight {float(last.get('gross_weight', 0)):.4f}x notional, "
           f"effective_exposure {float(last.get('effective_exposure', 0)):.4f}x economic "
           f"(derived from the budget, not a limit; alarm at {EXPOSURE_ALARM}x), "
           f"vol_scale {last.get('vol_scale', '?')}, regime {last.get('regime_reason', '?')}")

    nf = [r for r in recs if r.get("event") == "notify_failed"]
    if nf:
        ck.add(WARN, "daily.notify", f"{len(nf)} notify_failed - expected while live/alerts.json "
                                     "is missing (BLOCKERS.md item 2); the log is the alert surface")

    bad_lines = [r for r in recs if r.get("event") == "_unparseable"]
    if bad_lines:
        ck.add(FAIL, "daily.log_parses", f"{len(bad_lines)} unparseable line(s), first at {bad_lines[0]['line_no']}")

    return {
        "log": path.name, "runs": len(runs), "live_runs": len(live_runs),
        "orders": placed, "filled": filled_ok,
        "net_liq": float(live_runs[-1]["plan"].get("net_liq", 0.0)),
        "targets": live_runs[-1]["plan"].get("targets", {}),
    }


# ----------------------------------------------------------------------------- intraday sleeve
def audit_intraday(date: str, ck: Checks) -> dict:
    path = LOG_DIR / f"intraday-{date}.jsonl"
    recs = read_log(path)
    pre = date < INTRADAY_DEPLOY_DATE
    if not recs:
        ck.add(INFO if pre else WARN, "intraday.log_present",
               f"{path.name} missing or empty"
               + (f" - {date} predates the sleeve's first live session on {INTRADAY_DEPLOY_DATE}"
                  if pre else " (weekend, holiday, or the 09:25 task did not fire)"))
        return {"log": path.name, "started": 0}

    starts = [r for r in recs if r.get("event") == "start"]
    live_starts = [r for r in starts if not r.get("dry_run")]
    if not live_starts:
        ck.add(INFO if pre else WARN, "intraday.ran",
               f"{len(starts)} start(s), none live (dry run only)"
               + (f" - {date} predates {INTRADAY_DEPLOY_DATE}" if pre else ""))
        return {"log": path.name, "started": 0}
    ck.add(PASS, "intraday.ran", f"live start at {live_starts[0]['ts']}, strategy "
                                 f"{live_starts[-1].get('strategy')}, equity_frac "
                                 f"{live_starts[-1].get('equity_frac')}, nav {live_starts[-1].get('nav'):,.0f}")
    if len(live_starts) > 1:
        ck.add(WARN, "intraday.single_start",
               f"{len(live_starts)} live starts - a mid-session relaunch; equity_frac went "
               f"{[s.get('equity_frac') for s in live_starts]}")

    # -- flat by 15:38 ET ----------------------------------------------------------------
    end = [r for r in recs if r.get("event") == "end"]
    if not end:
        ck.add(FAIL, "intraday.end", "no end event - the loop did not exit cleanly")
    else:
        pos = end[-1].get("positions") or {}
        ck.add(FAIL if pos else PASS, "intraday.flat_at_end",
               f"end positions {pos}" if pos else
               f"flat at exit, P&L {float(end[-1].get('pnl', 0)):+,.2f} on "
               f"{end[-1].get('trades')} trades, costs {float(end[-1].get('costs', 0)):,.2f}")

    snaps = [r for r in recs if r.get("event") == "snapshot"]
    late = [(minute_of(str(s.get("t", ""))), s) for s in snaps]
    hot = [(m, s) for m, s in late if m is not None and m >= FLATTEN_MINUTE
           and (float(s.get("gross", 0) or 0) != 0.0 or (s.get("positions") or {}))]
    if hot:
        worst = max(m for m, _ in hot)
        status = FAIL if worst >= EXIT_MINUTE else WARN
        ck.add(status, "intraday.flat_by_1538",
               f"{len(hot)} snapshot(s) at or past minute {FLATTEN_MINUTE} (15:38 ET) still carrying "
               f"gross; latest minute {worst}")
    else:
        ck.add(PASS, "intraday.flat_by_1538",
               f"no gross in any snapshot at or past minute {FLATTEN_MINUTE} (15:38 ET)")
    late_orders = [r for r in recs if r.get("event") == "order"
                   and (minute_of(str(r.get("t", ""))) or -1) > EXIT_MINUTE]
    if late_orders:
        ck.add(FAIL, "intraday.no_late_orders", f"{len(late_orders)} order(s) after minute {EXIT_MINUTE} (15:42 ET)")

    # -- the rollover signature ----------------------------------------------------------
    # One `fill` event is one book trade. If yesterday's closed P&L, costs and trade count
    # leak into today's book (the c16cca4 defect) the snapshot's trade count runs ahead of
    # the fills logged today, and the loss limit is measured against a P&L that is not the
    # day's. This is the check that would have caught it on the day.
    fill_ts = sorted(r["ts"] for r in recs if r.get("event") == "fill")
    leak = []
    for s in snaps:
        seen = sum(1 for t in fill_ts if t <= s["ts"])
        if int(s.get("trades", 0)) > seen:
            leak.append(f"{s.get('t')}: trades {s.get('trades')} > {seen} fill(s) logged by then")
    ck.add(FAIL if leak else PASS, "intraday.pnl_reset",
           "; ".join(leak[:3]) if leak else
           f"trade count never runs ahead of the day's fills ({len(fill_ts)} fills, "
           f"{max([int(s.get('trades', 0)) for s in snaps], default=0)} trades at the last snapshot)")
    roll = [r for r in recs if r.get("event") == "book_rollover"]
    if roll:
        ck.add(INFO, "intraday.book_rollover",
               f"{len(roll)} rollover(s) from {[r.get('from_date') for r in roll]}, dropped "
               f"{[r.get('dropped_trades') for r in roll]} stale trade(s) - the c16cca4 fix working")
    stale = [r for r in recs if r.get("event") in ("stale_book", "ignored_book_file")]
    if stale:
        ck.add(WARN, "intraday.book_state", f"{[r.get('event') for r in stale]}")

    # -- risk gates ----------------------------------------------------------------------
    stops = [r for r in recs if r.get("event") in ("loss_limit", "halt")]
    if stops:
        ck.add(FAIL, "intraday.no_risk_stop",
               "; ".join(f"{r['event']} " + (f"P&L {float(r.get('pnl', 0)):+,.0f} on NAV "
                                             f"{float(r.get('nav_open', 0)):,.0f}"
                                             if r["event"] == "loss_limit" else str(r.get("files"))) for r in stops))
    else:
        ck.add(PASS, "intraday.no_risk_stop", "no loss-limit or HALT stop")

    # `GROSS_HARD_CAP` is applied in `targets_to_orders` to the TARGET weights at decision
    # time; the snapshot's `gross` is the book marked to market a minute or more later, and
    # `MIN_CHANGE` (2% of sleeve equity) deliberately leaves a name alone until it drifts
    # that far. So a mark-to-market gross slightly past the cap is the band working, not the
    # cap failing - 2026-09-10 peaked 3.4% over on 14 names. The assertion is therefore
    # two-tier: report any overshoot, fail only past a level the band cannot explain.
    decisions = [r for r in recs if r.get("event") == "decision"]
    eq = max([float(r.get("equity", 0) or 0) for r in decisions]
             or [float(live_starts[-1].get("nav", 0.0)) * float(live_starts[-1].get("equity_frac", 0.0))])
    peak_snap = max(snaps, key=lambda s: float(s.get("gross", 0) or 0), default=None)
    peak = float(peak_snap.get("gross", 0) or 0) if peak_snap else 0.0
    cap = GROSS_HARD_CAP * eq
    n_at_peak = len(peak_snap.get("positions") or {}) if peak_snap else 0
    band = cap * (1.0 + n_at_peak * MIN_CHANGE)      # what the no-trade band can account for
    ratio = peak / cap if cap else 0.0
    detail = (f"peak snapshot gross ${peak:,.0f} = {ratio:.3f}x the ${cap:,.0f} cap "
              f"({GROSS_HARD_CAP}x sleeve equity ${eq:,.0f}) on {n_at_peak} name(s)")
    if peak > band:
        ck.add(FAIL, "intraday.gross_cap", detail + f" - past the ${band:,.0f} the {MIN_CHANGE:.0%} "
                                                    f"MIN_CHANGE band can account for")
    elif peak > cap:
        ck.add(WARN, "intraday.gross_cap", detail + " - decision-time targets are capped, this is the "
                                                    "book marked to market inside the MIN_CHANGE band")
    else:
        ck.add(PASS, "intraday.gross_cap", detail)

    # -- order/fill reconciliation -------------------------------------------------------
    order_ids = {r.get("id") for r in recs if r.get("event") == "order"}
    fill_ids = {r.get("id") for r in recs if r.get("event") == "fill"}
    dead_ids = {r.get("id") for r in recs if r.get("event") == "order_dead"}
    orphan = sorted(i for i in order_ids - fill_ids - dead_ids if i is not None)
    ck.add(FAIL if orphan else PASS, "intraday.fills_reconcile",
           f"{len(orphan)} order id(s) with no fill and no order_dead: {orphan[:8]}" if orphan else
           f"{len(order_ids)} order(s), {len(fill_ids & order_ids)} filled, {len(dead_ids)} dead")
    partial = [r for r in recs if r.get("event") == "fill" and r.get("status") == "partial"]
    if partial:
        ck.add(WARN, "intraday.partials", f"{len(partial)} partial fill(s)")

    # -- errors and feed -----------------------------------------------------------------
    errs = [r for r in recs if r.get("event") in ("decide_error", "step_error")]
    ck.add(FAIL if errs else PASS, "intraday.no_errors",
           "; ".join(f"{r['event']}: {str(r.get('error'))[:120]}" for r in errs[:3]) if errs
           else "no decide_error or step_error")
    soft = [r for r in recs if r.get("event") in ("feed_error", "disconnected", "order_dead")]
    if soft:
        ck.add(WARN, "intraday.feed", f"{[r.get('event') for r in soft][:6]}")
    delays = [float(r.get("ib_delay_minutes", 0) or 0) for r in recs if r.get("event") == "feed_probe"]
    if delays:
        ck.add(WARN if max(delays) > 2 else PASS, "intraday.feed_delay",
               f"ib_delay_minutes {min(delays):.0f}..{max(delays):.0f} - IBKR serves this account "
               "delayed quotes; the trader runs off minute history, so this is expected, not new")
    nf = [r for r in recs if r.get("event") == "notify_failed"]
    if nf:
        ck.add(WARN, "intraday.notify", f"{len(nf)} notify_failed (BLOCKERS.md item 2)")
    bad_lines = [r for r in recs if r.get("event") == "_unparseable"]
    if bad_lines:
        ck.add(FAIL, "intraday.log_parses", f"{len(bad_lines)} unparseable line(s)")

    return {
        "log": path.name, "started": len(live_starts),
        "strategy": live_starts[-1].get("strategy"),
        "equity_frac": live_starts[-1].get("equity_frac"),
        "nav": float(live_starts[-1].get("nav", 0.0)),
        "decisions": len(decisions), "orders": len(order_ids), "fills": len(fill_ids),
        "pnl": float(end[-1].get("pnl", 0.0)) if end else None,
        "costs": float(end[-1].get("costs", 0.0)) if end else None,
        "trades": end[-1].get("trades") if end else None,
    }


# ----------------------------------------------------------------------------- driver
def dates_on_disk() -> list[str]:
    out = set()
    for p in LOG_DIR.glob("*.jsonl"):
        stem = p.stem
        if stem.startswith("intraday-replay-") or stem.startswith("alerts-") or stem.startswith("selftest-"):
            continue
        tail = stem.split("-", 1)[1] if stem.startswith("intraday-") else stem
        try:
            dt.date.fromisoformat(tail)
        except ValueError:
            continue
        out.add(tail)
    return sorted(out)


def audit_date(date: str) -> tuple[Checks, dict]:
    ck = Checks()
    daily = audit_daily(date, ck)
    intraday = audit_intraday(date, ck)
    report = {
        "date": date,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "verdict": ck.verdict(),
        "counts": ck.counts(),
        "daily": daily,
        "intraday": intraday,
        "checks": [{"status": s, "check": n, "detail": d} for s, n, d in ck.rows],
    }
    return ck, report


def print_report(date: str, ck: Checks, report: dict) -> None:
    print(f"\n=== SESSION AUDIT {date} ===")
    order = {FAIL: 0, WARN: 1, PASS: 2, INFO: 3}
    for status, name, detail in sorted(ck.rows, key=lambda r: (order[r[0]], r[1])):
        print(f"  {status:<5} {name:<28} {detail}")
    c = report["counts"]
    d, i = report["daily"], report["intraday"]
    print(f"\n  daily    {d.get('live_runs', 0)} live run(s), {d.get('filled', 0)}/{d.get('orders', 0)} "
          f"filled, net_liq ${d.get('net_liq', 0):,.0f}, targets "
          f"{ {k: round(v, 3) for k, v in (d.get('targets') or {}).items()} }")
    if i.get("started"):
        pnl = "n/a" if i.get("pnl") is None else format(i["pnl"], "+,.2f")
        costs = "n/a" if i.get("costs") is None else format(i["costs"], ",.2f")
        print(f"  intraday {i.get('decisions')} decision(s), {i.get('orders')} order(s), "
              f"{i.get('fills')} fill(s), P&L {pnl}, costs {costs}")
    else:
        print(f"  intraday no live session ({i.get('log')})")
    print(f"\n  VERDICT {report['verdict']}   ({c[FAIL]} fail, {c[WARN]} warn, {c[PASS]} pass, {c[INFO]} info)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="YYYY-MM-DD; default the latest date with a log on disk")
    ap.add_argument("--all", action="store_true", help="audit every date on disk, one line each")
    ap.add_argument("--json", action="store_true", help="also write live/log/audit-<date>.json")
    args = ap.parse_args()

    available = dates_on_disk()
    if not available:
        print(f"no session logs in {LOG_DIR}")
        return 2

    if args.all:
        print(f"{'date':<12}{'verdict':<9}{'fail':>5}{'warn':>6}{'pass':>6}  notes")
        worst = 0
        for date in available:
            ck, rep = audit_date(date)
            c = rep["counts"]
            worst = max(worst, RANK[rep["verdict"]])
            head = "; ".join(f"{n}" for s, n, _ in ck.rows if s == FAIL)[:60]
            print(f"{date:<12}{rep['verdict']:<9}{c[FAIL]:>5}{c[WARN]:>6}{c[PASS]:>6}  {head}")
            if args.json:
                (LOG_DIR / f"audit-{date}.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        return worst

    date = args.date or available[-1]
    if date not in available:
        print(f"no log for {date}; available: {', '.join(available)}")
        return 2
    ck, rep = audit_date(date)
    print_report(date, ck, rep)
    if args.json:
        out = LOG_DIR / f"audit-{date}.json"
        out.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {out.relative_to(REPO)}")
    return RANK[rep["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
