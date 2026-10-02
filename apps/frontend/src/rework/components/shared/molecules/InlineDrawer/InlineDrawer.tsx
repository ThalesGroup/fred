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

import { PropsWithChildren, ReactNode, useCallback, useLayoutEffect, useId, useRef } from "react";
import IconButton from "../../atoms/IconButton/IconButton.tsx";
import { usePaneResize } from "../../../../core/hooks/usePaneResize.ts";
import { FOCUSABLE, isVisibleFocusable } from "../../utils/focus";
import styles from "./InlineDrawer.module.css";

// Overlay drawers paint above push drawers; peers follow DOM paint order.
const openDrawers = new Set<HTMLElement>();
function topDrawer(document: Document): HTMLElement | undefined {
  return [...openDrawers]
    .filter((node) => node.ownerDocument === document && node.isConnected)
    .sort((a, b) => {
      const layer = (node: HTMLElement) => (node.dataset.layout === "overlay" ? 1 : 0);
      return layer(a) - layer(b) || (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);
    })
    .pop();
}

// Preserve consumer-owned inert state while an overlay owns interaction.
// Ancestors of a nested overlay cannot themselves be inert: block their other
// branches, leaving the path to the active drawer and its backdrop available.
const backdrops = new WeakMap<HTMLElement, HTMLElement>();
const blockedBranches = new Map<HTMLElement, boolean>();
function syncDrawerInteraction(document: Document) {
  for (const [node, wasInert] of blockedBranches) {
    if (node.ownerDocument !== document) continue;
    node.inert = wasInert || node.dataset.open === "false";
    blockedBranches.delete(node);
  }
  const top = topDrawer(document);
  if (!top || top.dataset.layout !== "overlay") return;
  const backdrop = backdrops.get(top);
  const block = (node: HTMLElement) => {
    if (node === top || node === backdrop) return;
    if (node.contains(top) || (backdrop && node.contains(backdrop))) {
      for (const child of node.children) {
        if (child instanceof HTMLElement) block(child);
      }
    } else {
      if (!blockedBranches.has(node)) blockedBranches.set(node, node.inert);
      node.inert = true;
    }
  };
  for (const drawer of openDrawers) {
    if (drawer.ownerDocument !== document || drawer === top) continue;
    block(drawer);
    const lowerBackdrop = backdrops.get(drawer);
    if (lowerBackdrop) block(lowerBackdrop);
  }
}

export interface InlineDrawerResizeSpec {
  /** localStorage identity for the persisted width — one key per drawer family. */
  persistKey: string;
  /** Drag bounds (px). Default 320–900, the legacy chat pane's bounds. */
  minWidth?: number;
  maxWidth?: number;
  /** Viewport-width cap as a fraction (0–1). Default 0.45; raise it for a drawer
   * meant to take most of the page (e.g. a full-height document preview). */
  maxViewportFraction?: number;
}

interface InlineDrawerBaseProps {
  open: boolean;
  onClose: () => void;
  title: string;
  closeLabel?: string;
  resizeLabel?: string;
  /** Optional content rendered immediately after the visible title. */
  titleAccessory?: ReactNode;
  /** Optional action(s) rendered in the header, immediately left of the close button. */
  headerActions?: ReactNode;
  /** Drawer shell background (CSS color/token). Defaults to `--surface-container`. */
  background?: string;
  /**
   * Open/close duration for the push layout (any CSS time, ideally a
   * `--duration-*` token). Defaults to `--duration-medium-1` (250ms).
   */
  duration?: string;
  /** Tightens the title band (12px above, 8px below) for a narrow panel. */
  compactHeader?: boolean;
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
   * Drop the body's default padding so full-bleed content (a PDF page, an image)
   * can use the whole width. The content then owns its own insets.
   */
  flushBody?: boolean;
  /**
   * Render the panel as a detached floating card (push layout): inset from every
   * edge, a single `outline-retreat` border, `--radius-l` corners and a subtle
   * shadow, dropping the drawer's flush edge border and the header divider.
   * Opt-in — default panels stay flush.
   */
  floating?: boolean;
  /**
   * Drop the drawer's own title band for content that already has one (a
   * capability pane naming the artefact it holds). The drawer then contributes no
   * chrome at all, so the content MUST offer its own close affordance — `title`
   * still names the panel, as the drawer's accessible name. `headerActions` are
   * not rendered.
   */
  hideHeader?: boolean;
}

