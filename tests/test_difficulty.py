"""Area difficulty: each area profiled at its own level and compared with its peers."""

import pytest

from xania_explorer.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_explorer.assess import difficulty as D

pytestmark = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


@pytest.fixture(scope="module")
def world():
    return load_world()


@pytest.fixture(scope="module")
def a(world):
    return D.analyse(world)


def test_every_area_with_combat_mobs_is_profiled(a):
    assert len(a.areas) >= 50
    for p in a.areas:
        assert 1 <= p.level <= 91 and p.span[0] <= p.span[1]
        assert 0 <= p.deadly <= 1 and p.hp_loss >= 0
        if p.population < D.MIN_POPULATION:
            assert p.peer_ratio is None and p.verdict == "no peers"  # tiny areas are never compared


def test_outliers_and_tails_follow_their_thresholds(a):
    for p in a.outliers("much harder"):
        assert p.peer_ratio >= D.OUTLIER_RATIO
    for p in a.outliers("much easier"):
        assert p.peer_ratio <= 1 / D.OUTLIER_RATIO
    for p in a.tails:
        assert p.deadly - p.peer_deadly >= D.TAIL_POINTS and p.killers


def test_traps_are_aggressive_mobs_far_above_the_band(a):
    for p, m, gap in a.traps:
        assert "Aggressive" in m.mob.act_names and gap >= D.TRAP_GAP
        assert m.mob.level - p.advertised[1] == gap


def test_re_advertising_level_matches_peers(a):
    for p in a.outliers("much harder"):
        level = a.level_to_match_peers(p)
        assert level is None or level > p.level


def test_area_pages_show_their_profile(world, a):
    from xania_explorer.gen.area_catalogue import render_area

    area = next(x for x in world.areas if x.name == a.areas[len(a.areas) // 2].name)
    page = render_area(world, area)
    assert "## Difficulty" in page and "](../difficulty.md)" in page
