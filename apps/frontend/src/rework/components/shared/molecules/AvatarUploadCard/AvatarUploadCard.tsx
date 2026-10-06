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

import styles from "./AvatarUploadCard.module.scss";
import Button from "@shared/atoms/Button/Button.tsx";
import AvatarCropEditor from "@shared/organisms/AvatarCropEditor/AvatarCropEditor.tsx";
import React, { useRef, useState } from "react";

// Mirrors the backend avatar validation (5 MB, JPEG/PNG/WebP).
const MAX_AVATAR_SIZE = 5 * 1024 * 1024;
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

interface AvatarUploadCardProps {
  title: string;
  hint: string;
  importLabel: string;
  emptyLabel: string;
  imageUrl?: string;
  /** Receives the square crop as a WebP blob. */
  onUpload: (blob: Blob) => Promise<void>;
  uploading?: boolean;
  /** Shows a Delete action, only while an image is set. */
  onDelete?: () => void;
  deleteLabel?: string;
  deleting?: boolean;
}

/** Square avatar upload card: pick a file, crop it, preview the result. */
export default function AvatarUploadCard({
  title,
  hint,
  importLabel,
  emptyLabel,
  imageUrl,
  onUpload,
  uploading = false,
  onDelete,
  deleteLabel,
  deleting = false,
}: AvatarUploadCardProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  // The image the user just picked, pending crop. Non-null opens the editor.
  const [cropFile, setCropFile] = useState<File | null>(null);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset the input immediately so re-picking the same file re-fires onChange.
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (!file) return;
    if (!ALLOWED_TYPES.includes(file.type)) {
      console.error("Invalid file type:", file.type);
      return;
    }
    if (file.size > MAX_AVATAR_SIZE) {
      console.error("File size exceeds limit:", file.size);
      return;
    }
    setCropFile(file);
  };

  const handleCropSave = async (blob: Blob) => {
    try {
      await onUpload(blob);
    } catch (error) {
      console.error("Avatar upload error:", error);
    } finally {
      setCropFile(null);
    }
  };

  return (
    <div className={styles["avatar-upload-card"]}>
      <span className={styles["avatar-upload-title"]}>{title}</span>
      <div className={styles["avatar-upload-content"]}>
        <div className={styles["avatar-upload-actions"]}>
          <input
            ref={fileInputRef}
            type="file"
            className={styles["avatar-upload-file-input"]}
            accept={ALLOWED_TYPES.join(",")}
            onChange={handleFileSelect}
            data-testid="avatar-upload-input"
          />
          <Button
            color="secondary"
            variant="outlined"
            size="small"
            icon={{ category: "outlined", type: "upload" }}
            onClick={() => fileInputRef.current?.click()}
          >
            {importLabel}
          </Button>
          {onDelete && imageUrl && (
            <Button
              color="error"
              variant="text"
              size="small"
              icon={{ category: "outlined", type: "delete" }}
              disabled={deleting}
              onClick={onDelete}
            >
              {deleteLabel}
            </Button>
          )}
          <span className={styles["avatar-upload-hint"]}>{hint}</span>
        </div>
        <div className={styles["avatar-upload-preview"]}>
          {imageUrl ? (
            <img
              className={styles["avatar-upload-preview-image"]}
              src={imageUrl}
              alt=""
              width={96}
              height={96}
              decoding="async"
            />
          ) : (
            <span className={styles["avatar-upload-preview-empty"]}>{emptyLabel}</span>
          )}
        </div>
      </div>
      {cropFile && (
        <AvatarCropEditor
          file={cropFile}
          open
          onCancel={() => setCropFile(null)}
          onSave={handleCropSave}
          saving={uploading}
        />
      )}
    </div>
  );
}
