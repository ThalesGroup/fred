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

"""Exact, model-free facts read from an SVG's markup: what a vision model cannot give."""

from __future__ import annotations

import base64
import io
import logging
import math
import re
import tempfile
import threading
from collections import Counter
from pathlib import Path
from typing import cast

from defusedxml import DefusedXmlException, ElementTree
from fred_core.conversion.office_pdf import convert_office_file_to_pdf
from PIL import Image

from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.utils.pptx_slide_renderer import render_pdf_pages_to_png

logger = logging.getLogger(__name__)

_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)")
# Linear forms: an unclosed rule or url( matches up to the end instead of backtracking.
_CSS_RULE_RE = re.compile(r"\.([\w-]+)\s*\{([^}]*)(?:\}|$)")
_DECLARATION_RE = re.compile(r"(fill|stroke|font-family)\s*:\s*([^;]+)")
_MAX_ITEMS = 40
# Each facts line is bounded so the facts block stays far below the summary budget
# and the limits note after it is never cut.
_MAX_ITEM_CHARS = 80
_MAX_LINE_CHARS = 600
# Internal entities (Illustrator declares namespaces as entities) are expanded only when
# their total expansion is small; nested ones could grow exponentially.
_ENTITY_DECL_RE = re.compile(r"<!ENTITY\s+([^\s%\"']+)\s+(?:\"([^\"]*)\"|'([^']*)')")
_MAX_ENTITY_DECLS = 64
_MAX_ENTITY_EXPANSION_CHARS = 1_000_000


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _declarations(style: str) -> list[tuple[str, str]]:
    return [(prop, value.strip()) for prop, value in _DECLARATION_RE.findall(style)]


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _listed(items: list[str], separator: str, empty: str) -> str:
    shown = separator.join(_clip(item, _MAX_ITEM_CHARS) for item in items[:_MAX_ITEMS])
    more = f" (+{len(items) - _MAX_ITEMS} more)" if len(items) > _MAX_ITEMS else ""
    return shown + more if shown else empty


def _small_internal_entities(source: str) -> bool:
    declared = source.count("<!ENTITY")
    if declared > _MAX_ENTITY_DECLS:
        return False
    matches = list(_ENTITY_DECL_RE.finditer(source))
    if len(matches) != declared:  # parameter or external entity
        return False
    expansion = 0
    for match in matches:
        value = match[2] if match[2] is not None else match[3]
        if "&" in value or "%" in value:
            return False
        expansion += source.count(f"&{match[1]};") * len(value)
    return expansion <= _MAX_ENTITY_EXPANSION_CHARS


def _parse(source: str):
    # External entities and DTDs stay forbidden; expat also bounds amplification.
    return ElementTree.fromstring(source, forbid_entities=not _small_internal_entities(source), forbid_external=True)


def summarize_svg(source: str) -> str:
    root = _parse(source)
    elements = list(root.iter())
    tags = Counter(_local(element.tag) for element in elements)

    class_rules: dict[str, list[tuple[str, str]]] = {}
    for style in (element.text or "" for element in elements if _local(element.tag) == "style"):
        for name, body in _CSS_RULE_RE.findall(style):
            class_rules[name] = _declarations(body)

    palette: Counter[tuple[str, str]] = Counter()
    fonts: Counter[str] = Counter()
    for element in elements:
        declarations = [(prop, element.get(prop, "")) for prop in ("fill", "stroke", "font-family")]
        declarations += _declarations(element.get("style", ""))
        for name in element.get("class", "").split():
            declarations += class_rules.get(name, [])
        for prop, value in declarations:
            if prop == "font-family" and value:
                fonts[value] += 1
            elif _COLOR_RE.fullmatch(value.strip()):
                palette[(value.strip().upper(), prop)] += 1

    texts = [" ".join("".join(element.itertext()).split()) for element in elements if _local(element.tag) in ("text", "title", "desc")]
    ids = [element.get("id", "") for element in elements if element.get("id")]
    canvas = " ".join(f"{name}={_clip(root.get(name, 'none'), _MAX_ITEM_CHARS)}" for name in ("viewBox", "width", "height"))

    lines = [
        f"Canvas: {canvas}",
        "Elements: " + _listed([f"{tag} {count}" for tag, count in tags.most_common()], ", ", "none"),
        "Palette (color, usage, element count): " + _listed([f"{color} {prop} {count}" for (color, prop), count in palette.most_common()], ", ", "none declared"),
        "Fonts: " + _listed(list(fonts), ", ", "none declared"),
        "Texts: " + _listed([text for text in texts if text], " | ", "none: no text element (text may be drawn as shapes)"),
        "Named ids: " + _listed(ids, ", ", "none"),
    ]
    return "\n".join(_clip(line, _MAX_LINE_CHARS) for line in lines)


