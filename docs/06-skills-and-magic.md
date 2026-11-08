# Skills and magic

How characters acquire and improve skills and spells, and how casting works. Paths are relative to `xania/src/`.
The [Skills & spells assessment](versions.md) applies these rules across levels 1–91.

## The skill table

`skill_table` ([SkillTables.cpp](../../xania/src/SkillTables.cpp)) lists every skill and spell. Each has:
- **level per class:** the level at which that class can learn it;
- **rating per class:** the cost in creation points or trains, and the *difficulty* used when practising and
  learning by use;
- **minimum mana** and **beats** (lag after use, in quarter-second pulses);
- a **slot number:** area files refer to spells by slot (scrolls, potions and so on), so slots must never change.

Special ratings:
- **0:** the class can never learn the skill.
- **−1 (cross-class):** learnable from level 60 at difficulty 8.
- **−2 (assassin):** learnable at 30 with the assassin group, otherwise 60, at difficulty 5.

A race's bonus skills are capped at level 30 and are one difficulty step easier ([skills.cpp:566](../../xania/src/skills.cpp#L566)).

## Getting skills

Groups (`group_table`) bundle skills. At creation a character takes `rom basics`, its class basics, and either
its class default package or a custom set. You can only practise skills you already know (at least 1%). Anything
else must be bought later with trains through `gain` ([skills.cpp:195](../../xania/src/skills.cpp#L195)).

## Improving skills

- **Practising** at a guild ([act_info.cpp:1561](../../xania/src/act_info.cpp#L1561)) costs a practice and adds
  `int_app.learn / difficulty`, up to the class's adept limit (75%).
- **Using** a skill can improve it further, up to 100% (`check_improve`, [Learning.cpp](../../xania/src/Learning.cpp)).
  The chance depends on int, difficulty and level. A failed use can teach you more (1–3 points) than a success (1).
  Each improvement gives `2 × difficulty` XP.
- **Mobs** don't learn. Their skills come from their level and flags ([Char.cpp:213](../../xania/src/Char.cpp#L213)).

## Casting

`do_cast` ([magic.cpp](../../xania/src/magic.cpp)):

1. **Mana cost** = `max(min_mana, 100 / (2 + level − level learned))` ([magic.cpp:582](../../xania/src/magic.cpp#L582)).
   New spells are expensive and get cheap as you out-level them.
2. **Lag:** the caster waits the spell's beats (12 pulses = 3 s for most attack spells).
3. **Success:** the cast fails if d100 exceeds your skill %. A failure costs half the mana.
4. **Saving throws:** the victim saves with chance `50 + victim level − caster level − saving throw`, clamped
   to 5–95% (`saves_spell`, [magic.cpp:546](../../xania/src/magic.cpp#L546)).

**Direct-damage spells** mostly roll `random(table[level] / 2, table[level] × 2)` from a per-level table in
magic.cpp (`get_direct_dmg_and_level`) and halve it on a save. Several spells share a table:
- acid blast, demonfire and exorcise;
- fireball and harm;
- lightning bolt, chain lightning and cause critical;
- burning hands and cause serious;
- magic missile and cause light;
- colour spray, dispel evil and dispel good.

The exceptions roll dice: call lightning `dice(level/2, 8)` and energy drain `dice(1, level)`. Breath weapons
scale with the caster's HP.

Spell damage goes through `damage()` like melee, so sanctuary, resistances and vulnerabilities apply. Parry,
dodge and shield block don't.
