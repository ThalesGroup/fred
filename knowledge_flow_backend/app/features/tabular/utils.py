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

from typing import Optional
import re
import logging

logger = logging.getLogger(__name__)

import re
from typing import Optional


def extract_safe_sql_query(text: str) -> Optional[str]:
    """
    Extract a safe SQL query (SELECT/WITH only) from the given text.
    Rejects attempts to modify the database.
    """

    # 1. Detect and reject forbidden (modifying) SQL statements
    forbidden_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
    for keyword in forbidden_keywords:
        if re.search(rf"(?i)\b{keyword}\b", text):
            raise PermissionError("❌ Non, tu n'as pas les droits de modifier la base.")

    # 2. Try to extract a query inside a ```sql code block
    sql_block = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if sql_block:
        query = sql_block.group(1).strip()
        if query.upper().startswith(("SELECT", "WITH")):
            return query
        raise PermissionError("❌ Non, tu n'as pas les droits de modifier la base.")

    # 3. Fallback: scan for SELECT/WITH queries inline
    read_keywords = ["SELECT", "WITH"]
    for keyword in read_keywords:
        match = re.search(rf"(?i)\b{keyword}\b.*", text, re.DOTALL)
        if match:
            return match.group(0).strip()

    return None


def column_name_corrector(col: str) -> str:
    if any(c in col for c in ' ()'):
        return f'"{col}"'
    return col
