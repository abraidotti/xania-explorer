"""Load the whole world the way ``boot_db`` does (db.cpp:190).

Reads ``area.lst`` in order, parses each file, builds global vnum indexes and
resolves exits. Anything the C++ would reject (fatal) or silently mishandle is
collected in ``World.problems`` rather than raised, so tools can report on it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import flags as F
from .model import AreaFile, Mob, Obj, Room
from .mobprog import MobProg, parse_prg_file
from .parser import parse_file
from ..paths import XaniaPaths
from .reader import AreaParseError, Diagnostic, Reader

DEFAULT_AREA_DIR = XaniaPaths.resolve().area_dir  # default checkout; see xania_utils/paths.py


@dataclass
class Problem:
    kind: str  # short slug, e.g. "fatal-parse", "missing-file", "dangling-exit"
    file: str
    message: str
    line: int = 0
    fatal_in_cpp: bool = False

    def __str__(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        return f"[{self.kind}] {where}: {self.message}"


@dataclass
class Area:
    """A loaded area: one file's contents plus world-derived facts."""

    file: AreaFile
    index: int  # load order among areas with an #AREA header (Area::num)
    lowest_vnum: int
    highest_vnum: int  # effective range after define_vnum (mobs+objects extend it; rooms don't)
    linked_areas: set[str] = field(default_factory=set)  # short names reachable by an exit

    @property
    def name(self) -> str:
        return self.file.name

    @property
    def filename(self) -> str:
        return self.file.filename


@dataclass
class World:
    xania: XaniaPaths
    load_order: list[str]
    files: list[AreaFile] = field(default_factory=list)
    areas: list[Area] = field(default_factory=list)
    rooms: dict[int, Room] = field(default_factory=dict)
    mobs: dict[int, Mob] = field(default_factory=dict)
    objects: dict[int, Obj] = field(default_factory=dict)
    room_area: dict[int, Area] = field(default_factory=dict)
    mob_area: dict[int, Area] = field(default_factory=dict)
    obj_area: dict[int, Area] = field(default_factory=dict)
    mobprogs: dict[str, list[MobProg]] = field(default_factory=dict)  # by .prg filename
    unlisted_files: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)  # logger.bug equivalents
    problems: list[Problem] = field(default_factory=list)

    @property
    def area_dir(self) -> Path:
        return self.xania.area_dir

    @property
    def src_dir(self) -> Path:
        return self.xania.src_dir

    def area_named(self, name: str) -> Area | None:
        return next((a for a in self.areas if a.name == name or a.filename == name), None)


def read_area_list(area_dir: Path) -> list[str]:
    """``area.lst``: whitespace-separated filenames up to one starting with ``$``."""
    r = Reader.from_path(area_dir / "area.lst")
    names = []
    while True:
        r.skip_ws()
        if r.at_eof:
            break
        word = r.read_word()
        if word.startswith("$"):
            break
        names.append(word)
    return names


def _define_vnum(area: Area, vnum: int) -> None:
    """``Area::define_vnum`` (Area.cpp:45), quirks included."""
    if area.lowest_vnum == 0 or area.highest_vnum == 0:
        area.lowest_vnum = area.highest_vnum = vnum
    if not area.lowest_vnum <= vnum <= area.highest_vnum:
        if vnum < area.lowest_vnum:
            area.lowest_vnum = vnum
        else:
            area.highest_vnum = vnum


