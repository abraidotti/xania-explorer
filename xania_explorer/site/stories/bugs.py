"""Bugs page: statistics first, then a catalogue explaining each bug and its fix."""

from __future__ import annotations

from collections import Counter

from ...areafile.world import World
from ...assess import bugs as B
from ...bugs import KINDS, SEVERITY_LABEL, BugResult
from .. import charts as V
from .common import HIGHLIGHT, MUTED, _list, _plural, finding, story

STATUS_COLOURS = {"present": HIGHLIGHT, "latent": "#e0a030", "fixed": "#5f8a5b", "clean": "#5f8a5b",
                  "unknown": MUTED}
SEVERITY_COLOURS = {"crash risk": HIGHLIGHT, "wrong behaviour": "#e0a030", "cosmetic": "#9a8b7e"}
TOP_AREAS = 15


def _ref(r: BugResult) -> str:
    return f"[{r.check.title}](#{r.anchor})"


def bugs_story(world: World):
    a = B.analyse(world)
    crash = a.by(severity="crash")
    tiles = V.stat_tiles([
        (str(len(a.open)), f"open of {len(a.results)} checks"),
        (str(len(crash)), "crash risks in the code or data"),
        (str(a.occurrences), "occurrences across open checks"),
        (" / ".join(str(len(a.by(kind=k))) for k in KINDS), "open code / data / content"),
    ])
    code_open = a.by(kind="code")
    data_found = sum(len(r.detection.occurrences) for r in a.by(kind="data") if r.check.id != "data.unlisted-broken")
    present_crash = [r for r in crash if r.status == "present"]
    return story("bugs", "Bugs",
                 "Defects found in this version's C++ code, area data and content, each explained with a fix. "
                 "Everything is re-detected on every build, so a branch that fixes a bug shows it as fixed.", tiles, [
                     finding("bugs.code", _code(a), metric=len(code_open), label="open code defects",
                             impact=3 if present_crash else 2 if any(r.check.kind == "code" for r in crash) else 1),
                     finding("bugs.data", _data(a), metric=data_found, label="area-data load errors and warnings",
                             issue=data_found > 0, impact=3 if any(r.status == "present" and r.check.kind == "data"
                                                                   for r in crash) else 1),
                     finding("bugs.content", _content(a),
                             metric=sum(len(r.detection.occurrences) for r in a.by(kind="content")),
                             label="pieces of content that never reach players"),
                     finding("bugs.by-area", _areas(a), metric=len({ar for ar, _ in a.area_counts()}),
                             label="areas with open data or content defects", better="none", issue=False),
                 ], a.method(), appendix=_catalogue(a))


def bugs_page(world: World) -> str:
    return bugs_story(world).markdown()


def _status_chart(results: list[BugResult], title: str) -> dict:
    rows = [{"check": r.check.title, "status": r.status, "count": max(1, len(r.detection.occurrences)),
             "occurrences": len(r.detection.occurrences), "severity": SEVERITY_LABEL[r.check.severity]}
            for r in results]
    return V.spec(rows, title=title, height=max(160, 30 * len(rows)), mark="bar",
                  encoding={"y": {"field": "check", "type": "nominal", "title": None, "sort": None,
                                  "axis": {"labelLimit": 360}},
                            "x": V.quant("count", "Occurrences (at least 1 per open check)"),
                            "color": V.nominal("status", "Status", STATUS_COLOURS),
                            "tooltip": V.tooltip(("check", "Check"), ("status", "Status"),
                                                 ("severity", "Severity"), ("occurrences", "Occurrences"))})


def _code(a: B.BugAnalysis) -> str:
    code = a.by(kind="code", open_only=False)
    open_ = [r for r in code if r.open]
    latent = [r for r in open_ if r.status == "latent"]
    crash = [r for r in open_ if r.check.severity == "crash"]
    text = (f"{_plural(len(open_), 'defect')} in the C++ source: "
            + _list([f"{_ref(r)} ({SEVERITY_LABEL[r.check.severity]})" for r in open_]) + ". "
            + (f"{_plural(len(crash), 'is a crash risk', 'are crash risks')}"
               + (f", {len(latent)} of them latent: the faulty code is there, but no current area data triggers it, "
                  "so the first builder to make that mistake takes the MUD down at boot. " if latent else ". ")
               if crash else "")
            + "Each has a suggested patch in the catalogue below.\n")
    title = (f"{_plural(len(open_), 'code defect')}, {_plural(len(crash), 'crash risk')} waiting to happen"
             if crash else f"{_plural(len(open_), 'code defect')}")
    return f"\n## {title}\n\n" + text + V.embed(_status_chart(code, "Code checks: status and occurrences"))


