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

import { useEffect, type ReactNode } from "react";
import Button from "@shared/atoms/Button/Button.tsx";
import { Portal } from "@shared/utils/Portal.tsx";
import { ButtonVariant, ColorTheme } from "@shared/utils/Type.ts";
import styles from "./ConfirmationDialog.module.css";

interface ConfirmationDialogProps {
  open: boolean;
  title: string;
  message?: string;
  /** Extra content rendered under the message — e.g. an impact drill-down. */
  details?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  criticalAction?: boolean;
  /** Override the cancel/dismiss button's emphasis — default "outlined", or
   *  "filled" when `criticalAction` is set. */
  cancelVariant?: ButtonVariant;
  /** Override the cancel/dismiss button's color — default "on-surface", or
   *  "primary" when `criticalAction` is set. */
  cancelColor?: ColorTheme;
  /** Override the confirm button's emphasis — default "filled", or "text"
   *  when `criticalAction` is set. Color still follows `criticalAction`
   *  (error vs. primary), independent of variant. */
  confirmVariant?: ButtonVariant;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmationDialog({
  open,
  title,
  message,
  details,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  criticalAction = false,
  cancelVariant,
  cancelColor,
  confirmVariant,
  onConfirm,
  onCancel,
}: ConfirmationDialogProps) {
  // Critical-action dialogs always de-emphasize the destructive choice: a
  // filled, primary "Cancel" and a text-only, error-coloured confirm — never
  // the other way around. Callers can still override any of the three
  // explicitly, but this is the one formalism every critical dialog in the
  // app must default to, so no call site needs to remember to opt into it.
  const resolvedCancelVariant = cancelVariant ?? (criticalAction ? "filled" : "outlined");
  const resolvedCancelColor = cancelColor ?? (criticalAction ? "primary" : "on-surface");
  const resolvedConfirmVariant = confirmVariant ?? (criticalAction ? "text" : "filled");
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onCancel}>
        <div
          className={styles.dialog}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="confirm-dialog-title"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.body}>
            <p id="confirm-dialog-title" className={styles.title}>
              {title}
            </p>
            {message && <p className={styles.message}>{message}</p>}
            {details}
          </div>
          <div className={styles.actions}>
            <Button color={resolvedCancelColor} variant={resolvedCancelVariant} size="medium" onClick={onCancel}>
              {cancelLabel}
            </Button>
            <Button
              color={criticalAction ? "error" : "primary"}
              variant={resolvedConfirmVariant}
              size="medium"
              onClick={onConfirm}
            >
              {confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
