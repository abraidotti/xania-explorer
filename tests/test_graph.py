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
