"""Narrative and explainability layer.

The whole system runs without an LLM: when ``OPENAI_API_KEY`` is absent the
module composes evidence-grounded narratives deterministically so that the UI,
the API and the PDF report always contain a readable explanation.  When a key
*is* configured the same prompt is sent to a chat-completions endpoint, and any
failure (network, auth, quota, refusal) silently degrades to the deterministic
narrative with a warning - a narrative is never allowed to break the workflow.

Hard rules enforced here:

* the model may only *phrase* conclusions that were computed by the services;
  it is never asked for numbers that were not supplied to it;
* the prompt forbids diagnostic language ("disease confirmed", "diagnosed");
* the returned ``source`` value states whether the text came from an LLM or
  from the deterministic composer.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import SourceKind
from app.schemas.common import Evidence, SourceReference

logger = get_logger(__name__)

DETERMINISTIC = SourceKind.DETERMINISTIC_NARRATIVE.value
LLM = SourceKind.LLM_NARRATIVE.value

SYSTEM_PROMPT = (
    "You are an agricultural advisory assistant writing one short paragraph for a farmer.\n"
    "HARD RULES:\n"
    "1. Use ONLY the facts, numbers and citations provided in the user message. Never invent a value.\n"
    "2. Do not diagnose. Describe conditions as 'environmental conditions favourable for X' and "
    "recommend scouting; never say a disease is confirmed or present.\n"
    "3. Never claim that irrigation or any other physical action has been carried out. The system only "
    "produces proposals that a human must authorise.\n"
    "4. If a number is missing, say it is not available. Never estimate silently.\n"
    "5. Mention the cited sources by title when you rely on them.\n"
    "6. Plain prose, no markdown, no bullet points, maximum 140 words."
)


def compose(
    *,
    context: dict[str, Any],
    evidence: list[Evidence] | list[dict],
    sources: list[SourceReference] | list[dict],
    instructions: str,
    fallback: str,
) -> dict[str, Any]:
    """Return ``{"narrative", "source", "model", "warnings"}`` for an agent step.

    ``fallback`` is the deterministic text produced by the calling service and
    is always used when no LLM is configured or when the call fails.
    """
    evidence_lines = [_evidence_line(item) for item in evidence or []]
    source_lines = [
        f"- {item.get('title', 'reference')} ({item.get('organisation') or 'source unknown'})"
        for item in (sources or [])
    ]

    result: dict[str, Any] = {
        "narrative": fallback,
        "source": DETERMINISTIC,
        "model": None,
        "warnings": [],
    }
    if not settings.llm_configured:
        result["warnings"].append("Narrative composed deterministically (no OPENAI_API_KEY configured).")
        return result

    prompt = _build_prompt(instructions=instructions, context=context, evidence=evidence_lines, sources=source_lines)
    try:
        text = _call_llm_sync(prompt)
    except Exception as exc:  # noqa: BLE001 - narrative must never break a run
        logger.warning("LLM narrative failed, using deterministic text: %s", exc)
        result["warnings"].append(f"LLM narrative unavailable ({type(exc).__name__}); deterministic text used.")
        return result

    cleaned = _clean(text)
    if len(cleaned) < 40:
        result["warnings"].append("LLM response too short or empty; deterministic text used.")
        return result

    result.update({"narrative": cleaned, "source": LLM, "model": settings.llm_model})
    return result


def _build_prompt(*, instructions: str, context: dict, evidence: list[str], sources: list[str]) -> str:
    parts = [
        f"TASK: {instructions}",
        "",
        "COMPUTED FACTS (already determined by the analysis services - phrase them, do not recompute):",
    ]
    for key, value in context.items():
        parts.append(f"- {key}: {value}")
    parts.extend(["", "EVIDENCE:"])
    parts.extend(f"- {line}" for line in (evidence or ["(none available)"]))
    parts.extend(["", "SOURCES:"])
    parts.extend(f"- {line}" for line in (sources or ["(no reference material retrieved)"]))
    parts.extend(["", "Write the paragraph now."])
    return "\n".join(parts)


def _evidence_line(item: Evidence | dict) -> str:
    data = item.model_dump() if isinstance(item, Evidence) else dict(item)
    value = data.get("value")
    unit = f" {data['unit']}" if data.get("unit") else ""
    rendered = "not available" if value is None else f"{value}{unit}"
    kind = data.get("kind", "measured")
    source = data.get("source") or "unknown source"
    note = f" ({data['note']})" if data.get("note") else ""
    return f"{data.get('label', 'fact')} = {rendered} [{kind}, source: {source}]{note}"


def _call_llm_sync(prompt: str) -> str:
    """Blocking chat-completions call, executed on a worker thread."""
    return asyncio.run(_call_llm(prompt))


async def _call_llm(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "temperature": 0.2,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    timeout = httpx.Timeout(settings.llm_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
    choices = body.get("choices") or []
    if not choices:
        msg = "LLM returned no choices"
        raise ValueError(msg)
    return str(choices[0].get("message", {}).get("content") or "")


def _clean(text: str) -> str:
    cleaned = " ".join(str(text).replace("\r", " ").split())
    for marker in ("**", "##", "- "):
        cleaned = cleaned.replace(marker, "")
    return cleaned.strip()
