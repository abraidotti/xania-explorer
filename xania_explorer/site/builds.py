"""Builds made on GitHub: the fallback when a live explorer run is too slow or fails.

A maintainer runs the Site workflow with ``base_repo``/``base_ref`` (and optionally ``head_repo``/``head_ref``);
``python -m xania_explorer custom-build`` builds that version or comparison as a static site into
``<builds dir>/<slug>/`` with a ``build.json`` describing it, and keeps the newest :data:`KEEP`. The workflow stores
the folder on a ``builds`` branch (one commit, force-pushed) and every deploy copies it to ``/builds/``. Builds
reuse the main site's explorer runtime (``XANIA_RUNTIME_URL``) instead of carrying their own 14 MB copy.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..paths import REPO_ROOT, XaniaPaths
from .targets import Target, TargetSpec, format_targets, slug_for

KEEP = 20
INFO = "build.json"
ENV_DIR = "XANIA_BUILDS_DIR"  # read by the hooks: list builds on the Builds page and in the explorer manifest
SEPARATOR = "..."  # base...head, as in GitHub's compare URLs


def side_of(paths: XaniaPaths) -> dict[str, str]:
    return {"repo": paths.repo_slug or "", "branch": paths.branch or "", "commit": paths.commit or ""}


def build_slug(sides: list[dict[str, str]]) -> str:
    """``mattgodbolt-xania-main...abraidotti-xania-balance``; one side gives just its slug."""
    return SEPARATOR.join(slug_for(s["repo"], s["branch"], f"side{i + 1}") for i, s in enumerate(sides))


def custom_build(checkouts: list[Path], out_dir: Path, *, site_url: str = "", runtime_url: str = "../../",
                 run_url: str = "", keep: int = KEEP) -> Path:
    """Build one version, or a comparison of two, as a static site into ``out_dir/<slug>/``."""
    if not 1 <= len(checkouts) <= 2:
        raise ValueError("a build has one side (a version) or two (a comparison)")
    paths = [XaniaPaths.resolve(c) for c in checkouts]
    for p in paths:
        p.check()
    sides = [side_of(p) for p in paths]
    slug = build_slug(sides)
    dest = out_dir / slug
    if dest.exists():
        shutil.rmtree(dest)
    specs = [TargetSpec(slug_for(s["repo"], s["branch"], f"side{i + 1}"), str(p.root))
             for i, (s, p) in enumerate(zip(sides, paths))]
    if len(specs) == 2 and specs[0].name == specs[1].name:
        specs[1] = TargetSpec(specs[1].name + "-2", specs[1].path)
    env = dict(os.environ, XANIA_TARGETS=format_targets(specs), XANIA_RUNTIME_URL=runtime_url, XANIA_SKIP_RUNTIME="1",
               SITE_URL=f"{site_url.rstrip('/')}/builds/{slug}/" if site_url else "")
    env.pop(ENV_DIR, None)  # a build doesn't list other builds
    subprocess.run([sys.executable, "-m", "mkdocs", "build", "--strict", "-f", str(REPO_ROOT / "mkdocs.yml"),
                    "--site-dir", str(dest)], check=True, env=env, cwd=REPO_ROOT)
    labels = [Target(s.name, p).label for s, p in zip(specs, paths)]
    built = datetime.now(timezone.utc).isoformat(timespec="seconds")
    info = {"slug": slug, "sides": sides, "labels": labels, "built": built, "run": run_url}
    (dest / INFO).write_text(json.dumps(info, indent=1), encoding="utf-8")
    prune(out_dir, keep)
    return dest


def list_builds(out_dir: Path | str | None) -> list[dict]:
    """Saved builds, newest first."""
    if not out_dir or not Path(out_dir).is_dir():
        return []
    found = []
    for info in Path(out_dir).glob(f"*/{INFO}"):
        try:
            found.append(json.loads(info.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(found, key=lambda b: b.get("built", ""), reverse=True)


def prune(out_dir: Path, keep: int = KEEP) -> list[str]:
    """Delete all but the newest ``keep`` builds; returns the removed slugs."""
    removed = [b["slug"] for b in list_builds(out_dir)[keep:]]
    for slug in removed:
        shutil.rmtree(out_dir / slug, ignore_errors=True)
    return removed


def builds_page(builds: list[dict], site_repo: str) -> str:
    """The Builds page: every saved build, and how to request one."""
    workflow = f"https://github.com/{site_repo}/actions/workflows/site.yml" if site_repo else ""
    out = ["# Builds on GitHub\n\n",
           "Static builds of versions and comparisons that a maintainer requested from the Site workflow, usually "
           "because a [live run](explore.md) was too slow on their device. They're ordinary pages: instant and "
           f"searchable. The newest {KEEP} are kept.\n\n"]
    if builds:
        out.append("| Build | Commits | Built |\n|---|---|---|\n")
        for b in builds:
            title = " vs ".join(b.get("labels") or [b["slug"]])
            commits = " / ".join(s["commit"][:7] for s in b["sides"] if s.get("commit"))
            when = b.get("built", "")[:16].replace("T", " ")
            out.append(f'| <a href="{b["slug"]}/">{title}</a> | {commits} | {when} |\n')  # this page is /builds/
    else:
        out.append("No builds yet.\n")
    out.append("\n## Requesting a build\n\n"
               + (f"Maintainers can run the [Site workflow]({workflow}) with the inputs `base_repo`, `base_ref`, "
                  "`head_repo` and `head_ref` (head optional), or use the command the explorer shows. "
                  if workflow else "Run the Site workflow with `base_repo`, `base_ref`, `head_repo` and `head_ref`. ")
               + "The build appears here once the site redeploys, a few minutes later.\n")
    return "".join(out)
