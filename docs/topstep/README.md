# Topstep rulebook — versioned specification

**Rulebook version: `2026.09.13`** (see [VERSIONING.md](VERSIONING.md))
**Retrieval date: 2026-09-13.** All sources are Topstep primary sources: `help.topstep.com`,
`topstep.com`, and the Terms of Use.

This directory is the *human-readable, versioned* rulebook. The *machine-readable* one is
`quant_brain/markets/futures_cme/topstep.py` (retrieved 2026-09-12). This spec supersedes that
module where they disagree; the disagreements are listed in
[§ Corrections to prior work](#corrections-to-prior-work) below and none of them have been
applied to the code — this pass writes documentation only.

## Files

| File | Contents |
|---|---|
| [RULES.md](RULES.md) | The master table. Every rule found, with source, exact quote, hard/soft, and what it affects. Read this first. |
| [COMBINE.md](COMBINE.md) | Trading Combine: profit target, cost, MLL, DLL, consistency, contract caps |
| [XFA.md](XFA.md) | Express Funded Account: $0 start, scaling plan, payout paths, account limits |
| [LFA.md](LFA.md) | Live Funded Account: reserve release, Dynamic Live Risk Expansion, $1,000 floor |
| [PAYOUTS.md](PAYOUTS.md) | Payout mechanics: eligibility, caps by size, resets, timing, methods |
| [PROHIBITED.md](PROHIBITED.md) | Prohibited conduct and prohibited trading strategies. Trading hours live here too, because the flat-time rules are enforcement rules. |
| [VERSIONING.md](VERSIONING.md) | How a rule version is identified, archived, and reproduced by a simulator |

Other tracks write into this directory too. `API.md` and `EXECUTION.md` cover the ProjectX/TopstepX
gateway and the execution-authority gating; they are not part of this rules specification and are
versioned separately by their own track.

## Confidence tiers

The same three tiers `topstep.py` uses, so the two rulebooks can be reconciled mechanically.

| Tier | Meaning |
|---|---|
| `DOC` | Stated on a Topstep-owned page fetched on the retrieval date, with the sentence recorded |
| `SEARCH` | From Topstep's own site via a search summary; the sentence was not seen on the page itself |
| `OWNER` | Not published on any Topstep page reached; the account holder must supply it from their dashboard |

## Method, and the caveat that goes with it

Pages were retrieved with an automated fetch-and-extract step: the page is converted to text and a
small model transcribes the passages asked for. **A quoted sentence in these files is therefore a
transcription of the live page, not a byte-exact copy taken by hand.** That is good enough to make a
rule actionable and to detect a change, and it is not good enough to litigate. Two consequences,
both deliberate:

1. Where a number decides whether real money is spent, it is only marked `DOC` if it was seen on
   **two independent Topstep pages**. The Combine profit target below is the case that matters.
2. `VERSIONING.md` requires the raw page snapshot to be archived alongside the rule version, so a
   future reader can go back to the bytes rather than to this transcription.

Some pages refused full verbatim reproduction on copyright grounds and were re-queried as a
structured extraction instead. `topstep.com/express-funded-account-rules` is the notable one.

## Corrections to prior work

`quant_brain/markets/futures_cme/topstep.py` is right about the hard part — the MLL is an
end-of-day-trailing threshold with an intraday breach test, and `EOD_TRAIL_INTRADAY_BREACH` is the
correct model. Six things in it are now wrong or incomplete. **No code was changed in this pass.**

| # | Prior work says | This spec finds | Severity |
|---|---|---|---|
| 1 | Combine consistency defaults to `strict` = 50% of **total profit**; the 55%-vs-50% question is open | **55% of total profit.** The page carries a worked example — "$1,600 best day ÷ $3,000 total profit = 53%" — which fixes the denominator, and "55% is a hard line" plus two other Topstep pages fix the threshold. The correct reading is the one the module already names `doc_calc`. | The default is *stricter* than reality, so it understates the pass rate. Safe direction, wrong number. |
| 2 | `XFA_STANDARD_CAP = 5_000`, `XFA_CONSISTENCY_CAP = 6_000` applied to every account size | Caps are **per account size**: standard $2,000 / $3,000 / $5,000 and consistency $3,000 / $4,000 / $6,000 for $50K / $100K / $150K. The module's constants are the $150K row. | **Overstates the $50K payout by 2.5x.** Wrong direction. |
| 3 | `take_payout` reduces the balance and leaves the MLL where it is | After the **first** payout the MLL is set to **$0 permanently**. The remaining balance becomes the effective floor. | Changes the risk budget after every payout. Not modelled at all. |
| 4 | `COMBINE_PROFIT_TARGET` is `SEARCH` tier and `combine()` refuses it by default | $3,000 / $6,000 / $9,000 seen on two Topstep-owned pages. Promotable to `DOC`. | Closes the #1 owner blocker. |
| 5 | Monthly cost absent entirely | $49 / $99 / $199 (Standard path) and $95 / $149 / $229 (No Activation Fee path). | Closes the #2 owner blocker. |
| 6 | `DLL_DOC` points at article `8284207` | The DLL article is now `10490293`. `8284207` still resolves but the canonical URL moved. | Link rot only; the numbers are unchanged. |

Two things the module records as unknown are **still unknown** and were not closed by this pass: the
XFA Scaling Plan ladder (published only as an image) and any explicit minimum-trading-days rule for
the Combine. See [RULES.md § Not found](RULES.md#not-found-on-any-official-page).
