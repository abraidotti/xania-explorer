"""Parse one ``.are`` file, section by section, as ``boot_db`` does.

Fatal conditions raise :class:`AreaParseError`; conditions the C++ only logs
are recorded as diagnostics on the reader. Validation that needs the whole
world (do vnums exist? are doors real?) happens in :mod:`world`.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import flags as F
from .model import (
    AreaFile, AreaHeader, Dice, Exit, ExtraDescription, Help, Mob, MobProgRef, Obj, ObjAffect,
    Reset, Room, Shop, Social, Special,
)
from .reader import AreaParseError, Diagnostic, Reader

_LEVEL_BAND = re.compile(r"^\{\s*([+-]?\d+)\s+([+-]?\d+)")


def parse_file(path: Path) -> tuple[AreaFile, list[Diagnostic]]:
    reader = Reader.from_path(path)
    return parse(reader), reader.diagnostics


def parse_text(text: str, filename: str = "<string>") -> tuple[AreaFile, list[Diagnostic]]:
    reader = Reader(text, filename)
    return parse(reader), reader.diagnostics


def parse(r: Reader) -> AreaFile:
    """Section loop from ``boot_db`` (db.cpp:241-273)."""
    af = AreaFile(r.filename)
    while True:
        if r.read_letter() != "#":
            raise r.error("Boot_db: # not found.")
        word = r.read_word()
        if word.startswith("$"):
            return af
        section = word.upper()
        af.sections.append(section)
        handler = _SECTIONS.get(section)
        if handler is None:
            raise r.error(f"Boot_db: bad section name {word!r}.")
        if section not in ("AREA", "HELPS", "SOCIALS") and af.header is None:
            # The C++ attaches to areas.back(), i.e. the *previous file's* area,
            # and only exits if no area has been loaded at all.
            r.bug(f"#{section} before any #AREA in this file")
        handler(r, af)


# -- #AREA ------------------------------------------------------------------
def _area(r: Reader, af: AreaFile) -> None:
    """``Area::parse`` (Area.cpp:14)."""
    filename_field = r.read_string()
    short_name = r.read_string()
    description = r.read_string()
    m = _LEVEL_BAND.match(description)
    lo = hi = None
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
    af.header = AreaHeader(filename_field, short_name, description, lo, hi, r.read_number(), r.read_number())


# -- #HELPS -----------------------------------------------------------------
def _helps(r: Reader, af: AreaFile) -> None:
    """``Help::load`` (Help.cpp:13): ``level keywords~ text~`` until keyword ``$``."""
    while True:
        line = r.line
        level = r.read_number()
        keywords = r.read_string()
        if keywords.startswith("$"):
            return
        text = r.read_string()
        if text.startswith("."):
            text = text[1:]
        af.helps.append(Help(level, keywords, text, line))


# -- #SOCIALS ---------------------------------------------------------------
def _socials(r: Reader, af: AreaFile) -> None:
    """``Social::load`` (Socials.cpp): name word, 8 phrases per line, then ``#``."""
    while True:
        name = r.read_word().lower()
        if name == "#0":
            return
        phrases = []
        for _ in range(8):
            p = r.read_string_eol()
            phrases.append("" if p == "$" else p)
        terminator = r.read_string_eol()
        if terminator != "#":
            r.bug(f"loading socials: expected social terminator (#) but instead got {terminator!r}")
            return  # the C++ stops loading socials here
        af.socials.append(Social(name, phrases))


# -- #MOBILES ---------------------------------------------------------------
def _lookup_or_bug(r: Reader, word: str, names, what: str, default: str) -> str:
    """Resolve an enum word by prefix as the C++ does; log and default if unknown."""
    found = F.prefix_lookup(word, names)
    if found is None:
        r.bug(f"Unrecognized {what}: {word!r}, defaulting to {default}")
        return default
    return found


def _dice(r: Reader) -> Dice:
    """``Dice::from_file`` (Dice.cpp:6): ``NdS+B``; malformed parts are logged only."""
    number = r.read_number()
    d = r.read_letter()
    sides = r.read_number()
    plus = r.read_letter()
    bonus = r.read_number()
    if number <= 0:
        r.bug("Bad dice: number <= 0")
    if sides <= 0:
        r.bug("Bad dice: type <= 0")
    if d not in ("d", "D"):
        r.bug(f"Bad dice: expected 'd' or 'D', got {d!r}")
    if plus != "+":
        r.bug(f"Bad dice: expected '+', got {plus!r}")
    return Dice(number, sides, bonus)


