// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type { Document, StorageSummary } from "../../../slices/fredManager/fredManagerOpenApi";
import type { DocumentMetadata, ResourceTypeStatsEntry } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { KeyCloakService } from "../../../security/KeycloakService";
import { handlePlatformAccessResponse } from "../../../common/platformAccess";
import { downloadFile } from "../../../utils/downloadUtils";
import { managerActor } from "./managerImportRun";

export type ResourceDocument = DocumentMetadata & { managerDocument?: Document };
/** Presentation only: no tags, ingestion results or KF identifiers are synthesized. */
export function presentManagerDocument(document: Document): ResourceDocument {
  return {
    managerDocument: document,
    identity: { document_uid: document.id, document_name: document.name, uploaded_by: document.created_by },
    source: { source_type: "push", date_added_to_kb: document.created_at, retrievable: false },
    file: { file_size_bytes: document.size, mime_type: document.mime, sha256: document.sha256 },
    processing: { stages: {} },
  };
}
export function managerTypeStats(summary?: StorageSummary): ResourceTypeStatsEntry[] | undefined {
  if (!summary) return undefined;
  const buckets = new Map<string, ResourceTypeStatsEntry>();
  for (const row of summary.types) {
    const mime = row.mime.toLowerCase();
    const bucket = mime.includes("pdf")
      ? "pdf"
      : /presentation|powerpoint/.test(mime)
        ? "ppt"
        : /spreadsheet|excel|csv/.test(mime)
          ? "excel"
          : /text|word|document/.test(mime)
            ? "text"
            : "other";
    const value = buckets.get(bucket) ?? { bucket, count: 0, size_bytes: 0 };
    value.count += row.documents;
    value.size_bytes += row.bytes;
    buckets.set(bucket, value);
  }
  return [...buckets.values()];
}
const MAX_BYTES = 100 * 1024 * 1024;
let downloading = false;
/** One individual Blob at a time; the existing save helper owns the browser link. */
export async function downloadManagerDocument(document: Document): Promise<void> {
  if (downloading) throw new Error("download_busy");
  if (document.size < 0 || document.size > MAX_BYTES) throw new Error("file_too_large");
  downloading = true;
  const actor = managerActor();
  try {
    await KeyCloakService.ensureFreshToken(30);
    if (managerActor() !== actor) throw new Error("account_changed");
    const response = await fetch(`/fred-manager/v1/documents/${encodeURIComponent(document.id)}/content`, {
      headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
      cache: "no-store",
      signal: AbortSignal.timeout(610_000),
    });
    await handlePlatformAccessResponse(response);
    if (!response.ok) throw new Error(`download_failed_${response.status}`);
    if (Number(response.headers.get("content-length")) !== document.size) throw new Error("download_integrity_failure");
    const blob = await response.blob();
    if (blob.size !== document.size) throw new Error("download_integrity_failure");
    if (managerActor() === actor) downloadFile(blob, document.name);
  } finally {
    downloading = false;
  }
}
