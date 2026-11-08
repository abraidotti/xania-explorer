# Xania Explorer

Balance reports and working notes for [Xania](https://github.com/mattgodbolt/xania), the MUD Matt Godbolt and
friends ran in the late 1990s. The name tips its hat to his [Compiler Explorer](https://godbolt.org/): point it
at a Xania checkout and see what the code and data actually do. The guides give formulas and point to the
source; they aren't player guides.

## Guides

| Guide | Covers |
|---|---|
| [Architecture and game loop](01-architecture.md) | doorman/xania, config, boot order, pulses and timers, level bands, code map |
| [Area file format](02-area-file-format.md) | Full `.are` / `.prg` spec: every section and field, with fatal vs logged errors |
| [World model](03-world-model.md) | Prototypes vs instances, rooms and exits, reset timing and rules, shops, specials, mobprogs |
| [Characters](04-characters.md) | Creation, classes, races, stats, XP per level, levelling and practising |
| [Combat & experience](05-combat.md) | Rounds, hit chance, defences, damage pipeline, mob stats, XP per kill and the played-time clock |
| [Skills & magic](06-skills-and-magic.md) | The skill table, getting and improving skills, mana costs, saves and damage spells |
| [Items & economy](07-items-and-economy.md) | Wearing items, AC, the item-points rule (and its AC bug), where items and gold come from and go |
| [About the assessments](assessments.md) | How the level 1–91 balance reports are calculated |

Planned: NPC behaviour, persistence and admin.

## Reports

Reports are generated from each Xania checkout the site is built from. See [Xania versions](versions.md). Each
version has an overview, [assessments](assessments.md) with interactive charts, an area catalogue and CSV
downloads. When there's more than one version, a **Compare** page shows how they differ.

## Running it yourself

```
python -m pip install -e .[site]
python -m xania_explorer serve                       # ../xania, live preview at http://127.0.0.1:8000
python -m xania_explorer serve --target upstream=../xania-upstream --target fork=../xania
```

`serve` rebuilds whenever an area file changes. When the C++ loader changes, update the parser in
[xania_explorer/areafile/](../xania_explorer/areafile/) and the [area file format](02-area-file-format.md) guide
together. Each parser function cites the C++ function it ports.
