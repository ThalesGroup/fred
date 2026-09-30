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

// Carrying out an import, and retrying a file that did not make it.
//
// This lives outside the dialog on purpose: the dialog is gone long before the
// transfer is, and the panel — not the dialog — is where a failed file is
// retried from. Nothing here touches React.

import type { Dispatch } from "@reduxjs/toolkit";
import { v4 as uuidv4 } from "uuid";
import { leafFileName, streamUploadOrProcessDocument, type ScheduledTask } from "../../../slices/streamDocumentUpload";
import {
  importPanelOpenRequested,
  taskEvicted,
  uploadConflicted,
  uploadFailed,
  uploadFinished,
  uploadHandedOff,
  uploadStarted,
} from "../tasks/taskSlice";
import type { ConflictDecision } from "../../components/shared/organisms/DocumentUploadDrawer/importConflicts";

export type UploadMode = "upload" | "process";

export interface ImportBatch {
  requestMetadata: Record<string, unknown>;
  files: File[];
}

/**
 * Resolves once every file in `files` has an outcome (task_id, reported
 * failure, or plain success) — resolving on just the first would let the
 * drawer close/refresh while the rest of the batch is still unaccounted for.
 * Each outcome still fires its callback as its own line streams in, so the
 * tray/toast never waits on the slowest file. A mid-stream transport failure
 * reports whatever's still pending too, so it isn't silently dropped. Pass
 * files sharing `requestMetadata` (see streamUploadOrProcessDocument).
 */
export function scheduleFiles(
  files: File[],
  uploadMode: "upload" | "process",
  requestMetadata: Record<string, unknown>,
  onDiscovered: (task: ScheduledTask) => void,
  onBackgroundError: (message: string) => void,
  onConflicted?: (filename: string) => void,
  /** Per-file end of the transfer, for the panel entry that is following it.
   *  Separate from `onBackgroundError`, whose job is to raise a toast: one is
   *  about a file, the other about telling the user. */
  uploadOutcome?: { onFailed: (filename: string, message: string) => void; onFinished: (filename: string) => void },
): Promise<void> {
  return new Promise<void>((resolve) => {
    let settled = false;
    const pendingLeafNames = new Set(files.map(leafFileName));
    const settle = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    const markDone = (filename: string) => {
      pendingLeafNames.delete(filename);
      if (pendingLeafNames.size === 0) settle();
    };

    streamUploadOrProcessDocument(
      files,
      uploadMode,
      requestMetadata,
      (task) => {
        onDiscovered(task);
        markDone(task.filename);
      },
      (filename, message) => {
        onBackgroundError(`${filename}: ${message}`);
        uploadOutcome?.onFailed(filename, message);
        markDone(filename);
      },
      (filename) => {
        uploadOutcome?.onFinished(filename);
        markDone(filename);
      },
      (filename) => {
        onConflicted?.(filename);
        markDone(filename);
      },
    )
      .then(() => settle())
      .catch((err) => {
        // Some files may already have an outcome (reported above, as their
        // lines streamed in) even though the request as a whole then failed
        // — only the ones still pending were never accounted for.
        if (pendingLeafNames.size > 0) {
          const message = err instanceof Error ? err.message : String(err);
          onBackgroundError(message);
          // Without this each unaccounted file would sit in the panel as
          // "sending" forever: nothing else will ever report on it.
          for (const filename of pendingLeafNames) uploadOutcome?.onFailed(filename, message);
        }
        settle();
      });
  });
}

// Bounds how many batched upload requests (and their ReBAC/quota checks) run
// at once, and how many files each request carries.
export const UPLOAD_BATCH_SIZE = 8;
export const UPLOAD_CONCURRENCY = 4;

/** Runs `worker` over `items` with at most `limit` calls in flight at once. */
export async function runWithConcurrencyLimit<T>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<void>,
): Promise<void> {
  let next = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const item = items[next++];
      await worker(item);
    }
  });
  await Promise.all(runners);
}