export type InlineDrawerProps = InlineDrawerBaseProps &
  (
    | {
        resizable?: undefined;
        /** Width in CSS units. Defaults to "480px". */
        width?: string;
      }
    | {
        /** Push-layout drag resize; persists the chosen pixel width under persistKey. */
        resizable: InlineDrawerResizeSpec;
        layout: "push";
        /** Initial width in pixels only. Defaults to "480px"; persisted widths take precedence. */
        width?: `${number}px`;
      }
  );

export function InlineDrawer({
  open,
  onClose,
  title,
  closeLabel = "Close panel",
  resizeLabel = "Resize panel",
  titleAccessory,
  headerActions,
  width = "480px",
  background,
  duration,
  compactHeader = false,
  layout = "overlay",
  resizable,
  flushBody = false,
  floating = false,
  hideHeader = false,
  children,
}: PropsWithChildren<InlineDrawerProps>) {
  const titleId = useId();
  const drawerRef = useRef<HTMLElement | null>(null);
  const ownedFocusEvents = useRef(new WeakSet<Event>());
  const lastOwnedFocus = useRef<HTMLElement | null>(null);
  const backdropRef = useRef<HTMLDivElement | null>(null);
  // Hooks must run unconditionally — without `resizable` the hook only reads a
  // never-written storage key and its handlers are never attached.
  if (resizable && layout !== "push") {
    throw new Error('InlineDrawer: resizable requires layout="push".');
  }
  const seedWidthPx = Number(width.slice(0, -2));
  if (resizable && (!width.endsWith("px") || !Number.isFinite(seedWidthPx))) {
    throw new Error('InlineDrawer: resizable width must use pixels (for example, "480px").');
  }
  const resize = usePaneResize({
    storageKey: `inline-drawer:${resizable?.persistKey ?? "unused"}:width`,
    initialWidth: resizable ? seedWidthPx : 480,
    minWidth: resizable?.minWidth,
    maxWidth: resizable?.maxWidth,
    maxViewportFraction: resizable?.maxViewportFraction,
    paneRef: drawerRef,
  });
  const resizeEnabled = resizable !== undefined && layout === "push";
  const capVw = (resizable?.maxViewportFraction ?? 0.45) * 100;
  // Push drawers take real layout space from the flex row they sit in — cap
  // at a fraction of the viewport so a wide `width` can't force the sibling
  // main column below a usable size on narrow windows. Overlay
  // drawers float over content and don't need the same guard. (The resized
  // width is already clamped to the same 45vw in JS; the CSS min() stays as a
  // guard against window shrinks between renders.)
  const drawerWidth = resizeEnabled
    ? `min(${resize.width}px, ${capVw}vw)`
    : layout === "push"
      ? `min(${width}, 45vw)`
      : width;

  // Blur before telling the host to close: closing sets aria-hidden={true} on
  // `aside` (below), and if the currently focused element is still inside it
  // at that point, the browser blocks the aria-hidden change and logs
  // "Blocked aria-hidden on an element because its descendant retained
  // focus." Blurring synchronously, before `onClose` triggers the state
  // update, guarantees focus has already left the subtree by the time React
  // commits `aria-hidden="true"`.
  const handleClose = useCallback(() => {
    const active = document.activeElement;
    if (active instanceof HTMLElement && drawerRef.current?.contains(active)) {
      active.blur();
    }
    onClose();
  }, [onClose]);

  useLayoutEffect(() => {
    if (!open) return;
    const drawer = drawerRef.current!;
    openDrawers.add(drawer);
    if (backdropRef.current) backdrops.set(drawer, backdropRef.current);
    else backdrops.delete(drawer);
    syncDrawerInteraction(drawer.ownerDocument);
    let pendingClose: ReturnType<typeof setTimeout> | undefined;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.isComposing || topDrawer(drawer.ownerDocument) !== drawer) return;
      // Dialog and drawer listeners can register in either order on window.
      // Browsers can flush microtasks between native listeners. A timer waits
      // for every listener, including a nested Dialog, to consume the event.
      clearTimeout(pendingClose);
      pendingClose = setTimeout(() => {
        if (!e.defaultPrevented && topDrawer(drawer.ownerDocument) === drawer) handleClose();
      }, 0);
    };
    window.addEventListener("keydown", handleKey);
    return () => {
      clearTimeout(pendingClose);
      openDrawers.delete(drawer);
      syncDrawerInteraction(drawer.ownerDocument);
      window.removeEventListener("keydown", handleKey);
    };
  });

  useLayoutEffect(() => {
    if (!open || layout !== "overlay") return;
    const drawer = drawerRef.current!;
    const doc = drawer.ownerDocument;
    const origin = doc.activeElement instanceof HTMLElement ? doc.activeElement : null;
    const focusable = () =>
      [...drawer.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((node) => isVisibleFocusable(node, drawer));
    const focusInside = () => (focusable()[0] ?? drawer).focus();
    const onFocus = (event: FocusEvent) => {
      if (topDrawer(doc) !== drawer || ownedFocusEvents.current.has(event) || drawer.contains(event.target as Node))
        return;
      const last = lastOwnedFocus.current;
      if (last?.isConnected && isVisibleFocusable(last, drawer)) last.focus();
      else focusInside();
    };
    const onTab = (event: KeyboardEvent) => {
      if (
        event.key !== "Tab" ||
        event.defaultPrevented ||
        topDrawer(doc) !== drawer ||
        !drawer.contains(event.target as Node)
      )
        return;
      const nodes = focusable();
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (
        !first ||
        (event.shiftKey && (doc.activeElement === first || doc.activeElement === drawer)) ||
        (!event.shiftKey && doc.activeElement === last)
      ) {
        event.preventDefault();
        (event.shiftKey ? (last ?? drawer) : (first ?? drawer)).focus();
      }
    };
    doc.defaultView!.addEventListener("focusin", onFocus);
    doc.defaultView!.addEventListener("keydown", onTab);
    const focusOnOpen = () => {
      if (
        topDrawer(doc) === drawer &&
        (!drawer.contains(doc.activeElement) || doc.activeElement === drawer) &&
        (doc.activeElement !== lastOwnedFocus.current || doc.activeElement === drawer)
      )
        focusInside();
    };
    const onTransitionEnd = (event: TransitionEvent) => {
      if (event.target === drawer) focusOnOpen();
    };
    drawer.addEventListener("transitionend", onTransitionEnd);
    focusOnOpen();
    // visibility transitions can still hide the panel during the layout effect.
    const focusFrame = doc.defaultView!.requestAnimationFrame(focusOnOpen);
    return () => {
      drawer.removeEventListener("transitionend", onTransitionEnd);
      doc.defaultView!.cancelAnimationFrame(focusFrame);
      doc.defaultView!.removeEventListener("focusin", onFocus);
      doc.defaultView!.removeEventListener("keydown", onTab);
      lastOwnedFocus.current = null;
      // Registration cleanup restores underlying drawers before focus returns.
      queueMicrotask(() => {
        if (origin?.isConnected && !origin.closest("[inert]")) origin.focus();
      });
    };
  }, [open, layout]);

  return (
    <>
      {layout === "overlay" && (
        <div
          ref={backdropRef}
          className={styles.backdrop}
          data-open={open}
          aria-hidden="true"
          inert={!open}
          onClick={handleClose}
        />
      )}
      <aside
        ref={drawerRef}
        tabIndex={-1}
        onFocusCapture={(event) => {
          ownedFocusEvents.current.add(event.nativeEvent);
          lastOwnedFocus.current = event.target as HTMLElement;
        }}
        className={styles.drawer}
        data-open={open}
        data-layout={layout}
        data-floating={floating ? "true" : undefined}
        data-compact-header={compactHeader ? "true" : undefined}
        data-dragging={resizeEnabled && resize.dragging ? "true" : undefined}
        inert={!open}
        role={layout === "overlay" ? "dialog" : undefined}
        aria-modal={layout === "overlay" && open ? true : undefined}
        aria-hidden={!open}
        aria-labelledby={hideHeader ? undefined : titleId}
        aria-label={hideHeader ? title : undefined}
        style={
          {
            "--drawer-width": drawerWidth,
            ...(background ? { "--drawer-background": background } : {}),
            ...(duration ? { "--drawer-duration": duration } : {}),
          } as React.CSSProperties
        }
      >
        {resizeEnabled && (
          <div
            className={styles.resizeHandle}
            role="separator"
            aria-orientation="vertical"
            aria-label={resizeLabel}
            {...resize.handleProps}
          />
        )}
        <div className={styles.panel}>
          {!hideHeader && (
            <div className={styles.header}>
              <div className={styles.titleGroup}>
                <span id={titleId} className={styles.title}>
                  {title}
                </span>
                {titleAccessory}
              </div>
              <div className={styles.headerActions}>
                {headerActions}
                <IconButton
                  type="button"
                  variant="icon"
                  size="small"
                  icon={{ category: "outlined", type: "close" }}
                  aria-label={closeLabel}
                  onClick={handleClose}
                />
              </div>
            </div>
          )}
          <div className={`${styles.body}${flushBody ? ` ${styles.bodyFlush}` : ""}`}>{children}</div>
        </div>
      </aside>
    </>
  );
}
