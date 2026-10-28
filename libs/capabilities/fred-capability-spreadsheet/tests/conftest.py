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

"""Register the capability once, as pod boot does: its chat part joins the
runtime UiPart union, so tool results can carry it in any test module."""

from __future__ import annotations

from fred_capability_spreadsheet.capability import SpreadsheetCapability
from fred_runtime.capabilities.registry import CapabilityRegistry


def pytest_configure(config) -> None:
    del config
    registry = CapabilityRegistry()
    registry.register(SpreadsheetCapability())
    registry.validate()
