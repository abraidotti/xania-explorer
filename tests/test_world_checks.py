"""World-level checks, exercised on a small deliberately broken world."""

from xania_utils.areafile.world import load_world

BROKEN = """#AREA
Broken.are~
Broken~
{ 1 10} Test Broken~
200 210

#MOBILES
#200
rat~
a rat~
A rat.
~
~
human~
0 0 0 0
1 0 1d1+1 1d1+1 1d1+1 bite
0 0 0 0
0 0 0 0
stand stand neutral 0
0 0 small flesh
#0

#OBJECTS
#201
cheese~
cheese~
Cheese.~
food~
food 0 A
0 0 0 0 0
1 1 1 P
#0

#ROOMS
#200
A~
A.
~
0 0
D0
~
~
0 0 201
D1
~
~
0 0 999
S
#201
B~
B.
~
0 0
D2
~
~
0 0 202
S
#202
C~
C.
~
0 0
S
#0

#RESETS
M 0 200 1 200 1
G 0 201 0
M 0 404 1 200 1
S

#SHOPS
404 0 0 0 0 0 100 100 0 23
0

#$
"""


def make_world(tmp_path, text=BROKEN, extra_files=()):
    (tmp_path / "area.lst").write_text("Broken.are\nMissing.are\n$\n")
    (tmp_path / "Broken.are").write_text(text)
    for name in extra_files:
        (tmp_path / name).write_text("#$\n")
    return load_world(tmp_path)


def kinds(world):
    return sorted(p.kind for p in world.problems)


def test_broken_world_problems(tmp_path):
    w = make_world(tmp_path, extra_files=["Unlisted.are"])
    msgs = "\n".join(map(str, w.problems))
    assert "missing-file" in kinds(w)
    assert "room #200 east -> #999 does not exist" in msgs
    assert "room #200 north -> #201, but its south exit leads to #202" in msgs
    assert "drop rate 0 not in 1..100" in msgs
    assert "'M' reset: mob #404 not found" in msgs
    assert "shop keeper mob #404 not found" in msgs
    assert w.unlisted_files == ["Unlisted.are"]


def test_fatal_parse_is_reported_not_raised(tmp_path):
    w = make_world(tmp_path, text=BROKEN.replace("D0\n", "D9\n"))
    assert any(p.kind == "fatal-parse" and "bad door number" in p.message for p in w.problems)


def test_define_vnum_extends_range_from_mobs_and_objects_only(tmp_path):
    w = make_world(tmp_path, text=BROKEN.replace("#201\ncheese", "#250\ncheese").replace("G 0 201", "G 0 250"))
    area = w.areas[0]
    assert (area.lowest_vnum, area.highest_vnum) == (200, 250)
