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

// The one shell every chat side panel wears. Three panels had drifted into
// three slightly different InlineDrawer configurations; this fixes the
// treatment in one place so a new panel inherits it instead of re-deciding.

import type { PropsWithChildren, ReactNode } from "react";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import styles from "./ChatSidePanel.module.css";

export interface ChatSidePanelProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Storage key for the drag-to-resize width. Must be unique per panel. */
  persistKey: string;
  /** Seeds the first-ever width only; the user's drag wins afterwards. */
  width?: string;
  /** Rendered in the header, immediately left of the close button. */
  headerActions?: ReactNode;
  /**
   * Make the body fill the drawer height so a child can own the scrolling and
   * whatever sits above it stays pinned. Leave off when the content should
   * simply grow and let the drawer scroll as a whole.
   */
  fill?: boolean;
}

export default function ChatSidePanel({
  open,
  onClose,
  title,
  persistKey,
  width,
  headerActions,
  fill = false,
  children,
}: PropsWithChildren<ChatSidePanelProps>) {
  return (
    <InlineDrawer
      open={open}
      onClose={onClose}
      title={title}
      width={width}
      headerActions={headerActions}
      layout="push"
      floating
      compactHeader
      background="var(--surface-container-high)"
      // Snappier than the 250ms default: these panels are a quick detour from
      // the conversation, not a context switch.
      duration="var(--duration-short-3)"
      // The body below owns its insets: the drawer's own padding would stack a
      // gap above the content on top of the one the header already leaves.
      flushBody
      resizable={{ persistKey }}
    >
      <div className={`${styles.body}${fill ? ` ${styles.bodyFill}` : ""}`}>{children}</div>
    </InlineDrawer>
  );
}
