"""Parser / validator for the PPT Filler toolkit (PPTFILL-01).

Turns a ``.pptx`` into a per-slide template schema plus a list of structured,
slide-numbered errors. Pure and offline: it reads the deck, lists ``{{keys}}`` via the
shared traversal, parses descriptions from each slide's notes, and validates that the
text-box keys and the described keys match per slide.

The schema/error Pydantic models defined here (:class:`KeyField`, :class:`SlideSchema`,
:class:`TemplateError`, :class:`ParseResult`) are the data contract that downstream
issues (params model, analyze endpoint, fill tool) import.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Dict, List, Union

from pptx import Presentation
from pydantic import BaseModel, ConfigDict, Field

from agentic_backend.integrations.ppt_filler.traversal import (
    KEY_PATTERN,
    list_keys_on_slide,
)

# Stable, machine-readable error codes. The frontend maps these to i18n messages; the
# ``message`` field on each error is an English fallback.
CODE_KEY_WITHOUT_DESCRIPTION = "key_without_description"
CODE_DESCRIBED_BUT_NOT_IN_SLIDE = "described_but_not_in_slide"

# A notes line is a header ONLY if it is one or more comma-separated ``{{key}}`` tokens
# ending in a colon, e.g. ``{{name}}:`` or ``{{a}}, {{b}}:``. Anything else (including a
# line that merely mentions ``{{...}}`` inline) is description text.
_HEADER_PATTERN = re.compile(r"^\s*\{\{[^}]+\}\}(\s*,\s*\{\{[^}]+\}\})*\s*:\s*$")

# A "keep separator" line is a line of only dashes (>= 3). Everything in a slide's notes
# AFTER the first such line is content the author wants kept verbatim in the FILLED deck
# (e.g. real speaker notes); everything before it is template-authoring content (the
# ``{{key}}:`` headers + descriptions) that is stripped from the output. The same split
# is used by the parser (so keep-notes are never mistaken for headers) and by the filler
# (so the output keeps only the keep-notes).
_KEEP_SEPARATOR_PATTERN = re.compile(r"^\s*-{3,}\s*$")


def split_authoring_and_kept_notes(notes_text: str) -> "tuple[str, str]":
    """Split a slide's notes at the first keep-separator line (``---``).

    Returns ``(authoring_text, kept_text)`` where:

    - ``authoring_text`` is everything BEFORE the first all-dashes line (the
      ``{{key}}:`` headers and their descriptions). It is what the parser reads.
    - ``kept_text`` is everything AFTER that line, with one leading blank line trimmed,
      preserved verbatim as the notes of the filled deck. Empty when there is no
      separator.

    The separator line itself is dropped from both parts.
    """
    lines = notes_text.splitlines()
    for i, line in enumerate(lines):
        if _KEEP_SEPARATOR_PATTERN.match(line):
            authoring = "\n".join(lines[:i])
            kept_lines = lines[i + 1 :]
            # Trim a single leading blank line so "desc\n---\n\nnotes" keeps "notes".
            if kept_lines and kept_lines[0].strip() == "":
                kept_lines = kept_lines[1:]
            return authoring, "\n".join(kept_lines)
    return notes_text, ""


class KeyField(BaseModel):
    """A single template field: a ``{{key}}`` and its note description (scoped to one
    slide)."""

    key: str
    description: str = ""


class SlideSchema(BaseModel):
    """The fields of one slide, grouped under its 1-based slide number."""

    slide: int
    keys: List[KeyField] = Field(default_factory=list)


class TemplateError(BaseModel):
    """A per-slide validation error with a stable machine-readable ``code``."""

    slide: int
    key: str
    code: str
    message: str


class ParseResult(BaseModel):
    """Result of :func:`parse`: the per-slide schema and the list of errors.

    The per-slide schema field is named ``slides`` in Python (a bare ``schema``
    attribute would shadow ``BaseModel``), but serializes as ``schema`` so the JSON
    contract stays ``{ "schema": [...], "errors": [...] }`` as specified by the RFC.
    Populate it positionally or by either name.
    """

    model_config = ConfigDict(populate_by_name=True)

    slides: List[SlideSchema] = Field(
        default_factory=list, alias="schema", serialization_alias="schema"
    )
    errors: List[TemplateError] = Field(default_factory=list)


def _parse_notes_descriptions(notes_text: str) -> Dict[str, str]:
    """Parse a slide's notes into a ``{key: description}`` mapping.

    A header line (``{{a}}, {{b}}:``) introduces a (possibly multiline) description that
    runs until the next header or end of notes. Blank lines inside the block are kept;
    leading/trailing blank lines are trimmed. A multi-key header applies the same
    description to each listed key. Lines that merely mention ``{{...}}`` inline are
    description text, not headers.

    Only the authoring portion (before the first ``---`` keep-separator) is parsed; any
    kept-notes content after the separator is opaque and never read as headers.
    """
    descriptions: Dict[str, str] = {}
    authoring_text, _kept = split_authoring_and_kept_notes(notes_text)
    lines = authoring_text.splitlines()

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not _HEADER_PATTERN.match(line):
            # Stray description text with no preceding header: ignore it (only
            # described keys matter).
            i += 1
            continue

        # The keys named on this header line (one or more).
        header_keys = [m.strip() for m in KEY_PATTERN.findall(line)]

        # Collect the description block: every line until the next header or EOF.
        block: List[str] = []
        i += 1
        while i < n and not _HEADER_PATTERN.match(lines[i]):
            block.append(lines[i])
            i += 1

        # Trim leading/trailing blank lines but keep internal blank lines.
        start = 0
        end = len(block)
        while start < end and block[start].strip() == "":
            start += 1
        while end > start and block[end - 1].strip() == "":
            end -= 1
        description = "\n".join(block[start:end])

        for key in header_keys:
            # Last header for a key wins (consistent with later issues storing one
            # description per key per slide).
            descriptions[key] = description

    return descriptions


def _slide_notes_text(slide) -> str:
    """Return the plain text of a slide's notes, or ``""`` if it has none."""
    if not slide.has_notes_slide:
        return ""
    notes_slide = slide.notes_slide
    if notes_slide.notes_text_frame is None:
        return ""
    return notes_slide.notes_text_frame.text or ""


