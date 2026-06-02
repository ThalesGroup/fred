from __future__ import annotations

import posixpath
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from fred_core import FilesystemResourceInfo, FilesystemResourceInfoResult

AREA_WORKSPACE = "workspace"
AREA_USER_LEGACY = "user"
AREA_AGENT = "agent"
AREA_TEAM = "team"
AREA_CORPUS = "corpus"

AREA_ALIASES = {
    AREA_WORKSPACE: AREA_WORKSPACE,
    AREA_USER_LEGACY: AREA_WORKSPACE,
    AREA_AGENT: AREA_AGENT,
    AREA_TEAM: AREA_TEAM,
    AREA_CORPUS: AREA_CORPUS,
}


class VirtualArea(str, Enum):
    ROOT = "root"
    WORKSPACE = AREA_WORKSPACE
    AGENT = AREA_AGENT
    TEAM = AREA_TEAM
    CORPUS = AREA_CORPUS


@dataclass(frozen=True)
class ResolvedVirtualPath:
    """
    Canonical path resolution result for the Fred virtual filesystem.

    Why this exists:
    - all filesystem operations first need a stable view of which top-level area
      a visible path belongs to
    - sharing this contract keeps routing logic small and consistent across modules

    How to use:
    - call `resolve_virtual_path(...)`
    - consume `area` for routing and `segments` for area-local handling

    Example:
    - `resolve_virtual_path("/workspace/reports").segments == ("reports",)`
    """

    area: VirtualArea
    segments: tuple[str, ...]


def current_time_utc() -> datetime:
    """
    Return the current UTC timestamp for virtual filesystem metadata.

    Why this exists:
    - virtual files such as rendered corpus previews need a synthetic timestamp
    - centralizing it keeps metadata generation consistent

    How to use:
    - call when building a synthetic `FilesystemResourceInfoResult` for a file

    Example:
    - `modified=current_time_utc()`
    """

    return datetime.now(timezone.utc)


def dir_entry(path: str) -> FilesystemResourceInfoResult:
    """
    Build one virtual directory entry.

    Why this exists:
    - the virtual filesystem frequently returns synthetic directory nodes
    - using one helper avoids repeating dataclass construction everywhere

    How to use:
    - pass the visible path segment or path to expose as a directory

    Example:
    - `dir_entry("corpus")`
    """

    return FilesystemResourceInfoResult(
        path=path,
        size=None,
        type=FilesystemResourceInfo.DIRECTORY,
        modified=None,
    )


def file_entry(path: str, size: int) -> FilesystemResourceInfoResult:
    """
    Build one virtual file entry.

    Why this exists:
    - virtual filesystem implementations often synthesize files from metadata
    - using one helper keeps file metadata shape consistent

    How to use:
    - pass the visible file path and its byte size

    Example:
    - `file_entry("preview.md", 128)`
    """

    return FilesystemResourceInfoResult(
        path=path,
        size=size,
        type=FilesystemResourceInfo.FILE,
        modified=current_time_utc(),
    )


def normalize_virtual_path(path: str) -> str:
    """
    Normalize one visible virtual filesystem path.

    Why this exists:
    - all filesystem callers should share one path grammar
    - normalization rejects traversal while keeping POSIX-style segments

    How to use:
    - pass any user-visible path
    - the result never starts with `/` and contains no `..` segments

    Example:
    - `normalize_virtual_path("/workspace/./notes")` returns `"workspace/notes"`
    """

    raw = (path or "").strip().replace("\\", "/").lstrip("/")
    if not raw:
        return ""
    normalized = posixpath.normpath(raw)
    if normalized in (".", "/"):
        return ""
    parts = [seg for seg in normalized.split("/") if seg]
    if any(seg == ".." for seg in parts):
        raise ValueError("Path cannot contain parent path segments")
    return "/".join(parts)


def join_segments(segments: tuple[str, ...]) -> str:
    """
    Join normalized path segments back into one visible relative path.

    Why this exists:
    - area-local routing works with segment tuples for safety
    - storage and service calls still need a joined relative path

    How to use:
    - pass the tuple returned by `resolve_virtual_path(...)`

    Example:
    - `join_segments(("reports", "q1.md"))` returns `"reports/q1.md"`
    """

    if not segments:
        return ""
    return "/".join(segments)


def absolute_virtual_path(path: str) -> str:
    """
    Normalize one visible virtual path to absolute POSIX form.

    Why this exists:
    - search-style helpers and agent-facing APIs should expose one stable
      absolute-path convention
    - it avoids mixing `corpus/x` and `/corpus/x` in returned results

    How to use:
    - pass any visible virtual path accepted by the filesystem service
    - the result always starts with `/`

    Example:
    - `absolute_virtual_path("corpus/CIR")` returns `"/corpus/CIR"`
    """

    normalized = normalize_virtual_path(path)
    return f"/{normalized}" if normalized else "/"


def join_virtual_child(parent_path: str, child_name: str) -> str:
    """
    Join one direct child name onto an absolute virtual parent path.

    Why this exists:
    - `ls(...)` returns direct child names, not absolute paths
    - recursive walkers need to rebuild absolute paths in a safe, uniform way

    How to use:
    - pass an absolute parent path and a child name returned by `ls(...)`

    Example:
    - `join_virtual_child("/workspace", "notes.txt")`
      returns `"/workspace/notes.txt"`
    """

    if parent_path == "/":
        return f"/{child_name}"
    return f"{parent_path.rstrip('/')}/{child_name}"


def format_numbered_file_excerpt(
    content: str,
    *,
    offset: int = 0,
    limit: int = 100,
) -> str:
    """
    Format one text excerpt with one-based numbered lines.

    Why this exists:
    - coding-oriented agents reason better over numbered excerpts than raw file blobs
    - pagination avoids forcing callers to read a full file in one shot

    How to use:
    - pass raw file text plus a zero-based offset and positive limit
    - the result contains only the requested slice with line numbers

    Example:
    - `format_numbered_file_excerpt("a\\nb", offset=0, limit=1)` returns `"1 | a"`
    """

    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit <= 0:
        raise ValueError("limit must be > 0")

    lines = content.splitlines()
    excerpt = lines[offset : offset + limit]
    if not excerpt:
        return ""

    width = len(str(offset + len(excerpt)))
    return "\n".join(f"{offset + index + 1:>{width}} | {line}" for index, line in enumerate(excerpt))


def resolve_virtual_path(
    path: str,
    *,
    default_area: VirtualArea = VirtualArea.WORKSPACE,
) -> ResolvedVirtualPath:
    """
    Resolve one visible path to its canonical virtual area and local segments.

    Why this exists:
    - the filesystem should expose one stable root layout while still accepting
      a few legacy aliases such as `/user`
    - every router/helper can share the same canonical area contract

    How to use:
    - pass any visible path received from API or MCP callers
    - use the returned `area` for dispatch and `segments` for area-local logic

    Example:
    - `resolve_virtual_path("/user/reports").area == VirtualArea.WORKSPACE`
    """

    normalized = normalize_virtual_path(path)
    if not normalized:
        return ResolvedVirtualPath(area=VirtualArea.ROOT, segments=())
    parts = tuple(seg for seg in normalized.split("/") if seg)
    head = parts[0]
    if head in AREA_ALIASES:
        return ResolvedVirtualPath(
            area=VirtualArea(AREA_ALIASES[head]),
            segments=parts[1:],
        )
    return ResolvedVirtualPath(area=default_area, segments=parts)
