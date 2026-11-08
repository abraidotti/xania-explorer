"""Where the Xania checkout lives.

Everything in xania-explorer reads from one Xania checkout: ``area/`` for game
data and ``src/`` for tables that only exist in C++. By default that's a
``xania`` folder next to ``xania-explorer``; override with ``--xania PATH`` on the
command line or the ``XANIA_DIR`` environment variable.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIBLING_XANIA = REPO_ROOT.parent / "xania"
UPSTREAM_URL = "https://github.com/mattgodbolt/xania"


def default_xania_dir() -> Path:
    return Path(os.environ.get("XANIA_DIR") or SIBLING_XANIA)


@dataclass(frozen=True)
class XaniaPaths:
    root: Path
    area_dir: Path
    src_dir: Path

    @classmethod
    def resolve(cls, path: Path | str | None = None) -> "XaniaPaths":
        """Accept a Xania checkout root *or* an area directory (one containing area.lst)."""
        p = Path(path) if path is not None else default_xania_dir()
        if (p / "area.lst").exists():
            return cls(p.parent, p, p.parent / "src")
        return cls(p, p / "area", p / "src")

    def check(self) -> None:
        if not (self.area_dir / "area.lst").exists():
            raise FileNotFoundError(
                f"No Xania area files at {self.area_dir} (expected area.lst). "
                "Pass --xania PATH or set XANIA_DIR to a Xania checkout.")

    @property
    def has_src(self) -> bool:
        return (self.src_dir / "SkillTables.cpp").exists()

    def git(self, *args: str) -> str | None:
        try:
            out = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None

    @property
    def commit(self) -> str | None:
        return self.git("rev-parse", "HEAD")

    @property
    def branch(self) -> str | None:
        return self.git("rev-parse", "--abbrev-ref", "HEAD")

    @property
    def web_url(self) -> str | None:
        """https URL of the checkout's ``origin`` remote, if it's on GitHub."""
        remote = self.git("remote", "get-url", "origin")
        if not remote:
            return None
        if remote.startswith("git@github.com:"):
            remote = "https://github.com/" + remote.split(":", 1)[1]
        remote = remote.removesuffix(".git")
        return remote if remote.startswith("https://github.com/") else None

    @property
    def repo_slug(self) -> str | None:
        """``owner/repo`` of the GitHub ``origin`` remote, e.g. ``mattgodbolt/xania``."""
        url = self.web_url
        return url.removeprefix("https://github.com/") if url else None

    def blob_url(self, rel_path: str = "") -> str:
        """Link to a file in this checkout on GitHub, pinned to its commit when known."""
        base = self.web_url or UPSTREAM_URL
        return f"{base}/blob/{self.commit or 'main'}/{rel_path}".rstrip("/")
