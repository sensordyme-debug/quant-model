# QUANT MODEL — FULL SYSTEM AUDIT

> **ERRATA, added 2026-09-14.** Preserved as a record. Two figures could not be reproduced
> and one is superseded:
>
> 1. **"+0.0551 ticks/leg over 68,388 legs"** (lines 64, 229, 346) could not be reproduced.
>    The mechanism is real and reproduces, but neither the rate nor the leg count matches any
>    rule reconstructible on any store under either session filter. Independent measurements
>    with the rule stated are in `docs/DATA.md` and `docs/FUTURES.md`.
> 2. **"Early closes (210 bars) pass the >=200-bar filter as full sessions"** (line 207) was
>    correct and is now fixed. `session_frames` requires a structurally complete session.
> 3. **"two-contract days are dropped"** (line 207) describes a filter that drops nothing:
>    there are zero mixed-contract days inside the RTH window in any store. Containment of the
>    roll gaps comes from the rolls landing outside the window and from per-session feature
>    building, not from that filter.
>
> The corrections this document already carries inline - the 9,110-line reachability figure
> and the ML track's "exactly and only three columns" - stand as written.

**Red-team audit of the Quant Model repository and the Quant Brain knowledge base.**

| | |
|---|---|
| Repository | `C:\Users\ashur\Quant-Model\quant-model` |
| Remote | `https://github.com/sensordyme-debug/quant-model.git` |
| Knowledge base | `C:\Users\ashur\Quant-Model\quant-model\Quant Brain` (1,128 `.md`, 255,897 files, 4.2 GB) |
| HEAD at audit | `6c8f9196b99d3314c7334fb88385b87691d1d2ac` · branch `main` · `origin/main` 0/0 |
| Audit date | 2026-09-13 → 14 |
| Question | *Can this system be trusted as a futures research and backtesting platform?* |
| Answer | **No, not today — and the reason is not the code. Every research conclusion the system has produced is currently unfalsifiable, while the engineering substrate underneath is materially better than that fact suggests.** |

**Scope note.** The brief instructs that this is not an audit of a separate "prop-firm repository." There is no separate repository: `sensordyme-debug/quant-model` at this path is one repo, and the Topstep/prop-firm code (`quant_brain/markets/futures_cme/topstep.py`, `venues/propfirm.py`) is one branch of work inside it alongside the equity/LEAN and ML branches. All findings below concern this repository.

**Method.** Seven independent tracks: architecture (lead), Quant Brain vault, ML, backtest-engine *exercise*, data lineage, testing/mutation, governance+AI-safety+reproducibility. Every agent read-only; every load-bearing claim re-verified by the lead. Nothing in the repository was modified except this file. Nothing was committed or pushed.

**Epistemic labels used throughout:** PROVEN · VERIFIED · TESTED · SUPPORTED · PROMISING · UNPROVEN · UNKNOWN · CONTRADICTED · REFUTED · INVALID · BLOCKED.

---

## 1. EXECUTIVE SUMMARY — what this system actually is today

Quant Model is **a well-engineered research substrate wrapped around a research process that cannot yet produce a trustworthy answer.** Those two halves must be judged separately, because they score very differently.

**What is genuinely good.** Secrets hygiene is excellent (zero secret-shaped matches across all 5,947 git objects — VERIFIED). Futures contract mechanics are flawless (tick value *derived* not stored; 14/14 independent P&L cases match hand arithmetic, 0 mismatches — PROVEN). The futures bar data is clean (0 duplicates, 0 out-of-order, 0 bad OHLC across 1.6M rows, DST correct — PROVEN). Both feature libraries are strictly causal under perturbation probing (PROVEN). All four backtest accounting identities close to 1e-10 (PROVEN). The two `Book` classes really are identical, as their docstring claims (PROVEN). The pre-registered futures baseline was **reproduced bit-for-bit**, all 9 statistics, fingerprint matched (PROVEN). And the project's culture of self-refutation is real and rare: it withdrew its own best ML result, retracted a look-ahead survivor while keeping its trial in the denominator, and its critic track attacks its own strongest claims.

**What is broken.** No result the system has produced can currently be trusted, for six independent reasons, each measured:

1. **No engine has a lookahead guard.** A one-bar-ahead oracle fed to the futures funnel earns **100.00%** of the theoretical ceiling and **clears every gate**. `sweep_s19.simulate` silently recorded **CAR 1,953% / Sharpe 16.17** for a same-day leak. (PROVEN by execution.)
2. **The headline research claim is arithmetically wrong.** "544 hypotheses, 0 survivors" is really **128 distinct trading rules**: 416 of 544 (76.5%) recorded `trades: 0` — the threshold never fires, so they are 104 replicas of buy-and-hold per market, and their cost was booked as **$0** for holding a position across 326 sessions. (VERIFIED in the ledger.)
3. **The funnel cannot detect any realistic edge.** Measured σ on MES is $222.70/session ⇒ MDE at the family's own bar is **$60.70/session**; power to find a genuine **$20/session** edge is **1.7%** (MNQ: 0.2%). "0 survivors" is a power statement, not a market statement.
4. **The prop-firm gate's verdicts are artifacts.** The path resampler rescales one day's intraday shape by `x/template.pnl`, producing minima of −$81,444 to −$608,290 where the true worst marks are −$692 to −$1,183. Corrected with an object-level resampler, **3 of 5 real ES hypotheses clear the funnel's own 10% pass gate.** (PROVEN by re-running.)
5. **The multiplicity machinery cannot read the main ledger.** `Ledger.all()` parses **0 of 1,653** equity rows; the two ledgers share **zero keys**; `trials('s1_momo')` returns **0**. If wired tomorrow it would apply the n=1 bar of 1.96 to a search of ~5,500 cells. (VERIFIED by execution.)
6. **No holdout has ever been carved.** `Holdout.spend()` has never been called. The window labelled "OOS 2020-2026" was inside the selection set — established by the repository's own S-33/S-38/S-40 audits, and the correction is *"owed, not taken."*

**And two live defects with money attached.** Both scheduled tasks fire **tomorrow**: `Quant Intraday Sleeve` 09:25, `Quant Paper Rebalance` 15:45 (VERIFIED, `Get-ScheduledTask`). The 09:25 runner will crash on an `UnboundLocalError` before its first decision (fails closed); the 15:45 runner will trade normally through an **empty risk chain**, authorised by an existence-only check on a gitignored file that names a **different champion** (S-12/`35ce0a9`) than the one it will trade (S-18/`d41aefe`).

**The verdict in one line:** the system is not lying on purpose — it is unable to tell whether it is lying, and it has been building level-8 capabilities on level-1 foundations.

---

## 2. OVERALL SCORE

# 26 / 100

**This is not an average.** It is bounded by the binding constraint: *no research conclusion this system has produced is currently falsifiable.* Security (86) and futures data quality (62) are genuinely good and do not lift the total, because a trustworthy pipeline is a conjunction, not a sum. Equally, the low score should not be read as "bad code" — the substrate would score in the 50s–60s if the research process around it were sound.

---

## 3. SCORECARD (0–100, evidence-based)

