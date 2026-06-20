import pytest

from knowledge_flow_backend.features.filesystem.virtual_fs_contract import (
    FileReadPage,
    VirtualArea,
    absolute_virtual_path,
    format_numbered_file_excerpt,
    format_numbered_file_page,
    normalize_virtual_path,
    resolve_virtual_path,
)


def test_resolve_virtual_path_routes_teams_and_corpus():
    teams_result = resolve_virtual_path("/teams/acme/shared/reports/q3.md")
    corpus_result = resolve_virtual_path("/corpus/CIR")

    assert teams_result.area == VirtualArea.TEAMS
    assert teams_result.segments == ("acme", "shared", "reports", "q3.md")
    assert corpus_result.area == VirtualArea.CORPUS
    assert corpus_result.segments == ("CIR",)


def test_resolve_virtual_path_rejects_unknown_top_level_area():
    # No implicit/default area: an unknown head (including a bare relative path) is rejected.
    with pytest.raises(ValueError, match="Unknown filesystem area"):
        resolve_virtual_path("notes/todo.md")
    with pytest.raises(ValueError, match="Unknown filesystem area"):
        resolve_virtual_path("/workspace/old")


def test_normalize_virtual_path_rejects_parent_segments():
    with pytest.raises(ValueError, match="parent path segments"):
        normalize_virtual_path("/workspace/../../secret")


def test_absolute_virtual_path_normalizes_root_and_relative_paths():
    assert absolute_virtual_path("") == "/"
    assert absolute_virtual_path("corpus/CIR") == "/corpus/CIR"


def test_format_numbered_file_excerpt_applies_pagination():
    excerpt = format_numbered_file_excerpt("a\nb\nc", offset=1, limit=2)

    assert excerpt == "2 | b\n3 | c"


def test_format_numbered_file_excerpt_applies_max_chars_cap():
    excerpt = format_numbered_file_excerpt("alpha\nbeta\ngamma", offset=0, limit=3, max_chars=10)

    assert excerpt == "1 | alpha"


def test_format_numbered_file_page_returns_safe_next_offset_after_truncation():
    page = format_numbered_file_page(
        path="/corpus/documents/doc-1/preview.md",
        content="alpha\nbeta\ngamma",
        offset=0,
        limit=3,
        max_chars=12,
        max_read_lines=500,
        max_read_chars=50_000,
    )

    assert page == FileReadPage(
        path="/corpus/documents/doc-1/preview.md",
        content="1 | alpha",
        start_line=0,
        end_line=0,
        returned_lines=1,
        total_lines=3,
        has_more=True,
        next_offset=1,
        truncated=True,
    )


def test_format_numbered_file_page_returns_empty_page_beyond_end():
    page = format_numbered_file_page(
        path="/workspace/report.md",
        content="a\nb",
        offset=5,
        limit=2,
        max_chars=20,
        max_read_lines=500,
        max_read_chars=50_000,
    )

    assert page.content == ""
    assert page.start_line == 5
    assert page.end_line is None
    assert page.returned_lines == 0
    assert page.total_lines == 2
    assert page.has_more is False
    assert page.next_offset is None
    assert page.truncated is False


def test_format_numbered_file_page_handles_single_overlong_line_without_loop():
    page = format_numbered_file_page(
        path="/workspace/report.md",
        content="abcdefghijklmnop\nbeta",
        offset=0,
        limit=2,
        max_chars=10,
        max_read_lines=500,
        max_read_chars=50_000,
    )

    assert page.content == "1 | abcde…"
    assert page.returned_lines == 1
    assert page.next_offset == 1
    assert page.has_more is True
    assert page.truncated is True


def test_format_numbered_file_page_handles_exact_page_boundary():
    page = format_numbered_file_page(
        path="/workspace/report.md",
        content="a\nb\nc\nd",
        offset=0,
        limit=2,
        max_chars=100,
        max_read_lines=500,
        max_read_chars=50_000,
    )

    assert page.content == "1 | a\n2 | b"
    assert page.returned_lines == 2
    assert page.next_offset == 2
    assert page.has_more is True
    assert page.truncated is False


def test_format_numbered_file_page_handles_unicode_and_trailing_newlines():
    page = format_numbered_file_page(
        path="/workspace/report.md",
        content="éclair\nbonjour\n",
        offset=0,
        limit=5,
        max_chars=100,
        max_read_lines=500,
        max_read_chars=50_000,
    )

    assert page.content == "1 | éclair\n2 | bonjour"
    assert page.total_lines == 2
    assert page.has_more is False


def test_format_numbered_file_excerpt_validates_bounds():
    with pytest.raises(ValueError, match="offset must be >= 0"):
        format_numbered_file_excerpt("a", offset=-1)
    with pytest.raises(ValueError, match="limit must be > 0"):
        format_numbered_file_excerpt("a", limit=0)
    with pytest.raises(ValueError, match="max_chars must be > 0"):
        format_numbered_file_excerpt("a", max_chars=0)
    with pytest.raises(ValueError, match="limit must be <= 500"):
        format_numbered_file_page(path="/x", content="a", limit=501, max_chars=10, max_read_lines=500, max_read_chars=50_000)
    with pytest.raises(ValueError, match="max_chars must be <= 50000"):
        format_numbered_file_page(path="/x", content="a", limit=1, max_chars=50_001, max_read_lines=500, max_read_chars=50_000)
