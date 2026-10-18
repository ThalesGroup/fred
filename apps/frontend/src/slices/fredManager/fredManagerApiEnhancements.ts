// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { fredManagerApi } from "./fredManagerOpenApi";

// The generator types binary fields as Blob, but sends the enclosing object as
// JSON. Adapt only the transport; URL, method, arguments and result stay generated.
export const enhancedFredManagerApi = fredManagerApi.enhanceEndpoints({
  addTagTypes: ["Folders"],
  endpoints: {
    createOrganization: { extraOptions: { retryUnauthorized: false } },
    listFolders: { providesTags: ["Folders"] },
    createFolder: { extraOptions: { retryUnauthorized: false }, invalidatesTags: ["Folders"] },
    renameFolder: { extraOptions: { retryUnauthorized: false }, invalidatesTags: ["Folders"] },
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
  useImportBlueprintMutation,
  useOrganizationRegistryQuery,
  useCreateOrganizationMutation,
  useCreateFolderMutation,
  useListFoldersQuery,
  useRenameFolderMutation,
  useDeleteFolderMutation,
  useMeQuery,
  useMySpacesQuery,
  useCreatePersonalSpaceMutation,
  useOnboardingStatusQuery,
  useAcceptTermsMutation,
  useBootstrapPlatformAdminMutation,
} = enhancedFredManagerApi;
