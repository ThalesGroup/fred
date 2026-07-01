// Copyright Thales 2025
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

/**
 * ResizablePaneShell
 * ------------------
 * The shared right-hand pane shell: a divider the user can drag to resize, plus the
 * smooth open/close width animation (0 ⇄ paneWidth) that lets the chat (flex:1) grow and
 * shrink in lockstep instead of snapping. It owns nothing about the pane's *content* —
 * callers pass whatever surface they want (the writable-document editor, the PPT preview).
 *
 * Extracted from ChatBotView so the writable-document pane and the PPT preview pane share
 * one implementation of resize + animation rather than each re-deriving it.
 *
 * Exactly one pane is shown at a time (the parent decides which `children` to pass); this
 * shell only renders when `open` is true (kept mounted through the closing transition).
 */

import { Box, useTheme } from "@mui/material";
import { useEffect, useState } from "react";
import { useResizablePane } from "./useResizablePane.ts";

export function ResizablePaneShell({
  open,
  children,
  onWidthChange,
  onDraggingChange,
}: {
  /** Whether the pane should be visible. Toggling drives the width animation. */
  open: boolean;
  /** The pane surface to render (only mounted while the shell is rendered). */
  children: React.ReactNode;
  /**
   * Reports the wrapper's animated target width (divider + pane, or 0 when collapsed) so
   * the parent can offset sibling overlays (e.g. a floating toolbar) in lockstep.
   */
  onWidthChange?: (width: number) => void;
  /** Reports drag start/stop so the parent can suppress its own transitions during a drag. */
  onDraggingChange?: (dragging: boolean) => void;
}) {
  const theme = useTheme();
  const { width: paneWidth, onPointerDown: onPaneResizeStart } = useResizablePane();

  // Smooth open/close: keep the wrapper mounted while it animates its width (0 ⇄ paneWidth).
  // `rendered` keeps the element alive during the closing transition; `expanded` drives the
  // animated target width. The width transition is suppressed while dragging so the drag
  // stays 1:1 with the pointer. (Mirrors the original ChatBotView pane machinery.)
  const [rendered, setRendered] = useState(open);
  const [expanded, setExpanded] = useState(open);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (open) {
      // Mount at width 0, then flip to expanded. The width:0 frame must be painted before
      // changing to the target width, otherwise the browser coalesces mount + change into
      // one paint and skips the transition. A double rAF guarantees one committed frame first.
      setRendered(true);
      let inner = 0;
      const outer = requestAnimationFrame(() => {
        inner = requestAnimationFrame(() => setExpanded(true));
      });
      return () => {
        cancelAnimationFrame(outer);
        cancelAnimationFrame(inner);
      };
    }
    setExpanded(false);
  }, [open]);

  useEffect(() => {
    // Divider net width (8 − 10 margin = -2) + pane width; 0 when collapsed.
    onWidthChange?.(expanded ? paneWidth + 6 : 0);
  }, [expanded, paneWidth, onWidthChange]);

  useEffect(() => {
    onDraggingChange?.(dragging);
  }, [dragging, onDraggingChange]);

  useEffect(() => {
    if (!dragging) return;
    const stop = () => setDragging(false);
    window.addEventListener("pointerup", stop);
    return () => window.removeEventListener("pointerup", stop);
  }, [dragging]);

  const onPaneResizeDown = (e: React.PointerEvent) => {
    setDragging(true);
    onPaneResizeStart(e);
  };

  if (!rendered) return null;

  return (
    <Box
      onTransitionEnd={(e) => {
        // Once the collapse finishes, unmount.
        if (e.propertyName === "width" && !expanded) setRendered(false);
      }}
      sx={{
        flexShrink: 0,
        minHeight: 0,
        height: "100%",
        overflow: "hidden",
        width: expanded ? paneWidth + 6 : 0,
        transition: dragging ? "none" : "width 0.2s ease-out",
      }}
    >
      <Box sx={{ display: "flex", flexDirection: "row", height: "100%", width: paneWidth + 6 }}>
        <Box
          onPointerDown={onPaneResizeDown}
          sx={{
            width: "8px",
            flexShrink: 0,
            cursor: "col-resize",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            // Pull the handle flush against the card's left border so it reads as the card's
            // edge grip, and keep it above the (transparent) pane wrapper so the grip shows.
            mr: "-10px",
            position: "relative",
            zIndex: 2,
            "&::before": {
              content: '""',
              height: "40px",
              width: "4px",
              borderRadius: "2px",
              bgcolor: theme.palette.text.disabled,
              transition: "background-color 0.15s, height 0.15s",
            },
            "&:hover::before": {
              bgcolor: theme.palette.primary.main,
              height: "56px",
            },
          }}
        />
        <Box sx={{ width: paneWidth, flexShrink: 0, minHeight: 0, height: "100%" }}>{children}</Box>
      </Box>
    </Box>
  );
}

export default ResizablePaneShell;
