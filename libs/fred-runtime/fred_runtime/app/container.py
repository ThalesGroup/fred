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

"""Pod container factory — single composition-root entry point."""

from __future__ import annotations

from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.context import PodApplicationContext

PodContainer = PodApplicationContext


def build_pod_container(configuration: AgentPodConfig) -> PodContainer:
    """Create a fresh PodApplicationContext with no side effects."""
    return PodApplicationContext(configuration)
