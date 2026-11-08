"""Mobs page."""

from __future__ import annotations

from collections import Counter

from ...areafile.world import World
from ...assess import common as C
from ...assess import mobs as M
from .. import charts as V
from .common import BAND_LABELS, HIGHLIGHT, MUTED, _list, _plural, _span


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
