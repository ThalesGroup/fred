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
  const configFields = capability.config_fields ?? [];
  const hasOptions = checked && configFields.length > 0;
  const displayName = t(capability.name);
  const description = t(capability.description);

  return (
    <li className={`${styles.card} ${checked ? styles.cardActive : ""}`}>
      <div className={styles.header} onClick={onToggle}>
        <span className={styles.switchWrapper} onClick={(e) => e.stopPropagation()}>
          <Switch checked={checked} onChange={onToggle} disabled={disabled} />
        </span>
        <div className={styles.meta}>
          <span className={`${styles.name} ${checked ? styles.nameActive : ""}`}>{displayName}</span>
          {description && <span className={styles.description}>{description}</span>}
        </div>
      </div>

      {hasOptions && (
        <div className={styles.subForm}>
          {configFields.map((field) => (
            <TuningFieldRenderer
              key={field.key}
              field={field}
              value={configValues[field.key]}
              onChange={onConfigChange}
              disabled={disabled}
              teamId={teamId}
            />
          ))}
        </div>
      )}
    </li>
  );
}
