# Architecture and game loop

How the Xania server is put together and how time passes in the game. Paths are relative to `xania/src/`.

## Two processes

| Process | Source | Job |
|---|---|---|
| **doorman** | [doorman/](../../xania/src/doorman/) | Owns the telnet port (`MUD_PORT`, default 9000). Handles telnet negotiation ([TelnetProtocol.cpp](../../xania/src/doorman/TelnetProtocol.cpp)), DNS and connection channels. Survives xania restarts, so players stay connected across a `reboot`. |
| **xania** | everything else | The game. Talks to doorman over a Unix socket (`/tmp/.xania-{port}-{user}`) using fixed packets ([doorman_protocol.h](../../xania/src/common/doorman_protocol.h)): INIT, CONNECT, DISCONNECT(_ACK), RECONNECT, MESSAGE, INFO (ip, port, ansi, hostname), ECHO_ON/OFF, AUTHORIZED, GO_AHEAD. |

The [apps/](../../xania/src/apps/) directory has offline tools that link the game code: `areas` (a DOT graph of how
areas connect), `map` (a DOT map of rooms) and `pfu` (a player-file upgrader). Both DOT tools print part of their
output to stdout instead of the output file.

## Configuration

Read from environment variables ([Configuration.cpp](../../xania/src/common/Configuration.cpp)). The defaults are
in [mud-settings-dev.sh](../../xania/mud-settings-dev.sh).

| Variable | Used for |
|---|---|
| `MUD_AREA_DIR` | `area.lst`, the `.are` and `.prg` files, `tipfile.txt` |
| `MUD_DATA_DIR` | `player/` (player files), `gods/`, `system/` (`ban.lst`, `notes.txt`, `bugs.txt`, `typos.txt`, `ideas.txt`) |
| `MUD_HTML_DIR` | static and generated web pages |
| `MUD_PORT` | doorman listen port |

## Boot

[main.cpp](../../xania/src/main.cpp) runs these steps in order:

1. `init_socket`
2. `boot_db` ([db.cpp:190](../../xania/src/db.cpp#L190)):
   - assign `gsn_*` skill numbers;
   - load every area file in `area.lst` order (see the [area format spec](02-area-file-format.md));
   - resolve exits (`map_exit_destinations`);
   - sort the areas;
   - **reset every area once** (`area_update`; each area starts at maximum age);
   - set up wiznet.
3. `MudImpl::boot`: load tips, bans and notes.
4. `game_loop`.

## The game loop

[MudImpl.cpp:180](../../xania/src/MudImpl.cpp#L180). Each iteration is one **pulse**, and the loop sleeps until the
next quarter-second (`PULSE_PER_SECOND = 4`, [Constants.hpp](../../xania/src/Constants.hpp)). Each pulse:

1. Read input from doorman.
2. For each connection: decrement the character's `wait` (lag). If the wait is zero, run one queued command:
   pager, `interpret` ([InterpreterImpl.cpp](../../xania/src/InterpreterImpl.cpp)), or `nanny` for login and
   character creation.
3. `update_handler` ([update.cpp:856](../../xania/src/update.cpp#L856)), described below.
4. Flush output. If output fails, a character above level 1 is saved and disconnected.

**One command per pulse.** Skills add lag through `wait` (in pulses; each skill's `beats` value in the skill
table). That lag is the main limit on how fast actions can happen.

### Update timers

| Timer | Period | Function | What it does |
|---|---|---|---|
| area | random 30–90 s (`PULSE_AREA` = 60 s, ±50%) | `area_update` → `Area::update` | Ages each area and resets it when it's old enough (see [world model](03-world-model.md#resets)) |
| mobile | 4 s | `mobile_update` ([update.cpp:242](../../xania/src/update.cpp#L242)) | Special functions, mobprog random triggers, scavenging, wandering |
| violence | 3 s | `violence_update` ([fight.cpp:102](../../xania/src/fight.cpp#L102)) | One combat round for everyone who's fighting (`multi_hit`) |
| tick ("point") | 30 s | `char_update`, `obj_update`, `weather_update`, `count_update`, tips | HP/mana/move regen (`hit_gain` etc.), hunger and thirst, affects wearing off, idle players moved to limbo, object decay, game time and weather |
| every pulse | 0.25 s | `aggr_update` ([update.cpp:196](../../xania/src/update.cpp#L196)) | Aggressive mobs attack visible players |
| every pulse | 0.25 s | `collect_all_garbage` | Frees extracted characters and objects |

A combat round (3 s) is therefore 12 pulses, and a tick (30 s) is 10 rounds.

## Level bands

[Constants.hpp](../../xania/src/Constants.hpp): `MAX_LEVEL` = 100, hero = 91. Levels 92 and up are immortal ranks
(Avatar 92, Angel 93, Demi 94, Immortal 95, God 96, Deity 97, Supreme 98, Creator 99, Implementor 100).

Mobs can be above 100: Dell's priest is level 112.

## Code map for balance work

| Topic | Where |
|---|---|
| Classes | [Class.cpp](../../xania/src/Class.cpp): 4 classes with prime stat, to-hit at level 0 and 32, HP/mana gain |
| Races | [Races.cpp](../../xania/src/Races.cpp): PC and NPC races with flags and tolerances |
| Stats | [Stats.cpp](../../xania/src/Stats.cpp): str/int/wis/dex/con bonus tables |
| Skills and spells | [SkillTables.cpp](../../xania/src/SkillTables.cpp) (per-class level and practice cost), [magic.cpp](../../xania/src/magic.cpp), [skills.cpp](../../xania/src/skills.cpp), [Learning.cpp](../../xania/src/Learning.cpp) |
| Combat | [fight.cpp](../../xania/src/fight.cpp), [HitChance.cpp](../../xania/src/HitChance.cpp), [DamageTolerance.cpp](../../xania/src/DamageTolerance.cpp) |
| Experience and levelling | `xp_compute` ([fight.cpp:1389](../../xania/src/fight.cpp#L1389)), `advance_level` ([update.cpp:480](../../xania/src/update.cpp#L480)) |
| Regen | `hit_gain`, `mana_gain`, `move_gain` ([update.cpp:319](../../xania/src/update.cpp#L319)) |
| Item balance rule | [entity_balance.cpp](../../xania/src/entity_balance.cpp) (`immworth`) |
| NPC behaviour | [special.cpp](../../xania/src/special.cpp), [MProgImpl.cpp](../../xania/src/MProgImpl.cpp), `mobile_update` |
| Saving | [save.cpp](../../xania/src/save.cpp) (player file format) |
