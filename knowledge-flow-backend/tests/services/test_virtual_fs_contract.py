import pytest

from knowledge_flow_backend.features.filesystem.virtual_fs_contract import (
    VirtualArea,
    absolute_virtual_path,
    format_numbered_file_excerpt,
    normalize_virtual_path,
    resolve_virtual_path,
)


def test_resolve_virtual_path_supports_workspace_alias_and_default_area():
    alias_result = resolve_virtual_path("/user/reports")
    default_result = resolve_virtual_path("notes/todo.md")

    assert alias_result.area == VirtualArea.WORKSPACE
    assert alias_result.segments == ("reports",)
    assert default_result.area == VirtualArea.WORKSPACE
    assert default_result.segments == ("notes", "todo.md")


def test_normalize_virtual_path_rejects_parent_segments():
    with pytest.raises(ValueError, match="parent path segments"):
        normalize_virtual_path("/workspace/../../secret")


def test_absolute_virtual_path_normalizes_root_and_relative_paths():
    assert absolute_virtual_path("") == "/"
    assert absolute_virtual_path("corpus/CIR") == "/corpus/CIR"


def test_format_numbered_file_excerpt_applies_pagination():
    excerpt = format_numbered_file_excerpt("a\nb\nc", offset=1, limit=2)

    assert excerpt == "2 | b\n3 | c"


def test_format_numbered_file_excerpt_validates_bounds():
    with pytest.raises(ValueError, match="offset must be >= 0"):
        format_numbered_file_excerpt("a", offset=-1)
    with pytest.raises(ValueError, match="limit must be > 0"):
        format_numbered_file_excerpt("a", limit=0)