def _data(a: B.BugAnalysis) -> str:
    data = a.by(kind="data", open_only=False)
    loaded = [r for r in data if r.check.id != "data.unlisted-broken"]
    found = sum(len(r.detection.occurrences) for r in loaded)
    broken = next((r for r in data if r.check.id == "data.unlisted-broken"), None)
    extra = (f" {_plural(len(broken.detection.occurrences), 'area file')} that {'isn' if len(broken.detection.occurrences) == 1 else 'aren'}'t "
             f"in `area.lst` would also fail to load if added ({_ref(broken)}).") if broken and broken.open else ""
    if found:
        return (f"\n## {_plural(found, 'area-data error')} in the loaded files\n\n"
                f"The area parser mirrors what the C++ loader rejects or logs. "
                + _list([f"{_ref(r)}: {len(r.detection.occurrences)}" for r in loaded if r.open]) + "." + extra + "\n")
    return ("\n## Every listed area file loads cleanly\n\n"
            "None of the files in `area.lst` has an error the C++ loader would reject or log: no duplicate vnums, "
            "dangling references, bad door resets or invalid drop rates." + extra + "\n")


def _content(a: B.BugAnalysis) -> str:
    content = a.by(kind="content", open_only=False)
    total = sum(len(r.detection.occurrences) for r in content)
    rows = [{"check": r.check.title, "count": len(r.detection.occurrences),
             "severity": SEVERITY_LABEL[r.check.severity]} for r in content]
    chart = V.spec(rows, title="Content that never reaches players", height=max(140, 34 * len(rows)), mark="bar",
                   encoding={"y": {"field": "check", "type": "nominal", "title": None, "sort": "-x",
                                   "axis": {"labelLimit": 360}},
                             "x": V.quant("count", "Occurrences"),
                             "color": V.nominal("severity", "Severity", SEVERITY_COLOURS),
                             "tooltip": V.tooltip(("check", "Check"), ("count", "Occurrences"))})
    text = ("Built content that players can't reach: "
            + _list([f"{len(r.detection.occurrences)} × {_ref(r)}" for r in content if r.detection.occurrences])
            + ". Some is deliberate (immortal rooms, items handed out by mob programs), so treat these as a review "
            "list rather than certain bugs.\n")
    return f"\n## {_plural(total, 'piece')} of content never reach players\n\n" + text + V.embed(chart)


def _areas(a: B.BugAnalysis) -> str:
    counts = a.area_counts()
    per_area = Counter()
    for (area, _), n in counts.items():
        per_area[area] += n
    top = [ar for ar, _ in per_area.most_common(TOP_AREAS)]
    titles = {r.check.id: r.check.title for r in a.results}
    checks = sorted({cid for (ar, cid) in counts if ar in top}, key=lambda c: list(titles).index(c))
    data = [{"area": ar, "check": titles[cid], "count": counts.get((ar, cid), 0)} for ar in top for cid in checks]
    chart = V.heatmap(data, x="check", y="area", value="count", title=f"Open defects per area (top {len(top)})",
                      x_order=[titles[c] for c in checks], y_order=top, value_title="Occurrences", fmt="d")
    chart["encoding"]["x"]["axis"] = {"orient": "top", "labelAngle": -20, "labelLimit": 160}
    worst = per_area.most_common(1)[0] if per_area else None
    text = ((f"**{worst[0]}** has the most ({worst[1]}), " if worst else "")
            + f"and {len(per_area)} areas have at least one. Each cell counts one kind of defect in one area.\n")
    return "\n## Where the defects are\n\n" + text + V.embed(chart)


def _catalogue(a: B.BugAnalysis) -> str:
    def link(file: str, line: int) -> str:
        return a.world.xania.blob_url(file) + f"#L{line}"

    out = ["\n## Bug catalogue {#catalogue}\n\n",
           "Every check, open or not: what it looks for, why it matters, and how to fix it.\n\n",
           V.details("Summary of all checks", a.summary_table(), kind="abstract")]
    for r in a.results:
        chip = (f'<span class="xu-chip xu-status-{r.status}">{r.status}</span>'
                f'<span class="xu-chip">{r.check.kind}</span>'
                f'<span class="xu-chip">{SEVERITY_LABEL[r.check.severity]}</span>')
        out.append(f"\n### {r.check.title} {{#{r.anchor}}}\n\n{chip}"
                   + (f" <span class=\"xu-card-label\">{r.detection.note}</span>" if r.detection.note else "")
                   + f"\n\n{r.check.explain}\n\n**Fix.** {r.check.remedy}\n")
        if r.detection.occurrences:
            out.append(V.details(f"Where: {_plural(len(r.detection.occurrences), 'occurrence')}",
                                 a.occurrence_table(r, link)))
    return "".join(out)