def load_world(xania: XaniaPaths | Path | str | None = None) -> World:
    """Load a world from a Xania checkout root or an area directory (default: XaniaPaths.resolve())."""
    paths = xania if isinstance(xania, XaniaPaths) else XaniaPaths.resolve(xania)
    paths.check()
    area_dir = paths.area_dir
    world = World(paths, read_area_list(area_dir))
    current: Area | None = None  # C++ areas.back()

    for name in world.load_order:
        path = area_dir / name
        if name == "-":
            continue  # stdin; not used in practice
        if not path.exists():
            world.problems.append(Problem("missing-file", name, "listed in area.lst but not on disk", fatal_in_cpp=True))
            continue
        path = _follow_placeholder(path)
        try:
            af, diags = parse_file(path)
        except AreaParseError as e:
            world.problems.append(Problem("fatal-parse", name, e.message, e.line, fatal_in_cpp=True))
            continue
        af.filename = name
        world.files.append(af)
        world.diagnostics.extend(diags)

        if af.header:
            h = af.header
            current = Area(af, len(world.areas), h.lowest_vnum, h.highest_vnum)
            world.areas.append(current)
        owner = current
        if owner is None and (af.mobs or af.objects or af.rooms):
            world.problems.append(Problem("no-area", name, "mobs/objects/rooms before any #AREA", fatal_in_cpp=True))
            continue

        for mob in af.mobs:
            _define_vnum(owner, mob.vnum)
            if mob.vnum in world.mobs:
                world.problems.append(Problem("duplicate-vnum", name, f"mob #{mob.vnum} duplicated", mob.line, True))
            world.mobs[mob.vnum] = mob
            world.mob_area[mob.vnum] = owner
        for obj in af.objects:
            if obj.vnum in world.objects:
                world.problems.append(Problem("duplicate-vnum", name, f"object #{obj.vnum} duplicated", obj.line, True))
            world.objects[obj.vnum] = obj
            world.obj_area[obj.vnum] = owner
            _define_vnum(owner, obj.vnum)
        for room in af.rooms:
            if room.vnum in world.rooms:
                world.problems.append(Problem("duplicate-vnum", name, f"room #{room.vnum} duplicated", room.line, True))
            world.rooms[room.vnum] = room
            world.room_area[room.vnum] = owner

    _find_unlisted(world)
    _load_mobprogs(world)
    _check_references(world)
    _link_areas(world)
    return world


def _follow_placeholder(path: Path) -> Path:
    """``area/version.are`` is a git symlink to ``version.are.in`` (CMake fills it in at build time).
    On Windows, git may check a symlink out as an empty file or as a text file holding the target
    name; follow either to the real file."""
    if path.stat().st_size == 0 and path.with_suffix(path.suffix + ".in").exists():
        return path.with_suffix(path.suffix + ".in")
    if path.stat().st_size < 256:
        target = path.read_text(encoding="latin-1").strip()
        if target and "\n" not in target and not target.startswith("#") and (path.parent / target).is_file():
            return path.parent / target
    return path


def _find_unlisted(world: World) -> None:
    listed = set(world.load_order)
    world.unlisted_files = sorted(
        p.name for p in world.area_dir.glob("*.are") if p.name not in listed
    )


def _load_mobprogs(world: World) -> None:
    for af in world.files:
        for ref in af.mobprogs:
            if ref.filename in world.mobprogs:
                continue
            path = world.area_dir / ref.filename
            if not path.exists():
                world.problems.append(Problem("missing-mobprog", af.filename,
                                              f"mob #{ref.mob_vnum}: can't open {ref.filename}", ref.line, True))
                continue
            try:
                world.mobprogs[ref.filename] = parse_prg_file(path)
            except AreaParseError as e:
                world.problems.append(Problem("fatal-parse", ref.filename, e.message, e.line, True))