_SVG_NS = "{http://www.w3.org/2000/svg}"
_XLINK_NS = "{http://www.w3.org/1999/xlink}"
_ACTIVE_TAGS = {"script", "foreignObject", "iframe", "object", "embed"}
_IMPORT_RE = re.compile(r"@import[^;]*;?|url\((?!\s*['\"]?#)[^)]*(?:\)|$)", re.IGNORECASE)
# A nested SVG or other markup in a data: URL would skip this sanitizer.
_RASTER_DATA_RE = re.compile(r"data:image/(png|jpeg|gif|webp);base64,", re.IGNORECASE)
# LibreOffice sniffs the payload, not the label: only a real, bounded raster is kept.
_RASTER_FORMATS = ["PNG", "JPEG", "GIF", "WEBP"]
_MAX_RASTER_DATA_CHARS = 4_000_000
_MAX_RASTER_PIXELS = 25_000_000
# PDFium renders the page at scale 2: a 784 pt long edge gives the 1568 px vision size.
_RENDER_LONG_EDGE_PT = 784
_LENGTH_RE = re.compile(r"\s*((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(px|pt|pc|mm|cm|in)?\s*")
_MAX_LENGTH_CHARS = 64
_UNIT_PX = {"": 1.0, "px": 1.0, "pt": 4 / 3, "pc": 16.0, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0}
# Each render is a LibreOffice process (~220 MB) plus a PDFium child: bound them per process.
_RENDER_SLOTS = threading.BoundedSemaphore(2)
# Renders run in the shared default executor: never wait there for long.
_RENDER_SLOT_TIMEOUT_S = 30
_MAX_RENDER_BYTES = 5 * 1024 * 1024
_MAX_RENDER_ELEMENTS = 50_000
# A render this small, or of a single color, shows nothing the facts do not say.
_MIN_RENDER_EDGE_PX = 32


class _TooComplex(Exception):
    pass


def _positive(value: float) -> float | None:
    return value if math.isfinite(value) and value > 0 else None


def _length_px(value: str | None) -> float | None:
    if value is None or len(value) > _MAX_LENGTH_CHARS:
        return None
    match = _LENGTH_RE.fullmatch(value)
    return _positive(float(match[1]) * _UNIT_PX[match[2] or ""]) if match else None


def _viewbox_size(value: str | None) -> tuple[float, float] | None:
    parts = re.split(r"[\s,]+", (value or "").strip())
    if len(parts) != 4:
        return None
    try:
        width, height = _positive(float(parts[2])), _positive(float(parts[3]))
    except ValueError:
        return None
    return (width, height) if width and height else None


def _fit_canvas(root) -> None:
    """The declared canvas size drives the render bitmap: fit it to the vision size, aspect kept."""
    size = _viewbox_size(root.get("viewBox"))
    if size is None:
        declared_w, declared_h = _length_px(root.get("width")), _length_px(root.get("height"))
        if declared_w and declared_h:
            size = (declared_w, declared_h)
            # Without a viewBox one user unit is one px: map them so the drawing scales with the canvas.
            root.set("viewBox", f"0 0 {declared_w:g} {declared_h:g}")
    size = size or (1.0, 1.0)
    width, height = (_RENDER_LONG_EDGE_PT * edge / max(size) for edge in size)
    root.set("width", f"{max(width, 1):.2f}pt")
    root.set("height", f"{max(height, 1):.2f}pt")


def _raster_data(value: str) -> bool:
    match = _RASTER_DATA_RE.match(value)
    if match is None or len(value) - match.end() > _MAX_RASTER_DATA_CHARS:
        return False
    try:
        with Image.open(io.BytesIO(base64.b64decode(value[match.end() :])), formats=_RASTER_FORMATS) as image:
            return image.width * image.height <= _MAX_RASTER_PIXELS
    except Exception:  # not a raster Pillow identifies: drop it
        return False


