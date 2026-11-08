"""Combat & experience page."""

from __future__ import annotations

from ...areafile.world import World
from ...assess import combat as CB
from ...assess import common as C
from ...source.cpp_tables import CLASSES
from .. import charts as V
from .common import HIGHLIGHT, _list, finding, story

CLOCK_MINUTES = CB.FULL_TIME_FACTOR_HOURS * 60
DEADLY_RUN = 5  # the majority must hold for this many consecutive levels (ignores single noisy levels)


def deadly_onset(a: CB.CombatAnalysis, cls: str) -> int | None:
    """First level from which most level-appropriate mobs are deadly in melee, for good."""
    s = a.series(cls, "deadly_share")
    return next((lvl for lvl in C.LEVELS if lvl > 5
                 and all((s.get(x) or 0) >= 0.5 for x in range(lvl, min(lvl + DEADLY_RUN, C.HERO_LEVEL + 1)))), None)


def combat_story(world: World):
    a = CB.analyse(world)
    hours = {c: a.hours_to_hero(c) for c in CLASSES}
    kills = [v for v in a.series("knight", "kills_per_level").values() if v]
    fastest, slowest = min(hours, key=hours.get), max(hours, key=hours.get)
    onsets = [x for x in (deadly_onset(a, c) for c in CLASSES) if x]
    hit = [v for lvl, v in a.series("mage", "hit_pc").items() if v and lvl >= 20]
    preamble = ("\n!!! warning \"A model, not a simulation\"\n    Expected values from the C++ formulas, for a human of "
                "each class with the best gear the world offers at that level. Spells, buffs such as haste and "
                "sanctuary, resistances and mob skills like bash aren't modelled, so casters look weaker here than "
                "they play. See the Method at the end.\n")
    tiles = V.stat_tiles([
        (f"{min(kills):.0f}–{max(kills):.0f}", "kills per level, at every level"),
        (f"{hours[fastest]:.0f} h", f"of combat to hero for a {fastest}"),
        (f"{hours[slowest]:.0f} h", f"for a {slowest}"),
        (f"{CB.FULL_TIME_FACTOR_HOURS * (C.HERO_LEVEL - 1):.0f} h", "played time needed for full XP"),
    ])
    return story("combat", "Combat & experience by level",
                 "What a straight melee fight against level-appropriate mobs looks like for each class at every level "
                 "from 1 to 91: how often each side hits, how long fights last, how many kills a level takes, and "
                 "when fights turn deadly.", tiles, [
                     finding("combat.kills-per-level", _kills(a), metric=round(sum(kills) / len(kills), 1),
                             label="kills per level on average", better="none", issue=False),
                     finding("combat.xp-clock", _clock(a, hours), metric=round(hours[slowest], 1),
                             label=f"hours of combat to hero for a {slowest} (vs a "
                                   f"{CB.FULL_TIME_FACTOR_HOURS * (C.HERO_LEVEL - 1):.0f} h clock)", impact=3),
                     finding("combat.fight-length", _rounds(a),
                             metric=round(a.series("knight", "rounds")[C.HERO_LEVEL] or 0),
                             label=f"rounds for a knight to kill a level-{C.HERO_LEVEL} mob", impact=2),
                     finding("combat.deadly-melee", _deadly(a), metric=min(onsets) if onsets else None,
                             label="level from which melee turns deadly for the weakest class", better="higher",
                             impact=2),
                     finding("combat.accuracy-dip", _accuracy(a), metric=round(100 * min(hit)) if hit else None,
                             label="% lowest chance per swing for a mage (level 20+)", better="higher"),
                 ], a.method(), preamble)


def combat_page(world: World) -> str:
    return combat_story(world).markdown()


def _lines(a: CB.CombatAnalysis, attr: str, title: str, ytitle: str, fmt: str | None = None,
           extra_layers: list | None = None, height: int = 300) -> dict:
    rows = [{"class": c, "level": lvl, "value": v} for c in CLASSES for lvl, v in a.series(c, attr).items()
            if v is not None]
    y = V.quant("value", ytitle, **({"axis": {"format": fmt}} if fmt else {}))
    line = {"mark": {"type": "line"},
            "encoding": {"x": V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                         "y": y, "color": V.nominal("class", "Class", V.CLASS_COLOURS, CLASSES),
                         "tooltip": [{"field": "class"}, {"field": "level"},
                                     {"field": "value", "title": ytitle, "format": fmt or ".1f"}]}}
    return {**V.spec([], title=title, height=height), "data": {"values": rows},
            "layer": [line] + (extra_layers or [])}


