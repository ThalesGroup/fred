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

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import Button from "../../atoms/Button/Button";
import { type ColorTheme } from "../../utils/Type";
import { Portal, uiPortalRoot } from "../../utils/Portal";
import styles from "./Dialog.module.css";

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
const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

function isVisibleFocusable(node: HTMLElement, dialog: HTMLElement): boolean {
  if (node.tabIndex < 0 || node.closest('[hidden], [inert], [aria-hidden="true"]')) return false;
  for (let ancestor: HTMLElement | null = node; ancestor; ancestor = ancestor.parentElement) {
    const style = getComputedStyle(ancestor);
    if (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse") return false;
    if (ancestor === dialog) break;
  }
  return true;
}

export interface DialogProps {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** Caller-owned label. The neutral default is English; FRED's wrapper supplies its translation. */
  cancelLabel?: string;
  confirmDisabled?: boolean;
  hideCancel?: boolean;
  confirmColor?: ColorTheme;
  maxWidth?: number;
  /** Optional caller-owned portal container inside the themed .fred-ui root. */
  portalContainer?: HTMLElement | null;
}

export function DialogPrimitive({
  open,
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
  cancelLabel = "Cancel",
  confirmDisabled = false,
  hideCancel = false,
  confirmColor = "primary",
  maxWidth,
  portalContainer,
}: DialogProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const originRef = useRef<HTMLSpanElement | null>(null);
  const openingFocus = useRef<HTMLElement | null>(null);
  const [portalRoot, setPortalRoot] = useState<HTMLElement | null>(null);
  const callbacks = useRef({ onCancel, onConfirm, confirmDisabled });
  callbacks.current = { onCancel, onConfirm, confirmDisabled };
  const attachDialog = useCallback((node: HTMLDivElement | null) => {
    dialogRef.current = node;
    if (node)
      (
        [...node.querySelectorAll<HTMLElement>(FOCUSABLE)].find((candidate) => isVisibleFocusable(candidate, node)) ??
        node
      ).focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    openingFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const originRoot = uiPortalRoot(originRef.current);
    if (portalContainer && originRoot !== document.body && !originRoot.contains(portalContainer)) {
      throw new Error("Dialog portalContainer must be inside its originating .fred-ui root");
    }
    setPortalRoot(portalContainer ?? originRoot);
    return () => {
      const target = openingFocus.current;
      openingFocus.current = null;
      setPortalRoot(null);
      if (target?.isConnected) target.focus();
    };
  }, [open, portalContainer]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const dialog = dialogRef.current;
      if (!dialog) return;
      if (event.key === "Escape") {
        event.preventDefault();
        callbacks.current.onCancel();
        return;
      }
      if (event.key === "Tab") {
        const focusable = [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((node) =>
          isVisibleFocusable(node, dialog),
        );
        if (!focusable.length) {
          event.preventDefault();
          dialog.focus();
          return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!dialog.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) {
          event.preventDefault();
          (event.shiftKey ? last : first).focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
        return;
      }
      if (
        event.key !== "Enter" ||
        event.shiftKey ||
        event.isComposing ||
        event.defaultPrevented ||
        callbacks.current.confirmDisabled
      )
        return;
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (!target || !dialog.contains(target)) return;
      const tag = target.tagName;
      if (["BUTTON", "A", "SELECT", "TEXTAREA"].includes(tag) || target.isContentEditable) return;
      const role = target.getAttribute("role");
      if (role === "button" || role === "link") return;
      if (tag === "INPUT" && NON_TEXT_INPUT_TYPES.has((target as HTMLInputElement).type)) return;
      event.preventDefault();
      callbacks.current.onConfirm();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  if (!open) return null;
  return (
    <>
      <span ref={originRef} hidden aria-hidden="true" />
      {portalRoot && (
        <Portal id="modal-portal" root={portalRoot}>
          <div
            className={styles.overlay}
            onClick={(event) => {
              if (event.target === event.currentTarget) onCancel();
            }}
          >
            <div
              ref={attachDialog}
              className={styles.dialog}
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
              tabIndex={-1}
              style={maxWidth ? { width: `min(${maxWidth}px, 90vw)` } : undefined}
              onClick={(event) => event.stopPropagation()}
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
                    {cancelLabel}
                  </Button>
                )}
                <Button
                  color={confirmColor}
                  variant="filled"
                  size="medium"
                  disabled={confirmDisabled}
                  onClick={onConfirm}
                >
                  {confirmLabel}
                </Button>
              </div>
            </div>
          </div>
        </Portal>
      )}
    </>
  );
}
