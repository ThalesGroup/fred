// Copyright Thales 2025
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

import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../common/dynamicBaseQuery.tsx";
import { Metadata } from "../components/documents/DocumentTable.tsx";

export const DOCUMENT_PROCESSING_STAGES = [
  "raw",
  "preview",
  "vector",
  "sql",
  "mcp",
] as const;
export interface KnowledgeDocument {
  document_name: string;
  document_uid: string;
  date_added_to_kb: string;
  ingestion_type: "push" | "pull"; // or broader if other types exist
  retrievable: boolean;
  source_tag: string | null;
  pull_location: string | null;
  source_type: string | null;
  tags: string[];
  title: string;
  author: string;
  created: string;
  modified: string;
  last_modified_by: string;
  category: string;
  subject: string;
  keywords: string;
  processing_stages: Partial<Record<DocumentProcessingStage, "not_started" | "in_progress" | "done" | "failed">>;
}

export interface DocumentSourceInfo {
  tag: string;
  type: "push" | "pull";
  provider?: string; // only for pull
  description: string;
  catalog_supported?: boolean;
}
export interface PullFileEntry {
  path: string;
  name: string;
  size: number;
  modified: string;
  metadata: KnowledgeDocument | null;
}
export type DocumentProcessingStage = typeof DOCUMENT_PROCESSING_STAGES[number];

export interface MarkdownDocumentPreview {
  content: string;
}

export const documentApiSlice = createApi({
  reducerPath: "documentApi",
  baseQuery: createDynamicBaseQuery({ backend: "knowledge" }),
  endpoints: () => ({}),
});
export const { reducer: documentApiReducer, middleware: documenApiMiddleware } = documentApiSlice;
const extendedDocumentApi = documentApiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getDocumentMarkdownPreview: builder.mutation<MarkdownDocumentPreview, { document_uid: string }>({
      query: ({ document_uid }) => ({
        url: `/knowledge-flow/v1/markdown/${document_uid}`,
        method: "GET",
      }),
    }),
    getDocumentSources: builder.query<DocumentSourceInfo[], void>({
      query: () => ({
        url: `/knowledge-flow/v1/documents/sources`,
        method: "GET",
      }),
    }),
    getCatalogFiles: builder.query<PullFileEntry[], { source_tag: string; offset?: number; limit?: number }>({
      query: ({ source_tag, offset = 0, limit = 100 }) => ({
        url: `/knowledge-flow/v1/catalog/files`,
        method: "GET",
        params: { source_tag, offset, limit },
      }),
    }),
    getDocumentRawContent: builder.query<Blob, { document_uid: string }>({
      query: ({ document_uid }) => ({
        url: `/knowledge-flow/v1/raw_content/${document_uid}`,
        method: "GET",
        responseHandler: async (response) => await response.blob(),
      }),
    }),
    getDocumentMetadata: builder.mutation<Metadata, { document_uid: string }>({
      query: ({ document_uid }) => ({
        url: `/knowledge-flow/v1/document/${document_uid}`,
        method: "GET",
      }),
    }),
    browseDocuments: builder.mutation<{ documents: KnowledgeDocument[]; total: number }, {
  source_tag: string;
  filters?: Record<string, any>;
  offset?: number;
  limit?: number;
}>({
  query: ({ source_tag, filters = {}, offset = 0, limit = 100 }) => ({
    url: "/knowledge-flow/v1/documents/browse",
    method: "POST",
    body: {
      source_tag,
      filters,
      offset,
      limit,
    },
  }),
}),
    getDocumentsWithFilter: builder.mutation<{ documents: KnowledgeDocument[] }, Record<string, any>>({
      query: (filters) => ({
        url: `/knowledge-flow/v1/documents/metadata`, // Single endpoint
        method: "POST",
        body: filters ?? {}, // If filters are undefined, send empty object
      }),
    }),
    updateDocumentRetrievable: builder.mutation<void, { document_uid: string; retrievable: boolean }>({
      query: ({ document_uid, retrievable }) => ({
        url: `/knowledge-flow/v1/document/${document_uid}`,
        method: "PUT",
        body: { retrievable },
      }),
    }),
    deleteDocument: builder.mutation<void, string>({
      query: (documentUid) => ({
        url: `/knowledge-flow/v1/document/${documentUid}`,
        method: "DELETE",
      }),
    }),
  }),
});

export const {
  useGetDocumentMetadataMutation,
  useUpdateDocumentRetrievableMutation,
  useGetDocumentsWithFilterMutation,
  useDeleteDocumentMutation,
  useGetDocumentMarkdownPreviewMutation,
  useLazyGetDocumentRawContentQuery,
  useGetDocumentSourcesQuery,
  useGetCatalogFilesQuery,
  useBrowseDocumentsMutation
} = extendedDocumentApi;
