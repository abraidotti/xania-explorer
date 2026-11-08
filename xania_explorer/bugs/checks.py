"""The bug checks. Code checks are narrow regexes over the C++ source; each was verified by reading the code."""

from __future__ import annotations

import re
from pathlib import Path

from ..areafile.parser import parse_file
from ..areafile.reader import AreaParseError
from ..areafile.world import World
from . import BugCheck, Detection, Occurrence


# -- helpers ---------------------------------------------------------------------------------------
def _source(world: World, rel: str) -> str | None:
    path = world.src_dir / rel
    return path.read_text(encoding="latin-1") if path.exists() else None


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _code(world: World, rel: str, pattern: str, detail: str, flags=re.S) -> list[Occurrence] | None:
    """Occurrences of ``pattern`` in src/``rel``; None when the file is missing."""
    text = _source(world, rel)
    if text is None:
        return None
    return [Occurrence(f"{rel}:{_line_of(text, m.start())}", detail, file=f"src/{rel}", line=_line_of(text, m.start()))
            for m in re.finditer(pattern, text, flags)]


def _code_status(found: list[Occurrence] | None, triggers: list[Occurrence] | None = None) -> Detection:
    if found is None:
        return Detection("unknown", note="the source file isn't in this checkout")
    if not found:
        return Detection("fixed")
    if triggers is None:
        return Detection("present", found)
    if triggers:
        return Detection("present", found + triggers)
    return Detection("latent", found, note="no area data triggers it today")


def _problems(world: World, *kinds: str) -> list[Occurrence]:
    out = []
    for p in world.problems:
        if p.kind in kinds:
            area = next((a.name for a in world.areas if a.filename == p.file), "")
            out.append(Occurrence(f"{p.file}:{p.line}" if p.line else p.file, p.message, area, f"area/{p.file}", p.line))
    return out


# -- code ------------------------------------------------------------------------------------------
def _affect_worth(world: World) -> Detection:
    return _code_status(_code(world, "AFFECT_DATA.cpp", r"if\s*\(\s*modifier\s*<\s*0\s*\)\s*if\s*\(\s*modifier\s*>\s*0\s*\)",
                              "`if (modifier < 0) if (modifier > 0)` can never be true"))


def _lose_level(world: World) -> Detection:
    text = _source(world, "update.cpp")
    if text is None:
        return Detection("unknown", note="update.cpp isn't in this checkout")

    def body(name: str) -> tuple[str, int]:
        m = re.search(rf"void {name}\(Char \*ch\) \{{(.*?)\n\}}", text, re.S)
        return (m.group(1), _line_of(text, m.start())) if m else ("", 0)

    adv, adv_line = body("advance_level")
    lose, lose_line = body("lose_level")
    if not adv or not lose:
        return Detection("unknown", note="advance_level/lose_level not found")

    def mana(b: str) -> str:
        m = re.search(r"add_mana\s*=(.*?);", b, re.S)
        return re.sub(r"\s+", "", m.group(1)) if m else ""

    differs = mana(adv) != mana(lose) or ("curr_stat" in adv and "max_stat" in lose)
    if not differs:
        return Detection("fixed")
    return Detection("present", [
        Occurrence(f"update.cpp:{adv_line}", "advance_level adds HP/mana from curr_stat with the squared mana factor",
                   file="src/update.cpp", line=adv_line),
        Occurrence(f"update.cpp:{lose_line}", "lose_level removes them using max_stat and a different mana formula",
                   file="src/update.cpp", line=lose_line)])


def _exit_null(world: World) -> Detection:
    found = _code(world, "db.cpp", r"exit_rev\s*&&\s*exit_rev->u1\.to_room->vnum",
                  "dereferences the reverse exit's destination without checking it for null")
    return _code_status(found, _problems(world, "reverse-exit-null"))


