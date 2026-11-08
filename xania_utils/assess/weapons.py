"""Weapon availability and quality across levels 1–91, per class.

Questions answered:
- How many weapons become usable at each level, of which types?
- At each level, what is the best weapon a character can use, and how close
  is it to the balance cap (entity_balance.cpp)?
- Does one class have an easier time finding a weapon it is good with?
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..areafile import flags as F
from ..areafile.model import Obj
from ..areafile.world import World
from ..source.cpp_tables import CLASSES, load_skills, starting_skills
from . import common as C
from .sources import ObjSource, object_sources

# Weapon type order (Weapon.hpp minus exotic, which has no skill: get_weapon_skill gives
# every PC min(2*level, 90)% with it, so no class is better or worse at it).
SKILLED_TYPES = ["sword", "dagger", "spear", "mace", "axe", "flail", "whip", "polearm"]
ALL_TYPES = SKILLED_TYPES + ["exotic"]
EASY_DIFFICULTY = 3  # skill difficulty <= this counts as "easy to train"
TWO_HANDS_FLAG = 1 << 5  # WeaponFlag::TwoHands = F
TWO_HANDS_WEAR = 1 << 15  # ObjectWearFlag::TwoHands = P


def allowed_average(level: int, two_handed: bool) -> float:
    """entity_balance.cpp report_object: allowed average damage for a weapon."""
    allowed = level // 2 + 4
    if two_handed:
        allowed += max(1, allowed // 20)
    return allowed


@dataclass
class Weapon:
    obj: Obj
    type: str
    sources: list[ObjSource]

    @property
    def vnum(self) -> int:
        return self.obj.vnum

    @property
    def level(self) -> int:
        return C.usable_level(self.obj.level)

    @property
    def average(self) -> float:
        n, s = int(self.obj.values[1]), int(self.obj.values[2])
        return (n * s + n) / 2  # same integer-ish formula as entity_balance.cpp

    @property
    def cpp_average(self) -> int:
        """entity_balance.cpp's integer version, used for the cap check."""
        n, s = int(self.obj.values[1]), int(self.obj.values[2])
        return (n * s + n) // 2

    @property
    def over_cap(self) -> bool:
        return self.cpp_average > self.cap

    @property
    def two_handed(self) -> bool:
        return bool(int(self.obj.values[4]) & TWO_HANDS_FLAG) and bool(self.obj.wear_flags & TWO_HANDS_WEAR)

    @property
    def cap(self) -> float:
        return allowed_average(self.obj.level, self.two_handed)

    @property
    def obtainable(self) -> bool:
        return bool(self.sources)

    @property
    def source_kinds(self) -> list[str]:
        return sorted({s.kind for s in self.sources})

    @property
    def buyable(self) -> bool:
        return any(s.kind == "shop" for s in self.sources)

    @property
    def best_drop_pct(self) -> int | None:
        drops = [s.drop_pct for s in self.sources if s.kind == "mob" and s.drop_pct is not None]
        return max(drops) if drops else None

    @property
    def easiest_mob_level(self) -> int | None:
        levels = [s.mob_level for s in self.sources if s.kind == "mob" and s.mob_level is not None]
        return min(levels) if levels else None


@dataclass
class ClassProfile:
    name: str
    starting: list[str]  # weapon types known at creation (basics + default package)
    easy: list[str]  # weapon types with difficulty <= EASY_DIFFICULTY
    difficulty: dict[str, int]


def class_profiles(src_dir: Path | None = None) -> list[ClassProfile]:
    skills = load_skills(src_dir)
    out = []
    for cls in CLASSES:
        start = starting_skills(cls, src_dir)
        diff = {t: skills[t].difficulty(cls) for t in SKILLED_TYPES}
        out.append(ClassProfile(cls, [t for t in SKILLED_TYPES if t in start],
                                [t for t in SKILLED_TYPES if 0 < diff[t] <= EASY_DIFFICULTY], diff))
    return out


def collect(world: World) -> list[Weapon]:
    sources = object_sources(world)
    weapons = []
    for obj in world.objects.values():
        if obj.type_name != "Weapon":
            continue
        wtype = str(obj.values[0]).lower()
        weapons.append(Weapon(obj, wtype if wtype in ALL_TYPES else "exotic", sources.get(obj.vnum, [])))
    return sorted(weapons, key=lambda w: (w.level, w.vnum))