| # | System | Score | Basis |
|---|---|---|---|
| 1 | **Overall Quant Model** | **26** | Bounded by unfalsifiable results, not by code quality |
| 2 | Quant Brain / Obsidian | 28 | Real intellectual quality; 54.4% unsourced, zero `validated: true`, frozen 2026-08-26, describes a different project |
| 3 | Quant Brain architecture | 22 | Three codebases, three self-declared canonical sources, 267 broken links, 156 orphans, ID collision with live strategies |
| 4 | Quant Brain ML | 20 | Not connected to this repo at all |
| 5 | ML research validity | 22 | **NO EDGE SHOWN**; a P0 future-split leak is live at HEAD in the best-ever arm |
| 6 | Futures research | 22 | 128 real hypotheses not 544; two-sided pass rule; family rename resets N |
| 7 | Futures data | **62** | Bars provably clean and specs correct; unhashed, un-rolled, one regime, DST roll bug |
| 8 | Futures backtesting | 24 | Oracle clears every gate; one RT/session uncharged; 76.5% degenerate |
| 9 | Backtest execution realism | 20 | No liquidity constraint; close-only stops; measured +0.0551 tick/leg fill subsidy |
| 10 | Statistical validity | 24 | Correct library, zero callers, cannot parse the ledger; HAC under-corrects ×1.22 |
| 11 | Research governance | 18 | 6 of 8 failure modes not prevented; two already occurred |
| 12 | Strategy quality | **8** | Zero validated strategies; deployed strategy rejected by its own research |
| 13 | Robustness | 20 | Parameter shelves checked; no regime, instrument, cost or delay testing that survives |
| 14 | Risk engine | 26 | Shape correct and provable; one limit in one chain; other chain empty |
| 15 | Execution architecture | 22 | Two P0s in the deployed runner; FLATTEN is an unverified label; no stop ever placed |
| 16 | Software engineering | 34 | Clean core ideas; 44.3% unreachable, 141 sys.path hacks, 305 script→script edges |
| 17 | Testing | 30 | 1,938 tests, **6 of 14 mutations survived**, suite mutates live state |
| 18 | **Security** | **86** | Zero secrets in tree or history across 5,947 objects; correct gitignore; redaction tested |
| 19 | AI safety | 24 | Agent can reach paper execution with no human step, invisibly to git |
| 20 | Reproducibility | 22 | One result reproduced bit-for-bit; no manifest, no hashes, 0 rows `reproducible: true` |
| 21 | Observability | 40 | Structured JSONL logging is good; alerts undelivered since 09-10; live state written by tests |
| 22 | Prop-firm readiness | 20 | Engine exists, is advisory, wrong units, wrong flat time |
| 23 | Topstep readiness | 18 | Combine boundary logic right; funded stage flatters six ways |
| 24 | Paper-trading readiness | 12 | Runner crashes; other runner has no risk chain |
| 25 | Live-trading readiness | **3** | Everything above; only the human-held Gateway login separates code from money |

**The bottlenecks, in order:** (1) no untouched holdout anywhere; (2) no lookahead guard on any engine; (3) the funnel's cost and degeneracy arithmetic; (4) multiplicity machinery structurally unable to read the ledger; (5) the two deployed-runner P0s.

---

## 4. ARCHITECTURE MAP (measured by AST, not read from docs)

### 4.1 The real numbers

| metric | measured |
|---|---|
| `quant_brain/` | **53 modules, 18,114 lines, 90 intra-package edges** (71 top-level, 17 in-function, 2 TYPE_CHECKING) |
| Import cycles | **2** — `core.execution ↔ core.risk`; `venues.base ↔ venues.propfirm` |
| Layer inversions | **1** — `core.dataquality → markets.equity_us` (in-function) |
| Reachable from any non-test importer | **36 / 53** |
| **Unreachable (import-level)** | **17 modules, 8,023 lines = 44.3%** |
| **Loaded by the 6 production entry points** | **15 / 53** |
| `sys.path` mutations | **141 files** |
| script→script import edges | **305**; fan-in: `intraday_common` 53, `lean_prices` 35, `sweep_s19` 25 |
| `algorithms/` importing `quant_brain` | **ZERO** |
| Tests | **1,938 across 68 files**; `-m runner` selects **248** |
| Tests exercising unreachable code | **533 (27.5%)** |

*Correction to the prior internal audit, which claimed 13 modules / 9,110 lines: that figure wrongly included `sizing.py` (reachable via a function-local import at `governor.py:105`) and `lean_calendar.py` (via a package `__init__`). 9,110 − 1,074 reconciles to 8,023 within 13 lines.*

### 4.2 The documented pipeline vs the executed one

**Documented** (`ARCHITECTURE.md` §4a-ii, `docs/IMPLEMENTATION_REPORT.md`):
`DATA → VALIDATION → FEATURES → SIGNAL → sizing.Sizer → idempotency.intent_id → RoutedExecutor[journal → Governor → adapter → journal] → OrderMachine → protection.verify → Reconciler`

**Executed** by both live runners:
```
pandas frame → signal dict {symbol: weight}
  → hand-rolled weight→share sizing, caps read from a scripts/ constants file
  → OrderIntent            (no intent_id, no journal)
  → RiskChain              EMPTY in paper_trade.py:797
                           ONE duplicate daily-loss limit in intraday_trader.py:567
  → IBKRAdapter.submit → ib.placeOrder
```

**Every binding limit is applied to weights before an `OrderIntent` exists**, by convention, in **nine inconsistent copies**: `intraday_common.py:69-74` (0.20/1.6/2.5%), `live/intraday_config.json` (0.15/1.5), `active/signal.py` PARAMS (0.15/1.0), `lev_revert`/`xsect` (0.20/0.10, 1.20), `intraday_backtest.RISK`, `dashboard/sources.py:77` (hard-coded `368, 372, 1.5`), `governor.Limits`, `sizing.SizeLimits`, `propfirm.PropFirmProfile`.

### 4.3 Node-by-node status

| node | EXISTS | CONNECTED | CALLED | TESTED | PROD | verdict |
|---|---|---|---|---|---|---|
| Data ingest (futures) | ✓ | ✓ | ✓ | ✓ | research | sound bars, no hashing |
| Data validation | ✓ | ✓ | funnel only | ✓ | partial | 19 of 20 harness callers skip `validate` |
| Features | ✓ | ✓ | ✓ | ✓ (causal, proven) | research | **STRONG** |
| Signal / strategy | ✓ | ✓ | ✓ | partial | ✓ | 6 of 8 intraday strategies never execute |
| Position sizing (`core/sizing`) | ✓ | imported | **NO CALLER** | 66 tests | ✗ | decorative |
| Cost model | ✓ | ✓ | ✓ | ✓ | research | micros 18% under-charged; RT undercount |
| Execution sim | ✓ | ✓ | **`execute()` never called** | ✓ | ✗ | funnel uses only `round_turn_cost()` |
| Backtest (funnel / intraday / LEAN / pandas) | ✓×4 | ✓ | ✓ | partial | ✓ | no lookahead guard on any |
| Risk chain | ✓ | ✓ | ✓ | partial | ✓ | 1 limit / empty |
| Prop-firm constraints | ✓ | wired to a dry-run venue | **NO CALLER** | ✓ | ✗ | advisory |
| Statistics | ✓ | ✗ | **NO CALLER** | 73 tests | ✗ | cannot parse the ledger |
| Multiple testing | ✓ | ✗ | **NO CALLER** | ✓ | ✗ | decorative |
| Validation / holdout | ✓ | ✗ | **NEVER CALLED** | 38 tests | ✗ | decorative |
| Promotion gate | ✓ | ✗ | **NO CALLER** | 54 tests | ✗ | real path is `evaluate.py` |
| Execution state machine | ✓ | ✗ | **NO CALLER** | ✓ | ✗ | a diagram |
| Protection / brackets | ✓ | ✗ | **NO CALLER** | ✓ | ✗ | no stop is ever placed |
| Reconciliation | ✓ | ✗ | **NO CALLER** | ✓ | ✗ | runner has its own |
| Idempotency journal | ✓ | CLI only | ✗ | ✓ | ✗ | not wired |
| Venue registry | ✓ | ✗ | **NO CALLER** | 59 tests | ✗ | 20 capabilities, one adapter that cannot send |
| Knowledge base link | ✗ | ✗ | ✗ | — | ✗ | **no code reads the vault** |

---

## 5. QUANT BRAIN ASSESSMENT

**Classification: (F) a mixture — a genuinely good research notebook and archive *for a different project*, wearing source-of-truth rhetoric.**

Measured: 255,897 files / 4.2 GB / **1,128 `.md`** (885 substantive notes). 290 `type: source` (212 machine-transcribed YouTube); **481/885 (54.4%) with no provenance**; **zero notes carry `validated: true`**; 8,573 wikilinks with **267 broken** and **156 orphans**; 212 PDFs of which **81 of 82 research papers have no note**. Every note created 2026-08-21…26; nothing since. Authored on macOS under `/Users/donov`, Python 3.13, remote `github.com/DonovanWillis/QuantModel`.

