# Items and economy

How objects become equipment, what keeps them balanced, and how gold moves. Paths are relative to `xania/src/`.
The [Weapons, Equipment and Economy assessments](versions.md) apply these rules across levels 1–91.

## Wearing things

- **Level:** you can't wear or wield an object above your level ([act_obj.cpp:137](../../xania/src/act_obj.cpp#L137)).
- **No class restrictions:** any class can wear anything.
- **Alignment flags:** items with AntiGood, AntiEvil or AntiNeutral "zap" a wearer of that alignment off when
  they next gain XP ([fight.cpp](../../xania/src/fight.cpp), `group_gain`).
- **Wear slots** ([Worn.hpp](../../xania/src/Worn.hpp)): light, two fingers, two necks, body, head, legs, feet,
  hands, arms, shield, about, waist, two wrists, wield, hold and ears.
- **Weapons:** two-handed weapons rule out a shield. Your strength limits the heaviest weapon you can wield
  ([handler.cpp:175](../../xania/src/handler.cpp#L175)).
- **Armour class:** armour objects subtract their four AC values (pierce, bash, slash, exotic) from your AC in
  any armour slot (`apply_ac`, [handler.cpp:363](../../xania/src/handler.cpp#L363)). `Ac` affects on any item
  change it further. A character starts at AC 0, so gear and dex are all the protection there is.

## The item-points rule

`report_object` ([entity_balance.cpp](../../xania/src/entity_balance.cpp)) is the builders' balance check,
reported by the immortal command `immworth`:

| Bonus | Points |
|---|---|
| +1 to a stat | 1 |
| +1 hitroll or damroll | 1 (½ on weapons) |
| +7 HP, mana or move | 1 |
| flaming, frost, vampiric, sharp or vorpal | 1 each |
| AC or saving throws | *meant to be* 1 per −1, but never counted (bug below) |

- **Allowance:** an item may carry `level/10 + 1` points.
- **Weapon damage:** a weapon's average damage, `(n·s + n) / 2`, may not exceed `level/2 + 4`, plus 5% for
  two-handers.
- **The bug:** in `AFFECT_DATA::worth` ([AFFECT_DATA.cpp:86](../../xania/src/AFFECT_DATA.cpp#L86)) the AC and
  saving-throw case reads `if (modifier < 0) if (modifier > 0)`, which is never true. So these bonuses are free.

## Where items come from

Resets place every object in the world (see the [area format](02-area-file-format.md)):
- **Shop stock:** items given to a shopkeeper, always present.
- **Mob drops:** items given to or worn by a mob, spawned with a drop chance from 1 to 100%.
- **Floor and container items:** these refresh only when the area is empty, and **floor items have cost 0**, so
  they can't be sold.

## Gold in

- **Mobs:** each instance carries `random(gold/2, 3·gold/2)` of its prototype's gold
  ([db.cpp:1034](../../xania/src/db.cpp#L1034)). Autogold loots it from the corpse.
- **Sacrifice:** sacrificing a corpse gives `max(1, 2 × level)` gold. Other objects give that much capped at
  their cost ([act_obj.cpp:1435](../../xania/src/act_obj.cpp#L1435)).
- **Money** objects on the floor or in containers.
- **Selling** to a shop that trades the item's type pays `cost × sell %`. A shop that already stocks the item
  pays nothing ([act_obj.cpp:481](../../xania/src/act_obj.cpp#L481)).

## Gold out

- **Shops** charge `cost × buy %`. Wands and staves scale with their remaining charges.
- **The healer** charges flat prices whatever your level ([healer.cpp](../../xania/src/healer.cpp)): cure light
  1,000, serious 1,600, critical 2,500, heal 5,000, blindness 2,000, disease 1,500, poison 2,500, remove curse
  5,000, refresh 500, mana 1,000.
- **Pets** from pet shops, and giving gold to other players.
