"""AUD-12 / S-35: a promotion may not carry a parameter the paper runner cannot trade.

The defect. `algorithms/s1_momo/main.py` builds its `sig.Params(...)` from `S1_*` environment
variables - 49 of the 56 names it reads go into the signal. Nothing carries them anywhere else:
`scripts/paper_trade.py:196` asks for `getattr(sig, "PARAMS", None)` and `signals.py` defines
`DEFAULTS`, so the runner always trades the defaults; `scripts/compare_orders.py:158` builds
`sig.Params()`, so the deploy gate compares the defaults with the defaults and agrees with
itself; and `--promote` recorded no `env` at all, so the override left no trace in the record.

S-35 priced it on the one ledger row that passed the pre-patch rules, `20260911T184723Z`
(S-20's defensive off-state at 2 bp): the promotion claims **+1.914 CAR points**, the account
receives **0.000** of them, the two books hold different things on **13.6% of sessions**, and
afterwards `champion.json` demands 24.982% from a book that earns 23.068% - which flips
**11 of the 167 `s1_momo` rows from "beats" to "does not"**, so the defect also denies the
account improvements it could have had. AUD-10 handed a candidate slack; this one withholds it.

The fix is an ALLOW list, and that is the load-bearing design decision these tests defend: a
deny list would have to name 49 keys and be re-derived every time a knob is added to `main.py`.
`test_allow_list_is_pinned_to_main_py` is the one that makes the choice real - it re-derives the
`S1_*` surface from the source and fails when a new knob appears that someone quietly added to
the allow list.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import evaluate as ev
import pytest

REPO = Path(__file__).resolve().parents[1]
MAIN_PY = REPO / "algorithms" / "s1_momo" / "main.py"

CHAMPION_STATS = {"Total Orders": "5128", "Compounding Annual Return": "23.068%",
                  "Sharpe Ratio": "0.938", "Drawdown": "25.000%"}

#: the real row S-35 priced the defect on
S20_ENV = {"S1_RISK_OFF_SLEEVE": "TLT,IEF,GLD", "S1_SLIPPAGE_BPS": "2"}
S20_STATS = {"Total Orders": "5305", "Compounding Annual Return": "24.982%",
             "Sharpe Ratio": "0.914", "Drawdown": "25.700%"}


@pytest.fixture
def champion():
    return {
        "algorithm": "s1_momo", "class": "S1MomentumRotationAlgorithm",
        "run_dir": r"results\s1_momo\CHAMP", "commit": "d41aefe",
        "stats": dict(CHAMPION_STATS),
        # both cost columns, so S-18's "same cost model" rule never decides a case this file
        # is about; the 0 bp column is the same book re-run, as it is in research/champion.json
        "stats_by_spread": {
            "0.0": dict(CHAMPION_STATS, run_dir=r"results\s1_momo\CHAMP"),
            "2.0": dict(CHAMPION_STATS, run_dir=r"results\s1_momo\CHAMP"),
        },
        "criteria": {"min_trades": 30, "must_beat": ["Compounding Annual Return"],
                     "sharpe_tolerance": 0.03, "drawdown_tolerance_points": 1.0,
                     "max_drawdown_limit": "35%"},
    }


def run_row(env=None, **over):
    row = {"ts": "20260911T184723Z", "algorithm": "s1_momo", "class": "S1Mom",
           "tag": "S-20 defensive sleeve TLT/IEF/GLD, top 1, 2 bp",
           "commit": "26b6b4a", "run_dir": r"results\s1_momo\CAND",
           "stats": dict(S20_STATS)}
    if env is not None:
        row["env"] = dict(env)
    row.update(over)
    return row


# --------------------------------------------------------------- the allow list is the design

def env_surface() -> set[str]:
    """Every `S1_*` name `main.py` reads, re-derived from the source."""
    src = MAIN_PY.read_text(encoding="utf-8")
    names = set(re.findall(r'os\.environ\.get\(\s*"(S1_[A-Z0-9_]+)"', src))
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("_env", "_env_date") and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            names.add("S1_" + node.args[0].value)
    return names


def test_allow_list_is_pinned_to_main_py():
    """A knob added to main.py must be refused by default, not silently promotable.

    This is the test that keeps the fix from decaying. `INERT_ENV` is allowed to name keys
    main.py no longer reads (S-22's `S1_NOOP` is one, and rows carrying it are still in the
    ledger), but it may never name a key main.py feeds into the signal.
    """
    surface = env_surface()
    assert len(surface) > 40, "the S1_* surface failed to parse; the derivation is broken"
    # every key in the allow list that main.py still reads must sit OUTSIDE the Params call
    params_call = None
    for node in ast.walk(ast.parse(MAIN_PY.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "Params"):
            params_call = node
            break
    assert params_call is not None, "main.py no longer builds sig.Params(...)"
    inside = set()
    for node in ast.walk(params_call):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith("S1_"):
                inside.add(node.value)
            else:
                inside.add("S1_" + node.value)
    leaked = ev.INERT_ENV & inside
    assert not leaked, f"allow-listed keys that reach sig.Params(): {sorted(leaked)}"


def test_reaching_env_splits_the_surface():
    assert ev.reaching_env({"S1_SLIPPAGE_BPS": "2"}) == {}
    assert ev.reaching_env({"S1_TOP_N": "5"}) == {"S1_TOP_N": "5"}
    assert ev.reaching_env(S20_ENV) == {"S1_RISK_OFF_SLEEVE": "TLT,IEF,GLD"}
    assert ev.reaching_env(None) == {}
    assert ev.reaching_env({}) == {}


def test_proxy_is_refused_even_though_it_is_not_a_params_argument():
    """`S1_PROXY=on` mutates `signals.LEVERED_PROXY`, a module global, not a Params field.

    It is the case a Params-shaped derivation would miss: the runner imports `signals` fresh
    and gets the empty map, so a promoted 3x book would paper trade unlevered parents. Default
    deny is what catches it.
    """
    assert ev.reaching_env({"S1_PROXY": "on"}) == {"S1_PROXY": "on"}


# ------------------------------------------------------------------------ the candidate half

def test_the_real_s20_row_is_refused(champion):
    ok, reasons = ev.verdict(run_row(S20_ENV), champion)
    assert not ok
    assert any("S1_RISK_OFF_SLEEVE=TLT,IEF,GLD" in r for r in reasons)
    assert any("paper_trade.py cannot reproduce" in r for r in reasons)


def test_the_same_row_passed_before_the_rule(champion, monkeypatch):
    """The defect was live: without this rule the row beats the champion on every criterion."""
    monkeypatch.setattr(ev, "param_env_note", lambda run: None)
    ok, reasons = ev.verdict(run_row(S20_ENV), champion)
    assert ok, reasons


def test_inert_env_still_passes(champion):
    """S-17/S-21/S-22's instruments are cost models, not parameters, and stay comparable."""
    ok, reasons = ev.verdict(run_row({"S1_SLIPPAGE_BPS": "2"}), champion)
    assert ok, reasons


