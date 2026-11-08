"""Skills & spells page."""

from __future__ import annotations

from ...areafile.world import World
from ...assess import common as C
from ...assess import skills as S
from ...source.cpp_tables import CLASSES
from .. import charts as V
from .common import _list

CASTERS = ["mage", "cleric"]


def skills_page(world: World) -> str:
    a = S.analyse(world)
    lvl20 = {c: (a.practices_needed(c, 20), a.practices_earned(c, 20)) for c in CLASSES}
    worst20 = max(CLASSES, key=lambda c: lvl20[c][0] - lvl20[c][1])
    casts91 = a.casts_to_kill("mage", C.HERO_LEVEL)
    out = ["# Skills & spells by level\n\n",
           "What each class can learn as it levels, whether its practices keep up, and how attack spells compare "
           "with mob HP and with melee.\n",
           V.stat_tiles([
               (str(max(len(a.abilities[c]) for c in CLASSES)), "skills and spells a class can learn"),
               (f"{lvl20[worst20][0]} vs {lvl20[worst20][1]:.0f}", f"practices needed vs earned by a {worst20} at 20"),
               (f"{casts91:.0f}", f"casts of a mage's best spell to kill a level-{C.HERO_LEVEL} mob"),
               (f"{C.median_or(v for lvl in C.LEVELS if lvl >= 10 and (v := a.kills_per_mana_bar('mage', lvl))):.1f}",
                "level-appropriate kills per full mana bar (mage)"),
           ])]
    out += [_availability(a), _practices(a), _mana(a), _casts(a), _vs_melee(a)]
    out.append("\n## Method\n")
    out.append(V.details("How these numbers are calculated", a.method(), kind="info"))
    return "".join(out)


def _x():
    return V.quant("level", "Level", scale={"domain": [1, C.HERO_LEVEL], "nice": False})


def _availability(a: S.SkillAnalysis) -> str:
    rows = [{"class": c, "level": lvl, "count": len(a.available(c, lvl))} for c in CLASSES for lvl in C.LEVELS]
    chart = V.spec(rows, title="Skills and spells each class can learn by each level",
                   mark={"type": "line", "interpolate": "step-after"},
                   encoding={"x": _x(), "y": V.quant("count", "Learnable"),
                             "color": V.nominal("class", "Class", V.CLASS_COLOURS, CLASSES),
                             "tooltip": V.tooltip(("class", "Class"), ("level", "Level"), ("count", "Learnable"))})
    at59 = {c: len(a.available(c, 59)) for c in CLASSES}
    at60 = {c: len(a.available(c, 60)) for c in CLASSES}
    jump = max(CLASSES, key=lambda c: at60[c] - at59[c])
    last = {c: max(x.level for x in a.abilities[c]) for c in CLASSES}
    text = ("New abilities arrive steadily up to level 60, where most classes get a burst: many other classes' "
            f"spells open to everyone at 60 (a {jump} gains {at60[jump] - at59[jump]} at once). After that the list is "
            "finished: the last "
            "new ability comes at level "
            + ", ".join(f"{last[c]} for {c}s" for c in CLASSES)
            + f", so the final {C.HERO_LEVEL - max(last.values())}–{C.HERO_LEVEL - min(last.values())} levels bring "
            "nothing new to learn.\n")
    return (f"\n## Nothing new to learn after level {max(last.values())}\n\n" + text + V.embed(chart)
            + "".join(V.details(f"Details: everything a {c} can learn", a.class_table(c)) for c in CLASSES))


def _practices(a: S.SkillAnalysis) -> str:
    rows = []
    for c in CLASSES:
        for lvl in C.LEVELS:
            rows.append({"class": c, "level": lvl, "what": "needed", "value": a.practices_needed(c, lvl)})
            rows.append({"class": c, "level": lvl, "what": "earned", "value": round(a.practices_earned(c, lvl))})
    chart = V.spec(rows, title="Practices needed to master the default package (solid) vs practices earned (dashed)",
                   mark={"type": "line", "interpolate": "step-after"},
                   encoding={"x": _x(), "y": V.quant("value", "Practices"),
                             "color": V.nominal("class", "Class", V.CLASS_COLOURS, CLASSES),
                             "strokeDash": {"field": "what", "type": "nominal", "title": "",
                                            "scale": {"domain": ["needed", "earned"], "range": [[1, 0], [5, 3]]},
                                            "legend": {"symbolType": "stroke"}},
                             "tooltip": V.tooltip(("class", "Class"), ("level", "Level"), ("what", ""),
                                                  ("value", "Practices"))})
    catch_up = {}
    for c in CLASSES:
        catch_up[c] = next((lvl for lvl in C.LEVELS if a.practices_earned(c, lvl) >= a.practices_needed(c, lvl)
                            and all(a.practices_earned(c, x) >= a.practices_needed(c, x)
                                    for x in range(lvl, C.HERO_LEVEL + 1))), None)
    l20 = {c: (a.practices_needed(c, 20), a.practices_earned(c, 20)) for c in CLASSES}
    text = ("Practising raises a skill by `int_app.learn / difficulty`, so taking a default-package skill from 1% "
            "to the 75% adept limit costs a handful of practices each. Practices arrive slowly (wis-based, often 1–3 a "
            "level), so by level 20 "
            + _list([f"a {c} needs {n} but has {e:.0f}" for c, (n, e) in l20.items()]) + ". "
            + ("Supply catches up with demand for good at level "
               + ", ".join(f"{lvl} ({c})" for c, lvl in catch_up.items() if lvl) + ". " if any(catch_up.values()) else "")
            + "In between, players must choose what to practise; using a skill also improves it, which softens this.\n")
    latest = max((lvl for lvl in catch_up.values() if lvl), default=C.HERO_LEVEL)
    return (f"\n## Practices only catch up with the default package by level {latest}\n\n" + text + V.embed(chart))


