import pytest

from xania_explorer.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_explorer.assess import combat as CB


def test_interpolate_matches_cpp_integer_division():
    assert CB.interpolate(0, -1, -47) == -1
    assert CB.interpolate(32, -1, -47) == -47
    assert CB.interpolate(64, -4, -76) == -148  # extrapolates past 32
    assert CB.interpolate(10, -4, -76) == -26  # -4 + trunc(10 * -72 / 32) = -4 - 22


def test_hit_chance_clamps_and_ratios():
    assert CB.hit_chance(-50, -100) == pytest.approx(0.5)
    assert CB.hit_chance(-500, -10) == pytest.approx(0.95)  # upper clamp
    assert CB.hit_chance(-1, -500) == pytest.approx(0.10)  # lower clamp
    assert CB.hit_chance(-50, 20) == pytest.approx(0.95)  # positive AC counts as 1


def test_base_exp_table():
    assert CB.base_exp(0) == 85
    assert CB.base_exp(-10) == 0
    assert CB.base_exp(5) == 170  # 150 + 20 × (5 − 4)


def test_xp_per_kill_scaling():
    # level 20, same-level neutral mob: 85, solo ×1.5
    assert CB.xp_per_kill(20, 20, 0, False) == 85 * 1.5
    # strongly aligned victim: ×1.25 for a neutral killer
    assert CB.xp_per_kill(20, 20, 800, False) == int(85 * 1.25) * 1.5
    # low-level bonus: level 1 → ×10/5
    assert CB.xp_per_kill(1, 1, 0, True) == 85 * 10 // 5 * 1.5
    # high-level cut: level 50 → ×100/(16+100)
    assert CB.xp_per_kill(50, 50, 0, True) == 85 * 100 // 116 * 1.5


def test_enhanced_damage_factor():
    assert CB.enhanced_damage_factor(0) == 1
    assert CB.enhanced_damage_factor(100) == pytest.approx(1 + 5050 / 10000)


@pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")
def test_model_runs_and_is_plausible():
    a = CB.analyse(load_world())
    r = a.results[("knight", 30)]
    assert r.fights and 0 < r.weighted_mean("hit_pc") <= 0.95
    assert 1 < r.kills_per_level < 50
    assert a.hours_to_hero("knight") < a.hours_to_hero("mage")
