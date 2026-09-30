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
import { leafFileName } from "../../../../../slices/streamDocumentUpload";
import {
  IngestionProcessingProfile,
  useImportNameCheckKnowledgeFlowV1DocumentsNameCheckPostMutation,
  useQuotaPrecheckKnowledgeFlowV1QuotaPrecheckPostMutation,
  type ImportNameConflicts,
  type QuotaPrecheckResponse,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useGetTeamQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { OptionModel } from "@models/Option.model";
import { importPanelOpenRequested } from "../../../../features/tasks/taskSlice";
import {
  UPLOAD_BATCH_SIZE,
  chunkFilesByLeafName,
  runImport,
  type ImportBatch,
} from "../../../../features/imports/importRun";
import {
  MAX_FOLDER_DEPTH,
  displayPath,
  exceedsMaxFolderDepth,
  folderPathDepth,
  relativeDirSegments,
} from "./droppedPaths";
import {
  conflictKey,
  conflictsToAsk,
  decisionsForGroup,
  destinationsToCheck,
  namesArrivingTwice,
  splitByDecision,
  type ConflictDecision,
  type ImportConflict,
  type UploadGroup,
} from "./importConflicts";
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
  const { showError, showInfo } = useToast();

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

  // Names the destination folder already holds. Asked once, on Save, before
  // any byte leaves: until every one has an answer, nothing is sent. Editing
  // the list drops the answers with it — they were about that selection.
  const [conflicts, setConflicts] = useState<ImportConflict[]>([]);
  const [decisions, setDecisions] = useState<Map<string, ConflictDecision>>(new Map());
  const [checkNames] = useImportNameCheckKnowledgeFlowV1DocumentsNameCheckPostMutation();
  useEffect(() => {
    setConflicts([]);
    setDecisions(new Map());
  }, [files]);

  const unansweredCount = conflicts.filter(
    (conflict) => !decisions.has(conflictKey(conflict.tagId, conflict.name)),
  ).length;

  const decideOne = (conflict: ImportConflict, decision: ConflictDecision) =>
    setDecisions((prev) => new Map(prev).set(conflictKey(conflict.tagId, conflict.name), decision));

  const decideAll = (decision: ConflictDecision) =>
    setDecisions((prev) => {
      const next = new Map(prev);
      for (const conflict of conflicts) next.set(conflictKey(conflict.tagId, conflict.name), decision);
      return next;
    });

  /** Whether the destination folder already holds any of the selected names,
   * so an import into it may be replacing rather than adding. Scoped to that
   * one folder: a dropped subdirectory's folder may not exist yet, and finding
   * out would mean creating it before the quota question is settled. */
  const destinationMayHoldTheseNames = async (): Promise<boolean> => {
    const destination = ((metadata?.tags as string[] | undefined) ?? [])[0];
    if (!destination) return false;
    try {
      const answer = await checkNames({
        importNameCheckRequest: { destinations: [{ tag_id: destination, names: files.map(leafFileName) }] },
      }).unwrap();
      return (answer.conflicts ?? []).some((entry) => entry.names.length > 0);
    } catch {
      return false;
    }
  };

  /** Which of these files the destination folders already hold and the user
   * has not answered about yet. Advisory: a transport failure returns nothing
   * to ask, because the upload re-checks and reports what it finds — the
   * import must not be blocked by a check that only exists to save a transfer. */
  const askAboutConflicts = async (groups: UploadGroup[]): Promise<ImportConflict[]> => {
    const destinations = destinationsToCheck(groups);
    if (!destinations.length) return [];
    let answer: ImportNameConflicts[] = [];
    try {
      answer = (await checkNames({ importNameCheckRequest: { destinations } }).unwrap()).conflicts ?? [];
    } catch {
      return [];
    }
    return conflictsToAsk(groups, answer, displayPath).filter(
      (conflict) => !decisions.has(conflictKey(conflict.tagId, conflict.name)),
    );
  };

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
      // A denial counts every file at full size, but a file replacing an
      // existing document only costs the difference — which only the server
      // can work out. So a denial is not final while the destination may
      // already hold one of these names: the upload endpoint nets it out and
      // answers for real. Asked against the destination folder alone, which
      // needs no folder created to answer.
      if (!verdict.allowed && !(await destinationMayHoldTheseNames())) {
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
    // Group files that share the same destination tags into batches (same
    // request metadata => one request can carry several files, see
    // scheduleFiles' doc comment), then run those batches through a bounded
    // pool rather than firing one request per file unbounded.
    const base = canSelectProfile ? { ...(metadata ?? {}), profile } : { ...(metadata ?? {}) };
    const destinationTag = ((metadata?.tags as string[] | undefined) ?? [])[0] ?? null;
    const groups = new Map<string, { requestMetadata: Record<string, unknown>; group: UploadGroup }>();
    for (const file of files) {
      // A file inside a dropped subdirectory attaches to that subdirectory's
      // tag instead of the destination folder's (`base` keeps the latter).
      const dirTagId = tagIdByDir.get(dirKeyByFile.get(file)!);
      const requestMetadata = dirTagId ? { ...base, tags: [dirTagId] } : base;
      const groupKey = dirTagId ?? "";
      const existing = groups.get(groupKey);
      if (existing) existing.group.files.push(file);
      else groups.set(groupKey, { requestMetadata, group: { tagId: dirTagId ?? destinationTag, files: [file] } });
    }

    const uploadGroups = Array.from(groups.values(), (entry) => entry.group);

    // Two files of the same name into the same folder have no answer: one
    // decision cannot mean two things, and replacing would let one take the
    // other's place unnoticed. Refuse before anything is sent or created.
    const arrivingTwice = namesArrivingTwice(uploadGroups);
    if (arrivingTwice.length) {
      showError?.({
        summary: t("documentLibrary.uploadDrawerTitle"),
        detail: t("documentLibrary.sameNameTwice", { count: arrivingTwice.length, names: arrivingTwice.join(", ") }),
      });
      setIsLoading(false);
      return;
    }

    // Ask about the names before sending any byte, and outside the block below
    // whose `finally` closes the drawer: an unanswered conflict must leave it
    // open on the question, since resolving it either way would be resolving
    // it for the user.
    const unanswered = await askAboutConflicts(uploadGroups);
    if (unanswered.length) {
      setConflicts(unanswered);
      setIsLoading(false);
      return;
    }

    const batches: ImportBatch[] = [];
    let skippedCount = 0;
    for (const { requestMetadata, group } of groups.values()) {
      const { toUpload, skipped } = splitByDecision(group, decisions);
      skippedCount += skipped.length;
      if (!toUpload.length) continue;
      const decided = decisionsForGroup({ ...group, files: toUpload }, decisions);
      const metadataWithDecisions = Object.keys(decided).length
        ? { ...requestMetadata, conflict_decisions: decided }
        : requestMetadata;
      for (const batchFiles of chunkFilesByLeafName(toUpload, UPLOAD_BATCH_SIZE)) {
        batches.push({ requestMetadata: metadataWithDecisions, files: batchFiles });
      }
    }

    if (skippedCount) {
      // A skipped file is never sent: the whole point of asking first is not
      // to transfer bytes the answer makes useless.
      showInfo?.({
        summary: t("documentLibrary.uploadDrawerTitle"),
        detail: t("documentLibrary.conflictSkippedSummary", { count: skippedCount }),
      });
    }

    // Everything that had to be settled before sending is settled. Give the
    // application back now: the transfer is the long part, and the panel is
    // where it is followed from here. `runImport` deliberately runs detached —
    // it holds no reference to this component, only to the store and the toast
    // provider, both of which outlive the dialog.
    setIsLoading(false);
    handleClose();
    dispatch(importPanelOpenRequested());
    // Detached on purpose: every outcome reaches the panel through the store,
    // so nothing about the transfer depends on this dialog still being mounted.
    void runImport(batches, {
      dispatch,
      uploadMode,
      teamId: teamId ?? null,
      onError: (detail) => showError?.({ summary: t("documentLibrary.uploadDrawerTitle"), detail }),
      onComplete: onUploadComplete,
    });
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
            <div className={styles.fieldRow}>
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
            </div>

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

            {conflicts.length > 0 && (
              <div className={styles.conflicts} role="group" aria-labelledby="upload-conflicts-title">
                <strong id="upload-conflicts-title" className={styles.conflictsTitle}>
                  {t("documentLibrary.conflictsTitle", { count: conflicts.length })}
                </strong>
                <p className={styles.conflictsMessage}>{t("documentLibrary.conflictsMessage")}</p>
                <div className={styles.conflictsBulk}>
                  <Button color="on-surface" variant="outlined" size="small" onClick={() => decideAll("overwrite")}>
                    {t("documentLibrary.conflictReplaceAll")}
                  </Button>
                  <Button color="on-surface" variant="outlined" size="small" onClick={() => decideAll("skip")}>
                    {t("documentLibrary.conflictSkipAll")}
                  </Button>
                </div>
                <ul className={styles.conflictList}>
                  {conflicts.map((conflict) => {
                    const decision = decisions.get(conflictKey(conflict.tagId, conflict.name));
                    return (
                      <li key={conflictKey(conflict.tagId, conflict.name)} className={styles.conflictRow}>
                        <span className={styles.fileName} title={conflict.label}>
                          {conflict.label}
                        </span>
                        <Button
                          color="on-surface"
                          variant={decision === "overwrite" ? "filled" : "outlined"}
                          size="small"
                          aria-pressed={decision === "overwrite"}
                          onClick={() => decideOne(conflict, "overwrite")}
                        >
                          {t("documentLibrary.conflictReplace")}
                        </Button>
                        <Button
                          color="on-surface"
                          variant={decision === "skip" ? "filled" : "outlined"}
                          size="small"
                          aria-pressed={decision === "skip"}
                          onClick={() => decideOne(conflict, "skip")}
                        >
                          {t("documentLibrary.conflictSkip")}
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

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
              disabled={!files.length || isLoading || !!quotaDenial || unansweredCount > 0}
            >
              {/* What the button does, and to how many files — "Save" said
                  neither, and nothing is being saved here. */}
              {files.length ? t("documentLibrary.importCount", { count: files.length }) : t("documentLibrary.import")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
