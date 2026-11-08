"""Levelling path page."""

from __future__ import annotations

import math

from collections import defaultdict

from ...areafile.world import World
from ...assess import common as C
from ...assess import levelling as L
from ...assess import mobs as M
from .. import charts as V
from .common import HIGHLIGHT, MUTED, _list, _plural, _span, by_area, edit_effort, finding, rec, story

TOP_AREAS = 9


def levelling_story(world: World):
    a = L.analyse(world)
    none_from = next((lvl for lvl in C.LEVELS if all(not a.suitable(x) for x in range(lvl, C.HERO_LEVEL + 1))), None)
    thin = sum(1 for lvl in C.LEVELS if len(a.suitable(lvl)) <= 3)
    top_shares = [a.top_share(lvl)[1] for lvl in C.LEVELS]
    tiles = V.stat_tiles([
        (f"{a.levels_of_xp(3):.0f} → {a.levels_of_xp(88):.1f}", "levels' worth of XP per world reset, level 3 → 88"),
        (str(none_from) if none_from else "—", "level from which no area suits"),
        (str(len(a.unreachable_rooms)), "rooms unreachable on foot from recall"),
        (str(max(d for _, d, _ in a.area_distance())), "steps to the farthest area"),
    ])
    return story("levelling", "Levelling path",
                 "Where a character of each level can go for experience: how many areas suit them, how much XP the "
                 "world offers per reset, which areas carry each stretch of levels, and how far away they are.", tiles, [
                     finding("levelling.xp-supply", _supply(a, none_from), metric=round(a.levels_of_xp(88), 1),
                             label="levels' worth of XP per reset for a level-88 character", better="higher", impact=3,
                             recs=[_r_supply(a)]),
                     finding("levelling.suitable-areas", _areas(a), metric=thin,
                             label="levels with three or fewer areas to level in", impact=3,
                             recs=[_r_areas(a)]),
                     finding("levelling.area-dominance", _dominance(a), metric=round(100 * max(top_shares)),
                             label="% largest share of a level's XP from one area"),
                     finding("levelling.distance", _distance(a), metric=max(d for _, d, _ in a.area_distance()),
                             label="steps from recall to the farthest area", better="none", issue=False),
                     finding("levelling.unreachable", _unreachable(a), metric=len(a.unreachable_rooms),
                             label="rooms unreachable on foot",
                             recs=[_r_unreachable(a)]),
                 ], a.method())


def levelling_page(world: World) -> str:
    return levelling_story(world).markdown()


def _x():
    return V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False})


def _supply(a: L.LevellingAnalysis, none_from: int | None) -> str:
    rows = [{"level": lvl, "levels": round(a.levels_of_xp(lvl), 2)} for lvl in C.LEVELS]
    one = [{"level": lvl, "y": 1} for lvl in C.LEVELS]
    chart = {**V.spec([], title="Levels' worth of XP a full world reset offers a character of each level "
                                "(log scale; dashed = one level)"),
             "layer": [
                 # a line, not an area: an area needs a zero baseline, which a log scale doesn't have
                 {"data": {"values": rows}, "mark": {"type": "line", "color": "#f5b82e", "strokeWidth": 2.5},
                  "encoding": {"x": _x(), "y": V.quant("levels", "Levels of XP", scale={"type": "log"}),
                               "tooltip": V.tooltip(("level", "Level"), ("levels", "Levels of XP"))}},
                 {"data": {"values": one}, "mark": {"type": "line", "strokeDash": [5, 4], "color": "#a8998b"},
                  "encoding": {"x": {"field": "level", "type": "quantitative"},
                               "y": {"field": "y", "type": "quantitative"}}},
             ]}
    x = {lvl: a.levels_of_xp(lvl) for lvl in (3, 20, 40, 60, 80, 88)}
    thin = [lvl for lvl in C.LEVELS if a.levels_of_xp(lvl) < 3]
    text = (f"Killing every level-appropriate mob once, in a freshly reset world, is worth about **{x[3]:.0f} levels** "
            f"of XP to a level-3 character, {x[20]:.0f} at level 20, {x[40]:.0f} at 40, {x[60]:.0f} at 60, {x[80]:.0f} "
            f"at 80 and **{x[88]:.1f}** at 88. Areas reset every 4–22 minutes (see World model), so even a thin supply "
            "refills, but "
            + (f"from level {thin[0]} there's less than three levels' worth on offer per reset, shared by everyone "
               "at that level. " if thin else "")
            + "This mirrors the mob population cliff on the Mobs page.\n")
    return (f"\n## The XP on offer falls {x[3] / x[88]:.0f}× between level 3 and level 88\n\n" + text + V.embed(chart))