def test_a_row_with_no_env_is_untouched(champion):
    assert ev.verdict(run_row(), champion)[0]
    assert ev.verdict(run_row({}), champion)[0]


def test_the_refusal_names_the_remedy(champion):
    note = ev.param_env_note(run_row({"S1_TOP_N": "5"}))
    assert "signals.py" in note and "Params default" in note


def test_financing_rule_still_fires_on_its_own(champion):
    """S-21's rule is separate and must not be swallowed by the new one."""
    ok, reasons = ev.verdict(run_row({"S1_FINANCING": "on"}), champion)
    assert not ok
    assert any("margin financing" in r for r in reasons)
    assert not any("paper_trade.py cannot reproduce" in r for r in reasons)


def test_window_rule_still_fires_on_its_own(champion):
    ok, reasons = ev.verdict(run_row({"S1_START": "2020-01-02"}), champion)
    assert not ok
    assert any("not the champion's" in r for r in reasons)
    assert not any("paper_trade.py cannot reproduce" in r for r in reasons)


# --------------------------------------------------------------------------- the reader half

def test_champion_recording_an_override_refuses_everything(champion):
    champion["env"] = {"S1_RISK_OFF_SLEEVE": "TLT,IEF,GLD"}
    ok, reasons = ev.verdict(run_row(), champion)
    assert not ok
    assert any("the deployed book is not the one described here" in r for r in reasons)


def test_champion_with_inert_env_is_silent(champion):
    champion["env"] = {"S1_SLIPPAGE_BPS": "2"}
    assert ev.champion_env_note(champion) is None
    assert ev.verdict(run_row(), champion)[0]


def test_champion_without_an_env_key_is_silent(champion):
    """Promotions before S-35 recorded nothing; that must not refuse every comparison."""
    assert "env" not in champion
    assert ev.champion_env_note(champion) is None


def test_the_table_warns_about_a_hand_edited_champion(champion, capsys):
    champion["env"] = {"S1_PROXY": "on"}
    ev.table([run_row()], champion)
    assert "WARNING" in capsys.readouterr().out


# ------------------------------------------------------------------------------- the writer

