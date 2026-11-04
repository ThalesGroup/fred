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

"""The template library configuration: the entries an admin uploads, and
the save path that stores each new template and reads its parts.
"""

from __future__ import annotations

import asyncio
import unicodedata
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

from fred_sdk.contracts.capability import (
    AssetKey,
    SaveContext,
    UploadedFile,
)
from pydantic import BaseModel

from fred_capability_word_template.analysis import (
    TemplateAnalysis,
)
from fred_capability_word_template.docmap import (
    build_map,
    render_parts,
)
from fred_capability_word_template.store import (
    WORD_TEMPLATE_ASSET_PREFIX,
)

TEMPLATE_LIBRARY_SLOT = "word_template_library"
_DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class WordTemplateEntry(BaseModel):
    """One template of the library.

    ``label`` is the only admin-authored field; empty, it is prefilled from
    the uploaded file's name. ``template_key`` is None only on the way in,
    for an entry the admin form just added: ``validate_config`` pairs it with
    its uploaded file and fills it with ``parts_summary`` (the blank
    template's parts, used to tell templates apart before one is selected).
    ``analysis`` is set at upload when a chat model is reachable
    there; otherwise it runs on first use and is cached in
    ``cap_word_template_analyses``.

    ``template_key`` is an asset key: copying the agent re-submits the file
    to ``validate_config`` in the destination (``resolve_library``)."""

    template_key: Annotated[str | None, AssetKey(TEMPLATE_LIBRARY_SLOT)] = None
    label: str = ""
    parts_summary: str = ""
    analysis: TemplateAnalysis | None = None


class WordTemplateConfig(BaseModel):
    template_library: list[WordTemplateEntry] | None = None


def normalized(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(folded.lower().split())


def _label_from_filename(filename: str) -> str:
    stem = Path(filename or "").stem
    return " ".join(stem.replace("_", " ").split()) or "Modèle"


def _read_template(docx_bytes: bytes) -> str:
    """The blank template's parts, or ``ValueError`` when it is not a
    readable Word document."""
    try:
        return render_parts(build_map(docx_bytes))
    except Exception as exc:  # noqa: BLE001 - python-docx raises many types on a malformed file
        raise ValueError("not a readable Word (.docx) document") from exc


async def resolve_library(
    entries: Sequence[WordTemplateEntry],
    uploads: Sequence[UploadedFile],
    ctx: SaveContext,
) -> list[WordTemplateEntry]:
    """Pair the NEW (keyless) entries, in order, with the uploaded files, in
    order; already stored entries pass through. Raises ``ValueError`` (422)
    on any mismatch or unreadable file - nothing is stored then.

    An agent copy re-submits every stored entry's file, in library order,
    with no new entry (``fred_runtime.capabilities.copy``): each entry is
    then stored again under a fresh key for the new instance, keeping its
    name and its analysis (same bytes)."""
    new_count = sum(1 for e in entries if not e.template_key)
    stored_count = len(entries) - new_count
    resubmitted = new_count == 0 and bool(uploads) and len(uploads) == stored_count
    if resubmitted:
        entries = [entry.model_copy(update={"template_key": None}) for entry in entries]
        new_count = stored_count
    if new_count != len(uploads):
        raise ValueError(
            f"Template library: {new_count} new template(s) declared but "
            f"{len(uploads)} file(s) uploaded - each new template needs exactly "
            "one .docx."
        )
    pending = iter(uploads)
    prepared: list[tuple[WordTemplateEntry, UploadedFile | None, str]] = []
    for entry in entries:
        if entry.template_key:
            prepared.append((entry, None, entry.label.strip()))
            continue
        upload = next(pending)
        label = entry.label.strip() or _label_from_filename(upload.filename)
        prepared.append((entry, upload, label))
    seen: set[str] = set()
    for _entry, _upload, label in prepared:
        if not label:
            raise ValueError("Template library: every template needs a name.")
        if normalized(label) in seen:
            raise ValueError(
                f'Template library: the name "{label}" is used more than once.'
            )
        seen.add(normalized(label))
    # Read every new file before storing any: one bad upload stores nothing.
    summaries: dict[int, str] = {}
    for index, (_entry, upload, label) in enumerate(prepared):
        if upload is None:
            continue
        try:
            summaries[index] = await asyncio.to_thread(_read_template, upload.content)
        except ValueError as exc:
            raise ValueError(
                f'Template library: "{upload.filename or label}" is {exc}.'
            ) from exc
    assets = ctx.services.agent_assets
    if summaries and assets is None:
        raise RuntimeError(
            "word_template: RuntimeServices.agent_assets is not available on "
            "this save path; the template cannot be stored."
        )
    resolved: list[WordTemplateEntry] = []
    for index, (entry, upload, label) in enumerate(prepared):
        if upload is None:
            resolved.append(entry.model_copy(update={"label": label}))
            continue
        assert assets is not None
        template_key = f"{WORD_TEMPLATE_ASSET_PREFIX}.{uuid.uuid4().hex}.docx"
        await assets.store(
            template_key,
            upload.content,
            content_type=_DOCX_CONTENT_TYPE,
            filename=upload.filename or WORD_TEMPLATE_ASSET_PREFIX,
        )
        resolved.append(
            entry.model_copy(
                update={
                    "label": label,
                    "template_key": template_key,
                    "parts_summary": summaries[index],
                    # No chat model on the save path: the analysis runs
                    # on first use. A copied
                    # entry keeps its own (same bytes).
                    "analysis": entry.analysis if resubmitted else None,
                }
            )
        )
    return resolved
