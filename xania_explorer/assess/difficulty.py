"""Area difficulty: how hard each area is for the characters it serves, and what it pays.

Each area is profiled for a character at the area's own level: the population-weighted median level of its combat
mobs. A human knight of that level (see Combat & XP) fights every combat mob in the area, using the same model as
the Combat page: real mob stats, the best gear and weapon for that level, mob specials, and helpers that spawn in
the same room. From those fights:

- **HP lost per kill**: the expected damage of a typical fight as a share of the character's maximum HP (the
  population-weighted median over the area's mobs, fought one at a time). The main difficulty number.
- **Deadly share**: the share of the population whose fight (counting helpers) would cost more than full HP.
- **XP per minute**: XP per kill over combat time. Resting, travel and searching aren't counted.
- **Peers**: areas whose level is within ±5. An area is an outlier when its HP lost per kill is at least twice, or
  at most half, its peers' median. Areas with fewer than 5 mob instances (mostly immortal areas) are listed but
  neither compared nor used as peers.
- **Dangerous tails**: areas whose deadly share is at least 20 points above their peers' median, and the mobs that
  make it so (those whose fight, counting helpers, costs more than full HP at the area's level).
- **Aggro traps**: aggressive mobs at least 10 levels above the area's advertised top level. Aggressive mobs attack
  any player up to 5 levels above them, so someone arriving at the advertised level is attacked by something far
  beyond them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..areafile.world import World
from . import combat as CB
from . import common as C

PEER_LEVELS = 5
OUTLIER_RATIO = 2.0
TRAP_GAP = 10
MIN_POPULATION = 5
TAIL_POINTS = 0.20
KNIGHT = "knight"


@dataclass
class AreaProfile:
    name: str
    advertised: tuple[int, int] | None  # the header's {lo hi}, None when the area is "all levels"
    level: int  # the character level it's profiled at: its combat mobs' median level
    span: tuple[int, int]  # 10th–90th percentile of its combat mob levels
    mobs: int  # combat mob prototypes
    population: int
    hp_loss: float  # mean share of max HP lost per kill
    deadly: float  # share of the population whose fight (with helpers) costs more than full HP
    xp_per_minute: float
    aggressive: float  # share of the population that's aggressive
    casters: float  # share with a damaging special
    helped: float  # share that spawns beside helpers
    traps: list[tuple[CB.MobFighter, int]] = field(default_factory=list)  # aggressive mobs far above the band
    peer_ratio: float | None = None  # hp_loss ÷ the median of its peers
    peer_deadly: float | None = None  # its peers' median deadly share
    killers: list[CB.MobFighter] = field(default_factory=list)  # mobs deadly at the area's level

    @property
    def xp_per_hp(self) -> float:
        return self.xp_per_minute / self.hp_loss if self.hp_loss else 0.0

    @property
    def verdict(self) -> str:
        if self.peer_ratio is None:
            return "no peers"
        if self.peer_ratio >= OUTLIER_RATIO:
            return "much harder"
        if self.peer_ratio <= 1 / OUTLIER_RATIO:
            return "much easier"
        return "typical"


def _weighted_percentile(pairs: list[tuple[float, float]], q: float) -> float:
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= q * total:
            return v
    return pairs[-1][0]


class DifficultyAnalysis:
    def __init__(self, world: World):
        self.world = world
        self.combat = CB.analyse(world)
        by_area: dict[str, list[CB.MobFighter]] = {}
        for m in self.combat.mobs:
            if m.info.population > 0:
                by_area.setdefault(m.info.area.name, []).append(m)
        self.areas = sorted((self._profile(name, mobs) for name, mobs in by_area.items() if mobs),
                            key=lambda p: (p.level, p.name))
        for p in self.areas:
            if p.population < MIN_POPULATION:
                continue
            median = C.median_or(self._peers(p.name, p.level))
            p.peer_ratio = p.hp_loss / median if median else None
            p.peer_deadly = C.median_or(q.deadly for q in self.areas if q.name != p.name
                                        and q.population >= MIN_POPULATION and abs(q.level - p.level) <= PEER_LEVELS)

    def _peers(self, name: str, level: int) -> list[float]:
        return [q.hp_loss for q in self.areas if q.name != name and q.population >= MIN_POPULATION
                and abs(q.level - level) <= PEER_LEVELS]

    def _hp_loss(self, mobs: list[CB.MobFighter], level: int) -> float:
        p = self.combat.player(KNIGHT, level)
        return _weighted_percentile([(self.combat.fight(p, m).damage_taken / p.hp, m.info.population)
                                     for m in mobs], 0.5)

    def _profile(self, name: str, mobs: list[CB.MobFighter]) -> AreaProfile:
        a = self.combat
        levels = [(C.usable_level(m.mob.level), m.info.population) for m in mobs]
        level = max(1, min(C.HERO_LEVEL, int(_weighted_percentile(levels, 0.5))))
        p = a.player(KNIGHT, level)
        pop = sum(m.info.population for m in mobs)
        deadly = xp = minutes = 0.0
        killers = []
        for m in mobs:
            f = a.fight(p, m)
            w = m.info.population
            if a.encounter_damage(p, m, f) >= p.hp:
                deadly += w
                killers.append(m)
            if f.rounds != float("inf"):
                xp += w * f.xp
                minutes += w * f.rounds * CB.ROUND_SECONDS / 60
        header = mobs[0].info.area.file.header
        advertised = None if header.min_level is None or header.all_levels else (header.min_level, header.max_level)
        traps = []
        if advertised:
            traps = sorted(((m, m.mob.level - advertised[1]) for m in mobs
                            if "Aggressive" in m.mob.act_names and m.mob.level - advertised[1] >= TRAP_GAP),
                           key=lambda t: -t[1])
        specials = a.specials.names if a.specials else set()
        return AreaProfile(
            name, advertised, level,
            (int(_weighted_percentile(levels, 0.1)), int(_weighted_percentile(levels, 0.9))),
            len(mobs), pop, self._hp_loss(mobs, level), deadly / pop, xp / minutes if minutes else 0.0,
            sum(m.info.population for m in mobs if "Aggressive" in m.mob.act_names) / pop,
            sum(m.info.population for m in mobs if m.special in specials) / pop,
            sum(m.info.population for m in mobs if a.helpers.get(m.mob.vnum)) / pop,
            traps, killers=sorted(killers, key=lambda m: (-m.mob.level, m.mob.vnum)))

    # -- facts ------------------------------------------------------------------------------------
    def outliers(self, verdict: str) -> list[AreaProfile]:
        return sorted((p for p in self.areas if p.verdict == verdict), key=lambda p: -(p.peer_ratio or 0)
                      if verdict == "much harder" else (p.peer_ratio or 0))

    def level_to_match_peers(self, area: AreaProfile) -> int | None:
        """The lowest level from which this area's HP lost per kill is no more than its new peers' median
        (re-profiling the area for a character of that level)."""
        mobs = [m for m in self.combat.mobs if m.info.area.name == area.name and m.info.population > 0]
        for level in range(area.level + 1, C.HERO_LEVEL + 1):
            peers = C.median_or(self._peers(area.name, level))
            if peers and self._hp_loss(mobs, level) <= peers:
                return level
        return None

    @property
    def tails(self) -> list[AreaProfile]:
        """Areas whose deadly share is at least TAIL_POINTS above their peers' median, worst first."""
        return sorted((p for p in self.areas if p.peer_deadly is not None and p.deadly - p.peer_deadly >= TAIL_POINTS),
                      key=lambda p: -(p.deadly - p.peer_deadly))

    @property
    def traps(self) -> list[tuple[AreaProfile, CB.MobFighter, int]]:
        return [(p, m, gap) for p in self.areas for m, gap in p.traps]

    # -- tables -------------------------------------------------------------------------------------
    def profile_table(self) -> str:
        return C.table(["Area", "Advertised", "Profiled at", "Mob levels", "Mobs", "HP lost per kill", "Deadly",
                        "XP/min", "Aggressive", "Casters", "With helpers", "vs peers"],
                       [[p.name, f"{p.advertised[0]}–{p.advertised[1]}" if p.advertised else "all", p.level,
                         f"{p.span[0]}–{p.span[1]}", p.mobs, f"{p.hp_loss:.0%}", f"{p.deadly:.0%}",
                         round(p.xp_per_minute), f"{p.aggressive:.0%}", f"{p.casters:.0%}", f"{p.helped:.0%}",
                         f"{p.peer_ratio:.1f}×" if p.peer_ratio else "—"] for p in self.areas])

    def trap_table(self) -> str:
        return C.table(["Area", "Advertised", "Mob", "Level", "Above the band by"],
                       [[p.name, f"{p.advertised[0]}–{p.advertised[1]}", f"#{m.mob.vnum} {m.mob.short_descr}",
                         m.mob.level, gap] for p, m, gap in self.traps])

    def method(self) -> str:
        return __doc__.split("\n\n", 1)[1].strip() + "\n"


