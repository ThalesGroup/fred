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
    getKnowledgeContexts: builder.query<KnowledgeContext[], { tag: string }>({
      query: ({ tag }) => ({
        url: `/knowledge-flow/v1/knowledgeContexts?tag=${encodeURIComponent(tag)}`,
        method: "GET",
      }),
    }),

    createKnowledgeContext: builder.mutation<KnowledgeContext, {
      title: string;
      description: string;
      files: File[];
      tag: string;
      fileDescriptions?: Record<string, string>;
    }>({
      query: ({ title, description, files, tag, fileDescriptions = {} }) => {
        const formData = new FormData();
        formData.append("title", title);
        formData.append("description", description);
        formData.append("tag", tag);

        files.forEach(file => {
          formData.append("files", file);
        });

        formData.append("file_descriptions", JSON.stringify(fileDescriptions));

        return {
          url: `/knowledge-flow/v1/knowledgeContexts`,
          method: "POST",
          body: formData,
        };
      },
    }),


    updateKnowledgeContext: builder.mutation<KnowledgeContext, {
      knowledgeContext_id: string;
      title: string;
      description: string;
      files?: File[];
      documentsDescription?: Record<string, string>;
    }>({
      query: ({ knowledgeContext_id, title, description, files, documentsDescription }) => {
        const formData = new FormData();
        formData.append("title", title);
        formData.append("description", description);

        files?.forEach(file => {
          formData.append("files", file);
        });

        if (documentsDescription && Object.keys(documentsDescription).length > 0) {
          formData.append("documents_description", JSON.stringify(documentsDescription));
        }
        
        return {
          url: `/knowledge-flow/v1/knowledgeContexts/${knowledgeContext_id}`,
          method: "PUT",
          body: formData,
        };
      },
    }),


    deleteKnowledgeContext: builder.mutation<{ success: boolean }, { knowledgeContext_id: string }>({
      query: ({ knowledgeContext_id }) => ({
        url: `/knowledge-flow/v1/knowledgeContexts/${knowledgeContext_id}`,
        method: "DELETE",
      }),
    }),

    deleteKnowledgeContextDocument: builder.mutation<{ success: boolean }, { knowledgeContext_id: string; document_id: string }>({
      query: ({ knowledgeContext_id, document_id }) => ({
        url: `/knowledge-flow/v1/knowledgeContexts/${knowledgeContext_id}/documents/${document_id}`,
        method: "DELETE",
      }),
    }),
  }),
});

export const {
  useLazyGetKnowledgeContextsQuery,
  useCreateKnowledgeContextMutation,
  useUpdateKnowledgeContextMutation,
  useDeleteKnowledgeContextMutation,
  useDeleteKnowledgeContextDocumentMutation,
} = knowledgeContextApiEndpoints;