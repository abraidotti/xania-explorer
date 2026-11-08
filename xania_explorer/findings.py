"""Structured findings: the unit every system page, dashboard and comparison is built from.

A system's story is a title, an intro, key-number tiles, a list of findings and a method. Each finding
has a stable id (used for its page anchor, the dashboards and the comparison scorecard), a generated
title sentence, a headline metric with a direction ("lower is better" …), and an impact rating:

- impact 3: affects most players across a wide stretch of levels (e.g. the XP supply collapsing)
- impact 2: affects a class, a long level range or a core rule (e.g. a class's 23-level weapon wait)
- impact 1: localised or cosmetic (e.g. a handful of rich mobs, a few unreachable rooms)
- issue=False: a description of how the game works rather than a problem (e.g. "kills per level are steady")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Finding:
    id: str  # "<system>.<name>", stable across builds and deployments
    title: str  # the generated heading sentence
    body: str  # Markdown: evidence paragraph, chart embed, details blocks
    metric: float | None = None  # headline number behind the finding
    metric_label: str = ""  # what the number is, e.g. "levels without an upgrade"
    better: str = "lower"  # "lower" | "higher" | "none": which direction is an improvement
    impact: int = 1  # 1–3, see module docstring
    issue: bool = True  # False = descriptive, not a balance problem
    summary: str = ""  # one sentence for dashboard cards; defaults to the body's first sentence

    @property
    def system(self) -> str:
        return self.id.split(".", 1)[0]

    @property
    def anchor(self) -> str:
        return self.id.replace(".", "-")

    @property
    def card_summary(self) -> str:
        return self.summary or first_sentence(self.body)

    def markdown(self) -> str:
        return f"\n## {self.title} {{#{self.anchor}}}\n\n{self.body.lstrip()}"


@dataclass
class Story:
    slug: str
    title: str
    intro: str
    tiles: str  # rendered stat tiles (charts.stat_tiles)
    findings: list[Finding] = field(default_factory=list)
    method: str = ""  # rendered method block
    preamble: str = ""  # optional extra block after the intro (e.g. a warning)

    def markdown(self) -> str:
        out = [f"# {self.title}\n\n", self.intro.rstrip() + "\n", self.preamble, self.tiles]
        out += [f.markdown() for f in self.findings]
        if self.method:
            out.append("\n## Method {#method}\n" + self.method)
        return "".join(out)

    @property
    def issues(self) -> list[Finding]:
        return sorted((f for f in self.findings if f.issue), key=lambda f: -f.impact)


_TAG = re.compile(r"<[^>]+>|`|\*\*|\*")


def first_sentence(markdown: str) -> str:
    """The first sentence of a finding's prose (charts, details and markup stripped)."""
    para = next((p for p in markdown.strip().split("\n\n") if p and not p.lstrip().startswith(("<", "???", "|", "!!!"))),
                "")
    text = _TAG.sub("", para).replace("\n", " ").strip()
    m = re.search(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text)[:300]


def fmt_metric(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".") if abs(value) < 10 else f"{value:.1f}".rstrip("0").rstrip(".")


def verdict(base: float | None, other: float | None, better: str) -> str:
    """'improved' | 'worse' | 'same' | 'n/a' for a metric moving from base to other."""
    if base is None or other is None or better == "none":
        return "n/a"
    if abs(other - base) < 1e-9:
        return "same"
    up = other > base
    return "improved" if (up and better == "higher") or (not up and better == "lower") else "worse"
