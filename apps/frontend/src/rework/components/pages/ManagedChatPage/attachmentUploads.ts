// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { enhancedControlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { UploadReceipt } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { managerActor, type ManagerDispatch } from "../../../features/imports/managerImportRun";

export interface AttachmentUpload {
  key: string;
  name: string;
  size: number;
  mime: string;
  phase: "uploading" | "uncertain" | "failed" | "stored";
  retryOf?: string;
  receipt?: UploadReceipt;
  error?: string;
  checkAfter?: number;
}
export interface UploadScope {
  actor: string;
  spaceId: string;
  sessionId: string;
  entries: AttachmentUpload[];
  listeners: Set<() => void>;
}
const scopes = new Map<string, UploadScope>();
const active = new Set<string>();
const storageKey = (scope: Pick<UploadScope, "actor" | "spaceId" | "sessionId">) =>
  `fred.conversation.uploads:${JSON.stringify([scope.actor, scope.spaceId, scope.sessionId])}`;

export function attachmentUploadScope(actor: string, spaceId: string, sessionId: string): UploadScope {
  const key = storageKey({ actor, spaceId, sessionId });
  const existing = scopes.get(key);
  if (existing) return existing;
  let entries: AttachmentUpload[] = [];
  try {
    const saved: AttachmentUpload[] = JSON.parse(localStorage.getItem(key) ?? "[]");
    entries = saved
      .filter((e) => typeof e.key === "string" && typeof e.name === "string")
      .map((e) => ({
        ...e,
        phase: e.phase === "uploading" ? "uncertain" : e.phase,
      }));
  } catch {
    // Local hints never replace the server list or receipts.
  }
  const scope = { actor, spaceId, sessionId, entries, listeners: new Set<() => void>() };
  scopes.set(key, scope);
  return scope;
}
function save(scope: UploadScope, entries: AttachmentUpload[], requireStorage = false) {
  try {
    localStorage.setItem(storageKey(scope), JSON.stringify(entries));
  } catch (error) {
    if (requireStorage) throw error;
  }
  scope.entries = entries;
  scope.listeners.forEach((listener) => listener());
}
function patch(scope: UploadScope, key: string, update: Partial<AttachmentUpload>) {
  save(
    scope,
    scope.entries.map((e) => (e.key === key ? { ...e, ...update } : e)),
  );
}
export function forgetAttachmentUpload(scope: UploadScope, key: string) {
  save(
    scope,
    scope.entries.filter((e) => e.key !== key),
  );
}
export const attachmentErrorCode = (error: unknown) =>
  (error as { data?: { code?: string } })?.data?.code ??
  (error instanceof Error ? error.message : "storage_unavailable");
