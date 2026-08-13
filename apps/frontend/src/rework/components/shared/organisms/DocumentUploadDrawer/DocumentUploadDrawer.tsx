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
import { streamUploadOrProcessDocument, type ScheduledTask } from "../../../../../slices/streamDocumentUpload";
import { IngestionProcessingProfile } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
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
 * Waits only until `file` is scheduled (its task_id known, via `onDiscovered`) or
 * its request settles with no task at all (upload-only mode, or a failure before
 * any task existed) — never until the file's full ingestion pipeline finishes.
 * The underlying request keeps running in the background regardless; a later
 * failure is reported by the failed task in the tray (once a task_id existed) or
 * by `onBackgroundError` (if it failed before one ever did).
 */
export function scheduleFile(
  file: File,
  uploadMode: "upload" | "process",
  requestMetadata: Record<string, unknown>,
  onDiscovered: (task: ScheduledTask) => void,
  onBackgroundError: (message: string) => void,
): Promise<void> {
  return new Promise<void>((resolve) => {
    let settled = false;
    let taskDiscovered = false;
    const settle = () => {
      if (settled) return;
      settled = true;
      resolve();
    };

    streamUploadOrProcessDocument(file, uploadMode, requestMetadata, (task) => {
      taskDiscovered = true;
      onDiscovered(task);
      settle();
    })
      .then(() => settle())
      .catch((err) => {
        settle();
        // A task_id already known means the backend fails that task explicitly
        // (visible in the tray/Activity) — reporting it here too would double it up.
        // Only surface a toast for a failure that happened before any task existed.
        if (!taskDiscovered) {
          onBackgroundError(err instanceof Error ? err.message : String(err));
        }
      });
  });
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

  const isQuotaExceeded = useMemo(() => {
    if (!team) return false;
    const current = team.current_resources_storage_size ?? 0;
    const max = team.max_resources_storage_size ?? 0;
    if (max <= 0) return false;
    return current + newFilesSize > max;
  }, [team, newFilesSize]);

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
    if (!files.length || isLoading || isQuotaExceeded) return;
    setIsLoading(true);
    // Mirror a dropped folder's structure first: one tag chain per distinct
    // subdirectory, resolved before any upload starts so a failed/forbidden tag
    // creation aborts the save with nothing half-uploaded (the drawer stays open
    // for a retry). Sequential on purpose — sibling chains share parent
    // prefixes, which the caller's resolver caches between calls.
    const tagIdByDir = new Map<string, string | null>();
    if (ensureFolderPath) {
      const chains = new Map<string, string[]>();
      for (const file of files) {
        const segments = relativeDirSegments(file);
        if (segments.length) chains.set(segments.join("/"), segments);
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
      // Schedule every file concurrently rather than one-at-a-time: each
      // `scheduleFile` already only waits for its own task_id to be discovered
      // (see its doc comment), not the file's full ingestion pipeline, so a
      // batch should close as soon as the slowest single file is scheduled —
      // not after the sum of every file's upload time.
      await Promise.all(
        files.map((file) => {
          const base = canSelectProfile ? { ...(metadata ?? {}), profile } : { ...(metadata ?? {}) };
          // A file inside a dropped subdirectory attaches to that subdirectory's
          // tag instead of the destination folder's (`base` keeps the latter).
          const dirTagId = tagIdByDir.get(relativeDirSegments(file).join("/"));
          const requestMetadata = dirTagId ? { ...base, tags: [dirTagId] } : base;
          // Register each task the instant the server first reports its id (the first
          // line of the stream), not after the whole upload finishes — so the tray
          // lights up and starts its SSE subscription while the upload streams.
          return scheduleFile(
            file,
            uploadMode,
            requestMetadata,
            ({ taskId, documentUid }) => {
              dispatch(
                taskRegistered({
                  taskId,
                  kind: "ingestion",
                  target: documentUid ? { type: "document", id: documentUid, label: file.name } : null,
                }),
              );
            },
            (message) => showError?.({ summary: t("documentLibrary.uploadDrawerTitle"), detail: message }),
          );
        }),
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

            {isQuotaExceeded && team && (
              <div className={styles.quotaWarning} role="alert">
                <strong className={styles.quotaTitle}>{t("documentLibrary.storageQuotaExceededTitle")}</strong>
                <p className={styles.quotaMessage}>{t("documentLibrary.storageQuotaExceededMessage")}</p>
                <div className={styles.quotaRow}>
                  <span>
                    {t("documentLibrary.currentUsage")}{" "}
                    <strong>{formatBytes(team.current_resources_storage_size ?? 0)}</strong>
                  </span>
                  <span>
                    {t("documentLibrary.limit")} <strong>{formatBytes(team.max_resources_storage_size ?? 0)}</strong>
                  </span>
                </div>
                <div className={styles.quotaRow}>
                  <span>
                    {t("documentLibrary.newFilesSize")} <strong>{formatBytes(newFilesSize)}</strong>
                  </span>
                  <span className={styles.quotaExcess}>
                    {t("documentLibrary.excessSize")}{" "}
                    {formatBytes(
                      (team.current_resources_storage_size ?? 0) +
                        newFilesSize -
                        (team.max_resources_storage_size ?? 0),
                    )}
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
              disabled={!files.length || isLoading || isQuotaExceeded}
            >
              {isLoading ? t("documentLibrary.saving") : t("documentLibrary.save")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