def analyse(world: World) -> DifficultyAnalysis:
    return C.cached(world, "difficulty", DifficultyAnalysis)


def render(world: World) -> str:
    a = analyse(world)
    harder, easier = a.outliers("much harder"), a.outliers("much easier")
    headlines = ("## Headline findings\n\n"
                 f"- **Much harder than their peers** (≥{OUTLIER_RATIO:g}× HP per typical fight): "
                 + (", ".join(f"{p.name} ({p.peer_ratio:.1f}×, level {p.level})" for p in harder) or "none") + ".\n"
                 f"- **Much easier**: " + (", ".join(f"{p.name} ({p.peer_ratio:.1f}×)" for p in easier) or "none")
                 + ".\n- **Dangerous tails**: " + (", ".join(f"{p.name} ({p.deadly:.0%} deadly vs {p.peer_deadly:.0%})"
                                                         for p in a.tails) or "none")
                 + f".\n- **Aggro traps**: {len(a.traps)}.\n\n")
    return (C.GENERATED_NOTE + "\n# Area difficulty\n\n" + headlines + "## Method\n\n" + a.method()
            + "\n## Every area\n\n" + a.profile_table()
            + ("\n## Aggro traps\n\n" + a.trap_table() if a.traps else ""))


def write_csv(world: World, path: Path) -> None:
    a = analyse(world)
    C.write_csv(path, ["area", "advertised_lo", "advertised_hi", "level", "mob_level_p10", "mob_level_p90", "mobs",
                       "population", "hp_lost_per_kill", "deadly_share", "xp_per_minute", "aggressive_share",
                       "caster_share", "helped_share", "vs_peers", "aggro_traps"],
                [[p.name, *(p.advertised or ("", "")), p.level, *p.span, p.mobs, p.population, round(p.hp_loss, 4),
                  round(p.deadly, 4), round(p.xp_per_minute, 2), round(p.aggressive, 4), round(p.casters, 4),
                  round(p.helped, 4), round(p.peer_ratio, 3) if p.peer_ratio else "", len(p.traps)]
                 for p in a.areas])
