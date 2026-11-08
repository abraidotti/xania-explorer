"""Area difficulty page: each area profiled for the characters it serves."""

from __future__ import annotations

from ...areafile.world import World
from ...assess import common as C
from ...assess import difficulty as D
from .. import charts as V
from .common import HIGHLIGHT, MUTED, _list, _plural, by_area, edit_effort, finding, rec, story

VERDICT_COLOURS = {"much harder": HIGHLIGHT, "typical": MUTED, "much easier": "#3f88c5", "no peers": "#d9cfc3"}


def difficulty_story(world: World):
    a = D.analyse(world)
    harder, easier = a.outliers("much harder"), a.outliers("much easier")
    tiles = V.stat_tiles([
        (str(len(a.areas)), "areas profiled"),
        (str(len(harder)), "much harder than their peers"),
        (str(len(easier)), "much easier"),
        (str(len(a.tails)), "with a dangerous tail"),
        (str(len(a.traps)), "aggressive mobs far above their area's range"),
    ])
    return story("difficulty", "Area difficulty",
                 "How hard each area is for a character at its own level, compared with other areas at that level, "
                 "and what it pays. Each area is profiled for a knight at the median level of its mobs, using the "
                 "Combat & XP model (gear, specials and helpers included).", tiles, [
                     finding("difficulty.outliers", _outliers(a), metric=len(harder),
                             label="areas at least twice as hard as their peers on a typical fight", impact=2,
                             issue=bool(harder), recs=[_r_outliers(a)]),
                     finding("difficulty.tails", _tails(a), metric=len(a.tails),
                             label=f"areas whose deadly share is {D.TAIL_POINTS:.0%}+ above their peers'", impact=2,
                             issue=bool(a.tails), recs=[_r_tails(a)]),
                     finding("difficulty.aggro-traps", _traps(a), metric=len(a.traps),
                             label=f"aggressive mobs {D.TRAP_GAP}+ levels above their area's advertised range",
                             impact=2, issue=bool(a.traps), recs=[_r_traps(a)]),
                     finding("difficulty.reward", _reward(a), metric=len(_poor_payers(a)),
                             label="areas paying under half their peers' XP per minute", issue=False),
                 ], a.method(), appendix=V.details("Every area's profile", a.profile_table(), kind="abstract"))


def difficulty_page(world: World) -> str:
    return difficulty_story(world).markdown()


def _peer_median(a: D.DifficultyAnalysis, p: D.AreaProfile, attr: str) -> float | None:
    return C.median_or(getattr(q, attr) for q in a.areas if q.name != p.name and q.population >= D.MIN_POPULATION
                       and abs(q.level - p.level) <= D.PEER_LEVELS)


def _outliers(a: D.DifficultyAnalysis) -> str:
    rows = [{"area": p.name, "level": p.level, "hp": round(max(p.hp_loss, 0.005), 3), "verdict": p.verdict,
             "deadly": round(p.deadly, 3), "population": p.population,
             "advertised": f"{p.advertised[0]}–{p.advertised[1]}" if p.advertised else "all"} for p in a.areas]
    chart = V.spec(rows, title="Every area: HP a typical fight costs at the area's level (log scale)", height=340,
                   mark={"type": "point", "filled": True, "opacity": 0.85},
                   params=[{"name": "zoom", "select": "interval", "bind": "scales"}],
                   encoding={"x": V.quant("level", "Area level (median mob level)"),
                             "y": V.quant("hp", "HP lost per kill", scale={"type": "log"}, axis={"format": ".0%"}),
                             "color": V.nominal("verdict", "Against its peers", VERDICT_COLOURS,
                                                list(VERDICT_COLOURS)),
                             "size": {"field": "population", "type": "quantitative", "title": "Mobs"},
                             "tooltip": [{"field": "area", "title": "Area"}, {"field": "advertised", "title": "Advertised"},
                                         {"field": "level", "title": "Level"},
                                         {"field": "hp", "title": "HP lost per kill", "format": ".0%"},
                                         {"field": "deadly", "title": "Deadly", "format": ".0%"}]})
    harder, easier = a.outliers("much harder"), a.outliers("much easier")

    def show(ps):
        return _list([f"**{p.name}** ({p.peer_ratio:.1f}× at level {p.level})" for p in ps])

    sized = [p for p in a.areas if p.population >= D.MIN_POPULATION]
    text = (f"At its own level, a typical fight costs a knight between "
            f"{min(p.hp_loss for p in sized):.0%} and {max(p.hp_loss for p in sized):.0%} of their HP, depending "
            f"on the area. Comparing each area with the others within ±{D.PEER_LEVELS} levels, "
            + (f"{_plural(len(harder), 'area is', 'areas are')} at least twice as hard as {'its' if len(harder) == 1 else 'their'} peers: "
               f"{show(harder)}. " if harder else "no area is twice as hard as its peers. ")
            + (f"{_plural(len(easier), 'area is', 'areas are')} at most half as hard: {show(easier)}." if easier else "")
            + "\n")
    title = (f"{_plural(len(harder), 'area is', 'areas are')} twice as hard as others at the same level" if harder
             else "Areas at the same level are about as hard as each other")
    return f"\n## {title}\n\n" + text + V.embed(chart)


