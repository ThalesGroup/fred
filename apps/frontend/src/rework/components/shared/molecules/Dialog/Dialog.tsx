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
import { ColorTheme } from "@shared/utils/Type";
import { Portal } from "@shared/utils/Portal";
import styles from "./Dialog.module.css";

// `<input>` types with no "Enter submits" convention — a checkbox or file
// picker inside a dialog body should not implicitly confirm it.
const NON_TEXT_INPUT_TYPES = new Set([
  "button",
  "checkbox",
  "color",
  "file",
  "image",
  "radio",
  "range",
  "reset",
  "submit",
]);

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
  /** Hide the cancel button for a single-action dialog (e.g. an info dialog
   *  whose only action is "Got it"). Escape and click-outside still dismiss. */
  hideCancel?: boolean;
  /** Confirm button color. Defaults to "primary"; use "error" for a destructive
   *  action that still needs the Dialog's free-form body (which ConfirmationDialog
   *  can't host). */
  confirmColor?: ColorTheme;
  /** Widen the dialog beyond the default 400px (still capped at 90vw), for
   *  content that needs room — e.g. a selectable list. */
  maxWidth?: number;
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
  confirmColor = "primary",
  maxWidth,
}: DialogProps) {
  const { t } = useTranslation();
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCancel();
        return;
      }
      // Enter confirms — a dialog whose body is one field should not need a
      // trip to the mouse. Never while composing an IME candidate, never past
      // a disabled confirm button (which would submit exactly what the caller
      // judged invalid), and never over a key some descendant already acted
      // on (`preventDefault` with no `stopPropagation`, e.g. a field that
      // commits its own Enter) — that would run the same action twice.
      if (e.key !== "Enter" || e.shiftKey || e.isComposing || confirmDisabled || e.defaultPrevented) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      // Enter already has a meaning here: a focused BUTTON/A fires its own
      // click natively, a native SELECT opens its own dropdown, and a
      // role="button"/"link" control is expected to run its own handler.
      // Forcing onConfirm on top would run both — or, focused on Cancel, run
      // the wrong one instead of the native click's onCancel.
      if (tag === "BUTTON" || tag === "A" || tag === "SELECT") return;
      const role = target?.getAttribute("role");
      if (role === "button" || role === "link") return;
      if (tag === "TEXTAREA" || target?.isContentEditable) return;
      // Implicit submission is for a single-line text field, not any input —
      // Enter has no such convention on a checkbox, radio, or file picker.
      if (tag === "INPUT" && NON_TEXT_INPUT_TYPES.has((target as HTMLInputElement).type)) return;
      e.preventDefault();
      onConfirm();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel, onConfirm, confirmDisabled]);

  if (!open) return null;

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onCancel}>
        <div
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          style={maxWidth ? { width: `min(${maxWidth}px, 90vw)` } : undefined}
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
            <Button color={confirmColor} variant="filled" size="medium" disabled={confirmDisabled} onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