def _mobiles(r: Reader, af: AreaFile) -> None:
    """``MobIndexData`` constructor (MobIndexData.cpp:28)."""
    while True:
        if r.read_letter() != "#":
            raise r.error("Load_mobiles: # not found.")
        line = r.line
        vnum = r.read_number()
        if vnum == 0:
            return
        keywords = r.read_string()
        short_descr = r.read_string()
        long_descr = r.read_string()
        description = r.read_string()
        race = r.read_string()
        act = r.read_flag()
        affected_by = r.read_flag()
        alignment = r.read_number()
        group = r.read_number()
        level = r.read_number()
        hitroll = r.read_number()
        hit, mana, damage = _dice(r), _dice(r), _dice(r)
        attack_word = r.read_word()
        attack = F.prefix_lookup(attack_word, F.ATTACKS)
        if attack is None:
            r.bug(f"Invalid attack type {attack_word} in mob #{vnum}, defaulting to hit")
            attack = "hit"
        ac = (r.read_number(), r.read_number(), r.read_number(), r.read_number())
        off, imm, res, vuln = r.read_flag(), r.read_flag(), r.read_flag(), r.read_flag()
        start_pos = _lookup_or_bug(r, r.read_word(), F.POSITIONS, "position", "Standing")
        default_pos = _lookup_or_bug(r, r.read_word(), F.POSITIONS, "position", "Standing")
        sex_word = r.read_word()
        sex = F.prefix_lookup(sex_word, F.SEXES)
        if sex is None:
            raise r.error(f"Unrecognized sex {sex_word!r}.")
        gold = r.read_number()
        morphology = r.read_flag()
        parts = r.read_flag()
        body_size = _lookup_or_bug(r, r.read_word(), F.BODY_SIZES, "body size", "medium")
        material = r.read_word()
        af.mobs.append(Mob(
            vnum, keywords, short_descr, long_descr, description, race, act, affected_by, alignment,
            group, level, hitroll, hit, mana, damage, attack, ac, off, imm, res, vuln, start_pos,
            default_pos, sex, gold, morphology, parts, body_size, material, line,
        ))


# -- #OBJECTS ---------------------------------------------------------------
def _objects(r: Reader, af: AreaFile) -> None:
    """``load_objects`` (db.cpp:574-776)."""
    while True:
        if r.read_letter() != "#":
            raise r.error("Load_objects: # not found.")
        line = r.line
        vnum = r.read_number()
        if vnum == 0:
            return
        keywords = r.read_string()
        short_descr = r.read_string()
        description = r.read_string()
        if not description:
            r.bug(f"Load_objects: empty long description in object {vnum}.")
        material = r.read_string()
        type_word = r.read_word()
        otype = F.lookup_object_type(type_word)
        if otype is None:
            r.bug(f"Unknown item type '{type_word}' - defaulting!")
            otype = F.OBJECT_TYPES["Light"]
        tname = F.OBJECT_TYPE_BY_NUM[otype]
        extra = r.read_flag()
        if extra & (1 << 12) and tname != "Weapon":  # ObjectExtraFlag::NoRemove = M
            raise r.error(f"Only weapons are meant to have ObjectExtraFlag::NoRemove: {vnum} {keywords}")
        wear = r.read_flag()
        wear_string = None
        if r.read_letter() == ",":
            wear_string = r.read_string()
        else:
            r.ungetc()

        values: list[int | str]
        if tname == "Weapon":
            wtype = _lookup_or_bug(r, r.read_word(), F.WEAPON_TYPES, "weapon type", "exotic")
            n, s = r.read_number(), r.read_number()
            attack = _lookup_or_bug(r, r.read_word(), F.ATTACKS, "attack type", "hit")
            values = [wtype, n, s, attack, r.read_flag()]
        elif tname == "Container":
            values = [r.read_number(), r.read_flag(), r.read_number(), r.read_number(), r.read_number()]
        elif tname in ("Drink", "Fountain"):
            values = [r.read_number(), r.read_number(), r.read_word(), r.read_number(), r.read_number()]
        elif tname in ("Wand", "Staff"):
            values = [r.read_number(), r.read_number(), r.read_number(), r.read_spnumber(), r.read_number()]
        elif tname in ("Potion", "Pill", "Scroll", "Bomb"):
            values = [r.read_number(), r.read_spnumber(), r.read_spnumber(), r.read_spnumber(),
                      r.read_spnumber()]
        else:
            values = [r.read_flag() for _ in range(5)]

        level, weight, cost = r.read_number(), r.read_number(), r.read_number()
        condition = r.read_letter()
        obj = Obj(vnum, keywords, short_descr, description, material, type_word, otype, extra, wear,
                  wear_string, values, level, weight, cost, condition, line=line)
        while True:
            letter = r.read_letter()
            if letter == "A":
                obj.affects.append(ObjAffect(r.read_number(), r.read_number()))
            elif letter == "E":
                obj.extra_descr.append(ExtraDescription(r.read_string(), r.read_string()))
            else:
                r.ungetc()
                break
        af.objects.append(obj)


