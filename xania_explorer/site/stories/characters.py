"""Characters page: classes and races from level 1 to 91."""

from __future__ import annotations

from ...areafile.world import World
from ...assess import characters as CH
from ...assess import common as C
from ...source.cpp_tables import CLASSES
from .. import charts as V
from .common import _a, _list, finding, story


def characters_story(world: World):
    a = CH.analyse(world)
    lo, hi = a.xp_extremes
    human = {c: a.build("human", c) for c in CLASSES}
    hp_ratio = a.hp91(human["barbarian"]) / a.hp91(human["mage"])
    swings = {c: a.hp91(a.best_worst(c, a.hp91)[0]) - a.hp91(a.best_worst(c, a.hp91)[1]) for c in CLASSES}
    maxed = [b.level_stats_maxed for b in a.builds]
    best_mana, worst_mana = a.best_worst("mage", lambda b: b.at(C.HERO_LEVEL).mana)
    dragon_gain = max(a.hp91(a.build("dragon", c)) / a.hp91(a.build("human", c)) - 1 for c in CLASSES)
    tiles = V.stat_tiles([
        (f"{hi.xp_per_level / lo.xp_per_level:.0f}×", "XP per level, dearest vs cheapest build"),
        (f"{hp_ratio:.1f}×", "a barbarian's HP vs a mage's at 91"),
        (f"±{max(swings.values()) / 2:.0f}", "HP that race choice swings at 91"),
        (f"{min(maxed)}–{max(maxed)}", "level by which stats are maxed"),
    ])
    return story("characters", "Characters by level",
                 "How each class and race grows from level 1 to 91: the XP each level costs, the HP, mana and "
                 "movement it brings, and how quickly stats max out.", tiles, [
                     finding("characters.xp-cost", _xp(a), metric=round(hi.xp_per_level / lo.xp_per_level, 2),
                             label="× XP per level, dearest vs cheapest build", impact=2),
                     finding("characters.hp-by-class", _hp(a), metric=round(hp_ratio, 2),
                             label="× a barbarian's HP vs a mage's at 91", better="none", issue=False),
                     finding("characters.mana-by-race", _mana(a),
                             metric=round(100 * (best_mana.at(C.HERO_LEVEL).mana / worst_mana.at(C.HERO_LEVEL).mana - 1)),
                             label="% more mana for the best mage race than the worst", better="none", issue=False),
                     finding("characters.race-value", _value(a), metric=round(100 * dragon_gain, 1),
                             label="% more HP at 91 a dragon buys with 4× the XP", better="higher", impact=2),
                     finding("characters.stats-maxed", _stats(a), metric=max(maxed),
                             label="level by which every build can max its stats", better="none", issue=False),
                 ], a.method())


def characters_page(world: World) -> str:
    return characters_story(world).markdown()


def _who(a: CH.CharacterAnalysis, b: CH.Build) -> str:
    """'human' when every class of the race costs the same, else 'dragon mage'."""
    same = {x.xp_per_level for x in a.builds if x.race.name == b.race.name}
    return b.race.name if len(same) == 1 else b.label


def _xp(a: CH.CharacterAnalysis) -> str:
    lo, hi = a.xp_extremes
    lo_name, hi_name = _who(a, lo), _who(a, hi)
    data = [{"race": b.race.name, "class": b.cls.name, "xp": b.xp_per_level} for b in a.builds]
    chart = V.heatmap(data, x="class", y="race", value="xp", title="XP per level, by race and class",
                      x_order=CLASSES, y_order=a.races, value_title="XP per level")
    pricey = sorted({b.race.name: b.race.points for b in a.builds}.items(), key=lambda kv: -kv[1])[:2]
    mults = sorted((b for b in a.builds if b.race.mult_for(b.cls.name) > 100),
                   key=lambda b: -b.race.mult_for(b.cls.name))[:3]
    text = (f"{_a(f'**{hi_name}**').capitalize()} needs **{hi.xp_per_level:,}** XP per level and "
            f"{_a(f'**{lo_name}**')} "
            f"**{lo.xp_per_level:,}**, so reaching level {C.HERO_LEVEL} takes {hi.xp_to_hero:,} against "
            f"{lo.xp_to_hero:,} XP. Two things drive it. Creation points: every 10 points above the default 40 "
            "raise the cost steeply (`exp_per_level`), and "
            + _list([f"{r}s cost {p} points" for r, p in pricey]) + ". Class multipliers: "
            + _list([f"{b.label} ×{b.race.mult_for(b.cls.name) / 100:g}" for b in mults]) + ".\n")
    return (f"\n## {_a(hi_name).capitalize()} needs {hi.xp_per_level / lo.xp_per_level:.0f}× the XP per level of "
            f"{_a(lo_name)}\n\n"
            + text + V.embed(chart) + V.details("Details: XP per level and creation points", a.xp_table()))


def _class_curves(a: CH.CharacterAnalysis, attr: str, title: str, ytitle: str) -> dict:
    lines, bands = [], []
    for c in CLASSES:
        for lvl in C.LEVELS:
            vals = [getattr(b.at(lvl), attr) for b in a.by_class(c)]
            lines.append({"class": c, "level": lvl, "value": round(getattr(a.build("human", c).at(lvl), attr))})
            bands.append({"class": c, "level": lvl, "lo": round(min(vals)), "hi": round(max(vals))})
    colour = V.nominal("class", "Class", V.CLASS_COLOURS, CLASSES)
    x = V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False})
    return {**V.spec([], title=title),
            "layer": [
                {"data": {"values": bands}, "mark": {"type": "area", "opacity": 0.15},
                 "encoding": {"x": x, "y": V.quant("lo", ytitle), "y2": {"field": "hi"},
                              "color": {**colour, "legend": None}}},
                {"data": {"values": lines}, "mark": {"type": "line"},
                 "encoding": {"x": x, "y": V.quant("value", ytitle), "color": colour,
                              "tooltip": V.tooltip(("class", "Class"), ("level", "Level"), ("value", ytitle))}},
            ]}


