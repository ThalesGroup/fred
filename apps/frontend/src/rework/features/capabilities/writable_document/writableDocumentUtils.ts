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

// Small pure helpers shared across the writable_document feature (slice, merge
// hook, download button) so the "newest updated_at wins" tie-break and the
// export filename rule live in exactly one place (DRY).

/** Parse an ISO timestamp to epoch ms; 0 when missing/invalid (treated as oldest). */
export const tsMs = (updatedAt?: string | null): number => {
  if (!updatedAt) return 0;
  const t = Date.parse(updatedAt);
  return Number.isNaN(t) ? 0 : t;
};

/** Make a safe, non-empty filename stem from a document title (mirrors the backend). */
export const sanitizeFilename = (name: string): string =>
  name
    .replace(/[^\w\-. ]+/g, "")
    .trim()
    .replace(/\s+/g, "_") || "document";

/** Word is an actual owner-provided export; arbitrary suffixes do not change the content type. */
export const writableExportFormat = (title: string): "docx" | "md" => (/\.docx$/i.test(title) ? "docx" : "md");
export const exportFilename = (title: string, format: "docx" | "md"): string =>
  `${sanitizeFilename(title.replace(/\.(md|docx)$/i, ""))}.${format}`;
export const writableFilename = (title: string): string => exportFilename(title, writableExportFormat(title));
