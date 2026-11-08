"""Economy page."""

from __future__ import annotations

from collections import Counter

from ...areafile.world import World
from ...assess import common as C
from ...assess import economy as EC
from ...assess import equipment as E
from .. import charts as V
from .common import HIGHLIGHT, MUTED, _list


def economy_page(world: World) -> str:
    a = EC.analyse(world)
    total = a.cumulative[C.HERO_LEVEL]
    out = ["# Economy by level\n\n",
           "Gold earned from kills against what gold can buy, from level 1 to 91: shop gear, the healer, and where "
           "the money ends up.\n",
           V.stat_tiles([
               (f"{total / 1e6:.1f}M", f"gold earned by level {C.HERO_LEVEL}"),
               (f"{a.kills_to_afford(EC.HEALER['heal'], 5):.0f}", "kills to pay for one 'heal' at level 5"),
               (str(_flat_from(a)), "level after which shops sell nothing better"),
               (str(len(a.gold_outliers())), "mobs with outsized gold"),
           ])]
    out += [_income(a), _healer(a), _shops(a), _hoard(a), _outliers(a)]
    out.append("\n## Method\n")
    out.append(V.details("How these numbers are calculated", a.method(), kind="info"))
    return "".join(out)


def _x():
    return V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False})


def _flat_from(a: EC.EconomyAnalysis) -> int:
    """The last level at which the best shop armour kit improves."""
    kits = {lvl: a.shop_kit(lvl)[0] for lvl in C.LEVELS}
    return max((lvl for lvl in C.LEVELS if lvl > 1 and kits[lvl] > kits[lvl - 1]), default=1)


def _income(a: EC.EconomyAnalysis) -> str:
    rows = [{"level": lvl, "gold": round(g)} for lvl, g in a.gold_per_kill.items() if g]
    chart = V.spec(rows, title="Gold per kill (mob gold + corpse sacrifice), level-appropriate mobs",
                   mark={"type": "line", "color": "#e0a030", "strokeWidth": 2.5},
                   encoding={"x": _x(), "y": V.quant("gold", "Gold per kill"),
                             "tooltip": V.tooltip(("level", "Level"), ("gold", "Gold per kill"))})
    g = a.gold_per_kill
    text = (f"A kill pays about **{g[5]:,.0f}** gold at level 5, {g[30]:,.0f} at 30, {g[60]:,.0f} at 60 and "
            f"**{g[C.HERO_LEVEL]:,.0f}** at {C.HERO_LEVEL}, counting the mob's gold and the 2-per-level a corpse "
            "sacrifice pays. With the kills per level from Combat, a character earns about "
            f"{a.gold_per_level[10]:,.0f} gold during level 10 and {a.gold_per_level[80]:,.0f} during level 80. The "
            "jagged line reflects a handful of very rich mobs (see the last section).\n")
    return (f"\n## Gold per kill grows {g[C.HERO_LEVEL] / g[5]:.0f}× from level 5 to {C.HERO_LEVEL}\n\n" + text
            + V.embed(chart) + V.details("Details: income and spending by band", a.band_table()))


def _healer(a: EC.EconomyAnalysis) -> str:
    rows = [{"level": lvl, "service": s, "kills": round(k, 2)} for s in ("cure light", "heal") for lvl in C.LEVELS
            if (k := a.kills_to_afford(EC.HEALER[s], lvl))]
    chart = V.spec(rows, title="Kills' worth of gold to buy a healer service (flat prices)",
                   mark={"type": "line"},
                   encoding={"x": _x(), "y": V.quant("kills", "Kills of gold", scale={"type": "log"}),
                             "color": V.nominal("service", "", {"heal": HIGHLIGHT, "cure light": "#4f7896"}),
                             "tooltip": V.tooltip(("service", "Service"), ("level", "Level"), ("kills", "Kills"))})
    k = lambda s, lvl: a.kills_to_afford(EC.HEALER[s], lvl)  # noqa: E731
    text = (f"The healer charges the same at every level: {EC.HEALER['cure light']:,} gold for cure light and "
            f"{EC.HEALER['heal']:,} for heal (healer.cpp). That's **{k('heal', 5):.0f} kills' worth** of gold for a "
            f"heal at level 5, {k('heal', 20):.0f} at 20 and {k('heal', 90):.1f} at 90. Bought healing costs new "
            "characters dearly and heroes almost nothing.\n")
    return ("\n## The healer's flat prices hit new characters hardest\n\n" + text + V.embed(chart)
            + V.details("Details: every healer service", a.healer_table()))


