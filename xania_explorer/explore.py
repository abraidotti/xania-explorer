"""The in-browser explorer's Python side: which files to fetch, whether a repo is Xania, and the run itself.

The browser (docs/javascripts/explore.js) lists a GitHub commit's files, asks :func:`plan` what to download
(via the manifest the site build writes, see :func:`manifest`), writes the files into Pyodide's virtual file
system with a ``.xania-explorer.json`` identity file, then calls :func:`run`. The pages come from exactly the
same generators as the static site, so a live run and a prebuilt page for the same commit match.

Everything here and in what it imports is pure Python with the standard library only (enforced by a test),
except the optional Markdown-to-HTML step, which uses the ``markdown`` and ``pymdown-extensions`` wheels the
site ships alongside this package.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .systems import SYSTEMS

REQUIRED = "area/area.lst"
AREA_DIR = "area/"
MAX_AREA_FILE = 4_000_000  # bytes; Xania's largest area file is ~250 KB
# C++ files read by the systems (System.needs) and the bug checks; anything else in src/ is ignored.
BUG_CHECK_SOURCES = ("AFFECT_DATA.cpp", "Area.cpp", "VnumObjects.hpp", "apps/areas.cpp", "apps/map.cpp", "db.cpp",
                     "update.cpp")
SOURCE_FILES = tuple(sorted({f for s in SYSTEMS for f in s.needs} | set(BUG_CHECK_SOURCES)))
MARKDOWN_EXTENSIONS = ["tables", "admonition", "attr_list", "md_in_html", "toc", "pymdownx.superfences",
                       "pymdownx.details"]  # as in mkdocs.yml


@dataclass
class Plan:
    ok: bool
    error: str = ""
    files: list[str] = field(default_factory=list)  # repo-relative paths to download
    missing_sources: list[str] = field(default_factory=list)  # src/ files a system needs but the repo lacks
    unavailable: list[str] = field(default_factory=list)  # system titles that will show "unavailable"
    warning: str = ""


def plan(tree: list[dict] | list[str], repo: str = "this repository") -> Plan:
    """Decide what to download from a commit's file list (GitHub's git tree: ``path``, ``type``, ``size``).

    Fails early, before anything is downloaded, when the repo isn't a Xania checkout."""
    entries = [{"path": e, "type": "blob", "size": 0} if isinstance(e, str) else e for e in tree]
    blobs = {e["path"]: e for e in entries if e.get("type") == "blob"}
    if REQUIRED not in blobs:
        has_src = any(p.startswith("src/") for p in blobs)
        hint = (" It has a src/ folder but no area files, so it may be another MUD or a code-only fork."
                if has_src else "")
        return Plan(False, error=f"{repo} doesn't look like a Xania checkout: it has no {REQUIRED}.{hint}")
    files = [p for p, e in blobs.items()  # area/ itself, as boot_db reads it; dotfiles are never read
             if p.startswith(AREA_DIR) and "/" not in p[len(AREA_DIR):] and not p[len(AREA_DIR):].startswith(".")
             and (e.get("size") or 0) <= MAX_AREA_FILE]
    files += [f"src/{f}" for f in SOURCE_FILES if f"src/{f}" in blobs]
    missing = [f for f in SOURCE_FILES if f"src/{f}" not in blobs]
    unavailable = [s.title for s in SYSTEMS if _needs_any(s, set(missing))]
    warning = ""
    if unavailable:
        warning = (f"{len(missing)} of the C++ files the assessments read are missing, so "
                   f"{', '.join(unavailable)} won't be available. Older Xania branches kept these tables in other "
                   "files "
                   "(const.cpp, tables.cpp); a trimmed copy or another MUD would also lack them.")
    return Plan(True, files=sorted(files), missing_sources=missing, unavailable=unavailable, warning=warning)


def _needs_any(system, missing: set[str]) -> bool:
    from .systems import by_slug

    seen, todo = set(), [system.slug]
    while todo:
        s = by_slug(todo.pop())
        if s.slug in seen:
            continue
        seen.add(s.slug)
        if missing & set(s.needs):
            return True
        todo += s.uses
    return False


