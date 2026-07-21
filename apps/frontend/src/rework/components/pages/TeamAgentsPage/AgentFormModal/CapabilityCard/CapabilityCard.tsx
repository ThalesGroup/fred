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
import { Fragment, type PropsWithChildren, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { CapabilityCatalogEntry } from "../../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { TuningFieldRenderer } from "../TuningFieldRenderer.tsx";
import styles from "./CapabilityCard.module.css";

interface CapabilityCardProps {
  capability: CapabilityCatalogEntry;
  teamId?: string;
  checked: boolean;
  disabled: boolean;
  /** Per-capability config values keyed by the field's local key (matches config_fields[].key). */
  configValues: Record<string, unknown>;
  onToggle: () => void;
  onConfigChange: (key: string, value: unknown) => void;
}

/**
 * One selectable capability in the agent Tools tab: a switch that activates the
 * capability plus, when active, its `config_fields` rendered through the shared
 * metadata-driven {@link TuningFieldRenderer} (no bespoke per-field UI here).
 */
/**
 * The active capability's `config_fields` form. Fields sharing a `ui.group`
 * form a visual section: a thin divider is drawn whenever the group changes
 * between two consecutive VISIBLE fields (hidden fields — `ui.hide` or an
 * unsatisfied `ui.visible_when` — never produce dangling dividers). Fields
 * flagged `ui.advanced` render inside a collapsed "Advanced settings"
 * disclosure below the main section.
 */
function CapabilityConfigForm({
  configFields,
  configValues,
  disabled,
  teamId,
  onConfigChange,
}: {
  configFields: NonNullable<CapabilityCatalogEntry["config_fields"]>;
  configValues: Record<string, unknown>;
  disabled: boolean;
  teamId?: string;
  onConfigChange: (key: string, value: unknown) => void;
}) {
  const { t } = useTranslation();
  const effectiveValues = Object.fromEntries(configFields.map((f) => [f.key, configValues[f.key] ?? f.default]));
  const visibleFields = configFields.filter(
    (f) => !f.ui?.hide && (!f.ui?.visible_when || Boolean(effectiveValues[f.ui.visible_when])),
  );
  const mainFields = visibleFields.filter((f) => !f.ui?.advanced);
  const advancedFields = visibleFields.filter((f) => f.ui?.advanced);

  const renderGrouped = (fields: typeof visibleFields) =>
    fields.map((field, index) => (
      <Fragment key={field.key}>
        {index > 0 && field.ui?.group !== fields[index - 1].ui?.group && <hr className={styles.sectionDivider} />}
        <TuningFieldRenderer
          field={field}
          value={configValues[field.key]}
          onChange={onConfigChange}
          disabled={disabled}
          teamId={teamId}
          allValues={effectiveValues}
        />
      </Fragment>
    ));

  return (
    <div className={styles.subForm}>
      {renderGrouped(mainFields)}
      {advancedFields.length > 0 && (
        <AdvancedSection title={t("rework.teams.formAgent.advancedSettings")}>
          <div className={styles.advancedFields}>{renderGrouped(advancedFields)}</div>
        </AdvancedSection>
      )}
    </div>
  );
}

/**
 * Collapsed-by-default host of the `ui.advanced` fields, drawn as a clickable
 * labeled divider (`──── Advanced settings ⌄ ────`) so it reads as part of the
 * form's section language rather than a nested boxed accordion.
 */
function AdvancedSection({ title, children }: PropsWithChildren<{ title: string }>) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={styles.advancedToggle} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className={styles.advancedToggleLabel}>{title}</span>
        <Icon category="outlined" type={open ? "expand_less" : "expand_more"} />
      </button>
      {open && children}
    </>
  );
}

export function CapabilityCard({
  capability,
  teamId,
  checked,
  disabled,
  configValues,
  onToggle,
  onConfigChange,
}: CapabilityCardProps) {
  const { t } = useTranslation();
  const switchId = useId();
  const configFields = capability.config_fields ?? [];
  const hasOptions = checked && configFields.length > 0;
  const displayName = t(capability.name);
  const description = t(capability.description);

  return (
    <li className={`${styles.card} ${checked ? styles.cardActive : ""}`}>
      <div className={styles.header}>
        <Switch id={switchId} checked={checked} onChange={onToggle} disabled={disabled} aria-label={displayName} />
        <label htmlFor={switchId} className={styles.meta}>
          <span className={`${styles.name} ${checked ? styles.nameActive : ""}`}>{displayName}</span>
          {description && <span className={styles.description}>{description}</span>}
        </label>
      </div>

      {hasOptions && <CapabilityConfigForm {...{ configFields, configValues, disabled, teamId, onConfigChange }} />}
    </li>
  );
}
