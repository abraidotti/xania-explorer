"""Mob special procedures that deal damage, extracted from ``xania/src/special.cpp``.

``mobile_update`` runs a mob's special every 4 seconds (``PULSE_MOBILE``), on top of its melee rounds. The fighting
specials pick an opponent with a fixed chance (``pick_fighting_victim(ch, number_bits(k) == 0)``), then:

- **casters** (``spec_cast_*``) draw a random case from ``switch (number_bits(4))`` until its spell fits the mob's
  level (``min_level``/``max_level``), and cast it at the mob's level;
- **breathers** (``spec_breath_*``, via ``dragon()``) breathe for ``number_range(hp/20 + 16, hp/15)``, where ``hp``
  is the mob's *current* HP clamped to 10–2000, halved on a save; gas breath hits the whole room without a pick;
- ``spec_breath_any`` picks one of the breaths from its own ``switch``.

Everything is read from the checkout, so a branch that changes a spell list or a chance changes the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .cpp_tables import _strip_comments
from .spell_tables import load_damage_spells, save_chance

PULSE_MOBILE_SECONDS = 4
ROUND_SECONDS = 3
BREATH_HP_CAP = 2000
# Spells that do nothing to a neutral victim (the combat model's player is neutral).
NEUTRAL_IMMUNE = {"spell_dispel_evil", "spell_dispel_good"}


@dataclass(frozen=True)
class SpellCase:
    weight: int  # how many of the 16 switch values pick it
    spell: str  # e.g. "fireball"
    min_level: int
    max_level: int


@dataclass(frozen=True)
class CasterSpecial:
    name: str
    pick: float  # chance per opponent per pulse
    cases: tuple[SpellCase, ...]

    def valid(self, level: int) -> list[SpellCase]:
        return [c for c in self.cases if c.min_level <= level <= c.max_level]


@dataclass(frozen=True)
class Specials:
    casters: dict[str, CasterSpecial]
    dragon_pick: float  # dragon(): chance per opponent per pulse
    breath_any: dict[str, float]  # spec_breath_any: share of each breath special

    @property
    def names(self) -> set[str]:
        return set(self.casters) | {f"spec_breath_{b}" for b in ("fire", "frost", "acid", "lightning", "gas", "any")}


def _function(text: str, name: str) -> str | None:
    m = re.search(rf"bool {name}\(Char \*ch\) \{{(.*?)\n\}}", text, re.S)
    return m.group(1) if m else None


def _pick(body: str) -> float | None:
    m = re.search(r"pick_fighting_victim\(ch,.*?number_bits\((\d+)\)\s*==\s*0", body, re.S)
    return 1 / 2 ** int(m.group(1)) if m else None


def _caster(name: str, body: str) -> CasterSpecial | None:
    pick = _pick(body)
    sw = re.search(r"switch \(number_bits\((\d+)\)\) \{(.*?)\n\s*\}\s*\n", body, re.S)
    if pick is None:
        return None
    if not sw:  # always the same spell (spec_cast_judge)
        fixed = re.search(r'spell = "([^"]+)"', body)
        return CasterSpecial(name, pick, (SpellCase(1, fixed.group(1), 0, 10_000),)) if fixed else None
    values = 2 ** int(sw.group(1))
    # a max_level set before the switch is the default for cases that don't set their own
    m = re.search(r"max_level = (\d+);", body[:sw.start()])
    default_max = int(m.group(1)) if m else 10_000
    explicit, groups = set(), []
    for chunk in sw.group(2).split("break;"):
        labels = [int(x) for x in re.findall(r"case (\d+):", chunk)]
        spell = re.search(r'spell = "([^"]+)"', chunk)
        if not spell:
            continue
        explicit |= set(labels)
        lo = re.search(r"min_level = (\d+);", chunk)
        hi = re.search(r"max_level = (\d+);", chunk)
        groups.append((labels, "default:" in chunk, spell.group(1), int(lo.group(1)) if lo else 0,
                       int(hi.group(1)) if hi else default_max))
    rest = values - len(explicit)
    cases = tuple(SpellCase(len(labels) + (rest if is_default else 0), spell, lo, hi)
                  for labels, is_default, spell, lo, hi in groups)
    return CasterSpecial(name, pick, cases) if cases else None


@lru_cache(maxsize=None)
def load_specials(src_dir: Path) -> Specials | None:
    """The damage-dealing specials in ``src_dir/special.cpp``; None if the file isn't there."""
    path = Path(src_dir) / "special.cpp"
    if not path.exists():
        return None
    text = _strip_comments(path.read_text(encoding="latin-1"))
    casters = {}
    for name in sorted(set(re.findall(r"bool (spec_cast_\w+)\(Char \*ch\) \{", text))):
        c = _caster(name, _function(text, name) or "")
        if c:
            casters[name] = c
    dragon = _pick(re.search(r"bool dragon\(Char \*ch, const char \*spell_name\) \{(.*?)\n\}", text, re.S).group(1)) \
        if "bool dragon(" in text else None
    any_body = _function(text, "spec_breath_any") or ""
    shares: dict[str, float] = {}
    sw = re.search(r"switch \(number_bits\((\d+)\)\) \{(.*?)\n\s*\}", any_body, re.S)
    if sw:
        values = 2 ** int(sw.group(1))
        for chunk in sw.group(2).split(";"):
            labels = re.findall(r"case (\d+):", chunk)
            target = re.search(r"return (spec_breath_\w+)\(ch\)", chunk)
            if labels and target:
                shares[target.group(1)] = shares.get(target.group(1), 0) + len(labels) / values
    return Specials(casters, dragon or 0.0, shares)


