"""Walking routes over a small hand-made world."""

import pytest

from xania_explorer.areafile import graph as G
from xania_explorer.areafile.world import load_world


def _room(vnum, name, exits=""):
    return f"#{vnum}\n{name}~\n{name}.\n~\n0 0\n{exits}S\n"


def _exit(d, to, locks=0, key=-1):
    return f"D{d}\n~\n~\n{locks} {key} {to}\n"


# 100 -n-> 101 -e-> 102 (door) ; 101 -u-> 103 ; 103 has a cosmetic exit and a dangling one; 104 is isolated.
# Area Two (200) is entered from 102 going north.
ONE = ("#AREA\nOne.are~\nOne~\n{ 1 10} Test One~\n100 110\n\n#ROOMS\n"
       + _room(100, "Start", _exit(0, 101))
       + _room(101, "Hall", _exit(2, 100) + _exit(1, 102, locks=1, key=150) + _exit(4, 103))
       + _room(102, "Vault", _exit(3, 101, locks=1, key=150) + _exit(0, 200))
       + _room(103, "Attic", _exit(5, 101) + _exit(0, -1) + _exit(1, 999))
       + _room(104, "Island")
       + "#0\n\n#$\n")
TWO = "#AREA\nTwo.are~\nTwo~\n{ 1 10} Test Two~\n200 210\n\n#ROOMS\n" + _room(200, "Garden", _exit(2, 102)) \
      + "#0\n\n#$\n"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    d = tmp_path_factory.mktemp("graph") / "area"
    d.mkdir()
    (d / "area.lst").write_text("One.are\nTwo.are\n$\n")
    (d / "One.are").write_text(ONE)
    (d / "Two.are").write_text(TWO)
    return load_world(d)


def test_steps_skip_cosmetic_and_dangling_exits(world):
    assert [(s.command, s.to_vnum) for s in G.steps_from(world, 103)] == [("down", 101)]
    assert G.steps_from(world, 999) == []


def test_doors_are_walkable_unless_excluded(world):
    vault = next(s for s in G.steps_from(world, 101) if s.to_vnum == 102)
    assert vault.door and vault.key == 150 and vault.command == "east"
    assert 102 not in {s.to_vnum for s in G.steps_from(world, 101, doors=False)}


def test_path_is_shortest_and_crosses_areas(world):
    route = G.path(world, 100, 200)
    assert [s.command for s in route] == ["north", "east", "north"]
    assert [s.from_vnum for s in route] == [100, 101, 102]
    assert G.path(world, 100, 100) == []
    assert G.path(world, 100, 104) is None
    assert G.path(world, 100, 200, doors=False) is None


def test_distances_and_reachable(world):
    assert G.distances(world, 100) == {100: 0, 101: 1, 102: 2, 103: 2, 200: 3}
    assert G.reachable(world, 100, doors=False) == {100, 101, 103}
    assert G.distances(world, 12345) == {}


def test_rooms_in_and_entrances(world):
    assert G.rooms_in(world, "One") == [100, 101, 102, 103, 104]
    assert G.rooms_in(world, "Two.are") == [200]
    assert [(s.from_vnum, s.command) for s in G.entrances(world, "Two")] == [(102, "north")]
    with pytest.raises(KeyError):
        G.rooms_in(world, "Nowhere")


# Restricted rooms (RoomFlag.hpp: NewbiesOnly = R = bit 17, HeroesOnly = Q = bit 16, GodsOnly = P = bit 15):
# 300 -n-> 301 (newbies only) ; 300 -e-> 302 (heroes only) ; 300 -s-> 303 (gods only) ; 301 -n-> 304
GATED = ("#AREA\nGated.are~\nGated~\n{ 1 91} Test Gated~\n300 310\n\n#ROOMS\n"
         + _room(300, "Square", _exit(0, 301) + _exit(1, 302) + _exit(2, 303))
         + f"#301\nSchool~\nSchool.\n~\n{1 << 17} 0\n" + _exit(2, 300) + _exit(0, 304) + "S\n"
         + f"#302\nHall of Heroes~\nHall.\n~\n{1 << 16} 0\n" + _exit(3, 300) + "S\n"
         + f"#303\nShrine~\nShrine.\n~\n{1 << 15} 0\n" + _exit(0, 300) + "S\n"
         + _room(304, "Classroom", _exit(2, 301))
         + "#0\n\n#$\n")


@pytest.fixture(scope="module")
def gated(tmp_path_factory):
    d = tmp_path_factory.mktemp("gated") / "area"
    d.mkdir()
    (d / "area.lst").write_text("Gated.are\n$\n")
    (d / "Gated.are").write_text(GATED)
    return load_world(d)


def test_level_gated_rooms(gated):
    """Char::can_see(const Room &): a mortal can't see, so can't enter, a room restricted above (or below) its
    level, and the game doesn't list the exit. Without a level every room counts, as before."""
    assert G.reachable(gated, 300) == {300, 301, 302, 303, 304}
    assert G.reachable(gated, 300, level=5) == {300, 301, 304}  # newbies: school yes, heroes and gods no
    assert G.reachable(gated, 300, level=6) == {300}
    assert G.reachable(gated, 300, level=91) == {300, 302}
    assert [s.to_vnum for s in G.path(gated, 300, 304, level=3)] == [301, 304]
    assert G.path(gated, 300, 304, level=20) is None
    assert G.distances(gated, 300, level=20) == {300: 0}
    assert [s.to_vnum for s in G.steps_from(gated, 300, level=91)] == [302]
