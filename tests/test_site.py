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
