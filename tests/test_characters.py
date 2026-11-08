import pytest

from xania_explorer.areafile.world import DEFAULT_AREA_DIR
from xania_explorer.assess import characters as CH

needs_xania = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


def test_exp_per_level_matches_cpp():
    # skills.cpp exp_per_level, worked by hand:
    assert CH.exp_per_level(40, 100) == 1000  # human default build
    assert CH.exp_per_level(39, 150) == 1500  # < 40 points: flat 1000 × mult
    assert CH.exp_per_level(45, 100) == 1250  # 5 points over: +5 × 500 / 10
    assert CH.exp_per_level(60, 100) == 2000  # +500, +500 (inc doubles to 1000)
    assert CH.exp_per_level(80, 100) == 4000  # +500 +500 +1000 +1000
    assert CH.exp_per_level(60, 150) == 3000
    assert CH.exp_per_level(200, 150) == CH.XP_CAP


def test_expected_gains():
    # HP: (con bonus + roll) × 9 // 10, at least 1. A mage (rolls 6–8) with con 18 (+3):
    # (9*9)//10 = 8, (10*9)//10 = 9, (11*9)//10 = 9
    assert CH.expected_hp_gain(3, 6, 8) == pytest.approx((8 + 9 + 9) / 3)


def test_mana_gain_ignores_stats_at_or_below_15():
    for factor in (10, 8, 6, 3):
        assert CH.expected_mana_gain(factor, 15, 15) == factor // 2  # (0 + 150) // 300 = 0


@needs_xania
def test_builds():
    a = {b.label: b for b in CH.builds()}
    assert len(a) == 40  # 10 PC races × 4 classes
    assert a["dragon mage"].xp_per_level == 4000
    human_mage = a["human mage"]
    assert human_mage.start_stats["int"] == 17  # 14 + 3 prime bonus
    assert a["dragon mage"].start_stats["int"] == 16  # dragons don't get the bonus
    assert human_mage.max_stats["int"] == 20  # 18 + 2 for the prime stat
    assert human_mage.at(1).hp == CH.START_HIT  # no trains go to HP while stats can still be raised
    assert human_mage.at(91).hp > human_mage.at(50).hp > human_mage.at(10).hp
    assert a["human barbarian"].at(91).hp > a["human mage"].at(91).hp
