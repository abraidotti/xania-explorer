"""MkDocs hooks: generate the per-target pages in memory at build time.

Configured in mkdocs.yml (``hooks:``). Nothing generated is written into
docs/, so the repo only contains hand-written pages; ``mkdocs serve`` also
watches the Xania checkouts and rebuilds when area files change.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import posixpath
import re

from mkdocs.structure.files import File, Files

# Absolute imports: MkDocs loads this file as a standalone module, not as part of the package.
from xania_explorer import explore
from xania_explorer.areafile.world import load_world
from xania_explorer.site import builds, compare, pages
from xania_explorer.site.dashboard import home_summary
from xania_explorer.site.targets import Target, load_targets
from xania_explorer.source import character_tables, cpp_tables
from xania_explorer.systems import SYSTEMS

log = logging.getLogger("mkdocs.plugins.xania_explorer")
# The explorer's Pyodide runtime is ES modules (.mjs). Windows' registry often maps .mjs to text/plain, which
# browsers refuse to run as a module, so `mkdocs serve` would break the explorer there.
mimetypes.add_type("text/javascript", ".mjs")

_targets: list[tuple[Target, object]] = []
_generated: dict[str, str] = {}

# Hand-written docs link to source with paths that work when browsing the repo
# (../../xania/src/db.cpp#L395, ../xania_explorer/...). On the site, point them at GitHub.
_XANIA_LINK = re.compile(r"\]\((?:\.\./)+xania/([^)]*)\)")
_UTILS_LINK = re.compile(r"\[([^\]]*)\]\((?:\.\./)+(xania_explorer/[^)]*)\)")


def on_config(config, **kwargs):
    global _targets, _generated
    cpp_tables.load_skills.cache_clear()  # serve rebuilds re-read the C++ tables
    cpp_tables.load_groups.cache_clear()
    character_tables.cache_clear()
    targets = load_targets()
    _targets = []
    _generated = {}
    for t in targets:
        log.info("xania_explorer: loading %s from %s", t.label, t.paths.root)
        world = load_world(t.paths)
        _targets.append((t, world))
        _generated.update(pages.target_pages(t, world))
    if len(_targets) > 1:
        _generated["compare.md"] = compare.render(_targets)
    _generated["versions.md"] = _versions_page()
    site_repo = (config.get("repo_url") or "").rstrip("/").removeprefix("https://github.com/")
    saved = builds.list_builds(os.environ.get(builds.ENV_DIR))
    _generated["builds.md"] = builds.builds_page(saved, site_repo)
    manifest = explore.manifest(
        prebuilt=[{"name": t.name, "repo": t.paths.repo_slug, "branch": t.paths.branch, "commit": t.paths.commit,
                   "label": t.label} for t, _ in _targets],
        version=explore.code_version())
    manifest.update(siteRepo=site_repo, runtimeBase=os.environ.get("XANIA_RUNTIME_URL", ""),
                    builds=[{"slug": b["slug"], "sides": b["sides"], "labels": b.get("labels", []),
                             "built": b.get("built", "")} for b in saved])
    _generated["explore-manifest.json"] = json.dumps(manifest)

    config["nav"] = _nav(bool(saved))
    # Pages that are a whole tab on their own (Home, Compare, Explore without builds)
    _single_page_tabs.clear()
    _single_page_tabs.update(v for item in config["nav"] for v in item.values() if isinstance(v, str))
    return config


_single_page_tabs: set[str] = set()


def _short_names() -> dict[str, str]:
    """Sidebar names per target; the full ``owner/repo @ branch`` when two short names would collide."""
    shorts = [t.short for t, _ in _targets]
    return {t.name: t.short if shorts.count(t.short) == 1 else t.side for t, _ in _targets}


def _nav(has_builds: bool) -> list:
    """Top-level tabs: Home · Reports · Compare · Explore · Guides.

    Reports lists each version's overview, then the systems once, as the baseline's pages. On another
    version's page, :func:`on_post_page` points those links at that version, so the sidebar always browses the
    version being read; the switcher at the top of each report page changes version."""
    short = _short_names()
    nav: list = [{"Home": "index.md"}]
    if _targets:
        base = _targets[0][0].name
        nav.append({"Reports": [
            {"Versions": [{short[t.name]: f"{t.name}/index.md"} for t, _ in _targets]},
            {"Systems": [{s.title: f"{base}/{s.slug}.md"} for s in SYSTEMS]
             + [{"Area catalogue": f"{base}/areas.md"}]},
            {"About the assessments": "assessments.md"},
        ]})
    if len(_targets) > 1:
        nav.append({"Compare": "compare.md"})
    nav.append({"Explore": [{"Explore any repo": "explore.md"}, {"Builds on GitHub": "builds.md"}]}
               if has_builds else {"Explore": "explore.md"})
    nav.append({"Guides": [{"Architecture & game loop": "01-architecture.md"},
                           {"Area file format": "02-area-file-format.md"},
                           {"World model": "03-world-model.md"},
                           {"Characters": "04-characters.md"},
                           {"Combat & experience": "05-combat.md"},
                           {"Skills & magic": "06-skills-and-magic.md"},
                           {"Items & economy": "07-items-and-economy.md"}]})
    return nav


def _version_of(src_uri: str) -> tuple[str, str] | None:
    """``("fork", "combat.md")`` for a page inside a version's folder, else None."""
    head, sep, rest = src_uri.partition("/")
    return (head, rest) if sep and any(t.name == head for t, _ in _targets) else None


def _nav_equivalent(rest: str) -> str:
    """The baseline page whose sidebar entry stands for this page of a version (area pages → the catalogue)."""
    return "areas.md" if rest.startswith("areas/") else rest


