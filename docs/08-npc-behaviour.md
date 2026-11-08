# NPC behaviour

What mobs do between and during fights: when they attack, help each other, flee, wander, pick things up, and
the two scripting systems that give them extra behaviour (special procedures and mob programs). Paths are relative
to `xania/src/`. How mobs fight a round is in [Combat](05-combat.md); how they're placed and respawned is in
[World model](03-world-model.md).

## The clock

The game runs at 4 pulses a second ([Constants.hpp:25](../../xania/src/Constants.hpp#L25)). `update_handler`
([update.cpp:856](../../xania/src/update.cpp#L856)) drives everything NPCs do:

| Every | Calls | NPC behaviour |
|---|---|---|
| pulse (¼ s) | `aggr_update` | aggression, sentient memory, queued Act programs |
| 4 s (`PULSE_MOBILE`) | `mobile_update` | special procedures, Random programs, scavenging, wandering |
| 3 s (`PULSE_VIOLENCE`) | `violence_update` | combat rounds, Fight and HitPercent programs, assisting |
| 30 s (`PULSE_TICK`) | `char_update` | regeneration, affects wearing off |
| 30–90 s (random) | `area_update` | area resets |

**Empty areas sleep.** `mobile_update` skips every mob in an area that has had no player since its last reset,
unless the mob has the `update_always` act flag. Random and Act programs need a player in the area right now
(`occupied()`).

## Aggression

`aggr_update` ([update.cpp:196](../../xania/src/update.cpp#L196)) runs every pulse. For each mortal player, it
checks every mob in the player's room with `do_aggressive_sentient`
([update.cpp:65](../../xania/src/update.cpp#L65)). An **aggressive** mob attacks when all of these hold:

- the room isn't `safe`;
- it isn't calmed, charmed, asleep or already fighting;
- it can see the player;
- a coin flip succeeds. With 4 tries a second, that's effectively at once.

It then attacks a random mortal in the room that it can see, but **only players no more than 5 levels above
it** (`mob level ≥ player level − 5`). A level-20 aggressive mob ignores a level-26 player. An aggressive mob
that is also **wimpy** only attacks sleeping players.

**Sentient mobs remember.** When a player attacks a mob with the `sentient` flag, the mob stores the player's
name ([fight.cpp:247](../../xania/src/fight.cpp#L247)). Later, if it sees that player and isn't fighting, it yells
"I never forget a face" and attacks, whatever the level difference. The memory clears once the mob is back at
full HP and mana.

## Assisting

After each combat round, `check_assist` ([fight.cpp:124](../../xania/src/fight.cpp#L124)) lets idle, awake
characters in the room join in:

| Who joins | When |
|---|---|
| mob with `assist_players` | a player is fighting someone and the mob's level + 6 > the victim's level |
| player with `autoassist`, or a charmed follower | someone in their group is fighting |
| mob with `assist_all` | any mob is fighting |
| mob with `assist_race` | a mob of the same race is fighting |
| mob with `assist_align` | a mob of the same alignment (good, neutral or evil) is fighting |
| mob with `assist_vnum` | a mob of the same prototype is fighting |

Mobs helping mobs join with a 50% chance each round, against a random member of the victim's group. So a pack of
`assist_vnum` mobs joins one by one, not all at once.

## Fleeing

After taking damage ([fight.cpp:834](../../xania/src/fight.cpp#L834)), an NPC flees when either:

- it's **wimpy** and below 20% HP, with a 1-in-4 chance per hit; or
- it's charmed and its master has left the room.

Players flee at their own `wimpy` setting.

## Wandering and scavenging

In `mobile_update` ([update.cpp:242](../../xania/src/update.cpp#L242)), after special procedures and Random
programs, an awake mob that isn't busy can:

- **Scavenge**, if it has the `scavenger` flag: a 1-in-64 chance each 4 s to pick up the most valuable object in
  the room it's allowed to take, then wear what it can.
- **Wander**, unless it has the `sentinel` flag: a 1-in-16 chance each 4 s to try a random direction (one of
  32 values, so 26 in 32 tries do nothing). It can't go through closed doors or into `no_mob` rooms. With
  `stay_area`, it can't leave its area.

So a free wanderer in a room with exits on every side moves about once every 6 minutes (1/16 × 6/32 per 4 s). Mobs never return to where they spawned.

## Regeneration

Each tick (30 s), `hit_gain` ([update.cpp:319](../../xania/src/update.cpp#L319)) heals an NPC by `5 + level`:

- ×2 with the regeneration affect;
- then ×1.5 asleep, ×1 resting, ÷2 standing, ÷3 fighting.

Mana regenerates the same way (`mana_gain`, without the regeneration bonus). A level-60 mob standing in a room regains
about 32 HP per tick, so a mob a party walked away from is back to full within minutes.

## Special procedures

A `#SPECIALS` section in an area file attaches a C++ function to a mob prototype
([db.cpp:265](../../xania/src/db.cpp#L265); names resolved by `spec_lookup`,
[special.cpp:65](../../xania/src/special.cpp#L65)). It runs **first** in `mobile_update`, every 4 s. If it
returns true, the mob does nothing else that pulse (no wandering or scavenging).

**Fighting specials** cast at the mob's level. They're not limited by mana and run on their own 4-second clock,
on top of the mob's melee rounds. Combat (Combat & XP) doesn't model them, so mobs that have them are tougher
than that page shows.

| Special | When | Does |
|---|---|---|
| `spec_breath_fire/frost/acid/lightning` | fighting; ⅛ chance per opponent | the breath spell on that opponent |
| `spec_breath_gas` | fighting | gas breath on the whole room |
| `spec_breath_any` | fighting | one of the above at random (frost and lightning likeliest) |
| `spec_cast_mage` | fighting; ⅛ chance per opponent | a random attack spell its level allows: magic missile, chill touch, burning hands, shocking grasp, colour spray, lightning bolt, fireball, acid blast |
| `spec_cast_cleric` | fighting; ¼ chance per opponent | a random spell its level allows: blindness, earthquake, dispel evil/good, curse, plague, dispel magic, demonfire, exorcise |
| `spec_cast_undead` | fighting; ⅛ chance per opponent | poison, blind, curse, weaken, plague, energy drain, insanity, cause light/serious/critical, harm, change sex |
| `spec_cast_bastard` | fighting; ⅛ chance per opponent | blind, curse, energy drain, dispel magic, lethargy, gas breath |
| `spec_cast_judge` | fighting; ¼ chance per opponent | high explosive |
| `spec_poison` | fighting; chance `2 × level`% | poisons its opponent |

The "chance per opponent" picks are made in room order, so the first opponent listed is likelier to be chosen
than later ones (the source notes this). The casting lists rely on a random spell fitting the mob's level range;
the comment warns that a level with no valid spell would loop forever.

**Other specials:**

| Special | Does |
|---|---|
| `spec_cast_adept` | casts armour, bless, cure light/blindness/poison or refresh on players below level 11 |
| `spec_guard` | attacks player killers and thieves; otherwise joins the fight against the most evil fighter in the room |
| `spec_executioner` | attacks killers and thieves and summons two city guards |
| `spec_thief` | steals up to 15% of an awake player's gold (capped at `15 × level²`), or gets caught |
| `spec_fido` | eats NPC corpses, spilling their contents on the floor |
| `spec_janitor` | picks up drinks, trash and anything worth under 10 gold |
| `spec_mayor` | walks a fixed route through Midgaard each morning and evening, opening or closing the city gates |
| `spec_DEATH` | gates to the most injured player in the game (below 15% HP) and looms ominously |
| `spec_summoner` | the Necropolis corpse summoner ([CorpseSummoner.cpp](../../xania/src/CorpseSummoner.cpp)) |
| `spec_puff`, `spec_phil`, `spec_concordius`, `spec_aquila_pet`, `spec_greasy_joe` | flavour for named mobs |

`spec_greasy_joe` always returns true, so Greasy Joe never wanders or scavenges.

## Mob programs

An area file's `#MOBPROGS` section maps mob prototypes to `.prg` script files
([MProgLoader.cpp:104](../../xania/src/MProgLoader.cpp#L104); format in [Area file format](02-area-file-format.md)).
Each program in a file has a trigger type, an argument and a script of `if`/`else` checks and commands. The [area catalogue](versions.md) lists each area's programs.

| Trigger | Fires when | Argument |
|---|---|---|
| `act_prog` | a message containing a phrase is shown in the mob's room | the phrase(s) |
| `speech_prog` | someone says something containing a phrase | the phrase(s) |
| `rand_prog` | every 4 s, while a player is in the area | % chance |
| `fight_prog` | every combat round the mob fights | % chance |
| `hitprcnt_prog` | every combat round while the mob is below a share of its HP | HP % |
| `death_prog` | the mob dies | % chance |
| `entry_prog` | the mob itself walks into a room | % chance |
| `greet_prog` | someone the mob can see enters its room | % chance |
| `all_greet_prog` | anyone enters its room, seen or not | % chance |
| `give_prog` | someone gives it a named object (or `all`) | object name |
| `bribe_prog` | someone gives it at least this much gold | gold |

Notes:

- **Chance-based triggers** roll each program of that type in order and run the first that succeeds
  (`exec_with_chance`, [MProgImpl.cpp:568](../../xania/src/MProgImpl.cpp#L568)). Greet programs are the
  exception: every one that succeeds runs.
- **Act programs** are queued when the message is shown and run on the next pulse, if the area is occupied.
- **Commands** are the normal player commands plus `mp*` commands
  ([mob_commands.cpp](../../xania/src/mob_commands.cpp)): `mpkill`, `mpjunk`, `mpecho`/`mpechoat`/
  `mpechoaround`, `mpasound`, `mpmload`, `mpoload`, `mppurge`, `mpgoto`, `mpat`, `mptransfer` and `mpforce`.
- **Assessment caveat.** Programs can load mobs and objects (`mpmload`, `mpoload`). The content checks on the
  Bugs page can't see that, so an item "no reset places" may still be handed out by a program.

## What this means for balance

- **Aggression has a level ceiling.** Aggressive mobs leave players more than 5 levels above them alone, so
  high-level characters can walk through low areas unmolested, and an aggressive area only threatens players near
  its level.
- **Specials are free damage.** A caster or breather adds a spell every few seconds at no mana cost. That
  matters most at high level, where the spells scale with the mob's level. The combat model leaves them out.
- **Assist flags turn single fights into group fights,** one helper per round at 50% each. An area full of
  `assist_vnum` mobs is much harder than its per-mob numbers suggest.
- **Regeneration is fast** relative to fight length at high level. Long fights against a healing mob, or
  fights abandoned and resumed, cost more than the per-kill numbers suggest.
