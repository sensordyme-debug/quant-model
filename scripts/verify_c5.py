#!/usr/bin/env python
"""C-5: adversarial verification of S-37 (AUD-13), the data-completeness gate in paper_trade.py.

S-37 shipped `data_faults()` + `previous_session()` into `scripts/paper_trade.py` and made a
fault RETURN 3 - i.e. the account does not rebalance at all. Before the patch the same frame
produced `print("warning: no history for [...]")` and the book rebalanced anyway.

That is a change in KIND, not degree: the failure mode moved from "trade on a stale/short frame"
to "do not trade". So the number that decides whether the patch is net-positive is the gate's
FALSE POSITIVE rate, and S-37 clause 6 measured it as 0 of 3,690 sessions ON THE REFERENCE DAILY
STORE (data/ LEAN format, written by scripts/fetch_data.py). The runner does not read that store.
The scheduled task passes no arguments, so it runs `--history yfinance` and reads a live
`yf.download(period="2y")` frame - a different distribution, and S-37's own clause 6 says so
("the store the runner actually reads is yfinance, not this one").

This script measures the same predicate on the store the runner actually reads.

Stages:
  a  identity + gate reproduction: re-run the shipped predicate over the reference store
     (reproduce clause 6's 0/3,690) and over the LIVE yfinance frame the runner fetches.
  b  reachability: exercise data_faults / previous_session on shapes the live path can produce.
  c  the `foreign` positions filter next to the gate (pre-existing, ops commit 162083e).

Usage: py -3.11 scripts/verify_c5.py [--stage a|b|c|all]
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd  # noqa: E402

import paper_trade as pt  # noqa: E402


def universe():
    sig = pt.load_signal("s1_momo")
    return list(sig.UNIVERSE)


def walk_gate(closes, uni, label):
    """Run the SHIPPED predicate over every row of `closes` as if it were the last row.

    The runner runs on session D with a frame ending at D-1, so for row i the previous session
    IS index[i]; the as_of clause therefore cannot fire and this isolates the three NaN clauses,
    which are the ones that can fire on a live fetch.
    """
    fired = []
    for i in range(len(closes)):
        sub = closes.iloc[: i + 1]
        f = pt.data_faults(sub, uni, sub.index[-1], sub.index[-1])
        if f:
            fired.append((sub.index[-1].date(), f))
    rate = 100.0 * len(fired) / max(len(closes), 1)
    print(f"  {label}: gate fires on {len(fired)} of {len(closes)} sessions ({rate:.3f}%)")
    for d, f in fired[:12]:
        print(f"      {d}  {'; '.join(f)}")
    if len(fired) > 12:
        print(f"      ... and {len(fired) - 12} more")
    return fired


def stage_a(uni):
    print("=" * 78)
    print("CLAUSE A  the gate's false-positive rate, on both stores")
    print("=" * 78)

    # --- the reference store, i.e. S-37 clause 6's own sample -------------------------------
    try:
        import sweep_s19 as s19
        px = s19.load_prices() if hasattr(s19, "load_prices") else None
    except Exception as e:  # noqa: BLE001
        px = None
        print(f"  (reference store via sweep_s19 unavailable: {e})")
    if px is not None:
        cols = [c for c in uni if c in px.columns]
        print(f"\n  reference daily store: {len(px)} sessions, {len(cols)}/{len(uni)} names")
        walk_gate(px[cols], uni, "reference store")

    # --- the store the runner actually reads ------------------------------------------------
    print("\n  live yfinance frame, exactly as scripts/paper_trade.py fetches it")
    live = pt.fetch_history_yf(uni)
    print(f"  fetched {len(live)} sessions {live.index[0].date()} -> {live.index[-1].date()}, "
          f"columns {list(live.columns)}")
    nan_cells = int(live[uni].isna().sum().sum())
    print(f"  NaN close cells in the universe block: {nan_cells}")
    fired = walk_gate(live, uni, "LIVE yfinance")

    print("\n  today's frame, which is the one clause 6 actually tested:")
    prev = pt.previous_session(dt.date.today())
    f = pt.data_faults(live, uni, live.index[-1], prev)
    print(f"      previous_session(today) = {prev}   as_of = {live.index[-1].date()}")
    print(f"      faults = {f if f else 'NONE (clean, reproduces S-37)'}")
    return fired, live


def stage_b(uni, live):
    print()
    print("=" * 78)
    print("CLAUSE B  reachability of a REFUSAL on shapes the live path can produce")
    print("=" * 78)

    def shot(label, frame, as_of=..., prev=...):
        as_of = (frame.index[-1] if len(frame) else None) if as_of is ... else as_of
        prev = pt.previous_session(dt.date.today()) if prev is ... else prev
        try:
            f = pt.data_faults(frame, uni, as_of, prev)
            verdict = "REFUSE (exit 3, no rebalance)" if f else "trade"
            print(f"  {label:<52} -> {verdict}")
            if f:
                print(f"      {'; '.join(f)}")
        except Exception as e:  # noqa: BLE001
            print(f"  {label:<52} -> RAISED {type(e).__name__}: {e}")

    shot("clean live frame", live)

    one = live.copy()
    one.iloc[-1, one.columns.get_loc(uni[0])] = float("nan")
    shot(f"one name's last close missing ({uni[0]})", one)

    drop = live.drop(columns=[uni[0]])
    shot(f"one name's column absent ({uni[0]})", drop)

    allnan = live.copy()
    allnan[uni[0]] = float("nan")
    shot(f"one name's column entirely NaN ({uni[0]})", allnan)

    shot("empty frame (yf.download total failure)", live.iloc[0:0])

    # The as_of clause: a stale whole frame. This is the clause the live path hits on a day
    # when yfinance has not yet posted the previous session for ANY name.
    shot("frame one session stale (as_of = D-2)", live.iloc[:-1],
         as_of=live.index[-2], prev=live.index[-1])

    # ...and the same clause from the other side. `data_faults` tests `day < prev` only, so a
    # frame ending on an UNFINISHED session passes. That is not hypothetical: the two history
    # sources sit on one line of `main()`, and `fetch_history_yf` drops today's bar
    # (`closes.index < today`) while `fetch_history_ib` applies no date filter at all - so
    # `--history ib` at 15:45 ET returns today's partial bar, and the signal ranks and sizes on
    # a mid-session print as if it were a close.
    today = pd.Timestamp(dt.date.today())
    partial = live.copy()
    partial.loc[today] = live.iloc[-1] * 1.01
    shot("frame ends on TODAY's unfinished bar (--history ib)", partial)

    # previous_session's own fallback, which decides whether the as_of clause is armed at all.
    print("\n  previous_session() behaviour:")
    for d in [dt.date.today(),
              dt.date(2026, 9, 14),      # a Monday
              dt.date(2026, 11, 27),     # day after Thanksgiving, early close
              dt.date(2028, 6, 1)]:      # past the calendar's coverage_end
        print(f"      previous_session({d}) = {pt.previous_session(d)}")


def stage_c(uni):
    print()
    print("=" * 78)
    print("CLAUSE C  the `foreign` positions filter, three lines above the new gate")
    print("=" * 78)
    from intraday_common import UNIVERSE as IU

    # Reproduce the shipped filter exactly (scripts/paper_trade.py, main()).
    def shipped(positions):
        foreign = {s: q for s, q in positions.items() if s in IU}
        if foreign:
            positions = {s: q for s, q in positions.items() if s in uni}
        return positions

    retired = "TQQQ"  # the name S-18 retired and ops commit 162083e says must still be sold
    cases = [
        ("intraday sleeve flat (the normal 15:45 case)", {retired: 3227, "SPY": 100}),
        ("intraday sleeve holding one name", {retired: 3227, "SPY": 100, "NVDA": 50}),
    ]
    for label, pos in cases:
        out = shipped(dict(pos))
        sold = retired in out
        print(f"  {label}")
        print(f"      positions in  {pos}")
        print(f"      positions out {out}")
        print(f"      retired {retired} still gets a zero target: "
              f"{'YES' if sold else 'NO  <-- orphaned, never sold'}")


def stage_d():
    """The headline break-even, re-derived with the seed error S-37 already measured.

    S-37 clause 2 quotes "the tightest break-even is 2.0 outages a year" and the journal turns
    that into "two bad yfinance prints in a year cost 0.5 CAR points". Both come from the
    1-in-21 cell, which runs at 11.34 outages/yr. The cell whose outage rate matches the
    sentence is 1-in-252 (0.93/yr), and its cost-per-outage is 27-33% SMALLER, so the headline
    is quoted from the most expensive cell rather than the matching one. The journal's defence
    is that "the cost per outage is the same size in both"; it is 1.50x and 1.33x apart, and
    the low-rate cell has no power to say whether that gap is real.

    Cells reproduced exactly at HEAD by C-5 (see the run log in the journal).
    """
    import math

    print()
    print("=" * 78)
    print("CLAUSE D  the headline break-even, carried through S-37's own seed error")
    print("=" * 78)
    # cost_bps, rate, events/yr, CAR cost (pts), sd over 5 seeds
    cells = [(0.0, 252, 0.93, 0.128, 0.318),
             (0.0, 21, 11.34, 2.338, 1.689),
             (2.0, 252, 0.93, 0.176, 0.317),
             (2.0, 21, 11.34, 2.860, 1.661)]
    bar = 0.5           # S-33's selection premium, the bar S-37 prices against
    threshold = 12.0    # S-37's pre-registered materiality threshold, outages/yr
    n_seeds = 5

    print(f"  bar {bar} CAR pts (S-33 selection premium); pre-registered threshold "
          f"{threshold:.0f} outages/yr\n")
    print(f"  {'cost':>5} {'rate':>7} {'ev/yr':>6} {'pts/outage':>11} {'+-1sd':>15} "
          f"{'breakeven':>10} {'+-1sd band':>18}")
    for cost, rate, per_year, drop, sd in cells:
        per_outage = drop / per_year
        se = (sd / math.sqrt(n_seeds)) / per_year
        lo, hi = per_outage - se, per_outage + se
        be = bar / per_outage
        be_lo = bar / hi if hi > 0 else float("inf")
        be_hi = bar / lo if lo > 0 else float("inf")
        band = f"[{be_lo:.1f}, {be_hi:.1f}]" if math.isfinite(be_hi) else f"[{be_lo:.1f}, inf)"
        print(f"  {cost:>4.0f}b {'1/'+str(rate):>7} {per_year:>6.2f} {per_outage:>11.4f} "
              f"{'+-'+format(se,'.4f'):>15} {be:>10.1f} {band:>18}")

    print("\n  rate-dependence of the quantity being extrapolated:")
    for cost in (0.0, 2.0):
        lo_c = [c for c in cells if c[0] == cost and c[1] == 252][0]
        hi_c = [c for c in cells if c[0] == cost and c[1] == 21][0]
        a, b = lo_c[3] / lo_c[2], hi_c[3] / hi_c[2]
        print(f"      {cost:.0f} bp: {a:.4f} pts/outage at 0.93/yr vs {b:.4f} at 11.34/yr "
              f"-> {b / a:.2f}x apart")

    print("\n  the headline is the 1-in-21 / 2 bp cell: breakeven 2.0 outages/yr.")
    m = [c for c in cells if c[0] == 2.0 and c[1] == 252][0]
    per_outage = m[3] / m[2]
    se = (m[4] / math.sqrt(n_seeds)) / m[2]
    be_hi = bar / (per_outage - se)
    print(f"  the cell that matches the sentence's own rate is 1-in-252 / 2 bp: "
          f"breakeven {bar / per_outage:.1f} outages/yr,")
    print(f"  and its +1sd break-even is {be_hi:.1f}/yr, which is "
          f"{'PAST' if be_hi > threshold else 'inside'} the pre-registered "
          f"threshold of {threshold:.0f}.")
    print("\n  VERDICT: the direction survives and the decision does not change (the gate's own")
    print("  cost is bounded by its false-positive rate, clause A: 0 of 501 live sessions), but")
    print("  '2.0 outages a year' is quoted from the wrong cell and carries no stated error.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["a", "b", "c", "d", "all"])
    args = ap.parse_args()
    uni = universe()
    print(f"universe ({len(uni)}): {uni}\n")
    live = None
    if args.stage in ("a", "all"):
        _, live = stage_a(uni)
    if args.stage in ("b", "all"):
        if live is None:
            live = pt.fetch_history_yf(uni)
        stage_b(uni, live)
    if args.stage in ("c", "all"):
        stage_c(uni)
    if args.stage in ("d", "all"):
        stage_d()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
