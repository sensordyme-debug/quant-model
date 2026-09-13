# Rule versioning

**This version: `topstep/2026.09.13`.**

A prop-firm rulebook is not a constant. Topstep changed the payout caps, moved the DLL article, and
updated its Terms of Use five days before this retrieval. A backtest run today under today's rules
and a backtest run in six months under different rules are not comparable, and neither is
reproducible, unless the rulebook itself is versioned and the version is recorded with the result.

This file specifies how.

---

## 1. Version identity

A rulebook version is named `topstep/YYYY.MM.DD`, where the date is the **retrieval date** — the day
the pages were fetched. It is not a semantic version: there is no meaningful "major/minor" for a
third party's rules, and pretending otherwise invites arguments about whether a payout-cap change is
breaking.

`topstep/2026.09.13` is the first version under this scheme. The `topstep.py` snapshot of
2026-09-12 is retroactively `topstep/2026.09.12`, incomplete (it lacks §5–§10 of
[RULES.md](RULES.md)) and superseded.

### Retrieved vs effective — the distinction that matters

We know when we **observed** a rule. We almost never know when it **started**. Topstep dates some
articles ("June 10, 2026") and not others ("Updated yesterday", "Over a week ago"). So each version
carries three dates, and only the first is a fact:

| Field | Meaning |
|---|---|
| `retrieved` | The date the pages were fetched. Known exactly. |
| `observed_from` | The date this rulebook is *known* to have been in force — equal to `retrieved` unless a page states an earlier effective date. |
| `observed_to` | `null` while current; set to the `retrieved` date of the next version when superseded. |

A rule was in force at some unknown point *before* `observed_from`. **Never claim a rule applied on
a date earlier than `observed_from`** — that is the failure mode this scheme exists to prevent,
because it is invisible in results and it always favours whichever answer you already wanted.

---

## 2. Layout on disk

```
docs/topstep/
  README.md              <- points at the current version
  CHANGELOG.md           <- created at the first version bump; one entry per version
  RULES.md   COMBINE.md   XFA.md   LFA.md
  PAYOUTS.md PROHIBITED.md VERSIONING.md
  versions/
    2026.09.13/
      manifest.json      <- machine-readable: version, dates, rule values, sources
      RULES.md  COMBINE.md  XFA.md  LFA.md  PAYOUTS.md  PROHIBITED.md
      raw/
        help.topstep.com_8284208.md
        help.topstep.com_8284233.md
        www.topstep.com_terms-of-use.md
        ...
    2026.12.xx/
      ...
```

The files at `docs/topstep/*.md` are **always the current version**, so a reader who opens the
directory gets today's rules without navigating. `versions/<v>/` holds the frozen copy of each
version, including this one. At the first bump, `2026.09.13/` is created by copying the current
files verbatim — it is not created retroactively from memory.

### `raw/` is not optional