def best_by_level(weapons: list[Weapon], types: set[str]) -> dict[int, float | None]:
    out = {}
    best = None
    pool = sorted((w for w in weapons if w.type in types), key=lambda w: w.level)
    i = 0
    for lvl in C.LEVELS:
        while i < len(pool) and pool[i].level <= lvl:
            best = max(best or 0, pool[i].average)
            i += 1
        out[lvl] = best
    return out


# -- report -----------------------------------------------------------------
def render(world: World) -> str:
    weapons = collect(world)
    mortal = [w for w in weapons if w.level <= C.HERO_LEVEL]
    got = [w for w in mortal if w.obtainable]
    profiles = class_profiles(world.src_dir)
    bands = C.bands()

    best_any = best_by_level(got, set(SKILLED_TYPES))
    best_start = {p.name: best_by_level(got, set(p.starting)) for p in profiles}
    best_easy = {p.name: best_by_level(got, set(p.easy)) for p in profiles}

    out = [C.GENERATED_NOTE, "\n# Weapons: availability by level and class\n\n"]
    out.append(_findings(got, profiles, bands, best_any, best_start))
    out.append(_method(profiles, weapons, mortal, got))

    # 1. Supply by band and type
    out.append("\n## 1. New weapons per level band, by type\n\n"
               "Obtainable weapons that become usable in each band (a character can't wield an object above "
               "their level, act_obj.cpp:137).\n\n")
    rows = []
    totals = []
    for b in bands:
        in_band = [w for w in got if w.level in b]
        counts = Counter(w.type for w in in_band)
        totals.append((b.label, len(in_band)))
        rows.append([b.label] + [counts.get(t, 0) for t in ALL_TYPES] + [len(in_band),
                                                                           sum(w.buyable for w in in_band)])
    rows.append(["**all**"] + [sum(1 for w in got if w.type == t) for t in ALL_TYPES]
                + [len(got), sum(w.buyable for w in got)])
    out.append(C.table(["Levels"] + ALL_TYPES + ["total", "buyable"], rows))
    out.append("\n" + C.histogram(totals))
    out.append(f"\nSpread across bands: {C.Spread.of([v for _, v in totals]).describe()}.\n")

    # 2. Class access by band
    out.append("\n## 2. New weapons per band that each class is good with\n\n"
               "*Start* = weapon types the class knows at creation; *easy* = types it trains cheaply "
               f"(difficulty ≤ {EASY_DIFFICULTY}). See Method.\n\n")
    headers = ["Levels"] + [f"{p.name} start" for p in profiles] + [f"{p.name} easy" for p in profiles]
    rows = []
    for b in bands:
        in_band = [w for w in got if w.level in b]
        rows.append([b.label] + [sum(w.type in p.starting for w in in_band) for p in profiles]
                    + [sum(w.type in p.easy for w in in_band) for p in profiles])
    rows.append(["**all**"] + [sum(w.type in p.starting for w in got) for p in profiles]
                + [sum(w.type in p.easy for w in got) for p in profiles])
    out.append(C.table(headers, rows))
    out.append("\nBands with **no** new weapon of a class's starting types:\n\n")
    for p in profiles:
        empty = [b.label for b in bands if not any(w.type in p.starting and w.level in b for w in got)]
        out.append(f"- **{p.name}** ({', '.join(p.starting)}): {len(empty)}/{len(bands)} bands"
                   + (f" — {', '.join(empty)}" if empty else "") + "\n")

    # 3. Damage progression per level
    out.append("\n## 3. Best usable weapon at each level\n\n"
               "Average damage (dice average, before skill/damroll) of the best obtainable weapon a character "
               "of that level can wield. *cap* is the balance allowance for a one-handed weapon of that level "
               "(`level/2 + 4`). Class columns use the class's starting types.\n\n")
    rows = []
    for lvl in C.LEVELS:
        new = sum(1 for w in got if w.level == lvl)
        rows.append([lvl, new, allowed_average(lvl, False), best_any[lvl]]
                    + [best_start[p.name][lvl] for p in profiles])
    out.append(C.table(["Lvl", "new", "cap", "best (any type)"] + [p.name for p in profiles], rows))

    out.append("\n### Best weapon as a share of the cap, by band\n\n"
               "Ratio of the best usable weapon (at the top of the band) to the cap at that level. "
               "Below ~0.8 means characters are noticeably under-equipped for their level.\n\n")
    rows = []
    for b in bands:
        cap = allowed_average(b.hi, False)
        def ratio(series):
            v = series[b.hi]
            return None if v is None else v / cap
        rows.append([b.label, ratio(best_any)] + [ratio(best_start[p.name]) for p in profiles]
                    + [ratio(best_easy[p.name]) for p in profiles])
    out.append(C.table(["Levels", "any"] + [f"{p.name} start" for p in profiles]
                       + [f"{p.name} easy" for p in profiles], rows))

    # 4. Plateaus
    out.append("\n## 4. Longest stretches without an upgrade\n\n"
               "Level ranges over which a class's best starting-type weapon doesn't improve (top 3).\n\n")
    rows = []
    for p in profiles:
        for lo, hi, val in C.runs_without_increase(best_start[p.name])[:3]:
            rows.append([p.name, f"{lo}–{hi}", hi - lo + 1, val])
    for lo, hi, val in C.runs_without_increase(best_any)[:3]:
        rows.append(["(any type)", f"{lo}–{hi}", hi - lo + 1, val])
    out.append(C.table(["Class", "Levels", "Length", "Best avg during"], rows))

    # 5. Sources
    out.append("\n## 5. How weapons are obtained, by band\n\n"
               "A weapon can have several sources. *Mob drop %* is the best drop chance among its mob sources; "
               "*mob − weapon level* is how much higher the easiest carrier is than the weapon itself.\n\n")
    rows = []
    for b in bands:
        in_band = [w for w in got if w.level in b]
        kinds = Counter(k for w in in_band for k in w.source_kinds)
        drops = [w.best_drop_pct for w in in_band if w.best_drop_pct is not None]
        gaps = [w.easiest_mob_level - w.obj.level for w in in_band if w.easiest_mob_level is not None]
        rows.append([b.label, len(in_band), kinds.get("shop", 0), kinds.get("mob", 0),
                     kinds.get("floor", 0) + kinds.get("container", 0),
                     C.median_or(drops), C.median_or(gaps), max(gaps, default=None)])
    out.append(C.table(["Levels", "weapons", "buyable", "mob drop", "floor/container", "median mob drop %",
                        "median mob − weapon lvl", "max mob − weapon lvl"], rows))

    # 6. Balance violations
    over = sorted((w for w in weapons if w.over_cap), key=lambda w: (-(w.average - w.cap), w.vnum))
    out.append(f"\n## 6. Weapons over the damage cap ({len(over)})\n\n"
               "`average > level/2 + 4` (+5% for two-handers), the check `immworth` reports as "
               "\"average damage too high\".\n\n")
    if over:
        out.append(C.table(["Vnum", "Weapon", "Area", "Type", "Lvl", "Dice", "Avg", "Cap", "Over by", "Sources"],
                           [[w.vnum, w.obj.short_descr, world.obj_area[w.vnum].name, w.type, w.obj.level,
                             f"{w.obj.values[1]}d{w.obj.values[2]}", w.average, w.cap, w.average - w.cap,
                             ", ".join(w.source_kinds) or "none"] for w in over]))

    # 7. Unobtainable / above-hero
    lost = [w for w in mortal if not w.obtainable]
    out.append(f"\n## 7. Weapons with no reset source ({len(lost)})\n\n"
               "Not placed by any reset, so not available in normal play (they may come from mobprogs, "
               "specials or immortals).\n\n")
    if lost:
        out.append(C.table(["Vnum", "Weapon", "Area", "Type", "Lvl", "Avg"],
                           [[w.vnum, w.obj.short_descr, world.obj_area[w.vnum].name, w.type, w.obj.level, w.average]
                            for w in lost]))
    high = [w for w in weapons if w.level > C.HERO_LEVEL]
    if high:
        out.append(f"\n{len(high)} weapon(s) above level {C.HERO_LEVEL} are excluded from the analysis.\n")
    return "".join(out)


