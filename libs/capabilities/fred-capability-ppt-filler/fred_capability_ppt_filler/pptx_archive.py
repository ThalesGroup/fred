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

"""Open user ``.pptx`` bytes without a zip bomb. python-pptx decompresses every
member up front and the upload limit bounds only the compressed size, so the
declared sizes are checked first (zipfile never inflates past them)."""

from __future__ import annotations

import hashlib
import io
import posixpath
import zipfile
from typing import Any, Dict, List, Set, Tuple

from lxml import etree  # pyright: ignore[reportAttributeAccessIssue]
from pptx import Presentation
from pptx.presentation import Presentation as PresentationType

MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
# Above this size a member must not inflate more than MAX_RATIO times: a large
# slide XML compresses ~10-30x, a bomb thousands of times.
RATIO_CHECKED_BYTES = 10 * 1024 * 1024
MAX_RATIO = 100


class UnsafeArchiveError(ValueError):
    """The archive would inflate beyond what a template may hold."""


def check_archive(content: bytes) -> None:
    """Raise :class:`UnsafeArchiveError` before anything is decompressed."""
    try:
        members = zipfile.ZipFile(io.BytesIO(content)).infolist()
    except zipfile.BadZipFile:
        return  # python-pptx reports an unreadable file itself
    total = 0
    for member in members:
        size = member.file_size
        total += size
        if size > MAX_MEMBER_BYTES or total > MAX_UNCOMPRESSED_BYTES:
            raise UnsafeArchiveError(
                "The file inflates to more than a presentation template may hold."
            )
        if size > RATIO_CHECKED_BYTES and size > MAX_RATIO * max(
            member.compress_size, 1
        ):
            raise UnsafeArchiveError(
                f"The file holds an abnormally compressed part ({member.filename})."
            )


def open_presentation(content: bytes) -> PresentationType:
    """``Presentation`` of user bytes, the archive checked first (CPU-bound)."""
    check_archive(content)
    return Presentation(io.BytesIO(content))


_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_CT_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
# Elements that only carry the reference: dropped with it (a required attribute).
_REFERENCE_ONLY = {
    "externalData",
    "videoFile",
    "audioFile",
    "quickTimeFile",
    "wavAudioFile",
    "link",
}
_MACRO_MAIN = {
    "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
    ),
    "application/vnd.ms-powerpoint.slideshow.macroEnabled.main+xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml"
    ),
    "application/vnd.ms-powerpoint.template.macroEnabled.main+xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml"
    ),
}


def _macro(name_or_type: str) -> bool:
    lowered = name_or_type.lower()
    return "vbaproject" in lowered or "vbadata" in lowered


def _kept_rel(rel: Any) -> bool:
    kind = rel.get("Type", "")
    if _macro(kind) or _macro(rel.get("Target", "")):
        return False
    return rel.get("TargetMode") != "External" or kind.endswith("/hyperlink")


