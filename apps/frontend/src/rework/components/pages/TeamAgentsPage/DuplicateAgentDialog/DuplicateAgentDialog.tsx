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
import { isAgentNameTaken } from "../agentNames.ts";
import styles from "./DuplicateAgentDialog.module.css";

interface DuplicateAgentDialogProps {
  open: boolean;
  /** The source agent's current display name, prefilled as the starting point. */
  initialName: string;
  isSubmitting?: boolean;
  /** Normalised names already used in the team (see agentNames.ts). */
  takenNames?: ReadonlySet<string>;
  onCancel: () => void;
  onConfirm: (newName: string) => void;
}

const NO_NAMES: ReadonlySet<string> = new Set();

export default function DuplicateAgentDialog({
  open,
  initialName,
  isSubmitting = false,
  takenNames = NO_NAMES,
  onCancel,
  onConfirm,
}: DuplicateAgentDialogProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(initialName);
  // Checked when the field is left or Enter is pressed, never while typing.
  const [nameChecked, setNameChecked] = useState(true);

  // Reset to the source name each time the dialog reopens (e.g. for a
  // different agent, or reopened after a cancel).
  useEffect(() => {
    if (open) {
      setName(initialName);
      setNameChecked(true);
    }
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
  const nameTaken = isAgentNameTaken(name, takenNames);
  const canConfirm = trimmedName.length > 0 && !isSubmitting && !(nameChecked && nameTaken);

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onCancel}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="duplicate-agent-dialog-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.body}>
            <p id="duplicate-agent-dialog-title" className={styles.title}>
              {t("rework.agentCard.duplicateDialog.title")}
            </p>
            <TextInput
              label={t("rework.agentCard.duplicateDialog.nameLabel")}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setNameChecked(false);
              }}
              onBlur={() => setNameChecked(true)}
              error={nameChecked && nameTaken ? t("rework.teams.formAgent.fields.name.taken") : undefined}
              autoFocus
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                setNameChecked(true);
                if (canConfirm && !nameTaken) onConfirm(trimmedName);
              }}
            />
          </div>
          <div className={styles.actions}>
            <Button color="on-surface" variant="outlined" size="medium" onClick={onCancel}>
              {t("rework.agentCard.duplicateDialog.cancel")}
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              disabled={!canConfirm}
              onClick={() => onConfirm(trimmedName)}
            >
              {t("rework.agentCard.duplicateDialog.confirm")}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
