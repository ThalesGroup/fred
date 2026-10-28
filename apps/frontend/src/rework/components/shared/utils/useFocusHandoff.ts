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

import { type RefObject, useLayoutEffect, useRef } from "react";

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';
const ACTIVE_ITEM = '[aria-selected="true"], [aria-checked="true"], [aria-current="page"], [aria-current="true"]';

// Last input modality: a text input matches :focus-visible even after a click, so the
// ring decision follows the device that opened the surface instead.
let keyboardModality = false;
let modalityTracked = false;
// The control a click landed on is the trigger even when it did not take focus (Safari, or a
// trigger that prevents focus on mousedown).
let pressedControl: HTMLElement | null = null;
let pressedAt = 0;
let keyAt = 0;
// Older than this, no user action opened the surface (an agent's pane opening later must not steal focus).
const USER_WINDOW_MS = 1000;
const MODIFIER_KEYS = new Set(["Shift", "Control", "Alt", "Meta"]);
function trackModality() {
  if (modalityTracked || typeof document === "undefined") return;
  modalityTracked = true;
  document.addEventListener(
    "keydown",
    (event) => {
      // A modifier alone (Shift-click, Ctrl-click) is not a keyboard interaction.
      if (MODIFIER_KEYS.has(event.key)) return;
      keyboardModality = true;
      pressedControl = null;
      keyAt = performance.now();
    },
    true,
  );
  document.addEventListener(
    "pointerdown",
    (event) => {
      keyboardModality = false;
      const target = event.target instanceof Element ? event.target.closest<HTMLElement>(FOCUSABLE) : null;
      pressedControl = target;
      pressedAt = performance.now();
    },
    true,
  );
}

/** True when the last interaction came from the keyboard: decides whether returned focus shows a ring. */
export function lastInputWasKeyboard(): boolean {
  trackModality();
  return keyboardModality;
}

// Listen from load: the press that opens the first surface happens before any hook mounts.
trackModality();

const NON_TEXT_INPUTS = new Set(["button", "checkbox", "radio", "submit", "reset", "file", "image", "range", "color"]);

/** Typing somewhere: a surface that opens meanwhile (an agent's pane) must not take the caret. */
function isTextEntry(node: Element | null): boolean {
  if (!(node instanceof HTMLElement)) return false;
  if (node.isContentEditable || node instanceof HTMLTextAreaElement) return !node.hasAttribute("readonly");
  return node instanceof HTMLInputElement && !node.readOnly && !NON_TEXT_INPUTS.has(node.type);
}

function isShown(node: HTMLElement): boolean {
  return node.getClientRects().length > 0 && getComputedStyle(node).visibility !== "hidden";
}

/** The active item of a list when it has one, else the first control, else the surface itself. */
export function initialFocusTarget(surface: HTMLElement): HTMLElement {
  const controls = [...surface.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(isShown);
  const active = [...surface.querySelectorAll<HTMLElement>(ACTIVE_ITEM)].find(
    (node) => isShown(node) && (node.matches(FOCUSABLE) || node.hasAttribute("tabindex")),
  );
  return active ?? controls[0] ?? surface;
}

/**
 * Moves focus into a surface while `open` and gives it back to the element that held it before,
 * with a focus ring only when the surface was opened from the keyboard, not by a click.
 */
export function useFocusHandoff(
  open: boolean,
  surfaceRef: RefObject<HTMLElement | null>,
  pickTarget: (surface: HTMLElement) => HTMLElement = initialFocusTarget,
) {
  const pick = useRef(pickTarget);
  pick.current = pickTarget;
  trackModality();

  useLayoutEffect(() => {
    if (!open) return;
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // Focus already inside (autoFocus) is not where focus came from.
    const focused = active && !surfaceRef.current?.contains(active) ? active : null;
    const now = performance.now();
    const recentPress = now - pressedAt < USER_WINDOW_MS;
    const recentUser = recentPress || now - keyAt < USER_WINDOW_MS;
    const pressed = recentPress && pressedControl?.isConnected ? pressedControl : null;
    const trigger = pressed ?? (recentUser && focused !== document.body ? focused : null);
    // No recent user action opened it, or they are typing: leave focus alone.
    if (!trigger || isTextEntry(trigger) || isTextEntry(focused)) return;
    const ring = keyboardModality;
    let surface: HTMLElement | null = null;
    let frame = 0;
    let attempts = 0;
    // A portal or an opening transition can make the surface focusable a frame late.
    const place = () => {
      surface = surfaceRef.current;
      if (surface) {
        if (surface.contains(document.activeElement)) return;
        const target = pick.current(surface);
        if (target === surface && surface.tabIndex < 0 && !surface.hasAttribute("tabindex")) surface.tabIndex = -1;
        target.focus({ preventScroll: true, focusVisible: ring } as FocusOptions);
        if (surface.contains(document.activeElement)) return;
      }
      if (attempts++ < 5) frame = requestAnimationFrame(place);
    };
    place();
    return () => {
      cancelAnimationFrame(frame);
      const current = document.activeElement;
      const lost = !current || current === document.body || !current.isConnected;
      // A pressed item of a parent menu may be gone: fall back to what held focus at open.
      const back = [trigger, focused].find((node) => node?.isConnected && isShown(node));
      // Only reclaim focus that was in the surface; a click elsewhere keeps its own target.
      if (back && (lost || surface?.contains(current))) back.focus({ focusVisible: ring } as FocusOptions);
    };
  }, [open, surfaceRef]);
}
