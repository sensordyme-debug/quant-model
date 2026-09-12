"""F-11: the forecast is worth 4.256 bps and the book pays 2.724 of it away. Rank on net alpha.

F-8 produced the F track's first positive edge column - gross **4.256** bps per dollar turned
against a cost of **2.724**, net **+$306/day**, t **+1.47** - and refused it on power (clause 7
asked for t > 2). F-10 then priced the only scaling argument that was parked (F-9, more breadth)
and refused that too, on the grounds that 57% of the breadth curve was available to a book with
no forecast and the other 43% pointed the wrong way for the extension.

Both of those iterations tried to make the **gross** bigger, or the **sample** bigger. Neither
touched the other side of the subtraction. **64% of F-8's gross is paid away as cost, and the
cost is not a constant of the book - it is a property of the names the book chooses.** IBKR's
commission is $0.005 per *share*, so a name's round trip costs

    c_i = 2 * 1.5 (slippage) + 2 * 50 / price_i (commission) + 0.206 (SEC) + 1.98 / price_i (TAF)

basis points of the position, and on this 56-name universe that runs from **3.4 bps** (TMO at
$516) to **11.1 bps** (SOXS at $13). The spread is 7.7 bps against a gross of ~8.5 bps of
position: one name's round trip can eat the entire edge and another's costs nothing.

And the book walks straight into it. A plain decile ranks on predicted alpha alone, so it buys
whichever names have the widest predicted moves - which on this universe are the low-priced,
high-commission, leveraged and reverse-split names. F-7 measured that premium from the other
side and called it out (clause 4: "1.7 bps of the 2.4 bps of extra cost is selection, not
construction"), but F-7's conviction gate made it *worse* by design and no iteration has ever
tried the inverse. The book's realised commission is ~1.22 bps per leg against a **median name's
0.34** - it is paying 3.6x the universe's typical commission because of what it selects.

**F-11 changes the ranking and nothing else.** A name is worth holding for its alpha *net of its
own round trip*, which is knowable at the decision minute from its price:

    long score  = pred_i * 1e4 - lambda * c_i
    short score = -pred_i * 1e4 - lambda * c_i

lambda = 0 is F-8 exactly. **lambda = 1 is the economically correct value and needs no tuning** -
predicted alpha and cost are both in basis points of the same position, so lambda = 1 is simply
"rank on net alpha". That is the primary cell and the decision rule reads it.

    python scripts/ml_f11.py --books              # the lambda ladder, floors, gate, controls
    python scripts/ml_f11.py --books --record     # ... and append DIAGNOSTIC rows to the ledger
    python scripts/ml_f11.py --importance         # feature-importance stability across test years

**Run it with `INTRADAY_DATA_DIR=data/minute_alpaca`** (F-7's documented cost hazard: `_splits.json`
lives only in that store and without it the cost line is understated by ~0.06 bps of turnover).
Run it as `py -3.14` - only 3.14 has `pyarrow` on this machine.

--------------------------------------------------------------------------------------------
PRE-REGISTERED - written in full before any F-11 number was read
--------------------------------------------------------------------------------------------

**Clause 0 - the prior, stated out loud.** The cost saving is close to arithmetic and should
arrive: pushing the four expensive names out of the deciles ought to take the cost column from
2.72 to somewhere near 2.2-2.4 bps. The open question, and the reason this is an experiment and
not a calculation, is **what it costs in gross**. Those same expensive names are the volatile,
leveraged ones, which is where a cross-sectional forecast on 30-minute bars would be expected to
have most of its signal; if gross falls as fast as cost, the edge column does not move and F-11
refuses like everything before it. The honest prior is **a partial win**: cost down ~0.4 bps,
gross down ~0.3 bps, edge up ~0.1 bps, t landing near 1.6 - **better and still under the hurdle**.
The prior is written down so the outcome cannot be re-read as whatever the numbers turn out to be.

**Clause 1 - what is frozen.** Everything except the ranking. F-8's winning cell exactly: label
`close`, book `session` (one decision at slot 0, fill 10:00, held to the 15:30 flatten), decile
0.10, gross 1.0, equity $1M, flat overnight, window 2019-2026, 1,933 out-of-sample sessions.
Predictions are **re-read frozen** from `data/f1/f8_preds.parquet`; **no model is re-fitted, no
feature is added, no label is changed, no hyper-parameter is touched.** The lambda = 0 cell must
reproduce F-8's published numbers (gross 4.256, cost 2.724, net $306/day, t +1.474) or the run is
void.

**Clause 2 - selection is ex ante, accounting is not.** The score uses an *estimate* of the round
trip, `c_i`, built only from the entry price and the split scale, both known at the decision
minute - it is strictly causal. The cost that is actually **charged** is unchanged: the same
`intraday_common.commission` / `slippage` calls F-8 used, per fill, with the signed share count
and the regulatory pass-throughs. A cell may therefore select on a cost estimate that is wrong;
it will still be charged the real one. No cell may be scored on `c_i`.

**Clause 3 - the cells.**
  (a) **lambda ladder** {0, 0.25, 0.5, 1, 2, 4, 8} - 0 is the identity, **1 is the primary cell**,
      the rest are sensitivity. A monotone cost column is the minimum sign that the lever works.
  (b) **price floors** {$25, $50, $100} at lambda = 0 - the blunt version of the same idea, which
      also bounds how much of any lambda result is just "drop the four cheap names".
  (c) **the gate** at lambda = 1: trade a name only when its own net score is positive. The book
      then holds fewer than a full decile and its gross exposure shrinks; per-name weight stays
      at gross/(2k) so the shrinkage is real and not a concentration, and the sides are truncated
      to equal length so the book stays dollar-neutral.
  (d) lambda = 1 combined with the $50 floor.

**Clause 4 - the control, and it is a gate, not a remark.** (F-10's post-run defect (i) was a
clause written as a gate and coded as a remark. It is coded as a gate here.) Every headline cell
is re-run on a per-timestamp scrambled prediction, 3 seeds. Two requirements:
  (i) The control's **gross** must stay indistinguishable from zero at every lambda. If a
      zero-forecast book earns gross under cost-aware ranking, the lever is a static name tilt
      (permanently short the leveraged sleeve) and not an improvement to the forecast's book.
  (ii) The control's **cost** column must fall with lambda by roughly as much as the real book's.
      If it does not, the real book's saving is coming from somewhere other than the price term
      and the mechanism claimed here is not the mechanism operating.
  Failing (i) voids the decision; failing (ii) voids the *explanation* and the cell is reported
  as unexplained.

**Clause 5 - the decision rule, fixed before the numbers, and it is F-8's own.** Read on the
**lambda = 1 primary cell only**:
  - **PASS** iff pooled **t > 2.0** and **>= 5 of 8 test years net positive**. A pass reopens the
    F track as a paper-deploy candidate and owes a fresh harness run, not a deployment.
  - **REFUSE** otherwise. A refusal closes the cost axis for good: cost is bounded below by
    slippage (3.0 bps of position, 1.5 of turnover), so if removing the *entire* commission
    dispersion does not clear the hurdle, nothing on this axis can.
  The lambda that maximises t is reported but **may not be read as the result** - it is selected
  on the test set and is recorded only to show the shape of the ladder.

**Clause 6 - the F-10 decomposition, now a standing repository rule.** Any improvement in t is
split into its mean channel and its sd channel before it is believed. An improvement that is all
sd is a smoothing artifact of the construction; the control tells which is which.

**Clause 7 - what F-11 does not claim.** (a) It cannot reduce slippage, which is 1.5 bps of
turnover, 55% of F-8's cost column and a shipped constant; the entire addressable cost here is the
~1.22 bps commission-and-fees term. (b) It does not touch the training channel - the model is
still fitted on all 56 names, including the ones the book will now refuse to hold, which is the
conservative direction (a model trained only on the cheap names might be better or worse and F-11
does not pretend to know). (c) Nothing deploys from this file:
`algorithms/intraday/active/signal.py` and `live/intraday_config.json` are not touched, so no
deploy gate and no `--replay` is owed.

**Clause 8 - what happens to the track afterwards, decided now.** A refusal closes the F track on
F-8's terms with the cost axis explicitly priced, and the standing sentence stays: the supervised
class does not reopen without a new *mechanism*. A pass does not deploy anything - it produces a
harness request and a journal entry, and the owner decides.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import intraday_common as ic  # noqa: E402
import sweep_f1 as f1  # noqa: E402
import ml_f7 as f7  # noqa: E402
import ml_f8 as f8  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
CELLS_CSV = OUT / "f11_costaware.csv"

LABEL = "close"          # clause 1
EQUITY = f8.EQUITY
N_SLOTS = f8.N_SLOTS
DECILE = f8.DECILE
LAMBDAS = [0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]   # clause 3(a)
FLOORS = [25.0, 50.0, 100.0]                     # clause 3(b)
CTRL_SEEDS = 3                                   # clause 4
CTRL_CELLS = [("lam0", dict(lam=0.0)), ("lam1", dict(lam=1.0)),
              ("lam4", dict(lam=4.0)), ("floor50", dict(lam=0.0, floor=50.0))]

# F-8's published full-universe numbers; clause 1's reproduction check
F8_CELL = {"gross_bps": 4.256, "cost_bps": 2.724, "net_day": 305.7, "t": 1.474}
TARGET_T = 2.0           # clause 5, inherited from F-8 clause 7
MIN_YEARS = 5            # clause 5, inherited from F-8 clause 7


# ------------------------------------------------------------------------- the cost estimate


def cost_bps(real_px: np.ndarray) -> np.ndarray:
    """Clause 2: the ex-ante round-trip cost of a position, in bps of that position.

    Two slippage legs, two per-share commission legs, and the regulatory pass-throughs that are
    charged once per round trip because exactly one of the two legs is a sale (a long sells to
    close, a short sells to open). Everything here is known at the decision minute.
    """
    px = np.where(np.isfinite(real_px) & (real_px > 0), real_px, np.nan)
    comm = 2.0 * ic.COMMISSION_PER_SHARE / px * 1e4
    taf = ic.TAF_PER_SHARE / px * 1e4
    return 2.0 * ic.SLIPPAGE_BPS + comm + ic.SEC_FEE_RATE * 1e4 + taf


def add_cost(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach the real (unadjusted) price and its round-trip cost estimate to every panel row."""
    f = frame.copy()
    scale = np.array([f8.f7_scale(s, d) for s, d in zip(f["sym"].to_numpy(), f["day"].to_numpy())])
    f["real_px"] = f["entry_px"].to_numpy(float) * scale
    f["c_bps"] = cost_bps(f["real_px"].to_numpy())
    return f


