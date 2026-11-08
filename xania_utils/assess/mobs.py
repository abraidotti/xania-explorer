"""Mob distribution and toughness across levels 1–91.

Questions answered:
- Are mobs evenly spread over levels, both as prototypes and as the population
  the resets actually maintain?
- Does toughness (HP, damage, hitroll, AC) rise smoothly with level, and which
  mobs are outliers for their level?
- Do mobs sit inside their area's advertised level band?
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..areafile.model import Mob
from ..areafile.world import Area, World
from . import common as C
from .sources import MobSpawn, estimated_population, mob_spawns, shopkeepers

SERVICE_ACT_BITS = {"Train", "Practice", "Healer", "Gain"}
OUTLIER_HIGH = 2.5  # × level-band median
OUTLIER_LOW = 0.4
OUTLIER_WINDOW = 2  # compare against mobs within ±2 levels


@dataclass
class MobInfo:
    mob: Mob
    area: Area
    spawns: list[MobSpawn]
    is_shopkeeper: bool

    @property
    def level(self) -> int:
        return C.usable_level(self.mob.level)

    @property
    def population(self) -> int:
        return estimated_population(self.spawns)

    @property
    def service(self) -> bool:
        return self.is_shopkeeper or bool(SERVICE_ACT_BITS & set(self.mob.act_names))

    @property
    def aggressive(self) -> bool:
        return "Aggressive" in self.mob.act_names

    @property
    def mean_ac(self) -> float:
        return sum(self.mob.ac) / 4

    @property
    def in_area_band(self) -> bool | None:
        h = self.area.file.header
        if h is None or h.all_levels:
            return None
        return h.min_level <= self.mob.level <= h.max_level

    @property
    def category(self) -> str:
        if self.population == 0:
            return "never spawns"
        if self.service:
            return "service"
        if self.level > C.HERO_LEVEL:
            return "above hero"
        return "combat"


def collect(world: World) -> list[MobInfo]:
    spawns = mob_spawns(world)
    keepers = shopkeepers(world)
    return sorted((MobInfo(m, world.mob_area[v], spawns.get(v, []), v in keepers) for v, m in world.mobs.items()),
                  key=lambda i: (i.level, i.mob.vnum))


def render(world: World) -> str:
    infos = collect(world)
    combat = [i for i in infos if i.category == "combat"]
    bands = C.bands()
    by_band = {b: [i for i in combat if i.level in b] for b in bands}

    out = [C.GENERATED_NOTE, "\n# Mobs: distribution and toughness by level\n\n"]
    out.append(_findings(combat, bands, by_band))

    cats = Counter(i.category for i in infos)
    out.append("\n## Method\n\n"
               f"- {len(infos)} mob prototypes: " + ", ".join(f"{n} {k}" for k, n in sorted(cats.items())) + ". "
               "Only **combat** mobs (spawned, not shopkeepers/trainers/practicers/healers/gain, level ≤ 91) "
               "are analysed below.\n"
               "- **Population** = the steady-state number of instances the resets maintain: "
               "min(world cap, sum of room caps) over the mob's `M` resets (db.cpp reset_room). "
               "It ignores wandering and kills, so it's what a freshly reset world holds.\n"
               "- HP and damage are dice averages. Damage dice only apply when the mob fights unarmed "
               "(fight.cpp:465); armed mobs use their weapon. AC is the mean of the four armour classes "
               "(more negative = better).\n"
               "- Flags are as written in the area file (race flags are merged at load and aren't counted).\n")

    # 1. Distribution by band
    out.append("\n## 1. Distribution by level band\n\n")
    rows = []
    for b in bands:
        g = by_band[b]
        inband = [i.in_area_band for i in g if i.in_area_band is not None]
        rows.append([b.label, len(g), sum(i.population for i in g),
                     _pct(sum(i.aggressive for i in g), len(g)),
                     C.median_or(i.mob.hit.average for i in g), C.median_or(i.mob.damage.average for i in g),
                     C.median_or(i.mob.hitroll for i in g), C.median_or(i.mean_ac for i in g),
                     _pct(sum(inband), len(inband))])
    out.append(C.table(["Levels", "prototypes", "population", "aggressive", "median HP", "median dmg",
                        "median hitroll", "median AC", "in area band"], rows))
    proto = [len(by_band[b]) for b in bands]
    pop = [sum(i.population for i in by_band[b]) for b in bands]
    out.append(f"\n- Prototypes per band: {C.Spread.of(proto).describe()}.\n"
               f"- Population per band: {C.Spread.of(pop).describe()}.\n\n")
    out.append("Population per band:\n\n" + C.histogram([(b.label, p) for b, p in zip(bands, pop)]))

    # 2. Per level
    per_level_pop = {lvl: sum(i.population for i in combat if i.level == lvl) for lvl in C.LEVELS}
    per_level_proto = {lvl: sum(1 for i in combat if i.level == lvl) for lvl in C.LEVELS}
    empty = [lvl for lvl in C.LEVELS if per_level_proto[lvl] == 0]
    out.append("\n## 2. Population at every level\n\n"
               f"Per-level spread (population): {C.Spread.of(list(per_level_pop.values())).describe()}.\n\n"
               f"Levels with **no** combat mob: {_ranges(empty) or 'none'}.\n\n")
    out.append(C.histogram([(str(lvl), per_level_pop[lvl]) for lvl in C.LEVELS], width=50))

    # 3. Toughness outliers
    def local_median(attr, lvl):
        return C.median_or(attr(i) for i in combat if abs(i.level - lvl) <= OUTLIER_WINDOW)

    outliers = []
    for i in combat:
        hp_med = local_median(lambda m: m.mob.hit.average, i.level)
        dmg_med = local_median(lambda m: m.mob.damage.average, i.level)
        hp_r = i.mob.hit.average / hp_med if hp_med else 1
        dmg_r = i.mob.damage.average / dmg_med if dmg_med else 1
        if not OUTLIER_LOW <= hp_r <= OUTLIER_HIGH or not OUTLIER_LOW <= dmg_r <= OUTLIER_HIGH:
            score = max(hp_r, dmg_r, 1 / hp_r if hp_r else 99, 1 / dmg_r if dmg_r else 99)
            outliers.append((score, i, hp_r, dmg_r))
    outliers.sort(key=lambda t: (-t[0], t[1].mob.vnum))
    out.append(f"\n## 3. Toughness outliers ({len(outliers)})\n\n"
               f"Combat mobs whose HP or damage is above {OUTLIER_HIGH}× or below {OUTLIER_LOW}× the median "
               f"of combat mobs within ±{OUTLIER_WINDOW} levels of them. Most extreme first (top 40).\n\n")
    out.append(C.table(["Vnum", "Mob", "Area", "Lvl", "HP", "× local", "Damage", "× local", "Pop"],
                       [[i.mob.vnum, i.mob.short_descr, i.area.name, i.mob.level, i.mob.hit.average, hp_r,
                         i.mob.damage.average, dmg_r, i.population] for _, i, hp_r, dmg_r in outliers[:40]]))

    # 4. Area bands
    out.append("\n## 4. Mobs outside their area's level band\n\n"
               "Areas with a declared `{min max}` band, sorted by share of combat mobs outside it.\n\n")
    per_area = defaultdict(list)
    for i in combat:
        if i.in_area_band is not None:
            per_area[i.area.name].append(i)
    rows = []
    for name, group in per_area.items():
        h = group[0].area.file.header
        below = sum(i.mob.level < h.min_level for i in group)
        above = sum(i.mob.level > h.max_level for i in group)
        if below or above:
            rows.append([name, f"{h.min_level}–{h.max_level}", len(group), below, above,
                         _pct(below + above, len(group)), f"{min(i.mob.level for i in group)}–"
                                                          f"{max(i.mob.level for i in group)}"])
    rows.sort(key=lambda r: (-(r[3] + r[4]) / r[2], r[0]))
    out.append(C.table(["Area", "Band", "Mobs", "Below", "Above", "Outside", "Actual range"], rows))

    # 5. Excluded mobs
    high = [i for i in infos if i.category == "above hero"]
    never = [i for i in infos if i.category == "never spawns"]
    out.append(f"\n## 5. Excluded mobs\n\n**Above level {C.HERO_LEVEL}** ({len(high)}), by area: "
               + ", ".join(f"{a} {n}" for a, n in Counter(i.area.name for i in high).most_common()) + ".\n\n"
               f"**Never spawn** ({len(never)}): no `M` reset, or every `M` reset has a world cap ≤ 0. "
               "Some may still be loaded by mob programs or specials.\n\n")
    out.append(C.table(["Vnum", "Mob", "Area", "Lvl", "M resets", "Reason"],
                       [[i.mob.vnum, i.mob.short_descr, i.area.name, i.mob.level, len(i.spawns),
                         "world cap ≤ 0" if i.spawns else "no reset"] for i in never]))
    return "".join(out)


def _findings(combat, bands, by_band) -> str:
    pop = [sum(i.population for i in by_band[b]) for b in bands]
    lo_b, hi_b = bands[pop.index(min(pop))], bands[pop.index(max(pop))]
    first_third = sum(pop[: len(pop) // 3])
    spread = C.Spread.of(pop)
    hp = [C.median_or(i.mob.hit.average for i in by_band[b]) for b in bands]
    drops = [(bands[k + 1].label, hp[k], hp[k + 1]) for k in range(len(hp) - 1)
             if hp[k] and hp[k + 1] and hp[k + 1] < hp[k]]
    lines = ["## Headline findings\n\n",
             f"- **{len(combat)} combat mob prototypes, ~{sum(pop)} instances** after a full reset.\n",
             f"- **Evenness**: population per 5-level band has CV {spread.cv:.2f} and Gini {spread.gini:.2f} "
             f"(0 = perfectly even). Busiest band {hi_b.label} ({max(pop)}), emptiest {lo_b.label} ({min(pop)}); "
             f"{first_third / sum(pop):.0%} of all mobs are level ≤ {bands[len(bands) // 3 - 1].hi}.\n"]
    if drops:
        lines.append("- **Toughness isn't monotonic**: median HP falls going into "
                     + ", ".join(f"{b} ({a:g}→{c:g})" for b, a, c in drops) + ".\n")
    return "".join(lines)


def _pct(n: int, d: int) -> str | None:
    return f"{n / d:.0%}" if d else None


def _ranges(levels: list[int]) -> str:
    if not levels:
        return ""
    out, start, prev = [], levels[0], levels[0]
    for lvl in levels[1:] + [None]:
        if lvl is not None and lvl == prev + 1:
            prev = lvl
            continue
        out.append(str(start) if start == prev else f"{start}–{prev}")
        if lvl is not None:
            start = prev = lvl
    return ", ".join(out)


def write_csv(world: World, path: Path) -> None:
    C.write_csv(path, ["vnum", "name", "area", "level", "category", "population", "hp_avg", "damage_avg",
                       "hitroll", "mean_ac", "aggressive", "in_area_band", "act", "offensive"],
                [[i.mob.vnum, i.mob.short_descr, i.area.name, i.mob.level, i.category, i.population,
                  i.mob.hit.average, i.mob.damage.average, i.mob.hitroll, i.mean_ac, int(i.aggressive),
                  "" if i.in_area_band is None else int(i.in_area_band), " ".join(i.mob.act_names),
                  " ".join(i.mob.off_names)] for i in collect(world)])
