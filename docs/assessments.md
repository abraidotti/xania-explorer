# About the assessments

Each assessment covers one game **system** and answers one question: **how balanced is it for a character levelling
from 1 to 91 (hero)?** The reports are generated for every [Xania version](versions.md) the site is built from.
Each has interactive charts and a CSV of the underlying data.

| System | Question | Builds on |
|---|---|---|
| Characters | How do classes and races grow, and what does each cost in XP? | — |
| Weapons | What weapons can each class find and wield at each level? | — |
| Equipment | How much armour and hitroll/damroll can a character wear at each level? | — |
| Combat & XP | What does a fight look like at each level, and how many kills does a level take? | Characters, Weapons, Equipment, Mobs |
| Skills & spells | What can each class learn as it levels, and do attack spells keep up? | Characters, Combat |
| Economy | Is the gold earned at each level enough for what there is to buy? | Combat, Equipment, Weapons |
| Levelling path | Where can a character of each level gain experience, and how much is there? | Combat |
| Mobs | Are mobs spread evenly over the levels, and is their toughness consistent? | — |
| Bugs | What's broken in the code, the area data and the content, and how do we fix it? | Weapons, Equipment, Mobs, Levelling path |

The Bugs system isn't about levels. It runs checks against the C++ source, the area data and the content. Code
checks look for a specific faulty pattern, so a branch that fixes a bug shows it as fixed (and Compare lists it
under "Bugs fixed or introduced"). Where a model ports C++ behaviour that a bug affects, it follows the
checkout's code. For example, Equipment's item-points rule counts AC bonuses once the AC bug is fixed.

Without the website, `python -m xania_explorer assess` writes the same reports as Markdown and CSV into `build/`.

## How a page reads

1. **Key numbers** at the top.
2. **One section per finding.** The heading states the finding, a short paragraph gives the evidence, and a chart
   shows it with the relevant part highlighted.
3. **Full tables** sit in collapsed "Details" blocks.
4. **The method** comes last.

All the wording is generated from the data, so it stays true as the game changes.

## Shared conventions

These live in [xania_explorer/assess/common.py](../xania_explorer/assess/common.py).

- **Levels** run from 1 to 91. Content above 91 (immortal/hero) is reported separately. Level-0 objects and mobs
  count as level 1.
- **Bands** are 5 levels wide (1–5, 6–10, …, 86–90, 91). Where a per-level view matters, it's shown as well.
- **Evenness** is measured over the bins with:
  - **CV** (stdev ÷ mean): 0 means perfectly even, and above ~0.5 is lumpy;
  - **Gini**: 0 means perfectly even, 1 means everything is in one bin;
  - range and number of empty bins.
- **Obtainable** means placed by at least one reset: shop stock, a mob drop, or on the floor or in a container
  ([sources.py](../xania_explorer/assess/sources.py)). Content no reset places is listed rather than counted.
- **Class views.** Class matters through skill *difficulty* (the per-class `skill_table` rating). It's the
  creation-point cost, and it divides practice and learn-by-use gains. Weapons shows a *start* view (what the
  class gets at creation) and an *easy* view (difficulty ≤ 3).
- **The reference character** for per-level models (Combat, Skills, Economy, Levelling) is a human with the
  class's default skill package, trains spent on stats and then HP, and the best gear the world offers at that
  level. It's an upper bound: real characters are less well equipped.
- **Expected values.** Models use expected values of the C++ random rolls, never simulations, so the same data
  always gives the same page.
- **Data comes from** the area files (via the [area parser](02-area-file-format.md)) and, for tables that only
  exist in C++, from extractors in [xania_explorer/source/](../xania_explorer/source/): skills and groups, classes,
  races and stat tables, and spell damage.

## Recommendations

Each version has a **Recommendations** page (under Reports). Every balance issue and bug can propose changes,
and each proposal states:

- **what to change and where:** the areas, items, mobs or C++ lines involved;
- **its expected effect,** computed from the same analysis as the finding (for example, by re-running the
  weapon curve with the proposed weapon added);
- **impact,** taken from the finding (1–3);
- **effort:**
    - **small:** a handful of edits or one constant;
    - **medium:** many area files, or one C++ formula or table;
    - **large:** new content or a new mechanic.

The page ranks recommendations by **impact × (4 − effort)**, so high impact for little work comes first. Each
recommendation also appears in a "What to change" box under its finding.

Some recommendations aim at a target that is a judgement call, such as "no race should cost more than 2× a
human's XP". The text names each target so it can be adjusted.

Nothing is stored: every build regenerates the list from the data, so a recommendation disappears once a version
no longer needs it. Compare lists which recommendations a version resolves or adds. The rules live next to the
findings they address, in [xania_explorer/site/stories/](../xania_explorer/site/stories/).
