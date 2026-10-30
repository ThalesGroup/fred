// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { FetchBaseQueryMeta } from "@reduxjs/toolkit/query";
import { controlPlaneApi, type OrganizationDetail } from "./controlPlaneOpenApi";

// The generator types binary fields as Blob, but sends the enclosing object as
// JSON. Adapt only the transport; URL, method, arguments and result stay generated.
export const enhancedControlPlaneApi = controlPlaneApi.enhanceEndpoints({
  addTagTypes: [
    "Folders",
    "Documents",
    "DocumentUploads",
    "OrganizationAgents",
    "OrganizationCapabilities",
    "OrganizationModels",
    "AgentInstances",
    "AgentTemplates",
    "Sessions",
    "Attachments",
  ],
  endpoints: {
    listAttachments: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { spaceId, sessionId }) => [
        { type: "Attachments", id: `${spaceId}:${sessionId}` },
      ],
    },
    uploadAttachment(endpoint) {
      endpoint.extraOptions = { retryUnauthorized: false };
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        const body = new FormData();
        body.append("file", args.fileUpload.file);
        return { ...(typeof request === "string" ? { url: request } : request), body, timeout: 2_000_000 };
      };
      endpoint.transformErrorResponse = (error, meta) => ({
        ...error,
        retryAfter: (meta as FetchBaseQueryMeta | undefined)?.response?.headers.get("Retry-After"),
      });
    },
    deleteAttachment: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, sessionId }) =>
        error ? [] : [{ type: "Attachments", id: `${spaceId}:${sessionId}` }],
    },
    listSessions: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { spaceId }) => [{ type: "Sessions", id: spaceId }],
    },
    getSession: {
      keepUnusedDataFor: 0,
      providesTags: (_result, _error, { spaceId, sessionId }) => [{ type: "Sessions", id: `${spaceId}:${sessionId}` }],
    },
    createSession: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId }) => (error ? [] : [{ type: "Sessions", id: spaceId }]),
    },
    updateSession: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, sessionId }) =>
        error
          ? []
          : [
              { type: "Sessions", id: spaceId },
              { type: "Sessions", id: `${spaceId}:${sessionId}` },
            ],
    },
    deleteSession: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId }) => (error ? [] : [{ type: "Sessions", id: spaceId }]),
    },

    listAgentInstances: {
      providesTags: (_result, _error, { spaceId }) => [{ type: "AgentInstances", id: spaceId }],
    },
    getAgentInstance: {
      providesTags: (_result, _error, { spaceId, agentInstanceId }) => [
        { type: "AgentInstances", id: `${spaceId}:${agentInstanceId}` },
      ],
    },
    spaceAgentTemplates: {
      providesTags: (_result, _error, { spaceId }) => [{ type: "AgentTemplates", id: spaceId }],
    },
    createAgentInstance: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId }) => (error ? [] : [{ type: "AgentInstances", id: spaceId }]),
    },
    updateAgentInstance: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, agentInstanceId }) =>
        error
          ? []
          : [
              { type: "AgentInstances", id: spaceId },
              { type: "AgentInstances", id: `${spaceId}:${agentInstanceId}` },
            ],
    },
    deleteAgentInstance: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, error, { spaceId, agentInstanceId }) =>
        error
          ? []
          : [
              { type: "AgentInstances", id: spaceId },
              { type: "AgentInstances", id: `${spaceId}:${agentInstanceId}` },
            ],
    },
    organizationModels: {
      providesTags: (_result, _error, { organizationId }) => [{ type: "OrganizationModels", id: organizationId }],
    },
    organizationModelPolicy: {
      providesTags: (_result, _error, { organizationId }) => [{ type: "OrganizationModels", id: organizationId }],
    },
    replaceOrganizationModelPolicy: {
      extraOptions: { retryUnauthorized: false },
      invalidatesTags: (_result, _error, { organizationId }) => [{ type: "OrganizationModels", id: organizationId }],
    },
    refreshModelSource: {
      extraOptions: { retryUnauthorized: false },
      // A failed discovery also updates its observation; inventories share sources.
      invalidatesTags: ["OrganizationModels"],
    },
    organizationAgents: {
      providesTags: (_result, _error, arg) => [{ type: "OrganizationAgents", id: arg.organizationId }],
    },
    setOrganizationAgentDefault: {
      invalidatesTags: (_result, _error, arg) => [{ type: "OrganizationAgents", id: arg.organizationId }],
      extraOptions: { retryUnauthorized: false },
    },
    organizationCapabilities: {
      providesTags: (_result, _error, arg) => [{ type: "OrganizationCapabilities", id: arg.organizationId }],
    },
    refreshOrganizationCapabilities: {
      extraOptions: { retryUnauthorized: false },
      // A failed refresh also records the pod as unavailable; pods are shared by organizations.
      invalidatesTags: ["OrganizationCapabilities"],
    },
    setOrganizationCapabilityDefault: {
      invalidatesTags: (_result, _error, arg) => [{ type: "OrganizationCapabilities", id: arg.organizationId }],
      extraOptions: { retryUnauthorized: false },
    },
    entries: { providesTags: ["Folders", "Documents"] },
    summary: { providesTags: ["Documents"] },
    receipts: { providesTags: ["DocumentUploads"] },
    receipt: { providesTags: ["DocumentUploads"] },
    acknowledge: { invalidatesTags: ["DocumentUploads"], extraOptions: { retryUnauthorized: false } },
    setRetrievable(endpoint) {
      endpoint.invalidatesTags = ["Documents"];
      endpoint.extraOptions = { retryUnauthorized: false };
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        return { ...(typeof request === "string" ? { url: request } : request), timeout: 90_000 };
      };
    },
    start: { invalidatesTags: ["Documents", "DocumentUploads"], extraOptions: { retryUnauthorized: false } },
    preview(endpoint) {
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        return {
          ...(typeof request === "string" ? { url: request } : request),
          responseHandler: "text",
          timeout: 30_000,
        };
      };
    },
    upload(endpoint) {
      endpoint.extraOptions = { retryUnauthorized: false };
      endpoint.invalidatesTags = ["Documents", "DocumentUploads"];
      const query = endpoint.query!;
      endpoint.query = (args) => {
        const request = query(args);
        const body = new FormData();
        body.append("file", args.fileUpload.file);
        return { ...(typeof request === "string" ? { url: request } : request), body, timeout: 2_000_000 };
      };
    },
    createOrganization: { extraOptions: { retryUnauthorized: false } },
    updateOrganization: {
      extraOptions: { retryUnauthorized: false },
      // Patch the cached registry pages in place: a refetch would replace the rows, and the
      // edit button that opened the dialog with them, so focus could not return to it.
      async onQueryStarted({ id }, { dispatch, getState, queryFulfilled }) {
        let detail: OrganizationDetail;
        try {
          detail = (await queryFulfilled).data;
        } catch {
          return;
        }
        // The returned detail is what was committed: a reopened edit must not start from an older copy.
        void dispatch(controlPlaneApi.util.upsertQueryData("getOrganization", { id }, detail));
        const saved = detail.organization;
        const state = getState() as Parameters<typeof controlPlaneApi.util.selectCachedArgsForQuery>[0];
        for (const args of controlPlaneApi.util.selectCachedArgsForQuery(state, "organizationRegistry")) {
          dispatch(
            controlPlaneApi.util.updateQueryData("organizationRegistry", args, (draft) => {
              const index = draft.items.findIndex((item) => item.id === saved.id);
              if (index >= 0) draft.items[index] = saved;
            }),
          );
        }
      },
    },
    createFolder: { extraOptions: { retryUnauthorized: false }, invalidatesTags: ["Folders"] },
    renameFolder: { extraOptions: { retryUnauthorized: false }, invalidatesTags: ["Folders"] },
    deleteDocument: { extraOptions: { retryUnauthorized: false }, invalidatesTags: ["Documents"] },
    deleteFolder: { extraOptions: { retryUnauthorized: false }, invalidatesTags: ["Folders"] },
    createPersonalSpace: {
      extraOptions: { retryUnauthorized: false },
    },
    bootstrapPlatformAdmin: { extraOptions: { retryUnauthorized: false } },
    importBlueprint(endpoint) {
      // Bearer expiry can follow committed provisioning writes: replay is explicit.
      endpoint.extraOptions = { retryUnauthorized: false };
      const generatedQuery = endpoint.query!;
      endpoint.query = (args) => {
        const request = generatedQuery(args);
        const body = new FormData();
        body.append("file", args.provisioningUpload.file);
        return { ...(typeof request === "string" ? { url: request } : request), body };
      };
    },
  },
});

