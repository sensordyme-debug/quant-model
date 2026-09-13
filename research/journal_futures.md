
## 2026-09-13 — where the multi-contract futures work actually landed

Recording this the way the daily track recorded S-39 in `560b0bb`, because the history is
otherwise misleading and this is the third instance today of the same hazard.

`98512df` ("ml: F-16 …") contains, under the ml track's message:

- `scripts/futures_fetch_multi.py` and `tests/test_futures_fetch_multi.py` — the multi-contract
  IBKR fetcher (clientId 77, historical only) and its 51 tests
- `research/futures_discovery_{es,mes,mnq}.json` — the corrected cross-contract funnel runs
- 408 lines of `research/experiments_futures.jsonl` — the ledger rows for those runs

What that commit actually delivered on this track:

  MES  358,845 bars  317d   NQ  447,596 bars  395d   MNQ  358,845 bars  317d
  all 0 FAIL / 2 WARN (roll_gap, roll_overlap), same profile as ES

  544 hypotheses across four contracts with the opening-range lookahead corrected:
  ES 124 statistical + 12 cost, MES 127 + 9, NQ 134 + 2, MNQ 135 + 1, ZERO survivors.

MES/MNQ stop a quarter short of ES/NQ because MESU5 and MNQU5 have aged out of IBKR
retention (error 200 by localSymbol and by contract month). Nothing was substituted.

THE RULE THAT LET IT HAPPEN, three times in one day and in both directions:
`git add -A` or a bare `git add <dir>` in a tree six tracks share. I did it to the S-39 files
and to `tests/test_intraday_splits.py` (split back out in `90704c4`); the ml track did it to
these. `AGENTS.md` already says "no more git add -A" — the missing half is that after clearing
a stale `.git/index.lock` you must check what is already staged before committing, because a
killed process leaves its staged files behind for whoever commits next.
