"""Recommendations: generated next to their findings, ranked by impact × effort, and never stored."""

import re

import pytest

from xania_explorer.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_explorer.findings import EFFORT_NAME, KIND_NAME
from xania_explorer.site import recommendations as R
from xania_explorer.site.dashboard import recommendation_changes
from xania_explorer.systems import SYSTEMS, by_slug

pytestmark = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


@pytest.fixture(scope="module")
def world():
    return load_world()


@pytest.fixture(scope="module")
def recs(world):
    return R.collect(world)


def test_every_recommendation_is_well_formed(recs):
    assert len(recs) >= 10
    ids = [r.id for _, _, r in recs]
    assert len(ids) == len(set(ids)), "recommendation ids must be unique"
    for s, f, r in recs:
        assert r.finding_id == f.id and r.system == s.slug
        assert f.issue, f"{r.id}: only issues get recommendations"
        assert r.impact in (1, 2, 3) and r.effort in EFFORT_NAME and r.kind in KIND_NAME
        assert r.title and r.change and r.effect
        assert "None" not in r.change + r.effect and "nan" not in r.effect, r.id


def test_ranked_by_impact_times_effort(recs):
    scores = [r.score for _, _, r in recs]
    assert scores == sorted(scores, reverse=True)
    assert all(r.score == r.impact * (4 - r.effort) for _, _, r in recs)


def test_links_resolve(world, recs):
    """The page has an anchor for every recommendation, and every 'What to change' link points at one."""
    page = R.page(world)
    anchors = set(re.findall(r"\{#([\w-]+)\}", page))
    for s, f, r in recs:
        assert r.anchor in anchors
        assert f"](recommendations.md#{r.anchor})" in by_slug(s.slug).page(world)
        assert f"]({s.slug}.md#{f.anchor})" in page  # the evidence link


def test_each_change_is_listed_once(recs):
    """A bug fix another system already recommends (with its computed effect) isn't repeated under Bugs."""
    ids = {r.id for _, _, r in recs}
    if "equipment.ac-not-counted.fix-worth" in ids:
        assert "bugs.code.affect-worth-ac" not in ids


def test_fixing_the_data_removes_the_recommendation(world, recs):
    """Stateless: bring every over-cap weapon within the cap and its recommendation is gone, and the comparison
    reports it as resolved."""
    from xania_explorer.assess import weapons as W

    assert any(r.id == "weapons.over-cap.lower-dice" for _, _, r in recs)
    fixed = load_world()
    for w in W.collect(fixed):
        while w.over_cap and int(w.obj.values[2]) > 1:
            w.obj.values[2] = int(w.obj.values[2]) - 1
            w = W.Weapon(w.obj, w.type, w.sources)  # fresh, so nothing cached survives
    after = {r.id for _, _, r in R.collect(fixed)}
    assert "weapons.over-cap.lower-dice" not in after

    class T:
        def __init__(self, name):
            self.name = name
            self.label = name

    text = recommendation_changes([(T("before"), world), (T("after"), fixed)])
    assert "Bring" in text and "▲ resolved" in text


def test_unavailable_systems_are_flagged(world, monkeypatch):
    from xania_explorer.findings import Story

    real = SYSTEMS[0].story
    monkeypatch.setattr(type(SYSTEMS[0]), "story",
                        lambda self, w: Story(self.slug, self.title, "", "", status="unavailable")
                        if self.slug == "characters" else real.__func__(self, w))
    page = R.page(world)
    assert "Characters couldn't run on this checkout" in page