export const {
  useListAttachmentsQuery,
  useDeleteAttachmentMutation,
  useListSessionsQuery,
  useGetSessionQuery,
  useCreateSessionMutation,
  useUpdateSessionMutation,
  useDeleteSessionMutation,
  usePrepareExecutionMutation,
  useListAgentInstancesQuery,
  useGetAgentInstanceQuery,
  useCreateAgentInstanceMutation,
  useUpdateAgentInstanceMutation,
  useDeleteAgentInstanceMutation,
  useSpaceAgentTemplatesQuery,
  useAuthorizeSpaceMutation,
  useOrganizationSupervisionQuery,
  useTeamSupervisionQuery,
  useOrganizationModelsQuery,
  useOrganizationModelPolicyQuery,
  useReplaceOrganizationModelPolicyMutation,
  useRefreshModelSourceMutation,
  useOrganizationAgentsQuery,
  useSetOrganizationAgentDefaultMutation,
  useOrganizationCapabilitiesQuery,
  useRefreshOrganizationCapabilitiesMutation,
  useSetOrganizationCapabilityDefaultMutation,
  useLazyOrganizationCapabilityRevokeImpactQuery,
  useStartMutation,
  useSetRetrievableMutation,
  useLazyPreviewQuery,
  useEntriesQuery,
  useLazyEntriesQuery,
  useSummaryQuery,
  usePreflightMutation,
  useImportBlueprintMutation,
  useOrganizationRegistryQuery,
  useSearchOrganizationCandidatesQuery,
  useCreateOrganizationMutation,
  useGetOrganizationQuery,
  useUpdateOrganizationMutation,
  useCreateFolderMutation,
  useRenameFolderMutation,
  useDeleteFolderMutation,
  useDeleteDocumentMutation,
  useMeQuery,
  useMySpacesQuery,
  useCreatePersonalSpaceMutation,
  useOnboardingStatusQuery,
  useAcceptTermsMutation,
  useBootstrapPlatformAdminMutation,
} = enhancedControlPlaneApi;