It contains **three codebases**: the repo's own `quant_brain/` (53 files), the vault's `QuantModel/src/catalyst` (332 files, 3,917 test functions, an options-convexity system), and `_System/quantbrain/` (30 files). None imports another. Four documents each declare a different tree canonical. **Zero Topstep, prop-firm, ProjectX or MNQ content.** **No code in this repository reads the vault** — `core/knowledge.py`, the only retrieval component, indexes `experiments.jsonl` / `backlog.md` / `journal*.md`, and is itself dead code.

### The decision-safety answer: **YES, an agent can be misled, and it is quantified**

The same 34 strategies carry **180 result notes across 5 parallel campaigns, and on 15 of 34 (44%) the campaigns disagree on the *sign* of the return.** `S-0012` returns +3.10%, +3.22%, +0.56%, or UNRUN depending on which note is retrieved. The single note carrying the disqualifying benchmark — *"equal-weight buy-and-hold returns +575.87% — most of the return is the universe, not the rule"* — is a **graph orphan** with no inbound links, so a link-following agent will never reach it. `Vault Map.md` republishes all 34 in bold **with the `BEST-GUESS / VERY LOW` disclaimers stripped**. All 9 dashboard notes render to a file-reading agent as literal `$= dv.pages(...)` strings. Vault IDs `S-00xx` collide with live repo strategy IDs `S-xx` in the same grep namespace.

**Methodology cross-check** — the vault's own rules against the repo's practice:

| vault rule | repo practice | status |
|---|---|---|
| Next-bar-open fills (`Backtesting Master Specification.md:31`) | `intraday_backtest.py:132` complies; the futures funnel fills at the decision bar's close | **PARTLY FOLLOWED** |
| "A final holdout is touched once… optimising against it, ever, voids the run" (`:38`) | `Holdout.spend()` never called; `backlog.md` reads its informal holdout **14 times** | **VIOLATED** |
| "A trial is issued when a hypothesis is *recorded*" (`_Trial Ledger.md`) | 1,653 equity rows have no trial field; futures resettable by a free-text `.v2` rename | **VIOLATED** |
| Deflate against the **combined** 112 trials | Never inherited; the vault's own two mandatory documents hardcode a stale **101** | **NOT INHERITED, and internally stale** |

**Safety.** **P0: `Quant Brain/.codex/config.toml`** sets `approval_policy = "never"` and `sandbox_mode = "danger-full-access"`. Its own header says *"DO NOT commit this file to version control"*; `git check-ignore` confirms **it is not ignored**. `Quant Brain/.claude/helpers/auto-commit.sh` runs `git add -A` → commit → **`git push origin "$branch"`** with `AUTO_PUSH` defaulting to `true` (`:16`); because the vault is not its own git repo, that targets **the trading repo's public origin**. This is **latent, not live**: nothing currently invokes it, and there is no `.claude/` at the repo root, so the vault's hooks fire only if Claude Code is opened with `Quant Brain/` as the project directory.

**Genuine strengths:** 287/287 transcript paths resolve; the most-cited source is externally verified real (SSRN 6559538) with every figure matching; `11 OVERFITTING CONTROLS.md` and `_Source of Truth.md` are **better methodology than the host repository practises**; a live `Contradictions/` register with `resolution: none — deliberately unresolved`; and **zero prompt-injection strings and zero shell blocks in any research folder** — the exposure is structural, not adversarial.

**Verdict: the vault is neither evidence nor contamination — it is un-inherited intent, plus a structural hazard from its presence in the working tree.**

---

## 6. ML ASSESSMENT

**Verdict: NO EDGE SHOWN.**

Every model item F-1…F-21 is REFUSED by its own pre-registered rule; the two ADOPTED items (F-23, F-24) adopt a *print*, not a model. In model-class terms the entire programme is **one gradient-boosted tree re-run 20 times** — only F-1, F-3 and F-12 fit anything; F-7…F-21 reuse `f1.GRID["mid"]` on F-1's panel.

**ML-01 (P0, live at HEAD).** `ml_f15.auction_daily` divides **split-adjusted** bar prices by **raw** auction prices (`alpaca_data.py:39` vs `ml_f15.py:182`). On 18.3% of rows / 14 names, `auc_cdrift` correlates with the **future** cumulative split factor at Spearman **+0.844** (NVDA +1212.3 pre-split vs +0.0016 post). This is a future-information leak: the feature encodes whether a stock is about to split.

**The corroboration that makes this decisive.** Two agents on unrelated mandates converged on the same admitted feature sets. I read `data/f1/f16_admitted.json` and `f17_admitted.json` directly: **2019** `amihud30, clv30, x_clv30, cs_clv30` · **2020** `amihud30, ofi5` · **2021** `clv30, x_clv30, cs_clv30` · **2024** `auc_osz_adv` · **2025–26** `auc_ofade, x_auc_ofade, cs_auc_ofade`. The 2024–26 admissions are the split-factor leak; the 2019–21 admissions include `amihud30`, which the data track independently showed selects **100% SOXS** rows (below). **Every year's admitted feature set is contaminated by one mechanism or the other** — and this is F-16's $412/day arm, the track's best-ever net. *(Correction to the ML agent: the sets are not "exactly and only" three columns; the conclusion is nonetheless stronger, because there are two independent contamination mechanisms rather than one.)*

**F-1, the one real signal.** IC reproduced **exactly** (+0.01133, t +4.7426). Labels genuinely non-overlapping (`HOLD == STEP == 6`). It **survives** HAC, day-clustering (+4.84) and a 21-day block bootstrap (+4.35, p<1e-5, robust up to 3,590 trials). It is real. It is also **non-stationary** — +0.01935 → +0.01093 → **−0.00012** by test year, second-half t +0.95 — and **unmonetisable**: 0.797 bps earned against a 0.892 bps commission floor, **−$2,206/day**.

**The baseline nobody had built.** A one-line 15-minute reversal (`-r3`) scores **IC +0.01529 (t +4.86)** against the 38-feature GBDT's **+0.01123 (t +4.69)** on identical rows. Orthogonalised, the reversal keeps **more** (+0.01285) than the GBDT (+0.00685). Book-gross advantage of the GBDT: +$642/day at t +1.06 — not significant.

**Holdout status.** 151 ML ledger rows, **145 touch one window** (2019-01-02→2026-09-10). **Nothing is a true holdout**, and every F-16/F-17 design parameter was fixed by reading that window in earlier runs.

**Deployed path — PROVEN SAFE today.** `S1_ML_SCORES` (not `S1_ML_MODE`) is the switch; `paper_trade.py` never sets either. **No ML output has ever reached a paper order.** One verified landmine: on the export's last 3 dates all 9 `RANK_UNIVERSE` names are NaN → `-1e9` → the sleeve silently funds nothing.

**Genuine strengths:** F-1's causal constructions are correct where it matters; F-11 and F-12 both refuse a pre-declared cell *while a test-max cell would have passed*; F-12's scrambled-sigma control is the best null in the tree and it kills F-12; the track withdrew its own best result and concluded four of its own refusals were coin flips.

---

## 7. FUTURES ASSESSMENT

**Data — the strongest subsystem.** ES/MES/NQ/MNQ: tz-aware UTC, start-stamped, **0 duplicates, 0 out-of-order, 0 bad OHLC** across 1.6M rows, DST correct at both 2025-11-03 and 2026-03-09. RTH sessions 326/261/326/261.

**Contract mechanics — PROVEN CORRECT.** Tick value is *derived* (`multiplier × tick`), removing the classic three-way disagreement. All 12 contracts match published CME values; **14 of 14 independent P&L cases match hand arithmetic, 0 mismatches** (MES +1.25 pt = $6.25; NQ −10 pt ×2 = −$400; ES 0.25 pt = $12.50; MNQ 100 pt ×3 = $600; GC, CL, YM, RTY, MYM, M2K, MCL, MGC all correct).