Every version archives the **fetched page text** for every source cited. As
[README.md](README.md#method-and-the-caveat-that-goes-with-it) records, the quotes in this spec are
automated transcriptions, not hand-copied bytes. The raw snapshot is what lets a future reader check
a transcription instead of trusting it, and it is the only way to produce a real diff when Topstep
edits a page silently. A version without `raw/` is an assertion; a version with it is evidence.

File naming: `<host>_<article-id-or-slug>.md`, with the fetch URL and timestamp as the first two
lines of each file.

### `manifest.json`

The machine-readable form. One entry per rule ID, so a simulator loads a version rather than parsing
markdown:

```json
{
  "version": "topstep/2026.09.13",
  "retrieved": "2026-09-13",
  "observed_from": "2026-09-13",
  "observed_to": null,
  "supersedes": "topstep/2026.09.12",
  "rules": {
    "TS-CON-01": {
      "value": 0.55,
      "unit": "fraction",
      "denominator": "total_profit",
      "enforcement": "SOFT",
      "affects": ["research", "simulation"],
      "confidence": "DOC",
      "quote": "55% is a hard line. It is not rounded, and there is no buffer.",
      "source": "https://help.topstep.com/en/articles/8284208-consistency-at-topstep",
      "raw": "raw/help.topstep.com_8284208.md"
    },
    "TS-SCL-07": {
      "value": null,
      "confidence": "OWNER",
      "note": "XFA scaling ladder published only as an image; not captured."
    }
  }
}
```

`manifest.json` is generated from the markdown, not maintained separately — one source of truth. Any
rule whose `confidence` is below `DOC` must carry a `note` saying what is missing and how to get it.

---

## 3. How a simulator reproduces a historical result

### 3.1 Every run records the version

Each entry written to `research/experiments.jsonl` gains a field:

```
"topstep_rules_version": "topstep/2026.09.13"
```

plus, when it is not the current version, `"topstep_rules_mode"` (below). A run that touches Topstep
rules and does **not** record a version is not reproducible and should be treated as untrusted, the
same way an unrecorded backtest is.

### 3.2 Two evaluation modes, and they answer different questions

| Mode | What it does | The question it answers |
|---|---|---|
| `pinned` | One rule version applied over the whole simulated history, regardless of dates | *"How would this strategy fare under today's rules?"* — the right mode for comparing strategies, tuning, and every purchase decision |
| `historical` | Rules switch at version boundaries as the simulation clock crosses them | *"Would this account actually have survived?"* — the right mode for reconstructing a real account's past |

**`pinned` is the default and should stay the default.** Comparing two strategies under two different
rulebooks is a confounded experiment, and the confound is invisible in the output.

**`historical` is refused before the archive begins.** The archive starts 2026-09-13. Topstep's rules
before that date were never captured and cannot be reconstructed — the help centre publishes no
history and shows no prior revisions. A `historical` run whose simulated period starts before the
earliest `observed_from` must **raise**, not fall back to the oldest version. Silently extrapolating
today's rules backwards is precisely the error `observed_from` exists to make impossible.

The practical consequence: a 2016–2026 backtest can only ever be `pinned`. That is a real limit on
what a Topstep backtest can claim, and it should be stated in the result rather than buried.

### 3.3 Reproducing a result

1. Read `topstep_rules_version` from the experiment record.
2. Load `docs/topstep/versions/<version>/manifest.json`.
3. Build the profile from that manifest, not from `topstep.py` constants.
4. Re-run. A mismatch is then a bug in the strategy or the engine, never a rules drift.

Step 3 is the part that requires a code change not made by this pass: `topstep.py` currently hardcodes
its constants. The migration is to have the module *load* a manifest and keep the `Rule`/`Confidence`
machinery as the in-memory representation — the dataclass already carries `value`, `quote`, `source`,
`confidence`, and `retrieved`, which is exactly the manifest schema. The fail-closed
`require()` gate should stay, and should additionally refuse a version whose `observed_to` is set
when the caller asked for current rules.

---

## 4. Procedure when Topstep changes a rule

**A published version is immutable. It is never edited in place, for any reason.**

That is the whole discipline, and the temptation to break it is strongest in the case that matters
most: noticing that a number in the current version is *wrong*. Fixing it in place silently
invalidates every result that cited that version while leaving the citation looking valid. A wrong
number gets a new version too, with the correction recorded — see §4.3.

### 4.1 Detecting a change

Re-fetch on a schedule and diff against `raw/`. Priority order, by observed volatility:

| Source | Why it moves |
|---|---|
| [Terms of Use](https://www.topstep.com/terms-of-use) | Updated 2026-09-08, five days before this retrieval. The contract; governs on conflict. |
| [Payout Policy 8284233](https://help.topstep.com/en/articles/8284233-topstep-payout-policy) | Carries a **limited-time** cap-doubling offer and dated regional changes (Wise, August 2026) |
| Pricing pages | Promotional rates; already disagree between the help centre and a landing page |
| [Risk Adjustments 13613539](https://help.topstep.com/en/articles/13613539-risk-adjustments-high-risk-high-volatility) | *"Temporary"* by construction |
| Parameter articles (8284197, 8284204, 8284215, 10657969, 8284208) | Slow-moving; the structural rules |

The scheduled-task infrastructure in this repo is the natural home for a monthly re-fetch. A diff
against `raw/` is a much better change detector than re-reading the prose, and it catches silent
edits — Topstep does not maintain a public changelog.

### 4.2 Applying a change

1. **Create** `versions/<new-date>/` — copy the current files, then edit the copies.
2. **Set** `observed_to` on the outgoing version's `manifest.json`. This is the **only** permitted
   modification to a published version, and it is metadata about supersession, never a rule value.
3. **Edit** the new version's files. Change values, quotes, sources, confidence tiers.
4. **Archive** fresh `raw/` snapshots for every page re-fetched. Pages not re-fetched keep the
   previous version's snapshot, and the manifest records which version each snapshot came from —
   a version may cite an older snapshot but must never pretend it is new.
5. **Regenerate** `manifest.json`.
6. **Append** a `CHANGELOG.md` entry (§4.4).
7. **Copy** the new version's files up to `docs/topstep/*.md` so the top level is current.
8. **Do not** touch prior versions' rule files, quotes, or raw snapshots.

### 4.3 Rule identity across versions

Rule IDs (`TS-CON-01`, `TS-PAY-03`, …) are **stable and never reused**.

| Situation | What to do |
|---|---|
| Value changes | Same ID, new value in the new version. The changelog records old → new. |
| Wording changes, value does not | Same ID, new quote. Flag as `editorial` in the changelog — it matters for provenance, not for simulation. |
| Rule is withdrawn | Keep the ID. Mark `"status": "withdrawn"` with the version it was withdrawn in. **Never delete and never renumber** — an old experiment record may reference it. |
| A genuinely new rule appears | Next free number in its section. |
| A rule splits into two | The original ID is withdrawn; two new IDs are created; the changelog records the split explicitly. Do not silently repurpose the old ID for one half. |
| **A recorded rule turns out to be wrong** | New version, corrected value, changelog entry with reason `correction`. The old version stays exactly as published, marked superseded. Results citing it stay honestly attributable to a rulebook that was wrong. |

### 4.4 Changelog entry

One per version. Minimum contents:

```markdown
## topstep/2026.12.01  (supersedes topstep/2026.09.13)

Retrieved 2026-12-01. Re-fetched: 8284233, 8284223, terms-of-use.

| Rule | Change | Old | New | Kind | Impact |
|---|---|---|---|---|---|
| TS-PAY-04 | Cap-doubling offer withdrawn | active | withdrawn | value | Halves modelled XFA payouts where a voluntary DLL was assumed |
| TS-SCL-07 | Ladder published as text | OWNER | DOC | confidence | XFA size model becomes admissible |
| TS-CON-01 | Wording only | 55% | 55% | editorial | none |

**Invalidated results:** any experiment with `topstep_rules_version: topstep/2026.09.13` that
depended on TS-PAY-04. Listed by run id: ...
```

The **impact** column is the point of the exercise. A version bump that does not say which prior
conclusions it overturns has recorded a fact and hidden its consequence.

### 4.5 What a version bump obliges you to do

Adding a version does **not** silently invalidate prior results — they remain valid statements about
the rulebook they cite. It obliges two things:

1. Any **open decision** resting on a superseded version is re-checked against the new one before
   money moves. The purchase decision is the obvious case.
2. Any **conclusion in a track journal** whose sign could flip is re-run under the new version, and
   the changelog's impact column is what identifies those.

---

## 5. Open items this scheme is designed to absorb

Three known gaps will close through a version bump rather than an edit, and the scheme should be
exercised on them:

| Item | Closes when |
|---|---|
| `TS-SCL-07` — the XFA scaling ladder (currently `OWNER`) | The owner reads it off the dashboard. It gets a new version with `confidence: OWNER` → `DOC` and `source: "owner dashboard, <date>"` — an owner-supplied value is still a versioned rule, and its provenance is recorded as honestly as a help-centre quote. |
| `TS-CMB-03` — the No-Activation-Fee pricing discrepancy | Confirmed at checkout, or on a re-fetch where the two pages agree. |
| The consistency profit-target increase size (`TS-CON-03`) | Observed on a real account that exceeded it, or published. Until then the lower-bound model stands and is labelled as a model, not a rule. |

Each of these is currently below `DOC` and each is gated by `require()` in `topstep.py`. **The gate
is the feature.** A rule this rulebook does not have should stop a decision, not quietly take a
default value — which is the same principle the `Confidence` tiers already encode, extended across
time.
