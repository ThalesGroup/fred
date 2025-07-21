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
from typing import List, Optional


class FileToProcess(BaseModel):
    source_tag: str
    document_uid: Optional[str] = None
    external_path: Optional[str] = None
    tags: List[str] = []

    def is_push(self) -> bool:
        return self.document_uid is not None

    def is_pull(self) -> bool:
        return self.external_path is not None


class PipelineDefinition(BaseModel):
    name: str
    files: List[FileToProcess]

class ProcessDocumentsRequest(BaseModel):
    files: List[FileToProcess]
    pipeline_name: Optional[str] = "manual_ui_trigger"
