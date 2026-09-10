"""O-2: SPY 0DTE defined-risk credit spreads, priced at the quoted bid/ask.

The owner's 3-10%/day mandate asks for a high-win-rate instrument with intrinsic leverage.
A same-day-expiry vertical credit spread is the canonical one: risk is capped at the width,
the win rate is the short strike's probability of staying out of the money, and the position
is levered by the fact that the premium is a few percent of the risk.

This study asks whether that trade has any edge once every fill crosses the spread.

Method, fixed before the runs (the L-1 / X-1 two-stage discipline):

  * One session = one 0DTE expiration in `data/options/odte/SPY` (see scripts/odte_data.py),
    5-minute bid/ask for both rights, +/-30 strikes around the money.
  * At the entry snapshot the underlying is recovered by put-call parity from the strike whose
    call and put mids are closest (0DTE, so carry is negligible), and the risk-neutral
    probability of finishing in the money is read off the chain itself as dP/dK for puts and
    -dC/dK for calls - no volatility model, no external data, and by construction the same
    number the market is quoting.
  * Short strike = the strike whose prob-ITM is closest to `--target`; long strike = `--width`
    percent of spot further out, snapped to the strike grid.
  * ENTRY fills sell the short leg at the **bid** and buy the long leg at the **ask**.
    EXIT fills buy the short leg at the **ask** and sell the long leg at the **bid**.
    The mid is only ever used as a *diagnostic* (`gross`), never as a fill.
  * Commission `--fee` dollars per contract per transaction, on every leg of both sides.
  * The decision statistic is the per-session **return on risk** - P&L divided by the position's
    own maximum loss - so a book that risks a fixed fraction of equity per day earns
    `risk_frac x ror`, and the sessions of 2016 and 2026 are directly comparable.

Verdict rule, also fixed before the runs: net of costs, mean return on risk must be positive
with t > 2 in at least two of the three a-priori regimes (2016-2019, 2020-2023, 2024-2026).

    python scripts/sweep_o2.py --grid
    python scripts/sweep_o2.py --structure put --target 0.16 --entry 10:00 --detail
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import odte_data  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REGIMES = [("2016-2019", "2016-01-01", "2019-12-31"),
           ("2020-2023", "2020-01-01", "2023-12-31"),
           ("2024-2026", "2024-01-01", "2026-12-31")]


# ------------------------------------------------------------------ chain helpers
class Chain:
    """One stored 0DTE session as dense [time, strike] bid/ask grids.

    Theta returns every strike at every interval, so the strike axis is constant through the
    day and the whole session is four 2-D arrays. `t`/`k` index them.
    """

    __slots__ = ("date", "times", "hhmm", "strikes", "cb", "ca", "pb", "pa",
                 "_ok", "_sell", "_buy", "_spot")

    def __init__(self, df: pd.DataFrame):
        piv = df.pivot_table(index="timestamp", columns=["right", "strike"],
                             values=["bid", "ask"], aggfunc="last").sort_index()
        self.times = piv.index.to_numpy()
        self.hhmm = np.array([pd.Timestamp(t).strftime("%H:%M") for t in self.times])
        self.date = pd.Timestamp(self.times[0]).date()
        cols = piv.columns
        ks = sorted({float(c[2]) for c in cols})
        self.strikes = np.asarray(ks, dtype=float)
        n_t, n_k = len(self.times), len(self.strikes)
        idx = {k: i for i, k in enumerate(self.strikes)}
        grids = {("bid", "C"): np.full((n_t, n_k), np.nan), ("ask", "C"): np.full((n_t, n_k), np.nan),
                 ("bid", "P"): np.full((n_t, n_k), np.nan), ("ask", "P"): np.full((n_t, n_k), np.nan)}
        for c in cols:
            v, r, k = c[0], str(c[1])[0], float(c[2])
            key = (v, r)
            if key in grids:
                grids[key][:, idx[k]] = piv[c].to_numpy(dtype=float)
        self.cb, self.ca = grids[("bid", "C")], grids[("ask", "C")]
        self.pb, self.pa = grids[("bid", "P")], grids[("ask", "P")]
        # parity needs both rights two-sided; a single leg only needs its own right quotable,
        # sellable (bid > 0) for the short leg and buyable (ask > 0) for the long leg.
        self._ok = (self.cb > 0) & (self.ca >= self.cb) & (self.pb > 0) & (self.pa >= self.pb)
        self._sell = {"C": (self.cb > 0) & (self.ca >= self.cb), "P": (self.pb > 0) & (self.pa >= self.pb)}
        self._buy = {"C": (self.ca > 0) & (self.ca >= self.cb), "P": (self.pa > 0) & (self.pa >= self.pb)}
        self._spot: dict[int, float] = {}

    # --- per-timestamp views -------------------------------------------------
    def cm(self, t: int) -> np.ndarray:
        return (self.cb[t] + self.ca[t]) / 2.0

    def pm(self, t: int) -> np.ndarray:
        return (self.pb[t] + self.pa[t]) / 2.0

    def valid(self, t: int) -> np.ndarray:
        return self._ok[t]

    def sellable(self, t: int, right: str) -> np.ndarray:
        return self._sell[right][t]

    def buyable(self, t: int, right: str) -> np.ndarray:
        return self._buy[right][t]

    def spot(self, t: int) -> float:
        """Put-call parity on the strike where |C - P| is smallest (0DTE: carry ~ 0)."""
        if t in self._spot:
            return self._spot[t]
        ok = self._ok[t]
        if not ok.any():
            self._spot[t] = float("nan")
            return self._spot[t]
        cm, pm = self.cm(t), self.pm(t)
        diff = np.where(ok, np.abs(cm - pm), np.inf)
        i = int(np.argmin(diff))
        self._spot[t] = float(self.strikes[i] + cm[i] - pm[i])
        return self._spot[t]

    def prob_itm(self, t: int) -> tuple[np.ndarray, np.ndarray]:
        """(put, call) risk-neutral prob of finishing ITM, from the chain's own slope."""
        with np.errstate(invalid="ignore"):
            pp = np.gradient(self.pm(t), self.strikes)
            pc = -np.gradient(self.cm(t), self.strikes)
        return np.clip(pp, 0.0, 1.0), np.clip(pc, 0.0, 1.0)

    def kidx(self, k: float) -> int:
        i = int(np.searchsorted(self.strikes, k))
        return i if i < len(self.strikes) and abs(self.strikes[i] - k) < 1e-6 else -1

    def at_or_after(self, hhmm: str) -> int:
        w = np.flatnonzero(self.hhmm >= hhmm)
        return int(w[0]) if len(w) else -1

    def before_or_at(self, hhmm: str) -> int:
        w = np.flatnonzero(self.hhmm <= hhmm)
        return int(w[-1]) if len(w) else -1