/** Splits `files` into batches of at most `maxSize`, never putting two files
 * with the same leaf name in the same batch — the backend correlates a
 * batch's progress lines by that leaf name, so a collision would make two
 * files' outcomes indistinguishable within one request. */
export function chunkFilesByLeafName(files: File[], maxSize: number): File[][] {
  const leafNames = files.map(leafFileName);
  const hasCollision = new Set(leafNames).size !== leafNames.length;
  if (!hasCollision) {
    // The common case — a drop rarely repeats a filename — is a plain O(n)
    // slice; the collision-safe grouping below is only needed when it does.
    const batches: File[][] = [];
    for (let i = 0; i < files.length; i += maxSize) batches.push(files.slice(i, i + maxSize));
    return batches;
  }

  const batches: File[][] = [];
  let remaining = files;
  while (remaining.length) {
    const batch: File[] = [];
    const leftover: File[] = [];
    const namesInBatch = new Set<string>();
    for (const file of remaining) {
      const leafName = leafFileName(file);
      if (batch.length < maxSize && !namesInBatch.has(leafName)) {
        batch.push(file);
        namesInBatch.add(leafName);
      } else {
        leftover.push(file);
      }
    }
    batches.push(batch);
    remaining = leftover;
  }
  return batches;
}

// ── Files we can still send again ────────────────────────────────────────────
//
// A `File` is a handle on something on disk, not its bytes, so holding one for
// a failed entry costs next to nothing — and it is the only way a retry can
// work at all: the browser cannot re-read a file it no longer holds. Cleared
// the moment the file is no longer ours to send (accepted by the server,
// settled, or dismissed), and gone entirely on reload, which is exactly when a
// retry stops being possible and the panel has to say so.

interface HeldImport {
  file: File;
  filename: string;
  uploadMode: UploadMode;
  requestMetadata: Record<string, unknown>;
}

const heldImports = new Map<string, HeldImport>();

/** The file behind a panel entry, if the browser still holds it. */
export function heldImport(entryId: string): HeldImport | undefined {
  return heldImports.get(entryId);
}

export function releaseHeldImport(entryId: string): void {
  heldImports.delete(entryId);
}

/** Test seam only — the vault is module state and outlives a component tree. */
export function clearHeldImports(): void {
  heldImports.clear();
}

export interface ImportRunHandlers {
  dispatch: Dispatch;
  uploadMode: UploadMode;
  /** Raise a notification. Called for transfer errors, with a message already
   *  naming the file where one is known. */
  onError: (message: string) => void;
  onComplete?: () => void;
}

/**
 * Carries out an import, reporting every file to the store as it goes.
 *
 * Detached by design: the caller does not await it, and nothing here holds a
 * reference to the component that started it.
 */
export async function runImport(batches: ImportBatch[], handlers: ImportRunHandlers): Promise<void> {
  const { dispatch, uploadMode, onError, onComplete } = handlers;

  // Every file is listed before a byte moves. Waiting for its own transfer to
  // end would leave most of a large import invisible: batches run a few at a
  // time, so the last files are queued for minutes with nothing on screen
  // saying they exist.
  const runId = uuidv4();
  const indexed = batches.map((batch, batchIndex) => ({ ...batch, batchIndex }));
  const localIdOf = (batchIndex: number, filename: string) => `import-${runId}-${batchIndex}-${filename}`;
  for (const batch of indexed) {
    for (const file of batch.files) {
      const filename = leafFileName(file);
      const localId = localIdOf(batch.batchIndex, filename);
      heldImports.set(localId, { file, filename, uploadMode, requestMetadata: batch.requestMetadata });
      dispatch(uploadStarted({ localId, filename }));
    }
  }

  try {
    await runWithConcurrencyLimit(indexed, UPLOAD_CONCURRENCY, (batch) =>
      sendBatch(batch.files, batch.requestMetadata, (filename) => localIdOf(batch.batchIndex, filename), {
        dispatch,
        uploadMode,
        onError,
      }),
    );
  } finally {
    onComplete?.();
  }
}

