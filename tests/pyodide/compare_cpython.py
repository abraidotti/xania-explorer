"""Check the Pyodide run matches CPython: same pages, same Markdown, for the same checkout.

    python tests/pyodide/compare_cpython.py XANIA_DIR PYODIDE_DUMP.json

The dump comes from ``budget.mjs --dump`` (whose first ``--xania`` must be XANIA_DIR; with a second side the dump
also holds that side's pages and the comparison, which aren't checked here). The CPython side copies the planned
files into a git-less folder with the same identity file, exactly as the browser does, so any difference is a
Pyodide behaviour difference.
"""

from __future__ import annotations

import difflib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from xania_explorer import explore as X


def main(xania: str, dump: str) -> int:
    src = Path(xania)
    pyo = json.loads(Path(dump).read_text(encoding="utf-8"))
    tree = [str(p.relative_to(src)).replace("\\", "/") for p in src.rglob("*") if p.is_file() and ".git" not in p.parts]
    git = lambda *a: subprocess.run(["git", "-C", str(src), *a], capture_output=True, text=True).stdout.strip()  # noqa: E731
    remote = git("remote", "get-url", "origin").replace("git@github.com:", "https://github.com/")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "side1"
        for f in X.plan(tree).files:
            (root / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src / f, root / f)
        X.write_identity(root, remote.removeprefix("https://github.com/").removesuffix(".git") or "local/xania",
                         git("rev-parse", "--abbrev-ref", "HEAD") or "main", git("rev-parse", "HEAD") or "0000000")
        cpy = X.run([{"root": str(root)}])["pages"]
    differ = sorted(p for p in cpy if cpy[p] != pyo.get(p))
    print(f"{len(cpy)} pages from CPython checked against Pyodide's; {len(differ)} differ")
    for p in differ[:3]:
        print("".join(list(difflib.unified_diff((cpy.get(p) or "").splitlines(True), (pyo.get(p) or "").splitlines(True),
                                                f"cpython/{p}", f"pyodide/{p}"))[:40]))
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
