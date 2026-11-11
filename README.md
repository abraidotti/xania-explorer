# Xania Explorer

Xania Explorer reads a [Xania](https://github.com/mattgodbolt/xania) checkout, its area files and its C++ source,
and reports how the game plays for a character levelling from 1 to 91: where the balance is off, what's broken,
and what to change. It only reads Xania. Nothing here changes the game, and no build of Xania is needed.

**The site: https://abraidotti.github.io/xania-explorer/**, rebuilt every night from `mattgodbolt/xania` and my
fork, with the two compared side by side.

## What you'll find

For each Xania version:

- **A dashboard** of the most pressing findings, and **recommendations**, ranked by impact and effort.
- **One page per game system**, each answering one question across levels 1-91, with charts and the data
  behind them as CSV:

  | System | Question |
  |---|---|
  | Characters | How do classes and races grow, and what does each cost in XP? |
  | Weapons | What weapons can each class find and wield at each level? |
  | Equipment | How much armour and hitroll/damroll can a character wear at each level? |
  | Combat & XP | What does a fight look like at each level, and how many kills does a level take? |
  | Skills & spells | What can each class learn as it levels, and do attack spells keep up? |
  | Economy | Is the gold earned at each level enough for what there is to buy? |
  | Levelling path | Where can a character of each level gain experience, and how much is there? |
  | Mobs | Are mobs spread evenly over the levels, and is their toughness consistent? |
  | Area difficulty | How hard is each area for the characters it serves, and what does it pay? |
  | Bugs | What's broken in the code, the area data and the content, and how do we fix it? |

- **An area catalogue**: every area's mobs, objects, shops, specials and mob programs, and how hard it is for
  the levels it serves.

Across versions:

- **Compare**: a scorecard of every finding between two versions (say, upstream and a branch): what improved or
  got worse, which bugs were fixed or introduced.
- **Explore any repo**: the same analysis for any public Xania repo and branch, run in your browser.
- **Guides** to how Xania works, written from the source: the game loop, the area file format, the world model,
  characters, combat, skills and magic, items and the economy, NPC behaviour, persistence and administration.

## How it works

**Reading the world.** A port of Xania's area loader reads the files in `area.lst` order, the way `db.cpp` does,
and reports the same warnings and fatal errors the MUD would at boot. Tables that live in the C++ (the skill table,
classes, races, stat tables, spell damage, specials, attack types) are read straight from `src/`, so a branch that
changes them is analysed as it is.

**Modelling it.** The assessments use expected values from Xania's own formulas: hit chances, parry, dodge and
block, damage, extra attacks, XP per kill, mob specials, mobs assisting each other, a caster's buffs and spells, and
mobs' immunities, resistances and vulnerabilities. Each formula names the C++ it comes from. A level-L character is
a human of each class with the best gear the world offers at L, fighting the mobs within two levels that it can
reach, see and hurt. It's a model, not a simulation. [Xania Sim](https://github.com/abraidotti/xania-sim) plays the
real game and checks the model against what actually happens.

**What it leaves out.** Weight limits on gear; how far players actually practise their skills (it assumes 75%
when learned, rising to 100% by level 30); mob skills like bash in fights; mobs wandering away from where they
spawn; sneak; portals and mob programs when finding routes; players trading or grouping. Each page's Method
section says what that page assumes.

**Writing it up.** Every page leads with its findings. Each finding is a sentence generated from the data, with the
evidence and a chart below it, so the wording stays true as the game changes. Bug checks come in two kinds:
narrow patterns in the C++ (each one confirmed by reading the code), and checks on the loaded data and content.
A code check reports a bug as `present` until its pattern goes away, then as `fixed`, so a branch that fixes a bug
shows it on Compare.

## Running it yourself

Python 3.12 or later. Put a Xania checkout next to this repo (`../xania`), then:

```
python -m venv .venv
source .venv/bin/activate            # .venv\Scripts\activate on Windows
python -m pip install -e ".[dev,site]"

python -m xania_explorer serve       # the site at http://127.0.0.1:8000, rebuilt when area files change
```

To compare two checkouts, the first being the baseline:

```
python -m xania_explorer serve --target upstream=../xania-upstream --target mine=../xania
```

| Command | What it does |
|---|---|
| `serve [--target NAME=PATH ...]` | Build the site and serve it locally, with live reload |
| `site [--target ...] [--out DIR]` | Build the static site into `site/` |
| `check` | Load the world and list loader warnings and integrity problems (exit 1 if any would stop the MUD booting) |
| `assess [SYSTEM ...]` | Write the assessments as Markdown and CSV into `build/assessments/` |
| `docs` | Write the area catalogue as Markdown into `build/reference/` |

`--xania PATH` (before the command) points at another checkout, or its `area/` directory; otherwise
`$XANIA_DIR`, then `../xania`. `site` and `serve` take `--target` instead, so they can show several versions.

**In the browser.** The site's Explore page runs this same package with [Pyodide](https://pyodide.org): it fetches
a repo's files from GitHub and builds the pages locally, so a live run matches the prebuilt pages. The analysis
is pure Python, standard library only, to keep that possible. If a device is too slow for it, the repo's Site
workflow can build any version or comparison on GitHub instead.

**From other tools.** [`xania_explorer/api.py`](xania_explorer/api.py) is the stable interface, used by Xania Sim
for routes and predictions:

```python
from xania_explorer import api
world = api.load_world("../xania")
api.path(world, api.RECALL_ROOM, 3054, level=20)              # walking steps a level-20 character can take
api.predict_fight(world, "knight", 10, 110)                   # expected rounds, damage taken, xp
api.predict_spell(world, "mage", "burning hands", 20, 13, mob_vnum=2804)   # damage, with that mob's tolerance
```