# ------------------------------------------------------------------------------ the selection


def select(pred: np.ndarray, cost: np.ndarray, ok: np.ndarray, decile: float, gross: float,
           lam: float, gate: bool, greedy: bool = False) -> np.ndarray:
    """Dollar-neutral decile on net-alpha scores.

    Per-name weight is gross/(2k) with k fixed by the eligible count, exactly as F-8's `_decile`.
    Under the gate the sides shrink and are truncated to equal length: exposure falls, the book
    stays neutral, and no position is concentrated.

    **`pred` is already in basis points** - `sweep_f1.fit_predict` trains on `y * 1e4` because
    sklearn's early stop compares a squared-error loss against an absolute tolerance. So the score
    is `pred - lambda * cost` with no unit conversion, and lambda = 1 is literally net alpha. The
    first cut of this file multiplied `pred` by 1e4 again, which made lambda = 1 behave as
    lambda = 1e-4 and flattened the whole ladder; the defect was found by clause 1.

    lambda = 0 without a gate delegates to F-8's own `_decile` so clause 1's identity is exact by
    construction. The greedy below agrees with it except on **exact prediction ties**, which the
    tree emits often (identical leaf values) and which the two routines break in opposite
    directions; `greedy=True` forces the greedy path so the ladder's own zero point is available
    for a like-for-like comparison.
    """
    w = np.zeros(len(pred))
    idx = np.flatnonzero(ok)
    if len(idx) < 6:
        return w
    if lam == 0.0 and not gate and not greedy:
        return f8._decile(pred, ok, decile, gross)
    k = max(1, int(round(decile * len(idx))))
    pb = pred
    scores = np.concatenate([pb[idx] - lam * cost[idx], -pb[idx] - lam * cost[idx]])
    who = np.concatenate([idx, idx])
    side = np.concatenate([np.ones(len(idx)), -np.ones(len(idx))])
    order = np.argsort(-scores, kind="stable")

    used = np.zeros(len(pred), bool)
    longs: list[int] = []
    shorts: list[int] = []
    for o in order:
        if gate and scores[o] <= 0:
            break
        i = int(who[o])
        if used[i]:
            continue
        if side[o] > 0:
            if len(longs) >= k:
                continue
            longs.append(i)
        else:
            if len(shorts) >= k:
                continue
            shorts.append(i)
        used[i] = True
        if len(longs) >= k and len(shorts) >= k:
            break

    m = min(len(longs), len(shorts))          # dollar neutrality, clause 3(c)
    if m == 0:
        return w
    unit = gross / 2.0 / k
    w[longs[:m]] = unit
    w[shorts[:m]] = -unit
    return w


