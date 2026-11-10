"""Direct-damage spell formulas extracted from ``xania/src/magic.cpp``.

Most attack spells roll ``number_range(table[level] / 2, table[level] * 2)`` from a per-level
damage table (``get_direct_dmg_and_level``) and halve it if the victim saves. A few use dice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..paths import XaniaPaths
from .cpp_tables import _strip_comments

# Spells with a dice formula instead of a table: name -> (description, expected damage at level L)
DICE_SPELLS = {
    "spell_call_lightning": ("dice(level/2, 8), outdoors in bad weather", lambda L: (L // 2) * 4.5),
    "spell_energy_drain": ("dice(1, level), also drains XP/mana", lambda L: (L + 1) / 2),
}


@dataclass(frozen=True)
class DamageSpell:
    fun: str  # e.g. spell_fireball
    table: str | None  # damage table name, or None for dice spells
    values: tuple[int, ...]  # the table (index = caster level, clamped)
    formula: str
    damage_type: str = "Other"  # DamageType of its damage() call, e.g. Fire (decides resistances)

    def expected(self, level: int, save_chance: float = 0.5) -> float:
        """Expected damage per successful cast at caster ``level`` against a victim saving
        with probability ``save_chance`` (a save halves it)."""
        if self.table is None:
            raw = DICE_SPELLS[self.fun][1](level)
        else:
            t = self.values[max(0, min(level, len(self.values) - 1))]
            lo, hi = t // 2, t * 2
            raw = (lo + hi) / 2
        return raw * (1 - save_chance / 2)


@lru_cache(maxsize=None)
def load_damage_spells(src_dir: Path | None = None) -> dict[str, DamageSpell]:
    text = _strip_comments(((src_dir or XaniaPaths.resolve().src_dir) / "magic.cpp").read_text(encoding="latin-1"))
    tables = {m.group(1): tuple(int(x) for x in re.findall(r"-?\d+", m.group(2)))
              for m in re.finditer(r"(?:constexpr|const)\s+(?:const\s+)?std::array(?:\s*<[^>]*>)?\s+(\w+)\s*=\s*"
                                   r"\{(.*?)\};",
                                   text, re.S)}
    out = {}
    for m in re.finditer(r"void (spell_\w+)\(int sn, int level[^{]*\{(.*?)\n\}", text, re.S):
        fun, body = m.group(1), m.group(2)
        used = re.findall(r"get_direct_dmg_and_level\(level, (\w+)\)", body)
        kind = re.search(r"\bdamage\([^;]*?DamageType::(\w+)", body)
        dtype = kind.group(1) if kind else "Other"
        if used:
            out[fun] = DamageSpell(fun, used[0], tables[used[0]], f"table {used[0]} (½× to 2×), halved on a save",
                                   dtype)
        elif fun in DICE_SPELLS:
            out[fun] = DamageSpell(fun, None, (), DICE_SPELLS[fun][0], dtype)
    assert "spell_fireball" in out and len(out) >= 15, "magic.cpp damage-spell parse looks wrong"
    return out


def save_chance(caster_level: int, victim_level: int, saving_throw: int = 0) -> float:
    """saves_spell (magic.cpp:546): 50 + victim level − caster level − saving throw, clamped 5–95%."""
    return min(95, max(5, 50 + victim_level - caster_level - saving_throw)) / 100


def mana_cost(min_mana: int, caster_level: int, learned_at: int) -> int:
    """mana_for_spell (magic.cpp:582)."""
    return max(min_mana, 100 // max(1, 2 + caster_level - learned_at))
