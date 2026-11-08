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
    needs: tuple[str, ...] = ()  # C++ files under src/ this system reads directly
    uses: tuple[str, ...] = ()  # other systems whose analyses it builds on

    def missing(self, world) -> list[str]:
        """C++ files this system (or anything it builds on) needs that the checkout lacks."""
        seen, todo, out = set(), [self.slug], []
        while todo:
            s = by_slug(todo.pop())
            if s.slug in seen:
                continue
            seen.add(s.slug)
            out += [f for f in s.needs if not (world.src_dir / f).exists() and f not in out]
            todo += s.uses
        return out

    def available(self, world) -> bool:
        return not self.missing(world) and self.story(world).status == "ok"

    @property
    def assessment(self):
        return importlib.import_module(f"xania_explorer.assess.{self.slug}")

    def story(self, world):
        """The system's findings-first story (xania_explorer.findings.Story), cached per world."""
        store = world.__dict__.setdefault("_story_cache", {})
        if self.slug not in store:
            store[self.slug] = self._build_story(world)
        return store[self.slug]

    def _build_story(self, world):
        """Run the system in isolation: missing C++ files or an unexpected error give a placeholder story
        for this system only, so every other page still renders."""
        from .findings import Story

        missing = self.missing(world)
        if missing:
            files = ", ".join(f"`src/{f}`" for f in missing)
            return Story(self.slug, self.title, self.question, "", status="unavailable",
                         note=f"This checkout has no {files}, which the {self.title} assessment needs. Older "
                              "Xania branches kept these tables in other files (const.cpp, tables.cpp); a trimmed "
                              "copy or another MUD would also lack them.")
        try:
            module = importlib.import_module(f"xania_explorer.site.stories.{self.slug}")
            return getattr(module, f"{self.slug}_story")(world)
        except Exception as e:  # noqa: BLE001 - isolate each system
            return Story(self.slug, self.title, self.question, "", status="error",
                         note=f"The {self.title} assessment failed on this checkout: `{type(e).__name__}: {e}`. "
                              "The other systems are unaffected.")

    def page(self, world) -> str:
        return self.story(world).markdown()


SYSTEMS: list[System] = [
    System("characters", "Characters", "How do classes and races grow from level 1 to 91, and what does each cost?",
           needs=("Class.cpp", "Races.cpp", "Stats.cpp")),
    System("weapons", "Weapons", "What weapons can each class find and wield at each level?",
           needs=("SkillTables.cpp",)),
    System("equipment", "Equipment", "How much armour and hitroll/damroll can a character wear at each level?",
           uses=("weapons", "mobs")),
    System("combat", "Combat & XP", "What does a fight look like at each level, and how many kills does a level take?",
           needs=("SkillTables.cpp",), uses=("characters", "weapons", "equipment", "mobs")),
    System("skills", "Skills & spells", "What can each class learn as it levels, and do attack spells keep up?",
           needs=("SkillTables.cpp", "magic.cpp"), uses=("characters", "combat", "mobs")),
    System("economy", "Economy", "Is the gold earned at each level enough for what there is to buy?",
           uses=("combat", "equipment", "weapons")),
    System("levelling", "Levelling path", "Where can a character of each level gain experience, and how much is there?",
           uses=("combat",)),
    System("mobs", "Mobs", "Are mobs spread evenly over the levels, and is their toughness consistent?"),
    System("bugs", "Bugs", "What's broken in the code, the area data and the content, and how do we fix it?"),
]


def by_slug(slug: str) -> System:
    return next(s for s in SYSTEMS if s.slug == slug)
