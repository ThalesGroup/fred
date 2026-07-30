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

import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactElement,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import styles from "./Tooltip.module.scss";

interface TooltipProps {
  text?: string;
  /** Rich content instead of a plain text hint (e.g. a multi-row info panel).
   *  Unlike `text`, the tooltip widens to fit and wraps instead of forcing a
   *  single nowrap line. Takes precedence over `text` when both are set. */
  content?: ReactNode;
  children: ReactNode;
}

// Matches --spacing-2xs (styles/spacings.css) — the gap CSS previously gave
// the tooltip for free via `margin-bottom`. A portaled tooltip is positioned
// in raw viewport pixels instead, so the same value has to be restated here.
const TOOLTIP_GAP_PX = 4;
// Minimum breathing room from the viewport edge when clamping/flipping.
const VIEWPORT_MARGIN_PX = 4;

interface TriggerRect {
  top: number;
  bottom: number;
  left: number;
  width: number;
}

// Shared across every Tooltip instance instead of per-instance state: focus
// modality (keyboard vs. pointer) is a single global fact about the current
// interaction, not something each tooltip needs its own listener pair for.
// `:focus-visible` can't be used here — it's a browser-internal heuristic
// that a synthetically dispatched FocusEvent doesn't carry, so it isn't
// exercised the same way a real Tab keypress is (and isn't testable via
// jsdom/happy-dom at all). Tracking the last keydown-vs-pointerdown directly
// mirrors what `:focus-visible` itself approximates.
let lastFocusWasKeyboard = false;

function trackFocusModality() {
  document.addEventListener("keydown", () => (lastFocusWasKeyboard = true), true);
  document.addEventListener("mousedown", () => (lastFocusWasKeyboard = false), true);
  document.addEventListener("pointerdown", () => (lastFocusWasKeyboard = false), true);
}

if (typeof document !== "undefined") trackFocusModality();

export const Tooltip = ({ text, content, children }: TooltipProps) => {
  const tooltipId = useId();
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const contentRef = useRef<HTMLSpanElement>(null);
  // Hover and keyboard-focus are tracked independently, OR'd into `visible` —
  // not collapsed into one boolean — because either can outlast the other:
  // clicking a trigger while hovering it, then moving the mouse away, must
  // not hide the tooltip while focus remains (and symmetrically for blur
  // while still hovered). The old CSS `:hover, :has(:focus-visible)` gave
  // this OR semantics for free; a single show/hide toggle driven by either
  // leave event loses it.
  const [isHovering, setIsHovering] = useState(false);
  const [isKeyboardFocused, setIsKeyboardFocused] = useState(false);
  const visible = isHovering || isKeyboardFocused;
  const [triggerRect, setTriggerRect] = useState<TriggerRect | null>(null);
  const [contentStyle, setContentStyle] = useState<CSSProperties | undefined>(undefined);

  // Rendered via a portal onto document.body: any table/panel this trigger
  // sits in clips its own overflow (scroll containers, `overflow: hidden`
  // cards, …), and the tooltip pops *above* the trigger by design — for a
  // trigger near the top of such a container there's no room left inside it,
  // so an in-place tooltip gets silently clipped to an unreadable sliver.
  // Escaping to body and positioning from the trigger's own viewport rect
  // sidesteps every ancestor's overflow instead of special-casing each one.
  const updateTriggerRect = useCallback(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setTriggerRect({ top: rect.top, bottom: rect.bottom, left: rect.left, width: rect.width });
  }, []);

  const handleMouseEnter = useCallback(() => setIsHovering(true), []);
  const handleMouseLeave = useCallback(() => setIsHovering(false), []);
  // A plain `onFocus` also fires for the lingering focus a mouse click leaves
  // behind on the trigger (e.g. clicking the preview/more icon buttons), which
  // would pop the tooltip open and pin it there until something else steals
  // focus. Gating on keyboard modality restricts this to real Tab navigation,
  // matching the hover trigger's intent.
  const handleFocus = useCallback(() => {
    if (lastFocusWasKeyboard) setIsKeyboardFocused(true);
  }, []);
  const handleBlur = useCallback(() => setIsKeyboardFocused(false), []);

  useEffect(() => {
    if (visible) {
      updateTriggerRect();
    } else {
      setTriggerRect(null);
      setContentStyle(undefined);
    }
  }, [visible, updateTriggerRect]);

  // A visible tooltip tracks the trigger's position through scroll/resize —
  // without this, scrolling the table while hovering leaves it stranded.
  useEffect(() => {
    if (!triggerRect) return;
    const onMove = () => updateTriggerRect();
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [triggerRect, updateTriggerRect]);

  // Runs after the portaled content is in the DOM but before paint, so its
  // real rendered size can be used to keep it inside the viewport instead of
  // always assuming there's room above and centered on the trigger — a
  // trigger near the top/left/right edge would otherwise push the tooltip
  // off-screen instead of merely escaping the ancestor's clipping (the bug
  // this component exists to fix).
  useLayoutEffect(() => {
    if (!triggerRect) {
      setContentStyle(undefined);
      return;
    }
    const el = contentRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();

    const fitsAbove = triggerRect.top - height - TOOLTIP_GAP_PX >= VIEWPORT_MARGIN_PX;
    const top = fitsAbove ? triggerRect.top - TOOLTIP_GAP_PX : triggerRect.bottom + TOOLTIP_GAP_PX;
    const translateY = fitsAbove ? "-100%" : "0%";

    const idealLeft = triggerRect.left + triggerRect.width / 2;
    const minLeft = VIEWPORT_MARGIN_PX + width / 2;
    const maxLeft = window.innerWidth - VIEWPORT_MARGIN_PX - width / 2;
    const left = Math.min(Math.max(idealLeft, minLeft), maxLeft);

    setContentStyle({ top, left, transform: `translate(-50%, ${translateY})` });
  }, [triggerRect]);

  const child = isValidElement(children)
    ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, { "aria-describedby": tooltipId })
    : children;

  const contentClasses = [styles["tooltip-content"]];
  if (content) contentClasses.push(styles["tooltip-content-rich"]);

  return (
    <span
      ref={wrapperRef}
      className={styles["tooltip-wrapper"]}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
    >
      {child}
      {triggerRect &&
        createPortal(
          <span
            ref={contentRef}
            id={tooltipId}
            className={contentClasses.join(" ")}
            role="tooltip"
            style={contentStyle}
          >
            {content ?? text}
          </span>,
          document.body,
        )}
    </span>
  );
};
