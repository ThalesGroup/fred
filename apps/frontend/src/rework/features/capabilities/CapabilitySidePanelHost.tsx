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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { sidePanelsForCapabilities, type SidePanelEntry } from "./sidePanelRegistry";
import styles from "./CapabilitySidePanelHost.module.css";

interface CapabilitySidePanelHostProps {
  /** The session's active capability ids (`selected_capability_ids`). */
  capabilityIds: readonly string[];
}

const entryKey = (entry: SidePanelEntry): string => `${entry.capabilityId}:${entry.widget}`;

export function CapabilitySidePanelHost({ capabilityIds }: CapabilitySidePanelHostProps) {
  const { t } = useTranslation();
  const entries = useMemo(() => sidePanelsForCapabilities(capabilityIds), [capabilityIds]);
  const [openKey, setOpenKey] = useState<string | null>(null);

  // No active capability contributes a panel — the slot stays inert (zero chrome).
  if (entries.length === 0) return null;

  const active = entries.find((entry) => entryKey(entry) === openKey) ?? null;
  // Each panel's launcher/drawer title resolves against the plugin's i18n keys;
  // a missing translation falls back to the widget id (never a blank label).
  const titleOf = (entry: SidePanelEntry): string =>
    t(`capability.${entry.capabilityId}.panel.${entry.widget}.title`, { defaultValue: entry.widget });

  return (
    <>
      <div className={styles.rail}>
        {entries.map((entry) => {
          const key = entryKey(entry);
          if (key === openKey) return null; // launcher hides while its panel is open
          return (
            <IconButton
              key={key}
              color="on-surface"
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "edit_note" }}
              aria-label={titleOf(entry)}
              onClick={() => setOpenKey(key)}
            />
          );
        })}
      </div>
      <InlineDrawer
        open={active !== null}
        onClose={() => setOpenKey(null)}
        title={active ? titleOf(active) : ""}
        layout="push"
      >
        {active && <active.Component capabilityId={active.capabilityId} onClose={() => setOpenKey(null)} />}
      </InlineDrawer>
    </>
  );
}
