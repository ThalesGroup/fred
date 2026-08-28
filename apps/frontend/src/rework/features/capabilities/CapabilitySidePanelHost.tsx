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

// The capability side-panel slot (RFC §9 item 3) — the ONE host that mounts a
// session's active capability panels in the reserved right column.
//
// It generalizes the trace/attachments push-drawer pattern: a floating launcher
// (one button per contributed panel, matching the chat page's floating chrome)
// toggles a single `InlineDrawer layout="push"` that reflows the main column.
// Which panels appear is driven entirely by the session's
// `selected_capability_ids`, resolved through the one plugin index.
//
// A launcher is only offered once its panel has something to show: the plugin's
// `useHasContent` hook answers for the open conversation, so a fresh chat with
// ppt_filler and writable_document active shows no chrome at all until the agent
// actually produces a deck or a document.
//
// The launchers live in the floating rail only while every panel is closed; with
// one open they move into that drawer's header, where the rail would otherwise
// float on top of the drawer's own close button.

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { sessionProbesForCapabilities } from "./sessionProbeRegistry";
import { sidePanelsForCapabilities, type SidePanelEntry } from "./sidePanelRegistry";
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

const alwaysHasContent = () => true;

/**
 * One panel's launcher. It is its own component so each `useHasContent` runs in a
 * stable hook slot — mapping the hooks inline would reorder them the moment a
 * session gains or loses a capability.
 */
function PanelLauncher({ entry, label, onOpen }: { entry: SidePanelEntry; label: string; onOpen: () => void }) {
  const useHasContent = entry.useHasContent ?? alwaysHasContent;
  if (!useHasContent()) return null;

  return (
    <IconButton
      variant="icon"
      size="small"
      icon={{ category: "outlined", type: entry.icon }}
      aria-label={label}
      onClick={onOpen}
    />
  );
}

export function CapabilitySidePanelHost({ capabilityIds, activeKey, onActiveKeyChange }: CapabilitySidePanelHostProps) {
  const { t } = useTranslation();
  const entries = useMemo(() => sidePanelsForCapabilities(capabilityIds), [capabilityIds]);
  const probes = useMemo(() => sessionProbesForCapabilities(capabilityIds), [capabilityIds]);

  // No active capability contributes a panel or a probe — the slot stays inert
  // (zero chrome). Probes mount even while every panel is closed: they are the
  // "observe the opened conversation" path (#1905 auto-open).
  if (entries.length === 0 && probes.length === 0) return null;

  const active = entries.find((entry) => entryKey(entry) === activeKey) ?? null;
  // Each panel's launcher/drawer title resolves against the plugin's i18n keys;
  // a missing translation falls back to the widget id (never a blank label).
  const titleOf = (entry: SidePanelEntry): string =>
    t(`capability.${entry.capabilityId}.panel.${entry.widget}.title`, { defaultValue: entry.widget });

  // Every panel but the open one; each decides for itself whether it has
  // anything to launch onto (PanelLauncher).
  const launchers = entries
    .filter((entry) => entryKey(entry) !== activeKey)
    .map((entry) => (
      <PanelLauncher
        key={entryKey(entry)}
        entry={entry}
        label={titleOf(entry)}
        onOpen={() => onActiveKeyChange(entryKey(entry))}
      />
    ));

  return (
    <>
      {probes.map(({ capabilityId, Probe }, index) => (
        <Probe key={`${capabilityId}:${index}`} capabilityId={capabilityId} />
      ))}
      {entries.length > 0 && (
        <>
          {/* The rail floats over the right edge of the whole slot, drawer
              included, so while a panel is open it would land on that panel's
              own close button. Open, the other launchers move into the drawer's
              header instead — switching panels stays one click. */}
          {active === null && <div className={styles.rail}>{launchers}</div>}
          <InlineDrawer
            open={active !== null}
            onClose={() => onActiveKeyChange(null)}
            title={active ? titleOf(active) : ""}
            headerActions={active !== null ? launchers : undefined}
            layout="push"
            // One shared width across every capability panel (writable-document
            // editor, PPT preview, …) — the same behaviour the legacy chat's
            // ResizablePaneShell had with its single persisted pane width.
            resizable={{ persistKey: "capability-side-panel" }}
          >
            {active && <active.Component capabilityId={active.capabilityId} onClose={() => onActiveKeyChange(null)} />}
          </InlineDrawer>
        </>
      )}
    </>
  );
}
