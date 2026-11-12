// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { skipToken } from "@reduxjs/toolkit/query";
import { useCallback } from "react";
import { useParams } from "react-router-dom";
import { useMySpacesQuery } from "../../slices/controlPlane/controlPlaneApiEnhancements";
import { useListConversationFilesQuery } from "../../slices/controlPlane/controlPlaneOpenApi";
import { resolveAgentSpace } from "../components/pages/TeamAgentsPage/weaverAgents";
import { useOpenSessionId } from "./capabilities/useOpenSessionId";
import {
  runtimeApi,
  type ListSessionWorkspaceFilesApiArg,
  type ListSessionWorkspaceFilesApiResponse,
} from "../../slices/runtime/runtimeOpenApi";
import { sameOriginDownloadUrl } from "../../utils/downloadUtils";

// Keep the generated contract; route it to the conversation's CP-approved pod.
const workspaceApi = runtimeApi.injectEndpoints({
  endpoints: (build) => ({
    workspaceFiles: build.query<
      ListSessionWorkspaceFilesApiResponse,
      ListSessionWorkspaceFilesApiArg & { url: string }
    >({
      query: ({ url }) => ({ url, redirect: "error" }),
    }),
  }),
});

export function workspaceFileUrl(filesUrl: string, path: string): string {
  return `${filesUrl.replace(/\/files$/, "/content")}?path=${encodeURIComponent(path)}`;
}

export function conversationFileUrl(space: string, session: string, document: string, preview = false): string {
  return `/control-plane/v1/spaces/${encodeURIComponent(space)}/sessions/${encodeURIComponent(session)}/files/${encodeURIComponent(document)}/${preview ? "preview" : "content"}`;
}

/** The catalogue survives runtime restarts and contains only the current user's deliverables. */
export function useConversationFiles(workspaceUrl?: string | null) {
  const { teamId } = useParams<{ teamId: string }>();
  const sessionId = useOpenSessionId();
  const spaces = useMySpacesQuery();
  const spaceId = resolveAgentSpace(spaces.currentData, teamId)?.id ?? "";
  const query = useListConversationFilesQuery(spaceId && sessionId ? { spaceId, sessionId } : skipToken, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
  });
  const workspaceEnabled = !!(workspaceUrl && sessionId && sameOriginDownloadUrl(workspaceUrl));
  const workspace = workspaceApi.useWorkspaceFilesQuery(
    workspaceEnabled ? { sessionId, url: workspaceUrl! } : skipToken,
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  const { refetch: refreshCatalogue, isUninitialized: catalogueUninitialized } = query;
  const { refetch: refreshWorkspace, isUninitialized: workspaceUninitialized } = workspace;
  const refetch = useCallback(() => {
    if (!catalogueUninitialized) void refreshCatalogue();
    if (workspaceEnabled && !workspaceUninitialized) void refreshWorkspace();
  }, [catalogueUninitialized, refreshCatalogue, workspaceEnabled, workspaceUninitialized, refreshWorkspace]);
  return {
    ...query,
    refetch,
    files: query.error ? [] : (query.currentData ?? []),
    spaceId,
    sessionId,
    workspaceFiles: workspaceEnabled && !workspace.error ? (workspace.currentData ?? []) : [],
    workspaceError: workspaceEnabled ? workspace.error : undefined,
    workspaceLoading: workspaceEnabled && workspace.isFetching,
  };
}
