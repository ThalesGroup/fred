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

export const Tooltip = ({ text, content, children }: TooltipProps) => {
  const tooltipId = useId();
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const [anchor, setAnchor] = useState<{ top: number; left: number } | null>(null);

  // Rendered via a portal onto document.body: any table/panel this trigger
  // sits in clips its own overflow (scroll containers, `overflow: hidden`
  // cards, …), and the tooltip pops *above* the trigger by design — for a
  // trigger near the top of such a container there's no room left inside it,
  // so an in-place tooltip gets silently clipped to an unreadable sliver.
  // Escaping to body and positioning from the trigger's own viewport rect
  // sidesteps every ancestor's overflow instead of special-casing each one.
  const updateAnchor = useCallback(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setAnchor({ top: rect.top - TOOLTIP_GAP_PX, left: rect.left + rect.width / 2 });
  }, []);

  const show = useCallback(() => updateAnchor(), [updateAnchor]);
  const hide = useCallback(() => setAnchor(null), []);

  // A visible tooltip tracks the trigger's position through scroll/resize —
  // without this, scrolling the table while hovering leaves it stranded.
  useEffect(() => {
    if (!anchor) return;
    const onMove = () => updateAnchor();
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [anchor, updateAnchor]);

  const child = isValidElement(children)
    ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, { "aria-describedby": tooltipId })
    : children;

  const contentClasses = [styles["tooltip-content"]];
  if (content) contentClasses.push(styles["tooltip-content-rich"]);

  const contentStyle: CSSProperties | undefined = anchor
    ? { top: anchor.top, left: anchor.left, transform: "translate(-50%, -100%)" }
    : undefined;

  return (
    <span
      ref={wrapperRef}
      className={styles["tooltip-wrapper"]}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {child}
      {anchor &&
        createPortal(
          <span id={tooltipId} className={contentClasses.join(" ")} role="tooltip" style={contentStyle}>
            {content ?? text}
          </span>,
          document.body,
        )}
    </span>
  );
};
