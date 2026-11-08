"""Mob special procedures: parsed from special.cpp and added to the combat model's damage."""

import shutil

import pytest

from xania_explorer.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_explorer.paths import XaniaPaths
from xania_explorer.source.specials import breath_damage, load_specials, special_damage_per_round, spell_damage

pytestmark = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


@pytest.fixture(scope="module")
def src():
    return XaniaPaths.resolve().src_dir


@pytest.fixture(scope="module")
def specials(src):
    return load_specials(src)


def test_caster_tables_cover_every_switch_value(specials):
    assert {"spec_cast_mage", "spec_cast_cleric", "spec_cast_undead", "spec_cast_bastard"} <= set(specials.casters)
    for c in specials.casters.values():
        total = sum(x.weight for x in c.cases)
        assert total in (1, 16), (c.name, total)  # one fixed spell, or all 16 values of number_bits(4)
        assert 0 < c.pick <= 1
    mage = specials.casters["spec_cast_mage"]
    assert mage.pick == 1 / 8
    assert next(x for x in mage.cases if x.spell == "acid blast").weight == 9  # case 7..10 + default
    assert specials.casters["spec_cast_judge"].cases[0].spell == "high explosive"


def test_breath_any_shares_sum_to_one(specials):
    assert abs(sum(specials.breath_any.values()) - 1) < 1e-9
    assert specials.dragon_pick == 1 / 8


def test_damage_is_sensible(specials, src):
    mage = [special_damage_per_round(specials, "spec_cast_mage", lvl, 1000, lvl, src) for lvl in (10, 50, 90)]
    assert 0 < mage[0] < mage[1] < mage[2]
    assert abs(breath_damage(1500, 1.0) - breath_damage(1500, 0) / 2) < 1e-9  # a sure save halves it
    capped = (2000 / 20 + 16 + 2000 / 15) / 2  # a breather far above 2000 HP breathes at the cap most of the fight
    assert breath_damage(10_000, 0) < capped and breath_damage(10_000, 0) > 0.9 * capped
    assert spell_damage("dispel evil", 50, 50, {}, 1000) == 0  # a neutral player is immune
    assert special_damage_per_round(specials, "spec_thief", 50, 1000, 50, src) == 0


def test_combat_adds_spell_damage():
    from xania_explorer.assess import combat as CB

    a = CB.analyse(load_world())
    fights = [f for lvl in (40, 91) for _, f in a.results[("knight", lvl)].fights]
    with_spells = [f for f in fights if f.spell_dpr > 0]
    assert with_spells
    assert all(abs(f.damage_taken - f.rounds * (f.mob_dpr + f.spell_dpr)) < 1e-6 for f in with_spells)
    assert "Mob specials** (special.cpp" in a.method()


def test_without_special_cpp_combat_still_runs(tmp_path):
    """special.cpp is optional: without it combat is melee-only and says so; no system becomes unavailable."""
    from xania_explorer import explore
    from xania_explorer.assess import combat as CB

    paths = XaniaPaths.resolve()
    shutil.copytree(paths.area_dir, tmp_path / "area")
    shutil.copytree(paths.src_dir, tmp_path / "src", ignore=shutil.ignore_patterns("special.cpp", "*.o"))
    a = CB.analyse(load_world(XaniaPaths.resolve(tmp_path)))
    assert a.specials is None
    assert all(f.spell_dpr == 0 for _, f in a.results[("knight", 50)].fights)
    assert "aren't modelled" in a.method()
    assert "special.cpp" in explore.SOURCE_FILES
    tree = [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()]
    plan = explore.plan(tree)
    assert plan.ok and not plan.unavailable