def _shop_null(world: World) -> Detection:
    found = _code(world, "db.cpp", r"mobIndex\s*=\s*get_mob_index\(shop\.keeper,\s*logger\);\s*mobIndex->shop",
                  "uses the shopkeeper's prototype without checking get_mob_index found one")
    triggers = [o for o in _problems(world, "dangling-ref") if "shop keeper" in o.detail]
    return _code_status(found, triggers)


def _dot_stdout(world: World) -> Detection:
    occ: list[Occurrence] = []
    missing = True
    for rel in ("apps/areas.cpp", "apps/map.cpp"):
        text = _source(world, rel)
        if text is None:
            continue
        missing = False
        if "out_file" not in text:
            continue
        for m in re.finditer(r'fmt::print\("(?!Error|\{\}")', text):
            line = _line_of(text, m.start())
            occ.append(Occurrence(f"{rel}:{line}", "DOT output printed to stdout, not to out_file",
                                  file=f"src/{rel}", line=line))
    if missing:
        return Detection("unknown", note="apps/ isn't in this checkout")
    return Detection("present", occ) if occ else Detection("fixed")


def _mudschool_comment(world: World) -> Detection:
    text = _source(world, "Area.cpp")
    if text is None:
        return Detection("unknown", note="Area.cpp isn't in this checkout")
    claim = re.search(r"Every minute if unoccupied", text)
    code = re.search(r"age_\s*=\s*RoomResetAgeUnoccupiedArea", text)
    if claim and code:
        return Detection("present", [
            Occurrence(f"Area.cpp:{_line_of(text, claim.start())}", "comment: Mud School resets every 1–2 minutes",
                       file="src/Area.cpp", line=_line_of(text, claim.start())),
            Occurrence(f"Area.cpp:{_line_of(text, code.start())}",
                       "code: age set to 10 against a threshold of 15, i.e. every ~5 area pulses (2.5–7.5 min)",
                       file="src/Area.cpp", line=_line_of(text, code.start()))])
    return Detection("fixed")


# -- data -----------------------------------------------------------------------------------------
def _fatal_load(world: World) -> Detection:
    occ = []
    for p in world.problems:
        if p.fatal_in_cpp:
            area = next((a.name for a in world.areas if a.filename == p.file), "")
            occ.append(Occurrence(f"{p.file}:{p.line}" if p.line else p.file, f"[{p.kind}] {p.message}", area,
                                  f"area/{p.file}", p.line))
    return Detection("present", occ) if occ else Detection("clean")


def _load_warnings(world: World) -> Detection:
    occ = [Occurrence(f"{d.file}:{d.line}", d.message, file=f"area/{d.file}", line=d.line) for d in world.diagnostics]
    for p in world.problems:
        if not p.fatal_in_cpp:
            area = next((a.name for a in world.areas if a.filename == p.file), "")
            occ.append(Occurrence(f"{p.file}:{p.line}" if p.line else p.file, f"[{p.kind}] {p.message}", area,
                                  f"area/{p.file}", p.line))
    return Detection("present", occ) if occ else Detection("clean")


def _unlisted_broken(world: World) -> Detection:
    occ = []
    for name in world.unlisted_files:
        try:
            parse_file(Path(world.area_dir) / name)
        except AreaParseError as e:
            occ.append(Occurrence(f"{name}:{e.line}", e.message, file=f"area/{name}", line=e.line))
    return Detection("present", occ) if occ else Detection("clean")


# -- content --------------------------------------------------------------------------------------
def _unobtainable(world: World) -> Detection:
    from ..assess import equipment as E
    from ..assess import weapons as W

    occ = [Occurrence(f"#{w.vnum} {w.obj.short_descr}", f"weapon, level {w.obj.level}", world.obj_area[w.vnum].name)
           for w in W.analyse(world).lost]
    occ += [Occurrence(f"#{i.vnum} {i.obj.short_descr}", f"gear ({', '.join(i.slots)}), level {i.obj.level}",
                       world.obj_area[i.vnum].name) for i in E.analyse(world).lost]
    return Detection("present", occ) if occ else Detection("clean")


