"""Assemble the full report for one strategy across the execution ladder.

THE ORDER OF THE SECTIONS IS THE ARGUMENT
-----------------------------------------
A reader who stops after the first screen should already have the information that would
change their mind. So the disqualifiers come first - breach, reconciliation, provisional
sample - then what was assumed, then what was measured, then what could not be measured at
all, and only then the P&L across the ladder.

The ladder is printed in full, always. A report that shows one rung is not a shorter report,
it is a different claim.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from topstep_backtester.reporting import unmodeled
from topstep_backtester.reporting.cards import ExecutiveCard, card_from_run
from topstep_backtester.reporting.montecarlo import HorizonRow


def _ladder_table(runs: Mapping[str, Any]) -> str:
    lines = [
        "| execution profile | fills | round trips | net P&L | ending balance | best day | "
        "max DD | verdict | reconciled |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for profile_id, run in runs.items():
        stats = run.stats
        verdict = getattr(run.result.verdict, "name", run.result.verdict)
        lines.append(
            f"| {profile_id} | {run.result.trade_count} | "
            f"{getattr(stats, 'closed_trades', 0)} | "
            f"${getattr(stats, 'net_pnl', 0):,.2f} | "
            f"${run.result.ending_balance:,.2f} | "
            f"${run.result.best_day:,.2f} | "
            f"${getattr(stats, 'max_drawdown', 0):,.2f} | "
            f"{verdict} | {'yes' if run.reconciled else 'NO'} |"
        )
    return "\n".join(lines)


def _horizon_table(rows: Sequence[HorizonRow]) -> str:
    lines = [
        "| horizon | P(pass) | P(MLL breach) | P(consistency blocked) | P(target not "
        "reached) | provisional |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.label} | {row.pass_probability:.3f} | "
            f"{row.mll_breach_probability:.3f} | "
            f"{row.consistency_blocked_probability:.3f} | "
            f"{row.target_not_reached_probability:.3f} | "
            f"{'YES' if row.provisional else 'no'} |"
        )
    return "\n".join(lines)


def build_report(
    runs: Mapping[str, Any],
    *,
    quoted_profile_id: str,
    horizons: Sequence[HorizonRow] = (),
    monte_carlo_caveat: str = "",
    title: str = "",
) -> str:
    """The whole report, as markdown.

    ``runs`` maps execution profile id to ``RunResult`` and must contain every rung that was
    run. ``quoted_profile_id`` names the rung the headline card is drawn from.
    """
    if quoted_profile_id not in runs:
        raise KeyError(
            f"the quoted rung {quoted_profile_id!r} is not among the runs "
            f"{sorted(runs)}; a report cannot quote a rung it did not run"
        )

    quoted = runs[quoted_profile_id]
    card: ExecutiveCard = card_from_run(quoted)
    manifest = quoted.manifest

    unreconciled = sorted(pid for pid, run in runs.items() if not run.reconciled)
    breached = sorted(
        pid for pid, run in runs.items() if run.result.breach is not None
    )

    parts: list[str] = []
    parts.append(f"# {title or quoted.spec.spec_id}")
    parts.append("")

    # ---- 1. the disqualifiers, first ------------------------------------------------------
    parts.append("## 1. Read this before any number below")
    parts.append("")
    parts.append(f"**{card.banner()}**")
    parts.append("")
    if unreconciled:
        parts.append(
            f"- **RECONCILIATION FAILED** at {unreconciled}. The engine and the independent "
            f"arithmetic in `reference/arithmetic.py` disagree about the money. Nothing in "
            f"this report is quotable until that is resolved."
        )
    else:
        parts.append(
            "- Every rung reconciled exactly against independent arithmetic that shares no "
            "code with the engine."
        )
    if breached:
        parts.append(
            f"- **ACCOUNT BREACHED** at {breached}. A breached account has no P&L worth "
            f"discussing: the run ended because the account was liquidated."
        )
    if card.provisional:
        parts.append(
            "- **PROVISIONAL.** Upstream flagged the sample as too small for its statistics "
            "to be load-bearing. Treat every distributional figure below as descriptive of "
            "this sample only."
        )
    parts.append("")

    # ---- 2. the headline card --------------------------------------------------------------
    parts.append("## 2. Executive result card")
    parts.append("")
    parts.append(f"Quoted at **{quoted_profile_id}**. Other rungs in section 5.")
    parts.append("")
    parts.append(card.to_markdown())
    parts.append("")

    # ---- 3. what was assumed ---------------------------------------------------------------
    parts.append("## 3. What produced this")
    parts.append("")
    parts.append(f"```\nrun_id     {manifest.run_id}\n"
                 f"spec       {quoted.spec.spec_id}\n"
                 f"bars       {manifest.bars_hash}  ({manifest.bar_count:,} bars, "
                 f"{manifest.instrument} {manifest.bar_interval}, {manifest.data_form})\n"
                 f"contracts  {', '.join(manifest.contract_ids)}\n"
                 f"engine     topstep-backtest {manifest.upstream_version} "
                 f"(API {manifest.upstream_api_fingerprint})\n"
                 f"layer B    {manifest.code_hash}\n"
                 f"account    {quoted.account_profile.profile_id}\n```")
    parts.append("")
    parts.append(f"Consistency rule in force: **{quoted.account_profile.consistency_pct}** "
                 f"of total profit. {quoted.account_profile.consistency_basis}")
    parts.append("")
    if quoted.spec.material_ambiguities():
        parts.append("### Material ambiguities in the specification")
        parts.append("")
        parts.append("| ref | question | reading taken | authority |")
        parts.append("|---|---|---|---|")
        for item in quoted.spec.material_ambiguities():
            parts.append(
                f"| {item.ref} | {item.question} | {item.reading_taken} | {item.authority} |"
            )
        parts.append("")

    # ---- 4. Monte Carlo ---------------------------------------------------------------------
    parts.append("## 4. Pass probability by horizon")
    parts.append("")
    if horizons:
        parts.append(_horizon_table(horizons))
        parts.append("")
        if monte_carlo_caveat:
            parts.append(f"_{monte_carlo_caveat}_")
    else:
        parts.append(
            "Not run. A pass probability is only meaningful once the underlying result "
            "reconciles and the sample is large enough to resample; see section 1."
        )
    parts.append("")

    # ---- 5. the ladder -----------------------------------------------------------------------
    parts.append("## 5. The execution ladder, in full")
    parts.append("")
    parts.append(_ladder_table(runs))
    parts.append("")
    parts.append(
        "Rungs are fixed assumptions, not a search space. The rung that flatters a strategy "
        "is not the rung to quote; the question this table answers is how much worse "
        "execution would have to be before the conclusion changes."
    )
    parts.append("")

    # ---- 6. what could not be measured ---------------------------------------------------------
    parts.append("## 6. What this pipeline cannot tell you")
    parts.append("")
    parts.append(unmodeled.markdown_table())
    parts.append("")
    parts.append(
        "These are not omissions from this run. They are capabilities the upstream engine "
        "does not have, and Layer B will not manufacture them."
    )
    parts.append("")

    return "\n".join(parts)


__all__ = ["build_report"]
