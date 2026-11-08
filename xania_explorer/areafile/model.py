"""Plain data classes for the contents of an area file.

Values are what the *file* says. Where the C++ loader transforms data on load
(e.g. merging race flags into mobs, translating spell slots to skill numbers),
this model keeps the file value and the docs describe the transformation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import flags as F


@dataclass(frozen=True)
class Dice:
    number: int
    sides: int
    bonus: int

    @property
    def average(self) -> float:
        return self.number * (self.sides + 1) / 2 + self.bonus

    @property
    def minimum(self) -> int:
        return self.number + self.bonus

    @property
    def maximum(self) -> int:
        return self.number * self.sides + self.bonus

    def __str__(self) -> str:
        return f"{self.number}d{self.sides}+{self.bonus}"


@dataclass
class ExtraDescription:
    keywords: str
    description: str


@dataclass
class AreaHeader:
    filename_field: str  # first string; ignored by the C++
    short_name: str
    description: str  # e.g. "{ 5 35} Author  Name" -- level band parsed from here
    min_level: int | None
    max_level: int | None
    lowest_vnum: int
    highest_vnum: int

    @property
    def all_levels(self) -> bool:
        return self.min_level is None


@dataclass
class Mob:
    vnum: int
    keywords: str
    short_descr: str
    long_descr: str
    description: str
    race: str
    act: int
    affected_by: int
    alignment: int
    group: int
    level: int
    hitroll: int
    hit: Dice
    mana: Dice
    damage: Dice
    attack: str
    ac: tuple[int, int, int, int]  # pierce, bash, slash, exotic
    off_flags: int
    imm_flags: int
    res_flags: int
    vuln_flags: int
    start_pos: str
    default_pos: str
    sex: str
    gold: int
    morphology: int
    parts: int
    body_size: str
    material: str
    line: int = 0

    @property
    def act_names(self) -> list[str]:
        return F.decode(self.act, F.CHAR_ACT)

    @property
    def off_names(self) -> list[str]:
        return F.decode(self.off_flags, F.OFFENSIVE)


@dataclass
class ObjAffect:
    location: int
    modifier: int

    @property
    def location_name(self) -> str:
        return F.AFFECT_LOCATIONS[self.location] if 0 <= self.location < len(F.AFFECT_LOCATIONS) \
            else f"loc{self.location}"


@dataclass
class Obj:
    vnum: int
    keywords: str
    short_descr: str
    description: str
    material: str
    type_word: str
    type: int  # ObjectType number (after lookup; Light=1 if unknown, as the C++ does)
    extra_flags: int
    wear_flags: int
    wear_string: str | None
    # value[0..4] as read. Weapons: [weapon type word, dice number, dice sides, attack word, flags].
    # Potions/pills/scrolls/bombs/wands/staves may hold spell slot numbers *or* spell names.
    values: list[int | str]
    level: int
    weight: int
    cost: int
    condition_letter: str
    affects: list[ObjAffect] = field(default_factory=list)
    extra_descr: list[ExtraDescription] = field(default_factory=list)
    line: int = 0

    @property
    def type_name(self) -> str:
        return F.OBJECT_TYPE_BY_NUM.get(self.type, str(self.type))

    @property
    def condition(self) -> int:
        return F.CONDITIONS.get(self.condition_letter, 100)

    @property
    def weapon_dice(self) -> Dice | None:
        if self.type_name != "Weapon":
            return None
        return Dice(int(self.values[1]), int(self.values[2]), 0)


@dataclass
class Exit:
    direction: int
    description: str
    keyword: str
    locks: int  # 0 none, 1 door, 2 door+pickproof, 3 door+passproof, 4 door+both
    key: int
    to_vnum: int  # absolute value; see one_way / cosmetic
    one_way: bool
    cosmetic: bool  # file value -1: an exit that leads nowhere

    @property
    def direction_name(self) -> str:
        return F.DIRECTIONS[self.direction]

    @property
    def is_door(self) -> bool:
        return self.locks in (1, 2, 3, 4)


@dataclass
class Room:
    vnum: int
    name: str
    description: str
    room_flags: int  # as in the file
    sector: int
    exits: dict[int, Exit] = field(default_factory=dict)
    extra_descr: list[ExtraDescription] = field(default_factory=list)
    line: int = 0

    @property
    def effective_room_flags(self) -> int:
        """db.cpp load_rooms 'horrible hack': rooms 3000-3399 always get Law."""
        if 3000 <= self.vnum < 3400:
            return self.room_flags | (1 << 18)  # RoomFlag::Law = S
        return self.room_flags

    @property
    def sector_name(self) -> str:
        return F.SECTORS[self.sector] if 0 <= self.sector < len(F.SECTORS) else f"sector{self.sector}"


@dataclass
class Reset:
    command: str  # M O P G E D R
    if_flag: int  # read and ignored by the C++
    arg1: int
    arg2: int
    arg3: int
    arg4: int
    comment: str  # trailing text on the line
    line: int = 0
    room_vnum: int | None = None  # the room the C++ attaches this reset to


@dataclass
class Shop:
    keeper: int
    buy_types: list[int]  # 5 slots; 0 = none
    profit_buy: int
    profit_sell: int
    open_hour: int
    close_hour: int
    line: int = 0


@dataclass
class Special:
    mob_vnum: int
    spec_fun: str
    line: int = 0


@dataclass
class MobProgRef:
    mob_vnum: int
    filename: str
    line: int = 0


@dataclass
class Help:
    level: int
    keywords: str
    text: str
    line: int = 0


@dataclass
class Social:
    name: str
    phrases: list[str]  # char_no_arg, others_no_arg, char_found, others_found, vict_found,
    #                     char_not_found (unused), char_auto, others_auto ("" where file had $)


@dataclass
class AreaFile:
    """Everything parsed from one ``.are`` file."""

    filename: str
    header: AreaHeader | None = None
    sections: list[str] = field(default_factory=list)  # order seen
    mobs: list[Mob] = field(default_factory=list)
    objects: list[Obj] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    resets: list[Reset] = field(default_factory=list)
    shops: list[Shop] = field(default_factory=list)
    specials: list[Special] = field(default_factory=list)
    mobprogs: list[MobProgRef] = field(default_factory=list)
    helps: list[Help] = field(default_factory=list)
    socials: list[Social] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.header.short_name if self.header else self.filename
