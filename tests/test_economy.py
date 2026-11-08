import pytest

from xania_utils.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_utils.assess import economy as EC

pytestmark = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


@pytest.fixture(scope="module")
def a():
    return EC.analyse(load_world())


def test_income_accumulates(a):
    assert a.cumulative[91] > a.cumulative[30] > a.cumulative[5] > 0
    assert all(a.gold_per_kill[lvl] >= 2 * 1 for lvl in (5, 30, 60))  # at least the sacrifice value


def test_shop_stock_prices_use_profit_buy(a):
    world = a.world
    shops = {s.keeper: s for f in world.files for s in f.shops}
    item = a.stock[0]
    assert item.price == world.objects[item.vnum].cost * shops[item.keeper].profit_buy // 100


def test_healer_is_flat(a):
    assert a.kills_to_afford(EC.HEALER["heal"], 5) > a.kills_to_afford(EC.HEALER["heal"], 90)
