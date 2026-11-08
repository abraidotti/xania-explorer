import pytest

from xania_utils.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_utils.assess import levelling as L

ROOMS = """#AREA
Mini.are~
Mini~
{ 1 10} Test Mini~
3000 3010

#ROOMS
#3001
Temple~
T.
~
0 0
D0
~
~
0 0 3002
S
#3002
Hall~
H.
~
0 0
D2
~
~
0 0 3001
D0
~
~
0 0 -3003
S
#3003
Trap~
One way in.
~
0 0
S
#3004
Island~
Nothing leads here.
~
0 0
D2
~
~
0 0 3001
S
#0

#$
"""


def test_distances_follow_exits_including_one_way(tmp_path):
    (tmp_path / "area.lst").write_text("Mini.are\n$\n")
    (tmp_path / "Mini.are").write_text(ROOMS)
    world = load_world(tmp_path)
    d = L.distances(world)
    assert d == {3001: 0, 3002: 1, 3003: 2}  # 3004 has an exit out but none in


@pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")
def test_xp_on_offer_shrinks_with_level():
    a = L.analyse(load_world())
    assert a.levels_of_xp(5) > a.levels_of_xp(50) > 0
    assert len(a.dist) > 0.9 * len(a.world.rooms)
