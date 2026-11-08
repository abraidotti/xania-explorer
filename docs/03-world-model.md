# World model

How the world is put together at runtime. The file syntax is in the [area format spec](02-area-file-format.md),
and the per-area numbers are in the generated area catalogue (see [Xania versions](versions.md)).

## Prototypes and instances

Area files define **prototypes**: `MobIndexData` and `ObjectIndex`, keyed by vnum. Resets create **instances**
(`Char` via `create_mobile`, and `Object`) from those prototypes. When an instance is created:

- **Mobs** ([db.cpp:1034](../../xania/src/db.cpp#L1034)) roll HP from the hit dice, get race flags merged in, and
  get NPCs' stat adjustments by size ([BodySize.cpp](../../xania/src/BodySize.cpp): bigger than medium gets bonus
  str/con).
- **Objects** copy their prototype values. Objects created by an `O` reset (lying on the floor) get **cost 0**.
- Each prototype keeps a live `count` of its instances. `M` and `P` resets use this to cap how many exist in the
  world.

## Areas

An area is a header plus a vnum range ([Area.hpp](../../xania/src/Area.hpp)). It owns its rooms only through that
range: `Area::reset()` walks `lowest..highest` vnum and resets every room it finds there. The range is the declared
one widened by the area's mob and object vnums, but not its room vnums.

`area.lst` currently loads 72 areas plus 6 header-less help/social/version files.

## Rooms and exits

- There are six directions: north, east, south, west, up, down. Each room has at most one exit per direction.
- An exit has a destination, a door state (`locks` in the file, turned into `IsDoor`/`PickProof`/`PassProof`
  flags), a key vnum, keywords and a description.
- **Door state** is stored twice. `rs_flags` is the reset state, set from the file's `locks` code plus any `D`
  resets. `exit_info` is the live state. Every room reset copies `rs_flags` into `exit_info`, for both sides of the
  door.
- **One-way exits** have a negative destination in the file. **Cosmetic exits** (`-1`) lead nowhere.
- Two-way exits are expected to be symmetric. The loader logs a `Fix_exits` bug otherwise
  ([db.cpp:804](../../xania/src/db.cpp#L804)).
- Rooms with no exit leading anywhere get `NoMob`.
- Rooms 3000–3399 (Midgaard) always get `Law`.
- Important vnums ([VnumRooms.hpp](../../xania/src/VnumRooms.hpp)): Limbo 2, Chat 1200, Midgaard temple 3001 (where
  you recall to), altar 3054, Mud School entrance 3700.

## Resets

The area clock ([Area.cpp:74](../../xania/src/Area.cpp#L74), [db.cpp:821](../../xania/src/db.cpp#L821)):

- An **area pulse** fires every 30–90 s (random, re-rolled each time). Each pulse adds 1 to every area's `age`.
- An area resets when `age >= 15`. If it was empty at its last reset and nobody has entered since, the threshold
  is `age >= 10`. After a reset, `age` is set to a random 0–3. So an area that stays empty resets every 7–10 area
  pulses (~3.5–15 min), and one that's had players in it every 12–15 (~6–22 min). An area is flagged "empty" at
  reset time if no players are in it. The flag clears (and
  `age` drops to 0) when a player enters, so stepping in and out doesn't speed up resets.
- **Mud School** (the area containing room 3700) has its `age` set to 10 after each reset and is never flagged
  empty. By this reading it resets every ~5 area pulses (~2.5–7.5 min). The comment in Area.cpp claims 1–2
  minutes, which doesn't match.
- Booting resets every area once.

Within a reset, rooms are processed in vnum order. Each room runs its reset list in file order: `M` spawns a mob,
and the `G`/`E` lines after it equip that mob. Key rules (full table in the
[spec](02-area-file-format.md) (§7)):

- `M` caps the mob at arg2 in the world and arg4 in the room.
- `O` and `P` are **skipped while any player is in the area**. Floor loot and container contents only refresh in
  empty areas.
- A `G`/`E` drop rate (arg2) is a percent chance for normal mobs. Shopkeepers always get the item, as stock.
- Pet-shop rule: a mob reset in the room *after* a `PetShop` room becomes a pet.

## Shops, specials, mob programs

- **Shops** attach to the keeper's mob prototype. They have buy types (object type numbers), profit
  percentages for buying and selling, and opening hours in game time.
- **Specials** attach a C++ behaviour function (`spec_*` in [special.cpp](../../xania/src/special.cpp)) to a mob.
  It runs on the mobile timer (every 4 s).
- **Mob programs** are scripted triggers from `.prg` files. Currently 12 files are used by 29 mobs
  ([MProgImpl.cpp](../../xania/src/MProgImpl.cpp)).

What specials and programs do, and how mobs aggress, assist, flee and wander, is in
[NPC behaviour](08-npc-behaviour.md).

## Inspecting the world from Python

```python
from xania_explorer.areafile.world import load_world
w = load_world()                      # ../xania/area by default
w.mobs[12100].hit.average             # 7601.0
w.area_named("Dell.are").linked_areas # {'Plains of the North'}
[p for p in w.problems]               # load-integrity problems
```
