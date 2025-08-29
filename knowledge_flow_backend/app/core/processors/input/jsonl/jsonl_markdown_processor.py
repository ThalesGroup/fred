# processors/jsonl_markdown_processor.py
# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Optional, Any, Iterable
import json
import datetime
import re

from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor


def _safe_read_lines(p: Path) -> Iterable[str]:
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip("\r\n")
            if not line:
                continue
            yield line


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _slug(s: str, maxlen: int = 96) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-._]+", "", s)
    return (s or "doc")[:maxlen]


def _pick_markdown(obj: Dict[str, Any]) -> str | None:
    # Prefer fields commonly produced by crawlers
    return obj.get("markdown") or obj.get("content_markdown") or obj.get("content") or obj.get("text")


def _pick_url(obj: Dict[str, Any]) -> str | None:
    return obj.get("url") or obj.get("page_url") or obj.get("source_url")


def _pick_title(obj: Dict[str, Any]) -> str | None:
    return obj.get("title") or obj.get("section_title")


logger = logging.getLogger(__name__)


class JsonlMarkdownProcessor(BaseMarkdownProcessor):
    """
    Convert a JSONL file (one JSON object per line) into a single Markdown document:
      - Adds YAML front-matter for provenance
      - Each record becomes a section (##) with a small source line
      - Expects a 'markdown' field (falls back to 'content'/'text' if needed)
    """

    def check_file_validity(self, file_path: Path) -> bool:
        return file_path.exists() and file_path.is_file() and file_path.suffix.lower() == ".jsonl"

    def extract_file_metadata(self, file_path: Path) -> Dict:
        # Light metadata + record count (best-effort)
        count = 0
        try:
            for _ in _safe_read_lines(file_path):
                count += 1
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            pass
        return {
            "document_name": file_path.name,
            "size_bytes": file_path.stat().st_size if file_path.exists() else None,
            "suffix": file_path.suffix.lower(),
            "record_count": count,
        }

    def convert_file_to_markdown(
        self,
        file_path: Path,
        output_dir: Path,
        document_uid: Optional[str] = None,
    ) -> Dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_name = "output.md"
        out_path = output_dir / out_name

        sections: list[str] = []
        total = 0
        used = 0

        for line in _safe_read_lines(file_path):
            total += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines, add a tiny diagnostic section
                sections.append(f"<!-- skipped: invalid JSON line {total} -->\n")
                continue

            md = _pick_markdown(obj)
            if not md:
                # Nothing to index for this record
                sections.append(f"<!-- skipped: no markdown for line {total} -->\n")
                continue

            title = _pick_title(obj) or f"Entry {total}"
            url = _pick_url(obj)
            h = obj.get("h_level")  # if your crawler provides it

            # Normalize line endings & trim trailing whitespace
            md = md.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"

            # Build one section
            # Use ## (or deeper if provided) but never shallower than ## (h2) to keep a consistent structure
            level = 2 if not isinstance(h, int) or h < 2 else min(int(h), 6)
            heading = "#" * level

            meta_line = f"<small>Source: {url}</small>\n\n" if url else ""

            sections.append(f"{heading} {title}\n\n{meta_line}{md}\n")
            used += 1

        fm_title = document_uid or file_path.stem
        fm = [
            "---",
            f"title: {fm_title}",
            "source: jsonl-crawler",
            f"created_at: {_now_iso()}",
            f"records_total: {total}",
            f"records_used: {used}",
            f"origin_file: {file_path.name}",
            "---",
            "",
        ]

        out_text = "\n".join(fm) + "\n".join(sections)
        out_path.write_text(out_text, encoding="utf-8")

        return {
            "doc_dir": str(output_dir),
            "md_file": str(out_path),
        }
