"""Dashboards built from findings: one per deployment, a home-page summary, and the comparison scorecard.

Cards are Markdown inside HTML blocks (md_in_html), so their links are ordinary `page.md#anchor` links that
MkDocs resolves and validates.
"""

from __future__ import annotations

from ..areafile.world import World
from ..findings import Finding, fmt_metric, verdict
from ..systems import SYSTEMS, System

IMPACT_NAME = {3: "high impact", 2: "medium impact", 1: "minor"}
TOP_CARDS = 9


def issues(world: World) -> list[tuple[System, Finding]]:
    """Every balance issue across systems, most impactful first (then in reading order)."""
    out = [(s, f) for s in SYSTEMS for f in s.story(world).findings if f.issue]
    order = {s.slug: i for i, s in enumerate(SYSTEMS)}
    return sorted(out, key=lambda sf: (-sf[1].impact, order[sf[0].slug]))


def _link(prefix: str, system: System, f: Finding) -> str:
    return f"{prefix}{system.slug}.md#{f.anchor}"


def card(system: System, f: Finding, prefix: str = "") -> str:
    metric = (f'<span class="xu-card-metric">{fmt_metric(f.metric)}</span> '
              f'<span class="xu-card-label">{f.metric_label}</span>') if f.metric is not None else ""
    return (f'<div class="xu-finding-card xu-impact-{f.impact}" markdown>\n\n'
            f'<span class="xu-chip">{system.title}</span>'
            f'<span class="xu-chip xu-chip-impact">{IMPACT_NAME[f.impact]}</span>\n\n'
            f"**[{f.title}]({_link(prefix, system, f)})**\n\n"
            f"{metric}\n\n</div>\n")


def card_grid(items: list[tuple[System, Finding]], prefix: str = "") -> str:
    return '\n<div class="xu-card-grid" markdown>\n\n' + "".join(card(s, f, prefix) for s, f in items) + "\n</div>\n\n"


def issue_counts(world: World) -> dict[int, int]:
    counts = {3: 0, 2: 0, 1: 0}
    for _, f in issues(world):
        counts[f.impact] += 1
    return counts


def deployment_dashboard(world: World) -> str:
    """The balance part of a deployment's overview page."""
    found = issues(world)
    top = found[:TOP_CARDS]
    rest = found[TOP_CARDS:]
    out = ["\n## Most pressing balance issues {#top-issues}\n\n",
           "The highest-impact findings across every system. Each links to its evidence.\n",
           card_grid(top)]
    if rest:
        out.append("\n## Other issues {#other-issues}\n\n| System | Finding | Impact | Number |\n|---|---|---|---|\n")
        for s, f in rest:
            out.append(f"| {s.title} | [{f.title}]({_link('', s, f)}) | {IMPACT_NAME[f.impact]} | "
                       f"{fmt_metric(f.metric)} {f.metric_label} |\n")
    out.append("\n## Systems {#systems}\n\n")
    out.append('\n<div class="xu-card-grid" markdown>\n\n')
    for s in SYSTEMS:
        st = s.story(world)
        worst = st.issues[0] if st.issues else None
        if st.status != "ok":
            line = f"**{'Unavailable' if st.status == 'unavailable' else 'Failed'}** for this checkout.\n\n"
        elif worst:
            line = f"Top issue: [{worst.title}]({s.slug}.md#{worst.anchor})\n\n"
        else:
            line = "No issues found.\n\n"
        out.append(f'<div class="xu-system-card" markdown>\n\n**[{s.title}]({s.slug}.md)**\n\n'
                   f'<span class="xu-card-label">{s.question}</span>\n\n' + line + "</div>\n")
    out.append("\n</div>\n\n")
    return "".join(out)


def home_summary(targets: list[tuple[object, World]], per_target: int = 3) -> str:
    """'At a glance' block for the site home page: each deployment's top issues."""
    out = ["\n## At a glance {#at-a-glance}\n\n"]
    for t, world in targets:
        counts = issue_counts(world)
        out.append(f"**[{t.label}]({t.name}/index.md)**: {counts[3]} high-impact, {counts[2]} medium and "
                   f"{counts[1]} minor balance issues.\n")
        out.append(card_grid(issues(world)[:per_target], prefix=f"{t.name}/"))
    if len(targets) > 1:
        out.append("See [Compare](compare.md) for how the versions differ. ")
    out.append("To look at any other repo or branch, or compare two of them, use the "
               "[live explorer](explore.md).\n\n")
    return "".join(out)