/**
 * Sends one failed file again, under the same entry it already has in the
 * panel, with the mode and destination it was first sent with.
 *
 * Returns false when the browser no longer holds the file — after a reload,
 * typically — so the caller can say the file has to be picked again rather
 * than offering a retry that cannot work.
 */
export async function retryImport(
  entryId: string,
  handlers: Pick<ImportRunHandlers, "dispatch" | "onError"> & { onComplete?: () => void },
): Promise<boolean> {
  const held = heldImports.get(entryId);
  if (!held) return false;
  const { dispatch, onError, onComplete } = handlers;

  dispatch(uploadStarted({ localId: entryId, filename: held.filename }));
  try {
    await sendBatch([held.file], held.requestMetadata, () => entryId, {
      dispatch,
      uploadMode: held.uploadMode,
      onError,
    });
  } finally {
    onComplete?.();
  }
  return true;
}

/** One request's worth of files, with every per-file outcome routed to the
 *  store entry that is following it. */
function sendBatch(
  files: File[],
  requestMetadata: Record<string, unknown>,
  entryIdOf: (filename: string) => string,
  handlers: {
    dispatch: Dispatch;
    uploadMode: UploadMode;
    onError: (message: string) => void;
  },
): Promise<void> {
  const { dispatch, uploadMode, onError } = handlers;
  const destinationTag = ((requestMetadata.tags as string[] | undefined) ?? [])[0] ?? null;
  return scheduleFiles(
    files,
    uploadMode,
    requestMetadata,
    ({ taskId, documentUid, filename }) => {
      // The server has the bytes now, so we no longer need to be able to
      // re-send them; whatever happens next is the task's to report.
      releaseHeldImport(entryIdOf(filename));
      dispatch(uploadHandedOff({ localId: entryIdOf(filename), taskId, documentUid, filename }));
    },
    onError,
    (filename) => {
      // Deliberately keeps the held file: answering "replace" means sending it
      // again, and only the browser has it.
      dispatch(uploadConflicted({ localId: entryIdOf(filename), tagId: destinationTag, filename }));
      // The question is only a question if it is seen. A panel the user closed
      // in the meantime opens itself again.
      dispatch(importPanelOpenRequested());
    },
    {
      // Deliberately keeps the held file: this is the one case a retry exists for.
      onFailed: (filename, error) => dispatch(uploadFailed({ localId: entryIdOf(filename), error })),
      // Only reached by a file that never got a task — upload-only mode, or one
      // the server skipped. Anything with a task is that task's to finish, and
      // the transfer ending says nothing about it.
      onFinished: (filename) => {
        releaseHeldImport(entryIdOf(filename));
        dispatch(uploadFinished({ localId: entryIdOf(filename) }));
      },
    },
  );
}

/**
 * Applies the user's answer to a name the folder took while the file was on
 * its way.
 *
 * `skip` sends nothing — the whole point of the question is not to transfer
 * bytes the answer makes useless — and the entry goes away. `overwrite` sends
 * the same file again, to the same folder, with the decision attached so the
 * server replaces the document that is there.
 *
 * Returns false when the browser no longer holds the file, so the caller can
 * say the import has to be started again rather than offering an answer that
 * cannot be applied.
 */
export async function resolveConflict(
  entryId: string,
  decision: ConflictDecision,
  handlers: Pick<ImportRunHandlers, "dispatch" | "onError"> & { onComplete?: () => void },
): Promise<boolean> {
  const held = heldImports.get(entryId);
  if (!held) return false;
  const { dispatch, onError, onComplete } = handlers;

  if (decision === "skip") {
    releaseHeldImport(entryId);
    dispatch(taskEvicted(entryId));
    return true;
  }

  const requestMetadata = {
    ...held.requestMetadata,
    conflict_decisions: { ...((held.requestMetadata.conflict_decisions as object) ?? {}), [held.filename]: decision },
  };
  dispatch(uploadStarted({ localId: entryId, filename: held.filename }));
  try {
    await sendBatch([held.file], requestMetadata, () => entryId, {
      dispatch,
      uploadMode: held.uploadMode,
      onError,
    });
  } finally {
    onComplete?.();
  }
  return true;
}
