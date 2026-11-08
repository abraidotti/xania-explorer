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

    nav = [{"Home": "index.md"}, {"Explore any repo": "explore.md"},
           {"Guides": [{"Architecture & game loop": "01-architecture.md"},
                       {"Area file format": "02-area-file-format.md"},
                       {"World model": "03-world-model.md"},
                       {"Characters": "04-characters.md"},
                       {"Combat & experience": "05-combat.md"},
                       {"Skills & magic": "06-skills-and-magic.md"},
                       {"Items & economy": "07-items-and-economy.md"},
                       {"About the assessments": "assessments.md"}]}]
    for t, _ in _targets:
        # The bare index.md first makes the section title itself link to the overview
        # (Material's navigation.indexes feature).
        nav.append({t.label: [f"{t.name}/index.md"]
                    + [{s.title: f"{t.name}/{s.slug}.md"} for s in SYSTEMS]
                    + [{"Area catalogue": f"{t.name}/areas.md"}]})
    if len(_targets) > 1:
        nav.append({"Compare": "compare.md"})
    if saved:
        nav.append({"Builds on GitHub": "builds.md"})
    config["nav"] = nav
    return config


def on_files(files: Files, config, **kwargs):
    if os.environ.get("XANIA_SKIP_RUNTIME"):  # saved builds use the main site's explorer runtime
        for f in [f for f in files if f.src_uri.startswith("runtime/")]:
            files.remove(f)
    for path, content in _generated.items():
        files.append(File.generated(config, path, content=content))
    return files


def on_page_markdown(markdown: str, page, config, files, **kwargs):
    if page.file.generated_by:
        return markdown
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

