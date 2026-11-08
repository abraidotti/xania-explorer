# xania-utils

Tools for documenting and assessing [Xania](https://github.com/mattgodbolt/xania). They read a Xania checkout's
data files directly (no C++ build needed) and produce a website of guides, level 1–91 balance reports with
interactive charts, an area catalogue, and a comparison between Xania versions (e.g. upstream vs your fork).

## Quick start

Put a Xania checkout next to this repo (`../xania`), then:

```
python -m venv .venv
.venv\Scripts\activate            # Windows   (source .venv/bin/activate elsewhere)
python -m pip install -e ".[dev,site]"

python -m xania_utils serve       # http://127.0.0.1:8000, rebuilds when area files change
```

To compare two versions, point at both checkouts. The first is the baseline:

```
python -m xania_utils serve --target upstream=../xania-upstream --target fork=../xania
```

## Commands

| Command | What it does |
|---|---|
| `serve [--target NAME=PATH ...]` | Build the website and serve it locally with live reload |
| `site [--target ...] [--out DIR] [--strict]` | Build the static website into `site/` |
| `check` | Load the world and list loader warnings and integrity problems (exit 1 if any would stop the MUD booting) |
| `assess [weapons\|mobs]` | Write the assessments as Markdown + CSV into `build/assessments/` |
| `docs` | Write the area catalogue as Markdown into `build/reference/` |

Every command takes `--xania PATH` (a checkout root or its `area/` dir) before the command name. Without it, the
default is `$XANIA_DIR`, or failing that `../xania`. `site`/`serve` use `--target` instead, so they can take
several versions.

## Published site

[.github/workflows/site.yml](.github/workflows/site.yml) checks out `mattgodbolt/xania` and your fork next to
this repo, runs the tests, builds the site with both as targets, and deploys it to GitHub Pages. It runs on every
push to `main`, nightly (to pick up new Xania commits), and on demand, where you can choose a branch or commit for
either checkout. Pull requests build the site but don't deploy it.

One-time setup:
1. Settings → Pages → Source: **GitHub Actions**.
2. Optionally, under Settings → Secrets and variables → Actions → Variables:
   - `XANIA_FORK_REPO` (default `<owner>/xania`);
   - `XANIA_FORK_REF` (default: the fork's default branch);
   - `XANIA_UPSTREAM_REF` (default `main`).

If the fork doesn't exist or isn't public, the site is built from upstream alone.

## Layout

```
docs/                             hand-written pages (guides); generated pages are added at build time
mkdocs.yml                        site config; hooks in xania_utils/site/hooks.py
xania_utils/paths.py              where the Xania checkout is (--xania / XANIA_DIR / ../xania)
xania_utils/areafile/             faithful port of Xania's area loader (reader, parser, model, world checks)
xania_utils/source/cpp_tables.py  skill/group tables extracted from xania/src/SkillTables.cpp
xania_utils/assess/               level-progression assessments (common stats, sources, weapons, mobs)
xania_utils/gen/area_catalogue.py area catalogue pages
xania_utils/site/                 website: targets, per-version pages, charts (Vega-Lite), compare, MkDocs hooks
```
