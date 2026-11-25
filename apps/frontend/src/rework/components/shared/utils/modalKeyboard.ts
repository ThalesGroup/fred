// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { isTopmostModal } from "./Portal";

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

export function focusableControls(dialog: HTMLElement): HTMLElement[] {
  return [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((node) => isVisibleFocusable(node, dialog));
}

/** Shared keyboard behavior for short dialogs and full-page settings surfaces. */
export function handleModalKeyDown(
  event: KeyboardEvent,
  dialog: HTMLElement | null,
  {
    onClose,
    onConfirm,
    confirmDisabled = false,
  }: {
    onClose?: () => void;
    onConfirm?: () => void;
    confirmDisabled?: boolean;
  },
) {
  if (!dialog || event.defaultPrevented || !isTopmostModal(dialog)) return;
  if (event.key === "Escape") {
    if (onClose) {
      event.preventDefault();
      onClose();
    }
    return;
  }
  if (event.key === "Tab") {
    const focusable = focusableControls(dialog);
    if (!focusable.length) {
      event.preventDefault();
      dialog.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (
      !focusable.includes(document.activeElement as HTMLElement) ||
      (event.shiftKey && document.activeElement === first)
    ) {
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
    !onConfirm ||
    confirmDisabled
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
  onConfirm();
}
