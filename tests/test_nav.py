"""The site's navigation: tabs, the systems listed once, short version names and the version switcher."""

import json

import pytest

from xania_explorer.paths import METADATA_FILE, XaniaPaths
from xania_explorer.site import hooks
from xania_explorer.site.targets import Target
from xania_explorer.systems import SYSTEMS


def _target(tmp_path, name, repo, branch):
    root = tmp_path / name
    (root / "area").mkdir(parents=True)
    (root / METADATA_FILE).write_text(json.dumps({"repo": repo, "branch": branch, "commit": "0123456789"}))
    return Target(name, XaniaPaths.resolve(root))


@pytest.fixture
def two(tmp_path, monkeypatch):
    targets = [(_target(tmp_path, "base", "mattgodbolt/xania", "main"), None),
               (_target(tmp_path, "fork", "abraidotti/xania", "balance"), None)]
    monkeypatch.setattr(hooks, "_targets", targets)
    return targets


def test_short_names(tmp_path):
    assert _target(tmp_path, "a", "mattgodbolt/xania", "main").short == "Canonical · main"
    assert _target(tmp_path, "b", "abraidotti/xania", "balance").short == "abraidotti · balance"
    assert _target(tmp_path, "c", "someone/xania-legacy", "main").short == "someone/xania-legacy · main"


def test_colliding_short_names_fall_back_to_repo_and_branch(tmp_path, monkeypatch):
    monkeypatch.setattr(hooks, "_targets", [(_target(tmp_path, "a", "x/xania", "main"), None),
                                            (_target(tmp_path, "b", "x/xania", "main"), None)])
    assert set(hooks._short_names().values()) == {"x/xania @ main"}


def test_nav_is_tabs_with_systems_listed_once(two):
    nav = hooks._nav(has_builds=False)
    assert [next(iter(item)) for item in nav] == ["Home", "Reports", "Compare", "Explore", "Guides"]
    reports = nav[1]["Reports"]
    assert reports[0] == {"Versions": [{"Canonical · main": "base/index.md"}, {"abraidotti · balance": "fork/index.md"}]}
    assert reports[1] == {"Recommendations": "base/recommendations.md"}
    systems = reports[2]["Systems"]
    assert len(systems) == len(SYSTEMS) + 1  # plus the area catalogue
    assert all(path.startswith("base/") for entry in systems for path in entry.values())
    explore = hooks._nav(has_builds=True)[3]["Explore"]
    assert [next(iter(e)) for e in explore] == ["Explore any repo", "Builds on GitHub"]


def test_switcher_links_the_same_page_and_falls_back_for_missing_areas(two):
    have = {"base/combat.md", "fork/combat.md", "base/areas.md", "fork/areas.md", "fork/areas/arachnos.md"}
    bar = hooks.switcher("fork/combat.md", have.__contains__)
    assert "Viewing **fork: abraidotti/xania @ balance (0123456)**" in bar
    assert "[Canonical · main](../base/combat.md)" in bar
    # an area the other version lacks links to its catalogue
    assert "(../../base/areas.md)" in hooks.switcher("fork/areas/arachnos.md", have.__contains__)
    assert hooks.switcher("compare.md", have.__contains__) == ""


def test_other_versions_sidebar_browses_that_version(two):
    page = type("P", (), {"file": type("F", (), {"src_uri": "fork/combat.md"})()})()
    html = ('<li class="md-nav__item"><a href="../../base/mobs/" class="md-nav__link">'
            '<a href="../../base/" class="md-nav__link">'
            '<li class="md-nav__item md-nav__item--active">\n  <a href="../../base/combat/" class="md-nav__link">')
    out = hooks.on_post_page(html, page, {})
    assert 'href="../../fork/mobs/"' in out
    assert 'href="../../base/"' in out  # the baseline's overview stays put
    assert 'href="../../fork/combat/" class="md-nav__link md-nav__link--active"' in out


def test_home_page_placeholders(two, monkeypatch):
    from xania_explorer import paths

    monkeypatch.setattr(hooks, "home_summary", lambda targets: "\n## At a glance\n")
    page = (paths.REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    both = hooks._home(page)
    assert "@base" not in both and "@systems" not in both and "@other" not in both
    assert "](base/recommendations.md)" in both and "[Compare](compare.md)" in both
    assert "fork: abraidotti/xania @ balance" in both
    monkeypatch.setattr(hooks, "_targets", two[:1])
    alone = hooks._home(page)
    assert "compare.md" not in alone and "if-compare" not in alone  # no Compare tab with one version
