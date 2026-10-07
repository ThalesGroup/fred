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
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import type { IconType } from "@shared/utils/Type.ts";
import { useEffect, useState, type ReactNode } from "react";
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
  /** Optional per-pack configuration UI (e.g. the PowerPoint template upload),
   *  revealed with a smooth open animation while the pack is active. Only some
   *  packs supply one; omit for packs with nothing to configure. */
  options?: ReactNode;
}

/**
 * Height-animated reveal for a pack's options, mounted only while the pack is
 * active — so the entrance animates once (max-height, the design-system's
 * chosen technique over grid-rows). The cap is lifted to `none` after the
 * open transition so async-growing content (the template's per-slide error
 * list) is never clipped.
 */
function PackOptionsReveal({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [capLifted, setCapLifted] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setOpen(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <div
      className={`${styles.optionsReveal} ${open ? styles.optionsRevealOpen : ""}`}
      style={capLifted ? { maxHeight: "none" } : undefined}
      onTransitionEnd={(e) => {
        if (e.propertyName === "max-height" && open) setCapLifted(true);
      }}
    >
      <div className={styles.optionsInner}>{children}</div>
    </div>
  );
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
 * (#2220), kept compact for small screens: the card body (32px icon, title,
 * description) is the activation switch, and an end segment expands the
 * capabilities the pack bundles, each showing whether the admin enabled it.
 */
export function ToolPackCard({
  pack,
  checked,
  disabled,
  availableIds,
  activeIds,
  onToggle,
  options,
}: ToolPackCardProps) {
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

  const includedLabel = t("rework.teams.formAgent.capabilities.included.label");
  const missingLabel = t("rework.teams.formAgent.capabilities.included.missing");

  return (
    <li className={styles.card} data-checked={checked}>
      {/* Two click zones with their own hover: the card body is the pack's
          switch, the end segment expands the included capabilities. */}
      <div className={styles.header}>
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          className={styles.toggleArea}
          disabled={disabled}
          onClick={() => onToggle(!checked)}
        >
          <span className={styles.icon} aria-hidden>
            <Icon category="outlined" type={pack.icon as IconType} />
          </span>
          <span className={styles.meta}>
            <span className={styles.titleRow}>
              <span className={styles.title}>{t(pack.titleKey)}</span>
              {hasMissing && (
                <Tooltip text={missingLabel}>
                  <span className={styles.missing} role="img" aria-label={missingLabel}>
                    <Icon category="outlined" type="error_outline" />
                  </span>
                </Tooltip>
              )}
            </span>
            <span className={styles.description}>{t(pack.descriptionKey)}</span>
          </span>
        </button>
        {hasIncluded && (
          <button
            type="button"
            className={styles.expand}
            aria-label={includedLabel}
            aria-expanded={expanded}
            onClick={() => setExpanded((o) => !o)}
          >
            <Icon category="outlined" type={expanded ? "expand_less" : "expand_more"} />
          </button>
        )}
      </div>

      {checked && options && <PackOptionsReveal>{options}</PackOptionsReveal>}

      {hasIncluded && (
        <>
          {expanded && (
            <ul className={styles.included} aria-label={includedLabel}>
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