def _unreferenced(xml: bytes, dropped: Set[str]) -> bytes:
    """``xml`` without its references to the ``dropped`` relationship ids."""
    root = etree.fromstring(xml)
    for element in list(root.iter(etree.Element)):
        refs = [
            k for k, v in element.attrib.items() if k.startswith(_R_NS) and v in dropped
        ]
        if not refs:
            continue
        local = etree.QName(element).localname
        parent = element.getparent()
        if local in _REFERENCE_ONLY and parent is not None:
            parent.remove(element)
            continue
        for key in refs:
            del element.attrib[key]
        if local == "oleObj":  # a linked object: its link goes too
            for link in element.findall("{*}link"):
                element.remove(link)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def sanitize_template(content: bytes) -> bytes:
    """The template without what reaches outside it: external relationships
    (hyperlinks kept), linked pictures and objects, and macros. Run once on an
    upload; the sanitised bytes are the ones stored."""
    check_archive(content)
    source = zipfile.ZipFile(io.BytesIO(content))
    names = source.namelist()
    removed = {n for n in names if _macro(posixpath.basename(n))}
    changed: Dict[str, bytes] = {}
    for name in names:
        if not name.endswith(".rels") or name in removed:
            continue
        root = etree.fromstring(source.read(name))
        dropped = [r for r in root.iter(f"{_REL_NS}Relationship") if not _kept_rel(r)]
        if not dropped:
            continue
        for rel in dropped:
            root.remove(rel)
        changed[name] = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        folder = posixpath.dirname(posixpath.dirname(name))
        owner = posixpath.join(folder, posixpath.basename(name)[: -len(".rels")])
        if owner in names and owner.endswith(".xml"):
            ids = {r.get("Id", "") for r in dropped}
            changed[owner] = _unreferenced(source.read(owner), ids)
    if "[Content_Types].xml" in names:
        types = etree.fromstring(source.read("[Content_Types].xml"))
        macros = [e for e in types if _macro(e.get("ContentType", ""))]
        mains = [e for e in types if e.get("ContentType") in _MACRO_MAIN]
        for entry in macros:  # a shared extension default stays, typeless
            if entry.tag == f"{_CT_NS}Default":
                entry.set("ContentType", "application/octet-stream")
            else:
                types.remove(entry)
        for entry in mains:
            entry.set("ContentType", _MACRO_MAIN[entry.get("ContentType")])
        if macros or mains:
            changed["[Content_Types].xml"] = etree.tostring(
                types, xml_declaration=True, encoding="UTF-8", standalone=True
            )
    if not changed and not removed:
        return content
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            if info.filename in removed:
                continue
            data = changed.get(info.filename)
            target.writestr(info, data if data is not None else source.read(info))
    return out.getvalue()


_R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
# Hashed by name: the template's shared parts. Never hashed: an embedded
# workbook carries its own creation time.
_BY_NAME = ("/slideLayout", "/notesMaster")
_SKIPPED = ("/package", "/oleObject")


def _rels(archive: zipfile.ZipFile, part: str) -> List[Tuple[str, str, str]]:
    """(id, type, resolved target) of a part's internal relationships."""
    folder, name = posixpath.split(part)
    path = posixpath.join(folder, "_rels", name + ".rels")
    if path not in archive.namelist():
        return []
    root = etree.fromstring(archive.read(path))
    return sorted(
        (
            rel.get("Id", ""),
            rel.get("Type", ""),
            posixpath.normpath(posixpath.join(folder, rel.get("Target", ""))),
        )
        for rel in root.iter(f"{_REL_NS}Relationship")
        if rel.get("TargetMode") != "External"
    )


def slide_fingerprints(content: bytes) -> List[str]:
    """Per slide, in deck order, ``<shown>:<notes>``: a hash of what the slide
    shows (its XML and the charts and pictures it uses), then of its speaker
    notes. Two renders that look the same hash the same, wherever they sit."""
    archive = zipfile.ZipFile(io.BytesIO(content))
    names = set(archive.namelist())
    order = etree.fromstring(archive.read("ppt/presentation.xml"))
    targets = {rid: target for rid, _, target in _rels(archive, "ppt/presentation.xml")}
    prints: List[str] = []
    for slide_id in order.iter("{*}sldId"):
        part = targets.get(slide_id.get(_R_ID, ""), "")
        shown, notes = hashlib.sha256(archive.read(part)), hashlib.sha256()
        for rid, kind, target in _rels(archive, part):
            digest = notes if kind.endswith("/notesSlide") else shown
            digest.update(f"\n{rid} {kind.rsplit('/', 1)[-1]} ".encode())
            if any(kind.endswith(k) for k in _BY_NAME):
                digest.update(target.encode())
            elif not any(kind.endswith(k) for k in _SKIPPED):
                digest.update(archive.read(target) if target in names else b"")
        prints.append(f"{shown.hexdigest()}:{notes.hexdigest()}")
    return prints
