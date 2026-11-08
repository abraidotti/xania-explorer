# Combat and experience

How a melee round is resolved, and how kills turn into experience. Paths are relative to `xania/src/`. The
[Combat & XP assessment](versions.md) applies these formulas across levels 1–91.

## The round

Every 3 seconds (`PULSE_VIOLENCE`), `violence_update` ([fight.cpp:102](../../xania/src/fight.cpp#L102)) calls
`multi_hit` once for each fighter.

**Player attacks per round** ([fight.cpp:239](../../xania/src/fight.cpp#L239)):

| Attack | When |
|---|---|
| 1st | always |
| extra | if hasted (and not lethargic) |
| 2nd | chance = second attack skill / 2 % |
| 3rd | chance = third attack skill / 4 % |

Backstab is a single blow.

**Mob attacks per round** (`mob_hit`, [fight.cpp:292](../../xania/src/fight.cpp#L292)):
- **1st:** always. Mobs with the Backstab flag can open with a backstab on an unhurt victim.
- **Extra:** if the mob is hasted or Fast.
- **Area attack:** a mob with AreaAttack also swings at everyone else fighting it.
- **2nd:** warrior or thief mobs only, at skill `max(25, level/2)`.
- **3rd:** warriors only, at skill `level − 30`, and only if the 2nd landed.
- **One special move:** chosen at random from its offensive flags (bash, berserk, disarm, kick, dirt kick, trip).

## Hitting

`HitChance` ([HitChance.cpp](../../xania/src/HitChance.cpp)):

1. **The attacker's to-hit AC** = `interpolate(level, AC₀, AC₃₂) × weapon skill % − hitroll`:
   - `interpolate` is linear and keeps going past level 32 ([db.cpp:1676](../../xania/src/db.cpp#L1676));
   - AC₀ and AC₃₂ come from the class (Characters) or, for mobs, from the class flag: warrior −76, thief −70,
     cleric −66, mage −63, default thief.
2. **Penalties:** the to-hit AC is ×0.8 if the attacker can't see. Backstab subtracts `skill/3` (an improvement).
3. **The victim's AC:** the armour value for the damage type (pierce, bash, slash or exotic), plus the dex
   bonus while awake. It's ×0.8 if the victim is sleeping or stunned, ×0.9 if resting or sitting.
4. **Chance** = both values made positive (minimum 1), as a ratio of attack to defence, **clamped to 10–95%**.
   A d100 roll below it hits.

**Defences.** Each is checked against a hit before damage ([fight.cpp:1061](../../xania/src/fight.cpp#L1061)):

| Defence | Needs | Chance |
|---|---|---|
| parry | the defender wields a weapon | `skill/3 + level difference` |
| dodge | — | `skill/3 + dex difference + level difference` |
| shield block | the defender wears a shield | `skill/3 + level difference` |

Each has a minimum of 5%. Whips can't be parried or blocked.

**Mob defensive skill** = `15 + level/2` for warriors and thieves, `level/3` for others
([Char.cpp:213](../../xania/src/Char.cpp#L213)).

## Damage

`one_hit` ([fight.cpp:410](../../xania/src/fight.cpp#L410)) then `damage` ([fight.cpp:586](../../xania/src/fight.cpp#L586)):

1. **Base damage** depends on what the attacker is holding:

   | Attacker | Base damage |
   |---|---|
   | armed | weapon dice × weapon skill % |
   | unarmed mob | its damage dice. The dice bonus became its damroll ([db.cpp:1062](../../xania/src/db.cpp#L1062)) |
   | unarmed player | `random(1 + 4·skill/100, 2·level/3 · skill/100)` |

2. **Weapon effects** on that base:
   - sharp: ×2 on 2% of hits;
   - vorpal: ×1.3 when the dice roll exactly their average;
   - no shield worn: ×1.05.
3. **Enhanced damage:** roll d100; if it's ≤ skill, add damage × roll / 100.
4. **The victim's position:** ×2 if asleep or stunned, ×1.5 if resting.
5. **Backstab:** ×(2 + level/10), or level/8 for daggers.
6. **Damroll:** add `damroll × min(100, skill) / 100`. Damage is at least 1 and capped at 1,000.
7. **Adjustments in `damage`:**
   - octarine fire: +level/8 %;
   - **sanctuary: ÷1.6**;
   - protection from evil or good: −25%;
   - parry, dodge or block can cancel the hit outright;
   - immune: 0, resistant: −⅓, vulnerable: +½;
   - material vulnerability (e.g. iron against elves): +½.
8. **On-hit effects:** poisoned and plagued weapons cast their spell on 25% of hits.

## Mob stats

`create_mobile` ([db.cpp:1034](../../xania/src/db.cpp#L1034)):
- **HP:** rolled from the hit dice.
- **Stats:** all `min(25, 11 + level/4)`, adjusted for class and size (+3 str and +2 con for warriors, +3 dex for
  thieves, and so on).
- **AC** from the area file.
- **Skills** from their level (see above). Weapon skill is `40 + 5·level/2` armed and `40 + 2·level` unarmed.
- **Gold:** `random(gold/2, 3·gold/2)`.

## Experience

`group_gain` and `xp_compute` ([fight.cpp:1338](../../xania/src/fight.cpp#L1338)):

1. **Base XP from the level gap** (victim − killer):

   | Gap | ≤ −10 | −5 | −2 | 0 | +2 | +4 | above +4 |
   |---|---|---|---|---|---|---|---|
   | XP | 0 | 11 | 55 | 85 | 120 | 160 | 150 + 20 per level above 4 |

   In a group, the highest member's level counts.
2. **Alignment:** the killer's alignment drifts toward the opposite of the victim's. XP is then ×0.75–1.25
   depending on both alignments (neutrals get ×1.25 for strongly good or evil victims).
3. **Low and high levels:**
   - below level 6: ×10 / (level + 4);
   - levels 36–69: ÷(1 + level/300);
   - levels 70+: ÷(1 + level/250), which is −36% at 91.
4. **The played-time clock:** quarter-hours played per level, clamped to 2–6, ÷6. **Full XP needs an average of
   1.5 hours played per level**; faster players get as little as a third. Below level 15 the floor is
   `8 − level`, so levels 1–2 always get full credit.
5. **Randomness and grouping:** ±25% random, then × your share of the group's levels × 1.5 (so ×1.5 solo).
6. **Levelling:** `gain_exp` advances a level each time XP passes `exp_per_level × (level + 1)` (see Characters).
   Heroes (91) stop gaining.
