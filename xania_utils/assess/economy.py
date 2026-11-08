"""Economy: gold earned against what gold can buy, from level 1 to 91.

Income per kill = the mob's gold (create_mobile rolls gold/2 … 3·gold/2, mean = gold) + sacrificing its
corpse (2 gold per mob level, act_obj.cpp do_sacrifice). Gold per level = income per kill × kills per
level (Combat). Selling loot to shops isn't counted (floor items are worth 0; drops sell at the shop's
sell %, if it trades that type).

Spending: shop stock (price = cost × the shop's buy %, act_obj.cpp get_cost) and the healer's flat
price list (healer.cpp).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..areafile.world import World
from . import combat as CB
from . import common as C
from . import equipment as E
from . import weapons as W
from .sources import object_sources

# healer.cpp: flat prices, whatever your level
HEALER = {"cure light": 1000, "cure serious": 1600, "cure critical": 2500, "heal": 5000, "cure blindness": 2000,
          "cure disease": 1500, "cure poison": 2500, "remove curse": 5000, "refresh": 500, "restore mana": 1000}
SACRIFICE_PER_LEVEL = 2
OUTLIER = 5.0  # mob gold above 5× the local median


@dataclass
class ShopItem:
    vnum: int
    name: str
    type: str
    level: int
    price: int
    keeper: int
    area: str
    ac: float = 0.0
    slots: tuple[str, ...] = ()
    weapon_avg: float | None = None


class EconomyAnalysis:
    def __init__(self, world: World):
        self.world = world
        self.combat = CB.analyse(world)
        shops = {s.keeper: s for f in world.files for s in f.shops}
        gear = {i.vnum: i for i in E.collect(world)}
        weapons = {w.vnum: w for w in W.collect(world)}
        self.stock: list[ShopItem] = []
        for vnum, srcs in object_sources(world).items():
            for s in srcs:
                if s.kind != "shop" or s.mob_vnum not in shops or vnum not in world.objects:
                    continue
                o = world.objects[vnum]
                g = gear.get(vnum)
                w = weapons.get(vnum)
                self.stock.append(ShopItem(vnum, o.short_descr, o.type_name, C.usable_level(o.level),
                                           o.cost * shops[s.mob_vnum].profit_buy // 100, s.mob_vnum, s.area,
                                           g.ac if g else 0.0, tuple(g.slots) if g else (),
                                           w.average if w else None))
        self.stock.sort(key=lambda i: (i.level, i.price, i.vnum))
        self.gold_per_kill = {lvl: self._gold_per_kill(lvl) for lvl in C.LEVELS}
        self.gold_per_level = {lvl: (self.gold_per_kill[lvl] or 0) * (self._kills(lvl) or 0) for lvl in C.LEVELS}
        running, self.cumulative = 0.0, {}
        for lvl in C.LEVELS:
            running += self.gold_per_level[lvl]
            self.cumulative[lvl] = running

    def _kills(self, level: int) -> float | None:
        return self.combat.results[("knight", level)].kills_per_level

    def _gold_per_kill(self, level: int) -> float | None:
        fights = self.combat.results[("knight", level)].fights
        weight = sum(m.info.population for m, _ in fights)
        if not weight:
            return None
        return sum((m.mob.gold + SACRIFICE_PER_LEVEL * m.mob.level) * m.info.population for m, _ in fights) / weight

    # -- spending -----------------------------------------------------------------------
    def shop_kit(self, level: int) -> tuple[float, int]:
        """Best-AC shop item per slot (two for neck/wrist/finger): (total AC, total price)."""
        ac = price = 0
        for slot, count in E.SLOTS.items():
            items = [i for i in self.stock if slot in i.slots and i.level <= level and i.ac > 0]
            if items:
                best = max(items, key=lambda i: (i.ac, -i.price))
                ac += best.ac * count
                price += best.price * count
        return ac, price

    def best_shop_weapon(self, level: int) -> ShopItem | None:
        items = [i for i in self.stock if i.weapon_avg and i.level <= level]
        return max(items, key=lambda i: (i.weapon_avg, -i.price)) if items else None

    @property
    def last_stock_level(self) -> int:
        return max((i.level for i in self.stock if i.slots or i.weapon_avg), default=0)

    def kills_to_afford(self, price: int, level: int) -> float | None:
        g = self.gold_per_kill[level]
        return price / g if g else None

    # -- mob gold outliers ----------------------------------------------------------------
    def gold_outliers(self) -> list[tuple[float, CB.MobFighter, float]]:
        out = []
        for m in self.combat.mobs:
            lvl = C.usable_level(m.mob.level)
            local = C.median_or(x.mob.gold for x in self.combat.by_level[lvl])
            if local and m.mob.gold > OUTLIER * local and m.mob.gold > 100:
                out.append((m.mob.gold / local, m, local))
        return sorted(out, key=lambda t: (-t[0], t[1].mob.vnum))

    # -- tables ------------------------------------------------------------------------------
    def band_table(self) -> str:
        rows = []
        for b in C.bands():
            lvl = b.hi
            ac, price = self.shop_kit(lvl)
            weapon = self.best_shop_weapon(lvl)
            rows.append([b.label, round(self.gold_per_kill[lvl] or 0), round(self.gold_per_level[lvl]),
                         f"{self.cumulative[lvl]:,.0f}", round(ac), f"{price:,}",
                         f"{weapon.name} ({weapon.price:,})" if weapon else None,
                         _r(self.kills_to_afford(HEALER['heal'], lvl))])
        return C.table(["Levels (at top level)", "gold/kill", "gold/level", "gold earned so far", "shop kit AC",
                        "shop kit price", "best shop weapon", "kills per 'heal'"], rows)

    def stock_table(self) -> str:
        return C.table(["Vnum", "Item", "Type", "Lvl", "Price", "Shop area", "AC", "Weapon avg"],
                       [[i.vnum, i.name, i.type, i.level, i.price, i.area, i.ac or None, i.weapon_avg]
                        for i in self.stock])

    def outlier_table(self) -> str:
        return C.table(["Vnum", "Mob", "Area", "Lvl", "Gold", "× local median", "Population"],
                       [[m.mob.vnum, m.mob.short_descr, m.info.area.name, m.mob.level, m.mob.gold, round(r, 1),
                         m.info.population] for r, m, _ in self.gold_outliers()])

    def healer_table(self) -> str:
        return C.table(["Service", "Price"] + [f"kills at {lvl}" for lvl in (5, 20, 50, 90)],
                       [[k, v] + [_r(self.kills_to_afford(v, lvl)) for lvl in (5, 20, 50, 90)]
                        for k, v in HEALER.items()])

    def method(self) -> str:
        return __doc__.split("\n\n", 1)[1].strip() + (
            "\n\n- Kills per level and the mobs fought are those of the Combat model (human, ±2 levels).\n"
            "- **Shop kit**: the best-AC item per slot that shops sell at or below the level; its price is what "
            "it would cost to buy it all at once.\n"
            f"- **Mob gold outliers**: combat mobs carrying more than {OUTLIER:g}× the median gold of mobs within "
            "±2 levels (and more than 100).\n")


def _r(v):
    return None if v is None else round(v, 1)


def analyse(world: World) -> EconomyAnalysis:
    return C.cached(world, "economy", EconomyAnalysis)


def render(world: World) -> str:
    a = analyse(world)
    out = [C.GENERATED_NOTE, "\n# Economy by level\n\n", "## Headline findings\n\n",
           f"- **Gold earned by level {C.HERO_LEVEL}**: about {a.cumulative[C.HERO_LEVEL]:,.0f} from kills and "
           "sacrifices.\n",
           f"- **Shops** stock gear up to level {a.last_stock_level}; {len(a.stock)} items in all.\n",
           f"- **Mob gold outliers**: {len(a.gold_outliers())}.\n",
           "\n## Method\n\n" + a.method(), "\n## 1. By level band\n\n" + a.band_table(),
           "\n## 2. Healer\n\n" + a.healer_table(), "\n## 3. Mob gold outliers\n\n" + a.outlier_table(),
           "\n## 4. Shop stock\n\n" + a.stock_table()]
    return "".join(out)


def write_csv(world: World, path: Path) -> None:
    a = analyse(world)
    rows = []
    for lvl in C.LEVELS:
        ac, price = a.shop_kit(lvl)
        w = a.best_shop_weapon(lvl)
        rows.append([lvl, _r(a.gold_per_kill[lvl]), _r(a.gold_per_level[lvl]), round(a.cumulative[lvl]), round(ac),
                     price, w.name if w else "", w.price if w else "", _r(a.kills_to_afford(HEALER["heal"], lvl))])
    C.write_csv(path, ["level", "gold_per_kill", "gold_per_level", "gold_earned_total", "shop_kit_ac",
                       "shop_kit_price", "best_shop_weapon", "best_shop_weapon_price", "kills_per_heal"], rows)
