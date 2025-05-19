import { createApi } from '@reduxjs/toolkit/query/react';
import { Metadata } from '../components/documents/DocumentCard.tsx';
import { createDynamicBaseQuery } from '../common/dynamicBaseQuery.tsx';

export interface KnowledgeDocument {
  document_uid: string;
  document_name: string;
  date_added_to_kb?: string;
  retrievable?: boolean;
  front_metadata?: {
    agent_name?: string;
    [key: string]: any;
  };
  [key: string]: any; // If your metadata is flexible
}

export interface MarkdownDocumentPreview {
  content: string;
}

export const documentApiSlice = createApi({
  reducerPath: 'documentApi',
  baseQuery: createDynamicBaseQuery({ backend: "knowledge" }),
  endpoints: () => ({}),
});
export const { reducer: documentApiReducer, middleware: documenApiMiddleware } = documentApiSlice;
const extendedDocumentApi = documentApiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getDocumentMarkdownPreview: builder.mutation<MarkdownDocumentPreview, { document_uid: string }>({
      query: ({ document_uid }) => ({
        url: `/knowledge/v1/markdown/${document_uid}`,
        method: 'GET',
      }),
    }),
    getDocumentRawContent: builder.query<Blob, { document_uid: string }>({
      query: ({ document_uid }) => ({
        url: `/knowledge/v1/raw_content/${document_uid}`,
        method: 'GET',
        responseHandler: async (response) => await response.blob(),
      }),
    }),
    getDocumentMetadata: builder.mutation<Metadata, { document_uid: string }>({
      query: ({ document_uid }) => ({
        url: `/knowledge/v1/document/${document_uid}`,
        method: 'GET',
      }),
    }),
    getDocumentsWithFilter: builder.mutation<{ documents: KnowledgeDocument[] }, Record<string, any>>({
      query: (filters) => ({
        url: `/knowledge/v1/documents/metadata`, // Single endpoint
        method: 'POST',
        body: filters ?? {}, // If filters are undefined, send empty object
      }),
    }),
    putDocumentMetadata: builder.mutation<Metadata, { document_uid: string; metadata: Metadata }>({
      query: ({ document_uid, metadata }) => ({
        url: `/knowledge/v1/document/${document_uid}`,
        method: 'PUT',
        body: metadata,
      }),
    }),
    deleteDocument: builder.mutation<void, string>({
      query: (documentUid) => ({
        url: `/knowledge/v1/document/${documentUid}`,
        method: "DELETE",
      }),
    }),
  }),
});

export const {
  useGetDocumentMetadataMutation,
  usePutDocumentMetadataMutation,
  useGetDocumentsWithFilterMutation,
  useDeleteDocumentMutation,
  useGetDocumentMarkdownPreviewMutation,
  useLazyGetDocumentRawContentQuery,
} = extendedDocumentApi;
