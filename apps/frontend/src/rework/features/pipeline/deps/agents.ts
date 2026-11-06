// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { controlPlaneApi } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { AgentsDeps } from "../scenarios/agentsScenario";
import type { PipelineDeps } from "../types";
import { FRESH, useApiDispatch } from "./api";

/** Extends the shared base deps, so the page keeps one set of product hooks. */
export function useAgentsDeps(base: PipelineDeps): AgentsDeps {
  const dispatch = useApiDispatch();
  const { i18n } = useTranslation();
  const locale = i18n.language?.startsWith("fr") ? "fr" : "en";
  return useMemo(() => {
    const cp = controlPlaneApi.endpoints;
    const teamId = base.teamId;
    return {
      ...base,
      updateAgent: async (agentInstanceId, { system, enabled }) => {
        await dispatch(
          cp.patchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatch.initiate({
            teamId,
            agentInstanceId,
            updateAgentInstanceRequest: {
              ...(system !== undefined ? { tuning_field_values: { "prompts.system": system } } : {}),
              ...(enabled !== undefined ? { status: enabled ? "enabled" : "disabled" } : {}),
            },
          }),
        ).unwrap();
      },
      listAgents: async () =>
        (
          await dispatch(
            cp.getTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGet.initiate({ teamId }, FRESH),
          ).unwrap()
        ).map((a) => ({ id: a.agent_instance_id, name: a.display_name })),
      effectiveModel: async (agentInstanceId) => {
        const model = await dispatch(
          cp.getEffectiveChatModelControlPlaneV1TeamsTeamIdRoutingPolicyEffectiveChatModelGet.initiate(
            { teamId, agentInstanceId },
            FRESH,
          ),
        ).unwrap();
        return { name: model.display_name ?? model.name ?? null, usable: model.enabled_for_team ?? false };
      },
      copyTargets: async (agentInstanceId) =>
        (
          await dispatch(
            cp.getAgentInstanceCopyTargetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyTargetsGet.initiate(
              { teamId, agentInstanceId },
              FRESH,
            ),
          ).unwrap()
        ).targets.map((t) => ({ teamId: t.team_id, templateEnabled: t.template_enabled })),
      duplicate: async (agentInstanceId, name) => {
        const response = await dispatch(
          cp.postAgentInstanceCopyControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyPost.initiate({
            teamId,
            agentInstanceId,
            agentCopyRequest: { target_team_ids: [teamId], display_name: name ?? null, locale },
          }),
        ).unwrap();
        const result = response.results[0];
        return {
          agentId: result?.agent?.agent_instance_id ?? null,
          name: result?.agent?.display_name ?? null,
          errorCode: result?.error_code ?? result?.error ?? null,
        };
      },
    };
  }, [base, dispatch, locale]);
}
