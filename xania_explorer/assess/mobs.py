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


@dataclass
class Outlier:
    info: MobInfo
    hp_ratio: float
    dmg_ratio: float

    @property
    def score(self) -> float:
        rs = [self.hp_ratio, self.dmg_ratio]
        return max(max(rs), max((1 / r if r else 99) for r in rs))


@dataclass
class AreaBandMiss:
    area: str
    band: tuple[int, int]
    mobs: int
    below: int
    above: int
    actual: tuple[int, int]

    @property
    def outside_share(self) -> float:
        return (self.below + self.above) / self.mobs


class MobAnalysis:
    """Everything the mobs report says, computed once (shared by the Markdown report and the site)."""

    def __init__(self, world: World):
        self.world = world
        self.infos = collect(world)
        self.combat = [i for i in self.infos if i.category == "combat"]
        self.high = [i for i in self.infos if i.category == "above hero"]
        self.never = [i for i in self.infos if i.category == "never spawns"]
        self.bands = C.bands()
        self.by_band = {b: [i for i in self.combat if i.level in b] for b in self.bands}
        self.band_pop = [sum(i.population for i in self.by_band[b]) for b in self.bands]
        self.band_proto = [len(self.by_band[b]) for b in self.bands]
        self.level_pop = {lvl: sum(i.population for i in self.combat if i.level == lvl) for lvl in C.LEVELS}
        self.level_proto = {lvl: sum(1 for i in self.combat if i.level == lvl) for lvl in C.LEVELS}
        self.empty_levels = [lvl for lvl in C.LEVELS if self.level_proto[lvl] == 0]
        self.outliers = self._outliers()
        self.area_misses = self._area_misses()

    @property
    def total_pop(self) -> int:
        return sum(self.band_pop)

    @property
    def spread(self) -> C.Spread:
        return C.Spread.of(self.band_pop)

    @property
    def early_cutoff(self) -> int:
        return self.bands[len(self.bands) // 3 - 1].hi

    @property
    def early_share(self) -> float:
        return sum(self.band_pop[: len(self.bands) // 3]) / self.total_pop if self.total_pop else 0.0

    def median_hp(self, band: C.Band) -> float | None:
        return C.median_or(i.mob.hit.average for i in self.by_band[band])

    @property
    def hp_drops(self) -> list[tuple[str, float, float]]:
        hp = [self.median_hp(b) for b in self.bands]
        return [(self.bands[k + 1].label, hp[k], hp[k + 1]) for k in range(len(hp) - 1)
                if hp[k] and hp[k + 1] and hp[k + 1] < hp[k]]

    def _outliers(self) -> list[Outlier]:
        def local_median(attr, lvl):
            return C.median_or(attr(i) for i in self.combat if abs(i.level - lvl) <= OUTLIER_WINDOW)

        out = []
        for i in self.combat:
            hp_med = local_median(lambda m: m.mob.hit.average, i.level)
            dmg_med = local_median(lambda m: m.mob.damage.average, i.level)
            hp_r = i.mob.hit.average / hp_med if hp_med else 1
            dmg_r = i.mob.damage.average / dmg_med if dmg_med else 1
            if not OUTLIER_LOW <= hp_r <= OUTLIER_HIGH or not OUTLIER_LOW <= dmg_r <= OUTLIER_HIGH:
                out.append(Outlier(i, hp_r, dmg_r))
        return sorted(out, key=lambda o: (-o.score, o.info.mob.vnum))

    def _area_misses(self) -> list[AreaBandMiss]:
        per_area = defaultdict(list)
        for i in self.combat:
            if i.in_area_band is not None:
                per_area[i.area.name].append(i)
        out = []
        for name, group in per_area.items():
            h = group[0].area.file.header
            below = sum(i.mob.level < h.min_level for i in group)
            above = sum(i.mob.level > h.max_level for i in group)
            if below or above:
                levels = [i.mob.level for i in group]
                out.append(AreaBandMiss(name, (h.min_level, h.max_level), len(group), below, above,
                                        (min(levels), max(levels))))
        return sorted(out, key=lambda m: (-m.outside_share, m.area))

    @property
    def banded_mobs(self) -> int:
        return sum(1 for i in self.combat if i.in_area_band is not None)

    @property
    def banded_outside(self) -> int:
        return sum(1 for i in self.combat if i.in_area_band is False)

    # -- tables --------------------------------------------------------------------
    def band_table(self) -> str:
        rows = []
        for b in self.bands:
            g = self.by_band[b]
            inband = [i.in_area_band for i in g if i.in_area_band is not None]
            rows.append([b.label, len(g), sum(i.population for i in g), _pct(sum(i.aggressive for i in g), len(g)),
                         C.median_or(i.mob.hit.average for i in g), C.median_or(i.mob.damage.average for i in g),
                         C.median_or(i.mob.hitroll for i in g), C.median_or(i.mean_ac for i in g),
                         _pct(sum(inband), len(inband))])
        return C.table(["Levels", "prototypes", "population", "aggressive", "median HP", "median dmg",
                        "median hitroll", "median AC", "in area band"], rows)

    def outlier_table(self, limit: int | None = 40) -> str:
        rows = self.outliers if limit is None else self.outliers[:limit]
        return C.table(["Vnum", "Mob", "Area", "Lvl", "HP", "× local", "Damage", "× local", "Pop"],
                       [[o.info.mob.vnum, o.info.mob.short_descr, o.info.area.name, o.info.mob.level,
                         o.info.mob.hit.average, o.hp_ratio, o.info.mob.damage.average, o.dmg_ratio,
                         o.info.population] for o in rows])

    def area_table(self) -> str:
        return C.table(["Area", "Band", "Mobs", "Below", "Above", "Outside", "Actual range"],
                       [[m.area, f"{m.band[0]}–{m.band[1]}", m.mobs, m.below, m.above, _pct(m.below + m.above, m.mobs),
                         f"{m.actual[0]}–{m.actual[1]}"] for m in self.area_misses])

    def never_table(self) -> str:
        return C.table(["Vnum", "Mob", "Area", "Lvl", "M resets", "Reason"],
                       [[i.mob.vnum, i.mob.short_descr, i.area.name, i.mob.level, len(i.spawns),
                         "world cap ≤ 0" if i.spawns else "no reset"] for i in self.never])

    def high_summary(self) -> str:
        return ", ".join(f"{a} {n}" for a, n in Counter(i.area.name for i in self.high).most_common())

    def method(self) -> str:
        cats = Counter(i.category for i in self.infos)
        return (f"- {len(self.infos)} mob prototypes: " + ", ".join(f"{n} {k}" for k, n in sorted(cats.items()))
                + f". Only **combat** mobs (spawned, not shopkeepers/trainers/practicers/healers/gain, "
                f"level ≤ {C.HERO_LEVEL}) are analysed.\n"
                "- **Population** = the steady-state number of instances the resets maintain: "
                "min(world cap, sum of room caps) over the mob's `M` resets (db.cpp reset_room). "
                "It ignores wandering and kills, so it's what a freshly reset world holds.\n"
                "- **Evenness**: CV (stdev ÷ mean) and Gini, both 0 when perfectly even.\n"
                "- HP and damage are dice averages. Damage dice only apply when the mob fights unarmed "
                "(fight.cpp:465); armed mobs use their weapon. AC is the mean of the four armour classes "
                "(more negative = better).\n"
                f"- **Outliers**: HP or damage above {OUTLIER_HIGH}× or below {OUTLIER_LOW}× the median of combat "
                f"mobs within ±{OUTLIER_WINDOW} levels.\n"
                "- Flags are as written in the area file (race flags are merged at load and aren't counted).\n")

    # -- headline sentences ------------------------------------------------------------
    def finding_evenness(self) -> str:
        pop = self.band_pop
        hi_b, lo_b = self.bands[pop.index(max(pop))], self.bands[pop.index(min(pop))]
        return (f"{self.early_share:.0%} of the ~{self.total_pop} mobs a reset world holds are level "
                f"≤ {self.early_cutoff}. Busiest band {hi_b.label} ({max(pop)}), emptiest {lo_b.label} "
                f"({min(pop)}); CV {self.spread.cv:.2f}, Gini {self.spread.gini:.2f}.")


def analyse(world: World) -> MobAnalysis:
    return C.cached(world, "mobs", MobAnalysis)


def render(world: World) -> str:
    a = analyse(world)
    out = [C.GENERATED_NOTE, "\n# Mobs: distribution and toughness by level\n\n", "## Headline findings\n\n",
           f"- **{len(a.combat)} combat mob prototypes, ~{a.total_pop} instances** after a full reset.\n",
           f"- **Evenness**: {a.finding_evenness()}\n"]
    if a.hp_drops:
        out.append("- **Toughness isn't monotonic**: median HP falls going into "
                   + ", ".join(f"{b} ({x:g}→{y:g})" for b, x, y in a.hp_drops) + ".\n")
    out.append("\n## Method\n\n" + a.method())
    out.append("\n## 1. Distribution by level band\n\n" + a.band_table())
    out.append(f"\n- Prototypes per band: {C.Spread.of(a.band_proto).describe()}.\n"
               f"- Population per band: {a.spread.describe()}.\n\n")
    out.append("Population per band:\n\n" + C.histogram([(b.label, p) for b, p in zip(a.bands, a.band_pop)]))
    out.append("\n## 2. Population at every level\n\n"
               f"Per-level spread (population): {C.Spread.of(list(a.level_pop.values())).describe()}.\n\n"
               f"Levels with **no** combat mob: {_ranges(a.empty_levels) or 'none'}.\n\n")
    out.append(C.histogram([(str(lvl), a.level_pop[lvl]) for lvl in C.LEVELS], width=50))
    out.append(f"\n## 3. Toughness outliers ({len(a.outliers)})\n\nMost extreme first (top 40).\n\n"
               + a.outlier_table())
    out.append("\n## 4. Mobs outside their area's level band\n\n" + a.area_table())
    out.append(f"\n## 5. Excluded mobs\n\n**Above level {C.HERO_LEVEL}** ({len(a.high)}), by area: "
               f"{a.high_summary()}.\n\n**Never spawn** ({len(a.never)}): no `M` reset, or every `M` reset has a "
               "world cap ≤ 0. Some may still be loaded by mob programs or specials.\n\n" + a.never_table())
    return "".join(out)


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
