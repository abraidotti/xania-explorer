# Persistence and administration

What survives a reboot and what doesn't, when characters are saved, and the immortal levels and tools for
running the MUD. Paths are relative to `xania/src/`.

## What persists

Only **players** and a few server files are stored. The world itself isn't. Every boot loads the area files and
resets every area ([World model](03-world-model.md)), so:

- **Lost at every reboot:** objects on the floor, corpses and their contents, mobs' state (HP, wandering
  position, sentient memory), shop stock sold or bought since boot, and door states.
- **Kept:** each player's character, inventory and pet, plus bans, notes and the bug, typo and idea logs.

The server finds its files through three required environment variables
([Configuration.cpp](../../xania/src/common/Configuration.cpp)): `MUD_AREA_DIR`, `MUD_DATA_DIR` and
`MUD_HTML_DIR` (plus `MUD_PORT`, default 9000).

| File | Holds |
|---|---|
| `$MUD_AREA_DIR/area.lst` and the area files | the world (read-only at runtime) |
| `$MUD_AREA_DIR/tipfile.txt` | tips shown to players |
| `$MUD_DATA_DIR/player/<Name>` | one file per player |
| `$MUD_DATA_DIR/gods/<Name>` | a one-line summary (level, trust, title) for each immortal |
| `$MUD_DATA_DIR/system/ban.lst` | permanent bans |
| `$MUD_DATA_DIR/system/notes.txt` | the note board; notes older than two weeks are dropped when it's loaded |
| `$MUD_DATA_DIR/system/bugs.txt`, `typos.txt`, `ideas.txt` | what players report with `bug`, `typo` and `idea` |

## When a character is saved

`save_char_obj` ([save.cpp:883](../../xania/src/save.cpp#L883)) writes the whole player file. It runs on:

- **Autosave.** Each tick (30 s), one player in 30 is saved, chosen by connection number, so everyone is saved
  about every 15 minutes ([update.cpp:815](../../xania/src/update.cpp#L815)).
- `quit` and `save`.
- **Going idle.** After 12 ticks (6 minutes) without input, a player above level 1 is saved and moved to Limbo.
  After 30 idle ticks they're quit, which saves again.
- **Becoming a KILLER** and **changing password.**
- **`reboot` and `shutdown`,** which force everyone to save first
  ([act_wiz.cpp:1115](../../xania/src/act_wiz.cpp#L1115)).

Levelling up and dying don't save; the save on death is commented out
([fight.cpp:1335](../../xania/src/fight.cpp#L1335)). If the server crashes, a player loses everything since their
last autosave, up to about 15 minutes of XP, gold and loot.

## What a player file holds

Player files are plain text with keyword lines (`Name`, `Levl`, `Exp`, `HMV`, `Sk` for each skill and so on;
the full list is in [CharFileMeta.hpp](../../xania/src/CharFileMeta.hpp)). They're versioned (`Vers`, currently 5)
and upgraded on load. A file has these sections:

- `#PLAYER`: stats, skills, affects, flags, title, prompt and the last login.
- `#O`: one per object carried, with a `Nest` level for containers
  ([save.cpp:199](../../xania/src/save.cpp#L199)). An object's names, descriptions, flags and values are written
  only if they differ from its prototype, and its affects only if it's been enchanted. Its **level and cost are
  always written.**
- `#PET`: the player's pet, but only if it's in the same room when the save happens.

**Objects that are never saved** ([save.cpp:199](../../xania/src/save.cpp#L199)):

- anything more than **2 levels above the character** (containers excepted), to stop low-level "storage"
  characters holding high-level gear for others;
- **keys;**
- **unused maps.**

These are silently destroyed at the next save. For balance, a character can't carry a piece of gear far above
their level through a logout, even if a friend handed it to them.

## Immortal levels

Mortals play levels 1–90; **91 is hero**, the top mortal level ([Constants.hpp:19](../../xania/src/Constants.hpp#L19)).
Immortal levels run from 92 to 100, and **trust** can grant an immortal the commands of a higher level without
raising their level.

| Level | Title | Commands gained (cumulative) |
|---|---|---|
| 92 | avatar / immortal | `goto`, `wiznet`, `alist`, `poofin`/`poofout`, `stat`, `mwhere`/`owhere`/`osearch`, `holylight`, `invis`/`wizinvis`, `immtalk`, `memory`, `awaken`, `coma`, `murder` |
| 93 | angel | `force`, `smite` |
| 94 | demigod | `at`, `switch`/`return`, `echo`/`zecho`, `nochannels`, `noemote`, `notell`, `noyell` |
| 95 | immortal | `teleport`, `transfer`, `peace`, `snoop`, `string`, `clone` |
| 96 | god | `load`, `purge`, `restore`, `vnum`, `sockets`, `gecho`/`pecho`, `newlock`, `clanset` |
| 97 | deity | `freeze`, `pardon`, `disconnect`, `slay`, `immworth` |
| 98 | supreme | `ban`, `permban`, `allow`, `permit`, `set`, `wizlock` |
| 99 | creator | `reboot`, `shutdown`, `deny`, `log` |
| 100 | implementor | `advance`, `trust`, `dump`, `sacname` |

The command table is in [InterpreterImpl.cpp](../../xania/src/InterpreterImpl.cpp). Commands such as `reboot`,
`shutdown` and `delete` deliberately have a misspelled short form (`reboo`, `shutdow`, `delet`) that only tells you
to type the whole word.

## Access control

- **Bans** ([Ban.cpp](../../xania/src/Ban.cpp)) match a host exactly, or with `*` as a prefix and/or suffix
  wildcard. Each ban has a type:
    - **all:** nobody from the site;
    - **newbies:** no new characters;
    - **permit:** only characters with the permit flag.

  `ban` lasts until reboot; `permban` writes to `ban.lst`.
- **`wizlock`** shuts out every mortal and **`newlock`** stops new characters. Neither is saved: a reboot unlocks
  the game.
- **`deny`** locks one character out; **`freeze`** stops them typing commands.

## Logging and oversight

- **Always logged:** commands marked to always log, whoever types them
  ([InterpreterImpl.cpp:526](../../xania/src/InterpreterImpl.cpp#L526)):
    - the powerful immortal ones, such as `advance`, `ban`, `force`, `load`, `purge`, `restore`, `set`, `snoop`,
      `switch` and `transfer`;
    - sensitive mortal ones: `delete`, `order`, `outfit` and clan management.

  `log <player>` toggles logging of everything one character types.
- **`wiznet`** streams the game log to immortals by category: logged mortal and immortal commands, ticks, bugs
  and debug messages.
- **`snoop`** shows an immortal everything a player sees.
- The game writes its log, including `bug` messages from the area loader and mob programs, to standard error.
  The [Bugs](versions.md) page reproduces the area-loader checks offline.

## What this means for balance

- **Testing on a live MUD resets the world, not the players.** Changing area files needs a reboot to take
  effect, and players keep everything they're carrying.
- **Rebalancing reaches carried items, except their level and cost.** New dice or affects on a prototype apply to
  every saved copy (unless it's enchanted). A new level or price applies only to copies created after the change:
  existing ones keep the old level, which also decides who can keep them.
- **Item level caps what a character can keep,** at character level + 2, which limits twinking more than the
  wear rules alone do.
- **Crashes cost up to 15 minutes of progress.** The latent crash bugs on the Bugs page matter for players as well
  as uptime.
