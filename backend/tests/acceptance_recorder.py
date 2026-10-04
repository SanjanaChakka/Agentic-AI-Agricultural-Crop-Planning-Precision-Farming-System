"""Shared helpers for the acceptance-test record.

The six mandatory cases (TC-01 .. TC-06) are not ordinary assertions: each one
records what was sent, what was expected, what actually came back, which agents
were involved and what evidence backed it, then writes the whole thing to
``artifacts/acceptance_report.json`` / ``.md`` so the result can be read without
re-running anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = BACKEND_ROOT / "artifacts"


@dataclass
class CaseResult:
    """One acceptance case, recorded in full."""

    case_id: str
    title: str
    requirement: str
    inputs: dict[str, Any] = field(default_factory=dict)
    expected: list[str] = field(default_factory=list)
    actual: list[str] = field(default_factory=list)
    agents_invoked: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    status: str = "PASS"
    notes: str = ""

    def check(self, description: str, passed: bool, detail: str = "") -> bool:
        self.checks.append({"check": description, "passed": bool(passed), "detail": detail})
        if not passed:
            self.status = "FAIL"
        return bool(passed)

    def expect(self, description: str, actual_value: Any, predicate=None) -> bool:
        """Record an observation and assert it with an optional predicate."""
        rendered = _render(actual_value)
        self.actual.append(f"{description}: {rendered}")
        passed = predicate(actual_value) if predicate is not None else bool(actual_value)
        return self.check(description, passed, rendered)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "requirement": self.requirement,
            "status": self.status,
            "notes": self.notes,
            "inputs": self.inputs,
            "expected": self.expected,
            "actual": self.actual,
            "agents_invoked": self.agents_invoked,
            "evidence": self.evidence,
            "sources": self.sources,
            "checks": self.checks,
            "checks_total": len(self.checks),
            "checks_passed": sum(1 for item in self.checks if item["passed"]),
        }


def _render(value: Any) -> str:
    if isinstance(value, str | int | float | bool) or value is None:
        return str(value)
    if isinstance(value, list | tuple):
        return f"[{', '.join(_render(item) for item in value[:8])}]" + (
            f" (+{len(value) - 8} more)" if len(value) > 8 else ""
        )
    if isinstance(value, dict):
        return json.dumps(value, default=str)[:400]
    return str(value)[:400]


def evidence_digest(items: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    """Compact, human-readable evidence rows for the record."""
    rows = []
    for item in list(items)[:limit]:
        kind = item.get("kind")
        rows.append(
            {
                "label": item.get("label"),
                "value": item.get("value"),
                "unit": item.get("unit"),
                "kind": getattr(kind, "value", kind),
                "source": item.get("source"),
                "reference": item.get("reference"),
            }
        )
    return rows


def source_digest(items: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    return [
        {
            "doc_key": item.get("doc_key"),
            "title": item.get("title"),
            "category": item.get("category"),
            "score": item.get("score"),
        }
        for item in list(items)[:limit]
    ]


def write_report(results: list[CaseResult]) -> dict[str, Any]:
    """Persist the acceptance record as JSON and Markdown."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "total_cases": len(results),
        "passed": sum(1 for item in results if item.status == "PASS"),
        "failed": sum(1 for item in results if item.status != "PASS"),
        "total_checks": sum(len(item.checks) for item in results),
        "checks_passed": sum(sum(1 for c in item.checks if c["passed"]) for item in results),
        "cases": [item.as_dict() for item in results],
    }

    (ARTIFACTS / "acceptance_report.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    lines: list[str] = [
        "# Acceptance test record (TC-01 .. TC-06)",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        f"**Cases:** {payload['passed']}/{payload['total_cases']} passed &nbsp;|&nbsp; "
        f"**Checks:** {payload['checks_passed']}/{payload['total_checks']} passed",
        "",
        "| Case | Title | Result | Checks |",
        "| --- | --- | --- | --- |",
    ]
    for item in results:
        data = item.as_dict()
        lines.append(
            f"| {item.case_id} | {item.title} | **{item.status}** | "
            f"{data['checks_passed']}/{data['checks_total']} |"
        )

    for item in results:
        lines.extend(["", f"## {item.case_id} - {item.title}", ""])
        lines.append(f"**Requirement:** {item.requirement}")
        lines.append("")
        lines.append("### Input")
        lines.append("```json")
        lines.append(json.dumps(item.inputs, indent=2, default=str))
        lines.append("```")
        lines.append("")
        lines.append("### Expected")
        for entry in item.expected:
            lines.append(f"- {entry}")
        lines.append("")
        lines.append("### Actual")
        for entry in item.actual:
            lines.append(f"- {entry}")
        if item.agents_invoked:
            lines.extend(["", "### Agents invoked", ""])
            lines.append(", ".join(f"`{name}`" for name in item.agents_invoked))
        if item.sources:
            lines.extend(
                ["", "### References retrieved (RAG)", "", "| Document | Title | Score |", "| --- | --- | --- |"]
            )
            for row in item.sources:
                lines.append(f"| `{row['doc_key']}` | {row['title']} | {row['score']} |")
        if item.evidence:
            lines.extend(
                [
                    "",
                    "### Evidence ledger (sample)",
                    "",
                    "| Label | Value | Unit | Provenance | Source |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for row in item.evidence:
                lines.append(
                    f"| {row['label']} | {row['value']} | {row['unit'] or ''} | "
                    f"{row['kind']} | {row['source'] or ''} |"
                )
        lines.extend(["", "### Checks", ""])
        for check in item.checks:
            lines.append(
                f"- [{'x' if check['passed'] else ' '}] {check['check']}"
                + (f" -> `{check['detail']}`" if check["detail"] else "")
            )
        if item.notes:
            lines.extend(["", f"> {item.notes}"])

    (ARTIFACTS / "acceptance_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload
