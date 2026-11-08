"""Generated pages for one Xania target: overview, assessments with charts, catalogue, CSVs."""

from __future__ import annotations

from collections import Counter

from ..areafile.world import World
from ..assess import common as C
from ..assess import mobs as M
from ..assess import weapons as W
from ..gen import area_catalogue
from . import charts as V
from .targets import Target

BAND_LABELS = [b.label for b in C.bands()]


# -- weapons ------------------------------------------------------------------
def weapon_charts(world: World) -> dict[str, dict]:
    got = [w for w in W.collect(world) if w.obtainable and w.level <= C.HERO_LEVEL]
    profiles = W.class_profiles(world.src_dir)
    bands = C.bands()
    out = {}

    supply = [{"band": b.label, "type": t, "count": n}
              for b in bands for t, n in Counter(w.type for w in got if w.level in b).items()]
    out["## 1."] = V.spec(supply, title="New obtainable weapons per level band, by type", mark="bar",
                          encoding={"x": V.ordinal("band", "Levels", BAND_LABELS),
                                    "y": V.quant("count", "Weapons", stack=True),
                                    "color": V.nominal("type", "Type", order=W.ALL_TYPES),
                                    "tooltip": V.tooltip(("band", "Levels"), ("type", "Type"), ("count", "Weapons"))})

    access = [{"band": b.label, "class": p.name, "view": view, "count": sum(w.type in types for w in got if w.level in b)}
              for b in bands for p in profiles for view, types in (("start", p.starting), ("easy", p.easy))]
    out["## 2."] = V.spec(access, title="New weapons per band in each class's types (solid = start, dashed = easy)",
                          mark={"type": "line", "point": True},
                          encoding={"x": V.ordinal("band", "Levels", BAND_LABELS),
                                    "y": V.quant("count", "Weapons"),
                                    "color": V.nominal("class", "Class", V.CLASS_COLOURS, [p.name for p in profiles]),
                                    "strokeDash": {"field": "view", "type": "nominal", "title": "View",
                                                   "scale": {"domain": ["start", "easy"], "range": [[1, 0], [5, 3]]},
                                                   "legend": {"symbolType": "stroke", "symbolStrokeWidth": 2}},
                                    "tooltip": V.tooltip(("band", "Levels"), ("class", "Class"), ("view", "View"),
                                                         ("count", "Weapons"))})

    series = {"any type": W.best_by_level(got, set(W.SKILLED_TYPES))}
    series.update({p.name: W.best_by_level(got, set(p.starting)) for p in profiles})
    curve = [{"level": lvl, "series": name, "avg": v} for name, s in series.items() for lvl, v in s.items()
             if v is not None]
    curve += [{"level": lvl, "series": "cap", "avg": W.allowed_average(lvl, False)} for lvl in C.LEVELS]
    out["## 3."] = V.spec(curve, title="Best usable weapon (average damage) at each level, starting types",
                          mark={"type": "line", "interpolate": "step-after"},
                          encoding={"x": V.quant("level", "Character level", scale={"domain": [1, C.HERO_LEVEL]}),
                                    "y": V.quant("avg", "Average damage"),
                                    "color": V.nominal("series", "Series", V.CLASS_COLOURS,
                                                       ["any type"] + [p.name for p in profiles] + ["cap"]),
                                    "strokeDash": {"condition": {"test": "datum.series === 'cap'", "value": [4, 4]},
                                                   "value": [1, 0]},
                                    "tooltip": V.tooltip(("series", "Series"), ("level", "Level"), ("avg", "Avg"))})

    points = [{"level": w.level, "avg": w.average, "name": w.obj.short_descr, "type": w.type,
               "area": world.obj_area[w.vnum].name, "vnum": w.vnum, "over": "over cap" if w.over_cap else "ok",
               "sources": ", ".join(w.source_kinds)} for w in got]
    cap = [{"level": lvl, "cap": W.allowed_average(lvl, False)} for lvl in C.LEVELS]
    out["## 6."] = {**V.spec([], title="Every obtainable weapon: level vs average damage (dashed = cap)"),
                    "data": {"values": points},
                    "layer": [
                        {"mark": {"type": "point", "filled": True, "opacity": 0.7},
                         "params": [{"name": "zoom", "select": "interval", "bind": "scales"}],
                         "encoding": {"x": V.quant("level", "Weapon level"), "y": V.quant("avg", "Average damage"),
                                      "color": V.nominal("type", "Type", order=W.ALL_TYPES),
                                      "shape": V.nominal("over", "Cap"),
                                      "tooltip": V.tooltip(("name", "Weapon"), ("vnum", "Vnum"), ("area", "Area"),
                                                           ("type", "Type"), ("level", "Level"), ("avg", "Avg"),
                                                           ("sources", "Sources"))}},
                        {"data": {"values": cap}, "mark": {"type": "line", "strokeDash": [4, 4], "color": "#9a8b7e"},
                         "encoding": {"x": {"field": "level", "type": "quantitative"},
                                      "y": {"field": "cap", "type": "quantitative"}}},
                    ]}
    return out


