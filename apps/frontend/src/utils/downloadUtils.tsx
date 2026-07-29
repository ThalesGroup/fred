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

import JSZip from "jszip";
import { KeyCloakService } from "../security/KeycloakService";

/**
 * Downloads a file by creating a temporary link and clicking it
 */
export const downloadFile = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "document";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

/**
 * Authenticated fetch → Blob, without saving — the building block shared by
 * `downloadAuthed` (single file) and `downloadManyAsZip` (bulk: every file
 * needs its own blob before they can be zipped together).
 *
 * Workspace files are proxied through Knowledge Flow and the `/fs/download` route
 * requires authentication — a plain anchor navigation carries no token and fails.
 */
export const fetchAuthedBlob = async (url: string): Promise<Blob> => {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
  });
  if (!response.ok) {
    throw new Error(`Download failed (${response.status})`);
  }
  return response.blob();
};

/**
 * Authenticated download: fetch a (session-protected) URL with the live Bearer
 * token, then save the response as a blob.
 *
 * This is the single place that turns a protected URL into a saved file; both the
 * Resources file browser and agent-produced artifact links go through it.
 */
export const downloadAuthed = async (url: string, filename: string): Promise<void> => {
  downloadFile(await fetchAuthedBlob(url), filename);
};

export interface DownloadableFile {
  filename: string;
  fetchBlob: () => Promise<Blob>;
}

/** Appends " (2)", " (3)"... before the extension until `used` no longer has the name. */
function uniqueName(filename: string, used: Set<string>): string {
  if (!used.has(filename)) return filename;
  const dot = filename.lastIndexOf(".");
  const base = dot > 0 ? filename.slice(0, dot) : filename;
  const ext = dot > 0 ? filename.slice(dot) : "";
  let n = 2;
  let candidate = `${base} (${n})${ext}`;
  while (used.has(candidate)) {
    n += 1;
    candidate = `${base} (${n})${ext}`;
  }
  return candidate;
}

/**
 * Downloads one file directly; zips 2+ files into a single archive.
 *
 * Client-side only (jszip) — every blob fully round-trips through the
 * browser before zipping, no streaming, no backend involvement. Fine for
 * today's typical selection sizes; revisit with a server-side
 * streaming-zip endpoint if usage shows many/large files being
 * bulk-downloaded regularly (RFC `KNOWLEDGE-WORKSPACE-REWORK-RFC.md` §13.13).
 */
export async function downloadManyAsZip(files: DownloadableFile[], zipFilename: string): Promise<void> {
  if (files.length === 0) return;
  if (files.length === 1) {
    downloadFile(await files[0].fetchBlob(), files[0].filename);
    return;
  }
  const zip = new JSZip();
  const blobs = await Promise.all(files.map((f) => f.fetchBlob()));
  const usedNames = new Set<string>();
  files.forEach((f, i) => {
    const name = uniqueName(f.filename, usedNames);
    usedNames.add(name);
    zip.file(name, blobs[i]);
  });
  downloadFile(await zip.generateAsync({ type: "blob" }), zipFilename);
}
