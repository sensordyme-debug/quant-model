"""A broad strategy tournament for the Topstep $50K Combine, on real futures data.

WHY THIS EXISTS, AND WHAT IT REPLACES
-------------------------------------
The previous funnel ran 817 hypotheses from one family: `feature > threshold`, with absolute
thresholds against a feature library scaled in returns. Measured on the real ES store, 104 of
its 136 cells collapse to a constant position, so three quarters of that search was
buy-and-hold with a sign. It also predates four engine fixes. Nothing in
`research/experiments_futures.jsonl` is evidence about a strategy.

This module is the replacement search. Two things are different and both matter:

**The strategies are mechanisms, not a grid.** Seven families with genuinely different
theories of why a price moves, so a null result means something. A grid of one mechanism
answering "no" tells you about the mechanism; seven families answering "no" starts to tell
you about the market.

**Positions are three-state.** `{-1, 0, +1}`, where 0 means flat and out. The old grid's
`np.where(cond, 1, -1)` was always in the market by construction, which is both unrealistic
for a Combine and the direct cause of the degeneracy. Being flat is a position.

WHAT THIS DOES NOT DO
---------------------
It does not optimise. Each family has a small, fixed, pre-declared parameter set chosen for
coverage rather than performance, and the whole set is declared before any of it runs. There
is no loop that tries values until one works, because that loop is how the last search
produced 41 "passing" verdicts of which 40 had negative t.

It runs through `scripts/futures_discover.evaluator`, deliberately, rather than a new engine.
That is where the round-turn count including the bell flatten lives, the cost charged at the
trading bar, the fill-convention reporting, the leakage canary and the degeneracy filter. A
second engine would be a second set of those bugs.

THE HONEST CONSTRAINT
---------------------
Measured per-session P&L standard deviation of a one-lot always-in rule is $222.7 on MES over
261 sessions. Against that, the power to detect a genuine $20-per-session edge at a
multiplicity-corrected bar is a few per cent. **This dataset cannot confirm a small edge.** It
can reject a large claimed one, and it can rank candidates for a decision that is made
elsewhere. Any result here that looks strong is more likely a survivor of selection than a
discovery, which is what the splits and the multiplicity accounting are for.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import futures_discover as fd  # noqa: E402
from quant_brain.markets.futures_cme import features as fe  # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst  # noqa: E402
from quant_brain.markets.futures_cme import twin as tw  # noqa: E402

#: Price source -> the contract actually sized. A $50K Combine with a $2,000 limit cannot
#: carry an ES point ($50), so the grid is priced on the parent series and sized in the micro.
TRADED = {"ES": "MES", "NQ": "MNQ", "MES": "MES", "MNQ": "MNQ"}

#: Temporal, in order, no shuffling. The holdout is carved here and never read by any ranking
#: in this module - `evaluate_split` refuses to touch it unless explicitly asked, and the
#: report records whether it was ever spent.
SPLITS = (("train", 0.50), ("validation", 0.25), ("test", 0.15), ("holdout", 0.10))


# =====================================================================================
# STRATEGY FAMILIES
# =====================================================================================
# Every signal returns a position in {-1, 0, +1} per bar, computed from the feature frame
# ONLY. The frame is built per session by the causal library, so a signal cannot see across
# a session boundary and cannot see the future within one - `fe.audit_causality` is run over
# the library by `build_features` before any of this executes.

@dataclass(frozen=True)
class Calibration:
    """Feature thresholds, as quantiles measured on the TRAIN split of ONE symbol.

    WHY QUANTILES AND NOT NUMBERS
    A first pass at this module hard-coded thresholds by eye. Measured against the real ES
    train split, four of them never fired: `vwap_dist` has a p80 of 0.0018 and the threshold
    written was 0.15, about a hundred times too large. Two more fired on three quarters of
    all bars, because `opening_range_pos` has a p80 of 1.39 and the "breakout" level written
    was 0.9. A mechanism that never triggers and a mechanism that is always on are both
    untested, and both look like a tested mechanism in a results table.

    So the levels are expressed where they belong, in the feature's own distribution, and the
    distribution is measured on the TRAIN SPLIT ONLY and then frozen. Validation, test and
    holdout all use the train numbers. That is a fit - a small one, seventeen features by a
    handful of quantiles - and it is disclosed rather than hidden, which is the difference
    between a calibration and a peek.

    The quantile LEVELS below are declared in advance and are not tuned: they are the
    conventional 80/90/95 and their mirrors, chosen for coverage of "somewhat extreme" to
    "rare" and applied identically to every feature and every symbol.
    """

    q: dict[tuple[str, float], float]
    symbol: str = ""
    sessions: int = 0

    def __call__(self, feature: str, quantile: float) -> float:
        v = self.q.get((feature, quantile))
        if v is None or not np.isfinite(v):
            # Fail closed: a threshold that cannot be measured becomes unreachable, so the
            # strategy sits flat rather than firing on a default that means nothing.
            return float("inf") if quantile >= 0.5 else float("-inf")
        return float(v)


#: Declared before any data is read.
QUANTILES = (0.05, 0.10, 0.20, 0.50, 0.80, 0.90, 0.95)


def calibrate(train_feats: list, symbol: str) -> Calibration:
    X = pd.concat(train_feats, ignore_index=True)
    q: dict[tuple[str, float], float] = {}
    for c in X.columns:
        v = pd.to_numeric(X[c], errors="coerce").to_numpy(dtype=float)
        v = v[np.isfinite(v)]
        if v.size < 100:
            continue
        for lvl in QUANTILES:
            q[(c, lvl)] = float(np.percentile(v, lvl * 100))
    return Calibration(q=q, symbol=symbol, sessions=len(train_feats))


def _flat(n: int) -> np.ndarray:
    return np.zeros(n, dtype=float)


def _col(X, name: str) -> np.ndarray:
    return np.nan_to_num(np.asarray(X[name], dtype=float), nan=0.0)


def _state(cond_long, cond_short) -> np.ndarray:
    """Three-state position. Flat unless one side is true; flat if somehow both are."""
    pos = np.zeros(len(cond_long), dtype=float)
    pos[cond_long & ~cond_short] = 1.0
    pos[cond_short & ~cond_long] = -1.0
    return pos


@dataclass(frozen=True)
class Strategy:
    """One testable mechanism. `family` is what multiplicity is counted over."""

    name: str
    family: str
    params: dict
    signal: object

    def experiment(self, extra: dict | None = None):
        from quant_brain.research.search import Experiment
        return Experiment(hypothesis=self.name, family=self.family,
                          params={**self.params, **(extra or {})})


def _s(name, family, params, fn) -> Strategy:
    return Strategy(name=name, family=family, params=params, signal=fn)


# ---- FAMILY A: trend / momentum ------------------------------------------------------
# Theory: a move that is large in its own recent units continues. The z-gate is what makes
# this volatility-adjusted; a raw return threshold is the thing that made the old grid
# degenerate, because a fixed number against a return-scaled feature either never binds or
# always does.

def family_trend(cal: Calibration) -> list[Strategy]:
    out = []
    for h in ("ret_15", "ret_30", "ret_60"):
        for ql in (0.80, 0.90):
            hi, lo = cal("z_60", ql), cal("z_60", round(1 - ql, 2))

            def fn(X, h=h, hi=hi, lo=lo):
                z, m = _col(X, "z_60"), _col(X, h)
                return _state((m > 0) & (z > hi), (m < 0) & (z < lo))
            out.append(_s(f"trend.{h}.q{int(ql * 100)}", "A.trend",
                          {"horizon": h, "z_quantile": ql, "z_hi": hi, "z_lo": lo}, fn))

    def ma_agree(X):
        f, sl = _col(X, "ma_dist_30"), _col(X, "ma_dist_120")
        return _state((f > 0) & (sl > 0), (f < 0) & (sl < 0))
    out.append(_s("trend.ma_agree.30_120", "A.trend", {}, ma_agree))

    def multi(X):
        a1, b1, c1 = _col(X, "ret_15"), _col(X, "ret_30"), _col(X, "ret_60")
        return _state((a1 > 0) & (b1 > 0) & (c1 > 0), (a1 < 0) & (b1 < 0) & (c1 < 0))
    out.append(_s("trend.multi_horizon_agree", "A.trend", {}, multi))

    def accel(X):
        ac, r = _col(X, "accel_30"), _col(X, "ret_30")
        return _state((ac > 0) & (r > 0), (ac < 0) & (r < 0))
    out.append(_s("trend.accel_confirm", "A.trend", {}, accel))
    return out


# ---- FAMILY B: breakout ---------------------------------------------------------------
# Theory: price leaving an established range keeps going. Directly opposed to family C, which
# is why both are here: a market cannot reward both, and a search containing only one cannot
# tell you which way it leans.

def family_breakout(cal: Calibration) -> list[Strategy]:
    out = []
    for ql in (0.90, 0.95):
        hi, lo = cal("opening_range_pos", ql), cal("opening_range_pos", round(1 - ql, 2))

        def fn(X, hi=hi, lo=lo):
            orp, mins = _col(X, "opening_range_pos"), _col(X, "minutes_from_open")
            live = mins > 30                 # the range needs time to form before it breaks
            return _state(live & (orp >= hi), live & (orp <= lo))
        out.append(_s(f"breakout.opening_range.q{int(ql * 100)}", "B.breakout",
                      {"quantile": ql, "hi": hi, "lo": lo}, fn))

    for ql in (0.80, 0.90):
        rx = cal("range_expansion", ql)

        def fn2(X, rx=rx):
            r, m = _col(X, "range_expansion"), _col(X, "ret_15")
            return _state((r > rx) & (m > 0), (r > rx) & (m < 0))
        out.append(_s(f"breakout.range_expansion.q{int(ql * 100)}", "B.breakout",
                      {"quantile": ql, "level": rx}, fn2))

    hi95, lo05 = cal("opening_range_pos", 0.95), cal("opening_range_pos", 0.05)

    def failed(X, hi=hi95, lo=lo05):
        orp, mins = _col(X, "opening_range_pos"), _col(X, "minutes_from_open")
        live = mins > 45
        prev = np.concatenate(([0.0], orp[:-1]))
        return _state(live & (prev > hi) & (orp < hi), live & (prev < lo) & (orp > lo))
    out.append(_s("breakout.failed_reversal", "B.breakout", {"hi": hi95, "lo": lo05}, failed))

    quiet_lvl = cal("rvol_30", 0.20)

    def compress(X, q=quiet_lvl):
        rv, r = _col(X, "rvol_30"), _col(X, "ret_15")
        return _state((rv < q) & (r > 0), (rv < q) & (r < 0))
    out.append(_s("breakout.compression_expansion", "B.breakout",
                  {"quiet": quiet_lvl}, compress))
    return out


# ---- FAMILY C: mean reversion ----------------------------------------------------------
# Theory: an extreme move reverts. The direct opposite of family B.

def family_reversion(cal: Calibration) -> list[Strategy]:
    out = []
    for ql in (0.90, 0.95):
        hi, lo = cal("z_60", ql), cal("z_60", round(1 - ql, 2))

        def fn(X, hi=hi, lo=lo):
            z = _col(X, "z_60")
            return _state(z < lo, z > hi)                       # fade the extreme
        out.append(_s(f"revert.z_60.q{int(ql * 100)}", "C.reversion",
                      {"quantile": ql, "hi": hi, "lo": lo}, fn))

    for ql in (0.90, 0.95):
        hi, lo = cal("vwap_dist", ql), cal("vwap_dist", round(1 - ql, 2))

        def fn2(X, hi=hi, lo=lo):
            d = _col(X, "vwap_dist")
            return _state(d < lo, d > hi)
        out.append(_s(f"revert.vwap.q{int(ql * 100)}", "C.reversion",
                      {"quantile": ql, "hi": hi, "lo": lo}, fn2))

    zhi, zlo = cal("z_60", 0.95), cal("z_60", 0.05)
    calm = cal("range_expansion", 0.50)

    def calm_only(X, hi=zhi, lo=zlo, c=calm):
        z, rx = _col(X, "z_60"), _col(X, "range_expansion")
        # Fading a genuine regime change is how a reversion book dies, so the calm gate is
        # part of the mechanism rather than a filter bolted on afterwards.
        return _state((rx < c) & (z < lo), (rx < c) & (z > hi))
    out.append(_s("revert.z_calm_only", "C.reversion", {"calm_below": calm}, calm_only))
    return out


# ---- FAMILY D: session / time ------------------------------------------------------------
# Theory: the clock matters. Thresholds here are wall-clock minutes, which need no
# calibration because a minute is a minute in every symbol.

def family_session(cal: Calibration) -> list[Strategy]:
    out = []

    def late_cont(X):
        """PREREGISTERED. The audit found late-day FADE strongly negative, which makes
        late-day CONTINUATION the paired hypothesis worth stating in advance rather than
        discovering afterwards. It is one candidate among many and is not privileged."""
        mins, r = _col(X, "minutes_from_open"), _col(X, "ret_30")
        late = mins > 300
        return _state(late & (r > 0), late & (r < 0))
    out.append(_s("session.late_day_continuation", "D.session",
                  {"after_minutes": 300, "preregistered": True}, late_cont))

    def late_fade(X):
        mins, r = _col(X, "minutes_from_open"), _col(X, "ret_30")
        late = mins > 300
        return _state(late & (r < 0), late & (r > 0))
    out.append(_s("session.late_day_fade", "D.session", {"after_minutes": 300}, late_fade))

    def open_drive(X):
        mins, r = _col(X, "minutes_from_open"), _col(X, "ret_15")
        early = (mins > 15) & (mins < 90)
        return _state(early & (r > 0), early & (r < 0))
    out.append(_s("session.opening_drive", "D.session", {}, open_drive))

    zhi, zlo = cal("z_60", 0.90), cal("z_60", 0.10)

    def midday(X, hi=zhi, lo=zlo):
        mins, z = _col(X, "minutes_from_open"), _col(X, "z_60")
        mid = (mins > 120) & (mins < 270)
        return _state(mid & (z < lo), mid & (z > hi))
    out.append(_s("session.midday_reversion", "D.session", {}, midday))
    return out


# ---- FAMILY E: volatility -----------------------------------------------------------------
# Theory: the volatility regime decides which of B and C is right at a given moment. The
# rvol_30 against rvol_120 comparison is scale-free and needs no calibration.

def family_volatility(cal: Calibration) -> list[Strategy]:
    out = []

    def expand(X):
        rv, rvl, r = _col(X, "rvol_30"), _col(X, "rvol_120"), _col(X, "ret_30")
        return _state((rv > rvl) & (r > 0), (rv > rvl) & (r < 0))
    out.append(_s("vol.expansion_trend", "E.volatility", {}, expand))

    zhi, zlo = cal("z_60", 0.90), cal("z_60", 0.10)

    def contract(X, hi=zhi, lo=zlo):
        rv, rvl, z = _col(X, "rvol_30"), _col(X, "rvol_120"), _col(X, "z_60")
        return _state((rv < rvl) & (z < lo), (rv < rvl) & (z > hi))
    out.append(_s("vol.contraction_revert", "E.volatility", {}, contract))

    shock = cal("vol_of_vol", 0.90)

    def vov(X, sh=shock):
        v, r = _col(X, "vol_of_vol"), _col(X, "ret_30")
        return _state((v > sh) & (r > 0), (v > sh) & (r < 0))
    out.append(_s("vol.vol_of_vol_shock", "E.volatility", {"shock": shock}, vov))
    return out


# ---- FAMILY F: volume -----------------------------------------------------------------

def family_volume(cal: Calibration) -> list[Strategy]:
    out = []
    for ql in (0.80, 0.90):
        lvl = cal("rel_volume", ql)

        def fn(X, lvl=lvl):
            rv, r = _col(X, "rel_volume"), _col(X, "ret_15")
            return _state((rv > lvl) & (r > 0), (rv > lvl) & (r < 0))
        out.append(_s(f"volume.heavy_continuation.q{int(ql * 100)}", "F.volume",
                      {"quantile": ql, "level": lvl}, fn))

    va_lvl = cal("volume_accel", 0.90)
    zhi, zlo = cal("z_60", 0.90), cal("z_60", 0.10)

    def climax(X, va=va_lvl, hi=zhi, lo=zlo):
        v, z = _col(X, "volume_accel"), _col(X, "z_60")
        return _state((v > va) & (z < lo), (v > va) & (z > hi))
    out.append(_s("volume.climax_reversion", "F.volume", {"accel": va_lvl}, climax))
    return out


# ---- FAMILY G: microstructure ------------------------------------------------------------
# ONLY where real quote columns exist. Measured 2026-09-14: the bar stores
# (data/futures/<SYM>.parquet) carry t,o,h,l,c,v,contract and NO bid/ask, so the library does
# not build spread_bps or quote_imbalance and this family is empty on every symbol tonight.
# ES quotes exist in a SEPARATE file (ES_quotes.parquet) and joining them is a real piece of
# work, not a one-liner. Returning an empty list is the honest outcome: a family of
# always-flat strategies would appear in the results table as tested and rejected, which is a
# lie about what was tested. Family G is recorded as NOT RUN.

def family_microstructure(cal: Calibration) -> list[Strategy]:
    return []


ALL_FAMILIES = (family_trend, family_breakout, family_reversion, family_session,
                family_volatility, family_volume, family_microstructure)


def inverse_of(strategy: Strategy) -> Strategy:
    """The exact sign flip of a strategy, as a first-class candidate.

    WHY THIS IS A SEPARATE TRIAL AND NOT A FREE LUNCH
    A strategy that loses significantly is not automatically a winner upside down. The same
    legs are traded either way, so the costs are paid twice over the round trip regardless:
    net = gross - costs becomes net_flip = -gross - costs. A mechanism has to lose MORE than
    twice its costs before its inverse makes money.

    It is included because the audit found the previous funnel produced 41 "passing" verdicts
    of which 40 had NEGATIVE t, and nobody ever tested whether flipping them worked. Now it
    is tested rather than assumed, and - this is the part that matters - it is COUNTED. Every
    inverse is a trial in the multiplicity denominator, which is why running them doubles the
    corrected bar from 3.53 to 3.71.
    """
    base = strategy.signal

    def flipped(X, _f=base):
        return -np.asarray(_f(X), dtype=float)
    return Strategy(name=f"INV::{strategy.name}", family=f"{strategy.family}.inverse",
                    params={**strategy.params, "inverse_of": strategy.name}, signal=flipped)


def build_strategies(cal: Calibration) -> list[Strategy]:
    out: list[Strategy] = []
    for f in ALL_FAMILIES:
        out.extend(f(cal))
    names = [s.name for s in out]
    assert len(names) == len(set(names)), "duplicate strategy name"
    return out


# =====================================================================================
# EVALUATION
# =====================================================================================

@dataclass
class SplitResult:
    split: str
    sessions: int
    trades: int
    gross: float
    costs: float
    net: float
    mean_per_session: float
    t_stat: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    best_day: float
    worst_day: float
    ceiling_share: float
    degenerate: bool
    blocked_by: str = ""
    p_pass_combine: float | None = None
    extras: dict = field(default_factory=dict)


def _stats(pnl: list[float]) -> dict:
    a = np.asarray(pnl, dtype=float)
    if a.size == 0:
        return {"t": 0.0, "win": 0.0, "pf": 0.0, "mdd": 0.0, "best": 0.0, "worst": 0.0}
    sd = float(a.std(ddof=1)) if a.size > 1 else 0.0
    t = float(a.mean() / (sd / np.sqrt(a.size))) if sd > 0 else 0.0
    wins, losses = a[a > 0].sum(), -a[a < 0].sum()
    equity = np.cumsum(a)
    peak = np.maximum.accumulate(equity)
    return {"t": t,
            "win": float((a > 0).mean()),
            "pf": float(wins / losses) if losses > 0 else float("inf") if wins > 0 else 0.0,
            "mdd": float((equity - peak).min()),
            "best": float(a.max()), "worst": float(a.min())}


def evaluate_split(strategy: Strategy, sessions, feats, *, split: str, symbol: str,
                   contracts: int, twin_obj) -> SplitResult:
    run = fd.evaluator(sessions, feats, contracts=contracts, twin_obj=twin_obj, symbol=symbol)
    out = run(strategy)
    pnl = out.get("pnl", [])
    st = _stats(pnl)
    blocked = ""
    for k, reason_key in (("degenerate", "degenerate_reason"), ("leakage_ok", "leakage_reason"),
                          ("cost_ok", "cost_reason"), ("topstep_ok", "topstep_reason"),
                          ("walkforward_ok", "walkforward_reason")):
        v = out.get(k)
        if (k == "degenerate" and v is True) or (k != "degenerate" and v is False):
            blocked = str(out.get(reason_key, k))
            break
    return SplitResult(
        split=split, sessions=int(out.get("sessions", 0)), trades=int(out.get("trades", 0)),
        gross=float(out.get("gross", 0.0)), costs=float(out.get("costs", 0.0)),
        net=float(np.sum(pnl)), mean_per_session=float(out.get("mean_per_session", 0.0)),
        t_stat=st["t"], win_rate=st["win"], profit_factor=st["pf"], max_drawdown=st["mdd"],
        best_day=st["best"], worst_day=st["worst"],
        ceiling_share=float(out.get("ceiling_share", 0.0)),
        degenerate=bool(out.get("degenerate", False)), blocked_by=blocked,
        p_pass_combine=out.get("p_pass_combine"),
        extras={"fill_subsidy": out.get("fill_subsidy"),
                "gross_next_open_fill": out.get("gross_next_open_fill")})


def split_indices(n: int) -> dict[str, tuple[int, int]]:
    """Temporal, contiguous, in order. No shuffling, no gaps, no overlap."""
    out, start = {}, 0
    for i, (name, frac) in enumerate(SPLITS):
        end = n if i == len(SPLITS) - 1 else start + int(round(n * frac))
        out[name] = (start, end)
        start = end
    return out


def load_symbol(source: str, *, quotes: bool = False):
    store = Path(f"data/futures/{source}.parquet")
    if not store.exists():
        return None, None
    df = fd.load(store, source)
    sessions = fd.session_frames(df)
    lib = fe.library()
    feats = fd.build_features(sessions, lib)
    return sessions, feats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["ES", "NQ", "MES", "MNQ"])
    ap.add_argument("--contracts", type=int, default=1)
    ap.add_argument("--profit-target", type=float, default=3_000.0)
    ap.add_argument("--out", type=Path, default=Path("research/tournament_2026_09_14.json"))
    ap.add_argument("--include-inverses", action="store_true",
                    help="also test the exact sign flip of every strategy. Doubles the "
                         "trial count and the multiplicity bar with it.")
    ap.add_argument("--spend-holdout", action="store_true",
                    help="read the final holdout. Doing this ONCE ends its status as "
                         "untouched; the report records that it happened.")
    args = ap.parse_args()

    results: list[dict] = []
    meta: dict = {}
    t0 = time.time()
    for source in args.symbols:
        sessions, feats = load_symbol(source)
        if sessions is None:
            print(f"{source}: no store, skipped")
            continue
        symbol = TRADED[source]
        idx = split_indices(len(sessions))
        ta, tb = idx["train"]
        cal = calibrate(feats[ta:tb], symbol)
        strategies = build_strategies(cal)
        if args.include_inverses:
            strategies = strategies + [inverse_of(x) for x in strategies]
        meta[source] = {"sessions": len(sessions), "traded": symbol,
                        "splits": {k: (b_ - a_) for k, (a_, b_) in idx.items()},
                        "calibrated_on_sessions": cal.sessions,
                        "n_strategies": len(strategies)}
        print(f"{source}: {len(sessions)} sessions -> {symbol}, "
              f"splits {{ {', '.join(f'{k}:{b_-a_}' for k, (a_, b_) in idx.items())} }}, "
              f"{len(strategies)} strategies calibrated on {cal.sessions} train sessions")

        for strat in strategies:
            row = {"symbol": source, "traded": symbol, "strategy": strat.name,
                   "family": strat.family, "params": strat.params, "splits": {}}
            for name, (a_, b_) in idx.items():
                if name == "holdout" and not args.spend_holdout:
                    row["splits"][name] = {"status": "UNTOUCHED"}
                    continue
                if b_ - a_ < 20:
                    row["splits"][name] = {"status": "TOO_SHORT", "sessions": b_ - a_}
                    continue
                # A FRESH twin per evaluation. `evaluate_twin` is not documented as pure
                # and a twin carrying state from a previous strategy would silently couple
                # results that must be independent. Cheap insurance against a whole table
                # being wrong in a way nobody could see from the numbers.
                r = evaluate_split(strat, sessions[a_:b_], feats[a_:b_], split=name,
                                   symbol=symbol, contracts=args.contracts,
                                   twin_obj=tw.TopstepTwin(50_000,
                                                           profit_target=args.profit_target))
                row["splits"][name] = r.__dict__
            results.append(row)
        print(f"  scored  [{time.time() - t0:.0f}s]")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": pd.Timestamp.utcnow().isoformat(),
        "engine": "scripts/futures_discover.py evaluator (post-fix)",
        "splits": dict(SPLITS),
        "holdout_spent": bool(args.spend_holdout),
        "contracts": args.contracts,
        "profit_target": args.profit_target,
        "calibration": "train-split quantiles, frozen, per symbol",
        "families_not_run": {"G.microstructure":
                             "bar stores carry no bid/ask; quotes are in a separate file"},
        "per_symbol": meta,
        "results": results,
    }
    args.out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(chr(10) + f"written to {args.out}  [{time.time() - t0:.0f}s total]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