def pick_strike(strikes: np.ndarray, prob: np.ndarray, ok: np.ndarray,
                target: float, side: str, spot: float) -> float:
    """The OTM strike whose prob-ITM is closest to the target."""
    otm = (strikes < spot) if side == "P" else (strikes > spot)
    m = ok & otm & np.isfinite(prob)
    if not m.any():
        return float("nan")
    d = np.where(m, np.abs(prob - target), np.inf)
    return float(strikes[int(np.argmin(d))])


def snap_long(strikes: np.ndarray, ok: np.ndarray, short_k: float, width: float, side: str) -> float:
    """The furthest-out usable strike at or beyond `width` dollars from the short strike."""
    if side == "P":
        cand = strikes[ok & (strikes <= short_k - width)]
        return float(cand.max()) if len(cand) else float("nan")
    cand = strikes[ok & (strikes >= short_k + width)]
    return float(cand.min()) if len(cand) else float("nan")


# ------------------------------------------------------------------ one session
@dataclass
class Cfg:
    structure: str = "put"      # put | call | condor
    target: float = 0.16        # prob-ITM of the short strike
    width_pct: float = 0.0075   # spread width as a fraction of spot
    entry: str = "10:00"
    exit: str = "15:50"
    stop_mult: float = 0.0      # 0 = no stop; else exit when spread mid >= stop_mult x credit
    fee: float = 0.75           # $ per contract per transaction
    fill_lag: int = 0           # bars between the decision snapshot and the fill snapshot
    expire_otm: bool = False    # let an untouched position expire instead of paying to close it
    pin_buffer: float = 0.0     # only expire when the close is this far (frac of spot) past the short strike


