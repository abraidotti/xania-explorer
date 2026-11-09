"""The names a client needs to make choices the MUD accepts: races and classes at creation, the skills and spells
each class learns and when, and directions. Read from the C++ tables, so they follow the checkout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..areafile.flags import DIRECTIONS
from .character_tables import load_pc_races
from .cpp_tables import CLASSES, load_skills, starting_skills

HERO_LEVEL = 91


@dataclass(frozen=True)
class AbilityInfo:
    name: str
    level: int  # the level the class can learn it
    is_spell: bool
    in_default: bool  # part of the default package offered at creation (Customize: N)
    min_mana: int
    beats: int  # lag in pulses after use


def classes() -> list[str]:
    return list(CLASSES)


def pc_races(src_dir: Path | None = None) -> list[str]:
    return list(load_pc_races(src_dir))


def abilities(cls: str, src_dir: Path | None = None) -> list[AbilityInfo]:
    """Every skill and spell ``cls`` can learn by hero level, in learning order."""
    if cls not in CLASSES:
        raise KeyError(f"no class named {cls!r}")
    default = starting_skills(cls, src_dir)
    out = []
    for s in load_skills(src_dir).values():
        if s.name == "reserved" or s.rating_for(cls) <= 0:
            continue
        lvl = s.learn_level(cls)
        if lvl is not None and lvl <= HERO_LEVEL:
            out.append(AbilityInfo(s.name, max(1, lvl), s.is_spell, s.name in default, s.min_mana, s.beats))
    return sorted(out, key=lambda a: (a.level, a.name))


def directions() -> list[str]:
    return list(DIRECTIONS)
