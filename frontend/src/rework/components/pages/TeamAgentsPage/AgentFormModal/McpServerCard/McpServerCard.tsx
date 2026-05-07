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
import Select from "@shared/molecules/Select/Select.tsx";
import { SwitchRow } from "@components/pages/TeamAgentsPage/AgentCreateEditModal/SwitchRow/SwitchRow.tsx";
import { useTranslation } from "react-i18next";
import type {
  ManagedAgentFieldSpec,
  ManagedMcpServerRef,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./McpServerCard.module.css";

interface McpServerCardProps {
  server: ManagedMcpServerRef;
  checked: boolean;
  disabled: boolean;
  /** Per-server config values keyed by the field's local key (matches config_fields[].key). */
  configValues: Record<string, unknown>;
  onToggle: () => void;
  onConfigChange: (key: string, value: unknown) => void;
}

function resolveValue(field: ManagedAgentFieldSpec, configValues: Record<string, unknown>): unknown {
  const stored = configValues[field.key];
  if (stored !== undefined && stored !== null) return stored;
  if (field.default !== undefined && field.default !== null) return field.default;
  if (field.type === "boolean") return false;
  if (field.enum && field.enum.length > 0) return field.enum[0];
  return "";
}

function useEnumOptionDescriptions(): Record<string, Record<string, string>> {
  const { t } = useTranslation();
  return {
    "chat_options.search_policy": {
      strict: t("search.strictDescription"),
      hybrid: t("search.hybridDescription"),
      semantic: t("search.semanticDescription"),
    },
    "chat_options.search_rag_scope": {
      corpus_only: t("chatbot.ragScope.tooltipCorpus"),
      hybrid: t("chatbot.ragScope.tooltipHybrid"),
      general_only: t("chatbot.ragScope.tooltipGeneral"),
    },
  };
}

export function McpServerCard({
  server,
  checked,
  disabled,
  configValues,
  onToggle,
  onConfigChange,
}: McpServerCardProps) {
  const enumOptionDescriptions = useEnumOptionDescriptions();
  const configFields = server.config_fields ?? [];
  const hasOptions = checked && configFields.length > 0;

  return (
    <li className={`${styles.card} ${checked ? styles.cardActive : ""}`}>
      <div className={styles.header} onClick={onToggle}>
        <span className={styles.switchWrapper} onClick={(e) => e.stopPropagation()}>
          <Switch checked={checked} onChange={onToggle} disabled={disabled} />
        </span>
        <div className={styles.meta}>
          <span className={`${styles.name} ${checked ? styles.nameActive : ""}`}>
            {server.display_name || server.id}
          </span>
          {server.require_tools && server.require_tools.length > 0 && (
            <span className={styles.requireTools}>{server.require_tools.join(", ")}</span>
          )}
        </div>
      </div>

      {hasOptions && (
        <div className={styles.subForm}>
          {configFields.map((field) => {
            const value = resolveValue(field, configValues);

            if (field.type === "boolean") {
              return (
                <SwitchRow
                  key={field.key}
                  label={field.title}
                  description={field.description ?? ""}
                  checked={Boolean(value)}
                  onChange={(v) => onConfigChange(field.key, v)}
                />
              );
            }

            if (field.enum && field.enum.length > 0) {
              return (
                <div key={field.key} className={styles.fieldRow}>
                  <div className={styles.fieldLabel}>
                    <span className={styles.fieldTitle}>{field.title}</span>
                    {field.description && <span className={styles.fieldDescription}>{field.description}</span>}
                  </div>
                  <Select
                    size="xs"
                    compact
                    value={value as string}
                    options={field.enum.map((opt) => ({
                      value: opt,
                      label: opt,
                      key: opt,
                      description: enumOptionDescriptions[field.key]?.[opt],
                    }))}
                    onChange={(v) => onConfigChange(field.key, v)}
                    disabled={disabled}
                  />
                </div>
              );
            }

            return null;
          })}
        </div>
      )}
    </li>
  );
}
