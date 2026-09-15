"""The control that decides whether the volatility gate is a signal or just less trading.

WHAT NEEDS CONTROLLING
----------------------
Gating the regular-session long on a quiet overnight range raised the simulated Combine pass
rate on MES from 16.8% to 45.8% at five contracts. Taken at face value that is the best
result in this whole study, and it is exactly the kind of result that turns out to be an
artefact.

The gate selects 48 of 251 sessions. So the gated strategy does two things at once: it picks
days by a criterion, and it trades on nineteen percent of the days. The second one alone
improves a barrier problem, because a strategy that is flat cannot breach a trailing
drawdown, and every day spent flat is a day the high-water mark does not advance while the
account waits for a good one.

So the comparison "gated versus always on" confounds the criterion with the exposure, and
cannot distinguish a real signal from a reduction in trading.

THE CONTROL
-----------
Run the same simulation on RANDOM subsets of exactly the same size. If picking 48 sessions at
random from the 251 produces the same pass rate, the overnight range contributed nothing and
the entire gain came from trading less - in which case the honest recommendation is "trade
less", not "use this signal".

The randomisation is repeated many times so the control has a distribution rather than a
point, and the gate's result is then reported as a percentile against it. That percentile is
the actual evidence. A gate at the 55th percentile of its own random control is noise however
large the raw improvement looked.

A SECOND CONTROL, FOR THE SIGN
-------------------------------
The loud-day gate is run the same way. If quiet days are genuinely better, loud days must be
correspondingly worse than their own matched random control - and if BOTH sit near their
controls, the split carries no information in either direction.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))

from overnight_combine import (MAX_DAYS, block_bootstrap_indices,  # noqa: E402
                               session_paths, to_twin_days)
from quant_brain.markets.futures_cme.twin import TopstepTwin, TwinDay  # noqa: E402

N_PATHS = 300
N_CONTROLS = 60


def pass_rate(base: list[TwinDay], rng: np.random.Generator, n_paths: int = N_PATHS) -> float:
    n = len(base)
    passed = 0
    for _ in range(n_paths):
        idx = block_bootstrap_indices(n, MAX_DAYS, rng)
        seq = [TwinDay(day=dt.date(2025, 1, 1) + dt.timedelta(days=k), pnl=base[i].pnl,
                       path=base[i].path, traded=base[i].traded)
               for k, i in enumerate(idx)]
        res = TopstepTwin(50_000, strict_path=True, allow_unverified_target=True).run(seq)
        passed += res.combine_days is not None
    return passed / n_paths


def main() -> int:
    from overnight_hypotheses import futures_features
    fut = futures_features(pd.read_parquet(REPO / "research" / "overnight_panel.parquet"))
    rng = np.random.default_rng(7717)

    print("=" * 96)
    print("MATCHED-EXPOSURE CONTROL: is the gate a signal, or is it just trading less?")
    print(f"{N_CONTROLS} random gates of identical size per cell, {N_PATHS} paths each.")
    print("=" * 96)

    for symbol, sizes in (("MES", [5, 10]), ("MNQ", [5, 10])):
        g = fut[fut.symbol == symbol].sort_values("tdate").reset_index(drop=True)
        thresh = g["on_range_pct"].expanding(60).quantile(0.33).shift(1)
        paths = session_paths(symbol, "rth")
        pdates = [d for d, _ in paths]
        keyed = dict(zip(g["tdate"], zip(g["on_range_pct"], thresh)))
        rng_pairs = [keyed.get(d, (np.nan, np.nan)) for d in pdates]
        quiet = np.array([bool(np.isfinite(b) and a <= b) for a, b in rng_pairs])
        valid = np.array([bool(np.isfinite(b)) for _, b in rng_pairs])
        loud = valid & ~quiet
        k_quiet, k_loud = int(quiet.sum()), int(loud.sum())

        print(f"\n{symbol}: {len(paths)} sessions, gate selects {k_quiet} quiet / "
              f"{k_loud} loud ({int(valid.sum())} with a formed threshold)")
        print(f"  {'size':>4} {'gate':7} {'k':>4} {'gate pass':>10} "
              f"{'random p50':>11} {'random p5-p95':>18} {'pctile':>8}  verdict")

        for size in sizes:
            for name, mask, k in (("quiet", quiet, k_quiet), ("loud", loud, k_loud)):
                obs = pass_rate(to_twin_days(paths, symbol, size, take=mask), rng)
                ctrl = []
                for _ in range(N_CONTROLS):
                    m = np.zeros(len(paths), dtype=bool)
                    m[rng.choice(np.flatnonzero(valid), size=k, replace=False)] = True
                    ctrl.append(pass_rate(to_twin_days(paths, symbol, size, take=m),
                                          rng, n_paths=120))
                ctrl = np.array(ctrl)
                pct = float((ctrl < obs).mean())
                verdict = ("SIGNAL" if pct > 0.95 else
                           "INVERSE SIGNAL" if pct < 0.05 else
                           "indistinguishable from trading less")
                band = f"[{np.percentile(ctrl, 5):.1%}, {np.percentile(ctrl, 95):.1%}]"
                print(f"  {size:4d} {name:7} {k:4d} {obs:10.1%} {np.median(ctrl):11.1%} "
                      f"{band:>18} {pct:8.1%}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
