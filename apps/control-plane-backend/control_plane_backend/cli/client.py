from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from control_plane_backend.product.schemas import (
    AgentTemplateSummary,
    CreateAgentInstanceRequest,
    CreatePromptRequest,
    ExecutionPreparation,
    FrontendBootstrap,
    ManagedAgentInstanceSummary,
    ManagedAgentRuntimeBinding,
    PromptDetail,
    PromptSummary,
    SessionListItem,
    UpdatePromptRequest,
)
from control_plane_backend.scheduler.policies.policy_models import (
    LifecycleTrigger,
    PolicyEvaluationResult,
    PolicyResolutionRequest,
)
from control_plane_backend.scheduler.temporal.structures import LifecycleManagerInput
from control_plane_backend.teams.schemas import Team, TeamMember, TeamWithPermissions
from control_plane_backend.users.schemas import UserSummary


class ControlPlaneUserDetails(BaseModel):
    """
    Minimal user-details payload consumed by the control-plane CLI.

    Why this model exists:
    - the CLI needs a stable typed shape for `/user` without depending on the
      temporary controller-local response model definition

    How to use it:
    - treat it as the typed response for `GET /user`

    Example:
    - `details = client.get_user_details()`
    """

    cguValidated: str | None = None
    personalTeam: TeamWithPermissions
    currentUser: UserSummary | None = None


class ControlPlanePolicySummary(PolicyEvaluationResult):
    """
    Typed response for the purge-policy summary endpoint.

    Why this model exists:
    - the CLI needs a stable local type for `/policies/purge` without importing
      the API application's inline response model

    How to use it:
    - treat it as the typed response for `GET /policies/purge`

    Example:
    - `summary = client.get_policy_summary()`
    """

    default_rule_count: int
    catalog_path: str


class ControlPlaneWorkflowStartResponse(BaseModel):
    """
    Typed lifecycle-run response used by the control-plane CLI.

    Why this model exists:
    - the CLI needs a typed contract for `/lifecycle/run-once` without importing
      the FastAPI app module just for a response class

    How to use it:
    - treat it as the typed response for one lifecycle trigger request

    Example:
    - `result = client.run_lifecycle_once(dry_run=True, batch_size=100)`
    """

    status: Literal["queued", "completed"] = "queued"
    backend: str
    workflow_id: str | None = None
    run_id: str | None = None
    result: dict[str, Any] | None = None