def _mana(a: S.SkillAnalysis) -> str:
    rows = [{"class": c, "level": lvl, "value": v} for c in CASTERS for lvl in C.LEVELS
            if (v := a.kills_per_mana_bar(c, lvl)) is not None]
    chart = V.spec(rows, title="Level-appropriate kills per full mana bar, best attack spell",
                   mark={"type": "line"},
                   encoding={"x": _x(), "y": V.quant("value", "Kills per full mana", scale={"zero": True}),
                             "color": V.nominal("class", "Class", V.CLASS_COLOURS, CASTERS),
                             "tooltip": [{"field": "class"}, {"field": "level"},
                                         {"field": "value", "title": "Kills", "format": ".2f"}]})
    vals = [r["value"] for r in rows if r["class"] == "mage" and r["level"] >= 10]
    med = C.median_or(vals)
    text = (f"Spending a full mana bar on a mage's best attack spell kills **{min(vals):.1f}–{max(vals):.1f}** "
            f"level-appropriate mobs (median {med:.1f}) at every level from 10 up: mana growth (see Characters), "
            "falling mana cost and rising spell damage roughly cancel mob HP growth. A caster fighting with spells "
            "alone needs to regenerate its mana after about every kill.\n")
    return (f"\n## A full mana bar buys about {med:.1f} kills, at every level\n\n" + text + V.embed(chart))


def _casts(a: S.SkillAnalysis) -> str:
    rows = [{"class": c, "level": lvl, "value": v} for c in CASTERS for lvl in C.LEVELS
            if (v := a.casts_to_kill(c, lvl)) is not None]
    chart = V.spec(rows, title="Casts of the best attack spell needed to kill a level-appropriate mob",
                   mark={"type": "line"},
                   encoding={"x": _x(), "y": V.quant("value", "Casts"),
                             "color": V.nominal("class", "Class", V.CLASS_COLOURS, CASTERS),
                             "tooltip": [{"field": "class"}, {"field": "level"},
                                         {"field": "value", "title": "Casts", "format": ".1f"}]})
    m30, m91 = a.spells["mage"][30], a.spells["mage"][C.HERO_LEVEL]
    hp30, hp91 = a.mob_hp(30), a.mob_hp(C.HERO_LEVEL)
    text = (f"A mage's best spell does about {m30.damage:.0f} damage per cast at level 30 ({m30.ability.name}) and "
            f"{m91.damage:.0f} at {C.HERO_LEVEL}, a {m91.damage / m30.damage:.1f}× rise. Over the same levels the "
            f"median level-appropriate mob goes from {hp30:,.0f} to {hp91:,.0f} HP, {hp91 / hp30:.1f}× more. The damage "
            "tables in magic.cpp flatten out after the 30s, so the number of casts per kill climbs from about "
            f"{a.casts_to_kill('mage', 30):.0f} to {a.casts_to_kill('mage', C.HERO_LEVEL):.0f}.\n")
    return (f"\n## Attack spells fall behind mob HP: {a.casts_to_kill('mage', C.HERO_LEVEL):.0f} casts per kill by "
            f"level {C.HERO_LEVEL}\n\n" + text + V.embed(chart)
            + "".join(V.details(f"Details: {c} attack spells by band", a.spell_table(c)) for c in CASTERS)
            + V.details("Details: every damage spell", a.damage_spell_table()))


def _vs_melee(a: S.SkillAnalysis) -> str:
    rows = []
    for c in CASTERS:
        for lvl in C.LEVELS:
            sp = a.spells[c][lvl]
            if sp:
                rows.append({"class": c, "level": lvl, "how": "best spell", "value": round(sp.per_round, 1)})
            m = a.melee_per_round(c, lvl)
            if m:
                rows.append({"class": c, "level": lvl, "how": "melee", "value": round(m, 1)})
    knight = a.melee_per_round("knight", C.HERO_LEVEL)
    for lvl in C.LEVELS:
        if (m := a.melee_per_round("knight", lvl)):
            rows.append({"class": "knight", "level": lvl, "how": "melee", "value": round(m, 1)})
    chart = V.spec(rows, title="Damage per round: casters' best spell (solid) vs melee (dashed); knight melee for scale",
                   mark={"type": "line"},
                   encoding={"x": _x(), "y": V.quant("value", "Damage per round"),
                             "color": V.nominal("class", "Class", V.CLASS_COLOURS, CASTERS + ["knight"]),
                             "strokeDash": {"field": "how", "type": "nominal", "title": "",
                                            "scale": {"domain": ["best spell", "melee"], "range": [[1, 0], [5, 3]]},
                                            "legend": {"symbolType": "stroke"}},
                             "tooltip": V.tooltip(("class", "Class"), ("how", ""), ("level", "Level"),
                                                  ("value", "Damage/round"))})
    ratio = {lvl: a.spells["mage"][lvl].per_round / a.melee_per_round("mage", lvl) for lvl in (30, C.HERO_LEVEL)}
    text = (f"Per round, a mage's best spell does {ratio[30]:.1f}× its melee damage at level 30 and "
            f"{ratio[C.HERO_LEVEL]:.1f}× at {C.HERO_LEVEL}, and out-damages even a knight's melee "
            f"({knight:.0f} per round at {C.HERO_LEVEL}) for as long as the mana lasts. Casters are strong in bursts and "
            "weak over a long fight, which is exactly where the long mob-HP fights of the Combat page hurt them.\n")
    return ("\n## Casters out-damage everyone, until the mana runs out\n\n" + text + V.embed(chart))
