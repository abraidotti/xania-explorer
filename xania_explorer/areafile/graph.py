"""Walking routes through room exits: what a player can reach on foot, and the steps to get there.

An exit is walkable when it leads to a room that exists: cosmetic exits (file value -1) and dangling exits are
skipped. Doors are walkable (a player can open them; locked ones need the key in ``Step.key``) unless a caller
passes ``doors=False``. Portals, mob programs, recall and other transport aren't followed.

With ``level``, rooms a mortal of that level can't see are left out, as the game does (``Char::can_see(const
Room &)``, Char.cpp): it neither lists an exit into them nor lets the character in. ImpOnly and GodsOnly rooms are
for immortals, HeroesOnly ones for level 91, NewbiesOnly ones (most of Mud School) for level 5 and below.
Without ``level`` every room counts, as before.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from . import flags as F
from .world import World


HERO_LEVEL = 91  # LEVEL_HERO: is_hero()
NEWBIE_MAX = 5  # NewbiesOnly rooms: level > 5 can't see them
RESTRICTED = frozenset({"ImpOnly", "GodsOnly", "HeroesOnly", "NewbiesOnly"})


def visible_to(room, level: int | None) -> bool:
    """Can a mortal of ``level`` see (and so enter) ``room``? ``None``: any level, always True."""
    if level is None or not room.room_flags:
        return True
    flags = set(F.decode(room.room_flags, F.ROOM)) & RESTRICTED
    if not flags:
        return True
    if flags & {"ImpOnly", "GodsOnly"}:
        return False
    if "HeroesOnly" in flags and level < HERO_LEVEL:
        return False
    return not ("NewbiesOnly" in flags and level > NEWBIE_MAX)


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


def steps_from(world: World, vnum: int, doors: bool = True, level: int | None = None) -> list[Step]:
    """The walkable exits of room ``vnum``, in direction order (empty for an unknown room); with ``level``, only into
    rooms a mortal of that level can see."""
    room = world.rooms.get(vnum)
    if room is None:
        return []
    out = []
    for d in sorted(room.exits):
        e = room.exits[d]
        if e.cosmetic or e.to_vnum <= 0 or e.to_vnum not in world.rooms or (e.is_door and not doors):
            continue
        if level is not None and not visible_to(world.rooms[e.to_vnum], level):
            continue
        out.append(Step(vnum, d, e.to_vnum, e.is_door, e.key))
    return out


def _search(world: World, start: int, doors: bool, goal: int | None = None,
            level: int | None = None) -> dict[int, Step | None]:
    """Breadth-first search from ``start``: each reached room -> the step that first reached it."""
    if start not in world.rooms:
        return {}
    came: dict[int, Step | None] = {start: None}
    queue = deque([start])
    while queue:
        vnum = queue.popleft()
        if vnum == goal:
            break
        for s in steps_from(world, vnum, doors, level):
            if s.to_vnum not in came:
                came[s.to_vnum] = s
                queue.append(s.to_vnum)
    return came


def distances(world: World, start: int, doors: bool = True, level: int | None = None) -> dict[int, int]:
    """Walking distance in steps from ``start`` to every reachable room (``start`` itself is 0)."""
    came = _search(world, start, doors, level=level)
    dist: dict[int, int] = {}
    for vnum in came:  # BFS order: a room's predecessor is always measured first
        step = came[vnum]
        dist[vnum] = 0 if step is None else dist[step.from_vnum] + 1
    return dist


def reachable(world: World, start: int, doors: bool = True, level: int | None = None) -> set[int]:
    return set(_search(world, start, doors, level=level))


def path(world: World, start: int, goal: int, doors: bool = True, level: int | None = None) -> list[Step] | None:
    """A shortest walking route from ``start`` to ``goal``; [] if they're the same room, None if there's none."""
    came = _search(world, start, doors, goal, level)
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


def entrances(world: World, area: str, doors: bool = True, level: int | None = None) -> list[Step]:
    """Walkable steps from a room outside the area into one inside it."""
    inside = set(rooms_in(world, area))
    return [s for vnum in sorted(world.rooms) if vnum not in inside
            for s in steps_from(world, vnum, doors, level) if s.to_vnum in inside]
