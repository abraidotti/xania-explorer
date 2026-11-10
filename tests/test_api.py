"""The public API other programs (xania-sim) depend on. Changing a pinned name or signature is a breaking change:
update the pin here and the callers together."""

import inspect

import pytest

from xania_explorer import api
from xania_explorer.areafile.world import DEFAULT_AREA_DIR

PINNED = {
    "load_world": "(xania: 'XaniaPaths | Path | str | None' = None) -> 'World'",
    "steps_from": "(world: 'World', vnum: 'int', doors: 'bool' = True, level: 'int | None' = None) -> 'list[Step]'",
    "path": "(world: 'World', start: 'int', goal: 'int', doors: 'bool' = True, level: 'int | None' = None) "
            "-> 'list[Step] | None'",
    "distances": "(world: 'World', start: 'int', doors: 'bool' = True, level: 'int | None' = None) "
                 "-> 'dict[int, int]'",
    "reachable": "(world: 'World', start: 'int', doors: 'bool' = True, level: 'int | None' = None) -> 'set[int]'",
    "rooms_in": "(world: 'World', area: 'str') -> 'list[int]'",
    "entrances": "(world: 'World', area: 'str', doors: 'bool' = True, level: 'int | None' = None) "
                 "-> 'list[Step]'",
    "predict_fight": "(world: 'World', cls: 'str', level: 'int', mob_vnum: 'int', caster: 'bool' = False) "
                     "-> 'FightPrediction'",
    "predict_spell": "(world: 'World', cls: 'str', spell: 'str', caster_level: 'int', victim_level: 'int', "
                     "skill: 'float | None' = None, mob_vnum: 'int | None' = None) -> 'SpellPrediction'",
    "area_profile": "(world: 'World', area: 'str') -> 'DF.AreaProfile'",
    "classes": "() -> 'list[str]'",
    "pc_races": "(src_dir: 'Path | None' = None) -> 'list[str]'",
    "abilities": "(cls: 'str', src_dir: 'Path | None' = None) -> 'list[AbilityInfo]'",
    "directions": "() -> 'list[str]'",
}
PINNED_FIELDS = {
    "Step": ["from_vnum", "direction", "to_vnum", "door", "key"],
    "FightPrediction": ["cls", "level", "mob_vnum", "mob_level", "player_hp", "hit_chance", "mob_hit_chance",
                        "rounds", "damage_taken", "encounter_damage", "xp"],
    "SpellPrediction": ["spell", "caster_level", "victim_level", "skill", "save_chance", "mana", "beats",
                        "damage_min", "damage_max", "damage_expected", "damage_type", "tolerance"],
    "AbilityInfo": ["name", "level", "is_spell", "in_default", "min_mana", "beats"],
}


def test_exports_are_pinned():
    assert set(api.__all__) == set(PINNED) | set(PINNED_FIELDS) | {"RECALL_ROOM", "World", "AreaProfile"}
    for name in api.__all__:
        assert hasattr(api, name), name


@pytest.mark.parametrize("name", sorted(PINNED))
def test_signature_is_pinned(name):
    assert str(inspect.signature(getattr(api, name))) == PINNED[name]


@pytest.mark.parametrize("name", sorted(PINNED_FIELDS))
def test_fields_are_pinned(name):
    assert list(getattr(api, name).__dataclass_fields__)[:len(PINNED_FIELDS[name])] == PINNED_FIELDS[name]


def test_names_need_no_checkout_for_fixed_tables():
    assert api.classes() == ["mage", "cleric", "knight", "barbarian"]
    assert api.directions() == ["north", "east", "south", "west", "up", "down"]


real = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


@pytest.fixture(scope="module")
def world():
    return api.load_world()


@real
def test_temple_routes(world):
    assert api.RECALL_ROOM in world.rooms
    assert len(api.reachable(world, api.RECALL_ROOM)) > 4000
    route = api.path(world, api.RECALL_ROOM, 3054)
    assert route and all(s.command in api.directions() for s in route)


@real
def test_names_from_the_checkout():
    assert "human" in api.pc_races() and "elf" in api.pc_races()
    mage = {a.name: a for a in api.abilities("mage")}
    assert mage["magic missile"].is_spell and mage["magic missile"].in_default and mage["magic missile"].level == 1
    assert [a.level for a in api.abilities("knight")] == sorted(a.level for a in api.abilities("knight"))
    with pytest.raises(KeyError):
        api.abilities("bard")


@real
def test_predict_fight_matches_the_combat_model(world):
    from xania_explorer.assess import combat as CB

    a = CB.analyse(world)
    m = next(m for m in a.mobs if m.mob.level == 10)
    f = api.predict_fight(world, "knight", 10, m.mob.vnum)
    assert f.rounds == pytest.approx(a.fight(a.player("knight", 10), m).rounds)
    assert f.encounter_damage >= f.damage_taken and f.seconds == pytest.approx(f.rounds * 3)
    assert f.deadly == (f.encounter_damage >= f.player_hp)
    assert api.predict_fight(world, "mage", 10, m.mob.vnum, caster=True).rounds < \
        api.predict_fight(world, "mage", 10, m.mob.vnum).rounds
    with pytest.raises(KeyError):
        api.predict_fight(world, "knight", 10, 3001)  # no such combat mob


@real
def test_predict_spell(world):
    s = api.predict_spell(world, "mage", "magic missile", 5, 5)
    assert s.save_chance == 50 and s.damage_min <= s.damage_expected <= s.damage_max
    assert s.per_cast == pytest.approx(s.damage_expected * s.skill / 100)
    assert api.predict_spell(world, "mage", "magic missile", 5, 5, skill=100).per_cast == s.damage_expected
    assert api.predict_spell(world, "mage", "magic missile", 5, 40).save_chance == 85
    with pytest.raises(KeyError):
        api.predict_spell(world, "mage", "sanctuary", 30, 30)  # not a damage spell


@real
def test_area_profile(world):
    p = api.area_profile(world, "Dell.are")
    assert p.name == "The Dell" and "killers" not in repr(p)
    with pytest.raises(KeyError):
        api.area_profile(world, "Nowhere")


def test_level_gated_rooms_on_the_checkout(world):
    """Mud School's inner rooms are NewbiesOnly: from level 6 nobody can walk in, so its level-30 acolyte and
    adepts (in those rooms) aren't fights for anyone, and the school's mob levels are its newbies' levels."""
    from xania_explorer.assess import combat as CB

    assert api.path(world, 3001, 3757, level=3) is not None and api.path(world, 3001, 3757, level=20) is None
    fights = CB.analyse(world).results[("knight", 30)].fights
    assert not [m for m, _ in fights if m.info.area.name == "Mud School"]
    assert api.area_profile(world, "MudSchool.are").span[1] <= 5
