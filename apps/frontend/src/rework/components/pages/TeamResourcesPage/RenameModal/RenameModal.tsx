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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { Portal } from "@shared/utils/Portal.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import styles from "./RenameModal.module.css";

interface RenameModalProps {
  open: boolean;
  onClose: () => void;
  initialName: string;
  onSubmit: (name: string) => Promise<void>;
}

/**
 * Single-field "new name" dialog reused for every rename action across the
 * Resources tabs (Corpus folders/documents, Espace perso/partagé/Agents
 * files) — one modal, callers supply the initial name and a submit handler
 * that hits whichever rename endpoint applies (tag PUT, document title PUT,
 * or `/fs/rename`).
 */
export default function RenameModal({ open, onClose, initialName, onSubmit }: RenameModalProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [name, setName] = useState(initialName);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (open) setName(initialName);
  }, [open, initialName]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const trimmed = name.trim();
  const unchanged = trimmed === initialName.trim();

  const submit = async () => {
    if (!trimmed || isSaving || unchanged) return;
    setIsSaving(true);
    try {
      await onSubmit(trimmed);
      onClose();
    } catch (e: unknown) {
      showError?.({
        summary: t("validation.error"),
        detail: (e as { data?: { detail?: string } })?.data?.detail ?? t("rework.resources.renameModal.error"),
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onClose}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="rename-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.body}>
            <div className={styles.header}>
              <p id="rename-title" className={styles.title}>
                {t("rework.resources.renameModal.title")}
              </p>
              <IconButton
                color="on-surface"
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "close" }}
                aria-label={t("common.close")}
                onClick={onClose}
              />
            </div>

            <TextInput
              autoFocus
              label={t("rework.resources.renameModal.nameLabel")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void submit();
              }}
            />
          </div>

          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={onClose}>
              {t("rework.resources.folderModal.cancel")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={!trimmed || isSaving || unchanged}
              onClick={() => void submit()}
            >
              {t("rework.resources.renameModal.save")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
