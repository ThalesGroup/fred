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

import { useTranslation } from "react-i18next";
import { ToolPackCard } from "../ToolPackCard/ToolPackCard.tsx";
import { applyPackToggle, derivePackChecked, type CapabilitySelectionState } from "../toolPackLogic.ts";
import { TOOL_PACK_SECTIONS } from "../toolPacks.ts";
import styles from "./SimpleCapabilitiesView.module.css";

interface SimpleCapabilitiesViewProps {
  /** Team's admin-enabled capability ids (from the template's available_capabilities). */
  availableIds: ReadonlySet<string>;
  selection: CapabilitySelectionState;
  disabled: boolean;
  onSelectionChange: (next: CapabilitySelectionState) => void;
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
}: SimpleCapabilitiesViewProps) {
  const { t } = useTranslation();
  const activeIds = new Set(selection.selectedCapabilityIds);

  return (
    <div className={styles.view}>
      {TOOL_PACK_SECTIONS.map((section) => (
        <section key={section.id} className={styles.section}>
          <h3 className={styles.sectionHeader}>{t(section.titleKey)}</h3>
          {section.emptyState ? (
            <p className={styles.emptyState}>{t("rework.teams.formAgent.capabilities.actionsIntegrationEmpty")}</p>
          ) : (
            <ul className={styles.packList}>
              {section.packs.map((pack) => (
                <ToolPackCard
                  key={pack.id}
                  pack={pack}
                  checked={derivePackChecked(pack, selection)}
                  disabled={disabled}
                  availableIds={availableIds}
                  activeIds={activeIds}
                  onToggle={(nextOn) => onSelectionChange(applyPackToggle(pack, nextOn, selection, availableIds))}
                />
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