# -- expected damage ---------------------------------------------------------------------------
def breath_damage(mob_hp: float, save: float) -> float:
    """Mean of number_range(h/20 + 16, h/15) over a fight in which the breather's HP falls from full to 0."""
    steps = 20
    total = 0.0
    for i in range(steps):
        h = min(BREATH_HP_CAP, max(10, mob_hp * (i + 0.5) / steps))
        total += (h / 20 + 16 + h / 15) / 2
    return total / steps * (1 - save / 2)


def spell_damage(spell: str, caster_level: int, victim_level: int, damage_spells: dict, caster_hp: float) -> float:
    """Expected damage of one cast against a neutral victim (0 for spells that don't deal damage)."""
    fun = "spell_" + spell.replace(" ", "_")
    if fun.endswith("_breath"):  # breaths scale with the caster's HP, whoever casts them
        return breath_damage(caster_hp, save_chance(caster_level, victim_level))
    if fun == "spell_high_explosive":  # number_range(level, 3 × level), halved on a save
        return 2 * caster_level * (1 - save_chance(caster_level, victim_level) / 2)
    if fun == "spell_earthquake":
        return caster_level + 9  # level + dice(2, 8), no save
    if fun in NEUTRAL_IMMUNE or fun not in damage_spells:
        return 0.0
    return damage_spells[fun].expected(caster_level, save_chance(caster_level, victim_level))


def special_damage_per_round(specials: Specials, name: str, mob_level: int, mob_hp: float,
                             victim_level: int, src_dir: Path) -> float:
    """Expected damage a solo opponent takes from the mob's special, per 3-second combat round."""
    damage_spells = load_damage_spells(src_dir)
    save = save_chance(mob_level, victim_level)
    per_pulse = 0.0
    if name in specials.casters:
        c = specials.casters[name]
        valid = c.valid(mob_level)
        weight = sum(x.weight for x in valid)
        if weight:
            per_pulse = c.pick * sum(x.weight / weight * spell_damage(x.spell, mob_level, victim_level, damage_spells, mob_hp)
                                     for x in valid)
    elif name.startswith("spec_breath_"):
        shares = specials.breath_any if name == "spec_breath_any" else {name: 1.0}
        for breath, share in shares.items():
            pick = 1.0 if breath == "spec_breath_gas" else specials.dragon_pick
            per_pulse += share * pick * breath_damage(mob_hp, save)
    return per_pulse * ROUND_SECONDS / PULSE_MOBILE_SECONDS
