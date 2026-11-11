"""Combat & experience: what a straight melee fight looks like at every level, per class.

For each class (human, default build, see Characters) at each level 1–91, fight every combat mob
within ±2 levels (the mobs a player of that level would hunt), using the C++ formulas:

- the player wields the best weapon of a starting type usable at that level (see Weapons) and wears
  the best-AC kit (see Equipment), including whatever hitroll/damroll that kit carries;
- weapon and combat skills are practised to adept (75%) when learned and improve with use to 100% by
  level 30 (an assumption);
- mobs use their real stats: level-based stats and skills (db.cpp create_mobile, Char::get_skill),
  file hitroll/damroll/AC, the weapon or shield their resets equip.

Expected values are used throughout (hit chances, extra attacks, parry/dodge/block, damage). Mobs' damaging
special procedures (casting and breath, special.cpp) are included, and mobs that assist each other are modelled
separately as group fights. Player spells, affects (sanctuary, haste…), resistances and mob skills like bash are
not modelled, so mages and clerics look weaker here than they play: see Skills & spells for spell damage.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from ..areafile import graph as G
from ..areafile.world import World
from ..areafile import flags as F
from ..source.character_tables import load_race_off_flags, load_race_tolerances
from ..source.cpp_tables import CLASSES, load_skills
from ..source.specials import load_specials, special_damage_per_round
from ..source.spell_tables import save_chance
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


# -- damage tolerances (DamageTolerance.cpp, fight.cpp damage) --------------------------------
PHYSICAL = {"Bash", "Pierce", "Slash"}
IMMUNE, RESISTANT, VULNERABLE = 0.0, 2 / 3, 1.5  # damage(): x0, -= /3, += /2
MATERIAL_VULNERABLE = 1.5  # check_material_vulnerability: wood, silver or iron weapon vs a mob vulnerable to it


def tolerance(imm: frozenset, res: frozenset, vuln: frozenset, damage_type: str) -> float:
    """The damage multiplier ``check_damage_tolerance`` gives a victim with these flags against ``damage_type``.
    For bash/pierce/slash the catch-all Weapon flag is checked first; damage types without a flag of their own
    (Other, Harm) count as Magic. Immune beats resistant beats vulnerable, as in the C++."""
    if damage_type == "None":
        return 1.0
    if damage_type in PHYSICAL:
        if "Weapon" in imm:
            return IMMUNE
        if "Weapon" in res:
            return RESISTANT
        if "Weapon" in vuln:
            return VULNERABLE
    bit = damage_type if damage_type in F.TOLERANCE.values() and damage_type not in ("Other", "Harm") else "Magic"
    if bit in imm:
        return IMMUNE
    if bit in res:
        return RESISTANT
    if bit in vuln:
        return VULNERABLE
    return 1.0


# -- mob side --------------------------------------------------------------------------
@dataclass
class MobFighter:
    info: M.MobInfo
    weapon_avg: float | None  # wielded weapon dice average (None = unarmed)
    has_shield: bool
    special: str | None = None  # spec_fun from the area's #SPECIALS, e.g. "spec_cast_mage"
    off: frozenset = frozenset()  # offensive flags: the file's plus the race's (MobIndexData.cpp merges them)
    imm: frozenset = frozenset()  # tolerance flags, the file's plus the race's (MobIndexData.cpp)
    res: frozenset = frozenset()
    vuln: frozenset = frozenset()

    def takes(self, damage_type: str, material: str = "") -> float:
        """Multiplier on damage of ``damage_type`` dealt to this mob, by a weapon of ``material`` if given."""
        f = tolerance(self.imm, self.res, self.vuln, damage_type)
        if material.capitalize() in ("Wood", "Silver", "Iron") and material.capitalize() in self.vuln:
            f *= MATERIAL_VULNERABLE
        return f

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
        if name == "dex" and "Fast" in self.off:
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
        fast = 1 if "Fast" in self.off else 0
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
    specials = {sp.mob_vnum: sp.spec_fun.lower() for af in world.files for sp in af.specials}
    has_races = (world.src_dir / "Races.cpp").exists()
    race_off = load_race_off_flags(world.src_dir) if has_races else {}
    race_tol = load_race_tolerances(world.src_dir) if has_races else {}
    none = (frozenset(), frozenset(), frozenset())

    def tol(i):
        r = race_tol.get(i.mob.race.lower(), none)
        own = [frozenset(F.decode(getattr(i.mob, k), F.TOLERANCE)) for k in ("imm_flags", "res_flags", "vuln_flags")]
        return [a | b for a, b in zip(own, r)]

    return [MobFighter(i, weapons.get(i.mob.vnum), i.mob.vnum in shields, specials.get(i.mob.vnum),
                       frozenset(i.mob.off_names) | race_off.get(i.mob.race.lower(), frozenset()), *tol(i))
            for i in M.collect(world) if i.category == "combat" and huntable_near_its_level(world, i)]


def huntable(world: World, info, level: int) -> bool:
    """Can a mortal of ``level`` get at the mob: does it spawn in a room that level can see? (Mud School's
    level-30 acolyte and adepts spawn in NewbiesOnly rooms: no one who could fight them can enter.) A mob with no
    spawn rooms counts, as before."""
    rooms = [s.room_vnum for s in info.spawns if s.room_vnum in world.rooms]
    return not rooms or any(G.visible_to(world.rooms[r], level) for r in rooms)


def huntable_near_its_level(world: World, info) -> bool:
    """Huntable at some level within ``WINDOW`` of its own, where Combat would fight it."""
    lvl = C.usable_level(info.mob.level)
    return any(huntable(world, info, L) for L in range(max(1, lvl - WINDOW), min(C.HERO_LEVEL, lvl + WINDOW) + 1))


ASSIST_JOIN = 0.5  # check_assist: a mob helping another mob joins with a coin flip each round
ALIGN_GOOD, ALIGN_EVIL = 350, -350  # Alignment::Amiable / Depraved (Char::is_good / is_evil)


def _align_band(alignment: int) -> int:
    return 1 if alignment >= ALIGN_GOOD else -1 if alignment <= ALIGN_EVIL else 0


def assists(helper: MobFighter, fighter: MobFighter) -> bool:
    """Would ``helper`` join a fight ``fighter`` is in? (check_assist's NPC cases)"""
    o = helper.off
    return ("AssistAll" in o
            or ("AssistRace" in o and helper.mob.race == fighter.mob.race)
            or ("AssistAlign" in o and _align_band(helper.mob.alignment) == _align_band(fighter.mob.alignment))
            or ("AssistVnum" in o and helper.mob.vnum == fighter.mob.vnum))


# -- player side -------------------------------------------------------------------------
BUFF_SPELLS = ("armor", "shield", "stone skin", "bless", "frenzy", "giant strength", "haste", "sanctuary",
               "protection evil")
SANCTUARY_DIVISOR = 1.6  # fight.cpp damage(): adjusted_damage /= 1.6
PULSES_PER_ROUND = 12  # a 3-second combat round; a spell's beats are its lag in pulses


@dataclass(frozen=True)
class Buffs:
    """Self-buffs and what they add (magic.cpp spell_armor, spell_shield, …)."""
    names: tuple[str, ...] = ()
    ac: int = 0  # armour class change (negative is better)
    hitroll: int = 0
    damroll: int = 0
    str: int = 0
    dex: int = 0
    haste: bool = False  # one extra attack per round
    sanctuary: bool = False  # incoming damage ÷ 1.6
    protection_evil: bool = False  # incoming damage from evil attackers −¼


NO_BUFFS = Buffs()


@dataclass(frozen=True)
class Player:
    cls: str
    level: int
    hp: float
    dex: int
    armed: bool
    to_hit_ac: float
    ac: float
    attacks: float
    per_hit: float
    defence: dict
    blocks: bool
    buffs: Buffs = NO_BUFFS
    damage_type: str = "Bash"  # its weapon's (attack word -> Attacks.cpp); unarmed hits bash
    material: str = ""  # its weapon's material (wood, silver and iron hurt mobs vulnerable to them)


@dataclass
class Fight:
    hit_pc: float  # player's chance per swing to land (after mob parry/dodge/block)
    hit_mob: float  # mob's chance per swing to land on the player
    pc_dpr: float  # player's expected damage per round
    mob_dpr: float  # melee
    rounds: float  # rounds to kill the mob
    damage_taken: float  # melee and special procedures, over the whole fight
    xp: float
    spell_dpr: float = 0.0  # expected damage per round from the mob's special (spells, breath)


@dataclass
class LevelResult:
    cls: str
    level: int
    hp: float
    fights: list[tuple[MobFighter, Fight]] = field(default_factory=list)
    # mobs in the level window it can't hurt (immune to its weapon's damage type): nobody hunts those, so they're
    # left out of the averages and listed here
    unhurtable: list[MobFighter] = field(default_factory=list)
    # passive mobs it can't see (invisible, or hidden, without the detect spell): it can't find them to attack
    unseen: list[MobFighter] = field(default_factory=list)

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
        # None when special.cpp (or magic.cpp, for spell damage) isn't in the checkout
        self.specials = load_specials(world.src_dir) if (world.src_dir / "magic.cpp").exists() else None
        self.by_level = {lvl: [m for m in self.mobs if abs(C.usable_level(m.mob.level) - lvl) <= WINDOW
                               and huntable(world, m.info, lvl)] for lvl in C.LEVELS}
        self.results = {(c, lvl): self._level(c, lvl) for c in CLASSES for lvl in C.LEVELS}

    def spell_dpr(self, m: MobFighter, level: int) -> float:
        """Expected damage per round a level-``level`` player takes from the mob's special procedure."""
        if not self.specials or m.special not in self.specials.names:
            return 0.0
        cache = self.__dict__.setdefault("_spell_dpr", {})
        key = (m.mob.vnum, level)
        if key not in cache:
            cache[key] = special_damage_per_round(self.specials, m.special, m.mob.level, m.mob.hit.average, level,
                                                  self.world.src_dir)
        return cache[key]

    def can_see(self, cls: str, level: int, m: MobFighter) -> bool:
        """Can a ``cls`` of ``level`` find ``m`` to attack it (Char::can_see(const Char &), Char.cpp)? Invisible
        mobs need detect invis; hidden ones need detect hidden while they aren't fighting. An aggressive mob attacks
        whoever it can, and a player fights back at what's fighting it, so those always count. Sneak (a random
        chance per look) isn't modelled. The detect spells count from the level the class learns them."""
        aff = set(F.decode(m.mob.affected_by, F.AFFECT))
        if not aff & {"Invisible", "Hide"} or "Aggressive" in m.mob.act_names:
            return True

        def knows(spell: str) -> bool:
            at = self.learned_at(cls, spell)
            return at is not None and at <= level

        if "Invisible" in aff and not knows("detect invis"):
            return False
        return not ("Hide" in aff and not knows("detect hidden"))

    def learned_at(self, cls: str, skill: str) -> int | None:
        s = self.skills.get(skill)
        if s is None or s.rating_for(cls) <= 0:
            return None
        return s.learn_level(cls)

    def buffs(self, cls: str, level: int) -> "Buffs":
        """The self-buffs a default ``cls`` build of ``level`` knows (its default package, as everywhere in this
        model) and can cast, at its own level (magic.cpp)."""
        from ..source.cpp_tables import starting_skills

        start = self.__dict__.setdefault("_start", {})
        if cls not in start:
            start[cls] = starting_skills(cls, self.world.src_dir)
        known = {name for name in BUFF_SPELLS if name in start[cls]
                 and (at := self.learned_at(cls, name)) is not None and at <= level}
        gs = 1 + (level >= 18) + (level >= 25) + (level >= 32)  # giant strength and haste's stat bonus
        return Buffs(
            tuple(n for n in BUFF_SPELLS if n in known),
            ac=-20 * ("armor" in known) - 20 * ("shield" in known) - 40 * ("stone skin" in known)
            + level * ("frenzy" in known),  # frenzy worsens AC by the caster's level
            hitroll=level // 8 * ("bless" in known) + level // 6 * ("frenzy" in known),
            damroll=level // 6 * ("frenzy" in known),
            str=gs * ("giant strength" in known), dex=gs * ("haste" in known),
            haste="haste" in known, sanctuary="sanctuary" in known, protection_evil="protection evil" in known)

    def player(self, cls: str, level: int, buffed: bool = False) -> "Player":
        """The player side of every fight at this class and level (cached); ``buffed`` adds its self-buffs."""
        cache = self.__dict__.setdefault("_players", {})
        if (cls, level, buffed) in cache:
            return cache[(cls, level, buffed)]
        build = self.chars.build("human", cls)
        state = build.at(level)
        t = self.tables
        b = self.buffs(cls, level) if buffed else NO_BUFFS
        top = len(t.str_app) - 1
        st = dict(state.stats, str=min(top, state.stats["str"] + b.str), dex=min(top, state.stats["dex"] + b.dex))
        kit = self.equip.ac_kits[level]
        gear_hit, gear_dam, gear_ac = kit.total("hitroll"), kit.total("damroll"), kit.total("ac")
        weapon_avg = self.weapons.best_start[cls][level]
        wielded = self.weapons.best_start_weapon[cls][level]
        damage_type = F.ATTACKS.get(str(wielded.obj.values[3]), "Bash") if wielded else "Bash"
        material = wielded.obj.material if wielded else ""
        weapon_skill = pc_skill(level, 1) if weapon_avg else 0
        hitroll = gear_hit + t.str_app[st["str"]][0] + b.hitroll
        damroll = gear_dam + t.str_app[st["str"]][1] + b.damroll
        to_hit_ac = (interpolate(level, build.cls.to_hit_ac_level0, build.cls.to_hit_ac_level32)
                     * (weapon_skill or 40) / 100 - hitroll)
        second = pc_skill(level, self.learned_at(cls, "second attack"))
        third = pc_skill(level, self.learned_at(cls, "third attack"))
        enhanced = enhanced_damage_factor(pc_skill(level, self.learned_at(cls, "enhanced damage")))
        if weapon_avg:
            per_hit = weapon_avg * weapon_skill / 100 * enhanced + damroll * min(100, weapon_skill) / 100
        else:  # unarmed (fight.cpp one_hit)
            per_hit = (1 + 2 * level / 3) / 2 + damroll
        pc_def = {k: pc_skill(level, self.learned_at(cls, k)) for k in ("parry", "dodge", "shield block")}
        cache[(cls, level, buffed)] = Player(
            cls, level, state.hp, st["dex"], bool(weapon_avg), to_hit_ac, -gear_ac + t.dex_app[st["dex"]] + b.ac,
            1 + second / 2 / 100 + third / 4 / 100 + b.haste, per_hit, pc_def,
            bool(pc_def["shield block"] or kit.picks.get("shield")), b, damage_type, material)
        return cache[(cls, level, buffed)]

    def fight_with_spells(self, p: "Player", m: MobFighter, spell, mana: float) -> Fight:
        """The fight a caster really has: its buffs on, auto-attacking every round, and casting ``spell`` (a Skills
        SpellChoice) on top while ``mana`` lasts; melee alone after that. Incoming damage is reduced by sanctuary
        (÷1.6) and, against evil mobs, protection from evil (−¼)."""
        f = self.fight(p, m)
        hp = m.mob.hit.average
        rounds = f.rounds
        if spell is not None and spell.mana > 0 and spell.damage > 0:
            # the cast's damage, with the save re-rolled against this mob's level
            skill = spell.damage / spell.spell.expected(p.level, save_chance(p.level, p.level))
            per_cast = spell.spell.expected(p.level, save_chance(p.level, m.mob.level)) * skill \
                * m.takes(spell.spell.damage_type)
            band = _align_band(m.mob.alignment)  # dispel evil/good only hurt evil/good victims
            if (spell.spell.fun == "spell_dispel_evil" and band >= 0) or \
                    (spell.spell.fun == "spell_dispel_good" and band <= 0):
                per_cast = 0.0
            casts = int(mana // spell.mana)
            cast_rounds = casts * spell.ability.skill.beats / PULSES_PER_ROUND
            boosted = f.pc_dpr + per_cast * PULSES_PER_ROUND / max(1, spell.ability.skill.beats)
            if boosted * cast_rounds >= hp:
                rounds = hp / boosted
            elif f.pc_dpr > 0:
                rounds = cast_rounds + (hp - boosted * cast_rounds) / f.pc_dpr
            else:
                rounds = float("inf")
        cut = (1 / SANCTUARY_DIVISOR if p.buffs.sanctuary else 1.0) * \
            (0.75 if p.buffs.protection_evil and _align_band(m.mob.alignment) < 0 else 1.0)
        return Fight(f.hit_pc, f.hit_mob, hp / rounds if rounds else f.pc_dpr, f.mob_dpr * cut, rounds,
                     rounds * (f.mob_dpr + f.spell_dpr) * cut, f.xp, f.spell_dpr * cut)

    def fight(self, p: "Player", m: MobFighter) -> Fight:
        """One straight fight between the player and a mob (expected values)."""
        t, level, ml = self.tables, p.level, m.mob.level
        # player attacking the mob
        avoid = 0.0
        mob_def = m.skill("defence")
        if m.weapon_avg:
            avoid += max(5, mob_def / 3 + ml - level) / 100
        avoid += (1 - avoid) * max(5, mob_def / 3 + (m.stat("dex") - p.dex) + ml - level) / 100
        if m.has_shield:
            avoid += (1 - avoid) * max(5, mob_def / 3 + ml - level) / 100
        hit_pc = hit_chance(p.to_hit_ac, m.armour_class(t)) * (1 - min(avoid, 0.95))
        pc_dpr = p.attacks * hit_pc * p.per_hit * m.takes(p.damage_type, p.material)
        # mob attacking the player
        pavoid = 0.0
        if p.armed:
            pavoid += max(5, p.defence["parry"] / 3 + level - ml) / 100
        pavoid += (1 - pavoid) * max(5, p.defence["dodge"] / 3 + (p.dex - m.stat("dex")) + level - ml) / 100
        if p.blocks:
            pavoid += (1 - pavoid) * max(5, p.defence["shield block"] / 3 + level - ml) / 100
        hit_mob = hit_chance(m.to_hit_ac(t), p.ac) * (1 - min(pavoid, 0.95))
        mob_dpr = m.attacks_per_round() * hit_mob * m.damage_per_hit(t)
        rounds = m.mob.hit.average / pc_dpr if pc_dpr > 0 else float("inf")
        xp = xp_per_kill(level, ml, m.mob.alignment, "NoAlign" in m.mob.act_names)
        spell_dpr = self.spell_dpr(m, level)
        return Fight(hit_pc, hit_mob, pc_dpr, mob_dpr, rounds, rounds * (mob_dpr + spell_dpr), xp, spell_dpr)

    # -- group fights (check_assist, fight.cpp) -------------------------------------------------
    @cached_property
    def helpers(self) -> dict[int, list[tuple[MobFighter, float]]]:
        """For each combat mob: the mobs spawned in its room that would join a fight against it, with how many of
        each (averaged over the mob's spawn rooms). Wandering is ignored: this is the fight where it spawns."""
        by_vnum = {m.mob.vnum: m for m in self.mobs}
        crowd: dict[int, dict[int, int]] = {}
        for m in self.mobs:
            cap = max((s.world_max for s in m.info.spawns), default=0)
            for s in m.info.spawns:
                room = crowd.setdefault(s.room_vnum, {})
                room[m.mob.vnum] = max(room.get(m.mob.vnum, 0), min(max(0, s.room_max), cap))
        out = {}
        for m in self.mobs:
            rooms = [(s.room_vnum, s.room_max) for s in m.info.spawns if s.room_max > 0]
            total = sum(w for _, w in rooms)
            found: dict[int, float] = {}
            for room, w in rooms:
                for vnum, n in crowd.get(room, {}).items():
                    n_help = n - 1 if vnum == m.mob.vnum else n
                    if n_help > 0 and assists(by_vnum[vnum], m):
                        found[vnum] = found.get(vnum, 0.0) + n_help * w / total
            out[m.mob.vnum] = [(by_vnum[v], n) for v, n in found.items()]
        return out

    def encounter_damage(self, p: "Player", m: MobFighter, f: Fight) -> float:
        """Expected damage to clear an encounter that starts with ``m``: its fight, its helpers' blows while they
        join (each with a coin flip per round), then a fight with each helper that joined. A lower bound: helpers
        that join later fights, and blows from several helpers during those fights, aren't counted."""
        helpers = self.helpers.get(m.mob.vnum, [])
        if not helpers or f.rounds == float("inf"):
            return f.damage_taken
        r = f.rounds
        joined = 1 - (1 - ASSIST_JOIN) ** r  # chance a given helper joins before m dies
        present = max(0.0, (r - 1) - (1 - (1 - ASSIST_JOIN) ** max(0.0, r - 1)))  # its expected rounds attacking
        total = f.damage_taken
        cache = self.__dict__.setdefault("_helper_fights", {})
        for h, n in helpers:
            key = (p.cls, p.level, h.mob.vnum)
            if key not in cache:
                cache[key] = self.fight(p, h)
            fh = cache[key]
            total += n * (present * (fh.mob_dpr + fh.spell_dpr) + joined * fh.damage_taken)
        return total

    def _level(self, cls: str, level: int) -> LevelResult:
        p = self.player(cls, level)
        res = LevelResult(cls, level, p.hp)
        for m in self.by_level[level]:
            if not self.can_see(cls, level, m):
                res.unseen.append(m)
                continue
            f = self.fight(p, m)
            if f.pc_dpr <= 0 and m.takes(p.damage_type, p.material) == 0:
                res.unhurtable.append(m)
            else:
                res.fights.append((m, f))
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
                "searching are not included.\n"
                + ("- **Mob specials** (special.cpp, run every 4 s): each casting or breathing special picks the "
                   "player with its own chance (⅛ for most, ¼ for clerics and judges), then a spell drawn the way "
                   "the C++ draws it (a random case that fits the mob's level), cast at the mob's level against "
                   "the player's save. Breath deals `hp/20 + 16` to `hp/15` of the breather's current HP (capped "
                   "at 2000), averaged over a fight in which it falls to 0. Spells that only curse, blind or "
                   "poison count as no damage; dispel evil/good don't affect a neutral player; exorcise isn't "
                   "halved for close alignments, a slight overestimate.\n"
                   if self.specials else "- **Mob specials** aren't modelled: this checkout has no "
                   "`src/special.cpp` (or no `src/magic.cpp`).\n")
                + "- **Offensive flags** include the race's (Races.cpp `race_table`, merged in as MobIndexData.cpp "
                "does), so race-given Fast and assist flags count.\n"
                "- **Group fights** (check_assist, fight.cpp): the mobs spawned in a mob's room that would assist it "
                "(same prototype, race or alignment band, or assist_all), counted from the resets. Over a fight of R "
                "rounds each joins with a 50% chance per round, so it joins at all with chance 1 − ½^R and attacks "
                "for about R − 1 − (1 − ½^(R−1)) rounds; then it has to be fought too. That's a lower bound: helpers "
                "joining later fights aren't counted. Mobs wander, so this is the fight where they spawn.\n"
                "- **Casters with spells and buffs**: a mage or cleric keeps up the buffs in its default package "
                "(armour, shield, stone skin, bless, frenzy, giant strength, haste, sanctuary, protection from evil, "
                "each with its magic.cpp effect: AC, hitroll/damroll, str/dex, an extra attack, incoming damage ÷1.6, "
                "−¼ from evil mobs), keeps auto-attacking, and casts its best attack spell (Skills & spells) on top "
                "until its mana runs out, starting each fight with a full bar. Dispel evil/good only hurt evil/good "
                "mobs.\n")


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
