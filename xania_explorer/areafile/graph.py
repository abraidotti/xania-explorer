"""Walking routes through room exits: what a player can reach on foot, and the steps to get there.

An exit is walkable when it leads to a room that exists: cosmetic exits (file value -1) and dangling exits are
skipped. Doors are walkable (a player can open them; locked ones need the key in ``Step.key``) unless a caller
passes ``doors=False``. Portals, mob programs, recall and other transport aren't followed.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from . import flags as F
from .world import World


@dataclass(frozen=True)
class Step:
    """One move through an exit: type ``command`` in ``from_vnum`` to arrive in ``to_vnum``."""

    from_vnum: int
    direction: int  # 0-5, flags.DIRECTIONS order
    to_vnum: int
    door: bool
    key: int  # key object vnum for a locked door, else 0 or -1

    @property
    def command(self) -> str:
        return F.DIRECTIONS[self.direction]


def steps_from(world: World, vnum: int, doors: bool = True) -> list[Step]:
    """The walkable exits of room ``vnum``, in direction order (empty for an unknown room)."""
    room = world.rooms.get(vnum)
    if room is None:
        return []
    out = []
    for d in sorted(room.exits):
        e = room.exits[d]
        if e.cosmetic or e.to_vnum <= 0 or e.to_vnum not in world.rooms or (e.is_door and not doors):
            continue
        out.append(Step(vnum, d, e.to_vnum, e.is_door, e.key))
    return out


def _search(world: World, start: int, doors: bool, goal: int | None = None) -> dict[int, Step | None]:
    """Breadth-first search from ``start``: each reached room -> the step that first reached it."""
    if start not in world.rooms:
        return {}
    came: dict[int, Step | None] = {start: None}
    queue = deque([start])
    while queue:
        vnum = queue.popleft()
        if vnum == goal:
            break
        for s in steps_from(world, vnum, doors):
            if s.to_vnum not in came:
                came[s.to_vnum] = s
                queue.append(s.to_vnum)
    return came


def distances(world: World, start: int, doors: bool = True) -> dict[int, int]:
    """Walking distance in steps from ``start`` to every reachable room (``start`` itself is 0)."""
    came = _search(world, start, doors)
    dist: dict[int, int] = {}
    for vnum in came:  # BFS order: a room's predecessor is always measured first
        step = came[vnum]
        dist[vnum] = 0 if step is None else dist[step.from_vnum] + 1
    return dist


def reachable(world: World, start: int, doors: bool = True) -> set[int]:
    return set(_search(world, start, doors))


def path(world: World, start: int, goal: int, doors: bool = True) -> list[Step] | None:
    """A shortest walking route from ``start`` to ``goal``; [] if they're the same room, None if there's none."""
    came = _search(world, start, doors, goal)
    if goal not in came:
        return None
    route = []
    while (step := came[goal]) is not None:
        route.append(step)
        goal = step.from_vnum
    return route[::-1]


def rooms_in(world: World, area: str) -> list[int]:
    """The room vnums of an area, by its name or file name (e.g. "The Dell" or "Dell.are")."""
    a = world.area_named(area)
    if a is None:
        raise KeyError(f"no area named {area!r}")
    return sorted(v for v, owner in world.room_area.items() if owner is a)


def entrances(world: World, area: str, doors: bool = True) -> list[Step]:
    """Walkable steps from a room outside the area into one inside it."""
    inside = set(rooms_in(world, area))
    return [s for vnum in sorted(world.rooms) if vnum not in inside
            for s in steps_from(world, vnum, doors) if s.to_vnum in inside]
