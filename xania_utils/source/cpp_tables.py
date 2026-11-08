"""Extract game tables that live in C++ source rather than data files.

These are regex/brace-matching readers over specific, stable initialisers in
``xania/src``. They are deliberately narrow: if the C++ layout changes they
should fail loudly (see the asserts) rather than return wrong data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..paths import XaniaPaths


# xania/src/Class.cpp: class_table order == Class::id == index into per-class arrays.
CLASSES = ["mage", "cleric", "knight", "barbarian"]

# SkillTables.hpp rating magic numbers.
SKILL_RATING_UNATTAINABLE = 0
SKILL_RATING_ATTAINABLE = -1  # cross-class: learnable at level 60, difficulty 8
SKILL_RATING_SPECIAL = -2  # assassin group: level 30 with the group, else 60; difficulty 5
_RATING_CONSTANTS = {"SkillRatingUnattainable": 0, "SkillRatingAttainable": -1, "SkillRatingSpecial": -2}
# skills.cpp:37-39
LEVEL_CROSS_CLASS_TRAINING = 60
LEVEL_SPECIAL_CLASS_TRAINING = 30


@dataclass(frozen=True)
class Skill:
    name: str
    slot: int
    min_mana: int
    beats: int  # lag in pulses after use
    levels: tuple[int, ...]  # per class: level at which it can be learned
    ratings: tuple[int, ...]  # per class: creation cost and learning difficulty (higher = harder)
    is_spell: bool

    def level_for(self, cls: str) -> int:
        return self.levels[CLASSES.index(cls)]

    def rating_for(self, cls: str) -> int:
        return self.ratings[CLASSES.index(cls)]

    def learn_level(self, cls: str, assassin: bool = False) -> int | None:
        """``get_skill_level`` (skills.cpp:566) ignoring race bonuses; None = never."""
        rating = self.rating_for(cls)
        if rating > 0:
            return self.level_for(cls)
        if rating == SKILL_RATING_ATTAINABLE:
            return LEVEL_CROSS_CLASS_TRAINING
        if rating == SKILL_RATING_SPECIAL:
            return LEVEL_SPECIAL_CLASS_TRAINING if assassin else LEVEL_CROSS_CLASS_TRAINING
        return None

    def difficulty(self, cls: str) -> int:
        """``get_skill_difficulty`` (skills.cpp:604) ignoring race: divides practice and
        learn-by-use gains; 0 = can't learn."""
        rating = self.rating_for(cls)
        return {SKILL_RATING_ATTAINABLE: 8, SKILL_RATING_SPECIAL: 5}.get(rating, max(rating, 0))


@dataclass(frozen=True)
class Group:
    name: str
    costs: tuple[int, ...]  # per class; negative = unavailable
    members: tuple[str, ...]


def _balanced(text: str, start: int) -> int:
    """Index just past the brace block opening at text[start] == '{'."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError("unbalanced braces")


def _strip_comments(text: str) -> str:
    """Remove /* */ and // comments (string literals in these tables contain neither)."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _source(src_dir: Path | None) -> str:
    src_dir = src_dir or XaniaPaths.resolve().src_dir
    return _strip_comments((src_dir / "SkillTables.cpp").read_text(encoding="latin-1"))


def _ints(group: str) -> tuple[int, ...]:
    vals = []
    for tok in group.split(","):
        tok = tok.strip()
        vals.append(_RATING_CONSTANTS[tok] if tok in _RATING_CONSTANTS else int(tok))
    return tuple(vals)


@lru_cache(maxsize=None)
def load_skills(src_dir: Path | None = None) -> dict[str, Skill]:
    """``skill_table`` from SkillTables.cpp."""
    text = _source(src_dir)
    start = text.index("skill_table[MAX_SKILL] = {")
    end = _balanced(text, text.index("{", start))
    body = text[text.index("{", start) + 1:end - 1]
    skills: dict[str, Skill] = {}
    pos = 0
    while (i := body.find("{", pos)) >= 0:
        j = _balanced(body, i)
        entry = body[i + 1:j - 1]
        pos = j
        name = re.match(r'\s*"([^"]*)"', entry)
        tail = re.search(r"SkillSlot\((\d+)\),\s*(-?\d+),\s*(-?\d+),\s*\{([^}]*)\},\s*\{([^}]*)\}", entry)
        assert name and tail, f"unrecognised skill_table entry: {entry[:80]!r}"
        spell_fun = entry.split(",")[1].strip()
        skills[name.group(1)] = Skill(
            name.group(1), int(tail.group(1)), int(tail.group(2)), int(tail.group(3)),
            _ints(tail.group(4)), _ints(tail.group(5)), spell_fun not in ("nullptr", "spell_null"),
        )
    assert len(skills) > 100, "skill_table parse looks wrong"
    return skills


@lru_cache(maxsize=None)
def load_groups(src_dir: Path | None = None) -> dict[str, Group]:
    """``group_table`` from SkillTables.cpp."""
    text = _source(src_dir)
    start = text.index("group_table[MAX_GROUP] = {")
    body = text[text.index("{", start) + 1:_balanced(text, text.index("{", start)) - 1]
    groups = {}
    for m in re.finditer(r'\{\s*"([^"]+)",\s*\{([^}]*)\},\s*\{([^}]*)\}\s*\}', body):
        members = tuple(re.findall(r'"([^"]+)"', m.group(3)))
        groups[m.group(1)] = Group(m.group(1), _ints(m.group(2)), members)
    assert "mage basics" in groups, "group_table parse looks wrong"
    return groups


def expand_group(name: str, groups: dict[str, Group]) -> set[str]:
    """All skill names granted by a group, recursively (``gn_add``)."""
    out: set[str] = set()
    for member in groups[name].members:
        if member in groups:
            out |= expand_group(member, groups)
        else:
            out.add(member)
    return out


def starting_skills(cls: str, src_dir: Path | None = None) -> set[str]:
    """Skills a new character of ``cls`` has: rom basics + class basics + class default
    (the default package offered at creation, MudImpl nanny / skills.cpp)."""
    groups = load_groups(src_dir)
    return set().union(*(expand_group(g, groups) for g in ("rom basics", f"{cls} basics", f"{cls} default")))
