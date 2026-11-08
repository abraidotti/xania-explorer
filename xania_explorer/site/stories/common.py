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
from .. import charts as V

BAND_LABELS = [b.label for b in C.bands()]
MUTED = "#b8ab9c"
HIGHLIGHT = "#b4532a"


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


