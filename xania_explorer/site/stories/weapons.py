"""Weapons page."""

from __future__ import annotations

from collections import Counter

from ...areafile.world import World
from ...assess import common as C
from ...assess import weapons as W
from .. import charts as V
from .common import BAND_LABELS, HIGHLIGHT, MUTED, _list, _plural, _span, finding, story


def weapons_story(world: World):
    a = W.analyse(world)
    worst = a.worst_plateau
    start = a.class_access("start")
    late = [w for w in a.got if w.level > a.early_cutoff]
    late_mob_only = sum(1 for w in late if not w.buyable and all(s.kind == "mob" for s in w.sources))
    obtainable = {w.vnum for w in a.got}
    tiles = V.stat_tiles([
        (str(len(a.got)), "obtainable weapons"),
        (f"{a.early_count / len(a.got):.0%}", f"usable by level {a.early_cutoff}"),
        (str(worst.length), f"levels a {worst.cls} waits for an upgrade"),
        (str(len(a.over)), "over the damage cap"),
        (str(len(a.lost)), "with no source"),
    ])
    return story("weapons", "Weapons by level and class",
                 "Which weapons a character can find and wield at each level from 1 to 91, how good they are, "
                 "and whether some classes get a worse deal.", tiles, [
                     finding("weapons.supply", _w_supply(a), metric=round(100 * a.early_count / len(a.got)),
                             label=f"% of weapons usable by level {a.early_cutoff}", impact=2),
                     finding("weapons.class-access", _w_access(a),
                             metric=round(max(start.values()) / max(1, min(start.values())), 1),
                             label="× more weapons for the best-served class", impact=3),
                     finding("weapons.plateau", _w_plateau(a), metric=worst.length,
                             label=f"levels a {worst.cls} waits for a better weapon", impact=2),
                     finding("weapons.sources", _w_sources(a),
                             metric=round(100 * late_mob_only / len(late)) if late else None,
                             label=f"% of weapons above {a.early_cutoff} only from mob drops", better="none",
                             issue=False),
                     finding("weapons.over-cap", _w_over(a), metric=sum(1 for w in a.over if w.vnum in obtainable),
                             label="obtainable weapons over the damage cap", impact=2),
                     finding("weapons.no-source", _w_lost(a), metric=len(a.lost), label="weapons with no source"),
                 ], a.method())


def weapons_page(world: World) -> str:
    return weapons_story(world).markdown()


def _w_supply(a: W.WeaponAnalysis) -> str:
    totals = a.band_totals
    k = len(a.bands) // 3
    early_mean = sum(totals[:k]) / k
    late_mean = sum(totals[k:]) / (len(totals) - k)
    chart = V.spec([{"band": b.label, "type": t, "count": n}
                    for b in a.bands for t, n in Counter(w.type for w in a.in_band(b)).items()],
                   title="New obtainable weapons per level band, by type", mark="bar",
                   encoding={"x": V.ordinal("band", "Levels", BAND_LABELS),
                             "y": V.quant("count", "Weapons", stack=True),
                             "color": V.nominal("type", "Type", order=W.ALL_TYPES),
                             "tooltip": V.tooltip(("band", "Levels"), ("type", "Type"), ("count", "Weapons"))})
    return (f"\n## {a.early_count / len(a.got):.0%} of weapons are usable by level {a.early_cutoff}\n\n"
            f"Of {len(a.got)} obtainable weapons, {a.early_count} become usable by level {a.early_cutoff}. "
            f"Up to then each 5-level band brings about **{early_mean:.0f}** new weapons; after it, about "
            f"**{late_mean:.0f}**, and the thinnest band ({a.bands[totals.index(min(totals))].label}) has only "
            f"{min(totals)}.\n"
            + V.embed(chart)
            + V.details("Details: weapons per band and type",
                        a.supply_table() + f"\nSpread across bands: {C.Spread.of(totals).describe()}.\n"))