def _kills(a: CB.CombatAnalysis) -> str:
    kills = a.series("knight", "kills_per_level")  # class-independent: XP depends only on levels
    xp = a.series("knight", "xp")
    rows = [{"level": lvl, "kills": k} for lvl, k in kills.items() if k]
    chart = V.spec(rows, title="Kills per level (human, any class) against mobs within ±2 levels",
                   mark={"type": "line", "color": HIGHLIGHT, "point": {"size": 18}},
                   encoding={"x": V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                             "y": V.quant("kills", "Kills per level", scale={"zero": True}),
                             "tooltip": V.tooltip(("level", "Level"), ("kills", "Kills"))})
    early = [kills[lvl] for lvl in range(6, 31) if kills[lvl]]
    late = [kills[lvl] for lvl in range(70, C.HERO_LEVEL + 1) if kills[lvl]]
    text = (f"A human needs 1,000 XP per level at every level, and a level-appropriate kill is worth about "
            f"{xp[10]:.0f} XP at level 10 and {xp[80]:.0f} at level 80, so a level takes roughly "
            f"**{sum(early) / len(early):.0f} kills** in levels 6–30 and **{sum(late) / len(late):.0f}** from 70 up. "
            "XP depends only on the level gap, not class, so this is the same for every class. The rise late on "
            "is `xp_compute` deliberately cutting XP above level 35. Races with dearer XP (up to 4× for "
            "dragons, see Characters) multiply these counts.\n")
    return ("\n## Every level takes about the same number of kills\n\n" + text + V.embed(chart)
            + V.details("Details: XP per kill by level gap", a.xp_table()))


def _clock(a: CB.CombatAnalysis, hours: dict[str, float]) -> str:
    clock = [{"level": lvl, "clock": CLOCK_MINUTES} for lvl in C.LEVELS if lvl >= 15]
    layer = {"data": {"values": clock}, "mark": {"type": "line", "strokeDash": [5, 4], "color": "#9a8b7e"},
             "encoding": {"x": {"field": "level", "type": "quantitative"},
                          "y": {"field": "clock", "type": "quantitative"}}}
    chart = _lines(a, "minutes_per_level", "Minutes of combat per level; dashed = the 90-minute XP clock",
                   "Minutes", extra_layers=[layer])
    under = [c for c in CLASSES if all((v or 0) < CLOCK_MINUTES for lvl, v in a.series(c, "minutes_per_level").items())]
    text = (f"`xp_compute` scales every kill by how long you've played per level: below an average of "
            f"{CB.FULL_TIME_FACTOR_HOURS:g} hours per level the reward shrinks, down to a third (below level 15 "
            "there's a softer floor, and levels 1–2 always get full credit). Reaching level "
            f"{C.HERO_LEVEL} at full XP therefore takes about "
            f"**{CB.FULL_TIME_FACTOR_HOURS * (C.HERO_LEVEL - 1):.0f} hours** of play, whatever the class. Pure "
            "combat time is much less: "
            + ", ".join(f"{c} {hours[c]:.0f} h" for c in sorted(hours, key=hours.get)) + ". "
            + ((f"For {'every class' if len(under) == len(CLASSES) else _list(under)}, combat never fills the "
                "clock, so the time rule, not the fighting, sets the pace.") if under else "") + "\n")
    who = "any class" if len(under) == len(CLASSES) else "most classes" if len(under) * 2 > len(CLASSES) else "some"
    return (f"\n## Full XP requires {CB.FULL_TIME_FACTOR_HOURS:g} hours per level, more than {who} spends "
            "fighting\n\n" + text + V.embed(chart))


def _rounds(a: CB.CombatAnalysis) -> str:
    chart = _lines(a, "rounds", "Rounds to kill a level-appropriate mob (population-weighted mean)", "Rounds")
    r = {c: a.series(c, "rounds") for c in CLASSES}
    top_band = C.bands()[-2]
    top_hp = C.median_or(m.mob.hit.average for m in a.mobs if C.usable_level(m.mob.level) in top_band)
    text = (f"At level 10 a knight needs about {r['knight'][10]:.0f} rounds ({r['knight'][10] * 3:.0f} s) and a mage "
            f"{r['mage'][10]:.0f}. By level 60 that's {r['knight'][60]:.0f} and {r['mage'][60]:.0f} rounds, and at "
            f"{C.HERO_LEVEL} {r['knight'][C.HERO_LEVEL]:.0f} and {r['mage'][C.HERO_LEVEL]:.0f}. Mob HP grows faster "
            f"than player damage: the median combat mob at levels {top_band.label} has about {top_hp:,.0f} HP. "
            "Haste (an extra attack per round) and spells would shorten these a lot.\n")
    return (f"\n## Fights stretch to {r['knight'][C.HERO_LEVEL]:.0f}+ rounds by level {C.HERO_LEVEL}\n\n" + text
            + V.embed(chart))


