"""Recommendations: every change the assessments propose, ranked by impact × effort.

Read-only and stateless: each build regenerates the list from the data, so a recommendation disappears once a
version no longer triggers it. Nothing is stored or tracked. Each recommendation is produced next to the finding
it addresses (see ``site/stories``), with its expected effect computed from the same analysis.
"""

from __future__ import annotations

from ..areafile.world import World
from ..findings import EFFORT_NAME, KIND_NAME, Finding, Recommendation
from ..systems import SYSTEMS, System
from . import charts as V

IMPACT_NAME = {3: "high", 2: "medium", 1: "minor"}
EFFORT_SECTIONS = [(1, "Quick wins", "A handful of edits or one constant."),
                   (2, "Worth planning", "Many area files, or one C++ formula or table."),
                   (3, "Projects", "New content or a new mechanic.")]


def collect(world: World) -> list[tuple[System, Finding, Recommendation]]:
    """Every recommendation for this version, best first: score, then impact, then reading order."""
    order = {s.slug: i for i, s in enumerate(SYSTEMS)}
    found = [(s, f, r) for s in SYSTEMS for f in s.story(world).findings for r in f.recommendations]
    return sorted(found, key=lambda x: (-x[2].score, -x[2].impact, x[2].effort, order[x[0].slug]))


def chips(system: System, r: Recommendation) -> str:
    return (f'<span class="xe-chip">{system.title}</span>'
            f'<span class="xe-chip xe-chip-impact">{IMPACT_NAME[r.impact]} impact</span>'
            f'<span class="xe-chip xe-effort-{r.effort}">{EFFORT_NAME[r.effort]} effort</span>'
            f'<span class="xe-chip">{KIND_NAME[r.kind]}</span>')


def page(world: World) -> str:
    recs = collect(world)
    missing = [s.title for s in SYSTEMS if s.story(world).status != "ok"]
    out = ["# Recommendations\n\n",
           "Changes that would address the balance issues and bugs found in this version, ranked by impact × "
           "effort: high impact for little work first. Each states what to change and where, and its expected "
           "effect, computed from the same data as the finding it links to. The list is regenerated on every "
           "build, so a recommendation disappears once a version no longer needs it.\n"]
    if missing:
        out.append(f"\n!!! warning \"Incomplete\"\n\n    {', '.join(missing)} couldn't run on this checkout, so "
                   "their recommendations are missing.\n")
    if not recs:
        return "".join(out) + "\nNothing to recommend: no finding in this version calls for a change.\n"
    quick = [r for _, _, r in recs if r.effort == 1 and r.impact >= 2]
    out.append(V.stat_tiles([
        (str(len(recs)), "recommendations"),
        (str(len(quick)), "quick wins with medium or high impact"),
        (" / ".join(str(sum(r.kind == k for _, _, r in recs)) for k in KIND_NAME),
         " / ".join(KIND_NAME.values())),
    ]))
    out.append(_matrix(recs))
    out.append("\n## Ranking {#ranking}\n\n| # | Recommendation | System | Impact | Effort |\n|---|---|---|---|---|\n")
    for i, (s, _, r) in enumerate(recs, 1):
        out.append(f"| {i} | [{r.title}](#{r.anchor}) | {s.title} | {IMPACT_NAME[r.impact]} | "
                   f"{EFFORT_NAME[r.effort]} |\n")
    for effort, title, blurb in EFFORT_SECTIONS:
        group = [(s, f, r) for s, f, r in recs if r.effort == effort]
        if not group:
            continue
        out.append(f"\n## {title} {{#effort-{effort}}}\n\n{blurb}\n")
        for s, f, r in group:
            out.append(f"\n### {r.title} {{#{r.anchor}}}\n\n{chips(s, r)}\n\n**Change.** {r.change}\n\n"
                       f"**Expected effect.** {r.effect}\n\n"
                       f"**Evidence.** [{f.title}]({s.slug}.md#{f.anchor})\n")
    return "".join(out)


def _matrix(recs) -> str:
    cells = [{"impact": IMPACT_NAME[i], "effort": EFFORT_NAME[e],
              "count": sum(1 for _, _, r in recs if r.impact == i and r.effort == e)}
             for i in (3, 2, 1) for e in (1, 2, 3)]
    chart = V.heatmap(cells, x="effort", y="impact", value="count", title="Recommendations by impact and effort",
                      x_order=[EFFORT_NAME[e] for e in (1, 2, 3)], y_order=[IMPACT_NAME[i] for i in (3, 2, 1)],
                      value_title="Recommendations", fmt="d")
    return V.embed(chart)


def top(world: World, n: int = 5) -> list[tuple[System, Finding, Recommendation]]:
    return collect(world)[:n]
