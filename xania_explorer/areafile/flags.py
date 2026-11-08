"""Flag and enum tables ported from Xania headers.

Flags are stored in area files as letters (``A``..``Z`` = bits 0..25, and
doubled lower-case letters ``aa``..``ee`` = bits 26..30, see
``xania/src/common/StandardBits.hpp``). In the file reader a run of the same
letter counts once, so ``aa`` in a header is written ``a`` in an area file.

Keep each table in the order of the C++ enum and cite its source header.
"""

from __future__ import annotations


def _letters(spec: str) -> dict[int, str]:
    """Build {bit: name} from 'Name=A Other=B Doubled=aa' style specs."""
    out: dict[int, str] = {}
    for item in spec.split():
        name, letter = item.split("=")
        if len(letter) == 1 and letter.isupper():
            bit = ord(letter) - ord("A")
        elif len(letter) == 2 and letter[0] == letter[1] and letter.islower():
            bit = 26 + ord(letter[0]) - ord("a")
        else:
            raise ValueError(item)
        out[bit] = name
    return out


# xania/src/CharActFlag.hpp
CHAR_ACT = _letters(
    "Npc=A Sentinel=B Scavenger=C Aggressive=F StayArea=G Wimpy=H Pet=I Train=J Practice=K "
    "Sentient=L Talkative=M Undead=O Cleric=Q Mage=R Thief=S Warrior=T NoAlign=U NoPurge=V "
    "Healer=aa Gain=bb UpdateAlways=cc CanBeRidden=dd"
)
# xania/src/OffensiveFlag.hpp
OFFENSIVE = _letters(
    "AreaAttack=A Backstab=B Bash=C Berserk=D Disarm=E Dodge=F Fade=G Fast=H Kick=I KickDirt=J "
    "Parry=K Rescue=L Tail=M Trip=N Crush=O AssistAll=P AssistAlign=Q AssistRace=R "
    "AssistPlayers=S AssistGuard=T AssistVnum=U Headbutt=V Slow=W"
)
# xania/src/ToleranceFlag.hpp (used for imm / res / vuln)
TOLERANCE = _letters(
    "Summon=A Charm=B Magic=C Weapon=D Bash=E Pierce=F Slash=G Fire=H Cold=I Lightning=J Acid=K "
    "Poison=L Negative=M Holy=N Energy=O Mental=P Disease=Q Drowning=R Light=S Wood=X Silver=Y Iron=Z"
)
# xania/src/AffectFlag.hpp
AFFECT = _letters(
    "Blind=A Invisible=B DetectEvil=C DetectInvis=D DetectMagic=E DetectHidden=F Talon=G "
    "Sanctuary=H FaerieFire=I Infrared=J Curse=K ProtectionEvil=L Poison=M ProtectionGood=N "
    "Sneak=P Hide=Q Sleep=R Charm=S Flying=T PassDoor=U Haste=V Calm=W Plague=X Weaken=Y "
    "DarkVision=Z Berserk=aa Swim=bb Regeneration=cc OctarineFire=dd Lethargy=ee"
)
# xania/src/RoomFlag.hpp
ROOM = _letters(
    "Dark=A NoMob=C Indoors=D Private=J Safe=K Solitary=L PetShop=M NoRecall=N ImpOnly=O "
    "GodsOnly=P HeroesOnly=Q NewbiesOnly=R Law=S"
)
# xania/src/ExitFlag.hpp (runtime flags; files use the 0-4 'locks' code instead)
EXIT = _letters(
    "IsDoor=A Closed=B Locked=C PickProof=F PassProof=G Easy=H Hard=I Infuriating=J NoClose=K "
    "NoLock=L Trap=M TrapDarts=N TrapPoison=O TrapExploding=P TrapSleepgas=Q TrapDeath=R Secret=S"
)
# xania/src/ObjectWearFlag.hpp
WEAR = _letters(
    "Take=A Finger=B Neck=C Body=D Head=E Legs=F Feet=G Hands=H Arms=I Shield=J About=K Waist=L "
    "Wrist=M Wield=N Hold=O TwoHands=P Ears=Q"
)
# xania/src/ObjectExtraFlag.hpp
OBJ_EXTRA = _letters(
    "Glow=A Hum=B Dark=C Lock=D Evil=E Invis=F Magic=G NoDrop=H Bless=I AntiGood=J AntiEvil=K "
    "AntiNeutral=L NoRemove=M Inventory=N NoPurge=O RotDeath=P VisDeath=Q ProtectContainer=R "
    "NoLocate=S SummonCorpse=T Unique=U"
)
# xania/src/WeaponFlag.hpp
WEAPON_FLAG = _letters(
    "Flaming=A Frost=B Vampiric=C Sharp=D Vorpal=E TwoHands=F Poisoned=G Plagued=I Lightning=J Acid=K"
)

# xania/src/ObjectType.hpp -- order matters: the C++ looks names up by
# case-insensitive *prefix* in enum order (ObjectType.cpp lookup_impl).
OBJECT_TYPES: dict[str, int] = {
    "Light": 1, "Scroll": 2, "Wand": 3, "Staff": 4, "Weapon": 5, "Treasure": 8, "Armor": 9,
    "Potion": 10, "Clothing": 11, "Furniture": 12, "Trash": 13, "Container": 15, "Drink": 17,
    "Key": 18, "Food": 19, "Money": 20, "Boat": 22, "Npccorpse": 23, "Pccorpse": 24,
    "Fountain": 25, "Pill": 26, "Map": 28, "Bomb": 29, "Portal": 30,
}
OBJECT_TYPE_BY_NUM = {v: k for k, v in OBJECT_TYPES.items()}

