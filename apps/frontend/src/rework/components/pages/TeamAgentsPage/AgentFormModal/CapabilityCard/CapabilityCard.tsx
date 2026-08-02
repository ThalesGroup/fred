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
import { Fragment, type PropsWithChildren, type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { configWidgetFor } from "../../../../../features/capabilities/configWidgetRegistry.ts";
import type { CapabilityCatalogEntry } from "../../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { TuningFieldRenderer } from "../TuningFieldRenderer.tsx";
import styles from "./CapabilityCard.module.css";

interface CapabilityCardProps {
  name: string;
  description?: string;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
  /** Rendered inside the card's own sub-form shell (background/divider/padding)
   *  when truthy — omit or pass `false` for a card with nothing to configure. */
  subForm?: ReactNode;
}

/**
 * Generic toggle card for the agent form's Capabilities tab: a switch plus a
 * name/description, and an optional sub-form area. Used for every entry in
 * that tab — a template-provided capability (its `config_fields` rendered via
 * {@link CapabilityConfigForm} as `subForm`) and the built-in reasoning offer
 * (REASON-01, Amendment C — a `SwitchRow` as `subForm`) alike, so the tab has
 * exactly one card component regardless of what's actually being toggled.
 */
export function CapabilityCard({ name, description, checked, disabled, onToggle, subForm }: CapabilityCardProps) {
  return (
    <li className={styles.card}>
      {/* The whole header is the click target, padding included — <label>
          wrapping the Switch as a descendant (same pattern as SwitchRow), not
          a plain <div> whose padding sits outside a smaller inner <label>'s
          box and swallows clicks near the card's edges. */}
      <label className={styles.header}>
        <Switch checked={checked} onChange={onToggle} disabled={disabled} aria-label={name} />
        <div className={styles.meta}>
          <span className={`${styles.name} ${checked ? styles.nameActive : ""}`}>{name}</span>
          {description && <span className={styles.description}>{description}</span>}
        </div>
      </label>

      {subForm && <div className={styles.subForm}>{subForm}</div>}
    </li>
  );
}

/**
 * A template-provided capability's `config_fields` form, passed as
 * {@link CapabilityCard}'s `subForm`. A field whose `ui.widget` resolves in
 * the owning capability's plugin `configWidgets` renders through the
 * plugin's custom form widget (RFC §9 item 4, #1903) — a widget id is
 * rendered at most once even when several fields name it. Remaining fields go
 * through the shared metadata-driven {@link TuningFieldRenderer}. Fields
 * sharing a `ui.group` form a visual section: a thin divider is drawn
 * whenever the group changes between two consecutive VISIBLE fields (hidden
 * fields — `ui.hide` or an unsatisfied `ui.visible_when` — never produce
 * dangling dividers). Fields flagged `ui.advanced` render inside a collapsed
 * "Advanced settings" disclosure below the main section.
 */
export function CapabilityConfigForm({
  capability,
  configFields,
  configValues,
  disabled,
  teamId,
  assetFiles,
  onConfigChange,
  onAssetFileChange,
  onBlockingErrorChange,
}: {
  capability: CapabilityCatalogEntry;
  configFields: NonNullable<CapabilityCatalogEntry["config_fields"]>;
  configValues: Record<string, unknown>;
  disabled: boolean;
  teamId?: string;
  assetFiles: Record<string, File | undefined>;
  onConfigChange: (key: string, value: unknown) => void;
  onAssetFileChange: (slotKey: string, file: File | null) => void;
  onBlockingErrorChange: (message: string | null) => void;
}) {
  const { t } = useTranslation();
  const effectiveValues = Object.fromEntries(configFields.map((f) => [f.key, configValues[f.key] ?? f.default]));
  const visibleFields = configFields.filter(
    (f) => !f.ui?.hide && (!f.ui?.visible_when || Boolean(effectiveValues[f.ui.visible_when])),
  );
  const mainFields = visibleFields.filter((f) => !f.ui?.advanced);
  const advancedFields = visibleFields.filter((f) => f.ui?.advanced);

  const renderedWidgets = new Set<string>();

  const renderGrouped = (fields: typeof visibleFields) =>
    fields.map((field, index) => {
      const Widget = configWidgetFor(capability.id, field.ui?.widget);
      if (Widget) {
        const widgetId = field.ui?.widget as string;
        if (renderedWidgets.has(widgetId)) return null;
        renderedWidgets.add(widgetId);
        return (
          <Fragment key={widgetId}>
            {index > 0 && field.ui?.group !== fields[index - 1].ui?.group && <hr className={styles.sectionDivider} />}
            <Widget
              capabilityId={capability.id}
              teamId={teamId}
              disabled={disabled}
              configValues={configValues}
              onConfigChange={onConfigChange}
              assetFiles={assetFiles}
              onAssetFileChange={onAssetFileChange}
              onBlockingErrorChange={onBlockingErrorChange}
            />
          </Fragment>
        );
      }
      return (
        <Fragment key={field.key}>
          {index > 0 && field.ui?.group !== fields[index - 1].ui?.group && <hr className={styles.sectionDivider} />}
          {/* A ui.visible_when field only exists under its gating sibling — a
              slight indent makes the subordination readable. */}
          <div className={field.ui?.visible_when ? styles.dependentField : undefined}>
            <TuningFieldRenderer
              field={field}
              value={configValues[field.key]}
              onChange={onConfigChange}
              disabled={disabled}
              teamId={teamId}
              allValues={effectiveValues}
            />
          </div>
        </Fragment>
      );
    });

  return (
    <>
      {renderGrouped(mainFields)}
      {advancedFields.length > 0 && (
        <AdvancedSection title={t("rework.teams.formAgent.advancedSettings")}>
          <div className={styles.advancedFields}>{renderGrouped(advancedFields)}</div>
        </AdvancedSection>
      )}
    </>
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
