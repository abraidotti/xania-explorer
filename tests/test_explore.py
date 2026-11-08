"""The in-browser explorer's Python side: repo validation, file selection, stdlib-only runs."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from xania_explorer import explore as X

REPO_ROOT = Path(__file__).resolve().parents[1]
XANIA_TREE = ["README.md", "area/.gitignore", "area/area.lst", "area/Midgaard.are", "area/version.are", "area/mobprogs/x.prg",
              "src/SkillTables.cpp", "src/Class.cpp", "src/fight.cpp"]


def test_non_xania_repo_is_rejected_before_download():
    p = X.plan(["README.md", "package.json", "src/index.js"], "someone/webapp")
    assert not p.ok and p.files == []
    assert "someone/webapp doesn't look like a Xania checkout" in p.error and "area/area.lst" in p.error
    assert "another MUD" in p.error  # has src/ but no areas


def test_plan_picks_area_files_and_known_sources():
    p = X.plan([{"path": f, "type": "blob", "size": 100} for f in XANIA_TREE] + [{"path": "area", "type": "tree"}])
    assert p.ok
    assert "area/area.lst" in p.files and "area/Midgaard.are" in p.files and "area/version.are" in p.files
    assert "area/mobprogs/x.prg" not in p.files  # only area/ itself, as boot_db reads it
    assert "area/.gitignore" not in p.files
    assert "src/SkillTables.cpp" in p.files and "src/fight.cpp" not in p.files
    assert "Races.cpp" in p.missing_sources
    assert "Characters" in p.unavailable and "Mobs" not in p.unavailable
    assert "won't be available" in p.warning


def test_oversized_area_file_is_skipped():
    p = X.plan([{"path": "area/area.lst", "type": "blob", "size": 10},
                {"path": "area/huge.are", "type": "blob", "size": X.MAX_AREA_FILE + 1}])
    assert p.ok and "area/huge.are" not in p.files


def test_manifest_is_json_and_lists_every_system():
    m = json.loads(json.dumps(X.manifest(version="abc")))
    assert m["required"] == "area/area.lst" and m["version"] == "abc"
    assert "SkillTables.cpp" in m["sourceFiles"] and len(m["systems"]) >= 9


def test_run_uses_identity_and_needs_only_the_stdlib(tmp_path):
    """Runs the explorer with site-packages disabled (python -I -S), as Pyodide has nothing else installed."""
    (tmp_path / "area").mkdir()
    (tmp_path / "area" / "area.lst").write_text("Mini.are\n$\n")
    from test_bugs import AREA

    (tmp_path / "area" / "Mini.are").write_text(AREA)
    script = textwrap.dedent(f"""
        import sys, json
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from xania_explorer import explore as X
        X.write_identity({str(tmp_path)!r}, "someone/xania", "feature/x", "abcdef1234567")
        r = X.run([{{"root": {str(tmp_path)!r}}}])
        banned = [m for m in sys.modules if m.split(".")[0] in ("markdown", "pymdownx", "mkdocs", "yaml")]
        print(json.dumps({{"names": r["names"], "labels": r["labels"], "pages": sorted(r["pages"]), "banned": banned}}))
    """)
    out = subprocess.run([sys.executable, "-I", "-S", "-c", script], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r["names"] == ["someone-xania-feature-x"]
    assert r["labels"] == {"someone-xania-feature-x": "someone/xania @ feature/x"}
    assert "someone-xania-feature-x/index.md" in r["pages"] and "someone-xania-feature-x/bugs.md" in r["pages"]
    assert r["banned"] == []


def test_same_repo_two_branches_compare(tmp_path):
    from test_bugs import AREA

    sides = []
    for branch in ("main", "balance"):
        root = tmp_path / branch
        (root / "area").mkdir(parents=True)
        (root / "area" / "area.lst").write_text("Mini.are\n$\n")
        (root / "area" / "Mini.are").write_text(AREA)
        X.write_identity(root, "mattgodbolt/xania", branch, branch * 3)
        sides.append({"root": str(root)})
    r = X.run(sides, catalogue=False)
    assert r["names"] == ["mattgodbolt-xania-main", "mattgodbolt-xania-balance"]
    assert r["order"][0] == "compare.md"
    assert "mattgodbolt/xania @ balance" in r["pages"]["compare.md"]


def test_html_rendering_keeps_anchors_and_cards():
    html = X.to_html('## Title {#combat-xp}\n\n<div class="xe-card-grid" markdown>\n\n**[x](combat.md#a)**\n\n</div>\n')
    assert 'id="combat-xp"' in html and 'href="combat.md#a"' in html and "<strong>" in html
