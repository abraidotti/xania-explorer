"""Equipment page: armour and worn gear from level 1 to 91."""

from __future__ import annotations

from collections import Counter

from ...areafile.world import World
from ...assess import common as C
from ...assess import equipment as E
from ...assess import mobs as M
from ...assess import weapons as W
from .. import charts as V
from .common import BAND_LABELS, HIGHLIGHT, MUTED, _list, _plural

SLOT_ORDER = list(E.SLOTS)


def equipment_page(world: World) -> str:
    a = E.analyse(world)
    k91 = a.ac_kits[C.HERO_LEVEL]
    out = ["# Equipment by level\n\n",
           "Armour and other worn gear: how much protection and hitroll/damroll the world offers at each level from "
           "1 to 91, where the gaps are, and which items break the item-points rule. Weapons have their own page.\n",
           V.stat_tiles([
               (f"{k91.total('ac'):.0f}", f"AC from a best-in-slot kit at {C.HERO_LEVEL}"),
               (f"+{a.hit_kits[C.HERO_LEVEL].total('damroll')}",
                f"damroll from gear at {C.HERO_LEVEL} (+{a.hit_kits[C.HERO_LEVEL].total('hitroll')} hitroll)"),
               (str(len(a.got)), "obtainable pieces of gear"),
               (str(len(a.over_points)), "items over the points rule"),
               (str(len(a.hidden_by_bug)), "more hidden by an AC bug"),
           ])]
    out += [_ac(a), _gaps(a), _hitdam(a), _points(a), _bug(a), _lost(a)]
    out.append("\n## Method\n")
    out.append(V.details("How these numbers are calculated", a.method(), kind="info"))
    return "".join(out)


def _ac(a: E.EquipmentAnalysis) -> str:
    rows = [{"level": lvl, "slot": slot, "ac": sum(i.ac for i in a.ac_kits[lvl].picks[slot])}
            for lvl in C.LEVELS for slot in SLOT_ORDER]
    chart = V.spec(rows, title="AC from a best-in-slot kit at each level, by slot", height=320,
                   mark={"type": "area", "interpolate": "step-after"},
                   encoding={"x": V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                             "y": V.quant("ac", "AC (higher = better protected)", stack=True),
                             "color": V.nominal("slot", "Slot", order=SLOT_ORDER),
                             "tooltip": V.tooltip(("slot", "Slot"), ("level", "Level"), ("ac", "AC"))})
    at = {lvl: a.ac_kits[lvl].total("ac") for lvl in (10, 30, 60, C.HERO_LEVEL)}
    latest_slot = max(SLOT_ORDER, key=lambda s: a.first_level(s) or 99)
    mobs = M.analyse(a.world)
    top_band = mobs.bands[-2]
    mob_ac = C.median_or(i.mean_ac for i in mobs.by_band[top_band])
    text = (f"Wearing the best obtainable piece in every slot gives about **{at[10]:.0f}** AC at level 10, "
            f"**{at[30]:.0f}** at 30, **{at[60]:.0f}** at 60 and **{at[C.HERO_LEVEL]:.0f}** at {C.HERO_LEVEL}. "
            f"Every slot has an armour piece by level {a.first_level(latest_slot)} ({latest_slot} is last). For "
            f"comparison, the median combat mob at levels {top_band.label} has an AC of only {-mob_ac:.0f} (see "
            "Mobs): players can armour far beyond what mobs carry.\n")
    return (f"\n## A fully kitted character reaches {at[C.HERO_LEVEL]:.0f} AC by level {C.HERO_LEVEL}\n\n" + text
            + V.embed(chart) + V.details("Details: kits by level band", a.kit_table()))


def _gaps(a: E.EquipmentAnalysis) -> str:
    waits = sorted(((s, *a.slot_plateau(s)) for s in SLOT_ORDER), key=lambda t: -(t[2] - t[1]))
    worst = waits[0]
    data = a.coverage_rows()
    chart = V.heatmap(data, x="band", y="slot", value="count", title="New obtainable items per slot and level band",
                      x_order=BAND_LABELS, y_order=SLOT_ORDER, value_title="New items", fmt="d")
    chart["encoding"]["x"]["axis"] = {"orient": "top", "labelAngle": -45}
    long_waits = [f"{s} {hi - lo + 1} levels ({lo}–{hi})" for s, lo, hi, _ in waits[:4]]
    text = (f"The longest a slot goes without a better piece is **{worst[2] - worst[1] + 1} levels** for {worst[0]} "
            f"({worst[1]}–{worst[2]}, stuck at AC {worst[3]:g}). Other long waits: {_list(long_waits[1:])}. "
            "Each cell below counts the new items in a slot and band; pale cells are where nothing new appears.\n")
    return (f"\n## {worst[0].capitalize()} armour stops improving for {worst[2] - worst[1] + 1} levels\n\n" + text
            + V.embed(chart) + V.details("Details: every slot", a.slot_table()))


