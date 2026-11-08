"""Generated pages for one Xania target: overview, one page per game system, catalogue, CSVs."""

from __future__ import annotations

from ..areafile.world import World
from ..assess import common as C
from ..gen import area_catalogue
from ..systems import SYSTEMS
from .targets import Target

BAND_LABELS = [b.label for b in C.bands()]


def overview_page(target: Target, world: World, explore_link: bool = True) -> str:
    from . import charts as V
    from .dashboard import deployment_dashboard, issue_counts

    p = target.paths
    commit = p.commit
    fatal = sum(x.fatal_in_cpp for x in world.problems)
    counts = issue_counts(world)
    lines = [f"# {target.label}\n\n",
             "A dashboard of this Xania version: its most pressing balance issues first, each linking to the "
             "evidence, then every system.\n",
             V.stat_tiles([
                 (str(counts[3]), "high-impact balance issues"),
                 (str(counts[2]), "medium-impact issues"),
                 (str(counts[1]), "minor issues"),
                 (str(len(world.problems)), "load problems"),
             ]),
             _explore_link(target) if explore_link else "",
             deployment_dashboard(world),
             "\n## This version {#this-version}\n\n",
             C.table(["", ""], [
                 ["Checkout", "downloaded from GitHub by the explorer" if p.metadata else f"`{p.root}`"],
                 ["Repository", f"[{p.web_url}]({p.web_url})" if p.web_url else "—"],
                 ["Branch", p.branch or "—"],
                 ["Commit", f"[`{commit[:10]}`]({p.web_url}/commit/{commit})" if commit and p.web_url
                  else (f"`{commit[:10]}`" if commit else "—")],
                 ["World", f"{len(world.areas)} areas, {len(world.rooms)} rooms, {len(world.mobs)} mobs, "
                           f"{len(world.objects)} objects"],
                 ["Load problems", f"{len(world.problems)} ({fatal} fatal in C++), "
                                   f"{len(world.diagnostics)} warnings, {len(world.unlisted_files)} unlisted files"],
             ]),
             "\n**Data downloads:** "
             + " · ".join(f"[{s.slug}.csv](data/{s.slug}.csv)" for s in SYSTEMS if s.available(world))
             + ". Also: the [area catalogue](areas.md), with every area's mobs, objects, shops and load integrity.\n"]
    if world.problems:
        lines.append("\n## Load problems\n\n")
        lines.append(C.table(["Kind", "Where", "Message"],
                             [[x.kind, f"{x.file}:{x.line}" if x.line else x.file, x.message]
                              for x in world.problems[:200]]))
    return "".join(lines)


def _explore_link(target: Target) -> str:
    """A prefilled link into the live explorer, so this version can be compared with any repo or branch."""
    from urllib.parse import quote

    p = target.paths
    if not p.repo_slug:
        return ""
    base = quote(f"{p.repo_slug}@{p.branch}" if p.branch and p.branch != "HEAD" else p.repo_slug, safe="/@")
    return (f'\n<p class="xu-explore-link">Compare this version with another repo or branch: '
            f'<a href="../explore/?base={base}">open it in the explorer</a>.</p>\n')


def csv_text(writer, world: World) -> str:
    """Run an assessment's write_csv into a string (it expects a path)."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "out.csv"
        writer(world, path)
        return path.read_text(encoding="utf-8")


def target_pages(target: Target, world: World) -> dict[str, str]:
    """All generated files for one target, keyed by path relative to docs/."""
    t = target.name
    pages = {f"{t}/index.md": overview_page(target, world), f"{t}/areas.md": area_catalogue.render_index(world)}
    for s in SYSTEMS:
        pages[f"{t}/{s.slug}.md"] = s.page(world)
        if s.available(world):
            pages[f"{t}/data/{s.slug}.csv"] = csv_text(s.assessment.write_csv, world)
    for area in world.areas:
        pages[f"{t}/areas/{area_catalogue.page_name(area)}"] = area_catalogue.render_area(world, area)
    return pages


__all__ = ["target_pages", "overview_page", "BAND_LABELS"]
