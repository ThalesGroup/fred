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

"""HTTP tests for the capability's stateless ``POST /analyze`` route.

Port of Kea's ``tests/test_ppt_filler_analyze_controller.py`` re-seated on the
capability router: the analyze endpoint now lives on
``PptFillerCapability.manifest.router`` and is mounted on a bare FastAPI app. The
route is STATELESS — it has no platform access, so it reports every offline error
code but never ``folder_not_found`` (folder existence needs a resolver, which the
save round-trip supplies). An unreadable upload returns ``200`` with a single
``slide=0`` ``invalid_upload`` error, not a 4xx.
"""

from __future__ import annotations

import pytest
from deck_builders import IMAGE_NOTES, build_deck, build_table_deck
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from fred_capability_ppt_filler.capability import PptFillerCapability

_PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(PptFillerCapability.manifest.router)
    return TestClient(app)


def _post_deck(
    client: TestClient, deck: bytes, *, filename="template.pptx", ctype=None
):
    return client.post(
        "/analyze",
        files={"file": (filename, deck, ctype or _PPTX_CONTENT_TYPE)},
    )


def test_analyze_valid_template_returns_200_schema_and_empty_errors(client):
    deck = build_deck(
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


def test_analyze_template_with_errors_returns_200_with_structured_errors(client):
    # {{age}} appears on slide 1 but is not described; {{ghost}} is described but absent.
    deck = build_deck(
        [
            (
                "Hi {{name}} aged {{age}}",
                "{{name}}:\nThe name\n{{ghost}}:\nA stale description",
            )
        ]
    )

    response = _post_deck(client, deck)

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

    for error in body["errors"]:
        assert set(error.keys()) == {"slide", "key", "code", "message"}

    codes = {(e["code"], e["key"], e["slide"]) for e in body["errors"]}
    assert ("key_without_description", "age", 1) in codes
    assert ("described_but_not_in_slide", "ghost", 1) in codes


def test_analyze_reports_each_error_against_its_own_slide(client):
    deck = build_deck(
        [
            ("Hello {{name}} the {{role}}", "{{name}}:\nThe name"),
            ("City: {{city}}", "{{city}}:\nThe city\n{{country}}:\nA ghost country"),
        ]
    )

    response = _post_deck(client, deck)

    assert response.status_code == status.HTTP_200_OK
    codes = {(e["code"], e["key"], e["slide"]) for e in response.json()["errors"]}
    assert ("key_without_description", "role", 1) in codes
    assert ("described_but_not_in_slide", "country", 2) in codes
    # Errors do not leak onto the wrong slide.
    assert ("key_without_description", "role", 2) not in codes
    assert ("described_but_not_in_slide", "country", 1) not in codes


def test_analyze_unreadable_upload_returns_200_with_invalid_upload_error(client):
    """A non-.pptx upload -> 200 with a single slide=0 invalid_upload error (not a 4xx)."""
    response = client.post(
        "/analyze",
        files={"file": ("notes.txt", b"this is not a pptx", "text/plain")},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["schema"] == []
    assert len(body["errors"]) == 1
    error = body["errors"][0]
    assert error["slide"] == 0
    assert error["key"] == ""
    assert error["code"] == "invalid_upload"


def test_analyze_reports_image_location_error(client):
    """An image key sitting in a table cell -> image_key_invalid_location (offline geometry
    check runs even with no resolver)."""
    deck = build_table_deck(IMAGE_NOTES, ["{{logo}}", "plain"])

    response = _post_deck(client, deck)

    assert response.status_code == status.HTTP_200_OK
    codes = {(e["code"], e["key"], e["slide"]) for e in response.json()["errors"]}
    assert ("image_key_invalid_location", "logo", 1) in codes


def test_analyze_does_not_report_folder_not_found(client):
    """A well-formed image template in a text box -> no folder_not_found on the stateless
    route (resolver=None), and the schema key keeps folder_tag_id unresolved."""
    deck = build_deck([("{{logo}}", IMAGE_NOTES)])

    response = _post_deck(client, deck)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert [e["code"] for e in body["errors"]] == []
    logo = body["schema"][0]["keys"][0]
    assert logo["type"] == "image"
    assert logo["folder"] == "Brand/Logos"
    assert logo.get("folder_tag_id") is None
