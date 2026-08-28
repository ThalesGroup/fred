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
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { Portal } from "@shared/utils/Portal.tsx";
import styles from "./DuplicatePromptDialog.module.css";

interface DuplicatePromptDialogProps {
  open: boolean;
  /** The source prompt's current name, prefilled as the starting point. */
  initialName: string;
  isSubmitting?: boolean;
  onCancel: () => void;
  onConfirm: (newName: string) => void;
}

/** Mirrors `DuplicateAgentDialog`: a single-field "name the copy" dialog. Prompt
 * names are unique within a team, so the parent surfaces a 409 as a field error. */
export default function DuplicatePromptDialog({
  open,
  initialName,
  isSubmitting = false,
  onCancel,
  onConfirm,
}: DuplicatePromptDialogProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(initialName);

  useEffect(() => {
    if (open) setName(initialName);
  }, [open, initialName]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  const trimmedName = name.trim();
  const canConfirm = trimmedName.length > 0 && !isSubmitting;

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onCancel}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="duplicate-prompt-dialog-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.body}>
            <p id="duplicate-prompt-dialog-title" className={styles.title}>
              {t("rework.teams.prompts.duplicateDialog.title")}
            </p>
            <TextInput
              label={t("rework.teams.prompts.duplicateDialog.nameLabel")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && canConfirm) onConfirm(trimmedName);
              }}
            />
          </div>
          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={onCancel}>
              {t("rework.teams.prompts.duplicateDialog.cancel")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={!canConfirm}
              onClick={() => onConfirm(trimmedName)}
            >
              {t("rework.teams.prompts.duplicateDialog.confirm")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
