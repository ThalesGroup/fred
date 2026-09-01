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
// layout="push"` (CapabilitySidePanelHost) that reflows the chat body, plus its
// launcher rail (CapabilityLauncherRail). Which panels appear is driven entirely
// by the session's `selected_capability_ids`, resolved through the one plugin
// index.
//
// The two mount at different DOM levels: the host sits inside the chat body so
// its push drawer reflows the conversation; the rail sits at the page root, a
// flex sibling of the body, so in-flow it reserves its own right-hand column.
//
// A launcher is only offered once its panel has something to show: the plugin's
// `useHasContent` hook answers for the open conversation, so a fresh chat with
// ppt_filler and writable_document active shows no chrome at all until the agent
// actually produces a deck or a document. The rail shows only while every panel
// is closed; opening one retires it entirely.

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
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

// Each panel's launcher/drawer title resolves against the plugin's i18n keys; a
// missing translation falls back to the widget id (never a blank label).
const titleOf = (t: TFunction, entry: SidePanelEntry): string =>
  t(`capability.${entry.capabilityId}.panel.${entry.widget}.title`, { defaultValue: entry.widget });
// The rail button says which viewer it opens ("HTML/CSS viewer", …); it falls
// back to the panel title when a capability declares no dedicated launcher label.
const launcherLabelOf = (t: TFunction, entry: SidePanelEntry): string =>
  t(`capability.${entry.capabilityId}.panel.${entry.widget}.launcher`, { defaultValue: titleOf(t, entry) });

/**
 * One panel's launcher. It is its own component so each `useHasContent` runs in a
 * stable hook slot - mapping the hooks inline would reorder them the moment a
 * session gains or loses a capability.
 */
function PanelLauncher({ entry, label, onOpen }: { entry: SidePanelEntry; label: string; onOpen: () => void }) {
  const useHasContent = entry.useHasContent ?? alwaysHasContent;
  if (!useHasContent()) return null;

  return (
    <Tooltip text={label} placement="left">
      <IconButton
        variant="icon"
        size="small"
        icon={{ category: "outlined", type: entry.icon }}
        aria-label={label}
        onClick={onOpen}
      />
    </Tooltip>
  );
}

/**
 * The launcher rail — one icon button per side panel the session's capabilities
 * contribute. Mounts at the page root (a flex sibling of the chat body) so it
 * reserves its own right-hand column in-flow. Shows only while every panel is
 * closed; opening one (`activeKey` set) retires the whole rail.
 */
export function CapabilityLauncherRail({ capabilityIds, activeKey, onActiveKeyChange }: CapabilitySidePanelHostProps) {
  const { t } = useTranslation();
  const entries = useMemo(() => sidePanelsForCapabilities(capabilityIds), [capabilityIds]);
  const active = entries.find((entry) => entryKey(entry) === activeKey) ?? null;
  if (entries.length === 0 || active !== null) return null;

  return (
    <div className={styles.rail}>
      {entries.map((entry) => (
        <PanelLauncher
          key={entryKey(entry)}
          entry={entry}
          label={launcherLabelOf(t, entry)}
          onOpen={() => onActiveKeyChange(entryKey(entry))}
        />
      ))}
    </div>
  );
}

export function CapabilitySidePanelHost({ capabilityIds, activeKey, onActiveKeyChange }: CapabilitySidePanelHostProps) {
  const { t } = useTranslation();
  const entries = useMemo(() => sidePanelsForCapabilities(capabilityIds), [capabilityIds]);
  const probes = useMemo(() => sessionProbesForCapabilities(capabilityIds), [capabilityIds]);
  const active = entries.find((entry) => entryKey(entry) === activeKey) ?? null;

  // Keep the closing panel mounted through the drawer's close animation (250ms)
  // so its content fades out with the panel instead of vanishing the instant the
  // launcher is dismissed: `active` drives open/close, `rendered` lags it on the
  // way down.
  const [rendered, setRendered] = useState<SidePanelEntry | null>(active);
  useEffect(() => {
    if (active) {
      setRendered(active);
      return;
    }
    const timer = setTimeout(() => setRendered(null), 250);
    return () => clearTimeout(timer);
  }, [active]);

  // No active capability contributes a panel or a probe — the slot stays inert
  // (zero chrome). Probes mount even while every panel is closed: they are the
  // "observe the opened conversation" path (#1905 auto-open).
  if (entries.length === 0 && probes.length === 0) return null;

  return (
    <>
      {probes.map(({ capabilityId, Probe }, index) => (
        <Probe key={`${capabilityId}:${index}`} capabilityId={capabilityId} />
      ))}
      {entries.length > 0 && (
        <InlineDrawer
          open={active !== null}
          onClose={() => onActiveKeyChange(null)}
          title={rendered ? titleOf(t, rendered) : ""}
          // A pane with its own header owns the whole column, insets included.
          hideHeader={rendered?.ownsHeader ?? false}
          flushBody={rendered?.ownsHeader ?? false}
          layout="push"
          // One shared width across every capability panel (writable-document
          // editor, PPT preview, …) — the same behaviour the legacy chat's
          // ResizablePaneShell had with its single persisted pane width.
          resizable={{ persistKey: "capability-side-panel" }}
        >
          {rendered && (
            <rendered.Component capabilityId={rendered.capabilityId} onClose={() => onActiveKeyChange(null)} />
          )}
        </InlineDrawer>
      )}
    </>
  );
}