**Defects.** Rolls are **raw stitches with no marker** (ES +57.75/+59.75/+50.25/+53.00; NQ up to +264.00; MNQ +276.50), contained today only because features are built per session and two-contract days are dropped. A **DST bug** hard-codes the roll page stamp at `21:00` UTC, so the December roll lands mid-session — my own measurement independently shows it at 16:00 ET while the other three sit at 18:00 ET; it fabricates NQ **+1.0286%**, the 2nd largest of 447,269 consecutive 1-minute moves. Early closes (210 bars) **pass the ≥200-bar filter as full sessions**. Micro commissions are **18% under-charged** vs the official $1.22 RT; MES/NQ/MNQ spreads were **never measured** and inherit ES's 1 tick. **Six** hard-coded spec tables exist, with a 28% MES commission disagreement between them.

**Research.** "544 hypotheses" = **128 distinct rules** + 416 buy-and-hold replicas booked at $0 cost. 41 PASS verdicts of which **40 have negative t** (worst −11.92 at −$133/session, printed as *"survives 65-trial correction"*); the **only** positive PASS (+6.25) is the retracted look-ahead. `rel_volume > +1.00 dir -1` carries an **identical** t = −11.92 in both `.threshold_grid` and `.v2`, proving the rename duplicated rather than replaced. **All 817 rows have `provenance: null` and no commit hash.**

**Power (measured σ, not assumed):**

| | sessions | σ $/session | s.e. | MDE @ family bar | power for a real $20/session edge |
|---|---|---|---|---|---|
| **MES** | 261 | 222.70 | 13.79 | **$60.70** | **1.7%** |
| **MNQ** | 261 | 485.50 | 30.05 | **$132.20** | **0.2%** |
| ES | 326 | 2,085.90 | 115.53 | $508.30 | 0.0% |
| NQ | 326 | 4,492.20 | 248.80 | $1,094.70 | 0.0% |

*(σ is for the funnel's own always-in family; a strategy in the market less often would have lower σ and better power.)*

---

## 8. BACKTEST ASSESSMENT — can it produce trustworthy futures results?

**No — PROVEN by exercising the engines, not by reading them.**

- **Oracle test:** a one-bar-ahead oracle earns **exactly 100.00%** of the theoretical `Σ|Δc|·mult` ceiling and **clears every gate** (cost 47.2%, Topstep 100%, WF 5/5). `sweep_s19.simulate` recorded **CAR 1,953% / Sharpe 16.17** for a same-day leak and **CAR 2,057% / Sharpe 18.21** for an oracle, silently. `sweep_s25`'s `weights_fn(index[i])` bypasses the causality window entirely (CAR 2,133%, Sharpe 18.95). **No lookahead guard exists in any engine.**
- **Fill subsidy:** the funnel fills at the decision bar's close — measured **+0.0551 ticks/leg over 68,388 legs** (random-signal control +0.0005), worth **+51%** of gross P&L on a mean-reversion signal.
- **Cost:** `int(abs(diff(pos, prepend=0)).sum()/2)` floors an always-odd leg count and never charges the end-of-session flatten — provably exactly one RT short, always. Uncharged on the ES family alone: 44,336 RT = **$731,544** at ES's $16.50/RT, **3.5× the family's entire |gross| of $208,215**. Re-running the 60% cost gate with the RT restored **reverses 16 of the 26 cost-gate survivors**.
- **Liquidity:** the intraday harness has **none** — a 985-share order fills bit-identically against a 1-share bar and a 100,000-share bar.
- **Validation:** `run()` never validates and 19 of 20 programmatic callers skip it. A 1e9 price books `net_profit_pct = +88,761,473`; a zero price invents a daily-limit stop; a duplicate timestamp fabricates $22.49 of cost.
- **Stops:** ORB's are close-only, so a bar piercing both stop and target books **neither** (mean unmarked intrabar excursion 14.81 bps, p95 42.85).
- **Execution sim:** fills **NaN quantities**, lets a NaN position defeat the position cap, and **refuses risk-reducing trades** when already over the cap.

**Proven strong by the same tests:** both feature libraries strictly causal (17 and 24 columns, zero leakage); **all four accounting identities close to 1e-10**; the two `Book` classes are genuinely identical across five stress cases; gap fills are pessimistic (5.50 pts through the stop); roll handling correct by construction ($43,538 of cross-session jumps never touched); passive limits refused as documented; `round_turn_cost` exact at 1 contract.

---

## 9. RESEARCH ASSESSMENT — can it discover an edge without fooling itself?

**Not today.** The loop is `AGENTS.md:50-68`: read backlog + `champion.json` + **the last 20 lines** of a 1,653-row ledger → *"pick the highest-value open hypothesis, **or a promising variation of the champion**"* → backtest → *"compare with the champion"* → promote on **CAR** → repeat, six scopes in parallel, ~100 commits/day, with an LLM performing the interpret-and-choose-next step.

**Governance, mechanically assessed:** of eight failure modes, **one** is prevented by mechanism, **one** in theory but unused, and **six are not prevented**. Two have already occurred. **An AI agent is permitted to optimise against the test set — and has.** The repo's own critic records that the shipped crisis-switch cell is *"the argmax of its own 36-cell grid on the half this repository labels out-of-sample (rank 1 of 36) while sitting below the median in-sample (rank 24 of 36)… hindsight in full."* `champion.json` still quotes those figures as OOS, and the fix is blocked by the governance rule itself — the label edit is *"owed, not taken"* because `AGENTS.md` reserves the file to `--promote`.

**Promotion criteria, verified in the file:** `must_beat: ["Compounding Annual Return"]`, min_trades 30, sharpe_tolerance 0.03, dd tolerance 1 pt, max dd 35%. *"Owner decision 2026-09-09: return-first."* **No significance test, no multiplicity, no OOS requirement.**

**A correction in the repository's favour.** The champion's *promotion decision* was made on the **2 bp cost column**, not the zero-cost one (`note`: *"the promotion below was decided on the 2.0 column"*), and `evaluate.py` refuses mismatched-cost comparisons. The repo also records a **pre-registered factorial** giving the honest all-in figure: **18.785% CAR** with spread + financing + clock-lag charged together, interactions ≤0.026 CAR points. The real defect is narrower than "promoted on a zero-cost number": the **displayed** `stats` block remains the zero-cost column (24.403%) and downstream documents quote it.

---

## 10. RISK / EXECUTION ASSESSMENT

**Enforced vs advisory** (ENFORCED = a runner cannot reach the venue without passing it):

| control | verdict |
|---|---|
| daily loss (2.5% NAV) | ENFORCED for intraday MARKET entries — **but blind**, because the book is frozen (below) |
| per-symbol / gross caps, RTH refusal, HALT flatten, approval-file existence, authority-at-construction | ENFORCED (runner code, pre-intent) |
| `paper_trade.py` chain | **EMPTY — no risk engine at all on the 15:45 runner** |
| max risk/trade, profit stop, drawdown, MLL buffer, contract & micro limits, trades/day, consecutive losses, cooldown, volatility scaling | **NO CALLER — advisory** |
| bracket verification, idempotency journal, session readiness, reconciliation, order state machine | **NO CALLER — advisory**; no stop is ever placed by either runner |

**The two P0s, both proven at bytecode/runtime level:**
- `intraday_trader.py:891` reads local `t` before its sole assignment at `:922`, inside the loop spanning 887–931 (`LOAD_FAST_CHECK` at 891, `STORE_FAST` at 922). `live()` raises `UnboundLocalError` immediately after the "INTRADAY start" alert. **Zero tests call `live()`.**
- `intraday_trader.py:349` aliases `self.open = self.adapter.open`; `settle():444` rebinds it. After the first `settle()` all adapter-placed fills are invisible: 4 bars → 4 orders / 4,000 shares for a strategy wanting 1,000 once, `book.pos == {}`, EOD flatten computes `{}`. **The crash currently masks this.**

**FLATTEN is a trusted label.** `risk.py:85-89` lets any FLATTEN bypass every engine and switch; nothing verifies it reduces a broker-sourced position; `LiveExecutor.submit(flatten=True)` labels the whole batch. A BUY 5,000 labelled FLATTEN passed a halted, breached governor.

**Mutation testing — 6 of 14 survived.** The two that matter:
- **`RiskChain.evaluate` min-combination:** mutating it so two caps of 2 and 10 return **10 instead of 2** (a 5× oversize) fails **zero tests**. *I verified the shipped code is correct* — caps (2,10) and (10,2) both return 2, order-independent, both rules named. The invariant is right and **unguarded** at the chain level; the equivalent property is tested one layer down in `LimitEngine`.
- **The `DU` paper-account prefix check:** deleting it from **both** runners fails **zero tests**. It is the only thing between this code and a live IBKR account.

**Tests mutate live state.** Hashing all 37 files under `live/state` + `live/log` before and after: exactly one changed — the real `live/state/governor.json`. `isolate_live` redirects `BOOK_FILE`/`HALT_FILES`/`APPROVAL`/loggers but **not `StateStore`**, and its own guard is vacuous (it asserts the absence of a filename nothing creates). Two escalations: `test_intraday_gates` is in `RUNNER_TESTS`, so **`pytest -m runner` — the 09:25 pre-trade gate — writes it**; and `.githooks/pre-commit` runs the full suite, so **every `git commit` writes it**. The gate that decides whether it is safe to trade mutates the risk-state file minutes before trading. (The agent restored the original bytes.)

---

## 11. PROP-FIRM / TOPSTEP ASSESSMENT

**What exists and is right (VERIFIED against official pages, retrieved 2026-09-13):** MLL amounts and the EOD-trail/intraday-breach semantics; the lock at starting balance (**no "+$100" exists on any official page**); MLL → $0 after payout; the ≤ boundary; DLL semantics; XFA lock at $0; per-size payout caps; 55% consistency; profit targets $3,000/$6,000/$9,000; ProjectX auth path, 24-hour token and 401 behaviour.

**What is wrong:**
- **Mandatory flat modelled as 15 min before a 16:00 CT calendar close ⇒ 15:45 CT — 35 minutes after Topstep's 3:10 PM CT liquidation.**
- Position limits counted in **raw contracts per symbol**: 30 minis accepted on a 5-mini account; 5 ES + 45 MES accepted; no 10:1 conversion; 50 ZN / 50 6E / **50 BTC** admitted with no permitted-products list.
- Funded stage flatters **six ways**: no $125 payout minimum ($75 paid), no 3-day restart, balance instead of net-since-payout, XFA simulated at Combine size (50 micros against a published 2-lot), one flat fee per attempt (160 sessions charged $49), MES commission 18% low.
- **Official: "Automated trading via the ProjectX API is prohibited in the LFA"** — the repo files this exact question as a *blocking unknown* and never records the published answer.
- A DOC-tier citation (article 8284207) returns **404**.
- The pass-probability engine's inputs are defective (§8's resampler) — corrected, **3 of 5 hypotheses flip from fail to pass**.

