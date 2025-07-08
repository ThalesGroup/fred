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

export interface KnowledgeDocument {
  document_uid: string;
  document_name: string;
  date_added_to_kb?: string;
  retrievable?: boolean;
  front_metadata?: {
    [key: string]: any;
  };
  [key: string]: any; // If your metadata is flexible
}

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
} = extendedDocumentApi;