def run_session(ch: Chain, cfg: Cfg) -> dict | None:
    i_dec = ch.at_or_after(cfg.entry)
    i_end = ch.before_or_at(cfg.exit)
    if i_dec < 0 or i_end < 0:
        return None
    i_fill = i_dec + cfg.fill_lag
    if i_fill > i_end:
        return None

    spot = ch.spot(i_dec)
    if not np.isfinite(spot):
        return None
    pp, pc = ch.prob_itm(i_dec)
    width = max(cfg.width_pct * spot, 0.0)

    sides = {"put": ["P"], "call": ["C"], "condor": ["P", "C"]}[cfg.structure]
    legs = []
    for side in sides:
        prob = pp if side == "P" else pc
        ks = pick_strike(ch.strikes, prob, ch.sellable(i_dec, side), cfg.target, side, spot)
        if not np.isfinite(ks):
            return None
        kl = snap_long(ch.strikes, ch.buyable(i_dec, side), ks, width, side)
        if not np.isfinite(kl):
            return None
        js, jl = ch.kidx(ks), ch.kidx(kl)
        if js < 0 or jl < 0:
            return None
        b, a = (ch.pb, ch.pa) if side == "P" else (ch.cb, ch.ca)
        sb, sa, lb, la = b[i_fill, js], a[i_fill, js], b[i_fill, jl], a[i_fill, jl]
        if not all(np.isfinite(x) for x in (sb, sa, lb, la)) or sb <= 0 or sa < sb or la < lb:
            return None
        legs.append({"side": side, "js": js, "jl": jl, "w": abs(ks - kl), "b": b, "a": a,
                     "credit": sb - la, "credit_mid": (sb + sa) / 2 - (lb + la) / 2,
                     "prob": float(prob[js])})

    credit = sum(l["credit"] for l in legs)
    credit_mid = sum(l["credit_mid"] for l in legs)
    if credit <= 0:
        return None
    # An iron condor can only lose on one side, so its risk is the wider wing less the credit.
    max_w = max(l["w"] for l in legs)
    risk = max_w * 100 - credit * 100
    if risk <= 0:
        return None

    # cost to close the whole position at each timestamp, executable and at the mid
    n_t = len(ch.times)
    close_x = np.zeros(n_t)
    close_m = np.zeros(n_t)
    for l in legs:
        b, a, js, jl = l["b"], l["a"], l["js"], l["jl"]
        close_x += a[:, js] - b[:, jl]
        close_m += (b[:, js] + a[:, js]) / 2 - (b[:, jl] + a[:, jl]) / 2

    i_stop = -1
    if cfg.stop_mult > 0 and credit_mid > 0:
        seg = close_m[i_fill + 1:i_end + 1]
        hit = np.flatnonzero(np.isfinite(seg) & (seg >= cfg.stop_mult * credit_mid))
        if len(hit):
            i_stop = i_fill + 1 + int(hit[0])
    i_close = i_stop if i_stop >= 0 else i_end
    debit, debit_mid = close_x[i_close], close_m[i_close]
    if not np.isfinite(debit):
        return None
    debit = max(float(debit), 0.0)

    spot_end = ch.spot(i_end)
    breach = 0
    if np.isfinite(spot_end):
        for l in legs:
            k = ch.strikes[l["js"]]
            if (l["side"] == "P" and spot_end < k) or (l["side"] == "C" and spot_end > k):
                breach = 1

    # distance from the closing print to the nearest short strike, as a fraction of spot -
    # the exposure the 'let it expire' branch is taking on (SPY settles on the official close
    # and can be exercised against until 17:30 ET, so a near-miss is not a free expiry).
    pin = float("nan")
    if np.isfinite(spot_end) and spot_end > 0:
        pin = min(abs(spot_end - ch.strikes[l["js"]]) for l in legs) / spot_end

    n_close_legs = 2 * len(legs)
    if (cfg.expire_otm and i_stop < 0 and breach == 0 and np.isfinite(spot_end)
            and (cfg.pin_buffer <= 0 or (np.isfinite(pin) and pin > cfg.pin_buffer))):
        # Nothing is in the money at the bell, so the book lets it expire: no closing spread,
        # no closing commission. A breached position is still bought back at the quote, because
        # taking assignment on the short leg means carrying SPY overnight.
        debit = debit_mid = 0.0
        n_close_legs = 0

    fees = cfg.fee * (2 * len(legs) + n_close_legs)
    pnl = (credit - debit) * 100 - fees
    pnl_gross = (credit_mid - max(float(debit_mid), 0.0)) * 100
    return {
        "date": str(ch.date), "spot": spot, "spot_end": spot_end, "width": max_w,
        "credit": credit, "credit_mid": credit_mid, "debit": debit, "debit_mid": float(debit_mid),
        "risk": risk, "pnl": pnl, "pnl_gross": pnl_gross,
        "ror": pnl / risk, "ror_gross": pnl_gross / risk,
        "stopped": int(i_stop >= 0), "prob": float(np.mean([l["prob"] for l in legs])),
        "breach": breach, "fees": fees, "pin": pin, "expired": int(n_close_legs == 0),
        "k_short": float(ch.strikes[legs[0]["js"]]),
        "spread_cost": (credit_mid - credit) * 100 + (debit - max(float(debit_mid), 0.0)) * 100,
    }


