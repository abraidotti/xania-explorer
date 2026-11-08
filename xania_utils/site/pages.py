"""Generated pages for one Xania target: overview, assessments with charts, catalogue, CSVs."""

from __future__ import annotations

from ..areafile.world import World
from ..assess import common as C
from ..assess import mobs as M
from ..assess import weapons as W
from ..gen import area_catalogue
from .stories import mobs_page, weapons_page
from .targets import Target

BAND_LABELS = [b.label for b in C.bands()]


# -- overview, catalogue, CSV -----------------------------------------------------
def overview_page(target: Target, world: World) -> str:
    p = target.paths
    commit = p.commit
    fatal = sum(x.fatal_in_cpp for x in world.problems)
    lines = [f"# {target.name}\n\n",
             C.table(["", ""], [
                 ["Checkout", f"`{p.root}`"],
                 ["Repository", f"[{p.web_url}]({p.web_url})" if p.web_url else "—"],
                 ["Branch", p.branch or "—"],
                 ["Commit", f"[`{commit[:10]}`]({p.web_url}/commit/{commit})" if commit and p.web_url
                  else (f"`{commit[:10]}`" if commit else "—")],
                 ["World", f"{len(world.areas)} areas, {len(world.rooms)} rooms, {len(world.mobs)} mobs, "
                           f"{len(world.objects)} objects"],
                 ["Load problems", f"{len(world.problems)} ({fatal} fatal in C++), "
                                   f"{len(world.diagnostics)} warnings, {len(world.unlisted_files)} unlisted files"],
             ]),
             "\n## Reports\n\n",
             "- [Weapons by level and class](weapons.md) — data: [weapons.csv](data/weapons.csv)\n",
             "- [Mobs by level](mobs.md) — data: [mobs.csv](data/mobs.csv)\n",
             "- [Area catalogue](areas.md) — every area, its mobs, objects, shops and load integrity\n"]
    if world.problems:
        lines.append("\n## Load problems\n\n")
        lines.append(C.table(["Kind", "Where", "Message"],
                             [[x.kind, f"{x.file}:{x.line}" if x.line else x.file, x.message]
                              for x in world.problems[:200]]))
    return "".join(lines)


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
    pages = {
        f"{t}/index.md": overview_page(target, world),
        f"{t}/weapons.md": weapons_page(world),
        f"{t}/mobs.md": mobs_page(world),
        f"{t}/areas.md": area_catalogue.render_index(world),
        f"{t}/data/weapons.csv": csv_text(W.write_csv, world),
        f"{t}/data/mobs.csv": csv_text(M.write_csv, world),
    }
    for area in world.areas:
        pages[f"{t}/areas/{area_catalogue.page_name(area)}"] = area_catalogue.render_area(world, area)
    return pages


__all__ = ["target_pages", "weapons_page", "mobs_page"]
