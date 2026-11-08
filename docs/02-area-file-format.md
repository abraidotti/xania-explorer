# Area file format (`.are`)

This is the reference spec for Xania's area files, written from the C++ loader. Line references point into
`xania/src/` (e.g. [db.cpp:395](../../xania/src/db.cpp#L395)). The Python port in
[xania_explorer/areafile/](../xania_explorer/areafile/) follows the same structure, so each section here corresponds
to one parser function.

**Severity.** The C++ treats some problems as fatal (`exit(1)`, so the MUD won't boot). Others it only logs
(`logger.bug`) and then carries on with a default. Each rule below says which.

---

## 1. Loading model

- `area/area.lst` lists the files to load, one word each, ending at a word starting with `$`. Files are loaded in that
  order ([db.cpp:225](../../xania/src/db.cpp#L225)). A name of `-` means stdin, which nothing uses.
  **`.are` files that aren't listed are never loaded.** Five are currently unlisted: CausewayToImmortality,
  HelpLore, LairOfTheShadowCouncil, TantricObstacles and proto. Three of them (HelpLore, LairOfTheShadowCouncil,
  proto) would be fatal to load, and Causeway has invalid attack types; see the
  area catalogue (see [Xania versions](versions.md)).
- `version.are` is generated from `version.are.in` at build time (in the repo it's an empty file).
- A file is a sequence of sections: `#NAME`, then the section body. `#$` ends the file
  ([db.cpp:241](../../xania/src/db.cpp#L241)). Section names are matched case-insensitively. An unknown name, or
  any non-`#` character where a section should start, is **fatal**.
- Mobs, objects, rooms, resets, shops, specials and mobprogs belong to the most recently loaded `#AREA`. That can be
  an `#AREA` from a *previous file* if this file has none. Help-only files (`Help.are`, `HelpGroups.are`, …) and
  `Socials.are` have no `#AREA` header.
- Vnums (virtual numbers) are global across all files. A duplicate mob, object or room vnum is **fatal**. Vnums
  are stored as `sh_int` (16-bit signed).
- Cross-file references (exit destinations, reset targets) are resolved after every file is loaded
  ([db.cpp:280](../../xania/src/db.cpp#L280)).

## 2. Primitive tokens

Every field is read by one of these functions ([db.cpp:1241-1470](../../xania/src/db.cpp#L1241)). Leading
whitespace is always skipped.

| Token | Reader | Grammar | Notes |
|---|---|---|---|
| **number** | `fread_number` :1267 | `[+-]digits` then optionally `\|number` | `a\|b` means a + b. Consumes **one** trailing space; any other character is pushed back, so `1d6+2` reads as `1` then `d`. A non-digit is **fatal**. |
| **flag** | `fread_flag` :1356 | letters and/or digits, then optionally `\|flag` | Each letter sets one bit: `A`–`Z` are bits 0–25 and `a`–`z` are bits 26–51. A run of the *same* letter counts once (`AAB` = `AB`). `0` means no flags. Digits are added as a decimal value. |
| **string** | `fread_string` :1389 | text up to `~` | Multi-line. `~` can't appear inside. EOF ends the string silently. |
| **string-eol** | `fread_string_eol` :1406 | rest of the line | Used only by `#SOCIALS`. |
| **word** | `try_fread_word` :1438 | non-space run, or `'...'` / `"..."` | **Fatal** at EOF, including a final word with no whitespace after it. |
| **letter** | `fread_letter` :1254 | one non-space char | Used for record markers (`#`, `D`, `E`, `A`, `S`, …). |
| **spnumber** | `try_fread_spnumber` :1310 | a spell slot number, or `spell name~` | Quoted spell names are **fatal**. An unknown spell name is **fatal**. |
| **dice** | `Dice::from_file` ([Dice.cpp:6](../../xania/src/Dice.cpp#L6)) | `NdS+B` | A wrong separator, `N<=0` or `S<=0` is only logged. |
| **to-eol** | `fread_to_eol` :1422 | discard to end of line | Text after a reset's arguments is a free-form comment. |

**Prefix-matched words.** Enum-valued words are matched by *case-insensitive prefix, first match in table order*
(`matches_start`, [string_utils.cpp:258](../../xania/src/string_utils.cpp#L258)). For example, `stand` gives
Standing, `s` as a body size gives small, and `s` as an attack gives slice.

**Flag letters in headers vs files.** C++ headers write bits 26 and up as doubled letters (`aa`, `bb`, …;
[StandardBits.hpp](../../xania/src/common/StandardBits.hpp)). In an area file you write the single lower-case
letter: `a` = bit 26 = `aa`.

---

## 3. `#AREA` — header

[Area.cpp:14](../../xania/src/Area.cpp#L14)

```
#AREA
<filename>~                 ignored
<short name>~               shown by 'areas' and used in logs
<description>~              "{min max} Author  Long Name", or "{ ALL } ..." / "{None} ..."
<lowest vnum> <highest vnum>
```

- **Level band** = `sscanf("{%d %d}")` on the description. If it doesn't match, the area is "all levels".
- **Vnum range.** The declared range is then *extended* by every mob and object vnum in the file
  (`Area::define_vnum`, [Area.cpp:45](../../xania/src/Area.cpp#L45)), but **not by room vnums**. Quirk: if either
  declared bound is 0, the first mob/object vnum replaces both.
- The effective range matters because `Area::reset()` resets rooms by iterating `lowest..highest` vnum
  ([Area.cpp:81](../../xania/src/Area.cpp#L81)). A room outside its area's range never has its resets run by that
  area.

## 4. `#MOBILES` — mob prototypes

[MobIndexData.cpp:28](../../xania/src/MobIndexData.cpp#L28). The records repeat until `#0`.

```
#<vnum>
<keywords>~
<short descr>~              "a priest of Wandera"  (leading articles lower-cased on load)
<long descr>~               room line when standing at default position
<look description>~
<race>~                     race_table name, prefix match (handler.cpp:61); unknown → "unique", silently
<act flags> <affected_by flags> <alignment> <group>
<level> <hitroll> <hit dice> <mana dice> <damage dice> <attack word>
<ac pierce> <ac bash> <ac slash> <ac exotic>
<offensive flags> <immune flags> <resist flags> <vuln flags>
<start pos> <default pos> <sex> <gold>
<form flags> <body-part flags> <size> <material>
```

| Field | Type | Values / notes |
|---|---|---|
| act | flag | [CharActFlag.hpp](../../xania/src/CharActFlag.hpp): B Sentinel, C Scavenger, F Aggressive, G StayArea, H Wimpy, J Train, K Practice, L Sentient, M Talkative, O Undead, Q Cleric, R Mage, S Thief, T Warrior, U NoAlign, V NoPurge, a Healer, b Gain, c UpdateAlways, d CanBeRidden. `A` (Npc) is always set on load. The class bits (Q/R/S/T) pick the NPC's to-hit curve in [HitChance.cpp](../../xania/src/HitChance.cpp#L89). |
| affected_by | flag | [AffectFlag.hpp](../../xania/src/AffectFlag.hpp) (Sanctuary H, Haste V, Flying T, …) |
| alignment | number | −1000..1000 by convention |
| group | number | NPC group id (used for assisting) |
| level | number | not capped at load; Dell's priest is level 112 |
| hitroll | number | added to the to-hit roll |
| hit / mana / damage | dice | Rolled per instance. Damage dice are used **only when the mob is unarmed** ([fight.cpp:465](../../xania/src/fight.cpp#L465)). |
| attack | word, prefix | [Attacks.cpp](../../xania/src/Attacks.cpp) table; sets the damage type. Unknown → logged, uses `hit`. |
| ac ×4 | number | order is [ArmourClass.hpp](../../xania/src/ArmourClass.hpp): pierce, bash, slash, exotic. More negative is better. |
| offensive | flag | [OffensiveFlag.hpp](../../xania/src/OffensiveFlag.hpp): A AreaAttack, B Backstab, C Bash, D Berserk, E Disarm, F Dodge, H Fast, I Kick, J KickDirt, K Parry, L Rescue, N Trip, P–U Assist*, V Headbutt, W Slow |
| imm / res / vuln | flag | [ToleranceFlag.hpp](../../xania/src/ToleranceFlag.hpp) |
| start / default pos | word, prefix | Dead Mortal Incap Stunned Sleeping Resting Sitting Fighting Standing. Unknown → logged, default. |
| sex | word, prefix | neutral / male / female (checked in that order). Unknown is **fatal**. |
| gold | number | |
| form / parts | flag | [MorphologyFlag.hpp](../../xania/src/MorphologyFlag.hpp), [BodyPartFlag.hpp](../../xania/src/BodyPartFlag.hpp) |
| size | word, prefix | tiny small medium large huge giant. Unknown → logged, medium. |
| material | word | [Materials.cpp](../../xania/src/Materials.cpp); unknown → default material |

**On load, race flags are ORed in.** act, affected_by, off, imm, res, vuln, form and parts all get the race's
values from [Races.cpp](../../xania/src/Races.cpp) added. The catalogue shows *file* values only, so for example an
elf mob also resists Charm even if the file doesn't say so.

## 5. `#OBJECTS` — object prototypes

[db.cpp:574-776](../../xania/src/db.cpp#L574). The records repeat until `#0`.

```
#<vnum>
<keywords>~
<short descr>~
<room description>~         empty → logged
<material>~                 note: a ~string, unlike mobs
<type word> <extra flags> <wear flags>
[,<wear string>~]           optional custom wear message (Death's "Wear Strings")
<v0> <v1> <v2> <v3> <v4>    grammar depends on type, see below
<level> <weight> <cost> <condition letter>
{ A <location> <modifier> | E <keywords>~ <description>~ }*
```

- **type**: prefix match in [ObjectType.hpp](../../xania/src/ObjectType.hpp) enum order (light, scroll, wand,
  staff, weapon, treasure, armor, potion, clothing, furniture, trash, container, drink, key, food, money, boat,
  npccorpse, pccorpse, fountain, pill, map, bomb, portal), or the type number. Unknown → logged, light.
- **extra flags** [ObjectExtraFlag.hpp](../../xania/src/ObjectExtraFlag.hpp): A Glow, B Hum, C Dark, D Lock, E Evil,
  F Invis, G Magic, H NoDrop, I Bless, J/K/L Anti-Good/Evil/Neutral, M NoRemove, N Inventory, O NoPurge, P RotDeath,
  Q VisDeath, R ProtectContainer, S NoLocate, T SummonCorpse, U Unique. **NoRemove on a non-weapon is fatal.**
- **wear flags** [ObjectWearFlag.hpp](../../xania/src/ObjectWearFlag.hpp): A Take, B Finger, C Neck, D Body, E Head,
  F Legs, G Feet, H Hands, I Arms, J Shield, K About, L Waist, M Wrist, N Wield, O Hold, P TwoHands, Q Ears.
- **condition**: P 100, G 90, A 75, W 50, D 25, B 10, R 0; anything else 100.
- **A** affects: `location modifier`. Locations are from
  [AffectLocation.hpp](../../xania/src/AffectLocation.hpp): 1 Str, 2 Dex, 3 Int, 4 Wis, 5 Con, 12 Mana, 13 Hit,
  14 Move, 17 Ac, 18 Hitroll, 19 Damroll, 20–24 saves, …
- **Validators:** `ScrollTargetValidator` rejects scrolls whose spells have incompatible targets (**fatal**;
  [ScrollTargetValidator.cpp](../../xania/src/ScrollTargetValidator.cpp)). It isn't ported yet.

### Value grammar by type

| Type | v0 | v1 | v2 | v3 | v4 |
|---|---|---|---|---|---|
| weapon | weapon-type word (exotic sword dagger spear mace axe flail whip polearm; prefix) | dice number | dice sides | attack word (prefix) | weapon flags: A Flaming, B Frost, C Vampiric, D Sharp, E Vorpal, F TwoHands, G Poisoned, I Plagued, J Lightning, K Acid |
| container | capacity (number) | container flags | key vnum | number | number |
| drink, fountain | capacity | current | liquid word | number (poisoned) | number |
| wand, staff | spell level | max charges | charges | **spnumber** | number |
| potion, pill, scroll, bomb | spell level | spnumber | spnumber | spnumber | spnumber |
| everything else (armor, light, food, …) | flag | flag | flag | flag | flag |

For armor, v0–v3 are the AC bonuses (pierce/bash/slash/exotic). They're read as flags, so plain numbers work. After
reading, spell **slot numbers are translated to skill numbers** ([db.cpp:746](../../xania/src/db.cpp#L746)); bombs
also translate v4. Slot numbers are listed in [SkillTables.cpp](../../xania/src/SkillTables.cpp) and must never
change.

Weapon damage is `dice(v1, v2) × weapon skill %`. The average is `v1 × (v2 + 1) / 2`. The balance rule in
[entity_balance.cpp](../../xania/src/entity_balance.cpp) allows an average of `level/2 + 4` (a little more for
two-handers).

## 6. `#ROOMS`

[db.cpp:395](../../xania/src/db.cpp#L395). The records repeat until `#0`.

```
#<vnum>
<name>~
<description>~
<room flags> <sector number>
{ D<dir> <exit description>~ <exit keywords>~ <locks> <key vnum> <to vnum>
| E <keywords>~ <description>~ }*
S
```

(Unlike stock ROM, there's no area-number field before the flags.)

- **room flags** [RoomFlag.hpp](../../xania/src/RoomFlag.hpp): A Dark, C NoMob, D Indoors, J Private, K Safe,
  L Solitary, M PetShop, N NoRecall, O ImpOnly, P GodsOnly, Q HeroesOnly, R NewbiesOnly, S Law.
  **Hack:** rooms 3000–3399 always get Law ([db.cpp:418](../../xania/src/db.cpp#L418)). **Rooms with no exit
  leading anywhere get NoMob** after load ([db.cpp:801](../../xania/src/db.cpp#L801)).
- **sector** [SectorType.hpp](../../xania/src/SectorType.hpp): 0 Inside, 1 City, 2 Field, 3 Forest, 4 Hills,
  5 Mountain, 6 SwimmableWater, 7 NonSwimmableWater, 8 Unused, 9 Air, 10 Desert. Invalid → logged, Inside.
- **dir**: 0 N, 1 E, 2 S, 3 W, 4 Up, 5 Down. Out of range is **fatal**. A later `D` for the same direction replaces
  the earlier one.
- **locks**: 0 no door, 1 door, 2 door + pick-proof, 3 door + pass-proof, 4 door + both.
- **to vnum**: a room vnum. `-1` is a cosmetic exit that leads nowhere. Below −1 is **one-way** to `abs(vnum)`.
  0, or a room that doesn't exist, leaves the exit unresolved (it leads nowhere).
- **Exit consistency** ([db.cpp:804](../../xania/src/db.cpp#L804)): for a two-way exit A→B, if B's reverse exit
  leads somewhere other than A, the loader logs `Fix_exits`. If B's reverse exit leads *nowhere*, the C++
  dereferences a null pointer. Mark deliberately asymmetric exits one-way (negative vnum).

## 7. `#RESETS` — repopulation script

Parsed by [db.cpp:301](../../xania/src/db.cpp#L301) and run by `reset_room`
([db.cpp:829](../../xania/src/db.cpp#L829)). Each line is `<cmd> <if_flag> <args…> [comment]` until `S`. `*`
starts a comment line. `if_flag` is read and ignored. Text after the last argument is ignored, so it's used for
comments (e.g. `M 0 3011 1 3001 1  Concordius`). An unknown command is **fatal**.

Resets are stored on rooms, not the area. The room each reset attaches to depends on the lines before it:

| Cmd | Args | Attached to | Behaviour at reset time |
|---|---|---|---|
| `M` | mob vnum, **world max**, room vnum, **room max** | room arg3 (becomes "last room") | Spawn the mob unless the world already has ≥ arg2 of it, or the room has ≥ arg4. If the room at `vnum − 1` is a PetShop, the mob gets Pet. Sets "last mob". |
| `O` | obj vnum, (unused), room vnum | room arg3 (becomes "last obj room") | Skipped if **any player is in the area** or the room already has one. **The object's cost is set to 0** ([db.cpp:908](../../xania/src/db.cpp#L908)), so floor loot can't be sold. |
| `P` | obj vnum, **world limit**, container obj vnum, **count** | the last `O`'s room (or the last `M`'s room after `G`/`E`) | Put up to arg4 copies into the first existing instance of the container. Skipped if the area is occupied. Limit: arg2 > 20 → 6, −1 → unlimited (999). Even past the limit there's a 1-in-5 chance to spawn anyway. |
| `G` | obj vnum, **drop %** | the last `M`'s room | Give the item to the last spawned mob. A shopkeeper always gets it, as shop inventory. Otherwise it spawns with probability arg2%. **arg2 outside 1..100 on a non-shopkeeper calls `exit(1)` at reset time, crashing a running MUD.** |
| `E` | obj vnum, **drop %**, wear location | the last `M`'s room | As `G`, then equips it at a [Worn.hpp](../../xania/src/Worn.hpp) slot: 0 Light, 1/2 Finger L/R, 3/4 Neck, 5 Body, 6 Head, 7 Legs, 8 Feet, 9 Hands, 10 Arms, 11 Shield, 12 About, 13 Waist, 14/15 Wrist L/R, 16 Wield, 17 Hold, 18 Ears. |
| `D` | room vnum, direction, state | (not stored) | Applied **once at load**: 0 open, 1 closed, 2 closed + locked. The exit must be a door (**fatal** otherwise). Every reset restores each exit's saved door state. |
| `R` | room vnum, number of exits | room arg1 | Shuffles exits 0..arg2−1 (a maze). arg2 outside 0..6 is **fatal**. |

`G`/`E` lines only take effect if the last `M` actually spawned. Spawn order matters: an area resets rooms in
ascending vnum order, and each room runs its resets in file order.

## 8. `#SHOPS`

[db.cpp:491](../../xania/src/db.cpp#L491). One line per shop, ending with a line containing just `0`:

```
<keeper mob vnum> <buy type ×5> <profit buy %> <profit sell %> <open hour> <close hour> [comment]
```

The buy types are object type **numbers** (0 = slot unused; see the ObjectType table above). If the keeper mob
doesn't exist, the C++ dereferences a null pointer.

## 9. `#SPECIALS`

[db.cpp:520](../../xania/src/db.cpp#L520). Lines are `M <mob vnum> <spec_fun name> [comment]`, and `*` lines are
comments, until `S`. The spec function name must exist in [special.cpp](../../xania/src/special.cpp) (`spec_lookup`),
otherwise it's **fatal**.

## 10. `#MOBPROGS`

[MProgLoader.cpp:104](../../xania/src/MProgLoader.cpp#L104). Lines are `M <mob vnum> <file.prg> [comment]`, and `*`
lines are comments, until `S`. The `.prg` file is read from the area dir. An unknown mob vnum, a missing file or
an invalid file is **fatal**.

A `.prg` file ([MProgLoader.cpp:76](../../xania/src/MProgLoader.cpp#L76)) has one or more blocks, then `|`:

```
>greet_prog 30~
if ispc($n)
    beg $n
endif
~
|
```

The triggers are: act, speech, rand, fight, hitprcnt, death, entry, greet, all_greet, give, bribe (all `_prog`).
`in_file_prog` is rejected. The argument string's meaning depends on the trigger, usually a % chance or an amount.
The interpreter is [MProgImpl.cpp](../../xania/src/MProgImpl.cpp).

## 11. `#HELPS`

[Help.cpp:13](../../xania/src/Help.cpp#L13). Each entry is `<min level> <keywords>~ <text>~`, ending at the keyword
`$` (conventionally `0 $~`). A leading `.` in the text is stripped, which lets the text start with whitespace.
Level −1 entries (e.g. `DIKU`) are visible to everyone.

## 12. `#SOCIALS`

[Socials.cpp:17](../../xania/src/Socials.cpp#L17). Each social is `<name>` followed by 8 lines (char-no-arg,
others-no-arg, char-found, others-found, victim-found, char-not-found (unused), char-auto, others-auto), then a line
containing `#`. `$` on a line means an empty phrase. The section ends at `#0`. A missing `#` terminator stops social
loading (logged).

---

## 13. Annotated example (Dell.are)

```
#AREA
Dell.are~                       filename (ignored)
The Dell~                       short name
{ ALL } Wandera The Dell~       no numeric band → all levels
12100  12120                    declared vnum range
#MOBILES
#12100
priest~
a priest of Wandera~
A priest loyal to Wandera stands here.
A priest of Wandera beams a smile at you.
~
A strong, holy man stands here preaching ...
~
human~
BQ CDFHV 1000 0                 act Sentinel+Cleric; aff DetectEvil/Invis/Hidden, Sanctuary, Haste; align 1000; group 0
112 56 1d1+7600 1d1+1444 10d11+56 wrath
                                level 112, hitroll 56, 7601 hp, 1445 mana, 10d11+56 dmg (avg 116), energy damage
-65 -65 -65 -65                 AC pierce/bash/slash/exotic
FKIHE N C Z                     off Dodge Parry Kick Fast Disarm; imm Holy; res Magic; vuln Iron
stand stand male 1236           positions, sex, gold
0 0 medium 0                    form/parts from race, size, material (0 → default)
```

## 14. Quick checklist for builders

- Put every new file in `area.lst`.
- Keep mobs, objects **and rooms** inside the declared vnum range; rooms outside it won't reset.
- `G`/`E` drop rate must be 1–100.
- Mark one-way exits with a negative vnum.
- Use `spell name~`, never `'spell name'`.
- Don't put NoRemove on anything but weapons.
- Run `python -m xania_explorer check` before committing.
