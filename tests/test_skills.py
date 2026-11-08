import pytest

from xania_utils.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_utils.source.spell_tables import load_damage_spells, mana_cost, save_chance

needs_xania = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


def test_mana_cost_matches_mana_for_spell():
    assert mana_cost(15, 10, 10) == 50  # just learned: 100 / 2
    assert mana_cost(15, 30, 10) == 15  # 100 / 22 = 4 → min_mana
    assert mana_cost(20, 12, 10) == 25  # 100 / 4


def test_save_chance_clamps():
    assert save_chance(30, 30) == 0.5
    assert save_chance(30, 100) == 0.95
    assert save_chance(90, 10) == 0.05


@needs_xania
def test_damage_tables():
    spells = load_damage_spells()
    fireball = spells["spell_fireball"]
    t = fireball.values[30]
    assert fireball.expected(30, 0.0) == pytest.approx((t // 2 + t * 2) / 2)
    assert fireball.expected(30, 1.0) == pytest.approx(fireball.expected(30, 0.0) / 2)
    assert fireball.expected(500) == fireball.expected(len(fireball.values) - 1)  # clamped to the table


@needs_xania
def test_skill_analysis():
    from xania_utils.assess import skills as S

    a = S.analyse(load_world())
    assert a.spells["mage"][30] is not None and a.spells["mage"][30].damage > 0
    assert a.spells["knight"][30] is None  # no attack spells in the knight default package
    assert a.practices_needed("mage", 91) > 0
    assert a.casts_to_kill("mage", 91) > a.casts_to_kill("mage", 30)
