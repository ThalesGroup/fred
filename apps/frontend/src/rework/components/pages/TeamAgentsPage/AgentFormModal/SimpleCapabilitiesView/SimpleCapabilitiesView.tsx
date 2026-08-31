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
import { ToolPackCard } from "../ToolPackCard/ToolPackCard.tsx";
import { applyPackToggle, derivePackChecked, type CapabilitySelectionState } from "../toolPackLogic.ts";
import { TOOL_PACK_SECTIONS, type ToolPack } from "../toolPacks.ts";
import styles from "./SimpleCapabilitiesView.module.css";

interface SimpleCapabilitiesViewProps {
  /** Team's admin-enabled capability ids (from the template's available_capabilities). */
  availableIds: ReadonlySet<string>;
  selection: CapabilitySelectionState;
  disabled: boolean;
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
 * see `toolPackLogic.ts` for the derive/toggle rules.
 */
export function SimpleCapabilitiesView({
  availableIds,
  selection,
  disabled,
  onSelectionChange,
  renderPackOptions,
}: SimpleCapabilitiesViewProps) {
  const { t } = useTranslation();
  const activeIds = new Set(selection.selectedCapabilityIds);
  // The template's own `available_capabilities` is now the honest signal
  // (see AgentDefinition.supports_capabilities) — empty means this agent
  // doesn't participate in capability selection at all, not just that
  // nothing happens to be enabled. A "reasoning"-kind pack maps to a plain
  // form field, not a backend capability, so it stays interactive regardless.
  const templateSupportsCapabilities = availableIds.size > 0;

  return (
    <div className={styles.view}>
      {TOOL_PACK_SECTIONS.map((section) => {
        const isCapabilityBackedSection =
          section.packs.length > 0 && section.packs.every((pack) => pack.kind === "capabilities");
        const showNotSupported = isCapabilityBackedSection && !templateSupportsCapabilities;

        return (
          <section key={section.id} className={styles.section}>
            <h3 className={styles.sectionHeader}>{t(section.titleKey)}</h3>
            {section.emptyState ? (
              <p className={styles.emptyState}>{t("rework.teams.formAgent.capabilities.actionsIntegrationEmpty")}</p>
            ) : showNotSupported ? (
              <p className={styles.emptyState}>{t("rework.teams.formAgent.capabilities.notSupported")}</p>
            ) : (
              <ul className={styles.packList}>
                {section.packs.map((pack) => (
                  <ToolPackCard
                    key={pack.id}
                    pack={pack}
                    checked={derivePackChecked(pack, selection, availableIds)}
                    disabled={disabled}
                    availableIds={availableIds}
                    activeIds={activeIds}
                    onToggle={(nextOn) => onSelectionChange(applyPackToggle(pack, nextOn, selection, availableIds))}
                    options={renderPackOptions?.(pack)}
                  />
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
