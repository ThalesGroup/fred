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

import { useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "react-i18next";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { Portal } from "@shared/utils/Portal";
import Button from "@shared/atoms/Button/Button";
import Select from "@shared/molecules/Select/Select";
import { usePermissions } from "../../../../../security/usePermissions";
import { streamUploadOrProcessDocument } from "../../../../../slices/streamDocumentUpload";
import { IngestionProcessingProfile } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useGetTeamQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { OptionModel } from "@models/Option.model";
import styles from "./DocumentUploadDrawer.module.css";

interface DocumentUploadDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadComplete?: () => void;
  metadata?: Record<string, unknown>;
  teamId?: string;
}

const UPLOAD_MODE_OPTIONS: OptionModel<"upload" | "process">[] = [
  { key: "upload", value: "upload", label: "Upload only" },
  { key: "process", value: "process", label: "Upload & process" },
];

const PROFILE_OPTIONS: OptionModel<IngestionProcessingProfile>[] = [
  { key: "fast", value: "fast", label: "Fast", description: "Quick extraction, basic chunking" },
  { key: "medium", value: "medium", label: "Medium", description: "Balanced quality and speed" },
  { key: "rich", value: "rich", label: "Rich", description: "Deep extraction, OCR, tables" },
];

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
}: DocumentUploadDrawerProps) {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const canSelectProfile = can("document", "update");

  const [uploadMode, setUploadMode] = useState<"upload" | "process">("process");
  const [profile, setProfile] = useState<IngestionProcessingProfile>("fast");
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
        await streamUploadOrProcessDocument(file, uploadMode, requestMetadata);
      }
      onUploadComplete?.();
    } finally {
      setIsLoading(false);
      handleClose();
    }
  };

  return (
    <Portal id="document-upload-drawer">
      <InlineDrawer open={isOpen} onClose={handleClose} title={t("documentLibrary.uploadDrawerTitle")} width="460px">
        <div className={styles.body}>
          <div className={styles.field}>
            <label className={styles.label}>Ingestion mode</label>
            <Select<"upload" | "process">
              options={UPLOAD_MODE_OPTIONS}
              value={uploadMode}
              onChange={setUploadMode}
              size="small"
            />
          </div>

          {canSelectProfile && (
            <div className={styles.field}>
              <label className={styles.label}>{t("documentLibrary.processingProfile")}</label>
              <Select<IngestionProcessingProfile>
                options={PROFILE_OPTIONS}
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
                    (team.current_resources_storage_size ?? 0) + newFilesSize - (team.max_resources_storage_size ?? 0),
                  )}
                </span>
              </div>
            </div>
          )}

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
      </InlineDrawer>
    </Portal>
  );
}
