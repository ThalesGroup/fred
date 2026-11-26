# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import base64
import io
import threading
import time
import xml.etree.ElementTree as StdElementTree  # nosec B405 - serialization registry only
from pathlib import Path

import pytest
from defusedxml import ElementTree
from PIL import Image

from knowledge_flow_backend.core.processors.input.fast_text_processor import svg_summary
from knowledge_flow_backend.core.processors.input.fast_text_processor.svg_summary import _self_contained, svg_facts, svg_png_data_url

NS = 'xmlns="http://www.w3.org/2000/svg"'
PLAN_SVG = f"""<svg {NS} viewBox="0 0 200 100" width="200" height="100">
  <style>.wall {{ fill: #1A2B3C; stroke: #ff0000 }} .room {{ fill: #eeeeee }}</style>
  <title>Floor plan</title>
  <rect id="kitchen" class="wall" x="0" y="0" width="10" height="10"/>
  <rect class="wall" x="20" y="0" width="10" height="10"/>
  <rect class="room" x="40" y="0" width="10" height="10"/>
  <circle fill="#00FF00" cx="5" cy="5" r="2"/>
  <text font-family="Arial" x="5" y="50">Living   room</text>
  <text style="font-family: Georgia; fill: #123456">Kitchen</text>
</svg>"""

EVIL_SVG = f"""<svg {NS} xmlns:xlink="http://www.w3.org/1999/xlink">
  <script>alert(1)</script>
  <style>@import url(http://evil.example/a.css); @IMPORT "x.css"; .a {{ fill: URL(http://evil.example/p.svg#p) }}</style>
  <foreignObject><div xmlns="http://www.w3.org/1999/xhtml">html</div></foreignObject>
  <image href="file:///etc/passwd" width="10" height="10"/>
  <image xlink:href="http://evil.example/x.png" width="10" height="10"/>
  <use href="#local"/>
  <rect id="local" class="a" style="fill: Url(http://evil.example/s.svg#s)" filter="url(file:///etc/f.svg#f)"/>
</svg>"""


def _svg(tmp_path: Path, source: str, name: str = "image.svg") -> Path:
    path = tmp_path / name
    path.write_text(source)
    return path


