"""Weapons page."""

from __future__ import annotations

from collections import Counter

from ...areafile.world import World
from ...assess import common as C
from ...assess import weapons as W
from .. import charts as V
from .common import BAND_LABELS, HIGHLIGHT, MUTED, _list, _plural, _span, by_area, edit_effort, finding, rec, src_link, story


def weapons_story(world: World):
    a = W.analyse(world)
    worst = a.worst_plateau
    start = a.class_access("start")
    late = [w for w in a.got if w.level > a.early_cutoff]
    late_mob_only = sum(1 for w in late if w.sources and all(s.kind == "mob" for s in w.sources))
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
                             label=f"% of weapons usable by level {a.early_cutoff}", impact=2,
                             recs=[_r_supply(a)]),
                     finding("weapons.class-access", _w_access(a),
                             metric=round(max(start.values()) / max(1, min(start.values())), 1),
                             label="× more weapons for the best-served class", impact=3,
                             recs=_r_access(a)),
                     finding("weapons.plateau", _w_plateau(a), metric=worst.length,
                             label=f"levels a {worst.cls} waits for a better weapon", impact=2,
                             recs=[_r_plateau(a)]),
                     finding("weapons.sources", _w_sources(a),
                             metric=round(100 * late_mob_only / len(late)) if late else None,
                             label=f"% of weapons above {a.early_cutoff} only from mob drops", better="none",
                             issue=False),
                     finding("weapons.over-cap", _w_over(a), metric=sum(1 for w in a.over if w.vnum in obtainable),
                             label="obtainable weapons over the damage cap", impact=2,
                             recs=[_r_over(a)]),
                     finding("weapons.no-source", _w_lost(a), metric=len(a.lost), label="weapons with no source",
                             recs=[_r_lost(a)]),
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
        if any(s.kind == "code" for s in w.sources):
            return "given by the game"
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
                                                {"shop": "#f5b82e", "floor/container": "#3fa66b",
                                                 "given by the game": "#3f88c5", "mob drop": "#e4572e"}),
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
                 {"data": {"values": cap}, "mark": {"type": "line", "strokeDash": [4, 4], "color": "#a8998b"},
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




# -- recommendations -------------------------------------------------------------------------------------
def _r_supply(a: W.WeaponAnalysis):
    totals = a.band_totals
    k = len(a.bands) // 3
    late = sorted(totals[k:])
    median = late[len(late) // 2]
    thin = [(b, n) for b, n in zip(a.bands[k:], totals[k:]) if n < median / 2]
    if not thin:
        return None
    needed = sum(round(median) - n for _, n in thin)
    return rec("weapons.supply.fill-thin-bands", f"Add weapons to the {_plural(len(thin), 'thinnest level band')}",
               f"Bands {_list([f'{b.label} ({n})' for b, n in thin])} get fewer than half the late-game median of "
               f"{median} new weapons. New weapons there need an object and a reset (shop, floor or mob) in an "
               "area of that level.",
               f"About **{needed}** new weapons would bring each of those bands up to the median.",
               effort=2 if needed <= 15 else 3)


def _r_access(a: W.WeaponAnalysis):
    start = a.class_access("start")
    worst = min(start, key=start.get)
    p = next(p for p in a.profiles if p.name == worst)
    out = []
    missing = [t for t in W.SKILLED_TYPES if t not in p.starting]
    if missing:
        counts = {t: sum(w.type == t for w in a.got) for t in missing}
        easiest = [t for t in missing if t in p.easy] or missing
        add = max(easiest, key=lambda t: counts[t])
        out.append(rec("weapons.class-access.starting-type",
                       f"Give {worst}s {add} skill at creation",
                       f"{worst.capitalize()}s start knowing {_list(p.starting)}. Adding **{add}** to the "
                       f"`\"{worst} basics\"` skill group "
                       f"({src_link(a.world, 'SkillTables.cpp', chr(34) + worst + ' basics' + chr(34))}) gives it to "
                       f"every new {worst} without costing creation points"
                       + (f"; it's already easy for them to train (difficulty {p.difficulty[add]})." if add in p.easy
                          else "."),
                       f"Weapons in a {worst}'s starting types rise from **{start[worst]}** to "
                       f"**{start[worst] + counts[add]}** (best-served class: {max(start.values())}).",
                       effort=1, kind="code"))
    empty = a.empty_bands(worst)
    if empty:
        out.append(rec("weapons.class-access.fill-empty-bands",
                       f"Place {'/'.join(p.starting)} weapons where {worst}s get nothing new",
                       f"{_plural(len(empty), 'level band')} ({_list([b.label for b in empty])}) have no new "
                       f"weapon of a {worst}'s starting types. One weapon per band, within that band's damage cap, "
                       "placed in an area of matching level.",
                       f"Every band would offer a {worst} at least one new weapon ({len(empty)} new objects).",
                       effort=edit_effort(len(empty), len(empty))))
    return out


def _r_plateau(a: W.WeaponAnalysis):
    worst = a.worst_plateau
    if worst.length < 10:
        return None
    p = next(p for p in a.profiles if p.name == worst.cls)
    mid = (worst.lo + worst.hi) // 2
    cap = W.allowed_average(mid, False)
    target = round(((worst.value or 0) + cap) / 2, 1)
    # simulate it: the class's best-weapon curve with the new weapon from level `mid` on
    curve = {lvl: max(v or 0, target) if lvl >= mid else v for lvl, v in a.best_start[worst.cls].items()}
    second = max((hi - lo + 1 for lo, hi, _ in C.runs_without_increase(curve)), default=0)
    if second >= worst.length:
        return None
    return rec("weapons.plateau.mid-upgrade", f"Add a level-{mid} {p.starting[0]} for {worst.cls}s",
               f"One {'/'.join(p.starting)} weapon at level **{mid}**, average damage about **{target:g}** (between "
               f"the current best, {worst.value:g}, and the level-{mid} cap of {cap:g}), from a shop or a common "
               "drop in a level-appropriate area.",
               f"The longest wait for a {worst.cls} upgrade falls from {worst.length} to {second} levels.",
               effort=1)


def _r_over(a: W.WeaponAnalysis):
    obtainable = {w.vnum for w in a.got}
    over = [w for w in a.over if w.vnum in obtainable]
    if not over:
        return None
    areas = [a.world.obj_area[w.vnum].name for w in over]
    return rec("weapons.over-cap.lower-dice", f"Bring {_plural(len(over), 'weapon')} down to the damage cap",
               f"Lower the damage dice of the obtainable over-cap weapons ({by_area(areas)}) so each average is at "
               "most the cap for its level. The table under the finding gives each weapon's cap.",
               f"Obtainable weapons over the cap: **{len(over)} → 0**. Their wielders lose on average "
               f"{sum(w.average - w.cap for w in over) / len(over):.1f} damage per hit.",
               effort=edit_effort(len(set(areas)), len(over)))


def _r_lost(a: W.WeaponAnalysis):
    if not a.lost:
        return None
    areas = [a.world.obj_area[w.vnum].name for w in a.lost]
    return rec("weapons.no-source.place-or-remove", f"Place or remove the {_plural(len(a.lost), 'unplaced weapon')}",
               f"Give each a reset (on a mob, in a room or a shop) or delete it: {by_area(areas)}. Check mob "
               "programs first: some may be handed out by scripts.",
               f"Weapons without a source: **{len(a.lost)} → 0**.",
               effort=edit_effort(len(set(areas)), len(a.lost)), impact=1)