def _shops(a: EC.EconomyAnalysis) -> str:
    rows = []
    for lvl in C.LEVELS:
        rows.append({"level": lvl, "what": "gold earned so far", "gold": round(a.cumulative[lvl])})
        rows.append({"level": lvl, "what": "best shop armour, all slots", "gold": a.shop_kit(lvl)[1]})
    chart = V.spec(rows, title="Gold earned so far vs the price of the best armour shops sell (log scale)",
                   mark={"type": "line", "interpolate": "step-after"},
                   encoding={"x": _x(), "y": V.quant("gold", "Gold", scale={"type": "log"}),
                             "color": V.nominal("what", "", {"gold earned so far": "#e0a030",
                                                             "best shop armour, all slots": "#4f7896"}),
                             "tooltip": V.tooltip(("what", ""), ("level", "Level"), ("gold", "Gold"))})
    kit5 = a.shop_kit(5)[1]
    afford = next((lvl for lvl in C.LEVELS if a.cumulative[lvl] >= kit5), None)
    flat = _flat_from(a)
    shop_ac = a.shop_kit(C.HERO_LEVEL)[0]
    world_ac = E.analyse(a.world).ac_kits[C.HERO_LEVEL].total("ac")
    text = (f"Buying the best armour shops sell for every slot costs {kit5:,} gold at level 5; a character has "
            f"earned that much only by level {afford}. Shops add nothing better after level {flat}: their best kit "
            f"stays at {shop_ac:.0f} AC, while the best gear in the world reaches {world_ac:.0f} by "
            f"{C.HERO_LEVEL} (see Equipment). After the early levels, shops stop mattering for gear.\n")
    return (f"\n## Shop gear tops out at level {flat}\n\n" + text + V.embed(chart)
            + V.details(f"Details: everything shops sell ({len(a.stock)})", a.stock_table()))


def _hoard(a: EC.EconomyAnalysis) -> str:
    total = a.cumulative[C.HERO_LEVEL]
    everything = sum(i.price for i in a.stock)
    rest = total - everything
    return ("\n## Gold piles up with little to spend it on\n\n"
            f"By level {C.HERO_LEVEL} a character has earned about **{total:,.0f}** gold. Buying one of every item "
            f"every shop sells would cost {everything:,}"
            + (f", leaving {rest:,.0f}, enough for {rest / EC.HEALER['heal']:,.0f} heals" if rest > 0 else "")
            + f". The healer's prices don't rise with level and shops sell no upgrades after level {_flat_from(a)}, "
            "so late-game gold has little to buy. Pets and trading between players aren't modelled.\n")


def _outliers(a: EC.EconomyAnalysis) -> str:
    out = a.gold_outliers()
    flagged = {m.mob.vnum for _, m, _ in out}
    pts = [{"level": C.usable_level(m.mob.level), "gold": max(1, m.mob.gold), "name": m.mob.short_descr,
            "area": m.info.area.name, "kind": "outlier" if m.mob.vnum in flagged else "typical"}
           for m in a.combat.mobs if m.mob.gold > 0]
    chart = V.spec(pts, title="Gold carried by every combat mob (log scale)", height=320,
                   mark={"type": "point", "filled": True, "opacity": 0.7},
                   params=[{"name": "zoom", "select": "interval", "bind": "scales"}],
                   encoding={"x": V.quant("level", "Mob level"), "y": V.quant("gold", "Gold", scale={"type": "log"}),
                             "color": V.nominal("kind", "", {"outlier": HIGHLIGHT, "typical": MUTED}),
                             "size": {"condition": {"test": "datum.kind === 'outlier'", "value": 70}, "value": 20},
                             "tooltip": V.tooltip(("name", "Mob"), ("area", "Area"), ("level", "Level"),
                                                  ("gold", "Gold"))})
    areas = Counter(m.info.area.name for _, m, _ in out).most_common(2)
    top = out[0] if out else None
    text = (f"{len(out)} combat mobs carry more than {EC.OUTLIER:g}× the median gold for their level"
            + (f", most of them in {_list([f'{n} ({c})' for n, c in areas])}" if out else "") + ". "
            + (f"The richest relative to its level is **{top[1].mob.short_descr}** ({top[1].info.area.name}, level "
               f"{top[1].mob.level}) with {top[1].mob.gold:,} gold, {top[0]:.0f}× the norm. " if top else "")
            + "Because these mobs respawn, they act as gold farms.\n")
    return (f"\n## {len(out)} mobs carry outsized gold\n\n" + text + V.embed(chart)
            + V.details("Details: the outliers", a.outlier_table()))
