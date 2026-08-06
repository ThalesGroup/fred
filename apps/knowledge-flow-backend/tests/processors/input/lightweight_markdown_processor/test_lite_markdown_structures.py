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

"""Unit tests for strip_surrogates (issue #2261).

PyMuPDF reads text through a PDF's ToUnicode CMap, which is UTF-16BE. A malformed
CMap leaks unpaired surrogates into the extracted str; a str may hold one, UTF-8
cannot encode one, so ingestion used to die with UnicodeEncodeError on the first
encode — and, the input being deterministic, on all three Temporal retries too.
"""

from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import (
    strip_surrogates,
)

HIGH = chr(0xD83D)  # high surrogate of U+1F600 GRINNING FACE
LOW = chr(0xDE00)  # low surrogate of U+1F600
LONE = chr(0xDBFF)  # the exact code point reported in issue #2261


def test_clean_text_is_returned_unchanged():
    text = "# Title\n\nPlain ASCII, accents (éàü) and CJK (日本語) are all untouched."
    assert strip_surrogates(text) is text


def test_empty_text_is_returned_unchanged():
    assert strip_surrogates("") == ""


def test_lone_surrogate_is_dropped():
    assert strip_surrogates(f"AERS Sensor{LONE} ICD") == "AERS Sensor ICD"


def test_leaked_surrogate_pair_is_recombined_not_lost():
    # The extractor failed to combine the pair; the real character is recoverable,
    # so it must survive rather than be silently deleted with the broken ones.
    assert strip_surrogates(f"emoji {HIGH}{LOW} here") == "emoji \U0001f600 here"


def test_mixed_pair_and_lone_surrogates():
    assert strip_surrogates(f"a{HIGH}{LOW}b{LONE}c") == "a\U0001f600bc"


def test_result_is_always_utf8_encodable():
    for raw in (f"x{LONE}y", f"{LOW}{HIGH}", HIGH, LOW, f"{HIGH}{LOW}{LONE}"):
        # The assertion is that this does not raise UnicodeEncodeError.
        strip_surrogates(raw).encode("utf-8")