**Enforcement: every Topstep check is advisory.** `PropFirmRiskEngine`, `must_be_flat`, `in_blackout` have no caller that trades; `TopstepRules` is attached only to the dry-run venue whose `submit` raises `NotPermitted`. **There is no Topstep P0 solely because nothing can reach a Topstep account today.**

---

## 12–16. SOFTWARE / DATA / STATISTICS / REPRODUCIBILITY / AI-SAFETY (condensed)

**Software engineering (34).** Central ideas are sound and provable — one path to a venue, authority checked at construction, an AST-enforced broker-SDK boundary. Around them: 44.3% unreachable, 141 `sys.path` mutations, 305 script→script edges seven levels deep (`sweep_s19.commission` was wrong until S-44 and fed S-22…S-39), two hidden cycles, nine copies of the risk limits, seven cost models, five P&L models, twelve session-logic copies, six instrument tables, three "current architecture" documents written within 24 hours, and **48% of `scripts/` unreachable, accruing 10–25 files/day**. **0 dead functions in the three money-path runners** — a genuine strength.

**Data (62).** Covered in §7. Adding: the LEAN daily store is split-adjusted in **price and volume** with `split_factor=1` on all 82 symbols (**58 of 82 symbols, 154 split events**). SOXS in `data/minute_alpaca`: **440,528 of 935,770 bars (47.1%) have `v == 0`**, max close **$768,499,200/share**, zero-volume fraction **1.000 for every year 2016–2019** — split-adjusted volume truncated to `int64`. I scoped it: **only SOXS** of 16 universe names, and it **fails closed** for the deployed ORB (its `vol_ratio ≥ 1.2` gate NaN-checks to `False`; `floor(w·equity/px)` at $500M/share gives 0 shares). The real damage is the ML panel, where `amihud30 > 40` selects **10,136 rows, 100% SOXS**, as a *computed* non-sentinel value. **Hashing the entire 3.68 GB tree costs 9.2 seconds** — there is no cost argument against content hashes, and there are currently zero digests in any manifest.

**Statistics (24).** The library is correct (Holm/BH/BY, White RC size 5.3%, DSR matching Bailey–López de Prado, PBO 0.47 on noise) and has **zero callers**. `Ledger.all()` parses **0 of 1,653** equity rows — the two ledgers share **zero keys** — so `trials()` returns 0 and a future wiring would silently apply the n=1 bar. HAC with Bartlett `L = h−1` recovers ⅔ of the long-run variance ⇒ every "HAC-corrected" t is still **×1.22 too large** (measured size 10.6% / 12.1% / 35.8% at nominal 5%). The Topstep gate runs **150 bootstrap reps at seed 0** with no CI (SE 2.4 pp at a 10% floor).

**Reproducibility (22).** **No dependency manifest of any kind** — no `requirements.txt`, `pyproject.toml`, lockfile or environment file. No CI. No coverage tooling. 255 of 1,653 equity rows carry a commit (15.4%); **0 carry `reproducible: true`**; 817 of 817 futures rows carry **no provenance and no commit**; no row anywhere has a seed or dataset identity. Content hashing is absent. The funnel runs under 3.14 (pyarrow) while the LEAN side runs 3.11 — **different pandas and numpy majors writing to comparable ledgers**. Against all that: **the pre-registered futures baseline was reproduced bit-for-bit, all 9 statistics, fingerprint matched** — proving reproducibility is achievable here when provenance is recorded.

**AI safety (24).** **YES — an agent can move a strategy from research to paper execution with no human step, invisibly to git.** The sole gate is `if not APPROVAL.exists():` (`paper_trade.py:779`) on a **gitignored** file — existence only, no strategy/commit/hash binding — and it currently authorises **S-12 / `35ce0a9`** while the code trades **S-18 / `d41aefe`**. Promotion can be bypassed entirely: `load_signal()` (`paper_trade.py:182-198`) `exec_module`s `algorithms/<name>/signal.py` with **no integrity check**, so editing one tracked file changes what trades at 15:45. Promotion criteria live inside `champion.json` — the same file `--promote` writes. `live/approvals/` **does not exist**, so `Authority.for_live()` can never be satisfied: the celebrated three-lock ladder fails closed but **guards nothing that runs**. What actually stops real money is the human-held paper Gateway login. **Security itself is excellent** — zero credentials across all 5,947 git objects.

---

## 17. TOP DEFECTS (ranked by financial impact, then research-invalidating potential, then detectability)