# ------------------------------------------------------------------------------- the simulator


def _day_matrices(g: pd.DataFrame, syms: np.ndarray):
    n = len(syms)
    pos = {s: i for i, s in enumerate(syms)}
    P = np.full((N_SLOTS, n), np.nan)
    F = np.full((N_SLOTS, n), np.nan)
    X = np.full((N_SLOTS, n), np.nan)
    C = np.full(n, np.nan)
    R = np.full(n, np.nan)
    for k, sym, pr, fw, px, cb, rp in zip(
            g["slot"].to_numpy(), g["sym"].to_numpy(), g["pred"].to_numpy(float),
            g["fwd"].to_numpy(float), g["entry_px"].to_numpy(float),
            g["c_bps"].to_numpy(float), g["real_px"].to_numpy(float)):
        j = pos[sym]
        P[k, j], F[k, j], X[k, j] = pr, fw, px
        if k == 0:
            C[j], R[j] = cb, rp
    return P, F, X, C, R


def simulate(frame: pd.DataFrame, lam: float = 0.0, floor: float = 0.0, gate: bool = False,
             decile: float = DECILE, gross: float = 1.0, greedy: bool = False,
             scramble: int | None = None) -> pd.DataFrame:
    """F-8's `session` book with the net-alpha ranking. One row per session.

    The P&L, turnover and cost accounting is F-8's, unchanged and per fill (clause 2).
    """
    rng = np.random.default_rng(scramble) if scramble is not None else None
    rows = []
    for day, g in frame.groupby("day", sort=True):
        syms = np.unique(g["sym"].to_numpy())
        P, F, X, C, R = _day_matrices(g, syms)
        if rng is not None:
            for k in range(N_SLOTS):
                ok_k = np.isfinite(P[k])
                if ok_k.sum() > 1:
                    P[k, ok_k] = rng.permutation(P[k, ok_k])

        ok = np.isfinite(P[0]) & np.isfinite(X[0]) & np.isfinite(C)
        for j in range(N_SLOTS):
            ok &= np.isfinite(F[j])
        if floor > 0:
            ok &= np.isfinite(R) & (R >= floor)

        W = np.zeros((N_SLOTS, len(syms)))
        w = select(P[0], C, ok, decile, gross, lam, gate, greedy)
        if w.any():
            W[0:N_SLOTS] += w

        fwd0 = np.where(np.isfinite(F), F, 0.0)
        pnl = float((W * np.expm1(fwd0)).sum() * EQUITY)

        turn = 0.0
        cost = 0.0
        prev = np.zeros(len(syms))
        for k in range(N_SLOTS + 1):
            cur = W[k] if k < N_SLOTS else np.zeros(len(syms))
            px = X[min(k, N_SLOTS - 1)]
            dw = cur - prev
            m = np.abs(dw) > 1e-12
            if m.any():
                notional = np.abs(dw[m]) * EQUITY
                turn += float(notional.sum())
                for s, d, q, nt in zip(syms[m], dw[m], px[m], notional):
                    if not np.isfinite(q) or q <= 0:
                        continue
                    sh = np.sign(d) * nt / q
                    cost += ic.commission(sh, float(q), f8.f7_scale(s, day)) + ic.slippage(sh, float(q))
            prev = cur
        rows.append({"day": day, "gross": pnl, "cost": cost, "turnover": turn,
                     "names": int((np.abs(W[0]) > 1e-12).sum())})

    sess = pd.DataFrame(rows)
    sess["net"] = sess["gross"] - sess["cost"]
    return sess


