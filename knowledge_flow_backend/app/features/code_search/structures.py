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

# app/features/code_search/structures.py
from pydantic import BaseModel
from typing import Optional

from app.common.structures import Status


class CodeSearchRequest(BaseModel):
    query: str
    top_k: int = 10


class CodeDocumentSource(BaseModel):
    content: str
    file_path: str
    file_name: str
    language: str
    symbol: Optional[str] = None  # e.g., method or class name
    uid: str
    score: float
    rank: Optional[int] = None
    embedding_model: Optional[str] = None
    vector_index: Optional[str] = None


class CodeIndexRequest(BaseModel):
    path: str


class CodeIndexProgress(BaseModel):
    step: str
    status: Status
    message: Optional[str] = None
    error: Optional[str] = None
