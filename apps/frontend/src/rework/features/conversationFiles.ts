// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { skipToken } from "@reduxjs/toolkit/query";
import { useParams } from "react-router-dom";
import { useMySpacesQuery } from "../../slices/controlPlane/controlPlaneApiEnhancements";
import { useListConversationFilesQuery } from "../../slices/controlPlane/controlPlaneOpenApi";
import { resolveAgentSpace } from "../components/pages/TeamAgentsPage/weaverAgents";
import { useOpenSessionId } from "./capabilities/useOpenSessionId";

export function conversationFileUrl(space: string, session: string, document: string, preview = false): string {
  return `/control-plane/v1/spaces/${encodeURIComponent(space)}/sessions/${encodeURIComponent(session)}/files/${encodeURIComponent(document)}/${preview ? "preview" : "content"}`;
}

/** The catalogue survives runtime restarts and contains only the current user's deliverables. */
export function useConversationFiles() {
  const { teamId } = useParams<{ teamId: string }>();
  const sessionId = useOpenSessionId();
  const spaces = useMySpacesQuery();
  const spaceId = resolveAgentSpace(spaces.currentData, teamId)?.id ?? "";
  const query = useListConversationFilesQuery(spaceId && sessionId ? { spaceId, sessionId } : skipToken, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
  });
  return { ...query, files: query.error ? [] : (query.currentData ?? []), spaceId, sessionId };
}
