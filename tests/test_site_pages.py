"""Every registered game system gets a findings-first page whose charts all render."""

import pytest

from xania_utils.areafile.world import DEFAULT_AREA_DIR, load_world
from xania_utils.site import charts as V
from xania_utils.systems import SYSTEMS

pytestmark = pytest.mark.skipif(not (DEFAULT_AREA_DIR / "area.lst").exists(), reason="xania checkout not found")


@pytest.fixture(scope="module")
def world():
    return load_world()


@pytest.fixture(scope="module")
def pages(world):
    return {s.slug: s.page(world) for s in SYSTEMS}


@pytest.mark.parametrize("slug", [s.slug for s in SYSTEMS])
def test_page_leads_with_findings(pages, slug):
    """Key numbers first, each finding followed by its chart, tables tucked into details blocks."""
    page = pages[slug]
    assert page.index('class="xu-stats"') < page.index('class="xu-chart"')
    sections = page.split("\n## ")[1:]
    findings = [s for s in sections if not s.startswith(("Method", "Left out"))]
    assert len(findings) >= 4
    charted = sum('class="xu-chart"' in s for s in findings)
    assert charted >= 3 and charted >= len(findings) - 2  # short text-only findings are fine, but few
    assert "\n| " not in page.split("\n??? ")[0]  # no bare tables before the first details block
    assert '??? info "How these numbers are calculated"' in page


@pytest.mark.parametrize("slug", [s.slug for s in SYSTEMS])
def test_assessment_markdown_and_csv(world, slug, tmp_path):
    mod = next(s for s in SYSTEMS if s.slug == slug).assessment
    assert "Headline findings" in mod.render(world)
    mod.write_csv(world, tmp_path / "out.csv")
    assert len((tmp_path / "out.csv").read_text(encoding="utf-8").splitlines()) > 1


@pytest.mark.parametrize("slug", [s.slug for s in SYSTEMS] + ["compare"])
def test_every_chart_renders(world, pages, slug):
    """Compile each chart with the real Vega-Lite engine (dev extra: vl-convert-python)."""
    vlc = pytest.importorskip("vl_convert")
    if slug == "compare":
        from xania_utils.paths import XaniaPaths
        from xania_utils.site.compare import render as render_compare
        from xania_utils.site.targets import Target

        t = Target("a", XaniaPaths.resolve())
        page = render_compare([(t, world), (Target("b", t.paths), world)])
    else:
        page = pages[slug]
    specs = V.extract_specs(page)
    assert specs
    for spec in specs:
        spec = {**spec, "width": 600}  # "container" needs a browser
        assert vlc.vegalite_to_svg(spec).startswith("<svg"), spec["title"]["text"]
