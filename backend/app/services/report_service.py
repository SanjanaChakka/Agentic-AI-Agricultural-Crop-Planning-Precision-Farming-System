"""PDF report generation (ReportLab).

The report is the farmer-facing artefact of a workflow run.  Its structure is
fixed and auditable:

1. Header with farm, field, crop, run id and generation timestamp
2. Executive summary and human-approval state
3. Measured soil values (clearly separated from interpretation)
4. Soil & nutrient interpretation
5. Weather and climate (with an explicit SIMULATED banner when applicable)
6. Crop suitability factor-by-factor table
7. Irrigation assessment (rules evaluated)
8. Environmental risk findings (favourability wording, never a diagnosis)
9. Machine-learning model output and documented metrics
10. Activity plan and alerts
11. Evidence ledger with provenance tags
12. Reference list and the mandatory limitations statement
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as canvas_module
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.common import Evidence, SourceReference

logger = get_logger(__name__)

Canvas = canvas_module.Canvas


@dataclass(frozen=True)
class RenderedReport:
    """What ``build_report_pdf`` produced, so the caller can persist real facts."""

    path: Path
    page_count: int
    size_bytes: int


BRAND = colors.HexColor("#1f6f43")
ACCENT = colors.HexColor("#e8f3ec")
GREY = colors.HexColor("#5b6b61")
WARN = colors.HexColor("#8a4b08")

LIMITATIONS = [
    "This report is decision support, not an agronomic prescription, and it never "
    "names any crop disease, pest or nutrient disorder.",
    "Every risk statement describes environmental conditions only. Confirmation requires field scouting "
    "and, where necessary, laboratory testing.",
    "Approving a plan in this system authorises documentation only. The system never actuates irrigation "
    "or any other physical equipment.",
    "Values are reported at the precision they were measured. Where a value was imputed by a model this "
    "is stated explicitly.",
    "Simulated or fallback data is labelled as such throughout and must not be treated as an observation.",
]


def build_report_pdf(
    *,
    destination: Path,
    title: str,
    context: dict[str, Any],
    sections: list[dict[str, Any]],
    references: Iterable[SourceReference | dict] | None = None,
) -> RenderedReport:
    """Render the report to ``destination`` and report what was actually written."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()

    doc = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="Agentic AI Agricultural Crop Planning & Precision Farming System",
        subject="Precision farming advisory report",
    )

    story: list[Any] = []
    story.extend(_header(title, context, styles))
    for section in sections:
        if section.get("page_break_before"):
            story.append(PageBreak())
        story.extend(_section(section, styles))
    story.append(PageBreak())
    story.extend(_references_block(references or [], styles))
    story.extend(_limitations_block(styles))

    pages = {"count": 0}

    def _page_number(canvas, document) -> None:  # noqa: ANN001 - reportlab callback
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(18 * mm, 10 * mm, "Agentic AI Precision Farming System - decision support only")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    class _CountingCanvas(Canvas):
        """Canvas that remembers how many pages were actually emitted."""

        def showPage(self) -> None:  # noqa: N802 - reportlab API
            pages["count"] += 1
            super().showPage()

    doc.build(
        story,
        onFirstPage=_page_number,
        onLaterPages=_page_number,
        canvasmaker=_CountingCanvas,
    )
    logger.info("Report written to %s (%s pages)", destination, pages["count"])
    return RenderedReport(path=destination, page_count=pages["count"], size_bytes=destination.stat().st_size)


# ----------------------------------------------------------------------
# rendering helpers
# ----------------------------------------------------------------------
def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "AgriTitle",
            parent=base["Title"],
            fontSize=17,
            leading=21,
            textColor=BRAND,
            alignment=TA_CENTER,
            spaceAfter=2 * mm,
        ),
        "subtitle": ParagraphStyle(
            "AgriSubtitle", parent=base["Normal"], fontSize=9.5, leading=13, textColor=GREY, alignment=TA_CENTER
        ),
        "h1": ParagraphStyle(
            "AgriH1",
            parent=base["Heading1"],
            fontSize=13,
            leading=16,
            textColor=BRAND,
            spaceBefore=5 * mm,
            spaceAfter=2 * mm,
        ),
        "h2": ParagraphStyle(
            "AgriH2",
            parent=base["Heading2"],
            fontSize=10.5,
            leading=13,
            textColor=BRAND,
            spaceBefore=3 * mm,
            spaceAfter=1 * mm,
        ),
        "body": ParagraphStyle("AgriBody", parent=base["BodyText"], fontSize=9, leading=12.5, spaceAfter=1.5 * mm),
        "small": ParagraphStyle("AgriSmall", parent=base["BodyText"], fontSize=7.8, leading=10, textColor=GREY),
        "warn": ParagraphStyle(
            "AgriWarn", parent=base["BodyText"], fontSize=9, leading=12, textColor=WARN, spaceAfter=2 * mm
        ),
    }


