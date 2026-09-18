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

// The capability side-panel slot (RFC §9 item 3): a single `InlineDrawer
// layout="push"` that reflows the chat body. Which panels appear is driven
// entirely by the session's `selected_capability_ids`, resolved through the one
// plugin index.
//
// It mounts inside the chat body so its push drawer reflows the conversation;
// the buttons that open these panels live in `ChatLauncherRail`, a page-root
// sibling of the body.
//
// A panel is only offered once it has something to show: the plugin's
// `useHasContent` hook answers for the open conversation, so a fresh chat with
// ppt_filler and writable_document active shows no chrome at all until the agent
// actually produces a deck or a document.

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDispatch } from "react-redux";
import type { TFunction } from "i18next";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { sidePanelsForCapabilities, type SidePanelEntry } from "./sidePanelRegistry";
import { requestSidePanelOpen } from "./sidePanelOpenRequestSlice";
import { wasPanelOpen } from "./capabilityPanelMemory";
import { useOpenSessionId } from "./useOpenSessionId";
import styles from "./CapabilitySidePanelHost.module.css";

interface CapabilitySidePanelHostProps {
  /** The session's active capability ids (`selected_capability_ids`). */
  capabilityIds: readonly string[];
  /**
   * Currently open panel key (`${capabilityId}:${widget}`), or `null`.
   * Controlled by the host page so it can enforce a single open push-drawer
   * across capability panels AND the session attachments drawer —
   * two independently-opened push drawers would otherwise cumulate width.
   */
  activeKey: string | null;
  onActiveKeyChange: (key: string | null) => void;
}

const entryKey = (entry: SidePanelEntry): string => `${entry.capabilityId}:${entry.widget}`;

/** The drawer's own slide, `--duration-medium-1` (InlineDrawer.module.css). */
const PANEL_SLIDE_MS = 250;

const alwaysHasContent = () => true;

/**
 * Restores one panel for the conversation being opened: if the user left it open
 * there, and it still has something to show, ask for it back.
 *
 * Its own component so each `useHasContent` keeps a stable hook slot — mapping
 * them inline would reorder hooks the moment a session gains or loses a
 * capability (the same reason `PanelLauncher` exists).
 */
function PanelRestorer({ entry }: { entry: SidePanelEntry }) {
  const dispatch = useDispatch();
  const sessionId = useOpenSessionId();
  const useHasContent = entry.useHasContent ?? alwaysHasContent;
  const hasContent = useHasContent();
  // Content arrives asynchronously, so "nothing yet" is not "nothing": the
  // decision waits for it rather than concluding early. It is taken once per
  // VISIT — tracking only which session was decided would carry the marker
  // across a detour through a content-less conversation and back.
  const visitingRef = useRef<string | null>(null);
  const decidedRef = useRef(false);

  useEffect(() => {
    if (visitingRef.current !== sessionId) {
      visitingRef.current = sessionId;
      decidedRef.current = false;
    }
    if (!sessionId || decidedRef.current) return;
    if (!hasContent) return;
    decidedRef.current = true;
    // Read at the moment of deciding, not before: the user may have opened and
    // closed the panel by hand while the content was still on its way.
    if (!wasPanelOpen(sessionId, entryKey(entry))) return;
    dispatch(requestSidePanelOpen({ capabilityId: entry.capabilityId, widget: entry.widget }));
  }, [sessionId, hasContent, entry, dispatch]);

  return null;
}

// Each panel's launcher/drawer title resolves against the plugin's i18n keys; a
// missing translation falls back to the widget id (never a blank label).
const titleOf = (t: TFunction, entry: SidePanelEntry): string =>
  t(`capability.${entry.capabilityId}.panel.${entry.widget}.title`, { defaultValue: entry.widget });
export function CapabilitySidePanelHost({ capabilityIds, activeKey, onActiveKeyChange }: CapabilitySidePanelHostProps) {
  const { t } = useTranslation();
  const entries = useMemo(() => sidePanelsForCapabilities(capabilityIds), [capabilityIds]);
  const active = entries.find((entry) => entryKey(entry) === activeKey) ?? null;

  // `active` drives the drawer open/close; `rendered` is what is mounted inside
  // it, and lags at BOTH ends of the slide — a closing panel leaves with the
  // drawer, and an opening one mounts only once the drawer has landed, because
  // a pane's first render is a long synchronous task that would stop the
  // animation dead. Swapping panels on an open drawer is immediate (no slide).
  // Rationale: COMPONENT-UX.md.
  const [rendered, setRendered] = useState<SidePanelEntry | null>(active);
  useEffect(() => {
    if (!active) {
      if (!rendered) return;
      const timer = setTimeout(() => setRendered(null), PANEL_SLIDE_MS);
      return () => clearTimeout(timer);
    }
    if (rendered) {
      if (rendered !== active) setRendered(active);
      return;
    }
    const timer = setTimeout(() => setRendered(active), PANEL_SLIDE_MS);
    return () => clearTimeout(timer);
  }, [active, rendered]);

  const shown = rendered ?? active;
  const paneLoading = (
    <div className={styles.paneLoading} data-pane-loading>
      <Spinner />
    </div>
  );

  // No active capability contributes a panel — the slot stays inert (zero
  // chrome).
  if (entries.length === 0) return null;

  return (
    <>
      {/* Restorers observe the opened conversation whether or not any panel is
          showing, so they mount outside the drawer. */}
      {entries.map((panel) => (
        <PanelRestorer key={entryKey(panel)} entry={panel} />
      ))}
      {entries.length > 0 && (
        <InlineDrawer
          open={active !== null}
          onClose={() => onActiveKeyChange(null)}
          // Dressed for the panel it is opening onto, not the one mounted:
          // reading `rendered` alone flipped the chrome mid-slide.
          title={shown ? titleOf(t, shown) : ""}
          // A pane with its own header owns the whole column, insets included.
          hideHeader={shown?.ownsHeader ?? false}
          flushBody={shown?.ownsHeader ?? false}
          layout="push"
          // Same inset card as the chat's own panels (ChatSidePanel): equal
          // height, corners and surface, so the column looks the same whichever
          // panel is showing.
          floating
          background="var(--surface-container-high)"
          // One shared width across every capability panel (writable-document
          // editor, PPT preview, …) — the same behaviour the legacy chat's
          // ResizablePaneShell had with its single persisted pane width.
          resizable={{ persistKey: "capability-side-panel" }}
        >
          {rendered ? (
            // A code-split panel suspends only while its chunk is in flight —
            // the first open of a page load — which is why the placeholder
            // cannot live here alone.
            <Suspense fallback={paneLoading}>
              <rendered.Component capabilityId={rendered.capabilityId} onClose={() => onActiveKeyChange(null)} />
            </Suspense>
          ) : (
            // Sliding, nothing mounted yet. Same placeholder either way, so the
            // wait reads the same and a pane owning its ✕ never leaves the
            // drawer looking empty and closeless.
            active && paneLoading
          )}
        </InlineDrawer>
      )}
    </>
  );
}
