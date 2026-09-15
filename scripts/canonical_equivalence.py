"""PHASE 3A: prove the canonical data path and the legacy data path are the same experiment.

    python scripts/canonical_equivalence.py --spec examples.example_strategy:SPEC

WHAT THIS IS FOR
----------------
`scripts/run_strategy.py` now takes its bars from `quant_brain.research.session_source`, which
loads through the canonical data layer. Every published futures number in this repository was
produced by the other path - `futures_discover.load` reading the provider parquet directly.
Switching the authoritative input without measuring the difference would silently reprice the
entire research history.

So the same FROZEN spec is run twice, once per data path, and the two runs are compared field
by field from the raw bars all the way to the Topstep account result. Nothing is tuned between
them and the spec hash is asserted identical, so any difference that appears is a difference in
the DATA PATH and nowhere else.

WHAT IS COMPARED
----------------
    bars · timestamps · contract labels · OHLC · volume · features · signals · orders ·
    fills · trade ledger · P&L · MAE · MFE · equity · monthly results · Topstep result

for every one of the four execution profiles, not only the headline.

THE RULE THIS SCRIPT ENFORCES
-------------------------------
A difference is not "fixed" by changing the strategy, and it is not fixed by changing the
comparison. It is either EXPLAINED - with the mechanism named and the number attributed - or
the run fails. `EXPECTED_DIFFERENCES` is the list of explanations, each one a written statement
of why two numbers legitimately differ; anything not on it that differs is a FAIL.
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import futures_discover as fd  # noqa: E402
import run_strategy as rs  # noqa: E402

from quant_brain.markets.futures_cme import features as fe  # noqa: E402
from quant_brain.research import execution_modes as em  # noqa: E402
from quant_brain.research import session_source as ssrc  # noqa: E402
from quant_brain.research.account_result import PayoutRuleSet, build_account_result  # noqa: E402
from quant_brain.research.ledger_builder import build_from_profile  # noqa: E402
from quant_brain.research.strategy_runner import monthly_table  # noqa: E402
from quant_brain.research.strategy_spec import StrategySpec  # noqa: E402

#: Money compares to the cent. Prices and features compare to float noise, because the two
#: paths do arithmetic in a different ORDER (the canonical adapter sorts and reindexes) and
#: IEEE addition is not associative. A tolerance here is a statement about float order of
#: operations, never a tolerance for a different answer - every comparison below that uses it
#: also reports the worst observed difference, so a real drift could not hide under it.
MONEY_TOL = 1e-9
PRICE_TOL = 0.0          # exact: the same bytes must produce the same price
FEATURE_TOL = 1e-12


#: Differences that are legitimate, each with the mechanism named. Anything not listed that
#: differs fails the run. These are counter differences, NOT data differences: no bar, price,
#: signal, fill, trade or dollar is permitted to differ at all.
EXPECTED_DIFFERENCES: dict[str, str] = {
    "attrition.bars_in_window": (
        "The two paths COUNT at different points, they do not keep different bars. "
        "`futures_discover.load` applies the window and the one-contract-per-session filter "
        "in one function and returns the result, so its bar count is already net of the "
        "multi-contract day. The canonical path counts the window first and the contract "
        "filter second, so its count still includes that day. The difference is exactly the "
        "bars of the dropped session(s) and the KEPT sessions are identical."),
    "attrition.sessions_in_window": (
        "Same mechanism as bars_in_window: the canonical count is taken before the "
        "multi-contract filter and the legacy count after it."),
    "attrition.sessions_dropped_multi_contract": (
        "The legacy path reports -1 (unknown) because `fd.load` has already discarded those "
        "days by the time it returns; the count is not recoverable without re-reading the "
        "file. Stated as unknown rather than guessed at."),
    "provenance": (
        "The canonical path declares the data form, the roll method, the adjustment method, "
        "the manifest id, the frame fingerprint and the quality status. The legacy path "
        "declares none of them - it has nowhere to put them. That asymmetry IS the reason "
        "for the migration and is not a discrepancy in the result."),
    "gates_run": (
        "The canonical path runs three gates (canonical schema, canonical quality, futures "
        "validator); the legacy path runs one (the futures validator). The canonical path is "
        "strictly stronger - it runs every check the legacy path runs, and more."),
    "wall_clock": (
        "The canonical path is slower because it runs the schema validation and the full "
        "quality gate on every load. That is a cost, not a difference in the answer."),
}


# ======================================================================================
# COMPARISON PRIMITIVES
# ======================================================================================

@dataclass
class Check:
    """One comparison. `status` is MATCH, EXPLAINED or DIFFER - never a silent pass."""

    name: str
    status: str
    detail: str = ""
    worst: float | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("MATCH", "EXPLAINED")

    def row(self) -> str:
        w = "" if self.worst is None else f"  worst |d|={self.worst:.3e}"
        return f"  {self.status:9} {self.name:44}{w}  {self.detail}"


@dataclass
class Comparison:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "", worst: float | None = None) -> None:
        self.checks.append(Check(name, status, detail, worst))

    def exact(self, name: str, a, b, *, tol: float = 0.0) -> None:
        """Element-wise equality of two sequences, with the worst difference reported."""
        a = np.asarray(a)
        b = np.asarray(b)
        if a.shape != b.shape:
            self.add(name, "DIFFER", f"shape {a.shape} vs {b.shape}")
            return
        if a.dtype.kind in "fiu" and b.dtype.kind in "fiu":
            af = a.astype(float)
            bf = b.astype(float)
            both_nan = np.isnan(af) & np.isnan(bf)
            d = np.where(both_nan, 0.0, np.abs(af - bf))
            worst = float(d.max()) if d.size else 0.0
            if worst <= tol:
                self.add(name, "MATCH", f"{a.size:,} values", worst)
            else:
                i = int(np.nanargmax(d))
                self.add(name, "DIFFER",
                         f"{int((d > tol).sum()):,} of {a.size:,} differ; first at index {i}: "
                         f"{af.flat[i]!r} vs {bf.flat[i]!r}", worst)
            return
        same = a.astype(str) == b.astype(str)
        if bool(same.all()):
            self.add(name, "MATCH", f"{a.size:,} values")
        else:
            i = int(np.argmax(~same))
            self.add(name, "DIFFER", f"{int((~same).sum()):,} of {a.size:,} differ; "
                                     f"first at index {i}: {a.flat[i]!r} vs {b.flat[i]!r}")

    def frames(self, name: str, a: pd.DataFrame, b: pd.DataFrame, *,
               tol: float = 0.0) -> None:
        """Every column of two frames, so a new column cannot slip past the comparison."""
        if list(a.columns) != list(b.columns):
            self.add(name, "DIFFER", f"columns {list(a.columns)} vs {list(b.columns)}")
            return
        if len(a) != len(b):
            self.add(name, "DIFFER", f"{len(a):,} rows vs {len(b):,} rows")
            return
        for col in a.columns:
            self.exact(f"{name}.{col}", a[col].to_numpy(), b[col].to_numpy(), tol=tol)

    def scalar(self, name: str, a, b, *, tol: float = 0.0) -> None:
        if isinstance(a, float) and isinstance(b, float):
            d = abs(a - b)
            if (np.isnan(a) and np.isnan(b)) or d <= tol:
                self.add(name, "MATCH", f"{a!r}", 0.0 if np.isnan(d) else d)
            else:
                self.add(name, "DIFFER", f"{a!r} vs {b!r}", d)
            return
        self.add(name, "MATCH" if a == b else "DIFFER",
                 f"{a!r}" if a == b else f"{a!r} vs {b!r}")

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]


# ======================================================================================
# THE RUN
# ======================================================================================

@dataclass
class PathRun:
    """Everything one data path produced, held so the two can be compared after the fact."""

    path: str
    sessions: list[pd.DataFrame]
    feats: list[pd.DataFrame]
    signals: list[np.ndarray]
    ledgers: dict
    accounts: dict
    provenance: dict
    attrition: dict
    seconds: float


def run_one(spec: StrategySpec, data_path: str, *, account_size: int,
            daily_loss_limit: float | None, reps: int) -> PathRun:
    """One full run: bars -> features -> signals -> ledgers -> accounts, on one data path."""
    t0 = time.time()
    sset = ssrc.build(spec, data_path=data_path, root=REPO)
    sessions = sset.frames
    feats = fd.build_features(sessions, fe.library())
    signals = [np.nan_to_num(np.asarray(spec.signal(X), dtype=float), nan=0.0)
               for X in feats]

    rules = PayoutRuleSet.as_documented(account_size)
    ledgers, accounts = {}, {}
    for profile in em.LADDER:
        led = build_from_profile(spec, sessions, feats, profile)
        ledgers[profile.name] = led
        accounts[profile.name] = build_account_result(
            led, account_size=account_size, daily_loss_limit=daily_loss_limit,
            payout_rules=rules, reps=reps)
    return PathRun(path=data_path, sessions=sessions, feats=feats, signals=signals,
                   ledgers=ledgers, accounts=accounts, provenance=sset.provenance,
                   attrition=sset.attrition.as_dict(), seconds=time.time() - t0)


def compare(a: PathRun, b: PathRun) -> Comparison:
    """`a` is canonical, `b` is legacy. Everything the phase gate asks for, in order."""
    cmp = Comparison()

    # -- 1. BARS -----------------------------------------------------------------------
    cmp.scalar("sessions.count", len(a.sessions), len(b.sessions))
    if len(a.sessions) != len(b.sessions):
        return cmp                       # nothing below is comparable
    cmp.exact("sessions.days",
              [s["day"].iloc[0] for s in a.sessions],
              [s["day"].iloc[0] for s in b.sessions])
    cmp.exact("sessions.bars_per_session",
              [len(s) for s in a.sessions], [len(s) for s in b.sessions])

    ca = pd.concat(a.sessions, ignore_index=True)
    cb = pd.concat(b.sessions, ignore_index=True)
    cmp.scalar("bars.total", len(ca), len(cb))

    # -- 2. TIMESTAMPS, CONTRACT LABELS, OHLC, VOLUME ----------------------------------
    cmp.exact("bars.timestamps", ca["t"].astype("int64").to_numpy(),
              cb["t"].astype("int64").to_numpy())
    cmp.exact("bars.session_date", ca["day"].astype(str).to_numpy(),
              cb["day"].astype(str).to_numpy())
    cmp.exact("bars.wall_clock", ca["hm"].astype(str).to_numpy(),
              cb["hm"].astype(str).to_numpy())
    cmp.exact("bars.contract_label", ca["contract"].astype(str).to_numpy(),
              cb["contract"].astype(str).to_numpy())
    for col, label in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close")):
        cmp.exact(f"bars.{label}", ca[col].to_numpy(), cb[col].to_numpy(), tol=PRICE_TOL)
    cmp.exact("bars.volume", ca["v"].to_numpy(), cb["v"].to_numpy(), tol=PRICE_TOL)

    # -- 3. FEATURES and SIGNALS -------------------------------------------------------
    fa = pd.concat(a.feats, ignore_index=True)
    fb = pd.concat(b.feats, ignore_index=True)
    if list(fa.columns) != list(fb.columns):
        cmp.add("features.columns", "DIFFER", f"{list(fa.columns)} vs {list(fb.columns)}")
    else:
        cmp.add("features.columns", "MATCH", f"{len(fa.columns)} features")
        worst = 0.0
        for col in fa.columns:
            x = fa[col].to_numpy(dtype=float)
            y = fb[col].to_numpy(dtype=float)
            d = np.where(np.isnan(x) & np.isnan(y), 0.0, np.abs(x - y))
            worst = max(worst, float(np.nanmax(d)) if d.size else 0.0)
        cmp.add("features.values", "MATCH" if worst <= FEATURE_TOL else "DIFFER",
                f"{fa.size:,} values across {len(fa.columns)} features", worst)
    cmp.exact("signals.positions", np.concatenate(a.signals), np.concatenate(b.signals))
    cmp.scalar("signals.entries",
               int((np.diff(np.concatenate(a.signals), prepend=0.0) != 0).sum()),
               int((np.diff(np.concatenate(b.signals), prepend=0.0) != 0).sum()))

    # -- 4. LEDGERS, per execution profile ---------------------------------------------
    for name in (p.name for p in em.LADDER):
        la, lb = a.ledgers[name], b.ledgers[name]
        cmp.scalar(f"{name}.ledger.spec_hash", la.spec_hash, lb.spec_hash)
        cmp.scalar(f"{name}.ledger.round_turn_cost", la.round_turn_cost, lb.round_turn_cost,
                   tol=MONEY_TOL)

        # orders and fills
        cmp.frames(f"{name}.fills", la.fill_frame(), lb.fill_frame(), tol=MONEY_TOL)
        # the trade ledger, every column: prices, P&L, MAE, MFE, R, reasons, hold times
        cmp.frames(f"{name}.trades", la.trade_frame(), lb.trade_frame(), tol=MONEY_TOL)

        # P&L, equity, intraday path
        cmp.exact(f"{name}.daily_pnl", la.daily().to_numpy(), lb.daily().to_numpy(),
                  tol=MONEY_TOL)
        cmp.exact(f"{name}.equity_curve", la.equity_curve(), lb.equity_curve(), tol=MONEY_TOL)
        cmp.exact(f"{name}.intraday_equity", la.intraday_equity(), lb.intraday_equity(),
                  tol=MONEY_TOL)
        cmp.scalar(f"{name}.net_pnl", float(la.daily().sum()), float(lb.daily().sum()),
                   tol=MONEY_TOL)

        # MAE / MFE called out by name, because they are what an exit study reads
        ta, tb = la.trade_frame(), lb.trade_frame()
        if len(ta) and len(tb) and len(ta) == len(tb):
            cmp.exact(f"{name}.mae", ta["mae"].to_numpy(), tb["mae"].to_numpy(),
                      tol=MONEY_TOL)
            cmp.exact(f"{name}.mfe", ta["mfe"].to_numpy(), tb["mfe"].to_numpy(),
                      tol=MONEY_TOL)

        # monthly
        ma, mb = monthly_table(la.daily()), monthly_table(lb.daily())
        cmp.frames(f"{name}.monthly", ma, mb, tol=MONEY_TOL)

        # -- 5. THE TOPSTEP RESULT -----------------------------------------------------
        aa, ab = a.accounts[name], b.accounts[name]
        for fname, va, vb in _account_fields(aa, ab):
            cmp.scalar(f"{name}.topstep.{fname}", va, vb,
                       tol=MONEY_TOL if isinstance(va, float) else 0.0)
        cmp.frames(f"{name}.topstep.mll_path", aa.mll_path(), ab.mll_path(), tol=MONEY_TOL)

    # -- 6. THE DIFFERENCES THAT ARE SUPPOSED TO BE THERE ------------------------------
    for key in ("bars_in_window", "sessions_in_window", "sessions_dropped_multi_contract"):
        va, vb = a.attrition[key], b.attrition[key]
        if va == vb:
            cmp.add(f"attrition.{key}", "MATCH", f"{va}")
        else:
            cmp.add(f"attrition.{key}", "EXPLAINED", f"canonical {va} vs legacy {vb}: "
                    + EXPECTED_DIFFERENCES[f"attrition.{key}"])
    cmp.exact("attrition.sessions_kept",
              [a.attrition["sessions_kept"]], [b.attrition["sessions_kept"]])
    cmp.add("provenance", "EXPLAINED",
            f"canonical declares {a.provenance['feature_data']['data_form']} / "
            f"manifest {a.provenance['feature_data']['manifest_id']} / frame "
            f"{a.provenance['feature_data']['frame_fingerprint']}; legacy declares nothing. "
            + EXPECTED_DIFFERENCES["provenance"])
    cmp.add("gates_run", "EXPLAINED",
            f"canonical {a.provenance['gates_run']} vs legacy {b.provenance['gates_run']}. "
            + EXPECTED_DIFFERENCES["gates_run"])
    cmp.add("wall_clock", "EXPLAINED",
            f"canonical {a.seconds:.1f}s vs legacy {b.seconds:.1f}s. "
            + EXPECTED_DIFFERENCES["wall_clock"])
    return cmp


def _account_fields(a, b):
    """Every scalar on the account result, paired. Reflection, so a new field is not missed."""
    skip = {"returns", "payout", "monthly", "cross_check", "probability_note", "ledger"}
    for name in sorted(vars(a)):
        if name in skip or name.startswith("_"):
            continue
        va, vb = getattr(a, name), getattr(b, name)
        if isinstance(va, (int, float, str, bool, type(None))):
            yield name, va, vb
        else:
            yield name, str(va), str(vb)
    for name in sorted(vars(a.returns)):
        yield f"returns.{name}", getattr(a.returns, name), getattr(b.returns, name)
    yield "payout.eligible_sessions", a.payout.eligible_sessions, b.payout.eligible_sessions
    yield "payout.total_paid", a.payout.total_paid, b.payout.total_paid
    yield "payout.first_eligible", str(a.payout.first_eligible_session), \
        str(b.payout.first_eligible_session)
    yield "cross_check.agrees", a.cross_check.agrees, b.cross_check.agrees
    yield "cross_check.fields", a.cross_check.fields_compared, b.cross_check.fields_compared
    yield "monthly.rows", len(a.monthly), len(b.monthly)
    for i, (ra, rb) in enumerate(zip(a.monthly, b.monthly, strict=False)):
        yield f"monthly[{i}].net_pnl", ra.net_pnl, rb.net_pnl
        yield f"monthly[{i}].month", str(ra.month), str(rb.month)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", default="examples.example_strategy:SPEC",
                    help="module:attribute pointing at the frozen reference StrategySpec")
    ap.add_argument("--instrument", default=None,
                    help="re-point the SAME frozen signal at another store, so equivalence "
                         "is measured on more than one file. The spec's logic, exits, sizing, "
                         "session and costs are untouched; only the price source moves, and "
                         "the spec hash changes accordingly and is reported.")
    ap.add_argument("--account-size", type=int, default=50_000)
    ap.add_argument("--daily-loss-limit", type=float, default=None)
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--out", type=Path,
                    default=REPO / "research" / "canonical_equivalence.json")
    args = ap.parse_args()

    mod_name, _, attr = args.spec.partition(":")
    spec: StrategySpec = getattr(importlib.import_module(mod_name), attr or "SPEC")
    if not isinstance(spec, StrategySpec):
        raise TypeError(f"{args.spec} is not a StrategySpec")
    if args.instrument and args.instrument != spec.instrument:
        spec = dataclasses.replace(spec, instrument=args.instrument)
        args.out = args.out.with_name(
            f"{args.out.stem}_{args.instrument.lower()}{args.out.suffix}")

    print("=" * 100)
    print("PHASE 3A EQUIVALENCE:  CANONICAL DATA PATH  vs  LEGACY DATA PATH")
    print("=" * 100)
    print(f"  frozen spec   {spec.name}   hash {spec.spec_hash}")
    print(f"  instrument    {spec.instrument} {spec.timeframe} "
          f"{spec.session.open_et}-{spec.session.close_et} ET")
    print(f"  engine        {rs.ENGINE_VERSION}")
    print("  The spec is IDENTICAL on both sides. Any difference below is the data path.\n")

    canonical = run_one(spec, ssrc.CANONICAL, account_size=args.account_size,
                        daily_loss_limit=args.daily_loss_limit, reps=args.reps)
    print(f"  canonical run: {len(canonical.sessions)} sessions, {canonical.seconds:.1f}s")
    legacy = run_one(spec, ssrc.LEGACY, account_size=args.account_size,
                     daily_loss_limit=args.daily_loss_limit, reps=args.reps)
    print(f"  legacy    run: {len(legacy.sessions)} sessions, {legacy.seconds:.1f}s")

    # The hash must be the same object on both sides or the comparison is meaningless.
    assert canonical.ledgers["CONSERVATIVE"].spec_hash == spec.spec_hash
    assert legacy.ledgers["CONSERVATIVE"].spec_hash == spec.spec_hash

    cmp = compare(canonical, legacy)
    matched = sum(1 for c in cmp.checks if c.status == "MATCH")
    explained = sum(1 for c in cmp.checks if c.status == "EXPLAINED")
    failed = cmp.failures

    print(f"\n  {len(cmp.checks)} comparisons: {matched} MATCH, {explained} EXPLAINED, "
          f"{len(failed)} DIFFER\n")
    for c in cmp.checks:
        if c.status != "MATCH":
            print(c.row())
    print("\n  MATCHING COMPARISONS (identical on both paths)")
    for c in cmp.checks:
        if c.status == "MATCH":
            print(c.row())

    verdict = "EQUIVALENT" if not failed else "NOT EQUIVALENT"
    print("\n" + "=" * 100)
    print(f"VERDICT: {verdict}")
    if failed:
        print("  Unexplained differences - the canonical path must NOT become authoritative "
              "until each is attributed to a mechanism:")
        for c in failed:
            print(c.row())
    else:
        print("  Every data, signal, order, fill, trade, P&L, excursion, equity, monthly and "
              "Topstep field is identical across the two paths on this dataset.")
        print("  The differences that remain are the ones the canonical layer exists to "
              "create: declared form, declared roll, declared adjustment, a quality gate, a "
              "manifest id and a frame fingerprint.")
    print("=" * 100)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "verdict": verdict,
        "spec": {"name": spec.name, "hash": spec.spec_hash, "instrument": spec.instrument,
                 "session": [spec.session.open_et, spec.session.close_et]},
        "engine_version": rs.ENGINE_VERSION,
        "sessions": len(canonical.sessions),
        "profiles": [p.name for p in em.LADDER],
        "counts": {"match": matched, "explained": explained, "differ": len(failed)},
        "checks": [{"name": c.name, "status": c.status, "detail": c.detail,
                    "worst_abs_difference": c.worst} for c in cmp.checks],
        "canonical_provenance": canonical.provenance,
        "legacy_provenance": legacy.provenance,
        "seconds": {"canonical": canonical.seconds, "legacy": legacy.seconds},
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten to {args.out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