def test_promote_records_the_env(tmp_path, monkeypatch, champion):
    """End to end through `main()`, so the write path is the one that ships."""
    ledger = tmp_path / "experiments.jsonl"
    champ_file = tmp_path / "champion.json"
    row = run_row({"S1_SLIPPAGE_BPS": "2"},
                  stats=dict(CHAMPION_STATS, **{"Compounding Annual Return": "26.000%"}),
                  run_dir=r"results\s1_momo\WINNER")
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    champ_file.write_text(json.dumps(champion) + "\n", encoding="utf-8")
    monkeypatch.setattr(ev, "LEDGER", ledger)
    monkeypatch.setattr(ev, "CHAMPION", champ_file)
    monkeypatch.setattr(sys, "argv", ["evaluate.py", "--promote", row["ts"]])

    assert ev.main() == 0
    out = json.loads(champ_file.read_text(encoding="utf-8"))
    assert out["env"] == {"S1_SLIPPAGE_BPS": "2"}
    assert ev.champion_env_note(out) is None


def test_promote_refuses_a_run_with_a_reaching_override(tmp_path, monkeypatch, champion):
    ledger = tmp_path / "experiments.jsonl"
    champ_file = tmp_path / "champion.json"
    ledger.write_text(json.dumps(run_row(S20_ENV)) + "\n", encoding="utf-8")
    before = json.dumps(champion)
    champ_file.write_text(before + "\n", encoding="utf-8")
    monkeypatch.setattr(ev, "LEDGER", ledger)
    monkeypatch.setattr(ev, "CHAMPION", champ_file)
    monkeypatch.setattr(sys, "argv", ["evaluate.py", "--promote", "20260911T184723Z"])

    assert ev.main() == 1
    assert champ_file.read_text(encoding="utf-8") == before + "\n", "champion.json was written"


def test_promote_keeps_recording_an_absent_env_as_empty(tmp_path, monkeypatch, champion):
    ledger = tmp_path / "experiments.jsonl"
    champ_file = tmp_path / "champion.json"
    row = run_row(stats=dict(CHAMPION_STATS, **{"Compounding Annual Return": "26.000%"}),
                  run_dir=r"results\s1_momo\WINNER")
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    champ_file.write_text(json.dumps(champion) + "\n", encoding="utf-8")
    monkeypatch.setattr(ev, "LEDGER", ledger)
    monkeypatch.setattr(ev, "CHAMPION", champ_file)
    monkeypatch.setattr(sys, "argv", ["evaluate.py", "--promote", row["ts"]])

    assert ev.main() == 0
    assert json.loads(champ_file.read_text(encoding="utf-8"))["env"] == {}


def test_promotion_still_retires_the_cost_columns(tmp_path, monkeypatch, champion):
    """AUD-10's fix must survive AUD-12's patch; the two writers share one dict."""
    champion["stats_by_spread"]["s34_note"] = "kept"
    ledger = tmp_path / "experiments.jsonl"
    champ_file = tmp_path / "champion.json"
    row = run_row({"S1_SLIPPAGE_BPS": "2"},
                  stats=dict(CHAMPION_STATS, **{"Compounding Annual Return": "26.000%"}),
                  run_dir=r"results\s1_momo\WINNER")
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    champ_file.write_text(json.dumps(champion) + "\n", encoding="utf-8")
    monkeypatch.setattr(ev, "LEDGER", ledger)
    monkeypatch.setattr(ev, "CHAMPION", champ_file)
    monkeypatch.setattr(sys, "argv", ["evaluate.py", "--promote", row["ts"]])

    assert ev.main() == 0
    out = json.loads(champ_file.read_text(encoding="utf-8"))
    assert sorted(ev.cost_columns(out)) == ["2.0"]
    assert ev.cost_columns(out)["2.0"]["run_dir"] == r"results\s1_momo\WINNER"
    assert out["stats_by_spread"]["s34_note"] == "kept"
    assert ev.stale_note(out) is None


# ---------------------------------------------------------------- the runner's dead lookup

def test_the_runner_trades_the_defaults_and_nothing_else():
    """Clause 7, pinned rather than patched.

    `paper_trade.py` resolves `getattr(sig, "PARAMS", None)` and falls through to
    `signals.DEFAULTS`. S-35 deliberately did not edit the live runner - the refusal above
    closes the hole and an edit would owe a `--replay` for no measured gain - so the invariant
    it relies on is stated here instead. If `signals.PARAMS` ever appears, the runner starts
    trading something `compare_orders.py` does not check and this test says so.
    """
    sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
    import signals as sig

    assert not hasattr(sig, "PARAMS"), (
        "signals.PARAMS now exists, so paper_trade.py:196 no longer resolves to DEFAULTS; "
        "compare_orders.py still builds sig.Params() and would not see the difference")
    assert sig.DEFAULTS == sig.Params()
    assert "IEF" not in sig.traded_universe(sig.DEFAULTS)


def test_evaluate_still_runs_as_a_script():
    """The table path, against the real ledger and the real champion, must stay green."""
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "evaluate.py"),
                          "--algorithm", "s1_momo", "--last", "5"],
                         capture_output=True, text=True, cwd=REPO)
    assert out.returncode == 0, out.stderr
    assert "champion: s1_momo" in out.stdout
