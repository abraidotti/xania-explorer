"""Which Xania checkouts the website covers.

A *target* is a named Xania checkout, e.g. ``upstream=../xania-upstream`` and
``fork=../xania``. The CLI passes them to MkDocs in the ``XANIA_TARGETS``
environment variable (JSON); with no targets, the default checkout is used.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..paths import XaniaPaths, default_xania_dir

ENV_VAR = "XANIA_TARGETS"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class TargetSpec:
    name: str  # URL slug: lower-case letters, digits, - and _
    path: str


@dataclass(frozen=True)
class Target:
    name: str
    paths: XaniaPaths

    @property
    def side(self) -> str:
        """``owner/repo @ branch``: what identifies a deployment (two branches of one repo differ here)."""
        slug, branch = self.paths.repo_slug, self.paths.branch
        if not slug:
            return self.name
        return f"{slug} @ {branch}" if branch and branch != "HEAD" else slug

    @property
    def short(self) -> str:
        """A sidebar-sized name: ``Canonical · main``, ``abraidotti · balance`` (owner/repo when not "xania")."""
        from ..paths import CANONICAL_REPO

        slug, branch = self.paths.repo_slug, self.paths.branch
        if not slug:
            return self.name
        owner, _, repo = slug.partition("/")
        who = "Canonical" if slug == CANONICAL_REPO else owner if repo == "xania" else slug
        return f"{who} · {branch}" if branch and branch != "HEAD" else who

    @property
    def label(self) -> str:
        """e.g. ``upstream: mattgodbolt/xania @ main (82171fa)`` (parts omitted when unknown)."""
        commit = self.paths.commit
        named_after_side = self.name == slug_for(self.paths.repo_slug, self.paths.branch, "")
        label = self.side if named_after_side or self.side == self.name else f"{self.name}: {self.side}"
        return f"{label} ({commit[:7]})" if commit else label


def slug_for(repo: str | None, branch: str | None, fallback: str) -> str:
    """A URL-safe target name from repo + branch, e.g. ``mattgodbolt-xania-main``."""
    parts = [p for p in ((repo or "").replace("/", "-"), branch if branch and branch != "HEAD" else "") if p]
    name = re.sub(r"[^a-z0-9_-]+", "-", "-".join(parts).lower()).strip("-")
    return name or re.sub(r"[^a-z0-9_-]+", "-", fallback.lower()).strip("-") or "xania"


def parse_target(text: str) -> TargetSpec:
    """``NAME=PATH``, or just ``PATH`` (name from the checkout's repo and branch, else its folder name)."""
    name, sep, path = text.partition("=")
    if not sep:
        p = XaniaPaths.resolve(text)
        path, name = text, slug_for(p.repo_slug, p.branch, Path(text).resolve().name)
    name = name.strip().lower()
    if not _SLUG.match(name):
        raise ValueError(f"target name {name!r} must be lower-case letters, digits, '-' or '_'")
    return TargetSpec(name, path.strip())


def format_targets(specs: list[TargetSpec]) -> str:
    names = [s.name for s in specs]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate target names: {names}")
    return json.dumps([{"name": s.name, "path": str(Path(s.path).resolve())} for s in specs])


def load_targets(env: dict[str, str] | None = None) -> list[Target]:
    raw = (env or os.environ).get(ENV_VAR)
    specs = [TargetSpec(d["name"], d["path"]) for d in json.loads(raw)] if raw else \
        [parse_target(str(default_xania_dir()))]
    targets = [Target(s.name, XaniaPaths.resolve(s.path)) for s in specs]
    for t in targets:
        t.paths.check()
    return targets