# ------------------------------------------------------------------ study
def run_cells(cfgs: list[Cfg], symbol: str = "SPY", dates: list[str] | None = None,
              progress: int = 0) -> list[pd.DataFrame]:
    """Every cell over every stored session, parsing each session exactly once."""
    dates = dates or odte_data.stored_dates(symbol)
    rows: list[list[dict]] = [[] for _ in cfgs]
    for n, d in enumerate(dates, 1):
        day = odte_data.load_day(symbol, d)
        if day.empty:
            continue
        try:
            ch = Chain(day)
        except Exception:  # noqa: BLE001 - a malformed stored day is not a result
            continue
        for i, cfg in enumerate(cfgs):
            r = run_session(ch, cfg)
            if r:
                rows[i].append(r)
        if progress and n % progress == 0:
            print(f"  {n}/{len(dates)} sessions", flush=True)
    return [pd.DataFrame(r) for r in rows]


def run_study(cfg: Cfg, symbol: str = "SPY", dates: list[str] | None = None) -> pd.DataFrame:
    return run_cells([cfg], symbol, dates)[0]


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for name, s, e in REGIMES + [("all", "1900-01-01", "2100-01-01")]:
        sub = df[(df.date >= s) & (df.date <= e)]
        if sub.empty:
            continue
        n = len(sub)
        r = sub.ror.to_numpy()
        t = r.mean() / (r.std(ddof=1) / np.sqrt(n)) if n > 1 and r.std(ddof=1) > 0 else np.nan
        g = sub.ror_gross.to_numpy()
        tg = g.mean() / (g.std(ddof=1) / np.sqrt(n)) if n > 1 and g.std(ddof=1) > 0 else np.nan
        out.append({"regime": name, "n": n,
                    "ror%": 100 * r.mean(), "t": t,
                    "gross%": 100 * g.mean(), "t_gross": tg,
                    "win%": 100 * (r > 0).mean(),
                    "worst%": 100 * r.min(), "best%": 100 * r.max(),
                    "cr/w": (sub.credit / sub.width).mean(),
                    "xcost%": 100 * (sub.spread_cost / sub.risk).mean(),
                    "stop%": 100 * sub.stopped.mean()})
    return pd.DataFrame(out)


