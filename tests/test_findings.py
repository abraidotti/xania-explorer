import pytest

from xania_explorer.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_explorer.findings import Finding, first_sentence, fmt_metric, verdict
from xania_explorer.site.stories.common import finding
from xania_explorer.systems import SYSTEMS

needs_xania = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


def test_finding_from_section_and_anchor():
    f = finding("combat.xp-clock", "\n## Full XP needs time\n\nBody text. More.\n", metric=3, impact=3)
    assert f.title == "Full XP needs time" and f.anchor == "combat-xp-clock" and f.system == "combat"
    assert f.markdown().startswith("\n## Full XP needs time {#combat-xp-clock}")
    assert f.card_summary == "Body text."
    assert finding("x.empty", "") is None


def test_verdict_directions():
    assert verdict(10, 5, "lower") == "improved"
    assert verdict(10, 15, "lower") == "worse"
    assert verdict(10, 15, "higher") == "improved"
    assert verdict(10, 10, "lower") == "same"
    assert verdict(10, 15, "none") == "n/a"
    assert verdict(None, 15, "lower") == "n/a"


def test_fmt_metric():
    assert fmt_metric(1586305) == "1,586,305"
    assert fmt_metric(4.0) == "4"
    assert fmt_metric(12.63) == "12.6"
    assert fmt_metric(None) == "—"


def test_first_sentence_skips_markup():
    assert first_sentence("**Bold** start here. Second.\n\n<div>chart</div>") == "Bold start here."


@needs_xania
def test_every_system_has_unique_anchored_findings():
    world = load_world()
    ids = []
    for s in SYSTEMS:
        st = s.story(world)
        assert st.findings, s.slug
        page = st.markdown()
        for f in st.findings:
            assert f.id.startswith(s.slug + "."), f.id
            assert f"{{#{f.anchor}}}" in page
            assert 1 <= f.impact <= 3 and f.better in ("lower", "higher", "none")
            ids.append(f.id)
    assert len(ids) == len(set(ids))


@needs_xania
def test_dashboard_and_scorecard():
    from xania_explorer.paths import XaniaPaths
    from xania_explorer.site.dashboard import deployment_dashboard, issues, scorecard
    from xania_explorer.site.targets import Target

    world = load_world()
    found = issues(world)
    assert found and all(f.issue for _, f in found)
    assert [f.impact for _, f in found] == sorted((f.impact for _, f in found), reverse=True)
    dash = deployment_dashboard(world)
    s, f = found[0]
    assert f"({s.slug}.md#{f.anchor})" in dash
    t = Target("a", XaniaPaths.resolve())
    card = scorecard([(t, world), (Target("b", t.paths), world)])
    assert "No finding's number changed." in card  # same world on both sides