# -- #ROOMS -----------------------------------------------------------------
def _rooms(r: Reader, af: AreaFile) -> None:
    """``load_rooms`` (db.cpp:395)."""
    while True:
        if r.read_letter() != "#":
            raise r.error("load_rooms: # not found.")
        line = r.line
        vnum = r.read_number()
        if vnum == 0:
            return
        room = Room(vnum, r.read_string(), r.read_string(), r.read_flag(), r.read_number(), line=line)
        if not 0 <= room.sector < len(F.SECTORS):
            r.bug(f"Invalid sector type {room.sector}, defaulted to Inside")
        while True:
            letter = r.read_letter()
            if letter == "S":
                break
            if letter == "D":
                d = r.read_number()
                if not 0 <= d < 6:
                    raise r.error(f"load_rooms: vnum {vnum} has bad door number.")
                desc, kw = r.read_string(), r.read_string()
                locks, key, to = r.read_number(), r.read_number(), r.read_number()
                one_way = to < -1
                room.exits[d] = Exit(d, desc, kw, locks, key, -to if one_way else to, one_way, to == -1)
            elif letter == "E":
                room.extra_descr.append(ExtraDescription(r.read_string(), r.read_string()))
            else:
                raise r.error(f"load_rooms: vnum {vnum} has unrecognized instruction {letter!r}.")
        af.rooms.append(room)


# -- #RESETS ----------------------------------------------------------------
def _resets(r: Reader, af: AreaFile) -> None:
    """``load_resets`` (db.cpp:301). Also records which room the C++ attaches
    each reset to (``room_vnum``), using its last-room/last-object tracking."""
    last_room = 0
    last_obj = 0
    while True:
        letter = r.read_letter()
        if letter == "S":
            return
        if letter == "*":
            r.read_to_eol()
            continue
        if letter not in "MOPGEDR" or not letter:
            raise r.error(f"Load_resets: bad command {letter!r}.")
        line = r.line
        if_flag = r.read_number()
        arg1 = r.read_number()
        arg2 = r.read_number()
        arg3 = 0 if letter in "GR" else r.read_number()
        arg4 = r.read_number() if letter in "PM" else 0
        comment = r.read_to_eol()
        reset = Reset(letter, if_flag, arg1, arg2, arg3, arg4, comment, line)
        if letter == "M":
            reset.room_vnum = last_room = arg3
        elif letter == "O":
            reset.room_vnum = last_obj = arg3
        elif letter == "P":
            reset.room_vnum = last_obj
        elif letter in "GE":
            reset.room_vnum = last_room
            last_obj = last_room
        elif letter == "D":
            reset.room_vnum = arg1
            if arg3 not in (0, 1, 2):
                r.bug(f"Load_resets: 'D': bad 'locks': {arg3}.")
        elif letter == "R":
            if not 0 <= arg2 <= 6:
                raise r.error(f"Load_resets: 'R': bad exit {arg2}.")
            reset.room_vnum = arg1
        af.resets.append(reset)


# -- #SHOPS -----------------------------------------------------------------
def _shops(r: Reader, af: AreaFile) -> None:
    """``load_shops`` (db.cpp:491)."""
    while True:
        line = r.line
        keeper = r.read_number()
        if keeper == 0:
            return
        buy = [r.read_number() for _ in range(5)]
        shop = Shop(keeper, buy, r.read_number(), r.read_number(), r.read_number(), r.read_number(), line)
        r.read_to_eol()
        af.shops.append(shop)


# -- #SPECIALS --------------------------------------------------------------
def _specials(r: Reader, af: AreaFile) -> None:
    """``load_specials`` (db.cpp:520)."""
    while True:
        letter = r.read_letter()
        if letter == "S":
            return
        if letter == "M":
            line = r.line
            af.specials.append(Special(r.read_number(), r.read_word(), line))
        elif letter != "*":
            raise r.error(f"Load_specials: letter {letter!r} not *, M or S.")
        r.read_to_eol()


# -- #MOBPROGS --------------------------------------------------------------
def _mobprogs(r: Reader, af: AreaFile) -> None:
    """``MProg::load_mobprogs`` (MProgLoader.cpp:104)."""
    while True:
        letter = r.read_letter()
        if letter in ("S", "s"):
            r.read_to_eol()
            return
        if letter == "*":
            r.read_to_eol()
        elif letter in ("M", "m"):
            line = r.line
            af.mobprogs.append(MobProgRef(r.read_number(), r.read_word(), line))
            r.read_to_eol()
        else:
            raise r.error(f"load_mobprogs: bad command {letter!r}.")


_SECTIONS = {
    "AREA": _area, "HELPS": _helps, "SOCIALS": _socials, "MOBILES": _mobiles,
    "OBJECTS": _objects, "ROOMS": _rooms, "RESETS": _resets, "SHOPS": _shops,
    "SPECIALS": _specials, "MOBPROGS": _mobprogs,
}

__all__ = ["parse", "parse_file", "parse_text", "AreaParseError"]
