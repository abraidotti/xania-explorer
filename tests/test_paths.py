"""Checkout identity: git-less copies carry it in .xania-explorer.json; targets are keyed by repo + branch."""

import json

from xania_explorer.paths import METADATA_FILE, XaniaPaths
from xania_explorer.site.targets import Target, slug_for


def test_metadata_file_gives_identity_without_git(tmp_path):
    (tmp_path / "area").mkdir()
    (tmp_path / METADATA_FILE).write_text(json.dumps(
        {"repo": "abraidotti/xania", "branch": "balance-pass", "commit": "0123456789abcdef"}))
    p = XaniaPaths.resolve(tmp_path)
    assert p.repo_slug == "abraidotti/xania"
    assert p.branch == "balance-pass" and p.commit == "0123456789abcdef"
    assert p.blob_url("src/fight.cpp") == "https://github.com/abraidotti/xania/blob/0123456789abcdef/src/fight.cpp"
    t = Target("head", p)
    assert t.side == "abraidotti/xania @ balance-pass"
    assert t.label == "head: abraidotti/xania @ balance-pass (0123456)"
    # a name derived from repo + branch isn't repeated
    assert Target("abraidotti-xania-balance-pass", p).label == "abraidotti/xania @ balance-pass (0123456)"


def test_two_branches_of_one_repo_get_distinct_names():
    a, b = slug_for("mattgodbolt/xania", "main", "x"), slug_for("mattgodbolt/xania", "feature/Combat-Tweak", "x")
    assert a == "mattgodbolt-xania-main"
    assert b == "mattgodbolt-xania-feature-combat-tweak"
    assert slug_for(None, None, "My Xania") == "my-xania"
