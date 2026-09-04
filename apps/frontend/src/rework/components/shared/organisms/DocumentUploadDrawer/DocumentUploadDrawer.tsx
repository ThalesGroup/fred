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

import { useEffect, useMemo, useState } from "react";
import { useDispatch } from "react-redux";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "react-i18next";
import { Portal } from "@shared/utils/Portal";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Select from "@shared/molecules/Select/Select";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import UploadWarningBanner from "@shared/molecules/UploadWarningBanner/UploadWarningBanner";
import { formatBytes } from "@shared/utils/formatBytes";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import {
  leafFileName,
  streamUploadOrProcessDocument,
  type ScheduledTask,
} from "../../../../../slices/streamDocumentUpload";
import {
  IngestionProcessingProfile,
  useQuotaPrecheckKnowledgeFlowV1QuotaPrecheckPostMutation,
  type QuotaPrecheckResponse,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useGetTeamQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { OptionModel } from "@models/Option.model";
import { taskRegistered } from "../../../../features/tasks/taskSlice";
import {
  MAX_FOLDER_DEPTH,
  displayPath,
  exceedsMaxFolderDepth,
  folderPathDepth,
  relativeDirSegments,
} from "./droppedPaths";
import styles from "./DocumentUploadDrawer.module.css";

interface DocumentUploadDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadComplete?: () => void;
  metadata?: Record<string, unknown>;
  teamId?: string;
  /** Destination folder path shown prominently in the header, e.g. "CIR" or "CIR/Sub". */
  destinationPath?: string;
  /** Files picked before the drawer opened (dropped on a folder row) — seeded into the
   * list on open so the user only has to choose mode/profile and save. */
  initialFiles?: File[];
  /** Resolves (creating tags as needed) the nested folder chain `segments` under the
   * upload destination and returns the tag id files in that folder attach to — how a
   * dropped directory keeps its on-disk structure as nested corpus tags. Owned by the
   * caller (it knows the tag tree); absent => structure is ignored and every file
   * lands flat in the destination folder, the historical behavior. */
  ensureFolderPath?: (segments: string[]) => Promise<string | null>;
  /** Destination with no tag of its own (the corpus root): every file must sit
   * inside a dropped folder — its chain becomes the file's library — because a
   * loose file would upload tagless and be invisible in the corpus. Loose
   * files are filtered out of the list (with a toast when it happens). */
  requireFolderPerFile?: boolean;
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
        markDone(filename);
      },
      markDone,
    )
      .then(() => settle())
      .catch((err) => {
        // Some files may already have an outcome (reported above, as their
        // lines streamed in) even though the request as a whole then failed
        // — only the ones still pending were never accounted for.
        if (pendingLeafNames.size > 0) {
          onBackgroundError(err instanceof Error ? err.message : String(err));
        }
        settle();
      });
  });
}

// Bounds how many batched upload requests (and their ReBAC/quota checks) run
// at once, and how many files each request carries.
const UPLOAD_BATCH_SIZE = 8;
const UPLOAD_CONCURRENCY = 4;

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

