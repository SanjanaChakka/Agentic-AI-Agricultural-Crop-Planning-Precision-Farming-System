"""Guards the risk agent's ML-escalation branch.

``_model_finding`` gained a ``ctx`` parameter to match the rule-finding helpers,
but its single call site kept passing two arguments. That mismatch only raises
when the trained classifier places a field in a *more* severe bucket than the
rule-based scan did, so the branch is data-dependent: acceptance TC-06 passed on
most runs and crashed the whole risk agent on the ones where the model
escalated, silently leaving the run with zero alerts.

The arity check below is static, so it fails on the mismatch itself rather than
waiting for a fixture that happens to reach the branch.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.agents import decision_agents
from app.agents.decision_agents import _model_finding

MODULE_PATH = Path(decision_agents.__file__)


def test_model_finding_accepts_context() -> None:
    params = list(inspect.signature(_model_finding).parameters)
    assert params == ["prediction", "disclaimer", "ctx"]


def test_model_finding_returns_a_non_diagnostic_finding() -> None:
    finding = _model_finding(
        {"prediction_label": "moderate", "confidence": 0.71},
        "Environmental conditions only.",
        ctx=object(),  # unused by design; the signature mirrors the rule helpers
    )
    assert finding["severity"] == "medium"
    assert finding["evidence"]
    # Must stay a favourability statement, never a diagnosis.
    assert "diagnos" not in finding["statement"].lower()


def _call_arity(node: ast.FunctionDef) -> tuple[int, list[int]]:
    """Return (declared positional params, arg counts passed at each call site)."""
    declared = len(node.args.posonlyargs) + len(node.args.args)
    calls: list[int] = []
    for child in ast.walk(ast.parse(MODULE_PATH.read_text(encoding="utf-8"))):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == node.name:
            calls.append(len(child.args) + len(child.keywords))
    return declared, calls


def test_every_call_site_matches_the_signature() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    target = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_model_finding")
    declared, calls = _call_arity(target)

    assert calls, "expected at least one call site to check"
    for count in calls:
        assert count == declared, (
            f"_model_finding declares {declared} parameters but a call site passes {count}; "
            "the data-dependent ML-escalation branch would raise TypeError at runtime"
        )


@pytest.mark.parametrize("label,expected", [("low", "medium"), ("severe", "high")])
def test_severity_bucket_mapping(label: str, expected: str) -> None:
    finding = _model_finding({"prediction_label": label, "confidence": 0.5}, "", ctx=object())
    assert finding["severity"] == expected
