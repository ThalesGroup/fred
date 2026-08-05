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
import { includedCapabilityStatus, type IncludedCapabilityStatus } from "../toolPackLogic.ts";
import type { ToolPack } from "../toolPacks.ts";
import styles from "./ToolPackCard.module.css";

interface ToolPackCardProps {
  pack: ToolPack;
  /** Whether the pack is currently active (derived from the form selection). */
  checked: boolean;
  /** Form-level disable (submitting). */
  disabled: boolean;
  /** Team's admin-enabled capability ids (drives the included-capability badges). */
  availableIds: ReadonlySet<string>;
  /** Capability ids currently active on the agent (drives active vs. inactive). */
  activeIds: ReadonlySet<string>;
  onToggle: (nextOn: boolean) => void;
}

const STATUS_ICON: Record<IncludedCapabilityStatus, IconType> = {
  active: "check_circle",
  inactive: "radio_button_unchecked",
  unavailable: "error",
};

const STATUS_TOOLTIP_KEY: Record<IncludedCapabilityStatus, string> = {
  active: "rework.teams.formAgent.capabilities.included.activeTooltip",
  inactive: "rework.teams.formAgent.capabilities.included.inactiveTooltip",
  unavailable: "rework.teams.formAgent.capabilities.included.unavailableTooltip",
};

/**
 * One "capability pack" card for the agent form's Simple capabilities view
 * (#2220): a 48px themed icon, title/description, an activation switch, and an
 * expandable list of the capabilities the pack bundles — each showing whether
 * the platform admin enabled it for the team. Shape mirrors the app's other
 * organism cards (AgentCard/CapabilityCard) so the form reads as one system.
 */
export function ToolPackCard({ pack, checked, disabled, availableIds, activeIds, onToggle }: ToolPackCardProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const hasIncluded = pack.includes.length > 0;
  const includedStatuses = pack.includes.map((entry) => ({
    entry,
    status: includedCapabilityStatus(entry.capabilityId, availableIds, activeIds),
  }));
  // Some included capability the admin hasn't enabled — the pack still works
  // with whatever IS available; we just flag it (never disable the pack).
  const hasMissing = includedStatuses.some(({ status }) => status === "unavailable");

  return (
    <li className={styles.card} data-checked={checked}>
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
            disabled={disabled}
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
            <span className={styles.expanderStart}>
              <span>{t("rework.teams.formAgent.capabilities.included.label")}</span>
              {/* At-a-glance status summary: one mini icon per included capability,
                  reusing the detailed list's icons/colors. Decorative — the
                  detailed list below carries the per-item accessible labels. */}
              <span className={styles.summary} aria-hidden>
                {includedStatuses.map(({ entry, status }) => (
                  <span key={entry.capabilityId} className={`${styles.summaryIcon} ${styles[`status_${status}`]}`}>
                    <Icon category="outlined" type={STATUS_ICON[status]} />
                  </span>
                ))}
              </span>
            </span>
            <span className={styles.expanderEnd}>
              {hasMissing && (
                <span className={styles.missing}>
                  <Icon category="outlined" type="error_outline" />
                  <span>{t("rework.teams.formAgent.capabilities.included.missing")}</span>
                </span>
              )}
              <span className={styles.chevron}>
                <Icon category="outlined" type={expanded ? "expand_less" : "expand_more"} />
              </span>
            </span>
          </button>

          {expanded && (
            <ul className={styles.included}>
              {includedStatuses.map(({ entry, status }) => {
                const tooltip = t(STATUS_TOOLTIP_KEY[status]);
                return (
                  <li key={entry.capabilityId} className={styles.includedRow}>
                    <Tooltip text={tooltip}>
                      <span
                        className={`${styles.statusIcon} ${styles[`status_${status}`]}`}
                        role="img"
                        aria-label={tooltip}
                      >
                        <Icon category="outlined" type={STATUS_ICON[status]} />
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