def apply_kept_notes_to_slide(slide) -> None:
    """Rewrite a slide's notes for the FILLED deck, dropping template-authoring content.

    The authoring notes (the ``{{key}}:`` headers and their descriptions) are internal
    guidance and must not leak into the deliverable. After filling, each slide's notes
    are replaced with only the *kept* portion (everything after the first ``---``
    keep-separator); if there is no separator, the notes are cleared entirely.

    Slides with no notes slide are left untouched (so we never create empty notes
    slides). The shared :func:`split_authoring_and_kept_notes` keeps this in lock-step
    with what the parser treats as authoring vs kept content.
    """
    if not slide.has_notes_slide:
        return
    notes_frame = slide.notes_slide.notes_text_frame
    if notes_frame is None:
        return
    _authoring, kept = split_authoring_and_kept_notes(notes_frame.text or "")
    # Setting ``.text`` collapses the frame to a single run with ``kept`` (or empties it).
    notes_frame.text = kept


def _dedupe_preserving_order(keys: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def parse(pptx_source: Union[bytes, str, Path]) -> ParseResult:
    """Parse a ``.pptx`` into a per-slide schema and a list of validation errors.

    ``pptx_source`` may be raw ``.pptx`` bytes, a path string, or a :class:`Path`.

    Validation is per-slide:

    - ``key_without_description`` — a key appears in a text box on slide N but has no
      description in slide N's notes.
    - ``described_but_not_in_slide`` — slide N's notes describe a key that never appears
      in a text box on slide N.

    The same key string on different slides is two independent fields (independent
    descriptions); the same key multiple times on one slide is one (deduped) field.
    """
    if isinstance(pptx_source, bytes):
        presentation = Presentation(io.BytesIO(pptx_source))
    else:
        presentation = Presentation(str(pptx_source))

    schema: List[SlideSchema] = []
    errors: List[TemplateError] = []

    for index, slide in enumerate(presentation.slides):
        slide_number = index + 1  # 1-based, as the author sees it

        text_keys = _dedupe_preserving_order(list_keys_on_slide(slide))
        described = _parse_notes_descriptions(_slide_notes_text(slide))

        # Build the schema for this slide from the text-box keys (deduped, in order).
        slide_keys: List[KeyField] = [
            KeyField(key=key, description=described.get(key, "")) for key in text_keys
        ]
        if slide_keys:
            schema.append(SlideSchema(slide=slide_number, keys=slide_keys))

        text_key_set = set(text_keys)

        # key_without_description: in a text box but not described in this slide's notes.
        for key in text_keys:
            if key not in described:
                errors.append(
                    TemplateError(
                        slide=slide_number,
                        key=key,
                        code=CODE_KEY_WITHOUT_DESCRIPTION,
                        message=(
                            f"{{{{{key}}}}} appears on slide {slide_number} but has no "
                            "description in the slide notes."
                        ),
                    )
                )

        # described_but_not_in_slide: described in notes but absent from this slide's
        # text boxes.
        for key in described:
            if key not in text_key_set:
                errors.append(
                    TemplateError(
                        slide=slide_number,
                        key=key,
                        code=CODE_DESCRIBED_BUT_NOT_IN_SLIDE,
                        message=(
                            f"{{{{{key}}}}} is described in the notes of slide "
                            f"{slide_number} but never appears in a text box on that "
                            "slide."
                        ),
                    )
                )

    # Construct via the ``schema`` alias (the field is named ``slides`` in Python to
    # avoid shadowing ``BaseModel``; ``populate_by_name=True`` also allows ``slides=``).
    return ParseResult(schema=schema, errors=errors)
