# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Build a bounded search program for the existing isolated execution port."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchFilesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["inputs", "skills"] = "inputs"
    file_glob: str = Field(default="*", min_length=1, max_length=200)
    query: str = Field(default="", max_length=200)


def build_search_program(
    request: SearchFilesRequest, *, root: str | None = None
) -> str:
    values = {
        "root": root if root is not None else f"/{request.scope}",
        "file_glob": request.file_glob,
        "query": request.query,
    }
    return "CONFIG = " + repr(values) + "\n" + _SEARCH_PROGRAM


_SEARCH_PROGRAM = r"""
import codecs
import fnmatch
import json
import os
import re

root = CONFIG["root"]
pattern = CONFIG["file_glob"]
query = CONFIG["query"].strip()
allowed_suffixes = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".yaml",
    ".yml", ".xml", ".html", ".htm", ".log", ".py", ".sh",
}
max_paths = 50
max_matches = 20
max_files = 1000
max_entries = 10000
max_bytes = 32 * 1024 * 1024
max_output_chars = 12000
paths = []
matches = []
visited = 0
entries_seen = 0
scanned_bytes = 0
output_chars = 0
truncated = False

tokens = re.split(r"[\s_-]+", query)
expression = re.compile(r"[\s_-]+".join(map(re.escape, tokens)), re.IGNORECASE) if query else None
root_real = os.path.realpath(root)
prefix = []
for part in pattern.split("/")[:-1]:
    if part in ("", ".", "..") or any(char in part for char in "*?["):
        break
    prefix.append(part)
search_root = os.path.join(root, *prefix)

if (
    os.path.isdir(search_root)
    and not os.path.islink(root)
    and not os.path.islink(search_root)
    and os.path.commonpath((root_real, os.path.realpath(search_root))) == root_real
):
    for directory, dirs, files in os.walk(search_root, followlinks=False):
        entries_seen += 1
        if entries_seen > max_entries:
            truncated = True
            break
        dirs[:] = sorted(name for name in dirs if not os.path.islink(os.path.join(directory, name)))
        for name in sorted(files):
            entries_seen += 1
            if entries_seen > max_entries:
                truncated = True
                break
            relative = os.path.relpath(os.path.join(directory, name), root)
            candidate = relative if "/" in pattern else name
            if not fnmatch.fnmatchcase(candidate.casefold(), pattern.casefold()):
                continue
            visited += 1
            if visited > max_files:
                truncated = True
                break
            path = os.path.join(directory, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            if os.path.commonpath((root_real, os.path.realpath(path))) != root_real:
                continue
            if len(relative) > 240:
                continue
            if not query:
                output_chars += len(json.dumps(path, ensure_ascii=False))
                if output_chars > max_output_chars:
                    truncated = True
                    break
                paths.append(path)
                if len(paths) == max_paths:
                    truncated = True
                    break
                continue
            if os.path.splitext(name)[1].lower() not in allowed_suffixes:
                continue
            try:
                with open(path, "rb") as source:
                    line_number = 0
                    while scanned_bytes < max_bytes:
                        raw = source.readline(4096)
                        if not raw:
                            break
                        line_number += 1
                        tail = ""
                        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                        while raw:
                            scanned_bytes += len(raw)
                            if b"\x00" in raw:
                                break
                            text = tail + decoder.decode(raw, final=raw.endswith(b"\n"))
                            hit = expression.search(text)
                            if hit and hit.end() > len(tail):
                                start = max(0, hit.start() - 80)
                                start = max(start, hit.end() - 240)
                                excerpt = text[start:start + 240].strip()
                                match = {"path": path, "line": line_number, "text": excerpt}
                                output_chars += len(json.dumps(match, ensure_ascii=False))
                                if output_chars > max_output_chars:
                                    truncated = True
                                    break
                                matches.append(match)
                                if len(matches) == max_matches:
                                    truncated = True
                                    break
                            if raw.endswith(b"\n") or scanned_bytes >= max_bytes:
                                break
                            tail = text[-240:]
                            raw = source.readline(4096)
                        if truncated or scanned_bytes >= max_bytes:
                            break
            except OSError:
                continue
            if len(matches) == max_matches or scanned_bytes >= max_bytes:
                truncated = True
                break
        if truncated:
            break

print(json.dumps({
    "paths": paths,
    "matches": matches,
    "visited_files": min(visited, max_files),
    "visited_entries": min(entries_seen, max_entries),
    "truncated": truncated,
    "scope_available": os.path.isdir(root),
}, ensure_ascii=False))
"""
