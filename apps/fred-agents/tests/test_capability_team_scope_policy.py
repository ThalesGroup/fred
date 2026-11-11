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

"""Installing a business contribution does not authorize its central connection."""

from fred_capability_mcp import TabularCapability
from fred_sdk.contracts.models import TeamScopePolicy


def test_tabular_does_not_declare_implicit_authorization():
    assert TabularCapability.manifest.team_scope is TeamScopePolicy.ADMIN_GATED
