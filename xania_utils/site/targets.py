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
    def label(self) -> str:
        commit = self.paths.commit
        return f"{self.name} @ {commit[:7]}" if commit else self.name


def parse_target(text: str) -> TargetSpec:
    """``NAME=PATH`` or just ``PATH`` (name = folder name)."""
    name, sep, path = text.partition("=")
    if not sep:
        path, name = text, Path(text).resolve().name
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