def _areas(a: L.LevellingAnalysis) -> str:
    rows = [{"level": lvl, "areas": len(a.suitable(lvl)), "thin": "3 or fewer" if len(a.suitable(lvl)) <= 3 else "4+"}
            for lvl in C.LEVELS]
    chart = V.spec(rows, title=f"Areas with at least {L.MIN_MOBS} level-appropriate mobs, at each level", mark="bar",
                   encoding={"x": {**V.ordinal("level", "Level"),
                                   "axis": {"values": [1] + list(range(5, C.HERO_LEVEL + 1, 5)), "labelAngle": 0}},
                             "y": V.quant("areas", "Suitable areas"),
                             "color": V.nominal("thin", "", {"3 or fewer": HIGHLIGHT, "4+": MUTED}),
                             "tooltip": V.tooltip(("level", "Level"), ("areas", "Areas"))})
    thin = [lvl for lvl in C.LEVELS if len(a.suitable(lvl)) <= 3]
    none = [lvl for lvl in C.LEVELS if not a.suitable(lvl)]
    text = (f"Up to level 15 a character can choose from {min(len(a.suitable(x)) for x in range(1, 16))}–"
            f"{max(len(a.suitable(x)) for x in range(1, 16))} areas. "
            f"**{len(thin)} levels** offer three or fewer"
            + (f", and {len(none)} (levels {M._ranges(none)}) offer none at all" if none else "") + ". "
            "Area level ranges advertised in `areas` often don't match the mobs inside (see Mobs), so this counts "
            "areas by the mobs they actually hold.\n")
    return (f"\n## {len(thin)} levels have three or fewer areas to level in\n\n" + text + V.embed(chart)
            + V.details("Details: by level band", a.band_table()))


def _dominance(a: L.LevellingAnalysis) -> str:
    totals = defaultdict(float)
    for lvl in C.LEVELS:
        for o in a.offers[lvl]:
            totals[o.area] += o.xp / max(1.0, sum(x.xp for x in a.offers[lvl]))
    top = [n for n, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:TOP_AREAS]]
    rows = []
    for lvl in C.LEVELS:
        total = sum(o.xp for o in a.offers[lvl]) or 1
        other = 0.0
        for o in a.offers[lvl]:
            if o.area in top:
                rows.append({"level": lvl, "area": o.area, "share": o.xp / total, "rank": top.index(o.area)})
            else:
                other += o.xp / total
        rows.append({"level": lvl, "area": "other areas", "share": other, "rank": len(top)})
    chart = V.spec(rows, title="Where the XP comes from at each level (share of XP on offer)", height=340,
                   mark={"type": "area"},
                   encoding={"x": _x(), "y": V.quant("share", "Share of XP", stack="normalize", axis={"format": "%"}),
                             "color": V.nominal("area", "Area", {**dict(zip(top, V.WARM_CATEGORY)),
                                                                 "other areas": "#d9cfc3"}, top + ["other areas"]),
                             "order": {"field": "rank", "type": "quantitative"},
                             "tooltip": [{"field": "area"}, {"field": "level"},
                                         {"field": "share", "title": "Share", "format": ".0%"}]})
    runs = []
    for lvl in C.LEVELS:
        name, share = a.top_share(lvl)
        if name and share >= 0.3:
            runs.append((lvl, name, share))
    by_area = defaultdict(list)
    for lvl, name, share in runs:
        by_area[name].append(lvl)
    biggest = max(by_area.items(), key=lambda kv: len(kv[1])) if by_area else None
    text = ("Most levels draw on many areas, but a few areas carry whole stretches. "
            + (f"**{biggest[0]}** supplies 30% or more of the XP on offer at {_plural(len(biggest[1]), 'level')} "
               f"({M._ranges(biggest[1])}). " if biggest else "")
            + f"The {TOP_AREAS} areas that matter most across the whole range are shown; everything else is "
            "grouped as other areas. A level stretch that leans on one area depends on that area's design.\n")
    title = (f"{biggest[0]} carries levels {M._ranges(biggest[1])}" if biggest
             else "No single area dominates any level")
    return f"\n## {title}\n\n" + text + V.embed(chart)


def _distance(a: L.LevellingAnalysis) -> str:
    pts = [{"area": n, "steps": d, "level": lvl} for n, d, lvl in a.area_distance() if lvl is not None]
    chart = V.spec(pts, title="Walking distance from recall vs the median level of an area's mobs", height=320,
                   mark={"type": "point", "filled": True, "size": 80, "opacity": 0.8, "color": HIGHLIGHT},
                   encoding={"x": V.quant("level", "Median mob level"), "y": V.quant("steps", "Steps from recall"),
                             "tooltip": V.tooltip(("area", "Area"), ("level", "Median mob level"),
                                                  ("steps", "Steps"))})
    far = sorted(pts, key=lambda p: -p["steps"])[:3]
    near_high = sorted((p for p in pts if p["level"] >= 60), key=lambda p: p["steps"])[:2]
    text = ("Every area is measured from the Midgaard temple, where recall leads, along room exits. "
            + f"The farthest are {_list([f'{p['area']} ({p['steps']} steps, mobs around level {p['level']:g})' for p in far])}. "
            + (f"Some high-level areas sit right next to recall: "
               f"{_list([f'{p['area']} ({p['steps']} steps, level {p['level']:g})' for p in near_high])}. "
               if near_high else "")
            + "Distance isn't a problem in itself (portals and spells shortcut it, and aren't followed here), but "
            "newcomers wandering out of Midgaard can walk straight into high-level content.\n")
    return ("\n## Some of the toughest areas are a few steps from recall\n\n" + text + V.embed(chart)
            + V.details("Details: every area's distance", a.distance_table()))