def _never_spawn(world: World) -> Detection:
    from ..assess import mobs as M

    occ = [Occurrence(f"#{i.mob.vnum} {i.mob.short_descr}",
                      f"level {i.mob.level}; " + ("every M reset has a world cap ≤ 0" if i.spawns else "no M reset"),
                      i.area.name) for i in M.analyse(world).never]
    return Detection("present", occ) if occ else Detection("clean")


def _unreachable(world: World) -> Detection:
    from ..assess import levelling as L

    a = L.analyse(world)
    occ = [Occurrence(f"room #{v} {world.rooms[v].name}", "no walking route from recall", world.room_area[v].name)
           for v in a.unreachable_rooms]
    return Detection("present", occ) if occ else Detection("clean")


def _unlisted(world: World) -> Detection:
    occ = [Occurrence(name, "on disk but not in area.lst, so never loaded", file=f"area/{name}")
           for name in world.unlisted_files]
    return Detection("present", occ) if occ else Detection("clean")


CHECKS: list[BugCheck] = [
    BugCheck(
        "code.affect-worth-ac", "Armour-class and saving-throw bonuses are free under the item-points rule", "code",
        "wrong-behaviour",
        "`AFFECT_DATA::worth` prices each affect for the item-points balance rule (`immworth`). Its case for "
        "`Ac` and the `Saving*` locations reads `if (modifier < 0) if (modifier > 0)`, which can never be true, so "
        "these bonuses cost nothing. Builders' items can carry any amount of AC and saves without the check "
        "noticing (see Equipment).",
        "Charge one point per −1, as the code intends:\n\n```cpp\n    case AffectLocation::Ac:\n"
        "        if (modifier < 0)\n            return Value{0, 0, -modifier};\n        break;\n```\n\nThen re-run "
        "`immworth` on existing items: Equipment lists the ones that would newly exceed the limit.",
        _affect_worth),
    BugCheck(
        "code.lose-level-asymmetry", "Losing a level doesn't undo what gaining it gave", "code", "wrong-behaviour",
        "From level 26, dying can cost a level (fight.cpp, `lose_level`). `advance_level` adds HP and mana from "
        "the character's *current* stats with a squared mana factor; `lose_level` removes them using *maximum* "
        "stats and an older mana formula. A death followed by re-levelling therefore changes a character's max HP "
        "and mana: for mages, mana grows a little with each cycle.",
        "Make the two mirror each other. Simplest: have `lose_level` remove the average of what `advance_level` "
        "would give at the same stats (share one helper for both), or record each level's actual gains in the "
        "player file and remove exactly those.",
        _lose_level),
    BugCheck(
        "code.reverse-exit-null", "Booting crashes if a two-way exit's return exit leads nowhere", "code", "crash",
        "`map_exit_destinations` checks that each two-way exit's reverse exit leads back. The test "
        "`exit_rev && exit_rev->u1.to_room->vnum != room.vnum` dereferences `to_room` without checking it; the "
        "logging two lines later does check it, so the case was anticipated. An area whose return exit is "
        "cosmetic (−1) or dangling would crash the MUD at boot.",
        "Check the destination first:\n\n```cpp\nif (auto &exit_rev = to_room->exits[reverse(direction)];\n"
        "    exit_rev && exit_rev->u1.to_room && exit_rev->u1.to_room->vnum != room.vnum && !exit->is_one_way) {\n```",
        _exit_null),
    BugCheck(
        "code.shop-keeper-null", "Booting crashes if a shop names a missing shopkeeper", "code", "crash",
        "`load_shops` looks up the shopkeeper's prototype and immediately writes to it. If the vnum doesn't exist, "
        "`get_mob_index` returns null and the MUD crashes during boot instead of reporting the bad shop.",
        "Report and skip the shop:\n\n```cpp\nmobIndex = get_mob_index(shop.keeper, logger);\nif (!mobIndex) {\n"
        "    logger.bug(\"Load_shops: shopkeeper #{} not found.\", shop.keeper);\n    continue;\n}\n"
        "mobIndex->shop = std::move(shop);\n```",
        _shop_null),
    BugCheck(
        "code.dot-tools-stdout", "The area and map tools write part of their output to the screen", "code", "cosmetic",
        "The `areas` and `map` utilities (src/apps) take an output file, but some of their DOT output is printed "
        "with `fmt::print(\"…\")`, which goes to stdout. Writing to a file produces a broken graph.",
        "Pass the file handle to every DOT line, e.g. `fmt::print(out_file, \"}}\\n\");`, and give `render_area` the "
        "`out_file` it already receives for its room and exit lines.",
        _dot_stdout),
    BugCheck(
        "code.mudschool-reset-comment", "The Mud School reset comment contradicts the code", "code", "cosmetic",
        "Area.cpp's comment says Mud School resets every 2 minutes when occupied and every minute when empty. The "
        "code sets its age to 10 after each reset against a threshold of 15 (it is never flagged empty), so it "
        "resets every ~5 area pulses, about 2.5–7.5 minutes.",
        "Decide which is intended. To match the comment, set `age_` to `RoomResetAgeOccupiedArea - 2` (and "
        "`- 1` when empty); otherwise correct the comment.",
        _mudschool_comment),
    BugCheck(
        "data.fatal-load", "Area data the MUD would refuse to boot with", "data", "crash",
        "Problems the C++ loader treats as fatal (`exit(1)`), found by the area parser: duplicate vnums, bad door "
        "resets, missing files, unparseable sections, invalid drop rates (which crash at reset time, not boot).",
        "Fix each listed file and line; `python -m xania_explorer check` re-tests them.",
        _fatal_load),
    BugCheck(
        "data.load-warnings", "Area data the MUD loads with a warning or silently mishandles", "data",
        "wrong-behaviour",
        "Problems the loader only logs (unknown attack types, body sizes or positions defaulted) and references "
        "it gets wrong without noticing (dangling exits and resets, asymmetric exits, resets outside the area's "
        "vnum range).",
        "Fix each listed file and line, or accept the default the loader applies.",
        _load_warnings),
    BugCheck(
        "data.unlisted-broken", "Unlisted area files that wouldn't load", "data", "cosmetic",
        "Area files that aren't in `area.lst` and would also fail to parse. They don't affect the running game, but "
        "anyone adding them to `area.lst` would stop the MUD booting.",
        "Fix the listed error before listing the file, or delete the file.",
        _unlisted_broken),
    BugCheck(
        "content.unobtainable-items", "Items that no reset places", "content", "wrong-behaviour",
        "Weapons and wearable gear (level ≤ 91) that no reset puts anywhere, so players never see them unless a mob "
        "program, special or immortal creates them.",
        "Give each a reset (a mob to carry it or a room to hold it) or remove it from the area file.",
        _unobtainable),
    BugCheck(
        "content.mobs-never-spawn", "Mobs that never spawn", "content", "wrong-behaviour",
        "Mob prototypes with no `M` reset, or whose resets all have a world cap of 0 or less.",
        "Add an `M` reset with a positive cap, check whether a mob program loads it (`mpmload`), or remove it.",
        _never_spawn),
    BugCheck(
        "content.unreachable-rooms", "Rooms no one can walk to", "content", "cosmetic",
        "Rooms with no walking route from the Midgaard temple. Some are deliberate (immortal rooms, portal "
        "destinations, one-way traps); others are broken exits.",
        "For each room, confirm how players are meant to arrive; add the missing exit if it's a mistake.",
        _unreachable),
    BugCheck(
        "content.unlisted-areas", "Area files that are never loaded", "content", "cosmetic",
        "`.are` files on disk that `area.lst` doesn't list, so their content isn't in the game.",
        "Add them to `area.lst` (after fixing any load errors above) or delete them.",
        _unlisted),
]