def decompose(df: pd.DataFrame) -> pd.DataFrame:
    """Where the money goes, per regime, as a percentage of the position's own maximum loss."""
    out = []
    for name, s, e in REGIMES + [("all", "1900-01-01", "2100-01-01")]:
        sub = df[(df.date >= s) & (df.date <= e)]
        if sub.empty:
            continue
        g = 100 * (sub.pnl_gross / sub.risk).mean()
        sc = 100 * (sub.spread_cost / sub.risk).mean()
        fe = 100 * (sub.fees / sub.risk).mean()
        out.append({"regime": name, "n": len(sub), "gross%": g, "spread%": -sc, "fee%": -fe,
                    "net%": g - sc - fe, "cover": g / (sc + fe) if (sc + fe) > 0 else np.nan,
                    "width$": sub.width.mean(), "cr/w": (sub.credit / sub.width).mean(),
                    "risk$": sub.risk.mean()})
    return pd.DataFrame(out)


def fmt(df: pd.DataFrame) -> str:
    return df.to_string(index=False, float_format=lambda x: f"{x:,.3f}")


def audit(symbol: str, fee: float, width_pct: float) -> None:
    """Prove the instrument before believing its verdict."""
    print("=" * 100)
    print("AUDIT 1 - is the chain's own dP/dK a calibrated probability, and is parity finding spot?")
    cfgs = [Cfg(structure="put", target=t, entry="10:00", fee=fee, width_pct=width_pct)
            for t in (0.05, 0.10, 0.16, 0.25, 0.35)]
    cfgs += [Cfg(structure="call", target=t, entry="10:00", fee=fee, width_pct=width_pct)
             for t in (0.05, 0.10, 0.16, 0.25, 0.35)]
    frames = run_cells(cfgs, symbol, progress=500)
    rows = []
    for cfg, df in zip(cfgs, frames):
        if df.empty:
            continue
        rows.append({"side": cfg.structure, "target": cfg.target, "n": len(df),
                     "quoted prob": df.prob.mean(), "realized breach": df.breach.mean(),
                     "z": (df.breach.mean() - df.prob.mean()) /
                          np.sqrt(max(df.prob.mean() * (1 - df.prob.mean()) / len(df), 1e-12))})
    print(fmt(pd.DataFrame(rows)))
    print("A calibrated market makes 'realized breach' track 'quoted prob'; a broken spot or a")
    print("broken slope would not. |z| is against the binomial standard error of the quoted rate.")

    print()
    print("=" * 100)
    print("AUDIT 2 - the cost decomposition, per regime, for the widest-sample cell")
    base = Cfg(structure="put", target=0.16, entry="10:00", fee=fee, width_pct=width_pct)
    df = run_study(base, symbol)
    print(fmt(decompose(df)))
    print("'cover' is the mid-price edge divided by the cost of harvesting it: > 1 means the")
    print("trade survives its own execution.")

    print()
    print("=" * 100)
    print("AUDIT 3 - sensitivity: fill lag, exit time, and holding to the last quote")
    variants = [("fill at the decision snapshot", Cfg(**{**base.__dict__})),
                ("fill one 5-minute bar later", Cfg(**{**base.__dict__, "fill_lag": 1})),
                ("exit 15:00", Cfg(**{**base.__dict__, "exit": "15:00"})),
                ("exit 15:55 (last quote)", Cfg(**{**base.__dict__, "exit": "15:55"})),
                ("entry 09:35", Cfg(**{**base.__dict__, "entry": "09:35"})),
                ("entry 14:00", Cfg(**{**base.__dict__, "entry": "14:00"})),
                ("zero commission", Cfg(**{**base.__dict__, "fee": 0.0})),
                ("width 1.5% of spot", Cfg(**{**base.__dict__, "width_pct": 0.015})),
                ("width 0.3% of spot", Cfg(**{**base.__dict__, "width_pct": 0.003}))]
    frames = run_cells([v for _, v in variants], symbol, progress=500)
    rows = []
    for (label, cfg), df in zip(variants, frames):
        if df.empty:
            continue
        d = decompose(df).set_index("regime").loc["all"]
        r = df.ror.to_numpy()
        rows.append({"variant": label, "n": len(df), "gross%": d["gross%"], "spread%": d["spread%"],
                     "fee%": d["fee%"], "net%": d["net%"], "cover": d["cover"],
                     "t net": r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))})
    print(fmt(pd.DataFrame(rows)))


