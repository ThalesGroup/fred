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

import { PropsWithChildren, ReactNode, useEffect, useId, useRef } from "react";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useInlineDrawerResize } from "./useInlineDrawerResize";
import styles from "./InlineDrawer.module.css";

interface InlineDrawerResizeSpec {
  /** localStorage identity for the persisted width — one key per drawer family. */
  persistKey: string;
  /** Drag bounds (px). Default 320–900, the legacy chat pane's bounds. */
  minWidth?: number;
  maxWidth?: number;
}

interface InlineDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Optional action(s) rendered in the header, immediately left of the close button. */
  headerActions?: ReactNode;
  /** Width in CSS units. Defaults to "480px". */
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
   * Drag-to-resize (push layout only): renders a grab handle on the drawer's
   * left edge and persists the chosen width under `persistKey`. `width` then
   * only seeds the first-ever width. Ported from the legacy chat's
   * ResizablePaneShell so capability panels keep the same UX.
   */
  resizable?: InlineDrawerResizeSpec;
}

export function InlineDrawer({
  open,
  onClose,
  title,
  headerActions,
  width = "480px",
  layout = "overlay",
  resizable,
  children,
}: PropsWithChildren<InlineDrawerProps>) {
  const titleId = useId();
  const drawerRef = useRef<HTMLElement | null>(null);
  // Hooks must run unconditionally — without `resizable` the hook only reads a
  // never-written storage key and its handlers are never attached.
  const seedWidthPx = Number.parseInt(width, 10);
  const resize = useInlineDrawerResize({
    persistKey: resizable?.persistKey ?? "unused",
    initialWidth: Number.isFinite(seedWidthPx) ? seedWidthPx : 480,
    minWidth: resizable?.minWidth,
    maxWidth: resizable?.maxWidth,
    drawerRef,
  });
  const resizeEnabled = resizable !== undefined && layout === "push";
  // Push drawers take real layout space from the flex row they sit in — cap
  // at a fraction of the viewport so a wide `width` can't force the sibling
  // main column below a usable size on narrow windows. Overlay
  // drawers float over content and don't need the same guard. (The resized
  // width is already clamped to the same 45vw in JS; the CSS min() stays as a
  // guard against window shrinks between renders.)
  const drawerWidth = resizeEnabled
    ? `min(${resize.width}px, 45vw)`
    : layout === "push"
      ? `min(${width}, 45vw)`
      : width;

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
        ref={drawerRef}
        className={styles.drawer}
        data-open={open}
        data-layout={layout}
        data-dragging={resizeEnabled && resize.dragging ? "true" : undefined}
        aria-hidden={!open}
        aria-labelledby={titleId}
        style={{ "--drawer-width": drawerWidth } as React.CSSProperties}
      >
        {resizeEnabled && (
          <div
            className={styles.resizeHandle}
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize panel"
            {...resize.handleProps}
          />
        )}
        <div className={styles.panel}>
          <div className={styles.header}>
            <span id={titleId} className={styles.title}>
              {title}
            </span>
            <div className={styles.headerActions}>
              {headerActions}
              <IconButton
                color="on-surface"
                variant="icon"
                size="small"
                icon={{ category: "outlined", type: "close" }}
                aria-label="Close panel"
                onClick={onClose}
              />
            </div>
          </div>
          <div className={styles.body}>{children}</div>
        </div>
      </aside>
    </>
  );
}