def _w_access(a: W.WeaponAnalysis) -> str:
    start = a.class_access("start")
    easy = a.class_access("easy")
    ranked = sorted(start, key=lambda c: -start[c])
    top, bottom = ranked[0], ranked[-1]
    empties = {p.name: a.empty_bands(p.name) for p in a.profiles}
    worst_gap = max(empties, key=lambda c: len(empties[c]))
    profile = {p.name: p for p in a.profiles}
    chart = V.spec(
        [{"band": b.label, "class": p.name, "view": view, "count": sum(w.type in types for w in a.in_band(b))}
         for b in a.bands for p in a.profiles for view, types in (("start", p.starting), ("easy", p.easy))],
        title="New weapons per band in each class's types (solid = start, dashed = easy)",
        mark={"type": "line", "point": True},
        encoding={"x": V.ordinal("band", "Levels", BAND_LABELS), "y": V.quant("count", "Weapons"),
                  "color": V.nominal("class", "Class", V.CLASS_COLOURS, [p.name for p in a.profiles]),
                  "strokeDash": {"field": "view", "type": "nominal", "title": "View",
                                 "scale": {"domain": ["start", "easy"], "range": [[1, 0], [5, 3]]},
                                 "legend": {"symbolType": "stroke", "symbolStrokeWidth": 2}},
                  "tooltip": V.tooltip(("band", "Levels"), ("class", "Class"), ("view", "View"),
                                       ("count", "Weapons"))})
    def types(p):
        return f"all {len(p.starting)} types" if len(p.starting) == len(W.SKILLED_TYPES) else ", ".join(p.starting)

    tiles = V.stat_tiles([(str(start[p.name]), f"{p.name}: {types(p)}") for p in a.profiles])
    text = (f"Counting weapons in the types each class starts with, a **{top}** can choose from "
            f"**{start[top]}** and a **{bottom}** from **{start[bottom]}**. ")
    if empties[worst_gap]:
        text += (f"{worst_gap.capitalize()}s ({', '.join(profile[worst_gap].starting)}) get nothing new in "
                 f"{len(empties[worst_gap])} of {len(a.bands)} level bands "
                 f"({_list([b.label for b in empties[worst_gap]])}). ")
    text += (f"Counting the types each class trains cheaply instead (dashed lines), the gap narrows: "
             + ", ".join(f"{c} {easy[c]}" for c in sorted(easy, key=lambda c: -easy[c])) + ".\n")
    return (f"\n## Class access is lopsided: {top} {start[top]}, {bottom} {start[bottom]}\n\n" + text + tiles
            + V.embed(chart)
            + V.details("Details: weapons per band for each class", a.access_table()
                        + "\nBands with **no** new weapon of a class's starting types:\n\n" + a.empty_bands_list()))


