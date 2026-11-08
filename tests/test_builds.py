"""'Build this on GitHub': slugs, the saved-builds list, pruning and the Builds page."""

import json

from xania_explorer.site import builds as B

from test_bugs import make


def save(out, slug, built, sides=None):
    (out / slug).mkdir(parents=True)
    (out / slug / B.INFO).write_text(json.dumps({"slug": slug, "built": built, "labels": [slug],
                                                 "sides": sides or [{"repo": "a/b", "branch": "main", "commit": "c" * 40}]}))


def test_build_slug_is_base_dot_dot_dot_head():
    sides = [{"repo": "mattgodbolt/xania", "branch": "main"}, {"repo": "abraidotti/xania", "branch": "feature/Tune"}]
    assert B.build_slug(sides) == "mattgodbolt-xania-main...abraidotti-xania-feature-tune"
    assert B.build_slug(sides[:1]) == "mattgodbolt-xania-main"


def test_list_and_prune_keep_the_newest(tmp_path):
    for i in range(5):
        save(tmp_path, f"b{i}", f"2026-11-0{i + 1}T10:00:00+00:00")
    (tmp_path / "not-a-build").mkdir()
    assert [b["slug"] for b in B.list_builds(tmp_path)] == ["b4", "b3", "b2", "b1", "b0"]
    assert B.prune(tmp_path, keep=2) == ["b2", "b1", "b0"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b3", "b4", "not-a-build"]
    assert B.list_builds(None) == [] and B.list_builds(tmp_path / "missing") == []


def test_builds_page_links_relative_to_builds(tmp_path):
    save(tmp_path, "x...y", "2026-11-08T10:00:00+00:00")
    page = B.builds_page(B.list_builds(tmp_path), "abraidotti/xania-explorer")
    assert '<a href="x...y/">' in page  # the page itself is served at /builds/
    assert "https://github.com/abraidotti/xania-explorer/actions/workflows/site.yml" in page
    assert "No builds yet" in B.builds_page([], "")


def test_custom_build_writes_a_static_site(tmp_path):
    """A real (small) MkDocs build of a one-room world, recorded in build.json."""
    import pytest

    pytest.importorskip("mkdocs")
    from xania_explorer.explore import write_identity

    (tmp_path / "co").mkdir()
    world = make(tmp_path / "co", {})
    write_identity(world.xania.root, "someone/xania", "main", "f" * 40)
    dest = B.custom_build([world.xania.root], tmp_path / "out", site_url="https://example.org/site")
    assert dest.name == "someone-xania-main"
    info = json.loads((dest / B.INFO).read_text())
    assert info["sides"] == [{"repo": "someone/xania", "branch": "main", "commit": "f" * 40}]
    assert (dest / "someone-xania-main" / "index.html").exists()
    assert not (dest / "runtime").exists()  # builds share the main site's runtime
    manifest = json.loads((dest / "explore-manifest.json").read_text())
    assert manifest["runtimeBase"] == "../../" and manifest["builds"] == []
