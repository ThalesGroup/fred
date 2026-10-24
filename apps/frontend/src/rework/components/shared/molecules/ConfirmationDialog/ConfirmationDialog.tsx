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

import { useCallback, useEffect, useRef, type ReactNode } from "react";
import Button from "@shared/atoms/Button/Button.tsx";
import { isTopmostModal, Portal } from "@shared/utils/Portal.tsx";
import { ButtonVariant, ColorTheme } from "@shared/utils/Type.ts";
import styles from "./ConfirmationDialog.module.css";

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

interface ConfirmationDialogProps {
  open: boolean;
  title: string;
  message?: string;
  /** Extra content rendered under the message — e.g. an impact drill-down. */
  details?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  showCancel?: boolean;
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
  confirmDisabled?: boolean;
  /** False for a choice the user must make explicitly: neither the scrim nor
   *  Escape closes the dialog. */
  dismissible?: boolean;
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
  showCancel = true,
  criticalAction = false,
  cancelVariant,
  cancelColor,
  confirmVariant,
  confirmDisabled = false,
  dismissible = true,
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
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const callbacks = useRef({ onCancel, dismissible });
  callbacks.current = { onCancel, dismissible };
  // Focus lands on Cancel when present, otherwise on the single action.
  const attachDialog = useCallback((node: HTMLDivElement | null) => {
    dialogRef.current = node;
    node?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const handleKeyDown = (e: KeyboardEvent) => {
      const dialog = dialogRef.current;
      if (!dialog || !isTopmostModal(dialog)) return;
      if (e.key === "Escape" && !e.defaultPrevented) {
        // A non-dismissible choice keeps the focus trap but ignores Escape.
        if (!callbacks.current.dismissible) return;
        e.preventDefault();
        callbacks.current.onCancel();
      } else if (e.key === "Tab") {
        const focusable = [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE)];
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!first) return;
        if (!dialog.contains(document.activeElement) || document.activeElement === (e.shiftKey ? first : last)) {
          e.preventDefault();
          (e.shiftKey ? last : first).focus();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      if (opener?.isConnected) opener.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={dismissible ? onCancel : undefined}>
        <div
          ref={attachDialog}
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
            {showCancel && (
              <Button
                color={resolvedCancelColor}
                variant={resolvedCancelVariant}
                size="medium"
                onClick={onCancel}
                data-autofocus
              >
                {cancelLabel}
              </Button>
            )}
            <Button
              color={criticalAction ? "error" : "primary"}
              variant={resolvedConfirmVariant}
              size="medium"
              disabled={confirmDisabled}
              onClick={onConfirm}
              data-autofocus={showCancel ? undefined : true}
            >
              {confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
