# Copyright Thales 2025
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

from dataclasses import dataclass, field
import re

import sqlparse
from sqlparse.sql import Function, Identifier, IdentifierList, Parenthesis, Statement, TokenList
from sqlparse.tokens import DML, Keyword, Literal, Name, Newline, Punctuation, Whitespace

_READ_KEYWORDS = {"FROM", "JOIN"}
_WRITE_KEYWORDS = {"UPDATE", "INTO"}
_NOISE_TOKENS = {Whitespace, Newline, Punctuation}


@dataclass
class QueryTableReferences:
    all_tables: set[str] = field(default_factory=set)
    write_targets: set[str] = field(default_factory=set)
    read_sources: set[str] = field(default_factory=set)
    qualified_tables: set[str] = field(default_factory=set)


def _strip_quotes(name: str) -> str:
    return str(name).strip('"`[]')


def _is_noise(token) -> bool:
    return token.is_whitespace or token.ttype in _NOISE_TOKENS


def _collect_cte_names(token_list: TokenList) -> set[str]:
    cte_names: set[str] = set()
    with_seen = False

    for token in token_list.tokens:
        if not with_seen:
            if token.ttype in Keyword and token.value.upper().startswith("WITH"):
                with_seen = True
            continue

        if _is_noise(token):
            continue

        if token.ttype in Keyword and token.value.upper() == "RECURSIVE":
            continue

        if isinstance(token, IdentifierList):
            for identifier in token.get_identifiers():
                name = identifier.get_name()
                if name:
                    cte_names.add(_strip_quotes(name))
            break

        if isinstance(token, Identifier):
            name = token.get_name()
            if name:
                cte_names.add(_strip_quotes(name))
            break

        if token.ttype is DML:
            break

    return cte_names


def _extract_identifier_names(token) -> list[tuple[str, bool]]:
    if isinstance(token, IdentifierList):
        out: list[tuple[str, bool]] = []
        for identifier in token.get_identifiers():
            out.extend(_extract_identifier_names(identifier))
        return out

    if isinstance(token, Function):
        name = token.get_real_name() or token.get_name()
        if not name:
            return []
        return [(_strip_quotes(name), token.get_parent_name() is not None)]

    if isinstance(token, Identifier):
        name = token.get_real_name() or token.get_name()
        if not name:
            return []
        return [(_strip_quotes(name), token.get_parent_name() is not None)]

    if token.ttype is Name:
        return [(_strip_quotes(token.value), False)]

    return []


def _replace_identifier_value(value: str, current: str, replacement: str) -> str:
    escaped = re.escape(current)
    pattern = rf'^\s*(?:"{escaped}"|`{escaped}`|\[{escaped}\]|{escaped})(?P<rest>.*)$'
    return re.sub(pattern, rf'"{replacement}"\g<rest>', value, count=1)


def _rewrite_leaf_name(token_list: TokenList, replacement: str) -> bool:
    for token in token_list.tokens:
        if token.ttype in Name or token.ttype in Literal.String.Symbol:
            token.value = f'"{replacement}"'
            return True
        if isinstance(token, TokenList) and _rewrite_leaf_name(token, replacement):
            return True
    return False


def _rewrite_identifier(identifier: Identifier | Function, mapping: dict[str, str], cte_names: set[str]) -> None:
    current = identifier.get_real_name() or identifier.get_name()
    if not current:
        return
    current = _strip_quotes(current)
    if current in cte_names or current not in mapping or identifier.get_parent_name() is not None:
        return
    if not _rewrite_leaf_name(identifier, mapping[current]):
        identifier.value = _replace_identifier_value(identifier.value, current, mapping[current])


def _rewrite_table_reference_token(token, mapping: dict[str, str], cte_names: set[str]) -> None:
    if isinstance(token, IdentifierList):
        for identifier in token.get_identifiers():
            _rewrite_identifier(identifier, mapping, cte_names)
        return

    if isinstance(token, Function):
        _rewrite_identifier(token, mapping, cte_names)
        return

    if isinstance(token, Identifier):
        _rewrite_identifier(token, mapping, cte_names)
        return

    if token.ttype in Name or token.ttype in Literal.String.Symbol:
        current = _strip_quotes(token.value)
        if current not in cte_names and current in mapping:
            token.value = f'"{mapping[current]}"'


def _scan_token_list(token_list: TokenList, refs: QueryTableReferences, cte_names: set[str]) -> None:
    expecting_mode: str | None = None
    delete_waiting_for_from = False

    for token in token_list.tokens:
        if expecting_mode:
            if _is_noise(token):
                continue

            extracted = _extract_identifier_names(token)
            if extracted:
                for name, qualified in extracted:
                    if name in cte_names:
                        continue
                    refs.all_tables.add(name)
                    if qualified:
                        refs.qualified_tables.add(name)
                    if expecting_mode == "write":
                        refs.write_targets.add(name)
                    else:
                        refs.read_sources.add(name)
                expecting_mode = None
                continue

            expecting_mode = None

        if token.ttype is DML:
            upper = token.value.upper()
            if upper == "UPDATE":
                expecting_mode = "write"
                delete_waiting_for_from = False
                continue
            if upper == "DELETE":
                delete_waiting_for_from = True
                continue

        if token.ttype is Keyword:
            upper = token.value.upper()
            if upper in _READ_KEYWORDS:
                expecting_mode = "write" if delete_waiting_for_from and upper == "FROM" else "read"
                delete_waiting_for_from = False
                continue
            if upper in _WRITE_KEYWORDS:
                expecting_mode = "write"
                delete_waiting_for_from = False
                continue

        if isinstance(token, TokenList):
            nested_ctes = cte_names
            if isinstance(token, (Statement, Parenthesis)):
                nested_ctes = cte_names | _collect_cte_names(token)
            _scan_token_list(token, refs, nested_ctes)


def extract_query_table_references(sql: str) -> QueryTableReferences:
    refs = QueryTableReferences()
    for statement in sqlparse.parse(sql):
        cte_names = _collect_cte_names(statement)
        _scan_token_list(statement, refs, cte_names)
    return refs


def _rewrite_token_list(token_list: TokenList, mapping: dict[str, str], cte_names: set[str]) -> None:
    expecting_table = False
    delete_waiting_for_from = False

    for token in token_list.tokens:
        if expecting_table:
            if _is_noise(token):
                continue

            _rewrite_table_reference_token(token, mapping, cte_names)
            expecting_table = False
            continue

        if token.ttype is DML:
            upper = token.value.upper()
            if upper == "UPDATE":
                expecting_table = True
                delete_waiting_for_from = False
                continue
            if upper == "DELETE":
                delete_waiting_for_from = True
                continue

        if token.ttype is Keyword and token.value.upper() in (_READ_KEYWORDS | _WRITE_KEYWORDS):
            expecting_table = token.value.upper() in _WRITE_KEYWORDS or (delete_waiting_for_from and token.value.upper() == "FROM") or token.value.upper() in _READ_KEYWORDS
            delete_waiting_for_from = False
            continue

        if isinstance(token, TokenList):
            nested_ctes = cte_names
            if isinstance(token, (Statement, Parenthesis)):
                nested_ctes = cte_names | _collect_cte_names(token)
            _rewrite_token_list(token, mapping, nested_ctes)


def rewrite_query_table_names(sql: str, mapping: dict[str, str]) -> str:
    statements = sqlparse.parse(sql)
    for statement in statements:
        cte_names = _collect_cte_names(statement)
        _rewrite_token_list(statement, mapping, cte_names)
    return "".join(str(statement) for statement in statements)
