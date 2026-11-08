"""Bugs: defects in Xania's code, area data and content (see xania_explorer/bugs)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..areafile.world import World
from ..bugs import KINDS, OPEN, SEVERITIES, SEVERITY_LABEL, BugResult, run_checks
from . import common as C


class BugAnalysis:
    def __init__(self, world: World):
        self.world = world
        self.results = run_checks(world)

    @property
    def open(self) -> list[BugResult]:
        return [r for r in self.results if r.open]

    def by(self, kind: str | None = None, severity: str | None = None, open_only: bool = True) -> list[BugResult]:
        return [r for r in (self.open if open_only else self.results)
                if (kind is None or r.check.kind == kind) and (severity is None or r.check.severity == severity)]

    @property
    def occurrences(self) -> int:
        return sum(len(r.detection.occurrences) for r in self.open)

    def area_counts(self) -> Counter:
        return Counter((o.area, r.check.id) for r in self.open for o in r.detection.occurrences if o.area)

    def summary_table(self) -> str:
        return C.table(["Check", "Kind", "Severity", "Status", "Occurrences"],
                       [[r.check.title, r.check.kind, SEVERITY_LABEL[r.check.severity], r.status,
                         len(r.detection.occurrences)] for r in self.results])

    def occurrence_table(self, r: BugResult, link=None) -> str:
        def where(o):
            if link and o.file and o.line:
                return f"[{o.where}]({link(o.file, o.line)})"
            return o.where

        return C.table(["Where", "Area", "Detail"], [[where(o), o.area or "—", o.detail] for o in r.detection.occurrences])

    def method(self) -> str:
        return ("- **Code checks** search the C++ source for a specific faulty pattern, each verified by reading the "
                "code. A branch that fixes the code shows the check as *fixed*. Checks whose faulty code only "
                "crashes on bad data are *latent* until some data triggers them.\n"
                "- **Data checks** use the area parser's load-integrity results, which mirror what the C++ loader "
                "rejects (fatal) or logs.\n"
                "- **Content checks** reuse the other systems: items no reset places (objects the C++ creates "
                "itself, like corpses and the Mud School kit, are excluded), mobs that never spawn, rooms with no "
                "walking route from recall, and area files that aren't loaded.\n"
                f"- **Severity**: {', '.join(SEVERITY_LABEL[s] for s in SEVERITIES)}. Kinds: {', '.join(KINDS)}.\n"
                f"- Statuses counted as open: {', '.join(sorted(OPEN))}.\n")


def analyse(world: World) -> BugAnalysis:
    return C.cached(world, "bugs-analysis", BugAnalysis)


def render(world: World) -> str:
    a = analyse(world)
    out = [C.GENERATED_NOTE, "\n# Bugs\n\n", "## Headline findings\n\n",
           f"- **Open**: {len(a.open)} of {len(a.results)} checks ({a.occurrences} occurrences).\n",
           f"- **Crash risks**: {len(a.by(severity='crash'))}.\n",
           "\n## Method\n\n" + a.method(), "\n## Checks\n\n" + a.summary_table()]
    for r in a.results:
        out.append(f"\n## {r.check.title}\n\n*{r.check.kind}, {SEVERITY_LABEL[r.check.severity]}, {r.status}*\n\n"
                   f"{r.check.explain}\n\n**Fix:** {r.check.remedy}\n")
        if r.detection.occurrences:
            out.append("\n" + a.occurrence_table(r))
    return "".join(out)


def write_csv(world: World, path: Path) -> None:
    a = analyse(world)
    rows = [[r.check.id, r.check.kind, r.check.severity, r.status, o.where, o.area, o.file, o.line, o.detail]
            for r in a.results for o in (r.detection.occurrences or [None]) if o] + \
           [[r.check.id, r.check.kind, r.check.severity, r.status, "", "", "", "", ""]
            for r in a.results if not r.detection.occurrences]
    C.write_csv(path, ["check", "kind", "severity", "status", "where", "area", "file", "line", "detail"], rows)
