// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { KeyCloakService } from "../../../security/KeycloakService";
import { enhancedControlPlaneApi as api } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { UploadReceipt, Profile, Summary } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type { store } from "../../../common/store";

export type ManagerDispatch = typeof store.dispatch;
export type ImportPhase = "queued" | "uploading" | "uncertain" | "failed" | "stored";
export interface ManagerImport {
  key: string;
  spaceId: string;
  folderId: string;
  name: string;
  size: number;
  createdAt: number;
  phase: ImportPhase;
  error?: string;
  receipt?: UploadReceipt;
  retryOf?: string;
  profile?: Profile;
}
const MAX_ENTRIES = 500;
const TTL = 7 * 24 * 60 * 60 * 1000;
const listeners = new Set<() => void>();
const files = new Map<string, File>();
const active = new Set<string>();
const retrying = new Set<string>();
const capacityWaiters = new Set<() => void>();
const checkedAt = new Map<string, number>();
const cursors = new Map<string, { before: string; beforeKey: string }>();
function releaseCapacity() {
  capacityWaiters.forEach((resolve) => resolve());
  capacityWaiters.clear();
}
let owner = "";
let entries: ManagerImport[] = [];

export const managerActor = () =>
  KeyCloakService.GetSessionIdentity?.() ??
  JSON.stringify([KeyCloakService.GetTokenParsed?.()?.iss ?? "", KeyCloakService.GetUserId?.()]);
