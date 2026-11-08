"""Vega-Lite chart specs embedded in generated Markdown pages.

Each chart is a self-contained Vega-Lite v5 spec with its data inlined. The
page embeds it as a JSON <script> that docs/javascripts/xania.js renders with
vega-embed, so charts are interactive (tooltips, zoom where enabled, export).
"""

from __future__ import annotations

import json
from typing import Any

SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"
CLASS_COLOURS = {"mage": "#4e79a7", "cleric": "#f28e2b", "knight": "#59a14f", "barbarian": "#e15759",
                 "any type": "#9c755f", "cap": "#888888"}


def spec(data: list[dict[str, Any]], *, title: str, height: int = 300, **body: Any) -> dict[str, Any]:
    return {
        "$schema": SCHEMA,
        "title": {"text": title, "anchor": "start"},
        "width": "container",
        "height": height,
        "data": {"values": data},
        "background": "transparent",
        "config": {"view": {"stroke": None}, "axis": {"labelFontSize": 11, "titleFontSize": 12},
                   "legend": {"orient": "bottom"}},
        **body,
    }


def embed(chart: dict[str, Any]) -> str:
    """Markdown-safe HTML block that xania.js turns into a chart."""
    payload = json.dumps(chart, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return f'\n<div class="xu-chart"><script type="application/json">{payload}</script></div>\n\n'


def ordinal(field: str, title: str, order: list[str] | None = None) -> dict[str, Any]:
    enc = {"field": field, "type": "ordinal", "title": title}
    if order is not None:
        enc["sort"] = order
    return enc


def quant(field: str, title: str, **extra: Any) -> dict[str, Any]:
    return {"field": field, "type": "quantitative", "title": title, **extra}


def nominal(field: str, title: str, colours: dict[str, str] | None = None, order: list[str] | None = None,
            ) -> dict[str, Any]:
    enc: dict[str, Any] = {"field": field, "type": "nominal", "title": title}
    if colours:
        domain = order or list(colours)
        enc["scale"] = {"domain": domain, "range": [colours.get(d, "#bab0ac") for d in domain]}
    elif order:
        enc["scale"] = {"domain": order}
    return enc


def tooltip(*fields: tuple[str, str]) -> list[dict[str, str]]:
    return [{"field": f, "title": t} for f, t in fields]


def insert_after_heading(markdown: str, heading_prefix: str, html: str) -> str:
    """Insert ``html`` after the paragraph that follows the heading starting with ``heading_prefix``."""
    lines = markdown.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(heading_prefix):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            while j < len(lines) and lines[j].strip() and not lines[j].startswith(("|", "#", "```", "-")):
                j += 1
            lines.insert(j, html)
            return "\n".join(lines)
    return markdown + html


def strip_text_histograms(markdown: str) -> str:
    """Remove the fenced █-bar histograms (the site shows real charts instead)."""
    out, skipping, block = [], False, []
    for line in markdown.split("\n"):
        if line.startswith("```"):
            if skipping:
                if not any("│" in b for b in block):
                    out += ["```", *block, line]
                skipping, block = False, []
                continue
            skipping = True
            continue
        (block if skipping else out).append(line)
    return "\n".join(out)
