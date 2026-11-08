"""Equipment: armour and other worn gear from level 1 to 91 (weapons have their own system).

Questions answered:
- At each level, how much armour class and hitroll/damroll can a character wear, slot by slot?
- Which wear slots have long gaps with nothing new to wear?
- Which items break the item-points balance rule (entity_balance.cpp)?

There are no class restrictions on wearing items in Xania (only level and alignment),
so equipment is the same for every class; differences come from alignment flags.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..areafile import flags as F
from ..areafile.model import Obj
from ..areafile.world import World
from . import common as C
from .sources import ObjSource, object_sources

# Wear slots that hold armour, with how many of each a character can wear (Worn.hpp).
SLOTS: dict[str, int] = {"body": 1, "head": 1, "legs": 1, "feet": 1, "hands": 1, "arms": 1, "shield": 1,
                         "about": 1, "waist": 1, "neck": 2, "wrist": 2, "finger": 2, "ears": 1, "hold": 1}
SLOT_FLAG = {"body": "Body", "head": "Head", "legs": "Legs", "feet": "Feet", "hands": "Hands", "arms": "Arms",
             "shield": "Shield", "about": "About", "waist": "Waist", "neck": "Neck", "wrist": "Wrist",
             "finger": "Finger", "ears": "Ears", "hold": "Hold"}
STAT_LOCATIONS = {"Str", "Dex", "Int", "Wis", "Con"}
ALIGN_FLAGS = {"AntiGood", "AntiEvil", "AntiNeutral"}


def points_allowed(level: int) -> int:
    """entity_balance.cpp: an item may carry level/10 + 1 points."""
    return level // 10 + 1


@dataclass
class Item:
    obj: Obj
    sources: list[ObjSource]

    @property
    def vnum(self) -> int:
        return self.obj.vnum

    @property
    def level(self) -> int:
        return C.usable_level(self.obj.level)

    @property
    def slots(self) -> list[str]:
        wear = set(F.decode(self.obj.wear_flags, F.WEAR))
        return [s for s, flag in SLOT_FLAG.items() if flag in wear]

    def _sum(self, *locations: str) -> int:
        return sum(a.modifier for a in self.obj.affects if a.location_name in locations)

    @property
    def armour_ac(self) -> float:
        """Mean of the four armour values (pierce/bash/slash/exotic); only Armor objects count (apply_ac)."""
        if self.obj.type_name != "Armor":
            return 0.0
        return sum(int(v) for v in self.obj.values[:4]) / 4

    @property
    def ac(self) -> float:
        """Total AC improvement (positive = better): armour values plus 'Ac' affects (negative modifiers)."""
        return self.armour_ac - self._sum("Ac")

    @property
    def hitroll(self) -> int:
        return self._sum("Hitroll")

    @property
    def damroll(self) -> int:
        return self._sum("Damroll")

    @property
    def hp(self) -> int:
        return self._sum("Hit")

    @property
    def mana(self) -> int:
        return self._sum("Mana")

    @property
    def stats(self) -> int:
        return sum(a.modifier for a in self.obj.affects if a.location_name in STAT_LOCATIONS)

    @property
    def obtainable(self) -> bool:
        return bool(self.sources)

    @property
    def alignment_flags(self) -> list[str]:
        return [f for f in F.decode(self.obj.extra_flags, F.OBJ_EXTRA) if f in ALIGN_FLAGS]

    # -- item-points rule (entity_balance.cpp report_object) -----------------------
    @property
    def points(self) -> int:
        """Port of report_object's worth, including its quirk that AC and saving-throw
        affects are never counted (AFFECT_DATA.cpp:86 tests modifier < 0 && modifier > 0)."""
        worth = hit = dam = 0
        for a in self.obj.affects:
            loc, m = a.location_name, a.modifier
            if loc in STAT_LOCATIONS and m > 0:
                worth += m
            elif loc == "Hitroll":
                hit += m
            elif loc == "Damroll":
                dam += m
            elif loc in ("Mana", "Hit", "Move") and m > 0:
                worth += (m + 6) // 7
        is_weapon = self.obj.type_name == "Weapon"
        worth += (hit + dam) // 2 if is_weapon else hit + dam
        if is_weapon:
            flags = set(F.decode(int(self.obj.values[4]), F.WEAPON_FLAG))
            worth += len(flags & {"Flaming", "Frost", "Vampiric", "Sharp", "Vorpal"})
        return worth

    @property
    def points_if_ac_counted(self) -> int:
        """What the rule would say if the intended AC/saves clause worked (one point per -1)."""
        extra = sum(-a.modifier for a in self.obj.affects
                    if a.modifier < 0 and (a.location_name == "Ac" or a.location_name.startswith("Saving")))
        return self.points + extra

    @property
    def allowed(self) -> int:
        return points_allowed(self.obj.level)


def collect(world: World) -> list[Item]:
    sources = object_sources(world)
    return sorted((Item(o, sources.get(o.vnum, [])) for o in world.objects.values()), key=lambda i: (i.level, i.vnum))


def wearables(items: list[Item]) -> list[Item]:
    return [i for i in items if i.slots and i.obj.type_name != "Weapon"]


@dataclass
class Kit:
    """Best item per slot at one level, judged by one score."""

    level: int
    picks: dict[str, list[Item]]

    def total(self, attr: str) -> float:
        return sum(getattr(i, attr) for items in self.picks.values() for i in items)


class EquipmentAnalysis:
    def __init__(self, world: World):
        self.world = world
        self.items = collect(world)
        self.gear = [i for i in wearables(self.items) if i.level <= C.HERO_LEVEL]
        self.got = [i for i in self.gear if i.obtainable]
        self.lost = [i for i in self.gear if not i.obtainable]
        self.bands = C.bands()
        self.ac_kits = {lvl: self.kit(lvl, "ac") for lvl in C.LEVELS}
        self.hit_kits = {lvl: self.kit(lvl, "hitdam") for lvl in C.LEVELS}
        mortal = [i for i in self.items if i.obtainable and i.level <= C.HERO_LEVEL]
        self.over_points = sorted((i for i in mortal if i.points > i.allowed),
                                  key=lambda i: (-(i.points - i.allowed), i.vnum))
        self.over_points_immortal = sorted((i for i in self.items if i.obtainable and i.level > C.HERO_LEVEL
                                            and i.points > i.allowed), key=lambda i: (-(i.points - i.allowed), i.vnum))
        self.hidden_by_bug = [i for i in mortal if i.points <= i.allowed < i.points_if_ac_counted]

    def kit(self, level: int, score: str) -> Kit:
        def value(i: Item) -> float:
            return i.ac if score == "ac" else i.hitroll + i.damroll

        picks = {}
        for slot, count in SLOTS.items():
            usable = sorted((i for i in self.got if slot in i.slots and i.level <= level and value(i) > 0),
                            key=lambda i: (-value(i), i.vnum))
            picks[slot] = usable[:1] * count if usable else []
        return Kit(level, picks)

    def slot_items(self, slot: str) -> list[Item]:
        return [i for i in self.got if slot in i.slots]

    def first_level(self, slot: str) -> int | None:
        levels = [i.level for i in self.slot_items(slot) if i.ac > 0]
        return min(levels) if levels else None

    def slot_plateau(self, slot: str) -> tuple[int, int, float | None]:
        series = {}
        for lvl in C.LEVELS:
            picks = self.ac_kits[lvl].picks[slot]
            series[lvl] = picks[0].ac if picks else None
        return C.runs_without_increase(series)[0]

    # tables
    def kit_table(self) -> str:
        rows = []
        for b in self.bands:
            ka, kh = self.ac_kits[b.hi], self.hit_kits[b.hi]
            rows.append([b.label, round(ka.total("ac")), sum(1 for p in ka.picks.values() if p),
                         kh.total("hitroll"), kh.total("damroll"), round(ka.total("hp"))])
        return C.table(["Levels (kit at top level)", "AC from best-AC kit", "slots filled", "hitroll (best hit kit)",
                        "damroll (best hit kit)", "HP on AC kit"], rows)

    def slot_table(self) -> str:
        rows = []
        for slot in SLOTS:
            items = self.slot_items(slot)
            lo, hi, val = self.slot_plateau(slot)
            best91 = self.ac_kits[C.HERO_LEVEL].picks[slot]
            rows.append([slot, SLOTS[slot], len(items), self.first_level(slot),
                         best91[0].obj.short_descr if best91 else None, best91[0].ac if best91 else None,
                         f"{lo}–{hi}", val])
        return C.table(["Slot", "worn", "obtainable items", "first AC item at level", "best at 91", "AC",
                        "longest wait", "AC during wait"], rows)

    def coverage_rows(self) -> list[dict]:
        return [{"slot": s, "band": b.label, "count": sum(1 for i in self.slot_items(s) if i.level in b)}
                for s in SLOTS for b in self.bands]

    def points_table(self) -> str:
        area = self.world.obj_area
        return C.table(["Vnum", "Item", "Area", "Type", "Lvl", "Points", "Allowed", "Over by", "Affects"],
                       [[i.vnum, i.obj.short_descr, area[i.vnum].name, i.obj.type_name, i.obj.level, i.points,
                         i.allowed, i.points - i.allowed,
                         ", ".join(f"{a.location_name} {a.modifier:+d}" for a in i.obj.affects)]
                        for i in self.over_points])

    def hidden_table(self) -> str:
        area = self.world.obj_area
        return C.table(["Vnum", "Item", "Area", "Lvl", "Points counted", "With AC/saves", "Allowed", "Affects"],
                       [[i.vnum, i.obj.short_descr, area[i.vnum].name, i.obj.level, i.points, i.points_if_ac_counted,
                         i.allowed, ", ".join(f"{a.location_name} {a.modifier:+d}" for a in i.obj.affects)]
                        for i in sorted(self.hidden_by_bug, key=lambda i: (-(i.points_if_ac_counted - i.allowed),
                                                                             i.vnum))])

    def lost_table(self) -> str:
        area = self.world.obj_area
        return C.table(["Vnum", "Item", "Area", "Slots", "Lvl", "AC"],
                       [[i.vnum, i.obj.short_descr, area[i.vnum].name, ", ".join(i.slots), i.obj.level, i.ac]
                        for i in self.lost])

    def method(self) -> str:
        return (
            f"- **Gear**: obtainable (placed by a reset), wearable, non-weapon items of level ≤ {C.HERO_LEVEL}: "
            f"{len(self.got)} items ({len(self.lost)} more have no source).\n"
            "- **AC** of an item = the mean of its four armour values (armour objects only, handler.cpp apply_ac) "
            "plus any `Ac` affect (negative is better). Higher here means more protection. A PC's own AC starts "
            "at 0 (Char.hpp) and only dex and gear lower it.\n"
            "- **Kits**: for each level, the best obtainable item per slot that a character of that level may wear, "
            "judged by AC (or by hitroll + damroll). Two-slot locations (neck, wrist, finger) take two of the best. "
            "Items with several wear flags are considered for each slot. Real characters won't have every best "
            "item; this is the ceiling the world offers.\n"
            "- **Points rule** (entity_balance.cpp `report_object`): stats +1 each, hitroll/damroll +1 each "
            "(half for weapons), HP/mana/move +1 per 7, weapon flags +1 each; allowed `level/10 + 1`. AC and "
            "saving-throw affects should count too but never do (AFFECT_DATA.cpp:86).\n"
            "- There are no class restrictions on wearing items, only level and alignment flags.\n"
        )


def analyse(world: World) -> EquipmentAnalysis:
    return C.cached(world, "equipment", EquipmentAnalysis)


def render(world: World) -> str:
    a = analyse(world)
    k91 = a.ac_kits[C.HERO_LEVEL]
    out = [C.GENERATED_NOTE, "\n# Equipment: armour and gear by level\n\n", "## Headline findings\n\n",
           f"- **Best-AC kit at level {C.HERO_LEVEL}**: {k91.total('ac'):.0f} AC from "
           f"{sum(1 for p in k91.picks.values() if p)} filled slots.\n",
           f"- **Points rule**: {len(a.over_points)} obtainable items exceed it; "
           f"{len(a.hidden_by_bug)} more would if AC/saves were counted.\n",
           "\n## Method\n\n", a.method(),
           "\n## 1. Kits by level band\n\n", a.kit_table(),
           "\n## 2. Slots\n\n", a.slot_table(),
           f"\n## 3. Items over the points rule ({len(a.over_points)})\n\n", a.points_table(),
           f"\n## 4. Items hidden by the AC/saves bug ({len(a.hidden_by_bug)})\n\n", a.hidden_table(),
           f"\n## 5. Gear with no source ({len(a.lost)})\n\n", a.lost_table()]
    return "".join(out)


def write_csv(world: World, path: Path) -> None:
    a = analyse(world)
    C.write_csv(path, ["vnum", "name", "area", "type", "level", "slots", "ac", "hitroll", "damroll", "hp", "mana",
                       "stats", "points", "allowed", "points_if_ac_counted", "alignment_flags", "sources"],
                [[i.vnum, i.obj.short_descr, world.obj_area[i.vnum].name, i.obj.type_name, i.obj.level,
                  " ".join(i.slots), i.ac, i.hitroll, i.damroll, i.hp, i.mana, i.stats, i.points, i.allowed,
                  i.points_if_ac_counted, " ".join(i.alignment_flags), " ".join(sorted({s.kind for s in i.sources}))]
                 for i in a.items if i.slots or i.obj.type_name == "Weapon"])


__all__ = ["analyse", "render", "write_csv", "EquipmentAnalysis", "Item", "SLOTS", "Counter"]
