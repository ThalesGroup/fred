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

from typing import List, Optional

from pydantic import BaseModel, Field


class RagSettings(BaseModel):
    knowledge_flow_url: str = Field(default="http://localhost:8111/knowledge-flow/v1")
    top_k: int = 3
    timeout_s: int = 10
    snippet_chars: int = 500
    include_tags_from_runtime_context: bool = True
    default_libraries: Optional[List[str]] = None  # fallback tags if runtime has none
