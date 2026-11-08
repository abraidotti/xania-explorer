"""The game systems xania-utils assesses, in reading order.

Each system has an assessment module (``xania_utils.assess.<slug>``) providing
``render(world) -> Markdown`` and ``write_csv(world, path)``, and a website page
(``xania_utils.site.stories.<slug>``) providing ``<slug>_page(world) -> Markdown``.
The CLI, the website pages, the navigation and the version overview all read this list.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass


@dataclass(frozen=True)
class System:
    slug: str
    title: str
    question: str

    @property
    def assessment(self):
        return importlib.import_module(f"xania_utils.assess.{self.slug}")

    def page(self, world) -> str:
        module = importlib.import_module(f"xania_utils.site.stories.{self.slug}")
        return getattr(module, f"{self.slug}_page")(world)


SYSTEMS: list[System] = [
    System("characters", "Characters", "How do classes and races grow from level 1 to 91, and what does each cost?"),
    System("weapons", "Weapons", "What weapons can each class find and wield at each level?"),
    System("mobs", "Mobs", "Are mobs spread evenly over the levels, and is their toughness consistent?"),
]


def by_slug(slug: str) -> System:
    return next(s for s in SYSTEMS if s.slug == slug)
