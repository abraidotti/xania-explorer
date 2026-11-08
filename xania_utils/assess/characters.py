"""Characters: how each class × race combination grows from level 1 to 91.

Questions answered:
- How much XP does each combination need per level (race XP multipliers and creation points)?
- How much HP, mana and movement does each gain per level, and where does it end up at 91?
- How long does it take to max out stats with trains, and what do maxed stats give in combat?

Model (all formulas from the C++, see Method):
- Default creation: the class's default skill package (40 points) + race points; customised builds cost more.
- Stats start at the race's base, +3 to the class prime stat (not for dragons).
- Trains: 3 at creation, +1 per level. They go into stats until every stat is at its trainable
  maximum (prime stat first, then con, str, dex, wis, int), then into +10 HP each.
- Per-level gains are *expected values* of advance_level's random rolls at the stats held at that level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..areafile.world import World
from ..source.character_tables import (
    DEFAULT_GROUP_POINTS, MAX_STAT_VALUE, NEWBIE_TRAINS, PRIME_STAT_BONUS_AT_CREATION, PRIME_STAT_TRAIN_BONUS,
    START_HIT, START_MANA, START_MOVE, STATS, ClassInfo, PcRace, StatTables, load_classes, load_pc_races,
    load_stat_tables,
)
from ..source.cpp_tables import CLASSES
from . import common as C

TRAIN_ORDER_AFTER_PRIME = ["con", "str", "dex", "wis", "int"]
HP_PER_TRAIN = 10  # act_move.cpp do_train "hp"
XP_CAP = 65500  # skills.cpp exp_per_level


def exp_per_level(points: int, class_mult: int) -> int:
    """Port of ``exp_per_level`` (skills.cpp:259)."""
    if points < DEFAULT_GROUP_POINTS:
        return 1000 * class_mult // 100
    expl, inc = 1000, 500
    points -= DEFAULT_GROUP_POINTS
    while points > 9:
        expl += inc
        points -= 10
        if points > 9:
            expl += inc
            inc *= 2
            points -= 10
    expl += points * inc // 10
    return min(XP_CAP, expl * class_mult // 100)


# -- expected per-level gains (advance_level, update.cpp:480) ---------------------
@lru_cache(maxsize=None)
def expected_hp_gain(con_hitp: int, hmin: int, hmax: int) -> float:
    rolls = range(hmin, hmax + 1)
    return sum(max(1, (con_hitp + r) * 9 // 10) for r in rolls) / len(rolls)


@lru_cache(maxsize=None)
def expected_mana_gain(factor: int, wis: int, intel: int) -> float:
    top = factor * factor * (max(0, wis - 15) + 2 * max(0, intel - 15))
    return sum((x + 150) // 300 for x in range(top + 1)) / (top + 1) + factor // 2


@lru_cache(maxsize=None)
def expected_move_gain(con: int, dex: int) -> float:
    top = max(1, (con + dex) // 6)
    return sum(max(6, r * 9 // 10) for r in range(1, top + 1)) / top


@dataclass
class LevelState:
    level: int
    stats: dict[str, int]
    hp: float
    mana: float
    move: float
    practices: float
    trains_into_hp: int


@dataclass
class Build:
    """One class × race combination with the default skill package."""

    cls: ClassInfo
    race: PcRace
    tables: StatTables
    levels: dict[int, LevelState] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.race.name} {self.cls.name}"

    @property
    def points(self) -> int:
        return DEFAULT_GROUP_POINTS + self.race.points

    @property
    def xp_per_level(self) -> int:
        return exp_per_level(self.points, self.race.mult_for(self.cls.name))

    @property
    def xp_to_hero(self) -> int:
        return self.xp_per_level * (C.HERO_LEVEL - 1)

    @property
    def start_stats(self) -> dict[str, int]:
        stats = dict(zip(STATS, self.race.stats))
        if self.race.name != "dragon":
            stats[self.cls.prime_stat] += PRIME_STAT_BONUS_AT_CREATION
        return stats

    @property
    def max_stats(self) -> dict[str, int]:
        """handler.cpp get_max_train: race max, +2 for the prime stat, capped at 25."""
        return {s: min(MAX_STAT_VALUE, m + (PRIME_STAT_TRAIN_BONUS if s == self.cls.prime_stat else 0))
                for s, m in zip(STATS, self.race.max_stats)}

    @property
    def trains_to_max(self) -> int:
        start, top = self.start_stats, self.max_stats
        return sum(max(0, top[s] - start[s]) for s in STATS)

    @property
    def level_stats_maxed(self) -> int:
        """First level at which all stats can be at their trainable maximum (3 trains at 1, +1/level)."""
        return max(1, self.trains_to_max - NEWBIE_TRAINS + 1)

    def simulate(self) -> "Build":
        stats = self.start_stats
        top = self.max_stats
        order = [self.cls.prime_stat] + [s for s in TRAIN_ORDER_AFTER_PRIME if s != self.cls.prime_stat]
        hp, mana, move, pracs, into_hp = float(START_HIT), float(START_MANA), float(START_MOVE), 0.0, 0
        trains = NEWBIE_TRAINS

        def spend(n: int) -> int:
            nonlocal into_hp
            spent_hp = 0
            for _ in range(n):
                stat = next((s for s in order if stats[s] < top[s]), None)
                if stat is None:
                    into_hp += 1
                    spent_hp += 1
                else:
                    stats[stat] += 1
            return spent_hp

        hp += HP_PER_TRAIN * spend(trains)
        t = self.tables
        for level in C.LEVELS:
            if level > 1:
                con, dex, wis, intel = stats["con"], stats["dex"], stats["wis"], stats["int"]
                hp += expected_hp_gain(t.con_app[con][0], self.cls.hp_gain_min, self.cls.hp_gain_max)
                mana += expected_mana_gain(self.cls.mana_factor, wis, intel)
                move += expected_move_gain(con, dex)
                pracs += t.wis_app[wis]
                hp += HP_PER_TRAIN * spend(1)
            self.levels[level] = LevelState(level, dict(stats), hp, mana, move, pracs, into_hp)
        return self

    def at(self, level: int) -> LevelState:
        return self.levels[level]

    def combat_bonuses(self, level: int = C.HERO_LEVEL) -> dict[str, int]:
        s = self.at(level).stats
        t = self.tables
        return {"hitroll": t.str_app[s["str"]][0], "damroll": t.str_app[s["str"]][1],
                "ac": t.dex_app[s["dex"]], "learn": t.int_app[s["int"]]}


def builds(src_dir: Path | None = None) -> list[Build]:
    classes, races, tables = load_classes(src_dir), load_pc_races(src_dir), load_stat_tables(src_dir)
    return [Build(classes[c], r, tables).simulate() for r in races.values() for c in CLASSES]


# -- analysis ---------------------------------------------------------------------
class CharacterAnalysis:
    def __init__(self, world: World):
        self.world = world
        self.builds = builds(world.src_dir)
        self.classes = load_classes(world.src_dir)
        self.races = list(load_pc_races(world.src_dir))

    def build(self, race: str, cls: str) -> Build:
        return next(b for b in self.builds if b.race.name == race and b.cls.name == cls)

    def by_class(self, cls: str) -> list[Build]:
        return [b for b in self.builds if b.cls.name == cls]

    # facts
    @property
    def xp_extremes(self) -> tuple[Build, Build]:
        ordered = sorted(self.builds, key=lambda b: (b.xp_per_level, b.label))
        return ordered[0], ordered[-1]

    def hp91(self, b: Build) -> float:
        return b.at(C.HERO_LEVEL).hp

    def best_worst(self, cls: str, key) -> tuple[Build, Build]:
        ordered = sorted(self.by_class(cls), key=lambda b: (key(b), b.race.name))
        return ordered[-1], ordered[0]

    # tables
    def xp_table(self) -> str:
        rows = [[r] + [self.build(r, c).xp_per_level for c in CLASSES] + [self.build(r, CLASSES[0]).points]
                for r in self.races]
        return C.table(["Race"] + CLASSES + ["creation points"], rows)

    def final_table(self, attr: str) -> str:
        rows = [[r] + [round(getattr(self.build(r, c).at(C.HERO_LEVEL), attr)) for c in CLASSES] for r in self.races]
        return C.table(["Race"] + CLASSES, rows)

    def stats_table(self) -> str:
        rows = []
        for b in self.builds:
            st, mx = b.start_stats, b.max_stats
            rows.append([b.race.name, b.cls.name] + [f"{st[s]}→{mx[s]}" for s in STATS]
                        + [b.trains_to_max, b.level_stats_maxed])
        return C.table(["Race", "Class"] + STATS + ["trains to max", "maxed by level"], rows)

    def combat_table(self) -> str:
        rows = []
        for b in self.builds:
            cb = b.combat_bonuses()
            rows.append([b.race.name, b.cls.name, cb["hitroll"], cb["damroll"], cb["ac"], cb["learn"],
                         b.tables.wis_app[b.at(C.HERO_LEVEL).stats["wis"]]])
        return C.table(["Race", "Class", "hitroll (str)", "damroll (str)", "AC (dex)", "learn (int)",
                        "practices/level (wis)"], rows)

    def per_level_table(self, race: str = "human") -> str:
        rows = [[lvl] + [round(self.build(race, c).at(lvl).hp) for c in CLASSES]
                + [round(self.build(race, c).at(lvl).mana) for c in CLASSES] for lvl in C.LEVELS]
        return C.table(["Lvl"] + [f"{c} HP" for c in CLASSES] + [f"{c} mana" for c in CLASSES], rows)

    def class_table(self) -> str:
        rows = [[c.name, c.prime_stat, f"{c.hp_gain_min}–{c.hp_gain_max}", c.mana_factor, c.to_hit_ac_level0,
                 c.to_hit_ac_level32, c.adept] for c in self.classes.values()]
        return C.table(["Class", "prime stat", "HP roll/level", "mana factor", "to-hit AC lvl 0",
                        "to-hit AC lvl 32", "skill adept %"], rows)

    def race_table(self) -> str:
        rows = [[r.name, r.points, " / ".join(map(str, r.class_mult)), ", ".join(r.bonus_skills) or "—",
                 " ".join(map(str, r.stats)), " ".join(map(str, r.max_stats)), r.size]
                for r in load_pc_races(self.world.src_dir).values()]
        return C.table(["Race", "points", "XP mult (m/c/k/b)", "bonus skills", "base stats", "max stats", "size"],
                       rows)

    def method(self) -> str:
        return (
            "- **Builds**: every PC race × class with the class's **default skill package** (40 creation points) "
            "plus the race's points. Customising costs more points and so more XP per level.\n"
            "- **XP per level** = `exp_per_level(points)` (skills.cpp:259) × the race's class multiplier. It's the "
            f"same at every level, so reaching level {C.HERO_LEVEL} takes {C.HERO_LEVEL - 1}× that.\n"
            "- **Stats** start at the race's base +3 to the class prime stat (not dragons, MudImpl.cpp). Each stat "
            "can be trained to the race maximum, +2 for the prime stat (handler.cpp get_max_train), capped at 25.\n"
            f"- **Trains**: {NEWBIE_TRAINS} at creation and 1 per level. Assumed spent on stats until all are maxed "
            f"(prime first, then {', '.join(TRAIN_ORDER_AFTER_PRIME)}), then on +{HP_PER_TRAIN} HP each.\n"
            "- **Per-level gains** are the expected values of `advance_level` (update.cpp:480): HP = "
            "(con bonus + class roll) × 0.9; mana from the class factor, int and wis above 15; move from con + "
            "dex; practices from wis. Starting values are 20 HP, 100 mana, 100 move.\n"
            "- Equipment, spells and skills that raise stats aren't included.\n\n"
            + self.class_table() + "\n" + self.race_table()
        )


def analyse(world: World) -> CharacterAnalysis:
    return CharacterAnalysis(world)


def render(world: World) -> str:
    a = analyse(world)
    lo, hi = a.xp_extremes
    out = [C.GENERATED_NOTE, "\n# Characters: classes and races by level\n\n", "## Headline findings\n\n",
           f"- **XP per level** ranges from {lo.xp_per_level} ({lo.label}) to {hi.xp_per_level} ({hi.label}).\n"]
    for c in CLASSES:
        best, worst = a.best_worst(c, a.hp91)
        out.append(f"- **{c}** HP at level {C.HERO_LEVEL}: {a.hp91(best):.0f} ({best.race.name}) to "
                   f"{a.hp91(worst):.0f} ({worst.race.name}).\n")
    out.append("\n## Method\n\n" + a.method())
    out.append("\n## 1. XP per level\n\n" + a.xp_table())
    out.append(f"\n## 2. HP at level {C.HERO_LEVEL}\n\n" + a.final_table("hp"))
    out.append(f"\n## 3. Mana at level {C.HERO_LEVEL}\n\n" + a.final_table("mana"))
    out.append(f"\n## 4. Stats: start → trainable max\n\n" + a.stats_table())
    out.append(f"\n## 5. Stat bonuses at level {C.HERO_LEVEL}\n\n" + a.combat_table())
    out.append("\n## 6. Human HP and mana at every level\n\n" + a.per_level_table())
    return "".join(out)


def write_csv(world: World, path: Path) -> None:
    rows = []
    for b in analyse(world).builds:
        for lvl, s in b.levels.items():
            rows.append([b.race.name, b.cls.name, lvl, b.xp_per_level, round(s.hp, 1), round(s.mana, 1),
                         round(s.move, 1), round(s.practices, 1)] + [s.stats[x] for x in STATS])
    C.write_csv(path, ["race", "class", "level", "xp_per_level", "hp", "mana", "move", "practices"] + STATS, rows)
