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

import { EntityIdentity } from "@shared/molecules/EntityIdentity/EntityIdentity.tsx";
import { useTranslation } from "react-i18next";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { capabilityLabel } from "./capabilityEnablement";
import { ModelDisplayNameEditor } from "./ModelDisplayNameEditor";
import { ModelDetailTooltip } from "./ModelDetailTooltip";
import styles from "./FeaturesPage.module.css";

export function ModelIdentityCell({
  capability,
  dimmed,
  isNew = false,
}: {
  capability: CapabilityEnablementItem;
  dimmed: boolean;
  isNew?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const reasoningLevels = [...new Set(Object.values(capability.model_reasoning_efforts ?? {}).flat())];
  const otherCapabilities = capability.model_capabilities?.filter((modelCapability) => modelCapability !== "chat");
  const discoveredTypeUnknown = Boolean(
    capability.model_discovery_source_id && !capability.model_chat_capability_verified,
  );
  const compactTokens = (count: number) =>
    new Intl.NumberFormat(i18n?.language ?? "fr", { notation: "compact", maximumFractionDigits: 1 }).format(count);
  return (
    <div className={styles.modelCell}>
      <div className={styles.modelIdentity}>
        <EntityIdentity
          name={capabilityLabel(t, capability)}
          sourceId={capability.name}
          runtimeId={(capability.model_runtime_ids ?? []).join(", ") || capability.runtime_id}
          version={capability.public_version}
          dimmed={dimmed}
        />
      </div>
      {isNew && <span className={styles.newModelBadge}>{t("rework.admin.capabilities.discovery.new")}</span>}
      {(capability.model_context_window_tokens ||
        capability.model_max_input_tokens ||
        capability.model_max_output_tokens ||
        otherCapabilities?.length ||
        discoveredTypeUnknown ||
        reasoningLevels.length > 0 ||
        capability.model_discovery_source_id) && (
        <span className={styles.modelSpecs}>
          {capability.model_discovery_source_id && (
            <span className={styles.modelSpecChip}>
              {t("rework.admin.capabilities.modelSpecs.source", { source: capability.model_discovery_source_id })}
            </span>
          )}
          {discoveredTypeUnknown && (
            <span className={styles.modelSpecChip}>{t("rework.admin.capabilities.modelSpecs.typeUnknown")}</span>
          )}
          {!discoveredTypeUnknown &&
            otherCapabilities?.map((modelCapability) => (
              <span key={modelCapability} className={styles.modelSpecChip}>
                {t(`rework.admin.capabilities.modelSpecs.capabilities.${modelCapability}`, {
                  defaultValue: modelCapability,
                })}
              </span>
            ))}
          {capability.model_context_window_tokens && (
            <span
              className={styles.modelSpecChip}
              title={t("rework.admin.capabilities.modelSpecs.contextExact", {
                count: capability.model_context_window_tokens,
              })}
            >
              {t("rework.admin.capabilities.modelSpecs.context", {
                value: compactTokens(capability.model_context_window_tokens),
              })}
            </span>
          )}
          {capability.model_max_input_tokens && (
            <span className={styles.modelSpecChip}>
              {t("rework.admin.capabilities.modelSpecs.input", {
                value: compactTokens(capability.model_max_input_tokens),
              })}
            </span>
          )}
          {capability.model_max_output_tokens && (
            <span className={styles.modelSpecChip}>
              {t("rework.admin.capabilities.modelSpecs.output", {
                value: compactTokens(capability.model_max_output_tokens),
              })}
            </span>
          )}
          {reasoningLevels.length > 0 && (
            <span className={styles.modelSpecChip}>
              {t("rework.admin.capabilities.modelSpecs.reasoningLevels", { levels: reasoningLevels.join(", ") })}
            </span>
          )}
        </span>
      )}
      <ModelDisplayNameEditor
        capabilityId={capability.id}
        wireName={capability.name}
        effectiveName={capability.model_display_name}
        overrideName={capability.model_display_name_override}
      />
      {capability.model_discovery_source_id && (
        <ModelDetailTooltip
          sourceId={capability.model_discovery_source_id}
          modelId={capability.name}
          runtimeId={capability.model_runtime_ids?.[0] ?? capability.runtime_id ?? undefined}
        />
      )}
    </div>
  );
}