def _method(profiles: list[ClassProfile], weapons, mortal, got) -> str:
    rows = [[p.name, ", ".join(p.starting), ", ".join(p.easy)]
            + [p.difficulty[t] for t in SKILLED_TYPES] for p in profiles]
    return (
        "\n## Method\n\n"
        f"- **Weapons**: {len(weapons)} weapon prototypes; {len(mortal)} at level ≤ {C.HERO_LEVEL}; "
        f"**{len(got)} obtainable** (placed by at least one reset: shop stock, mob drop, floor or container). "
        "Level-0 weapons count as level 1.\n"
        "- **Usable at level L** = obtainable and weapon level ≤ L.\n"
        "- **Class affinity.** Every class can learn every weapon from level 1 "
        "(SkillTables.cpp), but at different *difficulty* (the class rating): it's the creation-point cost "
        "and divides both practice gains (act_info.cpp:1604) and learn-by-use chances (Learning.cpp:52). "
        "Weapon skill % multiplies both to-hit and damage (fight.cpp:452, :472), so a class is effectively "
        "weaker with a hard-to-train type. Two views per class:\n"
        "  - *start*: types granted at creation by `rom basics` + `<class> basics` + `<class> default` "
        "(knight default includes `weaponsmaster` = all types);\n"
        f"  - *easy*: types with difficulty ≤ {EASY_DIFFICULTY}.\n"
        "- **Exotic** weapons have no skill; every PC uses them at min(2 × level, 90)% (handler.cpp:108), so "
        "they're shown in supply tables but excluded from class comparisons.\n"
        "- Damage is the dice average `n × (s + 1) / 2`; skill, damroll, enhanced damage and weapon flags "
        "come on top (see the combat guide).\n\n"
        "Weapon difficulty by class (lower is easier; from `skill_table` ratings):\n\n"
        + C.table(["Class", "start", "easy"] + SKILLED_TYPES, rows)
    )