def _png(size: tuple[int, int] = (200, 100), uniform: bool = False) -> bytes:
    image = Image.new("RGB", size, "white")
    if not uniform:
        image.paste((255, 0, 0), (10, 10, 50, 50))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fake_renderer(monkeypatch, png: bytes | None = None) -> list[str]:
    """LibreOffice and PDFium stand-ins: returns the markup LibreOffice was given."""
    seen: list[str] = []

    def convert(source: Path) -> Path:
        seen.append(source.read_text())
        pdf = source.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF")
        return pdf

    def render(_pdf: Path, _pages: list[int], out_dir: Path) -> dict[int, Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        page = out_dir / "slide_001.png"
        page.write_bytes(png or _png())
        return {1: page}

    monkeypatch.setattr(svg_summary, "convert_office_file_to_pdf", convert)
    monkeypatch.setattr(svg_summary, "render_pdf_pages_to_png", render)
    return seen


def test_facts_read_palette_fonts_texts_counts_and_ids(tmp_path: Path) -> None:
    facts = svg_facts(_svg(tmp_path, PLAN_SVG))

    assert "Canvas: viewBox=0 0 200 100 width=200 height=100" in facts
    for fact in ("#1A2B3C fill 2", "#FF0000 stroke 2", "#EEEEEE fill 1", "#00FF00 fill 1", "#123456 fill 1"):
        assert fact in facts
    assert "Fonts: Arial, Georgia" in facts and "rect 3" in facts and "Named ids: kitchen" in facts
    assert "Texts: Floor plan | Living room | Kitchen" in facts
    # No text element is not "no text": it may be drawn as shapes.
    assert "text may be drawn as shapes" in svg_facts(_svg(tmp_path, f'<svg {NS}><path d="M0 0L1 1"/></svg>'))


def test_text_heavy_facts_are_bounded(tmp_path: Path) -> None:
    texts = "".join(f'<text id="label-{i}-{"x" * 200}" font-family="Font{i}">{"word " * 300}</text>' for i in range(200))
    tags = "".join(f"<tag{i}/>" for i in range(200))

    facts = svg_facts(_svg(tmp_path, f'<svg {NS} viewBox="{"1 " * 500}">{texts}{tags}</svg>'))

    # Bounded far below the summary budget, so the limits note after them is never cut.
    assert all(len(line) <= 600 for line in facts.splitlines()) and "(+160 more)" in facts
    assert len(facts) < 4000


def test_sanitizer_drops_scripts_and_external_references_whatever_their_case() -> None:
    cleaned = _self_contained(EVIL_SVG)

    for forbidden in ("script", "alert", "foreignObject", "@import", "IMPORT", "evil.example", "file://"):
        assert forbidden not in cleaned
    assert 'href="#local"' in cleaned


def test_sanitized_root_stays_unprefixed_whatever_the_global_registry(monkeypatch) -> None:
    # Another library claiming the default prefix must not turn the root into <ns0:svg>.
    monkeypatch.setattr(StdElementTree, "_namespace_map", dict(getattr(StdElementTree, "_namespace_map")))
    StdElementTree.register_namespace("", "urn:other")

    cleaned = _self_contained(f'<svg {NS} xmlns:xlink="http://www.w3.org/1999/xlink"><use xlink:href="#a"/><rect id="a"/></svg>')

    assert cleaned.startswith(f"<svg {NS} xmlns:xlink=") and '<use xlink:href="#a"' in cleaned
    use = ElementTree.fromstring(cleaned).find("{http://www.w3.org/2000/svg}use")
    assert use is not None and use.get("{http://www.w3.org/1999/xlink}href") == "#a"


def test_only_real_bounded_raster_data_urls_survive_sanitizing(monkeypatch) -> None:
    nested = base64.b64encode(f'<svg {NS}><image href="file:///etc/passwd"/></svg>'.encode()).decode()
    real = base64.b64encode(_png()).decode()
    huge_image = io.BytesIO()
    Image.new("1", (6000, 5000)).save(huge_image, format="PNG")
    huge = base64.b64encode(huge_image.getvalue()).decode()
    source = f"""<svg {NS}>
      <image href="data:image/svg+xml;base64,{nested}"/>
      <image href="data:image/png;base64,{nested}"/>
      <image href="data:text/html,hi"/>
      <image href="data:image/png;base64,{huge}"/>
      <image href="data:image/png;base64,{real}"/>
    </svg>"""

    cleaned = _self_contained(source)

    assert "svg+xml" not in cleaned and "text/html" not in cleaned and nested not in cleaned and huge not in cleaned
    assert f'href="data:image/png;base64,{real}"' in cleaned
    monkeypatch.setattr(svg_summary, "_MAX_RASTER_DATA_CHARS", 100)
    assert real not in _self_contained(source)


def test_render_sends_only_sanitized_markup_to_libreoffice(tmp_path: Path, monkeypatch) -> None:
    seen = _fake_renderer(monkeypatch)

    assert svg_png_data_url(_svg(tmp_path, EVIL_SVG)) == "data:image/png;base64," + base64.b64encode(_png()).decode()
    assert "evil.example" not in seen[0] and "script" not in seen[0]
    # A prefixed <ns0:svg> root makes LibreOffice open the markup in Calc as a table.
    assert seen[0].startswith(f"<svg {NS}") and "ns0:" not in seen[0]


def test_canvas_is_fitted_to_the_vision_size_whatever_the_declared_size() -> None:
    def root_size(attributes: str) -> tuple[str | None, str | None, str | None]:
        root = ElementTree.fromstring(_self_contained(f"<svg {NS} {attributes}/>"))
        return root.get("width"), root.get("height"), root.get("viewBox")

    # Huge declared size: bounded, and a viewBox keeps the drawing scaled rather than cropped.
    assert root_size('width="10000cm" height="5000cm"') == ("784.00pt", "392.00pt", "0 0 377953 188976")
    # Tiny icon: enlarged.
    assert root_size('width="24" height="24" viewBox="0 0 24 24"')[:2] == ("784.00pt", "784.00pt")
    assert root_size('viewBox="0 0 100 200"')[:2] == ("392.00pt", "784.00pt")
    # Nothing usable: a sane default instead of the renderer's guess.
    assert root_size('width="50%" viewBox="0 0 0 0"')[:2] == ("784.00pt", "784.00pt")


def _broken_convert(_source: Path) -> Path:
    raise OSError("no space left")


@pytest.mark.parametrize(
    ("convert", "png"),
    [
        (lambda _source: None, None),  # LibreOffice gave no PDF
        (_broken_convert, None),  # renderer error
        (None, _png(uniform=True)),  # blank render
        (None, _png(size=(30, 20))),  # tiny render
    ],
)
def test_failed_or_empty_render_returns_none(tmp_path: Path, monkeypatch, convert, png: bytes | None) -> None:
    _fake_renderer(monkeypatch, png)
    if convert is not None:
        monkeypatch.setattr(svg_summary, "convert_office_file_to_pdf", convert)

    assert svg_png_data_url(_svg(tmp_path, PLAN_SVG)) is None


def test_renders_are_bounded_per_process_and_never_wait_long(tmp_path: Path, monkeypatch) -> None:
    path = _svg(tmp_path, PLAN_SVG)
    free_slots: list[int] = []
    seen = _fake_renderer(monkeypatch)
    convert = svg_summary.convert_office_file_to_pdf

    def counting_convert(source: Path) -> Path | None:
        free_slots.append(getattr(svg_summary._RENDER_SLOTS, "_value"))
        return convert(source)

    monkeypatch.setattr(svg_summary, "convert_office_file_to_pdf", counting_convert)
    monkeypatch.setattr(svg_summary, "_RENDER_SLOTS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(svg_summary, "_RENDER_SLOT_TIMEOUT_S", 0.05)

    svg_summary._RENDER_SLOTS.acquire()
    assert svg_png_data_url(path) is None and seen == []
    svg_summary._RENDER_SLOTS.release()
    assert svg_png_data_url(path) is not None

    # The slot is held during the conversion and released after it.
    assert free_slots == [0] and getattr(svg_summary._RENDER_SLOTS, "_value") == 1


def test_oversized_svg_is_not_rendered(tmp_path: Path, monkeypatch) -> None:
    seen = _fake_renderer(monkeypatch)
    many = _svg(tmp_path, f"<svg {NS}>" + "<rect/>" * 50_001 + "</svg>", "many.svg")
    heavy = _svg(tmp_path, PLAN_SVG, "heavy.svg")

    assert svg_png_data_url(many) is None
    monkeypatch.setattr(svg_summary, "_MAX_RENDER_BYTES", 100)
    assert svg_png_data_url(heavy) is None
    assert seen == [] and getattr(svg_summary._RENDER_SLOTS, "_value") == 2


def test_illustrator_internal_entities_are_read(tmp_path: Path) -> None:
    path = _svg(
        tmp_path,
        '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd" ['
        '<!ENTITY ns_svg "http://www.w3.org/2000/svg"><!ENTITY ns_flows "http://ns.adobe.com/Flows/1.0/">]>'
        '<svg xmlns="&ns_svg;" xmlns:x="&ns_flows;" viewBox="0 0 10 10"><text>Logo</text></svg>',
    )

    assert "Texts: Logo" in svg_facts(path) and "unreadable" not in svg_facts(path)


_LAUGHS = "".join(f'<!ENTITY e{i} "{f"&e{i - 1};" * 10}">' for i in range(1, 10))


@pytest.mark.parametrize(
    "source",
    [
        "<svg><rect></svg",
        f'<!DOCTYPE svg [<!ENTITY e0 "lol">{_LAUGHS}]><svg {NS}><text>&e9;</text></svg>',
        f'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg {NS}><text>&x;</text></svg>',
        f'<!DOCTYPE svg [<!ENTITY x "{"x" * 1000}">]><svg {NS}><text>{"&x;" * 2000}</text></svg>',
        f'<!DOCTYPE svg [<!ENTITY {"n" * 100_000} SYSTEM "http://x/">]><svg {NS}/>',  # long parse error
    ],
    ids=["broken", "laughs", "external", "wide", "long-error"],
)
def test_unreadable_or_expanding_markup_is_refused_fast(tmp_path: Path, source: str) -> None:
    path = _svg(tmp_path, source)
    started = time.monotonic()

    facts = svg_facts(path)

    assert facts.startswith("unreadable SVG markup") and len(facts) < 700
    assert svg_png_data_url(path) is None
    assert time.monotonic() - started < 0.2


def test_hostile_markup_is_processed_in_linear_time(tmp_path: Path) -> None:
    css = _svg(tmp_path, f"<svg {NS}><style>{'.a{' * 40_000}</style></svg>")
    for source in (f'<svg {NS}><rect fill="{"url(" * 40_000}"/></svg>', f'<svg {NS} width="1{" " * 20_000}x" height="1"/>'):
        started = time.monotonic()
        _self_contained(source)
        assert time.monotonic() - started < 0.2
    started = time.monotonic()
    svg_facts(css)
    assert time.monotonic() - started < 0.2
