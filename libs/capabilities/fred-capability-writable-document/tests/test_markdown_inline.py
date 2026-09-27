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

"""Inline-Markdown parser tests (adapted from Kea's ``test_markdown_inline.py``)."""

from __future__ import annotations

from fred_capability_writable_document.inline import Span, parse_inline_markdown


def test_plain_text_is_a_single_unstyled_span():
    assert parse_inline_markdown("just text") == [Span("just text")]


def test_empty_text_yields_one_empty_span():
    # Consumers always need at least one run to write; an empty value is one empty span.
    assert parse_inline_markdown("") == [Span("")]


def test_bold_span():
    assert parse_inline_markdown("a **b** c") == [
        Span("a "),
        Span("b", bold=True),
        Span(" c"),
    ]


def test_italic_star_span():
    assert parse_inline_markdown("a *b* c") == [
        Span("a "),
        Span("b", italic=True),
        Span(" c"),
    ]


def test_italic_underscore_span():
    assert parse_inline_markdown("a _b_ c") == [
        Span("a "),
        Span("b", italic=True),
        Span(" c"),
    ]


def test_bold_and_italic_combined_reads_as_bold():
    # ***x*** is matched as bold whose inner '*x*' markers are stripped (flat parsing).
    assert parse_inline_markdown("***x***") == [Span("x", bold=True)]


def test_nested_markers_do_not_leak():
    # Flat parsing keeps the outermost emphasis and strips inner markers; no stray
    # '*'/'_' ever survives.
    spans = parse_inline_markdown("**_x_**")
    assert spans == [Span("x", bold=True)]


def test_stray_unmatched_markers_are_stripped():
    spans = parse_inline_markdown("a lone * and a stray _ here")
    text = "".join(s.text for s in spans)
    assert "*" not in text and "_" not in text
    assert all(not (s.bold or s.italic) for s in spans)


def test_code_span_is_flagged_and_kept_literal():
    spans = parse_inline_markdown("use `a_b * c` now")
    code = next((s for s in spans if s.code), None)
    assert code is not None
    # Markers inside backticks are literal: not stripped, not styled bold/italic.
    assert code.text == "a_b * c"
    assert not (code.bold or code.italic)


def test_multiple_spans_in_order():
    assert parse_inline_markdown("**A** and *B*") == [
        Span("A", bold=True),
        Span(" and "),
        Span("B", italic=True),
    ]