def _check_references(world: World) -> None:
    """Cross-file checks the C++ performs at boot (some fatal), plus a few it
    silently gets wrong."""
    for af in world.files:
        fn = af.filename
        for shop in af.shops:
            if shop.keeper not in world.mobs:
                world.problems.append(Problem("dangling-ref", fn, f"shop keeper mob #{shop.keeper} not found",
                                              shop.line, True))
        for sp in af.specials:
            if sp.mob_vnum not in world.mobs:
                world.problems.append(Problem("dangling-ref", fn, f"special on unknown mob #{sp.mob_vnum}", sp.line, True))
        for ref in af.mobprogs:
            if ref.mob_vnum not in world.mobs:
                world.problems.append(Problem("dangling-ref", fn, f"mobprog on unknown mob #{ref.mob_vnum}", ref.line, True))
        keepers = {s.keeper for f in world.files for s in f.shops}
        last_mob = None
        for rs in af.resets:
            _check_reset(world, fn, rs)
            if rs.command == "M":
                last_mob = rs.arg1
            elif rs.command in "GE" and last_mob not in keepers and not 1 <= rs.arg2 <= 100:
                # reset_room (db.cpp): an invalid drop rate on a non-shopkeeper calls exit(1)
                # *at reset time*, i.e. it crashes a running MUD rather than failing boot.
                world.problems.append(Problem(
                    "bad-drop-rate", fn, f"'{rs.command}' reset of object #{rs.arg1} on mob #{last_mob}: "
                    f"drop rate {rs.arg2} not in 1..100", rs.line, True))
            if rs.command == "E" and not 0 <= rs.arg3 < 19:
                world.problems.append(Problem(
                    "bad-wear-location", fn, f"'E' reset of object #{rs.arg1}: wear location {rs.arg3}", rs.line))

    for vnum, room in world.rooms.items():
        fn = world.room_area[vnum].filename
        for exit_ in room.exits.values():
            if exit_.cosmetic or exit_.to_vnum == 0:
                continue
            if exit_.to_vnum not in world.rooms:
                world.problems.append(Problem(
                    "dangling-exit", fn, f"room #{vnum} {exit_.direction_name} -> #{exit_.to_vnum} does not exist",
                    room.line))
                continue
            # map_exit_destinations (db.cpp:804): logs "Fix_exits" when the reverse exit of a two-way exit
            # leads somewhere else. If that reverse exit leads nowhere, the C++ dereferences a null pointer.
            back = world.rooms[exit_.to_vnum].exits.get(F.REVERSE_DIRECTION[exit_.direction])
            if back is None or exit_.one_way:
                continue
            back_resolves = back.to_vnum > 0 and not back.cosmetic and back.to_vnum in world.rooms
            if not back_resolves:
                world.problems.append(Problem(
                    "reverse-exit-null", fn,
                    f"room #{vnum} {exit_.direction_name} -> #{exit_.to_vnum}, whose return exit leads nowhere "
                    "(null dereference in map_exit_destinations)", room.line, True))
            elif back.to_vnum != vnum:
                world.problems.append(Problem(
                    "asymmetric-exit", fn,
                    f"room #{vnum} {exit_.direction_name} -> #{exit_.to_vnum}, but its "
                    f"{F.DIRECTIONS[F.REVERSE_DIRECTION[exit_.direction]]} exit leads to #{back.to_vnum}",
                    room.line))


def _check_reset(world: World, fn: str, rs) -> None:
    def need(table, vnum, what):
        if vnum not in table:
            world.problems.append(Problem("dangling-ref", fn, f"'{rs.command}' reset: {what} #{vnum} not found",
                                          rs.line))

    c = rs.command
    if c == "M":
        need(world.mobs, rs.arg1, "mob")
        need(world.rooms, rs.arg3, "room")
    elif c == "O":
        need(world.objects, rs.arg1, "object")
        need(world.rooms, rs.arg3, "room")
    elif c in "PGE":
        need(world.objects, rs.arg1, "object")
        if c == "P":
            need(world.objects, rs.arg3, "container object")
    elif c in "DR":
        need(world.rooms, rs.arg1, "room")
        if c == "D" and rs.arg1 in world.rooms:
            ex = world.rooms[rs.arg1].exits.get(rs.arg2)
            if ex is None or not ex.is_door:
                world.problems.append(Problem("bad-door-reset", fn,
                                              f"'D' reset: room #{rs.arg1} exit {rs.arg2} is not a door",
                                              rs.line, True))
    # A reset attached to a room outside its area's vnum range is never run by
    # that area's Area::reset() (which iterates lowest..highest vnum).
    if rs.room_vnum and rs.room_vnum in world.rooms:
        area = world.room_area[rs.room_vnum]
        if not area.lowest_vnum <= rs.room_vnum <= area.highest_vnum:
            world.problems.append(Problem(
                "reset-outside-range", fn,
                f"'{c}' reset on room #{rs.room_vnum}, outside {area.name}'s vnum range "
                f"{area.lowest_vnum}-{area.highest_vnum}", rs.line))


def _link_areas(world: World) -> None:
    """Area adjacency, as in xania/src/apps/areas.cpp."""
    for vnum, room in world.rooms.items():
        here = world.room_area[vnum]
        for exit_ in room.exits.values():
            if exit_.to_vnum > 0 and exit_.to_vnum in world.rooms:
                there = world.room_area[exit_.to_vnum]
                if there is not here:
                    here.linked_areas.add(there.name)


def resets_by_area(world: World) -> dict[str, list]:
    out = defaultdict(list)
    for af in world.files:
        out[af.filename].extend(af.resets)
    return out
