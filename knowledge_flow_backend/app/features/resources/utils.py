# app/common/yaml_front_matter.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple, Dict
import re
from uuid import uuid4

import yaml

from app.features.resources.structures import Resource, ResourceCreate

_DASH_LINE_RE = re.compile(r"^\s*---\s*$")


def build_resource_from_create(payload: ResourceCreate, library_tag_id: str, user: str) -> Resource:
    """
    Validates YAML header/body and returns a fully-populated Resource ready to persist.
    - Requires 'version' in header
    - If header.kind is present, it must match payload.kind
    - requires 'schema' in header
    - Body must be non-empty (after the '---')
    - payload.{name,description,labels} override header {name,description,tags} when provided
    """
    header, body = parse_front_matter(payload.content)

    # 1) required keys
    version = header.get("version")
    if not version:
        raise ValueError("Missing 'version' in resource header")

    yaml_kind = header.get("kind")
    if yaml_kind and yaml_kind != payload.kind.value:
        raise ValueError(f"YAML kind '{yaml_kind}' does not match payload.kind '{payload.kind.value}'")

    schema = header.get("schema")
    if not schema:
        schema = {} 
    elif not isinstance(schema, dict):
        raise ValueError("Missing or invalid 'schema' in header.")

    # 3) body must exist
    if not body or not body.strip():
        raise ValueError("Resource body must not be empty")

    # 4) derive metadata (payload overrides header)
    name = payload.name or header.get("name")
    description = payload.description or header.get("description")

    # header.tags can be a list or a string; normalize to list[str]
    header_tags = header.get("tags") or []
    if isinstance(header_tags, str):
        header_tags = [header_tags]
    elif not isinstance(header_tags, list):
        header_tags = []

    labels = payload.labels if payload.labels is not None else header_tags

    # 5) assemble Resource
    now = datetime.now(timezone.utc)
    return Resource(
        id=str(uuid4()),
        kind=payload.kind,
        version=str(version),
        name=name,
        description=description,
        labels=labels,
        author=user,
        created_at=now,
        updated_at=now,
        content=payload.content,
        # TEMP: membership on resource; swap to join-table later
        library_tags=[library_tag_id],
    )


def parse_front_matter(content: str) -> Tuple[Dict, str]:
    """
    Split a resource file into YAML header (dict) and body (str).

    Supported forms:
    1) Header first, then a single line '---' separator, then body
       id: ...
       version: v1
       kind: template
       ---
       <body>

    2) Classic front-matter with opening and closing '---'
       ---
       id: ...
       version: v1
       kind: template
       ---
       <body>
    """
    if content is None:
        raise ValueError("Empty content")

    # normalize newlines, strip BOM if present
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    lines = text.split("\n")
    n = len(lines)

    # Case A: starts with '---' (classic)
    if n > 0 and _DASH_LINE_RE.match(lines[0]):
        # find closing '---'
        try:
            end_idx = next(i for i in range(1, n) if _DASH_LINE_RE.match(lines[i]))
        except StopIteration:
            raise ValueError("Unclosed front-matter: expected closing '---' line")

        header_text = "\n".join(lines[1:end_idx]).strip()
        body = "\n".join(lines[end_idx + 1 :])
    else:
        # Case B: header first, then a single '---'
        try:
            sep_idx = next(i for i in range(0, n) if _DASH_LINE_RE.match(lines[i]))
        except StopIteration:
            raise ValueError("Missing '---' separator between header and body")

        header_text = "\n".join(lines[:sep_idx]).strip()
        body = "\n".join(lines[sep_idx + 1 :])

    if not header_text:
        raise ValueError("Empty YAML header before '---'")

    try:
        header = yaml.safe_load(header_text)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML header: {e}") from e

    if not isinstance(header, dict):
        raise ValueError("YAML header must be a mapping (key: value)")

    return header, body
