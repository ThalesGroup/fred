from __future__ import annotations

import posixpath
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from fred_core import FilesystemResourceInfo, FilesystemResourceInfoResult
from pydantic import BaseModel

# Unified layout (FILES-04): everything non-platform is rooted at /teams/{team_id}/...
# The team is the confidentiality perimeter; team_id is always the first segment.
AREA_TEAMS = "teams"
AREA_CORPUS = "corpus"

# Sub-areas inside one team box: /teams/{team_id}/{sub-area}/...
SUBAREA_USERS = "users"  # personal-in-team:  /teams/{t}/users/{uid}/...
SUBAREA_SHARED = "shared"  # team-shared:       /teams/{t}/shared/...
SUBAREA_AGENTS = "agents"  # agent-per-user:    /teams/{t}/agents/{agent_id}/users/{uid}/...
# Agent-config assets (#1903, AGENT-CAPABILITY-RFC §3.4): capability upload
# slots store their binaries here at agent save; every team member can read
# them at chat time: /teams/{t}/agents/{agent_id}/config/...
SUBAREA_AGENT_CONFIG = "config"

AREA_ALIASES = {
    AREA_TEAMS: AREA_TEAMS,
    AREA_CORPUS: AREA_CORPUS,
}


class VirtualArea(str, Enum):
    ROOT = "root"
    TEAMS = AREA_TEAMS
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


class FileReadPage(BaseModel):
    """
    Structured paginated filesystem read response.

    Why this exists:
    - agents need a deterministic continuation contract when `max_chars` stops a page early
    - keeping the response typed makes the HTTP and MCP surface explicit

    How to use:
    - call `format_numbered_file_page(...)` to build one page from raw file text
    - continue with `next_offset` until `has_more` becomes false

    Example:
    - `page = format_numbered_file_page(path="/corpus/documents/doc-1/preview.md", content="a\\nb", limit=1, max_chars=20)`
    """

    path: str
    content: str
    start_line: int
    end_line: int | None
    returned_lines: int
    total_lines: int
    has_more: bool
    next_offset: int | None
    truncated: bool


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
    max_chars: int | None = None,
) -> str:
    """
    Format one text excerpt with one-based numbered lines.

    Why this exists:
    - coding-oriented agents reason better over numbered excerpts than raw file blobs
    - pagination avoids forcing callers to read a full file in one shot

    How to use:
    - pass raw file text plus a zero-based offset and positive limit
    - optionally pass `max_chars` to cap the rendered excerpt length server-side
    - the result contains only the requested slice with line numbers

    Example:
    - `format_numbered_file_excerpt("a\\nb", offset=0, limit=1)` returns `"1 | a"`
    """

    return format_numbered_file_page(
        path="",
        content=content,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    ).content


def format_numbered_file_page(
    *,
    path: str,
    content: str,
    offset: int = 0,
    limit: int = 100,
    max_chars: int | None = None,
    max_read_lines: int | None = None,
    max_read_chars: int | None = None,
) -> FileReadPage:
    """
    Build one paginated numbered filesystem read page with safe continuation metadata.

    Why this exists:
    - agents must be able to continue reading long files without guessing the next offset
    - `read_file` and `read_file_page` should share one deterministic pagination algorithm

    How to use:
    - pass the raw file text plus the requested offset/limit/max_chars
    - optionally pass server-side ceiling values to enforce hard bounds

    Example:
    - `format_numbered_file_page(path="/workspace/report.md", content="a\\nb", offset=0, limit=1, max_chars=20)`
    """

    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if max_read_lines is not None and limit > max_read_lines:
        raise ValueError(f"limit must be <= {max_read_lines}")
    if max_chars is not None and max_chars <= 0:
        raise ValueError("max_chars must be > 0")
    if max_chars is not None and max_read_chars is not None and max_chars > max_read_chars:
        raise ValueError(f"max_chars must be <= {max_read_chars}")

    lines = content.splitlines()
    total_lines = len(lines)
    if offset >= total_lines:
        return FileReadPage(
            path=path,
            content="",
            start_line=offset,
            end_line=None,
            returned_lines=0,
            total_lines=total_lines,
            has_more=False,
            next_offset=None,
            truncated=False,
        )

    requested_end = min(offset + limit, total_lines)
    width = len(str(requested_end))
    rendered_lines: list[str] = []
    truncated = False

    for line_index in range(offset, requested_end):
        rendered_line = f"{line_index + 1:>{width}} | {lines[line_index]}"
        candidate_lines = [*rendered_lines, rendered_line]
        candidate = "\n".join(candidate_lines)
        if max_chars is None or len(candidate) <= max_chars:
            rendered_lines.append(rendered_line)
            continue

        truncated = True
        if not rendered_lines:
            if max_chars == 1:
                rendered_lines.append("…")
            else:
                trimmed = rendered_line[: max_chars - 1].rstrip()
                rendered_lines.append(f"{trimmed}…" if trimmed else "…")
            break
        break

    returned_lines = len(rendered_lines)
    end_line = offset + returned_lines - 1 if returned_lines > 0 else None
    next_offset = offset + returned_lines
    has_more = next_offset < total_lines
    if not has_more:
        next_offset = None

    return FileReadPage(
        path=path,
        content="\n".join(rendered_lines),
        start_line=offset,
        end_line=end_line,
        returned_lines=returned_lines,
        total_lines=total_lines,
        has_more=has_more,
        next_offset=next_offset,
        truncated=truncated,
    )


def resolve_virtual_path(path: str) -> ResolvedVirtualPath:
    """
    Resolve one visible path to its canonical virtual area and local segments.

    Why this exists:
    - the unified layout has exactly two top-level areas: `/teams/...` (everything
      team-scoped) and `/corpus/...` (the read-only corpus view)
    - every router/helper can share the same canonical area contract

    How to use:
    - pass any visible path received from API or MCP callers
    - use the returned `area` for dispatch and `segments` for area-local logic
    - an unknown top-level segment is rejected: there is no implicit/default area

    Example:
    - `resolve_virtual_path("/teams/acme/shared/x").area == VirtualArea.TEAMS`
    - `resolve_virtual_path("/teams/acme/shared/x").segments == ("acme", "shared", "x")`
    """

    normalized = normalize_virtual_path(path)
    if not normalized:
        return ResolvedVirtualPath(area=VirtualArea.ROOT, segments=())
    parts = tuple(seg for seg in normalized.split("/") if seg)
    head = parts[0]
    area = AREA_ALIASES.get(head)
    if area is None:
        raise ValueError(f"Unknown filesystem area: {head!r} (expected '{AREA_TEAMS}' or '{AREA_CORPUS}')")
    return ResolvedVirtualPath(area=VirtualArea(area), segments=parts[1:])