def _unreachable(a: L.LevellingAnalysis) -> str:
    rows = a.unreachable_by_area()
    mobs = sum(r[3] for r in rows)
    return (f"\n## {len(a.unreachable_rooms)} rooms can't be reached on foot\n\n"
            f"{len(a.unreachable_rooms)} rooms in {_plural(len(rows), 'area')} have no walking route from recall, and "
            f"{_plural(mobs, 'mob reset')} place mobs in them. Some are deliberate (immortal rooms, rooms reached by "
            "portal, mob program or a one-way trap), others may be broken exits worth checking.\n"
            + V.details("Details: unreachable rooms by area", a.unreachable_table()))


# -- recommendations -------------------------------------------------------------------------------------
SUPPLY_TARGET = 3  # levels' worth of XP per reset a level should offer (the finding's threshold)


def _r_supply(a: L.LevellingAnalysis):
    from ...assess import combat as CB

    thin = {lvl: SUPPLY_TARGET - a.levels_of_xp(lvl) for lvl in C.LEVELS if a.levels_of_xp(lvl) < SUPPLY_TARGET}
    if not thin:
        return None
    plan = []
    for band in C.bands():
        short = {lvl: d for lvl, d in thin.items() if lvl in band}
        if not short:
            continue
        mid = (band.lo + band.hi) // 2
        # mobs of level `mid`, counted with the XP each short level actually gets for them
        need = max(math.ceil(d * L.XP_PER_LEVEL / CB.xp_per_kill(lvl, mid, 0, True)) for lvl, d in short.items())
        plan.append((band, mid, need))
    total = sum(n for _, _, n in plan)
    return rec("levelling.xp-supply.more-mobs", f"Add about {total} level-appropriate mobs from level {min(thin)}",
               "New combat mobs per level band, at the band's middle level: "
               + _list([f"{b.label}: {n} of level {mid}" for b, mid, n in plan])
               + ". Counted with `xp_compute`'s reward for each level in the band, for neutral mobs and a solo "
               "player.",
               f"Every level from {min(thin)} to {max(thin)} would offer at least {SUPPLY_TARGET} levels' worth of XP "
               f"per reset (today level 88 has {a.levels_of_xp(88):.1f}).",
               effort=3, kind="design")


def _r_areas(a: L.LevellingAnalysis):
    thin = [lvl for lvl in C.LEVELS if len(a.suitable(lvl)) <= 3]
    if not thin:
        return None
    runs, start = [], thin[0]
    for prev, cur in zip(thin, thin[1:] + [None]):
        if cur != prev + 1:
            runs.append((start, prev))
            start = cur
    need = [(lo, hi, max(4 - len(a.suitable(lvl)) for lvl in range(lo, hi + 1))) for lo, hi in runs]
    total = sum(n for _, _, n in need)
    return rec("levelling.suitable-areas.new-areas", f"Build or re-level areas for levels {M._ranges(thin)}",
               f"{_plural(len(thin), 'level')} offer three or fewer areas with at least {L.MIN_MOBS} "
               "level-appropriate mobs. Areas needed to give each at least four: "
               + _list([f"{_span((lo, hi))}: {n}" for lo, hi, n in need])
               + f" (an area spanning several of these ranges counts for each; {total} if each is separate). "
               "Moving under-used areas' mobs into these levels works too.",
               f"Levels with three or fewer areas: **{len(thin)} → 0** (every level gets at least 4).",
               effort=3, kind="design")


def _r_unreachable(a: L.LevellingAnalysis):
    rows = a.unreachable_by_area()
    if not rows:
        return None
    mobs = sum(r[3] for r in rows)
    return rec("levelling.unreachable.connect", f"Connect or retire the {_plural(len(a.unreachable_rooms), 'unreachable room')}",
               f"Add exits to them ({by_area([r[0] for r in rows for _ in range(r[1])])}), or delete them if "
               "they're leftovers. Skip rooms reached on purpose by portals or mob programs.",
               f"Rooms with no walking route from recall: **{len(a.unreachable_rooms)} → 0**"
               + (f"; {_plural(mobs, 'mob reset')} placed in them become reachable." if mobs else "."),
               effort=edit_effort(len(rows), len(a.unreachable_rooms)), impact=1)
