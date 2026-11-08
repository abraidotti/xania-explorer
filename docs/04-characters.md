# Characters: races, classes, stats and levelling

How a player character is built and how it grows from level 1 to 91. Paths are relative to `xania/src/`. The
[Characters assessment](versions.md) applies these rules to every race and class.

## Creation

1. **Race and class.** There are 10 PC races and 4 classes. The race sets starting stats
   ([MudImpl.cpp:831](../../xania/src/MudImpl.cpp#L831)), and the creation-point total starts at the race's cost.
2. **Skills.** Every character gets `rom basics` plus its `<class> basics` group free. The player then takes the
   `<class> default` package (40 points) or customises, buying groups and skills at their per-class cost
   ([skills.cpp](../../xania/src/skills.cpp), `group_add`). Points are capped at 200.
3. **XP per level** is fixed at creation from the total points (see below). Spending more on skills makes every
   level dearer.
4. **Entering the game** ([MudImpl.cpp:984](../../xania/src/MudImpl.cpp#L984)):
   - +3 to the class prime stat, except for dragons;
   - 20 HP, 100 mana, 100 move;
   - 3 trains and 5 practices;
   - if points are below 40, extra trains of (40 − points + 1) / 2.

## Classes

From [Class.cpp](../../xania/src/Class.cpp):

| Class | Prime stat | HP roll per level | Mana factor | To-hit AC at level 0 → 32 | Free weapon skill |
|---|---|---|---|---|---|
| mage | int | 6–8 | 10 | −1 → −47 | dagger |
| cleric | wis | 7–10 | 8 | −1 → −51 | mace |
| knight | str | 10–14 | 6 | −1 → −61 | sword |
| barbarian | con | 13–17 | 3 | −1 → −63 | axe |

- **To-hit AC** is interpolated by level and drives the chance to hit (see the combat guide).
- **Skill adept** is 75% for every class. That's the most practising can teach; using a skill can improve it
  further.

## Races

From `pc_race_table` in [Races.cpp:147](../../xania/src/Races.cpp#L147). Each race has:
- a creation-point cost;
- an XP multiplier for each class;
- up to 5 bonus skills;
- base and maximum stats;
- a body size.

The table is listed on the Characters page. Bonus skills are cheaper to learn: difficulty −1 and available by level
30 at the latest ([skills.cpp:566](../../xania/src/skills.cpp#L566)).

Race also merges NPC-style flags: elves resist charm and are vulnerable to iron, dwarves resist poison and disease,
and so on ([Races.cpp](../../xania/src/Races.cpp), `race_table`).

## XP per level

`exp_per_level(points)` ([skills.cpp:259](../../xania/src/skills.cpp#L259)) works like this:
- Below 40 points: 1000 × class multiplier.
- From 40 points: start at 1000. The next 10 points add 500, the 10 after that add 500 more, and the step then
  doubles for every following pair of 10s. Partial tens add pro rata.
- The result is multiplied by the race's class multiplier and capped at 65,500.

A character levels when `exp ≥ exp_per_level × (level + 1)` ([update.cpp:586](../../xania/src/update.cpp#L586)).
Every level costs the same, and reaching 91 takes 90 × that.

| Points | XP per level (×1.00) |
|---|---|
| 40 (human, default) | 1,000 |
| 45 (elf, dwarf) | 1,250 |
| 50 (eagle, orc) | 1,500 |
| 55 (minotaur, half-elf) | 1,750 |
| 60 (hobbit, wolf) | 2,000 |
| 80 (dragon) | 4,000 |

## Stats

Five stats, each from 3 to 25. Their effects come from the bonus tables in [Stats.cpp](../../xania/src/Stats.cpp):

| Stat | Effect |
|---|---|
| str | `str_app`: hitroll and damroll bonus ([Char.cpp:439](../../xania/src/Char.cpp#L439)), carry weight ([handler.cpp:156](../../xania/src/handler.cpp#L156)), heaviest weapon you can wield ([handler.cpp:175](../../xania/src/handler.cpp#L175)) |
| int | `int_app.learn`: practice gain ([act_info.cpp:1604](../../xania/src/act_info.cpp#L1604)) and learn-by-use chance; mana gain above 15 |
| wis | `wis_app`: practices per level; mana gain above 15 |
| dex | `dex_app.defensive`: added to AC while awake ([Char.cpp:200](../../xania/src/Char.cpp#L200)); movement gain |
| con | `con_app.hitp`: HP bonus per level; movement gain; HP regeneration ([update.cpp:336](../../xania/src/update.cpp#L336)) |

Limits:
- **Trainable maximum:** the race maximum, +2 for the prime stat, capped at 25
  ([handler.cpp:117](../../xania/src/handler.cpp#L117)).
- **Effective maximum with spells and items:** the race maximum +4, or +6 for the prime stat
  ([Char.cpp:192](../../xania/src/Char.cpp#L192)).

## Levelling up

`advance_level` ([update.cpp:480](../../xania/src/update.cpp#L480)) runs once per level gained:

- **HP:** `(con_app.hitp + random(class min..max)) × 9 / 10`, at least 1.
- **Mana:** `random(0 .. factor² × (max(0, wis−15) + 2·max(0, int−15)))`, then `(that + 150) / 300 + factor / 2`.
  So below 16 int and wis a mage gains a flat 5 mana and a barbarian 1.
- **Move:** `random(1 .. (con + dex) / 6) × 9 / 10`, at least 6.
- **Practices:** `wis_app.practice`.
- **Trains:** +1. A train buys +1 to a stat (up to its trainable maximum), +10 HP or +10 mana
  ([act_move.cpp:1020](../../xania/src/act_move.cpp#L1020)).

## Practising skills

Practising at a guild ([act_info.cpp:1561](../../xania/src/act_info.cpp#L1561)) costs a practice. It raises the skill
by `int_app.learn / difficulty`, where difficulty is the class's rating for that skill, up to the 75% adept limit.
Beyond that, skills improve only through use ([Learning.cpp](../../xania/src/Learning.cpp)).
