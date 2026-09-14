"""No process in this repository may reach a venue while the freeze is on.

WHY THIS FILE EXISTS
--------------------
`scripts/intraday_trader.py` grew `ORDER_TRANSMISSION_ENABLED = False` and checks it inside
`LiveExecutor.submit`, so every order that runner can produce is refused at one chokepoint.
`scripts/paper_trade.py` grew a hard disable too, and it was put in front of the REBALANCE
path only.

The FLATTEN path sits about 130 lines earlier. It fires on `--flatten` or on the mere
existence of `live/HALT`, and it builds an `IBKRAdapter` and calls `RoutedExecutor.flatten`,
which reaches `ib.placeOrder`. It sits after the DU paper-account check but BEFORE the
`live/APPROVED_PAPER.md` check and BEFORE the hard disable. So

    python scripts/paper_trade.py --flatten

transmitted market orders while the same file printed "order transmission is hard-disabled"
on its other path, and `docs/READINESS_REMEDIATION_REPORT.md` said no broker order could be
made. There was no test on that refusal anywhere in the suite - `grep -rn
"research_remediation_hard_disable" tests/` found nothing - which is why a guard could be
added to one path and not the other and nothing noticed.

WHAT THIS CHECKS, AND WHAT IT CANNOT
------------------------------------
It is a source-structure test, deliberately. A behavioural test needs a live broker session
or a mock deep enough to be its own risk, and the property worth protecting is structural
anyway: that no call able to reach a venue is lexically reachable in a function before that
function has had the chance to return on the switch.

It cannot prove the absence of an order path. It proves that the paths that exist today are
guarded, that the switch is off, and that the two runners agree with each other. A new call
site in a new function would need a new entry in `VENUE_CALLS` - so the list itself is the
thing to keep honest, and `test_the_venue_call_list_still_matches_the_code` is the guard on
the guard.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: Every runner that can hold a broker connection. Both must carry the switch and both must
#: have it off. Keeping them in one list is the point: they disagreed, and that was the bug.
RUNNERS = ("scripts/intraday_trader.py", "scripts/paper_trade.py")

#: Names whose call can put an order on the wire. `submit` and `flatten` are the
#: `RoutedExecutor` surface; `placeOrder` is `ib_async` itself.
#:
#: Constructing an `IBKRAdapter` is deliberately NOT in this list. It opens no order, and
#: `intraday_trader.py` builds one in `LiveExecutor.__init__` on every run including a dry
#: one. Treating construction as transmission would have forced that runner to move a guard
#: it does not need and would have made this file a nuisance rather than a check.
VENUE_CALLS = ("placeOrder", "flatten", "submit")

SWITCH = "ORDER_TRANSMISSION_ENABLED"


def _tree(rel: str) -> tuple[ast.Module, str]:
    src = (REPO / rel).read_text(encoding="utf-8")
    return ast.parse(src, rel), src


def _call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _enclosing_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _guard_lines(fn) -> list[int]:
    """Lines of every `if ... ORDER_TRANSMISSION_ENABLED ...:` whose body can return or log.

    A guard that neither returns nor skips the call would be decoration, so the body must
    contain a `return` or the whole `if` must wrap the call itself.
    """
    out = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        if SWITCH not in ast.dump(node.test):
            continue
        returns = any(isinstance(n, ast.Return) for n in ast.walk(node))
        wraps_call = any(isinstance(n, ast.Call) and _call_name(n) in VENUE_CALLS
                         for n in ast.walk(node))
        if returns or wraps_call:
            out.append(node.lineno)
    return out


# ---------------------------------------------------------------------------------------
# The switch itself
# ---------------------------------------------------------------------------------------

@pytest.mark.runner
@pytest.mark.parametrize("rel", RUNNERS)
def test_the_runner_declares_the_switch_and_it_is_off(rel):
    """`ORDER_TRANSMISSION_ENABLED = False` at module level, in both runners.

    Module level and a literal `False`, not a computed value: a switch whose state depends on
    an environment variable or a file is a switch whose state has to be reasoned about, and
    this one has to be readable at a glance by someone deciding whether it is safe to run a
    scheduled task.
    """
    tree, _ = _tree(rel)
    found = [n for n in tree.body
             if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == SWITCH for t in n.targets)]
    assert found, f"{rel} has no module-level {SWITCH}"
    assert len(found) == 1, f"{rel} assigns {SWITCH} {len(found)} times; there must be one"
    value = found[0].value
    assert isinstance(value, ast.Constant) and value.value is False, (
        f"{rel} sets {SWITCH} to {ast.dump(value)}; it must be the literal False while the "
        f"repository is in research remediation")


def test_the_two_runners_agree():
    """They did not, and that is the whole story of this file."""
    states = {}
    for rel in RUNNERS:
        _, src = _tree(rel)
        states[rel] = f"{SWITCH} = False" in src
    assert all(states.values()), f"runners disagree about the freeze: {states}"


# ---------------------------------------------------------------------------------------
# Every venue call is behind it
# ---------------------------------------------------------------------------------------

def _guarded_chokepoints(tree: ast.Module) -> set[str]:
    """Functions in this file whose own body refuses on the switch.

    The two runners are built differently and both designs are legitimate.
    `intraday_trader.py` has ONE chokepoint - `LiveExecutor.submit` checks the switch and
    returns `[]` - so every `executor.submit(...)` in that file is safe wherever it appears.
    `paper_trade.py` has no such chokepoint on its flatten path: it calls
    `RoutedExecutor.flatten`, which lives in `quant_brain` and knows nothing about this
    freeze, so that call has to be guarded where it is made.

    A single chokepoint is the better design of the two, and this function is what lets the
    test accept it instead of forcing every caller to repeat a check.
    """
    by_name: dict[str, list] = {}
    for fn in _enclosing_functions(tree):
        by_name.setdefault(fn.name, []).append(fn)
    out = set()
    for name, fns in by_name.items():
        # EVERY definition of the name has to be safe, not just one. Matching on the name
        # alone was the first version of this and it has a hole worth stating:
        # `intraday_trader.py` defines both `LiveExecutor.submit`, which is guarded, and
        # `SimExecutor.submit`, which is not - and once the guarded one existed, every call
        # written `x.submit(...)` was exempt regardless of which class it landed on. Today
        # `SimExecutor.submit` only updates a dict and cannot reach a venue, so nothing is
        # actually wrong; the point is that the test could not tell.
        #
        # "Safe" is therefore guarded OR demonstrably broker-free: a body that names none of
        # the broker handles below cannot place an order whatever it is called.
        if all(_guard_lines(fn) or not _touches_a_broker(fn) for fn in fns):
            out.add(name)
    return out


#: Identifiers that only appear in code that can reach a venue. A function whose body
#: mentions none of these is not the function that places an order.
BROKER_HANDLES = ("IBKRAdapter", "RoutedExecutor", "placeOrder", "qualifyContracts",
                  "self.adapter", "self.ib", "ib.")


def _touches_a_broker(fn) -> bool:
    return any(h in ast.unparse(fn) for h in BROKER_HANDLES)


@pytest.mark.runner
@pytest.mark.parametrize("rel", RUNNERS)
def test_every_venue_call_sits_behind_the_switch(rel):
    """Every call able to reach a venue is either guarded where it is made, or dispatches to
    a chokepoint in the same file that is guarded.

    "Guarded where it is made" is by line number within the function, which is the property
    that actually failed: the flatten branch was at line ~665 and the hard disable at ~789,
    so the orders went out 124 lines before the refusal was printed.
    """
    tree, _ = _tree(rel)
    chokepoints = _guarded_chokepoints(tree)
    offenders = []
    for fn in _enclosing_functions(tree):
        guards = _guard_lines(fn)
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name not in VENUE_CALLS:
                continue
            if name in chokepoints:
                continue                      # dispatches to a guarded chokepoint
            if any(g < node.lineno for g in guards):
                continue                      # guarded where it is made
            offenders.append(f"{rel}:{node.lineno} {name}() in {fn.name}() "
                             f"(guards here: {guards or 'none'}; "
                             f"guarded chokepoints in file: {sorted(chokepoints) or 'none'})")
    assert not offenders, (
        "a call that can reach a venue is reachable before the transmission switch is "
        "checked:" + "".join(chr(10) + "  " + o for o in offenders))


@pytest.mark.runner
def test_the_intraday_runner_guards_at_a_chokepoint_rather_than_at_every_caller():
    """Pins the DESIGN, not just the outcome.

    If someone later removes the check from `LiveExecutor.submit` and sprinkles guards at the
    call sites instead, the test above would still pass while the property got much easier to
    break - one new caller and the freeze is off. Assert the chokepoint exists by name.
    """
    tree, _ = _tree("scripts/intraday_trader.py")
    assert "submit" in _guarded_chokepoints(tree), (
        "LiveExecutor.submit no longer refuses on the switch; the intraday runner's single "
        "chokepoint is gone and every caller is now load-bearing")


def test_the_flatten_path_refuses_and_says_the_positions_are_still_open():
    """A refusal nobody hears is worse than the order.

    The flatten branch fires on `live/HALT`, which is the file a human creates when something
    is wrong. Refusing to close positions and staying quiet about it would leave someone
    believing the halt had flattened the book. The refusal must name the positions and say
    they need a hand.
    """
    _, src = _tree("scripts/paper_trade.py")
    i = src.index("if HALT.exists() or args.flatten:")
    j = src.index("held = {s_: q_ for s_, q_ in positions.items() if q_}", i)
    branch = src[i:j]
    assert f"if not {SWITCH}" in branch, "the flatten branch does not check the switch"
    assert "log_event" in branch and "notify" in branch, (
        "the flatten refusal must both log and push to the chat channel")
    assert "STILL OPEN" in branch, (
        "the operator message must say the positions were not closed")
    assert "return 3" in branch, "the refusal must exit rather than fall through"


def test_the_venue_call_list_still_matches_the_code():
    """The guard on the guard.

    This file can only check the call names it knows about. If a runner starts reaching a
    venue through a name that is not in `VENUE_CALLS`, every test above passes and proves
    nothing. So: each name must still appear in at least one runner, which catches the list
    going stale in the direction of a rename.
    """
    joined = "".join(_tree(rel)[1] for rel in RUNNERS)
    missing = [n for n in VENUE_CALLS if n not in joined]
    assert not missing, (
        f"{missing} no longer appear in either runner. Either they were renamed - in which "
        f"case add the new name here before deleting the old one - or the path is gone.")


def test_a_same_named_method_cannot_hide_behind_a_guarded_one():
    """The hole the chokepoint rule closes, asserted directly.

    `intraday_trader.py` defines `submit` twice: `LiveExecutor.submit`, which is guarded, and
    `SimExecutor.submit`, which is not. Under a rule that matched on the name alone, the
    guarded one made every `submit` call in the file exempt. `SimExecutor.submit` is safe
    today because it only updates a dict, and this test says that out loud so that the day it
    grows a broker handle the exemption disappears with it.
    """
    tree, _ = _tree("scripts/intraday_trader.py")
    submits = [fn for fn in _enclosing_functions(tree) if fn.name == "submit"]
    assert len(submits) >= 2, (
        f"expected at least two definitions of submit in intraday_trader.py, found "
        f"{len(submits)}; if the simulator was renamed, this test is stale rather than wrong")
    guarded = [fn for fn in submits if _guard_lines(fn)]
    brokerless = [fn for fn in submits if not _touches_a_broker(fn)]
    assert guarded, "no definition of submit checks the switch"
    assert len(guarded) + len(brokerless) >= len(submits), (
        "a definition of submit neither checks the switch nor is free of broker handles")


def test_both_paths_in_paper_trade_read_the_same_switch():
    """One constant, both paths.

    The rebalance guard was unconditional while the flatten branch had none, so flipping
    ORDER_TRANSMISSION_ENABLED to True would have re-armed flatten and left rebalance dead -
    a half-thaw in which the runner can close positions but not open them. Whatever the
    switch is set to, both paths must agree with it.
    """
    _, src = _tree("scripts/paper_trade.py")
    assert src.count(f"if not {SWITCH}") >= 2, (
        "paper_trade.py has fewer than two switch checks; the flatten path and the rebalance "
        "path must each read it")
    assert 'path="flatten"' in src and 'path="rebalance"' in src, (
        "each refusal must say which path it came from, so a log line is diagnosable")