def _deadly(a: CB.CombatAnalysis) -> str:
    chart = _lines(a, "deadly_share", "Share of level-appropriate mobs that would out-damage you in a straight fight",
                   "Deadly share", fmt=".0%")
    first = {}
    run = 5  # the majority must hold for this many consecutive levels (ignores single noisy levels)
    for c in CLASSES:
        s = a.series(c, "deadly_share")
        first[c] = next((lvl for lvl in C.LEVELS
                         if lvl > 5 and all((s.get(x) or 0) >= 0.5 for x in range(lvl, min(lvl + run, 92)))), None)
    known = {c: lvl for c, lvl in first.items() if lvl}
    text = ("A mob counts as deadly when its expected damage over the whole fight exceeds your maximum HP. "
            + ("More than half the mobs at your level are deadly in melee, for good, for "
               + ", ".join(f"{c} from level {lvl}" for c, lvl in sorted(known.items(), key=lambda kv: kv[1]))
               + ". " if known else "No class reaches a majority of deadly mobs. ")
            + "Casters really fight with spells and buffs (sanctuary alone cuts damage taken to 62%), so this marks "
            "where melee stops being an option, not where the class fails.\n")
    worst = min(known, key=known.get) if known else CLASSES[0]
    title = (f"Melee turns deadly for {worst}s from level {known[worst]}" if known
             else "Melee stays survivable for every class")
    return f"\n## {title}\n\n" + text + V.embed(chart)


def _accuracy(a: CB.CombatAnalysis) -> str:
    rows = []
    for c in CLASSES:
        for lvl, v in a.series(c, "hit_pc").items():
            if v is not None:
                rows.append({"class": c, "level": lvl, "value": v, "who": "you hit it"})
    for lvl, v in a.series("knight", "hit_mob").items():
        if v is not None:
            rows.append({"class": "mob vs knight", "level": lvl, "value": v, "who": "it hits you"})
    chart = V.spec(rows, title="Chance per swing to land a blow (after parry, dodge and block)",
                   mark={"type": "line"},
                   encoding={"x": V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                             "y": V.quant("value", "Chance", axis={"format": "%"}),
                             "color": V.nominal("class", "", {**V.CLASS_COLOURS, "mob vs knight": "#9a8b7e"},
                                                CLASSES + ["mob vs knight"]),
                             "strokeDash": {"field": "who", "type": "nominal", "title": "",
                                            "scale": {"domain": ["you hit it", "it hits you"],
                                                      "range": [[1, 0], [5, 3]]},
                                            "legend": {"symbolType": "stroke"}},
                             "tooltip": [{"field": "class"}, {"field": "level"},
                                         {"field": "value", "title": "Chance", "format": ".0%"}]})
    hp = a.series("mage", "hit_pc")
    low_lvl = min((lvl for lvl in C.LEVELS if lvl >= 20 and hp[lvl]), key=lambda lvl: hp[lvl])
    mob = a.series("knight", "hit_mob")
    text = (f"Players land most blows early, but accuracy dips through the middle levels: a mage's chance bottoms "
            f"out around level {low_lvl} at {hp[low_lvl]:.0%}. Mob stats are `11 + level/4`, so their dex reaches "
            "the 20s by level 40 and the dex bonus to their AC (`dex_app`) grows faster than a player's to-hit. "
            f"Mobs, meanwhile, rarely hit a fully armoured player: about {min(v for v in mob.values() if v):.0%}–"
            f"{max(v for v in mob.values() if v):.0%} per swing against a knight, because player AC from gear dwarfs "
            "anything mobs wear.\n")
    return (f"\n## Players' accuracy dips in the middle levels as mob dex climbs\n\n" + text + V.embed(chart)
            + "".join(V.details(f"Details: {c} by level band", a.class_table(c)) for c in CLASSES))
