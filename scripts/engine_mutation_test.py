"""Phase 17: break the engine on purpose and check the tests notice.

WHY A PASSING SUITE PROVES NOTHING ON ITS OWN
-----------------------------------------------
`tests/test_engine_forensics.py` passes. So would a suite of `assert True`. The question that
matters is whether the tests would have caught the bug if the bug were there, and the only way
to answer it is to put the bug there.

Each mutation below is a defect that has plausibly occurred in a real backtester - several of
them have occurred in THIS repository and are described in its own docstrings. The harness
applies one mutation at a time by monkey-patching the live function, runs the forensic suite,
and records whether anything failed.

    CAUGHT    at least one test failed. The suite defends that behaviour.
    SURVIVED  every test passed with the engine broken. That is a hole, and the brief says
              to fix the suite rather than shrug.

The mutations are applied in-process and reverted immediately. Nothing is written to the
source tree.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

MUT_DIR = REPO / "research" / "_mutations"


# --------------------------------------------------------------------------------------
# The mutations. Each returns (module_path, original_source, mutated_source).
# --------------------------------------------------------------------------------------

from _mutation_specs import MUTATIONS  # noqa: E402


#: Which suite defends which layer. A mutation names its own, because running the whole test
#: tree for every one of them would take hours and running the WRONG one would score a hole
#: as a catch - the integration defects are invisible to the P&L forensics suite and the
#: reverse is equally true.
FORENSICS = "tests/test_engine_forensics.py"
PIPELINE = "tests/test_canonical_pipeline.py"
TWIN = "tests/test_topstep_twin_forensics.py"


def run_suite(suite: str = FORENSICS) -> tuple[bool, str]:
    """Run one suite. Returns (all_passed, tail_of_output)."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *suite.split(),
         "-q", "--no-header", "-x", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True, timeout=1800)
    return r.returncode == 0, (r.stdout or "")[-400:]


def main() -> int:
    print("=" * 100)
    print("PHASE 17 - MUTATION TESTING")
    print("one deliberate defect at a time; the suite must fail")
    print("=" * 100)

    baseline_ok, _ = run_suite()
    if not baseline_ok:
        print("  BASELINE SUITE IS RED - fix that before mutating")
        return 1
    print("  baseline: suite green\n")

    caught = survived = skipped = 0
    results = []
    for entry in MUTATIONS:
        name, relpath, find, replace = entry[:4]
        suite = entry[4] if len(entry) > 4 else FORENSICS
        f = REPO / relpath
        original = f.read_text(encoding="utf-8")
        if find not in original:
            print(f"  {'SKIP':9} {name:52} (anchor not found in {relpath})")
            skipped += 1
            results.append((name, "SKIP"))
            continue
        try:
            f.write_text(original.replace(find, replace, 1), encoding="utf-8")
            ok, tail = run_suite(suite)
            if ok:
                survived += 1
                results.append((name, "SURVIVED"))
                print(f"  {'SURVIVED':9} {name:52} <-- HOLE IN THE SUITE")
            else:
                caught += 1
                results.append((name, "CAUGHT"))
                print(f"  {'caught':9} {name:52}")
        finally:
            f.write_text(original, encoding="utf-8")

    total = caught + survived
    print(f"\n  mutations applied : {total} ({skipped} skipped)")
    print(f"  caught            : {caught}")
    print(f"  survived          : {survived}")
    if total:
        print(f"  mutation score    : {caught / total:.0%}")
    if survived:
        print("\n  SURVIVORS - each is a behaviour the suite does not defend:")
        for n, v in results:
            if v == "SURVIVED":
                print(f"    - {n}")
    MUT_DIR.mkdir(parents=True, exist_ok=True)
    (MUT_DIR / "mutation_results.txt").write_text(
        "\n".join(f"{v}\t{n}" for n, v in results), encoding="utf-8")

    # restore-integrity check: the tree must be exactly as we found it
    final_ok, _ = run_suite()
    print(f"\n  suite green after restore: {final_ok}")
    return 0 if final_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