_lit: list = []  # sidebar entries lit for the page being rendered, switched off again in on_post_page


def on_page_context(context, page, config, nav, **kwargs):
    """Light up the sidebar entries for a version page: the version being read (under Versions) and, for a page
    that isn't itself in the nav (another version's system pages, every area page), its Systems entry."""
    found = _version_of(page.file.src_uri)
    if found and _targets:
        lit = {f"{found[0]}/index.md"}
        if found[1] != "index.md":  # an overview is its own Versions entry, not a system
            lit.add(f"{_targets[0][0].name}/{_nav_equivalent(found[1])}")
        for p in nav.pages:
            if p.file.src_uri in lit and p is not page:
                p.active = True
                _lit.append(p)
    return context


_NAV_LINK = re.compile(r'<a href="((?:\.\./)*)([a-z0-9_-]+)/([a-z0-9_-]+)/" class="md-nav__link')
# A lit entry that isn't the page itself: Material marks its <li> active but not its link.
_LIT_ITEM = re.compile(r'(<li class="md-nav__item md-nav__item--active">\s*<a href="[^"]*" class="md-nav__link)"')


def on_post_page(output: str, page, config, **kwargs):
    while _lit:
        _lit.pop().active = False
    found = _version_of(page.file.src_uri)
    if not found or not _targets:
        return output
    output = _LIT_ITEM.sub(r'\1 md-nav__link--active"', output)
    version, base = found[0], _targets[0][0].name
    if version == base:
        return output
    return _NAV_LINK.sub(lambda m: (f'<a href="{m[1]}{version}/{m[3]}/" class="md-nav__link' if m[2] == base
                                    else m[0]), output)


def on_files(files: Files, config, **kwargs):
    if os.environ.get("XANIA_SKIP_RUNTIME"):  # saved builds use the main site's explorer runtime
        for f in [f for f in files if f.src_uri.startswith("runtime/")]:
            files.remove(f)
    for path, content in _generated.items():
        files.append(File.generated(config, path, content=content))
    return files


def on_page_markdown(markdown: str, page, config, files, **kwargs):
    if page.file.src_uri in _single_page_tabs:  # a one-link sidebar is noise: give the page the width
        page.meta.setdefault("hide", []).append("navigation")
    if page.file.generated_by:
        return _with_switcher(markdown, page.file.src_uri, files)
    xania = _targets[0][0].paths if _targets else None
    if xania:
        markdown = _XANIA_LINK.sub(lambda m: f"]({xania.blob_url(m.group(1))})", markdown)
    repo = (config.get("repo_url") or "").rstrip("/")
    if repo:
        markdown = _UTILS_LINK.sub(lambda m: f"[{m.group(1)}]({repo}/blob/main/{m.group(2)})", markdown)
    else:  # no repo to link to (local build without SITE_REPO_URL): show the path as code
        markdown = _UTILS_LINK.sub(lambda m: f"`{m.group(2)}`", markdown)
    if page.file.src_uri == "index.md" and _targets:
        # Put each deployment's top balance issues up front, before the guides.
        summary = home_summary(_targets)
        marker = "\n## Guides"
        markdown = markdown.replace(marker, summary + marker, 1) if marker in markdown else markdown + summary
    return markdown


def switcher(src_uri: str, exists) -> str:
    """The bar under a version page's title: which version this is (full label) and the same page in the
    others. ``exists(path)`` says whether a page exists; an area another version lacks links to its catalogue."""
    found = _version_of(src_uri)
    if not found:
        return ""
    version, rest = found
    short = _short_names()
    here = next(t for t, _ in _targets if t.name == version)
    links = []
    for t, _ in _targets:
        if t.name == version:
            continue
        dest = next(p for p in (f"{t.name}/{rest}", f"{t.name}/{_nav_equivalent(rest)}", f"{t.name}/index.md")
                    if exists(p))
        rel = posixpath.relpath(dest, posixpath.dirname(src_uri))
        links.append(f'[{short[t.name]}]({rel}){{ .xe-version-link title="{t.label}" }}')
    switch = (" · Same page in " + " · ".join(links)) if links else ""
    return (f'\n<div class="xe-version-switch" markdown>\n\nViewing **{here.label}**{switch}\n\n</div>\n')


def _with_switcher(markdown: str, src_uri: str, files: Files) -> str:
    bar = switcher(src_uri, lambda p: files.get_file_from_path(p) is not None)
    if not bar:
        return markdown
    m = _H1.search(markdown)
    return markdown[:m.end()] + bar + markdown[m.end():] if m else bar + markdown


_H1 = re.compile(r"^# .*\n", re.MULTILINE)


def on_serve(server, config, builder, **kwargs):
    for t, _ in _targets:
        server.watch(str(t.paths.area_dir))
        if t.paths.has_src:
            server.watch(str(t.paths.src_dir / "SkillTables.cpp"))
    return server


def _versions_page() -> str:
    lines = ["# Xania versions on this site\n\n",
             "| Version | Checkout | Commit | Reports |\n|---|---|---|---|\n"]
    for t, w in _targets:
        commit = t.paths.commit
        lines.append(f"| **{t.name}** | `{t.paths.root.name}` | {commit[:10] if commit else '—'} | "
                     f"[overview]({t.name}/index.md) · "
                     + " · ".join(f"[{s.title.lower()}]({t.name}/{s.slug}.md)" for s in SYSTEMS)
                     + f" · [areas]({t.name}/areas.md) |\n")
    if len(_targets) > 1:
        lines.append("\nSee [Compare](compare.md) for differences between them.\n")
    return "".join(lines)

