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

// Binary access to the session's Word document (capability router):
// `/sessions/{id}/document.docx` and `/sessions/{id}/preview.pdf`.
//
// Sanctioned raw-fetch exception (CLAUDE.md "generated API client"): both
// routes stream bytes the generated RTK Query hooks cannot surface as a Blob.
// The JSON route (`getWordTemplateSession`) goes through the generated hook.

import { KeyCloakService } from "../../../../security/KeycloakService";
import type { WordTemplateSessionResponse } from "./api/wordTemplateCapabilityOpenApi";

/** A failed binary fetch: HTTP status + the backend's FastAPI `detail`. */
export interface WordTemplateFetchError {
  message: string;
  status?: number;
  detail?: string;
}

/** What the pane tells the user, keyed under `capability.word_template.preview.error.*`. */
export type WordTemplateErrorKind =
  | "noDocument"
  | "templateUnavailable"
  | "editsNotApplicable"
  | "conversion"
  | "generic";

/**
 * Map a failed fetch to a message kind. 404 = no document yet in this
 * conversation; a 409 says WHICH conflict only through its `detail`
 * (template not retrievable vs. edits that cannot be replayed); 502 = the
 * PDF conversion (the pod's LibreOffice helper) failed.
 */
export function wordTemplateErrorKind(error: Pick<WordTemplateFetchError, "status" | "detail">): WordTemplateErrorKind {
  if (error.status === 404) return "noDocument";
  if (error.status === 409) {
    return error.detail?.includes("could not be applied") ? "editsNotApplicable" : "templateUnavailable";
  }
  if (error.status === 502) return "conversion";
  return "generic";
}

/**
 * The preview's refetch key: changes whenever the agent records an edit
 * batch. `null` while the session has no document (nothing to preview).
 */
export function previewVersionKey(session: WordTemplateSessionResponse | undefined): string | null {
  const base = session?.base_ref ?? session?.template_key;
  if (!session || !base) return null;
  return `${session.base_kind ?? "template"}:${base}:${session.edit_count ?? 0}:${session.updated_at ?? ""}`;
}

/** The attached file's name when the document is built on one, else null. */
export function attachedBaseFilename(session: WordTemplateSessionResponse | undefined): string | null {
  if (session?.base_kind !== "attachment") return null;
  return session.base_filename || session.base_ref || null;
}

/** GET one of the session's binary routes with the live bearer. Throws a
 *  `WordTemplateFetchError`-shaped Error on a non-OK response. */
export async function fetchSessionBinary(params: {
  baseUrl: string;
  sessionId: string;
  file: "document.docx" | "preview.pdf";
  signal?: AbortSignal;
}): Promise<Blob> {
  const { baseUrl, sessionId, file, signal } = params;
  const res = await fetch(`${baseUrl}/sessions/${encodeURIComponent(sessionId)}/${file}`, {
    cache: "no-store",
    signal,
    headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string" ? body.detail : undefined;
    throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status, detail });
  }
  return res.blob();
}

/** Download the session's .docx (client-side blob save). */
export async function downloadSessionDocx(baseUrl: string, sessionId: string, fileName: string): Promise<void> {
  const blob = await fetchSessionBinary({ baseUrl, sessionId, file: "document.docx" });
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
