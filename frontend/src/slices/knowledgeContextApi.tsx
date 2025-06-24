import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../common/dynamicBaseQuery";
import { KnowledgeContext } from "../components/knowledgeContext/KnowledgeContextEditDialog";

export const knowledgeContextApiSlice = createApi({
  reducerPath: "knowledgeContextApi",
  baseQuery: createDynamicBaseQuery({ backend: "knowledge" }),
  endpoints: () => ({}),
});

export const { reducer: chatApiReducer, middleware: chatApiMiddleware } = knowledgeContextApiSlice;

const knowledgeContextApiEndpoints = knowledgeContextApiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getKnowledgeContexts: builder.mutation<KnowledgeContext[], void>({
      query: () => ({
        url: `/knowledge/v1/knowledgeContexts`,
        method: "GET",
      }),
    }),

    createKnowledgeContext: builder.mutation<KnowledgeContext, {
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
          url: `/knowledge/v1/knowledgeContexts`,
          method: "POST",
          body: formData,
        };
      },
    }),

    updateKnowledgeContext: builder.mutation<KnowledgeContext, { knowledgeContext_id: string; title: string; description: string; files?: File[] }>({
      query: ({ knowledgeContext_id, title, description, files }) => {
        const formData = new FormData();
        formData.append("title", title);
        formData.append("description", description);

        files?.forEach(file => {
          formData.append("files", file);
        });

        console.log(formData)
        return {
          url: `/knowledge/v1/knowledgeContexts/${knowledgeContext_id}`,
          method: "PUT",
          body: formData,
        };
      },
    }),

    deleteKnowledgeContext: builder.mutation<{ success: boolean }, { knowledgeContext_id: string }>({
      query: ({ knowledgeContext_id }) => ({
        url: `/knowledge/v1/knowledgeContexts/${knowledgeContext_id}`,
        method: "DELETE",
      }),
    }),

    deleteKnowledgeContextDocument: builder.mutation<{ success: boolean }, { knowledgeContext_id: string; document_id: string }>({
      query: ({ knowledgeContext_id, document_id }) => ({
        url: `/knowledge/v1/knowledgeContexts/${knowledgeContext_id}/documents/${document_id}`,
        method: "DELETE",
      }),
    }),
  }),
});

export const {
  useGetKnowledgeContextsMutation,
  useCreateKnowledgeContextMutation,
  useUpdateKnowledgeContextMutation,
  useDeleteKnowledgeContextMutation,
  useDeleteKnowledgeContextDocumentMutation,
} = knowledgeContextApiEndpoints;