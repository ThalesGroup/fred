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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation,
  useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation,
  useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation,
  useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useLazyGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation,
  usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation,
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation,
  usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
} from "../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useCreateTagKnowledgeFlowV1TagsPostMutation,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useLazyListAllTagsKnowledgeFlowV1TagsGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { awaitIngestion, streamAgentTurn, uploadDocument } from "./actions";
import type { PipelineDeps, Scenario, StepReport } from "./types";
import { KeyCloakService } from "../../../security/KeycloakService";
import { personalTeamId } from "../../components/shared/utils/teamId";

export interface PipelineRun {
  steps: StepReport[];
  isRunning: boolean;
  start: () => void;
}

/**
 * Generic runner: binds the real product hooks into the PipelineDeps contract,
 * runs ANY scenario, and tracks each step for the UI. The admin self-test page
 * passes the self-test scenario; a future eval-demo page passes its own.
 */
export function usePipelineRun(scenario: Scenario): PipelineRun {
  // Canonical personal-team id (`personal-<uid>`), NOT the bare "personal" alias.
  // The control-plane accepts both (teams/system.py), but the agent pod is now the
  // OpenFGA authority and checks ReBAC against the canonical id only — the bare
  // alias has no tuple, so it fails closed with 403 (RUNTIME-07 rev. 2). Mirrors
  // what ManagedChatPage already sends from the bootstrap-resolved team id.
  const teamId = personalTeamId(KeyCloakService.GetUserId() ?? "");
  const [createTag] = useCreateTagKnowledgeFlowV1TagsPostMutation();
  const [deleteTag] = useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation();
  const [prepareExecution] =
    usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation();
  const [listInstances] = useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery();
  const [listTemplates] = useLazyGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery();
  const [enrollInstance] = usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation();
  const [deleteInstance] =
    useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation();
  const [listTags] = useLazyListAllTagsKnowledgeFlowV1TagsGetQuery();
  const [createPrompt] = usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation();
  const [deletePrompt] = useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation();
  const [postSession] = usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation();
  const [patchSession] = usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation();
  const [deleteSessionMutation] = useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation();

  const [steps, setSteps] = useState<StepReport[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  const report = useCallback((step: StepReport) => {
    setSteps((prev) => {
      const i = prev.findIndex((s) => s.id === step.id);
      if (i === -1) return [...prev, step];
      const next = [...prev];
      next[i] = step;
      return next;
    });
  }, []);

  const deps: PipelineDeps = useMemo(
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
      ingestDocument: async (libraryId, file, signal) => {
        const taskId = await uploadDocument(libraryId, file);
        await awaitIngestion(taskId, signal);
      },
      provisionAgentInstance: async (sourceAgentId, tuningFieldValues) => {
        // 1. Find the template (composite template_id) for this agent definition.
        //    include_non_public so the internal self-test agent is discoverable
        //    even though it's hidden from the create-agent catalog.
        const templates = await listTemplates({ teamId, includeNonPublic: true }).unwrap();
        const template = templates.find((t) => t.source_agent_id === sourceAgentId && t.status !== "unavailable");
        if (!template) return null;
        // 2. Reconcile: delete any leftover instances of this internal template
        //    (all of which are harness-created) so we always enroll fresh and
        //    delete exactly what we created.
        const instances = await listInstances({ teamId }).unwrap();
        for (const stale of instances.filter((i) => i.template_id === template.template_id)) {
          await deleteInstance({ teamId, agentInstanceId: stale.agent_instance_id }).unwrap();
        }
        // 3. Enroll a fresh instance, with the optional initial tuning (e.g. the
        //    system-prompt marker for the tuning-prompt journey).
        const created = await enrollInstance({
          teamId,
          createAgentInstanceRequest: {
            template_id: template.template_id,
            display_name: "Self-test (auto)",
            usage_statement: "Automated internal self-test pipeline run — not a production agent.",
            ...(tuningFieldValues ? { tuning_field_values: tuningFieldValues } : {}),
          },
        }).unwrap();
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
      createSession: async (agentInstanceId) => {
        // The session id is frontend-generated (CreateSessionRequest.session_id).
        const sessionId = crypto.randomUUID();
        await postSession({
          teamId,
          createSessionRequest: {
            session_id: sessionId,
            agent_instance_id: agentInstanceId,
            title: "Self-test (auto)",
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
      runAgentTurn: async ({ agentInstanceId, question, libraryIds, sessionId }) => {
        const prep = await prepareExecution({
          teamId,
          agentInstanceId,
          lang: "en",
          ...(sessionId ? { sessionId } : {}),
        }).unwrap();
        return streamAgentTurn(prep, {
          agentInstanceId,
          teamId,
          question,
          libraryIds,
          sessionId: sessionId ?? null,
        });
      },
    }),
    [
      createTag,
      deleteTag,
      listTags,
      prepareExecution,
      listInstances,
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

  const start = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setSteps([]);
    setIsRunning(true);
    void scenario(deps, report, controller.signal).finally(() => {
      if (!controller.signal.aborted) setIsRunning(false);
    });
  }, [deps, report, scenario]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  return { steps, isRunning, start };
}
