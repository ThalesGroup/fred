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
import {
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation,
  useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation,
  useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation,
  useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useLazyGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  useLazyGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery,
  useLazyGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery,
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation,
  usePrepareAgentExecutionMutation,
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation,
  usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
} from "../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useCreateTagMutation,
  useDeleteTagMutation,
  useLazyListTagsQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { awaitIngestion, streamAgentTurn, uploadDocument } from "./actions";
import { expectRefused } from "./scenarios/runScope";
import type { PipelineDeps, Scenario } from "./types";
import { useScenarioRun, type PipelineRun } from "./useScenarioRun";
import { KeyCloakService } from "../../../security/KeycloakService";
import { personalTeamId } from "../../components/shared/utils/teamId";

/** Binds the real product hooks into the PipelineDeps contract, as the signed-in admin. */
export function usePipelineDeps(): PipelineDeps {
  // Canonical personal-team id (`personal-<uid>`), NOT the bare "personal" alias.
  // The control-plane accepts both (teams/system.py), but the agent pod is now the
  // OpenFGA authority and checks ReBAC against the canonical id only — the bare
  // alias has no tuple, so it fails closed with 403 (RUNTIME-07 rev. 2). Mirrors
  // what ManagedChatPage already sends from the bootstrap-resolved team id.
  const teamId = personalTeamId(KeyCloakService.GetUserId() ?? "");
  const [createTag] = useCreateTagMutation();
  const [deleteTag] = useDeleteTagMutation();
  const [prepareExecution] = usePrepareAgentExecutionMutation();
  const [listTemplates] = useLazyGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery();
  const [listAgents] = useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery();
  const [listPrompts] = useLazyGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery();
  const [readSession] = useLazyGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery();
  const [enrollInstance] = usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation();
  const [deleteInstance] =
    useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation();
  const [listTags] = useLazyListTagsQuery();
  const [createPrompt] = usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation();
  const [deletePrompt] = useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation();
  const [postSession] = usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation();
  const [patchSession] = usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation();
  const [deleteSessionMutation] = useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation();

  return useMemo(
    () => ({
      teamId,
      createLibrary: async (name) => {
        // team_id: null = the caller's personal space (owner = the admin).
        const tag = await createTag({ tagCreate: { name, type: "document", team_id: null } }).unwrap();
        return tag.id;
      },
      deleteLibrary: async (libraryId) => {
        await deleteTag({ tagId: libraryId }).unwrap();
      },
      listLibraries: async () => {
        const tags = await listTags({}).unwrap();
        return tags.filter((t) => t.type === "document").map((t) => ({ id: t.id, name: t.name }));
      },
      verifyDeleted: async (kind, id) => {
        if (kind === "session") {
          await expectRefused(() => readSession({ teamId, sessionId: id }).unwrap(), "reading a deleted session", [
            404,
          ]);
          return;
        }
        const ids =
          kind === "library"
            ? (await listTags({}).unwrap()).filter((tag) => tag.type === "document").map((tag) => tag.id)
            : kind === "agent"
              ? (await listAgents({ teamId }).unwrap()).map((agent) => agent.agent_instance_id)
              : (await listPrompts({ teamId }).unwrap()).map((prompt) => prompt.id);
        if (ids.includes(id)) throw new Error(`${kind} ${id} is still listed after deletion`);
      },
      ingestDocument: async (libraryId, file, signal) => {
        const taskId = await uploadDocument(libraryId, file);
        await awaitIngestion(taskId, signal);
      },
      provisionAgentInstance: async (sourceAgentId, tuningFieldValues, signal, runToken) => {
        signal?.throwIfAborted();
        // 1. Find the template (composite template_id) for this agent definition.
        //    include_non_public so the internal self-test agent is discoverable
        //    even though it's hidden from the create-agent catalog.
        const templates = await listTemplates({ teamId, includeNonPublic: true }).unwrap();
        signal?.throwIfAborted();
        const template = templates.find((t) => t.source_agent_id === sourceAgentId && t.status !== "unavailable");
        if (!template) return null;
        // Names are unique per team, so a fixed name left behind by an
        // interrupted run would refuse every later enrollment.
        const suffix = runToken ?? crypto.randomUUID().slice(0, 8);
        const created = await enrollInstance({
          teamId,
          createAgentInstanceRequest: {
            template_id: template.template_id,
            display_name: `Self-test (auto) ${suffix}`,
            usage_statement: "Automated internal self-test pipeline run — not a production agent.",
            ...(tuningFieldValues ? { tuning_field_values: tuningFieldValues } : {}),
          },
        }).unwrap();
        // Return the created id even after cancellation so cleanup can remove it.
        return created.agent_instance_id;
      },
      deleteAgentInstance: async (agentInstanceId) => {
        await deleteInstance({ teamId, agentInstanceId }).unwrap();
      },
      createContextPrompt: async (name, text) => {
        const created = await createPrompt({ teamId, createPromptRequest: { name, text } }).unwrap();
        return created.id;
      },
      deleteContextPrompt: async (promptId) => {
        await deletePrompt({ teamId, promptId }).unwrap();
      },
      createSession: async (agentInstanceId, runToken) => {
        // The session id is frontend-generated (CreateSessionRequest.session_id).
        const sessionId = crypto.randomUUID();
        await postSession({
          teamId,
          createSessionRequest: {
            session_id: sessionId,
            agent_instance_id: agentInstanceId,
            title: `Self-test (auto) ${runToken ?? sessionId.slice(0, 8)}`,
          },
        }).unwrap();
        return sessionId;
      },
      attachSessionPrompts: async (sessionId, promptIds) => {
        // Full ordered replacement set — resolved into context_prompt_text at prepare-execution.
        await patchSession({ teamId, sessionId, updateSessionRequest: { context_prompt_ids: promptIds } }).unwrap();
      },
      deleteSession: async (sessionId) => {
        await deleteSessionMutation({ teamId, sessionId }).unwrap();
      },
      runAgentTurn: async ({
        agentInstanceId,
        question,
        libraryIds,
        sessionId,
        bearer,
        signal,
        onProgress,
        onStatus,
      }) => {
        signal?.throwIfAborted();
        // Preparation stays on the session; only the streamed turn honors an
        // explicit bearer, so a scenario can let that one call expire.
        const prep = await prepareExecution({
          teamId,
          agentInstanceId,
          ...(sessionId ? { sessionId } : {}),
        }).unwrap();
        signal?.throwIfAborted();
        return streamAgentTurn(prep, {
          agentInstanceId,
          teamId,
          question,
          libraryIds,
          sessionId: sessionId ?? null,
          bearer,
          signal,
          onProgress,
          onStatus,
        });
      },
    }),
    [
      createTag,
      deleteTag,
      listTags,
      listAgents,
      listPrompts,
      readSession,
      prepareExecution,
      listTemplates,
      enrollInstance,
      deleteInstance,
      createPrompt,
      deletePrompt,
      postSession,
      patchSession,
      deleteSessionMutation,
    ],
  );
}

export type { PipelineRun };

export function usePipelineRun(scenario: Scenario): PipelineRun {
  return useScenarioRun(scenario, usePipelineDeps());
}