def _w_plateau(a: W.WeaponAnalysis) -> str:
    worst = a.worst_plateau
    profile = next(p for p in a.profiles if p.name == worst.cls)
    names = ["any type"] + [p.name for p in a.profiles] + ["cap"]
    series = {"any type": a.best_any, **{p.name: a.best_start[p.name] for p in a.profiles}}
    curve = [{"level": lvl, "series": n, "avg": v} for n, s in series.items() for lvl, v in s.items() if v is not None]
    curve += [{"level": lvl, "series": "cap", "avg": W.allowed_average(lvl, False)} for lvl in C.LEVELS]
    shade = [{"lo": worst.lo, "hi": worst.hi + 1, "label": f"{worst.cls}: {worst.length} levels"}]
    chart = {**V.spec([], title="Best usable weapon at each level (starting types); shaded = longest wait"),
             "data": {"values": curve},
             "layer": [
                 {"data": {"values": shade},
                  "mark": {"type": "rect", "opacity": 0.13, "color": V.CLASS_COLOURS.get(worst.cls, HIGHLIGHT)},
                  "encoding": {"x": {"field": "lo", "type": "quantitative"},
                               "x2": {"field": "hi"}}},
                 {"data": {"values": shade},
                  "mark": {"type": "text", "align": "left", "dx": 4, "dy": 12, "fontWeight": 600,
                           "color": V.CLASS_COLOURS.get(worst.cls, HIGHLIGHT)},
                  "encoding": {"x": {"field": "lo", "type": "quantitative"}, "y": {"value": 0},
                               "text": {"field": "label"}}},
                 {"mark": {"type": "line", "interpolate": "step-after"},
                  "encoding": {"x": V.quant("level", "Character level",
                                            scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                               "y": V.quant("avg", "Average damage"),
                               "color": V.nominal("series", "Series", V.CLASS_COLOURS, names),
                               "strokeDash": {"condition": {"test": "datum.series === 'cap'", "value": [4, 4]},
                                              "value": [1, 0]},
                               "tooltip": V.tooltip(("series", "Series"), ("level", "Level"), ("avg", "Avg"))}},
             ]}
    others = [x for x in (a.plateaus(p.name, 1)[0] for p in a.profiles) if x.cls != worst.cls]
    text = (f"From level {worst.lo} to {worst.hi}, the best {'/'.join(profile.starting)} a {worst.cls} can use stays "
            f"at average damage **{worst.value:g}**, while the damage cap for their level rises from "
            f"{W.allowed_average(worst.lo, False):g} to {W.allowed_average(worst.hi, False):g}. "
            "Longest waits for the other classes: "
            + ", ".join(f"{x.cls} {x.length} levels ({x.lo}–{x.hi})" for x in others) + ".\n")
    return (f"\n## {worst.cls.capitalize()}s wait {worst.length} levels for a better weapon\n\n" + text
            + V.embed(chart)
            + V.details("Details: longest waits per class", a.plateau_table())
            + V.details("Details: best weapon as a share of the cap, per band", a.cap_ratio_table())
            + V.details("Details: best weapon at every level", a.per_level_table()))


def _w_sources(a: W.WeaponAnalysis) -> str:
    def primary(w: W.Weapon) -> str:
        if w.buyable:
            return "shop"
        if any(s.kind in ("floor", "container") for s in w.sources):
            return "floor/container"
        return "mob drop"

    rows = [{"band": b.label, "source": k, "count": n}
            for b in a.bands for k, n in Counter(primary(w) for w in a.in_band(b)).items()]
    late = [w for w in a.got if w.level > a.early_cutoff]
    mob_only = sum(primary(w) == "mob drop" for w in late)
    early_shop = sum(w.buyable for w in a.got if w.level <= a.early_cutoff)
    late_shop = sum(w.buyable for w in late)
    drops = [w.best_drop_pct for w in late if w.best_drop_pct is not None]
    chart = V.spec(rows, title="Where each band's weapons come from", mark="bar",
                   encoding={"x": V.ordinal("band", "Levels", BAND_LABELS),
                             "y": V.quant("count", "Weapons", stack=True),
                             "color": V.nominal("source", "Easiest source",
                                                {"shop": "#e0a030", "floor/container": "#5f8a5b",
                                                 "mob drop": "#b4532a"}),
                             "order": {"field": "source", "sort": "descending"},
                             "tooltip": V.tooltip(("band", "Levels"), ("source", "Source"), ("count", "Weapons"))})
    share = mob_only / len(late) if late else 0
    return (f"\n## Above level {a.early_cutoff}, {share:.0%} of weapons only come from mob drops\n\n"
            f"Shops stock {_plural(early_shop, 'weapon')} up to level {a.early_cutoff} but only "
            f"{late_shop} after it. Past that point a character has to kill for nearly every upgrade; the "
            f"median best drop chance is **{C.median_or(drops, 0):g}%**.\n"
            + V.embed(chart)
            + V.details("Details: sources per band", a.source_table()))


def _w_over(a: W.WeaponAnalysis) -> str:
    points = [{"level": w.level, "avg": w.average, "name": w.obj.short_descr, "type": w.type, "vnum": w.vnum,
               "area": a.world.obj_area[w.vnum].name, "status": "over cap" if w.over_cap else "within cap",
               "sources": ", ".join(w.source_kinds)} for w in a.got]
    cap = [{"level": lvl, "cap": W.allowed_average(lvl, False)} for lvl in C.LEVELS]
    chart = {**V.spec([], title="Every obtainable weapon: level vs average damage (dashed = cap; drag to zoom)",
                      height=340),
             "data": {"values": points},
             "layer": [
                 {"mark": {"type": "point", "filled": True, "opacity": 0.75},
                  "params": [{"name": "zoom", "select": "interval", "bind": "scales"}],
                  "encoding": {"x": V.quant("level", "Weapon level"), "y": V.quant("avg", "Average damage"),
                               "color": V.nominal("status", "", {"over cap": HIGHLIGHT, "within cap": MUTED}),
                               "size": {"condition": {"test": "datum.status === 'over cap'", "value": 60},
                                        "value": 25},
                               "tooltip": V.tooltip(("name", "Weapon"), ("vnum", "Vnum"), ("area", "Area"),
                                                    ("type", "Type"), ("level", "Level"), ("avg", "Avg"),
                                                    ("sources", "Sources"))}},
                 {"data": {"values": cap}, "mark": {"type": "line", "strokeDash": [4, 4], "color": "#9a8b7e"},
                  "encoding": {"x": {"field": "level", "type": "quantitative"},
                               "y": {"field": "cap", "type": "quantitative"}}},
             ]}
    obtainable = {w.vnum for w in a.got}
    over = [w for w in a.over if w.vnum in obtainable]
    other = len(a.over) - len(over)
    if not over:
        return "\n## No obtainable weapon exceeds the damage cap\n" + V.embed(chart)
    high = sum(w.obj.level >= 80 for w in over)
    top = over[0]
    areas = Counter(a.world.obj_area[w.vnum].name for w in over).most_common(3)
    return (f"\n## {len(over)} obtainable weapons exceed the damage cap\n\n"
            f"{high} of them are level 80 or above. The biggest overshoot is **{top.obj.short_descr}** "
            f"({a.world.obj_area[top.vnum].name}, level {top.obj.level}): average {top.average:g} against a cap of "
            f"{top.cap:g}. The most offenders come from {_list([f'{n} ({c})' for n, c in areas])}."
            + (f" Another {other} over-cap weapons can't be obtained or are above level {C.HERO_LEVEL}."
               if other else "") + "\n"
            + V.embed(chart)
            + V.details(f"Details: all {len(a.over)} weapons over the cap", a.over_table()))


def _w_lost(a: W.WeaponAnalysis) -> str:
    if not a.lost:
        return ""
    return (f"\n## {len(a.lost)} weapons can't be obtained\n\n"
            "No reset places them, so they never appear in normal play. They may still be loaded by mob "
            "programs, specials or immortals.\n"
            + V.details(f"Details: the {len(a.lost)} weapons", a.lost_table()))


