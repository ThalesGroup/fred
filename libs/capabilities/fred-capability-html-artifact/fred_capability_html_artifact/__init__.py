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

"""Fred agent capability: agent-generated static HTML/CSS with a sandboxed preview."""

from fred_capability_html_artifact.capability import (
    HTML_ARTIFACT_CAPABILITY_ID,
    HtmlArtifactCapability,
    HtmlArtifactPart,
)

__all__ = [
    "HTML_ARTIFACT_CAPABILITY_ID",
    "HtmlArtifactCapability",
    "HtmlArtifactPart",
]
