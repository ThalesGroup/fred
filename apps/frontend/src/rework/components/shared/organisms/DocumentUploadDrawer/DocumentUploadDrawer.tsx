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
import { usePermissions } from "../../../../../security/usePermissions";
import { streamUploadOrProcessDocument } from "../../../../../slices/streamDocumentUpload";
import { IngestionProcessingProfile } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useGetTeamQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { OptionModel } from "@models/Option.model";
import { taskRegistered } from "../../../../features/tasks/taskSlice";
import styles from "./DocumentUploadDrawer.module.css";

interface DocumentUploadDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadComplete?: () => void;
  metadata?: Record<string, unknown>;
  teamId?: string;
  /** Destination folder path shown prominently in the header, e.g. "CIR" or "CIR/Sub". */
  destinationPath?: string;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function DocumentUploadDrawer({
  isOpen,
  onClose,
  onUploadComplete,
  metadata,
  teamId,
  destinationPath,
}: DocumentUploadDrawerProps) {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const canSelectProfile = can("document", "update");

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

  const resolvedTeamId = teamId ?? "personal";
  const { data: team } = useGetTeamQuery({ teamId: resolvedTeamId });

  const newFilesSize = useMemo(() => files.reduce((acc, f) => acc + f.size, 0), [files]);

  const isQuotaExceeded = useMemo(() => {
    if (!team) return false;
    const current = team.current_resources_storage_size ?? 0;
    const max = team.max_resources_storage_size ?? 0;
    if (max <= 0) return false;
    return current + newFilesSize > max;
  }, [team, newFilesSize]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    noKeyboard: true,
    onDrop: (accepted) => {
      setFiles((prev) => {
        const existing = new Set(prev.map((f) => `${f.name}-${f.size}-${f.lastModified}`));
        return [...prev, ...accepted.filter((f) => !existing.has(`${f.name}-${f.size}-${f.lastModified}`))];
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
    try {
      for (const file of files) {
        const requestMetadata = canSelectProfile ? { ...(metadata ?? {}), profile } : { ...(metadata ?? {}) };
        const scheduled = await streamUploadOrProcessDocument(file, uploadMode, requestMetadata);
        for (const { taskId, documentUid } of scheduled) {
          dispatch(
            taskRegistered({
              taskId,
              kind: "ingestion",
              target: documentUid ? { type: "document", id: documentUid, label: file.name } : null,
            }),
          );
        }
      }
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
              color="on-surface"
              variant="icon"
              size="xs"
              icon={{ category: "outlined", type: "close" }}
              aria-label={t("common.close")}
              onClick={handleClose}
            />
          </div>
          <div className={styles.body}>
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
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                  <span className={styles.dropzoneHint}>{t("documentLibrary.dropFiles")}</span>
                  <span className={styles.dropzoneCaption}>{t("documentLibrary.maxSize")}</span>
                </div>
              ) : (
                <ul className={styles.fileList}>
                  {files.map((f, i) => (
                    <li key={`${f.name}-${i}`} className={styles.fileRow}>
                      <span className={styles.fileName} title={f.name}>
                        {f.name}
                      </span>
                      <span className={styles.fileSize}>{formatBytes(f.size)}</span>
                      <button
                        type="button"
                        className={styles.removeBtn}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemove(i);
                        }}
                        aria-label={`Remove ${f.name}`}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

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
