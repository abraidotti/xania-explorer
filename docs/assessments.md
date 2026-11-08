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

Once every system is assessed, a **recommendations** page will rank changes by impact × effort. It's regenerated
from the same data on every build, with no stored state.
