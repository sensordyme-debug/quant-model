"""Phases 7, 8, 11 and 15: controls, slippage, Topstep economics, and the plots.

WHAT THE GRID ALREADY SETTLED
-------------------------------
Forty-one preregistered exit architectures on the one entry that carries information. The
in-sample best (a 30-bar time stop, +$7.19/trade) delivers -$20.55/trade out of sample, and the
rank correlation between in-sample and out-of-sample dollars per trade is **-0.002**. Choosing
an exit on the in-sample half carries no information about how it performs on the other half.

One result is worth more than the whole grid: `E.time1b` is byte-identical to
`F.baseline_invalidation`. The signal's median hold is one bar, so signal invalidation already
fires at bar one - the mechanism is a one-bar scalp and its existing exit is already the
correct one. That is consistent with the entry test, where the edge was t = 2.48 at one bar and
gone by bar ten.

So the remaining questions are not "which exit is best" but "is the one it already has worth
trading", and those are answered here.

THE CONTROLS, AND WHAT EACH ONE RULES OUT
-------------------------------------------
    RANDOM STOP / TARGET   the same architecture with the distances drawn at random from the
                           declared range. Rules out the possibility that any stop and target
                           of roughly the right size would do as well.
    RANDOM TIMING          exit after a random number of bars drawn to match the real exit's
                           holding-time distribution. Rules out the exit adding value purely
                           through duration.
    FIXED HOLD             exit after exactly the median holding time, every time. The
                           simplest possible exit; anything that cannot beat it is not an
                           architecture, it is a schedule.
    RANDOM ENTRY           the real exit architecture applied to entries drawn at random from
                           matched bars. Rules out the exit being the whole strategy.

The last one is the one most often skipped and the most informative here, because if a random
entry with this exit performs as well as the real entry with this exit, the entry test's
verdict was optimistic.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402
import pandas as pd               # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import futures_discover as fd  # noqa: E402

fd.use_session(*fd.TOPSTEP_SESSION)

from quant_brain.markets.futures_cme import instruments as inst   # noqa: E402
from quant_brain.markets.futures_cme.twin import TopstepTwin, TwinDay  # noqa: E402
from quant_brain.research import exits as X                       # noqa: E402
from exit_architecture_research import (PASSING, SPLIT, load, run_arch,  # noqa: E402
                                        session_atr, stats)

OUT = REPO / "docs" / "research" / "strategy_results" / "exit"
N_RANDOM = 200
MLL, DLL, TARGET = 2_000.0, 1_000.0, 3_000.0
plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False})


def random_control(sessions, feats, strategy, symbol, rng, mode: str,
                   median_bars: int) -> float:
    """One control replication. Returns $/trade."""
    spec = inst.get(symbol).spec
    from quant_brain.markets.futures_cme import execution_sim as ex
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(symbol), symbol=symbol)
    cost = sim.round_turn_cost(1)
    nets = []
    all_bars = []
    for g, Xf in zip(sessions, feats, strict=True):
        pos = np.nan_to_num(np.asarray(strategy.signal(Xf), dtype=float), nan=0.0)
        ev = X.entry_events(pos)
        if not ev:
            continue
        c = g["c"].to_numpy(dtype=float)
        hi = g["h"].to_numpy(dtype=float)
        lo = g["l"].to_numpy(dtype=float)
        atr = session_atr(g)
        n = len(c)
        for bar, d in ev:
            all_bars.append(bar)
            if mode == "random_entry":
                # Randomise ONLY the entry bar and hold for the SAME number of bars the
                # real exit holds. An earlier version also swapped in a random stop/target,
                # which changed two things at once and made the comparison uninterpretable.
                bar = int(rng.integers(0, n - 2))
                end = min(bar + median_bars, n - 1)
                nets.append((c[end] - c[bar]) * d * spec.multiplier - cost)
                continue
            if mode == "random_stop_target":
                arch = X.ExitArchitecture(
                    "ctl", stop_atr=float(rng.choice([0.5, 0.75, 1.0, 1.25, 1.5])),
                    target_r=float(rng.choice([0.5, 0.75, 1.0, 1.5, 2.0])),
                    use_invalidation=False)
                r = X.simulate_trade(c, hi, lo, pos, bar, d, atr, arch)
                nets.append(r.points * spec.multiplier - cost)
            elif mode == "random_timing":
                k = int(max(1, rng.geometric(1.0 / max(1, median_bars))))
                end = min(bar + k, n - 1)
                nets.append((c[end] - c[bar]) * d * spec.multiplier - cost)
            elif mode == "fixed_hold":
                end = min(bar + median_bars, n - 1)
                nets.append((c[end] - c[bar]) * d * spec.multiplier - cost)
    return float(np.mean(nets)) if nets else np.nan


def to_twin(trades: pd.DataFrame, sessions, scale: float) -> list[TwinDay]:
    """Per-session equity paths at `scale` contracts, from the realised trades."""
    by_day = {d: g for d, g in trades.groupby("session")}
    out = []
    for g in sessions:
        day = g["day"].iloc[0]
        n_bars = len(g)
        eq = np.zeros(n_bars, dtype=float)
        t = by_day.get(day)
        if t is not None:
            for _, r in t.iterrows():
                # mark the trade's excursion into the path, then settle at its net
                a, b = int(r.entry_bar), int(r.exit_bar)
                eq[a:b + 1] += np.linspace(0, r.net, max(1, b - a + 1))
                eq[b + 1:] += r.net
        eq = eq * scale
        step = max(1, n_bars // 100)
        marks = tuple(float(x) for x in eq[::step]) + (float(eq[-1]),)
        out.append(TwinDay(day=day, pnl=float(eq[-1]), path=marks,
                           traded=t is not None))
    return out


def run_twin(days, n_paths: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = len(days)
    passed = breached = 0
    d2p, dds, survive20 = [], [], 0
    for _ in range(n_paths):
        idx = []
        while len(idx) < 120:
            s = int(rng.integers(0, n))
            idx.extend((s + k) % n for k in range(10))
        idx = idx[:120]
        seq = [TwinDay(day=dt.date(2025, 1, 1) + dt.timedelta(days=k), pnl=days[i].pnl,
                       path=days[i].path, traded=days[i].traded)
               for k, i in enumerate(idx)]
        res = TopstepTwin(50_000, strict_path=True, allow_unverified_target=True).run(seq)
        if res.combine_days is not None:
            passed += 1
            d2p.append(res.combine_days)
        if res.breach_day is not None:
            breached += 1
        else:
            survive20 += 1
        eq = np.cumsum([d.pnl for d in seq])
        dds.append(float((eq - np.maximum.accumulate(eq)).min()))
        if res.breach_day is None or res.days > 20:
            pass
    return {"pass_rate": passed / n_paths, "breach_rate": breached / n_paths,
            "survive_20d": survive20 / n_paths,
            "median_days_to_target": float(np.median(d2p)) if d2p else np.nan,
            "max_intraday_dd": float(np.mean(dds)),
            "worst1pct_dd": float(np.percentile(dds, 1))}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(70707)
    sessions, feats, strat = load(PASSING[1])
    s = strat[PASSING[0]]
    n_train = int(len(sessions) * SPLIT)
    te_sess, te_f = sessions[n_train:], feats[n_train:]

    base = X.ExitArchitecture("F.baseline_invalidation", use_invalidation=True)
    t_all = run_arch(sessions, feats, s, PASSING[1], base)
    t_oos = run_arch(te_sess, te_f, s, PASSING[1], base)
    med_bars = int(max(1, t_all.bars_held.median()))

    print("=" * 108)
    print("PHASE 8 - SLIPPAGE LADDER (baseline architecture, which is the best surviving one)")
    print("=" * 108)
    print(f"  {'slippage':>10} {'full $/tr':>11} {'OOS $/tr':>10} {'full net':>10} "
          f"{'OOS net':>9}")
    slip_rows = []
    for slip in (0.0, 0.5, 1.0, 2.0):
        a = stats(run_arch(sessions, feats, s, PASSING[1], base, slip_ticks=slip))
        b = stats(run_arch(te_sess, te_f, s, PASSING[1], base, slip_ticks=slip))
        slip_rows.append({"slip_ticks": slip, "full_per_trade": a["per_trade"],
                          "oos_per_trade": b["per_trade"], "full_net": a["net"],
                          "oos_net": b["net"]})
        print(f"  {slip:10.2f} {a['per_trade']:11.2f} {b['per_trade']:10.2f} "
              f"{a['net']:10.0f} {b['net']:9.0f}")
    sl = pd.DataFrame(slip_rows)
    tick = inst.get(PASSING[1]).spec.tick_value
    f0, f1 = sl.full_per_trade.iloc[0], sl.full_per_trade.iloc[2]
    be = f0 / max(1e-9, f0 - f1)
    print(f"\n  one MNQ tick = ${tick:.2f}")
    print(f"  break-even slippage, full sample : {be:.2f} ticks (${be * tick:.2f})")
    o0, o1 = sl.oos_per_trade.iloc[0], sl.oos_per_trade.iloc[2]
    beo = o0 / max(1e-9, o0 - o1)
    print(f"  break-even slippage, OUT OF SAMPLE: {beo:.2f} ticks (${beo * tick:.2f})")
    sl.to_csv(REPO / "research" / "exit_slippage.csv", index=False)

    print("\n" + "=" * 108)
    print("PHASE 11 - RANDOM EXIT CONTROLS")
    print(f"{N_RANDOM} replications each, full sample, commission only")
    print("=" * 108)
    real = stats(t_all)["per_trade"]
    ctl_rows = []
    for mode in ("random_stop_target", "random_timing", "fixed_hold", "random_entry"):
        reps = 1 if mode == "fixed_hold" else N_RANDOM
        vals = np.array([random_control(sessions, feats, s, PASSING[1], rng, mode, med_bars)
                         for _ in range(reps)])
        vals = vals[np.isfinite(vals)]
        pct = float((vals < real).mean()) if len(vals) > 1 else np.nan
        ctl_rows.append({"control": mode, "median": float(np.median(vals)),
                         "p95": float(np.percentile(vals, 95)) if len(vals) > 1 else np.nan,
                         "real": real, "pctile": pct})
        print(f"  {mode:20} median ${np.median(vals):7.2f}/trade   "
              f"real ${real:6.2f}   "
              + (f"percentile {pct:5.1%}" if np.isfinite(pct) else "single value"))
    pd.DataFrame(ctl_rows).to_csv(REPO / "research" / "exit_controls.csv", index=False)
    print(f"\n  median holding time used by the timing controls: {med_bars} bar(s)")

    print("\n" + "=" * 108)
    print("PHASE 7 - TOPSTEP ECONOMICS, baseline architecture")
    print("=" * 108)
    rows = []
    for size in (1, 5, 10, 20, 50):
        days = to_twin(t_all, sessions, float(size))
        tw = run_twin(days, 400, seed=1234 + size)
        dll = float(np.mean([min(d.path) <= -DLL for d in days if d.path]))
        rows.append({"contracts": size, "dll_breach_rate": dll, **tw})
        print(f"  {size:3d} contracts   pass {tw['pass_rate']:6.1%}   "
              f"breach {tw['breach_rate']:6.1%}   survive-20d {tw['survive_20d']:6.1%}   "
              f"median days {tw['median_days_to_target'] if np.isfinite(tw['median_days_to_target']) else float('nan'):6.0f}   "
              f"DLL/session {dll:5.1%}   worst-1% DD ${tw['worst1pct_dd']:,.0f}")
    pd.DataFrame(rows).to_csv(REPO / "research" / "exit_topstep.csv", index=False)

    # ---------------- Phase 15: the plots that matter -----------------------------------
    print("\n" + "=" * 108)
    print("PHASE 15 - PLOTS")
    print("=" * 108)
    grid = pd.read_csv(REPO / "research" / "exit_grid.csv")

    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    ax.scatter(t_all.mae, t_all.mfe, s=16, alpha=0.55,
               c=np.where(t_all.net > 0, "#22543d", "#9b2c2c"))
    lim = max(abs(t_all.mae.min()), t_all.mfe.max())
    ax.plot([-lim, 0], [0, lim], color="grey", ls=":", lw=1)
    ax.set_xlabel("MAE per trade, $ (worse to the left)")
    ax.set_ylabel("MFE per trade, $")
    ax.set_title("MFE vs MAE — the payoff geometry an exit would have to exploit\n"
                 f"mean ratio {abs(t_all.mfe.mean() / t_all.mae.mean()):.2f}; the dotted line "
                 f"is symmetry", fontsize=10)
    fig.tight_layout(); fig.savefig(OUT / "01_mfe_mae_scatter.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    ax.scatter(grid.is_per_trade, grid.oos_per_trade, s=34, alpha=0.8, color="#2b6cb0")
    for _, r in grid.iterrows():
        if r.is_per_trade > 2 or r.oos_per_trade > 4:
            ax.annotate(r["arch"], (r.is_per_trade, r.oos_per_trade), fontsize=6.5,
                        xytext=(3, 3), textcoords="offset points")
    ax.axhline(0, color="black", lw=0.8); ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("in-sample $/trade (where the architecture was chosen)")
    ax.set_ylabel("out-of-sample $/trade (the truth)")
    ax.set_title(f"41 preregistered exit architectures: selection carries no information\n"
                 f"rank correlation {grid[['is_per_trade', 'oos_per_trade']].corr().iloc[0, 1]:+.3f}",
                 fontsize=10)
    fig.tight_layout(); fig.savefig(OUT / "02_is_vs_oos.png"); plt.close(fig)

    a = grid[grid.arch.str.startswith("A.")].copy()
    a["stop"] = a.arch.str.extract(r"stop([\d.]+)atr").astype(float)
    a["tgt"] = a.arch.str.extract(r"tgt([\d.]+)R").astype(float)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0))
    for ax, col, ttl in zip(axes, ["is_per_trade", "oos_per_trade"],
                            ["in-sample $/trade", "out-of-sample $/trade"], strict=True):
        piv = a.pivot_table(index="stop", columns="tgt", values=col)
        v = np.nanmax(np.abs(piv.to_numpy()))
        im = ax.imshow(piv.to_numpy(), cmap="RdYlGn", vmin=-v, vmax=v, aspect="auto")
        ax.set_xticks(range(len(piv.columns)))
        ax.set_xticklabels([f"{c:g}R" for c in piv.columns])
        ax.set_yticks(range(len(piv.index)))
        ax.set_yticklabels([f"{i:g}atr" for i in piv.index])
        for i in range(piv.shape[0]):
            for j in range(piv.shape[1]):
                ax.text(j, i, f"{piv.to_numpy()[i, j]:.1f}", ha="center", va="center",
                        fontsize=7.5)
        ax.set_title(ttl, fontsize=9); ax.grid(False)
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle("Parameter surface: the in-sample plateau at 1.25 ATR is the WORST "
                 "out-of-sample row", fontsize=10)
    fig.tight_layout(); fig.savefig(OUT / "03_parameter_surface.png"); plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
    axes[0].hist(t_all.bars_held.clip(0, 30), bins=30, color="#4a5568")
    axes[0].set_title(f"holding time (median {med_bars} bar)", fontsize=9)
    axes[1].plot(sl.slip_ticks, sl.full_per_trade, marker="o", label="full sample")
    axes[1].plot(sl.slip_ticks, sl.oos_per_trade, marker="s", label="out of sample")
    axes[1].axhline(0, color="crimson", lw=1.2)
    axes[1].set_xlabel("round-turn slippage, ticks"); axes[1].set_ylabel("$/trade")
    axes[1].legend(fontsize=7, frameon=False)
    axes[1].set_title("slippage sensitivity", fontsize=9)
    daily = t_all.groupby("session")["net"].sum()
    axes[2].hist(daily, bins=30, color="#2b6cb0")
    axes[2].axvline(0, color="black", lw=0.9)
    axes[2].set_title(f"daily P&L (mean ${daily.mean():.2f})", fontsize=9)
    fig.suptitle(f"{PASSING[0]} {PASSING[1]} — baseline exit", fontsize=10)
    fig.tight_layout(); fig.savefig(OUT / "04_diagnostics.png"); plt.close(fig)

    eq = np.cumsum(daily.to_numpy())
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.6, 5.2), sharex=True,
                                 gridspec_kw={"height_ratios": [2, 1]})
    xd = pd.to_datetime(daily.index)
    a1.plot(xd, eq, lw=1.3, color="#22543d")
    a1.axvline(xd[int(len(xd) * SPLIT)], color="grey", ls="--", lw=1)
    a1.text(xd[int(len(xd) * SPLIT)], eq.max() * 0.9, " OOS begins", fontsize=8, color="grey")
    a1.axhline(0, color="black", lw=0.8); a1.set_ylabel("cumulative net $")
    a1.set_title("Equity, 1 contract, commission only", fontsize=10)
    ddv = eq - np.maximum.accumulate(eq)
    a2.fill_between(xd, ddv, 0, alpha=0.4, color="#9b2c2c")
    a2.axhline(-MLL, color="crimson", ls="--", lw=1.2)
    a2.text(xd[len(xd) // 3], -MLL * 0.9, "$2,000 MLL", color="crimson", fontsize=8)
    a2.set_ylabel("drawdown $")
    fig.autofmt_xdate(); fig.tight_layout()
    fig.savefig(OUT / "05_equity.png"); plt.close(fig)

    for p in sorted(OUT.glob("*.png")):
        print(f"  wrote {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
