import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../common/dynamicBaseQuery";
import { Workspace } from "../components/workspace/WorkspaceEditDialog";

export const workspaceApiSlice = createApi({
  reducerPath: "workspaceApi",
  baseQuery: createDynamicBaseQuery({ backend: "knowledge" }),
  endpoints: () => ({}),
});

export const { reducer: chatApiReducer, middleware: chatApiMiddleware } = workspaceApiSlice;

const workspaceApiEndpoints = workspaceApiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getWorkspaces: builder.mutation<Workspace[], void>({
      query: () => ({
        url: `/knowledge/v1/chatProfiles`,
        method: "GET",
      }),
    }),

    createWorkspace: builder.mutation<Workspace, {
      title: string;
      description: string;
      files: File[];
    }>({
      query: ({ title, description, files }) => {
        const formData = new FormData();
        formData.append("title", title);
        formData.append("description", description);
        files.forEach(file => {
          formData.append("files", file);
        });

        return {
          url: `/knowledge/v1/chatProfiles`,
          method: "POST",
          body: formData,
        };
      },
    }),

    updateWorkspace: builder.mutation<Workspace, { workspace_id: string; title: string; description: string; files?: File[] }>({
      query: ({ workspace_id, title, description, files }) => {
        const formData = new FormData();
        formData.append("title", title);
        formData.append("description", description);

        files?.forEach(file => {
          formData.append("files", file);
        });

        console.log(formData)
        return {
          url: `/knowledge/v1/chatProfiles/${workspace_id}`,
          method: "PUT",
          body: formData,
        };
      },
    }),

    deleteWorkspace: builder.mutation<{ success: boolean }, { workspace_id: string }>({
      query: ({ workspace_id }) => ({
        url: `/knowledge/v1/chatProfiles/${workspace_id}`,
        method: "DELETE",
      }),
    }),

    deleteWorkspaceDocument: builder.mutation<{ success: boolean }, { workspace_id: string; document_id: string }>({
      query: ({ workspace_id, document_id }) => ({
        url: `/knowledge/v1/chatProfiles/${workspace_id}/documents/${document_id}`,
        method: "DELETE",
      }),
    }),
  }),
});

export const {
  useGetWorkspacesMutation,
  useCreateWorkspaceMutation,
  useUpdateWorkspaceMutation,
  useDeleteWorkspaceMutation,
  useDeleteWorkspaceDocumentMutation,
} = workspaceApiEndpoints;