| # | ID | SEV | Category | File:line | Defect | Conf |
|---|---|---|---|---|---|---|
| 1 | EX-01 | **P0** | EXECUTION | `intraday_trader.py:349,444` | `settle()` rebinds the aliased adapter order list; all fills invisible → same delta re-sent every bar, book frozen, loss limit blind, EOD flatten empty | PROVEN |
| 2 | EX-02 | **P0** | EXECUTION | `intraday_trader.py:891` (bound `:922`) | `UnboundLocalError` on the first loop pass; zero tests call `live()` | PROVEN |
| 3 | BT-01 | **P0** | BACKTEST | all engines | **No lookahead guard**: an oracle earns 100.00% of ceiling and clears every gate | PROVEN |
| 4 | ST-01 | **P0** | STATISTICS | `registry.py` vs `experiments.jsonl` | `Ledger.all()` parses **0 of 1,653** rows; zero key overlap; `trials()` → 0 | PROVEN |
| 5 | ML-01 | **P0** | ML / LEAKAGE | `ml_f15.py:182` vs `alpaca_data.py:39` | Split-adjusted ÷ raw prices ⇒ feature encodes the **future** split factor (ρ +0.844); live at HEAD in the best arm | PROVEN |
| 6 | RS-01 | **P0** | RESEARCH | `futures_discover.py:104` | RT counter undercharges exactly one round turn per session; 416/544 booked at $0; **16 of 26 cost-gate survivors reverse** | PROVEN |
| 7 | TS-01 | **P0** | PROP-FIRM | `paths.py:59-79` | Path resampler fabricates −$81k…−$608k minima; corrected, **3 of 5 hypotheses flip to pass** | PROVEN |
| 8 | GV-01 | **P0** | GOVERNANCE | `validation.py`, `promotion.py` | **No holdout has ever been carved**; `Holdout.spend()` never called; "OOS" was in the selection set | VERIFIED |
| 9 | AI-01 | **P1** | AI SAFETY | `paper_trade.py:779,182-198` | Existence-only gitignored approval naming the wrong champion; `exec_module` with no hash check | PROVEN |
| 10 | KB-01 | **P1** | SAFETY | `Quant Brain/.codex/config.toml` | `approval_policy="never"`, `sandbox_mode="danger-full-access"`, **not gitignored** | VERIFIED |
| 11 | RS-02 | **P1** | RESEARCH | ledger | "544 hypotheses" = **128 real rules** + 416 buy-and-hold replicas | VERIFIED |
| 12 | RS-03 | **P1** | RESEARCH | `registry.py:335` | Two-sided pass rule: **40 of 41 PASSes have negative t**; only positive was the retracted leak | VERIFIED |
| 13 | ST-02 | **P1** | STATISTICS | `stats.py:90-151` | Bartlett `L=h−1` recovers ⅔ of LRV ⇒ every "HAC-corrected" t is ×1.22 too large | PROVEN |
| 14 | TE-01 | **P1** | TESTING | `conftest.py:137-208` | Suite — and `-m runner`, the 09:25 gate, and every `git commit` — rewrites real `live/state/governor.json` | PROVEN |
| 15 | TE-02 | **P1** | TESTING | `risk.py`, both runners | 6 of 14 mutations survived; `DU` check deletable from both runners with zero failures | PROVEN |
| 16 | AR-01 | **P1** | ARCHITECTURE | `quant_brain/` | 44.3% unreachable; **15 of 53 modules** loaded in production; every safety API has no caller | PROVEN |
| 17 | AR-02 | **P1** | ARCHITECTURE | 9 locations | Nine inconsistent copies of the risk limits, all applied pre-intent | VERIFIED |
| 18 | EX-03 | **P1** | EXECUTION | `risk.py:85-89` | FLATTEN is an unverified caller-supplied label; a BUY 5,000 passed a halted governor | PROVEN |
| 19 | EX-04 | **P1** | EXECUTION | `paper_trade.py:797` | The 15:45 runner's risk chain is **empty** | VERIFIED |
| 20 | D-01 | **P1** | DATA | `data/minute_alpaca/SOXS.parquet` | 47.1% zero-volume bars, $768M/share, all of 2016–2019; ML leakage vector (`amihud30`→100% SOXS) | PROVEN |
| 21 | D-02 | **P1** | DATA | `futures_fetch_multi.py:181` | Hard-coded `21:00` UTC roll stamp ignores DST; December roll mid-session; fabricates NQ +1.0286% | VERIFIED |
| 22 | D-03 | **P1** | DATA | LEAN daily store | Split-adjusted price **and** volume with `split_factor=1`; 58 of 82 symbols, 154 events | VERIFIED |
| 23 | RP-01 | **P1** | REPRODUCIBILITY | repo root | No dependency manifest, no lockfile, no CI, no hashes, 0 rows `reproducible: true` | VERIFIED |
| 24 | RS-04 | **P1** | RESEARCH | `futures_discover.py:140-147` | "Walk-forward" is `np.array_split(pnl,5)` sign counting — no refit, no purge | VERIFIED |
| 25 | ST-03 | **P1** | STATISTICS | measured | MDE $60.70/session on MES; **power 1.7%** for a $20/session edge | PROVEN |
| 26 | TS-02 | **P1** | PROP-FIRM | `propfirm.py:135-138` | Flat modelled at 15:45 CT — **35 min after** Topstep's 3:10 PM CT liquidation | VERIFIED |
| 27 | TS-03 | **P1** | PROP-FIRM | `propfirm.py:318-347` | Raw-contract position limits: 30 minis on a 5-mini account; no permitted-products list | PROVEN |
| 28 | TS-04 | **P1** | KNOWLEDGE | `API_UNKNOWNS.md:22-42` | Official LFA API prohibition published and unrecorded; filed as a *blocking unknown* | VERIFIED |
| 29 | KB-02 | **P1** | KNOWLEDGE | `Quant Brain/` | 44% of 34 strategies disagree on the **sign** of returns across 5 campaigns; disqualifying note is an orphan | PROVEN |
| 30 | KB-03 | **P1** | SAFETY | `auto-commit.sh:16` | `git add -A` → push, `AUTO_PUSH=true`, targeting the public origin — **latent, unwired** | VERIFIED |
| 31 | RS-05 | **P2** | RESEARCH | `registry.py:136-139` | Family rename resets N to 1; `.v2` duplicates v1 with identical t | VERIFIED |
| 32 | RS-06 | **P2** | RESEARCH | `registry.py:317` | `verdict()` needs no `record()`; 50 looks leave the count at 0 | VERIFIED |
| 33 | BT-02 | **P2** | BACKTEST | `intraday_backtest.py` | No liquidity constraint; `run()` never validates; 19/20 callers skip it | PROVEN |
| 34 | BT-03 | **P2** | BACKTEST | `execution_sim.py` | Fills NaN quantities; NaN position defeats the cap; refuses risk-*reducing* trades | PROVEN |
| 35 | BT-04 | **P2** | BACKTEST | `futures_discover.py:97-103` | Decision-close fill = **+0.0551 ticks/leg** subsidy (+51% of gross on mean-reversion) | PROVEN |
| 36 | ML-02 | **P2** | ML | 145 of 151 rows | One window, no true holdout; design parameters fixed by reading it | VERIFIED |
| 37 | ML-03 | **P2** | ML | measured | A one-line reversal beats the 38-feature GBDT (IC +0.01529 vs +0.01123) | PROVEN |
| 38 | ML-04 | **P2** | ML | F-1 | The one real signal decays to **−0.00012** by the last test year; −$2,206/day | PROVEN |
| 39 | AR-03 | **P2** | ARCHITECTURE | `scripts/` | 305 script→script edges; 48% of scripts unreachable, +10–25 files/day | PROVEN |
| 40 | GV-02 | **P2** | GOVERNANCE | `champion.json` | `must_beat: CAR`; no significance test, no multiplicity, no OOS requirement | VERIFIED |
| 41 | DOC-01 | **P2** | DOCS | `champion.json.stats` | Displayed headline is the **zero-cost** column (24.403%); honest all-in is 18.785% | VERIFIED |
| 42 | ST-04 | **P2** | STATISTICS | `futures_discover.py:131` | 150 bootstrap reps at seed 0, no CI, gate at 10% (SE 2.4 pp) | VERIFIED |
| 43 | D-04 | **P2** | DATA | manifests | Zero content hashes; hashing 3.68 GB costs **9.2 s** | PROVEN |
| 44 | D-05 | **P2** | DATA | six tables | Six hard-coded spec tables; 28% MES commission disagreement | VERIFIED |
| 45 | BT-05 | **P2** | BACKTEST | `orb/signal.py:173` | Close-only stops; bar piercing both stop and target books neither | PROVEN |
| 46 | AR-04 | **P2** | ARCHITECTURE | `paper_trade.py:701-710` | Sleeve isolation falls back to `[]` on ImportError → daily runner sells the other sleeve | VERIFIED |
| 47 | AR-05 | **P3** | ARCHITECTURE | `core/dataquality.py:272` | Core mutates `sys.path` into `scripts/` and imports `markets.equity_us` | VERIFIED |
| 48 | TE-03 | **P3** | TESTING | `tests/` | No coverage, no mutation, no property-based testing ever run; 533 tests (27.5%) exercise dead code | VERIFIED |
| 49 | KB-04 | **P3** | KNOWLEDGE | `Quant Brain/` | 54.4% unsourced; **zero** `validated: true`; 267 broken links; 81/82 papers unnoted | PROVEN |
| 50 | OPS-01 | **P3** | OPS | `live/log` | Every alert since 2026-09-10 is `delivered: false` | VERIFIED |

