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
import { useEffect, useMemo, useRef, useState } from "react";
import { useDispatch } from "react-redux";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "react-i18next";
import { Portal } from "@shared/utils/Portal";
import { useFocusHandoff } from "@shared/utils/useFocusHandoff";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Select from "@shared/molecules/Select/Select";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import UploadWarningBanner from "@shared/molecules/UploadWarningBanner/UploadWarningBanner";
import { formatBytes } from "@shared/utils/formatBytes";
import { leafFileName } from "./droppedPaths";
import type { Profile } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { OptionModel } from "@models/Option.model";
import { importPanelOpenRequested } from "../../../../features/tasks/taskSlice";
import {
  MAX_FOLDER_DEPTH,
  displayPath,
  exceedsMaxFolderDepth,
  folderPathDepth,
  relativeDirSegments,
} from "./droppedPaths";
import { enhancedControlPlaneApi as managerApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { runManagerImport, type ManagerDispatch } from "../../../../features/imports/managerImportRun";
import styles from "./DocumentUploadDrawer.module.css";
interface DocumentUploadDrawerProps {
  isOpen: boolean;
  managerDestination: {
    spaceId: string;
    folderId?: string;
    processingEnabled?: boolean;
  };
  /** Keep the existing panel available while its destination cannot accept uploads. */
  unavailableReason?: string;
  onClose: () => void;
  onUploadComplete?: () => void;
  teamId?: string;
  /** The team an import is filed under, for the panel that follows it. Distinct
   *  from `teamId`, which may be the "personal" URL alias: the server reports
   *  the owning team's real id, and the two have to agree after a reload. */
  importScopeId?: string | null;
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
  managerDestination,
  unavailableReason,
  onClose,
  onUploadComplete,
  destinationPath,
  initialFiles,
  ensureFolderPath,
  requireFolderPerFile,
}: DocumentUploadDrawerProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const dispatch = useDispatch<ManagerDispatch>();
  const [uploadMode, setUploadMode] = useState<"upload" | "process">("process");
  const processingAvailable = managerDestination.processingEnabled === true;
  const effectiveMode = processingAvailable ? uploadMode : "upload";
  const [profile, setProfile] = useState<Profile>("fast");
  const uploadModeOptions = useMemo<OptionModel<"upload" | "process">[]>(
    () => [
      { key: "upload", value: "upload", label: t("documentLibrary.uploadOnly") },
      { key: "process", value: "process", label: t("documentLibrary.uploadAndProcess") },
    ],
    [t],
  );
  const profileOptions = useMemo<OptionModel<Profile>[]>(
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
  const newFilesSize = useMemo(() => files.reduce((acc, f) => acc + f.size, 0), [files]);
  const nestedDirCount = useMemo(() => {
    if (!ensureFolderPath) return 0;
    return new Set(files.map((f) => relativeDirSegments(f).join("/")).filter(Boolean)).size;
  }, [files, ensureFolderPath]);
  const [quotaDenial, setQuotaDenial] = useState<{
    current: number;
    limit: number;
  } | null>(null);
  useEffect(() => setQuotaDenial(null), [files]);
  // Names the destination folder already holds. Asked once, on Save, before
  // any byte leaves: until every one has an answer, nothing is sent. Editing
  // the list drops the answers with it — they were about that selection.
  const handingOffManagerFiles = useRef(false);
  const [managerConflicts, setManagerConflicts] = useState<
    {
      key: string;
      name: string;
      label: string;
    }[]
  >([]);
  const [decisions, setDecisions] = useState<Map<string, "skip">>(new Map());
  useEffect(() => {
    if (handingOffManagerFiles.current) {
      handingOffManagerFiles.current = false;
      return;
    }
    setManagerConflicts([]);
    setDecisions(new Map());
  }, [files]);
  const displayedConflicts = managerConflicts;
  const unansweredCount = displayedConflicts.filter((conflict) => !decisions.has(conflict.key)).length;
  const decideOne = (key: string, decision: "skip") => setDecisions((prev) => new Map(prev).set(key, decision));
  const decideAll = (decision: "skip") =>
    setDecisions((prev) => {
      const next = new Map(prev);
      for (const conflict of displayedConflicts) next.set(conflict.key, decision);
      return next;
    });
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
  const saveOriginals = async () => {
    if (!managerDestination || !files.length || isLoading) return;
    setIsLoading(true);
    try {
      if (files.length > 200) throw new Error(t("rework.documentStorage.batchLimit"));
      const destinations = new Map<
        string,
        {
          segments: string[];
          files: File[];
        }
      >();
      for (const file of files) {
        if (file.size > 100 * 1024 * 1024) throw new Error(t("rework.documentStorage.fileLimit"));
        const segments = relativeDirSegments(file);
        const key = JSON.stringify(segments);
        const group = destinations.get(key) ?? { segments, files: [] };
        if (group.files.some((f) => leafFileName(f).normalize("NFC") === leafFileName(file).normalize("NFC")))
          throw new Error(t("documentLibrary.sameNameTwice", { count: 1, names: leafFileName(file) }));
        group.files.push(file);
        destinations.set(key, group);
      }
      const selected: {
        file: File;
        folderId: string;
      }[] = [];
      const found: typeof managerConflicts = [];
      let budget:
        | {
            used: number;
            limit: number;
          }
        | undefined;
      for (const group of destinations.values()) {
        const folderId =
          group.segments.length && ensureFolderPath
            ? await ensureFolderPath(group.segments)
            : managerDestination.folderId;
        if (!folderId) throw new Error(t("documentLibrary.folderRequired"));
        const verdict = await dispatch(
          managerApi.endpoints.preflight.initiate({
            id: folderId,
            preflight: { files: group.files.map((file) => ({ name: leafFileName(file), size: file.size })) },
          }),
        ).unwrap();
        if (group.files.some((file) => file.size > verdict.storage.max_file_bytes))
          throw new Error(t("rework.documentStorage.fileLimit"));
        if (effectiveMode === "process" && !verdict.storage.processing_enabled)
          throw new Error(t("rework.documentStorage.noProcessing"));
        if (!verdict.storage.uploads_enabled) throw new Error(t("rework.documentStorage.unavailable"));
        const taken = new Set(verdict.conflicts);
        budget = {
          used: verdict.storage.used_bytes + verdict.storage.reserved_bytes,
          limit: verdict.storage.quota_bytes,
        };
        for (const file of group.files) {
          const name = leafFileName(file).normalize("NFC");
          const key = JSON.stringify([folderId, name]);
          if (taken.has(name)) {
            found.push({ key, name, label: displayPath(file) });
            if (decisions.get(key) !== "skip") continue;
          } else selected.push({ file, folderId });
        }
      }
      setManagerConflicts(found);
      const awaitingSkip = found.some((conflict) => decisions.get(conflict.key) !== "skip");
      if (budget && selected.reduce((sum, { file }) => sum + file.size, 0) > budget.limit - budget.used) {
        setQuotaDenial({ current: budget.used, limit: budget.limit });
        return;
      }
      const completion = selected.length
        ? runManagerImport(
            dispatch,
            managerDestination.spaceId,
            selected,
            effectiveMode === "process" ? profile : undefined,
          )
        : Promise.resolve();
      if (awaitingSkip) {
        if (selected.length) {
          handingOffManagerFiles.current = true;
          const launched = new Set(selected.map(({ file }) => file));
          setFiles(files.filter((file) => !launched.has(file)));
        }
      } else handleClose();
      if (selected.length) dispatch(importPanelOpenRequested());
      void completion
        .catch(() => showError({ summary: t("rework.documentStorage.unavailable") }))
        .finally(onUploadComplete);
    } catch (error) {
      showError({
        summary: t("documentLibrary.uploadDrawerTitle"),
        detail: error instanceof Error ? error.message : t("rework.documentStorage.unavailable"),
      });
    } finally {
      setIsLoading(false);
    }
  };
  const handleSave = saveOriginals;
  const dialogRef = useRef<HTMLDivElement>(null);
  useFocusHandoff(isOpen, dialogRef);
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
          ref={dialogRef}
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
                {/* No error slot held open under a field that has no error
            to report: neither of these can fail. */}
                <Select<"upload" | "process">
                  options={uploadModeOptions.map((option) => ({
                    ...option,
                    disabled: option.value === "process" && !processingAvailable,
                    tooltip:
                      option.value === "process" && !processingAvailable
                        ? t("rework.documentStorage.noProcessing")
                        : undefined,
                  }))}
                  value={effectiveMode}
                  onChange={setUploadMode}
                  size="small"
                  compact
                />
              </div>

              {
                <div className={styles.field}>
                  <label className={styles.label}>{t("documentLibrary.processingProfile")}</label>
                  <Select<Profile>
                    options={profileOptions}
                    disabled={effectiveMode === "upload"}
                    value={profile}
                    onChange={setProfile}
                    size="small"
                    compact
                  />
                </div>
              }
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

            {displayedConflicts.length > 0 && (
              <div className={styles.conflicts} role="group" aria-labelledby="upload-conflicts-title">
                <strong id="upload-conflicts-title" className={styles.conflictsTitle}>
                  {t("documentLibrary.conflictsTitle", { count: displayedConflicts.length })}
                </strong>
                <p className={styles.conflictsMessage}>
                  {t("rework.documentStorage.nameConflict", {
                    names: displayedConflicts.map((conflict) => conflict.label).join(", "),
                  })}
                </p>
                <div className={styles.conflictsBulk}>
                  <Button color="on-surface" variant="outlined" size="small" onClick={() => decideAll("skip")}>
                    {t("documentLibrary.conflictSkipAll")}
                  </Button>
                </div>
                <ul className={styles.conflictList}>
                  {displayedConflicts.map((conflict) => {
                    const decision = decisions.get(conflict.key);
                    return (
                      <li key={conflict.key} className={styles.conflictRow}>
                        <span className={styles.fileName} title={conflict.label}>
                          {conflict.label}
                        </span>
                        {/* One pick per file, so the two options are one
                        control rather than two buttons that happen to be
                        mutually exclusive. Nothing is selected until the
                        user answers — the import waits on that. */}
                        <Button
                          size="2xs"
                          color="on-surface"
                          variant="outlined"
                          disabled={decision === "skip"}
                          onClick={() => decideOne(conflict.key, "skip")}
                        >
                          {t("documentLibrary.conflictSkip")}
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {managerDestination && effectiveMode === "upload" && (
              <div className={styles.quotaWarning} role="status">
                {t("rework.documentStorage.storedHint")}
              </div>
            )}
            {unavailableReason && (
              <div className={styles.quotaWarning} role="status">
                {unavailableReason}
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
              disabled={!!unavailableReason || !files.length || isLoading || !!quotaDenial || unansweredCount > 0}
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
