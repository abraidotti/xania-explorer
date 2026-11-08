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


# -- analysis -----------------------------------------------------------------
@dataclass
class Plateau:
    cls: str
    lo: int
    hi: int
    value: float | None

    @property
    def length(self) -> int:
        return self.hi - self.lo + 1


class WeaponAnalysis:
    """Everything the weapons report says, computed once. Both the Markdown report
    (``render``) and the website page build on this."""

    def __init__(self, world: World):
        self.world = world
        self.weapons = collect(world)
        self.mortal = [w for w in self.weapons if w.level <= C.HERO_LEVEL]
        self.got = [w for w in self.mortal if w.obtainable]
        self.lost = [w for w in self.mortal if not w.obtainable]
        self.high = [w for w in self.weapons if w.level > C.HERO_LEVEL]
        self.over = sorted((w for w in self.weapons if w.over_cap), key=lambda w: (-(w.average - w.cap), w.vnum))
        self.profiles = class_profiles(world.src_dir)
        self.bands = C.bands()
        self.best_any = best_by_level(self.got, set(SKILLED_TYPES))
        self.best_start = {p.name: best_by_level(self.got, set(p.starting)) for p in self.profiles}
        self.best_easy = {p.name: best_by_level(self.got, set(p.easy)) for p in self.profiles}

    # -- derived facts used in findings ---------------------------------------
    def in_band(self, band: C.Band) -> list[Weapon]:
        return [w for w in self.got if w.level in band]

    @property
    def band_totals(self) -> list[int]:
        return [len(self.in_band(b)) for b in self.bands]

    @property
    def early_cutoff(self) -> int:
        """Top level of the first third of the bands (30 with 5-level bands)."""
        return self.bands[len(self.bands) // 3 - 1].hi

    @property
    def early_count(self) -> int:
        return sum(1 for w in self.got if w.level <= self.early_cutoff)

    def class_access(self, view: str = "start") -> dict[str, int]:
        attr = "starting" if view == "start" else "easy"
        return {p.name: sum(w.type in getattr(p, attr) for w in self.got) for p in self.profiles}

    def empty_bands(self, cls: str) -> list[C.Band]:
        p = next(p for p in self.profiles if p.name == cls)
        return [b for b in self.bands if not any(w.type in p.starting and w.level in b for w in self.got)]

    def plateaus(self, cls: str | None = None, top: int = 3) -> list[Plateau]:
        series = self.best_any if cls is None else self.best_start[cls]
        return [Plateau(cls or "(any type)", lo, hi, v) for lo, hi, v in C.runs_without_increase(series)[:top]]

    @property
    def worst_plateau(self) -> Plateau:
        return max((self.plateaus(p.name, 1)[0] for p in self.profiles), key=lambda x: (x.length, -x.lo))

    @property
    def last_buyable_level(self) -> int | None:
        return max((w.level for w in self.got if w.buyable), default=None)

    # -- tables ------------------------------------------------------------------
    def supply_table(self) -> str:
        rows = []
        for b in self.bands:
            ws = self.in_band(b)
            counts = Counter(w.type for w in ws)
            rows.append([b.label] + [counts.get(t, 0) for t in ALL_TYPES] + [len(ws), sum(w.buyable for w in ws)])
        rows.append(["**all**"] + [sum(1 for w in self.got if w.type == t) for t in ALL_TYPES]
                    + [len(self.got), sum(w.buyable for w in self.got)])
        return C.table(["Levels"] + ALL_TYPES + ["total", "buyable"], rows)

    def access_table(self) -> str:
        rows = []
        for b in self.bands:
            ws = self.in_band(b)
            rows.append([b.label] + [sum(w.type in p.starting for w in ws) for p in self.profiles]
                        + [sum(w.type in p.easy for w in ws) for p in self.profiles])
        start, easy = self.class_access("start"), self.class_access("easy")
        rows.append(["**all**"] + [start[p.name] for p in self.profiles] + [easy[p.name] for p in self.profiles])
        return C.table(["Levels"] + [f"{p.name} start" for p in self.profiles]
                       + [f"{p.name} easy" for p in self.profiles], rows)

    def empty_bands_list(self) -> str:
        out = []
        for p in self.profiles:
            empty = self.empty_bands(p.name)
            out.append(f"- **{p.name}** ({', '.join(p.starting)}): {len(empty)}/{len(self.bands)} bands"
                       + (f" — {', '.join(b.label for b in empty)}" if empty else "") + "\n")
        return "".join(out)

    def per_level_table(self) -> str:
        rows = [[lvl, sum(1 for w in self.got if w.level == lvl), allowed_average(lvl, False), self.best_any[lvl]]
                + [self.best_start[p.name][lvl] for p in self.profiles] for lvl in C.LEVELS]
        return C.table(["Lvl", "new", "cap", "best (any type)"] + [p.name for p in self.profiles], rows)

    def cap_ratio_table(self) -> str:
        def ratio(series, lvl):
            v = series[lvl]
            return None if v is None else v / allowed_average(lvl, False)

        rows = [[b.label, ratio(self.best_any, b.hi)] + [ratio(self.best_start[p.name], b.hi) for p in self.profiles]
                + [ratio(self.best_easy[p.name], b.hi) for p in self.profiles] for b in self.bands]
        return C.table(["Levels", "any"] + [f"{p.name} start" for p in self.profiles]
                       + [f"{p.name} easy" for p in self.profiles], rows)

    def plateau_table(self) -> str:
        rows = [[x.cls, f"{x.lo}–{x.hi}", x.length, x.value] for p in self.profiles for x in self.plateaus(p.name)]
        rows += [[x.cls, f"{x.lo}–{x.hi}", x.length, x.value] for x in self.plateaus(None)]
        return C.table(["Class", "Levels", "Length", "Best avg during"], rows)

    def source_rows(self) -> list[dict]:
        rows = []
        for b in self.bands:
            ws = self.in_band(b)
            kinds = Counter(k for w in ws for k in w.source_kinds)
            drops = [w.best_drop_pct for w in ws if w.best_drop_pct is not None]
            gaps = [w.easiest_mob_level - w.obj.level for w in ws if w.easiest_mob_level is not None]
            rows.append({"band": b.label, "weapons": len(ws), "shop": kinds.get("shop", 0),
                         "mob": kinds.get("mob", 0), "floor": kinds.get("floor", 0) + kinds.get("container", 0),
                         "drop": C.median_or(drops), "gap": C.median_or(gaps), "max_gap": max(gaps, default=None)})
        return rows

    def source_table(self) -> str:
        return C.table(["Levels", "weapons", "buyable", "mob drop", "floor/container", "median mob drop %",
                        "median mob − weapon lvl", "max mob − weapon lvl"],
                       [[r["band"], r["weapons"], r["shop"], r["mob"], r["floor"], r["drop"], r["gap"], r["max_gap"]]
                        for r in self.source_rows()])

    def over_table(self) -> str:
        area = self.world.obj_area
        return C.table(["Vnum", "Weapon", "Area", "Type", "Lvl", "Dice", "Avg", "Cap", "Over by", "Sources"],
                       [[w.vnum, w.obj.short_descr, area[w.vnum].name, w.type, w.obj.level,
                         f"{w.obj.values[1]}d{w.obj.values[2]}", w.average, w.cap, w.average - w.cap,
                         ", ".join(w.source_kinds) or "none"] for w in self.over])

    def lost_table(self) -> str:
        area = self.world.obj_area
        return C.table(["Vnum", "Weapon", "Area", "Type", "Lvl", "Avg"],
                       [[w.vnum, w.obj.short_descr, area[w.vnum].name, w.type, w.obj.level, w.average]
                        for w in self.lost])

    def method(self) -> str:
        rows = [[p.name, ", ".join(p.starting), ", ".join(p.easy)] + [p.difficulty[t] for t in SKILLED_TYPES]
                for p in self.profiles]
        return (
            f"- **Weapons**: {len(self.weapons)} weapon prototypes; {len(self.mortal)} at level ≤ {C.HERO_LEVEL}; "
            f"**{len(self.got)} obtainable** (placed by at least one reset: shop stock, mob drop, floor or "
            "container). Level-0 weapons count as level 1.\n"
            "- **Usable at level L** = obtainable and weapon level ≤ L (a character can't wield an object above "
            "their level, act_obj.cpp:137).\n"
            "- **Class affinity.** Every class can learn every weapon from level 1 "
            "(SkillTables.cpp), but at different *difficulty* (the class rating): it's the creation-point cost "
            "and divides both practice gains (act_info.cpp:1604) and learn-by-use chances (Learning.cpp:52). "
            "Weapon skill % multiplies both to-hit and damage (fight.cpp:452, :472), so a class is effectively "
            "weaker with a hard-to-train type. Two views per class: *start* = types granted at creation by "
            "`rom basics` + `<class> basics` + `<class> default` (knight default includes `weaponsmaster` = all "
            f"types); *easy* = types with difficulty ≤ {EASY_DIFFICULTY}.\n"
            "- **Exotic** weapons have no skill; every PC uses them at min(2 × level, 90)% (handler.cpp:108), so "
            "they're shown in supply figures but excluded from class comparisons.\n"
            "- **Damage** is the dice average `n × (s + 1) / 2`; skill, damroll, enhanced damage and weapon flags "
            "come on top. The **cap** is `level/2 + 4` (+5% for two-handers), the rule `immworth` checks "
            "(entity_balance.cpp).\n\n"
            "Weapon difficulty by class (lower is easier; from `skill_table` ratings):\n\n"
            + C.table(["Class", "start", "easy"] + SKILLED_TYPES, rows)
        )

    # -- headline sentences (shared by both renderers) ---------------------------
    def finding_supply(self) -> str:
        totals = self.band_totals
        thin = self.bands[totals.index(min(totals))]
        return (f"{self.early_count} of {len(self.got)} obtainable weapons "
                f"({self.early_count / len(self.got):.0%}) are usable by level {self.early_cutoff}; "
                f"the thinnest band is {thin.label} with {min(totals)}.")

    def finding_access(self) -> str:
        start = sorted(self.class_access("start").items(), key=lambda kv: -kv[1])
        return ("Obtainable weapons in each class's starting types: "
                + ", ".join(f"{c} {n}" for c, n in start) + ".")


def analyse(world: World) -> WeaponAnalysis:
    return C.cached(world, "weapons", WeaponAnalysis)


# -- plain Markdown report (CLI: python -m xania_explorer assess) ------------------
def render(world: World) -> str:
    a = analyse(world)
    out = [C.GENERATED_NOTE, "\n# Weapons: availability by level and class\n\n", "## Headline findings\n\n",
           f"- **Supply is front-loaded**: {a.finding_supply()}\n",
           f"- **Class access**: {a.finding_access()}\n"]
    for p in a.profiles:
        x = a.plateaus(p.name, 1)[0]
        out.append(f"- **{p.name}**: longest plateau {x.lo}–{x.hi} ({x.length} levels) at avg {x.value}; "
                   f"at level {C.HERO_LEVEL} best avg {a.best_start[p.name][C.HERO_LEVEL]} vs "
                   f"{a.best_any[C.HERO_LEVEL]} for any type.\n")
    out.append("\n## Method\n\n" + a.method())
    out.append("\n## 1. New weapons per level band, by type\n\n" + a.supply_table())
    out.append("\n" + C.histogram([(b.label, n) for b, n in zip(a.bands, a.band_totals)]))
    out.append(f"\nSpread across bands: {C.Spread.of(a.band_totals).describe()}.\n")
    out.append("\n## 2. New weapons per band that each class is good with\n\n" + a.access_table())
    out.append("\nBands with **no** new weapon of a class's starting types:\n\n" + a.empty_bands_list())
    out.append("\n## 3. Best usable weapon at each level\n\n" + a.per_level_table())
    out.append("\n### Best weapon as a share of the cap, by band\n\n" + a.cap_ratio_table())
    out.append("\n## 4. Longest stretches without an upgrade\n\n" + a.plateau_table())
    out.append("\n## 5. How weapons are obtained, by band\n\n" + a.source_table())
    out.append(f"\n## 6. Weapons over the damage cap ({len(a.over)})\n\n" + (a.over_table() if a.over else "None.\n"))
    out.append(f"\n## 7. Weapons with no reset source ({len(a.lost)})\n\n" + (a.lost_table() if a.lost else "None.\n"))
    if a.high:
        out.append(f"\n{len(a.high)} weapon(s) above level {C.HERO_LEVEL} are excluded from the analysis.\n")
    return "".join(out)


def write_csv(world: World, path: Path) -> None:
    C.write_csv(path, ["vnum", "name", "area", "type", "level", "dice", "average", "cap", "two_handed",
                       "flags", "sources", "buyable", "best_drop_pct", "easiest_mob_level"],
                [[w.vnum, w.obj.short_descr, world.obj_area[w.vnum].name, w.type, w.obj.level,
                  f"{w.obj.values[1]}d{w.obj.values[2]}", w.average, w.cap, int(w.two_handed),
                  " ".join(F.decode(int(w.obj.values[4]), F.WEAPON_FLAG)), " ".join(w.source_kinds),
                  int(w.buyable), w.best_drop_pct, w.easiest_mob_level] for w in collect(world)])


__all__ = ["render", "analyse", "WeaponAnalysis", "write_csv", "collect", "class_profiles", "allowed_average"]
