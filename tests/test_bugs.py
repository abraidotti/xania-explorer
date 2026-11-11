"""Bug checks report 'present' on buggy source and 'fixed' on patched source."""

import pytest

from xania_explorer.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_explorer.bugs import checks as K

AREA = "#AREA\nMini.are~\nMini~\n{ 1 10} Test Mini~\n3000 3010\n\n#ROOMS\n#3001\nTemple~\nT.\n~\n0 0\nS\n#0\n\n#$\n"

BUGGY = {
    "AFFECT_DATA.cpp": "case AffectLocation::Ac:\n        if (modifier < 0)\n            if (modifier > 0)\n"
                       "                return Value{0, 0, -modifier};\n        break;\n",
    "db.cpp": "if (auto &exit_rev = to_room->exits[reverse(direction)];\n    exit_rev && exit_rev->u1.to_room->vnum "
              "!= room.vnum) {}\n        mobIndex = get_mob_index(shop.keeper, logger);\n"
              "        mobIndex->shop = std::move(shop);\n",
    "update.cpp": "void advance_level(Char *ch) {\n    add_mana = factor * factor * ch->curr_stat(Stat::Int);\n}\n"
                  "void lose_level(Char *ch) {\n    add_mana = number_range(2, ch->max_stat(Stat::Int));\n}\n",
    "Area.cpp": " * - Every minute if unoccupied by players.\n        age_ = RoomResetAgeUnoccupiedArea;\n",
    "apps/map.cpp": "FILE *out_file;\nfmt::print(\"    v{} [label]\");\nfmt::print(out_file, \"ok\");\n",
    "act_obj.cpp": "if ((arg1[3] == '\\0' || is_name(&arg1[4], obj->name)) && ch->can_see(*obj)) {}\n",
    "fight.cpp": "        ch->hit += (adjusted_damage / 100) * 10;\n"
                 "/* if (check_enum_bit(wield->value[4], WeaponFlag::Flaming)) wield->value[3] = 29; */\n",
    "entity_balance.cpp": "        if (check_enum_bit(obj->value[4], WeaponFlag::Flaming))\n            worth++;\n"
                          "        if (check_enum_bit(obj->value[4], WeaponFlag::Frost))\n            worth++;\n",
    "magic.cpp": "void spell_harm(int sn, int level, Char *ch, void *vo) {\n    damage(ch, victim, dam, sn, "
                 "DamageType::Fire);\n}\nvoid spell_cause_light(int sn) {\n    damage(ch, v, d, sn, DamageType::Harm);\n}\n",
}
FIXED = {
    "AFFECT_DATA.cpp": "case AffectLocation::Ac:\n        if (modifier < 0)\n            return Value{0, 0, -modifier};\n",
    "db.cpp": "exit_rev && exit_rev->u1.to_room && exit_rev->u1.to_room->vnum != room.vnum\n"
              "mobIndex = get_mob_index(shop.keeper, logger);\nif (!mobIndex) continue;\nmobIndex->shop = shop;\n",
    "update.cpp": "void advance_level(Char *ch) {\n    add_mana = gains(ch);\n}\n"
                  "void lose_level(Char *ch) {\n    add_mana = gains(ch);\n}\n",
    "Area.cpp": " * - Every 5 minutes.\n        age_ = RoomResetAgeUnoccupiedArea;\n",
    "apps/map.cpp": "FILE *out_file;\nfmt::print(out_file, \"    v{} [label]\");\n",
    "act_obj.cpp": "if ((is_all || is_name(named, obj->name)) && ch->can_see(*obj)) {}\n",
    "fight.cpp": "        ch->hit += adjusted_damage / 10;\n"
                 "if (check_enum_bit(wield->value[4], WeaponFlag::Flaming)) dam += dice(level / 4 + 1, 6);\n"
                 "if (check_enum_bit(wield->value[4], WeaponFlag::Frost)) dam += dice(level / 4 + 1, 6);\n",
    "entity_balance.cpp": "        if (check_enum_bit(obj->value[4], WeaponFlag::Flaming))\n            worth++;\n",
    "magic.cpp": "void spell_harm(int sn, int level, Char *ch, void *vo) {\n    damage(ch, victim, dam, sn, "
                 "DamageType::Harm);\n}\nvoid spell_fireball(int sn) {\n    damage(ch, v, d, sn, DamageType::Fire);\n}\n",
}
CODE_CHECKS = [K._affect_worth, K._lose_level, K._exit_null, K._shop_null, K._mudschool_comment, K._dot_stdout,
               K._get_all_past_end, K._vampiric_drain, K._elemental_flags, K._harm_fire]


def make(tmp_path, sources):
    (tmp_path / "area").mkdir()
    (tmp_path / "area" / "area.lst").write_text("Mini.are\n$\n")
    (tmp_path / "area" / "Mini.are").write_text(AREA)
    for rel, text in sources.items():
        p = tmp_path / "src" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return load_world(tmp_path)


def test_code_checks_detect_buggy_source(tmp_path):
    world = make(tmp_path, BUGGY)
    statuses = {f.__name__: f(world).status for f in CODE_CHECKS}
    assert statuses == {"_affect_worth": "present", "_lose_level": "present", "_exit_null": "latent",
                        "_shop_null": "latent", "_mudschool_comment": "present", "_dot_stdout": "present",
                        "_get_all_past_end": "present", "_vampiric_drain": "present", "_elemental_flags": "present",
                        "_harm_fire": "present"}


def test_code_checks_see_fixes(tmp_path):
    world = make(tmp_path, FIXED)
    assert all(f(world).status == "fixed" for f in CODE_CHECKS), {f.__name__: f(world).status for f in CODE_CHECKS}


def test_missing_source_is_unknown(tmp_path):
    world = make(tmp_path, {})
    assert K._affect_worth(world).status == "unknown"


@pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")
def test_real_checkout():
    from xania_explorer.bugs import run_checks

    results = {r.check.id: r for r in run_checks(load_world())}
    assert results["code.affect-worth-ac"].status == "present"
    assert results["data.fatal-load"].status == "clean"
    # objects the C++ creates (the Mud School kit) aren't "unobtainable"
    names = [o.where for o in results["content.unobtainable-items"].detection.occurrences]
    assert not any(n.startswith("#3700 ") for n in names)


@pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")
def test_vanish_on_save_follows_item_levels():
    """A drop more than 2 levels above its easiest carrier is flagged; bring it within 2 and it isn't."""
    world = load_world()
    found = K._vanish_on_save(world)
    assert found.status == "present"
    first = found.occurrences[0]
    vnum = int(first.where.split()[0][1:])
    assert "kept only from level" in first.detail
    carrier_level = int(first.detail.split("dropped by level-")[1].split()[0])
    world.objects[vnum].level = carrier_level + K.SAVE_LEVEL_MARGIN
    assert all(not o.where.startswith(f"#{vnum} ") for o in K._vanish_on_save(world).occurrences)