const storageKey = (actor: string) => `fred.manager.imports:${actor}`;
function current() {
  const actor = managerActor();
  if (owner === actor) return;
  owner = actor;
  files.clear();
  active.clear();
  retrying.clear();
  checkedAt.clear();
  cursors.clear();
  releaseCapacity();
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(storageKey(actor)) ?? "[]");
    entries = Array.isArray(saved)
      ? saved
          .filter(
            (e): e is ManagerImport =>
              e &&
              typeof e.key === "string" &&
              typeof e.spaceId === "string" &&
              typeof e.folderId === "string" &&
              typeof e.name === "string" &&
              typeof e.size === "number" &&
              e.createdAt > Date.now() - TTL,
          )
          .slice(0, MAX_ENTRIES)
          .map((e) => ({ ...e, phase: "uncertain", receipt: undefined }))
      : [];
  } catch {
    entries = [];
  }
}
export function managerImportsSnapshot() {
  current();
  return entries;
}
export function subscribeManagerImports(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
function changed(actor: string, next: ManagerImport[]) {
  current();
  if (owner !== actor) return;
  entries = next;
  try {
    localStorage.setItem(storageKey(actor), JSON.stringify(entries));
  } catch {
    /* Receipts still recover accepted transfers. */
  }
  listeners.forEach((listener) => listener());
}
function patch(actor: string, key: string, values: Partial<ManagerImport>) {
  changed(
    actor,
    entries.map((e) => (e.key === key ? { ...e, ...values } : e)),
  );
}
function remove(actor: string, key: string) {
  if (managerActor() !== actor) return;
  files.delete(key);
  changed(
    actor,
    entries.filter((e) => e.key !== key),
  );
}
function record(actor: string, receipt: UploadReceipt) {
  if (managerActor() !== actor) return;
  const key = receipt.request_key;
  const phase = receipt.status === "pending" ? (active.has(key) ? "uploading" : "uncertain") : receipt.status;
  const value: ManagerImport = {
    key,
    spaceId: receipt.space_id,
    folderId: receipt.folder_id,
    name: receipt.name,
    size: receipt.size,
    createdAt: new Date(receipt.created_at).getTime(),
    phase,
    receipt,
    error: receipt.processing?.error_code ?? receipt.error_code ?? undefined,
    profile: receipt.processing_profile ?? undefined,
  };
  const old = entries.find((e) => e.key === key);
  if (old?.receipt?.status === "stored" && receipt.status !== "stored") return;
  if (
    old?.receipt?.processing &&
    (!receipt.processing || Date.parse(old.receipt.processing.created_at) > Date.parse(receipt.processing.created_at))
  )
    return;
  if (
    old?.receipt?.processing?.id === receipt.processing?.id &&
    (old?.receipt?.processing?.revision ?? -1) > (receipt.processing?.revision ?? -1)
  )
    return;
  if (
    (receipt.acknowledged_at && !["pending", "running"].includes(receipt.processing?.status ?? "")) ||
    receipt.successor_key
  ) {
    remove(actor, key);
    return;
  }
  if (old) patch(actor, key, value);
  else if (entries.length < MAX_ENTRIES) changed(actor, [...entries, value]);
  if (phase === "stored") files.delete(key);
}
const errorStatus = (error: unknown) => (error as { status?: number })?.status;
const errorText = (error: unknown) => (error as { data?: { code?: string } })?.data?.code ?? "storage_unavailable";

async function lookup(dispatch: ManagerDispatch, actor: string, key: string): Promise<UploadReceipt | null> {
  const request = dispatch(api.endpoints.receipt.initiate({ id: key }, { subscribe: false, forceRefetch: true }));
  try {
    const receipt = await request.unwrap();
    if (managerActor() !== actor) throw new Error("Account changed");
    const discovered = receipt.status === "stored" && entries.find((entry) => entry.key === key)?.phase !== "stored";
    record(actor, receipt);
    if (discovered) dispatch(api.util.invalidateTags(["Documents"]));
    return receipt;
  } catch (error) {
    if (managerActor() === actor && errorStatus(error) === 404) return null;
    throw error;
  }
}

/** Server receipts are authoritative; local records also cover bytes not yet reserved. */
export async function refreshManagerImports(dispatch: ManagerDispatch, spaceId: string) {
  current();
  const actor = owner;
  const page = async (cursor?: { before: string; beforeKey: string }) =>
    dispatch(
      api.endpoints.receipts.initiate({ id: spaceId, limit: 200, ...cursor }, { subscribe: false, forceRefetch: true }),
    ).unwrap();
  const latest = await page();
  if (managerActor() !== actor) return;
  const cursor = cursors.get(spaceId);
  // One current page plus at most one older page per poll. Scan older receipts
  // even after loss of browser storage; acknowledged rows disappear server-side.
  const older = cursor ? await page(cursor) : latest;
  if (managerActor() !== actor) return;
  const last = older[older.length - 1];
  if (older.length === 200 && last) cursors.set(spaceId, { before: last.created_at, beforeKey: last.request_key });
  else cursors.delete(spaceId);
  const receipts = cursor ? [...latest, ...older] : latest;
  const known = new Set(receipts.map((r) => r.request_key));
  const discovered = receipts.some(
    (r) => r.status === "stored" && entries.find((e) => e.key === r.request_key)?.phase !== "stored",
  );
  receipts.forEach((r) => {
    checkedAt.set(r.request_key, Date.now());
    record(actor, r);
  });
  if (discovered) dispatch(api.util.invalidateTags(["Documents"]));
  // Resolve local-only outcomes fairly, without a request per retained entry on
  // every poll. Queued File objects have not been sent and remain cancellable.
  const missing = entries
    .filter(
      (e) =>
        e.spaceId === spaceId &&
        !known.has(e.key) &&
        !active.has(e.key) &&
        !(e.phase === "queued" && files.has(e.key)) &&
        Date.now() - (checkedAt.get(e.key) ?? 0) >= 30_000,
    )
    .sort((a, b) => (checkedAt.get(a.key) ?? 0) - (checkedAt.get(b.key) ?? 0))
    .slice(0, 8);
  await pool(missing, 4, async (entry) => {
    checkedAt.set(entry.key, Date.now());
    try {
      if (!(await lookup(dispatch, actor, entry.key)))
        patch(actor, entry.key, { phase: "failed", error: "interrupted_before_send" });
    } catch {
      patch(actor, entry.key, { phase: "uncertain", error: "storage_unavailable" });
    }
  });
}

async function pool<T>(items: T[], count: number, run: (item: T) => Promise<void>) {
  let index = 0;
  await Promise.all(
    Array.from({ length: Math.min(count, items.length) }, async () => {
      while (index < items.length) await run(items[index++]);
    }),
  );
}

async function send(dispatch: ManagerDispatch, actor: string, entry: ManagerImport) {
  if (managerActor() !== actor || !entries.some((e) => e.key === entry.key)) return;
  while (active.size >= 3 && managerActor() === actor)
    await new Promise<void>((resolve) => capacityWaiters.add(resolve));
  if (managerActor() !== actor || !entries.some((e) => e.key === entry.key)) return;
  const file = files.get(entry.key);
  if (!file) return;
  active.add(entry.key);
  patch(actor, entry.key, { phase: "uploading", error: undefined });
  try {
    const receipt = await dispatch(
      api.endpoints.upload.initiate({
        id: entry.folderId,
        "Idempotency-Key": entry.key,
        retryOf: entry.retryOf,
        profile: entry.profile,
        fileUpload: { file },
      }),
    ).unwrap();
    record(actor, receipt);
  } catch (error) {
    if (managerActor() !== actor) return;
    try {
      const receipt = await lookup(dispatch, actor, entry.key);
      if (!receipt) patch(actor, entry.key, { phase: "failed", error: errorText(error) });
    } catch {
      patch(actor, entry.key, { phase: "uncertain", error: errorText(error) });
    }
  } finally {
    if (managerActor() === actor) active.delete(entry.key);
    releaseCapacity();
    dispatch(api.util.invalidateTags(["Documents", "DocumentUploads"]));
  }
}

export function runManagerImport(
  dispatch: ManagerDispatch,
  spaceId: string,
  selected: { file: File; folderId: string }[],
  profile?: Profile,
) {
  current();
  const actor = owner;
  if (entries.length + selected.length > MAX_ENTRIES) throw new Error("import_capacity");
  const batch = selected.map(({ file, folderId }): ManagerImport => {
    const key = crypto.randomUUID();
    files.set(key, file);
    return {
      key,
      spaceId,
      folderId,
      name: file.name.normalize("NFC"),
      size: file.size,
      createdAt: Date.now(),
      phase: "queued",
      profile,
    };
  });
  changed(actor, [...entries, ...batch]);
  return pool(batch, 3, (entry) => send(dispatch, actor, entry));
}
export function managerFileHeld(key: string) {
  current();
  return files.has(key);
}
export function managerCanRetryWithoutFile(key: string) {
  current();
  return (
    files.has(key) ||
    entries.some((e) => e.key === key && e.receipt?.status === "stored" && e.receipt.processing?.status === "failed")
  );
}
export function canCancelManagerImport(key: string) {
  current();
  return entries.find((e) => e.key === key)?.phase === "queued" && !active.has(key);
}
export function cancelManagerImport(key: string) {
  if (!canCancelManagerImport(key)) return false;
  remove(owner, key);
  return true;
}

/** Resolve ambiguity before resending. A failed receipt gets exactly one successor. */
export async function retryManagerImport(dispatch: ManagerDispatch, key: string, picked?: File) {
  current();
  const actor = owner;
  if (active.has(key) || retrying.has(key)) return;
  const entry = entries.find((e) => e.key === key);
  if (!entry) return;
  retrying.add(key);
  try {
    let receipt = await lookup(dispatch, actor, key);
    if (receipt?.successor_key) {
      receipt = await lookup(dispatch, actor, receipt.successor_key);
      return;
    }
    if (receipt?.status === "stored" && receipt.document_id && receipt.processing?.status === "failed") {
      await startManagerProcessing(dispatch, receipt.document_id, receipt.processing.profile, receipt.processing);
      await lookup(dispatch, actor, key);
      return;
    }
    if (receipt && receipt.status !== "failed") return;
    const file = picked ?? files.get(key);
    if (!file) throw new Error("reselect_file");
    if (file.name.normalize("NFC") !== entry.name || file.size !== entry.size) throw new Error("wrong_file");
    if (managerActor() !== actor) return;
    const retry = {
      ...entry,
      key: receipt ? crypto.randomUUID() : key,
      retryOf: receipt ? key : entry.retryOf,
      phase: "queued" as const,
      receipt: undefined,
      error: undefined,
    };
    files.set(retry.key, file);
    changed(actor, [...entries.filter((e) => e.key !== key), retry]);
    if (retry.key !== key) files.delete(key);
    await send(dispatch, actor, retry);
  } finally {
    if (managerActor() === actor) retrying.delete(key);
  }
}
export async function dismissManagerImport(dispatch: ManagerDispatch, key: string) {
  current();
  const actor = owner;
  if (active.has(key) || retrying.has(key)) throw new Error("upload_in_progress");
  const receipt = await lookup(dispatch, actor, key);
  if (receipt?.status === "pending") throw new Error("upload_in_progress");
  if (receipt) await dispatch(api.endpoints.acknowledge.initiate({ id: key })).unwrap();
  remove(actor, key);
}

/** Retry keys survive a lost response and a reload, without resending the original. */
export async function startManagerProcessing(
  dispatch: ManagerDispatch,
  documentId: string,
  profile: Profile,
  previous?: Summary | null,
) {
  const actor = managerActor();
  const storage = `fred.manager.processing:${actor}:${documentId}`;
  const binding = `${previous?.id ?? "initial"}:${profile}`;
  let key: string;
  {
    let saved: { binding?: string; key?: string } = {};
    try {
      saved = JSON.parse(localStorage.getItem(storage) ?? "{}");
    } catch {
      /* Ignore corrupted local hints. */
    }
    key = saved.binding === binding && saved.key ? saved.key : crypto.randomUUID();
    localStorage.setItem(storage, JSON.stringify({ binding, key }));
  }
  const result = await dispatch(
    api.endpoints.start.initiate({
      id: documentId,
      "Idempotency-Key": key,
      start: { profile, retry_of: previous?.id },
    }),
  ).unwrap();
  if (managerActor() !== actor) throw new Error("account_changed");
  return result;
}
