"""A checkout that isn't quite Xania degrades per system instead of failing the whole build."""

import pytest

from xania_explorer.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_explorer.site.pages import target_pages
from xania_explorer.site.targets import Target
from xania_explorer.systems import SYSTEMS, by_slug

from test_bugs import make

HAVE_XANIA = (DEFAULT_AREA_DIR / "area.lst").exists()


def test_no_cpp_marks_dependent_systems_unavailable(tmp_path):
    world = make(tmp_path, {})
    assert by_slug("weapons").missing(world) == ["SkillTables.cpp"]
    # combat builds on characters and weapons, so it inherits their missing files
    assert set(by_slug("combat").missing(world)) >= {"SkillTables.cpp", "Class.cpp"}
    assert by_slug("mobs").missing(world) == []
    for s in SYSTEMS:
        st = s.story(world)
        assert st.status in ("ok", "unavailable", "error"), (s.slug, st.note)  # a 1-room world may fail some
        assert st.markdown().startswith(f"# {s.title}")
    assert by_slug("combat").story(world).status == "unavailable"
    assert "src/SkillTables.cpp" in by_slug("combat").story(world).markdown()
    assert by_slug("bugs").story(world).status == "ok"


def test_every_page_renders_without_cpp(tmp_path):
    world = make(tmp_path, {})
    pages = target_pages(Target("mini", world.xania), world)
    assert "mini/index.md" in pages and "mini/combat.md" in pages
    assert "mini/data/bugs.csv" in pages and "mini/data/combat.csv" not in pages
    assert "Unavailable" in pages["mini/index.md"]


def test_an_unexpected_error_is_contained(tmp_path, monkeypatch):
    world = make(tmp_path, {})
    import xania_explorer.site.stories.mobs as mobs_story

    def boom(w):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(mobs_story, "mobs_story", boom)
    st = by_slug("mobs").story(world)
    assert st.status == "error" and "synthetic failure" in st.note
    assert by_slug("bugs").story(world).status == "ok"


@pytest.mark.skipif(not HAVE_XANIA, reason="xania checkout not found")
def test_real_checkout_has_every_system():
    world = load_world()
    assert all(s.missing(world) == [] for s in SYSTEMS)


@pytest.mark.skipif(not HAVE_XANIA, reason="xania checkout not found")
def test_scorecard_doesnt_count_unrunnable_checks_as_fixed(tmp_path):
    """Real areas but no C++: systems are 'not comparable' and unknown bug checks aren't improvements."""
    import shutil

    from xania_explorer.site.dashboard import scorecard

    base = load_world()
    shutil.copytree(DEFAULT_AREA_DIR, tmp_path / "area")
    head = load_world(tmp_path)
    out = scorecard([(Target("base", base.xania), base), (Target("head", head.xania), head)])
    assert "Not comparable: Characters, Weapons" in out
    changed = out.split("### What changed")[1].split("???")[0] if "### What changed" in out else ""
    assert "xu-improved" not in changed  # missing source isn't a fix
    bugs = by_slug("bugs").page(head)
    assert "The C++ checks couldn't run on this checkout" in bugs and "unknown, not fixed" in bugs
