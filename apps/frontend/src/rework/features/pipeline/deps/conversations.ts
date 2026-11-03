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
import { controlPlaneApi } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { knowledgeFlowApi } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { ConversationsDeps } from "../scenarios/conversationsScenario";
import type { PipelineDeps } from "../types";
import { FRESH, useApiDispatch } from "./api";

/** Extends the shared base deps, so the page keeps one set of product hooks. */
export function useConversationsDeps(base: PipelineDeps): ConversationsDeps {
  const dispatch = useApiDispatch();
  return useMemo(() => {
    const cp = controlPlaneApi.endpoints;
    const kf = knowledgeFlowApi.endpoints;
    const teamId = base.teamId;
    return {
      ...base,
      listSessions: async () =>
        (
          await dispatch(cp.getTeamSessionsControlPlaneV1TeamsTeamIdSessionsGet.initiate({ teamId }, FRESH)).unwrap()
        ).map((s) => ({ id: s.session_id, title: s.title ?? null })),
      readSession: async (sessionId) => {
        const s = await dispatch(
          cp.getTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGet.initiate({ teamId, sessionId }, FRESH),
        ).unwrap();
        return { title: s.title ?? null, agentId: s.agent_instance_id ?? null };
      },
      renameSession: async (sessionId, title) => {
        await dispatch(
          cp.patchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatch.initiate({
            teamId,
            sessionId,
            updateSessionRequest: { title },
          }),
        ).unwrap();
      },
      // Same two calls as the chat composer: session-scoped ingestion, then the attachment record.
      attach: async (sessionId, file) => {
        const form = new FormData();
        form.append("file", file);
        form.append("session_id", sessionId);
        form.append("scope", "session");
        form.append("options_json", JSON.stringify({ include_summary: true }));
        const ingested = await dispatch(
          kf.fastIngestKnowledgeFlowV1FastIngestPost.initiate({
            bodyFastIngestKnowledgeFlowV1FastIngestPost: form as never,
          }),
        ).unwrap();
        const attachmentId = crypto.randomUUID();
        await dispatch(
          cp.postTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPost.initiate({
            teamId,
            sessionId,
            createSessionAttachmentRequest: {
              attachment_id: attachmentId,
              name: file.name,
              mime: file.type || null,
              size_bytes: file.size,
              summary_md: ingested.summary_md || "Self-test attachment",
              document_uid: ingested.document_uid || null,
            },
          }),
        ).unwrap();
        return attachmentId;
      },
      listAttachments: async (sessionId) =>
        (
          await dispatch(
            cp.getTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGet.initiate(
              { teamId, sessionId },
              FRESH,
            ),
          ).unwrap()
        ).map((a) => a.attachment_id),
      deleteAttachment: async (sessionId, attachmentId) => {
        await dispatch(
          cp.deleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDelete.initiate(
            {
              teamId,
              sessionId,
              attachmentId,
            },
          ),
        ).unwrap();
      },
      searchSession: async (sessionId, question) =>
        (
          await dispatch(
            kf.searchDocumentsUsingVectorization.initiate({
              searchRequest: {
                question,
                top_k: 10,
                session_id: sessionId,
                include_session_scope: true,
                include_corpus_scope: false,
                owner_filter: "personal",
              },
            }),
          ).unwrap()
        ).map((h) => ({ uid: h.uid, content: h.content })),
      bulkDelete: async (sessionIds) =>
        dispatch(
          cp.postBulkDeleteMySessionsControlPlaneV1MeSessionsBulkDeletePost.initiate({
            bulkDeleteSessionsRequest: { sessions: sessionIds.map((session_id) => ({ session_id, team_id: teamId })) },
          }),
        ).unwrap(),
      inactiveCount: async () => {
        const response = await dispatch(
          cp.getMyInactiveSessionsControlPlaneV1MeInactiveSessionsGet.initiate({}, FRESH),
        ).unwrap();
        return response.sessions?.length ?? 0;
      },
      sleep: (ms) => new Promise((resolve) => window.setTimeout(resolve, ms)),
    };
  }, [base, dispatch]);
}
