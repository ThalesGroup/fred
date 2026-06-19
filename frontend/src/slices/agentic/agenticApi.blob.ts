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
// Raw blob downloads for the agentic backend (e.g. writable-document Word export).
import { agenticApi as api } from "./agenticApi";

// Supported export formats for writable documents. Extend as the backend gains formats.
export type ExportWritableDocumentFormat = "docx";

export const agenticBlobApi = api.injectEndpoints({
  endpoints: (build) => ({
    // Export a writable document as a Word (.docx) Blob.
    exportWritableDocumentBlob: build.query<
      Blob,
      { sessionId: string; documentId: string; format?: ExportWritableDocumentFormat }
    >({
      query: ({ sessionId, documentId, format = "docx" }) => ({
        url: `/agentic/v1/writable-documents/${sessionId}/${documentId}/export`,
        params: { format },
        responseHandler: (response) => response.blob(),
      }),
    }),
  }),
  overrideExisting: false,
});

export const { useLazyExportWritableDocumentBlobQuery } = agenticBlobApi;
