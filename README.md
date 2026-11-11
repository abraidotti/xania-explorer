<a id="readme-top"></a>

```text
  /    \    /    \
  \     \  /     /
   \     \/     /
    \          /  A N I A Explorer
    /    /\    \
   /    /  \    \
  /    /    \    \
  \   /      \   /
```

[![Site][site-shield]][site-url]
[![License][license-shield]][license-url]
[![Python][python-shield]][python-url]

<br />
<div align="center">
  <h3 align="center">Xania Explorer</h3>

  <p align="center">
    How Xania plays from level 1 to 91: balance reports, bug checks and guides, read straight from a checkout.
  </p>

  <h2 align="center">
    <a href="https://abraidotti.github.io/xania-explorer/">abraidotti.github.io/xania-explorer »</a>
  </h2>

  <p align="center">
    The reports for <code>mattgodbolt/xania</code> and my fork, side by side, rebuilt every night.
    <br />
    <br />
    <a href="https://abraidotti.github.io/xania-explorer/explore/">Explore any repo</a>
    &middot;
    <a href="https://abraidotti.github.io/xania-explorer/assessments/">How the reports work</a>
    &middot;
    <a href="https://github.com/abraidotti/xania-sim">Xania Sim</a>
  </p>
</div>

<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

## About The Project

Xania Explorer reads a [Xania](https://github.com/mattgodbolt/xania) checkout, its area files and its C++ source,
and reports how the game plays for a character levelling from 1 to 91. It only reads Xania: nothing here changes
the game, and no build is needed.

The [site](https://abraidotti.github.io/xania-explorer/) is rebuilt every night from `mattgodbolt/xania` and my
fork. For each version it has:

* **one report per game system** (characters, weapons, equipment, combat, skills and spells, economy, levelling,
  mobs, area difficulty, bugs), each answering one question across levels 1 to 91, with charts and CSVs;
* **a dashboard** and **recommendations**, ranked by impact and effort;
* **an area catalogue**: every area's mobs, objects, shops and difficulty.

It also **compares** two versions finding by finding, can **explore any public repo** in the browser, and has
**guides** to how Xania works, written from the source.

The numbers come from Xania's own formulas, as expected values: a port of the area loader reads the world, and the
tables that live in the C++ are read from `src/`, so a branch is analysed as it is. Bug checks look for specific
faulty patterns in the code, so a fix shows up as fixed. [How the reports work](https://abraidotti.github.io/xania-explorer/assessments/)
covers the method, its conventions and what the models leave out.

### Built With

* Python 3.12, standard library only for the analysis, so it also runs in the browser
* [MkDocs](https://www.mkdocs.org/) with [Material](https://squidfunk.github.io/mkdocs-material/) for the site
* [Vega-Lite](https://vega.github.io/vega-lite/) for the charts
* [Pyodide](https://pyodide.org) for the in-browser explorer

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Getting Started

### Prerequisites

* Python 3.12 or later
* A Xania checkout (no build needed), by default next to this repo at `../xania`

### Installation

1. Clone this repo next to your Xania checkout:
   ```sh
   git clone https://github.com/abraidotti/xania-explorer.git
   cd xania-explorer
   ```
2. Install it:
   ```sh
   python -m venv .venv
   source .venv/bin/activate          # .venv\Scripts\activate on Windows
   python -m pip install -e ".[site]"
   ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Usage

Serve the site locally (it rebuilds when area files change):

```sh
python -m xania_explorer serve
```

Compare two checkouts, the first being the baseline:

```sh
python -m xania_explorer serve --target upstream=../xania-upstream --target mine=../xania
```

Without the site:

```sh
python -m xania_explorer check     # loader warnings and integrity problems; exit 1 if the MUD wouldn't boot
python -m xania_explorer assess    # every report as Markdown and CSV, in build/assessments/
```

`--xania PATH`, before the command, points at another checkout.

Other tools can use [`xania_explorer/api.py`](xania_explorer/api.py), its stable interface: Xania Sim takes its
routes and fight and spell predictions from there.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Roadmap

- [x] Reports for ten game systems, recommendations, Compare, the in-browser explorer
- [x] Rooms only some levels can enter (Mud School, hero-only rooms)
- [x] Immunities, resistances and vulnerabilities; hidden and invisible mobs
- [x] Bug checks for problems Xania Sim found in play
- [ ] Weight limits, and how far players really practise their skills
- [ ] Areas whose advertised level range promises more than their mobs offer
- [ ] What each weapon flag is worth, and which damage types pay off against which mobs
- [ ] What Xania Sim's bots saw, beside the predictions

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Acknowledgments

* [Xania](https://github.com/mattgodbolt/xania) and its developers
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template), which this README follows

<p align="right">(<a href="#readme-top">back to top</a>)</p>

[site-shield]: https://img.shields.io/github/actions/workflow/status/abraidotti/xania-explorer/site.yml?branch=main&label=site&style=for-the-badge
[site-url]: https://abraidotti.github.io/xania-explorer/
[license-shield]: https://img.shields.io/github/license/abraidotti/xania-explorer?style=for-the-badge
[license-url]: LICENSE
[python-shield]: https://img.shields.io/badge/python-3.12%2B-blue?style=for-the-badge
[python-url]: https://www.python.org/