def _header(title: str, context: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    generated = context.get("generated_at") or datetime.now(UTC).isoformat(timespec="seconds")
    rows = [
        ["Farm", str(context.get("farm_name", "-"))],
        ["Field", f"{context.get('field_name', '-')} ({context.get('field_code', '-')})"],
        ["Crop", str(context.get("crop", "-"))],
        ["Area / soil", f"{context.get('area_ha', '-')} ha / {context.get('soil_type', '-')}"],
        [
            "Location",
            f"{context.get('location_name', '-')} ({context.get('latitude', '-')}, {context.get('longitude', '-')})",
        ],
        ["Workflow run", f"#{context.get('workflow_run_id', '-')} ({context.get('status', '-')})"],
        ["Agents invoked", ", ".join(context.get("agents_invoked", []) or []) or "-"],
        [
            "Weather source",
            f"{context.get('weather_source', 'not fetched')} (simulated: {context.get('weather_simulated', 'n/a')})",
        ],
        ["Generated at (UTC)", str(generated)],
    ]
    table = _table(rows, [38 * mm, None], styles)
    return [
        Paragraph(title, styles["title"]),
        Paragraph(
            "Decision-support report - every value below is traceable to the evidence ledger", styles["subtitle"]
        ),
        Spacer(1, 4 * mm),
        table,
        Spacer(1, 3 * mm),
    ]


def _section(section: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    flow: list[Any] = [Paragraph(str(section.get("title", "")), styles["h1"])]

    if section.get("banner"):
        flow.append(Paragraph(str(section["banner"]), styles["warn"]))

    for block in section.get("blocks", []):
        kind = block.get("kind", "paragraph")
        if kind == "paragraph":
            flow.append(Paragraph(str(block.get("text", "")), styles["body"]))
        elif kind == "h2":
            flow.append(Paragraph(str(block.get("text", "")), styles["h2"]))
        elif kind == "bullets":
            items = [str(item) for item in block.get("items", [])]
            if items:
                flow.append(_bullets(items, styles))
        elif kind == "table":
            rows = block.get("rows") or []
            if rows:
                flow.append(_table(rows, block.get("widths"), styles, header=bool(block.get("header"))))
        elif kind == "callout":
            flow.append(_callout(str(block.get("text", "")), styles))
        elif kind == "spacer":
            flow.append(Spacer(1, 2 * mm))

    flow.append(Spacer(1, 1 * mm))
    return flow


def _table(
    rows: list[list[Any]],
    widths: list[float | None] | None,
    styles: dict[str, ParagraphStyle],
    *,
    header: bool = False,
) -> Table:
    cell_style = ParagraphStyle(
        "AgriCell", parent=styles["body"], fontSize=8.2, leading=10.5, spaceAfter=0, spaceBefore=0
    )
    data = [[Paragraph(_cell(value), cell_style) for value in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands: list[tuple] = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c3d6c9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]
        for index in range(1, len(data)):
            if index % 2 == 0:
                commands.append(("BACKGROUND", (0, index), (-1, index), ACCENT))
    table.setStyle(TableStyle(commands))
    return table


def _bullets(items: list[str], styles: dict[str, ParagraphStyle]) -> Any:
    return KeepTogether(
        Table(
            [[Paragraph(f"&bull;&nbsp;&nbsp;{_cell(item)}", styles["body"])] for item in items],
            colWidths=[170 * mm],
            hAlign="LEFT",
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            ),
        )
    )


def _callout(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    inner = Paragraph(text, styles["body"])
    box = Table([[inner]], colWidths=[170 * mm], hAlign="LEFT")
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
                ("BOX", (0, 0), (-1, -1), 0.6, BRAND),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return box


def _references_block(references: Iterable[Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    flow: list[Any] = [Paragraph("References", styles["h1"])]
    items: list[str] = []
    for reference in references:
        data = reference if isinstance(reference, dict) else reference.model_dump()
        label = data.get("title") or data.get("doc_key", "reference")
        org = data.get("organisation") or "organisation not recorded"
        url = data.get("url") or data.get("source_url")
        score = data.get("score")
        line = f"{label} - {org} ({data.get('doc_key', '')})"
        if url:
            line += f" - {url}"
        if score is not None:
            line += f" [retrieval score {score}]"
        items.append(line)
    flow.append(_bullets(items or ["No reference material was retrieved for this report."], styles))
    return flow


def _limitations_block(styles: dict[str, ParagraphStyle]) -> list[Any]:
    return [
        Spacer(1, 3 * mm),
        Paragraph("Limitations and safety statement", styles["h1"]),
        _bullets(LIMITATIONS, styles),
    ]


def _cell(value: Any) -> str:
    text = "not available" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


# ----------------------------------------------------------------------
# small utilities reused by the report router
# ----------------------------------------------------------------------
def evidence_line(item: Evidence | dict) -> str:
    data = item.model_dump() if isinstance(item, Evidence) else dict(item)
    value = data.get("value")
    unit = f" {data['unit']}" if data.get("unit") else ""
    rendered = "not available" if value is None else f"{value}{unit}"
    return f"{data.get('label', 'fact')}: {rendered} [{data.get('kind', 'measured')}]"


def unique_file_name(base: str, suffix: str = ".pdf") -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha1(base.encode("utf-8"), usedforsecurity=False).hexdigest()[:6]
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in base).strip("-")
    return f"{safe[:48]}-{stamp}-{digest}{suffix}"


def reports_root() -> Path:
    root = Path(settings.reports_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root
