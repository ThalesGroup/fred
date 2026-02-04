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

// NOT GENERATED. Safe to edit.
import { knowledgeFlowApi as api } from "./knowledgeFlowApi";

export const blobApi = api.injectEndpoints({
  endpoints: (build) => ({
    // Raw file download as Blob
    downloadRawContentBlob: build.query<Blob, { documentUid: string }>({
      query: ({ documentUid }) => ({
        url: `/knowledge-flow/v1/raw_content/${documentUid}`,
        // Force Blob at runtime
        responseHandler: (response) => response.blob(),
      }),
    }),

    // Markdown media file as Blob
    downloadMarkdownMediaBlob: build.query<Blob, { documentUid: string; mediaId: string }>({
      query: ({ documentUid, mediaId }) => ({
        url: `/knowledge-flow/v1/markdown/${documentUid}/media/${mediaId}`,
        responseHandler: (response) => response.blob(),
      }),
    }),

    // User asset download as Blob (supports optional explicit owner header)
    downloadUserAssetBlob: build.query<Blob, { key: string; assetOwnerId?: string }>({
      query: ({ key, assetOwnerId }) => ({
        url: `/knowledge-flow/v1/user-assets/${key}`,
        headers: assetOwnerId ? { "X-Asset-User-ID": assetOwnerId } : undefined,
        responseHandler: (response) => response.blob(),
      }),
    }),

    // Generic download by absolute URL (workspace assets, config, etc.)
    downloadHrefBlob: build.query<Blob, { href: string; assetOwnerId?: string }>({
      query: ({ href, assetOwnerId }) => ({
        url: href, // absolute URL allowed by fetchBaseQuery
        headers: assetOwnerId ? { "X-Asset-User-ID": assetOwnerId } : undefined,
        responseHandler: (response) => response.blob(),
      }),
    }),
  }),
  overrideExisting: false,
});

export const {
  useLazyDownloadRawContentBlobQuery,
  useDownloadRawContentBlobQuery,
  useLazyDownloadMarkdownMediaBlobQuery,
  useDownloadMarkdownMediaBlobQuery,
  useLazyDownloadUserAssetBlobQuery,
  useDownloadUserAssetBlobQuery,
  useLazyDownloadHrefBlobQuery,
  useDownloadHrefBlobQuery,
} = blobApi;