---

## 18. TOP 20 UNKNOWNS

1. Magnitude of the path-resampler artefact on **all** real funnel families (measured on 5 of 128).
2. The XFA scaling-plan ladder (published only as an image).
3. Whether the Combine "best day" is net of commissions.
4. The MLL end-of-day snapshot clock (3:10 / 4:00 / 5:00 PM CT all published for different purposes).
5. Topstep's numeric HFT threshold — no page states one.
6. Whether an unattended personal workstation satisfies the "personal device" rule.
7. Realised IBKR slippage for the intraday sleeve (2.22 bps ± 0.80, n=66; breakeven 2.6).
8. MES/MNQ/NQ quoted spreads — never fetched.
9. Whether the champion's parameters survive 1999–2011 — never run.
10. Whether LEAN's in-`on_data` `history()` includes day D's own bar.
11. Whether `spa()`'s measured 8% size is Monte-Carlo noise.
12. The nested `QuantModel` repository's history and authorship (gitdir missing).
13. Whether any vault result seeded the 2026-09-08 backlog.
14. Whether `ib.managedAccounts()[0]` is the account orders route to (`Order.account` never set).
15. Whether `origin/main` is force-push protected; all 240 commits unsigned.
16. Whether OpenClaw holds cron entries in `openclaw.sqlite`.
17. The effective number of *distinct* P&L series per futures family after deduplication.
18. **What produced commit `592e11a` ("dcfhtg")** — the message does not match `auto-commit.sh`'s format.
19. Whether five A-16 ledger rows written by code present in no commit are reproducible.
20. Whether the 4,120-claim machine-generated vault corpus is accurate (needs a 20-claim sample audit).

---

## 19. TOP 20 STRENGTHS (evidence-backed)

1. **Secrets hygiene** — zero secret-shaped matches across all 5,947 git objects; correct `.gitignore`; `__repr__` redaction with a test guarding the package source. **PROVEN.**
2. **Futures contract mechanics** — tick value derived, 14/14 P&L cases exact, 0 mismatches. **PROVEN.**
3. **Futures bar integrity** — 0 duplicates, 0 out-of-order, 0 bad OHLC over 1.6M rows, DST correct. **PROVEN.**
4. **Feature causality** — both libraries strictly causal under perturbation probing. **PROVEN.**
5. **Accounting identities** — all four engines close to 1e-10. **PROVEN.**
6. **The two `Book` classes are genuinely identical** — the docstring's claim is true. **PROVEN.**
7. **Bit-for-bit reproduction** of the pre-registered futures baseline, 9/9 statistics. **PROVEN.**
8. **Retraction with denominator preservation** — a wrong result withdrawn, its trial kept. **VERIFIED.**
9. **`Ledger.verdict()` takes no trial-count argument**, and a test forbids adding one. **VERIFIED.**
10. **`RiskDecision.merge` / `RiskChain`** — min-combination, order-independent, denial terminal. **VERIFIED** (unguarded at chain level).
11. **AST ban on broker SDKs above `brokers/`**, with a self-test proving it catches an offender. **VERIFIED.**
12. **`StateScope` containment** — all four traversal attempts refused. **VERIFIED.**
13. **Gap fills are pessimistic**; passive limits refused as documented. **PROVEN.**
14. **The fail-closed preflight**, proven by a real incident (refused to trade on a mid-edit `NameError`). **PROVEN.**
15. **F-12's scrambled-sigma control** — the best null in the tree, and it kills F-12. **VERIFIED.**
16. **F-11/F-12 refuse a pre-declared cell while a test-max cell would have passed.** **VERIFIED.**
17. **The critic track** — C-11's block-length attack on the repo's own best result. **VERIFIED.**
18. **Self-audits S-33/S-38/S-40** measured the repo's own selection premium and OOS-argmax rate and wrote them down. **VERIFIED.**
19. **`compare_orders.py`** — diffs backtest vs runner orders on identical inputs, every date. **VERIFIED.**
20. **Zero dead functions in the three money-path runners**; zero prompt-injection strings in any vault research folder. **PROVEN.**

---

## 20. REQUIRED EXPERIMENTS

| # | Experiment | Purpose | Pass criterion |
|---|---|---|---|
| E1 | Drive `live()` under a stubbed broker ≥3 iterations with fills | Prove the runner can book a fill and not re-send | one order per intended delta; book reflects fills |
| E2 | Re-run the whole funnel with the flatten RT charged and degenerate rules excluded | Restate every futures verdict | attrition table restated; cost shares corrected |
| E3 | Object-level `(pnl, path)` bootstrap on all families | Quantify the resampler artefact | agreement within Monte-Carlo error, or all Topstep numbers void |
| E4 | Publish σ, s.e., MDE and power beside every funnel family | Make "0 survivors" falsifiable | table published |
| E5 | Carve a genuine date-forward holdout with a one-look ledger | Restore the ability to make an OOS claim | one recorded look per candidate |
| E6 | Oracle/leak canary in every engine's CI | Prevent the next lookahead | oracle scores ≈0 after the guard |
| E7 | Champion through 1999–2011 at honest costs | Test the regimes that break momentum | pre-registered thresholds met |
| E8 | Rebuild F-15/F-16/F-17 features on a consistent adjustment basis | Remove the split-factor leak | ρ(feature, future split factor) ≈ 0 |
| E9 | `late_momo direction=+1`, costed, on 2,686 sessions | Test the one mechanism-backed unexploited lead | positive net at the corrected bar |
| E10 | Measure MES/MNQ/NQ spreads | Replace an assumption with a measurement | measured tables in the cost model |
| E11 | Full suite with `isolate_live` extended to `StateStore` | Stop tests mutating live state | `live/state` mtimes unchanged |
| E12 | Two-process idempotency/lock stress with a slow holder | Quantify the fail-open window | exactly-once holds |
| E13 | Crash/restart reconciliation drill | Prove recovery | reconciled before READY |
| E14 | Topstep practice dry run with `PropFirmRiskEngine` in the chain | Convert rules from advisory to enforced | no violation in a full week |
| E15 | Sample-audit 20 vault claims against their cited sources | Establish whether the corpus is citable | ≥18/20 accurate |

---

## 21. BACKTEST-READY GATE

| Requirement | Status |
|---|---|
| Dataset provenance | **FAIL** — no manifest, no hashes |
| Dataset integrity | **PASS** (futures bars) / **FAIL** (Alpaca SOXS, LEAN daily adjustment) |
| Contract metadata | **PARTIAL** — correct, but six duplicate tables disagree |
| Correct tick values | **PASS** — 14/14 verified |
| Correct multipliers | **PASS** |
| Correct roll handling | **FAIL** — unmarked, DST bug |
| Correct sessions | **PARTIAL** — early closes pass as full sessions |
| Correct timestamps | **PASS** |
| No lookahead | **FAIL** — oracle clears every gate |
| Correct signal timing | **PARTIAL** — decision-close fill subsidy |
| Correct order timing | **PARTIAL** |
| Realistic fills | **FAIL** — no liquidity constraint |
| Realistic commissions | **FAIL** — micros 18% low |
| Realistic spread | **FAIL** — unmeasured for 3 of 4 contracts |
| Realistic slippage | **FAIL** |
| Flatten costs included | **FAIL** — exactly one RT/session missing |
| Position accounting | **PASS** — identities close to 1e-10 |
| P&L accounting | **PASS** |
| Risk constraints enforced | **FAIL** — advisory |
| Trial identity | **PARTIAL** — futures only |
| Trial counting | **FAIL** — resettable; ledger unreadable |
| Dataset fingerprint | **FAIL** |
| Git commit fingerprint | **FAIL** — 0/817 futures, 15.4% equity |
| Configuration fingerprint | **FAIL** |
| Experiment provenance | **FAIL** — 0/817 |
| Leakage tests | **FAIL** — guard exists, not on the research path |
| Multiple-testing control | **FAIL** — cannot read the ledger |
| Power / MDE analysis | **FAIL** — never published |
| Uncertainty estimates | **PARTIAL** — 150 reps, no CI |
| Robustness testing | **PARTIAL** |
| Parameter sensitivity | **PARTIAL** |
| Regime testing | **FAIL** — one regime |
| Date-forward validation | **FAIL** |
| Untouched holdout | **FAIL** — never carved |
| Reproducible execution | **PARTIAL** — one result reproduced bit-for-bit |
| End-to-end test | **FAIL** |
| Independent rerun | **PARTIAL** |