# -- mobs -----------------------------------------------------------------------
def mob_charts(world: World) -> dict[str, dict]:
    combat = [i for i in M.collect(world) if i.category == "combat"]
    out = {}
    per_band = [{"band": b.label, "population": sum(i.population for i in combat if i.level in b),
                 "prototypes": sum(1 for i in combat if i.level in b)} for b in C.bands()]
    out["## 1."] = V.spec(per_band, title="Combat mob population per level band", mark="bar",
                          encoding={"x": V.ordinal("band", "Levels", BAND_LABELS),
                                    "y": V.quant("population", "Instances after a full reset"),
                                    "tooltip": V.tooltip(("band", "Levels"), ("population", "Population"),
                                                         ("prototypes", "Prototypes"))})
    per_level = [{"level": lvl, "population": sum(i.population for i in combat if i.level == lvl),
                  "prototypes": sum(1 for i in combat if i.level == lvl)} for lvl in C.LEVELS]
    out["## 2."] = V.spec(per_level, title="Combat mob population at every level", mark="bar",
                          encoding={"x": {**V.ordinal("level", "Level"),
                                          "axis": {"values": [1] + list(range(5, C.HERO_LEVEL + 1, 5)) + [91],
                                                   "labelAngle": 0}},
                                    "y": V.quant("population", "Instances"),
                                    "tooltip": V.tooltip(("level", "Level"), ("population", "Population"),
                                                         ("prototypes", "Prototypes"))})
    points = [{"level": i.level, "hp": max(i.mob.hit.average, 1), "dmg": i.mob.damage.average,
               "name": i.mob.short_descr, "area": i.area.name, "vnum": i.mob.vnum, "pop": i.population,
               "kind": "aggressive" if i.aggressive else "passive"} for i in combat]
    out["## 3."] = V.spec(points, title="Every combat mob: level vs average HP (log scale; drag to zoom)",
                          height=380, mark={"type": "point", "filled": True, "opacity": 0.6},
                          params=[{"name": "zoom", "select": "interval", "bind": "scales"}],
                          encoding={"x": V.quant("level", "Mob level",
                                                 scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                                    "y": V.quant("hp", "Average HP", scale={"type": "log"}),
                                    "color": V.nominal("kind", "Behaviour",
                                                       {"aggressive": "#b4532a", "passive": "#4f7896"}),
                                    "size": V.quant("pop", "Population"),
                                    "tooltip": V.tooltip(("name", "Mob"), ("vnum", "Vnum"), ("area", "Area"),
                                                         ("level", "Level"), ("hp", "HP"), ("dmg", "Damage"),
                                                         ("pop", "Population"))})
    return out


def _with_charts(markdown: str, charts: dict[str, dict]) -> str:
    md = V.strip_text_histograms(markdown)
    for heading, chart in charts.items():
        md = V.insert_after_heading(md, heading, V.embed(chart))
    return md


def weapons_page(world: World) -> str:
    return _with_charts(W.render(world), weapon_charts(world))


def mobs_page(world: World) -> str:
    return _with_charts(M.render(world), mob_charts(world))


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


__all__ = ["target_pages", "weapon_charts", "mob_charts"]
