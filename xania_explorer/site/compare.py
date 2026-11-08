"""Compare page: how do two or more Xania versions differ, statistically and per prototype?

The first target is the baseline (in CI: upstream); every other target is
compared against it.
"""

from __future__ import annotations

from ..areafile import flags as F
from ..areafile.model import Mob, Obj
from ..areafile.world import World
from ..assess import common as C
from ..assess import mobs as M
from ..assess import weapons as W
from . import charts as V
from .pages import BAND_LABELS
from .targets import Target

MAX_CHANGE_ROWS = 300
TARGET_COLOURS = ["#4f7896", "#b4532a", "#5f8a5b", "#e0a030", "#9b5a8a"]


def _metrics(world: World) -> dict[str, object]:
    weapons = [w for w in W.collect(world) if w.obtainable and w.level <= C.HERO_LEVEL]
    mobs = [i for i in M.collect(world) if i.category == "combat"]
    pop = [sum(i.population for i in mobs if i.level in b) for b in C.bands()]
    out: dict[str, object] = {
        "Areas": len(world.areas), "Rooms": len(world.rooms), "Mob prototypes": len(world.mobs),
        "Object prototypes": len(world.objects), "Load problems": len(world.problems),
        "Obtainable weapons (≤ 91)": len(weapons),
        "Weapons over damage cap": sum(w.over_cap for w in W.collect(world)),
    }
    for p in W.class_profiles(world.src_dir):
        out[f"Weapons in {p.name} start types"] = sum(w.type in p.starting for w in weapons)
    spread = C.Spread.of(pop)
    out.update({"Combat mobs": len(mobs), "Mob population": sum(pop),
                "Mob population CV (bands)": round(spread.cv, 2), "Mob population Gini (bands)": round(spread.gini, 2),
                "Levels with no combat mob": sum(1 for lvl in C.LEVELS if not any(i.level == lvl for i in mobs))})
    out.update(_system_metrics(world))
    return out


def _system_metrics(world: World) -> dict[str, object]:
    """Headline numbers from the other systems, so a fork's balance changes show up here."""
    from ..assess import combat as CB
    from ..assess import economy as EC
    from ..assess import equipment as E
    from ..assess import levelling as L
    from ..assess import skills as S

    out: dict[str, object] = {}
    eq = E.analyse(world)
    out["Best-in-slot AC at 91"] = round(eq.ac_kits[C.HERO_LEVEL].total("ac"))
    out["Items over the points rule"] = len(eq.over_points)
    cb = CB.analyse(world)
    for c in ("mage", "knight"):
        out[f"Combat hours to 91 ({c})"] = round(cb.hours_to_hero(c), 1)
    kills = [v for v in cb.series("knight", "kills_per_level").values() if v]
    out["Mean kills per level"] = round(sum(kills) / len(kills), 1)
    sk = S.analyse(world)
    out["Mage casts per kill at 91"] = round(sk.casts_to_kill("mage", C.HERO_LEVEL) or 0, 1)
    ec = EC.analyse(world)
    out["Gold earned by 91"] = f"{ec.cumulative[C.HERO_LEVEL]:,.0f}"
    lv = L.analyse(world)
    out["Levels of XP per reset at 60"] = round(lv.levels_of_xp(60), 1)
    out["Levels with ≤ 3 suitable areas"] = sum(1 for lvl in C.LEVELS if len(lv.suitable(lvl)) <= 3)
    out["Rooms unreachable on foot"] = len(lv.unreachable_rooms)
    return out


def _mob_fields(m: Mob) -> dict[str, object]:
    return {"level": m.level, "hp": str(m.hit), "damage": str(m.damage), "hitroll": m.hitroll,
            "ac": "/".join(map(str, m.ac)), "attack": m.attack, "act": " ".join(m.act_names),
            "off": " ".join(m.off_names), "alignment": m.alignment}


def _obj_fields(o: Obj) -> dict[str, object]:
    return {"type": o.type_name, "level": o.level, "values": " ".join(map(str, o.values)),
            "affects": ", ".join(f"{a.location_name} {a.modifier:+d}" for a in o.affects),
            "extra": " ".join(F.decode(o.extra_flags, F.OBJ_EXTRA)), "cost": o.cost, "weight": o.weight}