# FUTURES BACKTEST READY: **NO**

---

## 22. READINESS GATES

| Gate | Verdict | Blocker |
|---|---|---|
| RESEARCH READY | **NO** | No experiment identity on 1,653 rows; provenance 0/817; ledger unreadable by its own tooling |
| BACKTEST READY | **NO** | No lookahead guard; one RT/session uncharged; 76.5% degenerate hypotheses |
| FUTURES BACKTEST READY | **NO** | All of the above plus unmarked rolls and unmeasured spreads |
| STATISTICAL VALIDATION READY | **NO** | Multiplicity machinery cannot parse the ledger; HAC ×1.22 |
| OOS READY | **NO** | No holdout ever carved; "OOS" was inside the selection set |
| ROBUSTNESS READY | **NO** | One regime; resampler fabricates paths |
| ML RESEARCH READY | **NO** | Live future-split leak in the admitted feature set; no true holdout |
| PROP-FIRM SIMULATION READY | **NO** | Wrong units, wrong flat time, defective resampler |
| TOPSTEP SIMULATION READY | **NO** | As above, plus six flattering funded-stage defects |
| PAPER READY | **NO** | Runner crashes; the other runner has no risk chain; approval names the wrong book |
| LIVE READY | **NO** | Everything above; only a human-held Gateway login separates code from money |

---

## 23. REMEDIATION PLAN

**PHASE 0 — safety, before Monday 09:25.** Fix EX-01 and EX-02 **together** (never EX-02 alone — fixing the crash un-masks the fill-blindness). Set the intraday sleeve to an explicit `NO_ORDER` mode. Redirect `StateStore` in `isolate_live`. Bind the approval file to `algorithm + commit + hash`. Add `Quant Brain/` and `.obsidian/` to `.gitignore`.

**PHASE 1 — data correctness.** Content-hash every store into the manifests (9.2 s). Mark rolls explicitly and fix the DST stamp. Rebuild the Alpaca store with float volume. Reconcile the six spec tables to one. Add a dependency manifest and lockfile.

**PHASE 2 — backtest correctness.** Charge the flatten RT and exclude degenerate rules; re-run the funnel (E2). Add an oracle canary to every engine (E6). Make `run()` validate. Add a liquidity constraint. Measure the three missing spreads (E10).

**PHASE 3 — statistics.** One ledger schema readable by `Ledger`. Mandatory provenance. `verdict()` writes a stub row. Family registration with declared parents. HAC bandwidth ≈1.5–2h or block bootstrap primary. Object-level resampling (E3). ≥1,000 reps with Wilson intervals. Publish MDE/power (E4).

**PHASE 4 — validation.** Carve the date-forward holdout with a one-look ledger (E5). Wire the causality guard into the funnel. Rebuild the ML features on a consistent adjustment basis (E8).

**PHASE 5+ — only then** strategy research (E7, E9), Topstep model corrections, practice (E13, E14), paper, live.

**WHAT NOT TO BUILD YET:** no new indicators, models, markets, parameter sweeps, prop-firm automation, venue adapters, sizers, or live capability. The repository already contains ~12,000 lines of level-8–10 infrastructure serving a Combine with no account and no candidate strategy; adding more widens the gap between capability and validation.

---

## 24. FINAL RED TEAM — how could this system be lying?

**The backtest?** It is: an oracle clears every gate, one RT/session is never charged, the fill sits at the decision bar's close worth +51% of gross on mean-reversion, and there is no liquidity constraint.
**The data?** SOXS is $768M/share with zero volume for four years; the LEAN daily store is adjusted-as-raw across 154 split events; the December futures roll fabricates the second-largest 1-minute move in the store.
**Quant Brain?** By offering an agent four different returns for the same strategy, hiding the disqualifying benchmark in an orphan note, and stripping the confidence disclaimers on the map page.
**ML?** By admitting a feature that encodes whether a stock is about to split, in the arm that produced its best-ever result — and by never building the one-line baseline that beats it.
**Multiple testing?** By making the denominator unreadable: `trials()` returns 0 for a 5,500-cell search, and a family rename resets the bar to 1.96.
**Execution?** By re-sending the full position every bar with a frozen book, no stop, and a FLATTEN label that bypasses every control.
**Risk?** It already can: one limit in one chain, the other chain empty, NaN passing every check, and the `DU` guard deletable with zero test failures.
**Prop-firm simulation?** By reporting 100% liquidation on paths that never happened — and, corrected, flipping 3 of 5 hypotheses to pass.
**The research process?** By optimising against the test set, which the repository's own critic documents in its own words.
**And the system as a whole?** By looking sophisticated: 18,114 core lines with 44.3% unreachable, 1,938 green tests of which 27.5% exercise dead code, six of fourteen mutations surviving, and a self-generated scorecard — over two runners that carry one limit between them.

---

## 25. THREE ANSWERS

> ### 1. What is the single biggest thing Quant Model is doing wrong?
>
> **It has built an elaborate apparatus for being right and connected almost none of it to the path where being right matters.**
>
> The purged walk-forward, the write-once holdout, the seven multiplicity corrections, the promotion gate, the bracket verifier, the reconciler, the order state machine, the eight position sizers, the twenty-capability venue protocol — **every one of them has zero production callers**, and the multiplicity machinery is *structurally incapable* of reading the ledger it was built to police (`Ledger.all()` → 0 of 1,653 rows). Meanwhile the code that actually decides things — a P&L loop that miscounts round turns, a resampler that divides by a near-zero, a promotion rule that reads `must_beat: CAR` — has no guard at all. The result is a system that cannot detect its own errors: an oracle with perfect foresight passes every gate it owns.

> ### 2. What is the single biggest thing Quant Model is doing right?
>
> **It refutes itself in writing, and the refutations are correct.**
>
> It retracted a look-ahead survivor while deliberately keeping its trial in the multiplicity denominator. Its critic track attacked its own best result with a block-length sweep and reported what survived. S-33 measured its own selection premium and found it nil. S-40 recorded that its shipped cell was the out-of-sample argmax and the in-sample 24th of 36. F-23 concluded that four of its own refusals were coin flips. F-12 built a scrambled control that killed F-12. **Most of the damning evidence in this audit came from the repository's own journals** — which is why the audit could be written at all. Foundations can be rebuilt in weeks; that habit cannot be installed later, and almost no research group has it.

> ### 3. What is the single highest-value next action?
>
> **Fix EX-01 and EX-02 in the same change before Monday's 09:25 launch — and put the intraday sleeve in an explicit no-order mode until it has a positive pre-registered result.**
>
> The order matters and is counter-intuitive: **fixing the crash alone is the dangerous move**, because the `UnboundLocalError` is currently the only thing preventing a runner that re-sends its entire position every minute with a blind loss limit and no end-of-day exit.
>
> Then, in strict order: carve a date-forward holdout and stop scoring the old ones (E5); add an oracle canary to every engine (E6); charge the flatten round turn and re-run the funnel (E2). Those four items cost days, not weeks, and they convert every future result from unfalsifiable to falsifiable — which is the entire purpose of the platform.

---

*Audit performed read-only at HEAD `6c8f9196`. No repository file other than this one was created, modified or deleted. Nothing was committed or pushed. No credential was opened, no venue contacted, no order placed, no live trading enabled. Where a fact could not be established it is marked **UNKNOWN — REQUIRES VERIFICATION** and listed in §18.*