def summarize(sess: pd.DataFrame, label: str) -> dict:
    r = f8.summarize(sess, label)
    r["names"] = float(sess["names"].mean())
    net = sess["net"].to_numpy()
    r["sd"] = float(net.std(ddof=1))
    return r


HDR = (f"{'cell':<22} {'sess':>5} {'nm':>4} {'gr bps':>7} {'cost bps':>8} {'edge':>7} "
       f"{'turn/day':>10} {'$/day':>8} {'t':>6} {'sd':>7} {'worst':>9} {'win':>5}")


def line(r: dict) -> str:
    return (f"{r['label']:<22} {r['sessions']:>5} {r['names']:>4.1f} {r['gross_bps']:>7.3f} "
            f"{r['cost_bps']:>8.3f} {r['edge_bps']:>7.3f} {r['turn_day']:>10,.0f} "
            f"{r['net_day']:>8,.0f} {r['t']:>+6.2f} {r['sd']:>7,.0f} {r['worst']:>9,.0f} "
            f"{100 * r['win']:>4.0f}%")


# ------------------------------------------------------------------------------------ reports


def by_year(sess: pd.DataFrame) -> pd.Series:
    y = pd.Series(pd.to_datetime(sess["day"]).dt.year.to_numpy(), index=sess.index)
    return sess.groupby(y)["net"].mean().round(0)


