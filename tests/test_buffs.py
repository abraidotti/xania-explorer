"""Casters fighting with their default package's buffs and best attack spell."""

import pytest

from xania_explorer.areafile.world import DEFAULT_AREA_DIR, load_world

pytestmark = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


@pytest.fixture(scope="module")
def a():
    from xania_explorer.assess import combat as CB

    return CB.analyse(load_world())


def test_buffs_come_from_the_default_package_and_level(a):
    assert a.buffs("knight", 91).names == ()  # no buffs in a knight's default package
    mage_lo, mage_hi = a.buffs("mage", 5), a.buffs("mage", 91)
    assert "sanctuary" not in mage_lo.names and mage_hi.sanctuary and mage_hi.haste
    assert a.player("knight", 50, buffed=True) == a.player("knight", 50)
    hasted = a.player("mage", 60, buffed=True)
    assert hasted.attacks == pytest.approx(a.player("mage", 60).attacks + 1)  # haste's extra attack
    assert hasted.ac < a.player("mage", 60).ac  # armour, shield and stone skin (no frenzy for mages)


def test_spells_and_sanctuary_shorten_and_soften_fights(a):
    from xania_explorer.assess import skills as S

    sk = S.analyse(a.world)
    lvl = 60
    p = a.player("mage", lvl, buffed=True)
    mana = a.chars.build("human", "mage").at(lvl).mana
    m, f = a.results[("mage", lvl)].fights[0]
    g = a.fight_with_spells(p, m, sk.spells["mage"][lvl], mana)
    assert g.rounds < f.rounds
    assert g.mob_dpr == pytest.approx(a.fight(p, m).mob_dpr / 1.6 * (0.75 if m.mob.alignment <= -350 else 1))


def test_dispel_evil_does_nothing_to_neutral_mobs(a):
    from types import SimpleNamespace

    from xania_explorer.source.spell_tables import load_damage_spells

    spell = load_damage_spells(a.world.src_dir)["spell_dispel_evil"]
    p = a.player("cleric", 30, buffed=True)
    neutral = next(m for m, _ in a.results[("cleric", 30)].fights if -350 < m.mob.alignment < 350)
    choice = SimpleNamespace(spell=spell, mana=10, damage=spell.expected(30, 0.5),
                             ability=SimpleNamespace(skill=SimpleNamespace(beats=12)))
    assert a.fight_with_spells(p, neutral, choice, 1000).rounds == pytest.approx(a.fight(p, neutral).rounds)
