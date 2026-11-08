"""Where can a player get each object, and where does each mob live?

Derived from #RESETS (see docs/02-area-file-format.md §7):

- ``M`` spawns a mob; ``G``/``E`` lines after it give it items. On a shopkeeper
  that is shop stock (always present, buyable); otherwise a drop with ``arg2`` %.
- ``O`` puts an object on a room floor; ``P`` puts one in a container.

Objects with no reset source are not obtainable through the world (they may
still come from mobprogs, specials, quests or immortals).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..areafile.world import Area, World


@dataclass(frozen=True)
class ObjSource:
    kind: str  # "shop" | "mob" | "floor" | "container"
    area: str  # area short name
    mob_vnum: int | None = None
    mob_level: int | None = None
    drop_pct: int | None = None  # mob drops only
    room_vnum: int | None = None


@dataclass(frozen=True)
class MobSpawn:
    room_vnum: int
    area: Area
    world_max: int
    room_max: int


def shopkeepers(world: World) -> set[int]:
    return {s.keeper for f in world.files for s in f.shops}


def object_sources(world: World) -> dict[int, list[ObjSource]]:
    keepers = shopkeepers(world)
    out: dict[int, list[ObjSource]] = defaultdict(list)
    for af in world.files:
        area_name = af.name
        last_mob: int | None = None
        for r in af.resets:
            if r.command == "M":
                last_mob = r.arg1
            elif r.command in "GE" and last_mob is not None:
                mob = world.mobs.get(last_mob)
                kind = "shop" if last_mob in keepers else "mob"
                out[r.arg1].append(ObjSource(kind, area_name, last_mob, mob.level if mob else None,
                                             None if kind == "shop" else r.arg2, r.room_vnum))
            elif r.command == "O":
                out[r.arg1].append(ObjSource("floor", area_name, room_vnum=r.arg3))
            elif r.command == "P":
                out[r.arg1].append(ObjSource("container", area_name, room_vnum=r.room_vnum))
    return dict(out)


def mob_spawns(world: World) -> dict[int, list[MobSpawn]]:
    out: dict[int, list[MobSpawn]] = defaultdict(list)
    for af in world.files:
        for r in af.resets:
            if r.command == "M" and r.arg3 in world.rooms:
                out[r.arg1].append(MobSpawn(r.arg3, world.room_area[r.arg3], r.arg2, r.arg4))
    return dict(out)


def estimated_population(spawns: list[MobSpawn]) -> int:
    """Steady-state number of instances the resets will maintain.

    Each ``M`` line adds one instance per reset while the room holds fewer than
    ``room_max`` and the world fewer than ``world_max`` (db.cpp reset_room).
    Ignores wandering and deaths, so it's an upper bound on what players meet.
    """
    if not spawns:
        return 0
    cap = max(s.world_max for s in spawns)
    return max(0, min(cap, sum(max(0, s.room_max) for s in spawns)))
