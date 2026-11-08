"""The in-browser explorer's runtime: a pinned Pyodide core and the wheels it installs, written into docs/runtime/.

``python -m xania_explorer bundle`` fetches the Pyodide core from the npm registry tarball (no Node needed),
builds this package's wheel and downloads the two pure-Python Markdown wheels, then writes
``runtime/wheels/index.json`` for the worker. MkDocs copies docs/runtime/ into the site like any static file,
so ``site``, ``serve`` and CI all get it; the folder is gitignored.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from ..paths import REPO_ROOT

PYODIDE_VERSION = "314.0.7"
PYODIDE_TARBALL = f"https://registry.npmjs.org/pyodide/-/pyodide-{PYODIDE_VERSION}.tgz"
# The core files loadPyodide needs; everything else in the package (consoles, type stubs, maps) is skipped.
PYODIDE_FILES = ("package.json", "pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip",
                 "pyodide-lock.json")
# Pure-Python wheels for Markdown -> HTML, pinned to what MkDocs uses here so pages render the same.
MARKDOWN_WHEELS = ("markdown", "pymdown-extensions")
RUNTIME_DIR = REPO_ROOT / "docs" / "runtime"
MAX_WHEEL_BYTES = 1024 * 1024


def _installed_version(dist: str) -> str:
    from importlib.metadata import version

    return version(dist)


def fetch_pyodide(dest: Path, source: Path | None = None) -> None:
    """Copy the Pyodide core into dest, from a local pyodide package dir or the npm tarball."""
    dest.mkdir(parents=True, exist_ok=True)
    if source:
        for name in PYODIDE_FILES:
            shutil.copy2(source / name, dest / name)
        return
    with urllib.request.urlopen(PYODIDE_TARBALL, timeout=120) as r:
        data = r.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for name in PYODIDE_FILES:
            member = tar.getmember(f"package/{name}")
            with tar.extractfile(member) as f, open(dest / name, "wb") as out:
                shutil.copyfileobj(f, out)


def build_wheels(dest: Path, own_only: bool = False) -> list[str]:
    """This package's wheel plus the Markdown wheels; returns the file names (also written to index.json).

    ``own_only`` rebuilds just this package's wheel (fast, offline), keeping the Markdown wheels."""
    from ..explore import code_version

    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.whl"):
        if not own_only or old.name.startswith("xania_explorer-"):
            old.unlink()
    pip = [sys.executable, "-m", "pip", "--disable-pip-version-check", "-q"]
    with tempfile.TemporaryDirectory() as tmp:  # build outside the source tree, so no build/ is left behind
        subprocess.run(pip + ["wheel", str(REPO_ROOT), "--no-deps", "-w", str(dest)], check=True, cwd=tmp,
                       stdout=subprocess.DEVNULL)
    if not own_only:
        pins = [f"{d}=={_installed_version(d)}" for d in MARKDOWN_WHEELS]
        subprocess.run(pip + ["download", "--no-deps", "--only-binary=:all:", "-d", str(dest), *pins], check=True)
    names = sorted(p.name for p in dest.glob("*.whl"))
    own = [n for n in names if n.startswith("xania_explorer-")]
    if len(own) != 1:
        raise RuntimeError(f"expected one xania_explorer wheel, found {own}")
    size = (dest / own[0]).stat().st_size
    if size > MAX_WHEEL_BYTES:
        raise RuntimeError(f"{own[0]} is {size / 1024:.0f} KB, over the {MAX_WHEEL_BYTES // 1024} KB budget")
    index = {"wheels": names, "pyodide": PYODIDE_VERSION, "code": code_version()}
    (dest / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return names


def bundle(out: Path = RUNTIME_DIR, pyodide_source: Path | None = None, skip_pyodide: bool = False) -> dict:
    if not skip_pyodide or not (out / "pyodide" / "pyodide.mjs").exists():
        fetch_pyodide(out / "pyodide", pyodide_source)
    wheels = build_wheels(out / "wheels")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    return {"dir": str(out), "wheels": wheels, "pyodide": PYODIDE_VERSION, "mb": round(size / 1e6, 1)}
