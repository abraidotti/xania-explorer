"""Loads the real Xania area files from ../xania/area."""

import pytest

from xania_utils.areafile.world import DEFAULT_AREA_DIR, load_world

pytestmark = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


@pytest.fixture(scope="module")
def world():
    return load_world()


def test_every_listed_file_loads_cleanly(world):
    assert [str(p) for p in world.problems] == []
    assert [str(d) for d in world.diagnostics] == []
    assert len(world.files) == len(world.load_order)


def test_plausible_totals(world):
    assert len(world.areas) > 60
    assert len(world.rooms) > 4000
    assert len(world.mobs) > 1500
    assert len(world.objects) > 2000


def test_dell_spot_checks(world):
    dell = world.area_named("Dell.are")
    assert dell.name == "The Dell"
    assert [m.vnum for m in dell.file.mobs] == [12100, 12101, 12102, 12103, 12104]
    priest = world.mobs[12100]
    assert priest.level == 112 and str(priest.hit) == "1d1+7600" and priest.attack == "wrath"
    assert "Plains of the North" in dell.linked_areas


def test_unlisted_files_are_reported(world):
    assert "proto.are" in world.unlisted_files


def test_mobprogs_loaded(world):
    beggar = world.mobprogs["beggar.prg"]
    assert beggar[0].trigger == "greet_prog" and beggar[0].args == "30"


def test_catalogue_is_deterministic(world, tmp_path):
    from xania_utils.gen.area_catalogue import render_area, render_index

    assert render_index(world) == render_index(world)
    dell = world.area_named("Dell.are")
    assert render_area(world, dell) == render_area(world, dell)
