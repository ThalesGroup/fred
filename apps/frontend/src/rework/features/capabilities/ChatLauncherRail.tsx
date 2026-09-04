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

// The chat's launcher rail: one icon button per side panel the conversation can
// open. Two sources feed it — the session's capabilities (viewers a plugin
// contributes) and first-party launchers the page passes in (session
// attachments). Page-root sibling of the chat body, so in-flow it reserves its
// own right-hand column.
//
// A capability launcher is only offered once its panel has something to show:
// the plugin's `useHasContent` hook answers for the open conversation. The rail
// stays put while a panel is open, the open one's launcher reading as selected
// and toggling it shut.

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import type { IconType } from "@shared/utils/Type.ts";
import { sidePanelsForCapabilities, type SidePanelEntry } from "./sidePanelRegistry";
import styles from "./ChatLauncherRail.module.css";

/** A launcher the page owns, rendered above the capability-derived ones. */
export interface ChatLauncher {
  key: string;
  label: string;
  icon: IconType;
  /** Rendered as an M3 badge on the button; nothing shows below 1. */
  badgeCount?: number;
  onOpen: () => void;
}

export interface ChatLauncherRailProps {
  /** The session's active capability ids (`selected_capability_ids`). */
  capabilityIds: readonly string[];
  /** Currently open capability panel key, or `null`. */
  activeKey: string | null;
  onActiveKeyChange: (key: string | null) => void;
  /** First-party launchers, pinned above the capability ones in order. */
  launchers?: ChatLauncher[];
}

const entryKey = (entry: SidePanelEntry): string => `${entry.capabilityId}:${entry.widget}`;

const alwaysHasContent = () => true;

const titleOf = (t: TFunction, entry: SidePanelEntry): string =>
  t(`capability.${entry.capabilityId}.panel.${entry.widget}.title`, { defaultValue: entry.widget });
// The rail button says which viewer it opens ("HTML/CSS viewer", …); it falls
// back to the panel title when a capability declares no dedicated launcher label.
const launcherLabelOf = (t: TFunction, entry: SidePanelEntry): string =>
  t(`capability.${entry.capabilityId}.panel.${entry.widget}.launcher`, { defaultValue: titleOf(t, entry) });

function RailButton({
  label,
  icon,
  badgeCount,
  selected = false,
  onOpen,
}: Omit<ChatLauncher, "key"> & { selected?: boolean }) {
  return (
    <Tooltip text={label} placement="left">
      <IconButton
        // The open panel's launcher reads as selected through the M3 filled
        // tonal variant, so the rail says which viewer is showing.
        variant={selected ? "tonal" : "icon"}
        size="small"
        icon={{ category: "outlined", type: icon }}
        aria-label={label}
        aria-pressed={selected}
        badgeCount={badgeCount}
        onClick={onOpen}
      />
    </Tooltip>
  );
}

/**
 * One capability panel's launcher. It is its own component so each
 * `useHasContent` runs in a stable hook slot — mapping the hooks inline would
 * reorder them the moment a session gains or loses a capability.
 */
function PanelLauncher({
  entry,
  label,
  selected,
  onToggle,
}: {
  entry: SidePanelEntry;
  label: string;
  selected: boolean;
  onToggle: () => void;
}) {
  const useHasContent = entry.useHasContent ?? alwaysHasContent;
  if (!useHasContent()) return null;

  return <RailButton label={label} icon={entry.icon} selected={selected} onOpen={onToggle} />;
}

export function ChatLauncherRail({
  capabilityIds,
  activeKey,
  onActiveKeyChange,
  launchers = [],
}: ChatLauncherRailProps) {
  const { t } = useTranslation();
  const entries = useMemo(() => sidePanelsForCapabilities(capabilityIds), [capabilityIds]);
  // The rail outlives an open panel: it sits in its own in-flow column beside
  // the viewer, so switching viewers — or reaching the attachments — no longer
  // means closing what is open first.
  if (entries.length === 0 && launchers.length === 0) return null;

  return (
    <div className={styles.rail}>
      {launchers.map((launcher) => (
        <RailButton
          key={launcher.key}
          label={launcher.label}
          icon={launcher.icon}
          badgeCount={launcher.badgeCount}
          onOpen={launcher.onOpen}
        />
      ))}
      {entries.map((entry) => (
        <PanelLauncher
          key={entryKey(entry)}
          entry={entry}
          label={launcherLabelOf(t, entry)}
          selected={entryKey(entry) === activeKey}
          // Clicking the open one closes it, so the launcher is the way in and
          // the way out.
          onToggle={() => onActiveKeyChange(entryKey(entry) === activeKey ? null : entryKey(entry))}
        />
      ))}
    </div>
  );
}