def manifest(prebuilt: list[dict] | None = None, version: str = "") -> dict:
    """What the browser needs before Pyodide starts: file rules, systems and the prebuilt deployments."""
    return {
        "version": version,  # site build id: cached results from older builds are discarded
        "required": REQUIRED, "areaDir": AREA_DIR, "maxAreaFile": MAX_AREA_FILE,
        "sourceFiles": list(SOURCE_FILES),
        "systems": [{"slug": s.slug, "title": s.title, "needs": list(s.needs), "uses": list(s.uses)}
                    for s in SYSTEMS],
        "prebuilt": prebuilt or [],
    }


def code_version() -> str:
    """A hash of this package's source: identifies the analysis, so cached results from other code are discarded
    and a stale explorer runtime can be detected."""
    import hashlib

    pkg = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for p in sorted(pkg.rglob("*.py")):
        h.update(p.relative_to(pkg).as_posix().encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def write_identity(root: Path | str, repo: str, branch: str, commit: str) -> None:
    from .paths import METADATA_FILE

    (Path(root) / METADATA_FILE).write_text(json.dumps({"repo": repo, "branch": branch, "commit": commit}),
                                      encoding="utf-8")


def run(sides: list[dict], *, catalogue: bool = True, progress=None) -> dict:
    """Analyse one or two checkouts. ``sides``: ``[{"root": path}, ...]`` (identity from .xania-explorer.json).

    Returns ``{"pages": {path: markdown}, "order": [...], "labels": {...}, "names": [...]}`` where paths are
    the static site's (``<name>/index.md``, ``<name>/combat.md``, ``compare.md``), so generated links work."""
    from .areafile.world import load_world
    from .gen import area_catalogue
    from .paths import XaniaPaths
    from .site import compare, pages as P, recommendations
    from .site.targets import Target, slug_for

    say = progress or (lambda *_: None)
    targets, pages, order, labels = [], {}, [], {}
    for i, side in enumerate(sides):
        paths = XaniaPaths.resolve(side["root"])
        name = side.get("name") or slug_for(paths.repo_slug, paths.branch, f"side{i + 1}")
        if any(t.name == name for t, _ in targets):
            name = f"{name}-{i + 1}"
        t = Target(name, paths)
        say(f"Loading the world for {t.side}")
        world = load_world(paths)
        targets.append((t, world))
        labels[name] = t.side
        for s in SYSTEMS:
            say(f"{t.side}: {s.title}")
            pages[f"{name}/{s.slug}.md"] = s.page(world)
            if s.available(world):
                pages[f"{name}/data/{s.slug}.csv"] = P.csv_text(s.assessment.write_csv, world)
        pages[f"{name}/index.md"] = P.overview_page(t, world, explore_link=False)
        pages[f"{name}/recommendations.md"] = recommendations.page(world)
        order += [f"{name}/index.md", f"{name}/recommendations.md"] + [f"{name}/{s.slug}.md" for s in SYSTEMS]
        if catalogue:
            pages[f"{name}/areas.md"] = area_catalogue.render_index(world)
            for area in world.areas:
                pages[f"{name}/areas/{area_catalogue.page_name(area)}"] = area_catalogue.render_area(world, area)
            order.append(f"{name}/areas.md")
    if len(targets) > 1:
        say("Comparing")
        pages["compare.md"] = compare.render(targets)
        order.insert(0, "compare.md")
    return {"pages": pages, "order": order, "labels": labels, "names": [t.name for t, _ in targets]}


def to_html(markdown_text: str) -> str:
    """Render one generated page with the site's Markdown extensions (needs the markdown wheels)."""
    import markdown

    return markdown.markdown(markdown_text, extensions=MARKDOWN_EXTENSIONS,
                             extension_configs={"toc": {"permalink": True}})


def run_json(sides_json: str, progress=None) -> str:
    """Pyodide entry point: JSON in, JSON out, with every page rendered to HTML (CSV files left as text)."""
    result = run(json.loads(sides_json), progress=progress)
    result["pages"] = {p: (to_html(md) if p.endswith(".md") else md) for p, md in result["pages"].items()}
    return json.dumps(result)


__all__ = ["Plan", "plan", "manifest", "run", "run_json", "to_html", "write_identity", "SOURCE_FILES"]
