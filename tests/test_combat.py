import pytest

from xania_explorer.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_explorer.areafile import flags as F
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


def test_tolerance_follows_check_damage_tolerance():
    """DamageTolerance.cpp: for bash/pierce/slash the catch-all Weapon flag comes first; types without a flag of
    their own count as Magic; immune beats resistant beats vulnerable. damage(): x0, -1/3, +1/2."""
    from xania_explorer.assess.combat import tolerance

    f = frozenset
    assert tolerance(f({"Weapon"}), f(), f({"Slash"}), "Slash") == 0
    assert tolerance(f(), f({"Weapon"}), f({"Slash"}), "Slash") == 2 / 3
    assert tolerance(f(), f(), f({"Slash"}), "Slash") == 1.5
    assert tolerance(f({"Weapon"}), f(), f(), "Fire") == 1.0  # Weapon only covers the physical types
    assert tolerance(f(), f({"Magic"}), f(), "Other") == 2 / 3 and tolerance(f(), f({"Magic"}), f(), "Harm") == 2 / 3
    assert tolerance(f({"Fire"}), f({"Fire"}), f({"Fire"}), "Fire") == 0
    assert tolerance(f(), f(), f(), "None") == 1.0


def test_tolerances_on_the_checkout():
    """Mobs get their race's flags too (MobIndexData.cpp): every troll resists bash and is vulnerable to fire and
    acid. Spells carry their damage() call's type (harm deals fire damage in Xania)."""
    from pathlib import Path

    from xania_explorer import api
    from xania_explorer.source.character_tables import load_race_tolerances
    from xania_explorer.source.spell_tables import load_damage_spells

    w = api.load_world()
    imm, res, vuln = load_race_tolerances(w.src_dir)["troll"]
    assert {"Bash"} <= res and {"Acid", "Fire"} <= vuln
    spells = load_damage_spells(w.src_dir)
    assert (spells["spell_fireball"].damage_type, spells["spell_magic_missile"].damage_type) == ("Fire", "Energy")
    troll = CB.analyse(w)
    giant = next(m for m in troll.mobs if m.mob.vnum == 2804)
    assert (giant.takes("Bash"), giant.takes("Slash"), giant.takes("Fire")) == (2 / 3, 1.0, 1.5)
    p = api.predict_spell(w, "mage", "burning hands", 20, 13, mob_vnum=2804)
    assert p.damage_type == "Fire" and p.tolerance == 1.5
    # a mob a player's weapon can't hurt isn't averaged in as an endless fight
    for r in troll.results.values():
        assert all(m.takes(troll.player(r.cls, r.level).damage_type) == 0 for m in r.unhurtable)
    assert any(r.unhurtable for r in troll.results.values())  # weapon-immune mobs exist (The Blob, The Fire...)


def test_unseen_mobs_need_the_detect_spells():
    """Char::can_see(const Char &): a passive hidden mob (the tiny water sprite, #13215) can't be found without
    detect hidden, so it's no fight for a knight; a mage learns detect hidden at 15 and sees it. Aggressive hidden
    or invisible mobs attack whoever they can, so they always count."""
    from xania_explorer import api

    cb = CB.analyse(api.load_world())
    sprite = next(m for m in cb.mobs if m.mob.vnum == 13215)
    assert not cb.can_see("knight", 23, sprite) and cb.can_see("mage", 23, sprite)
    assert sprite in cb.results[("knight", 23)].unseen
    assert sprite in [m for m, _ in cb.results[("mage", 23)].fights]
    sneaky = [m for m in cb.mobs if "Aggressive" in m.mob.act_names
              and {"Hide", "Invisible"} & set(F.decode(m.mob.affected_by, F.AFFECT))]
    assert sneaky and all(cb.can_see("knight", 10, m) for m in sneaky)
