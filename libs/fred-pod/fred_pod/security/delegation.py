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

# Keycloak convention: a client named after the audience holds the caller role,
# so granting the role also puts the audience into the holder's tokens.
DEFAULT_DELEGATION_AUDIENCE = "fred-delegation"
DEFAULT_CALLER_ROLE = "delegation_caller"


class DelegationConfig(BaseModel):
    """`security.delegation` block. Off by default, one switch per direction.

    A workload may speak for a person when its verified token is addressed to
    `audience` and lists `caller_role` in the claim `caller_roles_claim` names.
    """

    model_config = ConfigDict(extra="forbid")

    act_for_people: bool = Field(
        default=False,
        description=(
            "Outgoing, read where agents run: their calls during a person's run "
            "present this backend's workload token and name the person, run and "
            "agent. Other backends make no such calls; leave it off there."
        ),
    )
    accept_delegated_calls: bool = Field(
        default=False,
        description=(
            "Incoming: believe the person a calling workload names when that "
            "workload's token carries caller_role."
        ),
    )
    audience: GrantIdentifier = DEFAULT_DELEGATION_AUDIENCE
    caller_role: GrantIdentifier = DEFAULT_CALLER_ROLE
    caller_roles_claim: list[GrantIdentifier] | None = Field(
        default=None,
        min_length=1,
        description=(
            "Path to the list of roles in a verified token, one entry per nested "
            "claim name. Defaults to resource_access.<audience>.roles, where "
            "Keycloak puts the roles of the audience client."
        ),
    )
    service_accounts_only: bool = Field(
        default=False,
        description=(
            "Trust only a token Keycloak issued to a client's own service account: "
            "its preferred_username is service-account-<client> and it carries the "
            "client_id claim (clientId before Keycloak 21.1) that only client-"
            "credentials tokens get. Keycloak-specific; a person's token then never "
            "delegates, whichever client issued it."
        ),
    )
    user_clients: list[GrantIdentifier] = Field(
        default_factory=list,
        description=(
            "Clients people sign in through, besides security.user.client_id. A "
            "token issued to one never delegates, whatever roles it carries. List "
            "the login client where security.user.client_id names this receiver's "
            "own audience instead."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _refuse_the_single_switch(cls, data: object) -> object:
        # extra="forbid" already refuses the former key; this names what replaces it.
        if isinstance(data, dict) and "enabled" in data:
            raise ValueError(
                "security.delegation.enabled was split: set act_for_people where "
                "agents run and call other backends for a person, "
                "accept_delegated_calls on the backends that believe such calls"
            )
        return data

    @property
    def in_use(self) -> bool:
        """Either direction is on: persons are then named by workloads somewhere."""
        return self.act_for_people or self.accept_delegated_calls

    @property
    def roles_claim_path(self) -> tuple[str, ...]:
        if self.caller_roles_claim:
            return tuple(self.caller_roles_claim)
        return ("resource_access", self.audience, "roles")