def stress(symbol: str, fee: float) -> None:
    """Give the trade every advantage the data allows, then look for a cell that clears its cost."""
    print("=" * 100)
    print("STRESS 1 - the cheapest version of the trade: widen the spread, enter late, exit at the")
    print("last quote. 'cover' > 1 is the only thing that matters.")
    n_sessions = len(odte_data.stored_dates(symbol))
    cfgs, keys = [], []
    for wp in (0.0075, 0.015, 0.03, 0.05):
        for entry in ("10:00", "12:00", "14:00"):
            for target in (0.10, 0.16, 0.25):
                for f in (fee, 0.0):
                    cfgs.append(Cfg(structure="put", target=target, width_pct=wp, entry=entry,
                                    exit="15:55", fee=f))
                    keys.append({"width%": 100 * wp, "entry": entry, "target": target, "fee$": f})
    frames = run_cells(cfgs, symbol, progress=500)
    rows = []
    for key, df in zip(keys, frames):
        if df.empty:
            continue
        d = decompose(df).set_index("regime")
        r = df.ror.to_numpy()
        rec = dict(key, n=len(df), **{k: d.loc["all", k] for k in
                                      ("gross%", "spread%", "fee%", "net%", "cover", "risk$")})
        rec["cov%"] = 100 * len(df) / max(n_sessions, 1)
        rec["t net"] = r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))
        for nm, *_ in REGIMES:
            rec[f"net {nm}"] = d.loc[nm, "net%"] if nm in d.index else np.nan
        rec["pass"] = sum(1 for nm, *_ in REGIMES if nm in d.index and d.loc[nm, "net%"] > 0)
        # what a book that risks `risk_frac` of equity per session earns per session
        rec["risk_frac for 3%/day"] = 3.0 / rec["net%"] if rec["net%"] > 0 else np.nan
        rows.append(rec)
    g = pd.DataFrame(rows).sort_values("net%", ascending=False)
    print(fmt(g))
    print(f"\nbest net of {len(g)} cells: {g['net%'].max():+.3f}% of risk/session; "
          f"cells with cover > 1: {int((g.cover > 1).sum())}; "
          f"net-positive in all three regimes: {int((g['pass'] == 3).sum())}")
    print("'cov%' is the share of the 0DTE sessions on disk the cell could actually trade - a cell")
    print("below ~95% is choosing its own sample, because a wide spread needs a long strike that")
    print("the stored +/-30-strike window does not always contain.")

    print()
    print("=" * 100)
    print("STRESS 2 - conditioning. Does any regime the market itself flags carry a bigger premium?")
    best = g.iloc[0]
    cfg = Cfg(structure="put", target=float(best["target"]), width_pct=float(best["width%"]) / 100,
              entry=str(best["entry"]), exit="15:55", fee=fee)
    print(f"cell: put target {cfg.target} width {cfg.width_pct:.2%} entry {cfg.entry} fee ${cfg.fee}")
    df = run_study(cfg, symbol)
    iv = pd.read_parquet(ROOT / "data" / "options" / "iv_regime.parquet")[["day", "iv_atm_1w", "term_ratio"]]
    iv["day"] = pd.to_datetime(iv["day"]).astype("datetime64[ns]")
    iv = iv.sort_values("day")
    d = df.copy()
    d["day"] = pd.to_datetime(d["date"]).astype("datetime64[ns]")
    # strictly prior-day implied vol, so the bucket is knowable before the session opens
    d = pd.merge_asof(d.sort_values("day"), iv, on="day", direction="backward", allow_exact_matches=False)
    d["cr_w"] = d.credit / d.width
    for col, label in (("iv_atm_1w", "prior-day SPY 1w ATM implied vol"),
                       ("term_ratio", "prior-day 1w/1m term ratio"),
                       ("cr_w", "credit / width at entry (known at entry)")):
        sub = d.dropna(subset=[col])
        if sub.empty:
            continue
        sub = sub.assign(bucket=pd.qcut(sub[col], 3, labels=["low", "mid", "high"]))
        out = []
        for b, s in sub.groupby("bucket", observed=True):
            dd = decompose(s.assign(date=s.date)).set_index("regime").loc["all"]
            r = s.ror.to_numpy()
            out.append({"bucket": b, "n": len(s), "gross%": dd["gross%"], "spread%": dd["spread%"],
                        "net%": dd["net%"], "cover": dd["cover"],
                        "t net": r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))})
        print(f"\n{label}")
        print(fmt(pd.DataFrame(out)))