function record(scope: UploadScope, key: string, receipt: UploadReceipt) {
  if (receipt.space_id !== scope.spaceId || receipt.session_id !== scope.sessionId)
    throw new Error("receipt_scope_mismatch");
  patch(scope, key, {
    receipt,
    phase: receipt.status === "pending" || receipt.successor_key ? "uncertain" : receipt.status,
    error: receipt.error_code ?? undefined,
  });
}
async function lookup(dispatch: ManagerDispatch, scope: UploadScope, key: string): Promise<UploadReceipt | null> {
  if (managerActor() !== scope.actor) throw new Error("account_changed");
  try {
    const receipt = await dispatch(
      api.endpoints.receipt.initiate({ id: key }, { subscribe: false, forceRefetch: true }),
    ).unwrap();
    if (managerActor() !== scope.actor) throw new Error("account_changed");
    record(scope, key, receipt);
    return receipt;
  } catch (error) {
    if ((error as { status?: number }).status === 404) return null;
    throw error;
  }
}
export async function refreshAttachmentUploads(dispatch: ManagerDispatch, scope: UploadScope) {
  for (const entry of scope.entries) {
    if (managerActor() !== scope.actor) return;
    if (entry.phase !== "uncertain" || (entry.checkAfter ?? 0) > Date.now() || active.has(entry.key)) continue;
    try {
      const receipt = await lookup(dispatch, scope, entry.key);
      // The server reserves only after receiving the bytes; a 404 is not a rejection.
      if (receipt?.successor_key) {
        const successor = await lookup(dispatch, scope, receipt.successor_key);
        if (successor) record(scope, entry.key, successor);
      }
    } catch (error) {
      if (managerActor() === scope.actor) patch(scope, entry.key, { error: attachmentErrorCode(error) });
    }
  }
}
async function send(dispatch: ManagerDispatch, scope: UploadScope, entry: AttachmentUpload, file: File) {
  if (managerActor() !== scope.actor) return;
  active.add(entry.key);
  try {
    const receipt = await dispatch(
      api.endpoints.uploadAttachment.initiate({
        spaceId: scope.spaceId,
        sessionId: scope.sessionId,
        "Idempotency-Key": entry.key,
        retryOf: entry.retryOf,
        fileUpload: { file },
      }),
    ).unwrap();
    if (managerActor() === scope.actor) record(scope, entry.key, receipt);
  } catch (error) {
    if (managerActor() !== scope.actor) return;
    const code = attachmentErrorCode(error);
    const status = (error as { status?: number }).status;
    const rejected =
      typeof status === "number" &&
      status >= 400 &&
      status < 500 &&
      status !== 408 &&
      !["upload_in_progress", "retry_superseded", "upload_failed"].includes(code);
    const retryAfter = (error as { retryAfter?: string }).retryAfter;
    const delay = retryAfter
      ? /^\d+$/.test(retryAfter)
        ? Number(retryAfter) * 1000
        : Date.parse(retryAfter) - Date.now()
      : 0;
    patch(scope, entry.key, {
      phase: rejected ? "failed" : "uncertain",
      error: code,
      checkAfter: Date.now() + Math.max(0, delay || 0),
    });
  } finally {
    active.delete(entry.key);
    if (managerActor() !== scope.actor) patch(scope, entry.key, { phase: "uncertain" });
  }
}
export async function uploadAttachments(dispatch: ManagerDispatch, scope: UploadScope, files: File[]) {
  const selected = files.filter((file) => file.size > 0);
  const batch = selected.map(
    (file): AttachmentUpload => ({
      key: crypto.randomUUID(),
      name: file.name.normalize("NFC"),
      size: file.size,
      mime: file.type,
      phase: "uploading",
    }),
  );
  // Persist keys before sending bytes. Failure to retain them rejects this upload.
  save(scope, [...scope.entries, ...batch], true);
  await Promise.all(batch.map((entry, index) => send(dispatch, scope, entry, selected[index])));
  await refreshAttachmentUploads(dispatch, scope);
}
export async function retryAttachmentUpload(dispatch: ManagerDispatch, scope: UploadScope, key: string, file: File) {
  const entry = scope.entries.find((e) => e.key === key);
  if (!entry || active.has(key) || (entry.checkAfter ?? 0) > Date.now()) return;
  active.add(key);
  try {
    const receipt = await lookup(dispatch, scope, entry.receipt?.request_key ?? key);
    if (receipt?.successor_key) {
      const successor = await lookup(dispatch, scope, receipt.successor_key);
      if (successor) record(scope, key, successor);
      return;
    }
    if (receipt && receipt.status !== "failed") return;
    if (file.name.normalize("NFC") !== entry.name || file.size !== entry.size) throw new Error("wrong_file");
    if (managerActor() !== scope.actor) return;
    const retry: AttachmentUpload = {
      ...entry,
      key: receipt ? crypto.randomUUID() : key,
      retryOf: receipt?.request_key ?? entry.retryOf,
      phase: "uploading",
      receipt: undefined,
      error: undefined,
    };
    save(
      scope,
      scope.entries.map((e) => (e.key === key ? retry : e)),
      true,
    );
    await send(dispatch, scope, retry, file);
  } finally {
    active.delete(key);
  }
}
