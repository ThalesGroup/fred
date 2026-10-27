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

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { CapabilityCatalogEntry } from "../../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi.ts";
import { CapabilityCard } from "../CapabilityCard/CapabilityCard.tsx";
import { ToolPackCard } from "../ToolPackCard/ToolPackCard.tsx";
import {
  applyPackToggle,
  derivePackChecked,
  isPackSelectable,
  type CapabilitySelectionState,
} from "../toolPackLogic.ts";
import { TOOL_PACK_SECTIONS, type ToolPack, type ToolPackSection } from "../toolPacks.ts";
import styles from "./SimpleCapabilitiesView.module.css";

interface SimpleCapabilitiesViewProps {
  /** Team's admin-enabled capability ids (from the template's available_capabilities). */
  availableIds: ReadonlySet<string>;
  /** Template's own supports_capabilities (unfiltered by team grants). False: no
   *  packs to pick, the agent's included capabilities are listed instead. */
  supportsCapabilities: boolean;
  /** Capabilities included with an agent that offers no free selection. */
  includedCapabilities?: readonly CapabilityCatalogEntry[];
  /** Config UI shown inside one included capability's card. */
  renderIncludedOptions?: (capability: CapabilityCatalogEntry) => ReactNode;
  selection: CapabilitySelectionState;
  disabled: boolean;
  /** Journey-specific packs and activation restrictions, separate from catalog availability. */
  sections?: readonly ToolPackSection[];
  isPackDisabled?: (pack: ToolPack) => boolean;
  onSelectionChange: (next: CapabilitySelectionState) => void;
  /** Optional per-pack options UI (e.g. the PowerPoint template upload), shown
   *  inside the card while the pack is active. Returns `undefined` for packs
   *  with nothing to configure. */
  renderPackOptions?: (pack: ToolPack) => ReactNode;
}

/**
 * The Simple capabilities view (#2220): sections of "capability pack" cards
 * that bundle related capabilities behind one switch, so a non-technical user
 * enables a coherent feature without reasoning about individual capabilities.
 * A pure presentation layer over the form's existing capability selection —
 * see `toolPackLogic.ts` for the derive/toggle rules. An agent without free
 * selection gets no capability packs: its included capabilities are listed,
 * always on and configurable.
 */
export function SimpleCapabilitiesView({
  availableIds,
  supportsCapabilities,
  includedCapabilities = [],
  renderIncludedOptions,
  selection,
  disabled,
  sections = TOOL_PACK_SECTIONS,
  isPackDisabled,
  onSelectionChange,
  renderPackOptions,
}: SimpleCapabilitiesViewProps) {
  const { t } = useTranslation();
  const activeIds = new Set(selection.selectedCapabilityIds);

  return (
    <div className={styles.view}>
      {sections.map((section) => {
        if (section.packs.length > 0 && !supportsCapabilities) return null;
        // A pack the admin has opened nothing for is a dead switch; drop it,
        // and drop a section left with none rather than print a bare heading.
        // An agent still carrying a withdrawn capability is not left
        // unexplained: the form's suspension banner names it.
        const visiblePacks = section.packs.filter((pack) => isPackSelectable(pack, availableIds));
        if (visiblePacks.length === 0) return null;

        return (
          <section key={section.id} className={styles.section}>
            <h3 className={styles.sectionHeader}>{t(section.titleKey)}</h3>
            <ul className={styles.packList}>
              {visiblePacks.map((pack) => (
                <ToolPackCard
                  key={pack.id}
                  pack={pack}
                  checked={derivePackChecked(pack, selection, availableIds)}
                  disabled={disabled || isPackDisabled?.(pack) === true}
                  availableIds={availableIds}
                  activeIds={activeIds}
                  onToggle={(nextOn) => onSelectionChange(applyPackToggle(pack, nextOn, selection, availableIds))}
                  options={renderPackOptions?.(pack)}
                />
              ))}
            </ul>
          </section>
        );
      })}
      {!supportsCapabilities &&
        (includedCapabilities.length > 0 ? (
          <section className={styles.section}>
            <h3 className={styles.sectionHeader}>{t("rework.teams.formAgent.capabilities.builtIn.section")}</h3>
            <ul className={styles.packList}>
              {includedCapabilities.map((capability) => (
                <CapabilityCard
                  key={capability.id}
                  name={t(capability.name, { defaultValue: capability.name })}
                  description={t(capability.description, { defaultValue: capability.description })}
                  included
                  subForm={renderIncludedOptions?.(capability)}
                />
              ))}
            </ul>
          </section>
        ) : (
          <p className={styles.emptyState}>{t("rework.teams.formAgent.capabilities.builtIn.none")}</p>
        ))}
    </div>
  );
}
