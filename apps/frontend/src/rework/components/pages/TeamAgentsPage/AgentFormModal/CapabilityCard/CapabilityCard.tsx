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

import Switch from "@shared/atoms/Switch/Switch.tsx";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { configWidgetFor } from "../../../../../features/capabilities/configWidgetRegistry.ts";
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
  /** Pending asset files for this capability, keyed by AssetSlot.key (#1903). */
  assetFiles: Record<string, File | undefined>;
  onToggle: () => void;
  onConfigChange: (key: string, value: unknown) => void;
  onAssetFileChange: (slotKey: string, file: File | null) => void;
  onBlockingErrorChange: (message: string | null) => void;
}

/**
 * One selectable capability in the agent Tools tab: a switch that activates the
 * capability plus, when active, its `config_fields` rendered through the shared
 * metadata-driven {@link TuningFieldRenderer} — or, for a field whose
 * `ui.widget` resolves in the owning capability's plugin `configWidgets`, the
 * plugin's custom form widget (RFC §9 item 4, #1903). A widget id is rendered
 * at most once even when several fields name it.
 */
export function CapabilityCard({
  capability,
  teamId,
  checked,
  disabled,
  configValues,
  assetFiles,
  onToggle,
  onConfigChange,
  onAssetFileChange,
  onBlockingErrorChange,
}: CapabilityCardProps) {
  const { t } = useTranslation();
  const switchId = useId();
  const configFields = capability.config_fields ?? [];
  const hasOptions = checked && configFields.length > 0;
  const displayName = t(capability.name);
  const description = t(capability.description);

  const renderedWidgets = new Set<string>();

  return (
    <li className={`${styles.card} ${checked ? styles.cardActive : ""}`}>
      <div className={styles.header}>
        <Switch id={switchId} checked={checked} onChange={onToggle} disabled={disabled} aria-label={displayName} />
        <label htmlFor={switchId} className={styles.meta}>
          <span className={`${styles.name} ${checked ? styles.nameActive : ""}`}>{displayName}</span>
          {description && <span className={styles.description}>{description}</span>}
        </label>
      </div>

      {hasOptions && (
        <div className={styles.subForm}>
          {configFields.map((field) => {
            const Widget = configWidgetFor(capability.id, field.ui?.widget);
            if (Widget) {
              const widgetId = field.ui?.widget as string;
              if (renderedWidgets.has(widgetId)) return null;
              renderedWidgets.add(widgetId);
              return (
                <Widget
                  key={widgetId}
                  capabilityId={capability.id}
                  teamId={teamId}
                  disabled={disabled}
                  configValues={configValues}
                  onConfigChange={onConfigChange}
                  assetFiles={assetFiles}
                  onAssetFileChange={onAssetFileChange}
                  onBlockingErrorChange={onBlockingErrorChange}
                />
              );
            }
            return (
              <TuningFieldRenderer
                key={field.key}
                field={field}
                value={configValues[field.key]}
                onChange={onConfigChange}
                disabled={disabled}
                teamId={teamId}
              />
            );
          })}
        </div>
      )}
    </li>
  );
}
