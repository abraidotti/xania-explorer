"""Website generation: targets, page assembly, and chart specs that actually render."""

import json

import pytest

from xania_utils.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_utils.site import charts as V
from xania_utils.site.targets import format_targets, load_targets, parse_target

needs_xania = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


def test_parse_target_with_and_without_name(tmp_path):
    assert parse_target("fork=../xania").name == "fork"
    (tmp_path / "Xania").mkdir()
    assert parse_target(str(tmp_path / "Xania")).name == "xania"
    with pytest.raises(ValueError):
        parse_target("Bad Name=../xania")


def test_duplicate_target_names_rejected():
    with pytest.raises(ValueError):
        format_targets([parse_target("a=x"), parse_target("a=y")])


def test_load_targets_from_env(tmp_path):
    (tmp_path / "area").mkdir()
    (tmp_path / "area" / "area.lst").write_text("$\n")
    env = {"XANIA_TARGETS": format_targets([parse_target(f"one={tmp_path}")])}
    [t] = load_targets(env)
    assert t.name == "one" and t.paths.area_dir == tmp_path / "area"


def test_insert_after_heading_and_strip_histograms():
    md = "# T\n\n## 1. Supply\n\nIntro text.\n\n| a |\n|---|\n\n```\n x │██ 3\n```\n\n```\ncode\n```\n"
    out = V.strip_text_histograms(V.insert_after_heading(md, "## 1.", "<CHART>"))
    assert out.index("Intro text.") < out.index("<CHART>") < out.index("| a |")
    assert "│" not in out and "code" in out


def test_embed_is_valid_json_and_script_safe():
    html = V.embed(V.spec([{"x": "</script>"}], title="t", mark="bar"))
    payload = html.split('application/json">', 1)[1].rsplit("</script>", 1)[0]
    assert "</script>" not in payload
    assert json.loads(payload.replace("<\\/", "</"))["data"]["values"][0]["x"] == "</script>"


@needs_xania
def test_story_pages_lead_with_findings():
    """Key numbers first, each finding followed by its chart, tables tucked into details blocks."""
    from xania_utils.site.stories import mobs_page, weapons_page

    world = load_world()
    for page in (weapons_page(world), mobs_page(world)):
        assert page.index('class="xu-stats"') < page.index('class="xu-chart"')
        sections = page.split("\n## ")[1:]
        findings = [s for s in sections if not s.startswith(("Method", "Left out"))]
        assert len(findings) >= 4
        assert sum('class="xu-chart"' in s for s in findings) >= len(findings) - 1  # all but "can't obtain"
        assert "\n| " not in page.split("\n??? ")[0]  # no bare tables before the first details block
        assert '??? info "How these numbers are calculated"' in page


@needs_xania
def test_every_chart_renders():
    """Compile each chart with the real Vega-Lite engine (dev extra: vl-convert-python)."""
    vlc = pytest.importorskip("vl_convert")
    from xania_utils.paths import XaniaPaths
    from xania_utils.site.compare import render as render_compare
    from xania_utils.site.stories import mobs_page, weapons_page
    from xania_utils.site.targets import Target

    world = load_world()
    t = Target("a", XaniaPaths.resolve())
    pages = [weapons_page(world), mobs_page(world), render_compare([(t, world), (Target("b", t.paths), world)])]
    specs = [s for page in pages for s in V.extract_specs(page)]
    assert len(specs) >= 14
    for spec in specs:
        spec = {**spec, "width": 600}  # "container" needs a browser
        assert vlc.vegalite_to_svg(spec).startswith("<svg"), spec["title"]["text"]
