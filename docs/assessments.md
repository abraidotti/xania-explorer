# About the assessments

Each assessment answers one question: **how balanced is this topic for a character levelling from 1 to 91
(hero)?** The reports are generated for every [Xania version](versions.md) the site is built from. Each has
interactive charts and a CSV of the underlying data.

| Report | Question |
|---|---|
| Weapons | What weapons can a character use at each level, how good are they, and does one class find suitable weapons more easily than another? |
| Mobs | Are mobs evenly spread across levels, does toughness rise smoothly, and do mobs match their area's level band? |

Without the website, `python -m xania_utils assess` writes the same reports as Markdown and CSV into `build/`.

## Shared conventions

These live in [xania_utils/assess/common.py](../xania_utils/assess/common.py).

- **Levels** run from 1 to 91. Content above 91 (immortal/hero) is reported separately. Level-0 objects and mobs
  count as level 1.
- **Bands** are 5 levels wide (1–5, 6–10, …, 86–90, 91). Where a per-level view matters, it's shown as well.
- **Evenness** is measured over the bins with:
  - **CV** (stdev ÷ mean): 0 means perfectly even, and above ~0.5 is lumpy;
  - **Gini**: 0 means perfectly even, 1 means everything is in one bin;
  - range and number of empty bins.
- **Obtainable** means placed by at least one reset: shop stock, a mob drop, or on the floor or in a container
  ([sources.py](../xania_utils/assess/sources.py)). Content no reset places is listed rather than counted.
- **Class views.** Class matters through skill *difficulty* (the per-class `skill_table` rating). It's the
  creation-point cost, and it divides practice and learn-by-use gains. Assessments show a *start* view (what the
  class gets at creation) and an *easy* view (difficulty ≤ 3).
- **Data comes from** the area files (via the [area parser](02-area-file-format.md)) and, for tables that only
  exist in C++, from [xania_utils/source/cpp_tables.py](../xania_utils/source/cpp_tables.py).
- Every report starts with **headline findings** and a **method** section, then gives distributions by level, and
  ends with lists of specific outliers to fix.

## Planned

Armour and other equipment, mob XP yield per level (with the combat guide), skills and spells by class, gold and
shop economy, and area coverage of the levelling path.
