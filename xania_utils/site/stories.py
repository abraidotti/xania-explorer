"""Findings-first assessment pages for the website.

Each page opens with a row of key numbers, then one section per finding: the
heading *is* the finding, a short paragraph gives the evidence, a chart shows
it (with the relevant part highlighted), and the full table sits in a
collapsed "Details" block. Method goes last, collapsed.

All wording is generated from the analysis, so it stays true as the game data
changes. The plain Markdown reports (``assess`` command) are unchanged.
"""

from __future__ import annotations

from collections import Counter

from ..areafile.world import World
from ..assess import common as C
from ..assess import mobs as M
from ..assess import weapons as W
from . import charts as V

BAND_LABELS = [b.label for b in C.bands()]
MUTED = "#b8ab9c"
HIGHLIGHT = "#b4532a"


def _plural(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def _span(r: tuple[int, int]) -> str:
    return str(r[0]) if r[0] == r[1] else f"{r[0]}–{r[1]}"


def _list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


# =============================================================================
# Weapons
# =============================================================================
def weapons_page(world: World) -> str:
    a = W.analyse(world)
    worst = a.worst_plateau
    out = ["# Weapons by level and class\n\n",
           "Which weapons a character can find and wield at each level from 1 to 91, how good they are, "
           "and whether some classes get a worse deal.\n",
           V.stat_tiles([
               (str(len(a.got)), "obtainable weapons"),
               (f"{a.early_count / len(a.got):.0%}", f"usable by level {a.early_cutoff}"),
               (str(worst.length), f"levels a {worst.cls} waits for an upgrade"),
               (str(len(a.over)), "over the damage cap"),
               (str(len(a.lost)), "with no source"),
           ])]
    out += [_w_supply(a), _w_access(a), _w_plateau(a), _w_sources(a), _w_over(a), _w_lost(a)]
    out.append("\n## Method\n")
    out.append(V.details("How these numbers are calculated", a.method(), kind="info"))
    return "".join(out)


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


# =============================================================================
# Mobs
# =============================================================================
def mobs_page(world: World) -> str:
    a = M.analyse(world)
    out = ["# Mobs by level\n\n",
           "How the mobs a character fights are spread across levels 1 to 91, how tough they are, and whether "
           "they match their area's advertised level range.\n",
           V.stat_tiles([
               (f"~{a.total_pop}", "mobs after a full reset"),
               (f"{a.early_share:.0%}", f"are level ≤ {a.early_cutoff}"),
               (str(len(a.empty_levels)), "levels with no mobs"),
               (str(len(a.outliers)), "toughness outliers"),
               (f"{a.banded_outside / a.banded_mobs:.0%}" if a.banded_mobs else "—", "outside their area's band"),
           ])]
    out += [_m_evenness(a), _m_levels(a), _m_toughness(a), _m_areas(a), _m_excluded(a)]
    out.append("\n## Method\n")
    out.append(V.details("How these numbers are calculated", a.method(), kind="info"))
    return "".join(out)


def _m_evenness(a: M.MobAnalysis) -> str:
    k = len(a.bands) // 3
    chart = V.spec([{"band": b.label, "population": p, "prototypes": n,
                     "phase": f"levels 1–{a.early_cutoff}" if i < k else f"levels {a.early_cutoff + 1}+"}
                    for i, (b, p, n) in enumerate(zip(a.bands, a.band_pop, a.band_proto))],
                   title="Mobs a fully reset world holds, per level band", mark="bar",
                   encoding={"x": V.ordinal("band", "Levels", BAND_LABELS),
                             "y": V.quant("population", "Mobs"),
                             "color": V.nominal("phase", "", {f"levels 1–{a.early_cutoff}": HIGHLIGHT,
                                                              f"levels {a.early_cutoff + 1}+": MUTED}),
                             "tooltip": V.tooltip(("band", "Levels"), ("population", "Population"),
                                                  ("prototypes", "Prototypes"))})
    late = a.band_pop[k:-1]  # excluding the single-level 91 band
    return (f"\n## {a.early_share:.0%} of mobs are level {a.early_cutoff} or below\n\n"
            f"Up to level {a.early_cutoff}, each 5-level band holds {min(a.band_pop[:k])}–"
            f"{max(a.band_pop[:k])} mobs; after it, {min(late)}–{max(late)}. The busiest band is "
            f"{a.bands[a.band_pop.index(max(a.band_pop))].label} with {max(a.band_pop)}. Spread across bands: "
            f"CV {a.spread.cv:.2f}, Gini {a.spread.gini:.2f} (0 would be perfectly even).\n"
            + V.embed(chart)
            + V.details("Details: mobs per band (counts, toughness, aggression)",
                        a.band_table() + f"\n- Prototypes per band: {C.Spread.of(a.band_proto).describe()}.\n"
                        f"- Population per band: {a.spread.describe()}.\n"))


def _m_levels(a: M.MobAnalysis) -> str:
    rows = [{"level": lvl, "population": a.level_pop[lvl], "prototypes": a.level_proto[lvl]} for lvl in C.LEVELS]
    empty = [{"level": lvl, "note": "no combat mob"} for lvl in a.empty_levels]
    ticks = [1] + list(range(5, C.HERO_LEVEL + 1, 5))
    x = {**V.ordinal("level", "Level"), "axis": {"values": ticks, "labelAngle": 0}}
    chart = {**V.spec([], title="Mobs at every level (marks = levels with none)"),
             "layer": [
                 {"data": {"values": rows}, "mark": "bar",
                  "encoding": {"x": x, "y": V.quant("population", "Mobs"),
                               "tooltip": V.tooltip(("level", "Level"), ("population", "Population"),
                                                    ("prototypes", "Prototypes"))}},
                 {"data": {"values": empty},
                  "mark": {"type": "point", "shape": "triangle-up", "filled": True, "size": 150, "color": "#e0a030",
                           "stroke": "#7a4a0c", "strokeWidth": 1},
                  "encoding": {"x": x, "y": {"value": {"expr": "height - 5"}},
                               "tooltip": V.tooltip(("level", "Level"), ("note", "Note"))}},
             ]}
    levels_text = M._ranges(a.empty_levels)
    per_level = C.Spread.of(list(a.level_pop.values()))
    title = (f"{_plural(len(a.empty_levels), 'level')} {'has' if len(a.empty_levels) == 1 else 'have'} "
             "no combat mob at all") if a.empty_levels else "Every level has at least one combat mob"
    text = (f"No combat mob exists at level{'s' if len(a.empty_levels) != 1 else ''} **{levels_text}**. "
            if a.empty_levels else "")
    text += (f"Across single levels the population ranges from {per_level.min:g} to {per_level.max:g} "
             f"(CV {per_level.cv:.2f}).\n")
    return f"\n## {title}\n\n" + text + V.embed(chart)


def _m_toughness(a: M.MobAnalysis) -> str:
    flagged = {o.info.mob.vnum for o in a.outliers}
    points = [{"level": i.level, "hp": max(i.mob.hit.average, 1), "dmg": i.mob.damage.average,
               "name": i.mob.short_descr, "area": i.area.name, "vnum": i.mob.vnum, "pop": i.population,
               "kind": "outlier" if i.mob.vnum in flagged else "typical"} for i in a.combat]
    chart = V.spec(points, title="Every combat mob: level vs average HP (log scale; drag to zoom)", height=380,
                   mark={"type": "point", "filled": True, "opacity": 0.7},
                   params=[{"name": "zoom", "select": "interval", "bind": "scales"}],
                   encoding={"x": V.quant("level", "Mob level", scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                             "y": V.quant("hp", "Average HP", scale={"type": "log"}),
                             "color": V.nominal("kind", "", {"outlier": HIGHLIGHT, "typical": "#8fa3b0"}),
                             "size": {"condition": {"test": "datum.kind === 'outlier'", "value": 70}, "value": 22},
                             "tooltip": V.tooltip(("name", "Mob"), ("vnum", "Vnum"), ("area", "Area"),
                                                  ("level", "Level"), ("hp", "HP"), ("dmg", "Damage"),
                                                  ("pop", "Population"))})
    first, mid, last = a.bands[0], a.bands[len(a.bands) // 2], a.bands[-2]
    smooth = not a.hp_drops
    title = (f"Toughness rises smoothly, with {len(a.outliers)} outliers" if smooth
             else f"Toughness mostly rises with level, with {len(a.outliers)} outliers")
    text = (f"Median HP climbs from **{a.median_hp(first):g}** ({first.label}) to **{a.median_hp(mid):g}** "
            f"({mid.label}) and **{a.median_hp(last):g}** ({last.label}). ")
    if a.hp_drops:
        text += ("It dips going into " + ", ".join(f"{b} ({x:g}→{y:g})" for b, x, y in a.hp_drops) + ". ")
    tough = sorted((o for o in a.outliers if max(o.hp_ratio, o.dmg_ratio) > M.OUTLIER_HIGH),
                   key=lambda o: -max(o.hp_ratio, o.dmg_ratio))
    weak = [o for o in a.outliers if o not in tough]
    if tough:
        o = tough[0]
        what = "HP" if o.hp_ratio >= o.dmg_ratio else "damage"
        text += (f"{_plural(len(tough), 'mob is', 'mobs are')} far tougher than their level suggests; the most "
                 f"extreme is **{o.info.mob.short_descr}** ({o.info.area.name}, level {o.info.mob.level}) with "
                 f"{max(o.hp_ratio, o.dmg_ratio):.1f}× the usual {what}. ")
    if weak:
        tiny = sum(o.info.mob.level <= 5 for o in weak)
        text += (f"{_plural(len(weak), 'mob is', 'mobs are')} far weaker than their level suggests"
                 + (f", {tiny} of them level 5 or below (critters like rats and ducks)." if tiny * 2 > len(weak)
                    else "."))
    text += "\n"
    return (f"\n## {title}\n\n" + text + V.embed(chart)
            + V.details(f"Details: all {len(a.outliers)} outliers", a.outlier_table(limit=None)))


def _m_areas(a: M.MobAnalysis) -> str:
    worst = [m for m in a.area_misses if m.outside_share >= 0.5]
    top = a.area_misses[:15]
    rows = []
    for m in top:
        rows.append({"area": m.area, "where": "below the band", "share": m.below / m.mobs,
                     "total": m.outside_share, "band": f"{m.band[0]}–{m.band[1]}"})
        rows.append({"area": m.area, "where": "above the band", "share": m.above / m.mobs,
                     "total": m.outside_share, "band": f"{m.band[0]}–{m.band[1]}"})
    chart = V.spec(rows, title="Share of each area's mobs outside its advertised level band (worst 15)",
                   height=max(220, 22 * len(top)), mark="bar",
                   encoding={"y": {"field": "area", "type": "nominal", "title": None,
                                   "sort": {"field": "total", "order": "descending"}},
                             "x": V.quant("share", "Share of the area's combat mobs", axis={"format": "%"},
                                          stack=True),
                             "color": V.nominal("where", "", {"below the band": "#4f7896",
                                                              "above the band": HIGHLIGHT}),
                             "tooltip": V.tooltip(("area", "Area"), ("band", "Advertised band"),
                                                  ("where", "Where"), ("share", "Share"))})
    share = a.banded_outside / a.banded_mobs if a.banded_mobs else 0
    text = (f"Of the {a.banded_mobs} combat mobs in areas that advertise a level range, **{share:.0%}** fall "
            f"outside it. In {_plural(len(worst), 'area')}, most of the mobs do"
            + (f": {_list([f'{m.area} ({m.band[0]}–{m.band[1]}, actually {_span(m.actual)})' for m in worst[:4]])}"
               if worst else "") + ". Players choosing areas by the `areas` list will be misled.\n")
    title = (f"{_plural(len(worst), 'area')} {'has' if len(worst) == 1 else 'have'} most mobs outside "
             "their advertised level range") if worst else "Areas mostly match their advertised level range"
    return (f"\n## {title}\n\n" + text + V.embed(chart)
            + V.details("Details: every area with mobs outside its band", a.area_table()))


def _m_excluded(a: M.MobAnalysis) -> str:
    return ("\n## Left out of these numbers\n\n"
            f"{_plural(len(a.high), 'mob')} above level {C.HERO_LEVEL} (hero/immortal content) and "
            f"{_plural(len(a.never), 'mob')} that never spawn.\n"
            + V.details(f"Details: mobs above level {C.HERO_LEVEL}, by area", a.high_summary() + ".")
            + V.details(f"Details: the {len(a.never)} mobs that never spawn",
                        "No `M` reset, or every `M` reset has a world cap ≤ 0. Some may still be loaded by mob "
                        "programs or specials.\n\n" + a.never_table()))