def _r_outliers(a: D.DifficultyAnalysis):
    harder = a.outliers("much harder")
    if not harder:
        return None
    moves = [(p, a.level_to_match_peers(p)) for p in harder]
    moves = [(p, lvl) for p, lvl in moves if lvl]
    if not moves:
        return None
    return rec("difficulty.outliers.re-advertise", f"Advertise {_plural(len(moves), 'hard area')} for higher levels, "
               "or soften their mobs",
               "Raise the `{lo hi}` range in each area's header so it starts where the area is as hard as its "
               "peers: " + _list([f"{p.name} from level {lvl} (its mobs' median is {p.level})" for p, lvl in moves])
               + ". Or lower its mobs' HP and damage dice, if the area is meant for its current level.",
               "At those levels each area costs no more HP per typical fight than the median area there, so players "
               "who follow the advertised range meet a normal difficulty.",
               effort=edit_effort(len(moves), len(moves)))


def _tails(a: D.DifficultyAnalysis) -> str:
    tails = {p.name for p in a.tails}
    rows = [{"area": p.name, "level": p.level, "deadly": round(p.deadly, 3), "peers": round(p.peer_deadly, 3),
             "kind": "dangerous tail" if p.name in tails else "other areas"}
            for p in a.areas if p.peer_deadly is not None]
    chart = V.spec(rows, title="Share of each area's mobs that are deadly at its level (counting helpers)",
                   height=300, mark={"type": "point", "filled": True, "opacity": 0.85},
                   encoding={"x": V.quant("level", "Area level"),
                             "y": V.quant("deadly", "Deadly share", axis={"format": ".0%"}),
                             "color": V.nominal("kind", "", {"dangerous tail": HIGHLIGHT, "other areas": MUTED}),
                             "tooltip": [{"field": "area", "title": "Area"}, {"field": "level", "title": "Level"},
                                         {"field": "deadly", "title": "Deadly", "format": ".0%"},
                                         {"field": "peers", "title": "Peers' median", "format": ".0%"}]})
    if not a.tails:
        return ("\n## No area hides a dangerous minority of mobs\n\n"
                f"No area's deadly share is {D.TAIL_POINTS:.0%} above its peers'.\n" + V.embed(chart))
    parts = [f"**{p.name}** (level {p.level}): {p.deadly:.0%} deadly against {p.peer_deadly:.0%} for its peers, from "
             + _list([f"{m.mob.short_descr} ({m.mob.level})" for m in p.killers[:3]])
             + (f" and {len(p.killers) - 3} more" if len(p.killers) > 3 else "") for p in a.tails]
    text = ("Some areas are fine on a typical fight but hide mobs far beyond the characters the area serves, so a "
            "character at the area's level dies to a wrong turn. " + "; ".join(parts) + ".\n")
    table = C.table(["Area", "Level", "Mob", "Mob level"],
                    [[p.name, p.level, f"#{m.mob.vnum} {m.mob.short_descr}", m.mob.level] for p in a.tails
                     for m in p.killers])
    return (f"\n## {_plural(len(a.tails), 'area hides', 'areas hide')} mobs that kill characters of the area's level\n\n"
            + text + V.embed(chart) + V.details("Details: the deadly mobs", table))