def record(name: str, tag: str, df: pd.DataFrame, cfg: Cfg, risk_frac: float = 0.25) -> None:
    """Append one ledger row, sized as a book that risks `risk_frac` of equity per session."""
    r = df.ror.to_numpy() * risk_frac
    n = len(r)
    sd = r.std(ddof=1) if n > 1 else 0.0
    sessions_per_year = 175.0  # SPY had a 0DTE expiration on ~175 sessions a year over the sample
    car = 100 * ((1 + r.mean()) ** sessions_per_year - 1) if r.mean() > -1 else -100.0
    sharpe = (r.mean() / sd * np.sqrt(sessions_per_year)) if sd > 0 else 0.0
    eq = np.cumprod(1 + r)
    dd = 100 * float((1 - eq / np.maximum.accumulate(eq)).max()) if n else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": f"options/{name}", "class": "options", "tag": tag, "commit": "",
           "run_dir": "", "track": "options",
           "params": {"structure": cfg.structure, "target": cfg.target, "width_pct": cfg.width_pct,
                      "entry": cfg.entry, "exit": cfg.exit, "fee": cfg.fee,
                      "expire_otm": cfg.expire_otm, "pin_buffer": cfg.pin_buffer,
                      "risk_frac": risk_frac},
           "start": df.date.min(), "end": df.date.max(),
           "stats": {"Total Orders": str(4 * n), "Net Profit": f"{100 * (eq[-1] - 1):.3f}%",
                     "Compounding Annual Return": f"{car:.3f}%", "Sharpe Ratio": f"{sharpe:.3f}",
                     "Drawdown": f"{dd:.3f}%", "Trades Per Day": "1.0",
                     "Avg Daily PnL": f"{10000 * r.mean():.0f}",
                     "Costs Per Day": f"{-10000 * risk_frac * (df.spread_cost + df.fees).div(df.risk).mean():.0f}",
                     "Worst Day": f"{10000 * r.min():.0f}", "Loss Limit Days": "0",
                     "Sessions": str(n),
                     "Return On Risk Pct": f"{100 * df.ror.mean():.4f}",
                     "t": f"{df.ror.mean() / (df.ror.std(ddof=1) / np.sqrt(n)):.2f}",
                     "Win Rate": f"{100 * (df.ror > 0).mean():.0f}%"}}
    with (ROOT / "research" / "experiments.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def record_verdict(symbol: str, fee: float) -> None:
    """The four cells the O-2 verdict rests on, one ledger row per regime."""
    cells = [
        ("odte_put_spread", "O-2 pre-registered default: put 0.16 delta, 0.75% wide, enter 10:00, close at the quote 15:50",
         Cfg(structure="put", target=0.16, width_pct=0.0075, entry="10:00", exit="15:50", fee=fee)),
        ("odte_put_spread", "O-2 best cell, close at the quote: put 0.25 delta, 1.5% wide, enter 14:00",
         Cfg(structure="put", target=0.25, width_pct=0.015, entry="14:00", exit="15:55", fee=fee)),
        ("odte_put_spread", "O-2 best cell, untouched positions allowed to expire (no pin buffer)",
         Cfg(structure="put", target=0.25, width_pct=0.015, entry="14:00", exit="15:55", fee=fee, expire_otm=True)),
        ("odte_put_spread", "O-2 best cell, expire only when the close clears the short strike by 0.10% of spot",
         Cfg(structure="put", target=0.25, width_pct=0.015, entry="14:00", exit="15:55", fee=fee,
             expire_otm=True, pin_buffer=0.001)),
    ]
    frames = run_cells([c for _, _, c in cells], symbol, progress=900)
    for (name, tag, cfg), df in zip(cells, frames):
        if df.empty:
            continue
        for rname, s, e in REGIMES + [("all", "1900-01-01", "2100-01-01")]:
            sub = df[(df.date >= s) & (df.date <= e)]
            if len(sub) > 1:
                record(name, f"{tag} [{rname}]", sub, cfg)
        print(f"  recorded {tag[:70]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="SPY")
    ap.add_argument("--structure", default="put", choices=["put", "call", "condor"])
    ap.add_argument("--target", type=float, default=0.16)
    ap.add_argument("--width-pct", type=float, default=0.0075)
    ap.add_argument("--entry", default="10:00")
    ap.add_argument("--exit", default="15:50")
    ap.add_argument("--stop-mult", type=float, default=0.0)
    ap.add_argument("--fee", type=float, default=0.75)
    ap.add_argument("--fill-lag", type=int, default=0)
    ap.add_argument("--detail", action="store_true", help="also dump the per-session table")
    ap.add_argument("--grid", action="store_true", help="run the pre-registered grid")
    ap.add_argument("--audit", action="store_true", help="prove the instrument before its verdict")
    ap.add_argument("--stress", action="store_true", help="cheapest version of the trade, plus gates")
    ap.add_argument("--record", action="store_true", help="append the verdict cells to the ledger")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.audit:
        audit(args.symbol, args.fee, args.width_pct)
        return 0

    if args.stress:
        stress(args.symbol, args.fee)
        return 0

    if args.record:
        record_verdict(args.symbol, args.fee)
        return 0

    if args.grid:
        cfgs, keys = [], []
        for structure in ("put", "call", "condor"):
            for target in (0.10, 0.16, 0.25):
                for entry in ("10:00", "12:00"):
                    for stop in (0.0, 2.0):
                        cfgs.append(Cfg(structure=structure, target=target, width_pct=args.width_pct,
                                        entry=entry, exit=args.exit, stop_mult=stop, fee=args.fee,
                                        fill_lag=args.fill_lag))
                        keys.append({"structure": structure, "target": target,
                                     "entry": entry, "stop": stop})
        print(f"{len(cfgs)} cells over the stored {args.symbol} 0DTE sessions", flush=True)
        frames = run_cells(cfgs, args.symbol, progress=250)
        rows = []
        for key, df in zip(keys, frames):
            if df.empty:
                continue
            s = summarize(df).set_index("regime")
            rec = dict(key, n=int(s.loc["all", "n"]))
            for name, *_ in REGIMES:
                if name in s.index:
                    rec[name] = s.loc[name, "ror%"]
                    rec[f"t {name}"] = s.loc[name, "t"]
            rec["all%"] = s.loc["all", "ror%"]
            rec["t all"] = s.loc["all", "t"]
            rec["gross%"] = s.loc["all", "gross%"]
            rec["win%"] = s.loc["all", "win%"]
            rec["worst%"] = s.loc["all", "worst%"]
            rec["pass"] = sum(1 for name, *_ in REGIMES
                              if name in s.index and s.loc[name, "ror%"] > 0 and s.loc[name, "t"] > 2)
            rows.append(rec)
        g = pd.DataFrame(rows)
        print()
        print(fmt(g))
        print(f"\ncells passing the pre-registered rule (net > 0 at t > 2 in >= 2 of 3 regimes): "
              f"{int((g['pass'] >= 2).sum())} of {len(g)}")
        if args.out:
            g.to_csv(args.out, index=False)
        return 0

    cfg = Cfg(structure=args.structure, target=args.target, width_pct=args.width_pct,
              entry=args.entry, exit=args.exit, stop_mult=args.stop_mult, fee=args.fee,
              fill_lag=args.fill_lag)
    df = run_study(cfg, args.symbol)
    if df.empty:
        print("no sessions produced a position")
        return 1
    print(f"{cfg.structure} target {cfg.target} width {cfg.width_pct:.2%} entry {cfg.entry} "
          f"exit {cfg.exit} stop {cfg.stop_mult} fee ${cfg.fee} lag {cfg.fill_lag}")
    print(fmt(summarize(df)))
    if args.detail:
        print()
        print(df.tail(20).to_string(index=False))
    if args.out:
        df.to_csv(args.out, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
