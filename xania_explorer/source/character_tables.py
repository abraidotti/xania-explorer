"""Class, PC race and stat-bonus tables extracted from the C++ source.

- ``Class.cpp``     : the four classes (prime stat, to-hit curve, HP/mana gain per level)
- ``Races.cpp``     : ``pc_race_table`` (creation points, XP multipliers, bonus skills, stats)
- ``Stats.cpp``     : ``str_app`` / ``int_app`` / ``wis_app`` / ``dex_app`` / ``con_app``

Like cpp_tables.py these readers are narrow on purpose and assert loudly if the
C++ layout changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..paths import XaniaPaths
from .cpp_tables import CLASSES, _balanced, _strip_comments

STATS = ["str", "int", "wis", "dex", "con"]  # Stats.hpp order (pfile/area order)
MAX_STAT_VALUE = 25  # Stats.hpp MaxStatValue
START_HIT, START_MANA, START_MOVE = 20, 100, 100  # Char.hpp defaults
NEWBIE_TRAINS, NEWBIE_PRACS = 3, 5  # MudImpl.cpp
PRIME_STAT_BONUS_AT_CREATION = 3  # MudImpl.cpp: +3 to the prime stat (not for dragons)
PRIME_STAT_TRAIN_BONUS = 2  # handler.cpp get_max_train: prime stat may be trained 2 above the race max
DEFAULT_GROUP_POINTS = 40  # "<class> default" group cost for its own class (group_table)


def _src(src_dir: Path | None, name: str) -> str:
    src_dir = src_dir or XaniaPaths.resolve().src_dir
    return _strip_comments((src_dir / name).read_text(encoding="latin-1"))


def _initialiser(text: str, marker: str) -> str:
    start = text.index(marker)
    brace = text.index("{", start + len(marker) - 1)
    return text[brace + 1:_balanced(text, brace) - 1]


def _top_level_groups(body: str) -> list[str]:
    out, pos = [], 0
    while (i := body.find("{", pos)) >= 0:
        j = _balanced(body, i)
        out.append(body[i + 1:j - 1])
        pos = j
    return out


def _ints(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"-?\d+", text))


@dataclass(frozen=True)
class ClassInfo:
    id: int
    name: str
    prime_stat: str
    adept: int  # max % a skill can be practised to
    to_hit_ac_level0: int
    to_hit_ac_level32: int
    hp_gain_min: int
    hp_gain_max: int
    mana_factor: int
    base_group: str
    default_group: str


@dataclass(frozen=True)
class PcRace:
    name: str
    points: int  # creation-point cost
    class_mult: tuple[int, ...]  # XP multiplier ×100 per class (CLASSES order)
    bonus_skills: tuple[str, ...]
    stats: tuple[int, ...]  # starting stats (STATS order)
    max_stats: tuple[int, ...]  # race maximum (before class prime bonus)
    size: str

    def mult_for(self, cls: str) -> int:
        return self.class_mult[CLASSES.index(cls)]


@dataclass(frozen=True)
class StatTables:
    str_app: tuple[tuple[int, int, int, int], ...]  # tohit, todam, carry, wield
    int_app: tuple[int, ...]  # learn
    wis_app: tuple[int, ...]  # practices per level
    dex_app: tuple[int, ...]  # defensive (AC modifier; negative is better)
    con_app: tuple[tuple[int, int], ...]  # hitp per level, shock


@lru_cache(maxsize=None)
def load_classes(src_dir: Path | None = None) -> dict[str, ClassInfo]:
    text = _src(src_dir, "Class.cpp")
    out = {}
    for m in re.finditer(r"constexpr Class (\w+)\{(.*?)\};", text, re.S):
        body = m.group(2)
        strings = re.findall(r'"([^"]*)"sv', body)
        stat = re.search(r"Stat::(\w+)", body).group(1).lower()
        # Drop the strings, the Stat:: and Objects:: names and the guild-room array, leaving the numbers in order.
        rest = re.sub(r'"[^"]*"sv|Stat::\w+|Objects::\w+|\{[^}]*\}', " ", body)
        nums = _ints(rest)
        assert len(nums) == 7 and len(strings) == 4, f"unrecognised Class initialiser {m.group(1)}"
        cid, adept, th0, th32, hmin, hmax, mana = nums
        out[strings[0]] = ClassInfo(cid, strings[0], stat, adept, th0, th32, hmin, hmax, mana, strings[2], strings[3])
    assert sorted(out, key=lambda n: out[n].id) == CLASSES, f"class table changed: {list(out)}"
    return out


@lru_cache(maxsize=None)
def load_pc_races(src_dir: Path | None = None) -> dict[str, PcRace]:
    text = _src(src_dir, "Races.cpp")
    body = _initialiser(text, "pc_race_table[] = {")
    out = {}
    for entry in _top_level_groups(body):
        strings = re.findall(r'"([^"]*)"', entry.split("{", 1)[0])
        groups = _top_level_groups(entry)
        size = re.search(r"BodySize::(\w+)", entry).group(1).lower()
        head_nums = _ints(re.sub(r'"[^"]*"', " ", entry.split("{", 1)[0]))
        assert len(strings) >= 2 and len(head_nums) == 1 and len(groups) == 4, f"bad pc_race entry {entry[:60]!r}"
        name = strings[0]
        if name == "null race":
            continue
        skills = tuple(s for s in re.findall(r'"([^"]*)"', groups[1]) if s)
        out[name] = PcRace(name, head_nums[0], _ints(groups[0]), skills, _ints(groups[2]), _ints(groups[3]), size)
    assert len(out) >= 10 and all(len(r.class_mult) == len(CLASSES) for r in out.values())
    return out


@lru_cache(maxsize=None)
def load_stat_tables(src_dir: Path | None = None) -> StatTables:
    text = _src(src_dir, "Stats.cpp")

    def rows(name: str) -> list[tuple[int, ...]]:
        groups = [_ints(g) for g in _top_level_groups(_initialiser(text, f"{name}[StatTableSize] = {{"))]
        assert len(groups) == MAX_STAT_VALUE + 1, f"{name} has {len(groups)} rows"
        return groups

    return StatTables(
        tuple(rows("str_app")),  # type: ignore[arg-type]
        tuple(r[0] for r in rows("int_app")),
        tuple(r[0] for r in rows("wis_app")),
        tuple(r[0] for r in rows("dex_app")),
        tuple(rows("con_app")),  # type: ignore[arg-type]
    )


def cache_clear() -> None:
    for f in (load_classes, load_pc_races, load_stat_tables):
        f.cache_clear()


def _letter_bit(token: str) -> int | None:
    """'A'..'Z' -> 0..25, 'aa'..'ee' -> 26.. (merc.h letter macros)."""
    if len(token) == 1 and token.isupper():
        return ord(token) - ord("A")
    if len(token) == 2 and token[0] == token[1] and token.islower():
        return 26 + ord(token[0]) - ord("a")
    return None


@lru_cache(maxsize=None)
def load_race_off_flags(src_dir: Path | None = None) -> dict[str, frozenset[str]]:
    """Offensive flags each race gives its mobs (``race_table`` in Races.cpp; MobIndexData.cpp merges them in)."""
    from ..areafile.flags import OFFENSIVE

    by_bit = {bit: name for bit, name in OFFENSIVE.items()}
    text = _src(src_dir, "Races.cpp")
    body = _initialiser(text, "race_table[] = {")
    out = {}
    for entry in _top_level_groups(body):
        fields = [f.strip() for f in entry.split(",")]
        name = re.match(r'"([^"]*)"', fields[0])
        if not name or len(fields) < 5:
            continue
        flags = set()
        for token in (t.strip() for t in fields[4].split("|")):
            named = re.fullmatch(r"to_int\(OffensiveFlag::(\w+)\)", token)
            if named:
                flags.add(named.group(1))
            elif (bit := _letter_bit(token)) is not None and bit in by_bit:
                flags.add(by_bit[bit])
        out[name.group(1)] = frozenset(flags)
    assert "human" in out and len(out) >= 20, "race_table parse looks wrong"
    return out


def load_race_tolerances(src_dir: Path | None = None) -> dict[str, tuple[frozenset, frozenset, frozenset]]:
    """{race: (immune, resistant, vulnerable)} that each race gives its mobs: ``race_table`` in Races.cpp, fields 6-8
    (MobIndexData.cpp merges them into the file's own flags)."""
    from ..areafile.flags import TOLERANCE

    text = _src(src_dir, "Races.cpp")
    body = _initialiser(text, "race_table[] = {")
    out = {}
    for entry in _top_level_groups(body):
        fields = [f.strip() for f in entry.split(",")]
        name = re.match(r'"([^"]*)"', fields[0])
        if not name or len(fields) < 8:
            continue
        sets = []
        for field in fields[5:8]:
            flags = set()
            for token in (t.strip() for t in field.split("|")):
                named = re.fullmatch(r"to_int\(ToleranceFlag::(\w+)\)", token)
                if named:
                    flags.add(named.group(1))
                elif (bit := _letter_bit(token)) is not None and bit in TOLERANCE:
                    flags.add(TOLERANCE[bit])
            sets.append(frozenset(flags))
        out[name.group(1)] = tuple(sets)
    assert "human" in out and len(out) >= 20, "race_table parse looks wrong"
    return out
