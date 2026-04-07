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

from __future__ import annotations

from typing import Iterable

import sqlparse
from sqlparse import sql
from sqlparse import tokens as T

_FORBIDDEN_KEYWORDS = {
    "ALTER",
    "ANALYZE",
    "ATTACH",
    "BEGIN",
    "CALL",
    "COMMIT",
    "COPY",
    "CREATE",
    "DELETE",
    "DETACH",
    "DO",
    "DROP",
    "EXEC",
    "EXECUTE",
    "EXPORT",
    "IMPORT",
    "INSERT",
    "LOAD",
    "MERGE",
    "PRAGMA",
    "REINDEX",
    "RELEASE",
    "RENAME",
    "REPLACE",
    "ROLLBACK",
    "SAVEPOINT",
    "SET",
    "TRUNCATE",
    "UPDATE",
    "USE",
    "VACUUM",
}

_FROM_OR_JOIN_KEYWORDS = {
    "FROM",
    "JOIN",
    "INNER JOIN",
    "LEFT JOIN",
    "LEFT OUTER JOIN",
    "RIGHT JOIN",
    "RIGHT OUTER JOIN",
    "FULL JOIN",
    "FULL OUTER JOIN",
    "CROSS JOIN",
}

_CLAUSE_END_KEYWORDS = {
    "WHERE",
    "GROUP",
    "ORDER",
    "HAVING",
    "LIMIT",
    "UNION",
    "EXCEPT",
    "INTERSECT",
    "QUALIFY",
    "WINDOW",
    "SAMPLE",
    "USING",
    "ON",
}


def validate_read_query(query: str, *, allowed_relations: Iterable[str] | None = None) -> str:
    """
    Validate one read-only SQL query before execution.

    Why this exists:
    - The dataset-centric runtime accepts user/LLM SQL, so it must reject
      writes, multi-statements, and unexpected relation references early.

    How to use:
    - Call this before mounting the query in DuckDB.
    - Pass `allowed_relations` to ensure the query only references aliases that
      the current session is allowed to expose.

    Example:
    ```python
    sql_text = validate_read_query(
        "SELECT city FROM d_doc_sales LIMIT 10",
        allowed_relations={"d_doc_sales"},
    )
    ```
    """

    normalized = query.strip().rstrip(";").strip()
    if not normalized:
        raise ValueError("Empty SQL string provided")

    statements = [statement for statement in sqlparse.parse(normalized) if str(statement).strip()]
    if len(statements) != 1:
        raise ValueError("Exactly one SQL statement is allowed")

    statement = statements[0]
    first_keyword = _first_keyword(statement)
    if first_keyword not in {"SELECT", "WITH"}:
        raise ValueError("Only SELECT or WITH statements are allowed in read-only mode")

    for token in statement.flatten():
        if token.ttype in T.Comment:
            continue
        token_value = token.normalized.upper()
        if token_value in _FORBIDDEN_KEYWORDS:
            raise ValueError(f"Forbidden SQL keyword in read-only mode: {token_value}")

    if allowed_relations is not None:
        allowed_names = {_normalize_identifier(name) for name in allowed_relations}
        cte_names = collect_cte_names(statement)
        referenced_relations = collect_relation_names(statement)
        disallowed_relations = sorted(relation_name for relation_name in referenced_relations if relation_name not in allowed_names and relation_name not in cte_names)
        if disallowed_relations:
            raise ValueError(f"Query references unauthorized datasets: {', '.join(disallowed_relations)}")

    return normalized


def collect_cte_names(statement: sql.Statement | sql.TokenList) -> set[str]:
    """
    Collect common-table-expression names declared in one SQL statement.

    Why this exists:
    - Read-only validation must allow references to local CTE names while still
      blocking unknown dataset aliases.

    How to use:
    - Call this on the parsed statement before checking relation references.
    """

    names: set[str] = set()
    saw_with = False

    for token in statement.tokens:
        if token.is_whitespace or token.ttype in T.Comment:
            continue
        if not saw_with:
            if token.normalized.upper() == "WITH" or token.ttype is T.Keyword.CTE:
                saw_with = True
            else:
                break
            continue

        if token.normalized.upper() == "RECURSIVE":
            continue

        if token.ttype in T.Keyword.DML and token.normalized.upper() == "SELECT":
            break

        if isinstance(token, sql.IdentifierList):
            for identifier in token.get_identifiers():
                name = identifier.get_name() or identifier.get_real_name()
                if name:
                    names.add(_normalize_identifier(name))
            continue

        if isinstance(token, sql.Identifier):
            name = token.get_name() or token.get_real_name()
            if name:
                names.add(_normalize_identifier(name))

    return names


