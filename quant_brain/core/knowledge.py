"""Has this already been tested?

WHY
---
`AGENTS.md` step 2 of the improvement loop says: "Do not repeat a run that is already in the
ledger." With 735 rows in `research/experiments.jsonl` and a 307 KB backlog, that instruction
is no longer mechanically satisfiable. The only retrieval the system has is positional - the
loop reads "the last 20 lines" of the ledger and the latest journal entry - so an agent's
recall is limited to *recency*. Six concurrent tracks each reading only the tail is a
duplicate-work generator, and `grep` only finds the words you already thought of.

Measured corpus: experiments.jsonl 499 KB, journal.md 448 KB, backlog.md 307 KB,
BLOCKERS.md 77 KB - about 353k tokens, growing ~70k a day. It exceeds any context window
worth spending on it.

WHY TF-IDF AND NOT EMBEDDINGS
------------------------------
Part 22: "Do NOT introduce a giant infrastructure stack unless justified. Prefer the
smallest reliable solution." The corpus is ~1,500 short documents. Brute-force cosine over a
sparse TF-IDF index costs microseconds and needs no model, no service, no vector database,
no network call, and no new dependency - it is pure stdlib, so it imports on both the 3.11
and 3.14 interpreters without touching either environment.

The honest limitation: lexical similarity misses a paraphrase that shares no vocabulary
("opening range breakout" vs "first-30-minutes momentum"). Two things mitigate it in this
corpus specifically - the repository's tags are highly conventionalised (track prefixes
S-, F-, A-, O-, X-, plus instrument tickers), and character trigrams catch morphological
variants. If a paraphrase miss is ever observed in practice, THAT is the evidence that
justifies embeddings. Until then this is the right size.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESEARCH = REPO / "research"

#: Words that carry no discriminating signal in this corpus. Deliberately short - an
#: aggressive stoplist would strip "vol", "band" and "gap", which are the vocabulary.
_STOP = frozenset("""
a an the and or of to in on at for with without is are was were be been being it its this
that these those as by from not no than then so if but we i run runs ran
""".split())

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-_.]*")


def words_of(text: str) -> list[str]:
    """Whole content words. The part of a match that has to be real."""
    return [w for w in _TOKEN.findall(text.lower()) if w not in _STOP and len(w) > 1]


def tokenize(text: str) -> list[str]:
    """Words plus character trigrams of the longer words.

    The trigrams let "reversal" match "revert" and "momentum" match "momo" - the repository
    uses both spellings for the same idea, so a pure word index would miss half the corpus.
    Restricted to tokens of 5+ characters so short tickers do not explode into noise.

    THEY ALSO PRODUCE FALSE POSITIVES, which is why `search` gates on word overlap. Measured
    while writing the tests: "sourdough bread proofing schedule" scored **0.31** against
    "A-2 30-minute opening range breakout on leveraged ETFs", above the 0.30 threshold
    `already_tried` uses - on the strength of the shared "#ing" in proofing/opening. A
    "have we tried this?" tool that fires on unrelated ideas is worse than none, because it
    trains the reader to skip it. See `search` for the gate.
    """
    words = words_of(text)
    grams: list[str] = []
    for w in words:
        if len(w) >= 5:
            grams.extend(f"#{w[i:i + 3]}" for i in range(len(w) - 2))
    return words + grams


@dataclass
class Entry:
    """One searchable thing that was already done."""

    doc_id: str
    kind: str          # "experiment" | "backlog" | "journal"
    title: str
    date: str = ""
    track: str = ""
    detail: str = ""
    outcome: str = ""

    def text(self) -> str:
        return " ".join((self.title, self.track, self.detail, self.outcome))

    def describe(self, width: int = 110) -> str:
        head = f"[{self.kind}] {self.date or '?':<10} {self.track or '-':<6} "
        body = self.title.replace("\n", " ")
        return (head + body)[:width]


@dataclass
class Hit:
    entry: Entry
    score: float

    def __str__(self) -> str:
        return f"{self.score:5.2f}  {self.entry.describe()}"


class KnowledgeIndex:
    """A brute-force TF-IDF index over what this repository has already tried.

    Rebuilt from source on construction - there is no persisted index to go stale, and
    building over ~1,500 short documents takes well under a second. That is a deliberate
    trade: a stale "have we tried this?" answer is worse than a slightly slower one, because
    it produces false confidence in exactly the case the tool exists to prevent.
    """

    def __init__(self, entries: list[Entry] | None = None):
        self.entries: list[Entry] = entries or []
        self._tf: list[Counter[str]] = []
        self._words: list[set[str]] = []
        self._idf: dict[str, float] = {}
        self._norm: list[float] = []
        if self.entries:
            self._build()

    # -- construction ----------------------------------------------------------------------

    def _build(self) -> None:
        self._tf = [Counter(tokenize(e.text())) for e in self.entries]
        # Whole-word sets, kept separately so `search` can require a real word in common
        # before a trigram similarity is allowed to count. See tokenize()'s docstring.
        self._words = [set(words_of(e.text())) for e in self.entries]
        df: Counter[str] = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(self._tf) or 1
        # Smoothed IDF; +1 keeps a term that appears in every document at a small positive
        # weight rather than exactly zero, which would make an all-common-terms query score 0
        # against everything and silently report "nothing found".
        self._idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        self._norm = []
        for tf in self._tf:
            total = sum(tf.values()) or 1
            sq = sum(((c / total) * self._idf.get(t, 0.0)) ** 2 for t, c in tf.items())
            self._norm.append(math.sqrt(sq) or 1.0)

    # -- query -----------------------------------------------------------------------------

    def search(self, query: str, k: int = 8, *, kinds: tuple[str, ...] = ()) -> list[Hit]:
        """The `k` most similar things already done, most similar first."""
        q_tf = Counter(tokenize(query))
        if not q_tf or not self.entries:
            return []
        q_total = sum(q_tf.values())
        q_vec = {t: (c / q_total) * self._idf.get(t, 0.0) for t, c in q_tf.items()}
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        q_words = set(words_of(query))
        hits: list[Hit] = []
        for i, entry in enumerate(self.entries):
            if kinds and entry.kind not in kinds:
                continue
            # THE GATE: at least one whole content word in common. Without it, shared
            # morphology alone ("#ing" in proofing/opening) scored 0.31 on an unrelated
            # query. Trigrams now only refine the ranking among documents that already
            # share vocabulary, which is the job they are good at.
            if not (q_words & self._words[i]):
                continue
            tf = self._tf[i]
            total = sum(tf.values()) or 1
            dot = 0.0
            # Iterate the QUERY's terms, not the document's: a query has a handful of terms
            # and a document has hundreds, so this is the cheap direction.
            for t, qv in q_vec.items():
                c = tf.get(t)
                if c:
                    dot += qv * (c / total) * self._idf.get(t, 0.0)
            if dot > 0:
                hits.append(Hit(entry, dot / (q_norm * self._norm[i])))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    def already_tried(self, query: str, *, threshold: float = 0.30) -> list[Hit]:
        """Hits similar enough to be worth reading before spending compute.

        The threshold is a judgement, not a measurement: 0.30 was chosen so that a restated
        version of an existing tag clears it while a merely same-track idea does not. It is a
        prompt to read three lines, never an instruction to skip the work.
        """
        return [h for h in self.search(query, k=10) if h.score >= threshold]

    # -- sources ----------------------------------------------------------------------------

    @classmethod
    def load(cls, *, research: Path | None = None) -> KnowledgeIndex:
        research = research or RESEARCH
        entries: list[Entry] = []
        entries += load_experiments(research / "experiments.jsonl")
        entries += load_backlog(research / "backlog.md")
        return cls(entries)


def load_experiments(path: Path) -> list[Entry]:
    """Every row of the append-only ledger, as one searchable entry.

    The `tag` field is the payload: this repository writes genuinely descriptive tags
    ("S-32 placebo seed 4 (pandas book, ... DIAGNOSTIC, not promotable)"), which is why a
    lexical index works at all here. The headline stats go into `outcome` so a query can
    match on "negative" or a CAR figure.
    """
    if not path.exists():
        return []
    out: list[Entry] = []
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue          # a partial write from a concurrent appender; skip, never fail
        stats = row.get("stats") or {}
        outcome = " ".join(
            f"{k} {v}" for k, v in stats.items()
            if k in ("Compounding Annual Return", "Sharpe Ratio", "Drawdown", "Total Orders")
        )
        ts = str(row.get("ts", ""))
        out.append(Entry(
            doc_id=f"exp:{i}",
            kind="experiment",
            title=str(row.get("tag") or row.get("algorithm") or "(untagged run)"),
            date=f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else "",
            track=str(row.get("track") or ""),
            detail=f"{row.get('algorithm', '')} {row.get('class', '')} "
                   f"{row.get('start', '')} {row.get('end', '')}",
            outcome=outcome,
        ))
    return out


#: A backlog heading that names a tracked item, e.g. "### S-26 futures overlay" or "- **F-2**".
_ITEM = re.compile(r"^\s*(?:#{2,4}\s*|[-*]\s+)\**\[?([A-Z]{1,4}-\d+[a-z]?)\]?\**[ :.\-]*(.*)$")


def load_backlog(path: Path) -> list[Entry]:
    """Backlog items, tagged with the section they sit in.

    Section matters more than the text: an item under "## Done" is the direct answer to
    "have we tried this?", while the same words under "## Open" mean the opposite. `outcome`
    carries the section so a caller can tell them apart, and `kinds=` can filter.
    """
    if not path.exists():
        return []
    section = ""
    out: list[Entry] = []
    for i, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if raw.startswith("## "):
            section = raw[3:].strip()
        m = _ITEM.match(raw)
        if not m:
            continue
        code, title = m.group(1), m.group(2).strip()
        if not title:
            continue
        out.append(Entry(
            doc_id=f"backlog:{i}",
            kind="backlog",
            title=f"{code} {title}",
            track=code.split("-")[0],
            detail=section,
            outcome="done" if section.lower().startswith("done") else "open",
        ))
    return out


def _main(argv: list[str] | None = None) -> int:
    """`python -m quant_brain.core.knowledge "<idea>"` - what have we already tried?"""
    import argparse

    ap = argparse.ArgumentParser(description="Search what this repository has already tried.")
    ap.add_argument("query", nargs="+", help="the idea, in plain words")
    ap.add_argument("-k", type=int, default=8, help="how many hits to show")
    ap.add_argument("--kind", choices=("experiment", "backlog"), default=None)
    ap.add_argument("--threshold", type=float, default=None,
                    help="only show hits at or above this score")
    args = ap.parse_args(argv)

    idx = KnowledgeIndex.load()
    query = " ".join(args.query)
    kinds = (args.kind,) if args.kind else ()
    hits = idx.search(query, k=args.k, kinds=kinds)
    if args.threshold is not None:
        hits = [h for h in hits if h.score >= args.threshold]

    print(f"{len(idx.entries)} indexed entries; query: {query!r}\n")
    if not hits:
        print("  no similar prior work found - but a lexical index can miss a paraphrase, "
              "so this is weak evidence of novelty, not proof.")
        return 0
    for h in hits:
        print(f"  {h}")
    strong = [h for h in hits if h.score >= 0.30]
    if strong:
        print(f"\n  {len(strong)} hit(s) look close enough to read before spending compute.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
