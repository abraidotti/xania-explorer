"""Levelling path: where a character of each level can go to gain experience.

- **Suitable area** for level L: an area holding at least ``MIN_MOBS`` combat mobs (population) within
  ±2 levels of L.
- **XP on offer**: for a level-L character, the XP of killing every such mob once in a fully reset world
  (Combat's xp_compute model), in levels' worth (÷ 1,000 XP per level for a human).
- **Distance**: walking steps from the Midgaard temple (room 3001, where recall leads) through room exits,
  ignoring doors' locked state; portals, mob programs and other transport aren't followed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..areafile import graph as G
from ..areafile.world import World
from . import combat as CB
from . import common as C

RECALL_ROOM = 3001  # VnumRooms.hpp MidgaardTemple
MIN_MOBS = 5
XP_PER_LEVEL = 1000  # human, default build


def distances(world: World, start: int = RECALL_ROOM) -> dict[int, int]:
    """Breadth-first walking distance from ``start`` to every reachable room."""
    return G.distances(world, start)


@dataclass
class AreaOffer:
    area: str
    mobs: int  # population within the level window
    xp: float  # total XP for killing them all once
    steps: int | None  # walking distance from recall to the nearest of those mobs' rooms


class LevellingAnalysis:
    def __init__(self, world: World):
        self.world = world
        self.combat = CB.analyse(world)
        self.dist = distances(world)
        self.spawn_rooms = self._spawn_rooms()
        self.offers = {lvl: self._offers(lvl) for lvl in C.LEVELS}

    def _spawn_rooms(self) -> dict[int, list[int]]:
        rooms = defaultdict(list)
        for af in self.world.files:
            for r in af.resets:
                if r.command == "M" and r.arg3 in self.world.rooms:
                    rooms[r.arg1].append(r.arg3)
        return rooms

    def _offers(self, level: int) -> list[AreaOffer]:
        by_area: dict[str, list] = defaultdict(list)
        for m, fight in self.combat.results[("knight", level)].fights:
            by_area[m.info.area.name].append((m, fight))
        out = []
        for area, items in by_area.items():
            pop = sum(m.info.population for m, _ in items)
            xp = sum(f.xp * m.info.population for m, f in items)
            steps = [self.dist[r] for m, _ in items for r in self.spawn_rooms.get(m.mob.vnum, []) if r in self.dist]
            out.append(AreaOffer(area, pop, xp, min(steps) if steps else None))
        return sorted(out, key=lambda o: (-o.xp, o.area))

    # -- facts ----------------------------------------------------------------------------
    def suitable(self, level: int) -> list[AreaOffer]:
        return [o for o in self.offers[level] if o.mobs >= MIN_MOBS]

    def levels_of_xp(self, level: int) -> float:
        return sum(o.xp for o in self.offers[level]) / XP_PER_LEVEL

    def top_share(self, level: int) -> tuple[str | None, float]:
        total = sum(o.xp for o in self.offers[level])
        if not total:
            return None, 0.0
        top = self.offers[level][0]
        return top.area, top.xp / total

    @property
    def unreachable_rooms(self) -> list[int]:
        return sorted(v for v in self.world.rooms if v not in self.dist)

    def unreachable_by_area(self) -> list[tuple[str, int, int, int]]:
        """(area, unreachable rooms, rooms, combat mobs placed in unreachable rooms)."""
        rooms_by_area: dict[str, list[int]] = defaultdict(list)
        for vnum in self.world.rooms:
            rooms_by_area[self.world.room_area[vnum].name].append(vnum)
        mobs_in = defaultdict(int)
        for m in self.combat.mobs:
            for r in self.spawn_rooms.get(m.mob.vnum, []):
                if r not in self.dist:
                    mobs_in[self.world.room_area[r].name] += 1
        out = []
        for area, rooms in rooms_by_area.items():
            bad = sum(1 for r in rooms if r not in self.dist)
            if bad:
                out.append((area, bad, len(rooms), mobs_in[area]))
        return sorted(out, key=lambda t: (-t[1] / t[2], t[0]))

    def area_distance(self) -> list[tuple[str, int, float | None]]:
        """(area, nearest room's distance, median level of its combat mobs)."""
        nearest: dict[str, int] = {}
        for vnum, d in self.dist.items():
            a = self.world.room_area[vnum].name
            nearest[a] = min(d, nearest.get(a, d))
        levels = defaultdict(list)
        for m in self.combat.mobs:
            levels[m.info.area.name].append(m.mob.level)
        return sorted(((a, d, C.median_or(levels.get(a, []))) for a, d in nearest.items()),
                      key=lambda t: (t[1], t[0]))

    # -- tables -----------------------------------------------------------------------------
    def band_table(self) -> str:
        rows = []
        for b in C.bands():
            lvl = (b.lo + b.hi) // 2
            top, share = self.top_share(lvl)
            suitable = self.suitable(lvl)
            near = min((o.steps for o in suitable if o.steps is not None), default=None)
            rows.append([b.label, len(suitable), round(self.levels_of_xp(lvl), 1), top, f"{share:.0%}" if top else None,
                         near, ", ".join(o.area for o in suitable[:4])])
        return C.table(["Levels (mid-band)", "suitable areas", "levels of XP per reset", "richest area",
                        "its share", "nearest suitable (steps)", "top areas"], rows)

    def unreachable_table(self) -> str:
        return C.table(["Area", "unreachable rooms", "rooms", "share", "mobs placed there"],
                       [[a, n, total, f"{n / total:.0%}", mobs] for a, n, total, mobs in self.unreachable_by_area()])

    def distance_table(self) -> str:
        return C.table(["Area", "steps from recall", "median mob level"], self.area_distance())

    def method(self) -> str:
        return __doc__.split("\n\n", 1)[1].strip() + "\n"


def analyse(world: World) -> LevellingAnalysis:
    return C.cached(world, "levelling", LevellingAnalysis)


def render(world: World) -> str:
    a = analyse(world)
    out = [C.GENERATED_NOTE, "\n# Levelling path\n\n", "## Headline findings\n\n",
           f"- **Unreachable on foot from recall**: {len(a.unreachable_rooms)} of {len(world.rooms)} rooms.\n",
           f"- **Fewest suitable areas**: " + ", ".join(
               f"level {lvl} ({len(a.suitable(lvl))})" for lvl in sorted(C.LEVELS, key=lambda x: (len(a.suitable(x)), x))[:5])
           + ".\n",
           "\n## Method\n\n" + a.method(), "\n## 1. By level band\n\n" + a.band_table(),
           "\n## 2. Distance from recall\n\n" + a.distance_table(),
           "\n## 3. Unreachable rooms\n\n" + a.unreachable_table()]
    return "".join(out)


def write_csv(world: World, path: Path) -> None:
    a = analyse(world)
    rows = []
    for lvl in C.LEVELS:
        for o in a.offers[lvl]:
            rows.append([lvl, o.area, o.mobs, round(o.xp), o.steps, int(o.mobs >= MIN_MOBS)])
    C.write_csv(path, ["level", "area", "mobs_in_window", "xp_on_offer", "steps_from_recall", "suitable"], rows)
