"""Combat & experience: what a straight melee fight looks like at every level, per class.

For each class (human, default build, see Characters) at each level 1–91, fight every combat mob
within ±2 levels (the mobs a player of that level would hunt), using the C++ formulas:

- the player wields the best weapon of a starting type usable at that level (see Weapons) and wears
  the best-AC kit (see Equipment), including whatever hitroll/damroll that kit carries;
- weapon and combat skills are practised to adept (75%) when learned and improve with use to 100% by
  level 30 (an assumption);
- mobs use their real stats: level-based stats and skills (db.cpp create_mobile, Char::get_skill),
  file hitroll/damroll/AC, the weapon or shield their resets equip.

Expected values are used throughout (hit chances, extra attacks, parry/dodge/block, damage). Spells,
affects (sanctuary, haste…), resistances, special procedures and mob skills like bash are not modelled,
so mages and clerics look weaker here than they play: see Skills & spells for spell damage.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from ..areafile.world import World
from ..source.cpp_tables import CLASSES, load_skills
from . import characters as CH
from . import common as C
from . import equipment as E
from . import mobs as M
from . import weapons as W

WINDOW = 2  # fight mobs within ±2 levels
ADEPT = 75
SKILL_AT_30 = 100
ROUND_SECONDS = 3  # PULSE_VIOLENCE
FULL_TIME_FACTOR_HOURS = 1.5  # xp_compute: full XP needs >= 6 quarter-hours played per level

NPC_TO_HIT_AC0 = -4  # HitChance.cpp
NPC_TO_HIT_AC32 = {"Warrior": -76, "Thief": -70, "Cleric": -66, "Mage": -63}
NPC_DEFAULT_AC32 = -70


def interpolate(level: int, v0: int, v32: int) -> int:
    """db.cpp:1676 (C++ integer division truncates toward zero)."""
    return v0 + int(level * (v32 - v0) / 32)


def hit_chance(to_hit_ac: float, victim_ac: float) -> float:
    """HitChance.cpp: both ACs are made positive (minimum 1), ratio clamped to 10–95%."""
    attack = max(1.0, -to_hit_ac) if to_hit_ac < 0 else 1.0
    defence = max(1.0, -victim_ac) if victim_ac < 0 else 1.0
    return min(95.0, max(10.0, attack / defence * 100)) / 100


def pc_skill(level: int, learned_at: int | None) -> float:
    """Assumed PC skill %: 75 when learned, rising to 100 by level 30 through use."""
    if learned_at is None or level < learned_at:
        return 0.0
    return min(SKILL_AT_30, ADEPT + (SKILL_AT_30 - ADEPT) * min(level, 30) / 30)


def enhanced_damage_factor(skill: float) -> float:
    """one_hit: roll d100; if <= skill, damage += damage × roll / 100. Expected multiplier."""
    s = int(skill)
    return 1 + sum(range(1, s + 1)) / 100 / 100


def base_exp(level_range: int) -> int:
    """xp_compute's table of base XP by (victim level − killer level)."""
    table = {-9: 1, -8: 2, -7: 5, -6: 9, -5: 11, -4: 22, -3: 33, -2: 55, -1: 72, 0: 85, 1: 100, 2: 120, 3: 144,
             4: 160}
    if level_range > 4:
        return 150 + 20 * (level_range - 4)
    return table.get(level_range, 0)


def xp_per_kill(killer_level: int, victim_level: int, victim_alignment: int, no_align: bool) -> float:
    """Expected solo XP for a neutral player with full played-time credit (fight.cpp:1389)."""
    xp = float(base_exp(victim_level - killer_level))
    if not no_align:
        if victim_alignment > 500 or victim_alignment < -500:
            xp *= 1.25
        elif victim_alignment > 350 or victim_alignment < -350:
            xp *= 1.13
    xp = int(xp)
    if killer_level < 6:
        xp = 10 * xp // (killer_level + 4)
    if 35 < killer_level < 70:
        xp = xp * 100 // (killer_level // 3 + 100)
    if killer_level >= 70:
        xp = int(xp * 100 / (killer_level / 2.5 + 100))
    return xp * 1.5  # solo: (xp × level / total_levels) × 1.5; the ±25% random roll averages out


