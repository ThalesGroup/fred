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
  }),
  overrideExisting: false,
});

export const {
  useLazyDownloadRawContentBlobQuery,
  useDownloadRawContentBlobQuery,
  useLazyDownloadMarkdownMediaBlobQuery,
  useDownloadMarkdownMediaBlobQuery,
} = blobApi;
