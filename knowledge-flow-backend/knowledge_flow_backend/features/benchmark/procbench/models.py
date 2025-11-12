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

from typing import List, Literal, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class ProcessorDescriptor(BaseModel):
    id: str
    name: str
    kind: Literal["standard", "lite"]
    file_types: List[str] = Field(default_factory=list)


class ProcessorRunMetrics(BaseModel):
    chars: int
    words: int
    headings: int
    h1: int
    h2: int
    h3: int
    images: int
    links: int
    code_blocks: int
    table_like_lines: int
    tokens_est: int


class ProcessorRunResult(BaseModel):
    processor_id: str
    display_name: str
    kind: Literal["standard", "lite"]
    status: Literal["ok", "error"]
    duration_ms: int
    markdown: Optional[str] = None
    metrics: Optional[ProcessorRunMetrics] = None
    page_count: Optional[int] = None
    error_message: Optional[str] = None


class BenchmarkResponse(BaseModel):
    input_filename: str
    file_type: str
    results: List[ProcessorRunResult]


class SavedRun(BaseModel):
    """Full persisted benchmark run payload."""

    saved_at: datetime
    user_id: str
    input_filename: str
    file_type: str
    results: List[ProcessorRunResult]


class SavedRunSummary(BaseModel):
    """Lightweight summary for listing runs in the UI."""

    id: str
    input_filename: str
    file_type: str
    processors_count: int
    size: Optional[int] = None
    modified: Optional[datetime] = None
