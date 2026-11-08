"""Findings-first assessment pages for the website.

Each page opens with a row of key numbers, then one section per finding: the
heading *is* the finding, a short paragraph gives the evidence, a chart shows
it (with the relevant part highlighted), and the full table sits in a
collapsed "Details" block. Method goes last, collapsed.

All wording is generated from the analysis, so it stays true as the game data
changes. The plain Markdown reports (``assess`` command) are unchanged.
"""

from __future__ import annotations

from ...assess import common as C
from ...findings import Finding, Recommendation, Story
from .. import charts as V

BAND_LABELS = [b.label for b in C.bands()]


def finding(fid: str, section: str, *, metric: float | None = None, label: str = "", better: str = "lower",
            impact: int = 1, issue: bool = True, summary: str = "",
            recs: list[Recommendation | None] = ()) -> Finding | None:
    """Turn a rendered section ('## Title' + body) into a Finding; empty sections give None.

    ``recs`` are the finding's recommendations (None entries, from rules that didn't fire, are dropped)."""
    md = section.lstrip("\n")
    if not md:
        return None
    assert md.startswith("## "), f"{fid}: section must start with a level-2 heading"
    title, _, body = md[3:].partition("\n")
    return Finding(id=fid, title=title.strip(), body=body, metric=metric, metric_label=label, better=better,
                   impact=impact, issue=issue, summary=summary,
                   recommendations=[r for r in recs if r] if issue else [])


def rec(rid: str, title: str, change: str, effect: str, *, effort: int = 2, kind: str = "data",
        impact: int = 0) -> Recommendation:
    return Recommendation(rid, title, change.strip(), effect.strip(), effort, kind, impact)


def story(slug: str, title: str, intro: str, tiles: str, findings: list[Finding | None], method: str,
          preamble: str = "", appendix: str = "") -> Story:
    return Story(slug, title, intro, tiles, [f for f in findings if f], V.details(
        "How these numbers are calculated", method, kind="info") if method else "", preamble, appendix)
MUTED = "#b8ab9c"
HIGHLIGHT = "#e4572e"


def _plural(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def _a(phrase: str) -> str:
    """'a knight' / 'an elf mage'."""
    return ("an " if phrase[:1].lower() in "aeiou" else "a ") + phrase


def _span(r: tuple[int, int]) -> str:
    return str(r[0]) if r[0] == r[1] else f"{r[0]}–{r[1]}"


def _list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]




def edit_effort(areas: int, items: int = 0) -> int:
    """Effort of editing existing area data: a few files is small, a dozen medium, more is a project."""
    return 1 if areas <= 3 and items <= 15 else 2 if items <= 60 else 3


def by_area(names: list[str], top: int = 4) -> str:
    """'12 in UnderDark, 5 in Drow City and 9 more in 4 other areas'."""
    from collections import Counter

    counts = Counter(names).most_common()
    shown = [f"{n} in {area}" for area, n in counts[:top]]
    rest = counts[top:]
    if rest:
        shown.append(f"{sum(n for _, n in rest)} more in {_plural(len(rest), 'other area')}")
    return _list(shown)


def src_link(world, file: str, needle: str) -> str:
    """A Markdown link to the first line of ``src/<file>`` containing ``needle`` (plain path if not found)."""
    path = world.src_dir / file
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return f"`src/{file}`"
    line = next((i for i, text in enumerate(lines, 1) if needle in text), None)
    if line is None:
        return f"`src/{file}`"
    return f"[`src/{file}:{line}`]({world.xania.blob_url('src/' + file)}#L{line})"
