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

import { PropsWithChildren, useEffect, useId } from "react";
import IconButton from "@shared/atoms/IconButton/IconButton";
import styles from "./InlineDrawer.module.css";
import { useResizablePane } from "./useResizablePane";

interface InlineDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Width in CSS units. Defaults to "480px". Ignored while `resizable`. */
  width?: string;
  /**
   * Layout mode.
   * - `"overlay"` (default): floats over the page with a dimming backdrop.
   * - `"push"`: takes layout space on the right; the host's main column reflows
   *   (e.g. the chat shifts left). No backdrop — content stays interactive.
   *
   * `push` only reflows siblings when the drawer's parent is a flex row and the
   * rest of the content lives in a sibling `flex: 1` column.
   */
  layout?: "overlay" | "push";
  /**
   * Hide the drawer's own chrome header (title + close button) and body
   * padding. For panels that render their OWN header/close (e.g. capability
   * side panels styled as floating cards) — keeps exactly one close button.
   */
  hideHeader?: boolean;
  /**
   * Make the drawer resizable by dragging its left edge (push layout only).
   * The chosen width is clamped to [320, 900] px, still capped at 45vw, and
   * persisted under `resizeStorageKey`.
   */
  resizable?: boolean;
  /** localStorage key for the persisted resizable width. */
  resizeStorageKey?: string;
}

export function InlineDrawer({
  open,
  onClose,
  title,
  width = "480px",
  layout = "overlay",
  hideHeader = false,
  resizable = false,
  resizeStorageKey = "inlineDrawer:paneWidth",
  children,
}: PropsWithChildren<InlineDrawerProps>) {
  const titleId = useId();
  const { width: paneWidth, dragging, onPointerDown } = useResizablePane(resizeStorageKey);
  const isResizable = resizable && layout === "push";
  // Push drawers take real layout space from the flex row they sit in — cap
  // at a fraction of the viewport so a wide `width` can't force the sibling
  // main column below a usable size on narrow windows. Overlay
  // drawers float over content and don't need the same guard.
  const requestedWidth = isResizable ? `${paneWidth}px` : width;
  const drawerWidth = layout === "push" ? `min(${requestedWidth}, 45vw)` : width;

  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  return (
    <>
      {layout === "overlay" && (
        <div className={styles.backdrop} data-open={open} aria-hidden={!open} onClick={onClose} />
      )}
      <aside
        className={styles.drawer}
        data-open={open}
        data-layout={layout}
        data-headless={hideHeader || undefined}
        data-dragging={(isResizable && dragging) || undefined}
        aria-hidden={!open}
        aria-labelledby={hideHeader ? undefined : titleId}
        aria-label={hideHeader ? title : undefined}
        style={{ "--drawer-width": drawerWidth } as React.CSSProperties}
      >
        {isResizable && open && (
          <div
            className={styles.resizeHandle}
            role="separator"
            aria-orientation="vertical"
            aria-label={title}
            onPointerDown={onPointerDown}
          />
        )}
        <div className={styles.panel}>
          {!hideHeader && (
            <div className={styles.header}>
              <span id={titleId} className={styles.title}>
                {title}
              </span>
              <IconButton
                color="on-surface"
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "close" }}
                aria-label="Close panel"
                onClick={onClose}
              />
            </div>
          )}
          <div className={styles.body}>{children}</div>
        </div>
      </aside>
    </>
  );
}
