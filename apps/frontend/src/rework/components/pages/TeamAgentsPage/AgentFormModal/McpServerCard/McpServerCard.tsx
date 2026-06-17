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
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import { SwitchRow } from "@components/pages/TeamAgentsPage/AgentCreateEditModal/SwitchRow/SwitchRow.tsx";
import { DocumentLibraryScopePicker } from "@components/pages/TeamAgentsPage/AgentCreateEditModal/DocumentLibraryScopePicker/DocumentLibraryScopePicker";
import { useTranslation } from "react-i18next";
import type {
  ManagedAgentFieldSpec,
  ManagedMcpServerRef,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { CHAT_OPTION_FIELD_KEYS, hasConfigField, serverCarriesChatOptions } from "../chatOptionsConfig";
import styles from "./McpServerCard.module.css";

interface McpServerCardProps {
  server: ManagedMcpServerRef;
  teamId?: string;
  checked: boolean;
  disabled: boolean;
  /** Per-server config values keyed by the field's local key (matches config_fields[].key). */
  configValues: Record<string, unknown>;
  tuningValues: Record<string, unknown>;
  onToggle: () => void;
  onConfigChange: (key: string, value: unknown) => void;
  onTuningChange: (key: string, value: unknown) => void;
}

function resolveValue(field: ManagedAgentFieldSpec, configValues: Record<string, unknown>): unknown {
  const stored = configValues[field.key];
  if (stored !== undefined && stored !== null) return stored;
  if (field.default !== undefined && field.default !== null) return field.default;
  if (field.type === "boolean") return false;
  if (field.enum && field.enum.length > 0) return field.enum[0];
  return "";
}

export function McpServerCard({
  server,
  teamId,
  checked,
  disabled,
  configValues,
  tuningValues,
  onToggle,
  onConfigChange,
  onTuningChange,
}: McpServerCardProps) {
  const { t } = useTranslation();
  const configFields = server.config_fields ?? [];
  const hasOptions = checked && configFields.length > 0;
  const showAttachFilesOption = checked && serverCarriesChatOptions(configFields);
  const hasLibrariesBindingField = hasConfigField(configFields, CHAT_OPTION_FIELD_KEYS.librariesBinding);
  const hasLibrariesSelectionField = hasConfigField(configFields, CHAT_OPTION_FIELD_KEYS.librariesSelection);
  const hasBoundLibraryIdsField = hasConfigField(configFields, CHAT_OPTION_FIELD_KEYS.boundLibraryIds);
  const isLocked = server.locked === true;
  const displayLabel = server.display_name ? t(server.display_name) : server.id;
  const librariesBindingEnabled = Boolean(configValues[CHAT_OPTION_FIELD_KEYS.librariesBinding]);
  const showLibrariesBindingOption = checked && hasLibrariesBindingField;
  const showBoundLibraryPicker = showLibrariesBindingOption && librariesBindingEnabled && hasBoundLibraryIdsField;
  const selectedBoundLibraryIds = Array.isArray(configValues[CHAT_OPTION_FIELD_KEYS.boundLibraryIds])
    ? (configValues[CHAT_OPTION_FIELD_KEYS.boundLibraryIds] as string[])
    : [];
  const searchPolicyEnabled = Boolean(configValues[CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled]);
  const ragScopeEnabled = Boolean(configValues[CHAT_OPTION_FIELD_KEYS.searchRagScopeEnabled]);

  const enumOptionLabels: Record<string, Record<string, string>> = {
    [CHAT_OPTION_FIELD_KEYS.searchPolicy]: {
      strict: t("search.strict"),
      hybrid: t("search.hybrid"),
      semantic: t("search.semantic"),
    },
    [CHAT_OPTION_FIELD_KEYS.searchRagScope]: {
      corpus_only: t("chatbot.composerSettings.scopeCorpus"),
      hybrid: t("chatbot.composerSettings.scopeCorpusAndWeb"),
      general_only: t("chatbot.composerSettings.scopeGeneral"),
    },
  };

  return (
    <li className={`${styles.card} ${checked ? styles.cardActive : ""}`}>
      <div className={styles.header} onClick={isLocked ? undefined : onToggle}>
        <span className={styles.switchWrapper} onClick={(e) => e.stopPropagation()}>
          <Switch checked={checked} onChange={onToggle} disabled={disabled || isLocked} />
        </span>
        <div className={styles.meta}>
          <span className={`${styles.name} ${checked ? styles.nameActive : ""}`}>{displayLabel}</span>
          {isLocked && <span className={styles.lockedBadge}>{t("required")}</span>}
          {server.require_tools && server.require_tools.length > 0 && (
            <span className={styles.requireTools}>{server.require_tools.join(", ")}</span>
          )}
        </div>
      </div>

      {hasOptions && (
        <div className={styles.subForm}>
          {showAttachFilesOption && (
            <SwitchRow
              label={t("agentTuning.fields.chat_options_attach_files.title")}
              description={t("agentTuning.fields.chat_options_attach_files.description")}
              checked={Boolean(tuningValues[CHAT_OPTION_FIELD_KEYS.attachFiles])}
              onChange={(value) => onTuningChange(CHAT_OPTION_FIELD_KEYS.attachFiles, value)}
            />
          )}
          {showLibrariesBindingOption && (
            <div className={styles.booleanField}>
              <SwitchRow
                label={t("agentTuning.fields.library_binding.title")}
                description={t("agentTuning.fields.library_binding.description")}
                checked={librariesBindingEnabled}
                onChange={(value) => {
                  onConfigChange(CHAT_OPTION_FIELD_KEYS.librariesBinding, value);
                  if (value && hasLibrariesSelectionField) {
                    onConfigChange(CHAT_OPTION_FIELD_KEYS.librariesSelection, false);
                  } else if (!value && hasBoundLibraryIdsField) {
                    onConfigChange(CHAT_OPTION_FIELD_KEYS.boundLibraryIds, []);
                  }
                }}
              />
              {showBoundLibraryPicker && (
                <div className={styles.libraryPickerBlock}>
                  <DocumentLibraryScopePicker
                    teamId={teamId}
                    selectedTagIds={selectedBoundLibraryIds}
                    onChange={(tagIds) => onConfigChange(CHAT_OPTION_FIELD_KEYS.boundLibraryIds, tagIds)}
                  />
                </div>
              )}
            </div>
          )}
          {configFields.map((field) => {
            const value = resolveValue(field, configValues);

            if (
              field.key === CHAT_OPTION_FIELD_KEYS.librariesBinding ||
              field.key === CHAT_OPTION_FIELD_KEYS.boundLibraryIds
            ) {
              return null;
            }

            if (field.key === CHAT_OPTION_FIELD_KEYS.searchPolicy) {
              if (!searchPolicyEnabled || !field.enum || field.enum.length === 0) return null;
              const labels = enumOptionLabels[field.key] ?? {};
              const selectedIndex = Math.max(0, field.enum.indexOf(value as string));
              return (
                <div key={field.key} className={styles.fieldRow}>
                  <div className={styles.fieldLabel}>
                    <span className={styles.fieldTitle}>{field.title}</span>
                    {field.description && <span className={styles.fieldDescription}>{field.description}</span>}
                  </div>
                  <ButtonGroup
                    size="small"
                    color="secondary"
                    selectedIndex={selectedIndex}
                    onSelectedIndexChange={(i) => onConfigChange(field.key, field.enum![i])}
                    items={field.enum.map((opt) => ({
                      label: labels[opt] ?? opt.replace(/_/g, " "),
                    }))}
                  />
                </div>
              );
            }

            if (field.key === CHAT_OPTION_FIELD_KEYS.searchRagScope) {
              if (!ragScopeEnabled || !field.enum || field.enum.length === 0) return null;
              const labels = enumOptionLabels[field.key] ?? {};
              const selectedIndex = Math.max(0, field.enum.indexOf(value as string));
              return (
                <div key={field.key} className={styles.fieldRow}>
                  <div className={styles.fieldLabel}>
                    <span className={styles.fieldTitle}>{field.title}</span>
                    {field.description && <span className={styles.fieldDescription}>{field.description}</span>}
                  </div>
                  <ButtonGroup
                    size="small"
                    color="secondary"
                    selectedIndex={selectedIndex}
                    onSelectedIndexChange={(i) => onConfigChange(field.key, field.enum![i])}
                    items={field.enum.map((opt) => ({
                      label: labels[opt] ?? opt.replace(/_/g, " "),
                    }))}
                  />
                </div>
              );
            }

            if (field.type === "boolean") {
              if (field.key === CHAT_OPTION_FIELD_KEYS.librariesSelection && librariesBindingEnabled) {
                return null;
              }
              return (
                <div key={field.key} className={styles.booleanField}>
                  <SwitchRow
                    label={field.title}
                    description={field.description ?? ""}
                    checked={Boolean(value)}
                    onChange={(v) => {
                      onConfigChange(field.key, v);
                      if (field.key === CHAT_OPTION_FIELD_KEYS.librariesSelection && v && hasLibrariesBindingField) {
                        onConfigChange(CHAT_OPTION_FIELD_KEYS.librariesBinding, false);
                      }
                      if (field.key === CHAT_OPTION_FIELD_KEYS.librariesSelection && v && hasBoundLibraryIdsField) {
                        onConfigChange(CHAT_OPTION_FIELD_KEYS.boundLibraryIds, []);
                      }
                    }}
                  />
                </div>
              );
            }

            if (field.enum && field.enum.length > 0) {
              const labels = enumOptionLabels[field.key] ?? {};
              const selectedIndex = Math.max(0, field.enum.indexOf(value as string));
              return (
                <div key={field.key} className={styles.fieldRow}>
                  <div className={styles.fieldLabel}>
                    <span className={styles.fieldTitle}>{field.title}</span>
                    {field.description && <span className={styles.fieldDescription}>{field.description}</span>}
                  </div>
                  <ButtonGroup
                    size="small"
                    color="secondary"
                    selectedIndex={selectedIndex}
                    onSelectedIndexChange={(i) => onConfigChange(field.key, field.enum![i])}
                    items={field.enum.map((opt) => ({
                      label: labels[opt] ?? opt.replace(/_/g, " "),
                    }))}
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
