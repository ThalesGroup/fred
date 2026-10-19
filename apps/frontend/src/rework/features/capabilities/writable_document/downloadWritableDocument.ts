// Copyright Thales 2026
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

// Authenticated binary download for a writable document's export route.
//
// This is the sanctioned narrow exception to "consume the generated client" (see
// CLAUDE.md): the export endpoint returns a binary StreamingResponse, which the
// generated RTK Query hook cannot surface as a Blob cleanly. So we fetch the bytes
// WITH the live Keycloak bearer (same token source as capabilityBaseQuery) against
// the capability's own base URL, then trigger a client-side blob save — mirroring
// the ppt_filler `downloadAuthed` pattern. The FORMAT type is still imported from
// the generated client; only the transport is hand-written.

import { downloadAuthed } from "../../../../common/downloadAuthed";
import type { WritableDocumentExportFormat } from "./api/writableDocumentCapabilityOpenApi";
import { sanitizeFilename } from "./writableDocumentUtils";

const EXTENSION: Record<WritableDocumentExportFormat, string> = { docx: "docx", md: "md" };

/**
 * Fetch one document's export in `format` from the capability's `baseUrl` and save
 * it as `<sanitized title>.<ext>`. Throws on a non-OK response so the caller can toast.
 */
export async function downloadWritableDocument(params: {
  /** The capability's ingress-relative base URL (selectCapabilityBaseUrl). */
  baseUrl: string;
  sessionId: string;
  documentId: string;
  format: WritableDocumentExportFormat;
  title: string;
}): Promise<void> {
  const { baseUrl, sessionId, documentId, format, title } = params;
  const url = `${baseUrl}/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(
    documentId,
  )}/export?format=${format}`;

  await downloadAuthed(url, `${sanitizeFilename(title)}.${EXTENSION[format]}`);
}
