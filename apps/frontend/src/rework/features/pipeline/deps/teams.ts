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
import { legacyControlPlaneApi } from "../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { knowledgeFlowApi } from "../../../../slices/legacyKnowledgeFlow/knowledgeFlowOpenApi";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { personalTeamId } from "../../../components/shared/utils/teamId";
import type { TeamsDeps } from "../scenarios/teamsScenario";
import { FRESH, useApiDispatch } from "./api";

export function useTeamsDeps(): TeamsDeps {
  const dispatch = useApiDispatch();
  const userId = KeyCloakService.GetUserId() ?? "";
  return useMemo(() => {
    const cp = legacyControlPlaneApi.endpoints;
    const kf = knowledgeFlowApi.endpoints;
    return {
      userId,
      personalTeamId: personalTeamId(userId),
      // With the charter off, a new team's admin is effective at once.
      charterAccepted: async () => {
        const bootstrap = await dispatch(
          cp.getFrontendBootstrapControlPlaneV1FrontendBootstrapGet.initiate(undefined, FRESH),
        ).unwrap();
        if (!bootstrap.team_admin_charter_enabled) return true;
        const acceptance = await dispatch(
          cp.getTeamAdminCharterAcceptanceControlPlaneV1TeamAdminCharterGet.initiate(undefined, FRESH),
        ).unwrap();
        return acceptance != null;
      },
      createTeam: async (name, description, adminId) => {
        const team = await dispatch(
          cp.createTeamControlPlaneV1TeamsPost.initiate({
            createTeamRequest: { name, description, initial_team_admin_ids: [adminId] },
          }),
        ).unwrap();
        const relations = team.admins?.some((a) => a.id === adminId) ? ["team_admin"] : (team.my_relations ?? []);
        return { id: team.id, relations };
      },
      readTeam: async (teamId) => {
        const team = await dispatch(cp.getTeamControlPlaneV1TeamsTeamIdGet.initiate({ teamId }, FRESH)).unwrap();
        return { permissions: team.permissions ?? [] };
      },
      grantRole: async (teamId, memberId, relation) => {
        await dispatch(
          cp.grantTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesPost.initiate({
            teamId,
            userId: memberId,
            grantTeamMemberRoleRequest: { relation },
          }),
        ).unwrap();
      },
      revokeRole: async (teamId, memberId, relation) => {
        await dispatch(
          cp.revokeTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesRelationDelete.initiate({
            teamId,
            userId: memberId,
            relation,
          }),
        ).unwrap();
      },
      createPrompt: async (teamId, name) =>
        (
          await dispatch(
            cp.postTeamPromptControlPlaneV1TeamsTeamIdPromptsPost.initiate({
              teamId,
              createPromptRequest: { name, text: "Self-test team prompt, deleted at the end of the run." },
            }),
          ).unwrap()
        ).id,
      readPrompt: async (teamId, promptId) => {
        await dispatch(
          cp.getTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGet.initiate({ teamId, promptId }, FRESH),
        ).unwrap();
      },
      deletePrompt: async (teamId, promptId) => {
        await dispatch(
          cp.deleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDelete.initiate({ teamId, promptId }),
        ).unwrap();
      },
      createLibrary: async (teamId, name) =>
        (await dispatch(kf.createTag.initiate({ tagCreate: { name, type: "document", team_id: teamId } })).unwrap()).id,
      listLibraryIds: async (teamId) =>
        (
          await dispatch(
            kf.listTags.initiate(
              teamId ? { type: "document", ownerFilter: "team", teamId } : { type: "document" },
              FRESH,
            ),
          ).unwrap()
        ).map((t) => t.id),
      deleteLibrary: async (tagId) => {
        await dispatch(kf.deleteTag.initiate({ tagId })).unwrap();
      },
      provisionAgent: async (teamId, sourceAgentId, name) => {
        const templates = await dispatch(
          cp.getTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGet.initiate(
            { teamId, includeNonPublic: true },
            FRESH,
          ),
        ).unwrap();
        const template = templates.find((t) => t.source_agent_id === sourceAgentId && t.status !== "unavailable");
        if (!template) return null;
        const created = await dispatch(
          cp.postTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPost.initiate({
            teamId,
            createAgentInstanceRequest: {
              template_id: template.template_id,
              display_name: name,
              usage_statement: "Automated internal self-test pipeline run — not a production agent.",
            },
          }),
        ).unwrap();
        return created.agent_instance_id;
      },
      listAgentIds: async (teamId) =>
        (
          await dispatch(
            cp.getTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGet.initiate({ teamId }, FRESH),
          ).unwrap()
        ).map((a) => a.agent_instance_id),
      copyAgent: async (teamId, agentInstanceId, targetTeamId) => {
        const response = await dispatch(
          cp.postAgentInstanceCopyControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyPost.initiate({
            teamId,
            agentInstanceId,
            agentCopyRequest: { target_team_ids: [targetTeamId] },
          }),
        ).unwrap();
        return response.results[0]?.agent?.agent_instance_id ?? null;
      },
      deleteAgent: async (teamId, agentInstanceId) => {
        await dispatch(
          cp.deleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDelete.initiate({
            teamId,
            agentInstanceId,
          }),
        ).unwrap();
      },
      wikiEnabled: async (teamId) =>
        (
          await dispatch(
            cp.wikiAvailabilityControlPlaneV1TeamsTeamIdWikiAvailabilityGet.initiate({ teamId }, FRESH),
          ).unwrap()
        ).enabled,
      createWikiPage: async (teamId, title, content) => {
        const page = await dispatch(
          cp.createPageControlPlaneV1TeamsTeamIdWikiPagesPost.initiate({
            teamId,
            createWikiPageRequest: { title, content_md: content },
          }),
        ).unwrap();
        return { pageId: page.page.page_id, slug: page.page.slug, revisionId: page.revision_id ?? null };
      },
      writeWikiPage: async (teamId, pageId, content, baseRevisionId) => {
        await dispatch(
          cp.writePageContentControlPlaneV1TeamsTeamIdWikiPagesPageIdContentPut.initiate({
            teamId,
            pageId,
            updateWikiPageContentRequest: { content_md: content, base_revision_id: baseRevisionId },
          }),
        ).unwrap();
      },
      wikiRevisions: async (teamId, pageId) =>
        (
          await dispatch(
            cp.listRevisionsControlPlaneV1TeamsTeamIdWikiPagesPageIdRevisionsGet.initiate({ teamId, pageId }, FRESH),
          ).unwrap()
        ).revisions?.map((r) => r.revision_id) ?? [],
      restoreWikiRevision: async (teamId, pageId, revisionId) => {
        await dispatch(
          cp.restoreRevisionControlPlaneV1TeamsTeamIdWikiPagesPageIdRevisionsRevisionIdRestorePost.initiate({
            teamId,
            pageId,
            revisionId,
          }),
        ).unwrap();
      },
      readWikiPage: async (teamId, slug) =>
        (
          await dispatch(
            cp.readPageControlPlaneV1TeamsTeamIdWikiPagesSlugGet.initiate({ teamId, slug }, FRESH),
          ).unwrap()
        ).content_md ?? "",
      deleteWikiPage: async (teamId, pageId) => {
        await dispatch(
          cp.deletePageControlPlaneV1TeamsTeamIdWikiPagesPageIdDelete.initiate({ teamId, pageId }),
        ).unwrap();
      },
      setJoinLink: async (teamId, enabled) => {
        const link = await dispatch(
          cp.setTeamJoinLinkControlPlaneV1TeamsTeamIdJoinLinkPut.initiate({ teamId, setTeamJoinLink: { enabled } }),
        ).unwrap();
        return { enabled: link.enabled, token: link.token ?? null };
      },
      regenerateJoinLink: async (teamId) =>
        (
          await dispatch(
            cp.regenerateTeamJoinLinkControlPlaneV1TeamsTeamIdJoinLinkRegeneratePost.initiate({ teamId }),
          ).unwrap()
        ).token ?? null,
      modelProfileCount: async (teamId) =>
        (
          await dispatch(
            cp.getAvailableModelProfilesControlPlaneV1TeamsTeamIdRoutingPolicyAvailableModelsGet.initiate(
              { teamId },
              FRESH,
            ),
          ).unwrap()
        ).profiles?.length ?? 0,
      readRoutingPolicy: async (teamId) => {
        await dispatch(
          cp.getTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGet.initiate({ teamId }, FRESH),
        ).unwrap();
      },
      deleteTeam: async (teamId) => {
        await dispatch(cp.deleteTeamControlPlaneV1TeamsTeamIdDelete.initiate({ teamId })).unwrap();
      },
    };
  }, [dispatch, userId]);
}