def _changes(base: dict[int, object], other: dict[int, object], fields, names, areas_base, areas_other):
    rows = []
    for vnum in sorted(set(base) | set(other)):
        a, b = base.get(vnum), other.get(vnum)
        if a is None:
            rows.append([vnum, names(b), areas_other[vnum].name, "added", "", ""])
        elif b is None:
            rows.append([vnum, names(a), areas_base[vnum].name, "removed", "", ""])
        else:
            fa, fb = fields(a), fields(b)
            for key in fa:
                if fa[key] != fb[key]:
                    rows.append([vnum, names(b), areas_other[vnum].name, key, fa[key], fb[key]])
    return rows


def render(targets: list[tuple[Target, World]]) -> str:
    base_t, base_w = targets[0]
    names = [t.name for t, _ in targets]
    out = ["# Compare versions\n\n",
           f"Baseline: **{base_t.label}**. Compared: "
           + ", ".join(f"**{t.label}**" for t, _ in targets[1:]) + ".\n\n"]

    metrics = [_metrics(w) for _, w in targets]
    out.append("## Key numbers\n\n")
    out.append(C.table(["Metric"] + names, [[k] + [m[k] for m in metrics] for k in metrics[0]]))

    colours = {n: TARGET_COLOURS[i % len(TARGET_COLOURS)] for i, n in enumerate(names)}
    pop, wpn, curve = [], [], []
    for t, w in targets:
        combat = [i for i in M.collect(w) if i.category == "combat"]
        got = [x for x in W.collect(w) if x.obtainable and x.level <= C.HERO_LEVEL]
        for b in C.bands():
            pop.append({"band": b.label, "version": t.name, "value": sum(i.population for i in combat if i.level in b)})
            wpn.append({"band": b.label, "version": t.name, "value": sum(1 for x in got if x.level in b)})
        for p in W.class_profiles(w.src_dir):
            for lvl, v in W.best_by_level(got, set(p.starting)).items():
                if v is not None:
                    curve.append({"level": lvl, "version": t.name, "class": p.name, "avg": v})

    def grouped(data, title, ytitle):
        return V.spec(data, title=title, mark="bar",
                      encoding={"x": V.ordinal("band", "Levels", BAND_LABELS), "xOffset": {"field": "version"},
                                "y": V.quant("value", ytitle), "color": V.nominal("version", "Version", colours, names),
                                "tooltip": V.tooltip(("version", "Version"), ("band", "Levels"), ("value", ytitle))})

    out.append("\n## Mob population by band\n")
    out.append(V.embed(grouped(pop, "Combat mob population per level band", "Instances")))
    out.append("\n## Obtainable weapons by band\n")
    out.append(V.embed(grouped(wpn, "New obtainable weapons per level band", "Weapons")))
    out.append("\n## Best starting-type weapon per class\n")
    for p in W.class_profiles(base_w.src_dir):
        out.append(V.embed(V.spec([r for r in curve if r["class"] == p.name], height=180,
                                  title=f"{p.name}: best usable weapon by level",
                                  mark={"type": "line", "interpolate": "step-after"},
                                  encoding={"x": V.quant("level", "Level"), "y": V.quant("avg", "Average damage"),
                                            "color": V.nominal("version", "Version", colours, names),
                                            "tooltip": V.tooltip(("version", "Version"), ("level", "Level"),
                                                                 ("avg", "Avg"))})))

    for t, w in targets[1:]:
        mob_rows = _changes(base_w.mobs, w.mobs, _mob_fields, lambda m: m.short_descr, base_w.mob_area, w.mob_area)
        obj_rows = _changes(base_w.objects, w.objects, _obj_fields, lambda o: o.short_descr,
                            base_w.obj_area, w.obj_area)
        out.append(f"\n## Prototype changes: {base_t.name} → {t.name}\n\n"
                   f"{len({r[0] for r in mob_rows})} mobs and {len({r[0] for r in obj_rows})} objects differ.\n")
        for title, rows in (("Mobs", mob_rows), ("Objects", obj_rows)):
            out.append(f"\n### {title} ({len(rows)} changed fields)\n\n")
            if rows:
                out.append(C.table(["Vnum", "Name", "Area", "Field", base_t.name, t.name], rows[:MAX_CHANGE_ROWS]))
                if len(rows) > MAX_CHANGE_ROWS:
                    out.append(f"\n…and {len(rows) - MAX_CHANGE_ROWS} more.\n")
            else:
                out.append("No differences.\n")
    return "".join(out)
