"""Skills & spells: what each class can learn as it levels, what practising it costs, and how
attack spells keep up with mob HP.

Model (human, default package; see Characters):
- **Available** = skills/spells the class can learn by that level (`skill_table` level for the class,
  rating > 0). Skills outside the default package must be bought later with trains (`gain`).
- **Practice budget**: practices earned (5 at creation + wis-based per level) against the practices
  needed to take every default-package skill available so far from 1% to the 75% adept limit, at
  `int_app.learn / difficulty` per practice (act_info.cpp:1604).
- **Attack spells**: the best direct-damage spell in the class's default package at each level,
  cast at the caster's level against a same-level mob (50% save chance), at the 75%→100% skill
  assumption used for Combat.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from ..areafile.world import World
from ..source.cpp_tables import CLASSES, Skill, load_skills, starting_skills
from ..source.character_tables import NEWBIE_PRACS
from ..source.spell_tables import DamageSpell, load_damage_spells, mana_cost, save_chance
from . import characters as CH
from . import combat as CB
from . import common as C
from . import mobs as M

ROUND_PULSES = 12  # a combat round is 3 s = 12 pulses; a cast lags the caster `beats` pulses


@dataclass
class Ability:
    skill: Skill
    level: int  # level the class can learn it
    in_default: bool

    @property
    def name(self) -> str:
        return self.skill.name


@dataclass
class SpellChoice:
    level: int
    ability: Ability
    spell: DamageSpell
    damage: float  # expected damage per cast (after saves and cast failures)
    mana: int

    @property
    def per_round(self) -> float:
        return self.damage * ROUND_PULSES / max(1, self.ability.skill.beats)


class SkillAnalysis:
    def __init__(self, world: World):
        self.world = world
        self.skills = load_skills(world.src_dir)
        self.damage_spells = load_damage_spells(world.src_dir)
        self.chars = CH.analyse(world)
        self.combat = CB.analyse(world)
        self.mobs = M.analyse(world)
        self.abilities = {c: self._abilities(c) for c in CLASSES}
        self.spells = {c: {lvl: self._best_spell(c, lvl) for lvl in C.LEVELS} for c in CLASSES}

    def _abilities(self, cls: str) -> list[Ability]:
        default = starting_skills(cls, self.world.src_dir)
        out = []
        for s in self.skills.values():
            if s.name == "reserved" or s.rating_for(cls) <= 0:
                continue
            lvl = s.learn_level(cls)
            if lvl is not None and lvl <= C.HERO_LEVEL:
                out.append(Ability(s, max(1, lvl), s.name in default))
        return sorted(out, key=lambda a: (a.level, a.name))

    # -- availability --------------------------------------------------------------------
    def available(self, cls: str, level: int, default_only: bool = False) -> list[Ability]:
        return [a for a in self.abilities[cls] if a.level <= level and (a.in_default or not default_only)]

    def new_at(self, cls: str, level: int) -> list[Ability]:
        return [a for a in self.abilities[cls] if a.level == level]

    def dry_spell(self, cls: str) -> tuple[int, int]:
        """Longest run of levels (after 1) with nothing new to learn."""
        best, start = (0, 0), None
        for lvl in list(range(2, C.HERO_LEVEL + 1)) + [C.HERO_LEVEL + 1]:
            empty = lvl <= C.HERO_LEVEL and not self.new_at(cls, lvl)
            if empty and start is None:
                start = lvl
            if not empty and start is not None:
                if lvl - start > best[1] - best[0] + (1 if best != (0, 0) else 0):
                    best = (start, lvl - 1)
                start = None
        return best

    # -- practice budget -----------------------------------------------------------------------
    def practice_cost(self, cls: str, ability: Ability) -> int:
        build = self.chars.build("human", cls)
        intel = build.at(min(C.HERO_LEVEL, ability.level)).stats["int"]
        gain = build.tables.int_app[intel] // max(1, ability.skill.difficulty(cls))
        return math.ceil((CB.ADEPT - 1) / gain) if gain > 0 else 999

    def practices_earned(self, cls: str, level: int) -> float:
        return NEWBIE_PRACS + self.chars.build("human", cls).at(level).practices

    def practices_needed(self, cls: str, level: int) -> int:
        return sum(self.practice_cost(cls, a) for a in self.available(cls, level, default_only=True))

    # -- attack spells -------------------------------------------------------------------------
    def _best_spell(self, cls: str, level: int) -> SpellChoice | None:
        best = None
        for a in self.available(cls, level, default_only=True):
            spell = self.damage_spells.get(a.skill.spell_fun)
            if not spell:
                continue
            skill = CB.pc_skill(level, a.level) / 100
            dmg = spell.expected(level, save_chance(level, level)) * skill
            choice = SpellChoice(level, a, spell, dmg, mana_cost(a.skill.min_mana, level, a.level))
            if best is None or choice.per_round > best.per_round:
                best = choice
        return best

    def mob_hp(self, level: int) -> float | None:
        fights = self.combat.results[("knight", level)].fights
        return C.median_or(m.mob.hit.average for m, _ in fights)

    def casts_to_kill(self, cls: str, level: int) -> float | None:
        sp, hp = self.spells[cls][level], self.mob_hp(level)
        return hp / sp.damage if sp and hp and sp.damage > 0 else None

    def kills_per_mana_bar(self, cls: str, level: int) -> float | None:
        sp, hp = self.spells[cls][level], self.mob_hp(level)
        if not sp or not hp:
            return None
        mana = self.chars.build("human", cls).at(level).mana
        return mana / sp.mana * sp.damage / hp

    def melee_per_round(self, cls: str, level: int) -> float | None:
        return self.combat.results[(cls, level)].weighted_mean("pc_dpr")

    # -- tables --------------------------------------------------------------------------------
    def class_table(self, cls: str) -> str:
        rows = [[a.level, a.name, "spell" if a.skill.is_spell else "skill", "yes" if a.in_default else "",
                 a.skill.difficulty(cls), self.practice_cost(cls, a) if a.in_default else None]
                for a in self.abilities[cls]]
        return C.table(["Level", "Skill/spell", "Kind", "Default package", "Difficulty", "Practices to adept"], rows)

    def spell_table(self, cls: str) -> str:
        rows = []
        for b in C.bands():
            sp = self.spells[cls][b.hi]
            rows.append([b.label, sp.ability.name if sp else None, round(sp.damage) if sp else None,
                         sp.mana if sp else None, _r(self.casts_to_kill(cls, b.hi)),
                         _r(self.kills_per_mana_bar(cls, b.hi)),
                         round(sp.per_round) if sp else None, _r(self.melee_per_round(cls, b.hi))])
        return C.table(["Levels (at top level)", "best attack spell", "damage/cast", "mana/cast", "casts to kill",
                        "kills per full mana", "spell dmg/round", "melee dmg/round"], rows)

    def damage_spell_table(self) -> str:
        rows = []
        for s in self.skills.values():
            sp = self.damage_spells.get(s.spell_fun)
            if sp:
                rows.append([s.name, " / ".join(str(x) for x in s.levels), s.min_mana, s.beats,
                             round(sp.expected(10)), round(sp.expected(30)), round(sp.expected(60)),
                             round(sp.expected(91)), sp.formula])
        return C.table(["Spell", "levels m/c/k/b", "min mana", "lag (pulses)", "dmg @10", "@30", "@60", "@91",
                        "formula"], rows)

    def method(self) -> str:
        return (__doc__.split("\n\n", 1)[1].strip() + "\n\n"
                "- **Expected spell damage** = mean of the table roll (½× to 2× the table value) × (1 − save chance/2) "
                "× cast success (skill %). Mana per cast = `max(min_mana, 100 / (2 + level − level learned))` "
                "(magic.cpp:582). A cast lags the caster for the spell's beats; damage per round scales by 12 / beats.\n"
                "- **Mob HP** = the median combat mob within ±2 levels (as in Combat).\n"
                "- Healing, buffs, debuffs and area spells aren't valued here; chain lightning counts its first "
                "target only.\n")


def _r(v):
    return None if v is None else round(v, 1)


def analyse(world: World) -> SkillAnalysis:
    return C.cached(world, "skills", SkillAnalysis)


def render(world: World) -> str:
    a = analyse(world)
    out = [C.GENERATED_NOTE, "\n# Skills & spells by level\n\n", "## Headline findings\n\n"]
    for c in CLASSES:
        lo, hi = a.dry_spell(c)
        out.append(f"- **{c}**: {len(a.abilities[c])} learnable by level {C.HERO_LEVEL}; longest wait for something "
                   f"new {lo}–{hi}; practices needed {a.practices_needed(c, C.HERO_LEVEL)} vs earned "
                   f"{a.practices_earned(c, C.HERO_LEVEL):.0f}.\n")
    out.append("\n## Method\n\n" + a.method())
    for c in CLASSES:
        out.append(f"\n## {c.capitalize()}: attack spells\n\n" + a.spell_table(c))
        out.append(f"\n## {c.capitalize()}: everything learnable\n\n" + a.class_table(c))
    out.append("\n## Damage spells\n\n" + a.damage_spell_table())
    return "".join(out)


def write_csv(world: World, path: Path) -> None:
    a = analyse(world)
    rows = []
    for c in CLASSES:
        for lvl in C.LEVELS:
            sp = a.spells[c][lvl]
            rows.append([c, lvl, len(a.available(c, lvl)), len(a.available(c, lvl, True)), len(a.new_at(c, lvl)),
                         round(a.practices_earned(c, lvl), 1), a.practices_needed(c, lvl),
                         sp.ability.name if sp else "", _r(sp.damage) if sp else "", sp.mana if sp else "",
                         _r(a.casts_to_kill(c, lvl)), _r(a.kills_per_mana_bar(c, lvl)),
                         _r(sp.per_round) if sp else "", _r(a.melee_per_round(c, lvl))])
    C.write_csv(path, ["class", "level", "available", "available_default", "new", "practices_earned",
                       "practices_needed", "best_spell", "spell_damage", "spell_mana", "casts_to_kill",
                       "kills_per_mana_bar", "spell_dmg_per_round", "melee_dmg_per_round"], rows)
