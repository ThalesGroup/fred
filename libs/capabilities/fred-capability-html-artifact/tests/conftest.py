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

"""Register the capability so `HtmlArtifactPart` is a valid `UiPart`.

The union is rebuilt at pod boot by the registry. A test emitting the part needs
the same step, and it has to happen before any test module runs: the union is
process-global, so without this the suite only passed when a module that happens
to build a registry sorted ahead of the ones that emit a part.
"""

from __future__ import annotations

import pytest
from fred_capability_html_artifact.capability import HtmlArtifactCapability
from fred_runtime.capabilities.registry import CapabilityRegistry


@pytest.fixture(scope="session", autouse=True)
def _register_html_artifact_chat_part() -> None:
    registry = CapabilityRegistry()
    registry.register(HtmlArtifactCapability())
    registry.validate()