def by_regime(sess: pd.DataFrame) -> pd.DataFrame:
    reg = f7.vol_regime(sess["day"].to_numpy())
    s = sess.copy()
    s["regime"] = s["day"].astype(str).map(reg)
    out = []
    for name in ["low vol", "mid vol", "high vol"]:
        d = s[s["regime"] == name]
        if d.empty:
            continue
        net = d["net"].to_numpy()
        turn = float(d["turnover"].mean())
        out.append({"regime": name, "sessions": len(d), "net_day": float(net.mean()),
                    "t": f1.tstat(net),
                    "gross_bps": 1e4 * float(d["gross"].mean()) / turn if turn else np.nan,
                    "cost_bps": 1e4 * float(d["cost"].mean()) / turn if turn else np.nan})
    return pd.DataFrame(out)


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    sd = ret.std(ddof=1) if n > 1 else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f11_costaware", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-11", "params": params,
           "start": str(sess["day"].min()), "end": str(sess["day"].max()),
           "stats": {"Sessions": str(n),
                     "Avg Daily PnL": f"{net.mean():.0f}",
                     "t": f"{f1.tstat(net):.2f}",
                     "Gross Per Day": f"{sess['gross'].mean():.0f}",
                     "Costs Per Day": f"{sess['cost'].mean():.0f}",
                     "Turnover Per Day": f"{sess['turnover'].mean():.0f}",
                     "Gross Bps Per Turnover": f"{r['gross_bps']:.3f}",
                     "Cost Bps Per Turnover": f"{r['cost_bps']:.3f}",
                     "Edge Bps Per Turnover": f"{r['edge_bps']:.3f}",
                     "Names Held": f"{r['names']:.1f}",
                     "Worst Day": f"{net.min():.0f}",
                     "Win Rate": f"{100 * (net > 0).mean():.0f}%",
                     "Sharpe Ratio": f"{(ret.mean() / sd * np.sqrt(252)) if sd else float('nan'):.3f}",
                     "Diagnostic": "true",
                     **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


# --------------------------------------------------------------------------------------- main


def run_books(record_rows: bool = False) -> None:
    t_start = time.time()
    print(f"cost store: {ic.DATA_DIR}  (slippage {ic.SLIPPAGE_BPS} bps; "
          f"splits file present: {(Path(ic.DATA_DIR) / '_splits.json').exists()})")
    frame = add_cost(f8.load_frames()[LABEL])
    sub = frame[frame["slot"] == 0]
    per = sub.groupby("sym")["c_bps"].median().sort_values()
    print(f"\nround-trip cost estimate over the universe: min {per.iloc[0]:.2f} "
          f"(ned {per.index[0]}), median {per.median():.2f}, max {per.iloc[-1]:.2f} "
          f"({per.index[-1]}) bps of position")
    print("  most expensive 6:", ", ".join(f"{s} {v:.2f}" for s, v in per.tail(6)[::-1].items()))

    rows: list[dict] = []
    keep: dict[str, pd.DataFrame] = {}

    print("\n=== clause 3(a): the lambda ladder ===")
    print(HDR)
    for lam in LAMBDAS:
        sess = simulate(frame, lam=lam)
        r = summarize(sess, f"lambda {lam:g}")
        r.update(cell=f"lam{lam:g}", lam=lam, floor=0.0, gate=False, kind="real")
        rows.append(r)
        keep[r["cell"]] = sess
        print(line(r))
    # the ladder's own zero point on the greedy code path: the difference against `lambda 0` is
    # nothing but how exact prediction ties are broken, and it is reported so the first rung of
    # the ladder is not read as a cost-aware effect.
    sess = simulate(frame, lam=0.0, greedy=True)
    r0 = summarize(sess, "lambda 0 (greedy)")
    r0.update(cell="lam0_greedy", lam=0.0, floor=0.0, gate=False, kind="real")
    rows.append(r0)
    keep["lam0_greedy"] = sess
    print(line(r0))

    print("\n=== clause 3(b): price floors at lambda 0 ===")
    print(HDR)
    for fl in FLOORS:
        sess = simulate(frame, lam=0.0, floor=fl)
        r = summarize(sess, f"floor ${fl:g}")
        r.update(cell=f"floor{fl:g}", lam=0.0, floor=fl, gate=False, kind="real")
        rows.append(r)
        keep[r["cell"]] = sess
        print(line(r))

    print("\n=== clause 3(c)/(d): the gate, and lambda with a floor ===")
    print(HDR)
    for cell, kw, lab in [("gate_lam1", dict(lam=1.0, gate=True), "lambda 1 + gate"),
                          ("lam1_floor50", dict(lam=1.0, floor=50.0), "lambda 1 + floor $50")]:
        sess = simulate(frame, **kw)
        r = summarize(sess, lab)
        r.update(cell=cell, lam=kw.get("lam", 0.0), floor=kw.get("floor", 0.0),
                 gate=kw.get("gate", False), kind="real")
        rows.append(r)
        keep[cell] = sess
        print(line(r))

    # ---- clause 1: the identity check, before anything is read
    base = next(r for r in rows if r["cell"] == "lam0")
    ok_identity = (abs(base["gross_bps"] - F8_CELL["gross_bps"]) < 0.002
                   and abs(base["cost_bps"] - F8_CELL["cost_bps"]) < 0.002
                   and abs(base["net_day"] - F8_CELL["net_day"]) < 1.0
                   and abs(base["t"] - F8_CELL["t"]) < 0.01)
    print(f"\nclause 1 identity vs F-8: gross {base['gross_bps']:.3f}/{F8_CELL['gross_bps']}, "
          f"cost {base['cost_bps']:.3f}/{F8_CELL['cost_bps']}, "
          f"net {base['net_day']:.1f}/{F8_CELL['net_day']}, t {base['t']:.3f}/{F8_CELL['t']}"
          f"  -> {'OK' if ok_identity else 'VOID'}")
    if not ok_identity:
        print("!! clause 1 fails: the frozen cell does not reproduce. The run is void.")
        return

    # ---- clause 4: the control, coded as a gate
    print("\n=== clause 4: scrambled-prediction controls (3 seeds each) ===")
    print(HDR)
    ctrl: dict[str, list[dict]] = {}
    for cell, kw in CTRL_CELLS:
        got = []
        for s in range(CTRL_SEEDS):
            sess = simulate(frame, scramble=7000 + s, **kw)
            r = summarize(sess, f"ctrl {cell} s{s}")
            r.update(cell=f"ctrl_{cell}_s{s}", lam=kw.get("lam", 0.0),
                     floor=kw.get("floor", 0.0), gate=False, kind="control")
            rows.append(r)
            got.append(r)
            print(line(r))
        ctrl[cell] = got

    def cmean(cell: str, key: str) -> float:
        return float(np.mean([r[key] for r in ctrl[cell]]))

    def csd(cell: str, key: str) -> float:
        return float(np.std([r[key] for r in ctrl[cell]], ddof=1))

    print("\nclause 4 summary")
    print(f"{'cell':<10} {'ctrl gross bps':>15} {'+/- sd':>8} {'ctrl t(gross)':>14} "
          f"{'ctrl cost bps':>14} {'real cost bps':>14}")
    for cell, _ in CTRL_CELLS:
        real = next((r for r in rows if r["cell"] == cell), None)
        gt = float(np.mean([r["gross_t"] for r in ctrl[cell]]))
        print(f"{cell:<10} {cmean(cell, 'gross_bps'):>15.3f} {csd(cell, 'gross_bps'):>8.3f} "
              f"{gt:>+14.2f} {cmean(cell, 'cost_bps'):>14.3f} "
              f"{(real['cost_bps'] if real else float('nan')):>14.3f}")

    # (i) zero-forecast gross must stay at zero under cost-aware ranking
    ctrl_gross_ok = all(abs(float(np.mean([r["gross_t"] for r in ctrl[c]]))) < 2.0
                        for c, _ in CTRL_CELLS)
    # (ii) the control's cost must fall with lambda by roughly as much as the real book's
    real_drop = base["cost_bps"] - next(r for r in rows if r["cell"] == "lam1")["cost_bps"]
    ctrl_drop = cmean("lam0", "cost_bps") - cmean("lam1", "cost_bps")
    share = ctrl_drop / real_drop if real_drop else float("nan")
    print(f"\nclause 4(i)  zero-forecast gross flat at every cell: "
          f"{'PASS' if ctrl_gross_ok else 'FAIL - the decision is void'}")
    print(f"clause 4(ii) cost drop lambda0 -> lambda1: real {real_drop:+.3f} bps, "
          f"control {ctrl_drop:+.3f} bps ({100 * share:.0f}% of it) -> "
          f"{'PASS, the mechanism is the price term' if 0.5 <= share <= 1.6 else 'FAIL - unexplained'}")
    if not ctrl_gross_ok:
        print("!! clause 4(i) fails: cost-aware ranking earns gross with no forecast. Void.")
        return

    # ---- clause 6: mean and sd channels
    prim = next(r for r in rows if r["cell"] == "lam1")
    print("\n=== clause 6: where the change in t comes from ===")
    print(f"{'channel':<14} {'lambda 0':>12} {'lambda 1':>12} {'ratio':>8}")
    for key, lab in [("net_day", "mean $/day"), ("sd", "sd $/day"), ("t", "t")]:
        rt = prim[key] / base[key] if base[key] else float("nan")
        print(f"{lab:<14} {base[key]:>12,.1f} {prim[key]:>12,.1f} {rt:>8.3f}")

    # ---- post-run diagnostics, declared as such: they cannot change clause 5's decision, which
    # is read on the pooled t of lambda = 1 alone. They ask the different and weaker question of
    # whether the *lever* works, which a comparison of two separately-noisy t's cannot answer.
    print("\n=== post-run: is the lever real? paired on the session, not two t's side by side ===")
    a, b = keep["lam0"], keep["lam1"]
    assert (a["day"].to_numpy() == b["day"].to_numpy()).all()
    d = b["net"].to_numpy() - a["net"].to_numpy()
    print(f"per-session net(lambda 1) - net(lambda 0): mean ${d.mean():+,.0f}/day, "
          f"paired t {f1.tstat(d):+.2f}, positive on {100 * (d > 0).mean():.0f}% of sessions")
    dc = a["cost"].to_numpy() - b["cost"].to_numpy()
    dg = b["gross"].to_numpy() - a["gross"].to_numpy()
    print(f"  of which cost saved ${dc.mean():+,.0f}/day (paired t {f1.tstat(dc):+.2f}) and "
          f"gross given up ${-dg.mean():,.0f}/day (paired t {f1.tstat(dg):+.2f})")

    print("\n=== post-run: the two halves of the window, so the lever is not one regime ===")
    half = len(a) // 2
    print(f"{'period':<22} {'sess':>5} {'lam0 $/day':>11} {'lam1 $/day':>11} {'delta':>8} "
          f"{'paired t':>9}")
    for name, sl in [("first half", slice(0, half)), ("second half", slice(half, len(a)))]:
        aa, bb = a.iloc[sl], b.iloc[sl]
        dd = bb["net"].to_numpy() - aa["net"].to_numpy()
        print(f"{name} {str(aa['day'].iloc[0])[:7]}-{str(aa['day'].iloc[-1])[:7]:<7} "
              f"{len(aa):>5} {aa['net'].mean():>11,.0f} {bb['net'].mean():>11,.0f} "
              f"{dd.mean():>8,.0f} {f1.tstat(dd):>+9.2f}")

    # ---- clause 5: the decision, on the primary cell only
    print("\n=== clause 5: the decision, read on lambda = 1 ===")
    yr_base, yr_prim = by_year(keep["lam0"]), by_year(keep["lam1"])
    print(f"{'year':<6} " + " ".join(f"{y:>8}" for y in yr_prim.index))
    print(f"{'lam0':<6} " + " ".join(f"{v:>8,.0f}" for v in yr_base.values))
    print(f"{'lam1':<6} " + " ".join(f"{v:>8,.0f}" for v in yr_prim.values))
    pos = int((yr_prim > 0).sum())
    passed = prim["t"] > TARGET_T and pos >= MIN_YEARS
    print(f"\nlambda = 1: t {prim['t']:+.3f} (hurdle {TARGET_T}), {pos}/{len(yr_prim)} years "
          f"positive (hurdle {MIN_YEARS}), net ${prim['net_day']:,.0f}/day, "
          f"edge {prim['edge_bps']:+.3f} bps -> **{'PASS' if passed else 'REFUSE'}**")
    best = max((r for r in rows if r["kind"] == "real"), key=lambda r: r["t"])
    print(f"best cell on the test set (clause 5: may NOT be read as the result): "
          f"{best['label']} t {best['t']:+.2f}, net ${best['net_day']:,.0f}/day")

    # ---- regimes, which the job brief asks for explicitly
    print("\n=== out-of-sample P&L after costs, by causal SPY vol tercile ===")
    for cell in ["lam0", "lam1", "lam4"]:
        if cell not in keep:
            continue
        reg = by_regime(keep[cell])
        print(f"\n{cell}:")
        print(f"  {'regime':<10} {'sess':>5} {'gr bps':>7} {'cost bps':>8} {'$/day':>8} {'t':>6}")
        for r in reg.to_dict("records"):
            print(f"  {r['regime']:<10} {r['sessions']:>5} {r['gross_bps']:>7.3f} "
                  f"{r['cost_bps']:>8.3f} {r['net_day']:>8,.0f} {r['t']:>+6.2f}")

    # ---- what the book stopped holding
    print("\n=== what the ranking changed: name-days held, lambda 0 vs lambda 1 ===")
    held = {}
    for cell, lam in [("lam0", 0.0), ("lam1", 1.0)]:
        cnt: dict[str, int] = {}
        for day, g in frame.groupby("day", sort=True):
            syms = np.unique(g["sym"].to_numpy())
            P, F, X, C, R = _day_matrices(g, syms)
            ok = np.isfinite(P[0]) & np.isfinite(X[0]) & np.isfinite(C)
            for j in range(N_SLOTS):
                ok &= np.isfinite(F[j])
            w = select(P[0], C, ok, DECILE, 1.0, lam, False, greedy=True)
            for s in syms[np.abs(w) > 1e-12]:
                cnt[s] = cnt.get(s, 0) + 1
        held[cell] = pd.Series(cnt)
    tab = pd.DataFrame(held).fillna(0)
    tab["c_bps"] = per
    tab["delta"] = tab["lam1"] - tab["lam0"]
    print(tab.sort_values("delta").head(8).to_string())
    print("  ...")
    print(tab.sort_values("delta").tail(5).to_string())

    out = pd.DataFrame(rows)
    out.to_csv(CELLS_CSV, index=False)
    print(f"\nwrote {CELLS_CSV.relative_to(REPO)}  ({len(out)} cells, "
          f"{time.time() - t_start:.0f}s)")

    if record_rows:
        for r in rows:
            sess = keep.get(r["cell"])
            if sess is None:
                continue
            record(f"F-11 {r['label']}", r, sess,
                   {"label": LABEL, "book": "session", "decile": DECILE,
                    "lambda": r["lam"], "floor": r["floor"], "gate": r["gate"]},
                   {"Cell Kind": r["kind"], "IC Label": LABEL})
        print(f"recorded {sum(1 for r in rows if r['cell'] in keep)} DIAGNOSTIC rows")


# ------------------------------------------------------- feature importance stability (brief)


def run_importance() -> None:
    """The job brief's second judging criterion: is the model's feature ranking stable?"""
    imp = pd.read_csv(f8.IMP, index_col=0)
    years = [c for c in imp.columns if c.isdigit()]
    ranks = imp[years].rank(ascending=False)
    print(f"feature-importance stability over {len(years)} test years, "
          f"{len(imp)} features ({f8.IMP.name})")

    rho = ranks.corr(method="spearman")
    iu = np.triu_indices(len(years), 1)
    pair = rho.to_numpy()[iu]
    print(f"\nmean pairwise Spearman of the yearly rankings: {pair.mean():+.3f} "
          f"(min {pair.min():+.3f}, max {pair.max():+.3f})")

    k = 10
    tops = {y: set(ranks.index[ranks[y] <= k]) for y in years}
    ov = [len(tops[a] & tops[b]) / k for i, a in enumerate(years) for b in years[i + 1:]]
    print(f"mean top-{k} overlap between year pairs: {100 * np.mean(ov):.0f}% "
          f"(min {100 * min(ov):.0f}%, max {100 * max(ov):.0f}%)")

    always = set.intersection(*tops.values())
    print(f"features in the top-{k} of every year: "
          f"{', '.join(sorted(always)) if always else '(none)'}")

    print(f"\n{'feature':<18} {'rank mean':>10} {'rank sd':>9} " +
          " ".join(f"{y:>6}" for y in years))
    show = ranks.mean(axis=1).sort_values().head(12).index
    for s in show:
        print(f"{s:<18} {ranks.loc[s].mean():>10.1f} {ranks.loc[s].std():>9.1f} " +
              " ".join(f"{ranks.loc[s, y]:>6.0f}" for y in years))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--books", action="store_true", help="the lambda ladder and the decision")
    ap.add_argument("--importance", action="store_true", help="feature-importance stability")
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC ledger rows")
    a = ap.parse_args()
    if a.importance:
        run_importance()
    if a.books or not (a.importance):
        run_books(record_rows=a.record)


if __name__ == "__main__":
    main()
