"""Provenance for the V1.0.0_Frozen golden suite. Prints what was certified, and on what.

    python scripts/vwap_certify.py            # the provenance block
    python scripts/vwap_certify.py --run      # and run the three golden suites

Brief §32. A golden suite whose result cannot be tied to a specific specification, a specific
commit and a specific interpreter is a result nobody can reproduce, and the ambiguity register
is part of that record: a reading the owner has not confirmed is a caveat on every number the
suite produces, not a footnote in a document.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.strategies.vwap_pullback.spec import (  # noqa: E402
    AMBIGUITIES,
    CONFLICTS,
    FROZEN,
    FROZEN_MNQ,
    TIMEZONE,
    VERSION,
    characteristics,
    execution_table,
    resolved,
    unresolved,
)

SUITES = ("tests/test_vwap_indicators.py", "tests/test_vwap_strategy.py",
          "tests/test_vwap_governor.py")


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                              timeout=20, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):          # pragma: no cover
        return ""


def provenance() -> dict:
    import numpy
    import pandas
    return {
        "strategy_version": VERSION,
        "spec_hash_nq": FROZEN.spec_hash,
        "spec_hash_mnq": FROZEN_MNQ.spec_hash,
        "timezone": TIMEZONE.key,
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "suites": list(SUITES),
        "ambiguities_total": len(AMBIGUITIES),
        "ambiguities_resolved": [a.ref for a in resolved()],
        "ambiguities_material_unconfirmed": [a.ref for a in unresolved()],
        "specification_characteristics": [c.ref for c in characteristics()],
        "conflicts_total": len(CONFLICTS),
        "execution_profile": FROZEN.execution.name,
        "randomness": "none - no seeded or unseeded generator is imported by the package",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true", help="run the three golden suites too")
    ap.add_argument("--json", action="store_true", help="emit the provenance block only")
    args = ap.parse_args()

    prov = provenance()
    if args.json:
        print(json.dumps(prov, indent=1))
        return 0

    print("=" * 96)
    print(f"V1.0.0_FROZEN CERTIFICATION PROVENANCE")
    print("=" * 96)
    print(FROZEN.describe())
    print()
    print(execution_table())
    print()
    for k, v in prov.items():
        print(f"  {k:36} {v}")

    print("\n" + "=" * 96)
    print("AMBIGUITY REGISTER - readings taken where the specification admits more than one")
    print("=" * 96)
    for a in AMBIGUITIES:
        flag = "  ** MATERIAL, NEEDS OWNER CONFIRMATION **" if a.material else ""
        print(f"\n  {a.ref}  {a.rule}{flag}")
        print(f"      question: {a.question}")
        print(f"      reading : {a.reading}")
        if a.both_implemented:
            print("      both readings are implemented and tested")

    print("\n" + "=" * 96)
    print("CONFLICT REGISTER - where the frozen spec disagrees with certified existing code")
    print("=" * 96)
    for c in CONFLICTS:
        print(f"\n  {c.ref}  {c.component}")
        print(f"      disagreement: {c.disagreement}")
        print(f"      resolution  : {c.resolution}")

    if args.run:
        print("\n" + "=" * 96)
        print("RUNNING THE GOLDEN SUITES")
        print("=" * 96)
        r = subprocess.run([sys.executable, "-m", "pytest", *SUITES, "-q",
                            "-p", "no:randomly"], cwd=REPO, check=False)
        return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
