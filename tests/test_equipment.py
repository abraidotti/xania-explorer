import pytest

from xania_explorer.areafile.model import Obj, ObjAffect
from xania_explorer.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_explorer.assess import equipment as E

LOC = {name: i for i, name in enumerate(__import__("xania_explorer.areafile.flags", fromlist=["x"]).AFFECT_LOCATIONS)}


def armour(level: int, affects: list[tuple[str, int]], values=(10, 10, 10, 10), wear: int = 1 | 1 << 3) -> E.Item:
    obj = Obj(1, "test", "a test", "A test.", "steel", "armor", 9, 0, wear, None, list(values) + [0], level, 1, 1,
              "P", [ObjAffect(LOC[loc], mod) for loc, mod in affects])
    return E.Item(obj, [])


def test_points_rule_matches_entity_balance():
    # HP/move count one point per 7 (rounded up), stats and hit/dam one each.
    assert armour(23, [("Hit", 25), ("Move", 100)]).points == 4 + 15
    assert armour(10, [("Str", 2), ("Hitroll", 1), ("Damroll", 1)]).points == 4
    assert armour(10, [("Str", -2)]).points == 0  # penalties are free
    assert E.points_allowed(23) == 3


def test_ac_affects_are_not_counted_like_the_cpp():
    item = armour(10, [("Ac", -10), ("SavingSpell", -2)])
    assert item.points == 0  # AFFECT_DATA.cpp:86 bug
    assert item.points_if_ac_counted == 12


def test_item_ac_and_slots():
    item = armour(5, [("Ac", -4)], values=(8, 8, 4, 0))
    assert item.ac == 5 + 4
    assert item.slots == ["body"]


@pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")
def test_kits_grow_with_level():
    a = E.analyse(load_world())
    assert a.ac_kits[91].total("ac") > a.ac_kits[30].total("ac") > a.ac_kits[5].total("ac")
    assert all(len(a.ac_kits[91].picks[s]) == n for s, n in E.SLOTS.items())  # every slot filled at 91