def bug_changes(targets: list[tuple[object, World]]) -> str:
    """Bug checks whose status differs from the baseline: fixed, introduced or changed."""
    from ..assess import bugs as B

    base_t, base_w = targets[0]
    base = {r.check.id: r for r in B.analyse(base_w).results}
    rows = []
    for t, w in targets[1:]:
        for r in B.analyse(w).results:
            b = base.get(r.check.id)
            if b is None or b.status == r.status and len(b.detection.occurrences) == len(r.detection.occurrences):
                continue
            if b.open and not r.open:
                change = '<span class="xu-improved">▲ fixed</span>'
            elif r.open and not b.open:
                change = '<span class="xu-worse">▼ introduced</span>'
            else:
                d = len(r.detection.occurrences) - len(b.detection.occurrences)
                change = (f'<span class="xu-{"improved" if d < 0 else "worse"}">{"▲" if d < 0 else "▼"} '
                          f'{d:+d} occurrences</span>') if d else f"{b.status} → {r.status}"
            rows.append(f"| {t.name} | [{r.check.title}]({t.name}/bugs.md#{r.anchor}) | {b.status} "
                        f"({len(b.detection.occurrences)}) | {r.status} ({len(r.detection.occurrences)}) | {change} |\n")
    out = "\n## Bugs fixed or introduced {#bug-changes}\n\n"
    if not rows:
        return out + "Every bug check has the same status and count as the baseline.\n\n"
    return (out + f"| Version | Check | {base_t.name} | Version | Change |\n|---|---|---|---|---|\n" + "".join(rows)
            + "\n")


def scorecard(targets: list[tuple[object, World]]) -> str:
    """Every finding's headline number per deployment, with the change from the baseline (first target)."""
    from . import charts as V

    base_t, base_w = targets[0]
    others = targets[1:]
    changed, unchanged = [], []
    tally = {t.name: {"improved": 0, "worse": 0, "same": 0} for t, _ in others}
    for s in SYSTEMS:
        base_findings = {f.id: f for f in s.story(base_w).findings}
        other_findings = [{f.id: f for f in s.story(w).findings} for _, w in others]
        for fid, f in base_findings.items():
            cells = [f"[{fmt_metric(f.metric)}]({base_t.name}/{s.slug}.md#{f.anchor})"]
            moved = False
            for (t, _), found in zip(others, other_findings):
                g = found.get(fid)
                v = verdict(f.metric, g.metric if g else None, f.better)
                if v in tally[t.name]:
                    tally[t.name][v] += 1
                moved |= g is None or g.metric != f.metric
                mark = {"improved": "▲ ", "worse": "▼ ", "same": "= "}.get(v, "")
                value = fmt_metric(g.metric) if g else "—"
                cells.append(f'<span class="xu-{v}">{mark}{value}</span>' if g else "—")
            row = f"| {s.title} | {f.title} | {f.metric_label} | " + " | ".join(cells) + " |\n"
            (changed if moved else unchanged).append(row)
    head = ("| System | Finding (baseline) | Number | " + " | ".join(t.name for t, _ in targets) + " |\n"
            + "|---|---|---|" + "---|" * len(targets) + "\n")
    summary = "".join(f"**{t.name}** vs {base_t.name}: {c['improved']} improved, {c['worse']} worse, "
                      f"{c['same']} unchanged.\n\n" for t, c in ((t, tally[t.name]) for t, _ in others))
    out = ("\n## Scorecard {#scorecard}\n\n"
           f"Every finding's headline number, baseline **{base_t.label}** first. ▲ is an improvement and ▼ a "
           "regression, judged by each finding's direction; descriptive numbers have no arrow.\n\n" + summary)
    out += ("### What changed\n\n" + head + "".join(changed)) if changed else "No finding's number changed.\n\n"
    if unchanged:
        out += V.details(f"Unchanged findings ({len(unchanged)})", head + "".join(unchanged))
    return out
