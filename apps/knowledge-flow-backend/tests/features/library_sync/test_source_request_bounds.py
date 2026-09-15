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

"""What this surface accepts from a caller, and what it tells one when it fails.

A source key and a version are the caller's own vocabulary: bounded, never read.
A path says where in the library the document goes, so it is refused unless
nothing but a location inside that library is left. And what comes back from a
failure the caller did not cause is bounded too.
"""

import pytest

from knowledge_flow_backend.features.library_sync.controller import _bounded_failure
from knowledge_flow_backend.features.library_sync.structures import (
    MAX_SOURCE_KEY_LENGTH,
    MAX_VERSION_LENGTH,
    InvalidSourceRequest,
    split_document_path,
    validate_source_key,
    validate_version,
)


@pytest.mark.parametrize(
    "key",
    [
        "docs/api/openapi.md",
        "../not/a/path/at/all",
        "urn:acme:record:42",
        "rapport 2026 — révisé (v2).pdf",
        "?query=1&page=2#top",
        "  leading and trailing spaces  ",
    ],
)
def test_a_key_the_caller_chose_comes_back_as_it_was_sent(key):
    """No trimming, no normalizing: a key that changed shape would orphan its document."""
    assert validate_source_key(key) == key


@pytest.mark.parametrize(
    "key",
    ["", "   ", "a" * (MAX_SOURCE_KEY_LENGTH + 1), "with\na newline", "with\x00a nul"],
)
def test_a_key_outside_its_bounds_is_refused(key):
    with pytest.raises(InvalidSourceRequest):
        validate_source_key(key)


def test_a_version_is_opaque_and_optional():
    assert validate_version(None, label="v", code_prefix="v") is None
    for version in ("9d2f1a", "2026-w03", "AAECAwQ=", "r7"):
        assert validate_version(version, label="v", code_prefix="v") == version


@pytest.mark.parametrize("version", ["", "  ", "a" * (MAX_VERSION_LENGTH + 1), "tab\tseparated"])
def test_a_version_outside_its_bounds_is_refused(version):
    with pytest.raises(InvalidSourceRequest):
        validate_version(version, label="v", code_prefix="v")


def test_a_path_splits_into_its_folders_and_the_document_s_name():
    assert split_document_path("specs/api/openapi.md") == (["specs", "api"], "openapi.md")
    assert split_document_path("readme.md") == ([], "readme.md")


@pytest.mark.parametrize(
    "path",
    [
        "../outside.md",
        "specs/../../outside.md",
        "specs/./readme.md",
        "/absolute.md",
        "/etc/passwd",
        "..\\windows.md",
        "specs\\api\\openapi.md",
        # Percent-encoded: the form field arrives as written, so these reach the
        # handler literally — and must not become an escape further down.
        "%2e%2e%2foutside.md",
        "specs/%2E%2E/outside.md",
        "%2Fabsolute.md",
        "readme%00.md",
        "",
        "   ",
        "specs//openapi.md",
    ],
)
def test_a_path_that_could_leave_the_library_is_refused(path):
    with pytest.raises(InvalidSourceRequest):
        split_document_path(path)


def test_a_failure_says_its_kind_and_none_of_the_server_s_business():
    """Enough to decide what to do, and nothing a caller could not act on."""
    internal_detail = "/srv/kf/tmp/x1y2"
    failure = _bounded_failure(RuntimeError(f"boom at {internal_detail}"))

    assert failure.status_code == 500
    assert failure.detail == {"code": "document_write_failed", "failure": "RuntimeError"}
    assert internal_detail not in str(failure.detail)


def test_the_kind_is_what_tells_a_retry_from_a_dead_end():
    assert _bounded_failure(TimeoutError()).detail["failure"] == "TimeoutError"
    assert _bounded_failure(ValueError("x")).detail["failure"] == "ValueError"
