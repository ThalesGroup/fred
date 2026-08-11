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

import { ReactNode, useEffect, useId } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { Portal } from "@shared/utils/Portal";
import styles from "./Dialog.module.css";

interface DialogProps {
  open: boolean;
  /** Heading shown at the top of the dialog. */
  title: string;
  /** Dialog body — any content (a field, a message, a form…). */
  children: ReactNode;
  /** Confirm button label — always a precise action verb ("Save", "Rename",
   *  "Delete team"), never a generic "OK". */
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** Cancel button label. Defaults to the shared "Cancel" string. */
  cancelLabel?: string;
  /** Disables the confirm button (e.g. empty/invalid input, request in flight). */
  confirmDisabled?: boolean;
  /** Drops the Cancel button, leaving the confirm as the only action. Only for
   *  dialogs that present information rather than ask for a decision (there is
   *  nothing to cancel, so offering it would suggest the content is a choice).
   *  Escape and click-outside still dismiss. */
  hideCancel?: boolean;
}

/**
 * The app's central simple dialog: a title, free-form content, and a
 * two-button action bar (a text "Cancel" and a filled primary confirm named
 * after the action). Centred over a classic scrim; click-outside and Escape
 * both cancel. No close (X) affordance — the action bar is the only exit.
 *
 * For destructive/critical confirmations that must de-emphasise the dangerous
 * choice (inverted button emphasis), use `ConfirmationDialog` instead — this
 * component intentionally keeps a single, non-inverted action shape.
 */
export function Dialog({
  open,
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
  cancelLabel,
  confirmDisabled = false,
  hideCancel = false,
}: DialogProps) {
  const { t } = useTranslation();
  const titleId = useId();

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
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.titleContainer}>
            <p id={titleId} className={styles.title}>
              {title}
            </p>
          </div>
          <div className={styles.content}>{children}</div>
          <div className={styles.actions}>
            {!hideCancel && (
              <Button color="on-surface" variant="text" size="medium" onClick={onCancel}>
                {cancelLabel ?? t("common.cancel")}
              </Button>
            )}
            <Button color="primary" variant="filled" size="medium" disabled={confirmDisabled} onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