# xania/src/SectorType.hpp
SECTORS = ["Inside", "City", "Field", "Forest", "Hills", "Mountain", "SwimmableWater",
           "NonSwimmableWater", "Unused", "Air", "Desert"]
# xania/src/Direction.hpp
DIRECTIONS = ["north", "east", "south", "west", "up", "down"]
REVERSE_DIRECTION = [2, 3, 0, 1, 5, 4]
# xania/src/ArmourClass.hpp -- order of the four mob AC numbers
ARMOUR_CLASSES = ["pierce", "bash", "slash", "exotic"]
# xania/src/Weapon.hpp
WEAPON_TYPES = ["exotic", "sword", "dagger", "spear", "mace", "axe", "flail", "whip", "polearm"]
# xania/src/BodySize.hpp
BODY_SIZES = ["tiny", "small", "medium", "large", "huge", "giant"]
# xania/src/AffectLocation.hpp (object 'A' affect locations)
AFFECT_LOCATIONS = [
    "None", "Str", "Dex", "Int", "Wis", "Con", "Sex", "Class", "Level", "Age", "Height", "Weight",
    "Mana", "Hit", "Move", "Gold", "Exp", "Ac", "Hitroll", "Damroll", "SavingPara", "SavingRod",
    "SavingPetri", "SavingBreath", "SavingSpell",
]
# db.cpp load_objects: condition letter -> condition %
CONDITIONS = {"P": 100, "G": 90, "A": 75, "W": 50, "D": 25, "B": 10, "R": 0}

# xania/src/Attacks.cpp attack table: name -> damage type
ATTACKS: dict[str, str] = {
    "none": "None", "slice": "Slash", "stab": "Pierce", "slash": "Slash", "whip": "Slash",
    "claw": "Slash", "blast": "Bash", "pound": "Bash", "crush": "Bash", "grep": "Slash",
    "bite": "Pierce", "pierce": "Pierce", "suction": "Bash", "beating": "Bash",
    "digestion": "Acid", "charge": "Bash", "slap": "Bash", "punch": "Bash", "wrath": "Energy",
    "magic": "Energy", "divine": "Holy", "cleave": "Slash", "scratch": "Pierce", "peck": "Pierce",
    "peckb": "Bash", "chop": "Slash", "sting": "Pierce", "smash": "Bash", "shbite": "Lightning",
    "flbite": "Fire", "frbite": "Cold", "acbite": "Acid", "chomp": "Pierce", "drain": "Negative",
    "thrust": "Pierce", "slime": "Acid", "shock": "Lightning", "thwack": "Bash", "flame": "Fire",
    "chill": "Cold", "maul": "Slash", "hit": "Bash",
}


_DECODED: dict[tuple[int, int], list[str]] = {}


def decode(value: int, table: dict[int, str]) -> list[str]:
    """Names for the set bits of ``value``; unknown bits shown as ``bit<N>``. Returns a fresh list.

    Memoised per (table, value): the analyses decode the same few flag words millions of times."""
    key = (id(table), value)
    hit = _DECODED.get(key)
    if hit is None:
        hit = _DECODED[key] = _decode(value, table)
    return list(hit)


def _decode(value: int, table: dict[int, str]) -> list[str]:
    names = []
    bit = 0
    while value >> bit:
        if value >> bit & 1:
            names.append(table.get(bit, f"bit{bit}"))
        bit += 1
    return names


def letters(value: int) -> str:
    """Render a flag value back into area-file letter notation (``0`` if none)."""
    out = []
    bit = 0
    while value >> bit:
        if value >> bit & 1:
            out.append(chr(ord("A") + bit) if bit < 26 else chr(ord("a") + bit - 26))
        bit += 1
    return "".join(out) or "0"


def lookup_object_type(word: str) -> int | None:
    """Port of ``ObjectTypes::lookup_impl``: prefix match in enum order, then number."""
    w = word.lower()
    if w:
        for name, num in OBJECT_TYPES.items():
            if name.lower().startswith(w):
                return num
    if word.lstrip("-").isdigit() and int(word) in OBJECT_TYPE_BY_NUM:
        return int(word)
    return None

# xania/src/Worn.hpp -- 'E' reset arg3 (wear location); index = value
WORN = ["Light", "FingerL", "FingerR", "Neck1", "Neck2", "Body", "Head", "Legs", "Feet", "Hands", "Arms",
        "Shield", "About", "Waist", "WristL", "WristR", "Wield", "Hold", "Ears"]

# xania/src/Position.hpp
POSITIONS = ["Dead", "Mortal", "Incap", "Stunned", "Sleeping", "Resting", "Sitting", "Fighting", "Standing"]
# xania/src/Sex.hpp -- Sex::try_from_name checks in this order
SEXES = ["neutral", "male", "female"]


def prefix_lookup(word: str, names) -> str | None:
    """Port of the ubiquitous ``matches_start(word, name)`` loop
    (string_utils.cpp:258): the first name, in table order, of which ``word``
    is a non-empty case-insensitive prefix. ``"s"`` -> ``"slice"`` for attacks,
    ``"S"`` -> ``"small"`` for body sizes, ``"stand"`` -> ``"Standing"``."""
    w = word.lower()
    if not w:
        return None
    for name in names:
        if name.lower().startswith(w):
            return name
    return None
