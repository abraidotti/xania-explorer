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
}
FIXED = {
    "AFFECT_DATA.cpp": "case AffectLocation::Ac:\n        if (modifier < 0)\n            return Value{0, 0, -modifier};\n",
    "db.cpp": "exit_rev && exit_rev->u1.to_room && exit_rev->u1.to_room->vnum != room.vnum\n"
              "mobIndex = get_mob_index(shop.keeper, logger);\nif (!mobIndex) continue;\nmobIndex->shop = shop;\n",
    "update.cpp": "void advance_level(Char *ch) {\n    add_mana = gains(ch);\n}\n"
                  "void lose_level(Char *ch) {\n    add_mana = gains(ch);\n}\n",
    "Area.cpp": " * - Every 5 minutes.\n        age_ = RoomResetAgeUnoccupiedArea;\n",
    "apps/map.cpp": "FILE *out_file;\nfmt::print(out_file, \"    v{} [label]\");\n",
}
CODE_CHECKS = [K._affect_worth, K._lose_level, K._exit_null, K._shop_null, K._mudschool_comment, K._dot_stdout]


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
                        "_shop_null": "latent", "_mudschool_comment": "present", "_dot_stdout": "present"}


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
