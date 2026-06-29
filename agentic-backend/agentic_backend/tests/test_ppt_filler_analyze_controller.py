# Copyright Thales 2025
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

"""Thin HTTP smoke test for the stateless PPT Filler analyze endpoint.

Core parsing is already covered by ``tests/test_ppt_filler_parser.py`` (PPTFILL-01); this
only asserts the ``200 { schema, errors }`` response shape — for a valid upload and for a
template that produces parse errors carrying ``slide``, ``key``, ``code``, ``message``.

Decks are built in-test with python-pptx (no checked-in binaries), mirroring the
PPTFILL-01 parser tests.
"""

import io
from typing import List, Tuple

from fastapi import status
from fastapi.testclient import TestClient
from pptx import Presentation
from pptx.util import Inches

_ANALYZE_URL = "/agentic/v1/agents/ppt-filler/analyze"
_HEADERS = {"Authorization": "Bearer dummy-token"}

# (text-box body, notes text) per slide — same fixture shape as the PPTFILL-01 tests.
SlideSpec = Tuple[str, str]


def _build_deck(slides: List[SlideSpec]) -> bytes:
    """Build a ``.pptx`` with one text box and one notes block per slide spec."""
    presentation = Presentation()
    blank_layout = presentation.slide_layouts[6]  # blank
    for body, notes in slides:
        slide = presentation.slides.add_slide(blank_layout)
        textbox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
        textbox.text_frame.text = body
        if notes:
            notes_frame = slide.notes_slide.notes_text_frame
            assert notes_frame is not None  # python-pptx creates it on access
            notes_frame.text = notes
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def _post_deck(client: TestClient, deck: bytes):
    return client.post(
        _ANALYZE_URL,
        headers=_HEADERS,
        files={
            "file": (
                "template.pptx",
                deck,
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
    )


def test_analyze_valid_template_returns_200_schema_and_empty_errors(
    client: TestClient,
):
    deck = _build_deck(
        [
            (
                "Hello {{name}} and {{role}}",
                "{{name}}:\nThe person's name\n{{role}}:\nTheir role",
            ),
            ("City: {{city}}", "{{city}}:\nThe city"),
        ]
    )

    response = _post_deck(client, deck)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert set(body.keys()) == {"schema", "errors"}
    assert body["errors"] == []
    assert body["schema"] == [
        {
            "slide": 1,
            "keys": [
                {"key": "name", "description": "The person's name"},
                {"key": "role", "description": "Their role"},
            ],
        },
        {"slide": 2, "keys": [{"key": "city", "description": "The city"}]},
    ]


def test_analyze_template_with_errors_returns_200_with_structured_errors(
    client: TestClient,
):
    # {{age}} appears on slide 1 but is not described; {{ghost}} is described but absent.
    deck = _build_deck(
        [
            (
                "Hi {{name}} aged {{age}}",
                "{{name}}:\nThe name\n{{ghost}}:\nA stale description",
            )
        ]
    )

    response = _post_deck(client, deck)

    # Analyze returns 200 even with errors (schema + errors shown together).
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert set(body.keys()) == {"schema", "errors"}

    # Schema is still returned (the text-box keys, deduped per slide).
    assert body["schema"] == [
        {
            "slide": 1,
            "keys": [
                {"key": "name", "description": "The name"},
                {"key": "age", "description": ""},
            ],
        }
    ]

    # Every error carries slide, key, code, message.
    for error in body["errors"]:
        assert set(error.keys()) == {"slide", "key", "code", "message"}

    codes = {(e["code"], e["key"], e["slide"]) for e in body["errors"]}
    assert ("key_without_description", "age", 1) in codes
    assert ("described_but_not_in_slide", "ghost", 1) in codes


def test_analyze_reports_each_error_against_its_own_slide(client: TestClient):
    """Errors are attributed per-slide: a missing-description error on slide 1 and a
    ghost-key error on slide 2 each carry their own slide number (not conflated)."""
    deck = _build_deck(
        [
            # Slide 1: {{role}} has no description -> key_without_description on slide 1.
            ("Hello {{name}} the {{role}}", "{{name}}:\nThe name"),
            # Slide 2: {{country}} is described but absent -> described_but_not_in_slide on slide 2.
            ("City: {{city}}", "{{city}}:\nThe city\n{{country}}:\nA ghost country"),
        ]
    )

    response = _post_deck(client, deck)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert set(body.keys()) == {"schema", "errors"}

    for error in body["errors"]:
        assert set(error.keys()) == {"slide", "key", "code", "message"}

    codes = {(e["code"], e["key"], e["slide"]) for e in body["errors"]}
    # Each error is pinned to the slide it actually occurs on.
    assert ("key_without_description", "role", 1) in codes
    assert ("described_but_not_in_slide", "country", 2) in codes
    # The missing-description error must NOT leak onto slide 2, nor the ghost onto slide 1.
    assert ("key_without_description", "role", 2) not in codes
    assert ("described_but_not_in_slide", "country", 1) not in codes


def test_analyze_rejects_non_pptx_upload_with_400(client: TestClient):
    response = client.post(
        _ANALYZE_URL,
        headers=_HEADERS,
        files={"file": ("notes.txt", b"this is not a pptx", "text/plain")},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