def _findings(got, profiles, bands, best_any, best_start) -> str:
    lines = ["## Headline findings\n\n"]
    totals = [sum(1 for w in got if w.level in b) for b in bands]
    half = sum(totals[: len(totals) // 3])
    lines.append(f"- **Supply is front-loaded**: {half} of {len(got)} obtainable weapons "
                 f"({half / len(got):.0%}) are usable by level {bands[len(bands) // 3 - 1].hi}; "
                 f"the thinnest band is {bands[totals.index(min(totals))].label} with {min(totals)}.\n")
    per_class = sorted(((sum(w.type in p.starting for w in got), p) for p in profiles), key=lambda x: x[0])
    lines.append("- **Class access** (obtainable weapons in starting types): "
                 + ", ".join(f"{p.name} {n}" for n, p in reversed(per_class)) + ".\n")
    for p in profiles:
        lo, hi, val = C.runs_without_increase(best_start[p.name])[0]
        first = next((lvl for lvl, v in best_start[p.name].items() if v is not None), None)
        lines.append(f"- **{p.name}**: first starting-type weapon at level {first}; longest plateau "
                     f"{lo}–{hi} ({hi - lo + 1} levels) at avg {val}; at level 91 best avg "
                     f"{best_start[p.name][C.HERO_LEVEL]} vs {best_any[C.HERO_LEVEL]} for any type.\n")
    return "".join(lines)


def write_csv(world: World, path: Path) -> None:
    C.write_csv(path, ["vnum", "name", "area", "type", "level", "dice", "average", "cap", "two_handed",
                       "flags", "sources", "buyable", "best_drop_pct", "easiest_mob_level"],
                [[w.vnum, w.obj.short_descr, world.obj_area[w.vnum].name, w.type, w.obj.level,
                  f"{w.obj.values[1]}d{w.obj.values[2]}", w.average, w.cap, int(w.two_handed),
                  " ".join(F.decode(int(w.obj.values[4]), F.WEAPON_FLAG)), " ".join(w.source_kinds),
                  int(w.buyable), w.best_drop_pct, w.easiest_mob_level] for w in collect(world)])


__all__ = ["render", "write_csv", "collect", "class_profiles", "allowed_average", "statistics"]