def _hp(a: CH.CharacterAnalysis) -> str:
    human = {c: a.build("human", c) for c in CLASSES}
    hp = {c: a.hp91(human[c]) for c in CLASSES}
    trained = [b.at(C.HERO_LEVEL).trains_into_hp * CH.HP_PER_TRAIN for b in a.builds]
    chart = _class_curves(a, "hp", "HP at each level: human (line) and range across races (shading)", "HP")
    text = (f"At level {C.HERO_LEVEL} a human barbarian has about **{hp['barbarian']:,.0f}** HP, a knight "
            f"{hp['knight']:,.0f}, a cleric {hp['cleric']:,.0f} and a mage **{hp['mage']:,.0f}**. "
            f"{min(trained)}–{max(trained)} HP of every build comes from trains spent on HP once stats are maxed, "
            "about the same for every class, so the gap comes from the per-level roll (barbarian 13–17, mage 6–8) "
            "and, for barbarians, the extra con of their prime stat.\n")
    return (f"\n## Barbarians finish with {hp['barbarian'] / hp['mage']:.1f}× a mage's HP\n\n" + text
            + V.embed(chart) + V.details(f"Details: HP at level {C.HERO_LEVEL}, every race and class",
                                         a.final_table("hp"))
            + V.details("Details: human HP and mana at every level", a.per_level_table()))


def _mana(a: CH.CharacterAnalysis) -> str:
    best, worst = a.best_worst("mage", lambda b: b.at(C.HERO_LEVEL).mana)
    human = {c: round(a.build("human", c).at(C.HERO_LEVEL).mana) for c in CLASSES}
    chart = _class_curves(a, "mana", "Mana at each level: human (line) and range across races (shading)", "Mana")
    text = (f"Human mages reach about **{human['mage']}** mana, clerics {human['cleric']}, knights {human['knight']} "
            f"and barbarians {human['barbarian']}. Race matters more for casters: {_a(f'**{best.race.name}**')} mage "
            f"ends with {best.at(C.HERO_LEVEL).mana:.0f} and {_a(f'**{worst.race.name}**')} mage with "
            f"{worst.at(C.HERO_LEVEL).mana:.0f}, because mana gain only counts int and wis above 15.\n")
    return (f"\n## {_a(best.race.name).capitalize()} mage ends with "
            f"{best.at(C.HERO_LEVEL).mana / worst.at(C.HERO_LEVEL).mana - 1:.0%} more mana than "
            f"{_a(worst.race.name)} mage\n\n" + text + V.embed(chart)
            + V.details(f"Details: mana at level {C.HERO_LEVEL}, every race and class", a.final_table("mana")))


def _value(a: CH.CharacterAnalysis) -> str:
    points = [{"race": b.race.name, "class": b.cls.name, "xp": b.xp_per_level, "hp": round(a.hp91(b)),
               "label": b.label} for b in a.builds]
    chart = V.spec(points, title=f"XP per level vs HP at level {C.HERO_LEVEL}, every build", height=320,
                   mark={"type": "point", "filled": True, "size": 90, "opacity": 0.85},
                   encoding={"x": V.quant("xp", "XP per level"), "y": V.quant("hp", f"HP at {C.HERO_LEVEL}",
                                                                              scale={"zero": False}),
                             "color": V.nominal("class", "Class", V.CLASS_COLOURS, CLASSES),
                             "tooltip": V.tooltip(("label", "Build"), ("xp", "XP per level"), ("hp", "HP"))})
    gains = {c: a.hp91(a.build("dragon", c)) / a.hp91(a.build("human", c)) - 1 for c in CLASSES}
    dragon_xp = a.build("dragon", "mage").xp_per_level / a.build("human", "mage").xp_per_level
    text = (f"Within a class, the dearest races barely out-grow the cheapest. A dragon pays **{dragon_xp:.0f}×** a "
            f"human's XP per level for {min(gains.values()):.0%}–{max(gains.values()):.0%} more HP at level "
            f"{C.HERO_LEVEL}. Its other benefits (bonus skills such as breath weapons) aren't counted here, but "
            "the price is steep. Each dot is one build; further left is cheaper, higher is tougher.\n")
    return ("\n## Expensive races buy very little extra HP\n\n" + text + V.embed(chart)
            + V.details("Details: race table", a.race_table()))


def _stats(a: CH.CharacterAnalysis) -> str:
    late = max(a.builds, key=lambda b: (b.level_stats_maxed, b.label))
    early = min(a.builds, key=lambda b: (b.level_stats_maxed, b.label))
    elf = a.build("elf", "mage")
    text = (f"With {CH.NEWBIE_TRAINS} trains at creation and one per level, every build can max all five stats by "
            f"level **{early.level_stats_maxed}–{late.level_stats_maxed}** (latest: {late.label}). After that, "
            f"stats stop differentiating builds except through their *caps*: an elf's con tops out at "
            f"{elf.max_stats['con']} ({a.build('elf', 'barbarian').max_stats['con']} for barbarians), which is why "
            "elves have the lowest HP in every class.\n")
    return ("\n## Stats are maxed by level " + f"{late.level_stats_maxed}, then only the caps matter\n\n" + text
            + V.details("Details: start and maximum stats, trains needed", a.stats_table())
            + V.details(f"Details: combat bonuses from stats at level {C.HERO_LEVEL}", a.combat_table()))
