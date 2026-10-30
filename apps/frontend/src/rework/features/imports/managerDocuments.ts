// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type { Document, FailureCode, StorageSummary, Summary } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { KeyCloakService } from "../../../security/KeycloakService";
import { handlePlatformAccessResponse } from "../../../common/platformAccess";
import { downloadFile } from "../../../utils/downloadUtils";
import { managerActor } from "./managerImportRun";

export type ResourceDocument = Document & { processing?: Summary };
export function presentManagerDocument(document: Document, processing?: Summary): ResourceDocument {
  return { ...document, processing };
}
/** Display buckets, aggregated from Control Plane MIME usage. */
export type ResourceUsageBucket = { bucket: string; count: number; size_bytes: number };
const processingFailureKeys = {
  unsupported_input: "unsupported_input",
  access_changed: "access_changed",
  integrity_failure: "integrity_failure",
  extraction_failed: "extraction_failed",
  preview_failed: "preview_failed",
  indexing_failed: "indexing_failed",
  capacity_exceeded: "capacity_exceeded",
  worker_failed: "worker_failed",
  deadline_exceeded: "deadline_exceeded",
  delivery_unknown: "delivery_unknown",
} satisfies Record<FailureCode, string>;
/** Only stable server codes are presented; diagnostic payloads never become HTML. */
export function managerProcessingFailure(code: string | null | undefined, t: (key: string) => string) {
  const key =
    code && Object.prototype.hasOwnProperty.call(processingFailureKeys, code)
      ? processingFailureKeys[code as FailureCode]
      : "worker_failed";
  return t(`rework.documentStorage.processingErrors.${key}`);
}
export function managerProcessingErrors(processing: Summary | undefined, t: (key: string) => string) {
  if (processing?.status !== "failed") return undefined;
  return { [processing.stage]: managerProcessingFailure(processing.error_code, t) };
}
export function managerTypeStats(summary?: StorageSummary): ResourceUsageBucket[] | undefined {
  if (!summary) return undefined;
  const buckets = new Map<string, ResourceUsageBucket>();
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
    const response = await fetch(`/control-plane/v1/documents/${encodeURIComponent(document.id)}/content`, {
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
