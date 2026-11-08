"""The game systems xania-explorer assesses, in reading order.

Each system has an assessment module (``xania_explorer.assess.<slug>``) providing
``render(world) -> Markdown`` and ``write_csv(world, path)``, and a website page
(``xania_explorer.site.stories.<slug>``) providing ``<slug>_page(world) -> Markdown``.
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
        return importlib.import_module(f"xania_explorer.assess.{self.slug}")

    def story(self, world):
        """The system's findings-first story (xania_explorer.findings.Story), cached per world."""
        store = world.__dict__.setdefault("_story_cache", {})
        if self.slug not in store:
            module = importlib.import_module(f"xania_explorer.site.stories.{self.slug}")
            store[self.slug] = getattr(module, f"{self.slug}_story")(world)
        return store[self.slug]

    def page(self, world) -> str:
        return self.story(world).markdown()


SYSTEMS: list[System] = [
    System("characters", "Characters", "How do classes and races grow from level 1 to 91, and what does each cost?"),
    System("weapons", "Weapons", "What weapons can each class find and wield at each level?"),
    System("equipment", "Equipment", "How much armour and hitroll/damroll can a character wear at each level?"),
    System("combat", "Combat & XP", "What does a fight look like at each level, and how many kills does a level take?"),
    System("skills", "Skills & spells", "What can each class learn as it levels, and do attack spells keep up?"),
    System("economy", "Economy", "Is the gold earned at each level enough for what there is to buy?"),
    System("levelling", "Levelling path", "Where can a character of each level gain experience, and how much is there?"),
    System("mobs", "Mobs", "Are mobs spread evenly over the levels, and is their toughness consistent?"),
    System("bugs", "Bugs", "What's broken in the code, the area data and the content, and how do we fix it?"),
]


def by_slug(slug: str) -> System:
    return next(s for s in SYSTEMS if s.slug == slug)
