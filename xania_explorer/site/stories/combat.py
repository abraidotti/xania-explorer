"""Combat & experience page."""

from __future__ import annotations

import math

from ...areafile.world import World
from ...assess import combat as CB
from ...assess import common as C
from ...source.cpp_tables import CLASSES
from .. import charts as V
from .common import HIGHLIGHT, MUTED, _list, _plural, by_area, edit_effort, finding, rec, src_link, story

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
                "each class with the best gear the world offers at that level. Mobs' casting and breath specials "
                + ("are included" if a.specials else "aren't included (no `src/special.cpp`)")
                + ". Each fight is straight melee against one mob, except in two sections: casters fighting with "
                "their spells and buffs, and group fights. Resistances and mob skills like bash aren't modelled. "
                "See the Method at the end.\n")
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
                                   f"{CB.FULL_TIME_FACTOR_HOURS * (C.HERO_LEVEL - 1):.0f} h clock)", impact=3,
                             recs=[_r_clock(a, hours)]),
                     finding("combat.fight-length", _rounds(a),
                             metric=round(a.series("knight", "rounds")[C.HERO_LEVEL] or 0),
                             label=f"rounds for a knight to kill a level-{C.HERO_LEVEL} mob", impact=2,
                             recs=[_r_rounds(a)]),
                     finding("combat.deadly-melee", _deadly(a), metric=min(onsets) if onsets else None,
                             label="level from which melee turns deadly for the weakest class", better="higher",
                             impact=2),
                     finding("combat.accuracy-dip", _accuracy(a), metric=round(100 * min(hit)) if hit else None,
                             label="% lowest chance per swing for a mage (level 20+)", better="higher"),
                     finding("combat.mob-spells", _mob_spells(a), metric=_spell_peak(a)[1],
                             label="% of mob damage from spells and breath, at its peak level (knight)",
                             better="none", issue=False),
                     finding("combat.with-spells", _with_spells(a),
                             metric=round(_caster_hours(a, "mage"), 1) if _caster_play(a) else None,
                             label="hours of combat to hero for a mage fighting with its spells and buffs",
                             better="lower", issue=False),
                     finding("combat.group-fights", _groups(a), metric=_group_jump(a)[1],
                             label="percentage points more mobs deadly once helpers join, at the worst level (knight)",
                             impact=2, issue=bool(_traps(a)), recs=[_r_traps(a)]),
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
    layer = {"data": {"values": clock}, "mark": {"type": "line", "strokeDash": [5, 4], "color": "#a8998b"},
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
    text = ("A mob counts as deadly when its expected damage over the whole fight, melee plus any spells or breath, "
            "exceeds your maximum HP. "
            + ("More than half the mobs at your level are deadly in melee, for good, for "
               + ", ".join(f"{c} from level {lvl}" for c, lvl in sorted(known.items(), key=lambda kv: kv[1]))
               + ". " if known else "No class reaches a majority of deadly mobs. ")
            + "Casters really fight with spells and buffs (sanctuary alone cuts damage taken to 62.5%), so this "
            "marks where melee stops being an option, not where the class fails: see "
            "[casters with their spells and buffs](#combat-with-spells).\n")
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
                             "color": V.nominal("class", "", {**V.CLASS_COLOURS, "mob vs knight": "#a8998b"},
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


# -- recommendations -------------------------------------------------------------------------------------
def _r_clock(a: CB.CombatAnalysis, hours: dict[str, float]):
    slowest = max(hours.values())
    full = 4 * CB.FULL_TIME_FACTOR_HOURS  # quarter-hours per level for full credit (6)
    # the smallest whole number of quarter-hours per level that still covers the slowest class's combat time
    needed = max(2, math.ceil(4 * slowest / (C.HERO_LEVEL - 1)))
    if needed >= full:
        return None
    clock_after = needed / 4 * (C.HERO_LEVEL - 1)
    return rec("combat.xp-clock.shorten", f"Lower full-XP credit from {full:g} to {needed} quarter-hours per level",
               f"In `xp_compute` ({src_link(a.world, 'fight.cpp', 'std::clamp(time_per_level, 2, 6)')}), change "
               f"the clamp's upper bound and the divisor (`/ 6`) from {full:g} to **{needed}**, and cap the "
               f"below-15 floor (`8 - base_level`) at {needed} too, or levels 2–{8 - needed - 1} would earn more than "
               f"full XP. {needed} is the smallest value that still covers the slowest class's combat time "
               f"({slowest:.0f} h to hero).",
               f"Played time needed for full XP to hero: **{CB.FULL_TIME_FACTOR_HOURS * (C.HERO_LEVEL - 1):.0f} h → "
               f"{clock_after:.0f} h**. That's still more than any class spends fighting ({slowest:.0f} h at most), "
               "so a player who fights continuously still gets full XP per kill.",
               effort=1, kind="code")


FIGHT_TARGET = 2.0  # recommend capping fights at this multiple of the level-30 length (a judgement)


def _r_rounds(a: CB.CombatAnalysis):
    r = a.series("knight", "rounds")
    base = r.get(30)
    if not base:
        return None
    target = FIGHT_TARGET * base
    over = [lvl for lvl, v in r.items() if v and v > target]
    if not over:
        return None
    first = over[0]
    mobs = [m for m in a.mobs if C.usable_level(m.mob.level) >= first]
    factor = target / r[C.HERO_LEVEL] if r.get(C.HERO_LEVEL) else None
    areas = [a.world.mob_area[m.mob.vnum].name for m in mobs if m.mob.vnum in a.world.mob_area]
    return rec("combat.fight-length.mob-hp", f"Scale down the HP of mobs above level {first - 1}",
               f"Knights need more than {FIGHT_TARGET:g}× their level-30 fight length (about {base:.0f} rounds) from "
               f"level {first}. Rounds to kill scale directly with mob HP, so lowering the hit dice of the "
               f"{len(mobs)} combat mobs from level {first} up ({by_area(areas, 3)}) shortens fights in proportion. "
               f"At level {C.HERO_LEVEL} that's about {factor:.0%} of today's HP." if factor else "",
               f"Knight fights at level {C.HERO_LEVEL}: **{r[C.HERO_LEVEL]:.0f} → {target:.0f} rounds**, and combat "
               "time per level falls by the same proportion. Mobs also deal less total damage, so melee gets "
               "safer.",
               effort=edit_effort(len(set(areas)), len(mobs)))


def _spell_share(a: CB.CombatAnalysis, cls: str, level: int) -> tuple[float, float]:
    """(share of mob damage from specials, share of the mob population with a damaging special) at a level."""
    r = a.results[(cls, level)]
    melee, spell = r.weighted_mean("mob_dpr") or 0, r.weighted_mean("spell_dpr") or 0
    casters = sum(m.info.population for m, f in r.fights if f.spell_dpr > 0) / r.weight if r.weight else 0
    return (spell / (melee + spell) if melee + spell else 0.0), casters


def _spell_peak(a: CB.CombatAnalysis) -> tuple[int, int | None]:
    if not a.specials:
        return 0, None
    level = max(C.LEVELS, key=lambda lvl: _spell_share(a, "knight", lvl)[0])
    return level, round(100 * _spell_share(a, "knight", level)[0])


def _mob_spells(a: CB.CombatAnalysis) -> str:
    if not a.specials:
        return ("\n## Mob spells and breath aren't modelled for this checkout\n\n"
                "It has no `src/special.cpp` (or `src/magic.cpp`), so the damage above is melee only.\n")
    from collections import Counter

    rows = []
    for lvl in C.LEVELS:
        share, casters = _spell_share(a, "knight", lvl)
        rows += [{"level": lvl, "what": "share of mob damage", "value": round(share, 3)},
                 {"level": lvl, "what": "share of mobs with a damaging special", "value": round(casters, 3)}]
    chart = V.spec(rows, title="Mob spells and breath against a knight, at each level",
                   mark={"type": "line"},
                   encoding={"x": V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                             "y": V.quant("value", "Share", axis={"format": ".0%"}),
                             "color": V.nominal("what", "", {"share of mob damage": HIGHLIGHT,
                                                             "share of mobs with a damaging special": "#3f88c5"}),
                             "tooltip": [{"field": "what", "title": ""}, {"field": "level", "title": "Level"},
                                         {"field": "value", "title": "Share", "format": ".0%"}]})
    peak, pct = _spell_peak(a)
    kinds = Counter(m.special for m in a.mobs if m.special and m.special in a.specials.names)
    lvls = (20, 40, 60, 80, C.HERO_LEVEL)
    text = (f"{sum(kinds.values())} combat mobs cast or breathe through a special procedure, most often "
            + _list([f"`{k}` ({n})" for k, n in kinds.most_common(3)])
            + ". They act every 4 seconds on top of melee, cast at the mob's own level and use no mana. Against a "
            "knight, they add "
            + _list([f"{100 * _spell_share(a, 'knight', lvl)[0]:.0f}% at level {lvl}" for lvl in lvls])
            + f" of the damage mobs deal, peaking at **{pct}%** at level {peak}. The share depends on how many "
            "level-appropriate mobs have one (blue).\n")
    return (f"\n## Mob spells and breath add up to {pct}% of the damage mobs deal\n\n" + text + V.embed(chart))


# -- group fights -------------------------------------------------------------------------------------------
TRAP_GAP = 10  # a helper this many levels above the mob it guards makes a level trap


def _deadly_shares(a: CB.CombatAnalysis, cls: str, level: int, skip: frozenset = frozenset()) -> tuple[float, float]:
    """(deadly share fighting each mob alone, deadly share counting its helpers), population-weighted.
    ``skip`` = (mob vnum, helper vnum) pairs to leave out, to simulate separating them."""
    r = a.results[(cls, level)]
    p = a.player(cls, level)
    if not r.weight:
        return 0.0, 0.0
    alone = sum(m.info.population for m, f in r.fights if f.damage_taken >= p.hp) / r.weight
    if skip:
        saved = {}
        for mob, helper in skip:
            saved.setdefault(mob, a.helpers[mob])
            a.helpers[mob] = [(h, n) for h, n in a.helpers[mob] if h.mob.vnum != helper]
    try:
        grouped = sum(m.info.population for m, f in r.fights if a.encounter_damage(p, m, f) >= p.hp) / r.weight
    finally:
        if skip:
            a.helpers.update(saved)
    return alone, grouped


def _group_jump(a: CB.CombatAnalysis, skip: frozenset = frozenset()) -> tuple[int, int]:
    """(level, percentage points) where helpers raise the knight's deadly share the most."""
    jumps = {lvl: _deadly_shares(a, "knight", lvl, skip) for lvl in C.LEVELS}
    level = max(C.LEVELS, key=lambda lvl: (jumps[lvl][1] - jumps[lvl][0], -lvl))
    return level, round(100 * (jumps[level][1] - jumps[level][0]))


def _traps(a: CB.CombatAnalysis) -> list[tuple[CB.MobFighter, CB.MobFighter]]:
    """(mob, helper) pairs where the helper is at least TRAP_GAP levels above the mob it guards."""
    out = []
    for m in a.mobs:
        for h, _ in a.helpers.get(m.mob.vnum, []):
            if h.mob.level - m.mob.level >= TRAP_GAP:
                out.append((m, h))
    return sorted(out, key=lambda mh: (mh[0].mob.level, mh[0].mob.vnum, mh[1].mob.vnum))


def _groups(a: CB.CombatAnalysis) -> str:
    rows = []
    for lvl in C.LEVELS:
        alone, grouped = _deadly_shares(a, "knight", lvl)
        r = a.results[("knight", lvl)]
        helped = sum(m.info.population for m, _ in r.fights if a.helpers.get(m.mob.vnum)) / r.weight if r.weight else 0
        rows += [{"level": lvl, "what": "deadly, fought alone", "value": round(alone, 3)},
                 {"level": lvl, "what": "deadly, with helpers", "value": round(grouped, 3)},
                 {"level": lvl, "what": "mobs with helpers", "value": round(helped, 3)}]
    chart = V.spec(rows, title="Knight: share of level-appropriate mobs that are deadly, alone and with helpers",
                   mark={"type": "line"},
                   encoding={"x": V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                             "y": V.quant("value", "Share", axis={"format": ".0%"}),
                             "color": V.nominal("what", "", {"deadly, fought alone": MUTED,
                                                             "deadly, with helpers": HIGHLIGHT,
                                                             "mobs with helpers": "#3f88c5"}),
                             "tooltip": [{"field": "what", "title": ""}, {"field": "level", "title": "Level"},
                                         {"field": "value", "title": "Share", "format": ".0%"}]})
    with_helpers = [m for m in a.mobs if a.helpers.get(m.mob.vnum)]
    level, jump = _group_jump(a)
    alone, grouped = _deadly_shares(a, "knight", level)
    traps = _traps(a)
    text = (f"{_plural(len(with_helpers), 'combat mob')} spawn next to mobs that join a fight against them: the same "
            "prototype (`assist_vnum`), the same race (`assist_race`, which some races grant to all their mobs), "
            "the same alignment (`assist_align`) or anyone (`assist_all`). Each joins with a coin flip per round, "
            f"and then has to be fought too. The worst level is **{level}**, where helpers take the share of mobs a "
            f"knight can't survive from {alone:.0%} to **{grouped:.0%}**. ")
    if traps:
        text += (f"{_plural(len(traps), 'pairing is a level trap', 'pairings are level traps')}: a helper at least "
                 f"{TRAP_GAP} levels above the mob it guards, so a player hunting at the mob's level pulls in "
                 "something far beyond them. For example: "
                 + _list([f"{m.mob.short_descr} ({m.mob.level}) with {h.mob.short_descr} ({h.mob.level}) in "
                          f"{m.info.area.name}" for m, h in traps[:3]]) + ".")
    text += " Mobs wander, so this is the fight where they spawn.\n"
    table = C.table(["Mob", "Lvl", "Helper", "Lvl", "Flags", "Area"],
                    [[f"#{m.mob.vnum} {m.mob.short_descr}", m.mob.level, f"#{h.mob.vnum} {h.mob.short_descr}",
                      h.mob.level, ", ".join(sorted(x for x in h.off if x.startswith("Assist"))), m.info.area.name]
                     for m, h in traps])
    title = (f"Helpers make {jump} percentage points more mobs deadly at level {level}" if jump
             else "Mobs that help each other barely change the odds")
    return (f"\n## {title}\n\n" + text + V.embed(chart)
            + (V.details(f"Details: the {len(traps)} level traps", table) if traps else ""))


def _r_traps(a: CB.CombatAnalysis):
    traps = _traps(a)
    if not traps:
        return None
    level, jump = _group_jump(a)
    after_level, after = _group_jump(a, frozenset((m.mob.vnum, h.mob.vnum) for m, h in traps))
    areas = [m.info.area.name for m, _ in traps]
    guarded = len({m.mob.vnum for m, _ in traps})
    return rec("combat.group-fights.separate-traps",
               f"Separate {_plural(guarded, 'low-level mob')} from the much stronger helpers guarding them",
               f"For each pair in the table (" + by_area(areas) + "), move the helper to another room, re-level one "
               "of them, or drop the helper's assist flag (if it comes from the race, `assist_race`, give the "
               "helper a different race).",
               f"The biggest jump in deadly mobs from helpers falls from **{jump} points at level {level}** to "
               f"{after} points (at level {after_level}).",
               effort=edit_effort(len(set(areas)), len(traps)))


# -- casters with their spells and buffs ----------------------------------------------------------------------
CASTERS = ("mage", "cleric")


def _caster_play(a: CB.CombatAnalysis) -> dict[tuple[str, int], tuple[float, float, float]] | None:
    """(deadly share, mean rounds, combat minutes for the level) per caster and level, fighting with the default
    package's buffs and best attack spell (Skills), a full mana bar per fight. None without magic.cpp."""
    if "_caster_play" in a.__dict__:
        return a.__dict__["_caster_play"]
    out = None
    if (a.world.src_dir / "magic.cpp").exists():
        from ...assess import skills as S

        sk = S.analyse(a.world)
        out = {}
        for cls in CASTERS:
            for lvl in C.LEVELS:
                r = a.results[(cls, lvl)]
                if not r.weight:
                    out[(cls, lvl)] = (0.0, 0.0, 0.0)
                    continue
                p = a.player(cls, lvl, buffed=True)
                mana = a.chars.build("human", cls).at(lvl).mana
                fights = [(m, a.fight_with_spells(p, m, sk.spells[cls][lvl], mana)) for m, _ in r.fights]
                deadly = sum(m.info.population for m, f in fights if f.damage_taken >= p.hp) / r.weight
                rounds = sum(m.info.population * f.rounds for m, f in fights) / r.weight
                kills = r.kills_per_level or 0
                out[(cls, lvl)] = (deadly, rounds, kills * rounds * CB.ROUND_SECONDS / 60)
    a.__dict__["_caster_play"] = out
    return out


def _caster_hours(a: CB.CombatAnalysis, cls: str) -> float | None:
    play = _caster_play(a)
    return sum(play[(cls, lvl)][2] for lvl in C.LEVELS) / 60 if play else None


def _with_spells(a: CB.CombatAnalysis) -> str:
    play = _caster_play(a)
    if not play:
        return ("\n## Casters' own spells aren't modelled for this checkout\n\n"
                "It has no `src/magic.cpp`, so the numbers above are straight melee for every class.\n")
    rows = []
    for cls in CASTERS:
        melee = a.series(cls, "rounds")
        for lvl in C.LEVELS:
            if melee.get(lvl):
                rows.append({"class": cls, "level": lvl, "how": "straight melee", "rounds": round(melee[lvl], 1)})
            rows.append({"class": cls, "level": lvl, "how": "spells and buffs", "rounds": round(play[(cls, lvl)][1], 1)})
    chart = V.spec(rows, title="Rounds to kill a level-appropriate mob: spells and buffs (solid) vs straight melee "
                               "(dashed)", mark={"type": "line"},
                   encoding={"x": V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False}),
                             "y": V.quant("rounds", "Rounds"),
                             "color": V.nominal("class", "Class", V.CLASS_COLOURS, list(CASTERS)),
                             "strokeDash": {"field": "how", "type": "nominal", "title": "",
                                            "scale": {"domain": ["spells and buffs", "straight melee"],
                                                      "range": [[1, 0], [5, 3]]}},
                             "tooltip": V.tooltip(("class", "Class"), ("how", "How"), ("level", "Level"),
                                                  ("rounds", "Rounds"))})
    parts = []
    for cls in CASTERS:
        buffs = a.buffs(cls, C.HERO_LEVEL).names
        melee_h, spell_h = a.hours_to_hero(cls), _caster_hours(a, cls)
        onset = next((lvl for lvl in C.LEVELS if lvl > 5 and all(
            play[(cls, x)][0] >= 0.5 for x in range(lvl, min(lvl + DEADLY_RUN, C.HERO_LEVEL + 1)))), None)
        parts.append(f"A **{cls}** keeps up {_list(list(buffs))} once learned. Fighting with them and its best attack "
                     f"spell, it needs about {play[(cls, 60)][1]:.0f} rounds per kill at level 60 instead of "
                     f"{a.series(cls, 'rounds')[60]:.0f}, and "
                     + (f"most mobs at its level turn deadly only from level {onset}" if onset
                        else "no level has a majority of deadly mobs")
                     + f" (straight melee: {deadly_onset(a, cls) or 'never'}). Combat time to hero: "
                     f"**{spell_h:.0f} h** instead of {melee_h:.0f} h.")
    ratio = min(a.series(c, "rounds")[C.HERO_LEVEL] / play[(c, C.HERO_LEVEL)][1] for c in CASTERS)
    text = (" ".join(parts) + " These are best-case numbers: buffs from the default package are assumed kept up "
            "(recast between fights), every fight starts with a full mana bar (resting in between, which isn't "
            "counted), and the spell is the one Skills & spells ranks best. Knights and barbarians have no buffs or "
            "attack spells in their default package, so their numbers above already are how they fight.\n")
    return (f"\n## With their spells and buffs, casters kill at least {ratio:.1f}× faster by level {C.HERO_LEVEL}\n\n"
            + text + V.embed(chart))
