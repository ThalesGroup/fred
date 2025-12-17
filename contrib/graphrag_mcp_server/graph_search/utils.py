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

from pydantic import BaseModel
import re
from typing import List

class GraphSearchRequest(BaseModel):
    query: str
    top_k: int | None = 10
    center_uid: str = ""

def semantic_chunking(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
    """
    Splits a Markdown/text document into semantic chunks by headers and size,
    removes tables entirely.

    Args:
        text (str): full text of the document
        chunk_size (int): max characters per chunk
        chunk_overlap (int): overlap between chunks

    Returns:
        List[str]: list of text chunks
    """
    # 1. Remove Markdown tables
    text_no_tables = re.sub(r"\|.+?\|\n(?:\|[- :]+)+\n(?:\|.*\|(?:\n|$))*", "", text, flags=re.MULTILINE)

    # 2. Split by headers (keep header with content)
    header_pattern = r"(#{1,6}\s.*)"
    parts = re.split(header_pattern, text_no_tables)

    chunks = []
    buffer = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # If it's a header, maybe flush the buffer
        if part.startswith("#"):
            if buffer:
                # split buffer into smaller chunks if too long
                while len(buffer) > chunk_size:
                    chunks.append(buffer[:chunk_size])
                    buffer = buffer[chunk_size - chunk_overlap :]
                if buffer:
                    chunks.append(buffer)
                buffer = ""
            buffer += part + "\n"
        else:
            buffer += part + "\n"

    # Flush remaining buffer
    while buffer:
        if len(buffer) <= chunk_size:
            chunks.append(buffer)
            break
        else:
            chunks.append(buffer[:chunk_size])
            buffer = buffer[chunk_size - chunk_overlap :]

    # Strip whitespace from each chunk
    return [c.strip() for c in chunks if c.strip()]
