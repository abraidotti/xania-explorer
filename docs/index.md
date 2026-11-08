# How Xania works

Working notes and balance reports for assessing [Xania](https://github.com/mattgodbolt/xania). The guides give
formulas and point to the source; they aren't player guides.

## Guides

| Guide | Covers |
|---|---|
| [Architecture and game loop](01-architecture.md) | doorman/xania, config, boot order, pulses and timers, level bands, code map |
| [Area file format](02-area-file-format.md) | Full `.are` / `.prg` spec: every section and field, with fatal vs logged errors |
| [World model](03-world-model.md) | Prototypes vs instances, rooms and exits, reset timing and rules, shops, specials, mobprogs |
| [About the assessments](assessments.md) | How the level 1–91 balance reports are calculated |

Planned: characters (races, classes, stats), combat, skills and magic, items and economy, NPC behaviour,
persistence and admin.

## Reports

Reports are generated from each Xania checkout the site is built from. See [Xania versions](versions.md). Each
version has an overview, [assessments](assessments.md) with interactive charts, an area catalogue and CSV
downloads. When there's more than one version, a **Compare** page shows how they differ.

## Running it yourself

```
python -m pip install -e .[site]
python -m xania_utils serve                       # ../xania, live preview at http://127.0.0.1:8000
python -m xania_utils serve --target upstream=../xania-upstream --target fork=../xania
```

`serve` rebuilds whenever an area file changes. When the C++ loader changes, update the parser in
[xania_utils/areafile/](../xania_utils/areafile/) and the [area file format](02-area-file-format.md) guide
together. Each parser function cites the C++ function it ports.
