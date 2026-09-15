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

"""What a KPI event says the caller was.

A service identity filed as `human` makes any split of human against automated
traffic wrong by exactly the machine volume — and a workload that synchronizes a
source on a schedule contributes most of it.
"""

from fred_core.kpi.kpi_writer import to_kpi_actor
from fred_core.security.structure import SERVICE_AGENT_ROLE, KeycloakUser


def _user(*roles: str) -> KeycloakUser:
    return KeycloakUser(
        uid="caller-1", username="caller", roles=list(roles), email=None
    )


def test_a_service_identity_is_a_machine_and_still_says_which_one():
    actor = to_kpi_actor(_user(SERVICE_AGENT_ROLE, "admin"))

    assert actor.type == "system"
    assert actor.user_id == "caller-1"


def test_a_person_is_still_a_person():
    actor = to_kpi_actor(_user("admin"))

    assert actor.type == "human"
    assert actor.user_id == "caller-1"