# -- mob side --------------------------------------------------------------------------
@dataclass
class MobFighter:
    info: M.MobInfo
    weapon_avg: float | None  # wielded weapon dice average (None = unarmed)
    has_shield: bool

    @property
    def mob(self):
        return self.info.mob

    @cached_property
    def cls(self) -> str | None:
        acts = set(self.mob.act_names)
        return next((c for c in ("Warrior", "Thief", "Cleric", "Mage") if c in acts), None)

    def stat(self, name: str) -> int:
        """db.cpp create_mobile: 11 + level/4, class and size adjustments."""
        base = min(25, 11 + self.mob.level // 4)
        bump = {"Warrior": {"str": 3, "con": 2, "int": -1}, "Thief": {"dex": 3, "int": 1, "wis": -1},
                "Cleric": {"wis": 3, "dex": -1, "str": 1}, "Mage": {"int": 3, "str": -1, "dex": 1}}
        value = base + bump.get(self.cls or "", {}).get(name, 0)
        if name == "dex" and "Fast" in self.mob.off_names:
            value += 2
        size = ["tiny", "small", "medium", "large", "huge", "giant"].index(self.mob.body_size) - 2
        if name in ("str", "con"):
            value += size
        return max(3, min(25, value))

    def skill(self, which: str) -> float:
        """Char::get_skill for NPCs."""
        lvl = self.mob.level
        fighter = self.cls in ("Warrior", "Thief")
        if which == "weapon":
            return min(100, 40 + 5 * lvl // 2) if self.weapon_avg else min(100, 40 + 2 * lvl)
        if which == "defence":
            return min(100, 15 + (lvl // 2 if fighter else lvl // 3))
        if which == "second":
            return max(25, lvl // 2) if fighter else 0
        if which == "third":
            return max(0, lvl - 30) if self.cls == "Warrior" else 0
        return 0

    def attacks_per_round(self) -> float:
        second = self.skill("second") / 2 / 100
        third = second * self.skill("third") / 4 / 100  # only if the 2nd landed (fight.cpp mob_hit)
        fast = 1 if "Fast" in self.mob.off_names else 0
        return 1 + fast + second + third

    def damage_per_hit(self, tables) -> float:
        skill = self.skill("weapon")
        if self.weapon_avg:
            dam = self.weapon_avg * skill / 100
        else:
            dam = self.mob.damage.number * (self.mob.damage.sides + 1) / 2  # bonus moves to damroll
        damroll = self.mob.damage.bonus + tables.str_app[self.stat("str")][1]
        return max(1.0, dam + damroll * min(100, skill) / 100)

    def to_hit_ac(self, tables) -> float:
        v32 = NPC_TO_HIT_AC32.get(self.cls or "", NPC_DEFAULT_AC32)
        hitroll = self.mob.hitroll + tables.str_app[self.stat("str")][0]
        return interpolate(self.mob.level, NPC_TO_HIT_AC0, v32) * self.skill("weapon") / 100 - hitroll

    def armour_class(self, tables) -> float:
        return sum(self.mob.ac) / 4 + tables.dex_app[self.stat("dex")]


def mob_fighters(world: World) -> list[MobFighter]:
    """Combat mobs with the weapon/shield their E resets equip (wear locations 16 = wield, 11 = shield)."""
    weapons, shields = {}, set()
    for af in world.files:
        last = None
        for r in af.resets:
            if r.command == "M":
                last = r.arg1
            elif r.command == "E" and last is not None and r.arg1 in world.objects:
                obj = world.objects[r.arg1]
                if r.arg3 == 16 and obj.type_name == "Weapon" and last not in weapons:
                    weapons[last] = (int(obj.values[1]) * int(obj.values[2]) + int(obj.values[1])) / 2
                elif r.arg3 == 11:
                    shields.add(last)
    return [MobFighter(i, weapons.get(i.mob.vnum), i.mob.vnum in shields)
            for i in M.collect(world) if i.category == "combat"]


# -- player side -------------------------------------------------------------------------
@dataclass
class Fight:
    hit_pc: float  # player's chance per swing to land (after mob parry/dodge/block)
    hit_mob: float  # mob's chance per swing to land on the player
    pc_dpr: float  # player's expected damage per round
    mob_dpr: float
    rounds: float  # rounds to kill the mob
    damage_taken: float
    xp: float


@dataclass
class LevelResult:
    cls: str
    level: int
    hp: float
    fights: list[tuple[MobFighter, Fight]] = field(default_factory=list)

    def median(self, attr: str) -> float | None:
        vals = [getattr(f, attr) for _, f in self.fights]
        return statistics.median(vals) if vals else None

    @property
    def weight(self) -> float:
        return sum(m.info.population for m, _ in self.fights)

    def weighted_mean(self, attr: str) -> float | None:
        total = self.weight
        if not total:
            return None
        return sum(getattr(f, attr) * m.info.population for m, f in self.fights) / total

    @property
    def deadly_share(self) -> float | None:
        """Share of the mob population that would deal more than the player's max HP before dying."""
        total = self.weight
        if not total:
            return None
        return sum(m.info.population for m, f in self.fights if f.damage_taken >= self.hp) / total

    @property
    def kills_per_level(self) -> float | None:
        xp = self.weighted_mean("xp")
        return CH.exp_per_level(CH.DEFAULT_GROUP_POINTS, 100) / xp if xp else None

    @property
    def minutes_per_level(self) -> float | None:
        kills, rounds = self.kills_per_level, self.weighted_mean("rounds")
        return kills * rounds * ROUND_SECONDS / 60 if kills and rounds else None


class CombatAnalysis:
    def __init__(self, world: World):
        self.world = world
        self.chars = CH.analyse(world)
        self.tables = self.chars.builds[0].tables
        self.equip = E.analyse(world)
        self.weapons = W.analyse(world)
        self.skills = load_skills(world.src_dir)
        self.mobs = mob_fighters(world)
        self.by_level = {lvl: [m for m in self.mobs if abs(C.usable_level(m.mob.level) - lvl) <= WINDOW]
                         for lvl in C.LEVELS}
        self.results = {(c, lvl): self._level(c, lvl) for c in CLASSES for lvl in C.LEVELS}

    def learned_at(self, cls: str, skill: str) -> int | None:
        s = self.skills.get(skill)
        if s is None or s.rating_for(cls) <= 0:
            return None
        return s.learn_level(cls)

    def _level(self, cls: str, level: int) -> LevelResult:
        build = self.chars.build("human", cls)
        state = build.at(level)
        t = self.tables
        st = state.stats
        kit = self.equip.ac_kits[level]
        gear_hit, gear_dam, gear_ac = kit.total("hitroll"), kit.total("damroll"), kit.total("ac")
        weapon_avg = self.weapons.best_start[cls][level]
        weapon_skill = pc_skill(level, 1) if weapon_avg else 0
        hitroll = gear_hit + t.str_app[st["str"]][0]
        damroll = gear_dam + t.str_app[st["str"]][1]
        pc_ac = -gear_ac + t.dex_app[st["dex"]]
        to_hit_ac = interpolate(level, build.cls.to_hit_ac_level0, build.cls.to_hit_ac_level32) * \
            (weapon_skill or 40) / 100 - hitroll
        second = pc_skill(level, self.learned_at(cls, "second attack"))
        third = pc_skill(level, self.learned_at(cls, "third attack"))
        attacks = 1 + second / 2 / 100 + third / 4 / 100
        enhanced = enhanced_damage_factor(pc_skill(level, self.learned_at(cls, "enhanced damage")))
        if weapon_avg:
            per_hit = weapon_avg * weapon_skill / 100 * enhanced + damroll * min(100, weapon_skill) / 100
        else:  # unarmed (fight.cpp one_hit)
            per_hit = (1 + 2 * level / 3) / 2 + damroll
        pc_def = {k: pc_skill(level, self.learned_at(cls, k)) for k in ("parry", "dodge", "shield block")}
        res = LevelResult(cls, level, state.hp)
        for m in self.by_level[level]:
            ml = m.mob.level
            # player attacking the mob
            avoid = 0.0
            mob_def = m.skill("defence")
            if m.weapon_avg:
                avoid += max(5, mob_def / 3 + ml - level) / 100
            avoid += (1 - avoid) * max(5, mob_def / 3 + (m.stat("dex") - st["dex"]) + ml - level) / 100
            if m.has_shield:
                avoid += (1 - avoid) * max(5, mob_def / 3 + ml - level) / 100
            hit_pc = hit_chance(to_hit_ac, m.armour_class(t)) * (1 - min(avoid, 0.95))
            pc_dpr = attacks * hit_pc * per_hit
            # mob attacking the player
            pavoid = 0.0
            if weapon_avg:
                pavoid += max(5, pc_def["parry"] / 3 + level - ml) / 100
            pavoid += (1 - pavoid) * max(5, pc_def["dodge"] / 3 + (st["dex"] - m.stat("dex")) + level - ml) / 100
            if pc_def["shield block"] or kit.picks.get("shield"):
                pavoid += (1 - pavoid) * max(5, pc_def["shield block"] / 3 + level - ml) / 100
            hit_mob = hit_chance(m.to_hit_ac(t), pc_ac) * (1 - min(pavoid, 0.95))
            mob_dpr = m.attacks_per_round() * hit_mob * m.damage_per_hit(t)
            rounds = m.mob.hit.average / pc_dpr if pc_dpr > 0 else float("inf")
            xp = xp_per_kill(level, ml, m.mob.alignment, "NoAlign" in m.mob.act_names)
            res.fights.append((m, Fight(hit_pc, hit_mob, pc_dpr, mob_dpr, rounds, rounds * mob_dpr, xp)))
        return res

    # -- facts ---------------------------------------------------------------------------
    def series(self, cls: str, attr: str) -> dict[int, float | None]:
        out = {}
        for lvl in C.LEVELS:
            r = self.results[(cls, lvl)]
            out[lvl] = getattr(r, attr) if attr in ("deadly_share", "kills_per_level", "minutes_per_level") \
                else r.weighted_mean(attr)
        return out

    def hours_to_hero(self, cls: str) -> float:
        return sum(v for v in self.series(cls, "minutes_per_level").values() if v) / 60

    def band_rows(self, cls: str) -> list[list]:
        rows = []
        for b in C.bands():
            rs = [self.results[(cls, lvl)] for lvl in range(b.lo, b.hi + 1)]

            def avg(attr):
                vals = [getattr(r, attr) if attr in ("deadly_share", "kills_per_level", "minutes_per_level")
                        else r.weighted_mean(attr) for r in rs]
                vals = [v for v in vals if v is not None]
                return sum(vals) / len(vals) if vals else None

            share = avg("deadly_share")
            rows.append([b.label, _pct(avg("hit_pc")), _pct(avg("hit_mob")), _r(avg("pc_dpr")), _r(avg("mob_dpr")),
                         _r(avg("rounds")), _r(avg("xp")), _r(avg("kills_per_level")),
                         _r(avg("minutes_per_level")), _pct(share)])
        return rows

    def class_table(self, cls: str) -> str:
        return C.table(["Levels", "you hit", "it hits", "your dmg/round", "its dmg/round", "rounds to kill",
                        "XP/kill", "kills/level", "combat min/level", "deadly mobs"], self.band_rows(cls))

    def xp_table(self) -> str:
        rows = [[d, base_exp(d)] + [round(xp_per_kill(lvl, lvl + d, 0, True)) for lvl in (3, 20, 50, 80)]
                for d in range(-9, 9)]
        return C.table(["Mob level − yours", "base XP", "solo XP at 3", "at 20", "at 50", "at 80"], rows)

    def method(self) -> str:
        return (__doc__.split("\n\n", 1)[1].strip() + "\n\n"
                "- **Hit chance** (HitChance.cpp): attacker to-hit AC = interpolate(level, class AC at 0, at 32) × "
                "weapon skill % − hitroll; ratio to the defender's AC (made positive, minimum 1), clamped 10–95%. "
                "Then the defender's parry (if armed), dodge and shield block (if a shield is worn) each get "
                "`skill/3 + level difference` (minimum 5%).\n"
                "- **Attacks per round**: 1 + second attack (skill/2 %) + third attack (skill/4 %); mobs also get "
                "+1 if Fast, and their third only if the second landed.\n"
                "- **Damage per hit**: weapon dice × skill % (× enhanced damage) + damroll; mobs fighting unarmed "
                "use their damage dice, with the dice bonus as damroll.\n"
                f"- **Mobs fought** at level L: every combat mob within ±{WINDOW} levels, weighted by population.\n"
                "- **XP per kill**: xp_compute for a neutral, solo player with full played-time credit "
                f"(at least {FULL_TIME_FACTOR_HOURS} h played per level; less and every kill is worth "
                "proportionally less, down to a third). Kills per level = 1,000 XP (human) ÷ mean XP per kill.\n"
                "- **Deadly mobs**: share of that population whose expected damage over the whole fight exceeds "
                "the player's maximum HP.\n"
                f"- **Combat minutes per level** = kills × rounds × {ROUND_SECONDS} s; resting, travel and "
                "searching are not included.\n")


def _pct(v):
    return None if v is None else f"{v:.0%}"


def _r(v):
    return None if v is None else round(v, 1)


def analyse(world: World) -> CombatAnalysis:
    return C.cached(world, "combat", CombatAnalysis)


def render(world: World) -> str:
    a = analyse(world)
    out = [C.GENERATED_NOTE, "\n# Combat & experience by level\n\n", "## Headline findings\n\n"]
    for c in CLASSES:
        out.append(f"- **{c}**: about {a.hours_to_hero(c):.0f} hours of combat to reach level {C.HERO_LEVEL}.\n")
    out.append("\n## Method\n\n" + a.method())
    for c in CLASSES:
        out.append(f"\n## {c.capitalize()}\n\n" + a.class_table(c))
    out.append("\n## XP per kill\n\n" + a.xp_table())
    return "".join(out)


def write_csv(world: World, path: Path) -> None:
    a = analyse(world)
    rows = []
    for (cls, lvl), r in a.results.items():
        rows.append([cls, lvl, round(r.hp), len(r.fights), _r(r.weighted_mean("hit_pc")),
                     _r(r.weighted_mean("hit_mob")), _r(r.weighted_mean("pc_dpr")), _r(r.weighted_mean("mob_dpr")),
                     _r(r.weighted_mean("rounds")), _r(r.weighted_mean("xp")), _r(r.kills_per_level),
                     _r(r.minutes_per_level), _r(r.deadly_share)])
    C.write_csv(path, ["class", "level", "hp", "mobs_fought", "hit_chance", "mob_hit_chance", "dpr", "mob_dpr",
                       "rounds_to_kill", "xp_per_kill", "kills_per_level", "combat_minutes_per_level",
                       "deadly_share"], rows)
