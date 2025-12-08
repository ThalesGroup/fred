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

import re

FORBIDDEN_KEYWORDS_READ = [
    # Locking / concurrency
    " for update",
    " for share",
    " lock in share mode",
    " for no key update",
    " for key share",
    # Select… into (creates objects)
    "into temp",
    "into temporary",
    "into outfile",
    "into dumpfile",
    # DML
    " insert ",
    " update ",
    " delete ",
    " merge ",
    " replace ",  # Myquery
    # DDL
    " alter ",
    " drop ",
    " create ",
    " truncate ",
    " rename ",
    # Procedures / execution
    " call ",
    " exec ",
    " execute ",
    " do ",  # Postgres, query Server
    " pragma ",  # queryite
    # System/session modification
    " set ",
    " use ",  # Myquery
    " attach database",
    " detach database",
    # File/IO
    " load_file",
    " load data",
    " copy ",  # Postgres
    # System schemas
    "pg_",
    "queryite_",
    "sys.",
    "information_schema",
    "myquery.",
    # Transactions
    " begin ",
    " commit ",
    " rollback ",
    " savepoint ",
    " release savepoint",
    # Dangerous maintenance ops
    " vacuum ",
    " analyze ",
    " reindex ",
    " optimize ",
]

FORBIDDEN_KEYWORDS_WRITE = [
    # DDL
    "truncate",
    # Procedures / execution
    "call",
    "exec",
    "execute",
    "do",
    "pragma",
    # System/session modification
    "set",
    "use",
    "attach database",
    "detach database",
    # File/IO
    "load_file",
    "load data",
    "copy",
    # System schemas
    "pg_",
    "queryite_",
    "sys.",
    "information_schema",
    "myquery.",
    # Maintenance ops
    "vacuum",
    "analyze",
    "reindex",
    "optimize",
]


def check_read_query(query: str) -> str:
    # 1. Must start with "select" or "with"
    if not (query.startswith("select") or query.startswith("with")):
        raise ValueError("Only SELECT or WITH statements are allowed in read-only mode")

    # 2. No multiple statements
    if ";" in query.rstrip(";"):
        raise ValueError("Multiple query statements are not allowed")

    # 3. Block dangerous keywords
    for keyword in FORBIDDEN_KEYWORDS_READ:
        if re.search(rf"\b{keyword}\b", query, flags=re.IGNORECASE):
            raise ValueError("Forbidden query pattern in read-only mode")

    return query


def check_write_query(query: str) -> str:
    # 1. No multiple statements
    if ";" in query.rstrip(";"):
        raise ValueError("Multiple query statements are not allowed")

    # 2. Block dangerous keywords
    for keyword in FORBIDDEN_KEYWORDS_WRITE:
        if re.search(rf"\b{keyword}\b", query, flags=re.IGNORECASE):
            raise ValueError("Forbidden query pattern in write mode")

    return query