export function DocumentUploadDrawer({
  isOpen,
  onClose,
  onUploadComplete,
  metadata,
  teamId,
  destinationPath,
  initialFiles,
  ensureFolderPath,
  requireFolderPerFile,
}: DocumentUploadDrawerProps) {
  const { t } = useTranslation();
  const { showError } = useToast();

  const dispatch = useDispatch();
  const [uploadMode, setUploadMode] = useState<"upload" | "process">("process");
  const [profile, setProfile] = useState<IngestionProcessingProfile>("fast");

  const uploadModeOptions = useMemo<OptionModel<"upload" | "process">[]>(
    () => [
      { key: "upload", value: "upload", label: t("documentLibrary.uploadOnly") },
      { key: "process", value: "process", label: t("documentLibrary.uploadAndProcess") },
    ],
    [t],
  );
  const profileOptions = useMemo<OptionModel<IngestionProcessingProfile>[]>(
    () => [
      {
        key: "fast",
        value: "fast",
        label: t("documentLibrary.profileFast"),
        description: t("documentLibrary.profileFastDesc"),
      },
      {
        key: "medium",
        value: "medium",
        label: t("documentLibrary.profileMedium"),
        description: t("documentLibrary.profileMediumDesc"),
      },
      {
        key: "rich",
        value: "rich",
        label: t("documentLibrary.profileRich"),
        description: t("documentLibrary.profileRichDesc"),
      },
    ],
    [t],
  );
  const [files, setFiles] = useState<File[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Depth guardrail (#2355): destination folder + a file's own subdirectory
  // chain may not exceed MAX_FOLDER_DEPTH — the backend rejects the mirrored
  // tag chain past that cap, so too-deep files are filtered out up front.
  const destinationDepth = folderPathDepth(destinationPath);
  const withinDepth = (f: File) => !exceedsMaxFolderDepth(f, destinationDepth);

  // Seed on open only: `files` stays local state afterwards (user can still add
  // or remove entries), and closing resets it via handleClose as usual. The
  // caller already filters loose/too-deep files out of a drop seed — the
  // filters here are for any other opener.
  useEffect(() => {
    if (isOpen && initialFiles?.length) {
      const seeded = requireFolderPerFile
        ? initialFiles.filter((f) => relativeDirSegments(f).length > 0)
        : initialFiles;
      setFiles(seeded.filter(withinDepth));
    }
    // withinDepth derives from destinationPath, stable while the drawer is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, initialFiles, requireFolderPerFile, destinationPath]);

  const resolvedTeamId = teamId ?? "personal";
  const { data: team } = useGetTeamQuery({ teamId: resolvedTeamId });
  const { canUpdateResources: canSelectProfile } = useTeamCapabilities(team);

  const newFilesSize = useMemo(() => files.reduce((acc, f) => acc + f.size, 0), [files]);

  // Distinct subdirectories carried by the listed files (a dropped folder) that
  // saving will mirror as nested corpus tags — 0 when the list is flat or when
  // the caller provided no ensureFolderPath (structure is then ignored).
  const nestedDirCount = useMemo(() => {
    if (!ensureFolderPath) return 0;
    return new Set(files.map((f) => relativeDirSegments(f).join("/")).filter(Boolean)).size;
  }, [files, ensureFolderPath]);

  // Server-side quota verdict for the CURRENT batch (#2360), asked at Save
  // time with the declared sizes — one authoritative answer for team AND
  // personal quotas, replacing the old client-side team-only computation. A
  // denial keeps the drawer open with the server's numbers; editing the list
  // clears it (the next Save re-asks).
  const [quotaDenial, setQuotaDenial] = useState<QuotaPrecheckResponse | null>(null);
  const [quotaPrecheck] = useQuotaPrecheckKnowledgeFlowV1QuotaPrecheckPostMutation();
  useEffect(() => setQuotaDenial(null), [files]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    // Keyboard-accessible: the dropzone root becomes focusable (tabIndex) and
    // Enter/Space opens the file dialog (react-dropzone), so adding files no
    // longer depends on a mouse/drag. Focus-visible styling lives in the CSS.
    onDrop: (accepted) => {
      const foldered = requireFolderPerFile ? accepted.filter((f) => relativeDirSegments(f).length > 0) : accepted;
      if (foldered.length < accepted.length) {
        showError?.({
          summary: t("documentLibrary.uploadDrawerTitle"),
          detail: t("documentLibrary.folderRequired"),
        });
      }
      const usable = foldered.filter(withinDepth);
      if (usable.length < foldered.length) {
        showError?.({
          summary: t("documentLibrary.tooDeepTitle"),
          detail: t("documentLibrary.tooDeepSkipped", {
            count: foldered.length - usable.length,
            max: MAX_FOLDER_DEPTH,
          }),
        });
      }
      setFiles((prev) => {
        const existing = new Set(prev.map((f) => `${f.name}-${f.size}-${f.lastModified}`));
        return [...prev, ...usable.filter((f) => !existing.has(`${f.name}-${f.size}-${f.lastModified}`))];
      });
    },
  });

  const handleRemove = (index: number) => setFiles((prev) => prev.filter((_, i) => i !== index));

  const handleClose = () => {
    setFiles([]);
    setIsLoading(false);
    onClose();
  };

  const handleSave = async () => {
    if (!files.length || isLoading) return;
    setIsLoading(true);
    // Quota precheck FIRST (#2360): one request with the batch's declared
    // total rejects the whole batch before any tag is created or any byte
    // uploaded — including against the personal quota, which the client
    // cannot see. Advisory only: the upload endpoints re-check against the
    // actually-received sizes, so a precheck transport error falls through
    // to the save rather than blocking it.
    try {
      const verdict = await quotaPrecheck({
        quotaPrecheckRequest: {
          tags: (metadata?.tags as string[] | undefined) ?? [],
          team_id: resolvedTeamId,
          total_size: newFilesSize,
        },
      }).unwrap();
      if (!verdict.allowed) {
        setQuotaDenial(verdict);
        setIsLoading(false);
        return;
      }
    } catch {
      // Precheck unavailable — let the enforcement path answer.
    }
    // Each file's subdirectory key, computed once and reused below both to
    // resolve folder tags and to group files by destination.
    const dirKeyByFile = new Map<File, string>();
    const dirSegmentsByFile = new Map<File, string[]>();
    for (const file of files) {
      const segments = relativeDirSegments(file);
      dirSegmentsByFile.set(file, segments);
      dirKeyByFile.set(file, segments.join("/"));
    }

    // Mirror a dropped folder's structure first: one tag chain per distinct
    // subdirectory, resolved before any upload starts so a failed/forbidden tag
    // creation aborts the save with nothing half-uploaded (the drawer stays open
    // for a retry). Sequential on purpose — sibling chains share parent
    // prefixes, which the caller's resolver caches between calls.
    const tagIdByDir = new Map<string, string | null>();
    if (ensureFolderPath) {
      const chains = new Map<string, string[]>();
      for (const file of files) {
        const key = dirKeyByFile.get(file)!;
        if (key) chains.set(key, dirSegmentsByFile.get(file)!);
      }
      try {
        for (const [key, segments] of chains) tagIdByDir.set(key, await ensureFolderPath(segments));
      } catch (err) {
        setIsLoading(false);
        showError?.({
          summary: t("documentLibrary.uploadDrawerTitle"),
          detail: err instanceof Error ? err.message : String(err),
        });
        return;
      }
    }
    try {
      // Group files that share the same destination tags into batches (same
      // request metadata => one request can carry several files, see
      // scheduleFiles' doc comment), then run those batches through a bounded
      // pool rather than firing one request per file unbounded.
      const base = canSelectProfile ? { ...(metadata ?? {}), profile } : { ...(metadata ?? {}) };
      const groups = new Map<string, { requestMetadata: Record<string, unknown>; files: File[] }>();
      for (const file of files) {
        // A file inside a dropped subdirectory attaches to that subdirectory's
        // tag instead of the destination folder's (`base` keeps the latter).
        const dirTagId = tagIdByDir.get(dirKeyByFile.get(file)!);
        const requestMetadata = dirTagId ? { ...base, tags: [dirTagId] } : base;
        const groupKey = dirTagId ?? "";
        const group = groups.get(groupKey);
        if (group) group.files.push(file);
        else groups.set(groupKey, { requestMetadata, files: [file] });
      }

      const batches: { requestMetadata: Record<string, unknown>; files: File[] }[] = [];
      for (const group of groups.values()) {
        for (const batchFiles of chunkFilesByLeafName(group.files, UPLOAD_BATCH_SIZE)) {
          batches.push({ requestMetadata: group.requestMetadata, files: batchFiles });
        }
      }

      // Register each task the instant the server first reports its id (its own
      // line in the stream), not after the whole batch finishes — so the tray
      // lights up and starts its SSE subscription while the upload streams.
      await runWithConcurrencyLimit(batches, UPLOAD_CONCURRENCY, (batch) =>
        scheduleFiles(
          batch.files,
          uploadMode,
          batch.requestMetadata,
          ({ taskId, documentUid, filename }) => {
            dispatch(
              taskRegistered({
                taskId,
                kind: "ingestion",
                target: documentUid ? { type: "document", id: documentUid, label: filename } : null,
              }),
            );
          },
          (message) => showError?.({ summary: t("documentLibrary.uploadDrawerTitle"), detail: message }),
        ),
      );
      onUploadComplete?.();
    } finally {
      setIsLoading(false);
      handleClose();
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // handleClose only resets local state + calls onClose; a stale closure is harmless.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={handleClose}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="upload-modal-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.header}>
            <div>
              <p id="upload-modal-title" className={styles.title}>
                {t("documentLibrary.uploadDrawerTitle")}
              </p>
              {destinationPath && (
                <p className={styles.destination}>
                  <span className={styles.destinationIcon} aria-hidden>
                    <Icon category="outlined" type="folder" />
                  </span>
                  {t("documentLibrary.uploadDestination")}
                  <code className={styles.path}>{destinationPath}</code>
                </p>
              )}
            </div>
            <IconButton
              variant="icon"
              size="2xs"
              icon={{ category: "outlined", type: "close" }}
              aria-label={t("common.close")}
              onClick={handleClose}
            />
          </div>
          <div className={styles.body}>
            <UploadWarningBanner />
            <div className={styles.field}>
              <label className={styles.label}>{t("documentLibrary.ingestionMode")}</label>
              <Select<"upload" | "process">
                options={uploadModeOptions}
                value={uploadMode}
                onChange={setUploadMode}
                size="small"
              />
            </div>

            {canSelectProfile && (
              <div className={styles.field}>
                <label className={styles.label}>{t("documentLibrary.processingProfile")}</label>
                <Select<IngestionProcessingProfile>
                  options={profileOptions}
                  value={profile}
                  onChange={setProfile}
                  size="small"
                />
              </div>
            )}

            <div
              {...getRootProps()}
              className={styles.dropzone}
              data-active={isDragActive}
              data-filled={files.length > 0}
            >
              <input {...getInputProps()} />
              {files.length === 0 ? (
                <div className={styles.dropzoneEmpty}>
                  <span className={styles.dropzoneIcon} aria-hidden>
                    <Icon category="outlined" type="upload" />
                  </span>
                  <span className={styles.dropzoneHint}>{t("documentLibrary.dropFiles")}</span>
                  <span className={styles.dropzoneCaption}>{t("documentLibrary.maxSize")}</span>
                </div>
              ) : (
                <ul className={styles.fileList}>
                  {files.map((f, i) => (
                    <li key={`${f.name}-${i}`} className={styles.fileRow}>
                      <span className={styles.fileName} title={displayPath(f)}>
                        {displayPath(f)}
                      </span>
                      <span className={styles.fileSize}>{formatBytes(f.size)}</span>
                      <IconButton
                        variant="icon"
                        size="2xs"
                        icon={{ category: "outlined", type: "close" }}
                        aria-label={`Remove ${f.name}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemove(i);
                        }}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {nestedDirCount > 0 && (
              <p className={styles.formatsCaption}>
                {t("documentLibrary.nestedFoldersHint", { count: nestedDirCount })}
              </p>
            )}

            <p className={styles.formatsCaption}>{t("documentLibrary.supportedFormats")}</p>

            {quotaDenial && (
              <div className={styles.quotaWarning} role="alert">
                <strong className={styles.quotaTitle}>{t("documentLibrary.storageQuotaExceededTitle")}</strong>
                <p className={styles.quotaMessage}>{t("documentLibrary.storageQuotaExceededMessage")}</p>
                <div className={styles.quotaRow}>
                  <span>
                    {t("documentLibrary.currentUsage")} <strong>{formatBytes(quotaDenial.current ?? 0)}</strong>
                  </span>
                  <span>
                    {t("documentLibrary.limit")} <strong>{formatBytes(quotaDenial.limit ?? 0)}</strong>
                  </span>
                </div>
                <div className={styles.quotaRow}>
                  <span>
                    {t("documentLibrary.newFilesSize")} <strong>{formatBytes(newFilesSize)}</strong>
                  </span>
                  <span className={styles.quotaExcess}>
                    {t("documentLibrary.excessSize")}{" "}
                    {formatBytes((quotaDenial.current ?? 0) + newFilesSize - (quotaDenial.limit ?? 0))}
                  </span>
                </div>
              </div>
            )}
          </div>
          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="small" onClick={handleClose}>
              {t("documentLibrary.cancel")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="small"
              onClick={handleSave}
              disabled={!files.length || isLoading || !!quotaDenial}
            >
              {isLoading ? t("documentLibrary.saving") : t("documentLibrary.save")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
