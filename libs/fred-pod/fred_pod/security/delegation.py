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


"""The `security.delegation` configuration block.

Lives beside the rest of the pod's configuration models so a pod can read and
validate its own security block; admitting a grant at runtime stays in the
agents platform."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# The three values are identifiers, not free text: bounded so an unverified
# caller cannot push arbitrary payloads into an audit line.
GrantIdentifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)
]


class CallerPolicy(BaseModel):
    """One receiver-owned workload identity trusted to delegate."""

    model_config = ConfigDict(extra="forbid")

    client_id: GrantIdentifier
    subject: GrantIdentifier


class DelegationConfig(BaseModel):
    """`security.delegation` block. Off by default; enabling requires an allow-list."""

    enabled: bool = False
    allowed_callers: list[str] = Field(
        default_factory=list,
        description="Client ids of the workloads allowed to speak for a person.",
    )
    caller_policies: list[CallerPolicy] = Field(default_factory=list)

    @model_validator(mode="after")
    def _allow_list_required_when_enabled(self) -> DelegationConfig:
        # Fail closed at configuration time: with no allow-list nothing could ever
        # be believed, so an enabled flag without one is a mistake, not a no-op.
        if (
            self.enabled
            and not any(caller.strip() for caller in self.allowed_callers)
            and not self.caller_policies
        ):
            raise ValueError(
                "security.delegation.allowed_callers must name at least one client id "
                "when security.delegation.enabled is true"
            )
        return self

    def allows(self, client_id: str | None) -> bool:
        """True when `client_id` is a workload this receiver lets speak for a person."""
        if not client_id:
            return False
        return client_id in {
            caller.strip() for caller in self.allowed_callers if caller.strip()
        } or any(policy.client_id == client_id for policy in self.caller_policies)

    def policy_for(self, *, client_id: str, subject: str) -> CallerPolicy | None:
        return next(
            (
                policy
                for policy in self.caller_policies
                if policy.client_id == client_id and policy.subject == subject
            ),
            None,
        )
