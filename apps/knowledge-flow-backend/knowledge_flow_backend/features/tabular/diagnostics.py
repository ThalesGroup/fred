"""Metadata-only tabular resolution and scoped SQL diagnostics."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from fred_core.logs.context import safe_context

DescriptionFailureReason = Literal["datasets_not_resolved", "preview_not_ready", "preview_artifact_unavailable"]
DiscoveryEmptyReason = Literal["no_readable_documents", "empty_authorized_scope", "no_documents_in_scope", "no_registered_tables"]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VisibleQueryRelation:
    """A base table and its SQL qualifier, only in a proven flat SELECT scope."""

    relation: str
    qualifier: str


def visible_query_relations(statement: dict[str, Any]) -> tuple[VisibleQueryRelation, ...]:
    """Project a safe diagnostic scope from the AST validation already parsed.

    Call after validation, never as authorization. Derived queries, renaming and
    hidden join sides deliberately yield no candidates instead of guessing what
    the binder can see. This only examines the parser's opaque AST, with no I/O.
    """

    # opaque: DuckDB owns the JSON AST; only known node fields are projected.
    pending: list[object] = [statement]
    select_count = 0
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            if node.get("type") == "SELECT_NODE":
                select_count += 1
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    if statement.get("type") != "SELECT_NODE" or select_count != 1:
        return ()

    sources = [statement.get("from_table")]
    relations: list[VisibleQueryRelation] = []
    join_count = 0
    while sources:
        source = sources.pop()
        if not isinstance(source, dict):
            return ()
        if source.get("type") == "JOIN":
            join_count += 1
            # Earlier ON clauses cannot see a later join's columns. Without a
            # proven error position, keep the original for multi-join scopes.
            if join_count > 1 or source.get("alias") or source.get("join_type") not in {"INNER", "LEFT", "RIGHT", "OUTER"}:
                return ()
            sources.extend([source.get("right"), source.get("left")])
            continue
        if source.get("type") != "BASE_TABLE" or source.get("column_name_alias"):
            return ()
        name, alias = source.get("table_name"), source.get("alias")
        if not isinstance(name, str) or not isinstance(alias, str) or source.get("schema_name") or source.get("catalog_name"):
            return ()
        relations.append(VisibleQueryRelation(relation=name, qualifier=alias or name))

    # Duplicate qualifiers are themselves a binding error, not a reliable scope.
    if len({item.qualifier.lower() for item in relations}) != len(relations):
        return ()
    return tuple(relations)


_MISSING_QUALIFIED = re.compile(r'^Binder Error: (?:Values list|Table) "([^"]+)" does not have a column named "([^"]+)"$')
_MISSING_UNQUALIFIED = re.compile(r'^Binder Error: Referenced column "([^"]+)" not found in FROM clause!$')
_AMBIGUOUS = re.compile(r'^Binder Error: Ambiguous reference to column name "([^"]+)"(?: .*)?$')
_MAX_DIAGNOSTIC_CHARACTERS = 4096
_MAX_CANDIDATES = 8


def scoped_column_diagnostic(
    message: str,
    *,
    relations: Sequence[VisibleQueryRelation],
    mounted_columns: Mapping[str, Sequence[str]],
) -> str:
    """Explain supported binder failures using only already mounted metadata.

    Pass the redacted error, the validation projection and column names from the
    actual mounted subset. No reads, SQL changes or inferred joins occur here.
    Unsupported/uncertain scopes keep the original bounded diagnostic. Callers
    must preserve existing authority, cancellation and error-classification paths.
    """

    fallback = message[:_MAX_DIAGNOSTIC_CHARACTERS]
    if not relations:
        return fallback
    columns_by_relation = {name.lower(): columns for name, columns in mounted_columns.items()}
    if any(item.relation.lower() not in columns_by_relation for item in relations):
        return fallback

    first_line = message.splitlines()[0] if message else ""
    qualified = _MISSING_QUALIFIED.fullmatch(first_line)
    missing = _MISSING_UNQUALIFIED.fullmatch(first_line)
    ambiguous = _AMBIGUOUS.fullmatch(first_line)
    matched = qualified or missing or ambiguous
    if matched is None:
        return fallback
    qualifier = qualified[1] if qualified else None
    column = matched[2] if qualified else matched[1]
    sources = [item for item in relations if qualifier is None or item.qualifier.lower() == qualifier.lower()]
    if not sources:
        return fallback

    # Bound identifiers as well as list size: metadata names are caller content.
    def quoted(value: str) -> str:
        """Render bounded identifiers as SQL references, never executable SQL."""
        return '"' + value[:120].replace('"', '""').replace("\n", " ").replace("\r", " ") + '"'

    candidates = [f"{quoted(item.qualifier)}.{quoted(name)}" for item in relations for name in columns_by_relation[item.relation.lower()] if name.lower() == column.lower()]
    if ambiguous:
        if len(candidates) < 2:
            return fallback
        detail = f"Column {quoted(column)} is ambiguous. Visible qualified references: {', '.join(candidates[:_MAX_CANDIDATES])}. Choose the intended table explicitly."
    else:
        source_names = ", ".join(f"{quoted(item.relation)} (SQL qualifier {quoted(item.qualifier)})" for item in sources[:_MAX_CANDIDATES])
        detail = f"Column {quoted(column)} does not exist in {source_names}."
        if candidates:
            detail += f" Visible references in the tables already used by this SQL: {', '.join(candidates[:_MAX_CANDIDATES])}."
        else:
            available: list[str] = []
            for item in sources:
                for name in columns_by_relation[item.relation.lower()]:
                    available.append(f"{quoted(item.qualifier)}.{quoted(name)}")
                    if len(available) == _MAX_CANDIDATES:
                        break
                if len(available) == _MAX_CANDIDATES:
                    break
            if available:
                detail += f" Available column examples: {', '.join(available)}."
    return f"{first_line}\n{detail}"[:_MAX_DIAGNOSTIC_CHARACTERS]


class TabularDescriptionNotFound(FileNotFoundError):
    """Preserve the HTTP/message contract with a reason determined at its source."""

    def __init__(self, message: str, *, reason: DescriptionFailureReason) -> None:
        super().__init__(message)
        self.reason = reason


def log_description_failure(error: TabularDescriptionNotFound) -> None:
    logger.warning("tabular.description_failure", extra={"reason": error.reason})


@dataclass
class ResolutionSummary:
    """Only counts observed during existing lookups, never a global inventory."""

    readable_metadata_count: int = 0
    scoped_metadata_count: int = 0
    resolved_table_count: int = 0
    authorized_scope_empty: bool = False
    scope_applied: bool = False

    def log_empty(self) -> None:
        reason: DiscoveryEmptyReason
        if self.authorized_scope_empty:
            reason = "empty_authorized_scope"
        elif self.readable_metadata_count == 0 and not self.scope_applied:
            reason = "no_readable_documents"
        elif self.scoped_metadata_count == 0:
            reason = "no_documents_in_scope"
        else:
            reason = "no_registered_tables"
        fields = safe_context({"reason": reason, **{name: min(max(0, getattr(self, name)), 2**63 - 1) for name in ("readable_metadata_count", "scoped_metadata_count", "resolved_table_count")}})
        logger.info("tabular.discovery_empty", extra=fields)