def _self_contained(source: str) -> str:
    """The renderer must not read local files or the network: keep only in-document references."""
    root = _parse(source)
    if sum(1 for _ in root.iter()) > _MAX_RENDER_ELEMENTS:
        raise _TooComplex
    for parent in list(root.iter()):
        for child in list(parent):
            if _local(child.tag) in _ACTIVE_TAGS:
                parent.remove(child)
    for element in root.iter():
        for name, value in list(element.attrib.items()):
            if _local(name) == "href" and not (value.startswith("#") or _raster_data(value)):
                del element.attrib[name]
            elif "url(" in value.lower() or "@import" in value.lower():
                element.set(name, _IMPORT_RE.sub("", value))
        if _local(element.tag) == "style" and element.text:
            element.text = _IMPORT_RE.sub("", element.text)
    _fit_canvas(root)
    # LibreOffice opens <ns0:svg> in Calc as a table and refuses ns0:href, and the global prefix
    # registry is shared (docling claims the default one): spell both namespaces by hand.
    for element in root.iter():
        element.tag = element.tag.removeprefix(_SVG_NS)
        element.attrib = {name.replace(_XLINK_NS, "xlink:"): value for name, value in element.attrib.items()}
    root.attrib = {"xmlns": _SVG_NS.strip("{}"), "xmlns:xlink": _XLINK_NS.strip("{}"), **root.attrib}
    return ElementTree.tostring(root, encoding="unicode")


def svg_facts(file_path: Path) -> str:
    try:
        return summarize_svg(file_path.read_text(encoding="utf-8", errors="replace"))
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        return f"unreadable SVG markup ({_clip(str(exc), _MAX_LINE_CHARS)})"


def _informative_png(png: bytes) -> bool:
    with Image.open(io.BytesIO(png), formats=["PNG"]) as image:
        extrema = image.getextrema()
        bands = cast(tuple[tuple[float, float], ...], extrema if isinstance(extrema[0], tuple) else (extrema,))
        return max(image.size) >= _MIN_RENDER_EDGE_PX and any(low != high for low, high in bands)


def svg_png_data_url(file_path: Path) -> str | None:
    """Render through the LibreOffice + PDFium path the slide renderer already uses.

    Best-effort: any failure returns None, the exact markup facts still describe the file."""
    try:
        if file_path.stat().st_size > _MAX_RENDER_BYTES:
            raise _TooComplex
        markup = _self_contained(file_path.read_text(encoding="utf-8", errors="replace"))
    except _TooComplex:
        logger.info("[FAST TEXT][IMAGE] SVG not rendered for %s: above %d bytes or %d elements", file_path.name, _MAX_RENDER_BYTES, _MAX_RENDER_ELEMENTS)
        return None
    except Exception as exc:  # hostile or exotic markup (deep nesting, entities) must not fail the ingest
        logger.warning("[FAST TEXT][IMAGE] SVG not rendered for %s: %s", file_path.name, type(exc).__name__)
        return None
    if not _RENDER_SLOTS.acquire(timeout=_RENDER_SLOT_TIMEOUT_S):
        logger.warning("[FAST TEXT][IMAGE] SVG not rendered for %s: no render slot after %ss", file_path.name, _RENDER_SLOT_TIMEOUT_S)
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="svg-render-") as tmp:
            copy = Path(tmp) / "image.svg"
            copy.write_text(markup, encoding="utf-8")
            pdf = convert_office_file_to_pdf(copy)
            pages = render_pdf_pages_to_png(pdf, [1], Path(tmp) / "png") if pdf else {}
            png = pages[1].read_bytes() if 1 in pages else None
        if png is None:
            logger.warning("[FAST TEXT][IMAGE] SVG rendering failed for %s", file_path.name)
            return None
        if not _informative_png(png):
            logger.info("[FAST TEXT][IMAGE] SVG render of %s is blank or tiny: not described", file_path.name)
            return None
    except Exception as exc:  # renderer or PNG errors must not fail the ingest
        logger.warning("[FAST TEXT][IMAGE] SVG not rendered for %s: %s", file_path.name, type(exc).__name__)
        return None
    finally:
        _RENDER_SLOTS.release()
    return "data:image/png;base64," + base64.b64encode(png).decode()