def _r_tails(a: D.DifficultyAnalysis):
    if not a.tails:
        return None
    mobs = [(p, m) for p in a.tails for m in p.killers]
    return rec("difficulty.tails.separate-killers",
               f"Move or re-level the {_plural(len(mobs), 'mob')} that make {_plural(len(a.tails), 'area')} deadly",
               "Put them in a part of the area (or another area) meant for their level, behind a door or a warning, or "
               "lower them to the area's range: " + by_area([p.name for p, _ in mobs]) + ".",
               "Deadly share at each area's level: "
               + _list([f"{p.name} {p.deadly:.0%} → 0% (peers {p.peer_deadly:.0%})" for p in a.tails]) + ".",
               effort=edit_effort(len(a.tails), len(mobs)))


def _traps(a: D.DifficultyAnalysis) -> str:
    if not a.traps:
        return ("\n## No aggressive mob sits far above its area's advertised range\n\n"
                f"Every aggressive mob is within {D.TRAP_GAP} levels of its area's advertised top.\n")
    text = ("Aggressive mobs attack any player up to 5 levels above them on sight, so one far above an area's "
            "advertised range attacks the very characters the range invites in. "
            + _list([f"{m.mob.short_descr} (level {m.mob.level}) in {p.name} (advertised "
                     f"{p.advertised[0]}–{p.advertised[1]})" for p, m, _ in a.traps]) + ".\n")
    return (f"\n## {_plural(len(a.traps), 'aggressive mob')} attack{'s' if len(a.traps) == 1 else ''} the characters "
            "their area is advertised for\n\n" + text + V.details("Details: the traps", a.trap_table()))


def _r_traps(a: D.DifficultyAnalysis):
    if not a.traps:
        return None
    return rec("difficulty.aggro-traps.defuse", f"Defuse the {_plural(len(a.traps), 'aggressive mob')} far above "
               "their area's range",
               "For each, remove the `aggressive` act flag, lower its level towards the area's range, or move it out "
               "of the area's normal path: " + by_area([p.name for p, _, _ in a.traps]) + ".",
               f"Aggressive mobs {D.TRAP_GAP}+ levels above their area's range: **{len(a.traps)} → 0**.",
               effort=edit_effort(len({p.name for p, _, _ in a.traps}), len(a.traps)))


def _poor_payers(a: D.DifficultyAnalysis) -> list[D.AreaProfile]:
    out = []
    for p in a.areas:
        if p.population < D.MIN_POPULATION:
            continue
        median = _peer_median(a, p, "xp_per_minute")
        if median and p.xp_per_minute < median / 2:
            out.append(p)
    return out


def _reward(a: D.DifficultyAnalysis) -> str:
    rows = [{"area": p.name, "level": p.level, "xp": round(p.xp_per_minute), "hp": round(p.hp_loss, 3)}
            for p in a.areas if p.population >= D.MIN_POPULATION]
    chart = V.spec(rows, title="XP per minute of combat at each area's level", height=300,
                   mark={"type": "point", "filled": True, "color": "#3f88c5", "opacity": 0.8},
                   encoding={"x": V.quant("level", "Area level"),
                             "y": V.quant("xp", "XP per minute", scale={"type": "log"}),
                             "tooltip": [{"field": "area", "title": "Area"}, {"field": "level", "title": "Level"},
                                         {"field": "xp", "title": "XP/min"},
                                         {"field": "hp", "title": "HP lost per kill", "format": ".0%"}]})
    poor = _poor_payers(a)
    ranked = sorted((p for p in a.areas if p.population >= D.MIN_POPULATION and p.hp_loss > 0),
                    key=lambda p: -p.xp_per_hp)
    text = ("XP per minute of combat falls with level, because fights get longer (see Combat & XP). "
            + (f"{_plural(len(poor), 'area pays', 'areas pay')} under half the XP per minute of {'its' if len(poor) == 1 else 'their'} peers: "
               + _list([f"{p.name} ({p.xp_per_minute:.0f} vs ~{_peer_median(a, p, 'xp_per_minute'):.0f})"
                        for p in poor[:6]] + ([f"{len(poor) - 6} more"] if len(poor) > 6 else [])) + ". "
               if poor else "")
            + (f"For XP per HP lost, the best area is **{ranked[0].name}** and the worst **{ranked[-1].name}**."
               if len(ranked) > 1 else "") + "\n")
    return "\n## What each area pays for its risk\n\n" + text + V.embed(chart)