def collect_relation_names(statement: sql.Statement | sql.TokenList) -> set[str]:
    """
    Collect relation names referenced after `FROM` and `JOIN` clauses.

    Why this exists:
    - Authorization is enforced by the aliases mounted in DuckDB.
    - We still want a cheap allowlist check before execution to reject clearly
      out-of-scope relation names.

    How to use:
    - Pass the parsed statement returned by `sqlparse.parse(...)`.
    """

    names: set[str] = set()
    tokens = list(statement.tokens)

    index = 0
    while index < len(tokens):
        token = tokens[index]

        if _is_relation_keyword(token):
            index = _collect_relation_names_after_keyword(tokens, index + 1, names)
            continue

        if isinstance(token, sql.TokenList):
            names.update(collect_relation_names(token))

        index += 1

    return names


def quote_identifier(identifier: str) -> str:
    """
    Quote one SQL identifier for DuckDB statements.

    Why this exists:
    - Dataset aliases are generated by Fred, but quoting keeps the view creation
      statements safe and readable.

    How to use:
    - Wrap temp view names before interpolating them in SQL.

    Example:
    ```python
    sql_name = quote_identifier("d_doc_sales")
    ```
    """

    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def quote_string_literal(value: str) -> str:
    """
    Quote one SQL string literal for DuckDB statements.

    Why this exists:
    - Object-store paths and presigned URLs are runtime values that need safe
      embedding inside `read_parquet(...)` calls.

    How to use:
    - Wrap file paths or URLs before interpolating them in SQL.
    """

    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _first_keyword(statement: sql.Statement | sql.TokenList) -> str | None:
    for token in statement.tokens:
        if token.is_whitespace or token.ttype in T.Comment:
            continue
        if token.ttype in T.Keyword or token.ttype in T.Keyword.DML or token.ttype is T.Keyword.CTE:
            return token.normalized.upper()
        if isinstance(token, sql.TokenList):
            return _first_keyword(token)
        return token.normalized.upper()
    return None


def _is_relation_keyword(token: sql.Token) -> bool:
    return token.ttype in T.Keyword and token.normalized.upper() in _FROM_OR_JOIN_KEYWORDS


def _collect_relation_names_after_keyword(tokens: list[sql.Token], start_index: int, names: set[str]) -> int:
    index = start_index

    while index < len(tokens):
        token = tokens[index]

        if token.is_whitespace or token.ttype in T.Comment:
            index += 1
            continue

        if token.ttype in T.Keyword and token.normalized.upper() in _CLAUSE_END_KEYWORDS:
            return index

        if token.ttype in T.Punctuation and token.value == ",":
            index += 1
            continue

        names.update(_relation_names_from_token(token))
        return index + 1

    return index


def _relation_names_from_token(token: sql.Token) -> set[str]:
    if isinstance(token, sql.IdentifierList):
        identifier_names: set[str] = set()
        for identifier in token.get_identifiers():
            identifier_names.update(_relation_names_from_token(identifier))
        return identifier_names

    if isinstance(token, sql.Identifier):
        if any(isinstance(child, sql.Parenthesis) and _token_contains_select(child) for child in token.tokens):
            subquery_names: set[str] = set()
            for child in token.tokens:
                if isinstance(child, sql.Parenthesis):
                    subquery_names.update(collect_relation_names(child))
            return subquery_names

        real_name = token.get_real_name() or token.get_name()
        return {_normalize_identifier(real_name)} if real_name else set()

    if isinstance(token, sql.Parenthesis):
        return collect_relation_names(token)

    if token.ttype in T.Name:
        return {_normalize_identifier(token.value)}

    return set()


def _token_contains_select(token: sql.TokenList) -> bool:
    for child in token.tokens:
        if child.ttype in T.Keyword.DML and child.normalized.upper() == "SELECT":
            return True
        if isinstance(child, sql.TokenList) and _token_contains_select(child):
            return True
    return False


def _normalize_identifier(value: str) -> str:
    return value.strip().strip('"').strip("`").strip("[").strip("]").lower()