def _hitdam(a: E.EquipmentAnalysis) -> str:
    rows = []
    for lvl in C.LEVELS:
        k = a.hit_kits[lvl]
        rows += [{"level": lvl, "bonus": "hitroll", "value": k.total("hitroll")},
                 {"level": lvl, "bonus": "damroll", "value": k.total("damroll")}]
    chart = V.spec(rows, title="Hitroll and damroll from the best gear at each level",
                   mark={"type": "line", "interpolate": "step-after"},
                   encoding={"x": V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                             "y": V.quant("value", "Bonus"),
                             "color": V.nominal("bonus", "", {"hitroll": "#4f7896", "damroll": HIGHLIGHT}),
                             "tooltip": V.tooltip(("bonus", "Bonus"), ("level", "Level"), ("value", "Value"))})
    k30, k91 = a.hit_kits[30], a.hit_kits[C.HERO_LEVEL]
    combined = {lvl: a.hit_kits[lvl].total("hitroll") + a.hit_kits[lvl].total("damroll") for lvl in C.LEVELS}
    lo, hi, _ = C.runs_without_increase(combined)[0]
    best_weapon = W.analyse(a.world).best_any[C.HERO_LEVEL]
    text = (f"Gear chosen for offence gives +{k30.total('hitroll')} hitroll and +{k30.total('damroll')} damroll at "
            f"level 30, and **+{k91.total('hitroll')}/+{k91.total('damroll')}** at {C.HERO_LEVEL}. Damroll is added "
            "to every hit (fight.cpp:528), so by the late game gear damroll is comparable to the best weapon's dice "
            f"average ({best_weapon:g} at level {C.HERO_LEVEL}, see Weapons). The longest stretch with no "
            f"improvement is levels {lo}–{hi}.\n")
    return (f"\n## Gear adds up to +{k91.total('damroll')} damroll by level {C.HERO_LEVEL}\n\n" + text
            + V.embed(chart))


def _points(a: E.EquipmentAnalysis) -> str:
    pts = [{"level": i.level, "points": i.points, "name": i.obj.short_descr, "vnum": i.vnum,
            "area": a.world.obj_area[i.vnum].name, "status": "over the rule" if i.points > i.allowed else "within"}
           for i in a.items if i.obtainable and i.level <= C.HERO_LEVEL and (i.points or i.obj.affects)]
    allowed = [{"level": lvl, "allowed": E.points_allowed(lvl)} for lvl in C.LEVELS]
    chart = {**V.spec([], title="Every obtainable item with bonuses: points vs level (dashed = allowed)", height=320),
             "data": {"values": pts},
             "layer": [
                 {"mark": {"type": "point", "filled": True, "opacity": 0.7},
                  "params": [{"name": "zoom", "select": "interval", "bind": "scales"}],
                  "encoding": {"x": V.quant("level", "Item level"), "y": V.quant("points", "Points"),
                               "color": V.nominal("status", "", {"over the rule": HIGHLIGHT, "within": MUTED}),
                               "tooltip": V.tooltip(("name", "Item"), ("vnum", "Vnum"), ("area", "Area"),
                                                    ("level", "Level"), ("points", "Points"))}},
                 {"data": {"values": allowed}, "mark": {"type": "line", "strokeDash": [4, 4], "color": "#9a8b7e"},
                  "encoding": {"x": {"field": "level", "type": "quantitative"},
                               "y": {"field": "allowed", "type": "quantitative"}}},
             ]}
    top = a.over_points[0] if a.over_points else None
    areas = _list([f"{n} ({c})" for n, c in
                   Counter(a.world.obj_area[i.vnum].name for i in a.over_points).most_common(3)])
    text = (f"The rule allows `level/10 + 1` points; **{len(a.over_points)}** obtainable items exceed it"
            + (f", most from {areas}" if a.over_points else "") + ". "
            + (f"The furthest over is **{top.obj.short_descr}** ({a.world.obj_area[top.vnum].name}, level "
               f"{top.obj.level}): {top.points} points against {top.allowed}. " if top else "")
            + "Movement and HP bonuses count one point per 7, so large `Move +100` items blow the budget quickly.")
    if a.over_points_immortal:
        i = a.over_points_immortal[0]
        n = len(a.over_points_immortal)
        text += (f" Above level {C.HERO_LEVEL}, {_plural(n, 'item')} also {'breaks' if n == 1 else 'break'} it, "
                 f"including **{i.obj.short_descr}** ({a.world.obj_area[i.vnum].name}) at {i.points} points.")
    return (f"\n## {len(a.over_points)} items break the item-points rule\n\n" + text + "\n" + V.embed(chart)
            + V.details(f"Details: the {len(a.over_points)} items", a.points_table()))


def _bug(a: E.EquipmentAnalysis) -> str:
    return ("\n## Armour-class bonuses are never counted against the rule\n\n"
            "`AFFECT_DATA::worth` (AFFECT_DATA.cpp:86) is meant to charge a point for each −1 of AC or saving-throw "
            "bonus, but its test reads `if (modifier < 0) if (modifier > 0)`, which can never be true. So `Ac` and "
            f"`Saving*` affects are free. Counting them, **{len(a.hidden_by_bug)}** more items would be over the "
            "limit.\n"
            + V.details(f"Details: the {len(a.hidden_by_bug)} items the bug lets through", a.hidden_table()))


def _lost(a: E.EquipmentAnalysis) -> str:
    if not a.lost:
        return ""
    return (f"\n## {len(a.lost)} pieces of gear can't be obtained\n\n"
            "No reset places them. They may still come from mob programs, specials or immortals.\n"
            + V.details(f"Details: the {len(a.lost)} items", a.lost_table()))
