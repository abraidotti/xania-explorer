"""Per-case predictions from the assessment models, for tools that test the live MUD against them.

The assessments aggregate over every mob of a level; these functions answer one case: a default human build of
``cls`` at ``level`` (as in Characters and Combat) against one mob, or casting one spell. They return expected
values with the models' assumptions (default skill package, skills at the Combat model's assumed %, best kit
from Equipment), so a live test should compare an average over many trials, not a single fight.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..areafile.world import World
from ..source.cpp_tables import load_skills
from ..source.spell_tables import load_damage_spells, mana_cost, save_chance
from . import combat as CB
from . import difficulty as DF
from . import skills as SK


@dataclass(frozen=True)
class FightPrediction:
    cls: str
    level: int
    mob_vnum: int
    mob_level: int
    player_hp: float
    hit_chance: float  # player's chance per swing to land
    mob_hit_chance: float  # the mob's chance per swing to land on the player
    rounds: float  # rounds to kill the mob (inf if the player can't hurt it)
    damage_taken: float  # the straight fight
    encounter_damage: float  # including helpers that join (Combat's group-fight model)
    xp: float

    @property
    def seconds(self) -> float:
        return self.rounds * CB.ROUND_SECONDS

    @property
    def hp_lost_share(self) -> float:
        return self.encounter_damage / self.player_hp if self.player_hp else float("inf")

    @property
    def deadly(self) -> bool:
        return self.encounter_damage >= self.player_hp


def _mob(a: CB.CombatAnalysis, mob_vnum: int) -> CB.MobFighter:
    found = next((m for m in a.mobs if m.mob.vnum == mob_vnum), None)
    if found is None:
        raise KeyError(f"mob {mob_vnum} isn't a combat mob in this world")
    return found


def predict_fight(world: World, cls: str, level: int, mob_vnum: int, caster: bool = False) -> FightPrediction:
    """The expected fight of a default ``cls`` at ``level`` against mob ``mob_vnum``. ``caster`` adds the class's
    self-buffs and its best attack spell while a full mana bar lasts (Combat's fight_with_spells)."""
    a = CB.analyse(world)
    m = _mob(a, mob_vnum)
    p = a.player(cls, level, buffed=caster)
    if caster:
        spell = SK.analyse(world).spells[cls].get(level)
        f = a.fight_with_spells(p, m, spell, a.chars.build("human", cls).at(level).mana)
    else:
        f = a.fight(p, m)
    return FightPrediction(cls, level, mob_vnum, m.mob.level, p.hp, f.hit_pc, f.hit_mob, f.rounds, f.damage_taken,
                           a.encounter_damage(p, m, f), f.xp)


@dataclass(frozen=True)
class SpellPrediction:
    spell: str
    caster_level: int
    victim_level: int
    skill: float  # caster's skill %, the chance a cast doesn't fail
    save_chance: float  # victim's chance to save (halves the damage)
    mana: int
    beats: int  # lag in pulses after casting (4 pulses = 1 second)
    damage_min: float | None  # one successful cast, no save (None for dice spells)
    damage_max: float | None
    damage_expected: float  # per successful cast, averaged over saves

    @property
    def per_cast(self) -> float:
        """Expected damage per cast attempt, counting failed casts."""
        return self.damage_expected * self.skill / 100


def predict_spell(world: World, cls: str, spell: str, caster_level: int, victim_level: int,
                  skill: float | None = None) -> SpellPrediction:
    """A damage spell cast by a ``cls`` of ``caster_level`` on a victim of ``victim_level``. ``skill`` is the
    caster's % in it; by default the Combat model's assumption for that level (75% when learned, 100% by 30)."""
    s = load_skills(world.src_dir).get(spell)
    if s is None or not s.is_spell:
        raise KeyError(f"{spell!r} isn't a spell")
    ds = load_damage_spells(world.src_dir).get(s.spell_fun)
    if ds is None:
        raise KeyError(f"{spell!r} isn't a direct-damage spell")
    learned = s.learn_level(cls)
    if learned is None:
        raise ValueError(f"a {cls} can't learn {spell!r}")
    pct = CB.pc_skill(caster_level, learned) if skill is None else skill
    save = save_chance(caster_level, victim_level)
    if ds.table is None:
        lo = hi = None
    else:
        t = ds.values[max(0, min(caster_level, len(ds.values) - 1))]
        lo, hi = t // 2, t * 2
    return SpellPrediction(spell, caster_level, victim_level, pct, save * 100,
                           mana_cost(s.min_mana, caster_level, max(1, learned)), s.beats, lo, hi,
                           ds.expected(caster_level, save))


def area_profile(world: World, area: str) -> DF.AreaProfile:
    """The area's difficulty profile (Area difficulty), by name or file name."""
    a = world.area_named(area)
    if a is None:
        raise KeyError(f"no area named {area!r}")
    found = next((p for p in DF.analyse(world).areas if p.name == a.name), None)
    if found is None:
        raise KeyError(f"{a.name} has no combat mobs to profile")
    return found
