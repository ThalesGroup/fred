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

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


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

    @field_validator("saved_at", mode="before")
    @classmethod
    def _parse_saved_at(cls, v):
        """
        Accept both extended ISO-8601 (e.g. 2025-11-12T07:16:06Z)
        and compact basic format (e.g. 20251112T071606Z) historically written.
        """
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            s = v.strip()
            # First, try compact basic UTC format
            if s.endswith("Z"):
                try:
                    return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                except ValueError:
                    # Not the basic format; fall through
                    pass
            # Try extended ISO-8601; replace trailing Z with +00:00 for fromisoformat
            try:
                iso = s[:-1] + "+00:00" if s.endswith("Z") else s
                return datetime.fromisoformat(iso)
            except Exception:
                # Let pydantic raise a proper error afterwards
                return v
        return v


class SavedRunSummary(BaseModel):
    """Lightweight summary for listing runs in the UI."""

    id: str
    input_filename: str
    file_type: str
    processors_count: int
    size: Optional[int] = None
    modified: Optional[datetime] = None
