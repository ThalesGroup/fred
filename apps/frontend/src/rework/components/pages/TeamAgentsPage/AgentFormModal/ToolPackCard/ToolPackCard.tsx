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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import type { IconType } from "@shared/utils/Type.ts";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { isCapabilityAdminEnabled } from "../toolPackLogic.ts";
import type { ToolPack } from "../toolPacks.ts";
import styles from "./ToolPackCard.module.css";

interface ToolPackCardProps {
  pack: ToolPack;
  /** Whether the pack is currently active (derived from the form selection). */
  checked: boolean;
  /** Whether the admin enabled the capability the pack needs to function. When
   *  false the switch is locked off. */
  available: boolean;
  /** Form-level disable (submitting). */
  disabled: boolean;
  /** Team's admin-enabled capability ids, for the included-capability badges. */
  availableIds: ReadonlySet<string>;
  onToggle: (nextOn: boolean) => void;
}

/**
 * One "capability pack" card for the agent form's Simple capabilities view
 * (#2220): a 48px themed icon, title/description, an activation switch, and an
 * expandable list of the capabilities the pack bundles — each showing whether
 * the platform admin enabled it for the team. Shape mirrors the app's other
 * organism cards (AgentCard/CapabilityCard) so the form reads as one system.
 */
export function ToolPackCard({ pack, checked, available, disabled, availableIds, onToggle }: ToolPackCardProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const hasIncluded = pack.includes.length > 0;
  const switchDisabled = disabled || !available;

  return (
    <li className={styles.card} data-checked={checked} data-available={available}>
      {/* Whole header is the click target (padding included) — same <label>
          pattern as CapabilityCard, so clicks near the edges still toggle. */}
      <label className={styles.header}>
        <span className={styles.icon} aria-hidden>
          <Icon category="outlined" type={pack.icon as IconType} />
        </span>
        <span className={styles.meta}>
          <span className={styles.title}>{t(pack.titleKey)}</span>
          <span className={styles.description}>{t(pack.descriptionKey)}</span>
        </span>
        <span className={styles.switch}>
          <Switch
            checked={checked}
            onChange={() => onToggle(!checked)}
            disabled={switchDisabled}
            aria-label={t(pack.titleKey)}
          />
        </span>
      </label>

      {hasIncluded && (
        <>
          <button
            type="button"
            className={styles.expander}
            aria-expanded={expanded}
            onClick={() => setExpanded((o) => !o)}
          >
            <span>
              {expanded
                ? t("rework.teams.formAgent.capabilities.included.hide")
                : t("rework.teams.formAgent.capabilities.included.show")}
            </span>
            <Icon category="outlined" type={expanded ? "expand_less" : "expand_more"} />
          </button>

          {expanded && (
            <ul className={styles.included}>
              {pack.includes.map((entry) => {
                const enabled = isCapabilityAdminEnabled(entry.capabilityId, availableIds);
                return (
                  <li key={entry.capabilityId} className={styles.includedRow}>
                    <Tooltip
                      text={t(
                        enabled
                          ? "rework.teams.formAgent.capabilities.included.enabledTooltip"
                          : "rework.teams.formAgent.capabilities.included.disabledTooltip",
                      )}
                    >
                      <span
                        className={enabled ? styles.statusOk : styles.statusOff}
                        role="img"
                        aria-label={t(
                          enabled
                            ? "rework.teams.formAgent.capabilities.included.enabledTooltip"
                            : "rework.teams.formAgent.capabilities.included.disabledTooltip",
                        )}
                      >
                        <Icon category="outlined" type={enabled ? "check_circle" : "error"} />
                      </span>
                    </Tooltip>
                    <span className={styles.includedLabel}>{t(entry.labelKey, { defaultValue: entry.labelKey })}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </li>
  );
}
