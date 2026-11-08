import pytest

from xania_utils.areafile import flags as F
from xania_utils.areafile.parser import parse_text
from xania_utils.areafile.reader import AreaParseError

FIXTURE = """#AREA
Test.are~
Test Area~
{ 5 35} Author   Test Area~
100 120

#MOBILES
#100
guard~
a guard~
A guard stands here.
~
He looks bored.
~
human~
BT 0 500 0
10 5 2d8+100 1d1+10 2d4+3 slas
-5 -5 -5 0
CE 0 0 0
stand stand m 50
0 0 l steel
#0

#OBJECTS
#101
sword~
a sword~
A sword lies here.~
steel~
weapon 0 AN
sword 2 5 slash DE
10 8 500 G
A
18 2
E
sword~
Sharp.
~
#102
potion~
a potion~
A potion.~
glass~
potion 0 AO
20 cure light~ 0 0 0
5 1 100 P
#0

#ROOMS
#100
The Gate~
A gate.
~
S 1
D0
~
gate~
1 0 101
D2
~
~
0 0 -105
S
#101
Inside~
Inside.
~
0 0
D2
~
~
0 0 100
S
#0

#RESETS
* comment line
M 0 100 1 100 1  the guard
E 0 101 0 16
O 0 102 0 101
P 0 102 1 102 1
D 0 100 0 2
S

#SHOPS
100 10 0 0 0 0 150 50 6 22
0

#SPECIALS
M 100 spec_guard
S

#$
"""


@pytest.fixture
def parsed():
    return parse_text(FIXTURE, "Test.are")


def test_fixture_parses_without_warnings(parsed):
    af, diags = parsed
    assert diags == []
    h = af.header
    assert (h.short_name, h.min_level, h.max_level, h.lowest_vnum, h.highest_vnum) == ("Test Area", 5, 35, 100, 120)
    assert af.sections == ["AREA", "MOBILES", "OBJECTS", "ROOMS", "RESETS", "SHOPS", "SPECIALS"]


def test_mob_fields_and_prefix_lookups(parsed):
    m = parsed[0].mobs[0]
    assert m.vnum == 100 and m.level == 10 and m.hitroll == 5
    assert str(m.hit) == "2d8+100" and m.hit.average == 109
    assert m.attack == "slash"  # "slas" is a prefix of "slash"
    assert m.sex == "male"  # "m"
    assert m.body_size == "large"  # "l"
    assert m.start_pos == "Standing"  # "stand"
    assert m.act_names == ["Sentinel", "Warrior"]
    assert m.off_names == ["Bash", "Disarm"]
    assert m.ac == (-5, -5, -5, 0)


def test_attack_prefix_takes_first_table_match():
    af, _ = parse_text(FIXTURE.replace(" slas\n", " s\n"))
    assert af.mobs[0].attack == "slice"  # first attack in the table starting with "s"


def test_objects(parsed):
    sword, potion = parsed[0].objects
    assert sword.type_name == "Weapon"
    assert sword.values == ["sword", 2, 5, "slash", (1 << 3) | (1 << 4)]
    assert F.decode(sword.values[4], F.WEAPON_FLAG) == ["Sharp", "Vorpal"]
    assert sword.condition == 90
    assert [(a.location_name, a.modifier) for a in sword.affects] == [("Hitroll", 2)]
    assert sword.extra_descr[0].keywords == "sword"
    assert potion.type_name == "Potion" and potion.values == [20, "cure light", 0, 0, 0]


def test_rooms_and_exits(parsed):
    gate, _inside = parsed[0].rooms
    assert gate.room_flags == 1 << 18 and gate.sector == 1
    north = gate.exits[0]
    assert north.is_door and north.keyword == "gate" and north.to_vnum == 101
    south = gate.exits[2]
    assert south.one_way and south.to_vnum == 105


def test_resets_attach_like_cpp(parsed):
    af = parsed[0]
    # E follows the last M's room; P follows the last O's room.
    assert [(r.command, r.room_vnum) for r in af.resets] == [
        ("M", 100), ("E", 100), ("O", 101), ("P", 101), ("D", 100)]
    assert af.resets[0].arg4 == 1 and af.resets[0].comment == "the guard"
    assert af.resets[1].arg3 == 16


def test_shop_and_special(parsed):
    af = parsed[0]
    s = af.shops[0]
    assert s.keeper == 100 and s.buy_types == [10, 0, 0, 0, 0] and (s.profit_buy, s.profit_sell) == (150, 50)
    assert af.specials[0].spec_fun == "spec_guard"


def test_unknown_attack_is_logged_and_defaults_to_hit():
    af, diags = parse_text(FIXTURE.replace(" slas\n", " 5\n"))
    assert af.mobs[0].attack == "hit"
    assert any("Invalid attack type" in d.message for d in diags)


def test_quoted_spell_name_is_fatal():
    with pytest.raises(AreaParseError):
        parse_text(FIXTURE.replace("cure light~", "'cure light'~"))


def test_noremove_on_non_weapon_is_fatal():
    with pytest.raises(AreaParseError):
        parse_text(FIXTURE.replace("potion 0 AO", "potion M AO"))
