# Xania Explorer

Xania Explorer reads a [Xania MUD](https://github.com/mattgodbolt/xania) checkout (its area files and C++ source) and
reports how balanced the game is for a character levelling from 1 to 91, what's broken, and what to change. It
only reads Xania; nothing here changes the game. This site covers **@base-label**<!-- if-compare --> and compares it
with **@other-labels**<!-- /if-compare -->, and the live explorer can check any other repo or branch.

## What's on this site {#whats-here}

<div class="xe-card-grid xe-home-grid" markdown>

<div class="xe-system-card" markdown>

**[Reports](@base/index.md)**

<span class="xe-card-label">The findings, for each Xania version.</span>

Each version has a **dashboard** of its most pressing issues, a ranked list of **recommendations**, one page per
**system** (@systems) and an **area catalogue**.

</div>

<!-- if-compare -->
<div class="xe-system-card" markdown>

**[Compare](compare.md)**

<span class="xe-card-label">The versions side by side.</span>

A scorecard of every finding, with what improved or got worse, which bugs were fixed or introduced, and which
recommendations a version resolves.

</div>
<!-- /if-compare -->

<div class="xe-system-card" markdown>

**[Explore](explore.md)**

<span class="xe-card-label">Any public repo or branch, live.</span>

Runs the same reports in your browser for a fork or branch you choose, or compares two of them. Nothing to install.

</div>

<div class="xe-system-card" markdown>

**[Guides](01-architecture.md)**

<span class="xe-card-label">How the game works, from the C++.</span>

Reference for the formulas and rules behind every report: areas, combat, skills, items, NPCs and administration,
with links to the source.

</div>

</div>

## Where to start {#where-to-start}

| If you want to know… | Go to |
|---|---|
| What's most wrong with the game | the [dashboard](@base/index.md#top-issues) of @base-label |
| What to change first | [Recommendations](@base/recommendations.md), ranked by impact and effort |
| What's broken in the code or data | [Bugs](@base/bugs.md), each with a fix |
| How hard an area is, or what's in it | [Area difficulty](@base/difficulty.md) and the [area catalogue](@base/areas.md) |
| Whether a branch makes things better | <!-- if-compare -->[Compare](compare.md), or <!-- /if-compare -->the [live explorer](explore.md) for any branch |
| How something works in the code | the [Guides](01-architecture.md) |

## How to read a report {#how-to-read}

Every system page answers one question, such as "What weapons can each class find and wield at each level?":

- **Key numbers** come first.
- **Each heading is a finding**, stated as a conclusion ("Barbarians wait 23 levels for a better weapon"),
  followed by the evidence: a sentence or two, an interactive chart, and the full table in a collapsed block.
- **"What to change"** boxes under a finding link to its recommendations.
- **The Method** at the end says exactly how the numbers are calculated, and what's assumed.

Everything is regenerated from the data on every build, so the pages always describe the current code. More in
[About the assessments](assessments.md).

??? info "The words this site uses"

    | Term | Meaning |
    |---|---|
    | Version | One Xania checkout: a repo at a branch and commit, such as `mattgodbolt/xania @ main` |
    | System | One part of the game assessed as a whole: Characters, Weapons, Combat & XP, Bugs… |
    | Finding | One conclusion about a system, with its evidence. Balance issues are rated high, medium or minor impact |
    | Recommendation | A change that would address a finding, with its expected effect computed from the same data, and its effort: small, medium or large |
    | Bug status | **present** (the fault is there and the data triggers it), **latent** (the faulty code is there, but no data triggers it yet), **fixed**, **clean** (nothing found) or **unknown** (the source it checks isn't in this version) |
    | Level band | Five levels, such as 21–25; level 91 is hero, the top mortal level |

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
| [NPC behaviour](08-npc-behaviour.md) | Aggression and its level ceiling, assisting, fleeing, wandering, regeneration, special procedures, mob programs |
| [Persistence & admin](09-persistence-and-admin.md) | What survives a reboot, when players are saved, objects that are never saved, immortal levels, bans and logs |
| [About the assessments](assessments.md) | How the level 1–91 balance reports are calculated |

??? note "Running it yourself"

    ```
    python -m pip install -e .[site]
    python -m xania_explorer serve                       # ../xania, live preview at http://127.0.0.1:8000
    python -m xania_explorer serve --target upstream=../xania-upstream --target fork=../xania
    ```

    `serve` rebuilds whenever an area file changes. When the C++ loader changes, update the parser in
    [xania_explorer/areafile/](../xania_explorer/areafile/) and the [area file format](02-area-file-format.md) guide
    together. Each parser function cites the C++ function it ports.
