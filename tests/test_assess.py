import pytest

from xania_utils.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_utils.paths import XaniaPaths
from xania_utils.assess import common as C
from xania_utils.assess.sources import MobSpawn, estimated_population
from xania_utils.assess.weapons import allowed_average, class_profiles
from xania_utils.source.cpp_tables import load_skills, starting_skills


def test_bands_cover_1_to_91():
    bands = C.bands()
    assert bands[0] == C.Band(1, 5) and bands[-1] == C.Band(91, 91)
    assert all(any(lvl in b for b in bands) for lvl in C.LEVELS)


def test_spread_even_and_uneven():
    even = C.Spread.of([5, 5, 5, 5])
    assert even.cv == 0 and even.gini == 0
    lumpy = C.Spread.of([0, 0, 0, 20])
    assert lumpy.gini == pytest.approx(0.75) and lumpy.empty_bins == 3


def test_runs_without_increase_longest_first():
    series = {1: None, 2: 5, 3: 5, 4: 5, 5: 7, 6: 7}
    assert C.runs_without_increase(series)[0] == (2, 4, 5)


def test_allowed_average_matches_entity_balance():
    assert allowed_average(10, False) == 9
    assert allowed_average(91, False) == 49
    assert allowed_average(91, True) == 51  # +max(1, 49 // 20)


def test_population_is_capped_by_world_max():
    room = None
    assert estimated_population([MobSpawn(1, room, 3, 1)] * 5) == 3
    assert estimated_population([MobSpawn(1, room, 10, 1)] * 2) == 2
    assert estimated_population([MobSpawn(1, room, 0, 1)]) == 0


def test_skill_table_extraction():
    skills = load_skills()
    assert skills["sword"].ratings == (8, 6, 2, 4)
    assert skills["third attack"].learn_level("mage") == 60  # SkillRatingAttainable -> cross-class
    assert "raise dead" not in skills  # commented out in the C++
    assert {"dagger"} <= starting_skills("mage")
    assert {"sword", "axe", "whip"} <= starting_skills("knight")  # via weaponsmaster


def test_class_profiles():
    by_name = {p.name: p for p in class_profiles(XaniaPaths.resolve().src_dir)}
    assert by_name["barbarian"].starting == ["axe"]
    assert by_name["cleric"].starting == ["mace", "flail"]


@pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")
def test_reports_render_deterministically():
    from xania_utils.assess import mobs, weapons

    world = load_world()
    for mod in (weapons, mobs):
        first = mod.render(world)
        assert first == mod.render(world)
        assert "Headline findings" in first
