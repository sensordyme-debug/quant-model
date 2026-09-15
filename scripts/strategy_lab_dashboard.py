"""Phase 17: one local page that answers "what should we investigate next, and why?".

It is written to `docs/research/strategy_results/index.html` and opened from disk. It is not
connected to anything: no live data, no broker, no network call, no form that posts anywhere.
It reads the CSVs the lab produced and renders them.

The page leads with the verdict distribution and the barrier chart rather than with a P&L
league table, because a league table sorted by net profit is precisely the artefact this lab
exists to avoid producing. The two cells that are not REJECT are named at the top with the
reason they survived and the reason they are still not candidates.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
OUT = REPO / "docs" / "research" / "strategy_results"
MLL = 2_000.0

CSS = """
:root{--ink:#1a202c;--mut:#5a6678;--line:#dfe3e9;--bg:#fbfbfa;--card:#fff;
--rej:#9b2c2c;--wat:#8a6d1f;--res:#2b6cb0;--ok:#22543d;--accent:#2b6cb0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:32px 22px 70px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:17px;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:14px;margin:20px 0 6px}
.sub{color:var(--mut);margin:0 0 22px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:7px;padding:13px 15px}
.card .n{font-size:23px;font-weight:600;font-variant-numeric:tabular-nums}
.card .l{color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.05em}
table{border-collapse:collapse;width:100%;font-size:12.5px;background:var(--card)}
th,td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:right;
font-variant-numeric:tabular-nums}
th{background:#f2f4f7;font-weight:600;text-align:right;position:sticky;top:0}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:7px;max-height:640px;
overflow-y:auto}
.v{font-weight:600;font-size:11px;padding:2px 7px;border-radius:10px;color:#fff}
.REJECT{background:var(--rej)}.WATCH{background:var(--wat)}.RESEARCH{background:var(--res)}
.PAPER{background:var(--ok)}
figure{margin:16px 0}figure img{width:100%;border:1px solid var(--line);border-radius:7px;
background:#fff}
figcaption{color:var(--mut);font-size:12px;margin-top:6px}
.note{background:#fff8e6;border-left:3px solid #d69e2e;padding:11px 14px;margin:14px 0;
border-radius:0 5px 5px 0;font-size:13px}
.bad{color:var(--rej);font-weight:600}.good{color:var(--ok);font-weight:600}
code{background:#eef1f5;padding:1px 5px;border-radius:3px;font-size:12px}
"""


def esc(x) -> str:
    return html.escape(str(x))


def table(df: pd.DataFrame, fmts: dict) -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = r[c]
            if c == "verdict":
                cells.append(f'<td><span class="v {esc(v).split()[0]}">{esc(v)}</span></td>')
                continue
            f = fmts.get(c)
            try:
                s = f(v) if f else esc(v)
            except (TypeError, ValueError):
                s = esc(v)
            cls = ""
            if c in ("net_pnl", "expectancy_trade", "stressed_expectancy_trade", "t_stat"):
                cls = ' class="bad"' if (isinstance(v, (int, float))
                                         and np.isfinite(v) and v < 0) else ""
            cells.append(f"<td{cls}>{s}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def main() -> int:
    cards = pd.read_csv(REPO / "research" / "lab_scorecards.csv")
    rank = pd.read_csv(REPO / "research" / "lab_ranking.csv")
    port = pd.read_csv(REPO / "research" / "lab_portfolio.csv")
    ts = (pd.read_csv(REPO / "research" / "lab_topstep.csv")
          if (REPO / "research" / "lab_topstep.csv").exists() else pd.DataFrame())

    vc = cards.verdict.value_counts().to_dict()
    n_cells = len(cards)
    under = int((cards.dd_over_mll < 1).sum())
    stressed_pos = int((cards.stressed_expectancy_trade > 0).sum())
    normal = port[port.regime == "normal"]

    f2 = lambda v: f"{v:,.2f}"          # noqa: E731
    f0 = lambda v: f"{v:,.0f}"          # noqa: E731
    fp = lambda v: f"{v:.1%}" if np.isfinite(v) else "&mdash;"   # noqa: E731
    fx = lambda v: f"{v:.1f}x" if np.isfinite(v) else "&mdash;"  # noqa: E731

    show = rank[["strategy", "symbol", "family", "verdict", "trades", "net_pnl",
                 "expectancy_trade", "stressed_expectancy_trade", "profit_factor",
                 "win_rate", "max_dd", "dd_over_mll", "t_stat", "median_hold_min",
                 "dll_breach_rate", "best_twin_pass"]].copy()
    fmts = {"trades": f0, "net_pnl": f0, "expectancy_trade": f2,
            "stressed_expectancy_trade": f2, "profit_factor": f2, "win_rate": fp,
            "max_dd": f0, "dd_over_mll": fx, "t_stat": f2, "median_hold_min": f0,
            "dll_breach_rate": fp, "best_twin_pass": fp}

    survivors = rank[rank.verdict != "REJECT"]
    surv_html = ""
    for _, r in survivors.iterrows():
        surv_html += f"""
<h3>{esc(r.strategy)} &middot; {esc(r.symbol)} &mdash;
<span class="v {esc(r.verdict).split()[0]}">{esc(r.verdict)}</span></h3>
<p><b>Why it survived:</b> maximum drawdown at one contract is
<b>{r.max_dd:,.0f}</b> ({r.dd_over_mll:.1f}&times; the $2,000 barrier), and expectancy stays
positive at <b>${r.stressed_expectancy_trade:,.2f}</b>/trade with a full tick of round-turn
slippage charged. Daily-loss-limit breaches occur on
{'&mdash;' if not np.isfinite(r.dll_breach_rate) else f'{r.dll_breach_rate:.1%}'} of sessions.</p>
<p><b>Why it is still not a candidate:</b> the daily series gives t = {r.t_stat:.2f}, short of
1.96 &mdash; and that is before any correction for having examined {n_cells} cells. Net profit
over the whole sample is ${r.net_pnl:,.0f} on {int(r.trades):,} trades, which at a median hold
of {r.median_hold_min:.0f} minutes is a scalp, not a position.</p>"""

    body = f"""<div class="wrap">
<h1>Strategy Backtest &amp; Selection Lab</h1>
<p class="sub">{n_cells} strategy&times;instrument cells &middot; one contract &middot;
09:30&ndash;16:00&nbsp;ET &middot; commission and a stressed 1-tick slippage regime &middot;
research only, nothing connected</p>

<div class="cards">
  <div class="card"><div class="n">{n_cells}</div><div class="l">cells tested</div></div>
  <div class="card"><div class="n">{vc.get('REJECT', 0)}</div><div class="l">reject</div></div>
  <div class="card"><div class="n">{vc.get('WATCH', 0)}</div><div class="l">watch</div></div>
  <div class="card"><div class="n">{vc.get('RESEARCH', 0)}</div><div class="l">research</div></div>
  <div class="card"><div class="n">{vc.get('PAPER CANDIDATE', 0)}</div>
    <div class="l">paper candidate</div></div>
  <div class="card"><div class="n">0</div><div class="l">combine candidate</div></div>
</div>

<div class="note"><b>What should we investigate next?</b> Nothing in this field is ready to
paper-trade. The binding constraint is not profitability &mdash; it is that
<b>{n_cells - under} of {n_cells}</b> cells have a one-contract maximum drawdown larger than
the $2,000 trailing MLL, at a median of
<b>{cards.dd_over_mll.median():.1f}&times;</b> the barrier. Sizing down does not fix it,
because the edge scales down with the drawdown while the cost floor does not. The two cells
below are the only ones whose risk shape is compatible with a Combine at all, and neither has
statistical evidence behind it.</div>

<h2>The chart that decides the field</h2>
<figure><img src="01_drawdown_vs_mll.png" alt="drawdown against the MLL">
<figcaption>Each point is one strategy on one instrument. Everything right of the red line
breaches Topstep's trailing maximum loss limit on its own historical worst run, before any
resampling. {under} of {n_cells} cells sit left of it.</figcaption></figure>

<h2>The cost cliff</h2>
<figure><img src="02_cost_cliff.png" alt="cost cliff">
<figcaption>Expectancy per trade on commission alone against the same with one tick of
round-turn slippage. {int((normal.expectancy_per_trade > 0).sum())} cells are positive on
commission; {stressed_pos} survive a tick. With a two-minute median hold, slippage is not a
correction &mdash; it is frequently the whole result.</figcaption></figure>

<h2>The two cells that are not rejected</h2>
{surv_html}

<h2>What these mechanisms actually are</h2>
<figure><img src="04_trade_anatomy.png" alt="trade anatomy">
<figcaption>Holding time, maximum adverse excursion and maximum favourable excursion across
every trade in the field. The library is a set of scalps: no strategy has a stop or a target,
so a position ends when the signal changes or the session does.</figcaption></figure>

<h2>Equity and drawdown for the leaders</h2>
<figure><img src="03_equity_underwater.png" alt="equity and underwater">
<figcaption>The five highest-net cells. The lower panel is drawdown; the dashed line is the
$2,000 barrier. Note the vertical scale.</figcaption></figure>

<h2>Where the leaders make and lose it</h2>
<figure><img src="05_regime.png" alt="regime breakdown">
<figcaption>Net P&amp;L by calendar year and by causal trailing-volatility tercile.</figcaption>
</figure>

<h2>Master comparison table</h2>
<p class="sub">Ranked by the declared composite &mdash; barrier compatibility, stressed
expectancy, evidence, daily-limit behaviour and profit factor &mdash; never by net P&amp;L.</p>
{table(show, fmts)}

<h2>Reproduce</h2>
<pre><code>python scripts/strategy_registry.py
python scripts/strategy_lab_run.py
python scripts/strategy_lab_topstep.py
python scripts/strategy_lab_report.py
python scripts/strategy_lab_dashboard.py</code></pre>
</div>"""

    page = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Strategy Backtest Lab</title><style>{CSS}</style></head>"
            f"<body>{body}</body></html>")
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "index.html"
    p.write_text(page, encoding="utf-8")
    print(f"wrote {p.relative_to(REPO)}  ({p.stat().st_size:,} bytes)")
    print(f"  open with:  start {p}")
    print(f"\n  verdicts: {vc}")
    print(f"  cells under the MLL barrier: {under} of {n_cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