@dataclass(slots=True)
class ControlPlaneApiClient:
    """
    Minimal synchronous client for the public control-plane HTTP surface.

    Why this class exists:
    - the control-plane CLI should behave like a real API consumer, not call
      service-layer functions directly
    - typed methods keep terminal workflows explicit, testable, and safe

    How to use it:
    - instantiate it with the API base URL and an `httpx.Client`
    - call the typed methods needed by the interactive shell

    Example:
    - `client = ControlPlaneApiClient(base_url="http://127.0.0.1:8222/control-plane/v1", http_client=httpx.Client())`
    """

    base_url: str
    http_client: httpx.Client
    token_provider: Callable[[], str | None] | None = None

    def _auth_headers(self) -> dict[str, str]:
        """
        Build the Authorization header set for one control-plane request.

        Why this function exists:
        - the CLI should inject a fresh bearer token on every request when one
          login session or explicit token is configured

        How to use it:
        - called internally before each HTTP request

        Example:
        - `headers = client._auth_headers()`
        """

        if self.token_provider is None:
            return {}
        token = self.token_provider()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """
        Send one authenticated HTTP request to control-plane.

        Why this function exists:
        - all CLI methods share the same base URL and auth-header wiring

        How to use it:
        - call with one relative API path such as `/teams`

        Example:
        - `response = self._request("GET", "/teams")`
        """

        return self.http_client.request(
            method,
            f"{self.base_url}{path}",
            params=params,
            json=json_body,
            headers=self._auth_headers(),
        )

    def _get_json_payload(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """
        Send one request and return its decoded JSON payload.

        Why this function exists:
        - every typed CLI method needs the same "request then decode JSON"
          behavior with HTTP error propagation

        How to use it:
        - call from a typed client method and validate the returned payload

        Example:
        - `payload = self._get_json_payload("GET", "/teams")`
        """

        response = self._request(
            method,
            path,
            params=params,
            json_body=json_body,
        )
        response.raise_for_status()
        return response.json()

    def _validate_model(self, model_type: type[BaseModel], payload: Any) -> BaseModel:
        """
        Validate one decoded JSON payload against a pydantic model.

        Why this function exists:
        - typed CLI methods should fail early when the control-plane response no
          longer matches the expected contract

        How to use it:
        - pass the response model type and decoded JSON payload

        Example:
        - `team = self._validate_model(TeamWithPermissions, payload)`
        """

        return model_type.model_validate(payload)

    def get_user_details(self) -> ControlPlaneUserDetails:
        """Return the current user helper payload from control-plane."""

        payload = self._get_json_payload("GET", "/user")
        return ControlPlaneUserDetails.model_validate(payload)

    def get_frontend_bootstrap(self) -> FrontendBootstrap:
        """Return the frontend bootstrap payload owned by control-plane."""

        payload = self._get_json_payload("GET", "/frontend/bootstrap")
        return FrontendBootstrap.model_validate(payload)

    def list_teams(self) -> list[Team]:
        """Return the teams visible to the current user."""

        payload = self._get_json_payload("GET", "/teams")
        if not isinstance(payload, list):
            raise RuntimeError("Teams response must be a JSON array.")
        return [Team.model_validate(item) for item in payload]

    def get_team(self, team_id: str) -> TeamWithPermissions:
        """Return one team with its permissions."""

        payload = self._get_json_payload("GET", f"/teams/{team_id}")
        return TeamWithPermissions.model_validate(payload)

    def list_team_members(self, team_id: str) -> list[TeamMember]:
        """Return the members of one team."""

        payload = self._get_json_payload("GET", f"/teams/{team_id}/members")
        if not isinstance(payload, list):
            raise RuntimeError("Team members response must be a JSON array.")
        return [TeamMember.model_validate(item) for item in payload]

    def list_agent_templates(self, team_id: str) -> list[AgentTemplateSummary]:
        """Return the instantiable agent templates for one team."""

        payload = self._get_json_payload("GET", f"/teams/{team_id}/agent-templates")
        if not isinstance(payload, list):
            raise RuntimeError("Agent templates response must be a JSON array.")
        return [AgentTemplateSummary.model_validate(item) for item in payload]

    def list_agent_instances(self, team_id: str) -> list[ManagedAgentInstanceSummary]:
        """Return the managed agent instances for one team."""

        payload = self._get_json_payload("GET", f"/teams/{team_id}/agent-instances")
        if not isinstance(payload, list):
            raise RuntimeError("Agent instances response must be a JSON array.")
        return [ManagedAgentInstanceSummary.model_validate(item) for item in payload]

    def list_prompts(self, team_id: str) -> list[PromptSummary]:
        """Return the prompt-library summaries for one team."""

        payload = self._get_json_payload("GET", f"/teams/{team_id}/prompts")
        if not isinstance(payload, list):
            raise RuntimeError("Prompts response must be a JSON array.")
        return [PromptSummary.model_validate(item) for item in payload]

    def get_prompt(self, team_id: str, prompt_id: str) -> PromptDetail:
        """Return the full prompt-library payload for one prompt."""

        payload = self._get_json_payload("GET", f"/teams/{team_id}/prompts/{prompt_id}")
        return PromptDetail.model_validate(payload)

    def create_prompt(
        self,
        team_id: str,
        *,
        name: str,
        text: str,
        description: str | None = None,
    ) -> PromptSummary:
        """Create one team-scoped prompt-library record."""

        request = CreatePromptRequest(name=name, text=text, description=description)
        payload = self._get_json_payload(
            "POST",
            f"/teams/{team_id}/prompts",
            json_body=request.model_dump(mode="json"),
        )
        return PromptSummary.model_validate(payload)

    def update_prompt(
        self,
        team_id: str,
        prompt_id: str,
        *,
        name: str,
        text: str,
        description: str | None = None,
    ) -> PromptSummary:
        """Replace one team-scoped prompt-library record."""

        request = UpdatePromptRequest(name=name, text=text, description=description)
        payload = self._get_json_payload(
            "PUT",
            f"/teams/{team_id}/prompts/{prompt_id}",
            json_body=request.model_dump(mode="json"),
        )
        return PromptSummary.model_validate(payload)

    def delete_prompt(self, team_id: str, prompt_id: str) -> None:
        """Delete one team-scoped prompt-library record."""

        response = self._request("DELETE", f"/teams/{team_id}/prompts/{prompt_id}")
        response.raise_for_status()

    def enroll_agent_instance(
        self,
        team_id: str,
        *,
        template_id: str,
        display_name: str,
        description: str | None = None,
    ) -> ManagedAgentInstanceSummary:
        """Enroll one discovered template as a managed agent instance."""

        request = CreateAgentInstanceRequest(
            template_id=template_id,
            display_name=display_name,
            description=description,
        )
        payload = self._get_json_payload(
            "POST",
            f"/teams/{team_id}/agent-instances",
            json_body=request.model_dump(mode="json"),
        )
        return ManagedAgentInstanceSummary.model_validate(payload)

    def unenroll_agent_instance(self, team_id: str, agent_instance_id: str) -> None:
        """Delete one managed agent instance for one team."""

        response = self._request(
            "DELETE",
            f"/teams/{team_id}/agent-instances/{agent_instance_id}",
        )
        response.raise_for_status()

    def get_runtime_binding(
        self, team_id: str, agent_instance_id: str
    ) -> ManagedAgentRuntimeBinding:
        """Return the runtime binding for one managed agent instance (team-scoped)."""

        payload = self._get_json_payload(
            "GET",
            f"/teams/{team_id}/agent-instances/{agent_instance_id}/runtime",
        )
        return ManagedAgentRuntimeBinding.model_validate(payload)

    def list_sessions(self, team_id: str) -> list[SessionListItem]:
        """Return the session metadata list for one team."""

        payload = self._get_json_payload("GET", f"/teams/{team_id}/sessions")
        if not isinstance(payload, list):
            raise RuntimeError("Sessions response must be a JSON array.")
        return [SessionListItem.model_validate(item) for item in payload]

    def prepare_execution(
        self,
        team_id: str,
        agent_instance_id: str,
    ) -> ExecutionPreparation:
        """Return the execution preparation payload for one managed agent."""

        payload = self._get_json_payload(
            "POST",
            f"/teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution",
        )
        return ExecutionPreparation.model_validate(payload)

    def get_policy_summary(self) -> ControlPlanePolicySummary:
        """Return the current purge-policy summary."""

        payload = self._get_json_payload("GET", "/policies/purge")
        return ControlPlanePolicySummary.model_validate(payload)

    def resolve_policy(
        self,
        *,
        team_id: str | None = None,
        trigger: LifecycleTrigger = LifecycleTrigger.MEMBER_REMOVED,
    ) -> PolicyEvaluationResult:
        """Resolve the purge policy for one request context."""

        request = PolicyResolutionRequest(team_id=team_id, trigger=trigger)
        payload = self._get_json_payload(
            "POST",
            "/policies/purge/resolve",
            json_body=request.model_dump(mode="json"),
        )
        return PolicyEvaluationResult.model_validate(payload)

    def run_lifecycle_once(
        self,
        *,
        dry_run: bool = False,
        batch_size: int = 100,
    ) -> ControlPlaneWorkflowStartResponse:
        """Trigger one lifecycle run-once workflow request."""

        request = LifecycleManagerInput(dry_run=dry_run, batch_size=batch_size)
        payload = self._get_json_payload(
            "POST",
            "/lifecycle/run-once",
            json_body=request.model_dump(mode="json"),
        )
        return ControlPlaneWorkflowStartResponse.model_validate(payload)

    def dump_model_json(self, model: BaseModel) -> str:
        """
        Return one pretty JSON rendering for a typed response model.

        Why this function exists:
        - CLI inspection commands need a consistent JSON rendering for complex
          nested control-plane payloads

        How to use it:
        - pass any pydantic response model returned by this client

        Example:
        - `print(client.dump_model_json(binding))`
        """

        return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False)
