# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

"""Bounded revision source carried by the XLSX, with no separate persistence.

The custom XML part contains base64 JSON, never executable Python or formulas to
run outside the existing engine. Its digest detects changes to the rendered XLSX;
it is a consistency check, not an authorization signature.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import struct
import uuid
import zipfile
import zlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from fred_capability_spreadsheet.workbook import (
    CreateSpreadsheetInput,
    SpreadsheetInputError,
    sanitize_file_name,
)

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SPEC_BYTES = 4 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ZIP_ENTRIES = 256
_PART = "customXml/fred-spreadsheet.xml"
_PREFIX = b'<spreadsheet xmlns="urn:fred:spreadsheet:1" encoding="base64">'
_SUFFIX = b"</spreadsheet>"
_MAX_PART_BYTES = 4 * ((MAX_SPEC_BYTES + 2) // 3) + len(_PREFIX) + len(_SUFFIX)


class WorkbookSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal[1] = 1
    workbook_id: uuid.UUID
    version: int = Field(ge=1, le=1_000_000, strict=True)
    file_name: str = Field(min_length=1, max_length=200)
    spec: CreateSpreadsheetInput
    rendered_sha256: str = Field(default="", pattern=r"^(|[0-9a-f]{64})$")


def _digest(entries: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(entries.items()):
        if name == _PART:
            continue
        encoded = name.encode("utf-8")
        digest.update(struct.pack("!Q", len(encoded)))
        digest.update(encoded)
        digest.update(struct.pack("!Q", len(content)))
        digest.update(content)
    return digest.hexdigest()


def _entries(content: bytes) -> dict[str, bytes]:
    if len(content) > MAX_SOURCE_BYTES:
        raise SpreadsheetInputError("The XLSX exceeds the 32 MiB source limit.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if (
                len(infos) > MAX_ZIP_ENTRIES
                or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES
            ):
                raise SpreadsheetInputError(
                    "The XLSX exceeds the uncompressed archive limits."
                )
            if len({i.filename for i in infos}) != len(infos):
                raise SpreadsheetInputError(
                    "The XLSX is corrupt: duplicate archive members."
                )
            if any(
                i.flag_bits & 1
                or i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                for i in infos
            ):
                raise SpreadsheetInputError(
                    "Encrypted or unsupported XLSX compression is not supported."
                )
            entries: dict[str, bytes] = {}
            for info in infos:
                limit = (
                    _MAX_PART_BYTES
                    if info.filename == _PART
                    else MAX_UNCOMPRESSED_BYTES
                )
                if info.file_size > limit:
                    raise SpreadsheetInputError(
                        "The XLSX revision source exceeds its size limit."
                    )
                with archive.open(info) as member:
                    value = member.read(min(info.file_size, limit) + 1)
                if len(value) != info.file_size:
                    raise SpreadsheetInputError(
                        "The XLSX is corrupt: invalid archive member size."
                    )
                entries[info.filename] = value
            return entries
    except SpreadsheetInputError:
        raise
    except (
        ValueError,
        UnicodeError,
        zipfile.BadZipFile,
        zlib.error,
        EOFError,
        OSError,
        RuntimeError,
        NotImplementedError,
    ) as exc:
        raise SpreadsheetInputError(
            "The source XLSX archive is corrupt or unreadable."
        ) from exc


def embed_source(content: bytes, source: WorkbookSource) -> bytes:
    entries = _entries(content)
    # XlsxWriter already declares the XML content type. Register this part using
    # the standard customXml relationship so ordinary Excel readers retain it.
    relationship = (
        '<Relationship Id="fredSpreadsheetSource" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml" '
        'Target="customXml/fred-spreadsheet.xml"/>'
    ).encode()
    entries["_rels/.rels"] = entries["_rels/.rels"].replace(
        b"</Relationships>", relationship + b"</Relationships>"
    )
    source.rendered_sha256 = _digest(entries)
    payload = source.model_dump_json().encode("utf-8")
    if len(payload) > MAX_SPEC_BYTES:
        raise SpreadsheetInputError(
            "The workbook revision source exceeds 4 MiB; split the workbook."
        )
    entries[_PART] = _PREFIX + base64.b64encode(payload) + _SUFFIX
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    result = buffer.getvalue()
    if (
        len(result) > MAX_SOURCE_BYTES
        or sum(map(len, entries.values())) > MAX_UNCOMPRESSED_BYTES
    ):
        raise SpreadsheetInputError(
            "The workbook exceeds the source size limits; split the workbook."
        )
    return result


def read_source(content: bytes) -> WorkbookSource:
    entries = _entries(content)
    if "[Content_Types].xml" not in entries or "xl/workbook.xml" not in entries:
        raise SpreadsheetInputError("The source is not a supported XLSX workbook.")
    payload = entries.get(_PART)
    if payload is None:
        raise SpreadsheetInputError(
            "This XLSX has no supported Fred revision source. Send the whole workbook in sheets."
        )
    if not payload.startswith(_PREFIX) or not payload.endswith(_SUFFIX):
        raise SpreadsheetInputError(
            "The embedded XLSX revision source has an unsupported format."
        )
    try:
        raw = base64.b64decode(payload[len(_PREFIX) : -len(_SUFFIX)], validate=True)
        if len(raw) > MAX_SPEC_BYTES:
            raise SpreadsheetInputError(
                "The embedded XLSX revision source exceeds 4 MiB."
            )
        data = json.loads(raw)
        if isinstance(data, dict) and (
            type(data.get("format_version")) is not int
            or data.get("format_version") != 1
        ):
            raise SpreadsheetInputError(
                "The embedded XLSX revision source version is unsupported."
            )
        source = WorkbookSource.model_validate(data)
    except SpreadsheetInputError:
        raise
    except (
        ValidationError,
        ValueError,
        UnicodeError,
        binascii.Error,
        RecursionError,
    ) as exc:
        raise SpreadsheetInputError(
            "The embedded XLSX revision source is corrupt."
        ) from exc
    if source.file_name != sanitize_file_name(source.file_name):
        raise SpreadsheetInputError("The embedded XLSX file name is invalid.")
    if source.rendered_sha256 != _digest(entries):
        raise SpreadsheetInputError(
            "The XLSX was modified outside Fred; its revision source no longer matches the file. Send the updated workbook in sheets."
        )
    return source
